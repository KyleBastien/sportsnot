"""Per-player injury status from ESPN, with a manual override authority (US-008).

The pipeline needs a current injury picture per player without routine hand
entry. ESPN's public NHL JSON is the locked-in source (SPEC §5):

* **Injuries feed** —
  ``https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/injuries``.
  Response shape: ``{"injuries": [ {team group} ]}`` where each *team group*
  carries ``id`` / ``displayName`` (and sometimes ``abbreviation``) plus a
  nested ``injuries`` list. Each nested *injury entry* has ``status`` (e.g.
  ``"Out"`` / ``"Day-To-Day"`` / ``"Injured Reserve"``), ``date``, an
  ``athlete`` block (``id`` / ``fullName`` / ``position.abbreviation`` /
  ``status``), a ``type`` object (``name`` like ``INJURY_STATUS_OUT``), and a
  ``details`` object carrying the body-part ``type`` and expected ``returnDate``.
* **Core athlete detail** —
  ``https://sports.core.api.espn.com/v2/sports/hockey/leagues/nhl/athletes/{id}``
  is fetched only when a position/name gap must be filled; the injuries feed
  already carries position + name for the vast majority of entries.

Two hard rules govern this module:

* **Manual override is the final authority.** ``data/overrides/injuries.yaml``
  merges *over* the source: an override matched to a source row replaces its
  status / return date; an unmatched override is injected as a new row. Nothing
  the source says can win against a committed override.
* **Source failure degrades gracefully.** If the ESPN feed cannot be reached the
  pipeline continues on the last-known ``injuries.parquet`` plus the overrides,
  emitting a warning rather than crashing (SPEC §7 loud-but-non-fatal).

Historical injury data is deliberately NOT pulled here — ESPN resolves old game
``injuries`` blocks against *today's* rosters (SPEC §5 / PROVENANCE §10), so the
live feed is the source for CURRENT status only. Absence-spell derivation for
return-time calibration lives in US-015, not here.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field

from draft_oracle.ingest.entity_match import (
    DEFAULT_OVERRIDES_DIR,
    PlayerIndex,
    build_player_index,
    last_name_key,
    normalize_name,
)
from draft_oracle.ingest.nhl_api import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_TIMEOUT,
    NHLApiError,
    ResponseCache,
)
from draft_oracle.ingest.normalize import DEFAULT_NORMALIZED_DIR
from draft_oracle.ingest.odds import resolve_team_id

# ── Endpoints (the only place ESPN injury URLs are allowed) ──────────────

ESPN_INJURIES_BASE = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl"
ESPN_CORE_BASE = "https://sports.core.api.espn.com/v2/sports/hockey/leagues/nhl"

DEFAULT_INJURIES_CACHE_DIR = Path("data/raw/espn-injuries")
DEFAULT_INJURIES_DELAY = 1.0

INJURIES_TABLE_NAME = "injuries"
DEFAULT_INJURIES_OVERRIDES = DEFAULT_OVERRIDES_DIR / "injuries.yaml"

# Normalized status vocabulary (AC: out / IR / day-to-day / healthy).
STATUS_OUT = "out"
STATUS_IR = "ir"
STATUS_DAY_TO_DAY = "day_to_day"
STATUS_HEALTHY = "healthy"
NORMALIZED_STATUSES: tuple[str, ...] = (
    STATUS_OUT,
    STATUS_IR,
    STATUS_DAY_TO_DAY,
    STATUS_HEALTHY,
)

SOURCE_ESPN = "espn"
SOURCE_OVERRIDE = "override"
SOURCE_LAST_KNOWN = "last_known"

_INJURY_COLUMNS: tuple[str, ...] = (
    "player_id",
    "espn_id",
    "player_name",
    "position",
    "team_id",
    "team_abbrev",
    "status",
    "status_raw",
    "return_date",
    "detail",
    "as_of_date",
    "source",
)


# ── ESPN response models ─────────────────────────────────────────────────


class _Model(BaseModel):
    """Base: ignore unknown fields, accept both aliases and field names."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class EspnPosition(_Model):
    name: str | None = None
    abbreviation: str | None = None


class EspnAthlete(_Model):
    id: int | None = None
    full_name: str | None = Field(default=None, alias="fullName")
    display_name: str | None = Field(default=None, alias="displayName")
    position: EspnPosition | None = None


class EspnInjuryType(_Model):
    name: str | None = None
    description: str | None = None
    abbreviation: str | None = None


class EspnInjuryDetails(_Model):
    # ``type`` here is the body part ("Lower Body"), NOT the status object.
    type: str | None = None
    return_date: str | None = Field(default=None, alias="returnDate")


class EspnInjuryEntry(_Model):
    status: str | None = None
    date: str | None = None
    athlete: EspnAthlete | None = None
    type: EspnInjuryType | None = None
    details: EspnInjuryDetails | None = None


class EspnTeamInjuries(_Model):
    id: int | None = None
    display_name: str | None = Field(default=None, alias="displayName")
    abbreviation: str | None = None
    injuries: list[EspnInjuryEntry] = Field(default_factory=list)


class EspnInjuriesResponse(_Model):
    injuries: list[EspnTeamInjuries] = Field(default_factory=list)


# ── Status normalization ─────────────────────────────────────────────────


def normalize_status(status_raw: str | None, type_name: str | None = None) -> str:
    """Fold an ESPN status label + type name to the normalized vocabulary.

    Precedence: an explicit ``INJURY_STATUS_*`` type name is authoritative, then
    the free-text ``status``. Anything unrecognized (or a healthy/active marker)
    normalizes to :data:`STATUS_HEALTHY` so the table never carries an
    uninterpretable status.
    """
    type_key = (type_name or "").strip().upper()
    if type_key:
        if "INJURED_RESERVE" in type_key or type_key.endswith("_IR") or "LTIR" in type_key:
            return STATUS_IR
        if "DAY_TO_DAY" in type_key or "QUESTIONABLE" in type_key or "GTD" in type_key:
            return STATUS_DAY_TO_DAY
        if "OUT" in type_key or "SUSPEN" in type_key:
            return STATUS_OUT
        if "ACTIVE" in type_key or "HEALTHY" in type_key:
            return STATUS_HEALTHY

    text = (status_raw or "").strip().lower()
    collapsed = text.replace("-", " ").replace("_", " ")
    collapsed = " ".join(collapsed.split())
    if not collapsed:
        return STATUS_HEALTHY
    if "injured reserve" in collapsed or collapsed in {"ir", "ltir"} or "long term" in collapsed:
        return STATUS_IR
    if "day to day" in collapsed or "questionable" in collapsed or "gtd" in collapsed:
        return STATUS_DAY_TO_DAY
    if "out" in collapsed or "suspension" in collapsed or "suspended" in collapsed:
        return STATUS_OUT
    if "active" in collapsed or "healthy" in collapsed or "probable" in collapsed:
        return STATUS_HEALTHY
    # Unknown but non-empty statuses are conservatively treated as day-to-day so
    # they surface for review rather than silently reading as healthy.
    return STATUS_DAY_TO_DAY


# ── Feed → normalized rows ───────────────────────────────────────────────


# ESPN skater position abbreviations fold to the fantasy pool position (F/D);
# goalies (and anything unrecognized) are NOT resolved to a skater id because a
# goalie injury is consumed at the team level (team_abbrev + position), not by a
# per-player join.
_ESPN_SKATER_POSITIONS: dict[str, str] = {
    "C": "F",
    "LW": "F",
    "RW": "F",
    "L": "F",
    "R": "F",
    "W": "F",
    "F": "F",
    "D": "D",
}


def _fantasy_position(espn_position: str | None) -> str | None:
    if espn_position is None:
        return None
    return _ESPN_SKATER_POSITIONS.get(espn_position.strip().upper())


def _team_abbrev_key(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


@dataclass(frozen=True)
class PlayerIdResolution:
    """Outcome of mapping one ESPN athlete to an NHL ``player_id``."""

    player_id: int | None
    method: str  # exact | team | position | lastname | goalie | unresolved


def resolve_espn_player_id(
    name: str | None,
    team_abbrev: str | None,
    position: str | None,
    index: PlayerIndex,
    team_by_id: Mapping[int, Any],
) -> PlayerIdResolution:
    """Resolve one ESPN injury entry to an NHL ``player_id`` via name + team.

    Uses the shared entity-match index (``build_player_index``): an exact
    normalized-name hit wins; same-name collisions (there are two ``Sebastian
    Aho``s) are disambiguated by the injury's team abbreviation, then by
    position. A unique surname fallback covers feed spellings the exact key
    misses. Goalies fold to ``method='goalie'`` (team-level consumers key on
    ``team_abbrev``); anything left ambiguous is ``method='unresolved'`` and is
    NEVER guessed (SPEC §7 honesty rule).
    """
    fantasy_pos = _fantasy_position(position)
    if fantasy_pos is None:
        return PlayerIdResolution(None, "goalie")
    norm = normalize_name(name)
    team_key = _team_abbrev_key(team_abbrev)

    def _disambiguate(candidates: list[Any], method: str) -> PlayerIdResolution | None:
        if len(candidates) == 1:
            return PlayerIdResolution(candidates[0].player_id, method)
        if team_key is not None:
            by_team = [
                c
                for c in candidates
                if _team_abbrev_key(team_by_id.get(c.player_id)) == team_key
            ]
            if len(by_team) == 1:
                return PlayerIdResolution(by_team[0].player_id, "team")
            if by_team:
                candidates = by_team
        by_pos = [c for c in candidates if c.position == fantasy_pos]
        if len(by_pos) == 1:
            return PlayerIdResolution(by_pos[0].player_id, "position")
        return None

    exact = index.by_norm.get(norm, [])
    if exact:
        resolved = _disambiguate(exact, "exact")
        return resolved if resolved is not None else PlayerIdResolution(None, "unresolved")

    last = last_name_key(name)
    last_hits = index.by_last.get(last, []) if last else []
    if last_hits:
        resolved = _disambiguate(last_hits, "lastname")
        if resolved is not None:
            return resolved
    return PlayerIdResolution(None, "unresolved")


def resolve_player_ids(
    rows: pd.DataFrame, players: pd.DataFrame | None
) -> tuple[pd.DataFrame, list[int]]:
    """Map the ESPN ``espn_id`` key to an NHL ``player_id`` on every skater row.

    The frame keeps ``espn_id`` for provenance; ``player_id`` becomes the NHL id
    when a skater resolves and otherwise falls back to the ESPN id (so the row
    stays uniquely keyed and is never dropped). Returns the frame plus the list
    of ESPN ids that could not be resolved (surfaced, never guessed). When no
    ``players`` dimension is supplied the ESPN ids are retained unchanged.
    """
    if rows.empty or players is None or players.empty:
        return rows, []
    skaters = players[players["position"].isin(("F", "D"))]
    index = build_player_index(skaters)
    has_team = "current_team_abbrev" in players.columns
    team_by_id: dict[int, Any] = (
        {
            int(rec["player_id"]): rec["current_team_abbrev"]
            for rec in players.to_dict("records")
        }
        if has_team
        else {}
    )
    df = rows.copy()
    resolved_ids: list[int] = []
    unresolved: list[int] = []
    for rec in df.to_dict("records"):
        result = resolve_espn_player_id(
            _as_str(rec["player_name"]),
            _as_str(rec["team_abbrev"]),
            _as_str(rec["position"]),
            index,
            team_by_id,
        )
        if result.player_id is not None:
            resolved_ids.append(int(result.player_id))
        else:
            resolved_ids.append(int(rec["espn_id"]))
            if result.method == "unresolved":
                unresolved.append(int(rec["espn_id"]))
    df["player_id"] = resolved_ids
    return df, unresolved


def injuries_response_to_rows(
    response: EspnInjuriesResponse,
    *,
    players: pd.DataFrame | None = None,
    as_of: str | None = None,
) -> pd.DataFrame:
    """Flatten the ESPN injuries feed into normalized per-player rows.

    Team ids come from :func:`resolve_team_id` on the group's display name (the
    stable NHL id, not ESPN's), position from the athlete block. The ESPN athlete
    id is preserved in ``espn_id``; when a ``players`` dimension is supplied the
    row's ``player_id`` is resolved to the NHL id via name + team matching so the
    injured flag and IR-stash valuation join against real player ids (M-11).
    Entries without an athlete id are skipped — every row must key on a player.
    """
    rows: list[dict[str, Any]] = []
    for group in response.injuries:
        team_id = resolve_team_id(group.display_name) if group.display_name else None
        team_abbrev = group.abbreviation
        for entry in group.injuries:
            athlete = entry.athlete
            if athlete is None or athlete.id is None:
                continue
            player_name = athlete.full_name or athlete.display_name
            position = athlete.position.abbreviation if athlete.position else None
            type_name = entry.type.name if entry.type else None
            return_date = entry.details.return_date if entry.details else None
            detail = entry.details.type if entry.details else None
            espn_id = int(athlete.id)
            rows.append(
                {
                    "player_id": espn_id,
                    "espn_id": espn_id,
                    "player_name": player_name,
                    "position": position,
                    "team_id": team_id,
                    "team_abbrev": team_abbrev,
                    "status": normalize_status(entry.status, type_name),
                    "status_raw": entry.status,
                    "return_date": return_date,
                    "detail": detail,
                    "as_of_date": entry.date or as_of,
                    "source": SOURCE_ESPN,
                }
            )
    df = pd.DataFrame.from_records(rows, columns=list(_INJURY_COLUMNS))
    if df.empty:
        return df
    df, unresolved = resolve_player_ids(df, players)
    df = df.drop_duplicates(subset=["player_id"], keep="last").reset_index(drop=True)
    df.attrs["unresolved_espn_ids"] = unresolved
    return df


# ── Manual overrides (final authority) ───────────────────────────────────


@dataclass(frozen=True)
class InjuryOverride:
    """One manual injury override entry from ``injuries.yaml``."""

    player: str | None = None
    player_id: int | None = None
    espn_id: int | None = None
    status: str | None = None
    return_date: str | None = None
    detail: str | None = None
    team: str | None = None
    remove: bool = False
    # Round game (1-based) a player is expected back; consumed by the return-time
    # model (US-015) where it pins availability and overrides the model curve.
    return_game: int | None = None


def load_injury_overrides(
    path: Path = DEFAULT_INJURIES_OVERRIDES,
) -> list[InjuryOverride]:
    """Load ``injuries.yaml`` into a list of :class:`InjuryOverride`.

    A missing file is not an error — the overrides layer is simply empty. The
    file's top-level ``overrides`` key holds a list of entries; each needs a
    ``player`` name and/or an id (``player_id`` = NHL id, the preferred key, or
    the legacy ``espn_id``) so it can be matched to a source row.
    """
    if not path.exists():
        return []
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("overrides") or []
    overrides: list[InjuryOverride] = []
    for item in entries:
        if not isinstance(item, Mapping):
            continue
        player_id = item.get("player_id")
        espn_id = item.get("espn_id")
        status = item.get("status")
        return_game = item.get("return_game")
        overrides.append(
            InjuryOverride(
                player=_as_str(item.get("player")),
                player_id=int(player_id) if player_id is not None else None,
                espn_id=int(espn_id) if espn_id is not None else None,
                status=normalize_status(str(status)) if status is not None else None,
                return_date=_as_str(item.get("return_date")),
                detail=_as_str(item.get("detail")),
                team=_as_str(item.get("team")),
                remove=bool(item.get("remove", False)),
                return_game=int(return_game) if return_game is not None else None,
            )
        )
    return overrides


def _as_str(value: Any) -> str | None:
    return None if value is None else str(value)


def apply_overrides(source: pd.DataFrame, overrides: Iterable[InjuryOverride]) -> pd.DataFrame:
    """Merge overrides over ``source`` — overrides are the final authority.

    Matching precedence per override: ``espn_id`` (exact) first, else normalized
    ``player`` name. A matched override rewrites the row's status / return date /
    detail and stamps ``source='override'``; ``remove: true`` deletes the matched
    row. An unmatched override is injected as a brand-new override row so the
    owner can assert an injury the feed omitted entirely.
    """
    df = source.copy()
    if df.empty:
        df = pd.DataFrame(columns=list(_INJURY_COLUMNS))
    name_keys = df["player_name"].map(normalize_name) if not df.empty else pd.Series(dtype=str)

    for override in overrides:
        mask = _match_mask(df, override, name_keys)
        matched = bool(mask.any())
        if override.remove:
            if matched:
                df = df.loc[~mask].reset_index(drop=True)
                name_keys = df["player_name"].map(normalize_name)
            continue
        if matched:
            _rewrite_matched(df, mask, override)
        else:
            df = _append_override_row(df, override)
            name_keys = df["player_name"].map(normalize_name)
    return _reorder(df)


def _match_mask(df: pd.DataFrame, override: InjuryOverride, name_keys: pd.Series) -> pd.Series:
    if df.empty:
        return pd.Series([], dtype=bool)
    # NHL player_id is the preferred key; the legacy espn_id matches the
    # provenance column; name is the last resort (accent/punctuation-insensitive).
    if override.player_id is not None:
        return df["player_id"] == override.player_id
    if override.espn_id is not None and "espn_id" in df.columns:
        return df["espn_id"] == override.espn_id
    if override.player:
        return name_keys == normalize_name(override.player)
    return pd.Series([False] * len(df), index=df.index)


def _rewrite_matched(df: pd.DataFrame, mask: pd.Series, override: InjuryOverride) -> None:
    if override.status is not None:
        df.loc[mask, "status"] = override.status
        df.loc[mask, "status_raw"] = override.status
    if override.return_date is not None:
        df.loc[mask, "return_date"] = override.return_date
    if override.detail is not None:
        df.loc[mask, "detail"] = override.detail
    df.loc[mask, "source"] = SOURCE_OVERRIDE


def _append_override_row(df: pd.DataFrame, override: InjuryOverride) -> pd.DataFrame:
    team_id = resolve_team_id(override.team) if override.team else None
    # Key on the NHL player_id when given; fall back to the ESPN id so a legacy
    # espn_id-only override still injects a uniquely keyed row.
    player_id = override.player_id if override.player_id is not None else override.espn_id
    row = {
        "player_id": player_id,
        "espn_id": override.espn_id,
        "player_name": override.player,
        "position": None,
        "team_id": team_id,
        "team_abbrev": None,
        "status": override.status or STATUS_OUT,
        "status_raw": override.status or STATUS_OUT,
        "return_date": override.return_date,
        "detail": override.detail,
        "as_of_date": None,
        "source": SOURCE_OVERRIDE,
    }
    return pd.concat([df, pd.DataFrame([row])], ignore_index=True)


def _reorder(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=list(_INJURY_COLUMNS))
    return df[list(_INJURY_COLUMNS)].reset_index(drop=True)


# ── ESPN injuries client ─────────────────────────────────────────────────


class EspnInjuriesClient:
    """Cached, polite client for ESPN's public NHL injury JSON (SPEC §5).

    Caching / retry / injectable ``httpx.Client`` mirror
    :class:`draft_oracle.ingest.nhl_api.NHLApiClient`; ESPN needs no API key and
    403s browser-like User-Agents, so the default httpx UA is used. Raw responses
    cache under ``data/raw/espn-injuries/`` (a cache hit skips the network).
    """

    def __init__(
        self,
        cache_dir: Path | str = DEFAULT_INJURIES_CACHE_DIR,
        *,
        base: str = ESPN_INJURIES_BASE,
        core_base: str = ESPN_CORE_BASE,
        delay: float = DEFAULT_INJURIES_DELAY,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retry_backoff: float = 1.0,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.base = base.rstrip("/")
        self.core_base = core_base.rstrip("/")
        self.delay = delay
        self.max_attempts = max_attempts
        self.retry_backoff = retry_backoff
        self._cache = ResponseCache(Path(cache_dir))
        self._sleep = sleep
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> EspnInjuriesClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def _get_json(self, base: str, path: str) -> dict[str, Any]:
        cache_key = ResponseCache.key_for(base, path, None)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            if self.delay > 0:
                self._sleep(self.delay)
            try:
                response = self._client.get(f"{base}{path}")
                response.raise_for_status()
                parsed: dict[str, Any] = response.json()
                self._cache.put(cache_key, parsed)
                return parsed
            except (httpx.HTTPError, ValueError) as error:
                last_error = error
                if attempt + 1 < self.max_attempts:
                    self._sleep(self.retry_backoff * (2**attempt))
        raise NHLApiError(
            f"ESPN injuries request failed after {self.max_attempts} attempts: {path}"
        ) from last_error

    def injuries(self) -> EspnInjuriesResponse:
        """Fetch and parse the league-wide injuries feed (current status only)."""
        return EspnInjuriesResponse.model_validate(self._get_json(self.base, "/injuries"))

    def core_athlete(self, athlete_id: int | str) -> dict[str, Any]:
        """Raw ESPN core athlete detail (position/name gap fill, as needed)."""
        return self._get_json(self.core_base, f"/athletes/{athlete_id}")


# ── Build the normalized injuries table ──────────────────────────────────


@dataclass
class InjuriesResult:
    """Outcome of :func:`build_injuries_table`."""

    out_dir: Path
    source_rows: int
    override_rows: int
    total_rows: int
    degraded: bool
    unresolved_player_ids: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def report_lines(self) -> list[str]:
        lines = [
            f"Injuries table -> {self.out_dir}",
            f"  source rows: {self.source_rows}",
            f"  override rows: {self.override_rows}",
            f"  total rows: {self.total_rows}",
        ]
        if self.unresolved_player_ids:
            lines.append(
                f"  unresolved ESPN athlete ids (kept, not id-joined): "
                f"{len(self.unresolved_player_ids)} -> {self.unresolved_player_ids}"
            )
        if self.degraded:
            lines.append("  DEGRADED: source unavailable; used last-known data")
        for warning in self.warnings:
            lines.append(f"  WARNING: {warning}")
        return lines


def _load_players(normalized_dir: Path) -> pd.DataFrame | None:
    """Load the normalized ``players`` dimension for ESPN->NHL id mapping, if present."""
    path = normalized_dir / "players.parquet"
    if not path.is_file():
        return None
    return pd.read_parquet(path)


def build_injuries_table(
    *,
    client: EspnInjuriesClient | None = None,
    overrides_path: Path = DEFAULT_INJURIES_OVERRIDES,
    out_dir: Path = DEFAULT_NORMALIZED_DIR,
    players: pd.DataFrame | None = None,
    fetch: bool = True,
) -> InjuriesResult:
    """Ingest injuries into ``injuries.parquet``; overrides are final authority.

    The ESPN feed keys on athlete ids that are disjoint from NHL player ids, so
    every source row is resolved to an NHL ``player_id`` via name + team matching
    against the ``players`` dimension (loaded from ``out_dir/players.parquet``
    when not supplied) — otherwise the ``injured`` flag and IR-stash valuation
    could never match a real player (CODE_REVIEW M-11). Unresolved skaters are
    kept (never dropped) and surfaced in the result.

    On a source failure (or ``fetch=False``) the last-known table is reused so
    the pipeline never stalls on a flaky feed — the overrides always merge on
    top. Returns row counts, a ``degraded`` flag, and any warnings.
    """
    warnings: list[str] = []
    degraded = False
    unresolved: list[int] = []
    out_path = out_dir / f"{INJURIES_TABLE_NAME}.parquet"

    if players is None:
        players = _load_players(out_dir)
    if players is None:
        warnings.append(
            "no players.parquet found; ESPN athlete ids left unmapped (injured flag "
            "will not join)"
        )

    source: pd.DataFrame | None = None
    owns_client = fetch and client is None
    active_client = client
    if fetch:
        if active_client is None:
            active_client = EspnInjuriesClient()
        try:
            source = injuries_response_to_rows(active_client.injuries(), players=players)
            unresolved = list(source.attrs.get("unresolved_espn_ids", []))
        except NHLApiError as error:
            warnings.append(f"ESPN injuries source failed ({error}); using last-known data")
            degraded = True
            source = None
        finally:
            if owns_client and active_client is not None:
                active_client.close()
    else:
        warnings.append("fetch disabled; using last-known injuries data + overrides")

    if source is None:
        source = _load_last_known(out_path)
        if source.empty and not warnings:
            warnings.append("no last-known injuries table found; starting empty")

    source_rows = len(source)
    overrides = load_injury_overrides(overrides_path)
    merged = apply_overrides(source, overrides)
    override_rows = int((merged["source"] == SOURCE_OVERRIDE).sum()) if not merged.empty else 0

    out_dir.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(out_path, index=False)
    return InjuriesResult(
        out_dir=out_dir,
        source_rows=source_rows,
        override_rows=override_rows,
        total_rows=len(merged),
        degraded=degraded,
        unresolved_player_ids=unresolved,
        warnings=warnings,
    )


def _load_last_known(out_path: Path) -> pd.DataFrame:
    """Load the previous ``injuries.parquet`` (relabeled last-known), or empty."""
    if not out_path.is_file():
        return pd.DataFrame(columns=list(_INJURY_COLUMNS))
    df = pd.read_parquet(out_path)
    for column in _INJURY_COLUMNS:
        if column not in df.columns:
            df[column] = None
    df = df[list(_INJURY_COLUMNS)].copy()
    # Rows previously stamped from the live source become "last-known"; committed
    # override rows keep their authority so they merge cleanly again.
    df.loc[df["source"] == SOURCE_ESPN, "source"] = SOURCE_LAST_KNOWN
    return df.reset_index(drop=True)

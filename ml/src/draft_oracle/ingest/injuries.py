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

from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field

from draft_oracle.ingest import _injuries_build as _injuries_build_module
from draft_oracle.ingest.entity_match import (
    DEFAULT_OVERRIDES_DIR,
    PlayerIndex,
    build_player_index,
    last_name_key,
    normalize_name,
)
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

_TYPE_STATUS_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("INJURED_RESERVE", "LTIR"), STATUS_IR),
    (("DAY_TO_DAY", "QUESTIONABLE", "GTD"), STATUS_DAY_TO_DAY),
    (("OUT", "SUSPEN"), STATUS_OUT),
    (("ACTIVE", "HEALTHY"), STATUS_HEALTHY),
)
_TEXT_STATUS_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...], str], ...] = (
    (("injured reserve", "long term"), ("ir", "ltir"), STATUS_IR),
    (("day to day", "questionable", "gtd"), (), STATUS_DAY_TO_DAY),
    (("out", "suspension", "suspended"), (), STATUS_OUT),
    (("active", "healthy", "probable"), (), STATUS_HEALTHY),
)

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
    normalized_type = _normalize_type_status(type_key)
    if normalized_type is not None:
        return normalized_type

    collapsed = _collapse_status_text(status_raw)
    if not collapsed:
        return STATUS_HEALTHY
    normalized_text = _normalize_text_status(collapsed)
    if normalized_text is not None:
        return normalized_text
    # Unknown but non-empty statuses are conservatively treated as day-to-day so
    # they surface for review rather than silently reading as healthy.
    return STATUS_DAY_TO_DAY


def _normalize_type_status(type_key: str) -> str | None:
    if not type_key:
        return None
    if type_key.endswith("_IR"):
        return STATUS_IR
    for markers, status in _TYPE_STATUS_RULES:
        if _contains_status_marker(type_key, markers):
            return status
    return None


def _collapse_status_text(status_raw: str | None) -> str:
    text = (status_raw or "").strip().lower()
    collapsed = text.replace("-", " ").replace("_", " ")
    return " ".join(collapsed.split())


def _normalize_text_status(collapsed: str) -> str | None:
    for contains_markers, exact_markers, status in _TEXT_STATUS_RULES:
        contains = _contains_status_marker(collapsed, contains_markers)
        exact = collapsed in exact_markers
        if contains or exact:
            return status
    return None


def _contains_status_marker(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker in value for marker in markers)


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


@dataclass(frozen=True)
class _PlayerResolutionContext:
    index: PlayerIndex
    fantasy_pos: str
    team_key: str | None
    team_by_id: Mapping[int, Any]


@dataclass(frozen=True)
class _PlayerResolverContext:
    index: PlayerIndex
    team_by_id: Mapping[int, Any]


@dataclass(frozen=True)
class EspnPlayerIdRequest:
    name: str | None
    team_abbrev: str | None
    position: str | None


def resolve_espn_player_id(
    request: EspnPlayerIdRequest,
    resolver: _PlayerResolverContext | PlayerIndex,
    *legacy_team_by_id: Mapping[int, Any],
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
    fantasy_pos = _fantasy_position(request.position)
    if fantasy_pos is None:
        return PlayerIdResolution(None, "goalie")
    resolver = _coerce_player_resolver(resolver, legacy_team_by_id)
    norm = normalize_name(request.name)
    context = _PlayerResolutionContext(
        index=resolver.index,
        fantasy_pos=fantasy_pos,
        team_key=_team_abbrev_key(request.team_abbrev),
        team_by_id=resolver.team_by_id,
    )

    exact = context.index.by_norm.get(norm, [])
    if exact:
        resolved = _disambiguate_player_id(exact, "exact", context)
        return resolved if resolved is not None else PlayerIdResolution(None, "unresolved")

    last = last_name_key(request.name)
    last_hits = context.index.by_last.get(last, []) if last else []
    if last_hits:
        resolved = _disambiguate_player_id(last_hits, "lastname", context)
        if resolved is not None:
            return resolved
    return PlayerIdResolution(None, "unresolved")


def _coerce_player_resolver(
    resolver: _PlayerResolverContext | PlayerIndex,
    legacy_team_by_id: tuple[Mapping[int, Any], ...],
) -> _PlayerResolverContext:
    if isinstance(resolver, _PlayerResolverContext):
        return resolver
    team_by_id = legacy_team_by_id[0] if legacy_team_by_id else {}
    return _PlayerResolverContext(index=resolver, team_by_id=team_by_id)


def _disambiguate_player_id(
    candidates: list[Any], method: str, context: _PlayerResolutionContext
) -> PlayerIdResolution | None:
    if len(candidates) == 1:
        return PlayerIdResolution(candidates[0].player_id, method)
    narrowed = _team_matches(candidates, context)
    if len(narrowed) == 1:
        return PlayerIdResolution(narrowed[0].player_id, "team")
    candidates = narrowed or candidates
    by_pos = [c for c in candidates if c.position == context.fantasy_pos]
    if len(by_pos) == 1:
        return PlayerIdResolution(by_pos[0].player_id, "position")
    return None


def _team_matches(candidates: list[Any], context: _PlayerResolutionContext) -> list[Any]:
    if context.team_key is None:
        return []
    return [
        c
        for c in candidates
        if _team_abbrev_key(context.team_by_id.get(c.player_id)) == context.team_key
    ]


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
    if rows.empty:
        return rows, []
    if players is None:
        return rows, []
    if players.empty:
        return rows, []
    skaters = players[players["position"].isin(("F", "D"))]
    index = build_player_index(skaters)
    resolver = _PlayerResolverContext(
        index=index,
        team_by_id=_current_team_by_player_id(players),
    )
    df = rows.copy()
    resolved_ids: list[int] = []
    unresolved: list[int] = []
    for rec in df.to_dict("records"):
        result = resolve_espn_player_id(
            EspnPlayerIdRequest(
                _as_str(rec["player_name"]),
                _as_str(rec["team_abbrev"]),
                _as_str(rec["position"]),
            ),
            resolver,
        )
        resolved_ids.append(_resolved_player_id(rec, result))
        if _is_unresolved_skater(result):
            unresolved.append(int(rec["espn_id"]))
    df["player_id"] = resolved_ids
    return df, unresolved


def _is_unresolved_skater(result: PlayerIdResolution) -> bool:
    return result.player_id is None and result.method == "unresolved"


def _current_team_by_player_id(players: pd.DataFrame) -> dict[int, Any]:
    if "current_team_abbrev" not in players.columns:
        return {}
    return {int(rec["player_id"]): rec["current_team_abbrev"] for rec in players.to_dict("records")}


def _resolved_player_id(rec: Mapping[Hashable, Any], result: PlayerIdResolution) -> int:
    if result.player_id is not None:
        return int(result.player_id)
    return int(rec["espn_id"])


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
    rows = [row for group in response.injuries for row in _team_injury_rows(group, as_of)]
    df = pd.DataFrame.from_records(rows, columns=list(_INJURY_COLUMNS))
    if df.empty:
        return df
    df, unresolved = resolve_player_ids(df, players)
    df = df.drop_duplicates(subset=["player_id"], keep="last").reset_index(drop=True)
    df.attrs["unresolved_espn_ids"] = unresolved
    return df


def _team_injury_rows(group: EspnTeamInjuries, as_of: str | None) -> list[dict[str, Any]]:
    team_id = resolve_team_id(group.display_name) if group.display_name else None
    return [
        row
        for entry in group.injuries
        if (row := _injury_entry_row(entry, team_id, group.abbreviation, as_of)) is not None
    ]


def _injury_entry_row(
    entry: EspnInjuryEntry,
    team_id: int | None,
    team_abbrev: str | None,
    as_of: str | None,
) -> dict[str, Any] | None:
    athlete = entry.athlete
    if athlete is None:
        return None
    if athlete.id is None:
        return None
    player_name = athlete.full_name or athlete.display_name
    position = athlete.position.abbreviation if athlete.position else None
    type_name = entry.type.name if entry.type else None
    return_date = entry.details.return_date if entry.details else None
    detail = entry.details.type if entry.details else None
    espn_id = int(athlete.id)
    return {
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
        override = _injury_override_from_item(item)
        if override is not None:
            overrides.append(override)
    return overrides


def _injury_override_from_item(item: object) -> InjuryOverride | None:
    if not isinstance(item, Mapping):
        return None
    player_id = item.get("player_id")
    espn_id = item.get("espn_id")
    status = item.get("status")
    return_game = item.get("return_game")
    return InjuryOverride(
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


def _as_str(value: Any) -> str | None:
    return None if value is None else str(value)


def apply_overrides(source: pd.DataFrame, overrides: Iterable[InjuryOverride]) -> pd.DataFrame:
    """Merge overrides over ``source`` — overrides are the final authority.

    Matching precedence per override: NHL ``player_id`` first, then legacy
    ``espn_id``, then normalized ``player`` name. A matched override rewrites the
    row's status / return date / detail and stamps ``source='override'``;
    ``remove: true`` deletes the matched row. An unmatched override is injected
    as a brand-new override row so the owner can assert an injury the feed
    omitted entirely.
    """
    df = source.copy()
    if df.empty:
        df = pd.DataFrame(columns=list(_INJURY_COLUMNS))
    name_keys = df["player_name"].map(normalize_name) if not df.empty else pd.Series(dtype=str)

    for override in overrides:
        df, name_keys = _apply_one_override(df, name_keys, override)
    return _reorder(df)


def _apply_one_override(
    df: pd.DataFrame, name_keys: pd.Series, override: InjuryOverride
) -> tuple[pd.DataFrame, pd.Series]:
    mask = _match_mask(df, override, name_keys)
    matched = bool(mask.any())
    if override.remove:
        return _remove_override_match(df, mask) if matched else (df, name_keys)
    if matched:
        _rewrite_matched(df, mask, override)
        return df, name_keys
    df = _append_override_row(df, override)
    return df, df["player_name"].map(normalize_name)


def _remove_override_match(df: pd.DataFrame, mask: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    df = df.loc[~mask].reset_index(drop=True)
    return df, df["player_name"].map(normalize_name)


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


# ── ESPN injuries client + table builder ─────────────────────────────────

EspnInjuriesClient = _injuries_build_module.EspnInjuriesClient
EspnInjuriesClientConfig = _injuries_build_module.EspnInjuriesClientConfig
EspnInjuriesClientRuntime = _injuries_build_module.EspnInjuriesClientRuntime
InjuryBuildOptions = _injuries_build_module.InjuryBuildOptions
InjuriesResult = _injuries_build_module.InjuriesResult
_load_players = _injuries_build_module._load_players
_load_last_known = _injuries_build_module._load_last_known


def build_injuries_table(
    options: InjuryBuildOptions | None = None,
    *,
    client: EspnInjuriesClient | None = None,
    **legacy: object,
) -> InjuriesResult:
    """Ingest injuries into ``injuries.parquet``; overrides are final authority."""
    return _injuries_build_module.build_injuries_table(
        options=options,
        client=client,
        **legacy,
    )

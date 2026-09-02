"""ESPN injuries client and table build helpers."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pandas as pd

from draft_oracle.ingest.entity_match import DEFAULT_OVERRIDES_DIR
from draft_oracle.ingest.nhl_api import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_TIMEOUT,
    NHLApiError,
    ResponseCache,
)
from draft_oracle.ingest.normalize import DEFAULT_NORMALIZED_DIR

if TYPE_CHECKING:
    from draft_oracle.ingest.injuries import EspnInjuriesResponse

ESPN_INJURIES_BASE = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl"
ESPN_CORE_BASE = "https://sports.core.api.espn.com/v2/sports/hockey/leagues/nhl"
DEFAULT_INJURIES_CACHE_DIR = Path("data/raw/espn-injuries")
DEFAULT_INJURIES_DELAY = 1.0
INJURIES_TABLE_NAME = "injuries"
DEFAULT_INJURIES_OVERRIDES = DEFAULT_OVERRIDES_DIR / "injuries.yaml"
SOURCE_ESPN = "espn"
SOURCE_OVERRIDE = "override"
SOURCE_LAST_KNOWN = "last_known"

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
        from draft_oracle.ingest.injuries import EspnInjuriesResponse

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
            from draft_oracle.ingest.injuries import injuries_response_to_rows

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
    from draft_oracle.ingest.injuries import apply_overrides, load_injury_overrides

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
    from draft_oracle.ingest.injuries import _INJURY_COLUMNS

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

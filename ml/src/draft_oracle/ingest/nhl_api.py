"""Typed NHL API client with disk caching and polite fetching (US-003).

All NHL endpoint knowledge lives in this module — no raw URLs appear anywhere
else in ``draft_oracle``. Downstream ingestion (US-004+) calls the typed adapter
methods on :class:`NHLApiClient`, which return pydantic-validated responses.

Two NHL hosts are used (SPEC §5):

* ``https://api-web.nhle.com`` — per-player/team/game "web" endpoints.
* ``https://api.nhle.com/stats/rest/en`` — the bulk stats-rest reports.

Every raw JSON response is cached under ``data/raw/nhl-api/`` keyed by
endpoint + params; a cache hit skips the network entirely, so ingestion is
repeatable and tests never touch the wire (fixtures only — SPEC §7).
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

# ── Hosts (the only place NHL URLs are allowed) ──────────────────────────

WEB_BASE = "https://api-web.nhle.com/v1"
STATS_BASE = "https://api.nhle.com/stats/rest/en"

DEFAULT_CACHE_DIR = Path("data/raw/nhl-api")
DEFAULT_DELAY = 1.0
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_RETRY_BACKOFF = 1.0
DEFAULT_TIMEOUT = 30.0
SKATER_SUMMARY_ROW_CAP = 10_000

GameType = int  # 2 = regular season, 3 = playoffs
SeasonId = int  # e.g. 20252026

RawJson = dict[str, Any]
ParamValue = str | int
Params = Mapping[str, ParamValue]


class NHLApiError(RuntimeError):
    """Raised when an NHL request fails after exhausting all retries.

    Ingestion degrades loudly rather than silently (SPEC §7).
    """


# ── Shared value objects ─────────────────────────────────────────────────


class LocalizedName(BaseModel):
    """NHL localized string blob (``{"default": ..., "fr": ...}``)."""

    model_config = ConfigDict(extra="ignore")

    default: str
    fr: str | None = None


class _Model(BaseModel):
    """Base for API models: ignore unknown fields, accept aliases + field names."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


# ── Player game log: /v1/player/{id}/game-log/{season}/{gameType} ─────────


class GameLogEntry(_Model):
    game_id: int = Field(alias="gameId")
    game_date: str = Field(alias="gameDate")
    game_type_id: int | None = Field(default=None, alias="gameTypeId")
    team_abbrev: str | None = Field(default=None, alias="teamAbbrev")
    opponent_abbrev: str | None = Field(default=None, alias="opponentAbbrev")
    home_road_flag: str | None = Field(default=None, alias="homeRoadFlag")
    goals: int = 0
    assists: int = 0
    points: int = 0
    shots: int | None = None
    plus_minus: int | None = Field(default=None, alias="plusMinus")
    toi: str | None = None


class PlayerGameLog(_Model):
    season_id: int | None = Field(default=None, alias="seasonId")
    game_type_id: int | None = Field(default=None, alias="gameTypeId")
    game_log: list[GameLogEntry] = Field(default_factory=list, alias="gameLog")


# ── Team schedule/results: /v1/club-schedule-season/{abbrev}/{season} ─────


class GameTeam(_Model):
    id: int
    abbrev: str | None = None
    score: int | None = None


class GameOutcome(_Model):
    last_period_type: str | None = Field(default=None, alias="lastPeriodType")


class ScheduleGame(_Model):
    id: int
    season: int | None = None
    game_type: int | None = Field(default=None, alias="gameType")
    game_date: str | None = Field(default=None, alias="gameDate")
    game_state: str | None = Field(default=None, alias="gameState")
    away_team: GameTeam = Field(alias="awayTeam")
    home_team: GameTeam = Field(alias="homeTeam")
    game_outcome: GameOutcome | None = Field(default=None, alias="gameOutcome")


class ClubScheduleSeason(_Model):
    current_season: int | None = Field(default=None, alias="currentSeason")
    previous_season: int | None = Field(default=None, alias="previousSeason")
    games: list[ScheduleGame] = Field(default_factory=list)


# ── Scores by date: /v1/score/{YYYY-MM-DD} ───────────────────────────────


class DailyScores(_Model):
    current_date: str | None = Field(default=None, alias="currentDate")
    games: list[ScheduleGame] = Field(default_factory=list)


# ── Playoff bracket: /v1/playoff-bracket/{year} ──────────────────────────


class SeedTeam(_Model):
    id: int
    abbrev: str | None = None
    name: LocalizedName | None = None


class PlayoffSeries(_Model):
    series_letter: str | None = Field(default=None, alias="seriesLetter")
    series_abbrev: str | None = Field(default=None, alias="seriesAbbrev")
    playoff_round: int | None = Field(default=None, alias="playoffRound")
    top_seed_wins: int = Field(default=0, alias="topSeedWins")
    bottom_seed_wins: int = Field(default=0, alias="bottomSeedWins")
    winning_team_id: int | None = Field(default=None, alias="winningTeamId")
    losing_team_id: int | None = Field(default=None, alias="losingTeamId")
    top_seed_team: SeedTeam | None = Field(default=None, alias="topSeedTeam")
    bottom_seed_team: SeedTeam | None = Field(default=None, alias="bottomSeedTeam")


class PlayoffBracket(_Model):
    series: list[PlayoffSeries] = Field(default_factory=list)


# ── Team roster: /v1/roster/{abbrev}/{season} ────────────────────────────


class RosterPlayer(_Model):
    id: int
    first_name: LocalizedName | None = Field(default=None, alias="firstName")
    last_name: LocalizedName | None = Field(default=None, alias="lastName")
    position_code: str | None = Field(default=None, alias="positionCode")
    sweater_number: int | None = Field(default=None, alias="sweaterNumber")


class TeamRoster(_Model):
    forwards: list[RosterPlayer] = Field(default_factory=list)
    defensemen: list[RosterPlayer] = Field(default_factory=list)
    goalies: list[RosterPlayer] = Field(default_factory=list)


# ── Player info: /v1/player/{id}/landing (position, status) ───────────────


class PlayerLanding(_Model):
    player_id: int = Field(alias="playerId")
    position: str | None = Field(default=None, alias="position")
    is_active: bool | None = Field(default=None, alias="isActive")
    first_name: LocalizedName | None = Field(default=None, alias="firstName")
    last_name: LocalizedName | None = Field(default=None, alias="lastName")
    current_team_abbrev: str | None = Field(default=None, alias="currentTeamAbbrev")
    sweater_number: int | None = Field(default=None, alias="sweaterNumber")


# ── Bulk skater summary: stats-rest /skater/summary ──────────────────────


class SkaterSummaryRow(_Model):
    player_id: int = Field(alias="playerId")
    skater_full_name: str | None = Field(default=None, alias="skaterFullName")
    position_code: str | None = Field(default=None, alias="positionCode")
    team_abbrev: str | None = Field(default=None, alias="teamAbbrev")
    game_id: int | None = Field(default=None, alias="gameId")
    game_date: str | None = Field(default=None, alias="gameDate")
    goals: int | None = None
    assists: int | None = None
    points: int | None = None
    shots: int | None = None


class SkaterSummaryResponse(_Model):
    data: list[SkaterSummaryRow] = Field(default_factory=list)
    total: int | None = None


# ── Response cache ───────────────────────────────────────────────────────


class ResponseCache:
    """On-disk JSON cache keyed by endpoint + params (SPEC §5).

    A stored file means the network is never touched again for that request.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    @staticmethod
    def key_for(base: str, path: str, params: Params | None) -> str:
        payload = json.dumps(
            {"base": base, "path": path, "params": _sorted_params(params)},
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
        slug = path.strip("/").replace("/", "_") or "root"
        return f"{slug}__{digest}.json"

    def path_for(self, key: str) -> Path:
        return self.root / key

    def get(self, key: str) -> RawJson | None:
        path = self.path_for(key)
        if not path.is_file():
            return None
        with path.open("r", encoding="utf-8") as handle:
            data: RawJson = json.load(handle)
        return data

    def put(self, key: str, data: RawJson) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path_for(key)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)


def _sorted_params(params: Params | None) -> dict[str, ParamValue]:
    if not params:
        return {}
    return {key: params[key] for key in sorted(params)}


# ── Client ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NHLApiClientConfig:
    web_base: str = WEB_BASE
    stats_base: str = STATS_BASE
    delay: float = DEFAULT_DELAY
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    retry_backoff: float = DEFAULT_RETRY_BACKOFF
    timeout: float = DEFAULT_TIMEOUT


@dataclass(frozen=True)
class NHLApiClientRuntime:
    client: httpx.Client | None = None
    sleep: Callable[[float], None] = time.sleep


class NHLApiClient:
    """Polite, cached, typed NHL API client.

    Parameters
    ----------
    cache_dir:
        Directory for raw JSON responses. Defaults to ``data/raw/nhl-api``.
    delay:
        Seconds to wait before each network request (politeness). Set to ``0``
        in tests. Cache hits never sleep.
    max_attempts:
        Total attempts per request before raising :class:`NHLApiError`.
    retry_backoff:
        Base seconds for exponential backoff (``retry_backoff * 2**attempt``).
    client:
        Optional pre-built ``httpx.Client`` (inject an ``httpx.MockTransport``
        in tests). When omitted the client owns and closes its own instance.
    sleep:
        Injectable sleep function (defaults to :func:`time.sleep`); tests pass a
        no-op so backoff never blocks.
    """

    def __init__(
        self,
        cache_dir: Path | str = DEFAULT_CACHE_DIR,
        *,
        config: NHLApiClientConfig | None = None,
        runtime: NHLApiClientRuntime | None = None,
    ) -> None:
        config = config or NHLApiClientConfig()
        runtime = runtime or NHLApiClientRuntime()
        if config.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.web_base = config.web_base.rstrip("/")
        self.stats_base = config.stats_base.rstrip("/")
        self.delay = config.delay
        self.max_attempts = config.max_attempts
        self.retry_backoff = config.retry_backoff
        self._cache = ResponseCache(Path(cache_dir))
        self._sleep = runtime.sleep
        self._owns_client = runtime.client is None
        self._client = (
            runtime.client if runtime.client is not None else httpx.Client(timeout=config.timeout)
        )

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> NHLApiClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # -- transport ---------------------------------------------------------

    def _get_json(self, base: str, path: str, params: Params | None = None) -> RawJson:
        key = ResponseCache.key_for(base, path, params)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        data = self._request_with_retry(f"{base}{path}", params)
        self._cache.put(key, data)
        return data

    def _request_with_retry(self, url: str, params: Params | None) -> RawJson:
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            parsed, last_error = self._request_attempt(url, params, attempt, last_error)
            if parsed is not None:
                return parsed
        raise NHLApiError(
            f"NHL request failed after {self.max_attempts} attempts: {url} {dict(params or {})}"
        ) from last_error

    def _request_attempt(
        self,
        url: str,
        params: Params | None,
        attempt: int,
        last_error: Exception | None,
    ) -> tuple[RawJson | None, Exception | None]:
        if self.delay > 0:
            self._sleep(self.delay)
        try:
            response = self._client.get(url, params=dict(params or {}))
            response.raise_for_status()
            parsed: RawJson = response.json()
            return parsed, last_error
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as error:
            if attempt + 1 < self.max_attempts:
                self._sleep(self.retry_backoff * (2**attempt))
            return None, error

    # -- typed adapters (the only NHL endpoint knowledge in the codebase) --

    def player_game_log(
        self, player_id: int, season: SeasonId, game_type: GameType
    ) -> PlayerGameLog:
        """Per-game log for one player in one season and game type."""
        data = self._get_json(self.web_base, f"/player/{player_id}/game-log/{season}/{game_type}")
        return PlayerGameLog.model_validate(data)

    def player_info(self, player_id: int) -> PlayerLanding:
        """Player landing info (position, active status, current team)."""
        data = self._get_json(self.web_base, f"/player/{player_id}/landing")
        return PlayerLanding.model_validate(data)

    def team_roster(self, team_abbrev: str, season: SeasonId) -> TeamRoster:
        """Full team roster (forwards / defensemen / goalies) for a season."""
        data = self._get_json(self.web_base, f"/roster/{team_abbrev}/{season}")
        return TeamRoster.model_validate(data)

    def club_schedule_season(self, team_abbrev: str, season: SeasonId) -> ClubScheduleSeason:
        """Full-season schedule and results (with scores) for one team."""
        data = self._get_json(self.web_base, f"/club-schedule-season/{team_abbrev}/{season}")
        return ClubScheduleSeason.model_validate(data)

    def scores_by_date(self, date: str) -> DailyScores:
        """All games and scores for a single ``YYYY-MM-DD`` date."""
        data = self._get_json(self.web_base, f"/score/{date}")
        return DailyScores.model_validate(data)

    def playoff_bracket(self, year: int) -> PlayoffBracket:
        """Playoff bracket / series metadata for a playoff ``year``."""
        data = self._get_json(self.web_base, f"/playoff-bracket/{year}")
        return PlayoffBracket.model_validate(data)

    def skater_summary(
        self, season: SeasonId, game_type: GameType, *, per_game: bool = True
    ) -> SkaterSummaryResponse:
        """Bulk skater summary report from stats-rest (preferred for bulk pulls).

        ``per_game=True`` requests per-game rows (``isGame=true``); the NHL API
        hard-caps a single query at 10k rows, so partition by date upstream for
        full seasons (see ``data/raw/nhl-archive/PROVENANCE.md``).
        """
        cayenne = f"seasonId={season} and gameTypeId={game_type}"
        params: dict[str, ParamValue] = {
            "isGame": "true" if per_game else "false",
            "limit": -1,
            "start": 0,
            "cayenneExp": cayenne,
        }
        data = self._get_json(self.stats_base, "/skater/summary", params)
        response = SkaterSummaryResponse.model_validate(data)
        if _skater_summary_hits_cap(response):
            raise NHLApiError(
                "NHL skater summary reached the 10,000-row response cap; "
                "partition the request by date to avoid silent truncation"
            )
        return response


def _skater_summary_hits_cap(response: SkaterSummaryResponse) -> bool:
    declared_total_hits_cap = (
        response.total is not None and response.total >= SKATER_SUMMARY_ROW_CAP
    )
    returned_rows_hit_cap = len(response.data) >= SKATER_SUMMARY_ROW_CAP
    return declared_total_hits_cap or returned_rows_hit_cap

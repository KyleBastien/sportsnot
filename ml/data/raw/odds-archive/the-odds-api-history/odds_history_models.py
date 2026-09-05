"""Data models and fixed request/table schema for NHL odds history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from odds_archive_common import isoformat

API_HOST = "api.the-odds-api.com"
API_ROOT = "/v4"
MIN_REMAINING = 5_000
SEASONS = tuple(f"{year}-{str(year + 1)[-2:]}" for year in range(2019, 2026))
HISTORY_FLOOR = datetime(2020, 6, 6, tzinfo=UTC)
PLAYOFF_MARKETS = ("h2h", "spreads", "totals")
REGULAR_MARKETS = ("h2h",)
REGIONS = ("us", "eu")
MAX_START_DELTA = timedelta(hours=2)

INDEX_COLUMNS = (
    "gameId",
    "gameTypeId",
    "gameDate",
    "archiveStartTimeUTC",
    "requestedTimestamp",
    "returnedSnapshotTimestamp",
    "rawFile",
    "eventId",
    "commenceTime",
    "startTimeDeltaSeconds",
    "apiHomeName",
    "apiAwayName",
    "archiveHomeName",
    "archiveAwayName",
    "archiveHomeAbbrev",
    "archiveAwayAbbrev",
    "bookmakerCount",
    "hasH2h",
    "hasSpreads",
    "hasTotals",
    "matchStatus",
)

LINES_COLUMNS = (
    "gameId",
    "gameTypeId",
    "gameDate",
    "requestedTimestamp",
    "returnedSnapshotTimestamp",
    "eventId",
    "commenceTime",
    "archiveHomeAbbrev",
    "archiveAwayAbbrev",
    "bookmakerKey",
    "bookmakerTitle",
    "bookmakerLastUpdate",
    "marketKey",
    "marketLastUpdate",
    "outcomeName",
    "price",
    "point",
)


@dataclass(frozen=True)
class Game:
    season: str
    game_id: str
    game_type_id: str
    game_date: str
    start: datetime
    home_abbrev: str
    away_abbrev: str
    home_name: str
    away_name: str


@dataclass(frozen=True)
class RequestPlan:
    season: str
    game_type_id: str
    requested: datetime
    markets: tuple[str, ...]
    games: tuple[Game, ...]

    @property
    def estimated_cost(self) -> int:
        return 10 * len(self.markets) * len(REGIONS)

    @property
    def requested_iso(self) -> str:
        return isoformat(self.requested)

    @property
    def raw_relative_path(self) -> Path:
        filename = self.requested_iso.replace(":", "-") + ".json.gz"
        return Path("raw") / self.game_type_id / filename


@dataclass(frozen=True)
class ApiRequest:
    label: str
    path: str
    params: dict[str, str]
    output_name: str
    estimated_cost: int
    allowed_statuses: frozenset[int] = frozenset({200})


@dataclass(frozen=True)
class ClientSettings:
    api_key: str
    scratch: Path
    max_credits: int
    request_log: Path | None = None
    progress_every: int = 1
    delay: float = 0.0

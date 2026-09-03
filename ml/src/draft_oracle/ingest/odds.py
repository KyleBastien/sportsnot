"""Betting-odds ingestion and de-vigging (US-005).

Turns raw moneyline prices - from the committed historical archives and, for
future games only, from live public endpoints - into de-vigged implied
win probabilities stored in a normalized odds table keyed to games.

Sources (see ``data/raw/odds-archive/PROVENANCE.md`` - read it before touching
the parsers; it documents every trap handled here):

* **SBR workbooks** (``nhl-odds-*.xlsx``, 2016-17 - 2021-22 complete, 2022-23
  partial) - both-side Open/Close American moneylines. Preferred where present:
  a two-sided price de-vigs exactly with the proportional method.
* **Kaggle/ESPN** (``kaggle-nhl-historical/nhl_data_extensive.csv.gz``, 2004 -
  Dec 2025) - favorite-side moneyline only. Its two team rows repeat one
  game-level spread, so the favorite cannot be attributed reliably; rows remain
  uncovered rather than guessed.
* **ESPN 2025-26 completion** (``espn-2025-26-completion/games.csv``, Dec 2025 -
  Jun 2026 incl. the 2026 playoffs) - favorite-side moneyline only, attributed
  from each game's cached raw-summary favorite flag.

Favorite-only prices cannot be de-vigged exactly (no underdog price). We NEVER
fabricate an underdog American price; instead we remove a documented standard
two-way overround (``STANDARD_OVERROUND``) from the favorite's raw implied
probability and take the complement for the underdog (SPEC §5).

Archive dates are normalized to the NHL archive's local date, and playoff labels
come from its authoritative ``gameTypeId`` join. Per-season placeholder-price
guards and cross-source home-probability validation blank suspect rows. Games
without trustworthy, joinable coverage are flagged, never imputed.

Live/future odds:

* :class:`OddsApiClient` - The Odds API free tier (``icehockey_nhl``), current
  and upcoming games only; key from ``ODDS_API_KEY``. Game moneylines (``h2h``)
  and, where offered, series/outright markets.
* :class:`EspnGameOddsClient` - ESPN's public ``summary`` endpoint
  (``pickcenter`` block) for individual future games, favorite-only.

Both live clients cache and rate-limit exactly like
:class:`~draft_oracle.ingest.nhl_api.NHLApiClient`, read keys from the
environment, and never touch the wire in tests (fixtures only - SPEC §7).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from importlib import import_module
from pathlib import Path
from typing import Any, SupportsFloat, SupportsIndex, cast

import pandas as pd

from draft_oracle.ingest import _odds_consolidate as _odds_consolidate_module
from draft_oracle.ingest import _odds_live as _odds_live_module

# ── Directory contract (SPEC §4) ─────────────────────────────────────────

DEFAULT_ODDS_ARCHIVE_DIR = Path("data/raw/odds-archive")
DEFAULT_NHL_ARCHIVE_DIR = Path("data/raw/nhl-archive")
DEFAULT_NORMALIZED_DIR = Path("data/normalized")
DEFAULT_ODDS_CACHE_DIR = _odds_live_module.DEFAULT_ODDS_CACHE_DIR
DEFAULT_ESPN_CACHE_DIR = _odds_live_module.DEFAULT_ESPN_CACHE_DIR
ODDS_TABLE_NAME = "odds"
ODDS_BY_SOURCE_TABLE_NAME = "odds_by_source"

# ── De-vig configuration ─────────────────────────────────────────────────

# Assumed two-way overround (a.k.a. "juice"/hold) used to de-vig a favorite-only
# price when the underdog price is unavailable. NHL moneyline markets typically
# hold 3.5-5%; 4.5% is a conservative, documented standard. Only the resulting
# PROBABILITIES are produced - an underdog American price is never fabricated.
STANDARD_OVERROUND = 1.045

# De-vig method labels stored on each row.
DEVIG_PROPORTIONAL = "proportional"
DEVIG_STANDARD_OVERROUND = "standard_overround"

# ── Placeholder / cross-source guards (CODE_REVIEW C-2) ──────────────────

# The Kaggle ``nhl_data_extensive`` archive backfills seasons it has no win
# price for with a constant puck-line juice value (-105), then labels every one
# of those rows as a real favourite moneyline. A season whose favourite-price
# column is *near-constant* is therefore a fabricated placeholder, not genuine
# coverage. We reject such rows (flag ``covered=False``) instead of ingesting
# them. Two independent detectors, documented here:
#
#   * a season is WHOLLY placeholder-filled when its priced rows collapse to
#     <=2 distinct values or an (almost) zero standard deviation, and
#   * a season is placeholder-DOMINATED (real prices mixed with a big constant
#     block) when a single modal price covers >= ``PLACEHOLDER_MODAL_FRACTION``
#     of its priced rows.
#
# Measured against the committed file these thresholds reject 100% of 2004-2018
# and 2025, 98.7% of 2019, and the pre-Dec-11 2026 rows, while leaving the real
# 2020-2024 markets (top modal price <= 18%) untouched.
PLACEHOLDER_STD_EPSILON = 1.0
PLACEHOLDER_MODAL_FRACTION = 0.50
# A season needs at least this many priced rows before its price column can be
# judged near-constant; a handful of games is too small a sample to call a
# placeholder (and would false-positive on legitimate single-price fixtures).
PLACEHOLDER_MIN_SEASON_ROWS = 10

# ``xval_delta`` (max-min de-vigged HOME probability across the sources covering
# a game) is a *consumed* cross-source sanity gate. Comparing one consistent side
# is required: favorite-probability magnitudes can look equal when two sources
# name opposite favorites. When sources disagree by more than this many points,
# the consolidated price is flagged uncovered rather than silently published.
XVAL_DELTA_THRESHOLD = 0.15

# Consolidation priority (higher wins) when several sources cover a game.
_SOURCE_PRIORITY: dict[str, int] = {
    "sbr_close": 30,
    "espn_completion": 20,
    "kaggle_espn": 10,
}

# Source labels.
SOURCE_SBR = "sbr_close"
SOURCE_KAGGLE = "kaggle_espn"
SOURCE_ESPN_COMPLETION = "espn_completion"
SOURCE_ODDS_API = "odds_api"
SOURCE_ESPN_SUMMARY = "espn_summary"


# ── NHL team reference (id ↔ abbrev ↔ full name) ─────────────────────────


@dataclass(frozen=True)
class TeamRef:
    """A single NHL franchise identity."""

    team_id: int
    abbrev: str
    full_name: str


# Derived from the committed NHL archive (``team-games-*`` latest full name per
# id). Utah appears under two ids across relocation/rebrand seasons: 59 (Utah
# Hockey Club, 2024-25) and 68 (Utah Mammoth, 2025-26); both are carried so a
# source name resolves to the id used in that season's ``team_games`` rows.
NHL_TEAMS: tuple[TeamRef, ...] = (
    TeamRef(1, "NJD", "New Jersey Devils"),
    TeamRef(2, "NYI", "New York Islanders"),
    TeamRef(3, "NYR", "New York Rangers"),
    TeamRef(4, "PHI", "Philadelphia Flyers"),
    TeamRef(5, "PIT", "Pittsburgh Penguins"),
    TeamRef(6, "BOS", "Boston Bruins"),
    TeamRef(7, "BUF", "Buffalo Sabres"),
    TeamRef(8, "MTL", "Montreal Canadiens"),
    TeamRef(9, "OTT", "Ottawa Senators"),
    TeamRef(10, "TOR", "Toronto Maple Leafs"),
    TeamRef(12, "CAR", "Carolina Hurricanes"),
    TeamRef(13, "FLA", "Florida Panthers"),
    TeamRef(14, "TBL", "Tampa Bay Lightning"),
    TeamRef(15, "WSH", "Washington Capitals"),
    TeamRef(16, "CHI", "Chicago Blackhawks"),
    TeamRef(17, "DET", "Detroit Red Wings"),
    TeamRef(18, "NSH", "Nashville Predators"),
    TeamRef(19, "STL", "St. Louis Blues"),
    TeamRef(20, "CGY", "Calgary Flames"),
    TeamRef(21, "COL", "Colorado Avalanche"),
    TeamRef(22, "EDM", "Edmonton Oilers"),
    TeamRef(23, "VAN", "Vancouver Canucks"),
    TeamRef(24, "ANA", "Anaheim Ducks"),
    TeamRef(25, "DAL", "Dallas Stars"),
    TeamRef(26, "LAK", "Los Angeles Kings"),
    TeamRef(28, "SJS", "San Jose Sharks"),
    TeamRef(29, "CBJ", "Columbus Blue Jackets"),
    TeamRef(30, "MIN", "Minnesota Wild"),
    TeamRef(52, "WPG", "Winnipeg Jets"),
    TeamRef(53, "ARI", "Arizona Coyotes"),
    TeamRef(54, "VGK", "Vegas Golden Knights"),
    TeamRef(55, "SEA", "Seattle Kraken"),
    TeamRef(59, "UTA", "Utah Hockey Club"),
    TeamRef(68, "UTA", "Utah Mammoth"),
)


def _norm_key(name: str) -> str:
    """Lowercase, strip accents/whitespace/punctuation for fuzzy name matching."""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_name = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_name.lower())


def _build_name_index() -> dict[str, int]:
    """Map every recognized team spelling to its NHL ``team_id``."""
    index: dict[str, int] = {}
    for team in NHL_TEAMS:
        # Full name ("Boston Bruins") and city part ("Boston") both resolve.
        full = _norm_key(team.full_name)
        city = _norm_key(team.full_name.rsplit(" ", 1)[0])
        index.setdefault(full, team.team_id)
        index.setdefault(city, team.team_id)
        index.setdefault(_norm_key(team.abbrev), team.team_id)
    # Explicit aliases: SBR city strings, spaced variants, and the documented
    # typos (PROVENANCE §3.4). The rsplit-derived "city" above mishandles
    # two-word nicknames (Maple Leafs, Red Wings, Blue Jackets, Golden Knights),
    # so every franchise's city string is listed explicitly here.
    aliases: dict[str, int] = {
        "anaheim": 24,
        "boston": 6,
        "buffalo": 7,
        "calgary": 20,
        "carolina": 12,
        "chicago": 16,
        "colorado": 21,
        "columbus": 29,
        "dallas": 25,
        "detroit": 17,
        "edmonton": 22,
        "florida": 13,
        "losangeles": 26,
        "minnesota": 30,
        "montreal": 8,
        "montrealcanadiens": 8,
        "nashville": 18,
        "newjersey": 1,
        "nyislanders": 2,
        "nyrangers": 3,
        "ottawa": 9,
        "philadelphia": 4,
        "pittsburgh": 5,
        "sanjose": 28,
        "seattle": 55,
        "seattlekraken": 55,
        "stlouis": 19,
        "tampabay": 14,
        "tampa": 14,  # 2019-20 typo
        "toronto": 10,
        "vancouver": 23,
        "vegas": 54,
        "washington": 15,
        "winnipeg": 52,
        "arizona": 53,
        "arizonas": 53,  # 2019-20 typo
        "phoenix": 53,  # historical Coyotes name
        "utah": 68,
        "utahhockeyclub": 59,
        "utahmammoth": 68,
    }
    for key, team_id in aliases.items():
        index.setdefault(key, team_id)
    return index


_NAME_INDEX: dict[str, int] = _build_name_index()


def resolve_team_id(name: str | None) -> int | None:
    """Resolve a source team string to its NHL ``team_id`` (``None`` if unknown)."""
    if name is None:
        return None
    text = str(name).strip()
    if not text:
        return None
    return _NAME_INDEX.get(_norm_key(text))


# ── American-odds and de-vig math ────────────────────────────────────────


def american_to_decimal(american: float) -> float:
    """Convert American moneyline odds to decimal odds.

    ``-150`` → ``1.667``; ``+130`` → ``2.30``. ``0`` is invalid.
    """
    value = float(american)
    if value == 0:
        raise ValueError("American odds cannot be 0")
    if value > 0:
        return 1.0 + value / 100.0
    return 1.0 + 100.0 / abs(value)


def american_to_implied_prob(american: float) -> float:
    """Raw (vig-inclusive) implied win probability from an American price.

    ``-200`` → ``0.667``; ``+150`` → ``0.40``. This is ``1 / decimal_odds``.
    """
    value = float(american)
    if value == 0:
        raise ValueError("American odds cannot be 0")
    if value > 0:
        return 100.0 / (value + 100.0)
    return abs(value) / (abs(value) + 100.0)


@dataclass(frozen=True)
class DevigResult:
    """A de-vigged two-way market: fair probabilities and the removed overround."""

    home_prob: float
    away_prob: float
    overround: float
    method: str


def devig_proportional(home_ml: float, away_ml: float) -> DevigResult:
    """De-vig a two-sided moneyline with the proportional (normalization) method.

    Both raw implied probabilities are divided by their sum (the overround), so
    the fair probabilities sum to 1 while preserving their ratio. This is the
    documented default for two-sided prices (SPEC §5; PROVENANCE odds sources).
    """
    q_home = american_to_implied_prob(home_ml)
    q_away = american_to_implied_prob(away_ml)
    overround = q_home + q_away
    if overround <= 0:
        raise ValueError("Non-positive overround; invalid moneyline pair")
    return DevigResult(
        home_prob=q_home / overround,
        away_prob=q_away / overround,
        overround=overround,
        method=DEVIG_PROPORTIONAL,
    )


def devig_favorite_only(
    favorite_ml: float, *, overround: float = STANDARD_OVERROUND
) -> DevigResult:
    """Approximate a de-vigged price from the favorite side alone.

    With no underdog price, exact de-vigging is impossible. We remove an assumed
    two-way ``overround`` from the favorite's raw implied probability and take
    the complement for the underdog - a documented standard-overround
    approximation (SPEC §5). Only probabilities are produced; no underdog
    American price is ever fabricated. The favorite is treated as the *home*
    side here; callers map the result to the true favored side.

    The favorite is, by identification, at least a coin flip. Dividing a
    marginal favorite's raw implied probability by the assumed two-way overround
    can push prices in ``(-100, -110]`` fractionally below ``0.5`` - inverting
    the sides so the "favorite" reads as an underdog (CODE_REVIEW m-5). We floor
    the favorite at ``0.5`` so the identified favorite never de-vigs below even.
    """
    if overround <= 0:
        raise ValueError("overround must be positive")
    q_fav = american_to_implied_prob(favorite_ml)
    p_fav = q_fav / overround
    p_fav = min(max(p_fav, 0.5), 1.0)
    return DevigResult(
        home_prob=p_fav,
        away_prob=1.0 - p_fav,
        overround=overround,
        method=DEVIG_STANDARD_OVERROUND,
    )


# ── Playoff labeling (CODE_REVIEW M-4) ───────────────────────────────────

# NHL archive gameTypeId values (SPEC §4): 2 = regular season, 3 = playoffs.
# These are the authoritative source of a game's playoff status - the fixed
# April-window heuristic below mislabels late-April regular-season games (M-4)
# and misses early-October preseason games (m-12), so consolidation joins each
# priced row to the archive's gameTypeId whenever the archive index is supplied.
REGULAR_SEASON_GAME_TYPE = 2
PLAYOFF_GAME_TYPE = 3


# ── Playoff windows (PROVENANCE §5) ──────────────────────────────────────

# Real per-season playoff windows keyed by season ENDING year, as inclusive
# (start, end) dates. Non-April windows for the 2020 bubble and 2021 are
# explicit; any year not listed falls back to the standard April-June window.
_PLAYOFF_WINDOWS: dict[int, tuple[date, date]] = {
    2017: (date(2017, 4, 1), date(2017, 6, 30)),
    2018: (date(2018, 4, 1), date(2018, 6, 30)),
    2019: (date(2019, 4, 1), date(2019, 6, 30)),
    2020: (date(2020, 8, 1), date(2020, 10, 5)),  # Toronto/Edmonton bubble
    2021: (date(2021, 5, 15), date(2021, 7, 31)),  # late start, May-Jul
    2022: (date(2022, 4, 1), date(2022, 6, 30)),
    2023: (date(2023, 4, 1), date(2023, 6, 30)),
    2024: (date(2024, 4, 1), date(2024, 6, 30)),
    2025: (date(2025, 4, 1), date(2025, 6, 30)),
    2026: (date(2026, 4, 1), date(2026, 6, 30)),
}


def playoff_window(season_end_year: int) -> tuple[date, date]:
    """Inclusive playoff (start, end) dates for a season's ending year."""
    if season_end_year in _PLAYOFF_WINDOWS:
        return _PLAYOFF_WINDOWS[season_end_year]
    return (date(season_end_year, 4, 1), date(season_end_year, 6, 30))


def is_playoff_game(season_end_year: int, game_date: date) -> bool:
    """True if ``game_date`` falls in the season's real playoff window."""
    start, end = playoff_window(season_end_year)
    return start <= game_date <= end


def is_preseason_game(season_end_year: int, game_date: date) -> bool:
    """Heuristic preseason flag: September games outside the playoff window.

    The regular season starts in October, so September games are preseason -
    except the 2020 bubble, whose playoffs run into September (handled by the
    playoff-window check). Preseason rows are excluded from the odds table.
    """
    if is_playoff_game(season_end_year, game_date):
        return False
    return game_date.month == 9


# ── Row schema ───────────────────────────────────────────────────────────

_ODDS_COLUMNS: tuple[str, ...] = (
    "source",
    "season_end_year",
    "game_date",
    "neutral_site",
    "is_playoff",
    "away_team_id",
    "home_team_id",
    "away_team_name",
    "home_team_name",
    "away_ml",
    "home_ml",
    "favorite_side",
    "both_sides",
    "covered",
    "away_implied",
    "home_implied",
    "devig_method",
    "overround",
    "game_key",
)


def _game_key(season_end_year: int, game_date: date, away_id: int, home_id: int) -> str:
    return f"{season_end_year}:{game_date.isoformat()}:{away_id}@{home_id}"


def _american(value: object) -> float | None:
    """Coerce a cell to a float American price, or ``None`` if blank/invalid."""
    if value is None:
        return None
    try:
        price = float(cast("str | SupportsFloat | SupportsIndex", value))
    except (TypeError, ValueError):
        return None
    if pd.isna(price) or price == 0:
        return None
    return price


def _empty_odds_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=list(_ODDS_COLUMNS))


@dataclass(frozen=True)
class OddsRowGame:
    source: str
    season_end_year: int
    game_date: date
    away_id: int
    home_id: int
    away_name: str
    home_name: str
    neutral: bool


def _two_sided_row(
    game: OddsRowGame,
    *,
    away_ml: float,
    home_ml: float,
) -> dict[str, Any]:
    devig = devig_proportional(home_ml, away_ml)
    favorite_side = "home" if home_ml < away_ml else "away"
    return {
        "source": game.source,
        "season_end_year": game.season_end_year,
        "game_date": game.game_date.isoformat(),
        "neutral_site": game.neutral,
        "is_playoff": is_playoff_game(game.season_end_year, game.game_date),
        "away_team_id": game.away_id,
        "home_team_id": game.home_id,
        "away_team_name": game.away_name,
        "home_team_name": game.home_name,
        "away_ml": away_ml,
        "home_ml": home_ml,
        "favorite_side": favorite_side,
        "both_sides": True,
        "covered": True,
        "away_implied": devig.away_prob,
        "home_implied": devig.home_prob,
        "devig_method": devig.method,
        "overround": devig.overround,
        "game_key": _game_key(game.season_end_year, game.game_date, game.away_id, game.home_id),
    }


def _favorite_only_row(
    game: OddsRowGame,
    *,
    favorite_ml: float,
    favorite_side: str,
    overround: float = STANDARD_OVERROUND,
) -> dict[str, Any]:
    devig = devig_favorite_only(favorite_ml, overround=overround)
    if favorite_side == "home":
        home_prob, away_prob = devig.home_prob, devig.away_prob
        home_ml: float | None = favorite_ml
        away_ml: float | None = None
    else:
        away_prob, home_prob = devig.home_prob, devig.away_prob
        away_ml = favorite_ml
        home_ml = None
    return {
        "source": game.source,
        "season_end_year": game.season_end_year,
        "game_date": game.game_date.isoformat(),
        "neutral_site": game.neutral,
        "is_playoff": is_playoff_game(game.season_end_year, game.game_date),
        "away_team_id": game.away_id,
        "home_team_id": game.home_id,
        "away_team_name": game.away_name,
        "home_team_name": game.home_name,
        "away_ml": away_ml,
        "home_ml": home_ml,
        "favorite_side": favorite_side,
        "both_sides": False,
        "covered": True,
        "away_implied": away_prob,
        "home_implied": home_prob,
        "devig_method": devig.method,
        "overround": devig.overround,
        "game_key": _game_key(game.season_end_year, game.game_date, game.away_id, game.home_id),
    }


def _finalize(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return _empty_odds_frame()
    df = pd.DataFrame.from_records(rows, columns=list(_ODDS_COLUMNS))
    return df.reset_index(drop=True)


# Re-export source-parser helpers from this public module path.
_odds_sources_module = import_module("draft_oracle.ingest._odds_sources")
_SBR_SEASON_RE = _odds_sources_module._SBR_SEASON_RE
_FAVORITE_CSV_COLUMNS = _odds_sources_module._FAVORITE_CSV_COLUMNS
FavoriteResolver = _odds_sources_module.FavoriteResolver
_blank_market_fields = _odds_sources_module._blank_market_fields
_espn_completion_favorite_sides = _odds_sources_module._espn_completion_favorite_sides
_favorite_rows_from_games = _odds_sources_module._favorite_rows_from_games
_favorite_side_from_pair_spreads = _odds_sources_module._favorite_side_from_pair_spreads
_is_placeholder_price = _odds_sources_module._is_placeholder_price
_kaggle_favorite_side = _odds_sources_module._kaggle_favorite_side
_parse_utc_date = _odds_sources_module._parse_utc_date
_pickcenter_favorite_side = _odds_sources_module._pickcenter_favorite_side
_placeholder_prices_by_season = _odds_sources_module._placeholder_prices_by_season
_reconstruct_date = _odds_sources_module._reconstruct_date
_sbr_season_end_year = _odds_sources_module._sbr_season_end_year
_uncovered_row = _odds_sources_module._uncovered_row


def build_source_odds(archive_dir: Path = DEFAULT_ODDS_ARCHIVE_DIR) -> pd.DataFrame:
    """Parse every committed archive source into one de-vigged long table."""
    return cast("pd.DataFrame", _odds_sources_module.build_source_odds(archive_dir))


def parse_espn_completion(path: Path, *, summary_dir: Path | None = None) -> pd.DataFrame:
    """Parse the ESPN 2025-26 completion ``games.csv`` favorite-only odds file."""
    return cast(
        "pd.DataFrame",
        _odds_sources_module.parse_espn_completion(path, summary_dir=summary_dir),
    )


def parse_kaggle_extensive(path: Path) -> pd.DataFrame:
    """Parse the Kaggle/ESPN ``nhl_data_extensive`` favorite-only odds file."""
    return cast("pd.DataFrame", _odds_sources_module.parse_kaggle_extensive(path))


def parse_sbr_archive(archive_dir: Path) -> pd.DataFrame:
    """Parse every committed SBR workbook under ``archive_dir``."""
    return cast("pd.DataFrame", _odds_sources_module.parse_sbr_archive(archive_dir))


def parse_sbr_workbook(path: Path) -> pd.DataFrame:
    """Parse one SBR season workbook into two-sided, de-vigged odds rows."""
    return cast("pd.DataFrame", _odds_sources_module.parse_sbr_workbook(path))


# Re-export split helpers from this public module path.
_accumulate_game_types = _odds_consolidate_module._accumulate_game_types
_accumulate_local_dates = _odds_consolidate_module._accumulate_local_dates
_cluster_members = _odds_consolidate_module._cluster_members
_label_playoff_from_archive = _odds_consolidate_module._label_playoff_from_archive
_lookup_game_type = _odds_consolidate_module._lookup_game_type
_parse_date_str = _odds_consolidate_module._parse_date_str
_snap_to_local_date = _odds_consolidate_module._snap_to_local_date
consolidate_odds = _odds_consolidate_module.consolidate_odds
load_archive_game_types = _odds_consolidate_module.load_archive_game_types
load_local_game_dates = _odds_consolidate_module.load_local_game_dates

DEFAULT_ODDS_API_DELAY = _odds_live_module.DEFAULT_ODDS_API_DELAY
ESPN_SUMMARY_BASE = _odds_live_module.ESPN_SUMMARY_BASE
ODDS_API_BASE = _odds_live_module.ODDS_API_BASE
ODDS_API_SPORT = _odds_live_module.ODDS_API_SPORT
EspnGameOddsClient = _odds_live_module.EspnGameOddsClient
OddsApiBookmaker = _odds_live_module.OddsApiBookmaker
OddsApiClient = _odds_live_module.OddsApiClient
OddsApiEvent = _odds_live_module.OddsApiEvent
OddsApiMarket = _odds_live_module.OddsApiMarket
OddsApiOutcome = _odds_live_module.OddsApiOutcome
_dig = _odds_live_module._dig
_median = _odds_live_module._median
_pickcenter_favorite_ml = _odds_live_module._pickcenter_favorite_ml
espn_summary_to_rows = _odds_live_module.espn_summary_to_rows
odds_api_events_to_rows = _odds_live_module.odds_api_events_to_rows


@dataclass
class OddsResult:
    """Outcome of :func:`build_odds_table`."""

    out_dir: Path
    source_rows: int
    game_rows: int
    covered_rows: int
    uncovered_rows: int
    placeholder_uncovered_rows: int = 0
    xval_flagged_rows: int = 0
    unmatched_uncovered_rows: int = 0
    orientation_unmatched_rows: int = 0
    unattributed_uncovered_rows: int = 0


def build_odds_table(
    archive_dir: Path = DEFAULT_ODDS_ARCHIVE_DIR,
    out_dir: Path = DEFAULT_NORMALIZED_DIR,
    nhl_archive_dir: Path = DEFAULT_NHL_ARCHIVE_DIR,
) -> OddsResult:
    """Build the odds tables from committed archives and write them to Parquet.

    Writes ``odds_by_source.parquet`` (every source row, de-vigged) and
    ``odds.parquet`` (one consolidated best row per game). Offline and
    deterministic - no network. Games absent from every archive simply do not
    appear; games present but priceless are flagged (``covered=False``).

    ``nhl_archive_dir`` supplies the NHL archive's local game dates so
    consolidation normalizes Kaggle/ESPN UTC dates onto the local convention the
    market join expects (CODE_REVIEW M-2), and its authoritative ``gameTypeId``
    so ``is_playoff`` is labeled from the archive rather than fixed April windows
    (CODE_REVIEW M-4, m-12).
    """
    source_odds = build_source_odds(archive_dir)
    local_game_dates = load_local_game_dates(nhl_archive_dir)
    local_game_types = load_archive_game_types(nhl_archive_dir)
    consolidated = consolidate_odds(
        source_odds,
        local_game_dates=local_game_dates,
        local_game_types=local_game_types,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    source_odds.to_parquet(out_dir / f"{ODDS_BY_SOURCE_TABLE_NAME}.parquet", index=False)
    consolidated.to_parquet(out_dir / f"{ODDS_TABLE_NAME}.parquet", index=False)
    covered = int(consolidated["covered"].sum()) if not consolidated.empty else 0
    return OddsResult(
        out_dir=out_dir,
        source_rows=len(source_odds),
        game_rows=len(consolidated),
        covered_rows=covered,
        uncovered_rows=len(consolidated) - covered,
        placeholder_uncovered_rows=int(source_odds.attrs.get("placeholder_uncovered_rows", 0)),
        xval_flagged_rows=int(consolidated.attrs.get("xval_flagged_rows", 0)),
        unmatched_uncovered_rows=int(consolidated.attrs.get("unmatched_uncovered_rows", 0)),
        orientation_unmatched_rows=int(consolidated.attrs.get("orientation_unmatched_rows", 0)),
        unattributed_uncovered_rows=int(source_odds.attrs.get("unattributed_uncovered_rows", 0)),
    )

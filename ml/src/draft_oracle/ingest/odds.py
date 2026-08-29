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
  Dec 2025) - favorite-side moneyline only. The favorite's row carries the
  negative ``spread`` (PROVENANCE §8), which identifies the priced side.
* **ESPN 2025-26 completion** (``espn-2025-26-completion/games.csv``, Dec 2025 -
  Jun 2026 incl. the 2026 playoffs) - favorite-side moneyline only; ESPN's
  ``spread`` is home-relative (PROVENANCE §9), so ``spread < 0`` ⇒ home favorite.

Favorite-only prices cannot be de-vigged exactly (no underdog price). We NEVER
fabricate an underdog American price; instead we remove a documented standard
two-way overround (``STANDARD_OVERROUND``) from the favorite's raw implied
probability and take the complement for the underdog (SPEC §5).

Playoffs are tagged by the real per-season windows (PROVENANCE §5) - never a
fixed April-June rule, which mislabels the 2020 bubble (Aug-Sep) and 2021
(May-Jul). Games not covered by any archive are flagged, never imputed.

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

import gzip
import json
import os
import re
import time
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

import httpx
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from draft_oracle.ingest.nhl_api import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_TIMEOUT,
    NHLApiError,
    ResponseCache,
)

# ── Directory contract (SPEC §4) ─────────────────────────────────────────

DEFAULT_ODDS_ARCHIVE_DIR = Path("data/raw/odds-archive")
DEFAULT_NHL_ARCHIVE_DIR = Path("data/raw/nhl-archive")
DEFAULT_NORMALIZED_DIR = Path("data/normalized")
DEFAULT_ODDS_CACHE_DIR = Path("data/raw/odds-api")
DEFAULT_ESPN_CACHE_DIR = Path("data/raw/espn-odds")

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

# ``xval_delta`` (max-min de-vigged favourite probability across the sources
# covering a game) is now a *consumed* cross-source sanity gate: when covering
# sources disagree on the favourite's win probability by more than this many
# points the consolidated price is untrustworthy, so it is flagged uncovered
# (excluded from covered market probabilities) rather than silently published.
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
        price = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if pd.isna(price) or price == 0:
        return None
    return price


def _empty_odds_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=list(_ODDS_COLUMNS))


def _two_sided_row(
    *,
    source: str,
    season_end_year: int,
    game_date: date,
    away_id: int,
    home_id: int,
    away_name: str,
    home_name: str,
    away_ml: float,
    home_ml: float,
    neutral: bool,
) -> dict[str, Any]:
    devig = devig_proportional(home_ml, away_ml)
    favorite_side = "home" if home_ml < away_ml else "away"
    return {
        "source": source,
        "season_end_year": season_end_year,
        "game_date": game_date.isoformat(),
        "neutral_site": neutral,
        "is_playoff": is_playoff_game(season_end_year, game_date),
        "away_team_id": away_id,
        "home_team_id": home_id,
        "away_team_name": away_name,
        "home_team_name": home_name,
        "away_ml": away_ml,
        "home_ml": home_ml,
        "favorite_side": favorite_side,
        "both_sides": True,
        "covered": True,
        "away_implied": devig.away_prob,
        "home_implied": devig.home_prob,
        "devig_method": devig.method,
        "overround": devig.overround,
        "game_key": _game_key(season_end_year, game_date, away_id, home_id),
    }


def _favorite_only_row(
    *,
    source: str,
    season_end_year: int,
    game_date: date,
    away_id: int,
    home_id: int,
    away_name: str,
    home_name: str,
    favorite_ml: float,
    favorite_side: str,
    neutral: bool,
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
        "source": source,
        "season_end_year": season_end_year,
        "game_date": game_date.isoformat(),
        "neutral_site": neutral,
        "is_playoff": is_playoff_game(season_end_year, game_date),
        "away_team_id": away_id,
        "home_team_id": home_id,
        "away_team_name": away_name,
        "home_team_name": home_name,
        "away_ml": away_ml,
        "home_ml": home_ml,
        "favorite_side": favorite_side,
        "both_sides": False,
        "covered": True,
        "away_implied": away_prob,
        "home_implied": home_prob,
        "devig_method": devig.method,
        "overround": devig.overround,
        "game_key": _game_key(season_end_year, game_date, away_id, home_id),
    }


def _finalize(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return _empty_odds_frame()
    df = pd.DataFrame.from_records(rows, columns=list(_ODDS_COLUMNS))
    return df.reset_index(drop=True)


# ── SBR workbook parser (two-sided) ──────────────────────────────────────

_SBR_SEASON_RE = re.compile(r"(\d{4})-(\d{2})")


def _sbr_season_end_year(filename: str) -> int:
    match = _SBR_SEASON_RE.search(filename)
    if match is None:
        raise ValueError(f"Cannot parse SBR season from {filename!r}")
    start = int(match.group(1))
    return start + 1


def _reconstruct_date(mmdd: int, season_end_year: int) -> date:
    """MMDD integer + season → full date (months ≥ 8 belong to the earlier year).

    The 2019-20 season is the documented exception (PROVENANCE §3.3): its
    playoffs ran in the Aug-Sep 2020 bubble, so for that season Aug/Sep dates
    belong to the ending year (2020), not the starting year. No other season in
    the archive has Aug/Sep games.
    """
    month = mmdd // 100
    day = mmdd % 100
    if season_end_year == 2020 and month in (8, 9):
        year = 2020
    else:
        year = season_end_year - 1 if month >= 8 else season_end_year
    return date(year, month, day)


def parse_sbr_workbook(path: Path) -> pd.DataFrame:
    """Parse one SBR season workbook into two-sided, de-vigged odds rows.

    Indexes by column position (13 headers cover 16 values - PROVENANCE §3.1),
    reads only the first worksheet, derives home/away from the ``VH`` column
    (never row parity - §5), and reconstructs the year from the filename season
    plus the ``MMDD`` month (§3.3). Preseason rows are dropped.
    """
    season_end_year = _sbr_season_end_year(path.name)
    raw = pd.read_excel(path, sheet_name=0, header=None)
    rows: list[dict[str, Any]] = []
    # Pair consecutive rows by VH; skip the header (row 0).
    records = raw.iloc[1:].to_records(index=False)
    idx = 0
    entries = list(records)
    while idx < len(entries) - 1:
        first = entries[idx]
        second = entries[idx + 1]
        idx += 2
        vh1 = str(first[2]).strip().upper()
        vh2 = str(second[2]).strip().upper()
        neutral = vh1 == "N" and vh2 == "N"
        # Assign visitor/home from VH; for neutral games order is nominal.
        if vh1 == "H":
            home_rec, away_rec = first, second
        else:
            away_rec, home_rec = first, second
        away_id = resolve_team_id(str(away_rec[3]))
        home_id = resolve_team_id(str(home_rec[3]))
        away_ml = _american(away_rec[9])  # Close column (index 9)
        home_ml = _american(home_rec[9])
        mmdd = _american(first[0])
        if away_id is None or home_id is None or mmdd is None:
            continue
        game_date = _reconstruct_date(int(mmdd), season_end_year)
        if is_preseason_game(season_end_year, game_date):
            continue
        if away_ml is None or home_ml is None:
            rows.append(
                _uncovered_row(
                    source=SOURCE_SBR,
                    season_end_year=season_end_year,
                    game_date=game_date,
                    away_id=away_id,
                    home_id=home_id,
                    away_name=str(away_rec[3]),
                    home_name=str(home_rec[3]),
                    neutral=neutral,
                )
            )
            continue
        rows.append(
            _two_sided_row(
                source=SOURCE_SBR,
                season_end_year=season_end_year,
                game_date=game_date,
                away_id=away_id,
                home_id=home_id,
                away_name=str(away_rec[3]),
                home_name=str(home_rec[3]),
                away_ml=away_ml,
                home_ml=home_ml,
                neutral=neutral,
            )
        )
    return _finalize(rows)


def _uncovered_row(
    *,
    source: str,
    season_end_year: int,
    game_date: date,
    away_id: int,
    home_id: int,
    away_name: str,
    home_name: str,
    neutral: bool,
) -> dict[str, Any]:
    """A game with no usable price: flagged, never imputed."""
    return {
        "source": source,
        "season_end_year": season_end_year,
        "game_date": game_date.isoformat(),
        "neutral_site": neutral,
        "is_playoff": is_playoff_game(season_end_year, game_date),
        "away_team_id": away_id,
        "home_team_id": home_id,
        "away_team_name": away_name,
        "home_team_name": home_name,
        "away_ml": None,
        "home_ml": None,
        "favorite_side": None,
        "both_sides": False,
        "covered": False,
        "away_implied": None,
        "home_implied": None,
        "devig_method": None,
        "overround": None,
        "game_key": _game_key(season_end_year, game_date, away_id, home_id),
    }


def _blank_market_fields(row: dict[str, Any]) -> None:
    """Flag a consolidated row uncovered in place (xval gate, CODE_REVIEW C-2).

    Clears every priced field so the row is excluded from covered market
    probabilities while its identity, ``xval_delta`` and ``source_count`` remain
    for audit - flagged, never silently dropped.
    """
    row["covered"] = False
    row["away_ml"] = None
    row["home_ml"] = None
    row["favorite_side"] = None
    row["both_sides"] = False
    row["away_implied"] = None
    row["home_implied"] = None
    row["devig_method"] = None
    row["overround"] = None


def parse_sbr_archive(archive_dir: Path) -> pd.DataFrame:
    """Parse every committed SBR workbook under ``archive_dir``."""
    frames = [parse_sbr_workbook(p) for p in sorted(archive_dir.glob("nhl-odds-*.xlsx"))]
    non_empty = [f for f in frames if not f.empty]
    if not non_empty:
        return _empty_odds_frame()
    return pd.concat(non_empty, ignore_index=True)


# ── Favorite-only CSV parsers ────────────────────────────────────────────


def _parse_utc_date(value: object) -> date | None:
    ts = pd.to_datetime(str(value), utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    result: date = ts.date()
    return result


def _placeholder_prices_by_season(frame: pd.DataFrame) -> dict[int, frozenset[float] | None]:
    """Detect near-constant placeholder favourite prices per season (C-2).

    Returns a mapping ``season_end_year -> reject`` where ``reject is None`` means
    the whole season is placeholder-filled (reject every priced row) and a
    ``frozenset`` names the dominant modal price(s) to reject while keeping the
    season's genuine prices. Seasons with real, varied markets are absent.

    A season is flagged when its priced favourite column is *near-constant*: at
    most two distinct values or a standard deviation below
    :data:`PLACEHOLDER_STD_EPSILON` (wholly placeholder), or a single modal price
    covering at least :data:`PLACEHOLDER_MODAL_FRACTION` of the priced rows
    (placeholder-dominated). See the module-level guard notes for the empirical
    thresholds this reproduces on the committed archive.
    """
    result: dict[int, frozenset[float] | None] = {}
    if "season" not in frame.columns or "favorite_moneyline" not in frame.columns:
        return result
    prices_all = pd.to_numeric(frame["favorite_moneyline"], errors="coerce")
    for season, positions in frame.groupby("season").groups.items():
        prices = prices_all.loc[positions].dropna()
        n = len(prices)
        if n < PLACEHOLDER_MIN_SEASON_ROWS:
            continue
        season_year = int(cast("int", season))
        std = float(prices.std(ddof=0)) if n > 1 else 0.0
        counts = prices.value_counts()
        modal_value = float(counts.index[0])
        modal_fraction = float(counts.iloc[0]) / n
        if prices.nunique() <= 2 or std < PLACEHOLDER_STD_EPSILON:
            result[season_year] = None
        elif modal_fraction >= PLACEHOLDER_MODAL_FRACTION:
            result[season_year] = frozenset({modal_value})
    return result


def _is_placeholder_price(reject: frozenset[float] | None, fav_ml: float | None) -> bool:
    """True if ``fav_ml`` is a rejected placeholder for its (flagged) season."""
    if reject is None:
        return True
    if fav_ml is None:
        return False
    return any(abs(fav_ml - value) < 1e-6 for value in reject)


def _favorite_side_from_pair_spreads(
    home_spread: float | None, away_spread: float | None
) -> str | None:
    """Favored side from a genuine *per-team* (opposite-signed) spread pair.

    A trustworthy per-team spread encodes the favorite as the negative side and
    the underdog as the positive side. The Kaggle ``nhl_data_extensive`` archive
    instead stamps a single game-level spread on BOTH rows (identical in
    29,415/29,417 games - CODE_REVIEW C-1), which encodes no favorite: return
    ``None`` so those rows are left unattributed rather than guessed as home.
    """
    if home_spread is None or away_spread is None:
        return None
    if home_spread < 0 < away_spread:
        return "home"
    if away_spread < 0 < home_spread:
        return "away"
    return None


def _kaggle_favorite_side(_game_id: object, home: pd.Series, away: pd.Series) -> str | None:
    """Kaggle favorite resolver: trust only a genuine per-team spread pair."""
    return _favorite_side_from_pair_spreads(
        _american(home["spread"]), _american(away["spread"])
    )


# A resolver maps (game_id, home_row, away_row) -> favored side, or ``None``
# when the source carries no trustworthy favorite signal for that game.
FavoriteResolver = Callable[[object, pd.Series, pd.Series], "str | None"]


def _favorite_rows_from_games(
    grouped: pd.DataFrame,
    *,
    source: str,
    resolve_favorite: FavoriteResolver | None = None,
    placeholder_seasons: Mapping[int, frozenset[float] | None] | None = None,
) -> list[dict[str, Any]]:
    """Build favorite-only rows from a per-game two-row frame.

    ``resolve_favorite`` identifies the favored side per game (defaulting to the
    Kaggle per-team-spread resolver). When it returns ``None`` the price has no
    trustworthy favorite attribution, so the row is emitted ``covered=False``
    (unattributed) rather than guessed - CODE_REVIEW C-1: the Kaggle home-row
    spread sign is game-level and identical on both rows, so it must never be
    used to attribute a favorite.

    When ``placeholder_seasons`` flags a season (CODE_REVIEW C-2), that season's
    fabricated constant prices are emitted as ``covered=False`` rows rather than
    genuine coverage - flagged, never imputed and never silently dropped.
    """
    if resolve_favorite is None:
        resolve_favorite = _kaggle_favorite_side
    rows: list[dict[str, Any]] = []
    for game_id, pair in grouped.groupby("game_id", sort=True):
        if len(pair) != 2:
            continue
        home_mask = pair["is_home"].astype(float) == 1
        if home_mask.sum() != 1 or (~home_mask).sum() != 1:
            continue
        home = pair[home_mask].iloc[0]
        away = pair[~home_mask].iloc[0]
        game_date = _parse_utc_date(home["date"])
        season_end_year = int(home["season"])
        if game_date is None:
            continue
        if is_preseason_game(season_end_year, game_date):
            continue
        home_id = resolve_team_id(str(home["team_name"]))
        away_id = resolve_team_id(str(away["team_name"]))
        if home_id is None or away_id is None:
            continue
        fav_ml = _american(home["favorite_moneyline"])
        favorite_side = resolve_favorite(game_id, home, away)
        is_placeholder = (
            placeholder_seasons is not None
            and season_end_year in placeholder_seasons
            and _is_placeholder_price(placeholder_seasons[season_end_year], fav_ml)
        )
        if fav_ml is None or is_placeholder or favorite_side is None:
            row = _uncovered_row(
                source=source,
                season_end_year=season_end_year,
                game_date=game_date,
                away_id=away_id,
                home_id=home_id,
                away_name=str(away["team_name"]),
                home_name=str(home["team_name"]),
                neutral=False,
            )
            if is_placeholder:
                row["_placeholder"] = True
            elif fav_ml is not None and favorite_side is None:
                row["_unattributed"] = True
            rows.append(row)
            continue
        rows.append(
            _favorite_only_row(
                source=source,
                season_end_year=season_end_year,
                game_date=game_date,
                away_id=away_id,
                home_id=home_id,
                away_name=str(away["team_name"]),
                home_name=str(home["team_name"]),
                favorite_ml=fav_ml,
                favorite_side=favorite_side,
                neutral=False,
            )
        )
    return rows


_FAVORITE_CSV_COLUMNS = (
    "game_id",
    "date",
    "season",
    "team_name",
    "is_home",
    "spread",
    "favorite_moneyline",
)


def parse_kaggle_extensive(path: Path) -> pd.DataFrame:
    """Parse the Kaggle/ESPN ``nhl_data_extensive`` favorite-only odds file.

    Season labels are ENDING years; the favorite's row carries the negative
    ``spread`` (PROVENANCE §8). Rows with no ``favorite_moneyline`` are flagged.

    A per-season placeholder guard (CODE_REVIEW C-2) rejects the archive's
    fabricated constant prices: seasons whose favourite-price column is
    near-constant are emitted as ``covered=False`` rather than genuine coverage.
    The count of rejected rows is recorded on ``frame.attrs`` under
    ``"placeholder_uncovered_rows"``.
    """
    raw = pd.read_csv(
        path,
        compression="gzip" if path.suffix == ".gz" else None,
        usecols=list(_FAVORITE_CSV_COLUMNS),
    )
    placeholder_seasons = _placeholder_prices_by_season(raw)
    rows = _favorite_rows_from_games(
        raw, source=SOURCE_KAGGLE, placeholder_seasons=placeholder_seasons
    )
    placeholder_uncovered = sum(1 for row in rows if row.get("_placeholder"))
    unattributed = sum(1 for row in rows if row.get("_unattributed"))
    frame = _finalize(rows)
    frame.attrs["placeholder_uncovered_rows"] = placeholder_uncovered
    frame.attrs["unattributed_uncovered_rows"] = unattributed
    return frame


def _pickcenter_favorite_side(pickcenter: Mapping[str, Any]) -> str | None:
    """Favored side from an ESPN ``pickcenter`` entry's per-side favorite flags.

    ``homeTeamOdds.favorite`` / ``awayTeamOdds.favorite`` are the authoritative
    favorite encoding in the raw ESPN summaries (CODE_REVIEW C-1). Returns
    ``None`` when neither side is flagged.
    """
    home = pickcenter.get("homeTeamOdds")
    if isinstance(home, dict) and home.get("favorite"):
        return "home"
    away = pickcenter.get("awayTeamOdds")
    if isinstance(away, dict) and away.get("favorite"):
        return "away"
    return None


def _espn_completion_favorite_sides(
    summary_dir: Path, game_ids: Iterable[int]
) -> dict[int, str]:
    """Read authoritative favorite sides from committed raw ESPN summaries.

    Each ``{event_id}.json.gz`` under ``summary_dir`` carries a ``pickcenter``
    block whose ``homeTeamOdds.favorite`` flag names the favorite directly
    (CODE_REVIEW C-1). Missing/unreadable summaries are skipped so the caller
    can fall back to the home-relative spread convention.
    """
    sides: dict[int, str] = {}
    if not summary_dir.exists():
        return sides
    for game_id in game_ids:
        path = summary_dir / f"{int(game_id)}.json.gz"
        if not path.exists():
            continue
        try:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                summary = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        pickcenter = summary.get("pickcenter") if isinstance(summary, Mapping) else None
        if isinstance(pickcenter, list) and pickcenter and isinstance(pickcenter[0], dict):
            side = _pickcenter_favorite_side(pickcenter[0])
            if side is not None:
                sides[int(game_id)] = side
    return sides


def parse_espn_completion(
    path: Path, *, summary_dir: Path | None = None
) -> pd.DataFrame:
    """Parse the ESPN 2025-26 completion ``games.csv`` favorite-only odds file.

    The favorite is read from the committed raw ESPN summaries'
    ``homeTeamOdds.favorite`` flag (``raw/summary/{event_id}.json.gz`` beside the
    CSV - CODE_REVIEW C-1). When a summary is absent the parser falls back to
    ESPN's home-relative ``spread`` convention (``spread < 0`` ⇒ home favorite -
    PROVENANCE §9), which the completion CSV documents per-game. Season labels
    are ENDING years.
    """
    raw = pd.read_csv(path, usecols=list(_FAVORITE_CSV_COLUMNS))
    if summary_dir is None:
        summary_dir = path.parent / "raw" / "summary"
    game_ids = (
        pd.to_numeric(raw["game_id"], errors="coerce").dropna().astype(int).unique()
    )
    favorite_sides = _espn_completion_favorite_sides(Path(summary_dir), game_ids)

    def resolve(game_id: object, home: pd.Series, _away: pd.Series) -> str | None:
        gid = _american(game_id)
        if gid is not None and int(gid) in favorite_sides:
            return favorite_sides[int(gid)]
        home_spread = _american(home["spread"])
        return "home" if (home_spread is not None and home_spread < 0) else "away"

    rows = _favorite_rows_from_games(
        raw, source=SOURCE_ESPN_COMPLETION, resolve_favorite=resolve
    )
    return _finalize(rows)


# ── Build + consolidate ──────────────────────────────────────────────────


def build_source_odds(archive_dir: Path = DEFAULT_ODDS_ARCHIVE_DIR) -> pd.DataFrame:
    """Parse every committed archive source into one de-vigged long table."""
    frames: list[pd.DataFrame] = []
    if archive_dir.exists():
        frames.append(parse_sbr_archive(archive_dir))
        kaggle = archive_dir / "kaggle-nhl-historical" / "nhl_data_extensive.csv.gz"
        if kaggle.exists():
            frames.append(parse_kaggle_extensive(kaggle))
        completion = archive_dir / "espn-2025-26-completion" / "games.csv"
        if completion.exists():
            frames.append(parse_espn_completion(completion))
    non_empty = [f for f in frames if not f.empty]
    if not non_empty:
        return _empty_odds_frame()
    placeholder_uncovered = sum(
        int(f.attrs.get("placeholder_uncovered_rows", 0)) for f in non_empty
    )
    out = pd.concat(non_empty, ignore_index=True)
    out = out.reset_index(drop=True)
    out.attrs["placeholder_uncovered_rows"] = placeholder_uncovered
    return out


def consolidate_odds(
    source_odds: pd.DataFrame,
    local_game_dates: Mapping[tuple[int, int, int], tuple[date, ...]] | None = None,
    local_game_types: Mapping[tuple[int, int, int], Mapping[date, int]] | None = None,
) -> pd.DataFrame:
    """Collapse the per-source table to one best row per game.

    Rows are clustered into real games on (season, away id, home id): rows from
    the same source must share the exact date, while rows from *different*
    sources match within a ±1 day tolerance (Kaggle/ESPN dates are UTC and can
    be one calendar day ahead of SBR's local dates - PROVENANCE §9). Each
    cluster keeps at most one row per source, so two same-matchup games on
    adjacent days are never merged. The highest-priority covering source wins
    (SBR Close preferred); the de-vigged favorite probability of every covering
    source is cross-validated and the disagreement recorded in ``xval_delta``.

    When ``local_game_dates`` is supplied (the NHL archive's local game dates,
    keyed by ``(season_end_year, home_id, away_id)``), each consolidated row's
    ``game_date`` is snapped onto the matching archive local date within ±1 day
    (CODE_REVIEW M-2). This gives the written table ONE documented convention -
    the NHL-archive local date - so ``game_win._attach_market``'s exact-date
    join actually lands on the game instead of dropping UTC-stamped prices.

    When ``local_game_types`` is supplied (the archive's ``gameTypeId`` index,
    :func:`load_archive_game_types`), ``is_playoff`` is set from the archive's
    authoritative gameTypeId (2 = regular, 3 = playoff) rather than the fixed
    April windows that mislabel late-April regular-season games (CODE_REVIEW
    M-4). A priced row that matches no archive game is flagged ``is_playoff=None``
    and blanked to uncovered (kept and counted in ``attrs["unmatched_uncovered_rows"]``,
    never dropped silently) so it leaves the covered market universe - this also
    closes the early-October preseason leak (m-12), since preseason games are
    absent from the archive's regular-season set.
    """
    keep = [*list(_ODDS_COLUMNS), "xval_delta", "source_count"]
    if source_odds.empty:
        out = pd.DataFrame(columns=keep)
        out.attrs["xval_flagged_rows"] = 0
        out.attrs["unmatched_uncovered_rows"] = 0
        return out

    raw_records = source_odds.to_dict("records")
    records: list[dict[str, Any]] = [cast("dict[str, Any]", r) for r in raw_records]
    for i, rec in enumerate(records):
        rec["_priority"] = _SOURCE_PRIORITY.get(str(rec["source"]), 0)
        rec["_date"] = _parse_date_str(str(rec["game_date"]))
        rec["_pos"] = i
        rec["_used"] = False
        home_imp = rec.get("home_implied")
        away_imp = rec.get("away_implied")
        rec["_fav_prob"] = _max_prob(home_imp, away_imp)

    # Bucket by (season, away, home) for candidate lookup.
    buckets: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    for rec in records:
        if rec["away_team_id"] is None or rec["home_team_id"] is None:
            continue
        if pd.isna(rec["away_team_id"]) or pd.isna(rec["home_team_id"]):
            continue
        key = (
            int(rec["season_end_year"]),
            int(rec["away_team_id"]),
            int(rec["home_team_id"]),
        )
        buckets.setdefault(key, []).append(rec)

    order = sorted(records, key=lambda r: (-int(r["_priority"]), not bool(r["covered"]), r["_pos"]))
    out_rows: list[dict[str, Any]] = []
    xval_flagged = 0
    unmatched_uncovered = 0
    for anchor in order:
        if anchor["_used"]:
            continue
        if anchor["away_team_id"] is None or anchor["home_team_id"] is None:
            continue
        if pd.isna(anchor["away_team_id"]) or pd.isna(anchor["home_team_id"]):
            continue
        key = (
            int(anchor["season_end_year"]),
            int(anchor["away_team_id"]),
            int(anchor["home_team_id"]),
        )
        members = _cluster_members(anchor, buckets.get(key, []))
        for member in members:
            member["_used"] = True
        fav_probs = [
            float(m["_fav_prob"])
            for m in members
            if bool(m["covered"]) and m["_fav_prob"] is not None and not pd.isna(m["_fav_prob"])
        ]
        best = {col: anchor[col] for col in _ODDS_COLUMNS}
        xval_delta = (max(fav_probs) - min(fav_probs)) if len(fav_probs) > 1 else 0.0
        best["xval_delta"] = xval_delta
        best["source_count"] = len(members)
        _snap_to_local_date(best, local_game_dates)
        if _label_playoff_from_archive(best, local_game_types) and bool(best["covered"]):
            _blank_market_fields(best)
            unmatched_uncovered += 1
        if bool(best["covered"]) and xval_delta > XVAL_DELTA_THRESHOLD:
            _blank_market_fields(best)
            xval_flagged += 1
        out_rows.append(best)

    out = pd.DataFrame.from_records(out_rows, columns=keep)
    out = out.sort_values(["season_end_year", "game_date", "game_key"], kind="stable")
    out = out.reset_index(drop=True)
    out.attrs["xval_flagged_rows"] = xval_flagged
    out.attrs["unmatched_uncovered_rows"] = unmatched_uncovered
    return out


def _cluster_members(anchor: dict[str, Any], bucket: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select the anchor plus the nearest unused row from each other source.

    Same-source rows must share the anchor's exact date; other-source rows match
    within ±1 day, nearest first. At most one row per source is returned.
    """
    members = [anchor]
    taken_sources = {anchor["source"]}
    anchor_date = anchor["_date"]
    candidates = sorted(
        (
            rec
            for rec in bucket
            if not rec["_used"]
            and rec["_pos"] != anchor["_pos"]
            and rec["_date"] is not None
            and abs((rec["_date"] - anchor_date).days) <= 1
        ),
        key=lambda r: abs((r["_date"] - anchor_date).days),
    )
    for rec in candidates:
        if rec["source"] in taken_sources:
            continue
        members.append(rec)
        taken_sources.add(rec["source"])
    return members


def _parse_date_str(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _snap_to_local_date(
    row: dict[str, Any],
    local_game_dates: Mapping[tuple[int, int, int], tuple[date, ...]] | None,
) -> None:
    """Rewrite ``game_date`` to the NHL-archive local date (CODE_REVIEW M-2).

    Kaggle/ESPN stamp UTC calendar dates (an evening game lands on the next
    day); the NHL archive and SBR use local dates. When an archive game with the
    same matchup sits within ±1 day, snap ``game_date`` (and ``game_key``) onto
    it so the exact-date market join attaches. Rows already on a local date, or
    with no archive match, are left untouched - one documented convention, never
    a fabricated date.
    """
    if not local_game_dates:
        return
    home_id = row.get("home_team_id")
    away_id = row.get("away_team_id")
    if home_id is None or away_id is None or pd.isna(home_id) or pd.isna(away_id):
        return
    key = (int(row["season_end_year"]), int(home_id), int(away_id))
    candidates = local_game_dates.get(key)
    if not candidates:
        return
    current = _parse_date_str(str(row["game_date"]))
    if current is None or current in candidates:
        return
    within = [d for d in candidates if abs((d - current).days) <= 1]
    if not within:
        return
    nearest = min(within, key=lambda d: (abs((d - current).days), d.toordinal()))
    row["game_date"] = nearest.isoformat()
    row["game_key"] = _game_key(key[0], nearest, int(away_id), int(home_id))


def load_local_game_dates(
    archive_dir: Path = DEFAULT_NHL_ARCHIVE_DIR,
) -> dict[tuple[int, int, int], tuple[date, ...]]:
    """Index NHL-archive local game dates by ``(season_end_year, home_id, away_id)``.

    The committed archive (``team-games-*.csv.gz``) stamps each game with its
    LOCAL calendar date. ``consolidate_odds`` snaps Kaggle/ESPN UTC dates onto
    these so the market join in
    :func:`~draft_oracle.models.game_win._attach_market` lands on the game
    (CODE_REVIEW M-2). A matchup can recur within a season, so each key maps to
    the sorted tuple of its local dates.
    """
    accumulator: dict[tuple[int, int, int], set[date]] = {}
    for path in sorted(archive_dir.glob("team-games-*.csv.gz")):
        _accumulate_local_dates(pd.read_csv(path), accumulator)
    return {key: tuple(sorted(values)) for key, values in accumulator.items()}


def _accumulate_local_dates(
    frame: pd.DataFrame, accumulator: dict[tuple[int, int, int], set[date]]
) -> None:
    required = {"gameId", "seasonId", "teamId", "homeRoad", "gameDate"}
    if frame.empty or not required.issubset(frame.columns):
        return
    home = frame.loc[frame["homeRoad"] == "H", ["gameId", "seasonId", "teamId", "gameDate"]]
    away = frame.loc[frame["homeRoad"] == "R", ["gameId", "teamId"]]
    merged = home.merge(away, on="gameId", suffixes=("_home", "_away"))
    seasons = merged["seasonId"].astype(int).tolist()
    homes = merged["teamId_home"].astype(int).tolist()
    aways = merged["teamId_away"].astype(int).tolist()
    dates = merged["gameDate"].astype(str).tolist()
    for season, home_id, away_id, raw_date in zip(seasons, homes, aways, dates, strict=True):
        local = _parse_date_str(str(raw_date)[:10])
        if local is None:
            continue
        accumulator.setdefault((int(season) % 10000, int(home_id), int(away_id)), set()).add(local)


def load_archive_game_types(
    archive_dir: Path = DEFAULT_NHL_ARCHIVE_DIR,
) -> dict[tuple[int, int, int], dict[date, int]]:
    """Index NHL-archive ``gameTypeId`` by ``(season_end_year, home_id, away_id)``.

    The committed archive (``team-games-*.csv.gz``) stamps each game with its
    authoritative ``gameTypeId`` (2 = regular season, 3 = playoffs). This index
    lets :func:`consolidate_odds` label ``is_playoff`` from the archive instead
    of the fixed April windows that mislabel late-April regular-season games as
    playoffs (CODE_REVIEW M-4). Each key maps its local game dates to the
    matching ``gameTypeId``; the key is stored in both home/away orientations so
    a game whose odds row has the sides reversed still resolves.
    """
    accumulator: dict[tuple[int, int, int], dict[date, int]] = {}
    for path in sorted(archive_dir.glob("team-games-*.csv.gz")):
        _accumulate_game_types(pd.read_csv(path), accumulator)
    return accumulator


def _accumulate_game_types(
    frame: pd.DataFrame, accumulator: dict[tuple[int, int, int], dict[date, int]]
) -> None:
    required = {"gameId", "seasonId", "teamId", "homeRoad", "gameDate", "gameTypeId"}
    if frame.empty or not required.issubset(frame.columns):
        return
    home = frame.loc[
        frame["homeRoad"] == "H",
        ["gameId", "seasonId", "teamId", "gameDate", "gameTypeId"],
    ]
    away = frame.loc[frame["homeRoad"] == "R", ["gameId", "teamId"]]
    merged = home.merge(away, on="gameId", suffixes=("_home", "_away"))
    seasons = merged["seasonId"].astype(int).tolist()
    homes = merged["teamId_home"].astype(int).tolist()
    aways = merged["teamId_away"].astype(int).tolist()
    dates = merged["gameDate"].astype(str).tolist()
    types = merged["gameTypeId"].astype(int).tolist()
    for season, home_id, away_id, raw_date, type_id in zip(
        seasons, homes, aways, dates, types, strict=True
    ):
        local = _parse_date_str(str(raw_date)[:10])
        if local is None:
            continue
        season_end = int(season) % 10000
        accumulator.setdefault((season_end, int(home_id), int(away_id)), {})[local] = int(type_id)
        accumulator.setdefault((season_end, int(away_id), int(home_id)), {})[local] = int(type_id)


def _lookup_game_type(
    game_types: Mapping[tuple[int, int, int], Mapping[date, int]],
    season_end_year: int,
    home_id: int,
    away_id: int,
    game_date: date,
) -> int | None:
    """Archive ``gameTypeId`` for a matchup on ``game_date`` (exact, else ±1 day)."""
    by_date = game_types.get((season_end_year, home_id, away_id))
    if not by_date:
        return None
    exact = by_date.get(game_date)
    if exact is not None:
        return exact
    near = sorted(
        (d for d in by_date if abs((d - game_date).days) <= 1),
        key=lambda d: (abs((d - game_date).days), d.toordinal()),
    )
    return by_date[near[0]] if near else None


def _label_playoff_from_archive(
    row: dict[str, Any],
    game_types: Mapping[tuple[int, int, int], Mapping[date, int]] | None,
) -> bool:
    """Set ``is_playoff`` from the archive ``gameTypeId``; return True if unmatched.

    Joins the (already local-date-snapped) row to the NHL archive's authoritative
    ``gameTypeId`` on ``(season, home, away)`` within ±1 day: playoff → ``True``,
    regular → ``False`` (CODE_REVIEW M-4). A priced row that matches no archive
    game gets ``is_playoff=None`` and is reported so the caller can exclude it
    from covered market consumers - preseason games are absent from the archive's
    regular-season set, so this also closes the early-October preseason leak
    (m-12). Rows are never relabeled when no archive index is supplied.
    """
    if not game_types:
        return False
    home_id = row.get("home_team_id")
    away_id = row.get("away_team_id")
    if home_id is None or away_id is None or pd.isna(home_id) or pd.isna(away_id):
        return False
    game_date = _parse_date_str(str(row["game_date"]))
    if game_date is None:
        return False
    type_id = _lookup_game_type(
        game_types, int(row["season_end_year"]), int(home_id), int(away_id), game_date
    )
    if type_id is None:
        row["is_playoff"] = None
        return True
    row["is_playoff"] = type_id == PLAYOFF_GAME_TYPE
    return False


def _max_prob(home_imp: object, away_imp: object) -> float | None:
    values: list[float] = []
    for v in (home_imp, away_imp):
        if v is None or not isinstance(v, (int, float)):
            continue
        as_float = float(v)
        if pd.isna(as_float):
            continue
        values.append(as_float)
    return max(values) if values else None


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
    )


# ── Live odds: The Odds API (future games only) ──────────────────────────

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ODDS_API_SPORT = "icehockey_nhl"
DEFAULT_ODDS_API_DELAY = 1.0


class OddsApiOutcome(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str
    price: float
    point: float | None = None


class OddsApiMarket(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    key: str
    outcomes: list[OddsApiOutcome] = Field(default_factory=list)


class OddsApiBookmaker(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    key: str
    title: str | None = None
    markets: list[OddsApiMarket] = Field(default_factory=list)


class OddsApiEvent(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    commence_time: str | None = None
    home_team: str | None = None
    away_team: str | None = None
    bookmakers: list[OddsApiBookmaker] = Field(default_factory=list)


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


class OddsApiClient:
    """The Odds API client - current/upcoming NHL odds only (SPEC §5).

    Free tier serves live/upcoming markets; the paid historical endpoints are
    never called. Quota is capped (typically 500 requests/month on the free
    tier); each response's ``x-requests-remaining`` / ``x-requests-used``
    headers are captured on :attr:`requests_remaining` / :attr:`requests_used`.
    Caching and rate-limiting mirror :class:`NHLApiClient`; the API key is read
    from ``ODDS_API_KEY`` (gitignored ``ml/.env``) and never committed.
    """

    def __init__(
        self,
        cache_dir: Path | str = DEFAULT_ODDS_CACHE_DIR,
        *,
        api_key: str | None = None,
        base: str = ODDS_API_BASE,
        sport: str = ODDS_API_SPORT,
        delay: float = DEFAULT_ODDS_API_DELAY,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retry_backoff: float = 1.0,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.api_key = api_key if api_key is not None else os.environ.get("ODDS_API_KEY", "")
        self.base = base.rstrip("/")
        self.sport = sport
        self.delay = delay
        self.max_attempts = max_attempts
        self.retry_backoff = retry_backoff
        self._cache = ResponseCache(Path(cache_dir))
        self._sleep = sleep
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=timeout)
        self.requests_remaining: int | None = None
        self.requests_used: int | None = None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OddsApiClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def _get(self, path: str, params: Mapping[str, str]) -> Any:
        if not self.api_key:
            raise NHLApiError("ODDS_API_KEY is not set; cannot call The Odds API")
        query = {**params, "apiKey": self.api_key}
        # Cache key excludes the api key so a rotated key still hits the cache.
        cache_key = ResponseCache.key_for(self.base, path, dict(params))
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached.get("data")
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            if self.delay > 0:
                self._sleep(self.delay)
            try:
                response = self._client.get(f"{self.base}{path}", params=dict(query))
                response.raise_for_status()
                self._capture_quota(response.headers)
                parsed = response.json()
                self._cache.put(cache_key, {"data": parsed})
                return parsed
            except (httpx.HTTPError, ValueError) as error:
                last_error = error
                if attempt + 1 < self.max_attempts:
                    self._sleep(self.retry_backoff * (2**attempt))
        raise NHLApiError(
            f"Odds API request failed after {self.max_attempts} attempts: {path}"
        ) from last_error

    def _capture_quota(self, headers: httpx.Headers) -> None:
        remaining = headers.get("x-requests-remaining")
        used = headers.get("x-requests-used")
        if remaining is not None:
            try:
                self.requests_remaining = int(float(remaining))
            except ValueError:
                self.requests_remaining = None
        if used is not None:
            try:
                self.requests_used = int(float(used))
            except ValueError:
                self.requests_used = None

    def nhl_odds(
        self, *, markets: str = "h2h", regions: str = "us", odds_format: str = "american"
    ) -> list[OddsApiEvent]:
        """Current/upcoming NHL game odds. ``markets='h2h'`` for moneylines."""
        data = self._get(
            f"/sports/{self.sport}/odds",
            {"regions": regions, "markets": markets, "oddsFormat": odds_format},
        )
        return [OddsApiEvent.model_validate(item) for item in data]

    def nhl_series_odds(
        self, *, regions: str = "us", odds_format: str = "american"
    ) -> list[OddsApiEvent]:
        """Series/outright (futures) prices where the free tier offers them."""
        data = self._get(
            f"/sports/{self.sport}/odds",
            {"regions": regions, "markets": "outrights", "oddsFormat": odds_format},
        )
        return [OddsApiEvent.model_validate(item) for item in data]


def odds_api_events_to_rows(events: Iterable[OddsApiEvent]) -> pd.DataFrame:
    """Convert live Odds API ``h2h`` events into de-vigged odds rows.

    Uses the median moneyline across the books that priced each side (consensus
    per PROVENANCE/AC). Events whose teams do not resolve, or that lack a
    two-sided price, are flagged uncovered rather than imputed.
    """
    rows: list[dict[str, Any]] = []
    for event in events:
        if event.home_team is None or event.away_team is None:
            continue
        home_id = resolve_team_id(event.home_team)
        away_id = resolve_team_id(event.away_team)
        game_date = _parse_utc_date(event.commence_time)
        if home_id is None or away_id is None or game_date is None:
            continue
        season_end_year = game_date.year + 1 if game_date.month >= 8 else game_date.year
        home_prices: list[float] = []
        away_prices: list[float] = []
        for book in event.bookmakers:
            for market in book.markets:
                if market.key != "h2h":
                    continue
                for outcome in market.outcomes:
                    oid = resolve_team_id(outcome.name)
                    if oid == home_id:
                        home_prices.append(outcome.price)
                    elif oid == away_id:
                        away_prices.append(outcome.price)
        if not home_prices or not away_prices:
            rows.append(
                _uncovered_row(
                    source=SOURCE_ODDS_API,
                    season_end_year=season_end_year,
                    game_date=game_date,
                    away_id=away_id,
                    home_id=home_id,
                    away_name=event.away_team,
                    home_name=event.home_team,
                    neutral=False,
                )
            )
            continue
        rows.append(
            _two_sided_row(
                source=SOURCE_ODDS_API,
                season_end_year=season_end_year,
                game_date=game_date,
                away_id=away_id,
                home_id=home_id,
                away_name=event.away_team,
                home_name=event.home_team,
                away_ml=_median(away_prices),
                home_ml=_median(home_prices),
                neutral=False,
            )
        )
    return _finalize(rows)


# ── Live odds: ESPN summary (favorite-only, future games) ────────────────

ESPN_SUMMARY_BASE = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl"


class EspnGameOddsClient:
    """ESPN public ``summary`` endpoint client for a single future game.

    Reads the ``pickcenter`` block (favorite moneyline + home-relative spread,
    PROVENANCE §9). Favorite-only, so de-vigged with the standard-overround
    approximation. Caching/rate-limiting mirror :class:`NHLApiClient`; ESPN 403s
    browser-like User-Agents, so the default httpx UA is used. No key required.
    """

    def __init__(
        self,
        cache_dir: Path | str = DEFAULT_ESPN_CACHE_DIR,
        *,
        base: str = ESPN_SUMMARY_BASE,
        delay: float = 1.0,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retry_backoff: float = 1.0,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.base = base.rstrip("/")
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

    def __enter__(self) -> EspnGameOddsClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def summary(self, event_id: int | str) -> dict[str, Any]:
        """Raw (cached) ``summary`` JSON for one ESPN event id."""
        path = "/summary"
        params = {"event": str(event_id)}
        cache_key = ResponseCache.key_for(self.base, path, params)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            if self.delay > 0:
                self._sleep(self.delay)
            try:
                response = self._client.get(f"{self.base}{path}", params=dict(params))
                response.raise_for_status()
                parsed: dict[str, Any] = response.json()
                self._cache.put(cache_key, parsed)
                return parsed
            except (httpx.HTTPError, ValueError) as error:
                last_error = error
                if attempt + 1 < self.max_attempts:
                    self._sleep(self.retry_backoff * (2**attempt))
        raise NHLApiError(
            f"ESPN summary request failed after {self.max_attempts} attempts: event={event_id}"
        ) from last_error

    def game_odds(self, event_id: int | str) -> pd.DataFrame:
        """One favorite-only, de-vigged odds row for a future game (or flagged)."""
        return espn_summary_to_rows(self.summary(event_id))


def espn_summary_to_rows(summary: Mapping[str, Any]) -> pd.DataFrame:
    """Convert one ESPN ``summary`` payload into a favorite-only odds row.

    Reads ``header.competitions[0]`` for the teams/date and ``pickcenter[0]``
    for the favorite moneyline and home-relative spread (``spread < 0`` ⇒ home
    favorite - PROVENANCE §9). Missing/blank prices are flagged, not imputed.
    """
    competitions = _dig(summary, "header", "competitions")
    if not isinstance(competitions, list) or not competitions:
        return _empty_odds_frame()
    competition = competitions[0]
    competitors = competition.get("competitors", []) if isinstance(competition, dict) else []
    home_name: str | None = None
    away_name: str | None = None
    for competitor in competitors:
        team = competitor.get("team", {}) if isinstance(competitor, dict) else {}
        name = team.get("displayName") if isinstance(team, dict) else None
        if competitor.get("homeAway") == "home":
            home_name = name
        elif competitor.get("homeAway") == "away":
            away_name = name
    game_date = _parse_utc_date(competition.get("date")) if isinstance(competition, dict) else None
    if home_name is None or away_name is None or game_date is None:
        return _empty_odds_frame()
    home_id = resolve_team_id(home_name)
    away_id = resolve_team_id(away_name)
    if home_id is None or away_id is None:
        return _empty_odds_frame()
    season_end_year = game_date.year if game_date.month < 8 else game_date.year + 1

    pickcenter = summary.get("pickcenter") if isinstance(summary, Mapping) else None
    fav_ml: float | None = None
    home_relative_spread: float | None = None
    if isinstance(pickcenter, list) and pickcenter:
        first = pickcenter[0]
        if isinstance(first, dict):
            fav_ml = _pickcenter_favorite_ml(first)
            home_relative_spread = _american(first.get("spread"))
    if fav_ml is None:
        return _finalize(
            [
                _uncovered_row(
                    source=SOURCE_ESPN_SUMMARY,
                    season_end_year=season_end_year,
                    game_date=game_date,
                    away_id=away_id,
                    home_id=home_id,
                    away_name=away_name,
                    home_name=home_name,
                    neutral=False,
                )
            ]
        )
    favorite_side = (
        "home" if (home_relative_spread is not None and home_relative_spread < 0) else "away"
    )
    return _finalize(
        [
            _favorite_only_row(
                source=SOURCE_ESPN_SUMMARY,
                season_end_year=season_end_year,
                game_date=game_date,
                away_id=away_id,
                home_id=home_id,
                away_name=away_name,
                home_name=home_name,
                favorite_ml=fav_ml,
                favorite_side=favorite_side,
                neutral=False,
            )
        ]
    )


def _pickcenter_favorite_ml(pickcenter: Mapping[str, Any]) -> float | None:
    """Extract the favorite's moneyline from an ESPN ``pickcenter`` entry."""
    for side_key in ("homeTeamOdds", "awayTeamOdds"):
        side = pickcenter.get(side_key)
        if isinstance(side, dict) and side.get("favorite"):
            ml = side.get("moneyLine")
            coerced = _american(ml)
            if coerced is not None:
                return coerced
    # Fall back to a top-level moneyLine if the per-side flags are absent.
    return _american(pickcenter.get("moneyLine"))


def _dig(obj: Any, *keys: str) -> Any:
    """Safely walk nested mappings; return ``None`` on any miss."""
    current = obj
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current

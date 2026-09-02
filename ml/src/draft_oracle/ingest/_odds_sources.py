"""Committed odds archive source parsers."""

from __future__ import annotations

import gzip
import json
import re
from collections.abc import Callable, Iterable, Mapping
from datetime import date
from pathlib import Path
from typing import Any, cast

import pandas as pd

from draft_oracle.ingest.odds import (
    DEFAULT_ODDS_ARCHIVE_DIR,
    PLACEHOLDER_MIN_SEASON_ROWS,
    PLACEHOLDER_MODAL_FRACTION,
    PLACEHOLDER_STD_EPSILON,
    SOURCE_ESPN_COMPLETION,
    SOURCE_KAGGLE,
    SOURCE_SBR,
    _american,
    _empty_odds_frame,
    _favorite_only_row,
    _finalize,
    _game_key,
    _two_sided_row,
    is_playoff_game,
    is_preseason_game,
    resolve_team_id,
)

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
    return _favorite_side_from_pair_spreads(_american(home["spread"]), _american(away["spread"]))


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


def _espn_completion_favorite_sides(summary_dir: Path, game_ids: Iterable[int]) -> dict[int, str]:
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


def parse_espn_completion(path: Path, *, summary_dir: Path | None = None) -> pd.DataFrame:
    """Parse the ESPN 2025-26 completion ``games.csv`` favorite-only odds file.

    The favorite is read from the committed raw ESPN summaries'
    ``homeTeamOdds.favorite`` flag (``raw/summary/{event_id}.json.gz`` beside the
    CSV - CODE_REVIEW C-1). When a summary is absent the parser falls back to
    ESPN's home-relative ``spread`` convention (``spread < 0`` ⇒ home favorite -
    PROVENANCE §9), which the completion CSV documents per-game. A missing or
    zero spread carries no favorite signal and is emitted uncovered rather than
    guessed. Season labels are ENDING years.
    """
    raw = pd.read_csv(path, usecols=list(_FAVORITE_CSV_COLUMNS))
    if summary_dir is None:
        summary_dir = path.parent / "raw" / "summary"
    game_ids = pd.to_numeric(raw["game_id"], errors="coerce").dropna().astype(int).unique()
    favorite_sides = _espn_completion_favorite_sides(Path(summary_dir), game_ids)

    def resolve(game_id: object, home: pd.Series, _away: pd.Series) -> str | None:
        gid = _american(game_id)
        if gid is not None and int(gid) in favorite_sides:
            return favorite_sides[int(gid)]
        home_spread = _american(home["spread"])
        if home_spread is None:
            return None
        return "home" if home_spread < 0 else "away"

    rows = _favorite_rows_from_games(raw, source=SOURCE_ESPN_COMPLETION, resolve_favorite=resolve)
    unattributed = sum(1 for row in rows if row.get("_unattributed"))
    frame = _finalize(rows)
    frame.attrs["unattributed_uncovered_rows"] = unattributed
    return frame


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
    unattributed_uncovered = sum(
        int(f.attrs.get("unattributed_uncovered_rows", 0)) for f in non_empty
    )
    out = pd.concat(non_empty, ignore_index=True)
    out = out.reset_index(drop=True)
    out.attrs["placeholder_uncovered_rows"] = placeholder_uncovered
    out.attrs["unattributed_uncovered_rows"] = unattributed_uncovered
    return out




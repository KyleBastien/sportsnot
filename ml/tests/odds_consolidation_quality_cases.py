"""Kaggle placeholder and cross-validation odds tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from draft_oracle.ingest.odds import (
    SOURCE_KAGGLE,
    consolidate_odds,
    parse_kaggle_extensive,
)
from tests.odds_consolidation_helpers import (
    _KAGGLE_MATCHUPS,
    _kaggle_pair,
    parse_sbr_workbook_from_rows,
)
from tests.test_odds import REAL_KAGGLE_EXTENSIVE, _favorite_csv, _write_gz_csv


def test_parse_kaggle_extensive_flags_constant_placeholder_season(tmp_path: Path) -> None:
    # A whole season of constant -105 puck-line juice is a placeholder backfill,
    # not genuine coverage: every row must be flagged uncovered (C-2).
    games: list[dict[str, object]] = []
    for i, (home, away) in enumerate(_KAGGLE_MATCHUPS[:6], start=1):
        games += _kaggle_pair(
            game_id=i,
            date=f"2011-11-{i:02d} 00:00:00+00:00",
            season=2011,
            home=home,
            away=away,
            price=-105,
        )
    path = tmp_path / "nhl_data_extensive.csv.gz"
    _write_gz_csv(path, _favorite_csv(games))
    df = parse_kaggle_extensive(path)
    assert len(df) == 6  # rows kept (flagged), never silently dropped
    assert not bool(df["covered"].any())
    assert bool(df["home_implied"].isna().all())
    assert df.attrs["placeholder_uncovered_rows"] == 6


def test_parse_kaggle_extensive_keeps_genuine_prices_in_dominated_season(
    tmp_path: Path,
) -> None:
    # 8 placeholder -105 games + 2 genuine-priced games: modal fraction 0.8 >=
    # threshold, so the -105 block is rejected but the real prices survive.
    prices = [-105] * 8 + [-160, -220]
    games: list[dict[str, object]] = []
    for i, ((home, away), price) in enumerate(zip(_KAGGLE_MATCHUPS, prices, strict=True), start=1):
        games += _kaggle_pair(
            game_id=i,
            date=f"2026-11-{i:02d} 00:00:00+00:00",
            season=2026,
            home=home,
            away=away,
            price=price,
        )
    path = tmp_path / "nhl_data_extensive.csv.gz"
    _write_gz_csv(path, _favorite_csv(games))
    df = parse_kaggle_extensive(path)
    assert len(df) == 10
    assert int(df["covered"].sum()) == 2
    assert df.attrs["placeholder_uncovered_rows"] == 8
    covered = df.loc[df["covered"]]
    assert set(covered["home_ml"].dropna().tolist()) == {-160.0, -220.0}


def test_parse_kaggle_extensive_keeps_varied_market_season(tmp_path: Path) -> None:
    # A season of genuinely varied prices (top modal price well under half) is
    # real coverage and must be left untouched.
    prices = [-110, -135, -160, -185, -210, 105, 120, 140, 175, 210]
    games: list[dict[str, object]] = []
    for i, ((home, away), price) in enumerate(zip(_KAGGLE_MATCHUPS, prices, strict=True), start=1):
        games += _kaggle_pair(
            game_id=i,
            date=f"2022-11-{i:02d} 00:00:00+00:00",
            season=2022,
            home=home,
            away=away,
            price=price,
        )
    path = tmp_path / "nhl_data_extensive.csv.gz"
    _write_gz_csv(path, _favorite_csv(games))
    df = parse_kaggle_extensive(path)
    assert int(df["covered"].sum()) == 10
    assert df.attrs["placeholder_uncovered_rows"] == 0


def test_placeholder_guard_matches_committed_archive() -> None:
    if not REAL_KAGGLE_EXTENSIVE.exists():
        pytest.skip("committed Kaggle extensive archive not present")
    from draft_oracle.ingest.odds import (
        _FAVORITE_CSV_COLUMNS,
        _placeholder_prices_by_season,
    )

    raw = pd.read_csv(
        REAL_KAGGLE_EXTENSIVE,
        compression="gzip",
        usecols=list(_FAVORITE_CSV_COLUMNS),
    )
    placeholder = _placeholder_prices_by_season(raw)
    # Wholly-constant -105 seasons: reject every priced row.
    for season in (*range(2004, 2019), 2025):
        assert placeholder.get(season, "absent") is None, season
    # Placeholder-dominated seasons: reject the -105 block, keep genuine prices.
    assert placeholder.get(2019) == frozenset({-105.0})
    assert placeholder.get(2026) == frozenset({-105.0})
    # Real, varied markets are untouched.
    for season in (2020, 2021, 2022, 2023, 2024):
        assert season not in placeholder, season
    prices = pd.to_numeric(raw["favorite_moneyline"], errors="coerce")
    y2019 = prices[raw["season"] == 2019].dropna()
    assert float((y2019 == -105.0).mean()) == pytest.approx(0.98732, abs=1e-3)
    # The rejected 2026 -105 rows are precisely the pre-Dec-11 backfill.
    y2026 = raw[raw["season"] == 2026].copy()
    y2026["fm"] = pd.to_numeric(y2026["favorite_moneyline"], errors="coerce")
    ph_dates = pd.to_datetime(y2026.loc[y2026["fm"] == -105.0, "date"], utc=True, errors="coerce")
    assert ph_dates.max() < pd.Timestamp("2025-12-11", tz="UTC")


def test_committed_kaggle_archive_has_no_attributed_favorites() -> None:
    # CODE_REVIEW C-1: the committed Kaggle archive's spread is identical on both
    # rows (29,415/29,417 games), so no favorite can be trusted. Every parsed row
    # must be uncovered (unattributed or placeholder) - the honest outcome.
    if not REAL_KAGGLE_EXTENSIVE.exists():
        pytest.skip("committed Kaggle extensive archive not present")
    df = parse_kaggle_extensive(REAL_KAGGLE_EXTENSIVE)
    assert not bool(df["covered"].any())
    assert df["favorite_side"].isna().all()
    assert df.attrs["unattributed_uncovered_rows"] > 0


def test_consolidate_xval_gate_flags_source_disagreement(tmp_path: Path) -> None:
    from draft_oracle.ingest.odds import XVAL_DELTA_THRESHOLD, _favorite_rows_from_games, _finalize

    # SBR: Toronto a heavy home favorite (implied ~0.77).
    sbr = parse_sbr_workbook_from_rows(
        tmp_path,
        season="2019-20",
        rows=[
            [501, 1, "V", "Boston", 1, 0, 0, 1, 300, 320, 1.5, -130, 6, -110, 6, -115],
            [501, 2, "H", "Toronto", 2, 1, 0, 3, -380, -400, -1.5, 110, 6, -110, 6, -120],
        ],
    )
    # Kaggle: same game (UTC +1 day), calls Toronto a near-even favorite (~0.51).
    kaggle_frame = pd.DataFrame(
        _kaggle_pair(
            game_id=9,
            date="2020-05-02 02:00:00+00:00",
            season=2020,
            home="Toronto Maple Leafs",
            away="Boston Bruins",
            price=-115,
        )
    )
    kaggle = _finalize(_favorite_rows_from_games(kaggle_frame, source=SOURCE_KAGGLE))
    consolidated = consolidate_odds(pd.concat([sbr, kaggle], ignore_index=True))
    assert len(consolidated) == 1
    row = consolidated.iloc[0]
    assert row["source_count"] == 2
    assert row["xval_delta"] > XVAL_DELTA_THRESHOLD
    assert not bool(row["covered"])  # flagged out of covered market probabilities
    assert pd.isna(row["home_implied"])
    assert pd.isna(row["away_implied"])
    assert consolidated.attrs["xval_flagged_rows"] == 1


def test_consolidate_xval_gate_flags_opposite_favorite_sides(tmp_path: Path) -> None:
    from draft_oracle.ingest.odds import (
        XVAL_DELTA_THRESHOLD,
        _favorite_rows_from_games,
        _finalize,
    )

    # SBR makes Toronto the -165 home favorite.
    sbr = parse_sbr_workbook_from_rows(
        tmp_path,
        season="2019-20",
        rows=[
            [501, 1, "V", "Boston", 1, 0, 0, 1, 145, 145, 1.5, -130, 6, -110, 6, -115],
            [501, 2, "H", "Toronto", 2, 1, 0, 3, -165, -165, -1.5, 110, 6, -110, 6, -120],
        ],
    )
    # Kaggle names Boston the -165 away favorite for the same game.
    kaggle_frame = pd.DataFrame(
        [
            {
                "game_id": 9,
                "date": "2020-05-01 02:00:00+00:00",
                "season": 2020,
                "team_name": "Toronto Maple Leafs",
                "is_home": 1,
                "spread": 1.5,
                "favorite_moneyline": -165,
            },
            {
                "game_id": 9,
                "date": "2020-05-01 02:00:00+00:00",
                "season": 2020,
                "team_name": "Boston Bruins",
                "is_home": 0,
                "spread": -1.5,
                "favorite_moneyline": -165,
            },
        ]
    )
    kaggle = _finalize(_favorite_rows_from_games(kaggle_frame, source=SOURCE_KAGGLE))

    consolidated = consolidate_odds(pd.concat([sbr, kaggle], ignore_index=True))

    assert len(consolidated) == 1
    row = consolidated.iloc[0]
    assert row["source_count"] == 2
    assert row["xval_delta"] > XVAL_DELTA_THRESHOLD
    assert not bool(row["covered"])
    assert consolidated.attrs["xval_flagged_rows"] == 1

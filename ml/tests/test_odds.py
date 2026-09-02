"""Unit tests for betting-odds ingestion and de-vigging (US-005).

No test touches the network: live clients are exercised through an
``httpx.MockTransport`` and archive parsers run on small fixtures built in
``tmp_path`` (SPEC §7 - fixtures only). One light real-file smoke test parses a
single committed SBR workbook to guard the count against PROVENANCE.
"""

from __future__ import annotations

import gzip
import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from draft_oracle.ingest.nhl_api import NHLApiError
from draft_oracle.ingest.odds import (
    SOURCE_ESPN_COMPLETION,
    SOURCE_KAGGLE,
    SOURCE_SBR,
    STANDARD_OVERROUND,
    EspnGameOddsClient,
    OddsApiClient,
    american_to_decimal,
    american_to_implied_prob,
    build_odds_table,
    build_source_odds,
    consolidate_odds,
    devig_favorite_only,
    devig_proportional,
    espn_summary_to_rows,
    is_playoff_game,
    is_preseason_game,
    load_archive_game_types,
    load_local_game_dates,
    odds_api_events_to_rows,
    parse_espn_completion,
    parse_kaggle_extensive,
    parse_sbr_archive,
    parse_sbr_workbook,
    resolve_team_id,
)
from draft_oracle.ingest.odds import (
    OddsApiEvent as _OddsApiEvent,
)

REAL_SBR_2016_17 = Path("data/raw/odds-archive/nhl-odds-2016-17.xlsx")
REAL_SBR_2019_20 = Path("data/raw/odds-archive/nhl-odds-2019-20.xlsx")
REAL_KAGGLE_EXTENSIVE = Path(
    "data/raw/odds-archive/kaggle-nhl-historical/nhl_data_extensive.csv.gz"
)


# ── American-odds conversions ────────────────────────────────────────────


def test_american_to_decimal_and_implied() -> None:
    assert american_to_decimal(-150) == pytest.approx(1.6667, abs=1e-4)
    assert american_to_decimal(130) == pytest.approx(2.30, abs=1e-9)
    assert american_to_implied_prob(-200) == pytest.approx(2 / 3, abs=1e-9)
    assert american_to_implied_prob(150) == pytest.approx(0.4, abs=1e-9)


def test_american_odds_reject_zero() -> None:
    with pytest.raises(ValueError):
        american_to_decimal(0)
    with pytest.raises(ValueError):
        american_to_implied_prob(0)


# ── De-vigging math ──────────────────────────────────────────────────────


def test_devig_proportional_sums_to_one_and_removes_overround() -> None:
    result = devig_proportional(home_ml=-200, away_ml=170)
    assert result.home_prob + result.away_prob == pytest.approx(1.0, abs=1e-12)
    # Raw implied sum exceeds 1 (the vig); overround captures it.
    assert result.overround > 1.0
    # Favourite (home) keeps the larger probability.
    assert result.home_prob > result.away_prob
    assert result.method == "proportional"


def test_devig_proportional_preserves_probability_ratio() -> None:
    home_ml, away_ml = -140, 120
    result = devig_proportional(home_ml, away_ml)
    raw_home = american_to_implied_prob(home_ml)
    raw_away = american_to_implied_prob(away_ml)
    assert result.home_prob / result.away_prob == pytest.approx(raw_home / raw_away, abs=1e-9)


def test_devig_favorite_only_uses_standard_overround() -> None:
    result = devig_favorite_only(-150)
    q_fav = american_to_implied_prob(-150)
    assert result.home_prob == pytest.approx(q_fav / STANDARD_OVERROUND, abs=1e-12)
    assert result.home_prob + result.away_prob == pytest.approx(1.0, abs=1e-12)
    assert result.method == "standard_overround"
    # Favourite de-vigged below its raw (vig-inclusive) implied probability.
    assert result.home_prob < q_fav


def test_devig_favorite_only_rejects_bad_overround() -> None:
    with pytest.raises(ValueError):
        devig_favorite_only(-150, overround=0.0)


def test_devig_favorite_only_marginal_favorite_stays_at_least_even() -> None:
    # A -105 favorite's raw implied (~0.512) divided by the standard overround
    # lands just below 0.5, which would invert the sides (CODE_REVIEW m-5). The
    # identified favorite must never de-vig to an underdog.
    for price in (-101, -105, -108, -110):
        result = devig_favorite_only(price)
        assert result.home_prob >= 0.5
        assert result.away_prob <= 0.5
        assert result.home_prob + result.away_prob == pytest.approx(1.0, abs=1e-12)


@given(favorite_ml=st.integers(min_value=-100000, max_value=-100))
def test_devig_favorite_only_property_favorite_never_below_even(
    favorite_ml: int,
) -> None:
    result = devig_favorite_only(favorite_ml)
    assert result.home_prob >= 0.5
    assert result.home_prob <= 1.0
    assert result.home_prob + result.away_prob == pytest.approx(1.0, abs=1e-12)


@given(
    home_ml=st.integers(min_value=-100000, max_value=100000).filter(lambda x: abs(x) >= 100),
    away_ml=st.integers(min_value=-100000, max_value=100000).filter(lambda x: abs(x) >= 100),
)
def test_devig_proportional_probabilities_are_valid(home_ml: int, away_ml: int) -> None:
    result = devig_proportional(home_ml, away_ml)
    assert 0.0 < result.home_prob < 1.0
    assert 0.0 < result.away_prob < 1.0
    assert result.home_prob + result.away_prob == pytest.approx(1.0, abs=1e-9)


# ── Team-name resolution ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Toronto", 10),  # SBR city string (two-word nickname)
        ("Toronto Maple Leafs", 10),  # full name
        ("Columbus", 29),
        ("Detroit", 17),
        ("St.Louis", 19),  # SBR punctuation variant
        ("St. Louis Blues", 19),
        ("LosAngeles", 26),
        ("Los Angeles Kings", 26),
        ("TampaBay", 14),
        ("Tampa", 14),  # 2019-20 typo (PROVENANCE 3.4)
        ("Arizonas", 53),  # 2019-20 typo
        ("NYRangers", 3),
        ("NY Islanders", 2),
        ("Utah Mammoth", 68),
        ("Utah Hockey Club", 59),
        ("Montreal Canadiens", 8),
    ],
)
def test_resolve_team_id(name: str, expected: int) -> None:
    assert resolve_team_id(name) == expected


def test_resolve_team_id_unknown_is_none() -> None:
    assert resolve_team_id("Nonexistent Club") is None
    assert resolve_team_id(None) is None
    assert resolve_team_id("") is None


# ── Playoff windows (PROVENANCE 5) ───────────────────────────────────────


def test_playoff_window_standard_and_special_seasons() -> None:
    # Standard April-June window.
    assert is_playoff_game(2017, date(2017, 5, 1))
    assert not is_playoff_game(2017, date(2017, 2, 1))
    # 2020 bubble ran Aug-Sep (never April-June).
    assert is_playoff_game(2020, date(2020, 8, 15))
    assert not is_playoff_game(2020, date(2020, 4, 15))
    # 2021 late playoffs (May-July).
    assert is_playoff_game(2021, date(2021, 6, 20))


def test_preseason_flag_excludes_bubble() -> None:
    # September is preseason for a normal season...
    assert is_preseason_game(2024, date(2023, 9, 25))
    # ...but the 2020 bubble September games are playoffs, not preseason.
    assert not is_preseason_game(2020, date(2020, 9, 20))


# ── SBR workbook parser ──────────────────────────────────────────────────

_SBR_HEADER = [
    "Date",
    "Rot",
    "VH",
    "Team",
    "1st",
    "2nd",
    "3rd",
    "Final",
    "Open",
    "Close",
    "PuckLine",
    None,
    "OpenOU",
    None,
    "CloseOU",
    None,
]


def _write_sbr_workbook(path: Path, rows: list[list[object]]) -> None:
    frame = pd.DataFrame([_SBR_HEADER, *rows])
    frame.to_excel(path, sheet_name="Sheet1", header=False, index=False)


def test_parse_sbr_workbook_two_sided(tmp_path: Path) -> None:
    wb = tmp_path / "nhl-odds-2016-17.xlsx"
    _write_sbr_workbook(
        wb,
        [
            # Visitor Toronto @ home Ottawa, 12 Oct (regular season).
            [1012, 1, "V", "Toronto", 2, 2, 0, 4, 114, 121, 1.5, -245, 5.5, -110, 5.5, 105],
            [1012, 2, "H", "Ottawa", 2, 1, 1, 5, -134, -141, -1.5, 205, 5.5, -110, 5.5, -125],
            # A playoff game in May.
            [511, 3, "V", "Pittsburgh", 1, 0, 0, 1, 150, 160, 1.5, -130, 5.5, -110, 5.5, 100],
            [511, 4, "H", "Washington", 2, 1, 0, 3, -170, -180, -1.5, 110, 5.5, -110, 5.5, -120],
        ],
    )
    df = parse_sbr_workbook(wb)
    assert len(df) == 2
    assert bool(df["both_sides"].all())
    assert bool(df["covered"].all())
    first = df.iloc[0]
    assert first["away_team_id"] == resolve_team_id("Toronto")
    assert first["home_team_id"] == resolve_team_id("Ottawa")
    assert first["source"] == SOURCE_SBR
    assert first["game_date"] == "2016-10-12"
    assert first["favorite_side"] == "home"  # Ottawa -141 favoured
    assert first["home_implied"] + first["away_implied"] == pytest.approx(1.0, abs=1e-9)
    assert not bool(first["is_playoff"])
    assert bool(df.iloc[1]["is_playoff"])  # 11 May is in the playoff window


def test_parse_sbr_workbook_flags_missing_price(tmp_path: Path) -> None:
    wb = tmp_path / "nhl-odds-2018-19.xlsx"
    _write_sbr_workbook(
        wb,
        [
            [1012, 1, "V", "Boston", 1, 0, 0, 1, "", "", 1.5, -245, 5.5, -110, 5.5, 105],
            [1012, 2, "H", "Buffalo", 0, 1, 0, 1, "", "", -1.5, 205, 5.5, -110, 5.5, -125],
        ],
    )
    df = parse_sbr_workbook(wb)
    assert len(df) == 1
    row = df.iloc[0]
    assert not bool(row["covered"])  # flagged, never imputed
    assert row["home_ml"] is None
    assert row["away_ml"] is None
    assert row["home_implied"] is None
    assert row["favorite_side"] is None


def test_parse_sbr_workbook_reversed_pair_uses_vh(tmp_path: Path) -> None:
    # PROVENANCE 5: one 2019-20 pair lists the home row first; VH must win.
    wb = tmp_path / "nhl-odds-2019-20.xlsx"
    _write_sbr_workbook(
        wb,
        [
            [117, 55, "H", "Pittsburgh", 0, 0, 1, 2, -230, -230, -1.5, 110, 6, -110, 6, -105],
            [117, 56, "V", "Detroit", 0, 1, 0, 1, 192, 205, 1.5, -130, 6, -110, 6, -115],
        ],
    )
    df = parse_sbr_workbook(wb)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["home_team_id"] == resolve_team_id("Pittsburgh")
    assert row["away_team_id"] == resolve_team_id("Detroit")


def test_parse_sbr_real_workbook_smoke() -> None:
    if not REAL_SBR_2016_17.exists():
        pytest.skip("committed SBR workbook not present")
    df = parse_sbr_workbook(REAL_SBR_2016_17)
    # PROVENANCE 5: 2016-17 has 1,317 games, 322 playoff rows (161 games), 100% filled.
    assert len(df) == 1317
    assert bool(df["covered"].all())
    assert int(df["is_playoff"].sum()) == 161


# ── Favorite-only CSV parsers ────────────────────────────────────────────


def _favorite_csv(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _write_gz_csv(path: Path, frame: pd.DataFrame) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        frame.to_csv(handle, index=False)


def test_parse_kaggle_extensive_favorite_only(tmp_path: Path) -> None:
    frame = _favorite_csv(
        [
            # Home Carolina favoured (home spread negative), away Vegas.
            {
                "game_id": 1,
                "date": "2026-05-01 00:00:00+00:00",
                "season": 2026,
                "team_name": "Carolina Hurricanes",
                "is_home": 1,
                "spread": -1.5,
                "favorite_moneyline": -160,
            },
            {
                "game_id": 1,
                "date": "2026-05-01 00:00:00+00:00",
                "season": 2026,
                "team_name": "Vegas Golden Knights",
                "is_home": 0,
                "spread": 1.5,
                "favorite_moneyline": -160,
            },
            # Preseason September row -> dropped.
            {
                "game_id": 2,
                "date": "2025-09-25 00:00:00+00:00",
                "season": 2026,
                "team_name": "Boston Bruins",
                "is_home": 1,
                "spread": -1.5,
                "favorite_moneyline": -120,
            },
            {
                "game_id": 2,
                "date": "2025-09-25 00:00:00+00:00",
                "season": 2026,
                "team_name": "Buffalo Sabres",
                "is_home": 0,
                "spread": 1.5,
                "favorite_moneyline": -120,
            },
        ]
    )
    path = tmp_path / "nhl_data_extensive.csv.gz"
    _write_gz_csv(path, frame)
    df = parse_kaggle_extensive(path)
    assert len(df) == 1  # preseason dropped
    row = df.iloc[0]
    assert row["source"] == SOURCE_KAGGLE
    assert not bool(row["both_sides"])
    assert row["favorite_side"] == "home"
    assert row["home_ml"] == -160
    assert row["away_ml"] is None  # underdog price never fabricated
    assert row["home_implied"] > row["away_implied"]
    assert row["home_implied"] + row["away_implied"] == pytest.approx(1.0, abs=1e-9)
    assert bool(row["is_playoff"])  # 1 May 2026 is in the playoff window


def test_parse_espn_completion_home_relative_spread(tmp_path: Path) -> None:
    frame = _favorite_csv(
        [
            # Home Vegas underdog (spread +1.5) -> favourite is away Carolina.
            {
                "game_id": 401874176,
                "date": "2026-06-15 00:00:00+00:00",
                "season": 2026,
                "team_name": "Vegas Golden Knights",
                "is_home": 1,
                "spread": 1.5,
                "favorite_moneyline": -115,
            },
            {
                "game_id": 401874176,
                "date": "2026-06-15 00:00:00+00:00",
                "season": 2026,
                "team_name": "Carolina Hurricanes",
                "is_home": 0,
                "spread": 1.5,
                "favorite_moneyline": -115,
            },
        ]
    )
    path = tmp_path / "games.csv"
    frame.to_csv(path, index=False)
    df = parse_espn_completion(path)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["source"] == SOURCE_ESPN_COMPLETION
    assert row["favorite_side"] == "away"  # Carolina favoured
    assert row["away_ml"] == -115
    assert row["home_ml"] is None
    assert row["away_implied"] > row["home_implied"]


def test_parse_espn_completion_missing_favorite_signal_is_uncovered(
    tmp_path: Path,
) -> None:
    frame = _favorite_csv(
        [
            {
                "game_id": 401874176,
                "date": "2026-06-15 00:00:00+00:00",
                "season": 2026,
                "team_name": "Vegas Golden Knights",
                "is_home": 1,
                "spread": float("nan"),
                "favorite_moneyline": -115,
            },
            {
                "game_id": 401874176,
                "date": "2026-06-15 00:00:00+00:00",
                "season": 2026,
                "team_name": "Carolina Hurricanes",
                "is_home": 0,
                "spread": float("nan"),
                "favorite_moneyline": -115,
            },
        ]
    )
    path = tmp_path / "games.csv"
    frame.to_csv(path, index=False)

    df = parse_espn_completion(path)

    assert len(df) == 1
    row = df.iloc[0]
    assert not bool(row["covered"])
    assert row["favorite_side"] is None
    assert row["home_implied"] is None
    assert row["away_implied"] is None
    assert df.attrs["unattributed_uncovered_rows"] == 1


def test_parse_kaggle_extensive_unattributed_when_spreads_identical(
    tmp_path: Path,
) -> None:
    # CODE_REVIEW C-1: the real Kaggle archive stamps a single game-level spread
    # on BOTH rows (identical sign), so the home-row spread encodes no favorite.
    # Genuine, varied prices (not a placeholder) must be emitted unattributed
    # (covered=False) rather than guessed as home.
    frame = _favorite_csv(
        [
            {
                "game_id": 1,
                "date": "2022-05-01 00:00:00+00:00",
                "season": 2022,
                "team_name": "Carolina Hurricanes",
                "is_home": 1,
                "spread": -1.5,  # identical on both rows -> no favorite signal
                "favorite_moneyline": -160,
            },
            {
                "game_id": 1,
                "date": "2022-05-01 00:00:00+00:00",
                "season": 2022,
                "team_name": "Vegas Golden Knights",
                "is_home": 0,
                "spread": -1.5,
                "favorite_moneyline": -160,
            },
        ]
    )
    path = tmp_path / "nhl_data_extensive.csv.gz"
    _write_gz_csv(path, frame)
    df = parse_kaggle_extensive(path)
    assert len(df) == 1  # kept, never silently dropped
    row = df.iloc[0]
    assert not bool(row["covered"])
    assert row["favorite_side"] is None
    assert row["home_ml"] is None
    assert row["away_ml"] is None
    assert df.attrs["unattributed_uncovered_rows"] == 1
    assert df.attrs["placeholder_uncovered_rows"] == 0


def test_parse_espn_completion_reads_favorite_from_raw_summary(
    tmp_path: Path,
) -> None:
    # CODE_REVIEW C-1: the authoritative favorite comes from the raw ESPN
    # summary's homeTeamOdds.favorite flag, which here contradicts the CSV
    # spread sign (home spread -1.5 would guess "home"). The summary wins.
    frame = _favorite_csv(
        [
            {
                "game_id": 401999001,
                "date": "2026-06-15 00:00:00+00:00",
                "season": 2026,
                "team_name": "Florida Panthers",
                "is_home": 1,
                "spread": -1.5,  # spread would guess home favorite
                "favorite_moneyline": -160,
            },
            {
                "game_id": 401999001,
                "date": "2026-06-15 00:00:00+00:00",
                "season": 2026,
                "team_name": "Edmonton Oilers",
                "is_home": 0,
                "spread": 1.5,
                "favorite_moneyline": -160,
            },
        ]
    )
    path = tmp_path / "games.csv"
    frame.to_csv(path, index=False)
    summary_dir = tmp_path / "raw" / "summary"
    summary_dir.mkdir(parents=True)
    summary = {
        "pickcenter": [
            {
                "homeTeamOdds": {"favorite": False},
                "awayTeamOdds": {"favorite": True},
            }
        ]
    }
    with gzip.open(summary_dir / "401999001.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(summary, handle)

    df = parse_espn_completion(path)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["favorite_side"] == "away"  # summary overrides the spread guess
    assert row["away_ml"] == -160
    assert row["home_ml"] is None
    assert row["away_implied"] > row["home_implied"]


# ── Consolidation ────────────────────────────────────────────────────────


def _two_sided_frame_row(**kwargs: object) -> dict[str, object]:
    return kwargs


def test_consolidate_prefers_sbr_and_cross_validates() -> None:
    # Same game from SBR (two-sided) and Kaggle (favorite-only, UTC +1 day).
    sbr = parse_sbr_workbook_from_rows(
        season="2019-20",
        rows=[
            [501, 1, "V", "Boston", 1, 0, 0, 1, 150, 160, 1.5, -130, 6, -110, 6, -115],
            [501, 2, "H", "Toronto", 2, 1, 0, 3, -170, -180, -1.5, 110, 6, -110, 6, -120],
        ],
    )
    kaggle_frame = pd.DataFrame(
        [
            {
                "game_id": 9,
                "date": "2020-05-02 02:00:00+00:00",
                "season": 2020,
                "team_name": "Toronto Maple Leafs",
                "is_home": 1,
                "spread": -1.5,
                "favorite_moneyline": -175,
            },
            {
                "game_id": 9,
                "date": "2020-05-02 02:00:00+00:00",
                "season": 2020,
                "team_name": "Boston Bruins",
                "is_home": 0,
                "spread": 1.5,
                "favorite_moneyline": -175,
            },
        ]
    )
    from draft_oracle.ingest.odds import _favorite_rows_from_games, _finalize

    kaggle = _finalize(_favorite_rows_from_games(kaggle_frame, source=SOURCE_KAGGLE))
    combined = pd.concat([sbr, kaggle], ignore_index=True)
    consolidated = consolidate_odds(combined)
    assert len(consolidated) == 1  # the two sources collapse to one game
    row = consolidated.iloc[0]
    assert row["source"] == SOURCE_SBR  # SBR preferred
    assert bool(row["both_sides"])
    assert row["source_count"] == 2
    assert row["xval_delta"] >= 0.0


def parse_sbr_workbook_from_rows(season: str, rows: list[list[object]]) -> pd.DataFrame:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"nhl-odds-{season}.xlsx"
        _write_sbr_workbook(path, rows)
        return parse_sbr_workbook(path)


def test_consolidate_keeps_adjacent_distinct_games_separate() -> None:
    # Same matchup on two consecutive days (back-to-back) must NOT merge.
    sbr = parse_sbr_workbook_from_rows(
        season="2016-17",
        rows=[
            [101, 1, "V", "Boston", 1, 0, 0, 1, 150, 160, 1.5, -130, 6, -110, 6, -115],
            [101, 2, "H", "Toronto", 2, 1, 0, 3, -170, -180, -1.5, 110, 6, -110, 6, -120],
            [102, 3, "V", "Boston", 1, 0, 0, 1, 140, 150, 1.5, -130, 6, -110, 6, -115],
            [102, 4, "H", "Toronto", 2, 1, 0, 3, -160, -170, -1.5, 110, 6, -110, 6, -120],
        ],
    )
    consolidated = consolidate_odds(sbr)
    assert len(consolidated) == 2  # both games survive


def test_consolidate_empty_frame() -> None:
    empty = build_source_odds(Path("nonexistent-dir"))
    assert empty.empty
    out = consolidate_odds(empty)
    assert out.empty
    assert "xval_delta" in out.columns


# ── Local-date normalization for the market join (CODE_REVIEW M-2) ────────


def test_consolidate_snaps_utc_date_to_local() -> None:
    """A Kaggle UTC calendar date is snapped to the archive local date (M-2)."""
    from draft_oracle.ingest.odds import _favorite_rows_from_games, _finalize

    kaggle = _finalize(
        _favorite_rows_from_games(
            pd.DataFrame(_kaggle_pair(game_id=1, date="2024-05-02 02:00:00+00:00",
                                      season=2024, home="Toronto Maple Leafs",
                                      away="Boston Bruins", price=-175)),
            source=SOURCE_KAGGLE,
        )
    )
    home_id = resolve_team_id("Toronto Maple Leafs")
    away_id = resolve_team_id("Boston Bruins")
    assert home_id is not None and away_id is not None
    # Archive stamps the game one local day earlier than the UTC-stamped odds row.
    local_dates = {(2024, home_id, away_id): (date(2024, 5, 1),)}
    consolidated = consolidate_odds(kaggle, local_game_dates=local_dates)
    row = consolidated.iloc[0]
    assert row["game_date"] == "2024-05-01"  # snapped from UTC 2024-05-02
    assert row["game_key"].startswith("2024:2024-05-01:")


def test_consolidate_keeps_exact_local_date_untouched() -> None:
    """A row already on a local date is not moved (single convention, no churn)."""
    from draft_oracle.ingest.odds import _favorite_rows_from_games, _finalize

    kaggle = _finalize(
        _favorite_rows_from_games(
            pd.DataFrame(_kaggle_pair(game_id=1, date="2024-05-01 18:00:00+00:00",
                                      season=2024, home="Toronto Maple Leafs",
                                      away="Boston Bruins", price=-175)),
            source=SOURCE_KAGGLE,
        )
    )
    home_id = resolve_team_id("Toronto Maple Leafs")
    away_id = resolve_team_id("Boston Bruins")
    assert home_id is not None and away_id is not None
    local_dates = {(2024, home_id, away_id): (date(2024, 5, 1),)}
    consolidated = consolidate_odds(kaggle, local_game_dates=local_dates)
    assert consolidated.iloc[0]["game_date"] == "2024-05-01"


def test_consolidate_no_snap_when_no_archive_match() -> None:
    """No nearby archive game (>1 day) leaves the source date untouched."""
    from draft_oracle.ingest.odds import _favorite_rows_from_games, _finalize

    kaggle = _finalize(
        _favorite_rows_from_games(
            pd.DataFrame(_kaggle_pair(game_id=1, date="2024-05-02 02:00:00+00:00",
                                      season=2024, home="Toronto Maple Leafs",
                                      away="Boston Bruins", price=-175)),
            source=SOURCE_KAGGLE,
        )
    )
    home_id = resolve_team_id("Toronto Maple Leafs")
    away_id = resolve_team_id("Boston Bruins")
    assert home_id is not None and away_id is not None
    local_dates = {(2024, home_id, away_id): (date(2024, 1, 1),)}  # far away
    consolidated = consolidate_odds(kaggle, local_game_dates=local_dates)
    assert consolidated.iloc[0]["game_date"] == "2024-05-02"  # unchanged


def test_load_local_game_dates_indexes_home_away(tmp_path: Path) -> None:
    archive = tmp_path / "nhl-archive"
    archive.mkdir()
    frame = pd.DataFrame(
        [
            {"seasonId": 20232024, "gameId": 111, "teamId": 10, "homeRoad": "H",
             "gameDate": "2024-05-01"},
            {"seasonId": 20232024, "gameId": 111, "teamId": 6, "homeRoad": "R",
             "gameDate": "2024-05-01"},
        ]
    )
    frame.to_csv(archive / "team-games-2023-24.csv.gz", index=False, compression="gzip")
    index = load_local_game_dates(archive)
    assert index[(2024, 10, 6)] == (date(2024, 5, 1),)


def test_market_join_attaches_genuine_covered_odds() -> None:
    """CODE_REVIEW M-2: normalized odds dates attach covered prices to games.

    Builds the covered odds (SBR + ESPN completion - the only genuinely-priced
    sources for 2023-2026 after the C-2 placeholder guard) and the NHL-archive
    game frame from committed data, then asserts that >=95% of covered odds rows
    that identify a real archive game (a matchup within +-1 day) attach through
    ``_attach_market``'s exact-date join. The no-normalization control proves the
    fix is what closes the gap (UTC dates otherwise drop most of them).
    """
    from draft_oracle.ingest.normalize import (
        DEFAULT_ARCHIVE_DIR,
        load_archive_team_games,
        normalize_team_games,
    )
    from draft_oracle.ingest.odds import DEFAULT_ODDS_ARCHIVE_DIR
    from draft_oracle.models.game_win import _attach_market, _pivot_games

    seasons = [2023, 2024, 2025, 2026]
    sbr = parse_sbr_archive(DEFAULT_ODDS_ARCHIVE_DIR)
    espn = parse_espn_completion(
        DEFAULT_ODDS_ARCHIVE_DIR / "espn-2025-26-completion" / "games.csv"
    )
    source = pd.concat([sbr, espn], ignore_index=True)

    labels = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
    team_games = normalize_team_games(load_archive_team_games(DEFAULT_ARCHIVE_DIR, labels))
    games = _pivot_games(team_games)
    games["season_end_year"] = games["season_end_year"].astype(int)

    # Same-matchup archive dates, keyed home/away, for the "genuine" filter.
    archive_dates: dict[tuple[int, int, int], list[pd.Timestamp]] = {}
    a_season = games["season_end_year"].astype(int).tolist()
    a_home = games["home_team_id"].astype(int).tolist()
    a_away = games["away_team_id"].astype(int).tolist()
    a_date = pd.to_datetime(games["game_date"]).tolist()
    for season, home_id, away_id, when in zip(a_season, a_home, a_away, a_date, strict=True):
        archive_dates.setdefault((int(season), int(home_id), int(away_id)), []).append(
            pd.Timestamp(when)
        )

    def attach_rate(odds: pd.DataFrame) -> tuple[int, float]:
        odds = odds.copy()
        odds["season_end_year"] = odds["season_end_year"].astype(int)
        covered = odds.loc[odds["covered"] & odds["season_end_year"].isin(seasons)].copy()
        covered["game_date"] = pd.to_datetime(covered["game_date"])
        joined = _attach_market(games, odds)
        joined["season_end_year"] = joined["season_end_year"].astype(int)
        hit = joined.loc[
            :, ["season_end_year", "game_date", "home_team_id", "away_team_id"]
        ].copy()
        hit["_hit"] = joined["market_home_prob"].notna()
        merged = covered.merge(
            hit, on=["season_end_year", "game_date", "home_team_id", "away_team_id"], how="left"
        )
        merged["_hit"] = merged["_hit"].fillna(value=False)
        genuine_mask = [
            any(
                abs((gd - ad).days) <= 1
                for ad in archive_dates.get((int(sy), int(hid), int(aid)), [])
            )
            for sy, gd, hid, aid in zip(
                merged["season_end_year"],
                merged["game_date"],
                merged["home_team_id"],
                merged["away_team_id"],
                strict=True,
            )
        ]
        genuine = merged.loc[genuine_mask]
        return len(genuine), float(genuine["_hit"].mean())

    local_dates = load_local_game_dates(DEFAULT_ARCHIVE_DIR)
    normalized = consolidate_odds(source, local_game_dates=local_dates)
    n_genuine, rate = attach_rate(normalized)
    assert n_genuine > 500  # a substantial covered universe is exercised
    assert rate >= 0.95, f"only {rate:.3f} of genuine covered odds attached"

    _, control_rate = attach_rate(consolidate_odds(source))  # no normalization
    assert control_rate < rate  # the local-date fix is what closes the gap


# ── Playoff labeling by gameTypeId (CODE_REVIEW M-4, m-12) ────────────────


def test_load_archive_game_types_indexes_gametypeid(tmp_path: Path) -> None:
    """The loader maps each matchup date to its archive gameTypeId, both ways."""
    archive = tmp_path / "nhl-archive"
    archive.mkdir()
    frame = pd.DataFrame(
        [
            {"seasonId": 20212022, "gameTypeId": 2, "gameId": 111, "teamId": 10,
             "homeRoad": "H", "gameDate": "2022-04-29"},
            {"seasonId": 20212022, "gameTypeId": 2, "gameId": 111, "teamId": 6,
             "homeRoad": "R", "gameDate": "2022-04-29"},
            {"seasonId": 20212022, "gameTypeId": 3, "gameId": 222, "teamId": 10,
             "homeRoad": "H", "gameDate": "2022-05-10"},
            {"seasonId": 20212022, "gameTypeId": 3, "gameId": 222, "teamId": 6,
             "homeRoad": "R", "gameDate": "2022-05-10"},
        ]
    )
    frame.to_csv(archive / "team-games-2021-22.csv.gz", index=False, compression="gzip")
    index = load_archive_game_types(archive)
    assert index[(2022, 10, 6)][date(2022, 4, 29)] == 2
    assert index[(2022, 10, 6)][date(2022, 5, 10)] == 3
    # Stored in both orientations so a reversed odds row still resolves.
    assert index[(2022, 6, 10)][date(2022, 5, 10)] == 3


def _sbr_late_april_regular(*, home: str, away: str, price: int) -> list[dict[str, object]]:
    """A late-April (post Apr-1) two-sided SBR-style row for season 2022."""
    from draft_oracle.ingest.odds import _two_sided_row

    home_id = resolve_team_id(home)
    away_id = resolve_team_id(away)
    assert home_id is not None and away_id is not None
    return [
        _two_sided_row(
            source=SOURCE_SBR,
            season_end_year=2022,
            game_date=date(2022, 4, 29),
            away_id=away_id,
            home_id=home_id,
            away_name=away,
            home_name=home,
            away_ml=float(-price + 20),
            home_ml=float(price),
            neutral=False,
        )
    ]


def test_consolidate_labels_late_april_regular_as_non_playoff() -> None:
    """A 29 April regular-season game (inside the old April window) is not playoff."""
    from draft_oracle.ingest.odds import _finalize

    source = _finalize(
        _sbr_late_april_regular(home="Toronto Maple Leafs", away="Boston Bruins", price=-140)
    )
    # The fixed-window heuristic mislabels it (April 29 > April 1 window start).
    assert bool(source.iloc[0]["is_playoff"]) is True

    home_id = resolve_team_id("Toronto Maple Leafs")
    away_id = resolve_team_id("Boston Bruins")
    assert home_id is not None and away_id is not None
    dates = {(2022, home_id, away_id): (date(2022, 4, 29),)}
    types = {(2022, home_id, away_id): {date(2022, 4, 29): 2}}
    out = consolidate_odds(source, local_game_dates=dates, local_game_types=types)
    row = out.iloc[0]
    assert bool(row["is_playoff"]) is False  # archive gameTypeId=2 wins
    assert bool(row["covered"]) is True


def test_consolidate_labels_playoff_from_gametypeid() -> None:
    """An archive gameTypeId=3 game is flagged is_playoff even out of window."""
    from draft_oracle.ingest.odds import _finalize, _two_sided_row

    home_id = resolve_team_id("Toronto Maple Leafs")
    away_id = resolve_team_id("Boston Bruins")
    assert home_id is not None and away_id is not None
    source = _finalize(
        [
            _two_sided_row(
                source=SOURCE_SBR,
                season_end_year=2022,
                game_date=date(2022, 5, 10),
                away_id=away_id,
                home_id=home_id,
                away_name="Boston Bruins",
                home_name="Toronto Maple Leafs",
                away_ml=120.0,
                home_ml=-140.0,
                neutral=False,
            )
        ]
    )
    dates = {(2022, home_id, away_id): (date(2022, 5, 10),)}
    types = {(2022, home_id, away_id): {date(2022, 5, 10): 3}}
    out = consolidate_odds(source, local_game_dates=dates, local_game_types=types)
    assert bool(out.iloc[0]["is_playoff"]) is True


def test_consolidate_excludes_rows_with_no_archive_game() -> None:
    """A priced row absent from the archive (e.g. preseason) is flagged uncovered."""
    from draft_oracle.ingest.odds import _finalize, _two_sided_row

    home_id = resolve_team_id("Toronto Maple Leafs")
    away_id = resolve_team_id("Boston Bruins")
    assert home_id is not None and away_id is not None
    source = _finalize(
        [
            _two_sided_row(
                source=SOURCE_SBR,
                season_end_year=2022,
                game_date=date(2021, 10, 3),  # early-October preseason
                away_id=away_id,
                home_id=home_id,
                away_name="Boston Bruins",
                home_name="Toronto Maple Leafs",
                away_ml=120.0,
                home_ml=-140.0,
                neutral=False,
            )
        ]
    )
    # No archive game covers this matchup date -> excluded, kept, counted.
    out = consolidate_odds(source, local_game_types={})
    assert len(out) == 1  # not dropped silently
    assert out.attrs["unmatched_uncovered_rows"] == 0  # empty index = no labeling

    types: dict[tuple[int, int, int], dict[date, int]] = {(2022, home_id, away_id): {}}
    out = consolidate_odds(source, local_game_types=types)
    row = out.iloc[0]
    assert row["is_playoff"] is None
    assert bool(row["covered"]) is False
    assert row["home_implied"] is None
    assert out.attrs["unmatched_uncovered_rows"] == 1


def test_consolidate_counts_real_reversed_orientation_as_unjoinable() -> None:
    """The documented 2020 PIT/DET SBR row cannot attach in its recorded orientation."""
    from draft_oracle.ingest.normalize import DEFAULT_ARCHIVE_DIR

    sbr = parse_sbr_workbook(REAL_SBR_2019_20)
    pit = resolve_team_id("Pittsburgh Penguins")
    det = resolve_team_id("Detroit Red Wings")
    assert pit is not None and det is not None
    flipped = sbr.loc[
        (sbr["game_date"] == "2020-01-17")
        & (sbr["home_team_id"] == pit)
        & (sbr["away_team_id"] == det)
    ]
    assert len(flipped) == 1

    dates = load_local_game_dates(DEFAULT_ARCHIVE_DIR)
    types = load_archive_game_types(DEFAULT_ARCHIVE_DIR)
    assert date(2020, 1, 17) not in dates.get((2020, pit, det), ())
    assert date(2020, 1, 17) in dates[(2020, det, pit)]

    out = consolidate_odds(flipped, local_game_dates=dates, local_game_types=types)

    assert len(out) == 1
    assert not bool(out.iloc[0]["covered"])
    assert out.attrs["unmatched_uncovered_rows"] == 1
    assert out.attrs["orientation_unmatched_rows"] == 1


def test_playoff_labels_match_committed_archive_gametypeid() -> None:
    """CODE_REVIEW M-4/m-12 against committed data: labels follow gameTypeId.

    Builds the covered odds universe (SBR + ESPN completion) and the archive
    gameTypeId index from committed files, consolidates with archive labeling,
    then asserts NO regular-season (gameTypeId=2) game is flagged is_playoff and
    NO playoff (gameTypeId=3) game is flagged non-playoff. The fixed-window
    control demonstrates the mislabels the join removes, and every covered row
    resolves to a real archive game (closing the preseason leak).
    """
    from draft_oracle.ingest.normalize import DEFAULT_ARCHIVE_DIR
    from draft_oracle.ingest.odds import DEFAULT_ODDS_ARCHIVE_DIR, _lookup_game_type

    sbr = parse_sbr_archive(DEFAULT_ODDS_ARCHIVE_DIR)
    espn = parse_espn_completion(
        DEFAULT_ODDS_ARCHIVE_DIR / "espn-2025-26-completion" / "games.csv"
    )
    source = pd.concat([sbr, espn], ignore_index=True)
    dates = load_local_game_dates(DEFAULT_ARCHIVE_DIR)
    types = load_archive_game_types(DEFAULT_ARCHIVE_DIR)

    out = consolidate_odds(source, local_game_dates=dates, local_game_types=types)

    def archive_type(row: pd.Series) -> int | None:
        parsed = date.fromisoformat(str(row["game_date"]))
        return _lookup_game_type(
            types,
            int(row["season_end_year"]),
            int(row["home_team_id"]),
            int(row["away_team_id"]),
            parsed,
        )

    wrong_regular = 0
    wrong_playoff = 0
    for _, row in out.iterrows():
        type_id = archive_type(row)
        if type_id is None:
            continue
        flagged = bool(row["is_playoff"])
        if type_id == 2 and flagged:
            wrong_regular += 1
        if type_id == 3 and not flagged:
            wrong_playoff += 1
    assert wrong_regular == 0, f"{wrong_regular} regular-season games flagged playoff"
    assert wrong_playoff == 0, f"{wrong_playoff} playoff games flagged non-playoff"

    # Control: the fixed April windows DO mislabel regular-season games as playoff.
    old = consolidate_odds(source, local_game_dates=dates)
    old_wrong = 0
    for _, row in old.iterrows():
        if archive_type(row) == 2 and bool(row["is_playoff"]):
            old_wrong += 1
    assert old_wrong > 0, "control must reproduce the fixed-window mislabels"

    # Preseason leak (m-12): every covered row resolves to a real archive game.
    covered = out.loc[out["covered"].astype(bool)]
    unmatched_covered = sum(1 for _, row in covered.iterrows() if archive_type(row) is None)
    assert unmatched_covered == 0, f"{unmatched_covered} covered rows have no archive game"


# ── Placeholder guard + xval gate (CODE_REVIEW C-2) ──────────────────────


def _kaggle_pair(
    *, game_id: int, date: str, season: int, home: str, away: str, price: object
) -> list[dict[str, object]]:
    return [
        {
            "game_id": game_id,
            "date": date,
            "season": season,
            "team_name": home,
            "is_home": 1,
            "spread": -1.5,
            "favorite_moneyline": price,
        },
        {
            "game_id": game_id,
            "date": date,
            "season": season,
            "team_name": away,
            "is_home": 0,
            "spread": 1.5,
            "favorite_moneyline": price,
        },
    ]


_KAGGLE_MATCHUPS = [
    ("Boston Bruins", "Toronto Maple Leafs"),
    ("Carolina Hurricanes", "Vegas Golden Knights"),
    ("Colorado Avalanche", "Dallas Stars"),
    ("Edmonton Oilers", "Calgary Flames"),
    ("Florida Panthers", "Tampa Bay Lightning"),
    ("Los Angeles Kings", "Anaheim Ducks"),
    ("Minnesota Wild", "Winnipeg Jets"),
    ("Nashville Predators", "St. Louis Blues"),
    ("New York Rangers", "New Jersey Devils"),
    ("Ottawa Senators", "Montreal Canadiens"),
]


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
    for i, ((home, away), price) in enumerate(
        zip(_KAGGLE_MATCHUPS, prices, strict=True), start=1
    ):
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
    for i, ((home, away), price) in enumerate(
        zip(_KAGGLE_MATCHUPS, prices, strict=True), start=1
    ):
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
    ph_dates = pd.to_datetime(
        y2026.loc[y2026["fm"] == -105.0, "date"], utc=True, errors="coerce"
    )
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


def test_consolidate_xval_gate_flags_source_disagreement() -> None:
    from draft_oracle.ingest.odds import XVAL_DELTA_THRESHOLD, _favorite_rows_from_games, _finalize

    # SBR: Toronto a heavy home favorite (implied ~0.77).
    sbr = parse_sbr_workbook_from_rows(
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


def test_consolidate_xval_gate_flags_opposite_favorite_sides() -> None:
    from draft_oracle.ingest.odds import (
        XVAL_DELTA_THRESHOLD,
        _favorite_rows_from_games,
        _finalize,
    )

    # SBR makes Toronto the -165 home favorite.
    sbr = parse_sbr_workbook_from_rows(
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


# ── build_odds_table (Parquet round-trip) ────────────────────────────────


def test_build_odds_table_writes_parquet(tmp_path: Path) -> None:
    archive = tmp_path / "odds-archive"
    archive.mkdir()
    _write_sbr_workbook(
        archive / "nhl-odds-2016-17.xlsx",
        [
            [1012, 1, "V", "Toronto", 2, 2, 0, 4, 114, 121, 1.5, -245, 5.5, -110, 5.5, 105],
            [1012, 2, "H", "Ottawa", 2, 1, 1, 5, -134, -141, -1.5, 205, 5.5, -110, 5.5, -125],
        ],
    )
    out = tmp_path / "normalized"
    result = build_odds_table(archive_dir=archive, out_dir=out)
    assert result.game_rows == 1
    assert result.covered_rows == 1
    assert (out / "odds.parquet").exists()
    assert (out / "odds_by_source.parquet").exists()
    loaded = pd.read_parquet(out / "odds.parquet")
    assert len(loaded) == 1
    assert loaded.iloc[0]["home_team_id"] == resolve_team_id("Ottawa")


def test_build_odds_table_reports_unattributed_rows(tmp_path: Path) -> None:
    archive = tmp_path / "odds-archive"
    completion = archive / "espn-2025-26-completion"
    completion.mkdir(parents=True)
    frame = _favorite_csv(
        [
            {
                "game_id": 401874176,
                "date": "2026-06-15 00:00:00+00:00",
                "season": 2026,
                "team_name": "Vegas Golden Knights",
                "is_home": 1,
                "spread": float("nan"),
                "favorite_moneyline": -115,
            },
            {
                "game_id": 401874176,
                "date": "2026-06-15 00:00:00+00:00",
                "season": 2026,
                "team_name": "Carolina Hurricanes",
                "is_home": 0,
                "spread": float("nan"),
                "favorite_moneyline": -115,
            },
        ]
    )
    frame.to_csv(completion / "games.csv", index=False)

    result = build_odds_table(archive_dir=archive, out_dir=tmp_path / "normalized")

    assert result.unattributed_uncovered_rows == 1


# ── Live: The Odds API (MockTransport, no network) ───────────────────────


def _noop_sleep(_seconds: float) -> None:
    return None


def _odds_api_payload() -> list[dict[str, object]]:
    return [
        {
            "id": "evt1",
            "commence_time": "2026-05-01T23:00:00Z",
            "home_team": "Carolina Hurricanes",
            "away_team": "Vegas Golden Knights",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Carolina Hurricanes", "price": -160},
                                {"name": "Vegas Golden Knights", "price": 140},
                            ],
                        }
                    ],
                }
            ],
        }
    ]


def test_odds_api_client_fetches_and_captures_quota(tmp_path: Path) -> None:
    calls: list[int] = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        calls[0] += 1
        assert "apiKey=secret" in str(request.url)
        return httpx.Response(
            200,
            json=_odds_api_payload(),
            headers={"x-requests-remaining": "480", "x-requests-used": "20"},
        )

    client = OddsApiClient(
        cache_dir=tmp_path / "cache",
        api_key="secret",
        delay=0.0,
        retry_backoff=0.0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=_noop_sleep,
    )
    events = client.nhl_odds()
    assert len(events) == 1
    assert client.requests_remaining == 480
    assert client.requests_used == 20
    # Second call is served from cache -> no extra network hit.
    client.nhl_odds()
    assert calls[0] == 1
    client.close()


def test_odds_api_client_requires_key(tmp_path: Path) -> None:
    client = OddsApiClient(
        cache_dir=tmp_path / "cache",
        api_key="",
        delay=0.0,
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[]))),
        sleep=_noop_sleep,
    )
    with pytest.raises(NHLApiError):
        client.nhl_odds()
    client.close()


def test_odds_api_events_to_rows_devigs() -> None:
    events = [_OddsApiEvent.model_validate(item) for item in _odds_api_payload()]
    df = odds_api_events_to_rows(events)
    assert len(df) == 1
    row = df.iloc[0]
    assert bool(row["both_sides"])
    assert row["home_team_id"] == resolve_team_id("Carolina Hurricanes")
    assert row["home_implied"] + row["away_implied"] == pytest.approx(1.0, abs=1e-9)
    assert row["favorite_side"] == "home"


def test_odds_api_events_missing_market_flagged() -> None:
    payload = _odds_api_payload()
    payload[0]["bookmakers"] = []  # no prices
    events = [_OddsApiEvent.model_validate(item) for item in payload]
    df = odds_api_events_to_rows(events)
    assert len(df) == 1
    assert not bool(df.iloc[0]["covered"])  # flagged, not imputed


# ── Live: ESPN summary (MockTransport + payload conversion) ──────────────


def _espn_summary_payload(favorite_home: bool) -> dict[str, Any]:
    spread = -1.5 if favorite_home else 1.5
    return {
        "header": {
            "competitions": [
                {
                    "date": "2026-05-01T23:00:00Z",
                    "competitors": [
                        {"homeAway": "home", "team": {"displayName": "Carolina Hurricanes"}},
                        {"homeAway": "away", "team": {"displayName": "Vegas Golden Knights"}},
                    ],
                }
            ]
        },
        "pickcenter": [
            {
                "spread": spread,
                "homeTeamOdds": {"favorite": favorite_home, "moneyLine": -160},
                "awayTeamOdds": {"favorite": not favorite_home, "moneyLine": -160},
            }
        ],
    }


def test_espn_summary_to_rows_home_favorite() -> None:
    df = espn_summary_to_rows(_espn_summary_payload(favorite_home=True))
    assert len(df) == 1
    row = df.iloc[0]
    assert row["favorite_side"] == "home"
    assert not bool(row["both_sides"])
    assert row["home_implied"] > row["away_implied"]


def test_espn_summary_to_rows_missing_pickcenter_flagged() -> None:
    payload = _espn_summary_payload(favorite_home=True)
    payload["pickcenter"] = []
    df = espn_summary_to_rows(payload)
    assert len(df) == 1
    assert not bool(df.iloc[0]["covered"])


@pytest.mark.parametrize("spread", [None, ""])
def test_espn_summary_to_rows_missing_spread_and_flags_is_unattributed(
    spread: object,
) -> None:
    payload = _espn_summary_payload(favorite_home=True)
    pickcenter = payload["pickcenter"][0]
    pickcenter["spread"] = spread
    pickcenter["homeTeamOdds"]["favorite"] = False
    pickcenter["awayTeamOdds"]["favorite"] = False
    pickcenter["moneyLine"] = -160

    row = espn_summary_to_rows(payload).iloc[0]

    assert row["favorite_side"] is None
    assert not bool(row["covered"])


def test_espn_summary_to_rows_omitted_spread_and_flags_is_unattributed() -> None:
    payload = _espn_summary_payload(favorite_home=True)
    pickcenter = payload["pickcenter"][0]
    del pickcenter["spread"]
    pickcenter["homeTeamOdds"]["favorite"] = False
    pickcenter["awayTeamOdds"]["favorite"] = False
    pickcenter["moneyLine"] = -160

    row = espn_summary_to_rows(payload).iloc[0]

    assert row["favorite_side"] is None
    assert not bool(row["covered"])


def test_espn_summary_to_rows_favorite_flag_overrides_spread() -> None:
    payload = _espn_summary_payload(favorite_home=True)
    pickcenter = payload["pickcenter"][0]
    pickcenter["spread"] = 1.5

    row = espn_summary_to_rows(payload).iloc[0]

    assert row["favorite_side"] == "home"
    assert bool(row["covered"])


def test_espn_game_odds_client_uses_transport(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/summary")
        return httpx.Response(200, json=_espn_summary_payload(favorite_home=False))

    client = EspnGameOddsClient(
        cache_dir=tmp_path / "cache",
        delay=0.0,
        retry_backoff=0.0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=_noop_sleep,
    )
    df = client.game_odds(401874176)
    assert len(df) == 1
    assert df.iloc[0]["favorite_side"] == "away"
    client.close()

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

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from draft_oracle.ingest.odds import (
    SOURCE_ESPN_COMPLETION,
    SOURCE_KAGGLE,
    SOURCE_SBR,
    STANDARD_OVERROUND,
    american_to_decimal,
    american_to_implied_prob,
    devig_favorite_only,
    devig_proportional,
    is_playoff_game,
    is_preseason_game,
    parse_espn_completion,
    parse_kaggle_extensive,
    parse_sbr_workbook,
    resolve_team_id,
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

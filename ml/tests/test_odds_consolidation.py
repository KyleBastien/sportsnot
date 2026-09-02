"""Odds consolidation, archive-label, and validation tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from draft_oracle.ingest.odds import (
    SOURCE_KAGGLE,
    SOURCE_SBR,
    build_source_odds,
    consolidate_odds,
    load_archive_game_types,
    load_local_game_dates,
    parse_espn_completion,
    parse_kaggle_extensive,
    parse_sbr_archive,
    parse_sbr_workbook,
    resolve_team_id,
)
from tests.test_odds import (
    REAL_KAGGLE_EXTENSIVE,
    REAL_SBR_2019_20,
    _favorite_csv,
    _write_gz_csv,
    _write_sbr_workbook,
)

# ── Consolidation ────────────────────────────────────────────────────────


def _two_sided_frame_row(**kwargs: object) -> dict[str, object]:
    return kwargs


def test_consolidate_prefers_sbr_and_cross_validates(tmp_path: Path) -> None:
    # Same game from SBR (two-sided) and Kaggle (favorite-only, UTC +1 day).
    sbr = parse_sbr_workbook_from_rows(
        tmp_path,
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


def parse_sbr_workbook_from_rows(
    tmp_path: Path, season: str, rows: list[list[object]]
) -> pd.DataFrame:
    path = tmp_path / f"nhl-odds-{season}.xlsx"
    _write_sbr_workbook(path, rows)
    return parse_sbr_workbook(path)


def test_consolidate_keeps_adjacent_distinct_games_separate(tmp_path: Path) -> None:
    # Same matchup on two consecutive days (back-to-back) must NOT merge.
    sbr = parse_sbr_workbook_from_rows(
        tmp_path,
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



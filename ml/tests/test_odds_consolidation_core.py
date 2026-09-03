"""Core odds consolidation and local-date tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from draft_oracle.ingest.odds import (
    SOURCE_KAGGLE,
    SOURCE_SBR,
    build_source_odds,
    consolidate_odds,
    load_local_game_dates,
    resolve_team_id,
)
from tests.odds_consolidation_helpers import (
    _archive_dates_by_matchup,
    _attach_rate,
    _committed_archive_games,
    _covered_committed_odds_source,
    _default_archive_dir,
    _kaggle_pair,
    parse_sbr_workbook_from_rows,
)


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
    assert len(consolidated) == 2


def test_consolidate_empty_frame() -> None:
    empty = build_source_odds(Path("nonexistent-dir"))
    assert empty.empty
    out = consolidate_odds(empty)
    assert out.empty
    assert "xval_delta" in out.columns


def test_consolidate_snaps_utc_date_to_local() -> None:
    """A Kaggle UTC calendar date is snapped to the archive local date (M-2)."""
    from draft_oracle.ingest.odds import _favorite_rows_from_games, _finalize

    kaggle = _finalize(
        _favorite_rows_from_games(
            pd.DataFrame(
                _kaggle_pair(
                    game_id=1,
                    date="2024-05-02 02:00:00+00:00",
                    season=2024,
                    home="Toronto Maple Leafs",
                    away="Boston Bruins",
                    price=-175,
                )
            ),
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
            pd.DataFrame(
                _kaggle_pair(
                    game_id=1,
                    date="2024-05-01 18:00:00+00:00",
                    season=2024,
                    home="Toronto Maple Leafs",
                    away="Boston Bruins",
                    price=-175,
                )
            ),
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
            pd.DataFrame(
                _kaggle_pair(
                    game_id=1,
                    date="2024-05-02 02:00:00+00:00",
                    season=2024,
                    home="Toronto Maple Leafs",
                    away="Boston Bruins",
                    price=-175,
                )
            ),
            source=SOURCE_KAGGLE,
        )
    )
    home_id = resolve_team_id("Toronto Maple Leafs")
    away_id = resolve_team_id("Boston Bruins")
    assert home_id is not None and away_id is not None
    local_dates = {(2024, home_id, away_id): (date(2024, 1, 1),)}  # far away
    consolidated = consolidate_odds(kaggle, local_game_dates=local_dates)
    assert consolidated.iloc[0]["game_date"] == "2024-05-02"


def test_load_local_game_dates_indexes_home_away(tmp_path: Path) -> None:
    archive = tmp_path / "nhl-archive"
    archive.mkdir()
    frame = pd.DataFrame(
        [
            {
                "seasonId": 20232024,
                "gameId": 111,
                "teamId": 10,
                "homeRoad": "H",
                "gameDate": "2024-05-01",
            },
            {
                "seasonId": 20232024,
                "gameId": 111,
                "teamId": 6,
                "homeRoad": "R",
                "gameDate": "2024-05-01",
            },
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
    seasons = [2023, 2024, 2025, 2026]
    source = _covered_committed_odds_source()
    games = _committed_archive_games()
    archive_dates = _archive_dates_by_matchup(games)

    local_dates = load_local_game_dates(_default_archive_dir())
    normalized = consolidate_odds(source, local_game_dates=local_dates)
    n_genuine, rate = _attach_rate(normalized, games, archive_dates, seasons)
    assert n_genuine > 500  # a substantial covered universe is exercised
    assert rate >= 0.95, f"only {rate:.3f} of genuine covered odds attached"

    _, control_rate = _attach_rate(consolidate_odds(source), games, archive_dates, seasons)
    assert control_rate < rate

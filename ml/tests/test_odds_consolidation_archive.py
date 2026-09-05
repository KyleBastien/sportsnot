"""Archive game-type odds consolidation tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from draft_oracle.ingest.odds import (
    SOURCE_SBR,
    consolidate_odds,
    load_archive_game_types,
    load_local_game_dates,
    parse_sbr_workbook,
    resolve_team_id,
)
from tests.odds_consolidation_helpers import (
    _covered_committed_odds_source,
    _default_archive_dir,
    _playoff_label_mismatches,
    _sbr_late_april_regular,
    _unmatched_covered_rows,
)
from tests.test_odds import REAL_SBR_2019_20


def test_load_archive_game_types_indexes_gametypeid(tmp_path: Path) -> None:
    """The loader maps each matchup date to its archive gameTypeId, both ways."""
    archive = tmp_path / "nhl-archive"
    archive.mkdir()
    frame = pd.DataFrame(
        [
            {
                "seasonId": 20212022,
                "gameTypeId": 2,
                "gameId": 111,
                "teamId": 10,
                "homeRoad": "H",
                "gameDate": "2022-04-29",
            },
            {
                "seasonId": 20212022,
                "gameTypeId": 2,
                "gameId": 111,
                "teamId": 6,
                "homeRoad": "R",
                "gameDate": "2022-04-29",
            },
            {
                "seasonId": 20212022,
                "gameTypeId": 3,
                "gameId": 222,
                "teamId": 10,
                "homeRoad": "H",
                "gameDate": "2022-05-10",
            },
            {
                "seasonId": 20212022,
                "gameTypeId": 3,
                "gameId": 222,
                "teamId": 6,
                "homeRoad": "R",
                "gameDate": "2022-05-10",
            },
        ]
    )
    frame.to_csv(archive / "team-games-2021-22.csv.gz", index=False, compression="gzip")
    index = load_archive_game_types(archive)
    assert index[(2022, 10, 6)][date(2022, 4, 29)] == 2
    assert index[(2022, 10, 6)][date(2022, 5, 10)] == 3
    # Stored in both orientations so a reversed odds row still resolves.
    assert index[(2022, 6, 10)][date(2022, 5, 10)] == 3


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
    from draft_oracle.ingest.odds import OddsRowGame, _finalize, _two_sided_row

    home_id = resolve_team_id("Toronto Maple Leafs")
    away_id = resolve_team_id("Boston Bruins")
    assert home_id is not None and away_id is not None
    game = OddsRowGame(
        source=SOURCE_SBR,
        season_end_year=2022,
        game_date=date(2022, 5, 10),
        away_id=away_id,
        home_id=home_id,
        away_name="Boston Bruins",
        home_name="Toronto Maple Leafs",
        neutral=False,
    )
    source = _finalize(
        [
            _two_sided_row(
                game,
                away_ml=120.0,
                home_ml=-140.0,
            )
        ]
    )
    dates = {(2022, home_id, away_id): (date(2022, 5, 10),)}
    types = {(2022, home_id, away_id): {date(2022, 5, 10): 3}}
    out = consolidate_odds(source, local_game_dates=dates, local_game_types=types)
    assert bool(out.iloc[0]["is_playoff"]) is True


def test_consolidate_excludes_rows_with_no_archive_game() -> None:
    """A priced row absent from the archive (e.g. preseason) is flagged uncovered."""
    from draft_oracle.ingest.odds import OddsRowGame, _finalize, _two_sided_row

    home_id = resolve_team_id("Toronto Maple Leafs")
    away_id = resolve_team_id("Boston Bruins")
    assert home_id is not None and away_id is not None
    game = OddsRowGame(
        source=SOURCE_SBR,
        season_end_year=2022,
        game_date=date(2021, 10, 3),
        away_id=away_id,
        home_id=home_id,
        away_name="Boston Bruins",
        home_name="Toronto Maple Leafs",
        neutral=False,
    )
    source = _finalize(
        [
            _two_sided_row(
                game,
                away_ml=120.0,
                home_ml=-140.0,
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
    source = _covered_committed_odds_source()
    dates = load_local_game_dates(_default_archive_dir())
    types = load_archive_game_types(_default_archive_dir())

    out = consolidate_odds(source, local_game_dates=dates, local_game_types=types)

    wrong_regular, wrong_playoff = _playoff_label_mismatches(out, types)
    assert wrong_regular == 0, f"{wrong_regular} regular-season games flagged playoff"
    assert wrong_playoff == 0, f"{wrong_playoff} playoff games flagged non-playoff"

    # Control: the fixed April windows DO mislabel regular-season games as playoff.
    old = consolidate_odds(source, local_game_dates=dates)
    old_wrong, _ = _playoff_label_mismatches(old, types)
    assert old_wrong > 0, "control must reproduce the fixed-window mislabels"

    # Preseason leak (m-12): every covered row resolves to a real archive game.
    covered = out.loc[out["covered"].astype(bool)]
    unmatched_covered = _unmatched_covered_rows(covered, types)
    assert unmatched_covered == 0, f"{unmatched_covered} covered rows have no archive game"

"""End-to-end tests for league draft entity matching."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from draft_oracle.ingest.entity_match import (
    POINT_CROSSCHECK_TOLERANCE,
    LeagueEntityMatchResult,
    build_league_draft_picks,
)
from tests.test_entity_match import _write_manager_aliases

# ── End-to-end build on a synthetic normalized dir ───────────────────────

_DEFAULT_OVERRIDES = "players: {}\nteams: {}\n"


def _write_normalized(normalized_dir: Path) -> None:
    normalized_dir.mkdir(parents=True, exist_ok=True)
    players, teams = _normalized_lookup_tables()
    players.to_parquet(normalized_dir / "players.parquet", index=False)
    teams.to_parquet(normalized_dir / "teams.parquet", index=False)
    pd.DataFrame(
        columns=[
            "season_id",
            "game_type_id",
            "game_id",
            "player_id",
            "goals",
            "assists",
        ]
    ).to_parquet(normalized_dir / "skater_games.parquet", index=False)


def _normalized_lookup_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    players = pd.DataFrame(
        [
            {"player_id": 8478402, "player_name": "Connor McDavid", "position": "F"},
            {"player_id": 8477934, "player_name": "Leon Draisaitl", "position": "F"},
            {"player_id": 8477956, "player_name": "David Pastrnak", "position": "F"},
            {"player_id": 8477932, "player_name": "Aaron Ekblad", "position": "D"},
        ]
    )
    teams = pd.DataFrame(
        [
            {"team_id": 13, "team_abbrev": "FLA", "team_full_name": "Florida Panthers"},
            {"team_id": 22, "team_abbrev": "EDM", "team_full_name": "Edmonton Oilers"},
        ]
    )
    return players, teams


def _write_playoff_points(
    normalized_dir: Path,
    player_id: int,
    round_points: dict[int, int],
) -> None:
    rows = [
        {
            "season_id": 20232024,
            "game_type_id": 3,
            "game_id": int(f"2023030{playoff_round}01"),
            "player_id": player_id,
            "goals": points,
            "assists": 0,
        }
        for playoff_round, points in round_points.items()
    ]
    pd.DataFrame(rows).to_parquet(normalized_dir / "skater_games.parquet", index=False)


def _league_pick(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "season": 2025,
        "source": "sheet",
        "league_name": "The Gemmell Cup",
        "draft_event": "R1",
        "manager": "ben",
        "snake_slot": 1,
        "pick_number": None,
        "position": "F",
        "slot_label": "Forward 1",
        "player_or_team_name": "Connor McDavid",
        "corrected_name": None,
        "team_name": "Oilers",
        "points_for_round": 10,
        "points_when_drafted": 0,
        "current_total_points": 10,
        "status": None,
        "points_excluded": False,
        "ir_activated": False,
        "swap_partner": None,
        "note": None,
        "is_scored": True,
    }
    base.update(kw)
    return base


def _write_league_picks(normalized_dir: Path) -> None:
    rows = _league_pick_rows()
    pd.DataFrame(rows).to_parquet(normalized_dir / "league_picks.parquet", index=False)


def _league_pick_rows() -> list[dict[str, object]]:
    return [
        _league_pick(),  # exact skater
        _league_pick(
            player_or_team_name="David Pastrank",
            team_name="Bruins",
            snake_slot=2,
            slot_label="Forward 2",
        ),  # fuzzy typo
        _league_pick(
            position="D",
            player_or_team_name="Aaraon Ekblad",
            team_name="Panthers",
            slot_label="Defense 1",
        ),  # fuzzy typo, defenseman
        _league_pick(
            position="G",
            player_or_team_name="Panthers Goalie (Bob)",
            team_name="Panthers",
            slot_label="Goalie 1",
        ),  # team pick
        _league_pick(
            manager="Evi",  # alias -> levi
            player_or_team_name="Makar",
            corrected_name="Leon Draisaitl",  # corrected_name wins
            team_name="Oilers",
        ),
    ]


def _prepare_match_inputs(
    tmp_path: Path, overrides_text: str = _DEFAULT_OVERRIDES
) -> tuple[Path, Path]:
    normalized = tmp_path / "normalized"
    out = tmp_path / "out"
    _write_normalized(normalized)
    _write_manager_aliases(tmp_path / "manager_aliases.yaml")
    (tmp_path / "name_overrides.yaml").write_text(overrides_text, encoding="utf-8")
    return normalized, out


def _write_pick_rows(normalized_dir: Path, rows: list[dict[str, object]]) -> None:
    pd.DataFrame(rows).to_parquet(normalized_dir / "league_picks.parquet", index=False)


def _write_single_pick(normalized_dir: Path, **kw: object) -> None:
    _write_pick_rows(normalized_dir, [_league_pick(**kw)])


def _build_draft_picks(
    normalized_dir: Path,
    overrides_dir: Path,
    out_dir: Path,
) -> LeagueEntityMatchResult:
    return build_league_draft_picks(
        normalized_dir=normalized_dir,
        overrides_dir=overrides_dir,
        out_dir=out_dir,
    )


def test_build_league_draft_picks_end_to_end(tmp_path: Path) -> None:
    normalized, out = _prepare_match_inputs(tmp_path)
    _write_league_picks(normalized)

    result = _build_draft_picks(normalized, tmp_path, out)

    assert (out / "league_draft_picks.parquet").exists()
    assert result.total == 5
    assert result.matched == 5
    assert result.match_rate == 1.0
    # Manager alias applied.
    assert set(result.picks["manager"]) == {"ben", "levi"}
    # Goalie pick resolved to the team id, no player id.
    goalie = result.picks[result.picks["position"] == "G"].iloc[0]
    assert goalie["team_id"] == 13
    assert pd.isna(goalie["player_id"])
    # corrected_name wins over the raw name.
    corrected = result.picks[result.picks["player_or_team_name"] == "Makar"].iloc[0]
    assert corrected["player_id"] == 8477934
    # No review report when everything matches confidently.
    assert result.review_path is None
    # Per-season report present.
    assert result.seasons[0].season == 2025
    assert result.seasons[0].match_rate == 1.0


def test_build_league_draft_picks_review_report(tmp_path: Path) -> None:
    normalized, out = _prepare_match_inputs(tmp_path)
    rows = [
        _league_pick(),
        _league_pick(
            player_or_team_name="Zzxqwerty Nobody",
            team_name="Oilers",
            slot_label="Forward 2",
        ),  # unmatched -> review
    ]
    _write_pick_rows(normalized, rows)

    result = _build_draft_picks(normalized, tmp_path, out)
    assert result.matched == 1
    assert result.total == 2
    assert result.review_path is not None
    assert result.review_path.exists()
    review = pd.read_csv(result.review_path)
    assert "Zzxqwerty Nobody" in set(review["player_or_team_name"])


def test_build_league_draft_picks_override_closes_gap(tmp_path: Path) -> None:
    normalized, out = _prepare_match_inputs(
        tmp_path,
        "players:\n"
        "  'Mystery Man':\n"
        "    player_id: 8478402\n"
        "    expected_matches: 1\n"
        "teams: {}\n",
    )
    _write_single_pick(normalized, player_or_team_name="Mystery Man")

    result = _build_draft_picks(normalized, tmp_path, out)
    assert result.matched == 1
    assert result.picks.iloc[0]["player_id"] == 8478402
    assert result.picks.iloc[0]["match_method"] == "override"


def test_name_override_expected_match_guard_rejects_second_raw_name(
    tmp_path: Path,
) -> None:
    normalized, out = _prepare_match_inputs(
        tmp_path,
        "players:\n"
        "  McDavid:\n"
        "    player_id: 8477934\n"
        "    expected_matches: 1\n"
        "teams: {}\n",
    )
    _write_pick_rows(
        normalized,
        [
            _league_pick(manager="ben", player_or_team_name="McDavid"),
            _league_pick(
                manager="levi",
                slot_label="Forward 2",
                player_or_team_name="McDavid",
            ),
        ],
    )

    with pytest.raises(ValueError, match=r"expected 1 league-pick match.*found 2"):
        _build_draft_picks(normalized, tmp_path, out)


def test_name_override_guard_counts_corrected_name_used_by_matcher(
    tmp_path: Path,
) -> None:
    normalized, out = _prepare_match_inputs(
        tmp_path,
        "players:\n"
        "  McDavid:\n"
        "    player_id: 8477934\n"
        "    expected_matches: 1\n"
        "teams: {}\n",
    )
    _write_single_pick(
        normalized,
        season=2024,
        draft_event="R3_4",
        player_or_team_name="McDavid",
        corrected_name="Connor McDavid",
    )

    with pytest.raises(ValueError, match=r"expected 1 league-pick match.*found 0"):
        _build_draft_picks(normalized, tmp_path, out)


def test_team_override_guard_accepts_matching_g_slot_count(tmp_path: Path) -> None:
    normalized, out = _prepare_match_inputs(
        tmp_path,
        "players: {}\n"
        "teams:\n"
        "  'Mystery Club':\n"
        "    team_id: 13\n"
        "    expected_matches: 1\n",
    )
    _write_single_pick(
        normalized,
        position="G",
        slot_label="Goalie 1",
        player_or_team_name="Mystery Goalie",
        team_name="Mystery Club",
    )

    result = _build_draft_picks(normalized, tmp_path, out)

    assert int(result.picks.iloc[0]["team_id"]) == 13


def test_team_override_guard_rejects_wrong_g_slot_count(tmp_path: Path) -> None:
    normalized, out = _prepare_match_inputs(
        tmp_path,
        "players: {}\n"
        "teams:\n"
        "  'Mystery Club':\n"
        "    team_id: 13\n"
        "    expected_matches: 2\n",
    )
    _write_single_pick(
        normalized,
        position="G",
        slot_label="Goalie 1",
        player_or_team_name="Mystery Goalie",
        team_name="Mystery Club",
    )

    with pytest.raises(ValueError, match=r"expected 2 G-slot.*found 1"):
        _build_draft_picks(normalized, tmp_path, out)


def test_point_split_crosscheck_flags_wrong_2024_mcdavid_match(tmp_path: Path) -> None:
    """Row 99's 24/7/31 split contradicts Connor McDavid in all three fields."""
    normalized, out = _prepare_match_inputs(tmp_path)
    _write_playoff_points(normalized, 8478402, {1: 12, 2: 9, 3: 10, 4: 11})
    _write_single_pick(
        normalized,
        season=2024,
        draft_event="R3_4",
        manager="levi",
        player_or_team_name="McDavid",
        points_for_round=7,
        points_when_drafted=24,
        current_total_points=31,
    )

    result = _build_draft_picks(normalized, tmp_path, out)

    assert POINT_CROSSCHECK_TOLERANCE == 0
    assert result.point_mismatches == 1
    assert result.picks.iloc[0]["player_id"] == 8478402
    assert bool(result.picks.iloc[0]["needs_review"]) is True


def test_duplicate_player_ownership_flags_every_manager_copy(tmp_path: Path) -> None:
    normalized, out = _prepare_match_inputs(tmp_path)
    _write_pick_rows(
        normalized,
        [
            _league_pick(manager="ben"),
            _league_pick(manager="levi", slot_label="Forward 2"),
        ],
    )

    result = _build_draft_picks(normalized, tmp_path, out)

    assert result.duplicate_ownerships == 1
    assert result.duplicate_ownership_rows == 2
    assert result.picks["needs_review"].tolist() == [True, True]
    assert "1 duplicate-ownership asset(s)" in "\n".join(result.report_lines())


def test_duplicate_goalie_team_ownership_flags_every_manager_copy(tmp_path: Path) -> None:
    normalized, out = _prepare_match_inputs(tmp_path)
    _write_pick_rows(
        normalized,
        [
            _league_pick(
                manager="ben",
                position="G",
                slot_label="Goalie",
                player_or_team_name="Panthers Goalie",
                team_name="Panthers",
            ),
            _league_pick(
                manager="levi",
                position="G",
                slot_label="Goalie",
                player_or_team_name="Florida Panthers",
                team_name="Panthers",
            ),
        ],
    )

    result = _build_draft_picks(normalized, tmp_path, out)

    assert set(result.picks["team_id"].astype(int)) == {13}
    assert result.duplicate_ownerships == 1
    assert result.duplicate_ownership_rows == 2
    assert result.point_mismatches == 0
    assert result.picks["needs_review"].tolist() == [True, True]


def test_real_2024_override_resolves_draisaitl_without_ownership_conflict(
    tmp_path: Path,
) -> None:
    normalized = Path("data/normalized")
    if not (normalized / "league_picks.parquet").exists():
        pytest.skip("committed normalized league picks not present")

    result = _build_draft_picks(normalized, Path("data/overrides"), tmp_path)
    event = result.picks.loc[
        (result.picks["season"] == 2024) & (result.picks["draft_event"] == "R3_4")
    ]
    levi = event.loc[
        (event["manager"] == "levi") & (event["player_or_team_name"] == "McDavid")
    ].iloc[0]
    judah = event.loc[
        (event["manager"] == "judah") & (event["player_or_team_name"] == "Connor McDavid")
    ].iloc[0]

    assert int(levi["player_id"]) == 8477934
    assert levi["matched_name"] == "Leon Draisaitl"
    assert levi["match_method"] == "override"
    assert bool(levi["needs_review"]) is False
    assert int(judah["player_id"]) == 8478402
    assert result.duplicate_ownerships == 0
    assert result.point_mismatches == 0


def test_build_league_draft_picks_missing_input_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _build_draft_picks(tmp_path / "nope", tmp_path, tmp_path / "out")

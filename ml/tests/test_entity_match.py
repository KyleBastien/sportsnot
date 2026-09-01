"""Tests for draft-history entity matching to NHL ids (US-007).

All fixtures are built in-memory / on ``tmp_path`` — no network, no dependency on
generated Parquet tables. Fuzzy-matching normalization (accents, initials,
nicknames, typos) and manager-alias resolution are exercised directly.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from draft_oracle.ingest.entity_match import (
    HIGH_CONFIDENCE,
    POINT_CROSSCHECK_TOLERANCE,
    NameOverrides,
    PlayerIndex,
    build_league_draft_picks,
    build_player_index,
    last_name_key,
    load_manager_aliases,
    load_name_overrides,
    match_skater,
    match_team,
    name_tokens,
    normalize_name,
    resolve_manager,
    resolve_team,
)

# ── Name normalization ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Elias Pettersson", "eliaspettersson"),
        ("Montréal Canadiens", "montrealcanadiens"),  # accents stripped
        ("J.T. Miller", "jtmiller"),  # initials with dots
        ("JT Miller", "jtmiller"),
        ("J-T Miller", "jtmiller"),  # hyphenated initials
        ("  Connor  McDavid ", "connormcdavid"),  # whitespace collapse
        ("T.J. Oshie", "tjoshie"),
        ("Tim Stützle", "timstutzle"),  # umlaut -> ascii
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_name(raw: str | None, expected: str) -> None:
    assert normalize_name(raw) == expected


def test_normalize_name_accent_variants_collide() -> None:
    assert normalize_name("Montréal") == normalize_name("Montreal")


def test_name_tokens_and_last_name_key() -> None:
    assert name_tokens("J.T. Miller") == ["j", "t", "miller"]
    assert last_name_key("Connor McDavid") == "mcdavid"
    assert last_name_key("McDavid") == "mcdavid"
    assert last_name_key("") == ""
    assert last_name_key(None) == ""


# ── Manager alias resolution ─────────────────────────────────────────────


def _write_manager_aliases(path: Path) -> Path:
    path.write_text(
        "ben:\n  - ben\n  - bentunigold\n"
        "judah:\n  - judah\n  - judah18\n"
        "kyle:\n  - kyle\n  - nuttguy\n"
        "levi:\n  - levi\n  - evi\n  - gemmell.levi\n",
        encoding="utf-8",
    )
    return path


def test_load_manager_aliases_inverts_file(tmp_path: Path) -> None:
    aliases = load_manager_aliases(_write_manager_aliases(tmp_path / "m.yaml"))
    assert aliases["evi"] == "levi"
    assert aliases["gemmell.levi"] == "levi"
    assert aliases["nuttguy"] == "kyle"
    assert aliases["bentunigold"] == "ben"
    # Canonical ids map to themselves.
    for canonical in ("ben", "judah", "kyle", "levi"):
        assert aliases[canonical] == canonical


def test_load_manager_aliases_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_manager_aliases(tmp_path / "nope.yaml")


def test_resolve_manager(tmp_path: Path) -> None:
    aliases = load_manager_aliases(_write_manager_aliases(tmp_path / "m.yaml"))
    assert resolve_manager("Evi", aliases) == "levi"  # owner-confirmed
    assert resolve_manager("  LEVI  ", aliases) == "levi"
    assert resolve_manager("gemmell.levi", aliases) == "levi"
    # Unknown press/app manager passes through lowercased, never merged.
    assert resolve_manager("paul.markhauser", aliases) == "paul.markhauser"


def test_committed_manager_aliases_file_loads() -> None:
    aliases = load_manager_aliases()
    assert aliases["evi"] == "levi"
    assert {"ben", "judah", "kyle", "levi"} <= set(aliases.values())


# ── Name-override files ──────────────────────────────────────────────────


def test_load_name_overrides_normalizes_keys(tmp_path: Path) -> None:
    path = tmp_path / "ov.yaml"
    path.write_text(
        "players:\n  'Some Guy': 8471234\nteams:\n  'Montréal Canadiens': 8\n",
        encoding="utf-8",
    )
    ov = load_name_overrides(path)
    assert ov.players["someguy"] == 8471234
    assert ov.teams["montrealcanadiens"] == 8


def test_load_name_overrides_reads_expected_match_guard(tmp_path: Path) -> None:
    path = tmp_path / "ov.yaml"
    path.write_text(
        "players:\n"
        "  McDavid:\n"
        "    player_id: 8477934\n"
        "    expected_matches: 1\n"
        "teams: {}\n",
        encoding="utf-8",
    )

    ov = load_name_overrides(path)

    assert ov.players["mcdavid"] == 8477934
    assert ov.player_expected_matches == {"mcdavid": 1}


def test_load_name_overrides_missing_file_is_empty(tmp_path: Path) -> None:
    ov = load_name_overrides(tmp_path / "absent.yaml")
    assert ov == NameOverrides()


def test_load_name_overrides_empty_sections(tmp_path: Path) -> None:
    path = tmp_path / "ov.yaml"
    path.write_text("players: {}\nteams: {}\n", encoding="utf-8")
    ov = load_name_overrides(path)
    assert ov.players == {}
    assert ov.teams == {}


# ── Team resolution ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Panthers", 13),  # nickname only
        ("Florida Panthers", 13),  # full name
        ("Florida", 13),  # city
        ("FLA", 13),  # abbrev
        ("Jets", 52),
        ("Maple Leafs", 10),  # two-word nickname
        ("Red Wings", 17),
        ("Blue Jackets", 29),
        ("Golden Knights", 54),
        ("Vegas Knights", 54),  # sheet variant
        ("Montréal Canadiens", 8),  # accent
        ("Nobody FC", None),
    ],
)
def test_resolve_team(name: str, expected: int | None) -> None:
    assert resolve_team(name) == expected


def test_resolve_team_override_precedence() -> None:
    ov = NameOverrides(teams={"mysteryclub": 13})
    assert resolve_team("Mystery Club", None, ov) == 13


def test_resolve_team_uses_raw_fallback() -> None:
    assert resolve_team(None, "Panthers Goalie") == 13


# ── Skater matching ──────────────────────────────────────────────────────


@pytest.fixture
def index() -> PlayerIndex:
    players = pd.DataFrame(
        [
            {"player_id": 8478402, "player_name": "Connor McDavid", "position": "F"},
            {"player_id": 8477934, "player_name": "Leon Draisaitl", "position": "F"},
            {"player_id": 8477956, "player_name": "David Pastrnak", "position": "F"},
            {"player_id": 8480012, "player_name": "Elias Pettersson", "position": "F"},
            {"player_id": 8477932, "player_name": "Aaron Ekblad", "position": "D"},
            {"player_id": 8476869, "player_name": "Brady Skjei", "position": "D"},
            # Same-name collision resolved by position.
            {"player_id": 8478427, "player_name": "Sebastian Aho", "position": "F"},
            {"player_id": 8480222, "player_name": "Sebastian Aho", "position": "D"},
        ]
    )
    return build_player_index(players)


def test_match_skater_exact(index: PlayerIndex) -> None:
    match = match_skater("Connor McDavid", "F", index)
    assert match.entity_id == 8478402
    assert match.method == "exact"
    assert match.confidence == 1.0
    assert match.needs_review is False


def test_match_skater_accent_and_initials(index: PlayerIndex) -> None:
    # Exact after normalization despite spacing.
    assert match_skater(" Connor  McDavid ", "F", index).entity_id == 8478402


@pytest.mark.parametrize(
    ("typo", "position", "expected_id"),
    [
        ("David Pastrank", "F", 8477956),
        ("Elias Petterson", "F", 8480012),
        ("Aaraon Ekblad", "D", 8477932),
        ("Brady Skijei", "D", 8476869),
    ],
)
def test_match_skater_fuzzy_typos(
    index: PlayerIndex,
    typo: str,
    position: str,
    expected_id: int,
) -> None:
    match = match_skater(typo, position, index)
    assert match.entity_id == expected_id
    assert match.method == "fuzzy"
    assert match.confidence >= HIGH_CONFIDENCE
    assert match.needs_review is False


def test_match_skater_lastname_fallback(index: PlayerIndex) -> None:
    # Bare surname: full-string ratio is low, unique last name still resolves.
    match = match_skater("McDavid", "F", index)
    assert match.entity_id == 8478402
    assert match.method == "lastname"
    assert match.needs_review is False


def test_match_skater_position_disambiguates_collision(index: PlayerIndex) -> None:
    assert match_skater("Sebastian Aho", "F", index).entity_id == 8478427
    assert match_skater("Sebastian Aho", "D", index).entity_id == 8480222


def test_match_skater_override_wins(index: PlayerIndex) -> None:
    ov = NameOverrides(players={"mystery": 8478402})
    match = match_skater("Mystery", "F", index, ov)
    assert match.entity_id == 8478402
    assert match.method == "override"


def test_match_skater_unmatched_flags_review(index: PlayerIndex) -> None:
    match = match_skater("Zzxqwerty Nobody", "F", index)
    assert match.entity_id is None
    assert match.method == "unmatched"
    assert match.needs_review is True


# ── Team match wrapper ───────────────────────────────────────────────────


def test_match_team_resolves_and_names() -> None:
    match = match_team("Panthers", "Panthers Goalie (Bob)", {13: "Florida Panthers"})
    assert match.entity_id == 13
    assert match.matched_name == "Florida Panthers"
    assert match.method == "team"
    assert match.needs_review is False


def test_match_team_unmatched() -> None:
    match = match_team("Nowhere", "Nowhere", {})
    assert match.entity_id is None
    assert match.needs_review is True


# ── End-to-end build on a synthetic normalized dir ───────────────────────


def _write_normalized(normalized_dir: Path) -> None:
    normalized_dir.mkdir(parents=True, exist_ok=True)
    players = pd.DataFrame(
        [
            {"player_id": 8478402, "player_name": "Connor McDavid", "position": "F"},
            {"player_id": 8477934, "player_name": "Leon Draisaitl", "position": "F"},
            {"player_id": 8477956, "player_name": "David Pastrnak", "position": "F"},
            {"player_id": 8477932, "player_name": "Aaron Ekblad", "position": "D"},
        ]
    )
    players.to_parquet(normalized_dir / "players.parquet", index=False)
    teams = pd.DataFrame(
        [
            {"team_id": 13, "team_abbrev": "FLA", "team_full_name": "Florida Panthers"},
            {"team_id": 22, "team_abbrev": "EDM", "team_full_name": "Edmonton Oilers"},
        ]
    )
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
    rows = [
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
    pd.DataFrame(rows).to_parquet(normalized_dir / "league_picks.parquet", index=False)


def test_build_league_draft_picks_end_to_end(tmp_path: Path) -> None:
    normalized = tmp_path / "normalized"
    out = tmp_path / "out"
    _write_normalized(normalized)
    _write_league_picks(normalized)
    _write_manager_aliases(tmp_path / "manager_aliases.yaml")
    (tmp_path / "name_overrides.yaml").write_text("players: {}\nteams: {}\n", encoding="utf-8")

    result = build_league_draft_picks(
        normalized_dir=normalized, overrides_dir=tmp_path, out_dir=out
    )

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
    normalized = tmp_path / "normalized"
    out = tmp_path / "out"
    _write_normalized(normalized)
    rows = [
        _league_pick(),
        _league_pick(
            player_or_team_name="Zzxqwerty Nobody",
            team_name="Oilers",
            slot_label="Forward 2",
        ),  # unmatched -> review
    ]
    pd.DataFrame(rows).to_parquet(normalized / "league_picks.parquet", index=False)
    _write_manager_aliases(tmp_path / "manager_aliases.yaml")
    (tmp_path / "name_overrides.yaml").write_text("players: {}\nteams: {}\n", encoding="utf-8")

    result = build_league_draft_picks(
        normalized_dir=normalized, overrides_dir=tmp_path, out_dir=out
    )
    assert result.matched == 1
    assert result.total == 2
    assert result.review_path is not None
    assert result.review_path.exists()
    review = pd.read_csv(result.review_path)
    assert "Zzxqwerty Nobody" in set(review["player_or_team_name"])


def test_build_league_draft_picks_override_closes_gap(tmp_path: Path) -> None:
    normalized = tmp_path / "normalized"
    out = tmp_path / "out"
    _write_normalized(normalized)
    pd.DataFrame([_league_pick(player_or_team_name="Mystery Man")]).to_parquet(
        normalized / "league_picks.parquet", index=False
    )
    _write_manager_aliases(tmp_path / "manager_aliases.yaml")
    (tmp_path / "name_overrides.yaml").write_text(
        "players:\n"
        "  'Mystery Man':\n"
        "    player_id: 8478402\n"
        "    expected_matches: 1\n"
        "teams: {}\n",
        encoding="utf-8",
    )

    result = build_league_draft_picks(
        normalized_dir=normalized, overrides_dir=tmp_path, out_dir=out
    )
    assert result.matched == 1
    assert result.picks.iloc[0]["player_id"] == 8478402
    assert result.picks.iloc[0]["match_method"] == "override"


def test_name_override_expected_match_guard_rejects_second_raw_name(
    tmp_path: Path,
) -> None:
    normalized = tmp_path / "normalized"
    _write_normalized(normalized)
    pd.DataFrame(
        [
            _league_pick(manager="ben", player_or_team_name="McDavid"),
            _league_pick(
                manager="levi",
                slot_label="Forward 2",
                player_or_team_name="McDavid",
            ),
        ]
    ).to_parquet(normalized / "league_picks.parquet", index=False)
    _write_manager_aliases(tmp_path / "manager_aliases.yaml")
    (tmp_path / "name_overrides.yaml").write_text(
        "players:\n"
        "  McDavid:\n"
        "    player_id: 8477934\n"
        "    expected_matches: 1\n"
        "teams: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"expected 1 league-pick match.*found 2"):
        build_league_draft_picks(
            normalized_dir=normalized,
            overrides_dir=tmp_path,
            out_dir=tmp_path / "out",
        )


def test_point_split_crosscheck_flags_wrong_2024_mcdavid_match(tmp_path: Path) -> None:
    """Row 99's 24/7/31 split contradicts Connor McDavid in all three fields."""
    normalized = tmp_path / "normalized"
    _write_normalized(normalized)
    _write_playoff_points(normalized, 8478402, {1: 12, 2: 9, 3: 10, 4: 11})
    pd.DataFrame(
        [
            _league_pick(
                season=2024,
                draft_event="R3_4",
                manager="levi",
                player_or_team_name="McDavid",
                points_for_round=7,
                points_when_drafted=24,
                current_total_points=31,
            )
        ]
    ).to_parquet(normalized / "league_picks.parquet", index=False)
    _write_manager_aliases(tmp_path / "manager_aliases.yaml")
    (tmp_path / "name_overrides.yaml").write_text("players: {}\nteams: {}\n", encoding="utf-8")

    result = build_league_draft_picks(
        normalized_dir=normalized, overrides_dir=tmp_path, out_dir=tmp_path / "out"
    )

    assert POINT_CROSSCHECK_TOLERANCE == 0
    assert result.point_mismatches == 1
    assert result.picks.iloc[0]["player_id"] == 8478402
    assert bool(result.picks.iloc[0]["needs_review"]) is True


def test_duplicate_player_ownership_flags_every_manager_copy(tmp_path: Path) -> None:
    normalized = tmp_path / "normalized"
    _write_normalized(normalized)
    pd.DataFrame(
        [
            _league_pick(manager="ben"),
            _league_pick(manager="levi", slot_label="Forward 2"),
        ]
    ).to_parquet(normalized / "league_picks.parquet", index=False)
    _write_manager_aliases(tmp_path / "manager_aliases.yaml")
    (tmp_path / "name_overrides.yaml").write_text("players: {}\nteams: {}\n", encoding="utf-8")

    result = build_league_draft_picks(
        normalized_dir=normalized, overrides_dir=tmp_path, out_dir=tmp_path / "out"
    )

    assert result.duplicate_ownerships == 1
    assert result.duplicate_ownership_rows == 2
    assert result.picks["needs_review"].tolist() == [True, True]
    assert "1 duplicate-ownership asset(s)" in "\n".join(result.report_lines())


def test_duplicate_goalie_team_ownership_flags_every_manager_copy(tmp_path: Path) -> None:
    normalized = tmp_path / "normalized"
    _write_normalized(normalized)
    pd.DataFrame(
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
        ]
    ).to_parquet(normalized / "league_picks.parquet", index=False)
    _write_manager_aliases(tmp_path / "manager_aliases.yaml")
    (tmp_path / "name_overrides.yaml").write_text("players: {}\nteams: {}\n", encoding="utf-8")

    result = build_league_draft_picks(
        normalized_dir=normalized, overrides_dir=tmp_path, out_dir=tmp_path / "out"
    )

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

    result = build_league_draft_picks(
        normalized_dir=normalized,
        overrides_dir=Path("data/overrides"),
        out_dir=tmp_path,
    )
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
        build_league_draft_picks(
            normalized_dir=tmp_path / "nope",
            overrides_dir=tmp_path,
            out_dir=tmp_path / "out",
        )

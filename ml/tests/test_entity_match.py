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
    NameOverrides,
    PlayerIndex,
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


def test_load_name_overrides_reads_team_expected_match_guard(tmp_path: Path) -> None:
    path = tmp_path / "ov.yaml"
    path.write_text(
        "players: {}\n"
        "teams:\n"
        "  'Mystery Club':\n"
        "    team_id: 13\n"
        "    expected_matches: 2\n",
        encoding="utf-8",
    )

    ov = load_name_overrides(path)

    assert ov.teams["mysteryclub"] == 13
    assert ov.team_expected_matches == {"mysteryclub": 2}


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

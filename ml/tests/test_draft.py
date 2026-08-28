"""Unit tests for the interactive draft assistant (US-024)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from draft_oracle.cli.draft import (
    DraftSession,
    parse_command,
    resolve_asset,
    resolve_manager,
)
from draft_oracle.cli.project import app
from draft_oracle.optimize.recommend import build_synthetic_pool
from draft_oracle.optimize.simulator import DraftAsset

runner = CliRunner()

MANAGERS = 4
SEATS = [f"seat{i + 1}" for i in range(MANAGERS)]


def _make_session(**overrides: object) -> DraftSession:
    pool = build_synthetic_pool(MANAGERS, allow_ir=False)
    kwargs: dict[str, object] = {
        "artifact_dir": Path("art"),
        "manager_count": MANAGERS,
        "slot": 1,
        "ir": False,
        "pool": pool,
        "managers": list(SEATS),
    }
    kwargs.update(overrides)
    return DraftSession(**kwargs)  # type: ignore[arg-type]


# ── command parsing ───────────────────────────────────────────────────────


def test_parse_blank_line() -> None:
    assert parse_command("   ").name == ""


def test_parse_pick_multiword_name() -> None:
    parsed = parse_command("pick seat1 Connor McDavid")
    assert parsed.name == "pick"
    assert parsed.manager == "seat1"
    assert parsed.query == "Connor McDavid"


def test_parse_pick_requires_name() -> None:
    parsed = parse_command("pick seat1")
    assert parsed.name == "pick"
    assert parsed.error is not None


def test_parse_recommend_with_depth() -> None:
    parsed = parse_command("recommend --depth 1")
    assert parsed.name == "recommend"
    assert parsed.depth == 1


def test_parse_recommend_bad_depth() -> None:
    assert parse_command("recommend --depth two").error is not None


def test_parse_aliases_and_unknown() -> None:
    assert parse_command("u").name == "undo"
    assert parse_command("b").name == "board"
    assert parse_command("q").name == "quit"
    assert parse_command("frobnicate").error is not None


def test_parse_save_and_resume() -> None:
    assert parse_command("save out.json").path == "out.json"
    assert parse_command("resume in.json").path == "in.json"
    assert parse_command("save").error is not None


# ── manager resolution ────────────────────────────────────────────────────


def test_resolve_manager_by_number_id_and_prefix() -> None:
    assert resolve_manager(SEATS, "1") == "seat1"
    assert resolve_manager(SEATS, "seat3") == "seat3"
    assert resolve_manager(SEATS, "SEAT2") == "seat2"
    assert resolve_manager(SEATS, "99") is None
    assert resolve_manager(SEATS, "nobody") is None


# ── fuzzy asset resolution ────────────────────────────────────────────────


def _pool() -> list[DraftAsset]:
    def asset(key: str, name: str) -> DraftAsset:
        return DraftAsset(
            key=key,
            name=name,
            position="F",
            rank_value=10.0,
            player_id=int(key[1:]),
            team_id=1,
            team_abbrev="AAA",
            projection=10.0,
        )

    return [
        asset("P1", "Connor McDavid"),
        asset("P2", "Nathan MacKinnon"),
        asset("P3", "Connor Bedard"),
    ]


def test_resolve_exact_match() -> None:
    result = resolve_asset(_pool(), "Nathan MacKinnon")
    assert result.asset is not None
    assert result.asset.key == "P2"


def test_resolve_substring_unique() -> None:
    result = resolve_asset(_pool(), "mackinnon")
    assert result.asset is not None
    assert result.asset.key == "P2"


def test_resolve_ambiguous_substring() -> None:
    result = resolve_asset(_pool(), "connor")
    assert result.asset is None
    assert result.reason == "ambiguous"
    assert len(result.matches) == 2


def test_resolve_fuzzy_typo() -> None:
    result = resolve_asset(_pool(), "mackinon")
    assert result.asset is not None
    assert result.asset.key == "P2"


def test_resolve_no_match() -> None:
    result = resolve_asset(_pool(), "zzzzzz")
    assert result.asset is None
    assert result.reason == "no match"


def test_resolve_empty_query() -> None:
    assert resolve_asset(_pool(), "   ").reason == "empty query"


# ── legality / rejection reasons ──────────────────────────────────────────


def test_pick_wrong_turn_rejected() -> None:
    session = _make_session()
    # seat1 is on the clock; seat2 cannot pick yet.
    result = session.record_pick("seat2", "F0")
    assert not result.ok
    assert "turn" in result.message


def test_pick_already_drafted_rejected() -> None:
    session = _make_session()
    first = session.state.current_manager
    name = session.state.legal_assets(first)[0].name
    assert session.record_pick(first, name).ok
    # Next manager tries the same asset.
    second = session.state.current_manager
    result = session.record_pick(second, name)
    assert not result.ok
    assert "already drafted" in result.message


def test_pick_eliminated_rejected() -> None:
    pool = build_synthetic_pool(MANAGERS, allow_ir=False)
    target = next(asset for asset in pool if asset.position == "F")
    session = _make_session(pool=pool, eliminated_team_ids=frozenset({target.team_id}))
    result = session.record_pick(session.state.current_manager, target.name)
    assert not result.ok
    assert "eliminated" in result.message


def test_pick_position_full_rejected() -> None:
    session = _make_session()
    # Drive seat1 to a full goalie slot then try another G on its turn.
    # Simpler: exhaust forwards is long; instead assert has_capacity logic via
    # a direct fill of the goalie slot.
    owner = session.state.current_manager
    goalie = next(asset for asset in session.state.available.values() if asset.position == "G")
    assert session.record_pick(owner, goalie.name).ok
    # Fast-forward opponents so owner is up again, then try a second goalie.
    while session.state.current_manager != owner:
        current = session.state.current_manager
        pick = session.state.legal_assets(current)[0]
        assert session.record_pick(current, pick.name).ok
    other_goalie = next(
        asset for asset in session.state.available.values() if asset.position == "G"
    )
    result = session.record_pick(owner, other_goalie.name)
    assert not result.ok
    assert "full at G" in result.message


# ── undo ──────────────────────────────────────────────────────────────────


def test_undo_restores_state() -> None:
    session = _make_session()
    owner = session.state.current_manager
    name = session.state.legal_assets(owner)[0].name
    before_available = len(session.state.available)
    assert session.record_pick(owner, name).ok
    assert len(session.state.available) == before_available - 1
    assert len(session.picks) == 1

    result = session.undo()
    assert result.ok
    assert len(session.picks) == 0
    assert len(session.state.available) == before_available
    assert session.state.current_manager == owner


def test_undo_nothing_to_undo() -> None:
    session = _make_session()
    assert not session.undo().ok


# ── save / resume round-trip ──────────────────────────────────────────────


def test_save_resume_round_trip(tmp_path: Path) -> None:
    session = _make_session()
    # Record a few picks in snake order.
    for _ in range(5):
        current = session.state.current_manager
        pick = session.state.legal_assets(current)[0]
        assert session.record_pick(current, pick.name).ok

    path = tmp_path / "session.json"
    session.save(path)

    def loader(_dir: Path, ir: bool) -> list[DraftAsset]:
        return build_synthetic_pool(MANAGERS, allow_ir=ir)

    resumed = DraftSession.resume(path, pool_loader=loader)
    assert resumed.picks == session.picks
    assert resumed.manager_count == session.manager_count
    assert resumed.slot == session.slot
    assert resumed.state.pick_index == session.state.pick_index
    assert set(resumed.state.available) == set(session.state.available)


def test_resume_detects_corrupted_order(tmp_path: Path) -> None:
    session = _make_session()
    current = session.state.current_manager
    pick = session.state.legal_assets(current)[0]
    assert session.record_pick(current, pick.name).ok
    data = session.to_dict()
    # Corrupt the recorded manager so replay must fail loudly (SPEC section 7).
    data["picks"][0]["manager"] = "seat_bogus"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    def loader(_dir: Path, ir: bool) -> list[DraftAsset]:
        return build_synthetic_pool(MANAGERS, allow_ir=ir)

    with pytest.raises(ValueError):
        DraftSession.resume(path, pool_loader=loader)


# ── recommend + board + roster ────────────────────────────────────────────


def test_recommend_returns_five_explained_picks() -> None:
    session = _make_session(rollouts=50)
    result = session.recommend(depth=1)
    assert result.ok
    text = "\n".join(result.lines)
    assert "pick recommendation" in text
    # Header row + up to five ranked rows.
    ranked_rows = [line for line in result.lines if line.startswith("| ") and line[2:3].isdigit()]
    assert 1 <= len(ranked_rows) <= 5


def test_board_and_roster_lines() -> None:
    session = _make_session()
    board = session.board()
    assert board.ok
    assert any("F (" in line for line in board.lines)

    owner = session.state.current_manager
    name = session.state.legal_assets(owner)[0].name
    session.record_pick(owner, name)
    roster = session.roster()
    assert roster.ok
    assert any("(you)" in line for line in roster.lines)


# ── CLI wiring ────────────────────────────────────────────────────────────


def test_draft_command_registered() -> None:
    result = runner.invoke(app, ["draft", "--help"])
    assert result.exit_code == 0
    assert "draft assistant" in result.stdout.lower()


def test_draft_command_requires_artifact() -> None:
    result = runner.invoke(app, ["draft"])
    assert result.exit_code != 0

"""Unit tests for the interactive draft assistant (US-024)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from typer.testing import CliRunner

from draft_oracle.cli import draft as draft_module
from draft_oracle.cli.draft import (
    DraftSession,
    parse_command,
    parse_managers,
    resolve_asset,
    resolve_manager,
    resolve_opponents_kind,
)
from draft_oracle.cli.project import app
from draft_oracle.optimize.opponents import (
    Coefficients,
    FittedLeagueOpponents,
    FittedOpponentModel,
    OpponentFitConfig,
)
from draft_oracle.optimize.recommend import build_synthetic_pool
from draft_oracle.optimize.simulator import DraftAsset, GreedyOpponentModel

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


# ── opponent model wiring (US-113) ─────────────────────────────────────────

REAL_MANAGERS = ["ben", "judah", "levi", "kyle"]


def _fitted() -> FittedLeagueOpponents:
    """A tiny in-memory fitted league model (no artifact, no training run)."""
    return FittedLeagueOpponents(
        league=Coefficients(rank=0.2, affinity=1.0),
        per_manager={"ben": Coefficients(rank=-0.1, affinity=2.0)},
        affinity={"ben": {1: 0.5}},
        manager_pick_counts={"ben": 90},
        total_picks=100,
        config=OpponentFitConfig(),
    )


def _fitted_session(tmp_dir: Path, **overrides: object) -> DraftSession:
    pool = build_synthetic_pool(MANAGERS, allow_ir=False)
    kwargs: dict[str, object] = {
        "artifact_dir": Path("art"),
        "manager_count": MANAGERS,
        "slot": 1,
        "ir": False,
        "pool": pool,
        "managers": list(REAL_MANAGERS),
        "rollouts": 20,
        "opponents": "fitted",
        "opponent_artifact_dir": tmp_dir,
        "fitted": _fitted(),
    }
    kwargs.update(overrides)
    return DraftSession(**kwargs)  # type: ignore[arg-type]


def test_parse_managers_count_gives_seats() -> None:
    assert parse_managers("4") == SEATS


def test_parse_managers_uses_real_names() -> None:
    assert parse_managers("ben, judah ,levi,kyle") == REAL_MANAGERS


def test_parse_managers_rejects_out_of_range_count() -> None:
    with pytest.raises(Exception):  # noqa: B017 - typer.BadParameter
        parse_managers("1")


def test_parse_managers_rejects_too_few_names() -> None:
    with pytest.raises(Exception):  # noqa: B017 - typer.BadParameter
        parse_managers("ben")


@pytest.mark.parametrize("managers", ["ben,ben,kyle,levi", "ben,Ben,kyle,levi"])
def test_parse_managers_rejects_duplicate_ids(managers: str) -> None:
    with pytest.raises(Exception, match=r"duplicate id.*ben"):
        parse_managers(managers)


@pytest.mark.parametrize(
    "command,artifact_flag",
    [("draft", "--artifact"), ("recommend", "--artifact-dir")],
)
def test_cli_commands_reject_duplicate_managers(command: str, artifact_flag: str) -> None:
    artifact = Path(__file__).parents[1] / "artifacts" / "2026-r1"
    result = runner.invoke(
        app,
        [
            command,
            artifact_flag,
            str(artifact),
            "--managers",
            "ben,ben,kyle,levi",
        ],
    )
    assert result.exit_code != 0
    assert "duplicate id(s): ben" in result.output


def test_resolve_opponents_kind_auto_detects(tmp_path: Path) -> None:
    assert resolve_opponents_kind("auto", tmp_path) == "greedy"
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    assert resolve_opponents_kind("auto", tmp_path) == "fitted"
    assert resolve_opponents_kind("", tmp_path) == "fitted"


def test_resolve_opponents_kind_explicit_fitted_without_artifact_is_loud(tmp_path: Path) -> None:
    with pytest.raises(Exception):  # noqa: B017 - typer.BadParameter fails closed
        resolve_opponents_kind("fitted", tmp_path)


def test_resolve_opponents_kind_rejects_unknown(tmp_path: Path) -> None:
    with pytest.raises(Exception):  # noqa: B017 - typer.BadParameter
        resolve_opponents_kind("random", tmp_path)


def test_build_opponent_model_greedy_is_single_fast_path() -> None:
    session = _make_session()
    model = session.build_opponent_model()
    assert isinstance(model, GreedyOpponentModel)


def test_build_opponent_model_fitted_maps_each_seat(tmp_path: Path) -> None:
    session = _fitted_session(tmp_path)
    model = session.build_opponent_model()
    assert isinstance(model, Mapping)
    assert set(model) == set(REAL_MANAGERS)
    assert all(isinstance(m, FittedOpponentModel) for m in model.values())
    # ben's own coefficients attach to ben's seat; the rest fall back to the league model.
    ben_model = model["ben"]
    judah_model = model["judah"]
    assert isinstance(ben_model, FittedOpponentModel)
    assert isinstance(judah_model, FittedOpponentModel)
    assert ben_model.coefficients == Coefficients(rank=-0.1, affinity=2.0)
    assert judah_model.coefficients == Coefficients(rank=0.2, affinity=1.0)


def test_session_loads_fitted_from_artifact_dir(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(json.dumps(_fitted().manifest()), encoding="utf-8")
    pool = build_synthetic_pool(MANAGERS, allow_ir=False)
    session = DraftSession(
        artifact_dir=Path("art"),
        manager_count=MANAGERS,
        slot=1,
        ir=False,
        pool=pool,
        managers=list(REAL_MANAGERS),
        opponents="fitted",
        opponent_artifact_dir=tmp_path,
    )
    assert session.fitted is not None
    model = session.build_opponent_model()
    assert isinstance(model, Mapping)
    ben_model = model["ben"]
    assert isinstance(ben_model, FittedOpponentModel)
    assert ben_model.coefficients == Coefficients(rank=-0.1, affinity=2.0)


def test_session_rejects_unknown_opponents() -> None:
    with pytest.raises(ValueError, match="greedy or fitted"):
        _make_session(opponents="wat")


def test_recommend_reports_mixed_fitted_opponents(tmp_path: Path) -> None:
    session = _fitted_session(tmp_path)
    result = session.recommend(depth=1)
    assert result.ok
    assert result.message == (
        "recommendation (fitted opponents: mixed per-manager and league-average)"
    )


def test_recommend_reports_default_seats_without_per_manager_affinity(tmp_path: Path) -> None:
    session = _fitted_session(tmp_path, managers=list(SEATS))
    result = session.recommend(depth=1)
    assert result.ok
    assert result.message == (
        "recommendation (fitted opponents: league-average, no per-manager affinity)"
    )


def test_recommend_reports_greedy_opponents() -> None:
    session = _make_session(rollouts=20)
    result = session.recommend(depth=1)
    assert result.ok
    assert "greedy opponents" in result.message


@pytest.mark.parametrize("managers", ["4", "Ben,seat2,seat3,seat4"])
def test_recommend_command_discloses_no_per_manager_affinity(tmp_path: Path, managers: str) -> None:
    (tmp_path / "manifest.json").write_text(json.dumps(_fitted().manifest()), encoding="utf-8")
    artifact = Path(__file__).parents[1] / "artifacts" / "2026-r1"
    result = runner.invoke(
        app,
        [
            "recommend",
            "--artifact-dir",
            str(artifact),
            "--managers",
            managers,
            "--rollouts",
            "1",
            "--depth",
            "1",
            "--opponents",
            "fitted",
            "--opponent-artifact",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "fitted opponents: league-average, no per-manager affinity" in result.output


def test_opponents_survive_save_resume(tmp_path: Path) -> None:
    session = _fitted_session(tmp_path)
    # A real committed manifest lives at the artifact dir so resume can reload it.
    (tmp_path / "manifest.json").write_text(json.dumps(_fitted().manifest()), encoding="utf-8")
    path = tmp_path / "session.json"
    session.save(path)

    def loader(_dir: Path, ir: bool) -> list[DraftAsset]:
        return build_synthetic_pool(MANAGERS, allow_ir=ir)

    resumed = DraftSession.resume(path, pool_loader=loader)
    assert resumed.opponents == "fitted"
    assert resumed.opponent_artifact_dir == tmp_path
    assert resumed.managers == REAL_MANAGERS
    assert resumed.fitted is not None


def test_run_loop_end_to_end_uses_fitted_model(tmp_path: Path) -> None:
    """Drive a scripted draft through the interactive CLI with the fitted model.

    Asserts the fitted per-manager model was actually used (not silently fallen
    back to the greedy fallback): the recommendation is labeled ``fitted`` and the
    session's opponent policy is a mapping of :class:`FittedOpponentModel`.
    """
    session = _fitted_session(tmp_path)
    scripted = iter(
        [
            f"pick ben {session.state.legal_assets('ben')[0].name}",
            "recommend --depth 1",
            "quit",
        ]
    )

    def _input(_prompt: str) -> str:
        try:
            return next(scripted)
        except StopIteration as exc:  # pragma: no cover - defensive
            raise EOFError from exc

    echoed: list[str] = []
    final = draft_module._run_loop(
        session,
        tmp_path / "log.json",
        input_fn=_input,
        echo=echoed.append,
    )

    assert any(
        "recommendation (fitted opponents: mixed per-manager and league-average)" in line
        for line in echoed
    )
    model = final.build_opponent_model()
    assert isinstance(model, Mapping)
    assert all(isinstance(m, FittedOpponentModel) for m in model.values())
    assert len(final.picks) == 1


def test_eliminated_abbrevs_are_case_insensitive_and_unknowns_are_loud() -> None:
    pool = build_synthetic_pool(MANAGERS, allow_ir=False)
    target = next(asset for asset in pool if asset.team_id is not None)
    assert draft_module._resolve_eliminated(pool, [target.team_abbrev.lower()]) == frozenset(
        {target.team_id}
    )
    with pytest.raises(Exception, match=r"MON, XYZ"):
        draft_module._resolve_eliminated(pool, ["MON", "xyz"])


def test_new_session_refuses_to_clobber_existing_pick_log(tmp_path: Path) -> None:
    existing = _make_session()
    for _ in range(2):
        current = existing.state.current_manager
        pick = existing.state.legal_assets(current)[0]
        assert existing.record_pick(current, pick.name).ok
    path = tmp_path / "draft-session.json"
    existing.save(path)
    before = path.read_bytes()

    with pytest.raises(Exception, match="use --resume"):
        draft_module.draft(
            artifact=tmp_path / "unused-artifact",
            managers="4",
            session=path,
            opponents="greedy",
        )

    assert path.read_bytes() == before
    assert len(json.loads(path.read_text(encoding="utf-8"))["picks"]) == 2


def test_resume_refuses_to_clobber_different_existing_session(tmp_path: Path) -> None:
    resumed = _make_session()
    resume_path = tmp_path / "league-a.json"
    resumed.save(resume_path)

    existing = _make_session()
    for _ in range(2):
        current = existing.state.current_manager
        pick = existing.state.legal_assets(current)[0]
        assert existing.record_pick(current, pick.name).ok
    session_path = tmp_path / "league-b.json"
    existing.save(session_path)
    before = session_path.read_bytes()

    with pytest.raises(Exception, match="differs from resumed log"):
        draft_module.draft(
            resume=resume_path,
            session=session_path,
            opponents="greedy",
        )

    assert session_path.read_bytes() == before
    assert len(json.loads(session_path.read_text(encoding="utf-8"))["picks"]) == 2


def test_resume_allows_same_session_as_explicit_autosave_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resumed = _make_session()
    resume_path = tmp_path / "league-a.json"
    resumed.save(resume_path)
    observed: list[tuple[DraftSession, Path | None]] = []
    monkeypatch.setattr(
        DraftSession,
        "resume",
        classmethod(lambda _cls, _path: resumed),
    )
    monkeypatch.setattr(
        draft_module,
        "_run_loop",
        lambda loaded, path: observed.append((loaded, path)),
    )

    draft_module.draft(resume=resume_path, session=resume_path, opponents="greedy")

    assert observed == [(resumed, resume_path)]


def test_in_loop_resume_switches_autosave_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launch = _make_session()
    for _ in range(2):
        current = launch.state.current_manager
        pick = launch.state.legal_assets(current)[0]
        assert launch.record_pick(current, pick.name).ok
    launch_path = tmp_path / "league-one.json"
    launch.save(launch_path)
    launch_before = launch_path.read_bytes()

    resumed = _make_session()
    resumed_path = tmp_path / "league-two.json"
    resumed.save(resumed_path)
    monkeypatch.setattr(
        DraftSession,
        "resume",
        classmethod(lambda _cls, path: resumed if path == resumed_path else launch),
    )
    commands = iter([f"resume {resumed_path}", "quit"])
    echoed: list[str] = []

    final = draft_module._run_loop(
        launch,
        launch_path,
        input_fn=lambda _prompt: next(commands),
        echo=echoed.append,
    )

    assert final is resumed
    assert launch_path.read_bytes() == launch_before
    assert resumed_path.read_text(encoding="utf-8") == json.dumps(
        resumed.to_dict(), indent=2
    )
    assert any(
        f"autosave target switched to {resumed_path}" in line for line in echoed
    )

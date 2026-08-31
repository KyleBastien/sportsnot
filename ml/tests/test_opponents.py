"""Tests for draft_oracle.optimize.opponents (US-020).

Covers the order-free conditional-logit fit (a synthetic affinity-driven manager is
recovered), sample-size blending toward the league and greedy fallback, the
:class:`FittedOpponentModel` implementing the US-019 interface (usable in
``run_draft`` / ``survival_probability``), the config-driven model swap, team-affinity
construction, base-position collapse, and held-out membership / per-pick validation on
a tiny synthetic league. All fixtures are in-memory -- no committed data, no network
(SPEC section 7).
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pandas as pd
import pytest

from draft_oracle.optimize.opponents import (
    Coefficients,
    FittedLeagueOpponents,
    FittedOpponentModel,
    OpponentEvalResult,
    OpponentFitConfig,
    base_position,
    build_team_affinity,
    dedupe_duplicate_events,
    evaluate_opponents,
    fit_opponent_models,
    load_committed_opponents,
    opponent_model_from_config,
    train_opponent_model_from_normalized,
)
from draft_oracle.optimize.simulator import (
    DraftAsset,
    DraftState,
    GreedyOpponentModel,
    run_draft,
    survival_probability,
    validate_draft,
)

# ── Fixtures ──────────────────────────────────────────────────────────────

_PICK_COLUMNS = [
    "season",
    "draft_event",
    "manager",
    "snake_slot",
    "pick_number",
    "position",
    "player_id",
    "team_id",
    "points_when_drafted",
    "matched_name",
    "player_or_team_name",
]


def _pick(
    season: int,
    event: str,
    manager: str,
    slot: int,
    position: str,
    player_id: int | None,
    team_id: int | None,
    *,
    points: float | None = None,
    pick_number: int | None = None,
) -> dict[str, object]:
    return {
        "season": season,
        "draft_event": event,
        "manager": manager,
        "snake_slot": slot,
        "pick_number": pick_number,
        "position": position,
        "player_id": player_id,
        "team_id": team_id,
        "points_when_drafted": points,
        "matched_name": f"P{player_id}" if player_id is not None else f"T{team_id}",
        "player_or_team_name": f"P{player_id}" if player_id is not None else f"T{team_id}",
    }


def _frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=_PICK_COLUMNS)


def _affinity_league(seasons: tuple[int, ...]) -> pd.DataFrame:
    """Two managers who each *always* draft their favourite team's players.

    Manager ``home`` only drafts team 1 players; ``away`` only drafts team 2. Every
    event offers both teams' players, so a public-ranking-only model cannot separate
    them -- only affinity does. Snake seats and a shared pool make the events replayable.
    """
    rows: list[dict[str, object]] = []
    pid = 1000
    for season in seasons:
        for event in ("R1", "R2"):
            for slot, (manager, team) in enumerate([("home", 1), ("away", 2)], start=1):
                # each manager takes 3 F from their own team + 1 D from their own team
                for _ in range(3):
                    rows.append(
                        _pick(season, event, manager, slot, "F", pid, team, points=float(pid % 7))
                    )
                    pid += 1
                rows.append(
                    _pick(season, event, manager, slot, "D", pid, team, points=float(pid % 5))
                )
                pid += 1
            # cross pollute the pool: each manager COULD have taken the other's players,
            # they simply never do -> pure affinity signal.
    return _frame(rows)


def _skater(key: str, position: str, rank: float, team_id: int, player_id: int) -> DraftAsset:
    return DraftAsset(
        key=key,
        name=key,
        position=position,  # type: ignore[arg-type]
        rank_value=rank,
        player_id=player_id,
        team_id=team_id,
    )


# ── base_position / affinity ──────────────────────────────────────────────


def test_base_position_collapses_ir_and_drops_unknown() -> None:
    assert base_position("F") == "F"
    assert base_position("IR_F") == "F"
    assert base_position("IR_D") == "D"
    assert base_position("G") == "G"
    assert base_position("") is None
    assert base_position("BENCH") is None


def test_build_team_affinity_is_a_fraction() -> None:
    frame = _frame(
        [
            _pick(2024, "R1", "kyle", 1, "F", 10, 5),
            _pick(2024, "R1", "kyle", 1, "F", 11, 5),
            _pick(2024, "R1", "kyle", 1, "D", 12, 7),
            _pick(2024, "R1", "ben", 2, "F", 20, 9),
        ]
    )
    affinity = build_team_affinity(frame)
    assert affinity["kyle"][5] == pytest.approx(2 / 3)
    assert affinity["kyle"][7] == pytest.approx(1 / 3)
    assert affinity["ben"][9] == pytest.approx(1.0)


# ── Fit ────────────────────────────────────────────────────────────────────


def test_fit_recovers_positive_affinity_signal() -> None:
    picks = _affinity_league((2024, 2025))
    fitted = fit_opponent_models(picks, OpponentFitConfig(min_manager_picks=4))
    # affinity dominates because managers only ever draft their own team
    assert fitted.league.affinity > 0.5
    assert "home" in fitted.per_manager
    assert "away" in fitted.per_manager


def test_league_blends_toward_fallback_when_data_is_thin() -> None:
    picks = _affinity_league((2024,))
    # a tiny slice + a huge fallback half-weight => league is pulled toward the fallback
    cfg = OpponentFitConfig(league_fallback_k=10_000.0, fallback_rank=1.5)
    fitted = fit_opponent_models(picks, cfg)
    assert fitted.league.rank == pytest.approx(1.5, abs=0.2)
    assert fitted.league.affinity == pytest.approx(0.0, abs=0.2)


def test_manager_below_threshold_uses_league_model() -> None:
    picks = _affinity_league((2024, 2025))
    fitted = fit_opponent_models(picks, OpponentFitConfig(min_manager_picks=10_000))
    assert fitted.per_manager == {}
    # model_for falls back to the league coefficients
    model = fitted.model_for("home")
    assert model.coefficients == fitted.league


def test_coefficients_blend_is_convex() -> None:
    a = Coefficients(rank=2.0, affinity=4.0)
    b = Coefficients(rank=0.0, affinity=0.0)
    assert a.blend(b, 0.25) == Coefficients(rank=0.5, affinity=1.0)
    assert a.blend(b, 1.0) == a
    assert a.blend(b, 0.0) == b
    # weight is clamped to [0, 1]
    assert a.blend(b, 2.0) == a


# ── FittedOpponentModel behaviour ──────────────────────────────────────────


def _state(assets: list[DraftAsset], managers: list[str], *, allow_ir: bool = False) -> DraftState:
    return DraftState.new(managers, assets, allow_ir=allow_ir)


def test_fitted_model_prefers_its_managers_favourite_team() -> None:
    assets = [
        _skater("P1", "F", 5.0, team_id=1, player_id=1),
        _skater("P2", "F", 5.0, team_id=2, player_id=2),
    ]
    state = _state(assets, ["home"])
    model = FittedOpponentModel(
        coefficients=Coefficients(rank=0.0, affinity=5.0),
        affinity={1: 0.9, 2: 0.0},
        temperature=0.0,
    )
    picked = model.pick(state, "home", random.Random(0))
    assert picked.key == "P1"


def test_fitted_model_is_deterministic_at_zero_temperature() -> None:
    assets = [
        _skater("P1", "F", 9.0, team_id=1, player_id=1),
        _skater("P2", "F", 3.0, team_id=1, player_id=2),
    ]
    model = FittedOpponentModel(
        coefficients=Coefficients(rank=1.0, affinity=0.0),
        affinity={},
        temperature=0.0,
    )
    first = model.pick(_state(assets, ["m"]), "m", random.Random(1))
    second = model.pick(_state(assets, ["m"]), "m", random.Random(2))
    assert first.key == second.key == "P1"  # higher rank_value wins


def test_fitted_model_raises_without_legal_asset() -> None:
    model = FittedOpponentModel(coefficients=Coefficients(0.0, 0.0), affinity={})
    empty = _state([], ["m"])
    with pytest.raises(ValueError, match="no legal asset"):
        model.pick(empty, "m", random.Random(0))


def test_fitted_model_drops_into_run_draft_and_validates() -> None:
    # exact 2-manager pool: 5F/3D + 1 team goalie each = a full rules-valid roster
    assets: list[DraftAsset] = []
    pid = 1
    rank = 100.0
    for _ in range(10):
        assets.append(_skater(f"F{pid}", "F", rank, team_id=1 + (pid % 4), player_id=pid))
        pid += 1
        rank -= 1.0
    for _ in range(6):
        assets.append(_skater(f"D{pid}", "D", rank, team_id=1 + (pid % 4), player_id=pid))
        pid += 1
        rank -= 1.0
    assets.append(DraftAsset(key="G7", name="G7", position="G", rank_value=5.0, team_id=7))
    assets.append(DraftAsset(key="G8", name="G8", position="G", rank_value=4.0, team_id=8))

    fitted = fit_opponent_models(_affinity_league((2024, 2025)), OpponentFitConfig())
    models = {"home": fitted.model_for("home"), "away": fitted.model_for("away")}
    state = _state(assets, ["home", "away"])
    run_draft(state, models, seed=3)
    results = validate_draft(state)
    assert all(result.valid for result in results.values())


def test_fitted_model_works_in_survival_probability() -> None:
    assets = [
        _skater("P1", "F", 9.0, team_id=1, player_id=1),
        _skater("P2", "F", 8.0, team_id=1, player_id=2),
        _skater("P3", "F", 7.0, team_id=1, player_id=3),
    ]
    state = _state(assets, ["a", "b"])
    model = FittedOpponentModel(
        coefficients=Coefficients(rank=3.0, affinity=0.0), affinity={}, temperature=0.5
    )
    # the top-ranked asset rarely survives the opponent pick before 'a' is up again
    prob = survival_probability(state, assets[0], "a", model, rollouts=200, seed=5)
    assert 0.0 <= prob <= 1.0


# ── Config swap ────────────────────────────────────────────────────────────


def test_opponent_model_from_config_greedy() -> None:
    model = opponent_model_from_config("greedy", need_weight=2.0, temperature=0.0)
    assert isinstance(model, GreedyOpponentModel)
    assert model.need_weight == 2.0


def test_opponent_model_from_config_fitted() -> None:
    fitted = fit_opponent_models(_affinity_league((2024, 2025)), OpponentFitConfig())
    model = opponent_model_from_config("fitted", manager="home", fitted=fitted)
    assert isinstance(model, FittedOpponentModel)


def test_opponent_model_from_config_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown opponent model"):
        opponent_model_from_config("magic")


def test_opponent_model_from_config_fitted_requires_result() -> None:
    with pytest.raises(ValueError, match="requires a FittedLeagueOpponents"):
        opponent_model_from_config("fitted")


# ── Held-out validation ────────────────────────────────────────────────────


def test_evaluation_beats_fallback_on_pure_affinity_league() -> None:
    # a league driven entirely by team fandom is exactly where greedy fails and the
    # fitted model should win the membership comparison on every held-out season.
    picks = _affinity_league((2024, 2025, 2026))
    result = evaluate_opponents(picks, OpponentFitConfig(min_manager_picks=4))
    assert isinstance(result, OpponentEvalResult)
    assert len(result.membership) == 3
    for score in result.membership:
        assert score.fitted_accuracy >= score.greedy_accuracy
    assert result.seasons_beating_fallback >= 2


def test_per_pick_validation_runs_when_true_order_present() -> None:
    rows: list[dict[str, object]] = []
    # two order-free training seasons ...
    rows.extend(_affinity_league((2024, 2025)).to_dict("records"))  # type: ignore[arg-type]
    # ... plus one true-order (app) event to validate per-pick
    pick_no = 1
    for slot, (manager, team) in enumerate([("home", 1), ("away", 2)], start=1):
        for _ in range(3):
            rows.append(
                _pick(
                    2026,
                    "R1",
                    manager,
                    slot,
                    "F",
                    9000 + pick_no,
                    team,
                    points=1.0,
                    pick_number=pick_no,
                )
            )
            pick_no += 1
    picks = _frame(rows)
    result = evaluate_opponents(picks, OpponentFitConfig(min_manager_picks=4))
    assert result.per_pick is not None
    assert result.per_pick.picks > 0
    assert 0.0 <= result.per_pick.fitted_top1 <= 1.0


def test_membership_report_and_manifest_shapes() -> None:
    picks = _affinity_league((2024, 2025))
    result = evaluate_opponents(picks, OpponentFitConfig(min_manager_picks=4))
    manifest = result.manifest()
    assert "membership" in manifest
    assert "seasons_beating_fallback" in manifest
    lines = result.report_lines()
    assert any("Held-out validation" in line for line in lines)


# ── Duplicate-event dedupe + league isolation (US-106) ─────────────────────

_REAL_LEAGUE_PICKS = Path("data/normalized/league_draft_picks.parquet")


def _dup_row(
    league: str, source: str, manager: str, slot: int, player_id: int, team_id: int
) -> dict[str, object]:
    return {
        "season": 2026,
        "league_name": league,
        "draft_event": "R1",
        "source": source,
        "manager": manager,
        "snake_slot": slot,
        "pick_number": None,
        "position": "F",
        "player_id": player_id,
        "team_id": team_id,
        "points_when_drafted": 1.0,
        "points_excluded": False,
        "matched_name": f"P{player_id}",
        "player_or_team_name": f"P{player_id}",
    }


def _dup_frame() -> pd.DataFrame:
    """One real 2026 Gemmell draft recorded twice (sheet + app) plus a second league."""
    rows: list[dict[str, object]] = []
    for source in ("sheet", "app"):
        for slot, manager in enumerate(("ben", "kyle"), start=1):
            rows.append(_dup_row("The Gemmell Cup", source, manager, slot, 100 + slot, 5))
    for slot, manager in enumerate(("tobi", "kyle"), start=1):
        rows.append(_dup_row("Press Play-offs", "app", manager, slot, 200 + slot, 9))
    frame = pd.DataFrame(rows)
    frame.loc[
        (frame["league_name"] == "The Gemmell Cup")
        & (frame["source"] == "sheet")
        & (frame["manager"] == "ben"),
        "points_excluded",
    ] = True
    return frame


def test_dedupe_prefers_app_over_sheet_copy() -> None:
    deduped = dedupe_duplicate_events(_dup_frame())
    gemmell = deduped[deduped["league_name"] == "The Gemmell Cup"]
    assert set(gemmell["source"]) == {"app"}  # the sheet copy is dropped
    assert len(gemmell) == 2  # not double-counted
    # the separate league (app only) is untouched
    assert len(deduped[deduped["league_name"] == "Press Play-offs"]) == 2


def test_dedupe_carries_exclusion_flag_from_dropped_sheet_copy() -> None:
    deduped = dedupe_duplicate_events(_dup_frame())
    ben = deduped[
        (deduped["league_name"] == "The Gemmell Cup") & (deduped["manager"] == "ben")
    ].iloc[0]
    assert ben["source"] == "app"
    assert bool(ben["points_excluded"]) is True


def test_dedupe_is_noop_without_source_or_league_columns() -> None:
    frame = _affinity_league((2024,))
    pd.testing.assert_frame_equal(dedupe_duplicate_events(frame), frame)


def test_fitted_counts_are_deduped_and_within_league() -> None:
    """Per-manager choice counts match hand-counted truth after the app/sheet dedupe."""
    fitted = fit_opponent_models(_dup_frame(), OpponentFitConfig(min_manager_picks=1))
    # sheet Gemmell copy dropped -> ben once; kyle plays both leagues -> twice.
    assert fitted.manager_pick_counts["ben"] == 1
    assert fitted.manager_pick_counts["tobi"] == 1
    assert fitted.manager_pick_counts["kyle"] == 2


def test_fitted_counts_match_real_league_truth() -> None:
    """Regression against the committed table: no double-counted Gemmell rows.

    Before US-106 the duplicated 2026 Gemmell sheet+app copies inflated ben/judah/levi
    to 105 and kyle to 138. Hand-counted truth after preferring source='app': the three
    Gemmell-only managers hold 87 picks each across 2024-26, kyle also plays the separate
    Press Play-offs league (+33 -> 120), and the Press-only managers hold 33 each.
    """
    if not _REAL_LEAGUE_PICKS.exists():
        pytest.skip("committed league_draft_picks parquet not present")
    picks = pd.read_parquet(_REAL_LEAGUE_PICKS)
    deduped = dedupe_duplicate_events(picks)
    tuch = deduped.loc[
        (deduped["season"] == 2026)
        & (deduped["league_name"] == "The Gemmell Cup")
        & (deduped["draft_event"] == "R2")
        & (deduped["manager"] == "ben")
        & (deduped["player_id"] == 8477949)
    ]
    assert len(tuch) == 1
    assert tuch.iloc[0]["source"] == "app"
    assert bool(tuch.iloc[0]["points_excluded"]) is True

    counts = fit_opponent_models(picks, OpponentFitConfig()).manager_pick_counts
    assert counts["ben"] == 87
    assert counts["judah"] == 87
    assert counts["levi"] == 87
    assert counts["kyle"] == 87 + 33
    for press_manager in ("tobi", "paul.markhauser", "connor.fehr"):
        assert counts[press_manager] == 33
    # the old double-count pushed a manager to 105/138; the true ceiling is kyle at 120.
    assert max(counts.values()) == 120


# ── Committed artifact load path (US-113) ─────────────────────────────────


def _tiny_fitted() -> FittedLeagueOpponents:
    return FittedLeagueOpponents(
        league=Coefficients(rank=0.25, affinity=1.5),
        per_manager={"ben": Coefficients(rank=-0.1, affinity=2.0)},
        affinity={"ben": {1: 0.5, 6: 0.25}},
        manager_pick_counts={"ben": 90},
        total_picks=120,
        config=OpponentFitConfig(need_weight=1.0),
    )


def test_manifest_round_trips_through_from_manifest() -> None:
    original = _tiny_fitted()
    rebuilt = FittedLeagueOpponents.from_manifest(original.manifest())
    assert rebuilt.league == original.league
    assert rebuilt.per_manager == original.per_manager
    assert rebuilt.affinity == {"ben": {1: 0.5, 6: 0.25}}
    assert rebuilt.total_picks == original.total_picks
    assert rebuilt.manager_pick_counts == original.manager_pick_counts


def test_load_reads_only_manifest_json(tmp_path: Path) -> None:
    fitted = _tiny_fitted()
    payload = {
        "model": fitted.manifest(),
        "config": {"seed": 42, "need_weight": 1.0, "min_manager_picks": 20},
    }
    (tmp_path / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    loaded = FittedLeagueOpponents.load(tmp_path)
    assert loaded.config.seed == 42
    model = loaded.model_for("ben")
    assert model.coefficients == Coefficients(rank=-0.1, affinity=2.0)
    assert model.affinity == {1: 0.5, 6: 0.25}


def test_load_committed_opponents_returns_none_when_absent(tmp_path: Path) -> None:
    assert load_committed_opponents(tmp_path) is None


def test_load_committed_opponents_loads_when_present(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps(_tiny_fitted().manifest()), encoding="utf-8"
    )
    loaded = load_committed_opponents(tmp_path)
    assert loaded is not None
    assert loaded.league == Coefficients(rank=0.25, affinity=1.5)


def test_train_writes_affinity_and_reloads(tmp_path: Path) -> None:
    """The committed-artifact path is self-sufficient: train -> load reproduces it."""
    if not _REAL_LEAGUE_PICKS.exists():
        pytest.skip("committed league_draft_picks parquet not present")
    result = train_opponent_model_from_normalized(
        normalized_dir=_REAL_LEAGUE_PICKS.parent,
        artifact_dir=tmp_path,
    )
    reloaded = FittedLeagueOpponents.load(tmp_path)
    # The artifact rounds to 6 dp; the reload reproduces the *committed* model exactly.
    expected = FittedLeagueOpponents.from_manifest(result.fitted.manifest())
    assert reloaded.league == expected.league
    assert reloaded.per_manager == expected.per_manager
    # affinity persisted so the draft-time model is faithful, not affinity-blind.
    assert reloaded.affinity == expected.affinity
    assert reloaded.model_for("ben").affinity

"""Backtest replay engine (US-025).

Replays historical playoff rounds end-to-end so the oracle's edge is *measured*,
not assumed:

1. **As-of projections** — for every playoff round of a backtested season the
   US-017 projection artifact is rebuilt using only games played strictly before
   the round started (:func:`draft_oracle.projection_artifact.build_projection_artifact`
   enforces the cutoff; this harness re-asserts it with an independent guard).
2. **Simulated drafts** — the oracle is seated in *every* snake slot in turn and
   drafts against the opponents. Where the league's draft history covers the
   season the fitted US-020 opponent model drives the opponents (trained
   leave-one-season-out so the backtested season never leaks into its own
   opponents); otherwise the greedy fallback is used.
3. **Actual scoring** — every drafted roster is scored with the *actual*
   historical round results through :mod:`draft_oracle.rules` (skater goals +
   assists; the goalie slot via ``goalie_series_points`` over the team's real
   series). Projections drive the *decisions*; actuals only ever drive the
   *score*, never a pick.

A hard leakage guard (:func:`assert_round_inputs_leakfree`) fails the backtest
loudly if any round-``N`` game leaks into the as-of inputs for round ``N``. Runs
are seeded and reproducible: ``(snapshot, seed)`` fully determines every roster
and score. Per-round intermediate results are persisted under
``artifacts/backtests/<run-id>/rounds/`` so reporting (US-026) can run separately.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pandas as pd

from draft_oracle.backtest._replay_eval import (
    _build_projection_eval,
    _build_series_evals,
    _market_series_prob,
    _ProjectionEvalRequest,
    _round_series,
)
from draft_oracle.backtest._replay_events import (
    _draft_events,
    _draft_shortfall,
    _season_id_for,
    _season_rounds,
)
from draft_oracle.backtest._replay_league import _league_comparisons
from draft_oracle.backtest._replay_leakage import (
    RoundLeakageCheck,
    assert_round_inputs_leakfree,
    round_game_ids,
)
from draft_oracle.backtest._replay_opponents import (
    _fit_opponents_for_season,
    _managers_and_opponents,
)
from draft_oracle.backtest._replay_playout import _OracleDraftRequest, _play_oracle_draft
from draft_oracle.backtest._replay_scoring import (
    ScoreContext,
    _score_active_roster,
    _score_league_roster,
    skater_actual_points,
    team_actual_goalie_points,
)
from draft_oracle.backtest._replay_types import (
    STRATEGIES,
    BacktestConfig,
    BacktestResult,
    LeagueComparison,
    LeagueManagerRoster,
    ProjectionEval,
    RoundResult,
    SeriesEval,
    SlotResult,
    Strategy,
)
from draft_oracle.optimize.recommend import build_pool_from_frames
from draft_oracle.optimize.simulator import (
    DraftAsset,
    DraftState,
    OpponentModel,
)
from draft_oracle.projection_artifact import (
    DEFAULT_NORMALIZED_DIR,
    SNAPSHOTS_SUBDIR,
    ProjectArtifactResult,
    _load_league_picks,
    _load_tables,
    _require_complete_snapshot,
    _snapshot_id_for,
    build_projection_artifact,
)
from draft_oracle.provenance import add_git_provenance

for _exported in (
    assert_round_inputs_leakfree,
    round_game_ids,
    skater_actual_points,
    team_actual_goalie_points,
    _score_active_roster,
    _score_league_roster,
    _draft_events,
    _league_comparisons,
    _market_series_prob,
):
    _exported.__module__ = __name__

__all__ = [
    "DEFAULT_BACKTEST_ROOT",
    "STRATEGIES",
    "BacktestConfig",
    "BacktestResult",
    "LeagueComparison",
    "LeagueManagerRoster",
    "ProjectionEval",
    "RoundLeakageCheck",
    "RoundResult",
    "ScoreContext",
    "SeriesEval",
    "SlotResult",
    "Strategy",
    "_draft_events",
    "_league_comparisons",
    "_market_series_prob",
    "_score_active_roster",
    "_score_league_roster",
    "assert_round_inputs_leakfree",
    "round_game_ids",
    "run_backtest",
    "run_backtest_from_normalized",
    "skater_actual_points",
    "team_actual_goalie_points",
]

DEFAULT_BACKTEST_ROOT = Path("artifacts/backtests")










# ── Round / season / run orchestration ─────────────────────────────────────


@dataclass(frozen=True)
class _ReplayRoundSetup:
    artifact: ProjectArtifactResult
    projection_eval: ProjectionEval
    season_id: int
    scored_rounds: list[int]
    series_evals: list[SeriesEval]


@dataclass(frozen=True)
class _ReplayRoundRequest:
    tables: dict[str, pd.DataFrame]
    season: int
    playoff_round: int
    league_picks: pd.DataFrame | None
    injuries: pd.DataFrame | None
    odds: pd.DataFrame | None
    snapshot_id: str
    skater_actual: dict[tuple[int, int, int], int]
    team_actual: dict[tuple[int, int, int], int]
    config: BacktestConfig
    scored_rounds: Sequence[int] | None = None


@dataclass(frozen=True)
class _RunBacktestRequest:
    tables: dict[str, pd.DataFrame]
    seasons: list[int]
    league_picks: pd.DataFrame | None = None
    odds: pd.DataFrame | None = None
    snapshot_id: str = "backtest"
    config: BacktestConfig | None = None


@dataclass(frozen=True)
class _RunBacktestOptions:
    league_picks: pd.DataFrame | None
    odds: pd.DataFrame | None
    snapshot_id: str
    config: BacktestConfig | None


@dataclass(frozen=True)
class _SlotSimulationRequest:
    base_state: DraftState
    managers_list: list[str]
    opponent_model: OpponentModel | dict[str, OpponentModel]
    config: BacktestConfig
    score_context: ScoreContext


@dataclass(frozen=True)
class _RoundResultInput:
    season: int
    playoff_round: int
    setup: _ReplayRoundSetup
    cutoff: str
    opponents_kind: str
    warnings: list[str]
    slot_results: list[SlotResult]


@dataclass(frozen=True)
class _ReplayRoundContext:
    managers_list: list[str]
    opponent_model: OpponentModel | dict[str, OpponentModel]
    opponents_kind: str
    warnings: list[str]
    score_context: ScoreContext
    pool: list[DraftAsset]


def _prepare_round_setup(request: _ReplayRoundRequest) -> _ReplayRoundSetup:
    scored = list(request.scored_rounds) if request.scored_rounds else [request.playoff_round]
    artifact = build_projection_artifact(
        request.tables["skater_games"],
        request.tables["players"],
        request.tables["team_games"],
        request.tables["series"],
        season=request.season,
        playoff_round=request.playoff_round,
        snapshot_id=request.snapshot_id,
        injuries=request.injuries,
        league_picks=request.league_picks,
        config=replace(request.config.artifact_config(), slot_strategies=False),
    )
    season_id = _season_id_for(request.tables["series"], request.season)
    round_series = _round_series(request.tables["series"], request.season, request.playoff_round)
    projection_eval = _build_projection_eval(
        _ProjectionEvalRequest(
            artifact,
            request.skater_actual,
            request.team_actual,
            season_id,
            scored,
        )
    )
    series_evals = _build_series_evals(
        artifact,
        round_series,
        request.odds,
        season=request.season,
    )
    return _ReplayRoundSetup(
        artifact=artifact,
        projection_eval=projection_eval,
        season_id=season_id,
        scored_rounds=scored,
        series_evals=series_evals,
    )


def _assert_replay_inputs_leakfree(
    tables: dict[str, pd.DataFrame],
    *,
    season_id: int,
    cutoff: str,
    scored_rounds: Sequence[int],
) -> None:
    round_ids: set[int] = set()
    for scored_round in scored_rounds:
        round_ids |= round_game_ids(
            tables["team_games"],
            tables["series"],
            season_id=season_id,
            playoff_round=scored_round,
        )
    assert_round_inputs_leakfree(
        RoundLeakageCheck(tables["team_games"], round_ids, cutoff, label="team")
    )
    assert_round_inputs_leakfree(
        RoundLeakageCheck(
            tables["skater_games"],
            round_ids,
            cutoff,
            label="skater",
            authoritative_dates=tables["team_games"],
        )
    )


def _simulate_slot_results(
    request: _SlotSimulationRequest,
) -> list[SlotResult]:
    slot_results: list[SlotResult] = []
    for strategy in request.config.strategies:
        for seat in range(1, request.config.managers + 1):
            oracle = request.managers_list[seat - 1]
            for draft_index in range(request.config.n_drafts):
                draft_seed = request.config.seed + draft_index
                final = _play_oracle_draft(
                    _OracleDraftRequest(
                        request.base_state,
                        oracle,
                        strategy,
                        request.opponent_model,
                        request.config,
                        draft_seed,
                    )
                )
                opponent_points = {
                    manager: _score_active_roster(final, manager, request.score_context)
                    for manager in request.managers_list
                    if manager != oracle
                }
                oracle_points = _score_active_roster(final, oracle, request.score_context)
                slot_results.append(
                    SlotResult(
                        strategy=strategy,
                        seat=seat,
                        oracle_manager=oracle,
                        draft_index=draft_index,
                        oracle_points=oracle_points,
                        opponent_points=opponent_points,
                        roster_keys=[asset.key for asset in final.rosters[oracle].all_assets()],
                    )
                )
    return slot_results


def _round_result(request: _RoundResultInput) -> RoundResult:
    return RoundResult(
        season=request.season,
        season_id=request.setup.season_id,
        playoff_round=request.playoff_round,
        as_of_cutoff=request.cutoff,
        opponents_kind=request.opponents_kind,
        eligible_team_abbrevs=list(request.setup.artifact.manifest["eligible_team_abbrevs"]),
        leakage_ok=True,
        scored_rounds=request.setup.scored_rounds,
        slot_results=request.slot_results,
        warnings=request.warnings,
        projection_eval=request.setup.projection_eval,
        series_evals=request.setup.series_evals,
    )


def replay_round(request: _ReplayRoundRequest) -> RoundResult:
    """Replay one draft event: as-of projections, drafts in every slot, scoring.

    ``playoff_round`` is the round whose as-of projection drives the draft;
    ``scored_rounds`` is every round the resulting roster is scored across (just
    ``playoff_round`` for R1/R2, but both the conference final and Cup Final for the
    combined ``R3_4`` draft). The projection artifact folds the conditional next-round
    value in automatically when it is a combined event.
    """
    setup = _prepare_round_setup(request)
    cutoff = setup.artifact.as_of_cutoff
    _assert_replay_inputs_leakfree(
        request.tables,
        season_id=setup.season_id,
        cutoff=cutoff,
        scored_rounds=setup.scored_rounds,
    )
    context = _replay_round_context(request, setup)
    shortfall = _draft_shortfall(context.pool, request.config.managers, request.config.ir)
    if shortfall is not None:
        warnings = list(context.warnings)
        warnings.append(
            f"round skipped: pool cannot fill a {request.config.managers}-manager draft "
            f"({shortfall}); late rounds have too few eligible teams"
        )
        return _round_result(
            _RoundResultInput(
                season=request.season,
                playoff_round=request.playoff_round,
                setup=setup,
                cutoff=cutoff,
                opponents_kind=context.opponents_kind,
                warnings=warnings,
                slot_results=[],
            )
        )

    slot_results = _simulate_slot_results(
        _SlotSimulationRequest(
            DraftState.new(context.managers_list, context.pool, allow_ir=request.config.ir),
            context.managers_list,
            context.opponent_model,
            request.config,
            context.score_context,
        )
    )

    return _round_result(
        _RoundResultInput(
            season=request.season,
            playoff_round=request.playoff_round,
            setup=setup,
            cutoff=cutoff,
            opponents_kind=context.opponents_kind,
            warnings=context.warnings,
            slot_results=slot_results,
        )
    )


def _replay_round_context(
    request: _ReplayRoundRequest,
    setup: _ReplayRoundSetup,
) -> _ReplayRoundContext:
    fitted = _fit_opponents_for_season(request.league_picks, request.season, request.config)
    managers_list, opponent_model, opponents_kind = _managers_and_opponents(
        fitted,
        request.config,
    )
    pool = build_pool_from_frames(
        setup.artifact.skaters,
        setup.artifact.teams,
        ir=request.config.ir,
    )
    return _ReplayRoundContext(
        managers_list=managers_list,
        opponent_model=opponent_model,
        opponents_kind=opponents_kind,
        warnings=list(setup.artifact.warnings),
        score_context=ScoreContext(
            request.skater_actual,
            request.team_actual,
            setup.season_id,
            setup.scored_rounds,
        ),
        pool=pool,
    )












def run_backtest(
    tables: _RunBacktestRequest | dict[str, pd.DataFrame],
    seasons: list[int] | None = None,
    **legacy: object,
) -> BacktestResult:
    """Replay every playoff round of each season in ``seasons`` end-to-end.

    Builds the actual-result lookups once, then replays each round (as-of
    projections, drafts in every slot, actual scoring) under the leakage guard.
    ``odds`` (de-vigged historical betting lines) power the market-aware series-Brier
    track and are never used to make a pick. Every round runs with an **empty
    injuries input**: no historical injury snapshot exists (SPEC §5), and injecting
    today's live snapshot into a past round would leak future roster status into
    picks under ``ir=True`` (CODE_REVIEW m-4). Deterministic given ``(tables, seed)``.
    """
    request = _resolve_run_backtest_request(
        tables,
        seasons,
        _RunBacktestOptions(
            league_picks=cast("pd.DataFrame | None", legacy.get("league_picks")),
            odds=cast("pd.DataFrame | None", legacy.get("odds")),
            snapshot_id=cast("str", legacy.get("snapshot_id", "backtest")),
            config=cast("BacktestConfig | None", legacy.get("config")),
        ),
    )
    cfg = request.config or BacktestConfig()
    if not request.seasons:
        raise ValueError("seasons must be non-empty")
    skater_actual = skater_actual_points(
        request.tables["skater_games"],
        request.tables["series"],
    )
    team_actual = team_actual_goalie_points(
        request.tables["team_games"],
        request.tables["series"],
    )

    rounds: list[RoundResult] = []
    for season in request.seasons:
        for draft_round, scored_rounds in _draft_events(
            _season_rounds(request.tables["series"], season)
        ):
            rounds.append(
                replay_round(
                    _ReplayRoundRequest(
                        tables=request.tables,
                        season=season,
                        playoff_round=draft_round,
                        league_picks=request.league_picks,
                        injuries=None,
                        odds=request.odds,
                        snapshot_id=request.snapshot_id,
                        skater_actual=skater_actual,
                        team_actual=team_actual,
                        config=cfg,
                        scored_rounds=scored_rounds,
                    )
                )
            )

    comparisons = _league_comparisons(rounds, request.league_picks, skater_actual, team_actual)

    return BacktestResult(
        run_id=cfg.resolved_run_id(request.seasons),
        seasons=list(request.seasons),
        config=cfg,
        rounds=rounds,
        generated_at=datetime.now(UTC).isoformat(),
        league_comparisons=comparisons,
    )


def _resolve_run_backtest_request(
    tables: _RunBacktestRequest | dict[str, pd.DataFrame],
    seasons: list[int] | None,
    options: _RunBacktestOptions,
) -> _RunBacktestRequest:
    if isinstance(tables, _RunBacktestRequest):
        return tables
    if seasons is None:
        raise ValueError("seasons must be provided")
    return _RunBacktestRequest(
        tables=tables,
        seasons=seasons,
        league_picks=options.league_picks,
        odds=options.odds,
        snapshot_id=options.snapshot_id,
        config=options.config,
    )


def write_backtest(result: BacktestResult, root: Path = DEFAULT_BACKTEST_ROOT) -> Path:
    """Persist the run manifest + per-round intermediates under ``root/<run-id>/``.

    ``manifest.json`` is committed; the per-round JSON files under ``rounds/`` are
    regenerable intermediates (gitignored) that reporting (US-026) reads back.
    """
    manifest = add_git_provenance(result.manifest())
    out_dir = root / result.run_id
    rounds_dir = out_dir / "rounds"
    rounds_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    for round_result in result.rounds:
        name = f"{round_result.season}-r{round_result.playoff_round}.json"
        (rounds_dir / name).write_text(
            json.dumps(round_result.manifest(), indent=2) + "\n", encoding="utf-8"
        )
    return out_dir


def _load_odds(normalized_dir: Path) -> pd.DataFrame | None:
    """Load committed de-vigged betting odds if present, else ``None``.

    Powers the market-aware series-Brier track in reporting; never used to make a pick.
    """
    path = normalized_dir / "odds.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path)


def run_backtest_from_normalized(
    request: _RunBacktestFromNormalizedRequest | list[int] | None = None,
    **legacy: object,
) -> tuple[BacktestResult, Path]:
    """Load normalized tables, run the backtest, and persist it to disk.

    When ``snapshot`` is pinned every consumed input (core tables, league picks,
    odds) is read from the frozen snapshot copy so ``(snapshot, seed)`` fully
    determines every roster; an incomplete snapshot makes the pinned run fail
    loudly (M-10). Otherwise the live normalized tables are used. Writes
    ``manifest.json`` and a committed ``report.md`` under
    ``backtest_root/<run-id>/`` and returns the result and that run directory.
    """
    from draft_oracle.backtest.report import write_report

    resolved = _resolve_run_backtest_from_normalized_request(
        request,
        seasons=cast("list[int] | None", legacy.get("seasons")),
        normalized_dir=cast("Path", legacy.get("normalized_dir", DEFAULT_NORMALIZED_DIR)),
        backtest_root=cast("Path", legacy.get("backtest_root", DEFAULT_BACKTEST_ROOT)),
        snapshot=cast("str | None", legacy.get("snapshot")),
        config=cast("BacktestConfig | None", legacy.get("config")),
    )
    source_dir = (
        resolved.normalized_dir / SNAPSHOTS_SUBDIR / resolved.snapshot
        if resolved.snapshot
        else resolved.normalized_dir
    )
    if resolved.snapshot is not None:
        _require_complete_snapshot(source_dir)
    tables = _load_tables(source_dir)
    league_picks = _load_league_picks(source_dir)
    odds = _load_odds(source_dir)
    snapshot_id = _snapshot_id_for(source_dir, resolved.snapshot)

    # Historical rounds never receive the live injuries snapshot (CODE_REVIEW m-4);
    # run_backtest forces an empty injuries input for every replayed round.
    result = run_backtest(
        tables,
        resolved.seasons,
        league_picks=league_picks,
        odds=odds,
        snapshot_id=snapshot_id,
        config=resolved.config,
    )
    out_dir = write_backtest(result, resolved.backtest_root)
    write_report(result, out_dir)
    return result, out_dir


@dataclass(frozen=True)
class _RunBacktestFromNormalizedRequest:
    seasons: list[int]
    normalized_dir: Path = DEFAULT_NORMALIZED_DIR
    backtest_root: Path = DEFAULT_BACKTEST_ROOT
    snapshot: str | None = None
    config: BacktestConfig | None = None


def _resolve_run_backtest_from_normalized_request(
    request: _RunBacktestFromNormalizedRequest | list[int] | None,
    *,
    seasons: list[int] | None,
    normalized_dir: Path,
    backtest_root: Path,
    snapshot: str | None,
    config: BacktestConfig | None,
) -> _RunBacktestFromNormalizedRequest:
    if isinstance(request, _RunBacktestFromNormalizedRequest):
        return request
    if request is None:
        request = seasons
    if request is None:
        raise ValueError("seasons must be provided")
    return _RunBacktestFromNormalizedRequest(
        seasons=request,
        normalized_dir=normalized_dir,
        backtest_root=backtest_root,
        snapshot=snapshot,
        config=config,
    )

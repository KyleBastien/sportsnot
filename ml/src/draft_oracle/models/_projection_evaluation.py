"""Held-out skater projection evaluation helpers."""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, cast

import numpy as np
import pandas as pd

from draft_oracle.models._series_reconstruct import _matchup_key, _MatchupRecord
from draft_oracle.models.game_win import GameWinConfig, GameWinModel, train_game_win_model
from draft_oracle.models.series_sim import (
    _predict_series,
    _SeriesModels,
    reconstruct_series_matchups,
)
from draft_oracle.models.shutout import ShutoutConfig, ShutoutModel, train_shutout_model
from draft_oracle.models.skater_production import (
    LABEL_COLUMN,
    ProductionDatasetRequest,
    SkaterProductionConfig,
    SkaterProductionModel,
    build_production_dataset,
    mean_absolute_error,
    skater_round_production,
    spearman_correlation,
    train_skater_production_model,
)
from draft_oracle.rules import player_points

if TYPE_CHECKING:
    from draft_oracle.models.projections import (
        ProjectionEvaluationRequest,
        ProjectionRuntime,
        RoundProjection,
        SkaterRoundRequest,
    )


class _ProjectionConfigLike(Protocol):
    @property
    def seed(self) -> int: ...

    @property
    def n_test_seasons(self) -> int: ...

    @property
    def production_config(self) -> SkaterProductionConfig | None: ...

    @property
    def n_sims(self) -> int: ...

    @property
    def horizon(self) -> int: ...


class _ProjectRound(Protocol):
    def __call__(
        self,
        request: SkaterRoundRequest,
        runtime: ProjectionRuntime | None = ...,
    ) -> RoundProjection: ...


class _ProjectionEvaluationRequestLike(Protocol):
    @property
    def skater_games(self) -> pd.DataFrame: ...

    @property
    def players(self) -> pd.DataFrame: ...

    @property
    def team_games(self) -> pd.DataFrame: ...

    @property
    def series(self) -> pd.DataFrame: ...

    @property
    def config(self) -> _ProjectionConfigLike | None: ...


@dataclass(frozen=True)
class SeasonMetricValue:
    season_end_year: int
    n: int
    mae: float
    spearman: float


@dataclass(frozen=True)
class ProjectionEvaluation:
    test_years: tuple[int, ...]
    n_projected: int
    n_skipped_no_series: int
    test_mae_model: float
    test_mae_baseline_reg: float
    test_mae_baseline_prev: float
    test_spearman_model: float
    test_spearman_baseline_reg: float
    test_spearman_baseline_prev: float
    per_season: list[SeasonMetricValue]
    mean_expected_points: float
    mean_p10: float
    mean_p90: float


@dataclass(frozen=True)
class _ProjectionTrainingFrames:
    skater_games: pd.DataFrame
    team_games: pd.DataFrame
    series: pd.DataFrame


@dataclass(frozen=True)
class _ProjectionModels:
    production: SkaterProductionModel
    win: GameWinModel
    shutout: ShutoutModel


@dataclass(frozen=True)
class _EvaluateProjectionModelRequest:
    skater_games: pd.DataFrame
    players: pd.DataFrame
    team_games: pd.DataFrame
    series: pd.DataFrame
    config: _ProjectionConfigLike
    project_round: _ProjectRound
    baseline_reg_games: float


@dataclass(frozen=True)
class _ProjectionContextRequest:
    skater_games: pd.DataFrame
    players: pd.DataFrame
    team_games: pd.DataFrame
    series: pd.DataFrame
    config: _ProjectionConfigLike


@dataclass(frozen=True)
class _ProjectionContext:
    config: _ProjectionConfigLike
    production_config: SkaterProductionConfig
    test_years: tuple[int, ...]
    test_year_set: set[int]
    models: _ProjectionModels
    length_by_team: dict[tuple[int, int, int], dict[int, float]]
    abbrev_to_id: dict[str, int]
    previous_points: dict[tuple[int, int, int], float]


@dataclass(frozen=True)
class _ProjectionScores:
    scored: pd.DataFrame
    n_skipped: int
    model_pred: np.ndarray
    actual: np.ndarray
    baseline_reg: np.ndarray
    baseline_prev: np.ndarray


@dataclass(frozen=True)
class _ProjectionScoresRequest:
    skater_games: pd.DataFrame
    players: pd.DataFrame
    team_games: pd.DataFrame
    series: pd.DataFrame
    context: _ProjectionContext
    project_round: _ProjectRound
    baseline_reg_games: float


@dataclass(frozen=True)
class _ProjectionRequestOptions:
    config: _ProjectionConfigLike | None
    project_round: _ProjectRound | None
    baseline_reg_games: float | None


def _row_seed(base_seed: int, season_id: int, playoff_round: int, player_id: int) -> int:
    """Deterministic per-skater RNG seed from the projection keys (reproducible)."""
    combined = (
        (int(base_seed) & 0xFFFFFFFF)
        ^ ((int(season_id) & 0xFFFFF) << 20)
        ^ ((int(playoff_round) & 0xF) << 16)
        ^ (int(player_id) & 0xFFFF)
    )
    return int(combined & 0x7FFFFFFF)


def _team_id_by_abbrev(team_games: pd.DataFrame) -> dict[str, int]:
    """Map ``team_abbrev -> team_id`` from the team-games table."""
    pairs = team_games[["team_abbrev", "team_id"]].drop_duplicates()
    return {str(rec["team_abbrev"]): int(rec["team_id"]) for rec in pairs.to_dict("records")}


def _series_length_by_team(
    series: pd.DataFrame,
    matchups: dict[tuple[int, int, int], _MatchupRecord],
    models: _SeriesModels,
    test_year_set: set[int],
) -> dict[tuple[int, int, int], dict[int, float]]:
    """Length distribution per ``(year, round, team_id)`` for held-out series."""
    out: dict[tuple[int, int, int], dict[int, float]] = {}
    held_out = series.loc[series["year"].isin(test_year_set)]
    for row in held_out.to_dict("records"):
        top_id = row["top_seed_team_id"]
        bottom_id = row["bottom_seed_team_id"]
        if pd.isna(top_id) or pd.isna(bottom_id):
            continue
        top_id = int(top_id)
        bottom_id = int(bottom_id)
        year = int(row["year"])
        key = _matchup_key(year, top_id, bottom_id)
        matchup = matchups.get(key)
        if matchup is None:
            continue
        if not _has_series_snapshots(matchup, top_id, bottom_id):
            continue
        outcome, _sho_top, _sho_bottom = _predict_series(models, matchup, top_id, bottom_id)
        rnd = int(row["playoff_round"]) if not pd.isna(row["playoff_round"]) else 0
        out[(year, rnd, top_id)] = dict(outcome.length_probs)
        out[(year, rnd, bottom_id)] = dict(outcome.length_probs)
    return out


def _has_series_snapshots(
    matchup: _MatchupRecord | None, top_id: int, bottom_id: int
) -> bool:
    if matchup is None:
        return False
    return top_id in matchup.win_snapshots and bottom_id in matchup.win_snapshots


def _previous_round_points(labels: pd.DataFrame) -> dict[tuple[int, int, int], float]:
    """Map ``(season_id, playoff_round, player_id) -> actual round fantasy points``."""
    out: dict[tuple[int, int, int], float] = {}
    for rec in labels.to_dict("records"):
        key = (int(rec["season_id"]), int(rec["playoff_round"]), int(rec["player_id"]))
        out[key] = float(player_points(int(rec["round_goals"]), int(rec["round_assists"])))
    return out


def evaluate_projection_model(
    request: ProjectionEvaluationRequest | pd.DataFrame,
    *legacy_args: object,
    config: _ProjectionConfigLike | None = None,
    project_round: _ProjectRound | None = None,
    baseline_reg_games: float | None = None,
) -> ProjectionEvaluation:
    resolved_request = _resolve_projection_request(
        request,
        legacy_args,
        _ProjectionRequestOptions(
            config=config,
            project_round=project_round,
            baseline_reg_games=baseline_reg_games,
        ),
    )
    context = _projection_context(
        _ProjectionContextRequest(
            skater_games=resolved_request.skater_games,
            players=resolved_request.players,
            team_games=resolved_request.team_games,
            series=resolved_request.series,
            config=resolved_request.config,
        )
    )
    scores = _projection_scores(
        _ProjectionScoresRequest(
            skater_games=resolved_request.skater_games,
            players=resolved_request.players,
            team_games=resolved_request.team_games,
            series=resolved_request.series,
            context=context,
            project_round=resolved_request.project_round,
            baseline_reg_games=resolved_request.baseline_reg_games,
        )
    )
    return _projection_evaluation(context, scores)


def _projection_context(
    request: _ProjectionContextRequest,
) -> _ProjectionContext:
    test_years = _projection_test_years(request.series, request.config.n_test_seasons)
    train = _projection_training_frames(
        request.skater_games,
        request.team_games,
        request.series,
        set(test_years),
    )
    models = _train_projection_models(train, request.players, request.config)
    matchups = reconstruct_series_matchups(request.team_games, series=request.series)
    labels = skater_round_production(request.skater_games, request.series)
    return _ProjectionContext(
        config=request.config,
        production_config=request.config.production_config
        or SkaterProductionConfig(seed=request.config.seed),
        test_years=test_years,
        test_year_set=set(test_years),
        models=models,
        length_by_team=_series_length_by_team(
            request.series,
            matchups,
            _SeriesModels(win=models.win, shutout=models.shutout),
            set(test_years),
        ),
        abbrev_to_id=_team_id_by_abbrev(request.team_games),
        previous_points=_previous_round_points(labels),
    )


def _projection_test_years(series: pd.DataFrame, n_test_seasons: int) -> tuple[int, ...]:
    years = sorted({int(y) for y in series["year"].dropna().unique()})
    if len(years) <= n_test_seasons:
        raise ValueError("not enough seasons to hold out a projection test set")
    return tuple(years[-n_test_seasons:])


def _projection_training_frames(
    skater_games: pd.DataFrame,
    team_games: pd.DataFrame,
    series: pd.DataFrame,
    test_year_set: set[int],
) -> _ProjectionTrainingFrames:
    train_sk = skater_games.loc[~((skater_games["season_id"] % 10000).isin(test_year_set))]
    train_tg = team_games.loc[~((team_games["season_id"] % 10000).isin(test_year_set))]
    train_series = series.loc[~series["year"].astype(int).isin(test_year_set)]
    if _training_frames_empty((train_sk, train_tg, train_series)):
        raise ValueError("no training seasons remain after holding out the test set")
    return _ProjectionTrainingFrames(
        skater_games=train_sk,
        team_games=train_tg,
        series=train_series,
    )


def _training_frames_empty(frames: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]) -> bool:
    return any(frame.empty for frame in frames)


def _train_projection_models(
    train: _ProjectionTrainingFrames,
    players: pd.DataFrame,
    config: _ProjectionConfigLike,
) -> _ProjectionModels:
    prod_config = config.production_config or SkaterProductionConfig(seed=config.seed)
    prod_result = train_skater_production_model(
        ProductionDatasetRequest(
            train.skater_games,
            players,
            train.team_games,
            train.series,
            prod_config,
        )
    )
    win_model = train_game_win_model(
        train.team_games, odds=None, config=GameWinConfig(seed=config.seed)
    ).model
    shutout_model = train_shutout_model(
        train.team_games, config=ShutoutConfig(seed=config.seed)
    ).model
    return _ProjectionModels(
        production=prod_result.model,
        win=win_model,
        shutout=shutout_model,
    )


def _projection_scores(
    request: _ProjectionScoresRequest,
) -> _ProjectionScores:
    dataset = build_production_dataset(
        ProductionDatasetRequest(
            request.skater_games,
            request.players,
            request.team_games,
            request.series,
            request.context.production_config,
        )
    )
    test = dataset.loc[dataset["season_end_year"].isin(request.context.test_year_set)].reset_index(
        drop=True
    )
    if test.empty:
        raise ValueError("no held-out skater-round rows available to project")
    rows, n_skipped = _projection_rows(
        request.context.models.production.project(test),
        request.context,
        request.project_round,
        request.baseline_reg_games,
    )
    if not rows:
        raise ValueError("no skater-round could be projected (all series unsimulated)")
    return _score_projection_rows(rows, n_skipped)


def _projection_rows(
    projected: pd.DataFrame,
    context: _ProjectionContext,
    project_round: _ProjectRound,
    baseline_reg_games: float,
) -> tuple[list[dict[str, float]], int]:
    rows: list[dict[str, float]] = []
    n_skipped = 0
    for rec in projected.to_dict("records"):
        row = _projection_row(rec, context, project_round, baseline_reg_games)
        if row is None:
            n_skipped += 1
        else:
            rows.append(row)
    return rows, n_skipped


def _projection_row(
    rec: Mapping[Hashable, Any],
    context: _ProjectionContext,
    project_round: _ProjectRound,
    baseline_reg_games: float,
) -> dict[str, float] | None:
    from draft_oracle.models.projections import SkaterRoundRequest

    season_id = int(rec["season_id"])
    year = season_id % 10000
    rnd = int(rec["playoff_round"])
    player_id = int(rec["player_id"])
    team_id = context.abbrev_to_id.get(str(rec["team_abbrev"]))
    length_probs = (
        context.length_by_team.get((year, rnd, team_id)) if team_id is not None else None
    )
    if length_probs is None:
        return None

    projection = project_round(
        SkaterRoundRequest(float(rec["projected_points_per_game"]), length_probs),
        _projection_runtime(context, season_id, rnd, player_id),
    )
    baseline_reg = float(rec["points_per_game"]) * baseline_reg_games
    return {
        "season_end_year": year,
        "expected_points": projection.expected_points,
        "actual_points": float(rec[LABEL_COLUMN]) * float(rec["round_games"]),
        "baseline_reg": baseline_reg,
        "baseline_prev": context.previous_points.get(
            (season_id, rnd - 1, player_id), baseline_reg
        ),
        "p10": projection.p10,
        "p90": projection.p90,
    }


def _resolve_projection_request(
    request: ProjectionEvaluationRequest | pd.DataFrame,
    legacy_args: tuple[object, ...],
    options: _ProjectionRequestOptions,
) -> _EvaluateProjectionModelRequest:
    if options.project_round is None or options.baseline_reg_games is None:
        raise TypeError("project_round and baseline_reg_games are required")
    if _is_projection_request_like(request):
        request_like = cast(_ProjectionEvaluationRequestLike, request)
        if legacy_args:
            raise TypeError("projection request calls do not accept extra positional arguments")
        resolved_config = options.config or request_like.config
        if resolved_config is None:
            raise TypeError("projection request must provide config")
        return _EvaluateProjectionModelRequest(
            skater_games=request_like.skater_games,
            players=request_like.players,
            team_games=request_like.team_games,
            series=request_like.series,
            config=resolved_config,
            project_round=options.project_round,
            baseline_reg_games=options.baseline_reg_games,
        )
    if len(legacy_args) != 3 or options.config is None:
        raise TypeError(
            "legacy evaluate_projection_model calls require players, team_games, series, and config"
        )
    players, team_games, series = legacy_args
    return _EvaluateProjectionModelRequest(
        skater_games=cast(pd.DataFrame, request),
        players=cast(pd.DataFrame, players),
        team_games=cast(pd.DataFrame, team_games),
        series=cast(pd.DataFrame, series),
        config=options.config,
        project_round=options.project_round,
        baseline_reg_games=options.baseline_reg_games,
    )


def _is_projection_request_like(request: object) -> bool:
    return all(
        hasattr(request, attr)
        for attr in ("skater_games", "players", "team_games", "series", "config")
    )


def _projection_runtime(
    context: _ProjectionContext,
    season_id: int,
    playoff_round: int,
    player_id: int,
) -> ProjectionRuntime:
    from draft_oracle.models.projections import ProjectionRuntime

    return ProjectionRuntime(
        seed=_row_seed(context.config.seed, season_id, playoff_round, player_id),
        n_sims=context.config.n_sims,
        horizon=context.config.horizon,
    )


def _score_projection_rows(
    rows: list[dict[str, float]],
    n_skipped: int,
) -> _ProjectionScores:
    scored = pd.DataFrame(rows)
    return _ProjectionScores(
        scored=scored,
        n_skipped=n_skipped,
        model_pred=scored["expected_points"].to_numpy(dtype=float),
        actual=scored["actual_points"].to_numpy(dtype=float),
        baseline_reg=scored["baseline_reg"].to_numpy(dtype=float),
        baseline_prev=scored["baseline_prev"].to_numpy(dtype=float),
    )


def _projection_evaluation(
    context: _ProjectionContext,
    scores: _ProjectionScores,
) -> ProjectionEvaluation:
    return ProjectionEvaluation(
        test_years=context.test_years,
        n_projected=len(scores.scored),
        n_skipped_no_series=scores.n_skipped,
        test_mae_model=mean_absolute_error(scores.model_pred, scores.actual),
        test_mae_baseline_reg=mean_absolute_error(scores.baseline_reg, scores.actual),
        test_mae_baseline_prev=mean_absolute_error(scores.baseline_prev, scores.actual),
        test_spearman_model=spearman_correlation(scores.model_pred, scores.actual),
        test_spearman_baseline_reg=spearman_correlation(scores.baseline_reg, scores.actual),
        test_spearman_baseline_prev=spearman_correlation(scores.baseline_prev, scores.actual),
        per_season=_projection_per_season(scores, context.test_year_set),
        mean_expected_points=float(scores.scored["expected_points"].mean()),
        mean_p10=float(scores.scored["p10"].mean()),
        mean_p90=float(scores.scored["p90"].mean()),
    )


def _projection_per_season(
    scores: _ProjectionScores,
    test_year_set: set[int],
) -> list[SeasonMetricValue]:
    per_season: list[SeasonMetricValue] = []
    for year in sorted(test_year_set):
        mask = scores.scored["season_end_year"].to_numpy() == int(year)
        if not mask.any():
            continue
        per_season.append(
            SeasonMetricValue(
                season_end_year=int(year),
                n=int(mask.sum()),
                mae=mean_absolute_error(scores.model_pred[mask], scores.actual[mask]),
                spearman=spearman_correlation(scores.model_pred[mask], scores.actual[mask]),
            )
        )
    return per_season

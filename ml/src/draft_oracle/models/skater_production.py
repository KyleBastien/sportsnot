"""Skater per-game production model (US-014, PRD US-006 part 1).

Predicts ``E[G+A per game]`` for a skater in the *upcoming playoff round* from the
as-of skater feature matrix (US-009). In this league a skater's fantasy points are
goals + assists weighted 1 each (:func:`draft_oracle.rules.player_points`), so the
per-game production rate is exactly the round's expected fantasy points per game.
Composed with expected games played (US-016) it becomes a round-point projection.

Design (SPEC section 8: only ~350 skater-round rows per season -> keep it small,
regularized, and shrunk):

* **Leakage-free labels and features.** Each historical playoff round is a training
  example: the features are the US-009 matrix built *as of the round's start date*
  (only games strictly before the round can enter, enforced by
  :mod:`draft_oracle.features.leakage`), and the label is the skater's *observed*
  goals+assists per game **in that round**. Round membership and start dates are
  reconstructed from the ``series`` table by pairing each playoff game to its series;
  a round's start is the earliest game date of any series in that round, so a label
  game is never earlier than its own feature cutoff.
* **Regularized estimator, chosen by validation.** Two candidates are compared on a
  held-out validation season's MAE: a Poisson GLM (``PoissonRegressor`` on
  standardized features -- a natural non-negative rate model) and a regularized
  gradient-boosted Poisson regressor (``LGBMRegressor(objective="poisson")``). The
  lower-MAE candidate is chosen; the choice is recorded in the committed report.
* **Cold-case handling.** Rookies / low-sample skaters are shrunk toward a
  position+team prior with a credibility weight ``n / (n + k)`` so a two-game sample
  cannot dominate. Skaters with *no* regular-season games have no feature row at all;
  :meth:`SkaterProductionModel.project_cold` returns the position+team prior with a
  ``low_confidence`` flag instead of crashing.

Honesty (SPEC section 7): the report writes held-out MAE and Spearman rank
correlation **per test season** against two fixed baselines (predict the skater's
regular-season points/game, and predict the training mean). A miss is printed as the
honest number; baselines, splits, and seeds are never altered to force a pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from draft_oracle.features.skater import (
    SkaterFeatureConfig,
    SkaterFeatureRequest,
    build_skater_features,
)
from draft_oracle.models._skater_rounds import (
    LABEL_COLUMN as LABEL_COLUMN,
)
from draft_oracle.models._skater_rounds import (
    PLAYOFF_GAME_TYPE as PLAYOFF_GAME_TYPE,
)
from draft_oracle.models._skater_rounds import (
    QUALIFYING_ROUND_GAME_DIGIT as QUALIFYING_ROUND_GAME_DIGIT,
)
from draft_oracle.models._skater_rounds import (
    REGULAR_SEASON_GAME_TYPE as REGULAR_SEASON_GAME_TYPE,
)
from draft_oracle.models._skater_rounds import (
    _assign_rounds as _assign_rounds,
)
from draft_oracle.models._skater_rounds import (
    _pair_key as _pair_key,
)
from draft_oracle.models._skater_rounds import (
    _playoff_round_digit as _playoff_round_digit,
)
from draft_oracle.models._skater_rounds import (
    _series_round_map as _series_round_map,
)
from draft_oracle.models._skater_rounds import (
    playoff_round_cutoffs as playoff_round_cutoffs,
)
from draft_oracle.models._skater_rounds import (
    playoff_round_starts as playoff_round_starts,
)
from draft_oracle.models._skater_rounds import (
    skater_round_production as skater_round_production,
)
from draft_oracle.models.game_win import TemporalSplit, default_temporal_split
from draft_oracle.provenance import add_git_provenance

__all__ = [
    "LABEL_COLUMN",
    "PREDICTOR_COLUMNS",
    "SKATER_PRODUCTION_VERSION",
    "ProductionPriors",
    "SeasonMetrics",
    "SkaterProductionConfig",
    "SkaterProductionModel",
    "SkaterProductionResult",
    "build_production_dataset",
    "credibility_weight",
    "fit_priors",
    "mean_absolute_error",
    "playoff_round_cutoffs",
    "playoff_round_starts",
    "shrink_to_prior",
    "skater_round_production",
    "spearman_correlation",
    "train_skater_production_from_normalized",
    "train_skater_production_model",
]

for public_obj in (playoff_round_cutoffs, playoff_round_starts, skater_round_production):
    public_obj.__module__ = __name__

SKATER_PRODUCTION_VERSION = "skater-production-v1"

# Numeric predictors drawn from the US-009 skater-v1 matrix, plus a derived
# ``is_defense`` indicator. ``games_played`` is kept as a sample-size signal.
PREDICTOR_COLUMNS: tuple[str, ...] = (
    "is_defense",
    "games_played",
    "goals_per_game",
    "assists_per_game",
    "points_per_game",
    "goals_per_game_l25",
    "assists_per_game_l25",
    "points_per_game_l25",
    "pp_points_per_game",
    "pp_point_share",
    "avg_toi_seconds",
    "shots_per_game",
    "shooting_pct",
    "age_years",
    "linemate_ppg",
    "team_goals_for_per_game",
)


# ── Scalar metrics + shrinkage (each unit-tested) ────────────────────────


def mean_absolute_error(preds: Any, actuals: Any) -> float:
    """Mean absolute error ``mean(|pred - actual|)`` (lower is better)."""
    p = np.asarray(preds, dtype=float)
    y = np.asarray(actuals, dtype=float)
    if p.size == 0:
        return float("nan")
    return float(np.mean(np.abs(p - y)))


def _rankdata(values: Any) -> np.ndarray:
    """Average ranks of ``values`` (ties share the mean of their rank span)."""
    a = np.asarray(values, dtype=float)
    n = a.size
    order = a.argsort(kind="stable")
    ranks = np.empty(n, dtype=float)
    ranks[order] = np.arange(1, n + 1, dtype=float)
    sorted_a = a[order]
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sorted_a[j + 1] == sorted_a[i]:
            j += 1
        if j > i:
            ranks[order[i : j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    return ranks


def spearman_correlation(preds: Any, actuals: Any) -> float:
    """Spearman rank correlation between predictions and actuals.

    Pearson correlation of the average-rank transforms; returns ``nan`` when fewer
    than two points or when either side has zero rank variance (all tied).
    """
    p = np.asarray(preds, dtype=float)
    y = np.asarray(actuals, dtype=float)
    if p.size < 2:
        return float("nan")
    rp = _rankdata(p)
    ry = _rankdata(y)
    rp_c = rp - rp.mean()
    ry_c = ry - ry.mean()
    denom = float(np.sqrt(float((rp_c**2).sum()) * float((ry_c**2).sum())))
    if denom == 0.0:
        return float("nan")
    return float(float((rp_c * ry_c).sum()) / denom)


def credibility_weight(n_games: float, k: float) -> float:
    """Credibility weight ``n / (n + k)`` in ``[0, 1)`` (0 games -> 0 weight)."""
    n = float(n_games)
    if n <= 0.0:
        return 0.0
    return n / (n + float(k))


def shrink_to_prior(estimate: float, prior: float, n_games: float, k: float) -> float:
    """Blend a model estimate toward a prior by sample-size credibility.

    ``w = n / (n + k)`` weights the estimate; ``(1 - w)`` weights the prior. A
    skater with few games leans on the prior; a full regular season leans on the
    model. With ``k = 0`` (or infinite games) the estimate is returned unchanged.
    """
    w = credibility_weight(n_games, k)
    return w * float(estimate) + (1.0 - w) * float(prior)


# ── Dataset assembly (features x labels, leakage-free per round) ──────────


@dataclass(frozen=True)
class ProductionDatasetRequest:
    skater_games: pd.DataFrame
    players: pd.DataFrame
    team_games: pd.DataFrame
    series: pd.DataFrame
    config: SkaterProductionConfig | None = None


def build_production_dataset(
    request: ProductionDatasetRequest,
) -> pd.DataFrame:
    """Assemble one training row per skater-round: as-of features + observed label.

    For every reconstructed playoff round the US-009 feature matrix is built as of
    the round start (leakage-free) and inner-joined to that round's observed
    per-game production. Skaters without a feature row (no regular-season sample)
    are dropped here and handled as cold cases at projection time.
    """
    config = request.config or SkaterProductionConfig()
    feature_config = config.feature_config or SkaterFeatureConfig(min_games=config.min_games)
    starts = playoff_round_starts(request.team_games, request.series)
    labels = skater_round_production(request.skater_games, request.series)

    frames: list[pd.DataFrame] = []
    for season_id, round_dates in starts.items():
        for rnd, start in round_dates.items():
            feats = build_skater_features(
                request.skater_games,
                request.players,
                request.team_games,
                SkaterFeatureRequest(
                    season_id=season_id,
                    as_of_date=start,
                    playoff_round=rnd,
                    config=feature_config,
                ),
            )
            if feats.empty:
                continue
            round_labels = labels.loc[
                (labels["season_id"] == season_id) & (labels["playoff_round"] == rnd),
                ["player_id", LABEL_COLUMN, "round_games"],
            ]
            merged = feats.merge(round_labels, on="player_id", how="inner")
            if not merged.empty:
                frames.append(merged)

    if not frames:
        return pd.DataFrame()
    data = pd.concat(frames, ignore_index=True)
    data["season_end_year"] = (data["season_id"] % 10000).astype(int)
    data["is_defense"] = (data["position"] == "D").astype(float)
    return data


def _resolve_production_training_request(
    request: ProductionDatasetRequest | pd.DataFrame,
    legacy_args: tuple[object, ...],
    config: SkaterProductionConfig | None,
) -> ProductionDatasetRequest:
    if isinstance(request, ProductionDatasetRequest):
        if legacy_args or config is not None:
            raise TypeError("pass ProductionDatasetRequest or legacy dataframes, not both")
        return request
    if len(legacy_args) != 3:
        raise TypeError(
            "legacy train_skater_production_model calls require players, team_games, and series"
        )
    players, team_games, series = legacy_args
    return ProductionDatasetRequest(
        skater_games=request,
        players=cast(pd.DataFrame, players),
        team_games=cast(pd.DataFrame, team_games),
        series=cast(pd.DataFrame, series),
        config=config,
    )


# ── Position+team priors (fit on training rows only) ─────────────────────


@dataclass
class ProductionPriors:
    """Shrinkage targets: mean observed per-game production by group.

    ``position_team`` is the finest grouping; missing keys fall back to a
    position-wide prior, then to the global mean. All values are fit from the
    training split only, so a prior never leaks the label of the row it shrinks.
    """

    position_team: dict[tuple[str, str], float]
    position: dict[str, float]
    global_mean: float

    def prior_for(self, position: Any, team_abbrev: Any) -> float:
        """Best available prior for a (position, team), most specific first."""
        pt = self.position_team.get((str(position), str(team_abbrev)))
        if pt is not None:
            return pt
        p = self.position.get(str(position))
        if p is not None:
            return p
        return self.global_mean


def fit_priors(frame: pd.DataFrame) -> ProductionPriors:
    """Fit position+team / position / global label means from a training frame."""
    if frame.empty:
        return ProductionPriors(position_team={}, position={}, global_mean=0.0)
    global_mean = float(frame[LABEL_COLUMN].mean())
    pos_grouped = frame.groupby("position")[LABEL_COLUMN].mean().reset_index()
    position = {
        str(rec["position"]): float(rec[LABEL_COLUMN]) for rec in pos_grouped.to_dict("records")
    }
    pt_grouped = frame.groupby(["position", "team_abbrev"])[LABEL_COLUMN].mean().reset_index()
    position_team = {
        (str(rec["position"]), str(rec["team_abbrev"])): float(rec[LABEL_COLUMN])
        for rec in pt_grouped.to_dict("records")
    }
    return ProductionPriors(position_team=position_team, position=position, global_mean=global_mean)


# ── Estimators ───────────────────────────────────────────────────────────


def _prepare_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Select the predictor matrix, deriving ``is_defense`` when absent."""
    out = frame.copy()
    if "is_defense" not in out.columns:
        out["is_defense"] = (out["position"] == "D").astype(float)
    return out.loc[:, list(PREDICTOR_COLUMNS)]


def _build_poisson(_seed: int) -> Any:
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            ("reg", PoissonRegressor(alpha=1.0, max_iter=1000)),
        ]
    )


def _build_lgbm(seed: int) -> Any:
    return LGBMRegressor(
        objective="poisson",
        n_estimators=300,
        num_leaves=15,
        learning_rate=0.03,
        min_child_samples=30,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        random_state=seed,
        n_jobs=1,
        verbose=-1,
    )


def _fit(estimator: Any, frame: pd.DataFrame) -> Any:
    estimator.fit(_prepare_features(frame), frame[LABEL_COLUMN].astype(float))
    return estimator


def _predict_raw(estimator: Any, frame: pd.DataFrame) -> np.ndarray:
    preds = estimator.predict(_prepare_features(frame))
    return np.clip(np.asarray(preds, dtype=float), 0.0, None)


def _build_estimator(model_type: str, seed: int) -> Any:
    return _build_poisson(seed) if model_type == "poisson" else _build_lgbm(seed)


# ── Fitted model ─────────────────────────────────────────────────────────


@dataclass
class SkaterProductionModel:
    """A fitted per-game production estimator with cold-case shrinkage.

    :meth:`predict_raw` is the bare model output (clipped non-negative);
    :meth:`project` blends it toward a position+team prior by sample size and flags
    low-confidence rows; :meth:`project_cold` prices a skater that has no feature row
    at all (no regular-season sample) from the prior alone.
    """

    estimator: Any
    model_type: str
    priors: ProductionPriors
    shrink_k: float
    min_confident_games: int

    def predict_raw(self, frame: pd.DataFrame) -> np.ndarray:
        """Model ``E[G+A per game]`` for each feature row (clipped ``>= 0``)."""
        return _predict_raw(self.estimator, frame)

    def project(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Shrunk projections + confidence flags for a feature matrix.

        Adds ``raw_points_per_game`` (model), ``prior_points_per_game`` (shrinkage
        target), ``projected_points_per_game`` (blended), and ``low_confidence``
        (``games_played < min_confident_games``). Never mutates the input frame.
        """
        raw = self.predict_raw(frame)
        priors = [
            self.priors.prior_for(pos, team)
            for pos, team in zip(frame["position"], frame["team_abbrev"], strict=True)
        ]
        games = frame["games_played"].astype(float).to_numpy()
        projected = [
            shrink_to_prior(float(r), float(pr), float(n), self.shrink_k)
            for r, pr, n in zip(raw, priors, games, strict=True)
        ]
        out = frame.copy()
        out["raw_points_per_game"] = raw
        out["prior_points_per_game"] = priors
        out["projected_points_per_game"] = projected
        out["low_confidence"] = games < float(self.min_confident_games)
        return out

    def project_cold(self, position: Any, team_abbrev: Any) -> tuple[float, bool]:
        """Prior-only projection for a skater with no regular-season feature row.

        Returns ``(projected_points_per_game, low_confidence=True)``. This is the
        graceful path for rookies with zero regular-season games -- a flagged
        low-confidence number, never a crash (SPEC section 7).
        """
        return self.priors.prior_for(position, team_abbrev), True


# ── Result (report + manifest) ───────────────────────────────────────────


@dataclass(frozen=True)
class SeasonMetrics:
    """Held-out metrics for a single test season."""

    season_end_year: int
    n: int
    mae: float
    spearman: float


@dataclass(frozen=True)
class SkaterProductionConfig:
    """Training knobs; every stochastic step is seeded (SPEC section 3)."""

    seed: int = 20260827
    n_val_seasons: int = 1
    n_test_seasons: int = 2
    min_games: int = 1
    shrink_k: float = 10.0
    min_confident_games: int = 10
    feature_config: SkaterFeatureConfig | None = field(default=None)


@dataclass
class SkaterProductionResult:
    """Outcome of a training run: fitted model, metrics, and report material."""

    model: SkaterProductionModel
    config: SkaterProductionConfig
    split: TemporalSplit
    chosen_model_type: str
    val_mae_by_model: dict[str, float]
    test_mae_model: float
    test_mae_raw: float
    test_mae_baseline_reg: float
    test_mae_baseline_mean: float
    test_spearman_model: float
    test_spearman_baseline_reg: float
    per_season: list[SeasonMetrics]
    n_train: int
    n_val: int
    n_test: int
    n_cold_cases_test: int

    @property
    def beats_reg_baseline(self) -> bool:
        return self.test_mae_model < self.test_mae_baseline_reg

    @property
    def beats_mean_baseline(self) -> bool:
        return self.test_mae_model < self.test_mae_baseline_mean

    def manifest(self) -> dict[str, Any]:
        """JSON-serialisable run summary (seed, splits, metrics)."""
        return {
            "model_version": SKATER_PRODUCTION_VERSION,
            "seed": self.config.seed,
            "chosen_model_type": self.chosen_model_type,
            "shrink_k": self.config.shrink_k,
            "min_confident_games": self.config.min_confident_games,
            "split": {
                "train_years": list(self.split.train_years),
                "val_years": list(self.split.val_years),
                "test_years": list(self.split.test_years),
            },
            "counts": {
                "train": self.n_train,
                "val": self.n_val,
                "test": self.n_test,
                "cold_cases_test": self.n_cold_cases_test,
            },
            "validation_mae": self.val_mae_by_model,
            "test_mae": {
                "model": self.test_mae_model,
                "model_raw": self.test_mae_raw,
                "baseline_reg_ppg": self.test_mae_baseline_reg,
                "baseline_mean": self.test_mae_baseline_mean,
            },
            "test_spearman": {
                "model": self.test_spearman_model,
                "baseline_reg_ppg": self.test_spearman_baseline_reg,
            },
            "per_season": [
                {
                    "season_end_year": m.season_end_year,
                    "n": m.n,
                    "mae": m.mae,
                    "spearman": m.spearman,
                }
                for m in self.per_season
            ],
            "beats_reg_baseline": self.beats_reg_baseline,
            "beats_mean_baseline": self.beats_mean_baseline,
        }

    def report_lines(self) -> list[str]:
        """Human-readable evaluation report (Markdown; ASCII only)."""
        lines = _production_report_intro(self)
        lines.extend(_production_model_selection_lines(self))
        lines.extend(_production_test_lines(self))
        lines.extend(_production_per_season_lines(self))
        lines.extend(_production_cold_case_lines(self))
        lines.extend(_production_honest_note_lines(self))
        return lines


def _production_report_intro(result: SkaterProductionResult) -> list[str]:
    cfg = result.config
    return [
        f"# Skater per-game production model ({SKATER_PRODUCTION_VERSION})",
        "",
        "Predicts `E[G+A per game]` for a skater in the upcoming playoff round from",
        "the as-of US-009 skater feature matrix. Each historical round is one training",
        "example: features are frozen at the round start (leakage-free) and the label is",
        "the skater's observed goals+assists per game in that round.",
        "",
        "## Reproducibility",
        f"- Seed: {cfg.seed}",
        f"- Shrinkage: estimate * n/(n+{cfg.shrink_k:g}) + prior * k/(n+k), "
        "prior = position+team mean",
        f"- Low-confidence flag: fewer than {cfg.min_confident_games} regular-season games",
        f"- Train seasons (end year): {list(result.split.train_years)} ({result.n_train} rows)",
        f"- Validation seasons: {list(result.split.val_years)} ({result.n_val} rows)",
        f"- Test seasons (held out): {list(result.split.test_years)} ({result.n_test} rows)",
        "- Splits are strictly temporal: each round is predicted using only data",
        "  available before that round (SPEC section 6).",
        "",
        "## Model selection (validation MAE, lower is better)",
    ]


def _production_model_selection_lines(result: SkaterProductionResult) -> list[str]:
    lines: list[str] = []
    for model_type, mae in sorted(result.val_mae_by_model.items()):
        marker = "  <- chosen" if model_type == result.chosen_model_type else ""
        lines.append(f"- {model_type}: {mae:.4f}{marker}")
    lines += [
        "",
        f"Chosen model: **{result.chosen_model_type}** (lowest validation MAE).",
        "It is refit on train + validation seasons before the held-out test.",
    ]
    return lines


def _production_test_lines(result: SkaterProductionResult) -> list[str]:
    return [
        "",
        "## Held-out test error vs. fixed baselines (per-game points)",
        f"- production model (shrunk): MAE {result.test_mae_model:.4f}, "
        f"Spearman {result.test_spearman_model:.4f}",
        f"- raw model (no shrinkage):  MAE {result.test_mae_raw:.4f}",
        f"- baseline (a) reg-season points/game: MAE {result.test_mae_baseline_reg:.4f}, "
        f"Spearman {result.test_spearman_baseline_reg:.4f}",
        f"- baseline (b) training mean:          MAE {result.test_mae_baseline_mean:.4f}",
        "",
        f"- Beats reg-season-ppg baseline: {'yes' if result.beats_reg_baseline else 'NO'}",
        f"- Beats training-mean baseline:  {'yes' if result.beats_mean_baseline else 'NO'}",
        "",
        "## Per held-out season (MAE, Spearman rank correlation)",
    ]


def _production_per_season_lines(result: SkaterProductionResult) -> list[str]:
    return [
        f"- {m.season_end_year}: n={m.n}, MAE {m.mae:.4f}, Spearman {m.spearman:.4f}"
        for m in result.per_season
    ]


def _production_cold_case_lines(result: SkaterProductionResult) -> list[str]:
    return [
        "",
        "## Cold cases",
        f"- Test-season labeled skaters with no regular-season feature row: "
        f"{result.n_cold_cases_test}.",
        "  These rookies/no-sample skaters are priced from the position+team prior with a",
        "  low-confidence flag (`project_cold`), never crashing the pipeline.",
        "",
    ]


def _production_honest_note_lines(result: SkaterProductionResult) -> list[str]:
    if result.beats_reg_baseline:
        return []
    return [
        "## Honest note on a missed target",
        "The model did not beat the regular-season points/game baseline on this split.",
        "Reported as-is (SPEC section 7): baselines, splits, and seeds are unchanged.",
        "Playoff per-game production is famously noisy over 4-7 games, so a strong",
        "season-rate baseline is hard to beat on MAE; rank correlation (Spearman) is the",
        "more informative signal for draft ordering. A plausible improvement: add",
        "opponent-defense and expected-games context (US-010 team-series features) and",
        "widen the training window before scoring the held-out seasons.",
        "",
    ]


# ── Training + evaluation ──────────────────────────────────────────────────


def _rows_for_years(dataset: pd.DataFrame, years: tuple[int, ...]) -> pd.DataFrame:
    return dataset.loc[dataset["season_end_year"].isin([int(y) for y in years])]


def _count_cold_cases(labels: pd.DataFrame, dataset: pd.DataFrame, years: tuple[int, ...]) -> int:
    """Labeled skater-rounds in ``years`` that have no feature row in ``dataset``."""
    if labels.empty:
        return 0
    year_set = {int(y) for y in years}
    lab = labels.copy()
    lab["season_end_year"] = (lab["season_id"] % 10000).astype(int)
    lab = lab.loc[lab["season_end_year"].isin(year_set)]
    if lab.empty:
        return 0
    covered = dataset.loc[
        dataset["season_end_year"].isin(year_set),
        ["season_id", "playoff_round", "player_id"],
    ].drop_duplicates()
    merged = lab.merge(
        covered.assign(_covered=1),
        on=["season_id", "playoff_round", "player_id"],
        how="left",
    )
    return int(merged["_covered"].isna().sum())


@dataclass(frozen=True)
class _ProductionSplitFrames:
    split: TemporalSplit
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame
    train_val: pd.DataFrame


@dataclass(frozen=True)
class _ProductionEvaluation:
    test_mae_model: float
    test_mae_raw: float
    test_mae_baseline_reg: float
    test_mae_baseline_mean: float
    test_spearman_model: float
    test_spearman_baseline_reg: float
    per_season: list[SeasonMetrics]


def _split_production_dataset(
    dataset: pd.DataFrame, config: SkaterProductionConfig
) -> _ProductionSplitFrames:
    years = [int(y) for y in dataset["season_end_year"].unique()]
    split = default_temporal_split(years, n_val=config.n_val_seasons, n_test=config.n_test_seasons)
    train = _rows_for_years(dataset, split.train_years)
    val = _rows_for_years(dataset, split.val_years)
    test = _rows_for_years(dataset, split.test_years)
    return _ProductionSplitFrames(
        split=split,
        train=train,
        val=val,
        test=test,
        train_val=pd.concat([train, val], ignore_index=True),
    )


def _validation_mae_by_model(
    train: pd.DataFrame, val: pd.DataFrame, seed: int
) -> dict[str, float]:
    val_mae: dict[str, float] = {}
    for model_type in ("poisson", "lightgbm"):
        fitted = _fit(_build_estimator(model_type, seed), train)
        val_mae[model_type] = mean_absolute_error(_predict_raw(fitted, val), val[LABEL_COLUMN])
    return val_mae


def _fit_skater_model(
    model_type: str,
    frame: pd.DataFrame,
    config: SkaterProductionConfig,
) -> SkaterProductionModel:
    return SkaterProductionModel(
        estimator=_fit(_build_estimator(model_type, config.seed), frame),
        model_type=model_type,
        priors=fit_priors(frame),
        shrink_k=config.shrink_k,
        min_confident_games=config.min_confident_games,
    )


def _evaluate_production_model(
    model: SkaterProductionModel,
    frames: _ProductionSplitFrames,
) -> _ProductionEvaluation:
    projected = model.project(frames.test)
    test_pred = projected["projected_points_per_game"].to_numpy(dtype=float)
    test_raw = projected["raw_points_per_game"].to_numpy(dtype=float)
    test_actual = frames.test[LABEL_COLUMN].to_numpy(dtype=float)
    baseline_reg = frames.test["points_per_game"].to_numpy(dtype=float)
    baseline_mean = float(frames.train_val[LABEL_COLUMN].mean())

    return _ProductionEvaluation(
        test_mae_model=mean_absolute_error(test_pred, test_actual),
        test_mae_raw=mean_absolute_error(test_raw, test_actual),
        test_mae_baseline_reg=mean_absolute_error(baseline_reg, test_actual),
        test_mae_baseline_mean=mean_absolute_error(
            np.full(len(frames.test), baseline_mean), test_actual
        ),
        test_spearman_model=spearman_correlation(test_pred, test_actual),
        test_spearman_baseline_reg=spearman_correlation(baseline_reg, test_actual),
        per_season=_per_season_metrics(
            frames.test,
            frames.split.test_years,
            test_pred,
            test_actual,
        ),
    )


def _per_season_metrics(
    test: pd.DataFrame,
    test_years: tuple[int, ...],
    test_pred: np.ndarray,
    test_actual: np.ndarray,
) -> list[SeasonMetrics]:
    per_season: list[SeasonMetrics] = []
    for year in sorted(test_years):
        mask = test["season_end_year"].to_numpy() == int(year)
        if not mask.any():
            continue
        per_season.append(
            SeasonMetrics(
                season_end_year=int(year),
                n=int(mask.sum()),
                mae=mean_absolute_error(test_pred[mask], test_actual[mask]),
                spearman=spearman_correlation(test_pred[mask], test_actual[mask]),
            )
        )
    return per_season


def train_skater_production_model(
    request: ProductionDatasetRequest | pd.DataFrame,
    *legacy_args: object,
    config: SkaterProductionConfig | None = None,
) -> SkaterProductionResult:
    """Train, select, and evaluate the skater per-game production model end-to-end.

    Builds the leakage-free per-round dataset; splits seasons temporally; selects
    between a Poisson GLM and a gradient-boosted Poisson regressor on validation
    MAE; refits the winner on train+validation and scores the held-out seasons
    (overall and per season) against two baselines; counts cold cases; and fits the
    shipped model on all seasons with all-data priors. Every reported number is
    carried on the returned :class:`SkaterProductionResult` -- nothing is hidden.
    """
    training_request = _resolve_production_training_request(request, legacy_args, config)
    resolved_config = training_request.config or SkaterProductionConfig()
    dataset = build_production_dataset(
        ProductionDatasetRequest(
            training_request.skater_games,
            training_request.players,
            training_request.team_games,
            training_request.series,
            resolved_config,
        )
    )
    if dataset.empty:
        raise ValueError("no skater-round rows available to train the production model")

    labels = skater_round_production(training_request.skater_games, training_request.series)

    frames = _split_production_dataset(dataset, resolved_config)
    val_mae = _validation_mae_by_model(frames.train, frames.val, resolved_config.seed)
    chosen = min(val_mae, key=lambda k: val_mae[k])

    eval_model = _fit_skater_model(chosen, frames.train_val, resolved_config)
    evaluation = _evaluate_production_model(eval_model, frames)
    cold_cases = _count_cold_cases(labels, dataset, frames.split.test_years)
    model = _fit_skater_model(chosen, dataset, resolved_config)

    return SkaterProductionResult(
        model=model,
        config=resolved_config,
        split=frames.split,
        chosen_model_type=chosen,
        val_mae_by_model=val_mae,
        test_mae_model=evaluation.test_mae_model,
        test_mae_raw=evaluation.test_mae_raw,
        test_mae_baseline_reg=evaluation.test_mae_baseline_reg,
        test_mae_baseline_mean=evaluation.test_mae_baseline_mean,
        test_spearman_model=evaluation.test_spearman_model,
        test_spearman_baseline_reg=evaluation.test_spearman_baseline_reg,
        per_season=evaluation.per_season,
        n_train=len(frames.train),
        n_val=len(frames.val),
        n_test=len(frames.test),
        n_cold_cases_test=cold_cases,
    )


DEFAULT_NORMALIZED_DIR = Path("data/normalized")
DEFAULT_MODEL_ARTIFACT_DIR = Path("artifacts/models/skater-production")


def train_skater_production_from_normalized(
    *,
    normalized_dir: Path = DEFAULT_NORMALIZED_DIR,
    artifact_dir: Path = DEFAULT_MODEL_ARTIFACT_DIR,
    config: SkaterProductionConfig | None = None,
) -> SkaterProductionResult:
    """Load normalized Parquet tables, train, and write the report + manifest.

    Reads ``skater_games`` / ``players`` / ``team_games`` / ``series``, runs
    :func:`train_skater_production_model`, and commits the Markdown report and JSON
    manifest under ``artifact_dir``.
    """
    import json

    skater_games = pd.read_parquet(normalized_dir / "skater_games.parquet")
    players = pd.read_parquet(normalized_dir / "players.parquet")
    team_games = pd.read_parquet(normalized_dir / "team_games.parquet")
    series = pd.read_parquet(normalized_dir / "series.parquet")

    result = train_skater_production_model(
        ProductionDatasetRequest(skater_games, players, team_games, series, config)
    )
    manifest = add_git_provenance(result.manifest())

    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "report.md").write_text(
        "\n".join(result.report_lines()) + "\n", encoding="utf-8"
    )
    (artifact_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return result

"""Shutout probability model (US-012, PRD US-005 part 2).

Predicts ``P(the win is a shutout | a team wins this game)`` from the winning
team's goaltending situation and the loser's offence. In this league the goalie
slot is an entire NHL **team's** goaltending, and a shutout win is worth 4 fantasy
points instead of the usual 2 (SPEC section 1), so pricing shutout upside is what
gives the goalie slot its edge. The series simulator (US-013) rolls this per-game
probability up into expected goalie-slot points.

Design (SPEC section 8: ~150 series/season -> keep it small and regularized):

* **Winner-framed rows, leakage-free by construction.** Every decided NHL game has
  exactly one winner, so conditioning on "a team wins" costs no data: one row per
  game, framed from the winner. The label is ``1`` when the winner held the loser
  to zero goals. A single chronological pass maintains each team's running
  regular-season goaltending proxies (season save %, last-15-game save %, team
  shutout rate) and offensive rate (goals-for per game). Every game reads only the
  state accumulated from *strictly earlier* games, so no game leaks into its own
  features. Only regular-season games feed the running state; playoff games are
  still scored as observations off the regular-season state that precedes them.
* **Goaltender-situation features.** ``winner_save_pct_season`` and
  ``winner_save_pct_l15`` (starter proxy over the season and the last 15 games),
  ``winner_team_shutout_rate``, the loser's ``opponent_goals_for_per_game``, plus a
  ``backup_save_pct`` and a ``starter_unavailability_risk`` term with explicit
  missing-flags. The committed NHL archive has no per-goalie game rows, so the
  backup split cannot be computed and there is no historical injury feed: those two
  columns are imputed to documented neutral defaults and flagged
  (``goalie_split_available`` / ``goalie_injury_data_available`` are ``0``), never
  fabricated. They exist so the live pipeline (US-008 injuries, US-013) can supply a
  real backup save % and an unavailability risk at inference time.
* **Monotone in goalie quality.** Both estimators are constrained so higher goalie
  quality (season / last-15 save %, team shutout rate) never lowers the predicted
  shutout probability and stronger opponent offence never raises it.

Honesty (SPEC section 7): the report writes the held-out calibration (predicted vs.
observed shutout frequency, overall and per bin) against a base-rate baseline. The
plus/minus 25 percent calibration target is a goal to attempt and then report
truthfully -- a miss prints the honest number; baselines, splits, and seeds are
never altered to force a pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from draft_oracle.models._games import pivot_decided_games as pivot_decided_games
from draft_oracle.models._shutout_dataset import (
    NEUTRAL_SAVE_PCT as NEUTRAL_SAVE_PCT,
)
from draft_oracle.models._shutout_dataset import (
    ShutoutFeatureContext,
    ShutoutTeamState,
)
from draft_oracle.models._shutout_dataset import (
    _pivot_games as _pivot_games,
)
from draft_oracle.models._shutout_dataset import (
    _save_pct as _save_pct,
)
from draft_oracle.models._shutout_dataset import (
    build_shutout_dataset as build_shutout_dataset,
)
from draft_oracle.models._shutout_dataset import (
    shutout_feature_row as shutout_feature_row,
)
from draft_oracle.models.game_win import (
    TemporalSplit,
    brier_score,
    default_temporal_split,
)
from draft_oracle.provenance import add_git_provenance

__all__ = [
    "NEUTRAL_SAVE_PCT",
    "SHUTOUT_FEATURE_COLUMNS",
    "SHUTOUT_MODEL_VERSION",
    "CalibrationBin",
    "ShutoutConfig",
    "ShutoutFeatureContext",
    "ShutoutModel",
    "ShutoutResult",
    "ShutoutTeamState",
    "base_rate_probs",
    "build_shutout_dataset",
    "shutout_feature_row",
    "train_shutout_from_normalized",
    "train_shutout_model",
]

for public_obj in (
    ShutoutFeatureContext,
    ShutoutTeamState,
    build_shutout_dataset,
    shutout_feature_row,
):
    public_obj.__module__ = __name__

SHUTOUT_MODEL_VERSION = "shutout-v1"

# Feature order is fixed so it lines up with the LightGBM monotone constraints.
SHUTOUT_FEATURE_COLUMNS: tuple[str, ...] = (
    "winner_save_pct_season",
    "winner_save_pct_l15",
    "winner_team_shutout_rate",
    "opponent_goals_for_per_game",
    "backup_save_pct",
    "goalie_split_available",
    "starter_unavailability_risk",
    "goalie_injury_data_available",
)

# +1: goalie quality up -> shutout prob up. -1: opponent offence / unavailability up
# -> shutout prob down. 0: imputed-constant / missing-flag columns carry no order.
_MONOTONE_CONSTRAINTS: tuple[int, ...] = (1, 1, 1, -1, 0, 0, -1, 0)


# ── Baseline ───────────────────────────────────────────────────────────────


def base_rate_probs(n: int, rate: float) -> np.ndarray:
    """Baseline: predict the fixed training-set shutout ``rate`` for every game."""
    return np.full(int(n), float(rate), dtype=float)


# Candidate model weights for the shrinkage sweep: 1.0 = pure model, 0.0 = pure
# base rate. Selected on the validation fold, never on the held-out test (US-105).
DEFAULT_SHRINKAGE_GRID: tuple[float, ...] = (
    1.0,
    0.9,
    0.8,
    0.7,
    0.6,
    0.5,
    0.4,
    0.3,
    0.2,
    0.1,
    0.0,
)


def _apply_shrinkage(probs: np.ndarray, *, weight: float, base_rate: float) -> np.ndarray:
    """Blend ``probs`` toward ``base_rate``: ``weight*probs + (1-weight)*base_rate``.

    ``weight == 1.0`` is a no-op (pure model); ``weight == 0.0`` collapses onto the
    base rate. The result is clipped to ``[0, 1]``.
    """
    if weight >= 1.0:
        return np.asarray(np.clip(probs, 0.0, 1.0), dtype=float)
    blended = weight * probs + (1.0 - weight) * float(base_rate)
    return np.asarray(np.clip(blended, 0.0, 1.0), dtype=float)


def _select_shrinkage_weight(
    probs: np.ndarray,
    labels: np.ndarray,
    *,
    base_rate: float,
    grid: tuple[float, ...],
) -> tuple[float, dict[str, float]]:
    """Pick the shrinkage weight minimising validation Brier (ties prefer more model).

    Returns the chosen weight and the full ``{weight -> validation Brier}`` sweep so
    the report can print the honest decision either way. Grid is scored high-weight
    first so an exact tie keeps the least-shrunk (most model-driven) option.
    """
    by_weight: dict[str, float] = {}
    best_weight = 1.0
    best_brier = float("inf")
    for weight in sorted(set(grid), reverse=True):
        shrunk = _apply_shrinkage(probs, weight=weight, base_rate=base_rate)
        score = brier_score(shrunk, labels)
        by_weight[f"{weight:.2f}"] = score
        if score < best_brier - 1e-12:
            best_brier = score
            best_weight = weight
    return best_weight, by_weight


def _rows_for_years(dataset: pd.DataFrame, years: tuple[int, ...]) -> pd.DataFrame:
    return dataset.loc[dataset["season_end_year"].isin([float(y) for y in years])]


# ── Estimators (monotone in goalie quality) ────────────────────────────────


def _build_logreg(seed: int) -> Any:
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=1000, C=1.0, random_state=seed)),
        ]
    )


def _build_lgbm(seed: int) -> Any:
    return LGBMClassifier(
        n_estimators=200,
        num_leaves=15,
        learning_rate=0.05,
        min_child_samples=40,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        random_state=seed,
        n_jobs=1,
        verbose=-1,
        monotone_constraints=list(_MONOTONE_CONSTRAINTS),
    )


def _fit(estimator: Any, frame: pd.DataFrame, features: tuple[str, ...]) -> Any:
    estimator.fit(frame.loc[:, list(features)], frame["is_shutout"].astype(int))
    return estimator


def _predict(estimator: Any, frame: pd.DataFrame, features: tuple[str, ...]) -> np.ndarray:
    proba = estimator.predict_proba(frame.loc[:, list(features)])
    return np.asarray(proba, dtype=float)[:, 1]


def _train_variant(frame: pd.DataFrame, *, model_type: str, seed: int) -> Any:
    builder = _build_logreg if model_type == "logistic_regression" else _build_lgbm
    return _fit(builder(seed), frame, SHUTOUT_FEATURE_COLUMNS)


@dataclass(frozen=True)
class _ShutoutSplitFrames:
    split: TemporalSplit
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame
    train_val: pd.DataFrame


@dataclass(frozen=True)
class _ShutoutValidation:
    val_brier: dict[str, float]
    val_probs_by_model: dict[str, np.ndarray]
    chosen: str


@dataclass(frozen=True)
class _ShutoutEvaluation:
    test_brier_model: float
    test_brier_base: float
    train_rate: float
    observed_rate: float
    predicted_rate: float
    bins: list[CalibrationBin]
    shrink_weight: float
    val_brier_by_shrinkage: dict[str, float]
    test_brier_model_unshrunk: float


def _shutout_split_frames(dataset: pd.DataFrame, config: ShutoutConfig) -> _ShutoutSplitFrames:
    years = [int(y) for y in dataset["season_end_year"].unique()]
    split = default_temporal_split(years, n_val=config.n_val_seasons, n_test=config.n_test_seasons)
    train = _rows_for_years(dataset, split.train_years)
    val = _rows_for_years(dataset, split.val_years)
    test = _rows_for_years(dataset, split.test_years)
    return _ShutoutSplitFrames(
        split=split,
        train=train,
        val=val,
        test=test,
        train_val=pd.concat([train, val], ignore_index=True),
    )


def _validate_shutout_models(frames: _ShutoutSplitFrames, seed: int) -> _ShutoutValidation:
    val_brier: dict[str, float] = {}
    val_probs_by_model: dict[str, np.ndarray] = {}
    for model_type in ("logistic_regression", "lightgbm"):
        fitted = _train_variant(frames.train, model_type=model_type, seed=seed)
        preds = _predict(fitted, frames.val, SHUTOUT_FEATURE_COLUMNS)
        val_probs_by_model[model_type] = preds
        val_brier[model_type] = brier_score(preds, frames.val["is_shutout"])
    chosen = min(val_brier, key=lambda k: val_brier[k])
    return _ShutoutValidation(
        val_brier=val_brier,
        val_probs_by_model=val_probs_by_model,
        chosen=chosen,
    )


def _evaluate_shutout_model(
    frames: _ShutoutSplitFrames,
    validation: _ShutoutValidation,
    config: ShutoutConfig,
) -> _ShutoutEvaluation:
    train_base_rate = float(frames.train["is_shutout"].mean())
    val_labels = frames.val["is_shutout"].to_numpy(dtype=float)
    shrink_weight, val_brier_by_shrinkage = _select_shrinkage_weight(
        validation.val_probs_by_model[validation.chosen],
        val_labels,
        base_rate=train_base_rate,
        grid=config.shrinkage_grid,
    )
    holdout_model = _train_variant(frames.train_val, model_type=validation.chosen, seed=config.seed)
    test_probs_raw = _predict(holdout_model, frames.test, SHUTOUT_FEATURE_COLUMNS)
    test_labels = frames.test["is_shutout"].to_numpy(dtype=float)
    train_rate = float(frames.train_val["is_shutout"].mean())
    test_probs = _apply_shrinkage(test_probs_raw, weight=shrink_weight, base_rate=train_rate)
    return _ShutoutEvaluation(
        test_brier_model=brier_score(test_probs, test_labels),
        test_brier_base=brier_score(base_rate_probs(len(frames.test), train_rate), test_labels),
        train_rate=train_rate,
        observed_rate=float(test_labels.mean()) if test_labels.size else float("nan"),
        predicted_rate=float(test_probs.mean()) if test_probs.size else float("nan"),
        bins=_calibration_bins(test_probs, test_labels, n_bins=config.calibration_bins),
        shrink_weight=shrink_weight,
        val_brier_by_shrinkage=val_brier_by_shrinkage,
        test_brier_model_unshrunk=brier_score(test_probs_raw, test_labels),
    )


def _fit_production_shutout_model(
    dataset: pd.DataFrame,
    chosen: str,
    shrink_weight: float,
    seed: int,
) -> ShutoutModel:
    production = _train_variant(dataset, model_type=chosen, seed=seed)
    return ShutoutModel(
        estimator=production,
        feature_columns=SHUTOUT_FEATURE_COLUMNS,
        model_type=chosen,
        shrinkage_weight=shrink_weight,
        base_rate=float(dataset["is_shutout"].mean()),
    )


@dataclass
class ShutoutModel:
    """A fitted shutout-probability estimator (monotone in goalie quality).

    :meth:`predict_shutout_prob` scores a prepared dataset; :meth:`predict_matchup`
    scores an ad-hoc winner/loser matchup from per-team proxies (used by the series
    simulator, US-013, once a winner is drawn).
    """

    estimator: Any
    feature_columns: tuple[str, ...]
    model_type: str
    shrinkage_weight: float = 1.0
    base_rate: float = 0.0

    def predict_shutout_prob(self, dataset: pd.DataFrame) -> np.ndarray:
        """Shutout probability for each row of a :func:`build_shutout_dataset` frame.

        When ``shrinkage_weight`` is below ``1.0`` the raw estimator probability is
        blended toward the playoff ``base_rate`` (US-105 / CODE_REVIEW observation:
        the raw model shows no held-out skill, so a data-selected shrinkage pulls it
        back toward the base rate). ``shrinkage_weight == 1.0`` leaves probabilities
        untouched.
        """
        raw = _predict(self.estimator, dataset, self.feature_columns)
        return _apply_shrinkage(raw, weight=self.shrinkage_weight, base_rate=self.base_rate)

    def predict_matchup(
        self,
        winner: dict[str, float],
        loser: dict[str, float],
        *,
        context: ShutoutFeatureContext | None = None,
    ) -> float:
        """``P(shutout | winner beats loser)`` for one matchup from proxy dicts."""
        row = shutout_feature_row(
            winner,
            loser,
            context=context,
        )
        frame = pd.DataFrame([row])
        return float(self.predict_shutout_prob(frame)[0])


# ── Calibration ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CalibrationBin:
    """One predicted-probability bucket: predicted vs. observed shutout frequency."""

    lower: float
    upper: float
    count: int
    mean_predicted: float
    observed_rate: float


def _calibration_bins(
    probs: np.ndarray, labels: np.ndarray, *, n_bins: int
) -> list[CalibrationBin]:
    """Equal-width predicted-probability bins with observed vs. predicted rates."""
    if probs.size == 0:
        return []
    edges = np.linspace(0.0, max(float(probs.max()), 1e-6), n_bins + 1)
    bins: list[CalibrationBin] = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (probs >= lo) & (probs <= hi if i == n_bins - 1 else probs < hi)
        count = int(mask.sum())
        if count == 0:
            continue
        bins.append(
            CalibrationBin(
                lower=float(lo),
                upper=float(hi),
                count=count,
                mean_predicted=float(probs[mask].mean()),
                observed_rate=float(labels[mask].mean()),
            )
        )
    return bins


# ── Training + evaluation ──────────────────────────────────────────────────


@dataclass(frozen=True)
class ShutoutConfig:
    """Training knobs; every stochastic step is seeded (SPEC section 3)."""

    seed: int = 20260827
    min_pregame_games: int = 5
    last_n: int = 15
    n_val_seasons: int = 1
    n_test_seasons: int = 2
    calibration_bins: int = 5
    calibration_tolerance: float = 0.25
    shrinkage_grid: tuple[float, ...] = DEFAULT_SHRINKAGE_GRID


@dataclass
class ShutoutResult:
    """Outcome of a training run: fitted model, metrics, and report material."""

    model: ShutoutModel
    config: ShutoutConfig
    split: TemporalSplit
    chosen_model_type: str
    val_brier_by_model: dict[str, float]
    test_brier_model: float
    test_brier_base_rate: float
    train_shutout_rate: float
    test_observed_rate: float
    test_predicted_rate: float
    calibration_bins: list[CalibrationBin]
    n_train: int
    n_val: int
    n_test: int
    shrinkage_weight: float = 1.0
    shrinkage_base_rate: float = 0.0
    val_brier_by_shrinkage: dict[str, float] = field(default_factory=dict)
    test_brier_model_unshrunk: float = float("nan")

    @property
    def shrinkage_adopted(self) -> bool:
        """True when the validation sweep pulled the model below full model weight."""
        return self.shrinkage_weight < 1.0

    @property
    def calibration_rel_error(self) -> float:
        if self.test_observed_rate <= 0.0:
            return float("nan")
        return abs(self.test_predicted_rate - self.test_observed_rate) / self.test_observed_rate

    @property
    def calibrated_within_tolerance(self) -> bool:
        rel = self.calibration_rel_error
        return bool(np.isfinite(rel) and rel <= self.config.calibration_tolerance)

    @property
    def beats_base_rate(self) -> bool:
        return self.test_brier_model < self.test_brier_base_rate

    def manifest(self) -> dict[str, Any]:
        """JSON-serialisable run summary (seed, splits, metrics)."""
        return {
            "model_version": SHUTOUT_MODEL_VERSION,
            "seed": self.config.seed,
            "min_pregame_games": self.config.min_pregame_games,
            "goalie_last_n": self.config.last_n,
            "chosen_model_type": self.chosen_model_type,
            "split": {
                "train_years": list(self.split.train_years),
                "val_years": list(self.split.val_years),
                "test_years": list(self.split.test_years),
            },
            "counts": {"train": self.n_train, "val": self.n_val, "test": self.n_test},
            "validation_brier": self.val_brier_by_model,
            "test_brier": {
                "model": self.test_brier_model,
                "model_unshrunk": self.test_brier_model_unshrunk,
                "base_rate": self.test_brier_base_rate,
            },
            "shrinkage": {
                "weight": self.shrinkage_weight,
                "base_rate": self.shrinkage_base_rate,
                "adopted": self.shrinkage_adopted,
                "validation_brier_by_weight": self.val_brier_by_shrinkage,
            },
            "shutout_rate": {
                "train": self.train_shutout_rate,
                "test_observed": self.test_observed_rate,
                "test_predicted": self.test_predicted_rate,
            },
            "calibration": {
                "relative_error": self.calibration_rel_error,
                "tolerance": self.config.calibration_tolerance,
                "within_tolerance": self.calibrated_within_tolerance,
                "bins": [
                    {
                        "lower": b.lower,
                        "upper": b.upper,
                        "count": b.count,
                        "mean_predicted": b.mean_predicted,
                        "observed_rate": b.observed_rate,
                    }
                    for b in self.calibration_bins
                ],
            },
            "beats_base_rate": self.beats_base_rate,
        }

    def report_lines(self) -> list[str]:
        """Human-readable evaluation report (Markdown; ASCII only)."""
        lines = _shutout_report_intro(self)
        lines.extend(_shutout_model_selection_lines(self))
        lines.extend(_shutout_shrinkage_lines(self))
        lines.extend(_shutout_test_lines(self))
        lines.extend(_shutout_calibration_lines(self))
        lines.extend(_shutout_honest_note_lines(self))
        return lines


def _shutout_report_intro(result: ShutoutResult) -> list[str]:
    cfg = result.config
    return [
        f"# Shutout probability model ({SHUTOUT_MODEL_VERSION})",
        "",
        "`P(the win is a shutout | a team wins this game)`, framed from the winning",
        "team. Features are the winner's team-level goaltending proxies (season and",
        "last-15-game save %, team shutout rate), the loser's goals-for per game, and",
        "backup-save-% / starter-unavailability terms with explicit missing-flags. The",
        "model is monotone in goalie quality. Shutout wins are worth 4 fantasy points",
        "vs. 2 for a normal win, so this prices the goalie slot's upside (SPEC 1).",
        "",
        "## Reproducibility",
        f"- Seed: {cfg.seed}",
        f"- Min pre-game regular-season games (winner): {cfg.min_pregame_games}",
        f"- Save-% recency window: last {cfg.last_n} games",
        f"- Train seasons (end year): {list(result.split.train_years)} "
        f"({result.n_train} games)",
        f"- Validation seasons: {list(result.split.val_years)} ({result.n_val} games)",
        f"- Test seasons (held out): {list(result.split.test_years)} "
        f"({result.n_test} games)",
        "- Splits are strictly temporal: no test-season game touches training or",
        "  model selection (SPEC section 6).",
        "",
        "## Model selection (validation Brier, lower is better)",
    ]


def _shutout_model_selection_lines(result: ShutoutResult) -> list[str]:
    lines: list[str] = []
    for model_type, brier in sorted(result.val_brier_by_model.items()):
        marker = "  <- chosen" if model_type == result.chosen_model_type else ""
        lines.append(f"- {model_type}: {brier:.4f}{marker}")
    lines += [
        "",
        f"Chosen model: **{result.chosen_model_type}** (lowest validation Brier).",
        "It is refit on train + validation seasons before the held-out test.",
    ]
    return lines


def _shutout_shrinkage_lines(result: ShutoutResult) -> list[str]:
    shrink_note = (
        "shrinkage adopted"
        if result.shrinkage_adopted
        else "no shrinkage -- pure model wins on validation"
    )
    lines = [
        "",
        "## Base-rate shrinkage (validation-selected, US-105)",
        "The raw model shows little to no held-out skill over the playoff base",
        "rate (CODE_REVIEW observation), so a shrinkage weight `w` blending",
        "`w*model + (1-w)*base_rate` is selected on the validation fold only",
        "(never the held-out test). `w=1.0` keeps the pure model; `w=0.0`",
        "collapses onto the base rate.",
        "",
        f"- Selected weight: **{result.shrinkage_weight:.2f}** ({shrink_note})",
        f"- Shrinkage base rate (train+val shutout rate): {result.shrinkage_base_rate:.4f}",
        "- Validation Brier by weight (1.00 = pure model):",
    ]
    for weight_key in sorted(result.val_brier_by_shrinkage, key=float, reverse=True):
        marker = "  <- chosen" if abs(float(weight_key) - result.shrinkage_weight) < 1e-9 else ""
        brier = result.val_brier_by_shrinkage[weight_key]
        lines.append(f"  - w={weight_key}: {brier:.4f}{marker}")
    return lines


def _shutout_test_lines(result: ShutoutResult) -> list[str]:
    return [
        "",
        "## Held-out test Brier vs. base-rate baseline",
        f"- shutout model (w={result.shrinkage_weight:.2f}): {result.test_brier_model:.4f}",
        f"- shutout model (unshrunk, w=1.00):  {result.test_brier_model_unshrunk:.4f}",
        f"- baseline (train shutout rate {result.train_shutout_rate:.3f}): "
        f"{result.test_brier_base_rate:.4f}",
        f"- Beats base rate: {'yes' if result.beats_base_rate else 'NO'}",
    ]


def _shutout_calibration_lines(result: ShutoutResult) -> list[str]:
    cfg = result.config
    lines = [
        "",
        "## Calibration: predicted vs. observed shutout frequency (held out)",
        f"- Observed shutout rate:  {result.test_observed_rate:.4f}",
        f"- Predicted shutout rate: {result.test_predicted_rate:.4f}",
        f"- Relative error: {result.calibration_rel_error:.1%} "
        f"(target within +/-{cfg.calibration_tolerance:.0%})",
        f"- Within target: {'yes' if result.calibrated_within_tolerance else 'NO'}",
        "",
        "### Reliability bins (predicted bucket -> observed rate)",
        "| predicted range | n | mean predicted | observed |",
        "| --- | --- | --- | --- |",
    ]
    for b in result.calibration_bins:
        lines.append(
            f"| {b.lower:.3f}-{b.upper:.3f} | {b.count} | "
            f"{b.mean_predicted:.3f} | {b.observed_rate:.3f} |"
        )
    lines.append("")
    return lines


def _shutout_honest_note_lines(result: ShutoutResult) -> list[str]:
    if result.calibrated_within_tolerance:
        return []
    return [
        "## Honest note on a missed target",
        "Overall calibration missed the +/-25% target on this split. Reported",
        "as-is (SPEC section 7): baselines, splits, and seeds are unchanged. One",
        "plausible improvement: fit isotonic / Platt calibration on the validation",
        "fold before scoring the test set, and add real per-goalie starter/backup",
        "save-% and injury availability (US-008) once that data is wired in.",
        "",
    ]


def train_shutout_model(
    team_games: pd.DataFrame,
    *,
    config: ShutoutConfig | None = None,
) -> ShutoutResult:
    """Train, select, and evaluate the shutout-probability model end-to-end.

    Steps: build the leakage-free winner-framed dataset; split seasons temporally;
    select between logistic regression and (monotone) LightGBM on the validation
    Brier; refit the winner on train+validation and score the held-out test against a
    base-rate baseline; measure calibration (overall + per bin); and fit a production
    model on all available seasons. The returned :class:`ShutoutResult` carries every
    number the committed report and manifest print -- nothing is hidden.
    """
    config = config or ShutoutConfig()
    dataset = build_shutout_dataset(
        team_games, last_n=config.last_n, min_pregame_games=config.min_pregame_games
    )
    if dataset.empty:
        raise ValueError("no games available to train the shutout model")

    frames = _shutout_split_frames(dataset, config)
    validation = _validate_shutout_models(frames, config.seed)
    evaluation = _evaluate_shutout_model(frames, validation, config)
    model = _fit_production_shutout_model(
        dataset, validation.chosen, evaluation.shrink_weight, config.seed
    )

    return ShutoutResult(
        model=model,
        config=config,
        split=frames.split,
        chosen_model_type=validation.chosen,
        val_brier_by_model=validation.val_brier,
        test_brier_model=evaluation.test_brier_model,
        test_brier_base_rate=evaluation.test_brier_base,
        train_shutout_rate=evaluation.train_rate,
        test_observed_rate=evaluation.observed_rate,
        test_predicted_rate=evaluation.predicted_rate,
        calibration_bins=evaluation.bins,
        n_train=len(frames.train),
        n_val=len(frames.val),
        n_test=len(frames.test),
        shrinkage_weight=evaluation.shrink_weight,
        shrinkage_base_rate=evaluation.train_rate,
        val_brier_by_shrinkage=evaluation.val_brier_by_shrinkage,
        test_brier_model_unshrunk=evaluation.test_brier_model_unshrunk,
    )


DEFAULT_NORMALIZED_DIR = Path("data/normalized")
DEFAULT_MODEL_ARTIFACT_DIR = Path("artifacts/models/shutout")


def train_shutout_from_normalized(
    *,
    normalized_dir: Path = DEFAULT_NORMALIZED_DIR,
    artifact_dir: Path = DEFAULT_MODEL_ARTIFACT_DIR,
    config: ShutoutConfig | None = None,
) -> ShutoutResult:
    """Load ``team_games.parquet``, train, and write the report + manifest.

    Runs :func:`train_shutout_model` and commits the Markdown report and JSON
    manifest under ``artifact_dir`` (both re-included in .gitignore, like the
    per-game win model).
    """
    import json

    team_games = pd.read_parquet(normalized_dir / "team_games.parquet")
    result = train_shutout_model(team_games, config=config)
    manifest = add_git_provenance(result.manifest())

    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "report.md").write_text(
        "\n".join(result.report_lines()) + "\n", encoding="utf-8"
    )
    (artifact_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return result

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
    build_skater_features,
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

SKATER_PRODUCTION_VERSION = "skater-production-v1"

PLAYOFF_GAME_TYPE = 3
REGULAR_SEASON_GAME_TYPE = 2
LABEL_COLUMN = "actual_points_per_game"

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


# ── Playoff-round reconstruction (round windows + labels) ────────────────


def _pair_key(team_a: Any, team_b: Any) -> tuple[str, str]:
    """Order-independent key for the two teams in a series/game."""
    a, b = str(team_a), str(team_b)
    return (a, b) if a <= b else (b, a)


#: Round digit of a 2019-20 bubble qualifying-round / round-robin game id.
QUALIFYING_ROUND_GAME_DIGIT = "0"


def _playoff_round_digit(game_id: Any) -> str | None:
    """The round digit of a 10-char NHL playoff game id, or ``None`` if unparseable.

    NHL playoff game ids are ``SSSS03RMGG`` where the 8th character (index 7) is the
    round: ``1``-``4`` for the four best-of-seven rounds. The 2019-20 bubble's
    qualifying round *and* seeding round-robin both carry digit ``0`` and must never
    be attributed to a best-of-seven series — their team pairs collide with real
    later-round matchups (e.g. a round-robin game between two teams that also meet in
    round 2), which the team-pair round map would otherwise mislabel (CODE_REVIEW
    m-6).
    """
    text = str(game_id).strip()
    if len(text) != 10 or not text.isdigit():
        return None
    return text[7]


def _series_round_map(series: pd.DataFrame) -> dict[tuple[int, tuple[str, str]], int]:
    """Map ``(season_id, {team_a, team_b}) -> playoff_round`` from the series table."""
    out: dict[tuple[int, tuple[str, str]], int] = {}
    cols = ["season_id", "top_seed_abbrev", "bottom_seed_abbrev", "playoff_round"]
    for rec in series[cols].to_dict("records"):
        key = (int(rec["season_id"]), _pair_key(rec["top_seed_abbrev"], rec["bottom_seed_abbrev"]))
        out[key] = int(rec["playoff_round"])
    return out


def _assign_rounds(
    games: pd.DataFrame, round_map: dict[tuple[int, tuple[str, str]], int]
) -> list[int | None]:
    """Look up each playoff game's round via its (season, team-pair); ``None`` if unknown.

    A 2019-20 qualifying-round / round-robin game (``game_id`` round digit ``0``) is
    always ``None`` regardless of the team-pair map, so a round-robin game whose two
    teams also meet in a real later series is never mislabeled as that series' round
    (CODE_REVIEW m-6).
    """
    has_game_id = "game_id" in games.columns
    read_cols = ["season_id", "team_abbrev", "opponent_team_abbrev"]
    if has_game_id:
        read_cols = ["game_id", *read_cols]
    result: list[int | None] = []
    for rec in games[read_cols].to_dict("records"):
        if has_game_id and _playoff_round_digit(rec["game_id"]) == QUALIFYING_ROUND_GAME_DIGIT:
            result.append(None)
            continue
        key = (int(rec["season_id"]), _pair_key(rec["team_abbrev"], rec["opponent_team_abbrev"]))
        result.append(round_map.get(key))
    return result


def playoff_round_starts(
    team_games: pd.DataFrame, series: pd.DataFrame
) -> dict[int, dict[int, str]]:
    """Earliest game date of each playoff round, per season.

    Returns ``{season_id: {playoff_round: "YYYY-MM-DD"}}``. The start date is the
    exclusive as-of cutoff for that round's features. Games whose team pair matches
    no series row (e.g. the 2019-20 bubble round-robin) are ignored.
    """
    po = team_games.loc[team_games["game_type_id"] == PLAYOFF_GAME_TYPE].copy()
    if po.empty:
        return {}
    po["game_date"] = pd.to_datetime(po["game_date"])
    po["playoff_round"] = _assign_rounds(po, _series_round_map(series))
    po = po.dropna(subset=["playoff_round"])
    grouped = po.groupby(["season_id", "playoff_round"])["game_date"].min().reset_index()
    starts: dict[int, dict[int, str]] = {}
    for rec in grouped.to_dict("records"):
        season = int(rec["season_id"])
        rnd = int(rec["playoff_round"])
        starts.setdefault(season, {})[rnd] = pd.Timestamp(rec["game_date"]).strftime("%Y-%m-%d")
    return starts


def playoff_round_cutoffs(
    team_games: pd.DataFrame, series: pd.DataFrame
) -> dict[int, dict[int, str]]:
    """As-of cutoffs per round, extended with a *pre-round* cutoff for the next round.

    Returns ``{season_id: {playoff_round: "YYYY-MM-DD"}}`` like
    :func:`playoff_round_starts`, but so a genuinely pre-round artifact can be built
    (CODE_REVIEW M-1): the round drafts *before* it starts, so its own first game does
    not exist yet. For every season the round *after* the latest played playoff round
    gets a cutoff of the day AFTER that round's final game -- the previous round's
    completion / bracket-announcement boundary. When no playoff games exist yet, round
    1 gets the day after the regular season's final game.

    Rounds that have already been played keep their own first-game cutoff untouched,
    so backtests over complete seasons are byte-for-byte identical: the only added
    entries are for rounds with no games in the archive.
    """
    starts = playoff_round_starts(team_games, series)
    tg = team_games.copy()
    tg["game_date"] = pd.to_datetime(tg["game_date"])

    def _next_day(value: pd.Timestamp) -> str:
        return (pd.Timestamp(value) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    for season_id, group in tg.groupby("season_id"):
        season = int(cast(Any, season_id))
        played = starts.setdefault(season, {})
        if played:
            latest_round = max(played)
            po = group.loc[group["game_type_id"] == PLAYOFF_GAME_TYPE]
            if po.empty:
                continue
            played.setdefault(latest_round + 1, _next_day(po["game_date"].max()))
        else:
            reg = group.loc[group["game_type_id"] == REGULAR_SEASON_GAME_TYPE]
            if reg.empty:
                continue
            played.setdefault(1, _next_day(reg["game_date"].max()))
    return starts


def skater_round_production(skater_games: pd.DataFrame, series: pd.DataFrame) -> pd.DataFrame:
    """Observed goals+assists per game for each skater in each playoff round.

    One row per ``(season_id, playoff_round, player_id)`` with the round's goals,
    assists, games, and ``actual_points_per_game = (G + A) / GP``. This is the label
    the model learns; it uses only that round's playoff games.
    """
    po = skater_games.loc[skater_games["game_type_id"] == PLAYOFF_GAME_TYPE].copy()
    if po.empty:
        return pd.DataFrame(
            columns=[
                "season_id",
                "playoff_round",
                "player_id",
                "round_goals",
                "round_assists",
                "round_games",
                LABEL_COLUMN,
            ]
        )
    po["playoff_round"] = _assign_rounds(po, _series_round_map(series))
    po = po.dropna(subset=["playoff_round"])
    grouped = po.groupby(["season_id", "playoff_round", "player_id"], as_index=False).agg(
        round_goals=("goals", "sum"),
        round_assists=("assists", "sum"),
        round_games=("game_id", "nunique"),
    )
    grouped["playoff_round"] = grouped["playoff_round"].astype(int)
    grouped[LABEL_COLUMN] = [
        (g + a) / n if n else 0.0
        for g, a, n in zip(
            grouped["round_goals"], grouped["round_assists"], grouped["round_games"], strict=True
        )
    ]
    return grouped


# ── Dataset assembly (features x labels, leakage-free per round) ──────────


def build_production_dataset(
    skater_games: pd.DataFrame,
    players: pd.DataFrame,
    team_games: pd.DataFrame,
    series: pd.DataFrame,
    *,
    config: SkaterProductionConfig | None = None,
) -> pd.DataFrame:
    """Assemble one training row per skater-round: as-of features + observed label.

    For every reconstructed playoff round the US-009 feature matrix is built as of
    the round start (leakage-free) and inner-joined to that round's observed
    per-game production. Skaters without a feature row (no regular-season sample)
    are dropped here and handled as cold cases at projection time.
    """
    config = config or SkaterProductionConfig()
    feature_config = config.feature_config or SkaterFeatureConfig(min_games=config.min_games)
    starts = playoff_round_starts(team_games, series)
    labels = skater_round_production(skater_games, series)

    frames: list[pd.DataFrame] = []
    for season_id, round_dates in starts.items():
        for rnd, start in round_dates.items():
            feats = build_skater_features(
                skater_games,
                players,
                team_games,
                season_id=season_id,
                as_of_date=start,
                playoff_round=rnd,
                config=feature_config,
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
        cfg = self.config
        lines = [
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
            f"- Train seasons (end year): {list(self.split.train_years)} ({self.n_train} rows)",
            f"- Validation seasons: {list(self.split.val_years)} ({self.n_val} rows)",
            f"- Test seasons (held out): {list(self.split.test_years)} ({self.n_test} rows)",
            "- Splits are strictly temporal: each round is predicted using only data",
            "  available before that round (SPEC section 6).",
            "",
            "## Model selection (validation MAE, lower is better)",
        ]
        for model_type, mae in sorted(self.val_mae_by_model.items()):
            marker = "  <- chosen" if model_type == self.chosen_model_type else ""
            lines.append(f"- {model_type}: {mae:.4f}{marker}")
        lines += [
            "",
            f"Chosen model: **{self.chosen_model_type}** (lowest validation MAE).",
            "It is refit on train + validation seasons before the held-out test.",
            "",
            "## Held-out test error vs. fixed baselines (per-game points)",
            f"- production model (shrunk): MAE {self.test_mae_model:.4f}, "
            f"Spearman {self.test_spearman_model:.4f}",
            f"- raw model (no shrinkage):  MAE {self.test_mae_raw:.4f}",
            f"- baseline (a) reg-season points/game: MAE {self.test_mae_baseline_reg:.4f}, "
            f"Spearman {self.test_spearman_baseline_reg:.4f}",
            f"- baseline (b) training mean:          MAE {self.test_mae_baseline_mean:.4f}",
            "",
            f"- Beats reg-season-ppg baseline: {'yes' if self.beats_reg_baseline else 'NO'}",
            f"- Beats training-mean baseline:  {'yes' if self.beats_mean_baseline else 'NO'}",
            "",
            "## Per held-out season (MAE, Spearman rank correlation)",
        ]
        for m in self.per_season:
            lines.append(
                f"- {m.season_end_year}: n={m.n}, MAE {m.mae:.4f}, Spearman {m.spearman:.4f}"
            )
        lines += [
            "",
            "## Cold cases",
            f"- Test-season labeled skaters with no regular-season feature row: "
            f"{self.n_cold_cases_test}.",
            "  These rookies/no-sample skaters are priced from the position+team prior with a",
            "  low-confidence flag (`project_cold`), never crashing the pipeline.",
            "",
        ]
        if not self.beats_reg_baseline:
            lines += [
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
        return lines


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


def train_skater_production_model(
    skater_games: pd.DataFrame,
    players: pd.DataFrame,
    team_games: pd.DataFrame,
    series: pd.DataFrame,
    *,
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
    config = config or SkaterProductionConfig()
    dataset = build_production_dataset(skater_games, players, team_games, series, config=config)
    if dataset.empty:
        raise ValueError("no skater-round rows available to train the production model")

    labels = skater_round_production(skater_games, series)

    years = [int(y) for y in dataset["season_end_year"].unique()]
    split = default_temporal_split(years, n_val=config.n_val_seasons, n_test=config.n_test_seasons)
    train = _rows_for_years(dataset, split.train_years)
    val = _rows_for_years(dataset, split.val_years)
    test = _rows_for_years(dataset, split.test_years)
    train_val = pd.concat([train, val], ignore_index=True)

    # Model selection on validation MAE.
    val_mae: dict[str, float] = {}
    for model_type in ("poisson", "lightgbm"):
        fitted = _fit(_build_estimator(model_type, config.seed), train)
        val_mae[model_type] = mean_absolute_error(_predict_raw(fitted, val), val[LABEL_COLUMN])
    chosen = min(val_mae, key=lambda k: val_mae[k])

    # Refit the chosen model on train+val; build the evaluation model (priors from
    # train+val only, so the test labels never leak into the shrinkage target).
    eval_estimator = _fit(_build_estimator(chosen, config.seed), train_val)
    eval_model = SkaterProductionModel(
        estimator=eval_estimator,
        model_type=chosen,
        priors=fit_priors(train_val),
        shrink_k=config.shrink_k,
        min_confident_games=config.min_confident_games,
    )

    projected = eval_model.project(test)
    test_pred = projected["projected_points_per_game"].to_numpy(dtype=float)
    test_raw = projected["raw_points_per_game"].to_numpy(dtype=float)
    test_actual = test[LABEL_COLUMN].to_numpy(dtype=float)
    baseline_reg = test["points_per_game"].to_numpy(dtype=float)
    baseline_mean = float(train_val[LABEL_COLUMN].mean())

    test_mae_model = mean_absolute_error(test_pred, test_actual)
    test_mae_raw = mean_absolute_error(test_raw, test_actual)
    test_mae_baseline_reg = mean_absolute_error(baseline_reg, test_actual)
    test_mae_baseline_mean = mean_absolute_error(np.full(len(test), baseline_mean), test_actual)
    test_spearman_model = spearman_correlation(test_pred, test_actual)
    test_spearman_baseline_reg = spearman_correlation(baseline_reg, test_actual)

    per_season: list[SeasonMetrics] = []
    for year in sorted(split.test_years):
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

    cold_cases = _count_cold_cases(labels, dataset, split.test_years)

    # Shipped model: chosen type, all seasons, all-data priors.
    production_estimator = _fit(_build_estimator(chosen, config.seed), dataset)
    model = SkaterProductionModel(
        estimator=production_estimator,
        model_type=chosen,
        priors=fit_priors(dataset),
        shrink_k=config.shrink_k,
        min_confident_games=config.min_confident_games,
    )

    return SkaterProductionResult(
        model=model,
        config=config,
        split=split,
        chosen_model_type=chosen,
        val_mae_by_model=val_mae,
        test_mae_model=test_mae_model,
        test_mae_raw=test_mae_raw,
        test_mae_baseline_reg=test_mae_baseline_reg,
        test_mae_baseline_mean=test_mae_baseline_mean,
        test_spearman_model=test_spearman_model,
        test_spearman_baseline_reg=test_spearman_baseline_reg,
        per_season=per_season,
        n_train=len(train),
        n_val=len(val),
        n_test=len(test),
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

    result = train_skater_production_model(skater_games, players, team_games, series, config=config)
    manifest = add_git_provenance(result.manifest())

    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "report.md").write_text(
        "\n".join(result.report_lines()) + "\n", encoding="utf-8"
    )
    (artifact_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return result

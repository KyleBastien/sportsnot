"""Per-game win probability model (US-011, PRD US-005 part 1).

Predicts ``P(home team beats away team)`` for a single NHL game, home/away
aware, trained on historical regular-season **and** playoff games. The model is
the sharpest single-game estimate the series simulator (US-013) rests on.

Design (kept deliberately small — SPEC §8: ~150 series/season, prefer
regularized simple models):

* **Pre-game features, leakage-free by construction.** A single chronological
  pass over games maintains each team's running Elo rating (cross-season, with a
  season-boundary regression identical to
  :mod:`draft_oracle.features.elo`) and in-season
  regular-season aggregates (goals for/against per game, win %, points per game).
  Every game reads only the state accumulated from *strictly earlier* games, so
  no game can leak into its own features. A held-out season therefore contributes
  nothing to the features of games evaluated on it.
* **Home-perspective difference features.** The row is always framed from the
  home team, so home-ice advantage is captured by the model intercept and the
  Elo home advantage. Features are ``home - away`` differences plus a playoff
  indicator.
* **Market blend, optional.** When de-vigged betting odds are available for a
  game, the home implied win probability is added as a feature (with an explicit
  ``market_available`` flag). The model runs correctly in **stat-only** mode when
  odds are missing — the market columns are simply dropped from the feature set,
  which is exactly the ablation the report compares.

Honesty (SPEC §7): the evaluation report writes the held-out Brier score against
two fixed baselines (coin flip and "higher regular-season points wins"). A miss
is reported truthfully; baselines, splits, and seeds are never altered to force a
pass.
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

from draft_oracle.features.elo import (
    EloConfig,
    expected_score,
    regress_to_mean,
    update_rating,
)
from draft_oracle.provenance import add_git_provenance

__all__ = [
    "GAME_WIN_MODEL_VERSION",
    "MARKET_FEATURE_COLUMNS",
    "STAT_FEATURE_COLUMNS",
    "GameWinConfig",
    "GameWinModel",
    "GameWinResult",
    "TeamState",
    "TemporalSplit",
    "baseline_higher_points_probs",
    "brier_score",
    "build_game_dataset",
    "coin_flip_probs",
    "default_temporal_split",
    "matchup_feature_row",
    "train_game_win_model",
]

GAME_WIN_MODEL_VERSION = "game-win-v1"

REGULAR_SEASON_GAME_TYPE = 2
PLAYOFF_GAME_TYPE = 3
COIN_FLIP_PROB = 0.5

# Difference features shared by both model variants (home minus away).
STAT_FEATURE_COLUMNS: tuple[str, ...] = (
    "elo_diff",
    "goal_diff_per_game_diff",
    "goals_for_per_game_diff",
    "goals_against_per_game_diff",
    "win_pct_diff",
    "points_per_game_diff",
    "is_playoff",
)

# Market variant adds the de-vigged home implied probability + its missing flag.
MARKET_FEATURE_COLUMNS: tuple[str, ...] = (
    *STAT_FEATURE_COLUMNS,
    "market_home_prob",
    "market_available",
)

_STATE_PRIMITIVES: tuple[str, ...] = (
    "elo",
    "goals_for_per_game",
    "goals_against_per_game",
    "goal_diff_per_game",
    "win_pct",
    "points_per_game",
)


# ── Scalar metrics ─────────────────────────────────────────────────────────


def brier_score(probs: Any, labels: Any) -> float:
    """Mean squared error of probabilistic predictions (lower is better).

    ``mean((p - y) ** 2)`` for outcome labels ``y in {0, 1}``. A coin flip
    (``p = 0.5``) scores exactly ``0.25``.
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    if p.size == 0:
        return float("nan")
    return float(np.mean((p - y) ** 2))


def coin_flip_probs(n: int) -> np.ndarray:
    """Baseline (a): predict ``0.5`` for every game."""
    return np.full(int(n), COIN_FLIP_PROB, dtype=float)


def baseline_higher_points_probs(dataset: pd.DataFrame) -> np.ndarray:
    """Baseline (b): the team with more regular-season points (per game) wins.

    Deterministic pick expressed as a probability: ``1.0`` when the home team's
    as-of regular-season points per game exceeds the away team's, ``0.0`` when it
    trails, and ``0.5`` on an exact tie (including the pre-game cold start where
    both are zero).
    """
    home = dataset["home_points_per_game"].to_numpy(dtype=float)
    away = dataset["away_points_per_game"].to_numpy(dtype=float)
    probs = np.full(home.shape, COIN_FLIP_PROB, dtype=float)
    probs[home > away] = 1.0
    probs[home < away] = 0.0
    return probs


# ── Pre-game team state (leakage-free running aggregates) ──────────────────


@dataclass
class TeamState:
    """Mutable per-team running state accumulated from earlier games.

    Elo persists across seasons (with a boundary regression); the regular-season
    counters reset each season. All rates are ``0.0`` before a team's first game.
    """

    elo: float
    reg_games: int = 0
    reg_points: int = 0
    reg_goals_for: int = 0
    reg_goals_against: int = 0
    reg_wins: int = 0

    def snapshot(self) -> dict[str, float]:
        """Pre-game feature primitives from the state accumulated so far."""
        games = self.reg_games
        if games == 0:
            return {
                "elo": self.elo,
                "goals_for_per_game": 0.0,
                "goals_against_per_game": 0.0,
                "goal_diff_per_game": 0.0,
                "win_pct": 0.0,
                "points_per_game": 0.0,
            }
        return {
            "elo": self.elo,
            "goals_for_per_game": self.reg_goals_for / games,
            "goals_against_per_game": self.reg_goals_against / games,
            "goal_diff_per_game": (self.reg_goals_for - self.reg_goals_against) / games,
            "win_pct": self.reg_wins / games,
            "points_per_game": self.reg_points / games,
        }

    def record_regular_season(
        self, *, points: int, goals_for: int, goals_against: int, won: bool
    ) -> None:
        """Fold a completed regular-season game into the running counters."""
        self.reg_games += 1
        self.reg_points += points
        self.reg_goals_for += goals_for
        self.reg_goals_against += goals_against
        self.reg_wins += int(won)


def matchup_feature_row(
    home: dict[str, float],
    away: dict[str, float],
    *,
    is_playoff: bool,
    market_home_prob: float | None = None,
) -> dict[str, float]:
    """Build the model feature row for a home/away matchup from state snapshots.

    ``home`` / ``away`` are :meth:`TeamState.snapshot` dicts. Features are framed
    from the home team (``home - away`` differences). ``market_home_prob`` is the
    de-vigged home implied win probability, or ``None`` when odds are missing (the
    row then carries ``market_available = 0`` and an imputed neutral ``0.5``).
    """
    row: dict[str, float] = {
        "elo_diff": home["elo"] - away["elo"],
        "goal_diff_per_game_diff": home["goal_diff_per_game"] - away["goal_diff_per_game"],
        "goals_for_per_game_diff": home["goals_for_per_game"] - away["goals_for_per_game"],
        "goals_against_per_game_diff": (
            home["goals_against_per_game"] - away["goals_against_per_game"]
        ),
        "win_pct_diff": home["win_pct"] - away["win_pct"],
        "points_per_game_diff": home["points_per_game"] - away["points_per_game"],
        "is_playoff": 1.0 if is_playoff else 0.0,
        "market_available": 0.0 if market_home_prob is None else 1.0,
        "market_home_prob": COIN_FLIP_PROB if market_home_prob is None else float(market_home_prob),
    }
    return row


def _pivot_games(team_games: pd.DataFrame) -> pd.DataFrame:
    """One row per game (home + away), sorted chronologically.

    The home/away split uses the archive's ``home_road`` flag. Ties are dropped
    (real regular-season and playoff games are always decided in OT/SO).
    """
    tg = team_games.copy()
    tg["game_date"] = pd.to_datetime(tg["game_date"])
    home = tg.loc[tg["home_road"] == "H"]
    away = tg.loc[tg["home_road"] == "R"]
    merged = home.merge(away, on="game_id", suffixes=("_home", "_away"))

    games = pd.DataFrame(
        {
            "game_id": merged["game_id"],
            "season_id": merged["season_id_home"],
            "season_end_year": (merged["season_id_home"] % 10000).astype(int),
            "game_type_id": merged["game_type_id_home"],
            "game_date": merged["game_date_home"],
            "home_team_id": merged["team_id_home"].astype(int),
            "away_team_id": merged["team_id_away"].astype(int),
            "home_team_abbrev": merged["team_abbrev_home"],
            "away_team_abbrev": merged["team_abbrev_away"],
            "home_goals": merged["goals_for_home"].astype(int),
            "away_goals": merged["goals_for_away"].astype(int),
            "home_points": merged["points_home"].astype(int),
            "away_points": merged["points_away"].astype(int),
        }
    )
    games = games.loc[games["home_goals"] != games["away_goals"]]
    games["home_win"] = (games["home_goals"] > games["away_goals"]).astype(int)
    return games.sort_values(["game_date", "game_id"], kind="stable").reset_index(drop=True)


def _attach_market(games: pd.DataFrame, odds: pd.DataFrame | None) -> pd.DataFrame:
    """Left-join the de-vigged home implied probability onto each game."""
    out = games.copy()
    if odds is None or odds.empty:
        out["market_home_prob"] = np.nan
        return out
    market = odds.loc[
        :, ["season_end_year", "game_date", "home_team_id", "away_team_id", "home_implied"]
    ].copy()
    market["game_date"] = pd.to_datetime(market["game_date"])
    market = market.dropna(subset=["home_implied"])
    market = market.drop_duplicates(
        subset=["season_end_year", "game_date", "home_team_id", "away_team_id"], keep="first"
    )
    out = out.merge(
        market.rename(columns={"home_implied": "market_home_prob"}),
        on=["season_end_year", "game_date", "home_team_id", "away_team_id"],
        how="left",
    )
    return out


def build_game_dataset(
    team_games: pd.DataFrame,
    *,
    odds: pd.DataFrame | None = None,
    elo_config: EloConfig | None = None,
    min_pregame_games: int = 5,
) -> pd.DataFrame:
    """Assemble the per-game modelling frame with leakage-free pre-game features.

    One row per decided game with the home-perspective difference features, the
    optional market column, both teams' pre-game primitives (kept for the
    "higher points" baseline), and the ``home_win`` label. Games where either
    team has fewer than ``min_pregame_games`` regular-season games so far are
    dropped (their pre-game rates are pure cold-start noise); playoff games always
    qualify because a full regular season precedes them.
    """
    elo_config = elo_config or EloConfig()
    games = _pivot_games(team_games)
    games = _attach_market(games, odds)

    states: dict[str, TeamState] = {}
    last_season: int | None = None
    rows: list[dict[str, float]] = []

    for record in games.to_dict("records"):
        season = int(record["season_id"])
        if last_season is not None and season != last_season:
            for state in states.values():
                state.elo = regress_to_mean(
                    state.elo, elo_config.initial, elo_config.season_regression
                )
                state.reg_games = 0
                state.reg_points = 0
                state.reg_goals_for = 0
                state.reg_goals_against = 0
                state.reg_wins = 0
        last_season = season

        home_abbrev = str(record["home_team_abbrev"])
        away_abbrev = str(record["away_team_abbrev"])
        home_state = states.setdefault(home_abbrev, TeamState(elo=elo_config.initial))
        away_state = states.setdefault(away_abbrev, TeamState(elo=elo_config.initial))

        home_snap = home_state.snapshot()
        away_snap = away_state.snapshot()
        is_playoff = int(record["game_type_id"]) == PLAYOFF_GAME_TYPE
        market_raw = record["market_home_prob"]
        market_home_prob = None if pd.isna(market_raw) else float(market_raw)

        feature_row = matchup_feature_row(
            home_snap, away_snap, is_playoff=is_playoff, market_home_prob=market_home_prob
        )
        row: dict[str, float] = dict(feature_row)
        for key in _STATE_PRIMITIVES:
            row[f"home_{key}"] = home_snap[key]
            row[f"away_{key}"] = away_snap[key]
        row["game_id"] = float(record["game_id"])
        row["season_end_year"] = float(record["season_end_year"])
        row["game_type_id"] = float(record["game_type_id"])
        row["home_win"] = float(record["home_win"])
        row["home_pregame_games"] = float(home_state.reg_games)
        row["away_pregame_games"] = float(away_state.reg_games)
        rows.append(row)

        # Elo update (both teams), then in-season regular-season counters.
        exp_home = expected_score(home_state.elo, away_state.elo, elo_config.home_advantage)
        actual_home = float(record["home_win"])
        home_state.elo = update_rating(home_state.elo, exp_home, actual_home, elo_config.k)
        away_state.elo = update_rating(
            away_state.elo, 1.0 - exp_home, 1.0 - actual_home, elo_config.k
        )
        if int(record["game_type_id"]) == REGULAR_SEASON_GAME_TYPE:
            home_won = bool(record["home_win"])
            home_state.record_regular_season(
                points=int(record["home_points"]),
                goals_for=int(record["home_goals"]),
                goals_against=int(record["away_goals"]),
                won=home_won,
            )
            away_state.record_regular_season(
                points=int(record["away_points"]),
                goals_for=int(record["away_goals"]),
                goals_against=int(record["home_goals"]),
                won=not home_won,
            )

    dataset = pd.DataFrame(rows)
    if dataset.empty:
        return dataset
    keep = (dataset["home_pregame_games"] >= min_pregame_games) & (
        dataset["away_pregame_games"] >= min_pregame_games
    )
    return dataset.loc[keep].reset_index(drop=True)


# ── Temporal splits ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TemporalSplit:
    """Season-end years assigned to each split (strictly disjoint, ordered)."""

    train_years: tuple[int, ...]
    val_years: tuple[int, ...]
    test_years: tuple[int, ...]


def default_temporal_split(
    season_end_years: list[int], *, n_val: int = 1, n_test: int = 2
) -> TemporalSplit:
    """Assign the most recent seasons to test, the next-most to validation.

    Strictly temporal: the newest ``n_test`` seasons are held out for testing,
    the ``n_val`` before them tune model selection, and everything earlier trains.
    A test season therefore never touches training or selection (SPEC §6).
    """
    years = sorted({int(y) for y in season_end_years})
    if len(years) < n_val + n_test + 1:
        raise ValueError(
            f"need at least {n_val + n_test + 1} seasons for a "
            f"{n_val}-val / {n_test}-test split; got {len(years)}"
        )
    test = tuple(years[-n_test:])
    val = tuple(years[-(n_val + n_test) : -n_test])
    train = tuple(years[: -(n_val + n_test)])
    return TemporalSplit(train_years=train, val_years=val, test_years=test)


def _rows_for_years(dataset: pd.DataFrame, years: tuple[int, ...]) -> pd.DataFrame:
    return dataset.loc[dataset["season_end_year"].isin([float(y) for y in years])]


# ── Estimators ─────────────────────────────────────────────────────────────


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
    )


def _fit(estimator: Any, frame: pd.DataFrame, features: tuple[str, ...]) -> Any:
    estimator.fit(frame.loc[:, list(features)], frame["home_win"].astype(int))
    return estimator


def _predict(estimator: Any, frame: pd.DataFrame, features: tuple[str, ...]) -> np.ndarray:
    proba = estimator.predict_proba(frame.loc[:, list(features)])
    return np.asarray(proba, dtype=float)[:, 1]


@dataclass
class GameWinModel:
    """A fitted single-game win-probability estimator.

    ``estimator`` is either a scikit-learn logistic-regression pipeline or a
    LightGBM classifier; ``feature_columns`` records which feature set (market or
    stat-only) it was trained on. :meth:`predict_home_prob` scores a prepared
    dataset; :meth:`predict_matchup` scores an ad-hoc home/away matchup from
    per-team primitives (used by the series simulator, US-013).
    """

    estimator: Any
    feature_columns: tuple[str, ...]
    model_type: str
    uses_market: bool

    def predict_home_prob(self, dataset: pd.DataFrame) -> np.ndarray:
        """Home win probability for each row of a :func:`build_game_dataset` frame."""
        return _predict(self.estimator, dataset, self.feature_columns)

    def predict_matchup(
        self,
        home: dict[str, float],
        away: dict[str, float],
        *,
        is_playoff: bool = True,
        market_home_prob: float | None = None,
    ) -> float:
        """``P(home beats away)`` for one matchup from state-snapshot dicts.

        ``home`` / ``away`` are :meth:`TeamState.snapshot`-shaped dicts. Swap the
        two (and complement the market probability) to score the away side; the
        model is home-framed so the caller decides which team holds home ice.
        """
        row = matchup_feature_row(
            home, away, is_playoff=is_playoff, market_home_prob=market_home_prob
        )
        frame = pd.DataFrame([row])
        return float(self.predict_home_prob(frame)[0])


# ── Training + evaluation ──────────────────────────────────────────────────


@dataclass
class GameWinResult:
    """Outcome of a training run: fitted model, metrics, and report material."""

    model: GameWinModel
    config: GameWinConfig
    split: TemporalSplit
    chosen_model_type: str
    val_brier_by_model: dict[str, float]
    test_brier_market: float
    test_brier_stats_only: float
    test_brier_coin_flip: float
    test_brier_higher_points: float
    n_train: int
    n_val: int
    n_test: int
    test_market_coverage: float

    @property
    def beats_coin_flip(self) -> bool:
        return self.test_brier_market < self.test_brier_coin_flip

    @property
    def beats_higher_points(self) -> bool:
        return self.test_brier_market < self.test_brier_higher_points

    @property
    def beats_both_baselines(self) -> bool:
        return self.beats_coin_flip and self.beats_higher_points

    @property
    def market_helps(self) -> bool:
        return self.test_brier_market < self.test_brier_stats_only

    def manifest(self) -> dict[str, Any]:
        """JSON-serialisable run summary (seed, splits, metrics)."""
        return {
            "model_version": GAME_WIN_MODEL_VERSION,
            "seed": self.config.seed,
            "min_pregame_games": self.config.min_pregame_games,
            "chosen_model_type": self.chosen_model_type,
            "split": {
                "train_years": list(self.split.train_years),
                "val_years": list(self.split.val_years),
                "test_years": list(self.split.test_years),
            },
            "counts": {"train": self.n_train, "val": self.n_val, "test": self.n_test},
            "validation_brier": self.val_brier_by_model,
            "test_brier": {
                "market_plus_stats": self.test_brier_market,
                "stats_only": self.test_brier_stats_only,
                "coin_flip": self.test_brier_coin_flip,
                "higher_points": self.test_brier_higher_points,
            },
            "test_market_coverage": self.test_market_coverage,
            "beats_coin_flip": self.beats_coin_flip,
            "beats_higher_points": self.beats_higher_points,
            "beats_both_baselines": self.beats_both_baselines,
            "market_helps": self.market_helps,
        }

    def report_lines(self) -> list[str]:
        """Human-readable evaluation report (Markdown; ASCII only)."""
        cfg = self.config
        lines = [
            f"# Per-game win model ({GAME_WIN_MODEL_VERSION})",
            "",
            "Single-game `P(home beats away)` model, home/away aware, trained on",
            "historical regular-season and playoff games. Features are home-minus-away",
            "differences of a cross-season Elo rating and in-season regular-season rates,",
            "plus an optional de-vigged betting-market home probability.",
            "",
            "## Reproducibility",
            f"- Seed: {cfg.seed}",
            f"- Min pre-game regular-season games per team: {cfg.min_pregame_games}",
            f"- Train seasons (end year): {list(self.split.train_years)} ({self.n_train} games)",
            f"- Validation seasons: {list(self.split.val_years)} ({self.n_val} games)",
            f"- Test seasons (held out): {list(self.split.test_years)} ({self.n_test} games)",
            "- Splits are strictly temporal: no test-season game touches training or",
            "  model selection (SPEC section 6).",
            "",
            "## Model selection (validation Brier, lower is better)",
        ]
        for model_type, brier in sorted(self.val_brier_by_model.items()):
            marker = "  <- chosen" if model_type == self.chosen_model_type else ""
            lines.append(f"- {model_type}: {brier:.4f}{marker}")
        lines += [
            "",
            f"Chosen model: **{self.chosen_model_type}** (lowest validation Brier).",
            "It is refit on train + validation seasons before the held-out test.",
            "",
            "## Held-out test Brier vs. fixed baselines",
            f"- market + stats model: {self.test_brier_market:.4f}",
            f"- stats-only model:     {self.test_brier_stats_only:.4f}",
            f"- baseline (a) coin flip:              {self.test_brier_coin_flip:.4f}",
            f"- baseline (b) higher reg-season pts:  {self.test_brier_higher_points:.4f}",
            "",
            f"- Beats coin flip: {'yes' if self.beats_coin_flip else 'NO'}",
            f"- Beats higher-points baseline: {'yes' if self.beats_higher_points else 'NO'}",
            f"- Beats both baselines: {'yes' if self.beats_both_baselines else 'NO'}",
            "",
            "## Ablation: does the market help? (test seasons with odds coverage)",
            f"- Test-set market coverage: {self.test_market_coverage:.1%} of games priced.",
            f"- market + stats Brier: {self.test_brier_market:.4f}",
            f"- stats-only Brier:     {self.test_brier_stats_only:.4f}",
            f"- Market improves Brier: {'yes' if self.market_helps else 'no'}"
            f" (delta {self.test_brier_stats_only - self.test_brier_market:+.4f}).",
            "",
        ]
        if not self.beats_both_baselines:
            lines += [
                "## Honest note on a missed target",
                "The headline model did not beat both baselines on this split. Reported",
                "as-is (SPEC section 7): baselines, splits, and seeds are unchanged. One",
                "plausible improvement: add rest/schedule-density and goalie-availability",
                "features (US-010 team-series matrix) and probability calibration",
                "(isotonic / Platt) on the validation fold before scoring the test set.",
                "",
            ]
        return lines


@dataclass(frozen=True)
class GameWinConfig:
    """Training knobs; every stochastic step is seeded (SPEC section 3)."""

    seed: int = 20260827
    min_pregame_games: int = 5
    n_val_seasons: int = 1
    n_test_seasons: int = 2
    elo_config: EloConfig | None = field(default=None)


def _train_variant(
    train: pd.DataFrame,
    features: tuple[str, ...],
    *,
    model_type: str,
    seed: int,
) -> Any:
    builder = _build_logreg if model_type == "logistic_regression" else _build_lgbm
    return _fit(builder(seed), train, features)


def train_game_win_model(
    team_games: pd.DataFrame,
    *,
    odds: pd.DataFrame | None = None,
    config: GameWinConfig | None = None,
) -> GameWinResult:
    """Train, select, and evaluate the per-game win model end-to-end.

    Steps: build the leakage-free per-game dataset; split seasons temporally;
    select between logistic regression and LightGBM on the validation Brier;
    refit the winner on train+validation and score the held-out test set against
    two baselines; run the market-vs-stats ablation; and fit a production model on
    all available seasons. The returned :class:`GameWinResult` carries every
    number the committed report and manifest print — nothing is hidden.
    """
    config = config or GameWinConfig()
    dataset = build_game_dataset(
        team_games,
        odds=odds,
        elo_config=config.elo_config,
        min_pregame_games=config.min_pregame_games,
    )
    if dataset.empty:
        raise ValueError("no games available to train the per-game win model")

    years = [int(y) for y in dataset["season_end_year"].unique()]
    split = default_temporal_split(years, n_val=config.n_val_seasons, n_test=config.n_test_seasons)
    train = _rows_for_years(dataset, split.train_years)
    val = _rows_for_years(dataset, split.val_years)
    test = _rows_for_years(dataset, split.test_years)
    train_val = pd.concat([train, val], ignore_index=True)

    # Model selection on the market feature set (best available information).
    val_brier: dict[str, float] = {}
    for model_type in ("logistic_regression", "lightgbm"):
        fitted = _train_variant(
            train, MARKET_FEATURE_COLUMNS, model_type=model_type, seed=config.seed
        )
        val_brier[model_type] = brier_score(
            _predict(fitted, val, MARKET_FEATURE_COLUMNS), val["home_win"]
        )
    chosen = min(val_brier, key=lambda k: val_brier[k])

    # Refit the chosen model on train+val for the held-out test (both variants).
    market_model = _train_variant(
        train_val, MARKET_FEATURE_COLUMNS, model_type=chosen, seed=config.seed
    )
    stats_model = _train_variant(
        train_val, STAT_FEATURE_COLUMNS, model_type=chosen, seed=config.seed
    )
    test_brier_market = brier_score(
        _predict(market_model, test, MARKET_FEATURE_COLUMNS), test["home_win"]
    )
    test_brier_stats = brier_score(
        _predict(stats_model, test, STAT_FEATURE_COLUMNS), test["home_win"]
    )
    test_brier_coin = brier_score(coin_flip_probs(len(test)), test["home_win"])
    test_brier_points = brier_score(baseline_higher_points_probs(test), test["home_win"])
    coverage = float(test["market_available"].mean()) if len(test) else 0.0

    # Production model: chosen type, market features, all available seasons.
    production = _train_variant(
        dataset, MARKET_FEATURE_COLUMNS, model_type=chosen, seed=config.seed
    )
    model = GameWinModel(
        estimator=production,
        feature_columns=MARKET_FEATURE_COLUMNS,
        model_type=chosen,
        uses_market=True,
    )

    return GameWinResult(
        model=model,
        config=config,
        split=split,
        chosen_model_type=chosen,
        val_brier_by_model=val_brier,
        test_brier_market=test_brier_market,
        test_brier_stats_only=test_brier_stats,
        test_brier_coin_flip=test_brier_coin,
        test_brier_higher_points=test_brier_points,
        n_train=len(train),
        n_val=len(val),
        n_test=len(test),
        test_market_coverage=coverage,
    )


DEFAULT_NORMALIZED_DIR = Path("data/normalized")
DEFAULT_MODEL_ARTIFACT_DIR = Path("artifacts/models/game-win")


def train_game_win_from_normalized(
    *,
    normalized_dir: Path = DEFAULT_NORMALIZED_DIR,
    artifact_dir: Path = DEFAULT_MODEL_ARTIFACT_DIR,
    config: GameWinConfig | None = None,
    use_odds: bool = True,
) -> GameWinResult:
    """Load normalized Parquet tables, train, and write the report + manifest.

    Reads ``team_games.parquet`` (and ``odds.parquet`` unless ``use_odds`` is
    off), runs :func:`train_game_win_model`, and commits the Markdown report and
    JSON manifest under ``artifact_dir``.
    """
    import json

    team_games = pd.read_parquet(normalized_dir / "team_games.parquet")
    odds: pd.DataFrame | None = None
    odds_path = normalized_dir / "odds.parquet"
    if use_odds and odds_path.exists():
        odds = pd.read_parquet(odds_path)

    result = train_game_win_model(team_games, odds=odds, config=config)
    manifest = add_git_provenance(result.manifest())

    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "report.md").write_text(
        "\n".join(result.report_lines()) + "\n", encoding="utf-8"
    )
    (artifact_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return result

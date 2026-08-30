"""Skater round-point projections with uncertainty (US-016, PRD US-006 part 2).

Composes three already-built pieces into a per-skater, per-round fantasy-point
projection with quantiles:

1. **Per-game production** (US-014, :mod:`draft_oracle.models.skater_production`):
   ``E[G+A per game]`` for the skater in the upcoming round. In this league a
   skater's fantasy points are goals + assists weighted 1 each
   (:func:`draft_oracle.rules.player_points`), so the per-game production rate is
   exactly the round's expected fantasy points per game.
2. **Series-length distribution** (US-013, :mod:`draft_oracle.models.series_sim`):
   the best-of-7 outcome distribution for the player's team's series gives how many
   games the team plays that round (4/5/6/7 with probabilities that sum to 1) and its
   expectation ``E[series length]``.
3. **Availability** (US-015, :mod:`draft_oracle.models.returns`): the per-game
   availability curve / multiplier haircuts the games the skater actually dresses
   for. Historical evaluation has no injury feed (ESPN cannot supply *historical*
   injuries without leakage, SPEC section 5), so the haircut is a no-op (1.0) in
   backtests; it only bites at live projection time.

**Monte Carlo (seeded, reproducible).** For each skater a round is simulated many
times: draw a series length from the length distribution, and for each of those
games draw the skater's availability (Bernoulli on the availability curve) and, when
available, per-game points from a Poisson with mean equal to the projected per-game
rate. The samples give the mean (``expected_points``) and the ``p10/p50/p90``
quantiles. Every projection is reproducible from ``(seed, season, round, player)``
because the per-skater RNG is seeded deterministically from those keys
(:func:`_row_seed`).

Honesty (SPEC section 7): the committed report writes held-out MAE and Spearman rank
correlation of the projected round points vs. actual round fantasy points, against
two fixed baselines -- (a) regular-season points/game x 5.5 games, and (b) the
player's previous-round fantasy points. A miss is printed as the honest number;
baselines, splits, and seeds are never altered to force a pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from draft_oracle.models.game_win import GameWinConfig, train_game_win_model
from draft_oracle.models.series_sim import (
    _matchup_key,
    _predict_series,
    reconstruct_series_matchups,
    series_length_labels,
)
from draft_oracle.models.shutout import ShutoutConfig, train_shutout_model
from draft_oracle.models.skater_production import (
    LABEL_COLUMN,
    SkaterProductionConfig,
    build_production_dataset,
    mean_absolute_error,
    skater_round_production,
    spearman_correlation,
    train_skater_production_model,
)
from draft_oracle.provenance import add_git_provenance
from draft_oracle.rules import player_points

__all__ = [
    "BASELINE_REG_GAMES",
    "PROJECTION_VERSION",
    "ProjectionConfig",
    "ProjectionResult",
    "RoundProjection",
    "SeasonMetrics",
    "evaluate_skater_projections",
    "evaluate_skater_projections_from_normalized",
    "expected_series_length",
    "normalize_length_probs",
    "project_skater_combined",
    "project_skater_round",
    "simulate_round_points",
]

PROJECTION_VERSION = "skater-projection-v1"

# Baseline (a): regular-season points/game x this many games. 5.5 is the mid-point
# of the 4..7 best-of-7 length range (SPEC section 1); a fixed, documented constant.
BASELINE_REG_GAMES = 5.5

DEFAULT_HORIZON = 7
DEFAULT_N_SIMS = 4000


# -- Pure primitives (each unit-tested) -----------------------------------


def normalize_length_probs(length_probs: dict[int, float]) -> dict[int, float]:
    """Restrict to the four best-of-7 lengths and renormalize to sum 1.

    Missing lengths default to 0. A degenerate all-zero input falls back to a point
    mass on a 6-game series (the modal best-of-7 length) so downstream sampling never
    divides by zero.
    """
    lengths = series_length_labels()
    raw = {length: max(float(length_probs.get(length, 0.0)), 0.0) for length in lengths}
    total = float(sum(raw.values()))
    if total <= 0.0:
        return {length: (1.0 if length == 6 else 0.0) for length in lengths}
    return {length: value / total for length, value in raw.items()}


def expected_series_length(length_probs: dict[int, float]) -> float:
    """Expectation ``sum length * P(length)`` over the normalized length distribution."""
    probs = normalize_length_probs(length_probs)
    return float(sum(length * prob for length, prob in probs.items()))


def _availability_per_game(
    availability_curve: list[float] | tuple[float, ...] | None,
    availability: float,
    horizon: int,
) -> np.ndarray:
    """Per-game availability probabilities over the horizon.

    An explicit ``availability_curve`` (US-015 ``p_available_g1..gH``) wins; otherwise
    a constant ``availability`` multiplier is broadcast across the horizon (1.0 =
    healthy). Values are clamped to ``[0, 1]``.
    """
    if availability_curve is not None:
        arr = np.asarray(list(availability_curve), dtype=float)
        if arr.size < horizon:
            arr = np.concatenate([arr, np.full(horizon - arr.size, arr[-1] if arr.size else 1.0)])
        clipped: np.ndarray = np.clip(arr[:horizon], 0.0, 1.0)
        return clipped
    constant: np.ndarray = np.clip(np.full(horizon, float(availability)), 0.0, 1.0)
    return constant


def _expected_games(length_probs: dict[int, float], avail_per_game: np.ndarray) -> float:
    """Expected games the skater dresses for = sum_L P(L) * sum_{k<=L} avail_k."""
    probs = normalize_length_probs(length_probs)
    total = 0.0
    for length, prob in probs.items():
        total += prob * float(avail_per_game[:length].sum())
    return float(total)


def simulate_round_points(
    rng: np.random.Generator,
    pts_per_game: float,
    length_probs: dict[int, float],
    avail_per_game: np.ndarray,
    *,
    n_sims: int,
) -> np.ndarray:
    """Monte-Carlo samples of a skater's total round fantasy points.

    Each sim draws a series length ``L`` from ``length_probs`` (the team plays every
    game of its series), then for game ``k = 1..L`` the skater is available with
    probability ``avail_per_game[k-1]`` and, when available, scores
    ``Poisson(pts_per_game)`` fantasy points (goals + assists, weighted 1 each). The
    returned array has one summed total per sim; deterministic given ``rng``.
    """
    probs = normalize_length_probs(length_probs)
    lengths = np.asarray(list(probs.keys()), dtype=int)
    weights = np.asarray(list(probs.values()), dtype=float)
    rate = max(float(pts_per_game), 0.0)
    horizon = int(avail_per_game.size)

    drawn_lengths = rng.choice(lengths, size=int(n_sims), p=weights)
    # Availability + scoring are drawn per game up to the horizon; games beyond a
    # sim's drawn length are masked out so they contribute nothing.
    game_index = np.arange(horizon)
    avail_draw = rng.random((int(n_sims), horizon)) < avail_per_game[np.newaxis, :]
    points_draw = rng.poisson(rate, size=(int(n_sims), horizon)).astype(float)
    played = (game_index[np.newaxis, :] < drawn_lengths[:, np.newaxis]) & avail_draw
    totals = (points_draw * played).sum(axis=1)
    return totals


@dataclass(frozen=True)
class RoundProjection:
    """A skater's projected round fantasy points with an uncertainty band.

    ``expected_points`` is the Monte-Carlo mean; ``p10/p50/p90`` are the sampled
    quantiles. The decomposition (``pts_per_game`` x ``expected_games``) explains the
    mean; ``availability_multiplier`` is the US-015 haircut applied to games played.
    """

    expected_points: float
    p10: float
    p50: float
    p90: float
    pts_per_game: float
    expected_games: float
    availability_multiplier: float


def project_skater_round(
    pts_per_game: float,
    length_probs: dict[int, float],
    *,
    availability_curve: list[float] | tuple[float, ...] | None = None,
    availability: float = 1.0,
    seed: int = 20260827,
    n_sims: int = DEFAULT_N_SIMS,
    horizon: int = DEFAULT_HORIZON,
) -> RoundProjection:
    """Project one skater's round fantasy points with p10/p50/p90 quantiles.

    Composes the per-game production rate with the team's series-length distribution
    and the availability haircut, then Monte-Carlos the total. Deterministic given
    ``seed``. ``availability_curve`` (US-015 per-game probabilities) takes precedence
    over the scalar ``availability`` multiplier.
    """
    avail_per_game = _availability_per_game(availability_curve, availability, horizon)
    rng = np.random.default_rng(seed)
    samples = simulate_round_points(rng, pts_per_game, length_probs, avail_per_game, n_sims=n_sims)
    expected_games = _expected_games(length_probs, avail_per_game)
    e_series_length = expected_series_length(length_probs)
    multiplier = expected_games / e_series_length if e_series_length > 0 else 1.0
    p10, p50, p90 = (float(np.quantile(samples, q)) for q in (0.10, 0.50, 0.90))
    return RoundProjection(
        expected_points=float(np.mean(samples)),
        p10=p10,
        p50=p50,
        p90=p90,
        pts_per_game=max(float(pts_per_game), 0.0),
        expected_games=expected_games,
        availability_multiplier=multiplier,
    )


def project_skater_combined(
    pts_per_game: float,
    length_probs_first: dict[int, float],
    p_advance: float,
    length_probs_second: dict[int, float],
    *,
    availability_curve: list[float] | tuple[float, ...] | None = None,
    availability: float = 1.0,
    seed: int = 20260827,
    n_sims: int = DEFAULT_N_SIMS,
    horizon: int = DEFAULT_HORIZON,
) -> RoundProjection:
    """Project a skater's fantasy points across two back-to-back series (a combined draft).

    Models a draft event that spans the team's current series (``length_probs_first``)
    and a *conditional* next series it plays only if it advances (probability
    ``p_advance``, opponent-marginalized ``length_probs_second``). Each sim plays every
    game of the first series, then — with probability ``p_advance`` — every game of the
    second series; per game the skater is available per the (continuous) availability
    curve and, when available, scores ``Poisson(pts_per_game)`` fantasy points. Reduces
    exactly to :func:`project_skater_round` when ``p_advance == 0``. Deterministic given
    ``seed``.
    """
    rate = max(float(pts_per_game), 0.0)
    p_adv = min(max(float(p_advance), 0.0), 1.0)
    span = 2 * int(horizon)
    avail_per_game = _availability_per_game(availability_curve, availability, span)
    rng = np.random.default_rng(seed)

    first = normalize_length_probs(length_probs_first)
    second = normalize_length_probs(length_probs_second)
    lengths_first = np.asarray(list(first.keys()), dtype=int)
    weights_first = np.asarray(list(first.values()), dtype=float)
    lengths_second = np.asarray(list(second.keys()), dtype=int)
    weights_second = np.asarray(list(second.values()), dtype=float)

    n = int(n_sims)
    len_first = rng.choice(lengths_first, size=n, p=weights_first)
    len_second = rng.choice(lengths_second, size=n, p=weights_second)
    advanced = rng.random(n) < p_adv

    game_index = np.arange(span)[np.newaxis, :]
    first_played = game_index < len_first[:, np.newaxis]
    second_played = (
        (game_index >= len_first[:, np.newaxis])
        & (game_index < (len_first + len_second)[:, np.newaxis])
        & advanced[:, np.newaxis]
    )
    avail_draw = rng.random((n, span)) < avail_per_game[np.newaxis, :]
    played = (first_played | second_played) & avail_draw
    points_draw = rng.poisson(rate, size=(n, span)).astype(float)
    samples = (points_draw * played).sum(axis=1)

    avail_first = avail_per_game[:horizon]
    expected_games = _expected_games(length_probs_first, avail_first) + p_adv * _expected_games(
        length_probs_second, avail_first
    )
    e_length = expected_series_length(length_probs_first) + p_adv * expected_series_length(
        length_probs_second
    )
    multiplier = expected_games / e_length if e_length > 0 else 1.0
    p10, p50, p90 = (float(np.quantile(samples, q)) for q in (0.10, 0.50, 0.90))
    return RoundProjection(
        expected_points=float(np.mean(samples)),
        p10=p10,
        p50=p50,
        p90=p90,
        pts_per_game=rate,
        expected_games=expected_games,
        availability_multiplier=multiplier,
    )


# -- Evaluation (report + manifest) ---------------------------------------


@dataclass(frozen=True)
class SeasonMetrics:
    """Held-out projection metrics for a single test season."""

    season_end_year: int
    n: int
    mae: float
    spearman: float


@dataclass(frozen=True)
class ProjectionConfig:
    """Evaluation knobs; every stochastic step is seeded (SPEC section 3)."""

    seed: int = 20260827
    n_test_seasons: int = 2
    n_sims: int = DEFAULT_N_SIMS
    horizon: int = DEFAULT_HORIZON
    production_config: SkaterProductionConfig | None = field(default=None)


@dataclass
class ProjectionResult:
    """Outcome of the round-projection evaluation on held-out seasons."""

    config: ProjectionConfig
    test_years: tuple[int, ...]
    n_projected: int
    n_skipped_no_series: int
    test_mae_model: float
    test_mae_baseline_reg: float
    test_mae_baseline_prev: float
    test_spearman_model: float
    test_spearman_baseline_reg: float
    test_spearman_baseline_prev: float
    per_season: list[SeasonMetrics]
    mean_expected_points: float
    mean_p10: float
    mean_p90: float

    @property
    def beats_reg_baseline(self) -> bool:
        return self.test_mae_model < self.test_mae_baseline_reg

    @property
    def beats_prev_baseline(self) -> bool:
        return self.test_mae_model < self.test_mae_baseline_prev

    @property
    def beats_both_baselines(self) -> bool:
        return self.beats_reg_baseline and self.beats_prev_baseline

    def manifest(self) -> dict[str, Any]:
        """JSON-serialisable run summary (seed, splits, metrics)."""
        return {
            "model_version": PROJECTION_VERSION,
            "seed": self.config.seed,
            "n_sims": self.config.n_sims,
            "horizon": self.config.horizon,
            "baseline_reg_games": BASELINE_REG_GAMES,
            "test_years": list(self.test_years),
            "counts": {
                "projected": self.n_projected,
                "skipped_no_series": self.n_skipped_no_series,
            },
            "test_mae": {
                "model": self.test_mae_model,
                "baseline_reg_ppg_x_games": self.test_mae_baseline_reg,
                "baseline_prev_round": self.test_mae_baseline_prev,
            },
            "test_spearman": {
                "model": self.test_spearman_model,
                "baseline_reg_ppg_x_games": self.test_spearman_baseline_reg,
                "baseline_prev_round": self.test_spearman_baseline_prev,
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
            "uncertainty": {
                "mean_expected_points": self.mean_expected_points,
                "mean_p10": self.mean_p10,
                "mean_p90": self.mean_p90,
            },
            "beats_reg_baseline": self.beats_reg_baseline,
            "beats_prev_baseline": self.beats_prev_baseline,
            "beats_both_baselines": self.beats_both_baselines,
        }

    def report_lines(self) -> list[str]:
        """Human-readable evaluation report (Markdown; ASCII only)."""
        cfg = self.config
        lines = [
            f"# Skater round-point projections ({PROJECTION_VERSION})",
            "",
            "Per skater per round: expected fantasy points (mean) with p10/p50/p90",
            "quantiles, composed from the per-game production model (US-014), the",
            "series-length distribution from the best-of-7 simulator (US-013), and the",
            "availability haircut (US-015). Quantiles come from a seeded Monte Carlo over",
            "the series length and per-game Poisson scoring variance.",
            "",
            "## Reproducibility",
            f"- Seed: {cfg.seed} (per-skater RNG seeded from seed+season+round+player)",
            f"- Monte-Carlo sims per skater: {cfg.n_sims}",
            f"- Round horizon: {cfg.horizon} games (best-of-7)",
            f"- Held-out test seasons (end year): {list(self.test_years)}",
            "- Sub-models (production, per-game win, shutout) are trained ONLY on seasons",
            "  before the held-out set; test-season rounds never touch training",
            "  (SPEC section 6). Historical rounds have no injury feed, so the",
            "  availability haircut is a no-op (1.0) in this backtest.",
            f"- Skater-rounds projected: {self.n_projected} "
            f"(skipped for an unsimulated series: {self.n_skipped_no_series}).",
            "",
            "## Held-out test error vs. fixed baselines (total round points)",
            f"- projection model:            MAE {self.test_mae_model:.4f}, "
            f"Spearman {self.test_spearman_model:.4f}",
            f"- baseline (a) reg-ppg x {BASELINE_REG_GAMES:g}:  MAE "
            f"{self.test_mae_baseline_reg:.4f}, Spearman {self.test_spearman_baseline_reg:.4f}",
            f"- baseline (b) previous round: MAE {self.test_mae_baseline_prev:.4f}, "
            f"Spearman {self.test_spearman_baseline_prev:.4f}",
            "",
            f"- Beats reg-ppg baseline:      {'yes' if self.beats_reg_baseline else 'NO'}",
            f"- Beats previous-round baseline: {'yes' if self.beats_prev_baseline else 'NO'}",
            "",
            "Baseline (b) uses the player's actual fantasy points in the previous playoff",
            f"round; for round 1 (no previous round) it falls back to reg-ppg x "
            f"{BASELINE_REG_GAMES:g}.",
            "",
            "## Uncertainty band (held-out means)",
            f"- mean expected points: {self.mean_expected_points:.3f}",
            f"- mean p10: {self.mean_p10:.3f}   mean p90: {self.mean_p90:.3f}",
            "",
            "## Per held-out season (MAE, Spearman rank correlation)",
        ]
        for m in self.per_season:
            lines.append(
                f"- {m.season_end_year}: n={m.n}, MAE {m.mae:.4f}, Spearman {m.spearman:.4f}"
            )
        if not self.beats_both_baselines:
            lines += [
                "",
                "## Honest note on a missed target",
                "The projection did not beat both fixed baselines on this split. Reported",
                "as-is (SPEC section 7): baselines, splits, and seeds are unchanged. Playoff",
                "point totals over 4-7 games are dominated by scoring variance, so a strong",
                "season-rate baseline is hard to beat on MAE; Spearman rank correlation is the",
                "more informative signal for draft ordering. A plausible improvement: feed the",
                "opponent-adjusted series-win probabilities (US-011 team features) into the",
                "per-game rate so a soft first-round matchup lifts expected games and points.",
            ]
        lines.append("")
        return lines


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
    matchups: dict[tuple[int, int, int], Any],
    win_model: Any,
    shutout_model: Any,
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
        if (
            matchup is None
            or top_id not in matchup.win_snapshots
            or bottom_id not in matchup.win_snapshots
        ):
            continue
        outcome, _sho_top, _sho_bottom = _predict_series(
            win_model, shutout_model, matchup, top_id, bottom_id
        )
        rnd = int(row["playoff_round"]) if not pd.isna(row["playoff_round"]) else 0
        out[(year, rnd, top_id)] = dict(outcome.length_probs)
        out[(year, rnd, bottom_id)] = dict(outcome.length_probs)
    return out


def _previous_round_points(labels: pd.DataFrame) -> dict[tuple[int, int, int], float]:
    """Map ``(season_id, playoff_round, player_id) -> actual round fantasy points``."""
    out: dict[tuple[int, int, int], float] = {}
    for rec in labels.to_dict("records"):
        key = (int(rec["season_id"]), int(rec["playoff_round"]), int(rec["player_id"]))
        out[key] = float(player_points(int(rec["round_goals"]), int(rec["round_assists"])))
    return out


def evaluate_skater_projections(
    skater_games: pd.DataFrame,
    players: pd.DataFrame,
    team_games: pd.DataFrame,
    series: pd.DataFrame,
    *,
    config: ProjectionConfig | None = None,
) -> ProjectionResult:
    """Compose the sub-models and evaluate round projections on held-out seasons.

    Trains the production, per-game win, and shutout models on the non-held-out
    seasons only; reconstructs leakage-free pre-series states; and for every held-out
    skater-round projects expected points + quantiles by Monte Carlo over the team's
    series-length distribution and per-game scoring variance. Scores the projected
    totals against actual round fantasy points and the two fixed baselines. Every
    reported number is carried on the returned :class:`ProjectionResult`.
    """
    config = config or ProjectionConfig()
    prod_config = config.production_config or SkaterProductionConfig(seed=config.seed)

    years = sorted({int(y) for y in series["year"].dropna().unique()})
    if len(years) <= config.n_test_seasons:
        raise ValueError("not enough seasons to hold out a projection test set")
    test_years = tuple(years[-config.n_test_seasons :])
    test_year_set = set(test_years)

    def _keep_train(frame: pd.DataFrame, year_col: pd.Series) -> pd.DataFrame:
        return frame.loc[~year_col.isin(test_year_set)]

    train_sk = _keep_train(skater_games, skater_games["season_id"] % 10000)
    train_tg = _keep_train(team_games, team_games["season_id"] % 10000)
    train_series = _keep_train(series, series["year"].astype(int))
    if train_sk.empty or train_tg.empty or train_series.empty:
        raise ValueError("no training seasons remain after holding out the test set")

    prod_result = train_skater_production_model(
        train_sk, players, train_tg, train_series, config=prod_config
    )
    prod_model = prod_result.model
    win_model = train_game_win_model(
        train_tg, odds=None, config=GameWinConfig(seed=config.seed)
    ).model
    shutout_model = train_shutout_model(train_tg, config=ShutoutConfig(seed=config.seed)).model

    matchups = reconstruct_series_matchups(team_games, series=series)
    length_by_team = _series_length_by_team(
        series, matchups, win_model, shutout_model, test_year_set
    )
    abbrev_to_id = _team_id_by_abbrev(team_games)
    labels = skater_round_production(skater_games, series)
    prev_points = _previous_round_points(labels)

    # Build the held-out feature x label rows and project each skater-round.
    dataset = build_production_dataset(
        skater_games, players, team_games, series, config=prod_config
    )
    test = dataset.loc[dataset["season_end_year"].isin(test_year_set)].reset_index(drop=True)
    if test.empty:
        raise ValueError("no held-out skater-round rows available to project")
    projected = prod_model.project(test)

    rows: list[dict[str, Any]] = []
    n_skipped = 0
    for rec in projected.to_dict("records"):
        season_id = int(rec["season_id"])
        year = season_id % 10000
        rnd = int(rec["playoff_round"])
        player_id = int(rec["player_id"])
        team_id = abbrev_to_id.get(str(rec["team_abbrev"]))
        length_probs = length_by_team.get((year, rnd, team_id)) if team_id is not None else None
        if length_probs is None:
            n_skipped += 1
            continue

        ppg = float(rec["projected_points_per_game"])
        projection = project_skater_round(
            ppg,
            length_probs,
            seed=_row_seed(config.seed, season_id, rnd, player_id),
            n_sims=config.n_sims,
            horizon=config.horizon,
        )
        actual_points = float(rec[LABEL_COLUMN]) * float(rec["round_games"])
        baseline_reg = float(rec["points_per_game"]) * BASELINE_REG_GAMES
        prev_key = (season_id, rnd - 1, player_id)
        baseline_prev = prev_points.get(prev_key, baseline_reg)
        rows.append(
            {
                "season_end_year": year,
                "expected_points": projection.expected_points,
                "actual_points": actual_points,
                "baseline_reg": baseline_reg,
                "baseline_prev": baseline_prev,
                "p10": projection.p10,
                "p90": projection.p90,
            }
        )

    if not rows:
        raise ValueError("no skater-round could be projected (all series unsimulated)")
    scored = pd.DataFrame(rows)
    model_pred = scored["expected_points"].to_numpy(dtype=float)
    actual = scored["actual_points"].to_numpy(dtype=float)
    base_reg = scored["baseline_reg"].to_numpy(dtype=float)
    base_prev = scored["baseline_prev"].to_numpy(dtype=float)

    per_season: list[SeasonMetrics] = []
    for year in sorted(test_year_set):
        mask = scored["season_end_year"].to_numpy() == int(year)
        if not mask.any():
            continue
        per_season.append(
            SeasonMetrics(
                season_end_year=int(year),
                n=int(mask.sum()),
                mae=mean_absolute_error(model_pred[mask], actual[mask]),
                spearman=spearman_correlation(model_pred[mask], actual[mask]),
            )
        )

    return ProjectionResult(
        config=config,
        test_years=test_years,
        n_projected=len(scored),
        n_skipped_no_series=n_skipped,
        test_mae_model=mean_absolute_error(model_pred, actual),
        test_mae_baseline_reg=mean_absolute_error(base_reg, actual),
        test_mae_baseline_prev=mean_absolute_error(base_prev, actual),
        test_spearman_model=spearman_correlation(model_pred, actual),
        test_spearman_baseline_reg=spearman_correlation(base_reg, actual),
        test_spearman_baseline_prev=spearman_correlation(base_prev, actual),
        per_season=per_season,
        mean_expected_points=float(scored["expected_points"].mean()),
        mean_p10=float(scored["p10"].mean()),
        mean_p90=float(scored["p90"].mean()),
    )


DEFAULT_NORMALIZED_DIR = Path("data/normalized")
DEFAULT_MODEL_ARTIFACT_DIR = Path("artifacts/models/skater-projection")


def evaluate_skater_projections_from_normalized(
    *,
    normalized_dir: Path = DEFAULT_NORMALIZED_DIR,
    artifact_dir: Path = DEFAULT_MODEL_ARTIFACT_DIR,
    config: ProjectionConfig | None = None,
) -> ProjectionResult:
    """Load normalized Parquet tables, evaluate, and write the report + manifest.

    Reads ``skater_games`` / ``players`` / ``team_games`` / ``series``, runs
    :func:`evaluate_skater_projections`, and commits the Markdown report and JSON
    manifest under ``artifact_dir`` (both re-included in .gitignore).
    """
    import json

    skater_games = pd.read_parquet(normalized_dir / "skater_games.parquet")
    players = pd.read_parquet(normalized_dir / "players.parquet")
    team_games = pd.read_parquet(normalized_dir / "team_games.parquet")
    series = pd.read_parquet(normalized_dir / "series.parquet")

    result = evaluate_skater_projections(skater_games, players, team_games, series, config=config)
    manifest = add_git_provenance(result.manifest())

    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "report.md").write_text(
        "\n".join(result.report_lines()) + "\n", encoding="utf-8"
    )
    (artifact_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return result

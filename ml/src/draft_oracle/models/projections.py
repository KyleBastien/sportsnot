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
from typing import Any, cast

import numpy as np
import pandas as pd

from draft_oracle.models._projection_evaluation import (
    _previous_round_points as _previous_round_points,
)
from draft_oracle.models._projection_evaluation import (
    _row_seed as _row_seed,
)
from draft_oracle.models._projection_evaluation import (
    _series_length_by_team as _series_length_by_team,
)
from draft_oracle.models._projection_evaluation import (
    _team_id_by_abbrev as _team_id_by_abbrev,
)
from draft_oracle.models._projection_evaluation import (
    evaluate_projection_model,
)
from draft_oracle.models.series_sim import (
    series_length_labels,
)
from draft_oracle.models.skater_production import (
    SkaterProductionConfig,
)
from draft_oracle.provenance import add_git_provenance

__all__ = [
    "BASELINE_REG_GAMES",
    "PROJECTION_VERSION",
    "CombinedRoundRequest",
    "ProjectionConfig",
    "ProjectionEvaluationRequest",
    "ProjectionResult",
    "ProjectionRuntime",
    "RoundProjection",
    "RoundSimulationInput",
    "SeasonMetrics",
    "SkaterRoundRequest",
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


@dataclass(frozen=True)
class RoundSimulationInput:
    pts_per_game: float
    length_probs: dict[int, float]
    avail_per_game: np.ndarray
    n_sims: int


def simulate_round_points(
    rng: np.random.Generator,
    scenario: RoundSimulationInput | float,
    *legacy_args: object,
    n_sims: int | None = None,
) -> np.ndarray:
    """Monte-Carlo samples of a skater's total round fantasy points.

    Each sim draws a series length ``L`` from ``length_probs`` (the team plays every
    game of its series), then for game ``k = 1..L`` the skater is available with
    probability ``avail_per_game[k-1]`` and, when available, scores
    ``Poisson(pts_per_game)`` fantasy points (goals + assists, weighted 1 each). The
    returned array has one summed total per sim; deterministic given ``rng``.
    """
    resolved = _round_simulation_input(scenario, legacy_args, n_sims)
    probs = normalize_length_probs(resolved.length_probs)
    lengths = np.asarray(list(probs.keys()), dtype=int)
    weights = np.asarray(list(probs.values()), dtype=float)
    rate = max(float(resolved.pts_per_game), 0.0)
    horizon = int(resolved.avail_per_game.size)

    drawn_lengths = rng.choice(lengths, size=int(resolved.n_sims), p=weights)
    # Availability + scoring are drawn per game up to the horizon; games beyond a
    # sim's drawn length are masked out so they contribute nothing.
    game_index = np.arange(horizon)
    avail_draw = rng.random((int(resolved.n_sims), horizon)) < resolved.avail_per_game[
        np.newaxis, :
    ]
    points_draw = rng.poisson(rate, size=(int(resolved.n_sims), horizon)).astype(float)
    played = (game_index[np.newaxis, :] < drawn_lengths[:, np.newaxis]) & avail_draw
    totals = (points_draw * played).sum(axis=1)
    return totals


def _round_simulation_input(
    scenario: RoundSimulationInput | float,
    legacy_args: tuple[object, ...],
    n_sims: int | None,
) -> RoundSimulationInput:
    if isinstance(scenario, RoundSimulationInput):
        return scenario
    if n_sims is None or len(legacy_args) != 2:
        raise TypeError(
            "legacy simulate_round_points calls require length_probs, availability, n_sims"
        )
    return RoundSimulationInput(
        pts_per_game=float(scenario),
        length_probs=cast(dict[int, float], legacy_args[0]),
        avail_per_game=cast(np.ndarray, legacy_args[1]),
        n_sims=n_sims,
    )


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


@dataclass(frozen=True)
class SkaterRoundRequest:
    pts_per_game: float
    length_probs: dict[int, float]
    availability_curve: list[float] | tuple[float, ...] | None = None
    availability: float = 1.0


@dataclass(frozen=True)
class ProjectionRuntime:
    seed: int = 20260827
    n_sims: int = DEFAULT_N_SIMS
    horizon: int = DEFAULT_HORIZON


def _resolve_projection_runtime(
    runtime: ProjectionRuntime | None,
    legacy_kwargs: dict[str, object],
) -> ProjectionRuntime:
    if runtime is not None and legacy_kwargs:
        raise TypeError("pass runtime or seed/n_sims/horizon kwargs, not both")
    if runtime is not None:
        return runtime
    defaults = ProjectionRuntime()
    unexpected = set(legacy_kwargs) - {"seed", "n_sims", "horizon"}
    if unexpected:
        names = ", ".join(sorted(unexpected))
        raise TypeError(f"unexpected project_skater_round kwargs: {names}")
    return ProjectionRuntime(
        seed=_int_kwarg(legacy_kwargs, "seed", defaults.seed),
        n_sims=_int_kwarg(legacy_kwargs, "n_sims", defaults.n_sims),
        horizon=_int_kwarg(legacy_kwargs, "horizon", defaults.horizon),
    )


def _int_kwarg(legacy_kwargs: dict[str, object], key: str, default: int) -> int:
    value = legacy_kwargs.get(key, default)
    if not isinstance(value, int):
        raise TypeError(f"{key} must be an int")
    return value


def _float_kwarg(legacy_kwargs: dict[str, object], key: str, default: float) -> float:
    value = legacy_kwargs.get(key, default)
    if not isinstance(value, int | float):
        raise TypeError(f"{key} must be numeric")
    return float(value)


def _float_value(value: object, name: str) -> float:
    if not isinstance(value, int | float):
        raise TypeError(f"{name} must be numeric")
    return float(value)


def project_skater_round(
    request: SkaterRoundRequest,
    runtime: ProjectionRuntime | None = None,
    **legacy_kwargs: object,
) -> RoundProjection:
    """Project one skater's round fantasy points with p10/p50/p90 quantiles.

    Composes the per-game production rate with the team's series-length distribution
    and the availability haircut, then Monte-Carlos the total. Deterministic given
    ``seed``. ``availability_curve`` (US-015 per-game probabilities) takes precedence
    over the scalar ``availability`` multiplier.
    """
    resolved_runtime = _resolve_projection_runtime(runtime, legacy_kwargs)
    avail_per_game = _availability_per_game(
        request.availability_curve,
        request.availability,
        resolved_runtime.horizon,
    )
    rng = np.random.default_rng(resolved_runtime.seed)
    samples = simulate_round_points(
        rng,
        RoundSimulationInput(
            pts_per_game=request.pts_per_game,
            length_probs=request.length_probs,
            avail_per_game=avail_per_game,
            n_sims=resolved_runtime.n_sims,
        ),
    )
    expected_games = _expected_games(request.length_probs, avail_per_game)
    e_series_length = expected_series_length(request.length_probs)
    multiplier = expected_games / e_series_length if e_series_length > 0 else 1.0
    p10, p50, p90 = (float(np.quantile(samples, q)) for q in (0.10, 0.50, 0.90))
    return RoundProjection(
        expected_points=float(np.mean(samples)),
        p10=p10,
        p50=p50,
        p90=p90,
        pts_per_game=max(float(request.pts_per_game), 0.0),
        expected_games=expected_games,
        availability_multiplier=multiplier,
    )


@dataclass(frozen=True)
class CombinedRoundRequest:
    pts_per_game: float
    length_probs_first: dict[int, float]
    p_advance: float
    length_probs_second: dict[int, float]
    availability_curve: list[float] | tuple[float, ...] | None = None
    availability: float = 1.0


def _resolve_combined_round_request(
    request: CombinedRoundRequest | float,
    first_or_runtime: dict[int, float] | ProjectionRuntime | None,
    legacy_args: tuple[object, ...],
    legacy_kwargs: dict[str, object],
) -> tuple[CombinedRoundRequest, ProjectionRuntime]:
    if isinstance(request, CombinedRoundRequest):
        return _resolve_combined_request_data(
            request,
            first_or_runtime,
            legacy_args,
            legacy_kwargs,
        )

    if not isinstance(first_or_runtime, dict) or len(legacy_args) != 2:
        raise TypeError(
            "legacy project_skater_combined calls require first/second length probs and p_advance"
        )

    unexpected = set(legacy_kwargs) - {
        "availability_curve",
        "availability",
        "seed",
        "n_sims",
        "horizon",
    }
    if unexpected:
        names = ", ".join(sorted(unexpected))
        raise TypeError(f"unexpected project_skater_combined kwargs: {names}")

    request_data = CombinedRoundRequest(
        pts_per_game=float(request),
        length_probs_first=first_or_runtime,
        p_advance=_float_value(legacy_args[0], "p_advance"),
        length_probs_second=cast(dict[int, float], legacy_args[1]),
        availability_curve=cast(
            list[float] | tuple[float, ...] | None,
            legacy_kwargs.get("availability_curve"),
        ),
        availability=_float_kwarg(legacy_kwargs, "availability", 1.0),
    )
    runtime_kwargs = {
        key: value
        for key, value in legacy_kwargs.items()
        if key in {"seed", "n_sims", "horizon"}
    }
    return request_data, _resolve_projection_runtime(None, runtime_kwargs)


def _resolve_combined_request_data(
    request: CombinedRoundRequest,
    first_or_runtime: dict[int, float] | ProjectionRuntime | None,
    legacy_args: tuple[object, ...],
    legacy_kwargs: dict[str, object],
) -> tuple[CombinedRoundRequest, ProjectionRuntime]:
    runtime = _resolve_projection_runtime(
        first_or_runtime if isinstance(first_or_runtime, ProjectionRuntime) else None,
        legacy_kwargs,
    )
    if legacy_args:
        raise TypeError("combined request calls do not accept extra positional arguments")
    wrong_runtime = (
        first_or_runtime is not None
        and not isinstance(first_or_runtime, ProjectionRuntime)
    )
    if wrong_runtime:
        raise TypeError("combined request calls accept only ProjectionRuntime as second argument")
    return request, runtime


def project_skater_combined(
    request: CombinedRoundRequest | float,
    first_or_runtime: dict[int, float] | ProjectionRuntime | None = None,
    *legacy_args: object,
    **legacy_kwargs: object,
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
    resolved_request, runtime = _resolve_combined_round_request(
        request,
        first_or_runtime,
        legacy_args,
        legacy_kwargs,
    )
    rate = max(float(resolved_request.pts_per_game), 0.0)
    p_adv = min(max(float(resolved_request.p_advance), 0.0), 1.0)
    span = 2 * int(runtime.horizon)
    avail_per_game = _availability_per_game(
        resolved_request.availability_curve,
        resolved_request.availability,
        span,
    )
    rng = np.random.default_rng(runtime.seed)

    first = normalize_length_probs(resolved_request.length_probs_first)
    second = normalize_length_probs(resolved_request.length_probs_second)
    lengths_first = np.asarray(list(first.keys()), dtype=int)
    weights_first = np.asarray(list(first.values()), dtype=float)
    lengths_second = np.asarray(list(second.keys()), dtype=int)
    weights_second = np.asarray(list(second.values()), dtype=float)

    n = int(runtime.n_sims)
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

    avail_first = avail_per_game[: runtime.horizon]
    expected_games = _expected_games(
        resolved_request.length_probs_first,
        avail_first,
    ) + p_adv * _expected_games(
        resolved_request.length_probs_second,
        avail_first,
    )
    e_length = expected_series_length(
        resolved_request.length_probs_first
    ) + p_adv * expected_series_length(resolved_request.length_probs_second)
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


@dataclass(frozen=True)
class ProjectionEvaluationRequest:
    skater_games: pd.DataFrame
    players: pd.DataFrame
    team_games: pd.DataFrame
    series: pd.DataFrame
    config: ProjectionConfig | None = None


def _resolve_projection_evaluation_request(
    request: ProjectionEvaluationRequest | pd.DataFrame,
    legacy_args: tuple[object, ...],
    config: ProjectionConfig | None,
) -> ProjectionEvaluationRequest:
    if isinstance(request, ProjectionEvaluationRequest):
        if legacy_args or config is not None:
            raise TypeError("pass ProjectionEvaluationRequest or legacy dataframes, not both")
        return request
    if len(legacy_args) != 3:
        raise TypeError(
            "legacy evaluate_skater_projections calls require players, team_games, and series"
        )
    players, team_games, series = legacy_args
    return ProjectionEvaluationRequest(
        skater_games=request,
        players=cast(pd.DataFrame, players),
        team_games=cast(pd.DataFrame, team_games),
        series=cast(pd.DataFrame, series),
        config=config,
    )


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


def evaluate_skater_projections(
    request: ProjectionEvaluationRequest | pd.DataFrame,
    *legacy_args: object,
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
    resolved_request = _resolve_projection_evaluation_request(request, legacy_args, config)
    resolved_config = resolved_request.config or ProjectionConfig()
    evaluation = evaluate_projection_model(
        ProjectionEvaluationRequest(
            skater_games=resolved_request.skater_games,
            players=resolved_request.players,
            team_games=resolved_request.team_games,
            series=resolved_request.series,
            config=resolved_config,
        ),
        project_round=project_skater_round,
        baseline_reg_games=BASELINE_REG_GAMES,
    )
    per_season = [
        SeasonMetrics(
            season_end_year=m.season_end_year,
            n=m.n,
            mae=m.mae,
            spearman=m.spearman,
        )
        for m in evaluation.per_season
    ]

    return ProjectionResult(
        config=resolved_config,
        test_years=evaluation.test_years,
        n_projected=evaluation.n_projected,
        n_skipped_no_series=evaluation.n_skipped_no_series,
        test_mae_model=evaluation.test_mae_model,
        test_mae_baseline_reg=evaluation.test_mae_baseline_reg,
        test_mae_baseline_prev=evaluation.test_mae_baseline_prev,
        test_spearman_model=evaluation.test_spearman_model,
        test_spearman_baseline_reg=evaluation.test_spearman_baseline_reg,
        test_spearman_baseline_prev=evaluation.test_spearman_baseline_prev,
        per_season=per_season,
        mean_expected_points=evaluation.mean_expected_points,
        mean_p10=evaluation.mean_p10,
        mean_p90=evaluation.mean_p90,
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

    result = evaluate_skater_projections(
        ProjectionEvaluationRequest(skater_games, players, team_games, series, config)
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

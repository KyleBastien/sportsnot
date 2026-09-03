"""IR-stash valuation with the retroactive point-swap rule (US-022, PRD US-011 part 3).

An IR slot lets a manager roster an *injured* skater who cannot help the active
lineup yet. In this league IR activation is a **retroactive same-position swap**
(SPEC section 1): when the stashed player is activated they replace a same-position
active starter (``F`` swaps ``F``, ``D`` swaps ``D``) and, crucially, their points
count **from the start of the round** -- the swap rewrites the whole round, it is not
additive. A manager who stashes an injured star and activates optimally therefore
ends the round with *whichever of the two same-position players scored more*.

That single fact is :func:`retroactive_swap_points`::

    slot_pair_points = max(ir_player_round_points, active_starter_round_points)

so the marginal value an IR slot adds over simply rostering the replacement-level
active starter it would swap out is ``E[max(X - Y, 0)]`` -- the stash only ever helps,
never hurts, because you keep the starter when the stash underperforms.

The stash EV composes the two upstream models honestly:

* **US-015 return timing** (:mod:`draft_oracle.models.returns`): the per-game
  availability curve says *when* the injured player is back, so a long-shot stash that
  returns in game 6 of a short series contributes almost nothing.
* **US-016 round projections** (:mod:`draft_oracle.models.projections`): the per-game
  production rate + the team's series-length distribution drive the Monte-Carlo of the
  points the stash *would* score once available.

The cheat sheet's IR section (rendered by :func:`render_ir_section`) ranks injured
``F``/``D`` by stash value against the healthy replacement-level alternative a manager
could take instead, with a plain ``stash`` / ``avoid`` verdict. The optimizer prices
``IR_F`` / ``IR_D`` slots by that stash value via :func:`reprice_pool_for_ir` so an
injured star is valued for what an IR stash is really worth, not for full-health
points.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from draft_oracle.models.projections import (
    DEFAULT_HORIZON,
    DEFAULT_N_SIMS,
    _availability_per_game,
    expected_series_length,
    simulate_round_points,
)
from draft_oracle.optimize.ir_pool import reprice_pool_for_ir

__all__ = [
    "DEFAULT_STASH_HORIZON",
    "DEFAULT_STASH_N_SIMS",
    "StashInput",
    "StashValuation",
    "build_stash_valuations",
    "healthy_alternative_value",
    "render_ir_section",
    "reprice_pool_for_ir",
    "retroactive_swap_points",
    "round_points_with_return",
    "simulate_stash_samples",
    "value_stash",
]

DEFAULT_STASH_HORIZON = DEFAULT_HORIZON
DEFAULT_STASH_N_SIMS = DEFAULT_N_SIMS

# Verdict labels for the cheat-sheet IR section.
VERDICT_STASH = "stash"
VERDICT_AVOID = "avoid"


@dataclass(frozen=True)
class _StashSimulationInput:
    pts_per_game: float
    length_probs: Mapping[int, float]
    availability_curve: Sequence[float] | None


@dataclass(frozen=True)
class _StashValueRequest:
    pts_per_game: float
    length_probs: Mapping[int, float]
    availability_curve: Sequence[float] | None
    active_baseline: float


@dataclass(frozen=True)
class _HealthyAlternativeRequest:
    active_baseline: float
    length_probs: Mapping[int, float]


@dataclass(frozen=True)
class _BuildStashRequest:
    inputs: Sequence[StashInput]
    replacement_by_position: Mapping[str, float]


def retroactive_swap_points(ir_points: float, active_points: float) -> float:
    """Points an IR slot pair yields after an *optimal* retroactive activation.

    On activation the stashed player's whole-round points **replace** the swapped
    same-position active starter's points from the start of the round (SPEC section 1),
    so the manager keeps whichever scored more. The swap is a full replacement, never
    additive -- a stash that scores less than the starter is simply never activated.
    """
    return max(float(ir_points), float(active_points))


def round_points_with_return(
    per_game_points: Sequence[float],
    series_length: int,
    return_game: int,
) -> float:
    """Points a returning stash accrues in one round (deterministic, hand-computable).

    The player scores ``per_game_points[k - 1]`` in each round game ``k`` from
    ``return_game`` on, and nothing in the games they are still out for. ``return_game
    <= 1`` means available all round; a ``return_game`` past ``series_length`` means
    they never return and score ``0``.
    """
    if series_length < 0:
        raise ValueError(f"series_length must be >= 0, got {series_length}")
    total = 0.0
    for k in range(1, series_length + 1):
        if k >= return_game:
            total += float(per_game_points[k - 1])
    return total


def simulate_stash_samples(
    rng: np.random.Generator,
    stash_input: _StashSimulationInput,
    *,
    n_sims: int,
    horizon: int,
) -> np.ndarray:
    """Monte-Carlo samples of the round points a stashed player *would* score.

    Draws a series length from ``length_probs`` and, per game, the player's
    availability (from the US-015 ``availability_curve`` when given, else fully
    healthy) and Poisson production at ``pts_per_game`` -- exactly the US-016 round
    simulation, restricted to the stash's own scoring (the swap is applied by the
    caller).
    """
    avail = _availability_per_game(
        (
            list(stash_input.availability_curve)
            if stash_input.availability_curve is not None
            else None
        ),
        1.0,
        horizon,
    )
    return simulate_round_points(
        rng,
        stash_input.pts_per_game,
        dict(stash_input.length_probs),
        avail,
        n_sims=n_sims,
    )


def value_stash(
    request: _StashValueRequest,
    *,
    seed: int,
    n_sims: int = DEFAULT_STASH_N_SIMS,
    horizon: int = DEFAULT_STASH_HORIZON,
) -> tuple[float, float, float]:
    """Stash EV, marginal stash value, and activation probability for one player.

    ``active_baseline`` is the expected round points of the replacement-level active
    starter the stash would swap out (US-018 replacement level). Returns
    ``(stash_ev, stash_value, activation_prob)`` where ``stash_ev`` is
    ``E[max(round_points, active_baseline)]`` (the retroactive-swap EV), ``stash_value``
    is the marginal gain over just rostering that starter, and ``activation_prob`` is
    ``P(round_points > active_baseline)`` -- how often the stash is actually activated.
    """
    rng = np.random.default_rng(seed)
    samples = simulate_stash_samples(
        rng,
        _StashSimulationInput(
            request.pts_per_game,
            request.length_probs,
            request.availability_curve,
        ),
        n_sims=n_sims,
        horizon=horizon,
    )
    baseline = float(request.active_baseline)
    swapped = np.maximum(samples, baseline)
    stash_ev = float(np.mean(swapped))
    stash_value = stash_ev - baseline
    activation_prob = float(np.mean(samples > baseline))
    return stash_ev, stash_value, activation_prob


def healthy_alternative_value(
    request: _HealthyAlternativeRequest,
    *,
    seed: int,
    n_sims: int = DEFAULT_STASH_N_SIMS,
    horizon: int = DEFAULT_STASH_HORIZON,
) -> float:
    """Marginal IR value of the healthy replacement-level alternative.

    The counterfactual to stashing an injured star is spending the pick on a healthy
    replacement-level ``F``/``D``. That player is fully available, so its per-game rate
    is set to reproduce ``active_baseline`` expected round points, and its marginal IR
    value ``E[max(Z - active_baseline, 0)]`` is the pure upside a replacement-level body
    adds through the same swap. A stash is only worth it when it clears this bar.
    """
    e_len = expected_series_length(dict(request.length_probs))
    ppg = float(request.active_baseline) / e_len if e_len > 0 else 0.0
    _stash_ev, stash_value, _prob = value_stash(
        _StashValueRequest(ppg, request.length_probs, None, request.active_baseline),
        seed=seed,
        n_sims=n_sims,
        horizon=horizon,
    )
    return stash_value


@dataclass(frozen=True)
class StashInput:
    """One injured skater's inputs to the stash valuation."""

    player_id: int
    player_name: str
    position: str  # "F" or "D"
    team_abbrev: str
    status: str
    pts_per_game: float
    length_probs: Mapping[int, float]
    availability_curve: Sequence[float]
    expected_games_available: float


@dataclass(frozen=True)
class StashValuation:
    """Retroactive-swap stash valuation for one injured skater, with a verdict."""

    player_id: int
    player_name: str
    position: str
    team_abbrev: str
    status: str
    stash_ev: float
    active_baseline: float
    stash_value: float
    activation_prob: float
    expected_games_available: float
    healthy_alt_value: float
    verdict: str

    @property
    def edge(self) -> float:
        """Stash value minus the healthy replacement-level alternative's value."""
        return self.stash_value - self.healthy_alt_value


def build_stash_valuations(
    request: _BuildStashRequest,
    *,
    seed: int = 20260827,
    n_sims: int = DEFAULT_STASH_N_SIMS,
    horizon: int = DEFAULT_STASH_HORIZON,
) -> list[StashValuation]:
    """Value every injured skater and rank them by stash value (descending).

    Each player is swapped against its position's replacement-level active starter
    (``replacement_by_position``; SPEC forbids cross-position swaps, so ``F`` uses the
    ``F`` level and ``D`` the ``D`` level). The verdict is ``stash`` when the stash
    value beats the healthy replacement-level alternative for the same slot, else
    ``avoid``. Deterministic given ``seed``: each player's RNG is offset by its id.
    """
    valuations: list[StashValuation] = []
    for item in request.inputs:
        baseline = float(request.replacement_by_position.get(item.position, 0.0))
        player_seed = seed + int(item.player_id)
        stash_ev, stash_value, activation_prob = value_stash(
            _StashValueRequest(
                item.pts_per_game,
                item.length_probs,
                item.availability_curve,
                baseline,
            ),
            seed=player_seed,
            n_sims=n_sims,
            horizon=horizon,
        )
        alt_value = healthy_alternative_value(
            _HealthyAlternativeRequest(baseline, item.length_probs),
            seed=player_seed + 1,
            n_sims=n_sims,
            horizon=horizon,
        )
        verdict = VERDICT_STASH if stash_value > alt_value else VERDICT_AVOID
        valuations.append(
            StashValuation(
                player_id=item.player_id,
                player_name=item.player_name,
                position=item.position,
                team_abbrev=item.team_abbrev,
                status=item.status,
                stash_ev=stash_ev,
                active_baseline=baseline,
                stash_value=stash_value,
                activation_prob=activation_prob,
                expected_games_available=item.expected_games_available,
                healthy_alt_value=alt_value,
                verdict=verdict,
            )
        )
    valuations.sort(key=lambda v: (-v.stash_value, -v.activation_prob, v.player_id))
    return valuations


def _fmt(value: float) -> str:
    """Two-decimal cell, ``-`` for a missing (NaN) value; ASCII only (SPEC honesty)."""
    if value != value:  # NaN
        return "-"
    return f"{float(value):.2f}"


def render_ir_section(valuations: Sequence[StashValuation]) -> list[str]:
    """ASCII Markdown lines for the cheat sheet's IR-stash section.

    Ranks injured F/D by stash value with the retroactive-swap EV, the replacement-level
    active starter they swap, the activation probability, the healthy-alternative bar,
    and the ``stash`` / ``avoid`` verdict. Returns ``[]`` when there is nothing to stash.
    """
    if not valuations:
        return []
    lines: list[str] = [
        "",
        "## IR stash candidates",
        "",
        "Injured skaters valued by the retroactive same-position swap (SPEC section 1):",
        "on activation the stash's whole-round points replace the swapped starter's, so",
        "the slot yields max(stash, starter). `Stash EV` is that expectation; `Value` is",
        "the marginal gain over the replacement-level starter; `Alt` is what a healthy",
        "replacement-level pick would add instead. Verdict is stash when Value beats Alt.",
        "",
        (
            "| Rank | Pos | Player | Team | Status | E[games] | Swap | "
            "Stash EV | Value | Activate | Alt | Verdict |"
        ),
        (
            "| ---: | :-- | :----- | :--- | :----- | -------: | ---: | "
            "-------: | ----: | -------: | --: | :------ |"
        ),
    ]
    for rank, val in enumerate(valuations, start=1):
        games = _fmt(val.expected_games_available)
        swap = _fmt(val.active_baseline)
        ev = _fmt(val.stash_ev)
        value = _fmt(val.stash_value)
        activate = _fmt(val.activation_prob)
        alt = _fmt(val.healthy_alt_value)
        lines.append(
            f"| {rank} | {val.position} | {val.player_name} | {val.team_abbrev} "
            f"| {val.status} | {games} | {swap} | {ev} | {value} | {activate} "
            f"| {alt} | {val.verdict} |"
        )
    return lines

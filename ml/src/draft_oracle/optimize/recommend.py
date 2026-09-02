"""Multi-step pick recommendation engine (US-021) — public surface.

Greedy value-over-replacement (US-018) answers *which asset is worth the most in a
vacuum*. It does **not** answer the question a drafter on the clock actually asks:
*which pick, right now, leaves me with the best final roster once the rest of the
draft plays out against these specific opponents?* Those differ whenever a position
is about to run dry, or a target will obviously survive to your next turn, or a
forced slot looms — exactly the situations where greedy leaves points on the board.

This module rolls the whole remaining draft forward with Monte-Carlo simulation:

* the owner tentatively makes each candidate pick,
* the fitted opponent model (US-020, or the greedy fallback, US-019) drafts through
  every one of the owner's remaining turns,
* the owner's *future* slots are filled by a fast value-over-replacement rollout
  policy, and
* the owner's total final-roster projection is averaged across many seeded rollouts.

The recommended pick is the ``argmax`` of that expected final-roster value. Because
the opponents are simulated, the engine automatically prefers a scarce-position asset
that will not survive to the next turn over a safe one that will, times a goalie slot
correctly, and respects forced picks when a manager's roster is nearly full.

Determinism (SPEC section 3): every rollout draws from ``random.Random`` seeded from
``(config.seed, candidate index, rollout index)`` so ``(state, config)`` fully
determines the recommendation.

Speed (acceptance): a full-depth recommendation must finish in <10 s at any state of
a 12-manager 11-pick draft. Three levers keep it there without lowering the rollout
count below the spec floor: candidate pruning, an owner-full early stop, and depth
capping (see :mod:`draft_oracle.optimize._recommend_kernels`).

The value primitives, config, and object-model rollout live in
:mod:`draft_oracle.optimize._recommend_core`; the vectorized fast-path kernels in
:mod:`draft_oracle.optimize._recommend_kernels`; and the honest strategy comparison in
:mod:`draft_oracle.optimize._recommend_strategies`. They are re-exported here so the
public import paths (``draft_oracle.optimize.recommend.X``) stay stable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

from draft_oracle.optimize._recommend_core import (
    DEFAULT_MAX_CANDIDATES,
    DEFAULT_ROLLOUTS,
    DEFAULT_SURVIVAL_ROLLOUTS,
    RecommendConfig,
    asset_value,
    greedy_vor_pick,
    replacement_levels,
)
from draft_oracle.optimize._recommend_core import (
    _prune_candidates as _prune_candidates,
)
from draft_oracle.optimize._recommend_kernels import (
    _expected_value as _expected_value,
)
from draft_oracle.optimize._recommend_kernels import (
    _expected_values,
    choose_pick,
)
from draft_oracle.optimize._recommend_kernels import (
    _fitted_zero_temp_models as _fitted_zero_temp_models,
)
from draft_oracle.optimize._recommend_kernels import (
    _vectorized_fitted_expected as _vectorized_fitted_expected,
)
from draft_oracle.optimize._recommend_kernels import (
    _vectorized_greedy_expected as _vectorized_greedy_expected,
)
from draft_oracle.optimize._recommend_strategies import (
    DEFAULT_RECOMMEND_ARTIFACT_DIR,
    StrategyComparison,
    build_synthetic_pool,
    compare_strategies,
    evaluate_recommendation_strategies_from_normalized,
)
from draft_oracle.optimize._recommend_strategies import (
    _PositionRunOpponent as _PositionRunOpponent,
)
from draft_oracle.optimize.simulator import (
    DraftAsset,
    DraftState,
    OpponentModel,
    survival_probability,
)

__all__ = [
    "DEFAULT_MAX_CANDIDATES",
    "DEFAULT_RECOMMEND_ARTIFACT_DIR",
    "DEFAULT_ROLLOUTS",
    "DEFAULT_SURVIVAL_ROLLOUTS",
    "PickEvaluation",
    "RecommendConfig",
    "Recommendation",
    "StrategyComparison",
    "asset_value",
    "build_pool_from_frames",
    "build_pool_from_projection_artifact",
    "build_synthetic_pool",
    "choose_pick",
    "compare_strategies",
    "evaluate_recommendation_strategies_from_normalized",
    "greedy_vor_pick",
    "recommend_pick",
    "replacement_levels",
]


@dataclass(frozen=True)
class PickEvaluation:
    """One candidate's rolled-out value plus the reasoning behind it."""

    asset: DraftAsset
    expected_points: float
    immediate_value: float
    vor: float
    replacement: float
    survival: float
    open_slots: int
    position_limit: int
    delta_vs_next: float = 0.0

    def explanation(self) -> str:
        """One ASCII line of why this pick ranks where it does (SPEC honesty)."""
        need = f"{self.open_slots}/{self.position_limit} {self.asset.position} slots open"
        return (
            f"E[roster] {self.expected_points:.2f} "
            f"(proj {self.immediate_value:.2f}, VOR {self.vor:+.2f}); "
            f"P(survives to next pick) {self.survival:.2f}; "
            f"{need}; delta vs #2 {self.delta_vs_next:+.2f}"
        )


@dataclass
class Recommendation:
    """Ranked, explained pick recommendations for the owner on the clock."""

    owner: str
    pick_index: int
    rollouts: int
    depth: int | None
    replacement: dict[str, float]
    evaluations: list[PickEvaluation]
    candidates_considered: int
    seed: int = 20260827

    @property
    def best(self) -> PickEvaluation:
        """The single recommended pick (highest expected final-roster value)."""
        if not self.evaluations:
            raise ValueError("no evaluations; the owner has no legal pick")
        return self.evaluations[0]

    def top(self, n: int | None = None) -> list[PickEvaluation]:
        """The top ``n`` explained recommendations (all of them when ``n`` is None)."""
        if n is None:
            return list(self.evaluations)
        return self.evaluations[:n]

    def report_lines(self) -> list[str]:
        """Human-readable ranked board (Markdown, ASCII only)."""
        lines = [
            "# Draft Oracle pick recommendation",
            "",
            f"- On the clock: {self.owner} (pick #{self.pick_index + 1})",
            f"- Rollouts per candidate: {self.rollouts}"
            + (f" | depth {self.depth}" if self.depth is not None else " | full depth"),
            f"- Candidates rolled out: {self.candidates_considered}",
            (
                "- Replacement level (points):"
                f" F {self.replacement['F']:.2f}"
                f" / D {self.replacement['D']:.2f}"
                f" / G {self.replacement['G']:.2f}"
            ),
            "",
            "| Rank | Pos | Player | Team | E[roster] | Proj | VOR | P(survive) | Need |",
            "| ---: | :-- | :----- | :--- | --------: | ---: | --: | ---------: | :--- |",
        ]
        for index, ev in enumerate(self.evaluations, start=1):
            need = f"{ev.open_slots}/{ev.position_limit}"
            lines.append(
                f"| {index} | {ev.asset.position} | {ev.asset.name} "
                f"| {ev.asset.team_abbrev} | {ev.expected_points:.2f} "
                f"| {ev.immediate_value:.2f} | {ev.vor:+.2f} | {ev.survival:.2f} "
                f"| {need} |"
            )
        return lines

    def manifest(self) -> dict[str, Any]:
        """JSON-serialisable summary of the recommendation run."""
        return {
            "owner": self.owner,
            "pick_index": self.pick_index,
            "rollouts": self.rollouts,
            "depth": self.depth,
            "seed": self.seed,
            "candidates_considered": self.candidates_considered,
            "replacement_level": dict(self.replacement),
            "recommendations": [
                {
                    "rank": index,
                    "asset": ev.asset.key,
                    "name": ev.asset.name,
                    "position": ev.asset.position,
                    "expected_points": round(ev.expected_points, 6),
                    "immediate_value": round(ev.immediate_value, 6),
                    "vor": round(ev.vor, 6),
                    "survival": round(ev.survival, 6),
                    "open_slots": ev.open_slots,
                    "position_limit": ev.position_limit,
                    "delta_vs_next": round(ev.delta_vs_next, 6),
                }
                for index, ev in enumerate(self.evaluations, start=1)
            ],
        }


def recommend_pick(
    state: DraftState,
    owner: str,
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    *,
    config: RecommendConfig | None = None,
    managers: int | None = None,
) -> Recommendation:
    """Recommend the owner's best pick by multi-step Monte-Carlo rollout.

    ``owner`` must be on the clock. Every legal candidate (pruned to the top
    ``config.max_candidates`` by VOR) is rolled out to the end of the draft against
    ``opponent_model``; the pick maximising expected final-roster projection wins.
    Each returned :class:`PickEvaluation` carries the reasoning the acceptance asks for
    (VOR, ``P(survives to next pick)``, expected delta vs. the #2 option, positional
    need). Deterministic given ``(state, config)``.
    """
    cfg = config or RecommendConfig()
    if state.is_complete:
        raise ValueError("draft is complete; nothing to recommend")
    if state.current_manager != owner:
        raise ValueError(
            f"owner {owner!r} is not on the clock (current: {state.current_manager!r})"
        )
    n_managers = managers if managers is not None else len(state.rosters)
    replacement = replacement_levels(state, n_managers)
    candidates = _prune_candidates(state, owner, replacement, cfg.max_candidates)
    if not candidates:
        raise ValueError(f"owner {owner!r} has no legal pick")

    roster = state.rosters[owner]
    expecteds = _expected_values(
        state, owner, [c.asset for c in candidates], opponent_model, replacement, cfg
    )
    ranked = sorted(
        zip(candidates, expecteds, strict=True),
        key=lambda pair: (-pair[1], -pair[0].vor, pair[0].asset.key),
    )
    second_best = ranked[1][1] if len(ranked) > 1 else ranked[0][1]

    evaluations: list[PickEvaluation] = []
    # Survival is a display-only explanation, so estimate it just for the surfaced
    # top-N rather than every rolled-out candidate (keeps the <10s budget).
    for candidate, expected in ranked[: cfg.top_n]:
        asset = candidate.asset
        survival = (
            survival_probability(
                state,
                asset,
                owner,
                opponent_model,
                rollouts=cfg.survival_rollouts,
                seed=cfg.seed,
            )
            if cfg.compute_survival
            else 0.0
        )
        limit = state.capacity.limit(asset.position)
        open_slots = limit - roster.count(asset.position)
        evaluations.append(
            PickEvaluation(
                asset=asset,
                expected_points=expected,
                immediate_value=asset_value(asset),
                vor=candidate.vor,
                replacement=candidate.replacement,
                survival=survival,
                open_slots=open_slots,
                position_limit=limit,
                delta_vs_next=expected - second_best,
            )
        )

    return Recommendation(
        owner=owner,
        pick_index=state.pick_index,
        rollouts=cfg.rollouts,
        depth=cfg.depth,
        replacement=replacement,
        evaluations=evaluations,
        candidates_considered=len(candidates),
        seed=cfg.seed,
    )


def build_pool_from_frames(
    skaters: pd.DataFrame, teams: pd.DataFrame, *, ir: bool = False
) -> list[DraftAsset]:
    """Build a draftable pool from the two in-memory projection tables.

    Skater rows become F/D assets priced by ``expected_points``; team rows become the
    whole-team goalie (``G``) asset priced by ``e_goalie_points``. ``rank_value`` (the
    opponents' public-perception signal) tracks the projection. Skater ``team_id`` is
    resolved from the teams table via ``team_abbrev`` so elimination and team affinity
    still work.

    When ``ir`` is set, injured skaters carrying an ``ir_stash_value`` (US-022) are
    repriced to that stash value, so the optimizer values an ``IR_F`` / ``IR_D`` stash
    for the retroactive-swap points it really adds, not for full-health production.
    """
    import pandas as pd

    from draft_oracle.optimize.ir_pool import reprice_pool_for_ir

    abbrev_to_id = {
        str(rec["team_abbrev"]): int(rec["team_id"]) for rec in teams.to_dict("records")
    }
    pool: list[DraftAsset] = []
    for rec in skaters.to_dict("records"):
        position = str(rec["position"])
        if position not in ("F", "D"):
            continue
        projection = float(rec["expected_points"])
        pool.append(
            DraftAsset(
                key=f"P{int(rec['player_id'])}",
                name=str(rec["player_name"]),
                position=position,  # type: ignore[arg-type]
                rank_value=projection,
                player_id=int(rec["player_id"]),
                team_id=abbrev_to_id.get(str(rec["team_abbrev"])),
                team_abbrev=str(rec["team_abbrev"]),
                projection=projection,
            )
        )
    for rec in teams.to_dict("records"):
        projection = float(rec["e_goalie_points"])
        pool.append(
            DraftAsset(
                key=f"T{int(rec['team_id'])}",
                name=str(rec["team_abbrev"]),
                position="G",
                rank_value=projection,
                team_id=int(rec["team_id"]),
                team_abbrev=str(rec["team_abbrev"]),
                projection=projection,
            )
        )
    if ir and "ir_stash_value" in skaters.columns:
        stash_value_by_player = {
            int(rec["player_id"]): float(rec["ir_stash_value"])
            for rec in skaters.to_dict("records")
            if pd.notna(rec.get("ir_stash_value"))
        }
        if stash_value_by_player:
            pool = reprice_pool_for_ir(pool, stash_value_by_player)
    return pool


def build_pool_from_projection_artifact(
    artifact_dir: Path, *, ir: bool = False
) -> list[DraftAsset]:
    """Build a draftable pool from a US-017 projection artifact directory.

    Thin disk wrapper over :func:`build_pool_from_frames`: reads ``skaters.parquet`` and
    ``teams.parquet`` from ``artifact_dir`` and delegates the asset construction.
    """
    import pandas as pd

    skaters = pd.read_parquet(artifact_dir / "skaters.parquet")
    teams = pd.read_parquet(artifact_dir / "teams.parquet")
    return build_pool_from_frames(skaters, teams, ir=ir)

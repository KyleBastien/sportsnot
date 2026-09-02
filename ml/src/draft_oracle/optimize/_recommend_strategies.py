"""Strategy comparison, synthetic draft pool, and the committed evaluation report.

The honest multi-step vs. greedy-VOR vs. one-step comparison (US-021 acceptance) plus
the deterministic synthetic pool it runs on. Split out of the public
:mod:`draft_oracle.optimize.recommend` surface to keep each module cohesive; the names
here are re-exported from ``recommend`` so the public import paths are unchanged.
"""

from __future__ import annotations

import json
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from draft_oracle.optimize._recommend_core import (
    RecommendConfig,
    _owner_roster_value,
    _resolve_model,
    greedy_vor_pick,
    replacement_levels,
)
from draft_oracle.optimize._recommend_kernels import choose_pick
from draft_oracle.optimize.opponents import (
    FittedLeagueOpponents,
    OpponentFitConfig,
    fit_opponent_models,
)
from draft_oracle.optimize.simulator import DraftAsset, DraftState, OpponentModel
from draft_oracle.provenance import add_git_provenance

# Committed comparison artifact (report + manifest re-included in .gitignore).
DEFAULT_RECOMMEND_ARTIFACT_DIR = Path("artifacts/models/recommend")

_Strategy = Literal["greedy_vor", "one_step", "multi_step"]

# Real NHL team ids the synthetic pool spreads assets across so the fitted opponent
# model's team-affinity signal has something to bite on.
_SYNTHETIC_TEAM_IDS: tuple[int, ...] = tuple(range(1, 33))


@dataclass(frozen=True)
class _PositionRunOpponent(OpponentModel):
    """Opponent that over-drafts one position, creating a run greedy-VOR can't see.

    Balanced fitted/greedy opponents deplete positions evenly, so a static VOR board
    is already optimal against them. Real drafts have runs — a stretch where everyone
    hammers one position — which push that position *below* its pool-wide replacement
    level before a greedy drafter reacts. This model reproduces that: it adds a large
    ``bonus`` to the favoured position, so a multi-step lookout (which simulates it)
    correctly grabs that position early while greedy-VOR waits and gets stuck with
    scraps. Used only in the comparison's stress scenario.
    """

    favored: str
    bonus: float = 12.0
    need_weight: float = 4.0
    temperature: float = 0.4

    def pick(self, state: DraftState, manager: str, rng: random.Random) -> DraftAsset:
        legal = state.legal_assets(manager)
        if not legal:
            raise ValueError(f"manager {manager!r} has no legal asset to draft")
        roster = state.rosters[manager]
        scores: list[float] = []
        for asset in legal:
            limit = state.capacity.limit(asset.position)
            urgency = (limit - roster.count(asset.position)) / limit if limit else 0.0
            bonus = self.bonus if asset.position == self.favored else 0.0
            scores.append(asset.rank_value + self.need_weight * urgency + bonus)
        if self.temperature <= 0.0:
            best = max(range(len(legal)), key=lambda i: (scores[i], legal[i].key))
            return legal[best]
        highest = max(scores)
        weights = [math.exp((s - highest) / self.temperature) for s in scores]
        threshold = rng.random() * sum(weights)
        cumulative = 0.0
        for index, weight in enumerate(weights):
            cumulative += weight
            if threshold <= cumulative:
                return legal[index]
        return legal[-1]


def build_synthetic_pool(
    managers: int,
    *,
    allow_ir: bool,
    seed: int = 20260827,
    contention: float = 1.15,
) -> list[DraftAsset]:
    """A deterministic, self-contained draft pool sized to contest a league.

    The pool holds ``contention`` times each position's league-wide demand so a
    position can plausibly run dry before a manager's next turn — the regime where a
    multi-step lookahead earns its keep. Projections decay linearly with rank plus a
    seeded jitter, and assets are spread across real NHL team ids so the fitted
    opponent model's affinity term is meaningful. ``rank_value`` tracks projection
    (public perception), so no strategy gets a hidden information edge.
    """
    rng = random.Random(seed)
    forwards_per = 6 if allow_ir else 5
    defense_per = 4 if allow_ir else 3
    demand = {
        "F": forwards_per * managers,
        "D": defense_per * managers,
        "G": managers,
    }
    base = {"F": 22.0, "D": 16.0, "G": 30.0}
    pool: list[DraftAsset] = []
    player_id = 1000
    for position in ("F", "D"):
        buffer = max(2, round(demand[position] * (contention - 1.0)))
        count = demand[position] + buffer
        for i in range(count):
            projection = base[position] - 0.15 * i + rng.uniform(-1.0, 1.0)
            projection = max(0.5, projection)
            team_id = _SYNTHETIC_TEAM_IDS[player_id % len(_SYNTHETIC_TEAM_IDS)]
            pool.append(
                DraftAsset(
                    key=f"P{player_id}",
                    name=f"{position}{i}",
                    position=position,
                    rank_value=projection,
                    player_id=player_id,
                    team_id=team_id,
                    team_abbrev=f"T{team_id}",
                    projection=projection,
                )
            )
            player_id += 1
    team_count = demand["G"] + max(2, round(demand["G"] * (contention - 1.0)))
    for i in range(team_count):
        projection = base["G"] - 0.9 * i + rng.uniform(-1.0, 1.0)
        projection = max(0.5, projection)
        team_id = _SYNTHETIC_TEAM_IDS[i % len(_SYNTHETIC_TEAM_IDS)]
        pool.append(
            DraftAsset(
                key=f"T{team_id}",
                name=f"G{team_id}",
                position="G",
                rank_value=projection,
                team_id=team_id,
                team_abbrev=f"T{team_id}",
                projection=projection,
            )
        )
    return pool


def _decision_pick(
    state: DraftState,
    owner: str,
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    strategy: _Strategy,
    replacement: Mapping[str, float],
    cfg: RecommendConfig,
    managers: int,
) -> DraftAsset:
    """The single pick ``strategy`` makes for the owner at the current slot."""
    if strategy == "greedy_vor":
        return greedy_vor_pick(state, owner, replacement)
    depth = 1 if strategy == "one_step" else None
    return choose_pick(
        state,
        owner,
        opponent_model,
        config=replace(cfg, depth=depth),
        managers=managers,
    )


def _continue_to_end(
    state: DraftState,
    owner: str,
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    replacement: Mapping[str, float],
    seed: int,
) -> float:
    """Finish the draft with a fixed greedy-VOR owner tail + opponents; owner value.

    The common continuation shared by all three strategies once they diverge at the
    decision slot, seeded identically so the tail is paired across strategies. Isolates
    the quality of the single decision under test.
    """
    rng = random.Random(seed)
    while not state.is_complete:
        current = state.current_manager
        if current == owner:
            state.apply_pick(greedy_vor_pick(state, owner, replacement))
        else:
            model = _resolve_model(opponent_model, current)
            state.apply_pick(model.pick(state, current, rng))
    return _owner_roster_value(state, owner)


def _play_to_decision(
    base_state: DraftState,
    owner: str,
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    replacement: Mapping[str, float],
    prefix: int,
    seed: int,
) -> DraftState | None:
    """Advance a fresh draft to the owner's ``prefix``-th pick (greedy tail + opponents).

    Returns the state with the owner on the clock at the decision slot, or ``None`` if
    the draft ends before the owner reaches that many picks (skip such drafts).
    """
    state = base_state.copy()
    rng = random.Random(seed)
    owner_made = 0
    while not state.is_complete:
        current = state.current_manager
        if current == owner:
            if owner_made == prefix:
                return state
            state.apply_pick(greedy_vor_pick(state, owner, replacement))
            owner_made += 1
        else:
            model = _resolve_model(opponent_model, current)
            state.apply_pick(model.pick(state, current, rng))
    return None


@dataclass
class StrategyComparison:
    """Average final owner-roster projection for each drafting strategy."""

    n_drafts: int
    owner: str
    managers: int
    allow_ir: bool
    rollouts: int
    max_candidates: int
    opponent_kind: str
    means: dict[str, float]
    seed: int = 20260827
    scenario: str = "balanced fitted opponents"
    tie_epsilon: float = 0.05

    @property
    def beats_greedy(self) -> bool:
        return self.means["multi_step"] > self.means["greedy_vor"]

    @property
    def beats_one_step(self) -> bool:
        return self.means["multi_step"] > self.means["one_step"]

    @property
    def ties_greedy(self) -> bool:
        return abs(self.means["multi_step"] - self.means["greedy_vor"]) <= self.tie_epsilon

    def report_lines(self) -> list[str]:
        """Honest Markdown comparison (SPEC section 7 — report misses, never hide)."""
        multi = self.means["multi_step"]
        greedy = self.means["greedy_vor"]
        one = self.means["one_step"]
        if self.ties_greedy:
            verdict = "matches greedy-VOR (statistical tie)"
        elif self.beats_greedy and self.beats_one_step:
            verdict = "beats both baselines"
        elif self.beats_greedy:
            verdict = "beats greedy only"
        elif self.beats_one_step:
            verdict = "beats one-step only"
        else:
            verdict = "does not beat the baselines"
        return [
            f"## Scenario: {self.scenario}",
            "",
            f"- Simulated drafts: {self.n_drafts} (seeded, {self.opponent_kind} opponents)",
            f"- League: {self.managers} managers, IR {'on' if self.allow_ir else 'off'}, "
            f"owner seat {self.owner}",
            f"- Rollouts per recommendation: {self.rollouts}, candidates: {self.max_candidates}",
            "",
            "| Strategy | Mean final roster projection | Delta vs. greedy |",
            "| :------- | ---------------------------: | ---------------: |",
            f"| Greedy-VOR (baseline a) | {greedy:.3f} | +0.000 |",
            f"| One-step lookahead (baseline b) | {one:.3f} | {one - greedy:+.3f} |",
            f"| Multi-step rollout | {multi:.3f} | {multi - greedy:+.3f} |",
            "",
            f"Multi-step vs. one-step: {multi - one:+.3f}. Verdict: multi-step {verdict}.",
        ]

    def manifest(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "n_drafts": self.n_drafts,
            "owner": self.owner,
            "managers": self.managers,
            "allow_ir": self.allow_ir,
            "rollouts": self.rollouts,
            "max_candidates": self.max_candidates,
            "opponent_kind": self.opponent_kind,
            "seed": self.seed,
            "means": {k: round(v, 6) for k, v in self.means.items()},
            "multi_step_beats_greedy": self.beats_greedy,
            "multi_step_beats_one_step": self.beats_one_step,
            "multi_step_ties_greedy": self.ties_greedy,
        }


def compare_strategies(
    pool: Sequence[DraftAsset],
    managers_list: Sequence[str],
    owner: str,
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    *,
    allow_ir: bool = False,
    config: RecommendConfig | None = None,
    n_drafts: int = 200,
    decision_prefix: int | None = None,
    seed: int = 20260827,
    opponent_kind: str = "greedy",
    scenario: str = "balanced fitted opponents",
) -> StrategyComparison:
    """Compare multi-step vs. greedy-VOR vs. one-step over ``n_drafts`` seeded drafts.

    Single-decision, same-slot framing (acceptance: "from the same slot"): each draft
    is advanced to the owner's ``decision_prefix``-th pick with a greedy tail against
    seeded opponents; from that *shared* state each strategy makes exactly one pick,
    and the draft is then finished with an identical greedy-VOR tail + opponents seeded
    the same way. The mean final owner-roster projection isolates the quality of that
    one decision. Honest by construction: one fixed config, every draft counted, no
    per-seed or per-slot cherry-picking (acceptance / SPEC section 7).
    """
    if n_drafts < 1:
        raise ValueError(f"n_drafts must be >= 1, got {n_drafts}")
    cfg = config or RecommendConfig(compute_survival=False)
    managers = len(managers_list)
    base = DraftState.new(managers_list, pool, allow_ir=allow_ir)
    replacement = replacement_levels(base, managers)
    prefix = decision_prefix if decision_prefix is not None else base.capacity.total // 3
    totals = {"greedy_vor": 0.0, "one_step": 0.0, "multi_step": 0.0}
    strategies: tuple[_Strategy, ...] = ("greedy_vor", "one_step", "multi_step")
    counted = 0
    for draft in range(n_drafts):
        draft_seed = seed + draft
        decision = _play_to_decision(base, owner, opponent_model, replacement, prefix, draft_seed)
        if decision is None:
            continue
        counted += 1
        for strategy in strategies:
            state = decision.copy()
            pick = _decision_pick(
                state, owner, opponent_model, strategy, replacement, cfg, managers
            )
            state.apply_pick(pick)
            totals[strategy] += _continue_to_end(
                state, owner, opponent_model, replacement, draft_seed
            )
    if counted == 0:
        raise ValueError("no draft reached the decision slot; lower decision_prefix")
    means = {k: v / counted for k, v in totals.items()}
    return StrategyComparison(
        n_drafts=counted,
        owner=owner,
        managers=managers,
        allow_ir=allow_ir,
        rollouts=cfg.rollouts,
        max_candidates=cfg.max_candidates,
        opponent_kind=opponent_kind,
        means=means,
        seed=seed,
        scenario=scenario,
    )


def _league_managers(fitted: FittedLeagueOpponents, limit: int) -> list[str]:
    ranked = sorted(fitted.manager_pick_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [manager for manager, _ in ranked[:limit]]


def evaluate_recommendation_strategies_from_normalized(
    *,
    normalized_dir: Path,
    artifact_dir: Path = DEFAULT_RECOMMEND_ARTIFACT_DIR,
    managers: int = 4,
    n_drafts: int = 200,
    rollouts: int = 40,
    max_candidates: int = 6,
    allow_ir: bool = False,
    opponent_temperature: float = 0.75,
    run_bonus: float = 12.0,
    seed: int = 20260827,
) -> StrategyComparison:
    """Fit league opponents, run both comparison scenarios, and commit report + manifest.

    Two honest scenarios over the deterministic synthetic pool:

    1. **Balanced fitted opponents** (the acceptance's primary case) — the US-020
       fitted league model (``league_draft_picks.parquet``) with a positive
       ``opponent_temperature`` so the seeded playouts differ. Fitted opponents draft
       positions evenly, so a static VOR board is already optimal and multi-step is
       expected to *tie* it (and edge one-step).
    2. **Positional-run opponents** (:class:`_PositionRunOpponent`) — opponents that
       hammer one position, pushing it below its pool-wide replacement level. This is
       where a static VOR board is blind and the multi-step lookahead, which simulates
       the run, should beat both baselines.

    Writes a combined ``report.md`` + ``manifest.json`` under ``artifact_dir``
    (re-included in .gitignore like the other model reports). Returns the primary
    (fitted-opponent) comparison. Deterministic given the inputs + seed.
    """
    import pandas as pd

    picks = pd.read_parquet(normalized_dir / "league_draft_picks.parquet")
    fitted = fit_opponent_models(picks, OpponentFitConfig(temperature=opponent_temperature))
    managers_list = _league_managers(fitted, managers)
    if len(managers_list) < 2:
        raise ValueError("need at least two league managers to run the comparison")
    owner = managers_list[0]
    pool = build_synthetic_pool(len(managers_list), allow_ir=allow_ir, seed=seed)
    cfg = RecommendConfig(
        rollouts=rollouts,
        max_candidates=max_candidates,
        compute_survival=False,
        seed=seed,
    )

    fitted_comparison = compare_strategies(
        pool,
        managers_list,
        owner,
        fitted.as_mapping(managers_list),
        allow_ir=allow_ir,
        config=cfg,
        n_drafts=n_drafts,
        seed=seed,
        opponent_kind="fitted-league",
        scenario="balanced fitted opponents",
    )
    run_opponent = _PositionRunOpponent(favored="F", bonus=run_bonus)
    run_comparison = compare_strategies(
        pool,
        managers_list,
        owner,
        run_opponent,
        allow_ir=allow_ir,
        config=cfg,
        n_drafts=n_drafts,
        seed=seed,
        opponent_kind="positional-run",
        scenario="positional-run opponents (forward run)",
    )

    lines = ["# Multi-step pick recommendation comparison", ""]
    lines += fitted_comparison.report_lines()
    lines += [""]
    lines += run_comparison.report_lines()
    manifest = add_git_provenance(
        {
            "balanced_fitted": fitted_comparison.manifest(),
            "positional_run": run_comparison.manifest(),
        }
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (artifact_dir / "manifest.json").write_text(
        json.dumps(
            manifest,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return fitted_comparison

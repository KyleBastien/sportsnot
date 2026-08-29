"""Opponent models fitted from real league draft history (US-020).

The fallback :class:`~draft_oracle.optimize.simulator.GreedyOpponentModel` assumes
every manager just takes the best publicly-ranked player. Real leagues do not draft
that way: managers over-draft their favourite NHL teams, reach for role players, and
weight positions idiosyncratically. This module fits an opponent policy to *this*
league's committed draft history so the simulator's survival estimates reflect how
these specific managers actually draft.

Sequence is (mostly) unobservable
---------------------------------
The owner has confirmed the hand-kept sheets record only **final rosters plus the
snake seat order** — not the pick-by-pick sequence. Only the 2026 in-app export
carries a true ``pick_number``. A model that conditions on the observed pick index
would therefore be un-fittable on the bulk of the data and would leak order that we
do not actually know.

We use the *documented simpler approximation* the acceptance criteria permit: a
**per-manager player-selection propensity conditioned on positional need**, expressed
as a conditional-logit (softmax) choice model. For each historical draft *event* and
each base position we take the set of assets that were drafted at that position across
the whole league as the observed candidate pool, and model each of a manager's picks
as an independent softmax draw over that pool (an order-free, with-replacement
approximation — see ``README.md``). The utility of an asset for a manager is

    U = beta_rank * rank_z + beta_affinity * team_affinity(manager, asset_team)

where

* ``rank_z`` is the standardized public-ranking signal within the pool
  (``points_when_drafted`` — a pre-draft cumulative total, so no outcome leakage; the
  sheet round-1 tabs carry no public ranking, so ``rank_z`` is zero there and the
  model leans on affinity), and
* ``team_affinity`` is the fraction of a manager's history spent drafting that NHL
  team — the own-team fandom signal. It is computed only from the *training* picks, so
  the held-out-season validation never sees the season it scores.

Positional need is applied *at draft time* (in :meth:`FittedOpponentModel.pick`) as the
fraction of a position's slots a manager still has open — a quantity that is fully
determined by roster state and never by an observed pick index. It governs which
*position* a manager reaches for; the fitted coefficients govern which *player* within
a position.

Sample-size blending
--------------------
A league-level model is always fit. A manager also gets their own coefficients when
they have enough historical picks; those are shrunk toward the league model by
``n / (n + k)`` and the league model is in turn shrunk toward the greedy
best-available fallback by ``N / (N + K)``. Thin data therefore degrades smoothly to
the league average and then to the fallback (SPEC section 8).

Everything implements the US-019 :class:`OpponentModel` interface, so a fitted model
drops straight into :func:`~draft_oracle.optimize.simulator.run_draft` and
:func:`~draft_oracle.optimize.simulator.survival_probability` with no changes, and the
simulator swaps policies via :func:`opponent_model_from_config`.
"""

from __future__ import annotations

import json
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from draft_oracle.optimize.simulator import (
    DraftAsset,
    DraftState,
    GreedyOpponentModel,
    OpponentModel,
    roster_capacity,
)
from draft_oracle.rules import snake_order

__all__ = [
    "DEFAULT_OPPONENT_ARTIFACT_DIR",
    "Coefficients",
    "FittedLeagueOpponents",
    "FittedOpponentModel",
    "MembershipScore",
    "OpponentEvalResult",
    "OpponentFitConfig",
    "OpponentModelResult",
    "PerPickScore",
    "base_position",
    "build_team_affinity",
    "dedupe_duplicate_events",
    "evaluate_opponents",
    "fit_opponent_models",
    "opponent_model_from_config",
    "train_opponent_model_from_normalized",
]

# ── Configuration ────────────────────────────────────────────────────────

DEFAULT_NORMALIZED_DIR = Path("data/normalized")
DEFAULT_OPPONENT_ARTIFACT_DIR = Path("artifacts/models/opponent")


@dataclass(frozen=True)
class OpponentFitConfig:
    """Hyper-parameters for fitting and evaluating the opponent model.

    ``fallback_rank`` is the greedy best-available strength on the standardized rank
    scale that a data-starved model shrinks toward (``beta_affinity`` shrinks toward
    ``0``). ``manager_blend_k`` / ``league_fallback_k`` are the shrinkage half-weights
    (a manager with that many picks is weighted 50/50 with the league; a league with
    that many picks is weighted 50/50 with the fallback). ``min_manager_picks`` is the
    floor below which a manager gets no own coefficients at all.
    """

    seed: int = 20260827
    temperature: float = 0.0
    need_weight: float = 1.0
    l2: float = 1.0
    manager_blend_k: float = 40.0
    league_fallback_k: float = 60.0
    min_manager_picks: int = 20
    fallback_rank: float = 1.5
    top_k: int = 3
    max_newton_iters: int = 50


# ── Small helpers ─────────────────────────────────────────────────────────

_BASE_BY_POSITION: dict[str, str] = {
    "F": "F",
    "IR_F": "F",
    "D": "D",
    "IR_D": "D",
    "G": "G",
}


def base_position(position: str) -> str | None:
    """Collapse a roster-slot label to a base draft position (``F``/``D``/``G``).

    IR slots fold into their active position; anything else (blank, unknown) returns
    ``None`` and is dropped from the choice model.
    """
    return _BASE_BY_POSITION.get(position.strip())


def _asset_key(player_id: int | None, team_id: int | None, position: str) -> str | None:
    """Stable pool identity: skaters by player, goalie/team slots by team."""
    if position == "G":
        return f"T{team_id}" if team_id is not None else None
    return f"P{player_id}" if player_id is not None else None


@dataclass(frozen=True)
class Coefficients:
    """Fitted utility weights for the conditional-logit choice model."""

    rank: float
    affinity: float

    def blend(self, other: Coefficients, weight: float) -> Coefficients:
        """Convex blend ``weight * self + (1 - weight) * other``."""
        w = _clamp01(weight)
        return Coefficients(
            rank=w * self.rank + (1.0 - w) * other.rank,
            affinity=w * self.affinity + (1.0 - w) * other.affinity,
        )

    def as_dict(self) -> dict[str, float]:
        return {"rank": round(self.rank, 6), "affinity": round(self.affinity, 6)}


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


# ── Team affinity (own-team fandom) ───────────────────────────────────────


def build_team_affinity(picks: pd.DataFrame) -> dict[str, dict[int, float]]:
    """``manager -> {team_id: fraction of that manager's picks on that team}``.

    Only rows with a resolved ``team_id`` count. The fraction is over a manager's
    team-bearing picks, so it is a proper probability the fandom feature reads
    directly. Managers with no team-bearing picks map to an empty table.
    """
    affinity: dict[str, dict[int, float]] = {}
    frame = picks.loc[picks["team_id"].notna(), ["manager", "team_id"]]
    for manager, group in frame.groupby("manager"):
        counts = group["team_id"].astype(int).value_counts()
        total = float(counts.sum())
        if total <= 0:
            affinity[str(manager)] = {}
            continue
        affinity[str(manager)] = {int(str(team)): int(n) / total for team, n in counts.items()}
    return affinity


def _affinity_for(
    affinity: Mapping[str, Mapping[int, float]], manager: str, team_id: int | None
) -> float:
    if team_id is None:
        return 0.0
    return float(affinity.get(manager, {}).get(int(team_id), 0.0))


# ── Choice-set construction ───────────────────────────────────────────────


@dataclass(frozen=True)
class _Choice:
    """One observed selection: feature rows for the pool plus the chosen index."""

    features: Any  # np.ndarray [n_options, 2]
    chosen: int


# Prefer the authoritative in-app export over the hand-kept sheet copy when the same
# real draft is recorded under two ``source`` values.
_SOURCE_PRIORITY: dict[str, int] = {"app": 0, "sheet": 1}


def _event_keys(frame: pd.DataFrame) -> list[str]:
    """Grouping keys that isolate one real draft event, league-aware when possible.

    Real data carries ``league_name`` so two leagues drafting in the same season/round
    (2026 Gemmell Cup vs Press Play-offs) never pool their assets into one choice set.
    Synthetic fixtures without the column fall back to ``(season, draft_event)``.
    """
    keys = ["season"]
    if "league_name" in frame.columns:
        keys.append("league_name")
    keys.append("draft_event")
    return keys


def dedupe_duplicate_events(picks: pd.DataFrame) -> pd.DataFrame:
    """Drop duplicated copies of the same real draft, preferring ``source='app'``.

    A single physical draft can appear twice: an authoritative in-app export
    (``source='app'``) and a hand-maintained spreadsheet copy (``source='sheet'``). The
    2026 Gemmell Cup is recorded both ways (32/32 identical round-1 player ids), so
    fitting on the raw table double-counts every Gemmell pick. Keep exactly one copy per
    ``(season, league_name, draft_event)``, preferring ``app`` over ``sheet``. Frames
    lacking ``source``/``league_name`` (synthetic fixtures) are returned unchanged.
    """
    if "source" not in picks.columns or "league_name" not in picks.columns:
        return picks
    frame = picks.copy()
    frame["_source_priority"] = frame["source"].map(
        lambda s: _SOURCE_PRIORITY.get(str(s), len(_SOURCE_PRIORITY))
    )
    keys = ["season", "league_name", "draft_event"]
    best = frame.groupby(keys)["_source_priority"].transform("min")
    kept = frame.loc[frame["_source_priority"] == best].drop(columns="_source_priority")
    return kept.reset_index(drop=True)


def _prepare_picks(picks: pd.DataFrame) -> pd.DataFrame:
    """Attach base position + asset key and drop rows we cannot model.

    Deduplicates same-draft ``app``/``sheet`` copies first so no downstream count,
    choice pool, or validation event double-counts a duplicated draft.
    """
    frame = dedupe_duplicate_events(picks).copy()
    frame["base_position"] = frame["position"].map(lambda p: base_position(str(p)))
    keys: list[str | None] = []
    for _, row in frame.iterrows():
        pid = int(row["player_id"]) if pd.notna(row["player_id"]) else None
        tid = int(row["team_id"]) if pd.notna(row["team_id"]) else None
        keys.append(_asset_key(pid, tid, str(row["base_position"])))
    frame["asset_key"] = keys
    return frame.loc[frame["base_position"].notna() & frame["asset_key"].notna()].reset_index(
        drop=True
    )


def _pool_rank_z(pool: pd.DataFrame) -> dict[str, float]:
    """Standardized public-ranking signal per asset key within a position pool."""
    ranks = pool["points_when_drafted"].astype("float64")
    values = ranks.to_numpy(dtype="float64", na_value=np.nan)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return dict.fromkeys(pool["asset_key"].astype(str), 0.0)
    mean = float(finite.mean())
    std = float(finite.std())
    z: dict[str, float] = {}
    for key, raw in zip(pool["asset_key"].astype(str), values, strict=True):
        if not np.isfinite(raw) or std <= 0.0:
            z[str(key)] = 0.0
        else:
            z[str(key)] = (float(raw) - mean) / std
    return z


def _build_choices(
    picks: pd.DataFrame,
    affinity: Mapping[str, Mapping[int, float]],
    *,
    managers: frozenset[str] | None = None,
) -> list[_Choice]:
    """Build conditional-logit choices from the observed per-event position pools.

    A pool is one ``(season, event, base_position)`` group's unique assets. Each of a
    manager's picks in that pool contributes one choice over the whole pool's feature
    rows (order-free, with-replacement approximation).
    """
    choices: list[_Choice] = []
    grouped = picks.groupby([*_event_keys(picks), "base_position"], sort=True)
    for _, pool in grouped:
        unique = pool.drop_duplicates(subset="asset_key")
        if len(unique) < 2:
            continue
        rank_z = _pool_rank_z(unique)
        keys = list(unique["asset_key"].astype(str))
        team_ids = [
            int(t) if pd.notna(t) else None for t in unique["team_id"].to_numpy(dtype=object)
        ]
        index_of = {key: i for i, key in enumerate(keys)}
        base = np.array([[rank_z[key], 0.0] for key in keys], dtype="float64")
        for _, pick in pool.iterrows():
            manager = str(pick["manager"])
            if managers is not None and manager not in managers:
                continue
            chosen = index_of.get(str(pick["asset_key"]))
            if chosen is None:
                continue
            features = base.copy()
            features[:, 1] = [_affinity_for(affinity, manager, tid) for tid in team_ids]
            choices.append(_Choice(features=features, chosen=chosen))
    return choices


# ── Conditional-logit fit ─────────────────────────────────────────────────


def _softmax(scores: Any) -> Any:
    shifted = scores - scores.max()
    weights = np.exp(shifted)
    return weights / weights.sum()


def _fit_logit(choices: Sequence[_Choice], *, l2: float, max_iters: int) -> Coefficients:
    """L2-regularized conditional-logit fit by Newton-Raphson on two coefficients.

    Returns zero coefficients when there is nothing to fit; falls back to a damped
    gradient step if the Hessian is singular. Tiny problem (two parameters, a few
    hundred choices) so it converges in a handful of iterations.
    """
    if not choices:
        return Coefficients(rank=0.0, affinity=0.0)
    beta = np.zeros(2, dtype="float64")
    for _ in range(max_iters):
        grad = -l2 * beta
        hess = -l2 * np.eye(2, dtype="float64")
        for choice in choices:
            x = choice.features
            probs = _softmax(x @ beta)
            xbar = x.T @ probs
            grad = grad + x[choice.chosen] - xbar
            hess = hess - ((x.T * probs) @ x - np.outer(xbar, xbar))
        try:
            step = np.linalg.solve(hess, grad)
        except np.linalg.LinAlgError:
            step = -0.1 * grad
        beta = beta - step
        if float(np.abs(step).max()) < 1e-8:
            break
    return Coefficients(rank=float(beta[0]), affinity=float(beta[1]))


# ── Fitted models ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FittedOpponentModel(OpponentModel):
    """A per-manager fitted draft policy implementing the US-019 interface.

    Scores each legal asset by ``rank`` (standardized within the manager's legal
    assets at that base position), team ``affinity``, and positional ``need`` (open
    slots / limit), then softmax-samples with ``temperature`` (``0`` = deterministic
    argmax with the same tie-break as the greedy fallback).
    """

    coefficients: Coefficients
    affinity: Mapping[int, float]
    need_weight: float = 1.0
    temperature: float = 0.0

    def _utilities(
        self, state: DraftState, manager: str, legal: Sequence[DraftAsset]
    ) -> list[float]:
        roster = state.rosters[manager]
        rank_z = _legal_rank_z(legal)
        utilities: list[float] = []
        for asset in legal:
            limit = state.capacity.limit(asset.position)
            urgency = (limit - roster.count(asset.position)) / limit if limit else 0.0
            affinity = float(self.affinity.get(int(asset.team_id), 0.0)) if asset.team_id else 0.0
            utilities.append(
                self.coefficients.rank * rank_z[asset.key]
                + self.coefficients.affinity * affinity
                + self.need_weight * urgency
            )
        return utilities

    def rank_assets(self, state: DraftState, manager: str) -> list[DraftAsset]:
        """Legal assets ordered best-first by fitted utility (deterministic)."""
        legal = state.legal_assets(manager)
        if not legal:
            return []
        scored = list(zip(legal, self._utilities(state, manager, legal), strict=True))
        scored.sort(key=lambda pair: (-pair[1], -pair[0].rank_value, pair[0].key))
        return [asset for asset, _ in scored]

    def pick(self, state: DraftState, manager: str, rng: random.Random) -> DraftAsset:
        legal = state.legal_assets(manager)
        if not legal:
            raise ValueError(f"manager {manager!r} has no legal asset to draft")
        utilities = self._utilities(state, manager, legal)
        index = _choose(legal, utilities, rng, self.temperature)
        return legal[index]


def _legal_rank_z(legal: Sequence[DraftAsset]) -> dict[str, float]:
    """Standardize ``rank_value`` within each base position of the legal set."""
    by_position: dict[str, list[DraftAsset]] = {}
    for asset in legal:
        by_position.setdefault(asset.position, []).append(asset)
    z: dict[str, float] = {}
    for group in by_position.values():
        values = np.array([asset.rank_value for asset in group], dtype="float64")
        mean = float(values.mean())
        std = float(values.std())
        for asset, value in zip(group, values, strict=True):
            z[asset.key] = 0.0 if std <= 0.0 else (float(value) - mean) / std
    return z


def _choose(
    assets: Sequence[DraftAsset],
    scores: Sequence[float],
    rng: random.Random,
    temperature: float,
) -> int:
    if temperature <= 0.0:
        best = 0
        for index in range(1, len(scores)):
            if _is_better(assets[index], scores[index], assets[best], scores[best]):
                best = index
        return best
    highest = max(scores)
    weights = [math.exp((score - highest) / temperature) for score in scores]
    total = sum(weights)
    threshold = rng.random() * total
    cumulative = 0.0
    for index, weight in enumerate(weights):
        cumulative += weight
        if threshold <= cumulative:
            return index
    return len(weights) - 1


def _is_better(asset: DraftAsset, score: float, best_asset: DraftAsset, best_score: float) -> bool:
    if score != best_score:
        return score > best_score
    if asset.rank_value != best_asset.rank_value:
        return asset.rank_value > best_asset.rank_value
    return asset.key < best_asset.key


@dataclass
class FittedLeagueOpponents:
    """A fitted league model plus optional per-manager overrides.

    :meth:`model_for` returns the blended :class:`FittedOpponentModel` for a manager;
    :meth:`as_mapping` produces the per-manager ``dict`` the simulator consumes.
    """

    league: Coefficients
    per_manager: dict[str, Coefficients]
    affinity: dict[str, dict[int, float]]
    manager_pick_counts: dict[str, int]
    total_picks: int
    config: OpponentFitConfig

    def model_for(self, manager: str) -> FittedOpponentModel:
        coefficients = self.per_manager.get(manager, self.league)
        return FittedOpponentModel(
            coefficients=coefficients,
            affinity=self.affinity.get(manager, {}),
            need_weight=self.config.need_weight,
            temperature=self.config.temperature,
        )

    def as_mapping(self, managers: Sequence[str]) -> dict[str, OpponentModel]:
        return {manager: self.model_for(manager) for manager in managers}

    def manifest(self) -> dict[str, Any]:
        return {
            "league_coefficients": self.league.as_dict(),
            "total_picks": self.total_picks,
            "per_manager": {
                manager: {
                    "picks": self.manager_pick_counts.get(manager, 0),
                    "coefficients": coefficients.as_dict(),
                }
                for manager, coefficients in sorted(self.per_manager.items())
            },
        }

    def report_lines(self) -> list[str]:
        lines = [
            "## Fitted opponent model",
            "",
            f"- total historical picks: {self.total_picks}",
            f"- league coefficients: rank {self.league.rank:+.3f}, "
            f"affinity {self.league.affinity:+.3f}",
            f"- per-manager models: {len(self.per_manager)} "
            f"(min picks {self.config.min_manager_picks})",
            "",
            "| manager | picks | rank beta | affinity beta |",
            "| --- | ---: | ---: | ---: |",
        ]
        for manager in sorted(self.per_manager):
            coef = self.per_manager[manager]
            picks = self.manager_pick_counts.get(manager, 0)
            lines.append(f"| {manager} | {picks} | {coef.rank:+.3f} | {coef.affinity:+.3f} |")
        return lines


def fit_opponent_models(
    picks: pd.DataFrame, config: OpponentFitConfig | None = None
) -> FittedLeagueOpponents:
    """Fit the league model and sample-size-blended per-manager models.

    ``picks`` is the entity-matched ``league_draft_picks`` table (or any subset — the
    validation refits on a leave-one-season-out slice). Managers below
    ``min_manager_picks`` get the league model directly.
    """
    cfg = config or OpponentFitConfig()
    prepared = _prepare_picks(picks)
    affinity = build_team_affinity(prepared)
    fallback = Coefficients(rank=cfg.fallback_rank, affinity=0.0)

    league_choices = _build_choices(prepared, affinity)
    league_raw = _fit_logit(league_choices, l2=cfg.l2, max_iters=cfg.max_newton_iters)
    total = len(league_choices)
    league_weight = total / (total + cfg.league_fallback_k) if total else 0.0
    league = league_raw.blend(fallback, league_weight)

    counts = {str(manager): int(n) for manager, n in prepared.groupby("manager").size().items()}
    per_manager: dict[str, Coefficients] = {}
    for manager, n in counts.items():
        if n < cfg.min_manager_picks:
            continue
        manager_choices = _build_choices(prepared, affinity, managers=frozenset({manager}))
        raw = _fit_logit(manager_choices, l2=cfg.l2, max_iters=cfg.max_newton_iters)
        weight = n / (n + cfg.manager_blend_k)
        per_manager[manager] = raw.blend(league, weight)

    return FittedLeagueOpponents(
        league=league,
        per_manager=per_manager,
        affinity=affinity,
        manager_pick_counts=counts,
        total_picks=total,
        config=cfg,
    )


# ── Config-driven model swap ──────────────────────────────────────────────


def opponent_model_from_config(
    kind: str,
    *,
    manager: str | None = None,
    fitted: FittedLeagueOpponents | None = None,
    need_weight: float = 1.0,
    temperature: float = 0.0,
) -> OpponentModel:
    """Return the opponent policy named by ``kind`` (``"greedy"`` or ``"fitted"``).

    Lets the simulator swap policies from a single config string. ``"fitted"`` needs a
    ``fitted`` result and (for a manager-specific model) a ``manager`` id.
    """
    if kind == "greedy":
        return GreedyOpponentModel(temperature=temperature, need_weight=need_weight)
    if kind == "fitted":
        if fitted is None:
            raise ValueError("kind='fitted' requires a FittedLeagueOpponents instance")
        return fitted.model_for(manager) if manager is not None else fitted.model_for("")
    raise ValueError(f"unknown opponent model kind: {kind!r}")


# ── Held-out validation ───────────────────────────────────────────────────


def _event_assets(pool: pd.DataFrame) -> list[DraftAsset]:
    """Build the drafted-asset pool for one event (deduplicated by asset key)."""
    assets: list[DraftAsset] = []
    seen: set[str] = set()
    for _, row in pool.drop_duplicates(subset="asset_key").iterrows():
        key = str(row["asset_key"])
        if key in seen:
            continue
        seen.add(key)
        pid = int(row["player_id"]) if pd.notna(row["player_id"]) else None
        tid = int(row["team_id"]) if pd.notna(row["team_id"]) else None
        rank = float(row["points_when_drafted"]) if pd.notna(row["points_when_drafted"]) else 0.0
        name = (
            str(row["matched_name"])
            if pd.notna(row["matched_name"])
            else str(row["player_or_team_name"])
        )
        assets.append(
            DraftAsset(
                key=key,
                name=name,
                position=str(row["base_position"]),  # type: ignore[arg-type]  # F/D/G
                rank_value=rank,
                player_id=pid,
                team_id=tid,
            )
        )
    return assets


def _event_order(pool: pd.DataFrame) -> list[str] | None:
    """Round-1 manager order from ``snake_slot`` (returns ``None`` if incomplete)."""
    slots: dict[str, int] = {}
    for _, row in pool.iterrows():
        if pd.isna(row["snake_slot"]):
            return None
        slots[str(row["manager"])] = int(row["snake_slot"])
    if not slots:
        return None
    return [manager for manager, _ in sorted(slots.items(), key=lambda kv: kv[1])]


def _actual_rosters(pool: pd.DataFrame) -> dict[str, set[str]]:
    rosters: dict[str, set[str]] = {}
    for _, row in pool.iterrows():
        rosters.setdefault(str(row["manager"]), set()).add(str(row["asset_key"]))
    return rosters


def _simulate_membership(
    pool: pd.DataFrame,
    models: Mapping[str, OpponentModel],
    seed: int,
) -> dict[str, set[str]] | None:
    """Replay one event's snake order with ``models`` and return predicted rosters.

    Respects each manager's *actual* pick count so the pool and roster shape match the
    real event; returns ``None`` when the seat order is unrecoverable.
    """
    order = _event_order(pool)
    if order is None:
        return None
    assets = _event_assets(pool)
    actual = _actual_rosters(pool)
    remaining = {manager: len(actual.get(manager, set())) for manager in order}
    allow_ir = bool((pool["position"].isin(["IR_F", "IR_D"])).any())
    capacity = roster_capacity(allow_ir)
    state = DraftState.new(order, assets, allow_ir=allow_ir)
    sequence = snake_order(order, capacity.total)
    rng = random.Random(seed)
    predicted: dict[str, set[str]] = {manager: set() for manager in order}
    for manager in sequence:
        if remaining.get(manager, 0) <= 0:
            continue
        if not state.legal_assets(manager):
            remaining[manager] = 0
            continue
        model = models.get(manager)
        if model is None:
            continue
        asset = model.pick(state, manager, rng)
        state.place(manager, asset)
        predicted[manager].add(asset.key)
        remaining[manager] -= 1
    return predicted


def _membership_accuracy(
    predicted: Mapping[str, set[str]], actual: Mapping[str, set[str]]
) -> tuple[float, int]:
    hits = 0
    total = 0
    for manager, actual_keys in actual.items():
        if not actual_keys:
            continue
        predicted_keys = predicted.get(manager, set())
        hits += len(predicted_keys & actual_keys)
        total += len(actual_keys)
    if total == 0:
        return 0.0, 0
    return hits / total, total


@dataclass(frozen=True)
class MembershipScore:
    """Per-season roster-membership accuracy: fitted vs greedy fallback."""

    season: int
    events: int
    picks: int
    fitted_accuracy: float
    greedy_accuracy: float

    @property
    def fitted_beats_greedy(self) -> bool:
        return self.fitted_accuracy > self.greedy_accuracy


@dataclass(frozen=True)
class PerPickScore:
    """Per-pick top-1 / top-K accuracy on the true-order (app) events."""

    picks: int
    fitted_top1: float
    greedy_top1: float
    fitted_topk: float
    greedy_topk: float
    k: int


def _membership_for_season(
    picks: pd.DataFrame,
    season: int,
    config: OpponentFitConfig,
) -> MembershipScore | None:
    """Leave-one-season-out membership accuracy for ``season``."""
    train = picks.loc[picks["season"] != season]
    if train.empty:
        return None
    fitted = fit_opponent_models(train, config)
    prepared = _prepare_picks(picks.loc[picks["season"] == season])
    greedy = GreedyOpponentModel(temperature=0.0, need_weight=config.need_weight)

    events = 0
    picks_scored = 0
    fitted_hits = 0.0
    greedy_hits = 0.0
    fitted_total = 0
    greedy_total = 0
    for _, pool in prepared.groupby(_event_keys(prepared), sort=True):
        managers = [str(m) for m in pool["manager"].unique()]
        actual = _actual_rosters(pool)
        fitted_models = fitted.as_mapping(managers)
        greedy_models: dict[str, OpponentModel] = dict.fromkeys(managers, greedy)
        fitted_pred = _simulate_membership(pool, fitted_models, config.seed)
        greedy_pred = _simulate_membership(pool, greedy_models, config.seed)
        if fitted_pred is None or greedy_pred is None:
            continue
        f_acc, f_total = _membership_accuracy(fitted_pred, actual)
        g_acc, g_total = _membership_accuracy(greedy_pred, actual)
        if f_total == 0:
            continue
        events += 1
        picks_scored += f_total
        fitted_hits += f_acc * f_total
        greedy_hits += g_acc * g_total
        fitted_total += f_total
        greedy_total += g_total
    if events == 0 or fitted_total == 0:
        return None
    return MembershipScore(
        season=season,
        events=events,
        picks=picks_scored,
        fitted_accuracy=fitted_hits / fitted_total,
        greedy_accuracy=greedy_hits / greedy_total,
    )


def _per_pick_accuracy(
    picks: pd.DataFrame,
    config: OpponentFitConfig,
) -> PerPickScore | None:
    """Teacher-forced per-pick top-1/top-K accuracy on events with a true pick order.

    Fits on the seasons *without* observed order (leaving the true-order season fully
    held out), then replays each true-order event pick by pick.
    """
    ordered = picks.loc[picks["pick_number"].notna()]
    if ordered.empty:
        return None
    ordered_seasons = {int(s) for s in ordered["season"].unique()}
    train = picks.loc[~picks["season"].isin(ordered_seasons)]
    if train.empty:
        return None
    fitted = fit_opponent_models(train, config)
    greedy = GreedyOpponentModel(temperature=0.0, need_weight=config.need_weight)

    total = 0
    fitted_top1 = 0
    greedy_top1 = 0
    fitted_topk = 0
    greedy_topk = 0
    prepared = _prepare_picks(ordered)
    for _, pool in prepared.groupby(_event_keys(prepared), sort=True):
        order = _event_order(pool)
        if order is None:
            continue
        assets = _event_assets(pool)
        allow_ir = bool((pool["position"].isin(["IR_F", "IR_D"])).any())
        state = DraftState.new(order, assets, allow_ir=allow_ir)
        fitted_models = fitted.as_mapping(order)
        sequence = pool.sort_values("pick_number")
        rng = random.Random(config.seed)
        for _, pick in sequence.iterrows():
            manager = str(pick["manager"])
            key = str(pick["asset_key"])
            if key not in state.available:
                continue
            asset = state.available[key]
            if not state.has_capacity(manager, asset.position):
                continue
            legal = state.legal_assets(manager)
            if not any(a.key == key for a in legal):
                continue
            fitted_rank = _rank_keys(fitted_models[manager], state, manager)
            greedy_rank = _rank_keys(greedy, state, manager, rng)
            if fitted_rank and fitted_rank[0] == key:
                fitted_top1 += 1
            if greedy_rank and greedy_rank[0] == key:
                greedy_top1 += 1
            if key in fitted_rank[: config.top_k]:
                fitted_topk += 1
            if key in greedy_rank[: config.top_k]:
                greedy_topk += 1
            total += 1
            state.place(manager, asset)
    if total == 0:
        return None
    return PerPickScore(
        picks=total,
        fitted_top1=fitted_top1 / total,
        greedy_top1=greedy_top1 / total,
        fitted_topk=fitted_topk / total,
        greedy_topk=greedy_topk / total,
        k=config.top_k,
    )


def _rank_keys(
    model: OpponentModel,
    state: DraftState,
    manager: str,
    rng: random.Random | None = None,
) -> list[str]:
    """Best-first asset keys a model would consider for ``manager`` right now."""
    if isinstance(model, FittedOpponentModel):
        return [asset.key for asset in model.rank_assets(state, manager)]
    legal = state.legal_assets(manager)
    if not legal:
        return []
    # Greedy fallback ranks by its own utility; reuse a deterministic argmax sweep.
    roster = state.rosters[manager]
    scored: list[tuple[float, DraftAsset]] = []
    for asset in legal:
        limit = state.capacity.limit(asset.position)
        urgency = (limit - roster.count(asset.position)) / limit if limit else 0.0
        scored.append((asset.rank_value + DEFAULT_GREEDY_NEED * urgency, asset))
    scored.sort(key=lambda pair: (-pair[0], -pair[1].rank_value, pair[1].key))
    return [asset.key for _, asset in scored]


DEFAULT_GREEDY_NEED = 4.0


@dataclass
class OpponentEvalResult:
    """Held-out validation: per-season membership + optional per-pick accuracy."""

    membership: list[MembershipScore]
    per_pick: PerPickScore | None

    @property
    def seasons_beating_fallback(self) -> int:
        return sum(1 for score in self.membership if score.fitted_beats_greedy)

    def manifest(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "membership": [
                {
                    "season": score.season,
                    "events": score.events,
                    "picks": score.picks,
                    "fitted_accuracy": round(score.fitted_accuracy, 4),
                    "greedy_accuracy": round(score.greedy_accuracy, 4),
                    "fitted_beats_greedy": score.fitted_beats_greedy,
                }
                for score in self.membership
            ],
            "seasons_beating_fallback": self.seasons_beating_fallback,
        }
        if self.per_pick is not None:
            data["per_pick"] = {
                "picks": self.per_pick.picks,
                "k": self.per_pick.k,
                "fitted_top1": round(self.per_pick.fitted_top1, 4),
                "greedy_top1": round(self.per_pick.greedy_top1, 4),
                "fitted_topk": round(self.per_pick.fitted_topk, 4),
                "greedy_topk": round(self.per_pick.greedy_topk, 4),
            }
        return data

    def report_lines(self) -> list[str]:
        lines = [
            "## Held-out validation",
            "",
            "Roster-membership accuracy (leave-one-season-out): the fraction of each "
            "manager's actual roster the model reproduces given the true snake order "
            "and drafted pool. Compared against the greedy best-available fallback.",
            "",
            "| season | events | picks | fitted | greedy | fitted wins |",
            "| --- | ---: | ---: | ---: | ---: | :---: |",
        ]
        for score in self.membership:
            lines.append(
                f"| {score.season} | {score.events} | {score.picks} | "
                f"{score.fitted_accuracy:.3f} | {score.greedy_accuracy:.3f} | "
                f"{'yes' if score.fitted_beats_greedy else 'no'} |"
            )
        lines.append("")
        lines.append(
            f"Seasons where fitted beats the fallback: "
            f"{self.seasons_beating_fallback}/{len(self.membership)}."
        )
        if self.per_pick is not None:
            pp = self.per_pick
            lines.extend(
                [
                    "",
                    "### Per-pick accuracy (true-order app export)",
                    "",
                    f"- picks scored: {pp.picks}",
                    f"- top-1: fitted {pp.fitted_top1:.3f} vs greedy {pp.greedy_top1:.3f}",
                    f"- top-{pp.k}: fitted {pp.fitted_topk:.3f} vs greedy {pp.greedy_topk:.3f}",
                ]
            )
        return lines


def evaluate_opponents(
    picks: pd.DataFrame, config: OpponentFitConfig | None = None
) -> OpponentEvalResult:
    """Run leave-one-season-out membership + true-order per-pick validation."""
    cfg = config or OpponentFitConfig()
    prepared = _prepare_picks(picks)
    seasons = sorted(int(s) for s in prepared["season"].unique())
    membership: list[MembershipScore] = []
    for season in seasons:
        score = _membership_for_season(picks, season, cfg)
        if score is not None:
            membership.append(score)
    per_pick = _per_pick_accuracy(picks, cfg)
    return OpponentEvalResult(membership=membership, per_pick=per_pick)


# ── Artifact driver ────────────────────────────────────────────────────────


@dataclass
class OpponentModelResult:
    """Bundled fit + evaluation for the committed artifact."""

    fitted: FittedLeagueOpponents
    evaluation: OpponentEvalResult

    def manifest(self) -> dict[str, Any]:
        return {
            "model": self.fitted.manifest(),
            "config": {
                "seed": self.fitted.config.seed,
                "need_weight": self.fitted.config.need_weight,
                "l2": self.fitted.config.l2,
                "manager_blend_k": self.fitted.config.manager_blend_k,
                "league_fallback_k": self.fitted.config.league_fallback_k,
                "min_manager_picks": self.fitted.config.min_manager_picks,
                "fallback_rank": self.fitted.config.fallback_rank,
                "top_k": self.fitted.config.top_k,
            },
            "evaluation": self.evaluation.manifest(),
        }

    def report_lines(self) -> list[str]:
        lines = ["# Opponent model (US-020)", ""]
        lines.extend(self.fitted.report_lines())
        lines.append("")
        lines.extend(self.evaluation.report_lines())
        return lines


def train_opponent_model_from_normalized(
    *,
    normalized_dir: Path = DEFAULT_NORMALIZED_DIR,
    artifact_dir: Path = DEFAULT_OPPONENT_ARTIFACT_DIR,
    config: OpponentFitConfig | None = None,
) -> OpponentModelResult:
    """Load ``league_draft_picks.parquet``, fit + validate, write report + manifest."""
    cfg = config or OpponentFitConfig()
    picks = pd.read_parquet(normalized_dir / "league_draft_picks.parquet")
    fitted = fit_opponent_models(picks, cfg)
    evaluation = evaluate_opponents(picks, cfg)
    result = OpponentModelResult(fitted=fitted, evaluation=evaluation)

    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "report.md").write_text(
        "\n".join(result.report_lines()) + "\n", encoding="utf-8"
    )
    (artifact_dir / "manifest.json").write_text(
        json.dumps(result.manifest(), indent=2) + "\n", encoding="utf-8"
    )
    return result

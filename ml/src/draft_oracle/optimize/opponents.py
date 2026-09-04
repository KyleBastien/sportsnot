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
from typing import Any, TypedDict, Unpack, cast

import numpy as np
import pandas as pd

from draft_oracle.optimize._opponent_choice_sets import (
    _build_choices as _build_choices_impl,
)
from draft_oracle.optimize._opponent_choice_sets import (
    _Choice,
    base_position,
    build_team_affinity,
    dedupe_duplicate_events,
    event_keys,
)
from draft_oracle.optimize._opponent_choice_sets import (
    _fit_logit as _fit_logit_raw,
)
from draft_oracle.optimize._opponent_choice_sets import (
    _prepare_picks as _prepare_picks_impl,
)
from draft_oracle.optimize._opponent_eval import (
    MembershipExclusion,
    MembershipScore,
    OpponentEvalResult,
    PerPickScore,
    _membership_exclusions,
)
from draft_oracle.optimize._opponent_eval import (
    _membership_for_season as _eval_membership_for_season,
)
from draft_oracle.optimize._opponent_eval import (
    _per_pick_accuracy as _eval_per_pick_accuracy,
)
from draft_oracle.optimize.simulator import (
    DraftAsset,
    DraftState,
    GreedyOpponentModel,
    OpponentModel,
)
from draft_oracle.provenance import add_git_provenance

__all__ = [
    "DEFAULT_OPPONENT_ARTIFACT_DIR",
    "Coefficients",
    "FittedLeagueOpponents",
    "FittedOpponentModel",
    "MembershipExclusion",
    "MembershipScore",
    "OpponentEvalResult",
    "OpponentFitConfig",
    "OpponentModelResult",
    "PerPickScore",
    "base_position",
    "build_team_affinity",
    "dedupe_duplicate_events",
    "evaluate_opponents",
    "event_keys",
    "fit_opponent_models",
    "load_committed_opponents",
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

    @classmethod
    def from_manifest_entry(cls, data: Mapping[str, Any]) -> Coefficients:
        return cls(rank=float(data["rank"]), affinity=float(data["affinity"]))


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


# Private compatibility name retained for opponent-model internals and mutation guards.
_event_keys = event_keys


def _prepare_picks(picks: pd.DataFrame) -> pd.DataFrame:
    return _prepare_picks_impl(picks)


def _build_choices(
    picks: pd.DataFrame,
    affinity: Mapping[str, Mapping[int, float]],
    *,
    managers: frozenset[str] | None = None,
) -> list[_Choice]:
    return _build_choices_impl(picks, affinity, managers=managers)
def _fit_logit(choices: Sequence[_Choice], *, l2: float, max_iters: int) -> Coefficients:
    rank, affinity = _fit_logit_raw(choices, l2=l2, max_iters=max_iters)
    return Coefficients(rank=rank, affinity=affinity)


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


def _argmax_index(assets: Sequence[DraftAsset], scores: Sequence[float]) -> int:
    """Deterministic best index by score, breaking ties via :func:`_is_better`."""
    best = 0
    for index in range(1, len(scores)):
        if _is_better(assets[index], scores[index], assets[best], scores[best]):
            best = index
    return best


def _sample_softmax_index(scores: Sequence[float], rng: random.Random, temperature: float) -> int:
    """Sample an index from a numerically stable softmax over ``scores``."""
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


def _choose(
    assets: Sequence[DraftAsset],
    scores: Sequence[float],
    rng: random.Random,
    temperature: float,
) -> int:
    if temperature <= 0.0:
        return _argmax_index(assets, scores)
    return _sample_softmax_index(scores, rng, temperature)


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
            "affinity": {
                manager: {
                    str(team_id): round(float(fraction), 6)
                    for team_id, fraction in sorted(teams.items())
                }
                for manager, teams in sorted(self.affinity.items())
            },
        }

    @classmethod
    def from_manifest(
        cls, model: Mapping[str, Any], config: OpponentFitConfig | None = None
    ) -> FittedLeagueOpponents:
        """Reconstruct a fitted model from its serialized ``manifest()`` block.

        Pure (JSON in, model out) — the draft-time load path with no training,
        ingest, or network. ``config`` overrides the drafting hyper-parameters
        (``need_weight`` / ``temperature``); it defaults to the fit defaults.
        """
        cfg = config or OpponentFitConfig()
        league = Coefficients.from_manifest_entry(model["league_coefficients"])
        per_manager: dict[str, Coefficients] = {}
        counts: dict[str, int] = {}
        for manager, entry in model.get("per_manager", {}).items():
            per_manager[str(manager)] = Coefficients.from_manifest_entry(entry["coefficients"])
            counts[str(manager)] = int(entry.get("picks", 0))
        affinity: dict[str, dict[int, float]] = {}
        for manager, teams in model.get("affinity", {}).items():
            affinity[str(manager)] = {int(team): float(frac) for team, frac in teams.items()}
        return cls(
            league=league,
            per_manager=per_manager,
            affinity=affinity,
            manager_pick_counts=counts,
            total_picks=int(model.get("total_picks", 0)),
            config=cfg,
        )

    @classmethod
    def load(cls, artifact_dir: Path) -> FittedLeagueOpponents:
        """Load the committed opponent artifact (``manifest.json``) from ``artifact_dir``.

        Reads only the on-disk manifest — no ``league_draft_picks`` parquet, no
        model fitting, no ingest, no network — so it is safe at draft time.
        """
        manifest_path = Path(artifact_dir) / "manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        model = payload.get("model", payload)
        defaults = OpponentFitConfig()
        cfg_data = payload.get("config", {})
        config = OpponentFitConfig(
            seed=int(cfg_data.get("seed", defaults.seed)),
            temperature=defaults.temperature,
            need_weight=float(cfg_data.get("need_weight", defaults.need_weight)),
            l2=float(cfg_data.get("l2", defaults.l2)),
            manager_blend_k=float(cfg_data.get("manager_blend_k", defaults.manager_blend_k)),
            league_fallback_k=float(cfg_data.get("league_fallback_k", defaults.league_fallback_k)),
            min_manager_picks=int(cfg_data.get("min_manager_picks", defaults.min_manager_picks)),
            fallback_rank=float(cfg_data.get("fallback_rank", defaults.fallback_rank)),
            top_k=int(cfg_data.get("top_k", defaults.top_k)),
        )
        return cls.from_manifest(model, config=config)

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


def load_committed_opponents(
    artifact_dir: Path = DEFAULT_OPPONENT_ARTIFACT_DIR,
) -> FittedLeagueOpponents | None:
    """Load the committed opponent artifact, or ``None`` when it is absent.

    A convenience for CLI auto-detection: the fitted model becomes the default
    only when its committed ``manifest.json`` is present.
    """
    if not (Path(artifact_dir) / "manifest.json").exists():
        return None
    return FittedLeagueOpponents.load(artifact_dir)


def opponent_model_from_config(
    request: OpponentModelConfigRequest | str,
    **legacy: Unpack[_OpponentModelConfigKwargs],
) -> OpponentModel:
    """Return the opponent policy named by ``kind`` (``"greedy"`` or ``"fitted"``).

    Lets the simulator swap policies from a single config string. ``"fitted"`` needs a
    ``fitted`` result and (for a manager-specific model) a ``manager`` id.
    """
    resolved = _resolve_opponent_model_request(request, legacy)
    if resolved.kind == "greedy":
        return GreedyOpponentModel(
            temperature=resolved.temperature,
            need_weight=resolved.need_weight,
        )
    if resolved.kind == "fitted":
        if resolved.fitted is None:
            raise ValueError("kind='fitted' requires a FittedLeagueOpponents instance")
        return (
            resolved.fitted.model_for(resolved.manager)
            if resolved.manager is not None
            else resolved.fitted.model_for("")
        )
    raise ValueError(f"unknown opponent model kind: {resolved.kind!r}")


class _OpponentModelConfigKwargs(TypedDict, total=False):
    manager: str | None
    fitted: FittedLeagueOpponents | None
    need_weight: float
    temperature: float


@dataclass(frozen=True)
class OpponentModelConfigRequest:
    kind: str
    manager: str | None = None
    fitted: FittedLeagueOpponents | None = None
    need_weight: float = 1.0
    temperature: float = 0.0


def _resolve_opponent_model_request(
    request: OpponentModelConfigRequest | str,
    legacy: Mapping[str, object],
) -> OpponentModelConfigRequest:
    if isinstance(request, OpponentModelConfigRequest):
        _reject_opponent_request_kwargs(legacy)
        return request
    return OpponentModelConfigRequest(
        kind=request,
        manager=cast("str | None", legacy.get("manager")),
        fitted=cast("FittedLeagueOpponents | None", legacy.get("fitted")),
        need_weight=cast("float", legacy.get("need_weight", 1.0)),
        temperature=cast("float", legacy.get("temperature", 0.0)),
    )


def _reject_opponent_request_kwargs(legacy: Mapping[str, object]) -> None:
    if legacy:
        raise TypeError("OpponentModelConfigRequest calls do not accept extra keyword args")


def _membership_for_season(
    picks: pd.DataFrame,
    season: int,
    config: OpponentFitConfig,
) -> MembershipScore | None:
    return _eval_membership_for_season(
        picks,
        season,
        config,
        fit_models=fit_opponent_models,
        prepare_picks=_prepare_picks,
        event_keys=event_keys,
    )


def _per_pick_accuracy(
    picks: pd.DataFrame,
    config: OpponentFitConfig,
) -> PerPickScore | None:
    return _eval_per_pick_accuracy(
        picks,
        config,
        fit_models=fit_opponent_models,
        prepare_picks=_prepare_picks,
        event_keys=event_keys,
        rank_keys=_rank_keys,
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


def evaluate_opponents(
    picks: pd.DataFrame, config: OpponentFitConfig | None = None
) -> OpponentEvalResult:
    """Run leave-one-season-out membership + true-order per-pick validation."""
    cfg = config or OpponentFitConfig()
    prepared = _prepare_picks(picks)
    exclusions = _membership_exclusions(prepared, event_keys)
    seasons = sorted(int(s) for s in prepared["season"].unique())
    membership: list[MembershipScore] = []
    for season in seasons:
        score = _membership_for_season(picks, season, cfg)
        if score is not None:
            membership.append(score)
    per_pick = _per_pick_accuracy(picks, cfg)
    return OpponentEvalResult(
        membership=membership,
        per_pick=per_pick,
        membership_exclusions=exclusions,
    )


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
    manifest = add_git_provenance(result.manifest())

    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "report.md").write_text(
        "\n".join(result.report_lines()) + "\n", encoding="utf-8"
    )
    (artifact_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return result

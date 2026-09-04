"""Held-out evaluation helpers for fitted opponent models."""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

import pandas as pd

from draft_oracle.optimize.simulator import (
    DraftAsset,
    DraftState,
    GreedyOpponentModel,
    OpponentModel,
    roster_capacity,
)
from draft_oracle.rules import snake_order


class _OpponentEvalConfig(Protocol):
    @property
    def seed(self) -> int: ...

    @property
    def need_weight(self) -> float: ...

    @property
    def top_k(self) -> int: ...


def _event_assets(pool: pd.DataFrame) -> list[DraftAsset]:
    """Build drafted-asset pool for one event, deduplicated by asset key."""
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
                position=cast(Literal["F", "D", "G"], row["base_position"]),
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
    """Replay one event's snake order with ``models`` and return predicted rosters."""
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
    predicted: Mapping[str, set[str]],
    actual: Mapping[str, set[str]],
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
    """Per-pick top-1 / top-K accuracy on true-order app events."""

    picks: int
    fitted_top1: float
    greedy_top1: float
    fitted_topk: float
    greedy_topk: float
    k: int


@dataclass(frozen=True)
class MembershipExclusion:
    """One draft event omitted from roster-membership validation, with reason."""

    season: int
    draft_event: str
    league_name: str | None
    reason: str

    def manifest(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "draft_event": self.draft_event,
            "league_name": self.league_name,
            "reason": self.reason,
        }

    def report_line(self) -> str:
        league = f" ({self.league_name})" if self.league_name else ""
        return f"- {self.season} {self.draft_event}{league}: {self.reason}."


def _membership_exclusions(
    prepared: pd.DataFrame,
    event_keys: Callable[[pd.DataFrame], list[str]],
) -> list[MembershipExclusion]:
    """List events whose incomplete seat order prevents membership replay."""
    exclusions: list[MembershipExclusion] = []
    for _, pool in prepared.groupby(event_keys(prepared), sort=True):
        if _event_order(pool) is not None:
            continue
        first = pool.iloc[0]
        league_raw = first.get("league_name")
        league_name = str(league_raw) if pd.notna(league_raw) else None
        sources = {str(source) for source in pool.get("source", pd.Series(dtype=str)).dropna()}
        reason = "no snake order in sheet" if sources == {"sheet"} else "no snake order in source"
        exclusions.append(
            MembershipExclusion(
                season=int(first["season"]),
                draft_event=str(first["draft_event"]),
                league_name=league_name,
                reason=reason,
            )
        )
    return exclusions


def _membership_for_season(
    picks: pd.DataFrame,
    season: int,
    config: _OpponentEvalConfig,
    *,
    fit_models: Callable[[pd.DataFrame, Any], Any],
    prepare_picks: Callable[[pd.DataFrame], pd.DataFrame],
    event_keys: Callable[[pd.DataFrame], list[str]],
) -> MembershipScore | None:
    """Leave-one-season-out membership accuracy for ``season``."""
    runtime = _MembershipEvalRuntime(fit_models, prepare_picks, event_keys)
    train = _membership_training_frame(picks, season)
    if train is None:
        return None
    fitted = runtime.fit_models(train, config)
    prepared = runtime.prepare_picks(picks.loc[picks["season"] == season])
    greedy = GreedyOpponentModel(temperature=0.0, need_weight=config.need_weight)

    events = 0
    picks_scored = 0
    fitted_hits = 0.0
    greedy_hits = 0.0
    fitted_total = 0
    greedy_total = 0
    for _, pool in prepared.groupby(runtime.event_keys(prepared), sort=True):
        event_score = _membership_event_score(pool, fitted.as_mapping, greedy, config.seed)
        if event_score is None:
            continue
        events += 1
        picks_scored += event_score.picks
        fitted_hits += event_score.fitted_hits
        greedy_hits += event_score.greedy_hits
        fitted_total += event_score.fitted_total
        greedy_total += event_score.greedy_total
    if events == 0 or fitted_total == 0:
        return None
    return MembershipScore(
        season=season,
        events=events,
        picks=picks_scored,
        fitted_accuracy=fitted_hits / fitted_total,
        greedy_accuracy=greedy_hits / greedy_total,
    )


def _membership_training_frame(picks: pd.DataFrame, season: int) -> pd.DataFrame | None:
    train = picks.loc[picks["season"] != season]
    if train.empty:
        return None
    return train


@dataclass(frozen=True)
class _MembershipEventScore:
    picks: int
    fitted_hits: float
    greedy_hits: float
    fitted_total: int
    greedy_total: int


@dataclass(frozen=True)
class _MembershipEvalRuntime:
    fit_models: Callable[[pd.DataFrame, Any], Any]
    prepare_picks: Callable[[pd.DataFrame], pd.DataFrame]
    event_keys: Callable[[pd.DataFrame], list[str]]


def _membership_event_score(
    pool: pd.DataFrame,
    fitted_mapping: Callable[[list[str]], Mapping[str, OpponentModel]],
    greedy: OpponentModel,
    seed: int,
) -> _MembershipEventScore | None:
    managers = [str(manager) for manager in pool["manager"].unique()]
    actual = _actual_rosters(pool)
    fitted_models = fitted_mapping(managers)
    greedy_models: dict[str, OpponentModel] = dict.fromkeys(managers, greedy)
    fitted_pred = _simulate_membership(pool, fitted_models, seed)
    greedy_pred = _simulate_membership(pool, greedy_models, seed)
    if fitted_pred is None or greedy_pred is None:
        return None
    fitted_accuracy, fitted_count = _membership_accuracy(fitted_pred, actual)
    greedy_accuracy, greedy_count = _membership_accuracy(greedy_pred, actual)
    if fitted_count == 0:
        return None
    return _MembershipEventScore(
        picks=fitted_count,
        fitted_hits=fitted_accuracy * fitted_count,
        greedy_hits=greedy_accuracy * greedy_count,
        fitted_total=fitted_count,
        greedy_total=greedy_count,
    )


def _per_pick_accuracy(
    picks: pd.DataFrame,
    config: _OpponentEvalConfig,
    *,
    fit_models: Callable[[pd.DataFrame, Any], Any],
    prepare_picks: Callable[[pd.DataFrame], pd.DataFrame],
    event_keys: Callable[[pd.DataFrame], list[str]],
    rank_keys: Callable[[OpponentModel, DraftState, str, random.Random | None], list[str]],
) -> PerPickScore | None:
    """Teacher-forced per-pick top-1/top-K accuracy on events with a true pick order."""
    ordered, train = _per_pick_training_frames(picks)
    if ordered is None or train is None:
        return None
    fitted = fit_models(train, config)
    greedy = GreedyOpponentModel(temperature=0.0, need_weight=config.need_weight)

    total = 0
    fitted_top1 = 0
    greedy_top1 = 0
    fitted_topk = 0
    greedy_topk = 0
    prepared = prepare_picks(ordered)
    for _, pool in prepared.groupby(event_keys(prepared), sort=True):
        event_score = _per_pick_event_score(pool, fitted.as_mapping, greedy, config, rank_keys)
        if event_score is None:
            continue
        total += event_score.picks
        fitted_top1 += event_score.fitted_top1
        greedy_top1 += event_score.greedy_top1
        fitted_topk += event_score.fitted_topk
        greedy_topk += event_score.greedy_topk
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


def _per_pick_training_frames(
    picks: pd.DataFrame,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    ordered = picks.loc[picks["pick_number"].notna()]
    if ordered.empty:
        return None, None
    ordered_seasons = {int(season) for season in ordered["season"].unique()}
    train = picks.loc[~picks["season"].isin(ordered_seasons)]
    if train.empty:
        return None, None
    return ordered, train


@dataclass(frozen=True)
class _PerPickEventScore:
    picks: int
    fitted_top1: int
    greedy_top1: int
    fitted_topk: int
    greedy_topk: int


def _per_pick_event_score(
    pool: pd.DataFrame,
    fitted_mapping: Callable[[list[str]], Mapping[str, OpponentModel]],
    greedy: OpponentModel,
    config: _OpponentEvalConfig,
    rank_keys: Callable[[OpponentModel, DraftState, str, random.Random | None], list[str]],
) -> _PerPickEventScore | None:
    order = _event_order(pool)
    if order is None:
        return None
    state = _event_state(pool, order)
    fitted_models = fitted_mapping(order)
    rng = random.Random(config.seed)
    score = _PerPickEventScore(0, 0, 0, 0, 0)
    for _, pick in pool.sort_values("pick_number").iterrows():
        scored_pick = _score_pick(
            state,
            fitted_models[str(pick["manager"])],
            greedy,
            str(pick["manager"]),
            str(pick["asset_key"]),
            config.top_k,
            rank_keys,
            rng,
        )
        if scored_pick is None:
            continue
        fitted_hit, greedy_hit, fitted_topk_hit, greedy_topk_hit, asset = scored_pick
        score = _PerPickEventScore(
            picks=score.picks + 1,
            fitted_top1=score.fitted_top1 + fitted_hit,
            greedy_top1=score.greedy_top1 + greedy_hit,
            fitted_topk=score.fitted_topk + fitted_topk_hit,
            greedy_topk=score.greedy_topk + greedy_topk_hit,
        )
        state.place(str(pick["manager"]), asset)
    return score


def _event_state(pool: pd.DataFrame, order: list[str]) -> DraftState:
    assets = _event_assets(pool)
    allow_ir = bool((pool["position"].isin(["IR_F", "IR_D"])).any())
    return DraftState.new(order, assets, allow_ir=allow_ir)


def _score_pick(
    state: DraftState,
    fitted_model: OpponentModel,
    greedy_model: OpponentModel,
    manager: str,
    key: str,
    top_k: int,
    rank_keys: Callable[[OpponentModel, DraftState, str, random.Random | None], list[str]],
    rng: random.Random,
) -> tuple[int, int, int, int, DraftAsset] | None:
    if key not in state.available:
        return None
    asset = state.available[key]
    if not state.has_capacity(manager, asset.position):
        return None
    legal = state.legal_assets(manager)
    if not any(legal_asset.key == key for legal_asset in legal):
        return None
    fitted_rank = rank_keys(fitted_model, state, manager, None)
    greedy_rank = rank_keys(greedy_model, state, manager, rng)
    return (
        int(bool(fitted_rank) and fitted_rank[0] == key),
        int(bool(greedy_rank) and greedy_rank[0] == key),
        int(key in fitted_rank[:top_k]),
        int(key in greedy_rank[:top_k]),
        asset,
    )


@dataclass
class OpponentEvalResult:
    """Held-out validation: per-season membership + optional per-pick accuracy."""

    membership: list[MembershipScore]
    per_pick: PerPickScore | None
    membership_exclusions: list[MembershipExclusion]

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
            "membership_exclusions": [
                exclusion.manifest() for exclusion in self.membership_exclusions
            ],
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
        if self.membership_exclusions:
            lines.extend(
                [
                    "",
                    "### Events excluded from membership evaluation",
                    "",
                    *[exclusion.report_line() for exclusion in self.membership_exclusions],
                ]
            )
        if self.per_pick is not None:
            per_pick = self.per_pick
            lines.extend(
                [
                    "",
                    "### Per-pick accuracy (true-order app export)",
                    "",
                    f"- picks scored: {per_pick.picks}",
                    (
                        f"- top-1: fitted {per_pick.fitted_top1:.3f} vs greedy "
                        f"{per_pick.greedy_top1:.3f}"
                    ),
                    (
                        f"- top-{per_pick.k}: fitted {per_pick.fitted_topk:.3f} vs greedy "
                        f"{per_pick.greedy_topk:.3f}"
                    ),
                ]
            )
        return lines

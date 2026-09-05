"""IR stash valuation helpers for projection artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from draft_oracle.models.returns import (
    STATUS_MEAN_GAMES,
    ReturnTimeModel,
    derive_absence_spells,
    fit_return_time_model,
)
from draft_oracle.optimize.ir_value import (
    StashInput,
    StashValuation,
    _BuildStashRequest,
    build_stash_valuations,
    render_ir_section,
)


class _CheatSheetLike(Protocol):
    replacement_forward: float
    replacement_defense: float
    ir_section: list[str]


class _ConfigLike(Protocol):
    @property
    def ir(self) -> bool: ...

    @property
    def seed(self) -> int: ...

    @property
    def n_sims(self) -> int: ...

    @property
    def horizon(self) -> int: ...


@dataclass(frozen=True)
class _IrStashInput:
    skaters: pd.DataFrame
    cheatsheet: _CheatSheetLike
    injuries: pd.DataFrame | None
    length_by_abbrev: dict[str, dict[int, float]]
    train_sk: pd.DataFrame
    train_tg: pd.DataFrame
    config: _ConfigLike


def _fit_return_model(
    train_sk: pd.DataFrame,
    train_tg: pd.DataFrame,
    horizon: int,
) -> ReturnTimeModel:
    """Fit the return-time model from pre-cutoff archive spells."""
    spells = derive_absence_spells(train_sk, train_tg)
    if spells.empty:
        return ReturnTimeModel(
            spell_lengths=(),
            horizon=horizon,
            status_mean_games=dict(STATUS_MEAN_GAMES),
        )
    return fit_return_time_model(spells, horizon=horizon)


def _apply_ir_stash(request: _IrStashInput) -> list[StashValuation]:
    """Value injured F/D as IR stashes and fold the result into sheet + table."""
    skaters = request.skaters
    config = request.config
    if not config.ir or skaters.empty:
        return []
    injured = skaters.loc[skaters["injured"] & skaters["position"].isin(("F", "D"))]
    if injured.empty:
        return []

    model = _fit_return_model(request.train_sk, request.train_tg, config.horizon)
    inputs = _stash_inputs(
        injured,
        request.length_by_abbrev,
        _status_by_player_id(request.injuries),
        model,
    )
    valuations = build_stash_valuations(
        _BuildStashRequest(
            inputs,
            {
                "F": request.cheatsheet.replacement_forward,
                "D": request.cheatsheet.replacement_defense,
            },
        ),
        seed=config.seed,
        n_sims=config.n_sims,
        horizon=config.horizon,
    )
    _write_stash_columns(skaters, valuations)
    request.cheatsheet.ir_section = render_ir_section(valuations)
    return valuations


def _status_by_player_id(injuries: pd.DataFrame | None) -> dict[int, str]:
    if injuries is None or injuries.empty:
        return {}
    statuses: dict[int, str] = {}
    for rec in injuries.to_dict("records"):
        pid = rec.get("player_id")
        if pid is not None and pd.notna(pid):
            statuses[int(pid)] = str(rec.get("status") or "out")
    return statuses


def _stash_inputs(
    injured: pd.DataFrame,
    length_by_abbrev: dict[str, dict[int, float]],
    status_by_id: dict[int, str],
    model: ReturnTimeModel,
) -> list[StashInput]:
    inputs: list[StashInput] = []
    for rec in injured.to_dict("records"):
        team_abbrev = str(rec["team_abbrev"])
        length_probs = length_by_abbrev.get(team_abbrev)
        if length_probs is None:
            continue
        player_id = int(rec["player_id"])
        status = status_by_id.get(player_id, "out")
        curve = model.availability_curve(status)
        inputs.append(
            StashInput(
                player_id=player_id,
                player_name=str(rec.get("player_name", "")),
                position=str(rec["position"]),
                team_abbrev=team_abbrev,
                status=status,
                pts_per_game=float(rec["pts_per_game"]),
                length_probs=length_probs,
                availability_curve=curve,
                expected_games_available=float(sum(curve)),
            )
        )
    return inputs


def _write_stash_columns(skaters: pd.DataFrame, valuations: list[StashValuation]) -> None:
    by_id = {val.player_id: val for val in valuations}
    for column, attr in (
        ("ir_stash_ev", "stash_ev"),
        ("ir_stash_value", "stash_value"),
    ):
        skaters[column] = skaters["player_id"].map(
            lambda pid, a=attr: getattr(by_id[int(pid)], a) if int(pid) in by_id else float("nan")
        )
        skaters["ir_verdict"] = skaters["player_id"].map(
            lambda pid: by_id[int(pid)].verdict if int(pid) in by_id else ""
        )

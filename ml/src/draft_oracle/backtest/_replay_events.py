"""Backtest round and draft-event helpers."""

from __future__ import annotations

import pandas as pd

from draft_oracle.optimize.simulator import DraftAsset, roster_capacity

ROUND_TO_DRAFT_EVENT: dict[int, str] = {1: "R1", 2: "R2", 3: "R3_4", 4: "R3_4"}

def _draft_shortfall(pool: list[DraftAsset], managers: int, allow_ir: bool) -> str | None:
    """Describe why ``pool`` cannot fill a ``managers``-way draft, or ``None`` if it can.

    Late playoff rounds have too few eligible teams to seat a full league — the Cup
    Final's two teams cannot supply four managers a unique goalie, for instance. This
    reports the first unmet positional demand so the round is skipped honestly rather
    than crashing mid-draft (SPEC section 7).
    """
    capacity = roster_capacity(allow_ir)
    have = {"F": 0, "D": 0, "G": 0}
    for asset in pool:
        have[asset.position] += 1
    demand = {
        "F": capacity.forwards * managers,
        "D": capacity.defense * managers,
        "G": capacity.goalies * managers,
    }
    for position in ("F", "D", "G"):
        if have[position] < demand[position]:
            return f"{position}: {have[position]} available < {demand[position]} needed"
    return None


def _season_id_for(series: pd.DataFrame, season: int) -> int:
    """Resolve the numeric ``season_id`` for a backtested season from the series table."""
    scoped = series.loc[series["year"].astype(int) == int(season)]
    if scoped.empty:
        raise ValueError(f"no series rows for season {season}")
    return int(scoped["season_id"].iloc[0])


def _season_rounds(series: pd.DataFrame, season: int) -> list[int]:
    """Best-of-7 playoff rounds (1-4) present for ``season`` (round 0 excluded)."""
    scoped = series.loc[series["year"].astype(int) == int(season)]
    rounds = sorted({int(r) for r in scoped["playoff_round"].unique() if int(r) >= 1})
    return rounds


def _draft_events(rounds: list[int]) -> list[tuple[int, list[int]]]:
    """Group playoff rounds into the league's draft events.

    Returns ``(draft_round, scored_rounds)`` per event, where ``draft_round`` is the
    earliest round of the event (whose as-of projection drives the draft) and
    ``scored_rounds`` is every round the drafted roster is scored across. Rounds 3 and
    4 collapse into the single combined ``R3_4`` event (:data:`ROUND_TO_DRAFT_EVENT`).
    """
    by_event: dict[str, list[int]] = {}
    for rnd in rounds:
        event = ROUND_TO_DRAFT_EVENT.get(rnd, f"R{rnd}")
        by_event.setdefault(event, []).append(rnd)
    events = [(min(grouped), sorted(grouped)) for grouped in by_event.values()]
    return sorted(events)

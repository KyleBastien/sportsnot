"""Session save/resume helpers for interactive draft CLI."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol, cast

from draft_oracle.cli._draft_resolution import RecordedPick
from draft_oracle.optimize.simulator import DraftAsset


class _SessionLike(Protocol):
    artifact_dir: Path
    manager_count: int
    @property
    def managers(self) -> Sequence[str]: ...

    slot: int
    ir: bool
    temperature: float
    seed: int
    rollouts: int
    opponents: str
    opponent_artifact_dir: Path
    eliminated_team_ids: frozenset[int]

    @property
    def picks(self) -> Sequence[RecordedPick]: ...


def _session_dict(session: _SessionLike, *, version: int) -> dict[str, Any]:
    return {
        "version": version,
        "artifact_dir": str(session.artifact_dir),
        "manager_count": session.manager_count,
        "managers": list(session.managers),
        "slot": session.slot,
        "ir": session.ir,
        "temperature": session.temperature,
        "seed": session.seed,
        "rollouts": session.rollouts,
        "opponents": session.opponents,
        "opponent_artifact_dir": str(session.opponent_artifact_dir),
        "eliminated_team_ids": sorted(session.eliminated_team_ids),
        "picks": [pick.as_dict() for pick in session.picks],
    }


def _save_session(path: Path, data: dict[str, Any]) -> None:
    path = Path(path)
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_session_data(path: Path) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(Path(path).read_text(encoding="utf-8")))


def _resume_inputs(
    path: Path,
    *,
    pool_loader: Callable[[Path, bool], list[DraftAsset]],
) -> tuple[dict[str, Any], list[DraftAsset]]:
    data = _load_session_data(path)
    artifact_dir = Path(data["artifact_dir"])
    ir = bool(data["ir"])
    pool = pool_loader(artifact_dir, ir)
    return data, pool

"""Manifest assembly for projection artifacts."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np

from draft_oracle import __version__
from draft_oracle._projection_combined import (
    _COMBINED_DRAFT_ROUND,
    _COMBINED_SCORED_ROUNDS,
)
from draft_oracle.features.skater import FEATURE_SET_VERSION
from draft_oracle.models.game_win import GAME_WIN_MODEL_VERSION
from draft_oracle.models.projections import PROJECTION_VERSION
from draft_oracle.models.series_sim import SERIES_SIM_VERSION
from draft_oracle.models.shutout import SHUTOUT_MODEL_VERSION
from draft_oracle.models.skater_production import SKATER_PRODUCTION_VERSION
from draft_oracle.provenance import add_git_provenance


@dataclass(frozen=True)
class ProjectionManifestInput:
    artifact_version: str
    season: int
    playoff_round: int
    snapshot_id: str
    context: Any
    outputs: Any
    config: Any
    git_sha: str | None = None
    generated_at: str | None = None


def _projection_manifest(request: ProjectionManifestInput) -> dict[str, Any]:
    outputs = request.outputs
    config = request.config
    return add_git_provenance(
        {
            "artifact_version": request.artifact_version,
            "package_version": __version__,
            "season": int(request.season),
            "playoff_round": int(request.playoff_round),
            "snapshot_id": request.snapshot_id,
            "as_of_cutoff": request.context.cutoff,
            "feature_version": FEATURE_SET_VERSION,
            "model_versions": {
                "game_win": GAME_WIN_MODEL_VERSION,
                "shutout": SHUTOUT_MODEL_VERSION,
                "skater_production": SKATER_PRODUCTION_VERSION,
                "series_sim": SERIES_SIM_VERSION,
                "projection": PROJECTION_VERSION,
            },
            "git_sha": request.git_sha,
            "seeds": {"base": config.seed, "n_sims": config.n_sims, "horizon": config.horizon},
            "cli_flags": {
                "managers": config.managers,
                "ir": config.ir,
                "seed": config.seed,
                "no_refresh": config.no_refresh,
                "slot_strategies": config.slot_strategies,
                "slot_rollouts": config.resolved_slot_config.rollouts,
                "combine_final_rounds": config.combine_final_rounds,
                "n_sims": config.n_sims,
                "horizon": config.horizon,
            },
            "platform": {
                "os": platform.system(),
                "os_release": platform.release(),
                "machine": platform.machine(),
                "python": platform.python_version(),
                "numpy": np.__version__,
            },
            "generated_at": request.generated_at or datetime.now(UTC).isoformat(),
            "scarcity": outputs.cheatsheet.summary(),
            "counts": {
                "eligible_series": int(len(outputs.teams) // 2),
                "eligible_teams": len(outputs.teams),
                "skaters_projected": len(outputs.skaters),
                "skaters_injured": (
                    int(outputs.skaters["injured"].sum()) if not outputs.skaters.empty else 0
                ),
            },
            "eligible_team_abbrevs": sorted(outputs.length_by_abbrev),
            "ir_stash": {
                "enabled": config.ir,
                "candidates": len(outputs.ir_valuations),
                "stash_verdicts": sum(
                    1 for valuation in outputs.ir_valuations if valuation.verdict == "stash"
                ),
            },
            "slot_strategies": (
                outputs.slot_report.summary() if outputs.slot_report is not None else None
            ),
            "combined_event": (
                {
                    "draft_event": "R3_4",
                    "draft_round": _COMBINED_DRAFT_ROUND,
                    "scored_rounds": list(_COMBINED_SCORED_ROUNDS),
                    "teams": outputs.combined_diagnostics,
                }
                if outputs.combined_diagnostics is not None
                else None
            ),
            "warnings": request.context.warnings,
        }
    )

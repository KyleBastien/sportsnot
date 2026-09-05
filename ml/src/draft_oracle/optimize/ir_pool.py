"""Lightweight IR pool repricing for draft-time artifact consumers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from draft_oracle.optimize.simulator import DraftAsset

__all__ = ["reprice_pool_for_ir"]


def reprice_pool_for_ir(
    pool: Sequence[DraftAsset],
    stash_value_by_player: Mapping[int, float],
) -> list[DraftAsset]:
    """Reprice injured skaters to their committed IR stash value.

    This primitive stays separate from simulation-based stash valuation so live
    draft commands can consume precomputed artifacts without importing model-training
    dependencies.
    """
    repriced: list[DraftAsset] = []
    for asset in pool:
        if asset.player_id is not None and asset.player_id in stash_value_by_player:
            value = float(stash_value_by_player[asset.player_id])
            repriced.append(
                DraftAsset(
                    key=asset.key,
                    name=asset.name,
                    position=asset.position,
                    rank_value=value,
                    player_id=asset.player_id,
                    team_id=asset.team_id,
                    team_abbrev=asset.team_abbrev,
                    projection=value,
                )
            )
        else:
            repriced.append(asset)
    return repriced

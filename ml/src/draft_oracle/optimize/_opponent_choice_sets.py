"""Choice-set preparation and conditional-logit fitting for opponent models."""

from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

_BASE_BY_POSITION: dict[str, str] = {
    "F": "F",
    "IR_F": "F",
    "D": "D",
    "IR_D": "D",
    "G": "G",
}


def base_position(position: str) -> str | None:
    """Collapse a roster-slot label to a base draft position (``F``/``D``/``G``)."""
    return _BASE_BY_POSITION.get(position.strip())


def _asset_key(player_id: int | None, team_id: int | None, position: str) -> str | None:
    if position == "G":
        return f"T{team_id}" if team_id is not None else None
    return f"P{player_id}" if player_id is not None else None


def build_team_affinity(picks: pd.DataFrame) -> dict[str, dict[int, float]]:
    """``manager -> {team_id: fraction of that manager's picks on that team}``."""
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
    affinity: Mapping[str, Mapping[int, float]],
    manager: str,
    team_id: int | None,
) -> float:
    if team_id is None:
        return 0.0
    return float(affinity.get(manager, {}).get(int(team_id), 0.0))


@dataclass(frozen=True)
class _Choice:
    """One observed selection: feature rows for the pool plus the chosen index."""

    features: Any
    chosen: int


_SOURCE_PRIORITY: dict[str, int] = {"app": 0, "sheet": 1}


def event_keys(frame: pd.DataFrame) -> list[str]:
    """Grouping keys that isolate one real draft event, league-aware when possible."""
    keys = ["season"]
    if "league_name" in frame.columns:
        keys.append("league_name")
    keys.append("draft_event")
    return keys


def _dedupe_asset_key(row: Mapping[Hashable, Any]) -> str | None:
    position = str(row.get("position", ""))
    asset_id = row.get("team_id") if position == "G" else row.get("player_id")
    if pd.notna(asset_id):
        prefix = "T" if position == "G" else "P"
        return f"{prefix}{int(asset_id)}"
    return None


def _merge_sheet_team_ids(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    fill_keys = [*keys, "manager", "player_id"]
    sheet_rows = frame.loc[
        frame["source"].eq("sheet")
        & frame["player_id"].notna()
        & frame["team_id"].notna()
        & ~frame["position"].eq("G"),
        [*fill_keys, "team_id"],
    ].drop_duplicates()
    if sheet_rows.empty:
        return frame

    candidate_counts = sheet_rows.groupby(fill_keys, dropna=False)["team_id"].transform("size")
    supplements = sheet_rows.loc[candidate_counts.eq(1)].rename(
        columns={"team_id": "_sheet_team_id"}
    )
    merged = frame.merge(supplements, on=fill_keys, how="left", validate="many_to_one")
    missing_app_team = (
        merged["source"].eq("app")
        & ~merged["position"].eq("G")
        & merged["team_id"].isna()
        & merged["_sheet_team_id"].notna()
    )
    merged.loc[missing_app_team, "team_id"] = merged.loc[missing_app_team, "_sheet_team_id"]
    return merged.drop(columns="_sheet_team_id")


def dedupe_duplicate_events(picks: pd.DataFrame) -> pd.DataFrame:
    """Merge sheet metadata, then prefer ``source='app'`` for duplicate drafts."""
    if "source" not in picks.columns or "league_name" not in picks.columns:
        return picks
    frame = picks.copy()
    keys = event_keys(frame)
    frame = _merge_sheet_team_ids(frame, keys)
    if "points_excluded" in frame.columns and "manager" in frame.columns:
        frame["_dedupe_asset_key"] = [_dedupe_asset_key(row) for row in frame.to_dict("records")]
        resolved = frame["_dedupe_asset_key"].notna()
        flag_keys = [*keys, "manager", "_dedupe_asset_key"]
        frame.loc[resolved, "points_excluded"] = (
            frame.loc[resolved]
            .groupby(flag_keys, dropna=False)["points_excluded"]
            .transform(lambda values: values.fillna(False).astype(bool).any())
        )
    frame["_source_priority"] = frame["source"].map(
        lambda source: _SOURCE_PRIORITY.get(str(source), len(_SOURCE_PRIORITY))
    )
    best = frame.groupby(keys)["_source_priority"].transform("min")
    helper_columns = ["_source_priority"]
    if "_dedupe_asset_key" in frame.columns:
        helper_columns.append("_dedupe_asset_key")
    kept = frame.loc[frame["_source_priority"] == best].drop(columns=helper_columns)
    return kept.reset_index(drop=True)


def _prepare_picks(picks: pd.DataFrame) -> pd.DataFrame:
    """Attach base position + asset key and drop rows we cannot model."""
    frame = dedupe_duplicate_events(picks).copy()
    frame["base_position"] = frame["position"].map(lambda position: base_position(str(position)))
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


def _pool_asset_fields(
    pool: pd.DataFrame,
) -> tuple[list[str], list[int | None], np.ndarray] | None:
    unique = pool.drop_duplicates(subset="asset_key")
    if len(unique) < 2:
        return None
    keys = list(unique["asset_key"].astype(str))
    team_ids = [
        int(team_id) if pd.notna(team_id) else None
        for team_id in unique["team_id"].to_numpy(dtype=object)
    ]
    rank_z = _pool_rank_z(unique)
    features = np.array([[rank_z[key], 0.0] for key in keys], dtype="float64")
    return keys, team_ids, features


def _iter_modelled_picks(
    pool: pd.DataFrame,
    managers: frozenset[str] | None,
) -> Sequence[tuple[str, str]]:
    picks: list[tuple[str, str]] = []
    for _, pick in pool.iterrows():
        manager = str(pick["manager"])
        if managers is not None and manager not in managers:
            continue
        picks.append((manager, str(pick["asset_key"])))
    return picks


def _manager_features(
    base: np.ndarray,
    affinity: Mapping[str, Mapping[int, float]],
    manager: str,
    team_ids: Sequence[int | None],
) -> np.ndarray:
    features = base.copy()
    features[:, 1] = [_affinity_for(affinity, manager, team_id) for team_id in team_ids]
    return features


def _pool_choices(
    pool: pd.DataFrame,
    affinity: Mapping[str, Mapping[int, float]],
    managers: frozenset[str] | None,
) -> list[_Choice]:
    """Conditional-logit choices for one ``(event, base_position)`` pool."""
    asset_fields = _pool_asset_fields(pool)
    if asset_fields is None:
        return []
    keys, team_ids, base = asset_fields
    index_of = {key: i for i, key in enumerate(keys)}
    choices: list[_Choice] = []
    for manager, asset_key in _iter_modelled_picks(pool, managers):
        chosen = index_of.get(asset_key)
        if chosen is None:
            continue
        choices.append(
            _Choice(
                features=_manager_features(base, affinity, manager, team_ids),
                chosen=chosen,
            )
        )
    return choices


def _build_choices(
    picks: pd.DataFrame,
    affinity: Mapping[str, Mapping[int, float]],
    *,
    managers: frozenset[str] | None = None,
) -> list[_Choice]:
    """Build conditional-logit choices from observed per-event position pools."""
    choices: list[_Choice] = []
    for _, pool in picks.groupby([*event_keys(picks), "base_position"], sort=True):
        choices.extend(_pool_choices(pool, affinity, managers))
    return choices


def _softmax(scores: Any) -> Any:
    shifted = scores - scores.max()
    weights = np.exp(shifted)
    return weights / weights.sum()


def _fit_logit(
    choices: Sequence[_Choice],
    *,
    l2: float,
    max_iters: int,
) -> tuple[float, float]:
    """L2-regularized conditional-logit fit by Newton-Raphson on two coefficients."""
    if not choices:
        return 0.0, 0.0
    beta = np.zeros(2, dtype="float64")
    for _ in range(max_iters):
        grad = -l2 * beta
        hess = -l2 * np.eye(2, dtype="float64")
        for choice in choices:
            features = choice.features
            probs = _softmax(features @ beta)
            mean_features = features.T @ probs
            grad = grad + features[choice.chosen] - mean_features
            hess = hess - (
                (features.T * probs) @ features - np.outer(mean_features, mean_features)
            )
        try:
            step = np.linalg.solve(hess, grad)
        except np.linalg.LinAlgError:
            step = -0.1 * grad
        beta = beta - step
        if float(np.abs(step).max()) < 1e-8:
            break
    return float(beta[0]), float(beta[1])

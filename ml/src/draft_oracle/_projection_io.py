"""Projection artifact normalized-input helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

DEFAULT_NORMALIZED_DIR = Path("data/normalized")
DEFAULT_ARTIFACTS_ROOT = Path("artifacts")
SNAPSHOTS_SUBDIR = "snapshots"
SNAPSHOT_MANIFEST_NAME = "_manifest.json"

# Optional tables a pinned run consumes; a complete snapshot records each as
# "frozen" or "absent" so absence is the frozen truth, not a silent live read.
_OPTIONAL_SNAPSHOT_TABLES = ("league_draft_picks", "odds", "injuries")


def _require_complete_snapshot(source_dir: Path) -> dict[str, object]:
    """Fail loudly when a pinned snapshot is not a complete input contract."""
    manifest_path = source_dir / SNAPSHOT_MANIFEST_NAME
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"pinned snapshot at {source_dir} has no {SNAPSHOT_MANIFEST_NAME}; "
            "recreate it with `oracle snapshot` so every consumed input is frozen"
        )
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not (isinstance(loaded, dict) and loaded.get("complete") is True):
        raise RuntimeError(
            f"pinned snapshot {source_dir.name} predates complete-snapshot support "
            "(no 'complete' marker); recreate it with `oracle snapshot` so "
            "league_draft_picks/odds/injuries are frozen instead of read live (M-10)"
        )
    optional = loaded.get("optional_tables")
    if isinstance(optional, dict):
        _validate_optional_snapshot_tables(source_dir, optional)
    return loaded


def _validate_optional_snapshot_tables(
    source_dir: Path, optional: dict[object, object]
) -> None:
    for name in _OPTIONAL_SNAPSHOT_TABLES:
        if optional.get(name) == "frozen" and not (source_dir / f"{name}.parquet").exists():
            raise FileNotFoundError(
                f"pinned snapshot {source_dir.name} declares '{name}' frozen but "
                f"{name}.parquet is missing from the snapshot"
            )


def _load_tables(source_dir: Path) -> dict[str, pd.DataFrame]:
    """Read the four normalized tables the projection needs from ``source_dir``."""
    return {
        name: pd.read_parquet(source_dir / f"{name}.parquet")
        for name in ("skater_games", "players", "team_games", "series")
    }


def _load_injuries(source_dir: Path) -> pd.DataFrame | None:
    """Load the current-status injuries table from ``source_dir``, else ``None``."""
    path = source_dir / "injuries.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path)


def _load_league_picks(source_dir: Path) -> pd.DataFrame | None:
    """Load the entity-matched league draft history from ``source_dir``, else ``None``."""
    path = source_dir / "league_draft_picks.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path)


def _snapshot_id_for(source_dir: Path, snapshot: str | None) -> str:
    """Resolve the recorded snapshot id: the pinned id, or the source signature."""
    if snapshot:
        return snapshot
    manifest_path = source_dir / SNAPSHOT_MANIFEST_NAME
    if not manifest_path.exists():
        return "live"
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        return "live"
    sources = loaded.get("sources")
    if not isinstance(sources, dict):
        return "live"
    total = sum(int(value) for value in sources.values())
    return f"live-{len(sources)}src-{total}b"

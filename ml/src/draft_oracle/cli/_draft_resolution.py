"""Pure resolution and log-entry helpers for interactive draft CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from draft_oracle.optimize.simulator import DraftAsset

_FUZZY_MARGIN = 0.08
_FUZZY_FLOOR = 0.5


def resolve_manager(managers: list[str], token: str) -> str | None:
    """Resolve a manager ``token`` (1-based seat number, id, or prefix)."""
    stripped = token.strip().lower()
    if not stripped:
        return None
    if stripped.isdigit():
        return _manager_by_seat(managers, int(stripped))
    exact = _manager_by_exact_id(managers, stripped)
    if exact is not None:
        return exact
    return _manager_by_prefix(managers, stripped)


def _manager_by_seat(managers: list[str], index: int) -> str | None:
    if 1 <= index <= len(managers):
        return managers[index - 1]
    return None


def _manager_by_exact_id(managers: list[str], stripped: str) -> str | None:
    for manager in managers:
        if manager.lower() == stripped:
            return manager
    return None


def _manager_by_prefix(managers: list[str], stripped: str) -> str | None:
    prefixed = [manager for manager in managers if manager.lower().startswith(stripped)]
    if len(prefixed) == 1:
        return prefixed[0]
    return None


@dataclass(frozen=True)
class AssetResolution:
    """Outcome of resolving a fuzzy name against the pool."""

    asset: DraftAsset | None
    matches: list[DraftAsset]
    reason: str


def _ratio(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def _named_asset_matches(
    pool: list[DraftAsset],
    normalized: str,
    *,
    limit: int,
) -> AssetResolution | None:
    exact = [asset for asset in pool if asset.name.lower() == normalized]
    if len(exact) == 1:
        return AssetResolution(exact[0], exact, "")
    if len(exact) >= 2:
        return AssetResolution(None, exact[:limit], "ambiguous")

    substrings = [asset for asset in pool if normalized in asset.name.lower()]
    if len(substrings) == 1:
        return AssetResolution(substrings[0], substrings, "")
    return None


def _fuzzy_asset_resolution(
    pool: list[DraftAsset],
    normalized: str,
    *,
    limit: int,
) -> AssetResolution:
    substrings = [asset for asset in pool if normalized in asset.name.lower()]
    candidates = substrings if substrings else list(pool)
    scored = sorted(
        candidates,
        key=lambda asset: (-_ratio(normalized, asset.name.lower()), asset.name.lower(), asset.key),
    )
    if not scored:
        return AssetResolution(None, [], "no match")

    top = scored[0]
    top_score = _ratio(normalized, top.name.lower())
    if not substrings and top_score < _FUZZY_FLOOR:
        return AssetResolution(None, scored[:limit], "no match")
    if len(scored) >= 2:
        second_score = _ratio(normalized, scored[1].name.lower())
        if top_score - second_score < _FUZZY_MARGIN:
            return AssetResolution(None, scored[:limit], "ambiguous")
    return AssetResolution(top, scored[:limit], "")


def resolve_asset(pool: list[DraftAsset], query: str, *, limit: int = 5) -> AssetResolution:
    """Resolve a fuzzy ``query`` to a single pool asset (pure, deterministic)."""
    normalized = query.strip().lower()
    if not normalized:
        return AssetResolution(None, [], "empty query")
    named = _named_asset_matches(pool, normalized, limit=limit)
    if named is not None:
        return named
    return _fuzzy_asset_resolution(pool, normalized, limit=limit)


@dataclass(frozen=True)
class RecordedPick:
    """One recorded pick: who drafted which asset (a replayable log entry)."""

    manager: str
    asset_key: str
    name: str
    position: str

    def as_dict(self) -> dict[str, str]:
        return {
            "manager": self.manager,
            "asset_key": self.asset_key,
            "name": self.name,
            "position": self.position,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecordedPick:
        return cls(
            manager=str(data["manager"]),
            asset_key=str(data["asset_key"]),
            name=str(data["name"]),
            position=str(data["position"]),
        )


@dataclass(frozen=True)
class ActionResult:
    """Outcome of a session action: success flag, message, and any lines."""

    ok: bool
    message: str
    lines: list[str] = field(default_factory=list)

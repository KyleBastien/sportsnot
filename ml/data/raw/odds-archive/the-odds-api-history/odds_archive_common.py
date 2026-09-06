"""Shared path, environment, timestamp, and digest helpers."""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path


def _value_from_line(raw_line: str, name: str) -> str | None:
    line = raw_line.strip()
    if not line:
        return None
    if line.startswith("#"):
        return None
    key, separator, candidate = line.partition("=")
    if not separator:
        return None
    if key.strip() != name:
        return None
    value = candidate.strip().strip('"').strip("'")
    return value or None


def _env_file_value(name: str) -> str | None:
    env_path = Path(__file__).resolve().parents[4] / ".env"
    if not env_path.exists():
        return None
    values = (
        _value_from_line(raw_line, name)
        for raw_line in env_path.read_text(encoding="utf-8").splitlines()
    )
    return next((value for value in values if value), None)


def load_env_value(name: str) -> str:
    """Read a secret from process environment, then ignored ml/.env."""
    value = os.environ.get(name) or _env_file_value(name)
    if value:
        return value
    raise RuntimeError(f"{name} is missing from environment and ml/.env")


def assert_outside_repository(path: Path) -> None:
    """Reject plaintext scratch paths located anywhere inside this repository."""
    repository = Path(__file__).resolve().parents[5]
    try:
        path.resolve().relative_to(repository)
    except ValueError:
        return
    raise RuntimeError("scratch directory must be outside repository")


def isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise RuntimeError(f"timestamp lacks timezone: {value}")
    return parsed.astimezone(UTC)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

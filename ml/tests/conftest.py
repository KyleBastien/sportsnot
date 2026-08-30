"""Suite-wide safety fixtures."""

from __future__ import annotations

import socket
from collections.abc import Generator
from typing import NoReturn

import pytest


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Make accidental network access fail; explicit in-memory transports still work."""

    def denied(*_args: object, **_kwargs: object) -> NoReturn:
        raise RuntimeError("network access is forbidden in tests; use a fixture transport")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    yield

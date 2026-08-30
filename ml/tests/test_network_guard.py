"""Suite-wide no-network policy regression."""

from __future__ import annotations

import socket

import pytest


def test_network_guard_blocks_socket_connections() -> None:
    with pytest.raises(RuntimeError, match="network access is forbidden"):
        socket.create_connection(("example.com", 443))

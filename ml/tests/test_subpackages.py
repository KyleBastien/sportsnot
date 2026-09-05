"""Placeholder import tests — one per pipeline subpackage (SPEC §4).

These assert the directory contract exists and each subpackage imports cleanly.
Future stories replace/extend these with behavioral tests.
"""

from __future__ import annotations

import importlib

import pytest

SUBPACKAGES = [
    "draft_oracle.ingest",
    "draft_oracle.features",
    "draft_oracle.models",
    "draft_oracle.optimize",
    "draft_oracle.cli",
    "draft_oracle.backtest",
]


@pytest.mark.parametrize("module_name", SUBPACKAGES)
def test_subpackage_imports(module_name: str) -> None:
    module = importlib.import_module(module_name)
    assert module.__doc__, f"{module_name} should document its purpose"

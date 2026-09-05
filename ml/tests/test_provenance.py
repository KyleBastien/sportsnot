"""Artifact provenance tests."""

from __future__ import annotations

import subprocess

import pytest

from draft_oracle.provenance import add_git_provenance, git_state


@pytest.mark.parametrize(("status", "dirty"), [("", False), (" M file.py\n", True)])
def test_git_state_reports_dirty_tree(
    monkeypatch: pytest.MonkeyPatch, status: str, dirty: bool
) -> None:
    outputs = iter(("deadbeef\n", status))

    def run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, stdout=next(outputs), stderr="")

    monkeypatch.setattr(subprocess, "run", run)

    assert git_state() == ("deadbeef", dirty)


def test_add_git_provenance_preserves_explicit_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("draft_oracle.provenance.git_state", lambda: ("head", True))

    assert add_git_provenance({"git_sha": "pinned"}) == {
        "git_sha": "pinned",
        "git_dirty": True,
    }

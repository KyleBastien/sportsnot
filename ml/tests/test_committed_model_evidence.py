"""Regression checks for committed model and backtest evidence."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pytest

ML_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_ROOT = ML_ROOT / "artifacts"
EVIDENCE_PASS_FILE = ARTIFACTS_ROOT / "EVIDENCE_PASS.json"
MODEL_ARTIFACTS = (
    "game-win",
    "opponent",
    "recommend",
    "return-time",
    "series-sim",
    "shutout",
    "skater-production",
    "skater-projection",
)
BACKTEST_ARTIFACTS = (
    "2023-2024-2025-seed20260827",
    "2026-combined-r500-seed20260827",
)
PROJECTION_ARTIFACTS = ("2026-r1", "2026-r2", "2026-r3", "2026-r4")
EXPECTED_SEED = 20260827


def _manifest(path: Path) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((path / "manifest.json").read_text(encoding="utf-8")),
    )


def _manifest_file(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


MODEL_MANIFESTS = tuple(
    ARTIFACTS_ROOT / "models" / name / "manifest.json" for name in MODEL_ARTIFACTS
)
BACKTEST_MANIFESTS = tuple(
    ARTIFACTS_ROOT / "backtests" / name / "manifest.json" for name in BACKTEST_ARTIFACTS
)
PROJECTION_MANIFESTS = tuple(
    ARTIFACTS_ROOT / name / "run_manifest.json" for name in PROJECTION_ARTIFACTS
)
ALL_EVIDENCE_MANIFESTS = MODEL_MANIFESTS + BACKTEST_MANIFESTS + PROJECTION_MANIFESTS
GIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")


def _evidence_pass_git_sha() -> str:
    evidence_pass = _manifest_file(EVIDENCE_PASS_FILE)
    git_sha = str(evidence_pass["git_sha"])
    assert GIT_SHA_PATTERN.fullmatch(git_sha), (
        f"{EVIDENCE_PASS_FILE.relative_to(ML_ROOT)} carries malformed git_sha {git_sha!r}"
    )
    return git_sha


def _assert_manifest_matches_evidence_pass(
    manifest_path: Path, expected_git_sha: str
) -> None:
    manifest = _manifest_file(manifest_path)
    git_sha = _assert_git_sha(manifest, manifest_path.name)
    assert git_sha == expected_git_sha, (
        f"{manifest_path.name} git_sha {git_sha} does not match committed evidence "
        f"pass {expected_git_sha}"
    )
    _assert_clean_git_provenance(manifest, manifest_path.name)


def _values_for_key(value: object, key: str) -> list[object]:
    if isinstance(value, Mapping):
        return _values_for_key_in_mapping(value, key)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return _values_for_key_in_sequence(value, key)
    return []


def _values_for_key_in_mapping(value: Mapping[object, object], key: str) -> list[object]:
    found = [item for item_key, item in value.items() if item_key == key]
    for item in value.values():
        found.extend(_values_for_key(item, key))
    return found


def _values_for_key_in_sequence(value: Sequence[object], key: str) -> list[object]:
    found: list[object] = []
    for item in value:
        found.extend(_values_for_key(item, key))
    return found


def _assert_git_sha(manifest: Mapping[str, object], manifest_name: str) -> str:
    git_sha = str(manifest["git_sha"])
    assert GIT_SHA_PATTERN.fullmatch(git_sha), (
        f"{manifest_name} carries malformed git_sha {git_sha!r}"
    )
    return git_sha


def _assert_clean_git_provenance(manifest: Mapping[str, object], manifest_name: str) -> None:
    _assert_git_sha(manifest, manifest_name)
    assert manifest["git_dirty"] is False, f"{manifest_name} must carry git_dirty=false"


@pytest.mark.parametrize("manifest_path", ALL_EVIDENCE_MANIFESTS)
def test_committed_evidence_matches_pinned_pass(manifest_path: Path) -> None:
    _assert_manifest_matches_evidence_pass(manifest_path, _evidence_pass_git_sha())


def test_evidence_pass_guard_rejects_stale_manifest(tmp_path: Path) -> None:
    stale_manifest = _manifest_file(MODEL_MANIFESTS[0])
    expected_git_sha = _evidence_pass_git_sha()
    stale_manifest["git_sha"] = (
        "0" * 40 if expected_git_sha != "0" * 40 else "1" * 40
    )
    stale_path = tmp_path / "manifest.json"
    stale_path.write_text(json.dumps(stale_manifest), encoding="utf-8")

    with pytest.raises(AssertionError, match="does not match committed evidence pass"):
        _assert_manifest_matches_evidence_pass(stale_path, expected_git_sha)


@pytest.mark.parametrize(
    ("evidence_pass", "manifest_paths"),
    (
        ("models-and-backtests", MODEL_MANIFESTS + BACKTEST_MANIFESTS),
        ("2026-projection-fixtures", PROJECTION_MANIFESTS),
    ),
)
def test_evidence_pass_uses_one_shared_git_sha(
    evidence_pass: str, manifest_paths: tuple[Path, ...]
) -> None:
    shas = {str(_manifest_file(path)["git_sha"]) for path in manifest_paths}
    assert len(shas) == 1, f"{evidence_pass} carries mixed provenance: {sorted(shas)}"


@pytest.mark.parametrize("artifact_name", MODEL_ARTIFACTS)
def test_committed_model_evidence_has_clean_provenance_and_seed(
    artifact_name: str,
) -> None:
    artifact = ARTIFACTS_ROOT / "models" / artifact_name
    manifest = _manifest(artifact)

    assert (artifact / "report.md").is_file()
    _assert_clean_git_provenance(manifest, f"{artifact_name}/manifest.json")
    seeds = _values_for_key(manifest, "seed")
    assert seeds
    assert set(seeds) == {EXPECTED_SEED}


@pytest.mark.parametrize("artifact_name", BACKTEST_ARTIFACTS)
def test_committed_backtest_evidence_has_clean_provenance_and_version(
    artifact_name: str,
) -> None:
    artifact = ARTIFACTS_ROOT / "backtests" / artifact_name
    manifest = _manifest(artifact)

    assert (artifact / "report.md").is_file()
    _assert_clean_git_provenance(manifest, f"{artifact_name}/manifest.json")
    assert manifest["package_version"] == "0.1.0"
    assert manifest["config"]["seed"] == EXPECTED_SEED
    assert manifest["leakage_ok"] is True


def test_committed_game_win_evidence_discloses_zero_coverage_seasons() -> None:
    manifest = _manifest(ARTIFACTS_ROOT / "models" / "game-win")
    coverage = manifest["market_coverage_by_season"]

    assert coverage["2024"] == {
        "split": "validation",
        "priced_games": 0,
        "total_games": 1315,
        "coverage": 0.0,
        "uncovered": True,
    }
    assert coverage["2025"] == {
        "split": "test",
        "priced_games": 0,
        "total_games": 1311,
        "coverage": 0.0,
        "uncovered": True,
    }


def test_committed_backtests_preserve_corrected_league_evidence() -> None:
    historical = _manifest(ARTIFACTS_ROOT / "backtests" / "2023-2024-2025-seed20260827")
    combined = next(
        row
        for row in historical["league_comparisons"]
        if row["season"] == 2024 and row["draft_event"] == "R3_4"
    )
    manager_points = {
        manager["manager"]: manager["actual_points"] for manager in combined["managers"]
    }

    assert combined["league_mean_points"] == 55.25
    assert combined["league_best_points"] == 65.0
    assert manager_points["levi"] == 64.0

    current = _manifest(ARTIFACTS_ROOT / "backtests" / "2026-combined-r500-seed20260827")
    comparisons = current["league_comparisons"]
    assert len(comparisons) == 6
    assert {(row["draft_event"], row["league_name"]) for row in comparisons} == {
        (event, league)
        for event in ("R1", "R2", "R3_4")
        for league in ("Press Play-offs", "The Gemmell Cup")
    }
    assert all(len(row["managers"]) == 4 for row in comparisons)

    report = (
        ARTIFACTS_ROOT / "backtests" / "2026-combined-r500-seed20260827" / "report.md"
    ).read_text(encoding="utf-8")
    assert "| 2026 | 14 | 0.2339 | 0.4286 | 0.2500 |" in report

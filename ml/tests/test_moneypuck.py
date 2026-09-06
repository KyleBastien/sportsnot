"""MoneyPuck raw-archive integrity and aggregate reproducibility tests."""

from __future__ import annotations

import csv
import gzip
import hashlib
import re
import subprocess
import sys
from pathlib import Path

MONEYPUCK_DIR = Path(__file__).parents[1] / "data" / "raw" / "moneypuck"
SHOTS_DIR = MONEYPUCK_DIR / "shots"
SUMMARY_DIR = MONEYPUCK_DIR / "season-summary"
SUMMARY_HASHES_PATH = SUMMARY_DIR / "SHA256SUMS"
AGGREGATES_DIR = MONEYPUCK_DIR / "game-aggregates"
PROVENANCE_PATH = MONEYPUCK_DIR / "PROVENANCE.md"
AGGREGATE_SCRIPT = MONEYPUCK_DIR / "aggregate_shots.py"
PROVENANCE_HASH_ROW = re.compile(
    r"\| `(?P<name>(?:MoneyPuck[^`]+\.csv|shots_\d{4}\.zip))` "
    r"\|[^\n]*?\| `(?P<sha>[0-9a-f]{64})` \|"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def provenance_hashes() -> dict[str, str]:
    text = PROVENANCE_PATH.read_text(encoding="utf-8")
    return {
        match.group("name"): match.group("sha")
        for match in PROVENANCE_HASH_ROW.finditer(text)
    }


def test_committed_shot_files_match_provenance() -> None:
    expected = provenance_hashes()
    archives = sorted(SHOTS_DIR.glob("shots_*.zip"))
    dictionaries = sorted(SHOTS_DIR.glob("MoneyPuck*.csv"))
    committed = archives + dictionaries

    assert len(archives) == 19
    assert {path.name for path in committed} == set(expected)
    assert {path.name: sha256(path) for path in committed} == expected
    assert all(path.stat().st_size <= 45 * 1024 * 1024 for path in archives)


def test_committed_season_summaries_match_checksum_manifest() -> None:
    expected = {
        relative_path: digest
        for digest, relative_path in (
            line.split(maxsplit=1)
            for line in SUMMARY_HASHES_PATH.read_text(encoding="utf-8").splitlines()
        )
    }
    summaries = sorted(SUMMARY_DIR.glob("*/*/*.csv.gz"))
    relative_paths = [path.relative_to(SUMMARY_DIR).as_posix() for path in summaries]

    assert len(summaries) == 18 * 2 * 4
    assert set(relative_paths) == set(expected)
    actual = {
        relative: sha256(path)
        for relative, path in zip(relative_paths, summaries, strict=True)
    }
    assert actual == expected


def test_lockout_season_aggregates_rederive_byte_exact(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(AGGREGATE_SCRIPT),
            str(SHOTS_DIR),
            str(tmp_path),
            "2012",
        ],
        check=True,
    )

    expected_names = {
        "team-game-xg-2012-13.csv.gz",
        "skater-game-xg-2012-13.csv.gz",
        "goalie-game-2012-13.csv.gz",
    }
    assert {path.name for path in tmp_path.iterdir()} == expected_names
    for name in expected_names:
        assert (tmp_path / name).read_bytes() == (AGGREGATES_DIR / name).read_bytes()


def test_duplicate_source_events_count_once() -> None:
    aggregate_path = AGGREGATES_DIR / "team-game-xg-2007-08.csv.gz"
    with gzip.open(aggregate_path, "rt", encoding="utf-8", newline="") as handle:
        rows = {
            row["teamCode"]: int(row["allGoalsFor"])
            for row in csv.DictReader(handle)
            if row["gameId"] == "2007020001"
        }

    assert rows == {"ANA": 1, "L.A": 4}

"""Odds table build tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from draft_oracle.ingest.odds import build_odds_table, resolve_team_id
from tests.test_odds import _favorite_csv, _write_sbr_workbook


def test_build_odds_table_writes_parquet(tmp_path: Path) -> None:
    archive = tmp_path / "odds-archive"
    archive.mkdir()
    _write_sbr_workbook(
        archive / "nhl-odds-2016-17.xlsx",
        [
            [1012, 1, "V", "Toronto", 2, 2, 0, 4, 114, 121, 1.5, -245, 5.5, -110, 5.5, 105],
            [1012, 2, "H", "Ottawa", 2, 1, 1, 5, -134, -141, -1.5, 205, 5.5, -110, 5.5, -125],
        ],
    )
    out = tmp_path / "normalized"
    result = build_odds_table(archive_dir=archive, out_dir=out)
    assert result.game_rows == 1
    assert result.covered_rows == 1
    assert (out / "odds.parquet").exists()
    assert (out / "odds_by_source.parquet").exists()
    loaded = pd.read_parquet(out / "odds.parquet")
    assert len(loaded) == 1
    assert loaded.iloc[0]["home_team_id"] == resolve_team_id("Ottawa")


def test_build_odds_table_reports_unattributed_rows(tmp_path: Path) -> None:
    archive = tmp_path / "odds-archive"
    completion = archive / "espn-2025-26-completion"
    completion.mkdir(parents=True)
    frame = _favorite_csv(
        [
            {
                "game_id": 401874176,
                "date": "2026-06-15 00:00:00+00:00",
                "season": 2026,
                "team_name": "Vegas Golden Knights",
                "is_home": 1,
                "spread": float("nan"),
                "favorite_moneyline": -115,
            },
            {
                "game_id": 401874176,
                "date": "2026-06-15 00:00:00+00:00",
                "season": 2026,
                "team_name": "Carolina Hurricanes",
                "is_home": 0,
                "spread": float("nan"),
                "favorite_moneyline": -115,
            },
        ]
    )
    frame.to_csv(completion / "games.csv", index=False)

    result = build_odds_table(archive_dir=archive, out_dir=tmp_path / "normalized")

    assert result.unattributed_uncovered_rows == 1

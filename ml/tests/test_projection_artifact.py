"""Tests for draft_oracle.projection_artifact (US-017).

All fixtures are in-memory synthetic archives -- no network, no committed data
(SPEC section 7). The suite covers artifact assembly, automatic exclusion of teams
that are not in the round's bracket, injury flagging, byte-identical Parquet reruns
on the same snapshot, the run manifest contents, and the ``oracle project`` CLI.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from draft_oracle.cli.project import app
from draft_oracle.features.skater import FEATURE_SET_VERSION
from draft_oracle.ingest.injuries import (
    EspnInjuriesResponse,
    injuries_response_to_rows,
)
from draft_oracle.ingest.normalize import create_snapshot
from draft_oracle.models.skater_production import SkaterProductionConfig
from draft_oracle.projection_artifact import (
    _COMBINED_CHEATSHEET_NOTE,
    LIVE_PROJECTION_VERSION,
    SKATER_COLUMNS,
    TEAM_COLUMNS,
    ProjectArtifactConfig,
    build_projection_artifact,
    build_projection_artifact_from_normalized,
    write_projection_artifact,
)
from tests.projection_artifact_fixtures import (
    _PROJECT_ARTIFACT_CONFIG,
    _archive,
    _pre_round_archive,
)

# ── Core assembly ──────────────────────────────────────────────────────────


def test_build_projection_artifact_shapes_and_columns() -> None:
    sk, tg, players, series = _archive()
    result = build_projection_artifact(
        sk,
        players,
        tg,
        series,
        season=2022,
        playoff_round=1,
        snapshot_id="snap",
        config=_PROJECT_ARTIFACT_CONFIG,
    )
    assert list(result.skaters.columns) == list(SKATER_COLUMNS)
    assert list(result.teams.columns) == list(TEAM_COLUMNS)
    # Exactly the two teams in the round's only series appear.
    assert len(result.teams) == 2
    assert set(result.teams["team_abbrev"]) == {"AAA", "DDD"}
    assert result.manifest["counts"]["eligible_series"] == 1
    assert result.manifest["cli_flags"] == {
        "managers": 4,
        "ir": False,
        "seed": 20260827,
        "no_refresh": None,
        "slot_strategies": True,
        "slot_rollouts": 60,
        "combine_final_rounds": True,
        "n_sims": 300,
        "horizon": 7,
    }
    assert set(result.manifest["platform"]) == {
        "os",
        "os_release",
        "machine",
        "python",
        "numpy",
    }
    assert all(result.manifest["platform"].values())


def test_combined_cheatsheet_note_documents_team_column_contract() -> None:
    assert "e_goalie_points is combined R3+R4" in _COMBINED_CHEATSHEET_NOTE
    assert "e_wins, e_games, and e_shutout_wins remain R3-only" in (
        _COMBINED_CHEATSHEET_NOTE
    )


def test_round_one_has_no_combined_event() -> None:
    sk, tg, players, series = _archive()
    result = build_projection_artifact(
        sk,
        players,
        tg,
        series,
        season=2022,
        playoff_round=1,
        snapshot_id="snap",
        config=_PROJECT_ARTIFACT_CONFIG,
    )
    # Combined R3+R4 valuation only applies to the round-3 draft event.
    assert result.manifest["combined_event"] is None


def test_ineligible_teams_and_players_are_excluded() -> None:
    sk, tg, players, series = _archive()
    result = build_projection_artifact(
        sk,
        players,
        tg,
        series,
        season=2022,
        playoff_round=1,
        snapshot_id="snap",
        config=_PROJECT_ARTIFACT_CONFIG,
    )
    # BBB and CCC are not in the round-1 bracket -> excluded from both tables.
    assert "BBB" not in set(result.teams["team_abbrev"])
    assert "CCC" not in set(result.teams["team_abbrev"])
    assert set(result.skaters["team_abbrev"]).issubset({"AAA", "DDD"})
    assert (result.skaters["expected_points"] >= 0).all()
    assert (result.skaters["p10"] <= result.skaters["p90"]).all()


def test_series_win_probabilities_are_complementary() -> None:
    sk, tg, players, series = _archive()
    result = build_projection_artifact(
        sk,
        players,
        tg,
        series,
        season=2022,
        playoff_round=1,
        snapshot_id="snap",
        config=_PROJECT_ARTIFACT_CONFIG,
    )
    probs = result.teams.set_index("team_abbrev")["p_series_win"]
    assert probs["AAA"] + probs["DDD"] == pytest.approx(1.0)
    # The stronger top seed is favored.
    assert probs["AAA"] > probs["DDD"]


def test_injury_flag_is_set_from_injuries_table() -> None:
    sk, tg, players, series = _archive()
    injured_pid = 100  # AAA forward
    injuries = pd.DataFrame(
        [
            {
                "player_id": injured_pid,
                "player_name": "AAA-100",
                "position": "F",
                "status": "out",
            }
        ]
    )
    result = build_projection_artifact(
        sk,
        players,
        tg,
        series,
        season=2022,
        playoff_round=1,
        snapshot_id="snap",
        injuries=injuries,
        config=_PROJECT_ARTIFACT_CONFIG,
    )
    flagged = result.skaters.set_index("player_id")["injured"]
    assert bool(flagged.loc[injured_pid]) is True
    assert result.manifest["counts"]["skaters_injured"] >= 1
    others = result.skaters.loc[result.skaters["player_id"] != injured_pid, "injured"]
    assert not others.any()


def test_espn_mapped_injury_drives_flag_and_ir_stash() -> None:
    # M-11: the ESPN feed keys on athlete ids disjoint from NHL player ids. A
    # skater must be resolved by name + team to its NHL id before the injured
    # flag and _apply_ir_stash can fire. Here ESPN id 4900001 (~4-5M range) must
    # map to harness skater 100 (AAA forward) via injuries_response_to_rows.
    sk, tg, players, series = _archive()
    feed = {
        "injuries": [
            {
                "displayName": "AAA",
                "abbreviation": "AAA",
                "injuries": [
                    {
                        "status": "Injured Reserve",
                        "athlete": {
                            "id": "4900001",  # disjoint ESPN id, not the NHL 100
                            "fullName": "AAA-100",
                            "position": {"abbreviation": "C"},
                        },
                        "type": {"name": "INJURY_STATUS_INJURED_RESERVE"},
                        "details": {"type": "Lower Body", "returnDate": None},
                    }
                ],
            }
        ]
    }
    injuries = injuries_response_to_rows(EspnInjuriesResponse.model_validate(feed), players=players)
    # The disjoint ESPN id was mapped onto the NHL player id (100), not left as-is.
    assert set(injuries["player_id"]) == {100}
    assert set(injuries["espn_id"]) == {4900001}

    config = ProjectArtifactConfig(
        ir=True,
        seed=20260827,
        n_sims=300,
        production_config=SkaterProductionConfig(
            seed=20260827, n_val_seasons=1, n_test_seasons=1, min_confident_games=5
        ),
    )
    result = build_projection_artifact(
        sk,
        players,
        tg,
        series,
        season=2022,
        playoff_round=1,
        snapshot_id="snap",
        injuries=injuries,
        config=config,
    )
    flagged = result.skaters.set_index("player_id")["injured"]
    # Injured flag fires on the MAPPED NHL id, never the raw ESPN id.
    assert bool(flagged.loc[100]) is True
    assert 4900001 not in set(result.skaters["player_id"])
    # _apply_ir_stash valued the mapped injured skater (ir enabled).
    assert result.manifest["ir_stash"]["enabled"] is True
    assert result.manifest["ir_stash"]["candidates"] >= 1
    verdict = result.skaters.set_index("player_id")["ir_verdict"].loc[100]
    assert isinstance(verdict, str) and verdict != ""


def test_missing_round_raises() -> None:
    sk, tg, players, series = _archive()
    with pytest.raises(ValueError, match="no series found"):
        build_projection_artifact(
            sk,
            players,
            tg,
            series,
            season=2099,
            playoff_round=1,
            snapshot_id="x",
            config=_PROJECT_ARTIFACT_CONFIG,
        )


# ── Pre-round (M-1): build round N before round N starts ─────────────────────


def test_pre_round_artifact_builds_before_round_starts() -> None:
    # Archive has completed round-1 games (two series) and a round-2 bracket, but
    # NO round-2 games -- the moment the league actually drafts round 2. The cutoff
    # must derive from round-1's completion, not round-2's (absent) first game.
    sk, tg, players, series = _pre_round_archive([2018, 2019, 2020, 2021, 2022])
    result = build_projection_artifact(
        sk,
        players,
        tg,
        series,
        season=2022,
        playoff_round=2,
        snapshot_id="snap",
        config=_PROJECT_ARTIFACT_CONFIG,
    )
    # Exactly the two round-2 bracket teams are eligible.
    assert set(result.teams["team_abbrev"]) == {"AAA", "BBB"}
    assert set(result.skaters["team_abbrev"]).issubset({"AAA", "BBB"})
    assert result.manifest["counts"]["eligible_series"] == 1
    # The as-of cutoff is the day AFTER round-1's last game (2022-04-25), i.e. before
    # round 2 would start -- and no round-2 game exists in the archive at all.
    cutoff = pd.Timestamp(result.manifest["as_of_cutoff"])
    assert cutoff == pd.Timestamp("2022-04-26")
    played = tg.loc[(tg["season_id"] == 20212022) & (tg["game_type_id"] == 3), "game_date"]
    assert cutoff > pd.to_datetime(played).max()


def test_pre_round_cutoff_is_leak_safe() -> None:
    # The pre-round cutoff must remain strictly after every game used for training
    # (no round-2 leakage possible because none exists) and must exclude nothing that
    # belongs to round 1.
    sk, tg, players, series = _pre_round_archive([2018, 2019, 2020, 2021, 2022])
    result = build_projection_artifact(
        sk,
        players,
        tg,
        series,
        season=2022,
        playoff_round=2,
        snapshot_id="snap",
        config=_PROJECT_ARTIFACT_CONFIG,
    )
    cutoff = pd.Timestamp(result.manifest["as_of_cutoff"])
    round1_dates = pd.to_datetime(
        tg.loc[(tg["season_id"] == 20212022) & (tg["game_type_id"] == 3), "game_date"]
    )
    # Every round-1 game is available (strictly before the cutoff).
    assert (round1_dates < cutoff).all()


# ── Manifest ───────────────────────────────────────────────────────────────


def test_manifest_records_versions_seeds_and_snapshot() -> None:
    sk, tg, players, series = _archive()
    result = build_projection_artifact(
        sk,
        players,
        tg,
        series,
        season=2022,
        playoff_round=1,
        snapshot_id="snap-123",
        config=_PROJECT_ARTIFACT_CONFIG,
        git_sha="deadbeef",
        generated_at="2026-08-28T00:00:00+00:00",
    )
    m = result.manifest
    assert m["artifact_version"] == LIVE_PROJECTION_VERSION
    assert m["snapshot_id"] == "snap-123"
    assert m["git_sha"] == "deadbeef"
    assert isinstance(m["git_dirty"], bool)
    assert m["feature_version"] == FEATURE_SET_VERSION
    assert m["seeds"]["base"] == 20260827
    assert set(m["model_versions"]) == {
        "game_win",
        "shutout",
        "skater_production",
        "series_sim",
        "projection",
    }
    assert m["as_of_cutoff"].startswith("2022-04")


# ── Determinism / byte-identical reruns ────────────────────────────────────


def test_reruns_are_byte_identical_parquet(tmp_path: Path) -> None:
    sk, tg, players, series = _archive()

    def _run(sub: str) -> tuple[bytes, bytes]:
        result = build_projection_artifact(
            sk,
            players,
            tg,
            series,
            season=2022,
            playoff_round=1,
            snapshot_id="snap",
            config=_PROJECT_ARTIFACT_CONFIG,
            git_sha="sha",
            generated_at="2026-08-28T00:00:00+00:00",
        )
        out = write_projection_artifact(result, tmp_path / sub)
        return (
            (out / "skaters.parquet").read_bytes(),
            (out / "teams.parquet").read_bytes(),
        )

    sk_a, tm_a = _run("run_a")
    sk_b, tm_b = _run("run_b")
    assert sk_a == sk_b
    assert tm_a == tm_b


# ── From-normalized + CLI ──────────────────────────────────────────────────


def _write_normalized(dir_path: Path) -> None:
    sk, tg, players, series = _archive()
    dir_path.mkdir(parents=True, exist_ok=True)
    sk.to_parquet(dir_path / "skater_games.parquet", index=False)
    tg.to_parquet(dir_path / "team_games.parquet", index=False)
    players.to_parquet(dir_path / "players.parquet", index=False)
    series.to_parquet(dir_path / "series.parquet", index=False)


def test_from_normalized_writes_all_files(tmp_path: Path) -> None:
    normalized = tmp_path / "normalized"
    _write_normalized(normalized)
    result, out_dir = build_projection_artifact_from_normalized(
        season=2022,
        playoff_round=1,
        normalized_dir=normalized,
        artifacts_root=tmp_path / "artifacts",
        config=_PROJECT_ARTIFACT_CONFIG,
    )
    assert out_dir.name == "2022-r1"
    for fname in (
        "skaters.parquet",
        "skaters.csv",
        "teams.parquet",
        "teams.csv",
        "cheatsheet.md",
        "run_manifest.json",
    ):
        assert (out_dir / fname).exists()
    assert result.manifest["snapshot_id"] == "live"
    assert not result.cheatsheet.rows.empty
    assert result.manifest["scarcity"]["managers"] == 4
    assert (
        (out_dir / "cheatsheet.md")
        .read_text(encoding="utf-8")
        .startswith("# Draft Oracle cheat sheet")
    )


def test_pinned_run_reads_frozen_inputs_not_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # M-10: a pinned run must read every consumed input (injuries + league picks)
    # from the frozen snapshot so (snapshot, seed) fully determines the artifact --
    # the fitted-opponent league comparison is present and mutable live tables leak
    # nothing.
    import draft_oracle.projection_artifact as pa

    normalized = tmp_path / "normalized"
    _write_normalized(normalized)
    pd.DataFrame([{"team_id": 1, "team_abbrev": "AAA"}]).to_parquet(
        normalized / "teams.parquet", index=False
    )
    frozen_injuries = pd.DataFrame(
        [{"player_id": 100, "player_name": "AAA-100", "position": "F", "status": "out"}]
    )
    frozen_injuries.to_parquet(normalized / "injuries.parquet", index=False)
    frozen_picks = pd.DataFrame([{"manager": "kyle", "player_id": 100}])
    frozen_picks.to_parquet(normalized / "league_draft_picks.parquet", index=False)

    create_snapshot(out_dir=normalized, snapshot_id="pin1")

    # Corrupt the LIVE injuries and delete the LIVE league picks: any live read is
    # now observable (wrong player id) or would drop the fitted-opponent input.
    pd.DataFrame(
        [{"player_id": 999, "player_name": "X", "position": "F", "status": "out"}]
    ).to_parquet(normalized / "injuries.parquet", index=False)
    (normalized / "league_draft_picks.parquet").unlink()

    captured: dict[str, pd.DataFrame | None] = {}
    real = pa.build_projection_artifact

    def spy(*args: object, **kwargs: object) -> object:
        captured["injuries"] = kwargs.get("injuries")  # type: ignore[assignment]
        captured["league_picks"] = kwargs.get("league_picks")  # type: ignore[assignment]
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(pa, "build_projection_artifact", spy)

    result, _ = build_projection_artifact_from_normalized(
        season=2022,
        playoff_round=1,
        normalized_dir=normalized,
        artifacts_root=tmp_path / "artifacts",
        snapshot="pin1",
        config=_PROJECT_ARTIFACT_CONFIG,
    )

    # Injuries came from the frozen snapshot (player 100), NOT the mutated live 999.
    assert captured["injuries"] is not None
    assert set(captured["injuries"]["player_id"]) == {100}
    # The fitted-opponent league picks are present under the pin though the live
    # file was deleted -- no silent greedy fallback.
    assert captured["league_picks"] is not None
    assert not captured["league_picks"].empty
    assert result.manifest["snapshot_id"] == "pin1"


def test_pinned_run_on_incomplete_snapshot_fails_loudly(tmp_path: Path) -> None:
    # A legacy snapshot froze only the core tables (no 'complete' marker); a pin
    # against it must raise rather than silently read live odds/injuries (M-10).
    normalized = tmp_path / "normalized"
    _write_normalized(normalized)
    snap_dir = normalized / "snapshots" / "legacy"
    snap_dir.mkdir(parents=True)
    for name in ("skater_games", "team_games", "series", "players"):
        shutil.copy(normalized / f"{name}.parquet", snap_dir / f"{name}.parquet")
    (snap_dir / "_manifest.json").write_text(
        json.dumps({"snapshot_id": "legacy"}), encoding="utf-8"
    )

    with pytest.raises(RuntimeError, match="complete-snapshot"):
        build_projection_artifact_from_normalized(
            season=2022,
            playoff_round=1,
            normalized_dir=normalized,
            artifacts_root=tmp_path / "artifacts",
            snapshot="legacy",
            config=_PROJECT_ARTIFACT_CONFIG,
        )


def test_pinned_run_without_snapshot_manifest_fails_loudly(tmp_path: Path) -> None:
    # A snapshot directory with no manifest at all is not a valid pin.
    normalized = tmp_path / "normalized"
    _write_normalized(normalized)
    snap_dir = normalized / "snapshots" / "bare"
    snap_dir.mkdir(parents=True)
    for name in ("skater_games", "team_games", "series", "players"):
        shutil.copy(normalized / f"{name}.parquet", snap_dir / f"{name}.parquet")

    with pytest.raises(FileNotFoundError, match=r"_manifest\.json"):
        build_projection_artifact_from_normalized(
            season=2022,
            playoff_round=1,
            normalized_dir=normalized,
            artifacts_root=tmp_path / "artifacts",
            snapshot="bare",
            config=_PROJECT_ARTIFACT_CONFIG,
        )


def test_slot_strategies_skipped_when_pool_too_small() -> None:
    # The synthetic archive has only two eligible teams (a handful of assets), which
    # cannot fill a 4-manager league -- the report is skipped gracefully, not crashed.
    sk, tg, players, series = _archive()
    result = build_projection_artifact(
        sk,
        players,
        tg,
        series,
        season=2022,
        playoff_round=1,
        snapshot_id="snap",
        config=_PROJECT_ARTIFACT_CONFIG,
    )
    assert result.slot_strategies is None
    assert result.manifest["slot_strategies"] is None
    assert any("slot strategies skipped" in w for w in result.manifest["warnings"])


def test_slot_strategies_disabled_writes_no_file(tmp_path: Path) -> None:
    sk, tg, players, series = _archive()
    config = ProjectArtifactConfig(
        seed=20260827,
        n_sims=300,
        slot_strategies=False,
        production_config=SkaterProductionConfig(
            seed=20260827, n_val_seasons=1, n_test_seasons=1, min_confident_games=5
        ),
    )
    result = build_projection_artifact(
        sk, players, tg, series, season=2022, playoff_round=1, snapshot_id="snap", config=config
    )
    assert result.slot_strategies is None
    assert result.manifest["slot_strategies"] is None
    out = write_projection_artifact(result, tmp_path / "art")
    assert not (out / "slot_strategies.md").exists()


def test_cli_project_runs_offline(tmp_path: Path) -> None:
    normalized = tmp_path / "normalized"
    _write_normalized(normalized)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "--season",
            "2022",
            "--round",
            "1",
            "--normalized-dir",
            str(normalized),
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--no-refresh",
            "--no-slot-strategies",
            "--slot-rollouts",
            "17",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Projection artifact ->" in result.output
    assert (tmp_path / "artifacts" / "2022-r1" / "skaters.parquet").exists()
    manifest = json.loads(
        (tmp_path / "artifacts" / "2022-r1" / "run_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["cli_flags"]["no_refresh"] is True
    assert manifest["cli_flags"]["slot_strategies"] is False
    assert manifest["cli_flags"]["slot_rollouts"] == 17

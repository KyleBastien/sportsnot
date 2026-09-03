"""Tests for draft_oracle.backtest.report (US-026).

The metric aggregation (projection MAE/rho, series Brier on both tracks, strategy
win rate, league comparison) is exercised on hand-built in-memory results so the
numbers are exact and the tests stay fast. One integration test runs the real replay
on a synthetic archive with odds + league picks to prove the report wires end-to-end.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from draft_oracle.backtest.replay import (
    BacktestConfig,
    BacktestResult,
    LeagueComparison,
    LeagueManagerRoster,
    ProjectionEval,
    RoundResult,
    SeriesEval,
    SlotResult,
    run_backtest,
)
from draft_oracle.backtest.report import (
    _fmt,
    _pct,
    _projection_accuracy,
    _series_calibration,
    _strategy_summaries,
    build_backtest_report,
    write_report,
)
from tests.test_backtest import SERIES_PAIRS, TEAMS, _config, _tables

# ── Hand-built fixtures ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class _RoundInput:
    skaters: list[tuple[int, float, float]]
    teams: list[tuple[int, float, float]]
    series: list[SeriesEval]
    slots: list[SlotResult]
    season: int = 2022
    playoff_round: int = 1


def _round(spec: _RoundInput) -> RoundResult:
    return RoundResult(
        season=spec.season,
        season_id=spec.season * 10001,
        playoff_round=spec.playoff_round,
        as_of_cutoff=f"{spec.season}-04-15",
        opponents_kind="greedy",
        eligible_team_abbrevs=["AAA", "BBB"],
        leakage_ok=True,
        slot_results=spec.slots,
        warnings=[],
        projection_eval=ProjectionEval(skaters=spec.skaters, teams=spec.teams),
        series_evals=spec.series,
    )


def _slot(strategy: str, seat: int, oracle_points: float, opp: list[float]) -> SlotResult:
    return SlotResult(
        strategy=strategy,
        seat=seat,
        oracle_manager=f"seat{seat}",
        draft_index=0,
        oracle_points=oracle_points,
        opponent_points={f"opp{i}": v for i, v in enumerate(opp)},
        roster_keys=[],
    )


def _result(
    rounds: list[RoundResult], *, league: list[LeagueComparison] | None = None
) -> BacktestResult:
    config = BacktestConfig(strategies=("oracle", "greedy_vor", "random_legal"))
    return BacktestResult(
        run_id="test-run",
        seasons=sorted({r.season for r in rounds}),
        config=config,
        rounds=rounds,
        generated_at="2026-08-28T00:00:00Z",
        league_comparisons=league or [],
    )


# ── Formatting helpers ──────────────────────────────────────────────────────


def test_fmt_and_pct_handle_nan() -> None:
    assert _fmt(float("nan")) == "n/a"
    assert _fmt(1.23456, 2) == "1.23"
    assert _pct(float("nan")) == "n/a"
    assert _pct(0.5) == "50.0%"


# ── Projection accuracy ─────────────────────────────────────────────────────


def test_projection_accuracy_pools_pairs() -> None:
    rnd = _round(
        _RoundInput(
            skaters=[(1, 10.0, 8.0), (2, 4.0, 6.0), (3, 1.0, 0.0)],
            teams=[(101, 3.0, 4.0), (102, 1.0, 0.0)],
            series=[],
            slots=[],
        )
    )
    acc = _projection_accuracy("ALL", [rnd])
    assert acc.skater_n == 3
    assert acc.team_n == 2
    # MAE = mean(|10-8|,|4-6|,|1-0|) = (2+2+1)/3
    assert abs(acc.skater_mae - (5.0 / 3.0)) < 1e-9
    # Predictions monotonic with actuals here -> positive rank correlation.
    assert acc.skater_spearman > 0.0


# ── Series Brier, two tracks ────────────────────────────────────────────────


def test_series_calibration_two_tracks() -> None:
    series = [
        SeriesEval(1, 2, "AAA", "BBB", top_won=1, p_top_stat=0.8, p_top_market=0.7),
        SeriesEval(3, 4, "CCC", "DDD", top_won=0, p_top_stat=0.4, p_top_market=None),
    ]
    rnd = _round(_RoundInput(skaters=[], teams=[], series=series, slots=[]))
    cal = _series_calibration("ALL", [rnd])
    # Stat track scores both series; market track only the one with odds.
    assert cal.stat_n == 2
    assert cal.market_n == 1
    # Stat Brier = mean((0.8-1)^2, (0.4-0)^2) = (0.04 + 0.16)/2 = 0.10
    assert abs(cal.stat_brier - 0.10) < 1e-9
    # Market Brier = (0.7-1)^2 = 0.09
    assert abs(cal.market_brier - 0.09) < 1e-9


# ── Strategy summaries + win rate ───────────────────────────────────────────


def test_strategy_summaries_and_win_rate() -> None:
    rnd = _round(
        _RoundInput(
            skaters=[],
            teams=[],
            series=[],
            slots=[
                _slot("oracle", 1, 20.0, [10.0, 15.0]),  # win
                _slot("oracle", 2, 5.0, [10.0, 15.0]),  # loss
                _slot("greedy_vor", 1, 8.0, [10.0, 15.0]),  # loss
                _slot("random_legal", 1, 30.0, [10.0, 15.0]),  # win
            ],
        )
    )
    result = _result([rnd])
    summaries = {s.strategy: s for s in _strategy_summaries(result)}
    assert summaries["oracle"].win_rate == 0.5
    assert summaries["oracle"].mean_points == 12.5
    assert summaries["greedy_vor"].win_rate == 0.0


# ── Full report assembly ────────────────────────────────────────────────────


def test_report_has_all_sections_and_league_comparison(tmp_path: Path) -> None:
    rnd = _round(
        _RoundInput(
            skaters=[(1, 10.0, 8.0), (2, 4.0, 6.0)],
            teams=[(101, 3.0, 4.0)],
            series=[
                SeriesEval(1, 2, "AAA", "BBB", top_won=1, p_top_stat=0.8, p_top_market=0.7)
            ],
            slots=[_slot("oracle", 1, 20.0, [10.0])],
        )
    )
    league = [
        LeagueComparison(
            season=2022,
            playoff_round=1,
            draft_event="R1",
            managers=[
                LeagueManagerRoster("kyle", 25.0),
                LeagueManagerRoster("ben", 18.0),
            ],
            oracle_mean_points=20.0,
            oracle_best_points=22.0,
            league_name="The Gemmell Cup",
        )
    ]
    result = _result([rnd], league=league)
    report = build_backtest_report(result)
    text = report.markdown()
    assert "# Backtest report" in text
    assert "## Projection accuracy" in text
    assert "## Series-model calibration" in text
    assert "## Draft strategy vs. baselines" in text
    assert "## League comparison" in text
    assert "each league is reported separately" in text
    assert "The Gemmell Cup" in text
    assert "kyle" in text and "ben" in text
    # The run-parameter provenance note states rollouts/drafts and the honest under-run.
    assert "**Run parameters.**" in text
    assert "rollouts" in text and "under-samples" in text
    # The written file round-trips.
    path = write_report(result, tmp_path)
    assert path.exists()
    assert path.read_text(encoding="utf-8") == text


def test_league_section_notes_absence_when_no_overlap() -> None:
    rnd = _round(_RoundInput(skaters=[], teams=[], series=[], slots=[]))
    result = _result([rnd])
    text = build_backtest_report(result).markdown()
    assert "No backtested season overlapped" in text


# ── End-to-end via the replay engine ────────────────────────────────────────


def _synthetic_odds(season: int = 2022) -> pd.DataFrame:
    """Playoff odds for the round-1 series, favouring each top seed at home and away."""
    rows: list[dict[str, object]] = []
    for top, bottom in SERIES_PAIRS:
        top_id = TEAMS.index(top) + 1
        bottom_id = TEAMS.index(bottom) + 1
        rows.append(
            {
                "season_end_year": season,
                "game_date": f"{season}-04-16",
                "is_playoff": True,
                "home_team_id": top_id,
                "away_team_id": bottom_id,
                "home_implied": 0.62,
                "away_implied": 0.38,
            }
        )
        rows.append(
            {
                "season_end_year": season,
                "game_date": f"{season}-04-18",
                "is_playoff": True,
                "home_team_id": bottom_id,
                "away_team_id": top_id,
                "home_implied": 0.55,
                "away_implied": 0.45,
            }
        )
    return pd.DataFrame(rows)


def _synthetic_league_picks(season: int = 2022) -> pd.DataFrame:
    """A real 4-manager R1 draft over the round's teams for the league comparison."""
    rows: list[dict[str, object]] = []
    managers = ["kyle", "ben", "levi", "judah"]
    top_teams = [TEAMS.index(t) + 1 for t, _ in SERIES_PAIRS]  # 4 winning teams
    for m_idx, manager in enumerate(managers):
        rows.append(
            {
                "season": season,
                "draft_event": "R1",
                "manager": manager,
                "position": "G",
                "player_id": pd.NA,
                "team_id": top_teams[m_idx],
                "snake_slot": m_idx + 1,
            }
        )
    return pd.DataFrame(rows)


def test_end_to_end_report_captures_evals_and_market_and_league() -> None:
    tables = _tables()
    result = run_backtest(
        tables,
        [2022],
        odds=_synthetic_odds(),
        league_picks=_synthetic_league_picks(),
        config=_config(strategies=("oracle", "greedy_vor", "random_legal")),
    )
    rnd = result.rounds[0]
    assert rnd.projection_eval is not None
    assert rnd.projection_eval.skaters  # skaters were projected + scored
    assert rnd.series_evals  # series captured
    # Odds cover every round-1 series -> market track populated.
    assert all(ev.p_top_market is not None for ev in rnd.series_evals)
    # League picks overlap season 2022 round 1 -> a comparison exists.
    assert result.league_comparisons
    comp = result.league_comparisons[0]
    assert comp.draft_event == "R1"
    assert {m.manager for m in comp.managers} == {"kyle", "ben", "levi", "judah"}

    text = build_backtest_report(result).markdown()
    cal = _series_calibration("ALL", result.rounds)
    assert cal.market_n == len(rnd.series_evals)
    assert "market-aware" in text

"""Backtest reporting (US-026).

Turns a :class:`~draft_oracle.backtest.replay.BacktestResult` into a committed,
self-contained ``report.md`` so the tool's edge can be *inspected*, not assumed:

1. **Projection accuracy** — per season and in aggregate: skater and team projection
   MAE and Spearman rank correlation against the realized round points.
2. **Series-model calibration** — the series win model's Brier score on two tracks:
   *stat-only* (the probabilities the artifact actually drafted from, scored on every
   series) and *market-aware* (a post-hoc probability from the series' game-1 pre-series
   de-vigged betting line, scored only where historical odds exist), each against the
   higher-seed and coin-flip baselines.
3. **Draft strategy vs. baselines** — the multi-step oracle's actual roster points and
   win rate against the greedy-VOR, one-step-lookahead, and random-legal baselines,
   broken out per snake slot.
4. **League comparison** — where a backtested season overlaps the league's real drafts,
   the oracle's simulated roster points vs. what the league's managers actually drafted.

Every metric is reported truthfully: a baseline the oracle fails to beat, or a
projection that misses, is printed with its honest number (SPEC section 7). The report
consumes only the in-memory result (which already paired projections with actuals under
the leakage guard) — it never fetches data or trains a model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from draft_oracle import __version__
from draft_oracle.backtest.replay import BacktestResult, RoundResult, SlotResult
from draft_oracle.models.game_win import brier_score
from draft_oracle.models.skater_production import mean_absolute_error, spearman_correlation

__all__ = [
    "BacktestReport",
    "build_backtest_report",
    "write_report",
]


# ── Formatting helpers ──────────────────────────────────────────────────────


def _fmt(value: float, digits: int = 3) -> str:
    """Fixed-point string, or ``n/a`` for a missing/NaN value."""
    if _missing_number(value):
        return "n/a"
    return f"{value:.{digits}f}"


def _pct(value: float) -> str:
    """Percentage string, or ``n/a`` for a missing/NaN value."""
    if _missing_number(value):
        return "n/a"
    return f"{value * 100:.1f}%"


def _missing_number(value: float | None) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    """Render a GitHub-flavoured Markdown table (ASCII, cp1252-safe)."""
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


# ── Metric aggregation ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProjectionAccuracy:
    """Projection MAE + Spearman rank correlation for one scope (season or aggregate)."""

    label: str
    skater_n: int
    skater_mae: float
    skater_spearman: float
    team_n: int
    team_mae: float
    team_spearman: float


def _projection_accuracy(label: str, rounds: list[RoundResult]) -> ProjectionAccuracy:
    """Pool every projection/actual pair across ``rounds`` and score it."""
    sk_pred: list[float] = []
    sk_true: list[float] = []
    tm_pred: list[float] = []
    tm_true: list[float] = []
    for rnd in rounds:
        if rnd.projection_eval is None:
            continue
        for _pid, proj, actual in rnd.projection_eval.skaters:
            sk_pred.append(proj)
            sk_true.append(actual)
        for _tid, proj, actual in rnd.projection_eval.teams:
            tm_pred.append(proj)
            tm_true.append(actual)
    return ProjectionAccuracy(
        label=label,
        skater_n=len(sk_pred),
        skater_mae=mean_absolute_error(sk_pred, sk_true),
        skater_spearman=spearman_correlation(sk_pred, sk_true),
        team_n=len(tm_pred),
        team_mae=mean_absolute_error(tm_pred, tm_true),
        team_spearman=spearman_correlation(tm_pred, tm_true),
    )


@dataclass(frozen=True)
class SeriesCalibration:
    """Series-model Brier scores + baselines for one scope, both tracks."""

    label: str
    stat_n: int
    stat_brier: float
    stat_higher_seed: float
    stat_coin: float
    market_n: int
    market_brier: float
    market_higher_seed: float
    market_coin: float


def _series_calibration(label: str, rounds: list[RoundResult]) -> SeriesCalibration:
    """Brier the stat-only (all series) and market-aware (odds-covered) tracks."""
    stat_pred: list[float] = []
    stat_true: list[float] = []
    market_pred: list[float] = []
    market_true: list[float] = []
    for rnd in rounds:
        for ev in rnd.series_evals:
            stat_pred.append(ev.p_top_stat)
            stat_true.append(float(ev.top_won))
            if ev.p_top_market is not None:
                market_pred.append(ev.p_top_market)
                market_true.append(float(ev.top_won))

    def briers(pred: list[float], true: list[float]) -> tuple[float, float, float]:
        if not pred:
            return float("nan"), float("nan"), float("nan")
        model = brier_score(pred, true)
        higher = brier_score([1.0] * len(true), true)
        coin = brier_score([0.5] * len(true), true)
        return model, higher, coin

    s_model, s_higher, s_coin = briers(stat_pred, stat_true)
    m_model, m_higher, m_coin = briers(market_pred, market_true)
    return SeriesCalibration(
        label=label,
        stat_n=len(stat_pred),
        stat_brier=s_model,
        stat_higher_seed=s_higher,
        stat_coin=s_coin,
        market_n=len(market_pred),
        market_brier=m_model,
        market_higher_seed=m_higher,
        market_coin=m_coin,
    )


@dataclass(frozen=True)
class StrategySummary:
    """Actual-points and win-rate summary for one draft strategy."""

    strategy: str
    drafts: int
    mean_points: float
    win_rate: float


def _strategy_summaries(result: BacktestResult) -> list[StrategySummary]:
    """Aggregate every strategy's roster points + win rate across all rounds/slots."""
    summaries: list[StrategySummary] = []
    for strategy in result.config.strategies:
        slots = [s for rnd in result.rounds for s in rnd.slot_results if s.strategy == strategy]
        if not slots:
            continue
        summaries.append(
            StrategySummary(
                strategy=strategy,
                drafts=len(slots),
                mean_points=_mean([s.oracle_points for s in slots]),
                win_rate=_mean([1.0 if s.is_win else 0.0 for s in slots]),
            )
        )
    return summaries


def _oracle_by_seat(result: BacktestResult) -> list[tuple[int, int, float, float]]:
    """Per snake slot: ``(seat, drafts, mean_points, win_rate)`` for the oracle policy."""
    by_seat: dict[int, list[SlotResult]] = {}
    for rnd in result.rounds:
        for slot in rnd.slot_results:
            if slot.strategy != "oracle":
                continue
            by_seat.setdefault(slot.seat, []).append(slot)
    rows: list[tuple[int, int, float, float]] = []
    for seat in sorted(by_seat):
        slots = by_seat[seat]
        rows.append(
            (
                seat,
                len(slots),
                _mean([s.oracle_points for s in slots]),
                _mean([1.0 if s.is_win else 0.0 for s in slots]),
            )
        )
    return rows


# ── Report assembly ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BacktestReport:
    """A fully-rendered backtest report (Markdown lines)."""

    result: BacktestResult
    lines: list[str]

    def markdown(self) -> str:
        return "\n".join(self.lines) + "\n"


def _rounds_by_season(result: BacktestResult) -> dict[int, list[RoundResult]]:
    by_season: dict[int, list[RoundResult]] = {}
    for rnd in result.rounds:
        by_season.setdefault(rnd.season, []).append(rnd)
    return by_season


def _header_lines(result: BacktestResult) -> list[str]:
    cfg = result.config
    leakage_ok = all(r.leakage_ok for r in result.rounds)
    return [
        f"# Backtest report — run `{result.run_id}`",
        "",
        f"- Package version: {__version__}",
        f"- Generated: {result.generated_at}",
        f"- Seasons: {', '.join(str(s) for s in result.seasons)}",
        f"- Rounds replayed: {len(result.rounds)}",
        f"- League size: {cfg.managers} managers; IR slots: {cfg.ir}",
        f"- Strategies: {', '.join(cfg.strategies)}; drafts/slot: {cfg.n_drafts}; "
        f"rollouts: {cfg.rollouts}; seed: {cfg.seed}",
        f"- Leakage guard (all rounds pass): **{leakage_ok}**",
        "",
        "Projections drive every pick; the actual historical results only ever score a "
        "roster, never inform a pick. All numbers below are reported truthfully — a "
        "baseline the oracle fails to beat is printed with its honest value.",
        "",
        f"**Run parameters.** Each of the {len(result.rounds)} replayed rounds first "
        "rebuilds the full as-of projection artifact (retraining every model on only "
        f"pre-cutoff data), then seats {len(cfg.strategies)} strategies in each of the "
        f"{cfg.managers} snake slots for {cfg.n_drafts} seeded draft(s), each oracle "
        f"pick averaged over {cfg.rollouts} Monte-Carlo rollouts. The recommend-command "
        "design targets (>=500 rollouts / >=200 single-decision drafts, README) are "
        "measured at a single fixed state; applying them here would multiply the "
        "per-round retraining cost across every round and season, so this whole-replay "
        f"run deliberately under-samples them at {cfg.rollouts} rollouts / {cfg.n_drafts} "
        "draft(s) per slot to stay tractable. The league-comparison headline (M-6) scores "
        "fixed real and oracle rosters through the rules engine and is deterministic — "
        "unaffected by the rollout count; only the oracle mean-points / win-rate "
        "precision tightens with more rollouts.",
    ]


def _projection_section(result: BacktestResult) -> list[str]:
    by_season = _rounds_by_season(result)
    accuracies = [
        _projection_accuracy(str(season), by_season[season]) for season in sorted(by_season)
    ]
    accuracies.append(_projection_accuracy("ALL", result.rounds))
    rows = [
        [
            acc.label,
            str(acc.skater_n),
            _fmt(acc.skater_mae),
            _fmt(acc.skater_spearman),
            str(acc.team_n),
            _fmt(acc.team_mae),
            _fmt(acc.team_spearman),
        ]
        for acc in accuracies
    ]
    return [
        "## Projection accuracy",
        "",
        "MAE is mean absolute error of projected vs. actual round fantasy points (lower "
        "is better); rho is Spearman rank correlation (higher is better). Skaters are "
        "scored on projected round points; teams on projected goalie-slot points.",
        "",
        *_table(
            ["Season", "Skaters n", "Skater MAE", "Skater rho", "Teams n", "Team MAE", "Team rho"],
            rows,
        ),
    ]


def _series_section(result: BacktestResult) -> list[str]:
    by_season = _rounds_by_season(result)
    cals = [_series_calibration(str(season), by_season[season]) for season in sorted(by_season)]
    cals.append(_series_calibration("ALL", result.rounds))
    stat_rows = [
        [
            cal.label,
            str(cal.stat_n),
            _fmt(cal.stat_brier, 4),
            _fmt(cal.stat_higher_seed, 4),
            _fmt(cal.stat_coin, 4),
        ]
        for cal in cals
    ]
    market_rows = [
        [
            cal.label,
            str(cal.market_n),
            _fmt(cal.market_brier, 4),
            _fmt(cal.market_higher_seed, 4),
            _fmt(cal.market_coin, 4),
        ]
        for cal in cals
    ]
    aggregate = cals[-1]
    beats_stat = (
        not math.isnan(aggregate.stat_brier)
        and aggregate.stat_brier < aggregate.stat_higher_seed
        and aggregate.stat_brier < aggregate.stat_coin
    )
    market_note = (
        "No committed odds covered these series, so the market-aware track is empty."
        if aggregate.market_n == 0
        else (
            "The market-aware probability is derived post-hoc from the series' game-1 "
            "pre-series de-vigged betting line (an as-of-round-start benchmark) for "
            "calibration only — it is never used to make a pick."
        )
    )
    stat_header = ["Season", "Series n", "Series model", "Higher seed=1", "Coin flip=0.5"]
    return [
        "## Series-model calibration (Brier score, lower is better)",
        "",
        "Track 1 — **stat-only** (the probabilities the projection artifact actually "
        "drafted from), scored on every series:",
        "",
        *_table(stat_header, stat_rows),
        "",
        f"Aggregate stat-only series model beats both baselines: **{beats_stat}**.",
        "",
        "Track 2 — **market-aware** (post-hoc, series' game-1 pre-series de-vigged "
        "betting line), scored where historical odds exist:",
        "",
        *_table(stat_header, market_rows),
        "",
        market_note,
    ]


def _strategy_section(result: BacktestResult) -> list[str]:
    summaries = _strategy_summaries(result)
    rows = [
        [
            s.strategy,
            str(s.drafts),
            _fmt(s.mean_points, 2),
            _pct(s.win_rate),
        ]
        for s in summaries
    ]
    seat_rows = [
        [str(seat), str(drafts), _fmt(mean_pts, 2), _pct(win_rate)]
        for seat, drafts, mean_pts, win_rate in _oracle_by_seat(result)
    ]
    oracle = next((s for s in summaries if s.strategy == "oracle"), None)
    lines = [
        "## Draft strategy vs. baselines",
        "",
        "Mean actual roster points and win rate (fraction of drafts where the roster "
        "strictly outscored every opponent), pooled across every snake slot and round.",
        "",
        *_table(["Strategy", "Drafts", "Mean points", "Win rate"], rows),
    ]
    if oracle is not None:
        beats = [
            s.strategy
            for s in summaries
            if s.strategy != "oracle" and oracle.mean_points > s.mean_points
        ]
        lines += [
            "",
            f"Oracle mean-points beats: {', '.join(beats) if beats else 'none'}.",
        ]
    lines += [
        "",
        "### Oracle by snake slot",
        "",
        *_table(["Seat", "Drafts", "Mean points", "Win rate"], seat_rows),
    ]
    return lines


def _league_section(result: BacktestResult) -> list[str]:
    if not result.league_comparisons:
        return [
            "## League comparison",
            "",
            "No backtested season overlapped the committed league draft history, so there "
            "is nothing to compare against the league's real rosters.",
        ]
    rows: list[list[str]] = []
    manager_rows: list[list[str]] = []
    for comp in result.league_comparisons:
        rows.append(
            [
                str(comp.season),
                comp.league_name or "(unspecified)",
                f"r{comp.playoff_round} ({comp.draft_event})",
                _fmt(comp.oracle_mean_points, 2),
                _fmt(comp.oracle_best_points, 2),
                _fmt(comp.league_mean_points, 2),
                _fmt(comp.league_best_points, 2),
            ]
        )
        managers = "; ".join(f"{m.manager} {_fmt(m.actual_points, 1)}" for m in comp.managers)
        manager_rows.append(
            [
                str(comp.season),
                comp.league_name or "(unspecified)",
                f"r{comp.playoff_round}",
                managers,
            ]
        )
    return [
        "## League comparison",
        "",
        "Where a backtested season overlaps the league's real drafts, the oracle's "
        "simulated roster points (mean/best across snake slots) vs. what the league's "
        "managers actually drafted, all scored through the same rules engine. The "
        "combined `R3_4` draft is scored across both the conference final and the Cup "
        "Final, matching how the league drafts once for rounds 3+4. When history has "
        "multiple leagues in one season/event, each league is reported separately; "
        "manager rosters and league aggregates never pool across leagues.",
        "",
        *_table(
            [
                "Season",
                "League",
                "Round",
                "Oracle mean",
                "Oracle best",
                "League mean",
                "League best",
            ],
            rows,
        ),
        "",
        "### Real league rosters (actual points)",
        "",
        *_table(["Season", "League", "Round", "Managers (points)"], manager_rows),
    ]


def build_backtest_report(result: BacktestResult) -> BacktestReport:
    """Assemble the full Markdown report from a completed backtest run."""
    lines: list[str] = []
    lines += _header_lines(result)
    lines += ["", *_projection_section(result)]
    lines += ["", *_series_section(result)]
    lines += ["", *_strategy_section(result)]
    lines += ["", *_league_section(result)]
    return BacktestReport(result=result, lines=lines)


def write_report(result: BacktestResult, out_dir: Path) -> Path:
    """Render the report and write it to ``out_dir/report.md`` (committed artifact)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    report = build_backtest_report(result)
    path = out_dir / "report.md"
    path.write_text(report.markdown(), encoding="utf-8")
    return path

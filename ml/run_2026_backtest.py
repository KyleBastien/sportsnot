"""One-off: high-quality (slowest, best) 2025-2026 playoff backtest for a 4-team league.

Mirrors the committed 2023-2024-2025 historical example (same four strategies + seed)
so the runs are directly comparable, but maxes out the accuracy knobs instead of the
speed-tuned defaults: rollouts=1000, max_candidates=24, n_drafts=32, full depth.
"""

from draft_oracle.backtest.replay import BacktestConfig, run_backtest_from_normalized

config = BacktestConfig(
    seed=20260827,
    managers=4,
    ir=False,  # 2026 league disabled IR (SPEC §2)
    n_drafts=8,
    rollouts=500,
    max_candidates=24,
    depth=None,  # full-depth multi-step rollout
    strategies=("oracle", "greedy_vor", "one_step", "random_legal"),
    run_id="2026-combined-r500-seed20260827",
)

result, out_dir = run_backtest_from_normalized(seasons=[2026], config=config)

print(f"run_id: {result.run_id}")
print(f"out_dir: {out_dir}")
print(f"report: {out_dir / 'report.md'}")
print(f"rounds replayed: {len(result.rounds)}")
print(f"leakage_ok (all rounds): {all(r.leakage_ok for r in result.rounds)}")

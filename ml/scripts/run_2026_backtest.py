"""Run high-quality 2026 playoff backtest with 500 rollouts and eight drafts per slot.

Uses four strategies, 24 candidates, and full-depth rollouts. Config matches committed
``2026-combined-r500-seed20260827`` run id.
"""

from draft_oracle.backtest.replay import BacktestConfig, run_backtest_from_normalized


def main() -> None:
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
    print(
        f"leakage_ok (all rounds): {all(round_result.leakage_ok for round_result in result.rounds)}"
    )


if __name__ == "__main__":
    main()

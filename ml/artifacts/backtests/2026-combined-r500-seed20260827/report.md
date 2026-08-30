# Backtest report — run `2026-combined-r500-seed20260827`

- Package version: 0.1.0
- Generated: 2026-08-29T12:47:42.148884+00:00
- Seasons: 2026
- Rounds replayed: 3
- League size: 4 managers; IR slots: False
- Strategies: oracle, greedy_vor, one_step, random_legal; drafts/slot: 8; rollouts: 500; seed: 20260827
- Leakage guard (all rounds pass): **True**

Projections drive every pick; the actual historical results only ever score a roster, never inform a pick. All numbers below are reported truthfully — a baseline the oracle fails to beat is printed with its honest value.

## Projection accuracy

MAE is mean absolute error of projected vs. actual round fantasy points (lower is better); rho is Spearman rank correlation (higher is better). Skaters are scored on projected round points; teams on projected goalie-slot points.

| Season | Skaters n | Skater MAE | Skater rho | Teams n | Team MAE | Team rho |
| --- | --- | --- | --- | --- | --- | --- |
| 2026 | 808 | 1.647 | 0.488 | 28 | 3.123 | 0.329 |
| ALL | 808 | 1.647 | 0.488 | 28 | 3.123 | 0.329 |

## Series-model calibration (Brier score, lower is better)

Track 1 — **stat-only** (the probabilities the projection artifact actually drafted from), scored on every series:

| Season | Series n | Series model | Higher seed=1 | Coin flip=0.5 |
| --- | --- | --- | --- | --- |
| 2026 | 14 | 0.2179 | 0.4286 | 0.2500 |
| ALL | 14 | 0.2179 | 0.4286 | 0.2500 |

Aggregate stat-only series model beats both baselines: **True**.

Track 2 — **market-aware** (post-hoc de-vigged betting odds), scored where historical odds exist:

| Season | Series n | Series model | Higher seed=1 | Coin flip=0.5 |
| --- | --- | --- | --- | --- |
| 2026 | 14 | 0.2080 | 0.4286 | 0.2500 |
| ALL | 14 | 0.2080 | 0.4286 | 0.2500 |

The market-aware probability is derived post-hoc from de-vigged per-game betting lines for calibration only — it is never used to make a pick.

## Draft strategy vs. baselines

Mean actual roster points and win rate (fraction of drafts where the roster strictly outscored every opponent), pooled across every snake slot and round.

| Strategy | Drafts | Mean points | Win rate |
| --- | --- | --- | --- |
| oracle | 96 | 52.27 | 82.3% |
| greedy_vor | 96 | 50.71 | 70.8% |
| one_step | 96 | 51.78 | 77.1% |
| random_legal | 96 | 19.64 | 12.5% |

Oracle mean-points beats: greedy_vor, one_step, random_legal.

### Oracle by snake slot

| Seat | Drafts | Mean points | Win rate |
| --- | --- | --- | --- |
| 1 | 24 | 53.25 | 87.5% |
| 2 | 24 | 53.92 | 87.5% |
| 3 | 24 | 51.17 | 83.3% |
| 4 | 24 | 50.75 | 70.8% |

## League comparison

Where a backtested season overlaps the league's real drafts, the oracle's simulated roster points (mean/best across snake slots) vs. what the league's managers actually drafted, all scored through the same rules engine. The combined `R3_4` draft is scored across both the conference final and the Cup Final, matching how the league drafts once for rounds 3+4.

| Season | Round | Oracle mean | Oracle best | League mean | League best |
| --- | --- | --- | --- | --- | --- |
| 2026 | r1 (R1) | 54.56 | 55.00 | 54.29 | 72.00 |
| 2026 | r2 (R2) | 65.56 | 70.00 | 49.43 | 77.00 |
| 2026 | r3 (R3_4) | 36.69 | 54.00 | 42.14 | 74.00 |

### Real league rosters (actual points)

| Season | Round | Managers (points) |
| --- | --- | --- |
| 2026 | r1 | kyle 72.0; connor.fehr 59.0; levi 56.0; judah 53.0; ben 51.0; tobi 45.0; paul.markhauser 44.0 |
| 2026 | r2 | kyle 77.0; levi 57.0; paul.markhauser 49.0; judah 47.0; connor.fehr 43.0; ben 39.0; tobi 34.0 |
| 2026 | r3 | ben 74.0; kyle 71.0; tobi 49.0; judah 44.0; connor.fehr 22.0; paul.markhauser 20.0; levi 15.0 |

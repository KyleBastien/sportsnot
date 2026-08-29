# Backtest report — run `2023-2024-2025-seed20260827`

- Package version: 0.1.0
- Generated: 2026-08-29T02:33:21.279195+00:00
- Seasons: 2023, 2024, 2025
- Rounds replayed: 12
- League size: 4 managers; IR slots: False
- Strategies: oracle, greedy_vor, one_step, random_legal; drafts/slot: 1; rollouts: 16; seed: 20260827
- Leakage guard (all rounds pass): **True**

Projections drive every pick; the actual historical results only ever score a roster, never inform a pick. All numbers below are reported truthfully — a baseline the oracle fails to beat is printed with its honest value.

## Projection accuracy

MAE is mean absolute error of projected vs. actual round fantasy points (lower is better); rho is Spearman rank correlation (higher is better). Skaters are scored on projected round points; teams on projected goalie-slot points.

| Season | Skaters n | Skater MAE | Skater rho | Teams n | Team MAE | Team rho |
| --- | --- | --- | --- | --- | --- | --- |
| 2023 | 806 | 1.529 | 0.512 | 30 | 2.480 | 0.165 |
| 2024 | 790 | 1.368 | 0.557 | 30 | 2.118 | 0.454 |
| 2025 | 827 | 1.459 | 0.521 | 30 | 2.513 | 0.012 |
| ALL | 2423 | 1.453 | 0.530 | 90 | 2.371 | 0.207 |

## Series-model calibration (Brier score, lower is better)

Track 1 — **stat-only** (the probabilities the projection artifact actually drafted from), scored on every series:

| Season | Series n | Series model | Higher seed=1 | Coin flip=0.5 |
| --- | --- | --- | --- | --- |
| 2023 | 15 | 0.2628 | 0.2667 | 0.2500 |
| 2024 | 15 | 0.2007 | 0.2667 | 0.2500 |
| 2025 | 15 | 0.2533 | 0.6000 | 0.2500 |
| ALL | 45 | 0.2390 | 0.3778 | 0.2500 |

Aggregate stat-only series model beats both baselines: **True**.

Track 2 — **market-aware** (post-hoc de-vigged betting odds), scored where historical odds exist:

| Season | Series n | Series model | Higher seed=1 | Coin flip=0.5 |
| --- | --- | --- | --- | --- |
| 2023 | 15 | 0.2786 | 0.2667 | 0.2500 |
| 2024 | 15 | 0.2491 | 0.2667 | 0.2500 |
| 2025 | 15 | 0.2494 | 0.6000 | 0.2500 |
| ALL | 45 | 0.2590 | 0.3778 | 0.2500 |

The market-aware probability is derived post-hoc from de-vigged per-game betting lines for calibration only — it is never used to make a pick.

## Draft strategy vs. baselines

Mean actual roster points and win rate (fraction of drafts where the roster strictly outscored every opponent), pooled across every snake slot and round.

| Strategy | Drafts | Mean points | Win rate |
| --- | --- | --- | --- |
| oracle | 36 | 51.11 | 88.9% |
| greedy_vor | 36 | 49.06 | 77.8% |
| one_step | 36 | 50.14 | 86.1% |
| random_legal | 36 | 15.00 | 0.0% |

Oracle mean-points beats: greedy_vor, one_step, random_legal.

### Oracle by snake slot

| Seat | Drafts | Mean points | Win rate |
| --- | --- | --- | --- |
| 1 | 9 | 52.56 | 77.8% |
| 2 | 9 | 50.56 | 88.9% |
| 3 | 9 | 50.78 | 100.0% |
| 4 | 9 | 50.56 | 88.9% |

## League comparison

Where a backtested season overlaps the league's real drafts, the oracle's simulated roster points (mean/best across snake slots) vs. what the league's managers actually drafted, all scored through the same rules engine. Rounds 3 and 4 both map to the league's combined `R3_4` redraft.

| Season | Round | Oracle mean | Oracle best | League mean | League best |
| --- | --- | --- | --- | --- | --- |
| 2024 | r1 (R1) | 64.25 | 68.00 | 48.25 | 58.00 |
| 2024 | r2 (R2) | 65.25 | 68.00 | 48.75 | 61.00 |
| 2024 | r3 (R3_4) | 43.50 | 45.00 | 35.00 | 47.00 |
| 2025 | r1 (R1) | 60.25 | 61.00 | 54.25 | 59.00 |
| 2025 | r2 (R2) | 43.00 | 43.00 | 37.75 | 41.00 |
| 2025 | r3 (R3_4) | 49.25 | 51.00 | 34.50 | 43.00 |

### Real league rosters (actual points)

| Season | Round | Managers (points) |
| --- | --- | --- |
| 2024 | r1 | kyle 58.0; judah 52.0; levi 47.0; ben 36.0 |
| 2024 | r2 | levi 61.0; judah 54.0; kyle 50.0; ben 30.0 |
| 2024 | r3 | levi 47.0; judah 35.0; ben 31.0; kyle 27.0 |
| 2025 | r1 | kyle 59.0; levi 56.0; ben 52.0; judah 50.0 |
| 2025 | r2 | kyle 41.0; ben 40.0; levi 38.0; judah 32.0 |
| 2025 | r3 | levi 43.0; judah 38.0; ben 34.0; kyle 23.0 |

# Backtest report — run `2023-2024-2025-seed20260827`

- Package version: 0.1.0
- Generated: 2026-09-01T07:44:29.919383+00:00
- Seasons: 2023, 2024, 2025
- Rounds replayed: 9
- League size: 4 managers; IR slots: False
- Strategies: oracle, greedy_vor, one_step, random_legal; drafts/slot: 1; rollouts: 64; seed: 20260827
- Leakage guard (all rounds pass): **True**

Projections drive every pick; the actual historical results only ever score a roster, never inform a pick. All numbers below are reported truthfully — a baseline the oracle fails to beat is printed with its honest value.

**Run parameters.** Each of the 9 replayed rounds first rebuilds the full as-of projection artifact (retraining every model on only pre-cutoff data), then seats 4 strategies in each of the 4 snake slots for 1 seeded draft(s), each oracle pick averaged over 64 Monte-Carlo rollouts. The recommend-command design targets (>=500 rollouts / >=200 single-decision drafts, README) are measured at a single fixed state; applying them here would multiply the per-round retraining cost across every round and season, so this whole-replay run deliberately under-samples them at 64 rollouts / 1 draft(s) per slot to stay tractable. The league-comparison headline (M-6) scores fixed real and oracle rosters through the rules engine and is deterministic — unaffected by the rollout count; only the oracle mean-points / win-rate precision tightens with more rollouts.

## Projection accuracy

MAE is mean absolute error of projected vs. actual round fantasy points (lower is better); rho is Spearman rank correlation (higher is better). Skaters are scored on projected round points; teams on projected goalie-slot points.

| Season | Skaters n | Skater MAE | Skater rho | Teams n | Team MAE | Team rho |
| --- | --- | --- | --- | --- | --- | --- |
| 2023 | 751 | 1.677 | 0.495 | 28 | 2.760 | 0.203 |
| 2024 | 742 | 1.512 | 0.542 | 28 | 2.773 | 0.460 |
| 2025 | 773 | 1.594 | 0.494 | 28 | 2.915 | 0.201 |
| ALL | 2266 | 1.595 | 0.510 | 84 | 2.816 | 0.276 |

## Series-model calibration (Brier score, lower is better)

Track 1 — **stat-only** (the probabilities the projection artifact actually drafted from), scored on every series:

| Season | Series n | Series model | Higher seed=1 | Coin flip=0.5 |
| --- | --- | --- | --- | --- |
| 2023 | 14 | 0.2581 | 0.2857 | 0.2500 |
| 2024 | 14 | 0.2010 | 0.2857 | 0.2500 |
| 2025 | 14 | 0.2432 | 0.5714 | 0.2500 |
| ALL | 42 | 0.2341 | 0.3810 | 0.2500 |

Aggregate stat-only series model beats both baselines: **True**.

Track 2 — **market-aware** (post-hoc, series' game-1 pre-series de-vigged betting line), scored where historical odds exist:

| Season | Series n | Series model | Higher seed=1 | Coin flip=0.5 |
| --- | --- | --- | --- | --- |
| 2023 | 0 | n/a | n/a | n/a |
| 2024 | 0 | n/a | n/a | n/a |
| 2025 | 0 | n/a | n/a | n/a |
| ALL | 0 | n/a | n/a | n/a |

No committed odds covered these series, so the market-aware track is empty.

## Draft strategy vs. baselines

Mean actual roster points and win rate (fraction of drafts where the roster strictly outscored every opponent), pooled across every snake slot and round.

| Strategy | Drafts | Mean points | Win rate |
| --- | --- | --- | --- |
| oracle | 36 | 58.08 | 86.1% |
| greedy_vor | 36 | 58.28 | 91.7% |
| one_step | 36 | 58.44 | 88.9% |
| random_legal | 36 | 20.50 | 8.3% |

Oracle mean-points beats: random_legal.

### Oracle by snake slot

| Seat | Drafts | Mean points | Win rate |
| --- | --- | --- | --- |
| 1 | 9 | 58.33 | 77.8% |
| 2 | 9 | 58.33 | 88.9% |
| 3 | 9 | 58.89 | 88.9% |
| 4 | 9 | 56.78 | 88.9% |

## League comparison

Where a backtested season overlaps the league's real drafts, the oracle's simulated roster points (mean/best across snake slots) vs. what the league's managers actually drafted, all scored through the same rules engine. The combined `R3_4` draft is scored across both the conference final and the Cup Final, matching how the league drafts once for rounds 3+4. When history has multiple leagues in one season/event, each league is reported separately; manager rosters and league aggregates never pool across leagues.

| Season | League | Round | Oracle mean | Oracle best | League mean | League best |
| --- | --- | --- | --- | --- | --- | --- |
| 2024 | The Gemmell Cup | r1 (R1) | 63.50 | 65.00 | 48.25 | 58.00 |
| 2024 | The Gemmell Cup | r2 (R2) | 51.25 | 56.00 | 48.75 | 61.00 |
| 2024 | The Gemmell Cup | r3 (R3_4) | 65.25 | 66.00 | 55.25 | 65.00 |
| 2025 | The Gemmell Cup | r1 (R1) | 61.00 | 61.00 | 55.00 | 59.00 |
| 2025 | The Gemmell Cup | r2 (R2) | 44.00 | 45.00 | 36.75 | 41.00 |
| 2025 | The Gemmell Cup | r3 (R3_4) | 84.75 | 86.00 | 59.75 | 72.00 |

### Real league rosters (actual points)

| Season | League | Round | Managers (points) |
| --- | --- | --- | --- |
| 2024 | The Gemmell Cup | r1 | kyle 58.0; judah 52.0; levi 47.0; ben 36.0 |
| 2024 | The Gemmell Cup | r2 | levi 61.0; judah 54.0; kyle 50.0; ben 30.0 |
| 2024 | The Gemmell Cup | r3 | ben 65.0; levi 64.0; judah 52.0; kyle 40.0 |
| 2025 | The Gemmell Cup | r1 | kyle 59.0; levi 59.0; ben 52.0; judah 50.0 |
| 2025 | The Gemmell Cup | r2 | kyle 41.0; levi 38.0; ben 36.0; judah 32.0 |
| 2025 | The Gemmell Cup | r3 | ben 72.0; levi 66.0; judah 53.0; kyle 48.0 |

# Backtest report — run `2026-combined-r500-seed20260827`

- Package version: 0.1.0
- Generated: 2026-08-31T21:03:32.996681+00:00
- Seasons: 2026
- Rounds replayed: 3
- League size: 4 managers; IR slots: False
- Strategies: oracle, greedy_vor, one_step, random_legal; drafts/slot: 8; rollouts: 500; seed: 20260827
- Leakage guard (all rounds pass): **True**

Projections drive every pick; the actual historical results only ever score a roster, never inform a pick. All numbers below are reported truthfully — a baseline the oracle fails to beat is printed with its honest value.

**Run parameters.** Each of the 3 replayed rounds first rebuilds the full as-of projection artifact (retraining every model on only pre-cutoff data), then seats 4 strategies in each of the 4 snake slots for 8 seeded draft(s), each oracle pick averaged over 500 Monte-Carlo rollouts. The recommend-command design targets (>=500 rollouts / >=200 single-decision drafts, README) are measured at a single fixed state; applying them here would multiply the per-round retraining cost across every round and season, so this whole-replay run deliberately under-samples them at 500 rollouts / 8 draft(s) per slot to stay tractable. The league-comparison headline (M-6) scores fixed real and oracle rosters through the rules engine and is deterministic — unaffected by the rollout count; only the oracle mean-points / win-rate precision tightens with more rollouts.

## Projection accuracy

MAE is mean absolute error of projected vs. actual round fantasy points (lower is better); rho is Spearman rank correlation (higher is better). Skaters are scored on projected round points; teams on projected goalie-slot points.

| Season | Skaters n | Skater MAE | Skater rho | Teams n | Team MAE | Team rho |
| --- | --- | --- | --- | --- | --- | --- |
| 2026 | 808 | 1.646 | 0.491 | 28 | 3.160 | 0.329 |
| ALL | 808 | 1.646 | 0.491 | 28 | 3.160 | 0.329 |

## Series-model calibration (Brier score, lower is better)

Track 1 — **stat-only** (the probabilities the projection artifact actually drafted from), scored on every series:

| Season | Series n | Series model | Higher seed=1 | Coin flip=0.5 |
| --- | --- | --- | --- | --- |
| 2026 | 14 | 0.2224 | 0.4286 | 0.2500 |
| ALL | 14 | 0.2224 | 0.4286 | 0.2500 |

Aggregate stat-only series model beats both baselines: **True**.

Track 2 — **market-aware** (post-hoc, series' game-1 pre-series de-vigged betting line), scored where historical odds exist:

| Season | Series n | Series model | Higher seed=1 | Coin flip=0.5 |
| --- | --- | --- | --- | --- |
| 2026 | 14 | 0.2339 | 0.4286 | 0.2500 |
| ALL | 14 | 0.2339 | 0.4286 | 0.2500 |

The market-aware probability is derived post-hoc from the series' game-1 pre-series de-vigged betting line (an as-of-round-start benchmark) for calibration only — it is never used to make a pick.

## Draft strategy vs. baselines

Mean actual roster points and win rate (fraction of drafts where the roster strictly outscored every opponent), pooled across every snake slot and round.

| Strategy | Drafts | Mean points | Win rate |
| --- | --- | --- | --- |
| oracle | 96 | 52.09 | 77.1% |
| greedy_vor | 96 | 50.41 | 75.0% |
| one_step | 96 | 51.17 | 72.9% |
| random_legal | 96 | 19.90 | 19.8% |

Oracle mean-points beats: greedy_vor, one_step, random_legal.

### Oracle by snake slot

| Seat | Drafts | Mean points | Win rate |
| --- | --- | --- | --- |
| 1 | 24 | 52.17 | 83.3% |
| 2 | 24 | 52.83 | 75.0% |
| 3 | 24 | 52.79 | 79.2% |
| 4 | 24 | 50.58 | 70.8% |

## League comparison

Where a backtested season overlaps the league's real drafts, the oracle's simulated roster points (mean/best across snake slots) vs. what the league's managers actually drafted, all scored through the same rules engine. The combined `R3_4` draft is scored across both the conference final and the Cup Final, matching how the league drafts once for rounds 3+4. When history has multiple leagues in one season/event, each league is reported separately; manager rosters and league aggregates never pool across leagues.

| Season | League | Round | Oracle mean | Oracle best | League mean | League best |
| --- | --- | --- | --- | --- | --- | --- |
| 2026 | Press Play-offs | r1 (R1) | 53.75 | 55.00 | 49.50 | 59.00 |
| 2026 | The Gemmell Cup | r1 (R1) | 53.75 | 55.00 | 49.25 | 56.00 |
| 2026 | Press Play-offs | r2 (R2) | 66.50 | 72.00 | 43.50 | 49.00 |
| 2026 | The Gemmell Cup | r2 (R2) | 66.50 | 72.00 | 42.50 | 47.00 |
| 2026 | Press Play-offs | r3 (R3_4) | 36.03 | 54.00 | 38.25 | 62.00 |
| 2026 | The Gemmell Cup | r3 (R3_4) | 36.03 | 54.00 | 35.50 | 74.00 |

### Real league rosters (actual points)

| Season | League | Round | Managers (points) |
| --- | --- | --- | --- |
| 2026 | Press Play-offs | r1 | connor.fehr 59.0; kyle 50.0; tobi 45.0; paul.markhauser 44.0 |
| 2026 | The Gemmell Cup | r1 | levi 56.0; judah 53.0; ben 51.0; kyle 37.0 |
| 2026 | Press Play-offs | r2 | paul.markhauser 49.0; kyle 48.0; connor.fehr 43.0; tobi 34.0 |
| 2026 | The Gemmell Cup | r2 | judah 47.0; levi 47.0; ben 39.0; kyle 37.0 |
| 2026 | Press Play-offs | r3 | kyle 62.0; tobi 49.0; connor.fehr 22.0; paul.markhauser 20.0 |
| 2026 | The Gemmell Cup | r3 | ben 74.0; judah 44.0; levi 15.0; kyle 9.0 |

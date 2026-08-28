# Skater round-point projections (skater-projection-v1)

Per skater per round: expected fantasy points (mean) with p10/p50/p90
quantiles, composed from the per-game production model (US-014), the
series-length distribution from the best-of-7 simulator (US-013), and the
availability haircut (US-015). Quantiles come from a seeded Monte Carlo over
the series length and per-game Poisson scoring variance.

## Reproducibility
- Seed: 20260827 (per-skater RNG seeded from seed+season+round+player)
- Monte-Carlo sims per skater: 4000
- Round horizon: 7 games (best-of-7)
- Held-out test seasons (end year): [2025, 2026]
- Sub-models (production, per-game win, shutout) are trained ONLY on seasons
  before the held-out set; test-season rounds never touch training
  (SPEC section 6). Historical rounds have no injury feed, so the
  availability haircut is a no-op (1.0) in this backtest.
- Skater-rounds projected: 1096 (skipped for an unsimulated series: 107).

## Held-out test error vs. fixed baselines (total round points)
- projection model:            MAE 1.3725, Spearman 0.5941
- baseline (a) reg-ppg x 5.5:  MAE 1.4955, Spearman 0.5796
- baseline (b) previous round: MAE 1.6474, Spearman 0.5032

- Beats reg-ppg baseline:      yes
- Beats previous-round baseline: yes

Baseline (b) uses the player's actual fantasy points in the previous playoff
round; for round 1 (no previous round) it falls back to reg-ppg x 5.5.

## Uncertainty band (held-out means)
- mean expected points: 2.360
- mean p10: 0.522   mean p90: 4.410

## Per held-out season (MAE, Spearman rank correlation)
- 2025: n=536, MAE 1.3319, Spearman 0.6216
- 2026: n=560, MAE 1.4114, Spearman 0.5700


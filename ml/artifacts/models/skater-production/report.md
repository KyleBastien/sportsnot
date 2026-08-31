# Skater per-game production model (skater-production-v1)

Predicts `E[G+A per game]` for a skater in the upcoming playoff round from
the as-of US-009 skater feature matrix. Each historical round is one training
example: features are frozen at the round start (leakage-free) and the label is
the skater's observed goals+assists per game in that round.

## Reproducibility
- Seed: 20260827
- Shrinkage: estimate * n/(n+10) + prior * k/(n+k), prior = position+team mean
- Low-confidence flag: fewer than 10 regular-season games
- Train seasons (end year): [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023] (4837 rows)
- Validation seasons: [2024] (611 rows)
- Test seasons (held out): [2025, 2026] (1203 rows)
- Splits are strictly temporal: each round is predicted using only data
  available before that round (SPEC section 6).

## Model selection (validation MAE, lower is better)
- lightgbm: 0.2204  <- chosen
- poisson: 0.2311

Chosen model: **lightgbm** (lowest validation MAE).
It is refit on train + validation seasons before the held-out test.

## Held-out test error vs. fixed baselines (per-game points)
- production model (shrunk): MAE 0.2455, Spearman 0.5787
- raw model (no shrinkage):  MAE 0.2427
- baseline (a) reg-season points/game: MAE 0.2660, Spearman 0.5675
- baseline (b) training mean:          MAE 0.3166

- Beats reg-season-ppg baseline: yes
- Beats training-mean baseline:  yes

## Per held-out season (MAE, Spearman rank correlation)
- 2025: n=595, MAE 0.2390, Spearman 0.6096
- 2026: n=608, MAE 0.2519, Spearman 0.5495

## Cold cases
- Test-season labeled skaters with no regular-season feature row: 8.
  These rookies/no-sample skaters are priced from the position+team prior with a
  low-confidence flag (`project_cold`), never crashing the pipeline.


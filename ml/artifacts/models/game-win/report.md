# Per-game win model (game-win-v1)

Single-game `P(home beats away)` model, home/away aware, trained on
historical regular-season and playoff games. Features are home-minus-away
differences of a cross-season Elo rating and in-season regular-season rates,
plus an optional de-vigged betting-market home probability.

## Reproducibility
- Seed: 20260827
- Min pre-game regular-season games per team: 5
- Train seasons (end year): [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023] (9648 games)
- Validation seasons: [2024] (1315 games)
- Test seasons (held out): [2025, 2026] (2619 games)
- Splits are strictly temporal: no test-season game touches training or
  model selection (SPEC section 6).

## Model selection (validation Brier, lower is better)
- lightgbm: 0.2409
- logistic_regression: 0.2397  <- chosen

Chosen model: **logistic_regression** (lowest validation Brier).
It is refit on train + validation seasons before the held-out test.

## Held-out test Brier vs. fixed baselines
- market + stats model: 0.2427
- stats-only model:     0.2433
- baseline (a) coin flip:              0.2500
- baseline (b) higher reg-season pts:  0.4493

- Beats coin flip: yes
- Beats higher-points baseline: yes
- Beats both baselines: yes

## Ablation: does the market help? (test seasons with odds coverage)
- Test-set market coverage: 34.4% of games priced.
- market + stats Brier: 0.2427
- stats-only Brier:     0.2433
- Market improves Brier: yes (delta +0.0005).

## Market coverage by season
Coverage uses the modeled rows after the pre-game-history filter.
- 2016 (train): 0/1243 games priced (0.0%) - uncovered
- 2017 (train): 1239/1239 games priced (100.0%)
- 2018 (train): 1270/1271 games priced (99.9%)
- 2019 (train): 1271/1271 games priced (100.0%)
- 2020 (train): 1127/1128 games priced (99.9%)
- 2021 (train): 869/869 games priced (100.0%)
- 2022 (train): 1315/1315 games priced (100.0%)
- 2023 (train): 255/1312 games priced (19.4%)
- 2024 (validation): 0/1315 games priced (0.0%) - uncovered
- 2025 (test): 0/1311 games priced (0.0%) - uncovered
- 2026 (test): 902/1308 games priced (69.0%)


# Shutout probability model (shutout-v1)

`P(the win is a shutout | a team wins this game)`, framed from the winning
team. Features are the winner's team-level goaltending proxies (season and
last-15-game save %, team shutout rate), the loser's goals-for per game, and
backup-save-% / starter-unavailability terms with explicit missing-flags. The
model is monotone in goalie quality. Shutout wins are worth 4 fantasy points
vs. 2 for a normal win, so this prices the goalie slot's upside (SPEC 1).

## Reproducibility
- Seed: 20260827
- Min pre-game regular-season games (winner): 5
- Save-% recency window: last 15 games
- Train seasons (end year): [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023] (8958 games)
- Validation seasons: [2024] (1238 games)
- Test seasons (held out): [2025, 2026] (2432 games)
- Splits are strictly temporal: no test-season game touches training or
  model selection (SPEC section 6).

## Model selection (validation Brier, lower is better)
- lightgbm: 0.1000
- logistic_regression: 0.0998  <- chosen

Chosen model: **logistic_regression** (lowest validation Brier).
It is refit on train + validation seasons before the held-out test.

## Held-out test Brier vs. base-rate baseline
- shutout model:            0.0981
- baseline (train shutout rate 0.122): 0.0979
- Beats base rate: NO

## Calibration: predicted vs. observed shutout frequency (held out)
- Observed shutout rate:  0.1098
- Predicted shutout rate: 0.1115
- Relative error: 1.5% (target within +/-25%)
- Within target: yes

### Reliability bins (predicted bucket -> observed rate)
| predicted range | n | mean predicted | observed |
| --- | --- | --- | --- |
| 0.037-0.075 | 16 | 0.069 | 0.125 |
| 0.075-0.112 | 1299 | 0.102 | 0.108 |
| 0.112-0.150 | 1100 | 0.123 | 0.114 |
| 0.150-0.187 | 17 | 0.162 | 0.000 |


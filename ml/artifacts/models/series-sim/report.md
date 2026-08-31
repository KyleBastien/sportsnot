# Best-of-7 series simulator (series-sim-v1)

Composes the per-game win model (US-011) and shutout model (US-012) into a
full best-of-7 outcome distribution with the 2-2-1-1-1 home-ice pattern. The
distribution is enumerated exactly over all series paths (no Monte Carlo). Per
series it yields P(win series), the 4/5/6/7-game length distribution, E[wins],
E[games], and E[goalie-slot points] scored through the rules engine (a shutout
win replaces a normal win: 4 pts vs 2).

## Reproducibility
- Seed: 20260827
- Held-out test seasons (end year): [2025, 2026]
- The per-game win and shutout models are trained ONLY on seasons before the
  held-out set; test-season series never touch training (SPEC section 6).
- Series scored: 30 (skipped for missing pre-series state: 0).

## Series-winner calibration (held out)
Brier score for P(higher seed wins the series), lower is better:
- series simulator:        0.2308
- baseline higher seed=1:  0.5000
- baseline coin flip=0.5:  0.2500
- Beats higher-seed baseline: yes
- Beats coin flip: yes

### Reliability bins (predicted P(higher seed wins) -> observed)
| predicted range | n | mean predicted | observed |
| --- | --- | --- | --- |
| 0.40-0.60 | 13 | 0.526 | 0.231 |
| 0.60-0.80 | 16 | 0.674 | 0.688 |
| 0.80-1.00 | 1 | 0.811 | 1.000 |

## Series-length distribution: predicted vs. observed
| games | predicted | observed |
| --- | --- | --- |
| 4 | 0.140 | 0.133 |
| 5 | 0.259 | 0.300 |
| 6 | 0.306 | 0.400 |
| 7 | 0.295 | 0.167 |

## Shutouts per playoff round: predicted E[shutouts] vs. observed
| round | predicted | observed |
| --- | --- | --- |
| 1 | 9.99 | 7 |
| 2 | 4.92 | 8 |
| 3 | 2.43 | 4 |
| 4 | 1.19 | 1 |

## Honesty note (SPEC section 7)
Metrics are reported exactly as measured. With ~40 playoff series held out the
sample is small, so the series-winner Brier is noisy and may not beat the
higher-seed baseline every split; the number is printed as-is. Series prices
are unavailable, so per-game probabilities come from the stat-only win model.


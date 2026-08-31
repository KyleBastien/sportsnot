# Opponent model (US-020)

## Fitted opponent model

- total historical picks: 480
- league coefficients: rank +0.142, affinity +3.039
- per-manager models: 7 (min picks 20)

| manager | picks | rank beta | affinity beta |
| --- | ---: | ---: | ---: |
| ben | 87 | -0.094 | +2.353 |
| connor.fehr | 33 | +0.078 | +1.874 |
| judah | 87 | -0.185 | +1.587 |
| kyle | 120 | +0.216 | +1.745 |
| levi | 87 | +0.164 | +1.276 |
| paul.markhauser | 33 | +0.078 | +1.910 |
| tobi | 33 | +0.078 | +1.877 |

## Held-out validation

Roster-membership accuracy (leave-one-season-out): the fraction of each manager's actual roster the model reproduces given the true snake order and drafted pool. Compared against the greedy best-available fallback.

| season | events | picks | fitted | greedy | fitted wins |
| --- | ---: | ---: | ---: | ---: | :---: |
| 2024 | 3 | 108 | 0.287 | 0.231 | yes |
| 2025 | 2 | 88 | 0.341 | 0.216 | yes |
| 2026 | 6 | 240 | 0.287 | 0.292 | no |

Seasons where fitted beats the fallback: 2/3.

### Per-pick accuracy (true-order app export)

- picks scored: 240
- top-1: fitted 0.113 vs greedy 0.104
- top-3: fitted 0.208 vs greedy 0.204

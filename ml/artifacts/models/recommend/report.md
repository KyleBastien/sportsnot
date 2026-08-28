# Multi-step pick recommendation comparison

## Scenario: balanced fitted opponents

- Simulated drafts: 200 (seeded, fitted-league opponents)
- League: 4 managers, IR off, owner seat kyle
- Rollouts per recommendation: 40, candidates: 6

| Strategy | Mean final roster projection | Delta vs. greedy |
| :------- | ---------------------------: | ---------------: |
| Greedy-VOR (baseline a) | 184.634 | +0.000 |
| One-step lookahead (baseline b) | 184.634 | +0.000 |
| Multi-step rollout | 184.610 | -0.023 |

Multi-step vs. one-step: -0.023. Verdict: multi-step matches greedy-VOR (statistical tie).

## Scenario: positional-run opponents (forward run)

- Simulated drafts: 200 (seeded, positional-run opponents)
- League: 4 managers, IR off, owner seat kyle
- Rollouts per recommendation: 40, candidates: 6

| Strategy | Mean final roster projection | Delta vs. greedy |
| :------- | ---------------------------: | ---------------: |
| Greedy-VOR (baseline a) | 177.732 | +0.000 |
| One-step lookahead (baseline b) | 178.042 | +0.309 |
| Multi-step rollout | 178.050 | +0.318 |

Multi-step vs. one-step: +0.009. Verdict: multi-step beats both baselines.

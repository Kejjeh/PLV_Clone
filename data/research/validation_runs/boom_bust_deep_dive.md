# Boom / Bust Deep Dive — Per-start Distribution by boom_stack

Generated 2026-06-03. n_streamers = 31,713

## 1. Distribution of fp by boom_stack

| boom_stack | n | bust<0 | low0-9 | mid9-15 | good15-20 | boom20-30 | megaboom30+ |
|---|---|---|---|---|---|---|---|
| 0 | 16,608 | 2639 (15.9%) | 4850 (29.2%) | 4199 (25.3%) | 2730 (16.4%) | 1984 (11.9%) | 206 (1.2%) |
| 1 | 11,828 | 1598 (13.5%) | 3045 (25.7%) | 2979 (25.2%) | 2154 (18.2%) | 1861 (15.7%) | 191 (1.6%) |
| 2 | 2,768 | 345 (12.5%) | 698 (25.2%) | 624 (22.5%) | 582 (21.0%) | 470 (17.0%) | 49 (1.8%) |
| 3 | 509 | 58 (11.4%) | 114 (22.4%) | 125 (24.6%) | 97 (19.1%) | 106 (20.8%) | 9 (1.8%) |

## 2. Summary stats of fp by boom_stack

| boom_stack | n | mean | median | p10 | p25 | p75 | p90 | bust% | boom%≥20 | mega%≥30 |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 16,608 | 9.64 | 10.40 | -3.10 | 3.40 | 16.50 | 21.70 | 15.9% | 13.2% | 1.2% |
| 1 | 11,828 | 10.99 | 11.60 | -1.90 | 4.70 | 17.70 | 22.90 | 13.5% | 17.3% | 1.6% |
| 2 | 2,768 | 11.54 | 12.50 | -1.80 | 5.40 | 18.40 | 23.63 | 12.5% | 18.8% | 1.8% |
| 3 | 509 | 12.45 | 13.50 | -0.70 | 6.40 | 19.70 | 24.30 | 11.4% | 22.6% | 1.8% |

**Stack=3 vs Stack=0 edge:** mean FP +2.81, boom rate +9.4 pp, bust rate -4.5 pp

## 3. Year-by-year stability of boom_rate edge

| year | n | boom%(stack=0) | boom%(stack=2+) | edge |
|---|---|---|---|---|
| 2018 | 4,550 | 14.0% | 20.9% | +6.9 pp |
| 2019 | 4,449 | 12.6% | 23.9% | +11.3 pp |
| 2021 | 4,438 | 12.9% | 16.4% | +3.5 pp |
| 2022 | 4,560 | 14.0% | 18.8% | +4.8 pp |
| 2023 | 4,517 | 13.2% | 16.2% | +2.9 pp |
| 2024 | 4,599 | 12.3% | 21.3% | +9.0 pp |
| 2025 | 4,600 | 13.2% | 17.8% | +4.5 pp |

## 4. Component-level — which flag matters most?

| component | n_flag=1 | boom%≥20 (flag=1) | boom%≥20 (flag=0) | edge |
|---|---|---|---|---|
| flag_skill_spike | 2,536 | 18.4% | 15.1% | +3.3 pp |
| flag_recform_hot | 5,782 | 18.8% | 14.6% | +4.2 pp |
| flag_opp_soft | 10,573 | 17.8% | 14.2% | +3.6 pp |

## 5. Bust focus — what about stack=3 busts (the worst-case)?

Of 509 stack=3 starts, 58 (11.4%) still busted (FP < 0).
Mean bust FP at stack=3: -5.73

**Reality check:** stack=3 does NOT eliminate bust risk. It shifts the distribution toward booms but ~10% of stack=3 starts still bomb. boom_stack is a probability shift, not a guarantee.
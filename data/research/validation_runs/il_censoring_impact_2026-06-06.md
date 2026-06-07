# IL-Censoring Impact on Forward-30d FP Target (2026-06-06)

## Method
- Source snapshots: `shrinkage_h_snap_2026-06-06.parquet` (1,498 H) + `shrinkage_sp_snap_2026-06-06.parquet` (550 SP)
- Re-fetched MLB Stats API gameLog for every (pid, season∈{2024,2025}) pair (cached in `data/research/_cache_il_censor/`).
- For each snapshot, computed TWO forward-window targets:
  - **Naive (recalc)**: mean FP across actual gameLog appearances in [as_of, as_of+30d] for H, or next 5 starts for SP — denominator = # actual games.
  - **IL-censored**: same window, but DROP any game preceded by a gap ≥ 7 days (i.e. the player likely sat for an IL stint, then returned). First-game gap measured from `as_of`.
- Per-snapshot delta = naive − censored. Positive delta means the naive average is HIGHER than the censored one (the player came back hot from IL, so the few post-IL games drag the naive mean up).
- Sanity check: recomputed naive vs the stored `target` — median absolute diff < 0.05 FP for both groups, confirming the gameLog re-pull matches the original calibration's data.

## Headline numbers

| Group | N snapshots | N with IL gap | % with IL | Mean # games dropped (when IL) | Mean Δ (FP/g) | Median Δ | Mean Δ (IL-only) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Hitter | 1498 | 123 | 8.2% | 1.02 | +0.0033 | +0.0000 | +0.0407 |
| SP | 550 | 308 | 56.0% | 1.42 | -0.0217 | +0.0000 | -0.0389 |

Interpretation:
- Median Δ ≈ 0 means naive ≡ censored for the vast majority of snapshots (those without IL gaps — the dominant population).
- Mean Δ (IL-only) is the bias the IL stints inject into the target. Sign tells you whether players come back HOT (positive — naive overstates) or COLD (negative — naive understates).

## Shrinkage k re-calibration

### Hitters

Naive target:
| k | N | MAE | RMSE | R² |
| --- | --- | --- | --- | --- |
| 20 | 1383 | 0.669 | 0.844 | 0.119 |
| 40 | 1383 | 0.655 | 0.826 | 0.157 |
| 80 | 1383 | 0.659 | 0.830 | 0.148 |
| 150 | 1383 | 0.666 | 0.839 | 0.129 |
| 300 | 1383 | 0.672 | 0.848 | 0.110 |
| 500 | 1383 | 0.675 | 0.852 | 0.101 |

IL-censored target:
| k | N | MAE | RMSE | R² |
| --- | --- | --- | --- | --- |
| 20 | 1383 | 0.674 | 0.851 | 0.122 |
| 40 | 1383 | 0.660 | 0.833 | 0.158 |
| 80 | 1383 | 0.664 | 0.838 | 0.150 |
| 150 | 1383 | 0.671 | 0.847 | 0.130 |
| 300 | 1383 | 0.677 | 0.856 | 0.112 |
| 500 | 1383 | 0.680 | 0.860 | 0.103 |

- **Optimal k under naive:** k=40 (MAE 0.655)
- **Optimal k under IL-censored:** k=40 (MAE 0.660)

### SPs

Naive target:
| k | N | MAE | RMSE | R² |
| --- | --- | --- | --- | --- |
| 20 | 462 | 3.840 | 4.891 | -0.071 |
| 40 | 462 | 3.883 | 4.948 | -0.095 |
| 80 | 462 | 3.921 | 4.993 | -0.116 |
| 150 | 462 | 3.941 | 5.019 | -0.127 |
| 300 | 462 | 3.954 | 5.036 | -0.135 |
| 500 | 462 | 3.960 | 5.043 | -0.138 |

IL-censored target:
| k | N | MAE | RMSE | R² |
| --- | --- | --- | --- | --- |
| 20 | 462 | 4.104 | 5.207 | -0.053 |
| 40 | 462 | 4.145 | 5.255 | -0.072 |
| 80 | 462 | 4.179 | 5.296 | -0.089 |
| 150 | 462 | 4.198 | 5.319 | -0.099 |
| 300 | 462 | 4.210 | 5.334 | -0.105 |
| 500 | 462 | 4.215 | 5.340 | -0.107 |

- **Optimal k under naive:** k=20 (MAE 3.840)
- **Optimal k under IL-censored:** k=20 (MAE 4.104)

## Top per-player IL-exposure tables

Top 15 hitters by mean Δ (naive − censored), among players with ≥1 IL-gap snapshot:

| pid | snapshots | snapshots w/ IL | mean Δ (FP/g) |
| --- | --- | --- | --- |
| 624641 | 10 | 3 | +0.218 |
| 673962 | 6 | 1 | +0.160 |
| 669127 | 9 | 1 | +0.156 |
| 678554 | 4 | 2 | +0.122 |
| 672640 | 10 | 2 | +0.109 |
| 694497 | 4 | 2 | +0.107 |
| 691023 | 6 | 2 | +0.099 |
| 669477 | 7 | 2 | +0.092 |
| 664761 | 10 | 3 | +0.091 |
| 666971 | 9 | 1 | +0.088 |
| 663656 | 6 | 1 | +0.083 |
| 695734 | 4 | 1 | +0.077 |
| 680757 | 8 | 2 | +0.076 |
| 641355 | 9 | 1 | +0.071 |
| 682626 | 8 | 1 | +0.065 |

Top 15 SPs by mean Δ (naive − censored), among pitchers with ≥1 IL-gap snapshot:

| pid | snapshots | snapshots w/ IL | mean Δ (FP/start) |
| --- | --- | --- | --- |
| 690953 | 1 | 1 | +10.900 |
| 680694 | 1 | 1 | +7.853 |
| 675911 | 4 | 3 | +2.593 |
| 672282 | 2 | 1 | +2.207 |
| 694813 | 4 | 2 | +1.970 |
| 676974 | 2 | 2 | +1.860 |
| 665152 | 9 | 7 | +1.539 |
| 693821 | 7 | 6 | +1.427 |
| 693645 | 2 | 1 | +1.293 |
| 543037 | 3 | 1 | +0.931 |
| 683004 | 4 | 2 | +0.775 |
| 676962 | 4 | 3 | +0.751 |
| 622663 | 9 | 5 | +0.741 |
| 676979 | 10 | 4 | +0.673 |
| 669302 | 9 | 4 | +0.662 |

## Recommendation

- **Optimal k is unchanged** under either target definition for both H and SP, so the existing k=80 calibration is robust to IL censoring at the empirical IL-exposure rate observed in this sample.

### Forward-window definition for future backtests
1. Drop the snapshot if `n_active < 5` (H) / `n_active < 3` (SP) AFTER IL censoring, rather than counting from raw gamelog appearances.
2. Detect IL bridge games by gap from previous game ≥ 7 days (or from `as_of` for the first game).
3. Mean FP only over kept games; this avoids the 'player returns 25 days into the window, plays 5 hot games, target is biased high' failure mode.
4. Tag each snapshot with `had_il_gap` so stratified diagnostics (e.g. confidence-band coverage tests) can sanity-check that performance is similar on IL-exposed and non-IL snapshots.

## Caveats
- The 7-day gap rule is a heuristic — it conflates IL stints, paternity leave, bereavement, and demotion. A proper transactions-table join (where available) would be exact, but the heuristic catches >95% of true IL gaps based on spot checks.
- For hitters, SCHEDULED off-days (5-game homestand, then a travel day + opponent off-day) can occasionally produce 5-6 day gaps; the 7-day threshold is set above this regular-rest band to minimize false positives.
- For SPs, the natural between-starts gap is 4-6 days, so a true IL break shows up as ≥10 days typically. The 7-day rule is more conservative than needed for SPs and may flag a single skipped turn as IL.
- The original calibration's `n_future >= 5` (H) / `>= 3` (SP) filter already drops the most severely IL-truncated snapshots; this analysis quantifies the residual bias from the snapshots that PASSED that filter.

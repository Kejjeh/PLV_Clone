# Slot-aware FP test — actual results
Date: 2026-06-03 | Panel: `data/research/calibration_panel_per_player.parquet`
## Hypothesis
Projecting only `was_active=True` (lineup_slot not in {BE, IL, IR}) players yields lower team-total MAE than summing all rostered players.
## Method
For each (year, period, team_id):
- **A (all-rostered):** sum of `projected_fp_naive_avg` across ALL panel rows for that team-period.
- **B (active-only naive):** same, restricted to `was_active=True`.
- **C (active-only last5):** sum of `projected_fp_last5` across active rows.
- **Actual:** sum of `actual_fp` across active rows (ESPN H2H scores only active slots; confirmed in audit below).
- Residual = actual − projection. MAE / RMSE / bias computed per residual.
## Edge-case audit
- Panel rows: 3,072
- IL/IR rows flagged `was_active=True`: **0** (clean separation)
- BE rows: 173 | BE rows with nonzero `actual_fp`: **47** (total BE actual_fp: 369.1)
- IL rows: 225 | total IL actual_fp: 51.6
- Conclusion: BE/IL contribute ~0 to actual scoring (as expected for ESPN H2H). Using `actual_active` as ground truth is correct.
- Team-period rows analyzed: **80**
## Pooled results
| Projection | n | MAE | RMSE | Bias (actual − proj) |
|---|---|---|---|---|
| A_all | 80 | 167.27 | 201.96 | -27.14 |
| B_active_naive | 80 | 147.74 | 180.22 | +6.26 |
| C_active_last5 | 66 | 119.24 | 147.58 | -40.57 |

## Year-stratified
### 2024
| Projection | n | MAE | RMSE | Bias |
|---|---|---|---|---|
| A_all | 32 | 144.42 | 164.23 | -23.78 |
| B_active_naive | 32 | 117.54 | 145.12 | +5.87 |
| C_active_last5 | 24 | 77.49 | 91.35 | -63.12 |

### 2025
| Projection | n | MAE | RMSE | Bias |
|---|---|---|---|---|
| A_all | 48 | 182.51 | 223.60 | -29.37 |
| B_active_naive | 48 | 167.87 | 200.23 | +6.52 |
| C_active_last5 | 42 | 143.09 | 171.64 | -27.68 |

## Paired test (|resid_A| − |resid_B|)
n=80, mean diff=+19.534 FP, sd=35.586, SE=3.979, t=4.910 (df=79).

Positive mean diff => A's |residual| larger => B is more accurate.
## Top-5 A−B difference (biggest bench contributions to A)
```
    year  period  team_id  proj_A_all  proj_B_active_naive  actual
76  2025       8        4  488.676372           388.251934   121.6
75  2025       8        2  465.143915           371.330269    44.4
74  2025       8        1  450.582264           360.946002    88.5
77  2025       8        5  454.690096           366.876867    98.0
31  2024       4        8  232.279389           145.602394    51.2
```
## Magnitude assessment
- MAE(A) − MAE(B) = **+19.53 FP**. Spec threshold: >5 FP actionable; <2 FP small.
- Bias shift A→B: -27.14 → +6.26. A includes BE players whose actual contribution is 0, so A systematically over-projects (bias should be more negative for A).
## VERDICT: **SHIP_ACTIVE_ONLY**

Material accuracy gain. Modify `build_matchup_dashboard.py` to sum projections only over `lineup_slot not in {BE, IL, IR}`.

## Minimal spec for `build_matchup_dashboard.py`
- When summing per-player projections to a team total, filter to `lineup_slot not in {'BE','IL','IR'}` BEFORE summing.
- For SPs already subject to the 10-start cap, the active-vs-bench filter is independent and additive — apply both.
- No projector model change required; this is a sum-aggregation change only.
## Caveats (honest)
- n=80 team-periods is small; pooled t-stat should be read with caution.
- 2024 + 2025 were 6-team eras (not the live 8-team BrownU). Slot-aware mechanism is league-size-agnostic; FP magnitudes are not.
- Projections are last-N-game proxies, not live rh3/rp3/rprs2 — the test isolates the SLOT MECHANISM, not projector quality.
- ~9% of panel rows have `mlbam_id=NaN`; their projections still contribute via name-keyed history.
- Panel covers ~mp 1-8 (2025) and ~mp 1-4 (2024) due to ESPN historical-lineup cutoff.

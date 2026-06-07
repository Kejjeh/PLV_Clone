# Tier B Veto Empirical Validation

**Generated:** 2026-06-06

**Question.** When Tier A (prior-season FP/g percentile rank) says BUY
but Tier B (xwOBA L21 vs prior-season baseline / SP K% L30 vs prior
season) screams REAL_DECLINE/REGRESS, the production rule downgrades the
verdict one step (BUY -> HOLD). Does that veto actually improve hit rate?

**Method.**
- Snapshot grid: hitters n=1498, SPs n=550 from `shrinkage_*_snap_2026-06-06.parquet` (2024 + 2025, monthly as_of).
- Tier A bucketed by (year, progress): BUY = prior_avg > median, FADE < p25.
- Tier B hitter: gap = L21 xwOBA - prior-yr xwOBA; veto if gap < -0.060 and L21 PA >= 40.
- Tier B SP: drop = prior K% - L30 K% (pp); veto if drop > 8pp and L30 PA >= 50.
- Forward outcome = `target` (next-window FP/g). 'Hit' = target above
  bucket median; otherwise BUY 'would have whiffed.'
- Veto CORRECT = vetoed BUY and target was below median. FALSE = vetoed
  BUY and target was above median. Net FP swing = sum(median - target)
  across vetoed rows; positive means the veto saved FP.

## Results

| Group | N BUY rows | N conflicts | % correct vetoes | % false vetoes | Mean FP swing/veto | Net FP swing |
|---|---:|---:|---:|---:|---:|---:|
| Hitters | 687 | 102 | 52.9% | 47.1% | -0.0 | -1.1 |
| SPs | 230 | 15 | 80.0% | 20.0% | 2.2 | 33.2 |
| Combined (relative) | 917 | 117 | 56.4% | 43.6% | 0.013 (rel) | 1.539 (rel) |

### Detail per group
#### Hitters
- BUY rows: **687**, conflict rows: **102**.
- Vetoes that turned out CORRECT (target < median): **54** (52.9%)
- Vetoes that turned out FALSE   (target >= median): **48** (47.1%)
- Mean target FP on vetoed rows: **2.4**
- Mean target FP on un-vetoed BUY rows: **2.5**
- Bucket-median benchmark on vetoed rows: **2.4**
- Net FP swing if veto applied: **-1.1 FP** (-0.0 per row)

#### SPs
- BUY rows: **230**, conflict rows: **15**.
- Vetoes that turned out CORRECT (target < median): **12** (80.0%)
- Vetoes that turned out FALSE   (target >= median): **3** (20.0%)
- Mean target FP on vetoed rows: **12.6**
- Mean target FP on un-vetoed BUY rows: **14.5**
- Bucket-median benchmark on vetoed rows: **14.9**
- Net FP swing if veto applied: **33.2 FP** (2.2 per row)

#### Combined (relative)
- Hitter and SP targets are on different scales (FP/g vs FP/start) so FP
  swings are not directly summable. The combined row uses bucket-relative
  swing = `(median - target) / |median|`, pooled across both groups.
- Pooled BUY rows: **917**, conflict rows: **117**.
- Vetoes CORRECT: **66** (56.4%)
- Vetoes FALSE:   **51** (43.6%)
- Mean relative swing per veto: **0.013** (positive = veto saved FP relative to median)

## Recommendation
### Hitters
**WEAKEN the veto.** Only 52.9% correct, net swing -1.1 FP. Apply only when Tier B is paired with a second confirming signal (process metric drift, age >=32, IL-adjacent), not as a standalone downgrade rule.

### SPs
**KEEP the Tier B veto.** 80.0% of vetoes were correct, net FP swing +33.2 (2.2/row). The veto reliably rescues FP that a naive BUY would have lost.

### Pooled
Pooled hit rate **56.4%** with mean relative swing **0.013** per veto. Veto is at coin-flip; keep only where per-group evidence supports it (see SP section).
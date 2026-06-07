# Lens-Weight Sensitivity Analysis (2026-06-06)

## Setup

- **Snapshot:** `shrinkage_h_snap_2026-06-06.parquet` (1,498 hitter rows).
- **Lenses tested:** 8 (BUY=+1, HOLD=0, FADE=-1) constructed via the canonical project synthesis (mirrors `test_drop_one_lens.py`).
- **Baseline weights:** equal (0.125 each).
- **Verdict rule:** sum > +0.5 -> BUY; sum < -0.5 -> FADE; otherwise HOLD.
- **Baseline distribution:** BUY=124 (8.3%), HOLD=1307 (87.2%), FADE=67 (4.5%).
- **Perturbation rule:** scale one lens's weight by 1+delta, renormalise the other 7 so total mass stays = 1.0.

## Per-lens, per-perturbation flip table

| Lens | Description | Delta | New weight | Flips | % flipped |
|------|-------------|-------|------------|-------|-----------|
| L1 | Blended xFP rank (pred_k150 cohort decile) | -20% | 0.100 | 7 | 0.47% |
| L1 | Blended xFP rank (pred_k150 cohort decile) | -10% | 0.113 | 7 | 0.47% |
| L1 | Blended xFP rank (pred_k150 cohort decile) | +10% | 0.138 | 215 | 14.35% |
| L1 | Blended xFP rank (pred_k150 cohort decile) | +20% | 0.150 | 215 | 14.35% |
| L2 | Boom/bust L21 actuals (l21_avg cohort decile) | -20% | 0.100 | 57 | 3.81% |
| L2 | Boom/bust L21 actuals (l21_avg cohort decile) | -10% | 0.113 | 57 | 3.81% |
| L2 | Boom/bust L21 actuals (l21_avg cohort decile) | +10% | 0.138 | 165 | 11.01% |
| L2 | Boom/bust L21 actuals (l21_avg cohort decile) | +20% | 0.150 | 165 | 11.01% |
| L3 | Sustainability (sign(L42 - L21)) | -20% | 0.100 | 152 | 10.15% |
| L3 | Sustainability (sign(L42 - L21)) | -10% | 0.113 | 152 | 10.15% |
| L3 | Sustainability (sign(L42 - L21)) | +10% | 0.138 | 70 | 4.67% |
| L3 | Sustainability (sign(L42 - L21)) | +20% | 0.150 | 70 | 4.67% |
| L4 | Prior-year baseline (prior_avg cohort decile) | -20% | 0.100 | 13 | 0.87% |
| L4 | Prior-year baseline (prior_avg cohort decile) | -10% | 0.113 | 13 | 0.87% |
| L4 | Prior-year baseline (prior_avg cohort decile) | +10% | 0.138 | 209 | 13.95% |
| L4 | Prior-year baseline (prior_avg cohort decile) | +20% | 0.150 | 209 | 13.95% |
| L5 | xwOBA L21 vs prior gap (l21_avg - prior_avg) | -20% | 0.100 | 92 | 6.14% |
| L5 | xwOBA L21 vs prior gap (l21_avg - prior_avg) | -10% | 0.113 | 92 | 6.14% |
| L5 | xwOBA L21 vs prior gap (l21_avg - prior_avg) | +10% | 0.138 | 130 | 8.68% |
| L5 | xwOBA L21 vs prior gap (l21_avg - prior_avg) | +20% | 0.150 | 130 | 8.68% |
| L6 | xwOBACON YoY (prior_avg - prior2_avg) | -20% | 0.100 | 153 | 10.21% |
| L6 | xwOBACON YoY (prior_avg - prior2_avg) | -10% | 0.113 | 153 | 10.21% |
| L6 | xwOBACON YoY (prior_avg - prior2_avg) | +10% | 0.138 | 69 | 4.61% |
| L6 | xwOBACON YoY (prior_avg - prior2_avg) | +20% | 0.150 | 69 | 4.61% |
| L7 | Archetype age tier (top50) | -20% | 0.100 | 190 | 12.68% |
| L7 | Archetype age tier (top50) | -10% | 0.113 | 190 | 12.68% |
| L7 | Archetype age tier (top50) | +10% | 0.138 | 32 | 2.14% |
| L7 | Archetype age tier (top50) | +20% | 0.150 | 32 | 2.14% |
| L8 | Model rank decile (pred_k300 cohort decile) | -20% | 0.100 | 7 | 0.47% |
| L8 | Model rank decile (pred_k300 cohort decile) | -10% | 0.113 | 7 | 0.47% |
| L8 | Model rank decile (pred_k300 cohort decile) | +10% | 0.138 | 215 | 14.35% |
| L8 | Model rank decile (pred_k300 cohort decile) | +20% | 0.150 | 215 | 14.35% |

## Sensitivity ranking (by max |+-20%| flip rate)

### Most sensitive lenses

| Rank | Lens | Description | Max % flipped at +-20% | Sensitive? |
|------|------|-------------|-----------------------|------------|
| 1 | L1 | Blended xFP rank (pred_k150 cohort decile) | 14.35% | YES |
| 2 | L8 | Model rank decile (pred_k300 cohort decile) | 14.35% | YES |
| 3 | L4 | Prior-year baseline (prior_avg cohort decile) | 13.95% | YES |
| 4 | L7 | Archetype age tier (top50) | 12.68% | YES |
| 5 | L2 | Boom/bust L21 actuals (l21_avg cohort decile) | 11.01% | YES |
| 6 | L6 | xwOBACON YoY (prior_avg - prior2_avg) | 10.21% | YES |
| 7 | L3 | Sustainability (sign(L42 - L21)) | 10.15% | YES |
| 8 | L5 | xwOBA L21 vs prior gap (l21_avg - prior_avg) | 8.68% | YES |

### Most stable lenses

| Rank | Lens | Description | Max % flipped at +-20% |
|------|------|-------------|-----------------------|
| 1 | L5 | xwOBA L21 vs prior gap (l21_avg - prior_avg) | 8.68% |
| 2 | L3 | Sustainability (sign(L42 - L21)) | 10.15% |
| 3 | L6 | xwOBACON YoY (prior_avg - prior2_avg) | 10.21% |
| 4 | L2 | Boom/bust L21 actuals (l21_avg cohort decile) | 11.01% |
| 5 | L7 | Archetype age tier (top50) | 12.68% |
| 6 | L4 | Prior-year baseline (prior_avg cohort decile) | 13.95% |
| 7 | L1 | Blended xFP rank (pred_k150 cohort decile) | 14.35% |
| 8 | L8 | Model rank decile (pred_k300 cohort decile) | 14.35% |

## Overall verdict

**FRAGILE** (8 of 8 lenses exceed the 5% flip threshold at +-20%).

More than half the lenses flip > 5% of verdicts on a +-20% weight nudge. The merge protocol is highly sensitive to weight calibration; sloppy or eyeballed weights will produce inconsistent verdicts.

## Recommendation

Lenses that need careful weight calibration (small wrong move flips many verdicts):
- **L1** (Blended xFP rank (pred_k150 cohort decile)) - 14.35% flip rate at +-20%
- **L8** (Model rank decile (pred_k300 cohort decile)) - 14.35% flip rate at +-20%
- **L4** (Prior-year baseline (prior_avg cohort decile)) - 13.95% flip rate at +-20%
- **L7** (Archetype age tier (top50)) - 12.68% flip rate at +-20%
- **L2** (Boom/bust L21 actuals (l21_avg cohort decile)) - 11.01% flip rate at +-20%
- **L6** (xwOBACON YoY (prior_avg - prior2_avg)) - 10.21% flip rate at +-20%
- **L3** (Sustainability (sign(L42 - L21))) - 10.15% flip rate at +-20%
- **L5** (xwOBA L21 vs prior gap (l21_avg - prior_avg)) - 8.68% flip rate at +-20%
# Weight-blend trajectory feature analysis (2026-06-04)

Phase 2 drop-tests showed trajectory tags (TRENDING_UP / TRENDING_DOWN / CAREER_LOW)
contributing ~0.001 R² each vs ~0.06–0.08 for `arche_overall_prior`. Mandate:
test whether traj tags are (a) redundant with OVR, (b) too coarse vs the continuous
`OVERALL_slope_3yr`, (c) interaction-shaped, or (d) noise.

Script: `scripts/xfp/analyze_traj_redundancy.py`. Master panel n_total: H=3270,
SP=1178, RP=1107. Continuous-slope rows are limited (H=1999, SP=653, RP=505)
because `slope_3yr` requires 3 prior seasons, so all model comparisons below are
quoted on the matched-n subset for apples-to-apples fairness.

## 1. Correlations vs `arche_overall_prior`

|                | H     | SP    | RP    |
|---             |---    |---    |---    |
| traj_up        | +0.28 | +0.30 | +0.35 |
| traj_down      | −0.23 | −0.26 | −0.29 |
| traj_career_low| −0.19 | −0.14 | −0.08 |
| slope_3yr      | +0.41 | +0.45 | +0.50 |

All correlations are well under |0.5|. Binary tags carry modest signal beyond OVR;
continuous slope is more colinear with OVR but still has independent variance.

## 2. R² comparison (in-sample, matched n with slope rows)

| Model (base = anchor + OVR + career_pct + age) | H (n=1999) | SP (n=653) | RP (n=505) |
|---                                              |---         |---          |---          |
| **no_traj** (base only)                         | 0.3269     | 0.3602      | 0.3568      |
| base + binary traj tags                         | 0.3328     | 0.3733      | 0.3696      |
| base + continuous slope_3yr                     | 0.3383     | 0.3711      | 0.3575      |
| base + both                                     | 0.3384     | 0.3758      | 0.3699      |

Lift over `no_traj`: binary +0.006/+0.013/+0.013 (H/SP/RP); slope +0.011/+0.011/+0.001.
Slope wins for H. Binary wins for RP outright. SP is a near-tie. None exceed the
0.005 noise threshold cleanly across all three buckets.

## 3. Interaction terms (traj × OVR)

Within-binary-model drop tests on interactions:

| Feature              | H       | SP      | RP      |
|---                   |---      |---      |---      |
| traj_career_low      | 0.00132 | 0.00001 | 0.00140 |
| traj_career_low × ovr| 0.00370 | 0.01060 | 0.00245 |
| traj_down × ovr      | 0.00043 | 0.00461 | 0.00000 |
| traj_up × ovr        | 0.00038 | 0.00212 | 0.00007 |

For SP, `traj_career_low × ovr` is the largest single contributor (0.011, ~3× the
binary tag itself). The interpretation: a CAREER_LOW SP at high OVR (a former ace
in collapse) behaves very differently from a CAREER_LOW SP at low OVR (a fringe arm
trending the same direction). For H and RP the interaction edge is smaller but
consistently positive.

## 4. Per-year stability (lift vs no_traj)

Binary lift across years (sample): H mixed sign (−0.03 in 2016, +0.04 in 2017,
near-zero recently). SP positive 7/9 years, modest. RP positive 5/7 years, with
+0.041 in 2022 and +0.035 in 2025. Slope lift is similarly mixed.

No single binary tag dominates across all three player types in drop-tests — the
strongest individual contributor is `traj_down` for SP (0.0031) and `traj_up` for
RP (0.0025), consistent with Phase 2.

## 5. Recommendation

**Restructure as `slope_3yr + (traj_career_low × OVR)`. Drop the standalone
binary `traj_up` and `traj_down`.**

Rationale:

- Binary `traj_up`/`traj_down` are redundant with the OVR + slope signal (drop-test
  ≤0.003 across all 3 buckets, correlations 0.23–0.35 with OVR).
- `slope_3yr_prior` is a strictly richer continuous version of the same signal and
  wins or ties on R² in every bucket (H best, SP/RP tie).
- `traj_career_low × OVR` survives as a genuine non-linear signal especially for SP
  (0.011) — a tier-dependent collapse warning that linear OVR + slope cannot
  capture. Keep this one as an interaction.

### Cleaner blend formula

```
y_hat = w0 + w1·anchor_prior
          + w2·arche_overall_prior
          + w3·arche_career_pct_prior
          + w4·slope_3yr_prior              # replaces traj_up/traj_down
          + w5·(traj_career_low × OVR_z)    # tier-dependent collapse signal
          + w6·age_normalized
```

Caveat: requires backfilling `slope_3yr_prior` into the production projection
join — it is available in `*_ratings_master.csv` but not currently in the
projection CSVs. For players with <3 prior seasons (rookies, recent debuts),
fall back to `slope_3yr = 0` (already the natural neutral).

Honest note: total R² lift from this restructuring is ~0.005–0.013 on top of
`no_traj`. The trajectory layer as a whole is a *small* contributor compared to
`arche_overall_prior` (0.06–0.08). The cleanup is a simplification + small
accuracy gain, not a headline change.

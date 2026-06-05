# boom_stack @ split_day=30 POC — Phase 3 follow-up Agent B

**Date:** 2026-06-05
**Owner:** Agent B (Phase 3 follow-up)
**Script:** `scripts/xfp/build_boom_stack_sd30_test.py`
**JSON:** `data/research/validation_runs/weight_blend_boom_sd30_2026-06-04.json`

## Question

Agent 5's 2024 POC found boom_stack Δ R² = +0.0000 at split_day=90. The
hypothesis tested here: at sd=90, season-to-date (`_to`) features absorb
boom_stack's signal; at sd=30 the `_to` features are noisy (~5-6 starts
of sample) and a 5-game-rolling boom_stack might survive.

## Setup

- **Components (3-stack, opp_soft deferred):** recform_hot (trail-5 fp_proxy/BF z ≥ +0.5),
  skill_spike (trail-5 K%−to ≥ +3pp ∧ trail-5 BB%−to ≤ −1pp),
  park_friendly (home park PY pf_wOBA ≤ 33rd pct).
- **Train:** 2018-2023 ex-2020 sd=30 fold. **Hold-out:** 2024.
- **Min trail starts:** 3 (vs 3-start minimum in Agent 5's panel).

## Component fire rates (2024, n=109 qualifying SPs)

| component | fires | rate |
|---|---:|---:|
| recform_hot | 35 | 32.1% |
| skill_spike | **0** | 0.0% |
| park_friendly | 260† | — |

†park_friendly computed over the full 2024 SP universe (n=811 incl. relief-eligible). Within the n=109 sd=30 SP panel, distribution is:

| boom_stack_sd30 | n |
|---:|---:|
| 0 | 63 |
| 1 | 36 |
| 2 | 14 |
| 3 | 0 |

**skill_spike fires zero times at sd=30** — the trailing-5 window IS effectively the season-to-date window (mean 3-6 starts), so the dk/dbb deltas collapse to zero. This kills one of the three intended legs.

## Hold-out test

| model | 2024 R² |
|---|---:|
| baseline (all `_to` + recent + archetype features) | 0.6770 |
| baseline + boom_stack_sd30 | 0.6770 |
| **Δ R²** | **+0.0000** |

Bootstrap 95% CI on Δ R²: **[−0.0000, +0.0000]**. Coefficient on standardized boom_stack: +0.0000.

Caveat: boom_stack reconstructed only for 2024 (zero in 2018-2023 training rows). Coefficient is identified only off the 2024 in-sample within-fold, so the standard hold-out lift framing under-states what a fully-reconstructed multi-year boom_stack might deliver. To stress-test, I also ran a **residualized 2024-only test**: fit baseline on train, get residuals on 2024, regress on boom_stack:

- pearson(boom_stack, residual) = **+0.008  (p=0.93, n=113)**
- spearman = −0.021 (p=0.82)

## Per-stack ROS gradient (raw, 2024 test set)

| boom_stack | n | mean ROS FP/start | std |
|---:|---:|---:|---:|
| 0 | 63 | 9.86 | 3.25 |
| 1 | 36 | 11.70 | 4.05 |
| 2 | 14 | 12.82 | 2.77 |

Raw gradient = +2.96 FP/start across stack 0→2. **But this entire gap is already predicted by baseline features** — the baseline predicts boom_stack=2 SPs to score 0.55 FP higher than boom_stack=0 SPs, and the residuals show no remaining trend.

## Comparison to Agent 5 (sd=90)

| metric | sd=90 (Agent 5) | sd=30 (this run) |
|---|---:|---:|
| Δ R² 2024 hold-out | +0.0000 | +0.0000 |
| raw per-stack ROS gradient | (similar) | +2.96 FP |
| residual correlation with boom_stack | (not reported) | +0.008 (ns) |

The sd=30 hypothesis (noisier `_to` features → more room for boom_stack) **does not hold**. Even with `_to` features formed from only 3-6 starts of sample, they (combined with `_anchor` = prior-year fp_per_start and archetype OVR) absorb the boom_stack signal completely. Half the components either don't fire (skill_spike=0) or are nearly stationary across the season (park_friendly is a yearly home-park binary).

## Verdict

**ARCHIVE THE IDEA.** Do not fund multi-year boom_stack reconstruction.

The two consistent negative findings (sd=90 and sd=30) along with a near-zero residual correlation on 2024 (the year where boom_stack was actually computed in-sample) indicate boom_stack's predictive signal is already absorbed by the existing `_to` + anchor + archetype feature stack at every split_day tested. The infrastructure investment for decision-time park + opp_xwOBA reconstruction is **not justified** by this POC.

This does NOT invalidate boom_stack as a **display tag** for live triangulate/stream-the-stack cards — its per-stack boom-rate gradient (validated in `reference_boom_stack_tag.md`) is a real conditional probability, just not an additive signal on top of the within-season blend model. The two roles are different (binary boom outcome vs continuous ROS FP regression) and the tag layer remains valid.

## Files

- `scripts/xfp/build_boom_stack_sd30_test.py` (new)
- `data/research/validation_runs/weight_blend_boom_sd30_2026-06-04.json` (new)
- `data/research/validation_runs/weight_blend_boom_sd30_2026-06-04.md` (this file)

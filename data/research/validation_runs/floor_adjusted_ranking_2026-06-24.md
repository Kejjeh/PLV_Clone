# Floor-adjusted (risk-aware) H2H ranking — validation + ship record

**Date:** 2026-06-24
**Status:** SHIPPED (decision-layer; Rule-13 context-only, registered `floor_adjusted` family)
**Trigger:** "rp3 makes José Soriano look better than he is" — can we make rp3 better at RoS FP?

## What was tested and rejected

Four proposed rp3 improvements, tested leakage-safe through the model's OWN harness
(`cross_year_eval`, 7-fold leave-one-year-out, RidgeCV, pooled Pearson r, +0.005 gate),
on the 19,111-row filtered panel. Engineered from the snapshot panel using only
current+past snapshots (no target/future leakage).

| Idea | feature(s) | Δr vs 24-feat baseline (r=0.5546) | verdict |
|---|---|---|---|
| ① within-season **slope/trend** | OLS slope of recent K-BB% / velo / FP | −0.0002 / −0.0003 / −0.0001 | FAIL |
| ② **xFP anchor** (rate-implied) | fold-safe rates→FP, add & swap | +0.0001 / −0.0004 | FAIL |
| ③ **EWMA** recency of rates | span-3 ewm K-BB% + gap | −0.0005 / +0.0001 | FAIL |
| ④ **change-point** regime gap | recent-3 minus early-season K-BB% | −0.0006 | FAIL |

All within ±0.0006 of zero — an order of magnitude below the +0.005 gate. Script:
`scripts/_oneoff/validate_rp3_ideas.py`.

**Why:** (a) redundancy with the existing 6 drift deltas; (b) RoS FP is noisy and
**mean-reverting**, so trend-extrapolation actively hurts OOS. The level+shrinkage design
is correct for a point forecast. (Confirms the prior rejection of last-21 features.)

## Then: does trajectory predict the DOWNSIDE (bust), not the mean?

Tested the same trajectory family on the **sp_floor** model's own frame/target/split
(per-start bust = fp<5, train 2018-22 → test 2023-25, AUC). Script:
`scripts/_oneoff/validate_floor_trajectory.py`.

| + candidate (per-start, leakage-safe) | AUC | ΔAUC |
|---|---|---|
| baseline (prior_k_pct,prior_bb_pct,lineup_xfp,days_rest,n_prior) | 0.6006 | — |
| traj_slope / ewma_gap / rec3_gap / regime | 0.6001 / 0.6005 / 0.6003 / 0.6002 | ≈0 |
| all four | 0.5997 | −0.0009 |

Bootstrap ΔAUC (all-4, 400 resamples): mean −0.0008, **95% CI [−0.0024, +0.0008]**,
P(Δ>0)=16% → not significant, leans negative. Even bust risk mean-reverts; the
cumulative command **level** already carries the decline.

## Conclusion → what shipped

Trajectory is a great **explanatory/context** lens (tells the story of *why* an arm
declined) but a **non-predictive modeling feature** for both mean and downside — exactly
what Rule 13 already asserts. So **no model change.** Instead, surface the validated
sp_floor bust risk in the DECISION layer:

```
floor_adj_xfp = rp3_mean − λ·(bust_prob − 0.27)·9        # λ=0.5 (risk-aversion knob)
floor_flag    = FLOOR-RISK (penalty ≥ 0.8) | SAFE-FLOOR (penalty ≤ −0.5) | None
```

Surfaced in triangulate: `floor_adj_xfp` / `floor_adj_penalty` / `floor_flag` columns +
`floor_adj_rank` (risk-aware within-bucket rank) + a card line + a grid marker (→X⚠/✓).
Headline (rp3/blended) UNCHANGED. Engine: `lib/extra_lenses.floor_adjusted_xfp`.

## The honest Soriano result (read this before "drop Soriano")

Applied live to the four arms in question:

| arm | rp3 mean | bust% | floor_adj | floor_adj_rank |
|---|---|---|---|---|
| **Soriano** | 11.65 (#39) | 22% | **11.88** | **1** |
| Bradish | 11.63 (#40) | 27% | 11.64 | 2 |
| Bibee | 10.99 (#61) | 28% | 10.95 | 3 |
| Weathers | 10.23 (#82) | 19% | 10.60 | 4 |

The tool does **NOT** flag Soriano — it rates him *best of the four*. His high K% (97-mph
velo → strikeouts) gives him a **below-base bust probability (22%)** despite the walks; Ks
protect the floor. **Every validated lens (mean, floor, floor_adj) says Soriano is a fine
~11.6 FP arm.** Only RECENT FORM (63% bust L8) is down on him — and recent form is exactly
what we just proved is non-predictive OOS. So dropping Soriano is **selling low against the
validated models**; it's a conviction/variance-management call, not a model-supported one.
The validation discipline did its job twice: it refuted the feature ideas, then refuted the
premise that the models overrate him.

## Follow-on: the stuff-vs-command divergence flag (`stuff_command_lens`)

Built same day to answer "can we flag Soriano without overfitting?" The key distinction the
floor/mean models can't express: **STUFF decays permanently; COMMAND wobbles revert.** So a
context lens classifies the *type* of decline from PROCESS signals (not outcome trajectory,
which is non-predictive):

- **STUFF-DECLINE** — SwStr%/velo eroding **in-season** (recent vs early 2026) OR **year-over-year**
  (2026 vs 2025 SwStr, gated on a real prior-year sample so post-TJ arms don't false-flag) →
  structural, persistent, a sell candidate.
- **COMMAND-WATCH** — stuff intact (in-season AND YoY) but walks up / zone% down → usually
  reversible; a yellow flag, NOT a sell.

Live, on the four arms in the Soriano/Warren-for-Bradish/Bibee decision:

| arm | rp3# | floor_adj (rank) | stuff_cmd | read |
|---|---|---|---|---|
| **Soriano** | 39 | 11.88 (1) | **COMMAND-WATCH** (SwStr YoY **+3.2**, BB +7.2) | stuff *improving*, command wobble → reversible, **hold** |
| **Warren** | 96 | 10.26 (4) | **STUFF-DECLINE** (SwStr in-season **−2.3**) | swing-and-miss eroding → structural → **the right drop** |
| Bradish | 40 | 11.64 (2) | none | clean (TJ YoY false-positive correctly gated out) |
| Bibee | 61 | 10.95 (3) | none | clean |

Validates the Soriano/Framber contrast: **Framber = STUFF-DECLINE** (SwStr 12.4→10.1 YoY),
**Soriano = COMMAND-WATCH** (SwStr rising YoY, only walks up). The flag is context-only
(Rule-13, registered `stuff_command` family), experimental (thresholds reasoned, not backtested).
Engine: `lib/extra_lenses.{classify_stuff_command, stuff_command_lens}`. Decision import: it
endorses **dropping Warren** (structural) but argues **against dropping Soriano** (reversible,
stuff improving) — drop Warren → add Bradish; hold Soriano unless his *stuff* (not his walks)
starts to slide.

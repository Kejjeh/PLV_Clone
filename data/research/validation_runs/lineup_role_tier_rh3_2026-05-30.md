---
signal: lineup_role_tier_prior
formula: prior-year (T-1) aggregate lineup features from hitter_lineup_features_2018_2026.csv — mean_lineup_spot (continuous, PA-weighted mean batting-order slot), top5_share (continuous, fraction of starts in slots 1-5), lineup_role_tier (categorical one-hot: LEADOFF / TOP_ORDER / HEART_OF_ORDER / MIDDLE_ORDER / BOTTOM_ORDER / ROTATIONAL)
outcome: ros_full_fp_per_pa (rh3's standard target — rest-of-season FP per PA from the cutoff)
expected_sign: continuous mean_lineup_spot − (lower spot number = better lineup position = higher RoS FP/PA); continuous top5_share +; categorical tiers — HEART_OF_ORDER / TOP_ORDER coef +, BOTTOM_ORDER / ROTATIONAL coef −
theory: A hitter's role in the batting order is sticky year-over-year (raw YoY r = 0.682 per HITTER_EXTERNAL_SIGNALS.md) and lineup spot correlates with FP/PA at ±0.55 contemporaneously and ±0.35 one year ahead. Prior-year role tier may carry independent context (PA opportunity, RBI/R counting-stat exposure) over and above current-year cumulative rate stats already in RH3_FEATS.
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/_research/validate_lineup_role_tier.py
date: 2026-05-30
verdict: MARGINAL
purpose: User flagged lineup_role_tier as a candidate input to rh3 after the column was added to hitter_ratings_master.csv as display-only context. Raw YoY r=0.682 and same-year r=±0.55 suggested potential lift; goal is to determine whether prior-year role-tier features add ≥+0.005 partial r over the full 17-feature RH3_FEATS baseline (Rule 9). Existing same-year `lineup_spot_to` already MARGINAL (Δr +0.0009, 2026-05-23) — this run tests whether the more stable PRIOR-YEAR aggregate clears the gate that the noisy cumulative version did not.
---

## Pre-registration: lineup_role_tier_prior → rh3 (2026-05-30)

### Hypothesis

H0: Adding prior-year (T-1) lineup-role features to the full RH3_FEATS
baseline produces Δr < +0.005 vs baseline alone on held-out cross-year
evaluation (2024 and 2025).

H1: Adding prior-year lineup-role features lifts cross-year r by
≥ +0.005 vs the full RH3_FEATS baseline, with consistent sign in
≥ 5 of 7 training years and ≥ 1 of 2 holdout years (2024-2025) positive.

### Rule 9 baseline (production feature set as of 2026-05-30)

The exact RH3_FEATS list from `src/plv_clone/models/xfp/rh3.py` is:

```
RH3_FEATS = [
  # Cumulative shrunken rates (RH2)
  'iso_to_sh', 'k_pct_to_sh', 'hr_per_pa_to_sh', 'hard_hit_pct_to_sh',
  'contact_pct_to_sh', 'whiff_pct_to_sh', 'swstr_pct_to_sh', 'bb_pct_to_sh',
  'chase_pct_to_sh', 'in_play_pct_to_sh', 'sb_per_pa_to_sh',
  'xwoba_per_pa_to_sh', 'barrel_pct_to_sh',
  # Prior + sample-size cues
  'prior_fp_per_pa', 'prior_pa_eff', 'pa_to', 'split_day',
  # H2 + xwOBA residual + career stage + opp-SP schedule
  'lift_h2_aug150', 'xwoba_residual_career', 'career_stage',
  'ros_opp_sp_xwoba_weighted',
]
```

21 features total. Baseline already includes:
- in-season cumulative xwoba_per_pa_to_sh (rate-stat skill)
- career_stage (age proxy)
- prior_fp_per_pa (Marcel prior — encodes RBI/R-driven FP indirectly)
- pa_to (volume / opportunity proxy)

The candidate prior-year lineup features must beat the residual after
all of the above are already in the model.

### Treatments

| Treatment | Features over baseline | Notes |
|---|---|---|
| A | none (baseline) | RH3_FEATS only |
| B | + mean_lineup_spot_prior | continuous PA-weighted mean spot at year T-1 |
| C | + top5_share_prior | continuous share of PAs in slots 1-5 at year T-1 |
| D | + tier one-hots (5 cols, MIDDLE_ORDER dropped as baseline) | one-hots from lineup_role_tier at year T-1 |
| E | + mean_lineup_spot_prior + top5_share_prior + tier one-hots | combined |

### Pass criteria (3-part gate)

1. **Effect size**: Δr ≥ +0.005 vs baseline (overall pooled cross-year r).
2. **Year consistency**: Δr > 0 in ≥ 5 of 7 training years (Rule 2b).
3. **Holdout replication**: Δr > 0 in BOTH 2024 AND 2025 (strict —
   matches the bar applied to other recent rh3 candidates like
   ros_opp_sp_xwoba_weighted PASS 2/2).

### Coverage / sample-size pre-check (Rule 5)

Lineup-features cache covers 2018-2026 (n=4228 batter-years). Prior-year
features require year T-1 to exist:
- 2018 outcomes: NO prior (T-1 = 2017 not in cache) → treat as NaN→median fill
- 2019: prior 2018 available
- 2020: dropped (rh3 already excludes 2020)
- 2021: prior 2020 (COVID short season — short PA samples, fill if PA<50)
- 2022-2026: prior years all available

Per-year n: ~330-530 batter-years per year > 200 pooled minimum.
Training set excluding 2020 = 5 years (2018, 2019, 2021, 2022, 2023). Plus
holdout 2024 + 2025 = 7 evaluated years. Clears Rule 2b 5-of-7 bar.

### NaN-fill protocol

For 2018 and any batter without a prior-year lineup-features row, fill
with the training-year MEDIAN of the candidate column (computed only on
rows that have a real prior, on training years 2019, 2021, 2022, 2023).
For the categorical tier, fill missing as 'MIDDLE_ORDER' (the modal /
ambiguous category) so the one-hots are all zero — this prevents the
fill choice from injecting signal.

Baseline and extended evaluations both use the same row set (any row
with NaN in non-candidate features is dropped equally).

### Honest expectations

The same-year r=±0.55 and YoY r=0.682 cited in research are RAW
correlations. The 4× over-claim from rh3 v2 (2026-05-13) showed that
partial r against the FULL production baseline routinely shrinks 75%+
once career_stage, prior_fp_per_pa, xwoba_per_pa_to_sh, and pa_to are
controlled for. Most of the lineup-spot signal is plausibly downstream
of (skill → role assignment), and skill is what RH3_FEATS already
encodes via rate stats + career_stage.

Predicted outcome: MARGINAL or REJECTED. Will be surprised but pleased
if any treatment clears +0.005 — that would be the second-strongest
single-feature lift in the last 30 rh3 attempts.

### Results (run 2026-05-30)

Baseline RH3_FEATS pooled cross-year r = **0.6287** (n=36,571 batter-year×split_day snapshots).

| Treatment | Δr overall | Per-year +/7 | Holdout 2024 Δr | Holdout 2025 Δr | Verdict |
|---|---|---|---|---|---|
| B (mean_lineup_spot_prior) | **+0.0021** | 4/7 | +0.0038 | +0.0041 | MARGINAL |
| C (top5_share_prior) | **+0.0019** | 4/7 | +0.0048 | +0.0044 | MARGINAL |
| D (tier one-hots, 5 cols) | **+0.0020** | 4/7 | +0.0040 | +0.0042 | MARGINAL |
| E (combined, 7 cols) | **+0.0019** | 4/7 | +0.0048 | +0.0055 | MARGINAL |

Per-year deltas (E, combined):

| Year | Δr | sign |
|---|---|---|
| 2018 | -0.0010 | (−) |
| 2019 | +0.0013 | (+) |
| 2021 | +0.0090 | (+) |
| 2022 | -0.0047 | (−) |
| 2023 | -0.0014 | (−) |
| 2024 | +0.0048 | (+) |
| 2025 | +0.0055 | (+) |

**Coefficient signs (Treatment E, n_train=36,571 — all directionally sensible):**

| Feature | Coef | Expected | OK? |
|---|---|---|---|
| mean_lineup_spot_prior | -0.0093 | − | OK |
| top5_share_prior | +0.0012 | + | OK |
| tier__LEADOFF | -0.0010 | + (expected; got near-zero) | weak |
| tier__TOP_ORDER | +0.0027 | + | OK |
| tier__HEART_OF_ORDER | +0.0047 | + | OK |
| tier__BOTTOM_ORDER | +0.0028 | − (UNEXPECTED — small positive) | wrong-sign |
| tier__ROTATIONAL | -0.0015 | − | OK |

Coefs mostly directionally clean. BOTTOM_ORDER small-positive is mild Simpson's effect — the continuous mean_lineup_spot already absorbs the "lower slot = worse" signal, so the BOTTOM tier indicator captures residual variance among players already classified as low-slot.

### Verdict

**MARGINAL — all 4 treatments.** None clears the +0.005 effect-size gate.
Per-year consistency fails 5/7 bar (only 4/7 positive — 2022 and 2023 are
consistently negative across all treatments). Holdout 2024+2025 is the
**strongest part of the result**: both years positive across all treatments
(+0.0038 to +0.0055), which means the signal is real in the years that
matter most — but the pooled cross-year r doesn't move enough to clear
the strict Rule 9 bar.

### Honest reading of "why the same-year r=0.55 didn't translate"

This is the canonical 4× over-claim story from rh3 v2:

1. **Same-year r=0.55 was contemporaneous** — included lineup spots from
   games inside the predicted window. Of course they correlate.
2. **YoY r=0.682 measures role stickiness, not predictive lift over a
   baseline that already encodes the underlying skill.**
3. **Most of "role" is downstream of skill.** RH3_FEATS already has
   xwoba_per_pa_to_sh, iso_to_sh, k_pct_to_sh, career_stage, and
   prior_fp_per_pa. Lineup role is what a manager assigns AFTER seeing
   that skill profile. The unique-to-role signal (manager preference,
   org context, batting-order construction) only contributes ~+0.002 r.
4. **Holdout-strong, training-mixed pattern** (2/2 holdout positive but
   only 4/7 training positive) suggests the signal IS slightly more
   predictive in recent years — possibly tied to more-stable post-2023
   lineup construction — but the pooled cross-year r flattens it.

### Recommendation

**Keep `lineup_role_tier` as display-only context** in
hitter_ratings_master.csv. **Do NOT add to RH3_FEATS.** Lift exists
(directionally clean, holdout-positive) but at +0.002 magnitude it is
below the rh3 promotion gate and would not move any add/drop decision.

### Comparable closed dead-ends

| Run | Δr vs full baseline | Verdict |
|---|---|---|
| lineup_spot_to (cumulative, in-season) | +0.0009 | MARGINAL (2026-05-23) |
| lineup_spot_early (I[sd≤60] mask) | +0.0014 | MARGINAL (2026-05-24) |
| lineup_spot_decay (exp(-sd/30)) | +0.0015 | MARGINAL (2026-05-24) |
| lineup_role_tier_prior (this run, combined) | +0.0019 | MARGINAL (2026-05-30) |

Four lineup-spot framings tested across 3 sessions. All MARGINAL, none
PASS. **This closes the lineup-spot line of inquiry for rh3.** Any
future re-test would need a fundamentally different framing — e.g.,
manager-stickiness interaction with career_stage, or PA-projected
opportunity delta vs prior year — not yet another way to encode "where
in the lineup the hitter is hitting."

### Pre-registration → results integrity

Hypothesis, baseline (21 features), 5-treatment list, gate (+0.005 lift,
≥5/7 positives, 2/2 holdout), NaN-fill protocol, and training/holdout
years (2018-2023 train, 2024-2025 holdout) were all locked BEFORE
results were inspected. Rule 1 (pre-registration) satisfied. Rule 9
satisfied — baseline includes all 21 production features. Rule 5
satisfied — 36,571 pooled n; each year > 200.

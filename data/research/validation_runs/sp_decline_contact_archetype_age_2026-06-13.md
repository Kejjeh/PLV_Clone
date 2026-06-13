# SP RoS-Decline Signals — Contact-Quality / Archetype / Age

**Date:** 2026-06-13
**Question:** Which in-season CONTACT-QUALITY / ARCHETYPE / AGE decline signals best
predict a starting pitcher's rest-of-season FP **decline** (catch Framber-Valdez vets
early)? Velo / whiff / K / Stuff+-slope deliberately EXCLUDED (separate agent).
**Script:** `scripts/research/sp_decline_contact_archetype_age.py`

## Method (leakage discipline — `lens_value_add_2026-06-11.md`)

- **As-of features only.** Contact signals = recent 21-day window (`_last21`) minus
  season-to-date cumulative (`_to`). Archetype signals = PRIOR completed-year ratings
  only (prior2→prior YoY deltas), never the in-progress year.
- **Base projection** = season-to-date FP/start (`fp_per_start_to`), the naive
  carry-forward baseline.
- **Targets:** (a) realized RoS FP/start; (b) DECLINE = RoS − to-date; (c) binary
  material decline = RoS drops >2 FP below to-date (**base rate 37.1%**, n=17,201).
- **Incremental value over base** (Rule 9): partial r controlling for base; logistic
  ΔAUC `[base]` vs `[base+sig]`.
- **Player-clustered** GroupKFold (cluster = pitcher) for AUC; **cluster-bootstrap**
  (pitcher) 95% CIs for partial r; **convergence curve** across split_day bands as a
  leakage check (a real as-of signal should be roughly flat, not decaying late-season).
- Sample: gs_to ≥ 6 and ros_gs ≥ 4. n ≈ 16.5k start-split rows for contact, 4–9k for
  archetype (limited by YoY history availability).

## Ranked results (by |partial r| predicting DECLINE)

| signal | desc | n | partial_r | 95% CI | CI excl 0 | ΔAUC | auc_full |
|---|---|---|---|---|---|---|---|
| **overall_slope** | OVERALL 3yr declining trajectory (neg slope) | 8881 | **−0.063** | [−0.128, −0.0005] | **YES** | +0.0008 | 0.661 |
| stuff_yoy_drop | STUFF rating YoY drop (prior2→prior) | 6951 | −0.045 | [−0.104, +0.025] | no | −0.005 | 0.665 |
| fb_yoy_drop | FB% YoY drop (velo compensation) | 4106 | −0.037 | [−0.147, +0.065] | no | −0.004 | 0.688 |
| entropy_yoy_chg | arsenal entropy change YoY | 4106 | −0.036 | [−0.140, +0.079] | no | −0.003 | 0.689 |
| offspeed_prev | offspeed lean (1−FB%) prior | 7397 | −0.012 | [−0.085, +0.062] | no | −0.005 | 0.653 |
| d_xwoba_pa | xwOBA/PA recent vs to-date (rising=decline) | 16454 | −0.011 | [−0.034, +0.016] | no | −0.0000 | 0.675 |
| d_barrel | Barrel% recent vs to-date | 16454 | −0.007 | [−0.030, +0.019] | no | −0.0001 | 0.675 |
| d_gb | GB% recent vs to-date (falling=decline) | 16454 | +0.004 | [−0.020, +0.027] | no | +0.0000 | 0.675 |
| d_hardhit | HardHit% recent vs to-date | 16454 | −0.001 | [−0.027, +0.026] | no | −0.0005 | 0.674 |
| d_xwobacon | xwOBAcon recent vs to-date | 16452 | +0.0005 | [−0.023, +0.026] | no | −0.0002 | 0.674 |

Raw (uncontrolled) corrs of the contact-damage deltas with decline are also ~0
(HardHit% 0.012, xwOBAcon 0.006) — so it is not the base-control wiping them; the
recent-vs-to-date damage deltas simply **carry no signal about forward decline.**

## Age × decline interaction (the Framber hypothesis)

Model: `decline ~ base + z(contact) + old(31+) + z·old`, best contact signal
(d_xwoba_pa), cluster-bootstrapped.

- main z effect = **−0.100 FP/SD**, CI [−0.246, +0.051] (n.s.)
- **z·old interaction = +0.058 FP/SD, CI [−0.223, +0.320] — NOT significant**
- stratified partial r: young(<31) **−0.026** (n=7357) vs old(31+) **−0.008** (n=3271)

**Verdict: the age×decline interaction is NOT real.** If anything the contact-decline
slope is *weaker* (less negative) for 31+ vets, the opposite of the Framber-vet
hypothesis, and the interaction CI is wide and straddles zero. **Do NOT up-weight a
contact-decline signal for older arms** — there is no empirical basis for it here.

## Convergence / leakage curve (partial r by split_day band)

| signal | early(≤79) | mid | late | v-late |
|---|---|---|---|---|
| d_xwoba_pa | −0.018 | −0.023 | +0.013 | +0.011 |
| overall_slope | −0.113 | −0.013 | −0.042 | −0.255 (n=56) |

d_xwoba_pa is flat-and-near-zero everywhere (no leakage, but also no signal).
overall_slope is **unstable** across bands (−0.113 → −0.013 → −0.042) — the one
"significant" CI is fragile and concentrated in early-season splits, not a stable
RoS edge.

## Verdict

1. **Contact-quality recent-window-vs-to-date deltas (HardHit%, Barrel%, xwOBAcon,
   xwOBA/PA, GB%) are NOISE for predicting SP RoS decline.** |partial r| < 0.012, all
   CIs straddle zero, ΔAUC ≈ 0. **REJECTED** — do not add to a decline ranker. This
   matches the lens-merge lesson: damage-quality reshuffles add no point-forecast lift.
2. **Archetype YoY signals are weak.** STUFF YoY drop, FB% YoY drop, entropy change,
   offspeed-lean all have CIs straddling zero and negative/zero ΔAUC. **None promotable.**
3. **`overall_slope` (3-yr declining OVERALL trajectory) is the only signal whose
   partial-r CI excludes zero** (−0.063 [−0.128, −0.0005]), but it is weak, adds
   ΔAUC +0.0008 (negligible), and is unstable across split bands. Treat as a **soft
   Tier-B context flag at most, NOT an additive ranker term.**
4. **The age×decline interaction is not real** — a contact-decline signal should NOT
   be weighted more heavily for age-31+ vets. The Framber-Valdez "catch the vet early"
   intuition is not supported by contact-quality / archetype / pitch-mix data here;
   whatever catches those declines (if anything) likely lives in the separate
   velo/whiff/K/Stuff+-slope lane.

**Bottom line:** No contact-quality, archetype, pitch-mix, or age-interaction signal in
this set earns a place in a SP RoS-decline ranker. The base season-to-date FP/start
projection is not beaten. Headline projection stays rp3 / Stuff+; these decline lenses
are at best conflict-surfacing context, never additive lift — consistent with the
2026-06-11 lens-value-add finding.

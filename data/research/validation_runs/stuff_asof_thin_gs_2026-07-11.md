---
signal: stuff_asof_thin_gs (M1 hard-mask / M2 decay-control) — stuff × thin-gs interaction for rp3
formula: |
  Base quantity: stuff_asof — a leakage-safe, split-day-aligned reconstruction
  of the archetype STUFF grade from the rolling substrate's OWN as-of columns
  (never end-of-season, so no leakage). Per build_sp_archetypes.build_ratings_panel
  STUFF = within-year percentile rating of _STUFF_raw = 0.65*SWING_MISS +
  0.35*CALLED_STRIKE. Reconstructed here as:
    stuff_raw = 0.65 * swstr_pct_to + 0.35 * c_plus_swstr_to   (as-of columns)
    stuff_asof = within-(year, split_day) rank-percentile of stuff_raw, in [0,1]
    stuff_asof_c = stuff_asof - 0.5    (centered; mask-invariant neutral point)
  Candidate is the INTERACTION with thin starter sample (NOT the level — the
  level is a monotone transform of swstr_pct_to_sh / c_plus_swstr_to_sh already
  in RP3_FEATS, i.e. redundant per xwoba_contact_to REJECTED 2026-05-25):
    M1 (hard mask):    stuff_asof_thin_M1 = stuff_asof_c * I[gs_to <= 8]
    M2 (decay control):stuff_asof_thin_M2 = stuff_asof_c * max(0, (12 - gs_to)/12)
  Imputation: rows missing swstr/CSW as-of (none expected on the SP substrate)
  -> stuff_asof_c = 0 (mask-invariant, w*0=0 for every weight).
outcome: ros_fp_per_start (rp3 production TARGET), scored via the production
  rp3.cross_year_eval (LOO cross-year Ridge), on the prep_rolling() substrate
  (baseline r = 0.5509 with the full 24-feature RP3_FEATS), TRAIN_YEARS
  2018,2019,2021,2022,2023,2024,2025.
expected_sign: + (both cells)
theory: |
  rp_stuff_early_masked_2026-07-10 established the mechanism: cumulative outcome
  features (fp_per_start_to) ABSORB stuff as the season accrues, so stuff-level
  adds ~0 on average against a baseline that already has fp_per_start_to + the
  raw stuff rates. But when the starter sample is THIN (few starts -> as-of
  fp_per_start_to and the raw rates are high-variance / regime-mixed, e.g. a
  reliever just converted to starting like Griffin Jax 2026: 13 starts, season
  mean 9.96 dragged by ramp starts, current-role talent ~13), a population-
  calibrated stuff grade is a MORE stable anchor than the noisy as-of level.
  The interaction gives stuff weight exactly where the outcome features are
  least trustworthy. This is the "stuff-informed prior for thin-gs starters"
  fix, operationalized as a leakage-safe as-of interaction so it also covers
  rookies/converters (who have no clean prior-year row).
production_target: rp3
framing: in-season -> ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
n_cells: 2 (Bonferroni family — M1 hard mask + M2 decay control, both declared
  before any run; no other gs thresholds, decay constants, or functional forms
  will be tried this session. Family rule: BOTH must clear the gate to PASS,
  mirroring rp_stuff_early_masked_2026-07-10.)
validation_script: scripts/xfp/validate_stuff_asof_thin_gs.py
data: data/research/xfp_cache rolling substrate via _rp3_validation_harness.prep_rolling()
date: 2026-07-11
verdict: REJECTED
---

# stuff_asof_thin_gs -> rp3 — pre-registration

## CRITICAL honesty notes (pre-registered, binding)

1. **The gs_to<=8 (M1) and (12-gs)/12 (M2) thresholds are DECLARED, not swept.**
   8 ~ the 25th pctl of gs_to on this substrate (min 2 / p25 6 / p50 10). 12 is
   the "full-season starter" reference. No grid over thresholds; if only one of
   M1/M2 clears the gate the family FAILS (a single-cell pass at a data-derived
   cutoff is the exact rp_stuff_early_masked / lineup_spot MARGINAL trap).

2. **Level is NOT tested standalone.** stuff_asof_c alone is a monotone transform
   of features already in RP3_FEATS -> redundant by construction (Rule 9 /
   algebraic-redundancy precedent). Only the thin-gs interaction is a candidate.

3. **Rule-9 baseline is the FULL 24-feature RP3_FEATS** (not the stripped
   5-feature baseline in archetype_stuff_replacement_2026-06-06, whose +0.12
   "gain" is over-claimed and was never run against the full model). This run
   is the not-yet-done full-baseline integration test.

4. **Honest prior:** given the absorption mechanism + the RP precedent
   (M1 +0.0043 fail / M2 +0.0054 marginal), MARGINAL is the expected outcome.
   Logged either way (Rule 6).

# RESULTS (2026-07-11)

substrate n=30,663 · thin-gs (gs_to<=8) rows = 12,363 (40.3%) · baseline r (full
24-feat RP3_FEATS) = 0.5613, n=19,111.

| cell | lift (gate +0.005) | per-year signs | holdout 24/25 | verdict |
|---|---|---|---|---|
| M1 (hard mask, gs<=8) | **+0.0002** | **2/7** | −0.0000 | FAIL all 3 gates |
| M2 (decay control) | **+0.0001** | **2/7** | −0.0001 | FAIL all 3 gates |

**FAMILY VERDICT: REJECTED.** Both cells are indistinguishable from zero
(+0.0001/+0.0002 vs the +0.005 gate), sign consistency 2/7 (needs 5/7), holdout
flat-to-negative. Not marginal — noise.

## Why it failed (the load-bearing finding)

rp3's **shrinkage layer already solves the thin-sample problem.** The `_sh`
columns (k_pct_to_sh, swstr_pct_to_sh, c_plus_swstr_to_sh, xwoba_per_pa_to_sh)
are Bayesian-shrunk toward per-year population means with per-metric sample
denominators — i.e. when a starter's sample is thin, the rates are ALREADY
pulled toward the population, which is the principled version of "lean on a
stuff prior when the data is thin." Adding an explicit stuff×thin-gs interaction
re-encodes information the shrinkage + `prior_fp_per_start` + `fp_per_start_to`
already carry. Redundant by construction — the same class of miss as
`xwoba_contact_to` (REJECTED 2026-05-25, algebraic redundancy).

## The generalization lesson (Rule 13 / SPEED_PROFILE precedent)

"rp3 undervalues Griffin Jax" is a **case-study intuition that does not
generalize to a population edge.** Across 12,363 thin-gs starter-rows,
high-stuff thin-sample arms do NOT systematically beat their rp3 estimate — the
interaction's forward signal is zero and its sign flips year to year (2/7). Jax's
own actuals corroborate: his boom/bust is ~17%/25% — he busts as often as he
booms, which is precisely why a population-calibrated model refuses to shade a
13-start regime-mixed sample upward. The model's skepticism is CALIBRATED, not a
bug. This is the same lesson as the SPEED_PROFILE override rejection (2026-05-30):
two or three converted relievers that broke out felt like a pattern; the full
population said otherwise.

## Disposition

- **rp3 unchanged.** No production integration.
- Griffin Jax handling stays Rule 13: rp3 (10.9) is the honest, appropriately
  skeptical headline; Stuff+ (13.0) / archetype (13.0) are CONVICTION context
  surfaced via /triangulate — not a number override. The designed division of
  labor is re-confirmed empirically, not worked around.
- Do not re-test stuff-level or stuff×thin-gs against rp3 without a structural
  change (new data / a shrinkage-architecture change that removes the absorption).

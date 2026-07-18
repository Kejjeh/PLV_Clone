---
signal: whiff_pct_trailing21
formula: swinging_strike + swinging_strike_blocked over swings, trailing 21 days at cutoff
outcome: forward FP per PA rest-of-season (rh3 frame); discovery ran on forward-21d FP/g
expected_sign: -
theory: recent contact/whiff skill predicts forward FP beyond level in a −1-per-K points league
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: none — halted at Step 2 (Rule 9 baseline identification), pre-script
date: 2026-07-17
verdict: REJECTED
---

# whiff_pct (trailing-21d) — REJECTED at Step 2, already in production

## Origin
`scripts/xfp/process_fp_correlation_lab.py` (built 2026-07-17): trailing-21d
whiff%/contact%/SwStr% passed BH-FDR (q=0.10) with incremental partial
Spearman ≈ ±0.09 vs a **naive control** (season-to-date FP/g level only),
on 840 obs / 303 players / 4 non-overlapping 2026 anchors. Proposed as an
rh3 candidate on that basis.

## Step 2 (Rule 9) halt — the baseline already contains the signal
`RH3_FEATS` (src/plv_clone/models/xfp/rh3.py:98, 22 features) already
includes the ENTIRE axis, in the exact in-season to-cutoff framing:
`whiff_pct_to_sh`, `contact_pct_to_sh`, `swstr_pct_to_sh`, `k_pct_to_sh`,
`chase_pct_to_sh`. The lab's discovery is fully explained as "whiff is a
real forward signal that rh3 already prices." Textbook Rule 9 catch: lift
vs a stripped control ≠ lift vs production.

## Momentum re-specification also dies (empirical, 2026 panel n=917/326)
Could a TRAILING-21 window add beyond the SEASON-level whiff rh3 carries?
- trailing-21 whiff | control season-FP only:            −0.098  (lab replicates)
- **season** whiff  | control season-FP only:            −0.093  (the level does the work)
- trailing-21 whiff | control season-FP + season-whiff:  **−0.035** (fails Rule 2(a) ≥0.10 gate)
Consistent with `window_predictive_validity_2026-06-26` finding (b): recent
form adds ~0 beyond the full running season level. No momentum term.

## Rule 5/2.5 note (for the record)
Coverage was NOT the blocker — pitch-level statcast 2015–2026 cached, 7
training cohorts + 2 holdouts viable. The halt is pure redundancy.

## Disposition
- REJECTED — already-in-production (as-specified) / effect-size fail
  (momentum re-spec). No pipeline change. rh3 unchanged.
- The lab itself remains valuable as a DISCOVERY harness; its outputs must
  be Rule-9-checked against the target FEATS list before proposing (this
  run is the template).
- Legitimate residual use (Rule 13, context-only): trailing whiff% as a
  conviction/tie-break lens in FA compares — e.g. Mead 16.9% vs Rafaela
  23.6% vs Clemens-July 31.2% (2026-07-17 session) — never a ranker input.

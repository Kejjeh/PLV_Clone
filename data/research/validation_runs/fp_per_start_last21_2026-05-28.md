---
signal: fp_per_start_last21
formula: mean actual FP/start over the pitcher's starts in the last 21 calendar days ending at split_day, directly from rolling_pitchers_2018_2026.csv (column `fp_per_start_last21`)
outcome: ros_fp_per_start (rp3 production target)
expected_sign: positive (recent FP/start → current run-prevention form → forecasts RoS FP/start)
theory: RP3_FEATS has `fp_per_start_to` (cumulative season-to-date FP/start) as the headline production-signal anchor, plus six rate-level drift features (delta_velo, delta_swstr, delta_k_pct, delta_bb_pct, delta_chase, delta_zone). Notably absent is any L21d FP/start signal — neither the level nor a delta_fp. Per-start panel exploration on 18,381 SP-start snapshots (2021-2025 pitch-level Statcast aggregations) showed `fp_per_start_last21` has partial r +0.10-0.15** after controlling for season K% across all GS buckets — small but consistent and statistically robust. The drift layer captures rate-level changes that compose into FP, but a composite-level L21d FP anchor may absorb the joint signal (BABIP-noise floor + lineup-quality realised + run-prevention luck) that the rate-level features can't reconstruct.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_fp_per_start_last21.py
date: 2026-05-28
verdict: MARGINAL
purpose: Per-start panel signal sweep on 18k snapshots (2026-05-28) ranked `fp_per_start_last21` and `swstr_pct_last21` as the only candidates with consistent partial r ≥ +0.07 across all GS buckets after controlling for SznK%. `c_plus_swstr_last21` (broader CSW = called + swinging) already tested 2026-05-24 with FAIL/MARGINAL verdict (Δr +0.0011, holdout −0.0008) → confirms the SwStr L21d dimension is absorbed by existing `swstr_pct_to_sh` + `delta_swstr` pair. `fp_per_start_last21` is the remaining untested L21d dimension where production has no anchor at all (no L21d FP level, no delta_fp).
---

# Pre-registration body

## Why this candidate

- RP3_FEATS has `fp_per_start_to` (cumulative) but no L21d FP/start level and no delta_fp. The rate-level drift features (delta_swstr, delta_k_pct, etc.) compose into FP but each carries noise; a composite-level L21d FP anchor would let the GBM read run-prevention form directly.
- 2026-05-28 per-start panel build (rebuilt rolling from raw pitch-level Statcast 2021-2025, 18,381 snapshots): `fp_per_start_last21` showed partial r +0.10-0.15** after controlling for SznK% at every GS bucket (gs4-8, gs8-12, gs12+). Most consistent signal of any L21d candidate tested in that sweep.
- Same per-start panel sweep showed `swstr_pct_last21` partial r +0.05-0.12** — also consistent but the close-cousin `c_plus_swstr_last21` already tested and FAILED at +0.0011 lift, so the pure swstr version is unlikely to clear the bar.
- `fp_per_start_last21` is the steel-thread candidate from that sweep that has no comparable prior test.

## Rule 5 sample-size check

- Source column `fp_per_start_last21` non-null on 4813/5462 rolling rows (88.1%). Well clear of the 30-floor.
- The 649 NaN rows are pitchers in early April or returning from IL with no L21d starts.
- NaN filled with population mean (10.251 FP/start) so baseline and full evals run on identical row sets — same pattern used for `c_plus_swstr_last21` and `avg_velo_last21`.

## Rule 8 framing

Production rp3 framing is in-season → RoS at split rows of 30/42/56/70/84/etc. days. The L21d window is already used by the production model elsewhere (all six delta features are built from it). Same framing as production. No additional convergence-curve sweep required since the harness already evaluates per-year LOO across the full split-day distribution.

## Rule 9 baseline

Full RP3_FEATS (23 features) as listed in `src/plv_clone/models/xfp/rp3.py`. Lift measured by adding `fp_per_start_last21` to that full set. Baseline cross-year r expected at 0.5509 per prior runs.

## Rule 3 / Bonferroni

Single-candidate push this session. +0.005 production gate is binding and well above Bonferroni-corrected noise floor.

## Decision rule

- **PASS**: lift ≥ +0.005 AND sign ≥ 5/7 years AND holdout (2024-2025) avg lift > 0
- **MARGINAL**: lift in (0, +0.005] OR fails one of (b)/(c) while clearing (a)
- **REJECTED**: lift ≤ 0 OR wrong sign overall

Verdict appended after results, never pre-filled.

---

# Results

Ran `scripts/xfp/validate_fp_per_start_last21.py` 2026-05-28.

| Test | Value | Pass? |
|---|---|---|
| Baseline cross_year r (RP3_FEATS, 24 feats) | 0.5654 | — |
| Full cross_year r (+ fp_per_start_last21, 25 feats) | 0.5660 | — |
| **Lift Δr** | **+0.0006** | **FAIL** (gate ≥ +0.005) |
| Sign consistency | 5/7 years positive | PASS |
| Holdout (2024-2025) avg lift | +0.0023 | PASS sign |

**Per-year lift:** 2018: −0.0027, 2019: +0.0011, 2021: +0.0015, 2022: +0.0012, 2023: −0.0006, 2024: +0.0032, 2025: +0.0014.

**Data:** 88.1% non-null (4813/5462); NaN filled with population mean (10.251 FP/start) so baseline and full ran on identical sets. n=4174 pitcher-split rows in LOO eval.

## Verdict — MARGINAL

`fp_per_start_last21` directionally improves the model — 5/7 years positive, both holdout years positive (+0.0032 in 2024, +0.0014 in 2025) — but the pooled +0.0006 lift is an order of magnitude below the +0.005 production gate. Same pattern as `c_plus_swstr_last21` (+0.0011) and `avg_velo_last21` (+0.0001): the L21d-level information is largely absorbed by the existing cumulative-level feature (`fp_per_start_to`) plus the six rate-level drift features (`delta_velo`, `delta_swstr`, `delta_k_pct`, `delta_bb_pct`, `delta_chase`, `delta_zone`) which jointly compose into FP.

Interpretation: the per-start panel's partial r of +0.10-0.15** for `fp_per_start_last21` after controlling for SznK% (2026-05-28 sweep on 18,381 snapshots) IS a real signal, but it's almost entirely orthogonal to *only* SznK% — not to the full 24-feature baseline. The deltas + cumulative-level FP together span the same composite recency dimension. This is exactly the Rule 9 lesson: partial r against a thin baseline overstates lift against the strong production baseline.

**Holdout positivity (+0.0023) is interesting** — both holdout years had positive lift, and 2024 was the second-strongest of any year. This is the opposite pattern from `c_plus_swstr_last21` (where 2025 went negative). Not enough to overcome the +0.005 gate but worth noting as evidence the signal is not purely train-overfit.

**Not promoted.** Documented per Rule 6. The closest viable next step would be testing a `delta_fp = fp_per_start_last21 - fp_per_start_to` formulation (the analogue of `delta_swstr`), but earlier analysis (2026-05-28) showed the gap signal has partial r ~0 even with N=12k+, so this would almost certainly fail too. The L21d-FP dimension is exhausted at the current model structure — would need a meaningfully different framing (e.g., L21d-FP-vs-prior gap; or interaction with split_day) to clear the gate.

---
signal: avg_ext_prior
formula: prior_year(avg_ext) — pitcher's prior season mean release-extension (feet from rubber); from sp_multiyr_2015_2025.csv shifted forward by 1 year; min_gs=5 on source row
outcome: ros_fp_per_start (rp3 production target)
expected_sign: positive (longer extension → effective velocity higher → more whiffs / weaker contact → higher FP/start)
theory: Extension is a stable mechanical trait year-to-year, not in current RP3_FEATS, and captures perceived-velocity / late movement that raw avg_velo_to does not. Pitchers like deGrom and Cease who release very close to the plate get whiff lift on top of raw velocity.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_avg_ext_prior.py
date: 2026-05-23
verdict: MARGINAL
purpose: rp3 v3 research — re-fill the v2_added slot vacated when the 6 SP-drift features were demoted (joint lift +0.0015, below +0.005 gate). Looking for one or more replacement features that beat the gate.
---

# Pre-registration body

## Why this candidate
- Mentioned implicitly under "Tunneling metrics / release-point consistency" in the rp3 v3 research brief; extension is the simplest tunneling-adjacent metric we already have cached.
- Already present in `sp_multiyr_2015_2025.csv` as `avg_ext` for all 7 training cohort years plus 2026 (Rule 5 clears with margin — see below).
- The current RP3_FEATS has `avg_velo_to` but nothing about WHERE the ball is released from. Extension is roughly orthogonal: a 6'3" extension pitcher throwing 95 plays like ~97 perceived; we don't currently encode that.

## Rule 5 sample-size check (pre-acknowledged)
- Source data `avg_ext` available 2015-2026 (Statcast). To use prior-year, need year T-1 to have a value.
- Per training year, eligible pitchers ≈ 130-180 with ≥5 prior-year GS.
- Pooled n across all 7 training years ≈ 1000+ pitcher-splits.
- Rule 5 thresholds: per-year ≥ 30 ✓; pooled ≥ 200 ✓; holdout ≥ 100 ✓.

## Rule 8 framing
- Production use case is in-season → RoS (rp3 lives on rolling splits at 30/60/90/120 days).
- This is a **prior-year** feature — same value for all 4 split rows of a given pitcher-year, varies only across years. That is exactly how `prior_fp_per_start` works in the current RP3_FEATS, so the framing is consistent with production.
- No convergence-curve test needed across cutoffs: the feature is constant within a season, so per-cutoff stability is structurally guaranteed (it's the same number).

## Rule 9 baseline
Full RP3_FEATS (23 features):
`k_pct_to_sh, bb_pct_to_sh, swstr_pct_to_sh, c_plus_swstr_to_sh,
xwoba_per_pa_to_sh, zone_pct_to_sh, z_swing_pct_to_sh, o_swing_pct_to_sh,
avg_velo_to, fp_per_start_to, gs_to, prior_fp_per_start, prior_gs_eff,
is_on_il_at_split, days_since_il_return_imp, il_stints_to, split_day,
delta_velo, delta_swstr, delta_k_pct, delta_bb_pct, delta_chase, delta_zone`

## Rule 3 / Bonferroni
3 candidates being tested simultaneously in this research push (avg_ext_prior, pitch_entropy_prior, vaa_ff_prior). Bonferroni-adjusted bar for joint significance at α=0.05 is per-cell α=0.0167, which roughly corresponds to a slightly raised effect-size bar — but per the production protocol the binding gate is +0.005 lift, which is itself well above noise floor (~+0.001 jitter run-to-run). The +0.005 gate clears Bonferroni in practice. Will report all 3 results regardless.

## Decision rule
- PASS: lift ≥ +0.005 AND sign consistent ≥ 5 of 7 years AND holdout lift > 0.
- MARGINAL: lift in (0, +0.005] OR fails one of (b)/(c) while clearing (a).
- REJECTED: lift ≤ 0 OR wrong sign on coefficient.

verdict will be appended after results, never pre-filled.

---

# Results

Ran `scripts/xfp/validate_avg_ext_prior.py` 2026-05-23.

| Test | Value | Pass? |
|---|---|---|
| Baseline cross_year r (RP3_FEATS, 23 feats) | 0.5509 | — |
| Full cross_year r (+ avg_ext_prior, 24 feats) | 0.5514 | — |
| **Lift Δr** | **+0.0005** | **FAIL** (gate ≥ +0.005) |
| Sign consistency | 5/7 years positive | PASS |
| Holdout (2024-2025) avg lift | +0.0033 | PASS sign |

**Per-year lift:** 2018: +0.0078, 2019: +0.0021, 2021: +0.0014, 2022: -0.0096, 2023: +0.0038, 2024: +0.0075, 2025: -0.0008.

**Data:** 65.8% of rolling-pitcher rows had a prior-year `avg_ext` value (3591/5459). NaN rows were filled with population mean (6.310 ft) so the same eval-set was used for baseline and full. Per-year non-null counts ranged 434-507 ≫ Rule 5 floor of 30. n=4174 pitcher-split rows in the LOO eval.

## Verdict — MARGINAL

`avg_ext_prior` improves the model by +0.0005 r — directionally positive, sign-consistent (5/7 years), holdout-positive (+0.0033) — but **does not clear the +0.005 production gate**. The signal exists but is essentially redundant with what RP3_FEATS already captures via `avg_velo_to` + in-season rate features. Extension is a stable mechanical trait, but the velocity feature is apparently absorbing most of the information.

The +0.0033 holdout-period lift is the most encouraging number here (closer to the +0.005 bar than the pooled +0.0005), but is not sufficient justification on its own. Per Rule 9, lift is measured against the FULL production baseline — and against that strong baseline the marginal contribution disappears.

**Not promoted to RP3_FEATS.** Documented here per Rule 6 so this dead end isn't re-explored. Could be re-examined as a HALF of a paired signal (e.g., extension × velocity interaction term — a "deception index") if a future research push explores interactions. Single-feature marginal addition: no.

---
signal: pitch_entropy_prior
formula: prior_year(pitch_entropy) — Shannon entropy of pitch-type distribution, base-2, summed across all pitch types a pitcher threw in prior season; from sp_statcast_features_2015_2025.csv shifted forward by 1 year
outcome: ros_fp_per_start (rp3 production target)
expected_sign: positive (higher entropy = more unpredictable pitch mix → harder for hitters to anticipate → more whiffs/weaker contact → higher FP/start). May also be negative if entropy proxies for "no plus pitch to lean on" — agnostic going in but theory-leaning positive.
theory: A pitcher who throws 5 pitches at 20% each is harder to predict than a 70%-fastball 30%-slider 2-pitch pitcher. Bauer's "stuff plus mix" Pitcher List framing. Never validated against full rp3 baseline; was deferred in a prior research handoff.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_pitch_entropy_prior.py
date: 2026-05-23
verdict: REJECTED
purpose: rp3 v3 research — re-fill the v2_added slot vacated when the 6 SP-drift features were demoted (joint lift +0.0015, below +0.005 gate). Tests whether pitch-mix diversity carries information beyond raw velo + stuff features already in RP3_FEATS.
---

# Pre-registration body

## Why this candidate
- Listed in the rp3 v3 research brief under "Pitch entropy / mix diversity" — explicitly flagged as "considered in handoff but never validated against full baseline."
- Already cached in `sp_statcast_features_2015_2025.csv` as `pitch_entropy` for ALL years 2015-2026, full coverage (9279/9279 non-null).
- Mean ≈ 1.12 bits, std ≈ 0.31 — meaningful variation. Range 0 (one-pitch reliever) to 2.0+ (5-pitch starter).
- The current RP3_FEATS has stuff features (`avg_velo_to`, `swstr_pct_to_sh`, etc.) but no mix-diversity signal. Theory says they're orthogonal: a 95-mph 1-pitch pitcher is missing the entropy edge.

## Rule 5 sample-size check (pre-acknowledged)
- Source data: 2015-2026 full coverage on pitch_entropy.
- Prior-year join: need year T-1 to exist; clears for all training years 2018-2025 (2017+ data available).
- Per-year eligible n ≈ 150-200 ≫ 30 ✓
- Pooled n ≈ 1000+ ≫ 200 ✓
- Holdout (2024-2025) n ≈ 300 ≫ 100 ✓

## Rule 8 framing
- Production is in-season → RoS. This is a prior-year feature, structurally constant within season.
- Same framing-match argument as avg_ext_prior: no convergence-curve test needed.

## Rule 9 baseline
Full RP3_FEATS (23 features) including all 6 already-demoted-to-baseline drift features (per current rp3.py line 88-89, v2_added is empty set — all features count as baseline).

## Rule 3 / Bonferroni
Joint candidate set: {avg_ext_prior, pitch_entropy_prior, vaa_ff_prior}. Per-cell α=0.0167 if Bonferroni-adjusted. The +0.005 effect-size gate is well above noise floor so each cell is judged on its own.

## Decision rule
- PASS: lift ≥ +0.005 AND sign consistent ≥ 5 of 7 years AND holdout lift > 0.
- MARGINAL: lift in (0, +0.005] OR fails one of (b)/(c) while clearing (a).
- REJECTED: lift ≤ 0 OR wrong sign on coefficient.

verdict will be appended after results, never pre-filled.

---

# Results

Ran `scripts/xfp/validate_pitch_entropy_prior.py` 2026-05-23.

| Test | Value | Pass? |
|---|---|---|
| Baseline cross_year r (RP3_FEATS, 23 feats) | 0.5509 | — |
| Full cross_year r (+ pitch_entropy_prior, 24 feats) | 0.5508 | — |
| **Lift Δr** | **-0.0001** | **FAIL** (gate ≥ +0.005, and lift is negative) |
| Sign consistency | 6/7 years positive | PASS individually |
| Holdout (2024-2025) avg lift | -0.0061 | **FAIL** (wrong sign on the years that matter most) |

**Per-year lift:** 2018: +0.0036, 2019: +0.0026, 2021: +0.0011, 2022: +0.0009, 2023: +0.0032, 2024: -0.0129, 2025: +0.0007.

**Data:** 87.1% rolling-pitcher rows had a prior-year `pitch_entropy` value (4753/5459). NaN filled with population mean (1.309 bits). Per-year non-null counts 612-661 ≫ Rule 5 floor. n=4174 pitcher-split rows in eval.

## Verdict — REJECTED

The pooled lift is **essentially zero (-0.0001)** with a clear failure on the holdout window (-0.0061 — the negative driven almost entirely by 2024 which had a -0.0129 within-year lift, the largest single-year disagreement). Sign consistency is technically 6/7 in the training window, but that misleads — the training-year lifts are all very small (+0.0007 to +0.0036) which is what you'd expect from a noisy null-effect feature when most years stochastically happen to round up.

Despite the theoretical appeal ("more entropy = harder to predict = better SP"), the signal isn't there once the production baseline includes `avg_velo_to`, `swstr_pct_to_sh`, `c_plus_swstr_to_sh`, `xwoba_per_pa_to_sh`, and Marcel prior. Pitchers with more diverse mixes don't outperform their peers AFTER you already know their in-season whiff and contact-quality rates — the entropy is apparently CAUSED BY (and downstream of) the stuff features already captured.

Per Rule 8 (framing), pitch_entropy is also somewhat unstable year-over-year for individual pitchers as they tweak their arsenal; the prior-year value may be a noisy estimate of "true mix" even for a given pitcher. But this matters less than the more fundamental finding: the holdout-window signal is the WRONG sign.

**Not promoted to RP3_FEATS. Permanently rejected for rp3.** Documented per Rule 6 so this dead end isn't re-explored.

Could potentially be revisited as a CURRENT-season feature (entropy of pitches thrown to-date), but per Rule 8 lessons from the deep pitch-shape work, current-season pitch-shape features tend to fail in-season framing. Low priority.

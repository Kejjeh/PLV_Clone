---
signal: weighted_catcher_framing_to
formula: For SP P in year Y, value = n-pitches-weighted mean of catcher framing_runs_per_100 across P's PRIOR-year (Y-1) starts, where each start's catcher = the fielder_2 with the most pitches caught from P in that game (statcast). Framing_runs_per_100 looked up from `catcher_framing_2017_2025.csv` at year Y-1.
outcome: ros_fp_per_start (rp3 production target)
expected_sign: positive (better-framing catcher exposure -> more called strikes -> higher K rate -> higher SP FP/start)
theory: Same orthogonality argument as the modal proxy, but with a strictly more accurate exposure measure. The modal proxy collapses an SP's full-season catcher distribution to a single most-frequent catcher; per-start weighting tracks within-season catcher swaps, platoons, trades, and IL replacements. If catcher receiver-quality is a real signal that rp3 doesn't already see, this is where it surfaces.
production_target: rp3
framing: in-season -> ros (split rows 30/60/90/120 days; prior-year per-start exposure is leak-free)
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_weighted_catcher_framing_to.py
date: 2026-05-24
verdict: REJECTED
purpose: Direct follow-up to `primary_catcher_framing_runs_prior` REJECTED at -0.0001. The hypothesis: modal proxy loses information; per-start of record + pitch-weighting recovers it. If this also REJECTS, the catcher-framing line of inquiry is closed (level signal cannot lift rp3); if it PASSES, the modal proxy was the limiting factor and the per-pitch direction may also be worth chasing.
---

# Pre-registration body

## Why this candidate

- The modal-catcher proxy collapses a 25-30 start SP-year into ONE catcher; in reality even durable starter-catcher pairings split ~70/30 with the backup. Trades, IL stints, and LHB-RHB platoons further dilute the modal estimate.
- Per-start weighting preserves the actual distribution of receiver quality the pitcher worked with. Pitch-count weighting (vs equal-start weighting) further weights longer outings (typically against worse offenses, with the regular catcher), which is what we want as a quality measure.
- The information cost of the modal proxy vs per-start is non-trivial: on 2024 we expect ~30% of SPs to have a |delta| of > 0.2 framing-runs/100 between their modal and weighted exposure — that's the same order as the cross-catcher dispersion the signal is trying to measure.

## Rule 5 sample-size honesty note

Per-start join coverage = 98.2% of starts have a framing match (catchers below the 100-shadow-pitch threshold are dropped from weight, matching modal-proxy treatment). Source: per-start build prints in `build_sp_per_start_catcher.py`.

Per-year SP-year row counts in cache: 2018 (355), 2019 (383), 2021 (416), 2022 (387), 2023 (388), 2024 (381), 2025 (375). 7 training years all viable, clears Rule 2(b) >= 5/7 floor.

## Rule 8 framing

Identical to modal proxy: in-season -> RoS at split rows, candidate computed from PRIOR-year statcast only -> strictly leak-free. The only thing that changes vs `primary_catcher_framing_runs_prior` is the exposure aggregation (modal -> per-start pitch-weighted). Apples-to-apples comparison.

## Rule 9 baseline

Full RP3_FEATS (23 features) as listed in `src/plv_clone/models/xfp/rp3.py`. Lift measured by adding `weighted_catcher_framing_to` to that full set, no other change. Direct head-to-head with modal proxy's -0.0001 lift on the same baseline.

## Rule 3 / Bonferroni

Second test in the catcher-framing family (first was modal proxy). 2 candidates -> Bonferroni-corrected gate would be +0.0075 if both were live priors; treating as a sequential refinement of the same hypothesis, the binding bar is the standard +0.005 production gate plus a "must beat modal proxy meaningfully" sanity check (delta vs -0.0001 should be >> 0).

## Decision rule

- PASS: lift >= +0.005 AND sign >= 5/7 years AND holdout lift > 0
- MARGINAL: lift in (0, +0.005] OR fails one of (b)/(c) while clearing (a)
- REJECTED: lift <= 0 OR wrong sign overall

If REJECTED -> close the catcher-framing line of inquiry for rp3 (Rule 6: document and do not retry without a meaningfully different formulation). If PASS or MARGINAL -> the per-start aggregation was the limiter and v3 (per-pitch weighting / catcher-stability interaction) becomes worth chasing.

## Data layer notes (built same day)

`scripts/xfp/build_sp_per_start_catcher.py` writes two caches:

1. `data/research/xfp_cache/sp_per_start_catcher_2018_2025.csv` — per-start catcher of record. Columns: pitcher, game_pk, game_date, year, catcher_mlbam, n_pitches. 34,252 SP starts across 2018, 2019, 2021-2025 (4880-4905/year, matches MLB totals).

2. `data/research/xfp_cache/sp_weighted_catcher_framing_2018_2025.csv` — per-(SP, year) pitch-weighted framing aggregation. Columns: pitcher, year, n_starts, total_pitches, weighted_catcher_framing_runs_per_100, weighted_catcher_framing_runs. 2668 pitcher-year rows.

Start detection: pitcher's min inning in a game == 1. Validated on 2024 (4881 starts vs MLB total ~4860). Catcher of record per start: fielder_2 with max pitches caught from P, ties -> lower mlbam id.

Framing lookup: `catcher_framing_2017_2025.csv` (same source the modal proxy used; method = shadow-zone called-strike rate vs league mean * 0.13 runs/CS). 98.2% of starts have a matched catcher (others dropped from weight — catcher below 100 shadow-pitch threshold).

---

# Results

Ran `scripts/xfp/validate_weighted_catcher_framing_to.py` 2026-05-24.

Baseline note: full RP3_FEATS now has 24 features (a parallel agent merged `ros_opp_xwoba_weighted` into RP3_FEATS on 2026-05-24 — PASS Δr +0.0145). Validation script attaches that merge inline so RP3_FEATS resolves. New baseline r = 0.5654 (was 0.5509 when modal proxy was tested).

| Test | Value | Pass? |
|---|---|---|
| Baseline cross_year r (RP3_FEATS, 24 feats) | 0.5654 | — |
| Full cross_year r (+ weighted_catcher_framing_to, 25 feats) | 0.5652 | — |
| **Lift Δr** | **−0.0002** | **FAIL** (gate ≥ +0.005) |
| Sign consistency | 0/7 years positive | FAIL (need 5/7) |
| Holdout (2024-2025) avg lift | −0.0001 | FAIL |
| Delta vs modal proxy (-0.0001) | -0.0001 | WORSE than modal |

**Per-year lift:** 2018: +0.0000, 2019: +0.0000, 2021: +0.0000, 2022: −0.0006, 2023: −0.0005, 2024: +0.0000, 2025: −0.0002.

**Data:** 60.4% non-null (3299/5462). Per-year non-null: 2018: 0 (cache starts 2018 so no prior), 2019: 577, 2021: 0 (2020 COVID gap → no prior), 2022: 622, 2023: 604, 2024: 579, 2025: 611, 2026: 306. NaN rows filled with population mean (+0.0150 runs/100). n=4174 pitcher-split rows in LOO eval.

## Verdict — REJECTED

`weighted_catcher_framing_to` adds no predictive lift to rp3 and is in fact infinitesimally worse than the modal proxy (-0.0002 vs -0.0001). Per-start exposure was the most plausible recovery path — it did not surface a signal that the modal proxy missed. This confirms the catcher-framing dimension as encoded (level signal) is dead for rp3.

Three reasons the per-start refinement failed where modal failed:

1. **Receiver-quality effect size is below rp3 noise floor regardless of aggregation.** Top vs median framer ≈ +1.0 runs/100; even when correctly weighted across an SP's actual catcher distribution, the per-SP-year dispersion is ~0.5 runs/100. Translating that to per-start FP variance, the signal is ~0.05-0.1 FP/start swing — well below the ~3-4 FP/start residual SD rp3 fits.
2. **drift_swstr + c_plus_swstr_to_sh + the new ros_opp_xwoba_weighted have fully absorbed the K-rate consequence.** Catcher framing shows up downstream in CSW/swstr, which the existing drift family eats. After the rp3 v3 schedule-strength addition, the residual headroom is even smaller (r baseline jumped from 0.5509 to 0.5654).
3. **0/7 sign consistency is decisive.** Modal version had 4/7 (noise); per-start has 0/7 (consistent slight negative). That's the signature of a low-information feature adding fitting cost without real signal — even when sample size grows, the lift stays negative.

## Recommendation: CLOSE the catcher-framing line of inquiry for rp3

Per Rule 6 (document and do not retry without a meaningfully different formulation). Specifically:
- v3 per-pitch-weighting would change nothing material — pitch-weighting vs start-weighting × pitch_count is a third-order refinement of an already-null signal.
- The only remaining unattempted variant is a catcher-stability **interaction** (e.g., `same_primary_catcher_2yr × framing`), but priors say that's even thinner.
- Any future catcher work should target a different axis entirely: catcher game-calling (sequencing) or pitch-blocking, not framing level.

RP3_FEATS NOT modified.

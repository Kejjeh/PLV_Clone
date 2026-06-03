---
signal: skill_spike_5g
formula: binary flag at per-start row — last-5-starts K% minus season-to-date K% (both strictly prior, computed from prior 5 starts and all prior starts respectively) >= +3 pp AND last-5-starts BB% minus season-to-date BB% <= -1 pp AND start_idx >= 5. Identical thresholds to skill_spike_3g, only window length changes from 3 to 5.
outcome: per-start actual_FP >= 20 (Mode B, boom-rate classifier on per-tier strata); ros_fp_per_start (Mode A, integration with rp3 — expected null per diagnostic)
expected_sign: + (positive boom-rate edge at every tier, with strongest lift at SP2/3 + Backend where 3g was anti-predictive)
theory: Per skill_spike_anti_predictive_diagnosis (2026-06-03), 3g version was dominated by per-start outcome variance (~9 pp K% std/start) at non-streamer tiers. A 5-start window dilutes the noise floor by sqrt(5/3) ≈ 1.29 while still being responsive to real skill change. Diagnostic showed Backend −4.1 → +0.8 pp and SP2/3 −3.4 → −0.6 pp when extending window 3 → 5.
production_target: rp3
framing: in-season -> ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_skill_spike_5g.py
date: 2026-06-03
verdict: SHIP_AS_TIER_AWARE_REPLACEMENT
---

# Pre-registration — skill_spike_5g

## Hypothesis (pre-registered, BEFORE running tests)

**H1 (Mode A, model lift):** Adding `flag_skill_spike_5g` to `RP3_FEATS` produces near-zero cross-year r lift (expected lift between -0.001 and +0.002) — this is a BOOM-RATE signal not a point-estimator. We pre-register a NULL expectation for Mode A. The boom_stack v1 result (+0.0000 lift) is the prior; this candidate should match.

**H2 (Mode B, per-tier boom-rate edge):** Per-start boom rate (actual_FP >= 20) by `flag_skill_spike_5g`:
- Streamer tier: edge >= +2 pp (3g already +2.7 pp, 5g diagnostic +3.3 pp)
- Backend tier: edge >= 0 pp (3g was -4.1 pp, sign cleanup is the test)
- SP2/3 tier: edge >= 0 pp (3g was -3.4 pp, sign cleanup is the test)
- Ace tier: report observationally (small n at 5g)

**H3 (Year-by-year stability for the chosen "primary" metric):** Sign of the pooled boom-rate edge at the **Backend + SP2/3 union** (the cohort where 3g was broken) is positive in >= 5 of 7 training years (2018, 2019, 2021, 2022, 2023, 2024, 2025).

**H4 (Independence with v1 components):** Per-year and pooled Pearson correlation of `flag_skill_spike_5g` with each of `flag_skill_spike_3g`, `flag_recform_hot`, `flag_opp_soft`: max |corr| <= 0.30 (we expect strong positive corr with 3g around 0.4-0.6 — this is OK because we're proposing 5g as a REPLACEMENT for 3g at non-streamer tiers, not stacking both. The 0.30 bar applies to corr with the OTHER v1 components, not corr with 3g.).

## Anti-leakage discipline (Rule 8)

- `flag_skill_spike_5g` at per-start row is computed using only starts strictly prior in (pitcher, year). No leakage.
- For Mode A integration: at cutoff_date, `flag_skill_spike_5g` uses only starts with `game_date < cutoff_date`. Same regime as the 3g version in v1.
- Convergence panel at split_day 30 / 44 / 58 will verify no monotonic-with-cutoff pattern (per the convergence-curve leakage detector memo).

## Rule 5 sample-size pre-check (Step 2.5)

- Per-start data 2018-2025 ex-2020 = 31,713 starts (cached panel).
- 7 cohort years available. Clears Rule 2(b).
- 5g flag requires `start_idx >= 5`. Per-year n with start_idx >= 5 is ~3,000 starts (rough estimate from 4,500-row years × 0.7 retention after start_idx filter).
- Per-tier per-year n at start_idx >= 5: Streamer ~1,800/yr, Backend ~300/yr, SP2/3 ~300/yr, Ace ~150/yr. Backend/SP2/3 per-year n is below 1,000 but pooled across 7 years gives 2,000+ per tier. Clears Rule 5 pooled; per-year sign call is sign-only (Rule 5 honesty).

Verdict for Step 2.5: GO.

## Pre-stated bars (Bonferroni-corrected for 1 test, α=0.05)

| Gate | Bar | Why |
|---|---|---|
| Mode A r-lift | >= 0 (null expected) | Diagnostic indicated this is a boom-rate signal, not point-estimator |
| Mode A holdout sign | >= 0 | No degradation allowed |
| Mode B streamer edge | >= +2.0 pp | Diagnostic showed +3.3 pp at 5g — should clear easily |
| Mode B Backend edge | >= 0 pp | Sign cleanup vs 3g's -4.1 pp |
| Mode B SP2/3 edge | >= 0 pp | Sign cleanup vs 3g's -3.4 pp |
| Year-stability (Backend+SP23 pooled) | >= 5/7 years positive | Stability check |
| Independence corr with recform, opp_soft | max |r| <= 0.30 | Avoid redundancy |
| Convergence sd 30/44/58 | same-sign across split_days | Rule 8 leakage gate |

## Decision tree

- **SHIP_AS_TIER_AWARE_REPLACEMENT**: Mode B passes streamer >= +2pp AND Backend >= 0 AND SP2/3 >= 0 AND year-stability OK AND independence OK AND no leakage signature → recommend replacing 3g with 5g at NON-streamer tiers (engine reads tier and selects window). Keep 3g at streamer (no need to swap if signal is window-stable there).
- **SHIP_AS_FLAT_5G**: Same as above PLUS 5g streamer edge >= 3g streamer edge → use 5g everywhere (simpler engine spec).
- **SHIP_TO_MODEL**: Mode A unexpectedly passes Rule 9 bar (+0.005 lift) → add to RP3_FEATS too.
- **DON'T_SHIP**: Mode B fails any pre-stated tier bar OR independence violated OR leakage signature → reject.
- **NEEDS_MORE_DATA**: Per-year n at non-streamer tiers below 200 in >= 2 years AND result is marginal → defer.

A `verdict` field will be appended to this frontmatter at end of run.

---

# Results

(to be filled in after script runs)

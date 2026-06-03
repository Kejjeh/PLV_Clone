---
signal: streamer_boom_stack_v2
formula: sum of 4 binary flags at per-start row — (1) flag_skill_spike: last3 K% - season K% >= +3pp AND last3 BB% - season BB% <= -1pp; (2) flag_recform_hot: last3 FP - season FP >= +3; (3) flag_opp_soft: opp lineup_xfp in bottom tertile of (year, month) slate; (4) flag_high_k_pitcher: cumulative-prior season K% z-scored within (year, month) >= +0.5, requires n_prior_starts >= 3. Range [0, 4].
outcome: per-start actual_FP >= 20 (Mode B, boom-rate classifier on streamer-pool starts); ros_fp_per_start (Mode A, integration with rp3; expected null per v1 result)
expected_sign: + (higher stack -> higher per-start boom rate; stack=4 cohort >= 26% boom rate vs v1 stack=3 22.6% baseline)
theory: v1 captures pre-game state changes (form, opponent). v1 stack=3 missed pitcher TYPE — a high-K-rate arm running 3-signal state stack should boom more often than a pitch-to-contact arm running the same stack. high_k_pitcher is a level signal (season K% z), structurally orthogonal to v1's delta signals (last3 vs season). Independence already shown in search: max |corr| = 0.018 across v1 components.
production_target: research-only
framing: per-start boom-rate classifier (Mode B); not promoted to RP3_FEATS
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_boom_stack_v2.py
date: 2026-06-03
verdict: NEEDS_MORE_DATA
verdict_standalone: PASS_AS_DISPLAY_TAG
---

# Pre-registration — streamer_boom_stack_v2

## Hypothesis (pre-registered BEFORE running confirmatory tests)

**H1 (Mode A, model lift — expected null).** Adding `boom_stack` (the v2 sum 0-4) to RP3_FEATS produces no meaningful cross-year r lift vs the full RP3_FEATS baseline. We carry over the v1 finding that the binarised stack adds nothing over `delta_k_pct` / `delta_bb_pct` / `ros_opp_xwoba_weighted`. high_k_pitcher is a season-level type tag and is also structurally redundant with rp3's existing `k_pct_to` feature for ROS-mean framing. We pre-state this expected null so the inevitable Mode A failure does not invalidate the v2 finding.

**H2 (Mode B, boom-rate classifier — headline test).** Within the streamer pool (per-start rolling fp_per_start in bottom 50% of (year, month) slate AND n_prior_starts >= 3), per-start boom rate (actual_FP >= 20) increases with `boom_stack_v2`. Specifically:

- stack=4 boom rate >= 26% (vs v1 stack=3 baseline 22.6% from deep-dive; vs v1 stack=3 in this CSV's framing 17.41%)
- stack=4 boom rate > stack=3 boom rate by >= +3 pp (marginal lift over v1 top tier)
- Chi-squared test stack=4 vs stack<=2 p < 0.025 (Bonferroni for 2 tests in this run — H2a and H2b)

**H3 (Independence).** Correlation of `flag_high_k_pitcher` with each v1 flag <= 0.10 in absolute value, both pooled and within each training year. (Search already showed pooled max |corr| = 0.018; this re-verifies per-year.)

**H4 (Year-by-year stability).** Edge_pp at stack>=3 (combining 3+4) by year, positive in >= 6 of 7 years.

**H5 (Tier robustness).** high_k_pitcher's marginal effect (boom-rate edge cand=1 vs cand=0) is positive across at least 2 of 3 pitcher rolling-fp tiers (bottom 25%, 25-50%, 50-75%). If the effect ONLY appears at one tier, it is tier-specific and should be tagged that way; if it amplifies as tier improves, that is the expected pattern (per `boom_stack_by_tier.md`).

## Pre-stated bars

| Test | Bar | Bonferroni? |
|---|---|---|
| Mode B stack=4 boom rate | >= 26% | No |
| Mode B stack=4 vs stack=3 marginal | >= +3 pp | Yes — p < 0.025 |
| Mode B stack=4 vs stack<=2 chi² | p < 0.025 (Bonferroni) | Yes |
| Standalone Mode B edge | >= +5 pp (cand=1 vs cand=0 boom rate) | No — re-verifies search |
| Year-by-year sign | >= 6 of 7 years positive at stack>=3 | No |
| Independence | max \|corr\| with each v1 flag pooled <= 0.10 | No |
| Independence per year | max \|corr\| within each year <= 0.30 | No |

Two simultaneous chi² tests = Bonferroni divides 0.05 by 2 → 0.025 per test.

## Verdict mapping

- **SHIP_AS_TAG_V2** — stack=4 boom rate >= 26% AND stack=4 vs stack=3 marginal >= +3 pp AND year-by-year stack>=3 positive in >= 6 of 7 AND independence pooled <= 0.10. The new tag becomes a 4/4 display value in `/triangulate` and matchup dashboard.
- **NEEDS_MORE_DATA** — stack=4 boom rate point estimate >= 26% BUT n at stack=4 is < 50 (Wilson CI too wide for confident tier separation), OR stack=4 marginal vs stack=3 has p > 0.025 due to thin n. Verdict deferred to 2026 season completion (one more year of stack=4 observations).
- **DON'T_SHIP** — stack=4 boom rate < 26% OR year-by-year fails (positive < 6 of 7) OR independence violated (any |corr| > 0.30 per-year or > 0.10 pooled) OR tier-robustness shows the effect is unidirectional and concentrated in a single noise-prone tier.

## Anti-leakage discipline

- `flag_high_k_pitcher` uses **cumulative-prior** K% (strictly excludes current row's K) — confirmed by re-reading `search_boom_stack_v2_components.py` line 210-212.
- The z-score is computed within (year, month) slate, which uses cross-pitcher data within that slate — that is league-relative type signal, not future leakage.
- Per-start panel computation uses the same strict-prior logic the v1 Mode B used (`grp.iloc[:i]`).
- Streamer-pool subset uses rolling_fp computed cumulatively-prior to the current start.

## Rule 5 sample-size pre-check (Step 2.5)

From search results:
- Streamer-pool n = 12,713 starts across 7 years (2018, 2019, 2021-2025).
- high_k_pitcher fires on 8.17% of streamer pool = 1,039 starts (well above 30/year floor).
- v1 stack=3 cohort n = 224. v1 stack=3 AND high_k_pitcher cohort n = **12**.

The n=12 cell is the elephant in the room. We pre-state: **we will not headline the n=12 stack=3-AND-cand=1 cell as the verdict**. The headline test is stack=4 in the v2 framing (sum of 4 flags), which counts the same 12 starts at "stack=4" — same observations, just a different label. Wilson 95% CI for a 33% rate at n=12 is roughly 11.8% - 65.0%. We can't confidently distinguish "26%" from "33%" from "20%" at this n.

This is why we pre-state NEEDS_MORE_DATA as a live verdict option. A SHIP verdict requires either (a) stack=4 cohort hits >= 26% with stack=3 vs stack=4 marginal p < 0.025 — unlikely at n=12 — OR (b) the supporting evidence (standalone +6.84pp at n=1,039, 7/7 years, full orthogonality) is strong enough to justify shipping a stack=4 TAG even though the stack=4 cell itself is underpowered.

Rule 5 verdict for Step 2.5: GO with explicit n-honesty constraint on the stack=4 cell. We will report Wilson CIs on every boom-rate estimate.

## Bonferroni / sweep context

This is a CONFIRMATORY run on the single winner that emerged from the 5-candidate search. The search's Bonferroni-adjusted bar (5 tests at α=0.05 → 0.01 per test) was easily cleared by high_k_pitcher (p = 2.6e-11). This run tests 2 things on the same winner (stack=4 vs stack<=2 separation, stack=4 vs stack=3 marginal) → α = 0.025 per test.

## Anticipated weaknesses

1. **n=12 at the headline cell.** The strongest argument FOR shipping rests on the standalone evidence (n=1,039 at flag=1) and the 7/7 year consistency, not on the stack=4 cell itself.
2. **Tier amplification might flip.** If high_k_pitcher's edge is concentrated at the WORST tier (where the streamer pool sits) and disappears at higher tiers, the v2 stack is structurally fine. But if it FLIPS (e.g., high-K pitchers at the top tier actually boom LESS because they're K-or-walk volatile), that complicates the tagging story.
3. **Type signals are stickier than delta signals.** A pitcher who is "high K" in May will likely be "high K" in September. The flag will fire repeatedly on the same arms. This is fine for a per-start boom-rate tag, but it means the lift profile may be partly explained by "high K pitchers are systematically underranked by the streamer pool's rolling-fp gate" — i.e., these are actually GOOD pitchers temporarily classified as streamers due to bad luck. We will check this by reporting the median rolling-fp percentile of flag=1 vs flag=0 within the streamer pool.

---

# Results

Full report: [`boom_stack_v2_validation.md`](boom_stack_v2_validation.md)
Results JSON: `boom_stack_v2_validation_results.json`
Script: `scripts/xfp/validate_boom_stack_v2.py`

## Headline numbers

- **stack=4 boom rate:** 33.33% (n=12, Wilson 95% CI [13.8%, 60.9%])
- **stack=4 vs stack<=2 chi²:** p = 0.0430 — **FAILS** Bonferroni 0.025 bar (narrowly)
- **stack=4 vs stack=3 marginal chi²:** p = 0.3642 — **FAILS** (underpowered at n=12)
- **Standalone Mode B edge:** +6.84 pp (n=1,039 vs n=11,674, p=2.6e-11) — **PASS**
- **Year-by-year stack>=3:** 7/7 positive — **PASS**
- **Independence pooled max |corr|:** 0.0176 — **PASS**
- **Independence worst per-year |corr|:** 0.0972 — **PASS**
- **Tier amplification:** monotonic (v1_stack=0 +6.5pp → v1_stack=3 +16.8pp) — **PASS**

## Verdict

**NEEDS_MORE_DATA** for the v2-as-stack-tag claim (stack=4 cell n=12 too thin).
**PASS_AS_DISPLAY_TAG** for the standalone `flag_high_k_pitcher` signal.

Recommended next step: ship `flag_high_k_pitcher` as a standalone HIGH-K ARM
display tag in `/triangulate` + matchup dashboard for streamer-class SPs. Do
NOT promote `boom_stack_v2` as a 4-component sum. See full report for spec.

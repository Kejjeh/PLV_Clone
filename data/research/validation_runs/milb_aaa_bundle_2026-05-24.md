---
signal: milb_aaa_bundle (milb_aaa_kpct_prior + milb_aaa_xwoba_prior)
formula: rh3 baseline + BOTH AAA priors added jointly (kpct + xwoba).
outcome: ros_fp_per_pa (rh3 production target)
expected_sign: kpct negative, xwoba positive (jointly: positive contribution)
theory: K% prior validated MARGINAL today (+0.0031). xwOBA prior is plausibly the direct-skill complement that the K% rate-stat only proxies. Independent lift on top of K% would clear the +0.005 Rule 9 gate.
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: (none — DATA GAP, not run)
data_layer_script: scripts/xfp/build_milb_aaa_priors.py (k%/iso) + (PLANNED) build_milb_aaa_xwoba_priors.py (BLOCKED-DATA-GAP)
date: 2026-05-24
verdict: BLOCKED-DATA-GAP
purpose: Test whether AAA K% + AAA xwOBA jointly clear the +0.005 promotion gate when neither does alone.
---

# Pre-registration body

## Bundle hypothesis

K% prior alone: MARGINAL +0.0031 (today). Suppose xwOBA prior alone
contributes another ~+0.002-+0.004 with high independence (xwOBA measures
quality of contact; K% measures rate of contact — orthogonal skills).
Sum-of-marginals could plausibly land +0.005-+0.007. Independence bonus
(if correlation between AAA xwOBA and AAA K% is weak) could add another
+0.001.

## Decision rule

- **PASS**: Δr (bundle vs full RH3_FEATS baseline) ≥ +0.005 AND ≥3/4
  positive on real-data years (2022/23/24/25) AND both coef signs OK.
- **MARGINAL**: 0 < Δr < +0.005.
- **REJECTED**: Δr ≤ 0.
- **Comparison metric**: bundle Δr vs (kpct marginal + xwoba marginal) —
  if bundle > sum, independence bonus exists; if bundle < sum,
  redundancy.

---

# DATA GAP — not run

Bundle cannot be evaluated because `milb_aaa_xwoba_prior` could not be
built. See `milb_aaa_xwoba_prior_2026-05-24.md` for full data-source
audit (pybaseball v2.2.7 lacks `statcast_minor_league_batter`; Savant
leaderboard CSVs ignore `hfMinors=AAA`; Savant `/statcast-search-minors`
hard-caps at 25K rows requiring a custom date-chunked aggregation;
MLB Stats API `expectedStatistics` with `sportId=11` returns
non-seasonal stat values).

**Verdict: BLOCKED-DATA-GAP.** No code shipped. RH3_FEATS unchanged.

## Re-attempt prerequisite

Ship `build_milb_aaa_xwoba_priors.py` against the chunked Savant
endpoint (~half-day build); then this bundle test becomes a 5-minute
join + re-run of the existing `_validate_milb_helper.run_milb_candidate_eval`
with a 2-feature extension list.

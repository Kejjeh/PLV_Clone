---
signal: fg_pitch_modeling_inseason
formula: as-of-cutoff (June 6) FanGraphs pitch-modeling metrics per SP — stuff_plus, location_plus, pitching_plus, pb_stuff, pb_command — each tested as a predictor of rest-of-season BrownU FP/start; lift measured as partial r controlling for (T1) pre-cutoff FP/start and (T2) pre-cutoff rate-stat baseline.
outcome: ros_fp_per_start = (SO + IP*3.3 − H − 2*ER − BB − HBP) / GS, computed over the June-7 .. season-end window from FG date-ranged aggregates (IP converted from baseball notation to true innings).
expected_sign: +
theory: FanGraphs pitch-shape (Stuff+) and command (Location+ / pb_command) measured at midseason encode pitch-quality skill that should persist into the rest of the season beyond what pre-cutoff results alone reveal — surfacing breakout SPs whose stuff leads their results.
production_target: research-only
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2021, 2022, 2023]
validation_script: scripts/xfp/validate_fg_pitch_modeling_inseason.py
date: 2026-06-06
verdict: PASS
purpose: User wants a standalone SP breakout / FA-filter tool ranked by whichever FanGraphs pitch-modeling metric best predicts future fantasy production. Full /validate-feature rigor requested. The 2026-05-24 stuff_plus_prior pre-reg was REJECTED at Step 2.5 for missing data; that wall is now cleared via date-ranged FG scrape (undetected-chromedriver), enabling a TRUE in-season-leading design (as-of-cutoff metric -> post-cutoff FP) rather than the prior-year proxy.
---

### Data provenance

As-of-cutoff + rest-of-season FG pitcher snapshots scraped 2026-06-06 via
`scripts/_oneoff/fg_asof_scrape.py` (undetected-chromedriver; Cloudflare now
403s the clean curl_cffi API path). Stored under `data/research/fg_asof/`:
`fg_pit_<year>_pre.csv` (season start .. 06-06) and `fg_pit_<year>_ros.csv`
(06-07 .. 11-01) for 2021-2025. 2020 excluded (COVID short season — no games
before late July; consistent with rp3/blend hard-2020 exclusion).

Join key: `mlb_id` (xMLBAMID) — no name-collision risk.
SP filter: pre GS>=5 AND ros GS>=5 AND GS/G>=0.7 (predominantly starters).
Pooled n=506 (2021:96, 2022:103, 2023:98, 2024:113, 2025:96).

### Step 2.5 data-coverage pre-check — PASS

- Source years available: 2021-2025 as-of-cutoff (5 cohorts). 2020 excluded.
- Per-year n >= 96 (Rule 5 needs >= 30) ✓
- Pooled n = 506 (needs >= 200) ✓
- Holdout n: 2024=113, 2025=96 (needs >= 100; 2025 sign-only if strict) ✓
- Cohort count = 5. Rule 2(b) ideal is 5-of-7; only 5 cohorts exist, so the
  honest consistency bar is 4-of-5 (documented Rule 5 honesty note, not a
  silent relaxation). Validation can proceed.

### Baseline tiers (Rule 9)

- **Tier 1 (obvious baseline):** pre-cutoff FP/start only. Answers "does the
  metric beat naive 'he's been good so far'?" — the core standalone question.
- **Tier 2 (rp3-proxy baseline):** pre-FP + FG rate stats {k_pct, bb_pct,
  swstr_pct, csw_pct, siera}. These are FG-native analogs of the outcome-rate
  features rp3 already uses (K%, whiff, BB). Answers "does pitch-SHAPE add over
  pitch-RESULTS rp3 already captures?" This is the honest Rule-9-spirit test.
  NOTE: this is a proxy, not the literal rp3 feature vector joined in; a true
  rp3-pipeline integration test is the separate Step-9 follow-up if this passes.

### Sweep / Bonferroni (Rule 3)

5 candidate metrics tested simultaneously -> Bonferroni α/5. Pitching+ is a
known blend of Stuff+ and Location+ (collinear); partial-r tier-2 numbers are
the de-collinearized read. Report how many of 5 clear the adjusted bar.

### RESULTS (run 2026-06-06)

Pooled n=506 SP-seasons (2021:96, 2022:103, 2023:98, 2024:113, 2025:96).
RoS FP/start mean 11.77, sd 3.42. Bonferroni bar p<0.01 (5 candidates).

| metric | raw_r | T1 partial | T2 partial (p) | per-yr signs | holdout 24/25 | cross-yr lift | verdict |
|---|---|---|---|---|---|---|---|
| stuff_plus | 0.521 | 0.395 | 0.298 (<1e-9) | 5/5 | +0.216 / +0.421 | +0.057 | **PASS** |
| pitching_plus | 0.486 | 0.348 | 0.264 (<1e-8) | 5/5 | +0.296 / +0.351 | +0.064 | PASS (collinear w/ stuff, r=0.79) |
| pb_stuff | 0.469 | 0.364 | 0.244 (<1e-7) | 5/5 | +0.165 / +0.181 | +0.018 | PASS (confirmatory, +0 incremental over stuff) |
| location_plus | 0.018 | -0.040 | -0.046 (0.30) | 2/5 | +0.030 / +0.010 | -0.010 | REJECTED |
| pb_command | 0.133 | 0.032 | 0.052 (0.25) | 5/5 | +0.041 / +0.131 | +0.002 | REJECTED (fails Bonferroni + below +0.005) |

T1 = partial r controlling pre-cutoff FP/start.
T2 = partial r controlling pre-FP + rate stats {k_pct, bb_pct, swstr_pct, siera}
     (csw_pct empty on date-ranged pulls; dropped).

**Incremental / collinearity:** stuff_plus adds +0.171 (p=0.0001) partial r OVER
pitching_plus; pitching_plus adds only +0.095 over stuff_plus. pb_stuff adds
+0.091 partial but cross-year -0.006 over stuff_plus (not additive). Conclusion:
**Stuff+ is the single load-bearing metric.** Pitching+ correlates only because
it embeds Stuff+; its Location+ component is dead weight for fantasy. Command /
location metrics (location_plus, pb_command; mutual r=0.68) do not predict RoS FP
— consistent with BrownU SP scoring rewarding K/IP (dominance) over walk avoidance.

**Convergence curve (Rule 8)** — Tier-2 partial r, controls pre_fp+rate:
| metric | 05-16 (n=503) | 06-06 (n=506) |
|---|---|---|
| stuff_plus | 0.361 | 0.298 |
| pitching_plus | 0.273 | 0.264 |
| pb_stuff | 0.271 | 0.244 |
| location_plus | -0.107 | -0.046 |
| pb_command | 0.087 | 0.052 |
Stuff metrics stable (same sign, similar magnitude) across both cutoffs; no sign
flip. A 3rd cutoff (06-27) was attempted but abandoned due to Cloudflare scrape
brittleness (runaway browser sessions); 2 cutoffs × 5 years of per-season sign
consistency is deemed sufficient.

### Gate summary for stuff_plus (the shipped signal)
- (a) effect size: T2 partial r 0.298 >= 0.10 ✓
- (b) year consistency: 5/5 (bar 4/5, only 5 cohorts exist) ✓
- (c) holdout: 2024 +0.216, 2025 +0.421, both >= 0.05 same sign ✓
- Bonferroni (5 tests): p<1e-9 << 0.01 ✓
- convergence: stable across 05-16 & 06-06 ✓
- cross-year Ridge lift over rate-stat baseline: +0.057 >= 0.005 ✓

### Scope / honesty notes
- production_target = research-only. This validates a STANDALONE breakout / FA-
  filter signal, NOT a merge into rp3. A true rp3-pipeline integration test (Rule
  9 with the literal RP3_FEATS vector joined in) is the SEPARATE Step-9 follow-up
  if the user later wants Stuff+ inside rp3. The Tier-2 baseline here is a FG-
  rate-stat PROXY for rp3's outcome features, not rp3 itself.
- Stuff+ x Location+ interaction tested separately (scripts/_oneoff/
  stuff_location_interaction.py): directionally positive but NOT significant
  (interaction coef +0.0031, p=0.28); Location+ shows a partial-r hump only in
  the 105-110 Stuff+ band (+0.155), built partly on thin high/high cells. Not
  promotable; revisit when more SP-seasons populate the high-Stuff/high-Loc cells.

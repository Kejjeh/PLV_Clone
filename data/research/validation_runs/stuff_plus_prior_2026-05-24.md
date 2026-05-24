---
signal: stuff_plus_prior
formula: prior-year FanGraphs Stuff+ per pitcher, joined onto current-season rp3 outcome rows
outcome: fp_per_start_actual in year T (rp3 framing)
expected_sign: +
theory: FG Stuff+ encodes pitch-shape quality (velo + spin + movement + release) independent of outcome. Theoretically orthogonal to the outcome-based features in RP3_FEATS (K%, whiff, BB, HR), and should add lift on the "stuff > results" gap pitchers.
production_target: rp3
framing: full-year (prior-year Stuff+ predicts current-year per-start outcome)
holdout_years: [2026]
training_years: [2018-2025]
validation_script: scripts/xfp/validate_stuff_plus_prior.py (NOT WRITTEN — fails Step 2.5 data availability)
date: 2026-05-24
verdict: REJECTED — Step 2.5 data unavailable
purpose: User asked to mine cheap data sources. v11 SP model history references historical FG Stuff+/Pitching+ scrapes (undetected-chromedriver). Test whether those landed in the cache and are usable as a prior-year feature.
---

### Step 2.5 data coverage audit

Searched `data/research/xfp_cache/` for any of:
- `*stuff*`, `*pitching_plus*`, `*fg_*`, `*fangraphs*`, `*plv*`, `*plus*`

Result: **no matching files exist**. The pitcher-side files in the cache
are limited to:
- `pitcher_counting_stats_{2018-2026}.json` (MLB Stats API)
- `pitcher_prior_career.csv`, `pitcher_splits.csv`, `pitcher_schedule_2026.csv`
- `rolling_pitchers_2018_2026.csv`
- `sp_pitch_type_pfxz_2015_2026.csv` (pitch-type IVB from statcast — already
  feeds `avg_pfxz_to`, which was REJECTED 2026-05-24)
- `milb_pitcher_*` (minor-league)

There is no FG Stuff+ / Pitching+ cache. The historical scrape referenced
in v11 docs either was not retained in this repo or was deleted.

### Verdict

REJECTED at Step 2.5 — required source data is not on disk.

### What would unblock validation

- One-time FG Stuff+ scrape via undetected-chromedriver for 2020-2025
  leaderboards (~6 csvs, ~500 SPs each). Rate-limited but feasible
  outside of cron. Out of scope for this task per user constraint
  ("Don't try to re-scrape FG — rate limits + brittle").
- Alternative: PLA/PLV via pitcherlist data export, if available.
- Note: `sp_pitch_type_pfxz_2015_2026.csv` is the closest in-repo proxy
  (per-pitch-type IVB) but the average-IVB feature `avg_pfxz_to`
  already REJECTED at -0.0007 lift (2026-05-24), suggesting outcome-rate
  features in RP3_FEATS already absorb the in-repo pitch-shape signal.
  An external Stuff+ would have to clear a high bar to add lift.

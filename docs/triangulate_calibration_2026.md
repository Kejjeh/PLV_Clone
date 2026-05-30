# /triangulate Override Calibration — 2026-05

Empirical backtest of the three 4th-lens overrides against the hitter (N=4,824) and SP (N=1,967) archetype career panels.

**Method.** For each override, build the trigger set (player-years matching the IF-clause) and a comparison set (similar bearish trajectory, override does NOT fire). Compare T+1 outcomes: actual `next_fp`, % beating `t1_fp_projection` ("bounce rate"), and % achieving an archetype upgrade. Sweep the key parameter to find the lift-maximising threshold.

## Executive Summary

| override               |   n_trigger |   bounce_trig |   bounce_comp |   lift_pp | recommendation                                                                  |
|:-----------------------|------------:|--------------:|--------------:|----------:|:--------------------------------------------------------------------------------|
| A: speed-profile HOLD  |         321 |         0.467 |         0.491 |    -0.024 | REJECT — production thr=60 shows -2.4pp lift; best alternative (50) only +2.5pp |
| B: post-TJ ramp HOLD   |          13 |         0.231 |       nan     |   nan     | INSUFFICIENT DATA (n=13 < 20)                                                   |
| C: process-intact HOLD |         203 |         0.448 |       nan     |   nan     | TIGHTEN to 25 (lift 2.2pp vs current)                                           |

*`bounce_trig` / `bounce_comp` = share of player-years where `next_fp > t1_fp_projection`. Lift is the percentage-point delta.*

---

## Override A — Speed-profile HOLD (hitters)

**Rule.** `(SPEED_TOOL ≥ 60 OR SB ≥ 60) AND traj ∈ {TRENDING_DOWN, STABLE}` → HOLD

**Comparison set.** Same trajectory, fails the speed condition.

### Threshold sensitivity (SPEED_TOOL/SB cutoff)

|   threshold |   trig_n |   trig_next_fp_mean |   trig_t1_proj_mean |   trig_beat_rate |   trig_upgrade_rate |   comp_n |   comp_next_fp_mean |   comp_t1_proj_mean |   comp_beat_rate |   comp_upgrade_rate |
|------------:|---------:|--------------------:|--------------------:|-----------------:|--------------------:|---------:|--------------------:|--------------------:|-----------------:|--------------------:|
|          50 |      860 |               0.483 |               0.491 |            0.498 |               0.295 |      690 |               0.467 |               0.476 |            0.472 |               0.231 |
|          55 |      559 |               0.482 |               0.491 |            0.49  |               0.279 |      991 |               0.472 |               0.48  |            0.484 |               0.259 |
|          60 |      321 |               0.48  |               0.496 |            0.467 |               0.262 |     1229 |               0.475 |               0.481 |            0.491 |               0.268 |
|          65 |      158 |               0.482 |               0.5   |            0.456 |               0.279 |     1392 |               0.475 |               0.483 |            0.49  |               0.265 |
|          70 |       75 |               0.495 |               0.501 |            0.467 |               0.243 |     1475 |               0.475 |               0.484 |            0.487 |               0.268 |

**Best lift at threshold = 50** (lift = 2.5pp on beat-rate).

**Recommendation: REJECT — production thr=60 shows -2.4pp lift; best alternative (50) only +2.5pp**

### Named comp examples (top 8 by next_fp at threshold 60)

| name             |   year |   SPEED_TOOL |   SB | traj_flag     |   t1_fp_projection |   next_fp | archetype      | next_arch     |
|:-----------------|-------:|-------------:|-----:|:--------------|-------------------:|----------:|:---------------|:--------------|
| Cody Bellinger   |   2018 |           62 |   59 | TRENDING_DOWN |               0.54 |      0.9  | AVERAGE_HITTER | GOAT_TIER     |
| Mike Trout       |   2018 |           64 |   63 | STABLE        |               0.72 |      0.89 | GOAT_TIER      | GOAT_TIER     |
| Mike Trout       |   2017 |           65 |   65 | STABLE        |               0.7  |      0.84 | GOAT_TIER      | GOAT_TIER     |
| José Ramírez     |   2019 |           56 |   72 | TRENDING_DOWN |               0.65 |      0.83 | PURE_HITTER    | CONTACT_POWER |
| Ronald Acuña Jr. |   2019 |           65 |   74 | STABLE        |               0.64 |      0.81 | GOAT_TIER      | GOAT_TIER     |
| Paul Goldschmidt |   2016 |           52 |   62 | TRENDING_DOWN |               0.57 |      0.79 | BALANCED_EYE   | CONTACT_POWER |
| José Ramírez     |   2024 |           57 |   70 | STABLE        |               0.71 |      0.79 | CONTACT_POWER  | PURE_HITTER   |
| José Ramírez     |   2021 |           57 |   69 | STABLE        |               0.73 |      0.79 | CONTACT_POWER  | CONTACT_POWER |

---

## Override B — Post-TJ ramp HOLD (SPs)

**Rule.** `CAREER_LOW + walk-driven archetype + (SWING_MISS − WALK_AVOID) ≥ 10 + career_yr ≥ 3` → HOLD

Walk-driven archetypes used: WILD_MID, WILD_FIREBALLER, STUFF_MOVE_WILD, MOVE_WILD, SINKER_WILD, BAD_BIG_INNINGS, LIABILITY.

### Threshold sensitivity (SWING_MISS − WALK_AVOID gap)

|   sm_minus_wa_thr |   trig_n |   trig_next_fp_mean |   trig_t1_proj_mean |   trig_beat_rate |   trig_upgrade_rate |   comp_n |   comp_next_fp_mean |   comp_t1_proj_mean |   comp_beat_rate |   comp_upgrade_rate |
|------------------:|---------:|--------------------:|--------------------:|-----------------:|--------------------:|---------:|--------------------:|--------------------:|-----------------:|--------------------:|
|                 0 |       16 |               9.831 |              10.189 |            0.375 |               0.625 |        2 |               9.077 |               7.92  |            0.5   |               1     |
|                 5 |       16 |               9.831 |              10.189 |            0.375 |               0.625 |        2 |               9.077 |               7.92  |            0.5   |               1     |
|                10 |       13 |               8.77  |              10.468 |            0.231 |               0.538 |        5 |              12.286 |               8.556 |            0.8   |               1     |
|                15 |       10 |               9.573 |              10.851 |            0.3   |               0.5   |        8 |               9.965 |               8.795 |            0.5   |               0.875 |
|                20 |        6 |              10.35  |              11.008 |            0.5   |               0.833 |       12 |               9.445 |               9.402 |            0.333 |               0.583 |

**Best lift at SM−WA ≥ 20** (lift = 16.7pp).

### career_yr ≥ 3 vs gap-year proxy

| proxy        |   n |   next_fp_mean |   t1_proj_mean |   beat_rate |   upgrade_rate |
|:-------------|----:|---------------:|---------------:|------------:|---------------:|
| career_yr>=3 |  13 |           8.77 |         10.468 |       0.231 |          0.538 |
| gap_year     |  22 |           9.59 |         10.797 |       0.273 |          0.667 |

*Gap-year proxy = no prior-year row in the panel (a crude TJ/injury-year approximation). Compared head-to-head against the looser career_yr ≥ 3 rule.*

**Recommendation: INSUFFICIENT DATA (n=13 < 20)**

### Named comp examples (career_yr ≥ 3 trigger, top 8 by next_fp)

| name            |   year |   career_year | gap_year   | archetype       |   SWING_MISS |   WALK_AVOID |   t1_fp_projection |   next_fp | next_arch     |
|:----------------|-------:|--------------:|:-----------|:----------------|-------------:|-------------:|-------------------:|----------:|:--------------|
| Nathan Eovaldi  |   2019 |             4 | False      | WILD_MID        |           51 |           26 |              10.11 |     13.29 | MOVE_CTRL_ACE |
| Jose Quintana   |   2021 |             6 | True       | BAD_BIG_INNINGS |           60 |           32 |              10    |     11.38 | PURE_MOVEMENT |
| Brad Peacock    |   2017 |             3 | True       | STUFF_MOVE_WILD |           66 |           38 |              12.92 |     11.33 | AVERAGE_4_5   |
| Trevor Cahill   |   2017 |             3 | True       | WILD_MID        |           55 |           33 |              10.24 |     10.6  | AVERAGE_4_5   |
| Carlos Rodón    |   2017 |             3 | False      | WILD_MID        |           57 |           38 |              11.06 |     10.52 | LIABILITY     |
| Luis Gil        |   2024 |             3 | True       | WILD_MID        |           59 |           28 |              11.28 |      9.51 | WILD_MID      |
| Julio Teheran   |   2019 |             5 | False      | WILD_MID        |           46 |           32 |               9.26 |      9.18 | PURE_CONTROL  |
| Carlos Martinez |   2018 |             4 | False      | MOVE_WILD       |           53 |           35 |              11.09 |      8.43 | FILLER        |

---

## Override C — Process-intact HOLD (SPs)

**Rule.** `traj ∈ {TRENDING_DOWN, CAREER_LOW} AND model_rank ≤ 50` → HOLD

Using panel `rank_in_year` as the model-rank proxy.

### Threshold sensitivity (rank_in_year)

|   rank_thr |   trig_n |   trig_next_fp_mean |   trig_t1_proj_mean |   trig_beat_rate |   trig_upgrade_rate |   comp_n |   comp_next_fp_mean |   comp_t1_proj_mean |   comp_beat_rate |   comp_upgrade_rate |
|-----------:|---------:|--------------------:|--------------------:|-----------------:|--------------------:|---------:|--------------------:|--------------------:|-----------------:|--------------------:|
|         25 |       93 |              13.711 |              13.908 |            0.452 |               0.194 |      740 |               9.766 |              10.336 |            0.43  |               0.291 |
|         50 |      203 |              12.638 |              12.937 |            0.448 |               0.219 |      630 |               9.423 |              10.025 |            0.427 |               0.299 |
|         75 |      333 |              11.752 |              12.244 |            0.411 |               0.183 |      500 |               9.177 |               9.73  |            0.446 |               0.343 |
|        100 |      461 |              11.189 |              11.754 |            0.416 |               0.218 |      372 |               8.99  |               9.472 |            0.452 |               0.356 |

**Best lift at rank ≤ 25** (lift = 2.2pp).

### Alternative proxy — OVERALL rating cutoff

|   OVERALL_thr |   trig_n |   trig_next_fp_mean |   trig_t1_proj_mean |   trig_beat_rate |   trig_upgrade_rate |   comp_n |   comp_next_fp_mean |   comp_t1_proj_mean |   comp_beat_rate |   comp_upgrade_rate |
|--------------:|---------:|--------------------:|--------------------:|-----------------:|--------------------:|---------:|--------------------:|--------------------:|-----------------:|--------------------:|
|            50 |      395 |              11.411 |              12.215 |            0.38  |               0.176 |      438 |               9.12  |               9.4   |            0.479 |               0.372 |
|            55 |      214 |              12.416 |              13.137 |            0.397 |               0.206 |      619 |               9.443 |               9.904 |            0.444 |               0.306 |
|            60 |      113 |              13.477 |              14.119 |            0.434 |               0.204 |      720 |               9.693 |              10.204 |            0.432 |               0.292 |
|            65 |       54 |              14.468 |              15.207 |            0.444 |               0.222 |      779 |               9.911 |              10.425 |            0.431 |               0.284 |

**Recommendation: TIGHTEN to 25 (lift 2.2pp vs current)**

### Named comp examples (rank ≤ 50 trigger, top 8 by next_fp)

| name             |   year | traj_flag     |   rank_in_year |   OVERALL |   t1_fp_projection |   next_fp | archetype       | next_arch       |
|:-----------------|-------:|:--------------|---------------:|----------:|-------------------:|----------:|:----------------|:----------------|
| Clayton Kershaw  |   2015 | CAREER_LOW    |              1 |        80 |              18.63 |     23.53 | MT_RUSHMORE     | MT_RUSHMORE     |
| Corey Kluber     |   2016 | CAREER_LOW    |              7 |        66 |              14.55 |     22.18 | STUFF_PLUS_MOVE | MT_RUSHMORE     |
| Chris Sale       |   2016 | TRENDING_DOWN |              5 |        62 |              14.01 |     20.38 | STUFF_PLUS_CTRL | MT_RUSHMORE     |
| Max Scherzer     |   2016 | TRENDING_DOWN |              2 |        73 |              17.01 |     20.21 | PURE_STUFF      | STUFF_PLUS_MOVE |
| Tyler Glasnow    |   2025 | TRENDING_DOWN |             28 |        56 |              11.05 |     19.9  | WILD_MID        | PURE_STUFF      |
| Justin Verlander |   2017 | TRENDING_DOWN |             11 |        52 |              12.07 |     19.63 | AVERAGE_4_5     | STUFF_PLUS_CTRL |
| Cam Schlittler   |   2025 | CAREER_LOW    |             38 |        55 |              12.51 |     19.49 | AVERAGE_4_5     | MT_RUSHMORE     |
| Max Scherzer     |   2015 | CAREER_LOW    |              2 |        76 |              18.78 |     19.3  | STUFF_PLUS_CTRL | PURE_STUFF      |

---

## Suggested code changes to `apply_overrides()`

- **Override A (SPEED/SB threshold)**: REJECT — production thr=60 shows -2.4pp lift; best alternative (50) only +2.5pp
- **Override B (SWING_MISS − WALK_AVOID gap)**: INSUFFICIENT DATA (n=13 < 20)
- **Override C (rank cutoff)**: TIGHTEN to 25 (lift 2.2pp vs current)

If any line above reads REJECT or INSUFFICIENT DATA, leave the production threshold untouched and treat this as a known-limitation note rather than a code change.

# RP archetype data audit

**Date:** 2026-05-28
**Purpose:** Scope what's actually available before writing `build_rp_archetypes.py` to parallel `build_sp_archetypes.py` / `sp_ratings_master.csv`.
**Goal:** A `data/research/rp_ratings_master.csv` analog with 20-80 rate-skill sub-domains within-year, archetype labels, age tier, trajectory, T+1/T+2 outcomes, comp panel.

The SP build leans on `data/research/xfp_cache/sp_multiyr_2015_2025.csv` (player-year, all 6 rate-skill inputs present 2015-2026, n=2,159, GS-floor 6 rated / 20 full).

---

## 1. Existing RP-relevant files

### 1a. Primary RP player-year aggregate — `data/research/xfp_cache/relievers_multiyr_2018_2026.csv`

| Property | Value |
|---|---|
| Shape | **2,221 rows × 51 cols** |
| Row grain | pitcher-season (one row per pitcher per year) |
| Year coverage | **2018-2026** (NOT 2015-2017) |
| Per-year counts | 2018: 282, 2019: 285, 2020: 133 (COVID-short), 2021: 302, 2022: 285, 2023: 258, 2024: 265, 2025: 279, 2026: 132 (partial) |
| Join key to mlbam | `pitcher` (int MLBAM id) |
| Role tag | `role` column present: `closer` (317), `setup` (324), `middle` (929), `long_low` (651) |
| FP fields | `fp`, `fp_per_g`, `fp_per_ip` — all populated |

**Columns present (51):**
`pitcher, name, season, team_abbr, g, gs, gf, ip, tbf_api, wins, losses, sv, svo, hld, bs, k, bb, h, er, hr_allowed, hbp, era, whip, role, fp, fp_per_g, fp_per_ip, k_pct, bb_pct, pitches, tbf, bip, in_zone, swing, contact, swstr, called_strike, z_swing, o_swing, avg_velo, avg_pfxz, woba_v_sum, woba_d_sum, swstr_pct, c_plus_swstr, zone_pct, z_swing_pct, o_swing_pct, contact_pct, xwoba_per_pa, year`

**CRITICAL GAPS** vs SP `sp_multiyr_2015_2025.csv`:

| Missing column | Used in SP for | Workaround |
|---|---|---|
| `barrel_pct` / `barrel_n` | DAMAGE_SUPP rating | Derive from statcast parquet (2015-2026) or join FanGraphs (2020-2026, ~75% RP cov) |
| `hard_hit_pct` / `hard_hit_n` | DAMAGE_SUPP rating | Same as above |
| `gb_pct` / `gb_n` | GB_TENDENCY rating | Same as above |
| `xwoba_contact` (xwOBA on contact only) | DAMAGE_SUPP rating | Derive from statcast parquet |
| `avg_ev` | secondary (SP has it but doesn't use in archetype) | Derive from statcast parquet |

Coverage of present columns on eligible (G_relief ≥ 20, TBF ≥ 50) RP-seasons: **100% on swstr_pct, called_strike, c_plus_swstr, avg_velo, xwoba_per_pa, k_pct, bb_pct** — i.e. the SWING_MISS / CALLED_STRIKE / WALK_AVOID / velo_rating sub-domains are 100% computable today straight from this file.

### 1b. RP rolling intra-year — `data/research/xfp_cache/rolling_relievers_2018_2026.csv`

| Property | Value |
|---|---|
| Shape | 11,952 rows × 68 cols |
| Row grain | **pitcher-year-split_day** (multiple cuts within year for rolling-window features) |
| Year coverage | 2018-2026 |
| Unique pitcher-year cells | 3,411 |
| split_day values | 30, 60, 90, 120, 185 (+ 181/186/193 for late-season cuts) |

Adds these RP-specific cols not in `relievers_multiyr`:
- `gf_pct_to`, `sv_per_g_to`, `hld_per_g_to`, `sv_plus_hld_to`
- `fp_skill_to`, `fp_with_role_to`
- `role_lag1`, `sv_lag1`, `hld_lag1`, `g_lag1`, `ip_lag1`, `fp_lag1`, `fp_per_g_lag1`, `k_pct_lag1`, `bb_pct_lag1`, `xwoba_per_pa_lag1`
- `role_closer_lag1`, `role_setup_lag1`, `role_middle_lag1`
- `prior_closer_on_il`, `is_team_prior_closer`, `prior_closer_returned_recently`, `prior_closer_days_since_return`
- `fp_year_total`

This file already encodes **role persistence YoY** via `role_*_lag1` and **closer-of-record context** via the `prior_closer_*` block — both crucial for RP archetype labeling.

### 1c. `rolling_pitchers_2018_2026.csv` — combined SP+RP rolling

5,308 rows × 76 cols, has `barrel_pct_to`, `hard_hit_pct_to`, `gb_pct_to`, `xwoba_on_contact_to`. This is filtered to **SPs** (`gs_to` is populated, no equivalent for relief grain). NOT a direct RP backfill.

### 1d. `pitcher_splits.csv` — L/R splits

| Property | Value |
|---|---|
| Shape | 4,021 rows × 7 cols |
| Cols | `pitcher, year, p_throws, tbf_vs_L, tbf_vs_R, xwoba_vs_L, xwoba_vs_R` |
| Year coverage | **2022-2026 only** (NOT 2018-2021) |
| RP-season join coverage | **54.9% of eligible RP-seasons** (1,219 / 2,221) |
| Per year | 2022: 871, 2023: 863, 2024: 855, 2025: 873, 2026: 559 (partial) |

L/R splits are **partial** — only available for 2022+ and only ~55% of RP-seasons join.

### 1e. `pitcher_prior_career.csv`

| Property | Value |
|---|---|
| Shape | 2,159 rows × 4 cols |
| Cols | `pitcher, year, prior_career_fp_per_start, prior_career_gs` |
| Year coverage | 2015-2026 |
| Note | This is **SP-only** by content (FP per *start*); for RP comp matching we'd need a parallel `prior_career_fp_per_g` derived from `relievers_multiyr`. |

### 1f. `pitcher_primary_team_2018_2026.csv`

7,363 rows, `(pitcher, year, pitcher_team)` — covers all pitchers; usable to tag team context for RP role/closer-of-record analysis.

### 1g. RP projection output — `data/outputs/xfp_rprs2_projections.csv`

| Property | Value |
|---|---|
| Shape | 282 rows × 24 cols |
| Row grain | one row per active 2026 RP |
| Key cols | `pitcher, name_api, role_lag1, sv_lag1, hld_lag1, g_to, sv_to, hld_to, gf_to, gf_pct_to, sv_per_g_to, sv_2026, hld_2026, fp_actual_2026, xfp_full_year, xfp_p25, xfp_p75, xfp_ros, replacement_xfp, replacement_delta, signal` |
| Usage in archetype build | **Source of validated ROS RP projection (= the rprs2 number)** — would attach to 2026 RPs as `t1_fp_projection`-equivalent for the in-progress year. |

### 1h. `data/outputs/closer_persistence.csv`

170 rows, cols `team, year, mid_pitcher, mid_sv, late_pitcher, late_sv, same_closer`. Encodes mid- vs late-season closer-of-record per team-year; thin (170 rows = ~30 teams × 6 years × 1 mid/late). Useful as a sanity flag, not as primary archetype input.

### 1i. `data/outputs/bullpen_quality.csv`

240 rows, `team, year, bullpen_fp, bullpen_ip, n_rps, bullpen_fp_per_ip` — team-bullpen aggregate, irrelevant to per-RP archetype.

### 1j. FanGraphs cache — `data/outputs/fangraphs_pitchers_{2020..2026}.csv`

| Year | Rows | RP-ish rows (G≥20, GS<5) | Cols of interest |
|---|---|---|---|
| 2020 | 490 | 133 | `barrel_pct, hard_hit_pct, gb_pct, avg_ev, stuff_plus, location_plus, pitching_plus` |
| 2021 | 500 | 221 | same |
| 2022 | 500 | 217 | same |
| 2023 | 500 | 209 | same |
| 2024 | 500 | 208 | same |
| 2025 | 500 | 206 | same |
| 2026 | 374 | 240 | same (missing `xera` and `pb_xrv100` is identical to 2025 file) |

Top-500 cap means some marginal RPs are silently excluded each year.

**Critical FG gaps:** No `gmLI`, no `IR`/`IS` (inherited runner / inherited scored), no `WPA`, no `HLD`, no `SV`. The cache is **stuff-and-results focused**, not leverage-focused.

**Join coverage to RP-multiyr** (eligible RPs only):

| Year | Eligible RPs | FG barrel/HH/GB cov |
|---|---|---|
| 2020 | 132 | **100.0%** |
| 2021 | 299 | 73.2% |
| 2022 | 282 | 76.6% |
| 2023 | 255 | 82.0% |
| 2024 | 261 | 78.2% |
| 2025 | 277 | 74.0% |
| 2026 | 126 (partial) | 0.0% in current snapshot |

2026 FG file does have 240 RP-ish rows but they aren't joining cleanly — likely a mid-season FG snapshot vs current `relievers_multiyr` mismatch in `mlb_id` for 2026 in-progress; investigate before relying on it.

### 1k. Raw statcast — `data/research/xfp_cache/statcast_{2015..2026}.parquet`

| Property | Value |
|---|---|
| Files | 12 parquet files, ~700k pitch-level rows each |
| Year coverage | **2015-2026** |
| Has `launch_speed`, `launch_angle`, `bb_type` | YES (all 12 years) |
| Has `estimated_woba_using_speedangle` | YES (xwOBA per BBE → derive xwoba_contact) |
| Has `launch_speed_angle` | YES (Statcast's official barrel classification 1-6) |
| Unique pitchers / year | ~855 (2024 verified) |

Prototype confirmed: filtering to relief PAs (= pitcher ≠ first-inning-of-game pitcher) for 2015 yields 277 pitchers with ≥20 relief outings and ≥50 TBF, totaling 57,809 RP-PAs and 39,509 BBE — sufficient density to derive barrel/HH/GB/xwoba_contact per RP-season directly from statcast for **2015-2017** (the years FG doesn't cover).

### 1l. Pitch-type / movement cache — `data/research/xfp_cache/sp_pitch_type_pfxz_2015_2026.csv`

Shape 8,580 × 5 (`pitcher, bb_pfxz, fb_pfxz, pfxz_spread, year`), 2,248 unique pitchers — covers both SPs and RPs in practice. Usable for pitch-shape secondary tagging (e.g. POWER vs FINESSE within MOVEMENT label).

### 1m. Age — `data/outputs/sp_age_career.csv` + `data/research/xfp_cache/milb_pitcher_ages.csv`

`sp_age_career.csv`: 8,792 rows × 5 cols (`pitcher, year, age, age_residual_28, career_year`), 2015-2026, 2,625 unique pitchers — despite the file name, **covers RPs as well**.

Join coverage to RP-multiyr: **94.0%** of eligible RP-seasons have age.

`milb_pitcher_ages.csv` (6,990 pitcher rows, `pitcher, name, birthDate`) covers **866 / 877** unique RP pitchers as birthDate fallback. With both, age coverage is effectively 100%.

---

## 2. Sub-domain feasibility for the RP archetype build

| Sub-domain | Required signal | Source(s) | 2015-17 | 2018-26 | Verdict |
|---|---|---|---|---|---|
| **SWING_MISS** | `swstr_pct` | `relievers_multiyr.swstr_pct` | NO (no 2015-17 RP roll-up) | 100% cov 2018-26 | **PARTIAL — AVAILABLE 2018+** |
| **CALLED_STRIKE** | called-strike rate, csw% | `relievers_multiyr.called_strike` + `c_plus_swstr` | NO | 100% cov 2018-26 | **PARTIAL — AVAILABLE 2018+** |
| **DAMAGE_SUPP** | `xwoba_contact`, `barrel_pct` | NOT in `relievers_multiyr` — need FG (2020-26, 74-100% cov) OR statcast-derived (2015-26, all years) | YES via statcast | YES via statcast (or FG fallback) | **AVAILABLE — requires new derivation step** |
| **GB_TENDENCY** | `gb_pct`, optional avg LA | NOT in `relievers_multiyr` — need FG (2020-26, 74-100%) OR statcast (2015-26) | YES via statcast | YES via statcast | **AVAILABLE — requires new derivation step** |
| **WALK_AVOID** | `bb_pct` | `relievers_multiyr.bb_pct` | NO | 100% cov 2018-26 | **PARTIAL — AVAILABLE 2018+** |
| **velo_rating** | `avg_velo` | `relievers_multiyr.avg_velo` | NO direct roll-up | 100% cov 2018-26 | **PARTIAL — AVAILABLE 2018+** (statcast-derivable for 2015-17 if wanted) |
| **gmLI** (game leverage) | gmLI per outing | NOT in any current cache; FG file lacks it | NO | NO | **NOT-AVAILABLE — needs FanGraphs re-scrape** |
| **IP/G** (multi-inning capacity) | IP / G | `relievers_multiyr.ip / g` → trivial | NO | 100% cov 2018-26 | **AVAILABLE 2018+** (and easily derivable from statcast for 2015-17) |
| **SV / HLD** | sv, hld | `relievers_multiyr.sv, hld` | NO | 100% cov 2018-26 | **AVAILABLE 2018+** |
| **Role tag** (closer / setup / middle / mop-up) | role string | `relievers_multiyr.role` (already labeled `closer/setup/middle/long_low`) | NO | 100% cov 2018-26 | **AVAILABLE 2018+** |
| **Role persistence YoY** | role last year | `rolling_relievers.role_lag1` and lag block | NO | computable for 2019-26 | **AVAILABLE 2019+** |
| **L/R splits** (TBF + xwOBA vs L/R) | `pitcher_splits.csv` | only 2022-2026, 55% cov of RP-seasons | NO | **PARTIAL 2022-26 only, ~55%** | **PARTIAL — use as secondary signal only** |
| **Inherited-runner-stranded rate** (IR / IS) | IR, IS, IRS% | NOT in any cache | NO | NO | **NOT-AVAILABLE — needs FanGraphs re-scrape** |
| **First-batter K rate** | Statcast play-by-play, first PA of outing | derivable from raw statcast 2015-26 (have all PA-level fields) | YES (expensive) | YES (expensive) | **AVAILABLE — requires new derivation step, moderate cost** |

---

## 3. Cohort sizing

### 3a. Eligible RP-seasons by year (G_relief ≥ 20 AND TBF ≥ 50)

| Year | Eligible RP-seasons |
|---|---|
| 2015 | (~277 estimated from statcast pilot; not currently in `relievers_multiyr`) |
| 2016 | (~280 est from statcast; not in cache) |
| 2017 | (~280 est from statcast; not in cache) |
| 2018 | 278 |
| 2019 | 281 |
| 2020 | 132 (COVID-short) |
| 2021 | 299 |
| 2022 | 282 |
| 2023 | 255 |
| 2024 | 261 |
| 2025 | 277 |
| 2026 | 126 (partial — season in progress, 2026-05-28) |
| **Total 2018-26** | **2,191** |
| **Total 2015-26 (with statcast backfill)** | **~3,000+** |

For comparison, SP archetype master is 2,159 SP-years 2015-2026 — so **RP cohort is ~larger** than SP if we restrict to 2018+ (2,191), and **clearly larger** if we backfill 2015-17 via statcast (~3,000+).

### 3b. Joinability to all 6 rate-skill sub-domains

For the build-script-ready set (no new derivations), eligible RPs joinable to **all** of {SWING_MISS, CALLED_STRIKE, WALK_AVOID, velo_rating, IP/G, SV/HLD, role}:

- 2018-26: **100% of 2,191 eligible** (all stats are in `relievers_multiyr` directly).
- 2015-17: **0% currently** (would require new statcast-derived RP roll-up — feasible but new work).

For the **full** 6-domain set including DAMAGE_SUPP and GB_TENDENCY:

- Without new work — **FG join only**: 2020-26 RP-seasons with FG barrel/HH/GB ≈ 1,408 (74-100% × per-year eligible). 2018-19 and 2015-17 = **0%**.
- With statcast-derived backfill (new build step): **~3,000+ RP-seasons 2015-2026 at ~100%**.

### 3c. Median PA/TBF/IP per RP-season

| Metric | Median |
|---|---|
| TBF | 198 |
| IP | 47.3 |
| G | 45 |
| IP / G | 0.99 (i.e. most RPs throw ~1 IP per outing) |

For context the SP archetype build has `GS_FLOOR_RATED = 6` (~70 TBF). 50 TBF is the K%-stabilization equivalent for RPs; 198 TBF median means the **typical eligible RP-season has 2.8× the K%-stability floor**, so stat ratings are well-stabilized.

### 3d. Consecutive-season distribution (longitudinal modeling capacity)

Among 2,191 eligible RP-seasons:
- Pitchers with 1 eligible season: 349
- Pitchers with 2 seasons: 198
- Pitchers with 3+ seasons: 320
- Pitchers with 5+ seasons: 134
- **T+1 consecutive pairs (origin-year has a year+1 follow-up):** **1,104**
- **T+2 consecutive triplets:** **579**

For comparison the SP archetype build calibrated stickiness and decline base rates off ~1,353 SP-years; with **1,104 T+1 RP pairs and 579 T+2 triplets, RP cohort is comparable**.

### 3e. Age join

- `sp_age_career.csv` covers 94.0% of eligible RP-seasons (2,088 / 2,221).
- `milb_pitcher_ages.csv` provides `birthDate` for 866 of 877 RP pitchers as fallback.
- **Effective age coverage: ~100%** (no realistic gap).

---

## 4. Biographical / age join — confirmed

`data/outputs/sp_age_career.csv`:
- Cols: `pitcher, year, age, age_residual_28, career_year`
- 8,792 rows, 2015-2026, 2,625 unique pitchers
- Despite the file name (`sp_*`), it covers RPs (94% join rate to RP cohort).
- For the 6% gap, `milb_pitcher_ages.csv` provides `birthDate` for 866 of 877 RP pitchers.

Age tier definition for RPs may need its own tuning (SPs use ≤26 PRE_PEAK, 27-31 PEAK, 32+ POST_PEAK; RP peak-age literature suggests slightly later peak / shallower decline — but that's a separate empirical question for the build).

---

## 5. Honest gaps — what's truly missing

| Gap | Severity | Workaround |
|---|---|---|
| **DAMAGE_SUPP / GB_TENDENCY raw inputs not in `relievers_multiyr`** | MEDIUM | Add a new build step that derives `barrel_pct, hard_hit_pct, gb_pct, xwoba_contact` per RP-season from raw statcast parquet (2015-2026, all years). One-time addition; pattern parallels `build_sp_multiyr.py`. Or use FG file as a faster but year-incomplete fallback. |
| **2015-2017 RP-season roll-up does not exist in any cache** | MEDIUM | Build it from statcast parquet (pattern: aggregate pitch-level rows where pitcher ≠ first-inning pitcher of the same game). Pilot confirmed feasible: 2015 yields 277 RP-eligible pitchers with 57k PAs. Without this, RP archetype is 2018-2026 (still 2,191 seasons). |
| **gmLI (game leverage index per outing)** | HIGH (impact on archetype labeling for HIGH-LEVERAGE vs LOW-LEVERAGE) | **No cached source.** Requires fresh FanGraphs scrape (URL pattern: `/leaders/major-league?lg=all&pos=all&type=18&pageitems=2000`). New ETL needed. |
| **IR / IS (inherited runner stranded)** | MEDIUM (matters for SETUP / FIREMAN sub-types) | **No cached source.** Same FanGraphs scrape would pick this up. |
| **`pitcher_splits.csv` only covers 2022-2026 and ~55% of RP-seasons** | LOW for archetype (could become a sub-type qualifier, not a primary axis) | Live with the partial coverage; flag splits-based sub-types as "available 2022+" only. |
| **`prior_career_fp_per_start` is SP-only** | LOW | Compute parallel `prior_career_fp_per_g` from `relievers_multiyr` directly — trivial group-by. |
| **First-batter K rate / leverage by inning** | LOW (not in original SP build either) | Derivable from statcast PA-level data; defer to v2. |
| **FG 2026 join failing in current snapshot (0% cov)** | LOW-MEDIUM (only affects in-progress year) | Investigate `mlb_id` mismatch; the FG 2026 file does have 240 RP-ish rows. Likely a stale-id problem. |

---

## 6. Summary of what an RP archetype build can ship today

### MVP scope ("ship now, no new scrapes")
- **Years:** 2018-2026 (lose the 2015-17 history vs SP archetype, but gain 32 more RP-years than SP for 2018+).
- **Cohort:** 2,191 RP-seasons (vs SP's 2,159).
- **Sub-domains directly computable:** SWING_MISS, CALLED_STRIKE, WALK_AVOID, velo_rating, IP/G, SV/HLD/GF, role tag, role-persistence YoY, age tier.
- **Sub-domains requiring one new derivation step** (statcast-based, ~SP-pattern):  DAMAGE_SUPP (xwoba_contact, barrel), GB_TENDENCY (gb_pct).
- **T+1 pairs:** 1,104. **T+2 triplets:** 579. **Age cov:** ~100%.

### Mid scope ("add statcast-based RP roll-up for 2015-2017")
- Years: 2015-2026, ~3,000+ RP-seasons.
- Pattern: extend `build_relievers_multiyr.py` to backfill 2015-2017 (or write a one-shot `_build_rp_multiyr_2015_2017.py` aggregator). Statcast has all the inputs; just need RP-PA identification logic (pilot in section 1k).

### Full scope ("match the SP build's depth + RP-native features")
- Requires new FanGraphs scrape for `gmLI`, `IR`, `IS`, `WPA` (RP-specific signals not in any current cache).
- This is what would let RP archetype labels distinguish HIGH-LEVERAGE-FIREMAN vs SETUP-BY-USAGE vs LOW-LEVERAGE-MOPUP cleanly. Without it we're labeling by SV/HLD/GF ratios only.

---

## 7. Specific filenames touched

Read-only data sources for the RP build (in priority order):

1. `data/research/xfp_cache/relievers_multiyr_2018_2026.csv` — primary player-year (2,221 rows, 51 cols)
2. `data/research/xfp_cache/rolling_relievers_2018_2026.csv` — adds role_lag1, SV/HLD per game, closer context (11,952 rows, 68 cols)
3. `data/research/xfp_cache/statcast_{2015..2026}.parquet` — for DAMAGE_SUPP/GB_TENDENCY derivation, and for 2015-17 backfill
4. `data/outputs/fangraphs_pitchers_{2020..2026}.csv` — optional faster path for barrel/HH/GB (2020-26 only)
5. `data/outputs/sp_age_career.csv` — age + career_year join (94% cov)
6. `data/research/xfp_cache/milb_pitcher_ages.csv` — birthDate fallback (covers 99% of gap)
7. `data/research/xfp_cache/sp_pitch_type_pfxz_2015_2026.csv` — secondary movement tag
8. `data/research/xfp_cache/pitcher_splits.csv` — L/R splits, 2022+ only, partial coverage
9. `data/research/xfp_cache/pitcher_primary_team_2018_2026.csv` — team context
10. `data/outputs/xfp_rprs2_projections.csv` — validated ROS RP projection for in-progress 2026 attachment
11. `data/research/closer_persistence.csv` — sanity flag for closer-of-record per team-year

Outputs to mirror SP build:
- `data/research/rp_ratings_master.csv` (the SP `sp_ratings_master.csv` analog)
- `data/research/rp_archetype_career_panel.parquet`
- `data/research/rp_archetype_definitions.json` (RP-specific 27-cell or simpler matrix)
- `data/research/rp_archetype_stickiness.json`
- `data/research/rp_decline_baselines.json`
- `data/research/rp_boundary_validation.json`

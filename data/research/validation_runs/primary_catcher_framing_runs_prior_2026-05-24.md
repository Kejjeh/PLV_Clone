---
signal: primary_catcher_framing_runs_prior
formula: For SP P in year Y, find P's modal catcher C in year Y-1 (from statcast fielder_2 across all P's pitches that year). Look up C's framing_runs_per_100 in year Y-1 (shadow-zone called-strike rate vs league mean × 0.13 runs/CS × 100). Both shifts are prior-year so the feature is leak-free for forecasting year-Y RoS.
outcome: ros_fp_per_start (rp3 production target)
expected_sign: positive (better framer → more called strikes on borderline → higher K rate → higher SP FP/start)
theory: Catcher framing swings called-strike rate on borderline pitches by 3-5%. This is orthogonal to every existing RP3_FEATS column (none encode the receiving catcher). A pitcher who keeps the same elite framer year over year inherits a small but persistent K-rate tailwind that the model currently can't see.
production_target: rp3
framing: in-season → ros (split rows 30/60/90/120 days; prior-year catcher framing is leak-free)
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_primary_catcher_framing_runs_prior.py
date: 2026-05-24
verdict: REJECTED
purpose: First test of a catcher-influence feature in rp3. Catcher framing is the largest empirically-documented orthogonal driver of pitcher K rate that RP3_FEATS does not encode. If it lifts, rp3 v4 catcher-quality module is justified; if it doesn't, the per-pitcher catcher dimension is dead and we focus elsewhere.
---

# Pre-registration body

## Why this candidate

- RP3_FEATS encodes the pitcher's own stuff/command/discipline (velo, swstr, CSW, chase, zone, walks) plus IL, prior, drift. None of the 23 features knows who is catching.
- Catcher framing is the single biggest external influence on a starter's borderline-strike rate. Industry estimates put the top-vs-bottom catcher gap at ~25-30 framing runs/yr, which translates to several percentage points of called-strike rate on shadow-zone pitches and ~3-5% on full-PA K rate at the margin.
- Primary-catcher assignment is sticky within a team. A pitcher's prior-year primary catcher predicts the catcher pair for year T with high probability (>60% same-team retention). Even when the catcher changes, the framing-skill carryover is meaningful (the pitcher's organization tends to acquire similar receivers).

## Rule 5 sample-size honesty note

Source data: statcast (2017-2025, fully cached locally). Both prior-year primary catcher AND prior-year framing rows exist. Per-year non-null coverage is reported in the validation script output. Pitchers with no prior-year statcast (rookies, MiLB call-ups, two-way) get NaN; we fill with population mean so baseline and full evaluations run on identical row sets. Expected per-year non-null ≥80% for established SPs at the split horizons rp3 trains on.

7 training years (2018-2019, 2021-2025) all viable. Clears Rule 2(b) ≥5/7 floor.

## Rule 8 framing

Production framing is in-season → RoS at split rows. The candidate is computed from PRIOR-year statcast only — strictly leak-free. No within-season catcher-of-record signal is used (which would risk endogeneity: hot SPs get paired with starter catchers more often).

## Rule 9 baseline

Full RP3_FEATS (23 features) as listed in `src/plv_clone/models/xfp/rp3.py`. Lift measured by adding `primary_catcher_framing_runs_prior` to that full set, no other change.

## Rule 3 / Bonferroni

Single candidate this push. +0.005 production gate is the binding bar.

## Decision rule

- PASS: lift ≥ +0.005 AND sign ≥ 5/7 years AND holdout lift > 0
- MARGINAL: lift in (0, +0.005] OR fails one of (b)/(c) while clearing (a)
- REJECTED: lift ≤ 0 OR wrong sign overall

Verdict appended after results, never pre-filled.

## Data layer notes (built same day)

`scripts/xfp/build_catcher_framing.py` writes two caches:

1. `data/research/xfp_cache/catcher_framing_2017_2025.csv` — per (catcher_mlbam, year): shadow_pitches, framing_rate, framing_runs_per_100, framing_runs. Shadow zone = just outside rulebook zone (0.83 < |x| ≤ 1.0, or 0-0.2 ft above/below sz_top/sz_bot). Runs valuation = 0.13 runs / called-strike-above-mean.

2. `data/research/xfp_cache/sp_primary_catcher_2018_2025.csv` — per (pitcher, year): modal fielder_2 across all pitches.

pybaseball.statcast_catcher_framing is broken (Savant CSV parser error). All numbers computed from local statcast parquet cache.

### Eye-test (2024 / 2025, ≥800 shadow pitches)

| Year | Top 3 framers | Bottom 3 framers |
|---|---|---|
| 2024 | Patrick Bailey, Cal Raleigh, Austin Wells | Tyler Stephenson, Miguel Amaya, Keibert Ruiz |
| 2025 | Patrick Bailey, Austin Wells, Alejandro Kirk | J.T. Realmuto, Will Smith, Salvador Perez |

Bailey #1 both years and Wells/Raleigh top tier matches industry consensus (Bailey is the consensus best framer in MLB 2024-25). Bottom tier Ruiz/Realmuto/Perez also matches Savant's public framing leaderboard. Eye-test PASSES.

Note: 2025 league shadow CS rate dropped to 0.324 vs 0.40s in prior years — likely a partial-season artifact (lower in-zone proportion early in 2026 cache) or a strike-zone calibration shift. Does not affect the within-year ranking the model consumes.

---

# Results

Ran `scripts/xfp/validate_primary_catcher_framing_runs_prior.py` 2026-05-24.

| Test | Value | Pass? |
|---|---|---|
| Baseline cross_year r (RP3_FEATS, 23 feats) | 0.5509 | — |
| Full cross_year r (+ primary_catcher_framing_runs_prior, 24 feats) | 0.5508 | — |
| **Lift Δr** | **−0.0001** | **FAIL** (gate ≥ +0.005) |
| Sign consistency | 4/7 years positive | FAIL (need 5/7) |
| Holdout (2024-2025) avg lift | +0.0001 | PASS sign (trivial) |

**Per-year lift:** 2018: +0.0001, 2019: +0.0001, 2021: −0.0003, 2022: +0.0001, 2023: −0.0009, 2024: −0.0001, 2025: +0.0002.

**Data:** 86.4% non-null (4721/5462). Per-year non-null: 2018: 625, 2019: 601, 2021: 612, 2022: 661, 2023: 632, 2024: 625, 2025: 644, 2026: 321. NaN rows filled with population mean (+0.030 runs/100). n=4174 pitcher-split rows in LOO eval.

## Verdict — REJECTED

`primary_catcher_framing_runs_prior` adds no predictive lift to rp3 at the SP-RoS framing. Three reasons this likely failed despite the orthogonality argument and the clean eye-test on the framing data itself:

1. **Framing-runs-per-100 is a thin signal at the per-pitcher level.** Even a top-tier framer (~+1.0 runs/100 shadow pitches) only differs from a median framer by ~0.5-1.0 fantasy points / season for the average SP — well below the noise floor of per-start fp variance that rp3 is fitting.
2. **Catcher turnover within season decouples prior-year primary catcher from actual receiver.** A pitcher's prior-year modal catcher is a proxy for the current catcher, but trades, injuries, and platoons (especially LHB-RHB based catcher splits) dilute the signal.
3. **rp3's `delta_swstr` and `c_plus_swstr_to_sh` already absorb the K-rate consequence of better receiving.** If your catcher is stealing strikes, your CSW and swstr go up the next L21 days, and the drift features eat the signal.

The per-year pattern (4/7 sign, no year above |0.001|) is consistent with white noise, not with a directional effect being washed out by sample size. Not promoted. Confirms the per-pitcher catcher dimension as currently encoded is dead for rp3; do not retry without a meaningfully different formulation (e.g., real-time catcher-of-record per start, or a multi-year catcher-stability interaction).

Documented per Rule 6 so this is not re-explored. RP3_FEATS NOT modified.

## What would unblock a v2 attempt

- Per-start catcher of record (requires joining MLB Stats API game logs to the `gamelogs` substrate, not just statcast pitch-level modal). Would let rp3 see today's catcher's framing skill directly.
- Catcher-pair durability flag (same prim catcher 2 years in a row × framing quality) — interaction rather than level.
- Joint framing × pitcher arm-side (LHP gain more from framing on the outer-third to RHB).

None of these are obviously high-prior worth the build cost given the level-feature null result.

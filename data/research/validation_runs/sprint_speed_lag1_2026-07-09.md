---
signal: sprint_speed_lag1 (primary cell) + sprint_speed_delta (secondary cell, Bonferroni 2)
formula: "lag1: Savant season-aggregate sprint speed (ft/s, competitive runs) for year T-1, joined to each rh3 rolling row (batter, year=T) by MLBAM batter id from data/research/xfp_cache/sprint_speed_{T-1}.csv; rows with no T-1 reading filled with the mean of merged non-null lag1 values over TRAIN_YEARS rows. delta: sprint_speed(T-1) - sprint_speed(T-2); rows missing either year filled 0.0 (no-change neutral)."
outcome: rh3 cross_year_eval Δr on ros_full_fp_per_pa target (matches rh3 production LOO)
expected_sign: + (both cells)
theory: Sprint speed is a fast-stabilizing PHYSICAL prior orthogonal to the outcome-rate axes in RH3_FEATS — SB is worth a full FP in BrownU scoring (R+TB+RBI+BB+HBP+SB−K) and speed also feeds R (baserunning advancement) and BABIP (infield hits), while sb_per_pa_to_sh is a heavily-shrunk (k=300) OUTCOME rate that lags true speed for low-PA and role-changed players.
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_sprint_speed_lag1.py
date: 2026-07-09
verdict: REJECTED (both cells; Rule-4 component mechanism PASS — diagnostic tie-breaker only, do NOT promote)
purpose: Recon error-analysis (2026-07) found the hitter in-season layer adds ~0 forward rate signal over the Marcel prior — orthogonal physical signals are the identified gap. Sprint speed data has sat unused on disk since 2015.
---

# Pre-registration: `sprint_speed_lag1` (+ `sprint_speed_delta`) — rh3 candidates

**Date:** 2026-07-09
**Production target:** `rh3`
**Baseline:** full `RH3_FEATS` (21 features, includes `sb_per_pa_to_sh`,
`prior_fp_per_pa`, `career_stage`, `ros_opp_sp_xwoba_weighted`). Rule 9
satisfied — baseline is the current production feature set.
**Cells:** 2 (lag1 primary, delta secondary) → **Bonferroni 2** noted per
Rule 3. The Δr gate is effect-size based (unchanged at +0.005 per cell);
Bonferroni applies to any p-value-style claims in the component test
(α = 0.025 per cell).

## Step 2.5 data-coverage pre-check (run BEFORE this prereg was locked)

Sprint speed CSVs exist 2015-2026 (one per year, ~460-590 batters each,
columns `batter, sprint_speed`, zero duplicate ids). lag1 therefore covers
outcome years 2016+ → **all 7 TRAIN_YEARS pass**. Join rates on
eval-eligible rolling rows (pa_to ≥ 50, ros_pa ≥ 100, year ≠ 2020):

| year | rows | lag1 join | lag2 join |
|---|---|---|---|
| 2018 | 5,154 | 91.9% | 82.6% |
| 2019 | 5,387 | 92.2% | 79.4% |
| 2021 | 5,258 | 87.5% | 87.2% |
| 2022 | 5,055 | 90.4% | 77.1% |
| 2023 | 5,312 | 91.2% | 76.0% |
| 2024 | 5,271 | 94.2% | 78.7% |
| 2025 | 5,134 | 91.8% | 81.6% |
| 2026 | 1,474 | 94.0% | 81.5% |

All years ≥ 87% for lag1 — well above the 60% bar, so the primary cell
uses **plain mean-fill, no missing-indicator column**. Missing lag1 rows
are mostly rookies/short-stint players; the TRAIN_YEARS population mean
(~27 ft/s) is the neutral prior for them.

## Leakage note

Savant sprint speed is a SEASON-LEVEL aggregate. Using year T-1 for
outcome year T is fully leakage-safe at every split_day (the value is
frozen before the season starts). No within-season sprint speed is used.

## Hypothesis

Faster players out-earn their rate-stat profile in BrownU FP/PA (SB = +1
FP each; extra R from baserunning; infield-hit BABIP). `sb_per_pa_to_sh`
is shrunk with k=300 PA — at early split_days it is mostly population
mean, while prior-year sprint speed is a near-noiseless physical
measurement. Expected redundancy risk: `sb_per_pa_to_sh` +
`prior_fp_per_pa` already carry realized SB value for established
regulars, so the composite lift may be small even if the mechanism is
real.

## Test plan (in order)

1. **Rule 4 component test FIRST** (cheap, mechanism-level): partial
   correlation of `sprint_speed_lag1` with **RoS SB per PA**
   (`(season_sb − sb_to) / ros_pa`, clipped ≥ 0) controlling for
   `sb_per_pa_to_sh` + `prior_fp_per_pa`, on eval-eligible TRAIN_YEARS
   rows. Pre-registered expectation: partial r > 0 with p < 0.025
   (Bonferroni-2). This validates the mechanism independent of composite
   FP lift.
2. **Rule 9 integration test** (headline): `rh3.cross_year_eval` LOO of
   RH3_FEATS + candidate vs full RH3_FEATS, via
   `_validate_rh3_v3_helper.run_candidate_eval` (production-parity prep).
   Note: the helper unpacks `cross_year_eval` as a 2-tuple; the current
   rh3 returns 3 (detail frame added 2026-07-04) — the validation script
   shims the module attribute to a 2-tuple wrapper, changing no shared
   files.
3. Rule 8 convergence per split_day, Rule 2(b) per-year signs, coef sign
   check — all emitted by the shared helper.

## Decision rule (per cell)

- **PASS** if Δr ≥ +0.005 AND per-year positives ≥ 5/7 AND holdout
  2024-2025 positive AND coef > 0.
- **MARGINAL** if 0.0 < Δr < +0.005 OR sign/holdout fail.
- **REJECTED** if Δr ≤ 0.
- If component test passes but composite fails → note "diagnostic
  tie-breaker candidate, do NOT promote" per Rule 4.

`RH3_FEATS` is NOT modified regardless of verdict.

---

# RESULTS (appended after the run — design above unchanged)

**Run:** 2026-07-09, `scripts/xfp/validate_sprint_speed_lag1.py`, exit 0.
Baseline = full 21-feature RH3_FEATS, production-parity prep via
`_validate_rh3_v3_helper` (with a script-local 2-tuple shim around
`rh3.cross_year_eval`'s new 3-tuple return; no shared file modified).

## Rule 4 component test (mechanism) — PASS

Partial r of raw (non-filled) `sprint_speed_lag1` with RoS SB/PA,
controlling for `sb_per_pa_to_sh` + `prior_fp_per_pa`, on n = 33,396
eval-eligible TRAIN_YEARS rows:

- **partial r = +0.4990, p ≈ 0** (bar was r > 0, p < 0.025 Bonferroni-2)

The mechanism is emphatically real: prior-year sprint speed carries large
independent information about future SB rate that the shrunk SB-rate
feature does not. It is the composite FP/PA target where it adds nothing.

## Rule 9 integration — both cells REJECTED

| cell | baseline r | +cand r | Δr | per-year + | holdout 24-25 | coef |
|---|---|---|---|---|---|---|
| sprint_speed_lag1 | 0.6338 | 0.6334 | **−0.0004** | 5/7 (all ≤ +0.0010) | **0/2** (−0.0016, −0.0008) | +0.0022 OK |
| sprint_speed_delta | 0.6338 | 0.6333 | **−0.0005** | 0/7 | 0/2 | −0.0001 WRONG SIGN |

Per-year Δr (lag1): 2018 +0.0005, 2019 +0.0006, 2021 +0.0005,
2022 +0.0004, 2023 +0.0010, 2024 −0.0016, 2025 −0.0008.

Rule 8 convergence: lag1 Δr is ≤ 0 at EVERY split_day (−0.0001 @sd44 →
−0.0020 @sd142, drifting more negative late-season as `sb_per_pa_to_sh`
un-shrinks with accumulating PA — exactly the redundancy signature).
Delta cell negative at every split_day too.

## Interpretation

The pre-acknowledged redundancy risk materialized: the Ridge already
recovers SB fantasy value through `sb_per_pa_to_sh` + `prior_fp_per_pa`
(the Marcel prior embeds each player's realized SB production), and SB is
a small share of total FP/PA variance. A feature can be a strong
mechanism-level predictor of ONE scoring component and still add zero to
the composite when the baseline spans that component's realized level.

**Per Rule 4: diagnostic tie-breaker candidate, do NOT promote.**
Legitimate non-FEATS uses: as a context column when arbitrating between
two hitters with similar rh3 whose SB-rate samples are thin (< ~150 PA,
where the k=300 shrinkage still dominates), or in rookie/short-sample
displays. Never a number-mover (Rule 13).

`RH3_FEATS` NOT modified. Closes the sprint-speed line of inquiry for the
composite rh3 target; a re-attempt would need a different framing (e.g. a
dedicated SB-component sub-model feeding a decision layer, not the
FP/PA ranker).

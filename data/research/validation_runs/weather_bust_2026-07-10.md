---
signal: weather_bust (3 cells, Bonferroni 3 — temp_f / wind_out_component / temp_x_park)
formula: see per-cell formulas below (locked)
outcome: per-start bust = (fp < 5.0) on the sp_floor per-start panel (_boom_stack_per_start_panel_cache.parquet)
expected_sign: + (all three cells, on bust log-odds)
theory: game-environment (heat / wind blowing out / heat at HR-friendly parks) inflates HR-driven blowups, fattening the SP bust tail — orthogonal to the pitcher-history features sp_floor uses
production_target: sp_floor (decision layer) — NOT rp3
framing: per-start (game-time weather known pre-first-pitch; see Rule 8 note)
holdout_years: [2023, 2024, 2025]  (sp_floor's own TEST split)
training_years: [2018, 2019, 2021, 2022]  (sp_floor's own TRAIN split)
validation_script: scripts/xfp/validate_weather_bust.py
date: 2026-07-10
verdict: REJECTED (all 3 cells; temp_f is a sub-gate near-miss +0.0042)
purpose: 19,795 games of historical game-time weather sit unused in data/research/xfp_cache/game_weather.csv; a clean pass/reject on the bust-tail framing closes the "should the floor model see weather" question. Prior registry entry game_weather_temperature (2026-06-13) found temp is ~0.2% of MEAN FP variance (RESEARCH-ONLY) — this run tests the different claim that weather moves the BUST TAIL (per-start AUC), which the mean study did not test.
---

# Pre-registration: game-time weather → SP per-start bust probability

Locked BEFORE any model fitting. Step 2.5 data-coverage results below were
computed first (allowed — coverage/join inspection only, no outcome contact).

## Substrate (exact replication of production sp_floor)

- Panel: `data/research/_boom_stack_per_start_panel_cache.parquet` via a verbatim
  copy of `sp_floor_model.build_panel()` (same filters: `n_prior_starts>=4`,
  `cum_PA>=40`, dropna on FEATS+bust).
- Baseline features (FULL, Rule 9): `prior_k_pct, prior_bb_pct, lineup_xfp,
  days_rest, n_prior_starts`.
- Model: `StandardScaler` + `LogisticRegression(max_iter=1000)`, train on
  TRAIN years, evaluate on TEST years — byte-for-byte the production recipe.
- Join key: `game_pk` (mlbam game key) only. No name joins.

## Step 2.5 data-coverage pre-check (computed 2026-07-10, pre-fit)

`data/research/xfp_cache/game_weather.csv` actual schema: `game_pk, game_date,
venue, condition, temp_f, wind, dome` — **no humidity column; `wind` is
"N mph, DIRECTION" with MLB field-relative direction** ("Out To CF", "In From
LF", "L To R", "None", ...), NOT compass degrees.

| year | weather rows | temp NA rate | panel starts | join rate (temp present) |
|---|---|---|---|---|
| 2018 | 2,487 | 0.04% | 4,550 | 100.0% |
| 2019 | 2,472 | 0.08% | 4,449 | 100.0% |
| 2021 | 2,512 | 0.04% | 4,438 | 100.0% |
| 2022 | 2,479 | 0.00% | 4,560 | 100.0% |
| 2023 | 2,476 | 0.00% | 4,517 | 100.0% |
| 2024 | 2,469 | 0.04% | 4,599 | 100.0% |
| 2025 | 2,462 | 0.00% | 4,600 | 100.0% |

(2026 rows are 76% temp-missing but the panel ends 2025 — irrelevant.)

**Gate: >= 5 usable years and >= 60% join. Result: 7/7 years, 100% join → PASS,
proceed.**

## Documented deviations from the task spec (data-driven, locked pre-fit)

1. **No stadium-orientation CSV is built.** The spec assumed compass
   `wind_direction`; the file carries MLB's field-relative direction, which is
   already expressed relative to the home-plate→CF axis. A bearings table would
   be a no-op. Cell 2 maps the direction string directly (table below).
2. **No humidity cell** — column does not exist in the file. Not substituted.
3. Park factor source `data/research/xfp_cache/park_factors_savant.csv` is keyed
   by `key_year × venue_name` with `index_hr`; where both 1-yr and 3-yr rolling
   rows exist for a key_year, the **max `n_years_rolling`** row is used
   (3-yr preferred; 2017 only has 1-yr).

## Candidate cells (exactly 3, Bonferroni N=3)

Each cell = baseline 5 features + the ONE named column, refit with the same
scaler/logit recipe.

### Cell 1 — `temp_f`
Game-time temperature (°F) as recorded (dome/roof-closed games keep their
recorded indoor temp). Missing (<0.1%) → TRAIN-set median. Expected sign: **+**
(hotter → more carry → more blowups).

### Cell 2 — `wind_out_component`
`wind_speed_mph × dir_factor`, parsed from the `wind` string:

| direction | dir_factor |
|---|---|
| Out To CF | +1.0 |
| Out To LF / Out To RF | +0.7071 |
| In From CF | −1.0 |
| In From LF / In From RF | −0.7071 |
| L To R / R To L / None / Varies / other | 0.0 |

`dome == True` OR `condition in {Dome, Roof Closed}` → forced 0.0. Missing wind
string → 0.0. Expected sign: **+** (wind out → HR help → busts).

### Cell 3 — `temp_x_park`
`(temp_f − 70) × (index_hr_lag1 − 100) / 100`, where `index_hr_lag1` is the
Savant park HR factor for the game's venue at `key_year = game_year − 1`
(**T−1 lagged** — no same-year outcome contact). Venue joined weather→park via
`venue_name` with a fixed alias map (AT&T→Oracle, Guaranteed Rate→Rate Field,
Minute Maid→Daikin, SunTrust→Truist, Marlins→loanDepot, Miller→American Family,
Safeco→T-Mobile, Dodger Stadium→UNIQLO Field at Dodger Stadium). Special-event
venues (~60 games: London, Field of Dreams, Rickwood, Tokyo, Monterrey, etc.)
→ neutral `index_hr_lag1 = 100` (term = 0 in the park dimension). Centered
product so it is 0 at a neutral park or neutral temp. Expected sign: **+**
(heat amplifies HR parks). Interpretation caveat pre-acknowledged: added as a
single column without separate main effects, per spec.

## Metrics and gates (locked)

Primary metric: **TEST-set ΔAUC** (augmented − baseline), paired bootstrap over
TEST rows, **1000 draws**, percentile CI at **98.33%** (Bonferroni 3 on α=0.05).

A cell **PASSES** only if ALL of:
1. Bootstrap 98.33% CI on ΔAUC excludes 0;
2. Point ΔAUC ≥ **+0.005**;
3. Calibration preserved: augmented model's TEST predicted-prob quintiles have
   actual bust rates monotone non-decreasing Q1→Q5 (tolerance 0.5pp inversion).

Also reported (non-gating): per-TEST-year ΔAUC signs (2023/2024/2025);
tail-lift = actual bust rate in the top decile of the weather-risk shift
(`p_aug − p_base`) vs the bottom decile; augmented coefficient sign vs expected.

## Rule 8 honesty note (train/predict information mismatch, pre-acknowledged)

Weather here is the ACTUAL game-time reading (historical). At PREDICTION time
the model would only have a FORECAST. This validation therefore licenses the
signal's EXISTENCE only; the realized-weather ΔAUC is an UPPER BOUND on
production lift. Any production integration requires a forecast source
(e.g. Open-Meteo hourly forecast at first pitch) and ideally a
forecast-vs-realized error study before the term goes live.

## Outcome space

PASS (per cell) / REJECTED (per cell). If any cell passes: sp_floor_model.py is
NOT modified in this run — an integration recipe (incl. the forecast-source
requirement) is written into the results section; owner integration is a
separate step. A 3-cell REJECTED closes the weather file question for the
floor model permanently.

---

# RESULTS (appended 2026-07-10 after run — design above unchanged)

Run: `PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/validate_weather_bust.py`
Panel after join: train 13,682 starts (2018/19/21/22), test 10,435 (2023-25);
bust base rate 26.3% / 27.1%. Weather join on the FILTERED panel: 100.0% every
year (355 duplicate game_pk rows in the weather file — rescheduled games listed
under two dates with identical readings — deduped keep-last; documented, does
not touch the design).

Baseline (full 5-feat production recipe) TEST AUC = **0.6006**, quintiles
17.7 → 37.6% monotone — reproduces the registered sp_floor result (0.601).

| cell | ΔAUC | 98.33% CI | CI excl 0 | coef (std) | cal mono | per-year ΔAUC (23/24/25) | tail-lift top/bottom decile | verdict |
|---|---|---|---|---|---|---|---|---|
| temp_f | **+0.0042** | [+0.0000, +0.0086] | yes (barely) | +0.126 (+, as expected) | yes | +0.0067 / +0.0053 / +0.0011 | 33.1% / 27.2% | **REJECTED** (fails ΔAUC ≥ +0.005) |
| wind_out_component | −0.0001 | [−0.0004, +0.0003] | no | +0.010 (+) | yes | +0.0002 / −0.0005 / −0.0000 | 29.1% / 30.7% | **REJECTED** |
| temp_x_park | −0.0007 | [−0.0020, +0.0005] | no | +0.038 (+) | yes | +0.0009 / −0.0020 / −0.0013 | 31.0% / 31.5% | **REJECTED** |

Joint all-3 (non-gating): TEST AUC 0.6043, ΔAUC +0.0037 — i.e. the whole
weather file is worth less than temp alone plus noise.

## Interpretation

- **Temperature is the only real weather signal in the bust tail, and it is
  sub-gate.** Direction correct (hot → bust, coef +0.126/SD), calibration
  preserved, top-decile temp-risk starts bust 33.1% vs 27.2% bottom-decile
  (~+6pp tail separation) — but the pooled ΔAUC +0.0042 misses the +0.005
  gate, the Bonferroni CI lower bound sits at ~0, and the effect decays across
  test years (2023 +0.0067 → 2025 +0.0011). Consistent with the 2026-06-13
  mean-FP study (~0.2% of variance): weather is real, tiny, and mostly spanned
  once command + opponent are in the model.
- **Wind is a decisive null** (ΔAUC −0.0001, CI tight around 0) despite the
  clean field-relative out-component construction. Plausibly because the panel
  outcome is pitcher FP (K/IP-heavy), park HR context is already implicit in
  lineup_xfp/opponent, and wind-out days are also strikeout-neutral.
- **Temp × park-HR interaction adds nothing over nothing** — negative point
  estimate; the heat-amplifies-HR-parks theory does not show up in the tail.
- Rule 8 reminder: these are REALIZED-weather upper bounds. A forecast-based
  production feature would only be weaker. Since even the upper bound fails
  the gate, the forecast-pipeline question is moot.

## Disposition

**Closes the "should sp_floor see game weather" question: NO.** Do not modify
`scripts/xfp/sp_floor_model.py`. Do not build a weather-forecast ingestion
pipeline for the floor model. The one defensible residual use is unchanged
from the 2026-06-13 memo: daily streaming COLOR only (e.g. a pregame note when
temp ≥ 85°F, worth ~1 FP of tail risk) — display/context (Rule 13), never a
ranker or bust-prob input. Re-attempt only with a meaningfully different
framing (e.g. HR-allowed-specific outcome instead of FP-bust, or forecast-error
-aware live layer), not with these three cells.

Artifacts: validation script `scripts/xfp/validate_weather_bust.py`. No
stadium-bearings CSV was needed (deviation #1 above). No production files
touched.

---
signal: rp_leverage_lag1 (3-cell sweep — pli_lag1, gmli_lag1, sd_md_per_g_lag1)
formula: |
  All three are PRIOR-year (season-level lag1) values joined to the rolling
  relievers panel on (pitcher mlbam, year-1) from
  data/research/xfp_cache/fangraphs_rp_leverage_2018_2026.csv:
    cell 1: pli_lag1        = prior-year pLI  (avg leverage index across all batters faced)
    cell 2: gmli_lag1       = prior-year gmLI (avg leverage index when ENTERING the game)
    cell 3: sd_md_per_g_lag1 = (shutdowns - meltdowns) / g, prior year
  Missing lag1 (rookies / no qualifying prior RP season / all of 2021) ->
  impute the population mean of the observed lag values (global scalar,
  matching the production rolling-builder pattern, e.g. g_lag1 sentinel
  45.4249). NO new has-prior indicator is added — the existing
  role_closer/setup/middle_lag1 dummies already encode has-prior structure.
outcome: fp_year_total (rprs2 TARGET), LOO cross-year per src/plv_clone/models/xfp/rprs2.py cross_year_eval
expected_sign: + (all three cells)
theory: >
  rprs2's forward rank skill lives in the SV/HLD role component; leverage
  indices are the managerial-trust signal UPSTREAM of role. gmLI especially
  encodes when the manager deploys the arm — trust that trailing SV/HLD
  counts lag. SD-MD per game is a leverage-outcome quality rate that saves
  and holds only partially capture.
production_target: rprs2
framing: full-year (rprs2 target is fp_year_total; xfp_ros derived downstream)
holdout_years: [2024, 2025]
training_years: [2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_rp_leverage_lag1.py (harness scripts/xfp/_rprs2_validation_harness.py)
date: 2026-07-09
verdict: REJECTED (all 3 cells)
purpose: >
  Recon error analysis (2026-07) showed rprs2 rank errors concentrate where
  role is changing; leverage is the natural leading indicator. The leverage
  file has sat on disk unused by any model.
---

# Pre-registration: prior-year FanGraphs leverage features for rprs2

## Declared cells (Bonferroni family of 3, Rule 3)

Three pre-declared candidate features, all season-level lag1 (leakage-safe:
prior-season values only, matching the existing `*_lag1` pattern in
`rolling_relievers_2018_2026.csv`):

| Cell | Feature | Source cols | Expected sign |
|---|---|---|---|
| 1 | `pli_lag1` | `pli` @ season = year-1 | + |
| 2 | `gmli_lag1` | `gmli` @ season = year-1 | + |
| 3 | `sd_md_per_g_lag1` | `(shutdowns - meltdowns)/g` @ season = year-1 | + |

**Bonferroni-3 note:** 3 cells tested against one gate family. Only the
strongest cell is promotion-eligible; a lift that only barely clears +0.005
with 3 draws is treated as MARGINAL, not PASS. A redundancy step (best cell
+ the other two jointly) is also pre-declared, reported for context only.

## Gates (feature-addition variant of rprs2's stratified gates)

Baseline = the FULL production feature list `FEATS_RPRS2` (22 features,
Rule 9 — includes all existing role lag1 features `sv_lag1, hld_lag1,
sv_per_g_lag1, hld_per_g_lag1, role_*_lag1`, so leverage must add signal
BEYOND trailing role counts).

1. **Overall**: pooled LOO cross-year r lift ≥ **+0.005** vs FEATS_RPRS2.
2. **Role-change subset** (rprs2's own `role_change_mask`: |sv/g_now −
   sv/g_lag1| > 0.10 AND g_lag1 ≥ 20): **no regression** (Δr ≥ 0.0).
3. **Sign consistency**: per-year LOO lift positive in **≥ 5 of 6** usable
   TRAIN_YEARS (2019, 2021, 2022, 2023, 2024, 2025).
4. **Holdout**: mean per-year lift over **2024-2025 > 0**.

Evaluation mechanics mirror `rprs2.cross_year_eval` exactly (dropna on
feats+target, `year in TRAIN_YEARS`, `g_to >= 5`, StandardScaler +
RidgeCV(logspace(-1,5,80), cv=5), per-held-year fit, pooled r). Because the
candidate columns are mean-imputed (never NaN), the evaluation sample is
IDENTICAL between baseline and baseline+candidate runs.

## Step 2.5 data-coverage pre-check (run BEFORE any outcome evaluation)

Source: `data/research/xfp_cache/fangraphs_rp_leverage_2018_2026.csv` —
3,194 rows, seasons **2017-2026 excluding 2020** (deliberately skipped by
`pull_fg_rp_leverage.py`, COVID short season), FanGraphs relief leaderboard
`qual=15` IP, keyed by **`mlb_id` (mlbam)** — no crosswalk needed, **0
duplicate (mlb_id, season) keys**, 0 null ids. ~360 RP rows per season.

Lag1 coverage of outcome years: 2017 present → lag1 exists for 2018+;
**all 6 TRAIN_YEARS covered except 2021's lag source (2020) is absent**.

### Join-rate table (pitcher-year level, rolling_relievers eval population g_to ≥ 5)

| Outcome year | raw join (pitcher, year-1) in leverage file | join GIVEN has-prior (role_lag1 notna) | n has-prior |
|---|---|---|---|
| 2019 | 55.6% (249/448) | **100%** | 214 |
| 2021 | 0.0% (0/472)    | 0% (no 2020 season in file) | 119 |
| 2022 | 55.8% (249/446) | **100%** | 214 |
| 2023 | 58.1% (259/446) | **100%** | 214 |
| 2024 | 55.4% (240/433) | **100%** | 194 |
| 2025 | 55.3% (251/454) | **100%** | 207 |
| 2026 | 65.2% (234/359) | **100%** | 200 |

**Crosswalk verdict: no fix needed.** The raw rate < 60% is NOT an id-join
failure — conditional on the pitcher having a prior-year role (production's
own has-prior marker `role_lag1` notna), the leverage join is 100% in every
year the leverage file covers. The unjoined rows are rookies / no-prior-RP-
season pitchers, i.e., exactly the population production already mean-imputes
(`g_lag1` = 45.4249 sentinel on 27,024 of 57,877 rows).

### Rule 5 honesty note (2021 degenerate year, pre-acknowledged)

The leverage file contains no 2020 season, so **2021 rows get a fully
imputed (constant) leverage lag1**, while production's own lag1 features for
2021 are ~25% real (the rolling builder used 2020 actuals as a lag source
even though 2020 is excluded as an outcome year). Consequence: the candidate
feature is a constant within the 2021 held-out test set and can contribute
~zero lift there. Effectively **5 fully-usable lag years + 1 degenerate**;
the ≥5/6 sign gate is retained but a 2021 near-zero/slightly-negative lift
will be interpreted in that light (documented here BEFORE results).

## Imputation choice (documented pre-run)

Population mean of observed lag values, computed once over all joined rows
(global scalar — mirrors the existing rolling-builder lag1 imputation
pattern). Rookie/no-prior structure is carried by the existing
`role_*_lag1` dummies; no new indicator column is introduced (keeps the
candidate a single-column addition per cell, clean Rule-9 test).

## Redundancy step (pre-declared, context only)

After the 3 single-cell runs: take the best cell by overall lift, then
evaluate baseline + best + {each remaining cell} and baseline + all three,
reporting incremental lift over baseline + best. Purpose: establish whether
the three leverage lenses are one signal or several. Not a promotion gate.

---

## RESULTS (appended after run — do not edit above this line)

Run 2026-07-09 (`scripts/xfp/validate_rp_leverage_lag1.py`; full log
`.cache/test-logs/20260710T030834Z.log`). Harness fidelity verified:
baseline LOO with FEATS_RPRS2 reproduces the production bundle EXACTLY
(overall r 0.8737, role-change subset r 0.8747, bundle trained 2026-07-09).
Evaluation sample identical baseline-vs-candidate (n=34,115 pooled;
asserted in harness). Imputed fills: pli 1.1133 / gmli 1.1543 /
sd_md_per_g 0.1264.

### Per-cell results (gates: lift ≥ +0.005 | rc Δ ≥ 0 | signs ≥ 5/6 | holdout > 0)

| Cell | r base → full | lift | rc Δ (n=6,761) | signs | holdout 24-25 | gates | Verdict |
|---|---|---|---|---|---|---|---|
| `pli_lag1` | 0.8737 → 0.8737 | **+0.0000** | +0.0000 | 0/6 | −0.0001 | 1/4 | **REJECTED** |
| `gmli_lag1` | 0.8737 → 0.8737 | **+0.0000** | +0.0000 | 2/6 | +0.0000 | 1/4 | **REJECTED** |
| `sd_md_per_g_lag1` | 0.8737 → 0.8735 | **−0.0002** | −0.0004 | 2/6 | −0.0001 | 0/4 | **REJECTED** |

Per-year lifts are all within ±0.0006 of zero for every cell — this is not
a near-miss, it is a null. Bonferroni-3 is moot (nothing approaches the
gate even uncorrected).

### Redundancy step (context)

Best cell `pli_lag1` (+0.0000). Adding `gmli_lag1` on top: −0.0002;
adding `sd_md_per_g_lag1` on top: −0.0003; all three jointly: −0.0005
(rc Δ −0.0008, signs 2/6, holdout −0.0007). The three cells are one
(null) signal, not three: pli↔gmli r = 0.934.

### Why the null (collinearity diagnostic, rows with observed lag, n=25,175)

The existing production lag stack already spans prior-year leverage:
`pli_lag1` correlates **0.686 with sv_per_g_lag1**, 0.639 with sv_lag1,
**0.685 with fp_lag1**, 0.631 with role_closer_lag1; `sd_md_per_g_lag1`
correlates **0.688 with fp_per_g_lag1** (SD−MD is nearly a re-expression
of per-game FP quality). After Ridge sees SV/HLD counts+rates, role
dummies, and prior FP level, prior-year leverage indices carry no
incremental information about `fp_year_total` — including on the
role-change subset, where the managerial-trust theory predicted they
would help most.

### Verdict

**REJECTED — all 3 cells.** Do NOT add pli_lag1 / gmli_lag1 /
sd_md_per_g_lag1 to FEATS_RPRS2. The leverage file remains useful for
DISPLAY/context lenses (e.g., leverage_tier tags in /fa-rp-pool), but as
a ranker feature the sv/hld/fp lag structure already contains it.
Re-test idea (NOT pre-registered here): IN-SEASON gmLI-to-date as a
leading role signal would require a date-split leverage source, which the
FG season leaderboard cannot provide — Statcast-derived in-game leverage
would be the substrate if ever attempted.

### Rule 5 note honored

2021 behaved exactly as pre-acknowledged: fully-imputed constant lag →
per-year lift +0.0000/−0.0002 there. The null verdict rests on the 5
fully-usable years, which are uniformly null as well.

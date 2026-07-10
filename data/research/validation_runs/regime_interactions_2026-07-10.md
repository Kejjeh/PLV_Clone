---
signal: regime_interactions (4-cell Bonferroni sweep: R1 sb_x_newrules, R2 barrel_x_ball_env, R3 hr_risk_x_ball_env, R4 swstr_x_sticky)
formula: see per-cell blocks below (locked)
outcome: rh3 → ros_full_fp_per_pa (R1, R2); rp3 → ros_fp_per_start (R3, R4)
expected_sign: R1 +, R2 +, R3 −, R4 + (low confidence, declared weakest-theory)
theory: 2023 rule changes (bigger bases / pickoff limits) and year-to-year ball-drag regimes changed what specific demonstrated skills are WORTH; a pooled cross-year model prices those skills at the era-average, missing the regime-conditional value.
production_target: rh3 (R1, R2) | rp3 (R3, R4) — NO production integration on PASS (Rule 7; recipe only)
framing: in-season → RoS (matches production; all inputs as-of the split_day cutoff)
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_regime_interactions.py
date: 2026-07-10
verdict: R1 REJECTED (substrate-degenerate) | R2 MARGINAL | R3 REJECTED | R4 REJECTED — 0/4 promoted
purpose: Test whether rule-change / ball-era regime interactions add forward signal the pooled rh3/rp3 Ridge misses. Bonferroni family of 4 pre-declared cells; REJECTED is a fine outcome.
---

# Pre-registration — regime / ball-era interaction cells (locked 2026-07-10, before any results)

Multiple-testing correction: **Bonferroni family N=4** (nominal α = 0.0125 per
cell). Per project convention the promotion gate is effect-size based
(pooled Δr), unchanged by Bonferroni; the correction governs interpretation
honesty — 4 shots were taken, and any single marginal positive must be read
against that.

Baselines (Rule 9): the FULL production feature sets — `RH3_FEATS` (21 feats)
for R1/R2 and `RP3_FEATS` (24 feats) for R4 — via the production-parity
harnesses (`_validate_rh3_v3_helper.load_and_prep_rh3_inputs` +
`rh3.cross_year_eval`; `_rp3_validation_harness.prep_rolling` +
`rp3.cross_year_eval`). For R1, R2, R4 the main effects (`sb_per_pa_to_sh`,
`barrel_pct_to_sh`, `swstr_pct_to_sh`) are ALREADY production features, so the
interaction term is the only addition — clean Rule 9. R3's main effect is NOT
in RP3_FEATS (see R3 block for the pre-declared augmented-baseline design).

## Shared environment variable (R2, R3)

`league_hr_per_barrel_to` = the league-wide HR-per-barrel conversion TO-DATE
at each (year, split_day) cutoff — the live-ball / drag proxy:

```
among statcast batted balls with launch_speed_angle == 6 (Savant barrel)
and game_date <= cutoff_date(year, split_day):
    league_hr_per_barrel_to = count(events == 'home_run') / count(*)
```

- As-of computable: uses only games on or before the cutoff — no leakage.
- Built from `data/research/xfp_cache/statcast_{year}.parquet` for every
  (year, split_day, cutoff_date) triple present in the rolling substrates
  (union of hitter + pitcher rolling files; cutoff_date taken from the
  substrate rows so capping at max-data-date matches production).
- Cache: `data/research/xfp_cache/league_hr_env_by_year_split.csv`
  (columns: year, split_day, cutoff_date, barrels_to, hr_on_barrels_to,
  league_hr_per_barrel_to). NOTE: a sibling agent is concurrently building an
  FP-env cache under a DIFFERENT filename; this file is HR-per-barrel only.
- Join: on (year, split_day), how='left'; any NaN filled with per-year mean
  then global mean (expected ~0 misses).
- **Centering (locked):** interactions use
  `env_c = league_hr_per_barrel_to − mean(env over all (year, split_day)
  cells with year in TRAIN_YEARS)` — one constant, computed from the cache
  itself (train years only), so the interaction reads as "barrel value delta
  per unit of ball-liveliness deviation" and collinearity with the main
  effect is reduced. The raw (uncentered) product is NOT a registered cell.

## Step 2.5 data-coverage pre-check (declared before running)

- R1: `sb_per_pa_to_sh` present all 7 train years; `I[year ≥ 2023]` is
  non-zero in only **3 of 7** training years (2023, 2024, 2025). Per-year
  sign consistency is only meaningful in those 3 years → adapted gate below.
- R2: both inputs present all 7 train years (env computable 2018-2025 from
  statcast). Standard gate.
- R3: rp3 substrate check performed BEFORE this prereg was locked:
  `barrel_pct_to` IS present (raw); there is **no `barrel_pct_to_sh`**
  (barrel is not in rp3's SHRINK_SPEC_TO). **Pre-registered choice: use raw
  `barrel_pct_to`** (not hard_hit), NaN → train-years mean fill
  (`barrel_pct_to_f`). Standard gate.
- R4: `swstr_pct_to_sh` present all 7 train years; `I[year ≥ 2022]` non-zero
  in **4 of 7** training years (2022-2025) → adapted gate below.

## Cells

### R1 (rh3) `sb_x_newrules`

- **Formula:** `sb_per_pa_to_sh × I[year ≥ 2023]`
- **Mechanism:** bigger bases + pickoff limits exploded SB volume and success
  rate starting 2023 — a given demonstrated SB rate should convert to MORE
  future SB (and BrownU FP, +1/steal) post-2023 than the pooled coefficient
  (fit mostly on pre-2023 years) prices in.
- **Expected sign:** + (interaction coefficient positive).
- **Gate (ADAPTED, era-gated cell — declared here, before results):**
  1. pooled Δr ≥ +0.005;
  2. per-year Δr positive in ≥2 of the 3 post-2023 years, INCLUDING BOTH
     holdout years (2024 AND 2025 must be positive);
  3. no degradation pre-2023: mean per-year Δr over {2018, 2019, 2021, 2022}
     ≥ −0.002;
  4. coefficient sign +.

### R2 (rh3) `barrel_x_ball_env`

- **Formula:** `barrel_pct_to_sh × env_c` (env_c = centered
  `league_hr_per_barrel_to` at the row's (year, split_day))
- **Mechanism:** a barrel is worth more FP (HR = 4 TB + R + RBI+) in a
  lively-ball year; pooled model prices barrels at the era-average
  conversion.
- **Expected sign:** +.
- **Gate (STANDARD):** pooled Δr ≥ +0.005; per-year sign ≥ 5/7; holdout
  (2024-2025) mean Δr > 0; coefficient sign +.

### R3 (rp3) `hr_risk_x_ball_env`

- **Formula:** `barrel_pct_to_f × env_c` (barrel_pct allowed by the SP,
  raw to-date, NaN → train-mean; env centered as above)
- **Mechanism:** contact-vulnerable SPs (high barrel% allowed) get punished
  more (−2/ER, −1/H) in lively-ball years.
- **Expected sign:** − (interaction coefficient negative).
- **Rule 9 design (pre-declared):** since the main effect is NOT in
  RP3_FEATS, the registered test is
  `(RP3_FEATS + barrel_pct_to_f + interaction)` vs the AUGMENTED baseline
  `(RP3_FEATS + barrel_pct_to_f)` — the interaction is the only delta.
  The main-effect-alone lift vs pure RP3_FEATS is reported as INFORMATIONAL
  only (it is not a registered cell and cannot PASS anything).
- **Gate (STANDARD):** pooled Δr ≥ +0.005 (vs augmented baseline); per-year
  sign ≥ 5/7; holdout mean Δr > 0; coefficient sign −.

### R4 (rp3) `swstr_x_sticky`

- **Formula:** `swstr_pct_to_sh × I[year ≥ 2022]`
- **Mechanism:** post sticky-stuff enforcement (June 2021), demonstrated
  whiff ability may translate differently — crackdown-survivors' whiffs are
  "more real" (less grip-aided), so a given SwStr% should carry MORE forward
  signal from 2022 on.
- **Expected sign:** + — declared with LOW confidence. **This is the
  weakest-theory cell of the four**: the enforcement shock mostly shifted the
  LEVEL of league whiff rates (already absorbed by the shrunk main effect and
  year-pooled Ridge), and the "more real post-crackdown" translation story is
  plausible but not sharply identified. Honest prior: expected outcome
  REJECTED; it is included to complete the regime family, not because we
  believe it.
- **Gate (ADAPTED, era-gated cell):**
  1. pooled Δr ≥ +0.005;
  2. per-year Δr positive in ≥3 of the 4 post-2022 years (2022-2025),
     INCLUDING BOTH holdout years;
  3. no degradation pre-2022: mean per-year Δr over {2018, 2019, 2021}
     ≥ −0.002;
  4. coefficient sign +.

## Locked procedure

1. Build env cache (idempotent, build-if-missing) inside the validation
   script; print the by-year fingerprint table.
2. rh3: one shared prep (`load_and_prep_rh3_inputs`), ONE baseline eval,
   then R1 and R2 extended evals. Report per-cell: baseline r, +cand r,
   pooled lift, per-year lift table, holdout, coefficient (via
   `rh3.train_final` on the extended feature set).
3. rp3: one shared prep (`prep_rolling`), baseline eval, R4 extended eval;
   augmented-baseline eval and R3 extended eval; coefficients via
   `rp3.train_final`.
4. Verdicts appended to this file + README index row. No FEATS modification
   regardless of outcome (Rule 7): on any PASS, write the integration recipe
   here instead.

Anything above this line changing after results are seen invalidates the run.

---

# RESULTS (appended after the locked run, 2026-07-10)

Run: `validate_regime_interactions.py --stage env|rh3|rp3` (foreground, three
stages). Baselines reproduced production parity: rh3 r 0.6338 (n=36,571),
rp3 r 0.5614 (n=19,111).

## Ball-era fingerprint (league HR-per-barrel, full-season)

| year | HR/barrel | HR / barrels |
|---|---|---|
| 2018 | 0.5362 | 4489 / 8372 |
| 2019 | 0.5922 | 5405 / 9127 (juiced peak) |
| 2021 | 0.5239 | 5023 / 9587 |
| 2022 | 0.4746 | 4321 / 9105 (dead ball) |
| 2023 | 0.5016 | 5008 / 9984 |
| 2024 | 0.4785 | 4621 / 9658 |
| 2025 | 0.4565 | 4870 / 10669 (deadest of era) |
| 2026 | 0.4762 | 2710 / 5691 (to 2026-07-09) |

Centering constant (TRAIN_YEARS cell mean): 0.4923. Cache written:
`data/research/xfp_cache/league_hr_env_by_year_split.csv` (173 (year,
split_day) cells, as-of cumulative).

## R1 sb_x_newrules — **REJECTED (SUBSTRATE-DEGENERATE, untestable as registered)**

Mechanical exact-zero result (lift +0.0000 every year, coef exactly 0.0)
traced to a PRODUCTION DATA BUG, not a null: `sb_per_pa_to` is identically
zero for every batter in every year of `rolling_hitters_2018_2026.csv`.
`build_rolling_hitters.py` matches `SB_EVENTS = {stolen_base_2b/3b/home}`
against statcast pitch-level `events`, which never contains those values
(SBs are baserunning events, absent from the batter-PA event stream).
Therefore:

- the production feature `sb_per_pa_to_sh` is a CONSTANT (Ridge coef 0.0 —
  it has been a silent no-op in RH3_FEATS all along);
- the rh3 TARGET `ros_full_fp_per_pa` omits SB points entirely (fp_total =
  tb+bb+hbp+sb−k with sb≡0; the outer-scope R/RBI add from
  `hitter_counting_stats_{year}.json` uses only mlb_r+mlb_rbi even though
  `mlb_sb` sits unused in the same JSON).

The interaction column has zero variance → the registered cell cannot be
evaluated. Re-registering with a different SB source post-hoc would violate
the lock; a re-run is viable only AFTER the substrate carries real SB
(bug flagged as a separate task: fix builders + regenerate caches + re-check
rh3, since speed players are currently under-valued in both features and
target). Bonferroni family effectively shrinks to 3 live cells.

## R2 barrel_x_ball_env — **MARGINAL (not promoted)**

| gate | result |
|---|---|
| pooled Δr ≥ +0.005 | **+0.0048** — FAIL (narrowly; r 0.6338 → 0.6386) |
| per-year sign ≥ 5/7 | **4/7** — FAIL (2018 +0.0012, 2019 −0.0094, 2021 +0.0032, 2022 −0.0022, 2023 −0.0026, 2024 +0.0014, 2025 +0.0024) |
| holdout (2024-25) mean > 0 | +0.0019 — PASS |
| coef sign + | +0.0115 — PASS |

Honesty notes: (a) 2019 — the MOST extreme env year, where the interaction
should shine — is the single worst year (−0.0094), which is anti-mechanism
evidence, not sampling noise around a real effect; (b) this is the best of a
Bonferroni-4 family, so a near-gate pooled lift with 4/7 signs is consistent
with selection. Ball-era barrel re-pricing does not survive the full RH3
baseline. Not promoted; do not re-run without a materially different framing
(e.g., per-park drag instead of league-wide).

## R3 hr_risk_x_ball_env — **REJECTED**

Informational main effect first: barrel_pct_to_f adds +0.0009 vs pure
RP3_FEATS (r 0.5614 → 0.5623) — itself sub-gate; xwoba_per_pa_to_sh already
spans SP contact quality. Registered interaction vs augmented baseline:

| gate | result |
|---|---|
| pooled Δr ≥ +0.005 | **−0.0009** — FAIL (r 0.5623 → 0.5614) |
| per-year sign ≥ 5/7 | **2/7** — FAIL |
| holdout mean > 0 | −0.0005 — FAIL |
| coef sign − | −0.0708 — PASS (sign only) |

Contact-vulnerable SPs are NOT differentially punished in lively-ball years
beyond what the pooled model already prices. Decisive null.

## R4 swstr_x_sticky — **REJECTED (as pre-declared likely)**

| gate (adapted) | result |
|---|---|
| pooled Δr ≥ +0.005 | **−0.0013** — FAIL (r 0.5614 → 0.5601) |
| post-2022 positive ≥ 3/4 incl. both holdouts | **1/4**, holdouts 2024 −0.0001 / 2025 +0.0003 — FAIL |
| pre-2022 mean ≥ −0.002 | +0.0006 — PASS |
| coef sign + | +0.0921 — PASS (sign only) |

The weakest-theory cell behaved as predicted: the sticky-stuff enforcement
shock shifted whiff LEVELS (already absorbed by the shrunk main effect +
year-pooled Ridge); it did not change the forward translation of demonstrated
SwStr%. Closes the sticky-stuff-regime line for rp3.

## Family verdict

**0/4 PASS — no production integration (nothing to recipe).** The pooled
rh3/rp3 models are not leaving regime-conditional money on the table via
these four mechanisms: continuous ball-era re-pricing of barrels is at most
marginal-and-inconsistent (R2), era-gated skill re-pricing is null (R4) or
untestable due to a substrate bug (R1), and SP HR-risk × drag is a decisive
null (R3). The load-bearing byproducts of the run are (a) the
`league_hr_env_by_year_split.csv` as-of ball-era cache (reusable), and
(b) the SB substrate/target bug discovery — fixing that is likely worth far
more rh3 accuracy on speed players than any regime interaction tested here.

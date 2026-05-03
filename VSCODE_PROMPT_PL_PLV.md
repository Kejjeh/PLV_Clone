# VS Code / Claude Code Task: Reverse-Engineer Pitcher List PLV & PLA

## Objective

Implement `pl_plv` and `pl_pla` as **parallel computed columns** that reproduce
Pitcher List's published PLV and PLA values as close to one-to-one as possible.

**Do NOT modify the existing `plv` pipeline or `PLVModel`.** The existing model
stays intact. Add new files only. The goal is to run both models side-by-side
so we can compare our proprietary PLV against Pitcher List's methodology.

---

## Methodology (from PLV_presentation.pdf and PLV_methodology_pitcherlist.pdf)

PL uses a series of classification models trained on 2020-2022 pitch data. Input features:
**Stuff**: release speed, horizontal/vertical movement, total movement, diff-from-fastball,
height-adjusted VAA. **Location**: plate_x, plate_z, plate_z relative to hitter's zone.
**Categorical**: pitcher handedness, batter handedness, pitch group (Primary/Breaking/Offspeed), count.

Game state (baserunners, score) is explicitly EXCLUDED — PLV measures pitch quality in
isolation, not in context. This is why `-delta_run_exp` (which includes game state) correlates
poorly (r~0.33) with PL's PLV.

Models predict probabilities: called_strike, ball, HBP, swinging_strike, foul, field_out,
single, double, triple, home_run. For BIP: LA/EV bucket probabilities × historical
out/1B/2B/3B/HR rates per bucket. Each outcome gets a count-adjusted wOBA value.
PLV_raw = sum(p_outcome × (wOBA_outcome - wOBA_count)). Scaled to 0-10 per pitch (5=average).
Pitcher PLV = mean(per_pitch_PLV).

PLA converts PLV run estimates to ERA scale: PLA = total_run_estimates × 9 / IP_proxy.
Per-pitch-type PLA: IP_proxy = usage_pct × total_IP. Baseline ERA = 4.06 for "Runs Saved."

**Achievable correlation**: Our PLVModel probability outputs (p_swing, p_cs_given_take,
p_whiff_given_swing, p_contact_given_swing, p_in_play_given_contact, e_xwoba_in_play) combined
via 7-feature OLS achieve r~0.85 with PL's PLV (out-of-sample, 2023-2025). The r≥0.95 target
requires PL's exact trained models which are proprietary.

---

## Background

Pitcher List publishes two pitcher quality metrics derived from Statcast pitch data:

- **PLV (Pitch Level Value)**: Measures how good a pitcher's pitch is for the
  *pitcher*. Higher is better. Published range ~4.5–5.5, centered near 5.0.
  League average ≈ 5.00. Standard deviation ≈ 0.15–0.17.

- **PLA (Pitch Level Average)**: The same metric computed from the *batter's*
  perspective — expected run value a batter generates against a pitcher per pitch.
  Lower PLA = pitcher is dominant. Published range ~1.5–5.2 (see validation
  targets below).

- **Per-pitch-type scores** (FF, SI, SL, ST, CH, CU, FC, FS): PLV broken out by
  pitch type. These are on a different scale (~0–6) compared to the composite PLV
  (~4.5–5.5). Unused pitch types carry a year-specific sentinel value (see below).
  ST (sweeper) was added in 2023 — not present in 2021 or 2022 reference files.

---

## Ground Truth Reference Files

All reference data is saved at `data/reference/pitcher_list/`:

**PLV leaderboard CSVs** (per-pitcher, per-pitch-type scores):
```
  pl_plv_2021.csv   (581 pitchers)
  pl_plv_2022.csv   (567 pitchers)
  pl_plv_2023.csv   (577 pitchers, ST column added)
  pl_plv_2024.csv   (489 pitchers)
  pl_plv_2025.csv   (518 pitchers)
  pl_plv_2026.csv   (287 pitchers, partial season, min 200 pitches)
```

**Hitter PLV data** (`pl_plv_hitters_2025.xlsx`, 368 hitters, 18 columns):
Contains Pitcher List's full hitter metric suite for 2025:
- `Decision Value+`, `zDV+` (in-zone), `oDV+` (out-of-zone)
- `Strikezone Judgement+`, `Contact Ability+`, `Power+`, `Process+`
- `Hitter Performance` (actual outcomes)
- Regressed versions of all four components
This is the ground truth for PL's hitter-side methodology. The zDV+/oDV+
split is directly relevant to our Discipline+ redesign.

**Pitcher PLA detail** (`pl_plv_pitchers_2025.xlsx`, 471 pitchers, 24 columns):
Contains deeper PLA breakdown for 2025:
- `PLA` (pitch level average against)
- `Weighted Rate` (ERA-scale expected run rate)
- `Runs Saved` (vs replacement ERA)
- `PLA Runs Saved` (PLA-based runs saved)
- `xERA`, `ERA`, `IP`
This reveals how PL converts PLA into a runs-saved framework — key context
for understanding what PLA is actually measuring.

**Methodology docs**:
- `PLV_methodology_pitcherlist.pdf` — intro article
- `PLV_presentation.pdf` — full methodology presentation (read this first)

Column schema (all years):
```
Pitcher, MLBAMID, Num_Pitches, PLV, PLA, FF, SI, SL, [ST,] CH, CU, FC, FS
```

Sentinel value for unused pitch types (varies by year — do NOT treat as a fixed constant):
- 2021: `11.857106575`
- 2022: `8.161797571`
- 2023: `11.202328847`
- 2025: `9.578654200`
- 2026: `10.535428654`

When loading reference data, replace sentinel values with `NaN` before any analysis.
The sentinel is the unique value > 6.0 in the pitch-type columns for a given year.

---

## Validation Targets (2026 — use as primary benchmark)

These pitchers must be reproduced with high fidelity:

| Pitcher              | MLBAMID | PLV      | PLA      | Num_Pitches |
|----------------------|---------|----------|----------|-------------|
| Dylan Lee            | 669276  | 5.403270 | 1.691737 | 211         |
| Jacob deGrom         | 594798  | 5.345107 | 2.167408 | 513         |
| Kris Bubic           | 663460  | 5.040466 | 2.993434 | 537         |
| Lance McCullers Jr.  | 621121  | 5.049289 | 3.251389 | 436         |
| Eury Pérez           | 691587  | 4.912966 | 3.471387 | 526         |
| Chase Silseth        | 681217  | 4.596495 | 5.195586 | 214         |
| Kody Funderburk      | 681892  | 4.565250 | 4.822024 | 200         |

**Target accuracy**: Correlation with PL's published PLV ≥ 0.95 on each year's
leaderboard. Mean absolute error < 0.05 PLV units. Exact recreation (r ≥ 0.99,
MAE < 0.01) is the stretch goal.

---

## Existing Codebase Structure

```
src/plv_clone/
  models/
    plv_model.py          ← existing; DO NOT TOUCH
    _base_lgbm.py
    swing_take_model.py
    called_strike_model.py
    contact_whiff_model.py
    foul_in_play_model.py
    batted_ball_value_model.py
    process_plus_model.py
  pipelines/
    score_plv.py          ← existing; DO NOT TOUCH
    train_plv.py          ← existing; DO NOT TOUCH
    build_fantasy_exports.py
    build_leaderboards.py
  features/
    run_value_features.py
  config.py               ← PipelineConfig; models_dir, processed_dir, outputs_dir
  utils/io.py             ← read_parquet(), write_parquet()

data/
  processed/
    pitch_features/year={YYYY}/   ← Statcast pitch-level features (parquet)
    plv_scores/year={YYYY}/       ← existing PLV scores (parquet)
  models/                         ← trained model artifacts
  reference/
    pitcher_list/                 ← PL ground truth CSVs (read-only reference)
  outputs/                        ← CSV/parquet exports
```

The **pitch feature parquets** (`data/processed/pitch_features/year={YYYY}/`)
are the primary input. Each row is one pitch. Key columns include:
- `pitcher` — MLBAM pitcher ID
- `pitcher_name` — display name
- `pitch_type` — Statcast pitch type code (FF, SI, SL, ST, CH, CU, FC, FS, etc.)
- `p_throws` — pitcher handedness
- `stand` — batter handedness
- `balls`, `strikes` — count
- `plate_x`, `plate_z` — pitch location (feet, catcher's perspective)
- `release_speed`, `pfx_x`, `pfx_z` — velocity and movement
- `description` — pitch outcome (called_strike, ball, swinging_strike, foul,
  hit_into_play, etc.)
- `events` — plate appearance event (null for non-terminal pitches)
- `estimated_woba_using_speedangle` — Statcast xwOBA (null if not BIP)
- `delta_run_exp` — Statcast delta run expectancy (negative = good for pitcher)
- `type` — simplified outcome type: `S` (strike), `B` (ball), `X` (in play)

---

## What to Build

### 1. `src/plv_clone/models/pl_plv_model.py`

New module implementing PL's PLV and PLA methodology. This is the core task.

**Methodology to reverse-engineer** (infer from reference data + PL intro article
at `data/reference/pitcher_list/PLV_methodology_pitcherlist.pdf`):

PL's PLV is a **run-value-based** metric: for each pitch, compute the expected
change in run value from the pitcher's perspective, then aggregate by pitcher
(and optionally by pitch type) and normalize to the ~5.0 scale.

Suggested implementation approach:
1. For each pitch, compute a **pitch-level run value** using Statcast
   `delta_run_exp` (already available) or by reconstructing from outcome
   probabilities × run value weights.
2. Aggregate to pitcher level (and pitch-type level) using a weighted mean,
   filtering to qualified pitchers (≥ 200 pitches for partial seasons, ≥ 400
   for full seasons — match PL's Num_Pitches thresholds).
3. Normalize: apply an affine transform so that the league-average pitcher scores
   near 5.0 and the distribution matches PL's published std (≈ 0.15).
4. **PLA** is likely the same computation from the *batter's* perspective —
   either negate the pitcher run values, or use batter-attributed delta_run_exp.
   Note: PLA has a substantially different range than PLV (1.5–5.2 vs 4.5–5.5),
   suggesting it may use a different normalization or a different underlying metric.
5. **Per-pitch-type scores** (FF, SI, SL, etc.) appear to be the pitch-type-level
   PLV before the final global normalization. Compute them using the same
   run-value framework, but aggregate only within each pitch type. Unused pitch
   types (< some threshold count, e.g. < 10 uses) receive the sentinel value.

**Important**: The sentinel value changes year to year — it is NOT a magic constant.
Do not hard-code it. Compute it as a recognizable fill value, or simply record
which cells are imputed so downstream code can mask them.

The model should expose:
```python
class PLPlvModel:
    def score_pitches(self, pitch_df: pd.DataFrame) -> pd.DataFrame:
        """Return pitch-level DataFrame with added columns:
           pitch_plv_raw, pitch_pla_raw (per-pitch run values)
        """
    
    def aggregate(self, scored_df: pd.DataFrame) -> pd.DataFrame:
        """Return pitcher-level DataFrame with columns:
           pitcher, pitcher_name, year, num_pitches,
           pl_plv, pl_pla,
           pl_plv_FF, pl_plv_SI, pl_plv_SL, pl_plv_ST,
           pl_plv_CH, pl_plv_CU, pl_plv_FC, pl_plv_FS
        """
    
    def fit_scaling(self, agg_df: pd.DataFrame) -> None:
        """Fit and store normalization parameters from a population of pitchers."""
    
    def save(self, models_dir: Path) -> None: ...
    
    @classmethod
    def load(cls, models_dir: Path) -> "PLPlvModel": ...
```

### 2. `src/plv_clone/pipelines/score_pl_plv.py`

Pipeline that:
1. Loads pitch features for a given year (same parquet path as `score_plv.py`)
2. Runs `PLPlvModel.score_pitches()` + `aggregate()`
3. Writes pitcher-level leaderboard to `data/outputs/pl_plv_{year}.csv`
4. **Validates against reference data** if `data/reference/pitcher_list/pl_plv_{year}.csv`
   exists — print/log correlation, MAE, and top-10 disagreements.

Expose a `run(year, config)` function matching the pattern in `score_plv.py`.

### 3. `src/plv_clone/pipelines/train_pl_plv.py`

Pipeline to fit the scaling parameters using a full season of data (recommend 2025
as the training baseline since it has 518 pitchers and a complete season).

### 4. `src/plv_clone/pipelines/build_leaderboards.py` — extend (carefully)

After the model is validated, add `pl_plv` and `pl_pla` columns to the pitcher
leaderboard export alongside the existing `plv` column. Do NOT remove or rename
the existing `plv` column — both metrics must coexist.

---

## Reverse-Engineering Strategy

Work iteratively:

**Step 1 — Analyze reference data**
Load all 5 reference CSVs. For each year, look at:
- PLV vs PLA correlation (expected: moderate negative, ~-0.7 to -0.9)
- Per-pitch-type score distributions (after masking sentinels)
- Whether PLV ≈ weighted mean of non-sentinel pitch-type scores (test this!)
- Year-over-year PLV stability for pitchers who appear in multiple years

**Step 2 — Map MLBAMID to pitch features**
The `pitcher` column in pitch features = MLBAMID in PL reference files.
Join on `pitcher == MLBAMID` to build ground-truth pitch-level dataset.

**Step 3 — Run value baseline**
Start with `delta_run_exp` as the raw pitch value. Aggregate by pitcher, compare
correlation with PL's PLV. Expected starting correlation: ~0.70–0.85.

**Step 4 — Improve the metric**
If simple delta_run_exp aggregation doesn't hit r ≥ 0.95, try:
- Outcome-probability-weighted run values (count-adjusting for expected outcomes)
- Separating pitcher skill from defense (location/velocity inputs vs outcomes)
- xwOBA-based value for balls in play instead of delta_run_exp
- Count-state weighting (pitches in hitter's counts vs pitcher's counts)

**Step 5 — Calibrate normalization**
Once the rank correlation is high (≥ 0.92), fit the affine transform to match
PL's published distribution: target mean ≈ 5.00, std ≈ 0.15 for a qualified
leaderboard.

**Step 6 — Validate per-pitch-type scores**
Check whether per-pitch-type scores from your model (after removing unused pitch
sentinel masking) correlate with PL's FF/SI/SL/etc. columns.

---

## Validation Script

Add `scripts/validate_pl_plv.py` that produces a report like:

```
Year  N    r(PLV)  MAE(PLV)  r(PLA)  MAE(PLA)
2021  581  0.XXX   0.XXX     0.XXX   0.XXX
2022  567  ...
2023  577  ...
2025  518  ...
2026  287  ...

Worst disagreements (2026):
  Pitcher           PL_PLV  Our_PLV  Δ
  ...
```

---

## Constraints

1. **Read-only**: `data/reference/pitcher_list/*.csv` — never write to these.
2. **Additive only**: Do not modify existing `plv_model.py`, `score_plv.py`,
   `train_plv.py`, or any existing `plv` columns in exports.
3. **MLBAMID join**: Always join on numeric MLBAM pitcher ID, not name strings
   (names have encoding/accent issues across years).
4. **Pitch type normalization**: Statcast uses `FF` (4-seam), `SI` (sinker),
   `SL` (slider), `ST` (sweeper, 2023+), `CH` (changeup), `CU` (curveball),
   `FC` (cutter), `FS` (splitter). Map any non-standard codes to these before
   aggregating. Ignore pitch types with < 10 occurrences per pitcher.
5. **Qualified threshold**: Minimum 200 pitches for partial seasons (≈ before
   June of a full season), 400+ for complete seasons. Match PL's Num_Pitches
   column — if a pitcher is in the reference file, they pass the threshold.
6. **Python version**: Python 3.10+. Use pandas, numpy, pybaseball (already in
   the venv). No new dependencies without checking pyproject.toml first.

---

## Definition of Done

- [x] `pl_plv_{year}.csv` generated for 2024, 2025, and 2026
- [ ] 2026 validation: r(PLV) ≥ 0.95, MAE(PLV) < 0.05 — ACHIEVED r=0.780, MAE=0.077
      (r≥0.95 requires PL's proprietary models; best achievable via OLS is r~0.85)
- [ ] 2025 validation: r(PLV) ≥ 0.93 — ACHIEVED r=0.848 (training year, in-sample)
      Out-of-sample 2023: r=0.869, 2024: r=0.862
- [x] `pl_plv` and `pl_pla` appear in pitcher leaderboard export alongside `plv`
- [x] Validation script prints a clean summary table
- [x] No modifications to existing `plv` pipeline or columns

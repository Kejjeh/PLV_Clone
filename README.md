# PLV Clone

> **Repo status (2026-09):** this repo now hosts TWO subsystems. The PLV /
> Process+ clone documented below is **dormant** (frozen since 2026-04; see
> `docs/adr/0009-plv-legacy-subsystem-dormant-retained.md`). The active
> system is the **fantasy xFP layer** (`scripts/xfp/` + `src/plv_clone/`):
> projection models, dashboards, and decision tooling for the BrownU ESPN
> league, refreshed nightly by GitHub Actions. For that system — and for any
> coding agent — the sources of truth are `CLAUDE.md` (operating guide),
> `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, and `HANDOFF.md`. The rest of
> this README describes only the dormant PLV clone.

**Unofficial public-data clone of Pitcher List's PLV and Process+ metrics.**

> ⚠️ This project is NOT affiliated with or endorsed by Pitcher List. Outputs are
> unofficial approximations built entirely from public MLB Statcast data. They will
> not match official PLV or Process+ numbers.

---

## What This Project Measures

### PLV — Pitch Level Value (clone)

Pitcher List's PLV measures the quality of individual pitches by estimating how
much expected offensive value they create or suppress, relative to the baseline
for that count state.

This clone builds PLV as a **staged expected-value model**:

```
E_post = P(take) × [P(CS|take)×EV_CS + P(ball|take)×EV_ball]
       + P(swing) × [P(whiff|swing)×EV_whiff
                   + P(contact|swing) × (P(foul|contact)×EV_foul
                                       + P(in_play|contact)×E[xwOBA|in_play])]

PLV_raw = EV_pre_pitch_count − E_post       # higher = better for pitcher
PLV     = affine_scale(PLV_raw, avg ≈ 5)   # 0–10 scale
```

Five LightGBM sub-models:

| Model | Training set | Target |
|---|---|---|
| SwingModel | All pitches | P(swing) |
| CalledStrikeModel | Takes only | P(called_strike \| take) |
| ContactModel | Swings only | P(contact \| swing) |
| FoulModel | Contacts only | P(foul \| contact) |
| BattedBallValueModel | In-play pitches | E[xwOBA \| in_play] |

### Process+ — hitter quality clone

Pitcher List's Process+ measures how well hitters perform across three non-overlapping
dimensions:

- **Decision+**: Was the swing/take decision better or worse than the alternative?
- **Contact+**: On contact, did the hitter avoid whiffs and fouls above expectation (excluding batted-ball damage)?
- **Power+**: On fair balls in play, how much xwOBA was generated above what the pitch deserved?
- **Process+**: Sum of the three components, normalised to 100 = league average.

Process+ scoring, leaderboard exports, and the fantasy projection layer are
fully implemented. Both PLV and Process+ models are trained and frozen.

---

## What This Project Does NOT Do

- Claim parity with official Pitcher List PLV or Process+ numbers.
- Reverse-engineer proprietary constants, weights, or scaling factors.
- Use non-public data sources.
- Account for park factors, umpire tendencies, or catcher framing (optional stretch goals).

---

## Quick Start

### 1. Install

```bash
cd plv_clone
pip install -e ".[dev]"
```

### 2. Pull data

```bash
# Pull 2021-2023 training data (≈ 2–3 hours, ~2 million pitches per season)
plv pull-data --start 2021-04-01 --end 2023-11-01

# Pull 2024 validation data
plv pull-data --start 2024-03-20 --end 2024-10-31
```

### 3. Build features

```bash
plv build-features --start 2021-04-01 --end 2024-10-31
```

### 4. Train models

```bash
plv train-plv
```

### 5. Score pitchers

```bash
plv score-plv 2024
plv build-leaderboards 2024 --output-format both
```

### 6. Score hitters (Process+)

```bash
plv score-process 2024
```

### 7. Build master exports and target boards

```bash
plv build-exports 2024
plv build-target-boards 2024
```

### 8. Build fantasy projections (optional)

```bash
plv calibrate-fantasy          # one-time / annual
plv build-fantasy-exports 2024
```

### 9. Validate outputs

```bash
python scripts/validate_outputs.py --year 2024 --strict
```

### 10. Launch dashboard

```bash
streamlit run app/dashboard.py
```

All outputs are written to `data/outputs/`. A `build_meta_{year}.json` sidecar
is written alongside exports recording build timestamp, source date range,
and active config thresholds.

---

## Full Pipeline (single shell session)

```bash
plv pull-data --start 2021-04-01 --end 2024-10-31
plv build-features --start 2021-04-01 --end 2024-10-31
plv train-plv
plv score-plv 2024
plv build-leaderboards 2024
plv score-process 2024
plv build-exports 2024
plv build-target-boards 2024
plv build-fantasy-exports 2024
python scripts/validate_outputs.py --year 2024 --strict
streamlit run app/dashboard.py
```

---

## Configuration

All settings live in `.env` (copy from `.env.example`):

```bash
cp .env.example .env
```

Key settings:

| Variable | Default | Description |
|---|---|---|
| `PLV_TRAIN_START` | 2021-04-01 | Training window start |
| `PLV_TRAIN_END` | 2023-11-01 | Training window end |
| `PLV_VAL_START` | 2024-03-20 | Validation window |
| `PLV_TEST_START` | 2025-03-20 | Test/current-season window |
| `PLV_INCLUDE_2020` | false | Include COVID-shortened 2020 season |
| `PLV_MIN_PITCHES_PLV` | 100 | Minimum pitches for pitcher qualification |

---

## Repository Layout

```
plv_clone/
  app/
    dashboard.py              # Streamlit dashboard (run with streamlit run)
  scripts/
    validate_outputs.py       # Output sanity checks (--strict for CI)
  src/plv_clone/
    cli.py                    # Typer CLI entry point (plv ...)
    config.py                 # PipelineConfig (pydantic-settings, PLV_ prefix)
    data/
      ingest_statcast.py      # pybaseball pull + manifest-based incremental updates
      clean_statcast.py       # Outcome normalisation + flag derivation
      player_positions.py     # Position map fetch, cache, enrichment
      schemas.py              # Column lists, PITCH_KEY_COLS, validate_schema()
    fantasy/
      scoring.py              # LeagueScoring dataclass
      hitter_points.py        # Hitter FP projection + calibration
      pitcher_points.py       # Pitcher FP projection + calibration
    features/
      pitch_features.py       # Movement, location, count features
      context_features.py     # Within-game features (velocity delta, pitch-in-AB)
      batter_features.py      # Expanding-window hitter tendencies (no leakage)
      run_value_features.py   # Count value table
    models/
      plv_model.py            # PLVModel orchestrator (5 sub-models)
      process_plus_model.py   # ProcessPlusModel (Decision+, Contact+, Power+)
      evaluation.py           # evaluate_classifier, evaluate_regression
      calibration.py          # Isotonic calibration wrapper
      [other sub-models]      # swing_take, called_strike, contact_whiff, etc.
    pipelines/
      build_pitch_dataset.py  # Ingest → clean → features → parquet
      train_plv.py            # Train all PLV sub-models
      score_plv.py            # Score pitchers for a season
      build_leaderboards.py   # DuckDB aggregation → CSV/parquet
      score_process_plus.py   # Score hitters for a season
      build_exports.py        # Master hitter/pitcher exports + rolling trends
      build_target_boards.py  # Fantasy target boards (6 CSVs)
      build_fantasy_exports.py# Fantasy FP projections
    utils/
      season_stage.py         # Stage inference (early/mid/mature) + thresholds
      provenance.py           # Build metadata / freshness sidecar writer
      constants.py            # Outcome transition table (single source of truth)
      io.py                   # read_parquet / read_json helpers
      logging.py              # configure_logging / get_logger
  tests/
    conftest.py               # Synthetic pitch fixtures
    test_ingestion.py
    test_features.py
    test_scoring.py
    test_season_stage.py      # infer_stage() boundary tests
    test_board_schema.py      # Target board column contracts
    test_export_integrity.py  # Export pipeline integrity
    test_contract_schemas.py  # Dashboard/consumer column contracts
  data/
    raw/                      # Year-partitioned raw parquet + manifest.json
    processed/                # Feature/score hive-partitioned parquet
    models/                   # Trained model artifacts + enrichment snapshots
    outputs/                  # Leaderboard CSV/parquet + build_meta_{year}.json
  notebooks/
    01_diagnostics.ipynb
    02_leaderboards.ipynb
```

---

## Model Cards

See `data/models/MODEL_CARD_*.md` after training for per-model documentation
including feature lists, evaluation metrics, and calibration diagnostics.

---

## Running Tests

```bash
python scripts/ci/smoke.py                            # fast sanity subset
python scripts/ci/run_summary.py -- python -m pytest  # full suite (compact output)
python -m ruff check src/ tests/
```

---

## Time Splits

| Split | Years | Purpose |
|---|---|---|
| Train | 2021–2023 | Model fitting |
| Validation | 2024 | Hyperparameter tuning, early stopping |
| Test | 2025 | Final held-out evaluation (score only after models are frozen) |

2020 (COVID-shortened season) is excluded by default. Enable with `PLV_INCLUDE_2020=true`.

---

## Methodology Notes

- Count baseline EVs are computed from training data only (no leakage).
- Batter rolling features use expanding windows shifted by 1 pitch (no look-ahead).
- All classifiers are calibrated with isotonic regression on the validation set.
- PLV scaling: `PLV = ((plv_raw − μ) / σ) × 1.5 + 5`, where μ and σ are from
  qualified pitchers in the training population.
- The outcome transition table in `src/plv_clone/utils/constants.py` is the single
  source of truth for all flag derivation.

---

*Built with Python 3.11+, pybaseball, LightGBM, scikit-learn, DuckDB, Typer, Streamlit, and SciPy.*

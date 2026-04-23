# PLV Clone — Changelog

All notable changes to this project are documented here.

---

## v1.0.0 — 2026-04-23 — First Usable Release

### Summary
First production-quality release. PLV and Process+ are validated on 2021-2024 Statcast data
and approved for exploratory leaderboard use.

### PLV Hardening Pass
- **Fixed PyArrow duplicate accumulation bug** (`existing_data_behavior="delete_matching"`).
  Raw pipeline re-runs were silently doubling feature rows by appending new UUID-named parquet
  files to existing hive partitions. All feature parquets were deduplicated in-place.
- **Fixed PLV scaling** from pitcher-level to pitch-level distribution.
  Old: pitcher-level std≈0.009 → amplification 166×, pitch range [-46, +49].
  New: pitch-level std≈0.054 → amplification 28×, pitch range [-3.5, +12.2] (0.55% outside [0,10]).
- **Fixed ECE computation** — rewrote `_expected_calibration_error` with `np.digitize`
  to avoid `sklearn.calibration_curve` shape mismatch on boundary bins.
- **Fixed `categorical_cols` double-pass TypeError** in all five sub-model `load()` paths.

### Process+ (new)
- **Decision+** — swing/take choice quality (all pitches). Reuses SwingModel + CalledStrikeModel.
- **Contact+** — contact execution quality (all swings). Uses ContactModel + FoulModel;
  model-predicted xwOBA for in-play prevents overlap with Power+.
- **Power+** — fair-ball damage above expectation (in-play only). Uses BattedBallValueModel.
- **Process+** — combined hitter metric (100-scale, 10-pt SD, same as wRC+/OPS+).

### Validation (2024, 413 qualified hitters, min 150 PA)
- Process+ mean=102.3, std=10.6, range=[60.1, 148.1]
- YoY 2023→2024: Decision+ r=0.740 | Contact+ r=0.790 | Power+ r=0.724 | Process+ r=0.646
- Spearman-Brown reliability: Decision+ ≥0.70 at 50 PA | Contact+ at 25 PA | Power+ at 100 PA
- Top hitters pass sanity check: Judge, Ohtani, Soto, Álvarez, Tatís Jr, Ozuna, Witt, Rooker, Guerrero

### Infrastructure
- Added `plv train-process` and `plv score-process` CLI commands
- Added `scripts/run_process_review.py` review packet generator
- PLV review packet: `scripts/run_plv_review.py`

---

## Pre-release (2026-04-01 to 2026-04-22)

Initial build: data ingestion, feature engineering, five PLV sub-models, PLV scoring,
pitcher leaderboards, PLV review script. Approved for internal use after PLV hardening pass.

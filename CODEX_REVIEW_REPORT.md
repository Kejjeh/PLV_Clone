# Codex Review Report — `plv_clone`

## Scorecard

| Area | Score | Notes |
| --- | ---: | --- |
| Code quality | 6/10 | Core model path is disciplined; dashboard/export layer has growing duplication and coupling. |
| Test coverage | 5/10 | Core ingestion/features/contracts are covered, but several pipelines and app integrations have no direct tests. |
| Dashboard UX | 5/10 | Analytical surface is rich, but top-level navigation and hardcoded season wiring increase cognitive load. |
| Pipeline robustness | 7/10 | Leakage controls are generally sound; schema enforcement and post-write mutation are weaker than they should be. |
| Production readiness (personal tool) | 6/10 | Reliable enough for daily use with manual supervision; not yet hardened against stale caches, dashboard drift, and auth/data-edge failures. |

## Scope

Audit covered:

- `src/plv_clone/` across `data`, `features`, `models`, `pipelines`, `fantasy`, `utils`
- `scripts/`
- `app/dashboard.py`
- `app/espn_connector.py`
- `pyproject.toml`
- `tests/`

Code changes made during this review were intentionally minimal:

- `app/espn_connector.py`
- `tests/test_espn_connector.py`

## A. Code Quality & Maintainability

### P1 — export writers are duplicated across pipelines instead of centralized
- Files: [src/plv_clone/pipelines/build_exports.py](src/plv_clone/pipelines/build_exports.py), [src/plv_clone/pipelines/build_fantasy_exports.py](src/plv_clone/pipelines/build_fantasy_exports.py:256), [src/plv_clone/pipelines/build_leaderboards.py](src/plv_clone/pipelines/build_leaderboards.py:112)
- Lines: `build_exports.py:1084-1091`, `build_fantasy_exports.py:256-263`, `build_leaderboards.py:112-119`
- Finding: each pipeline rolls its own parquet/CSV writer even though `utils/io.py` already centralizes other persistence concerns.
- Risk: output drift, inconsistent logging, and uneven future schema enforcement.
- Recommended fix: add a shared CSV/parquet export helper in `plv_clone.utils.io` and route all export pipelines through it.

### P1 — fantasy export build mutates other exports after write, creating hidden coupling
- File: [src/plv_clone/pipelines/build_fantasy_exports.py](src/plv_clone/pipelines/build_fantasy_exports.py:161)
- Lines: `161-163`
- Finding: `build_fantasy_exports.run()` calls `enrich_outputs(year, cfg.outputs_dir)` after writing fantasy outputs.
- Paired file: [src/plv_clone/pipelines/enrich_outputs.py](src/plv_clone/pipelines/enrich_outputs.py:128)
- Lines: `128-145`
- Risk: hidden post-processing changes `pitcher_fantasy_YYYY.csv` and `master_hitter_YYYY.csv` in place, which complicates reproducibility and makes downstream debugging harder.
- Recommended fix: either move enrichment into the pipeline that owns each artifact or version the enriched outputs explicitly.

### P1 — dashboard contains repeated styling and signal-mapping logic
- File: [app/dashboard.py](app/dashboard.py:52)
- Lines: `52-56`, `1495-1499`, `150-153`
- Finding: signal color maps and rank maps are defined more than once.
- Risk: reporting drift when a tier label or color changes in one place but not another.
- Recommended fix: hoist dashboard display maps into one shared module-level constant block.

### P2 — dead or orphaned code remains in active tree
- File: [scripts/fetch_savant_rolling.py](scripts/fetch_savant_rolling.py:327)
- Lines: `327-362`
- Finding: `_compute_delta()` is defined but never used.
- File: [src/plv_clone/pipelines/batscore_merge.py](src/plv_clone/pipelines/batscore_merge.py)
- Finding: no references from CLI, scripts, dashboard, or tests.
- Risk: low immediate correctness risk, but raises maintenance cost and weakens confidence about which code paths are live.
- Recommended fix: remove or explicitly document as experimental/unwired.

### P2 — exception handling is often too broad in dashboard/export helpers
- Files: [app/dashboard.py](app/dashboard.py:89), [src/plv_clone/pipelines/build_exports.py](src/plv_clone/pipelines/build_exports.py:646), [src/plv_clone/pipelines/build_fantasy_exports.py](src/plv_clone/pipelines/build_fantasy_exports.py:107)
- Lines: many `except Exception` blocks
- Finding: some broad catches are appropriate for UI resilience, but several cache/network helpers silently downgrade failures to warnings.
- Risk: stale or partially enriched data can look “healthy” in the UI.
- Recommended fix: reserve broad catches for explicitly non-critical enrichments and log source, year, and fallback path consistently.

### P2 — magic season values are hardcoded in dashboard
- File: [app/dashboard.py](app/dashboard.py:141)
- Lines: `141`, `1465`, `2132-2140`, `2207`, `2238-2240`, `2270`, `2337`, `2406-2415`, `2466-2467`
- Finding: several fantasy/team/wire flows hardcode `2026` instead of using the active year.
- Risk: dashboard drift across seasons and surprising mixed-year views.
- Recommended fix: isolate “current-season only” views behind one helper and make year choice explicit in captions.

## B. Pipeline Architecture

### Dependency graph

Observed effective sequence:

1. `pull_statcast_range()` in `data/ingest_statcast.py`
2. `clean_statcast()` in `data/clean_statcast.py`
3. feature engineering via `pitch_features`, `context_features`, `batter_features`
4. `train_plv.py`
5. `score_plv.py`
6. `train_process_plus.py`
7. `score_process_plus.py`
8. `build_exports.py`
9. `build_fantasy_exports.py`
10. `build_target_boards.py`
11. dashboard / scripts consume `data/outputs`

### P1 — schema enforcement exists, but export-time enforcement is inconsistent
- Files: [src/plv_clone/data/schemas.py](src/plv_clone/data/schemas.py:171), [src/plv_clone/pipelines/build_pitch_dataset.py](src/plv_clone/pipelines/build_pitch_dataset.py:27), [src/plv_clone/pipelines/build_exports.py](src/plv_clone/pipelines/build_exports.py), [src/plv_clone/pipelines/build_fantasy_exports.py](src/plv_clone/pipelines/build_fantasy_exports.py)
- Finding: `validate_schema()` is defined centrally, but export pipelines generally do not validate their output shape before writing.
- Risk: dashboard contract breakage shows up late, often as UI failures instead of pipeline failures.
- Recommended fix: add lightweight pre-write validation hooks for high-value exports (`master_hitter`, `master_pitcher`, fantasy outputs, target boards).

### P1 — `validate_schema()` only checks presence, not dtype stability
- File: [src/plv_clone/data/schemas.py](src/plv_clone/data/schemas.py:171)
- Lines: `171-180`
- Finding: despite the module’s role as schema authority, validation only checks missing columns.
- Risk: dtype drift can still break joins, formatting, and dashboard filters silently.
- Recommended fix: extend validation with optional dtype expectations for the highest-risk columns (`player_id`, dates, numeric metric columns).

### P1 — build pitch dataset imports validation constants but does not enforce feature schema post-build
- File: [src/plv_clone/pipelines/build_pitch_dataset.py](src/plv_clone/pipelines/build_pitch_dataset.py:27)
- Lines: `27`, `101-121`
- Finding: `validate_schema` and `FEATURE_COLS_PLV` are imported, but no validation call is made before writing feature parquet.
- Risk: missing engineered columns can survive until model training or scoring.
- Recommended fix: call `validate_schema(feat_df, FEATURE_COLS_PLV, ...)` before write, or explicitly validate the full expected feature contract.

### P2 — `clean_statcast()` docstring promises schema validation, but implementation only hard-fails on pitch-key columns
- File: [src/plv_clone/data/clean_statcast.py](src/plv_clone/data/clean_statcast.py:57)
- Lines: `57`, `82-91`
- Finding: docstring says “Validate output schema,” but current code performs only a soft presence check plus a hard key-column check.
- Risk: misleading guarantees for downstream callers.
- Recommended fix: either tighten implementation to use `CLEAN_REQUIRED_COLS` or weaken docstring language to match actual behavior.

### Pipeline parallelism assessment

Safe to parallelize after prerequisites:

- `score_plv` and `score_process_plus` are not parallel from cold start because `score_process_plus` depends on trained PLV artifacts, but once model artifacts exist both seasonal scoring jobs for different years are parallel-friendly.
- `build_target_boards` and `build_fantasy_exports` can run in parallel only after `build_exports` completes for the same year.

Must remain sequential:

- ingest → clean/features → model train
- `build_exports` before dashboard-oriented consumers
- `build_exports` before `build_target_boards`
- `build_exports` before `build_fantasy_exports`

No meaningful circular imports were observed in the core scoring path, but the dashboard is tightly coupled to output schemas.

### Are `build_exports.py` and `build_fantasy_exports.py` merge candidates?

Recommendation: no full merge.

- They overlap in I/O style and export writing patterns.
- They do not share enough domain logic to justify a single pipeline.
- Better move: extract shared helper layers for writing, metadata, and common loader/cache utilities.

## C. Model Layer

### Are the models used downstream?

Yes, the core model chain is live:

- PLV submodels: `SwingModel`, `CalledStrikeModel`, `ContactModel`, `FoulModel`, `BattedBallValueModel`
- Hitter components: decision/contact/power values feeding `ProcessPlusModel`

These are consumed in:

- [src/plv_clone/models/plv_model.py](src/plv_clone/models/plv_model.py)
- [src/plv_clone/models/process_plus_model.py](src/plv_clone/models/process_plus_model.py)
- [src/plv_clone/pipelines/score_plv.py](src/plv_clone/pipelines/score_plv.py)
- [src/plv_clone/pipelines/score_process_plus.py](src/plv_clone/pipelines/score_process_plus.py)
- downstream exports and dashboard views

### P2 — PLV blended shrinkage lives in fantasy projection layer, not PLV model layer
- File: [src/plv_clone/fantasy/pitcher_points.py](src/plv_clone/fantasy/pitcher_points.py:219)
- Lines: `219-245`
- Finding: Bayesian `plv_blended` shrinkage is implemented in pitcher fantasy projection, not in `models/plv_model.py`.
- Risk: low correctness risk, but terminology can mislead maintainers expecting “PLV blended” to be a model-layer artifact.
- Recommended fix: document this clearly in methodology/docs; do not move it unless you want `plv_blended` to become a first-class exported model metric.

### `calibration.py` status

Not orphaned.

- File: [src/plv_clone/models/_base_lgbm.py](src/plv_clone/models/_base_lgbm.py:21)
- Lines: `21`, `126`
- Finding: classifier calibration is wired via the base LightGBM wrapper and fit on held-out validation data.

### `evaluation.py` status

Not orphaned.

- Files: [src/plv_clone/pipelines/train_plv.py](src/plv_clone/pipelines/train_plv.py), [scripts/run_plv_review.py](scripts/run_plv_review.py:189)
- Finding: evaluation helpers are used in training review and report generation, not dead code.

## D. Data Layer

### `clean_statcast.py` vs `ingest_statcast.py`

Boundary is clear and well chosen:

- ingest: remote pull, chunking, manifest reconciliation, partitioned raw parquet
- clean: description normalization, flags, dedupe, pitch grouping, imputation

This separation is one of the cleaner parts of the repo.

### P2 — position handling is season-snapshot based, so freshness depends on cache refresh cadence
- File: [src/plv_clone/data/player_positions.py](src/plv_clone/data/player_positions.py)
- Finding: multi-position eligibility is handled reasonably via yearly snapshots and OF collapsing, but in-season role changes only surface when the cached position artifact is refreshed.
- Risk: minor dashboard/fantasy-position drift during active season.
- Recommended fix: document refresh assumptions and optionally add cache-age metadata to position artifacts.

### `.copy()` / SettingWithCopy risk

Core pipeline code is mostly disciplined here. The bigger SettingWithCopy exposure is in dashboard shaping code, not in model training.

No critical leakage-inducing slice mutation bug stood out in the core data path.

## E. Test Coverage Gaps

### P1 — several important pipelines have little or no direct unit coverage
- Files:
  - [src/plv_clone/pipelines/build_fantasy_exports.py](src/plv_clone/pipelines/build_fantasy_exports.py)
  - [src/plv_clone/pipelines/build_leaderboards.py](src/plv_clone/pipelines/build_leaderboards.py)
  - [src/plv_clone/pipelines/score_process_plus.py](src/plv_clone/pipelines/score_process_plus.py)
  - [src/plv_clone/pipelines/train_process_plus.py](src/plv_clone/pipelines/train_process_plus.py)
  - [src/plv_clone/pipelines/enrich_outputs.py](src/plv_clone/pipelines/enrich_outputs.py)
  - [scripts/fetch_savant_rolling.py](scripts/fetch_savant_rolling.py)
  - [app/espn_connector.py](app/espn_connector.py) before this review
- Risk: regressions in the daily-user workflows are more likely to escape CI than core feature/model regressions.
- Recommended fix: add small targeted tests for export enrichment, Savant merge semantics, and external-connector error handling.

### P1 — no end-to-end sample-data integration test
- Files: `tests/` suite overall
- Finding: there is no single test that runs synthetic data through the full feature → score → export path.
- Risk: contract mismatches between layers can survive until manual runs.
- Recommended fix: add one reduced-size integration test that builds a minimal year slice and verifies the final export set.

### Schema-contract tests assessment

Current contract tests are useful for column presence and downstream stability:

- [tests/test_contract_schemas.py](tests/test_contract_schemas.py)
- [tests/test_board_schema.py](tests/test_board_schema.py)

But they do not fully enforce dtypes because the underlying schema layer does not.

## Performance & Caching Audit

### Cached loaders found in dashboard

- ESPN loaders: `ttl=3600`
  - [app/dashboard.py](app/dashboard.py:84)
  - [app/dashboard.py](app/dashboard.py:93)
  - [app/dashboard.py](app/dashboard.py:112)
  - [app/dashboard.py](app/dashboard.py:121)
- local output loaders: `ttl=300`
  - [app/dashboard.py](app/dashboard.py:394)
  - [app/dashboard.py](app/dashboard.py:401)
  - [app/dashboard.py](app/dashboard.py:408)
  - [app/dashboard.py](app/dashboard.py:415)
  - [app/dashboard.py](app/dashboard.py:422)
  - [app/dashboard.py](app/dashboard.py:429)
  - [app/dashboard.py](app/dashboard.py:436)
  - [app/dashboard.py](app/dashboard.py:443)
- Savant rolling loaders: `ttl=3600`
  - [app/dashboard.py](app/dashboard.py:452)
  - [app/dashboard.py](app/dashboard.py:462)

### P1 — ESPN cache TTL is too long for live roster/free-agent workflow
- File: [app/dashboard.py](app/dashboard.py:84)
- Lines: `84-121`
- Finding: roster/free-agent/standings caches live for 3600 seconds.
- Risk: user sees stale roster or waiver state for up to an hour.
- Recommended fix: shorten ESPN TTLs to roughly 300–600 seconds.

### P1 — one uncached CSV load still happens inside a render path
- File: [app/dashboard.py](app/dashboard.py:1769)
- Lines: `1769-1772`
- Finding: `pitch_type_leaderboard.csv` is read directly with `pd.read_csv()` inside Player View.
- Risk: unnecessary rerender cost and inconsistent caching story.
- Recommended fix: hoist to a cached loader like the rest of the output files.

### Heaviest data loads

Based on local output sizes, the three heaviest dashboard-facing artifacts are:

1. `plv_rolling_YYYY.csv`
2. `process_plus_rolling_YYYY.csv`
3. `hitter_fantasy_YYYY.csv` / `master_hitter_YYYY.csv` depending season

These are all behind `@st.cache_data`, which is the correct pattern.

### Top-level navigation recommendation

Keep `st.sidebar.radio` for top-level navigation.

- File: [app/dashboard.py](app/dashboard.py:480)
- Reason: Streamlit tabs render all tab bodies on rerun, while the radio branch only executes one view path.
- Use `st.tabs()` only inside a selected page for grouped subviews.

## Dashboard Consolidation Audit

### Current top-level structure

- `Hitters`
- `Pitchers`
- `Rolling Trends`
- `Target Boards`
- `Player View`
- `Hitter Fantasy`
- `Pitcher Fantasy`
- `My Team`
- `Wire Report`
- `SP Starts`
- `Matchup`
- `Trade Analyzer`

Source: [app/dashboard.py](app/dashboard.py:477)

### Consolidation answers

1. `Hitter Fantasy` / `Pitcher Fantasy`
   - Yes, they share enough shape with `Hitters` / `Pitchers` to become subtabs inside those pages.

2. `Target Boards`
   - Not redundant, but too narrow to justify its own top-level page. Better as entity-specific subtabs or a waiver-focused section.

3. `SP Starts`
   - Too narrow for a standalone top-level page. Better as a `Pitchers` subtab or a `Waiver/SP Starts` subtab.

4. `Matchup`
   - Conceptually belongs under `My Team`; it is roster-context analysis, not a peer to global leaderboards.

5. `Wire Report`
   - Best kept as a dedicated waiver-oriented section with subtabs (`Hitters | SP | RP`) rather than folded into a generic board page.

See `CONSOLIDATION_PROPOSAL.md` for the recommended hybrid structure.

## Task 4 Review Outcomes

### 1. `fetch_savant_rolling.py` multi-bucket merge
- Status: not reproduced as a current bug
- File: [scripts/fetch_savant_rolling.py](scripts/fetch_savant_rolling.py:388)
- Lines: `388-403`
- Reason: the pivot is built from the concatenated set of available buckets and merged left from the 50-PA slice; players missing 250 PA are not dropped by that logic.
- No code change made.

### 2. `build_target_boards.py` thresholds vs dashboard `_waiver_score`
- Status: no material divergence found
- Files:
  - [src/plv_clone/pipelines/enrich_outputs.py](src/plv_clone/pipelines/enrich_outputs.py:19)
  - [app/dashboard.py](app/dashboard.py:153)
- Reason: the dashboard maps existing labels to ranks; it does not reimplement the label thresholds.
- No code change made.

### 3. `gen_leaderboards.py` output path helper
- Status: prompt appears stale
- File: [scripts/gen_leaderboards.py](scripts/gen_leaderboards.py:25)
- Lines: `25-38`
- Reason: it already uses `CFG.outputs_dir / f"review_{year}"`.
- No code change made.

### 4. `app/dashboard.py` trade analyzer duplicate rows for two-way players
- Status: not reproduced in current code
- File: [app/dashboard.py](app/dashboard.py:2495)
- Lines: `2495-2528`
- Reason: `_ta_build_side()` checks hitter match first and `continue`s, so a single selected name is not appended twice from hitter and pitcher frames.
- No code change made.

### 5. `espn_connector.py` expired-cookie failure handling
- Status: confirmed and fixed
- File: [app/espn_connector.py](app/espn_connector.py:23)
- Lines: `23-77`
- Fix: `_get_league()` now converts auth-looking failures into a clear cookie-refresh message and generic failures into a cleaner connection error.
- Test added: [tests/test_espn_connector.py](tests/test_espn_connector.py)

## Implemented Fixes

### `app/espn_connector.py`
- Added auth-failure keyword detection for ESPN cookie/session errors.
- Replaced raw exception bubbling with user-facing `RuntimeError` messages suitable for Streamlit display.

### `tests/test_espn_connector.py`
- Added regression coverage for:
  - auth-looking failures → cookie refresh guidance
  - generic failures → clean connection error message

## Recommended Next Steps

1. Add export-time schema validation for `master_hitter`, `master_pitcher`, fantasy outputs, and target boards.
2. Reduce ESPN dashboard cache TTL to 5–10 minutes.
3. Hoist uncached `pitch_type_leaderboard.csv` loading into a cached helper.
4. Remove or quarantine dead/orphaned code (`_compute_delta`, `batscore_merge.py`).
5. Add one end-to-end synthetic integration test covering score → export → board contracts.

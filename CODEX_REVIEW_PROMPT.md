# Codex Project Review Prompt — plv_clone

## Context

This is a Python fantasy baseball analytics project (`plv-clone`) that:
- Ingests MLB Statcast pitch-level parquet data
- Computes Pitching (PLV/PLV Blended) and Hitter (Process+/Decision+/Power+/K-Avoid+) proprietary metrics
- Produces target boards and waiver wire signal tiers for ESPN fantasy leagues
- Pulls live rolling xwOBA data from Baseball Savant
- Connects to ESPN fantasy API (cookie auth) for league roster context
- Serves everything through a 2,595-line Streamlit dashboard (`app/dashboard.py`)

**Stack**: Python 3.11, LightGBM, Pandas/PyArrow/DuckDB, Streamlit + Plotly, typer CLI, hatchling build.

---

## Review Task 1: Full Project Architecture Audit

Please do an in-depth review of the entire project. Read every file in:
- `src/plv_clone/` (all subpackages: data, features, models, pipelines, fantasy, utils)
- `scripts/` (fetch_savant_rolling.py, gen_leaderboards.py, refresh_data.sh, run_plv_review.py, run_process_review.py, validate_outputs.py)
- `app/dashboard.py` and `app/espn_connector.py`
- `pyproject.toml`
- `tests/`

For each layer, evaluate and report:

### A. Code Quality & Maintainability
- Duplication: functions/logic that appear in multiple files and should be centralized
- Dead code: functions/imports/variables defined but never used
- Inconsistent patterns: e.g. some pipelines use one I/O helper, others roll their own
- Type annotation completeness (especially pipeline entrypoints and public functions)
- Error handling: places where silent failures or bare `except` could mask bugs
- Magic numbers/strings that should be constants in `utils/constants.py`

### B. Pipeline Architecture
- Is the dependency graph between pipelines clear? (ingest → clean → feature → model → export → fantasy → target board → dashboard)
- Are there circular imports or tight coupling between layers?
- Which pipelines are safe to run in parallel vs. must be sequential?
- Are the parquet output schemas validated at write time? (see `data/schemas.py` — is it actually enforced?)
- The `build_exports.py` and `build_fantasy_exports.py` seem to do overlapping work — are they candidates for merging?

### C. Model Layer
- Are all 8 models (PLV, Process+, Decision+, Power+, K-Avoid+, called strike, contact/whiff, batted ball value) actually being used downstream in exports/dashboard?
- Is the Bayesian shrinkage for PLV Blended implemented in `plv_model.py` or in a pipeline step?
- `calibration.py` — is it wired into any training pipeline, or is it orphaned?
- `evaluation.py` — is it used by any test or pipeline, or standalone?

### D. Data Layer
- `clean_statcast.py` vs `ingest_statcast.py` — is the boundary clear?
- `player_positions.py` — how does it handle multi-position players and in-season roster moves?
- Are there any places where pandas `.copy()` is missing on slices (SettingWithCopyWarning risk)?

### E. Test Coverage Gaps
- Review all test files in `tests/`. Which pipelines/models have zero test coverage?
- Are the schema tests in `test_contract_schemas.py` and `test_board_schema.py` actually enforcing the right columns/dtypes?
- Is there an integration test that runs the full pipeline end-to-end with sample data?

---

## Review Task 2: Dashboard Consolidation

The dashboard currently has **12 top-level tabs**:
```
Hitters | Pitchers | Rolling Trends | Target Boards | Player View |
Hitter Fantasy | Pitcher Fantasy | My Team | Wire Report | SP Starts | Matchup | Trade Analyzer
```

With subtabs under several of them. The goal is to **reduce cognitive load without losing any analytical surface** — fewer top-level pages, more logical groupings via subtabs/expanders/columns.

### Proposed consolidation directions to evaluate:

**Option A: 5-tab structure**
```
1. Leaderboards      (was: Hitters + Pitchers + rolling leaderboard views)
2. Trends            (was: Rolling Trends — keep 4 subtabs)
3. Player View       (was: Player View — already self-contained)
4. Fantasy Hub       (was: Hitter Fantasy + Pitcher Fantasy + Target Boards merged with subtabs)
5. My Team           (was: My Team + Wire Report + SP Starts + Matchup + Trade Analyzer)
```

**Option B: 6-tab structure**
```
1. Hitters           (merge current Hitters tab + Hitter Fantasy subtab + hitter Target Board)
2. Pitchers          (merge current Pitchers tab + Pitcher Fantasy subtab + pitcher Target Board)
3. Trends & Signals  (Rolling Trends + Convergence scatter + xwOBA board)
4. Player View       (unchanged)
5. Wire & Adds       (Wire Report + Target Boards + SP Starts)
6. My Team           (My Team + Matchup + Trade Analyzer)
```

For each option, tell me:
- Which views would need to be converted from full-page to subtab/expander/column
- Any data that's currently fetched per-tab that could be hoisted to a shared `@st.cache_data` loader
- Whether the `st.sidebar.radio` navigation pattern should be replaced with `st.tabs()` (Streamlit native tabs widget) for the inner groupings

### Specific consolidation questions:
1. `Hitter Fantasy` and `Pitcher Fantasy` tabs — do they share enough structure with `Hitters`/`Pitchers` tabs that they can become a subtab ("Fantasy View" toggle) rather than separate top-level tabs?
2. `Target Boards` tab — is it meaningfully different from a filtered view of Hitters/Pitchers + Wire Report, or is it redundant?
3. `SP Starts` tab — this is a narrow view (just two-start pitchers + schedule). Should it be a sidebar widget or collapsible panel on the Pitchers tab rather than its own top-level tab?
4. `Matchup` tab — what data does it actually show? Could it live as a section within `My Team`?
5. `Wire Report` hitters vs. pitchers — should this be 2 subtabs inside a merged "Waiver Wire" section of `My Team`, or keep as its own tab?

---

## Review Task 3: Performance & Caching Audit

The dashboard is 2,595 lines. Identify:
- All `@st.cache_data` calls — are TTLs appropriate? (e.g. ESPN roster data probably should be 5–10 min, not 3600s)
- Are there any DataFrame loads inside render loops (inside `if active_tab ==` blocks) that are NOT cached?
- Identify the 3 heaviest data loads (by estimated file size / row count) and confirm they all have `@st.cache_data`
- Any place where a large DataFrame is passed into a function and then filtered — should the filter happen before the cache boundary instead?
- Is there any Plotly figure being regenerated every rerender that could be cached?

---

## Review Task 4: Specific Code Issues to Fix

After your read-through, please implement fixes for any of the following if you find them:

1. **`fetch_savant_rolling.py`**: The `run()` function pivots on `xwoba_now` from multiple bucket sizes (50/100/250 PA). Confirm the merge logic correctly handles players who appear in some buckets but not others — there should be no rows dropped for a player just because they don't have 250 PA yet. Add a test in `tests/` for this case.

2. **`build_target_boards.py`**: Confirm the signal tier logic (`Top Target` / `Strong Add` / `Watchlist` / `Pass` / `Too Small`) uses consistent thresholds with what `_waiver_score()` in dashboard.py expects. If they diverge, standardize the thresholds into `utils/constants.py`.

3. **`gen_leaderboards.py`**: The pitch type leaderboard outputs `pitch_type_leaderboard.csv` to `data/outputs/review_{year}/`. This should go through the same output path helper used by `build_exports.py` (`cfg.outputs_dir`). Refactor to use the config.

4. **`app/dashboard.py` — `_ta_build_side()`**: The Trade Analyzer helper fuzzy-merges player names against both hitter and pitcher model DataFrames. If a player name matches in both (two-way players), it may produce duplicate rows. Add deduplication by player_id or player_name, keeping the row with the higher `signal_tier` rank.

5. **`espn_connector.py`**: Audit the cookie-based auth flow. If the `espn_s2` or `SWID` cookies are expired, the connector should fail gracefully with a clear user-facing error message rather than a stack trace in the Streamlit UI.

---

## Deliverables

Please produce:

1. **`CODEX_REVIEW_REPORT.md`** in the project root — your full audit findings organized by the sections above (A–E + Performance + Consolidation). For each finding: file path, line number(s) if applicable, severity (P0/P1/P2), and recommended fix.

2. **`CONSOLIDATION_PROPOSAL.md`** in the project root — a concrete recommendation for which consolidation option (A, B, or a hybrid you design) to adopt, with a before/after tab map, estimated lines-of-code delta, and a migration checklist.

3. **Direct code fixes** for all Task 4 items you confirm are real issues. Make the fixes — don't just report them.

4. A summary at the top of `CODEX_REVIEW_REPORT.md` with a **scorecard**: 
   - Code quality (1–10)
   - Test coverage (1–10)  
   - Dashboard UX (1–10)
   - Pipeline robustness (1–10)
   - Overall readiness for a "production" personal tool (1–10)

---

## Notes for Codex

- This is a personal fantasy baseball tool, not a commercial product. "Production readiness" means reliable daily use, not enterprise SLAs.
- The metric names (PLV, Process+, PLV Blended, proc_plus_positional, xwoba_delta) are domain-specific — don't suggest renaming them.
- The ESPN API integration uses unofficial cookie-based auth — this is intentional and not a security concern for a personal tool.
- Prioritize findings that affect daily workflow reliability (data freshness, silent failures, dashboard crashes) over style issues.
- The `data/outputs/` directory is gitignored — all parquet/CSV outputs are generated locally by running the pipeline.

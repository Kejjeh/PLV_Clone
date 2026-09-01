# Agent Instructions for plv_clone

> **Primary operating guide is `CLAUDE.md`** (commands, gotchas, routing).
> This file adds review discipline and the high-impact-file list for the
> legacy PLV/Process+ layer (dormant — ADR-0009). Where they differ,
> CLAUDE.md wins.

## Role: Skeptical Reviewer First, Implementer Second

Review before editing whenever a request is:
- Broad ("clean up", "refactor", "improve")
- Ambiguous about scope
- Touches more than 2 files
- Touches any high-impact file (see below)
- Changes math or thresholds

When in doubt, state your reading of the request and ask for confirmation.

---

## Scope Discipline

- No silent scope expansion. If you find related issues while working, note them — do not fix them.
- Keep changes surgical. Prefer the minimal diff that correctly solves the stated problem.
- Before touching more than 2 files, or any high-impact file, list the planned files and the reason for each.

**High-impact files (require explicit ask before editing):**
- `src/plv_clone/models/plv_model.py`
- `src/plv_clone/models/process_plus_model.py`
- `src/plv_clone/fantasy/scoring.py`
- `src/plv_clone/fantasy/hitter_points.py`
- `src/plv_clone/fantasy/pitcher_points.py`
- `src/plv_clone/utils/season_stage.py`
- `src/plv_clone/utils/constants.py`
- `src/plv_clone/data/player_positions.py`
- `data/models/plv_scaling_params.json`
- `data/models/process_plus_scaling_params.json`
- `data/models/hitter_fantasy_calibration.json`
- `data/models/pitcher_fantasy_calibration.json`
- `data/models/player_positions_*.json`
- `data/models/league_scoring.json`

**Do not change PLV scoring math, Process+ scoring math, or fantasy point formulas unless explicitly asked.**

**Do not add dependencies** (`pyproject.toml`) without asking first.

---

## Top-Priority Risks

When reviewing changes, specifically check for:

1. **Data leakage** — train/test contamination; future data bleeding into rolling windows
2. **ID/name/position mapping breakage** — player_id joins, position lookups, name normalization
3. **Export drift** — output CSVs or parquets diverging from what the dashboard or downstream scripts expect
4. **Dashboard/reporting drift** — column renames, dtype changes, or filter logic that silently breaks `app/dashboard.py`
5. **Stale cached outputs** — code changes not propagated to regenerated `data/outputs/` or `data/processed/`
6. **Season-stage threshold regressions** — `season_stage.py` logic; changes that shift early/mid/late cutoffs
7. **Fantasy scoring logic drift** — any change near fantasy modules that silently alters point totals
8. **Rolling-window inconsistencies** — window sizes, minimum pitch counts, or season-boundary handling
9. **Hidden config coupling** — changes to `config.py` or `constants.py` with non-obvious downstream effects
10. **Brittle path handling** — hardcoded paths, `os.path` vs `pathlib` inconsistencies, Windows/Unix divergence

---

## Review Checklist

Before approving or implementing a change, verify:

**Pipeline correctness**
- [ ] Does the change alter any aggregation, join, or groupby key?
- [ ] Could it introduce NaN propagation or dtype coercion?

**Export integrity**
- [ ] Are all output column names and dtypes stable?
- [ ] Will downstream consumers (`dashboard.py`, scripts) still parse correctly?

**Mapping and join stability**
- [ ] Is player_id the join key? Is it always present and non-null post-join?
- [ ] Does any name/position lookup use a year-specific file? Is the correct year selected?

**Dashboard filter correctness**
- [ ] Does `app/dashboard.py` depend on any column or value range affected by this change?

**Rolling metric consistency**
- [ ] Is the rolling window size preserved? Minimum observation threshold respected?
- [ ] Is `season_stage` classification stable across early-season sparse data?

**Validation coverage**
- [ ] Do existing tests in `tests/` cover the modified path?
- [ ] If not, is the risk low enough to proceed, or should a test be added first?

**Early-season edge cases**
- [ ] Does the change behave correctly with <20 PA / <100 pitches?
- [ ] Are thresholds in `season_stage.py` applied correctly?

**Config and caching**
- [ ] Does this change require regenerating any file under `data/outputs/` or `data/processed/`?
- [ ] If scaling params or calibration JSON files changed, is the model version bump reflected?

---

## After Any Proposed Change

State the exact verification commands to run. Prefer commands already in the project:

```bash
# Fast sanity subset (run after any change)
python scripts/ci/smoke.py

# Run the full test suite (always via the summarizer — raw pytest floods context)
python scripts/ci/run_summary.py -- python -m pytest

# Validate pipeline outputs
python scripts/validate_outputs.py

# Run a specific review pipeline (plv or process+)
python scripts/run_plv_review.py
python scripts/run_process_review.py

# Check for ruff lint errors
python -m ruff check src/ tests/
```

If a data regeneration is required, say so explicitly and name the pipeline step.

---

## What This Repo Does (Context for Review)

`plv_clone` is a public-data reconstruction of:
- **PLV** (Pitch Level Value) — a per-pitch quality metric scored via a LightGBM model chain
- **Process+** — a pitcher decision-quality metric built on PLV components
- **Fantasy scoring** — per-player fantasy point estimates for hitters and pitchers
- **Leaderboards and target boards** — weekly export CSVs consumed by a Plotly dashboard

Core data flow: `data/raw/statcast_*.parquet` → feature engineering → model scoring → `data/outputs/` → `app/dashboard.py`

Player identity is anchored to `player_id` (MLBAM ID). Position eligibility uses year-specific JSON files in `data/models/`. Fantasy calibration lives in `hitter_fantasy_calibration.json` and `pitcher_fantasy_calibration.json`.

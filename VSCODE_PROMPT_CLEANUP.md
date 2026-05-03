# VS Code / Codex Task Prompt — Cleanup & Position Filter Fix

## Context

`plv_clone` is a Python fantasy baseball analytics project. The dashboard
(`app/dashboard.py`) serves 6 consolidated tabs backed by Streamlit. The data
pipeline lives in `src/plv_clone/`. Position eligibility for hitters is built
by `src/plv_clone/data/player_positions.py` → consumed by
`src/plv_clone/pipelines/build_exports.py` → displayed in
`app/dashboard.py`.

---

## Task 1 — Remove dead code

### 1a. Delete `_compute_delta()` from `scripts/fetch_savant_rolling.py`

**File:** `scripts/fetch_savant_rolling.py`

Find the function `_compute_delta` (approximately lines 327–362). It is
defined but never called anywhere in the repo. Delete it entirely (function
def + body). Confirm no call-sites exist with a grep before deleting.

### 1b. Remove `src/plv_clone/pipelines/batscore_merge.py`

**File:** `src/plv_clone/pipelines/batscore_merge.py`

Confirm it has zero import-sites or call-sites across the repo (grep for
`batscore_merge`). If confirmed unused, delete the file. Also remove any
reference to it in `src/plv_clone/pipelines/__init__.py` if present.

---

## Task 2 — Deduplicate `_BADGE_CSS` in the dashboard

**File:** `app/dashboard.py`

`_BADGE_CSS` is a dict mapping signal tier names to CSS strings. It is
currently defined at module level near the top of the file AND duplicated
inline inside the Target Boards section (look for `_bt_sig_map = {` around
the `bat_tracking_stars` board block).

**Fix:**
1. Keep the single module-level `_BADGE_CSS` definition (already at the top).
2. Find every other dict that maps the same five signal tier keys
   (`"Top Target"`, `"Strong Add"`, `"Watchlist"`, `"Pass"`, `"Too Small"`)
   to equivalent CSS strings — there should be at least one duplicate (`_bt_sig_map`).
3. Replace each duplicate with a reference to `_BADGE_CSS`.
4. Run `python -c "import ast; ast.parse(open('app/dashboard.py').read()); print('OK')"` to confirm syntax.

---

## Task 3 — Export-time schema validation

**Files to modify:**
- `src/plv_clone/pipelines/build_exports.py`
- `src/plv_clone/pipelines/build_fantasy_exports.py`
- `src/plv_clone/data/schemas.py` (read this first — `validate_schema()` is already defined here)

**Context:** `validate_schema(df, required_cols, context="")` already exists in
`schemas.py`. It raises or warns when required columns are missing. It is
currently called in `build_pitch_dataset.py` but not in the export pipelines.

**Fix:**

In `build_exports.py`, immediately before each of the following `to_csv` /
`to_parquet` write calls, add a `validate_schema()` call using the
appropriate required-column list:

| Artifact | Required columns to validate |
|---|---|
| `master_hitter_{year}.csv` | `["batter", "batter_name", "pa", "process_plus", "signal", "fantasy_positions"]` |
| `master_pitcher_{year}.csv` | `["pitcher", "player_name", "pitches", "plv", "signal"]` |

In `build_fantasy_exports.py`, validate before writing:

| Artifact | Required columns |
|---|---|
| `hitter_fantasy_{year}.csv` | `["batter", "batter_name", "pa", "core_fp_per_pa", "signal"]` |
| `pitcher_fantasy_{year}.csv` | `["pitcher", "player_name", "pitches", "fp_per_ip", "signal"]` |

**Behavior:** use `validate_schema()` in "warn" mode (not raise) so a
missing column produces a logged warning but does not abort the pipeline run.
Check the existing `validate_schema` signature to confirm the right kwarg for
warn-vs-raise.

---

## Task 4 — Fix position filter: primary position always grants eligibility

**Root cause:** `fantasy_positions` is built using a `min_games_for_eligibility`
threshold (default: 10 games started at that position). A player like Ivan
Herrera who is a catcher by primary MLB registration but is getting DH starts
this season may not have 10 GS at C yet — so he doesn't appear in the "C"
filter even though he is a catcher.

**Expected behavior:** A player's `primary_position` (their MLB-registered
defensive position) should always be included in their `fantasy_positions`
string, regardless of the games-started threshold. This matches how ESPN
actually grants eligibility (your primary position always qualifies).

**File to modify:** `src/plv_clone/data/player_positions.py`

**Function to modify:** `build_position_map()` (around line 238)

**Specific fix:** In the loop body, after `fantasy_sorted` is built from the
games-started threshold, add:

```python
# Primary defensive position always grants eligibility regardless of GS threshold
if norm_primary and norm_primary not in fantasy_set:
    _is_pitcher_pos = norm_primary in _PITCHER_RAW if "_PITCHER_RAW" in dir() else norm_primary in {"P", "SP", "RP"}
    if not cfg.exclude_pitchers or not _is_pitcher_pos:
        fantasy_set.add(norm_primary)
        fantasy_sorted = _sort_positions(list(fantasy_set))
```

Do this BEFORE the `rows.append({...})` call so that `fantasy_positions` and
`fantasy_positions_display` reflect the updated set.

**Also check:** `_normalize_position()` and `_PITCHER_RAW` — confirm the
right set name for pitcher positions in this file's namespace. Adjust the
pitcher-exclusion check accordingly.

**After the fix:**
1. Write or update a test in `tests/test_board_schema.py` or a new
   `tests/test_player_positions.py` that:
   - Constructs a minimal fielding-stats DataFrame where a player has
     `primary_position = "C"` but zero games started at C (all games at DH).
   - Calls `build_position_map()` (or the internal row-building logic) on it.
   - Asserts that `"C"` appears in the player's `fantasy_positions`.
2. Run `pytest tests/test_player_positions.py -v` (or equivalent) to confirm.

**Note:** After this code change, the `player_positions_{year}.json` cache
file will be stale. Delete `data/models/player_positions_2026.json` (or
wherever the cache lives per `cfg.models_dir`) and re-run
`plv build-exports 2026` to regenerate with the new logic.

---

## Verification

After completing all tasks, run:

```bash
python -m pytest tests/ -p no:cacheprovider --no-cov -q
python -c "import ast; ast.parse(open('app/dashboard.py').read()); print('dashboard syntax OK')"
python scripts/validate_outputs.py --year 2026
```

All 3 should pass without new failures. Report any new test failures or
warnings introduced by these changes.

---

## Notes

- Do not change any metric names, threshold values, or scoring math.
- The position cache path is `cfg.models_dir / f"player_positions_{year}.json"`.
  Mention in your summary which cache files need to be deleted and regenerated.
- The `_PITCHER_RAW` set in `player_positions.py` contains the raw position
  strings that map to pitcher roles — double-check its name before using it.

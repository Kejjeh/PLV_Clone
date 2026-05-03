# Dashboard Consolidation Proposal — `plv_clone`

## Recommendation

Adopt a hybrid structure closest to Option B, with **6 top-level pages**:

1. `Hitters`
2. `Pitchers`
3. `Trends & Signals`
4. `Player View`
5. `Waiver Wire`
6. `My Team`

This keeps the current performance advantage of `st.sidebar.radio` at the top level while reducing cognitive load from 12 pages to 6.

## Why not Option A as written?

Option A is cleaner conceptually, but `Fantasy Hub` becomes too heterogeneous:

- hitter fantasy
- pitcher fantasy
- target boards

Those views do not share enough interaction shape to feel natural in one page.

It also overloads `My Team` with both roster management and acquisition/discovery workflows.

## Why not keep the current 12-tab layout?

The current layout spreads closely related views across separate pages:

- `Hitters` vs `Hitter Fantasy`
- `Pitchers` vs `Pitcher Fantasy`
- `Target Boards` vs `Wire Report`
- `My Team` vs `Matchup` vs `Trade Analyzer`
- `SP Starts` as a narrow singleton page

That increases navigation cost more than it increases clarity.

## Proposed Before/After Map

### Current

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

### Proposed

#### 1. `Hitters`
Subtabs:
- `Leaderboard`
- `Fantasy`
- `Targets`

Moves:
- current `Hitters`
- current `Hitter Fantasy`
- hitter-facing slice of `Target Boards`

#### 2. `Pitchers`
Subtabs:
- `Leaderboard`
- `Fantasy`
- `Targets`
- `SP Starts`

Moves:
- current `Pitchers`
- current `Pitcher Fantasy`
- pitcher-facing slice of `Target Boards`
- current `SP Starts`

#### 3. `Trends & Signals`
Subtabs:
- `Rolling Trends`
- `Savant`
- `Convergence`

Moves:
- current `Rolling Trends`
- any cross-entity trend/convergence views now embedded in fantasy/wire tabs

#### 4. `Player View`
Subtabs:
- `Hitter`
- `Pitcher`

Moves:
- current `Player View` unchanged structurally

#### 5. `Waiver Wire`
Subtabs:
- `Hitters`
- `SP`
- `RP`
- `Boards`

Moves:
- current `Wire Report`
- current `Target Boards` summary/entry slice

#### 6. `My Team`
Subtabs:
- `Roster`
- `Matchup`
- `Trade Analyzer`

Moves:
- current `My Team`
- current `Matchup`
- current `Trade Analyzer`

## View Conversion Details

### Full-page → subtab conversions

- `Hitter Fantasy` → `Hitters > Fantasy`
- `Pitcher Fantasy` → `Pitchers > Fantasy`
- `SP Starts` → `Pitchers > SP Starts`
- `Matchup` → `My Team > Matchup`
- `Trade Analyzer` → `My Team > Trade Analyzer`
- `Target Boards` → split across `Hitters > Targets`, `Pitchers > Targets`, and `Waiver Wire > Boards`

### Full-page → expander/panel candidates

- narrow methodological notes
- low-frequency secondary tables inside `Target Boards`
- optional “Bat Tracking Detail” style views

## Option A vs Option B Evaluation

### Option A: 5 tabs

Pros:
- cleanest surface
- easiest to explain

Cons:
- `Fantasy Hub` becomes a grab bag
- `My Team` becomes too broad
- more unrelated code ends up in one branch, making `dashboard.py` harder to reason about

### Option B: 6 tabs

Pros:
- better entity alignment
- easier mental model for fantasy baseball workflow
- fits current code structure with less churn

Cons:
- still needs careful handling of `Target Boards` to avoid duplication

### Recommended hybrid

Use Option B as the base, but treat `Waiver Wire` as the main home for acquisition decisions and only keep entity-specific target views where they materially differ from wire filtering.

## Shared Cached Loaders to Hoist / Reuse

These should remain loader-level helpers, not per-tab one-offs:

- `load_hitters(year)`
- `load_pitchers(year)`
- `load_hitter_fantasy(year)`
- `load_pitcher_fantasy(year)`
- `load_board(name, year)`
- `load_savant_rolling_batters(year)`
- `load_savant_rolling_pitchers(year)`
- ESPN helpers:
  - `_load_espn_roster()`
  - `_load_espn_all_teams()`
  - `_load_espn_free_agents()`
  - `_load_espn_standings()`

Additional hoist recommended:

- add cached loader for `review_{year}/pitch_type_leaderboard.csv`

## Navigation Guidance

### Keep for top level

Use `st.sidebar.radio` for top-level page selection.

Reason:
- only one page branch executes per rerun
- avoids expensive multi-page render work
- matches current performance assumptions in a 2,500+ line dashboard

### Use for inner grouping

Use `st.tabs()` inside each top-level page for:

- `Hitters`
- `Pitchers`
- `Waiver Wire`
- `My Team`

This is where native tabs help without forcing full top-level recomputation.

## Estimated LOC Delta

Expected net change for the initial consolidation pass:

- `app/dashboard.py`: **-250 to -450 lines net**
- mostly from:
  - collapsing repeated page headers/filter blocks
  - moving repeated loader/format logic behind entity subtabs
  - reducing duplicated year-specific fantasy/wire scaffolding

This is not a “small diff” refactor. It should be staged.

## Migration Checklist

1. Create one shared “page-local state” helper for top-level filters.
2. Merge `Hitter Fantasy` into `Hitters` with a `Leaderboard | Fantasy | Targets` subtab set.
3. Merge `Pitcher Fantasy` and `SP Starts` into `Pitchers`.
4. Split `Target Boards` into entity-specific or waiver-specific subtabs.
5. Move `Matchup` and `Trade Analyzer` under `My Team`.
6. Add cached loader for `pitch_type_leaderboard.csv`.
7. Reduce ESPN TTLs from 3600s to ~300–600s.
8. Remove or isolate hardcoded `2026` paths where a season selector should apply.
9. Smoke-test every page branch on:
   - current season
   - older pre-bat-tracking season
   - no-ESPN-data path

## Lowest-Risk Refactor Order

If you want to implement this incrementally:

1. Merge `Hitter Fantasy` into `Hitters`
2. Merge `Pitcher Fantasy` + `SP Starts` into `Pitchers`
3. Move `Matchup` + `Trade Analyzer` into `My Team`
4. Re-home `Target Boards` / `Wire Report`
5. Clean up labels and duplicated formatting logic last

That order minimizes simultaneous movement of unrelated workflows.

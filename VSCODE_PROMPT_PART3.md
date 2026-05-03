# Claude VS Code — plv_clone Dashboard Part 3

## Context

This is a fantasy baseball analytics dashboard built in Streamlit (`app/dashboard.py`, currently ~2230 lines). The underlying Python package is `plv_clone` with a CLI (`plv <command>`). All output data lives in `data/outputs/`.

**What was recently added (do NOT redo these):**
- `app/espn_connector.py` — ESPN API integration with fuzzy name matching
- `scripts/fetch_savant_rolling.py` — pulls Baseball Savant rolling xwOBA leaderboard; outputs `data/outputs/savant_rolling_batters_2026.parquet` and `savant_rolling_pitchers_2026.parquet` (columns: `player_name`, `xwoba_l50`, `xwoba_l100`, `xwoba_l250`, `xwoba_then`, `xwoba_delta`, `fetch_date` for batters; `xwoba_against_l100bf`, `xwoba_against_l250bf`, `xwoba_against_then`, `xwoba_against_delta` for pitchers)
- Dashboard tabs already built: My Team, Wire Report, SP Starts, Matchup, xwOBA Trends (Savant), convergence scatter, multi-season career trajectory on Player View, waiver add_score on Wire Report

**Key data facts:**
- `hitter_fantasy_2026.csv` has 51 columns including: `batter_name`, `pa`, `process_plus`, `proc_plus_positional`, `decision_plus`, `k_avoidance_plus`, `power_plus`, `blend_weight`, `signal` (Top Target/Strong Add/Watchlist/Pass/Too Small), `risk_flag` (Chase Risk/K Risk/Power Flag), `sample_tier`, `core_fp_per_pa`, `full_fp_per_pa`, `xwoba_on_contact`, `xwoba_vs_expected`, `blast_rate`, `avg_swing_speed`, `fast_swing_rate`, `squared_up_rate`, `swing_count`, `est_k_rate`, `est_bb_rate`, `est_tb_rate`, `est_sb_rate`
- `pitcher_fantasy_2026.csv` has 34 columns including: `player_name`, `pitches`, `plv`, `plv_blended`, `plv_std`, `whiff_pct`, `cs_pct`, `xwoba_model`, `pitcher_role`, `est_k_per_ip`, `est_bb_per_ip`, `fp_per_ip`, `fp_per_start`, `fp_per_app`, `sv_hd_fp_per_162`, `signal`, `profile_flag`, `sample_tier`
- `data/outputs/review_2024/pitch_type_leaderboard.csv` has per-pitcher per-pitch-type: `pitcher`, `player_name`, `pitch_type`, `pitch_group`, `pitches`, `plv`, `plv_std`, `avg_velo`, `swing_rate`, `whiff_rate`, `e_xwoba_ip`, `plv_pctile`
- Signal badge CSS already defined in dashboard as `_BADGE_CSS`
- Helper `_fuzzy_merge(espn_df, model_df, model_name_col)` already exists in dashboard scope

---

## Tasks

### TASK 1 — Build pitch-type leaderboard for 2026

The CLI command `plv run-review <year>` generates `data/outputs/review_<year>/pitch_type_leaderboard.csv`. Run it:

```
plv run-review 2026
```

If that command does not exist, look at `scripts/run_process_review.py` and `src/plv_clone/cli.py` for how the 2024 review was generated, then replicate for 2026. The output should be `data/outputs/review_2026/pitch_type_leaderboard.csv` with the same schema as the 2024 version.

---

### TASK 2 — Add "Pitch Mix" section to Player View (Pitcher tab)

In `app/dashboard.py`, in the **Pitcher** subtab of the **Player View** tab, after the existing PLV metrics and rolling charts but before the multi-season trajectory, add:

```python
# ── Pitch Mix breakdown ───────────────────────────────────────────────
st.divider()
st.subheader("Pitch Mix — PLV by Pitch Type")
```

Load `data/outputs/review_2026/pitch_type_leaderboard.csv` (fall back to 2025, then 2024 if 2026 is missing). Filter to the current pitcher by MLBAM ID (`pitcher` column). Show a horizontal bar chart (Plotly) of PLV by pitch type, colored by pitch group (Fastball=blue, Breaking=orange, Offspeed=green). Each bar should show: pitch type label, PLV value, avg velo, whiff_rate, and pitch count. Sort descending by `pitches` (usage).

If fewer than 2 pitch types exist, show a plain table instead of chart. If no data exists, show `st.info("Pitch mix data not available for this pitcher.")`.

Also add a sortable table below the chart with columns: `pitch_type`, `pitch_group`, `pitches`, `plv`, `avg_velo`, `whiff_rate`, `swing_rate`, `e_xwoba_ip`, `plv_pctile` — formatted to 3 decimal places.

---

### TASK 3 — Add Trade Analyzer tab

Add **"Trade Analyzer"** to the sidebar `tab_labels` list in `app/dashboard.py`.

The tab should:

1. Load all ESPN teams via the existing `_load_espn_all_teams()` cached function.
2. Show two `st.selectbox` dropdowns side by side ("Give" team, "Receive" team) defaulting to the user's team ("New York Ligers") on the left.
3. Under each team selector, show a multiselect of that team's players (from the all-teams data). The user picks which players move in each direction.
4. After selection, merge the two player groups against `hitter_fantasy_2026.csv` and `pitcher_fantasy_2026.csv` using `_fuzzy_merge`. Show a side-by-side comparison table with columns: `player_name`, `type` (H/SP/RP), `signal`, `proc_plus_positional` or `plv_blended`, `core_fp_per_pa` or `fp_per_app`, `sample_tier`.
5. Below the table, show aggregate "Give" vs "Receive" summary metrics in `st.metric` columns: total FP rate, average signal rank (numeric), count of Top Target + Strong Add players. Include a verdict line like "You receive the better process profile" or "Roughly even" based on signal rank totals.

Use `_SIG_RANK` dict (already in scope: `{"Top Target": 4, "Strong Add": 3, "Watchlist": 2, "Pass": 1, "Too Small": 0}`) for numeric signal comparison.

---

### TASK 4 — Batted Ball Stars target board

Add a new board option to the **Target Boards** tab dropdown:

**"Bat-Tracking Stars (Blast Rate + Speed)"** → reads from `hitter_fantasy_2026.csv`

Filter criteria:
- `blast_rate` >= 75th percentile of players with `swing_count` >= 50
- `avg_swing_speed` >= 70th percentile
- `sample_tier` not "Too Small"

Sort by `blast_rate` descending. Display columns: `batter_name`, `signal`, `blast_rate`, `avg_swing_speed`, `fast_swing_rate`, `squared_up_rate`, `swing_count`, `process_plus`, `core_fp_per_pa`.

This does NOT need to be a pre-built CSV — compute it live in the Target Boards tab when that option is selected. Add a caption: "Bat-tracking stars: top blast rate + swing speed. Predictive of power breakouts. Data: MLB Statcast bat-tracking sensors."

---

### TASK 5 — Two-start SP flag on SP Starts tab

In the **SP Starts** tab, add a `st.text_input` where the user can paste a comma-separated list of dates for the upcoming week (e.g. "2026-05-01, 2026-05-04"). For each SP in the merged results, check if two of the pitcher's pro team's games fall on those dates by querying a simple schedule lookup.

Since we don't have a schedule API, implement a pragmatic fallback: add a boolean column `two_start_candidate` that is True when `percent_owned < 30` (likely a streamer). Add a "2-Start Streamers" toggle checkbox that filters to only those players. Add a note: "Two-start detection requires manual date entry — we flag low-ownership streamers as likely 2-start candidates."

---

### TASK 6 — Schedule `fetch_savant_rolling.py` as a daily task

Add a cron-style note at the top of `scripts/fetch_savant_rolling.py` as a module docstring update:

```
Run daily via cron (example):
  0 7 * * * cd /path/to/plv_clone && python scripts/fetch_savant_rolling.py --year 2026
```

Then create a wrapper shell script at `scripts/refresh_data.sh`:

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")/.."
python scripts/fetch_savant_rolling.py --year 2026
plv build-exports 2026
plv build-fantasy-exports 2026
plv build-target-boards 2026
echo "Refresh complete: $(date)"
```

Make it executable.

---

## Style rules
- Dark-theme compatible: use existing `_BADGE_CSS` for signal coloring, `#22c55e` green / `#ef4444` red for deltas
- All new Plotly charts: `height=350`, `margin=dict(l=30, r=20, t=40, b=30)`
- All new tables: `use_container_width=True`, `hide_index=True`
- Prefer `st.dataframe(styler)` over `st.table()` for anything with numeric formatting
- All data loading: use `@st.cache_data(ttl=3600)` for ESPN calls, `ttl=300` for file-based loads
- Never import at module level anything that might fail — use try/except or local imports inside functions
- Keep the existing `_render_signal_table()` helper for any table that has a `signal` column

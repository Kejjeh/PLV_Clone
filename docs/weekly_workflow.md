# Weekly Fantasy Workflow — PLV + Process+

*Unofficial public-data clone. Calibrated on 2021-2024 Statcast data, v1.0.0.*

Estimated weekly time commitment: 20-30 minutes.

---

## Step 0: One-time Setup (skip after first run)

```bash
cd plv_clone
pip install -e ".[dev]"

# Pull and score historical data (takes 30-60 min first time)
plv pull-data --start 2021-04-01 --end 2025-11-01
plv build-features --start 2021-04-01 --end 2025-11-01
plv train-plv
plv train-process
plv score-plv 2025
plv score-process 2025
plv build-exports 2025
plv build-target-boards 2025
```

---

## Step 1: Pull New Data (Monday morning)

```bash
# Pull any new pitches since last run
plv pull-data --start 2025-04-01 --end 2025-11-01

# Re-score (incremental: only new pitch rows are processed)
plv score-plv 2025
plv score-process 2025
```

These commands are idempotent. Running them again when nothing is new is safe — no data is duplicated.

---

## Step 2: Rebuild Exports and Target Boards

```bash
plv build-exports 2025
plv build-target-boards 2025
```

This regenerates:
- `master_hitter_2025.csv` — full-season hitter leaderboard
- `master_pitcher_2025.csv` — full-season pitcher leaderboard
- `process_plus_rolling_2025.csv` — 30-day rolling windows
- `plv_rolling_2025.csv` — 30-day rolling PLV
- All 6 target board CSVs

Typical runtime: under 2 minutes.

---

## Step 3: Open the Dashboard

```bash
streamlit run app/dashboard.py
```

Navigate to `http://localhost:8501` in your browser.

### What to look at each week

**Target Boards tab — start here**

1. **Buy Targets** (rank_gap > 0.15): Hitters whose Process+ rank outpaces their xwOBA rank.
   - Filter to Tier A/B only for actionable adds.
   - Sort by `rank_gap` descending — the biggest divergence = highest buy confidence.
   - Look for `rolling hot` in the tag column — process ahead AND recently trending up is the strongest signal.

2. **Regression Flags** (rank_gap < -0.15): Sell-high candidates.
   - Check `rolling_trend` column — if trend is also "cold", the deterioration may be underway already.
   - Cross-check Decision+: if < 94, the chasing behavior is the cause (structural). If only Power+ is weak, could be batted-ball variance.

3. **Breakout Flags**: Process+ >= 110, surface stats not yet elite. Add-low targets on waivers.

**Hitters tab — leaderboard drill-down**

- Filter to Min PA = 150, sort by Decision+ to find early-season discipline leaders.
- For hitters in the top 30 Process+ but not in your lineup: check if they're available.

**Rolling Trends tab — week-to-week movers**

- Sort by `decision_value_mean` — the raw rolling value that drives Decision+.
- Anyone who jumped into the top 20 this week and isn't in your lineup is worth evaluating.

**Player View tab — individual deep-dive**

- Search any hitter to see their component breakdown and rolling sparkline.
- Use this to evaluate trade targets or free agents with surprising stats.

---

## Step 4: Weekly Decision Checklist

For each player you're considering adding, trading for, or dropping:

**Waiver add:**
- [ ] Process+ >= 100 (above average)?
- [ ] Decision+ >= 109 (top 25%)? If yes, the walk rate/K% trajectory is reliable.
- [ ] Rolling trend: improving or hot?
- [ ] Sample: Tier B or A? Tier C = watch for 2 more weeks before acting.

**Trade target:**
- [ ] rank_gap > 0.15? (Process rank > xwOBA rank = process ahead of results)
- [ ] Full-season and rolling both positive? Stronger conviction.
- [ ] xwoba_vs_expected positive? Power+ is generating above what pitchers expect.

**Sell-high target:**
- [ ] rank_gap < -0.15? (xwOBA ahead of process)
- [ ] Decision+ < 94? Chase rate is the culprit — structural, not variance.
- [ ] Rolling trend falling? Deterioration may already be underway.

**Dynasty hold vs. cut:**
- Full-season Tier A (400+ PA) with Process+ >= 108: hold, regardless of current slump.
- Tier C (< 250 PA) with falling rolling trend: monitor one more week.
- Both Process+ and xwOBA below average (both < 96): no redeeming signal — drop.

---

## Threshold Quick Reference

| Decision | Threshold |
|---|---|
| Strong Process+ (top 25%) | >= 108 |
| Elite Process+ (top 10%) | >= 115 |
| Strong Decision+ (top 25%) | >= 109 |
| Strong Power+ (top 25%) | >= 107 |
| Buy signal (rank divergence) | rank_gap > 0.15 |
| Regression risk (rank divergence) | rank_gap < -0.15 |
| xwOBA above average | >= 0.363 |
| xwOBA top quartile | >= 0.400 |
| PLV strong (top 25%) | >= 5.17 |
| Tier A sample (hitter) | >= 400 PA |
| Tier B sample (hitter) | 250-399 PA |
| Min reliable Process+ | 150 PA |
| Min reliable Decision+ | 50 PA |

Full threshold documentation: `docs/fantasy_decision_framework.md`

---

## Periodic Tasks (monthly or start of season)

**Validate outputs after new data:**
```bash
python scripts/validate_outputs.py --year 2025
```
All 19 checks should pass. If scaling drift > 3 points, re-run `plv train-process` with updated data.

**BatScore integration (when you have BatScore data):**
```python
from plv_clone.pipelines.batscore_merge import run
from plv_clone.config import get_config

merged = run(year=2025, batscore_path="your_batscore_2025.csv", config=get_config())
# Produces data/outputs/fantasy_hitter_merged_2025.csv
```
See `docs/process_plus_vs_batscore_analysis.md` for how to interpret the `pp_vs_bs_gap` and `pp_bs_agreement` columns.

---

## Key Files Reference

| File | Purpose |
|---|---|
| `data/outputs/master_hitter_2025.csv` | Full-season hitter leaderboard |
| `data/outputs/master_pitcher_2025.csv` | Full-season pitcher leaderboard |
| `data/outputs/hitter_buy_targets_2025.csv` | Buy target board |
| `data/outputs/hitter_regression_flags_2025.csv` | Sell-high board |
| `data/outputs/hitter_breakout_flags_2025.csv` | Breakout/add-low board |
| `data/outputs/hitter_discipline_targets_2025.csv` | Top Decision+ |
| `data/outputs/hitter_power_targets_2025.csv` | Top Power+ |
| `data/outputs/pitcher_plv_targets_2025.csv` | Top PLV pitchers |
| `data/outputs/fantasy_hitter_merged_2025.csv` | BatScore merge (template until data loaded) |
| `docs/fantasy_decision_framework.md` | Full threshold documentation |
| `docs/process_plus_vs_batscore_analysis.md` | BatScore vs Process+ integration guide |
| `app/dashboard.py` | Streamlit dashboard |

---

*Thresholds calibrated on 2024 data. Re-validate with `scripts/validate_outputs.py` each season.*

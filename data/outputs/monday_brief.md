# Monday brief — New York Ligers (BrownU)

_As-of date **2026-07-30** (Thursday). Composed offline from artifacts already on disk — no live ESPN, MLB Stats, or Pitcher List calls. Every number below is stamped with the age of the file it came from._

<!-- Brief built: 2026-07-30T02:02:20 — the ONLY wall-clock stamp in this file; the body depends on the calendar date only, so intraday reruns diff to this line alone. -->

## 1. Decisions

### Needs a decision

1. **TRIPWIRE FAIL** `fg_scrape_silent_fail` (fg_pit_2026_current.csv) — mtime-based; daily step (0.8) — FG scrape appears to be SILENTLY FAILING (13d since last successful update; it exits 0 on chromedriver crash). Run scripts/_oneoff/fg_2026_current.py in an interactive shell with a working Chrome. [from model_scorecard.csv, as-of 2026-07-27, 3 days old (content date)]
2. **MOVE AVAILABLE — STEP 1 of 2 (sequenced — do them IN ORDER; later steps are scored against the roster after the earlier ones and may drop a player an earlier step added)** ADD Ryan Jeffers / DROP Reid Detmers for dP(win) +0.0944 (> 2x MC se — a real gap). Verify live rosters (`/roster-verify`) before executing. [weekly_optimizer.json, as-of 2026-07-30, today (content date)]
3. **MOVE AVAILABLE — STEP 2 of 2 (sequenced — do them IN ORDER; later steps are scored against the roster after the earlier ones and may drop a player an earlier step added)** ADD Trent Grisham / DROP Ryan Jeffers for dP(win) +0.0674 (> 2x MC se — a real gap). Verify live rosters (`/roster-verify`) before executing. [weekly_optimizer.json, as-of 2026-07-30, today (content date)]

### Worth knowing

- TRIPWIRE WARN `fg_proj_cache_systems_latest` (2026-07-27) — 7/8 systems; absent: steamerr_bat [model_scorecard.csv, as-of 2026-07-27, 3 days old (content date)]
- `season_sim.json` is 2 period(s) behind (sim 15 vs live 17) — the title-equity weight applied to every move above comes from older standings. Run: `python scripts/xfp/run_season_sim.py`
- PL cache `pl_sp_streamers_latest.json` is STALE — 10d old (rolling, refresh every 2d) (10d old). Refresh in an interactive session (`/triangulate --check-caches`); this brief cannot fetch pitcherlist.com.

## 2. This period — P(win) and cap

- `matchup_leverage.json` — as-of 2026-07-29, 1 day old (content date)
- Period **17** vs **Late Night Bettsing** — 91.1 to 121.7, 5d left incl. today
- **P(win) 0.281** — regime **TRAILING**
- Regime directive: variance is an ASSET — prefer boom/bust (high-sigma, high boom%) plays
- SP cap 3/10 banked, 7 remaining (opp 9)
- Top leverage moves from this run:
  - ADD Walbert Urena (FA) for 2026-08-02 vs MIL — dP(win) +0.0287 (extra cap-eligible start, EV 11.75, boom% 20)
  - ADD Cade Cavalli (FA) for 2026-08-02 vs ATL — dP(win) +0.0286 (extra cap-eligible start, EV 10.93, boom% 33)
  - ADD Kyle Bradish (FA) for 2026-08-02 vs PHI — dP(win) +0.0275 (extra cap-eligible start, EV 11.23, boom% 47)

## 3. Recommended plan (weekly optimizer)

- `weekly_optimizer.json` — as-of 2026-07-30, today (content date)
- Base P(win) 0.385, regime TRAILING, period 17, 5000 sims (seed 7), cap remaining 7
- Recommended sequenced plan:
  1. ADD Ryan Jeffers (H) / DROP Reid Detmers (SP) — dP(win) +0.0944, mc_se 0.0071, title equity +0.0831pp
  2. ADD Trent Grisham (H) / DROP Ryan Jeffers (H) — dP(win) +0.0674, mc_se 0.0070, title equity +0.0593pp
- Title-equity weight: 0.88pp per win (status **stale**)
  - season_sim.json was generated at period 15, now period 17 (2 behind, stale) — the leverage weight is estimated from older standings. Re-run /season-sim to refresh.

## 4. Delta-P(win) surface (durable counterfactual store)

- `dpwin_history.parquet` — as-of 2026-07-30, today (content date)
- 690 counterfactual rows over 2 snapshot day(s) (2026-07-29 -> 2026-07-30)
- Latest snapshot 2026-07-30: 662 rows from 3 run(s) [2026-07-30T003057_7, 2026-07-30T003632_7, 2026-07-30T005713_7]
- Best-scoring alternative per move_type in the latest snapshot:
  - `drop` Reid Detmers — dP(win) +0.0000
  - `swap` Ryan Jeffers — dP(win) +0.0944

## 5. Season outlook (title odds, value of a win)

- `season_sim.json` — as-of 2026-07-11, 19 days old (content date) [STALE]
- **New York Ligers** — P(playoffs) 0.925, P(title) 0.108 (sim period 15, 5000 sims)
- **2 period(s) BEHIND** the live matchup (sim period 15 vs live 17) — the odds and the value-of-win curve are computed off older standings. Run: `python scripts/xfp/run_season_sim.py`
- Value of winning each remaining period (dP(title), pp):
  - period 15: dtitle +2.67pp, dplayoffs +6.56pp (P(win week) 0.343)
  - period 16: dtitle +1.24pp, dplayoffs +9.27pp (P(win week) 0.688)
  - period 17: dtitle +0.88pp, dplayoffs +6.42pp (P(win week) 0.431)
  - period 18: dtitle +1.39pp, dplayoffs +18.47pp (P(win week) 0.63)
  - period 19: dtitle +2.37pp, dplayoffs +10.80pp (P(win week) 0.49)
  - period 20: dtitle +1.84pp, dplayoffs +9.72pp (P(win week) 0.538)
- Strategy directive from the sim:
  - Playoff odds 93%, title odds 10.8%, modal seed 5 (P(miss) 7%).
  - A win THIS period is worth +2.7pp title equity (vs +2.1pp avg for periods 19-20).
  - MOSTLY SAFE: entry likely but not locked (P(miss) 7%) — take cheap wins and free streams, but don't burn premium FAAB on marginal regular-season edges; start positioning the playoff roster (/playoff-team-build, /sp-stash-finder).
  - Variance is roughly title-neutral right now (+0.00pp per +10% sigma) — optimize E[FP].
  - Mean dial: +2 FP/week of true strength = +0.56pp title / +0.40pp playoffs — the scale for valuing any add/trade in equity terms.

## 6. Decision quality (settled verdicts)

- `verdict_scorecard.csv` — as-of 2026-07-30, today (file mtime) (no date column in this artifact, so the age is mtime-based)
- 10 bucket x verdict cells over 382 settled observations

| bucket | verdict | n | players | mean actual | mean proj | residual | hit rate |
|---|---|---|---|---|---|---|---|
| H | BUY | 126 | 11 | 0.558 | 0.594 | -0.036 | 0.325 |
| H | CAUTION | 21 | 4 | 0.640 | 0.555 | 0.085 | -- |
| H | FADE | 4 | 2 | 0.289 | 0.490 | -0.201 | 1.000 |
| H | MIXED | 132 | 14 | 0.588 | 0.560 | 0.028 | -- |
| RP | BUY | 30 | 4 | 6.548 | -- | -- | 0.000 |
| RP | MIXED | 2 | 1 | 2.555 | -- | -- | -- |
| SP | BUY | 19 | 3 | 9.494 | 11.406 | -1.913 | 0.053 |
| SP | HOLD | 2 | 1 | 14.000 | 10.329 | 3.671 | -- |
| SP | CAUTION | 26 | 4 | 9.153 | 10.671 | -1.518 | -- |
| SP | MIXED | 20 | 3 | 4.477 | 10.683 | -6.205 | -- |

## 7. Model + data health

- `model_scorecard.csv` — as-of 2026-07-27, 3 days old (content date)
- Tripwires (data_health + pipeline_staleness): FAIL 1, PASS 29, WARN 1
- Drift sentinels (added 2026-07-29):
  - `collision_team_reachability` — **NO ROW in this scorecard**: this scorecard is as-of 2026-07-27, which PREDATES the 2026-07-29 introduction — expected; the next Monday scorecard will carry it
  - `collision_smoke` — **NO ROW in this scorecard**: this scorecard is as-of 2026-07-27, which PREDATES the 2026-07-29 introduction — expected; the next Monday scorecard will carry it
  - `fa_join_coverage` — **NO ROW in this scorecard**: this scorecard is as-of 2026-07-27, which PREDATES the 2026-07-29 introduction — expected; the next Monday scorecard will carry it
- Forward accuracy (all-segment headline rows):
  - `rh3_spearman_rate_7d` = 0.1247 [INFO]
  - `rh3_vs_prior_delta_7d` = 0.0253 [INFO]
  - `rp3_spearman_rate_7d` = 0.1947 [INFO]
  - `rp3_vs_prior_delta_7d` = 0.2455 [INFO]
  - `rprs2_spearman_rate_7d` = 0.1986 [INFO]
  - `rh3_spearman_rate_14d` = 0.1607 [INFO]
  - `rh3_vs_prior_delta_14d` = -0.0123 [INFO]
  - `rp3_spearman_rate_14d` = 0.3585 [INFO]
  - `rp3_vs_prior_delta_14d` = 0.2492 [INFO]
  - `rprs2_spearman_rate_14d` = 0.2544 [INFO]
  - `rh3_spearman_rate_21d` = 0.1514 [INFO]
  - `rh3_vs_prior_delta_21d` = 0.0465 [INFO]
  - `rp3_spearman_rate_21d` = 0.3962 [INSUFFICIENT]
  - `rprs2_spearman_rate_21d` = 0.2952 [INFO]
  - `rh3_spearman_rate_28d` = 0.1713 [INFO]
  - `rh3_vs_prior_delta_28d` = 0.0496 [INFO]
  - `rp3_spearman_rate_28d` = 0.3056 [INFO]
  - `rp3_vs_prior_delta_28d` = 0.0918 [INFO]
  - `rprs2_spearman_rate_28d` = 0.3256 [INFO]
- Full rendered scorecard: `model_scorecard.md` — as-of 2026-07-27, 3 days old (file mtime)

## 8. Pitcher List cache ages (no scraping here)

- Read-only: this brief does NOT fetch pitcherlist.com. Per `refresh_dashboards.py` step 7 the PL caches need a live agent WebSearch/WebFetch (deliberately not another headless scrape), so refresh them in an interactive session (`/triangulate --check-caches`).
- `pl_sps_top100.json` — fetched 2026-07-27 (3d old) — current: current (latest live Mon edition 2026-07-27 already cached)
- `pl_closers.json` — fetched 2026-07-28 (2d old) — current: current (latest live Tue edition 2026-07-28 already cached)
- `pl_hitters_top150.json` — fetched 2026-07-29 (1d old) — current: current (latest live Wed edition 2026-07-29 already cached)
- `pl_sp_streamers_latest.json` — fetched 2026-07-20 (10d old) — **STALE**: 10d old (rolling, refresh every 2d)

## 9. Provenance

| artifact | status | as-of | age | basis | regenerate with |
|---|---|---|---|---|---|
| `dpwin_history.parquet` | ok | 2026-07-30 | 0d | content date | `python scripts/xfp/run_matchup_leverage.py  (or run_weekly_optimizer.py — either appends)` |
| `matchup_leverage.json` | ok | 2026-07-29 | 1d | content date | `python scripts/xfp/run_matchup_leverage.py` |
| `model_scorecard.csv` | ok | 2026-07-27 | 3d | content date | `python scripts/xfp/build_model_scorecard.py  (refresh step 4.97, Mondays only)` |
| `model_scorecard.md` | ok | 2026-07-27 | 3d | file mtime | `python scripts/xfp/build_model_scorecard.py  (refresh step 4.97, Mondays only)` |
| `season_sim.json` | STALE | 2026-07-11 | 19d | content date | `python scripts/xfp/run_season_sim.py` |
| `verdict_scorecard.csv` | ok | 2026-07-30 | 0d | file mtime | `python scripts/xfp/run_verdict_scorecard.py  (refresh step 4.97b, Mondays only)` |
| `weekly_optimizer.json` | ok | 2026-07-30 | 0d | content date | `python scripts/xfp/run_weekly_optimizer.py` |

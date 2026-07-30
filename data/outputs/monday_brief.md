# Monday brief — New York Ligers (BrownU)

_As-of date **2026-07-30** (Thursday). Composed offline from artifacts already on disk — no live ESPN, MLB Stats, or Pitcher List calls. Every number below is stamped with the age of the file it came from._

<!-- Brief built: 2026-07-30T09:08:50 — the ONLY wall-clock stamp in this file; the body depends on the calendar date only, so intraday reruns diff to this line alone. -->

## 1. Decisions

### Needs a decision

1. **TRIPWIRE FAIL** `fg_scrape_silent_fail` (fg_pit_2026_current.csv) — mtime-based; daily step (0.8) — FG scrape appears to be SILENTLY FAILING (15d since last successful update; it exits 0 on chromedriver crash). Run scripts/_oneoff/fg_2026_current.py in an interactive shell with a working Chrome. [from model_scorecard.csv, as-of 2026-07-30, today (content date)]
2. **MOVE AVAILABLE — STEP 1 of 2 (sequenced — do them IN ORDER; later steps are scored against the roster after the earlier ones and may drop a player an earlier step added)** ADD Ryan Jeffers / DROP Reid Detmers for dP(win) +0.0944 (> 2x MC se — a real gap). Verify live rosters (`/roster-verify`) before executing. [weekly_optimizer.json, as-of 2026-07-30, today (content date)]
3. **MOVE AVAILABLE — STEP 2 of 2 (sequenced — do them IN ORDER; later steps are scored against the roster after the earlier ones and may drop a player an earlier step added)** ADD Trent Grisham / DROP Ryan Jeffers for dP(win) +0.0674 (> 2x MC se — a real gap). Verify live rosters (`/roster-verify`) before executing. [weekly_optimizer.json, as-of 2026-07-30, today (content date)]

### Worth knowing

- TRIPWIRE WARN `console_data_freshness` (all) — console_data.json vs newest input xfp_rh3_projections.csv; hours behind (>0 = stale decision console — the 2026-07-18 trap) [model_scorecard.csv, as-of 2026-07-30, today (content date)]
- TRIPWIRE WARN `espn_snapshot_ttl` (all) — oldest free_agents_2000.pkl age minutes vs TTL 240min (WARN >960min = stale snapshot lingering) [model_scorecard.csv, as-of 2026-07-30, today (content date)]
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

- `season_sim.json` — as-of 2026-07-30, today (content date)
- **New York Ligers** — P(playoffs) 0.977, P(title) 0.141 (sim period 17, 5000 sims)
- Sim period 17 matches the live matchup period.
- Value of winning each remaining period (dP(title), pp):
  - period 17: dtitle +0.75pp, dplayoffs +2.42pp (P(win week) 0.336)
  - period 18: dtitle +1.79pp, dplayoffs +7.21pp (P(win week) 0.678)
  - period 19: dtitle +2.03pp, dplayoffs +4.58pp (P(win week) 0.577)
  - period 20: dtitle +0.74pp, dplayoffs +5.59pp (P(win week) 0.656)
- Strategy directive from the sim:
  - Playoff odds 98%, title odds 14.1%, modal seed 4 (P(miss) 2%).
  - A win THIS period is worth +0.8pp title equity (vs +1.4pp avg for periods 19-20).
  - SAFE: playoff spot near-locked — bank floor, hoard FAAB/streams for the playoff weeks; a marginal regular-season win buys little. Position the playoff roster (/playoff-team-build, /sp-stash-finder).
  - VARIANCE HURTS: +10% weekly sigma costs -0.16pp title equity — you are protecting a position; prefer floor (SAFE-tier arms, low bust%).
  - Mean dial: +2 FP/week of true strength = +0.68pp title / +0.06pp playoffs — the scale for valuing any add/trade in equity terms.

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

- `model_scorecard.csv` — as-of 2026-07-30, today (content date)
- Tripwires (data_health + pipeline_staleness): FAIL 1, PASS 33, WARN 2
- Drift sentinels (added 2026-07-29):
  - `collision_team_reachability` (all): **PASS** — 29/29 collision team hints reachable from 30 live ESPN codes
  - `collision_smoke` (all): **PASS** — 12/12 canonical resolver cases
  - `fa_join_coverage` (H): **PASS** — 214/214 FA H rows join xfp_rh3_projections.csv by mlbam; no trailing baseline yet (need 3+ prior days) — absolute floors 0.70/0.40 applied
  - `fa_join_coverage` (SP): **PASS** — 209/209 FA SP rows join xfp_rp3_projections.csv by mlbam; no trailing baseline yet (need 3+ prior days) — absolute floors 0.70/0.40 applied
  - `fa_join_coverage` (RP): **PASS** — 281/281 FA RP rows join xfp_rprs2_projections.csv by mlbam; no trailing baseline yet (need 3+ prior days) — absolute floors 0.70/0.40 applied
- Forward accuracy (all-segment headline rows):
  - `rh3_spearman_rate_7d` = 0.0572 [INFO]
  - `rh3_vs_prior_delta_7d` = 0.0035 [INFO]
  - `rp3_spearman_rate_7d` = 0.3036 [INFO]
  - `rp3_vs_prior_delta_7d` = 0.2335 [INFO]
  - `rprs2_spearman_rate_7d` = 0.2950 [INFO]
  - `rh3_spearman_rate_14d` = 0.2139 [INFO]
  - `rh3_vs_prior_delta_14d` = 0.0338 [INFO]
  - `rp3_spearman_rate_14d` = 0.3724 [INFO]
  - `rp3_vs_prior_delta_14d` = 0.2910 [INFO]
  - `rprs2_spearman_rate_14d` = 0.2283 [INFO]
  - `rh3_spearman_rate_21d` = 0.2041 [INFO]
  - `rh3_vs_prior_delta_21d` = 0.0510 [INFO]
  - `rp3_spearman_rate_21d` = 0.5071 [INSUFFICIENT]
  - `rprs2_spearman_rate_21d` = 0.2592 [INFO]
  - `rh3_spearman_rate_28d` = 0.1869 [INFO]
  - `rh3_vs_prior_delta_28d` = 0.0598 [INFO]
  - `rp3_spearman_rate_28d` = 0.3794 [INFO]
  - `rp3_vs_prior_delta_28d` = 0.1283 [INFO]
  - `rprs2_spearman_rate_28d` = 0.3038 [INFO]
- Full rendered scorecard: `model_scorecard.md` — as-of 2026-07-30, today (file mtime)

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
| `model_scorecard.csv` | ok | 2026-07-30 | 0d | content date | `python scripts/xfp/build_model_scorecard.py  (refresh step 4.97, Mondays only)` |
| `model_scorecard.md` | ok | 2026-07-30 | 0d | file mtime | `python scripts/xfp/build_model_scorecard.py  (refresh step 4.97, Mondays only)` |
| `season_sim.json` | ok | 2026-07-30 | 0d | content date | `python scripts/xfp/run_season_sim.py` |
| `verdict_scorecard.csv` | ok | 2026-07-30 | 0d | file mtime | `python scripts/xfp/run_verdict_scorecard.py  (refresh step 4.97b, Mondays only)` |
| `weekly_optimizer.json` | ok | 2026-07-30 | 0d | content date | `python scripts/xfp/run_weekly_optimizer.py` |

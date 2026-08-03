# Monday brief — New York Ligers (BrownU)

_As-of date **2026-08-03** (Monday). Composed offline from artifacts already on disk — no live ESPN, MLB Stats, or Pitcher List calls. Every number below is stamped with the age of the file it came from._

<!-- Brief built: 2026-08-03T12:57:08 — the ONLY wall-clock stamp in this file; the body depends on the calendar date only, so intraday reruns diff to this line alone. -->

## 1. Decisions

### Needs a decision

1. **MOVE AVAILABLE — STEP 1 of 2 (sequenced — do them IN ORDER; each dpwin is the marginal gain given the earlier steps)** ADD Spencer Horwitz / DROP Drew Rasmussen for dP(win) +0.0644 (> 2x MC se — a real gap). Verify live rosters (`/roster-verify`) before executing. [weekly_optimizer.json, as-of 2026-08-03, today (content date)]
2. **MOVE AVAILABLE — STEP 2 of 2 (sequenced — do them IN ORDER; each dpwin is the marginal gain given the earlier steps)** ADD Alec Bohm / DROP Griffin Jax for dP(win) +0.0232 (> 2x MC se — a real gap). Verify live rosters (`/roster-verify`) before executing. [weekly_optimizer.json, as-of 2026-08-03, today (content date)]

### Worth knowing

- TRIPWIRE WARN `fg_proj_cache_systems_latest` (2026-08-03) — 7/8 systems; absent: steamerr_pit [model_scorecard.csv, as-of 2026-08-03, today (content date)]
- `matchup_leverage.json` is 2d old, so the cap count above is 2d of starts behind. Run: `python scripts/xfp/run_matchup_leverage.py`
- PL cache `pl_sp_streamers_latest.json` is STALE — 4d old (rolling, refresh every 2d) (4d old). Refresh in an interactive session (`/triangulate --check-caches`); this brief cannot fetch pitcherlist.com.

## 2. This period — P(win) and cap

- `matchup_leverage.json` — as-of 2026-08-01, 2 days old (content date) [STALE]
- Period **17** vs **Late Night Bettsing** — 279.6 to 298.0, 2d left incl. today
- **P(win) 0.604** — regime **LEADING**
- Regime directive: variance is a LIABILITY — prefer floor (SAFE-tier, low bust%) plays
- SP cap 6/10 banked, 4 remaining (opp 3)
- Top leverage moves from this run:
  - ADD Walbert Urena (FA) for 2026-08-02 vs MIL — dP(win) +0.0264 (extra cap-eligible start, EV 12.18, boom% 20)
  - ADD Kyle Bradish (FA) for 2026-08-02 vs PHI — dP(win) +0.0250 (extra cap-eligible start, EV 11.28, boom% 47)
  - ADD Jake Bennett (FA) for 2026-08-02 vs LAD — dP(win) +0.0249 (extra cap-eligible start, EV 10.34, boom% 36)

## 3. Recommended plan (weekly optimizer)

- `weekly_optimizer.json` — as-of 2026-08-03, today (content date)
- Base P(win) 0.797, regime LEADING, period 18, 20000 sims (seed 7), cap remaining 10
- Recommended sequenced plan:
  1. ADD Spencer Horwitz (H) / DROP Drew Rasmussen (SP) — dP(win) +0.0644, mc_se 0.0024, title equity +0.1153pp
  2. ADD Alec Bohm (H) / DROP Griffin Jax (SP) — dP(win) +0.0232, mc_se 0.0023, title equity +0.0415pp
- Title-equity weight: 1.79pp per win (status **stale**)
  - season_sim.json was generated at period 17, now period 18 (1 behind, stale) — the leverage weight is estimated from older standings. Re-run /season-sim to refresh.

## 4. Delta-P(win) surface (durable counterfactual store)

- `dpwin_history.parquet` — as-of 2026-08-03, today (content date)
- 2706 counterfactual rows over 4 snapshot day(s) (2026-07-29 -> 2026-08-03)
- Latest snapshot 2026-08-03: 502 rows from 1 run(s) [2026-08-03T071820_7]
- Best-scoring alternative per move_type in the latest snapshot:
  - `drop` Drew Rasmussen — dP(win) +0.0000
  - `swap` Spencer Horwitz — dP(win) +0.0644

## 5. Season outlook (title odds, value of a win)

- `season_sim.json` — as-of 2026-07-30, 4 days old (content date)
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

- `verdict_scorecard.csv` — as-of 2026-08-03, today (file mtime) (no date column in this artifact, so the age is mtime-based)
- 10 bucket x verdict cells over 482 settled observations

| bucket | verdict | n | players | mean actual | mean proj | residual | hit rate |
|---|---|---|---|---|---|---|---|
| H | BUY | 156 | 11 | 0.554 | 0.595 | -0.040 | 0.301 |
| H | CAUTION | 26 | 4 | 0.630 | 0.556 | 0.074 | -- |
| H | FADE | 4 | 2 | 0.289 | 0.490 | -0.201 | 1.000 |
| H | MIXED | 167 | 14 | 0.568 | 0.562 | 0.006 | -- |
| RP | BUY | 35 | 4 | 6.268 | -- | -- | 0.000 |
| RP | MIXED | 2 | 1 | 2.555 | -- | -- | -- |
| SP | BUY | 28 | 4 | 10.135 | 11.545 | -1.410 | 0.143 |
| SP | HOLD | 4 | 1 | 12.670 | 10.809 | 1.861 | -- |
| SP | CAUTION | 35 | 4 | 9.754 | 10.664 | -0.910 | -- |
| SP | MIXED | 25 | 4 | 4.841 | 10.779 | -5.938 | -- |

## 7. Model + data health

- `model_scorecard.csv` — as-of 2026-08-03, today (content date)
- Tripwires (data_health + pipeline_staleness): PASS 35, WARN 1
- Drift sentinels (added 2026-07-29):
  - `collision_team_reachability` (all): **PASS** — 29/29 collision team hints reachable from 30 live ESPN codes
  - `collision_smoke` (all): **PASS** — 12/12 canonical resolver cases
  - `fa_join_coverage` (H): **PASS** — 219/219 FA H rows join xfp_rh3_projections.csv by mlbam; no trailing baseline yet (need 3+ prior days) — absolute floors 0.70/0.40 applied
  - `fa_join_coverage` (SP): **PASS** — 210/210 FA SP rows join xfp_rp3_projections.csv by mlbam; no trailing baseline yet (need 3+ prior days) — absolute floors 0.70/0.40 applied
  - `fa_join_coverage` (RP): **PASS** — 282/282 FA RP rows join xfp_rprs2_projections.csv by mlbam; no trailing baseline yet (need 3+ prior days) — absolute floors 0.70/0.40 applied
- Forward accuracy (all-segment headline rows):
  - `rh3_spearman_rate_7d` = 0.1451 [INFO]
  - `rh3_vs_prior_delta_7d` = 0.0276 [INFO]
  - `rp3_spearman_rate_7d` = 0.1038 [INFO]
  - `rp3_vs_prior_delta_7d` = 0.3109 [INFO]
  - `rprs2_spearman_rate_7d` = 0.4503 [INFO]
  - `rh3_spearman_rate_14d` = 0.1910 [INFO]
  - `rh3_vs_prior_delta_14d` = 0.0258 [INFO]
  - `rp3_spearman_rate_14d` = 0.3016 [INFO]
  - `rp3_vs_prior_delta_14d` = 0.2699 [INFO]
  - `rprs2_spearman_rate_14d` = 0.3077 [INFO]
  - `rh3_spearman_rate_21d` = 0.1954 [INFO]
  - `rh3_vs_prior_delta_21d` = -0.0053 [INFO]
  - `rp3_spearman_rate_21d` = 0.6791 [INSUFFICIENT]
  - `rprs2_spearman_rate_21d` = 0.3098 [INFO]
  - `rh3_spearman_rate_28d` = 0.1772 [INFO]
  - `rh3_vs_prior_delta_28d` = 0.0155 [INFO]
  - `rp3_spearman_rate_28d` = 0.3946 [INFO]
  - `rp3_vs_prior_delta_28d` = 0.2721 [INFO]
  - `rprs2_spearman_rate_28d` = 0.3473 [INFO]
- Full rendered scorecard: `model_scorecard.md` — as-of 2026-08-03, today (file mtime)

## 8. Pitcher List cache ages (no scraping here)

- Read-only: this brief does NOT fetch pitcherlist.com. Per `refresh_dashboards.py` step 7 the PL caches need a live agent WebSearch/WebFetch (deliberately not another headless scrape), so refresh them in an interactive session (`/triangulate --check-caches`).
- `pl_sps_top100.json` — fetched 2026-07-27 (7d old) — current: current (latest live Mon edition 2026-07-27 already cached)
- `pl_closers.json` — fetched 2026-07-28 (6d old) — current: current (latest live Tue edition 2026-07-28 already cached)
- `pl_hitters_top150.json` — fetched 2026-07-29 (5d old) — current: current (latest live Wed edition 2026-07-29 already cached)
- `pl_sp_streamers_latest.json` — fetched 2026-07-30 (4d old) — **STALE**: 4d old (rolling, refresh every 2d)

## 9. Provenance

| artifact | status | as-of | age | basis | regenerate with |
|---|---|---|---|---|---|
| `dpwin_history.parquet` | ok | 2026-08-03 | 0d | content date | `python scripts/xfp/run_matchup_leverage.py  (or run_weekly_optimizer.py — either appends)` |
| `matchup_leverage.json` | STALE | 2026-08-01 | 2d | content date | `python scripts/xfp/run_matchup_leverage.py` |
| `model_scorecard.csv` | ok | 2026-08-03 | 0d | content date | `python scripts/xfp/build_model_scorecard.py  (refresh step 4.97, Mondays only)` |
| `model_scorecard.md` | ok | 2026-08-03 | 0d | file mtime | `python scripts/xfp/build_model_scorecard.py  (refresh step 4.97, Mondays only)` |
| `season_sim.json` | ok | 2026-07-30 | 4d | content date | `python scripts/xfp/run_season_sim.py` |
| `verdict_scorecard.csv` | ok | 2026-08-03 | 0d | file mtime | `python scripts/xfp/run_verdict_scorecard.py  (refresh step 4.97b, Mondays only)` |
| `weekly_optimizer.json` | ok | 2026-08-03 | 0d | content date | `python scripts/xfp/run_weekly_optimizer.py` |

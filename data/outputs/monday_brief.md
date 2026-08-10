# Monday brief — New York Ligers (BrownU)

_As-of date **2026-08-10** (Monday). Composed offline from artifacts already on disk — no live ESPN, MLB Stats, or Pitcher List calls. Every number below is stamped with the age of the file it came from._

<!-- Brief built: 2026-08-10T11:31:49 — the ONLY wall-clock stamp in this file; the body depends on the calendar date only, so intraday reruns diff to this line alone. -->

## 1. Decisions

### Needs a decision

1. **MOVE AVAILABLE — STEP 1 of 2 (sequenced — do them IN ORDER; each dpwin is the marginal gain given the earlier steps)** ADD Caleb Durbin / DROP Griffin Jax for dP(win) +0.1023 (> 2x MC se — a real gap). Verify live rosters (`/roster-verify`) before executing. [weekly_optimizer.json, as-of 2026-08-10, today (content date)]
2. **MOVE AVAILABLE — STEP 2 of 2 (sequenced — do them IN ORDER; each dpwin is the marginal gain given the earlier steps)** ADD Andruw Monasterio / DROP Max Muncy for dP(win) +0.0374 (> 2x MC se — a real gap). Verify live rosters (`/roster-verify`) before executing. [weekly_optimizer.json, as-of 2026-08-10, today (content date)]

### Worth knowing

- SP cap TIGHT period 18: 9/10 banked, 1 remaining — sequence the rest of the week before streaming. [matchup_leverage.json, as-of 2026-08-09, 1 day old (content date)]
- PL cache `pl_sp_streamers_latest.json` is STALE — 4d old (rolling, refresh every 2d) (4d old). Refresh in an interactive session (`/triangulate --check-caches`); this brief cannot fetch pitcherlist.com.

## 2. This period — P(win) and cap

- `matchup_leverage.json` — as-of 2026-08-09, 1 day old (content date)
- Period **18** vs **Frendy's Fantastic Team** — 302.9 to 220.6, 1d left incl. today
- **P(win) 0.996** — regime **LEADING**
- Regime directive: variance is a LIABILITY — prefer floor (SAFE-tier, low bust%) plays
- SP cap 9/10 banked, 1 remaining (opp 3)
- Top leverage moves from this run:
  - ADD J.T. Ginn (FA) for 2026-08-09 vs BOS — dP(win) +0.0023 (extra cap-eligible start, EV 10.16, boom% 27)
  - ADD Sean Manaea (FA) for 2026-08-09 vs PIT — dP(win) +0.0021 (extra cap-eligible start, EV 9.8, boom% 20)
  - ADD Ian Seymour (FA) for 2026-08-09 vs SEA — dP(win) +0.0020 (extra cap-eligible start, EV 10.8, boom% 38)

## 3. Recommended plan (weekly optimizer)

- `weekly_optimizer.json` — as-of 2026-08-10, today (content date)
- Base P(win) 0.685, regime LEADING, period 19, 10000 sims (seed 7), cap remaining 10
- Recommended sequenced plan:
  1. ADD Caleb Durbin (H) / DROP Griffin Jax (SP) — dP(win) +0.1023, mc_se 0.0041, title equity +0.1504pp
  2. ADD Andruw Monasterio (H) / DROP Max Muncy (H) — dP(win) +0.0374, mc_se 0.0038, title equity +0.0550pp
- Title-equity weight: 1.47pp per win (status **stale**)
  - season_sim.json was generated at period 18, now period 19 (1 behind, stale) — the leverage weight is estimated from older standings. Re-run /season-sim to refresh.

## 4. Delta-P(win) surface (durable counterfactual store)

- `dpwin_history.parquet` — as-of 2026-08-10, today (content date)
- 7618 counterfactual rows over 9 snapshot day(s) (2026-07-29 -> 2026-08-10)
- Latest snapshot 2026-08-10: 431 rows from 1 run(s) [2026-08-10T075018_7]
- Best-scoring alternative per move_type in the latest snapshot:
  - `drop` Griffin Jax — dP(win) +0.0000
  - `swap` Caleb Durbin — dP(win) +0.1023

## 5. Season outlook (title odds, value of a win)

- `season_sim.json` — as-of 2026-08-05, 5 days old (content date)
- **New York Ligers** — P(playoffs) 0.996, P(title) 0.146 (sim period 18, 5000 sims)
- Sim period 18 matches the live matchup period.
- Value of winning each remaining period (dP(title), pp):
  - period 18: dtitle -0.19pp, dplayoffs +2.21pp (P(win week) 0.837)
  - period 19: dtitle +1.47pp, dplayoffs +0.82pp (P(win week) 0.564)
  - period 20: dtitle +0.08pp, dplayoffs +0.95pp (P(win week) 0.621)
- Strategy directive from the sim:
  - Playoff odds 100%, title odds 14.6%, modal seed 4 (P(miss) 0%).
  - A win THIS period is worth -0.2pp title equity (vs +0.8pp avg for periods 19-20).
  - SAFE: playoff spot near-locked — bank floor, hoard FAAB/streams for the playoff weeks; a marginal regular-season win buys little. Position the playoff roster (/playoff-team-build, /sp-stash-finder).
  - VARIANCE HURTS: +10% weekly sigma costs -0.60pp title equity — you are protecting a position; prefer floor (SAFE-tier arms, low bust%).
  - Mean dial: +2 FP/week of true strength = +0.94pp title / +0.02pp playoffs — the scale for valuing any add/trade in equity terms.

## 6. Decision quality (settled verdicts)

- `verdict_scorecard.csv` — as-of 2026-08-10, today (file mtime) (no date column in this artifact, so the age is mtime-based)
- 10 bucket x verdict cells over 638 settled observations

| bucket | verdict | n | players | mean actual | mean proj | residual | hit rate |
|---|---|---|---|---|---|---|---|
| H | BUY | 197 | 11 | 0.550 | 0.598 | -0.048 | 0.274 |
| H | CAUTION | 32 | 4 | 0.609 | 0.559 | 0.050 | -- |
| H | FADE | 4 | 2 | 0.289 | 0.490 | -0.201 | 1.000 |
| H | MIXED | 216 | 15 | 0.548 | 0.564 | -0.016 | -- |
| RP | BUY | 50 | 4 | 5.682 | -- | -- | 0.000 |
| RP | MIXED | 2 | 1 | 2.555 | -- | -- | -- |
| SP | BUY | 43 | 5 | 10.808 | 11.737 | -0.929 | 0.233 |
| SP | HOLD | 4 | 1 | 12.670 | 10.809 | 1.861 | -- |
| SP | CAUTION | 43 | 5 | 10.916 | 10.865 | 0.052 | -- |
| SP | MIXED | 47 | 8 | 6.579 | 11.148 | -4.569 | -- |

## 7. Model + data health

- `model_scorecard.csv` — as-of 2026-08-10, today (content date)
- Tripwires (data_health + pipeline_staleness): PASS 36
- Drift sentinels (added 2026-07-29):
  - `collision_team_reachability` (all): **PASS** — 41/41 collision team hints reachable from 30 live ESPN codes
  - `collision_smoke` (all): **PASS** — 12/12 canonical resolver cases
  - `fa_join_coverage` (H): **PASS** — 216/216 FA H rows join xfp_rh3_projections.csv by mlbam; no trailing baseline yet (need 3+ prior days) — absolute floors 0.70/0.40 applied
  - `fa_join_coverage` (SP): **PASS** — 213/213 FA SP rows join xfp_rp3_projections.csv by mlbam; no trailing baseline yet (need 3+ prior days) — absolute floors 0.70/0.40 applied
  - `fa_join_coverage` (RP): **PASS** — 292/292 FA RP rows join xfp_rprs2_projections.csv by mlbam; no trailing baseline yet (need 3+ prior days) — absolute floors 0.70/0.40 applied
- Forward accuracy (all-segment headline rows):
  - `rh3_spearman_rate_7d` = 0.2020 [INFO]
  - `rh3_vs_prior_delta_7d` = 0.0835 [INFO]
  - `rp3_spearman_rate_7d` = 0.2338 [INFO]
  - `rp3_vs_prior_delta_7d` = 0.0113 [INFO]
  - `rprs2_spearman_rate_7d` = 0.1806 [INFO]
  - `rh3_spearman_rate_14d` = 0.2520 [INFO]
  - `rh3_vs_prior_delta_14d` = 0.0749 [INFO]
  - `rp3_spearman_rate_14d` = 0.2951 [INFO]
  - `rp3_vs_prior_delta_14d` = 0.1261 [INFO]
  - `rprs2_spearman_rate_14d` = 0.2959 [INFO]
  - `rh3_spearman_rate_21d` = 0.2498 [INFO]
  - `rh3_vs_prior_delta_21d` = 0.0583 [INFO]
  - `rp3_spearman_rate_21d` = 0.2958 [INFO]
  - `rp3_vs_prior_delta_21d` = 0.1459 [INFO]
  - `rprs2_spearman_rate_21d` = 0.3125 [INFO]
  - `rh3_spearman_rate_28d` = 0.2338 [INFO]
  - `rh3_vs_prior_delta_28d` = 0.0084 [INFO]
  - `rp3_spearman_rate_28d` = 0.3669 [INFO]
  - `rp3_vs_prior_delta_28d` = 0.1854 [INFO]
  - `rprs2_spearman_rate_28d` = 0.3433 [INFO]
- Full rendered scorecard: `model_scorecard.md` — as-of 2026-08-10, today (file mtime)

## 8. Pitcher List cache ages (no scraping here)

- Read-only: this brief does NOT fetch pitcherlist.com. Per `refresh_dashboards.py` step 7 the PL caches need a live agent WebSearch/WebFetch (deliberately not another headless scrape), so refresh them in an interactive session (`/triangulate --check-caches`).
- `pl_sps_top100.json` — fetched 2026-08-03 (7d old) — current: current (latest live Mon edition 2026-08-03 already cached)
- `pl_closers.json` — fetched 2026-08-04 (6d old) — current: current (latest live Tue edition 2026-08-04 already cached)
- `pl_hitters_top150.json` — fetched 2026-08-05 (5d old) — current: current (latest live Wed edition 2026-08-05 already cached)
- `pl_sp_streamers_latest.json` — fetched 2026-08-06 (4d old) — **STALE**: 4d old (rolling, refresh every 2d)

## 9. Provenance

| artifact | status | as-of | age | basis | regenerate with |
|---|---|---|---|---|---|
| `dpwin_history.parquet` | ok | 2026-08-10 | 0d | content date | `python scripts/xfp/run_matchup_leverage.py  (or run_weekly_optimizer.py — either appends)` |
| `matchup_leverage.json` | ok | 2026-08-09 | 1d | content date | `python scripts/xfp/run_matchup_leverage.py` |
| `model_scorecard.csv` | ok | 2026-08-10 | 0d | content date | `python scripts/xfp/build_model_scorecard.py  (refresh step 4.97, Mondays only)` |
| `model_scorecard.md` | ok | 2026-08-10 | 0d | file mtime | `python scripts/xfp/build_model_scorecard.py  (refresh step 4.97, Mondays only)` |
| `season_sim.json` | ok | 2026-08-05 | 5d | content date | `python scripts/xfp/run_season_sim.py` |
| `verdict_scorecard.csv` | ok | 2026-08-10 | 0d | file mtime | `python scripts/xfp/run_verdict_scorecard.py  (refresh step 4.97b, Mondays only)` |
| `weekly_optimizer.json` | ok | 2026-08-10 | 0d | content date | `python scripts/xfp/run_weekly_optimizer.py` |

# Monday brief — New York Ligers (BrownU)

_As-of date **2026-08-31** (Monday). Composed offline from artifacts already on disk — no live ESPN, MLB Stats, or Pitcher List calls. Every number below is stamped with the age of the file it came from._

<!-- Brief built: 2026-08-31T16:18:48 — the ONLY wall-clock stamp in this file; the body depends on the calendar date only, so intraday reruns diff to this line alone. -->

## 1. Decisions

### Needs a decision

1. **MOVE AVAILABLE — MOVE 1 of 2 (jointly evaluated PAIR — execute both, either order; each dpwin is the marginal gain given the other)** ADD Luke Weaver / DROP Jacob Latz for dP(win) +0.0096 (WITHIN 2x MC se 0.0048 — not distinguishable from no move; break the tie on regime, not dpwin). Verify live rosters (`/roster-verify`) before executing. [weekly_optimizer.json, as-of 2026-08-30, 1 day old (content date)]
2. **MOVE AVAILABLE — MOVE 2 of 2 (jointly evaluated PAIR — execute both, either order; each dpwin is the marginal gain given the other)** ADD Yusei Kikuchi / DROP Corbin Carroll for dP(win) +-0.0000 (WITHIN 2x MC se 0.0048 — not distinguishable from no move; break the tie on regime, not dpwin). Verify live rosters (`/roster-verify`) before executing. [weekly_optimizer.json, as-of 2026-08-30, 1 day old (content date)]

### Worth knowing

- `matchup_leverage.json` is 3d old, so the cap count above is 3d of starts behind. Run: `python scripts/xfp/run_matchup_leverage.py`

## 2. This period — P(win) and cap

- `matchup_leverage.json` — as-of 2026-08-28, 3 days old (content date) [STALE]
- Period **21** vs **Boone's Bad Bullpen** — 150.8 to 185.4, 3d left incl. today
- **P(win) 0.684** — regime **LEADING**
- Regime directive: variance is a LIABILITY — prefer floor (SAFE-tier, low bust%) plays
- SP cap 2/10 banked, 8 remaining (opp 7)
- Top leverage moves from this run:
  - ADD Jake Bennett (FA) for 2026-08-29 vs NYY — dP(win) +0.0870 (extra cap-eligible start, EV 10.66, boom% 27)
  - ADD Christian Scott (FA) for 2026-08-28 vs HOU — dP(win) +0.0805 (extra cap-eligible start, EV 10.78, boom% 20)
  - ADD Tyler Mahle (FA) for 2026-08-30 vs COL — dP(win) +0.0775 (extra cap-eligible start, EV 11.09, boom% 33)

## 3. Recommended plan (weekly optimizer)

- `weekly_optimizer.json` — as-of 2026-08-30, 1 day old (content date)
- Base P(win) 0.626, regime LEADING, period 21, 10000 sims (seed 7), cap remaining 4
- Recommended plan (jointly evaluated pair — either order):
  1. ADD Luke Weaver (RP) / DROP Jacob Latz (RP) — dP(win) +0.0096, mc_se 0.0048, title equity +0.3038pp
  2. ADD Yusei Kikuchi (SP) / DROP Corbin Carroll (H) — dP(win) -0.0000, mc_se 0.0048, title equity -0.0000pp
- Title-equity weight: 31.65pp per win (status **fresh**)

## 4. Delta-P(win) surface (durable counterfactual store)

- `dpwin_history.parquet` — as-of 2026-08-30, 1 day old (content date)
- 15952 counterfactual rows over 22 snapshot day(s) (2026-07-29 -> 2026-08-30)
- Latest snapshot 2026-08-30: 228 rows from 1 run(s) [2026-08-30T071737_7]
- Best-scoring alternative per move_type in the latest snapshot:
  - `drop` Corbin Carroll — dP(win) +0.0000
  - `swap` Luke Weaver — dP(win) +0.0096

## 5. Season outlook (title odds, value of a win)

- `season_sim.json` — as-of 2026-08-29, 2 days old (content date)
- **New York Ligers** — P(playoffs) 1.000, P(title) 0.192 (sim period 21, 2000 sims)
- Sim period 21 matches the live matchup period.
- Value of winning each remaining period (dP(title), pp):
  - period 21: dtitle +31.65pp, dplayoffs +0.00pp (P(win week) 0.605)
  - period 22: dtitle +59.94pp, dplayoffs +0.00pp (P(win week) 0.528)
  - period 23: dtitle +100.00pp, dplayoffs +0.00pp (P(win week) 0.599)
- Strategy directive from the sim:
  - Playoff odds 100%, title odds 19.1%, modal seed 4 (P(miss) 0%).
  - PLAYOFF ROUND (period 21 of 3 rounds): winning THIS round is worth +31.6pp of title probability — the highest-leverage week of the season. Spend streams/FAAB NOW; there is nothing left to hoard for.

## 6. Decision quality (settled verdicts)

- `verdict_scorecard.csv` — as-of 2026-08-31, today (file mtime) (no date column in this artifact, so the age is mtime-based)
- 10 bucket x verdict cells over 1107 settled observations

| bucket | verdict | n | players | mean actual | mean proj | residual | hit rate |
|---|---|---|---|---|---|---|---|
| H | BUY | 345 | 14 | 0.560 | 0.600 | -0.040 | 0.313 |
| H | CAUTION | 48 | 5 | 0.583 | 0.568 | 0.014 | -- |
| H | FADE | 4 | 2 | 0.289 | 0.490 | -0.201 | 1.000 |
| H | MIXED | 310 | 17 | 0.541 | 0.568 | -0.027 | -- |
| RP | BUY | 109 | 4 | 5.263 | 4.981 | -0.025 | 0.229 |
| RP | MIXED | 2 | 1 | 2.555 | -- | -- | -- |
| SP | BUY | 52 | 6 | 11.926 | 11.933 | -0.007 | 0.365 |
| SP | HOLD | 10 | 2 | 13.925 | 12.180 | 1.745 | -- |
| SP | CAUTION | 118 | 8 | 13.453 | 11.351 | 2.101 | -- |
| SP | MIXED | 109 | 8 | 10.967 | 11.736 | -0.770 | -- |

## 7. Model + data health

- `model_scorecard.csv` — as-of 2026-08-31, today (content date)
- Tripwires (data_health + pipeline_staleness): PASS 36
- Drift sentinels (added 2026-07-29):
  - `collision_team_reachability` (all): **PASS** — 41/41 collision team hints reachable from 30 live ESPN codes
  - `collision_smoke` (all): **PASS** — 12/12 canonical resolver cases
  - `fa_join_coverage` (H): **PASS** — 238/238 FA H rows join xfp_rh3_projections.csv by mlbam; +0.000 vs trailing mean 1.000 (WARN -0.05 / FAIL -0.15)
  - `fa_join_coverage` (SP): **PASS** — 218/218 FA SP rows join xfp_rp3_projections.csv by mlbam; +0.000 vs trailing mean 1.000 (WARN -0.05 / FAIL -0.15)
  - `fa_join_coverage` (RP): **PASS** — 321/321 FA RP rows join xfp_rprs2_projections.csv by mlbam; +0.001 vs trailing mean 0.999 (WARN -0.05 / FAIL -0.15)
- Forward accuracy (all-segment headline rows):
  - `rh3_spearman_rate_7d` = 0.0902 [INFO]
  - `rh3_vs_prior_delta_7d` = -0.0080 [INFO]
  - `rp3_spearman_rate_7d` = -0.0227 [INSUFFICIENT]
  - `rprs2_spearman_rate_7d` = 0.0261 [INFO]
  - `rh3_spearman_rate_14d` = 0.1962 [INFO]
  - `rh3_vs_prior_delta_14d` = 0.0039 [INFO]
  - `rp3_spearman_rate_14d` = 0.1949 [INFO]
  - `rp3_vs_prior_delta_14d` = 0.0773 [INFO]
  - `rprs2_spearman_rate_14d` = 0.2066 [INFO]
  - `rh3_spearman_rate_21d` = 0.2667 [INFO]
  - `rh3_vs_prior_delta_21d` = 0.0580 [INFO]
  - `rp3_spearman_rate_21d` = 0.3106 [INFO]
  - `rp3_vs_prior_delta_21d` = 0.2687 [INFO]
  - `rprs2_spearman_rate_21d` = 0.2502 [INFO]
  - `rh3_spearman_rate_28d` = 0.3169 [INFO]
  - `rh3_vs_prior_delta_28d` = 0.0825 [INFO]
  - `rp3_spearman_rate_28d` = 0.2427 [INFO]
  - `rp3_vs_prior_delta_28d` = 0.0712 [INFO]
  - `rprs2_spearman_rate_28d` = 0.2638 [INFO]
- Full rendered scorecard: `model_scorecard.md` — as-of 2026-08-31, today (file mtime)

## 8. Pitcher List cache ages (no scraping here)

- Read-only: this brief does NOT fetch pitcherlist.com. Per `refresh_dashboards.py` step 7 the PL caches need a live agent WebSearch/WebFetch (deliberately not another headless scrape), so refresh them in an interactive session (`/triangulate --check-caches`).
- `pl_sps_top100.json` — fetched 2026-08-24 (7d old) — current: current (latest live Mon edition 2026-08-24 already cached)
- `pl_closers.json` — fetched 2026-08-25 (6d old) — current: current (latest live Tue edition 2026-08-25 already cached)
- `pl_hitters_top150.json` — fetched 2026-08-26 (5d old) — current: current (latest live Wed edition 2026-08-26 already cached)
- `pl_sp_streamers_latest.json` — fetched 2026-08-30 (1d old) — current: 1d old (rolling, refresh every 2d)

## 9. Provenance

| artifact | status | as-of | age | basis | regenerate with |
|---|---|---|---|---|---|
| `dpwin_history.parquet` | ok | 2026-08-30 | 1d | content date | `python scripts/xfp/run_matchup_leverage.py  (or run_weekly_optimizer.py — either appends)` |
| `matchup_leverage.json` | STALE | 2026-08-28 | 3d | content date | `python scripts/xfp/run_matchup_leverage.py` |
| `model_scorecard.csv` | ok | 2026-08-31 | 0d | content date | `python scripts/xfp/build_model_scorecard.py  (refresh step 4.97, Mondays only)` |
| `model_scorecard.md` | ok | 2026-08-31 | 0d | file mtime | `python scripts/xfp/build_model_scorecard.py  (refresh step 4.97, Mondays only)` |
| `season_sim.json` | ok | 2026-08-29 | 2d | content date | `python scripts/xfp/run_season_sim.py` |
| `verdict_scorecard.csv` | ok | 2026-08-31 | 0d | file mtime | `python scripts/xfp/run_verdict_scorecard.py  (refresh step 4.97b, Mondays only)` |
| `weekly_optimizer.json` | ok | 2026-08-30 | 1d | content date | `python scripts/xfp/run_weekly_optimizer.py` |

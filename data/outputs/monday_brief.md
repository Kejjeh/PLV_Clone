# Monday brief — New York Ligers (BrownU)

_As-of date **2026-08-24** (Monday). Composed offline from artifacts already on disk — no live ESPN, MLB Stats, or Pitcher List calls. Every number below is stamped with the age of the file it came from._

<!-- Brief built: 2026-08-24T11:11:29 — the ONLY wall-clock stamp in this file; the body depends on the calendar date only, so intraday reruns diff to this line alone. -->

## 1. Decisions

### Needs a decision

1. **MOVE AVAILABLE — STEP 1 of 2 (sequenced — do them IN ORDER; each dpwin is the marginal gain given the earlier steps)** ADD Alec Bohm / DROP Joshua Baez for dP(win) +0.0119 (> 2x MC se — a real gap). Verify live rosters (`/roster-verify`) before executing. [weekly_optimizer.json, as-of 2026-08-24, today (content date)]
2. **MOVE AVAILABLE — STEP 2 of 2 (sequenced — do them IN ORDER; each dpwin is the marginal gain given the earlier steps)** ADD Javier Sanoja / DROP Jose Soriano for dP(win) +0.0068 (> 2x MC se — a real gap). Verify live rosters (`/roster-verify`) before executing. [weekly_optimizer.json, as-of 2026-08-24, today (content date)]

### Worth knowing

- TRIPWIRE WARN `fg_proj_cache_systems_latest` (2026-08-24) — 7/8 systems; absent: rzips_pit [model_scorecard.csv, as-of 2026-08-24, today (content date)]
- SP cap TIGHT period 19: 8/10 banked, 2 remaining — sequence the rest of the week before streaming. [matchup_leverage.json, as-of 2026-08-14, 10 days old (content date) [STALE]]
- `matchup_leverage.json` is 10d old, so the cap count above is 10d of starts behind. Run: `python scripts/xfp/run_matchup_leverage.py`
- PL cache `pl_sp_streamers_latest.json` is STALE — 6d old (rolling, refresh every 2d) (6d old). Refresh in an interactive session (`/triangulate --check-caches`); this brief cannot fetch pitcherlist.com.

## 2. This period — P(win) and cap

- `matchup_leverage.json` — as-of 2026-08-14, 10 days old (content date) [STALE]
- Period **19** vs **Boone's Bad Bullpen** — 228.6 to 157.2, 3d left incl. today
- **P(win) 0.657** — regime **LEADING**
- Regime directive: variance is a LIABILITY — prefer floor (SAFE-tier, low bust%) plays
- SP cap 8/10 banked, 2 remaining (opp 7)
- No `top_moves` in this run (field absent or empty).

## 3. Recommended plan (weekly optimizer)

- `weekly_optimizer.json` — as-of 2026-08-24, today (content date)
- Base P(win) 0.976, regime LEADING, period 20, 10000 sims (seed 7), cap remaining 2
- Recommended sequenced plan:
  1. ADD Alec Bohm (H) / DROP Joshua Baez (H) — dP(win) +0.0119, mc_se 0.0011
  2. ADD Javier Sanoja (H) / DROP Jose Soriano (SP) — dP(win) +0.0068, mc_se 0.0007
- Title-equity weight: Nonepp per win (status **unavailable**)
  - value_of_win_curve empty (sim ran but produced no rows)

## 4. Delta-P(win) surface (durable counterfactual store)

- `dpwin_history.parquet` — as-of 2026-08-24, today (content date)
- 12791 counterfactual rows over 17 snapshot day(s) (2026-07-29 -> 2026-08-24)
- Latest snapshot 2026-08-24: 468 rows from 1 run(s) [2026-08-24T031137_7]
- Best-scoring alternative per move_type in the latest snapshot:
  - `drop` Jose Soriano — dP(win) +0.0000
  - `swap` Caleb Durbin — dP(win) +0.0131

## 5. Season outlook (title odds, value of a win)

- `season_sim.json` — as-of 2026-08-23, 1 day old (content date)
- **New York Ligers** — P(playoffs) 1.000, P(title) 0.186 (sim period 20, 5000 sims)
- Sim period 20 matches the live matchup period.
- No `value_of_win_curve` in this run.
- Strategy directive from the sim:
  - Playoff odds 100%, title odds 18.6%, modal seed 4 (P(miss) 0%).
  - SAFE: playoff spot near-locked — bank floor, hoard FAAB/streams for the playoff weeks; a marginal regular-season win buys little. Position the playoff roster (/playoff-team-build, /sp-stash-finder).
  - VARIANCE HURTS: +10% weekly sigma costs -0.18pp title equity — you are protecting a position; prefer floor (SAFE-tier arms, low bust%).
  - Mean dial: +2 FP/week of true strength = +0.96pp title / +0.00pp playoffs — the scale for valuing any add/trade in equity terms.

## 6. Decision quality (settled verdicts)

- `verdict_scorecard.csv` — as-of 2026-08-24, today (file mtime) (no date column in this artifact, so the age is mtime-based)
- 10 bucket x verdict cells over 950 settled observations

| bucket | verdict | n | players | mean actual | mean proj | residual | hit rate |
|---|---|---|---|---|---|---|---|
| H | BUY | 297 | 13 | 0.548 | 0.601 | -0.053 | 0.290 |
| H | CAUTION | 36 | 4 | 0.585 | 0.562 | 0.023 | -- |
| H | FADE | 4 | 2 | 0.289 | 0.490 | -0.201 | 1.000 |
| H | MIXED | 287 | 17 | 0.537 | 0.568 | -0.031 | -- |
| RP | BUY | 89 | 4 | 5.314 | 4.923 | -0.027 | 0.191 |
| RP | MIXED | 2 | 1 | 2.555 | -- | -- | -- |
| SP | BUY | 45 | 5 | 10.936 | 11.749 | -0.813 | 0.267 |
| SP | HOLD | 4 | 1 | 12.670 | 10.809 | 1.861 | -- |
| SP | CAUTION | 98 | 8 | 12.634 | 11.268 | 1.366 | -- |
| SP | MIXED | 88 | 8 | 10.416 | 11.609 | -1.193 | -- |

## 7. Model + data health

- `model_scorecard.csv` — as-of 2026-08-24, today (content date)
- Tripwires (data_health + pipeline_staleness): PASS 35, WARN 1
- Drift sentinels (added 2026-07-29):
  - `collision_team_reachability` (all): **PASS** — 41/41 collision team hints reachable from 30 live ESPN codes
  - `collision_smoke` (all): **PASS** — 12/12 canonical resolver cases
  - `fa_join_coverage` (H): **PASS** — 229/229 FA H rows join xfp_rh3_projections.csv by mlbam; +0.000 vs trailing mean 1.000 (WARN -0.05 / FAIL -0.15)
  - `fa_join_coverage` (SP): **PASS** — 220/220 FA SP rows join xfp_rp3_projections.csv by mlbam; +0.000 vs trailing mean 1.000 (WARN -0.05 / FAIL -0.15)
  - `fa_join_coverage` (RP): **PASS** — 316/317 FA RP rows join xfp_rprs2_projections.csv by mlbam; -0.003 vs trailing mean 1.000 (WARN -0.05 / FAIL -0.15)
- Forward accuracy (all-segment headline rows):
  - `rh3_spearman_rate_7d` = 0.1233 [INFO]
  - `rh3_vs_prior_delta_7d` = -0.0306 [INFO]
  - `rp3_spearman_rate_7d` = 0.2217 [INSUFFICIENT]
  - `rprs2_spearman_rate_7d` = 0.2247 [INFO]
  - `rh3_spearman_rate_14d` = 0.2470 [INFO]
  - `rh3_vs_prior_delta_14d` = 0.0808 [INFO]
  - `rp3_spearman_rate_14d` = 0.2481 [INFO]
  - `rp3_vs_prior_delta_14d` = 0.1130 [INFO]
  - `rprs2_spearman_rate_14d` = 0.2504 [INFO]
  - `rh3_spearman_rate_21d` = 0.2873 [INFO]
  - `rh3_vs_prior_delta_21d` = 0.0976 [INFO]
  - `rp3_spearman_rate_21d` = 0.1796 [INFO]
  - `rp3_vs_prior_delta_21d` = -0.0388 [INFO]
  - `rprs2_spearman_rate_21d` = 0.2427 [INFO]
  - `rh3_spearman_rate_28d` = 0.3265 [INFO]
  - `rh3_vs_prior_delta_28d` = 0.0892 [INFO]
  - `rp3_spearman_rate_28d` = 0.3066 [INFO]
  - `rp3_vs_prior_delta_28d` = 0.1277 [INFO]
  - `rprs2_spearman_rate_28d` = 0.2675 [INFO]
- Full rendered scorecard: `model_scorecard.md` — as-of 2026-08-24, today (file mtime)

## 8. Pitcher List cache ages (no scraping here)

- Read-only: this brief does NOT fetch pitcherlist.com. Per `refresh_dashboards.py` step 7 the PL caches need a live agent WebSearch/WebFetch (deliberately not another headless scrape), so refresh them in an interactive session (`/triangulate --check-caches`).
- `pl_sps_top100.json` — fetched 2026-08-17 (7d old) — current: current (latest live Mon edition 2026-08-17 already cached)
- `pl_closers.json` — fetched 2026-08-18 (6d old) — current: current (latest live Tue edition 2026-08-18 already cached)
- `pl_hitters_top150.json` — fetched 2026-08-19 (5d old) — current: current (latest live Wed edition 2026-08-19 already cached)
- `pl_sp_streamers_latest.json` — fetched 2026-08-18 (6d old) — **STALE**: 6d old (rolling, refresh every 2d)

## 9. Provenance

| artifact | status | as-of | age | basis | regenerate with |
|---|---|---|---|---|---|
| `dpwin_history.parquet` | ok | 2026-08-24 | 0d | content date | `python scripts/xfp/run_matchup_leverage.py  (or run_weekly_optimizer.py — either appends)` |
| `matchup_leverage.json` | STALE | 2026-08-14 | 10d | content date | `python scripts/xfp/run_matchup_leverage.py` |
| `model_scorecard.csv` | ok | 2026-08-24 | 0d | content date | `python scripts/xfp/build_model_scorecard.py  (refresh step 4.97, Mondays only)` |
| `model_scorecard.md` | ok | 2026-08-24 | 0d | file mtime | `python scripts/xfp/build_model_scorecard.py  (refresh step 4.97, Mondays only)` |
| `season_sim.json` | ok | 2026-08-23 | 1d | content date | `python scripts/xfp/run_season_sim.py` |
| `verdict_scorecard.csv` | ok | 2026-08-24 | 0d | file mtime | `python scripts/xfp/run_verdict_scorecard.py  (refresh step 4.97b, Mondays only)` |
| `weekly_optimizer.json` | ok | 2026-08-24 | 0d | content date | `python scripts/xfp/run_weekly_optimizer.py` |

# Subseason variance bands — production build (2026-07-10)

Deliverable commissioned by the sub-season horizon probe
(`data/research/boxscore_era/subseason_horizons_2026-07-10.md` §4): era-general
**within-player FP variance by horizon** as honest σ inputs for
`/matchup-leverage` and `/season-sim`. Rule 13 throughout — variance/decision
layer only; rh3/rp3/rprs2 and the engines' primary per-player empirical
bootstrap path are untouched. The bands replace only the **crude fallback
constants** that bound for thin-history players.

## 1. Panel coverage

Stratified MLB Stats API gameLog panel, pulled 2026-07-10 via batched
`people?personIds=…&hydrate=stats(group=[hitting|pitching],type=[gameLog])`
(10 ids/call, `fields=` trimmed, ≤2 req/s):

- **Years:** 2010–2019 + 2021–2025 (15 seasons; 2020 short season excluded —
  era buckets 2010-14 / 2015-19 / 2021-25 partition cleanly).
- **Per year:** top 200 hitters by PA + top 80 SPs by GS (GS≥10 and GS/G≥0.5)
  + top 60 fantasy-relevant RPs (GS/G<0.2, ranked by G + 2·(SV+HLD)).
- **Total: 5,100 player-seasons**, 100% of which qualify at all three horizons
  (H 3,000 / SP 1,200 / RP 900 per horizon). ~715k player-games scored.
- Raw cache: `data/research/xfp_cache/variance_gamelog_raw/` (20 MB gz,
  gitignored, resume-safe; regenerate with
  `python scripts/xfp/build_subseason_variance_bands.py pull`).
- Wall clock: ~7 min pull + 22 s compute (the probe's 1.5–2.5 h estimate
  assumed 1 call/player-season; batching + field-trimming cut it ~20×).

## 2. Method

Per player-season: BrownU FP per game (H: R+TB+RBI+BB+HBP+SB−K, all games
PA≥1), per start (SP: K+IP·3.3−H−2ER−BB−HBP, **starts only** — relief cameos
excluded), per appearance (RP: SP formula + 5SV+2HLD, relief apps only). Then:

- **Horizons:** game; week = Mon–Sun; month = calendar. Qualifying windows:
  H PA≥15/wk, ≥50/mo; SP ≥1 start/wk, ≥3/mo; RP ≥2 apps/wk, ≥6/mo.
- **sd_fp_per_unit** = within-player SD of the window per-unit rate (H: FP/PA,
  SP: FP/start, RP: FP/app); **sd_fp_total_per_horizon** = within-player SD of
  the window total FP. Cell aggregation = √(mean within-player variance).
- **shrink_k** (empirical): regress each window's leave-window-out season rate
  on the window rate within a cell; slope b ≈ n̄/(n̄+k) ⇒ k = n̄(1−b)/b, in
  units of PA (H), starts (SP), appearances (RP). All 81 cells fit per-cell
  (min 150 windows never binding — smallest cell had 560).
- **Tiers:** T1/T2/T3 = season-volume terciles within (player_type, era).

Outputs: `data/research/xfp_cache/subseason_variance_bands.csv` (81 cells:
3 types × 3 horizons × 3 tiers × 3 eras) + per-player-season diagnostics in
`subseason_variance_panel.csv`. Builder:
`scripts/xfp/build_subseason_variance_bands.py`.

## 3. Bands headline (tier T2, sd_fp_total_per_horizon)

| type | horizon | 2010-14 | 2015-19 | 2021-25 | shrink_k (2021-25) |
|---|---|---|---|---|---|
| H  | game  | 3.18 | 3.35 | 3.33 | 621 PA |
| H  | week  | 8.23 | 8.71 | 8.38 | 654 PA |
| H  | month | 18.75 | 19.49 | 18.85 | 639 PA |
| SP | start | 9.99 | 9.92 | 9.35 | 13 starts |
| SP | week  | 12.46 | 12.30 | 11.26 | 14 starts |
| SP | month | 24.94 | 25.20 | 23.40 | 13 starts |
| RP | app   | 3.81 | 3.97 | 3.96 | 21 apps |
| RP | week  | 7.66 | 7.49 | 7.40 | 25 apps |
| RP | month | 17.68 | 16.61 | 17.02 | 31 apps |

Per-unit rates (2021-25 T2): hitter weekly FP/PA SD **0.337**, monthly
**0.168** — brackets the probe's top-45-hitter numbers (weekly 0.27–0.36,
monthly 0.135–0.157; ours sit slightly higher because the top-200 panel
includes lower-volume regulars).

## 4. Sanity / consistency checks — all pass

1. **√n check (pre-registered):** hitter weekly/monthly per-PA SD ratio =
   **2.01** vs √(PA-ratio) prediction ~2.0. Week noise is pure sampling noise.
2. **SP per-start SD 9.35–9.99** ≈ the known ~9–10 FP (and exposes the old
   `SIGMA_PER_SP_START = 5.5` dashboard constant as ~2× too tight).
3. **RP lumpier per unit than SP:** RP per-app SD ~3.9 on a ~1-IP appearance
   (~3.6 FP-SD per IP) vs SP ~9.4 on a ~5.7-IP start (~1.6 FP-SD per IP) —
   saves/holds lumpiness, exactly as expected. Old constant 2.5 was too tight.
4. **Hitter per-game SD 3.33** validates the engines' existing 3.0/3.2
   hitter fallbacks as nearly honest already.
5. **shrink_k is horizon-invariant within player type** (H ~460–650 PA,
   SP ~13–23 starts, RP ~10–31 apps across game/week/month) — required by the
   n/(n+k) model since k is in units, and it holds empirically.
6. **Era stability:** bands move <7% across 15 years (SP σ mildly tighter
   2021-25; hitter σ mildly wider post-2015) — matches the probe's 40-year
   stability finding, so quoting the 2021-25 cell is safe.
7. shrink_k quantifies the 2026-06-26 no-momentum-term rule: a hot week
   (~25 PA) deserves weight 25/(25+650) ≈ **4%** against the season mean.

## 5. Engine wiring (fallback σ only)

New shared loader **`scripts/xfp/lib/variance_bands.py`** —
`fallback_sigma(type, horizon='game', tier='T2', era='2021-25', default=…)` +
`shrink_k(…)` + `band_row(…)`; caches the CSV, degrades gracefully to the
caller's `default` if the file/cell is missing (engines can never crash on it).

- **`run_matchup_leverage.py`** (4 sites): SP-event σ when rp3 σ missing
  (was `SIGMA_PER_SP_START`=5.5 → band 9.35); RP `sigma_app` when model σ² is
  0/missing (was 2.5 → 3.96); hitter `sigma_g` when model σ² missing (was
  3.0 → 3.33); FA-streamer σ when rp3 σ missing (was 5.5 → 9.35).
- **`run_season_sim.py`** (3 sites): `DEFAULT_SIGMA_G_H` (was 3.2 → 3.33);
  SP σ fallback (5.5 → 9.35); RP `sigma_app` fallback (2.5 → 3.96).
- NOT touched: `build_matchup_dashboard.py` constants (out of scope), the
  empirical-bootstrap path, `K_PRIOR_*` blend priors (those weight the
  *distribution shape*, a different quantity than mean-regression shrink_k —
  though SP shrink_k ≈13–17 starts landing next to `K_PRIOR_SP=12` is a nice
  independent corroboration).

## 6. Before/after (same seeds; engines run live 2026-07-10 evening)

| metric | before | after | Δ |
|---|---|---|---|
| /matchup-leverage P(win), seed 42, 20k sims | 55.8% | 55.0% | **−0.8pp** |
| /season-sim P(playoffs) Ligers, seed 42 | 92.6% | 92.6% | 0.0pp |
| /season-sim P(title) Ligers, seed 42 | 10.6% | 10.6% | 0.0pp |

All moves ≪ the 3pp gate. Part of the matchup −0.8pp is live-state drift
(WTD score moved 197.6→196.6 between the two runs — games were in progress);
the wiring itself binds only where model σ is missing, i.e. thin-history
players, and most current-roster players have both model σ and ≥8-game
empirical history. Season-sim P(title)/P(playoffs) are unchanged to the
displayed decimal.

## 7. Files

- `scripts/xfp/build_subseason_variance_bands.py` — puller + computer (new)
- `scripts/xfp/lib/variance_bands.py` — shared loader (new)
- `data/research/xfp_cache/subseason_variance_bands.csv` — bands table (new)
- `data/research/xfp_cache/subseason_variance_panel.csv` — diagnostics (new)
- `scripts/xfp/run_matchup_leverage.py`, `scripts/xfp/run_season_sim.py` —
  fallback-σ wiring only
- `.gitignore` — `variance_gamelog_raw/` raw-cache pattern

No commits made. Future use: the `week`/`month` rows + `shrink_k` are ready
for CI widths on weekly matchup projections and any future horizon-window
shrinkage; consumers should read tier T2 / era 2021-25 unless they know the
player's volume tercile.

# boxscore_era — the `xfp_bx` model family

Box-score-era foundation: a deep-history (pre-Statcast) player-season panel
plus a v0 next-season xFP model. First member of the `xfp_bx` family.
Built 2026-07-10; pre-registration + results:
`data/research/validation_runs/xfp_bx_v0_2026-07-10.md`.

## Why this family exists

1. **Era-robust validation** — 40+ years of holdout instead of 2015+.
   The v0 harness holds out ENTIRE DECADES (1970s..2020s).
2. **Aging / career-arc priors on huge samples** — 14.8k hitter and 6.1k SP
   season-to-season transitions vs the few hundred the Statcast window has.
3. **A decorrelated ensemble opinion** — 2026 overlap corr vs the Statcast
   stack is 0.741 (hitters vs rh3) / 0.697 (SP vs rp3): sane but far from
   redundant.
4. **Substrate for multi-horizon xFP** — a sibling effort owns month/period
   horizons; this directory owns SEASON + the panel.

## What exists

| File | What |
|---|---|
| `build_panels.py` | Panel builder. MLB Stats API season lines (playerPool=all), cached per season-group under `raw/`. Chadwick register crosswalk. |
| `hitter_season_panel.csv` | 1960-2026, 53,293 rows. Keys: `mlbam`, `lahman_id` (= Chadwick `key_bbref` ≡ Lahman playerID), `retro_id`. Age, PA, box rates (K%, BB%, ISO, HR/PA, SB/PA, BABIP, R/PA, RBI/PA, HBP/PA), `fp_total`, `fp_per_pa`. |
| `pitcher_season_panel.csv` | 1970-2026, 31,970 rows. GS, IP/GS, K% (per BF), BB%, HR/9, ERA, box-FIP, SV, HLD, `fp_total_base`, `fp_per_start`, and RP columns (`fp_total_rp`, `fp_per_g_rp`) valid only where holds exist (~2000+). |
| `xfp_bx_v0.py` | Pair construction, Marcel-lite baseline, Ridge model (house StandardScaler+RidgeCV idiom), LOO-by-decade harness + gates. |
| `bx_v0_eval_results.json` | Per-decade + pooled r for model vs Marcel-lite, both legs. |
| `bx_v0_holdout_preds_{hitters,pitchers}.csv` | Every held-out prediction (mlbam, year, marcel, model, actual) — reusable for calibration / slicing studies. |
| `aging_curves.py` + `aging_curve_{hitters,pitchers}.csv` | Delta-method aging curves, overall + per era bucket. |
| `build_2026_output.py` | Fits on all history, emits `data/outputs/xfp_bx_season_2026.csv` (477 rows: 325 hitters + 152 SP, mlbam-keyed, 2026 rate + implied total) + rh3/rp3 comparison. |
| `raw/` | API cache (`{group}_{year}.json`) + `chadwick_register.csv`. Gitignored parquet rules don't apply; these are JSON/CSV. Delete a year's file to force a refetch. |

## Data-source notes (hard-won, don't re-derive)

- **pybaseball Lahman is broken** (stale zip URL → `BadZipFile`), and the
  chadwickbureau/baseballdatabank raw CSV path 404s. The **MLB Stats API is
  the single source**: `/api/v1/stats?stats=season&group={hitting|pitching}
  &season=YYYY&sportId=1&playerPool=all&limit=5000` returns EVERY player's
  season line for any year (verified to 1960/1970), including `age`,
  HBP, TB, SB, battersFaced. One call per season-group; paginate only if
  `totalSplits` > limit (never triggered).
- **History constraints:** HBP fine all the way back; SV official 1969+
  (pitcher panel starts 1970 so always valid); **HLD only ~2000+** → RP FP
  is fully computable only 2000+ (columns are NaN before then). SP FP is
  fine much earlier.
- `fp_per_start` = season FP / GS — swingman relief innings pollute it
  (canonical: Mlodzinski 2025). A future version should split via game
  logs if per-start purity matters.
- 2020 excluded as feature and target year; 1981/1994/1995 retained under
  volume floors (PA ≥ 200 / GS ≥ 10).

## v0 results, one line

Both legs PASS all pre-registered gates: hitters pooled LOO-by-decade
r 0.648 vs Marcel-lite 0.632 (Δ +0.016, 6/6 decades); SP r 0.521 vs 0.476
(Δ +0.046, 6/6). Statcast premium ≈ +0.05 r (hitter 2015-25 slice 0.569
vs rh3 ≈ 0.62 anchor). Hitters peak at 26 with decline STEEPENING by era
(−0.020/yr 1970s → −0.034/yr 2020s, 1990s anomaly peak 31); SP FP/start
is peak-on-arrival, declining monotonically, shallower now (−0.95 →
−0.63 FP/start/yr at 30-36).

## How to extend

- **RoS / month / period horizons:** the panel is season-grain. For finer
  horizons, either (a) rebuild from Stats API `gameLog` stats (same
  endpoint family, `stats=gameLog`) aggregated to the horizon, or (b) let
  the sibling horizon effort own the grain and consume this panel as the
  prior substrate. The pair-construction + Marcel-lite + decade-LOO code
  in `xfp_bx_v0.py` generalizes: swap the (T, T+1) alignment for
  (through-T, horizon-window) rows.
- **Aging prior → rh3/rp3:** the era-aware aging deltas are the most
  immediately valuable export (rh3's `career_stage` is a validated
  feature; a proper aging PRIOR could sharpen the Marcel priors). That is
  a **future Rule-9 candidate** — it must clear `/validate-feature`
  against the full production baseline before integration. NOT integrated.
- **Ensemble seat:** `xfp_bx_season_2026.csv` is an ensemble-research
  artifact, NOT a ranker. Any blend with rh3/rp3 needs its own prereg.
- **RP leg:** panel columns exist 2000+; no RP model was fit in v0
  (26 years only — the era-robustness rationale is weakest there).

## Refresh

Panels: `python data/research/boxscore_era/build_panels.py` (cached — only
missing years hit the API; delete `raw/{group}_{year}.json` to force).
Eval: `python data/research/boxscore_era/xfp_bx_v0.py`.
2026 file: `python data/research/boxscore_era/build_2026_output.py`.
All with the `PYTHONIOENCODING=utf-8 PYTHONUTF8=1` prefix on Windows.

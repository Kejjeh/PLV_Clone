# Hitter forward-volume model — results memo (2026-07-09)

Companion to prereg `hitter_volume_model_2026-07-09.md` (verdict **PASS**,
all 3 gates). Engine: `scripts/xfp/xfp_volume_pipeline.py`. Output:
`data/outputs/xfp_volume_projections.csv` (500 hitters, current split_day=105).

## Headline numbers

- **Pooled LOO Spearman 0.740 vs naive persistence 0.666 → Δ +0.0737**
  (gate was +0.03; 2.5× cleared). Per-year Δ positive **7/7**; holdout
  2024 +0.062, 2025 +0.088. Pooled MAE 0.682 vs 0.782 (−12.8%).
- Spearman computed within (year, split_day) cells (n ≥ 30), n-weighted —
  ranks compared only within a snapshot, never across dates.
- Calibration near-perfect by predicted tercile (pred vs actual:
  1.22/1.20, 2.36/2.34, 3.41/3.40). The naive pace over-predicts the top
  tercile by +0.32 PA/team-game — everyday regulars carry forward
  injury/rest risk that to-date pace ignores. The model's ~10% haircut on
  elite volume is validated shrinkage, not pessimism.

## What drives it (final ridge, alpha=747, n=61,231)

`pa_last21` (+0.44) dominates — recent realized volume is the strongest
forward signal — followed by `pa_per_started_game_to` (+0.20),
`pa_per_teamgame_to` (+0.19), `prior1_pa_per_g` (+0.15),
`started_pct_to` (+0.14), `lineup_spot_to` (−0.11, lower spot = fewer PA),
`career_stage` (−0.09, older = more rest/decline), `is_catcher` (−0.02 on
top of the usage features already capturing catcher rest).

## 2026 sanity checks

- Everyday top-of-order regulars: James Wood 4.38, Brice Turang 4.22,
  Gunnar Henderson 4.06 (their **naive_pace** column reads 4.3–4.7 — the
  raw-pace band — while the model projects the injury-risk-discounted
  expected value; the calibration table shows the actuals side with the model).
- Catchers: distribution median **1.52**, IQR 1.02–2.19 (backup-catcher
  band); everyday catchers Iván Herrera 3.72, Contreras 3.60; deep backups
  (Stubbs, McCann) 0.3–0.7.
- Early-season-IL regulars now back: model corrects ABOVE the season pace
  via pa_last21 — Lindor naive 1.71 → proj 2.95; Betts naive 2.65 → 3.33.
  This is precisely the failure mode of the old `expected_pa_remaining`
  (raw season pace) inside rh3's display column.

## How downstream should consume the CSV

`data/outputs/xfp_volume_projections.csv`, keyed by **mlbam_id** (never name):

```
ros_total_fp ≈ xfp_rh3_per_pa × proj_ros_pa_per_teamgame × team_games_remaining
```

- `proj_ros_pa_per_teamgame` — headline. Multiply by the consumer's own
  remaining-team-games count (or 162 − elapsed for a quick read).
- `naive_pace` — the persistence baseline (to-date PA/team-game); show the
  model−naive delta to explain WHY a ranking moved (e.g., IL-return
  corrections, top-tercile shrinkage).
- `volume_percentile` — 0–100 rank for display tiers.
- Coverage floor: pa_to ≥ 30 in 2026. Players below it (fresh call-ups,
  season-long IL) are absent — fall back to naive pace or a prior, and
  LOW-CONF flag them.
- **Do NOT wire into rh3/rp3/rprs2 or any FEATS list** — the rate models
  are untouched by design. Integration into a total-FP ranking layer
  (xfp-board, matchup dashboard, replacement-delta) is a separate step
  with its own validation. Natural first consumer: replace the naive
  `expected_pa_remaining` display column logic in downstream boards
  (rate × validated volume instead of rate × raw pace).
- Refresh: rerun `python scripts/xfp/xfp_volume_pipeline.py` after the
  daily rolling-hitters rebuild (it reads the same substrate). Not yet in
  `refresh_dashboards.py` — wiring it in is part of the integration step.

## SP analog feasibility (no build — note only)

Highly feasible. `rolling_pitchers_2018_2026.csv` already carries the
target (`ros_gs`) and the persistence anchors (`gs_to`, `gs_last21`), and
`il_split_features_2018_2026.csv` covers pitchers natively. Same design
transfers: target = RoS GS per remaining team game; features gs-pace,
gs_last21, prior-year GS, IL state, career_stage; same gates vs naive
gs-pace persistence. Extra care needed for (a) role changes (use
`detect_pitcher_role` idiom, SP/RP dual-eligibility), (b) the 10-start
weekly cap layer is a SEPARATE decision problem (volume model feeds it,
doesn't replace it), (c) `marcel_il` suppressed-prior rows must be
excluded from eval. Expected value is high: the /forced-drop-planner and
sp-week-plan cap math currently assume flat 1.19 starts/week/SP.

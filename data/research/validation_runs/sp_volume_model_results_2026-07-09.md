# SP forward-volume model — results memo (2026-07-09)

Companion to prereg `sp_volume_model_2026-07-09.md` (verdict **PASS**,
all 3 gates). Engine: `scripts/xfp/xfp_sp_volume_pipeline.py`. Output:
`data/outputs/xfp_sp_volume_projections.csv` (258 SPs, current split_day=105).
SP analog of the hitter volume model (`hitter_volume_model_2026-07-09.md`,
PASS same day) — same design, gates, and eval style.

## Headline numbers

- **Pooled LOO Spearman 0.520 vs naive persistence 0.420 → Δ +0.1001**
  (gate was +0.03; 3.3× cleared — a LARGER lift than the hitter model's
  +0.0737, because SP start pace is noisier and mean-reverts harder).
  Per-year Δ positive **7/7**; holdout 2024 +0.0852, 2025 +0.1050.
  Pooled MAE 0.0431 vs 0.0516 GS/team-game (−16.5%).
- Spearman computed within (year, split_day) cells (n ≥ 30), n-weighted —
  ranks compared only within a snapshot, never across dates.
- Calibration near-unbiased by predicted tercile (pred vs actual:
  0.092/0.088, 0.140/0.142, 0.170/0.168). The naive pace over-predicts the
  top tercile badly (0.187 vs actual 0.168): even top-tercile SPs realize
  only ~1 start per 6 team games forward — to-date pace ignores IL/skip
  risk. The model's haircut on elite volume is validated shrinkage.

## What drives it (final ridge, alpha=0.1, n=26,291)

`gs_last21` (+0.019) dominates — recent realized starts is the strongest
forward signal — then `fp_per_start_to` (+0.013; bad performers get
skipped/demoted, good ones keep the every-5th-day slot), `split_day`
(+0.010), `gs_per_teamgame_to` (+0.007), prior-year GS lags (+0.005/+0.004).
IL features carry small weight because the IL cache has only MONTHLY split
anchors (see deviations below).

## Substrate truncation + known caveats (read before consuming)

1. **`ros_gs` ≥ 1 on 100% of substrate rows** — the rolling builder emits a
   split row only when a subsequent start exists. The model ranks volume
   CONDITIONAL on at least one more start; "projects low" means FEW starts,
   never ZERO starts. The zero-start class (8% of non-IL SPs over 20 days;
   60% of IL-flagged never starting within 34 days) stays a decision-layer
   concern (`/forced-drop-planner`, `/sp-stash-finder`, ESPN return dates).
2. **IL join is asof-backward on monthly anchors** (30/60/90/120): an exact
   join on the weekly rolling splits matches <1% of rows (rp3's production
   exact join has the same property — flagged separately). Consequence:
   `is_on_il_at_split` in the CSV means "on IL at the last monthly anchor",
   up to ~4 weeks stale — context, not live state.
3. **marcel_il / prior-only pitchers are absent by construction** (no
   rolling row without to-date MLB starts) — they have no pace anchor.
   Fall back to ESPN return dates + team schedule, LOW-CONF.
4. The **10-start weekly cap** is a DECISION layer; this model projects
   supply of starts, the cap governs which ones score.

## 2026 sanity checks (all pass)

- Workhorses ~1 start per 5.2 team games: Cease 0.191, C. Sánchez 0.189,
  Misiorowski 0.188, Wheeler 0.187 (implied ~13 RoS starts each).
- IL-stint arms now active again: **90% project above season-long naive
  pace** — Hunter Brown 0.145 vs naive 0.063, Skubal 0.185 vs 0.130,
  Wheeler 0.187 vs 0.151, Boyd 0.137 vs 0.087. Exactly the correction the
  naive pace can't make.
- Recent callups (gs_to ≤ 6, no prior-year GS) land 0.10-0.13, below the
  workhorse band but ABOVE their own tiny to-date pace (a callup's season
  pace divides by team games before the callup — the model reads gs_last21
  instead). Ian Seymour 0.127 vs naive 0.056.

## How downstream should consume the CSV

`data/outputs/xfp_sp_volume_projections.csv`, keyed by **mlbam_id** (never name):

```
ros_total_fp ≈ xfp_rp3_per_start × proj_ros_gs_per_teamgame × team_games_remaining
```

- `proj_ros_gs_per_teamgame` — headline. `proj_ros_starts` is the implied
  count using 162 − team_games_to; consumers with a live schedule should
  multiply by their own remaining-games count instead.
- `naive_pace` — the persistence baseline; show model−naive to explain WHY
  a ranking moved (IL-return corrections, top-tercile shrinkage).
- `volume_percentile` — 0-100 rank for display tiers.
- Coverage: gs_to ≥ 2 in 2026 with a snapshot in the last 14 days (rp3's
  recency idiom). Trust the rate side only where rp3's `data_quality_tag`
  is `data_driven_*`; for `marcel_il` arms neither model has a real read.
- **Do NOT wire into rh3/rp3/rprs2 or any FEATS list** — rate models
  untouched by design. Ranker/board integration (xfp-board, matchup
  dashboard, `/sp-week-plan` cap math replacing the flat 1.19 starts/week
  assumption) is a separate step with its own validation.
- Refresh: rerun `python scripts/xfp/xfp_sp_volume_pipeline.py` after the
  daily rolling-pitchers rebuild. Not yet in `refresh_dashboards.py` —
  wiring it in is part of the integration step.

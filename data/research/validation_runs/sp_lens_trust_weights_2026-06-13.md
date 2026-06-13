# SP RoS-FP/start lens trust weights (2026-06-13)

Empirical ranking of **how much to trust each SP rest-of-season lens** at
predicting realized RoS FP/start, for a trust-weighted synthesis (Framber-style
prediction table). Each lens scored as a STANDALONE predictor + its INCREMENTAL
value over the base rank.

**Method** (`lens_value_add_2026-06-11.md` discipline):
- Eval set: `data/research/xfp_cache/rolling_pitchers_2018_2026.csv`, leakage-safe
  as-of-split features + `ros_fp_per_start` target. Filters `gs_to>=2`, `ros_gs>=5`,
  drop 2020. **n = 19,471 split-rows / 777 pitchers, 2018-2026** (Stuff+ subpop n=12,084).
- **Player-clustered CV** (`GroupKFold` on `pitcher`, 5 folds) — no pitcher in
  train+test. All learned lenses are z-scored RidgeCV; single-column lenses scored raw.
- Per lens: standalone **Spearman / Pearson / MAE** vs realized RoS FP/start, plus
  **incremental partial-r over the base** (rp3-core, re-fit OOS on each subpop), the
  metric that matters for additive synthesis weight.
- Subpop-limited lenses scored on their valid subpop and flagged.
- **Archetype T+1 is a different horizon** — next-SEASON `next_fp` on
  `sp_archetype_career_panel.parquet` (n=1,334 SP-years), base = current-year
  `fp_per_start` carry-forward. NOT comparable head-to-head with in-season RoS rows.

**Base caveat:** "rp3 per_start (core)" is a faithful proxy refit on the rp3 features
present in the raw panel (in-season K%/BB%/SwStr%/CSW/xwOBA/zone/velo/season-FP/gs +
split_day). The IL/within-season-delta/RoS-schedule add-ons (each validated at only
+0.01–0.015 r) are not reconstructed here, so the base slightly understates production
rp3 — incremental partials are therefore mild **upper bounds**.

## The table

| Lens | n | Spearman | Pearson | MAE (FP) | Partial-r over base | Trust tier | Best for / blind to |
|---|---|---|---|---|---|---|---|
| **rp3 per_start (core)** | 19,471 | **0.498** | 0.502 | **2.97** | — (is base) | **HIGH** | Best all-round in-season rank; blind to thin-data/IL arms (marcel_il artifact) |
| **Stuff+ projection** | 12,084 | 0.446 | 0.449 | 2.97 | **0.182** | **HIGH** | Best *additive* lens — process signal rp3 misses; blind to command/walks & non-FG arms |
| **Sustainability E[ROS]** | 19,471 | 0.476 | 0.482 | 3.02 | 0.064 | **MED** | Strong standalone but mostly redundant w/ rp3; needs Statcast; weak as additive term |
| **Blended xFP (proxy)** | 18,001 | 0.437 | 0.445 | 3.26 | 0.079 | **MED** | Robust composite; blind to process — adds little once rp3 is in |
| **Recent actuals (L5)** | 18,001 | 0.313 | 0.320 | 4.98 | 0.051 | **LOW** | Conviction/streak context only; high MAE, noisy; do NOT move the point forecast |
| **talent_prior (marcel)** | 19,471 | 0.252 | 0.284 | 3.36 | 0.150 | **LOW→MED (subpop)** | The fallback for IL / thin-data arms; weak in-season but a real additive anchor |
| ↳ talent_prior (gs_to≤5) | 3,802 | 0.130 | 0.238 | 3.43 | **0.190** | **MED (its niche)** | On thin-data arms (its valid subpop) it adds most — use ONLY here |
| **Archetype T+1** *(next-season)* | 1,334 | 0.511 | 0.550 | 2.48 | **0.324** | **HIGH (off-horizon)** | Best for draft / year-ahead talent; NOT an in-season RoS read — horizon mismatch |

## Trust ranking (for synthesis weights)

In-season RoS prediction, by **additive** trust weight (partial-r over base):

1. **rp3 per_start (core)** — HIGH — the headline / base rank. Spearman 0.498, lowest MAE.
2. **Stuff+ projection** — HIGH — the single best *additive* lens (partial-r **0.182**).
   It earns real weight on top of rp3 because it carries process signal (pitch shape)
   rp3 doesn't fully capture. Confirms the validated 2026-06-06 read (Stuff+ partial-r
   ≈0.30 vs results-only; smaller here because rp3-core already holds velo/whiff).
   Command/Location+ stays excluded (REJECTED for points scoring).
3. **talent_prior (marcel)** — context-dependent — LOW in-season overall (0.252) but
   partial-r **0.150** all-rows and **0.190** on thin-data arms. **Use as the primary
   anchor ONLY for marcel_il / IL / gs_to≤5 arms** where rp3 is a suppressed prior;
   near-zero added weight for established arms.
4. **Blended xFP** — MED — solid standalone (0.437) but only +0.079 over rp3; a
   convenience composite, not an independent edge.
5. **Sustainability E[ROS]** — MED — high standalone (0.476) is mostly rp3 redundancy;
   only +0.064 additive. Matches `lens_value_add` "non-additive" finding — keep as a
   **Tier-B confidence gate**, not a point-forecast mover.
6. **Recent actuals (L5)** — LOW — Spearman 0.313, MAE 4.98 (worst). Pure recency noise
   as a point forecast. Per Don't-#13: use for **conviction / conflict surfacing**
   (boom-bust context), NEVER to move the number.
7. **Archetype T+1** — HIGH but **OFF-HORIZON** — strongest on its own panel (0.511,
   partial-r 0.324) but predicts NEXT SEASON, not in-season RoS. Weight it in
   **draft / keeper / year-ahead** synthesis only; do not blend into a same-season RoS table.

### Headline discipline
Per Don't-#13, the synthesis HEADLINE number stays **rp3/Stuff+**. The lens stack is for
**conviction and conflict**, not free R². Recommended additive weights (in-season RoS):
rp3 base 1.0 · Stuff+ ~0.35 · talent_prior ~0.15 (thin-data only, else ~0) · everything
else ≈ context-only (0 additive). Archetype-T+1 belongs to the year-ahead table.

Artifacts: `scripts/_oneoff/sp_lens_trust_eval_2026-06-13.py`,
`data/research/validation_runs/sp_lens_trust_weights_2026-06-13.json`.

---
signal: milb_aaa_xwoba_prior
formula: prior-season (year-1) AAA xwOBA per batter; intended as a Statcast-quality skill complement to milb_aaa_kpct_prior.
outcome: ros_fp_per_pa (rh3 production target)
expected_sign: positive (higher AAA xwOBA → better MLB hitter outcomes)
theory: AAA Statcast xwOBA is the direct skill measure K% and ISO only proxy. If AAA xwOBA + AAA K% bundles for joint >+0.005 Δr, the MiLB data layer clears the Rule 9 gate and becomes promotable.
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: (none — DATA GAP, not run)
data_layer_script: (none — DATA GAP, not built)
date: 2026-05-24
verdict: BLOCKED-DATA-GAP
purpose: Test AAA xwOBA as a stronger skill carryover than counting-stat K%/ISO. Pair with milb_aaa_kpct_prior (today MARGINAL +0.0031) to attempt joint +0.005 bundle.
---

# Pre-registration body

## Why this candidate

K% prior validated MARGINAL today (+0.0031, 6/7 sign, 2/2 holdout). Pre-reg's
suggested next-step was to add AAA xwOBA — a direct Statcast skill measure
rather than a counting-stat rate. If xwOBA prior contributes independent
lift, the bundle may clear the +0.005 gate.

## Rule 5 sample-size constraint (planned)

AAA Statcast began **2021**. So even in the best case:
- AAA seasons 2021/22/23/24/25 → MLB rolling years 2022/23/24/25/26.
- Of the 7 rh3 training folds (2018, 19, 21, 22, 23, 24, 25), only **4**
  (2022, 23, 24, 25) get a real prior xwOBA value. The other 3 fold to
  population-median fill — same NaN-fill scheme as milb_aaa_kpct_prior.
- Per-year sign threshold relaxed to **3/4** on the years with real data.
- Bundle (kpct + xwoba) target: clear +0.005 to promote.

---

# DATA GAP — not run

## What was attempted (2026-05-24)

1. **pybaseball.statcast_minor_league_batter** — not present in
   pybaseball 2.2.7. Searched `dir(pybaseball)` for `minor` / `milb` /
   `statcast` — only MLB endpoints exist. No undocumented function found
   in `pybaseball.statcast` submodule either.

2. **Baseball Savant leaderboard CSV** — endpoint
   `/leaderboard/expected_statistics?type=batter&...&csv=true` returns
   the MLB leaderboard regardless of `hfMinors=AAA`, `level=AAA`,
   `statType=minorBatter`, or `type=minorBatter`. The minorBatter HTML
   page (`?type=minorBatter`) embeds JSON in a `<script>var data=...`
   block, but verified those embedded values are MLB stats, not AAA
   (Duran/Ohtani/Henderson lead the supposed "minorBatter" leaderboard).
   The Savant JS bundle (`expected-stats.js`) contains no `minorBatter`
   branch — i.e. that tab is non-functional.

3. **MLB Stats API `/stats?stats=expectedStatistics&sportId=11`** —
   returns 200 OK with AAA-tagged sport records, BUT the stat values
   are NOT seasonal xwOBA. Verified: Jordan Diaz (id 672478) actually
   hit .301 / .362 / .529 with 436 PA at AAA in 2024 (per the
   counting-stat pull at sportId=11); this expectedStatistics endpoint
   returns avg .118 / woba .179 for him. Across the 136 "qualified"
   AAA hitters returned, woba values cluster around 0.05-0.20 — about
   half the actual AAA xwOBA scale. Endpoint appears to apply an
   undocumented split filter (perhaps a specific count or game state)
   that makes its output not interpretable as season AAA xwOBA. Cannot
   be repaired from the public API surface.

4. **Baseball Savant `/statcast-search-minors/csv`** — pitch-level CSV
   works (200 OK), returns columns including
   `estimated_woba_using_speedangle` and `events`. But responses are
   **hard-capped at 25,000 rows** per request, which for 2024 returned
   only Sep 27 – Oct 30 (~5 weeks). A full-season pull would require
   ~5 date-chunked requests per year × 5 seasons (2021-25) × ~17 MB
   each ≈ 425 MB + custom server-side xwOBA aggregation (separating
   walks / HBP / SF from BIP-only `estimated_woba_using_speedangle` and
   applying linear weights). Feasible but a substantial new data-layer
   build that exceeds the time-box and risks introducing aggregation
   bugs (xwOBA formula sensitivity to event-type weighting, intent-walk
   handling, etc.).

## Verdict: BLOCKED-DATA-GAP

No xwOBA prior can be built without a from-scratch pitch-level
aggregation pipeline. **No code shipped** for `milb_aaa_xwoba_prior` —
no data layer, no validator. RH3_FEATS unchanged.

## Recommended next session

A dedicated multi-hour build that:
1. Implements `build_milb_aaa_xwoba_priors.py` against
   `/statcast-search-minors/csv` with date-chunked pulls (≤25K rows
   each), aggregating to per-batter-season:
   - Sum of `estimated_woba_using_speedangle * (1 - is_pa_terminal_non_bip)`
     for BIP outcomes
   - Linear-weight injection of walks (`woba_walk≈0.69`), HBP (`0.72`),
     IBB exclude per fangraphs convention
   - PA-weighted xwOBA per batter-season
2. Cross-validates against the few MLB-debuted players in the existing
   `milb_hitters_2015_2026.csv` to confirm the agg matches public
   sources (Fangraphs, Savant when available).
3. Then re-runs validation per this pre-reg's training/holdout split.

Estimated complexity: ~half-day. Worth doing because K% prior at
+0.0031 is the strongest MARGINAL candidate in 20+ recent attempts —
xwOBA is plausibly the missing direct-skill complement.

## Bundle test note

The companion pre-reg `milb_aaa_bundle_2026-05-24.md` is **also blocked**
by this same data gap — bundle = kpct + xwoba, so without xwoba the
bundle cannot be evaluated. K%-alone already validated MARGINAL today
(see `milb_aaa_kpct_prior_2026-05-24.md`).

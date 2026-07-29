---
signal: inseason_discipline_composite
formula: >
  At each (batter, year, split_day) with split_day >= 79, pair the snapshot
  with the same batter-year's snapshot at split_day - 42 (exact match on the
  7-day grid; the 121/125 off-grid pair is dropped). EARLY = season-to-date
  counts at the lagged snapshot; RECENT = current _to counts minus lagged _to
  counts (the last ~42 days). Component deltas, all computed from raw counts:
  d_chase = chase(RECENT) - chase(EARLY); d_zswing = zswing(RECENT) -
  zswing(EARLY) where zswing = (swing - o_swing)/in_zone; d_bb = bb_pct(RECENT)
  - bb_pct(EARLY); d_k = k_pct(RECENT) - k_pct(EARLY). Composite =
  z(-d_chase) + z(d_zswing) + z(d_bb) + z(-d_k), z-scored within (year,
  split_day) cell, averaged over available components (require all 4).
  Min sample: EARLY pitches >= 300, RECENT pitches >= 300, RECENT in_zone
  >= 80, RECENT out_zone >= 80.
outcome: ros_full_fp_per_pa (rolling_hitters_2018_2026.csv), EVAL_PA_MIN=50,
  ROS_PA_MIN=100, matching production rh3 eval frame
expected_sign: +
theory: A hitter whose swing decisions (chase down, zone-swing up, BB up,
  K down) improved over the recent ~6 weeks relative to his own early-season
  self carries forward skill change not yet fully priced into his
  season-to-date levels.
production_target: rh3
framing: in-season -> ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_inseason_discipline.py
date: 2026-07-29
verdict: MARGINAL
---

# In-season discipline composite — pre-registration

## Motivation

2026-07-29 session: an FA-pool sweep ranked hitters by in-season
swing-decision improvement (EARLY -> MID -> LATE windows, two-window
confirmation). Surfaced Trevor Larnach / Jared Triolo as top improvers.
Question: does this composite carry forward-FP signal beyond the full rh3
baseline, or is it already subsumed by the season-to-date levels
(chase_pct_to_sh, k_pct_to_sh, bb_pct_to_sh, whiff_pct_to_sh are ALL
already in RH3_FEATS)?

## Prior art this must overcome

- CLAUDE.md #12 (2026-06-26): recent form adds ~0 beyond the full running
  season level; of all process metrics only bat speed added incremental
  forward-FP signal. K%/BB% deltas were in the redundant set. Chase and
  zone-swing deltas were NOT explicitly tested -> that is the open question.
- Registry 2026-05-25: trajectory slope features REJECTED for rp3 (causal
  version +0.0000). Hitter-side deltas not identically tested.
- recent_signal_tournament (whiff_pct_trailing21): recent-window signals must
  Rule-9 diff against RH3_FEATS before proposing.

## Rule 5 pre-check

Source: rolling_hitters_2018_2026.csv — pitch-level derived counts back to
2018, all components available all years (no bat-tracking dependency).
7 training-eligible years (2018-2025 ex 2020), well over the 5-of-7 bar;
per-year n after the split_day >= 79 + min-sample gates expected in the
thousands (verified in-script; abort if < 30/yr). PASSES pre-check.

## Gates (declared)

- (a) pooled partial r >= 0.10 vs the most obvious prior baseline
  (season-to-date levels of the same four metrics + prior_fp_per_pa)
- (b) sign consistency >= 5 of 7 training years (2020 excluded per
  production convention)
- (c) holdout 2024-2025 partial r >= 0.05, same sign
- Integration: cross_year_r(RH3_FEATS + candidate) -
  cross_year_r(RH3_FEATS) >= +0.005 strict bar (Rule 9: all 22 features)
- Rule 8: convergence across split_day cutoffs {79..191}; sign must not
  flip across cutoff bands
- Bonferroni: single pre-registered composite, no sweep. The 4 components
  are reported individually as DIAGNOSTICS only, not selected-over.

## RESULT (2026-07-29, run on 15,396 rows, splits 79-170)

- **(a) FAIL** — pooled partial r **+0.046** vs the +0.10 bar
  (train 2018-2023 ex 2020, n=10,725).
- **(b) 4/5 train years positive** (2018 the lone negative at -0.002);
  holdout years also positive -> 6/7 overall. Passes.
- **(c) PASS** — holdout 2024-2025 partial r **+0.090** (n=4,318),
  same sign, above the +0.05 bar.
- **Integration (Rule 9, the headline): FAIL/MARGINAL** — cross-year r
  +0.6720 -> +0.6724, delta **+0.0004** vs the +0.005 strict bar.
  Per-year deltas -0.0011..+0.0012, sign-unstable.
- **Rule 8 band stability:** +0.037 (d79-107) / +0.063 (d108-142) /
  +0.006 (d143-191). Sign-stable, magnitude fades late-season (RoS
  window shrinks -> noise dominates). No flip; passes but weak.
- **Components (train | holdout):** d_k -0.054|+0.070 and d_zswing
  +0.055|+0.022 carry the signal; d_chase (-0.014|+0.049) and d_bb
  (+0.009|+0.048) are unstable between eras.
- **Curiosity, not a claim:** per-year partial r rises monotonically
  2018 -> 2025 (-0.002 -> +0.099). Consistent with recent-form signal
  strengthening in the modern run environment, but establishing that
  would need its own pre-registered test.

> **SUPERSEDED SAME DAY — read with `inseason_delta_grid_2026-07-29.md`.**
> The +0.090 holdout above was AUTOCORRELATION-INFLATED: overlapping
> 7-day-grid snapshots of the same batter-year were treated as independent.
> Under the grid's non-overlapping design (the correct one), no cell of the
> family generalizes — the hard_hit lag42 screen survivor died at holdout
> −0.002 and the family is CLOSED. Treat this run's standalone gates as
> optimistic; the MARGINAL/no-promote verdict stands, the "real-but-small
> standalone signal" framing does not.

**Verdict: MARGINAL.** The composite is real-but-tiny standalone
(clears holdout, misses effect size) and adds **+0.0004** against the
full 22-feature production baseline — the season-to-date levels already
in RH3_FEATS (chase/k/bb/whiff `_to_sh`) absorb nearly all of it,
exactly the CLAUDE.md #12 "recency adds ~0 beyond the season level"
result reproduced on the decision-metric axis. Do NOT add to RH3_FEATS.
Legitimate uses: Rule-13 context lens / conviction tie-breaker (the
d_k and d_zswing components are the defensible halves), same tier as
xwOBA-L21d.

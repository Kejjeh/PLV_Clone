---
signal: inseason_delta_grid (full family sweep + empirical cutoff study)
formula: >
  PART A (cutoff stabilization): for each of 12 rate metrics, forward
  reliability curve r(metric_to at sample-size bucket, metric_rest_of_season)
  across batter-snapshots, where rest = multiyr season count minus _to count.
  Empirical cutoff = interpolated sample size where forward r crosses 0.50
  (decision floor) and 0.70 (high confidence). Denominator matched to metric
  (pitch-based by pitches_to, PA-based by pa_to, contact-based by bip_to).
  PART B (delta grid): d_metric = RECENT(lag L) - EARLY(to split_day - L),
  from raw counts only, for every metric M in the declared list and every lag
  L in {21, 42, 63, 84} days, plus 3 declared composites per lag.
  NON-OVERLAPPING snapshots only: for lag L keep split_days spaced >= L apart
  starting at 79 (21: 79,100,121,142,163,184 | 42: 79,121,163 | 63: 79,142 |
  84: 79,163) so no batter-year contributes overlapping windows.
outcome: ros_full_fp_per_pa, EVAL_PA_MIN=50, ROS_PA_MIN=100 (production frame)
expected_sign: per-metric, declared in the cell table below
theory: If any in-season skill-change axis carries forward signal beyond the
  season-to-date levels already in RH3_FEATS, it should survive a
  multiplicity-corrected screen AND the Rule-9 integration bar; the 2026-06-26
  study predicts near-total mortality, and this sweep closes the family
  either way.
production_target: rh3
framing: in-season -> ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_delta_grid.py (Part B),
  scripts/xfp/validate_cutoff_stabilization.py (Part A)
date: 2026-07-29
verdict: REJECTED
---

# In-season delta grid + empirical cutoff study — pre-registration

## Declared cells (Rule 3 — counted BEFORE any result is seen)

12 metrics x 4 lags = 48 single cells + 3 composites x 4 lags = 12
-> **60 cells total**, one outcome, one frame. No cell added after results.

| # | metric | expected sign | denominator |
|---|---|---|---|
| 1 | chase (o_swing/out_zone) | − | pitches |
| 2 | zswing ((swing−o_swing)/in_zone) | + | pitches |
| 3 | z_contact (z_contact/z_swing) | + | pitches |
| 4 | whiff (1 − contact/swing) | − | pitches |
| 5 | swstr (swstr/pitches) | − | pitches |
| 6 | k_pct (k/pa) | − | pa |
| 7 | bb_pct (bb/pa) | + | pa |
| 8 | hard_hit (hard_hit_n/bip) | + | bip |
| 9 | barrel (barrel_n/bip) | + | bip |
| 10 | xwoba_ppa (xwoba_per_pa reconstructed sum/pa) | + | pa |
| 11 | iso ((tb−h)/ab) | + | ab |
| 12 | hr_ppa (hr/pa) | + | pa |
| C1 | discipline4 = z(−1)+z(2)+z(7)+z(−6) | + | mixed |
| C2 | contact3 = z(8)+z(9)+z(10) | + | mixed |
| C3 | all7 = C1 + C2 | + | mixed |

## Multiplicity control (the statistical upgrade, declared)

1. **Non-overlapping windows** — snapshots spaced >= lag apart, killing the
   within-batter-year autocorrelation that inflated every prior
   overlapping-anchor sweep's effective n.
2. **Screen:** pooled partial r on TRAIN years only, controls =
   [same-metric level `_to_sh` where it exists else raw `_to` rate,
   prior_fp_per_pa, pa_to]. p-values via t on Fisher-stable partial r,
   df = n − q − 2. **Benjamini-Hochberg FDR at q = 0.05 across all 60
   cells** + an economic-significance floor |partial r| >= 0.05
   (statistical pass with trivial effect does not advance).
3. **Holdout gate:** survivors must show same-sign partial r >= 0.05 on
   2024-2025 (never touched by the screen).
4. **Integration gate (Rule 9):** survivors of 2+3 get the full
   leave-one-year-out RidgeCV test vs ALL 22 RH3_FEATS; bar >= +0.005
   mean cross-year r. This is the only gate that can promote.
5. Part A cutoffs REPLACE the hand-picked minimums: each cell's min
   sample = the metric's empirical r>=0.50 crossing (rounded up to the
   nearest 25), both EARLY and RECENT windows. If Part A shows a metric
   never stabilizes within a lag window's plausible sample, its cells
   are reported as UNDERPOWERED, not tested-and-failed.

## Prior art being tested at scale

CLAUDE.md #12 (recency ~0 beyond season level), the 2026-07-29
discipline-composite MARGINAL (+0.0004 integration), 2026-05-25 rp3
trajectory rejections. This sweep either finds the exception or closes
the entire in-season-delta family for rh3 in one registry entry.

## RESULT (2026-07-29, same day — both parts run)

### Part A — empirical cutoffs (validate_cutoff_stabilization.py, 91,628
snapshots 2018-2026 ex 2020; forward r vs rest-of-season)

| metric | r=0.50 at | r=0.70 at | empirical min (ceil 25) |
|---|---|---|---|
| chase | 150 pitches (r already .72 in first bucket) | 150 | **150 pitches** |
| zswing | 150 | 168 | **150 pitches** |
| z_contact | 150 | 168 | **150 pitches** |
| whiff | 150 (.75 first bucket) | 150 | **150 pitches** |
| swstr | 150 | 218 | **150 pitches** |
| k_pct | 38 PA | 135 PA | **50 PA** |
| bb_pct | 154 PA | never in-window | **175 PA** |
| hard_hit | 30 BIP | 121 BIP | **50 BIP** |
| barrel | 40 BIP | 162 BIP | **50 BIP** |
| xwoba_ppa | 203 PA | never | **225 PA** |
| iso | 239 AB | never | **275 AB** |
| hr_ppa | 244 PA | never | **275 PA** |

Grades our prior hand-picks: 300 pitches for swing-decision metrics was
2x conservative (150 suffices); a 21-day window (~250 pitches, ~90 PA)
is ADEQUATE for chase/zswing/whiff/K and hard-hit, INADEQUATE for
BB% (needs 175 PA ~ 6-7 wks) and for xwOBA/ISO/HR deltas (need most of
a season — in-season power-delta claims are essentially unmeasurable
at window scale). This explains the composite's era-unstable d_chase/
d_bb halves: d_bb was noise by construction at 42d.

### Part B — 60-cell grid (validate_delta_grid.py)

Frames (non-overlapping): lag21 n=7,729 | lag42 n=3,892 | lag63 n=1,312 |
lag84 n=75. 25/60 cells testable — the other 35 UNDERPOWERED by the
Part-A minimums (all xwoba/iso/hr cells; bb_pct below lag63; all lag84),
reported as unmeasurable, not failed.

- **Stage 1 (BH-FDR q=.05 + |r|>=.05 floor):** exactly **1 of 25**
  survived — hard_hit lag42, train partial +0.081. (discipline4 lag63
  hit +0.102 but missed FDR at its n.)
- **Stage 2 (holdout):** hard_hit lag42 -> 2024-25 partial **-0.002**
  (n=799). **DIES.**
- **Stage 3 (Rule 9):** zero finalists. Family closed.

Key methodological finding: yesterday's overlapping-anchor holdout
(+0.090) was inflated by within-batter-year window autocorrelation —
under non-overlapping windows with same-metric level controls, no cell
generalizes. The non-overlap design is the correct default for all
future window studies.

**Verdict: REJECTED — the entire in-season-delta family (12 metrics x
feasible lags, 3 composites) adds nothing to rh3 beyond season-to-date
levels.** Matches CLAUDE.md #12 at 60-cell scale. Part A's empirical
minimums are the durable deliverable: adopted as the canonical
sample-size gates for any future window/lens work (display lenses
included). Do not re-open without a structural data change (e.g.
in-season bat-speed deltas when the gf bridge carries swing speed).

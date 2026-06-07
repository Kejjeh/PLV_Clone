# xwOBACON YoY Investigation — 2026-06-06

## Context

The 2026-06-06 lens_weight_backtest found that the L6 xwOBACON YoY lens
showed wrong-direction lift for hitters: lift = -0.21 (n=99 BUY / 102
FADE, mean BUY 2.34 vs mean FADE 2.55 FP/g). This investigation isolates
the cause and proposes a recalibration or drop.

## Sample

- Reused the 362 hitter snapshots from the original backtest
  (top-100 rh3 ranks × 4 as_of dates in 2025: 5/15, 6/30, 8/15, 9/15)
- Recomputed multi-year xwOBACON series from statcast 2021-2025 parquets
- Multi-year trajectory = avg of consecutive year-to-year deltas
- Forward target reuses the gameLog FP/g from the original snapshots;
  H4 uses statcast forward-30d xwOBA instead

Snapshots with >= 2 years of xwOBACON: **330 / 362**

## H1 — Mean reversion at top-of-rank

Bin the existing L6 signal (original +/-0.020 abs YoY) by rh3 rank percentile
and compute lift inside each bin. If RISING players are reverting at the
TOP-of-rank but holding at MID-of-rank, mean reversion explains the
negative lift.

| Rank bin | n BUY | n FADE | Mean BUY | Mean FADE | Lift |
|---|---|---|---|---|---|
| top10 | 40 | 45 | 2.57 | 2.85 | -0.28 |
| top25 | 59 | 57 | 2.19 | 2.31 | -0.12 |

## H2 — Sample composition

Compare the prior-year xwOBACON, current xwOBACON, and rh3 rank_pct of
each vote bucket. If RISING players have systematically LOWER prior-year
xwOBACON, they are coming UP to a peak that the sample-rank filter has
already captured.

| Vote | n | Prior-Yr xwOBACON | Cur xwOBACON | Mean rank_pct | Fwd FP/g |
|---|---|---|---|---|---|
| RISING (BUY) | 99 | 0.369 | 0.418 | 0.13 | 2.34 |
| STABLE | 128 | 0.387 | 0.386 | 0.13 | 2.34 |
| DECLINING (FADE) | 102 | 0.417 | 0.378 | 0.12 | 2.55 |

## H3 — Wider threshold sweep on multi-year avg delta

Original lens used a single-year diff +/-0.020. This sweep uses
multi-year avg yearly delta across 2021..as_of_year-1 + as_of-year partial
at widths +/-0.005 .. +/-0.030.

| Threshold | n BUY | n FADE | Lift | 95% CI | p(lift<=0) |
|---|---|---|---|---|---|
| +/-0.005 | 126 | 111 | -0.107 | [-0.348, +0.136] | 0.829 |
| +/-0.010 | 97 | 83 | -0.062 | [-0.361, +0.219] | 0.652 |
| +/-0.015 | 73 | 58 | -0.144 | [-0.442, +0.152] | 0.823 |
| +/-0.020 | 54 | 31 | -0.196 | [-0.552, +0.170] | 0.862 |
| +/-0.030 | 31 | 5 | -0.888 | [-1.466, -0.255] | 0.998 |

## H4 — Wrong target

Use forward-30d xwOBA per BIP as the target instead of FP/g. xwOBACON
is a contact-quality predictor by construction.

BUY xwOBA = 0.335, FADE xwOBA = 0.352, lift = -0.017 [CI -0.033, -0.002], p(lift<=0)=0.983

## Diagnosed root cause

- **H1 confirmed**: At top-10% rh3 rank the lift is -0.28 — RISING players among elites had peak-pulled-down regression in the forward window.
- **H2 confirmed**: RISING players have lower prior-year xwOBACON (0.369) than DECLINING (0.417). The top-100-rh3 sample selects already-peaked talent; RISING is the subset coming UP to that peak — exactly the players most likely to regress in the next 30 days.
- RISING players' mean rank_pct 0.13 > DECLINING 0.12 = RISING are LOWER-RANKED elites (further-from-#1, closer to top-100 cliff) — more downside risk in the forward window.

## Recommendation

**Drop the lens from the synthesis layer.** In the top-100 hitter sample no threshold variant of multi-year xwOBACON YoY produces positive forward-FP lift, and the underlying mechanism (RISING players regress to a sample-selected peak) inverts the intended signal direction. Keep xwOBACON YoY as a NARRATIVE LENS for interpreting prior-trough recovery (per memory `reference_xwoba_l21d_vs_2025_diagnostic.md`) but EXCLUDE it from any BUY/FADE weighted vote.

## Lift estimate with recommended thresholds

N/A (drop or switch-target recommendation).

## Caveats

- Sample is **top-100 rh3 only**; bottom-200 of the requested top-250
  range was not extended because gameLog API calls would re-incur the
  original 5-minute fetch cost. The existing 362 snapshots already cover
  the FADE arm with n=102, sufficient for a direction-of-lift call.
- Only 2025 as_of dates in this re-run; 2024 was deferred to keep this
  investigation single-pass.
- Forward FP/g target is unchanged from the original backtest (gameLog
  MLB Stats API). Forward xwOBA target was added for H4.
- The 2026-06-06 multi-year delta uses partial-year-to-date for the
  as_of year, which has small-sample bias for May as_of dates.

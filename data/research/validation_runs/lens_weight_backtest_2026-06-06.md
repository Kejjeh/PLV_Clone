# Lens Weight Empirical Backtest — Sample (2026-06-06)

## Method

- Player sample: top 100 hitters by xfp_rh3 rank + top 50 SPs by xfp_rp3 rank
- As-of dates: 2025-05-15, 2025-06-30, 2025-08-15, 2025-09-15
- Forward window: 30 days from each as_of
- Forward FP: MLB Stats API gameLog, BrownU canonical scoring
- Lens votes: computed strictly from Statcast / gameLog dated <= as_of
- 2024 full-season xwOBA used as the "established skill baseline" for L5 (a 2025
  in-season baseline would self-leak through future games)
- Encoding: BUY=+1, HOLD=0, FADE=−1; lift = mean(BUY) − mean(FADE)
- Bootstrap CI: 2000 resamples each side, independent

Resulting snapshots: **511** (362 hitter rows, 149 SP rows)

## Hitters — per-lens lift

| Lens | n BUY | n FADE | Mean BUY FP/g | Mean FADE FP/g | Lift | 95% CI | p(lift<=0) |
|---|---|---|---|---|---|---|---|
| L1_blend | 175 | 0 | — | — | INCONCLUSIVE | — | — |
| L2_rank | 362 | 0 | — | — | INCONCLUSIVE | — | — |
| L3_boom | 133 | 44 | 2.59 | 2.12 | +0.47 | [+0.20, +0.75] | 0.000 |
| L4_sust | 56 | 0 | — | — | INCONCLUSIVE | — | — |
| L5_xwoba_l21 | 85 | 31 | 2.43 | 2.43 | -0.01 | [-0.38, +0.35] | 0.497 |
| L6_xwobacon_yoy | 99 | 102 | 2.34 | 2.55 | -0.21 | [-0.46, +0.04] | 0.948 |

## SPs — per-lens lift

| Lens | n BUY | n FADE | Mean BUY FP/g | Mean FADE FP/g | Lift | 95% CI | p(lift<=0) |
|---|---|---|---|---|---|---|---|
| L1_blend | 56 | 0 | — | — | INCONCLUSIVE | — | — |
| L2_rank | 149 | 0 | — | — | INCONCLUSIVE | — | — |
| L3_boom | 62 | 29 | 15.14 | 9.69 | +5.44 | [+2.65, +8.03] | 0.000 |
| L4_sust | 51 | 36 | 13.42 | 12.85 | +0.58 | [-2.22, +3.16] | 0.347 |

## Recommended weights (proportional to positive lift)

### Hitters
| Lens | Lift | Recommended weight |
|---|---|---|
| L3_boom | +0.47 | 1.00 |

### SPs
| Lens | Lift | Recommended weight |
|---|---|---|
| L3_boom | +5.44 | 0.90 |
| L4_sust | +0.58 | 0.10 |

## Lenses with NEGATIVE lift (wrong direction in this sample)

Hitters: L5_xwoba_l21, L6_xwobacon_yoy

SPs: _none_

## Lenses inconclusive (sample too small to read)

L1_blend, L2_rank, L4_sust; SPs: L1_blend, L2_rank

## Caveats

- **Sample size**: top-of-rank skews toward high-talent players, compressing the
  fade tail. A balanced sample drawn from across the rh3/rp3 distribution would
  give cleaner FADE groups.
- **As-of timing**: only 4 dates × (100+50) players = upper bound
  ~600 snapshots before exclusions for IL / insufficient games.
- **Recency leak**: L1 and L2 use the current (2026) rh3/rp3 rank as a proxy for
  rank-at-T because no historical rank snapshots exist for 2025. This means L2
  in particular has end-of-season information baked in and will look STRONGER
  here than it would in a true real-time test.
- **L4 sustainability**: simplified to a 2-marker (K%, SwStr% for SPs) or
  L30-vs-season xwOBA gap (hitters) decomposition; the production 9-marker
  panel is more nuanced.
- **L5 baseline**: uses 2024 full-season xwOBA, which is the closest non-leaky
  baseline for 2025 as-of dates but doesn't match the production "2025 baseline"
  framing. Real validation would use a rolling-prior-window baseline.
- **No IL filter**: players who land on the IL during the forward window
  contribute low forward FP/g that's not a lens failure but a health event.

## What full validation would need

- Historical rank snapshots for 2024 + 2025 (would unblock L1, L2)
- Per-game IL status panel to censor forward window on IL events
- Bootstrap clustered on player (current bootstrap treats each snapshot as
  independent; multiple as_of per player creates within-player correlation)
- N >= 1000 snapshots per pos group, with the FADE arm boosted by sampling
  bottom-rank players, not just top-100

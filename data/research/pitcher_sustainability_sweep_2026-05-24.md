# Pitcher Sustainability Sweep — 2026-05-24

Tool: `scripts/xfp/pitcher_sustainability.py` (rp3 v3 csv, sp_multiyr cache,
statcast parquets).

Methodology: 9-marker Statcast skill decomposition (velo, swstr, CSW, chase,
K%, BB%, HardHit%, Barrel%, xwOBA-contact) vs prior year. Sustainability
E[ROS] is a confidence layer on the headline rp3.per_start; flags trigger
when decomp and rp3 diverge by >1.5 FP/start.

---

## Your roster SPs — bucket assignments

| SP | rp3 | Sus E[ROS] | Bucket | 2026 FP/GS | Δ | Signal |
|---|---:|---:|---|---:|---:|---|
| Jose Soriano | 11.96 | 13.58 | IMPROVING | 17.1 | +1.62 | **BUY-LOW** (rp3 lagging real breakout) |
| Freddy Peralta | 11.77 | 14.21 | STABLE | 13.4 | -1.3 vs prod | INVESTIGATE |
| Carlos Rodon | 11.39 | 12.91 | NOISE | 14.9 | +1.52 (sus>rp3) | **SELL-HIGH** (production won't sustain) |
| Logan Henderson | 11.04 | n/a | NO_BASELINE | 12.9 | — | AGREE (no prior yr) |
| Parker Messick | 11.01 | n/a | NO_BASELINE | 16.3 | — | AGREE (no prior yr) |
| Kyle Bradish | 10.70 | 13.12 | REGRESS | 9.4 | — | INVESTIGATE (rebuilding from TJ) |
| Framber Valdez | 10.67 | 12.31 | REGRESS | 8.6 | — | INVESTIGATE (skills below norms) |
| Will Warren | 10.25 | 11.13 | LEGIT | 12.2 | +1.9 skill | CONFIRM bullish |

Notes:
- Carlos Rodon sustainability bucket NOISE despite 14.9 FP/GS — skill markers
  not supporting the run; sus E[ROS] (12.91) is well below his 2026 surface.
  Flagged SELL-HIGH because surface production exceeds skill-implied baseline.
- Soriano: only roster BUY-LOW; consider holding tight or upgrading priority.

## FA SP pool — top BUY-LOW candidates (decomp >> rp3)

Pool: all FA SPs with 2026 FP/GS ≥ 8 (n=38). Only 2 cleared the >1.5 FP
divergence + bullish-decomp threshold; no need to cap at 15.

| FA SP | rp3 | Sus E[ROS] | Bucket | 2026 FP/GS | Δ |
|---|---:|---:|---|---:|---:|
| Landen Roupp | 9.28 | 11.54 | IMPROVING | 13.9 | +2.26 |
| Randy Vasquez | 8.68 | 10.31 | IMPROVING | 12.0 | +1.63 |

Honorable mentions (just under bar, watch):
- Martin Perez — STABLE bucket, sus 11.71 vs rp3 8.66 (Δ +3.05) but skill
  markers don't all align; INVESTIGATE.
- Michael Soroka — STABLE, sus 11.26 vs rp3 9.14 (Δ +2.12); INVESTIGATE.
- Matthew Boyd — UNLUCKY tag; sus 11.20, rp3 10.57.

## FA SP pool — SELL-HIGH warning candidates (for trade/avoid context)

| FA SP | rp3 | Sus E[ROS] | Bucket | 2026 FP/GS | Δ |
|---|---:|---:|---|---:|---:|
| Spencer Arrighetti | 8.95 | 11.80 | NOISE | 14.6 | +2.85 |
| Michael McGreevy | 6.76 | 9.38 | NOISE | 13.8 | +2.62 |
| Keider Montero | 7.78 | 9.32 | NOISE | 12.0 | +1.54 |
| Eduardo Rodriguez | 8.55 | 9.55 | NOISE | 13.9 | -0.8 (CONFIRM bearish) |
| Bailey Ober | 9.04 | 9.46 | NOISE | 11.8 | CONFIRM bearish |
| Eury Perez | 11.97 | 12.14 | REGRESS | 10.1 | CONFIRM bearish |

These FAs look juicy on raw 2026 FP/GS but skill decomp does not support
the surface line — expect material regression.

## Your roster SELL-HIGH watch

- **Carlos Rodon** — NOISE bucket, sus E[ROS] 12.91 vs current 2026 FP/GS
  14.9. Skill markers do not support the production tier. rp3 (11.39) is
  already conservative; if rp3 is being trusted as the ROS read, no action
  required, but DO NOT trade for him at peak surface value.

No other current roster SP flags SELL-HIGH; Bradish/Valdez REGRESS labels
are downside risk but rp3 has already priced them down.

## Recommendation

1. **Claim Landen Roupp** — strongest FA BUY-LOW (Δ +2.26, IMPROVING). Skill
   decomp says rp3 (9.28) will drift up; better than several of your back-end
   rotation arms.
2. **Hold Carlos Rodon for matchups only; do not promote** — surface FP is
   ahead of skill. If trade interest exists, market him on the 14.9 FP/GS
   line. Continue starting him in plus matchups.
3. **Avoid Spencer Arrighetti and Michael McGreevy** despite gaudy 2026 FP/GS
   — both NOISE with sustained sus<surface gap; rp3 already penalizes them.

## Bucket distribution (this sweep)

- Roster (8): 1 LEGIT, 1 IMPROVING, 1 STABLE, 1 NOISE, 2 REGRESS, 2 NO_BASELINE
- FA pool ≥12 FP (14): 1 LEGIT-adjacent, 2 IMPROVING, 4 STABLE, 1 MIXED,
  4 NOISE, 1 REGRESS-tilt, plus NO_BASELINE rookies

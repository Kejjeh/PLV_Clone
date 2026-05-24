# Hitter sustainability sweep — 2026-05-24

Scope: BrownU roster (12 healthy hitters) + ESPN FA hitter pool (`--min-2026-fp 1.0`, n≈170).
Tool: `python scripts/xfp/hitter_sustainability.py` (rh3 + 9-marker decomp + staleness layer).

---

## Your roster — bucket assignments

| Hitter | rh3 | sus E | Bucket | 2026 | Skill | Signal | Notes |
|---|---:|---:|---|---:|---:|---|---|
| Aaron Judge | 2.45 | 2.90 | REGRES | 2.24 | -0.24 | ? INVESTIGATE | 0/9 markers favorable but L15g cold (-3.17σ); sus says baseline still elite |
| Corbin Carroll | 2.23 | 2.27 | STABLE | 2.11 | +0.16 | · AGREE | EV+BB up; recent L15g HOT (+5.10σ) — rh3 may rise |
| Michael Harris II | 2.19 | 1.76 | STABLE | 1.87 | +0.19 | ? INVESTIGATE | Skill rising (4/9 ✓) but sus E < rh3 — rh3 may be overshooting |
| Vladimir Guerrero Jr. | 2.05 | 2.21 | REGRES | 1.81 | +0.03 | ✗ CONFIRM | Bearish across the board; K% improved but EV/Barrel/Chase worse |
| Pete Alonso | 2.01 | 2.08 | REGRES | 1.60 | -0.08 | ✗ CONFIRM | EV90 -3.1mph, Barrel -5.5pp — power eroding |
| Bo Bichette | 1.98 | 2.00 | REGRES | 1.18 | -0.09 | ✗ CONFIRM | 0/9 favorable; -1.00 luck drag but skills also down |
| Luis Arraez | 1.91 | 1.98 | STABLE | 1.91 | -0.02 | · AGREE | Vintage Arraez; recent L15g HOT (+4.17σ) |
| Elly De La Cruz | 1.89 | 1.94 | STABLE | 1.93 | -0.03 | · AGREE | **7/9 markers ✓** — under-the-hood breakout, rh3 lags |
| Jordan Walker | 1.83 | 1.59 | IMPROV | 2.22 | +0.37 | ✓ CONFIRM | 6/9 favorable, +1.26 FP/g jump; rh3 still catching up (+4.92σ stale) |
| Trea Turner | 1.79 | 1.98 | REGRES | 1.25 | -0.15 | ✗ CONFIRM | Real skill slippage (Chase +3.4pp, SweetSpot -3.2pp) |
| Salvador Perez | 1.64 | 1.66 | REGRES | 1.17 | -0.13 | ✗ CONFIRM | 0/9 favorable; age-curve signal |
| Max Muncy | 1.33 | 1.08 | STABLE | 1.13 | -0.07 | · AGREE | HardHit jumped but K% +4.3pp / Chase +6.3pp offsets |

**No roster hitters flagged SELL-HIGH.** Closest watch: Michael Harris II (sus E 1.76 < rh3 2.19, Δ=-0.43) — recent skill improvement is real but rh3 may be ahead of base.

---

## FA pool — top BUY-LOW candidates (decomp >> rh3, sus E exceeds rh3 by ≥0.4 FP/g)

Sorted by gap. These are hitters whose 9-marker Statcast says they're better than rh3 currently prices, in a healthy 2026 sample. Not formal BUY-LOW signal (which requires bullish bucket), but `INVESTIGATE-up` is the FA-pool equivalent.

| Hitter | rh3 | sus E | Δ | 2026 FP/g | Bucket | Why |
|---|---:|---:|---:|---:|---|---|
| Dustin Harris | 1.39 | 3.62 | +2.23 | 0.98 | REGRES | Bucket REGRES but sus E inflated by small sample / luck spike — treat with caution |
| Gary Sanchez | 1.56 | 1.99 | +0.43 | 2.01 | STABLE | K% -6.4pp, BB% +14.6pp, Chase -4.3pp — discipline overhaul, rh3 hasn't caught up |
| Carter Jensen | 1.65 | 2.39 | +0.74 | 1.19 | REGRES | Underlying skills strong; rh3 cautious on prior |
| Miguel Amaya | 1.51 | 2.21 | +0.70 | 1.61 | REGRES | Sus says catcher with usable bat |
| Richie Palacios | 1.47 | 2.10 | +0.63 | 1.39 | REGRES | Skills > production |
| Alex Call | 1.71 | 2.32 | +0.61 | 1.80 | REGRES | Decent multi-pos OF |
| Giancarlo Stanton | 1.49 | 2.07 | +0.58 | 1.41 | REGRES | Power markers say he's underpriced — IL-risk caveat |
| Nasim Nunez | 1.35 | 1.83 | +0.48 | 1.21 | REGRES | Light bat ceiling |

Notable bullish-bucket FAs (LEGIT/IMPROV) with no rh3 anchor — speculative add territory:
- **Curtis Mead** (LEGIT, rh3 1.69, 2.06 FP/g, +0.66 skill, CONFIRM)
- **Tyler Black** (IMPROV, sus 1.58, 2.42 FP/g 2026, +1.69 skill — small sample but breaking out)
- **Carlos Cortes** (rh3 2.16, sus 2.19, AGREE)
- **Dominic Smith** (rh3 1.79, sus 2.05, AGREE)

---

## FA pool — SELL-HIGH warning candidates (decomp << rh3)

Only two hitters tripped the formal SELL-HIGH signal in the FA pool:

| Hitter | rh3 | sus E | Δ | Note |
|---|---:|---:|---:|---|
| Drew Romo | 1.57 | -0.58 | -2.15 | Skills collapsed; rh3 still bullish on prior |
| Luis Campusano | 1.79 | 1.22 | -0.57 | -0.65 FP/g 2026; if owned in another league, sell |

(Both are already FAs in BrownU, so the trade-context value is limited — flagged here per the requested output.)

---

## Your roster SELL-HIGH watch

**None.** No hitter on your roster tripped the formal SELL-HIGH signal (rh3 high, sus E bearish by ≥0.4).

Closest watch — **Michael Harris II** (rh3 2.19, sus E 1.76, Δ=-0.43, INVESTIGATE-down). Skill markers are actually rising (4/9 favorable, +0.19 skill FP), so this is more "rh3 may overshoot" than "sell now." Hold.

The REGRES bucket on Judge/Vlad/Alonso/Bichette/Turner/Perez reflects the 2026 skill decomposition vs prior — but in each case sus E ≈ rh3, so rh3 already prices the regression. No sell-high mispricing.

---

## Recommendation

1. **Stash watch: Curtis Mead** (LEGIT bucket, rh3 1.69, +0.66 skill FP, CONFIRM). The cleanest "rh3 + sus agree bullish" non-rostered FA. Bench-spec add if a slot opens.
2. **Hold Michael Harris II** despite sus E < rh3. Underlying skill markers (EV +2.66mph, HardHit +12.2pp, Barrel +7.5pp, xwOBAcon +0.087) are improving — sus E is just slow to credit it. Do NOT sell on this signal alone.
3. **No action on REGRES roster names.** Judge / Vlad / Alonso / Bichette / Turner / Perez all bucket REGRES, but sus E ≈ rh3 in every case — the model already prices the regression. The L15g cold streak on Judge (-3.17σ) is noise on top of an already-marked-down rh3.

---

## Methodology notes

- Source: `data/research/xfp_cache/statcast_2026.parquet` + 2025 baseline (per skill SKILL.md)
- 9 markers: AvgEV, EV90, HardHit%, Barrel%, xwOBAcon, K%, BB%, Chase%, SweetSpot%
- Buckets: LEGIT / IMPROV / STABLE / MIXED / NOISE / REGRES / UNLUCKY
- Signals: CONFIRM (agree bullish/bearish), AGREE (gap within noise), INVESTIGATE (gap ≥0.4 FP/g), SELL-HIGH / BUY-LOW (formal divergence + bucket trigger)
- Player IDs resolved via `plv_clone.utils.name_match.resolve_batter_id` (Muncy LAD/ATH collision handled)

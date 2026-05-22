---
name: hitter-sustainability
description: Augments rh3 (the validated ROS hitter projection) with a 9-marker Statcast skill decomposition (avg_ev, ev90, hard_hit_pct, barrel_pct, xwoba_on_contact, k_pct, bb_pct, chase_pct, sweet_spot_pct). Headline ROS number is rh3.per_game. Outputs LEGIT/IMPROVING/STABLE/MIXED/NOISE/BAD_LUCK/REGRESS buckets as the CONFIDENCE LAYER on rh3, plus BUY-LOW / SELL-HIGH divergence signals when sustainability decomp disagrees with rh3 by >0.4 FP/game. Sweep mode (my-roster or fa-pool) is its main value over `/breakout-sustainability` which is a deep-dive single-player skill. Use to (a) audit your full hitter roster for who's truly sustainable vs running hot, (b) surface FA pool hitters whose Statcast underlyings are ahead of rh3, (c) compare 2-6 hitters head-to-head with structured marker decomp.
---

# hitter-sustainability

Direct mirror of `/pitcher-sustainability`: rh3 is the headline ROS
projection; the sustainability bucket and divergence signal layer on
top of it. The most valuable output is the **ACTIONABLE SIGNALS**
section that surfaces BUY-LOW (skills bullish, rh3 hasn't caught up)
and SELL-HIGH (skills bearish, rh3 still high) candidates.

For deep-dive on a single hitter or 2-3 narrative comparison, use
`/breakout-sustainability` instead — it has richer per-player analysis
with bat tracking + slump-or-decline framework.

---

## When to invoke

- Auditing your full hitter roster for hidden regression risk or
  buy-low candidates (Sunday roster review)
- Sizing up the FA hitter pool for actionable adds (BUY-LOW signals)
- Comparing 2-6 specific hitters head-to-head
- Validating a `/breakout-sustainability` verdict against rh3

## When NOT to invoke

- Deep-dive single-player narrative ("is X's breakout real?") →
  `/breakout-sustainability` is better
- Daily lineup decisions → use `/hitter-compare` for matchup-aware reads
- Pitcher sustainability → use `/pitcher-sustainability`

---

## Invocation

```bash
# Specific list (most common for trade evaluation)
python scripts/xfp/hitter_sustainability.py --players "Aaron Judge,Bo Bichette,Trea Turner"

# Whole roster audit (Sunday review)
python scripts/xfp/hitter_sustainability.py --scope my-roster

# FA pool sweep for buy-low candidates
python scripts/xfp/hitter_sustainability.py --scope fa-pool --min-2026-fp 2.0

# Summary table only (no per-hitter detail)
python scripts/xfp/hitter_sustainability.py --scope my-roster --brief
```

---

## Understanding the output

Per-hitter block leads with:
- **rh3 per_game** (validated model, headline)
- **Bucket** (confidence layer)
- Per-year FP/game (current + baseline + delta)
- 9-marker table with ✓/✗ flags
- FP decomposition (skill vs luck attribution)
- Bull/base/bear ROS + E[FP/game]
- **Signal** (BUY_LOW / SELL_HIGH / CONFIRM / AGREE / INVESTIGATE)

Summary table at the end sorts by rh3 desc. The **ACTIONABLE SIGNALS**
block at the bottom is the call-to-action: surfaces only BUY-LOW and
SELL-HIGH hitters across the whole sweep.

---

## Hitter 9-marker checklist

| Marker | Favored direction | Material if Δ ≥ |
|---|---|---|
| Avg EV | + | 1.0 mph |
| EV90 (90th pct exit velocity) | + | 1.5 mph |
| HardHit% (95+ mph) | + | 3.0 pp |
| Barrel% | + | 1.5 pp |
| xwOBA-on-contact | + | 0.020 |
| K% | − | 2.0 pp |
| BB% | + | 1.5 pp |
| Chase% (o_swing) | − | 2.0 pp |
| SweetSpot% (8-32° launch angle) | + | 2.0 pp |

xwOBA-on-contact is a marker but NOT used in the FP decomposition
(redundant with Barrel%; would double-count).

FP decomposition uses **K%, BB%, Barrel%** with PA-per-game = 3.5
(matches rh3 pipeline's PA_PER_GAME_LEAGUE constant).

---

## Bucket → ROS probabilities

| Bucket | P(bull) | P(base) | P(bear) |
|---|---:|---:|---:|
| LEGIT | 40% | 45% | 15% |
| IMPROVING | 25% | 50% | 25% |
| MIXED | 20% | 40% | 40% |
| NOISE | 10% | 30% | 60% |
| STABLE | 20% | 60% | 20% |
| BAD_LUCK | 40% | 40% | 20% |
| REGRESS | 10% | 30% | 60% |

---

## Anti-patterns this skill exists to prevent

- **Trusting raw FP/game without skill check.** A hitter whose FP/g
  jumped 0.6 might be all BABIP (NOISE) or all skill (LEGIT) — same
  surface, opposite verdict.
- **Reading the bucket without the signal.** Bucket says how the
  STATCAST decomp interprets the year; signal says whether rh3 has
  caught up to it. Both matter.
- **Acting on small-sample 2026 calls.** If `n=2026 < 20 games`, the
  tool falls back to comparing the two most recent prior years. The
  output flags this with `⚠ 2026 sample too small`.
- **Comparing to `/breakout-sustainability` for sweep work.** That
  skill is single-player narrative-rich. Use THIS one for the wide
  scan, then drill into specific names with breakout-sustainability.

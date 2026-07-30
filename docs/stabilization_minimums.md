# Empirical stabilization minimums

Canonical sample-size gates for every rate metric we read. **Measured on our
own data**, not borrowed from public rules of thumb. Implemented in
[`src/plv_clone/stabilization.py`](../src/plv_clone/stabilization.py), locked by
`tests/test_stabilization.py`, summarized in CLAUDE.md gotcha #12.

## What "stabilization" means here

For each metric we ask the *decision-relevant* question: **if I measure this
over the first N units, how well does it predict the same metric over the rest
of the season?** Formally, forward reliability

```
r( metric(first N units) , metric(remainder of season) )
```

bucketed by N, with the crossing points at r=0.50 (usable) and r=0.70 (high
confidence) interpolated between buckets.

This deliberately conflates two sources of uncertainty — measurement noise and
true in-season drift — because a forward-looking decision faces both. It is not
split-half reliability, which measures only the first.

## Provenance

| Study | Script | Sample | Memo |
|---|---|---|---|
| Hitters | `scripts/xfp/validate_cutoff_stabilization.py` | 91,628 batter-snapshots, 2018–2026 ex 2020 | `data/research/validation_runs/inseason_delta_grid_2026-07-29.md` (Part A) |
| Pitchers | `scripts/xfp/validate_cutoff_stabilization_pitchers.py` | 26,958 SP + 42,978 RP snapshots, same window | `data/research/validation_runs/pitcher_cutoff_stabilization_2026-07-29.md` |

Both pre-registered before any number was computed. Buckets require ≥200
snapshots; rest-of-season windows require ≥200 pitches / 40 TBF / 30 BIP.
Minimums are the r≥0.50 crossing rounded **up** to the nearest 25.

## Hitters

| Metric | Minimum | Denominator | Reaches r=0.70? |
|---|---|---|---|
| **Bat speed** | **50** | swings | ✅ **by 25–30** (never below .70 anywhere) |
| Chase% | **150** | out-of-zone pitches | ✅ ~150 |
| Z-Swing% | **150** | in-zone pitches | ✅ ~168 |
| Z-Contact% | **150** | in-zone pitches | ✅ ~168 |
| Whiff% | **150** | swings | ✅ ~150 |
| SwStr% | **150** | pitches | ✅ ~218 |
| K% | **50** | PA | ✅ ~135 PA |
| Hard-hit% | **50** | BIP | ✅ ~121 BIP |
| Barrel% | **50** | BIP | ✅ ~162 BIP |
| BB% | **175** | PA | ❌ never in-window |
| xwOBA/PA | **225** | PA | ❌ never |
| ISO | **275** | AB | ❌ never |
| HR-rate | **275** | PA | ❌ never |

## Starting pitchers

| Metric | Minimum | Denominator | Reaches r=0.70? |
|---|---|---|---|
| **Velocity** | **150** | pitches | ✅ immediately (r≈0.90 first bucket) |
| Whiff% | **150** | swings | ✅ ~651 |
| SwStr% | **175** | pitches | ✅ ~744 |
| Z-Swing% | **275** | in-zone pitches | ❌ |
| GB% | **50** | BIP | ❌ |
| K% | **100** | TBF (~4 starts) | ❌ |
| CSW% | **425** | pitches | ❌ |
| wOBA-against | **525** | TBF (≈ full season) | ❌ |
| Chase% induced | **never stabilizes** | — | — |
| BB% | **never stabilizes** | — | — |
| Hard-hit / Barrel / HR-rate against | **never stabilizes** | — | — |

## Relief pitchers

| Metric | Minimum | Denominator | Reaches r=0.70? |
|---|---|---|---|
| **Velocity** | **150** | pitches | ✅ immediately (r≈0.93) |
| Whiff% | **150** | swings | ❌ |
| Z-Swing% | **150** | in-zone pitches | ❌ |
| SwStr% | **200** | pitches | ✅ ~903 |
| K% | **125** | TBF | ❌ |
| CSW% | **425** | pitches | ❌ |
| Chase% / BB% / wOBA-against | **never stabilizes** | — | — |

## The four consequences that change how we read things

1. **Velocity is the king pitcher metric.** Trustworthy after ~1–2 starts. This
   is why the FB-velo spine of `/fa-monitor`, `/trending` and the
   `stuff_command` lens is sound — now empirically, not by convention.
2. **Short-window BB% and power reads are noise by construction.** Hitter BB%
   needs 175 PA and never reaches high confidence; HR-rate needs 275 PA. A
   three-week "he's walking more" or "his power is back" claim is unsupportable.
3. **Pitcher command and contact-quality-against never stabilize in-window.**
   No sample size rescues a mid-season "his command improved" or "he's been
   HR-prone lately" read. The `/sp-board` HR/9 lens survives *only* because it
   compares 2026 to CAREER — never to a window. This is the measurement math
   behind CLAUDE.md gotcha #11's "watch an arm's STUFF, not its walks".
4. **Our old hand-picks were wrong in both directions** — 300 pitches for
   swing-decision metrics was 2× conservative (150 suffices); 60 PA for BB% was
   ~3× too permissive.

## Usage

```python
from plv_clone.stabilization import gate, insufficient, describe

# One-line column gate — blank cell instead of a number that looks real
row["bb_pct"] = gate(bb_rate, pa_count, "bb_pct", "H")

# Board footer caveat
missing = insufficient(["k_pct", "bb_pct", "iso"], denoms, "H")
# -> ["bb_pct", "iso"]

describe("velo", "SP")   # "velo (SP): >= 150 pitches"
```

`minimum()` **raises** on a metric in `NEVER_STABILIZES` — asking for a
threshold there is a design bug, not a threshold problem.

## Two things this module is NOT

- **Not the model-universe filters.** `EVAL_PA_MIN` / `ROS_PA_MIN` (rh3),
  `EVAL_GS_MIN` / `ROS_GS_MIN` (rp3), `EVAL_G_MIN` (rprs2) decide which rows a
  model trains and projects on. They are owned by the model modules and merely
  **re-exported** here so downstream scripts stop copy-pasting the literals.
- **Not the in-season trajectory of a metric.** These gates answer "is this
  number knowable yet." Whether a *change* in it predicts anything is a separate
  question, and the answer has consistently been no — the 60-cell
  `inseason_delta_grid` rejection, and then bat speed itself (below).

## Bat speed (added 2026-07-29) — measured, and the one to read

| swings-to-date | n player-seasons | mean_bat_speed | fast_swing_rate | p90 |
|---|---|---|---|---|
| 27 | 229 | **+0.736** | +0.766 | +0.816 |
| 32 | 264 | +0.849 | +0.900 | +0.908 |
| 42 | 319 | +0.864 | +0.912 | +0.912 |
| 52 | 242 | +0.879 | +0.902 | +0.909 |
| 87 | — | +0.905 | +0.918 | — |
| 612 | — | +0.950 | +0.950 | — |

Source: `scripts/xfp/validate_bat_speed_stabilization.py` over
`data/research/bat_speed_daily.parquet` — 126,434 batter-days / 869 batters /
860,531 swings / 1,929 player-seasons. Identical to 3 decimals with
`--drop-provisional`, so gf-bridge same-day rows are harmless.

**No bucket anywhere in the curve falls below +0.70.** Both crossings clear at
or below 25–30 swings; the crossing cannot be resolved lower only because fewer
than 200 player-seasons exist below 25 swings under a weekly snapshot stride.
The registry value **50** is `ceil(27/25)*25` — the same mechanical rule every
other entry uses, so it is deliberately conservative. The old literature value
of 30 was **confirmed** by this measurement before being retired.

### The critical companion result: read the LEVEL, not the trajectory

`validate_bat_speed_delta.py` tested whether an in-season bat-speed **delta**
adds forward FP/PA signal beyond the season-to-date level. **REJECTED** — 0 of 6
pre-registered cells survived BH-FDR, and the near-miss (lag63, partial r
+0.1126, n=466) failed the full 22-feature Rule-9 integration at **+0.0035**
against the +0.005 bar. This was the `inseason_delta_grid` family's sole named
re-open condition; it now has none.

So a metric can be beautifully measured and still carry no forward information
beyond the level that already contains it. Practically: rank on the bat-speed
**level** and the **year-over-year step** (both r≈0.95); display the in-season
trajectory as Rule-13 context; never let it move a rank, add, or drop.

Canonical trap: a board sorted by in-season bat-speed delta surfaces **Bichette**
(+1.87 mph — a slow April washing out, on a 25th-percentile level) as the riser
and **Cam Smith** (flat +0.01, on a 98th-percentile level, +3.10 mph YoY) as
boring. Exactly backwards.

### What this does NOT license

`lib/trend_signal.py`'s `HIT_MIN_SW_CUR / HIT_MIN_SW_BASE = 80 / 200` gate a
**year-over-year delta**, whose noise is ~√2× a level's. The curve above measures
the **level**. Directionally there is probably headroom, but the multiplier is
not derivable from this curve — **do not relax 80/200 on this evidence**, and do
not re-run `/trending` cells that were blanked at 30–79 swings until a
delta-appropriate gate is derived.

## Maintenance rule

A number in this module changes only when a new pre-registered study measures
it. Never loosen a gate to make a read possible — that inverts the entire
point. (Same rule as `/model-health`: don't fix a WARN by moving the line.)

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
- **Not bat speed.** Bat speed's 30-swing threshold is a **literature value**,
  carried in `LITERATURE_ONLY` and labelled as such by `describe()`. No
  window-capable bat-speed store existed when these studies ran. Re-deriving it
  is workstream W3b.

## Maintenance rule

A number in this module changes only when a new pre-registered study measures
it. Never loosen a gate to make a read possible — that inverts the entire
point. (Same rule as `/model-health`: don't fix a WARN by moving the line.)

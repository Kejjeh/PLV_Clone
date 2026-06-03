# 2-Start Week Amplification — boom_stack Persistence & Week-Boom Rate

Generated 2026-06-03. n = 4,905 two-start weeks (4,650 with tier assignment).
Source panel: `data/research/_boom_stack_per_start_panel_cache.parquet`
(2018-2025, PA >= 5, n_prior_starts >= 3 for component flags).

## Question

When an SP has `boom_stack >= 2` at start 1 of a 2-start week, what's the
probability the stack persists to start 2, and what is the resulting week-total
boom rate (>= 30 FP across both starts)? Translation: should we lock a 2-start
streamer ALL week or just for start 1?

## Methodology

- **2-start-week definition:** same pitcher, both starts in same Monday-Sunday
  calendar window (ESPN scoring week). 4,905 such pairs across 2018-2025.
- **Strict framing:** `boom_stack` at start 2 is computed from data through end
  of start 1 only (panel was built per-start in
  `build_per_start_boom_stack`, no leakage).
- **Tier assignment:** season-end FP-per-start rank within year (min 8 starts).
  ace = #1-10, sp2_sp3 = #11-30, backend = #31-50, streamer = #51+.
- **Week-boom:** week_total_fp = fp_s1 + fp_s2 >= 30.
- **Single-start boom:** fp >= 20 (per repo convention).

## 1. Transition matrix — P(boom_stack_s2 | boom_stack_s1)

Pooled across all tiers (n=4,905):

| stack_s1 \\ stack_s2 | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| 0 (n=2,590) | 0.564 | 0.388 | 0.042 | 0.006 |
| 1 (n=1,781) | 0.476 | 0.392 | 0.116 | 0.016 |
| 2 (n=452)   | 0.277 | 0.398 | 0.268 | 0.058 |
| 3 (n=82)    | 0.098 | 0.354 | 0.390 | 0.159 |

**Headline persistence numbers:**
- **P(stack_s2 >= 2 | stack_s1 >= 2) = 36.0%** (n_s1>=2 = 534)
- **P(stack_s2 >= 2 | stack_s1 < 2) = 8.2%** (n_s1<2 = 4,371)
- **Base rate P(stack_s2 >= 2) = 11.2%**
- **Lift: +27.8 pp** — a stacked start 1 is ~4.4x more likely to be followed by
  a stacked start 2 than a non-stacked start 1.

### By tier:

| tier | n_s1>=2 | P(s2>=2 \| s1>=2) | P(s2>=2 \| s1<2) | lift |
|---|---|---|---|---|
| ace | 42 | 45.2% | 8.9% | +36.3 pp |
| sp2_sp3 | 78 | 38.5% | 10.8% | +27.7 pp |
| backend | 70 | 40.0% | 9.3% | +30.7 pp |
| streamer | 342 | 33.6% | 8.0% | +25.6 pp |

Persistence is universally strong across tiers — the signal carries.

## 2. Per-component sticky rates

For each flag, P(flag_s2=1 | flag_s1=1) vs base rate (pooled):

| component | n_s1=1 | P(s2=1 \| s1=1) | base P(s2=1) | lift |
|---|---|---|---|---|
| **flag_skill_spike** | 411 | 44.3% | 8.5% | **+35.8 pp** |
| **flag_recform_hot** | 929 | 58.6% | 20.1% | **+38.5 pp** |
| **flag_opp_soft** | 1,591 | 34.4% | 34.6% | **-0.2 pp** |

**Interpretation:**
- `flag_skill_spike` persists 5.2x base rate. Recent K%-spike + BB%-drop reflect
  a real-arm-state signal that doesn't dissolve in 4-7 days.
- `flag_recform_hot` persists 2.9x base rate. Recency form is sticky — the L3
  window largely overlaps between consecutive starts.
- **`flag_opp_soft` is essentially independent** (0.998x base rate). Different
  opponent on start 2 is uncorrelated with start 1 — exactly as the schedule
  would predict.

This means the **persistent portion of boom_stack is the SKILL-driven part**
(spike + recform), while the matchup part needs to be re-validated for start 2.

### By tier (consistent pattern):

| tier | skill_spike lift | recform_hot lift | opp_soft lift |
|---|---|---|---|
| ace      | +41.4 pp | +37.3 pp | -1.6 pp |
| sp2_sp3  | +35.3 pp | +34.9 pp | -2.0 pp |
| backend  | +38.3 pp | +35.1 pp | +4.6 pp |
| streamer | +33.7 pp | +38.6 pp | -0.5 pp |

Sticky rates of the two skill flags are nearly tier-invariant (~33-41 pp).

## 3. Week-total boom rate (week_total_fp >= 30)

Pooled across tiers:

| stack_s1 | n | week_boom% | mean week FP |
|---|---|---|---|
| 0 | 2,590 | 27.5% | 20.95 |
| 1 | 1,781 | 29.5% | 22.38 |
| 2 | 452   | 31.6% | 22.63 |
| 3 | 82    | 35.4% | 24.75 |

Pooled lift stack_s1=2 vs 0: **+4.1 pp week-boom edge**. Stack_s1=3 vs 0:
**+7.9 pp** (n=82, wide CI).

### Per-tier week-boom rate by stack_s1:

| tier | stack_s1=0 | stack_s1=1 | stack_s1=2 | stack_s1=3 | stack_s1>=2 edge |
|---|---|---|---|---|---|
| ace      | 67.1% (n=149) | 69.4% (n=108) | 72.2% (n=36) | 83.3% (n=6) | **+6.7 pp** |
| sp2_sp3  | 44.9% (n=292) | 52.6% (n=209) | 55.6% (n=63) | 53.3% (n=15) | **+10.3 pp** |
| backend  | 41.5% (n=306) | 42.9% (n=210) | 41.9% (n=62) | 50.0% (n=8) | +1.4 pp |
| streamer | 20.0% (n=1,674) | 20.4% (n=1,170) | 19.3% (n=290) | 23.1% (n=52) | -0.1 pp |

**Tier-amplification holds for week-boom too** — SP2/3 and Ace get a clean
week-boom edge from stack_s1>=2; Backend and Streamer do not (consistent with
the per-start tier table — the streamer per-start +8 pp edge does NOT compound
to a week-boom +8 pp edge because week-boom requires BOTH starts to contribute
or one mega-boom).

## 4. Compound vs independent

If the two starts were independent given stack_s1, P(at least one boom_20)
would be 1-(1-p1)*(1-p2). Comparison:

| stack_s1 | n | P(boom_s1) | P(boom_s2) | P(>=1 boom): indep / actual | P(both boom): indep / actual |
|---|---|---|---|---|---|
| 0 | 2,421 | 15.2% | 17.5% | 30.1% / 29.1% | 2.7% / 3.6% |
| 1 | 1,697 | 19.7% | 16.4% | 32.8% / 31.5% | 3.2% / 4.5% |
| 2 | 451   | 16.9% | 21.5% | 34.7% / 33.3% | 3.6% / 5.1% |
| 3 | 81    | 24.7% | 17.3% | 37.7% / 35.8% | 4.3% / 6.2% |

The two starts are **slightly positively correlated** (P(both boom) ~1.5x indep).
Realized week-boom>=30 rate is close to the independent at-least-one-boom rate
because a single 30+ start guarantees week-boom regardless of start 2.

## 5. Year-by-year stability (pooled stack_s1 >= 2)

| year | n_s1>=2 | week_boom% | stack_s1=0 base | edge |
|---|---|---|---|---|
| 2018 | 69 | 36.2% | 33.6% | +2.6 pp |
| 2019 | 90 | 34.4% | 26.8% | +7.7 pp |
| 2021 | 74 | 29.7% | 28.9% | +0.8 pp |
| 2022 | 85 | 27.1% | 30.1% | -3.0 pp |
| 2023 | 69 | 29.0% | 26.0% | +3.0 pp |
| 2024 | 68 | 41.2% | 26.5% | +14.7 pp |
| 2025 | 77 | 29.9% | 28.1% | +1.7 pp |

Pooled-tier signal is noisy year to year (one negative year, +1 to +14 spread).
The tier-conditional signal is more stable but n shrinks fast.

## 6. Tier amplification at week-total level — does it hold?

Comparing per-start vs week-boom amplification (stack_s1=2 vs stack_s1=0):

| tier | per-start boom edge (stack=2 vs 0) | week-boom edge (stack_s1=2 vs 0) |
|---|---|---|
| ace      | +6.8 pp | **+5.1 pp** (n=36) |
| sp2_sp3  | +1.0 pp | **+10.7 pp** (n=63) |
| backend  | +0.4 pp | +0.4 pp (n=62) |
| streamer | +3.8 pp | -0.7 pp (n=290) |

Notable: **SP2/3 stack_s1=2 amplifies MORE at the week level than at the start
level** (+10.7 pp vs +1.0 pp). This is because skill_spike + recform_hot persist
into start 2, lifting the SP2/3 chance of a second usable start. Streamer
tier's per-start signal does NOT carry to week-boom because the single-start
boom rate is too low for two-event compounding to matter much.

## 7. Verdict

### VERDICT: SHIP_AS_WEEK_BOOM_RATE — but tier-gated

The persistence signal is real and large:
- P(stack_s2 >= 2 | stack_s1 >= 2) = 36% vs 8.2% base (4.4x lift)
- Driven by skill_spike (+35.8 pp) and recform_hot (+38.5 pp); opp_soft is
  independent across starts (+0 pp lift).

The week-boom signal is tier-conditional:
- **Ace / SP2-3 stack_s1 >= 2 — LOCK FOR THE WEEK.** Week-boom rate 72%
  (ace) / 55% (sp2_sp3), edges +6.7 / +10.3 pp vs stack_s1=0. n moderate
  but signal direction stable.
- **Backend stack_s1 >= 2 — NEUTRAL.** Week-boom rate 42% vs 41.5% base
  (+1.4 pp). Same weak amplification observed at single-start level.
- **Streamer stack_s1 >= 2 — NO WEEK-LEVEL EDGE.** Week-boom rate 19.3%
  vs 20.0% base. The per-start +8 pp boom edge does not survive the
  compounding required for week-total >= 30.

### How to surface in `sp-week-plan`

For each 2-start-week SP, expose:

```
Bradish (backend) — Start 1 stack=2, Start 2 projected stack=2 with 40% prob
  Week-boom (>= 30 FP) rate at this profile: 42% (Backend × stack_s1=2)
  Persistence driver: skill_spike (sticky 48%) + recform_hot (sticky 56%)
  Note: opp_soft does NOT carry to start 2 (recompute for start 2 opponent)
```

For SP2/3 + Ace 2-start weeks with stack_s1 >= 2, label as **LOCK WEEK**:

```
Valdez (sp2_sp3) — Start 1 stack=2, week-boom rate 55.6%
  Lock both starts. Skill signal persists into start 2.
```

### Composite week-boom probability formula (suggested)

For a 2-start week with stack_s1 = s:

```
week_boom_prob = WEEK_BOOM_RATE_BY_TIER_STACK_S1[tier][s]
```

Tables to add to `lib/boom_stack.py`:

```python
WEEK_BOOM_RATE_BY_TIER_STACK_S1 = {
    'ace':      {0: 0.671, 1: 0.694, 2: 0.722, 3: 0.833},
    'sp2_sp3':  {0: 0.449, 1: 0.526, 2: 0.556, 3: 0.533},
    'backend':  {0: 0.415, 1: 0.429, 2: 0.419, 3: 0.500},
    'streamer': {0: 0.200, 1: 0.204, 2: 0.193, 3: 0.231},
}
# Component sticky rates (pooled — tier-invariant within +/-5 pp).
COMPONENT_STICKY_RATE = {
    'flag_skill_spike': 0.443,   # 5.2x base
    'flag_recform_hot': 0.586,   # 2.9x base
    'flag_opp_soft':    0.344,   # ~base (independent across starts)
}
```

## 8. Caveats

- **n shrinks fast at tier × stack_s1 cells.** Ace stack_s1=3 has n=6 (not
  actionable). Backend / Streamer stack_s1=3 have n=8 / 52. Use stack_s1>=2
  as the operational threshold.
- **opp_soft re-evaluation needed for start 2.** Because opp_soft doesn't
  persist, the *actual* start 2 stack will reflect a fresh opponent. The
  persistence-of-skill-flags piece means stack_s1 >= 2 with skill flags
  predicts an "automatic" stack >= 1 at start 2 (~58% from recform_hot
  alone), plus whatever the start 2 matchup delivers.
- **2020 excluded** (panel construction).
- **HIGH-K compound not tested here.** HIGH-K cohort baseline requires
  (year, month) z-score data — not computed in the historical per-start
  panel. The 2026 in-season HIGH-K tag would compound multiplicatively with
  stack_s1 (validation: `boom_stack_v2_validation.md` shows +6.84 pp
  standalone, +6.5 to +16.8 pp at stacks 0-3). Future work: compute HIGH-K
  per-start historical baseline to confirm week-level amplification.
- **Tier assignment is season-end (forward-leaky).** Same caveat as
  `boom_stack_by_tier.md` — directional finding holds; magnitudes within tier
  may shift ~1-2 pp under rolling-rank assignment.

## Files

- Panel: `data/research/validation_runs/2start_week_panel.csv` (4,905 rows)
- Source: `data/research/_boom_stack_per_start_panel_cache.parquet`
- Engine reference: `scripts/xfp/lib/boom_stack.py`

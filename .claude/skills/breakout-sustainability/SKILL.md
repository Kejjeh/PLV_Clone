---
name: breakout-sustainability
description: Distinguish a sustainable skill-driven breakout from a hot-streak outcome fluke. For a hitter whose recent FP/xwOBA looks elite, decomposes which inputs actually changed — bat tracking (bat speed), discipline (whiff/chase/zone-contact), quality of contact (EV90/hard-hit), xwOBA stability — against a 2025 baseline. Outputs SUSTAINABLE / NARROW-BREAKOUT / HOT STREAK verdict with age-curve context. Use whenever the user asks "is this breakout real", "should I trust X's hot start", or compares a young player's recent performance to a veteran.
---

# breakout-sustainability

You are answering whether a hitter's hot stretch is a **real
skill-level change** (sustainable, the player has evolved) or an
**outcome fluke** (regresses to prior baseline).

The skill exists because Steer/Montgomery/Muncy all had elite L21d
xwOBA, but the underlying drivers were very different:
- Muncy: peak-Muncy form (all-skill confirmed by 8-year history)
- Steer: real process change (chase down, contact up, hard-hit up)
- Montgomery: HR outcome up (bat speed real) BUT whiff% actually
  WORSENED — power-only "breakout" with capped AVG ceiling

Without decomposing the inputs, you can't separate these three
sustainability cases.

---

## Inputs

1. **Player name(s)** — 1-4 players (often comparing 2-3 hot
   candidates against a veteran benchmark)
2. **Optional benchmark** — e.g., a known veteran ("how does Steer's
   xwOBA jump compare to peak-Muncy?") or a historical archetype
   comp (e.g., Eugenio Suárez 2025 as the "power-or-bust" archetype)

---

## Step 1 — Pull skill-level metrics across windows

For each player, pull from Statcast parquets:

```python
# Three windows: 2025 baseline, 2026 season-to-date, 2026 L21d
PARQ_25 = 'data/research/xfp_cache/statcast_2025.parquet'
PARQ_26 = 'data/research/xfp_cache/statcast_2026.parquet'
```

Compute for each window:

| Metric | Source | Stabilization threshold |
|---|---|---|
| **Bat speed** (avg) | `bat_speed` on swing pitches | **30 swings** |
| Swing length | `swing_length` | 30 swings |
| **xwOBA** | `estimated_woba_using_speedangle` on events | 150 PA |
| **EV90** (90th pct exit velo) | `launch_speed` on events | 70 batted balls |
| Hard-hit% (95+ EV) | `launch_speed >= 95` / events | 70 batted balls |
| **Whiff%** | `swinging_strike*+foul_tip` / swings | 100 swings |
| **Chase%** (OOZ swing) | OOZ swings / OOZ pitches | 60 OOZ pitches |
| Z-Contact% | in-zone contacts / in-zone swings | 60 IZ swings |
| **K%** | strikeouts / PA | 60 PA |
| BB% | walks / PA | 60 PA |
| HR/PA | HRs / PA | 70 batted balls |

Surface as a 4-column table per metric: 2025 | 2026 season | 2026 L21d | **Δ L21d vs 2025**.

---

## Step 2 — Sample-size stabilization + 95% CI on L21d xwOBA

Sanity-check that the L21d sample is large enough to be meaningful
AND compute the 95% confidence interval on the L21d xwOBA.

```python
import numpy as np

# Stabilization check
print(f"Swings L21d: {n_swings}  → bat-speed/whiff stabilized: "
      f"{'YES' if n_swings>=30 else 'borderline' if n_swings>=20 else 'NO'}")
print(f"PA L21d:     {n_pa}      → K%/BB% stabilized: "
      f"{'YES' if n_pa>=60 else 'borderline' if n_pa>=40 else 'NO'}")
print(f"PA season:   {n_pa_szn} → xwOBA stabilized: "
      f"{'YES (>150)' if n_pa_szn>=150 else 'borderline' if n_pa_szn>=100 else 'NO'}")

# 95% CI on L21d xwOBA (mandatory)
se = 0.39 / np.sqrt(n_pa)  # approximation: SE ≈ 0.39 / sqrt(PA)
ci_low, ci_high = obs_l21d - 1.96*se, obs_l21d + 1.96*se
print(f"L21d xwOBA: {obs_l21d:.3f} ± {se:.3f} → 95% CI [{ci_low:.3f}, {ci_high:.3f}]")
```

**Critical interpretation:** if the player's 2025 baseline xwOBA
FALLS INSIDE the L21d 95% CI, you cannot statistically distinguish
"breakout" from "noise around baseline." Downgrade the verdict
confidence accordingly — call it "POSSIBLE BREAKOUT, await more PA"
not "SUSTAINABLE BREAKOUT."

If L21d sample is below stabilization threshold (≤40 PA), the verdict
is **always** "TBD — re-run in 1-2 weeks."

---

## Step 2.5 — Bayesian shrinkage of L21d toward baseline (CRITICAL)

xwOBA stabilizes around k≈150 PA. Pull noisy short-window estimates
toward the stable baseline to avoid over-interpreting hot streaks:

```python
k = 150  # xwOBA stabilization threshold
baseline_xwoba = xwoba_2025  # or career mean if 2025 sample is thin
shrunk_l21d = (n_l21d * obs_l21d + k * baseline_xwoba) / (n_l21d + k)
shrunk_breakout_gap = shrunk_l21d - baseline_xwoba
print(f"Observed L21d gap: {obs_l21d - baseline_xwoba:+.3f}")
print(f"Shrunk gap (k=150): {shrunk_breakout_gap:+.3f}")
```

For breakout candidates, this prevents over-claiming. A hot 21-day
xwOBA of 0.444 (Steer example) shrunk toward a 0.293 baseline with
n=75, k=150 yields shrunk = 0.343 — still a meaningful improvement
(+0.050) but more honest than the raw +0.151 claim.

**The shrunk gap is the value that should anchor the sustainability
verdict, not the raw observed gap.**

---

## Step 2.6 — Year-over-year xwOBACON trajectory (breakout ceiling estimator)

Before assessing how "real" the current breakout is, check whether the xwOBACON improvement is part of a multi-year trend or just a within-season hot window:

```python
for yr in [2021, 2022, 2023, 2024, 2025, 2026]:
    sql = f"""
    SELECT COUNT(*) bb, AVG(estimated_woba_using_speedangle) xwobacon
    FROM read_parquet('data/research/xfp_cache/statcast_{yr}.parquet')
    WHERE batter=? AND events IS NOT NULL AND events != ''
      AND launch_speed IS NOT NULL
    """
```

| Year | Batted Balls | xwOBACON |
|---|---|---|
| 2021 | n | 0.XXX |
| ... | | |
| 2026 | n | 0.XXX |

**Interpretation for breakouts:**

- **xwOBACON rising year-over-year** → breakout is the continuation of a multi-year skill trajectory. **Highest sustainability.** The player has been improving; this season is confirmation, not aberration.
- **xwOBACON stable across years + current L21d xwOBACON UP significantly** → breakout is real but new, not part of a trend. **Moderate sustainability** — watch for regression to the stable baseline.
- **xwOBACON stable + current xwOBACON FLAT** → breakout is discipline-driven (fewer K, more BB) or BABIP hot. Sustainable in the K%/BB% dimension only; power/contact ceiling unchanged.
- **xwOBACON declining year-over-year** → any xwOBA "breakout" is almost certainly outcomes (BABIP hot, HR landing). **Low sustainability.** The contact platform is falling; outcomes temporarily obscure it.

**Surface in output:** `xwOBACON trajectory: RISING / STABLE / DECLINING (peak → current: ±0.XXX)` — this is the single most useful single-line summary for whether the breakout ceiling is real.

---

## Step 2.8 — xwOBACON separation (distinguish skill vs BABIP up, within-season)

A hot stretch can come from (a) real contact-quality improvement OR
(b) outcomes finding holes. Separate the two using xwOBACON (Step 2.6 covers the multi-year version; this is the within-season split):

```python
# xwOBACON = xwOBA on batted balls only (luck-decoupled from K%/BB%)
sql = """
SELECT AVG(estimated_woba_using_speedangle), COUNT(*)
FROM read_parquet('data/research/xfp_cache/statcast_2026.parquet')
WHERE batter=? AND events IS NOT NULL AND events != ''
  AND launch_speed IS NOT NULL
  AND game_date >= ?
"""
```

Compare xwOBACON across 2025 / 2026 season / L21d. A breakout backed
by xwOBACON improvement (e.g., 0.408 → 0.500+) is more sustainable
than one driven only by K%/BB% changes — because xwOBACON correlates
with EV/Barrel/bat-speed (the physical inputs).

If xwOBA is up but xwOBACON is FLAT or DOWN, the "breakout" is
discipline-driven (more BB%, fewer K%) — which CAN be sustainable
if the process metrics (whiff%, chase%) also support it, but the
contact-quality ceiling isn't actually higher.

---

## Step 3 — Rolling 21-PA xwOBA path

This distinguishes "steady climb" from "one hot week pulled the
average up":

```python
# Event-based rolling window (not date-based)
sql = """
SELECT game_date::DATE d, estimated_woba_using_speedangle xwoba
FROM read_parquet('{PARQ_26}')
WHERE batter={pid} AND events IS NOT NULL AND events != ''
  AND estimated_woba_using_speedangle IS NOT NULL
ORDER BY game_date
"""
df['roll_xwoba'] = df['xwoba'].rolling(window=21, min_periods=15).mean()
```

Show last 10 reading points of rolling 21-PA xwOBA. Look for:
- **Steady high band** (e.g., 0.480-0.560 sustained for last 30+ days)
  = sustainable
- **Single big spike** (0.250 → 0.600 in 3 days, hovering high)
  = recent fluke, watch for revert
- **Climbing trend** (0.300 → 0.400 → 0.480 over 4 weeks)
  = genuine process change happening

---

## Step 4 — Career-trajectory and age context

Annotate per player:
- **Age** (relevant to growth/decline curves)
- **Career history at this level** — has the player been here before?
  - Multiple prior seasons at the new rate → HIGHLY sustainable
  - 1 prior season → suggests "rediscovering known form" (Steer's 2023
    is the analog for his 2026 rebound)
  - No prior MLB time at this level → "rookie breakout" pattern
    (Montgomery) — needs more skill confirmation

Pull bio + prior-season summary from MLB Stats API or hardcode for
common players.

---

## Step 5 — Sustainability scorecard

Synthesize into a per-dimension scorecard:

| Dimension | What you want to see | Evidence quality |
|---|---|---|
| History at this level | Multiple seasons of similar production | ✗ none / ✓ 1 prior / ✓✓ 2+ prior |
| Process change (discipline) | Whiff/chase DOWN, zone-contact UP | ✗ static / ~ mixed / ✓✓ multi-axis improvement |
| Power change (bat speed/EV) | Bat speed +2mph, EV90 +2mph, hard-hit +5pt | ✗ flat or down / ✓ modest gain / ✓✓ +5pt or more |
| Stabilization | L21d sample crosses all thresholds | ✗ below / ✓ borderline / ✓✓ comfortably stabilized |
| Age curve | Young growth phase OR established peak | ✗ aging decline / ~ stable / ✓✓ growth window |
| Rolling 21-PA consistency | Sustained high band, not single spike | ✗ recent fluke / ~ climbing / ✓✓ steady high |

Verdict:

| Score | Verdict |
|---|---|
| All-✓✓ axes | **HIGHLY SUSTAINABLE — bet on it** |
| Process + power both ✓+ | **SUSTAINABLE NARROW BREAKOUT** (one dimension, e.g., contact-only or power-only) |
| Process ✗ but Power ✓ (or vice versa) | **OUTCOME-DRIVEN — capped ceiling, possible regression on the missing axis** |
| All metrics flat or worse | **HOT STREAK — expect revert** |

---

## Step 6 — Player-archetype identification

Cluster the player into a fantasy archetype using the skill profile.
Helps the user picture what production looks like long-term:

| Archetype | Profile signature | Fantasy ceiling/floor |
|---|---|---|
| **Five-tool elite** | High everywhere (xwOBA 95+, EV 95+, K-rate 60+, BB-rate 75+) | 3.0+ FP/g ceiling, 2.3 FP/g floor |
| **Contact specialist** | Elite K-rate / sweet-spot, modest EV/Barrel | 2.5 FP/g via AVG/OBP, capped power |
| **Power-or-bust** | Elite EV/Barrel/bat speed, poor whiff/chase | 3.0+ FP/g if HRs land, 2.0 floor if approach craters |
| **Aging veteran** | Skills declining year-over-year, history hides recent decay | tail-risk; floor falling |
| **Rookie growth** | Improving across multiple axes mid-season | High variance; trajectory matters more than current |

Show comparative archetype profiles when relevant. For example,
Suárez 2025 (49 HR / .228 AVG) is the canonical "power-or-bust"
ceiling outcome — use as a benchmark when evaluating new power-only
breakouts.

---

## Step 7 — Output format

```markdown
## Sustainability comparison: <P1> vs <P2> vs <P3>

### Per-player decomposition

#### <Player 1> (age N, context: <history>)
[4-column metric table per Step 1]
Stabilization status + L21d xwOBA CI: [Step 2]
**Shrunk gap vs raw gap: [Step 2.5] — anchor verdict to shrunk gap**
xwOBACON 2025 vs 2026 vs L21d: [Step 2.6]
Rolling 21-PA xwOBA path: [Step 3]
Sustainability scorecard: [Step 5]
Archetype: [Step 6]

[repeat per player]

### Cross-player synthesis
Which has highest sustainability confidence and why.
What each archetype implies for fantasy use.

### Recommendation
Map to user's actual decision (which to add / hold / sell).
```

---

### Calibrated examples (2026-05-25)

Three peak-type archetypes from the 2026-05-25 league-wide audit:

**PROCESS_DRIVEN — Ryan Jeffers (C, Boone's Bad Bullpen)**
Career %ile: 99.9% | rh3: 0.595 | Sust: IMPROVING
Bayes P(talent > .320): **81.0%** | Survival: **92.7%** (+30PA) / **82.2%** (+60PA) | Weeks to reversion: 6.7
All 5 physical inputs improved: bat_speed +1.1mph, EV90 +1.7mph, whiff% −4.9pt, z_contact% +5.6pt, xwOBACON +0.050
Trade window: HOLD_SHORT — even process-driven peaks revert; the survival curve buys ~6-7 weeks, not a half-season.

**OUTCOME_DRIVEN — Josh Naylor (1B, Frendy's Fantastic Team)**
Career %ile: 92.4% | rh3: 0.571 | Sust: REGRESS
Bayes P(talent > .320): **80.7%** — nearly identical to Jeffers — but process verdict: DECLINING.
No process metrics improved. Surface outcomes inflated over true skill.
Survival: 89.2% (+30PA) / **76.2%** (+60PA) | Weeks to reversion: 5.6
Cross-verdict: **SELL_HIGH_WARNING**. Bayes alone cannot distinguish archetype; process verdict is the separator.

**MIXED — Drake Baldwin (C, Frendy's Fantastic Team)**
Career %ile: 99.8% | rh3: 0.679 | Sust: STABLE
Bayes P(talent > .320): **100.0%** — highest in the league — yet trade window: HOLD_SHORT.
Survival: 91.4% (+30PA) / **80.0%** (+60PA) | Weeks to reversion: 5.6
Only 1/6 process metrics improved (xwOBACON +0.110). Elite Bayes reflects career level, not new skill level.
Cross-verdict: CONSENSUS_HOLD_PEAK. Even a 100% Bayes posterior doesn't override a 5.6-week survival clock.

Key takeaway: Jeffers, Naylor, and Baldwin share nearly identical survival horizons (~5-7 weeks) and all have
Bayes 80%+. What separates them is the process verdict — IMPROVING vs DECLINING vs MIXED. Always pull that
column first before acting on Bayes or surface rh3.

---

## Name-collision guard (mandatory before any rh3 lookup)

When building a `dict[name] → rh3 row` lookup, NEVER key on normalized
name alone. Two MLB players named "Max Muncy" exist (LAD batter_id 571970,
ATH batter_id 691777); a bare name dict silently assigns the wrong
projection. Canonical fix:

```python
import unicodedata
def _norm(s): return unicodedata.normalize('NFKD', str(s)).encode('ascii','ignore').decode('ascii').lower().strip()

rh3 = pd.read_csv('data/outputs/xfp_rh3_projections.csv')
rh3_idx = {}
dup_keys = set()
for _, row in rh3.iterrows():
    key = (_norm(row['player_name']), str(row.get('team', '')).upper())
    if key in rh3_idx:
        dup_keys.add(key)
    rh3_idx[key] = row
if dup_keys:
    print(f"WARNING: duplicate rh3 keys {dup_keys} — verify team-keyed resolution")

def rh3_row(name, team):
    return rh3_idx.get((_norm(name), str(team).upper()))
```

Use `pro_team` from the ESPN row as the second key. If unavailable, call
`resolve_batter_id(name, team=..., position=...)` from
`plv_clone.utils.name_match`.

---

## Anti-patterns this skill exists to prevent

- **Building `{_norm(name): row}` dicts from rh3 without team key.**
  Always key on `(norm_name, pro_team)` tuple to prevent same-name
  player collisions (canonical: Max Muncy LAD #39 vs ATH #331).
- **Calling a breakout sustainable on xwOBA alone.** Step 1's
  multi-axis table is non-optional. Montgomery had elite xwOBA
  improvement but whiff% actually got WORSE — that's an outcome
  fluke (HRs landing) on the same underlying skill profile.
- **Ignoring career history.** Steer's 2023 season is a real comp
  for his 2026 contact profile. Without that context, his L21d
  numbers look implausibly hot. With context, they're "rediscovering
  the 2023 player."
- **Confusing "young player" with "guaranteed growth."** Montgomery
  is 23 and elite bat speed, but the K-rate / whiff% profile is
  capped. Age helps the ceiling estimate, doesn't change the
  current ceiling cap.
- **Bootstrapping FP from a hot stretch and trusting the mean.**
  This is what `/hitter-compare` does — sometimes the mean is
  misleading because the underlying skill is unstable. Use THIS
  skill to determine if the bootstrap mean is trustworthy.
- **Skipping the stabilization check.** A 0.500 xwOBA on 15 PA is
  noise. Always state sample sizes vs stabilization thresholds.
- **Reporting raw observed gap instead of Bayesian-shrunk gap.** A
  hot L21d (e.g., Steer's +0.151 vs 2025 baseline) shrunk toward the
  baseline with k=150 is a much more honest number. The shrunk gap
  is what should anchor the SUSTAINABLE/NARROW/HOT-STREAK verdict.
- **Ignoring 95% CI on the L21d xwOBA.** If the 2025 baseline is
  inside the L21d CI, the "breakout" cannot be statistically
  distinguished from noise around the baseline. Downgrade to
  "POSSIBLE BREAKOUT, await more PA" rather than overclaiming.
- **Not separating xwOBA from xwOBACON.** A discipline-driven
  breakout (more BB%, fewer K%) shows up in xwOBA but not in
  xwOBACON. A contact-quality-driven breakout shows up in both. The
  latter is more sustainable.

---

## When NOT to use this skill

- Player is cold, not hot — use `/slump-or-decline` for bounce/decline
  analysis
- Single-player deep dive without comparison context — use
  `/fa-pickup-deep-dive`
- Pitcher (SP/RP) — different metrics needed (xERA, SIERA, pitch shape
  changes); could be built as `/pitcher-breakout-sustainability` later
- Quick FA scan — use `/fa-replacement-pool` first to narrow candidates
  then apply this skill to the shortlist

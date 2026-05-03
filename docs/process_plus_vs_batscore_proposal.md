# Proposal: Integrating Process+ with BatScore / BatSignal

*Unofficial public-data clone. Not affiliated with Pitcher List.*

---

## What Process+ measures that BatScore/BatSignal likely doesn't

Most fantasy frameworks — including most xwOBA-based systems — measure **outcomes after contact**.
BatScore / BatSignal are presumably built on exit velocity, hard-hit rate, barrel rate, or
expected stats derived from launch conditions.

Process+ is pitch-sequence-level and **decomposed by decision stage**:

| Component | What it captures | BatScore equivalent |
|---|---|---|
| **Discipline+** | Swing/take quality *before* contact — did the hitter take the right pitches? | No direct equivalent. Swing% and Chase% are volume, not value-adjusted. |
| **K-Avoidance+** | Whiff/chase rate vs. pitch expectation (K-avoidance skill) | Partially: K% implies contact failure, but not conditioned on pitch quality |
| **Power+** | xwOBA above pitch-level expectation on fair balls | Closest overlap: raw xwOBA, barrel rate, hard-hit% — but those are not pitch-adjusted |
| **Process+** | Combined | No single BatScore/BatSignal column maps here directly |

The core difference: **Process+ conditions every value on the pitch itself**. A hitter who
takes a 3-0 fastball for a strike hurts their Discipline+ even if they "look disciplined".
A hitter who avoids whiffing on an unhittable slider gets K-Avoidance+ credit. A hitter who
crushes a meatball is expected to — Power+ rewards only the excess.

---

## What BatScore/BatSignal likely captures better

- **True exit velocity profiles** — launch angle, max EV, 90th-percentile EV
- **Batted-ball type mix** — pull%, GB%, FB%, LD% — shapes long-term wOBA independently of count
- **Platoon splits and matchup exposure** — BatScore presumably adjusts for opponent quality
- **Park-adjusted outcomes** — Process+ makes no park adjustments (all pitch characteristics only)
- **Sprint speed / baserunning** — entirely outside Process+ scope

---

## Where Process+ adds the most signal

### 1. Identifying "unlucky" hitters (regression candidates)

```
Target: process_plus >= 108  AND  xwoba_on_contact < league_median_xwoba
```

These hitters are making good decisions and quality contact relative to pitch difficulty,
but their raw xwOBA is below median. This can indicate:
- Bad luck on BABIP / sequencing
- Elevated strand rate from team context
- Injury that suppresses contact outcomes but not decision-making

**Concrete query**: see `notebooks/02_leaderboards.ipynb` — Cell 4 "Fantasy Targeting".

### 2. Flagging hitters with structural discipline improvement

Discipline+ is highly stable (SB r=0.833 at 150 PA, YoY r=0.740). If a hitter's
Discipline+ improved YoY, it's likely real, not noise. BatScore metrics often lag
because they require in-play contact to manifest.

**Early-season tiebreaker**: Discipline+ at 50 PA is already reliable (SB r=0.741).
Use it to separate hitters with similar BatScore profiles in April/May.

### 3. Breakout identification

A hitter with elevated Process+ but depressed BatScore has demonstrated the underlying
process; the surface stats haven't caught up. Monitor:

```
Process+ >= 108  AND  "BatScore below top tercile"
```

Reciprocally: a hitter with strong BatScore but mediocre Process+ is a regression risk.
High exit velocity on pitches you shouldn't have swung at is not sustainable.

### 4. Separating contact quality from swing decisions

BatScore can't separate "hit it hard because he swings at hittable pitches" from
"hit it hard despite swinging at unhittable pitches". Process+ can. A hitter who
is Power+ 130 but Discipline+ 85 is swinging at bad pitches and still barreling them —
that's less sustainable than Power+ 125 with Discipline+ 115.

---

## Proposed correlation analysis (run once)

```python
# Load both leaderboards and merge on player name / MLBAM ID
merged = process_lb.merge(batscore_lb, on='player_id', how='inner')

# 1. Check information overlap
from scipy.stats import spearmanr
for comp in ['process_plus', 'discipline_plus', 'k_avoidance_plus', 'power_plus']:
    r, _ = spearmanr(merged[comp], merged['batscore'])
    print(f'{comp} vs BatScore: r={r:.3f}')

# 2. Find hitters where they disagree most
merged['disagreement'] = merged['process_plus'].rank(pct=True) - merged['batscore'].rank(pct=True)
# Large positive disagreement = Process+ likes them, BatScore doesn't (breakout candidates)
# Large negative disagreement = BatScore likes them, Process+ doesn't (regression risks)
```

Expected result: Power+ will correlate most strongly with BatScore (both capture
batted-ball damage). Discipline+ will have the lowest correlation — that's the novel signal.

---

## Proposed combined targeting framework

### BatSignal-style tier list augmented with Process+

| Signal | Source | Weight |
|---|---|---|
| Batted-ball damage (exit velo, barrel%) | BatScore | Primary — talent ceiling |
| Pitch-level decision quality | Discipline+ | Secondary — sustainable rate |
| K-avoidance vs. pitch expectation | K-Avoidance+ | Secondary — K% interpretation |
| xwOBA above pitch expectation | Power+ | Confirmation — correlated with BatScore |

**Tier definition (draft):**

| Tier | BatScore | Process+ | Interpretation |
|---|---|---|---|
| Tier 1 | Top 20% | ≥ 110 | Elite — high ceiling, good process |
| Tier 2 | Top 40% | ≥ 105 | Core starter |
| Breakout flag | Any | ≥ 112 with BatScore not in Top 20% | Buy-low target |
| Regression flag | Top 20% | < 92 | Sell-high candidate |
| Avoid | Bottom 40% | < 95 | No redeeming signal |

Thresholds are starting points. Calibrate against your historical hit rate.

---

## Process+ caveats to keep in mind

1. **Power+ is the noisiest component** (reliable at 100 PA vs. 25 PA for K-Avoidance+).
   Do not over-index on Power+ in early-season samples.

2. **Frozen scaling creates mild season drift**. Process+ scaling is frozen to 2021-2023
   training data. In any given scoring year, the league mean may sit at 101-103, not
   exactly 100. This is expected and does not affect relative rankings within a year.

3. **No park adjustment**. A hitter who plays in Coors vs. Dodger Stadium will have
   different batted-ball outcomes independent of pitch quality.

4. **No pitcher-quality adjustment in Discipline+**. Swinging at a Chase-zone pitch
   from Jacob deGrom and a Chase-zone pitch from a replacement-level arm have the
   same Discipline+ penalty. This is a deliberate scope choice (pitch features are
   included, but pitcher identity is not).

5. **Process+ is a one-year snapshot**. Use rolling trends
   (`process_plus_rolling_YYYY.csv`) for in-season signal.

---

*Build version: v1.0.0 (2026-04-23). This document should be updated if the
core Process+ math changes.*

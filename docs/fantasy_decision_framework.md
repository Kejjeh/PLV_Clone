# Fantasy Decision Framework — PLV + Process+

*Unofficial public-data clone. Calibrated on 2021–2024 Statcast data, v1.0.0.*

---

## Sample Thresholds — When to Trust Each Metric

| Metric | Minimum sample | Notes |
|---|---|---|
| **Process+** (combined) | **150 PA** | Below this = noise dominates |
| **Discipline+** | **50 PA** | Most stable component; reliable early |
| **Contact+** | **25 PA** | Extremely stable; trust quickly |
| **Power+** | **100 PA** | Noisiest component; wait for volume |
| **PLV** (pitcher) | **100 pitches** | Roughly 3–4 starts |
| **Rolling (30-day) values** | **20+ pitches / 10+ PA in window** | Below this = window too sparse |

**Confidence tiers used across all target boards:**
- **Tier A** — ≥ 400 PA (or 1,000+ pitches for pitchers). Full-season signal. Act on it.
- **Tier B** — 250–399 PA (or 400–999 pitches). Adequate sample. Use with rolling context.
- **Tier C** — 150–249 PA. Early signal. Flag for watchlist; confirm with next 2–3 weeks.

---

## Threshold Reference (2024 calibration)

All thresholds are percentile-based on 2024 qualified hitters (n=413, min 150 PA).

| Threshold label | Process+ | Discipline+ | Contact+ | Power+ | xwOBA |
|---|---|---|---|---|---|
| **Top 10%** | ≥ 115 | ≥ 115 | ≥ 115 | ≥ 115 | ≥ 0.44 |
| **Top 25% (strong)** | ≥ 108 | ≥ 109 | ≥ 109 | ≥ 107 | ≥ 0.40 |
| **Average** | ≈ 101 | ≈ 101 | ≈ 102 | ≈ 101 | ≈ 0.363 |
| **Bottom 25% (weak)** | ≤ 96 | ≤ 94 | ≤ 95 | ≤ 94 | ≤ 0.329 |

---

## What Qualifies as a Buy Target

**Definition:** Hitter whose process is strong but whose surface results haven't caught up.

**Hard criteria:**
- Process+ ≥ 108 (top 25%)
- xwOBA actual < 0.363 (below median) — surface underperformance signal

**Soft criteria (strengthen the case):**
- Discipline+ ≥ 109 (selective + disciplined)
- Power+ ≥ 107 (quality contact when he makes it)
- 30-day rolling discipline_value_mean above 0.075 (trending up recently)
- xwoba_vs_expected > 0.00 (hitting the ball harder than pitch quality predicts)

**How to use:** Sort `hitter_buy_targets_2024.csv` by Process+. Prioritize Tier A/B hitters
first. For Tier C, only act if rolling trend is also positive.

**What makes it a better buy:** Discipline+ is the most predictive and stable — a hitter
who is making better decisions (higher D+) is correcting a sustainable behaviour. Power+
improvement is real but reverts faster than Discipline+.

---

## What Qualifies as a Breakout Flag

**Definition:** Hitter who shows emerging elite process but isn't yet reflected in
traditional rankings or ADP.

**Hard criteria:**
- Process+ ≥ 110
- xwOBA actual < 0.400 (not yet in the top xwOBA quartile)
- Tier B or C sample (still accumulating — upside not yet priced)

**Soft criteria:**
- 30-day discipline_value_mean in the top 25% of rolling leaders
- Discipline+ ≥ 112 (exceptional discipline signal)
- Contact+ ≥ 109 (making contact on difficult pitches)

**How to use:** `hitter_breakout_flags_2024.csv`. These are add-low / priority
waiver targets. The process is real; the results haven't arrived.

---

## What Qualifies as a Regression Flag

**Definition:** Hitter whose surface results look strong but whose underlying process
is weak — results are likely to deteriorate.

**Hard criteria:**
- xwOBA actual ≥ 0.400 (top quartile in results)
- Process+ < 96 (bottom 25% in process)

**Soft criteria (strengthen the case):**
- Discipline+ < 94 (chasing, not selective)
- Power+ < 94 (contact quality below pitch expectation)
- 30-day rolling values also declining

**How to use:** `hitter_regression_flags_2024.csv`. Sell-high candidates.
Strong caution: check that strong surface stats aren't from a legitimate hot streak
that's already ended. Use rolling context to confirm.

**Important caveat:** A hitter can have weak Process+ and still be a good
fantasy asset if their raw exit velocity / barrel rate is elite. Cross-check
with BatScore before selling.

---

## Discipline Targets

**Definition:** Hitters who excel at the swing/take decision — they swing at
hittable pitches and lay off unhittable ones.

**Criteria:** Discipline+ ≥ 109 (top 25%)

**Why this matters for fantasy:** Discipline+ is the most stable metric (YoY r=0.74).
It is the earliest reliable signal of a hitter's true quality. Elite walk rate, low
K%, and consistent BABIP often trace back to strong Discipline+.

**Actionable use:** In points leagues, walks and strikeout avoidance are explicit.
In roto/category leagues, high OBP hitters with strong Discipline+ tend to hold their
walk rate even in slumps.

---

## Power Targets

**Definition:** Hitters generating xwOBA above what their pitch diet predicts.

**Criteria:** Power+ ≥ 107 (top 25%)

**Why this matters:** Power+ isolates batted-ball damage from pitch selection.
A hitter with high Power+ and mediocre BatScore is getting unlucky on BABIP or
strand rate — not generating weak contact.

**Best use:** Pair with BatScore. Power+ ≥ 107 + BatScore strong = elite.
Power+ ≥ 107 + BatScore mediocre = under-the-radar buy.

---

## Full-Season vs 30-Day Rolling — How to Weigh Them

| Situation | Lean toward |
|---|---|
| Hitter has ≥ 400 PA, stable all year | **Full-season** — larger sample wins |
| Hitter had a known injury or role change mid-season | **Post-event rolling** — ignore pre-event |
| Making a waiver add decision this week | **30-day rolling** — most recent process is most relevant |
| Evaluating for a dynasty trade (1–2 year view) | **Full-season** for stability; use rolling to confirm direction |
| Hitter is at Tier C (150–249 PA) | **Rolling only** — season is too short to aggregate |
| Full-season and rolling disagree | See below |

### When full-season and rolling disagree

**Rolling much better than full-season:** Recent breakout. Check contact rate and
chase rate trend. If both are improving, weight rolling more. If only power is up,
be cautious (power streaks are noisy).

**Rolling much worse than full-season:** Recent slump. Distinguish: is Discipline+
falling (concerning, potentially structural) or only Power+ falling (more likely
variance)? Discipline+ slumps matter more.

**Heuristic:** Weight rolling at 40% if full-season sample ≥ 300 PA. Weight
rolling at 60% if full-season is Tier C or there's a known recent event.

---

## Resolving Disagreement Between BatScore and Process+

BatScore/BatSignal is primarily a **batted-ball damage** framework.
Process+ is a **pitch-sequence decision quality** framework.
They measure partially overlapping but distinct things.

### BatScore high, Process+ low → **Regression candidate**

The hitter is generating exit velocity but making poor decisions (chasing, swinging
at unhittable pitches). This is sustainable only if raw power is truly elite
(think: free-swinging slugger archetype). If the hitter is NOT a known free-swinger,
this is a sell signal. Check Discipline+: if < 90, that's the culprit.

### Process+ high, BatScore low → **Buy candidate / stealth value**

The hitter is making excellent decisions and generating contact quality above pitch
expectation, but the raw exit velocity profile doesn't look impressive. This can
mean: (a) unlucky BABIP, (b) hitter generates average EV but to high-leverage zones,
or (c) contact quality on difficult pitches is genuinely better than it looks.
Target aggressively on the waiver wire.

### Both high → **Conviction hold / priority add**

Elite process + elite batted-ball quality. These are the Aaron Judge / Ohtani tier.
Do not trade away. Add at any price.

### Both low → **Drop / avoid**

No redeeming signal. Move on.

### Partial agreement (one high, one neutral) → **Hold and monitor**

Do not act on mild disagreement. Check rolling trends for a recent direction change.
Act only if the signal strengthens over the next 2 weeks.

---

*Framework calibrated on 2024 data. Thresholds should be re-validated after
each season using `scripts/validate_outputs.py`.*

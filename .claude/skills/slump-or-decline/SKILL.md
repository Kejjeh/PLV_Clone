---
name: slump-or-decline
description: Rigorous diagnostic of whether an underperforming hitter is in luck-driven outcome variance (will bounce) or real skill decline (won't). Uses L150 PA as the stable baseline, sample-size CIs, Bayesian shrinkage, xwOBACON separation, process-metric decomposition (bat speed, whiff%, chase%, Z-contact%, K%), pitch-mix changes, calendar history, and a three-test statistical convergence panel — (1) MC bounce simulator (10k bootstrap sims from career rolling-150 distribution); (2) Bayesian posterior talent (conjugate normal-normal update, P(true talent > .320)); (3) historical comp matcher (54k real 2015-2025 snapshots at similar career %ile/PA/month, actual outcome distributions). DROP verdict requires all 3 tests to agree. Outputs HOLD / SELL-HIGH / DROP / NOT-SLUMPING-STRUCTURAL. Use when the user asks should-I-hold X, is-this-slump-real, should-I-drop X, or any player is at a career-low percentile.
---

# slump-or-decline

You are diagnosing whether a hitter's recent underperformance is
**outcome luck on holding skill** (will bounce) or **real talent
decline** (won't). The two look identical at the box-score level —
diagnostic requires statistical rigor and multi-axis decomposition.

The skill exists because we made this call wrong on Vlad Jr.
(2026-05-18→19) using a noisy 21-day xwOBA window without sample-size
confidence. The deep-dive revealed L21d 95% CI included his career
baseline, Bayesian-shrunk gap was −0.022 (not −0.069), process
metrics were IMPROVING (whiff% −5pt, Z-contact +2pt), and xwOBACON
collapse pointed to pure BABIP variance. The skill must produce
calibrated verdicts, not noisy point estimates.

---

## Three lenses with named failure modes

The convergence panel is built on **three independent statistical lenses**, each with its own anchor and its own known failure mode. The DROP verdict requires all three to agree — disagreement is the insight, not noise.

| Lens | What it measures | Anchor | Known failure mode |
|---|---|---|---|
| **MC bounce simulator** | 10k bootstrap sims from career rolling-150 distribution → "what fraction of career windows recover to median within the next 150 PA?" | Career rolling-150 distribution (stationarity assumed) | Mis-weights regime shifts: if the hitter's true talent has stepped down (post-injury, age cliff), the career distribution over-represents prior talent. Sims look bullish on a player whose underlying talent has actually decayed. |
| **Bayesian posterior talent** | Conjugate normal-normal update: prior = career mean; data = recent window; output = P(true talent > .320) | Prior strength scales with career PA — large careers anchor strongly | Strong-prior players (e.g. 10+ year vets) get pulled toward career baseline regardless of how bad the recent stretch is, masking real decline. Conversely, short-career players over-fit recent noise. |
| **Historical comp matcher** | 54k snapshots 2015-2025; match on career %ile + PA + month-of-season; report empirical T+150 distribution | Population of comparable past situations | Bucketing on career %ile alone misses archetype context — a power hitter at career-low and a contact hitter at career-low have different recovery base rates. Comp set quality depends on having enough age-matched snapshots; thin for very old or very young players. |

The diagnostic value is in **disagreement**: if MC says bounce but Bayesian says decline, the lenses are disagreeing on the regime-shift question, and the call should be SELL-HIGH (intermediate verdict) rather than HOLD or DROP.

---

## Inputs

1. **Player name(s)** — single or short list (≤5). For a roster-wide
   sweep, use `/roster-audit` instead.
2. **Optional context** — "deciding whether to drop", "trade-target
   evaluation", "FA candidate check"

---

## Step 1 — Production-line decomposition (multi-year)

For each player, pull career stats AND each of the last 3-4 seasons
individually (not just 2025) from MLB Stats API. Compute FP/g per
season using BrownU formula:
**FP = R + TB + RBI + BB + HBP + SB − K**

Display:
```
2023 (G): X.XX FP/g | .AVG | xwOBA from statcast 2023
2024 (G): X.XX FP/g | .AVG | xwOBA from statcast 2024
2025 (G): X.XX FP/g | .AVG | xwOBA from statcast 2025
2026 to-date (G): X.XX FP/g | .AVG
Career (G): X.XX FP/g | .AVG
```

Compute gap-vs-career and gap-vs-2025. Flag COLD/AT-BASELINE/HOT.

This gives the player-level baseline. A player with 4 prior seasons
in the same range has a more stable "true talent" than one with
huge year-to-year variance.

---

## Step 2 — Multi-window xwOBA path (CRITICAL: use L150 PA as primary baseline)

Pull xwOBA AND xBA across multiple windows. **L150 PA is the
stable baseline; L21d and L7d are change-detectors with CI, never
the verdict driver alone.**

```python
import duckdb
con = duckdb.connect()
# Compute L150 PA from event-based rolling, NOT date-based
sql_l150 = """
WITH events AS (
  SELECT game_date, estimated_woba_using_speedangle xwoba
  FROM read_parquet('data/research/xfp_cache/statcast_2026.parquet')
  WHERE batter=? AND events IS NOT NULL AND events != ''
  ORDER BY game_date DESC
  LIMIT 150
)
SELECT AVG(xwoba), COUNT(*), MIN(game_date), MAX(game_date) FROM events
"""
```

Display table:

| Window | PA | xwOBA | xBA | EV90 | K% | HR |
|---|---|---|---|---|---|---|
| L7d | n | x | x | x | x | n |
| L14d | n | x | x | x | x | n |
| L21d | n | x | x | x | x | n |
| L30d | n | x | x | x | x | n |
| **L150 PA** (event-based, may span 2025+2026) | 150 | x | x | x | x | n |
| 2026 season | n | x | x | x | x | n |
| 2025 | n | x | x | x | x | n |

If L150 PA goes back into 2025 (early-season player), span both years
and document the date range. This handles the "we don't have a full
season of 2026 yet" problem cleanly.

---

## Step 3 — Sample-size confidence intervals (MANDATORY)

For every window smaller than 150 PA, compute and surface the 95% CI:

```python
import numpy as np
def xwoba_ci(xwoba, n, sd=None):
    """Approximate xwOBA SE; default sd≈0.39 if not computed."""
    se = (sd / np.sqrt(n)) if sd else (0.39 / np.sqrt(n))
    return (xwoba - 1.96*se, xwoba + 1.96*se), se
```

Display:
```
L7d  xwOBA 0.269 ± 0.076 → 95% CI [0.121, 0.417]
L14d xwOBA 0.293 ± 0.049 → 95% CI [0.198, 0.389]
L21d xwOBA 0.315 ± 0.037 → 95% CI [0.243, 0.387]
L30d xwOBA 0.343 ± 0.034 → 95% CI [0.275, 0.410]
```

**Critical interpretation:** if the player's career/L150 baseline FALLS
INSIDE the L21d 95% CI, you cannot statistically distinguish "slump"
from "noise around baseline." Vlad Jr. example: L21d CI [0.243, 0.387]
included his 2025 baseline 0.384. No DECLINING call warranted.

If you make a DECLINING call when the baseline is inside CI, you're
overstating confidence. Either state explicitly "not statistically
distinguishable from baseline" OR widen the window.

---

## Step 4 — Bayesian shrinkage of L21d toward the L150 anchor (not 2025!)

xwOBA stabilizes around k≈150 PA. Pull noisy L21d estimates toward
the **L150 pre-L21d baseline** (most-recent stable estimate of true
talent), not toward 2025 full-season. The 2025 anchor over-weights
year-old data and gives stale verdicts.

```python
k = 150  # xwOBA stabilization
# Anchor priority:
#   1. L150 PA excluding L21d window (pre-slump baseline) — best
#   2. L150 PA including L21d (fallback if pre-L21d <50 PA)
#   3. 2025 full season (fallback if no L150 available)
#   4. 2024 full season (fallback for early-season callups)
#   5. Season-pre-L21d (fallback for rookies)

anchor_xwoba = pre_L21d_xwoba if pre_L21_n >= 50 else (L150_xwoba or xwoba_25)
shrunk_l21d = (n_l21d * obs_l21d_xwoba + k * anchor_xwoba) / (n_l21d + k)
shrunk_gap = shrunk_l21d - anchor_xwoba
# This is the gap to report, NOT the raw observed gap
```

**Why L150 pre-L21d, not 2025:**
- Anchoring against 2025 over-weights data that's a year stale.
- Vlad Jr. example: vs 2025 (0.384) shrunk gap −0.022. Vs L150 pre-L21d
  (0.374) shrunk gap −0.019. Similar, but L150 is more current.
- Salvy Perez critical example: vs 2025 (0.357) shrunk gap −0.030 →
  classified REAL_DECLINE. Vs L150 pre-L21d (0.236) shrunk gap +0.009 →
  classified NEUTRAL (his recent stretch is BETTER than his pre-L21d
  baseline). The 2025-anchored verdict was wrong because Perez had
  already been declining for weeks before L21d.

Always show BOTH the L150 baseline AND the 2025 reference in output —
2025 catches year-over-year decline (which still matters for trade
context and contract decisions), but L150 drives the immediate verdict.

---

## Step 4.5 — Year-over-year xwOBACON trajectory (structural decline detector)

**This is the step that distinguishes "recovering from a familiar trough" from "the floor is lower now."**

A player can have the exact same rolling xwOBA trough (e.g., 0.285) in two different years — once as pure variance (recovers to career mean) and once as structural decline (recovers to a lower ceiling). The xwOBACON trajectory across years is the tell.

```python
# Pull full-season xwOBACON for each year, sorted ascending
for yr in [2021, 2022, 2023, 2024, 2025, 2026]:
    sql = f"""
    SELECT COUNT(*) bb, AVG(estimated_woba_using_speedangle) xwobacon
    FROM read_parquet('data/research/xfp_cache/statcast_{yr}.parquet')
    WHERE batter=? AND events IS NOT NULL AND events != ''
      AND launch_speed IS NOT NULL
    """
```

Build the year-by-year table:

| Year | Batted Balls | xwOBACON |
|---|---|---|
| 2021 | n | 0.XXX |
| 2022 | n | 0.XXX |
| 2023 | n | 0.XXX |
| 2024 | n | 0.XXX |
| 2025 | n | 0.XXX |
| 2026 | n | 0.XXX |

**Interpretation rules:**

- **xwOBACON stable across years (within ±0.015)**: prior-year troughs are valid recovery templates. A trough in 2026 at the same xwOBA depth as a 2023 trough predicts a similar recovery.
- **xwOBACON declining year-over-year (each year lower)**: prior recovery templates are NOT valid. The player's contact quality ceiling is falling. A recovery from a trough will hit a lower ceiling than it did in 2023.
- **xwOBACON up year-over-year**: player is improving — a trough is almost certainly variance.

**Key threshold:** If xwOBACON has declined ≥ 0.030 from peak to current full-season, classify as **STRUCTURAL CONTACT DECLINE** regardless of how many prior troughs/recoveries occurred. The 0.030 threshold corresponds to roughly one full skill tier (e.g., league-avg contact → below-avg contact).

**The Turner pattern (canonical example):** 2026 rolling xwOBA at 0.285 looks identical to 2023 trough at 0.285. But:
- 2023 trough xwOBACON: 0.396 (stayed high during trough → outcomes not falling, skill intact)  
- 2026 full-season xwOBACON: 0.330 (66pt lower → contact quality genuinely lower)
The 2023 recovery (to 0.363 xwOBA) happened on a 0.396 xwOBACON platform. In 2026, the platform is 0.330 — the recovery ceiling is lower.

**Output:** Append to the verdict block:
```
xwOBACON trajectory: [year list] → STABLE / DECLINING / IMPROVING
YoY drop from peak: −0.XXX (STRUCTURAL flag if ≥ 0.030)
Recovery ceiling adjustment: prior templates predict X.XXX → adjusted ceiling X.XXX
```

---

## Step 5 — xwOBACON separation (CRITICAL for BABIP variance detection)

xwOBA combines (a) walk/K outcomes (no-contact events) with
(b) contact outcomes. Slumps can come from either source. To
distinguish:

```python
# xwOBACON = xwOBA only on batted balls (launch_speed IS NOT NULL)
sql = """
SELECT AVG(estimated_woba_using_speedangle), COUNT(*)
FROM read_parquet('data/research/xfp_cache/statcast_2026.parquet')
WHERE batter=? AND events IS NOT NULL AND events != ''
  AND launch_speed IS NOT NULL
  AND game_date >= ?
"""
```

Display xwOBACON across all windows. Compare to xwOBA:

- **xwOBA down + xwOBACON down + EV90 down + bat-speed down** =
  real contact-quality decline. SLUMP IS SKILL-DRIVEN.
- **xwOBA down + xwOBACON down BUT EV90 holding + bat-speed holding** =
  contact quality intact, outcomes not landing (defensive positioning,
  bad spray luck). SLUMP IS BABIP-VARIANCE.
- **xwOBA down BUT xwOBACON holding** = K%/BB% changed; check Step 6
  for the K-rate story.

Vlad example: xwOBACON L21d 0.290 vs 2025 0.408 (down sharply) BUT
EV90 still 105.7 (elite) AND bat-speed still 75.3 (elite). Diagnosis:
**outcomes not finding gaps** (BABIP variance), not skill decline.

---

## Step 6 — K% decomposition (outcome breakdown)

```python
# Per window, compute share of outcomes
sql = """
SELECT COUNT(*) pa,
  SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END)*1.0/COUNT(*) k_rate,
  SUM(CASE WHEN events='walk' THEN 1 ELSE 0 END)*1.0/COUNT(*) bb_rate,
  SUM(CASE WHEN events IN ('single','double','triple','home_run') THEN 1 ELSE 0 END)*1.0/COUNT(*) hit_rate,
  SUM(CASE WHEN events IN ('field_out','force_out','grounded_into_double_play','fielders_choice','double_play','sac_fly') THEN 1 ELSE 0 END)*1.0/COUNT(*) out_rate
FROM read_parquet('data/research/xfp_cache/statcast_2026.parquet')
WHERE batter=? AND events IS NOT NULL AND events != '' AND game_date >= ?
"""
```

Look for:
- **K% UP + Hit% DOWN** → swing-and-miss is driving the slump (concerning)
- **K% DOWN + BB% UP + Hit% DOWN + Out% UP** → contact rate fine but outs on contact is the problem (BABIP variance — bounce expected)
- **K% UP + BB% DOWN** → discipline collapse (concerning)
- **K% flat + Hit% down + Out% up on in-play** → pure BABIP variance

Vlad example: K% L21d 9.9% (DOWN from 13.5% in 2025), BB% UP, Hit% DOWN,
Out% on in-play UP from 47.6% to 60.6%. **Discipline IMPROVING, outcomes
worse — pure BABIP variance.**

---

## Step 7 — Process metrics across windows (the leading indicator)

Process metrics (bat speed, whiff%, chase%, Z-contact%) stabilize
faster than xwOBA — bat speed at ~25-30 swings, whiff% at ~100
swings. They reveal SKILL changes directly.

```python
sql = """
WITH p AS (
  SELECT description, zone, bat_speed,
    CASE WHEN description IN ('swinging_strike','swinging_strike_blocked','foul','foul_tip','hit_into_play') THEN 1 ELSE 0 END is_swing,
    CASE WHEN description IN ('swinging_strike','swinging_strike_blocked','foul_tip') THEN 1 ELSE 0 END is_whiff,
    CASE WHEN description IN ('foul','hit_into_play') THEN 1 ELSE 0 END is_contact,
    CASE WHEN zone BETWEEN 1 AND 9 THEN 1 ELSE 0 END in_zone
  FROM read_parquet('data/research/xfp_cache/statcast_2026.parquet')
  WHERE batter=? AND game_date >= ?
)
SELECT
  AVG(bat_speed) bs,
  COUNT(*) FILTER (WHERE is_swing=1) swings,
  COUNT(*) FILTER (WHERE is_whiff=1) whiffs,
  COUNT(*) FILTER (WHERE is_swing=1 AND in_zone=0) ooz_sw,
  COUNT(*) FILTER (WHERE in_zone=0) ooz_p,
  COUNT(*) FILTER (WHERE is_swing=1 AND in_zone=1 AND is_contact=1) iz_con,
  COUNT(*) FILTER (WHERE is_swing=1 AND in_zone=1) iz_sw
FROM p
"""
```

Display table comparing 2025 / 2026 season / L21d / L7d:

| Metric | 2025 | 2026 szn | L21d | L7d |
|---|---|---|---|---|
| Bat speed | x | x | x | x |
| Whiff% | x% | x% | x% | x% |
| Chase% | x% | x% | x% | x% |
| Z-Contact% | x% | x% | x% | x% |

Interpretation:
- **Bat speed −2+ mph in L21d** = real physical decline (injury or age)
- **Whiff% UP + Z-Contact DOWN** = swing-and-miss problem worsening (skill)
- **Whiff% DOWN + Z-Contact UP** = discipline IMPROVING (bounces underway, even if xwOBA hasn't caught up)
- **Chase% UP** by itself = aggressiveness change, not necessarily skill loss

Vlad example: bat speed stable 75.3, whiff% DOWN to 16.9% from 21.5%,
Z-contact UP to 86.1% from 84.2%. **Discipline is BETTER than 2025.
The "slump" isn't a skill problem.**

---

## Step 8 — Pitch-mix attack (are pitchers attacking differently?)

```python
sql = """
SELECT COUNT(*) total,
  SUM(CASE WHEN pitch_type IN ('FF','FT','SI','FC') THEN 1 ELSE 0 END) fb_n,
  SUM(CASE WHEN pitch_type IN ('SL','CU','KC','SV','ST') THEN 1 ELSE 0 END) brk_n,
  SUM(CASE WHEN pitch_type IN ('CH','FS','SP','EP','KN') THEN 1 ELSE 0 END) off_n
FROM read_parquet('data/research/xfp_cache/statcast_2026.parquet')
WHERE batter=? AND pitch_type IS NOT NULL AND game_date >= ?
"""
```

(SQL parser note: avoid using `off` as a column alias — it's a reserved
word in DuckDB. Use `off_n` or `offspeed_n`.)

Compare FB%/BRK%/OFF% across 2025 / 2026 season / L21d. A 5+ percentage-
point shift in pitch mix may indicate scouting reports adapted to the
hitter — these usually self-correct as the hitter adjusts back, but
flag for context.

---

## Step 9 — Splits check (concentrated weakness?)

```python
sql = """
SELECT
  CASE WHEN home_team=? THEN 'home' ELSE 'away' END venue,
  p_throws,
  COUNT(*) pa, AVG(estimated_woba_using_speedangle) xwoba,
  SUM(CASE WHEN events='home_run' THEN 1 ELSE 0 END) hr
FROM read_parquet('data/research/xfp_cache/statcast_2026.parquet')
WHERE batter=? AND events IS NOT NULL AND events != ''
GROUP BY 1, 2 ORDER BY 1, 2
"""
```

(Need the player's home team abbreviation as parameter.)

Look for concentrated weakness:
- vs LHP only (platoon adjustment? small sample?)
- away only (travel/park issue?)
- One specific opponent (small-sample matchup luck)

A slump concentrated in one split is more recoverable than a slump
spread across all splits.

---

## Step 10 — Calendar history (is this month historically slow?)

```python
for yr in [career_years]:
    sql = f"""
    SELECT COUNT(*) pa, AVG(estimated_woba_using_speedangle) xwoba,
           SUM(CASE WHEN events='home_run' THEN 1 ELSE 0 END) hr
    FROM read_parquet('data/research/xfp_cache/statcast_{yr}.parquet')
    WHERE batter=? AND events IS NOT NULL AND events != ''
      AND EXTRACT(MONTH FROM game_date)={current_month}
    """
```

Surface each prior year's same-month performance. Some players have
documented seasonal patterns (cold April, hot July). If "May 2024" and
"May 2023" were also below career rates, the current slump is
seasonal, not a true talent change.

---

## Step 11 — Injury/news check

```python
from app.espn_connector import get_my_roster_with_injuries, get_injury_details
roster = get_my_roster_with_injuries()
player_row = roster[roster['player_name'].str.contains(name, ...)]
if len(player_row) and player_row['injured'].iloc[0]:
    details = get_injury_details([player_row['player_id'].iloc[0]])
    # Surface injury_type, injury_detail, days_until_return
```

For non-roster players (FAs, opponents' players), check the ESPN FA
pool's `injuryStatus` field. If the player has been DTD or quietly
nursing something, that explains a real-seeming decline.

---

## Step 12 — Rolling 30-PA xwOBA trajectory (when did slump START?)

```python
df = con.execute(f"""
  SELECT game_date::DATE d, estimated_woba_using_speedangle xwoba
  FROM read_parquet('data/research/xfp_cache/statcast_2026.parquet')
  WHERE batter={pid} AND events IS NOT NULL AND events != ''
    AND estimated_woba_using_speedangle IS NOT NULL
  ORDER BY game_date
""").df()
df['roll_30'] = df['xwoba'].rolling(window=30, min_periods=20).mean()
```

Sample ~15 evenly-spaced points and show the trajectory. Identifies:
- Slump start date (when did rolling-30 drop?)
- Acute drop (single-event injury?) vs gradual decay (skill loss)
- Recovery in progress (rolling-30 climbing back)

---

## Step 13 — rh3 slump signals (existing model output)

From `data/outputs/xfp_rh3_projections.csv`:

| Column | Note |
|---|---|
| `slump_pct_rank` | Severity (0-100) |
| `slump_n_comparable` | Historical sample size |
| **`slump_bounce_pct`** | **% of comparables who bounced (stored 0-100, NOT decimal)** |
| `slump_next_rate` | Mean FP/PA next 21d for bouncers |
| `slump_delta` | Expected vs current FP/PA gap |

**Don't double-multiply slump_bounce_pct by 100** — it's already stored
as a percentage 0-100, not a decimal proportion. Values like 81, 97,
100 are the percentages directly.

---

## Step 14 — Three-test statistical convergence (replaces single MC step)

Run all three tests. A HOLD verdict requires ≥ 2 of 3 to support bounce.
A DROP verdict requires all 3 to support decline — which is genuinely rare.

### Step 14a — MC bounce simulator (10k career-distribution bootstrap)

```python
from scripts.xfp.mc_bounce_simulator import batch_mc_bounce
mc = batch_mc_bounce([batter_id], n_sim=10_000)
```

The simulator draws 10,000 samples from the player's OWN career rolling-150
xwOBA distribution (not a parametric assumption), then applies 30-PA shrinkage:
`sim_30pa = (30 * sample + 150 * career_mean) / 180`

Report:
- **P(bounce above career median)** — what fraction of simulations project
  next-30PA xwOBA above the career median? The cleanest single number.
- **Expected xwOBA next 30PA** and **95% CI** on the distribution.
- If P(bounce > median) > 55%: bounce is more likely than not from career history alone.
- If P(bounce > median) < 40%: career distribution itself says this player
  structurally lives in the lower range — more information needed.

### Step 14b — Bayesian posterior talent estimate

```python
from scripts.xfp.bayesian_talent_estimator import batch_bayesian_talent
b = batch_bayesian_talent([batter_id])
```

Conjugate normal-normal update:
- **Prior:** career rolling-150 xwOBA distribution (mean μ₀, variance σ₀²)
- **Likelihood:** observed L21d PA events (mean x̄ᵢ, n observations)
- **Posterior:** precision-weighted combination

Report:
- **posterior_mu** — best current estimate of true talent level (shrinks
  L21d observation toward career prior by how much the L21d sample moves precision)
- **95% credible interval** [ci_low, ci_high]
- **P(true talent > .320)** — P above league average. The single most
  useful number for a drop decision:
  - > 70%: clearly above-average talent, slump is noise
  - 40-70%: borderline, need other signals
  - < 40%: talent may genuinely be at or below average right now
- **Games to 200 FP at career rate** — if talent is at prior_mu, how
  long until 200 RoS FP? Frames the recovery timeline concretely.

Note: posterior_mu is a BETTER estimate than L21d xwOBA alone AND a
better estimate than 2025 xwOBA alone. It correctly weights how much
new information (L21d PA) should update a career-long prior.

### Step 14c — Historical comp matcher (2015-2025 outcome distributions)

```python
from scripts.xfp.historical_comp_matcher import batch_historical_comps
comps = batch_historical_comps([batter_id])
```

Finds ALL real historical players (2015-2025 Statcast) who were at:
- Similar career percentile (±10 percentile points)
- Similar career PA count (±20%)
- Similar calendar month (±1 month)

And shows what actually happened to them next.

Report:
- **n_comps** — number of real historical matches. > 200 = statistically
  reliable; 50-200 = directional; < 50 = informational only.
- **P(bounced within 30 PA)** — fraction of real comps who had a
  meaningful xwOBA improvement (> +0.010) in the next 30 PA events.
- **P(bounced within 60 PA)** — for slower-building recoveries.
- **Median next-30PA xwOBA + 10th/90th percentile range** — the full
  outcome distribution. The 10th percentile is the realistic downside.
- **comp_sample** — up to 5 example real comps for context ("Javier Báez
  (2023) at 8% form" etc.)

This is the most epistemically rigorous test: it makes no distributional
assumptions, uses no model, and is grounded entirely in historical reality.
When n_comps > 500, treat hist_p_bounce as near-ground-truth for what
happens to players in this exact situation.

---

## Step 15 — Verdict synthesis (4-test calibrated, not point-estimate)

Combine Steps 2-13 AND all three Step 14 tests into a calibrated verdict.
**The xwOBA L21d gap ALONE should never drive the verdict** — it must be
cross-checked with CI, shrinkage, xwOBACON, process metrics, AND now
the three statistical tests.

**Verdict decision matrix:**

| Verdict | Required evidence |
|---|---|
| **HOLD — bounce expected** | ≥ 2 of: (a) anchor_in_CI=True OR (b) MC P>median > 55% OR (c) Bayes P>avg > 60% OR (d) hist_p_bounce > 60% AND ≥ 1 of: process IMPROVING OR K-decomp BABIP_DRIVEN OR xwOBACON gap < 0.040 |
| **HOLD with caveat** | Mixed statistical signals (2 tests say bounce, 1 says decline). Watch 2 weeks. |
| **SELL-HIGH** | Bayes posterior_mu < 0.280 + hist_p_bounce < 45% + process DECLINING + shrunk gap < −0.050. Market still values player. Sell while perception lags. |
| **DROP** | ALL of: Bayes P>avg < 30% + hist_p_bounce < 45% + MC P>median < 40% + REGRESS + process DECLINING/MIXED + shrunk gap < −0.060 + age-decline plausible. This gate is intentionally strict. **Note: STRUCTURAL CONTACT DECLINE (Step 4.5, xwOBACON YoY drop ≥ 0.030) lowers the DROP bar** — prior recovery templates are invalid; a "recoverable trough" pattern can still be a genuine decline if the xwOBACON platform itself has fallen. |
| **NOT SLUMPING (structural)** | Current rate ≈ career rate. action depends on roster slot pressure. |

Always surface in the output:
- Shrunk gap (not raw)
- Process-metric direction (leading indicator)
- xwOBACON gap (BABIP-variance signal)
- MC P(bounce > median) [Step 14a]
- Bayes posterior μ + P(true talent > .320) [Step 14b]
- Hist n_comps + P(bounce 30PA) [Step 14c]
- "N games to break 200 RoS at career rate" as recovery anchor
- Confidence statement ("X PA in L21d — verdict has ±Y uncertainty")

---

### Calibrated examples (2026-05-25)

**Freddie Freeman — CONSENSUS_HOLD_BOUNCE**
Career %ile 14.1%, but process is IMPROVING on every axis (whiff% −5.7pt,
chase% −4.5pt, Z-contact% +5.4pt, EV90 +1.8mph). Bayesian P(talent > .320)
= 97.0%. MC 54.6%, hist 49.0% (104 comps). Anchor in CI. Three tests are
split but process override is decisive: outcome noise, not skill decline.

**Vlad Guerrero Jr. — HOLD_NOISE**
Career %ile 13.2%, DTD (bruise, right). Anchor in CI (shrunk gap +0.005 vs
anchor 0.343). 596 age-matched historical comps → 65.1% bounce rate. MC
53.1%, Bayes P(>avg) 84.8%. BABIP-driven K-decomp. Verdict: noise.
Process notes worsening (chase% +11.3pt, EV90 −5.5mph) — watch the
DTD timeline but statistical tests do not support a drop call.

**Rafael Devers — SPLIT-SIGNAL (why all 3 tests matter)**
MC P(bounce) = 12.3% (alarming). Bayes P(talent > .320) = 70.9%.
Hist P(bounce 30PA) = 72.0% (293 comps). Three tests point in three
directions. Single-test verdict would be wrong in either direction.
Anchor is in CI (shrunk gap +0.016) and process is declining but small;
correct call is HOLD_NOISE with close monitoring — not DROP (MC alone
would trigger), not safe HOLD (process declining on all axes).

**Corey Seager — HOLD_NOISE but watch**
Anchor in CI, MC 70.6%, Bayes 88.4%, hist 72.1% (340 comps) — statistics
all say hold. But process is declining on every axis (whiff% +4.6pt,
chase% +8.3pt, Z-contact% −4.4pt, EV90 −1.5mph, hard-hit% −8.6pt) AND
active DTD (inflammation, not specified). The statistical tests override for
now, but if process metrics don't stabilize in the next 14 days, revisit.

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

When pulling the player via ESPN (roster or FA pool), `pro_team` is always
available. Use it as the second key. If `pro_team` is absent, call
`resolve_batter_id(name, team=..., position=...)` from
`plv_clone.utils.name_match` instead.

---

## Anti-patterns this skill exists to prevent

- **Building `{_norm(name): row}` dicts from rh3 without team key.**
  This is what caused a wrong Muncy LAD/ATH verdict in the roster audit
  (2026-05-25). Always key on `(norm_name, pro_team)` tuple.
- **Skipping Step 14's three-test convergence.** The old single-MC bounce
  step was noisy. The three-test panel (MC + Bayesian + historical comps)
  is the 2026-05-25 upgrade. All three must be run before a DROP verdict.
  Vlad Jr. at 13th career percentile looked like a drop on career-form alone;
  1,177 real historical comps (63% bounce rate) + Bayesian 79% P(>avg) + IMPROVING
  process said hold. The old skill would have missed that.
- **Ignoring hist_n_comps count.** A 70% bounce rate from 12 comps is
  noise. A 63% bounce rate from 1,177 comps is load-bearing. Always surface
  n_comps alongside the percentage.
- **Confusing Bayesian posterior_mu with the L21d xwOBA.** The posterior
  shrinks the noisy L21d observation toward the career prior by the relative
  precision of each. A 86-PA L21d observation moves the posterior about halfway
  from the prior. Always report posterior_mu, not raw L21d, as "where we think
  the player's talent is."
- **Treating a 21-day window as a verdict driver.** L21d typically has
  60-80 PA — well below xwOBA's 150 PA stabilization. The CI alone
  spans 0.080+ xwOBA, which is the entire range from "declining" to
  "career-best." Always anchor to L150 PA.
- **Reporting raw observed gap as "the gap."** Use Bayesian-shrunk gap
  for the verdict. The Vlad example: raw −0.069 vs shrunk −0.022 —
  completely different verdicts.
- **Anchoring shrinkage to 2025 instead of L150 pre-L21d.** Salvy Perez
  example (2026-05-19): vs 2025 anchor → REAL_DECLINE; vs L150 pre-L21d
  anchor → NEUTRAL (recent stretch is improving from pre-L21d baseline).
  The 2025-anchored verdict was wrong. Always anchor to the most-recent
  stable baseline available.
- **Ignoring xwOBACON vs xwOBA separation.** A slump driven by BABIP
  variance (outcomes-not-falling) looks identical at the xwOBA level
  but has totally different recovery profiles. xwOBACON IS the
  diagnostic.
- **Ignoring process metrics (bat speed, whiff%, Z-contact%).** These
  stabilize faster than xwOBA and reveal skill changes directly.
  Process improving + xwOBA down = lock-in BOUNCE call. Process
  declining + xwOBA down = real decline call.
- **Overconfident verdicts on noisy data.** If the player's career
  baseline is INSIDE the L21d 95% CI, the verdict CANNOT be
  "DECLINING" — it must be "not distinguishable from baseline" or
  the window must be widened.
- **Multiplying rh3 `slump_bounce_pct` by 100.** It's already stored
  0-100. Display as-is.
- **Using `off` as a SQL alias.** DuckDB reserved word. Use `off_n`
  or `offspeed_n`.
- **Skipping injury/news check.** A player in a "slump" might just be
  playing through a recent DTD label — that's a different drop call.
- **Skipping multi-year baseline.** A "declining" call against 2025
  alone misses that 2024 was the actual outlier. Pull 2022-2025
  individually.
- **Using prior recovery as a valid template without checking xwOBACON trajectory.**
  The Turner pattern (2026-05-25): 2023 and 2026 both show rolling xwOBA at 0.285,
  which looks identical. But 2023 trough xwOBACON was 0.396 (contact quality intact),
  while 2026 full-season xwOBACON is 0.330 (genuinely lower platform). Prior recovery
  to 0.363 xwOBA was built on the 0.396 platform — the 2026 recovery ceiling is lower.
  Always run Step 4.5 before citing a prior slump/recovery as evidence that a current
  trough will fully bounce back.

---

## Verdict decision tree (pseudo-code)

The four verdicts (HOLD / SELL-HIGH / DROP / NOT-SLUMPING-STRUCTURAL) emerge from
the three-lens convergence panel + the xwOBACON trajectory gate. Rules fire in
priority order; first match wins.

```
# Required pre-check (Step 4.5)
xwobacon_floor_intact = (current_xwobacon >= 0.95 * career_peak_xwobacon)

1. NOT-SLUMPING-STRUCTURAL
   L21d xwOBA 95% CI INCLUDES career baseline
   AND Bayesian-shrunk gap > −0.040
   # The slump is noise — sample size doesn't support a decline call

2. DROP
   MC P(bounce) < 0.50
   AND Bayesian P(true talent > .320) < 0.40
   AND historical_comp_recovery_rate < 0.40
   AND NOT xwobacon_floor_intact     # all 3 lenses agree, contact quality cracked
   # The Turner-pattern gate prevents a DROP call when xwOBACON
   # platform suggests the bear case is over-reading

3. SELL-HIGH
   Lenses DISAGREE — at least one bullish, at least one bearish
   # The window of opportunity to move the player before the
   # disagreement resolves toward decline

4. HOLD                            # fallback when lenses lean bullish or noise
```

The pre-check on Step 4.5 (xwOBACON year-over-year trajectory) is load-bearing —
it prevents the "prior-slump-recovered" template from being applied when the
underlying contact-quality platform has dropped.

---

## When NOT to use this skill

- Player is hot, not cold → use `/breakout-sustainability` (which now
  also includes CI + shrinkage + xwOBACON per the same upgrade)
- Pitcher (SP/RP) — different metrics needed (xERA, SIERA, pitch shape);
  could be `/pitcher-slump-or-decline` later
- Trade evaluation comparing 2+ players — this skill is single-player
  diagnostic. Use `/hitter-compare` for side-by-side
- Quick fantasy verdict needed (<10s) — this skill's full output runs
  12-15 steps. For a fast take, use the L21d xwOBA + CI from Step 3
  as a quick gut check, then come back for full analysis if the gap
  is borderline

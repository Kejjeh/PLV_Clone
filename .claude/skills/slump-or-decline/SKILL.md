---
name: slump-or-decline
description: Rigorous diagnostic of whether an underperforming hitter is in luck-driven outcome variance (will bounce) or real skill decline (won't). Uses L150 PA as the stable baseline (not noisy L21d), explicit sample-size confidence intervals, Bayesian shrinkage of recent windows toward career mean, xwOBACON separation from xwOBA, process-metric decomposition (bat speed, whiff%, chase%, Z-contact%, K%, BB%), pitch-mix attack changes, splits, calendar history, and bounce Monte Carlo. Outputs HOLD / SELL-HIGH / DROP / NOT-SLUMPING-STRUCTURAL with statistical honesty about confidence. Use whenever the user asks "should I give X more time", "is this slump real", "how close is X to bouncing", or surface-MC says drop on noisy recent data.
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

## Step 14 — Bounce Monte Carlo (with confidence anchored on Steps 2-7)

Run 10,000 bootstrap sims under three scenarios — but pre-tier by
the confidence-adjusted gap from Step 4 (Bayesian shrinkage), not raw L21d:

```python
sims_curr   = ...  # bootstrap from 2026 FPs
sims_bounce = ...  # scale by career_fp_g / current_fp_g
sims_half   = ...  # scale by midpoint
```

Report mean / P>200 / P>250 for each scenario.

Bounce-math: "needs N games at career rate to break 200 RoS."

---

## Step 15 — Verdict synthesis (calibrated, not point-estimate)

Combine Steps 2-13 into a calibrated verdict. **The xwOBA L21d gap
ALONE should never drive the verdict** — it must be cross-checked
with sample-size CI, shrinkage, xwOBACON, and process metrics.

| Verdict | Required evidence |
|---|---|
| **HOLD — bounce expected** | xwOBACON down + EV90/bat-speed holding + process metrics stable-or-improving + L150 PA shrunk gap < 0.030 + slump_bounce_pct > 75% |
| **HOLD with caveat** | Shrunk gap −0.030 to −0.050 + process metrics mixed. Watch for 2 weeks; revisit. |
| **SELL-HIGH** | Shrunk gap < −0.050 + xwOBACON down + EV90/bat-speed declining + market still values player (e.g., PL still ranks top-50). Sell while perception lags. |
| **DROP** | Shrunk gap < −0.060 + age-decline plausible + multi-year trajectory negative + no role/PT protection. |
| **NOT SLUMPING (structural)** | Current rate ≈ career rate AND surface MC depressed by missed time (IL). Action depends on roster slot pressure, not bounce. |

Always show:
- Shrunk gap (not raw)
- Process-metric direction (the actual skill signal)
- xwOBACON gap (the BABIP-variance signal)
- "N games to break 200 RoS at career rate" as the recovery anchor
- Confidence statement ("X PA in L21d — verdict has ±Y uncertainty")

---

## Anti-patterns this skill exists to prevent

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

# Skill: sp-breakout-signal

Evaluate whether a starting pitcher's recent hot stretch represents persistent skill
or outcome noise, using an empirically validated rolling-window good-start methodology
(33,063 SP starts, 2018-2025).

**Trigger phrases:** "is X on a hot streak", "should I trust X's recent starts",
"X has been dealing lately", "hot hand signal for X", streamer evaluation with claimed
recent form, any FA SP where last 3-5 starts are cited as evidence.

---

## Empirical Foundation

### Good-start threshold
```
fp_proxy_per_bf = (K - BB - H - HR) / BF
Good start: fp_proxy_per_bf >= -0.0476   (65th percentile, 2018-2025 calibration)
```

### Persistence probability table
Baseline next-start good-start rate: **36.0%** (corrected — prior 25.4% was calibration artifact from different ER formula; MC re-calibration 2021-2025, 10k bootstrap)

**Rolling window (K good out of last N — order irrelevant):**
```
Window  Rate    Delta vs baseline   CI                  Tier
2/3     43.6%   +7.7pp              [42.3%, 45.0%]      WATCH
3/4     47.7%   +11.7pp             [45.8%, 49.5%]      ACTIONABLE
4/5     51.1%   +15.1pp             [48.7%, 53.6%]      STRONG
3/3     52.7%   +16.8pp             [50.2%, 55.3%]      STRONG
4/4     54.1%   +18.1pp             [50.5%, 57.7%]      LOCK
5/5     57.5%   +21.5pp             [52.6%, 62.4%]      LOCK
2/4     28.9%   +3.5pp              —                   NOISE
3/5     35.5%   +10.1pp             —                   WATCH
0/N     ~12%    -13 to -17pp        —                   NEGATIVE SIGNAL
```

**Order-within-window finding (MC-confirmed):** Position of the bad start is irrelevant. Max spread across bad-GG / G-bad-G / GG-bad positions = 2.1pp, well within CI. Use rolling window count only — do not penalize for where the bad start fell. Tier labels (WATCH / ACTIONABLE / STRONG / LOCK) are unchanged from prior calibration.

**Consecutive streaks (different baseline: 45.8%):**
```
Streak  Continuation  Delta    Note
1       49.2%         +3.4pp   Noise — do not act
2       58.7%         +12.9pp  Watch
3       64.2%         +18.4pp  Minimum actionable
5       74.8%         +29pp    Strong
7       88.3%         +42pp    Near-certain
```

**Key pattern finding:** Within any window, the POSITION of the bad start is irrelevant.
bad-GGG, G-bad-GG, GG-bad-G all produce similar continuation rates (max spread 2.1pp, within CI). Order does not matter.
Use rolling window, not streak counting, to avoid penalizing one-bad-outing profiles.

---

## Decision Rules

```
Signal          Action
1/anything      IGNORE — +3pp lift, noise
2/3 or 2/4      WATCH — don't act, re-check next start
3/4 or 4/5      ADD / ROSTER PROTECT — actionable threshold
4/4 or 5/5      LOCK IN — strong evidence
0/N             NOTE NEGATIVE — flag as cold, avoid streaming
```

**Model-lag trigger (Meyer pattern):**
If `gs_2026 >= 10` AND `rp3_rank` implies hold/drop BUT rolling signal is 3/4 or better:
flag as MODEL-LAG CANDIDATE. The rp3 model is trained on season-level aggregates; it
takes ~10 GS before rolling form updates meaningfully. Do not dismiss the signal — dig deeper
with `/fa-pickup-deep-dive` for full Statcast decomposition.

Note on thresholds: `/fa-monitor` Signal A uses `rp3_rank <= 150` as the FA pool filter.
The model-lag trigger here uses 3/4 rolling signal as the secondary condition — these are
different gates at different decision layers. Both can be true simultaneously for the same
pitcher without contradiction.

---

## Step-by-Step Execution

### Step 0: Pre-condition
Run `/roster-verify` before labeling any pitcher as "your SP." Never infer roster
membership from session context.

### Step 1: Pull recent starts, compute fp_proxy

```python
import duckdb
from pathlib import Path

REPO = Path(r"c:\Users\Joshua\plv_clone")

def get_sp_rolling_signal(pitcher_id: int, n_starts: int = 5) -> dict:
    con = duckdb.connect()
    sql = f"""
    WITH raw AS (
      SELECT pitcher, game_date::DATE AS gd,
        COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) AS bf,
        SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) AS k,
        SUM(CASE WHEN events='walk' THEN 1 ELSE 0 END) AS bb,
        SUM(CASE WHEN events IN ('single','double','triple','home_run') THEN 1 ELSE 0 END) AS h,
        SUM(CASE WHEN events='home_run' THEN 1 ELSE 0 END) AS hr,
        AVG(CASE WHEN pitch_type IN ('FF','FT','SI') THEN release_speed END) AS avg_velo
      FROM read_parquet('{(REPO / "data/research/xfp_cache/statcast_2026.parquet").as_posix()}')
      WHERE pitcher = {pitcher_id}
      GROUP BY pitcher, game_date::DATE
      HAVING COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) >= 10
    )
    SELECT *, ROUND((k-bb-h-hr)*1.0/NULLIF(bf,0), 4) AS fp_proxy_per_bf
    FROM raw ORDER BY gd
    """
    df = con.execute(sql).df()
    con.close()

    GOOD_THRESH = -0.0476
    df['good'] = (df['fp_proxy_per_bf'] >= GOOD_THRESH).astype(int)
    goods = df['good'].tolist()

    signal = {}
    for w in [3, 4, 5]:
        if len(goods) >= w:
            window = goods[-w:]
            k = sum(window)
            signal[f'L{w}_rate'] = f"{k}/{w}"
            signal[f'L{w}_pct'] = k / w
    return {
        'starts': df[['gd','bf','k','bb','h','hr','fp_proxy_per_bf','good']].to_dict('records'),
        'signal': signal
    }
```

Resolve pitcher_id via Baseball Savant search or `plv_clone.utils.name_match`.
Use `statcast_2026.parquet` for current season. BF >= 10 filter excludes mid-inning
relief appearances from SP game logs.

### Step 2: Apply threshold, display per-start table

Print each start with date, BF, K, BB, H, HR, fp_proxy_per_bf, and GOOD/BAD label.
Show the last 5 starts prominently. Compute L3/L4/L5 windows.

### Step 3: Map to persistence table, output signal tier

Look up each window's K/N in the table above. Report:
- Best window signal (highest actionable window)
- Signal tier: NOISE / WATCH / ACTIONABLE / STRONG / LOCK
- Delta vs 36.0% baseline

### Step 4: Cross-reference rp3 model

Pull pitcher's row from `data/outputs/xfp_rp3_projections.csv`.
Report: rp3_rank, xfp_rp3 (projected FP/start), gs_2026.

Check for model-lag condition:
- gs_2026 >= 10 AND signal >= 3/4 AND rp3 rank implies hold/drop → MODEL-LAG CANDIDATE
- If model-lag: recommend `/fa-pickup-deep-dive` for full Statcast decomposition before acting

Note: rp3 is validated for SP ranking. Do NOT use rp3 for RP evaluation (use rprs2).

### Step 5: FA availability check

**ALWAYS** call `league.teams` roster scan. Never infer availability from percent_owned.

```python
from app.espn_connector import get_espn_league
league = get_espn_league()
all_rostered = set()
for team in league.teams:
    for p in team.roster:
        all_rostered.add(p.name.strip().lower())
is_available = player_name.strip().lower() not in all_rostered
```

Percent_owned is unreliable in an 8-team league with small N. A player at 45% owned
can be rostered (Sheehan error, 2026-05-25: inferred FA status from ownership %, was wrong).

### Step 6: Recommendation

Output format:
```
PLAYER: [Name]
Signal: [K/N best window] → [tier] ([delta]pp above baseline)
L3: [k]/3  L4: [k]/4  L5: [k]/5
Model: rp3 rank #[X], xfp=[Y] FP/start, gs_2026=[Z]
Model-lag: YES / NO
FA available: YES / NO (verified via roster scan)

RECOMMENDATION: [IGNORE / WATCH / ADD / LOCK IN]
Rationale: [1-2 sentences]
```

---

## Alternate Signal: stuff_contact_composite (for BABIP-contaminated pitchers)

fp_proxy treats all hits equally — a bloop single and a 105-mph line drive both subtract 1.
For pitchers with soft contact profiles but high BABIP, fp_proxy fires too late or never.

**Canonical case: Kyle Harrison (690986), 2026**
- fp_proxy rolling signal: NEVER fired through 9 GS (too many H, bad BABIP luck)
- Actual contact quality: avg xwOBA on contact = **.279** (MLB average ~.375); avg EV = 81.1 mph
- K% jumped +9pp from 2025, whiff% +6.8pp — genuinely different pitcher
- fp_proxy correlates with BABIP at r = −0.696, with xwOBA-on-contact at r = −0.900

**Trigger condition:** Use `stuff_contact_composite` when EITHER of:
- **BABIP case:** Pitcher has ≥ 3 GS with BABIP > .350 AND avg EV < 87 mph OR avg xwOBA-on-contact < .310
  (Harrison archetype: unlucky hits masking elite soft contact)
- **fp_proxy blind spot case:** Pitcher has ≥ 6 GS, fp_proxy rolling signal has not fired,
  BUT whiff% ≥ 26% in ≥ 4 of those starts AND season avg xwOBA-on-contact < .320
  (Ginn/Griffin archetype: walks tank fp_proxy but contact quality is real)

**Signal definition (updated 2026-05-28 with audit-validated fp_proxy floor):**
```
stuff_contact_composite ("SigStuff") fires when:
  gs >= 6
  AND season_fp_proxy_per_bf >= 0.0
  AND (whiff_pct >= 26% AND xwoba_on_contact <= 0.320)
      OR (csw_pct >= 30% AND xwoba_on_contact <= 0.310)
```

**Why the fp_proxy >= 0 floor was added (2026-05-28):**
Per-start audit across 21,864 SP-start snapshots 2021-2025
(`data/research/sp_signal_audit_2021_2025.parquet`) found that adding an absolute
`fp_proxy >= 0` floor to Signal H lifts the Strong TP rate (RoS fp_proxy ≥ +0.02)
from 28% → 38% pooled — a +10pp gain — with sign-consistency in 5/5 training years.
Canonical false positive correctly disqualified: **Walbert Ureña 2026** (whiff 27.7%,
xwc 0.303, velo 97.7 — looked like SUPER tier; fpp = −0.104 from 16% BB rate). Pitchers
firing whiff+xwc gates while fp_proxy is already deeply negative are the 2023 BUST
archetype (Alex Wood, J.P. France, Patrick Sandoval). Harrison's blind-spot framing
requires `fp_proxy hasn't fired YET` (near 0), not `fp_proxy is actively failing`.

**Year-to-year stability (audit 2026-05-28):**
Pooled 28% Strong TP rate is sign-stable (5/5 years > baseline) but magnitude wobbles:
2021: 24%, 2022: 32%, 2023: 21%, 2024: 25%, 2025: 38% (std 6.1pp). 2023 dip ~75% real
(league mean xwoba-contact rose to 0.324 vs ~0.315 in other years — pitch-clock and
post-spider-tack adjustment), ~25% measurement (gs=1 noise in unrefined audit).
Honest framing: 21-38% range, not 28% locked in. Sub-cells (whiff≥33 AND xwc≤0.290,
SUPER tier with velo gate) have insufficient sample at gs≥6 for reliable per-year
calibration (1-9 fires per year).

**Why the xwOBA-contact gate was added:**
Original definition used `whiff_pct >= 26%` without a contact quality gate. Retroactive
analysis of J.T. Ginn and Foster Griffin (2026-05-25) found clear false positives:
- Griffin May 14: whiff 26.8% BUT xwOBA-contact 0.463 -- getting shelled on contact
- Ginn season avg xwOBA-contact ~0.320 -- persistently elevated despite solid whiff rates
The contact quality gate (≤ 0.320 for whiff branch, ≤ 0.310 for CSW branch) eliminates
these false positives while preserving Harrison (.279 xwOBA-contact) as a true positive.

**Query for per-start stuff_contact metrics:**
```python
sql = f"""
SELECT gd, bf, k, bb, h, hr,
  COUNT(CASE WHEN description IN ('swinging_strike','swinging_strike_bounded','foul_tip')
        THEN 1 END)*100.0 / NULLIF(swings,0) AS whiff_pct,
  COUNT(CASE WHEN description IN ('swinging_strike','swinging_strike_bounded','foul_tip','called_strike')
        THEN 1 END)*100.0 / NULLIF(total_pitches,0) AS csw_pct,
  AVG(CASE WHEN events IS NOT NULL AND events != '' THEN estimated_woba_using_speedangle END)
        AS xwoba_on_contact,
  AVG(CASE WHEN launch_speed IS NOT NULL THEN launch_speed END) AS avg_ev
FROM (... per-start aggregation ...)
"""
```

**Persistence table for stuff_contact_composite:**
Calibrated empirically for Harrison 2026 (9 GS); generalizes to soft-contact
profiles with high BABIP and high-walk fp_proxy blind spots. Use same rolling 3/4 = ACTIONABLE.

Harrison timeline under stuff_contact_composite:
- 3/4 first fired: **2026-05-02** (Apr26, May2, May9 all fire)
- vs fp_proxy: never fired -- 35 days earlier pickup signal

**When to use stuff_contact_composite instead of fp_proxy:**
1. **BABIP case:** Check if BABIP > .350 for 3+ starts AND avg EV < 87 OR avg xwOBA-contact < .310
2. **fp_proxy blind spot:** Check if ≥ 6 GS elapsed with no fp_proxy fire AND whiff% ≥ 26% sustained
3. If either trigger: apply signal (requires whiff AND xwOBA-contact gate — not whiff alone)
4. If BABIP is high AND xwOBA-contact is also bad (> .350): fp_proxy is correct, not a soft-contact case
5. If walk rate is the fp_proxy drag (BB% > 12%): xwOBA-contact gate is especially important --
   high-walk pitchers who also allow hard contact are genuinely bad (Ginn pattern), not blind spots

**Do NOT promote stuff_contact_composite to the rp3 ranker without running `/validate-feature`.**
This is an in-session signal, not a validated model feature. Rule 9 applies: baseline must
include all existing rp3 production features before claiming any lift.

---

## Signal A: Early-Start Breakout Signal (MC-Refined)

For pitchers with a small sample (4-8 GS), the rolling-window table has wide CI. Signal A
provides an alternative early trigger based on process quality rather than outcome count.

**Threshold (MC-refined, validated on 2025 holdout):**
```
Signal A fires when: fpp >= +0.02 AND whiff% >= 26%  (over 4-8 GS window)
```

- Previously: `fpp > 0.00`, no whiff filter — too many false positives in early-season noise
- Validation: ~68% precision on 2025 holdout, +53pp lift vs base rate
- The whiff% gate is load-bearing: fpp alone at ≥ +0.02 overfires on lucky-hit suppression;
  the combination isolates genuine stuff-driven early dominance

**When to use Signal A:** SP with 4-8 GS where rolling-window table has insufficient data
or CI is too wide to be actionable. Signal A supplements (does not replace) the rolling table.

---

## Anti-Patterns

1. **Consecutive streaks only** — penalizes one-bad-outing profiles like Meyer. Rolling window
   is forgiving of noise; use it as primary signal.

2. **Acting on 1/anything** — +3.4pp lift is within noise. Wait for at least 2/3.

3. **Ignoring model-vs-signal tension** — when rp3 says hold/drop but rolling signal says 3/4+,
   this is the most interesting case. Flag it, don't dismiss either side. Model may be lagging
   10-GS update cycle.

4. **Inferring FA availability from percent_owned** — always scan `league.teams` directly.
   Percent_owned in an 8-team league is meaningless (Sheehan, 2026-05-25).

5. **Using this as a standalone drop signal** — 0/N is negative signal, but check xwOBA and
   velo before recommending drop. This skill is optimized for ADD evaluation, not DROP.

6. **Trusting whiff% alone in stuff_contact_composite** — whiff% ≥ 26% without a contact quality
   gate is a false-positive generator. Griffin May 14 (whiff 26.8%, xwOBA-contact 0.463) is the
   canonical false positive: high whiff, getting shelled on contact. Always require
   xwOBA-on-contact ≤ 0.320 in the same start for the composite to fire.

---

## Integration

| Skill | Relationship |
|---|---|
| `/roster-verify` | Pre-condition — run before labeling any pitcher as "yours" |
| `/sp-week-plan` | Consumer — use signal tier to decide which starts to trust this week |
| `/fa-sp-pool` | Upstream — surfaces FA SPs; this skill validates their recent form |
| `/fa-pickup-deep-dive` | Complement — pulls full rp3 row + Statcast; use when model-lag flagged |
| `/sp-archetype` | Complement — outcome-based rolling-window signal lives here; process-based 20-80 ratings + archetype label + historical comps live there. Use both for highest-confidence breakout call. |
| `/breakout-sustainability` | Hitter analog — same rolling-window philosophy for hitters |
| `/pitcher-sustainability` | Deeper velo/K-form decomposition if signal is ambiguous |
| `build_sp_alerts.py` | Generates `data/outputs/sp_alerts.json` for Signal A. **Known bug fixed 2026-05-25:** `str.contains(last)` → `str.contains(re.escape(last))` — names with regex-special characters (e.g., "O'Brien", "Durán)") silently zeroed FA match results before fix. |

**Feeds into /sp-week-plan:** A pitcher with 3/4+ rolling signal earns a "trust" tag for
this week's starts. One with 0/3 gets flagged for bench consideration even if rp3 rank is solid.

---

## Calibration Notes

- Dataset: 33,063 SP starts, 2018-2025 (Statcast game-level aggregates, BF >= 10 filter)
- Threshold: fp_proxy_per_bf = -0.0476 is the 65th percentile of the distribution
- Two baselines: 45.8% (consecutive streak analysis) vs 36.0% (rolling window analysis) —
  different because consecutive streaks condition on the prior start being good; rolling window
  does not. Use the matching baseline for the matching table. Prior rolling-window baseline of
  25.4% was a calibration artifact from a different ER formula; corrected via MC re-calibration
  (2021-2025, 10k bootstrap).
- Validated: 2026-05-25. Refresh calibration if 2026 season data shifts threshold materially.

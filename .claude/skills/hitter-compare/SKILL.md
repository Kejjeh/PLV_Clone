---
name: hitter-compare
description: Multi-hitter head-to-head Statcast + model comparison. Produces side-by-side tables — L21d vs season xwOBA/EV90/K%/bat-speed, rh3 projection, lineup-spot distribution, ESPN counting stats, per-game last 10 — for 2-6 hitters with a comparative verdict. Use whenever the user asks to compare/decide between 2+ specific hitters ("Steer vs Muncy", "deep dive these 4", "which of these is the best add"). This is the explicit gap the /fa-pickup-deep-dive skill flags ("use a different pattern for head-to-head comparison").
---

# hitter-compare

You are doing structured head-to-head deep-dives across 2-6 hitters
in a single output. The skill exists because we did this exact pattern
three times in one session (5 players, then 6 with Sheets, then 4 with
Angel/Montgomery) — every time with the same tables and the same
synthesis steps.

The user's job is to name the hitters. Your job is to pull all four
data streams per hitter and produce ONE comparative writeup that
makes the decision easy.

---

## Inputs

1. **2-6 hitter names** (required). Less than 2 → use
   `/fa-pickup-deep-dive` instead. More than 6 → ask user to narrow,
   or split into two runs.
2. **Decision context** (optional but helpful):
   - "Replace player X" — uses X's baseline as the anchor
   - "Backup / part-time slot" — favors per-game rate + flex
   - "Everyday starter slot" — favors total RoS + lineup spot
   - "Max upside / breakout" — favors leading indicators (EV90, bat
     speed, K% trend), age, lineup-spot upside
3. **Decision weights** (optional): if user says "I just care about
   total xFP RoS" or "ownership isn't a concern" — note explicitly
   in the synthesis section so the verdict reflects their actual ask.

---

## Step 1 — Resolve player IDs

For each name, look up the `batter` MLBAM ID from
`data/outputs/xfp_rh3_projections.csv`. Apply normalization:

```python
import unicodedata
def norm(s):
    return unicodedata.normalize('NFKD', str(s)).encode('ascii','ignore').decode().lower().strip()
```

Disambiguate same-name (Max Muncy LAD vs Max Muncy ATH) by team. If
the player is not in rh3 (recent callup), look up via MLB Stats API
`people/search?names=<name>` and flag "no rh3 row — ESPN stats only."

---

## Step 2 — Pull rh3 projection row per hitter

Capture per hitter:
- `rh3_rank`, `xfp_rh3_per_pa`, `xfp_rh3_per_game`,
  `expected_total_fp_remaining`, `prior_fp_per_pa`, `recency_form_gap`,
  `pa_last21`, `signal`, `replacement_delta`

If a hitter has no rh3 row, mark all model cols as `—`.

---

## Step 3 — Pull Statcast L21d vs season (one query per hitter)

```python
import duckdb
con = duckdb.connect()
sql = """
WITH pa AS (
  SELECT game_date::DATE d, events,
         estimated_woba_using_speedangle xwoba,
         launch_speed ev, bat_speed bs
  FROM read_parquet('data/research/xfp_cache/statcast_2026.parquet')
  WHERE batter=? AND events IS NOT NULL AND events != ''
)
SELECT 'season' span, COUNT(*) pa, ROUND(AVG(xwoba),3) xwoba,
       SUM(CASE WHEN events='home_run' THEN 1 ELSE 0 END) hr,
       ROUND(SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END)*1.0/COUNT(*),3) k_rate,
       ROUND(QUANTILE(ev,0.90),1) ev90,
       ROUND(AVG(bs),1) bat_speed
FROM pa
UNION ALL
SELECT 'last_21d' ..., FROM pa WHERE d >= (CURRENT_DATE - INTERVAL '21' DAY)
"""
```

Compute the trend column (Δ = last_21d − season) for each metric.
Flag with arrows:
- 🔥 = xwOBA up > +0.030 OR K% down > 2pt OR EV90 up > +2.0
- ⚠ = xwOBA down > 0.020 OR K% up > 2pt OR EV90 down > 2.0
- (no marker) = stable

---

## Step 4 — Pull last-10-game per-game breakdown

For each hitter:
```sql
SELECT game_date::DATE d, COUNT(*) FILTER (WHERE events IS NOT NULL AND events != '') pa,
       ROUND(AVG(estimated_woba_using_speedangle) FILTER (WHERE events IS NOT NULL),3) xwoba_pa,
       SUM(CASE WHEN events='home_run' THEN 1 ELSE 0 END) hr,
       SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) k,
       SUM(CASE WHEN events IN ('single','double','triple','home_run') THEN 1 ELSE 0 END) h,
       ROUND(MAX(launch_speed),1) max_ev, ROUND(AVG(bat_speed),1) bs
FROM read_parquet('data/research/xfp_cache/statcast_2026.parquet')
WHERE batter=? GROUP BY 1 ORDER BY d DESC LIMIT 10
```

Surface only last-5 in the writeup; keep last-10 in case the user
zooms in.

---

## Step 5 — Pull lineup-spot distribution (L21d)

```sql
SELECT lineup_spot, COUNT(*) FILTER (WHERE started_game) starts, SUM(pa_in_game) pa
FROM read_parquet('data/research/xfp_cache/hitter_lineup_appearances_2026.parquet')
WHERE batter=? AND game_date >= (CURRENT_DATE - INTERVAL '21' DAY)
GROUP BY lineup_spot ORDER BY starts DESC
```

Surface the modal spot + total starts. Lineup-spot context matters
hugely for fantasy:
- Cleanup (4th) / 3rd: most RBI opportunities, premium
- 1st-2nd: most R, most PA per game (4.5+)
- 5th-6th: middle-tier
- 7th-9th: PA discount, RBI discount
- Scattered (no modal spot): platoon usage, PA volatility

---

## Step 6 — Pull ESPN counting stats + ownership

```python
from app.espn_connector import _get_league
league = _get_league()
fas = league.free_agents(size=2000)
for p in fas:
    if p.name in names_or_match_norm(p.name):
        s = p.stats.get(0,{}).get('breakdown',{})
        # AB, R, HR, RBI, BB, K, SB, AVG
        # plus p.percent_owned, p.projected_total_points, p.injuryStatus
```

If a candidate isn't in the FA pool, fall back to `get_all_teams()` to
fetch ownership info. Flag any candidate currently on another roster.

---

## Step 7 — Compose the comparative writeup

Use this exact structure (proven repeatable from the session that
prompted this skill):

```markdown
## <N>-way comparison: <P1> vs <P2> vs <P3> ...

(Anchor: <decision context if provided, e.g., "replacing Donovan: 1.86 FP/g, 117 RoS">)

### Per-player deep-dives

#### 1. <Player Name> (<TEAM>, <pos>) — ★★★★★ <VERDICT>

**Model (rh3):** rank #<N> | <fpg> FP/g | <ros> RoS | signal <X> | recency_gap <Y>

**Statcast (last 21d vs season):**
| | Season (N PA) | Last 21d (N PA) | Trend |
|---|---|---|---|
| xwOBA | ... | ... | ±value 🔥/⚠ |
| K% | ... | ... | ±pt |
| EV90 | ... | ... | ±value |
| Bat speed | ... | ... | ... |
| HR pace | ... | ... | ... |

**Per-game last 5:** <date>=<xwoba> (HR/K notes), ...

**Lineup:** <modal spot> (<starts> of <total> starts)

**ESPN:** <injury status> | <pct>% owned | proj <X> RoS | <AVG>/<HR>/<RBI>/<SB>

**Read:** <1-2 sentence interpretation — what's the story for this player?>

---

(repeat per player)

---

### Comparative axes

Build a comparison table on whatever 3-5 axes matter for the decision
context. Common axes:

| Axis | P1 | P2 | P3 | ... |
|---|---|---|---|---|
| rh3 RoS | ... | ... | ... | ... |
| rh3 FP/g | ... | ... | ... | ... |
| Recency trend | ... | ... | ... | ... |
| Lineup spot | ... | ... | ... | ... |
| Power (EV90 / bat speed) | ... | ... | ... | ... |
| Breakout indicators | ... | ... | ... | ... |
| Positional flex | ... | ... | ... | ... |

### Verdict

Direct answer to the user's question. If they specified a decision
weighting (e.g., "I just care about RoS + breakout"), apply it
explicitly. If not, give 2 verdicts:
- **Best on pure rate / projection** (favors stable veterans)
- **Best on upside / breakout** (favors leading-indicator winners)

Surface the divergence if our model disagrees with what surface stats
suggest (we got bitten by Muncy LAD's name-brand draw vs Montgomery's
unsexier-but-stronger-bat-speed profile — call this out explicitly).

End with: "Want PL cross-reference? (uses `/pl-cross-reference`)"
```

---

## Step 8 — Cross-reference with /pl-cross-reference if user asks

This skill stays focused on our model + Statcast. If the user wants
the external sanity check, hand off to `/pl-cross-reference`. Don't
auto-fetch PL by default — adds latency and the user usually wants
the data-driven verdict first.

---

## Anti-patterns this skill exists to prevent

- Running 5 separate /fa-pickup-deep-dive's instead of one
  /hitter-compare — duplicate work, inconsistent format across players,
  no comparative table at the end.
- Skipping the lineup-spot pull — it's the single biggest model-
  underweighted factor (Luis García Jr. batting 2nd is genuinely
  more valuable than rh3 captures).
- Showing season-only Statcast without the L21d trend column — the
  trend IS the story for breakout candidates.
- Forgetting to apply user-stated decision weights — if they said
  "RoS only, no ownership concern," the verdict should reflect that
  AND surface the ownership data without filtering on it.
- Using rh3 to compare RPs — wrong model. Pitchers go through
  `/pitcher-compare` (not yet built — candidate for future).
- Auto-fetching Pitcher List in this skill — keep it model-focused;
  delegate PL to /pl-cross-reference on user request.

---

## When NOT to use this skill

- 1 player only → `/fa-pickup-deep-dive`
- 7+ players → ask user to narrow, or run /fa-replacement-pool to
  get a ranked overview first then narrow to top 4-6 for this skill
- Pitchers (SP/RP) → out of scope; build /pitcher-compare separately
- Trade analysis (their hitter for your hitter) → similar pattern but
  needs roster-construction implications; consider /trade-compare
  (not yet built)

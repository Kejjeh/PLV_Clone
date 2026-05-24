---
name: career-form-rank
description: Rank a set of batters by current L150-PA xwOBA AND surface where that current value sits in each player's full career distribution of rolling-150 windows. Outputs a "peak vs slump vs typical" landscape that distinguishes "FA looks better than my hitter" (often a peak-form mirage) from genuine sustainable upgrades. Use whenever the user asks "where does my current performance rank in my career", "is X at peak or slumping", "compare my roster + FAs by L150 process", or wants to gut-check a swap by career-percentile context.
---

# career-form-rank

You are answering: **for a set of batters, where does each one sit in
his OWN career distribution of rolling-150-PA xwOBA windows?**

The skill exists because raw L150 comparisons (mine vs FA) are biased
by selection — FAs are mostly hot-stretch players running at career
peaks, while owned veterans in slumps look weaker than they really
are. Without the career-percentile lens, you'll repeatedly recommend
buying-high + selling-low.

This is the rosier of the two perspectives for slump-or-decline
analysis: it shows you that the slumping player is at the 13th
percentile of their career and the "hot FA" is at the 99th percentile,
both poised to revert toward their respective career means.

---

## Inputs

1. **Universe** — `my-roster`, `my-roster + fa-pool`, or an explicit
   list of player names. Default `my-roster + fa-pool`.
2. **Min career PA** — exclude players with fewer than N total career
   PAs (their percentile is unstable). Default 300.
3. **Min current L150 sample** — only show players with at least N
   recent PAs. Default 100 (allows missed-time players to still show).

---

## Step 1 — Resolve batter IDs (the disambiguation gate)

**CRITICAL:** name → batter-ID can collide. The classic case is
"Max Muncy" — both the LAD veteran (571970) and the ATH rookie
(691777) share the name. Naive `.set_index('player_name')['batter']`
takes whichever appears last in the cache.

Always resolve via the disambiguating helper:

```python
from plv_clone.utils.name_match import resolve_batter_id
batter_id = resolve_batter_id(name, team=roster_team, position=roster_position)
```

That helper consults the multiyr cache and breaks ties using team +
position metadata. See `memory/feedback_player_name_collisions.md`
for the canonical collisions list.

If the resolver returns None or surfaces a collision warning, STOP
and ask the user to disambiguate before proceeding. Silent collisions
are how Max Muncy (LAD vet) became Max Muncy (ATH rookie) in a prior
session and the entire percentile analysis was wrong.

---

## Step 2 — Pull every PA-event across the cached year-range

```python
import duckdb
con = duckdb.connect()
ids_csv = ','.join(str(b) for b in resolved_ids)
union = ' UNION ALL '.join(
    f"SELECT batter, game_date, estimated_woba_using_speedangle AS xwoba "
    f"FROM read_parquet('data/research/xfp_cache/statcast_{y}.parquet') "
    f"WHERE batter IN ({ids_csv}) AND events IS NOT NULL AND events != '' "
    f"AND estimated_woba_using_speedangle IS NOT NULL"
    for y in range(2015, 2027)  # bump end year as new years cache
)
```

Cached years are 2015-2026 currently. If a younger player has no
pre-debut data, that's fine — windows simply start from their first
PA.

---

## Step 3 — Rolling 150-PA xwOBA per batter

```sql
WITH all_events AS ({union}),
ranked AS (
  SELECT batter, game_date, xwoba,
         ROW_NUMBER() OVER (PARTITION BY batter ORDER BY game_date) AS rn,
         COUNT(*) OVER (PARTITION BY batter) AS total_pa
  FROM all_events
),
rolling AS (
  SELECT batter, rn, total_pa,
         AVG(xwoba) OVER (PARTITION BY batter ORDER BY rn
                          ROWS BETWEEN 149 PRECEDING AND CURRENT ROW) AS roll150
  FROM ranked
)
SELECT batter, total_pa,
       AVG(roll150)    FILTER (WHERE rn >= 150) AS career_mean,
       MEDIAN(roll150) FILTER (WHERE rn >= 150) AS career_median,
       MIN(roll150)    FILTER (WHERE rn >= 150) AS career_min,
       MAX(roll150)    FILTER (WHERE rn >= 150) AS career_max,
       MAX(roll150)    FILTER (WHERE rn = total_pa) AS current_l150
FROM rolling
GROUP BY batter, total_pa;
```

The `FILTER (WHERE rn >= 150)` excludes the warmup rows where the
window isn't yet full.

---

## Step 4 — Career percentile of current L150 per batter

Per batter, compute the fraction of historical rolling-150 windows
that fell BELOW the current value:

```sql
-- one query per batter (the `IN (ids_csv)` in Step 3 becomes `= {batter}`)
WITH rolling AS (...)
SELECT
  SUM(CASE WHEN roll150 < {current_l150} THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS percentile
FROM rolling
WHERE rn >= 150;
```

Output is a [0, 1] value: 0.50 = at career median, 0.95 = top 5% of
career, 0.10 = bottom 10%.

---

## Step 5 — Interpret + categorise

| Percentile | Label | Read |
|---|---|---|
| ≥ 95th | **Career peak** | At or near ceiling; reversion likely |
| 80–94th | Peak form | Hot stretch; partial reversion expected |
| 60–79th | Above-median | Healthy run; sustainable |
| 40–59th | Typical | Median performance for this player |
| 20–39th | Below-median | Cooling; some bounce expected |
| < 20th | **Slumping** | Well below career floor; high bounce-back conviction |

Career peakers + career slumpers BOTH have high reversion
expectations. Healthy `typical` players have lowest reversion
expectation.

---

## Step 6 — Output the landscape

Two tables:

### Your hitters
| Player | Total PA | Current L150 | Career median | Career max | Percentile | Read |

Sort by percentile descending (or current_l150 if user prefers).

### Top FAs
| Player | Total PA | Current L150 | Career median | Career max | Percentile |

Filter to current_l150 > your-roster floor AND career sample ≥ 500 PA
(otherwise the percentile is noisy).

### Cross-comparison view (the actionable section)

For each of your bottom-3 hitters by percentile, list 2-3 FAs above
their current L150 + flag which FAs are at peak-of-career vs typical.
The honest swap is "your slumper" → "FA at typical-form, not peak-form."

---

## Step 7 — Mandatory anti-mirage check before any recommendation

Before recommending a swap, verify:

- **Your candidate-to-drop's percentile is < 30**. If they're at 30+,
  they're not actually slumping — the swap target needs a higher bar.
- **FA pickup's percentile is < 90**. If they're at peak-of-career, the
  swap will look smart for 2 weeks then revert. Prefer FAs at 50–80
  percentile (above-median but not peak).

Cross-check with rh3 projection ranks — the model encodes counting
stats + position scarcity that pure xwOBA misses. If xwOBA says
"upgrade" but rh3 disagrees, the rh3 disagreement is the more
trustworthy signal for fantasy use.

---

## Output format

```markdown
## Career-form rank (universe: <description>, as of <date>)

### Your hitters by current L150 xwOBA + career percentile
[table]

### Top FAs (current L150 above your floor)
[table]

### Slumping (yours) vs peak (FAs) — buy-low pile vs mirage pile
- Slumping (percentile < 20): <list>
- Peak (FA, percentile ≥ 90): <list>
- Honest upgrade pool (FA, 50–80 percentile, current > yours): <list>

### Recommendation
Apply Step 7's anti-mirage check; surface 0–2 honest swap candidates.
```

---

## Anti-patterns this skill exists to prevent

- **Recommending an upgrade based on L150 xwOBA alone.** The
  percentile context is non-optional — without it you'll buy peaks
  and sell slumps. This is the canonical mistake the skill exists
  to stop.
- **Skipping disambiguation.** Max Muncy is the well-known case;
  others exist (see `memory/feedback_player_name_collisions.md`).
  Naive name lookup silently uses the wrong player.
- **Using current_l150 with < 100 recent PA.** That's not a stable
  measurement; the "percentile" of a noisy estimate is also noise.
- **Reading raw rh3 rank as the truth without the xwOBA context.**
  Both are signals; xwOBA is process, rh3 is full projection. They
  agree when something is real; disagreements usually mean the rh3
  is lagging an actual change.

---

## Relationship to existing skills

- `/slump-or-decline` — per-player diagnostic (HOLD/SELL/DROP). Use
  AFTER this skill flags a slumper to decide whether the slump is
  luck-driven (will bounce) or skill decline (won't).
- `/breakout-sustainability` — per-player breakout decomp
  (SUSTAINABLE/NARROW/HOT STREAK). Use AFTER this skill flags a
  peak-form FA to decide if the peak is real or already eroding.
- `/hitter-sustainability` — roster/FA sweep with 9-marker decomp
  + rh3 confidence layer. Different decomposition (skill-axis); use
  alongside career-form-rank when you want both views.
- `/hitter-compare` — head-to-head 2-6 player Statcast. Use to
  drill into a specific candidate set this skill identified.

This skill is the FIRST one to run when the user asks about
roster-vs-FA upgrades. The other skills are deep-dives on whichever
candidates this skill flags.

---

## When NOT to use this skill

- Single-player deep dive → `/fa-pickup-deep-dive` or
  `/breakout-sustainability`
- Pitcher analysis → not built for SP/RP (would need xERA-equivalent
  rolling windows; could be `/career-form-rank-pitchers` follow-up)
- Pre-season / no in-season sample → the "current L150" doesn't exist
  yet; defer to the rh3 RoS projection alone

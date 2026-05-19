---
name: fa-sp-pool
description: Identify FA starting pitchers actually available in your ESPN league, ranked by quality with PL Top 100 cross-reference. Pulls all FA SPs (size=2000), verifies each is truly available (not on another team's roster — the Connelly Early gotcha), cross-references with the latest PL Top 100 SP article via WebFetch, compares against the user's current SP staff, and flags meaningful upgrades. Use whenever the user asks "what SPs are available", "is there an SP upgrade", "who should I add for streaming", or wants to validate a pickup target's availability.
---

# fa-sp-pool

You are identifying which starting pitchers are ACTUALLY available
in the user's ESPN league and ranking them by quality with Pitcher
List as the external authority.

The skill exists because of the **Connelly Early bug** (2026-05-18):
PL ranked Early at #42 T6 with a "discount Max Fried" comp, but he
was already rostered on another team in the user's league — not
available as a FA. The PL rank doesn't guarantee availability; ESPN
roster verification is mandatory.

---

## Inputs

1. **Optional**: minimum season FP threshold (default 50 for SPs —
   filters out callups with no track record yet)
2. **Optional**: max ownership % filter (default 100 = no filter; set
   to 50 if user wants "low-owned upside plays")
3. **Optional**: limit to top N by season FP (default top 50 for
   tractable PL cross-reference)

---

## Step 1 — Pull FA SP pool (use single unfiltered call)

```python
from app.espn_connector import _get_league
league = _get_league()
fas = league.free_agents(size=2000)   # single unfiltered call
sps = [p for p in fas if p.position == 'SP']
```

**Do NOT use** `get_free_agents(position='SP', size=300)` — per
`feedback_fa_pool_size_cap.md`, this silently truncates the pool.

Capture for each: `name`, `playerId`, `proTeam`, `total_points` (season FP),
`projected_total_points`, `percent_owned`, `injuryStatus`.

---

## Step 2 — Verify availability against ALL rosters (CRITICAL)

**This is the Connelly Early lesson.** ESPN's `get_free_agents()`
returns the FA pool BUT some "FAs" can be misclassified, and the
PL Top 100 may rank pitchers who are rostered in your specific league.

For the top 50 candidates by season FP (or any specifically-named
candidate from a PL article):

```python
from app.espn_connector import get_all_teams
teams = get_all_teams()

# Sanity check named candidates
for name in candidates_of_interest:
    on_roster = teams[teams['player_name'].str.contains(name, case=False, na=False)]
    if len(on_roster):
        print(f"⚠ ROSTERED: {name} on {on_roster.iloc[0]['team_name']} — NOT FA")
```

Always run this check before recommending a PL-ranked pitcher as
a pickup. If a name comes from a PL article, the assumption
"PL-ranked = available" is FALSE.

---

## Step 3 — Sort FA pool by quality metric

Default sort: `season_fp` descending (top-50 cut). Optional sorts:
- By `projected_total_points` (more forward-looking)
- By rh3/rp3 model rank if available (cross-join with
  `data/outputs/xfp_rp3_projections.csv`)

For low-ownership upside plays, also surface bottom-quartile owned
candidates with high season FP — these are the "league hasn't
noticed yet" picks.

---

## Step 4 — Fetch current PL Top 100 SP article

Use WebSearch to locate the latest:

```python
WebSearch(
  query="Pitcher List Top 100 Starting Pitchers 2026 latest week rankings",
  allowed_domains=["pitcherlist.com"]
)
```

Pick the highest week-number result. URL pattern:
```
https://pitcherlist.com/top-100-starting-pitchers-for-2026-fantasy-baseball-{MM-DD}-week-{N}-rankings/
```

Then WebFetch with a prompt naming the top 30-50 FA SP candidates by
ESPN season FP:

```python
WebFetch(
  url=top100_url,
  prompt="Find rank, tier, weekly change, and any analyst commentary for these
  specific pitchers — they are top FA candidates: <list of names>. For each,
  report: rank, tier, weekly change. **CRITICAL: For any pitcher NOT on the
  list, explicitly say 'NOT ON LIST' — do not silently skip absent pitchers.**"
)
```

The explicit "NOT ON LIST" instruction is required — otherwise
absent players get silently dropped.

---

## Step 5 — Also fetch streamer ranks for the current week (optional)

If the question is about THIS WEEK's pickups (not season-long
rosterables), also fetch the daily streamer-ranks article:

```
https://pitcherlist.com/starting-pitcher-streamer-ranks-fantasy-baseball-{MM-DD}-{MM-DD}-{MM-DD}/
```

This gives Auto-Start / Probably Start / Questionable / Do Not Start
tiers for specific dates — useful for one-week streaming decisions.

---

## Step 6 — Compare to user's current SP staff

Pull the user's current SPs:

```python
from app.espn_connector import get_my_roster_with_injuries
roster = get_my_roster_with_injuries()
my_sps = roster[(roster['position']=='SP') & (~roster['injured'])]
```

For each of the user's SPs, look up their PL rank (from cached
prior fetch or a separate WebFetch). Build a "your staff vs best
FA" comparison:

```markdown
| Your SP | PL # | Best FA at same/better rank? | Net upgrade if swap |
|---|---|---|---|
| Your worst | #49 | Yes — Soroka at #35 | +14 PL ranks |
| ... | ... | ... | ... |
```

A meaningful "upgrade" needs to clear at least 5-10 PL ranks AND
materially improve season-FP trajectory. If best FA is within 5
ranks of user's worst SP, the swap is cosmetic — recommend HOLD.

---

## Step 7 — Categorize each FA SP

Bucket the PL-cross-referenced FA pool:

| Category | Criteria | Action |
|---|---|---|
| **Real upgrade** | PL rank ≥ 10 ranks better than user's worst rostered SP | Strong add candidate |
| **Marginal swap** | Within 5-10 PL ranks of user's worst | Hold unless specific niche |
| **Speculative stash** | Low ownership (<10%), rising trajectory (+UR or +5 weekly) | Stash candidate if roster slot |
| **Streamer only** | Tier 9-11 (#75-100), Probably Start tier in current week | Weekly streaming, not season hold |
| **Avoid** | Falling -10+ weekly OR injury concern | Skip entirely |

---

## Step 8 — Output format

```markdown
## FA SPs in your league — ranked by PL Week N

### Verified availability check
(List any candidates of interest that were NOT actually FA, with the
team that's rostering them. Example: Connelly Early — rostered on
"Frendy's Fantastic Team", NOT available.)

### Ranked FA SPs (sorted by PL rank)
| PL Rank | Pitcher | Tier | Δ | League Owned% | Season FP | Notes |
... full table ...

### Notable FA SPs NOT in PL Top 100
- High-FP earners PL doesn't rank (sometimes signals "production but
  poor underlying" — e.g., Bailey Ober today)
- Names from recent waiver-watch discussion

### Your staff vs FA pool
| Your SP | PL # | vs Best FA |
... 1-line each ...
**Translation: your bottom-N SPs are within striking distance of FA pool;
top-M are clear holds.**

### Recommendations
- **Real upgrade**: <name(s)> — swap for <which SP>
- **Speculative stash**: <name(s)> — if IL slot frees up
- **Streamer this week**: <name(s)> from streamer article
- **Skip**: <name(s)> with declining PL trajectory
```

---

## Anti-patterns this skill exists to prevent

- **Recommending a PL-ranked pitcher as a FA pickup without ESPN
  roster verification.** The Connelly Early gotcha. Always cross-check
  `get_all_teams()` for any specifically-named candidate before
  recommending.
- **Per-position `get_free_agents(position='SP', size=300)`** —
  truncates pool silently. Use single unfiltered size=2000 call.
- **Treating "high season FP" as "PL likes them"**. Many high-FP
  arms (Wacha, Vásquez, McGreevy at the top of the FA-by-FP list)
  are mid-T6/T8/T9 in PL — counting-stats accumulated by volume,
  not skill. The PL cross-reference is the quality filter.
- **Skipping the "user's staff vs FA" comparison.** Without it,
  recommending an FA add is meaningless — you don't know if it's
  an actual upgrade vs a sidegrade.
- **Recommending a streamer add as a season-long hold.** The
  weekly-streamer article ranks for ONE START; long-term
  rosterability is the Top 100 article's domain.
- **Ignoring injury status in the FA pool.** A 90-FP earner on IL15
  with no return date is a worse hold than a 60-FP earner who's
  active. Surface injury status alongside the rank.

---

## When NOT to use this skill

- Hitter FAs — use `/fa-replacement-pool` instead
- Single-pitcher deep dive — use `/fa-pickup-deep-dive` with bucket=SP
- Mid-game streaming decision — use `live_monitor.py` for in-progress
  game context
- RP/closer FA scan — different model (rprs2) and different role
  context (save situations). Build `/fa-rp-pool` separately if needed.
- Long-term rotation outlook (which prospect to stash for September) —
  better handled by `/roster-audit` or a future MiLB-translation skill

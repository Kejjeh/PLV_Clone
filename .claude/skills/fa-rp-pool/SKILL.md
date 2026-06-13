---
name: fa-rp-pool
description: Identify FA relief pitchers actually available in your ESPN league, ranked by leverage_tier + rprs2 with Pitcher List "Closers and Saves" cross-reference. Pulls all FA RPs (size=2000), verifies each is truly available (not on another team's roster — the Connelly Early gotcha), joins archetype + leverage_tier + CLOSER/FIREMAN tags from rp_ratings_master, cross-references with the latest PL Closers and Saves article via WebFetch, compares against the user's current RP staff, and flags meaningful upgrades. Use whenever the user asks "FA RP pool", "FA reliever pool", "find me a closer", "is there a closer available", "should I add a setup man", "RP pickup pool", "FAAB on closers", "FA closer scan", "available closers in my league".
---

# fa-rp-pool

You are identifying which relief pitchers are ACTUALLY available
in the user's ESPN league and ranking them by leverage_tier +
rprs2 quality with Pitcher List "Closers and Saves" as the
external authority.

This is the RP analog to `/fa-sp-pool`. RP closer-watching is one
of the highest-ROI fantasy moves — but recommending a closer based
on PL inclusion alone (without ESPN roster verification) is the
**Connelly Early gotcha** transposed to RPs. Always verify.

The other RP-specific trap: **SV count is not role**. A 5-SV
closer on a bad team beats a 12-SV setup man because the role
(leverage_tier, gmLI) is real and stable. Rank by leverage, not
counting stats.

---

## Inputs

1. **Optional**: minimum season FP threshold (default 20 for RPs —
   filters out callups; RP FP volume is much lower than SP)
2. **Optional**: max ownership % filter (default 100 = no filter;
   set to 30 for "low-owned closer-in-waiting" stash mode)
3. **Optional**: focus mode — `closers` (CLOSER==True only),
   `firemen` (FIREMAN==True only), `all` (default, ranked by tier)

---

## Step 1 — Pull FA RP pool (use single unfiltered call)

```python
from app.espn_connector import _get_league
league = _get_league()
fas = league.free_agents(size=2000)   # single unfiltered call
rps = [p for p in fas if p.position == 'RP']
```

**Do NOT use** `get_free_agents(position='RP', size=300)` — per
`feedback_fa_pool_size_cap.md`, this silently truncates the pool
and drops low-owned high-upside closer-in-waiting names.

Capture for each: `name`, `playerId`, `proTeam`, `total_points`
(season FP), `projected_total_points`, `percent_owned`,
`injuryStatus`.

---

## Step 2 — Verify availability against ALL rosters (CRITICAL)

**Connelly Early lesson, applied to RPs.** PL's "Closers and Saves"
tier list ranks the publicly-available closer landscape; it does
not know your 8-team-league roster state. A "Locked-In" closer in
PL Tier 1 may already be rostered in BrownU.

For any specifically-named candidate from a PL article or
external source:

```python
from app.espn_connector import get_all_teams
teams = get_all_teams()

for name in candidates_of_interest:
    on_roster = teams[teams['player_name'].str.contains(name, case=False, na=False)]
    if len(on_roster):
        print(f"ROSTERED: {name} on {on_roster.iloc[0]['team_name']} — NOT FA")
```

Run this BEFORE recommending any PL-ranked RP as a pickup.

---

## Step 3 — Join archetype + leverage_tier from rp_ratings_master

```python
import pandas as pd
rp_master = pd.read_csv('data/research/rp_ratings_master.csv')
rp_2026 = rp_master[rp_master['year'] == 2026]

fa_rp_df = fa_rp_df.merge(
    rp_2026[['player_name','archetype','leverage_tier','CLOSER',
             'HIGH_LEVERAGE','MULTI_INNING_BULK','FIREMAN','gmli',
             'pli','sv','hld','k_pct','swstr_pct']],
    on='player_name', how='left'
)
```

Also join the validated rprs2 RoS projection:

```python
rprs2 = pd.read_csv('data/outputs/xfp_rprs2_projections.csv')
fa_rp_df = fa_rp_df.merge(rprs2, on='player_name', how='left')
```

If a FA RP has no rp_ratings_master row (insufficient 2026 IP),
keep them but mark archetype as `UNRATED` — they may be recent
callups worth flagging if rprs2 picked them up.

---

## Step 4 — Tier the FA pool by leverage + role

Settled tiering scheme (combines leverage_tier with CLOSER/FIREMAN/
MULTI_INNING_BULK role tags):

| Tier | Criteria | Why |
|---|---|---|
| **Tier 1 — Elite closer** | `leverage_tier == 'ELITE_LEVERAGE'` AND `CLOSER == True` | Locked-in closer-of-record on a contending team; saves + skill |
| **Tier 2 — High-leverage closer** | `leverage_tier == 'HIGH_LEVERAGE'` AND `CLOSER == True` | Closer-of-record, lower team context (fewer save opps, role still real) |
| **Tier 3 — High-leverage setup / fireman** | `leverage_tier == 'HIGH_LEVERAGE'` AND `FIREMAN == True` | Highest-impact innings, inherited-runner work → HLD + W, often next-in-line for SV |
| **Tier 3.5 — High-leverage setup** | `leverage_tier == 'HIGH_LEVERAGE'` AND `CLOSER == False` AND `FIREMAN == False` | Standard setup, real role but no SV path yet |
| **Tier 4 — Mid-leverage with skill** | `leverage_tier == 'MID_LEVERAGE'` AND (rprs2 rank top-80 OR `k_pct >= 28`) | Stash candidates — skill present, role hasn't materialized |
| **Tier 5 — Low/garbage** | `leverage_tier in ('LOW_LEVERAGE','GARBAGE_TIME')` | Skip unless platoon/specialist niche |
| **Bulk** | `MULTI_INNING_BULK == True` | Different value (length, W) — NOT a closer alternative |

Within each tier, sort by `rprs2.per_game` desc (or by `gmli` desc
as a tiebreaker — gmLI is the cleanest role signal we have).

---

## Step 5 — Closer-of-record cross-check

Most adds will target closers. Cross-reference with the user's
existing `data/outputs/save_handcuffs.csv` (and any current
closer-tracker output) to identify FAs who are the **current
closer-of-record** vs the SV-leader-by-accident.

Flag explicitly:
- `CURRENT_CLOSER` — FIREMAN==False, CLOSER==True, gmli >= 1.4
- `RAMPING_BACK` — was the closer pre-IL, recent SV trickling in
  (use `save_handcuffs.csv` context per `feedback_save_handcuffs_needs_closer_context.md`)
- `TEMP_CLOSER` — current SV leader but starter closer is healthy
  and active; volatile role
- `NEXT_IN_LINE` — FIREMAN==True or HIGH_LEVERAGE setup behind a
  closer with declining gmli / age 35+

---

## Step 6 — Fetch current PL "Closers and Saves" article

Use WebSearch to locate the latest:

```python
WebSearch(
  query="Pitcher List Closers and Saves 2026 latest week rankings",
  allowed_domains=["pitcherlist.com"]
)
```

URL pattern (recent years):
```
https://pitcherlist.com/the-closer-report-closers-and-saves-fantasy-baseball-{MM-DD}-week-{N}/
```
or
```
https://pitcherlist.com/closers-and-saves-{MM-DD}-{YYYY}/
```

Pick the highest week-number / most recent date result.

Then WebFetch with the FA RP candidate list:

```python
WebFetch(
  url=closer_report_url,
  prompt="Find PL closer tier (Locked-In / Probably / Sliding /
  Watch List / Speculative-Add), weekly change, and analyst
  commentary for these specific RPs: <list of FA RP names>. For
  each, report: tier, trajectory (rising/falling/stable), team's
  current closer situation. **CRITICAL: For any RP NOT discussed
  in the article, explicitly say 'NOT ON LIST' — do not silently
  skip absent pitchers.**"
)
```

The explicit "NOT ON LIST" instruction is required — same lesson
as fa-sp-pool.

---

## Step 7 — Recency outlier alert (role-change / model-lagging)

Two RP-specific outlier scans after the main tier sort:

### 7a — ROLE_CHANGE flag
For each FA RP, compare last-30-day SV/HLD pattern against full
season:
- If `recent_sv_rate > 0.5 * total_sv_rate` AND `MID/LOW_LEVERAGE`
  full-season → leverage_tier may be lagging the role change
- Likely cause: starter closer IL'd or DFA'd, this RP inherited
  the role late

Surface as: `ROLE_CHANGE: {name} — was {old_tier}, recent gmLI
{recent_gmli:.2f} suggests {new_tier}`

### 7b — MODEL_LAGGING flag
If rprs2 rank is below top-100 BUT recent xwoba_against /
k_pct is elite → model hasn't updated. Same pattern as fa-sp-pool
Step 3 recency-outlier scan. Same 10-appearance threshold caveat
(K% stabilizes faster for RPs — ~50 BF, roughly 10 appearances).

---

## Step 7.5 — rp-decline ROLE-RISK trap filter (do-NOT-add flag)

**Trap avoidance.** The single worst FA-RP add is picking up a closer who is about
to lose the job. The validated `/rp-decline` lens flags exactly that: a reliever
whose **velo is declining YoY AND** whose **skill or role-share is slipping** — the
convergence that precedes the −38% FP-crater when the manager strips the role.

Join the tier and flag any ROLE-RISK FA as **"⚠ velo fading + role slipping → do
NOT add"** BEFORE recommending it. Ready-to-run snippet (degrades to no-op if the
rolling cache is unavailable):

```python
import sys
sys.path.insert(0, 'scripts/xfp')
from rp_decline_model import tier_map          # {norm_name: {tier, role, legs, velo_yoy, ...}}
import unicodedata
def _norm(s):
    return unicodedata.normalize('NFKD', str(s)).encode('ascii','ignore').decode().lower().strip()

rpd = tier_map()   # Tier-B CONTEXT tiers; never moves rprs2
for _, row in fa_rp_df.iterrows():
    d = rpd.get(_norm(row['player_name']))
    if d and d['tier'] == 'ROLE-RISK' and d.get('has_role'):
        vy = f"{d['velo_yoy']:+.1f}" if d.get('velo_yoy') is not None else '--'
        print(f"⚠ DO-NOT-ADD: {row['player_name']} ({d['role']}) — rp-decline ROLE-RISK, "
              f"velo YoY {vy}, {d['legs']}/3 legs. Role likely to crater; chasing these "
              f"saves is the trap. (Tier-B watch flag, weaker/noisier than /sp-decline — "
              f"role loss ~1/3 manager-driven; verify via /triangulate + /rp-decline.)")
    elif d and d['tier'] in ('WATCH', 'NA-VELO'):
        print(f"  note: {row['player_name']} rp-decline={d['tier']} (one leg / no prior velo) "
              f"— monitor, not yet a do-not-add.")
```

**Discipline:** this is a **Tier-B context/watch flag — it NEVER moves rprs2 or the
leverage_tier ranking** (CLAUDE.md #13), and it is **honestly weaker/noisier than
`/sp-decline`** (velo-decline partial-r +0.112 ≈ half the SP whiff/K signal; role
loss is ~1/3 manager-driven, AUC 0.683 — it tilts the odds, it does not predict).
Use it to DOWN-rank or veto a chase, never to override a genuine leverage upgrade.
`NA-VELO` (no 2025 velo — rookies / post-TJ) is **not a clean bill**; treat it as
"primary signal blind," not SECURE. Surface ROLE-RISK FAs in the Step 9 output as
an explicit **"Do NOT add — role fading"** line in the Skip section.

## Step 8 — Compare to user's current RP staff

```python
from app.espn_connector import get_my_roster_with_injuries
roster = get_my_roster_with_injuries()
my_rps = roster[(roster['position']=='RP') & (~roster['injured'])]

my_rps = my_rps.merge(
    rp_2026[['player_name','leverage_tier','CLOSER','FIREMAN','gmli']],
    on='player_name', how='left'
).merge(rprs2[['player_name','rank','per_game']], on='player_name', how='left')
```

For each of the user's RPs, identify the best FA at same/better
leverage_tier:

```markdown
| Your RP | leverage_tier | CLOSER | rprs2/g | Best FA at same/better | Net upgrade |
|---|---|---|---|---|---|
| Your worst | MID_LEVERAGE | False | 2.4 | Soriano (HIGH, CLOSER) | +1 tier + SV path |
```

Cap-aware: user has **4 RP slots**. Don't recommend more swaps
than slot economics allow.

---

## Step 9 — Output format

```markdown
## FA RPs in your league — closer-watch Week N

### Verified availability check
(List any candidates of interest that were NOT actually FA, with
the team rostering them. Example: "Pete Fairbanks — rostered on
Frendy's Fantastic Team, NOT available.")

### Tier 1 — Elite-leverage closers available
| Pitcher | Team | PL Tier | %Own | rprs2 rank | gmLI | leverage_tier | CLOSER | FIREMAN | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
...

### Tier 2 — High-leverage closers / Tier 3 — Setup + firemen
... combined table ...

### Tier 4 — Mid-leverage stash candidates (skill > role)

### Notable RPs NOT in PL Closers and Saves
- High-rprs2 / high-gmLI names PL hasn't surfaced — sometimes
  genuine gems (FIREMAN setup undervalued by save-only frameworks),
  sometimes "stat compilers" on losing teams

### ROLE_CHANGE / MODEL_LAGGING flags
- (from Step 7)

### Your RP staff vs FA pool
| Your RP | leverage_tier | CLOSER | Best FA at same/better | Net upgrade |
... 1-line each ...

### Recommendations
- **Real upgrade**: <name> — swap for <your RP>, +<tier delta>, +SV path
- **Speculative stash**: <name> — next-in-line behind <closer> (age 36, declining gmLI)
- **Skip**: <name> — high SV count but TEMP_CLOSER, role reverts when X returns from IL
- **FIREMAN gem**: <name> — HLD + W value, undervalued by SV-only frameworks
```

---

## Anti-patterns this skill exists to prevent

- **Recommending a closer based on SV count alone.** Use
  `leverage_tier` (gmLI-driven). A 5-SV closer on a losing team
  beats a 12-SV setup man because the role is real and stable.
  See `feedback_save_handcuffs_needs_closer_context.md`.
- **Trusting PL closer-list inclusion without ESPN availability
  check.** PL ranks publicly available closer landscape, doesn't
  know your 8-team-league roster state. The Connelly Early
  pattern, transposed.
- **Ignoring the FIREMAN tag.** A FIREMAN-tagged setup man wins
  more close games for you than a low-leverage nominal closer;
  inherited-runner work shows up as HLD + W in BrownU scoring
  (HLD = +2 in our RP formula).
- **Recommending a MULTI_INNING_BULK RP for save value.** Bulk
  long-relief delivers value via IP + W, not SV. Different role,
  different scoring profile — don't conflate.
- **Per-position `get_free_agents(position='RP', size=300)`.** Same
  silent-truncation gotcha as SPs. Always single unfiltered
  size=2000 call.
- **Skipping the "your staff vs FA pool" comparison.** Without it,
  recommending an FA add is meaningless. The 4-RP-slot cap means
  every add is a swap.
- **Confusing TEMP_CLOSER with CURRENT_CLOSER.** A starter closer
  ramping back from IL is the real role-holder even if their SV
  count is currently low. Cross-check `save_handcuffs.csv`.
- **Adding a "Locked-In" PL closer on a team where your existing
  RP is already that team's closer.** Roster awareness — don't
  swap laterally.

---

## Complementary skills

- **`/rp-archetype <name>`** — after this skill surfaces a candidate,
  run rp-archetype to get the 20-80 ratings + archetype label +
  historical comps (T+1/T+2 outcomes). Especially powerful for
  Tier 4 stash candidates where archetype trajectory (upward shift)
  is the actual buy signal.
- **`/fa-pickup-deep-dive <name>`** — single-RP deep dive after
  pool scan narrows the field.
- **`/pl-cross-reference`** — generic PL cross-reference; this
  skill specializes for the Closers and Saves article.

---

## When NOT to use this skill

- SP scan → `/fa-sp-pool`
- Hitter FA scan → `/fa-replacement-pool`
- Single-RP deep dive → `/fa-pickup-deep-dive`
- Mid-game RP usage decision → `live_monitor.py` for in-progress
  game context
- Closer-of-record tracker across the whole league (not just FA) —
  `data/outputs/save_handcuffs.csv` directly

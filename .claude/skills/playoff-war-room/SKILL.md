---
name: playoff-war-room
description: Quarterly playoff-prep meta-skill (periods 18+) that chains roster-verify → playoff-team-build → sp-stash-finder → sp-rehab-tracker → forced-drop-planner into one report, threading one roster/FA pull and the cap_math playoff-window multiplier through every step. Use when planning the playoff roster, hunting IL stashes that return before playoffs end, or sequencing forced drops around IL cascades. NO roster moves are executed — decision surface only.
---

# playoff-war-room

Runs the full playoff-prep workflow in one pass (SKILL_REGISTRY section 3,
bundle **playoff-war-room**):

1. **roster-verify** — confirm live roster membership before anything else
2. **playoff-team-build** — build the ideal playoff roster across all
   positions using Blended xFP for ranking
3. **sp-stash-finder** — IL'd FA SPs whose ESPN return date arrives before
   playoffs end, ranked by playoff xFP and IL-slot cost
4. **sp-rehab-tracker** — rehab-timeline tracking for my IL'd + stash SPs
5. **forced-drop-planner** — exact date the period SP-start cap (20 in a 2-week playoff round) breaches from the IL
   return cascade + pre-identified cut candidate (cap_math)

For any specific player, run `/triangulate <name>` for the 3-lens verdict.

---

## Shared data (pull ONCE, thread through all steps)

```python
from app.espn_connector import get_my_roster_with_injuries, get_free_agents
import pandas as pd

roster = get_my_roster_with_injuries()          # step 1 truth + IL timeline
fa_all = get_free_agents(size=2000)             # steps 2-3 pool (never <2000)

rh3   = pd.read_csv('data/outputs/xfp_rh3_projections.csv')
rp3   = pd.read_csv('data/outputs/xfp_rp3_projections.csv')
rprs2 = pd.read_csv('data/outputs/xfp_rprs2_projections.csv')

# Cap math + playoff-window multiplier from the OWNER (never hand-typed 1.19/10):
from plv_clone.cap_math import SP_CAP, STARTS_PER_SP_PER_WEEK, projected_starts, gap_to_cap
```

Role via `scripts.xfp.lib.pitcher_role.detect_pitcher_role` (gotcha #8 —
dual-eligible Detmers). IL capacity from `lineup_slot=='IL'`, never
`injured==True` (feedback rule 2). All joins by MLBAM id.

---

## Step 1 — roster-verify

Verify live roster membership. See `/roster-verify`.

## Step 2 — playoff-team-build (condensed)

Run `/playoff-team-build` over `roster` + `fa_all`, ranking by Blended xFP.
Surface the **ROLE+AGE (annual-value z)** keeper lens per hitter (item 2 —
ANNUAL horizon only, Rule 13 context; do NOT let it move a weekly rank).

## Step 3 — sp-stash-finder (condensed)

Run `/sp-stash-finder` over `fa_all`: IL'd FA SPs with ESPN return date before
playoffs end, ranked by playoff xFP and IL-slot cost.

## Step 4 — sp-rehab-tracker (condensed)

Run `/sp-rehab-tracker` for my IL'd SPs + any stash candidates from Step 3 —
rehab-start timeline, ETA confidence.

## Step 5 — forced-drop-planner (condensed)

```python
il_sps = roster[(roster['injured']==True)]  # then filter detect_pitcher_role=='SP'
for _, r in il_sps.sort_values('days_until_return').iterrows():
    projected = projected_starts(n_healthy_sp + 1)
    if projected >= SP_CAP:
        print(f"FORCED DROP DEADLINE: {r['return_date']} — {r['player_name']} activates → over cap")
        break
```

---

## Output format

```markdown
# Playoff War Room — <date>

## Ideal playoff roster (by Blended xFP)
<position-grouped table; ROLE+AGE annual-value z on hitters (context)>

## IL stashes returning before playoffs end
<table: SP · return date · playoff xFP · IL-slot cost · %owned>

## Rehab timeline
<my IL'd + stash SPs — next rehab step, ETA>

## Forced-drop cascade
⚠ Deadline: <date> — <player> activates → over cap
Pre-identified cut: <weakest SP by rp3>

## Recommended sequence (≤5) — DECISION SURFACE ONLY
1. ...
```

---

## Anti-patterns this bundle exists to prevent

- Re-pulling roster / FA pool between steps — pull once, thread through
- Counting IL capacity from `injured==True` instead of `lineup_slot=='IL'` (rule 2)
- Hand-typing 1.19 / 10-cap instead of cap_math owners
- Reporting a forced-drop date without pre-identifying the cut (useless as a warning)
- Folding ROLE+AGE into a weekly rank (ANNUAL horizon only, Rule 13)

## When NOT to use

- Weekly cap upkeep → `/sp-week-plan` or `/monday-morning`
- Single stash question → `/sp-stash-finder` alone

---
name: playoff-team-build
description: Build the user's ideal playoff roster across all positions using baseline xFP for ranking, sp-stash-finder for IL stashes, and opponent_profiler for race-timing. Chains roster-verify → playoff-xFP rank → stash-finder → action list. Use when the user asks "what's my ideal playoff team", "playoff roster plan", "playoff prep", or as a quarterly checkpoint before periods 18+. Built 2026-06-05 after we ran the workflow twice manually in one session.
---

# playoff-team-build

You are designing the user's optimal roster for playoffs (BrownU weeks 21-23,
~mid-Aug through early Sept) by combining all the validated production layers:
roster verification + baseline xFP + sp-stash-finder + opponent profiles.

## Why this skill exists

We built this workflow manually twice in the 2026-06-05 session. It's a
reusable chain. The decisive playoff decisions (Snell IL stash, Morejón hold
upgrade, Trea Turner FADE drop, Salvy → Goodman C upgrade) emerged from the
same multi-step process: verify roster, rank by playoff xFP, scan IL stashes
returning by mid-Aug, propose drop-add pairs that respect IL slot constraints.

## Workflow

### Step 1 — Roster verify (mandatory)

Run `/roster-verify` first to anchor everyone "yours". Pull each rostered
player's current `lineup_slot`, `injured` flag, eligible positions.

### Step 2 — Compute playoff xFP for every roster slot

For each player on the roster, pull their **baseline xFP** from
`scripts/xfp/lib/blend_score.py` (it already incorporates rh3/rp3/rprs2 +
archetype + PL + slope_3yr + HIGH-K + shadow features).

Per-position playoff_xfp = blended_xfp × playoff_PA_or_starts:
- **Hitters:** blended_per_pa × 72 (3 weeks × ~4 PA/G × 6 games/wk)
- **SPs:** blended_per_start × 3.6 (1.19 starts/wk × 3 weeks)
- **RPs:** blended_per_g × ~10 appearances (3 weeks)

**ROLE+AGE keeper lens (context only, item 2, 2026-07-04):** for hitters, also
surface `role_age` from `data/research/hitter_ratings_master.csv` (latest year,
keyed by MLBAM `batter`) as an annual-value tiebreak between two similar
playoff_xfp holds — a younger, higher-lineup-role bat is the better long-term
keep. It is the only hitter construct validated to beat the raw-FP baseline for
forward ANNUAL value (+.164/+.151, 5/5 years). **Rule 13:** ANNUAL horizon only
— it NEVER moves the blended_xfp playoff ranking (which is the weekly-window
number). Render as `annual-value (ROLE+AGE z): +x.xx — keeper lens` beside the
hitter row; do not fold it into playoff_xfp.

```python
import pandas as pd
from plv_clone.paths import ROOT
_m = pd.read_csv(ROOT / 'data' / 'research' / 'hitter_ratings_master.csv')
_m = _m[_m['year'] == _m['year'].max()]
role_age = {int(r['batter']): float(r['role_age'])
            for _, r in _m.iterrows()
            if pd.notna(r.get('batter')) and pd.notna(r.get('role_age'))}
# annual-value tiebreak only — never added to playoff_xfp
```

### Step 3 — Scan FA pool for playoff upgrades at each position

For each lineup slot (C, 1B, 2B, 3B, SS, MI, CI, OF×4, UTIL, P×9), compute
**top-5 verified FAs** by blended playoff_xfp.

A position is "upgradeable" if best FA's playoff_xfp ≥ current player's + 5
(i.e., +5 FP over the playoff window is a meaningful upgrade).

### Step 4 — Run `/sp-stash-finder`

Specifically for SP, the highest-leverage moves are usually IL stashes
returning before playoffs (~before week 18 = ~Aug 1) at high per_start.
Canonical 2026-06-05 finds: Snell (return 7/17, per_start 13.02), Pivetta
(7/10, 11.97), Eury Pérez (7/24, 11.24), Boyd (6/12, 10.06), Henderson
(7/1, shadow PLUS_PROCESS).

### Step 5 — IL slot cascade math

BrownU = 3 IL slots. Map out when current IL'd players activate vs when new
stashes need to occupy a slot. Often the cascade requires staging:
> When player X returns from IL slot → drop X to BE or active P → free slot
> for Y stash → Y returns mid-July → free slot for Z stash → ...

Show the user the staged sequence by week.

### Step 6 — Race-timing via opponent_profiler

For each proposed claim, check which opponents are most likely to compete:
```bash
python scripts/xfp/opponent_profiler.py
```
Specifically watch for PL_PROCESS_FOLLOWER teams (Late Night Bettsing in
BrownU) — they grab archetype_breakout adds on Monday PL refresh. Recommend
acting BEFORE their peak day, NOT on it.

### Step 7 — Output structure

```
## Ideal playoff team

### Hitters (13)
| Slot | Player | Source | Playoff xFP | Action |
| --- | --- | --- | --- | --- |
| C | Hunter Goodman | FA (claim) | 37 | DROP Salvy → ADD |
| 1B | Pete Alonso | own | 41.8 | hold |
| ...

### Pitchers (9 + 4 BE + 3 IL)
| # | Player | Source | per_start (or per_g) | Status |
| 1 | Tyler Glasnow | own (IL→returns) | 13.27 | hold |
| 2 | Blake Snell | FA-IL stash (claim) | 13.02 | CLAIM → IL slot |
| ...

### IL slot cascade
| Week | Slot 1 | Slot 2 | Slot 3 |
| now | Glasnow | Greene | Fried |
| early July | Glasnow | Greene | Snell (stash) |
| ...

### Top 3 actions THIS WEEK
1. Drop Trea Turner → CLAIM Snell (timing: tonight, AVOID Sunday)
2. Drop Palencia → CLAIM Morejón (any time)
3. Drop Salvy → CLAIM Goodman (any time)
```

## When to invoke

- "What's my ideal playoff team"
- "Playoff prep"
- "Plan for playoffs"
- Quarterly checkpoint (start of weeks 18, 20)
- After major IL event in the league
- Before any 2+ drops in a single roster move

## Anti-patterns

- DON'T propose a stash claim without checking the IL slot cascade
- DON'T forget `/roster-verify` first — labeling current roster wrong wastes the analysis
- DON'T use raw rp3/rh3 per_start — use baseline xFP (incorporates archetype + PL + new features per Phase 3 backtest validation)
- DON'T ignore the timing-of-claim guidance from opponent_profiler — for IL stashes specifically, claim BEFORE PL Monday refresh
- DON'T overcount your hitters — confirm the lineup slot count (13 active hitters in BrownU per the league rules memory)

## Related

- `/sp-stash-finder` — IL stash discovery layer
- `/triangulate` — per-player blended_xfp lens (3-source verdict + baseline xFP)
- `/blend-score` (if exists) — direct blended_xfp wrapper
- `/opp-watch` — predicted opponent moves
- `/roster-verify` — mandatory first step
- `/forced-drop-planner` — if SP cap pressure forces moves
- `/monday-morning` — chains roster-verify + roster-audit + sp-week-plan + fa-monitor (different focus, weekly not playoff)

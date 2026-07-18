---
name: pitcher-role
description: Resolve a pitcher's TRUE role (SP vs RP) from eligible_slots + gamesStarted via detect_pitcher_role — never trust the ESPN .position tag. MANDATORY before bucketing any pitcher in a table, counting RP-slot compliance, cap math, or calling someone "your RP/SP". Canonical mislabels — Detmers (ESPN RP, true SP), Jax post-trade (ESPN RP, starting for TB), Dual-elig 2026: any recent RP→SP convert.
---

# pitcher-role — role truth before any pitcher claim

## The rule (CLAUDE.md gotcha #8, promoted to a skill 2026-07-18)

ESPN's `.position` is a preseason-ish label. Before ANY statement that
buckets a pitcher (SP table vs RP table, "your 4 RPs", SP-cap planning,
drop-candidate lists), resolve the true role:

```python
import sys; sys.path.insert(0, 'scripts/xfp')
from lib.pitcher_role import detect_pitcher_role
role = detect_pitcher_role(player_or_row)   # accepts espn row or mlbam_id kwarg
```

Logic: SP-only eligible_slots → SP; RP-only → RP; dual-eligible →
MLB Stats API `gamesStarted / gamesPlayed >= 0.4` → SP.

## When this skill MUST fire

- Building any roster/FA pitcher table (SP and RP sections)
- Counting active-RP-slot compliance (cap is 4 RPs — count TRUE RPs)
- SP-start cap math (a "RP"-tagged starter's starts still bank vs statId-33)
- Saying "your RP X" / "your SP Y" in any user-facing sentence
- Career-split or per-unit stats (role-converts: FP/unit is poisoned by
  relief-era FP over tiny GS — use ERA/K-BB% instead; Jax canonical)

## Failure it prevents (2026-07-18 session)

Jax + Detmers were repeatedly called "RPs" while their STARTS were being
cited in the same analysis; an RP-complement count (`4 RPs left`) silently
included two true SPs. Wired correctly in `build_matchup_dashboard.py`,
`run_roster_audit.py`, `run_second_half_splits.py` — wire it into any new
script that touches pitchers.

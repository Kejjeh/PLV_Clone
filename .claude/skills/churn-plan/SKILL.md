---
name: churn-plan
description: Multi-step roster-churn planner + execution verifier. Use when a move sequence has ORDER and DEADLINES - "drop A for B before B's start, then add C after C pitches", streamer-day churn, add-after-his-start-so-nobody-claims-him timing. Produces an ordered checklist with ET first-pitch deadlines and waiver notes, saves the plan, and later verifies against the LIVE roster that each step actually EXECUTED (the 2026-07-19 missed-Bradish class of failure). Triggers - "plan these moves", "what order do I do these adds/drops", "did my moves go through", "verify my churn", "what's the deadline to add X".
---

# churn-plan

Born from a real failure: on 2026-07-19 the planned Soriano→Bradish→Bennett
churn silently never executed — the 2:10 first pitch passed, the banked
start was lost, and nothing checked. `plan` builds the deadlined checklist;
`verify` reconciles the plan against the live roster.

```bash
python -X utf8 scripts/xfp/run_churn_plan.py plan \
    --move "drop Jose Soriano add Kyle Bradish ; before-start-of Kyle Bradish" \
    --move "drop Kyle Bradish add Jake Bennett ; after-start-of Kyle Bradish"

python -X utf8 scripts/xfp/run_churn_plan.py verify          # latest plan
python -X utf8 scripts/xfp/run_churn_plan.py verify --plan <path>
```

Move syntax: `"[drop NAME] [add NAME] [; before-start-of NAME | ; after-start-of NAME]"`.
Conditions resolve to the named pitcher's NEXT probable start
(pitcher_schedule cache → statsapi for the first-pitch TIME):
`before-` → deadline = first pitch ET; `after-` → not-before = first pitch
+ 4h. Plans save to `data/research/churn_plans/` (gitignored scratch).

## Verify statuses

**EXECUTED ✓** (drop gone AND add on roster) · **PARTIAL ◐** · **PENDING …**
(deadline ahead) · **MISSED ✗** (deadline passed, roster unchanged — the
Bradish case; salvage pointer to upcoming probables +
/streamer-precision-board). Also warns when an intended add got claimed by
another team.

## House rules baked into the engine

- **4-RP floor is enforced**: a plan that drops a true RP without a same-plan
  RP add is REFUSED outright (CLAUDE.md standing rule, 2026-07-18).
- Every drop carries the waiver note (BrownU drops sit ~24-48h, faab=False —
  claim-back window).
- Name resolution is collision-safe (resolve_* owners, then normalized
  FULL-name fallback against the projection CSVs — never last-name
  contains).

## When NOT to use

- Single unconditional move with no deadline → just make it.
- Cap-breach cascades from IL returns → /forced-drop-planner (then feed its
  output here as the move sequence).
- Choosing WHICH player to add/drop → boards first (/sp-board,
  /streamer-precision-board, /hitter-board); this skill sequences and
  verifies, it does not rank.
- Roster-verify still applies before labeling anyone yours — verify pulls
  the live roster itself.

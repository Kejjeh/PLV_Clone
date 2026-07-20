---
name: moves
description: Master meta-skill for the MAKING-AND-TRACKING-MOVES domain — one command that surfaces the full execution state. Chains decision-gates check (pre-registered gate readouts) → churn-plan verify (EXECUTED / PENDING / MISSED reconciliation of in-flight move plans) → cap-check (exact banked-vs-cap verdict) → forced-drop-planner (IL-return cascade + pre-identified cuts). Use when the user asks "where do my moves stand", "run the moves check", "did everything execute", "what's pending", "am I on track with the plan", or before/after any transaction day. Planning a NEW multi-step churn routes to /churn-plan plan; this master reads state, it does not create plans or execute moves.
---

# moves

The execution-domain master: everything about moves you've planned, gates
you've registered, and caps that constrain the next one — in one pass.

1. **decision-gates check** — `python -X utf8 scripts/xfp/run_decision_gates.py check`
   → OPEN / TRIGGERED / CLEARED table with measured values (self-pruning).
2. **churn-plan verify** — `python -X utf8 scripts/xfp/run_churn_plan.py verify`
   → per planned move: EXECUTED / PENDING (deadline ahead) / **MISSED**
   (deadline passed, roster unchanged — the 2026-07-19 Bradish failure this
   step exists to catch), with salvage notes.
3. **cap-check** — `python -X utf8 scripts/xfp/weekly_cap_check.py`
   → banked (ESPN statId-33) + projected vs the live period cap
   (`sp_cap_for_period` — never hardcode 10).
4. **forced-drop-planner** — IL-return cascade: breach dates + pre-identified
   cut candidates (SP-only cuts; the 4-RP floor is absolute).

## Pull-once contract

One live `get_all_teams()` serves steps 2-4 (verify needs the league-wide
scan anyway); one `espn_period_meta` call serves 3-4. Gates (step 1) read
statcast/boxscore stores, no ESPN.

## Output format

```markdown
# Moves — <date, ET>
## Gates            (OPEN n / TRIGGERED n / CLEARED n + table)
## In-flight plans  (per move: status + deadline + salvage)
## Cap              (one-line verdict: UNDER by N / OVER by N → bench X)
## Forced-drop horizon (next breach date → cut candidate → gate that decides)
## Next actions     (≤4, sequenced with deadlines)
```

## Hard rules

0. **Rollover mornings**: `weekly_cap_check.py` follows ESPN's lagging
   `currentMatchupPeriod` — on period day 1 it reports the CLOSED period.
   Resolve the new period explicitly (`weekly_cap_check.py --period N` —
   flag added by the QA fix; the engine also self-warns when its window
   ended before today) and state both ("p15 closed UNDER by N; p16 opens
   0 banked vs cap C"). Pull-once: set `PLV_ESPN_SNAPSHOT=1
   PLV_ESPN_SNAPSHOT_TTL_MIN=45` for the chain (shared disk cache).
1. **Verify-first (Rule 11/gotcha 4):** every EXECUTED/MISSED claim comes
   from the live `get_all_teams()` scan, never from session memory. Waivers
   lag 24-48h — a dropped player still showing rostered is PENDING-WAIVER,
   not MISSED.
2. **4-RP floor** — no output may propose an RP drop for an SP return.
3. TRIGGERED gates print their pre-registered decision verbatim (that is the
   point of pre-registration) — do not re-litigate them in the same pass.

## When NOT to use

- Creating a new sequenced plan → `/churn-plan` (plan subcommand, arg-driven).
- Deciding WHICH player to move → `/player-verdict` first, then plan here.
- The Monday full picture → `/daily-rhythm` (this master runs inside it via
  monday-morning's cap/gates steps; run /moves standalone on transaction days).

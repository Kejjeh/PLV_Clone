---
name: cap-check
description: Weekly SP-start cap planner — projects your rostered starters' remaining starts in the CURRENT scoring period against the period SP-start cap (10 standard / 16 ASG block / 20 two-week playoff), subtracts starts already banked (ESPN statId-33), and when you're over the cap names the exact lowest-value start(s) to bench (they'd score 0 past the cap). Bench value blends rp3 season projection with recent L5 form so a stale/opener-dragged rp3 can't mis-bench a hot arm. Use Monday mornings, or whenever the user asks "am I over the cap", "which start do I bench this week", "how many SP starts do I have left", "cap check", or after any SP add/drop. Distinct from /sp-week-plan (fuller Monday planning with opponent strength + drop candidates) — this is the focused cap-vs-benched-start answer, runnable any day.
---

# cap-check

You are answering one focused question: **given the period SP-start cap and what
I've already banked, how many more starts can I run this period, and which start
do I bench if I'm over?** A wrong bench costs 0 FP on what could have been a
20-FP start, so this recurs and must be exact.

## Run the engine — do not re-derive

The whole computation lives in `scripts/xfp/weekly_cap_check.py`. Run it:

```bash
python scripts/xfp/weekly_cap_check.py              # current period, as of today
python scripts/xfp/weekly_cap_check.py --date 2026-07-20   # plan a future Monday
```

Windows: prefix `PYTHONIOENCODING=utf-8 PYTHONUTF8=1 ` (the report prints `→`/`·`).

It already owns the load-bearing pieces (do not re-implement any of them):

- **Period + cap** via `resolve_current_period_meta(league)` (`scripts/xfp/lib/period_meta`)
  — period-aware; **never hardcode 10** (16 ASG block / 20 two-week playoff).
- **Banked starts** via `espn_period_meta(...)` → statId-33 (`my_banked`). If ESPN
  is unavailable it assumes 0 and says so — flag that the remaining-cap number is
  then an upper bound.
- **Pitcher role** via `detect_pitcher_role` (dual-eligible Detmers-safe) — only
  active (non-IL) SPs are counted; bench = active for scoring.
- **Start projection** = confirmed MLB probables where posted + rotation-cadence
  fallback, **sliding off All-Star-break / off days** so a start is never dropped
  because its slot lands on a no-game date (locked by `tests/test_weekly_cap_check.py`).
- **Bench value** = blend of rp3 per_start + recent L5 start FP, so an
  opener-dragged / role-change rp3 (the canonical Griffin Jax case) can't mis-bench
  a hot arm.

## Reading the output for the user

- Lead with the one-line verdict: **UNDER cap by N** (start everyone, N slots to
  stream) or **OVER cap by N** (bench these N).
- When over, name the exact start(s) to bench — pitcher + date + value — and the
  lowest kept start, so the decision is unambiguous.
- **State the bench-vs-drop distinction every time** (it is the #1 misread): a
  benched start is a THIS-WEEK form call, **not a drop signal**. A cold arm with
  good process (velo / K-BB% up — e.g. a Peralta cold streak on rising velo) stays
  rostered and just sits the one start. Only `/roster-audit`-style process decline
  (velo down, whiff down) argues for a drop.
- `~proj` starts use rotation cadence (not yet announced). Tell the user to re-run
  mid-week as probables post — the projection tightens as the week develops.
- `LOW-CONF` = talent_prior / marcel prior; if the benched/streamed arm is
  LOW-CONF, rank it by Stuff+ (`/sp-stuff-board`) rather than its suppressed rp3.

## When NOT to use this

- Full Monday planning with opponent offense + long-IL drop candidates → `/sp-week-plan`.
- "Which streamer should I add today" → `/stream-the-stack` or `/sp-board`.
- This skill is the fast, any-day **cap-and-bench** answer; keep it to that.

---
name: daily-rhythm
description: Master meta-skill for the DAILY RHYTHM domain — one command that runs the whole open-the-app sequence, day-aware. Chains whats-new (delta since last look) → daily-edge (game-day start/bench + streamer, skipped on off-days) → monday-morning (full weekly chain, Mondays only or --full). Use when the user says "run my daily rhythm", "morning pass", "run everything for today", "full morning briefing", or opens a session wanting the complete picture rather than just the delta. Awareness + decision surface only — NO roster moves are executed.
---

# daily-rhythm

One command for the whole morning. Day-aware — it runs only the legs that
matter today:

| Leg | Runs when | Skill it runs |
|---|---|---|
| 1. Catch-up | always | `/whats-new` (delta since last look; advances last_seen) |
| 2. Game-day edge | MLB games scheduled today | `/daily-edge` (verify → pregame-check → streamer board) |
| 3. Weekly chain | Monday (or `--full` any day) | `/monday-morning` (audit → health → week-plan → cap → FA → conviction; Step 3c gates) |

`--full` forces all three regardless of day. `--lite` = leg 1 only
(identical to `/whats-new`).

## Pull-once contract

The monday-morning / daily-edge pull-once contracts already hold inside each
leg; ACROSS legs, thread these so nothing is fetched twice:

- `roster = get_my_roster_with_injuries()` — pulled in leg 2 (or leg 3 if leg
  2 skipped); leg 1's MINE tags reuse it when available.
- `fa_all = get_free_agents(size=2000)` — pulled at most once (legs 2/3 share).
- Projection CSVs read once; probables via the owner
  (`src/plv_clone/mlb_stats.py` / pitcher_schedule CSV) once.

## Output format

One report, three sections in leg order, each leg's own format preserved
(whats-new's numbered sections; daily-edge's START/BENCH + streamer table;
monday-morning's full template). End with a single consolidated
**"Today's actions"** list (≤5, sequenced) merging leg 2/3 recommendations —
deduplicated, cap-aware, 4-RP-floor respected.

## Hard rules

0. **Rollover mornings** (first day of a new period, before ESPN flips
   `currentMatchupPeriod` — lags until ~mid-morning): cap/matchup engines
   report the CLOSED period. Resolve the new period explicitly
   (`resolve_period_meta(league, period+1)`) and label both windows.
   (Found in live QA 2026-07-20 at 2am: everything said "period 15".)
0b. Pull-once mechanism (QA fix 2026-07-20): set
   `PLV_ESPN_SNAPSHOT=1 PLV_ESPN_SNAPSHOT_TTL_MIN=45` for the whole chain —
   the refresh pipeline's disk-cache layer then serves every engine's
   `free_agents(2000)` + injury sweeps from ONE live pull, across all
   subprocess boundaries, no engine changes. Thread inline frames as before.
1. Leg ordering is load-bearing: whats-new FIRST (it diffs against last_seen
   before anything else mutates caches), then decisions.
2. A leg failing is fail-soft: report the failure line and continue (the
   morning must never die because one store is stale).
3. Rule 12/13 discipline flows through: whats-new stays awareness-only;
   verdicts come only from the decision legs and never flip silently.

## When NOT to use

- Mid-day single question → use the specific skill (`/cap-check`,
  `/triangulate X`).
- You only want the delta → `/whats-new` directly.
- Executing planned moves → `/moves` (the execution-domain master).

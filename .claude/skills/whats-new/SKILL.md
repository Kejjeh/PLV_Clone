---
name: whats-new
description: Delta briefing of everything notable since the user's LAST LOOK — league transactions, my players' game lines (boom/bust flagged), rh3/rp3 rank movers, injury-status changes, PL edition deltas, and FA standouts (volume + FB-velo risers) — as a pure joiner over stores the nightly refresh already accumulates. Use when the user says "what's new", "catch me up", "anything happen since yesterday", "bring in everything through yesterday", "any standouts", "what did I miss", or opens a session asking for the overnight picture. AWARENESS layer only (Rule 13) — never moves a projection or makes a roster call.
---

# whats-new — delta briefing since last look

## What this is

Josh opens most sessions with "bring in everything through yesterday — what's
new, any standouts?". This engine answers that in one pass: a compact
sectioned briefing of everything that changed since `last_seen`, joined from
stores the nightly refresh already writes. **No model math, no
recommendations** — it surfaces; decisions route to `/daily-edge` (game-day),
`/monday-morning` (weekly), and any player worth a look goes to
`/triangulate` / `/fa-pickup-deep-dive`.

## How to run

```bash
# Standard: everything since last_seen, then advance last_seen
python -X utf8 scripts/xfp/run_whats_new.py

# Preview without advancing last_seen
python -X utf8 scripts/xfp/run_whats_new.py --dry-run

# Explicit window (also ignores seen-edition markers)
python -X utf8 scripts/xfp/run_whats_new.py --since 2026-07-13
```

Engine: `scripts/xfp/run_whats_new.py`. State:
`data/research/whats_new_last_seen.json`.

## Section map (each fail-soft: missing store = one WARN line, never a crash)

| # | Section | Store |
|---|---------|-------|
| 1 | League transactions (by team) | `transactions_history.parquet` (persist_transactions) |
| 2 | My game lines, BOOM/BUST flagged | `boxscore_{hitters,pitchers}.parquet` × live `my_roster()` |
| 3 | rh3/rp3 rank movers (2 latest snapshots) | `player_projection_history.parquet` |
| 4 | Injury changes (diff vs stored IL map) | `xfp_cache/injury_status.json` |
| 5 | PL rank deltas (SP100 / H150 / Closers) | `pl_cache/pl_*_<date>.json` editions |
| 6 | FA standouts: volume risers + velo risers | `volume_watch.csv` + `lib/trend_signal` |
| 7 | Josh's inbox (Obsidian vault trial 2026-07-20) | `C:\Users\Joshua\Obsidian\Brain\inbox.md` |

> **No xwOBA section — deliberate (2026-08-10).** A section 8 for rolling
> xwOBA L225 movers was added and removed the same day, alongside its nightly
> refresh step. Two reasons: without a scheduled build there is no reliable
> snapshot pair to diff, and the forward study that afternoon measured xwOBA's
> incremental value beyond the season FP level at **partial r = +0.069 with
> unstable signs**. A daily briefing line for a metric that adds ~nothing over
> the level is noise wearing a lab coat. Ask `/xwoba-l225` when you want the
> board.

## last_seen semantics

- Default run reads `last_seen` from the state file (first run: 7 days back)
  and updates it **at the end, only on success**. `--dry-run` never writes.
- Per-store **seen markers** (latest proj snapshot date, PL edition dates,
  volume_watch mtime) make a same-day second run near-empty instead of
  repeating the same diffs. `--since` bypasses the markers.
- The IL map is snapshotted into the state file, so section 4 shows true
  NEW-IL / CHANGED / OFF-IL diffs from the second run onward (first run:
  current my-roster IL with ESPN return dates).

## Hard rules

1. **Rule 13 tone.** Awareness only — never present a mover/standout as an
   add/drop verdict; route to `/daily-edge` or `/triangulate`.
2. **MINE labels come only from the live `my_roster()` pull** (roster-verify
   rule). If the pull fails, MINE flags are omitted and section 2 skips.
3. **All joins by mlbam id** where the store carries one; name fallback is
   normalized FULL-name only — never last-name contains.
4. Boom/bust flags use the canonical `lib/boom_bust` display cutoffs
   (SP 17/5, H 5/0, RP 6/0) — display lens, imported not re-typed.
5. **Inbox triage (section 7) is Claude's job, not the engine's.** The
   engine only prints the note. When items appear: user vetoes →
   `/decision-gates add` (manual gate), lessons/standing rules → CLAUDE.md
   with a linked enforcement artifact, questions → answer them in the
   briefing. Then mark items ✔ (edit the note) or tell Josh they're
   handled. The vault is capture-only — nothing decision-binding may live
   ONLY there (see the vault's Home.md contract).

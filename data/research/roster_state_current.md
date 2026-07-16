# New York Ligers — current roster-state ledger

Running override for known live roster changes **between** full audits. The web/cloud session
can't query ESPN (no `.env` creds cloned), so this file is the authoritative delta on top of the
last committed audit until a live pull refreshes it. **Trust this over any older audit's roster.**

## Confirmed deltas (most recent first)

### 2026-07-16 (Josh, in-session)
- ❌ **Carlos Rodón — DROPPED.** Not on roster; NOT an IL returner for us. The 7/8 audit's
  "Rodón IL15, returns 7/19" is OBSOLETE — do not repeat it.
- ✅ **Troy Melton (DET) — ADDED** (now MINE). Executed ~Melton-for-Rodón.

## Current SP staff — BEST KNOWN (verify via live pull; see HANDOFF_sp_roster_finalize_2026-07-16.md)
Glasnow (IL ~8/1) · Fried (IL ~7/24) · Imanaga · Hunter Greene · Eury Pérez · José Soriano ·
Emmet Sheehan · Parker Messick · Freddy Peralta · **Troy Melton** — (Rodón removed)

## Open decisions (as of 2026-07-16, not yet executed)
- Drop **Freddy Peralta** (model #1 cut) — recommended.
- Add **Logan Henderson** (FA, streamer #6 vs MIA Fri) — recommended if slot/FAAB free.
- **Soriano**: hold (model COMMAND-WATCH) vs sell (Nick "not that guy anymore") — decide live.

## Refresh protocol
A live session should run `/roster-verify` (or `get_my_roster_with_injuries()` +
`get_all_teams()`), reconcile this ledger, save `live_rosters_<date>.parquet`, then commit.

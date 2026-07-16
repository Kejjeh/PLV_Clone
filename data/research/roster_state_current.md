# New York Ligers — current roster-state ledger

Running override for known live roster changes **between** full audits. **Trust this over any
older audit's roster.** Refreshed from a live ESPN pull — supersedes the cloud session's
best-guess staff list.

## Last live pull: 2026-07-16 (local session, creds present)
Snapshot: `data/research/live_rosters_2026-07-16.parquet` (229 rostered players, 8 teams).

## Confirmed deltas (most recent first)

### 2026-07-16 — live pull corrections (SUPERSEDES the 7/16 cloud handoff)
- ❌ **Carlos Rodón — DROPPED, confirmed.** Live-verified FREE AGENT. Not on our roster, NOT an
  IL returner for us. The 7/8 audit's "Rodón IL15, returns 7/19" is OBSOLETE.
- ❌ **Troy Melton — NOT OURS.** The handoff's "Melton ADDED, Melton-for-Rodón" is **WRONG**.
  Live: Melton is rostered by **2015 Draft First Round**. The add never landed (or he was
  scooped). Do not plan around him or start him Friday.
- ❌ **Emmet Sheehan — NOT OURS.** Listed in the handoff's SP staff; live he is a **FREE AGENT**.
- ✅ **Griffin Jax — ALREADY MINE** (RP, TB). The handoff listed him as an FA add target.

## Current roster — LIVE VERIFIED 2026-07-16
**29/29 full. All 3 IL slots used (Judge IL10, Fried IL15, Glasnow IL60). Any add needs a drop.**

SP staff (8): Glasnow (IL60) · Fried (IL15) · Imanaga · Hunter Greene (BE) · Eury Pérez ·
José Soriano · Parker Messick · Freddy Peralta
RP staff (6): Duran · Tanner Scott (BE) · Latz (BE) · Detmers · Weaver · Jax

## Open decisions (as of 2026-07-16, NOT executed)
- Drop **Freddy Peralta** (model #1 forced-SP cut) — recommended, high confidence.
- Add **Logan Henderson** — live-verified FA, still available. Streamer #6 Fri 7/17 vs MIA.
- **Soriano**: hold (model COMMAND-WATCH = reversible) vs sell (Nick "not that guy anymore").
  Rule 13 — the quote does not override the model. Model-consistent 2nd cut is Messick.
- Other live-verified FA alternatives: Cantillo, Trevor Rogers, Ian Seymour, Sheehan, Rodón.
  (Sean Burke is rostered by Late Night Bettsing — not available.)

## Cap note
Period 15 (ASG block, Jul 6–19) cap = **16**, not 10. IL cascade is **Fried ~7/24 → Glasnow ~8/1**
(Rodón removed) — one fewer returner, so forced-drop pressure eases slightly.

## Refresh protocol
A live session should run `/roster-verify` (or `get_my_roster_with_injuries()` +
`get_all_teams()`), reconcile this ledger, save `live_rosters_<date>.parquet`, then commit.
**Never trust a cloud/web session's ownership tags** — it cannot reach ESPN (gotcha #4/#11).

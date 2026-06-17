# Roster moves — 2026-06-17 (New York Ligers)

Branch: `claude/update-roster-decisions-MdfDN`

## Transactions completed (this session)

| # | Action | Player | Notes |
|---|---|---|---|
| 1 | **Activate** | Pete Fairbanks (RP, TB) | Off real MLB IL. Reclaims his active RP slot. |
| 2 | **Drop** | Lucas Erceg (RP) | Forced cut for Fairbanks. Lowest-RoS RP on staff per 5/10 audit (153.8). Fairbanks 2025 full-season was 291.1 FP, RoS dominant. |
| 3 | **Add** | Logan Henderson (SP, FA) | Replaces Max Fried's active slot after Fried hit the IL. |
| 4 | **IL** | Max Fried (SP, ATL) | Moved to team IL slot. ETA TBD — see handoff. |

Net roster size: unchanged (drop + add).

## Decisions held (no action)

| Slot | Player | Considered | Result | Reason |
|---|---|---|---|---|
| C | Salvador Perez | Iván Herrera (FA) | **Hold Perez** | Herrera +60.5 RoS per 5/10 snapshot, but Perez = veteran volume, durable, prefer not to chase a still-developing bat at C. Revisit at next refresh. |
| C | Salvador Perez | Dillon Dingler (FA) | **Hold Perez** | Dingler 177.9 RoS < Perez 195.8. Hot streak but replacement-level prior + replacement_delta 0.0. Stream-only. |
| 3B | Bo Bichette | Max Muncy LAD (FA) | **Hold Bo** | Wash on RoS (Bo 233.2 vs Muncy 228.5). Better per-PA on Muncy, more PA on Bo. Not enough edge to justify the move. |

## Logan Henderson — 5/10 snapshot read

| Field | Value |
|---|---|
| xFP / start | 10.52 (raw) |
| xFP / start (sched-adj) | 9.91 |
| sigma | 3.55 |
| replacement_delta | **−0.76** (below replacement starter) |
| prior_source | `milb_translation` |
| signal | hold |

Reasonable bridge while Fried is shelved; not a guy to bench an SP1-5 for.
If Fried is 60-day, upgrade SP-end-of-rotation more aggressively
(see `/sp-stash-finder`).

## Open follow-ups — for local Claude session

(All require ESPN cookies + `espn-api`, which the remote container doesn't have.)

1. **Fetch every roster player's ESPN return date / status code** via
   `python -X utf8 scripts/xfp/fetch_roster_return_dates.py --save`.
2. **Fried ETA** specifically — drives whether Henderson is a 2-start bridge
   or a 60-day commitment.
3. **Rodón ETA** — was sitting at bench with `signal=il` per the 5/10 audit;
   confirm current state, plan rotation accordingly.
4. **Confirm Fairbanks status flipped to ACTIVE** (sanity check the move).
5. **Confirm Judge ETA** — last decision file referenced ~7/24.
6. Update this file's "Open follow-ups" → "Resolved" once the local
   session has the data.

See `docs/handoff_local_claude_return_dates_2026-06-17.md` for the runbook.

## Sources

- Snapshot read: `data/research/projection_snapshots/2026-05-10/xfp_rh3_projections.csv`
  and `data/research/projection_snapshots/2026-05-10/xfp_rp3_projections.csv`.
- Prior roster audit: `data/research/ligers_audit_2026-05-10.md` (five weeks stale).
- Prior Fairbanks/hitter swap context (now reversed by real-IL activation):
  `data/research/decisions/fairbanks_to_hitter_2026-06-16.md`.

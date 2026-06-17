# Handoff — local Claude Code (VS Code session)

**Date:** 2026-06-17
**Branch:** `claude/update-roster-decisions-MdfDN`
**Context:** Web-session Claude (this remote container) drafted the moves and
the runner, but cannot hit ESPN — no `espn-api` package and no cookies.
Hand this off to your local VS Code Claude Code session, which has both.

---

## What the remote Claude already did (this branch)

1. **Roster-decision context** confirmed against `data/research/projection_snapshots/2026-05-10/xfp_rh3_projections.csv`:
   - Hold Perez (C) over Herrera — small RoS gap, Josh prefers veteran volume.
   - Drop Erceg (RP, 153.8 RoS) → activate Pete Fairbanks coming off real IL.
   - Add Logan Henderson (SP) → forced by Fried going to IL.
   - Hold Bo Bichette over Muncy — wash on RoS, kept Bo.
2. **Added runner:** `scripts/xfp/fetch_roster_return_dates.py`. Focused IL/ETA
   dump — no model joins, no FA scan. Calls
   `app.espn_connector.get_my_roster_with_injuries`, which already hits
   ESPN's public athlete endpoint inside `get_injury_details` for structured
   `return_date` + `days_until_return`. Existing `run_roster_audit.py` does
   the same thing as part of its larger output; the new runner is the
   stripped-down version Josh asked for.
3. **Logged today's transactional moves** at
   `data/research/decisions/2026-06-17/roster_moves_2026-06-17.md`.

---

## What we need YOU (local Claude) to do

ESPN cookies live on Josh's local machine. Remote container has none.
You do.

### Step 1 — Sanity check the connector

```bash
# from repo root
python -X utf8 -c "from app.espn_connector import _get_league; print(_get_league().teams[0].team_name)"
```

If this prints something like "New York Ligers", you're good. If it raises
`ESPN authentication failed` → cookies expired, refresh `ESPN_S2` /
`ESPN_SWID` in the `.env` per `.env.example`.

### Step 2 — Run the new return-date snapshot

```bash
# Print to stdout
python -X utf8 scripts/xfp/fetch_roster_return_dates.py

# Save markdown + JSON under data/research/decisions/2026-06-17/
python -X utf8 scripts/xfp/fetch_roster_return_dates.py --save
```

Expected output: a markdown table with every injured player on the New York
Ligers roster, their ESPN status code (IL10/IL15/IL60/DTD), injury detail,
and **return date / days until return** straight from ESPN's public athlete
endpoint. JSON file mirrors the same shape.

### Step 3 — Focused checks Josh cares about most

The four roster spots in flux right now:

| Player | Why we care |
|---|---|
| **Max Fried** | Just hit the IL — need an ETA to decide if Logan Henderson is a 2-start bridge or a 60-day commitment. |
| **Carlos Rodón** | Sitting on bench with `signal=il` per the 5/10 audit. Confirm he's still IL'd and pull his return date. |
| **Pete Fairbanks** | Just activated. Confirm his ESPN status is now ACTIVE (sanity check the move went through). |
| **Aaron Judge** | Last decision-record had him with a ~7/24 return; confirm that's still the ETA. |

Shortcut for a focused pull:

```bash
python -X utf8 scripts/xfp/fetch_roster_return_dates.py --names "Max Fried,Carlos Rodon,Pete Fairbanks,Aaron Judge"
```

### Step 4 — Decide and update the decision log

Once you have ETAs, edit
`data/research/decisions/2026-06-17/roster_moves_2026-06-17.md`'s
"Open follow-ups" section with:

- Fried ETA + recommendation: Henderson as a 2-start bridge vs upgrade SP3
  more aggressively (use `/sp-stash-finder` if 60-day).
- Rodón ETA → if he's coming back soon and one of Soriano/Peralta/Valdez
  has a soft week, that's natural rotation.
- Whether any other IL'd roster spots free up in the next 7-14 days
  (changes the urgency of further moves).

### Step 5 — Commit + push (stay on this branch)

```bash
git add scripts/xfp/fetch_roster_return_dates.py \
        docs/handoff_local_claude_return_dates_2026-06-17.md \
        data/research/decisions/2026-06-17/roster_moves_2026-06-17.md \
        data/research/decisions/2026-06-17/roster_return_dates_2026-06-17.*
git commit -m "roster: capture 2026-06-17 IL moves + return-date snapshot"
git push -u origin claude/update-roster-decisions-MdfDN
```

---

## Notes / gotchas

- **`return_date` can be `None`** — ESPN doesn't always have an ETA, especially
  for fresh-day IL placements (Fried might be `None` for a day or two).
  The runner prints `—` and counts it in the missing summary footer.
- **`days_until_return` is computed `return_date - date.today()`** — so a
  player whose ETA is in the past (rehab assignment running long) will show
  a negative number. Not a bug, that's the live truth.
- **`status_code` reflects the ESPN injury *type*** (IL10/IL15/IL60/DTD) and
  is usually what you want over the noisier `injury_status` string.
- **The connector caches the League object** for the process lifetime
  (`@lru_cache`). If you run multiple scripts back-to-back in one Python
  process and ESPN state changes mid-run, restart Python to refresh.
- **CLAUDE.md gotcha #4** still applies: BrownU drops sit on ~24-48h
  waivers (`faab=False`). If Erceg shows up as still on the roster in your
  output, that's the waiver window, not a stale fetch.
- The audit at `data/research/ligers_audit_2026-05-10.md` is **five weeks
  stale** — the projection snapshot is the right source of truth for
  current-state value comparisons until the next refresh runs.

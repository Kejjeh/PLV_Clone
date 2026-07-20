# HANDOFF → local session — finalize SP adds/drops (2026-07-16)

> **STATUS: STEPS 1–2 EXECUTED 2026-07-16 (local session). This file is now PARTLY OBSOLETE.**
> The live pull **contradicted** this handoff's roster premise:
> - **Troy Melton is NOT ours** — rostered by *2015 Draft First Round*. The "Melton ADDED /
>   Melton-for-Rodón" claim below is **false**; the add never landed. Do not start him Friday.
> - **Emmet Sheehan is NOT ours** — live FREE AGENT (this file listed him on our staff).
> - **Griffin Jax is ALREADY ours** — listed below as an FA add target.
> - **Sean Burke is rostered** (Late Night Bettsing) — not an available alternative.
> - Rodón-dropped ✅ confirmed. Henderson still a live FA ✅.
> - **Roster is 29/29 with all 3 IL slots used → any add requires a drop.**
>
> Read `data/research/roster_state_current.md` for the verified state. Steps 3–4 below remain
> open, but re-read them against the corrected staff, not the list in this file.

**Why this exists:** the web/cloud session that did the roundup + sentiment work **cannot reach
ESPN** (no `.env` creds in the cloud clone — `ESPN_LEAGUE_ID`/`ESPN_SWID`/`ESPN_S2` live only in
the gitignored local `.env`; `espn_api`/pandas also not installed there). Run the steps below in a
**local** Claude Code session on this same branch (`claude/sp-roundups-roster-updates-zpc2td`),
which has creds + deps, to reconcile the live roster and finalize the moves.

## Roster deltas confirmed by Josh (2026-07-16) — supersede the 7/8 audit
- ❌ **Carlos Rodón — DROPPED.** He is NOT on the roster and is NOT an IL returner for us.
  (Kill the stale "Rodón returns 7/19" note everywhere — it came from the 7/8 audit.)
- ✅ **Troy Melton (DET) — ADDED.** Now MINE, not FA. Executed as (best understanding)
  **Melton-for-Rodón**.
- Everything else about my SP staff is **unverified** — do a live pull before trusting it.

## STEP 1 — live roster truth (run first)
```
# preferred: the repo skill that does this correctly (my_tag + injuries + slots)
/roster-verify
# or inline:
python - <<'PY'
from app.espn_connector import get_my_roster_with_injuries, get_all_teams
my = get_my_roster_with_injuries()
print(my[['player_name','position','lineup_slot','injured','injury_status']].to_string())
teams = get_all_teams()   # all ~230 rostered players across 8 teams = ownership truth
teams.to_parquet('data/research/live_rosters_2026-07-16.parquet')
print('rostered players:', len(teams))
PY
```
Then **update** `data/research/roster_state_current.md` (created this session) with the true
current SP staff, open bench/IL slots, and the live SP-cap count.

## STEP 2 — verify FA status of the add targets (collision-safe, NOT last-name contains)
Use `resolve_pitcher_id(name, team=..., role='SP')` or a normalized FULL-name match against the
live `get_all_teams()` set (CLAUDE.md gotcha #10 — Will/Austin Warren). Confirm each is truly
unrostered in BrownU (national % ≠ 8-team availability, and hot arms get scooped):
- **Logan Henderson (MIL)** — the intended 2nd add
- Alternatives if Henderson is gone / you want a bigger swing: **Sean Burke (CHW)**,
  **Joey Cantillo (CLE)**, **Trevor Rogers (MIA)**, **Griffin Jax (TBR)**, **Ian Seymour (TBR)**

## STEP 3 — finalize the remaining move(s)
Original plan was *drop Peralta + Soriano, add Henderson + Melton*. **Melton is done** (via the
Rodón slot). Still open — decide with live slots + the model:
- **Drop Freddy Peralta** — clean. Model's #1 forced-SP cut (STUFF🔻, ~50% bust), Nick "dropping
  is absolutely an option," not on the streamer board. High confidence.
- **Add Logan Henderson** — strong: **SP-streamer #6** for Fri 7/17 vs MIA ("super safe"),
  roundup 🟡→ (soft MIA/COL/LAA runway). Do this if a slot/FAAB is free after the Peralta drop.
- **Soriano — THE decision to make deliberately.** Divergence: our validated tag is
  **COMMAND-WATCH = HOLD/reversible** (stuff intact, walks up), but Nick 7/12 = "he's not that guy
  anymore" and he's off the streamer board. Rule 13 → the quote does NOT override the model. If you
  need a 2nd drop, the model-consistent alternative is **Messick** (also fading — velo→94, fatigue
  into break, but likely rebounds with rest). My lean: Soriano is a defensible sell-low ONLY because
  the incoming arms out-trend him; if respecting the model, hold Soriano and cut Messick instead.

## STEP 4 (optional) — regenerate the integrated board with live tags
The sentiment I distilled is cached. The engine reads it from
`data/research/triangulate_universe/nick_sentiment_2026-07-15.json` (that dir is gitignored, so
the committed copy is `data/research/pl_cache/nick_sentiment_2026-07-15.json` — copy it into place):
```
mkdir -p data/research/triangulate_universe
cp data/research/pl_cache/nick_sentiment_2026-07-15.json data/research/triangulate_universe/
/sp-board --scope roster          # or: python scripts/xfp/build_sp_pl_board.py --date 2026-07-15
```
This will now tag MINE/FA correctly off the live pull and fold in the roundup sentiment.

## Cap note (Rodón gone changes this)
IL cascade is now **Fried 7/24 → Glasnow 8/1** (Rodón removed). One fewer SP returning, so the
forced-drop pressure eases slightly, but Melton/Henderson still need to out-pitch whoever they'd
displace when Fried/Glasnow activate.

## Artifacts already on this branch (built this session, ready to use)
- `data/research/pl_cache/sp_sentiment_board_2026-07-15.md` — my SPs + 43 FA Top-100 SPs, Nick
  sentiment 🟢/🟡/🔴 (6/30–7/12 roundups). **Fix the ownership tags** with the live pull — it used
  the 7/8 snapshot (had Rodón as mine, Melton as FA).
- `data/research/pl_cache/sp_roundup_timeline_2026-07-15.md` — full chronological blurbs.
- `data/research/pl_cache/nick_sentiment_2026-07-15.json` — engine-format sentiment.
- `data/research/pl_cache/roundup_fetch_manifest_2026-07-15.md` — provenance.
- **Fresh SP-Streamer ranks (7/16–7/18)** pulled this session, Fri 7/17 slate:
  #6 Henderson vs MIA (40%), #7 **Melton @ LAA** (59%, "looking HOT" — start him Fri), #8 Jax @BOS,
  #9 Bradish @HOU, #10 Bennett vs TBR. Today 7/16 = one game, "start neither."

## What to do when done
Update `roster_state_current.md`, commit, push. If you want, re-open the web session afterward — it
can read the committed live-roster parquet + updated ledger even though it can't query ESPN itself.

# SP Roundup fetch manifest — teed up 2026-07-15

> **✅ RESOLVED 2026-07-15.** The env egress policy was updated to allow `pitcherlist.com`,
> so the fetch was executed the same day. WebFetch stays bot-blocked (403), but `curl` gets
> 200. Window 6/30–7/12 fetched + distilled. Deliverables:
> `sp_roundup_timeline_2026-07-15.md` + `nick_sentiment_2026-07-15.json` (this dir).
> The notes below are kept for provenance.


**Why this file exists:** a session on 2026-07-15 was asked to *fetch all missing
Pitcher List "SP Roundup" recaps, distill Nick/Crumpler sentiment per pitcher, and
store the timeline* — but the Claude-Code-on-the-web environment's egress policy
**denied `pitcherlist.com:443`** (gateway 403 to CONNECT, confirmed in the agent
proxy's `recentRelayFailures`). Per proxy rules the block was reported, not routed
around. The fix chosen: **relaunch with a network policy that allows pitcherlist.com.**
This manifest lets the relaunched (unblocked) session execute immediately.

## Unblock step (do this before relaunching)
Edit the environment → **Network access** selector → **Custom** → add:
```
pitcherlist.com
*.pitcherlist.com
```
Check *"Also include default list of common package managers"* so package installs
still work. (Or pick **Full** to allow any domain.) Docs:
https://code.claude.com/docs/en/claude-code-on-the-web#network-access

## Cache state at time of writing
**Zero** roundups cached — no `*roundup*` or `pl_timeline*` files exist anywhere in
`data/`. So "all we don't have" = the entire recent window below.

## Missing roundup articles (confirmed to exist via WebSearch)
Daily cadence; author is Nick Pollack unless noted. URL pattern
`https://pitcherlist.com/sp-roundup-M-D-26/` where the date = the **completed-start**
day (`[R]` per the sp-pl-board dating rule).

| Date covered | URL slug | Author |
|---|---|---|
| 7/12 | `sp-roundup-7-12-26/` | Jake Crumpler |
| 7/11 | `sp-roundup-7-11-26/` | Jake Crumpler |
| 7/10 | `sp-roundup-7-10-26/` | Nick Pollack |
| 7/8  | `sp-roundup-7-8-26/`  | Nick Pollack |
| 7/7  | `sp-roundup-7-7-26/`  | Nick Pollack |
| 7/2  | `sp-roundup-7-2-26/`  | Nick Pollack |
| 6/30 | `sp-roundup-6-30-26/` | Nick Pollack |
| 6/23 | `sp-roundup-6-23-26/` | Nick Pollack |

Also fetch any daily editions the search didn't surface but that the cadence implies:
**7/13, 7/14** (and 7/9, 7/6, 7/5, 7/4, 7/3, 7/1, 6/29…6/24 as needed for the window).
Confirm the live list against the category page once unblocked:
`https://pitcherlist.com/category/fantasy/starting-pitchers/sp-roundup/`

## SP name-sets to track (roster swap — side by side, per user request 2026-07-15)
- **Current staff:** Freddy Peralta, José Soriano, Emmet Sheehan, Parker Messick,
  Hunter Greene, Carlos Rodón, Max Fried, Tyler Glasnow
- **Pending swap:** DROP Peralta + Soriano → ADD **Henderson + Melton**
  - ⚠ **Resolve Henderson & Melton to MLBAM IDs first** via
    `resolve_pitcher_id(name, team=..., role='SP')` — do NOT last-name `contains`
    (Will/Austin Warren rule, CLAUDE.md gotcha #10). Confirm which "Henderson" /
    "Melton" once the live roster/FA pull is available.
- Fried, Glasnow, Greene, Rodón are IL'd — they may have no recent roundup entry.

## Execution steps once unblocked (from sp-pl-board SKILL §4–5)
1. Fan out a Workflow over the roundup URLs (one agent per article, schema-structured):
   extract per-pitcher blurb + the `[R]` completed-start date + Nick/Crumpler tone.
2. Compile per pitcher, oldest→newest, into
   `data/research/triangulate_universe/pl_timeline_<date>.md`
   (note: `triangulate_universe/` is `.gitignore`d for CodeGraph hygiene — if the
   timeline should be committed, write it somewhere tracked, e.g. here in `pl_cache/`).
3. Distill one latest-weighted sentiment string per pitcher (🟢/🟡/🔴 + trend arrow
   + ≤12-word why, quoting signature phrases) →
   `data/research/pl_cache/nick_sentiment_<date>.json`.
4. Prioritize the tracked SP name-sets above; then roster + FA Top-100 arms.
5. Feed into `python scripts/xfp/build_sp_pl_board.py --date <date>` for the board.

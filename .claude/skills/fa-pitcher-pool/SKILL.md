---
name: fa-pitcher-pool
description: Unified FA pitcher availability pool with `--role {sp|rp}`. `--role sp` = FA starting pitchers actually available (size=2000, Connelly-Early availability-verified), ranked by quality with PL Top 100 cross-reference vs your current SP staff — the old /fa-sp-pool. `--role rp` = FA relievers ranked by leverage_tier + rprs2 with archetype + CLOSER/FIREMAN tags and PL "Closers and Saves" cross-reference — the old /fa-rp-pool. Use for "what SPs/RPs are available", "find me a closer", "is there an SP/RP upgrade", "streaming pickup pool", "available closers in my league", "FA reliever pool". Merges /fa-sp-pool + /fa-rp-pool (item 15, 2026-07-04).
maturity: unified-fa-pitcher-pool
---

# fa-pitcher-pool — unified FA pitcher pool (`--role {sp|rp}`)

Merges the two near-identical FA pitcher pools into one entry point (item 15).
Both roles share the SAME engine pattern and MUST use the size=2000 owner:

- **Pool fetch (both):** `league_state.available_fa(...)` / `league.free_agents(size=2000)`
  — NEVER per-position `size<2000` (drops low-owned high-FP FAs — the Sheehan bug,
  don't-do #6).
- **Availability (both):** verify each candidate is truly a FA via `get_all_teams()`
  — the Connelly-Early gotcha (PL rank / percent_owned are NOT roster truth, gotcha #7).
- **Role detection:** `detect_pitcher_role(row)` (gotcha #8, dual-eligible Detmers) —
  never bucket by ESPN `.position` alone.

## `--role sp` — FA starting pitchers

Run the full `/fa-sp-pool` protocol: pull all FA SPs (size=2000), verify availability,
join rp3 + `data_quality_tag` (rank marcel_il arms by Stuff+ `proj_ros_fp`, not rp3 —
gotcha #1), cross-reference the latest **PL Top 100 SP** article (+ current-week streamer
ranks) via WebFetch, compare against the user's current SP staff, and flag meaningful
upgrades. Mandatory `get_all_teams()` verification (Connelly-Early bug).

## `--role rp` — FA relievers

Run the full `/fa-rp-pool` protocol: pull all FA RPs (size=2000), verify availability,
join archetype + **leverage_tier + CLOSER/FIREMAN** tags from `rp_ratings_master` and
**rprs2** (NOT rp3 — the canonical RP-ranking mistake), cross-reference the latest **PL
"Closers and Saves"** article via WebFetch, compare against the user's current RP staff.
Sort by leverage_tier then rprs2. (RP CONTROL rating is forward ~zero — do not gate on it.)

---

**Deprecation note:** `/fa-sp-pool` and `/fa-rp-pool` remain as aliases pointing here;
new invocations should use `/fa-pitcher-pool --role {sp|rp}`. Distinct from `/sp-board`
(joined decision board) and `/stream-the-stack` (boom-tier streamers) — this is the flat
FA-only availability list.

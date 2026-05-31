---
name: sp-rehab-tracker
description: Track MiLB rehab outings of IL'd SPs via Baseball Savant minors filter. Per-pitcher FB velo/K%/BB%/SwStr% deltas vs pre-injury MLB baseline → AHEAD/ON-TRACK/BEHIND/WORKLOAD-ONLY/NO-DATA verdict. Surfaces buy-low windows before MLB-only model catches up. Script `scripts/xfp/build_sp_rehab_tracker.py`. Note "NO DATA" is the most common verdict (no rehab outings yet); re-run weekly during active rehabs. Built to catch the Jared Jones / post-TJ pattern.
---

# sp-rehab-tracker

You are tracking the **MiLB rehab outings** of every injured SP across the
user's 8-team league so the buy-low / trade-target windows aren't missed.

The skill exists because we discovered (2026-05-28) that `/league-breakout-sustainability`
and `/fa-monitor` both tagged Jared Jones DECLINE when he was actually coming
back from TJ with better velo than pre-injury (98.4 mph vs 97.3 in 2024,
31.7% MiLB K%, .450 SL whiff/swing). The model layer has zero 2026 MLB data
for IL'd pitchers, so the signal is invisible until they return — by which
time the buy-low window has closed.

Rehab data is publicly available via the **Baseball Savant minors filter**
(`baseballsavant.mlb.com/statcast_search/csv?...&minors=true`). This skill
operationalizes the pull.

---

## Inputs (all optional)

1. **Scope** — default `league`. Options: `league` (all rostered IL'd SPs),
   `mine` (my roster only), `single:<pitcher_name>` (one-off lookup).
2. **Window** — default 2026 season start → today. Override with date range
   for retrospective audits.

---

## Step 1 — Identify IL'd SPs

Pull all 8 rosters via `get_all_teams()`, filter to positions `SP` or `RP`
where `injured == True` OR `injury_status` is non-ACTIVE. Carry through:
- player_id (ESPN), player_name, position, team_name (owner), injury_status

Optional v2: scan FA pool for SPs whose model projection is suppressed
because of long IL absences (no 2026 MLB games, gs_to == 0).

**Critical:** Surface the IL list to the user before pulling rehab data —
the user should confirm the scope is right (some "injured" flags are DTD,
not real rehab assignments). 5+ pitchers in scope is a flag that the
filter is too loose.

---

## Step 2 — Resolve MLBAM batter IDs

ESPN player_id ≠ MLBAM. Resolve via:
1. `data/research/xfp_cache/sp_multiyr_2015_2025.csv` — accent-folded
   fuzzy match on `player_name` (which is "Last, First" format).
2. Fallback: `pybaseball.playerid_lookup(last, first)`. Slower (downloads
   the lookup table on first call) but exhaustive.

Cache resolved IDs in `data/research/xfp_cache/sp_mlbam_resolved.csv`
keyed by ESPN player_id so future runs are O(1).

---

## Step 3 — Pull MiLB rehab data

For each MLBAM ID, query the Savant minors-filter CSV endpoint:

```python
url = (
    "https://baseballsavant.mlb.com/statcast_search/csv?"
    "all=true"
    "&hfPT=&hfAB=&hfBBT=&hfPR=&hfZ=&stadium=&hfBBL=&hfNewZones="
    "&hfGT=R%7CPO%7CS%7C&hfC=&hfSea=2026%7C&hfSit="
    "&player_type=pitcher&hfOuts=&opponent=&pitcher_throws="
    "&batter_stands=&hfSA=&game_date_gt=2026-03-01&game_date_lt=<TODAY>"
    "&hfInfield=&team=&position=&hfOutfield=&hfRO=&home_road=&hfFlag="
    "&hfPull=&metric_1=&hfInn=&min_pitches=0&min_results=0&group_by=name"
    "&sort_col=pitches&player_event_sort=api_p_release_speed&sort_order=desc"
    f"&min_pas=0&pitchers_lookup%5B%5D={mlbam}&minors=true&type=details"
)
```

Same Statcast schema as MLB parquets (118 columns). Empty CSV = no rehab
outings logged yet (still working back, bullpen-only, or fully active MLB).

---

## Step 4 — Pull prior MLB baseline

For each pitcher, pull their most-recent FULL-season MLB row from
`sp_multiyr_2015_2025.csv`. Key columns:
- `avg_velo` (overall) — useful but FB-specific is better when available
- `k_pct`, `bb_pct`, `swstr_pct`, `c_plus_swstr` (CSW%)
- `xwoba_contact`, `fp_per_start_actual`
- `gs` (volume context — small `gs` priors are noisier)

If the SP has 2024 AND 2025 baselines, use the more recent. If only 2024
(TJ-style year-out cases like Jones), use 2024.

---

## Step 5 — Compute deltas + verdict

For each pitcher with ≥ 30 MiLB pitches:

```python
# Velo delta — FB-specific, not overall
fb_velo_milb = milb[milb['pitch_type'].isin(['FF','FT','SI'])]['release_speed'].mean()
prior_fb_velo = prior_mlb['avg_velo']  # sp_multiyr is overall but tracks closely
velo_delta = fb_velo_milb - prior_fb_velo  # >0 = velo back / up

# K% and BB% deltas
milb_k_pct = (milb_pa['events'] == 'strikeout').sum() / total_pa
milb_bb_pct = (milb_pa['events'] == 'walk').sum() / total_pa
k_delta  = milb_k_pct  - prior['k_pct']
bb_delta = milb_bb_pct - prior['bb_pct']

# SwStr% (skill confirmation)
milb_swstr = (milb['description'].isin(['swinging_strike','foul_tip'])).sum() / len(milb)
swstr_delta = milb_swstr - prior['swstr_pct']
```

**Verdict tiers:**

- **AHEAD** — `velo_delta >= +1.0` mph AND `swstr_delta >= +0.01` AND
  `k_delta >= 0`. Stuff is BETTER than pre-injury. Buy-low candidate.
- **ON TRACK** — `velo_delta within ±1.0` AND `swstr_delta within ±0.015`.
  Same player; command may lag (BB% typically up 1-3 pts in rehab —
  normal, fades with workload). Hold if rostered.
- **BEHIND** — `velo_delta < -1.0` OR `swstr_delta < -0.02`. Stuff is
  measurably worse. Don't expect immediate MLB impact.
- **WORKLOAD-ONLY** — fewer than 80 pitches across all outings. Too early
  to read stuff; only the workload-build curve is informative. Report
  pitch counts and last-game date; defer verdict.
- **NO DATA** — 0 MiLB pitches. Either bullpen-only or hasn't started
  rehab assignment yet. Flag the days-since-IL for context.

### Verdict decision tree (pseudo-code; Pattern H)

```
# Rules fire in priority order; first match wins.

1. NO DATA
   n_pitches == 0
   # Surface days_since_IL for context

2. WORKLOAD-ONLY
   n_pitches < 80
   # Surface pitch-count progression; defer stuff verdict

3. AHEAD
   velo_delta >= +1.0
   AND swstr_delta >= +0.01
   AND k_delta >= 0
   # Buy-low — process exceeds pre-injury baseline

4. BEHIND
   velo_delta < -1.0
   OR swstr_delta < -0.02
   # Don't expect immediate MLB impact

5. ON TRACK   # fallback when no other rule fires
   # |velo_delta| <= 1.0 AND |swstr_delta| <= 0.015
   # Same pitcher; BB% lag is normal post-injury
```

**Setback overlay:** if workload curve shows >12d gap or pitch-count drop
outing-over-outing, append `(POSSIBLE SETBACK)` to the verdict and confirm
via news. This applies regardless of the underlying tier.

---

## Step 6 — Workload build curve

For each pitcher with ≥ 2 outings, report the pitch-count progression:

```
4/29: 41 pitches
5/06: 54 pitches
5/23: 76 pitches
```

Flag any gap > 12 days between outings as **POSSIBLE SETBACK** — confirm
via MLB news if surfacing in an action recommendation.

Flag any drop in pitch count outing-over-outing as a regression in workload
build (also potentially setback-related).

---

## Step 7 — Output ranked table

Columns:

| MLBAM | Player | Source | Injury | Outings | Last MiLB | FB velo (Δ vs prior) | K% (Δ) | BB% (Δ) | SwStr% (Δ) | Workload | Verdict |

Sorted by verdict tier (AHEAD → ON TRACK → BEHIND → WORKLOAD-ONLY → NO DATA),
then within tier by FB velo delta descending.

---

## Step 8 — Action callouts

Below the table:

1. **Buy-low watch (AHEAD-tier on other rosters)** — these are the
   trade targets. Owner may be selling at depressed price because the
   model layer hasn't caught up.
2. **My-roster IL'd SPs** — verdict per pitcher + estimated MLB return
   if known. Useful for the next IL slot decision.
3. **Faders (BEHIND-tier on my roster)** — drop watch on activation.
4. **Awaiting data (NO DATA / WORKLOAD-ONLY)** — re-check in N days
   based on injury timeline.

---

## Anti-patterns this skill exists to prevent

- **Ranking IL'd SPs in /league-breakout-sustainability or /fa-monitor**
  — those skills see zero MLB data and tag them DECLINE or skip them.
  This skill is the dedicated layer that surfaces MiLB rehab signal.
- **Assuming the MLB model rp3 has any read on an IL'd SP** — the rp3
  projection collapses to prior + IL feature for IL'd pitchers; the
  baseline is the SP's pre-injury form. Use this skill for the "current
  state" read, NOT rp3.
- **Quoting raw MiLB stats without the level context** — AAA hitters
  whiff at 30%+ on stuff that MLB hitters lay off. The verdict logic
  uses *deltas vs the SP's own prior MLB baseline*, not absolute MiLB
  numbers. A 36% K% in AAA is the SAME pitcher who ran 26% in MLB; the
  delta is what matters.
- **Trusting <30 pitches** — set the WORKLOAD-ONLY tier above 30. Below
  that, the velo number alone is meaningful but K%/BB%/SwStr% are noise.
- **Forgetting the workload-build curve** — a 41 → 54 → 76 pitch
  progression is healthy. A 76 → 54 → 41 sequence is a regression and
  matters even if the stuff numbers look good.

---

## When NOT to use this skill

- Healthy MLB-active SPs → `/sp-breakout-signal` or `/pitcher-sustainability`
- IL but no MiLB outings yet → workload-build context only, no stuff read possible
- Position players → not applicable; hitters' rehab readings are different

---

## Output expectations

After a successful run:
1. A CSV `data/research/sp_rehab_tracker_<date>.csv` with every IL'd SP scored
2. A markdown ranked table in the assistant's response
3. Action callouts: buy-low / my-roster / faders / awaiting-data
4. Updated cache file: `sp_mlbam_resolved.csv` so future runs are faster
5. Production script: `scripts/xfp/build_sp_rehab_tracker.py`

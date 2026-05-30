---
name: triangulate
description: Unified three-lens player analysis combining Pitcher List ranks, our projection model (rh3/rp3/rprs2), and the archetype model (20-80 ratings, cell, trajectory, T+1 projection). Works for hitters, SPs, and RPs with a single script that auto-detects the position bucket. Produces a structured profile card per player plus a comparison table for multi-player queries, with a verdict synthesized from the agreement/disagreement pattern across the three sources. Use whenever the user wants the "complete picture" on one or more players, asks "triangulate X", "full profile on X", "compare X Y Z across all lenses", or wants to weigh a PL ranking against our model and the process-based archetype simultaneously.
---

# triangulate — three-lens unified player analysis

Every player gets analyzed through **three independent lenses** that have different anchors and different failure modes. The diagnostic value is in *agreement vs disagreement* — when all three converge, conviction; when they diverge, the disagreement itself is the insight.

| Lens | What it measures | Anchor | Failure mode |
|---|---|---|---|
| **PL rank** | Recent outcomes + expert eye | 12-team rate-stat mindset | Reacts to HR/K clusters before process catches up |
| **Model (rh3/rp3/rprs2)** | Validated career prior + recent regression-shrunk | Career baseline | Lags real breakouts; stuck on prior when archetype changes |
| **Archetype** | 20-80 ratings on process pillars + trajectory + T+1 | Process | Needs enough IP/PA; rookies have no profile |

---

## Trigger phrases

"triangulate X", "full profile on X", "complete picture on X", "all three lenses on X", "PL + model + archetype on X", "compare X Y Z across sources", "triangulate these N players", "what does everything say about X".

---

## Inputs

- **1 to ~6 player names** (positional args)
- **Optional `--bucket H|SP|RP`** to force a position bucket; otherwise auto-detected from name lookup against rh3 → rp3 → rprs2 → archetype panels (in that order)

---

## Workflow

### Step 1 — Verify PL cache freshness

Cache files live in `data/research/pl_cache/`:

| File | Source article | Refresh cadence |
|---|---|---|
| `pl_hitters_top150.json` | PL Top 150 Hitters weekly | Weekly (Sundays) |
| `pl_sps_top100.json` | PL Top 100 Starting Pitchers weekly | Weekly (Mondays) |
| `pl_sp_streamers_latest.json` | PL SP Streamer Ranks daily | Daily |
| `pl_closers.json` | PL Closers and Saves weekly | Weekly |

**Each cache file has `fetched` (date) + `source_url` + `ranks` (dict of name → rank).** Before any RP triangulation make sure `pl_closers.json` has been seeded (it ships empty by default — the article URL pattern is `https://pitcherlist.com/closers-and-saves-...`).

**Refresh procedure** (do this only when stale or user explicitly asks):
1. `WebSearch` with `allowed_domains=['pitcherlist.com']` for the latest version of the article.
2. `WebFetch` the URL and ask for the FULL ranked list as `rank. Player Name` (one per line).
3. Parse into the JSON schema and overwrite the cache file with new `fetched` date.

For the streamer cache, key the `ranks` dict to `{rank, tier, opp}` objects (see the existing `pl_sp_streamers_latest.json` for the schema).

A stale cache (>7d for weekly, >2d for streamer) should be refreshed before quoting PL ranks as current.

### Step 2 — Run the triangulate engine

**Single-player or small comparison (≤10 names) — interactive mode:**
```bash
python scripts/xfp/run_triangulate.py "Player One" "Player Two" "Player Three"
# Force bucket if name resolution might collide:
python scripts/xfp/run_triangulate.py --bucket SP "Christian Scott"
```

**Batch mode (10+ names, league-wide scans) — CSV output:**
```bash
python scripts/xfp/run_triangulate.py \
    --names-file data/research/triangulate_universe/master_universe.csv \
    --csv-out    data/research/triangulate_universe/triangulate_results.csv
```
The `--names-file` flag reads a CSV with a `player_name` column (extra columns are passed through, allowing pre-tagged inputs). `--csv-out` suppresses per-player markdown cards and writes one row per player with all lens fields flattened — ideal input for downstream synthesis or parallel-agent processing.

The script:
- Resolves each name against the projection files (rh3 → rp3 → rprs2 → archetype panels)
- Reads cached PL rank
- Reads the model row (rank, fp/game or fp/start or xfp_ros, signal, replacement_delta, recency_form_gap)
- Reads the archetype row (OVERALL, archetype label, cell, sub-ratings, traj_flag, 3yr slope, career percentile, T+1 fp, career arc, velo + tier)
- Synthesizes a verdict from the agreement pattern
- Prints a markdown card per player and a side-by-side comparison table (interactive mode) OR writes a CSV (batch mode)

### Step 3 — Read the output and offer follow-ups

The verdict tag is one of:
- **STRONG HOLD/BUY** — all three converge in the top tier
- **BUY — archetype breakout** — archetype TRENDING_UP with model lag >50 ranks
- **BUY — model anchored on prior** — model rank far below PL+archetype
- **FADE — PL chasing outcomes** — PL rank far above model+archetype OVERALL
- **CAUTION** — at least one process red flag (TRENDING_DOWN with high PL, GENERIC_HR_PRONE archetype, FINESSE velo declining, CAREER_LOW)
- **MIXED — see profile** — signals don't converge; surface the table and let the user decide

When the verdict is BUY or FADE, suggest the natural follow-up skill:
- BUY breakout → `/pitcher-sustainability` or `/hitter-sustainability` for process confirmation
- FADE → `/slump-or-decline` (hitters) or `/sp-breakout-signal` (SPs) for outcome-vs-process triangulation at the rate level

---

## Output anatomy

Each player card has four blocks:

1. **Header line** with verdict and rationale
2. **3-source table** (PL | Model | Archetype) with rank, headline metric, and detail
3. **Career arc** showing last 4 archetype + OVERALL transitions
4. **T+1 projection + velo + role tags** (RPs get CLOSER/FIREMAN/HIGH_LEVERAGE + leverage_tier)

For multi-player queries, the script appends a **comparison table** sorted in input order with the seven key columns (Player, Bucket, PL, Model, Archetype OVERALL, T+1, Traj, Verdict).

---

## Mega-research mode (league-wide multi-category scan)

When the user asks for a sweeping report — e.g. "triangulate my whole team and every dropped/added player and the FA pool" — use the **universe builder + parallel agents** pattern:

```bash
# 1. Build the player universe (writes 4 category CSVs + a deduped master)
python scripts/xfp/build_triangulate_universe.py
# → data/research/triangulate_universe/{my_roster, my_drops, opp_churn, fa_above_50fp, master_universe}.csv

# 2. Batch-triangulate the whole master in one pass
python scripts/xfp/run_triangulate.py \
    --names-file data/research/triangulate_universe/master_universe.csv \
    --csv-out    data/research/triangulate_universe/triangulate_results.csv

# 3. Split results by category for parallel agent processing
# (one-liner that joins the category column back from master_universe and writes per-category CSVs)
```

Then **dispatch one general-purpose agent per category in parallel**. Each agent:
- Reads its `results_<CATEGORY>.csv` slice
- Identifies actionable players (BUYs, FADEs, CAUTIONs on the roster)
- Returns a ~400-800 word focused markdown section

Synthesize the four agent reports into a single top-down research document with an executive summary, top-5 league-wide actions, and a cross-category arbitrage section (e.g. use opp FADE-tagged players as bait for opp BUY-tagged trade targets).

The universe builder handles the four standard categories (`ROSTER`, `MY_DROP`, `OPP_CHURN`, `FA_TOP`). FA filtering uses model-derived season FP (`prior_fp_per_pa × pa_to` for H, `fp_per_start_to × gs_to` for SP, `fp_actual_2026` for RP) because ESPN's `applied_total` field returns 0 reliably across the API.

---

## When to use a different skill instead

- Only one source matters: use that single skill directly (`/pl-cross-reference` for PL-only, `/hitter-archetype` for archetype-only, etc.)
- Need a *deep dive* with recent Statcast (last 3-5 outings, bat tracking, pitch shape): use `/fa-pickup-deep-dive` (hitter or pitcher) — that pulls per-game shapes the triangulate engine deliberately omits to keep the table tight
- Comparing 2+ players on Statcast process specifically (not full triangulation): use `/hitter-compare`
- Scanning the league for archetype shifts: use `/sp-archetype scan` or `/hitter-archetype scan`
- League-wide multi-team audit: use `/league-deep-audit`

---

## Anti-patterns

- **Don't quote PL ranks from a stale cache** as "current" — check the `fetched` date and refresh if >7d old (or >2d for streamer ranks)
- **Don't treat rookies' missing archetype rows as "no signal"** — explicitly note "insufficient innings/PA for archetype profile" and rely on the Statcast process layer instead
- **Don't downgrade a player based on `signal=il` alone** — the rp3 signal column has known defects in the current production file (2026-05-28 build flags 213/264 SPs as "il"); use rank + replacement_delta + recency_form_gap to read the model instead
- **Don't synthesize a verdict from just rank gaps** — always weigh the archetype trajectory and T+1 because those are the leading indicators when PL and model disagree
- **Don't add a fourth data source ad-hoc** — if you find yourself reaching for Statcast L21d or bat tracking, hand off to `/fa-pickup-deep-dive` rather than expanding the triangulate output
- **Don't print per-player markdown cards for >10 players** — switch to batch mode (`--csv-out`) and dispatch parallel agents per category for synthesis. A 400-player run in interactive mode would dump 30k+ lines and blow context
- **Don't trust ESPN's `applied_total`/`points` fields for FP filters** — they return 0 across the public API for most players. Use the model-derived season-to-date FP (see "Mega-research mode" above) for "FAs above N FP" type filters
- **Don't assume `recent_activity` returns Player objects** — in this `espn-api` version the action tuple is `(Team, action_str, player_name_str)`, NOT `(Team, action, Player)`. Position has to be looked up post-hoc from the projection files
- **Don't treat MIXED as "no signal"** — when archetype OVERALL ≥ 60 and trajectory is TRENDING_UP but model lags <50 ranks (so the BUY-archetype-breakout rule doesn't fire), the synthesize() output is MIXED but the player is usually a quiet BUY (canonical: Casey Schmitt 2026, arche 66 CONTACT_POWER TRENDING_UP, verdict MIXED because model lag was only 26 ranks). Read the archetype row before defaulting to "wait and see"

---

## Files

- Engine: [scripts/xfp/run_triangulate.py](../../scripts/xfp/run_triangulate.py) — supports both interactive (`names ...`) and batch (`--names-file`, `--csv-out`) modes
- Universe builder: [scripts/xfp/build_triangulate_universe.py](../../scripts/xfp/build_triangulate_universe.py) — for the mega-research workflow; pulls roster + transactions + FAs and writes the 4 category CSVs
- PL cache dir: [data/research/pl_cache/](../../data/research/pl_cache/)
- Mega-research output dir: [data/research/triangulate_universe/](../../data/research/triangulate_universe/) (created on first universe build)
- Model files: `data/outputs/xfp_rh3_projections.csv`, `xfp_rp3_projections.csv`, `xfp_rprs2_projections.csv`
- Archetype panels: `data/research/hitter_archetype_career_panel.parquet`, `sp_archetype_career_panel.parquet`, `rp_archetype_career_panel.parquet`

---

## Implementation notes (debt + future polish)

- **Name resolution for RPs uses `name_api` from rprs2** (not `player_name`, which is "Last, First" in rp3 only). The `resolve_player()` function dispatches on bucket — keep that in mind if you ever swap projection schemas.
- **Synthesize edge case** — the BUY-archetype-breakout rule requires both PL ≤ some rank AND model lag > 50. Players with strong archetype but only modest model lag fall through to MIXED. If the user complains "you flagged X as MIXED but the archetype is clearly bullish," that's why — the rule could be liberalized to fire on `arche_overall ≥ 60 AND traj == TRENDING_UP AND (PL int or model good)`.
- **Hitter T+1 is fp/PA, not fp/game** — the output label reflects this (look for `fp/PA` vs `fp/start` vs `fp/g`). PA-to-game conversion is ~4.2× for full-time hitters.

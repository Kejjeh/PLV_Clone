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

## Common one-liners

```bash
# Single deep-dive
python scripts/xfp/run_triangulate.py "Player Name"

# Compare 2-6 players
python scripts/xfp/run_triangulate.py "Player A" "Player B" "Player C"

# Show only the comparison table, skip per-player cards
python scripts/xfp/run_triangulate.py "A" "B" "C" --summary-only

# Filter to verdicts containing any of these tokens (case-insensitive substring)
python scripts/xfp/run_triangulate.py "A" "B" "C" --filter "BUY,FADE,CAUTION"

# Batch mode — CSV in, CSV out (preserves category column if present)
python scripts/xfp/run_triangulate.py --names-file roster.csv --csv-out results.csv

# League-wide research (roster + drops + opp churn + FAs above 50 FP)
python scripts/xfp/build_triangulate_universe.py
python scripts/xfp/run_triangulate.py \
    --names-file data/research/triangulate_universe/master_universe.csv \
    --csv-out data/research/triangulate_universe/triangulate_results.csv
```

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

A stale cache (>7d for weekly, >2d for streamer) should be refreshed before quoting PL ranks as current. **The engine prints a `⚠ <filename> is Nd stale` warning to stderr at startup** whenever any consulted cache is past TTL — heed it. The streamer cache is now date-keyed (`pl_sp_streamers_YYYY-MM-DD.json`) so old streamer ranks won't be silently quoted as today's; the engine picks the newest-dated file.

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
- **BUY — process upgrade** — archetype TRENDING_UP top-tier with moderate model/PL lag
- **BUY — under-the-radar** — PL hasn't ranked but model + archetype both endorse
- **BUY — outcomes only (no archetype)** — rookie with strong model, no process layer yet
- ~~**HOLD — speed profile**~~ — REMOVED 2026-05-30 (calibration rejected; underperformed comparison set by 2.4pp on T+1 bounce)
- **HOLD — post-TJ ramp candidate** *(4th-lens override, unvalidated n=13)* — SP CAREER_LOW + WILD_MID/FILLER but SwingMiss far outpaces WalkAvoid (walk-driven, stuff intact)
- **HOLD — process intact** *(4th-lens override, calibrated)* — SP trajectory bearish but model still ranks **top-25** (tightened from top-50 after calibration)
- **FADE — PL chasing outcomes** — PL rank far above model+archetype OVERALL
- **CAUTION** — at least one process red flag (TRENDING_DOWN with high PL, GENERIC_HR_PRONE archetype, FINESSE velo declining, CAREER_LOW)
- **MIXED — see profile** — signals don't converge; surface the table and let the user decide

When the verdict is BUY or FADE, suggest the natural follow-up skill:
- BUY breakout → `/pitcher-sustainability` or `/hitter-sustainability` for process confirmation
- FADE → `/slump-or-decline` (hitters) or `/sp-breakout-signal` (SPs) for outcome-vs-process triangulation at the rate level

---

## Verdict decision tree (synthesize order)

```
# Rules fire in this priority order; first match wins.

1. BUY — archetype breakout
   archetype.have AND archetype.traj == TRENDING_UP
   AND PL_rank is int AND model_rank is int AND (model_rank - PL_rank) > 50

2. STRONG HOLD/BUY
   PL_rank is int AND model_rank is int AND archetype.have
   AND PL_rank <= 30 AND model_rank <= 50 AND archetype.overall >= 55

3. FADE — PL chasing outcomes
   PL_rank and model_rank are both int AND (model_rank - PL_rank) > 60
   AND archetype.have AND archetype.overall < 50 AND traj != TRENDING_UP

4. BUY — model anchored on prior
   (model_rank - PL_rank) < -50
   AND archetype.have AND archetype.overall >= 55

5. BUY — process upgrade  (NEW)
   archetype.have AND archetype.overall >= 60 AND traj == TRENDING_UP
   AND (PL_rank int and <= 80  OR  model_rank int and <= 80)

6. BUY — under-the-radar  (NEW)
   PL_rank in ('UR','—') AND model_rank int and <= 80
   AND archetype.have AND archetype.overall >= 60

7. BUY — outcomes only (no archetype)  (NEW)
   NOT archetype.have AND model_rank int and <= 60 AND model.rep_delta > 0

8. CAUTION  (note-accumulator — any one fires)
   - archetype.traj == TRENDING_DOWN AND PL_rank <= 50
   - archetype label in {GENERIC_HR_PRONE, FILLER, WILD_MID, PIT_CHF, BUST, BACKUP_BAT}
   - archetype.career_pct == 0 (CAREER_LOW)
   - velo_tier == FINESSE AND TRENDING_DOWN

9. MIXED — see profile  (fallback when no rule fires)

# ---- 4th-lens overrides ----
# Applied AFTER the rules above. May upgrade a FADE/CAUTION verdict to a HOLD tier
# when a fourth signal contradicts the bearish call. Each override sets `override_tag`
# in the CSV output so downstream filtering can find them.

A. HOLD — speed profile     (SPEED_PROFILE override; REMOVED 2026-05-30)
   # REJECTED by empirical calibration: at SB/SPEED ≥ 60 the override
   # UNDERPERFORMED the comparison set by 2.4pp on T+1 bounce rate (N=321).
   # The Trea Turner case-study intuition did not generalize. Removed from
   # production; do not re-enable without re-running calibrate_overrides.py.
   # See docs/triangulate_calibration_2026.md.

B. HOLD — post-TJ ramp candidate     (POST_TJ_RAMP override; UNVALIDATED, n=13)
   bucket == 'SP'
   AND archetype.career_pct == 0  AND archetype.career_year >= 3
   AND archetype.label in {WILD_MID, FILLER, GENERIC_HR_PRONE}
   AND (sub_ratings.SWING_MISS - sub_ratings.WALK_AVOID) >= 10
   # Calibration N=13 trigger set is below the validation threshold; kept on
   # case-study merit (Eovaldi 2019, Quintana 2021, Bradish 2026) but should
   # be re-validated when the SP archetype panel grows. Output rationale is
   # tagged "(unvalidated, n=13)" so consumers know.
   # Rationale: walk-driven downgrade with K-stuff intact = post-injury command lag,
   # not stuff loss. Canonical case: Kyle Bradish 2026.

C. HOLD — process intact     (PROCESS_INTACT override; CALIBRATED to rank <= 25)
   bucket == 'SP'
   AND archetype.traj in (TRENDING_DOWN, CAREER_LOW)
   AND model_rank int and <= 25
   # Rationale: the model integrates career + recency and still ranks the SP
   # top-25, disagreeing with the archetype's within-year peer-relative trajectory
   # call. Tightened from <=50 after calibration: rank 26-50 added noise while
   # top-25 cohort showed clean +2.2pp T+1 bounce lift.
   # Calibration named-comps at top-25: Kershaw 2015, Kluber 2016, Sale 2016,
   # Scherzer 2016, Glasnow 2025 — all delivered strong T+1 rebounds.
   # See docs/triangulate_calibration_2026.md.
```

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
- **`signal` column behavior is per-bucket** — rprs2's `signal` (add/hold/drop) is validated and reliable; engine renders it for RPs. The rp3 file currently has a defect (2026-05-28 build flags 213/264 SPs as "il") so the engine NO LONGER renders the signal token for SPs or H — use rank + replacement_delta + recency_form_gap to read the SP/H model. The rprs2 signal IS surfaced in the RP card output.
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

---
name: triangulate
description: Unified three-lens player analysis combining Pitcher List ranks, our projection model (rh3/rp3/rprs2), and the archetype model (20-80 ratings, cell, trajectory, T+1 projection). Works for hitters, SPs, and RPs with a single script that auto-detects the position bucket. Produces a structured profile card per player plus a comparison table for multi-player queries, with a verdict synthesized from the agreement/disagreement pattern across the three sources. Use whenever the user wants the "complete picture" on one or more players, asks "triangulate X", "full profile on X", "compare X Y Z across all lenses", or wants to weigh a PL ranking against our model and the process-based archetype simultaneously.
---

# triangulate — three-lens unified player analysis

> **⚠ Consistency mandate (2026-06-09).** Show the FULL lens stack and keep the
> headline STABLE across turns. Never headline a single sliver (the Steer
> cool↔buy flip). When the actuals lens (boom-bust), the trajectory lens
> (xwOBACON YoY / archetype traj), and the process/ranker lens (rh3·rp3·rprs2 +
> Blended xFP) diverge, write the explicit **actuals vs trajectory vs process**
> reconciliation rather than picking one. A verdict may change only on new data
> or a corrected error — say WHY when it does. **(SP) This explicitly covers the
> stuff-vs-trajectory case:** a high-Stuff+ / lagging-results "buy-low" is a LEVEL
> read, blind to trajectory — never headline it as a BUY without cross-checking the
> decline lenses (archetype STUFF-rating YoY slope + sustainability K%/SwStr +
> comp T+1). If ≥2 say decline, headline the DECLINE, not the buy (canonical:
> Framber Valdez 2026). See
> `reference_lens_merge_protocol.md` → "ALWAYS run + SHOW the full stack" and
> `reference_decision_type_lens_registry.md` (subset = weighting, not hiding).

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

## CLI commands (delta + cache + schedule)

| Flag | Purpose |
|---|---|
| `--snapshot LABEL` | After a batch run with `--csv-out`, also save a dated copy to `data/research/triangulate_universe/snapshots/triangulate_{LABEL}_{YYYY-MM-DD}.csv`. Use to lock in a baseline before a roster/FA shuffle. |
| `--diff PRIOR_CSV` | After the current `--csv-out` run, emit a markdown diff vs PRIOR_CSV (verdict changes, override flips, new/dropped players). Written to `data/research/triangulate_universe/diff_{YYYY-MM-DD}.md` and the top 20 changes are echoed to stdout. |
| `--check-caches` | Print refresh instructions (WebSearch query + WebFetch save-path) for any stale PL cache file, then exit without running. Thresholds: 7d for weekly caches, 2d for streamers. |

### `schedule_idx` CSV column (SP only)

Each SP row carries a `schedule_idx` float in `[0, 1]` — the SP's next-14-day
opponent offensive-strength index, normalised across the current SP universe.
`1.0` = facing the toughest offenses; `0.0` = softest. `None`/blank when the
underlying `next2_avg_bat_index` is missing in `xfp_rp3_projections.csv`
(the schedule_idx layer requires `data/outputs/week_schedule_tilt.csv` to be
populated upstream of the rp3 pipeline; otherwise it falls back to None).

The field is also exposed on the in-process model dict as `model['schedule_idx']`
for downstream callers. No override consumes it yet — it is surfaced for ad-hoc
inspection and future calibration.

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
| `pl_sps_top100.json` | PL Top 100 Starting Pitchers weekly **(main list only)** | Weekly (Mondays) |
| `pl_sp_streamers_latest.json` | PL SP Streamer Ranks daily | Daily |
| `pl_closers.json` | PL Closers and Saves weekly | Weekly |

> **PL IL list gap.** `pl_sps_top100.json` does NOT contain the separate "Injured Pitchers" table from the same article. That table ranks 30-40 IL'd SPs as they would rank if healthy (Snell at IL-#9, Pivetta IL-#13, Eury Pérez IL-#27, Logan Henderson IL-#16, etc.). Until a dated `pl_sps_injury_list.json` is added, IL stash candidates will show `pl_rank=nan` in triangulate even though they ARE PL-ranked. For IL stash workflows, use `/sp-stash-finder` which pulls both lists via WebFetch directly. Known queue item — see `~/.claude/plans/hidden-percolating-harp.md`.

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

#### Public API fields (returned by `triangulate_player()` and written to `--csv-out`)

| Field | Type | Description |
|---|---|---|
| `verdict` | str | Full label (back-compatible; one of 11 strings — see decision tree) |
| `verdict_top` | str | Collapsed top-level: `BUY` / `HOLD` / `CAUTION` / `FADE` / `MIXED` |
| `reason_tag` | str | Original specifier: `strong_hold`, `archetype_breakout`, `model_anchored`, `process_upgrade`, `under_the_radar`, `outcomes_only_rookie`, `post_tj_ramp`, `process_intact`, `process_red_flag`, `pl_outcome_chase`, `no_convergence` |
| `confidence` | float 0-1 | Fraction of 4 independent signals (PL aligned / model aligned / archetype present / arche traj aligned) that converge with `verdict_top`. STRONG HOLD with all 4 signals = 1.0 |
| `watch_list` | list[str] (dict) / `;`-joined str (CSV) | 4-5 counterfactual triggers that would flip the verdict — surfaced for HOLD/CAUTION/MIXED especially |
| `within_bucket_rank` | int / None | Batch mode only: per `(category, bucket)` group, rank by `model_rank` asc. Tells you "this is the user's #3 SP" vs "#11 SP" — critical for the 10-start cap. `None` when input CSV has no `category` column. |

The `format_card()` output now includes a `**Confidence:** N (X of Y signals agree)` line and a `**Watch list:** ...; ...` line.

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

# ---- post-verdict augmentation ----
# After the verdict label is finalized (including 4th-lens overrides), the engine
# computes 5 additional fields surfaced on every dict + CSV row:
#   - verdict_top:    BUY / HOLD / CAUTION / FADE / MIXED  (collapsed from the 11 full labels)
#   - reason_tag:     stable specifier (strong_hold, archetype_breakout, model_anchored,
#                     process_upgrade, under_the_radar, outcomes_only_rookie, post_tj_ramp,
#                     process_intact, process_red_flag, pl_outcome_chase, no_convergence)
#   - confidence:     fraction in [0,1] = (# of {PL aligned, model aligned, archetype present,
#                     traj aligned}) / 4 — independent signals that agree with verdict_top
#   - watch_list:     4-5 counterfactual triggers that would flip the verdict
#   - within_bucket_rank: batch-mode only; per (category, bucket) group, model_rank ascending

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

### SP card additions — variance band + data quality tag

For SPs, the rp3 row in the 3-source table now renders as:

```
| **rp3** | #28 | 12.13 (9.68-14.59) fp/start | rep_d=+0.74 recform=-2.617 dq=data_driven_full | gs_to=12 |
```

- The `(P25-P75)` band comes from `xfp_rp3_p25` / `xfp_rp3_p75` in the
  rp3 CSV — central 50% floor/ceiling.
- The `dq=...` token surfaces `data_quality_tag`:
  - `data_driven_full` — anchored on enough 2026 starts.
  - `data_driven_thin` — too few starts; headline mostly Marcel.
  - `marcel_il` / `marcel_no_data` — pure Marcel regression-to-mean prior.

When `|marcel_baseline − data_driven_estimate| >= 2 FP`, a one-line
**Marcel vs data divergence** flag prints below the table:

```
**Marcel vs data divergence:** model and Marcel disagree by 4.39 FP
(marcel=12.77, data-driven=8.38) — treat the headline as a blend;
weight Marcel side more when data_quality_tag indicates thin data.
```

This is the canonical signal that the headline is in an unstable
transition zone (Grayson Rodriguez 2026-06-02 incident — see
`feedback_show_variance_and_data_quality.md`).

### SP card additions — tier-aware boom-stack tag

**Rank-floor dropped 2026-06-03.** boom_stack now fires for **every SP** with
an rp3 row, not just rank ≥ 50. The rp3 detail row appends a
`boom_stack=N/3 [tier=X] (boom%~Y.Y%, bust%~Z.Z%)` token. boom_stack is the
sum of three pre-game binary signals (skill_spike, recform_hot, opp_soft)
and ranges 0-3. Tier is derived from current rp3 rank:

| Tier | Rank range | Stack=3 boom% | Stack=3 mean FP |
|---|---|---|---|
| `ace` | 1-10 | **56.7%** | 20.9 |
| `sp2_sp3` | 11-30 | 31.2% | 15.9 |
| `backend` | 31-50 | 21.5% | 13.6 |
| `streamer` | 51+ | 17.4% | 10.6 |

The per-tier `boom_rate_expected` / `bust_rate_expected` / `mean_fp_expected`
in the model dict are pulled from `BOOM_RATE_BY_TIER_STACK` /
`BUST_RATE_BY_TIER_STACK` / `MEAN_FP_BY_TIER_STACK` in `scripts/xfp/lib/boom_stack.py`,
which encode the per-tier × per-stack table from
`data/research/validation_runs/boom_stack_by_tier.md`.

#### Callout lines (display only — not verdict overrides)

When `boom_stack >= 2`, a **Boom-stack flag** callout prints listing which
components are lit and the tier-specific boom% + bust%.

When **`tier == 'ace' AND boom_stack >= 2`**, an extra line prints:
`🎯 Ace + boom_stack≥2 = high-conviction boom shot (historical 35-57% boom rate at ace tier).`

When **`tier in {sp2_sp3, backend} AND skill_spike == 1 AND boom_stack >= 1`**,
the engine sets `model['boom_skill_spike_anti_predictive'] = True` and prints:

> ⚠ skill_spike at this tier is historically regression-predictive (not boom-predictive).
> At {tier} tier, recent K%-spike + BB%-drop has negative per-component lift
> (Backend −4.1 pp / SP2_SP3 −3.4 pp). Treat as mean-reversion risk, not continuation signal.

The anti-predictive logic comes from the per-tier component breakdown in
section 3 of the validation report: `flag_skill_spike` had **negative** lift at
SP2/3 (−3.4 pp) and Backend (−4.1 pp), positive at Ace (+3.1 pp) and Streamer
(+2.7 pp). Interpretation: a backend SP with a sudden K%-spike is mean-reverting;
an ace with the same signal is sustaining a real skill jump.

**The tag is informational only — it does NOT override the verdict or the rp3
point projection.** Validated 2026-06-03 (SHIP_AS_TAG, Mode B PASS) + tier-
amplification confirmed in `boom_stack_by_tier.md`. See
`reference_boom_stack_tag.md` and the validation reports at
`data/research/validation_runs/streamer_boom_stack_v1_2026-06-03.md` and
`data/research/validation_runs/boom_stack_by_tier.md`.

### SP card additions — HIGH-K ARM standalone tag

**Shipped 2026-06-03 as PASS_AS_DISPLAY_TAG.** Independent of boom_stack —
a TYPE signal (talent), not a DELTA signal (process change). The flag fires
when this pitcher's cumulative season K% z-scored within the (year, current
month) SP cohort is **≥ +0.5**, requiring **≥3 prior starts** in 2026.

The rp3 detail row appends a `🔥HIGH-K z=+X.XX` token next to the boom_stack
token. A standalone callout always fires when the flag is on:

> 🔥 **HIGH-K ARM:** season K% z=+X.XX within YYYY-MM cohort. Standalone boom
> edge +6.84 pp (p=2.6e-11, n=1,039 historical, validated 2026-06-03).
> Independent of boom_stack — compounds on top.

When **HIGH-K ARM == True AND boom_stack ≥ 2**, an extra compound callout
fires (the actionable case):

> 🔥🎯 **HIGH-K ARM + boom_stack≥2** — tier-amplified boom EV. Expect
> ~+X.X pp on top of base stack signal (stack=2: +9.48 pp / stack=3: +16.82
> pp historical, monotonic amplification).

Per-tier amplification table (HIGH-K=1 vs HIGH-K=0 boom edge within each v1
boom_stack tier, source `boom_stack_v2_validation.md`):

| v1 boom_stack | HIGH-K lift |
|---:|---:|
| 0 | +6.51 pp |
| 1 | +6.18 pp |
| 2 | +9.48 pp |
| 3 | +16.82 pp |

**The tag does NOT override the verdict and is NOT a 4th boom_stack
component.** The v2-as-stack version was NEEDS_MORE_DATA (stack=4 cell n=12
failed Bonferroni-adjusted chi²). The standalone signal is what shipped.
Implementation: `compute_high_k_pitcher()` in `scripts/xfp/lib/boom_stack.py`.
See `reference_high_k_arm_tag.md` and the validation report at
`data/research/validation_runs/boom_stack_v2_validation.md`.

### SP card additions — CATCHER FRAMING standalone tag

**Shipped 2026-06-03 as SHIP_AS_DISPLAY_TAG.** Independent of boom_stack
AND of HIGH-K ARM — pure visual context layer. Fires only on the tails of
the 2026 framing distribution (quintile 1 or 5); Q2/Q3/Q4 catchers produce
no badge.

The pitcher's team's modal 2026 catcher (most pitches received on defense)
is looked up via `pitcher_schedule_2026.csv` → fallback statcast modal.
That catcher's `framing_runs_per_100` (shadow-zone CS% vs league mean ×
0.13) and 2026 in-season quintile (≥200 shadow-pitches floor) determine
whether the tag fires.

When `is_elite_framer == True` (modal catcher in Q5), the inline detail
row adds `🧊ELITE FRAMER` and a callout below the table fires:

> 🧊 **ELITE FRAMER:** <Catcher> (CSAA +X.XX, Q5). Within-pitcher paired
> test p=0.017; historical +3-7 pp boom rate at boom_stack 0/1
> (where existing tags don't already fire).

When `is_framing_tax == True` (modal catcher in Q1):

> ⚠ **FRAMING TAX:** <Catcher> (CSAA −X.XX, Q1, bottom-tier framer).
> Historical −3 pp boom rate within-pitcher (p=0.017). Soriano-O'Hoppe
> is the canonical case.

**The tag does NOT override the verdict and is NOT a 5th boom_stack
component.** The 5th-component variant was rejected to avoid double-
counting downstream catcher-receiving effects already absorbed by
drift_swstr / c_plus_swstr in the rp3 v2 baseline. Within-pitcher paired
test (n=208 SPs with starts vs BOTH Q1 and Q5 catchers): t=2.40,
p=0.017, +3.06 pp boom-rate gap. 6/7 years positive (2018-2025, ex-2020).

Implementation: `compute_catcher_framing()` in
`scripts/xfp/lib/catcher_framing.py`. See `reference_catcher_framing_tag.md`
and the validation report at
`data/research/validation_runs/catcher_framing_boom_modifier.md`.

### SP card additions — IL_RETURN salvage tag

**Shipped 2026-06-03 as standalone display tag — salvaged from the
otherwise-rejected bust_stack_v2_context research program.** Independent
of boom_stack, HIGH-K ARM, and catcher framing. Fires when the
pitcher's previous MLB start was >= 30 calendar days before the next
scheduled start (proxy for "first start back from a 30+ day IL stint").

Computed on the fly from `statcast_2026.parquet` (last MLB start: latest
`game_date` with >= 5 PA) and `pitcher_schedule_2026.csv` (next scheduled
start; falls back to `date.today()` when the pitcher isn't in the probables
feed).

When `is_first_back_long_il == True`, the inline detail row adds
`🏥IL RETURN (Nd)` and a callout below the table fires:

> 🏥 **IL RETURN start** — pitcher's previous MLB outing was Nd ago
> (last MLB start YYYY-MM-DD); gap to next scheduled start >= 30d.
> Historical bust rate +2.93 pp at first-back-from-long-IL starts
> (n=640, p=0.044; salvaged from bust_stack_v2 research). Cross-reference
> `/sp-rehab-tracker` for MiLB rehab quality if applicable. Display tag
> only, not a verdict override.

**Why standalone, not a bust_stack component:** the parent
bust_stack_v2_context program was rejected (DON'T_SHIP) — H1 stack=3
magnitude failed (16.73% vs >=25% target), H2 components failed
Bonferroni (0/5 passed alpha=0.01), H3 year-stability failed (4/7
years sign-positive). But `flag_first_back_long_IL` was the one signal
with both real lift AND intuitive mechanism (rust + rehab quality
uncertainty). Salvaged as a TYPE-style standalone tag — same pattern
as HIGH-K ARM and catcher framing.

Implementation: `compute_il_return_flag()` in
`scripts/xfp/lib/il_return_flag.py`. See `reference_il_return_tag.md`
and the validation report at
`data/research/validation_runs/bust_stack_v2_context_validation.md`.

### SP card additions — sp-decline velo-trajectory lens + DECLINE VETO ✅ WIRED (2026-06-14)

**The concrete operationalization of the §2 / consistency-mandate decline
cross-check — now wired into the engine, not a manual side-call.** The mandate (top
of this file) says a high-Stuff+ / lagging-results "buy-low" is a LEVEL read, blind
to TRAJECTORY, and must be cross-checked against the decline lenses before headlining
a BUY. The SP card now joins `sp_decline_model.decline_lens_map()` by MLBAM and
surfaces both the **velo-trajectory flags** and the **decline-risk tier**, and a new
**DECLINE_VETO override** enforces the mandate automatically.

**Velo-trajectory token** on the rp3 detail row (validated `velo_signal_2026-06-13.md`):
`velo[vYoY±X.X▼ vIn±X.X v2y±X.X▼▼] SEVERE` — the three velo decline horizons
(YoY vs last-season-end, in-season vs 2026-peak gated ≥80 BF, 2-year vs 2024-end)
plus the composite severity (`SEVERE` double-fade / `LOW-VELO` tilt). Velo is a
bust/conviction lens, NOT a mean-FP term — it never moves the rp3 point estimate
(CLAUDE.md #13). Callouts fire below the table on SEVERE (~49% forward bust) and
LOW-VELO.

**DECLINE VETO** (`apply_overrides`, override_tag `DECLINE_VETO`): when a verdict
resolves to any **BUY** but the SP shows a **SEVERE velo fade** OR a **DECLINE-RISK**
whiff/K-level tier, the headline is downgraded to **`CAUTION — decline veto`** with an
explicit actuals-vs-trajectory reconciliation. This is the Framber/Weathers trap: an
"archetype breakout" / "model anchored" BUY that is really a `marcel_il`-suppressed
rank gap on a fading arm. The veto changes the verdict **LABEL only** — the rp3 point
number is untouched (#13 preserved; the mandate about not contradicting yourself is
enforced). Canonical: **Ryan Weathers 2026-06-14** (BUY — archetype breakout →
CAUTION — decline veto; SEVERE velo fade + marcel_il rp3).

`/sp-decline` remains the dedicated full board (league-wide + your staff). The
triangulate card now carries the same lens inline so a Stuff+/PL buy-low can't slip
through without the trajectory cross-check.

The lens (`sp_decline_model.build()`, validated 2026-06-13
`sp_decline_stuff_decay_2026-06-13.md`, partial-r ~0.235 on the whiff/K LEVEL)
classifies each 2026 SP (≥5 GS) into:

- **DECLINE-RISK** — below-average whiff/K stuff LEVEL (`stuff_level_pctl ≤ 45`)
  with FP still propped above it → RoS FP regresses DOWN. The Framber Valdez 2026
  pattern (K% 18.6% / SwStr% 9.1%).
- **RISING** — whiff/K level well ahead of FP → sustainable / buy-low-safe.
- **STABLE** — level supports the FP (aces never flag).

Surface it on the SP card as a `sp-decline=DECLINE-RISK (lvlPct N, gap +M)` token
in the rp3 detail row, and when it fires DECLINE-RISK, a callout below the table:

> ⚠ **sp-decline DECLINE-RISK:** whiff/K stuff LEVEL is below average (pctl N)
> with FP propped above it (gap +M) — RoS FP regresses DOWN. If a Stuff+/PL
> "buy-low" is on the table for this SP, this is the trajectory lens that VETOES
> the buy headline (≥2 declining signals → headline the DECLINE, not the buy).
> Display/context flag only — does NOT move the rp3 point estimate (CLAUDE.md #13).

**How it interacts with the verdict:** the velo flags + tier are **display/conviction
context** (never move the rp3 point number, #13). The **DECLINE_VETO** is the one
place the decline lens touches the verdict — and it touches the **label only**, never
the projection: it downgrades a BUY *headline* to `CAUTION — decline veto` when SEVERE
velo or DECLINE-RISK contradicts it. This is the engine enforcing the mandate's
"if the decline lenses veto, headline the DECLINE not the BUY" rule, so it can't be
forgotten in a fast turn.

**Engine wiring (DONE 2026-06-14).** `triangulate_core.model_row()` SP branch joins
`sp_decline_model.decline_lens_map()` (a cached, ownership-free public helper) by
MLBAM and adds `decline_tier` / `velo_*` fields; `apply_overrides()` adds the
`DECLINE_VETO` branch; `run_triangulate.format_card()` renders the velo token +
callouts and `compare_table()` adds a "Velo traj" column; the batch CSV carries
`decline_tier`/`velo_severity`/`velo_yoy`/`velo_in`/`velo_2y`. Regression fixtures
updated in `tests/test_triangulate.py` (Weathers veto canonical + 12th verdict tier).

### RP card additions — rp-decline tier (role-loss CONVERGENCE WATCH lens)

**The RP-side parallel of the sp-decline SP-card addition.** RP value is
opportunity-dominated (rprs2 r≈0.87 — saves/holds are the ROLE), so the decline
that matters for an RP is a **role crater**, not rate regression. `/rp-decline`
(`rp_decline_model.build()` / `tier_map()`, validated 2026-06-13:
`rp_decline_stuff_velo_2026-06-13.md` velo-YoY-decline partial-r +0.112;
`rp_decline_role_leverage_2026-06-13.md` role-loss −38% FP-crater mechanism)
classifies each 2026 RP (≥8 G) into:

- **ROLE-RISK** — velo declining YoY **AND** (whiff/K LEVEL weak **OR** sv+hld
  share slipping) **AND** has a role to lose → the role is most likely to crater.
  A sell-high-while-saves-still-land candidate. (Emilio Pagán 2026 pattern.)
- **WATCH** — one leg firing; a fade to monitor, not yet a role-loss setup.
- **NA-VELO** — no 2025 velo, primary signal blind — **NOT a clean bill**.
- **SECURE** — velo stable/up and skill+role intact.

Surface it on the RP card as an `rp-decline=ROLE-RISK (velo YoY −1.6, 2/3 legs)`
token in the rprs2 detail row, and when it fires ROLE-RISK, a callout below the
table:

> ⚠ **rp-decline ROLE-RISK:** velo declining YoY AND skill/role-share slipping —
> the convergence that precedes a role-loss FP-crater. A sell-high-NOW candidate
> while saves/holds still land. **Honestly weaker/noisier than the sp-decline SP
> equivalent** (velo +0.112 vs SP whiff/K +0.235; role loss ~1/3 manager-driven,
> AUC 0.683 — it tilts the odds, it does NOT predict). Display/context flag only —
> does NOT move the rprs2 point estimate or the verdict (CLAUDE.md #13).

**How it interacts with the verdict:** exactly like the sp-decline SP token and the
boom_stack/HIGH-K/framing display tags — it is a **context/risk flag, never a
headline mover or an additive verdict input** (CLAUDE.md #13). It adds **no** new
branch to the verdict decision tree. Its job is to make the RP analog of the
"trajectory lens" concrete: a high-rprs2 closer whose role is quietly converging on
a crater should be read as a SELL-HIGH, not a blind HOLD.

**Engine wiring (TODO — documented-only for now, mirroring the sp-decline RP
parallel).** Surfacing this in `run_triangulate.py` cleanly means joining
`rp_decline_model.tier_map()` (the ready-made public join helper) by normalized
name in the RP branch of `triangulate_core.model_row()` and rendering the
token/callout in `format_card()`. That touches the verdict-augmentation path and
the multi-bucket card renderer, so — as with sp-decline — it is left as a clear
TODO rather than wired inline to avoid destabilizing the verdict tree. **Until
wired, run `/rp-decline --players "X"` alongside `/triangulate "X"` for any RP
where a sell-high / hold-the-closer call is in play.** `tier_map()` returns
`{norm_name: {tier, role, legs, velo_yoy, velo_flag, svhld_per_g, role_slip_frac,
has_role}}` and degrades to `{}` if the rolling cache is unavailable.

### Hitter card additions — hitter boom-stack advisory tag

**Shipped 2026-06-03 as SHIP-CAUTIOUS advisory tag (3-component); 4th
component `lineup_amp_hitter` added 2026-06-03.** The hitter analog of
the SP boom_stack: a sum of FOUR pre-game binary signals computed live
from the 2026 statcast panel + today's confirmed probable SP + today's
expected lineup. Range 0-4.

The rh3 detail row appends a `boom_stack=N/4 (boom%~X.X%)` token. When
`boom_stack >= 2`, a callout line prints below the rh3 row:

> 🎯 **Hitter boom flag:** boom_stack=N/4 (lit components) — historically
> 27-34% chance of >=10 FP game (~X.X% boom rate, ~Y.Y% bust vs 23.9%
> baseline). Advisory tag only; stack=3 still busts 37.5%.

When component 4 `lineup_amp_hitter` is lit, an additional callout follows:

> 🌊 **LINEUP STACK** — N teammates also in boom-eligible form (team boom
> rate ~34% historical at lineup_stack=3+, validated 2026-06-03).

| # | Component | Threshold |
|---|---|---|
| 1 | `skill_spike_hitter` | last-10g xwOBA - season xwOBA ≥ +0.040 AND last-10g K% - season K% ≤ -3 pp (needs ≥20 prior games) |
| 2 | `recform_hot_hitter` | last-10g fp_proxy/g - season fp_proxy/g ≥ +1.5 (fp_proxy = TB + BB + HBP - K, the validation unit) |
| 3 | `opp_soft_hitter` | today's opposing SP `xfp_rp3_per_start` ≤ 33rd-pct (weak SP = soft opp). If no confirmed probable yet, component is 0 with reason `no_opp_sp` |
| 4 | `lineup_amp_hitter` | own components 1+2+3 ≥ 1 AND ≥ 2 OTHER starters on today's expected lineup also have components 1+2+3 ≥ 1. Lineup resolved via MLB Stats API confirmed lineup; falls back to top-9-by-rh3 for the team. Recursive guard: teammate stacks computed with `skip_lineup_amp=True` so component 4 never recurses. |

Per-stack outcomes (n=245,712 starter-games, 2018-2025, PA≥4, boom = fp_proxy
≥ 80th pct):

| boom_stack | n | boom rate | bust rate | mean fp_proxy |
|---|---|---|---|---|
| 0 | 161,766 | 23.9% | 43.4% | 1.12 |
| 1 | 75,234 | 25.6% | 40.7% | 1.27 |
| 2 | 7,971 | 27.5% | 40.2% | 1.35 |
| 3 | 741 | 30.6% | 37.5% | 1.58 |
| 4 | *(extrapolated)* | ~34.0% | ~35.0% | ~1.73 |

Stack=4 is extrapolated — anchored to the validation heatmap cell
(own_stack=2 + 3+ teammates_stack2 = 32.5% boom rate, n=268) and the
team-day lineup_stack2=3+ boom rate (33.8%, n=396). See
`reference_lineup_amp_component.md`.

Edge stack=3 vs stack=0 is +6.7 pp boom rate, year-stable 2018-2025
(+2.3 to +5.3 pp on stack≥2 vs 0 every year). **Strongest single component
is `recform_hot_hitter` (+3.7 pp).** Smaller than the SP analog (+9.4 pp)
because daily-hitter outcomes are noisier than per-start SP outcomes; the
spec is SHIP-CAUTIOUS advisory only and does NOT override rh3 or the verdict.

Implementation: `scripts/xfp/lib/hitter_boom_stack.py` (live compute +
MLB Stats API today-probable resolver), wired into `triangulate_core.model_row()`
HITTER branch, rendered by `run_triangulate.format_card()`. See
`reference_hitter_boom_stack.md` and the validation report at
`data/research/validation_runs/hitter_boom_bust_deep_dive.md`.

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
- **Don't treat rookies' missing archetype rows as "no signal"** — explicitly note "insufficient innings/PA for archetype profile" and rely on the Statcast process layer instead. For SPs specifically, run `/shadow-scout` — it pulls 2026 MLB Statcast and grades FB velo / K% / BB% / whiff% / CSW% against the live 432-SP population (>=200 pitches). Canonical use: Henderson, Sasaki, Ben Brown 2026-06-04. When the shadow grade is PLUS_PROCESS (>=60) and the archetype panel says CAREER_LOW, **trust the shadow** — the archetype panel is annual-aggregated and trails by ~6 weeks.
- **`signal` column behavior is per-bucket** — rprs2's `signal` (add/hold/drop) is validated and reliable; engine renders it for RPs. The rp3 file currently has a defect (2026-05-28 build flags 213/264 SPs as "il") so the engine NO LONGER renders the signal token for SPs or H — use rank + replacement_delta + recency_form_gap to read the SP/H model. The rprs2 signal IS surfaced in the RP card output.
- **For SPs, two validated lenses live outside triangulate** (2026-06-06) — don't reinvent them inline: `/sp-stuff-board` (FanGraphs Stuff+ RoS-FP projection — the MEAN; velocity-driven; Stuff+→rp3 Rule-9 PASS +0.0095) and `/sp-floor` (per-start bust probability — the FLOOR; driven by K−BB%, NOT stuff). Canonical: a low-Stuff+/high-command arm (Messick) is a HIGH-floor start even when stuff/EV rank him low. When a triangulate SP verdict hinges on "is this start safe / who do I bench," hand to `/sp-floor`; when it hinges on "elite stuff the box score hasn't caught," hand to `/sp-stuff-board`. **Location+/command REJECTED as a fantasy-points signal** — never fade a high-Stuff+ SP for walks. **But Stuff+ is a LEVEL lens, blind to TRAJECTORY** — never headline a high-Stuff+/lagging-results vet as a "buy-low" without the decline cross-check (archetype STUFF YoY slope + sustainability K%/SwStr + comp T+1); ≥2 declining → headline DECLINE, not buy (Framber 2026). See `/sp-stuff-board` mandatory cross-check + `reference_lens_merge_protocol.md` SP rule #6.
- **Don't synthesize a verdict from just rank gaps** — always weigh the archetype trajectory and T+1 because those are the leading indicators when PL and model disagree
- **Don't add a fourth data source ad-hoc** — if you find yourself reaching for Statcast L21d or bat tracking, hand off to `/fa-pickup-deep-dive` rather than expanding the triangulate output
- **Don't print per-player markdown cards for >10 players** — switch to batch mode (`--csv-out`) and dispatch parallel agents per category for synthesis. A 400-player run in interactive mode would dump 30k+ lines and blow context
- **Don't trust ESPN's `applied_total`/`points` fields for FP filters** — they return 0 across the public API for most players. Use the model-derived season-to-date FP (see "Mega-research mode" above) for "FAs above N FP" type filters
- **Don't assume `recent_activity` returns Player objects** — in this `espn-api` version the action tuple is `(Team, action_str, player_name_str)`, NOT `(Team, action, Player)`. Position has to be looked up post-hoc from the projection files
- **Don't treat MIXED as "no signal"** — when archetype OVERALL ≥ 60 and trajectory is TRENDING_UP but model lags <50 ranks (so the BUY-archetype-breakout rule doesn't fire), the synthesize() output is MIXED but the player is usually a quiet BUY (canonical: Casey Schmitt 2026, arche 66 CONTACT_POWER TRENDING_UP, verdict MIXED because model lag was only 26 ranks). Read the archetype row before defaulting to "wait and see"

---

## Dashboard view

A browser-based view of the triangulate results lives at `xfp-model/docs/triangulate.html` (published via GitHub Pages alongside the other dashboards). It loads a sibling JSON file `triangulate_data.json` at page-load and renders:

- generated timestamp + player/bucket counts header
- verdict-distribution bars (color-coded: BUY=green, HOLD=blue, CAUTION=amber, FADE=red, MIXED=gray)
- override-counts mini-table
- a filterable + sortable player table (Name, Team, Bucket, PL, Model, Arche OVERALL, Label, Traj, Verdict, T+1, Rationale) with filters by team (dropdown), bucket (H/SP/RP buttons), verdict (multi-select), override (multi-select), and a name search box

### `--json-out` flag

The engine accepts `--json-out PATH` in batch mode. May coexist with `--csv-out` (both will be written). When set alone, no per-player cards are printed. JSON schema:

```json
{
  "generated": "2026-05-30T...Z",
  "n_players": 230,
  "n_unresolved": 0,
  "verdict_counts": {"STRONG HOLD/BUY": 40, "FADE": 9},
  "override_counts": {"PROCESS_INTACT": 3, "POST_TJ_RAMP": 1},
  "bucket_counts": {"H": 130, "SP": 70, "RP": 30},
  "players": [
    {
      "name": "Aaron Judge", "bucket": "H", "team": "NYY",
      "pl_rank": 1, "model_rank": 2, "model_proj": 2.48, "model_proj_label": "fp/PA",
      "arche_overall": 74, "arche_label": "GOAT_TIER", "arche_traj": "TRENDING_DOWN",
      "arche_t1_fp": 0.566, "arche_career_pct": 0.99,
      "verdict": "STRONG HOLD/BUY", "rationale": "...", "override_tag": null,
      "category": "New York Ligers"
    }
  ]
}
```

### Data refresh

```bash
python scripts/xfp/run_triangulate.py \
    --names-file data/research/triangulate_universe/all_teams_roster.csv \
    --json-out   xfp-model/docs/triangulate_data.json
```

### Local preview

```bash
python -m http.server 8000 --directory xfp-model/docs
# then open http://localhost:8000/triangulate.html
```

The dashboard is fully self-contained (inline CSS + vanilla JS, no build step) and uses the same Source Serif 4 / IBM Plex Mono palette as the other docs in `xfp-model/docs/`.

---

## Files

- Engine: [scripts/xfp/run_triangulate.py](../../scripts/xfp/run_triangulate.py) — supports both interactive (`names ...`) and batch (`--names-file`, `--csv-out`, `--json-out`) modes
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

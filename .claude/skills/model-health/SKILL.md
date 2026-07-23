---
name: model-health
description: Run the MODEL SCORECARD + DATA-HEALTH engine — the permanent measurement backbone that (a) tracks each production model's forward accuracy over time (rh3 / rp3 / rprs2 rate + total Spearman at 7/14/21/28d anchors, model-vs-prior delta, tercile bias/MAE, C-vs-rest and data_quality_tag slices, volume-model skill vs naive pace) and (b) catches silent data regressions via PASS/WARN/FAIL tripwires (IL-join match rate, ros_opp_xwoba NaN rate, frozen ros/park cache, statcast + boxscore lag, FG snapshot age, fg_proj_cache gaps, projection row-count swings, proj_volume fill). Use when the user asks "model health", "health check", "is the model still calibrated", "run the scorecard", "did anything break in the data", "are the models degrading", "how accurate have the projections been", "any dead features", or monthly/after any pipeline refactor. Built 2026-07-10 after rp3's three IL features were discovered DEAD for 6 weeks (join match rate 0.45%, invisible to LOO r) — a scorecard run would have caught it in days.
---

# model-health — model scorecard + data-health tripwires

## What this is

The **referee for the whole model stack**. Two sections, one engine:

1. **FORWARD ACCURACY** — at anchor snapshots ~7/14/21/28 days back (from
   `data/research/player_projection_history.parquet`, daily since 2026-06-04),
   scores every production model against realized forward BrownU FP from the
   boxscore parquets. All joins **mlbam_id only**. Hitters per-PA (PA counted
   from `statcast_2026.parquet`), SPs per-start, RPs per-appearance (rprs2's
   proj is a RoS TOTAL, so RP metrics are rank-only). Also the ongoing referee
   for the **volume models** shipped 2026-07-09: Spearman(proj_volume,
   realized forward PA/GS per team-game) vs the naive backward-pace
   comparator (validated at +0.074 H / +0.100 SP — watch for decay).
2. **DATA HEALTH** — regression tripwires that each print **PASS/WARN/FAIL
   with a number**. The canonical catch target: the 2026-07-09 rp3 IL-join
   regression (a cache-cadence change killed the `rolling x
   il_split_features` join; match rate fell 28% -> 0.45% and NO model metric
   noticed for ~6 weeks).

## How to run

```bash
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/build_model_scorecard.py
```

Exit code 0 = no FAIL tripwires; 1 = at least one FAIL. Outputs:

- `data/outputs/model_scorecard.csv` — long format (date, section, metric,
  segment, value, status, note)
- `data/outputs/model_scorecard.md` — rendered scorecard
- `data/research/model_scorecard_history.csv` — dated history, appended
  (idempotent: same-day re-run replaces same-day rows)

## Steps

1. **Run the engine** (command above). It is fail-soft — a missing input
   yields SKIP with a message, never a crash. Read the console summary.
2. **Triage tripwires first.** Any FAIL = "the model is lying to you here"
   candidate — the models will keep emitting confident numbers on top of the
   broken substrate. For each FAIL/WARN, read the note (it carries the
   healthy band and n) and identify the owning builder:
   - `il_join_match_rate` -> `scripts/xfp/build_il_split_features.py`
     (grid derives from the rolling CSVs — regenerate AFTER any rolling
     cache regen; see `rp3_il_join_fix_2026-07-09.md`)
   - `il_grid_coverage` -> `scripts/xfp/build_il_split_features.py`
     (2026-07-11: FAILs if any rolling `(year, split_day)` cell is MISSING
     from the IL cache — the direct cause the match-rate check only sees as
     a consequence. Fix: rebuild IL features after the rolling substrates;
     `refresh_all.py` now orders the IL stage after them.)
   - `il_tx_json_freshness` -> the IL-transactions self-refresh in
     `build_il_split_features.py` (2026-07-11: FAILs on a stale
     `il_transactions_2026.json` FILE mtime — proves the STALE_AFTER_DAYS
     refetch is running; newest-event staleness is WARN-only so the ASG
     break / transaction lulls don't false-fire.)
   - `ros_opp_xwoba_nan_rate` / `ros_cache_split_day_lag` ->
     `scripts/xfp/build_ros_schedule_features.py`
   - `statcast_max_date_lag_days` -> gf bridge
     (`build_statcast_gf_bridge.py`, refresh step 1.05)
   - `boxscore_*_lag_days` -> `refresh_boxscores.py` (step 1.5)
   - `fg_scrape_silent_fail` (was `fg_2026_snapshot_age`) / `fg_proj_cache_*`
     -> the daily FG scrape `scripts/_oneoff/fg_2026_current.py` (step 0.8).
     TIGHTENED 2026-07-20: FG is a DAILY step but its Chrome scrape EXITS 0
     even when chromedriver crashes, so the refresh's fail-soft logs ✓ while
     the file freezes (canonical: 6d frozen at 7/14). Thresholds are now
     daily-tight — WARN >2d (≥1 missed scrape), FAIL >5d — and a MISSING
     current file is FAIL. Fix = rerun the scrape in an interactive shell
     with a working Chrome; the scrape's exit code is unreliable, trust this
     tripwire's age instead.
   - `proj_rowcount_delta_7d` -> the model pipeline whose CSV swung
   - `proj_volume_fill_rate` -> volume builders (steps 4.09/4.09b) or
     snapshot-logger ordering (4.10 must run AFTER 4.09)
   Report the finding with severity; fix only with the user's go-ahead.
3. **Read forward accuracy against the honest baselines**, not against
   same-period fit: forward Spearman ~**0.30-0.40** for rp3 and rh3-vs-TOTAL
   at 21-28d is HEALTHY (the 2026-06-26 retro showed same-period r 0.77+ is
   inflated). First-scorecard baselines (2026-07-10): rh3 rate 0.21 / total
   0.40 @21d; rp3 rate 0.33 @21d; rprs2 total 0.26 @21d; model-vs-prior
   delta positive everywhere (+0.02..+0.07 = in-season layer earning).
4. **Compare to the last N scorecards** in
   `data/research/model_scorecard_history.csv` (filter by metric, plot/eyeball
   value by date). One weak anchor is noise; a **sustained slide across
   runs** (e.g. rp3 21d rate 0.33 -> 0.25 -> 0.15) or a vs-prior delta
   going persistently NEGATIVE (in-season layer now hurting) is the signal.
5. **Synthesize**: a short report — tripwires fired (with numbers + owner),
   models degrading vs stable (with trend), volume-model referee status,
   and any "insufficient data yet" notes (e.g. volume skill needs ~5+
   forward days past 2026-07-10, the first snapshot carrying proj_volume).

## Pipeline staleness section (added 2026-07-20)

Third scorecard section (`pipeline_staleness`), same PASS/WARN/FAIL pattern,
FAILs count into the exit code. Charter: **model-health owns DATA/PIPELINE
runtime health; /production-audit owns CODE/SKILL/registry drift.** Each check
is fail-soft (an errored check reports WARN, never crashes the scorecard).

1. `console_data_freshness` — WARN = `console_data.json` is older than a
   model input (rh3/rp3/rprs2 CSV or boxscore_hitters) → the decision console
   is serving stale numbers (the 2026-07-18 trap). Fix: regenerate the console
   (the refresh step that builds `data/outputs/console_data.json`).
2. `tri_nightly_freshness` — FAIL = freshest
   `triangulate_nightly_*.json` ≥26h old (nightly not running; rerun the
   triangulate nightly builder). WARN = `_cards.json` sidecar missing
   (first-night tolerance; FA cards fall back to the flat batch).
3. `publish_freshness` — WARN = a GitHub Pages artifact
   (`xfp-model/docs/{index,matchup,triangulate,xfp_board}.html`) lags
   `console_data.json` by >26h → stuck publish. Fix: rerun the publish step /
   `/refresh-matchup` push. SKIP if the xfp-model sibling isn't checked out.
4. `espn_snapshot_ttl` — WARN = a `data/research/espn_snapshot/` file is
   older than 4× its TTL (env `PLV_ESPN_SNAPSHOT_TTL_MIN`, default 240 min)
   → a refresh crashed mid-flight and left its snapshot behind. Fix: delete
   the stale snapshot (it only exists refresh-side).
5. `trajectory_endpoint` — WARN = the freshest nightly CSV's
   `traj_last_label` MM-DD endpoints max out >3 days before the file's own
   date (the frozen 04-25→06-20 trajectory class). Fix: rebuild the archetype
   trajectory panels feeding the nightly.
6. `golden_stash_leftover` — FAIL = `data/models/.golden_stash/` has a
   subdir → a crashed /golden-run left model pkls stashed (production may be
   running swapped-in goldens). Fix:
   `python scripts/ci/golden_run.py --restore`.

## Reading the output

- `status`: **PASS/WARN/FAIL** (health tripwires), **INFO** (accuracy
  metric), **INSUFFICIENT** (n or window too small — do not interpret),
  **SKIP** (input missing — itself a mild health signal).
- Every accuracy metric is **conditional on forward-volume floors**
  (hitters >=~15-30 fwd PA, SPs >=2-4 starts, RPs >=3+ apps) — survivorship
  is real and stated in the note. Do NOT recalibrate projections from the
  tercile bias rows (Rule 13 / fast-path gotcha 13: the mild positive bias
  on regulars is expected and validated as non-actionable).
- `*_vs_prior_delta` > 0 = the in-season model layer beats its own Marcel
  prior at ranking forward outcomes. This is the "is the machine-learning
  earning its keep" number.
- SP `marcel_il` segment rows measure the SUPPRESSED prior, not the model —
  expect them weak; they're there to catch the opposite failure (marcel_il
  arms secretly ranking better than data_driven = tagging bug).

## Hard rules

1. **Measurement only.** Nothing in the scorecard moves an rh3/rp3/rprs2
   number. A degrading metric routes to investigation (or
   `/validate-feature` for any proposed fix), never to a silent re-rank.
2. **mlbam_id joins only** — never name joins (Muncy/Warren collisions).
3. **>=20-day windows / >=4 starts carry the weight.** 7d anchors are shown
   for freshness but flagged INSUFFICIENT when thin — don't headline them.
4. **Don't "fix" a WARN by loosening its threshold.** Thresholds encode
   post-mortems (IL join healthy ~27-32%, dead at 0.45%). If a threshold
   seems wrong, check the history CSV for what normal has actually been.
5. **State survivorship every time** forward accuracy is reported.

## Canonical example (the bug this skill exists to catch)

2026-07-09: rp3's three IL features (`il_stints_to`, `is_on_il_at_split`,
`days_since_il_return_imp`) had been silently dead for ~6 weeks. A rolling-
cache cadence change shifted the `split_day` grid; `build_il_split_features`
was not re-run, so the `['pitcher','year','split_day']` merge matched only
0.45% of rows and fillna(0) hid the rest. LOO r barely moved (the features
are small), projections kept publishing daily, and 47 arms carried wrong
tags until a manual audit. `il_join_match_rate` on this scorecard reads that
exact join: 0.28 all-years PASS today; <0.05 FAIL. A monthly `/model-health`
run turns that 6-week silence into days.

## Cadence + companions

- **Weekly (Monday)** via refresh step 4.13 (fail-soft; see
  `docs/wiring_notes_2026-07-10_scorecard.md`), or on demand monthly at
  minimum, and ALWAYS after touching any cache builder or model pipeline.
- Companions: `/matchup-audit` (dashboard-level SP bugs), `/validate-feature`
  (promoting fixes), `reference_validated_signals_registry.md` (what is
  allowed to drive decisions), `model_forward_calibration_2026-06-26.md`
  (why forward r ~0.35 is honest, not broken).

## Paired Monday run: /verdict-scorecard (added 2026-07-18)

This skill grades the MODELS; its sibling grades the CALLS. The Monday
refresh runs both (steps 4.13 + 4.13b). When invoking /model-health
manually, also read `data/outputs/verdict_scorecard.csv` (or run
`python scripts/xfp/run_verdict_scorecard.py`) and check the two open
watch items from the 2026-07-18 first read:
1. Confidence calibration INVERSION — 1.00-conf calls hit 7.7% vs
   0.75-conf 32.5%. If it persists at directional n≥10 per bin, the
   4-of-4-signals confidence formula is overclaiming.
2. SP MIXED cohort missing projection by −5.5 FP/start (n=5/3 — noise
   until more settles).
July decision cohort (Mead/Bennett/Henderson churn) settles ~2026-08-08.

# Production audit — 2026-07-19

Full behavior-preserving audit of the engines, nightly refresh pipeline, model
pipelines, dashboard/skill engines, and shared-lib layer. Four parallel deep
passes (refresh / models / engines / libs+tests+data). This file is the durable
record: what was found, what shipped same-day, and the ranked backlog.

Scope rule: NO model feature/math changes (Rule 9), no verdict-logic changes.
Targets: duplicate compute, fragility, silent-failure joins, dead weight.

---

## Shipped same-day (commit "audit: ...", 2026-07-19)

1. **Killed the nightly ~45-60 min duplicate FA re-triangulation (top finding).**
   Step 4.73 (`build_triangulate_dashboard.py --live-fa`) re-ran
   `triangulate_player()` per FA over the exact pool step 4.72b had just
   batch-triangulated (~25-30% of nightly wall-clock, and it head-of-line
   blocked the publish). Fix, three parts:
   - `lib/triangulate_core.assemble_result(...)` — the result-dict schema
     extracted into ONE shared seam; `triangulate_player()` now calls it.
   - `run_triangulate.py --cards-out PATH` — the nightly batch (4.72b) also
     persists the FULL per-player result dicts (`{name: result}`, JSON-safe via
     `_jsonable`) as `triangulate_nightly_<date>_cards.json`. Serial + parallel
     shard paths both plumbed.
   - `build_triangulate_dashboard.py` — `load_fa_cards_store()`; the DEFAULT
     build now hydrates FA cards from the store (full fidelity: confidence /
     bands / watch list / value tier), flat-batch fallback per missing name,
     `--live-fa` demoted to a manual force-live override. The nightly glob
     excludes `*_cards.json` so the sidecar can't shadow the batch payload.
   - refresh: old 4.7 (roster-only, pre-batch) removed; the single dashboard
     build now runs AFTER the 4.72 chain as the new 4.7. Step 4.73 deleted.
   Verified: 4-player store round-trips through `build_card_data` + card HTML
   with confidence/watch/blend intact; glob still resolves the batch JSON.

2. **Publish gating (F2).** `refresh_dashboards.py`: if the step-2 model
   rebuild fails, steps 5/6 (xfp-model commit+push) are SKIPPED with a loud
   "PUBLISH GATED" message instead of publishing dashboards rendered from
   stale projections. Fail-soft build steps still run.

3. **`console_data.json` staleness trap (H4).** `lib/decision_console.py`
   `--if-stale` now requires the payload to be same-day AND newer (mtime) than
   its key inputs (rh3/rp3/rprs2 CSVs + boxscore parquet). The old
   calendar-date check served the morning payload all day even after an
   intraday refresh (the 2026-07-18 `rm console_data.json` workaround).

4. **rprs2 counting-join match-rate guard (R1).** `models/xfp/rprs2.py`: the
   `pitcher_counting_stats_2026.json` left-join now prints its match rate and
   raises if <50% (pool ≥20) — an id desync would previously zero
   `fp_actual_2026` silently and collapse `xfp_ros` to `xfp_full_year` for the
   whole RP board (same failure shape as the 6-week rp3 IL-join regression).

5. **Dormant HLD=3 scoring landmine (H2 sub-finding).**
   `scripts/xfp/league_config.py` declared `'HD': 3` (docstring too) vs the
   league's actual 2 (canonical `fantasy/scoring.py hd=2.0`). No consumer read
   the weight dict yet — corrected before one ever did.

6. **64 MB `.csv.bak` tracked in git.** `.gitignore` covered only
   `*.parquet.bak` in xfp_cache; `rolling_hitters_2018_2026.csv.bak` (63.8 MB,
   biggest tracked file in the repo) slipped through. Rule widened to `*.bak`,
   file `git rm --cached`'d (kept on disk).

7. **rh3 `career_stage` vectorized (W1).** Row-wise `.apply` over the full
   multi-year rolling frame → `year - batter.map(first_year)`, output-identical.

8. **Dead code removed (DC1).** `derive_2b3b_rate` / `rate_2b3b` in
   `build_hitter_archetypes.py` — computed, never rated, never exported.

9. **Canonical verdict locks re-pinned** (pre-existing data drift from the
   07-19 refresh, verified to fail on pre-change code): Weathers → bucket-only
   lock (5th BUY/MIXED flip; pre-committed remedy), Suárez FADE→MIXED
   (boundary churn, re-pinned once), Schmitt sub-reason lock dropped (BUY top
   kept; the two BUY rules oscillate).

Non-finding: the two `requests.get`-without-timeout claims
(`run_decision_trend.py`, `run_second_half_splits.py`) were wrong — both
already pass `timeout=`.

---

## Backlog items 1-4 — SHIPPED 2026-07-19 (second commit, same day)

1. **ESPN snapshot layer (F3) — DONE, redesigned per survey.** Key finding:
   `league.teams` comes free with League construction; the real duplicate
   network cost was 5-6 `free_agents(size=2000)` pulls + ~4 per-player
   injury-HTTP sweeps per night. Implementation (env-gated, fail-open):
   - `plv_clone/espn.py::_wrap_free_agents_with_snapshot` — when
     `PLV_ESPN_SNAPSHOT=1`, the plain big-pool pull is served from a
     short-TTL pickle (`data/research/espn_snapshot/`, gitignored). One
     seam covers every consumer because all League handles come from the
     lru-cached `_get_league()` factory. Verified live: disk hit 0.017s vs
     1.12s live, Player attrs intact through pickle.
   - `league_state.injury_details` — accumulating per-player JSON cache with
     TTL + `days_until_return` recomputed from cached `return_date` at read
     time (verified: date round-trips as a real `date`). All refresh-path
     injury consumers route through this one method (survey).
   - `refresh_dashboards.main()` sets `PLV_ESPN_SNAPSHOT=1` (+TTL 240) for
     all child steps; interactive/skill use never sets it → stays live.
2. **Volume-pipeline dedup + team-games cache (D1/W4) — DONE.** New
   `scripts/xfp/lib/volume_model.py` (team-games + catcher-flags scans with
   PER-YEAR mtime-guarded parquet caches, attach, make_pipe, cross_year_eval,
   tercile_calibration, check_gates — bodies extracted verbatim,
   parametrized). Hitter + SP pipelines slimmed to config + prepare/eligible/
   main; RP keeps its by-design-different scan/gates but shares the eval
   primitives. The 7 immutable historical parquets are no longer re-read
   nightly (~2.5 GB/night IO removed). **Golden check: all three projection
   CSVs byte-IDENTICAL before/after.**
3. **Year-2026 rollover (R2/R3) — filters + dynamic scans DONE.**
   `proj_year = int(rolling['year'].max())` replaces every `== 2026` in
   rh3/rp3/rprs2 + the three volume pipelines; statcast scan ranges are now
   `range(2018, current_year+1)`; rprs2's counting-stats path follows
   proj_year. Execution-tested: all three models run clean, row counts match
   production, rprs2 join match rate 100%. REMAINING (offseason): the
   `*_2018_2026.csv` substrate FILENAMES are a cross-builder naming
   convention — parameterizing them needs a coordinated pass through the
   rolling/multiyr builders (single-constant change per file at rollover).
4. **FP-formula consolidation (H2/§5) — production paths DONE, bit-safely.**
   Because float addition is non-associative, only sites whose operand order
   matches `scoring.pitcher_fp` exactly were swapped to the helper
   (bit-identical by construction): `build_rolling_pitchers`,
   `build_sp_multiyr`, `build_multiyr_fp_store`, `build_weekly_fp_substrate`
   (runs-as-ER proxy documented). `rprs2.py` (RP-order site) swapped and
   **A/B-verified: projections CSV identical**. DEFERRED (order-mismatched,
   would need per-file re-verification): `build_rolling_relievers:290`,
   `build_relievers_multiyr:46/193`, `build_subseason_variance_bands:293`,
   `monitor_drift:175` + its local parse_ip (different None semantics than
   `scoring._parse_ip` — do not blind-swap). CORRECTION to the original
   finding: `lib/boom_bust._ip_to_float` is NOT wrong — its docstring
   describes the naive-float bug it deliberately avoids.

## Backlog (ranked; each verified against source, none started)

### High impact
5. **Model-scaffolding dedup (D2).** `cross_year_eval` / `train_final` /
   `_fit_fingerprint` / warm-load / pred-bucket loops copy-pasted across
   rh3/rp3/rprs2 → engine.py. Load-bearing: ship behind byte-identical
   golden-projection tests.
6. **sys.path codemod + package `lib/` (Finding 1).** plv_clone is already
   pip-installed editable, so all 103 `src`-adding inserts are dead weight;
   packaging `scripts/xfp/lib` (move to `src/plv_clone/lib/` or add second
   wheel package) kills the remaining ~150. 246/420 scripts currently do path
   surgery in ~10 spellings.

### Medium
7. **Constants module (Finding 4).** `'New York Ligers'` ×66, output-path
   strings ×118, season-year literals ×1220. `league_config.py` bills itself
   as the config seam but omits exactly team name / league id / season year.
   Add + codemod the team-name and path literals first; year literals need
   triage (many are legitimate historical ranges).
8. **ESPN retry/backoff (M3).** Zero retry anywhere in `espn.py`/
   `espn_connector.py`; a transient 5xx aborts an engine or refresh step.
   Wrap `_get_league()` + fetchers in exponential backoff. Also: engines
   calling raw `espn_connector` bypass `league_state.py`'s 300s TTL cache.
9. **Name-resolution adoption sweep (M1/M2).** ~15 inline "Last, First" flips
   and ~13 engines doing bare StatsAPI `people/search` (bypassing
   KNOWN_COLLISIONS). Route through `name_match._normalize` / `join_key` /
   `resolve_id`.
10. **Tests for the untested lens layer (Finding 3).** `lib/boom_stack.py`
    (612 ln), `lib/hitter_boom_stack.py` (696 ln), `lib/il_return_flag.py`
    (IL-join adjacent!), `shadow_scout`, `recform_hot`, `cli.py`.
11. **Split `build_triangulate_dashboard.py`** (1,309 ln): CSS/JS blobs, card
    rendering (~450 ln), FA rail, SVG traj chart (duplicated vs the profiles
    page's JS chart — extract one spec), profile-link map (re-implements
    normalize + re-reads CSVs `cached_data` already caches).
12. **`cached_data.py` lru_cache has no mtime guard (M5)** — long-lived
    processes serve pre-refresh CSVs; copy the `(mtime,size)` key from
    `disk_cache.py`.
13. **gf-bridge silent drop counter (R4)** — `build_statcast_gf_bridge.py:104`
    swallows all mapping errors; count + threshold-warn.
14. **Match-rate prints on remaining joins (R5)** — rh3 master-hitter merge
    (position→UTIL collapse), rp3 schedule merge, volume team-map fallback.

### Low / hygiene
15. **Archive ~132 unreferenced research scripts** from `scripts/xfp/` top
    level (validate_*, xfp_vN locks, *_backtest, _-prefixed scratch) into a
    gitignored research tree (existing convention). Verify each against
    CI/cron first; a few `validate_*` are invoked ad-hoc by /validate-feature.
16. **Renumber refresh step labels** (two "3.7"s, two "4.11"s, order ≠ label
    order) + explicit timeouts on publish-critical steps now on the 900s
    default (1, 3, 4, 5/6).
17. **Idle-step gating** — 3.6/3.7-synthetic/4.11 spawn subprocess+pandas
    nightly just to no-op; add driver-level mtime gates like 1.95's.
18. **Merge `lib/period_math.py` (1 importer) into `period_meta`/`cap_math`;**
    verify orphan-looking engines (`monitor_drift.py` etc.) before archiving.
19. **Data litter**: `data/outputs/_*` scratch CSVs read by nothing;
    fangraphs yearly CSVs unreferenced by code; `xfp_rp3_projections.csv.bak`.
20. **Archetype builders dedup (D3/D4)** — `_trajectory_metrics`/`_traj_flag`/
    `build_career_panel` identical across sp/hitter builders → archetype_engine;
    IL-asof idiom triplicated → `lib/il_return_flag` helper.
21. **Vectorize sigma `iterrows` + `.apply` tag loops (W2/W3)** in all three
    models (small frames; consistency, not speed).
22. **Per-row try/except in `run_conviction_scan.py` / `sp_stuff_model.py`
    (L4)** — currently one bad row aborts the whole scan; adopt the
    collect_cards skip-and-warn pattern.
23. **`sys.stdout.reconfigure` guard (L3)** on user-invokable engines that
    print unicode (`run_roster_audit.py` etc.) for bare-console runs.

Parallelization note (F7): archetype panels 2.6/2.7/2.8, volume 4.09/b/c, and
the archival appends are mutually independent — natural candidates if the
driver ever grows a job-graph/`--jobs` mode. Dependency chains that must NOT
be reordered: 1.6→2, 1.9/1.95→2, 2→2a→4, 2.9→4/4.45, 4.72a→b→c→4.7.

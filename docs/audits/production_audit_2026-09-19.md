# Production audit — 2026-09-19 (xFP decision layer trust pass)

Scope: the ACTIVE fantasy xFP decision layer only — cached projection CSVs
→ `run_roster_audit.py` / `run_weekly_optimizer.py` (+ `lib/leverage_engine.py`)
/ `build_matchup_dashboard.py` / `plv_clone.matchup_projection`. The dormant
PLV/Process+ package (ADR-0009) was not touched. Offseason constraints held:
no live ESPN/MLB query, no refresh/publish, no roster artifact published,
no dependency added. Every repair below was reproduced OFFLINE with a
synthetic fixture before the code changed, and each fix ships with the test
that reproduced it.

Method: four read-only traces (canonical player IDs · projection as-of and
staleness · missingness · chronological boundaries), each producing
`file:line` claims; the main session verified the top claims against the
source and against the on-disk 2026-08-31 artifacts, then repaired the
subset that (a) changes a decision output and (b) reproduces offline.
Everything else is filed below as OPEN with a repro sketch — nothing was
"fixed" on trust.

Baseline before edits (this checkout): `python scripts/ci/smoke.py` → 211
passed, 1 skipped. Full suite and post-fix counts: see §5.

## 1. Data-path map (what was traced)

| Stage | Identity key | As-of signal | Missing → ? |
|---|---|---|---|
| `xfp_rh3_projections.csv` | `batter` (mlbam) + `player_name` + `team` | file mtime only (no built_at column) | row absent |
| `xfp_rp3_projections.csv` | `pitcher` (mlbam) + `player_name` ("Last, First"), `data_quality_tag` | mtime; `_il_fixed` shim guarded 24h *relative* to canonical | row absent / `marcel_il` |
| `xfp_rprs2_projections.csv` | `pitcher` + `name_api`; sigma from p25/p75 | mtime | row absent |
| ESPN lineup objects | `name`, `position`, `proTeam`, `injuryStatus`, `lineup_slot`; **no espn→mlbam crosswalk** | live | — |
| `build_matchup_dashboard.load_projections` | name-keyed maps + `_RH3_BY_BATTER` (id) + `rp3_by_mlbam` (**was name-derived**, now id) | — | `or 0` (**was NaN-blind**) |
| `project_player` | `_resolve_pitcher_mlbam` (collision-gated) / `resolve_id` for hitters in `KNOWN_COLLISIONS` | `today` = ET; window from `resolve_period_meta` | SP: `≈ est` badge; H/RP: **silent 0 → now `⚠ no proj`** |
| `leverage_engine.build_state` | `resolve_player_mlbam` (**hitters were not collision-gated**) → draw key `id:` / `nm:` | `_today_et()`; banked provisional flag | H/RP with no mlbam or fp≤0 **dropped from D silently** |
| `run_weekly_optimizer` | candidate mlbam via resolvers + API fallback (loud) | `generated_at` naive local | drop of a player absent from D **scored 0.00pp** |
| `run_roster_audit` | `safe_lookup` (refuse-to-guess) | mtime age, **label was a literal "fresh"** | NaN `proj` sorted last (correct) |

Fact checks against the 2026-08-31 artifacts (read with `nrows`, no bulk
Read): rh3 has one true same-name pair (Max Muncy 571970 LAD / 691777 ATH);
rp3 has 0 duplicate names but 16 of 376 pitchers absent from the frozen
`sp_multiyr_2015_2025.csv` name map (all `data_driven_thin` 2026 arms plus
Logan Allen 671106 `marcel_il`); every CSV mtime in this checkout is the
clone time, not the build time (`build_meta_2026.json` says
`built_at 2026-08-28T21:39Z`).

## 2. Repaired (each: defect → reproduction → fix → pin)

R1 **Roster audit labelled every projection "fresh"** — `run_roster_audit.py`
printed the literal suffix `— fresh.` after the mtime ages regardless of
value. Also CWD-relative CSV paths. Fix: `PROJECTION_MAX_AGE_DAYS = 2`,
`projection_age_note(ages)` names STALE/MISSING models; paths on ROOT.
Pin: `tests/test_roster_audit_projection_age.py`.

R2 **`rp3_by_mlbam` built by name through a frozen 2015-2025 cache** —
`build_matchup_dashboard.load_projections` walked `sp_multiyr_2015_2025.csv`
deduped by name and joined back onto the name-keyed `rp3_map`: 16/376 rp3
pitchers unreachable by id (opposing-SP factor fell back to team index) and
the `KNOWN_PITCHER_COLLISIONS` branch that reads this map "to be safe"
could get the other pitcher's row. Fix: build from rp3's own `pitcher`
column over the full frame; the cache read is gone.
Pin: `tests/test_matchup_rp3_by_mlbam_identity.py`.

R3 **NaN-blind matchup factors** — `matchup_projection.sp_opp_factor` /
`hitter_opp_factor` tested `if not x` / `is not None`; NaN passed, `1/NaN`
went through `_clamp` which returns the UPPER bound for NaN → a missing
team index / opposing-SP rate became a +20% / +30% boost. Fix: `_present()`
guard; NaN reads as missing (neutral / team-index fallback).
Pin: `tests/test_matchup_nan_inputs.py`.

R4 **NaN poisons the Monte Carlo** — `leverage_engine._blend_draws` passed
a NaN mean/sigma into `rng.normal`; `pwin` scored every NaN trial as a
LOSS (`nan > x` is False both ways), so one NaN-rate player dragged P(win)
toward 0 and "drop him" ranked first. Fix: non-finite mean → missing path,
non-finite sigma → floor; `pwin` raises on non-finite totals.
Pin: `tests/test_leverage_nan_guard.py`.

R5 **Unmatched drop scored as free (0.00pp)** — `_resolve_keys` returned ∅
for a zero-match name (raised only on ambiguity) and the SP partition
matched nothing, so `delta_pwin(drop=[X])` for any player absent from D
(no projection, unresolved id) was the unchanged baseline. Fix:
`delta_pwin` raises `KeyError` when a drop lands in no bucket;
`run_weekly_optimizer` filters such players out of the droppable set
(`scoreable_in_D`), prints them as UNSCOREABLE and writes
`unscoreable_drops` into `weekly_optimizer.json`.
Pins: `tests/test_leverage_unmatched_drop.py`, `tests/test_optimizer_unscoreable.py`.

R6 **ESPN schedule dates bucketed in the process-local zone** —
`fetch_espn_week_schedule` used `date.fromtimestamp(ms/1000)`; on the UTC
`live-matchup` runner every ≥20:00 ET first pitch landed on tomorrow: the
period's last night games fell past `week_end`, and the (team, date,
ordinal) key stopped matching `fetch_completed_games` (ET block dates).
Fix: `espn_game_date()` converts in America/New_York.
Pin: `tests/test_espn_schedule_et_dates.py` (forces `TZ=UTC`).

R7 **A finalized SP start was re-projected and double-consumed a cap slot** —
the hitter/RP branch of `project_player` subtracts completed games; the SP
branch filtered by date only. Fix: `drop_completed_starts()` (drops a start
only when every game of that team-date is final, so a split-DH game-2
start survives game-1 final).
Pin: `tests/test_sp_completed_start_dropped.py`.

R8 **matchup.html capped the today-forward projection at the FULL period
cap** — `apply_sp_cap(my_proj, cap=sp_cap)` ignored banked starts (12/20
banked → 20 more allowed to score, while the cap panel said 12/20).
Fix: `remaining_cap(period_cap, banked)` for both sides (None banked keeps
the full cap, the pre-fix behaviour, labelled by `render_cap_status`).
Pin: `tests/test_matchup_cap_uses_remaining.py` (+ AST guard on every
`apply_sp_cap` call).

R9 **Missing ≠ zero for hitters/RPs** — a hitter with no rh3 row (or RP
with no rprs2 row) rendered exactly like a 60-day-IL player. Fix: `⚠ no
proj` badge (IL zero stays unbadged). `_num_or()` makes the projection maps
NaN-safe (`r.get(...) or 0` did not default NaN).
Pin: `tests/test_matchup_missing_is_not_zero.py`.

R10 **One NaN `pitcher` cell emptied the whole `data_quality_tag` map** —
`astype(int)` inside a bare `except: {}` (the marcel_il gotcha-#1 guard).
Fix: `load_dq_by_mlbam()` skips bad rows. Pin: `tests/test_leverage_dq_map.py`.

R11 **Engine hitter resolver had no collision guard** — `resolve_player_mlbam`
gated pitchers only; both Max Muncys resolved to the first-loaded id, which
keys the MC draws and the boxscore `emp_series` join. Fix: `KNOWN_COLLISIONS`
hitters go through `resolve_id(kind='batter', team, position)`.
Pin: `tests/test_leverage_hitter_collision.py`.

R12 **Period resolver defaulted `today` to the UTC clock** —
`period_meta.resolve_period_meta` used `date.today()` when a caller omitted
`today=` (`run_roster_audit`, `lineup_optimizer`, `build_period_xfp_board`,
`weekly_cap_check --period`): from 20:00 ET Sunday the window rolled a
period early. Fix at the owner: `today_et()` default (covers every caller).
Pin: `tests/test_period_meta_et_default.py`.

R13 **Roster audit: `int(NaN)` crash and DAY_TO_DAY treated as OUT** —
`int(days_until_return)` raised when ESPN had no returnDate; healthy-SP
count and drop pools filtered on `~injured`, which ESPN sets for DTD too
(don't-do #2). Fix: `fmt_days()`, `out_mask()` (IL slot or
`IL_STATES_STRICT`), forward transitions keyed on `effective_role`, summary
counts the "no return date" players instead of silently dropping them.
Pin: `tests/test_roster_audit_out_mask.py`.

Multifile edit scope (code): `scripts/xfp/build_matchup_dashboard.py`,
`scripts/xfp/lib/leverage_engine.py`, `scripts/xfp/lib/period_meta.py`,
`scripts/xfp/run_weekly_optimizer.py`, `scripts/xfp/run_roster_audit.py`,
`src/plv_clone/matchup_projection.py`, new `scripts/ci/render_offline_scenarios.py`.
No change to `src/plv_clone/models/xfp/*`, no projection value re-tuned,
no held-out outcome used.

## 3. Offline rendered scenarios (review evidence)

`python scripts/ci/render_offline_scenarios.py` renders the matchup team
table, playoff-odds card, roster-audit header and optimizer payload through
the PRODUCTION renderers over synthetic fixtures in three states —
`docs/audits/offline_scenarios_2026-09-19/{complete,stale,missing}.html`.
No real roster data appears (every name is synthetic). Pinned by
`tests/test_offline_scenarios_render.py`: complete carries no marker; stale
says `STALE (>2d): rp3 41d` and the playoff card refuses a 6-period-old
payload; missing shows `⚠ no proj` / `≈ est` / `MISSING: rp3` /
`season_sim.json missing` / `unscoreable_drops: Beta Bat (H), Closer Arm (RP)`.

## 4. OPEN — verified in source, not repaired here (each with a repro sketch)

Ranked by decision impact. None needs a network to reproduce unless marked.

- O1 `weekly_cap_check._project_starts` returns ONLY confirmed dates once any
  probable exists (early return) → a Monday-confirmed SP projects 1 start,
  never his Saturday turn → systematic under-count at the cap. Also slides
  cadence onto league-wide game days, not the pitcher's team's. Repro: the
  existing `tests/test_weekly_cap_check.py` fixtures + one confirmed Monday.
- O2 `fetch_espn_week_schedule` never populates `opp_probable_id` (docstring
  says "filled later"; `build_sp_starts_by_pitcher` only reads it), so on
  the primary ESPN path the hitter opposing-SP factor and platoon adjuster
  always fall back to the team index. Repro: assert on the ESPN-path dict.
  Fix sketch: hydrate from `fetch_schedules_by_team` (the engine already
  fetches `mlb_sched_all`).
- O3 Two live `SEASON_END` constants (`build_matchup_dashboard` 09-28 vs
  `build_xfp_boards` 09-20 → decision console RP axes read 0 for the final
  week). Repro: import both and compare.
- O4 `run_season_sim.py:347` uses a flat cap of 10 for every simulated week
  (2-week playoff rounds are 20; ASG 16) → biases `title_equity` weights.
- O5 `mlb_stats.resolve_mlbam` prefers any PITCHER among the first five
  people matches, else `people[0]` — reached for HITTERS via the API
  fallback in three call sites. Needs a mocked-HTTP fixture (network path).
- O6 `render_snapshot_diff` reads `tail(2)` of `predictions_history.csv`,
  which holds a baseline AND a shadow row per build → "since last snapshot"
  is the adjuster-chain delta, not a time delta. `render_accuracy_history`
  never filters `model_version`.
- O7 `render_power_rankings`: `SP_REM = 24` calendar-blind; `.fillna(0)` /
  `.get(nk, 0)` count unmatched names as zero contributors; bypasses
  `ProjectionStore`.
- O8 `ProjectionStore.rp3(live_il=True)` staleness is RELATIVE (shim vs
  canonical mtime) with no absolute bound, and mtime resets on checkout —
  in this clone every CSV reads 0d old while the data is from 2026-08-28.
  Recommendation: have `refresh_dashboards.py` write a
  `xfp_projections_meta.json {built_at, data_through}` sidecar (no CSV
  schema change) and have consumers prefer it over mtime.
- O9 `days_remaining` means "after today" in the dashboard and "including
  today" in the engine (`roster_rules.check_swap` sizes capacity from the
  latter).
- O10 `counterfactual.FIRST_PITCH_CUTOFF_HOUR = 13` is evaluated on a naive
  clock that is UTC in the cloud container (documented as ET); moves made
  09:00–13:00 ET shift a day. Same class: `freshness.ensure_fresh`'s
  "yesterday" and `build_index_dashboard`'s decision-console "today" check.
- O11 `PUBLISH_GATED` gates on the model rebuild only; a stale il-fix, FG,
  team-override or park cache still publishes under a fresh "Generated"
  stamp; matchup.html has no "data through" stamp (index.html does).
- O12 `mlb_stats.predict_rotation_starts` marks a team-date "taken" only by
  ROSTERED confirmed probables, so a prediction can land on a game already
  assigned to an unrostered starter.
- O13 `punt_detector.py` hardcodes 6/8/10 thresholds; `build_period_xfp_board`
  falls back to a literal 10.
- O14 `run_roster_audit._rp3_mlbam` keys by `.lower().strip()` (no accent /
  suffix fold) — display-only (`last start` suffix disappears).

## 5. Verification

- `python scripts/ci/smoke.py` — PASS (see §5a for the count after edits).
- `python scripts/ci/run_summary.py -- python -m pytest` — see §5a.
- ruff on the diff: every modified production file has the same or fewer
  findings than at HEAD (`build_matchup_dashboard` 115→114, `leverage_engine`
  28→28, `run_roster_audit` 16→16, `run_weekly_optimizer` 32→30,
  `period_meta` 12→11, `matchup_projection` 20→20); all new files are clean.
- NOT run (needs a live league read, prohibited this pass): `/matchup-audit`
  after the `build_matchup_dashboard.py` change (CLAUDE.md "before you
  finish" #3). Astra/Josh: run it on the first 2027 build before trusting
  the page. `golden_run.py` was not applicable — no model/pipeline output
  was refactored behavior-preservingly; every change here is a deliberate
  behaviour change with its own pin.

### 5a. Counts and commits

- Code + tests + rendered scenarios: commit `77fedb7fb9a52b92953710bef300cf25997d4f16`
  (branch `claude/nifty-curie-v7r6kd`). This audit, the football contract
  and the HANDOFF update: the commit that follows it on the same branch.
- `python scripts/ci/smoke.py` after edits: 211 passed, 1 skipped (PASS).
- `python scripts/ci/run_summary.py -- python -m pytest` after edits:
  **2453 passed, 68 skipped (all data-gated: substrate parquet / PowerShell /
  xfp-model sibling absent in this checkout), 2 deselected, 1 xfailed**
  (the known stale-PL-cache xfail) in 81s — log `.cache/test-logs/20260919T010719Z.log`.
  Before edits the same suite: 2447 passed + the new tests' files absent.
- Test census (`test_testqual_data_gating`): the new tests carry NO
  presence/import guards (hard imports on tracked source), so the declared
  bound (72 files / 128 sites) is unchanged.

## 6. Review repairs (owner closeout, 2026-09-19)

Astra independently ran the 15 changed test files at `67aa621` via
`run_summary.py`: 54 passed. Three source-probe findings from that review,
repaired in the closeout commit on the same branch (targeted regressions +
smoke rerun; no further scope):

- **R3b `_present` covered Python-float NaN only** — `sp_opp_factor(np.float32(nan))`
  still returned 1.2, and ±inf passed as present. Now present iff the value
  converts to a FINITE float (any numeric type). Valid values and clamps are
  unchanged; controls for np.float32/64 NaN and ±inf, plus numpy-typed valid
  inputs, in `tests/test_matchup_nan_inputs.py`.
- **R11b collision fall-through** — `resolve_player_mlbam` called the
  fail-closed `resolve_id` for a `KNOWN_COLLISIONS` hitter but, on `None`
  (missing/unknown team), fell through to the first-loaded name cache / API,
  undoing the guarantee. A known collision that cannot be settled now stays
  `None`. Test forbids the fallback calls and covers missing/empty/unknown
  team alongside both valid Muncys (`tests/test_leverage_hitter_collision.py`).
- **R10b `load_dq_by_mlbam` truncation** — `int(123.7)` filed a malformed id
  under 123 (another person). Only finite, positive, integer-valued ids are
  accepted; fractional/negative/zero/inf are rejected
  (`tests/test_leverage_dq_map.py`).

Owner direction recorded: football (Gridiron) is the only ongoing
development repo; this PR is the closeout of the plv_clone ID/missingness
milestone. Astra to review; nothing further is planned here.

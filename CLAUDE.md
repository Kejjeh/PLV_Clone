# plv_clone — agent operating guide

Fantasy-baseball projection models + decision tooling for the **BrownU** ESPN
league (8-team H2H points; Josh's team: **New York Ligers**). The active
system is the xFP layer (`src/plv_clone/` package + `scripts/xfp/` engines);
the repo's namesake PLV/Process+ clone is **dormant** (ADR-0009). State:
production-stable, refreshed nightly by self-hosted GitHub Actions.
Orientation: `docs/ARCHITECTURE.md` (map) · `docs/DECISIONS.md` (settled —
don't re-litigate) · `HANDOFF.md` (state of play, next steps).

## Commands (verified 2026-09-01)

```bash
pip install -e ".[dev]"                               # install; Python 3.11+ (runs on 3.13)
python scripts/ci/smoke.py                            # fast sanity check — run after ANY change
python scripts/ci/run_summary.py -- python -m pytest  # full suite — NEVER raw pytest (log → .cache/test-logs/)
python -m ruff check src/ tests/                      # lint — 186 pre-existing findings; lint only YOUR diff, never mass-fix
python scripts/xfp/refresh_dashboards.py              # nightly full refresh — PUBLISHES to GitHub Pages; CI runs it daily 11:00 UTC, don't run casually
python -X utf8 scripts/xfp/run_roster_audit.py        # roster audit report (live ESPN read)
```

ESPN auth: env vars `ESPN_LEAGUE_ID` / `ESPN_YEAR` / `ESPN_SWID` / `ESPN_S2`,
loaded from the gitignored `.env`. Never write credential values into a file.

## Architecture map (detail: docs/ARCHITECTURE.md)

- `src/plv_clone/` — the package = production boundary. Single-source modules
  (never duplicate): `espn.py` auth · `paths.py` roots · `config.py` settings
  · `league_config.py` SEASON_YEAR · `cap_math.py` SP-cap math ·
  `league_state.py` read-side league rules · `projections.py` PROJECTIONS
  loader · `models/xfp/{rh3,rp3,rprs2}.py` the production models.
- `scripts/xfp/` — engines + ~90 skill drivers; `scripts/xfp/lib/` is the
  real library: `leverage_engine.py` (the ONE P(win) MC engine),
  `dpwin_history.py`, `title_equity.py`, `roster_rules.py`, `pitcher_role.py`.
- `scripts/xfp/build_matchup_dashboard.py` — 4.2k-line dashboard builder AND
  imported library; treat its public names as API.
- `scripts/ci/` — `run_summary.py` (test-log compactor), `smoke.py`,
  `golden_run.py` (A/B verifier for behavior-preserving refactors).
- `xfp-model/` — nested public repo → GitHub Pages; `/safe-commit` checks it.
- Exploration: `.codegraph/` is live — spawn an Explore agent with the block
  in `docs/memory/codegraph.md`; main session uses only codegraph_search/
  callers/callees/impact/node. Don't re-derive with grep.

## League constants and models

- Roster 13 H + 9 P active, 4 BE, 3 IL. **SP-start cap is period-aware —
  never hardcode 10**: resolve via `cap_math.sp_cap_for_period(period,
  weeks=weeks)`; banked count from ESPN statId-33. RP slots: cap 4 AND
  **floor 4** (RP drops only RP-for-RP). Full: `docs/memory/league_rules.md`.
- Scoring: hitter `R+TB+RBI+BB+HBP+SB-K`; SP `K+IP*3.3-H-2*ER-BB-HBP`;
  RP adds `+5*SV+3*HLD`.
- Validated models (others are research-stage): hitters `xfp_rh3` · SP
  `xfp_rp3` · **RP `xfp_rprs2` (never rp3)** — CSVs in `data/outputs/`, load
  via `PROJECTIONS`. **RoS totals = rate × volume** (volume CSVs supply
  PA/team-game and GS/team-game). Full: `docs/memory/validated_models.md`.
- P(win) decision layer: roster moves are ΔP(win)-denominated, not
  expected-FP. Run `run_weekly_optimizer.py` or `/matchup-leverage` BEFORE
  executing any move. Rule 13: this layer never touches rh3/rp3/rprs2.
  Full: `docs/memory/pwin_layer.md`.

## Fast-path gotchas (full text + numbers: docs/memory/gotchas.md)

1. rp3 `data_quality_tag=marcel_il` = suppressed Marcel prior, not a read — rank those by Stuff+ `proj_ros_fp`; trust rp3 only on `data_driven_*`.
2. Windows console: prefix inline python with `PYTHONIOENCODING=utf-8 PYTHONUTF8=1` (or `python -X utf8`).
3. `get_all_teams()` is a flat DataFrame of ~230 rostered players, not team objects; match names two-pass (full normalized, then last+first-initial), never last-only.
4. Verify "dropped/added" LIVE via `get_all_teams()` — BrownU drops sit on ~24-48h waivers.
5. Don't fan out agents for a single-player question — one inline script; fan out only for broad FA-pool scans.
6. `fetch_schedules_by_team(team_ids, start, end)` from build_matchup_dashboard has 5 consumers — pinned by `tests/test_schedule_fetch_contract.py`.
7. BE slot = active for Josh; only IL/IR slots and `injuryStatus` in the IL states zero a player — never say a bench player "won't score."
8. Never bucket pitchers by ESPN `.position` — use `detect_pitcher_role()` (`scripts/xfp/lib/pitcher_role.py`).
9. Data is through YESTERDAY (two bridges erase the Statcast lag) — don't caveat "models lag a day."
10. PL-cache staleness is cadence-aware (SP Mon · closers ~Tue · hitters ~Wed · streamers 2-3d), not a flat 7 days.
11. SP trajectory/recency-trend is NON-PREDICTIVE — use shipped `floor_adj_xfp`/`floor_flag` for downside, `stuff_cmd_tag` for decline type; both context-only.
12. Hitters: anchor season LEVEL, L21d for recent form, L7 only for bat speed; in-season rate-metric DELTAS add ~0 (family CLOSED); bat-speed trajectory never moves a rank.
13. Model forward-calibration is GOOD — no intercept, no shading up, no reduced shrinkage; the conservatism is context-only.
14. In-season "different player now" is CLOSED (~89% sampling noise); event-given split z>1.83, searched split SP 2.58 / hitters 2.79; nothing regime-derived moves rh3/rp3/rprs2.
15. Read the OUTCOME for hitters, the PROCESS for pitchers (SP K% beats his own FP level); walks invert — the walk belongs to the batter.
16. TBD probable ≠ no start — read the rotation ORDER; median turn is stale.

## Don't do these (full text + canonical cases: docs/memory/dont_do.md)

1. No feature into rh3/rp3/rprs2 without `/validate-feature`; the Rule 9 baseline must include ALL existing production features.
2. Never count IL slots from `injured==True` — use `lineup_slot=='IL'`.
3. Never rank/filter FAs by `n_pos_flags` or the composite rolling-trend flag (validated noise).
4. "Best available" means FAs only (`get_free_agents()`), never players on other rosters.
5. Never commit `*.parquet`, `*.pkl`, `*.bak` — gitignored.
6. Pool scans use `league.free_agents(size=2000)` + manual filter, never per-position `size=300`.
7. Never conclude a player is rostered/unrostered without `get_all_teams()` — PL rank and percent_owned are not substitutes.
8. Never recommend a hitter drop without xwOBA L21d vs prior year AND xwOBACON YoY.
9. Never trust matchup.html SP projection blindly — run `/matchup-audit` after any build_matchup_dashboard change.
10. Player IDs via `resolve_batter_id`/`resolve_pitcher_id` with team/role — NEVER name-substring + `.iloc[0]`.
11. Never label a player "yours" without a live `get_my_roster_with_injuries()` + `my_tag()`.
12. Never headline a single lens or flip a verdict across turns — full lens stack, and a verdict changes only on new data or corrected error, stated.
13. Lens stack is conviction/conflict surfacing only, never additive lift — the headline number stays rh3/rp3/rprs2.
14. No veteran Stuff+ "buy-low" headline without the decline cross-check (≥2 of archetype-YoY-slope / sustainability / comp-T+1 declining → headline DECLINING).
15. Never drop on a "declining" read from a single window — require ≥2 non-overlapping windows.
16. Short-hold FA churn (<48h) gets re-scanned 3+ weeks later (signal P in `/fa-monitor`).
17. Every study: never compare r across frames, and assert `1/(B+1) < q/M` before believing a BH-FDR result.
18. Never ship a guard/fix without sweeping sibling call sites; prefer discovery over enumeration in guards.

## Before you finish any task

1. `python scripts/ci/smoke.py` — must pass (<1 min, offline).
2. Touched code? `python scripts/ci/run_summary.py -- python -m pytest`.
3. Touched `build_matchup_dashboard.py`? Also run `/matchup-audit`.
4. Behavior-preserving refactor of model/pipeline code? Referee it with
   `scripts/ci/golden_run.py` (phase A before edits, B after).
5. Committing? Use `/safe-commit` (checks the xfp-model sibling too).
6. Never leave a new skill dir out of `.claude/skills/SKILL_REGISTRY.md`.

## Model routing (Sonnet vs Opus)

**Sonnet-safe**: skill-driver runs and reports, roster/FA questions via
existing skills, doc updates, adding tests that pin current behavior, data
refresh reruns, dashboard cosmetics, fixing a failing test whose cause is a
path/import/fixture.
**Escalate to Opus**: anything inside `src/plv_clone/models/xfp/` or
`scripts/xfp/lib/leverage_engine.py`; statistical methodology or validation
protocol; changes crossing output-schema contracts; `refresh_dashboards.py`
step logic; anything `/validate-feature`- or `golden_run`-shaped.
**Either model**: when a numbered rule above conflicts with your plan, the
rule wins; if you believe the rule is wrong, stop and ask Josh.

## Context hygiene (cheap-model survival rules)

- Never Read/Grep bulk data: `data/raw/`, `data/processed/`,
  `data/research/xfp_cache/`, `*.parquet`, `*.pkl` (blocked; see
  `.claudeignore`). Inspect via `python -c` with `nrows=`.
- Wrap test/build commands in `run_summary.py` — raw pytest dumps thousands
  of lines.
- Root `scratchpad_*` / `scratch_*` files are untracked one-offs — ignore.
- CLAUDE.md is line-budgeted (`tests/test_claude_md_budget.py`): new rule =
  one line here + full text in `docs/memory/`; retire in place, never
  renumber.
- claude-mem worker (port 37778) auto-restarts via hook; if "worker
  unreachable", just send any message (`docs/memory/claude_mem_worker.md`).

## Skills

Guards before any claim: `/roster-verify` (is-mine) · `/player-id-resolve` ·
`/pitcher-role`. Domain masters: `/daily-rhythm` · `/moves` ·
`/player-verdict` · `/all-boards` · `/form-check`. Routing table:
`docs/memory/skills_cheatsheet.md`; enforced catalog:
`.claude/skills/SKILL_REGISTRY.md`. Josh's host memory dir under his Windows
user profile is NOT reachable from Linux containers — cite via
`docs/memory/host_memory_index.md`, don't read.

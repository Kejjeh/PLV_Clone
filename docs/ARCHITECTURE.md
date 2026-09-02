# Architecture

One repo, two subsystems sharing `data/` and `tests/`:

1. **Legacy PLV/Process+ clone** (`src/plv_clone/models/plv_model.py`,
   `pipelines/`, the `plv` CLI) — the repo's namesake, **dormant since
   2026-04** (ADR-0009). One live edge: `build_exports.py` writes
   `data/outputs/master_hitter_2026.csv`, which the active layer reads for
   hitter positions. Don't work here unless asked.
2. **Fantasy xFP layer** (everything else) — the active system. Models,
   dashboards, and a decision layer for the BrownU ESPN league.

## Data flow (active layer)

```
MLB Statcast (pybaseball)      ESPN league API (espn-api)     MLB Stats API
        |                              |                           |
refresh_xfp_statcast.py        src/plv_clone/espn.py        src/plv_clone/mlb_stats.py
        |                      (auth; league_state reads)    (probables, mlbam ids)
        v                              |                           |
data/research/xfp_cache/*.csv          |                           |
        |                              v                           v
  RATE models                    +--------------------------------------+
  rh3 (hitters) rp3 (SP)         |  scripts/xfp/build_matchup_dashboard |
  rprs2 (RP)                     |  run_weekly_optimizer (ΔP(win))      |
  src/plv_clone/models/xfp/      |  run_roster_audit, live_monitor,     |
        +                        |  ~90 skill drivers in scripts/xfp/   |
  VOLUME models (PA/g, GS)       +--------------------------------------+
        |                              |
        v                              v
data/outputs/xfp_*_projections.csv   data/outputs/*.html
        \______________________________/
                       |
        scripts/xfp/refresh_dashboards.py   (nightly driver, ~40 steps)
                       |
                       v
        xfp-model/docs/  →  git push  →  GitHub Pages
        (nested sibling repo, gitignored here)
```

**RoS totals = rate × volume.** Rate models are per-PA / per-start;
`xfp_volume_projections.csv` / `xfp_sp_volume_projections.csv` supply the
volume. Consumers multiply; never hand-multiply by flat constants.

## Key abstractions (why the structure is this way)

- **`src/plv_clone/` is the package = the production boundary.** Models in
  `src/plv_clone/models/xfp/` (rh3.py, rp3.py, rprs2.py + engine.py toolkit)
  are production; `scripts/xfp/` holds engines, skill drivers, and research.
  The package boundary is the authoritative "is this production?" test
  (CONTEXT.md).
- **Single-source modules** — never duplicate these concerns:
  `espn.py` (auth + cached `_get_league`), `paths.py` (ROOT/DATA/OUTPUTS,
  `PLV_ROOT` override), `config.py` (pydantic-settings, `PLV_` prefix),
  `league_config.py` (`SEASON_YEAR`), `cap_math.py` (SP-cap arithmetic,
  pure over injected data — ADR-0002), `league_state.py` (read-side league
  rules; deliberately has no `injured_players()` — ADR-0004),
  `projections.py` (`PROJECTIONS.rh3()/rp3()/rprs2()` — the only sanctioned
  way to load projection CSVs).
- **`scripts/xfp/lib/` (75 modules) is the de-facto library** for the
  decision layer: `leverage_engine.py` (P(win) Monte Carlo — the ONE engine;
  never reimplement a piece), `dpwin_history.py` (durable ΔP(win) record),
  `title_equity.py` (win → championship equity; refuses to extrapolate),
  `roster_rules.py` (legality predicates; 4-RP floor), `pitcher_role.py`
  (true SP/RP role), `archetype_engine.py`, `boom_bust.py`, `period_meta.py`,
  `atomic_io.py`.
- **Lens stack is display-only** (ADR-0008): ~10 context lenses (Stuff+,
  boom/bust, trends, splits…) surface conviction/conflict but NEVER feed the
  projection. Enforced by tests (`test_lens_context_only.py` etc.).
- **Validated-signals registry** (ADR-0003): markdowns in
  `data/research/validation_runs/` are the registry; import-time asserts in
  the model files refuse unregistered FEATS entries. New features go through
  `/validate-feature`, nothing else.

## Automation (GitHub Actions — 3 of 4 run SELF-HOSTED on Josh's PC)

- `daily-refresh.yml` (11:00 UTC): pytest gate → `refresh_dashboards.py`.
  Runs in the real working tree `C:\Users\Joshua\plv_clone` (not a checkout)
  so `.env`, the nested xfp-model repo, and git creds all work.
- `live-matchup.yml` (hourly, game hours): live scores → matchup rebuild →
  publish. `monday-brief.yml`, `pl-cache.yml` (cloud). (`build-report.yml`
  was archived to `docs/archive/workflows/` with the legacy PLV chain,
  2026-09-01.)
- Publishing is gated: model-rebuild failure writes `.cache/PUBLISH_GATED`
  and skips the push; the driver itself still exits 0.

## Boundaries a change is likely to cross

- **Column contracts**: `data/outputs/*.csv` columns are pinned by
  `tests/test_schema_stability_*.py`, `test_contract_schemas.py`,
  `test_board_schema.py`. Renaming/adding output columns → run those.
- **Shared signatures**: `fetch_schedules_by_team(team_ids, start_date,
  end_date)` in `build_matchup_dashboard.py` has 5 AST-discovered consumers
  (`test_schedule_fetch_contract.py`). `build_matchup_dashboard.py` (4234
  lines) is both an entry point and an imported library — treat its
  public names as API.
- **Scoring formulas**: single canonical source; `test_sp_fp_formula_copies.py`
  / `test_no_hardcoded_scoring_weights.py` catch copies.
- **CLAUDE.md itself**: budget + numbered-rule structure is pinned by
  `tests/test_claude_md_budget.py`.
- **Skills**: every `.claude/skills/<name>/` must be in
  `.claude/skills/SKILL_REGISTRY.md` (`test_skills_registered.py`).

## Deliberate non-abstractions

Consolidations that were evaluated and REJECTED — don't re-propose without
reading the ADR: one orchestrator over rh3/rp3/rprs2 (0001), a
`player_profile()` facade (0005), a deep snapshot-rating core (0006), merging
all name `_norm`s (0007). See `docs/DECISIONS.md` for the full log.

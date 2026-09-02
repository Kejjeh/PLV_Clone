# HANDOFF — state of play (2026-09-01)

Written for a cold-start agent on a small budget. Read `CLAUDE.md` first,
then this.

## OFFSEASON — wound down 2026-09-01

The 2026 season is over (Josh lost in the playoffs). Wind-down actions
taken, all reversible:

- All 5 GitHub Actions workflows disabled via `gh workflow disable`
  (daily-refresh, live-matchup, monday-brief, pl-cache, build-report —
  build-report was later ARCHIVED outright with the legacy chain, so only
  the first four exist to re-enable in 2027).
- All Claude scheduled tasks already paused (daily-edge-briefing,
  rehab-master-check, plus expired one-shots).
- Nothing deleted; GitHub Pages dashboards remain up as static artifacts;
  data caches remain on disk.

### Restart checklist (spring 2027)

1. Refresh ESPN cookies in the gitignored `.env` (`ESPN_SWID` / `ESPN_S2`
   expire; harvest per `.env.example`) and confirm the new league year.
2. Bump `SEASON_YEAR` in `src/plv_clone/league_config.py` — the single
   rollover switch by design (issue #59).
3. Check the `espn-api>=0.35,<0.47` pin still works against the new season;
   bump the ceiling deliberately if not.
4. Re-verify league settings (scoring, roster slots, SP cap, RP floor)
   against `docs/memory/league_rules.md` — edit `cap_math.py` constants only
   if the league actually changed.
5. Bootstrap the new year's caches: `scripts/xfp/refresh_xfp_statcast.py`
   for the new season, then one manual `refresh_dashboards.py`.
6. Re-enable automation: `gh workflow enable <name>.yml` × 5; re-enable the
   two recurring Claude scheduled tasks if wanted.
7. `python scripts/ci/smoke.py` + a `/matchup-audit` on the first built
   dashboard before trusting anything.

The offseason is the right window for the P1/P2 items below — especially
positions un-staling (P1-1) and the `requirements.lock` rebuild (P2-4).

## Season context at shutdown

## Done and working

- **Nightly automation ran green all season**: `daily-refresh.yml`
  (self-hosted, 11:00 UTC) runs the pytest gate then
  `refresh_dashboards.py`; last run 2026-08-31 committed and published.
  `live-matchup.yml`, `monday-brief.yml`, `pl-cache.yml` likewise
  (`build-report.yml` archived 2026-09-01; all disabled for the offseason).
- **Test suite green** (verified 2026-09-01): 2447 passed, 3 data-gated
  skips, 1 expected xfail (stale PL cache, cadence-aware), 98s via
  `python scripts/ci/run_summary.py -- python -m pytest`.
  Fast subset: `python scripts/ci/smoke.py` (~15s, 216 tests, offline).
- **Production models** (rh3 / rp3 / rprs2 + volume companions) validated and
  frozen behind the `/validate-feature` protocol; import-time registry
  asserts block unvalidated features.
- **Decision layer** (P(win) optimizer, ΔP(win) history, title equity,
  counterfactual ledger) landed 2026-07-30 and is in daily use.
- **Aug 2026 bug-audit waves 1–18** all landed with pinning tests (script
  payload escaping, IP parsing, cache identity, publish gating, etc.).

## In progress

- **Availability-overlay (Study C)**: failed its auto-ship gate 2026-08-12;
  `build_period_xfp_board.py` emits `*_diag` columns only. Diagnostic-only is
  the CURRENT INTENDED state — do not promote without a new validation run.

## Completed in the 2026-09-01 offseason pass (was "in progress")

- **ADR-0009 edge severed** (commit `0f780a1e`): rh3/rh3_april/xfp_h2_lock
  (+ verdict_backtest) take positions from
  `player_positions.load_position_frame()` over a nightly MLB-API cache
  (`data/reference/player_positions_{year}.json`, new refresh_all stage).
  A ratchet test keeps the consumers severed. NOTE: the old HANDOFF text
  claimed months-stale positions; in fact a weekly `plv update` (step 1.98,
  added 2026-07-20) kept them ≤7 days stale — the ADR addendum has the
  corrected history.
- **Legacy PLV scripts-side chain archived** (commit `9158041b`):
  refresh.ps1 / fetch_fangraphs.py / generate_report.py → `scripts/_attic/`
  (batch 2 in its README); build-report.yml → `docs/archive/workflows/`;
  step 1.98 retired. The PACKAGE stays dormant-retained (step 2.55 +
  tests + CLI still need it); `validate_outputs.py` stays (test-pinned).
- **Issue #54 closed** (commit `e442c640`): never-pairable executed records
  get a terminal UNSETTLEABLE block (`ungradeable: true`, per-population
  reason) once the 2-day attribution horizon passes. Real-ledger effect:
  exactly 3 records (Baez ×2, Grisham) — the census's 3,091 were mostly
  verdict-only records, never pairing candidates.
- **`get_league(year)` factory** (commit `beea4b73`): both synthetic-
  calibration scripts now use the single auth home; bare `_get_league`
  copies deleted.

## Known issues (with repro)

- **Ruff: 186 pre-existing findings** (`python -m ruff check src/ tests/`).
  Not wired into CI. Lint only your own diff; a mass-fix is a big,
  low-value diff that will collide with everything.
- **`requirements.lock` is a whole-machine pip freeze**, not this project's
  closure (pins alpaca-py, backtrader, openai… from unrelated work). Fresh
  machines should prefer `pip install -e ".[dev]"`. Repro: read the lock.
- **91 files hardcode `c:/Users/Joshua/...` roots** (e.g.
  `scripts/xfp/validate_sustainability.py:25`). Fine on Josh's PC (all
  automation is self-hosted there); breaks anywhere else.
  `plv_clone.paths.ROOT` is the fix; migrate only files you touch anyway.
- **Duplicate bare `_get_league`** in
  `scripts/xfp/build_synthetic_calibration_panel.py:49` — reads os.environ
  directly, no retry/snapshot. Migrate to `plv_clone.espn._get_league`.
- **Duplicate template**: `app/reports/process_report_template.html` vs
  `app/templates/process_report_template.html`.
- Version-floor skew: pyproject floors (pandas>=2.0, numpy>=1.26) are far
  below the actually-tested versions (pandas 3.0.2, numpy 2.4.4 on py3.13).

## Next steps (each ≈ one small session)

**P0 — none.** Offseason; automation intentionally disabled.

**P1 — all three completed 2026-09-01** (see "Completed" above).

**P2**
1. *Trim `requirements.lock` to the project closure* (freeze inside a clean
   venv built from `pip install -e ".[dev]"`). Accept: fresh-venv install +
   smoke green using only the new lock.
2. *Migrate hardcoded roots opportunistically* — whenever touching one of
   the 91 files, swap to `plv_clone.paths.ROOT`. Never as a mass sweep.
3. *Dedupe the process_report template* (verify which one
   `scripts/_attic/generate_report.py` reads; delete the orphan).
   Sonnet-safe.
4. *Residual-path sibling of #54*: `PENDING_NO_ID` records retry forever in
   `settle_decisions.py` (~:497). Same terminal-state pattern applies;
   needs its own decision (out of #54's scope by design).
5. *`xfp_h2_lock.py` `approx_games=35` freeze* (~:135): pa_premium has been
   computed against a frozen May game count all season. Fixing changes
   output values — do it at season start 2027 with a fresh A/B.

## Open questions (for Josh)

1. **CLAUDE.md compression trade-off**: the handoff pass compressed CLAUDE.md
   320 → 146 lines, keeping all 34 numbered rules verbatim-in-spirit but one
   line each, and lowered the budget-test ratchet (MAX_LINES 320 → 155).
   Sections dropped to pointers: recent-shipping log, agent-skills pointers,
   claude-mem detail. If any dropped headline should fire from CLAUDE.md
   itself again, it must displace a line.
2. **~30 `scratchpad_*`/`scratch_*` files + 5 loose HTML reports in the repo
   root**: untracked, some are real analysis scripts
   (`scratchpad_reconcile.py`, `scratchpad_streamers.py`). Delete, or move
   keepers into `scripts/xfp/research/`? Not touched in this pass (no
   deletions allowed).
3. **Stale local branches**: `arch/deepening-2026-06-11`,
   `skills-ownership-refactor`, two `backup/pre-rebase-*`, four `claude/*`.
   Delete or keep?
4. **`.claude/settings.json` is gitignored** — the new Read-deny rules for
   bulk data live only on this machine. Track it in git (it holds no
   secrets), or leave local?

## Tech debt (known, not urgent)

- Dead trees (`scripts/_attic/`, `scripts/_oneoff/`, `scripts/xfp/archive/`,
  `_research/`, `_attic/`) — acknowledged in pyproject coverage-omit; the
  PLV legacy chain joins them once P1-1 lands.
- `build_matchup_dashboard.py` is a 4.2k-line entry-point-and-library;
  consumers sys.path-juggle to import it. Works; pinned by contract tests;
  split only with `golden_run.py` refereeing.
- Coverage is honest-but-low and opt-in by design (audit 2026-08-01).
- `.claude/worktrees/lucid-meninsky-*` stale worktree copy of the entry
  points (gitignored).
- Known-issue prose lives in dated docs (`docs/production_audit_2026-*.md`,
  `docs/redo_list_2026-07-29.md`) rather than code TODOs — there are zero
  TODO/FIXME markers in the codebase, deliberately.

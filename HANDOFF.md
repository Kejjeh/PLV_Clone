# HANDOFF — state of play (2026-09-01)

Written for a cold-start agent on a small budget. Read `CLAUDE.md` first,
then this. Season context: 2026 BrownU season, playoffs approaching
(periods 18+); the daily cadence is fully automated.

## Done and working

- **Nightly automation is green**: `daily-refresh.yml` (self-hosted, 11:00
  UTC) runs the pytest gate then `refresh_dashboards.py`; last run 2026-08-31
  committed and published. `live-matchup.yml`, `monday-brief.yml`,
  `pl-cache.yml`, `build-report.yml` also active.
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

- **Issue [#54](https://github.com/Kejjeh/PLV_Clone/issues/54)** (only open
  issue): counterfactual pairing never completes when the rejected side is an
  unrostered FA with no actuals. The "fixable half" shipped in commit
  `74c50819`; what remains is the structurally unfixable half — needs a
  decision on how to grade rejected-FA counterfactuals (proxy actuals from
  MLB logs vs. mark ungradeable). Code: `lib/dpwin_history.py` +
  `scripts/xfp/reconcile_decisions.py` (settlement path).
- **ADR-0009 follow-up**: rh3 hitter positions come from
  `data/outputs/master_hitter_2026.csv`, last regenerated **2026-05-16** by
  the dormant PLV pipeline — new call-ups get `primary_position=None`.
  Fix = source positions from ESPN `get_all_teams()` or MLB Stats API in
  `src/plv_clone/models/xfp/rh3.py` (optional position join) +
  `scripts/xfp/xfp_h2_lock.py`; that also unlocks archiving the whole legacy
  chain (see the ADR's follow-up section).
- **Availability-overlay (Study C)**: failed its auto-ship gate 2026-08-12;
  `build_period_xfp_board.py` emits `*_diag` columns only. Diagnostic-only is
  the CURRENT INTENDED state — do not promote without a new validation run.

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

**P0 — none.** Nothing is on fire; automation carries the daily load.

**P1**
1. *Positions un-staling (ADR-0009 follow-up).* Replace the
   `master_hitter_2026.csv` position join in rh3/h2 with a live source.
   Accept: a 2026 call-up gets a non-null `primary_position` in
   `xfp_rh3_projections.csv`; smoke + `test_schema_stability_h.py` green.
   Escalate to Opus (touches a production model file).
2. *Decide issue #54's unfixable half.* Write the decision into the issue
   and `docs/DECISIONS.md`; implement "mark ungradeable" (conservative) in
   `lib/dpwin_history.py` settlement. Accept: reconcile run completes with
   explicit `ungradeable` rows instead of hanging pairs; issue closed.
3. *Kill the duplicate `_get_league`* in
   `build_synthetic_calibration_panel.py`. Accept: imports from
   `plv_clone.espn`, smoke green. Sonnet-safe.

**P2**
4. *Trim `requirements.lock` to the project closure* (freeze inside a clean
   venv built from `pip install -e ".[dev]"`). Accept: fresh-venv install +
   smoke green using only the new lock.
5. *Migrate hardcoded roots opportunistically* — whenever touching one of
   the 91 files, swap to `plv_clone.paths.ROOT`. Never as a mass sweep.
6. *Dedupe the process_report template* (verify which one
   `generate_report.py` reads; delete the orphan). Sonnet-safe.

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

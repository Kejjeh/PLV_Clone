# Wiring notes — model scorecard (2026-07-10)

New engine: `scripts/xfp/build_model_scorecard.py` (skill: `/model-health`).
Outputs `data/outputs/model_scorecard.{csv,md}` + appends
`data/research/model_scorecard_history.csv`. **NOT yet wired into
refresh_dashboards.py** — the orchestrator owns that file; snippet below.

## Proposed step 4.13 (weekly, Mondays, fail-soft)

Place AFTER step 4.12 (IL transactions, also Monday-gated) in
`scripts/xfp/refresh_dashboards.py`'s main sequence. Weekly is the right
cadence: forward-accuracy anchors move ~7d at a time, and the health
tripwires exist to catch multi-week silent regressions (the rp3 IL-join bug
was invisible for ~6 weeks; a Monday run bounds that to <=7 days).

```python
    # 4.13. Model scorecard + data-health tripwires (Mondays). Forward
    # accuracy per model at 7/14/21/28d anchors + PASS/WARN/FAIL data
    # regression checks (IL join, ros caches, statcast/boxscore lag, FG
    # snapshots, row counts, proj_volume fill). Built 2026-07-10 after the
    # rp3 IL-join regression sat undetected for ~6 weeks. Fail-soft: a
    # scorecard problem must never block the refresh — but DO surface a
    # non-zero exit (exit 1 == at least one FAIL tripwire) loudly.
    if datetime.now().weekday() == 0:  # Monday
        rc = run_step(
            '4.13. Model scorecard + data-health tripwires',
            [sys.executable, str(SCRIPTS / 'build_model_scorecard.py')],
            check=False,
        )
        if rc:
            print('  ! model scorecard reported FAIL tripwire(s) — read '
                  'data/outputs/model_scorecard.md (non-gating)')
```

Adapt the `run_step(...)`/`check=False` invocation to whatever helper the
surrounding steps actually use (4.09/4.12 follow the same fail-soft
pattern); the two load-bearing properties are:

1. **non-gating** — scorecard failure must not abort the refresh;
2. **exit code surfaced** — the engine exits 1 iff a health check FAILs,
   so the refresh log carries the alarm even when nothing crashes.

## Ordering constraints

- Must run AFTER 4.10 (snapshot logger) so today's snapshot row-counts and
  proj_volume fill are in the panel it audits.
- Must run AFTER 1.05/1.5 (statcast gf bridge, boxscore bridge) so the lag
  checks measure the post-bridge state, not the pre-refresh state.
- No downstream consumer: nothing reads model_scorecard.csv in the same
  refresh, so last position (4.13) is safe.

## Manual / ad-hoc

```bash
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/build_model_scorecard.py
```

Idempotent — same-day re-runs replace same-day history rows. Also run it
immediately after touching ANY cache builder (rolling features,
il_split_features, ros_schedule_features, gf bridge) or model pipeline.

## Known day-one observations (2026-07-10 first scorecard)

- `fg_proj_cache_systems_latest` WARN: `rzips_pit` absent from the
  2026-07-10 pull (7/8 systems) — FG snapshotter (step 4.11) issue to watch.
- The 2026-07-09 projection-history rows have `proj_volume` all-NaN: on
  ship day the snapshot logger (4.10) appended before the volume builders'
  output existed, and its (date,type,mlbam) idempotency key prevents
  backfill. Self-heals from 2026-07-10 onward; volume-skill metrics start
  reading meaningfully ~5+ days after 2026-07-10.

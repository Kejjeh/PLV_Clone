# _attic — quarantined legacy PLV scripts

> This directory is listed in `.gitignore` (a CodeGraph-index exclusion, not
> a git removal — the moved files stay tracked because `git mv` preserves
> index entries). Consequence: add NEW files here only via `git mv` of an
> already-tracked file, or `git add -f`; a plain `git add` is silently
> ignored.

**Date:** 2026-07-04
**Why:** 2026-07-04 whole-repo audit (evidence: `.cache/audit0704b/quarantine.txt`)
verified zero references from any live tree (refresh stages, skills, tests,
launchers, imports). Legacy PLV editorial stack — nothing in the current
daily xFP flow touches them. `git mv` only; recoverable from here or git history.

- `run_plv_review.py` — legacy PLV editorial engine (last touch 2026-04-23)
- `run_process_review.py`, `gen_leaderboards.py`, `validate_pl_plv.py` —
  legacy PLV stack, zero refs since 2026-05-03

**Batch 2 — 2026-09-01** (offseason archive of the PLV chain's scripts-side
drivers, unblocked by the ADR-0009 edge-sever: rh3/h2 positions now come
from the live map, so the active layer no longer needs `plv update`):

- `refresh.ps1` — legacy daily driver wrapping `plv update` + `plv
  generate-report`; superseded by daily-refresh.yml + refresh_dashboards.py
  (doc refs only since ADR-0009).
- `fetch_fangraphs.py` — Blast/EV bat-tracking pull merged fail-soft by
  build_exports; zero executable callers. Its output columns are frozen at
  their last refresh.
- `generate_report.py` — legacy public process report. Its workflow moved
  to `docs/archive/workflows/build-report.yml` (was cron every 4h);
  `plv generate-report` still works — cli.py adds `_attic` to sys.path.
- NOT here: `scripts/validate_outputs.py` stays at scripts/ root — pinned
  by tests/test_export_integrity.py's `import validate_outputs`.

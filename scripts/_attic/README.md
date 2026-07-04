# _attic — quarantined legacy PLV scripts

**Date:** 2026-07-04
**Why:** 2026-07-04 whole-repo audit (evidence: `.cache/audit0704b/quarantine.txt`)
verified zero references from any live tree (refresh stages, skills, tests,
launchers, imports). Legacy PLV editorial stack — nothing in the current
daily xFP flow touches them. `git mv` only; recoverable from here or git history.

- `run_plv_review.py` — legacy PLV editorial engine (last touch 2026-04-23)
- `run_process_review.py`, `gen_leaderboards.py`, `validate_pl_plv.py` —
  legacy PLV stack, zero refs since 2026-05-03

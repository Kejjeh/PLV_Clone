---
name: golden-run
description: When refactoring any model/pipeline/dashboard code behavior-preservingly, verify outputs are byte-identical before/after via the A/B golden engine. Use when the user says "golden run", "verify my refactor didn't change outputs", "A/B the models", "prove this is output-identical", or before committing any Rule-9-scoped refactor (dedup, vectorization, extraction, reorder) touching rh3/rp3/rprs2, the volume pipelines, or the archetype builders. Codifies the manual workflow run ~6x during the 2026-07-19 production audit.
---

# golden-run — A/B output-equivalence verifier

## What this is

The **referee for behavior-preserving refactors**. Phase A captures a golden
run on CURRENT code (+ md5-freezes every input); you apply your edits; phase B
re-runs and proves every output byte-identical — then always restores the prod
outputs. If outputs SHOULD change, this is the wrong tool (see Hard rules).

## How to run

```bash
# 1. BEFORE touching code — capture the golden on current code
python scripts/ci/golden_run.py --target volume --phase A
# 2. Apply the refactor
# 3. Verify (exit 0 = all outputs byte-IDENTICAL, prod restored either way)
python scripts/ci/golden_run.py --target volume --phase B
```

Exit codes: **0** identical / **1** diffs or command failure / **2** refusal
(lock held, no manifest, input drift). `--force` overrides the lock; `--restore`
recovers the newest `data/models/.golden_stash/<ts>/` after a `--cold` crash.

## Targets

| target | runs | outputs | frozen inputs |
|---|---|---|---|
| `models` | rh3 / rp3 / rprs2 pipelines | `data/outputs/xfp_{rh3,rp3,rprs2}_projections.csv` | 3 rolling CSVs + `pitcher_counting_stats_2026.json` |
| `volume` | the 3 `xfp_*volume_pipeline.py` | `data/outputs/xfp_{,sp_,rp_}volume_projections.csv` | 3 rolling CSVs |
| `archetypes` | `build_{sp,hitter}_archetypes.py` | 12 files in `data/research/` (ratings_master CSVs, career-panel parquets, definitions/stickiness/decline/boundary JSONs) | multiyr CSVs + age/park/lineup caches |
| `custom` | `--cmd "..."` (repeatable) | `--outputs path...` | `--inputs path...` |

Diff ladder per output: byte `cmp` first; a differing CSV is re-checked with
`pd.testing.assert_frame_equal` (EQUIVALENT = float-formatting only — inspect
why serialization changed), parquet via `DataFrame.equals`, JSON via payload
equality. **Only byte-IDENTICAL across the board exits 0.**

## Gotchas (learned 2026-07-19 — the audit this codifies)

1. **Warm-skip artifacts predating the change make warm-vs-cold diffs
   meaningless — use `--cold` (models target).** It stash-copies the 3
   `data/models/xfp_*_pipeline.pkl`, deletes them so the pipelines cold-fit,
   and restores from stash in a finally block. Canonical: rh3's LOO includes
   in-progress-season rows OUTSIDE the warm-skip fingerprint, so its CI/sigma
   tables drift between fingerprint bumps — a warm/cold rh3 diff is NOT a
   regression. Pass `--cold` on BOTH phases (the engine warns on a mismatch).
2. **Float addition is non-associative.** A formula reorder that is
   algebraically identical (`K + IP*3.3 − H...` operand swaps) can still
   change bytes — that's exactly why the FP-consolidation pass only swapped
   order-matching sites. Run the A/B even for "trivially identical" reorders.
3. **Prod outputs carry enrichment** (post-pipeline columns/joins). The engine
   snapshots them to `.../prod/` in phase A and ALWAYS restores them in the
   finally of both phases — never leave a raw pipeline CSV in `data/outputs`.
   If a run crashes hard, restore by hand from
   `data/research/.golden_run/<target>/prod/` (or `--restore` for the pkls).
4. **Input drift voids the diff** (the data-coupled-golden lesson,
   `tests/test_triangulate_golden.py`): phase B refuses (exit 2, names the
   file) if any frozen input's md5 changed — a nightly refresh between phases
   means the diff measures the data, not your refactor. Recapture phase A.
5. **Rule 9: if outputs SHOULD change, this is the wrong tool.** A golden run
   proves a refactor changed nothing; a feature/signal that is SUPPOSED to
   move projections goes through `/validate-feature` instead. Never "accept"
   a golden diff as an improvement.

## Hard rules

1. **Phase A runs on CURRENT (pre-edit) code.** Capturing after editing
   compares the refactor to itself — always green, always worthless.
2. **Don't run during (or into) a nightly refresh.** The lockfile
   (`<scratch>/LOCK`) refuses concurrent starts because a refresh rewrites
   both the outputs mid-diff and the inputs under the hashes. Scratch dir:
   `GOLDEN_RUN_DIR` env or `data/research/.golden_run/` (gitignore-worthy;
   never commit it).
3. **A non-identical result blocks the commit** until explained: EQUIVALENT
   needs a serialization-change explanation; DIFFERENT means the refactor was
   not behavior-preserving — fix it or reclassify the work under Rule 9.

## Companions

- `/production-audit` (docs/production_audit_2026-07-19.md) — the audit
  workflow whose per-item "golden check: byte-identical" steps this automates.
- `/model-health` — run after the refactor LANDS to confirm the substrate
  tripwires still pass; golden-run proves equivalence, model-health proves
  ongoing health.
- `/validate-feature` — the path for changes that are MEANT to move outputs.

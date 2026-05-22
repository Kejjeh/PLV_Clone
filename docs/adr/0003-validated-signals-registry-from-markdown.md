# Validated-signals registry sourced from markdown frontmatter

Three pieces of state were disconnected: FEATS lists (hardcoded Python in each per-model file), validation runs (markdown files in `data/research/validation_runs/` with YAML-ish frontmatter), and the validated-signals registry (text in `memory/reference_validated_signals_registry.md`, not in the repo). A feature could be added to `RH3_FEATS` / `RP3_FEATS` / `FEATS_RPRS2` without ever appearing in a validation run or registry — the 9-rule multi-testing protocol was enforced by the `/validate-feature` skill's prompt, not by code.

**Decision:** The markdown files in `data/research/validation_runs/` are the registry. `src/plv_clone/models/xfp/validated_signals.py` loads them at import time into a typed `REGISTRY: dict[str, ValidatedSignal]`. Each per-model file asserts at import that every FEATS entry has a registry record with matching `production_target`. Failure halts the pipeline; an unvalidated feature cannot ship.

## Sequencing

Backfilling the existing markdowns to a consistent frontmatter schema is its own workstream and must not block the package-restructure refactor. The phased rollout is:

1. **Package move lands (#5)** + cheap #4 (package boundary as the structural production marker).
2. **`/validate-feature` skill updates** to write the canonical frontmatter schema on every new validation. Caps backfill scope to existing features only.
3. **Background pass** to bring existing `validation_runs/*.md` frontmatter to the schema.
4. **Loader lands as soft warning** in one PR — operates against backfilled markdowns to verify the schema works.
5. **Flip to hard `assert`** in a second PR after one cycle of soft-warning running clean.

The Rule 9 baseline check (currently `xfp_rh3_pipeline.py:374-381`, `xfp_rp3_pipeline.py:320-331`, both printing PASS/MARGINAL non-fatally) becomes a hard `assert overall['r'] - baseline['r'] >= 0.005` in step 1 — it does not depend on the registry backfill and was never a valid ship state.

## Considered and rejected

- **Typed Python registry as primary source of truth, markdowns become pointers.** Creates two sources of truth; PRs that validate a feature touch two files; drift between them is the predictable failure.
- **Stop at the package boundary; no registry loader.** Doesn't address the structural gap that a v3-validated-but-not-shipped feature can still sneak into FEATS by accident.
- **Soft warning indefinitely instead of hard assert.** Trains callers to ignore warnings — refresh_dashboards.py printing "WARNING: N unvalidated features" daily normalizes the noise. The assert is the discipline; the soft phase exists only to verify the loader, not as a permanent stance.

## Schema as prerequisite

The loader's `ValidatedSignal` dataclass and tolerant parser must be written **before** the backfill begins, not after. Otherwise the backfill is done against an implicit schema the loader later rejects.

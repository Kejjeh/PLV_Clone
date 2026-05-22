# Engine as toolkit, not orchestrator

The three production xFP pipelines (`rh3`, `rp3`, `rprs2`) share eight bug-prone helpers (`build_marcel_prior`, `compute_population_means`, `apply_shrinkage`, `cross_year_eval`, `fit_residual_ci`, `lookup_sigma`, `train_final`, `compute_replacement_delta`), so the deepening instinct was to consolidate them into one `engine.fit_and_project(config: ProjectionConfig)`. A side-by-side trace of the existing `main()` functions before committing showed this would not survive: the three pipelines diverge at **three independent touchpoints** (pre-training data transformation — rh3/rp3 shrink, rprs2 doesn't; accountability gate shape — rh3 has one Rule 9 comparison, rprs2 has a 2×2 dual gate; projection-time logic — IL-vet fallback, schedule strength, PA-aware totals, slump-precedent merge are each rh3-only-or-rp3-only steps). Forcing one config object to express all of that became config-as-code.

**Decision:** `engine.py` is a *toolkit* of the shared helpers. Each per-model file (`rh3.py`, `rp3.py`, `rprs2.py`) owns its own `fit_and_project()` and composes the toolkit at load-bearing steps. Per-model orchestration is code, not config.

## Considered and rejected

- **Single `fit_and_project(config)` with a `shrinkage=None` branch.** Defeated by the three-touchpoint trace: the branch was never one gate. Would have grown into a god-function with three independent strategy slots.
- **Two engines — `marcel_engine` for rh3+rp3, `direct_engine` for rprs2.** Defeated by the rh3-vs-rp3 trace: even those two diverge at prior layering (rh3 single-layer, rp3 three-tier mlb_lag→milb→league_mean), external feature merges, v2 features, eligibility column, IL-vet fallback (rp3-only), schedule strength (rp3-only), PA projection (rh3-only), slump-precedent merge (rh3-only), and bundle shape. The shared-orchestration claim does not hold up to side-by-side reading.

## Consequence

The deletion test for the toolkit is honest: delete `engine.py` and the eight helpers reappear in three files. The orchestration is genuinely per-model — not duplication — so we accept ~120-line `fit_and_project` per file as the correct shape.

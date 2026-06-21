# No deep `rate_snapshot` core / `RoleSpec` adapters for the snapshot builders

An architecture review (2026-06-21) of the player-archetype **snapshot**
subsystem proposed, as candidate C4, collapsing the three snapshot builders
(`build_hitter_snapshots`, `build_sp_start_snapshots`, `build_rp_snapshots` in
`scripts/xfp/build_player_profiles_dashboard.py`) behind a single deep
`rate_snapshot(windowed_counts, baselines, role_spec)` module, with each role
reduced to a declarative `RoleSpec` (pillar→metric map, cadence source, sample
floor, baseline keys).

**Decision:** Do **not** build the deep core + `RoleSpec` adapter layer.

## Why

- **The hard nuclei are already extracted and tested** (C1–C3 + the Option-A
  start-anchored work). Scalar 20-80 rating + cell→label live once in
  `lib/archetype_engine.py` (`rate_value` / `bucket` / `label_for_cell`, covered
  by `tests/test_archetype_engine.py`); the SP event cadence lives in
  `lib/sp_start_snapshots.py` (`trailing_start_windows` / `rates_from_counts`,
  covered by `tests/test_sp_start_snapshots.py`). The "no covering tests" premise
  the deep-core case leaned on is true only of the thin builder *wrappers*.

- **What actually remains duplicated is small and bounded** — only the per-pillar
  fold: *rate each component → drop None → mean (RP `BATTED_BALL` is a weighted
  mean) → return None if a pillar has zero surviving components → round to int*,
  ~15–20 lines × 3 builders. That, and only that, survives the deletion test as a
  shared unit. It does **not** justify a deep core.

- **`RoleSpec` is config-as-code — the shape ADR-0001 already rejected.** The RP
  two-source baseline merge (`R_SRC` + `R_MASTER` with the `pct/100` unit
  alignment) and the three cadences are **baseline assembly + source iteration**,
  not pillar-fold logic; they diverge per builder by nature. A `RoleSpec` must
  absorb them as independent strategy callables (`counts_source` /
  `baseline_builder` / `sample_floor` / `extra_fields`) — the same god-config
  posture ADR-0001 forbade for `fit_and_project`. Complexity would be relocated
  into a config object, not concentrated. Highest blast radius (a behavior-
  preserving rewrite of three loops), net-neutral LOC, display-only payoff.

- **Display-only ceiling (feedback #13).** Snapshots cannot move
  rh3/rp3/rprs2 — a fold bug degrades a chart, not a decision. The risk/reward of
  a dedicated refactor push does not clear the bar.

## The right-sized alternative (allowed, opportunistic — not urgent)

A small pure helper in the existing toolkit — `rate_pillars(components,
weights=None)` in `lib/archetype_engine.py` — that folds *rate → drop-None →
(optionally weighted) mean → empty-pillar None-gate → round*, collapsing the
H/SP plain-mean and RP weighted-mean paths into one tested path (weights default
to 1.0). Constraints if/when taken:

- The caller (builder) keeps ownership of metrics-dict construction, the RP
  `pct/100` unit alignment, cadence, and baseline assembly — the helper only
  folds already-aligned components. The unit-alignment trap should become a
  named, commented helper *in the builder*, not in the toolkit.
- `cell` + `OVERALL` composition stay in the builder against the existing
  `label_for_cell` seam.
- Add a uniform-weights equivalence test (weighted mean with all weights == 1
  equals the plain mean) so the RP and H/SP paths are proven to be one code path.
- Capture golden-output characterization of the three builders before the swap
  (the C1–C3 work already established this net).

## Consequence

A future architecture review that re-proposes a deep `rate_snapshot` core or a
`RoleSpec`/adapter layer should stop here: it was evaluated (judge panel,
2026-06-21) and rejected on the ADR-0001 config-as-code precedent + the
display-only ceiling. The bounded pillar-fold duplication may be consolidated via
the `rate_pillars` toolkit helper whenever these builders are next touched.

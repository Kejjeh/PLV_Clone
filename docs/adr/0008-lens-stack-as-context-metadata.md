# 0008 — The lens stack is context metadata, never a projection input

- Status: accepted
- Date: 2026-06-23
- Supersedes/relates: 0003 (validated-signals registry), 0005 (no player_profile lens facade)

## Context

`/triangulate` layers ~10 context lenses on top of the validated projection models —
platoon splits, expected-vs-actual (luck), home/road, times-through-order decay, realized
boom/bust, in-season archetype trajectory, Stuff+, SP-floor, physical (bat-speed/velo)
trend, and shadow-scout. It is tempting to treat "more signal" as "better projection" and
fold these into the model feature vectors or let them nudge the headline number.

That temptation is empirically wrong here. The leakage-safe, player-clustered OOS study
(`lens_value_add_2026-06-11.md`) showed the multi-lens synthesis does **not** beat the base
rank at point-forecasting forward FP: clean ΔR² **+0.006 H (n.s.) / −0.014 SP (negative)**;
the apparent +0.033 was an L7-leakage artifact. The lenses earn their keep ONLY as
conviction / conflict surfacing (agreement count sorts realized direction monotonically),
not as a free R² boost. xwOBA-L21d (H) and boom/bust + sustainability (SP) are specifically
non-additive / mildly negative as point terms (CLAUDE.md #13).

Historically this was enforced by discipline ("remember rule #13") — fragile. A single edit
adding `stuff_plus` to `RP3_FEATS`, or a `flatten_*` serializer emitting a new column that a
downstream model later picks up, could silently regress the projection.

## Decision

1. **The lens stack is context metadata.** A lens may inform the *displayed verdict /
   conviction* and the dashboards, but it MUST NOT be a feature of any projection model
   (rh3 / rp3 / rprs2 / blended xFP) and MUST NOT move the headline number.

2. **One authoritative declaration.** `scripts/xfp/lib/lens_registry.py` enumerates every
   lens family and the EXACT batch columns it emits (exact names, not prefixes — a prefix
   like `split_` wrongly swallows the model feature `split_day`, and `tto_` misses
   `tto1_rate`). Each family records validated-vs-experimental + a validation reference.

3. **Mechanical enforcement, both directions** (`tests/test_lens_context_only.py`):
   - no model feature list (`RH3_FEATS` / `RP3_FEATS` / rprs2 feats) may contain a
     registered context-only column — a lens can't leak into the projection;
   - every column a `flatten_lenses` / `flatten_actuals` / `flatten_extra` serializer
     emits must be a registered context-only column — no rogue column escapes the contract.
   Adding or renaming a serialized column without updating the registry fails CI.

4. **Schema validation at the boundary.** `cached_data._load_projection` validates
   `REQUIRED_COLUMNS` per bucket, so a model-pipeline refactor that drops a headline/id
   column fails loudly at load instead of as a cryptic `KeyError` deep inside `model_row`.

## Consequences

- The headline projection is structurally protected: wiring a lens into a model now fails a
  test rather than silently shifting numbers.
- New lenses are cheap and safe to add (one registry entry); the contract scales.
- The registry doubles as documentation of what each lens is, where it lives, and whether it
  is validated.
- Cost: a small amount of duplication (exact column names live in both the serializer and
  the registry), paid down by the coverage test that keeps them in sync.

## Alternatives considered

- **Runtime `@display_only` decorator that strips lens keys before the model.** Rejected as
  heavier and less informative than a static, enumerated contract enforced in CI — the test
  catches the leak at authoring time, not at runtime.
- **Prefix-based registry.** Rejected: `split_day` (a real rh3/rp3 feature) collides with the
  platoon `split_` prefix; exact columns are unambiguous.

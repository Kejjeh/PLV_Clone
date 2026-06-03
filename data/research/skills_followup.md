# Skills audit follow-up (2026-06-03)

Items deferred from the YES_HIGH/YES_LOW skills pass.

## Missing memory file

- `reference_park_friendly_component.md` — referenced by triangulate,
  stream-the-stack, fa-pickup-deep-dive SKILL.md updates, but no file
  exists in `~/.claude/projects/c--Users-Joshua-plv-clone/memory/`.
  Need to capture: validation methodology, per-tier lift, park-factor
  source (presumably `data/research/xfp_cache/park_factors_2026.csv`),
  and confirmation that it's the 4th SP boom_stack component (replacing
  the prior 3-component spec). Once written, add to MEMORY.md index.

## Threshold recalibration (pitcher-sustainability)

- σ rescale ×2.41 widened p25/p75 bands. The 1.5 FP BUY-LOW / SELL-HIGH
  divergence threshold may now over-fire at the margin. A note has been
  added to the SKILL.md but the threshold itself was not re-anchored.
  Run a calibration pass against post-rescale data and decide whether
  to bump to 2.0 FP or hold at 1.5 with a softer interpretation.

## roster-health alert promotion

- BOOM_STACK_HIGH / BOOM_STACK_LOW / HIGH-K_ARM alert types are noted
  as candidates in the SKILL.md but not implemented. Need per-stack
  threshold calibration on rostered-SP universe before promoting.

## league-deep-audit 12th layer

- boom_stack tier distribution per team is noted as an optional addition;
  no code change made. Add once first-week stream-the-stack outputs are
  stable so we can compute team-level distributions consistently.

## Items intentionally skipped (already up-to-date)

- `/triangulate` — already comprehensively documents all new tags.
- `/sp-week-plan` Step 5.5 (week-boom) — already shipped and documented.
- `/stream-the-stack` — minor refinement applied (park_friendly as
  4th component + /boom-stack-explain cross-link).

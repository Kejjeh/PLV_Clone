---
name: production-audit
description: Repeatable multi-agent CODE audit of the engines, pipelines, and skill system — the 2026-07-19 five-wave process as a skill. Use for "audit the codebase", "review all our engines and make them faster/more robust", "find duplication/dead weight", quarterly maintenance, or after a burst of feature-shipping. CODE/SKILL/registry drift only — runtime DATA/pipeline health is /model-health's charter.
---

# production-audit

Codifies the 2026-07-19 audit (5 waves, ~30 findings shipped same-day, all
behavior-preserving). Findings and the living backlog append to
`docs/production_audit_<date>.md` (prior art: production_audit_2026-07-19.md
— read its backlog first; don't re-derive known items).

## Step 1 — 4-surface parallel Explore fan-out

Launch four Explore agents (CodeGraph block per CLAUDE.md), one per surface,
each returning ranked findings with file:line + concrete fix:

1. **Refresh pipeline** (`refresh_dashboards.py`): step inventory, duplicate
   compute across steps, fail-soft vs gating, timeouts, ordering deps,
   wall-clock ranking.
2. **Model pipelines** (rh3/rp3/rprs2, volume, archetypes, ingestion):
   copy-pasted helpers, repeated big-parquet reads, silent-failure joins
   (match-rate guards!), hardcoded years, dead code, scoring-formula strays.
3. **Engines + dashboards** (run_*, build_*, espn layer): duplicated
   data-access, cache-invalidation rules per on-disk cache, missing
   timeouts/retries, per-row crash guards, oversized files, dead engines.
4. **Libs + tests + data** (lib/, src/, tests/, data/): lib-vs-src
   duplication, untested load-bearing modules, constants sprawl, tracked
   files that should be ignored, orphan scripts.

## Step 2 — triage rules (non-negotiable)

- **Behavior-preserving only.** Model features/weights/verdict logic are
  Rule 9 territory — never "fixed" in an audit.
- **Every model-touching change ships behind /golden-run** (byte-identical
  A/B; cold-vs-cold when warm artifacts predate the change).
- Silent-failure guards (match-rate asserts, drop counters, staleness
  prints) change VALUES never — visibility only.
- Verify agents' claims before acting: two of the 2026-07-19 findings were
  stale/wrong on inspection (timeouts already present; a documented-not-real
  bug). Agents find; you confirm.
- Float op-order is not associative: formula consolidation only where
  operand order matches, else per-file A/B.

## Step 3 — skill/registry drift check

Run the skills half: `python -m pytest tests/test_skills_registered.py`
(on-disk dirs ↔ SKILL_REGISTRY catalog, alias banners); grep CLAUDE.md's
cheat sheet for names that no longer exist; report drift as findings.

## Step 4 — ship + record

Tiered commits (one coherent theme each, full suite green between), audit
doc updated with SHIPPED/backlog deltas, and a final summary that separates
"verified fixed" from "deferred with reasons". Deliberate-deferral is a
valid outcome — record the rationale (the lib/-packaging entry is the
model).

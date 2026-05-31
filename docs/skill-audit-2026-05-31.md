# Baseball-skill consistency audit — 2026-05-31

Four parallel agents audited 32 baseball skills (4 missed by Edit-permission denial; audits captured below for follow-up). Highest-leverage fixes have been applied inline; remaining recommendations are catalogued here.

---

## Applied this session

### Factual fixes
- **rp-archetype** — version drift: description said 2,354 RP-years 2017-2026; body still said 2,087 / 2018-2026 in multiple places. Reconciled.

### Frontmatter restoration (skills that had no YAML, so auto-loaded with placeholder descriptions)
- **fa-monitor** — added YAML, surfaces all 6 signal types, cross-refs `/triangulate` and `/fa-pickup-deep-dive`
- **sp-breakout-signal** — added YAML, surfaces the 33k-start calibration + threshold
- **sp-rehab-tracker** — added YAML, notes that "NO DATA" is the most common verdict
- **league-breakout-sustainability** — added YAML, surfaces the 6-tier scorecard

### Cross-references (Pattern A handoff fixes)
- **monday-morning** — chain now includes `/roster-health` between roster-audit and sp-week-plan; explicit handoff to `/triangulate` for individual player deep-dive

---

## Catalogued for follow-up (audit-only, edits not applied)

These were flagged by the audit agents but require either user input or larger surgery than fit this pass.

### High-value, low-effort (do next pass)
| Skill | Recommended addition |
|---|---|
| **validate-feature** | Worked example: SPEED_PROFILE override rejection (2026-05-30). N=321, 2.4pp underperformance, cleanest live demo of Rule 9. See `docs/triangulate_calibration_2026.md`. |
| **pl-cross-reference** | "When `/triangulate` is the better choice" callout at top — many use cases now superseded by triangulate's batch mode + cached PL. |
| **fa-rp-pool** | Warn that `data/research/pl_cache/pl_closers.json` ships empty — first-run requires seeding via WebSearch + WebFetch per `/triangulate` Step 1. |
| **fa-sp-pool** | Reference `data/research/pl_cache/pl_sps_top100.json` cache; skill currently re-WebFetches every call. Cross-ref `/triangulate`. |
| **sp-week-plan** | Cross-ref `/triangulate` per-SP `verdict_top` + `confidence` for weighting EV scores on borderline bench candidates. |
| **scouting-report** | Add `/triangulate` to integration table; recommend it as deep-dive for any top-priority candidate. |

### Pattern H — decision-tree pseudo-code missing
These skills emit verdict tiers but don't formalize the rules in pseudo-code:
- **fa-pickup-deep-dive** (PASS/CONSIDER/SKIP)
- **fa-signal-to-decision** (YES/BORDERLINE/PASS + scoring formula constants)
- **fa-replacement-pool** (Tier 1/2/3 classifier)
- **breakout-sustainability** (SUSTAINABLE/NARROW/HOT-STREAK)
- **sp-bench-mc** (gap>1pp recommend, gap<1pp fallback)
- **sp-rehab-tracker** (AHEAD/ON-TRACK/BEHIND/WORKLOAD-ONLY/NO-DATA — exists prose-form, lift to block)
- **league-breakout-sustainability** (6 tiers)
- **league-deep-audit CONSENSUS_** verdicts (already retrofitted with 11-lens table; pseudo-code could come next)

### Pattern A — Independent-lenses framing missing
- **hitter-sustainability** — 9-marker decomp should be a lens table with per-marker failure modes
- **fa-monitor** — 6 signals should each have an anchor + failure mode
- **fa-signal-to-decision** — scoring formula has hard-coded magic numbers (`/3.0`, `0.1` slot bonus); should be tagged "heuristic, not validated" or run through `/validate-feature`

### Pattern F — Cache-with-staleness inconsistencies
- **pl-cross-reference**, **savant-compare** — both re-fetch on every call. Should adopt the `pl_cache/` schema + TTL warning pattern from `/triangulate`.
- **league-deep-audit** — has prose "<24h old" check but no print-warning at startup.

### Common one-liners missing (Pattern G)
8 of 11 skills with backing scripts don't surface the canonical invocation:
- fa-monitor, fa-replacement-pool, matchup-audit, validate-feature, league-deep-audit, league-breakout-sustainability, sp-rehab-tracker, fa-sp-pool — all have scripts that should be in a top-of-file bash code block.

### Trigger-phrases section inconsistent
~6 skills have triggers in YAML frontmatter only (not a dedicated section). The exemplars (triangulate, rp-archetype, scouting-report) put them in a labeled `## Trigger phrases` block which aids agent discoverability.

### "Known limitations" section absent from every skill
None of the 32 audited skills have a dedicated `## Known limitations` section flagging stale calibration dates. The triangulate skill could be retrofitted with this too — currently the only date-warning is in the engine's stderr output.

### Duplicate name-collision guards
Same block copy-pasted across `hitter-sustainability`, `hitter-compare`, `breakout-sustainability`, `slump-or-decline`, `fa-monitor`, `fa-pickup-deep-dive`, `fa-replacement-pool`, `league-deep-audit`. Should all link to `/player-id-resolve` as the single source of truth.

### Specific gaps with named edits
| Skill | Issue |
|---|---|
| **forced-drop-planner** | Add today's Glasnow/Fried/Greene IL pattern as canonical case; Step 2 cascade-counter doesn't propagate after a drop is "absorbed" |
| **roster-audit** | Step 4 SP-cap math should hand off to `/forced-drop-planner` when `gap_to_cap < -1` |
| **roster-verify** | Document as REQUIRED pre-condition for ~6 other skills |
| **roster-deep-audit** | Add "Common one-liners" showing the canonical 4-skill chain |
| **roster-health** | State explicitly that this is a do-it-inline skill (no script) |
| **career-form-rank** | No dedicated script — confirm whether to formalize one or leave as inline SQL recipe |
| **sp-archetype** | Add cross-ref to `/triangulate` in Integration table (archetype is one of triangulate's 3 lenses) |
| **hitter-archetype** | Add Common one-liners block; flag 2026-05-28 boundary calibration in Known limitations |
| **sp-bench-mc** | Cross-ref the 10-SP-start-cap rule from CLAUDE.md |

---

## Cross-skill design observations

1. **Three formatting conventions for "When NOT to use":** `## When NOT to use this skill` / `## When NOT to invoke` / `## When NOT to use`. Normalize to first form.

2. **Common one-liners is a triangulate-only pattern.** Worth promoting to a standard for all skills with backing scripts.

3. **Decision-tree pseudo-code is also triangulate-only** despite ~12 skills emitting verdict tiers. Pattern H from `docs/lessons-from-triangulate.md` was the lessons-doc deliverable — applying it to all verdict-emitting skills is the natural next pass.

4. **Triangulate cross-references are missing across the board.** Triangulate (2 commits ago) became the canonical 3-lens layer but only a handful of skills have been updated to mention it as the deep-dive layer or batch-mode option.

5. **Two skills have no backing script** (roster-health, career-form-rank) — they're "do-it-inline" skills. State this explicitly so users know not to look for `run_X.py`.

---

## Suggested next pass

If time allows, the next audit pass should:
1. Apply Pattern H decision-tree pseudo-code blocks to the 7-8 verdict-emitting skills listed above.
2. Add the SPEED_PROFILE-rejection worked example to `/validate-feature`.
3. Retrofit `/pl-cross-reference` with the "when triangulate is better" callout.
4. Sweep `/triangulate` cross-references into the 6 skills that need them (fa-sp-pool, fa-rp-pool, sp-week-plan, scouting-report, sp-archetype, hitter-archetype).
5. Add a single `## Known limitations` section pattern to all 32 skills (small lift each).

These were all explicitly identified by the audit agents and require ~10-15 minutes of focused editing per pass.

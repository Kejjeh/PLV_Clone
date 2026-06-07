# Adversarial replay — 2026-06-06 wrong calls vs merge protocol

Method: for each known wrong call, walk the encoded skill body + memory
references and check whether the protocol would have caught it. Cite the
specific rule / section that triggers.

Protocol surface audited:
- `.claude/skills/boom-bust-history/SKILL.md` (Step 0.5, 6.5, Tier C
  positioning, merge block)
- `.claude/skills/sp-slate-grid/SKILL.md` (Drop-target rule, Tag
  verification rule)
- `.claude/skills/hitter-slate-grid/SKILL.md` (Tier B veto, drop-target
  rule, slot-fungibility anti-pattern)
- `.claude/skills/roster-deep-audit/SKILL.md` (v2 chain, conflict
  resolution algorithm, confidence-weighted block)
- `memory/reference_lens_merge_protocol.md` (5 conflict rules + Tier B
  veto + 8-lens confidence)
- `memory/reference_decision_type_lens_registry.md`
- `memory/feedback_slot_fungibility.md`
- `memory/feedback_rank_full_staff_before_naming_drop.md`

---

## 1. Adames — manual k=80 said 15.4 FP/wk; HIGH-conf Blended xFP said 10.27

Encoded countermeasure: `reference_lens_merge_protocol.md` § "Tier A
projection source — prefer Blended xFP, fall back to manual shrinkage"
names Adames by name as the canonical failure and codifies the rule
"Trust the blend when available; manual shrinkage is a fallback, not a
parallel signal." Mirrored in `boom-bust-history/SKILL.md` § "When to
prefer Blended xFP over manual shrinkage."

Trace: Adames row in `live_blend_xfp_latest.csv` would join with
confidence_tier=HIGH. Per the rule, manual k=80 is suppressed.

VERDICT: CAUGHT.

---

## 2. Bradish hot streak — L5 17.88 / 37% boom read as BUY; blend 7.12 + NOISE said FADE

Encoded countermeasure: `reference_lens_merge_protocol.md` Conflict Rule
1 names Bradish explicitly — "Model says FADE but L5 actuals say BUY →
check Tier B sustainability bucket: NOISE/REGRESS → trust model." Also
in `roster-deep-audit/SKILL.md` § Conflict resolution algorithm Rule 1.
`boom-bust-history/SKILL.md` § Tier C positioning block names Bradish
as the canonical case for "boom-bust verdict downgraded by Conflict Rule
1."

Trace: Tier C HOT STREAK + Tier A FADE + Tier B NOISE → Conflict Rule 1
fires → model wins → FADE.

VERDICT: CAUGHT.

---

## 3. Soriano "bust" — 37% bust read as DROP; sustainability IMPROVING said HOLD

Encoded countermeasure: `reference_lens_merge_protocol.md` Conflict Rule
2 names Soriano explicitly — "CAP_FODDER + xwOBA L21d gap within ±0.020
→ Tier B trumps Tier C." Also in `boom-bust-history/SKILL.md` § Tier C
positioning block: Soriano is the canonical case.

Trace: Tier C 37% bust + Tier B IMPROVING (5/9 markers up) + Tier 3 gate
SKILL_HOLDING → Conflict Rule 2 fires → HOLD.

VERDICT: CAUGHT.

---

## 4. Muncy — boom-bust 57% bust; Tier 3 revealed REAL_DECLINE L21d but RISING xwOBACON

Encoded countermeasure: `reference_lens_merge_protocol.md` Conflict Rule
3 names Muncy — "REAL_DECLINE L21d but xwOBACON YoY RISING → Recovery
template VALID, ceiling intact. HOLD with sell-high optionality."
`boom-bust-history/SKILL.md` Step 6.5 mandates xwOBACON YoY trajectory
pull BEFORE any drop. `roster-deep-audit/SKILL.md` § conflict-resolution
Rule 3 ditto.

Trace: drop recommendation triggers Tier 3 mandatory gate → pulls
xwOBACON YoY → RISING → Rule 3 fires → HOLD.

VERDICT: CAUGHT.

---

## 5. Langford slot fungibility — drop OF Langford "to fill OF5"

Encoded countermeasure: `feedback_slot_fungibility.md` exists as a
named memory; `boom-bust-history/SKILL.md` anti-pattern list names the
Langford case verbatim; `hitter-slate-grid/SKILL.md` anti-pattern list
mirrors it. `boom-bust-history` § "Marginal FP per slot — SP vs Hitter"
codifies the cross-position decision math.

Trace: a same-position drop-to-fill would be flagged by either skill's
anti-pattern list. The corrected output is "ADD an OF-eligible FA;
don't shuffle existing OF players."

VERDICT: CAUGHT.

---

## 6. Messick "no data, rookie callup" — actually rp3 #63 / Blended xFP 14.68 HIGH

Encoded countermeasure: `feedback_rank_full_staff_before_naming_drop.md`
names Messick explicitly. `sp-slate-grid/SKILL.md` § Drop-target rule
(added 2026-06-06 after Messick mis-call) requires ranking the user's
full SP staff by Blended xFP before naming a drop. `hitter-slate-grid`
mirrors the rule. Anti-pattern: "Calling a rostered player 'no data'
because they're not on the slate's date window."

Trace: drop recommendation triggers staff-rank → Messick surfaces at
top → STOP and reconsider.

VERDICT: CAUGHT.

---

## 7. Cameron HIGH-K emoji rendered without checking JSON boolean

Encoded countermeasure: `sp-slate-grid/SKILL.md` § "CRITICAL — Tag
verification rule (added 2026-06-06 after Cameron mis-call)" mandates
reading `season_only_tags.high_k_pitcher.is_high_k` BOOLEAN; provides
a `boom_tags()` reference implementation. Anti-pattern list: "Rendering
an emoji tag without verifying the boolean field in the JSON. Canonical
bug 2026-06-06."

Trace: tag render path goes through `boom_tags()` → reads the boolean →
`is_high_k=false, reason="z=0.28_below_threshold"` → no emoji emitted.

VERDICT: CAUGHT.

---

## Summary

All 7 wrong calls: CAUGHT by current protocol. Every named canonical
failure has a corresponding rule, anti-pattern, or named conflict-rule
entry in either the skill body or the merge-protocol memory.

## Residual gaps (not failures from the 7 cases — but holes adjacent to them)

1. **No protocol-level enforcement of the v2 confidence-weighted block
   for casual one-off questions.** The block is mandated for
   `/roster-deep-audit`, `/sp-slate-grid` synthesis, and
   `/hitter-slate-grid` synthesis, but NOT explicitly for a freeform
   "should I drop X" question that doesn't trigger a slate-grid run.
   Risk: a user asks "drop Suárez?" and Claude answers conversationally
   without the lens-merge block, bypassing Tier B veto enforcement.
   Mitigation: cross-reference the merge protocol from `/triangulate`
   and `/fa-pickup-deep-dive` so the block fires on single-player
   questions too.

2. **Tier B for RPs is thin.** Conflict Rules 1-5 are hitter/SP-shaped
   (xwOBA L21d, xwOBACON YoY, sustainability NOISE/REGRESS). Boom-bust
   Step 6.5 names `leverage_tier` for RPs but no Conflict Rule covers
   "leverage_tier intact + boom-bust DECLINING." A 37%-bust closer
   could still ship as DROP under the current rules unless leverage
   downgrade is also surfaced.

3. **Drop-target rule says "STOP and reconsider" but doesn't hard-block
   the swap.** A future session could acknowledge the trade-off and
   still ship a RoS-negative swap. For high-stakes drops the rule
   should escalate to "RoS-negative drops require explicit user
   confirmation," not soft warning.

4. **Slot fungibility anti-pattern is enumerated in 3 skills but not in
   `/roster-deep-audit` or the merge-protocol memory itself.** A
   session running `/roster-deep-audit` alone (without slate-grid
   chaining) could re-emit the Langford pattern. Suggest mirroring
   the anti-pattern into `roster-deep-audit/SKILL.md` and adding a
   one-liner to `reference_lens_merge_protocol.md`.

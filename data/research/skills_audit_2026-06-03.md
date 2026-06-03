# Skills Audit — 2026-06-03

Triggered by today's shipped changes:
- σ rescale (×2.41 global) on rp3 variance bands
- Tier-aware boom_stack thresholds (ace / sp2_sp3 / backend / streamer)
- HIGH-K ARM standalone tag
- skill_spike: 3g → 5g window flip
- /stream-the-stack new skill
- Hitter boom_stack tag
- park_friendly as 5th boom_stack component (N/4 → N/4 with park as one of them; SP stack components are now skill_spike/recform_hot/opp_soft/park_friendly)
- Anti-predictive skill_spike warning
- In-flight: catcher_framing tag, lineup_amp (4th hitter component), week_boom in /sp-week-plan

See `docs/architectural_lessons_2026-06-03.md` for context.

## Audit table

| Skill | Affected? | Priority | Specific update needed |
|---|---|---|---|
| triangulate | YES_HIGH | P0 | Verify SKILL.md reflects: SP boom_stack is 4 components including park_friendly; HIGH-K standalone tag printed; hitter boom_stack tag exists; anti-predictive skill_spike warning shown when fired. Confirm display section enumerates current tag set. |
| stream-the-stack | YES_HIGH | P0 | New skill — refine after first week of use. Confirm tier-aware thresholds documented, σ-rescaled variance band labels correct, park_friendly listed as a component. Add cross-link to /boom-stack-explain. |
| sp-week-plan | YES_HIGH | P0 | Parallel agent adding week_boom rate. Once shipped: document the column, set thresholds for "boom-heavy week" call-out, and decide whether boom_stack tier influences bench-decision tiebreaker under cap. |
| fa-pickup-deep-dive | YES_HIGH | P1 | Should mention boom_stack tier + components (esp. park_friendly) in the SP section; hitter boom_stack tag now exists and should be referenced. Wider rp3 σ bands change the "CONSIDER vs SKIP" thresholds — review verdict logic. |
| fa-sp-pool | YES_HIGH | P1 | Selection should reference boom_stack tier as a secondary rank within FA SP shortlist; cross-link /stream-the-stack for daily streamer view. |
| pitcher-sustainability | YES_HIGH | P1 | rp3 σ widened ×2.41 → BUY-LOW / SELL-HIGH divergence threshold (currently 1.5 FP) may now over-fire. Re-anchor threshold or note "thresholds being recalibrated for σ rescale." |
| matchup-audit | YES_HIGH | P1 | Add check for boom_stack column presence + park_friendly resolution + HIGH-K tag rendering on matchup.html. |
| fa-monitor | YES_LOW | P2 | Signal taxonomy should mention boom_stack stack≥2 as a candidate trigger (or explicit "covered by /stream-the-stack" pointer). |
| hitter-compare | YES_LOW | P2 | Add hitter boom_stack tag to the comparison table once stable. |
| hitter-sustainability | YES_LOW | P2 | Cross-link hitter boom_stack as a complementary tag (not a sustainability replacement). |
| roster-health | YES_LOW | P2 | Could add "BOOM_STACK_HIGH" / "BOOM_STACK_LOW" as a SP alert type once tier-aware thresholds settle. |
| roster-audit | YES_LOW | P2 | Reference boom_stack in SP drop-candidate logic (low stack + low rp3 = stronger drop). |
| roster-deep-audit | YES_LOW | P2 | Orchestrator — add boom_stack into the agreement matrix. |
| league-deep-audit | YES_LOW | P3 | Optional 12th layer: boom_stack tier distribution per team. |
| breakout-sustainability | YES_LOW | P3 | Cross-link hitter boom_stack as a complementary surface. |
| refresh-and-commit-and-push | YES_LOW | P3 | Document new artifacts produced (stream-the-stack outputs, boom_stack columns). |
| refresh-matchup | YES_LOW | P3 | Confirm matchup.html re-render picks up new tags. |
| monday-morning | YES_LOW | P3 | Optionally chain /stream-the-stack into the Monday flow. |
| validate-feature | NO | — | Protocol unchanged; today's features were validated through it. |
| slump-or-decline | NO | — | Hitter slump logic untouched by today's shipping. |
| sp-archetype | NO | — | Process-based, independent of boom_stack/σ. |
| hitter-archetype | NO | — | Same — process-based. |
| rp-archetype | NO | — | RP boom_stack doesn't exist yet. |
| sp-breakout-signal | NO | — | Outcome-based; unrelated to stack tag. |
| sp-rehab-tracker | NO | — | MiLB rehab path, untouched. |
| sp-bench-mc | NO | — | MC over rp3 distribution; σ rescale flows through automatically but logic unchanged. |
| career-form-rank | NO | — | L150 PA xwOBA percentile only. |
| league-breakout-sustainability | NO | — | Sweep parallel to breakout-sustainability. |
| scouting-report | NO | — | Archetype trajectory only. |
| fa-replacement-pool | NO | — | Broad scan, rh3/rp3 join unchanged. |
| fa-rp-pool | NO | — | RP-only; boom_stack not applied to RPs. |
| fa-signal-to-decision | NO | — | Meta-chain unaffected. |
| forced-drop-planner | NO | — | Cap math unchanged. |
| pl-cross-reference | NO | — | External PL fetch only. |
| player-id-resolve | NO | — | Name-collision utility. |
| roster-verify | NO | — | Roster-membership precondition. |
| savant-compare | NO | — | Public Savant fetch only. |

## Summary

- Total audited: 37
- YES_HIGH: 7 (triangulate, stream-the-stack, sp-week-plan, fa-pickup-deep-dive, fa-sp-pool, pitcher-sustainability, matchup-audit)
- YES_LOW: 10
- NO: 20

## Top 3 by priority

1. **triangulate** — most visible decompose surface; must reflect current tag schema or it'll mislead.
2. **stream-the-stack** — brand new; needs first-week refinement and cross-links.
3. **sp-week-plan** — week_boom landing now; integration point with cap math.

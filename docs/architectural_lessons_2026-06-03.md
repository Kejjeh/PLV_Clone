# Architectural lessons — 2026-06-03 session

A long session shipped a substantial reframe of the projection engine.
These are the load-bearing lessons. Each maps to a specific commit or
validation report.

## 1. Point estimate alone is hubris — three layers replace one number

Old engine: rp3 → one FP number per pitcher.
New engine: rp3 → **point estimate + calibrated 50% interval + tier-aware
boom_stack + standalone display tags (HIGH-K ARM, eventually catcher_framing,
park_friendly is now component 4)**.

Eight layers in total. None of them tells you the exact FP. All of them
together tell you **where in the range to bet**. The user explicitly named
this shift: "we've been operating with a little bit of hubris thinking
we can predict exactly."

Lesson: when handing a single number to a user, ALWAYS also surface the
calibrated band + categorical tags. The single number lies; the layered
output is honest.

## 2. σ calibration is foundational — discovered as broken, fixed globally

`multi_year_sp_backtest.md` found `xfp_rp3_p25/p75` covered only 21.6% of
actual outcomes vs the 50% target. The σ was **2.41× too tight**.

Single global rescale (α=2.41) brought coverage to 51.7%. Tier-specific
calibration was tested (`sigma_heteroskedastic_search.md`) and rejected
— per-pitcher σ requires ≥30 starts to fit reliably, and at our sample
sizes the noise dominates any signal from features.

Lesson: **calibration before novelty.** Before adding any new component
or feature, verify the existing point estimate + band actually mean what
the engine claims they mean. We almost shipped 4 new features against
a 21.6%-coverage band.

## 3. DISPLAY TAG vs STACK COMPONENT — a real architectural distinction

We tested several signals as candidate boom_stack components AND as
standalone display tags. Three patterns emerged:

- **boom_stack COMPONENT**: must be process-change signal (delta-style),
  independent from existing components, must amplify boom rate within
  stack=3 cohort. Adds to the 0-N range.
- **DISPLAY TAG**: standalone signal that compounds with boom_stack.
  Often TYPE-style (talent, structural), independent of stack value.
  Examples: HIGH-K ARM (z-scored season K%), catcher_framing.
- **NEITHER**: fails both modes — reject (e.g., velo_trend, days_rest).

Rule of thumb: if it's a process change → test as component. If it's a
talent/context modifier → test as display tag. Don't double-count.

## 4. Wrong-axis trap — pf_HR vs pf_wOBA

Park factors are commonly cited as pf_HR (HR multiplier). The
`park_factor_boom_modifier.md` investigation found pf_HR is **non-monotonic**
on boom rate, while pf_wOBA is **monotonic**. Parks like LAD/PHI/MIL have
high HR rates but suppress overall offense — they look "hitter-friendly"
on HR but are "pitcher-friendly" on wOBA.

Lesson: always test the axis assumption. The "standard" metric in
literature is not always the correct metric for the prediction target.
The 9-rule protocol exists in part to catch this.

## 5. Tier amplification — signals can amplify (or INVERT) by tier

`boom_stack_by_tier.md` found `skill_spike` is **anti-predictive** at
backend/SP2-3 tiers (−3.4 / −4.1 pp boom edge) while being positive at
streamer (+2.7 pp) and ace (+3.1 pp).

The diagnosis (`skill_spike_anti_predictive_diagnosis.md`) identified
**sample-size noise** as the primary mechanism: established pitchers
have stable baselines that a 3-start window can't move; "spikes" are
mostly outcome variance that reverts. Switching to 5g window neutralizes
the anti-predictive sign at non-streamer tiers without sacrificing
streamer.

Lesson: when a signal has different relationships at different tiers,
don't assume one mechanism — diagnose first, then tune the window/threshold
to the regime that produced the underlying behavior.

## 6. Asymmetry — boom is predictable, bust is not

The `bust_stack_validation.md` investigation tried to mirror boom_stack's
3 components inversely. Result: stack=3 bust rate was only +3.7 pp over
baseline (vs the +9.4 pp lift on the boom side). Only 1 of 4 candidate
bust components cleared the Bonferroni gate.

Honest finding: bust outcomes are dominated by within-game noise, not
upstream process drift. Right-tail signals don't invert cleanly to
left-tail signals.

Lesson: don't assume bilateral symmetry between boom and bust. The
prediction surface for the right tail and left tail can have very
different structure.

## 7. Within-pitcher paired test — required validity check for context modifiers

`catcher_framing_boom_modifier.md` showed the raw Q5 vs Q1 boom edge
was +4.6 pp. But "good teams have good framers AND good SPs" could
explain that entirely as team-quality confound.

The within-pitcher paired test (same pitcher throwing to Q1 vs Q5
catcher across different games): **t=2.40, p=0.017, +3.06 pp causal
effect**. About 2/3 of the cross-section gap is real framing, 1/3 is
team selection.

Lesson: for any feature that depends on the player's context (catcher,
ballpark, lineup), run the within-player paired test before claiming
causation. Cross-section correlations include team-quality confound.

## 8. The 9-rule protocol earns its keep

In this session we tested 9 candidate features/signals:

| Candidate | Verdict |
|---|---|
| velo_trend (model feature) | REJECTED (saturated by existing features) |
| days_rest (model feature) | REJECTED |
| lineup_handedness_match | REJECTED (re-encodes team strength) |
| streamer_boom_stack_v1 | SHIPPED (Mode B PASS) |
| high_k_pitcher (boom_stack v2) | NEEDS_MORE_DATA / SHIPPED_AS_TAG |
| skill_spike_5g | SHIPPED (flat 5g flip) |
| skill_spike_tier_aware | REJECTED (flat 5g dominates) |
| bust_stack | REJECTED (magnitude fail) |
| heteroskedastic σ | REJECTED (CV r² negative) |
| hitter_boom_stack | SHIPPED |
| lineup_amp_hitter | SHIPPED (queued) |
| 2-start_week_amplification | SHIPPED (queued) |
| park_friendly (5th component) | SHIPPED |
| catcher_framing | SHIPPED_AS_TAG (queued) |

**6 of 13 promoted to engine**, 7 rejected. Without the framework, we'd
have shipped 11/13 and discovered the over-claims later. The Rule 9
requirement (full baseline, never stripped) is what catches the saturated
features cleanly.

Lesson: 50% rejection rate is healthy. If validation is showing 90%+
pass rate, the bar is too low.

## 9. Engine evolution by composition, not replacement

Today's commits modified the engine 6-8 times. Each change was
schema-additive — existing consumers kept working through every iteration.
The pipeline stayed live the whole session (predictions_history.csv has
10+ snapshots from today's rebuilds).

Lesson: when iterating on a live model, change schema additively unless
absolutely forced. Backwards-compat shims are cheap; broken downstream
consumers are expensive.

## What's queued for next session

- catcher_framing display tag (validated, spec'd, not wired)
- lineup_amp 4th hitter component (validated, spec'd, not wired)
- week_boom rate in sp-week-plan (validated, spec'd, not wired)
- Skills audit + memory updates (rate-limited, partial)
- New skill proposal: `/boom-stack-explain <player>` (decompose tag)
- Update CLAUDE.md to reference these lessons

## Commit pointers

- `8e8effd` park_friendly 5th component
- `9f8a629` 6-investigation research dump
- `4519b16` skill_spike 3g → 5g flip
- `3988463` HIGH-K ARM tag
- `(earlier)` σ rescale ×2.41, tier-aware boom_stack, hitter boom_stack,
  /stream-the-stack, refresh_dashboards step 4.6

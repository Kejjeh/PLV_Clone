# Triangulate canonical fixture review — 2026-06-06

## Purpose

Three of the five PR 1a test failures are the triangulate canonical fixtures
(`tests/test_triangulate.py::CANONICAL_CASES`). Per plan v11, this surface is a
**halt-for-user-approval gate**: implementer produces this memo and waits before
changing either fixture or routing.

Verdict shifts are below. None of the shifts indicates a routing bug; each is
consistent with the documented decision tree in
`.claude/skills/triangulate/SKILL.md` and reflects underlying data drift in
rh3/rp3, PL ranks, or archetype OVERALL scores between fixture-snapshot date
and 2026-06-06.

## Observed vs expected (2026-06-06 run)

| Player | Bucket | Fixture verdict_sub | Actual verdict | verdict_top change |
|---|---|---|---|---|
| Reid Detmers | SP | `BUY — archetype breakout` | `BUY — process upgrade` | BUY → BUY (reason_tag only) |
| Ryan Weathers | SP | `BUY — archetype breakout` | `MIXED — see profile` | **BUY → MIXED** |
| Casey Schmitt | H | `BUY — process upgrade` | `BUY — archetype breakout` | BUY → BUY (reason_tag only) |

## Per-case data + decision-tree trace

### Reid Detmers (SP)

```
PL Top100: #61
rp3:       #37  (overall is solid)
archetype: OVERALL 64, MT_RUSHMORE, TRENDING_UP, 3yr-slope +3.6, career-pct 75%
career arc: 2022:AVERAGE_4_5(50) → 2023:AVERAGE_4_5(54) → 2024:PURE_STUFF(54) → 2026:MT_RUSHMORE(64)
T+1: 13.41 fp/start
```

Decision-tree trace:
- Rule #1 (archetype_breakout): requires `(model_rank − PL_rank) > 50`. Here gap is
  `37 − 61 = −24`. **Does NOT fire** — model has already caught up to PL.
- Rule #2 (strong_hold): requires `PL <= 30 AND model <= 50 AND overall >= 55`.
  PL=61 fails the first clause. Does not fire.
- Rules #3, #4: do not fire.
- **Rule #5 (process_upgrade)** fires: `overall=64 >= 60 AND traj=TRENDING_UP AND model=37 <= 80`. ✓

**Interpretation**: legitimate verdict for current data. Detmers's model rank caught
up to where PL has him, eliminating the "model lagging PL" condition that
defines `archetype_breakout`. He is still a strong BUY — the reason_tag just
shifted to reflect that process leads outcomes rather than outcomes leading
process. verdict_top unchanged (BUY → BUY).

### Ryan Weathers (SP)

```
PL Top100: #34
rp3:       #68  (rep_d=-1.01 recform=-1.297 streamer tier)
archetype: OVERALL 56, PURE_STUFF, TRENDING_UP, 3yr-slope +4.5, career-pct 75%
career arc: 2021:FILLER(38) → 2023:WILD_MID(41) → 2024:AVERAGE_4_5(53) → 2026:PURE_STUFF(56)
T+1: 13.05 fp/start
```

Decision-tree trace:
- Rule #1 (archetype_breakout): `(model − PL) = 68 − 34 = 34`, NOT `> 50`. Does not fire.
- Rule #2 (strong_hold): PL=34 > 30. Does not fire.
- Rule #3 (PL_outcome_chase): `(model − PL) = 34`, NOT `> 60`. Does not fire.
- Rule #4 (model_anchored): gap is positive (model behind PL by 34), not `< −50`. Does not fire.
- **Rule #5 (process_upgrade)**: requires `overall >= 60`. Weathers's archetype OVERALL is **56, below threshold by 4 points**. Does NOT fire.
- Rules #6–7: do not fire (PL is not UR; archetype is present).
- Rule #8 (CAUTION): no triggers — traj is TRENDING_UP, not TRENDING_DOWN; label is PURE_STUFF (not in CAUTION list); career_pct=75% (not CAREER_LOW); velo is not FINESSE.
- **Rule #9 (MIXED — fallback)** fires.

**Interpretation**: Weathers's archetype OVERALL has drifted DOWN from a likely
60–62 at fixture-snapshot time to 56 today. That single 4-point slide is what
flipped the verdict from `process_upgrade` (≥60 threshold) to `MIXED` (no rule
fires). This is process drift in the data, NOT a routing bug — but it IS a
verdict_top regression (BUY → MIXED), which is the only one of the three that
crosses the top-level boundary.

The 4 candidate fixes (only the user can pick):
1. Accept MIXED and update the fixture. Verdicts move with data; this is the
   honest read for today.
2. Drop Weathers from the canonical set if you only want top-level-stable cases.
3. Lower Rule #5's archetype-OVERALL threshold from 60 to 55 (would impact
   other near-borderline SPs — needs validation).
4. Adjust the fixture to assert only `verdict_top in {BUY, MIXED}` for
   Weathers — accept that he was borderline and may oscillate.

### Casey Schmitt (H)

```
PL Top150: #50
rh3:       #101 (rep_d=-0.04 recform=-0.002)
archetype: OVERALL 63, CONTACT_POWER, TRENDING_UP, 3yr-slope +3.5, career-pct 75%
career arc: 2023:AVERAGE_HITTER(43) → 2024:ALL_OR_NOTHING(56) → 2025:AVERAGE_HITTER(54) → 2026:CONTACT_POWER(63)
T+1: 0.569 fp/PA
```

Decision-tree trace:
- **Rule #1 (archetype_breakout)** fires: `(model − PL) = 101 − 50 = 51 > 50`. ✓
  Traj TRENDING_UP. PL and model both integers.

**Interpretation**: model rank has slipped further from PL (gap widened past the
50-rank breakout threshold) since the fixture was set. Rule #1 now fires before
Rule #5 would have. The fixture's `process_upgrade` was true when the gap was
just under 50; today it's 51. Schmitt remains a BUY, reason_tag flipped.
verdict_top unchanged (BUY → BUY).

## Recommended actions (await user decision)

**Detmers (BUY → BUY reason shift)**: low-stakes fixture update. Change
`verdict_sub` from `BUY — archetype breakout` to `BUY — process upgrade` OR
relax the canonical fixture to assert only `verdict_top == 'BUY'` (more
robust to data drift).

**Weathers (BUY → MIXED top-level regression)**: requires user judgment.
Recommended path: accept MIXED and update fixture, since the data legitimately
no longer supports BUY (archetype OVERALL fell below the 60 threshold). Document
in `lessons-from-triangulate.md` that the canonical fixture is a point-in-time
snapshot and should be reviewed weekly.

**Schmitt (BUY → BUY reason shift)**: same as Detmers. Update `verdict_sub` to
`BUY — archetype breakout` OR relax to `verdict_top == 'BUY'`.

**Cross-cutting consideration**: tightening the fixture to `verdict_top` only
(BUY/HOLD/CAUTION/FADE/MIXED) would eliminate this entire class of false
failures while still catching the regressions that matter (e.g., a player who
should have been BUY is now FADE). Recommended as a separate small PR.

## What this memo does NOT do

- Does NOT modify `tests/test_triangulate.py::CANONICAL_CASES`.
- Does NOT modify `scripts/xfp/run_triangulate.py` or `lib/triangulate_core.py`
  routing.
- Does NOT change the live verdicts surfaced to the user via `/triangulate`.

The 3 triangulate tests remain in their current FAIL state until user picks
one of the recommended actions above. PR 1a's other two failures (the
`predict_rotation_starts` test and the slump-or-decline YAML scanner) ARE
fixed in this commit.

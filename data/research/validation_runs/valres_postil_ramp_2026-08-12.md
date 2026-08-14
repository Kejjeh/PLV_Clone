# Study B results — Post-IL hitter performance ramp by injury class

Run 2026-08-14 against the contract in `prereg_availability_suite_2026-08-12.md`
(Study B). No gate was revised after seeing results. Companion data:
`valres_postil_ramp_2026-08-12.csv` (653 rows, one per qualifying activation).

## Verdict (gates applied exactly as registered)

**NO class ships a POST-IL RAMP tag. The pooled effect also fails.**
No class's player-clustered 95% CI excludes 0; only two classes even reach the
|deficit| >= 0.04 FP/PA magnitude bar, and both are in the WRONG direction
(better after return, n.s.). Per the prereg: classes that fail simply carry no
tag — nothing ships, Rule 13 never engages.

## Per-class table (deficit = post FP/PA − pre FP/PA; negative = worse after return)

| class | n act | n players | mean deficit | 95% CI (player-clustered) | CI excl 0 | \|d\|>=0.04 | gate |
|---|---|---|---|---|---|---|---|
| hand_wrist_finger | 89 | 75 | **+0.0460** | [−0.0035, +0.0967] | no | yes | **NO-TAG** |
| hamstring_quad_calf | 118 | 98 | −0.0318 | [−0.0767, +0.0132] | no | no | **NO-TAG** |
| back_oblique_core | 127 | 101 | −0.0253 | [−0.0758, +0.0272] | no | no | **NO-TAG** |
| arm_shoulder_elbow | 55 | 53 | +0.0547 | [−0.0117, +0.1168] | no | yes | **NO-TAG** |
| other | 165 | 129 | −0.0370 | [−0.0771, +0.0022] | no | no | **NO-TAG** |
| unknown (not a registered class) | 99 | 86 | +0.0218 | [−0.0206, +0.0664] | no | no | reported only |
| **POOLED (all)** | **653** | **354** | **−0.0059** | [−0.0255, +0.0137] | no | no | **NO-TAG** |

Classification power check (registered): unknown = **15.2%** of qualifying
activations (13.9% of all hitter stints) — far below the 60% underpowered
threshold, so the per-class leg was fully powered and gated. It failed on the
merits, not on classification coverage.

Context: pooled pre FP/PA 0.4960 vs post 0.4893; 325/653 (49.8%) of deficits
negative — a coin flip. Per-season qualifying counts are balanced
(2021-2025: 129/135/136/121/132). Bootstrap = 1000 reps, percentile CI,
clusters = player (pid), seed 20260812.

## Interpretation

The registered hypothesis (hitters underperform their own baseline in the
first 15 games back, hand/wrist worst) is not supported at any gated
magnitude, and the hand/wrist prediction is directionally CONTRADICTED
(+0.046, i.e. mildly better after return, n.s.). Among qualifiers — hitters
healthy enough to log 40 PA in their first 15 games back — there is no
exploitable post-IL discount. Do not apply any post-IL haircut in boards or
verdicts on the basis of this study.

## Pipeline (as registered, with one documented data-source substitution)

1. **Transactions**: MLB Stats API `/v1/transactions` per season 2021-2025
   (Mar 1 – Oct 5, sportId=1). typeCode `SC` mentioning "injured list":
   4,851 placements, 3,055 activations, 681 transfers (ignored — a 15→60-day
   transfer is not a new stint). Each activation paired with the most recent
   prior placement, same season → 2,699 paired stints; 2,152 placements never
   activated in-window (season-enders / next-year returns) and 356 activations
   without an in-window placement (pre-Mar-1 or prior-season placements)
   dropped.
2. **Injury class**: keyword classification (word-boundary regex) of the
   description text after "injured list", precedence hand_wrist_finger >
   hamstring_quad_calf > back_oblique_core > arm_shoulder_elbow > other
   (other = injury text present but outside the 4 named classes, e.g. knee /
   ankle / concussion); no injury text → unknown. 95.5% of placement
   descriptions carry injury text. Spot-checked correct on samples of all 6
   buckets. `lat` was binned to back_oblique_core (anatomically trunk).
3. **Hitters only**: people API `primaryPosition.code != '1'`; TWP (Ohtani)
   kept, per prereg "position != P". 1,248 hitter stints, 544 players.
4. **Per-game lines — deviation, declared**: the prereg says
   "statcast-derived box lines," but statcast per-pitch rows cannot attribute
   R (requires baserunner-state tracking) or SB (event attaches to the
   runner, not the batter) to a batter-game — the repo's own canonical
   `build_hitters_multiyr.py` treats the MLB Stats API as authoritative for
   R/RBI/SB for exactly this reason. Per-game lines therefore come from the
   MLB gameLog (gameType R only), scored with the canonical
   `LeagueScoring.score_hitter_game` (exact BrownU formula:
   R + TB + RBI + BB + HBP + SB − K). Cross-check: gameLog PA matched the
   statcast distinct-(game_pk, at_bat_number) count exactly on sampled
   batter-games. This substitutes a strictly more exact source of the SAME
   registered quantity; metric, windows, PA gates, and decision thresholds
   are untouched. Omitting R/SB (pure-statcast) would have systematically
   shrunk measured deficits — i.e. this substitution is anti-conservative for
   NO-TAG, and it still gated NO-TAG.
5. **Legs**: pre = last up-to-30 games strictly before placement date
   (mean 27.1 g / 103.1 PA); post = first up-to-15 games on/after activation
   date (mean 14.8 g / 56.5 PA); >= 40 PA both legs (the registered gate);
   both legs same-season. 653 of 1,248 stints qualify (46-58% by class).

## Caveats (honest, none gate-relevant)

- **Survivorship/selection**: qualification demands ~56 PA in the first 15
  games back — hitters who returned and immediately re-injured, were benched,
  or were eased back in part-time roles are under-represented. The estimate is
  "ramp GIVEN a regular's workload on return," which is exactly the roster-
  decision population, but it cannot see the worst returns.
- **Pre-leg contamination**: the 30 pre-placement games can include games
  played hurt just before the IL trip, which deflates the pre baseline and
  shrinks measured deficits. A buffer variant (e.g. excluding the final 7 days
  pre-placement) was NOT registered and was not run — flagging it as the one
  plausible re-open if this question returns.
- Qualifying stints skew short (median IL 13-17 days by class); long 60-day
  rehabs mostly fail the same-season 15-game/40-PA requirement, so this says
  little about season-spanning rehabs (the Study C population).
- Activations after Oct 5 are outside the pull window (negligible: a post-Oct-5
  activation cannot log 15 games anyway).
- FP/PA is context-inclusive (R/RBI depend on lineup); paired same-player
  differencing removes most of it, but a team's September lineup context can
  differ from June's.

## Files

- Deliverable CSV: `data/research/validation_runs/valres_postil_ramp_2026-08-12.csv`
- Working artifacts (scratchpad, session-local): transaction JSONs, stint
  tables, 997 cached gameLogs, `build_stints.py` / `compute_legs.py` /
  `bootstrap_gate.py`.

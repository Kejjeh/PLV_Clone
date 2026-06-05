---
name: opp-watch
description: Predict an opponent's next roster move (transact / add / drop) before they make it. Uses per-team behavioral profiles derived from 71 days of transaction history + the triangulate engine. Backtest-validated: under Late Night Bettsing's profile, their signature archetype_breakout adds (Max Meyer, Ryan Weathers, Ashcraft) surface in the predictor's top-12. Use when the user asks "what will X do next", "is Y going to drop Z", "predict opponent moves", "snipe opponent FA targets", or as part of Monday-morning planning.
---

# opp-watch

You are surfacing an opponent's likely next roster move *before* they make it,
so the user can either snipe the same FA add first or anticipate their drops.

## Why this skill exists

The 2026-06-04 brain-reconstruction of Late Night Bettsing showed their adds
cluster on Monday nights (Pitcher List refresh) and consistently target
TRENDING_UP archetypes our career-anchored model lags on (Weathers PL #34 /
mdl #204 added 5/4; Max Meyer PL #31 / mdl #211 added 5/25). That's a
reproducible fingerprint, not luck. The predictor turns that fingerprint into
a daily prediction.

The same engine works for every opponent. Each manager has a different
hardcoded profile (PL-weighted, outcome-chaser, save-chaser, asleep-at-the-
wheel) derived from the manager-rating audit. The same feature set with
per-team weights gives per-opponent behavioral predictions.

## Engine

`scripts/xfp/opponent_action_predictor.py`. Two-stage:

1. **TRIGGER** — P(team T transacts in next 24h). Uses recency-weighted
   base rate × day-of-week multiplier. Backtest on 14-day holdout shows the
   absolute Brier is still imperfect vs constant-mean baseline (sparse-event
   problem at 71 days of data), but the *relative ordering* across teams is
   directionally correct.

2. **TARGET — ADD** ranking over verified FAs, scored per the team's
   behavioral profile (PL rank weight, archetype trajectory weight, model
   rank weight, outcome-heat weight, role-change weight).

3. **TARGET — DROP** ranking via marginal-upgrade framing: a roster player
   is droppable if a better FA in the same bucket is available AND the
   roster player has weak intrinsic signals.

## Usage

```bash
# Single opponent — the standard call
python scripts/xfp/opponent_action_predictor.py --team "Late Night Bettsing" --top 6

# All 8 teams
python scripts/xfp/opponent_action_predictor.py --all-teams --top 3

# Other opponents (matched by exact ESPN team name)
python scripts/xfp/opponent_action_predictor.py --team "Frendy's Fantastic Team"
```

Output format per team:
- Profile weights (their behavioral fingerprint)
- TRIGGER probability + components
- Top-N ADD candidates (player, bucket, PL rank, model rank, archetype traj, our verdict)
- Top-N DROP candidates (player, bucket, model rank, draft round, slot, verdict)

## When to invoke

- **Monday morning** as part of the weekly read — combine with `/monday-morning`
- After a major IL event in the league (multiple teams' rosters destabilized)
- Before placing a FAAB claim, to check if a high-volume opponent (Frendy,
  Solomon) is likely to bid against you on the same player
- When user asks "what will X do next" / "is Y going to drop Z" / similar

## Limitations and honest framing

1. **v1 uses hardcoded behavioral profiles**, not panel-fitted weights. The
   data infrastructure (PL rank history + player projection history panels)
   started accumulating 2026-06-04. Once we have ≥4 weeks of dated snapshots
   (~2026-07-02), refit weights from data and remove the hardcoded `PROFILES`
   dict in the engine.

2. **Δ-PL-rank and Δ-model-rank features are not yet active.** They're the
   single most important predicted-add signals based on the brain-recon
   analysis. They require panel data we just started persisting. Until then
   the predictor uses current rank/traj — directionally correct but blind to
   week-over-week movement.

3. **Trigger Brier > null baseline** on the small backtest window. The
   *relative ordering* of teams is the useful output (Frendy more likely
   than Treasure Island), not the absolute probability. Don't read the
   trigger P-value literally below 0.85 — read it as "high / medium / low."

4. **The validation that worked:** under each team's behavioral profile,
   their actual historical adds rank in our predictor's top-60 about 38%
   of the time (~3x random). Late Night's Meyer and Weathers — the
   signature archetype_breakout cases — surface at #10 and #11.

## Anti-patterns

- **Don't trust the trigger probability as calibrated.** Use it for relative
  comparison only. If you need a calibrated probability, retrain once panels
  have 6+ months of data.
- **Don't ignore the profile description in the output.** If you find the
  ranking surprising, check whether the manager's profile weights make sense
  — they're declarative and editable in `PROFILES = {...}` at the top of
  the engine.
- **Don't claim a player will definitely be added/dropped.** Surface the
  prediction with explicit "based on observed pattern" framing. Managers
  deviate; this is a probability layer.

## Related

- `/triangulate` is the per-player engine the predictor consumes.
- The manager-rating audit (run via the league-wide triangulate flow) is
  what produced the initial profile weights.
- `/fa-pickup-deep-dive` for a deeper read on a specific predicted-add
  candidate before claiming.

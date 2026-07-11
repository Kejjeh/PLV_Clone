---
name: season-sim
description: CHAMPIONSHIP-EQUITY layer for the rest of the BrownU season — the strategy skill above /matchup-leverage. Where /matchup-leverage answers "can I win THIS week and should I play boom or floor", /season-sim answers "what are my playoff/title odds, and how aggressive should I be for the rest of the season" — because the marginal value of a weekly win is NOT constant (it depends on the standings race) and the value of weekly VARIANCE flips sign with seeding safety. Builds each of the 8 teams' weekly-total FP distribution from its CURRENT roster (rate x volume layer + empirical per-player variance, fitted as a normal from a ~2k-draw representative-week MC, blended with played-week actuals, roster-churn haircut), then simulates the remaining regular season + the real 6-team playoff bracket ~5k times with ESPN's actual seeding tiebreak (H2H record then points-for). Outputs per team P(playoffs) / seed distribution / P(final) / P(title); for Josh additionally the value-of-a-win curve (dTitle per period result — the number that prices this week's matchup in title equity), the aggressiveness dials (dTitle per +2 FP weekly mean, dTitle per +10% weekly sigma), and a plain-English strategy directive (spend FAAB now vs hoard for playoffs; boom vs floor roster construction). Rule 13 decision layer — never moves rh3/rp3/rprs2. Triggers — "playoff odds", "title odds", "season sim", "how aggressive should I be", "should I sell the future", "is this week worth FAAB", "championship equity", "what seed will I get", "am I making the playoffs".
---

# season-sim

You are running the **championship-equity layer** for the rest of the
BrownU season. THE INSIGHT this skill owns: `/matchup-leverage` (its
weekly sibling) optimizes P(win) for the CURRENT period, but the value
of that win — and of variance itself — depends on the standings race:

| Situation | Marginal weekly win | Weekly variance |
|---|---|---|
| Playoff spot contested | worth several pp of title equity — spend NOW | helps entry only if trailing the cut line |
| Entry safe, seeding live | worth little for entry, some for seed/bye | usually a LIABILITY (protecting a position) |
| Entry safe, bracket underdog | worth little | an ASSET in the bracket — tilt boom AFTER clinching |
| Longshot | entry is the bottleneck | maximize everywhere |

**Rule 13 statement:** this is a DECISION layer only. It never touches
rh3/rp3/rprs2/Blended xFP, never re-ranks a projection, and its
probabilities/sensitivities are strategy weights, not forecasts. The
headline projection stays the model's.

## Trigger phrases

"playoff odds", "title odds", "championship odds", "season sim",
"simulate the season", "how aggressive should I be", "should I sell the
future", "is this week worth FAAB", "championship equity", "what seed
will I get", "am I making the playoffs", "should I punt this week".

## How to run

```bash
# Full live run (~2-4 min; live ESPN pulls + roster MC + 3x 5k season sims)
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/run_season_sim.py

# More/fewer season sims, different seed, heavier team-strength MC
... run_season_sim.py --sims 10000 --seed 11 --team-sims 4000
```

Machine-readable output: `data/outputs/season_sim.json`.

## What the engine does

1. **STATE** — live standings (W-L from `team.wins`, points-for summed
   from played `team.schedule` box scores), remaining regular-season
   matchups per period, live WTD scores for the in-progress period, and
   the playoff structure read from ESPN settings (BrownU 2026: 6 of 8
   teams; rounds = matchup periods 21 [1 wk], 22 [2 wks], 23 [2 wks];
   `playoff_seed_tie_rule = H2H_RECORD`, then points-for).
2. **TEAM STRENGTH** — per team, a weekly-total Normal(mu, sd) fitted
   from one ~2k-draw representative-week roster MC using the validated
   rate x volume layer: hitters = rh3 per-PA x volume PA/team-game
   (top 13 healthy by weekly mean; BE counts active, only IL/injury
   states zero a player); SPs = rp3 per-start x SP-volume GS/team-game
   with the period SP-start cap inside each draw (resolve per period via
   `resolve_period_meta(league, period)['sp_cap']` from
   `scripts.xfp.lib.period_meta` — 10 standard week, but 16 for the ASG
   block / 20 for a 2-week playoff round, not a flat 10); RPs = rprs2 RoS/week
   (top 4). Per-player variance is the empirical boxscore bootstrap
   blended with model sigma — the same `_blend_draws`/`emp_series`
   machinery imported from `run_matchup_leverage.py`. The MC mean is
   rescaled to the league's real weekly-FP scale (`calibrate_means`
   from `monte_carlo.py`) and blended 50/50 with the team's own
   played-week mean/SD (manager behavior lives in the empirical half),
   then a roster-churn haircut shrinks mu 15% toward the league mean
   and inflates sd 5%.
3. **SIMULATE** — ~5k seasons. The current period finishes from live
   WTD + the remaining-days fraction of the weekly distribution; future
   periods are full weekly draws; wins/points-for/pairwise-H2H
   accumulate; seeding = wins, then H2H record within the tie group,
   then points-for; the 6-team bracket (1-2 byes; R1 3v6 + 4v5; semis
   1 vs w(4v5), 2 vs w(3v6); multi-week rounds = Normal(mu*L,
   sd*sqrt(L))) plays out with the same distributions.
4. **JOSH SENSITIVITIES** — (a) value-of-a-win curve: P(title | win
   period p) − P(title | lose period p) for every remaining period —
   the number that connects to `/matchup-leverage` (its P(win) tells
   you whether you CAN win the week; this tells you what the week is
   WORTH); (b) mean dial: dTitle/dPlayoffs per +2 FP of true weekly
   strength (the equity price of any add/trade); (c) sigma dial:
   dTitle/dPlayoffs per +10% weekly sigma (the aggressiveness dial —
   run with common random numbers so the difference is low-noise).
5. **STRATEGY DIRECTIVE** — plain guidance synthesized from the bands:
   SAFE (>=95% playoffs) bank floor / hoard FAAB; MOSTLY SAFE (85-95%)
   take cheap wins, start playoff positioning; CONTESTED (30-85%)
   spend now; LONGSHOT (<30%) maximize variance. Variance guidance
   distinguishes the SPLIT case (helps title, hurts entry -> floor
   until clinched, boom in the bracket).

## Interpreting the output

- **P(playoffs) / P(title) per team are the headline.** Sum of
  P(title) is exactly 1 by construction.
- **The value-of-a-win curve is the bridge to weekly tactics:** if this
  week's dTitle is 2.5pp and period 20's is 1.0pp, a stream/FAAB burn
  is worth ~2.5x more this week. Feed the current week's number to
  `/matchup-leverage` when deciding how hard to chase its
  Delta-P(win) moves.
- **The mean dial prices roster moves in equity:** a +2 FP/week upgrade
  (e.g. a real SP add over replacement) = the printed pp of title
  equity. Compare trade/FAAB costs against it.
- **The sigma dial is the boom/floor policy:** positive -> prefer
  high-variance construction; negative -> floor; split -> floor until
  the spot is clinched, then boom.
- dTitle values carry MC noise ~ +/-0.5-1pp at 5k sims (conditional
  slices are smaller samples); treat small differences as ties.

## Relationship to sibling skills

- `/matchup-leverage` — the weekly tactical layer (P(win) THIS period +
  Delta-P(win) per move). season-sim supplies the exchange rate that
  turns its weekly win probability into title equity. Consistency
  check: season-sim's current-period P(win) should land within a few
  pp of matchup-leverage's (coarser team-level normal vs player-level
  event sim — a small gap is expected and reported in the output).
- `monte_carlo.py` — the ancestor playoff MC (empirical means + IL
  phasing). season-sim adds the roster MC strength model, real H2H
  seeding, per-round playoff lengths from settings, and the
  championship-equity sensitivities. Both can be run; large
  disagreement usually means a roster changed faster than played-week
  averages.
- `/playoff-team-build`, `/sp-stash-finder`, `/playoff-war-room` — the
  ACTION skills once the directive says "position for playoffs".
- `/forced-drop-planner`, `/fa-monitor` — the action skills when the
  directive says "spend now".

## Known limitations (be honest about these)

- Weekly totals are team-level normals — no within-week player
  correlation beyond what the roster MC baked into mu/sd, no schedule
  strength (opponent MLB matchups), no 2-start-week lumpiness at the
  season scale.
- Currently-IL players are EXCLUDED from team strength with no return
  phasing — a team stashing elite IL returners is underrated
  (cross-check `/sp-rehab-tracker`; `monte_carlo.py` has IL phasing if
  that's the question).
- Roster-churn haircut (15% shrink toward mean, +5% sd) is an
  assumption, not a fitted value.
- marcel_il SP rows carry the suppressed rp3 prior (gotcha #1) —
  opposing rosters holding such arms are slightly underrated.
- Seed tiebreak implements wins -> H2H within group -> PF; ESPN's full
  multi-way circular resolution can differ in rare knots.
- Playoff strength assumes the same distributions as today — no
  September call-ups, fatigue, or shutdowns.

## When NOT to use

- "Can I win THIS week / boom or floor TODAY" -> /matchup-leverage
- Which specific player to add/drop -> /fa-pickup-deep-dive,
  /triangulate, /streamer-precision-board
- Building the actual playoff roster -> /playoff-team-build,
  /playoff-war-room

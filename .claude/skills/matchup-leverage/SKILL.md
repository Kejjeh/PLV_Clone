---
name: matchup-leverage
description: Win-probability STRATEGY layer for the current H2H matchup — the skill that tells every other skill WHICH OBJECTIVE to optimize. Every other lens maximizes expected FP, but BrownU H2H is won by P(my_total > opp_total); when TRAILING variance is an ASSET (prefer boom/bust plays), when LEADING variance is a LIABILITY (prefer floor), when CLOSE E[FP] is approximately right. Monte-Carlo simulates the rest of the scoring period (~10k draws; per remaining player-game the FP draw bootstraps the player's empirical boxscore game-log distribution, Bayesian-blended with the model mean/sigma when history is thin; SP starts are event-level with the chronological 10-start cap inside each trial and rotation-gap starts occurring at p=0.80), outputs P(win) + score distribution + dP(win)/d(variance), then scores each ACTIONABLE decision in Delta-P(win) — NOT Delta-E[FP]: (a) hitter sit-priority, (b) SP cap-bench scenarios, (c) top-3 FA streamer adds. Rule 13 decision layer — never moves rh3/rp3/rprs2. Triggers — "can I win this week", "what are my odds", "should I go boom or floor", "matchup strategy", "I'm down 40 points", "protect my lead", "win probability", "leverage", "am I drawing dead this week".
---

# matchup-leverage

You are running the **win-probability strategy layer** for the current
BrownU matchup. THE INSIGHT this skill owns: every other skill in this
repo maximizes expected FP, but the H2H objective is
**P(my_total > opp_total)** — and the mapping from FP to wins depends on
game state:

| Regime | P(win) | Variance is | Prefer |
|---|---|---|---|
| TRAILING | < 40% | an ASSET | boom/bust: high-sigma hitters, high boom% SPs, upside streamers |
| CLOSE | 40-60% | ~neutral | E[FP] — the normal lens stack is already right |
| LEADING | > 60% | a LIABILITY | floor: SAFE-tier sp_floor, low bust%, no speculative streams |

**Rule 13 statement:** this is a DECISION layer only. It never touches
rh3/rp3/rprs2/Blended xFP, never re-ranks a projection, and its
Delta-P(win) numbers are decision weights, not forecasts. The headline
projection stays the model's.

## Trigger phrases

"can I win this week", "what are my odds", "should I go boom or floor",
"matchup strategy", "I'm down 40 points", "protect my lead", "win
probability this week", "matchup leverage", "am I drawing dead",
"should I play it safe or swing".

## How to run

```bash
# Full live run: state + MC + regime + Delta-P(win) advice (~2-5 min, live ESPN/MLB pulls)
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/run_matchup_leverage.py

# Just P(win) + regime (skip the advice scan)
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/run_matchup_leverage.py --simulate-only

# More draws / different seed
... run_matchup_leverage.py --sims 20000 --seed 11

# Calibration smoke test against closed periods (honesty check)
... run_matchup_leverage.py --calibrate auto        # last 2 closed periods
... run_matchup_leverage.py --calibrate "15,16,17"  # explicit periods
```

Machine-readable output: `data/outputs/matchup_leverage.json`
(and `matchup_leverage_calibration.json` for the smoke test).

## What the engine does

1. **STATE** — `get_matchup()` (live ESPN box score = the roster-verify;
   never label anyone MINE from session memory), week window via
   `_today_et()` Monday->Sunday, schedules (ESPN primary / MLB fallback),
   per-player remaining units via the dashboard's `project_player`
   (neutral adjusters), role-aware SP bucketing via
   `detect_pitcher_role` (gotcha #8), banked SP starts from the boxscore
   parquet (role-correct `gs` flag), cap_remaining = 10 - banked.
   BE slots count as active (gotcha #7 — Josh activates healthy bench
   daily; only IL/IR slots and IL injuryStatus zero a player).
2. **MONTE CARLO** — ~10k sims. Hitters: n remaining games, each game FP
   drawn from the player's last-25 empirical game log (boxscore parquet,
   mlbam-keyed) blended with N(model mean/g, model sigma/g) at weight
   n_emp/(n_emp+8). RPs: appearances ~ Binomial(remaining team games,
   app_rate) with empirical fp_rp draws (SV/HLD credit included). SPs:
   event-level starts (confirmed + rotation-gap predicted at p=0.80),
   empirical last-15-start bootstrap blended with the rp3 per-start
   mean/sigma, rescaled to the dashboard's matchup-adjusted per-start EV,
   chronological 10-cap applied INSIDE each trial. marcel_il arms lean
   parametric automatically (no 2026 start history = no empirical weight).
3. **Variance sensitivity** — re-sims with my remaining-FP deviations
   scaled +/-20%: the sign of dP(win)/dVar is the regime confirmation
   (trailing => positive: more variance helps).
4. **ADVICE (Delta-P(win), not Delta-E[FP])** —
   (a) hitter sit-priority: Delta-P(win) of zeroing each hitter (which
   13 of N healthy hitters should score; least-costly sit first);
   (b) SP cap-bench scenarios per remaining start, tagged with empirical
   boom%/bust% (lib/boom_bust cutoffs SP 17/5) and sp_floor tier;
   (c) FA streamer adds: free_agents(size=2000) x all-30 probable
   scan, Delta-P(win) of adding the start under the cap, regime-aware
   tiebreak (TRAILING sorts boom% up, LEADING sorts bust% down).

## Interpreting the output

- **P(win) and regime are the headline.** The Delta-P(win) moves are
  ranked levers, usually fractions of a point to a few points each —
  small numbers are HONEST (one roster move rarely swings a week).
- **TRAILING:** accept negative-E[FP] swaps if they buy variance
  (start the 35%-boom / 30%-bust arm over the steady 10-FP one; stream
  the upside lottery ticket). A -0.5 FP, +1.2pp P(win) move is GOOD.
- **LEADING:** the mirror — bench the volatile arm even at slight E[FP]
  cost, prefer SAFE floor_tier, don't stream speculatively into a lead.
- **CLOSE:** defer to /pregame-check and /sp-week-plan verdicts as-is;
  E[FP] ranking is approximately optimal.
- **dP(win)/dVar** near zero with P(win) extreme (>90% / <10%) means the
  matchup is effectively decided — spend the week positioning for NEXT
  period instead (see /sp-week-plan, /fa-monitor).

## Relationship to sibling skills (the objective router)

- `/pregame-check` — daily START/CAP-BENCH verdicts. Run
  matchup-leverage FIRST: its regime tells pregame-check whether a
  Tier-B-flagged high-boom arm is a keep (TRAILING) or the first bench
  (LEADING). The validated conservative v2 bench rules still gate the
  rare CAP-BENCH; leverage only re-orders within what those rules allow.
- `/sp-week-plan` — Monday cap budgeting maximizes E[FP] across 10
  starts; leverage re-scores the marginal start in P(win) space when the
  matchup is lopsided.
- `/sp-bench-mc` (sp_bench_mc.py) — the SP-only ancestor of this engine
  (same blend-prior MC idiom); matchup-leverage generalizes it to the
  full roster + regime advice.
- `/stream-the-stack` / `/fa-sp-pool` — candidate generators; leverage
  is the objective function that picks WHICH candidate profile fits the
  regime.
- `/boom-bust-history` — the display lens for the same empirical
  distributions this engine resamples.

## Known limitations (be honest about these)

- Delta-P(win) values carry MC noise ~ +/-0.5pp at 10k sims; treat
  moves inside that band as ties and fall back to E[FP]/regime logic.
- FA adds are scored WITHOUT modeling the corresponding drop; route the
  actual transaction through /fa-replacement-pool or
  /forced-drop-planner.
- Hitter "swaps" are modeled as marginal zero-outs (BE counts active),
  not slot-by-slot daily eligibility puzzles.
- WTD score and "remaining games incl. today" can double-count a game
  already scored today (same convention as the matchup dashboard).
- Calibration mode uses period-end lineups and counts all MLB games by
  rostered players (a passive opponent's bench days inflate their sim
  side slightly).

## When NOT to use

- Single-player add/drop verdict -> /fa-pickup-deep-dive, /triangulate
- Daily pre-lock start/bench -> /pregame-check (leverage sets the
  objective, pregame-check makes the call)
- Season-long roster construction -> /xfp-board, /playoff-team-build

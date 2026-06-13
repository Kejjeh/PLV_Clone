---
name: trade-target-scan
description: Scan opponent rosters for sell-bait (live_marginal < -10) and ask-targets (live_marginal > +30), paired with behavioral pitch templates per opponent's manager profile (OUTCOME_CHASER / IMPULSIVE_CHURNER / PL_PROCESS_FOLLOWER / etc). Built on Phase 2+2.5 live_marginal across H/SP/RP plus opponent_profiler. Use when the user asks "who should I trade for/away", "trade target scan", "find trade opportunities", "sell-high candidates on other teams", or before opening trade negotiations. Engine: scripts/xfp/trade_target_scan.py.
---

# trade-target-scan

You are surfacing concrete trade opportunities across the BrownU 8-team league
by combining `live_marginal` (Phase 2+2.5 — every player's FP gap vs the best
available FA at their position/role) with opponent behavioral profiles
(opponent_profiler) to recommend per-opponent trade pitches.

## Why this skill exists

Until 2026-06-05, trade asks were vibes-based — "Solomon has a lot of decliners,
pitch him a swap." With Phase 2+2.5 shipped, every player on every roster has
a measurable live_marginal in fp/season. Combined with the manager-profile
behavioral fingerprints (Frendy = OUTCOME_CHASER takes PL top-50 bait,
Late Night = PL_PROCESS_FOLLOWER won't bite without genuine value), we can
now propose **trades anchored in numbers** with **pitches anchored in opponent
psychology**.

## Engine

`scripts/xfp/trade_target_scan.py`

```bash
# Scan all 7 opponents
python -X utf8 scripts/xfp/trade_target_scan.py

# Single opponent
python -X utf8 scripts/xfp/trade_target_scan.py --opponent "Frendy's Fantastic Team"

# With positional gap filter (only show targets at a position you need)
python -X utf8 scripts/xfp/trade_target_scan.py --my-position SS
```

## What it surfaces per opponent

### Sell-bait — their players you might ask for
Filter: `live_marginal < -10` (DOWNGRADE or ACTIVE_LOSS). These are players
the opponent is holding at a value loss vs the live FA pool. They're emotionally
attached to draft capital or recent narrative; the live_marginal proves they're
losing FP/season.

### Ask-targets — their stars you'd want
Filter: `live_marginal > +30` (OWN_THE_ROLE / OWN_THE_SLOT). These are players
your roster would meaningfully upgrade with. Auto-gated by your positional
gap — only shows asks at positions where you have a weaker player.

### ⚠ ROLE-RISK reliever sell-high surface (rp-decline — engine-wired)

**The killer app for the RP side.** For every reliever on an opponent's roster,
the engine joins the validated `/rp-decline` convergence tier (via
`rp_decline_model.tier_map()`). Any reliever that is **ROLE-RISK** *and still has
a role to lose* (to-date sv+hld/app ≥ 0.12) surfaces in a dedicated block:

```
### ⚠ ROLE-RISK relievers on this roster → sell-high candidates
  - Emilio Pagán (closer) — velo YoY -1.6, 2/3 legs converged. Their owner
    should sell while saves/holds still land; for YOU this is a do-NOT-acquire
    (role likely to crater). ...
```

Why it matters: a ROLE-RISK closer is a **sell-high-NOW** candidate — his velo is
declining YoY AND his skill/role-share is slipping, the convergence that precedes
the −38% FP-crater when the manager strips the role. **Trade him while he still
has saves.** As a *trade-ask* target it flips to a **do-NOT-acquire** flag (you'd
be buying a role about to vanish). The `rp-decline` tier is also appended as a
column to the sell-bait table so you can see a leaking-value RP that's *also*
ROLE-RISK at a glance.

**Honest caveat (carry it every time):** rp-decline is **weaker/noisier than
`/sp-decline`** — velo-decline partial-r +0.112 (≈half the SP whiff/K signal) and
role loss is **~1/3 manager-driven** (AUC 0.683), so it **tilts the odds, it does
not predict**. It is a **Tier-B context/watch flag — it NEVER moves rprs2 or
live_marginal** (CLAUDE.md #13). Always confirm a flagged arm via `/triangulate`
+ `/rp-decline --players "X"` before opening a trade. The surface degrades cleanly
(shows nothing) when the rolling cache is unavailable or no rostered RP is
ROLE-RISK — as of the wiring date all ROLE-RISK arms were unrostered FAs, so the
block correctly stayed empty in the live league scan.

### Behavioral pitch template
Pulled from opponent profile:

| Manager Style | Pitch frame |
|---|---|
| OUTCOME_CHASER (Frendy) | Lead with PL top-50 names. They take outcome-flashy bait. Offer player with high PL rank but negative live_marginal. |
| IMPULSIVE_CHURNER (Solomon, Edwin Diaz) | Same-tier swap framed as upgrade. Don't lead with rankings. |
| PL_PROCESS_FOLLOWER (Late Night) | HARD-TARGET — only move on clear wins for THEM. Don't bother unless you have a real overpay. |
| DISCIPLINED_MINIMALIST (same as above) | Same. |
| BALANCED_SHARPSHOOTER (2015 Draft, Boone's) | Standard same-position fair offer. |
| ASLEEP_AT_THE_WHEEL (Treasure Island) | Unlikely to respond. Low priority. |
| SAVE_CHASER (Solomon's RP-tilt) | Pitch RP arms with positive live_marginal. They value SVs over total FP. |

## When to invoke

- "Find trade opportunities" / "trade target scan"
- "Who should I trade for"
- "Who's holding sell-bait on Frendy/Solomon/etc"
- Before opening trade negotiations
- Weekly as part of long-form roster planning (Monday-morning checkpoint)
- After a major IL event in the league destabilizes opponent rosters

## What it does NOT do

- Doesn't actually negotiate or send the trade — output is a recommendation deck
- Doesn't model multi-player packages — surfaces 1-for-1 candidate fits
- Doesn't account for category needs in non-points formats (BrownU is points-only)
- Doesn't model trade veto risk (BrownU vetoes require 4 votes per ESPN settings)

## Anti-patterns

- **Don't trust live_marginal for IL'd players** whose snapshots are stale (>36h). Engine flags this; respect the warning.
- **Don't propose to PL_PROCESS_FOLLOWERs** without a clear win for them on the numbers. They will see through outcome-flashy bait.
- **Don't ignore name collisions** — every join uses `resolve_pitcher_id` / `resolve_batter_id`, but verify if a recommendation surprises you.
- **Don't pitch trades the opponent's behavioral profile says won't land.** The pitch template is data-driven; deviating wastes negotiation capital.
- **Don't act on a single sell-bait number without context.** A Suárez at −20 could be IL'd (live_marginal stale) or could be in real decline — cross-check with `/triangulate`.
- **Don't treat a ROLE-RISK reliever flag as a prediction.** It tilts the odds of a role-loss crater up — it does NOT foretell the closer losing the job (~1/3 manager-driven). Use it to PRIORITIZE a sell-high pitch or AVOID an acquisition, then verify via `/triangulate` + `/rp-decline`. It never moves rprs2/live_marginal.

## Workflow

1. Run the engine: `python scripts/xfp/trade_target_scan.py`
2. Pick the 1-2 opponents with the deepest sell-bait lists OR who match your positional gap
3. For each candidate, run `/triangulate "Player Name"` to confirm the live_marginal isn't a snapshot artifact
4. Frame the pitch using the behavioral template
5. Send the trade offer through ESPN

## Related

- `/triangulate` — per-player live_marginal + verdict, confirms any trade candidate
- `/league-deep-audit` — full 8-team statistical landscape (heavier weekly pass)
- `/opp-watch` — predicts opponent's next FA move (different surface — adds/drops, not trades)
- `/rp-decline` — the engine-wired source of the ROLE-RISK sell-high surface; run `--players "X"` to confirm any flagged reliever before pitching
- Memory: `reference_trade_target_scan.md` for the dependency map + caveats

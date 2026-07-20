---
name: hitter-form
description: Unified hitter form/sustainability sweep with `--scope {roster|fa|league}` plus `--lens career`. `--scope roster` (DEFAULT) = 9-marker Statcast skill decomposition over your full hitter roster with LEGIT→REGRESS buckets + BUY-LOW/SELL-HIGH divergence vs rh3 — the old /hitter-sustainability roster sweep. `--scope fa` = the same 9-marker sweep over the FA pool to surface hitters whose underlyings are ahead of rh3 — the old /hitter-sustainability fa-pool mode. `--scope league` = 5-axis breakout-sustainability scorecard across all 8 rosters + FA pool (SUSTAINABLE/NARROW/POWER-ONLY/MIXED/HOT-STREAK/DECLINE) — the old /league-breakout-sustainability. `--lens career` = current L150-PA xwOBA ranked WITHIN each player's career distribution of rolling-150 windows (peak vs slump vs typical, the anti-mirage lens) — the old /career-form-rank. Use for "audit my hitters for who's truly sustainable vs running hot", "which of my hitters will regress", "FA hitters whose Statcast is ahead of the model", "buy-low hitter scan", "league-wide breakout sustainability", "trade-target heat-map across the league", "where does my current performance rank in my career", "is X at peak or slumping", "compare my roster + FAs by L150 process", "gut-check this swap by career percentile". Merges /hitter-sustainability + /league-breakout-sustainability + /career-form-rank (2026-07-20).
maturity: unified-hitter-form
---

# hitter-form — unified hitter form/sustainability sweep (`--scope {roster|fa|league}`, `--lens career`)

Merges the three hitter form-sweep skills into one entry point. All are
**sweep** tools (many players at once) answering "is the form real?" — the
confidence layer on rh3, never a competing projection. All joins by MLBAM
batter_id via `resolve_batter_id` (KNOWN_COLLISIONS gate — Max Muncy LAD/ATH).

## Pick the scope/lens by the question

| Ask | Invocation | Complete recipe lives in | Engine |
|---|---|---|---|
| "audit my hitter roster — sustainable vs running hot", "hidden regression risk on my team" | **`--scope roster`** | `/hitter-sustainability` SKILL.md | `scripts/xfp/hitter_sustainability.py --scope my-roster` |
| "FA hitters whose underlyings are ahead of rh3", "buy-low FA sweep" | **`--scope fa`** | `/hitter-sustainability` SKILL.md (same doc, `--scope fa-pool`) | `scripts/xfp/hitter_sustainability.py --scope fa-pool` |
| "league-wide breakout sustainability", "trade-target heat-map across all 8 teams" | **`--scope league`** | `/league-breakout-sustainability` SKILL.md | `scripts/xfp/build_league_breakout_sustainability.py` |
| "is X at peak or slumping in his own career", "L150 career percentile", "is that hot FA a mirage" | **`--lens career`** | `/career-form-rank` SKILL.md | inline duckdb rolling-150-PA windows over `statcast_{2015..2026}.parquet` |

**Default when unspecified: `--scope roster`.** A named 2-6 player list routes
to the roster/fa engine's `--players "A,B"` mode (same recipe doc). `--lens
career` composes with any universe (`my-roster + fa-pool` is its default) and
is the FIRST lens to run on roster-vs-FA upgrade questions — it separates
peak-form FA mirages from honest upgrades before the 9-marker decomp.

## What each piece adds (kept distinct — different decompositions)

- **roster / fa** — 9-marker checklist (EV, EV90, HardHit%, Barrel%,
  xwOBA-on-contact, K%, BB%, Chase%, SweetSpot%) → bucket
  LEGIT/IMPROVING/STABLE/MIXED/NOISE/BAD_LUCK/REGRESS + BUY_LOW/SELL_HIGH
  divergence signal when the decomp disagrees with rh3 by >0.4 FP/g.
- **league** — 5-axis scorecard (Bayesian-shrunk gap, process count, power
  count, CI distinguishability, career-best xwOBACON) → tier + POWER-ONLY /
  DISCIPLINE-ONLY sub-tags + FA-add / trade-target / drop-watch callouts.
- **career** — career percentile of the current rolling-150 xwOBA window, with
  the mandatory anti-mirage check (drop only if your player <30th pct; add only
  if the FA <90th pct — prefer 50-80 pct FAs).

## Shared preconditions (all scopes/lenses)

1. **Live roster truth** — MINE/OTHER/FA tags from live ESPN calls
   (`get_my_roster_with_injuries` / `get_all_teams` / `get_free_agents`
   size=2000), never session memory; per-position size caps forbidden
   (don't-do #6).
2. **Id resolution** — `resolve_batter_id(name, team=…, position=…)` for every
   lookup; accent-fold before any name join (Suárez/García). Stop on collision
   warnings.
3. **Rule 13** — every output here is a CONFIDENCE/context layer on rh3.
   Buckets, tiers, percentiles, and divergence flags never move the projection;
   the hitter BUY-LOW flavor was REJECTED as additive lift (705defc) — display
   for diagnosis, treat with skepticism.
4. **Rule 12** — when a player appears in multiple scopes/lenses with
   diverging reads, show the reconciliation (actuals vs trajectory vs process);
   never flip a verdict silently across turns.
5. **Injury check before any DECLINE/SELL call** — a DECLINE-tier player may be
   playing hurt (`feedback_check_il_before_decline_call.md`).

## Relationship to the standalone deep-dives

**`/breakout-sustainability` and `/slump-or-decline` remain standalone
single-player deep-dives** (per the 2026-07-10 registry P3 decision) — this
skill is the wide scan that FEEDS them:

- Hot name flagged NARROW/HOT-STREAK or RIDING a peak percentile →
  `/breakout-sustainability` (bat-tracking + discipline + contact decomp).
- Cold name flagged REGRESS/DECLINE or a sub-20th-percentile slumper →
  `/slump-or-decline` (3-test convergence: MC bounce, Bayesian posterior,
  historical comps).
- Head-to-head on 2-6 shortlisted names → `/hitter-compare`.
- SP form → `/sp-form` (this skill is hitters-only).

**Deprecation note:** `/hitter-sustainability`, `/league-breakout-sustainability`,
and `/career-form-rank` remain as aliases holding the complete recipes; new
invocations should use `/hitter-form --scope {roster|fa|league}` or
`/hitter-form --lens career`.

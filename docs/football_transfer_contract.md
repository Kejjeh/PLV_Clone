# Football transfer contract — what the 2026-09-19 xFP trust pass exports

Written 2026-09-19 alongside `docs/audits/production_audit_2026-09-19.md`.
Companion to `docs/fantasy_football_bootstrap.md` (the day-one seed). This
file is narrower: it names the WORKFLOW concepts the trust pass proved out,
states which are sport-agnostic, and lists every baseball-only assumption
that must NOT be ported. Nothing in the Gridiron repo was changed in the
session that wrote this; it is a contract for the next one.

## A. Reusable workflow concepts (port these)

1. **Trace-then-repair on four axes.** Before touching code, fan out
   read-only traces along (a) canonical player identity, (b) as-of /
   staleness, (c) missingness, (d) chronological boundaries, each producing
   `file:line` claims. Verify the top claims in the main session, then fix
   only what reproduces offline. The four axes are the same for any
   projection-plus-decision system.
2. **Reproduce before repair, offline.** Every fix ships with a test that
   builds the failing state from synthetic fixtures (tmp dirs, monkeypatched
   clocks, hand-built draw dicts) — never a live league read. If a defect
   cannot be reproduced without the network, it is documented, not "fixed".
3. **Missing ≠ zero ≠ stale, at every surface.** A player with no
   projection row carries a visible badge; a stale artifact carries a
   labelled age and, past a threshold, the surface REFUSES to print its
   number; a missing artifact says "missing". Pinned by rendering all three
   states through the production renderers
   (`scripts/ci/render_offline_scenarios.py`). Port the renderer pattern,
   not the HTML.
4. **Refuse, don't launder.** A win-probability engine must raise on
   non-finite totals and on a "drop" that matches nobody in the simulation.
   Both used to score as "free". The rule: an unscorable counterfactual is
   an error at the engine and an exclusion + named list at the optimizer
   (`unscoreable_drops` in the payload).
5. **Fix the default at the owner.** When several callers omit a
   timezone-correct `today=`, change the resolver's default (one edit covers
   every caller) rather than sweeping call sites. Discovery over enumeration.
6. **Identity from the artifact's own id column.** An mlbam-keyed map is
   built from the projection file's id column, never by name-joining a frozen
   historical cache. Same-name players get their own rows by construction.
7. **Freshness labels derive from the ages, never from a literal.** The
   verdict string is computed by a pure function over `{model: age_days |
   None}` with an explicit threshold constant, and tested at the boundary.
8. **Cap arithmetic on the remaining window.** A today-forward projection is
   capped at `period_cap − banked`, never the whole cap; the engine and the
   page share one helper. (Football analogue: any weekly roster-limit that
   partially "banked" before kickoff — e.g. locked starters.)
9. **Calendar dates in the league's zone.** Convert platform epoch stamps to
   the league's local date explicitly; a process-local `fromtimestamp` is
   wrong on any cloud runner. Pin it with a test that forces `TZ=UTC`.
10. **NaN is truthy.** `x or default` and `if not x` do not default NaN.
    Every numeric ingestion boundary uses a NaN-aware getter; every clamp is
    guarded so a missing input reads neutral, never as the clamp's upper
    bound.

## B. Baseball-only assumptions (do NOT port)

- **SP-start cap per scoring period** (`cap_math.sp_cap_for_period`,
  banked via ESPN statId-33, the ASG two-week block override). Football has
  no per-period pitching cap; the analogue is lineup lock timing, not a cap.
- **Two-bridge "data through yesterday"** (Statcast game-feed + boxscore
  bridges). Football data cadence is weekly (nflverse), so staleness
  thresholds are per-week, not per-day, and "yesterday" has no meaning.
- **Pitcher role detection** (`detect_pitcher_role`, dual-eligible SP/RP,
  `gamesStarted / gamesPlayed >= 0.4`). Port the *idea* (derive role from
  usage) but none of the thresholds.
- **Rotation-gap start prediction** (median clean gap 4–7 days, ±1-day
  slide, confirmed probables). Football starters are known from the depth
  chart; there is no rotation to infer.
- **RP appearance-rate model** (closer 0.55 / setup 0.40 / middle 0.30 per
  team game) and the RoS-total-over-team-games sigma. No analogue.
- **Split doubleheaders** as a game-count identity problem. Football has one
  game per team-week; the (team, date, ordinal) key is unnecessary.
- **Hitter/pitcher scoring formulas** and every boom/bust cutoff.
- **The ET calendar.** Football games span ET/PT and Thursday/Monday; the
  league's scoring week is the unit, so "game date" bucketing is by week
  index, not by local calendar day.
- **IL semantics** (`IL_STATES_STRICT`, DAY_TO_DAY-still-plays, 3 IL slots).
  Port only the principle: derive "cannot score" from the platform's
  injury-slot state, never from a boolean `injured` flag.

## C. Explicitly NOT verified in this pass (carry as open, not as fact)

- Anything requiring a live ESPN or MLB read (`/matchup-audit` after the
  dashboard change was NOT run — offseason, no league query allowed).
- The mlb_stats name→id API fallback that takes the first pitcher or
  `people[0]` on a collision (documented in the audit; needs a network
  fixture to pin).

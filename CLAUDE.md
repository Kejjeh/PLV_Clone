# plv_clone — Claude Code session context

Auto-loaded every session. Keep tight; ~200 lines max. Detail belongs
in memory files (`C:\Users\Joshua\.claude\projects\c--Users-Joshua-plv-clone\memory\`).

## What this repo is

Fantasy baseball model + tooling for the **BrownU** league (8-team H2H
points). Owner: Josh (team: **New York Ligers**). Models live in
`scripts/xfp/`, outputs in `data/outputs/`, dashboards published via
the sibling `xfp-model/` repo to GitHub Pages.

## League rules (constants)

- **Format:** 8-team H2H points
- **Roster:** 13 active hitters + 9 active pitchers + 4 bench + 3 IL = 29
- **Hard cap:** **10 SP starts/week** count toward scoring; starts 11+
  are zeros. **No** slot count limit on SPs themselves.
- **RP slots:** cap is **4** active RPs, not 3.
- **Empirical rate:** ~1.19 SP starts per active SP per week.

### Scoring formulas

```
HITTER FP/game  = R + TB + RBI + BB + HBP + SB − K
SP FP/start     = K + IP*3.3 − H − 2*ER − BB − HBP
RP FP/g         = K + IP*3.3 − H − 2*ER − BB − HBP + 5*SV + 2*HLD
```

## Validated models (use these — others are research-stage)

| Model | File | Use for |
|---|---|---|
| `xfp_rh3` | `data/outputs/xfp_rh3_projections.csv` | Hitter RoS rank |
| `xfp_rp3` | `data/outputs/xfp_rp3_projections.csv` | SP RoS rank |
| `xfp_rprs2` | `data/outputs/xfp_rprs2_projections.csv` | **RP** RoS rank (NOT rp3) |

Common mistake: ranking RPs with xfp_rp3. Always use **rprs2** for RPs.
See `memory/feedback_team_value_reads_must_be_cap_role_elig_aware.md`.

## Key file paths

```
scripts/xfp/xfp_rh3_pipeline.py        # hitter model — RH3_FEATS list
scripts/xfp/xfp_rp3_pipeline.py        # SP model — RP3_FEATS list
scripts/xfp/xfp_rprs2_pipeline.py      # RP model
scripts/xfp/refresh_dashboards.py      # daily one-command refresh
scripts/xfp/run_roster_audit.py        # implementation for /roster-audit
scripts/xfp/live_monitor.py            # MLB Stats API live game tracker
app/espn_connector.py                  # ESPN league API + injury fetcher
data/research/xfp_cache/*.csv          # multiyr / rolling training data
data/research/validation_runs/         # pre-registration files for /validate-feature
xfp-model/docs/                        # GitHub Pages dashboards (separate repo)
```

## Common commands

```bash
# Daily refresh — pulls statcast, rebuilds all models, regenerates
# dashboards, commits+pushes xfp-model. Run this once per day.
python scripts/xfp/refresh_dashboards.py

# Just refresh statcast (cheap, ~few seconds)
python scripts/xfp/refresh_xfp_statcast.py --year 2026 --lag 1

# Live game monitor
python scripts/xfp/live_monitor.py --dashboard

# Roster audit (replicates /roster-audit skill)
python scripts/xfp/run_roster_audit.py
```

## Skills available (repo-level)

- `/validate-feature` — codified 9-rule multi-testing protocol with
  Step 2.5 data-coverage pre-check. Use before promoting any signal
  to a ranker.
- `/roster-audit` — weekly slot occupancy + IL/return timeline + SP
  cap math + drop/add candidates.
- `/refresh-and-commit-and-push` — daily refresh ritual wrapped end-to-end.
- `/fa-pickup-deep-dive` — single-player deep dive: model projection
  + recent Statcast + injury + ownership + recommendation.
- `/fa-monitor` — proactive weekly scan across 6 signals (SP first-start
  fp_proxy, RP closer/setup opportunity, hitter sustained xwOBA, drafted-
  then-dropped comeback, IL return timing, role-change RP). Run Monday
  mornings. Script: `scripts/xfp/run_fa_monitor.py`.
- `/fa-replacement-pool` — broad scan: given a player to drop, returns
  ranked FA replacement candidates above a season-FP threshold with
  rh3 join, Δ vs drop target, and positional-flex match. Uses the
  unfiltered `size=2000` pattern (see `feedback_fa_pool_size_cap.md`).
- `/hitter-compare` — 2-6 player head-to-head: Statcast L21d/season
  table, rh3 row, lineup spot, ESPN counting stats per player, plus
  a comparative verdict. Fills the gap that `/fa-pickup-deep-dive`
  explicitly flags.
- `/boom-bust-history` — variance-aware historical actuals across last
  N games per player. SP L8 / hitter L21 / RP L15 windows; pulls MLB
  Stats API gameLogs and computes BrownU FP per game. Surfaces
  L8/L5/L3 averages + trend arrow + std + **boom% (SP ≥20 / H ≥10 /
  RP ≥5) + bust% (SP <5 / H <2 / RP <0)** with auto-fallback to prior
  year for IL60+ stashes (Hunter Greene 2025 surfaces automatically).
  Status tags: HOT STREAK / CAP FODDER / DECLINING / RAMP / VOLATILE
  / FLOOR / STASH. Default scope = full roster (split by position);
  optional `--names "A,B,C"` for any list. The lens that catches
  Bradish blend 5.98 vs L5 actuals 17.88 = model 12 FP behind reality.
  Canonical companion to `/sp-slate-grid`, `/hitter-slate-grid`,
  `/triangulate`, `/sp-week-plan`.
- `/hitter-slate-grid` — multi-day FA-hitter decision board (parallel
  of `/sp-slate-grid`). Joins all 14 hitter model layers: Blended xFP
  + CI, rh3, live_marginal + value_tier (same-position bucket
  C/1B/2B/3B/SS/OF/DH with H-scaled cuts ±100/±40), Triangulate
  verdict, Sustainability bucket (with **BUY-LOW REJECTED** caveat at
  −0.069 FP/PA per `705defc` — display for diagnosis only, not
  additive lift), **xwOBA L21d vs 2025 baseline diagnostic** (required
  pre-check per memory), **xwOBACON YoY trajectory**, hitter archetype
  master + T+1 + 5 comps, hitter boom_stack with 4 components
  including lineup_amp_hitter, process panel composite (PR 8), PL Top
  150, lineup confirmation, park + vs LHP/RHP, positional eligibility.
  **Mandatory KNOWN_COLLISIONS check** via `resolve_batter_id(name,
  team=..., position=...)` to prevent Max Muncy LAD-vs-ATH style bugs.
  All joins by MLBAM batter_id, never name. Drop-target rule
  (parallel of SP version): rank user's full hitter staff by Blended
  xFP before naming any drop.
- `/pl-cross-reference` — fetches current week's Pitcher List rankings
  via WebFetch and cross-references against our model picks, surfacing
  divergence with bias context (PL is rate-stat / 12-team mindset).
- `/sp-week-plan` — Monday-morning pitcher planning: projects week's
  starts against 10-SP cap, identifies weakest start to bench, flags
  long-IL SPs as drop candidates.
- `/fa-sp-pool` — mirror of /fa-replacement-pool for SPs: pulls FA
  SP pool, cross-references with PL Top 100 (and streamer ranks for
  the current week), compares against user's rostered SPs, includes
  mandatory `get_all_teams()` verification (Connelly Early bug).
- `/sp-slate-grid` — full-slate SP scan over a date window
  (default today+tomorrow). Pulls EVERY scheduled SP start from MLB
  Stats API, joins six model layers (rp3 + per_start band, SP
  archetype OVERALL/traj/T+1, live boom_stack + boom%/bust%/E[FP],
  PL Top 100, PL daily streamers with auto-fresh WebFetch when stale),
  tags ownership (MINE / opp team name / FA), renders a time-sorted
  grid with FA highlighted and decision-deadline header, then
  synthesizes a boom-layer-aware recommendation that can DOWNGRADE
  high-rp3 picks when live boom disagrees (canonical: Sheehan
  6/7/26 rp3 #55 but boom 9/18 said skip). Distinct from
  `/fa-sp-pool` (FA-only flat list), `/sp-week-plan` (my-roster cap
  math), `/stream-the-stack` (my-eligible-pool only). All joins by
  MLBAM pitcher_id — never name.
- `/slump-or-decline` — diagnose a hitter slump: career/2025/2026/L21d
  decomposition + xwOBACON/shrinkage/anchor-in-CI + process metrics +
  **year-over-year xwOBACON trajectory** (distinguishes valid prior-trough
  recovery templates from structural decline where recovery ceiling is lower) +
  three-test convergence panel (MC bounce 10k sims, Bayesian posterior
  talent, historical comp matcher 54k snapshots). DROP requires all
  3 tests to agree. Outputs HOLD / SELL-HIGH / DROP / NOT-SLUMPING-STRUCTURAL.
- `/league-deep-audit` — full 8-team league-wide statistical audit v4
  (11 layers, calibrated ECE=0.0197): career-form, 9-marker sustainability,
  xwOBACON/shrinkage/anchor-in-CI, process metrics, K%-decomp, PEAK validator,
  injury signals (ESPN DTD/IL), MC bounce (10k sims, λ=0.20 recency decay),
  Bayesian posterior talent (recency-weighted), historical comp matcher (54k
  snapshots, age-matched ±3yr), peak decay survival curves with Wilson CIs,
  SP velo/k-form. Power ranking, per-team breakdown, slump cards with
  4-signal convergence, trade targets, sell-high alerts.
  Script: `league_wide_full_audit.py`.
- `/breakout-sustainability` — diagnose if a hot hitter's recent
  L21d is skill change vs outcome luck. Decomposes bat tracking,
  discipline, contact quality across 2025/season/L21d windows,
  classifies fantasy archetype, and outputs SUSTAINABLE / NARROW /
  HOT-STREAK verdict.
- `/sp-breakout-signal` — evaluate whether a starting pitcher's recent
  hot stretch is persistent skill or outcome noise. Uses rolling-window
  good-start methodology (33,063 SP starts, 2018-2025 calibration;
  threshold: fp_proxy_per_bf ≥ −0.0476). Triggered by "is X on a hot
  streak", "should I trust X's recent starts", or any FA SP where last
  3-5 starts are cited as evidence.
- `/sp-archetype` — profile any SP by 20-80 scouting ratings on
  Stuff/Movement/Control with archetype label (27-cell matrix), career
  trajectory, and historical comp matching (Euclidean distance over
  1,353 SP-years 2015-2026). Three modes: `profile <name>` for single-
  pitcher deep dive, `scan` for league-wide trajectory shifts (upward/
  downward archetype transitions), `comps <name>` for K=5-8 closest
  historical SP-seasons with T+1/T+2 outcomes. Built on calibrated
  archetype stickiness (retention rates 0-69% depending on streak) and
  honest decline base rates (59% T+1 decline among elite, no actionable
  warning signs). Complementary to `/sp-breakout-signal` (outcome-based)
  — this is process-based. Triggered by "what kind of pitcher is X",
  "who does X compare to", "is X breaking out / declining". Daily
  refresh via `build_sp_archetypes.py` (step 2.6 of refresh_dashboards).
- `/hitter-archetype` — hitter parallel to `/sp-archetype`: profile any
  hitter by 20-80 ratings on Contact/Power/Discipline + SB overlay (27-cell
  C/P/D matrix; SB is rated but excluded from the archetype label and from
  comp-matching distance). Three modes (profile/scan/comps). Built on 3,485
  batter-years 2015-2026, PA floor 250 (80 in-progress), age tiers
  PRE_PEAK ≤25 / PEAK 26-30 / POST_PEAK 31+ (hitters peak earlier than SPs).
  Boundary tier retention validated EDGE 28.5% / SOLID 56.1% (~2× spread).
  Triggered by "what kind of hitter is X", "who does X compare to", "is X
  breaking out / declining". Daily refresh via `build_hitter_archetypes.py`
  (step 2.7 of refresh_dashboards). Complementary to `/breakout-sustainability`
  and `/hitter-sustainability` (outcome-based) — this is process-based.
- `/savant-compare` — Baseball Savant percentile side-by-side for
  2-6 players. WebFetches each player's profile, extracts percentile
  rankings, builds comparison table, identifies archetypes. Supports
  historical-season anchors (e.g., Suárez 2025 as power-or-bust comp).
- `/refresh-matchup` — light weekly refresh: rerun
  `build_matchup_dashboard.py`, sanity-check, commit + push both
  plv_clone + xfp-model (GitHub Pages). 30-second flow vs full
  refresh's 3-30 min.
- `/matchup-audit` — cross-check matchup.html projections against
  MLB Stats API + ESPN roster. Catches the 4 known SP-projection bug
  patterns (IL'd projected, undercount, mlbam=None false-positive,
  today excluded). See `reference_matchup_dashboard_sp_gotchas.md`.
- `/player-id-resolve` — name-collision prevention for same-name MLB
  players (canonical: Max Muncy LAD 3B vs ATH C). Use
  `resolve_batter_id(name, team=..., position=...)` from
  `plv_clone.utils.name_match`; builds `(norm_name, pro_team)` tuple
  keys and consults `KNOWN_COLLISIONS`. Required before any dict-keyed
  batter lookup in audit, compare, or FA scan contexts.
- `/roster-verify` — hard pre-condition before labeling ANY player as
  "yours." Calls `get_my_roster_with_injuries()` live, builds a
  normalized name set, applies `my_tag()` to every row. Exists because
  on 2026-05-25 Weathers (Late Night Bettsing) and Rasmussen (2015
  Draft First Round) were labeled "Your SP" from stale session context.
  Required before: SP/RP/hitter evals, drop/add recs, matchup previews,
  any Statcast pull filtered by roster membership.
- `/monday-morning` — **meta-skill**: chains roster-verify → roster-audit
  → sp-week-plan → fa-monitor into one unified Monday report. Pulls
  roster/FA data once and passes through all steps. Replaces 4 separate
  invocations with manual handoff.
- `/fa-signal-to-decision` — **meta-skill**: fa-monitor HIGH alerts →
  fa-pickup-deep-dive (≤3 players) → ranked add recommendation. Replaces
  the manual "signal fired, should I deep-dive it?" loop.
- `/forced-drop-planner` — compute exact date the 10-SP cap will be
  breached by upcoming IL activations, pre-identify cut candidates from
  rp3 rankings, simulate full IL return cascade. Use when multiple IL
  starters (Glasnow/Fried pattern) are returning in close succession.
- `/triangulate` — unified three-lens player analysis: PL rank + our
  model (rh3/rp3/rprs2) + archetype model (20-80 ratings + cell +
  trajectory + T+1) in a single card per player, with auto-synthesized
  verdict from the agreement/disagreement pattern. Works on H/SP/RP via
  position auto-detect. PL ranks cached in `data/research/pl_cache/`
  (refresh weekly for Top150/Top100/Closers, daily for streamers).
  Engine: `scripts/xfp/run_triangulate.py`.
- `/stream-the-stack` — daily ranked FA SP streamer recommender filtered
  by boom_stack tier (≥2/4). Confirmed probables in next 3 days,
  Connelly-Early-verified FA pool, tier-aware thresholds, σ-rescaled
  rp3 variance bands.
- `/sp-stash-finder` — find IL'd SPs available in the FA pool whose ESPN
  return date arrives before playoffs end, ranked by playoff xFP and IL-slot
  cost. Combines PL Top 100 + PL injury table + ESPN return dates + rp3 +
  archetype + (when needed) shadow-scout. Canonical discovery 2026-06-04:
  Blake Snell IL60 elbow / return 7/17 / per_start 13.02 / 0.1% owned. Also
  surfaced Pivetta, Boyd, Henderson, Eury Pérez. Engine: WebFetch PL article
  + `app.espn_connector.get_injury_details`.
- `/shadow-scout` — process-grade scouting card for SPs with no rp3 + no
  archetype (rookies / small-sample post-callup). Pulls 2026 MLB Statcast,
  percentile-ranks FB velo / K% / BB% / whiff% / CSW% vs the live 432-SP
  population, outputs 20-80 grades + PLUS_PROCESS / AVG_PROCESS / BELOW_AVG /
  NO_MLB_DATA verdict. Built 2026-06-04 to triangulate Henderson-class FAs
  the engine missed; canonical disagreement Ben Brown: archetype CAREER_LOW
  vs shadow PLUS_PROCESS (g61 at 759 pitches) — shadow wins when archetype is
  stale. Module: `scripts/xfp/lib/shadow_scout.py`.
- `/opp-watch` — predict an opponent's next roster move (transact / add /
  drop) before they make it. Per-team behavioral profiles derived from the
  manager-rating audit (PL-weighted, outcome-chaser, save-chaser, etc.).
  Backtest-validated: under Late Night Bettsing's profile their actual
  archetype_breakout adds (Max Meyer, Weathers, Ashcraft) surface in the
  predictor's top-12. v1 uses hardcoded profile weights; once the new
  player_projection_history.parquet + date-keyed pl_cache snapshots have
  accumulated ~4 weeks, refit from panel data. Engine:
  `scripts/xfp/opponent_action_predictor.py`. See plan
  `~/.claude/plans/hidden-percolating-harp.md`.
- `/boom-stack-explain` — decompose a single player's current
  boom_stack tag (SP or hitter) into components with status, value,
  threshold, tier outcome lookup, and verdict. Use when asked "why is
  X's boom_stack 2/4" or "decompose this tag". Explanatory only —
  headline number is still rp3/rh3.

Global skills also used here: `/safe-commit` (universal commit flow with
multi-repo awareness and opt-in push), `/init`, `/security-review`,
`/review`, `/fewer-permission-prompts`.

## Two-repo split (intentional)

- **plv_clone** (this repo) — private working repo. Code, data, models,
  research, repo-level skills. Most work happens here.
- **xfp-model** (sibling at `./xfp-model/`) — public deployment artifact.
  Holds `docs/index.html`, `docs/matchup.html`, `docs/live_dashboard.html`
  for GitHub Pages at https://kejjeh.github.io/xfp-model/. The
  `refresh_dashboards.py` script auto-commits + pushes to it.

If you commit in this repo, the safe-commit skill will auto-check the
sibling and ask if it needs attention too.

## Don't do these (load-bearing feedback)

1. **Don't drop a feature into rh3/rp3/rprs2 without `/validate-feature`.**
   Rule 9: baseline must include ALL existing production features.
   Stripped-down backtests over-claim lift (we got burned 4× on rh3 v2).
2. **Don't count IL slots from `injured==True`.** Use `lineup_slot=='IL'`
   to compute free IL capacity. A player can be IL'd while in their
   starting slot (Langford OF) or on the bench (Helsley BE).
3. **Don't use n_pos_flags or the composite "rolling trend" flag** to
   rank or filter FAs. Validated as noise (v3, 2026-05-11).
4. **Don't recommend players from other teams' rosters** as "best available."
   FAs only — use `get_free_agents()` exclusively.
5. **Don't commit `*.parquet`, `*.pkl`, or `*.bak` files** — they're
   gitignored. The refresh script creates `.bak` backups automatically.
6. **Don't use per-position `get_free_agents(position=X, size=300)` for
   pool scans.** Silently drops low-owned high-FP candidates. Always
   `league.free_agents(size=2000)` + manual position filter for any
   "all FAs above threshold" query. See `feedback_fa_pool_size_cap.md`.
7. **Don't conclude a player is rostered without calling `get_all_teams()`.**
   Neither PL rank nor percent_owned is a substitute. PL ranks reflect
   MLB performance, not 8-team roster state (Connelly Early, 2026-05-18).
   percent_owned is national data — 60% nationally owned is routinely
   unclaimed in 8-team (Emmett Sheehan, 2026-05-25: 60.7% owned, confirmed
   FA). Always verify via `league.teams` roster scan before concluding
   anyone is unavailable. See `feedback_pl_rank_not_equal_fa_available.md`.
8. **Don't recommend dropping a hitter without checking xwOBA L21d
   vs 2025 baseline AND xwOBACON year-over-year trajectory first.**
   MC can show "drop" while the underlying contact quality says "bounce
   coming." The YoY trajectory determines whether prior slump/recovery
   patterns are valid templates: if xwOBACON is declining each year
   (Turner pattern), recovery will hit a lower ceiling than prior
   troughs. If xwOBACON is stable, prior recoveries predict this one.
   See `reference_xwoba_l21d_vs_2025_diagnostic.md`.
9. **Don't trust matchup.html SP projection blindly.** Four known bug
   patterns can cause undercount, IL'd-projected, or mlbam-None false
   matches. Run `/matchup-audit` after any change to
   `scripts/xfp/build_matchup_dashboard.py`. See
   `reference_matchup_dashboard_sp_gotchas.md`.
10. **Don't lookup batter IDs by name alone.** Same-name MLB players
    (canonical: Max Muncy LAD vs ATH) silently grab the wrong row in a
    `dict[name]=batter_id` map. Always use
    `plv_clone.utils.name_match.resolve_batter_id(name, team=..., position=...)`
    which consults `KNOWN_COLLISIONS` and refuses to silently guess. See
    `feedback_player_name_collisions.md` and `/player-id-resolve`.
11. **Don't label any player as "yours" without a live roster call.**
    On 2026-05-25, Weathers and Rasmussen were labeled "Your SP" from
    session memory — both were on opponent rosters. Always call
    `get_my_roster_with_injuries()` first and use `my_tag()` to annotate.
    See `/roster-verify` skill.

## Memory pointers (for context-dense lookups)

All in `~/.claude/projects/c--Users-Joshua-plv-clone/memory/`:

- `MEMORY.md` — index, always loaded
- `reference_league_rules.md` — full BrownU scoring + roster spec
- `reference_validated_signals_registry.md` — what's allowed to drive decisions
- `reference_multitesting_protocol.md` — the 9 rules (Rule 8 framing, Rule 9 baseline)
- `feedback_il_slot_vs_il_status.md` — slot counting gotcha
- `feedback_validate_before_ship.md` — anti-promotion-without-validation rule
- `feedback_save_handcuffs_needs_closer_context.md` — closer ranking nuance

## Recent shipping (2026-06-03)

Today's batch added a tag layer on top of the existing rh3/rp3 numbers
(headline projections unchanged). New display-only tags surfaced via
`/triangulate`, `/stream-the-stack`, matchup.html: **tier-aware
boom_stack** (SP 4 components incl. park_friendly, range 0-4, per-tier
boom% lookup), **hitter boom_stack** (4 components incl. lineup_amp,
range 0-4), **HIGH-K ARM** standalone z-score tag, **catcher framing**
🧊 ELITE / ⚠ TAX, **anti-predictive skill_spike warning** at backend/
sp2_sp3 tiers, **skill_spike 3g → 5g window**, **σ rescale ×2.41**
calibrating SP p25/p75 bands, **per-batter hetero σ** for hitters,
**week_boom rate** in `/sp-week-plan` Step 5.5. New skills:
`/stream-the-stack`, `/boom-stack-explain`. Lessons + validation index:
`docs/architectural_lessons_2026-06-03.md`.

## Agent skills

### Issue tracker

GitHub Issues in `Kejjeh/PLV_Clone` via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical defaults (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

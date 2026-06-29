# plv_clone — Claude Code session context

Auto-loaded every session. Keep tight; ~200 lines max. Detail belongs
in memory files (`C:\Users\Joshua\.claude\projects\c--Users-Joshua-plv-clone\memory\`).

## What this repo is

Fantasy baseball model + tooling for the **BrownU** league (8-team H2H
points). Owner: Josh (team: **New York Ligers**). Models live in
`scripts/xfp/`, outputs in `data/outputs/`, dashboards published via
the sibling `xfp-model/` repo to GitHub Pages.

## CodeGraph (USE IT — don't re-derive with grep)

`.codegraph/` is **initialized and live** here (~550 files, real-time
file-watcher daemon). It's the pre-built semantic index; reaching for
grep/glob/read to explore wastes the ~90% token saving. Full rules in
the global `~/.claude/CLAUDE.md`; the load-bearing bits:

- **Exploration ("how does X work", "where is Y", architecture, tracing)
  → spawn an `Explore` agent** and paste the block below into its prompt.
  Do NOT call `codegraph_explore`/`codegraph_context` from the main
  session (they dump source and fill context).
- **Targeted pre-edit lookups → main session may call the lightweight
  tools directly:** `codegraph_search` (find a symbol), `codegraph_callers`
  / `codegraph_callees` (trace call flow), `codegraph_impact` (blast radius
  before editing), `codegraph_node` (one symbol's detail). Prefer
  `codegraph_impact` over a grep sweep before changing a shared signature.

Paste verbatim into every `Explore` agent prompt:

> This project has CodeGraph initialized (`.codegraph/` exists). Use
> `codegraph_explore` as your PRIMARY tool — one call returns full source
> for all relevant files. Follow the call budget in its tool description.
> Do NOT re-read files it already returned; only fall back to grep/glob/read
> for "Additional relevant files" or if it returns nothing.

Index hygiene: dead/one-off trees (`scripts/xfp/archive|research|_research/`,
`scripts/_oneoff/`) are `.gitignore`d **purely to keep them out of the index**
(they stay tracked in git) — CodeGraph 0.9.9 honors `.gitignore` and has no
ignore config of its own. Re-add a tree there if a future symbol search
surfaces stale `v9/v10/v11`-style duplicates.

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

## claude-mem background worker

The `claude-mem` plugin requires a background worker (Bun) on port **37778**
(set in `~/.claude-mem/settings.json`). The plugin auto-starts it with `--daemon`
when Claude Code opens. A `UserPromptSubmit` hook in `~/.claude/settings.json`
also checks port 37778 and restarts via `Start-Process bun --daemon` if down.
No manual action needed — if you ever see hook errors saying "worker unreachable",
just send any message and the hook will restart it.

To start manually if needed:
```
bun C:/Users/Joshua/.claude/plugins/cache/thedotmack/claude-mem/13.6.1/scripts/worker-service.cjs --daemon
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

## Running tests / builds (token-saving summarizer)

Don't run raw `pytest` — its full dump is thousands of lines. Wrap any
test/build command in the summarizer so you see a compact ~50-150 line
summary (final result line + verbatim FAILURES/ERRORS), with the full log
cached to `.cache/test-logs/<ts>.log`:

```bash
# Canonical test run (config lives in pyproject.toml [tool.pytest.ini_options])
python scripts/ci/run_summary.py -- python -m pytest

# Any subset works the same way
python scripts/ci/run_summary.py -- python -m pytest tests/test_scoring.py
python scripts/ci/run_summary.py pytest -q          # convenience shorthand

# Works for any build/command too (generic error+tail summary)
python scripts/ci/run_summary.py -- python scripts/xfp/refresh_dashboards.py
```

Exit code passes through unchanged, so failures still register. Only read
the printed full-log path when the summary doesn't have enough detail.

## Skills available (repo-level)

- `/validate-feature` — codified 9-rule multi-testing protocol with
  Step 2.5 data-coverage pre-check. Use before promoting any signal
  to a ranker.
- `/roster-audit` — weekly slot occupancy + IL/return timeline + SP
  cap math + drop/add candidates.
- `/pregame-check` — morning-of (before lineup lock) daily decision
  skill. For each SP starting today: START vs CAP-BENCH verdict using
  **empirically validated v2 conservative rules** (2026-06-06 backtest
  n=13,716 starts REJECTED the v1 aggressive bench rules — even
  flagged starts avg 9-11 FP, well above replacement ~5 FP). Default
  START unless cap overflow + lowest-EV start, OR blend ≤7 + opp_bat
  ≥1.10 + Tier B NOISE/REGRESS. Always START on SOFT opp_bat (<0.95).
  Also pre-scans opponent's confirmed SPs and flags my hitters facing
  high boom_stack opp pitchers. Pulls live matchup state + win prob.
  Built 2026-06-06 after Bradish/Leiter Saturday bombs that the merge
  protocol predicted at the ROSTER level but couldn't enforce daily.
  See `bench_rule_validation_2026-06-06.md`.
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
  L8/L5/L3 averages + trend arrow + std + **boom% (SP ≥17 / H ≥5 /
  RP ≥6) + bust% (SP <5 / H <0 / RP <0)** (recalibrated 2026-06-28 to
  empirical p~78/p~22 quantiles; old H ≥10/<2 fired 3%/57% = useless,
  SP ≥20 missed top-quartile starts like a 17.7; see
  `boom_bust_cutoff_recalibration_2026-06-28.md`) with auto-fallback to prior
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
- `/sp-stuff-board` — SP breakout / FA-filter board driven by the
  VALIDATED FanGraphs **Stuff+** in-season signal (validated 2026-06-06,
  `fg_pitch_modeling_inseason_2026-06-06.md`; partial r 0.30 predicting
  RoS FP/start). Projects every 2026 SP's RoS FP/start, tags MINE/opp/FA
  (live ESPN), flags breakout candidates (elite Stuff+, lagging results).
  **Location+/command REJECTED for points scoring** — don't penalize a
  high-Stuff+ arm for walks (Eury Pérez canonical: 98th-pct Stuff+,
  7th-pct Loc+, still a BUY). Single-lens — feed picks into `/triangulate`.
  Engine `scripts/xfp/sp_stuff_model.py`. Companion decline monitor:
  `scripts/xfp/sp_stuff_alert.py` (rolling velo/whiff drop, NOT a ranker).
- `/sp-floor` — SP FLOOR / bust-risk board: P(start busts, <5 FP) — the
  "avoid bad days" lens (Stuff+ = mean, this = downside). Validated
  2026-06-06 (`sp_floor_model_2026-06-06.md`): the floor is **K−BB%**, not
  stuff (season model: K% −6.3pp bust/SD dominant, BB% +2.5, barrel% +1.5,
  GB%/stuff ~0). Per-start AUC 0.601 — modest/calibrated, riskiest quintile
  busts 2.1× the safest. Tiers SAFE/MODERATE/RISKY; bench-priority tilt, NOT a
  game predictor. ~85% command so needs no live matchup. Engine
  `scripts/xfp/sp_floor_model.py`. Cross-check outliers (measured≫predicted
  bust = shape/contact, e.g. Soriano) via `/pitcher-sustainability`.
- `/trending` — physical getting-better/worse detector from fast-stabilizing
  signals. **Hitters = 3-axis** (bat speed + attack angle toward ~15° band +
  fast-swing% intent), each non-redundant, OOS CV R² 0.495→0.536; **pitchers =
  FB velo** (induced bat speed REJECTED for pitchers). 2026-to-date vs prior-yr
  baseline, z-scored, contact/results column as confirmation. Default = my roster
  + FA risers; `--names "A,B"` for cards. **DISPLAY/CONTEXT ONLY** (Rule 13 — never
  moves rh3/rp3); necessary-not-sufficient; attack angle is direction-aware (toward
  band, NOT "up=good"). Built on the bat-tracking stabilization insight: bat speed
  trustworthy in ~20 swings vs 6-12 wks for rate stats, so it's an EARLY read.
  Engine `scripts/xfp/lib/trend_signal.py`, runner `scripts/xfp/run_trending.py`.
  Validation `early_season_bat_speed_2026-06-16.md`. Rejected forward-ranker
  promotion (sample-blocked to 2027) — `bat_tracking_fp_family_2026-06-16.md`.

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

## Fast-path gotchas (don't re-derive these — they waste tool calls)

Recurring rediscoveries that cost agents 3-5 tool calls each. Start here:

1. **`marcel_il` artifact (SP).** Many FA-tier + IL'd-at-split SPs (Valdez,
   Bradish, Detmers, Eury Pérez…) carry `data_quality_tag=marcel_il` in
   `xfp_rp3_projections.csv` — their `rp3 per_start` is a SUPPRESSED Marcel
   prior (`gs_to=0`), NOT a real read, NOT an injury flag. **Rank these by
   `Stuff+ proj_ros_fp` (`sp_stuff_model.py`), not rp3.** Trust rp3 only where
   `data_quality_tag` is `data_driven_*`.
2. **Console encoding (Windows).** Prefix python INLINE with
   `PYTHONIOENCODING=utf-8 PYTHONUTF8=1 ` (or `python -X utf8`). cp1252 chokes
   on σ/→/emoji. The `set VAR=…&&` form does NOT persist in the Bash tool.
3. **`get_all_teams()` shape.** Flat pandas DataFrame of ~230 rostered players
   (`player_name, player_id, position, pro_team, team_name, lineup_slot,
   injured, injury_status`) — NOT team objects. Match names two-pass: full
   normalized, then `(last, first-initial)` (never last-only) — Cam/Cameron leak.
4. **Verify "dropped/added" LIVE.** `get_all_teams()` is the only truth; BrownU
   drops sit on ~24-48h waivers (`faab=False`). Canonical: Weathers 2026-06-11
   reported "dropped" but the live scan still showed him rostered.
5. **Don't fan out agents for a single-player / focused question** — do it inline
   in one script. Reserve agent fan-out for genuine broad FA-pool scans.
6. **`sp_bench_mc.py`** imports `fetch_schedules_by_team(team_ids, start, end)`
   (batch) from `build_matchup_dashboard`; keep in sync if that module refactors.
7. **BE slot = active for Josh.** He manages lineup daily — every healthy bench
   player gets activated before lock. **Only `IL`/`IR` slots and `injuryStatus`
   in `IL_INJURY_STATES` / `DAY_TO_DAY` zero a player.** `INACTIVE_LINEUP_SLOTS`
   in `build_matchup_dashboard.py` intentionally excludes `BE`/`BENCH`/`BN`.
   Never tell Josh a bench player "won't score" — the slot doesn't matter, health
   does. Canonical fix 2026-06-15.
8. **Never bucket pitchers by ESPN `.position` tag alone.** ESPN can mislabel
   dual-eligible pitchers (canonical: Detmers 2026 — `position='RP'` but
   `'SP' in eligible_slots` and `gamesStarted=6`; he's rp3 #29 @ 12.19
   fp/start, not an RP). Always use `detect_pitcher_role(player_or_row)`
   from `scripts/xfp/lib/pitcher_role.py`, which checks `eligible_slots`
   first and falls back to MLB Stats API `gamesStarted` for dual-eligible
   cases. The rule: SP `eligible_slots` only → SP; RP only → RP; both →
   `gamesStarted / gamesPlayed >= 0.4` → SP. Applied in
   `build_matchup_dashboard.py` and `run_roster_audit.py`; wire it anywhere
   you filter pitchers by role. Canonical fix 2026-06-15.
9. **Data is through YESTERDAY — two bridges erase the Statcast lag (2026-06-23).**
   `pybaseball.statcast()` finalizes ~1-2 days late, so two bridges fill the gap and
   both run early in `refresh_dashboards.py`: (a) **boxscore bridge** (`refresh_boxscores.py`,
   step 1.5) → real-time per-game BrownU FP into `boxscore_{hitters,pitchers}.parquet`
   (powers boom/bust, `/boom-bust-history`); (b) **statcast gf bridge**
   (`build_statcast_gf_bridge.py`, step 1.05) → Savant per-game-feed pitches mapped into
   `statcast_2026.parquet` tagged `source='gf_provisional'`, so the MODELS (rh3/rp3/rprs2,
   archetypes, splits, expected-stats, in-season arcs) are same-day current too. The
   canonical pull overwrites the provisional rows once a day finalizes. **After a daily
   refresh, assume everything reflects yesterday's games** — don't caveat "models lag a day."
10. **PL rankings publish on a known cadence — staleness is cadence-aware (2026-06-23).**
    Top 100 SP drops **Monday**; closers/relievers **~Tuesday**; Top 150 hitters **~Wednesday**;
    SP streamers are **rolling 2-3 day** windows. `lib/pl_cache._cache_is_stale` (+ `/triangulate
    --check-caches`) flags a cache stale only once its NEXT edition has actually published —
    so a Friday SP pull is "stale" by Monday, not by a flat 7-day age. Refresh in that rhythm.
11. **Trajectory/recency-trend is NON-PREDICTIVE for SP projection — validated 2026-06-24.**
    Don't re-attempt slope / EWMA / change-point / "recent K-BB% is falling" features for rp3
    OR the floor model: tested leakage-safe through both models' own harnesses — **Δr ≈ 0**
    (rp3 mean, vs the +0.005 gate) AND **ΔAUC ≈ 0** (per-start bust, bootstrap CI spans 0).
    RoS FP and bust risk both **mean-revert**; the cumulative LEVEL already carries the decline.
    For H2H downside, use the shipped **`floor_adj_xfp`** (rp3 mean docked/credited by sp_floor
    bust risk) + **`floor_adj_rank`** + **`floor_flag`** (FLOOR-RISK on RISKY tier / SAFE-FLOOR on
    SAFE tier) — decision-layer, Rule-13 context-only (registered `floor_adjusted` family).
    Tunable knobs in `lib/extra_lenses` (FLOOR_RISK_LAMBDA=0.5). **Canonical:** Soriano's
    *validated* bust risk is only 22% (his Ks protect the floor) → floor_adj ranks him #1 of his
    peer set; his 63%-bust recent run is variance, not predictive decline — so "drop Soriano"
    is selling low vs every validated lens. See `floor_adjusted_ranking_2026-06-24.md`.
    **Companion flag (same memo):** `stuff_command_lens` classifies the TYPE of decline —
    **STUFF-DECLINE** (SwStr/velo eroding in-season OR YoY, gated on a real prior-year sample so
    post-TJ arms don't false-flag → structural, sell) vs **COMMAND-WATCH** (stuff intact but
    walks up → reversible, hold-watch). Columns `stuff_cmd_tag`/`_swstr_d`/`_velo_d`/`_bb_d`/
    `_yoy_swstr_d`, registered `stuff_command` family, context-only. Canonical split: **Framber =
    STUFF-DECLINE** (SwStr 12.4→10.1 YoY, good drop) vs **Soriano = COMMAND-WATCH** (SwStr rising
    YoY, hold). Watch an arm's STUFF, not its walks, to know when a wobble becomes a sell.
12. **Hitter rolling-window predictive validity — validated 2026-06-26.** Don't re-derive which
    window to read or re-attempt a "hot-streak momentum" term for hitter FP. On our own 2026 panel
    (leakage-safe, non-overlapping anchors, `window_predictive_validity_2026-06-26.md`): (a) **longer
    trailing window predicts forward FP better, monotonically** — full season-to-date is the single
    best predictor (L7 r~0.15 → season ~0.32); (b) recent form adds **~0 beyond the FULL running
    season level** (it DOES add vs an older baseline, but the season average already contains it →
    **no separate momentum term**, Rule 13); (c) **of all process metrics, ONLY bat speed adds
    forward-FP signal beyond the FP level** (incremental partial r +0.076, CI excludes 0; K%/xwOBACON/
    HardHit%/BB% are redundant/confirmatory). **Practical:** anchor on the season level, use **L21d**
    as the recent-form window, trust **L7 only for bat speed**, and a hot L21d rate with flat bat
    speed = variance, not a new tier. (Caveat: established everyday regulars only.)
13. **Model forward-calibration is GOOD — don't "fix" the small under-projection (validated
    2026-06-26).** True forward retrospective (real git-recovered rh3/rp3 snapshots, projected at
    T vs actuals AFTER T; `model_forward_calibration_2026-06-26.md`): forward rank skill is modest
    & honest (**rh3 r≈0.35, rp3 r≈0.40** over 2-3 wks — the same-period r 0.77-0.82 is INFLATED by
    the projection containing the actuals). Forward bias is mildly positive (**rh3 +0.19 at the
    survivorship floor → +0.56 for heavy-usage regulars**; corr(err, fwd games)=+0.31). **Do NOT
    add an intercept / shade projections up / reduce shrinkage / widen σ from this** — the +bias is
    conditional on "keeps playing" (unconditionally the models are centered-to-OVER, since they
    hold priors for faders), shrinkage is validated to help, and the band check was a units bug
    (rh3 p25/p75 are **per-PA** not per-game) / confounded (rp3). The conservatism on regulars is a
    faint floor, **context-only (Rule 13) — never a number-mover or re-rank reason.** Snapshot
    logger (`build_player_projection_history.py`, refresh step 4.10) re-verified live; re-run the
    retro on logged (not git) snapshots in ~3-4 wks + do a proper single-start rp3 σ-coverage study.

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
    (or `resolve_pitcher_id(name, team=..., role=...)`) which consults
    `KNOWN_COLLISIONS` and refuses to silently guess. See
    `feedback_player_name_collisions.md` and `/player-id-resolve`.
    **NEVER `df[player_name.str.contains(last_name)]` for a stats/projection/draft
    lookup** — a surname substring grabs the wrong same-name player and `.iloc[0]`
    hides it. Canonical 2026-06-26: **Will Warren** (701542, NYY, STARTER) vs
    **Austin Warren** (681810, NYM, RELIEVER) — a `contains('Warren')` query pulled
    Austin's relief games into Will's profile, falsely showing Will "moved to the
    bullpen." (Will/Austin differ on FIRST name so they normalize differently —
    a normalized FULL-name match is safe; only same-FULL-name pairs like Muncy /
    the Garcias need a team hint.) A workflow audit fixed every skill engine doing
    this (`run_fa_monitor`, `build_sp_alerts`, `bench_tracker`, `week_schedule_tilt`,
    matchup boom-scan); the rule: resolve to mlbam with team/role, else a normalized
    FULL-name match (skip-on-ambiguous) — never last-name `contains`. The boxscore
    store + `lib/boom_bust.py` were already mlbam-keyed (safe). Locked by
    `tests/test_name_collision.py`.
11. **Don't label any player as "yours" without a live roster call.**
    On 2026-05-25, Weathers and Rasmussen were labeled "Your SP" from
    session memory — both were on opponent rosters. Always call
    `get_my_roster_with_injuries()` first and use `my_tag()` to annotate.
    See `/roster-verify` skill.
12. **Don't headline a single lens or let a verdict flip across turns.**
    The SAME player (Steer 2026-06-09) was called "cooling" one turn and
    "BUY/rising" the next because different runs foregrounded different
    slivers (the `decision_type_lens_registry` "Skip" columns optimize
    brevity over consistency). For ANY user-facing player verdict: COMPUTE
    and SHOW the full lens stack, give an explicit **actuals vs trajectory
    vs process** reconciliation when they diverge, and keep the headline
    **stable + lens-order-independent**. A verdict may change only on (a)
    new data (a refresh) or (b) a corrected error — and when it changes,
    say WHY. Never flip silently. See `reference_lens_merge_protocol.md`
    ("ALWAYS run + SHOW the full stack").
13. **Don't treat the lens stack as additive point-forecast lift.** Validated
    2026-06-11 (`lens_value_add_2026-06-11.md`, leakage-safe player-clustered
    OOS): the multi-lens synthesis does NOT beat the base rank at
    point-forecasting forward FP — clean ΔR² **+0.006 H (n.s.) / −0.014 SP
    (negative)**; the +0.033 was an L7 leakage artifact. Lenses earn their keep
    ONLY as **conviction / conflict surfacing** (agreement count sorts realized
    direction monotonically: LOW +0.15 → MED +0.30 → HIGH +0.47 FP/g), NOT as a
    free R² boost. **xwOBA-L21d (hitters)** and **boom-bust + sustainability
    (SPs)** are NON-additive / mildly negative as point terms — use them for
    CONTEXT and as Tier-B gates, NEVER to move the projection. Headline number
    stays rh3/rp3/rprs2 / Blended xFP. See `reference_lens_merge_protocol.md`.
14. **Don't headline a Stuff+ "buy-low" for a veteran without the decline
    cross-check.** Stuff+ measures stuff LEVEL, not TRAJECTORY — a high-Stuff+ /
    lagging-results SP can be a real decline, not a buy. Before headlining BUY,
    cross-check (a) archetype STUFF-rating YoY slope
    (`data/research/sp_archetype_career_panel.parquet`), (b) sustainability
    K%/SwStr decomp (`scripts/xfp/pitcher_sustainability.py`), (c) archetype
    trajectory + comp T+1. If ≥2 signal real decline → headline **"DECLINING —
    back-end / defensible drop, not a buy,"** NOT the Stuff+ buy. Canonical:
    **Framber Valdez 2026** (Stuff+ 103 looked buy-low, but STUFF 56→46 YoY,
    K% −4.7pp / SwStr −2.4pp, TRENDING_DOWN slope −4.5, comps avg 10.7 FP/start
    T+1 = real decline, not luck). See `/sp-stuff-board` mandatory cross-check +
    `reference_lens_merge_protocol.md` SP conflict rule #6.

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

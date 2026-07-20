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
- **SP-start cap is PERIOD-AWARE — never hardcode 10.** The cap is
  **10 SP starts per SCORING WEEK**; starts past the cap are zeros. **No**
  slot count limit on SPs themselves. A few periods span multiple weeks and
  carry a bigger cap:
  - Standard 1-week period → **10**.
  - **2-week playoff rounds → 20** (general rule `10 × weeks`, auto-derived
    from ESPN `matchupPeriods`).
  - **2026 All-Star block (period 15, Jul 6–19) → 16** (explicit override —
    a 2-calendar-week span but the ASG dead days Jul 13–15 remove game-days,
    so it is NOT 20).
  Always resolve the live cap via `plv_clone.cap_math.sp_cap_for_period(period,
  weeks=weeks)` (or `scripts/xfp/lib/period_meta.resolve_period_meta(league,
  period)`), and read the authoritative banked count from ESPN statId-33
  (`espn_period_meta`). Add a new ASG-style exception by adding one entry to
  `PERIOD_CAP_OVERRIDES` + `PERIOD_WINDOW_OVERRIDES`. Committed 2026-07-11.
- **RP slots:** cap is **4** active RPs, not 3. **Josh's standing rule: 4 true
  RPs is also the FLOOR — never propose an RP drop to absorb an SP return or
  free a roster spot; RP drops are only RP-for-RP upgrades (2026-07-18).**
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
| volume (H) | `data/outputs/xfp_volume_projections.csv` | proj RoS **PA/team-game** |
| volume (SP) | `data/outputs/xfp_sp_volume_projections.csv` | proj RoS **GS/team-game** |

Common mistake: ranking RPs with xfp_rp3. Always use **rprs2** for RPs.
See `memory/feedback_team_value_reads_must_be_cap_role_elig_aware.md`.

**RoS TOTALS = rate × volume (validated 2026-07-09).** The rate models are
per-PA / per-start; the volume companions (hitter +0.074 / SP +0.100 Spearman
vs naive pace, 7/7 yrs, holdout 2/2 each) convert them to totals. xfp_board and
the snapshot logger (`proj_volume`) already consume them (refresh steps
4.09/4.09b). Don't hand-multiply by flat 3.5 PA/g or 1.19 starts/wk when a
volume row exists. Full day's outcomes (incl. the rp3 IL-join regression fix,
47 arms re-tagged marcel_il): `reference_validated_signals_registry.md`
§2026-07-09.

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

## Skills — decision-moment cheat sheet (resynced 2026-07-20)

Canonical names only; ~16 aliases still resolve (old names redirect). The
FULL enforced catalog + ownership seams live in
`.claude/skills/SKILL_REGISTRY.md` (`tests/test_skills_registered.py` keeps
it in sync with disk — trust it over this summary). Depth lives in each
SKILL.md; this table routes.

**Guards — ALWAYS, before any claim:** `/roster-verify` (is-mine),
`/player-id-resolve` (name collisions), `/pitcher-role` (SP/RP truth incl.
the Jax RP-slot-lag rule).

| Moment | Reach for |
|---|---|
| **Catch-up** ("what's new / any standouts?") | `/whats-new` (delta since last look: transactions, my lines, rank movers, injuries, PL, FA standouts) |
| **Game-day morning** | `/daily-edge` (= roster-verify → pregame-check → streamer-precision-board); pieces: `/pregame-check`, `/streamer-precision-board` |
| **Monday** | `/monday-morning` (verify → roster-audit → roster-health → sp-week-plan → cap-check → fa-monitor → conviction-scan; Step 3c = decision-gates check) + `/model-health` + `/verdict-scorecard` |
| **Executing moves** | `/churn-plan` (sequenced deadlines + DID-IT-EXECUTE verify); deferred decisions → `/decision-gates` |
| **Cap crunch / IL returns** | `/cap-check` (exact banked math) · `/sp-week-plan` · `/forced-drop-planner` · `/sp-bench-mc` |
| **"Which of these N players?"** | `/pitcher-compare` (SP/RP, firm verdict) · `/hitter-compare` |
| **One player, full picture** | `/triangulate` (reference 3-lens card) · `/boom-bust-history` (actuals variance) · `/fa-pickup-deep-dive` (FA verdict) |
| **Form / sustainability** | `/sp-form --lens {breakout\|decline\|sustainability\|shadow}` · `/hitter-form --scope {roster\|fa\|league}` (+`--lens career`) · deep-dives: `/slump-or-decline`, `/breakout-sustainability` |
| **Archetypes / process** | `/sp-archetype` · `/hitter-archetype` · `/rp-archetype` · `/savant-compare` |
| **FA boards** | `/hitter-board --mode {slate\|level\|replace}` · `/sp-board --scope {slate\|roster}` · `/fa-pitcher-pool --role {sp\|rp}` · `/xfp-board` (cross-position merged) · single lenses `/sp-stuff-board`, `/sp-floor` |
| **FA monitoring** | `/fa-monitor` (12 signals) → `/fa-signal-to-decision` · IL stashes `/sp-stash-finder`, `/sp-rehab-tracker` |
| **Matchup strategy** | `/matchup-leverage` (P(win) regime) · `/opp-watch` (opponent's next move) |
| **Trade** | `/trade-deadline` (meta) → `/league-deep-audit`, `/trade-target-scan`, `/scouting-report` |
| **Playoffs** | `/playoff-war-room` (meta) → `/playoff-team-build`, `/season-sim` |
| **Roster sweeps** | `/roster-audit` (slots/cap/IL) · `/roster-health` (alerts) · `/roster-deep-audit` (agreement matrix) |
| **External sanity** | `/pl-cross-reference` |
| **Maintenance / model work** | `/validate-feature` (Rule 9 gate) · `/golden-run` (A/B refactor proof) · `/production-audit` (code audit) · `/model-health` (data+pipeline tripwires) · `/refresh-and-commit-and-push` · `/refresh-matchup` · `/matchup-audit` |

**Context lenses (Rule 13 — display only, never move rh3/rp3/rprs2; each
separately validated, deliberately separate):** `/trending` (bat speed / FB
velo) · `/volume-watch` (playing time) · `/rating-arc` (pillar arc) ·
`/conviction-scan` (ours-vs-process) · `/consensus-diff` (ours-vs-market) ·
`/decision-trend` (swing decisions) · `/second-half-splits` (career 2H).

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
   cases. The rule: SP `eligible_slots` only → SP; RP only → RP **unless the
   name is in rp3 (ESPN slot grants lag a mid-season RP→SP conversion —
   canonical: Griffin Jax 2026 post-trade, RP-only slots for weeks while
   starting for TB, so cap math ignored his starts; fixed 2026-07-19), then
   decide on `gamesStarted` like the dual path**; both →
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
    **(Both closed: σ-coverage 2026-07-10 NO-CHANGE α=2.41; logged-snapshot retro 2026-07-19
    CONFIRMED — registry entry same date. New watch: SP volume edge decay, next 4.13 run.)**

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

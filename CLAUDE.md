# plv_clone — Claude Code session context

Auto-loaded every session, so every line is a permanent tax on every turn —
and a gotcha list nobody finishes reading is a gotcha list that doesn't fire.
**Keep tight; 320 lines is the hard ceiling** (`tests/test_claude_md_budget.py`).

Detail belongs in **`docs/memory/`** — repo-local and reachable from any
platform, unlike the Windows memory path this line used to name (issue #46).
The rule is: the HEADLINE fires from here, the evidence lives one hop away.
Adding a rule means adding one line here and the full text there — never
growing a section inline.

## What this repo is

Fantasy baseball model + tooling for the **BrownU** league (8-team H2H
points). Owner: Josh (team: **New York Ligers**). Models live in
`scripts/xfp/`, outputs in `data/outputs/`, dashboards published via
the sibling `xfp-model/` repo to GitHub Pages.

## CodeGraph (USE IT — don't re-derive with grep)

`.codegraph/` is initialized and live (~550 files, file-watcher daemon) — the
pre-built semantic index. Reaching for grep/glob/read to explore wastes the
~90% token saving.

- **Exploration** ("how does X work", architecture, tracing) → spawn an
  `Explore` agent. Do NOT call `codegraph_explore` / `codegraph_context` from
  the main session — they dump source and fill context.
- **Targeted pre-edit lookups** → main session may call `codegraph_search`,
  `codegraph_callers` / `codegraph_callees`, `codegraph_impact` (prefer this
  over a grep sweep before changing a shared signature), `codegraph_node`.

Full rules, the verbatim block to paste into every `Explore` agent prompt, and
index hygiene: **`docs/memory/codegraph.md`**.

## League rules (constants)

- **Format:** 8-team H2H points
- **Roster:** 13 active hitters + 9 active pitchers + 4 bench + 3 IL = 29
- **SP-start cap is PERIOD-AWARE — never hardcode 10.** 10 SP starts per
  SCORING WEEK; starts past the cap are zeros. No slot limit on SPs themselves.
  1-week period → 10 · 2-week playoff round → 20 (`10 × weeks`, auto-derived) ·
  2026 ASG block (period 15) → **16** (explicit override, not 20). Always
  resolve via `plv_clone.cap_math.sp_cap_for_period(period, weeks=weeks)` and
  read the banked count from ESPN statId-33. Mechanics + how to add another
  ASG-style exception: `docs/memory/league_rules.md`.
- **RP slots:** cap is **4** active RPs, not 3. **Josh's standing rule: 4 true
  RPs is also the FLOOR — never propose an RP drop to absorb an SP return or
  free a roster spot; RP drops are only RP-for-RP upgrades (2026-07-18).**
- **Empirical rate:** ~1.19 SP starts per active SP per week.

### Scoring formulas

```
HITTER FP/game  = R + TB + RBI + BB + HBP + SB − K
SP FP/start     = K + IP*3.3 − H − 2*ER − BB − HBP
RP FP/g         = K + IP*3.3 − H − 2*ER − BB − HBP + 5*SV + 3*HLD
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

**RoS TOTALS = rate × volume** (validated 2026-07-09). The rate models are
per-PA / per-start; the volume companions convert them to totals, and xfp_board
+ the snapshot logger already consume them. Don't hand-multiply by a flat
3.5 PA/g or 1.19 starts/wk when a volume row exists.
Detail: `docs/memory/validated_models.md`.

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

Needs a Bun worker on port **37778**; the plugin auto-starts it and a
`UserPromptSubmit` hook restarts it if down. **No manual action needed** — if
you see "worker unreachable", send any message. Manual start command:
`docs/memory/claude_mem_worker.md`.

## Common commands

```bash
python scripts/xfp/refresh_dashboards.py            # daily: statcast, all models,
                                                    # dashboards, push xfp-model
python scripts/xfp/refresh_xfp_statcast.py --year 2026 --lag 1   # statcast only
python scripts/xfp/live_monitor.py --dashboard      # live game monitor
python scripts/xfp/run_roster_audit.py              # /roster-audit
```

## Running tests / builds (token-saving summarizer)

Don't run raw `pytest` — its full dump is thousands of lines. Wrap any
test/build command in the summarizer for a compact ~50-150 line summary (result
line + verbatim FAILURES/ERRORS), with the full log cached to
`.cache/test-logs/<ts>.log`. Exit code passes through unchanged.

```bash
python scripts/ci/run_summary.py -- python -m pytest          # canonical run
python scripts/ci/run_summary.py -- python -m pytest tests/test_scoring.py
python scripts/ci/run_summary.py -- python scripts/xfp/refresh_dashboards.py
python scripts/ci/run_summary.py pytest -q                    # shorthand
```

## Skills — decision-moment cheat sheet

Canonical names only; ~16 aliases still resolve. The FULL enforced catalog +
ownership seams live in `.claude/skills/SKILL_REGISTRY.md`
(`tests/test_skills_registered.py` keeps it in sync with disk — trust it over
any summary). The decision-moment routing table is
**`docs/memory/skills_cheatsheet.md`**.

**Guards — ALWAYS, before any claim:** `/roster-verify` (is-mine),
`/player-id-resolve` (name collisions), `/pitcher-role` (SP/RP truth).

**Domain masters — one command runs a whole domain:** `/daily-rhythm` ·
`/moves` · `/player-verdict <names>` · `/all-boards` · `/form-check`.

**Most common moments:** catch-up `/whats-new` · game-day `/daily-edge` ·
Monday `/monday-morning` · executing `/churn-plan` · cap crunch `/cap-check` ·
one player `/triangulate` · FA boards `/xfp-board` · trade `/trade-deadline` ·
playoffs `/playoff-war-room` · roster sweep `/roster-audit`.

**Context lenses (Rule 13 — display only, never move rh3/rp3/rprs2):**
`/trending` · `/volume-watch` · `/rating-arc` · `/conviction-scan` ·
`/consensus-diff` · `/decision-trend` · `/second-half-splits`.

Roster moves are P(win)-denominated: run `run_weekly_optimizer.py` **before**
executing — see the P(win) section below.

## Two-repo split (intentional)

- **plv_clone** (this repo) — private working repo. Code, data, models,
  research, skills. Most work happens here.
- **xfp-model** (sibling at `./xfp-model/`) — public deployment artifact:
  `docs/{index,matchup,live_dashboard}.html` served at
  https://kejjeh.github.io/xfp-model/. `refresh_dashboards.py` pushes to it.
  `/safe-commit` auto-checks the sibling when you commit here.

## Fast-path gotchas (don't re-derive these — they waste tool calls)

One line each; **full text, validation numbers and canonical cases in
`docs/memory/gotchas.md`**. Numbers are load-bearing — memos cite "gotcha #12".

1. **`marcel_il` (SP).** `data_quality_tag=marcel_il` in rp3 is a SUPPRESSED
   Marcel prior, not a read and not an injury flag — rank those by Stuff+
   `proj_ros_fp`. Trust rp3 only where the tag is `data_driven_*`.
2. **Console encoding (Windows).** Prefix inline python with
   `PYTHONIOENCODING=utf-8 PYTHONUTF8=1` (or `python -X utf8`).
3. **`get_all_teams()` is a flat DataFrame** of ~230 rostered players, not team
   objects. Match names two-pass: full normalized, then (last, first-initial) —
   never last-only.
4. **Verify "dropped/added" LIVE.** `get_all_teams()` is the only truth; BrownU
   drops sit on ~24-48h waivers.
5. **Don't fan out agents for a single-player question** — one inline script.
   Reserve fan-out for genuine broad FA-pool scans.
6. **`sp_bench_mc` + 4 others import `fetch_schedules_by_team(team_ids, start,
   end)`** from `build_matchup_dashboard`. Pinned by
   `tests/test_schedule_fetch_contract.py`.
7. **BE slot = active for Josh.** Only `IL`/`IR` slots and `injuryStatus` in
   `IL_INJURY_STATES`/`DAY_TO_DAY` zero a player. Never tell Josh a bench
   player "won't score" — the slot doesn't matter, health does.
8. **Never bucket pitchers by ESPN `.position` alone** — use
   `detect_pitcher_role()` (`lib/pitcher_role.py`), which checks
   `eligible_slots` first and falls back to `gamesStarted`. Includes the Jax
   RP-slot-lag rule.
9. **Data is through YESTERDAY.** Two bridges (boxscore + statcast gf) erase
   the Statcast lag in `refresh_dashboards.py`. Don't caveat "models lag a day."
10. **PL staleness is cadence-aware.** SP Monday · closers ~Tuesday · hitters
    ~Wednesday · streamers rolling 2-3 day. A cache is stale once its NEXT
    edition publishes, not at a flat 7 days.
11. **Trajectory / recency-trend is NON-PREDICTIVE for SP projection**
    (validated 2026-06-24, Δr ≈ 0 AND ΔAUC ≈ 0). For H2H downside use the
    shipped `floor_adj_xfp` / `floor_flag`; for the TYPE of decline use
    `stuff_cmd_tag` (STUFF-DECLINE = sell, COMMAND-WATCH = hold). Both
    decision-layer, Rule-13 context-only.
12. **Hitters: anchor on the season LEVEL**, use L21d as the recent-form
    window, trust L7 only for bat speed. Every in-season DELTA of a rate metric
    adds ~0 — family CLOSED, no re-open condition left. Bat speed is measured
    and reliable at 25-30 swings, but its in-season TRAJECTORY must never move
    a rank. Per-metric empirical sample minimums are in the memory file — use
    them, never hand-picks.
13. **Model forward-calibration is GOOD — don't "fix" the small
    under-projection.** No intercept, no shading up, no reduced shrinkage. The
    conservatism on regulars is context-only, never a re-rank reason.
14. **In-season "he's a different player now" is CLOSED** — five independent
    attempts failed; ~89% of apparent change is sampling noise. Split point
    GIVEN by an event → judge at z > 1.83; split point you SEARCHED for → SP
    2.58 / hitters 2.79. Events do not CAUSE breaks. Nothing regime-derived may
    move rh3/rp3/rprs2.
15. **Read the OUTCOME for hitters, the PROCESS for pitchers.** Hitter FP level
    beats every rate metric; SP K% beats the pitcher's own FP level. Pitchers
    and hitters INVERT on walks — the walk belongs to the batter.
16. **TBD probable ≠ no start.** Read the rotation ORDER; median turn is stale.

## The P(win) decision layer — read before roster advice

`P(my_total > opp_total)` wins BrownU, and it is NOT the same objective as
expected FP. The whole layer sits behind ONE engine — never reimplement a piece
of it. **Full detail: `docs/memory/pwin_layer.md`.**

- `lib/leverage_engine.py` — MC engine + `delta_pwin(state, D, add=, drop=,
  bench=)`. Draw dicts are keyed by **mlbam**; `assemble()` RAISES on a non-key.
- `lib/dpwin_history.py` — every evaluated candidate, chosen AND rejected. The
  only durable record; the rejected surface is what the ledger settles against.
- `lib/title_equity.py` — the value-of-a-win curve is far from flat (period 15 =
  2.67pp of title probability vs period 17 = 0.88pp).
- `lib/roster_rules.py` — legality as pure functions. **4 RPs is a FLOOR**: an
  RP may only be dropped for an RP.

**THE WORKFLOW RULE:** run the optimizer or `/matchup-leverage` **BEFORE**
executing a move. A move made when no surface existed can never be graded.
Rule 13 throughout: this layer never touches rh3/rp3/rprs2/baseline xFP.

## Don't do these (load-bearing feedback)

One line each; **full text and canonical cases in `docs/memory/dont_do.md`**.
Numbers are load-bearing — memos cite "don't-do #10".

1. **No feature into rh3/rp3/rprs2 without `/validate-feature`.** Rule 9: the
   baseline must include ALL existing production features.
2. **Don't count IL slots from `injured==True`** — use `lineup_slot=='IL'`.
3. **Don't rank or filter FAs by `n_pos_flags`** or the composite rolling-trend
   flag. Validated as noise 2026-05-11.
4. **Don't recommend players from other teams' rosters as "best available."**
   FAs only — `get_free_agents()`.
5. **Don't commit `*.parquet`, `*.pkl`, or `*.bak`** — gitignored.
6. **Don't use per-position `get_free_agents(position=X, size=300)` for pool
   scans** — it silently drops low-owned high-FP candidates. Always
   `league.free_agents(size=2000)` + manual filter.
7. **Don't conclude a player is rostered without `get_all_teams()`.** Neither
   PL rank nor percent_owned is a substitute — 60% nationally owned is
   routinely unclaimed in an 8-team league.
8. **Don't recommend dropping a hitter without checking xwOBA L21d vs 2025 AND
   xwOBACON year-over-year.** The YoY trajectory decides whether prior
   recoveries are valid templates.
9. **Don't trust matchup.html SP projection blindly** — four known bug
   patterns. Run `/matchup-audit` after any `build_matchup_dashboard.py` change.
10. **Don't look up player IDs by name alone.** Use
    `resolve_batter_id/resolve_pitcher_id` with team/role. **NEVER**
    `df[name.str.contains(last_name)]` — a surname substring grabs the wrong
    same-name player and `.iloc[0]` hides it.
11. **Don't label a player "yours" without a live roster call** —
    `get_my_roster_with_injuries()` first, then `my_tag()`.
12. **Don't headline a single lens or let a verdict flip across turns.** Show
    the full lens stack with an explicit actuals-vs-trajectory-vs-process
    reconciliation; a verdict changes only on new data or a corrected error,
    and you say WHY.
13. **Don't treat the lens stack as additive point-forecast lift.** Lenses earn
    their keep as conviction / conflict surfacing only. The headline number
    stays rh3/rp3/rprs2 / baseline xFP.
14. **Don't headline a Stuff+ "buy-low" for a veteran without the decline
    cross-check.** Stuff+ measures LEVEL, not TRAJECTORY. If ≥2 of (archetype
    YoY slope, sustainability decomp, comp T+1) signal real decline → headline
    DECLINING, not the buy.
15. **Don't drop on a "declining" read from a SINGLE window.** Require ≥2
    non-overlapping windows — a one-week dip looks exactly like a trend and can
    fully reverse.
16. **Don't let a short-hold FA add/drop (<48h) go unchecked forever.** Signal
    P in `/fa-monitor` re-scans churned players 3+ weeks later.
17. **Two statistical traps — check both, every study.** (a) NEVER compare an r
    across frames: window length and durability filters move r more than any
    feature effect. (b) A permutation p cannot go below 1/(B+1) — assert
    `1/(B+1) < q/M` before believing a BH-FDR result. Corollaries: always
    report one-row-per-player-season next to any pooled result, and dispersion
    is only valid on genuine 0/1-per-event rates.
18. **Don't ship a guard or a fix without sweeping its sibling call sites.** The
    dominant bug shape in this repo is a CORRECT fix applied to a strict subset
    of the places that needed it, failing silently rather than crashing. Grep
    for the siblings before committing, and prefer DISCOVERY over ENUMERATION
    in guards — a guard that enumerates drifts, one that walks the package
    covers the next case on the day it's written.

## Memory pointers (for context-dense lookups)

**`docs/memory/`** — repo-local, reachable from any platform. Holds the full
text of everything CLAUDE.md summarizes: `gotchas.md`, `dont_do.md`,
`pwin_layer.md`, `skills_cheatsheet.md`, `league_rules.md`,
`validated_models.md`, `codegraph.md`, `recent_shipping.md`,
`claude_mem_worker.md`. New detail belongs here, not inline above —
`tests/test_claude_md_budget.py` holds the line ceiling.

Josh's host also has `~/.claude/projects/c--Users-Joshua-plv-clone/memory/`
(`MEMORY.md`, `reference_league_rules.md`,
`reference_validated_signals_registry.md`,
`reference_multitesting_protocol.md`, `feedback_*`) — indexed in
`docs/memory/host_memory_index.md`. That is a **Windows** path and is NOT
reachable from the Linux containers these sessions run in — cite it, don't
try to read it.

## Recent shipping

Shipping log with the 2026-06-03 tag-layer batch (boom_stack, framing, σ
rescale, `/stream-the-stack`): **`docs/memory/recent_shipping.md`**.

## Agent skills

- **Issue tracker** — GitHub Issues in `Kejjeh/PLV_Clone`, `docs/agents/issue-tracker.md`
- **Triage labels** — `docs/agents/triage-labels.md`
- **Domain docs** — `CONTEXT.md` + `docs/adr/`, `docs/agents/domain.md`

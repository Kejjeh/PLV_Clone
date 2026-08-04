# SKILL_REGISTRY.md

> Skills-as-interchangeable-parts registry for plv_clone (8-team H2H BrownU).
>
> **The one rule:** every shared fact has ONE owner module; every skill/engine
> **CALLS** it, never re-derives it. We learned why the hard way — a hand-typed
> park table shipped **ATH backwards** (credited a pitcher +0.9 FP at the 2nd-worst
> pitcher park in baseball), and the repo's own `_park_R_map` had a latent
> venue-move bug on top. The fix was making `lib/extra_lenses.park_fp_adj` the
> **sole** owner of park→FP. This registry generalizes that fix to every shared fact.
>
> Audits: 2026-07-03 (5-agent ownership) · 2026-07-04 (adoption; merges executed)
> · **2026-07-10 (full-catalog consolidation — see `data/research/skill_audit_2026-07-10.md`)**.
> Reference implementation to copy: `triangulate`.

---

## 1. Ownership table — the shared facts + their ONE owner

| Shared fact | Owner module | Import / call | Status |
|---|---|---|---|
| **Park → FP adj** (VENUE_ERAS ATH/TB 2025 guard) | `scripts/xfp/lib/extra_lenses.py` | `park_fp_adj(team)` · `_park_R_map()` · `park_env()` | ✅ **shipped 2026-07-03** (+ `test_park_factors.py`) |
| **Opp bat-index tier** (soft ≤0.97 / tough ≥1.03) | `scripts/xfp/lib/extra_lenses.py` | `opp_env(bat_index)` | violators: build_matchup_dashboard:1160, boom_stack:239/377 |
| **Floor-adjusted xFP** + decline type | `scripts/xfp/lib/extra_lenses.py` | `floor_adjusted_xfp(mean, bust%)` · `stuff_command_lens` · `next_start_lens` | ✅ clean (triangulate + sp-floor import it) |
| **Probables fetch** (schedule?hydrate=probablePitcher) | `src/plv_clone/mlb_stats.py:129` | `get_probables(start,end)` · `fetch_week_probables()` | ✅ **owner seam shipped 2026-07-04** (sweep residual re-implementers as found) |
| **Live roster truth** (is-mine) | `app/espn_connector.py` | `get_my_roster_with_injuries()` · `my_tag()` | pre-condition (see `/roster-verify`) |
| **Pitcher role** (SP/RP, dual-elig Detmers) | `scripts/xfp/lib/pitcher_role.py` | `detect_pitcher_role(row)` | ✅ fixed 2026-07-03; violators: sp-week-plan:41, pregame-check:125 |
| **Name → mlbam + normalizer** | `src/plv_clone/utils/name_match.py` | `resolve_batter_id/resolve_pitcher_id` · `join_key` · `KNOWN_COLLISIONS` | ⚠️ 73 files re-define `_norm` (241 occ, 2 incompatible variants) |
| **PL ranks + cadence staleness** | `scripts/xfp/lib/pl_cache.py` | `load_pl_ranks()` · `cache_is_stale()` | violators: sp-stash-finder:498, pl-cross-reference |
| **Current club** (traded players; `team` col in the projection CSVs) | `scripts/xfp/lib/team_override.py` | `load_map()` · `apply_team_override(df, tmap, mlbam_col=)` · `MODEL_TEAM_CODES` | ✅ **shipped 2026-08-03** (+ `test_team_override.py`); refresh step 2c repoints the 4 CSVs that carry `team`. Models derive it from historical Statcast, so a trade goes stale until the new club accrues history |
| **Window/split gating** ("since the ASG", "since he came off the IL") | `scripts/xfp/lib/window_split.py` | `split_read(metric, side, before, before_denom, after, after_denom, league_*)` · `summarize()` · `render()` | ✅ **shipped 2026-08-03** (+ `test_window_split.py`); gates come from `plv_clone.stabilization`, never hand-picked. Wired into `/triangulate` Step 2b, inherited by `/player-verdict` |
| **Boom/bust cutoffs** (SP 17/5, H 5/0, RP 6/0) | `scripts/xfp/lib/boom_bust.py` | `boom_bust_summary(...)` · `SP_BOOM/SP_BUST/RP_BOOM/H_BOOM` | ✅ named consts 2026-07-03; ✅ stale hitter 10/2 doc in hitter-slate-grid fixed 2026-07-10 |
| **BrownU scoring formula** | `src/plv_clone/fantasy/scoring.py` | `pitcher_fp/hitter_fp/score_*`; `3.3` only as `LeagueScoring.ip` | 🔴 ~25 research-script inline copies remain (live producers clean) |
| **FA-pool fetch** (size=2000) | `src/plv_clone/league_state.py:198` | `available_fa(position=...)` | ✅ done 2026-07-04 (dashboard + matchup) |
| **SP cap + 1.19 starts/wk + roster spec** | `src/plv_clone/cap_math.py` | `SP_CAP` · `STARTS_PER_SP_PER_WEEK` · `projected_starts()` · `gap_to_cap()` | ✅ owner + main consumers routed 2026-07-04; remaining engines pending |
| **Stuff+ source-of-truth + staleness fallback** | `scripts/xfp/sp_stuff_model.py` (`load_2026` seam) + `scripts/xfp/build_inhouse_stuff.py` | FG `stuff_plus` when fresh; arch-STUFF/PLV quantile-mapped in-house score when FG >2d stale; `stuff_source` provenance col (fg\|arch\|plv\|fg_frozen) | ✅ shipped 2026-07-20 — implements the REGISTERED `archetype_stuff_replacement_2026-06-06` FALLBACK-ONLY verdict; refresh step 2.62; tripwire `fg_scrape_silent_fail` |

**Migration frontier:** the bypass hotspots are the `scripts/xfp` layer's
re-implementations of `scoring.py` (research scripts only) and the 73
`name_match` normalizer copies (mechanical sweep, do as isolated workflow).

---

## 2. Full skill catalog (resynced 2026-07-20; enforced by `tests/test_skills_registered.py`)

**83 skills on disk.** Status: **active** · **alias** (delegate — banner in
file, recipe retained, redirects to canonical; NEVER deleted) · **meta**
(chains others). P1 (streamers) executed 2026-07-10; **P2 (hitter-board,
modified) + P3 (hitter-form) + the sp-form dispatcher executed 2026-07-20**
— 16 aliases total. The drift that let this catalog claim "63" while disk
held 74 is now test-enforced: every on-disk skill must appear here and every
row here must exist on disk.

**Alias policy (amended 2026-07-20):** an alias keeps its full recipe under
an ALIAS banner, but its TRIGGER PHRASES are ported to the canonical's
description and its own description is cut to the short `ALIAS → /canonical`
form (the always-loaded token cost of 16 verbose alias descriptions was the
biggest listing bloat). Never delete an alias directory — cross-references
resolve through it.

### Guards / preconditions
| Skill | Status | Role |
|---|---|---|
| roster-verify | active | Live is-mine verification before labeling anyone "yours" |
| player-id-resolve | active | Name-collision guard (KNOWN_COLLISIONS, resolve_*_id) |
| pitcher-role | active | Role truth (detect_pitcher_role incl. the Jax RP-slot rule) — mandatory pre-claim |

### Ops / process
| Skill | Status | Role |
|---|---|---|
| refresh-and-commit-and-push | active | Daily full refresh ritual end-to-end |
| refresh-matchup | active | Light matchup.html-only rebuild + publish |
| matchup-audit | active | Cross-check matchup.html vs MLB API + ESPN (4 SP bug patterns) |
| validate-feature | active | 9-rule multi-testing gate before any ranker promotion |

### SP boards + streamers
| Skill | Status | Role |
|---|---|---|
| **sp-board** | active | CANONICAL unified SP board — `--scope {slate\|roster}` |
| sp-slate-grid | alias | → `/sp-board --scope slate` (holds the full slate recipe) |
| sp-pl-board | alias | → `/sp-board --scope roster` (holds the PL-sentiment recipe) |
| **streamer-precision-board** | active | CANONICAL streamer board — MINE+FA probables ranked by FADJ, boom_stack column + `--filter boom>=2` (P1 merge 2026-07-10) |
| stream-the-stack | alias | → `/streamer-precision-board --filter boom>=2` (holds the boom-stack recipe) |
| sp-stuff-board | active | Stuff+ RoS FP/start single lens (Location+ REJECTED note carried) |
| sp-floor | active | Bust-risk P(start <5 FP); K−BB% floor; bench-priority tilt |

### SP cap / week management
| Skill | Status | Role |
|---|---|---|
| cap-check | active | Focused any-day cap answer: banked (statId-33) + projected starts vs period cap → exact bench call; value blends rp3 + L5 form. Engine `weekly_cap_check.py`. Calls `period_meta` + `detect_pitcher_role` |
| sp-week-plan | active | Week's starts vs 10-cap; weakest-start bench call |
| pregame-check | active | Morning-of START vs CAP-BENCH (validated v2 rules) + opp-SP scan |
| forced-drop-planner | active | Cap-breach date from IL cascade + pre-identified cuts (canonical role/IL math) |
| sp-bench-mc | active | MC bench-scenario comparator for genuinely unclear calls |

### SP / RP diagnosis
| Skill | Status | Role |
|---|---|---|
| sp-archetype | active | 20-80 S/M/C + trajectory + comps (process lens) |
| **sp-form** | active | CANONICAL SP form surface — `--lens {breakout\|decline\|sustainability\|shadow}` (4 separately-validated engines, never blended; 2026-07-20) |
| sp-breakout-signal | alias | → `/sp-form --lens breakout` (holds the recipe) |
| sp-decline | alias | → `/sp-form --lens decline` (holds the recipe) |
| pitcher-sustainability | alias | → `/sp-form --lens sustainability` (holds the recipe) |
| shadow-scout | alias | → `/sp-form --lens shadow` (holds the recipe) |
| sp-rehab-tracker | active | MiLB rehab-outing tracker for IL'd SPs |
| sp-stash-finder | active | FA IL stashes whose return beats playoff end |
| rp-archetype | active | RP 20-80 S/C/B + role tags + comps |
| rp-decline | active | RP role-loss convergence watch (velo YoY + role-share) |

### FA pools / monitoring
| Skill | Status | Role |
|---|---|---|
| **fa-pitcher-pool** | active | CANONICAL FA pitcher pool — `--role {sp\|rp}` |
| fa-sp-pool | alias | → `/fa-pitcher-pool --role sp` (holds SP recipe) |
| fa-rp-pool | alias | → `/fa-pitcher-pool --role rp` (holds RP recipe) |
| fa-monitor | active | Weekly 13-signal wire scan (A-F + J-O incl. rating-arc riser + Signal P short-hold churn re-scan) |
| fa-pickup-deep-dive | active | Single-FA deep dive → PASS/CONSIDER/SKIP |
| fa-replacement-pool | alias | → `/hitter-board --mode replace` (holds the recipe; P drops dispatch to fa-pitcher-pool) |

### Hitter boards
| Skill | Status | Role |
|---|---|---|
| **hitter-board** | active | CANONICAL hitter board — `--mode {slate\|level\|replace\|pl}` (P2 executed 2026-07-20, MODIFIED: xfp-board + hitter-compare deliberately NOT absorbed — see notes on their rows). **`pl` added 2026-07-28**: PL-spined board (one row per PL Top-150 hitter that is MINE/FA, ▲▼ vs prior edition) — the hitter twin of `/sp-board --scope roster`. New surface, no alias. Engine `build_hitter_pl_board.py` |
| hitter-slate-grid | alias | → `/hitter-board --mode slate` (holds the 14-layer recipe) |
| level-board | alias | → `/hitter-board --mode level` (holds the recipe) |
| xfp-board | active | Merged roster+FA RoS/playoff dual-rank HTML boards — CROSS-POSITION (its SP half would misroute under hitter-board; kept standalone) |
| hitter-compare | active | 2-6 hitter head-to-head tables + verdict (distinct interaction; kept standalone; SP twin = /pitcher-compare) |

### Hitter form / sustainability
| Skill | Status | Role |
|---|---|---|
| **hitter-form** | active | CANONICAL hitter form sweep — `--scope {roster\|fa\|league}` + `--lens career` (P3 executed 2026-07-20) |
| hitter-sustainability | alias | → `/hitter-form --scope roster\|fa` (holds the 9-marker recipe) |
| league-breakout-sustainability | alias | → `/hitter-form --scope league` (holds the recipe) |
| career-form-rank | alias | → `/hitter-form --lens career` (holds the recipe) |
| slump-or-decline | active | Downside diagnostic; DROP needs 3/3 test convergence (standalone deep-dive per P3) |
| breakout-sustainability | active | Single-hitter "is the breakout real" deep dive (standalone per P3) |
| hitter-archetype | active | 20-80 C/P/D + SB overlay + trajectory + comps |

### Cross-position lenses
| Skill | Status | Role |
|---|---|---|
| triangulate | active | REFERENCE IMPL — PL + model + archetype 3-lens card |
| boom-bust-history | active | Actuals variance lens (`--explain` = boom_stack decomposition) |
| boom-stack-explain | alias | → `/boom-bust-history --explain` |
| trending | active | Physical trend (bat speed / FB velo) — early read, Rule 13 |
| rating-arc | active | ~4-wk arc on validated pillar (SP STUFF / H CONTACT), Rule 13 |
| conviction-scan | active | Model-vs-process divergence (buy-low/sell-high WATCH), Rule 13 |
| savant-compare | active | Savant percentile side-by-side (external visual proof) |
| pl-cross-reference | active | Pure external-sanity PL-vs-us surface (RETAINED 2026-07-04) |
| second-half-splits | active | Career pre/post-ASG splits in BrownU FP, role-truth bucketing (2026-07-18) |
| decision-trend | active | Swing-decision approach-change tracker (L21/L7 validated windows), Rule 13 (2026-07-18) |

### League-wide / trade
| Skill | Status | Role |
|---|---|---|
| roster-audit | active | Slot/cap/IL leg of the roster view |
| roster-health | active | Signal leg (alerts) of the roster view |
| league-deep-audit | active | Heavyweight 11-layer 8-team statistical audit |
| scouting-report | active | Roster ownership × archetype trajectory movers brief |
| opp-watch | active | Predict opponent's next roster move (behavior profiles) |
| trade-target-scan | active | live_marginal sell-bait / ask-targets + pitch templates |
| season-sim | active | Season simulation (playoff odds / seed scenarios) |

### Meta-skills (report bundles — chain, never re-derive)
| Skill | Status | Chain |
|---|---|---|
| monday-morning | meta | roster-verify → roster-audit → roster-health → sp-week-plan → cap-check → fa-monitor → conviction-scan |
| daily-edge | meta | roster-verify → pregame-check → streamer-precision-board (incl. its `--filter boom>=2` shortlist; 4→3 steps, P1 2026-07-10) |
| trade-deadline | meta | league-deep-audit → conviction-scan → opp-watch → trade-target-scan |
| playoff-war-room | meta | roster-verify → playoff-team-build → sp-stash-finder → sp-rehab-tracker → forced-drop-planner |
| playoff-team-build | meta | roster-verify → playoff-xFP rank → sp-stash-finder → action list |
| fa-signal-to-decision | meta | fa-monitor HIGH → fa-pickup-deep-dive (≤3) → ranked add rec |
| roster-deep-audit | meta | career-form-rank + hitter/pitcher-sustainability + slump-or-decline sweeps → agreement matrix (MINE-only) |

### Domain masters (2026-07-20 — one command per decision domain; chain-only, day/arg-aware)
| Skill | Status | Chain |
|---|---|---|
| daily-rhythm | meta | whats-new → daily-edge (game-days) → monday-morning (Mondays / --full); consolidated "Today's actions" list |
| moves | meta | decision-gates check → churn-plan verify → cap-check → forced-drop-planner (execution state; live-scan truth) |
| player-verdict | meta | guards (verify + role + id) → triangulate N names → pitcher-/hitter-compare (bucket-correct) → boom-bust-history → ONE firm verdict (Rule 12) |
| all-boards | meta | sp-board slate → streamer-precision-board (+boom>=2) → hitter-board slate → fa-pitcher-pool sp+rp → fa-monitor HIGH; one FA pull |
| **team** | meta | sp-board --scope roster + hitter-board --mode pl over one FA pull → cross-position synthesis (2026-07-28). The **PL-spined** cross-position surface: one row per PL-ranked SP/hitter that is MINE or FA, ▲▼ vs prior edition. Distinct from all-boards (slate-spined market browse) and xfp-board (model-spined single value scale) — spine, not data, is the difference. Owns the **cadence-asymmetry header** (SP Top 100 Mon vs hitter Top 150 Wed → the two halves are always at different edition ages) |
| form-check | meta | sp-form ×4 lenses (+rp-decline) → hitter-form roster (+career) → flag-routed deep-dive queue (Rule 13 sweep) |

**Alias policy:** the 6 alias skills keep their full recipe text and trigger
phrases; a banner below frontmatter redirects to the successor. Never delete an
alias directory — ~20 other SKILL.md files cross-reference them by old name and
resolve through the delegation. New prose should cite the canonical names.

---

## 3. Added 2026-07-10 (this session)

| Skill | Status | Role |
|---|---|---|
| model-health | active | Model scorecard + data-health tripwires: forward accuracy per model (7/14/21/28d anchors, model-vs-prior delta, tercile bias, volume skill) + PASS/WARN/FAIL regression checks (IL join, frozen caches, snapshot lag/gaps, row counts, proj_volume fill). Weekly Monday refresh step 4.13; run after any pipeline/cache refactor. Engine `build_model_scorecard.py`. Born from the 6-week-silent rp3 IL-join regression. |
| volume-watch | active | Playing-time movers off the validated volume layer: RISERS/FADERS (model volume vs naive season pace) ranked by FP impact (gap × rate), live ownership overlay, IL/marcel flags; WoW deltas auto-activate at ≥7 days of proj_volume history. Volume parallel of /trending (playing MORE vs getting BETTER); dual-list riser = strongest pickup signal. Rule 13. Engine `run_volume_watch.py`. |
| consensus-diff | active | Ours-vs-MARKET divergence: rate×volume RoS totals vs Steamer/ZiPS/ATC/FG-DC RoS (daily fg_proj_cache snapshots), within-role z-scores, volume-vs-rate decomposition ("plays more" ≠ "is better"), ownership-tagged with roster reality-check section. Rule 13 — routes to /triangulate. Ensemble FEATURE validation unlocks ≈2026-08-06 (4 wks of snapshots). Engine `run_consensus_diff.py`. Sibling of /conviction-scan (ours-vs-process). |
| matchup-leverage | active | H2H win-probability strategy layer: Monte Carlo of the live matchup (empirical game-log bootstrap + model σ fallback), P(win), regime call (TRAILING→boom / LEADING→floor / CLOSE→E[FP]), and ΔP(win)-ranked moves (bench swaps, SP cap usage, streamer adds). Tells /pregame-check and /sp-week-plan WHICH objective to optimize. Rule 13. Engine `run_matchup_leverage.py`. |
| verdict-scorecard | active | Decision-quality accountability — the sibling of /model-health (models vs CALLS). Aggregates all SETTLED decisions from the daily decision chain (4.10a/b/c: log → materialize → settle vs realized FP/unit, H 21d / SP 35d / RP 35d) into a verdict ladder (BUY/HOLD/CAUTION/FADE/MIXED × bucket: n, unique players, realized FP-per-unit, hit rate), monotonicity + BUY-vs-FADE discrimination, confidence calibration, named worst calls. Honest n's (EARLY READ + powered-from date below n=100; effective n = unique players). Surfaces the proj_per H/RP units caveat rather than hiding it. Rule 13/5. Engine `run_verdict_scorecard.py`. |

---

## 4. Skill dependency seams

- **Reference impl:** `triangulate` — imports `detect_pitcher_role`, `pl_cache`,
  `boom_bust`, `extra_lenses(floor/park/opp/next_start)`. Every board copies this.
- **SP boards:** ✅ MERGED 2026-07-04 → `sp-board --scope {slate|roster}`.
  `sp-stuff-board` (Stuff+) and `sp-floor` (K-BB floor) stay standalone
  single-lens; sp-floor bust tiers are the single bench-priority source.
- **Streamers:** ✅ MERGED 2026-07-10 (P1) → `streamer-precision-board`
  (`run_streamer_board.py` grew the boom_stack column via
  `lib.boom_stack.compute_boom_stack` + `--filter boom>=2`);
  `stream-the-stack` is the alias.
- **SP cap family:** `sp-week-plan` / `forced-drop-planner` / `pregame-check` /
  `sp-bench-mc` all DELEGATE to `cap_math` (forced-drop-planner's
  `detect_pitcher_role` + `lineup_slot=='IL'` math is canonical).
- **FA pitcher pools:** ✅ MERGED 2026-07-04 → `fa-pitcher-pool --role {sp|rp}`.
- **Archetype trio:** `sp/hitter/rp-archetype` kept; ENGINE unified on one
  template + per-position definitions JSON.
- **Hitter-form family:** shares ONE window-metrics + Bayesian-shrink helper
  (distinct verdicts). SP mirror: `sp-breakout-signal` / `sp-decline` /
  `pitcher-sustainability` / `rp-decline`.
- **Process-direction family (documented seam — do NOT build a sixth):**
  `rating-arc` (pillar arc) · `trending` (physical tools) · `sp-decline` /
  `rp-decline` (validated decline boards) · `conviction-scan` (level divergence).
  All Rule-13 context lenses, each separately validated; they stay separate.
- **`pl-cross-reference`:** RETAINED (only pure external-sanity surface) — reads
  via `lib/pl_cache`, not bare WebFetch.

---

## 5. Consolidation proposals — 2026-07-10 (structural; dedicated follow-ups, NOT rushed)

Full rationale + break analysis: `data/research/skill_audit_2026-07-10.md`.

| # | Proposal | Shape | Breaks to manage |
|---|---|---|---|
| P1 | ✅ **EXECUTED 2026-07-10** — `stream-the-stack` → filter of `streamer-precision-board` | board grew boom_stack column (live `compute_boom_stack`, tier-aware boom% + ⚠spike-anti) + `--filter boom>=2`; stack is now an alias | daily-edge chain updated (4→3 steps); tier-aware thresholds ported via the owner lib; verified live 2026-07-10 (49 probables → 11 boom≥2) |
| P2 | ✅ **EXECUTED 2026-07-20, MODIFIED** — `hitter-board --mode {slate\|level\|replace}` | hitter-slate-grid / level-board / fa-replacement-pool aliased. DEVIATIONS from the 07-10 design, both deliberate: **xfp-board NOT absorbed** (cross-position board — its SP half would misroute under a "hitter" name) and **hitter-compare NOT absorbed** (distinct 2-6-player interaction; /pitcher-compare built as its SP twin instead) | replace-mode dispatches P drops to fa-pitcher-pool (noted in canonical) |
| P3 | ✅ **EXECUTED 2026-07-20** — `hitter-form --scope {roster\|fa\|league}` + `--lens career` | hitter-sustainability / league-breakout-sustainability / career-form-rank aliased; breakout-sustainability + slump-or-decline stay standalone deep-dives as designed | roster-deep-audit chain wording verified (aliases resolve) |
| P4 | ✅ **EXECUTED 2026-07-20** — `sp-form --lens {breakout\|decline\|sustainability\|shadow}` | sp-breakout-signal / sp-decline / pitcher-sustainability / shadow-scout aliased — invocation surface ONLY over four separately-validated engines (§4 seam intact; a /lens dispatcher over the process-direction family was considered and REJECTED against the "do NOT build a sixth" rule — discovery handled by CLAUDE.md's cheat-sheet lens table instead) | rp-decline / rp-archetype stay standalone (RP seam) |

**Still pending from earlier audits:** `buy-low-sell-high-scan` dedicated skill
(conviction-scan is the interim surface) · scoring-formula sweep of ~25 research
scripts · 73-copy name-normalizer collapse.

---

## 6. Fix backlog (ranked; carried from 2026-07-03/04, updated 2026-07-10)

| # | Sev | Fix | Status |
|---|---|---|---|
| 1 | 🔴 CRIT | Scoring formula → `fantasy/scoring.py` | ✅ live producers migrated; ~25 research scripts remain (mechanical) |
| 3 | 🟠 HIGH | Delete 2 inline `PARK_FACTORS` dicts; point `boom_stack:54` at `extra_lenses` | ⬜ pending (validate_drift_v5_*, boom_stack) |
| 4 | 🟠 HIGH | Collapse 73 name-normalizer copies → `name_match` | ⬜ pending (isolated workflow) |
| 7 | 🟠 HIGH | `STARTS_PER_SP_PER_WEEK` — route remaining engines | ⬜ partial (owner + 4 skills done 2026-07-04) |
| 10 | 🟠 HIGH | Domain-master QA 2026-07-20 findings: (a) rookie STUFF-DECLINE fires from in-season split alone in `stuff_command_lens` — add the prior-year gate at the OWNER (memo #11); (b) pool/roster injection seams for `run_streamer_board` + `run_fa_monitor` (pull-once currently best-effort); (c) `resolve_pitcher_id` accent/suffix misses (Eury Pérez, Luis García Jr.) — extend KNOWN_COLLISIONS/normalizer; (d) rollover-morning period lag handled in skill docs — consider `weekly_cap_check --period` flag | ✅ done 2026-07-20 — (a) fixed at the owner (`stuff_command_lens` prior_ok gate); (b) resolved via the `PLV_ESPN_SNAPSHOT` chain pattern (doc'd in the masters); (c) fixed at the owner (`name_match`: Eury Pérez + Luis García Jr. KNOWN_* entries, single-candidate resolution-force hintless resolve; pinned in `tests/test_name_collision.py`); (d) resolved via `weekly_cap_check --period` |
| 9 | 🟡 MED | Doc drift fixed 2026-07-10: fa-monitor 12-signal count, hitter-slate-grid boom cutoffs (10/2→5/0), monday-morning chain description | ✅ done |

**Legend:** ✅ shipped · ⬜ pending · 🔴 needs validated migration.

## 2026-07-18 additions
- `/second-half-splits` — career pre/post-ASG splits in BrownU FP, position-grouped, role-truth bucketing. Engine `run_second_half_splits.py`.
- `/decision-trend` — swing-decision approach-change tracker (L21/L7, validated windows). Engine `run_decision_trend.py`; evidence `decision_window_study.py`.
- `/pitcher-role` — role-truth (detect_pitcher_role) promoted from gotcha #8 to a mandatory pre-claim skill after the Jax/Detmers mislabel session.

## 7. Added 2026-07-20 (skill-system redesign)

Daily-use (born from July's recurring workflows):
| Skill | Status | Role |
|---|---|---|
| churn-plan | active | Multi-step move sequencing with ET first-pitch deadlines + LIVE execution verify (EXECUTED/PARTIAL/PENDING/MISSED — the missed-Bradish class). Engine `run_churn_plan.py`; 4-RP floor enforced in-engine. |
| decision-gates | active | Pre-registered, self-pruning decision gates (velo/FP/PT metrics + manual); state `data/research/decision_gates.json` (tracked); monday-morning 3c now runs its `check`. Engine `run_decision_gates.py`. |
| whats-new | active | Delta briefing since last look (transactions, my lines, rank movers, injuries, PL editions, FA standouts) — pure joiner over the refresh's accumulated stores. Rule 13 awareness layer. Engine `run_whats_new.py`. |
| pitcher-compare | active | 2-6 pitcher head-to-head + FIRM verdict (SP twin of hitter-compare; PROSE over existing engines; delta-vs-triangulate stated in-skill). |

Maintenance:
| Skill | Status | Role |
|---|---|---|
| golden-run | active | A/B output-equivalence verifier for behavior-preserving refactors (manifest + input-drift refusal + --cold pkl stash + always-restore). **Owner of "output-equivalence verification."** Engine `scripts/ci/golden_run.py`. |
| production-audit | active | Repeatable multi-agent CODE audit (4-surface fan-out; the 2026-07-19 five-wave process). Owns CODE/SKILL/registry drift; /model-health owns DATA/PIPELINE runtime health. |

model-health grew the 6-tripwire PIPELINE STALENESS section same day
(console_data freshness, tri nightly + cards sidecar, publish freshness,
espn_snapshot TTL, trajectory endpoints, golden_stash leftovers).

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
| **Boom/bust cutoffs** (SP 17/5, H 5/0, RP 6/0) | `scripts/xfp/lib/boom_bust.py` | `boom_bust_summary(...)` · `SP_BOOM/SP_BUST/RP_BOOM/H_BOOM` | ✅ named consts 2026-07-03; ✅ stale hitter 10/2 doc in hitter-slate-grid fixed 2026-07-10 |
| **BrownU scoring formula** | `src/plv_clone/fantasy/scoring.py` | `pitcher_fp/hitter_fp/score_*`; `3.3` only as `LeagueScoring.ip` | 🔴 ~25 research-script inline copies remain (live producers clean) |
| **FA-pool fetch** (size=2000) | `src/plv_clone/league_state.py:198` | `available_fa(position=...)` | ✅ done 2026-07-04 (dashboard + matchup) |
| **SP cap + 1.19 starts/wk + roster spec** | `src/plv_clone/cap_math.py` | `SP_CAP` · `STARTS_PER_SP_PER_WEEK` · `projected_starts()` · `gap_to_cap()` | ✅ owner + main consumers routed 2026-07-04; remaining engines pending |

**Migration frontier:** the bypass hotspots are the `scripts/xfp` layer's
re-implementations of `scoring.py` (research scripts only) and the 73
`name_match` normalizer copies (mechanical sweep, do as isolated workflow).

---

## 2. Full skill catalog (audit 2026-07-10)

63 skills. Status: **active** · **alias** (deprecated delegate — banner in file,
still triggers, redirects to successor; NEVER deleted) · **meta** (chains others).
Counts: 40 active-distinct, 11 active-in-overlapping-cluster (⚠ marks them —
consolidation proposed in §5), 5 aliases, 7 meta.

### Guards / preconditions
| Skill | Status | Role |
|---|---|---|
| roster-verify | active | Live is-mine verification before labeling anyone "yours" |
| player-id-resolve | active | Name-collision guard (KNOWN_COLLISIONS, resolve_*_id) |

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
| streamer-precision-board ⚠ | active | Daily MINE+FA probables ranked by FADJ (owner-module powered) |
| stream-the-stack ⚠ | active | Daily FA streamers filtered by boom_stack tier ≥2 |
| sp-stuff-board | active | Stuff+ RoS FP/start single lens (Location+ REJECTED note carried) |
| sp-floor | active | Bust-risk P(start <5 FP); K−BB% floor; bench-priority tilt |

### SP cap / week management
| Skill | Status | Role |
|---|---|---|
| sp-week-plan | active | Week's starts vs 10-cap; weakest-start bench call |
| pregame-check | active | Morning-of START vs CAP-BENCH (validated v2 rules) + opp-SP scan |
| forced-drop-planner | active | Cap-breach date from IL cascade + pre-identified cuts (canonical role/IL math) |
| sp-bench-mc | active | MC bench-scenario comparator for genuinely unclear calls |

### SP / RP diagnosis
| Skill | Status | Role |
|---|---|---|
| sp-archetype | active | 20-80 S/M/C + trajectory + comps (process lens) |
| sp-breakout-signal | active | Outcome-based hot-streak validity (NOISE→LOCK) |
| sp-decline | active | RoS decline-risk (SwStr/K LEVEL — validated, not slope) |
| pitcher-sustainability | active | 9-marker confidence layer on rp3 + divergence flags |
| shadow-scout | active | Process card for SPs with no rp3/archetype row (rookies) |
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
| fa-monitor | active | Weekly 12-signal wire scan (A-F + J-O incl. rating-arc riser) |
| fa-pickup-deep-dive | active | Single-FA deep dive → PASS/CONSIDER/SKIP |
| fa-replacement-pool ⚠ | active | "Dropping X" flat ranked replacement list (H or P) |

### Hitter boards
| Skill | Status | Role |
|---|---|---|
| **hitter-slate-grid** ⚠ | active | CANONICAL hitter FA decision board (all 14 layers) |
| xfp-board ⚠ | active | Merged roster+FA RoS/playoff dual-rank HTML boards |
| level-board ⚠ | active | Season FP/g LEVEL rank + LEVEL-vs-rh3 divergence |
| hitter-compare ⚠ | active | 2-6 hitter head-to-head tables + verdict |

### Hitter form / sustainability
| Skill | Status | Role |
|---|---|---|
| slump-or-decline | active | Downside diagnostic; DROP needs 3/3 test convergence |
| breakout-sustainability ⚠ | active | Single-hitter "is the breakout real" deep dive |
| hitter-sustainability ⚠ | active | Sweep 9-marker confidence layer on rh3 |
| league-breakout-sustainability ⚠ | active | League-wide 5-axis breakout sweep / trade heat-map |
| career-form-rank ⚠ | active | L150 career-percentile landscape (anti-buy-high lens) |
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

### League-wide / trade
| Skill | Status | Role |
|---|---|---|
| roster-audit | active | Slot/cap/IL leg of the roster view |
| roster-health | active | Signal leg (alerts) of the roster view |
| league-deep-audit | active | Heavyweight 11-layer 8-team statistical audit |
| scouting-report | active | Roster ownership × archetype trajectory movers brief |
| opp-watch | active | Predict opponent's next roster move (behavior profiles) |
| trade-target-scan | active | live_marginal sell-bait / ask-targets + pitch templates |

### Meta-skills (report bundles — chain, never re-derive)
| Skill | Status | Chain |
|---|---|---|
| monday-morning | meta | roster-verify → roster-audit → roster-health → sp-week-plan → fa-monitor → conviction-scan |
| daily-edge | meta | roster-verify → pregame-check → streamer-precision-board → stream-the-stack |
| trade-deadline | meta | league-deep-audit → conviction-scan → opp-watch → trade-target-scan |
| playoff-war-room | meta | roster-verify → playoff-team-build → sp-stash-finder → sp-rehab-tracker → forced-drop-planner |
| playoff-team-build | meta | roster-verify → playoff-xFP rank → sp-stash-finder → action list |
| fa-signal-to-decision | meta | fa-monitor HIGH → fa-pickup-deep-dive (≤3) → ranked add rec |
| roster-deep-audit | meta | career-form-rank + hitter/pitcher-sustainability + slump-or-decline sweeps → agreement matrix (MINE-only) |

**Alias policy:** the 5 alias skills keep their full recipe text and trigger
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

---

## 4. Skill dependency seams

- **Reference impl:** `triangulate` — imports `detect_pitcher_role`, `pl_cache`,
  `boom_bust`, `extra_lenses(floor/park/opp/next_start)`. Every board copies this.
- **SP boards:** ✅ MERGED 2026-07-04 → `sp-board --scope {slate|roster}`.
  `sp-stuff-board` (Stuff+) and `sp-floor` (K-BB floor) stay standalone
  single-lens; sp-floor bust tiers are the single bench-priority source.
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
| P1 | `stream-the-stack` → mode of `streamer-precision-board` | board grows boom_stack column + `--filter boom>=2`; stack becomes alias | daily-edge chain (4→3 steps); port tier-aware thresholds |
| P2 | Hitter-board core: `hitter-board --mode {slate\|merged\|level\|replace\|compare}` | hitter-slate-grid canonical; xfp-board / level-board / fa-replacement-pool / hitter-compare become mode delegates (sp-board `--scope` is the template) | xfp-board ENGINE is a refresh artifact (GH Pages) — engine untouched, only skill entry merges; replace-mode must dispatch P drops to fa-pitcher-pool |
| P3 | Hitter-form sweeps: `hitter-form --scope {roster\|fa\|league} --lens {sustainability\|breakout\|career-pct}` | merges hitter-sustainability + league-breakout-sustainability + career-form-rank; breakout-sustainability + slump-or-decline stay as deep-dives | roster-deep-audit step list; reconcile tier vocabularies |

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
| 9 | 🟡 MED | Doc drift fixed 2026-07-10: fa-monitor 12-signal count, hitter-slate-grid boom cutoffs (10/2→5/0), monday-morning chain description | ✅ done |

**Legend:** ✅ shipped · ⬜ pending · 🔴 needs validated migration.

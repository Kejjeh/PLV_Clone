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
> Audit: 2026-07-03 (5-agent workflow). Reference implementation to copy: `triangulate`.

---

## 1. Ownership table — the shared facts + their ONE owner

| Shared fact | Owner module | Import / call | Status |
|---|---|---|---|
| **Park → FP adj** (VENUE_ERAS ATH/TB 2025 guard) | `scripts/xfp/lib/extra_lenses.py` | `park_fp_adj(team)` · `_park_R_map()` · `park_env()` | ✅ **shipped 2026-07-03** (+ `test_park_factors.py`) |
| **Opp bat-index tier** (soft ≤0.97 / tough ≥1.03) | `scripts/xfp/lib/extra_lenses.py` | `opp_env(bat_index)` | violators: build_matchup_dashboard:1160, boom_stack:239/377 |
| **Floor-adjusted xFP** + decline type | `scripts/xfp/lib/extra_lenses.py` | `floor_adjusted_xfp(mean, bust%)` · `stuff_command_lens` · `next_start_lens` | ✅ clean (triangulate + sp-floor import it) |
| **Probables fetch** (schedule?hydrate=probablePitcher) | `src/plv_clone/mlb_stats.py:129` | `get_probables(start,end)` · `fetch_week_probables()` | ✅ **owner seam shipped 2026-07-04** (consolidation landed; sweep any residual re-implementers as found) |
| **Live roster truth** (is-mine) | `app/espn_connector.py` | `get_my_roster_with_injuries()` · `my_tag()` | pre-condition (see `/roster-verify`) |
| **Pitcher role** (SP/RP, dual-elig Detmers) | `scripts/xfp/lib/pitcher_role.py` | `detect_pitcher_role(row)` | ✅ fixed 2026-07-03; violators: sp-week-plan:41, pregame-check:125 |
| **Name → mlbam + normalizer** | `src/plv_clone/utils/name_match.py` | `resolve_batter_id/resolve_pitcher_id` · `join_key` · `KNOWN_COLLISIONS` | ⚠️ 73 files re-define `_norm` (241 occ, 2 incompatible variants) |
| **PL ranks + cadence staleness** | `scripts/xfp/lib/pl_cache.py` | `load_pl_ranks()` · `cache_is_stale()` | violators: sp-stash-finder:498, pl-cross-reference |
| **Boom/bust cutoffs** (SP 17/5, H 5/0, RP 6/0) | `scripts/xfp/lib/boom_bust.py` | `boom_bust_summary(...)` · `SP_BOOM/SP_BUST/RP_BOOM/H_BOOM` | ✅ **named consts shipped 2026-07-03**; fix stale `20` in hitter-slate-grid:788 |
| **BrownU scoring formula** | `src/plv_clone/fantasy/scoring.py` | `pitcher_fp/hitter_fp/score_*`; `3.3` only as `LeagueScoring.ip` | 🔴 ~30 inline copies incl LIVE producer refresh_boxscores:9 |
| **FA-pool fetch** (size=2000) | `src/plv_clone/league_state.py:198` | `available_fa(position=...)` | 🔴 dashboard:113/1276/1712/2169 (size 250/200), matchup:1618 (300) |
| **SP cap + 1.19 starts/wk + roster spec** | `src/plv_clone/cap_math.py` | `SP_CAP` · `STARTS_PER_SP_PER_WEEK` · `projected_starts()` · `gap_to_cap()` | ✅ **1.19 + helpers shipped 2026-07-03**; route 8 aliases + 4 skills |

**Migration frontier:** `cap_math` and the new `park_fp_adj`/boom-bust consts are now clean owners.
The bypass hotspots are the `scripts/xfp` layer's re-implementations of `scoring.py`,
`name_match`, and `league_state.available_fa()` (probables now owned by
`mlb_stats.get_probables()`, shipped 2026-07-04).

---

## 2. Skill dependency map

- **Reference impl:** `triangulate` — imports `detect_pitcher_role`, `pl_cache`, `boom_bust`,
  `extra_lenses(floor/park/opp/next_start)`. Every board copies this pattern.
- **SP boards:** ✅ MERGED 2026-07-04 → `sp-board --scope {slate|roster}` (PL-sentiment +
  HR/9 preserved; old `sp-slate-grid`/`sp-pl-board` kept as delegating aliases).
  `stream-the-stack` stays thin (shares probables + FA-pool helpers). `sp-stuff-board`
  (Stuff+) and `sp-floor` (K-BB floor) stay standalone single-lens; sp-floor bust tiers
  are the single bench-priority source.
- **SP cap family:** `sp-week-plan` / `forced-drop-planner` / `pregame-check` / `sp-bench-mc`
  all DELEGATE to `cap_math` (forced-drop-planner's `detect_pitcher_role` + `lineup_slot=='IL'`
  math is canonical).
- **FA pitcher pools:** ✅ MERGED 2026-07-04 → `fa-pitcher-pool --role {sp|rp}` (old
  `fa-sp-pool`/`fa-rp-pool` kept as delegating aliases).
- **Archetype trio:** `sp/hitter/rp-archetype` skills kept; ENGINE unified onto one template
  + per-position definitions JSON; matrix prose deleted from each SKILL.md.
- **Hitter-form family:** `breakout-sustainability` / `slump-or-decline` / `hitter-sustainability`
  / `career-form-rank` share ONE window-metrics + Bayesian-shrink helper (distinct verdicts).
  SP mirror: `sp-breakout-signal` / `sp-decline` / `pitcher-sustainability` / `rp-decline`.
- **Hitter boards:** `hitter-slate-grid` is the superset; `xfp-board`, `level-board`,
  `fa-replacement-pool`, `hitter-compare` → thin modes over one FA-board core.
- **Absorb:** ✅ 2026-07-04 `boom-stack-explain` → `boom-bust-history --explain` (alias kept).
  **`pl-cross-reference`:** RETAINED 2026-07-04 (only pure external-sanity surface) — reads
  via the `lib/pl_cache` escape hatch instead of bare WebFetch. NOT deprecated.
- **New:** `streamer-precision-board` (✅ built), `buy-low-sell-high-scan`, `cap-engine` (the
  `cap_math` helpers above, now the lib layer of it).

---

## 3. Report bundles (auto-chained multi-skill reports)

| Bundle | When | Chain | Data passed between steps |
|---|---|---|---|
| **daily-edge** ✅ built 2026-07-04 | game-day AM before lock | roster-verify → pregame-check → **streamer-precision-board** → stream-the-stack | `my_tag` set → probables/FA pool pulled once → FA boom filter over same pool |
| **monday-full** (=/monday-morning) | Monday / post-IL txn | roster-verify → roster-audit → sp-week-plan(cap_math) → fa-monitor → buy-low-sell-high-scan | one roster/FA pull threaded through (the monday-morning contract) |
| **trade-deadline** ✅ built 2026-07-04 | trade eval / sell-high | league-deep-audit → **conviction-scan** (buy-low/sell-high surface until dedicated skill ships) → opp-watch → trade-target-scan | 11-layer panel → divergence → PROFILES → pitch templates |
| **playoff-war-room** ✅ built 2026-07-04 | quarterly, periods 18+ | roster-verify → playoff-team-build → sp-stash-finder → sp-rehab-tracker → forced-drop-planner(cap_math) | playoff-window mult from cap_math; shared FA + injury-return helper |

---

## 4. Fix backlog (ranked; audit 2026-07-03, progress 2026-07-04)

| # | Sev | Fix | Status |
|---|---|---|---|
| 1 | 🔴 CRIT | Scoring formula → `fantasy/scoring.py` | ✅ **lib/boom_bust (4 sites) migrated** w/ parity gate; refresh_boxscores was already on the seam (audit false-positive). ~25 research scripts remain (mechanical) |
| 2 | 🔴 CRIT | FA-pool size<2000 → `available_fa()` | ✅ **done** (dashboard default 2000 + matchup:1618) |
| 3 | 🟠 HIGH | Delete 2 inline `PARK_FACTORS` dicts; point `boom_stack:54` at `extra_lenses` | ⬜ pending (validate_drift_v5_*, boom_stack) |
| 4 | 🟠 HIGH | Collapse 73 name-normalizer copies → `name_match`; kill NFKD-ascii first | ⬜ pending (mechanical sweep — do as isolated workflow) |
| 5 | 🟠 HIGH | One `get_probables()` for the 8 duplicated fetches | ✅ **done 2026-07-04** (`mlb_stats.get_probables()` owner shipped + consumers consolidated) |
| 6 | 🟠 HIGH | boom/bust named consts + fix stale `boom>=20` | ✅ **done** (consts + build_sp_pl_board + hitter-slate-grid doc) |
| 7 | 🟠 HIGH | `STARTS_PER_SP_PER_WEEK` owner + route consumers | ✅ **partial 2026-07-04**: owner done; sp-week-plan + pregame-check routed (8fd4797); opponent_scouting.py CAP_AWARE_* now derived from cap_math; remaining engines pending |
| 8 | 🟠 HIGH | role/resolve in sp-week-plan + pregame-check + fa-rp-pool | ✅ **done** (all three) |
| — | 🟡 MED | fa-monitor signal-count doc (3/6 → 11) | ✅ **done** |

**Merges (structural — dedicated follow-ups, NOT rushed):** `sp-slate-grid`+`sp-pl-board`→`sp-board`;
`fa-sp-pool`+`fa-rp-pool`→`fa-pitcher-pool`; absorb `boom-stack-explain`. **New skill pending:** `buy-low-sell-high-scan`.

**Legend:** ✅ shipped · ⬜ pending · 🔴 needs validated migration.

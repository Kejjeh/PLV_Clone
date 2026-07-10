# Skill-layer audit — 2026-07-10

Full audit + consolidation pass over the 63 repo-level skills in `.claude/skills/`.
Companion to the rewritten `.claude/skills/SKILL_REGISTRY.md` (same date).
Prior audits: 2026-07-03 (5-agent ownership audit), 2026-07-04 (adoption audit,
merges executed: sp-board, fa-pitcher-pool, boom-stack-explain absorption).

## Headline counts

| Classification | Count |
|---|---|
| ACTIVE-DISTINCT | 40 |
| OVERLAPPING-CLUSTER (kept; consolidation proposed, NOT executed) | 11 |
| DEPRECATED / delegating alias (banner in file, still triggers, redirects) | 5 |
| META (chains other skills) | 7 |
| STALE (dead engine / rejected methodology requiring deprecation) | 0 |
| **Total** | **63** |

Every engine script referenced by a SKILL.md exists (checked all 52 unique
`scripts/xfp/*.py` refs + all `app/` and `src/` refs — zero missing). No skill
still *recommends* a REJECTED signal from the validated-signals registry as a
decision input; the known rejects (Location+, n_pos_flags, hitter buy-low
additive, trajectory-slope features) all appear only as explicit warnings.
Three stale-content items were found and fixed (see "Executed" below).

## Full classification table

Status key: **A** active-distinct · **O** overlapping-cluster member ·
**D** deprecated alias · **M** meta.

| Skill | St | Cluster | One-line role |
|---|---|---|---|
| boom-bust-history | A | cross-lens | Actuals variance lens: L-N game logs → FP/g, boom%/bust% (recalibrated cutoffs), trend; `--explain` decomposes boom_stack |
| boom-stack-explain | D | cross-lens | → `/boom-bust-history --explain` (absorbed 2026-07-04) |
| breakout-sustainability | O | hitter-form | Single-hitter deep-dive: is the hot stretch skill change or outcome luck (SUSTAINABLE/NARROW/HOT-STREAK) |
| career-form-rank | O | hitter-form | L150 xwOBA level + career-percentile landscape (peak-form-mirage detector for swaps) |
| conviction-scan | A | cross-lens | Model-vs-process divergence board (validated pillar pct vs rp3/rh3 pct); buy-low/sell-high WATCH, Rule 13 |
| daily-edge | M | meta | Game-day AM bundle: roster-verify → pregame-check → streamer-precision-board → stream-the-stack |
| fa-monitor | A | fa-pools | Weekly 12-signal FA wire scan (A-F core + J-O extended incl. rating-arc riser) → HIGH/MED/LOW alerts |
| fa-pickup-deep-dive | A | fa-pools | Single-FA deep dive: model + Statcast + injury + archetype + PASS/CONSIDER/SKIP |
| fa-pitcher-pool | A | fa-pools | Canonical FA pitcher pool, `--role {sp\|rp}` (merged 2026-07-04) |
| fa-replacement-pool | O | hitter-boards | "Dropping X, who replaces him" flat ranked FA list (H or P) with Δ vs drop target |
| fa-rp-pool | D | fa-pools | → `/fa-pitcher-pool --role rp` (merged 2026-07-04; holds the RP recipe) |
| fa-signal-to-decision | M | meta | fa-monitor HIGH alerts → deep-dive (≤3) → ranked add recommendation |
| fa-sp-pool | D | fa-pools | → `/fa-pitcher-pool --role sp` (merged 2026-07-04; holds the SP recipe) |
| forced-drop-planner | A | sp-cap | Exact cap-breach date from IL return cascade + pre-identified cuts (canonical role/IL-slot math) |
| hitter-archetype | A | archetypes | 20-80 C/P/D + SB overlay, 27-cell matrix, trajectory + comps (3,485 batter-years) |
| hitter-compare | O | hitter-boards | 2-6 hitter head-to-head Statcast/model/lineup tables + verdict |
| hitter-slate-grid | O | hitter-boards | CANONICAL hitter FA decision board — all 14 hitter layers joined, multi-day |
| hitter-sustainability | O | hitter-form | Sweep-mode 9-marker confidence layer on rh3 (LEGIT…REGRESS) + divergence flags |
| league-breakout-sustainability | O | hitter-form | League-wide (~640 hitters) 5-axis breakout-sustainability sweep / trade heat-map |
| league-deep-audit | A | league | Heavyweight 11-layer 8-team statistical audit (MC, Bayesian, comps, survival curves) |
| level-board | O | hitter-boards | Season-to-date FP/g LEVEL rank + LEVEL-vs-rh3 divergence (RIDING-HOT/PEDIGREE) |
| matchup-audit | A | ops | Cross-check matchup.html vs MLB API + ESPN (4 known SP-projection bug patterns) |
| monday-morning | M | meta | Monday bundle: roster-verify → roster-audit → roster-health → sp-week-plan → fa-monitor → conviction-scan |
| opp-watch | A | league | Predict an opponent's next roster move from behavioral profiles |
| pitcher-sustainability | A | sp-diagnosis | 9-marker Statcast confidence layer on rp3 + BUY-LOW/SELL-HIGH divergence |
| pl-cross-reference | A | cross-lens | Pure external-sanity surface: PL ranks vs our picks (RETAINED 2026-07-04, uses pl_cache) |
| player-id-resolve | A | guard | Name-collision guard (KNOWN_COLLISIONS, resolve_*_id) — precondition skill |
| playoff-team-build | M | meta | Ideal playoff roster: playoff-xFP rank + stash-finder + action list |
| playoff-war-room | M | meta | Quarterly bundle: playoff-team-build → sp-stash-finder → sp-rehab-tracker → forced-drop-planner |
| pregame-check | A | sp-cap | Morning-of START vs CAP-BENCH verdicts (validated v2 conservative rules) + opp-SP boom scan |
| rating-arc | A | cross-lens | ~4-week in-season arc on the validated pillar (SP STUFF / hitter CONTACT); RISER/FALLER, Rule 13 |
| refresh-and-commit-and-push | A | ops | Daily full refresh ritual end-to-end |
| refresh-matchup | A | ops | Light matchup.html-only rebuild + publish |
| roster-audit | A | roster | Slot occupancy + IL timeline + SP cap math + drop/add candidates (the slot/cap leg) |
| roster-deep-audit | M | meta | Mine-only bundle: chains form/sustainability sweeps → agreement matrix → swaps |
| roster-health | A | roster | Signal-layer Monday briefing (TRENDING_DOWN / COLD_* / DROP_RISK alerts; the signal leg) |
| roster-verify | A | guard | Live is-mine verification precondition (my_tag) — the Weathers/Rasmussen rule |
| rp-archetype | A | archetypes | RP 20-80 S/C/B + role tags + comps (weak-signal caveat built in) |
| rp-decline | A | rp | RP role-loss convergence watch (velo YoY + role-share slip) |
| savant-compare | A | cross-lens | Baseball Savant percentile side-by-side (external visual-proof lens) |
| scouting-report | A | league | League-wide proactive movers brief: roster ownership × archetype trajectory |
| shadow-scout | A | sp-diagnosis | Process-grade 20-80 card for SPs with no rp3/archetype row (rookie/callup fallback) |
| slump-or-decline | A | hitter-form | Downside diagnostic w/ 3-test convergence panel; HOLD/SELL-HIGH/DROP verdicts (DROP needs 3/3) |
| sp-archetype | A | archetypes | SP 20-80 S/M/C + trajectory + comps (1,353 SP-years) |
| sp-bench-mc | A | sp-cap | Monte Carlo bench-scenario comparator when the point-estimate call isn't settled |
| sp-board | A | sp-boards | CANONICAL unified SP board, `--scope {slate\|roster}` (merged 2026-07-04) |
| sp-breakout-signal | A | sp-diagnosis | Outcome-based hot-streak validity (good-start rolling windows, NOISE→LOCK tiers) |
| sp-decline | A | sp-diagnosis | RoS decline-risk board (SwStr/K LEVEL, validated — not slope) |
| sp-floor | A | sp-boards | Bust-risk lens P(start <5 FP) — K−BB% floor; bench-priority tilt |
| sp-pl-board | D | sp-boards | → `/sp-board --scope roster` (merged 2026-07-04; holds PL-sentiment recipe) |
| sp-rehab-tracker | A | sp-diagnosis | MiLB rehab-outing tracker for IL'd SPs (buy-low window before models catch up) |
| sp-slate-grid | D | sp-boards | → `/sp-board --scope slate` (merged 2026-07-04; holds full slate recipe) |
| sp-stash-finder | A | sp-diagnosis | FA IL-stash SPs whose return beats playoff end, ranked by playoff xFP |
| sp-stuff-board | A | sp-boards | Stuff+ RoS FP/start board (validated single lens; Location+ REJECTED note carried) |
| sp-week-plan | A | sp-cap | Monday week-plan vs 10-start cap; weakest-start bench call |
| stream-the-stack | O | streamers | Daily FA SP streamers filtered by boom_stack tier ≥2 |
| streamer-precision-board | O | streamers | Daily MINE+FA probables board ranked by FADJ (floor-adjusted xFP), owner-module powered |
| trade-deadline | M | meta | Trade bundle: league-deep-audit → conviction-scan → opp-watch → trade-target-scan |
| trade-target-scan | A | league | live_marginal sell-bait / ask-targets + per-manager pitch templates |
| trending | A | cross-lens | Fast-stabilizing physical trend (bat speed 3-axis / FB velo); display-only early read |
| triangulate | A | cross-lens | Reference implementation: PL + model + archetype 3-lens card w/ synthesized verdict |
| validate-feature | A | ops | The 9-rule multi-testing protocol gate before any ranker promotion |
| xfp-board | O | hitter-boards | Merged roster+FA RoS/playoff xFP HTML boards (SP + 5 hitter buckets); engine also a refresh artifact |

## Executed this session (safe subset)

**Deprecation banners:** none newly needed. The five superseded skills
(`sp-slate-grid`, `sp-pl-board`, `fa-sp-pool`, `fa-rp-pool`, `boom-stack-explain`)
already carry MERGED/ABSORBED banners below frontmatter (added 2026-07-04) that
name the successor and keep the recipe live as delegate — exactly the intended
pattern. Verified all five banners present and correct.

**Stale-content fixes (3 files):**

1. `.claude/skills/hitter-slate-grid/SKILL.md` — the "Related" pointer to
   `/boom-bust-history` still cited the pre-recalibration hitter cutoffs
   (boom ≥10 / bust <2). Fixed to ≥5 / <0 per
   `boom_bust_cutoff_recalibration_2026-06-28.md` (the old cutoffs fired
   3%/57% = useless).
2. `.claude/skills/fa-monitor/SKILL.md` — frontmatter + body said "12 signal
   types — 6 core + 5 RP-leverage" (=11). Engine `run_fa_monitor.py` has 12:
   A-F plus J-O including **Signal O rating-arc riser**, which the doc omitted.
   Fixed both spots to "6 core (A-F) + 6 extended (J-O … rating-arc riser)".
3. `.claude/skills/monday-morning/SKILL.md` — frontmatter chain omitted the
   roster-health step that the body (step 3) includes. Fixed description to the
   6-step chain.

**Verified clean (no action):** all engine paths exist; rejected-signal
references appear only as warnings (roster-health warns off n_pos_flags,
hitter-slate-grid carries the hitter-BUY-LOW-REJECTED caveat, sp-stuff-board
carries the Location+ rejection, sp-decline/rp-decline are built ON the
rejection of slope features). No skill directory deleted or restructured.

**Cross-references to alias skills:** ~20 SKILL.md files still reference
`/fa-sp-pool`, `/sp-slate-grid`, etc. by their old names. NOT edited — the
aliases are live delegates by design (they trigger and redirect), so these
references still resolve. Registry documents the alias policy.

## Consolidation proposals (NOT executed — structural, need dedicated sessions)

### P1 — Streamer surface: merge `stream-the-stack` into `streamer-precision-board`

Both answer "which FA SP do I stream today" over the same universe (confirmed
probables ∩ FA pool, Connelly-Early verified); they differ only in ranking lens
(boom_stack tier filter vs FADJ floor-adjusted rank). `daily-edge` currently
runs BOTH as separate steps (3 and 4), re-rendering overlapping rows.
**Proposal:** `streamer-precision-board` grows a `boom_stack` column (from
`sp_boom_stack_full_pool_<date>.json`) + optional `--filter boom>=2`;
`stream-the-stack` becomes a delegating alias (same banner pattern as
sp-slate-grid); `daily-edge` drops to a 3-step chain. **Breaks:** daily-edge
step list, a dozen trigger phrases (kept via the alias), and the
tier-aware-threshold logic in stream-the-stack must port into the board.

### P2 — Hitter-board core: `hitter-board --mode {slate|merged|level|replace|compare}`

Five skills render ranked hitter tables off the same joins (rh3 + Blended xFP +
FA pool + ownership): `hitter-slate-grid` (superset, canonical),
`xfp-board` (RoS+playoff dual rank, HTML), `level-board` (season LEVEL vs rh3),
`fa-replacement-pool` (Δ vs drop target), `hitter-compare` (2-6 head-to-head).
Registry section 2 already envisions "thin modes over one FA-board core"; the
shipped `sp-board --scope` dispatcher is the template. **Proposal:** one
`hitter-board` dispatcher skill; the five become mode delegates (aliases kept).
**Breaks:** `xfp-board`'s engine doubles as a refresh-pipeline artifact
(xfp_board.html, GH Pages nav) — its ENGINE must stay untouched, only the
skill entry point merges; fa-replacement-pool also covers pitchers, so the
`replace` mode must dispatch to fa-pitcher-pool for P drops.

### P3 — Hitter-form sweeps: one `hitter-form` skill for the three sweep variants

`hitter-sustainability` (my-roster/FA 9-marker sweep on rh3),
`league-breakout-sustainability` (league-wide 5-axis scorecard), and
`career-form-rank` (L150 career-percentile landscape) are three sweeps over
the same rolling-window caches answering "whose form is real" at different
scopes with different scorecards. **Proposal:** `hitter-form --scope
{roster|fa|league} --lens {sustainability|breakout|career-pct}` sharing the
one window-metrics + Bayesian-shrink helper the registry already mandates;
keep `breakout-sustainability` and `slump-or-decline` as single-player
deep-dives (distinct verdicts, richer per-player panels). **Breaks:**
`roster-deep-audit` step list (chains career-form-rank + hitter-sustainability
by name) and the scorecard tiers must be reconciled (LEGIT… vs SUSTAINABLE…)
or kept per-lens.

### P4 (observation, no action) — Process-direction family

`rating-arc`, `trending`, `sp-decline`, `rp-decline`, `conviction-scan` all
answer "is the underlying skill moving" via separately-validated engines with
different windows/substrates. Keep separate — each has its own validation memo
and Rule-13 framing — but the registry now documents the seam so nobody builds
a sixth.

## Skills the user probably forgot exist (high-value, low-recall)

- **`/sp-bench-mc`** — the MC tiebreaker for genuinely unclear cap-bench calls
  (self-aware: says when it's "not earning complexity"). Untouched since 5/21.
- **`/career-form-rank`** — the anti-buy-high lens (FA at 99th career pct vs
  your guy at 13th). Predates most boards; still the only career-percentile view.
- **`/savant-compare`** — percentile visual-proof layer for convincing-yourself
  moments; supports historical-season anchors.
- **`/opp-watch`** — predicts opponent adds BEFORE they happen; profile-refit
  from panel data is now possible (~4 weeks of snapshots accumulated since 6/04).
- **`/sp-rehab-tracker`** — the Jared Jones lens; run weekly during active
  rehabs (Rodón arc showed up in rating-arc first, this confirms from MiLB data).
- **`/scouting-report`** — league-wide trade-target heat map in one cheap pass;
  complementary to conviction-scan and much lighter than league-deep-audit.
- **`/level-board`** — the validated "season level is the best simple predictor"
  read; fastest sanity check before any hitter add.
- **`/forced-drop-planner`** — pre-computes the cap-breach date when IL arms
  stack up (Glasnow/Fried pattern); relevant again with July IL returns.

## Placeholder — new skills being added 2026-07-10 (other agents, this session)

`model-health`, `volume-watch`, `consensus-diff`, `matchup-leverage` — see
SKILL_REGISTRY.md "Added 2026-07-10" section; descriptions TBD by orchestrator.

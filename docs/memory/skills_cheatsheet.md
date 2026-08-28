# Skills — decision-moment cheat sheet (full table)

<!-- Extracted VERBATIM from CLAUDE.md on 2026-08-28 (issue #46). CLAUDE.md is
auto-loaded into every session and had drifted to 635 lines against its own
~200-line budget; every line is a permanent tax on every turn, and a gotcha
list nobody finishes reading is a gotcha list that does not fire.

Nothing here was rewritten or shortened — the text below is what CLAUDE.md
carried. CLAUDE.md keeps a one-line headline per rule, numbered identically,
so the rule still fires from the auto-loaded file and the evidence is one hop
away. Numbering is load-bearing: memos and skill docs cite "gotcha #12" and
"don't-do #10" by number. Never renumber; retire in place. -->

Canonical names only; ~16 aliases still resolve (old names redirect). The
FULL enforced catalog + ownership seams live in
`.claude/skills/SKILL_REGISTRY.md` (`tests/test_skills_registered.py` keeps
it in sync with disk — trust it over this summary). Depth lives in each
SKILL.md; this table routes.

**Guards — ALWAYS, before any claim:** `/roster-verify` (is-mine),
`/player-id-resolve` (name collisions), `/pitcher-role` (SP/RP truth incl.
the Jax RP-slot-lag rule).

**Domain masters (2026-07-20) — one command runs a whole domain:**
`/daily-rhythm` (whats-new → daily-edge → monday-morning, day-aware) ·
`/moves` (gates → churn verify → cap → forced-drop) · `/player-verdict <names>`
(triangulate → bucket-correct compare → boom-bust → ONE answer) ·
`/all-boards` (every board, one FA pull) · `/form-check` (all form lenses,
roster-wide, flag-routed deep-dive queue).

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
| **Roster moves, P(win)-denominated (NEW 2026-07-29)** | `run_weekly_optimizer.py` — searches legal add/drop/swap combos maximizing ΔP(win), not E[FP]. Enforces 13H/9P/4BE/3IL, the **4-RP FLOOR**, last-catcher coverage, the period-aware SP cap, and lineup capacity (13 × days-remaining). Reports `mc_se` so an edge is separable from MC noise, and says WHY a tempting move is illegal. **Run it BEFORE executing** — see the ledger note below. |
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


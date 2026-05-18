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
- `/fa-replacement-pool` — broad scan: given a player to drop, returns
  ranked FA replacement candidates above a season-FP threshold with
  rh3 join, Δ vs drop target, and positional-flex match. Uses the
  unfiltered `size=2000` pattern (see `feedback_fa_pool_size_cap.md`).
- `/hitter-compare` — 2-6 player head-to-head: Statcast L21d/season
  table, rh3 row, lineup spot, ESPN counting stats per player, plus
  a comparative verdict. Fills the gap that `/fa-pickup-deep-dive`
  explicitly flags.
- `/pl-cross-reference` — fetches current week's Pitcher List rankings
  via WebFetch and cross-references against our model picks, surfacing
  divergence with bias context (PL is rate-stat / 12-team mindset).
- `/sp-week-plan` — Monday-morning pitcher planning: projects week's
  starts against 10-SP cap, identifies weakest start to bench, flags
  long-IL SPs as drop candidates.

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

## Memory pointers (for context-dense lookups)

All in `~/.claude/projects/c--Users-Joshua-plv-clone/memory/`:

- `MEMORY.md` — index, always loaded
- `reference_league_rules.md` — full BrownU scoring + roster spec
- `reference_validated_signals_registry.md` — what's allowed to drive decisions
- `reference_multitesting_protocol.md` — the 9 rules (Rule 8 framing, Rule 9 baseline)
- `feedback_il_slot_vs_il_status.md` — slot counting gotcha
- `feedback_validate_before_ship.md` — anti-promotion-without-validation rule
- `feedback_save_handcuffs_needs_closer_context.md` — closer ranking nuance

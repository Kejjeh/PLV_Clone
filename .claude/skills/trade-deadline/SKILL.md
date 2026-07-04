---
name: trade-deadline
description: Trade-evaluation / sell-high meta-skill that chains league-deep-audit → conviction-scan (model-vs-process divergence, the buy-low/sell-high surface) → opp-watch → trade-target-scan into one report, threading the 11-layer league panel and one FA/roster pull through every step. Use when evaluating a trade, hunting sell-high windows, or scanning the league for undervalued targets. NO trades are executed — this produces the decision surface only.
---

# trade-deadline

Runs the full trade-evaluation workflow in one pass (SKILL_REGISTRY section 3,
bundle **trade-deadline**):

1. **league-deep-audit** — the 11-layer, calibrated league-wide statistical
   panel (career-form, sustainability, MC bounce, Bayesian posterior,
   historical comps, decline curves) — the shared substrate for the rest
2. **conviction-scan** — model-vs-process divergence board (PROCESS>MODEL =
   buy-low WATCH; MODEL>PROCESS = sell-high WATCH). This is the standing
   buy-low/sell-high surface until the dedicated **buy-low-sell-high-scan**
   skill ships (pending, SKILL_REGISTRY section 2)
3. **opp-watch** — predict each opponent's next roster move (per-team
   behavioral profiles) so a trade offer is framed to their tendencies
4. **trade-target-scan** — rank concrete acquisition targets, now annotated
   with the ROLE+AGE keeper/trade lens (item 2)

For any specific player, run `/triangulate <name>` for the 3-lens verdict.

---

## Shared data (pull ONCE, thread through all steps)

```python
from app.espn_connector import get_all_teams, get_free_agents
import pandas as pd

teams  = get_all_teams()               # league-wide roster state (all 8 teams)
fa_all = get_free_agents(size=2000)    # never <2000

rh3   = pd.read_csv('data/outputs/xfp_rh3_projections.csv')
rp3   = pd.read_csv('data/outputs/xfp_rp3_projections.csv')
rprs2 = pd.read_csv('data/outputs/xfp_rprs2_projections.csv')
```

All joins by MLBAM id via
`plv_clone.utils.name_match.resolve_batter_id/resolve_pitcher_id` — never a
name-only `str.contains` (gotcha #10). Verify ownership only via
`get_all_teams()` (gotcha #7 — PL rank / percent_owned are NOT roster truth).

---

## Step 1 — league-deep-audit (condensed)

Run `/league-deep-audit` once; carry its per-player panel (career-form,
sustainability bucket, MC bounce, Bayesian posterior, comp outcomes) forward
as the substrate for steps 2-4. Do not recompute these downstream.

## Step 2 — conviction-scan (buy-low / sell-high surface)

```python
# run_conviction_scan.scan() → mlbam-keyed divergence tags (Rule 13: context only)
# PROCESS>MODEL = patience/buy-low WATCH; MODEL>PROCESS = distrust/sell-high WATCH
python scripts/xfp/run_conviction_scan.py --top 12
```

Rule 13: divergence NEVER moves rh3/rp3 and never re-ranks — it sets
conviction and routes to `/triangulate`. Hitter buy-low was REJECTED as an
additive signal (−0.069 FP/PA) — treat the hitter flavor as context only.

## Step 3 — opp-watch (condensed)

Run `/opp-watch <team>` per opponent of interest, using `teams` from shared
data. Frames a trade offer to the target manager's behavioral profile.

## Step 4 — trade-target-scan (condensed)

Run `/trade-target-scan`. Surface the **ROLE+AGE (annual-value z)** keeper/
trade lens per candidate (item 2 — ANNUAL horizon only, Rule 13 context).

---

## Output format

```markdown
# Trade Deadline — <date>

## Sell-high windows (MODEL>PROCESS)
<table: player · model pct · process pct · divergence · sustainability>

## Buy-low windows (PROCESS>MODEL)
<table — SP flavor validated; hitter flavor CONTEXT ONLY>

## Opponent tendencies
<per-team: likely next move + how to frame an offer>

## Concrete targets (ranked)
<table: target · Δ vs my hold · ROLE+AGE annual-value z · verdict>

## Recommended offers (≤3) — DECISION SURFACE ONLY
1. ...
```

---

## Anti-patterns this bundle exists to prevent

- Recomputing the league panel in every step — audit once, thread through
- Folding conviction / ROLE+AGE / sustainability into a headline number (Rule 13 — display/context only)
- Treating hitter buy-low divergence as additive lift (REJECTED, −0.069 FP/PA)
- Concluding a player is available without `get_all_teams()` (gotchas #7, #4)

## When NOT to use

- Single-player hold/sell question → `/slump-or-decline` or `/triangulate`
- Weekly roster upkeep → `/monday-morning`

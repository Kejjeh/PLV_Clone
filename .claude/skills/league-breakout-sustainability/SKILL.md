---
name: league-breakout-sustainability
description: ALIAS → /hitter-form --scope league. Recipe lives below; routing/triggers live on the canonical.
---

> **⚠ MERGED (2026-07-20) → `/hitter-form --scope league`.** This SKILL holds
> the complete 5-axis league-wide scorecard recipe and stays live as the
> delegate; new invocations should prefer `/hitter-form --scope league`
> (routing + trigger phrases live on the canonical).

# league-breakout-sustainability

You are producing a league-wide breakout-sustainability ranking for **every
hitter in the user's league** (own roster + other 7 teams' rosters + FA pool).
The skill exists because the single-player `/breakout-sustainability` and the
2-6 player `/hitter-compare` skills can't surface trade targets, drop candidates,
or hidden FA breakouts that are out of view.

It's the methodology from `/breakout-sustainability` applied at scale to
~640+ MLB hitters with PA ≥ 80 in 2026.

---

## Inputs (all optional)

1. **Min PA gate** — default 80. Below that, individual scores are too noisy.
2. **Focus tier** — default `all`. Options: `sustainable`, `narrow`,
   `power-only`, `decline`, `all`.
3. **Position filter** — default none. e.g., `1B`, `OF`, `C`.

---

## Step 1 — Pull all three player pools

```python
from app.espn_connector import (
    get_my_roster_with_injuries,
    get_all_teams,
    get_free_agents,
)
my_roster = get_my_roster_with_injuries()         # mine
all_teams = get_all_teams()                       # all 8 teams (incl. mine)
fa_pool   = get_free_agents(size=2000)            # unfiltered FA — see feedback_fa_pool_size_cap.md
```

Build a unified frame with one row per (player_name, mlbam) and a `source`
column = `MY_ROSTER` / `OTHER:<team_name>` / `FA`. Dedupe — a player can
appear in only one pool. Tag injury status from `get_my_roster_with_injuries()`
where available.

**Critical:** use `size=2000` on `get_free_agents()`. The per-position
`size=300` pattern silently drops low-owned high-FP candidates
(see `feedback_fa_pool_size_cap.md`).

---

## Step 2 — Resolve MLBAM batter IDs

ESPN player_id ≠ MLBAM batter_id. Resolve via fuzzy match on `player_name`
against `hitters_multiyr_2015_2026.csv`. Apply accent folding
(`unicodedata.normalize('NFKD', name)`) so "Eugenio Suárez" matches
"Eugenio Suarez".

For ambiguous cases (canonical: Max Muncy LAD vs ATH), use
`plv_clone.utils.name_match.resolve_batter_id(name, team=..., position=...)`
— this consults `KNOWN_COLLISIONS` and refuses to silently guess. Do NOT
build a naïve `dict[name]=batter_id` lookup. See
`feedback_player_name_collisions.md`.

---

## Step 3 — Filter to candidates

Drop any row with `pa26 < 80` (stabilization gate). At PA<80 the
95% CI on xwOBA is ±0.085, too wide for breakout detection.

Drop any row missing both 2025 AND 2026 multiyr rows. Pure rookies (only
2026 row, no 2025 baseline) get tagged `ROOKIE_DEBUT` rather than scored —
the YoY delta is undefined.

---

## Step 4 — Compute the 5-axis sustainability scorecard

For each candidate:

```python
# Axis 1: Bayesian-shrunk gap
k_prior = 150.0
baseline_xw = xw25  # 2025 full-year xwOBA per PA
shrunk_xw = (pa26*xw26 + k_prior*baseline_xw) / (pa26 + k_prior)
shrunk_gap = shrunk_xw - baseline_xw
axis1 = shrunk_gap >= 0.020

# Axis 2: process improvement count (whiff/chase/K — count those that improved)
proc_axes = sum([
    w26 < w25 - 0.005,
    ch26 < ch25 - 0.005,
    k26 < k25 - 0.005,
])
axis2 = proc_axes >= 2

# Axis 3: power improvement count (EV90/hard-hit/xwOBACON)
pow_axes = sum([
    ev26 > ev25 + 0.3,
    hh26 > hh25 + 0.01,
    xc26 > xc25 + 0.01,
])
axis3 = pow_axes >= 2

# Axis 4: CI distinguishability
se = 0.39 / np.sqrt(pa26)
ci_lo, ci_hi = xw26 - 1.96*se, xw26 + 1.96*se
axis4 = (xw25 < ci_lo) or (xw25 > ci_hi)

# Axis 5: career-best xwOBACON in 2026
career_peak_xc = sub[sub['pa'] >= 250]['xwoba_on_contact'].max()
axis5 = xc26 >= career_peak_xc - 0.005   # within 5pt of career best
```

Score = sum of 5 booleans (0..5).

---

## Step 5 — Tier

```
score >= 4  → SUSTAINABLE        (strongest — multi-axis, distinguishable, career-best)
score == 3  → NARROW BREAKOUT    (real improvement on most axes)
score == 2  → MIXED              (one-axis breakout, watch list)
score == 1  → HOT STREAK         (one indicator only — likely revert)
score == 0  → HOT STREAK (deep)

shrunk_gap < -0.020 AND (xw26 < xw25 - 0.020)  → DECLINE
```

Power-only sub-tag: if `pow_axes >= 2 AND proc_axes == 0`, append `[POWER-ONLY]`
— this is the Suárez 2025 archetype (capped AVG/OBP, HR-or-bust).

Discipline-only sub-tag: if `proc_axes >= 2 AND pow_axes == 0`, append
`[DISCIPLINE-ONLY]`.

---

## Step 6 — Output ranking (markdown)

Tier blocks in order: **SUSTAINABLE → NARROW BREAKOUT → POWER-ONLY → MIXED →
HOT STREAK → DECLINE → ROOKIE DEBUT (no baseline)**. Within each tier sort by
2026 xwOBA descending.

Columns per row: `player | pos | source | own% | pa26 | xw26 | xwc26 | Δ xwc YoY | shrunk_gap | pow / proc axes | tier-specific note`.

The `source` column is the actionable bit:
- `MY_ROSTER` = your player
- `OTHER:<team>` = on another roster (trade target / sell-high context)
- `FA` = available pickup

---

## Step 7 — Action callouts

Below the tables, three explicit recommendations:

1. **Top FA SUSTAINABLE adds** (own% < 50%, sorted by shrunk_gap descending)
   — these are the breakouts not yet rostered in your league.
2. **Trade targets** (other-roster MIXED/HOT-STREAK tier where their owner
   may be selling on a perceived breakout that the scorecard rejects).
3. **Drop watch on own roster** (HOT-STREAK or DECLINE tier on MY_ROSTER) —
   players you've been holding on hope that the score says aren't sustainable.

---

## Anti-patterns this skill exists to prevent

- **Ranking on raw 2026 xwOBA alone** — without the YoY decomposition this
  collapses breakouts and steady stars together. The whole point is to
  separate them.
- **Using full-year fp_strike or similar leaky features** as inputs —
  see `feedback_convergence_curve_leakage_detector.md`. Stick to the
  hitters_multiyr cache + 2025/2026 row comparison.
- **Forgetting injury context** — a player flagged DECLINE may just be
  playing hurt. Always check the IL game-log for any DECLINE-tier candidate
  before issuing a SELL/DROP. See `feedback_check_il_before_decline_call.md`.
- **Skipping accent folding** — "Eugenio Suárez" must match "Eugenio
  Suarez". Always apply `unicodedata.normalize('NFKD', name)` before joining
  ESPN data to MLBAM data.
- **Naïve dict[name] = batter_id** — same-name collisions (Muncy LAD vs ATH)
  produce silently wrong joins. Always use `resolve_batter_id(name, team=..., position=...)`
  for same-name MLB players.

---

## When NOT to use this skill

- Single-player evaluation → `/breakout-sustainability`
- 2-6 player head-to-head → `/hitter-compare`
- Identifying a single FA pickup with deep context → `/fa-pickup-deep-dive`
- SP sustainability → `/sp-breakout-signal` (different metrics needed)

This skill is the **league-wide aerial view** — use it weekly or when
restructuring trade targets / drop candidates / FA scans across all your
options at once.

---

## Output expectations

After a successful run:
1. A CSV: `data/research/league_breakout_sustainability_<date>.csv` with all
   scored candidates + tier + per-axis breakdown
2. A markdown ranking in the assistant's response, tiered as above
3. Three explicit action callouts (top FA add, top trade target, top drop watch)
4. Production script: `scripts/xfp/build_league_breakout_sustainability.py`

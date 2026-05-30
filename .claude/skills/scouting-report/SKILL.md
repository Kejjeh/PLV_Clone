---
name: scouting-report
description: League-wide Monday-morning scouting brief that surfaces 10-20 highlight players across all 8 BrownU teams who are TRENDING_UP, at CAREER_HIGH, have just received an ARCHETYPE_UPGRADE, posted a LEVERAGE_RISE (RP), shown a BREAKOUT_PROCESS jump in underlying skill ratings, or fit the AGE_PROFILE_GOAT pattern (PRE_PEAK + SOLID boundary). Roster-ownership × archetype-trajectory cross-product — the proactive trade-target / breakout-watch layer that complements reactive roster-health audits. Triggered by "scouting report", "monday scouting", "trending up", "breakout watch", "career high", "weekly scouting brief", "who's heating up in the league", "league wide trending".
---

# scouting-report — league-wide proactive scouting brief

Single weekly read across all 8 BrownU rosters that surfaces players whose **process** (archetype trajectory, boundary tier, slope, sub-domain ratings) is positioned for outsized forward value. Different from `/roster-audit` (mine-only, reactive) and `/league-deep-audit` (full multi-layer audit). This skill is **fast, league-wide, and forward-looking** — built entirely off the master ratings CSVs + a single ESPN roster fan-out.

**Trigger phrases:** "scouting report", "monday scouting", "weekly scouting brief", "trending up", "career high", "breakout watch", "who's heating up in the league", "league-wide trending", "movers brief".

---

## What this skill is NOT

- Not `/roster-audit` (mine-only, reactive — fixing slot/IL/cap problems)
- Not `/league-deep-audit` (full 11-layer audit — heavyweight, weekly-at-most)
- Not `/sp-archetype scan` or `/hitter-archetype scan` (those are league-wide on archetype trajectory but **not roster-aware** — they don't tell you who owns the player)

Unique value: **roster ownership × archetype trajectory in one brief.** Surfaces who is positioned for forward value AND who actually has them — the trade-target / breakout-watch layer.

---

## Data sources (read, do not re-derive)

```
data/research/hitter_ratings_master.csv   — hitter 20-80 ratings + traj_flag + slope + career_pct + archetype + boundary_tier
data/research/sp_ratings_master.csv       — SP same
data/research/rp_ratings_master.csv       — RP same + leverage_tier + CLOSER + role
```

Roster ownership: `app.espn_connector.get_all_teams()` — iterate, pull every roster, build a `name → team_name` map across all 8 teams. Use `plv_clone.utils.name_match.resolve_batter_id` semantics for collision-safe matching where possible; otherwise a normalized lower-case strip is acceptable for this surface (Connelly / Muncy gotchas don't apply here because output is annotated by team, not filtered to "mine vs not-mine").

Filter every CSV to `year == 2026` before classifying.

---

## Categories (6 total)

For each rostered player across all 8 teams, evaluate against the six categories. A player can land in multiple buckets — surface them once in the strongest category, mention the secondary in the row note.

### 1. TRENDING_UP — sustained 3-year climbers

```
traj_flag == 'TRENDING_UP'  AND  OVERALL_slope_3yr >= 4
```

Stable upward arc, not a single-year spike. The slope floor of 4 (≈ +4 OVERALL points per year, sustained 3 years) is the bar for "real trend, not noise." Show players with the highest slope first.

### 2. CAREER_HIGH — peak-form moments worth noting

```
OVERALL_career_pct >= 0.90  AND  (current OVERALL == max of player's career OVERALL across all years)
```

Different from TRENDING_UP because TRENDING_UP captures sustained climb (which may not be a new high); CAREER_HIGH captures the player's current year being their personal best AND a top-decile mark within their career. Read the master CSV grouped by `batter` / `pitcher` to confirm "is 2026 the max year for this player."

### 3. ARCHETYPE_UPGRADE — fresh tier jump versus last year

This year's archetype is a higher tier than the player's last qualified year. Specific upgrade ladders:

**Hitters** (use the archetype matrix in `hitter-archetype/SKILL.md`):
- `GENERIC_NO_POWER / AVERAGE_HITTER / BACKUP_BAT / FRINGE / BUST` → any non-fringe label
- `POWER_HITTER / PURE_HITTER / BALANCED_EYE / SLAP_HITTER` → `POWER_EYE / CONTACT_POWER / CONTACT_EYE / SLAP_AND_WALK`
- any → `GOAT_TIER / CONTACT_POWER / POWER_EYE / CONTACT_EYE` (elite tier)

**SPs** (matrix in `sp-archetype/SKILL.md`):
- `LIABILITY / FILLER / GENERIC_HR_PRONE / PIT_CHF / WILD_MID / AVERAGE_4_5` (back-end) → `PURE_STUFF / PURE_MOVEMENT / PURE_CONTROL / WILD_FIREBALLER / JUNKBALLER` (mid-rotation)
- mid-rotation → `STUFF_PLUS_MOVE / STUFF_PLUS_CTRL / MOVE_CTRL_ACE` (frontline)
- frontline → `MT_RUSHMORE` (ace)

**RPs** (matrix in `rp-archetype/SKILL.md`):
- `GENERIC_MIDDLE / COMMAND_MIDDLE / WILD_HIGH_LEVERAGE` (middle) → any non-middle label
- middle → high-leverage / closer archetypes
- any → `ELITE_CLOSER_STUFF`

For each upgrade, call out FROM → TO and the year of the prior archetype.

### 4. LEVERAGE_RISE — RP role-change in progress (RP only)

```
RP whose 2026 leverage_tier is higher than their 2025 leverage_tier
```

Tier order (low → high): `GARBAGE_TIME < LOW_LEVERAGE < MID_LEVERAGE < HIGH_LEVERAGE < ELITE_LEVERAGE`. A jump of 2+ tiers (e.g. MID → ELITE) is a stronger signal than 1 tier. Surface the gmLI band on the row.

This is meaningful because leverage_tier is a usage/role signal — a rise indicates the manager is trusting the RP in higher-leverage spots, often the pre-cursor to a saves role. Combine with `CLOSER` tag transition for confirmation.

### 5. BREAKOUT_PROCESS — sub-domain ratings jump (process improvement)

Real underlying-skill improvement, year-over-year deltas in sub-domains.

**Hitters:** `r_xCON`, `r_Barrel`, `r_HardHit` ALL jumped ≥ 10 points vs prior year (means contact quality genuinely improved across three independent measures — barrel rate, hard-hit rate, and xwOBA-on-contact).

**SPs:** `r_SwStr`, `r_CSW`, `velo_rating` ALL jumped ≥ 8 points vs prior year (swing-and-miss rate, called+swinging strike rate, and velocity all climbing — the trifecta of stuff improvement).

**RPs:** `r_K`, `swstr_pct` (computed as percentile bump ≥ 8 equivalent), `avg_velo` rising — if all three present in master CSV per RP. Use the SP-style trigger by analogy: rated swing-and-miss components up ≥ 8.

The "all three" requirement is intentional — single-component jumps can be noise; concordant 3-component jumps survive the multi-test bar.

### 6. AGE_PROFILE_GOAT — PRE_PEAK + SOLID

```
age_tier == 'PRE_PEAK'  AND  boundary_tier == 'SOLID'  AND  OVERALL >= 60
```

Young players who have already cracked the SOLID boundary tier (well inside their archetype cell — label is durable) AND clear an OVERALL ≥ 60 (above-average rating). These are the youngest + most-durable combination — the highest dynasty market value bucket. The OVERALL floor prevents a `SOLID` boundary on a `BUST` archetype from showing up.

---

## Output structure

Lead with date and week number (compute from current date — BrownU H2H scoring weeks usually start Monday). Output sections in this exact order:

```markdown
# League Scouting Brief — Week N (YYYY-MM-DD)

## TRENDING_UP — sustained climbers across all teams (3-7 players)

### Player A — POWER_EYE (PEAK, SOLID, OVERALL 67, +6 slope 3yr) — C=58 P=64 D=63
- Rostered: <Team Name>
- Reasoning: 3yr slope +6, archetype stable (3 years in POWER_EYE), boundary SOLID
- Action: trade target (or hold-with-context if already mine)

### Player B — ...

## CAREER_HIGH — peak-form moments worth noting (3-7)

### Player C — STUFF_PLUS_CTRL (PEAK, SOLID, OVERALL 73, career pct 0.96) — S=68 M=55 C=66
- Rostered: <Team Name>
- Reasoning: 2026 is highest OVERALL of their 8-year career; previous high 71 (2023)
- Action: ...

## ARCHETYPE_UPGRADE — fresh archetype transitions (3-7)

### Player D — FROM AVERAGE_4_5 (2025) → TO STUFF_PLUS_MOVE (2026) — S=64 M=62 C=51 (dS+12 dM+9 dC+3)
- Rostered: <Team Name>
- Reasoning: frontline jump — STUFF +12, MOVEMENT +9; boundary NEAR_EDGE on STUFF
- Action: ...

## LEVERAGE_RISE — RP role-change candidates (2-4)

### Player E — MID_LEVERAGE (2025, gmLI 1.05) → ELITE_LEVERAGE (2026, gmLI 1.62) — S=66 C=60 B=55
- Rostered: <Team Name>
- Reasoning: 2-tier jump; CLOSER tag flipped True in 2026
- Action: ...

## BREAKOUT_PROCESS — process metrics jumping (3-5)

### Player F — CONTACT_POWER, C=60 P=64 D=51 — Process triggers: r_xCON +13, r_Barrel +11, r_HardHit +14
- Rostered: <Team Name>
- Reasoning: all three contact-quality components jumped 10+; underlying skill improvement is real
- Action: ...

## AGE_PROFILE_GOAT — PRE_PEAK + SOLID combinations (2-4)

### Player G — POWER_EYE, age 24 (PRE_PEAK), SOLID, OVERALL 64 — C=52 P=66 D=63
- Rostered: <Team Name>
- Reasoning: durable archetype + young + above-average OVERALL — dynasty-shape upside
- Action: stash if available (FA), otherwise long-term hold

## Action priorities (5 things to consider this week)

1. <Player from Team Foo> — sustained TRENDING_UP, no decline signals — pursue in trade
2. <Player on YOUR roster> — at CAREER_HIGH, sell-high candidate (peak-form mirage risk?)
3. <FA player from any bucket> — actionable add right now
4. <RP with LEVERAGE_RISE> — handcuff target
5. <ARCHETYPE_UPGRADE player elsewhere> — monitor for trade window
```

**Output rules:**
- Always include the player's raw ratings inline (`C=X P=Y D=Z` for hitters, `S=X M=Y C=Z` for SPs, `S=X C=Y B=Z` for RPs). Archetype label without the underlying numbers violates the same rule as `/sp-archetype` and `/hitter-archetype` — the numbers are the actual information.
- Limit each section to 3-7 players (or 2-4 for the RP-only and AGE_PROFILE_GOAT sections). Total across all sections: **10-20** players. If a category is empty, write "(no players matched this week)" — do not pad.
- For each player, always state their team owner. If the player is on **YOUR** roster (New York Ligers), label as **YOURS** and adjust the action accordingly (validate the breakout, consider sell-high if at CAREER_HIGH).
- If a player is a free agent (matches no team), label as **FA** and flag as an immediate add candidate.

---

## Step-by-step execution

### Step 0: Data freshness check
Verify all three master CSVs were modified within the last 36 hours. If stale, suggest running `python scripts/xfp/refresh_dashboards.py` first.

### Step 1: Load + filter
```python
import pandas as pd
from pathlib import Path
REPO = Path(r'c:\Users\Joshua\plv_clone')

hit = pd.read_csv(REPO / 'data/research/hitter_ratings_master.csv')
sp  = pd.read_csv(REPO / 'data/research/sp_ratings_master.csv')
rp  = pd.read_csv(REPO / 'data/research/rp_ratings_master.csv')

CUR = 2026
hit_cur = hit[hit['year'] == CUR].copy()
sp_cur  = sp[sp['year'] == CUR].copy()
rp_cur  = rp[rp['year'] == CUR].copy()
```

### Step 2: Roster fan-out
```python
from app.espn_connector import get_all_teams
teams = get_all_teams()
name_to_team = {}
for t in teams:
    for p in t.roster:
        name_to_team[_norm(p.name)] = t.team_name
```

### Step 3: Apply 6 category filters (see definitions above)

For each category, sort by:
- TRENDING_UP — by `OVERALL_slope_3yr` desc
- CAREER_HIGH — by `OVERALL_career_pct` desc
- ARCHETYPE_UPGRADE — by archetype-tier delta (FP/start or FP/PA implied lift)
- LEVERAGE_RISE — by tier-jump magnitude, then by gmLI
- BREAKOUT_PROCESS — by mean of the 3 triggering deltas
- AGE_PROFILE_GOAT — by OVERALL desc

### Step 4: Annotate with roster owner
Each row gets one of: `YOURS`, `<TeamName>`, or `FA`.

### Step 5: Cap counts and write markdown

Limit each section as specified; total 10-20 players. Write the final markdown to stdout. Do **not** create a file in `data/outputs/` — this skill is read-and-report only.

---

## Anti-patterns to avoid

1. **Recommending a TRENDING_UP player without checking boundary tier.** A `TRENDING_UP` with `boundary_tier == EDGE` is fragile — the label could flip with one bad month. Always show the boundary tier in the row.
2. **Surfacing CAREER_HIGH on a player with age_tier == POST_PEAK.** Peak-form moments late in career are often sell-high, not hold. Flag in the row note.
3. **ARCHETYPE_UPGRADE on a player with prior-year n_pa or gs below the qualifying threshold.** A jump from "no qualifying year" to a frontline archetype is sample-noise, not a real upgrade. Require the prior year to have valid OVERALL.
4. **LEVERAGE_RISE without checking CLOSER tag transition.** A rise from MID to HIGH without the closer tag may just be middle-relief reshuffling.
5. **BREAKOUT_PROCESS triggers from only 1-2 sub-domains.** Single-component process jumps are noise; the "all three" requirement is what survives multi-testing.
6. **Putting the same player in multiple sections.** Pick the strongest category for them, mention the secondary in the row note ("also at CAREER_HIGH").
7. **Padding categories that have no matches.** If only 1 player passes BREAKOUT_PROCESS, list that one; write "(no players matched this week)" for empty categories.
8. **Annotating a player as YOURS without `/roster-verify` semantics.** Always use a live `get_all_teams()` call — never label from memory. The Weathers/Rasmussen rule.

---

## Integration with other skills

| Skill | Relationship |
|---|---|
| `/sp-archetype scan` | Upstream component — that scan is league-wide archetype trajectory but not roster-aware. This skill is `that scan × roster fan-out`. |
| `/hitter-archetype scan` | Same as above for hitters. |
| `/rp-archetype` (scan-like) | Same as above for RPs; also feeds the LEVERAGE_RISE bucket. |
| `/league-deep-audit` | Complement — this is the lightweight movers brief; that is the heavyweight 11-layer audit. Run this Monday, run that monthly or before a major trade. |
| `/roster-audit` | Complement — that is mine-only reactive; this is league-wide proactive. |
| `/monday-morning` | Sibling — could be chained: `/monday-morning` covers mine-side, this skill covers proactive trade-target side. |
| `/roster-verify` | Pre-condition — required for the YOURS label. |

---

## Example invocation

User: "Run my Monday scouting report."

Expected: a markdown brief headed `# League Scouting Brief — Week N (YYYY-MM-DD)` with the 6 sections, 10-20 total players across all 8 teams, each row including raw 20-80 ratings, owner team, reasoning, and action. Action priorities at the bottom give the user 5 concrete moves to consider this week.

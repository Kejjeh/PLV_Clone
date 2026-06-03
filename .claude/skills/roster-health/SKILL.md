---
name: roster-health
description: Signal-driven Monday morning briefing across the user's full BrownU roster. Reads validated signal CSVs (hitter/sp/rp ratings master + xfp_rh3/rp3/rprs2 projections) and surfaces 3-7 prioritized alerts — TRENDING_DOWN, COLD_BABIP, COLD_xWOBA_L21d, ARCHETYPE_DOWNGRADE, DROP_RISK for hitters; TRENDING_DOWN, ARCHETYPE_DOWNGRADE, IL_RISK, RECENCY_BAD for SPs; LEVERAGE_SLIDE, LOST_CLOSER, TRENDING_DOWN, VELO_DECLINE, USAGE_DROP for RPs. Scores HIGH/MED/LOW and recommends the right deep-dive skill per alert. Use whenever the user asks "roster health", "roster check", "monday roster", "monday morning roster", "what's wrong with my roster", or "any roster red flags". Distinct from /roster-audit (slot/cap math) and /monday-morning (chains roster-verify + roster-audit + sp-week-plan + fa-monitor) — this skill is the signal layer.
---

# roster-health — signal-driven roster briefing

Run every player on the live BrownU roster through the validated signal layer (archetype trajectories + projection recency gaps + role/leverage shifts) and produce a prioritized action list. This is the *signal* leg of Monday morning — the *slot/cap* leg is `/roster-audit`.

**Trigger phrases:** "roster health", "roster check", "monday roster", "monday morning roster", "what's wrong with my roster", "any roster red flags", "scan my roster for issues".

---

## DO / DON'T

**DO:**
- Run `/roster-verify` first. Live ESPN call via `get_my_roster_with_injuries()`. Never label players "yours" from session memory (CLAUDE.md rule #11).
- Read existing signal CSVs only. Do not re-derive archetypes, slopes, sustainability buckets, or projections — those pipelines run in `refresh_dashboards.py` and are validated.
- Pair every alert with the underlying numeric so the reader can sanity-check (e.g., `BABIP .256 vs career .302, Δ −.046`).
- Cap output: ≤ 5 HIGH alerts, ≤ 5 MED, then collapse LOW to a count + name list.
- Recommend the *next* skill to run for each HIGH alert (deep-dive routing), don't try to do the deep-dive inline.

**DON'T:**
- Don't compute slot occupancy, IL slot math, or SP cap headroom here — that's `/roster-audit`.
- Don't pull statcast L21d directly — the recency_form_gap column in `xfp_rh3` / `xfp_rp3` already encodes this and is validated.
- Don't rank RPs by `xfp_rp3` — RPs use **`xfp_rprs2`** (CLAUDE.md "validated models" table).
- Don't surface a `DROP_RISK` alert for an IL'd player. Filter `lineup_slot != 'IL'` first.
- Don't lookup batter/pitcher IDs by name alone. Use `plv_clone.utils.name_match.resolve_batter_id()` when joining roster → projection (rule #10).

---

## Data sources (read-only)

| File | Role |
|---|---|
| `data/research/hitter_ratings_master.csv` | hitter archetype, sub-types, traj_flag, OVERALL_slope_3yr, boundary_tier, babip / babip_career / babip_delta |
| `data/research/sp_ratings_master.csv` | SP archetype, traj_flag, OVERALL_slope_3yr, boundary_tier, age_tier |
| `data/research/rp_ratings_master.csv` | RP archetype, traj_flag, CLOSER, HIGH_LEVERAGE, leverage_tier (gmLI-driven), VELO, rank_in_year |
| `data/outputs/xfp_rh3_projections.csv` | hitter RoS rank + `recency_form_gap` (model-validated L21d vs baseline) |
| `data/outputs/xfp_rp3_projections.csv` | SP RoS rank + `recency_form_gap`, `is_on_il_at_split` |
| `data/outputs/xfp_rprs2_projections.csv` | RP RoS rank (use for ALL RP ranking, NOT rp3) |
| `app/espn_connector.py::get_my_roster_with_injuries()` | live roster + injury status |

---

## Execution

### Step 0 — roster-verify (mandatory pre-condition)

```python
from app.espn_connector import get_my_roster_with_injuries
roster = get_my_roster_with_injuries()  # live ESPN call
```

If the call fails, STOP and surface the error. Do not fall back to a cached roster.

### Step 1 — load signal layer

```python
import pandas as pd
from pathlib import Path
REPO = Path(r'c:\Users\Joshua\plv_clone')

hit_m = pd.read_csv(REPO / 'data/research/hitter_ratings_master.csv')
sp_m  = pd.read_csv(REPO / 'data/research/sp_ratings_master.csv')
rp_m  = pd.read_csv(REPO / 'data/research/rp_ratings_master.csv')

rh3   = pd.read_csv(REPO / 'data/outputs/xfp_rh3_projections.csv')
rp3   = pd.read_csv(REPO / 'data/outputs/xfp_rp3_projections.csv')
rprs2 = pd.read_csv(REPO / 'data/outputs/xfp_rprs2_projections.csv')

CURR_YR, PREV_YR = 2026, 2025
```

Filter ratings master to the current and prior year for each player, joined on `player_name` (with team disambiguation when a collision is known — see `/player-id-resolve`).

### Step 2 — compute alerts per player

For each rostered player, determine their role bucket (hitter / SP / RP from `roster.position` and `eligibleSlots`) and run the matching alert checks below.

#### Hitter alerts

| Code | Condition | Severity tier |
|---|---|---|
| `TRENDING_DOWN` | `traj_flag == 'TRENDING_DOWN'` OR `OVERALL_slope_3yr < -3` | HIGH if both, MED if one |
| `COLD_BABIP` | `babip_delta < -0.040` (current vs career) | MED (informational — likely bounce coming, *not* a sell) |
| `COLD_xWOBA_L21d` | `rh3.recency_form_gap < -2.5` (current production hot relative to projection baseline, expect cooling) | MED |
| `DROP_RISK` | `rh3.rank > 200` AND `xfp_rh3_per_game < replacement_xfp_per_pa * avg_PA` AND `lineup_slot != 'IL'` | HIGH |
| `ARCHETYPE_DOWNGRADE` | this year's archetype is a lower-mean-FP tier than prior year (e.g. `GOAT_TIER → POWER_EYE`, `POWER_EYE → GENERIC`) | HIGH if 2+ tier drop, MED if 1 tier |
| `AGE_TIER_TRANSITION` | `age_tier` changed PRE_PEAK→PEAK or PEAK→POST_PEAK | LOW (informational, never alerting alone) |

**Hitter archetype tier ordering** (highest → lowest mean FP, from `hitter_archetype_definitions.json`): `GOAT_TIER` > `POWER_EYE` > `CONTACT_POWER` > `EYE_CONTACT` > `PURE_POWER` > `PURE_EYE` > `PURE_CONTACT` > `GENERIC` > `BELOW_AVG`. A downgrade is moving to a strictly lower tier label across consecutive years.

#### SP alerts

| Code | Condition | Severity |
|---|---|---|
| `TRENDING_DOWN` | `traj_flag == 'TRENDING_DOWN'` | HIGH |
| `ARCHETYPE_DOWNGRADE` | 2026 archetype lower tier than 2025 (per `sp_archetype_definitions.json` ordering: MT_RUSHMORE > STUFF_PLUS_CTRL > STUFF_PLUS_MOVE > MOVE_CTRL_ACE > PURE_STUFF > PURE_MOVEMENT > WILD_FIREBALLER > PURE_CONTROL > AVERAGE_4_5 > WILD_MID > JUNKBALLER > GENERIC_HR_PRONE > FILLER > LIABILITY > PIT_CHF) | HIGH if 2+ tiers, MED if 1 |
| `IL_RISK` | `rp3.is_on_il_at_split == True` OR `roster.injured == True` for this player | HIGH if current, MED if recently returned |
| `RECENCY_BAD` | `rp3.recency_form_gap < -2.5` (recent starts well below baseline projection) | HIGH |

#### RP alerts

| Code | Condition | Severity |
|---|---|---|
| `LOST_CLOSER` | `CLOSER` (2025) == True AND `CLOSER` (2026) == False | HIGH |
| `LEVERAGE_SLIDE` | `leverage_tier` dropped from `ELITE_LEVERAGE` / `HIGH_LEVERAGE` in 2025 to `MID_LEVERAGE` / `LOW_LEVERAGE` in 2026 (gmLI-driven role indicator) | HIGH |
| `TRENDING_DOWN` | `traj_flag == 'TRENDING_DOWN'` | MED |
| `VELO_DECLINE` | `VELO` (2026) − `VELO` (2025) ≤ −5 (5-point drop on the 20-80 scale ≈ 1+ mph) | MED |
| `USAGE_DROP` | `rprs2.rank` (2026) − `rprs2.rank` (2025) > 50 (model has demoted them by 50+ slots) | MED |

### Step 3 — severity rollup & deep-dive routing

Score each player with their highest-severity alert. If a player has 2+ alerts at the same tier, elevate one tier (e.g., MED + MED → HIGH, HIGH + HIGH → HIGH but bold).

**Per-HIGH deep-dive recommendation map:**

| Alert | Recommended next skill |
|---|---|
| `COLD_BABIP`, `COLD_xWOBA_L21d`, `RECENCY_BAD` (hitter) | `/slump-or-decline <name>` |
| `RECENCY_BAD` (SP) | `/sp-breakout-signal <name>` (rolling-window outcome check) + `/pitcher-sustainability <name>` |
| `ARCHETYPE_DOWNGRADE` (SP) | `/sp-archetype <name>` for comp-based forward outlook |
| `ARCHETYPE_DOWNGRADE` (hitter) | `/hitter-archetype <name>` |
| `LOST_CLOSER` / `LEVERAGE_SLIDE` | `/fa-pickup-deep-dive <emerging-closer-from-FA>` |
| `DROP_RISK` | `/fa-replacement-pool <name>` |
| `IL_RISK` (SP) | `/sp-rehab-tracker <name>` |
| `TRENDING_DOWN` (any) | `/sp-archetype` or `/hitter-archetype` for comp T+1/T+2 base rates |

### Step 4 — emit briefing

---

## Output format

```markdown
# Roster Health — Week N (YYYY-MM-DD)

Scanned R players (H hitters / S SPs / B RPs).
Found: X HIGH / Y MED / Z LOW alerts.

## HIGH-priority (action recommended this week)

### Player A (hitter) — TRENDING_DOWN + COLD_BABIP
- Archetype: GOAT_TIER (2025) → POWER_EYE (2026) — 1-tier downgrade
- OVERALL_slope_3yr: −4.2 (declining)
- BABIP: .256 vs career .302 (Δ −.046) — likely bounce
- L21d recency_form_gap: −3.1 (model says recent production lagging baseline)
- Suggested: `/slump-or-decline Player A`

### Player B (RP) — LOST_CLOSER
- 2025: CLOSER=True, 28 SV, leverage_tier ELITE_LEVERAGE (gmLI 1.64)
- 2026: CLOSER=False, 0 SV, leverage_tier MID_LEVERAGE (gmLI 0.94)
- rprs2 rank: 18 (2025) → 73 (2026), USAGE_DROP confirmed
- Suggested: `/fa-pickup-deep-dive <emerging-closer-from-FA>` then `/fa-replacement-pool`

### Player C (SP) — RECENCY_BAD + ARCHETYPE_DOWNGRADE
- Archetype: STUFF_PLUS_CTRL (2025) → AVERAGE_4_5 (2026) — 2-tier drop
- recency_form_gap: −3.4
- S/M/C: 72/55/64 → 58/52/58 (S dropped 14 points)
- Suggested: `/sp-archetype Player C` + `/sp-breakout-signal Player C`

## MED-priority (monitor; deep-dive if a roster move is needed)

- **Player D** (hitter) — COLD_xWOBA_L21d: recency gap −2.8, current production hot, model expects cooling. Hold for now.
- **Player E** (RP) — VELO_DECLINE: VELO 62 → 56 (−6). r_K still 58, leverage intact. Watch next 7 days.
- **Player F** (hitter) — ARCHETYPE_DOWNGRADE 1-tier (CONTACT_POWER → EYE_CONTACT). Power outage; xwOBACON trajectory check via `/slump-or-decline` if continues.

## LOW-priority (informational; counts + names only)

- AGE_TIER_TRANSITION (N=2): Player G (PEAK→POST_PEAK), Player H (PRE_PEAK→PEAK)
- Minor `traj_flag == 'STABLE_TRENDING'` movers (N=4): G, H, I, J

## Suggested next deep-dives this week

1. **Drop-add candidate:** Player A — `/slump-or-decline` + `/fa-replacement-pool` if structural
2. **Closer replacement:** Player B → run `/fa-pickup-deep-dive` on the top-2 FA save-getters
3. **Trade target:** Player C — sell-while-name-value-still-exists if `/sp-archetype` confirms 2-tier downgrade

---
Run `/roster-audit` next for slot/cap math; `/monday-morning` if you want all four (verify + audit + sp-week + fa-monitor) chained.
```

---

## Edge cases

- **In-progress (2026) ratings are sample-thin.** Players with <100 PA (hitters), <4 GS (SPs), <12 G (RPs) should have their alerts tagged `(sample-thin — N games)`. Don't suppress; just caveat.
- **Player not in ratings master.** A rookie called up in 2026 won't have a 2025 row. Skip the YoY-delta alerts (ARCHETYPE_DOWNGRADE, LOST_CLOSER, VELO_DECLINE, USAGE_DROP) and run only the current-state alerts (DROP_RISK, RECENCY_BAD, COLD_xWOBA_L21d, COLD_BABIP).
- **Player on IL.** Suppress DROP_RISK alerts (they aren't producing because they aren't playing). Keep IL_RISK, ARCHETYPE_DOWNGRADE, and TRENDING_DOWN since those describe the player not the slot.
- **Same-name collision** (Max Muncy LAD vs ATH): join ratings ↔ roster by `(_norm(player_name), team)` tuple. See `/player-id-resolve` and the `/monday-morning` collision-safe pattern.

---

## When NOT to use

- **You need slot/cap/eligibility math** → `/roster-audit` (counts IL slots, projects SP starts, computes positional gaps)
- **You need the full Monday workflow** → `/monday-morning` (chains roster-verify + roster-audit + sp-week-plan + fa-monitor)
- **One-player deep-dive question** → `/slump-or-decline`, `/sp-archetype`, `/hitter-archetype`, `/fa-pickup-deep-dive`
- **Mid-week IL transaction** → `/forced-drop-planner` (cap-breach date math)
- **League-wide scan across all 8 teams** → `/league-deep-audit`

---

## Integration map

| Skill | Relationship |
|---|---|
| `/roster-verify` | Pre-condition — mandatory before any "your player" labeling |
| `/roster-audit` | Sibling — slot/cap layer; this skill is signal layer. Run both Monday. |
| `/monday-morning` | Parent meta — should call this skill as its signal step (future refactor opportunity) |
| `/slump-or-decline` | Downstream — recommended for HIGH COLD_BABIP / RECENCY_BAD hitter alerts |
| `/sp-archetype` / `/hitter-archetype` | Downstream — recommended for ARCHETYPE_DOWNGRADE alerts (comp-based T+1 outlook) |
| `/fa-pickup-deep-dive` | Downstream — recommended for LOST_CLOSER / LEVERAGE_SLIDE alerts |
| `/fa-replacement-pool` | Downstream — recommended for DROP_RISK alerts |
| `/league-deep-audit` | Upstream/companion — full 8-team statistical audit; this skill is a focused-on-your-roster subset |

---

## Anti-patterns to avoid

1. **Using session memory for roster membership.** Always Step 0. The Weathers/Rasmussen incident (2026-05-25) was caused by this exact shortcut.
2. **Ranking RPs by `xfp_rp3`.** RPs use `xfp_rprs2`. The two models target different distributions; rp3 conflates roles.
3. **Treating COLD_BABIP as a sell signal.** It's a *bounce-coming* signal — informational, MED severity. Selling on a BABIP slump is exactly the inverse of optimal play.
4. **Surfacing `n_pos_flags` or "rolling trend" composite as a signal.** Validated noise (CLAUDE.md rule #3, feedback_rolling_trend_short_horizon_only.md). Ignore those columns even if they appear in the master files.
5. **Recommending `/slump-or-decline` for an IL'd player.** Playing-hurt mimics decline (Suárez 2026-05-27). Check IL gaps in the parquet game-log before issuing any drop verdict — that's why DROP_RISK is suppressed for IL'd players here.
6. **Issuing more than 5 HIGH alerts.** If everything is HIGH, nothing is. Re-tier or collapse to MED.


---

## Note (2026-06-03): new alert candidates

Once tier-aware thresholds settle, consider adding:
- `BOOM_STACK_HIGH` (SP at ace/sp2_sp3 tier, stack ≥ 2 today) — confirms a strong start
- `BOOM_STACK_LOW` (SP at backend/streamer tier with sustained stack=0) — drop signal
- `HIGH-K_ARM` (rostered SP with HIGH-K z ≥ +0.5, indicates real K-talent floor)

Currently these surface via `/triangulate` per-player and `/stream-the-stack`
daily; promote into this skill once a per-stack alert threshold is calibrated.

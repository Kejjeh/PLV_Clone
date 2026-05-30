# Hitter archetype — external (non-skill) signals scoping

**Date:** 2026-05-30
**Purpose:** Identify the hitter analog of the RP `gmLI` boost — an external context/usage signal that
distinguishes "production by role" from "production by skill" without being itself a skill metric.
**Goal:** Recommend the top 2-3 candidate signals to integrate into `build_hitter_archetypes.py` after
empirical YoY-stability and fantasy-ROI testing.
**Scope:** Research / proposal only. No build script changes. Compare model in style to `RP_DATA_AUDIT.md`.

---

## 1. Background — what gmLI gave the RP build

In `RP_DATA_AUDIT.md`, gmLI (FanGraphs game-entry leverage index) was flagged as the HIGH-impact missing
signal. It is **not a skill metric** — it is the average leverage at the moment the RP entered the game.
Adding it transformed the RP archetype labels from "stats only" (SV/HLD/GF ratios + rate skills) to
context-aware labels: HIGH-LEVERAGE FIREMAN, SETUP-BY-USAGE, CLOSER-BY-ROLE-NOT-SKILL,
LOW-LEVERAGE MOPUP-WITH-MOVEMENT, etc.

The properties that made gmLI valuable were:

1. **Stable enough YoY** — managers don't shuffle reliever leverage randomly; the same arm gets the
   same leverage band most of the year.
2. **Independent of skill** — a 60-grade swing-and-miss arm in low leverage is a real archetype
   (the mopup-with-stuff prospect); ignoring leverage merges them with the elite closers and
   destroys the interpretive distinction.
3. **Fantasy-decisive** — leverage directly translates to SV/HLD opportunities, which dominate
   RP scoring (5×SV + 2×HLD per the BrownU formula).

The hitter analog must hit all three: **YoY stable, skill-orthogonal, fantasy-decisive**.

---

## 2. Candidate signals considered (8 total)

| # | Signal | Captures | Skill-orthogonal? |
|---|---|---|---|
| 1 | **Lineup spot consistency** (mean spot, mode-share, top-5 share) | Role security; lineup-locked vs platoon/shuffled | Strongly orthogonal — managers anchor by reputation/team need, not by rate skill alone |
| 2 | **Lineup quality around them** (OBP in front, ISO behind) | Run-scoring + RBI opportunity environment | Pure team context |
| 3 | **Platoon usage** (% PAs vs. opposite-handed pitching; season start share) | PA-volume cap from L/R platoon | Skill-orthogonal (manager / team handed-mix decision) |
| 4 | **SB green-light** (SB attempts / times-on-base) | Real SB ceiling distinct from sprint speed | Skill-adjacent (sprint speed) but rate is manager-driven |
| 5 | **Park HR-leverage** (extended from pf_HR to runs-park-factor + handedness split) | Team environment for HR/R/RBI scoring | Pure context |
| 6 | **Defensive position scarcity** (where actually played, not eligible) | C/SS/2B premium discount | Pure context (lineup card, not skill) |
| 7 | **Batting order leverage index (bLI)** — pLI-equivalent at PA time, FanGraphs | Literal gmLI analog; clutch-spot exposure | Skill-orthogonal |
| 8 | **Sprint speed × steal-attempt rate** | Speed conversion — speed that is actually used | Hybrid (skill × usage) |

---

## 3. Per-candidate scoping

### 3.1 Lineup spot consistency

**Data source.** Already cached. `data/research/xfp_cache/hitter_lineup_appearances_{2018..2026}.parquet`
(48,824 rows in the 2025 file alone). Cols: `game_pk, batter, lineup_spot, started_game, pa_in_game, game_date, year`.

**Derived signals computed from this file:**
- `mean_lineup_spot` (PA-weighted)
- `top5_share` = fraction of PAs in spots 1-5
- `mode_share` = fraction of PAs at the most-frequent spot (consistency proxy)

**YoY stability (just measured here, 2018-2025, paired, 250+ PA both years, n=1,118):**

| Metric | YoY r |
|---|---|
| `mean_lineup_spot` | **0.682** |
| `top5_share` | **0.647** |
| `mode_share` | 0.439 |

All three clear the r >= 0.40 bar. `mean_lineup_spot` is the strongest.

**Fantasy ROI (paired y/y+1, 250+ PA both years, n=1,900):**

| Predictor (year y) | r vs. next-year FP/PA |
|---|---|
| `mean_lineup_spot` | **-0.349** (lower spot = more FP/PA next year) |
| `top5_share` | **+0.351** |
| `xwoba_per_pa` (baseline skill signal) | +0.418 |

Lineup spot is ~80% as predictive of next-year FP/PA as `xwoba_per_pa` itself — a remarkable
independent signal given it carries zero rate-skill information. Same-year `r` is even stronger
(-0.531 / +0.544), so during in-progress evaluation it is highly informative for current FP-rate context.

**Verdict.** **TOP RECOMMENDATION.** Free (data already on disk), strong YoY stability, large
fantasy ROI, captures "lineup-locked vs shuffled / platoon" — the hitter analog of gmLI's
"high-leverage vs mopup" distinction.

---

### 3.2 Lineup quality around them

**Data source.** Partially derivable from the same `hitter_lineup_appearances` parquet: for each
batter-game, identify the players hitting in the spot above (lineup feeder) and below (protection).
Skill ratings of those teammates come from `hitters_multiyr_2015_2026.csv` (xwoba_per_pa, obp_proxy,
iso) joined back.

There is an existing `data/outputs/lineup_protection.csv` (1,023 rows; bb_pct/iso/k_pct under
STRONG/AVG/WEAK protection buckets), but **it has no year column** — it's a one-shot snapshot.
Useful as a backfill but not as a year-stable feature; would need a panel rebuild.

**YoY stability.** Not directly tested here (would need to build the panel). Estimate: HIGH for
locked-in lineups (LAD/HOU/ATL) where the manager runs the same order, LOW for rebuilders. Net
estimate r ~ 0.35-0.45.

**Fantasy ROI.** Strong on counting stats (R, RBI) but largely *redundant* with `mean_lineup_spot`:
if you know a player hits 3rd-4th-5th, you already know there is a good OBP guy in front and a power
bat behind. Marginal lift over signal #1 is likely small (<0.05 r once spot is controlled).

**Verdict.** **SECOND-TIER.** Conceptually right but largely captured by signal #1. Defer to v2.

---

### 3.3 Platoon usage

**Data source.** Statcast PA-level data has `p_throws` on every PA; combined with batter handedness
(`hitter_handedness.csv` exists in `data/outputs/`) we get `pa_vs_opposite_hand_pct`. Season start
share is derivable from `hitter_lineup_appearances` (`starts / 162`).

**YoY stability (just tested for `season_start_share`, n=1,747, 60+ starts):**

| Metric | YoY r |
|---|---|
| `season_start_share` | **0.425** |

Clears r >= 0.40, but barely. Platoon roles can change mid-season (call-ups, injuries).

**Fantasy ROI.** Predicts FP/PA next year at r = +0.215 — meaningful but weaker than lineup spot. The
real fantasy value of platoon detection is **PA-volume capping**: a strict platoon player on a top
contender (Carroll/Thomas split, etc.) will look elite on a per-PA basis and rate skills will be
inflated, but their season FP ceiling is half what raw rh3 would suggest.

**Verdict.** **SECOND-TIER, complement to signal #1.** Add as a *volume-cap flag* (PLATOON_STRICT vs
PLATOON_HEAVY vs EVERYDAY) rather than a continuous feature. Cheap to derive but the archetype
interpretive value is narrower than #1.

---

### 3.4 SB green-light proxy

**Data source.** Statcast PA-level for SB attempts per times-on-base, combined with sprint_speed
from `hitters_multiyr_2015_2026.csv` (already a column). Trivial derivation.

**YoY stability.** Not directly tested. Manager-driven SB philosophy is famously sticky team-level
(Brewers / Phillies high, Astros / Yankees low historically); player-level should track team. Estimate
r ~ 0.50-0.60 within batter, but mostly captured by *team* fixed effect.

**Fantasy ROI.** SB is in the scoring formula (+1 SB, K is -1). For high-speed players this is the
difference between a 3-FP/game and a 4.5-FP/game profile. Important for the speed archetype layer
but **doesn't move the verdict on power hitters at all**.

**Verdict.** **NICHE — speed archetype only.** Already partially captured in current archetype build
via the `SB overlay` (per CLAUDE.md, SB is rated but excluded from main C/P/D archetype label).
Defer to v2; not the gmLI analog.

---

### 3.5 Extended park factor (runs + handedness split)

**Data source.** Current build uses `pf_HR` (single column). FanGraphs Guts! or BaseballSavant park
factors are public, year-by-year, with L/R splits.

**YoY stability.** Park factors are extremely stable (the park doesn't change). r ~ 0.85+. Within
park-year, splits are noisier — r ~ 0.55-0.70.

**Fantasy ROI.** Modest. We already capture HR via `pf_HR`. Run-scoring park factor is mostly
redundant with team-OPS context. Marginal lift estimated < 0.03 r.

**Verdict.** **MARGINAL.** Cheap but small payoff. Could be added with no ETL cost, but not a gmLI
analog. Defer.

---

### 3.6 Defensive position actually played

**Data source.** MLB Stats API / Statcast — `position` field on PA-level rows. ESPN gives
*eligibility* (where they can be slotted), but the actual fielding position is what determines
real-world PA pace (catchers get ~140 starts/year, DH/1B/corner OFs get 145-160).

**YoY stability.** HIGH for established position players (r ~ 0.80+), MEDIUM for multi-position
utility (r ~ 0.45). Could compute `mode_position` and `position_diversity_index`.

**Fantasy ROI.** Indirect — drives PA volume, which combined with FP/PA gives total FP. C and
multi-position utility players cap volume; corner OF and 1B/DH maximize it. Estimate r ~ 0.25
vs season total FP.

**Verdict.** **SECOND-TIER, volume layer.** Already implicit in PA totals so partly redundant. Worth
adding as a discrete tag (POSITION_C / POSITION_UTILITY / POSITION_FULLTIME) for archetype labeling,
not a continuous feature. Cheap.

---

### 3.7 Batting order leverage index (bLI)

**Data source.** FanGraphs publishes `pLI` (average leverage index when a player is at the plate)
on the batting leaderboard. Same scrape pattern as RP `gmLI`. Not in any local cache today.

**YoY stability.** Estimate r ~ 0.45-0.55 (managers play matchups but heart-of-order batters
consistently get more late-and-close exposure).

**Fantasy ROI.** Distinct from lineup spot — a 3-hole hitter on the Tigers (low team-OPS) accumulates
less leverage than a 6-hole hitter on the Dodgers (high team-OPS, deep lineup). Estimate r ~ 0.25
vs next-year FP/PA, but heavily correlated with signal #1.

**Verdict.** **THIRD-TIER.** This is the literal gmLI analog, but for hitters, **lineup spot
captures most of the leverage context for free** because the batting order is structurally fixed
1-9 (whereas RP leverage is fluid — managers choose when each arm enters). For hitters, the
lineup-spot signal dominates; pLI adds marginal incremental signal at the cost of a new FanGraphs
scrape. Defer to v2 unless signal #1 underperforms.

---

### 3.8 Sprint speed × steal-attempt rate

**Data source.** Both fields already in `hitters_multiyr_2015_2026.csv` (`sprint_speed`) and
derivable (SB attempts from PA-level statcast). Already exists in some form.

**YoY stability.** Sprint speed itself is r ~ 0.85 YoY. Attempt rate is r ~ 0.50.

**Fantasy ROI.** Same comment as #4: SB-bucket only. Already represented in current SB overlay.

**Verdict.** **REDUNDANT** with current SB overlay handling.

---

## 4. Top 3 recommendations (ranked)

### Rank 1 — Lineup spot consistency (signal #1)

**Why.** Data already on disk (eight years of per-game lineup parquet, 2018-2026). YoY stability
r=0.68 on mean spot (cleanest result in this audit). Next-year FP/PA correlation r=-0.35, ~80% as
predictive as the rate-skill baseline (`xwoba_per_pa`) — and crucially **orthogonal** to skill, so
the lift will compound rather than overlap.

**Archetype interpretive lift.**
- Labels gain a context modifier: `POWER_THUMPER_3-4-5_LOCKED` vs `POWER_THUMPER_LATE-ORDER_PLATOON`.
- Distinguishes a 30-grade-volume role player with elite per-PA rates (will not return rh3) from
  the lineup-locked everyday version of the same skill profile (will return rh3).
- Creates the "BAT-LOCK" tier flag (analog of CLOSER tier in RP) for hitters with mode_share >= 0.70
  in spots 1-5 across most starts.

**Scope estimate.** **1.5 days.**
- ~0.5 day: write `_build_hitter_lineup_panel.py` aggregator that produces a
  `hitter_lineup_panel_2015_2026.csv` analog with `(batter, year, mean_spot, top5_share, mode_share,
  primary_spot, lineup_consistency_grade_20_80)`. The 2015-2017 parquet files don't exist yet;
  either build them from raw statcast (PA-level has `home_team`/`away_team`/`inning_topbot`/
  `at_bat_number` to reconstruct order) or accept 2018-2026 coverage (still 8 years, comparable to
  RP archetype's 2018+ window).
- ~0.5 day: integrate into `build_hitter_archetypes.py` as a new `lineup_role` column block and
  add LINEUP-LOCKED / LINEUP-SHUFFLED / PLATOON tags.
- ~0.5 day: regenerate archetype-stickiness and decline-baseline JSON files with the new column;
  re-validate boundary retention rates.

**New tags / columns added:**
- `mean_lineup_spot`, `top5_share`, `mode_share` (continuous)
- `lineup_role_tag` ∈ {LINEUP_LOCKED_HEART, LINEUP_LOCKED_TOP, LINEUP_LOCKED_LATE, SHUFFLED, PLATOON}
- `lineup_consistency_grade_20_80` (within-year, comparable to other 20-80 ratings)

**Does it replace or augment?** **Augment.** Adds a new context column; no existing column removed.

---

### Rank 2 — Platoon usage / PA-volume cap (signal #3)

**Why.** YoY r=0.43 on season start share — clears the bar. Captures the *PA-volume ceiling* that
the lineup-spot signal does not (a player hitting 4th vs RHP only and benched vs LHP looks elite
per PA but caps at 450 PA). Combines naturally with #1 to define a single context tier.

**Scope estimate.** **1 day.**
- Derive `pa_vs_RHP_pct`, `pa_vs_LHP_pct`, `season_start_share` from statcast + lineup parquet.
- Add PLATOON_STRICT / PLATOON_HEAVY / EVERYDAY tag to the archetype `lineup_role_tag` from #1
  (merge into the same enum rather than a parallel column).

**New tags / columns added:**
- `season_start_share`, `pa_vs_opposite_hand_pct` (continuous)
- Merged into `lineup_role_tag` from signal #1

**Does it replace or augment?** **Augment** — extends signal #1's `lineup_role_tag`.

---

### Rank 3 — pLI (batting order leverage index, FanGraphs scrape)

**Why.** The literal gmLI analog. Distinct from lineup spot when team-OPS varies (a 3-hole Dodger
sees higher leverage than a 3-hole Pirate). Honest assessment: the marginal lift over signals #1+#2
is probably small for hitters because the batting-order structure does most of the leverage
allocation work for free.

**Scope estimate.** **2-3 days.**
- 1 day: FanGraphs leaderboard scrape (URL pattern parallel to RP gmLI scrape).
  Add `data/outputs/fangraphs_batter_leverage_{year}.csv` per year 2015-2026.
- 0.5 day: join + YoY stability validation. **Run `/validate-feature` (the 9-rule protocol)
  before promoting to a ranker.** Baseline must include signals #1 and #2 (Rule 9).
- 0.5 day: integration if validated.
- 0.5 day buffer for the FG ETL surprises (rate limiting, schema drift, mlb_id join coverage).

**Decision rule:** only ship #3 if validate-feature shows incremental r >= 0.03 vs (rh3 baseline + #1 + #2).
Otherwise defer indefinitely — the lineup-spot signal subsumes ~90% of what pLI adds for hitters,
unlike the RP case where gmLI was irreplaceable.

**New tags / columns added:**
- `pLI`, `bLI_relative_to_team` (continuous)
- `LEVERAGE_TIER` ∈ {HIGH, MID, LOW} (only if validated)

**Does it replace or augment?** **Augment.**

---

## 5. Comparison table

| Rank | Signal | Data on disk? | YoY r | Next-year FP/PA r | Skill-orthogonal? | Implementation | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | **Lineup spot consistency** | YES (`hitter_lineup_appearances_*.parquet`) | **0.68** | **-0.35** | Yes | **1.5 days** | **SHIP FIRST** |
| 2 | Lineup quality around batter | Partial (`lineup_protection.csv`, no year col) | ~0.40 (est) | weak | Yes | 2 days (rebuild panel) | Defer — redundant with #1 |
| 3 | Platoon usage | YES (derivable, statcast + handedness) | **0.43** | +0.22 | Yes | **1 day** | **SHIP WITH #1** |
| 4 | SB green-light | YES (statcast + sprint_speed) | ~0.55 (est) | speed-only | Hybrid | 0.5 day | Already in SB overlay |
| 5 | Extended park factor | YES (`pf_HR`, easy extend) | ~0.85 | low marginal | Yes | 0.5 day | Marginal, defer |
| 6 | Defensive position actually played | YES (statcast) | ~0.80 | +0.25 (volume) | Yes | 1 day | Volume tag, defer |
| 7 | **pLI (FanGraphs)** | NO (needs scrape) | ~0.50 (est) | ~0.25 (est) | Yes | **2-3 days** | Validate first; v2 |
| 8 | Sprint speed × SB attempts | YES | high | speed-only | Hybrid | redundant | Already covered |

---

## 6. Highest-priority single recommendation

If we ship one thing, ship **signal #1: lineup spot consistency**.

- The data is already on disk in eight pre-built parquet files (no ETL).
- YoY stability **r = 0.68** is the strongest signal in this audit — far above the r >= 0.40 bar
  and comparable to gmLI for RPs.
- Same-year correlation with FP/PA is **+0.54 / -0.53** (top5_share / mean_spot) — *higher*
  than the same-year correlation of `xwoba_per_pa` with FP/PA (which is what `xwoba_per_pa` is
  designed to track). It is the **single most fantasy-decisive context signal available**.
- Next-year predictive r=-0.35 is ~80% of the rate-skill baseline, and orthogonal — meaning
  it compounds rather than overlaps.
- 1.5 days of work, no new scrape, no new external dependency.

The hitter analog of `gmLI` for RPs is **lineup spot consistency**, not pLI. The batting order is
structurally fixed 1-9 every game, so the "leverage allocation" decision a manager makes is
**where in the order to place each hitter** rather than *when* to insert them. Lineup spot is
therefore the natural carrier of role/leverage information for hitters, the way bullpen entry
timing carries it for relievers.

Pair it with signal #2 (platoon usage) for the PA-volume cap that lineup spot alone misses, and
the archetype build has both the "role security" axis (lineup spot) and the "role ceiling" axis
(platoon usage) — a full context layer parallel to what gmLI + role tag gave the RP build.

---

## 7. Honest gaps and caveats

| Gap | Severity | Workaround |
|---|---|---|
| 2015-2017 lineup parquet doesn't exist locally | LOW | Either back-derive from raw statcast PA-level (we have `at_bat_number` + `inning_topbot`), or accept 2018-2026 coverage (still 8 years of data). |
| `lineup_protection.csv` has no year column | LOW | If pursuing signal #2, rebuild as a panel. |
| FanGraphs hitter leaderboard not currently cached | MEDIUM (blocks signal #7) | Build a `fangraphs_batters_leverage_{year}.csv` parallel to `fangraphs_rp_leverage_{year}.csv` if/when promoting pLI. |
| `season_start_share` divisor uses fixed 162 instead of actual team games played | LOW | Replace with per-team game count from MLB Stats API once integrated. |
| Mid-season lineup-spot drift not captured by full-season aggregate | MEDIUM | Mirror the SP rolling-cuts pattern (`rolling_hitters_*.csv`) with split_day buckets for in-season verdicts. Defer to v2. |

---

## 8. Specific filenames touched (if signal #1 + #2 ship)

Read-only sources:
1. `data/research/xfp_cache/hitter_lineup_appearances_{2018..2026}.parquet` — per-game lineup spot history
2. `data/research/xfp_cache/hitters_multiyr_2015_2026.csv` — for `pa`, batter join
3. `data/outputs/hitter_handedness.csv` — for platoon hand classification
4. `data/research/xfp_cache/statcast_{2018..2026}.parquet` — for `p_throws` per PA (platoon split)

New artifacts produced:
- `data/research/hitter_lineup_panel_2018_2026.csv` — `(batter, year, mean_spot, top5_share, mode_share,
  primary_spot, season_start_share, pa_vs_opposite_hand_pct, lineup_role_tag,
  lineup_consistency_grade_20_80)`
- Updated `data/research/sp_archetype_definitions.json`-equivalent for hitters with `lineup_role_tag` enum
- Updated stickiness/decline base-rate JSONs with the new column included

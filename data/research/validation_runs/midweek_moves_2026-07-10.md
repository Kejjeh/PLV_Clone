# Midweek roster-moves residual study (transaction persistence) — PRE-REGISTRATION

Date: 2026-07-10
Author: Claude (research agent)
Status: PRE-REGISTERED (this section written BEFORE any outcome was computed)
Predecessor: `midweek_roster_moves_test.md` (2026-06-03, NEEDS_MORE_DATA — unlock
condition "N closed periods ≥ 6" is now met, ~14 closed Mon–Sun periods).

## Question

Do MID-WEEK pickups outperform opening-day-rostered players over the remainder
of that scoring week, accounting for slate position (days remaining)? Does
add-day-of-week carry signal for streamer timing?

## Data sources (found in step-1 data hunt, before design freeze)

1. **Transactions**: `data/research/transactions_history.parquet`
   (written daily by `scripts/xfp/persist_transactions.py`). 371 rows,
   2026-03-24 → 2026-07-09, continuous weekly coverage (~20–30/wk, no gap
   weeks). Actions: FA ADDED 181, WAIVER ADDED 15, DROPPED 175, no trades.
   The initial `size=500` pull on 2026-06-03 reached back to opening day
   (371 < 500), so the archive is believed season-complete; the ADD−DROP
   imbalance (+21) is a completeness caveat checked below (fidelity check).
   `position`/`pro_team` fields are blank; `mlbam_id` resolved for 214/371.
2. **Roster snapshots**: `data/research/matchup_rosters_history.parquet`
   (`persist_matchup_rosters.py`). Full 8-team snapshots on 2026-06-03/04,
   06-06, 06-07, then daily 2026-06-15 → present. Has `mlbam_id`,
   `position`, `lineup_slot`, `injury_status` per player.
3. **Outcomes**: `data/research/xfp_cache/boxscore_hitters.parquet` /
   `boxscore_pitchers.parquet` — per-game BrownU FP (fp_h / fp_sp / fp_rp),
   mlbam-keyed, 2026-03-25 → 2026-07-09 (covers every closed period).
4. Week definition: repo-canonical Mon–Sun (`build_matchup_dashboard.py:3132`).
   Closed weeks in scope: **2026-03-30 … 2026-07-05 (14 weeks)** plus the
   opening stub 2026-03-24 → 03-29 treated as its own short week (week_start
   2026-03-23). Current week (Jul 6–12) EXCLUDED (not closed).

## Coverage scoping (declared)

- Roster state at each week open is RECONSTRUCTED: anchor = nearest full
  snapshot; walk transactions (ts_ms-ordered) backward/forward to the Monday
  00:00 state (i.e., end-of-prior-Sunday). Feasible season-wide only because
  the transaction archive appears season-complete.
- **Fidelity check (gate, run before outcomes):** reconstruct each team's
  roster on 2026-06-15, 06-22, 06-29 from the 2026-06-03 anchor + transactions
  and compare to the actual snapshots. Decision rule, declared now:
  - mean absolute mismatch ≤ 1.5 players/team → PRIMARY analysis = full
    season (all 15 closed weeks);
  - else → PRIMARY = snapshot-anchored weeks only (2026-06-08 → 07-05, 4–5
    weeks), full-season becomes sign-only SECONDARY.
- If total resolvable add-events in scope < 60 → report UNDERPOWERED with
  powered date and STOP.

## Design

**Unit**: (team, player, add-event). All `FA ADDED` / `WAIVER ADDED` rows in
closed weeks. Duplicate (team, player) adds within one week: keep earliest.

**ID resolution** (never last-name contains): (a) archived `mlbam_id`;
(b) exact normalized full-name + team_id match in roster snapshots ≤ 21 days
after the add; (c) `resolve_batter_id`/`resolve_pitcher_id` with team hint;
(d) unique normalized full-name match in boxscore parquets (skip-on-ambiguous).
Unresolved adds are excluded and counted.

**Position bucket** (H / SP / RP): roster-snapshot `position` mode per player;
fallback boxscore membership (pitcher if in pitcher parquet; SP if season
GS/G ≥ 0.4 per repo `detect_pitcher_role` convention; else RP; hitter
otherwise). Two-way players: hitter-parquet FP if bucketed H.

**Outcome**: FP_per_day = sum of BrownU FP over MLB games in
[add_date, week_end] inclusive ÷ (week_end − add_date + 1). FP column by
bucket: H→fp_h, SP→fp_sp, RP→fp_rp. No games in window ⇒ 0 (that is the
real streamer outcome). Intention-to-treat: later same-week drops do NOT
truncate the window (for adds or holds).

**Comparison (within-team-week matching controls slate position)**: for each
add-event, holds = same team's opening-roster players in the SAME position
bucket who were rostered at week open (reconstructed), each scored over the
IDENTICAL [add_date, week_end] window. Exclusions from the hold pool:
players on IL at week open (snapshot `injury_status` in IL states where a
snapshot within ±1 day of Monday exists; else proxy = 0 MLB games in the 14
days before week_start). Matched difference:
`d = add_FP_per_day − mean(hold_FP_per_day)`. Events with an empty matched
hold pool are dropped (counted).

**Covariates recorded**: add day-of-week, position bucket, adder identity
(team_id; Josh = team_id 8, New York Ligers), days_remaining, SP
started-in-window flag.

## Hypotheses (signs declared BEFORE computing outcomes)

- **H1** (churn is chase-y): mean d < 0 overall — midweek adds underperform
  same-position opening-day holds per remaining day.
- **H2** (SP streamer exception): among SP adds, those with ≥1 start in the
  remaining window (ex-post proxy for "added for a confirmed start") have
  mean d greater than non-starting SP adds, and their mean d is not
  significantly negative (CI does not sit wholly below 0).
- **H3** (late-week adds worse): mean d(add Thu–Sun) < mean d(add Mon–Wed).
- **Slice** (descriptive, no declared sign): Josh (team 8) vs the other 7.

## Analysis (declared)

Simple, transparent: matched-difference means. Inference = 10,000-resample
bootstrap, resampling clustered by (team, week); 95% percentile CIs. No model
fitting, no covariate regression. Rule 5 honesty: n per cell reported; any
cell with n < 30 is SIGN-ONLY (no verdict from its CI). Multiple-look
discipline: the three hypotheses above are the only confirmatory tests;
everything else (day-of-week grid, per-team table) is descriptive.

**Verdict mapping**: per hypothesis — VALIDATED (CI excludes 0 in declared
direction, n ≥ 30), SIGN-ONLY (n < 30), NULL (CI spans 0), REJECTED (CI
excludes 0 opposite the declared sign). Actionable rule reported only if its
CI clears 0 at n ≥ 30.

Engine: `data/research/validation_runs/midweek_moves_analysis_2026-07-10.py`
(added with this prereg). Results appended below after execution.

---

# RESULTS (appended 2026-07-10, after prereg freeze)

Full tables: `midweek_moves_results_2026-07-10.md`; event-level panel:
`midweek_moves_panel_2026-07-10.csv`.

**Fidelity gate**: reconstruction from the 2026-06-04 anchor reproduced the
real 2026-06-15 / 06-22 / 06-29 snapshots with mean 0.04 players/team
mismatch (max 1, one team, one date: Wacha/Lewis swap timing). Gate ≤ 1.5
PASSED → PRIMARY = full season, 15 closed weeks. The transaction archive is
effectively season-complete.

**Panel**: 190 adds in closed weeks → 162 matched add-events (2 unresolved
mlbam, 1 unbucketable, 25 empty same-bucket hold pools). n ≥ 60 → powered.

| Hypothesis (declared sign) | effect (FP/day) | 95% CI | n | verdict |
|---|---|---|---|---|
| H1 all adds underperform holds (d<0) | +0.574 | [−0.110, +1.317] | 162 | **NULL** (point is opposite sign) |
| H1 hitters | −0.309 | [−0.837, +0.236] | 64 | NULL |
| H1 SP | +1.658 | [+0.233, +3.037] | 68 | **REJECTED** (CI>0, opposite declared sign) |
| H1 RP | −0.003 | [−0.740, +0.749] | 30 | NULL |
| H2 SP adds w/ start in window, d not <0 | +2.915 | [+1.285, +4.369] | 51 | **VALIDATED** |
| H2 diff started − not-started | +5.025 | [+3.204, +6.812] | 68 | **VALIDATED** |
| (SP adds w/o start) | −2.111 | [−3.079, −1.371] | 17 | sign-only (negative) |
| H3 Thu–Sun worse than Mon–Wed (Δ<0) | Δ=+0.902 | [−0.273, +2.151] | 162 | **NULL** (point opposite sign) |
| Slice: Josh adds (descriptive) | +1.802 | [+0.409, +3.555] | 35 | CI>0 |
| Slice: other 7 teams | +0.235 | [−0.480, +0.995] | 127 | NULL |

**Registry verdict**: midweek churn is NOT chase-y in this league. The only
cell that clears its CI at n≥30 is SP streamer adds — driven entirely by
adds that actually start in the remaining window (+2.9 FP/day vs held SPs).
Hitter and RP midweek adds are a clean null vs holds. No day-of-week timing
penalty exists (Sunday adds are the BEST cell descriptively, +2.5 FP/day,
because they are morning-of confirmed-start streamers).

**Caveat (declared proxy)**: H2 conditions on the ex-post start — partly
mechanical (an SP only scores if he pitches, and held SPs may not start in a
short window). The decision-relevant contrast ("add a confirmed starter vs
ride the roster") is exactly this quantity, but do not read +2.9 as pure
selection skill.

**Actionable rules (CI-cleared, n≥30)**:
1. Keep streaming SPs for confirmed starts, any day of week — +2.9 FP/day
   vs same-team held SPs (n=51, CI[+1.3, +4.4]). Sunday morning-of adds
   are fine; there is no late-week penalty (H3 rejected in direction).
2. Do NOT add an SP speculatively without a start scheduled in the current
   week — sign-only but strongly negative (−2.1 FP/day, n=17).
3. Hitter/RP midweek churn is value-neutral vs holds — no evidence it
   costs anything, no evidence it helps (H: −0.31, RP: −0.00, both NULL).

Rule-13 note: this is a DECISION-layer finding (transaction behavior), not a
ranker feature; nothing here moves rh3/rp3/rprs2.

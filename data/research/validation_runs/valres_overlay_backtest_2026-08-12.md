# Study C results — IL-return volume overlay backtest (run 2026-08-14)

Registered: `prereg_availability_suite_2026-08-12.md` (Study C — the load-bearing
gate). Contract: REALISTIC overlay must (a) cut median |error| >= 20% vs the
pace-forward baseline AND (b) improve Spearman(predicted, realized RoS PA)
within the IL cohort. Both required.

## GATE VERDICT: **FAIL**

| Gate leg | Requirement | Result | Pass? |
|---|---|---|---|
| (a) median \|error\| | cut >= 20% vs baseline | **−83.8%** (WORSENS: 43.38 → 79.73 PA) | **NO** |
| (b) Spearman | improve vs baseline | 0.3837 → 0.4289 (+0.045) | yes |

Per registration: **overlay does NOT ship. It stays a manual diagnostic; boards
keep pace-forward** for IL'd/returning players. No threshold shopping, no
partial credit.

## Score table (pooled cohort, n = 683 player-asof rows, 333 distinct players)

| Variant | median \|err\| (PA) | mean \|err\| (PA) | Spearman | median signed err | mean signed err |
|---|---|---|---|---|---|
| baseline (pace_forward) | **43.38** | 54.37 | 0.3837 | +7.9 | +9.1 |
| overlay ORACLE (actual return) | 32.28 | 50.78 | **0.6835** | +31.9 | +48.9 |
| overlay REALISTIC (est. return) | 79.73 | 88.41 | 0.4289 | +79.7 | +83.7 |

### By as-of date

| Cell | n | base med\|e\| | real med\|e\| | base rho | real rho |
|---|---|---|---|---|---|
| Jul 15 | 252 | 52.41 | 111.65 | 0.316 | 0.461 |
| Aug 1 | 227 | 45.13 | 75.59 | 0.376 | 0.390 |
| Aug 15 | 204 | 31.25 | 59.59 | 0.416 | 0.260 |

### By season

| Season | n | base med\|e\| | real med\|e\| | base rho | real rho |
|---|---|---|---|---|---|
| 2021 | 175 | 43.72 | 86.88 | 0.465 | 0.492 |
| 2022 | 126 | 48.87 | 71.12 | 0.328 | 0.446 |
| 2023 | 119 | 43.26 | 74.90 | 0.411 | 0.540 |
| 2024 | 125 | 40.57 | 84.49 | 0.248 | 0.319 |
| 2025 | 138 | 41.89 | 92.69 | 0.343 | 0.253 |

Median |error| is worse for the realistic overlay in **5/5 seasons and 3/3
as-of dates**. Spearman is better in 4/5 seasons (2025 worse) and 2/3 as-of
dates (Aug 15 worse).

## Why it fails (mechanism, from the diagnostics)

1. **The realistic return-date estimate is structurally too optimistic for this
   cohort.** 37.5% of cohort rows were already PAST placement + min-stint + 10d
   at the as-of date (estimate clamped to as-of + 1) — by construction, players
   still on IL at a mid-summer snapshot are disproportionately the slow healers,
   so "minimum stint + 10 days" predicts near-full remaining playing time for
   players who often return weeks later (or barely play). Median signed error
   +79.7 PA.
2. **Even the ORACLE over-predicts on level** (median signed +31.9): when-active
   rate × ALL post-return team games assumes full-time play after return;
   returning players routinely ease back part-time or re-injure (canonical in-
   cohort example: Garrett Mitchell 2023 Aug-1 row — oracle/realistic assume
   full slates, realized 11 PA).
3. **The rank signal in the overlay is real** — oracle Spearman 0.68 vs baseline
   0.38 — but the gate is on the REALISTIC variant, and its date estimate both
   inflates the level and (at later as-of dates) scrambles the ordering.
4. Baseline pace_forward, for the RETURNED cohort, is roughly level-calibrated
   at the median (+7.9) — its known failure is rank resolution (rho 0.38) and
   the 15 rows with 0 season PA (pred 0 for genuinely returning players, e.g.
   Trevor Story 2023).

**Exploratory, NOT shipped (Rule 8):** the oracle gap says a better overlay
would need (i) a real return-date estimate (e.g., ESPN/rehab-informed, not
min-stint arithmetic) and (ii) a post-return playing-time discount. Any such
construction requires its own registration before it can gate.

## Method (documented decisions)

- **Transactions:** MLB Stats API `/api/v1/transactions`, sportId=1, monthly
  windows Feb 1 – Oct 31 per season 2021-2025; typeCode `SC` only. Placements =
  "placed … injured list" (12,435 raw IL-related SC rows kept). Activations =
  "activated"/"reinstated" that either name an injured/disabled list **or name
  no list at all** — plain "TEAM activated PLAYER." is the dominant IL-exit
  phrasing (2,960 of 6,832) and omitting it was caught in the sample pass;
  activations naming paternity / bereavement / restricted / reserve lists are
  NOT IL exits and are ignored.
- **Dates:** `effectiveDate` (falls back to `date`) for both placements and
  activations — captures retroactive IL dating.
- **Hitters:** people-API `primaryPosition.type != 'Pitcher'` (694 of 1,708 IL
  players; Ohtani TWP kept as hitter). 1,874 hitter stints built.
- **Stints:** placements paired with next qualifying activation per
  player-season; "transferred to the 60-day IL" upgrades the stint's minimum to
  60 (from the ORIGINAL placement date); unlabeled/COVID placements default to
  the 10-day position-player minimum; labels honored as written (7/10/15/60).
- **On IL at as-of:** placement_eff <= as-of AND (no activation OR
  activation_eff > as-of) AND **game-evidence closure** — any MLB regular-season
  game in (placement_eff, as-of] disqualifies the stint (catches residual missed
  activations; removed 117 candidate rows). Latest spanning stint per player.
- **Cohort filter:** realized >= 1 PA after as-of that season (per prereg);
  as-of dates Jul 15 / Aug 1 / Aug 15, 2021-2025 (15 cells).
- **PA truth:** statcast parquets, `game_type == 'R'`; PA = distinct (game_pk,
  at_bat_number) per batter. To-date = game_date <= as-of; realized RoS =
  game_date > as-of.
- **Team & team games:** batter team from statcast inning_topbot (Top → away
  team); player's team at as-of = team of most recent game on/before as-of, else
  the IL transaction's team (id → statcast abbr map; OAK→ATH patch). Team games
  counted as **distinct game_pk per team** (refinement of the registered
  "distinct game dates" so doubleheaders count as 2; documented here). Known
  cache gap: 2024 Seoul series (2 LAD/SD games) absent → those two teams' 2024
  game counts are as-cached.
- **Baseline:** (season PA to date / team games to date) × remaining team games.
- **Oracle:** when-active rate × team games on/after ACTUAL return (first game
  with a PA after as-of, inclusive).
- **Realistic:** when-active rate × team games on/after est. return =
  placement_eff + min stint + 10d, clamped early to as-of + 1 (prediction target
  starts at as-of; 37.5% of rows clamped), 0 games if past the team's last game
  (0 rows in final cohort). No knowledge of actual return used.
- **When-active rate:** PA to date / player games to date; if 0 games to date,
  prior-season (season − 1) rate when prior games >= 30 (used for 15 rows).
- **Exclusions (counted per prereg):** 7 rows dropped (0 games to date AND no
  qualifying prior season); 0 rows dropped for unresolvable team.
- **Scoring:** median/mean |error| and Spearman within the pooled cohort
  (primary, gated); per-as-of and per-season breakdowns reported above.

## Files

- Row-level results: `data/research/validation_runs/valres_overlay_backtest_2026-08-12.csv`
  (683 rows; one per player-asof: stint fields, rate + source, team-game counts,
  all three predictions, realized PA, absolute errors).
- Pipeline (scratchpad, session-local): `fetch_il_transactions.py`,
  `build_pa_tables.py`, `run_study_c.py`.

Run by Claude (Fable 5) subagent at Josh's direction, 2026-08-14. Gates judged
exactly as registered on 2026-08-12; no gate revised after results.

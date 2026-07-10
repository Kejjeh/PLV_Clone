# Midweek roster-moves study — result tables (2026-07-10)

Prereg + verdicts: `midweek_moves_2026-07-10.md`. Engine:
`midweek_moves_analysis_2026-07-10.py`. Panel:
`midweek_moves_panel_2026-07-10.csv` (162 matched add-events).

Design recap: unit = (team, player, add-event); outcome = BrownU FP per
remaining day [add_date → Sunday]; comparison = same-team, same-position-
bucket opening-Monday holds over the IDENTICAL window (controls slate
position); inference = 10k bootstrap clustered by (team, week); no models.

## Data source and coverage

- `data/research/transactions_history.parquet` (daily archival by
  `persist_transactions.py`): 371 rows, 2026-03-24 → 2026-07-09,
  season-complete (initial size=500 pull reached opening day; verified by
  the fidelity check below). 196 adds total; 190 in closed weeks
  (Mar 24 → Jul 5, 15 closed Mon–Sun periods incl. opening stub).
- Roster state: `matchup_rosters_history.parquet` snapshots + transaction
  walk. Fidelity: reconstruction from the 2026-06-04 anchor vs real
  snapshots on Jun 15/22/29 = **mean 0.04 players/team mismatch (max 1)**.
- Outcomes: `xfp_cache/boxscore_{hitters,pitchers}.parquet` per-game FP
  (fp_h / fp_sp / fp_rp), mlbam-joined; IDs resolved via archived mlbam →
  snapshot name+team → repo resolvers → unique-name boxscore match
  (skip-on-ambiguous; never last-name contains). 2/190 unresolved.

## Confirmatory results (d = add FP/day − matched-hold FP/day)

| Cell | n | d (FP/day) | 95% CI | tag |
|---|---|---|---|---|
| ALL adds | 162 | +0.574 | [−0.110, +1.317] | NULL |
| Hitters | 64 | −0.309 | [−0.837, +0.236] | NULL |
| SP | 68 | +1.658 | [+0.233, +3.037] | CI>0 |
| RP | 30 | −0.003 | [−0.740, +0.749] | NULL |
| SP w/ start in window | 51 | +2.915 | [+1.285, +4.369] | CI>0 |
| SP w/o start in window | 17 | −2.111 | [−3.079, −1.371] | sign-only |
| SP diff (started − not) | 68 | Δ +5.025 | [+3.204, +6.812] | CI>0 |
| Mon–Wed adds | 67 | +0.045 | [−0.331, +0.428] | NULL |
| Thu–Sun adds | 95 | +0.947 | [−0.172, +2.175] | NULL |
| H3 diff (late − early) | 162 | Δ +0.902 | [−0.273, +2.151] | NULL |
| Josh (New York Ligers) | 35 | +1.802 | [+0.409, +3.555] | CI>0 |
| Other 7 teams | 127 | +0.235 | [−0.480, +0.995] | NULL |
| Snapshot-era only (≥ Jun 8) | 46 | +0.896 | [−0.488, +2.423] | NULL (robustness) |

Hypothesis verdicts: **H1 NULL/REJECTED** (adds do not underperform holds;
SP bucket significantly the OPPOSITE), **H2 VALIDATED** (confirmed-start SP
streamers are the driver, +2.9 FP/day, diff vs non-starting SP adds +5.0
with CI far from 0), **H3 NULL** (no late-week penalty; point estimate is
late-week BETTER, carried by Sunday confirmed-start streamers).

## Descriptive: day-of-week grid (mean d, n; NOT confirmatory)

| dow | n | mean d | add FP/day | hold FP/day |
|---|---|---|---|---|
| Mon | 25 | +0.143 | 1.941 | 1.798 |
| Tue | 26 | +0.045 | 1.922 | 1.877 |
| Wed | 16 | −0.109 | 1.695 | 1.804 |
| Thu | 20 | −0.321 | 1.429 | 1.750 |
| Fri | 22 | +0.924 | 2.539 | 1.616 |
| Sat | 21 | −0.252 | 1.669 | 1.921 |
| Sun | 32 | +2.541 | 4.581 | 2.041 |

## Descriptive: bucket × timing (mean d / n)

| bucket | Mon–Wed | Thu–Sun |
|---|---|---|
| H | +0.116 / 30 | −0.683 / 34 |
| RP | +0.359 / 14 | −0.319 / 16 |
| SP | −0.239 / 23 | +2.628 / 45 |

Late-week hitter adds trend negative (−0.68, n=34, does not clear CI) while
late-week SP adds are strongly positive — the late-week edge is a pure
confirmed-start-streamer phenomenon, not a general churn edge.

## Descriptive: per-team (mean d / n)

| team | n | mean d |
|---|---|---|
| Team Solomon | 23 | −0.757 |
| U Just Lost To Edwin Diaz | 25 | −0.703 |
| Treasure Island Mashers | 5 | −0.662 |
| Frendy's Fantastic Team | 24 | −0.247 |
| 2015 Draft First Round | 13 | −0.187 |
| Late Night Bettsing | 19 | +1.481 |
| New York Ligers (Josh) | 35 | +1.802 |
| Boone's Bad Bullpen | 18 | +2.687 |

Josh's adds clear their CI (+1.80, [+0.41, +3.56], n=35) — his churn has
been positive-EV, consistent with an SP-streamer-heavy add mix.

## Caveats (honesty)

- H2's "started in window" is ex-post: partly mechanical (only pitching
  scores). It IS the decision-relevant contrast for streaming, but don't
  read +2.9 as pure selection skill.
- Intention-to-treat: later same-week drops don't truncate windows.
- Hold pools exclude IL (snapshot-based from Jun; 14-day-inactivity proxy
  before Jun) — proxy weeks could retain a few phantom-inactive holds.
- 25 events dropped for empty same-bucket hold pools (mostly RP adds on
  teams carrying 0-1 healthy RP holds); 21 add/drop archive imbalance is
  consistent with open-slot adds, and the fidelity check bounds any
  missing-transaction error at ~0.04 players/team.
- Confirmatory tests were only H1/H2/H3 as preregistered; everything else
  here is descriptive.

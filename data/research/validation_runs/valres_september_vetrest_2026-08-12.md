# Study A results — September veteran-rest effect (prereg 2026-08-12)

**Verdict: KILL — gate fails on all three conditions. No September availability
multiplier ships.**

Registered in `prereg_availability_suite_2026-08-12.md` (Study A). Executed
2026-08-14 by background agent. Data rows:
`valres_september_vetrest_2026-08-12.csv` (368 veteran player-seasons,
2021-2025; gray-zone rows included, flagged EXCLUDED).

## Headline result

| Quantity | Value | Gate requirement | Pass? |
|---|---|---|---|
| Effect = mean Δ(elim) − mean Δ(cont) | **−0.051 PA/tg** | ≤ −0.25 PA/tg | **NO** |
| 95% player-clustered bootstrap CI (1000 reps, seed 42) | **(−0.294, +0.184)** | excludes 0 | **NO** |
| Seasons with negative sign | **2 of 5** (2021, 2022) | ≥ 4 of 5 | **NO** |

Mean Δ (Sep PA/tg − Aug PA/tg): ELIMINATED −0.371, CONTENDER −0.320. Both
cohorts lose ~1/3 PA per team game in September (roster expansion + rest is
league-wide); the eliminated-vs-contender *contrast* — the registered effect —
is small, unstable in sign, and statistically indistinguishable from zero.

## Per-season signs

| Season | n elim | n cont | Δ elim | Δ cont | Effect | Sign |
|---|---|---|---|---|---|---|
| 2021 | 17 | 54 | −0.390 | −0.264 | **−0.126** | NEG |
| 2022 | 30 | 42 | −0.508 | −0.288 | **−0.220** | NEG |
| 2023 | 13 | 42 | −0.378 | −0.457 | **+0.079** | POS |
| 2024 |  5 | 49 | +0.162 | −0.260 | **+0.422** | POS |
| 2025 |  8 | 62 | −0.139 | −0.345 | **+0.206** | POS |

Pooled: 73 ELIMINATED / 249 CONTENDER player-seasons (167 unique players
clustered), 46 gray-zone rows excluded per registration.

## Method (as executed)

- **PA counting.** `statcast_{2021..2025}.parquet`, `game_type=='R'` only;
  PA = distinct `(game_pk, at_bat_number)` where `events` is non-null/non-empty,
  attributed to `batter`.
- **Windows.** Aug = Aug 1–31. Sep = **Sep 1 through end of regular season**
  (includes the early-Oct regular-season tail in 2021/2022/2023; `game_type=='R'`
  bounds it). Chosen before results were computed, since the Sep-1 team context
  applies to all remaining games; documented here as the operationalization of
  "September" in the registration.
- **Team resolution (documented per registration).** Batting team per PA =
  `away_team` if `inning_topbot=='Top'` else `home_team`; player's team per
  month = modal team over that month's PA rows. Classification team = September
  modal team, falling back to August modal team when a player logged no Sep PA.
  No MLB gameLog API fallback was needed — every cohort row resolved.
- **Team-game denominators.** Distinct regular-season `game_pk` per team
  (home or away) within each window, from the same parquet. Sanity: 2,425-2,430
  games/season; Aug team games 25-30; Sep-window team games 24-34 (2022 high
  end reflects the lockout-shifted Oct 5 season end).
- **Abbreviation normalization.** Savant retroactively labels the Athletics
  `ATH` in all seasons; MLB API says `OAK` through 2024 → normalized API side
  to `ATH` (team id 133). All 5 seasons matched 30/30 after this.
- **Age.** MLB people API `birthDate` (chunked `personIds` calls) for the
  ≥350-PA-through-Aug-31 candidates only; veteran = age ≥ 30 as of Sep 1
  (calendar age, floor). Cohort: 350+ PA through Aug 31 per registration.
- **Sep-1 standings context.** `/api/v1/standings?leagueId=103,104&season=Y&date=Y-09-01`.
  Last playoff spot: **2021 format = 10 teams (2 WC/league); 2022+ = 12 teams
  (3 WC/league)**. Division leaders = `divisionRank=='1'`; non-leaders ranked by
  winning pct (ties by wins) within league; last spot = Nth wild card (N=2 in
  2021, N=3 in 2022+). GB of last spot via standard formula
  `((W_wc − W_t) + (L_t − L_wc)) / 2` vs that team. HOLDING (leader or top-N WC)
  or GB ≤ 5.0 → CONTENDER; GB ≥ 10.0 → ELIMINATED; in between → EXCLUDED.
  Season eliminated-team lists spot-checked against history (2021
  AZ/COL/DET/KC/MIA/MIN/PIT; 2024 only COL/CWS/LAA/PIT — correct, few teams
  were ≥10 out by Sep 1 2024).
- **Effect + CI.** Pooled across seasons; player-clustered bootstrap = resample
  the 167 unique players with replacement (a player's rows across seasons move
  together), 1000 reps, `numpy default_rng(42)`, percentile CI.

## Interpretation + caveats (exploratory, non-gating)

- The hypothesized mechanism is real only in 2021-2022; 2023-2025 actually show
  eliminated-team vets holding PA *better* than contender vets. Post-2022 the
  12-team format leaves fewer truly buried teams by Sep 1 (n_elim 13/5/8), and
  contenders increasingly rest veterans for the postseason (the 2023-2025
  CONTENDER Δ ≈ −0.26 to −0.46 includes late-September lineup rest +
  playoff-lock coasting), which erases the contrast.
- Injury shutdowns contaminate both cohorts symmetrically (Votto 2022 elim;
  Seager/Semien 2025 cont) — no injury filter was registered, none applied.
- 2024 ELIMINATED n=5 makes that season's +0.422 noisy, but the gate counts
  signs, and 2023/2025 are positive too — the sign test fails regardless.
- Per registration: **no partial credit, no threshold shopping.** Anything
  above is exploratory context and cannot ship without its own registration.

**Decision: KILL. Period-22/23 projections keep the current volume
construction for eliminated-team veterans (no September multiplier).**

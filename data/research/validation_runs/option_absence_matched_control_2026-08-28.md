---
signal: option_absence_break (OPTION as a new event type in the regime-break taxonomy)
formula: split a pitcher-season at the first MLB appearance after a >=14-day appearance gap that contains an "Optioned" transaction (MLB Stats API /v1/transactions, typeDesc Optioned/Recalled); statistic = |dK-BB%| across the split minus the mean |dK-BB%| of 30 matched random splits at the same fractional season position for the same pitcher, both sides gated at 100 TBF + 3 GS
outcome: excess |dK-BB%| over matched controls (does the option stint break the line more than a random split at the same time of year)
expected_sign: + (issue #52 mechanism: an option is a deliberate organisational intervention, unlike an IL interruption)
bar: one-sided z > 1.83 on the paired per-pitcher-season excess — the GIVEN-split bar (the option supplies the split point; one test, M=1), NOT the searched bar of 2.58
production_target: none — this is the issue #52 step-2 gate BEFORE any feature work
framing: event taxonomy extension of analyze_break_events.py (v4 of sp_regime_break_finding_2026-08-26.md)
validation_script: scripts/_oneoff/option_absence_matched_control.py (seed 20260827, same as v4)
substrate: data/research/xfp_cache/sp_event_panel_2017_2026.csv (35,849 appearances, >=12 GS cohort, 1,331 pitcher-seasons) + data/research/xfp_cache/option_transactions_cache_2017_2026.json (349 pitchers fetched, 0.2s throttle)
date: 2026-08-28
verdict: DOES NOT CLEAR
---

# OPTION absences vs matched controls — issue #52 steps 1-2

## Hypothesis (from issue #52)

rp3 models IL absences but not minor-league option stints. The issue argued the
option may be the MORE informative absence because it is an intervention (the
org sends a pitcher down to change something — canonical: Jacob Lopez 2026,
2.75 FP/start pre-option -> 14.76 post-recall). Every event type v4 tested
(IL_SHORT/MED/LONG, TRADE, ROLE_ROT, ROLE_PEN) showed ~0 excess |dK-BB%| over
matched controls, but OPTION was never among them because the panel had no
transaction data. This run closes that gap BEFORE any feature is written.

## Method

1. **Event panel extension.** For the 349 pitchers whose eligible (>=12 GS)
   seasons contain a >=14-day appearance gap, fetched
   `GET /api/v1/transactions?playerId={id}&startDate=2017-01-01&endDate=2026-12-31`
   (one call per pitcher, 0.2s sleep, cached to
   `option_transactions_cache_2017_2026.json`). An OPTION event = a gap between
   consecutive MLB appearances >= 14 days containing an "Optioned" transaction;
   event/split date = first appearance after the gap (v4's `classify()`
   convention). Recall dates recorded (typeDesc "Recalled", typeCode CU).
2. **Matched-control test.** Verbatim `analyze_break_events.py` machinery:
   both sides >= 100 TBF (`stabilization.SP_MINS['k_pct']`) and >= 3 GS;
   30 control splits drawn at the same fractional season position
   (normal(frac, 0.05) clipped to [.05,.95]); paired excess averaged to ONE ROW
   PER PITCHER-SEASON before the t — pooled n is shown next to season n
   throughout (the 509-records-from-14-pitchers lesson).
3. **Significance.** Paired t (=z) vs the given-split bar 1.83, plus a
   sign-flip permutation (B=200,000). Guaranteed-null trap asserted:
   1/(B+1) = 5.0e-6 < alpha = 0.0336 (one-sided p at z=1.83, one test).

## Event panel (deliverable 1)

`data/research/xfp_cache/sp_option_events_2017_2026.csv` — **176 OPTION events,
116 distinct pitchers**, with optioned/recalled transaction dates and gap length.

| year | 2017 | 2018 | 2019 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|
| events | 23 | 21 | 20 | 14 | 25 | 20 | 16 | 31 | 6 |
| admissible (100 TBF + 3 GS/side) | 12 | 8 | 11 | 8 | 12 | 12 | 5 | 10 | 2 |

Base-rate honesty: 2026 yields only 6 events / **2 admissible** (Lopez 682052
and 691725) — the issue's "3 of 19 long-gap pitchers" expectation was right, and
the season is not over (Painter's post-recall side has not reached 100 TBF).
The 2017-2026 extension is what makes the test powered at all.

**Taxonomy contamination found in passing:** v4's gap-based classifier had been
calling these option gaps IL_SHORT (112), IL_MED (50), IL_LONG (6) — its "IL"
bins were IL+option mixtures. With options now separated and also null, both
readings stand.

## Result (deliverable 2)

80 admissible events over **66 pitcher-seasons** (96 events failed the
100-TBF/3-GS gate):

| event | n events | seasons | \|dK-BB%\| | control | **excess** | t (=z) |
|---|---|---|---|---|---|---|
| **OPTION** | 80 | 66 | 5.34 | 5.26 | **+0.08** | **0.82** |

- Per-season excess: **+0.097pp, SE 0.119pp, n=66** -> z = **0.82** vs bar 1.83.
- Sign-flip permutation p (one-sided, B=200,000, floor 5.0e-6 < 0.0336): **0.211**.
- Secondary |dFP/start| excess: +0.01 (t=0.23).
- **Powered null, not a thin one:** SE 0.119pp means an excess of ~0.22pp
  (z=1.83) would have been detected — that is 4% of the 5.3pp baseline shift.
  n=66 seasons sits between v4's IL_LONG (37) and ROLE_PEN (75) and behaves
  like every one of them (v4 range: −0.07 to +0.14pp).

### The Lopez row, specifically

| pitcher | split | pre K-BB% | post K-BB% | \|d\| | matched control | excess |
|---|---|---|---|---|---|---|
| Jacob Lopez 2026 | 2026-07-07 (37d option) | 2.1 | 21.6 | **19.53** | 19.23 | **+0.30** |

His break is enormous and real in magnitude — and a random split at the same
fractional position of his season shows 19.2pp. The option DATE carries almost
no information beyond its calendar position, exactly the v4 pattern for IL
returns ("the apparent break is explained by where in the season it happens,
not by the stint"). Same design note as v4: for long absences the matched
control often lands inside the gap itself, so this test asks whether the event
date adds information beyond its position — the identical question every IL/
TRADE/ROLE event was judged on, so the comparison is apples-to-apples.

### Per player-season table (all 80 admissible events; excess in pp K-BB%)

| pitcher | year | event date | gap | preTBF | postTBF | pre K-BB% | post K-BB% | \|d\| | ctrl | excess |
|---|---|---|---|---|---|---|---|---|---|---|
| 502043 | 2017 | 2017-05-22 | 18 | 129 | 564 | 2.3 | 10.3 | 7.96 | 8.01 | -0.05 |
| 502043 | 2017 | 2017-08-05 | 14 | 432 | 261 | 3.9 | 16.9 | 12.92 | 12.83 | +0.10 |
| 543045 | 2017 | 2017-07-18 | 71 | 134 | 329 | 5.2 | 7.0 | 1.77 | 1.79 | -0.02 |
| 571510 | 2017 | 2017-07-18 | 48 | 257 | 348 | 5.1 | 12.6 | 7.59 | 7.14 | +0.44 |
| 594902 | 2017 | 2017-08-20 | 46 | 181 | 191 | 2.2 | 12.6 | 10.36 | 10.09 | +0.26 |
| 596001 | 2017 | 2017-07-24 | 25 | 162 | 260 | 7.4 | 16.5 | 9.13 | 8.25 | +0.88 |
| 605194 | 2017 | 2017-05-27 | 18 | 171 | 395 | 11.1 | 8.4 | 2.76 | 2.08 | +0.68 |
| 605254 | 2017 | 2017-08-23 | 21 | 237 | 177 | 10.5 | 9.0 | 1.51 | 2.44 | -0.93 |
| 605483 | 2017 | 2017-06-28 | 46 | 189 | 358 | 4.8 | 14.2 | 9.48 | 9.95 | -0.47 |
| 607259 | 2017 | 2017-08-01 | 28 | 302 | 176 | 6.3 | 11.4 | 5.07 | 7.01 | -1.94 |
| 607259 | 2017 | 2017-08-25 | 19 | 348 | 130 | 5.7 | 14.6 | 8.87 | 8.33 | +0.54 |
| 607352 | 2017 | 2017-08-27 | 25 | 368 | 149 | 12.0 | 7.4 | 4.57 | 4.28 | +0.29 |
| 592351 | 2018 | 2018-07-14 | 16 | 412 | 331 | 21.8 | 12.4 | 9.46 | 9.66 | -0.20 |
| 592468 | 2018 | 2018-07-02 | 23 | 144 | 198 | 19.4 | 7.6 | 11.87 | 10.63 | +1.24 |
| 605276 | 2018 | 2018-07-28 | 24 | 219 | 235 | 4.1 | 11.9 | 7.81 | 7.54 | +0.26 |
| 607231 | 2018 | 2018-06-21 | 22 | 106 | 381 | 16.0 | 5.5 | 10.53 | 9.23 | +1.30 |
| 608717 | 2018 | 2018-07-26 | 23 | 415 | 210 | 8.9 | 10.0 | 1.08 | 1.34 | -0.26 |
| 608717 | 2018 | 2018-08-21 | 18 | 445 | 180 | 8.5 | 11.1 | 2.57 | 2.17 | +0.40 |
| 642547 | 2018 | 2018-07-25 | 14 | 145 | 176 | 22.1 | 13.6 | 8.43 | 7.30 | +1.13 |
| 670950 | 2018 | 2018-06-07 | 43 | 107 | 440 | 9.3 | 15.0 | 5.65 | 5.87 | -0.22 |
| 592314 | 2019 | 2019-08-06 | 45 | 260 | 231 | 11.5 | 16.5 | 4.91 | 4.03 | +0.88 |
| 605446 | 2019 | 2019-05-25 | 15 | 182 | 257 | 6.0 | 9.3 | 3.29 | 4.12 | -0.83 |
| 605446 | 2019 | 2019-07-15 | 15 | 249 | 190 | 5.2 | 11.6 | 6.36 | 4.47 | +1.89 |
| 605446 | 2019 | 2019-08-01 | 17 | 267 | 172 | 7.1 | 9.3 | 2.19 | 4.01 | -1.82 |
| 605446 | 2019 | 2019-08-15 | 14 | 287 | 152 | 5.9 | 11.8 | 5.92 | 6.16 | -0.24 |
| 607536 | 2019 | 2019-07-13 | 44 | 273 | 200 | 8.8 | 8.0 | 0.79 | 1.08 | -0.29 |
| 622608 | 2019 | 2019-08-25 | 36 | 430 | 152 | 1.9 | 7.2 | 5.38 | 6.29 | -0.92 |
| 641816 | 2019 | 2019-09-01 | 44 | 437 | 119 | 18.3 | 12.6 | 5.70 | 5.70 | +0.00 |
| 656546 | 2019 | 2019-07-25 | 35 | 151 | 164 | 15.2 | 6.7 | 8.52 | 7.39 | +1.14 |
| 656546 | 2019 | 2019-08-13 | 19 | 174 | 141 | 13.2 | 7.8 | 5.42 | 5.83 | -0.41 |
| 656546 | 2019 | 2019-09-01 | 19 | 187 | 128 | 13.4 | 7.0 | 6.34 | 6.30 | +0.04 |
| 592866 | 2021 | 2021-08-12 | 18 | 264 | 141 | 14.8 | 14.2 | 0.59 | 0.59 | +0.00 |
| 656605 | 2021 | 2021-08-01 | 52 | 228 | 242 | 9.6 | 8.7 | 0.97 | 1.00 | -0.03 |
| 663474 | 2021 | 2021-07-09 | 27 | 189 | 306 | 10.6 | 19.0 | 8.37 | 6.66 | +1.71 |
| 666200 | 2021 | 2021-08-02 | 44 | 173 | 264 | 13.9 | 9.8 | 4.02 | 3.41 | +0.62 |
| 669060 | 2021 | 2021-06-20 | 29 | 104 | 218 | 7.7 | 7.3 | 0.35 | 1.44 | -1.09 |
| 669060 | 2021 | 2021-07-21 | 31 | 124 | 198 | 9.7 | 6.1 | 3.62 | 2.16 | +1.46 |
| 675921 | 2021 | 2021-07-21 | 23 | 101 | 128 | 10.9 | 10.9 | 0.05 | 0.22 | -0.18 |
| 677960 | 2021 | 2021-07-01 | 17 | 184 | 217 | 11.4 | 9.7 | 1.74 | 1.27 | +0.46 |
| 656849 | 2022 | 2022-08-20 | 14 | 335 | 119 | 15.8 | 21.0 | 5.19 | 4.91 | +0.27 |
| 657093 | 2022 | 2022-06-25 | 34 | 140 | 319 | -0.7 | 10.7 | 11.37 | 10.03 | +1.35 |
| 663372 | 2022 | 2022-07-29 | 33 | 149 | 279 | 16.8 | 8.6 | 8.18 | 7.16 | +1.01 |
| 663559 | 2022 | 2022-07-24 | 17 | 125 | 224 | 12.8 | 18.3 | 5.50 | 4.47 | +1.03 |
| 663559 | 2022 | 2022-08-20 | 22 | 170 | 179 | 15.3 | 17.3 | 2.02 | 2.88 | -0.86 |
| 669060 | 2022 | 2022-06-14 | 23 | 137 | 372 | 7.3 | 9.9 | 2.65 | 2.67 | -0.02 |
| 669060 | 2022 | 2022-07-02 | 18 | 163 | 346 | 7.4 | 10.1 | 2.75 | 2.04 | +0.71 |
| 669169 | 2022 | 2022-08-23 | 14 | 278 | 187 | 6.1 | 3.2 | 2.91 | 2.36 | +0.55 |
| 669923 | 2022 | 2022-07-26 | 18 | 274 | 268 | 19.3 | 21.6 | 2.30 | 2.05 | +0.25 |
| 669952 | 2022 | 2022-06-25 | 18 | 105 | 335 | 18.1 | 7.2 | 10.93 | 9.53 | +1.40 |
| 672282 | 2022 | 2022-07-08 | 17 | 237 | 302 | 9.7 | 17.5 | 7.85 | 7.35 | +0.49 |
| 672710 | 2022 | 2022-08-17 | 41 | 217 | 191 | 12.9 | 9.9 | 2.96 | 2.39 | +0.56 |
| 656731 | 2023 | 2023-08-05 | 45 | 327 | 240 | 5.8 | 11.7 | 5.86 | 5.78 | +0.07 |
| 656849 | 2023 | 2023-06-27 | 43 | 182 | 310 | 17.0 | 15.2 | 1.87 | 1.52 | +0.35 |
| 663559 | 2023 | 2023-08-05 | 82 | 175 | 172 | 11.4 | 11.6 | 0.20 | 0.88 | -0.68 |
| 666201 | 2023 | 2023-07-07 | 32 | 282 | 133 | 2.1 | 10.5 | 8.40 | 5.28 | +3.12 |
| 666214 | 2023 | 2023-07-29 | 31 | 330 | 162 | 10.6 | 9.9 | 0.73 | 2.10 | -1.37 |
| 671106 | 2023 | 2023-07-18 | 20 | 275 | 262 | 14.2 | 12.2 | 1.97 | 4.43 | -2.47 |
| 671737 | 2023 | 2023-09-03 | 36 | 330 | 130 | 22.1 | 13.1 | 9.04 | 8.51 | +0.54 |
| 680570 | 2023 | 2023-07-17 | 52 | 211 | 304 | 16.6 | 17.1 | 0.52 | 1.19 | -0.67 |
| 682847 | 2023 | 2023-08-23 | 50 | 247 | 153 | 3.2 | 2.0 | 1.28 | 1.40 | -0.12 |
| 691587 | 2023 | 2023-08-07 | 32 | 215 | 159 | 20.5 | 20.8 | 0.29 | 0.39 | -0.10 |
| 694297 | 2023 | 2023-06-29 | 34 | 107 | 314 | 9.3 | 18.5 | 9.13 | 9.52 | -0.40 |
| 694297 | 2023 | 2023-07-22 | 23 | 122 | 299 | 9.0 | 19.1 | 10.05 | 8.74 | +1.31 |
| 672282 | 2024 | 2024-09-03 | 94 | 277 | 114 | 15.5 | 24.6 | 9.04 | 9.04 | +0.00 |
| 679525 | 2024 | 2024-08-26 | 28 | 425 | 123 | 14.4 | 18.7 | 4.35 | 5.18 | -0.83 |
| 681867 | 2024 | 2024-07-12 | 27 | 218 | 206 | 16.5 | 2.9 | 13.60 | 11.71 | +1.89 |
| 687792 | 2024 | 2024-07-23 | 16 | 141 | 241 | 22.7 | 15.8 | 6.93 | 6.40 | +0.52 |
| 700249 | 2024 | 2024-07-29 | 17 | 149 | 203 | 4.0 | 14.3 | 10.26 | 14.12 | -3.86 |
| 663568 | 2025 | 2025-07-22 | 17 | 287 | 174 | 9.4 | 10.9 | 1.51 | 1.66 | -0.15 |
| 663568 | 2025 | 2025-08-30 | 34 | 336 | 125 | 8.9 | 12.8 | 3.87 | 3.65 | +0.22 |
| 671737 | 2025 | 2025-08-24 | 32 | 471 | 134 | 10.8 | 14.9 | 4.10 | 5.58 | -1.48 |
| 680573 | 2025 | 2025-06-10 | 27 | 166 | 305 | 12.7 | 13.1 | 0.46 | 1.25 | -0.79 |
| 686701 | 2025 | 2025-07-29 | 18 | 130 | 193 | 12.3 | 11.4 | 0.91 | 1.37 | -0.46 |
| 688138 | 2025 | 2025-06-10 | 14 | 144 | 206 | 10.4 | 6.3 | 4.11 | 4.70 | -0.60 |
| 688138 | 2025 | 2025-07-03 | 23 | 167 | 183 | 10.8 | 5.5 | 5.31 | 4.85 | +0.47 |
| 693821 | 2025 | 2025-06-01 | 18 | 181 | 498 | 11.0 | 12.0 | 1.00 | 1.77 | -0.77 |
| 694477 | 2025 | 2025-08-19 | 45 | 400 | 103 | 16.2 | 21.4 | 5.11 | 5.11 | -0.00 |
| 801403 | 2025 | 2025-08-11 | 36 | 309 | 132 | 6.1 | 10.6 | 4.46 | 4.50 | -0.04 |
| 682052 | 2026 | 2026-07-07 | 37 | 243 | 176 | 2.1 | 21.6 | 19.53 | 19.23 | +0.30 |
| 691725 | 2026 | 2026-07-31 | 44 | 299 | 111 | 9.7 | 14.4 | 4.72 | 4.72 | -0.00 |

## Verdict

**DOES NOT CLEAR.** OPTION behaves exactly like every other event type in the
v4 taxonomy: excess |dK-BB%| over matched same-position controls is +0.10pp
(z = 0.82, permutation p = 0.21), against a bar of z > 1.83 that was already
the LENIENT given-split bar. The issue's "intervention, not interruption"
mechanism does not show up in the data — an option stint supplies a legitimate
place to LOOK (a given split point), but the split moves the line no more than
a random split at the same time of year. This is the sixth failure in the
regime-break family and the first for an event type with a deliberate-
intervention mechanism.

Full v4 table with OPTION appended:

| event | seasons | excess dK-BB% | t |
|---|---|---|---|
| IL_SHORT | 219 | +0.02 | 0.66 |
| IL_MED | 134 | +0.14 | 1.87 |
| ROLE_ROT | 77 | +0.02 | 0.06 |
| TRADE | 86 | +0.09 | 0.99 |
| ROLE_PEN | 75 | -0.00 | 0.14 |
| IL_LONG | 37 | -0.07 | -0.57 |
| **OPTION** | **66** | **+0.10** | **0.82** |

## Next step

**None toward a model feature.** Per issue #52's own sequencing ("If excess
|dK-BB%| over controls is ~0 like every other event, stop there"), step 3
(`/validate-feature` pre-registration of `is_optioned_at_split` /
`days_since_recall` / `option_stints_to`) is NOT triggered. The regime-break
family stays CLOSED; the re-open condition in
`sp_regime_break_finding_2026-08-26.md` v5 stands unchanged.

What survives as a byproduct:
- the OPTION event panel + transaction cache are reusable (e.g. for a
  `/model-health` coverage tripwire, or descriptive annotation in
  `/triangulate` — Rule 13, context only);
- the v4 IL bins are now known to have been IL+option mixtures (112/50/6
  events relabeled), and both components are null, so no v4 conclusion changes.

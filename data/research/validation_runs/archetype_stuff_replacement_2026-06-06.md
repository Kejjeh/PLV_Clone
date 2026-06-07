# Archetype STUFF vs FanGraphs Stuff+ — replacement analysis
_2026-06-06 — research one-off (compare_stuff_sources.py). Not committed._

## 1. Clean predictive head-to-head (predicting ros_fp)

Frame: n=506 FG SP-seasons 2021-25.
Coverage in frame: FG stuff_plus=506, archetype STUFF full-season=506, archetype STUFF prior-year=324.

### Pooled partial r over baseline [pre_fp + k_pct + bb_pct + swstr_pct + siera]

| signal | raw r | partial r | p | n |
|---|---|---|---|---|
| FG stuff_plus (as-of) | +0.521 | +0.298 | 0.0000 | 506 |
| archetype STUFF (PRIOR yr, CLEAN) | +0.519 | +0.291 | 0.0000 | 324 |
| archetype STUFF (full-season, LEAKY) | +0.655 | +0.572 | 0.0000 | 506 |

### Per-year partial r over baseline

| signal | 2021 | 2022 | 2023 | 2024 | 2025 | signs |
|---|---|---|---|---|---|---|
| FG stuff_plus (as-of) | +0.304 | +0.349 | +0.258 | +0.216 | +0.421 | 5/5 |
| archetype STUFF (PRIOR yr, CLEAN) | n/a | +0.322 | +0.140 | +0.400 | +0.252 | 4/5 |
| archetype STUFF (full-season, LEAKY) | +0.413 | +0.597 | +0.612 | +0.596 | +0.621 | 5/5 |

### Cross-year Ridge lift (train 2021-23 -> test 2024-25)

Baseline [pre_fp + rate stats]: r = 0.4773 (n_test=209)

| + signal | r | gain |
|---|---|---|
| FG stuff_plus (as-of) | 0.5346 | +0.0573 |
| archetype STUFF (PRIOR yr, CLEAN) | 0.6001 | +0.1229 |
| archetype STUFF (full-season, LEAKY) | 0.7115 | +0.2342 |

## 2. As-of availability — is there a LIVE 2026 archetype STUFF?

- 2026 rows in sp_ratings_master.csv: **115**, STUFF non-null: **115**.
- 2026 gs range in archetype master: 6-7 (GS_FLOOR_RATED=6 applied) -> season-to-date, NOT end-of-year.
- Underlying Statcast source (sp_multiyr) 2026: 161 SPs, gs 3-7 (mean 5.9).
- build_sp_archetypes.build_ratings_panel() rates STUFF from season-to-date k_pct / swstr_pct / c_plus_swstr aggregated per (pitcher, year); 2026 = games played to date. It is step 2.6 of refresh_dashboards.py, so it updates DAILY.

**Verdict 2b: YES — archetype STUFF is a live, season-to-date grade that refreshes daily.**

## 3. Ranking-equivalence on the live 2026 pool

Joined 2026 SPs (FG gs>=5 INNER archetype): n=115.

- FG stuff_plus <-> archetype STUFF on 2026 pool: Pearson r = 0.631, Spearman rho = 0.583.

- Breakout-ranking Spearman (FG-stuff ranking vs archetype-STUFF ranking): rho = 0.635.

- Top-15 breakout name overlap: **7/15** (47%).

- **Eury Perez check**: FG stuff_plus=117.6 (rank 1/115), archetype STUFF=54 (rank 24/115). Both rank him elite-stuff: see ranks.
  Raw stuff percentile in pool: FG 97th, archetype 65th.

### Side-by-side: top 15 breakout picks by FG ranking

| name | FG stuff+ | arch STUFF | rank_FG | rank_arch | d_rank |
|---|---|---|---|---|---|
| Pérez, Eury | 118 | 54 | 1 | 24 | +23 |
| Crochet, Garrett | 113 | 50 | 2 | 22 | +20 |
| Sasaki, Roki | 106 | 50 | 3 | 8 | +5 |
| Sánchez, Cristopher | 118 | 64 | 4 | 13 | +9 |
| Misiorowski, Jacob | 126 | 80 | 5 | 3 | -2 |
| Nola, Aaron | 107 | 55 | 6 | 9 | +3 |
| Bello, Brayan | 92 | 45 | 7 | 1 | -6 |
| May, Dustin | 103 | 33 | 8 | 82 | +74 |
| Castillo, Luis | 98 | 43 | 9 | 15 | +6 |
| Woo, Bryan | 110 | 44 | 10 | 79 | +69 |
| Flaherty, Jack | 100 | 45 | 11 | 20 | +9 |
| Chandler, Bubba | 105 | 45 | 12 | 49 | +37 |
| Williamson, Brandon | 98 | 37 | 13 | 47 | +34 |
| Cavalli, Cade | 102 | 56 | 14 | 2 | -12 |
| Bassitt, Chris | 96 | 36 | 15 | 42 | +27 |

## 4. Coverage gap (2026 live pool)

- FG 2026 SPs (gs>=5): 165
- Archetype 2026 SPs (gs>=6 floor): 115
- In both: 115
- **FG-only (have FG stuff, NO archetype STUFF): 50** — these LOSE a stuff grade if we drop FG.
- Archetype-only (archetype but not in FG gs>=5 pool): 0.

### FG-only SPs (top 15 by FG stuff+) — the coverage we'd lose

| name | FG gs | FG stuff+ |
|---|---|---|
| Payton Tolle | 8 | 114 |
| Shohei Ohtani | 10 | 114 |
| Trey Yesavage | 8 | 111 |
| Carlos Rodon | 5 | 109 |
| Christian Scott | 8 | 108 |
| Logan Henderson | 5 | 107 |
| Nick Lodolo | 5 | 107 |
| Griffin Jax | 7 | 107 |
| Zack Wheeler | 8 | 106 |
| Ben Brown | 5 | 104 |
| Anthony Kay | 11 | 104 |
| Connor Prielipp | 8 | 103 |
| Sonny Gray | 11 | 101 |
| Trevor McDonald | 6 | 101 |
| Andrew Painter | 10 | 100 |

Median FG gs among FG-only: 8 (low gs => small-sample / callups, below archetype's gs>=6 floor).

## Recommendation

- Predictive (clean): FG stuff_plus partial r = +0.298; archetype STUFF (prior, clean) partial r = +0.291. d = -0.007.
- Live stuff-source correlation (2026): r = 0.631.
- Breakout ranking agreement: Spearman 0.635, top-15 overlap 7/15.
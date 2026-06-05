# Pitcher List Historical Rank Archive — Coverage Report

**Built:** 2026-06-04
**Output dir:** `data/research/pl_historical/`
**Purpose:** Feed historical PL ranks paired with outcomes into a weight-optimization backtest for the rh3/rp3/rprs2 ensemble. Quantifies how much weight PL rank should carry in the blend.

## Articles scraped (31 total)

### Starting Pitchers (Top 100) — 15 articles

| Year | Early | Mid | Late | Notes |
|------|-------|-----|------|-------|
| 2025 | W1 (3/31) | W13 (6/23) | W21 (8/18) | Full coverage |
| 2024 | W2 (4/8)  | W13 (6/24) | W21 (8/19) | Full coverage |
| 2023 | W2 (4/10) | W13 (6/26) | W21 (8/21) | Full coverage |
| 2022 | W1 (4/11) | W13 (7/5)  | W21 (8/22) | Full coverage |
| 2021 | W2 (4/5)  | W13 (6/21) | W21 (8/16) | Full coverage |
| 2020 | — | — | — | **GAP**: 2020 PL articles are split into Top 20/40/60/80/100 partial articles; main URL only contains rank 81–100. COVID-shortened 60-game season anyway. |
| 2019 | — | — | — | **GAP**: Same split-article format as 2020; the canonical Top-100 URL only contains ranks 81–100. |
| 2018 | — | — | — | Same partial-article format. Not scraped. |

### Hitters (Top 150) — 16 articles

| Year | Early | Mid | Late | Notes |
|------|-------|-----|------|-------|
| 2025 | W1 (3/26) | W13 (6/26) | W20 (8/14) | Full coverage |
| 2024 | W1 (4/3)  | W13 (6/26) | W15 (7/11) | Full coverage; late=W15 (no clean W21 URL found) |
| 2023 | — | W13 (6/28) | W21 (8/23) | Missing early-season (W1 URL not surfaced; W3 4/19 exists but skipped) |
| 2022 | W1 (4/13) | W13 (7/6)  | W21 (8/31) | Full coverage |
| 2021 | early (4/21) | mid (6/23) | late (8/25) | Article title format used "Hitter List X/Y" with no "Week N" label |
| 2020 | — | mid (8/5) | late (9/16) | COVID-shortened; preseason URL is a split-article series |
| 2019 | — | — | — | Not in scope per scan results |

### URL pattern shifts observed

- **2021–2025 SP**: stable `top-100-starting-pitchers-for-<YEAR>-fantasy-baseball-week-<N>-<M-DD>/` (2024–25) and `the-list-<M-DD>-top-100-starting-pitchers-for-<YEAR>-week-<N>/` (2021–23).
- **2018–2020 SP**: pre-season ranks were SPLIT into Top 20 / Top 40 / Top 60 / Top 80 / Top 100 articles. The "complete" URL only contains the final 81–100 segment. Reconstructing 1–100 requires fetching 5 separate articles per year (not done in this pass).
- **2021 hitters** used "Hitter List M/D - Ranking the Top 150 Hitters" pattern (no "Week N" label); 2022+ moved to explicit "Week N" labels.
- **2020 in-season hitter articles** continue weekly despite the 60-game season.

## Observation count for backtest

Approximate paired (rank, outcome) observations available:

- **SP**: 15 articles × ~100 ranked + ~30 IL-section players = **~1,950 SP rank-snapshots** across 2021–2025 (5 years × 3 windows).
- **Hitters**: 16 articles × ~150 = **~2,400 hitter rank-snapshots** across 2020–2025 (6 years × varying windows).
- **Total**: **~4,350 rank-snapshots** to join against MLB season outcomes (FP-per-game H, FP-per-start SP).
- After ROS-window pairing (e.g., W1 rank → full-season outcome, W13 rank → 2H outcome, W21 rank → final-month outcome), each snapshot yields ~1 outcome row → **~4,350 training pairs** for the weight-optimization backtest.

## Notable gaps / issues

1. **2018–2020 SP coverage missing** — PL used split-articles pre-2021 (Top 20 → Top 100 as 5 separate URLs). Recovering ranks 1–80 per year requires 4 additional fetches per year (12 extra fetches for 2018+2019+2020). Skipped to respect rate-limit budget; can be filled in a follow-up pass.
2. **2020 COVID-shortened** — 60 games total. In-season hitter coverage exists (mid/late) but small-sample outcomes; flag in model with a `season_short=True` indicator before joining.
3. **Hitter 2023 W1** — Did not find a clean W1/W2 URL; W3 (4/19) is the earliest hitter article surfaced. Acceptable since W3 still represents early-season decisions.
4. **Hitter 2024 late** — Used W15 instead of W20/W21 (closest surfaced).
5. **2021 hitter article naming** — No "Week N" in URL; I labeled files `early/mid/late` and stored `as_of_date` for joining.
6. **2018 not scraped at all** — pre-season-only format, would yield very low-information for our model.
7. **IL section format inconsistency** — Some weeks list IL players with specific ranks (W13 2025), others bucket them in 10-rank bands ("1–10", "11–20"). I encoded bands as single midpoint values (e.g., "1–10" → 5) for join-friendliness. Re-check `injury_list_ranks` schemas in JSON before joining.
8. **Player-name normalization required** — Accents (José, Suárez), Jr./Sr. suffixes, "Luis García" vs "Luis García Jr." disambiguation. Pipeline should reuse `plv_clone.utils.name_match.resolve_batter_id` and equivalent for pitchers.

## File inventory

```
data/research/pl_historical/
├── article_url_index.csv          # 38 candidate URLs (some not scraped)
├── coverage_report.md             # this file
├── pl_sp_2025_W1.json   pl_sp_2025_W13.json   pl_sp_2025_W21.json
├── pl_sp_2024_W2.json   pl_sp_2024_W13.json   pl_sp_2024_W21.json
├── pl_sp_2023_W2.json   pl_sp_2023_W13.json   pl_sp_2023_W21.json
├── pl_sp_2022_W1.json   pl_sp_2022_W13.json   pl_sp_2022_W21.json
├── pl_sp_2021_W2.json   pl_sp_2021_W13.json   pl_sp_2021_W21.json
├── pl_h_2025_W1.json    pl_h_2025_W13.json    pl_h_2025_W20.json
├── pl_h_2024_W1.json    pl_h_2024_W13.json    pl_h_2024_W15.json
├── pl_h_2023_W13.json   pl_h_2023_W21.json
├── pl_h_2022_W1.json    pl_h_2022_W13.json    pl_h_2022_W21.json
├── pl_h_2021_early.json pl_h_2021_mid.json    pl_h_2021_late.json
└── pl_h_2020_mid.json   pl_h_2020_late.json
```

## Schema (per JSON)

```json
{
  "source_url": "<canonical pitcherlist.com URL>",
  "fetched": "2026-06-04",
  "season_year": 2024,
  "week": 13,                  // int OR "early"/"mid"/"late" for 2020-21 H, "preseason" for 2020 SP
  "as_of_date": "2024-06-25",  // approximate; matches the article slug date
  "notes": "optional flag like 'COVID-shortened 60-game season'",
  "ranks": {"Player Name": 1, ...},               // main top-100 (SP) or top-150 (H)
  "injury_list_ranks": {"Player Name": 5 | "IL", ...}   // 5 = midpoint of 1-10 band when bucketed
}
```

## Next steps (for the backtest consumer)

1. Build a loader that walks the directory, normalizes names with `resolve_batter_id`/`resolve_pitcher_id`, and emits a long-form `(season_year, as_of_date, player_id, pl_rank, role, list_type)` table.
2. Join against historical FP outcomes from `data/research/xfp_cache/multiyear/` for the ROS window relative to each `as_of_date`.
3. Run grid search on weight `w_pl` in the blend `score = w_model * model_rank_norm + w_pl * pl_rank_norm` against held-out FP per-game / per-start outcomes.
4. Stratify by SP vs H — PL hitter ranks are 12-team-redraft + 5x5 calibrated (R/HR/RBI/AVG/SB), so they likely undervalue BB+K-neutral profiles that our points-league model prefers. Expect different optimal weights per role.
5. **Backfill 2018–2020 SP** in a future pass by walking the 5 split URLs per year if PL→model lift is found to be informative.

---

## 2026-06-04 update — Phase 3 Agent 4 gap-fill

Added 8 new article files via 5-split reconstruction (preseason SP) and direct in-season closer fetches:

### SP gap-fill (preseason, bucketed as `early` W1)
| Year | File | Source | Notes |
|------|------|--------|-------|
| 2019 | `pl_sp_2019_W1.json` | 5 split URLs (Top 20/40/60/80/100) | Full 1-100 reconstructed |
| 2020 | `pl_sp_2020_W1.json` | 5 split URLs | Full 1-100, `covid_short: true` |
| 2018 | **NOT ADDED** | Top 20 paywalled, Top 60 returned 404 | Cannot reconstruct full top-100; skipped to avoid biased partial |

### RP gap-fill (closers articles — Closing Time series)
| Year | File | Source date | Notes |
|------|------|-------------|-------|
| 2025 | `pl_rp_2025_W13.json` | 2025-06-24 (Top 40) | |
| 2024 | `pl_rp_2024_W13.json` | 2024-06-25 (Top 30) | |
| 2023 | `pl_rp_2023_W11.json` | 2023-06-12 (Top 30) | |
| 2022 | `pl_rp_2022_W14.json` | 2022-07-12 (Top 30) | |
| 2021 | `pl_rp_2021_W12.json` | 2021-06-22 (Top 30) | |
| 2020 | `pl_rp_2020_W13.json` | 2020-08-11 (Top 30) | COVID-shifted; mapped to mid bucket; `covid_short: true` |
| 2019, 2018 | **NOT ADDED** | Closer rankings rendered via WP shortcode (`[closing_time list_id=...]`) — not in fetched HTML | Cannot extract without authenticated/JS-rendered scrape |

### New coverage (post-rebuild)
Panel grew from 1,661 → **2,044 player-years** (+383, +23%).
- `pl_rank_early`: 1,134 (was ~700)
- `pl_rank_mid`: 1,291 (was ~900; RPs now populate mid)
- Name match rate: 82.1% (3,506 / 4,269); was 80.5%

### Weight blend re-fit (`weight_blend_with_pl_2026-06-04.json`, overwritten)

| Pos | n_joined | join rate | R² baseline | R² + PL | Lift | CI95 | Convergence |
|-----|---------:|----------:|------------:|--------:|-----:|------|:-----------:|
| H   | 721      | 22.1% (unchanged) | 0.1083 | 0.1705 | +0.0623 | [0.020, 0.102] | 4/4 |
| SP  | 604      | **51.3%** (was 45%) | 0.1756 | 0.2752 | **+0.0997** | [0.042, 0.157] | 5/6 |
| RP  | 146      | **13.2%** (was 2.1%) | 0.0919 | 0.4540 | **+0.3622** | [0.247, 0.479] | 5/5 |

**RP unlocked.** PL closer-rank now drives 30+ R² points on a 146-row inner-join (closers-only subset of RP universe). The `pl_rank_mid_inv` drop-test value is **0.3046** — by far the largest single-feature drop in any blend so far. Caveats: small N, restricted to closers (selection bias — middle relievers don't appear on PL closers list), and 2020 included because COVID flag handled at file level.

### Caveats / failed fetches
1. **2018 SP backfill blocked** — Top 20 paywalled by PL Pro; Top 60 URL returns 404. Top 21-100 fragments available but partial dataset would bias coverage. **Skipped intentionally.**
2. **2018 + 2019 closers blocked** — articles render rankings via `[closing_time list_id=...]` shortcode; HTML doesn't include the list. Would require JS-rendering or PL API access.
3. **In-season SP top-100 weekly articles 2018-2020** paywalled (e.g., "The List 7/10" 2018).
4. **2024 PL Top 100 RPs (Save+Hold)** exists but not fetched this pass — could grow RP coverage to ~25% if extracted. Deferred to a future pass.

### Remaining gaps
- 2018 SP: cannot reconstruct without subscriber access.
- 2018-2019 RP: shortcode-rendered.
- Hitters: hitter coverage unchanged this pass (no PL hitter articles added).


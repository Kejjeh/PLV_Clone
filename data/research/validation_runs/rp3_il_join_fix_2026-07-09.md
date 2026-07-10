# rp3 IL-feature join fix — 2026-07-09

**Verdict: SHIPPED.** Production bug confirmed, quantified, fixed via cache
rebuild (no join-code change), validated with a Rule-9 full-baseline LOO
before/after under a pre-registered no-regression rule (Δr −0.0002, within
the −0.002 tolerance; MAE improved).

## The bug

`rp3.main()` (and `_rp3_validation_harness.prep_rolling`) attach the three
VALIDATED IL features with an EXACT merge:

```python
rolling.merge(il, on=['pitcher', 'year', 'split_day'], how='left')
```

`il_split_features_2018_2026.csv` was built on MONTHLY anchors
`[30, 60, 90, 120]` (+ one end-of-season elapsed day per year), while
`rolling_pitchers_2018_2026.csv` moved to a WEEKLY grid
(`range(30, 201, 7)` = 30, 37, 44, …, 198). 60/90/120 are not ≡ 30 (mod 7),
so the only shared anchor was split_day 30.

## Quantification (before fix)

- **Exact-join match rate: 0.45% overall** (139 / 30,595 rolling rows).
  Per year: 2018 0.03%, 2019 0.34%, 2021 0.73%, 2022 0.49%, 2023 0.45%,
  2024 0.66%, 2025 0.42%, 2026 0.55%. Per split_day: 11.0% at day 30,
  **0.00% at every other split**.
- Joinable ceiling (pitcher-years with an IL row at ≤ split_day): **27.4%**.
- **Post-fillna the three features were effectively constant:**
  - `il_stints_to`: 99.62% zeros (117 nonzero rows of 30,595)
  - `is_on_il_at_split`: 99.72% zeros (87 ones)
  - `days_since_il_return_imp`: 99.62% at the sentinel; std 0.90
- **Sentinel collision (coordinator item):** with only day-30 rows matching,
  the observed max of `days_since_il_return` was 15, so the production
  `max+1` sentinel became **16.0** — inside the plausible range of real
  days-since-return values. In the degenerate state this was moot (117 real
  rows total). **Post-fix the sentinel is 170.0 vs a real max of 169** — by
  construction `max+1` always sits above every real value, so there is no
  collision. Sensitivity test (fixed cache, full RP3_FEATS both sides):
  sentinel `max+1` vs `9999` → overall LOO r **0.5613 vs 0.5613**
  (Δ 0.0000; per-year deltas −0.0005…+0.0012, mixed signs = noise).
  **Kept production `max+1`. No change shipped for the sentinel.**

### Second, compounding bug: stale current-year transactions

`il_transactions_2026.json` is a fetch-once cache
(`build_il_history.fetch_year_transactions` returns it as-is if present).
It froze at **2026-05-06** (1,807 events). Every IL placement after May 6
(Glasnow 5/8, Strider 6/13, Crochet transfer 6/5, Woodruff 7/5, Ranger
Suarez 7/9, …) was invisible to the IL features even where the join matched,
and the builder's "current elapsed day" row was emitted at split_day 41
(May 6) instead of 105 (today). Downstream this was partially masked by
refresh step 2a (`fix_il_flag_from_espn.py`), which patches
`is_on_il_at_split` in the projections CSV from live ESPN — one reason the
degeneracy went unnoticed.

## Timeline (since when)

- **2026-05-12** — IL features validated (RP2 integration; research doc
  §"Same-year IL status"). At that time BOTH the rolling substrate and the
  IL cache used `[30, 60, 90, 120]`: the join was healthy. Standardized
  coefs then: `days_since_il_return_imp` +0.128, `il_stints_to` +0.057,
  `is_on_il_at_split` −0.037. Registry PASS records are the three
  grandfather entries dated 2026-05-23.
- **2026-05-29** — commits `a71a740` (weekly snapshots 2024-2026 for the
  Player-Profiles dashboard) + `0d28168` (backfill weekly to 2018) moved
  `build_rolling_pitchers.py` to the weekly grid. `build_il_split_features.py`
  was never updated (its only commit is `a7f13c9`, 2026-05-07). **The join
  broke here — a TRUE regression, ~6 weeks in production, not a
  validated-through-broken-join artifact** (coordinator question #4
  answered: the 2026-05-12 validation predates the break).
- **~2026-05-06 onward** — separately, the 2026 transactions JSON froze.
- **2026-07-04** — audit added the NaN-truthy fix in `rp3.py` (comment at
  the `days_since_il_return` imputation: "float(nan or 200) returns nan …
  poisoning the imputation for an all-NaN column"). That fix implies the
  auditor OBSERVED `days_since_il_return` as (near-)all-NaN post-merge —
  a partial prior sighting of this degeneracy that was patched at the
  imputation symptom, not the join cause.
- **2026-07-09** — found while building the SP volume model
  (`sp_volume_model_2026-07-09.md` flagged the monthly-vs-weekly mismatch);
  fixed here.

## The fix (option a — cache rebuild; zero join-code change)

`scripts/xfp/build_il_split_features.py`:

1. **Substrate-derived anchor grid.** Per year, emit split_days =
   union of the split_day values actually present in
   `rolling_{pitchers,hitters,relievers}_2018_2026.csv`, the legacy monthly
   anchors `[30,60,90,120]` (back-compat for monthly consumers:
   backtest_framework, volume pipelines, diagnostics), the last-IL-date
   elapsed day (previous behavior), and today's elapsed day for the
   in-progress season. The exact join now stays correct even if the rolling
   cadence changes again.
2. **Staleness guard.** If the current year's `il_transactions_{year}.json`
   is > 3 days old, refetch from the MLB Stats API (same endpoint + trim
   rules as `build_il_history.py`) and rewrite the cache (fail-soft).
   Refetch pulled 4,155 IL events through 2026-07-09 (was 1,807 through
   May 6).
3. Perf: per-pid `groupby` instead of repeated boolean scans (grid is ~5×
   denser).

Cache: 65,284 → **361,416 rows**. `src/plv_clone/models/xfp/rp3.py` got a
**hard guard only** (mirroring the 2026-07-04 ros_opp_xwoba frozen-cache
guard): if < 2% of rolling rows carry IL history after the merge
(healthy ≈ 27%), raise instead of silently constant-filling. The merge
itself is unchanged. The validation harness needed **no change** — it reads
the same `IL_CSV` and its join is identical, so parity is preserved by the
cache rebuild.

## Quantification (after fix)

- Match rate **31.75%** = exactly the joinable ceiling (100% of joinable
  rows join; ceiling rose from 27.4% with the denser IL grid + refetched
  2026 events).
- `il_stints_to` 28.1% nonzero; `is_on_il_at_split` 12.2% ones;
  `days_since_il_return_imp` 164 distinct values, std 67.7.

## LOO cross-year eval (Rule-9 full baseline: same 24 RP3_FEATS both sides)

Pre-registered decision rule: ship if fixed ≥ current − 0.002.

| year | r (degenerate) | r (fixed) | Δr | MAE (degen) | MAE (fixed) |
|---|---|---|---|---|---|
| 2018 | 0.5440 | 0.5437 | −0.0003 | 2.8823 | 2.8772 |
| 2019 | 0.6508 | 0.6526 | +0.0018 | 2.9767 | 2.9702 |
| 2021 | 0.5742 | 0.5730 | −0.0012 | 2.7409 | 2.7343 |
| 2022 | 0.5979 | 0.5909 | −0.0070 | 2.8392 | 2.8543 |
| 2023 | 0.5049 | 0.5056 | +0.0007 | 2.9192 | 2.9153 |
| 2024 | 0.4717 | 0.4738 | +0.0021 | 2.8191 | 2.8139 |
| 2025 | 0.5718 | 0.5718 | +0.0000 | 2.7182 | 2.7146 |
| **overall** | **0.5615** | **0.5613** | **−0.0002** | **2.8430** | **2.8407** |

n = 19,111 both sides. Δr −0.0002 clears the −0.002 no-regression rule →
correct-by-construction ship (restores the features to what was validated
2026-05-12). Per-year signs 4+/3− — the restored features move pooled point-
forecast r by ~0 in the CURRENT 24-feature stack (drift + schedule features
absorb most of their 2026-05-12 marginal). **This is NOT a validation-grade
improvement claim** — the value of the fix is correctness of the 2026 IL
state (below), live nonzero coefficients (`days_since_il_return_imp` +0.158,
`il_stints_to` +0.130 in the refit), and un-degenerating three registry
features. Which also explains why LOO never flagged the break: the pooled r
was insensitive to killing them.

## Production output movement (348 pitchers before and after)

- Rank correlation before↔after **0.9979**; mean |Δ per_start| 0.07 FP,
  max 0.405 FP; zero players moved > 1 FP/start.
- Top 20: identical except one adjacent swap — Woo 17→16, **Glasnow 16→17**
  (−0.32 FP/start; his 2026 IL history is now visible to the model).
- **The real movement is the 2026 IL state:** `is_on_il_at_split=1` rows
  90 → **137**; `data_quality_tag` flips 47 pitchers from
  `data_driven_*` → `marcel_il` (Glasnow, Woodruff, Strider, Crochet,
  Fried, Rodón, Ranger Suarez, Severino, Holmes, Taillon, Bubic, …).
  Spot-checked 10/10 against the raw MLB transaction log: all have genuine
  open IL stints (placements/transfers after the old May-6 freeze).
  These pitchers were previously projected as ACTIVE data-driven SPs.

## rh3 analogous-bug check

**No analogous bug.** `rh3.py` defines `IL_CSV` but never reads or merges
it, and `RH3_FEATS` contains no IL features (same for `rh3_april.py` —
dead constant). Hitter IL features remain backlog. Consumers of the IL cache
that DO exact-join on weekly split_days (`enrich_rolling_relievers.py`)
are fixed for free by the denser grid; monthly/asof consumers
(`backtest_framework`, `xfp_volume_pipeline`, `xfp_sp_volume_pipeline`
merge_asof) are unaffected (monthly anchors preserved in the grid).

## Files changed

- `scripts/xfp/build_il_split_features.py` — substrate-derived grid,
  staleness refetch, groupby perf
- `data/research/xfp_cache/il_split_features_2018_2026.csv` — rebuilt
  (65,284 → 361,416 rows)
- `data/research/xfp_cache/il_transactions_2026.json` — refetched
  (1,807 → 4,155 events, through 2026-07-09)
- `src/plv_clone/models/xfp/rp3.py` — degenerate-join hard guard after the
  IL merge (no change to merge/imputation semantics)
- `data/models/xfp_rp3_pipeline.pkl`, `data/outputs/xfp_rp3_projections.csv`
  — regenerated
- `scripts/xfp/_rp3_validation_harness.py` — **untouched** (parity holds via
  the shared cache)

Tests: 148 il/rp3/rolling-matched tests pass; schema-stability suites pass.

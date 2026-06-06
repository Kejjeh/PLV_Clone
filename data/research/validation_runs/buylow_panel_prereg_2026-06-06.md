# Pre-registration: hitter BUY-LOW signal (composite_pct >= 75 AND rh3_pct <= 25) — 2026-06-06

## Hypothesis
Hitter BUY-LOW candidates flagged at as-of date `D` produce a mean residual
FP/PA over the window `[D+30d, D+60d]` that is strictly positive vs the model's
own `xfp_rh3_per_pa` projection at `D`.

A BUY-LOW candidate is defined as a hitter where:
- `composite_pct >= 0.75` (process composite rank-percentile within the
  build_process_panel hitter universe at `D`)
- `rh3_pct <= 0.25` (model rank-percentile of `xfp_rh3_per_pa` within the
  rh3 snapshot at `D`)

The intuition: "process is ahead of outcomes" — the player's 9-marker
direction-adjusted composite has moved high while the rh3 model still
ranks them in the bottom quartile of FP/PA expectation.

## Plan v11 references
- Decision 12: production CSV ships WITHOUT `buylow_flag` until this test passes.
- Decision 13: as-of safety = 2024-2025 universe (no 2023 snapshots).
  Gap rule + max snapshot age 31 days.

## Test metric
For each candidate at as-of `D`:

```
residual = actual_fp_per_pa([D+30d, D+60d])  −  xfp_rh3_per_pa[at D]
```

Where:
- `actual_fp_per_pa([a, b])` is BrownU hitter FP per plate appearance,
  computed from `statcast_<yr>.parquet` over the window:
  `(R + TB + RBI + BB + HBP + SB − K) / PA`.
- `xfp_rh3_per_pa[at D]` is read from the historical snapshot at
  `data/research/projection_snapshots/<D>/xfp_rh3_projections.csv`.

Aggregate statistics:
- Per-year mean residual + 95% CI (1.96 × SE on candidate-level residuals)
- Pooled mean residual + 95% CI

## Pass criteria (all must hold)
1. **Mean residual ≥ +0.015 FP/PA** (pooled across all candidates)
2. **Lower bound of 95% CI > 0** (pooled)
3. **N ≥ 30 candidates** across the 2024-2025 universe
4. **Both years agree** — neither 2024 nor 2025 mean residual flips sign
   (i.e., no single-year fluke driving the pooled result)

Bonferroni penalty: this is a single pre-registered hypothesis (1 family),
so the nominal α = 0.05 → CI bound > 0 is the right bar. No multi-comparison
penalty needed.

## Pre-registered as-of dates
For each year `yr in {2024, 2025}`, evaluate at every snapshot whose date
is within 31 days of an anchor stepped 30 days from `season_start(yr)`:

- 2024 anchors (season_start 2024-03-28): 04-27, 05-27, 06-26, 07-26
- 2025 anchors (season_start 2025-03-27): 04-26, 05-26, 06-25, 07-25

Available historical snapshots:
- `data/research/projection_snapshots/2024-04-27/xfp_rh3_projections.csv`
- `data/research/projection_snapshots/2024-05-27/xfp_rh3_projections.csv`
- `data/research/projection_snapshots/2024-06-26/xfp_rh3_projections.csv`
- `data/research/projection_snapshots/2024-07-26/xfp_rh3_projections.csv`
- `data/research/projection_snapshots/2025-04-26/xfp_rh3_projections.csv`
- `data/research/projection_snapshots/2025-05-26/xfp_rh3_projections.csv`
- `data/research/projection_snapshots/2025-06-25/xfp_rh3_projections.csv`
- `data/research/projection_snapshots/2025-07-25/xfp_rh3_projections.csv`

If at any as-of date the snapshot is missing or the snapshot date is more
than 31 days from the requested anchor, that date is `snapshot_missing`
or `gap_too_large` and is excluded from the test.

Hard 2020 exclusion is enforced upstream (no 2020 dates anywhere).

## Substrate / data sources
- Process panel: `scripts/xfp/build_process_panel.py --as-of D`
  → hitter panel with `composite` and `level_pct` columns. We compute
  `composite_pct` as a rank-percentile within the panel at `D`.
- Model snapshot: `data/research/projection_snapshots/<D>/xfp_rh3_projections.csv`
  → joins on `batter` (mlbam ID), provides `xfp_rh3_per_pa`. We compute
  `rh3_pct` as a rank-percentile within the snapshot.
- Forward outcomes: `data/research/xfp_cache/statcast_<yr>.parquet`
  filtered to `game_date in [D+30d, D+60d]`, aggregated per batter to
  (R, TB, RBI, BB, HBP, SB, K, PA) then scored by BrownU hitter formula.

## Failure modes that would invalidate the test
1. Snapshot gap > 31 days at any tested date (date is dropped, not faked)
2. Fewer than 30 BUY-LOW candidates pooled across both years
3. Sign flip between 2024 and 2025 pooled means (single-year fluke)
4. Forward-window has fewer than ~30 PA for a candidate
   (per-candidate filter: drop if `PA_forward < 30`)

## What we DO NOT test in this run
- SP BUY-LOW (process composite + low rp3 percentile) — separate hypothesis,
  separate future pre-reg.
- Season-long residuals (we test the T+30→T+60 window specifically; longer
  horizons would dilute the signal).
- Alternative thresholds (e.g., composite_pct >= 0.70, rh3_pct <= 0.30) —
  hypothesis is pre-registered at the (0.75, 0.25) cut.
- K%-only or BB%-only proxies for composite — composite is the full 9-marker
  direction-adjusted sum, no single-marker substitutes.

## Honest expectation
The BUY-LOW conjecture is plausible but unproven. Two ways it could fail:
1. The composite is dominated by recent-window K%/whiff% noise that does not
   convert to outcome lift in the next 30-60 days.
2. The rh3 model already accounts for process via its own feature set
   (career_stage, prior_fp_per_pa, etc.), so "low rh3" might already encode
   "process won't translate" — i.e., the model is right and BUY-LOW catches
   nothing.

A REJECTED outcome is a healthy result and matches the pattern from the
2026-06-06 closer-IL bundle rejection. Per Decision 12, no production
CSV change ships unless this passes.

## Audit trail
- Pre-reg committed BEFORE the script runs (this commit).
- Script + results in a separate commit.
- Verdict in a third commit if results require interpretation.

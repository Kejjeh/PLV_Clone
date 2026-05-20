# Matchup Adjuster Validation Plan (Phase MA)

## Current state (2026-05-20)

**MA0-MA7 adjuster chain SHIPPED but GATED OFF for production** via `--with-adjusters`
flag in `build_matchup_dashboard.py`. Live dashboard uses baseline xfp model only.

Adjusters can be enabled for backtest/dev work:
```bash
python scripts/xfp/build_matchup_dashboard.py --with-adjusters
# or
ADJUSTERS_ON=1 python scripts/xfp/build_matchup_dashboard.py
```

## Backtest findings (Week 8 / 2026-05-20)

Per `scripts/xfp/backtest_adjusters.py` — adjusters-off vs adjusters-on diff:

| Team | FP off | FP on | Delta |
|---|---|---|---|
| Ligers | 225.1 | 226.2 | +1.0 (+0.5%) |
| Team Solomon | 245.5 | 255.0 | +9.5 (+3.9%) |

**Aggregate impact small.** Adjusters move FP between players (top movers ±1-2 FP)
but don't fix the 15% over-projection bias — that lives in MA7 calibration which
is correctly gated off pending real validation.

### Per-adjuster status

| Adjuster | Status | Notes |
|---|---|---|
| MA1 — per-SP variance | ✓ WORKING | σ² tighter by 10-13% (good — per-player < blanket) |
| MA2 — recent-form | ✓ WORKING | 37/48 players non-neutral, directionally correct (Vlad 0.85, Bichette 1.15) |
| MA3 — lineup-spot | ✓ WORKING | 22/48 non-neutral, small magnitudes |
| MA4 — park factor | ✓ WORKING | 28/48 non-neutral, small magnitudes |
| **MA5 — platoon** | **✗ BROKEN** | **0/48 fires — `bat_side` not populated on ESPN player object** |
| MA6 — IL pro-rate | ⚠ UNTESTED | No IL'd players returning mid-window in current roster |
| MA7 — calibration | ⊘ GATED OFF | scalar 0.847 from Period 7 fit-on-self; safe_to_consume=false |

## Known issues / TODOs before any ship-on

1. **Fix MA5 platoon factor.** `getattr(player, 'batsHand', None)` returns None.
   ESPN's `Player` object exposes `_eligibleSlots` and other private attrs;
   need to find the bat-side attribute name or hit MLB Stats API for handedness.
   Until fixed, MA5 contributes nothing.

2. **MA0 calibration is fit on n=1 period (Period 7 only).** Scalar 0.847 is
   tautological for Period 7 — provides zero predictive evidence. Need ≥3 closed
   periods before scalar is trustworthy.

3. **Adjusters are heuristic, not fit.** The 0.85-1.15 clamps and ±3% lineup
   bonuses are intuition + literature, NOT fit to data. Could be too aggressive
   or too weak. Magnitude calibration requires post-Period-8+ data.

4. **Double-counting risk with xfp base model.** rh3 already exposes
   `recency_form_gap`; rp3 exposes `schedule_factor` and `next_opp_bat_index`.
   Our MA2/MA4 may overlap with these internal signals. AUDIT REQUIRED:
   - Read `scripts/xfp/xfp_rh3_pipeline.py` — is `xfp_rh3_per_game` already
     adjusted by `recency_form_gap` internally, or is the gap a diagnostic
     column only?
   - Read `scripts/xfp/xfp_rp3_pipeline.py` — is `xfp_rp3_per_start` already
     scheduled-adjusted, or is `xfp_rp3_per_start_sched` the adjusted version?
   - If base model already adjusts, our MA2/MA4 double-counts → bias.

## Validation gate before flipping ADJUSTERS_ON for production

Required before turning adjusters on:

### Gate 1: MA5 platoon must fire (fix bat-side lookup)
- 0/48 firing = adjuster is dead code
- Either fix or remove the gate from MA5 in the chain

### Gate 2: Double-counting audit on MA2 and MA4
- Read xfp_rh3_pipeline.py and xfp_rp3_pipeline.py
- Confirm `xfp_rh3_per_game` and `xfp_rp3_per_start` are RAW projections
  (recent form / schedule NOT yet applied) or DOCUMENTED adjusted versions
- If already adjusted, REMOVE the corresponding MA adjuster

### Gate 3: Post-Period-8 out-of-sample test (Sunday 5/24)
After Period 8 closes:
```bash
python scripts/xfp/calibrate_matchup_projection.py --backtest
# n_periods should now be 2 (Period 7 + 8)
# scalar_correction should be stable around 0.85 (or new value)
# If scalar moves dramatically (e.g., 0.85 → 1.10), Period 7 was an outlier
```

Compute predicted-vs-actual on Period 8:
- Build with adjusters OFF on Day 1 of Period 8 (5/19) → projection X_off
- Build with adjusters ON on Day 1 of Period 8 → projection X_on
- Final actual after Sunday games → actual_8
- Compare |X_off - actual_8| vs |X_on - actual_8| per team
- If adjusters-on MAE < adjusters-off MAE: evidence adjusters help
- If reverse: adjusters hurt, do not ship

### Gate 4: Accumulate evidence across ≥3 periods before flipping production
- Period 8 closes 5/24
- Period 9 closes 5/31
- Period 10 closes 6/7
- That's 3 out-of-sample observations × 2 teams = 6 data points
- If adjusters-on consistently beats adjusters-off MAE on 4/6 or better → ship

## Shipping decision tree (after Period 8 closes)

```
1. Run backtest_adjusters.py with actuals
   ├── adjusters-on MAE > adjusters-off MAE → keep gated off, iterate
   └── adjusters-on MAE ≤ adjusters-off MAE
       ├── Difference within noise (< 5% MAE improvement) → wait Period 9+
       └── Material improvement (>5% MAE reduction)
           ├── MA5 platoon still broken? → fix first
           ├── Double-counting audit done? → if not, audit first
           └── Both gates passed → consider ship-on
```

## Re-fit MA7 calibration scalar with proper history

Once we have ≥3 periods and adjusters validate:
1. Re-fit `calibrate_matchup_projection.py` with adjusters-ON projections
2. New scalar should be near 1.0 (per-component fixes absorbed the bias)
3. If still far from 1.0, the per-component adjusters aren't capturing the
   bias source — keep using residual scalar
4. Add `"safe_to_consume": true` to `data/models/matchup_calibration.json`
5. MA7 activates automatically

## Files involved

| File | Purpose |
|---|---|
| `scripts/xfp/build_matchup_dashboard.py` | Adjuster chain (gated by `--with-adjusters`) |
| `scripts/xfp/calibrate_matchup_projection.py` | MA0 calibration regression |
| `scripts/xfp/backtest_adjusters.py` | Per-adjuster off-vs-on diff (rerun weekly) |
| `data/models/matchup_calibration.json` | Calibration scalar + safe_to_consume flag |
| `data/research/backtest_adjusters.csv` | Latest per-player off-vs-on table |
| `data/outputs/predictions_history.csv` | Snapshots for backtest fitting |

## Honest assessment

The MA0-MA7 chain was built per spec but **shipped without empirical validation
of NET accuracy improvement.** Per the project's `feedback_validate_before_ship`
convention, this is the kind of ship we shouldn't make. The gate-off correctly
prevents the unvalidated chain from affecting live decisions. The backtest_adjusters
script provides the framework for proper validation once we have out-of-sample
data (Period 8 closes 5/24).

If adjusters fail their post-Period-8 validation, candidate actions:
- Disable individual adjusters that NET hurt MAE
- Keep only adjusters with clear directional value (MA1 σ², maybe MA2 recent-form)
- Drop the rest until they prove themselves
- Document each removal in this file with reason

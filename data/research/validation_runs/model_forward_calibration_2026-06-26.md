# Player-model forward calibration (rh3 / rp3) — retrospective + over/under verdict

**Date:** 2026-06-26
**Status:** VALIDATED (true forward test, real historical model outputs from git).
**Verdict:** Models are well-behaved. **No model change warranted** — point or bands.
The actionable bias is small, conditional, and mostly survivorship; correcting it would
re-introduce optimism for the full population.
**Engines:** `scripts/_oneoff/retro_calibration.py`, `retro_band_coverage.py`.

## Method (why this beats the same-period fit check)

The same-period check (`calib_models.py`, audited) compared the CURRENT projection to
realized SAME-season rates — confounded by (a) the projection containing the actuals
and (b) survivorship in the playing-time filter. This retrospective instead recovers the
**actual historical model output from git** (~14 dated snapshots of `xfp_rh3/rp3` CSVs,
May 7 → Jun 11) and compares each snapshot's projection to the player's realized FP over
the window **strictly AFTER** the snapshot date. Leakage-safe; regression-to-mean cannot
manufacture spurious tier bias because the forward actuals are a fresh realization.

- rh3: projected FP/game vs realized next-14d FP/game, ≥6 fwd G. n=3,929 / 14 snapshots.
- rp3: projected FP/start vs realized next-21d FP/start (data_driven only), ≥3 fwd GS. n=1,154 / 10 snapshots.

## Results

| Model | Forward bias | Forward Pearson r | Spearman | MAE |
|---|---|---|---|---|
| rh3 (hitter FP/g) | **+0.28** | **+0.35** | +0.35 | 0.88 |
| rp3 (SP FP/start) | **+0.45** | **+0.40** | +0.34 | 4.44 |

**Forward bias is positive in every one of 14 rh3 snapshots and across all rank tiers.**

### The survivorship gradient (rh3, the decisive diagnostic)
Forward bias is monotonic in the forward-games threshold:

| forward-games filter | rh3 bias |
|---|---|
| ≥1 (≈ no selection) | **+0.19** ← the real residual |
| ≥3 | +0.22 |
| ≥6 | +0.28 |
| ≥10 | +0.44 |
| ≥12 | +0.56 |

`corr(forward error, forward games) = +0.31`. So the bias GROWS with playing time
(endogenous — you keep starting the hot guys), BUT a **real residual ~+0.19 FP/g (~11%)**
survives at the floor where selection is ~zero. So: a small genuine under-projection +
a survivorship gradient on top.

### Reconciliation with the same-period audit
The same-period audit found the apparent +bias was "mostly survivorship; full population
centered-to-over." Both are true: (a) for players who keep a regular role, the models run
mildly light (+0.19 floor); (b) across the FULL population including faders, the models are
centered (rh3 ≈ +0.07 unfiltered) to mildly OVER (rp3 −0.82 unfiltered) because they hold
priors for players who then lose playing time. The forward-on-regulars read is the
decision-relevant one; the unconditional read is why you must NOT de-bias the number up.

### Forward rank skill is modest and honest
rh3 r≈0.35, rp3 r≈0.40 over a 2-3 week horizon — the same-period r 0.77-0.82 was inflated
by the projection containing the actuals. Matches the window study (season-to-date forward
r≈0.33). Per-2-week player FP is mostly irreducible noise; the models capture what's capturable.

## Band coverage (uncertainty-interval check)
- **rh3: NOT VALIDLY TESTED here** — `xfp_rh3_p25/p75` are on the **per-PA** scale
  (Yordan p25 0.71 / p75 0.88 ≈ his per_PA 0.80), so comparing to per-game actuals was a
  units mismatch. A real rh3 band check needs per-PA forward actuals (boxscore has no PA col).
- **rp3 (valid):** forward window-mean coverage **39%** in [p25,p75] (28% below / 33% above).
  Mildly narrow + a slight upward skew from the +0.45 point bias. Confounded: I compared a
  3-4-start window MEAN to a SINGLE-start band, and the point bias contaminates the skew, so
  this is **suggestive, not conclusive** — it does NOT mandate a σ change.

## Anything to change? — NO (and why the tempting changes are wrong)

1. **Do NOT add an intercept (+0.19) to rh3.** The bias is conditional on "keeps playing"
   and survivorship-flavored; unconditionally the models are centered-to-over. A blanket
   +0.19 would over-project the full population (the faders) and re-introduce the optimism
   the model correctly removed. Would fail Rule-9 validation.
2. **Do NOT reduce shrinkage.** The level bake-off (`window_predictive_validity_2026-06-26.md`)
   showed shrinkage HELPS; less shrinkage isn't validated and wouldn't improve forward r.
3. **Do NOT widen σ from the band check.** rh3's result was a units bug; rp3's 39% is
   confounded (window-mean vs single-start band + point-bias skew). A real σ recalibration
   needs a proper single-start-outcome coverage study — registered as an OPEN QUESTION, not
   a change.
4. **What IS done:** keep logging daily snapshots (`build_player_projection_history.py`,
   refresh step 4.10 — re-verified live, today's snapshot captured). In ~3-4 weeks re-run
   this on LOGGED snapshots (cleaner than git reconstruction) and run the proper rp3 σ study.

**Decision-layer framing (context, never a number-mover — Rule 13):** the models run mildly
conservative on established everyday regulars. Read it as a faint floor, NOT a reason to
re-rank or shade projections — the rank skill (~0.35-0.40 forward) is the value.

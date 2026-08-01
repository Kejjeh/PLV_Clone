# Cross-player daily FP correlation — the sigma-reversal follow-up

```yaml
registered: 2026-08-01
author: claude + josh
status: PRE-REGISTERED (results appended below the line after the run)
family: mc_correlation_structure (decision layer — Rule 13: cannot touch
        rh3/rp3/rprs2 or any shipped sigma without its own sign-off)
```

## Why this study exists

The 2026-07-30 §7b re-score on repaired matchup labels REVERSED the
team-level acceptance of the hitter-sigma widening: per-player daily sigma
was measured 9.7x understated (label-independent, stands), yet with the
widened sigmas the TEAM-level dispersion ratio fell to 0.704 (bootstrap CI
[0.546, 0.863], excluding 1) — the Monte Carlo now OVERSTATES team spread.

Those two facts can only coexist through the independence assumption: the
MC sums player draws independently, so Var(team) = Σσᵢ². If real same-team
daily FPs are NEGATIVELY correlated on average, independent summation with
CORRECT per-player sigmas overstates team variance — which is exactly the
observed pattern. (Negative within-team daily correlation is mechanically
plausible: a lineup shares a finite budget of PAs, runs, and RBI
opportunities on a normal night; blowouts push the other way.)

## Pre-registered questions

1. **ρ̂**: the average pairwise same-team same-day correlation of hitter
   daily FP, estimated from `boxscore_hitters.parquet` (2026 season,
   mlbam-keyed, the same store the boom/bust engine trusts). Player-pair
   correlations computed over shared game-days (min 20 shared days), then
   averaged weighted by shared-day count. Same for SP-vs-team-hitters and
   RP pairs if sample allows.
2. **Implied team-variance ratio**: for a k-hitter active lineup with
   average per-player sigma σ̄, Var_corr/Var_indep = (1 + (k−1)ρ̂ σ̄²/σ̄²)
   ≈ 1 + (k−1)ρ̂ for homogeneous sigmas. With k=13, even ρ̂ = −0.02 gives
   0.76 — the observed 0.704² ≈ 0.50... note the DISPERSION ratio is in SD
   units: SD ratio 0.704 implies variance ratio ≈ 0.50, needing
   (k−1)ρ̂ ≈ −0.50 → ρ̂ ≈ −0.04 at k=13. So the testable prediction:
   **if ρ̂ lands near −0.04, the correlation structure fully explains the
   reversal and BOTH prior measurements are right.**
3. **Decision consequence** (reported, not auto-shipped): whether the MC
   needs a correlation term (a shared-team daily factor in the draw
   assembly) or whether the per-player sigmas should absorb it. Either
   change is decision-layer, requires its own sign-off, and must NOT be
   shipped by this study.

## Stopping rules

- ρ̂ CI (player-pair clustered bootstrap, 2,000 resamples) excluding 0 in
  the negative direction AND |ρ̂| ≥ 0.02 → correlation structure is REAL;
  register the MC follow-up.
- CI spanning 0 → the reversal stays UNEXPLAINED; the per-player sigma
  scale becomes the prime suspect and the §7b follow-up re-opens.
- ρ̂ > 0 → independence UNDERSTATES team variance; the reversal deepens
  (both a wider-than-modeled team and an overwide post-fix measurement
  cannot both be true) — flag for a full re-derivation, change nothing.

---
## RESULTS (appended after the run — nothing above this line changed)

Run 2026-08-01, boxscore_hitters.parquet, 2026 season: 33,513 player-days,
611 players, 30 teams, 2,665 qualifying pairs (>=20 shared days, median 45).

| quantity | value |
|---|---|
| rho_hat (shared-day-weighted) | **+0.1085** |
| 95% CI (pair bootstrap, 2000) | [+0.1028, +0.1140] |
| unweighted mean | +0.1041 |
| share of pairs negative | 26.0% |
| implied k=13 variance ratio 1+(k-1)rho | 2.302 |
| implied k=13 SD ratio | **1.517** |

## VERDICT — stopping rule 3 fires: rho > 0, REVERSAL DEEPENS

The correlation is strongly POSITIVE, not the −0.04 that would have
explained the team-level reversal. Mechanically sensible: a lineup shares
one opposing pitcher, one park, one run environment — blowout coupling
dominates the finite-PA-budget effect.

**The three measurements now form an inconsistent triangle** and, per the
pre-registered rule, NOTHING SHIPS from this study:

1. per-player daily sigma understated 9.7x pre-fix (label-independent,
   sections 1-6 of the sigma memo — stands);
2. same-team daily correlation +0.11 (this study) → an independent-draw MC
   with CORRECT per-player sigmas UNDERSTATES team SD by ~1.5x at k=13;
3. yet the post-fix team-level dispersion measured 0.704 (OVERWIDE) on the
   repaired labels (n=19 snapshots, CI [0.546, 0.863]).

(1)+(2) predict the MC should still be too NARROW at team level; (3) says
it is too WIDE. Algebraically the triangle closes only if the widened
per-player sigma overshoots truth by ~2.2x — which contradicts (1)'s
direct measurement — or if (3)'s harness is measuring something other
than draw dispersion (its residual bundles PROJECTION error + realized
variance over a 19-snapshot panel), or n=19 is simply too small. The
follow-up that settles it is registered below.

## REGISTERED FOLLOW-UP (owner: next /model-health after period 18 closes)

Re-derive the three quantities in ONE harness on the same panel: per-player
draw sigma, the team aggregation with the measured +0.11 correlation, and
the team-level dispersion — on >=25 closed-period snapshots (period 18+
closes add 4/wk). Until then: P(win) numbers carry BOTH flags — the MC
assumes independence (understates tails if rho=+0.11 is the binding truth)
AND the only team-level calibration says overwide. Rule 13: no sigma, no
correlation term, no MC change ships without that harness's sign-off.

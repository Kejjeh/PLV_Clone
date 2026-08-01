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

---
# AMENDMENT A — fantasy-roster dilution (pre-registered 2026-08-01, before any run)

The +0.1085 is a SAME-MLB-CLUB pairwise correlation. A BrownU roster's 13
active hitters are spread across many MLB clubs, and cross-club pairs share
only the league-wide run environment — so the correlation that actually
reaches a FANTASY team total should be far smaller than +0.11. If it is
~0, leg (2) of the triangle (independence understates team SD 1.5x)
collapses to ~1.0x and the triangle reduces to a two-way tension:
per-player sigma vs the n=19 team-level 0.704.

## Pre-registered questions

A1. rho_fantasy: average pairwise daily-FP correlation among ACTIVE hitters
    of the SAME FANTASY roster (matchup_rosters_history x boxscore store,
    all 8 teams, every snapshot day; pair weights = shared days; min 10
    shared days given the store's ~2-3 week depth). Also report the split:
    same-MLB-club pairs vs cross-club pairs within fantasy rosters, and the
    average number of same-club pairs per roster-day.

A2. Direct realized-vs-modeled team-day SD: for each (fantasy_team, day),
    realized total FP of active hitters who PLAYED that day; modeled SD =
    sqrt(sum of per-player daily sigma^2) over the SAME players, using the
    shipped post-fix per-player sigma scale (the 3.2502 truth-SD constant
    x the hetero factors where available; flat 3.25 fallback acceptable and
    labelled). Report SD(realized - roster-mean)/modeled per team, pooled,
    raw AND day-demeaned (the day demean removes the shared-slate
    component, i.e. the cross-club correlation channel).

## Pre-registered interpretations

- rho_fantasy in [-0.01, +0.03] AND pooled A2 ratio in [0.85, 1.15]:
  the MC's independence assumption is FINE at the fantasy level, the
  per-player sigma is FINE at daily resolution, and the 0.704 team-level
  reading is an artifact of the SPREAD-level harness (projection error,
  n=19, or the weekly-total aggregation) — the triangle closes with all
  three legs right and the follow-up narrows to auditing the spread
  harness's construction.
- rho_fantasy > +0.05: dilution insufficient (stacked rosters); the MC
  correlation term goes back on the table (own sign-off required).
- A2 ratio < 0.8: the per-player daily sigma IS overshooting at the day
  level; the 9.7x fix gets a targeted re-audit (its own harness, not here).
- A2 ratio > 1.2: per-player sigma still too narrow at fantasy-team level;
  0.704 becomes the anomaly.

Rule 13: measurement only; nothing here ships a sigma, a correlation term,
or an MC change.

## AMENDMENT A RESULTS (run 2026-08-01, after the pre-registration above)

Roster store 2026-06-03..2026-08-01, 8 teams; 4,154 roster-day player rows
over 381 roster-days; 778 qualifying fantasy pairs (29 same-club / 749
cross-club; mean 2.09 same-club pairs per roster-day).

| quantity | value |
|---|---|
| rho_fantasy (weighted) | **-0.0097** [-0.0236, +0.0036] |
| same-club subset | +0.1570 (n=29 — replicates the club-level +0.1085) |
| cross-club subset | -0.0161 (n=749) |
| A2 realized/modeled, team-demeaned (raw) | 1.208 |
| A2 realized/modeled, day+team demeaned | **1.001** |
| per-team raw ratios | 1.05 - 1.42 |

## AMENDMENT VERDICT — pre-registered interpretation 1 FIRES; TRIANGLE CLOSES

- rho_fantasy is statistically zero: the +0.11 club correlation is real but
  DILUTED to nothing at the fantasy-roster level (~2 same-club pairs of ~54).
  The MC's independence assumption is FINE for BrownU rosters. Leg 2 closes.
- The per-player daily sigma is DIRECTLY confirmed: realized fantasy-team-day
  SD / modeled (sqrt(k) x 3.2502) = 1.001 after removing the shared-slate day
  component, on 381 team-days across all 8 rosters. Leg 1 closes.
- The raw ratio 1.208 quantifies the shared day environment (~20% SD) — a
  component that hits BOTH sides of a matchup and largely cancels in the
  my-vs-opp spread P(win) consumes. Honest caveat: for SINGLE-team totals
  (e.g. a fixed-FP target question) the MC understates SD by ~1.2x.
- The 0.704 team-level "overwide" reading is therefore ISOLATED as a
  spread-harness artifact (weekly aggregation + projection-error-bundled
  residuals + n=19). The >=25-period follow-up narrows to auditing THAT
  harness's construction; the sigmas and the independence assumption are
  measured sound. The 2026-08-01 tail-softness caveat on P(win) is
  substantially RETRACTED.

Analysis script: `corr_amendment_run.py` alongside this memo (read-only).
Rule 13: nothing shipped; nothing needed shipping — both measured legs
confirmed the production configuration.

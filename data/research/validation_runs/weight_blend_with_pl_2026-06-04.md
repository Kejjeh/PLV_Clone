# Weight blend + PL historical ranks — Phase 3 validation

**Date:** 2026-06-04
**Question:** Does Pitcher List historical rank add R² lift on top of the
existing Phase 2 blend (prior-year FP + archetype OVR + archetype career %ile
+ trajectory + age)?

## Files created

- `scripts/xfp/build_pl_rank_panel.py` — name-resolves PL archive JSON,
  buckets weeks into early (W1-6) / mid (W10-16) / late (W18-24), keeps
  earliest snapshot per (mlbam_id, year, bucket).
- `data/research/historical_panel/pl_rank_panel.parquet` — 1,661 player-years
  with up to 6 columns (pl_rank_early/mid/late and pl_il_rank_early/mid/late).
- `scripts/xfp/fit_weight_blend_with_pl.py` — refit with PL features added.
- `data/research/validation_runs/weight_blend_with_pl_2026-06-04.json` — raw
  per-fold results.

## 1 — Match rate

PL archive: 31 JSON files (15 SP, 16 H), 2020-2025. Overall name
resolution rate **80.5%** (3,122 of 3,880 ranked-name slots). Misses are
dominated by spelling variants the cache doesn't carry (e.g., players who
appeared in PL ranks but never accumulated enough Statcast PA/TBF to enter
our caches) and a handful of collision-guarded names that lack team
context in the PL JSON. No silent misattributions — collisions are
dropped from the name map per the canonical `KNOWN_COLLISIONS` rule.

## 2 — Effective N after inner-join with master panel

| Pos | n_baseline | n_joined | join rate |
|-----|-----------:|---------:|----------:|
| H   | 3,256      | 721      | 22.1%     |
| SP  | 1,178      | 532      | 45.2%     |
| RP  | 1,907      | 40       | 2.1%      |

**RP is unusable** — the PL archive is Top-150 Hitters + Top-100 SPs only.
RP coverage (~40 player-years) likely comes from positional-flex mismatches.
RP analysis is dropped from this report.

## 3 — R² blend without PL vs with PL (on identical joined rows)

| Pos | R² baseline | R² with PL | Pooled lift | Bootstrap 95% CI |
|-----|------------:|-----------:|------------:|------------------|
| H   | 0.108       | 0.171      | **+0.062**  | [+0.020, +0.102] |
| SP  | 0.164       | 0.297      | **+0.134**  | [+0.064, +0.193] |

Both lifts CI-positive — i.e., the lower 2.5% bound stays above zero.
The on-identical-rows baseline R² is lower than the Phase 2 figures
(H 0.240 / SP 0.295) because the PL-joined subset is shifted toward
top-tier players where prior-year FP is a weaker anchor (less spread).
The lift is what matters here, not the absolute R².

## 4 — Per-fold lift (Rule 8 convergence, excluding 2020)

**H** — 4/4 folds positive:
- 2022 +0.073, 2023 +0.124, 2024 +0.017, 2025 +0.076

**SP** — 5/5 folds positive:
- 2021 +0.158, 2022 +0.163, 2023 +0.088, 2024 +0.207, 2025 +0.055

No fold reverses sign. Magnitude is steady, not driven by a single year.
This passes the convergence gate.

## 5 — Drop-test contribution of each PL rank feature

(in-sample R² drop when the named feature is removed from the full model)

| Feature                 | H drop | SP drop |
|-------------------------|-------:|--------:|
| pl_rank_early_inv       | 0.009  | 0.003   |
| pl_rank_mid_inv         | **0.019** | **0.019** |
| pl_rank_late_inv        | 0.003  | **0.022** |
| anchor_fp (prior-yr FP) | 0.002  | 0.001   |
| arche_overall_prior     | 0.005  | 0.003   |

**pl_rank_mid is the workhorse for hitters**, dwarfing both prior-year-FP
and archetype OVR on this subset. For SPs, mid + late ranks each
contribute ~2% R² individually, with late edging out mid — consistent
with the intuition that the late-season ranking captures most of the
in-season information the model otherwise misses.

The early-season (W1-6) ranks are weak — they're essentially preseason
re-statements of prior-year production that the anchor already encodes.

## 6 — Honest assessment

**The PL signal is real and large enough to ship — with caveats:**

- The lift (+0.06 H / +0.13 SP) is several multiples of the Phase 2
  archetype OVR signal in this same subset. On in-sample drop-test,
  pl_rank_mid contributes ~4-20× more R² than anchor_fp or
  archetype OVR.
- **It is not a free lift in production.** PL ranks are only available
  for ~22% of hitter-years and ~45% of SP-years — restricted to "the
  top ~150 hitters" and "top ~100 SPs". Outside that envelope, the
  feature is structurally NaN, and the existing blend must still
  carry. Build the production scorer with a hard fallback: PL-ranked
  player → use enriched blend; everyone else → use Phase 2 blend.
- **Most of the signal is mid- and late-season, which is leak-adjacent.**
  pl_rank_late draws from W18-24 snapshots of the SAME season we're
  predicting — this is partial in-season information, not a clean
  preseason feature. For a true preseason model, restrict to
  pl_rank_early (lift drops to ~+0.01-0.02, marginal).
  For a midseason re-projection model (which is closer to how rh3/rp3
  are actually used), mid/late ranks are legitimate inputs.
- RP is dead air for this signal — PL doesn't rank relievers in the
  Top-100 SP series. Would need a separate "Closers and Saves"
  historical archive to test analogously.

**Recommended next step:** Promote `pl_rank_mid_inv` (single feature)
into a midseason rh3/midseason rp3 variant, gated on
`pl_rank_mid IS NOT NULL`. Skip pl_rank_late for now (within-season
leakage risk needs convergence-curve check per `feedback_convergence_curve_leakage_detector.md`).
Skip pl_rank_early (negligible lift).
Skip the IL-list ranks — N is too sparse (124-229 player-years)
for a clean signal isolation.

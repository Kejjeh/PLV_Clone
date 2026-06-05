# recform_hot retroactive + boom_stack 2024 POC — 2026-06-04

Phase 3 Agent 5 mandate: take the two live-compute tags that were
deferred in `weight_blend_live_tags_2026-06-04.md` and test whether
they add R² on top of Agent Y's blend (which already shipped
HIGH-K-ARM + shadow-scout, +0.055 R² lift).

## Part A — recform_hot retroactive (2018-2025 ex-2020)

**Builder:** `scripts/xfp/build_recform_hot_retroactive.py` →
`data/research/historical_panel/recform_hot_retroactive.parquet`
(n=4,089 pitcher × split-day rows). Leak-free: at split_day D, only
games with day-of-season < D are aggregated. Per-pitcher fp_proxy_per_bf
is computed start-level from statcast events (K, BB, HBP, H, R, outs),
last-5 starts averaged, then z-scored within the same-year-same-split
SP population (≥3 starts at cutoff floor). Verified mean ≈ 0, std ≈ 1.0
in every year × split cell.

**Fitter:** `scripts/xfp/fit_weight_blend_recform.py`. LOYO across
5 held-out years on matched sample, vs baseline of the existing
within-season SP blend (18 features incl. `fp_per_start_to`,
`k_pct_to`, `xwoba_per_pa_to`, `arche_ovr`, last21 trio, age, traj).

| split_day | n matched | baseline R² | +recform R² | Δ R² | recform partial R² |
|---|---|---|---|---|---|
| 60 | 582 | 0.6132 | 0.6130 | **−0.0002** | +0.0000 |
| 90 | 571 | 0.5755 | 0.5789 | **+0.0034** | +0.0029 |
| 120 | 558 | 0.5015 | 0.5030 | **+0.0015** | +0.0016 |

**5/5 fold convergence at all split days, but the effect is below the
+0.01 ship threshold by 3-7×.**

### Recform decomposition (correlations at split_day=90)

| Feature | r with recform_hot_z |
|---|---|
| fp_per_start_to | **+0.69** |
| xwoba_per_pa_to | −0.56 |
| arche_ovr | +0.51 |
| k_pct_to | +0.50 |
| swstr_pct_to | +0.40 |
| xwoba_on_contact_to | −0.33 |
| fp_per_start_last21 | +0.25 |
| k_pct_last21 | +0.21 |

Recform is **almost entirely redundant** with `fp_per_start_to` and the
season-to-date K-rate stack. The Phase-3 deferral note expected
"partially captured by k_pct_to and swstr_to" — the actual answer is
"largely captured by `fp_per_start_to`" (r=0.69) which is the single
strongest within-season predictor in the blend.

## Part B — boom_stack 2024-only POC

**Builder:** `scripts/xfp/build_boom_stack_2024_poc.py`. Three components
reconstructed at split_day=90 for 208 SPs with ≥3 starts before day-90
of 2024:

| Component | Logic (leak-free) | Fires |
|---|---|---|
| recform_hot | `recform_hot_z >= +0.5` from Part A panel | 69 / 208 |
| skill_spike | last-5 K% − season K% ≥ +3 pp AND last-5 BB% − season BB% ≤ −1 pp | 9 / 208 |
| park_friendly | pitcher's home-team PRIOR-year `pf_wOBA` ≤ 33rd-pct of league | 260 / 811 (all yrs) |

`opp_soft` was **NOT** reconstructed — it requires per-start opponent
xwOBA-at-decision-time, the biggest infra cost flagged in the original
deferral note. The POC ships as a **3/4** boom_stack proxy.

**Distribution on 2024 SP panel (n=811):** stack=0: 507 / stack=1: 271 /
stack=2: 32 / stack=3: 1.

### Hold-out test (2024 fold; train = 2018-2023 ex-2020)

| Spec | n_test | 2024 hold-out R² |
|---|---|---|
| 18-feature baseline (existing within-season blend) | 110 | **0.6055** |
| + boom_stack_2024 (4th component skipped) | 110 | **0.6055** |
| Δ R² | | **+0.0000** |

Standardized boom_stack coefficient: +0.0000 (signal entirely absorbed
by the rest of the blend).

### Univariate sanity check

Mean ROS FP per start on the 2024 hold-out by `boom_stack_2024`:

| Stack | n | mean ROS FP/start |
|---|---|---|
| 0 | 43 | 8.66 |
| 1 | 46 | 10.58 |
| 2 | 20 | 11.25 |
| 3 | 1 | 12.08 |

A **+2.6 FP/start spread from stack=0→stack=2** in raw outcomes confirms
boom_stack tracks a real performance gradient — but the gradient is
entirely co-linear with `fp_per_start_to`, `k_pct_to`, and `arche_ovr`
already in the blend, so it adds zero **incremental** predictive R².

## Promotion recommendations

1. **recform_hot — DO NOT PROMOTE to live_blend_xfp.** +0.003 R² at
   split_day=90 (1/3 of the ship bar), partial R² ~0, r=0.69 with
   `fp_per_start_to`. The signal is real but already in the model. The
   builder is retained as panel infrastructure — useful for downstream
   tag work (it powered the boom_stack POC) but it is not a production
   feature.

2. **boom_stack — DO NOT proceed to full multi-year reconstruction
   yet.** The 2024 POC shows the **3-component** proxy adds zero R² on
   top of within-season features. Before investing in the much-harder
   `opp_soft` infrastructure (per-start opponent xwOBA at decision time)
   we should first re-test on data where the within-season blend is
   *weaker* — i.e., the **early-season** split (sd=30 or 45) where
   `fp_per_start_to` has 3-5 starts of noise and an `opp_soft`-anchored
   tag might still carry orthogonal signal. The current POC tests
   boom_stack against its hardest competitor (the full 18-feature blend
   at sd=90, the strongest cutoff). That's the wrong fight.

## Honest assessment vs Agent Y

Agent Y added HIGH-K-ARM + shadow-scout for **+0.055 R²** — these were
**prior-year** features into a **next-year** prediction, so they
operate in an information regime where season-to-date features don't
exist yet. Recform_hot and boom_stack are **same-season** features
competing against the same-season `_to` aggregates. That's a fundamentally
harder lift target, and the 18-feature within-season blend already
sweeps most of the signal these tags carry.

## Followup work (out of scope today)

- Re-test boom_stack at split_day=30 (or pre-season) where within-season
  signal is thinnest — most likely place for incremental lift.
- Build `opp_soft` panel (per-start opponent xwOBA at decision time) —
  the single deferred component. Needs lineup-construction history and
  is multi-week work.
- Consider recform_hot as an **explanatory tag** (display only on
  triangulate cards) rather than a ranker input — its 8.66→11.25
  FP-per-start gradient is intuitive and communicable even if the
  model already uses the underlying signal.

## Files

- `scripts/xfp/build_recform_hot_retroactive.py`
- `scripts/xfp/fit_weight_blend_recform.py`
- `scripts/xfp/build_boom_stack_2024_poc.py`
- `data/research/historical_panel/recform_hot_retroactive.parquet`
- `data/research/validation_runs/weight_blend_recform_2026-06-04.json`

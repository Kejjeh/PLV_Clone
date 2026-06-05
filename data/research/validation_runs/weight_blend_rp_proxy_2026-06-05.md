# RP leverage-proxy weight-blend test — 2026-06-05

**Recommendation: PROPOSE_ADD (CAUTIOUS) — ship `is_proxy_int` segmentation flag; HOLD proxy `pl_rank_mid_inv_combined` as low-confidence diagnostic only.**

The headline +0.124 R² lift PASSES the +0.02 / 5-of-7 bar but post-hoc audit shows the lift is fragile and not what we hoped for. See "Post-hoc audit" at bottom.

## Coverage gained
- Real PL-only RP rows (intersection): **186**
- Union (real PL ∪ leverage proxy): **894**  (+708)
- Rows where proxy is the sole leverage signal: **753**
- Years covered: [2018, 2019, 2021, 2022, 2023, 2024, 2025]

## Proxy construction
For each (mlbam_id, year) with FG IP >= 20:
- `z_gmLI`, `z_ir_inv = 100 - is_pct`, `z_sd_minus_md = shutdowns - meltdowns`, each z-scored within year cohort
- `proxy_value = 0.5*z_gmLI + 0.3*z_ir_inv + 0.2*z_sd_minus_md` (renorm to 0.714/0.286 when IR missing)
- `proxy_rank` = within-year rank by `proxy_value` (1 = best)
- `proxy_pl_rank_mid_inv = 1 / (proxy_rank + 5)` — mirrors runtime transform in `lib/blend_score.py`
- Panel: `data/research/historical_panel/rp_leverage_proxy_panel.parquet` (see build script rows)

## R² lift (LOYO, ex-2020, target = `fp_per_g`)
| setup | features | pooled R² on union rows |
|---|---|---|
| A | baseline (anchor + arche + traj + age) | **0.2907** |
| B | A + real `pl_rank_{early,mid,late}_inv` (NaN-imputed) | 0.301 |
| C | A + `pl_rank_mid_inv_combined` + `is_proxy_int` | **0.4147** |

- **Lift C − A: +0.1239**   95% bootstrap CI [0.0754, 0.1722]
- Lift C − B: +0.1136
- Convergence (years with C>A, ex-2020): **5/7**

## Per-fold lifts (C − A)
| year | n | r2_A | r2_C | lift |
|---|---|---|---|---|
| 2018 | 155 | 0.2675 | 0.2281 | -0.0394 |
| 2019 | 137 | 0.2829 | 0.2213 | -0.0616 |
| 2021 | 21 | -1.0472 | 0.1978 | +1.2450 |
| 2022 | 147 | 0.2394 | 0.4643 | +0.2248 |
| 2023 | 153 | 0.3509 | 0.5572 | +0.2062 |
| 2024 | 139 | 0.3206 | 0.5195 | +0.1989 |
| 2025 | 142 | 0.2481 | 0.4821 | +0.2339 |

## Drop test within C (pooled in-sample ΔR²)
- `pl_rank_mid_inv_combined`: 0.0222
- `is_proxy_int` (proxy-vs-real flag): 0.053
- `anchor_fp` (sanity reference): 0.0154

## Intersection test (does proxy add lift when real PL is already present?)
- Real PL on intersection rows: R² = 0.0445
- Real PL + proxy: R² = 0.0138
- Lift: **-0.0307**

## Recommendation rationale
Threshold to ship: lift ≥ +0.02 AND convergence ≥ 5/7 years.

- Lift hit: YES (+0.1239)
- Convergence hit: YES (5/7)
- **Action:** Propose adding `pl_rank_mid_inv_combined` + `is_proxy_int` to `VALIDATED_WEIGHTS["RP"]["with_pl_or_proxy"]` variant. Cleanup #3 to execute refit + wire into `lib/blend_score.py`.

## Honesty caveats
1. **Selection bias:** middle relievers receive low-leverage opportunities precisely because they have weaker stuff/track record. The proxy partially encodes the same talent signal as `anchor_fp` and `arche_overall_prior`, which inflates drop-test redundancy.
2. **2026 in-progress** excluded from fit (year filter ≤ 2025).
3. **Confidence tier** ('low' for IP < 25 or missing IR) is carried in the panel — downstream consumers should respect it.
4. **No `lib/blend_score.py` edits this PR.** Cleanup #3 owns wiring.

## Post-hoc audit (what the headline lift actually is)

Three findings degrade the +0.124 R² lift below face value:

1. **2018 and 2019 folds are NEGATIVE.** −0.039 and −0.062 lift respectively. The "5/7 convergence" pass relies on 2021–2025 only. 2018–2019 are pre-PL-rank-coverage in the real panel (B≈A there), so C carries them on proxy alone — and proxy alone is worse than baseline in those years. This is meaningful: it says the leverage proxy is not stable as a leading indicator before MLB's high-leverage usage conventions tightened post-2020.

2. **2021 fold lift is degenerate.** n=21 (PL coverage was sparse in 2021), baseline R² = −1.05 (overfit/blow-up on 21 holdout points). The proxy "recovers" to R²=+0.20 mostly by being closer to the year-mean. This single fold contributes ~0.18 to the pooled lift via volume-weighting. Exclude it and pooled lift drops from +0.124 → ~+0.07.

3. **The is_proxy flag does more work than the proxy value.** Drop-test ΔR²:
   - `is_proxy_int` (binary "this row is a non-closer middle reliever"): **0.053**
   - `pl_rank_mid_inv_combined` (the actual leverage signal): 0.022
   - `anchor_fp` (sanity reference): 0.015

   Translation: the model is mostly learning "middle relievers (no PL rank) have systematically different fp_per_g intercepts than closers." That's a useful segmentation insight, but it doesn't validate the gmLI/IR/SD-MD weighted blend as a ranking signal. We could get most of that lift from a binary `is_non_closer` flag without computing gmLI z-scores at all.

4. **Intersection test is NEGATIVE.** On the 186 rows where real PL is available, adding the proxy as an additional feature loses 0.031 R². The proxy is NOT complementary to real PL — it's a (worse) substitute.

### Revised recommendation
- **DO ship** the `is_proxy_int` (or rename `is_non_closer_rp`) binary flag — this captures the segmentation effect honestly without claiming the leverage z-score works.
- **DO NOT ship** `pl_rank_mid_inv_combined` as a ranker for non-closer RPs without an independent test on a held-out cohort. The proxy adds value as "non-closer indicator" but is not a useful leverage rank in its current form.
- Keep `rp_leverage_proxy_panel.parquet` for diagnostic use (display tag candidate: "high-leverage non-closer" for FA RP scouting), but DO NOT use it to override rprs2 rankings.
- Cleanup #3 should test the binary flag separately before wiring the combined feature.

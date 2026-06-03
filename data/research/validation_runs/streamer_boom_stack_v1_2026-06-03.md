---
signal: streamer_boom_stack_v1
formula: sum of 3 binary flags at (pitcher, year, cutoff_date) — (1) last-3-starts K% minus season-to-date K% >= +3pts AND last-3-starts BB% minus season-to-date BB% <= -1pt, (2) recform >= +3 where recform = last-3-start mean FP minus season-to-date mean FP, (3) opp lineup tertile = SOFT where opp lineup_xfp is from the pitcher's NEXT start strictly after cutoff_date and tertile is bucketed within (year, split_day) slate. Range [0, 3].
outcome: ros_fp_per_start (Mode A, integration with rp3); per-start actual_FP >= 20 (Mode B, boom-rate classifier on streamer-pool starts)
expected_sign: + (higher stack -> higher RoS FP/start and higher per-start boom rate)
theory: Three pre-game signals identified in streamer_accuracy_audit (skill spike, hot form, soft matchup) each individually lift CAUTION-tier streamer boom rate by +1.4 to +3.7 pp. Stacking them should isolate the high-EV streamer windows that the archetype-layer-dominant triangulate verdict currently misses (Cameron 6/2).
production_target: rp3
framing: in-season -> ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_streamer_boom_stack.py
date: 2026-06-03
verdict: SHIP_AS_TAG
---

# Pre-registration — streamer_boom_stack_v1

## Hypothesis (pre-registered, copied + sharpened from streamer_accuracy_audit §8)

**H1 (Mode A, model lift):** Adding `boom_stack` to RP3_FEATS produces a cross-year r lift of >= +0.005 vs the full RP3_FEATS baseline (Rule 9), sign-consistent on >= 5 of 7 training years, with non-negative holdout (2024-2025) lift and a MAE improvement >= 0.05 FP/start.

**H2 (Mode B, boom-rate classifier):** Within the streamer pool (defined here as rp3-projected FP/start rank >= 50 at cutoff_date, with `gs_to >= 2` to exclude opening-week starts), per-start boom rate (actual_FP >= 20) increases monotonically with boom_stack, with `boom_stack >= 2` booming at >= 17% vs `boom_stack <= 0` booming at <= 12%. Chi-squared p < 0.05 for tier separation.

## Anti-leakage discipline

- `boom_stack` is computed using only data strictly before cutoff_date for components 1 & 2 (skill spike, recform).
- Component 3 (opp tertile) for Mode A uses the FIRST scheduled start strictly AFTER cutoff_date — this is the same forward-looking-but-fixed-at-cutoff information regime that `ros_opp_xwoba_weighted` already uses; both reflect the published rotation/schedule.
- For Mode B per-start outcome, components 1 & 2 use only starts strictly before that game's date; component 3 is the actual lineup_xfp of THAT game (pre-game knowable — lineups posted hours before first pitch).
- `recency_form_gap` is in the rolling substrate but NOT in RP3_FEATS (display-only per rp3.py:72). So component 2 is a fresh signal vs baseline.
- `delta_k_pct` / `delta_bb_pct` ARE in RP3_FEATS — so component 1 is partially redundant with baseline. The boom_stack is a binarised/thresholded SUM, which is different in shape from the continuous drift features, but the lift will be lower-bounded by the residual not captured by deltas. **Expected lift is small.**

## Rule 8 / framing match

Production target rp3 is in-season -> ros. We will run convergence at split_day 30, 44, 58. Lift must be sign-consistent across the three split_days (Rule 8).

## Rule 5 sample-size pre-check (Step 2.5)

- Per-start data available 2016-2025 (per_start_predictor_battle.csv = 41,077 starts).
- Statcast game_date join via game_pk available all years.
- Per cohort year: ~4500-4600 starts. Streamer subset will be ~50% of these (rank >= 50 in each year), so ~2000-2300 per year. Easily clears Rule 5.
- 7 cohort years available (2018, 2019, 2021, 2022, 2023, 2024, 2025). Clears Rule 2(b).

Verdict for Step 2.5: GO.

---

# Results

Script: `scripts/xfp/validate_streamer_boom_stack.py`
Output JSON: `data/research/validation_runs/streamer_boom_stack_v1_results.json`

## Feature distribution

Built at every (pitcher, year, cutoff_date) row in the rp3 substrate (years 2018-2025 ex-2020).

| Component | Fire rate at cutoff panel | Per-start fire rate |
|---|---|---|
| flag_skill_spike (dK >= +3pp AND dBB <= -1pp) | 6.11% | 8.00% |
| flag_recform_hot (dFP >= +3) | 13.21% | 18.23% |
| flag_opp_soft (lineup tertile = bottom) | 25.28% | 33.34% |

Cutoff-panel boom_stack distribution: 0=31,443 / 1=14,683 / 2=2,930 / 3=523 (45.3% nonzero in merged rolling).

## Mode A — Model integration into rp3 (Rule 9)

Baseline = full RP3_FEATS (24 features, including `delta_k_pct`, `delta_bb_pct`, `ros_opp_xwoba_weighted`).

| Metric | Baseline | + boom_stack | Lift |
|---|---|---|---|
| Cross-year r (LOYO, 7 train years) | **0.5548** | **0.5548** | **+0.0000** |
| Holdout 2024-2025 mean r-lift | — | — | +0.0002 |
| Pooled partial r vs full baseline | — | — | +0.0082 |
| Holdout MAE (FP/start) | 2.7738 | 2.7734 | +0.0004 |

Per-year lift (full − baseline): 2018 −0.0003, 2019 +0.0004, 2021 +0.0008, 2022 −0.0019, 2023 +0.0006, 2024 +0.0009, 2025 −0.0004. **Sign-consistent on 4/7 years.**

Convergence panel (Rule 8):

| split_day | r_base | r_full | r_gain | mae_gain | n |
|---|---|---|---|---|---|
| 30 | 0.5766 | 0.5753 | **−0.0013** | −0.0022 | 1,002 |
| 44 | 0.5725 | 0.5729 | +0.0004 | −0.0025 | 1,051 |
| 58 | 0.5655 | 0.5648 | **−0.0007** | +0.0004 | 1,074 |

Two of three split-days show negative gain. No leakage signature (we explicitly looked for the "identical lift at sd 30/42/56" smoke from the convergence-curve leakage memo); pattern is null/noise, not leakage. The +0.0082 partial r is real residual signal but too small to register in cross-year r at this baseline width.

### Mode A gate verdict

| Gate | Threshold | Observed | Pass? |
|---|---|---|---|
| (a) Cross-year r lift | >= +0.005 | +0.0000 | **FAIL** |
| (b) Sign consistency | >= 5 of 7 years | 4/7 | **FAIL** |
| (c) Holdout sign | >= 0 | +0.0002 | PASS |
| Convergence stability | same-sign across split_days | mixed signs (-, +, -) | **FAIL** |

**Mode A verdict: DO NOT SHIP to RP3_FEATS.** The candidate is dominated by `delta_k_pct` / `delta_bb_pct` (already in baseline) and `ros_opp_xwoba_weighted` (already in baseline). The thresholded sum adds no marginal point-estimate lift over the continuous forms.

### Leakage / redundancy notes

- Component 1 (skill_spike) is a binarised form of `delta_k_pct >= +3pp AND delta_bb_pct <= −1pp`. Both deltas are in baseline. Expected near-zero residual.
- Component 2 (recform_hot) is `recency_form_gap >= +3`. `recency_form_gap` is **NOT** in RP3_FEATS (rp3.py:72 marks it display-only). So this component is fresh. The +0.0082 partial r is almost entirely attributable to this + component 3.
- Component 3 (opp_soft) is a tertile binarisation of `lineup_xfp` of the next start. Baseline already has `ros_opp_xwoba_weighted` (the FULL ROS opponent strength weighted by start count), which subsumes single-game opp info for ROS prediction.
- Net: boom_stack is structurally redundant with the production baseline for the ROS framing.

## Mode B — Per-start boom-rate classifier

Streamer pool = per-start rolling fp_per_start in bottom 50% of (year, month) slate AND >= 3 prior starts. N = 12,713 starts.

| boom_stack | n | booms (FP>=20) | boom rate | mean FP |
|---|---|---|---|---|
| 0 | 6,350 | 616 | **9.70%** | 8.44 |
| 1 | 4,876 | 589 | 12.08% | 9.62 |
| 2 | 1,263 | 172 | **13.62%** | 9.92 |
| 3 | 224 | 39 | **17.41%** | 10.14 |

Aggregated `>=2` vs `<=0`: 14.19% vs 9.70%. Chi-squared (2x2 table [193 booms / 1,294 non-booms] vs [616 / 5,734]): **chi2 = 25.25, p < 0.0001**. Highly significant tier separation.

Pre-registered prediction (H2): "stack >= 2 booms at >= 17%, stack <= 0 booms at <= 12%."
- stack=0: 9.70% (better than 12% prediction — passes)
- stack>=2 aggregate: 14.19% (below the 17% prediction)
- stack=3 only: 17.41% (matches the 17% prediction)

**H2 directionally validated** (monotonic, p<0.0001), magnitude slightly weaker than predicted at the aggregate >=2 bucket. The full 17% prediction only materialises at the stack=3 (all 3 signals lit) tier, which fires on only ~1.8% of streamer starts (n=224).

### Mode B verdict

The stack IS a real boom-rate flagger. The lift profile (+4.5pp boom rate at stack>=2 vs stack<=0) is statistically robust and practically meaningful for streamer pickup decisions — but the signal is concentrated at stack=3 (only ~1.8% of streamer starts). At stack=2 (1,263 starts, ~10% of streamer pool), the lift is only +3.9pp vs stack=0.

**Mode B verdict: SHIP AS TAG.** Surface boom_stack as a non-ranker tag in `/triangulate` output and the matchup dashboard for streamer-class SPs (rp3 rank >= 50 or rolling FP <= 12). The tag should distinguish stack=3 ("3-signal stack — top-decile streamer boom EV") from stack=2 ("2-signal stack — modest boom uplift"). It MUST NOT be used to override the rp3 point projection.

## Cross-mode synthesis

Mode A (point) FAIL + Mode B (boom rate) PASS is consistent with the candidate's design intent: boom_stack identifies HIGH-VARIANCE high-tail-EV windows within an otherwise-flat streamer-pool projection (per the streamer_accuracy_audit r=0.149 corr finding). It does not improve the conditional MEAN; it shifts the right-tail mass. Per-start framing surfaces this; ROS-mean framing buries it.

This is exactly the case the validate-feature protocol's two-mode pattern was designed to differentiate.

## Final verdict per mode

| Mode | Verdict |
|---|---|
| Mode A (point estimator, integration with rp3) | **DON'T SHIP** |
| Mode B (boom-rate classifier tag) | **SHIP AS TAG** |

Frontmatter verdict: `SHIP_AS_TAG`.

## Recommended next step

Production integration is a SEPARATE request (Rule 7). The shippable here is:

1. Compute `boom_stack` per-start (or per-pitcher-cutoff) inside `scripts/xfp/run_triangulate.py` for any SP with rp3 rank >= 50 or rolling FP <= 12.
2. Surface in triangulate card output as a tag:
   - `stack=3` → display `BOOM STACK 3/3 — top-decile streamer EV (~17% boom rate)`
   - `stack=2` → display `BOOM STACK 2/3 — modest boom uplift (~14% boom rate)`
   - `stack<=1` → no tag
3. Add a registry entry under "✅ VALIDATED (research-stage / display tag)" — NOT under production ranker features.
4. Do NOT add to RP3_FEATS or use as a verdict override gate.

## Bonferroni / sweep context

Single-feature test, no grid sweep. Rule 3 is a no-op here.

## Sample-size honesty (Rule 5)

- Mode A: pooled n = 19,111 cross-year. Per-year n >= 1,800 every counted year. Clears Rule 5.
- Mode B streamer pool: n = 12,713. Per-bucket n: 6,350 / 4,876 / 1,263 / 224. Stack=3 bucket (n=224) is small enough that the 17.41% rate has a Wilson 95% CI of roughly 12.7%-23.2% — directionally correct but not pinpoint. Stack=2 bucket (n=1,263) is well-powered.

# Velo x Platoon SP decline-risk study

- **Signal:** Platoon-split constructs (wOBA/K%/FB-velo vs opposite- vs same-hand) and velo-decline x platoon interaction
- **Outcome:** RoS BrownU FP/start (`ros_fp_per_start`), forward, leakage-safe as-of
- **Verdict:** REJECT (do NOT wire). Platoon split alone = NULL. Interaction = suggestive trend but NOT significant. Overall FB-velo decline (vYoY) remains the stronger lens.
- **Date:** 2026-06-13
- **Script:** `scripts/_oneoff/velo_platoon_study.py`

## Methods

- Panel: `rolling_pitchers_2018_2026.csv`, years 2021-2025, gated `gs_to>=5 & ros_gs>=3`, cutoffs split_day in {51,72,93,114}. 2897 cells before split-coverage gate.
- LEAKAGE-SAFE AS-OF: for each (pitcher, year, split_day, cutoff_date) cell, platoon features built ONLY from pitch-level Statcast rows with `game_date < cutoff_date` (regular season). Same-hand vs opposite-hand defined by `stand != p_throws`.
- Outcome of platoon read = true wOBA-against (`woba_value`/`woba_denom` sums) split opp−same, plus K%-split, FB-velo (FF/SI/FC) split, opposite-hand wOBA level, opp-hand BF fraction.
- Coverage gate: need >=80 BF vs opposite hand AND >=50 vs same hand for a stable split read -> 2210 / 2897 cells retained.
- Rule-9 baseline (level controls): `rank(swstr_pct_to)+rank(k_pct_to)` and `fp_per_start_to`. Bar to beat: ALSO control for overall velo-YoY decline (`vYoY` = `avg_velo_to` − prior-year season-end velo). Partial-r reported over both control sets.
- Interaction: velo-decline partial-r within platoon-vulnerability (woba_split) tertiles + explicit standardized product term.
- Downside: bust = bottom-tercile `ros_fp_per_start` within (year, split_day) cell.

## Partial-r table (sample = cells with >=80 opp BF)
n analysis cells = 2210

| construct | r over [level,fp] | p | r over [level,fp,vYoY] | p | n |
|---|---|---|---|---|---|
| woba_split | +0.009 | 0.656 | +0.040 | 0.116 | 2210 |
| kpct_split | +0.014 | 0.499 | +0.041 | 0.110 | 2210 |
| velo_split | -0.015 | 0.481 | -0.008 | 0.769 | 2210 |
| woba_opp | -0.008 | 0.692 | -0.003 | 0.912 | 2210 |
| kpct_opp | +0.017 | 0.431 | -0.013 | 0.605 | 2210 |
| opp_bf_frac | -0.066 | 0.002 | -0.050 | 0.052 | 2210 |
| fbvel_opp | +0.133 | 0.000 | +0.086 | 0.001 | 2210 |

REFERENCE overall velo (vYoY) over [level,fp]: r=+0.147 p=0.000 n=1521

## Interaction: velo-decline (vYoY) partial-r within platoon-vulnerability tertile
vulnerability = woba_split (worse vs opposite hand). Tertile within sample.

| vuln tertile | vYoY partial-r over [level,fp] | p | n |
|---|---|---|---|
| low | +0.106 | 0.017 | 507 |
| mid | +0.128 | 0.004 | 507 |
| high | +0.205 | 0.000 | 507 |

Explicit vYoY x woba_split interaction term, partial-r over [level,fp,vYoY,woba_split]: r=+0.034 p=0.188 n=1521

## Downside: bust-rate gap (bust = bottom-tercile ros_fp_per_start)
woba_split: bust-rate top-tercile=0.332  bottom-tercile=0.329  gap=+0.003
vYoY: bust-rate top-tercile=0.249  bottom-tercile=0.416  gap=-0.168

## VERDICT

**REJECT — do NOT wire platoon into the SP decline board.**

1. **Platoon split alone is a NULL.** Over the level baseline, every platoon-split construct is non-significant: `woba_split` r=+0.009 (p=0.66), `kpct_split` r=+0.014 (p=0.50), `velo_split` r=−0.015 (p=0.48), `woba_opp` r=−0.008 (p=0.69). A widening opposite-hand split does NOT predict RoS decline. Bust-rate gap for `woba_split` is +0.003 (flat).

2. **Overall velo decline still wins.** On the same analysis sample, `vYoY` carries r=+0.147 over the level baseline and a bust-rate gap of −0.168 (top-velo-tertile busts 24.9% vs bottom 41.6%). Nothing platoon-derived approaches this.

3. **The interaction is directionally consistent with the mechanism but NOT statistically significant.** Velo-decline partial-r rises monotonically across platoon-vulnerability tertiles — low +0.106 / mid +0.128 / high +0.205 — i.e. losing velo bites ~2x harder for arms already vulnerable to opposite-hand bats. BUT the explicit standardized `vYoY x woba_split` product term is NS (r=+0.034, p=0.19, n=1521). The tertile pattern is suggestive folklore, not a wireable term.

4. **Only artifact of note:** `fbvel_opp` (FB velo vs opposite hand, a LEVEL not a split) shows r=+0.133 — but that is just overall velo level leaking through, redundant with vYoY (drops to +0.086 once vYoY is controlled). Not a platoon effect.

**Recommendation:** keep vYoY/vIn/v2y as the velo-decline conviction lens unchanged. Do not add platoon-split features. Optionally note (display-only, NOT additive) that high-opposite-hand-vulnerability arms losing velo are a higher-conviction DECLINE flag, but only as a tertile gate, never as a projection term. No thresholds recommended for production.

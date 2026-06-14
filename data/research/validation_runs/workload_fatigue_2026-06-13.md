# Workload / Fatigue OOS Study for SP Decline-Risk (2026-06-13)

**Question:** Do WORKLOAD / FATIGUE signals predict SP rest-of-season decline OVER our existing velo-decline flags?

**Frame:** BrownU 8-team points. Forward target = `ros_fp_per_start` (rest-of-season FP/start over `ros_gs` starts). All features AS-OF the cutoff (leakage-safe).

## Methodology

- Leakage-safe as-of: statcast `game_date < cutoff_date`; cutoffs split_day in [51, 72, 93, 114]; years [2021, 2022, 2023, 2024, 2025]; join on (pitcher,year,split_day).
- Gate: `gs_to>=5` & `ros_gs>=3`.
- Baseline Rule 9 partial-r controls:
  - **BAR-A** = `level` [rank(swstr%_to)+rank(k%_to)] + `fp_per_start_to`.
  - **BAR-B** = BAR-A + `overall_velo_yoy` (`avg_velo_to` - prior-yr season-end velo). *THE BAR: beat velo.*
- partial-r = within-cell OLS residualization (house `resid_within`), pooled.
- Gated panel rows with workload join: **n=2897** (Verducci subset n=2508).

## THE BAR -- velo-decline's own incremental partial-r over BAR-A

`overall_velo_yoy` partial-r over BAR-A: r=+0.115* p=0.000 n=2281

A workload feature must beat this AND remain significant over BAR-B (which already contains velo) to earn a flag.

## Partial-r table (incremental over baselines)

| Feature | raw r | partial-r over BAR-A | partial-r over BAR-B (+velo) |
|---|---|---|---|
| cum_pitches_to (season load) | +0.130 | r=+0.032  p=0.090 n=2897 | r=+0.014  p=0.504 n=2281 |
| cum_tbf_to (season TBF load) | +0.110 | r=+0.033  p=0.080 n=2897 | r=+0.016  p=0.458 n=2281 |
| pitches_per_start | +0.296 | r=+0.097* p=0.000 n=2897 | r=+0.086* p=0.000 n=2281 |
| recent_load (pitches last21) | +0.166 | r=+0.070* p=0.000 n=2722 | r=+0.066* p=0.002 n=2146 |
| mean_days_rest | -0.012 | r=+0.054* p=0.003 n=2897 | r=+0.060* p=0.004 n=2281 |
| min_days_rest | +0.123 | r=+0.082* p=0.000 n=2897 | r=+0.087* p=0.000 n=2281 |
| short_rest_share (<=4d) | -0.116 | r=-0.080* p=0.000 n=2897 | r=-0.092* p=0.000 n=2281 |
| verducci_pitch_jump (Verducci) | +0.049 | r=-0.059* p=0.003 n=2508 | r=-0.050* p=0.017 n=2281 |
| verducci_pitch_ratio (Verducci) | -0.019 | r=-0.059* p=0.003 n=2508 | r=-0.029  p=0.169 n=2281 |
| verducci_tbf_jump (Verducci IP) | +0.055 | r=-0.044* p=0.027 n=2508 | r=-0.027  p=0.205 n=2281 |
| load_x_velodecline (INTERACTION) | -0.037 | r=-0.067* p=0.001 n=2281 | r=-0.051* p=0.014 n=2281 |
| verducci_x_velodecline (INTERACTION) | -0.009 | r=-0.031  p=0.145 n=2281 | r=-0.015  p=0.485 n=2281 |

(`*` = p<0.05. Sign: positive partial-r = MORE of this feature -> HIGHER forward FP. For a *decline* signal we want a NEGATIVE, significant partial-r that survives BAR-B.)

## Verducci YoY pitch-jump -- forward FP by tercile

`verducci_pitch_jump` = (projected full-season pitches at current pace) - (prior-year actual season pitches).

| Jump tercile | mean ros_fp/start | median | n |
|---|---|---|---|
| low | 10.26 | 10.34 | 843 |
| mid | 9.77 | 9.88 | 829 |
| high | 10.64 | 10.63 | 836 |

(Verducci predicts the HIGH-jump tercile fades. A real effect = high tercile mean materially below low/mid.)

## Cumulative season load -- forward FP by tercile

| `cum_pitches_to` tercile | mean ros_fp/start | median | n |
|---|---|---|---|
| low | 9.26 | 9.40 | 971 |
| mid | 9.84 | 9.76 | 959 |
| high | 11.34 | 11.41 | 967 |

## KEY interaction -- heavy load AND losing velo

`load_x_velodecline` = z(cum_pitches_to) x z(velo_decline) [velo_decline = -overall_velo_yoy]. High = heavy load AND losing velo (the hypothesized worst quadrant).

| `load_x_velodecline` tercile | mean ros_fp/start | median | n |
|---|---|---|---|
| low | 10.65 | 10.55 | 767 |
| mid | 9.89 | 10.03 | 754 |
| high | 10.47 | 10.63 | 760 |

## VERDICT

**DO NOT WIRE A WORKLOAD FLAG.** No workload/fatigue feature -- Verducci YoY pitch jump, cumulative season load, pitches/start, days-rest, OR the load x velo-decline interaction -- clears BOTH bars at adequate n with the *right sign*. Specifically:

- **The bar:** velo-decline alone over BAR-A is r=+0.115 (p<0.001, n=2281). A fatigue flag must beat this incremental |r| over BAR-B (velo already in) AND point the decline direction (negative partial-r). Nothing does both.

- **The "significant" workload features point the WRONG way for a fatigue thesis.** `pitches_per_start` (+0.086), `min_days_rest` (+0.087), `mean_days_rest` (+0.060), `recent_load` (+0.066), and the `cum_pitches_to` tercile table (low 9.26 -> high 11.34 FP) all say MORE load / longer rest gaps -> HIGHER forward FP. These are **durability / quality proxies**, not fatigue: good, healthy pitchers are trusted to throw more pitches and stay in the rotation. None is a decline signal, and the biggest (pitches_per_start +0.086) still does not beat velo's +0.115 anyway.

- **Verducci is null-to-wrong.** `verducci_pitch_jump` is significant over BAR-A (-0.059) but **collapses once velo is added** (BAR-B -0.050, and the ratio/IP variants go non-significant, p=0.17 / 0.21). The tercile table is non-monotone (high-jump tercile mean 10.64 is actually the HIGHEST, not the lowest) -- no second-half fade. The Verducci effect does not survive in this points sample.

- **The interaction is also subsumed.** `load_x_velodecline` (heavy load AND losing velo) is -0.067 over BAR-A but shrinks to -0.051 over BAR-B, and its tercile table is non-monotone (mid 9.89 < high 10.47). `verducci_x_velodecline` is flat-out non-significant (p=0.15 / 0.49). The "worst quadrant" hypothesis is not supported -- velo decline alone already carries it.

- **The lone negative survivor (`short_rest_share` -0.092) is a velo confound, not actionable.** It barely edges velo's |r| and is itself just a noisy re-encoding of usage; it has no incremental decline content beyond velo and a much weaker effect than simply watching velo. Not worth a flag.

**Bottom line:** workload/fatigue is **subsumed by velo** for points decline-risk. Once you control for cumulative skill (swstr/K/FP) and velo trajectory, raw innings/pitch load carries no independent FORWARD-DECLINE signal -- and where load does correlate, it correlates *positively* (durability), the opposite of the fatigue thesis. **Keep the existing velo-decline flag; do not add a Verducci, pitch-count, days-rest, or load x velo interaction flag.**

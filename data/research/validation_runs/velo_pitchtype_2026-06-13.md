---
signal: per-pitch-type velocity decline (SP decline-risk board)
outcome: ros_fp_per_start (BrownU FP/start over post-cutoff starts)
verdict: NULL — no pitch-type cut beats overall-velo decline
date: 2026-06-13
script: scripts/_oneoff/velo_pitchtype_study.py
---

# Per-pitch-type velo decline vs overall-velo decline — leakage-safe OOS study

## Methods

- Panel: `rolling_pitchers_2018_2026.csv`, cohort gate gs_to>=5 & ros_gs>=3, years [2021, 2022, 2023, 2024, 2025], cutoffs split_day [51, 72, 93, 114] (~4/season).
- Leakage-safe AS-OF: per cell, pitch-type velo computed only from pitches with `game_date < cutoff_date`; per-type min 30 pitches.
- YoY deltas = current as-of per-type velo minus PRIOR full-season per-type velo.
- Baseline (Rule 9): `level = rank(swstr_pct_to)+rank(k_pct_to)`, `fp_base = fp_per_start_to`.
- Two bars: partial-r over [level, fp_base]; and the REAL bar partial-r ALSO over the overall all-pitch velo YoY delta.
- Bust gap = bust-rate(worst/most-decline tercile) − bust-rate(best tercile); bust = bottom-tercile ros within (year,split_day).
- Sign convention: positive partial-r means higher velo (less decline) → higher fwd FP, i.e. velo decline is bad. Positive bust gap means the declining tercile busts more.

## Partial-r table

| Construct | partial-r over level+FP | partial-r ALSO over overall-velo | bust gap (worst−best) | n |
|---|---|---|---|---|
| FB-group velo YoY (FF/SI/FC) | +0.097 | +0.031 | +0.144 | 2601 |
| FF (4-seam) velo YoY | +0.102 | +0.058 | +0.117 | 2290 |
| SI (sinker) velo YoY | +0.128 | +0.040 | +0.156 | 1474 |
| Primary-pitch velo YoY | +0.081 | +0.008 | +0.128 | 2510 |
| SL (slider) velo YoY | +0.117 | +0.067 | +0.122 | 1414 |
| CH (change) velo YoY | +0.041 | -0.022 | +0.042 | 1724 |
| Offspeed-group velo YoY | +0.005 | -0.062 | +0.040 | 2484 |
| FB-vs-offspeed SEPARATION erosion | +0.057 | +0.072 | +0.057 | 2484 |
| [REF] Overall all-pitch velo YoY | +0.104 | n/a | +0.105 | 2601 |

Merged panel rows: **2897**. Overall-velo YoY reference partial-r over level+FP = **+0.104**.

## Verdict

**NULL RESULT (with two near-miss caveats).** No per-pitch-type velo cut adds incremental OOS partial-r over BOTH the level baseline AND the overall all-pitch velo YoY delta AT ADEQUATE COVERAGE (n>=2000). Per the team lens rule, a feature only wins if it beats BOTH bars; none do. Keep the existing overall-velo constructs (vYoY / vIn / v2y); do NOT add a per-pitch-type velo flag as the headline.

Two slices flirt with the bar but fail honesty checks:
- **SL (slider) velo YoY**: raw +0.117 (> overall +0.104) and marginal-over-overall +0.067 — passes both partial-r bars, BUT only on n=1414 (≈half coverage: requires both a 2026-as-of slider sample and a prior-year slider sample). It is a self-selected subset of slider-heavy arms, not a roster-wide flag. SI is the same story (n=1474). REJECTED on coverage.
- **FB-vs-offspeed SEPARATION erosion**: has the single highest marginal-over-overall partial-r (+0.072) at full coverage (n=2484), meaning it carries information overall-velo YoY does NOT. BUT its RAW partial-r (+0.057) is well BELOW overall velo (+0.104) — it loses the first bar. It is a complement, not a replacement.
- **FB-group / FF YoY**: essentially re-express overall velo (collinear, FBs dominate mix); marginal partial-r collapses to +0.031 / +0.058. Offspeed-group and CH YoY go NEGATIVE once overall velo is controlled — seductive-but-null, rejected.

### Honesty notes
- Per-pitch slices suffer coverage loss (per-type 30-pitch gate + prior-year per-type 50-pitch gate) vs the overall mean, which is always available — fewer n, more noise.
- FB-group YoY is the closest competitor but is highly collinear with overall-velo YoY (FBs dominate pitch mix), so its marginal partial-r over overall velo is the honest test it must pass.
- Secondary-pitch (SL/CH/offspeed) velo YoY is the noisiest and least predictive — rejected as seductive-but-null.
# Reliever Role-Aware Fantasy Scoring — Future Work

## What is missing

The current pitcher fantasy layer computes `fp_per_ip` from calibrated rate models
(K, BB, H, ER) and assigns a flat `fp_per_app = fp_per_ip × 1.0` for all relievers.

**Saves (SV) and Holds (HD) are not included.** With your scoring (SV = +5, HD = +3),
role-dependent context is a major source of reliever fantasy value:

| Role | Typical SV/HD rate | FP/app from role alone |
|------|-------------------|------------------------|
| Closer | ~0.15 SV/app | +0.75/app |
| Setup/hold | ~0.25 HD/app | +0.75/app |
| Other RP | ~0.05 HD/app | +0.15/app |

A closer with `fp_per_app = 2.5` + `0.75 SV` = `3.25/app` total — a 30% upward
adjustment that is entirely invisible to the current output.

The current `sv_upside` / `hd_upside` columns are note strings (e.g., "+5/save
(role-dependent)"), not numeric estimates. They are placeholders, not projections.

---

## Root cause

Role assignment (closer, setup, other) requires knowing:
- Leverage index or save-situation appearance rate
- Official save/hold outcomes per appearance (not available in Statcast pitch data)
- Roster/usage context (team bullpen structure)

None of these are captured by PLV or pitch-quality metrics. A 7.5 PLV reliever could be
a closer, a setup man, or a mop-up arm. PLV tells you the quality of the innings — not
when or why they appear.

---

## What would be needed later

### Data source
- `savant_game_logs` or `pybaseball.pitching_stats_bref()` for actual SV/HD/BS totals
  per pitcher per season
- This is a separate, result-based data source from the pitch-quality model stack

### Role classifier
- Classify each RP pitcher into: Closer / Setup / High-leverage / Bulk / Mop-up
- Input features: avg leverage index (if available), SV rate, HD rate, appearance rate
  in close-game situations
- A simple threshold classifier (SV rate > 0.10 → Closer, HD rate > 0.15 → Setup)
  may be sufficient

### Integration point
- After `pitcher_points.project()`, add a separate `_add_role_upside()` step
- Merge in role classification from the result-based data
- Compute `sv_fp_per_app = sv_rate × scoring.sv` and `hd_fp_per_app = hd_rate × scoring.hd`
- Add `total_fp_per_app = fp_per_app + sv_fp_per_app + hd_fp_per_app`

### Calibration approach
- Role rates can be estimated empirically: mean SV/app and HD/app for each role tier
  from 2-3 seasons of data
- These are very stable (role-based, not skill-based), so simple means are sufficient
- Re-estimate annually as bullpen structures evolve

---

## Current workaround

Manually add SV/HD to fp_per_app from your league platform's role assignments:

```
adjusted_fp_per_app = fp_per_app + (sv_rate × 5) + (hd_rate × 3)
```

Closer example: `2.5 + (0.15 × 5) + (0 × 3) = 3.25/app`
Setup example:  `2.2 + (0 × 5) + (0.25 × 3) = 2.95/app`

Use `est_k_per_ip` and `fp_per_ip` as the quality signal, and overlay role context
from your league platform.

---

## Priority

Low. The most actionable reliever fantasy signal is already present: K/IP rankings
correctly identify high-strikeout relievers regardless of role. Role context is
best handled by the fantasy manager directly given their knowledge of team situations.

Build this when you want to:
1. Automate RP rankings that include role context
2. Identify relievers with elite K/IP who are in line for save opportunities
3. Model save probability from team performance (a larger project)

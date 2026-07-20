---
signal: sb_takeoff_rate
formula: per (batter-as-RUNNER, year, split_day) — takeoff_rate = goes / opportunities over PAs with game_date <= cutoff, where opportunity = PA whose first pitch has this runner on 1B with 2B open, and go = (runner appears on 2B/3B at a later pitch of the same PA) OR (runner absent from all bases at the PA's last pitch, multi-pitch PA) OR (caught_stealing_2b event in the PA); k=15 shrinkage toward the as-of population rate
outcome: ros_full_fp_per_pa (rh3 harness target)
expected_sign: "+"
theory: post-2023 bigger-bases regime rewards attempt PROPENSITY; takeoff rate normalizes by opportunity (times on 1B with 2B open) which raw sb_per_pa cannot, and attempt behavior is stickier than SB counts
production_target: rh3
framing: in-season → ros (all split_days)
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_sb_takeoff_rate.py
date: 2026-07-19
verdict: REJECTED
---

## RESULT (2026-07-19): Dr -0.0001, 1/7 years, holdout 0/2, coef WRONG sign.
Measurement itself verified excellent (league takeoff 10.5%; Elly 0.45 #1, PCA 0.40,
catchers/Pasquantino ~0; the GroupBy.first() NaN-skip footgun was caught in sanity —
it backfills mid-PA steal arrivals into the PA-start state and silently excludes
steal PAs from the opportunity set). The FEATURE dies to the declared absorber:
sb_per_pa_to_sh + Marcel prior span attempt propensity (sprint_speed precedent).
SB axis for rh3 now fully closed (physical + behavioral forms both rejected).

## Cell (campaign ledger 3A; single cell, no sweep)

`sb_takeoff_rate_to_sh` vs full RH3_FEATS (which contains `sb_per_pa_to_sh` — the
declared absorber). No green-light-index or catcher-matchup variants (would be
forking paths; not declared).

## Measurement caveat (pre-declared)

"Goes" from base-state transitions includes advances via WP/PB/balk (not true
attempts) and pickoffs (aggressive-lead proxy, kept intentionally). Contamination
is runner-independent to first order and shrinks toward noise, not bias, in the
cross-sectional ranking. True SB events are not row-marked in statcast mid-PA;
this proxy avoids a ~5h/season MLB-API PBP pull. Sanity gate before harness:
league takeoff rate in a plausible band and known burners (Elly De La Cruz-type)
rank top / station-to-station sluggers bottom in 2024.

## Priors (pre-declared, pessimistic)

sprint_speed was REJECTED for rh3 (2026-07-09) with the note "Marcel prior + shrunk
SB rate already span it; SB is a small share of FP/PA variance." Takeoff rate is
behavioral rather than physical, but the same absorber applies. The 2023+ regime
interaction is NOT testable multi-year yet (partial-FUTURE); this run tests the
attempt-rate MAIN effect on 2018-2025.

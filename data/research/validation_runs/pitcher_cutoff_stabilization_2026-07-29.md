---
signal: pitcher_cutoff_stabilization (measurement study, SP + RP)
formula: >
  Forward reliability r(metric_to at denominator-size bucket,
  metric_rest_of_season) across pitcher-snapshots, rest = multiyr season
  count minus rolling _to count (same year). Empirical cutoff = interpolated
  denominator where forward r crosses 0.50 / 0.70. Velocity handled as a
  pitch-weighted average (rest_avg = (season_p*avg_season - to_p*avg_to)/rest_p).
outcome: same-metric rest-of-season value (measurement reliability, not FP)
expected_sign: + by construction
theory: Hitter-side study (2026-07-29) replaced hand-picked minimums with
  empirical ones; SP/RP form lenses (/sp-form, /fa-monitor velo signals,
  pitcher_sustainability) still run on hand-picked windows. Same method,
  pitcher side.
production_target: research-only
framing: in-season measurement
holdout_years: n/a (measurement study, no promotion decision)
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025] ex 2020
validation_script: scripts/xfp/validate_cutoff_stabilization_pitchers.py
date: 2026-07-29
---

# Pitcher-side empirical cutoffs — pre-registration

SP metrics (rolling_pitchers_2018_2026 x sp_multiyr_2015_2025, join <= 2025):
chase, zswing, whiff, swstr, csw, k_pct(tbf), bb_pct(tbf), hard_hit(bip),
barrel(bip), gb(bip), woba_against (woba_v_sum/woba_d_sum), hr_rate(tbf),
velo (pitch-weighted avg).

RP metrics (rolling_relievers x relievers_multiyr): chase, zswing, whiff,
swstr, csw, k_pct, bb_pct, woba_against, velo (RP caches lack
hard-hit/barrel/gb/hr counts — reported as NOT MEASURABLE, not skipped
silently).

Bucket floors and rest-window floors mirror the hitter study (>=200
snapshots per bucket; rest >= 200 pitches / 40 TBF / 30 BIP). Deliverable:
canonical minimums table (r>=0.50 ceil 25) for the registry; no
promotion decision attaches to this study.

## RESULT (2026-07-29 — SP 26,958 snapshots, RP 42,978)

| metric | SP min (r=.50) | SP r=.70 | RP min (r=.50) | RP r=.70 |
|---|---|---|---|---|
| **velo** | **150 pitches** (r=.90 at first bucket) | 150 | **150** (r=.93) | 150 |
| whiff | **150 pitches** | 651 | **150** | never |
| swstr | **175** | 744 | **200** | 903 |
| zswing | **275** | never | **150** | never |
| csw | **425** | never | **425** | never |
| k_pct | **100 TBF** (~4 starts) | never | **125 TBF** | never |
| gb | **50 BIP** | never | n/a (no counts) | — |
| woba_against | **525 TBF** (≈ full season) | never | NEVER | — |
| chase | **NEVER** | never | NEVER | — |
| bb_pct | **NEVER** | never | NEVER | — |
| hard_hit / barrel / hr_rate | **NEVER** (against) | never | n/a | — |

Headline findings:
1. **Velocity is in a class of its own** — r≈0.90-0.96 from the very first
   bucket (~1-2 SP starts / ~10 RP appearances). Empirically ratifies the
   FB-velo spine of /fa-monitor, /trending and the stuff_command lens.
2. **Pitcher BB% and chase NEVER stabilize in-window** — stronger than the
   hitter result. Any mid-season "his control/command improved" or "he's
   getting more chases" read is noise by construction. Ratifies gotcha #11's
   "watch an arm's STUFF, not its walks" with measurement math.
3. **Contact-quality-AGAINST (hard-hit/barrel/HR-rate) never stabilizes**
   for SPs — classic DIPS, reproduced on our own data. The /sp-board HR/9
   structural lens (2026 vs career) sits on a never-stabilizing in-season
   numerator; usable only because it compares to CAREER, and should never
   be read from a window shorter than the season.
4. gb% is the fastest-stabilizing batted-ball trait (50 BIP, ~2 starts).
5. SwStr/whiff legit at ~150-200 pitches; K% needs ~4 SP starts (100 TBF).

Status: measurement study, research-only; minimums adopted as canonical
gates for pitcher window/lens work alongside the hitter table.

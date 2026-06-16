---
signal: early_season_bat_speed
formula: mean(statcast.bat_speed | bat_speed>10) over [season_start, cutoff) per batter; change = early_mean − prior_year_full_season_mean. Computed from raw statcast_{year}.parquet via exact game_date split (no leaderboard date-param ambiguity).
outcome: rest-of-season xwOBACON (primary; more stable target) and RoS wOBA/PA (secondary)
expected_sign: +
theory: Bat speed stabilizes in ~20 swings (~2 games) vs 6-12 weeks for outcome rates, so early in a season it is a reliable physical "getting better/worse" read while the box score is still noise.
production_target: research-only
framing: in-season (early-window) -> ros
holdout_years: []
training_years: [2024, 2025]
validation_script: scripts/xfp/research/early_season_stabilization.py + early_season_ros_test.py + early_season_trending_2026.py
date: 2026-06-16
verdict: RESEARCH-ONLY
purpose: User wants to detect when a player is getting better/worse from bat-tracking. Forward-ranker promotion is sample-blocked (see bat_tracking_fp_family_2026-06-16.md) and full-season bat-tracking changes are redundant with barrel%/hard-hit% already in rh3. This tests the ONE non-redundant use — early-season, before the outcome rates stabilize. Validated AS A DISPLAY/CONTEXT early-warning signal (PASS-AS-DISPLAY), not a FEATS ranker.
---

## Why this is the non-redundant use (resolves the orthogonality "kill")

Earlier (`bat_tracking_fp_family`): year-over-year, Δbat-tracking is a faithful but
~fully redundant mirror of Δbarrel%/Δhard-hit% (partial r vs ΔFP collapsed
+0.49 → +0.01). That measured FULL seasons — everything stabilized → mirror.
The one place bat-tracking can beat the box score is EARLY, when bat speed is
already reliable and the rate stats are not.

## Part A — Stabilization (high-powered; pooled 2024+2025, +2026 for swings)

Split-half reliability, smallest n with r >= 0.70:

| metric | stabilizes at | ≈ real time for a regular |
|---|---|---|
| bat speed | **20 swings** | ~2 games / 3-4 days |
| swing length | 15 swings | ~2 games |
| attack angle | 30 swings | ~3 games |
| hard-hit% | 100 BIP | ~8-9 weeks |
| K% | 150 PA | ~6 weeks |
| xwOBACON | 150 BIP | ~12 weeks |
| wOBA | not by 400 PA | full season+ |

Bat speed is trustworthy after ~2 games; the outcome rates need 6-12 weeks.
That gap is the early-warning window.

## Part B — RoS prediction (2 cohorts: 2024, 2025; exploratory/display-grade)

(1) Raw r of EACH early signal with RoS xwOBACON — bat speed dominates early, the
rate stats start lower and catch up by ~10 weeks (the predicted crossover):

| cutoff | bat_speed | hard_hit% | xwOBACON | wOBA | K% |
|---|---|---|---|---|---|
| 21d | **+0.604** | +0.514 | +0.478 | +0.194 | +0.266 |
| 35d | +0.617 | +0.525 | +0.503 | +0.137 | +0.343 |
| 49d | +0.617 | +0.558 | +0.564 | +0.180 | +0.330 |
| 70d | +0.591 | +0.583 | +0.602 | +0.210 | +0.362 |

(2) Partial r of early bat_speed (controls = early wOBA, early hard-hit%, early K%,
prior-yr wOBA) — adds the MOST early, decays as rates catch up; both cohorts agree:

| cutoff | → RoS xwOBACON | → RoS wOBA | per-yr |
|---|---|---|---|
| 21d | **+0.385** | +0.181 | ++ |
| 35d | +0.379 | +0.202 | ++ |
| 49d | +0.344 | +0.167 | ++ |
| 70d | +0.283 | +0.169 | ++ |

(vs +0.01 full-season YoY → the value is entirely early-season-specific.)

(3) Δ-vs-prior "getting better/worse": r(early_bat_speed − prior_bat_speed,
RoS xwOBACON − prior wOBA): 2025 (clean prior) +0.161@35d / +0.207@49d;
2024 (2023 prior = 2H-only) +0.089 (caveated). Positive both cohorts.

## Part C — Live 2026 application (cross-checks the method)

`bat_speed_trending_2026.csv`. Reproduces the handoff's leaderboard alerts from
the parquet: Vargas +3.63 mph (xwOBACON confirming +0.085), McNeil −2.57,
Pasquantino −2.71. Bat-speed Δ population SD = 1.20 mph (so a ±2 mph move ≈ ±1.7σ).

## Honest caveats / scope

- **2 RoS cohorts** (2024, 2025) — display-grade, not a 5/7 validation. The Part A
  stabilization is high-powered and carries most of the weight. A 3rd cohort
  arrives when 2026 completes.
- **Hitters only.** SP/RP analog = INDUCED bat speed, with an opponent-quality
  confound (induced bat speed depends on which lineups were faced); needs a
  separate build before any RP/SP claim.
- **Necessary, not sufficient.** Bat speed up = the physical tool improved
  (breakout WATCH), not a guaranteed production gain — must still square it up
  (Nick Allen +5 mph but flat xwOBACON). Concurrent Δsign agreement with
  ΔxwOBACON is only 57% (magnitude matters; the predictive r is far stronger).
- Use as DISPLAY/CONTEXT early-warning, never to move the rh3 projection.

## Part D — SP/RP analog (induced bat speed): REJECTED, hitter-only tool

Pitcher analog = induced bat speed (mean bat speed of swings faced), opponent-
adjusted as SUPPRESSION (faced swing − batter's season baseline). Build:
`scripts/xfp/research/pitcher_induced_batspeed.py` (2024-25, SP gs>=8 vs RP).

- **Stabilization fails:** induced_supp split-half r reaches only ~0.60 at 200
  faced swings and never hits 0.70 (vs hitter bat speed 0.70 @ 20 swings). SPs
  face ~970 swings/full season, RPs ~170 → NO early-warning window; RPs can't get
  a stable read at all.
- **Faithfulness ~zero to damage:** Δind_supp vs ΔxwOBA-allowed raw r +0.074 (SP) /
  +0.025 (RP); partial goes negative. Only a modest ΔK% link (−0.21 SP / −0.19 RP).
- **Why:** a hitter's bat speed is his own repeated skill (fast-stabilizing); a
  pitcher's effect on opponents' bat speed is a tiny signal in huge between-hitter
  variance — needs hundreds of swings, never gets clean.

**Conclusion:** the bat-speed early-warning detector is HITTER-ONLY. For pitchers,
the fast-stabilizing physical "getting better/worse" signal is FASTBALL VELOCITY,
already validated and in production rp3 (`avg_velo_to` + `delta_velo`). Use velo
trend (not induced bat speed) for the pitcher side of any trending board.

## Part E — Slice frontier: 3-AXIS UPGRADE (shipped)

Asked "are we being exhaustive?" → tested 5 candidate slices on TWO axes
(stabilization speed + incremental early-RoS partial r OVER plain bat speed),
Bonferroni + 2-cohort signs. Scripts: `slice_frontier.py`, `slice_additivity.py`,
`new_axes_delta_faithfulness.py`.

**WINNERS (added to the hitter detector):**
| slice | metric | stabilizes | partial r over bat speed (35d) | 2-cohort |
|---|---|---|---|---|
| swing-path | **attack_angle** (toward ~15° band) | @30 sw | **+0.21** | ++ |
| intent | **fast-swing %** (≥75 mph) | @20 sw | **+0.17** | ++ |

- **Additivity (5-fold CV R², RoS xwOBACON @35d):** box+prior 0.412 → +bat speed
  0.495 → +attack_angle 0.516 → +fast_swing **0.536** (+0.041 OOS = ~½ of bat
  speed's own lift again). Cross-partials +0.26 / +0.23 → the two are NOT redundant
  with each other. Three orthogonal physical axes: how hard / how shaped / intent.
- **Δ-faithfulness (change framing):** Δattack_angle +0.25/+0.14, Δfast_swing
  +0.31/+0.20, Δ-toward-band −0.23/−0.12 (all 2/2). Population-optimal attack angle
  ≈ 15-16°; attack angle wired as movement TOWARD the band (direction-aware — a
  hitter already >16° rising further is bad, so naive "up=good" is wrong).

**REJECTED slices (do NOT re-investigate):**
- **premium-velo bat speed (vs 95+)** — partial −0.05 over overall bat speed.
  Decline hits all velocities proportionally; no orthogonal "can't catch the
  heater first" signal. (My top prior — killed by the test.)
- **swing-grain contact quality** (squared-up/swing @150 sw, hard-hit/swing >300
  sw) — premise that swing-grain stabilizes faster than BIP-grain was FALSE;
  contact quality is noisy at any grain. Partial null/negative.
- **contact-depth timing (`intercept_y`)** — ~zero raw r, partial −0.07.
- **binary ideal-AA %** — discards magnitude (the continuous attack_angle carries
  it); partial null. Same lesson as boom_stack v2.
- **attack_angle SD (consistency)** — real (+0.16) but stabilizes @150 sw, too slow
  for the early-season edge; not shipped.

**Shipped:** 3-axis composite `z_comp` in `scripts/xfp/lib/trend_signal.py`
(`hitter_trend_table` + `tag_hitter`), surfaced by `/trending`. Catches breakouts/
declines single-axis bat speed missed (Jordan Walker via swing-path; Wyatt
Langford swing-path off-band). Pitchers unchanged (FB velo). Still display/context.

## Where it should live

Display tag in `/slump-or-decline`, `/breakout-sustainability`, `/hitter-archetype`:
"bat speed +X.X mph vs '25 baseline (Nσ) — physical [breakout watch / decline watch],
contact [confirming/not yet]." Extends the existing xwOBACON-YoY-trajectory rule
(physical decline = lower recovery ceiling).

---
study: september_playing_time
date: 2026-08-05
family: late_season_volume
status: SPLIT -- constant retention PASS, age x contention FAIL (family CLOSED)
panel: statcast 2018-2025 (2020 excluded), Aug-5 anchor, Aug-24 -> season end target
train: 2018, 2019, 2021, 2022, 2023
holdout: 2024, 2025 (untouched until final scoring)
n: 1,494 hitter-seasons / 1,209 starter-seasons
---

# Predicting September playing time

## Motivation

The playoff-FP board projected the Aug 24 - Sep 27 window using season-to-date
volume, and I flagged in-chat that late-season playing time is "a real risk I
haven't modelled" -- eliminated clubs rest regulars, contenders ride theirs.
This study tests that.

## Construction

Per player-season: rate = PA / team-games (hitters), GS / team-games (starters).
Anchor Aug 5 (mirrors the live decision), target Aug 24 -> season end. Club
contention = games back of the club holding the last playoff spot within the
league, recomputed from W/L rather than trusting MLB's gamesBack strings (a
literal `-` means the club LEADS, not that data is missing). Playoff field is
5 clubs per league through 2021, 6 from 2022.

Population: hitters with >=150 PA and >=2.5 PA/team-game at the anchor;
starters with >=8 starts. That is the set I would actually roster.

## Result 1 -- constant retention: PASS, and it is not September

Forward rate is a stable fraction of season-to-date rate:
**hitters 0.865, starters 0.829.**

Holdout 2024-25:

| predictor | hitter bias | hitter RMSE | starter bias | starter RMSE |
|---|---|---|---|---|
| naive season-to-date | +0.482 | 1.235 | +0.0295 | 0.0803 |
| constant shrink | **+0.010** | **1.137** | **+0.0035** | **0.0738** |

Note MAE moves the other way for hitters (0.858 -> 0.891) because MAE rewards
the biased predictor on a skewed target. Bias and RMSE are the right criteria
here: the consumer sums ~22 players into a team total, where bias compounds
and absolute error partly cancels.

**Placebo kills the September framing.** The identical construction at a MAY
anchor decays MORE than August:

| arm | change in PA/team-game | retained |
|---|---|---|
| AUGUST (real) | -0.470 | 86% |
| JUNE (placebo) | -0.380 | 89% |
| MAY (placebo) | **-0.515** | 85% |

So this is generic attrition + mean reversion, present in any 5-week window,
not a September phenomenon. It is named `late_season_volume` for where it was
found, but it applies year-round.

## Result 2 -- age x contention: FAIL, family CLOSED

The mechanism is real in-sample and the placebo is clean. In AUGUST, hitters
30+ on clubs 12+ back kept **75%** vs **89%** on contenders; partial
r(games back, forward rate | to-date rate) = **-0.141, 95% CI
[-0.220,-0.062]**. The same JUNE cut shows **+0.030, CI spans 0** -- nobody
sells in June, exactly as the mechanism predicts. In-sample collapse rate
(losing >=half your playing time) was 27.3% for veterans on sellers vs 10.9%
on contenders.

**None of it replicated.**

| test | train | holdout 2024-25 |
|---|---|---|
| hitter collapse-flag lift | +16.4pp | **-1.0pp +/- 12.4pp** |
| hitter rate model, veterans-on-sellers segment | -- | **-0.084 PA/tg WORSE than flat shrink** |
| starter partial r (games back) | -- | **-0.062, CI [-0.168,+0.044]** |

The age x contention model beat a flat shrink by only 1.6% MAE overall, and
lost in the one segment it exists for. Starters show nothing at any anchor.

**Family CLOSED.** Re-open only on a genuinely new information source --
lineup cards, roster transactions, published rest plans -- not another cut of
standings.

## Result 3 -- production audit

`xfp_volume_projections.csv` already applies 0.873, matching the empirical
0.865. **The hitter volume model is correctly calibrated; use it as is.**

`xfp_sp_volume_projections.csv` applies 0.920 against an empirical 0.829, so
projected starts run ~11% optimistic. Not patched here -- that model is
validated for ranking and a bias correction is its own sign-off. Exposed as
`SP_MODEL_OPTIMISM`.

**Live bug found:** the playoff board took
`max(proj_ros_pa_per_teamgame, pa_per_teamgame_to, measured_30d)`, which
discards the calibrated projection whenever raw pace is higher and re-inflates
the exact bias the volume model removes. Effect on the 2026-08-05 board:
hitter total 1,028 -> 888 FP (-13.6%), with Michael Harris II dropping from
3rd to 6th among hitters and Aaron Judge rising (his was IL-suppressed).

## Shipped

- `scripts/xfp/lib/late_season_volume.py` -- constants, `volume_from_to_date`,
  `is_double_shrunk` guard, full provenance in the module docstring.
- `tests/test_late_season_volume.py` -- 7 tests locking the constants.

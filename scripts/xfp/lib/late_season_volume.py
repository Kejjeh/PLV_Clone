# -*- coding: utf-8 -*-
"""Forward playing-time retention for late-season / playoff-window projections.

Validated 2026-08-05 on 2018-2025 statcast (2020 excluded -- a 60-game season
has no comparable dynamics). Anchor Aug 5, target Aug 24 -> season end, the
exact shape of the BrownU playoff window. Train 2018-2023, holdout 2024-2025.

WHAT SURVIVED
-------------
A player's forward rate over a ~5-week window is a CONSTANT fraction of his
season-to-date rate. Hitters keep 0.865 of their PA/team-game, starters 0.829
of their GS/team-game. Applying the shrink removes essentially all of the
systematic error: on the 2024-25 holdout it took hitter bias from +0.482 to
+0.010 PA/team-game and RMSE from 1.235 to 1.137; starter bias from +0.0295
to +0.0035 GS/team-game and RMSE from 0.0803 to 0.0738.

This is NOT a September effect. The identical construction at a MAY anchor
decays MORE (-0.515 PA/team-game) than the August one (-0.470), so the shrink
is generic attrition plus mean reversion -- injuries, demotions, trades, and
selection on a healthy season-to-date rate. It applies to any forward window,
which is why it belongs in a volume helper rather than a playoff one.

WHAT FAILED -- do not re-derive
-------------------------------
Club contention (games back of a playoff spot) interacting with age. The
mechanism is real in-sample and the placebo was clean: in AUGUST, hitters 30+
on clubs 12+ games back kept 75% vs 89% on contenders (partial r -0.141,
95% CI [-0.220,-0.062]), while the same JUNE cut showed nothing (+0.030, CI
spans 0). The in-sample collapse flag looked strong -- 27.3% of veterans on
sellers lost half their playing time vs 10.9% on contenders.

It did not replicate. On the 2024-25 holdout the flag lift vanished entirely
(14.7% flagged vs 15.7% unflagged, diff -1.0% +/- 12.4%), and as a rate model
the age x contention term was WORSE than a flat shrink in the very segment it
was built for (-0.084 PA/team-game on veterans-on-sellers). Starters showed
nothing anywhere: holdout partial r -0.062, CI [-0.168,+0.044].

Family CLOSED. Re-open only with a genuinely new information source (e.g.
actual lineup-card or roster-transaction data), not another cut of standings.

DOUBLE-APPLICATION IS THE REAL HAZARD
-------------------------------------
`xfp_volume_projections.csv` ALREADY applies this shrink -- its
`proj_ros_pa_per_teamgame` averages 0.873 of `pa_per_teamgame_to`, matching
the empirical 0.865. So use `proj_ros_pa_per_teamgame` AS IS.

Never take max(projection, season-to-date, trailing-30d): that silently
reverts to the uncalibrated rate whenever raw pace is higher, which is the
majority of the time, and re-inflates precisely the bias the volume model
exists to remove. Use `volume_from_to_date` only when no projection row
exists.

`xfp_sp_volume_projections.csv` shrinks to 0.920 against the empirical 0.829,
so projected starts run optimistic. That model is validated for RANKING
(+0.100 Spearman vs naive pace) and this module does not silently patch it;
`SP_MODEL_OPTIMISM` is exposed so callers can state the gap explicitly.
"""
from __future__ import annotations

# empirical retention over a ~5-week forward window, mean of per-player ratios
HITTER_RETENTION = 0.865
SP_RETENTION = 0.829

# what the shipped volume models actually apply, for double-application checks
HITTER_MODEL_RETENTION = 0.873
SP_MODEL_RETENTION = 0.920

# starters project this much hotter than history supports
SP_MODEL_OPTIMISM = SP_MODEL_RETENTION / SP_RETENTION   # ~1.11

_SIDES = {'H': HITTER_RETENTION, 'SP': SP_RETENTION}


def retention(side: str) -> float:
    """Fraction of a season-to-date rate that carries into a ~5-week window."""
    try:
        return _SIDES[side.upper()]
    except KeyError:
        raise ValueError(f"side must be 'H' or 'SP', got {side!r}") from None


def volume_from_to_date(to_date_rate: float, side: str) -> float:
    """Calibrate a RAW season-to-date rate for forward use.

    Only for players with no volume-model row -- the models already shrink.
    """
    return float(to_date_rate) * retention(side)


def is_double_shrunk(projected: float, to_date: float, side: str,
                     tol: float = 0.04) -> bool:
    """True if `projected` looks like a model projection that was shrunk again.

    A calibrated projection sits near the model's own retention; a value near
    retention squared means the shrink was applied twice.
    """
    if not to_date:
        return False
    ratio = float(projected) / float(to_date)
    model = HITTER_MODEL_RETENTION if side.upper() == 'H' else SP_MODEL_RETENTION
    return ratio < model * retention(side) + tol

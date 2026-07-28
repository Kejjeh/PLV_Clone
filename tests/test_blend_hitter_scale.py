"""Hitter blend / rh3 display-scale invariant (audit closed 2026-07-28).

WHY THIS FILE EXISTS. ~25 hitters were observed blending 1.5-1.75x above
rh3 at 'high' confidence, and the consistency of the multiplier looked like
a units regression in `_hitter_pa_per_game` (fp_per_pa -> fp/game). It was
not: both sides run on an identical 3.500 PA/game and identical levels, and
the H and SP disagreement distributions are statistically indistinguishable
(|log ratio| p95 1.59 vs 1.52). The band is ordinary tail disagreement
between a prior-year-anchored blend and an in-season model.

Nothing asserted that invariant, which is why the question stayed open long
enough to need an investigation. These tests pin it. A REAL units bug --
someone reintroducing the 3.85 default, double-multiplying by PA/G, or rh3
changing its own PA assumption -- moves the MEDIAN of the ratio
distribution. Tail behaviour is expected and deliberately not asserted.

See the "Hitter scale audit" section of scripts/xfp/lib/blend_score.py for
the measured numbers.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from scripts.xfp.lib.blend_score import (
    _MASTER_PANEL,
    _PA_PER_GAME_DEFAULT,
    _fit_model,
    _hitter_pa_per_game,
    compute_blended_xfp,
)

_RH3 = "data/outputs/xfp_rh3_projections.csv"

# The single constant both sides must agree on. rh3 publishes per_game to
# 2dp, so its recovered ratio wobbles ~0.02 around this.
_EXPECTED_PA_PER_GAME = 3.50
_PA_TOL = 0.05

_needs_rh3 = pytest.mark.skipif(not os.path.exists(_RH3), reason="rh3 projections not present")
_needs_panel = pytest.mark.skipif(
    not os.path.exists(_MASTER_PANEL), reason="master_panel.parquet not present"
)


@_needs_rh3
def test_rh3_publishes_a_constant_3_5_pa_per_game() -> None:
    """rh3's per_game is per_pa * 3.5 for every hitter. If this changes, the
    blend's mapping must change with it — that is the whole point of
    `_hitter_pa_per_game` deriving the ratio rather than hardcoding it."""
    rh3 = pd.read_csv(_RH3).dropna(subset=["xfp_rh3_per_pa", "xfp_rh3_per_game"])
    rh3 = rh3[rh3["xfp_rh3_per_pa"] > 0]
    ratio = rh3["xfp_rh3_per_game"] / rh3["xfp_rh3_per_pa"]
    assert ratio.median() == pytest.approx(_EXPECTED_PA_PER_GAME, abs=_PA_TOL)
    # Spread is 2dp rounding on per_game only — not per-player PA/G.
    assert ratio.max() - ratio.min() < 0.05


@_needs_panel
def test_master_panel_uses_the_same_pa_per_game_as_rh3() -> None:
    """The blend's intercept and z-scores come from the panel; its display
    mapping comes from rh3. Those two only compose into a comparable number
    while both sit on the same PA/G."""
    panel = pd.read_parquet(_MASTER_PANEL, columns=["player_type", "fp_per_pa", "fp_per_game"])
    h = panel[(panel["player_type"] == "H") & (panel["fp_per_pa"] > 0)]
    implied = (h["fp_per_game"] / h["fp_per_pa"]).median()
    assert implied == pytest.approx(_EXPECTED_PA_PER_GAME, abs=_PA_TOL)


@_needs_panel
@_needs_rh3
def test_blend_intercept_sits_at_the_rh3_level() -> None:
    """target_mean is the blend's anchor. If it drifts far from rh3's own
    central tendency the two are no longer measuring the same quantity,
    whatever the units say."""
    target_mean = _fit_model()["H"]["target_mean"]          # fp_per_pa units
    rh3_median = pd.read_csv(_RH3)["xfp_rh3_per_pa"].median()
    assert target_mean / rh3_median == pytest.approx(1.0, abs=0.15)


@_needs_rh3
def test_hitter_pa_per_game_tracks_rh3_not_the_fallback() -> None:
    """Per-player: the mapping must come from rh3's published ratio. Silently
    falling back to 3.85 for rostered hitters would reintroduce the 2026-06-05
    over-scaling bug."""
    rh3 = pd.read_csv(_RH3).dropna(subset=["batter"]).head(25)
    for _, r in rh3.iterrows():
        got = _hitter_pa_per_game(int(r["batter"]))
        assert got == pytest.approx(_EXPECTED_PA_PER_GAME, abs=_PA_TOL)
        assert got != _PA_PER_GAME_DEFAULT, "fell back to 3.85 for a hitter rh3 covers"


@_needs_panel
@_needs_rh3
def test_blend_is_centred_on_rh3_across_the_population() -> None:
    """GROSS-break backstop only — read the division of labour before
    widening or tightening this.

    A units error shifts the whole distribution; genuine model disagreement
    only fattens the tails, so the median is the right statistic. But it is
    a BLUNT one, and this test is deliberately not the primary defence:

      - `test_hitter_pa_per_game_tracks_rh3_not_the_fallback` is what
        actually catches a PA/G substitution. It asserts the mapping equals
        rh3's own 3.50 and is not the 3.85 default, directly and precisely.
      - This test catches scale breaks that DON'T route through
        `_hitter_pa_per_game` — a double-multiply, a per-PA value published
        as per-game, a panel/rh3 unit divergence.

    Verified 2026-07-28 by simulating the regressions: a double-multiply
    moves the median to 3.96 and trips this. A 3.85/3.50 slip only moves it
    to 1.245 and does NOT trip it — that one is the direct test's job. The
    band is kept loose on purpose so ordinary blend drift doesn't raise a
    false "display-scale regression", which would be worse than useless.
    """
    rh3 = pd.read_csv(_RH3).dropna(subset=["batter", "xfp_rh3_per_game"])
    rh3 = rh3[rh3["xfp_rh3_per_game"] > 0]
    ratios = []
    for _, r in rh3.iterrows():
        res = compute_blended_xfp(str(r["player_name"]), "H", int(r["batter"]))
        blended = res.get("blended_xfp")
        if blended and blended > 0:
            ratios.append(blended / float(r["xfp_rh3_per_game"]))
    assert len(ratios) >= 50, f"only {len(ratios)} hitters scored — sample too thin to judge"
    median_ratio = float(np.median(ratios))
    assert 0.80 <= median_ratio <= 1.40, (
        f"blend/rh3 median ratio {median_ratio:.3f} is off-centre — suspect a "
        f"GROSS display-scale break (double-multiply, per-PA published as "
        f"per-game, panel/rh3 unit divergence), not model disagreement. See "
        f"the hitter scale audit in blend_score.py."
    )

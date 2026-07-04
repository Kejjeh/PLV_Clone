"""Tests for lib/extra_lenses park-factor ownership.

Regression (2026-07-03, the "ATH Sutter Health" bug): _park_R_map blended
2022-2026 pf_R, mixing 3 Coliseum years (pitcher-friendly) into the Sutter
Health era (hitter-friendly) and calling ATH "neutral" (1.001). A streamer
board then credited a visiting SP +0.9 FP at the second-worst pitcher venue
in baseball (empirical 2026: SPs avg 7.1 FP/start there, -2.8 vs league).
VENUE_ERAS must clamp the blend to current-venue years, and park_fp_adj is
the ONE owner of park->FP conversion so boards never hand-type park tables.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts" / "xfp"))

from lib.extra_lenses import _park_R_map, park_fp_adj, VENUE_ERAS, PARK_FP_SLOPE


def test_ath_reflects_sutter_not_coliseum():
    """Sutter-era (2025+) pf_R is ~1.04-1.10; the old blend said ~1.00."""
    pf = _park_R_map()
    assert pf, "park map failed to load"
    assert pf["ATH"] >= 1.03, f"ATH pf_R {pf['ATH']:.3f} still blending Coliseum years"


def test_tb_reflects_steinbrenner_era():
    pf = _park_R_map()
    assert pf["TB"] >= 1.00, f"TB pf_R {pf['TB']:.3f} still blending Tropicana years"


def test_venue_era_teams_declared():
    assert VENUE_ERAS.get("ATH") == 2025
    assert VENUE_ERAS.get("TB") == 2025


def test_coors_still_extreme():
    """The era clamp must not disturb single-venue teams."""
    pf = _park_R_map()
    assert pf["COL"] > 1.15
    assert max(pf, key=pf.get) == "COL"


def test_park_fp_adj_signs():
    """+ = pitcher-friendly (SEA), - = hitter-friendly (ATH, COL)."""
    assert park_fp_adj("SEA") > 0.5
    assert park_fp_adj("ATH") < -0.4
    assert park_fp_adj("COL") < -2.0
    assert park_fp_adj("NOPE") == 0.0  # unknown -> neutral, never invents


def test_slope_is_negative_and_sane():
    """Higher run factor must cost the SP FP; magnitude near the 2026 empirical fit."""
    assert -25.0 < PARK_FP_SLOPE < -8.0

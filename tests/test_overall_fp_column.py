"""OVERALL_FP — the FP-faithful parallel composite (display-only, 2026-07-04).

The rating-reimagine study showed the shipped OVERALL composites use weights
that don't match forward FP value (hitter .55/.35/.10 forward r=.477 < the
raw-FP carry .510; SP MOVEMENT 3x overweighted; RP CONTROL/BATTED_BALL dead).
OVERALL_FP is the refit-weights composite added as a PARALLEL column at the
dashboard payload layer — the shipped OVERALL is untouched because
arche_overall_prior feeds baseline xFP (changing it needs /validate-feature).

Weights (research 2026-07-04, rating_reimagine memo):
  hitter: .58 CONTACT + .17 POWER + .17 SB + .08 DISCIPLINE   (fwd .515 vs .477)
  SP:     .76 STUFF + .14 MOVEMENT + .10 CONTROL              (fwd .577 vs .551)
  RP:     .55 save-role(z of SV) + .35 STUFF + .10 FP-level(z) (role-first, r .558)
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "xfp"))

from build_player_profiles_dashboard import annotate_overall_fp


def test_hitter_weights():
    recs = [{"CONTACT": 60, "POWER": 40, "DISCIPLINE": 50, "SB": 50, "OVERALL": 52}]
    annotate_overall_fp(recs, "hitter")
    # .58*60 + .17*40 + .17*50 + .08*50 = 34.8+6.8+8.5+4 = 54.1 -> 54
    assert recs[0]["OVERALL_FP"] == 54


def test_sp_weights_stuff_dominant():
    recs = [{"STUFF": 70, "MOVEMENT": 40, "CONTROL": 40, "OVERALL": 56}]
    annotate_overall_fp(recs, "sp")
    # .76*70 + .14*40 + .10*40 = 53.2+5.6+4 = 62.8 -> 63 (vs shipped 56)
    assert recs[0]["OVERALL_FP"] == 63


def test_missing_pillar_leaves_none():
    recs = [{"STUFF": None, "MOVEMENT": 50, "CONTROL": 50}]
    annotate_overall_fp(recs, "sp")
    assert recs[0]["OVERALL_FP"] is None


def test_rp_role_first_orders_by_saves():
    # Same skill pillars, different save totals, same year: the closer must
    # out-rate the middle reliever on the role-first composite.
    recs = [
        {"year": 2026, "sv": 30, "STUFF": 55, "fp_per_g": 5.0},
        {"year": 2026, "sv": 0,  "STUFF": 55, "fp_per_g": 5.0},
        {"year": 2026, "sv": 5,  "STUFF": 55, "fp_per_g": 5.0},
        {"year": 2026, "sv": 2,  "STUFF": 55, "fp_per_g": 5.0},
        {"year": 2026, "sv": 12, "STUFF": 55, "fp_per_g": 5.0},
    ]
    annotate_overall_fp(recs, "rp")
    vals = [r["OVERALL_FP"] for r in recs]
    assert all(v is not None for v in vals)
    assert vals[0] > vals[2] > vals[1]     # 30 SV > 5 SV > 0 SV
    assert vals[4] > vals[2]               # 12 SV > 5 SV


def test_template_ships_the_column():
    import re
    import _player_profiles_template as T
    for tbl in ("H_TBL_COLS", "S_TBL_COLS", "RP_TBL_COLS"):
        block = T.JS.split(f"const {tbl} = [")[1].split("];")[0]
        assert "OVERALL_FP" in block, f"{tbl} missing OVERALL_FP column"
    assert "'OVERALL_FP'" in T.JS.split("RATING_CHIP_KEYS")[1][:600], "no chip render"
    assert re.search(r"OVERALL_FP:\s*'", T.JS), "no tooltip for OVERALL_FP"

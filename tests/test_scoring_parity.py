"""Parity gate for the BrownU scoring-formula owner migration (audit 2026-07-03).

lib/boom_bust.py re-typed the SP/RP/hitter FP formula inline in 4 places; those
now call src/plv_clone/fantasy/scoring.py (the owner). This test is the gate that
made the migration safe: scoring.py must reproduce (a) the documented BrownU
formula exactly and (b) every persisted boxscore FP value, and boom_bust must be
wired to the owner (not a re-typed copy).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
for p in (_ROOT, _ROOT / "src", _ROOT / "scripts" / "xfp"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from plv_clone.fantasy.scoring import pitcher_fp, hitter_fp

_BOX_P = _ROOT / "data" / "research" / "xfp_cache" / "boxscore_pitchers.parquet"
_BOX_H = _ROOT / "data" / "research" / "xfp_cache" / "boxscore_hitters.parquet"


def test_pitcher_fp_is_brownu_formula():
    # K + IP*3.3 - H - 2*ER - BB - HBP  = 6 + 6*3.3 - 4 - 2*2 - 1 - 0 = 16.8
    assert pitcher_fp(k=6, ip=6.0, h=4, er=2, bb=1, hbp=0) == pytest.approx(16.8)


def test_rp_fp_adds_sv_hld():
    # + 5*SV + 2*HLD
    base = pitcher_fp(k=3, ip=1.0, h=1, er=0, bb=0, hbp=0)
    assert pitcher_fp(k=3, ip=1.0, h=1, er=0, bb=0, hbp=0, sv=1, hld=0) == pytest.approx(base + 5)
    assert pitcher_fp(k=3, ip=1.0, h=1, er=0, bb=0, hbp=0, hld=2) == pytest.approx(base + 4)


def test_hitter_fp_is_brownu_formula():
    # R + TB + RBI + BB + HBP + SB - K = 1 + 4 + 2 + 1 + 0 + 1 - 1 = 8
    assert hitter_fp(r=1, tb=4, rbi=2, bb=1, hbp=0, sb=1, k=1) == pytest.approx(8.0)


def test_boom_bust_is_wired_to_the_owner():
    """The migration's core guarantee: boom_bust uses the owner functions, not a
    re-typed copy. Same function object => no divergent formula can exist."""
    import lib.boom_bust as bb
    assert bb.pitcher_fp is pitcher_fp
    assert bb.hitter_fp is hitter_fp


@pytest.mark.skipif(not _BOX_P.exists(), reason="boxscore store not built")
def test_scoring_reproduces_persisted_pitcher_fp():
    import pandas as pd, numpy as np
    bp = pd.read_parquet(_BOX_P)
    sp, rp = bp[bp["gs"] == 1], bp[bp["gs"] == 0]
    sp_new = pitcher_fp(k=sp["so"], ip=sp["ip"].astype(float), h=sp["h_allowed"],
                        er=sp["er"], bb=sp["bb_allowed"], hbp=sp["hbp_allowed"])
    rp_new = pitcher_fp(k=rp["so"], ip=rp["ip"].astype(float), h=rp["h_allowed"],
                        er=rp["er"], bb=rp["bb_allowed"], hbp=rp["hbp_allowed"],
                        sv=rp["sv"], hld=rp["hld"])
    # tolerance = the stored `ip` column's own rounding (not a formula difference)
    assert np.abs(sp_new.values - sp["fp_sp"].values).max() < 2e-4
    assert np.abs(rp_new.values - rp["fp_rp"].values).max() < 2e-4


@pytest.mark.skipif(not _BOX_H.exists(), reason="boxscore store not built")
def test_scoring_reproduces_persisted_hitter_fp():
    import pandas as pd, numpy as np
    bh = pd.read_parquet(_BOX_H)
    h_new = hitter_fp(r=bh["r"], tb=bh["tb"], rbi=bh["rbi"], bb=bh["bb"],
                      hbp=bh["hbp"], sb=bh["sb"], k=bh["k"])
    assert np.abs(h_new.values - bh["fp_h"].values).max() == 0.0

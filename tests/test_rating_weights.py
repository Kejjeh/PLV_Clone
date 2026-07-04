"""Tests for lib/rating_weights.py — the FPwt (OVERALL_FP) owner module.

Item 3: the three weight sets were extracted verbatim from
build_player_profiles_dashboard.annotate_overall_fp. These tests pin the
exact weights + the per-row and batch (RP-population) behaviours so the
dashboard's byte-identical output is guaranteed and downstream surfaces
(triangulate / scouting-report / fa-pickup-deep-dive) share one owner.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for p in (_ROOT / "scripts" / "xfp", _ROOT / "src", _ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from lib import rating_weights as rw


def test_hitter_weights_exact():
    # .58C/.17P/.17SB/.08D
    row = {"CONTACT": 60, "POWER": 50, "SB": 40, "DISCIPLINE": 50}
    # .58*60 + .17*50 + .17*40 + .08*50 = 34.8+8.5+6.8+4 = 54.1 -> 54
    assert rw.overall_fp("hitter", row) == 54


def test_sp_weights_exact():
    # .76 STUFF/.14 MOV/.10 CTRL
    row = {"STUFF": 70, "MOVEMENT": 50, "CONTROL": 40}
    # .76*70 + .14*50 + .10*40 = 53.2+7+4 = 64.2 -> 64
    assert rw.overall_fp("sp", row) == 64


def test_missing_pillar_returns_none():
    assert rw.overall_fp("hitter", {"CONTACT": 60, "POWER": None, "SB": 40, "DISCIPLINE": 50}) is None
    assert rw.overall_fp("sp", {"STUFF": 70, "MOVEMENT": 50}) is None


def test_weights_are_the_registered_constants():
    assert rw.WEIGHTS["hitter"] == [("CONTACT", .58), ("POWER", .17), ("SB", .17), ("DISCIPLINE", .08)]
    assert rw.WEIGHTS["sp"] == [("STUFF", .76), ("MOVEMENT", .14), ("CONTROL", .10)]


def test_annotate_hitter_matches_overall_fp():
    recs = [
        {"CONTACT": 60, "POWER": 50, "SB": 40, "DISCIPLINE": 50},
        {"CONTACT": 55, "POWER": 55, "SB": 55, "DISCIPLINE": 55},
        {"CONTACT": None, "POWER": 50, "SB": 40, "DISCIPLINE": 50},
    ]
    rw.annotate_overall_fp(recs, "hitter")
    assert recs[0]["OVERALL_FP"] == 54
    assert recs[1]["OVERALL_FP"] == 55
    assert recs[2]["OVERALL_FP"] is None


def test_annotate_rp_population_zblend():
    # RP is role-first: .55*z(SV)+.35*STUFF+.10*z(FP/g), z within year.
    # Need >=5 SV and >=5 FP samples or all None.
    recs = [
        {"year": 2026, "sv": s, "fp_per_g": f, "STUFF": 50}
        for s, f in [(30, 10), (25, 9), (20, 8), (15, 7), (10, 6), (5, 5)]
    ]
    rw.annotate_overall_fp(recs, "rp")
    vals = [r["OVERALL_FP"] for r in recs]
    assert all(isinstance(v, int) for v in vals)
    # Highest-SV, highest-FP reliever should score highest.
    assert vals[0] == max(vals)


def test_annotate_rp_too_few_samples_none():
    recs = [{"year": 2026, "sv": 30, "fp_per_g": 10, "STUFF": 50},
            {"year": 2026, "sv": 20, "fp_per_g": 8, "STUFF": 50}]
    rw.annotate_overall_fp(recs, "rp")
    assert all(r["OVERALL_FP"] is None for r in recs)


def test_overall_fp_rp_per_row_needs_pop_returns_none():
    # Single-row RP FPwt cannot be computed without a population -> None (never invents).
    assert rw.overall_fp("rp", {"sv": 30, "fp_per_g": 10, "STUFF": 50}) is None

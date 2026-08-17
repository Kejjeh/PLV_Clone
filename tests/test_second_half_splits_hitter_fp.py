"""run_second_half_splits.py's _hit_fp must use the canonical scoring
function, not a hand-duplicated formula — issue #18.

_pitch_fp (same file) was already fixed for exactly this reason: it
"silently desynced from the league when holds went 2 -> 3 (2026-08-12)".
_hit_fp is the un-migrated sibling — if any hitter-side LeagueScoring
weight is ever tuned via data/models/league_scoring.json, this file keeps
computing FP with the stale hardcoded weights.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import run_second_half_splits as m  # noqa: E402
from plv_clone.fantasy.scoring import hitter_fp  # noqa: E402


def test_hit_fp_matches_canonical_default_scoring():
    stat = dict(runs=2, totalBases=5, rbi=3, baseOnBalls=1, hitByPitch=0,
                stolenBases=1, strikeOuts=2)
    expected = hitter_fp(r=2, tb=5, rbi=3, bb=1, hbp=0, sb=1, k=2)
    assert m._hit_fp(stat) == expected


def test_hit_fp_actually_calls_the_canonical_function(monkeypatch):
    """A hand-duplicated formula and the canonical one agree numerically at
    default weights by coincidence — that alone doesn't prove delegation
    (a future weight tune would silently desync a hardcoded copy, the exact
    failure _pitch_fp was already fixed for). Spy on the real import site
    to prove _hit_fp genuinely calls plv_clone.fantasy.scoring.hitter_fp,
    not a local re-derivation."""
    calls = []

    def _spy(**kwargs):
        calls.append(kwargs)
        return 999.0

    monkeypatch.setattr("plv_clone.fantasy.scoring.hitter_fp", _spy)
    stat = dict(runs=1, totalBases=2, rbi=1, baseOnBalls=0, hitByPitch=0,
                stolenBases=0, strikeOuts=1)
    result = m._hit_fp(stat)
    assert calls, "_hit_fp never called plv_clone.fantasy.scoring.hitter_fp"
    assert result == 999.0

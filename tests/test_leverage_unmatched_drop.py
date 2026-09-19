"""delta_pwin(drop=X) must REFUSE a drop that matches no simulated player.

Defect (found 2026-09-18): ``_resolve_keys`` returned an empty set for a
name/id with zero matches (it only raised on an AMBIGUOUS name), and the SP
partition in ``delta_pwin`` likewise matched nothing — so the scenario was the
unchanged baseline and the move scored dpwin = 0.00pp: "dropping him is free".
A rostered player with no projection row or an unresolved mlbam is absent from
D by construction, so he was the optimizer's cheapest drop leg every time.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import scripts.xfp.lib.leverage_engine as E  # tracked source: a hard import, never a guard

N = 500


def _state():
    return {"mu": {"my_score": 100.0, "opp_score": 100.0},
            "cap_remaining_mine": 10, "cap_remaining_opp": 10}


def _D(seed=3):
    rng = np.random.default_rng(seed)
    a = lambda v: rng.normal(v, 4.0, N)
    return {"n_sims": N, "seed": seed, "cand": {}, "rng": rng,
            "my_h": {"id:1": {"name": "Real Hitter", "mlbam": 1, "arr": a(10)}},
            # opp sized so the baseline is NOT saturated (pwin strictly inside
            # (0,1)); otherwise a real drop can read 0.00 for the wrong reason
            "opp_h": {"id:2": {"name": "Opp Hitter", "mlbam": 2, "arr": a(26)}},
            "my_rp": {"id:3": {"name": "Real RP", "mlbam": 3, "arr": a(4)}},
            "opp_rp": {},
            "my_sp": [{"event": {"name": "Real SP", "date": "2026-09-20",
                                 "confirmed": True, "mlbam": 4},
                       "fp": a(12), "occ": np.ones(N, dtype=bool)}],
            "opp_sp": []}


@pytest.mark.parametrize("ghost", ["Ghost Player", 999999, "id:999999"])
def test_unmatched_drop_raises_instead_of_scoring_zero(ghost):
    with pytest.raises(KeyError, match="matches no rostered player"):
        E.delta_pwin(_state(), _D(), drop=[ghost])


def test_matched_drops_still_score_in_every_bucket():
    st, D = _state(), _D()
    for who in ("Real Hitter", 1, "Real RP", 3, "Real SP", 4):
        r = E.delta_pwin(st, D, drop=[who])
        assert r["dpwin"] < 0, (who, r)


def test_mixed_list_with_one_ghost_still_raises():
    with pytest.raises(KeyError):
        E.delta_pwin(_state(), _D(), drop=["Real Hitter", "Ghost Player"])

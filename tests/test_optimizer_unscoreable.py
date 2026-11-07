"""A rostered player the simulation holds no draws for is never offered as a
drop, and the payload names him.

Defect (found 2026-09-18): build_state silently omits a hitter/RP with no
projection row or no resolved mlbam from D, while _roster_meta still lists
him — so score_single_moves offered him as a drop, ``_resolve_keys`` matched
nothing, and the scenario scored 0.00pp: the cheapest drop leg every time.
delta_pwin now REFUSES such a drop; the optimizer must therefore filter him
out before scoring and report him as UNSCOREABLE.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import run_weekly_optimizer as WO
from test_weekly_optimizer_plan import BASE_P, _cand, _fake_dp, _roster, _state


def _D_missing(roster, missing_name):
    """Engine-shaped D with draw entries for every roster player EXCEPT one."""
    D = {"n_sims": 10, "seed": 1, "cand": {}, "my_h": {}, "my_rp": {}, "my_sp": [],
         "opp_h": {}, "opp_rp": {}, "opp_sp": []}
    for p in roster:
        if p["name"] == missing_name:
            continue
        rec = {"name": p["name"], "mlbam": p["mlbam"], "arr": np.zeros(10)}
        if p["bucket"] == "H":
            D["my_h"][f"id:{p['mlbam']}"] = rec
        elif p["bucket"] == "RP":
            D["my_rp"][f"id:{p['mlbam']}"] = rec
        else:
            D["my_sp"].append({"event": {"name": p["name"], "mlbam": p["mlbam"],
                                         "date": "2026-09-20", "confirmed": True},
                               "fp": np.zeros(10), "occ": np.ones(10, dtype=bool)})
    return D


@pytest.mark.parametrize("missing", ["My OF3", "My RP2", "My SP4"])
def test_unscoreable_player_is_never_a_drop_leg(missing):
    roster = _roster()
    D = _D_missing(roster, missing)
    assert [p["name"] for p in WO.unscoreable_players(D, roster)] == [missing]
    # make the ghost the "cheapest" drop in the toy model (contrib 0 => free)
    contribs = {p["name"]: 0.05 for p in roster}
    contribs[missing] = 0.0
    contribs["FA Alpha"] = 0.10
    rows, _ = WO.score_single_moves(_state(roster), D, roster, [_cand("FA Alpha", 900)],
                                    BASE_P, verbose=False, _dp=_fake_dp(contribs))
    assert rows, "no legal moves scored"
    assert all(r["drop"]["name"] != missing for r in rows), (
        f"{missing} was offered as a drop although the engine holds no draws for him")


def test_toy_D_without_draw_tables_filters_nobody():
    roster = _roster()
    assert WO.unscoreable_players({}, roster) == []


def test_payload_carries_the_unscoreable_list():
    roster = _roster()
    D = _D_missing(roster, "My OF3")
    plan = {"source": "hold", "total_dpwin": 0.0, "pwin_final": BASE_P, "moves": []}
    res = {"rounds": [], "skipped": [], "pairs": []}
    payload = WO.build_payload(plan=plan, res=res, base_p=BASE_P, regime="CLOSE",
                               period=23, sims=10, seed=1, cap_remaining=8, wv={},
                               unscoreable=WO.unscoreable_players(D, roster))
    assert payload["unscoreable_drops"] == [{"name": "My OF3", "bucket": "H", "mlbam": 107}]

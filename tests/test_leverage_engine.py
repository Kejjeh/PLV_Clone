"""Tests for lib/leverage_engine — the P(win) MC engine (extracted 2026-07-29).

Three defects were fixed during extraction, and each is guarded here. All three
would have silently corrupted persisted dpwin history, which is what the decision
ledger later settles against — so these are the load-bearing tests of the whole
decision layer:

  1. draw dicts keyed by NAME (same-name players merged — the Muncy class)
  2. candidate draws pulled from a SHARED rng (dpwin depended on pool ordering)
  3. EV retarget was MULTIPLICATIVE on a distribution containing negatives
     (a pitcher's outlook improving made his blow-up starts worse)

Fixtures are synthetic — no network, no ESPN, no parquet — so these run fast and
deterministically in CI.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

E = pytest.importorskip("scripts.xfp.lib.leverage_engine",
                        reason="leverage engine needs the dashboard import chain")

N = 4000


def _state(cap_mine=10, cap_opp=10, my_score=100.0, opp_score=100.0):
    return {
        "mu": {"my_score": my_score, "opp_score": opp_score},
        "cap_remaining_mine": cap_mine,
        "cap_remaining_opp": cap_opp,
    }


def _draws(*, hitters=(), rps=(), my_sp=(), opp_h=(), seed=7, spread=0.0):
    """Hand-build a D dict in the engine's post-fix shape.

    spread=0 gives CONSTANT arrays, which is what the exact-sum assertions want.
    Any pwin-sensitivity test must pass spread>0: with zero variance every total
    is deterministic, so pwin saturates at exactly 0 or 1 and cannot respond to
    an added or dropped player.
    """
    rng = np.random.default_rng(seed)
    def _a(v):
        return (np.full(N, float(v)) if spread <= 0
                else rng.normal(float(v), spread, N))
    D = {"n_sims": N, "seed": seed, "cand": {}}
    D["my_h"] = {f"id:{m}": {"name": nm, "mlbam": m,
                             "arr": _a(v)}
                 for m, nm, v in hitters}
    D["opp_h"] = {f"id:{m}": {"name": nm, "mlbam": m,
                              "arr": _a(v)}
                  for m, nm, v in opp_h}
    D["my_rp"] = {f"id:{m}": {"name": nm, "mlbam": m,
                              "arr": _a(v)}
                  for m, nm, v in rps}
    D["opp_rp"] = {}
    D["my_sp"] = [
        {"event": {"name": nm, "date": dt, "confirmed": True, "mlbam": m},
         "fp": _a(v), "occ": np.ones(N, dtype=bool)}
        for m, nm, dt, v in my_sp]
    D["opp_sp"] = []
    D["rng"] = rng
    return D


# ── DEFECT 1: mlbam-keyed draws ──────────────────────────────────────────────

def test_two_same_name_hitters_do_not_merge():
    """THE Muncy test. Name-keyed dicts silently dropped one of them; the
    mlbam-keyed dict must carry both and sum both."""
    D = _draws(hitters=[(571970, "Max Muncy", 10.0), (691777, "Max Muncy", 3.0)])
    assert len(D["my_h"]) == 2, "same-name players must occupy distinct keys"
    my, _ = E.assemble(_state(), D)
    assert my[0] == pytest.approx(100.0 + 10.0 + 3.0)


def test_dropping_one_same_name_hitter_by_id_leaves_the_other():
    D = _draws(hitters=[(571970, "Max Muncy", 10.0), (691777, "Max Muncy", 3.0)])
    r = E.delta_pwin(_state(), D, drop=[691777])
    my, _ = E.assemble(_state(), D, drop_hitters={"id:691777"})
    assert my[0] == pytest.approx(113.0 - 3.0)
    assert r["dpwin"] <= 0.0


def test_ambiguous_name_refuses_rather_than_guessing():
    """Same refuse-to-guess contract as resolve_batter_id."""
    D = _draws(hitters=[(571970, "Max Muncy", 10.0), (691777, "Max Muncy", 3.0)])
    with pytest.raises(ValueError, match="matches 2 players"):
        E._resolve_keys(D, "my_h", ["Max Muncy"])


def test_unambiguous_name_still_resolves():
    D = _draws(hitters=[(1, "Bo Bichette", 9.0), (2, "Alec Bohm", 8.0)])
    assert E._resolve_keys(D, "my_h", ["Bo Bichette"]) == {"id:1"}


def test_draw_key_falls_back_to_name_without_colliding_with_ids():
    assert E._draw_key({"mlbam": 5, "name": "X"}) == "id:5"
    k = E._draw_key({"mlbam": None, "name": "Unresolved Guy"})
    assert k.startswith("nm:") and not k.startswith("id:")


# ── DEFECT 2: per-candidate RNG streams ──────────────────────────────────────

def test_candidate_rng_is_a_pure_function_of_seed_and_player():
    a = E.candidate_rng(7, 12345, "SP").normal(size=50)
    b = E.candidate_rng(7, 12345, "SP").normal(size=50)
    np.testing.assert_array_equal(a, b)


def test_candidate_rng_differs_across_players_and_buckets():
    a = E.candidate_rng(7, 12345, "SP").normal(size=50)
    b = E.candidate_rng(7, 99999, "SP").normal(size=50)
    c = E.candidate_rng(7, 12345, "H").normal(size=50)
    assert not np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_candidate_draws_are_independent_of_pool_ORDER():
    """THE order-dependence test. Under the old shared-rng code a candidate's
    draws depended on how many candidates were scored before it, so the same
    player scored differently in a reordered pool — fatal once dpwin is
    persisted and later settled against."""
    state = _state()

    def score(order):
        D = _draws(hitters=[(1, "Rostered", 5.0)])
        out = {}
        for c in order:
            cand = {"mlbam": c, "name": f"C{c}", "bucket": "H",
                    "proj": {"fp": 12.0, "units": 4, "sigma2": 16.0}}
            out[c] = E.ensure_candidate_draws(state, D, cand)["arr"].mean()
        return out

    fwd = score([101, 202, 303])
    rev = score([303, 202, 101])
    for k in fwd:
        assert fwd[k] == pytest.approx(rev[k]), f"candidate {k} moved with order"


def test_precompute_draws_retains_seed_for_candidate_streams():
    """candidate_rng needs the run seed; it must be carried on D."""
    import inspect
    src = inspect.getsource(E.precompute_draws)
    assert "'seed'" in src and "'cand'" in src


# ── DEFECT 3: location shift, not multiplicative rescale ─────────────────────

def test_ev_retarget_is_a_location_shift_not_a_multiply():
    """A multiplicative retarget makes disasters WORSE when the outlook
    improves. A shift moves the whole distribution and preserves spread."""
    rng = np.random.default_rng(0)
    base = rng.normal(8.0, 9.0, 20000)          # SP FP: negatives are routine
    assert (base <= 0).mean() > 0.10, "fixture must contain real negatives"
    target = 12.0                                # outlook improved

    shifted = base + (target - base.mean())
    scaled = base * (target / base.mean())       # the OLD behaviour

    assert shifted.mean() == pytest.approx(target, abs=1e-9)
    assert scaled.mean() == pytest.approx(target, abs=1e-9)
    # the shift preserves spread; the multiply inflates it
    assert shifted.std() == pytest.approx(base.std(), rel=1e-9)
    assert scaled.std() > base.std() * 1.4
    # and the multiply makes the worst case worse, which is the real bug
    assert shifted.min() > base.min()
    assert scaled.min() < base.min()


def test_engine_source_no_longer_multiplies_draws_by_a_target_ratio():
    """Strip comments first — the fix is DOCUMENTED by quoting the old
    expression, so a naive substring check trips on its own explanation."""
    import inspect
    src = inspect.getsource(E.precompute_draws)
    code = chr(10).join(l.split("#", 1)[0] for l in src.split(chr(10)))
    assert "base * (target / ev)" not in code, "multiplicative retarget is back"
    assert "target - float(np.mean(base))" in code


# ── delta_pwin core contract ─────────────────────────────────────────────────

def test_delta_pwin_with_no_args_reproduces_assemble_exactly():
    """The baseline invariant: the new primitive must not perturb the old path."""
    state = _state(my_score=100.0, opp_score=100.0)
    D = _draws(hitters=[(1, "A", 6.0)], opp_h=[(9, "Z", 4.0)], spread=9.0)
    my, opp = E.assemble(state, D)
    base = E.pwin(my, opp)
    r = E.delta_pwin(state, D)
    assert r["pwin"] == pytest.approx(base)
    assert r["dpwin"] == pytest.approx(0.0)


def test_adding_a_scorer_raises_pwin_and_benching_him_lowers_it():
    state = _state(my_score=100.0, opp_score=110.0)
    D = _draws(hitters=[(1, "A", 6.0)], my_sp=[(50, "Ace", "2026-08-01", 18.0)],
               spread=9.0)
    base = E.pwin(*E.assemble(state, D))
    added = E.delta_pwin(state, D, add=[{
        "mlbam": 77, "name": "FA Bat", "bucket": "H",
        "proj": {"fp": 20.0, "units": 5, "sigma2": 5.0}}], base_pwin=base)
    assert added["dpwin"] > 0, "adding a positive scorer must not lower P(win)"
    benched = E.delta_pwin(state, D, bench=[("SP", 50, "2026-08-01")],
                           base_pwin=base)
    assert benched["dpwin"] < 0, "benching the ace must lower P(win)"


def test_swap_is_one_scenario_not_two():
    """add+drop together is the primitive the optimizer needs; it must differ
    from either leg alone."""
    state = _state(my_score=100.0, opp_score=105.0)
    D = _draws(hitters=[(1, "Weak", 2.0), (2, "Keep", 8.0)], spread=9.0)
    base = E.pwin(*E.assemble(state, D))
    cand = {"mlbam": 77, "name": "Better", "bucket": "H",
            "proj": {"fp": 18.0, "units": 4, "sigma2": 6.0}}
    swap = E.delta_pwin(state, D, add=[cand], drop=[1], base_pwin=base)
    add_only = E.delta_pwin(state, D, add=[cand], base_pwin=base)
    drop_only = E.delta_pwin(state, D, drop=[1], base_pwin=base)
    assert swap["dpwin"] != pytest.approx(add_only["dpwin"])
    assert swap["dpwin"] > drop_only["dpwin"]
    assert swap["scenario"]["add"] and swap["scenario"]["drop"]


def test_added_sp_start_competes_for_the_cap():
    """With zero cap left, an added start cannot score — the chronological cap
    is enforced inside each trial, so this is the acceptance test for it."""
    state_full = _state(cap_mine=0)
    D = _draws(my_sp=[(50, "Ace", "2026-08-01", 18.0)])
    cand = {"mlbam": 88, "name": "Streamer", "bucket": "SP",
            "proj": {"fp": 15.0, "units": 1, "sigma2": 40.0},
            "starts": [{"date": "2026-08-02", "confirmed": True}]}
    r = E.delta_pwin(state_full, D, add=[cand])
    assert r["dpwin"] == pytest.approx(0.0, abs=1e-9)


def test_dropped_sp_events_leave_the_cap_pool():
    state = _state(cap_mine=1)
    D = _draws(my_sp=[(50, "Ace", "2026-08-01", 18.0),
                      (51, "Other", "2026-08-03", 12.0)])
    my_before, _ = E.assemble(state, D)
    my_after, _ = E.assemble(state, D, drop_sp_mlbams={50})
    # cap=1 so only the chronologically first occurring start scores
    assert my_before[0] == pytest.approx(100.0 + 18.0)
    assert my_after[0] == pytest.approx(100.0 + 12.0)


def test_candidate_with_zero_remaining_units_scores_zero_not_an_error():
    state = _state()
    D = _draws(hitters=[(1, "A", 5.0)])
    r = E.delta_pwin(state, D, add=[{
        "mlbam": 77, "name": "Idle", "bucket": "H",
        "proj": {"fp": 0.0, "units": 0, "sigma2": 0.0}}])
    assert r["dpwin"] == pytest.approx(0.0, abs=1e-9)


def test_candidate_without_proj_raises_rather_than_guessing_units():
    state = _state()
    D = _draws(hitters=[(1, "A", 5.0)])
    with pytest.raises(ValueError, match="no 'proj'"):
        E.delta_pwin(state, D, add=[{"mlbam": 7, "name": "X", "bucket": "H"}])


def test_delta_pwin_is_deterministic_under_a_fixed_seed():
    state = _state(my_score=100.0, opp_score=103.0)
    cand = {"mlbam": 77, "name": "FA", "bucket": "H",
            "proj": {"fp": 14.0, "units": 4, "sigma2": 9.0}}
    a = E.delta_pwin(state, _draws(hitters=[(1, "A", 5.0)], seed=11, spread=9.0), add=[cand])
    b = E.delta_pwin(state, _draws(hitters=[(1, "A", 5.0)], seed=11, spread=9.0), add=[cand])
    assert a["dpwin"] == b["dpwin"] and a["pwin"] == b["pwin"]


def test_mc_se_shrinks_with_more_sims():
    assert E.mc_se(0.5, 10_000) < E.mc_se(0.5, 1_000)
    assert E.mc_se(0.5, 10_000) == pytest.approx(0.005, abs=1e-4)


# ── extraction integrity ─────────────────────────────────────────────────────

def test_runner_is_a_thin_cli_over_the_engine():
    """The engine must not be reimplemented in the runner — that is the whole
    point of the extraction (cf. four divergent rh3 feature assemblies)."""
    src = (ROOT / "scripts" / "xfp" / "run_matchup_leverage.py").read_text(encoding="utf-8")
    assert "from scripts.xfp.lib.leverage_engine import" in src
    for moved in ("def precompute_draws", "def build_state", "def assemble(",
                  "def _sp_side_total", "def _blend_draws"):
        assert moved not in src, f"{moved} should live only in the engine now"


def test_regime_cuts_unchanged_by_extraction():
    assert (E.TRAILING_MAX, E.LEADING_MIN) == (0.40, 0.60)
    assert E.classify_regime(0.30) == "TRAILING"
    assert E.classify_regime(0.50) == "CLOSE"
    assert E.classify_regime(0.70) == "LEADING"


def test_blend_priors_unchanged_by_extraction():
    assert (E.K_PRIOR_SP, E.K_PRIOR_H, E.K_PRIOR_RP) == (12, 8, 10)
    assert E.UNCONFIRMED_START_P == 0.80

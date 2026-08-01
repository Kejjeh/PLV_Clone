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


def test_identity_less_candidates_are_scored_independently():
    """C1 (2026-08-01): two candidates whose mlbam never resolved (None) must
    NOT collapse onto one cached draw object. Under the sentinel-0 cache key,
    the second identity-less candidate literally received the first's draws —
    wrong name, wrong mean — and its dpwin moved with pool order.

    Spec: two identity-less candidates with different projections are scored
    independently — each scored distribution reflects its own projected mean,
    and swapping pool order changes neither."""
    state = _state()

    def score(order):
        D = _draws(hitters=[(1, "Rostered", 5.0)])
        out = {}
        for name, fp in order:
            cand = {"mlbam": None, "name": name, "bucket": "H",
                    "proj": {"fp": fp, "units": 4, "sigma2": 16.0}}
            rec = E.ensure_candidate_draws(state, D, cand)
            out[name] = (rec["name"], float(rec["arr"].mean()))
        return out

    fwd = score([("Ghost A", 12.0), ("Ghost B", 40.0)])
    rev = score([("Ghost B", 40.0), ("Ghost A", 12.0)])

    # each candidate gets back ITS OWN record, not a cache-mate's
    assert fwd["Ghost A"][0] == "Ghost A"
    assert fwd["Ghost B"][0] == "Ghost B"
    # each scored distribution reflects its own projected mean (no emp history
    # for an identity-less candidate -> pure parametric at fp; MC SE ~0.06)
    assert fwd["Ghost A"][1] == pytest.approx(12.0, abs=1.0)
    assert fwd["Ghost B"][1] == pytest.approx(40.0, abs=1.0)
    # and pool order changes neither
    for k in fwd:
        assert fwd[k] == pytest.approx(rev[k]), f"candidate {k} moved with order"


def test_optimizer_warns_loudly_when_candidates_fail_to_resolve(monkeypatch, capsys):
    """C1 visibility companion (2026-08-01): resolve_candidate_mlbams may
    legitimately leave mlbam=None — name-fallback identity keeps such
    candidates safe downstream — but it must SAY how many, because a silent
    None is exactly how identity-less candidates entered the dpwin path
    unnoticed. Visibility only: the values are unchanged."""
    WO = pytest.importorskip("run_weekly_optimizer")
    import plv_clone.utils.name_match as NM

    def _unresolvable(*a, **k):
        raise ValueError("ambiguous")
    monkeypatch.setattr(NM, "resolve_batter_id", _unresolvable)
    monkeypatch.setattr(NM, "resolve_pitcher_id", _unresolvable)

    cands = [
        {"name": "Ghost A", "bucket": "H", "team": "", "espn_pos": "OF"},
        {"name": "Ghost B", "bucket": "SP", "team": "", "starts": []},
    ]
    WO.resolve_candidate_mlbams({}, cands)
    assert all(c["mlbam"] is None for c in cands), "values must not change"
    out = capsys.readouterr().out.lower()
    assert "unresolved" in out and "2" in out, (
        "a nonzero unresolved count must be printed, never silent")


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


def test_matchup_factor_scales_location_not_the_finished_draw():
    """The defect's signature: a pure multiplicative rescale leaves P(FP<=0)
    COMPLETELY INVARIANT to the matchup, because scaling cannot move mass across
    zero. Location scaling makes it monotone with a meaningful spread.

    Mirror of tests/test_sp_sampler_tail_2026_07_29.py::
    test_opp_factor_scales_location_not_the_finished_draw, at the same F2 panel
    median (mu=9.86, sigma=8.73) so the two engines are checked against one
    reference point.
    """
    mu, sigma, n = 9.86, 8.73, 120_000
    emp = list(np.random.default_rng(0).normal(mu, sigma, 30))
    factors = (0.83, 0.90, 1.00, 1.10, 1.20)

    mult, shift = [], []
    for f in factors:
        base = E._blend_draws(np.random.default_rng(7), emp, mu, sigma,
                              E.K_PRIOR_SP, n)
        ev, target = float(base.mean()), mu * f
        mult.append(float(((base * (target / ev)) <= 0).mean()))
        shift.append(float(((base + (target - ev)) <= 0).mean()))

    # the OLD treatment is blind to the matchup
    assert max(mult) - min(mult) < 1e-9, (
        f"multiplicative rescale should be invariant, got spread "
        f"{max(mult) - min(mult):.6f}")
    # the NEW treatment is monotone and materially different
    assert all(shift[i] > shift[i + 1] for i in range(len(shift) - 1)), shift
    assert (max(shift) - min(shift)) > 0.03, (
        f"location scaling must move P(FP<=0) meaningfully, got "
        f"{max(shift) - min(shift):.4f}")


def test_matchup_factor_holds_sigma_fixed():
    """A multiply scales the SD along with the mean (despite the old comment
    claiming variance shape was preserved); a shift genuinely holds it."""
    mu, sigma, n = 9.86, 8.73, 120_000
    emp = list(np.random.default_rng(0).normal(mu, sigma, 30))
    base = E._blend_draws(np.random.default_rng(7), emp, mu, sigma,
                          E.K_PRIOR_SP, n)
    ev, target = float(base.mean()), mu * 1.20
    assert (base + (target - ev)).std() == pytest.approx(base.std(), rel=1e-9)
    assert (base * (target / ev)).std() > base.std() * 1.20


def test_weekly_total_downside_responds_to_the_matchup():
    """The consumer-facing consequence: p05/p10 of a 6-start week must widen
    when the matchup is unfavorable and tighten when it is favorable. Under the
    multiply both moved the WRONG way relative to truth."""
    mu, sigma, n = 9.86, 8.73, 40_000
    emp = list(np.random.default_rng(0).normal(mu, sigma, 30))

    def weekly(factor, shift_it):
        tot = np.zeros(n)
        for k in range(6):
            b = E._blend_draws(np.random.default_rng(100 + k), emp, mu, sigma,
                               E.K_PRIOR_SP, n)
            ev, target = float(b.mean()), mu * factor
            tot += (b + (target - ev)) if shift_it else (b * (target / ev))
        return np.percentile(tot, 5), np.percentile(tot, 10), tot.mean()

    bad_s, good_s = weekly(0.83, True), weekly(1.20, True)
    bad_m, good_m = weekly(0.83, False), weekly(1.20, False)

    # means agree by construction under both treatments
    assert bad_s[2] == pytest.approx(bad_m[2], rel=1e-6)
    assert good_s[2] == pytest.approx(good_m[2], rel=1e-6)
    # but the tails do not: the multiply is optimistic in a bad matchup and
    # pessimistic in a good one — backwards in both directions
    assert bad_m[0] > bad_s[0], "multiply overstates the floor in a bad matchup"
    assert good_m[0] < good_s[0], "multiply understates the floor in a good matchup"
    assert (good_s[0] - bad_s[0]) > (good_m[0] - bad_m[0]), (
        "location scaling must make the floor MORE matchup-sensitive")


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

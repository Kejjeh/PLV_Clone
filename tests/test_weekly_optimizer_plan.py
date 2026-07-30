"""Regression guards for run_weekly_optimizer's plan semantics (fix 2026-07-30).

The defects being pinned, both from the 2026-07-30 10:00 production run
(dpwin run 2026-07-30T100002_7):

1. GREEDY UNDO / DISHONEST MARGINALS. ``delta_pwin`` always scores against the
   ORIGINAL state, but the greedy loop pretended its step-2 scores were
   "re-scored against the updated roster". Worse, a step-2 "drop" of the player
   step 1 added silently NO-OPed inside ``_resolve_keys`` (an unrostered name
   matches no draw key), so the run recommended "ADD Jeffers / DROP Pederson
   +8.84pp" — an undo whose +8.84 was really a free add scored vs base, and the
   displayed running P(win) summed base-relative numbers to 56.4% for what was
   a one-hitter endpoint. Fixed: cumulative scoring (original roster + all
   prior adds − all prior drops + this move), marginal ``dpwin``, prior adds
   excluded from the droppable pool.

2. PAIR CHECK DISCARDED. The console printed "best +16.98pp" for the jointly
   evaluated pair and neither persisted nor adopted it; the JSON carried only
   the flawed greedy sequence. Fixed: ``assemble_plan`` adopts the pair when it
   beats the greedy sequence's TRUE total by more than the pair's MC se, and
   ``build_payload`` persists ``pair_check`` either way.

Everything here runs on a toy additive P(win) model injected through the
``_dp`` seam — no ESPN, no draws, no parquet. The regime tie-break
(2×mc_se → boom%) is intended behavior and is deliberately NOT exercised here
(fixture mc_se is tiny so no ties form); see the module docstring's contract.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import run_weekly_optimizer as WO  # noqa: E402


# ── toy world ────────────────────────────────────────────────────────────────
# A legal BrownU roster shape: 13 H covering every required slot, 5 SP, 4 RP.

def _hitter(name, mlbam, pos):
    return {"name": name, "mlbam": mlbam, "bucket": "H", "espn_pos": pos,
            "slot": pos, "eligible": {pos, "UTIL"}, "on_il": False,
            "injury_status": ""}


def _pitcher(name, mlbam, bucket):
    return {"name": name, "mlbam": mlbam, "bucket": bucket, "espn_pos": bucket,
            "slot": "P", "eligible": {bucket, "P"}, "on_il": False,
            "injury_status": ""}


def _roster():
    hitters = [
        _hitter("My C", 100, "C"), _hitter("My 1B", 101, "1B"),
        _hitter("My 2B", 102, "2B"), _hitter("My 3B", 103, "3B"),
        _hitter("My SS", 104, "SS"), _hitter("My OF1", 105, "OF"),
        _hitter("My OF2", 106, "OF"), _hitter("My OF3", 107, "OF"),
        _hitter("My OF4", 108, "OF"), _hitter("My U1", 109, "1B"),
        _hitter("My U2", 110, "2B"), _hitter("My U3", 111, "3B"),
        _hitter("My U4", 112, "OF"),
    ]
    sps = [_pitcher(f"My SP{i}", 200 + i, "SP") for i in range(1, 6)]
    rps = [_pitcher(f"My RP{i}", 300 + i, "RP") for i in range(1, 5)]
    return hitters + sps + rps


def _cand(name, mlbam):
    return {"name": name, "mlbam": mlbam, "bucket": "H", "espn_pos": "OF",
            "eligible": {"OF", "UTIL"}, "team": "TST",
            "proj": {"fp": 8.0, "units": 3.0}, "fp": 8.0, "units": 3.0,
            "per_unit": 8.0 / 3.0, "pct_owned": 1.0, "injury_status": "",
            "starts": []}


def _state(roster):
    # only the keys the search actually touches
    return {"my_roster": roster,
            "my_hitters": [{"name": p["name"], "mlbam": p["mlbam"], "n_games": 3}
                           for p in roster if p["bucket"] == "H"],
            "cap_remaining_mine": 7, "days_remaining": 4, "period": 17}


BASE_P = 0.40


def _fake_dp(contribs, interactions=None, mc_se=1e-6):
    """A fake ``delta_pwin`` over an additive toy model.

    pwin = BASE_P + Σ contrib(adds) − Σ contrib(drops) + Σ interaction(pairs).
    Drop keys arrive as mlbam-or-name exactly like production; both index
    ``contribs``. Unknown drop keys contribute 0 — mirroring the engine's
    silent no-op, so the undo temptation exists in the toy world too.
    """
    interactions = interactions or {}

    def dp(state, D, *, add=(), drop=(), bench=(), base_pwin=None):
        p = BASE_P
        names = []
        for a in add:
            p += contribs.get(a["name"], 0.0)
            names.append(a["name"])
        for d in drop:
            p -= contribs.get(d, 0.0)
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                key = frozenset((names[i], names[j]))
                p += interactions.get(key, 0.0)
        return {"pwin": p, "dpwin": p - BASE_P, "mc_se": mc_se,
                "scenario": {"add": names, "drop": list(drop)}}

    return dp


def _run(contribs, interactions=None, *, max_moves=2, cands=None):
    roster = _roster()
    state = _state(roster)
    cands = cands if cands is not None else [
        _cand("FA Alpha", 900), _cand("FA Beta", 901), _cand("FA Gamma", 902)]
    dp = _fake_dp(contribs, interactions)
    res = WO.optimize(state, D={}, base_p=BASE_P, regime="CLOSE", cands=cands,
                      max_moves=max_moves, verbose=False, _dp=dp)
    return res


# ── 1. undo suppression ──────────────────────────────────────────────────────

def test_step_two_can_never_drop_the_player_step_one_added():
    """THE regression. Alpha is the best add; in the pre-fix code round 2's
    droppables included Alpha (now on the virtual roster) and dropping him
    no-oped into a free +Beta score. Post-fix, no round-2 row may drop Alpha,
    and the chosen plan must not contain an undo."""
    res = _run({"FA Alpha": 0.09, "FA Beta": 0.08, "FA Gamma": 0.02})
    assert len(res["chosen"]) == 2
    step1, step2 = res["chosen"]
    assert step1["add"]["name"] == "FA Alpha"
    assert step2["drop"]["name"] != "FA Alpha"
    # and not just the chosen row: the whole round-2 surface excludes him
    round2 = res["rounds"][1]
    assert round2, "round 2 scored no rows — fixture broke"
    assert all(r["drop"]["name"] != "FA Alpha" for r in round2)


def test_prior_drops_stay_dropped_in_later_scoring():
    """Round 2 must score scenarios as original + prior add − prior drop +
    this move: the step-1 drop's contribution must be absent from every
    round-2 pwin. With every roster player worth 0.01, step 2's endpoint
    reflects BOTH drops."""
    contribs = {"FA Alpha": 0.09, "FA Beta": 0.08}
    contribs.update({p["name"]: 0.01 for p in _roster()})
    contribs.update({p["mlbam"]: 0.01 for p in _roster()})
    res = _run(contribs)
    step1, step2 = res["chosen"]
    # endpoint: base + 0.09 + 0.08 − 0.01 − 0.01
    assert step2["pwin"] == pytest.approx(BASE_P + 0.15, abs=1e-9)


# ── 2. honest marginals + running P(win) ─────────────────────────────────────

def test_dpwin_is_marginal_and_sums_to_the_endpoint():
    contribs = {"FA Alpha": 0.09, "FA Beta": 0.08}
    contribs.update({p["name"]: 0.01 for p in _roster()})
    contribs.update({p["mlbam"]: 0.01 for p in _roster()})
    res = _run(contribs)
    step1, step2 = res["chosen"]
    assert step1["dpwin"] == pytest.approx(0.08, abs=1e-9)   # 0.09 − 0.01 drop
    assert step2["dpwin"] == pytest.approx(0.07, abs=1e-9)   # 0.08 − 0.01 drop
    # marginals sum to the true endpoint — never base + base-relative numbers
    assert step1["dpwin"] + step2["dpwin"] == pytest.approx(
        step2["pwin"] - BASE_P, abs=1e-9)
    # and the vs-base bookkeeping is carried separately for the history log
    assert step2["dpwin_from_base"] == pytest.approx(0.15, abs=1e-9)


def test_round_one_marginal_equals_from_base():
    """No priors -> the two dpwin flavors coincide (old behavior preserved)."""
    res = _run({"FA Alpha": 0.09})
    r0 = res["rounds"][0]
    for r in r0:
        assert r["dpwin"] == pytest.approx(r["dpwin_from_base"], abs=1e-12)


# ── 3. pair persistence ──────────────────────────────────────────────────────

def test_pair_check_is_persisted_in_the_payload_even_when_not_adopted():
    contribs = {"FA Alpha": 0.09, "FA Beta": 0.08, "FA Gamma": 0.02}
    res = _run(contribs)
    plan = WO.assemble_plan(res, BASE_P)
    payload = WO.build_payload(plan=plan, res=res, base_p=BASE_P,
                               regime="CLOSE", period=17, sims=10000, seed=7,
                               cap_remaining=7, wv={})
    pc = payload["pair_check"]
    assert pc is not None and pc["n_combos"] > 0
    assert pc["adopted"] is False                      # greedy already optimal
    best = pc["best"]
    assert {m["add"] for m in best["moves"]} == {"FA Alpha", "FA Beta"}
    for k in ("dpwin", "pwin", "mc_se", "sum_solo", "interaction"):
        assert k in best
    # no interactions in this toy world: interaction term ~ 0
    assert best["interaction"] == pytest.approx(0.0, abs=1e-9)


# ── 4. pair-vs-greedy adoption ───────────────────────────────────────────────

def test_pair_is_adopted_when_it_beats_the_greedy_endpoint():
    """Greedy myopia by construction: Alpha is the best single (+0.10) but
    interacts badly with everything (−0.08), so greedy lands on +0.11 while
    the clean pair Beta+Gamma is worth +0.15. The plan must adopt the pair,
    with marginals that sum to the pair total."""
    contribs = {"FA Alpha": 0.10, "FA Beta": 0.09, "FA Gamma": 0.06}
    inter = {frozenset(("FA Alpha", "FA Beta")): -0.08,
             frozenset(("FA Alpha", "FA Gamma")): -0.08}
    res = _run(contribs, inter)
    # sanity of the trap: greedy took Alpha first and ended below the pair
    assert res["chosen"][0]["add"]["name"] == "FA Alpha"
    greedy_total = res["chosen"][-1]["pwin"] - BASE_P
    assert greedy_total == pytest.approx(0.11, abs=1e-9)

    plan = WO.assemble_plan(res, BASE_P)
    assert plan["source"] == "pair_check"
    assert plan["total_dpwin"] == pytest.approx(0.15, abs=1e-9)
    assert [m["add"]["name"] for m in plan["moves"]] == ["FA Beta", "FA Gamma"]
    m1, m2 = plan["moves"]
    assert m1["dpwin"] == pytest.approx(0.09, abs=1e-9)      # solo
    assert m2["dpwin"] == pytest.approx(0.06, abs=1e-9)      # pair − solo1
    assert m1["dpwin"] + m2["dpwin"] == pytest.approx(plan["total_dpwin"])
    assert m2["pwin_after"] == pytest.approx(BASE_P + 0.15, abs=1e-9)
    payload = WO.build_payload(plan=plan, res=res, base_p=BASE_P,
                               regime="CLOSE", period=17, sims=10000, seed=7,
                               cap_remaining=7, wv={})
    assert payload["plan_source"] == "pair_check"
    assert payload["pair_check"]["adopted"] is True
    assert payload["plan_total_dpwin"] == pytest.approx(0.15, abs=1e-9)


def test_greedy_is_kept_when_the_pair_is_not_better():
    """No interactions: honest greedy finds the same endpoint the pair does,
    the adoption margin is ~0 (inside the pair's mc_se), and the sequenced
    greedy plan — whose ordering encodes the regime tie-break — is kept."""
    res = _run({"FA Alpha": 0.09, "FA Beta": 0.08, "FA Gamma": 0.02})
    plan = WO.assemble_plan(res, BASE_P)
    assert plan["source"] == "greedy"
    assert plan["total_dpwin"] == pytest.approx(0.17, abs=1e-9)
    assert plan["pwin_final"] == pytest.approx(BASE_P + 0.17, abs=1e-9)


def test_hold_when_no_positive_move_exists():
    res = _run({"FA Alpha": -0.02, "FA Beta": -0.05, "FA Gamma": -0.01})
    assert res["chosen"] == []
    plan = WO.assemble_plan(res, BASE_P)
    assert plan["source"] == "hold" and plan["moves"] == []
    assert plan["pwin_final"] == pytest.approx(BASE_P)


# ── 5. adversarial-review round 2 (2026-07-30): joint legality + gates ───────

def _roster_two_catchers():
    """13 H including TWO catchers — each singly droppable, jointly not."""
    r = _roster()
    # swap one utility hitter for a second catcher
    r = [p for p in r if p["name"] != "My U4"]
    c2 = _hitter("My C2", 113, "C")
    return r + [c2]


def test_jointly_illegal_pair_is_blocked_from_sweep_and_adoption():
    """BLOCKING regression: two singly-legal legs whose drops are the two
    catchers must never form a pair — dropping both leaves nobody at C. The
    trap is armed by making the catchers the most attractive drops, so the
    same-drop fallback lands leg b on the second catcher."""
    contribs = {"FA Alpha": 0.10, "FA Beta": 0.09}
    contribs.update({p["name"]: 0.02 for p in _roster_two_catchers()})
    contribs.update({p["mlbam"]: 0.02 for p in _roster_two_catchers()})
    for c in ("My C", "My C2"):
        contribs[c] = -0.01                    # dropping a catcher LOOKS best
    contribs[100] = -0.01
    contribs[113] = -0.01
    # a poisonous interaction makes the pair beat greedy IF it were allowed
    inter = {frozenset(("FA Alpha", "FA Beta")): 0.05}
    roster = _roster_two_catchers()
    state = _state(roster)
    cands = [_cand("FA Alpha", 900), _cand("FA Beta", 901)]
    dp = _fake_dp(contribs, inter)
    res = WO.optimize(state, D={}, base_p=BASE_P, regime="CLOSE", cands=cands,
                      max_moves=2, verbose=False, _dp=dp)
    # every surviving pair keeps at least one catcher
    for pr in res["pairs"]:
        drops = {m["drop"]["name"] for m in pr["moves"]}
        assert not {"My C", "My C2"} <= drops, (
            "a pair dropping BOTH catchers survived the joint legality check")
    plan = WO.assemble_plan(res, BASE_P)
    if plan["source"] == "pair_check":
        drops = {m["drop"]["name"] for m in plan["moves"]}
        assert not {"My C", "My C2"} <= drops


def test_max_moves_one_never_yields_a_two_move_plan():
    """IMPORTANT regression: `--max-moves 1` caps the PLAN, and a pair is two
    moves — the sweep must not run at all."""
    contribs = {"FA Alpha": 0.10, "FA Beta": 0.09, "FA Gamma": 0.06}
    inter = {frozenset(("FA Alpha", "FA Beta")): -0.08,
             frozenset(("FA Alpha", "FA Gamma")): -0.08}
    res = _run(contribs, inter, max_moves=1)
    assert res["pairs"] == []
    plan = WO.assemble_plan(res, BASE_P)
    assert plan["source"] != "pair_check"
    assert len(plan["moves"]) <= 1


def test_pair_item_two_dpwin_from_base_is_the_cumulative_endpoint():
    """dpwin_from_base means endpoint-vs-base on EVERY plan item (greedy and
    pair alike) — not one item carrying a solo score under the same name."""
    contribs = {"FA Alpha": 0.10, "FA Beta": 0.09, "FA Gamma": 0.06}
    inter = {frozenset(("FA Alpha", "FA Beta")): -0.08,
             frozenset(("FA Alpha", "FA Gamma")): -0.08}
    res = _run(contribs, inter)
    plan = WO.assemble_plan(res, BASE_P)
    assert plan["source"] == "pair_check"
    m1, m2 = plan["moves"]
    assert m2["dpwin_from_base"] == pytest.approx(plan["total_dpwin"], abs=1e-9)
    assert m1["dpwin_from_base"] == pytest.approx(m1["dpwin"], abs=1e-9)

"""Offline tests for the decision-console engine (scripts/xfp/lib/decision_console.py).

Everything runs with hand-built boards / roster / FA fakes and a hand-built
week_ctx — no ESPN, no MLB Stats API, no CSV reads. Fixture style follows
tests/test_period_meta.py / tests/test_xfp_boards_offline.py.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp" / "lib"))
sys.path.insert(0, str(ROOT / "src"))

import decision_console as dc

TODAY = date(2026, 7, 11)
WEEK_START = date(2026, 7, 6)
WEEK_END = date(2026, 7, 19)


# ── fakes ────────────────────────────────────────────────────────────────────
class _FakePlayer:
    def __init__(self, name, playerId, position, eligibleSlots, proTeam="NYM",
                 injured=False, injuryStatus="ACTIVE", percent_owned=1.2):
        self.name = name
        self.playerId = playerId
        self.position = position
        self.eligibleSlots = eligibleSlots
        self.proTeam = proTeam
        self.injured = injured
        self.injuryStatus = injuryStatus
        self.percent_owned = percent_owned


def _roster_df(rows):
    cols = ["player_name", "player_id", "position", "pro_team", "eligible_slots",
            "lineup_slot", "injured", "injury_status", "return_date"]
    return pd.DataFrame(rows, columns=cols)


def _sp_board(rows):
    cols = ["owner", "name", "team", "own", "per_start", "stuff", "src", "vol",
            "inj", "ret", "xfp_ros", "xfp_po"]
    return pd.DataFrame(rows, columns=cols)


def _hit_board(rows):
    cols = ["owner", "name", "team", "own", "slots", "per_game", "rank",
            "signal", "etfr", "src", "vol", "inj", "ret", "xfp_ros", "xfp_po"]
    df = pd.DataFrame(rows, columns=cols)
    df["buckets"] = df["slots"].apply(
        lambda s: dc.B.buckets_for(s))
    return df


def _empty_hit_board():
    return _hit_board([])


def _empty_rprs2():
    return pd.DataFrame(columns=["pitcher", "name_api", "xfp_ros", "role_lag1",
                                 "sv_2026", "hld_2026", "signal"])


def _pmeta(sp_cap=16, weeks=2):
    return {"period": 15, "weeks": weeks, "sp_cap": sp_cap,
            "week_start": WEEK_START, "week_end": WEEK_END, "covered": True}


def _ctx(sp_starts, banked, sp_cap=16, schedules=None, team_map=None):
    return {"pmeta": _pmeta(sp_cap=sp_cap), "banked_mine": banked,
            "schedules_by_team": schedules or {},
            "sp_starts_by_pitcher": sp_starts, "today": TODAY,
            "source": "matchup", "team_map": team_map or {}}


def _start(d, opp="BAL", confirmed=True):
    return {"date": d, "opp_team": opp, "confirmed": confirmed}


def _build(**kw):
    """build_console_data with offline-safe defaults."""
    kw.setdefault("roster", _roster_df([]))
    kw.setdefault("fas", [])
    kw.setdefault("sp_board", _sp_board([]))
    kw.setdefault("hitter_board", _empty_hit_board())
    kw.setdefault("rprs2", _empty_rprs2())
    kw.setdefault("role_detector", lambda p: "RP")
    kw.setdefault("id_resolver", lambda name, team=None, role=None: None)
    kw.setdefault("starts_fetcher", lambda *a, **k: {})
    kw.setdefault("today", TODAY)
    return dc.build_console_data(**kw)


def _bucket(data, key):
    return next(b for b in data["buckets"] if b["key"] == key)


def _player(data, bucket, name):
    return next(p for p in _bucket(data, bucket)["players"] if p["name"] == name)


@pytest.fixture(autouse=True)
def _no_extra_sp_maps(monkeypatch):
    """Keep _extra_sp_rate offline (no rp3 CSV read)."""
    monkeypatch.setattr(dc, "_EXTRA_SP_MAPS", [])


# ── 1-2: cap-marginal engine ─────────────────────────────────────────────────
IDS = {"My Ace": 100, "Two Start Guy": 200, "Weak Arm": 101, "Strong Arm": 102,
       "Other FA": 201}


def _sp_resolver(name, team=None, role=None):
    return IDS.get(name)


def test_cap_marginal_asg_banked_15_of_16_two_start_fa():
    """cap 16, banked 15 -> one slot; a 2-start FA @12 is worth 12.0 and his
    second start is counts:false."""
    sp = _sp_board([
        dict(owner="MINE", name="My Ace", team="PHI", own="", per_start=15.0,
             stuff=None, src="Stuff+", vol=None, inj="", ret="",
             xfp_ros=300.0, xfp_po=60.0),
        dict(owner="FA", name="Two Start Guy", team="SD", own=4.0,
             per_start=12.0, stuff=None, src="rp3_dd", vol=None, inj="",
             ret="", xfp_ros=250.0, xfp_po=50.0),
    ])
    ctx = _ctx({200: [_start("2026-07-13"), _start("2026-07-18")]}, banked=15)
    data = _build(sp_board=sp, id_resolver=_sp_resolver, week_ctx=ctx)

    assert data["week"]["sp_cap"] == 16
    assert data["week"]["banked_mine"] == 15
    assert data["week"]["cap_room"] == 1
    fa = _player(data, "SP", "Two Start Guy")
    assert fa["xfp_week_marginal"] == 12.0
    counts = [s["counts"] for s in fa["week_detail"]["starts"]]
    assert counts == [True, False]
    assert "TWO_START" in fa["flags"]


def test_over_cap_all_fa_marginals_zero():
    sp = _sp_board([
        dict(owner="MINE", name="My Ace", team="PHI", own="", per_start=15.0,
             stuff=None, src="Stuff+", vol=None, inj="", ret="",
             xfp_ros=300.0, xfp_po=60.0),
        dict(owner="FA", name="Two Start Guy", team="SD", own=4.0,
             per_start=12.0, stuff=None, src="rp3_dd", vol=None, inj="",
             ret="", xfp_ros=250.0, xfp_po=50.0),
    ])
    ctx = _ctx({100: [_start("2026-07-12")],
                200: [_start("2026-07-13"), _start("2026-07-18")]}, banked=16)
    data = _build(sp_board=sp, id_resolver=_sp_resolver, week_ctx=ctx)

    assert data["week"]["cap_room"] == 0
    assert _player(data, "SP", "Two Start Guy")["xfp_week_marginal"] == 0.0
    mine = _player(data, "SP", "My Ace")
    assert mine["xfp_week"] == 0.0                      # banked ate the cap
    assert [s["counts"] for s in mine["week_detail"]["starts"]] == [False]


# ── 3: pairwise ≠ add-only ───────────────────────────────────────────────────
def test_pairwise_delta_exceeds_add_only_when_drop_frees_slot():
    """banked 14/16 (2 slots). Base: mine start d1 @10 counted. Add-only FA
    (2 starts @12, d2/d3): counted 10+12 -> marginal +12. Pair (drop mine):
    24 - 10 = +14."""
    sp = _sp_board([
        dict(owner="MINE", name="Weak Arm", team="PHI", own="", per_start=10.0,
             stuff=None, src="rp3_dd", vol=None, inj="", ret="",
             xfp_ros=150.0, xfp_po=30.0),
        dict(owner="FA", name="Two Start Guy", team="SD", own=4.0,
             per_start=12.0, stuff=None, src="rp3_dd", vol=None, inj="",
             ret="", xfp_ros=250.0, xfp_po=50.0),
    ])
    ctx = _ctx({101: [_start("2026-07-12")],
                200: [_start("2026-07-13"), _start("2026-07-18")]}, banked=14)
    data = _build(sp_board=sp, id_resolver=_sp_resolver, week_ctx=ctx)

    fa = _player(data, "SP", "Two Start Guy")
    assert fa["xfp_week_marginal"] == 12.0
    pw = _bucket(data, "SP")["pair_week_deltas"]
    assert pw[f"m-101|m-200"] == 14.0


# ── 4: chronological first-cap rule ─────────────────────────────────────────
def test_chronological_first_cap_earlier_weaker_start_counts():
    sp = _sp_board([
        dict(owner="MINE", name="Weak Arm", team="PHI", own="", per_start=5.0,
             stuff=None, src="rp3_dd", vol=None, inj="", ret="",
             xfp_ros=100.0, xfp_po=20.0),
        dict(owner="MINE", name="Strong Arm", team="LAD", own="",
             per_start=20.0, stuff=None, src="Stuff+", vol=None, inj="",
             ret="", xfp_ros=400.0, xfp_po=80.0),
    ])
    ctx = _ctx({101: [_start("2026-07-12")],
                102: [_start("2026-07-14")]}, banked=15)   # one slot left
    data = _build(sp_board=sp, id_resolver=_sp_resolver, week_ctx=ctx)

    assert _player(data, "SP", "Weak Arm")["xfp_week"] == 5.0     # earlier
    assert _player(data, "SP", "Strong Arm")["xfp_week"] == 0.0   # capped out


# ── 5: LOW-CONF FA excluded from recs, kept in tables ───────────────────────
def test_lowconf_fa_excluded_from_recs_shown_in_table():
    hit = _hit_board([
        dict(owner="MINE", name="My Weak OF", team="NYY", own="",
             slots=["OF", "UTIL"], per_game=2.0, rank=200, signal="fade",
             etfr=80.0, src="id", vol=None, inj="", ret="",
             xfp_ros=100.0, xfp_po=20.0),
        dict(owner="FA", name="Stash Elite", team="LAD", own=40.0,
             slots=["OF", "UTIL"], per_game=5.0, rank=None, signal="stash",
             etfr=None, src="talent_prior", vol=None, inj="", ret="",
             xfp_ros=400.0, xfp_po=90.0),
        dict(owner="FA", name="Modeled Good", team="SD", own=10.0,
             slots=["OF", "UTIL"], per_game=4.0, rank=30, signal="hold",
             etfr=250.0, src="id", vol=None, inj="", ret="",
             xfp_ros=300.0, xfp_po=70.0),
    ])
    data = _build(hitter_board=hit)

    of = _bucket(data, "OF")
    names = {p["name"] for p in of["players"]}
    assert "Stash Elite" in names                       # visible in table
    assert "LOW_CONF" in _player(data, "OF", "Stash Elite")["flags"]
    assert of["recs"], "expected a rec"
    add_ids = {r["add_id"] for r in of["recs"]}
    stash_id = _player(data, "OF", "Stash Elite")["id"]
    modeled_id = _player(data, "OF", "Modeled Good")["id"]
    assert stash_id not in add_ids
    assert modeled_id in add_ids


# ── 6: UTIL dedup in headline recs ───────────────────────────────────────────
def test_util_dedup_single_headline_entry():
    hit = _hit_board([
        dict(owner="MINE", name="My Weak OF", team="NYY", own="",
             slots=["OF", "UTIL"], per_game=2.0, rank=200, signal="fade",
             etfr=80.0, src="id", vol=None, inj="", ret="",
             xfp_ros=100.0, xfp_po=20.0),
        dict(owner="FA", name="Modeled Good", team="SD", own=10.0,
             slots=["OF", "UTIL"], per_game=4.0, rank=30, signal="hold",
             etfr=250.0, src="id", vol=None, inj="", ret="",
             xfp_ros=300.0, xfp_po=70.0),
    ])
    data = _build(hitter_board=hit)

    # the same swap appears in both OF and UTIL bucket recs...
    assert _bucket(data, "OF")["recs"] and _bucket(data, "UTIL")["recs"]
    # ...but exactly once in the headline
    pairs = [(r["drop_id"], r["add_id"]) for r in data["headline_recs"]]
    assert len(pairs) == len(set(pairs)) == 1


# ── 7: Muncy collision — same-name FAs stay distinct ────────────────────────
def test_same_name_fas_distinct_ids():
    hit = _hit_board([
        dict(owner="FA", name="Max Muncy", team="LAD", own=50.0,
             slots=["3B", "UTIL"], per_game=3.5, rank=40, signal="hold",
             etfr=200.0, src="id", vol=None, inj="", ret="",
             xfp_ros=250.0, xfp_po=55.0),
        dict(owner="FA", name="Max Muncy", team="OAK", own=2.0,
             slots=["C", "UTIL"], per_game=1.5, rank=300, signal="fade",
             etfr=60.0, src="id", vol=None, inj="", ret="",
             xfp_ros=90.0, xfp_po=18.0),
    ])
    fas = [
        _FakePlayer("Max Muncy", 5001, "3B", ["3B", "UTIL"], proTeam="LAD"),
        _FakePlayer("Max Muncy", 5002, "C", ["C", "UTIL"], proTeam="OAK"),
    ]
    data = _build(hitter_board=hit, fas=fas)

    util = [p for p in _bucket(data, "UTIL")["players"]
            if p["name"] == "Max Muncy"]
    assert len(util) == 2
    assert {p["espn_id"] for p in util} == {5001, 5002}
    assert len({p["id"] for p in util}) == 2


# ── 8: Detmers dual-eligible routes to SP, not RP ────────────────────────────
def test_dual_eligible_detected_sp_lands_in_sp_not_rp(monkeypatch):
    detmers = _FakePlayer("Reid Detmers", 6001, "RP", ["SP", "RP"],
                          proTeam="LAA")
    # give the extras path a real rp3 rate (rate-less FA extras are dropped
    # as noise — only arms the model can score surface as role-corrected rows)
    monkeypatch.setattr(
        dc, "_EXTRA_SP_MAPS",
        [(*dc.B._build_map(["Reid Detmers"], [11.0]), "rp3_dd")])

    def role(p):
        return "SP" if getattr(p, "name", "") == "Reid Detmers" else "RP"

    data = _build(fas=[detmers], role_detector=role)

    rp_names = {p["name"] for p in _bucket(data, "RP")["players"]}
    sp_names = {p["name"] for p in _bucket(data, "SP")["players"]}
    assert "Reid Detmers" not in rp_names
    assert "Reid Detmers" in sp_names
    row = _player(data, "SP", "Reid Detmers")
    assert "ROLE_SP" in row["flags"]
    assert row["rate"] == 11.0 and row["src"] == "rp3_dd"


def test_rateless_dual_eligible_fa_extra_dropped_as_noise():
    """A dual-eligible FA detected as SP but with NO model rate is dropped
    (noise control) — not shown, and still kept out of the RP bucket."""
    ghost = _FakePlayer("Org Depth Arm", 6002, "RP", ["SP", "RP"], proTeam="MIA")

    def role(p):
        return "SP" if getattr(p, "name", "") == "Org Depth Arm" else "RP"

    data = _build(fas=[ghost], role_detector=role)
    assert "Org Depth Arm" not in {p["name"]
                                   for p in _bucket(data, "SP")["players"]}
    assert "Org Depth Arm" not in {p["name"]
                                   for p in _bucket(data, "RP")["players"]}


# ── 9-10: MINE retention + BE/IL droppability ────────────────────────────────
def test_mine_below_fa_cut_retained():
    rows = [dict(owner="FA", name=f"FA Guy {i}", team="SD", own=1.0,
                 slots=["OF", "UTIL"], per_game=4.0, rank=i, signal="hold",
                 etfr=200.0, src="id", vol=None, inj="", ret="",
                 xfp_ros=500.0 - i, xfp_po=60.0)
            for i in range(60)]           # more FA than the UTIL cap of 50
    rows.append(dict(owner="MINE", name="My Deep Bench", team="NYY", own="",
                     slots=["OF", "UTIL"], per_game=1.0, rank=400,
                     signal="fade", etfr=30.0, src="id", vol=None, inj="",
                     ret="", xfp_ros=20.0, xfp_po=4.0))
    data = _build(hitter_board=_hit_board(rows))
    names = {p["name"] for p in _bucket(data, "UTIL")["players"]}
    assert "My Deep Bench" in names


def test_bench_droppable_il_slot_not():
    roster = _roster_df([
        ("Bench Bat", 11, "OF", "NYY", ["OF", "UTIL"], "BE", False, "ACTIVE", None),
        ("IL Bat", 12, "OF", "NYY", ["OF", "UTIL"], "IL", True,
         "FIFTEEN_DAY_DL", None),
    ])
    hit = _hit_board([
        dict(owner="MINE", name="Bench Bat", team="NYY", own="",
             slots=["OF", "UTIL"], per_game=2.0, rank=200, signal="fade",
             etfr=80.0, src="id", vol=None, inj="", ret="",
             xfp_ros=100.0, xfp_po=20.0),
        dict(owner="MINE", name="IL Bat", team="NYY", own="",
             slots=["OF", "UTIL"], per_game=1.5, rank=250, signal="fade",
             etfr=60.0, src="id", vol=None, inj="FIFTEEN_DAY_DL", ret="",
             xfp_ros=50.0, xfp_po=10.0),
        dict(owner="FA", name="Modeled Good", team="SD", own=10.0,
             slots=["OF", "UTIL"], per_game=4.0, rank=30, signal="hold",
             etfr=250.0, src="id", vol=None, inj="", ret="",
             xfp_ros=300.0, xfp_po=70.0),
    ])
    data = _build(roster=roster, hitter_board=hit)
    drop_ids = {r["drop_id"] for r in _bucket(data, "OF")["recs"]}
    bench_id = _player(data, "OF", "Bench Bat")["id"]
    il_id = _player(data, "OF", "IL Bat")["id"]
    assert bench_id in drop_ids            # bench = active = droppable
    assert il_id not in drop_ids           # IL slot never a drop rec


# ── 11: week_ctx=None fallback ───────────────────────────────────────────────
def test_week_ctx_none_flat_estimates():
    sp = _sp_board([
        dict(owner="MINE", name="My Ace", team="PHI", own="", per_start=15.0,
             stuff=None, src="Stuff+", vol=None, inj="", ret="",
             xfp_ros=300.0, xfp_po=60.0),
    ])
    data = _build(sp_board=sp, id_resolver=_sp_resolver)
    assert data["week"] is None
    mine = _player(data, "SP", "My Ace")
    assert "WEEK_EST" in mine["flags"]
    # flat: per_start × RATE(per day) × 7 days = per_start × 1.19
    assert mine["xfp_week"] == round(15.0 * dc.B.RATE * 7, 1)


# ── 12: RP bucket — rprs2 source + IL scaling + week unsupported ─────────────
def test_rp_bucket_rprs2_and_il_scaling():
    rprs2 = pd.DataFrame([
        {"pitcher": 700, "name_api": "Healthy Closer", "xfp_ros": 150.0,
         "role_lag1": "closer", "sv_2026": 20, "hld_2026": 0, "signal": "add"},
        {"pitcher": 701, "name_api": "Hurt Setup", "xfp_ros": 100.0,
         "role_lag1": "setup", "sv_2026": 0, "hld_2026": 15, "signal": "hold"},
    ])
    roster = _roster_df([
        ("Healthy Closer", 21, "RP", "NYY", ["RP"], "RP", False, "ACTIVE", None),
    ])
    ret = date(2026, 8, 15)
    fas = [_FakePlayer("Hurt Setup", 7001, "RP", ["RP"], proTeam="SD",
                       injured=True, injuryStatus="FIFTEEN_DAY_DL")]
    resolver = lambda name, team=None, role=None: \
        {"Healthy Closer": 700, "Hurt Setup": 701}.get(name)
    data = _build(roster=roster, fas=fas, rprs2=rprs2, id_resolver=resolver,
                  injury_details={7001: ret})

    rp = _bucket(data, "RP")
    assert rp["axis_support"]["week"] is False
    hc = _player(data, "RP", "Healthy Closer")
    assert hc["xfp_ros"] == 150.0                     # avail ratio 1.0
    assert hc["xfp_week"] is None
    assert hc["src"] == "rprs2"
    assert hc["extras"]["role_lag1"] == "closer"
    hs = _player(data, "RP", "Hurt Setup")
    remaining = (dc.B.SEASON_END - TODAY).days
    avail_days = (dc.B.SEASON_END - ret).days
    assert hs["xfp_ros"] == round(100.0 * avail_days / remaining, 1)
    assert "IL" in hs["flags"]


# ── 13: verdict thresholds are strict > ──────────────────────────────────────
def test_verdict_threshold_boundaries():
    assert dc._verdict(30.0, dc.PAIR_STRONG_FP, dc.PAIR_MODEST_FP) == "MODEST"
    assert dc._verdict(30.1, dc.PAIR_STRONG_FP, dc.PAIR_MODEST_FP) == "STRONG"
    assert dc._verdict(10.0, dc.PAIR_STRONG_FP, dc.PAIR_MODEST_FP) == "MARGINAL"
    assert dc._verdict(50.0, dc.SLOT_STRONG_FP, dc.SLOT_MODEST_FP) == "MODEST"
    assert dc._verdict(50.5, dc.SLOT_STRONG_FP, dc.SLOT_MODEST_FP) == "STRONG"
    assert dc._verdict(20.0, dc.SLOT_STRONG_FP, dc.SLOT_MODEST_FP) == "MARGINAL"


# ── 14: payload schema lock ──────────────────────────────────────────────────
def test_payload_schema_lock():
    sp = _sp_board([
        dict(owner="MINE", name="My Ace", team="PHI", own="", per_start=15.0,
             stuff=None, src="Stuff+", vol=None, inj="", ret="",
             xfp_ros=300.0, xfp_po=60.0),
        dict(owner="FA", name="Two Start Guy", team="SD", own=4.0,
             per_start=12.0, stuff=None, src="rp3_dd", vol=None, inj="",
             ret="", xfp_ros=250.0, xfp_po=50.0),
    ])
    ctx = _ctx({200: [_start("2026-07-13")]}, banked=15)
    data = _build(sp_board=sp, id_resolver=_sp_resolver, week_ctx=ctx)

    assert set(data.keys()) == {
        "schema_version", "generated_at", "source", "today", "season_end",
        "playoff_start", "note", "week", "buckets", "headline_recs", "sim",
        "thresholds"}
    assert data["schema_version"] == 1
    assert [b["key"] for b in data["buckets"]] == [
        "SP", "RP", "C", "1B/3B", "2B/SS", "OF", "UTIL"]
    assert set(data["week"].keys()) == {
        "period", "weeks", "sp_cap", "week_start", "week_end", "covered",
        "banked_mine", "banked_source", "scheduled_mine", "cap_room",
        "week_est"}
    row = _player(data, "SP", "Two Start Guy")
    assert set(row.keys()) == {
        "id", "mlbam", "espn_id", "name", "owner", "team", "own_pct", "slots",
        "rate", "rate_unit", "src", "xfp_ros", "xfp_po", "xfp_week",
        "xfp_week_marginal", "week_detail", "flags", "inj", "ret", "extras"}
    assert set(data["sim"].keys()) == {"mine_ids", "fa_ids_by_bucket"}
    # pairwise key format
    for k in _bucket(data, "SP")["pair_week_deltas"]:
        drop_id, add_id = k.split("|")
        assert drop_id.startswith(("m-", "e-", "n-"))
        assert add_id.startswith(("m-", "e-", "n-"))
    # JSON-serializable end to end
    import json
    json.dumps(data)


# ── 15: renderer smoke ───────────────────────────────────────────────────────
def test_render_console_html_smoke():
    sp = _sp_board([
        dict(owner="MINE", name="My Ace", team="PHI", own="", per_start=15.0,
             stuff=None, src="Stuff+", vol=None, inj="", ret="",
             xfp_ros=300.0, xfp_po=60.0),
        dict(owner="FA", name="Two Start Guy", team="SD", own=4.0,
             per_start=12.0, stuff=None, src="rp3_dd", vol=None, inj="",
             ret="", xfp_ros=250.0, xfp_po=50.0),
    ])
    ctx = _ctx({200: [_start("2026-07-13"), _start("2026-07-18")]}, banked=15)
    data = _build(sp_board=sp, id_resolver=_sp_resolver, week_ctx=ctx)
    html = dc.render_console_html(data, theme="board", page_key="testpage",
                                  default_axis="week")

    assert 'id="dc-testpage"' in html
    assert 'data-axis="week"' in html                    # default axis
    assert data["generated_at"] in html                  # staleness stamp
    assert "window.__DC_DATA_testpage" in html           # namespaced payload
    # three axis spans per value cell
    assert html.count('class="v v-ros"') >= 2
    assert html.count('class="v v-week"') >= 2
    assert html.count('class="v v-po"') >= 2
    # every CSS rule is .dc-scoped (no bare tag selectors leaking to the host)
    css = html.split("<style>")[1].split("</style>")[0]
    for line in css.splitlines():
        line = line.strip()
        if line.startswith((".", "}", "--")) or not line or ":" in line.split("{")[0] and "{" not in line:
            continue
        if "{" in line:
            sel = line.split("{")[0].strip()
            if sel:
                assert sel.startswith(".dc"), f"unscoped CSS selector: {sel}"
    # cap header shows the live period cap + banked
    assert "SP cap <b>16</b>" in html
    assert "banked <b>15</b>" in html
    # </ escaped inside embedded JSON (script-injection guard)
    payload_part = html.split("window.__DC_DATA_testpage = ")[1].split(";\n(function")[0]
    assert "</" not in payload_part.replace("<\\/", "")


# ── hitter week axis from schedule ───────────────────────────────────────────
def test_hitter_week_games_from_schedule():
    hit = _hit_board([
        dict(owner="MINE", name="Everyday Guy", team="NYY", own="",
             slots=["OF", "UTIL"], per_game=4.0, rank=10, signal="hold",
             etfr=280.0, src="id", vol=None, inj="", ret="",
             xfp_ros=280.0, xfp_po=60.0),
    ])
    sched = {147: [{"date": f"2026-07-{d:02d}"} for d in (11, 12, 14, 15, 17)]}
    ctx = _ctx({}, banked=15, schedules=sched, team_map={"NYY": 147})
    data = _build(hitter_board=hit, week_ctx=ctx)
    row = _player(data, "UTIL", "Everyday Guy")
    assert row["week_detail"]["games"] == 5
    assert row["xfp_week"] == 20.0        # 4.0 × 5 games

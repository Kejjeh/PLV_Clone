"""Tests for the canonical position-grouping seam (plv_clone.positions)."""
from plv_clone.positions import (
    position_group, hitter_groups, primary_hitter_group, detect_closer_status,
    order_groups, GROUP_ORDER,
)


# ── hitter membership + primary group ──────────────────────────────────────────

def test_multi_position_hitter_membership_and_primary():
    # 1B + OF eligible (e.g. a corner/OF flex) -> in 1B/3B, OF, UTIL; primary = 1B/3B
    p = {"eligible_slots": ["1B", "OF", "DH", "UTIL"]}
    g = hitter_groups(p)
    assert {"1B/3B", "OF", "UTIL", "DH"} <= g
    assert "2B/SS" not in g
    assert primary_hitter_group(p) == "1B/3B"   # most specific fielding wins
    assert position_group(p, "H") == "1B/3B"


def test_catcher_outranks_other_eligibility():
    p = {"eligible_slots": ["C", "1B", "UTIL"]}
    assert primary_hitter_group(p) == "C"


def test_middle_infield():
    assert position_group({"eligible_slots": ["SS", "UTIL"]}, "H") == "2B/SS"
    assert position_group({"eligible_slots": ["2B"]}, "H") == "2B/SS"


def test_pure_dh_falls_back_to_dh_not_util():
    # only DH/UTIL eligible (no fielding position) -> DH bucket, not UTIL
    p = {"eligible_slots": ["DH", "UTIL"]}
    assert primary_hitter_group(p) == "DH"
    assert "DH" in hitter_groups(p)


def test_util_only_when_no_other_signal():
    assert primary_hitter_group({"eligible_slots": ["UTIL"]}) == "DH"  # no fielding -> DH fallback
    assert primary_hitter_group({"eligible_slots": []}) == "DH"


def test_position_tag_used_when_slots_missing():
    # a df row with only a position string still groups
    assert position_group({"position": "SS"}, "H") == "2B/SS"
    assert position_group({"position": "RF"}, "H") == "OF"


# ── pitchers: SP comes from caller bucket (dual-eligible authority) ─────────────

def test_detmers_dual_eligible_grouped_sp_when_bucket_sp():
    # ESPN .position='RP' but detect_pitcher_role says SP -> caller passes 'SP'
    detmers = {"position": "RP", "eligible_slots": ["SP", "RP"]}
    assert position_group(detmers, "SP") == "SP"


def test_sp_bucket_always_sp():
    assert position_group({"position": "SP"}, "SP") == "SP"


# ── closer vs setup (current-season saves/holds, display-only) ──────────────────

def test_closer_from_saves():
    assert detect_closer_status({"sv_to": 14, "hld_to": 1}) == "CLOSER"
    assert position_group({"position": "RP"}, "RP", rp_row={"sv_to": 14, "hld_to": 1}) == "CLOSER"


def test_setup_from_holds():
    assert detect_closer_status({"sv_to": 1, "hld_to": 12}) == "SETUP"
    assert position_group({"position": "RP"}, "RP", rp_row={"sv_to": 1, "hld_to": 12}) == "SETUP"


def test_middle_relief_groups_under_setup():
    # few saves, few holds -> MIDDLE classifier, but the display group is SETUP
    assert detect_closer_status({"sv_to": 1, "hld_to": 2}) == "MIDDLE"
    assert position_group({"position": "RP"}, "RP", rp_row={"sv_to": 1, "hld_to": 2}) == "SETUP"


def test_thin_data_falls_back_to_role_label():
    assert detect_closer_status({"sv_to": 0, "hld_to": 0, "role_lag1": "CL"}) == "CLOSER"
    assert detect_closer_status({"sv_to": 0, "hld_to": 0, "role_lag1": "SU"}) == "SETUP"
    assert detect_closer_status({"sv_to": 0, "hld_to": 0, "role_lag1": ""}) == "MIDDLE"


def test_save_share_threshold():
    # save-dominant committee arm (share >= .55) -> CLOSER even below 8 saves
    assert detect_closer_status({"sv_to": 4, "hld_to": 2}) == "CLOSER"   # share .67
    assert detect_closer_status({"sv_to": 3, "hld_to": 6}) == "SETUP"    # holds-heavy


# ── ordering ───────────────────────────────────────────────────────────────────

def test_order_groups_canonical():
    assert order_groups(["SETUP", "C", "OF", "SP", "1B/3B"]) == ["1B/3B", "OF", "SP", "SETUP"] or \
           order_groups(["SETUP", "C", "OF", "SP", "1B/3B"]) == ["C", "1B/3B", "OF", "SP", "SETUP"]
    # exact:
    assert order_groups(["SETUP", "C", "OF", "SP", "1B/3B"]) == ["C", "1B/3B", "OF", "SP", "SETUP"]
    assert GROUP_ORDER.index("CLOSER") < GROUP_ORDER.index("SETUP")

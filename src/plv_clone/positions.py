"""positions — the canonical fantasy position-grouping seam.

ONE place that maps any player to the BrownU fantasy taxonomy, so dashboards and
skills stop re-deriving (and diverging on) position groups. Groups:

    C · 1B/3B · 2B/SS · OF · UTIL · DH · SP · CLOSER · SETUP

Hitters: C / corner-IF / middle-IF / OF as fielding groups; UTIL = every hitter
(the flex membership); DH = the fallback bucket for a player whose ONLY hitting
eligibility is DH/UTIL (no fielding position). Pitchers: SP, and relievers split
into CLOSER (the arm getting SAVES) vs SETUP (the arm getting HOLDS / any other
relief role) — this split is DISPLAY-ONLY grouping (CLAUDE.md #13), never a ranker
input. The SP-vs-RP decision is NOT made here — callers pass ``bucket`` from
scripts.xfp.lib.pitcher_role.detect_pitcher_role (the dual-eligible authority,
e.g. Detmers). This module is pure (no network, no scripts-tree imports) so it is
importable everywhere and unit-testable with literal inputs.
"""
from __future__ import annotations

import ast

# ESPN slot strings -> our buckets
OF_SLOTS = {"OF", "LF", "CF", "RF"}
HITTER_SLOTS = {"C", "1B", "2B", "3B", "SS", "OF", "LF", "CF", "RF", "DH", "UTIL", "IF"}

# Ordered (key, label) group lists for dashboards/tables.
HITTER_POSITION_GROUPS = [
    ("C", "Catcher (C)"),
    ("1B/3B", "Corner Infield (1B / 3B)"),
    ("2B/SS", "Middle Infield (2B / SS)"),
    ("OF", "Outfield (OF)"),
    ("UTIL", "UTIL (all hitters)"),
    ("DH", "DH / non-fielder"),
]
PITCHER_POSITION_GROUPS = [
    ("SP", "Starter (SP)"),
    ("CLOSER", "Closer (saves)"),
    ("SETUP", "Setup / middle relief (holds)"),
]
ALL_POSITION_GROUPS = HITTER_POSITION_GROUPS + PITCHER_POSITION_GROUPS

# Canonical display order across every surface (matches the user's taxonomy).
GROUP_ORDER = ["C", "1B/3B", "2B/SS", "OF", "UTIL", "DH", "SP", "CLOSER", "SETUP"]
GROUP_RANK = {g: i for i, g in enumerate(GROUP_ORDER)}


def order_groups(groups):
    """Sort an iterable of group keys into the canonical display order."""
    return sorted(set(groups), key=lambda g: GROUP_RANK.get(g, len(GROUP_ORDER)))


# ── input extraction (accept ESPN obj / df row / dict) ─────────────────────────

def _slots(player) -> set[str]:
    # Accept a raw iterable of slot strings directly (board passes df['slots'] lists).
    if isinstance(player, (list, tuple, set, frozenset)):
        return {str(x).upper() for x in player}
    elig = getattr(player, "eligibleSlots", None)
    if elig is None and hasattr(player, "get"):
        elig = player.get("eligible_slots", player.get("eligibleSlots", []))
    if isinstance(elig, str):
        try:
            elig = ast.literal_eval(elig)
        except Exception:
            elig = [p.strip() for p in elig.replace("|", ",").split(",") if p.strip()]
    return {str(x).upper() for x in (elig or [])}


def _position_tag(player) -> str:
    pos = getattr(player, "position", None)
    if pos is None and hasattr(player, "get"):
        pos = player.get("position") or player.get("primary_position") or player.get("gpos")
    return (pos or "").upper()


def _int_field(row, *keys) -> int:
    for k in keys:
        v = getattr(row, k, None)
        if v is None and hasattr(row, "get"):
            v = row.get(k)
        try:
            if v is not None:
                return int(float(v))
        except (TypeError, ValueError):
            continue
    return 0


# ── hitters ────────────────────────────────────────────────────────────────────

def hitter_groups(player) -> set[str]:
    """MEMBERSHIP set (multi) for filtering: every hitting group a player qualifies
    for. UTIL is always included (every hitter is flex-eligible). DH is included when
    the player is DH-eligible OR has no fielding position at all (pure DH fallback)."""
    s = _slots(player)
    pos = _position_tag(player)
    if pos:
        s = s | {pos}
    out = {"UTIL"}
    if "C" in s:
        out.add("C")
    if "1B" in s or "3B" in s:
        out.add("1B/3B")
    if "2B" in s or "SS" in s:
        out.add("2B/SS")
    if s & OF_SLOTS:
        out.add("OF")
    fielding = out - {"UTIL"}
    if "DH" in s or not fielding:
        out.add("DH")
    return out


# fielding-specificity order for picking ONE primary group per hitter
_HITTER_PRIMARY_ORDER = ["C", "1B/3B", "2B/SS", "OF", "DH", "UTIL"]


def primary_hitter_group(player) -> str:
    """Single best group for one-row-per-player grouping: most specific fielding
    position first (C > corner > middle > OF), then DH (pure DH), then UTIL."""
    g = hitter_groups(player)
    for grp in _HITTER_PRIMARY_ORDER:
        if grp in g:
            return grp
    return "UTIL"


# ── relievers: closer vs setup (display-only) ──────────────────────────────────

_CLOSER_ROLE_TAGS = {"CL", "CP", "CLOSER", "RPCL"}
_SETUP_ROLE_TAGS = {"SU", "SETUP", "HLD", "8TH", "MR", "MIDDLE", "RP"}


def detect_closer_status(rp_row, *, season_year=None) -> str:
    """Classify a reliever as CLOSER / SETUP / MIDDLE from CURRENT-season saves &
    holds (the user's rule: closer = getting saves, setup = getting holds). Falls
    back to the prior-year role label (role_lag1) when current sv+hld is too thin.
    DISPLAY-ONLY grouping — never a ranker input (CLAUDE.md #13).

    Reads sv/hld from common column names (sv_to/hld_to current-season to-date, or
    saves/holds). `season_year` is accepted for future calibration but unused today.
    """
    sv = _int_field(rp_row, "sv_to", "saves", "sv", "SV")
    hld = _int_field(rp_row, "hld_to", "holds", "hld", "HLD")
    total = sv + hld
    if total >= 3:  # enough current-season relief usage to classify on outcomes
        save_share = sv / total
        if sv >= 8 or save_share >= 0.55:
            return "CLOSER"
        if hld >= 5:
            return "SETUP"
        return "MIDDLE"
    # thin current data -> prior-year role tag fallback
    role = ""
    if hasattr(rp_row, "get"):
        role = str(rp_row.get("role_lag1") or rp_row.get("role") or "").upper()
    else:
        role = str(getattr(rp_row, "role_lag1", "") or "").upper()
    if role in _CLOSER_ROLE_TAGS:
        return "CLOSER"
    if role in _SETUP_ROLE_TAGS:
        return "SETUP"
    return "MIDDLE"


# ── the one public entry point ─────────────────────────────────────────────────

def position_group(player, bucket=None, *, rp_row=None, season_year=None) -> str:
    """Return the single canonical fantasy group for a player.

    Args:
        player: ESPN player object / pandas row / dict (for slots + position).
        bucket: 'H' | 'SP' | 'RP' — the caller's already-resolved bucket. For
                pitchers pass the result of detect_pitcher_role (the dual-eligible
                authority); positions.py does NOT re-derive SP vs RP. If None, a
                coarse guess is made from the position tag (SP/RP/hitter).
        rp_row: optional row carrying current-season sv/hld (+ role_lag1) for the
                CLOSER/SETUP split when bucket == 'RP'. Defaults to `player`.

    Returns one of: C, 1B/3B, 2B/SS, OF, UTIL, DH, SP, CLOSER, SETUP.
    (A MIDDLE reliever is grouped under SETUP — the two reliever display groups the
    league uses are CLOSER and SETUP.)
    """
    b = (bucket or "").upper()
    if not b:
        tag = _position_tag(player)
        if tag == "SP":
            b = "SP"
        elif tag in ("RP", "CL", "CP"):
            b = "RP"
        else:
            b = "H"
    if b == "SP":
        return "SP"
    if b == "RP":
        status = detect_closer_status(rp_row if rp_row is not None else player,
                                      season_year=season_year)
        return "CLOSER" if status == "CLOSER" else "SETUP"
    return primary_hitter_group(player)

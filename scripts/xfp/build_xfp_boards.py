"""build_xfp_boards.py — production merged xFP boards (SP + hitter).

Consolidates the two `scripts/_oneoff/` board builders (sp_merged_xfp_rank.py +
hitter_merged_xfp_rank.py) into one importable engine exposing:

    build_sp_board()     -> pd.DataFrame   (MINE + every FA SP, dual-ranked)
    build_hitter_board() -> pd.DataFrame   (MINE + every FA hitter, bucketed)

plus a `main()` CLI that writes the two dated CSVs and prints a summary.

WINDOW MATH (date-parameterized — see TODAY / SEASON_END / PLAYOFF_START below;
works any day, not hardcoded to 2026-06-11). FLAT path (no volume row):
  SP RoS      = per_start * (avail->SEASON_END days * RATE)          RATE=1.19/7/day
  SP Playoffs = per_start * PLAYOFF_FULL * po_days/PLAYOFF_DAYS      PLAYOFF_FULL=3.6
  Hitter RoS  = per_game  * (avail->SEASON_END days /7 * GPW)        GPW=6.3 g/wk
  Hitter Po   = per_game  * PLAYOFF_GAMES_FULL * po_days/PLAYOFF_DAYS  =18 g
VOLUME path (2026-07-09): where the validated forward-volume models
(xfp_volume_projections.csv / xfp_sp_volume_projections.csv) carry the player,
the flat league volume is replaced by the player's projected per-teamgame
volume — see the FORWARD-VOLUME MODELS constants block. src gets "·vol".

PER_START / PER_GAME SOURCE TIERS (honest source label carried in `src`):
  SP:      Stuff+ proj_ros_fp  > rp3 data_driven  > rp3 marcel (talent_prior, LOW-CONF)
  HITTER:  rh3 (id-keyed, collision-safe) > rh3 (exact-norm name) > talent_prior LOW-CONF

The `talent_prior` tier is flagged LOW-CONF in `src`. For SPs the rp3 marcel
value is a SUPPRESSED Marcel prior (the `marcel_il` gotcha) — NOT a real read.
For hitters it is the calibrated Marcel fallback for rh3-absent elites
(Judge/Greene/Snell class).

IL-RETURN CAVEAT (Corbin-Burnes-style): return dates come from
LeagueState.injury_details() where available; otherwise a COARSE status
heuristic (HEUR below). Season-ending surgery cases (TJ etc.) are over-estimated
by the heuristic — a player tagged FIFTEEN_DAY_DL who is actually done for the
year will still get a 21-day return guess and an inflated xFP. Trust the
explicit injury_details return date over the heuristic, and treat any
talent_prior + long-IL row as a ranking aid, not a guarantee.

NAME / COLLISION SAFETY: hitters join rh3 by MLBAM batter id via
resolve_batter_id(name, team=, position=) (CLAUDE.md rule #10; Max Muncy
LAD/ATH smoke test in main()), falling back to exact-norm name only when id
resolution fails and the name is unambiguous in rh3. SPs flip rp3's
"Last, First" names to "First Last" before matching the FA pool / roster.
"""
from __future__ import annotations
import sys
import re
import unicodedata
from pathlib import Path
from datetime import date

import pandas as pd

# scripts/xfp/build_xfp_boards.py -> parents[2] == repo root
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp" / "lib"))

from plv_clone.league_state import LeagueState
from plv_clone.projections import PROJECTIONS
from plv_clone.utils.name_match import resolve_batter_id
import sp_stuff_model as ss
import talent_prior as TP   # production lib (scripts/xfp/lib/talent_prior.py)

# ── DATE-PARAMETERIZED CONSTANTS ─────────────────────────────────────────────
# Defaults work any day. The 2026 season window: regular season ends ~Sep 20,
# the BrownU fantasy playoff window opens ~Aug 17 (3 playoff weeks).
TODAY = date.today()
SEASON_END = date(2026, 9, 20)
PLAYOFF_START = date(2026, 8, 17)
PLAYOFF_DAYS = max(1, (SEASON_END - PLAYOFF_START).days)

# SP window math
from plv_clone.cap_math import STARTS_PER_SP_PER_WEEK as _SPW  # owner (audit 2026-07-04)
RATE = _SPW / 7.0          # empirical SP starts per active SP per day
PLAYOFF_FULL = 3.6         # full-availability playoff starts

# Hitter window math
GPW = 6.3                  # hitter games/week (MLB everyday cadence)
PLAYOFF_GAMES_FULL = 18    # ~6 g/wk x 3 playoff wk

# ── FORWARD-VOLUME MODELS (validated 2026-07-09, PASS) ──────────────────────
# data/research/validation_runs/{hitter,sp}_volume_model_2026-07-09.md.
# Where a per-player volume row exists, the RoS/PO totals swap the FLAT league
# volume constants for the player's projected per-teamgame volume:
#   hitter: RoS FP = per_pa   × proj_ros_pa_per_teamgame × team_games_in_window
#   SP:     RoS FP = per_start × proj_ros_gs_per_teamgame × team_games_in_window
# with team_games_in_window = the EXISTING window numbers (days/7 × GPW for
# hitters; for SPs, days × RATE ÷ FLAT_GS_PER_TEAMGAME) — i.e. both reduce to
#   xfp = flat_xfp × (vol / FLAT_*_PER_TEAMGAME)
# so the availability-date (IL) window scaling is preserved EXACTLY as before;
# the volume model is conditional-on-active and the window handles IL timing.
# The SAME multiplier is applied to the playoff window (defensible + consistent:
# playoff games count × player-vol / league-flat-vol). Rows using a volume row
# get src suffix "·vol" + a `vol` column; rows absent from the volume CSVs
# (e.g. marcel_il IL-stash arms) keep the flat path + existing LOW-CONF flags.
VOL_HIT_CSV = ROOT / "data/outputs/xfp_volume_projections.csv"
VOL_SP_CSV = ROOT / "data/outputs/xfp_sp_volume_projections.csv"
FLAT_PA_PER_TEAMGAME = 3.5           # rh3 convention: per_game = per_pa × 3.5
FLAT_GS_PER_TEAMGAME = _SPW / GPW    # 1.19 starts/wk ÷ 6.3 team-g/wk ≈ 0.189

# ── FLAT-PATH COMPARABILITY DOCK (2026-07-09 follow-up) ─────────────────────
# Flat-path rows (no volume row) that are IL'd or prior-only (talent_prior /
# marcel_il class) are docked by the 75th-PERCENTILE vol ratio
# (vol / flat_const) of the volume-modeled rows in the SAME universe — i.e. an
# unmodeled player is credited the volume of a TOP-QUARTILE modeled player,
# NOT the flat league constant. Rationale: flat-path rows are mostly IL
# stashes and priors-only arms whose healthy-workload ceiling is
# top-quartile-like, but crediting them the full flat constant (which exceeds
# even the MAX modeled volume — ratio 1.0 vs max ~0.93 for SPs) systematically
# over-ranks them vs volume-modeled rows that embed forward injury/rest risk.
# Docked rows get src suffix "·flat↓" and keep their existing LOW-CONF flags.
# Rows that are flat merely because they fall below the volume model's
# coverage floor but are otherwise ACTIVE/healthy (not prior-only, no ESPN
# injury status) are NOT docked — they keep the plain flat path.
FLAT_DOCK_Q = 0.75


def _dock_flat_rows(df: pd.DataFrame, flat_const: float):
    """Apply the flat-path comparability dock in place; returns (df, p75 or
    None). Dock class = no volume row AND (prior-only src OR IL'd). The p75
    ratio is computed from this board's own vol-row distribution."""
    if "vol" not in df.columns:
        return df, None
    ratios = (pd.to_numeric(df["vol"], errors="coerce") / flat_const).dropna()
    if len(ratios) < 10:      # no usable distribution — leave the flat path alone
        return df, None
    p75 = float(ratios.quantile(FLAT_DOCK_Q))
    src_s = df["src"].astype(str)
    vol_missing = pd.to_numeric(df["vol"], errors="coerce").isna()
    has_ros = pd.to_numeric(df["xfp_ros"], errors="coerce").notna()
    prior_only = src_s.str.startswith("talent_prior")
    il = df["inj"].astype(str).str.strip().replace("nan", "").ne("")
    dock = vol_missing & has_ros & (prior_only | il)
    if dock.any():
        df.loc[dock, "xfp_ros"] = (pd.to_numeric(df.loc[dock, "xfp_ros"]) * p75).round(0)
        df.loc[dock, "xfp_po"] = (pd.to_numeric(df.loc[dock, "xfp_po"]) * p75).round(0)
        df.loc[dock, "src"] = src_s[dock] + "·flat↓"
    df.attrs["flat_dock_p75"] = p75
    df.attrs["n_flat_dock"] = int(dock.sum())
    return df, p75

# Coarse IL-return heuristic (days from TODAY) when injury_details has no date.
# Surgery / season-ending cases are OVER-estimated here (see module docstring).
HEUR = {"SIXTY_DAY_DL": 56, "FIFTEEN_DAY_DL": 21, "TEN_DAY_DL": 15,
        "OUT": 14, "DAY_TO_DAY": 0, "DOUBTFUL": 5, "QUESTIONABLE": 0}

# ESPN slot -> our hitter bucket membership
OF_SLOTS = {"OF", "LF", "CF", "RF"}
HITTER_POSITIONS = {"C", "1B", "2B", "3B", "SS", "OF", "LF", "CF", "RF",
                    "DH", "UTIL", "IF"}

# ESPN proTeam abbreviations differ from KNOWN_COLLISIONS / multiyr cache; alias
# BEFORE resolve_batter_id so the team hint matches (canonical: ESPN "OAK" vs
# collision-list "ATH" for the second Max Muncy).
ESPN_TEAM_ALIAS = {"OAK": "ATH", "WSH": "WSH", "CHW": "CWS", "AZ": "ARI"}


# ── shared helpers ───────────────────────────────────────────────────────────
# NOT routed to name_match.join_key (item 10, 2026-07-04): this `norm` feeds
# `_li_key` below, a (last, first-initial) fallback that needs SPACE-separated,
# order-preserving tokens. join_key sorts alphabetic tokens and drops separators
# ("kyle schwarber" -> "kyleschwarber"), which collapses _li_key's split to a
# single token and breaks the Cam/Cameron-style fallback join. Kept local; the
# owner has no (last, first-initial) key scheme.
def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", s.lower())).strip()


def alias_team(t):
    if not t:
        return t
    return ESPN_TEAM_ALIAS.get(str(t).upper(), str(t).upper())


def _ret_map(ls, players) -> dict:
    """ESPN playerId -> return date, for the injured subset of `players`.

    Lifted from the previously duplicated per-board blocks; the map is a
    superset of what each board reads (it covers the whole pool, not just the
    board's position slice), which is behavior-identical per row."""
    inj_ids = [int(p.playerId) for p in players if getattr(p, "injured", False)]
    out = {}
    if not inj_ids:
        return out
    try:
        idf = ls.injury_details(inj_ids)
        rc = next((c for c in idf.columns if "return" in c.lower()), None)
        ic = next((c for c in idf.columns if c.lower() in ("player_id", "playerid", "id")), None)
        if rc and ic:
            for _, r in idf.iterrows():
                rv = pd.to_datetime(r[rc], errors="coerce")
                if pd.notna(rv):
                    out[int(r[ic])] = rv.date()
    except Exception as e:
        print(f"[injury_details] {type(e).__name__}: {e}")
    return out


def fetch_board_inputs() -> dict:
    """ONE network pass feeding both boards (and the decision console).

    Returns {ls, league, my_team_id, roster, fas, injury_details,
    rostered_names}. `fas` is the raw unfiltered size=2000 pool (never <2000 —
    feedback_fa_pool_size_cap.md); each board applies its own position filter.
    `injury_details` is the espn-playerId->return-date map for every injured
    FA in the pool."""
    ls = LeagueState()
    lg = ls._get_league()
    try:
        my_team_id = getattr(ls._find_my_team(), "team_id", None)
    except Exception:
        my_team_id = None
    roster = ls.my_roster_with_injuries()
    fas = list(lg.free_agents(size=2000))
    rostered_names = {norm(p.name) for t in lg.teams for p in t.roster}
    return {
        "ls": ls,
        "league": lg,
        "my_team_id": my_team_id,
        "roster": roster,
        "fas": fas,
        "injury_details": _ret_map(ls, fas),
        "rostered_names": rostered_names,
    }


# =============================================================================
# SP BOARD
# =============================================================================
def _li_key(nn):
    p = nn.split()
    return (p[-1], p[0][0]) if len(p) >= 2 and p[0] else None


def _build_map(names, vals):
    full, li = {}, {}
    for nm, v in zip(names, vals):
        if pd.isna(v):
            continue
        nn = norm(nm); full[nn] = v
        k = _li_key(nn)
        if k:
            li.setdefault(k, []).append(v)
    return full, li


def _lookup(maps, nm):
    nn = norm(nm); k = _li_key(nn)
    for full, li, src in maps:
        if nn in full:
            return full[nn], src
        b = li.get(k) if k else None
        if b and len(b) == 1:
            return b[0], src
    return None, "NO_DATA"


def _sp_starts(avail):
    ros = max(0.0, (SEASON_END - avail).days) * RATE
    po_days = max(0, (SEASON_END - max(avail, PLAYOFF_START)).days)
    return ros, PLAYOFF_FULL * po_days / PLAYOFF_DAYS


# SP volume map: norm("First Last") -> proj_ros_gs_per_teamgame. Name-keyed
# because the SP board rows are ESPN-name-keyed; names come from the volume
# CSV itself ("Last, First", flipped) with NaN names recovered via rp3's
# mlbam `pitcher` -> player_name. Skip-on-ambiguous: any two distinct SPs
# normalizing to the same full name are dropped from the map entirely
# (collision safety, CLAUDE.md rule #10 — never guess between same-name arms).
_SP_VOL_MAPS = None


def _sp_vol_maps():
    global _SP_VOL_MAPS
    if _SP_VOL_MAPS is not None:
        return _SP_VOL_MAPS
    try:
        v = pd.read_csv(VOL_SP_CSV)
        rp3 = PROJECTIONS.rp3().dropna(subset=["pitcher", "player_name"])
        id2nm = dict(zip(rp3["pitcher"].astype(int), rp3["player_name"]))
        names = []
        for _, r in v.iterrows():
            nm = r.get("player_name")
            if pd.isna(nm) or not str(nm).strip():
                nm = id2nm.get(int(r["mlbam_id"]))
            names.append(TP.flip_name(nm) if (nm is not None and pd.notna(nm)) else None)
        v = v.assign(_nm=names)
        v = v[v["_nm"].notna() & v["proj_ros_gs_per_teamgame"].notna()]
        nn = v["_nm"].map(norm)
        v = v[~nn.duplicated(keep=False)]
        _SP_VOL_MAPS = [(*_build_map(v["_nm"], v["proj_ros_gs_per_teamgame"]), "vol")]
    except Exception as e:
        print(f"[sp_volume] unavailable ({type(e).__name__}: {e}) — flat volume everywhere")
        _SP_VOL_MAPS = []
    return _SP_VOL_MAPS


def _apply_sp_vol(ps, ros, po, nm):
    """(xfp_ros, xfp_po, vol, src_suffix) — volume-model totals when the SP has
    a volume row, flat totals otherwise. See FORWARD-VOLUME MODELS block."""
    if ps is None:
        return None, None, None, ""
    maps = _sp_vol_maps()
    gv = None
    if maps:
        gv, _ = _lookup(maps, nm)
    if gv is None:
        return round(float(ps) * ros, 0), round(float(ps) * po, 0), None, ""
    mult = float(gv) / FLAT_GS_PER_TEAMGAME
    return (round(float(ps) * ros * mult, 0), round(float(ps) * po * mult, 0),
            round(float(gv), 3), "·vol")


def build_sp_board(*, roster=None, fas=None, injury_details=None) -> pd.DataFrame:
    """Merged SP board: MINE staff + every FA SP, dual-ranked by xFP-RoS and
    xFP-playoffs. Returns a DataFrame of the RANKED universe (rows with a
    per_start). Columns: owner, name, team, own, per_start, stuff, src, vol,
    inj, ret, xfp_ros, xfp_po. src carries a "·vol" suffix (and vol the
    starts-per-teamgame number) where the forward-volume model replaced the
    flat 1.19/wk rate.

    Injection seam (fetch_board_inputs): pass `roster`
    (my_roster_with_injuries frame), `fas` (raw free_agents(size=2000) list)
    and `injury_details` (espn playerId -> return date) to skip ALL network
    fetches. No-arg call is behavior-identical to before."""
    # ---- per_start source tiers ----
    mdl, sc, _ = ss.fit_model()
    d = ss.load_2026().dropna(subset=ss.FEATS).copy()
    d["proj_ros_fp"] = mdl.predict(sc.transform(d[ss.FEATS]))
    sf = _build_map(d["player_name_fg"], d["proj_ros_fp"])
    st = _build_map(d["player_name_fg"], d["stuff_plus"])
    rp3 = PROJECTIONS.rp3().dropna(subset=["player_name"])
    tag = rp3["data_quality_tag"].astype(str)
    dd = rp3[tag.str.startswith("data_driven")]
    mar = rp3[tag.str.contains("marcel")]
    # rp3 stores names "Last, First" — flip so they match the FA pool / roster.
    rp_dd = _build_map(dd["player_name"].map(TP.flip_name), dd["xfp_rp3_per_start"])
    rp_mar = _build_map(mar["player_name"].map(TP.flip_name), mar["xfp_rp3_per_start"])
    PS = [(*sf, "Stuff+"), (*rp_dd, "rp3_dd"), (*rp_mar, "talent_prior")]
    STF = [(*st, "")]

    rows = []

    # ---- MY staff ----
    ros_my = roster if roster is not None else LeagueState().my_roster_with_injuries()
    mine = ros_my[ros_my["position"] == "SP"]
    for _, p in mine.iterrows():
        nm = p["player_name"]
        ps, src = _lookup(PS, nm); stf, _ = _lookup(STF, nm)
        injured = bool(p.get("injured"))
        rd = pd.to_datetime(p.get("return_date"), errors="coerce")
        ret = rd.date() if (injured and pd.notna(rd)) else TODAY
        avail = max(TODAY, ret)
        ros, po = _sp_starts(avail)
        xros, xpo, vol, sfx = _apply_sp_vol(ps, ros, po, nm)
        rows.append(dict(owner="MINE", name=nm, team=p.get("pro_team", ""), own="",
                         per_start=None if ps is None else round(float(ps), 2),
                         stuff=None if stf is None else round(float(stf), 0),
                         src=src + sfx, vol=vol,
                         inj=p.get("injury_status", "") if injured else "",
                         ret=ret if injured else "",
                         xfp_ros=xros, xfp_po=xpo))

    # ---- FA pool ----
    # size=2000 UNFILTERED, position post-filtered — per-position size<2000 silently
    # drops low-owned high-FP FAs (feedback_fa_pool_size_cap.md; audit 2026-07-04).
    ls = None
    if fas is None or injury_details is None:
        ls = LeagueState()
    pool = fas if fas is not None else ls._get_league().free_agents(size=2000)
    fa_sps = [p for p in pool if getattr(p, "position", None) == "SP"]
    ret_map = injury_details if injury_details is not None else _ret_map(ls, fa_sps)

    for p in fa_sps:
        nm = p.name; pid = int(p.playerId)
        ps, src = _lookup(PS, nm); stf, _ = _lookup(STF, nm)
        injured = bool(getattr(p, "injured", False))
        status = getattr(p, "injuryStatus", "ACTIVE")
        if injured:
            ret = ret_map.get(pid) or (pd.Timestamp(TODAY) + pd.Timedelta(days=HEUR.get(status, 21))).date()
        else:
            ret = TODAY
        avail = max(TODAY, ret)
        ros, po = _sp_starts(avail)
        xros, xpo, vol, sfx = _apply_sp_vol(ps, ros, po, nm)
        rows.append(dict(owner="FA", name=nm, team=getattr(p, "proTeam", ""),
                         own=round(getattr(p, "percent_owned", 0) or 0, 1),
                         per_start=None if ps is None else round(float(ps), 2),
                         stuff=None if stf is None else round(float(stf), 0),
                         src=src + sfx, vol=vol,
                         inj=status if injured else "", ret=ret if injured else "",
                         xfp_ros=xros, xfp_po=xpo))

    df = pd.DataFrame(rows)
    have = df[df["per_start"].notna()].copy()
    have, p75 = _dock_flat_rows(have, FLAT_GS_PER_TEAMGAME)  # before sort — dock moves ranks
    n_dock = have.attrs.get("n_flat_dock", 0)
    have = have.sort_values("xfp_ros", ascending=False).reset_index(drop=True)
    # re-set attrs — sort_values/reset_index don't reliably propagate .attrs
    have.attrs["n_nodata"] = int(len(df) - len(have))
    have.attrs["flat_dock_p75"] = p75
    have.attrs["n_flat_dock"] = n_dock
    return have


# =============================================================================
# HITTER BOARD
# =============================================================================
# rh3 lookup tables built lazily (id-keyed primary + name-keyed fallback).
_RH3 = None
_RH3_BY_ID = None
_FULL = None
_AMBIG_NAMES = None
_MULTIYR = None
_HIT_VOL = None   # mlbam batter id -> proj_ros_pa_per_teamgame (volume model)


def _load_rh3():
    global _RH3, _RH3_BY_ID, _FULL, _AMBIG_NAMES, _MULTIYR, _HIT_VOL
    if _RH3 is not None:
        return
    rh3 = PROJECTIONS.rh3().dropna(subset=["player_name"])
    rh3 = rh3[rh3["batter"].notna()].copy()
    rh3["batter"] = rh3["batter"].astype(int)
    _RH3 = rh3
    _RH3_BY_ID = rh3.set_index("batter")
    full, full_ids = {}, {}
    for _, r in rh3.iterrows():
        nn = norm(r["player_name"])
        full[nn] = r
        full_ids.setdefault(nn, set()).add(int(r["batter"]))
    _FULL = full
    _AMBIG_NAMES = {k for k, v in full_ids.items() if len(v) > 1}
    _MULTIYR = pd.read_csv(ROOT / "data/research/xfp_cache/hitters_multiyr_2015_2026.csv")
    # Hitter forward-volume model (mlbam-id-keyed — collision-free by design).
    try:
        hv = pd.read_csv(VOL_HIT_CSV).dropna(subset=["mlbam_id", "proj_ros_pa_per_teamgame"])
        _HIT_VOL = dict(zip(hv["mlbam_id"].astype(int),
                            hv["proj_ros_pa_per_teamgame"].astype(float)))
    except Exception as e:
        print(f"[hit_volume] unavailable ({type(e).__name__}: {e}) — flat volume everywhere")
        _HIT_VOL = {}


def _rh3_row(name, team=None, position=None):
    """Return (rh3_row_series, source_str, mlbam_id) or (None, 'NO_DATA', None).
    Primary: resolve_batter_id -> RH3_BY_ID. Fallback: collision-safe exact name."""
    _load_rh3()
    try:
        bid = resolve_batter_id(name, team=alias_team(team), position=position, multiyr=_MULTIYR)
    except Exception:
        bid = None
    if bid is not None and bid in _RH3_BY_ID.index:
        row = _RH3_BY_ID.loc[bid]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        return row, "id", int(bid)
    nn = norm(name)
    if nn in _AMBIG_NAMES:
        return None, "NO_DATA", None   # collision-safe: don't silently grab a row
    if nn in _FULL:
        row = _FULL[nn]
        return row, "name", int(row["batter"])
    return None, "NO_DATA", None


def _project_hitter(name, team=None, position=None):
    """(per_game, rank, signal, etfr, src, per_pa, mlbam_id). Falls back to the
    calibrated talent prior (LOW-CONF, src='talent_prior') for rh3-absent elites
    (per_pa is None on that path)."""
    row, src, bid = _rh3_row(name, team=team, position=position)
    if row is not None:
        return (float(row["xfp_rh3_per_game"]), int(row["rank"]), str(row["signal"]),
                round(float(row["expected_total_fp_remaining"]), 0), src,
                float(row["xfp_rh3_per_pa"]), bid)
    try:
        bid = resolve_batter_id(name, team=alias_team(team), position=position, multiyr=_MULTIYR)
    except Exception:
        bid = None
    tp = TP.hitter_prior_pg(bid) if bid is not None else None
    if tp is not None:
        return (tp, None, "stash", None, "talent_prior", None,
                None if bid is None else int(bid))
    return (None, None, "", None, "NO_DATA", None, None)


def _apply_hit_vol(per_game, per_pa, bid, rg, pg):
    """(xfp_ros, xfp_po, vol, src_suffix) — volume-model totals when the hitter
    has a volume row (mlbam-id join), flat totals otherwise. rg/pg are the
    existing availability-scaled window game counts, read as TEAM games under
    the volume path (GPW 6.3/wk ≈ team cadence). per_pa path is exact; the
    talent_prior path (per_pa=None) uses the equivalent ratio form
    per_game × vol / FLAT_PA_PER_TEAMGAME (per_game = per_pa × 3.5 by rh3
    convention, so the two forms are algebraically identical)."""
    if per_game is None:
        return None, None, None, ""
    vol = _HIT_VOL.get(int(bid)) if bid is not None else None
    if vol is None:
        return round(per_game * rg, 0), round(per_game * pg, 0), None, ""
    eff_pg = per_pa * vol if per_pa is not None else per_game * (vol / FLAT_PA_PER_TEAMGAME)
    return round(eff_pg * rg, 0), round(eff_pg * pg, 0), round(float(vol), 2), "·vol"


def _hitter_windows(avail):
    ros_games = max(0.0, (SEASON_END - avail).days) / 7.0 * GPW
    po_days = max(0, (SEASON_END - max(avail, PLAYOFF_START)).days)
    po_games = PLAYOFF_GAMES_FULL * po_days / PLAYOFF_DAYS
    return ros_games, po_games


def buckets_for(slots):
    """ESPN eligible-slot strings -> set of board buckets. UTIL = every hitter."""
    s = {str(x).upper() for x in (slots or [])}
    out = {"UTIL"}
    if "C" in s:
        out.add("C")
    if "1B" in s or "3B" in s:
        out.add("1B/3B")
    if "2B" in s or "SS" in s:
        out.add("2B/SS")
    if s & OF_SLOTS:
        out.add("OF")
    return out


def _is_hitter_slots(slots):
    s = {str(x).upper() for x in (slots or [])}
    return bool(s & HITTER_POSITIONS)


# Bucket display config (key, label). Used by the engine + dashboard.
HITTER_BUCKETS = [
    ("C", "Catcher (C)"),
    ("1B/3B", "Corner Infield (1B / 3B)"),
    ("2B/SS", "Middle Infield (2B / SS)"),
    ("OF", "Outfield (OF)"),
    ("UTIL", "UTIL (all hitters)"),
]


def build_hitter_board(*, roster=None, fas=None, injury_details=None) -> pd.DataFrame:
    """Merged hitter board: MINE hitters + every FA hitter, dual-ranked by
    xFP-RoS and xFP-playoffs, with bucket membership. Returns the FULL frame
    (ranked + no-data rows). `buckets` is a set per row; `per_game` is None for
    rh3-absent rows. Columns: owner, name, team, own, slots, buckets, per_game,
    rank, signal, etfr, src, vol, inj, ret, xfp_ros, xfp_po. src carries a
    "·vol" suffix (and vol the PA-per-teamgame number) where the forward-volume
    model replaced the flat 3.5 PA/g × 6.3 g/wk rate.

    Injection seam (fetch_board_inputs): pass `roster`, `fas` (raw unfiltered
    size=2000 pool) and `injury_details` (espn playerId -> return date) to
    skip ALL network fetches. No-arg call is behavior-identical to before."""
    _load_rh3()
    rows = []

    # ── MY hitters ──
    ros_my = roster if roster is not None else LeagueState().my_roster_with_injuries()
    mine = ros_my[~ros_my["position"].isin(["SP", "RP", "P"])].copy()
    for _, p in mine.iterrows():
        nm = p["player_name"]
        team = p.get("pro_team", "") or None
        pos = p.get("position", "") or None
        per_game, rk, sig, etfr, src, per_pa, bid = _project_hitter(nm, team=team, position=pos)
        injured = bool(p.get("injured"))
        rd = pd.to_datetime(p.get("return_date"), errors="coerce")
        ret = rd.date() if (injured and pd.notna(rd)) else TODAY
        avail = max(TODAY, ret)
        rg, pg = _hitter_windows(avail)
        xros, xpo, vol, sfx = _apply_hit_vol(per_game, per_pa, bid, rg, pg)
        slots = p.get("eligible_slots", [])
        rows.append(dict(
            owner="MINE", name=nm, team=team or "", own="", slots=list(slots),
            per_game=None if per_game is None else round(per_game, 2),
            rank=rk, signal=sig, etfr=etfr, src=src + sfx, vol=vol,
            inj=p.get("injury_status", "") if injured else "",
            ret=ret if injured else "",
            xfp_ros=xros, xfp_po=xpo,
        ))

    # ── FA pool: ONE unfiltered size=2000 pull, hitter-eligibility post-filter ──
    # (was 7 per-position size=1500 pulls — per-position fetches silently drop
    # low-owned high-FP FAs AND cost 7x the API calls. feedback_fa_pool_size_cap.md;
    # audit 2026-07-04.)
    ls = None
    if fas is None or injury_details is None:
        ls = LeagueState()
    seen, fa_players = set(), []
    try:
        pool = fas if fas is not None else ls._get_league().free_agents(size=2000)
        for pl in pool:
            pid = int(pl.playerId)
            if pid in seen:
                continue
            if not _is_hitter_slots(getattr(pl, "eligibleSlots", [])):
                continue
            seen.add(pid)
            fa_players.append(pl)
    except Exception as e:
        print(f"[free_agents unfiltered] {type(e).__name__}: {e}")

    ret_map = injury_details if injury_details is not None else _ret_map(ls, fa_players)

    for p in fa_players:
        nm = p.name; pid = int(p.playerId)
        team = getattr(p, "proTeam", "") or None
        pos = getattr(p, "position", "") or None
        per_game, rk, sig, etfr, src, per_pa, bid = _project_hitter(nm, team=team, position=pos)
        injured = bool(getattr(p, "injured", False))
        status = getattr(p, "injuryStatus", "ACTIVE")
        if injured:
            ret = ret_map.get(pid) or (pd.Timestamp(TODAY) + pd.Timedelta(days=HEUR.get(status, 21))).date()
        else:
            ret = TODAY
        avail = max(TODAY, ret)
        rg, pg = _hitter_windows(avail)
        xros, xpo, vol, sfx = _apply_hit_vol(per_game, per_pa, bid, rg, pg)
        rows.append(dict(
            owner="FA", name=nm, team=team or "",
            own=round(getattr(p, "percent_owned", 0) or 0, 1),
            slots=list(getattr(p, "eligibleSlots", [])),
            per_game=None if per_game is None else round(per_game, 2),
            rank=rk, signal=sig, etfr=etfr, src=src + sfx, vol=vol,
            inj=status if injured else "", ret=ret if injured else "",
            xfp_ros=xros, xfp_po=xpo,
        ))

    df = pd.DataFrame(rows)
    df["buckets"] = df["slots"].apply(buckets_for)
    df, _ = _dock_flat_rows(df, FLAT_PA_PER_TEAMGAME)
    return df


# =============================================================================
# CLI
# =============================================================================
def _sp_out_path():
    return ROOT / f"data/research/sp_merged_xfp_rank_{TODAY.isoformat()}.csv"


def _hitter_out_path():
    return ROOT / f"data/research/hitter_merged_xfp_rank_{TODAY.isoformat()}.csv"


def main():
    print(f"build_xfp_boards — TODAY={TODAY} SEASON_END={SEASON_END} "
          f"PLAYOFF_START={PLAYOFF_START}")
    inputs = fetch_board_inputs()   # ONE roster + FA pull for both boards
    _inj = dict(roster=inputs["roster"], fas=inputs["fas"],
                injury_details=inputs["injury_details"])

    # ── SP board ──
    sp = build_sp_board(**_inj)
    sp_out = _sp_out_path()
    sp.to_csv(sp_out, index=False)
    n_mine = int((sp["owner"] == "MINE").sum())
    print(f"\nSP universe: {len(sp)} ranked ({n_mine} MINE + {len(sp)-n_mine} FA)"
          f" | no-data dropped: {sp.attrs.get('n_nodata', '?')}")
    print(f"  -> {sp_out}")

    # ── Hitter board ──
    hit = build_hitter_board(**_inj)
    have = hit[hit["per_game"].notna()].copy()
    nodata = hit[hit["per_game"].isna()].copy()
    out_df = hit.copy()
    out_df["buckets"] = out_df["buckets"].apply(lambda s: "|".join(sorted(s)))
    out_df["slots"] = out_df["slots"].apply(lambda s: "|".join(map(str, s)))
    hit_out = _hitter_out_path()
    out_df.sort_values("xfp_ros", ascending=False, na_position="last").to_csv(hit_out, index=False)
    print(f"\nHITTER universe: {len(have)} ranked "
          f"({(have['owner']=='MINE').sum()} MINE + {(have['owner']=='FA').sum()} FA) | "
          f"no rh3 data: {len(nodata)}")
    a, b = TP.calib()
    src_s = have["src"].astype(str)
    print(f"  id-joins: {src_s.str.startswith('id').sum()} | name-fallback: "
          f"{src_s.str.startswith('name').sum()} | talent-prior LOW-CONF: "
          f"{src_s.str.startswith('talent_prior').sum()} [calib rh3_pg={a:.2f}+{b:.2f}*raw]")
    print(f"  volume-model rows (·vol): hitters {src_s.str.endswith('·vol').sum()}/{len(have)}"
          f" | SPs {sp['src'].astype(str).str.endswith('·vol').sum()}/{len(sp)}")
    hp75 = hit.attrs.get("flat_dock_p75"); sp75 = sp.attrs.get("flat_dock_p75")
    print(f"  flat-path dock (·flat↓, p75 vol ratio): hitters "
          f"{hit.attrs.get('n_flat_dock', 0)} rows @ x{hp75 if hp75 is None else round(hp75, 3)}"
          f" | SPs {sp.attrs.get('n_flat_dock', 0)} rows @ x{sp75 if sp75 is None else round(sp75, 3)}")
    print(f"  -> {hit_out}")

    # smoke test: Max Muncy collision resolves to distinct ids
    mm_lad = resolve_batter_id("Max Muncy", team="LAD", position="3B", multiyr=_MULTIYR)
    mm_ath = resolve_batter_id("Max Muncy", team="ATH", position="C", multiyr=_MULTIYR)
    print(f"[smoke] Max Muncy LAD/3B -> {mm_lad} | ATH/C -> {mm_ath} "
          f"(distinct={mm_lad != mm_ath})")


if __name__ == "__main__":
    main()

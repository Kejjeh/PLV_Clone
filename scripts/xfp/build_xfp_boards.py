"""build_xfp_boards.py — production merged xFP boards (SP + hitter).

Consolidates the two `scripts/_oneoff/` board builders (sp_merged_xfp_rank.py +
hitter_merged_xfp_rank.py) into one importable engine exposing:

    build_sp_board()     -> pd.DataFrame   (MINE + every FA SP, dual-ranked)
    build_hitter_board() -> pd.DataFrame   (MINE + every FA hitter, bucketed)

plus a `main()` CLI that writes the two dated CSVs and prints a summary.

WINDOW MATH (date-parameterized — see TODAY / SEASON_END / PLAYOFF_START below;
works any day, not hardcoded to 2026-06-11):
  SP RoS      = per_start * (avail->SEASON_END days * RATE)          RATE=1.19/7/day
  SP Playoffs = per_start * PLAYOFF_FULL * po_days/PLAYOFF_DAYS      PLAYOFF_FULL=3.6
  Hitter RoS  = per_game  * (avail->SEASON_END days /7 * GPW)        GPW=6.3 g/wk
  Hitter Po   = per_game  * PLAYOFF_GAMES_FULL * po_days/PLAYOFF_DAYS  =18 g

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
sys.path.insert(0, str(ROOT / "src"))
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


def build_sp_board() -> pd.DataFrame:
    """Merged SP board: MINE staff + every FA SP, dual-ranked by xFP-RoS and
    xFP-playoffs. Returns a DataFrame of the RANKED universe (rows with a
    per_start). Columns: owner, name, team, own, per_start, stuff, src, inj,
    ret, xfp_ros, xfp_po."""
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
    ros_my = LeagueState().my_roster_with_injuries()
    mine = ros_my[ros_my["position"] == "SP"]
    for _, p in mine.iterrows():
        nm = p["player_name"]
        ps, src = _lookup(PS, nm); stf, _ = _lookup(STF, nm)
        injured = bool(p.get("injured"))
        rd = pd.to_datetime(p.get("return_date"), errors="coerce")
        ret = rd.date() if (injured and pd.notna(rd)) else TODAY
        avail = max(TODAY, ret)
        ros, po = _sp_starts(avail)
        rows.append(dict(owner="MINE", name=nm, team=p.get("pro_team", ""), own="",
                         per_start=None if ps is None else round(float(ps), 2),
                         stuff=None if stf is None else round(float(stf), 0), src=src,
                         inj=p.get("injury_status", "") if injured else "",
                         ret=ret if injured else "",
                         xfp_ros=None if ps is None else round(float(ps) * ros, 0),
                         xfp_po=None if ps is None else round(float(ps) * po, 0)))

    # ---- FA pool ----
    ls = LeagueState(); lg = ls._get_league()
    # size=2000 UNFILTERED, position post-filtered — per-position size<2000 silently
    # drops low-owned high-FP FAs (feedback_fa_pool_size_cap.md; audit 2026-07-04).
    fas = [p for p in lg.free_agents(size=2000)
           if getattr(p, "position", None) == "SP"]
    inj_ids = [int(p.playerId) for p in fas if getattr(p, "injured", False)]
    ret_map = {}
    try:
        idf = ls.injury_details(inj_ids)
        rc = next((c for c in idf.columns if "return" in c.lower()), None)
        ic = next((c for c in idf.columns if c.lower() in ("player_id", "playerid", "id")), None)
        if rc and ic:
            for _, r in idf.iterrows():
                rv = pd.to_datetime(r[rc], errors="coerce")
                if pd.notna(rv):
                    ret_map[int(r[ic])] = rv.date()
    except Exception as e:
        print(f"[injury_details] {type(e).__name__}: {e}")

    for p in fas:
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
        rows.append(dict(owner="FA", name=nm, team=getattr(p, "proTeam", ""),
                         own=round(getattr(p, "percent_owned", 0) or 0, 1),
                         per_start=None if ps is None else round(float(ps), 2),
                         stuff=None if stf is None else round(float(stf), 0), src=src,
                         inj=status if injured else "", ret=ret if injured else "",
                         xfp_ros=None if ps is None else round(float(ps) * ros, 0),
                         xfp_po=None if ps is None else round(float(ps) * po, 0)))

    df = pd.DataFrame(rows)
    have = df[df["per_start"].notna()].copy()
    have = have.sort_values("xfp_ros", ascending=False).reset_index(drop=True)
    have.attrs["n_nodata"] = int(len(df) - len(have))
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


def _load_rh3():
    global _RH3, _RH3_BY_ID, _FULL, _AMBIG_NAMES, _MULTIYR
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


def _rh3_row(name, team=None, position=None):
    """Return (rh3_row_series, source_str) or (None, 'NO_DATA').
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
        return row, "id"
    nn = norm(name)
    if nn in _AMBIG_NAMES:
        return None, "NO_DATA"   # collision-safe: don't silently grab a row
    if nn in _FULL:
        return _FULL[nn], "name"
    return None, "NO_DATA"


def _project_hitter(name, team=None, position=None):
    """(per_game, rank, signal, etfr, src). Falls back to the calibrated talent
    prior (LOW-CONF, src='talent_prior') for elites absent from rh3."""
    row, src = _rh3_row(name, team=team, position=position)
    if row is not None:
        return (float(row["xfp_rh3_per_game"]), int(row["rank"]), str(row["signal"]),
                round(float(row["expected_total_fp_remaining"]), 0), src)
    try:
        bid = resolve_batter_id(name, team=alias_team(team), position=position, multiyr=_MULTIYR)
    except Exception:
        bid = None
    tp = TP.hitter_prior_pg(bid) if bid is not None else None
    if tp is not None:
        return (tp, None, "stash", None, "talent_prior")
    return (None, None, "", None, "NO_DATA")


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


def build_hitter_board() -> pd.DataFrame:
    """Merged hitter board: MINE hitters + every FA hitter, dual-ranked by
    xFP-RoS and xFP-playoffs, with bucket membership. Returns the FULL frame
    (ranked + no-data rows). `buckets` is a set per row; `per_game` is None for
    rh3-absent rows. Columns: owner, name, team, own, slots, buckets, per_game,
    rank, signal, etfr, src, inj, ret, xfp_ros, xfp_po."""
    _load_rh3()
    rows = []

    # ── MY hitters ──
    ros_my = LeagueState().my_roster_with_injuries()
    mine = ros_my[~ros_my["position"].isin(["SP", "RP", "P"])].copy()
    for _, p in mine.iterrows():
        nm = p["player_name"]
        team = p.get("pro_team", "") or None
        pos = p.get("position", "") or None
        per_game, rk, sig, etfr, src = _project_hitter(nm, team=team, position=pos)
        injured = bool(p.get("injured"))
        rd = pd.to_datetime(p.get("return_date"), errors="coerce")
        ret = rd.date() if (injured and pd.notna(rd)) else TODAY
        avail = max(TODAY, ret)
        rg, pg = _hitter_windows(avail)
        slots = p.get("eligible_slots", [])
        rows.append(dict(
            owner="MINE", name=nm, team=team or "", own="", slots=list(slots),
            per_game=None if per_game is None else round(per_game, 2),
            rank=rk, signal=sig, etfr=etfr, src=src,
            inj=p.get("injury_status", "") if injured else "",
            ret=ret if injured else "",
            xfp_ros=None if per_game is None else round(per_game * rg, 0),
            xfp_po=None if per_game is None else round(per_game * pg, 0),
        ))

    # ── FA pool: ONE unfiltered size=2000 pull, hitter-eligibility post-filter ──
    # (was 7 per-position size=1500 pulls — per-position fetches silently drop
    # low-owned high-FP FAs AND cost 7x the API calls. feedback_fa_pool_size_cap.md;
    # audit 2026-07-04.)
    ls = LeagueState(); lg = ls._get_league()
    seen, fa_players = set(), []
    try:
        for pl in lg.free_agents(size=2000):
            pid = int(pl.playerId)
            if pid in seen:
                continue
            if not _is_hitter_slots(getattr(pl, "eligibleSlots", [])):
                continue
            seen.add(pid)
            fa_players.append(pl)
    except Exception as e:
        print(f"[free_agents unfiltered] {type(e).__name__}: {e}")

    inj_ids = [int(p.playerId) for p in fa_players if getattr(p, "injured", False)]
    ret_map = {}
    try:
        idf = ls.injury_details(inj_ids)
        rc = next((c for c in idf.columns if "return" in c.lower()), None)
        ic = next((c for c in idf.columns if c.lower() in ("player_id", "playerid", "id")), None)
        if rc and ic:
            for _, r in idf.iterrows():
                rv = pd.to_datetime(r[rc], errors="coerce")
                if pd.notna(rv):
                    ret_map[int(r[ic])] = rv.date()
    except Exception as e:
        print(f"[injury_details] {type(e).__name__}: {e}")

    for p in fa_players:
        nm = p.name; pid = int(p.playerId)
        team = getattr(p, "proTeam", "") or None
        pos = getattr(p, "position", "") or None
        per_game, rk, sig, etfr, src = _project_hitter(nm, team=team, position=pos)
        injured = bool(getattr(p, "injured", False))
        status = getattr(p, "injuryStatus", "ACTIVE")
        if injured:
            ret = ret_map.get(pid) or (pd.Timestamp(TODAY) + pd.Timedelta(days=HEUR.get(status, 21))).date()
        else:
            ret = TODAY
        avail = max(TODAY, ret)
        rg, pg = _hitter_windows(avail)
        rows.append(dict(
            owner="FA", name=nm, team=team or "",
            own=round(getattr(p, "percent_owned", 0) or 0, 1),
            slots=list(getattr(p, "eligibleSlots", [])),
            per_game=None if per_game is None else round(per_game, 2),
            rank=rk, signal=sig, etfr=etfr, src=src,
            inj=status if injured else "", ret=ret if injured else "",
            xfp_ros=None if per_game is None else round(per_game * rg, 0),
            xfp_po=None if per_game is None else round(per_game * pg, 0),
        ))

    df = pd.DataFrame(rows)
    df["buckets"] = df["slots"].apply(buckets_for)
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

    # ── SP board ──
    sp = build_sp_board()
    sp_out = _sp_out_path()
    sp.to_csv(sp_out, index=False)
    n_mine = int((sp["owner"] == "MINE").sum())
    print(f"\nSP universe: {len(sp)} ranked ({n_mine} MINE + {len(sp)-n_mine} FA)"
          f" | no-data dropped: {sp.attrs.get('n_nodata', '?')}")
    print(f"  -> {sp_out}")

    # ── Hitter board ──
    hit = build_hitter_board()
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
    print(f"  id-joins: {(have['src']=='id').sum()} | name-fallback: "
          f"{(have['src']=='name').sum()} | talent-prior LOW-CONF: "
          f"{(have['src']=='talent_prior').sum()} [calib rh3_pg={a:.2f}+{b:.2f}*raw]")
    print(f"  -> {hit_out}")

    # smoke test: Max Muncy collision resolves to distinct ids
    mm_lad = resolve_batter_id("Max Muncy", team="LAD", position="3B", multiyr=_MULTIYR)
    mm_ath = resolve_batter_id("Max Muncy", team="ATH", position="C", multiyr=_MULTIYR)
    print(f"[smoke] Max Muncy LAD/3B -> {mm_lad} | ATH/C -> {mm_ath} "
          f"(distinct={mm_lad != mm_ath})")


if __name__ == "__main__":
    main()

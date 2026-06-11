"""Merged SP board: MY staff + every FA SP, one ranking by xFP-RoS and xFP-playoffs.

per_start tiers (honest source label):
  1. Stuff+ proj_ros_fp   (validated FA-SP signal — best)
  2. rp3 data_driven      (model-confident)
  3. rp3 marcel_il        (SUPPRESSED prior — low confidence, flagged 'marcel')
Windows match repo convention (RoS now->Sep20 ~17 healthy starts; Playoffs
Aug17->Sep20 x3.6), with live IL return dates folded in for both pools.
"""
from __future__ import annotations
import sys, re, unicodedata
from pathlib import Path
from datetime import date
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from plv_clone.league_state import LeagueState
from app.espn_connector import get_my_roster_with_injuries
import sp_stuff_model as ss
import talent_prior as TP   # provides flip_name for the rp3 "Last, First" fix

TODAY = date(2026, 6, 11)
SEASON_END = date(2026, 9, 20)
PLAYOFF_START = date(2026, 8, 17)
PLAYOFF_DAYS = (SEASON_END - PLAYOFF_START).days
RATE = 1.19 / 7.0
PLAYOFF_FULL = 3.6
HEUR = {"SIXTY_DAY_DL": 56, "FIFTEEN_DAY_DL": 21, "TEN_DAY_DL": 15,
        "OUT": 14, "DAY_TO_DAY": 0, "DOUBTFUL": 5, "QUESTIONABLE": 0}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", s.lower())).strip()


def li_key(nn):
    p = nn.split()
    return (p[-1], p[0][0]) if len(p) >= 2 and p[0] else None


def build_map(names, vals):
    full, li = {}, {}
    for nm, v in zip(names, vals):
        if pd.isna(v):
            continue
        nn = norm(nm); full[nn] = v
        k = li_key(nn)
        if k:
            li.setdefault(k, []).append(v)
    return full, li


def lookup(maps, nm):
    nn = norm(nm); k = li_key(nn)
    for full, li, src in maps:
        if nn in full:
            return full[nn], src
        b = li.get(k) if k else None
        if b and len(b) == 1:
            return b[0], src
    return None, "NO_DATA"


def starts(avail):
    ros = max(0.0, (SEASON_END - avail).days) * RATE
    po_days = max(0, (SEASON_END - max(avail, PLAYOFF_START)).days)
    return ros, PLAYOFF_FULL * po_days / PLAYOFF_DAYS


def main():
    # ---- per_start tiers -------------------------------------------------
    mdl, sc, _ = ss.fit_model()
    d = ss.load_2026().dropna(subset=ss.FEATS).copy()
    d["proj_ros_fp"] = mdl.predict(sc.transform(d[ss.FEATS]))
    sf = build_map(d["player_name_fg"], d["proj_ros_fp"])
    st = build_map(d["player_name_fg"], d["stuff_plus"])
    rp3 = pd.read_csv(ROOT / "data/outputs/xfp_rp3_projections.csv").dropna(subset=["player_name"])
    tag = rp3["data_quality_tag"].astype(str)
    dd = rp3[tag.str.startswith("data_driven")]
    mar = rp3[tag.str.contains("marcel")]
    # rp3 stores names "Last, First" — flip to "First Last" so they match the FA
    # pool / roster ("Blake Snell"). Without this every marcel-only arm (Snell,
    # Greene) silently fell into NO_DATA and vanished from the board.
    rp_dd = build_map(dd["player_name"].map(TP.flip_name), dd["xfp_rp3_per_start"])
    rp_mar = build_map(mar["player_name"].map(TP.flip_name), mar["xfp_rp3_per_start"])
    PS = [(*sf, "Stuff+"), (*rp_dd, "rp3_dd"), (*rp_mar, "talent_prior")]
    STF = [(*st, "")]

    rows = []

    # ---- MY staff --------------------------------------------------------
    ros_my = get_my_roster_with_injuries()
    mine = ros_my[ros_my["position"] == "SP"]
    for _, p in mine.iterrows():
        nm = p["player_name"]
        ps, src = lookup(PS, nm); stf, _ = lookup(STF, nm)
        injured = bool(p.get("injured"))
        rd = pd.to_datetime(p.get("return_date"), errors="coerce")
        ret = rd.date() if (injured and pd.notna(rd)) else (TODAY if not injured else TODAY)
        avail = max(TODAY, ret)
        ros, po = starts(avail)
        rows.append(dict(owner="MINE", name=nm, team=p.get("pro_team", ""), own="",
                         per_start=None if ps is None else round(float(ps), 2),
                         stuff=None if stf is None else round(float(stf), 0), src=src,
                         inj=p.get("injury_status", "") if injured else "",
                         ret=ret if injured else "",
                         xfp_ros=None if ps is None else round(float(ps) * ros, 0),
                         xfp_po=None if ps is None else round(float(ps) * po, 0)))

    # ---- FA pool ---------------------------------------------------------
    ls = LeagueState(); lg = ls._get_league()
    fas = [p for p in lg.free_agents(size=1500, position="SP")
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
        ps, src = lookup(PS, nm); stf, _ = lookup(STF, nm)
        injured = bool(getattr(p, "injured", False))
        status = getattr(p, "injuryStatus", "ACTIVE")
        if injured:
            ret = ret_map.get(pid) or (pd.Timestamp(TODAY) + pd.Timedelta(days=HEUR.get(status, 21))).date()
        else:
            ret = TODAY
        avail = max(TODAY, ret)
        ros, po = starts(avail)
        rows.append(dict(owner="FA", name=nm, team=getattr(p, "proTeam", ""),
                         own=round(getattr(p, "percent_owned", 0) or 0, 1),
                         per_start=None if ps is None else round(float(ps), 2),
                         stuff=None if stf is None else round(float(stf), 0), src=src,
                         inj=status if injured else "", ret=ret if injured else "",
                         xfp_ros=None if ps is None else round(float(ps) * ros, 0),
                         xfp_po=None if ps is None else round(float(ps) * po, 0)))

    df = pd.DataFrame(rows)
    have = df[df["per_start"].notna()].copy()
    out = ROOT / "data/research/sp_merged_xfp_rank_2026-06-11.csv"
    have.sort_values("xfp_ros", ascending=False).to_csv(out, index=False)

    def show(sortcol, label, n=55):
        v = have.sort_values(sortcol, ascending=False).head(n).copy()
        v["name"] = v.apply(lambda r: ("* " if r.owner == "MINE" else "  ") + str(r["name"]), axis=1)
        cols = ["name", "owner", "team", "own", "per_start", "stuff", "src", "inj", "ret", "xfp_ros", "xfp_po"]
        print(f"\n================= MERGED RANK BY {label} (top {n}; * = MINE) =================")
        print(v[cols].to_string(index=False))

    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 400)
    nmine = (have["owner"] == "MINE").sum()
    print(f"Merged SP universe: {len(have)} ranked ({nmine} MINE + {len(have)-nmine} FA) | "
          f"no-data dropped: {len(df)-len(have)}")
    show("xfp_ros", "xFP ROS")
    show("xfp_po", "xFP PLAYOFFS")
    print(f"\nFull merged board -> {out}")


if __name__ == "__main__":
    main()

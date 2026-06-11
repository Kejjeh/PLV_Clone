"""Rank EVERY FA SP by xFP-RoS and xFP-playoffs.

per_start lens: Stuff+ proj_ros_fp (validated FA-SP signal) primary, rp3
data_driven fallback (NEVER marcel_il — suppressed prior). Injury/return from
live ESPN. Windows match repo convention:
  RoS:      per_start * ros_starts   (ros_starts ~ (now->Sep20)/7 * 1.19 ~= 17 healthy)
  Playoffs: per_start * 3.6 * (playoff-window days available / 34)   (Aug17-Sep20)
Two-pass name match (norm exact -> (last, first-initial)) avoids Cam/Cameron leaks.
"""
from __future__ import annotations
import sys, re, unicodedata
from pathlib import Path
from datetime import date
import pandas as pd, numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))
from plv_clone.league_state import LeagueState
import sp_stuff_model as ss

TODAY = date(2026, 6, 11)
SEASON_END = date(2026, 9, 20)      # end of playoff period
PLAYOFF_START = date(2026, 8, 17)
PLAYOFF_DAYS = (SEASON_END - PLAYOFF_START).days   # 34
RATE = 1.19 / 7.0                    # starts per day (empirical 1.19/wk)
PLAYOFF_FULL = 3.6                   # repo convention: 3 wk * 1.19


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", s.lower())).strip()


def li_key(nn):
    p = nn.split()
    return (p[-1], p[0][0]) if len(p) >= 2 and p[0] else None


def build_map(names, vals):
    """Two-pass: full-norm dict + (last,initial)->{val} bucket."""
    full, li = {}, {}
    for nm, v in zip(names, vals):
        if pd.isna(v):
            continue
        nn = norm(nm); full[nn] = v
        k = li_key(nn)
        if k:
            li.setdefault(k, []).append(v)
    return full, li


def lookup(full, li, nm):
    nn = norm(nm)
    if nn in full:
        return full[nn]
    k = li_key(nn); b = li.get(k) if k else None
    if b and len(b) == 1:      # unambiguous last+initial
        return b[0]
    return None


def main():
    # --- per_start lenses ------------------------------------------------
    mdl, sc, _ = ss.fit_model()
    d = ss.load_2026().dropna(subset=ss.FEATS).copy()
    d["proj_ros_fp"] = mdl.predict(sc.transform(d[ss.FEATS]))
    sf_full, sf_li = build_map(d["player_name_fg"], d["proj_ros_fp"])
    st_full, st_li = build_map(d["player_name_fg"], d["stuff_plus"])

    rp3 = pd.read_csv(ROOT / "data/outputs/xfp_rp3_projections.csv").dropna(subset=["player_name"])
    dd = rp3[rp3["data_quality_tag"].astype(str).str.startswith("data_driven")]
    rp_full, rp_li = build_map(dd["player_name"], dd["xfp_rp3_per_start"])

    # --- FA SP pool (raw league: id + injury) ----------------------------
    ls = LeagueState(); lg = ls._get_league()
    fas = [p for p in lg.free_agents(size=1500, position="SP")
           if getattr(p, "position", None) == "SP"]
    inj_ids = [int(p.playerId) for p in fas if getattr(p, "injured", False)]
    ret = {}
    try:
        idf = ls.injury_details(inj_ids)
        rc = next((c for c in idf.columns if "return" in c.lower()), None)
        ic = next((c for c in idf.columns if c.lower() in ("player_id", "playerid", "id")), None)
        if rc and ic:
            for _, r in idf.iterrows():
                rv = pd.to_datetime(r[rc], errors="coerce")
                if pd.notna(rv):
                    ret[int(r[ic])] = rv.date()
    except Exception as e:
        print(f"[injury_details] {type(e).__name__}: {e}")

    # heuristic return if no explicit date (by injuryStatus bucket)
    HEUR = {"SIXTY_DAY_DL": 56, "FIFTEEN_DAY_DL": 21, "TEN_DAY_DL": 15,
            "OUT": 14, "DAY_TO_DAY": 0, "DOUBTFUL": 5, "QUESTIONABLE": 0}

    rows = []
    for p in fas:
        nm = p.name; pid = int(p.playerId)
        ps = lookup(sf_full, sf_li, nm); src = "Stuff+"
        if ps is None:
            ps = lookup(rp_full, rp_li, nm); src = "rp3_dd"
        if ps is None:
            src = "NO_DATA"
        stf = lookup(st_full, st_li, nm)
        injured = bool(getattr(p, "injured", False))
        status = getattr(p, "injuryStatus", "ACTIVE")
        if injured:
            rd = ret.get(pid)
            if rd is None:
                rd = TODAY + pd.Timedelta(days=HEUR.get(status, 21)).to_pytimedelta()
                rd = (pd.Timestamp(TODAY) + pd.Timedelta(days=HEUR.get(status, 21))).date()
        else:
            rd = TODAY
        avail = max(TODAY, rd)
        ros_starts = max(0.0, (SEASON_END - avail).days) * RATE
        po_days = max(0, (SEASON_END - max(avail, PLAYOFF_START)).days)
        po_starts = PLAYOFF_FULL * po_days / PLAYOFF_DAYS
        rows.append(dict(
            name=nm, team=getattr(p, "proTeam", ""), own=round(getattr(p, "percent_owned", 0) or 0, 1),
            per_start=None if ps is None else round(float(ps), 2),
            stuff=None if stf is None else round(float(stf), 0), src=src,
            inj=status if injured else "", ret=rd if injured else "",
            xfp_ros=None if ps is None else round(float(ps) * ros_starts, 0),
            xfp_po=None if ps is None else round(float(ps) * po_starts, 0)))

    df = pd.DataFrame(rows)
    have = df[df["per_start"].notna()].copy()
    nodata = len(df) - len(have)
    out = ROOT / "data/research/fa_sp_xfp_rank_2026-06-11.csv"
    have.sort_values("xfp_ros", ascending=False).to_csv(out, index=False)

    pd.set_option("display.width", 240); pd.set_option("display.max_rows", 400)
    cols = ["name", "team", "own", "per_start", "stuff", "src", "inj", "ret", "xfp_ros", "xfp_po"]
    print(f"FA SP pool: {len(df)} | with projection: {len(have)} | no-data tail: {nodata}")
    print(f"Windows: RoS now->{SEASON_END} (~17 healthy starts) | "
          f"Playoffs {PLAYOFF_START}->{SEASON_END} (x3.6 healthy)\n")
    print("================= RANKED BY xFP ROS (top 45) =================")
    print(have.sort_values("xfp_ros", ascending=False).head(45)[cols].to_string(index=False))
    print("\n================= RANKED BY xFP PLAYOFFS (top 45) =================")
    print(have.sort_values("xfp_po", ascending=False).head(45)[cols].to_string(index=False))
    print(f"\nFull ranking ({len(have)} arms) -> {out}")


if __name__ == "__main__":
    main()

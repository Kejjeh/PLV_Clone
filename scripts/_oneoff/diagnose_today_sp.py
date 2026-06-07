"""Diagnose today's SP performance vs the Stuff+ board: was each blowup
AVOIDABLE (model flagged regression: low stuff / negative d_proj) or VARIANCE
(high stuff, model liked it, just a bad night)?"""
from __future__ import annotations
import sys, datetime as dt
from pathlib import Path
import pandas as pd, requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "xfp"))
from sp_stuff_model import build  # noqa: E402

TODAY = dt.date.today().isoformat()  # 2026-06-06

def real_ip(ip_str):
    try:
        w, f = (ip_str.split(".") + ["0"])[:2]
        return int(w) + int(f) / 3
    except Exception:
        return 0.0

def brownu_fp(s):
    ip = real_ip(str(s.get("inningsPitched", "0.0")))
    return (int(s.get("strikeOuts",0)) + ip*3.3 - int(s.get("hits",0))
            - 2*int(s.get("earnedRuns",0)) - int(s.get("baseOnBalls",0))
            - int(s.get("hitByPitch",0)))

def today_line(mlbid):
    url=(f"https://statsapi.mlb.com/api/v1/people/{mlbid}/stats"
         f"?stats=gameLog&group=pitching&season=2026")
    try:
        r=requests.get(url,timeout=20).json()
        for blk in r.get("stats",[]):
            for sp in blk.get("splits",[]):
                if sp.get("date")==TODAY:
                    return sp["stat"]
    except Exception as e:
        print(f"  api err {mlbid}: {e}")
    return None

def main():
    d,_=build()
    mine=d[d["own"]=="MINE"].copy()
    print(f"Checking {len(mine)} rostered SPs for a {TODAY} start...\n")
    rows=[]
    for _,r in mine.iterrows():
        st=today_line(int(r["mlb_id"]))
        if not st or int(st.get("gamesStarted",0))==0:
            continue
        fp=brownu_fp(st)
        rows.append({"name":r["player_name_fg"],"stuff":r["stuff_plus"],
            "projFP":r["proj_ros_fp"],"d_proj":r["proj_vs_current"],
            "line":f"{st.get('inningsPitched')}IP {st.get('strikeOuts')}K "
                   f"{st.get('hits')}H {st.get('earnedRuns')}ER {st.get('baseOnBalls')}BB",
            "todayFP":round(fp,1)})
    if not rows:
        print("None of your SPs have a recorded start dated today in the MLB API."
              " (Either none started today, or stats haven't posted yet.)")
        return
    t=pd.DataFrame(rows).sort_values("todayFP")
    print(f"{'SP':<20}{'Stuff+':>7}{'projFP':>8}{'todayFP':>9}  line")
    print("-"*72)
    for _,r in t.iterrows():
        print(f"{r['name']:<20}{r['stuff']:>7.0f}{r['projFP']:>8.1f}{r['todayFP']:>9.1f}  {r['line']}")
    print("\nVERDICT per blown start (todayFP < 5 = a dud):")
    for _,r in t[t["todayFP"]<5].iterrows():
        if r["d_proj"]< -1.0 or r["stuff"]<100:
            v=f"AVOIDABLE — model flagged regression (Stuff+ {r['stuff']:.0f}, d_proj {r['d_proj']:+.1f})"
        else:
            v=f"VARIANCE — model liked him (Stuff+ {r['stuff']:.0f}, projFP {r['projFP']:.1f}); bad night, hold"
        print(f"  {r['name']}: {v}")

if __name__=="__main__":
    main()

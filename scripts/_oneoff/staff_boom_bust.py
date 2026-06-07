"""boom-bust-history for my SP staff + measured bust% vs Stuff+-tier-implied bust%."""
from __future__ import annotations
import sys, statistics, requests
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "xfp"))
from sp_stuff_model import build  # noqa: E402

BOOM, BUST = 20.0, 5.0
# Stuff+-tier-implied bust% from messick_comps_boombust.py tier table
def implied_bust(s):
    if s < 95: return 31.6
    if s < 100: return 25.7
    if s < 105: return 24.3
    if s < 110: return 18.8
    return 14.7

def fp(st):
    ips=str(st.get("inningsPitched","0.0")); w,f=(ips.split(".")+["0"])[:2]
    ip=int(w)+int(f)/3
    return (int(st.get("strikeOuts",0))+ip*3.3-int(st.get("hits",0))
            -2*int(st.get("earnedRuns",0))-int(st.get("baseOnBalls",0))-int(st.get("hitByPitch",0)))

def last8(pid):
    out=[]
    for yr in [2026,2025]:
        try:
            r=requests.get(f"https://statsapi.mlb.com/api/v1/people/{pid}/stats"
                           f"?stats=gameLog&group=pitching&season={yr}",timeout=20).json()
            sp=[s for s in r["stats"][0]["splits"] if int(s["stat"].get("gamesStarted",0))>=1]
            sp.sort(key=lambda s:s["date"],reverse=True)
            for s in sp:
                out.append((yr,round(fp(s["stat"]),1)))
                if len(out)>=8: break
            if len(out)>=8: break
        except Exception as e:
            print(f"  err {pid} {yr}: {e}")
    return out

def trend(fps):
    if len(fps)<3: return "?"
    l8=statistics.mean(fps); l5=statistics.mean(fps[:5]); l3=statistics.mean(fps[:3])
    sd,ld=l3-l5,l5-l8
    if sd>=2 and ld>=0: return "UP"
    if sd<=-2 and ld<=0: return "DOWN"
    return "FLAT"

def tag(boom,bust,tr,std):
    t=[]
    if boom==0 and bust>=25: t.append("CAP FODDER")
    if tr=="DOWN" and bust>=25: t.append("DECLINING")
    if boom>=30 and tr=="UP": t.append("HOT STREAK")
    if std>9: t.append("VOLATILE")
    if std<5 and bust<=10: t.append("FLOOR")
    return "+".join(t) or "-"

def main():
    d,_=build(); mine=d[d.own=="MINE"].copy()
    rows=[]
    for _,r in mine.iterrows():
        g=last8(int(r.mlb_id))
        if not g: continue
        yrs="+".join(str(y) for y in sorted(set(y for y,_ in g)))
        fps=[v for _,v in g]; n=len(fps)
        boom=100*sum(f>=BOOM for f in fps)/n; bust=100*sum(f<BUST for f in fps)/n
        std=statistics.stdev(fps) if n>1 else 0
        rows.append(dict(name=r.player_name_fg,stuff=r.stuff_plus,proj=r.proj_ros_fp,yr=yrs,n=n,
            l8=statistics.mean(fps),l5=statistics.mean(fps[:5]),l3=statistics.mean(fps[:3]),
            tr=trend(fps),std=std,mn=min(fps),mx=max(fps),boom=boom,bust=bust,
            impl=implied_bust(r.stuff_plus),tag=tag(boom,bust,trend(fps),std)))
    rows.sort(key=lambda x:-x["l5"])
    h=(f"{'SP':<18}{'Yr':>5}{'N':>3}{'L8':>6}{'L5':>6}{'L3':>6}{'Tr':>5}{'Std':>6}"
       f"{'Min':>6}{'Max':>6}{'Boom%':>7}{'Bust%':>7}{'Stuff+':>7}{'impBust':>8}{'dBust':>7}  Note")
    print(h); print("-"*len(h))
    for r in rows:
        print(f"{r['name']:<18}{r['yr']:>5}{r['n']:>3}{r['l8']:>6.1f}{r['l5']:>6.1f}{r['l3']:>6.1f}"
              f"{r['tr']:>5}{r['std']:>6.1f}{r['mn']:>6.1f}{r['mx']:>6.1f}{r['boom']:>7.0f}{r['bust']:>7.0f}"
              f"{r['stuff']:>7.0f}{r['impl']:>8.0f}{r['bust']-r['impl']:>+7.0f}  {r['tag']}")
    print("\nimpBust = Stuff+-tier-implied bust% | dBust = measured − implied "
          "(positive = busts MORE than his stuff predicts)")

if __name__=="__main__":
    main()

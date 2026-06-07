"""Most-droppable SP synthesis across every lens built this session:
canonical RoS value (rp3 per_start + Blended xFP) + floor (bust prob) +
measured variance (boom/bust) + buy-low gap + IL flag."""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"xfp"))
from sp_stuff_model import build  # noqa
from sp_floor_model import floor_for  # noqa
ROOT = Path(__file__).resolve().parents[2]

# measured boom%/bust%/std from /boom-bust-history run (L8, 2026-06-06)
MEAS = {  # name_substr: (boom%, bust%, std)
 "Glasnow":(25,12,9.4),"Messick":(12,0,4.3),"Bradish":(38,25,10.8),"Fried":(25,25,10.0),
 "Rodon":(12,12,6.2),"Valdez":(0,25,10.5),"Soriano":(12,38,8.8),"Peralta":(0,12,4.7),
 "Leiter":(25,25,8.7),"Warren":(25,12,8.7)}

def meas(name):
    for k,v in MEAS.items():
        if k in name: return v
    return (None,None,None)

def main():
    d,_=build(); mine=d[d.own=="MINE"][["mlb_id","player_name_fg","stuff_plus","proj_ros_fp","breakout_gap"]].copy()
    rp3=pd.read_csv(ROOT/"data/outputs/xfp_rp3_projections.csv").rename(columns={"pitcher":"mlb_id"})
    m=mine.merge(rp3[["mlb_id","xfp_rp3_per_start","data_quality_tag","is_on_il_at_split",
        "replacement_delta","recency_form_gap"]],on="mlb_id",how="left")
    bl=pd.read_csv(ROOT/"data/outputs/live_blend_xfp_latest.csv").rename(columns={"mlbam_id":"mlb_id"})
    m=m.merge(bl[["mlb_id","live_blend_xfp","confidence_tier"]],on="mlb_id",how="left")
    cur=pd.read_csv(ROOT/"data/research/fg_asof/fg_pit_2026_current.csv")
    for c in ["k_pct","bb_pct"]: cur[c]=pd.to_numeric(cur[c],errors="coerce")
    m=m.merge(cur[["mlb_id","k_pct","bb_pct"]],on="mlb_id",how="left")
    m["bust_prob"],m["floor_tier"]=floor_for(m.k_pct.fillna(m.k_pct.mean()).values,
                                             m.bb_pct.fillna(m.bb_pct.mean()).values)
    m["boom"],m["bust_m"],m["std"]=zip(*m.player_name_fg.map(meas))
    m["kbb"]=((m.k_pct-m.bb_pct)*100).round(1)
    # canonical keep value = rp3 per_start (fallback blend)
    m["keep"]=m.xfp_rp3_per_start.fillna(m.live_blend_xfp).fillna(m.proj_ros_fp)
    m=m.sort_values("keep")
    cols_h=(f"{'SP':<17}{'rp3':>6}{'blend':>7}{'projF':>6}{'gap':>5}{'K-BB':>6}"
            f"{'boom%':>6}{'bust%':>6}{'floor':>9}{'IL':>4}  dqt")
    print(cols_h); print("-"*len(cols_h))
    for _,r in m.iterrows():
        rp=f"{r.xfp_rp3_per_start:.1f}" if pd.notna(r.xfp_rp3_per_start) else "  -"
        bl_=f"{r.live_blend_xfp:.1f}" if pd.notna(r.live_blend_xfp) else "  -"
        il="IL" if r.is_on_il_at_split==True else ""
        print(f"{r.player_name_fg:<17}{rp:>6}{bl_:>7}{r.proj_ros_fp:>6.1f}{r.breakout_gap:>+5.0f}"
              f"{r.kbb:>6.1f}{(r.boom or 0):>6.0f}{(r.bust_m or 0):>6.0f}"
              f"{r.bust_prob*100:>6.0f}% {r.floor_tier:<2}{il:>4}  {r.data_quality_tag}")
    print("\nSorted by canonical keep value (rp3 per_start) ASC = most droppable on top.")
    print("gap=Stuff+ breakout gap (+=buy-low signal); floor=per-start bust prob; boom/bust%=measured L8.")

if __name__=="__main__":
    main()

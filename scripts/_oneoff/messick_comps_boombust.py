"""Messick comps (both directions) + Stuff+ vs boom/bust relationship.

Messick 2026: Stuff+ 95.6 (low) BUT Location+ 105.6 (high), K% 26.4, BB% 7.5,
archetype PURE_MOVEMENT (STUFF 58 / MOVEMENT 67 / CONTROL 56). Currently 15.7
FP/start; Stuff+ board projects 12.0 (bench lean). This script stress-tests
that lean with historical comps, then quantifies how Stuff+ relates to boom/bust.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import pearsonr

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "xfp"))
from validate_fg_pitch_modeling_inseason import load  # noqa: E402
ROOT = Path(__file__).resolve().parents[2]

def hdr(t): print("\n"+"="*78+f"\n{t}\n"+"="*78)

def main():
    d = load()  # 2021-25 SP-seasons: stuff_plus(as-of), location_plus, pre_fp, ros_fp
    a = pd.read_csv(ROOT/"data/research/sp_ratings_master.csv").rename(columns={"pitcher":"mlb_id"})
    d = d.merge(a[["mlb_id","year","STUFF","MOVEMENT","CONTROL","archetype"]],on=["mlb_id","year"],how="left")

    # ---- Messick-situation cohort: LOW stuff but PRODUCING at midseason ----
    coh = d[(d.stuff_plus<=100) & (d.pre_fp>=13)].copy()
    sustained = coh[coh.ros_fp>=13]
    regressed = coh[coh.ros_fp<9]
    hdr("MESSICK COHORT: low Stuff+ (<=100) + hot results (pre_fp>=13)")
    print(f"  cohort n={len(coh)}  | SUSTAINED (RoS>=13): {len(sustained)} ({100*len(sustained)/len(coh):.0f}%)"
          f"  | REGRESSED (RoS<9): {len(regressed)} ({100*len(regressed)/len(coh):.0f}%)"
          f"  | middle: {len(coh)-len(sustained)-len(regressed)}")
    print(f"  mean pre_fp {coh.pre_fp.mean():.1f} -> mean RoS {coh.ros_fp.mean():.1f} (delta {coh.ros_fp.mean()-coh.pre_fp.mean():+.1f})")

    # The discriminator: does LOCATION (Messick's edge, 105.6) separate sustain vs regress?
    print(f"\n  DISCRIMINATOR — mean Location+ : sustained {sustained.location_plus.mean():.1f}  vs  regressed {regressed.location_plus.mean():.1f}")
    print(f"  mean archetype CONTROL        : sustained {sustained.CONTROL.mean():.0f}  vs  regressed {regressed.CONTROL.mean():.0f}")
    print(f"  mean archetype MOVEMENT       : sustained {sustained.MOVEMENT.mean():.0f}  vs  regressed {regressed.MOVEMENT.mean():.0f}")
    hi = coh[coh.location_plus>=103]; lo = coh[coh.location_plus<103]
    print(f"\n  Sustain rate by location (Messick=105.6 -> HIGH group):")
    print(f"    HIGH loc (>=103, n={len(hi)}): {100*(hi.ros_fp>=13).mean():.0f}% sustain, {100*(hi.ros_fp<9).mean():.0f}% regress")
    print(f"    LOW  loc (<103,  n={len(lo)}): {100*(lo.ros_fp>=13).mean():.0f}% sustain, {100*(lo.ros_fp<9).mean():.0f}% regress")

    def show(df, title, n=10):
        print(f"\n  {title}:")
        print(f"  {'pitcher':<20}{'yr':>5}{'Stuff+':>7}{'Loc+':>6}{'preFP':>7}{'rosFP':>7}{'CTRL':>5}{'MOV':>5}  archetype")
        for _,r in df.sort_values("ros_fp",ascending=(title.startswith('SUPPORT'))).head(n).iterrows():
            print(f"  {str(r['player_name_fg'])[:19]:<20}{int(r['year']):>5}{r['stuff_plus']:>7.0f}{r['location_plus']:>6.0f}"
                  f"{r['pre_fp']:>7.1f}{r['ros_fp']:>7.1f}{r.get('CONTROL',np.nan):>5.0f}{r.get('MOVEMENT',np.nan):>5.0f}  {r.get('archetype','')}")

    hdr("COUNTER-EXAMPLES (bull case): low Stuff+ + hot who SUSTAINED — esp. high-location like Messick")
    show(sustained[sustained.location_plus>=103], "SUSTAINED with high location (Messick's profile)", 12)
    hdr("SUPPORTING (bear case): low Stuff+ + hot who REGRESSED")
    show(regressed, "SUPPORT-BENCH: regressed hard", 12)

    # ---- Stuff+ vs boom/bust ----
    hdr("STUFF+ vs BOOM/BUST  (per-start panel, boom>=20 / bust<5 FP)")
    panel = pd.read_parquet(ROOT/"data/research/_boom_stack_per_start_panel_cache.parquet")
    g = panel.groupby(["pitcher","year"]).agg(
        n=("fp","size"), boom=("fp",lambda x:(x>=20).mean()*100),
        bust=("fp",lambda x:(x<5).mean()*100), meanfp=("fp","mean"), stdfp=("fp","std")).reset_index()
    g = g[g.n>=10]
    # join as-of Stuff+ (2021-25)
    fg = pd.concat([pd.read_csv(ROOT/f"data/research/fg_asof/fg_pit_{y}_pre.csv").assign(year=y) for y in [2021,2022,2023,2024,2025]])
    fg = fg.rename(columns={"mlb_id":"pitcher"})[["pitcher","year","stuff_plus"]].dropna()
    fg["stuff_plus"]=pd.to_numeric(fg["stuff_plus"],errors="coerce")
    gg = g.merge(fg,on=["pitcher","year"]).dropna(subset=["stuff_plus"])
    print(f"  n pitcher-seasons (>=10 starts, w/ Stuff+): {len(gg)}")
    for y in ["boom","bust","stdfp","meanfp"]:
        r,p = pearsonr(gg["stuff_plus"],gg[y])
        print(f"  corr(Stuff+, {y:<7}) = {r:+.3f}  (p={p:.1e})")
    gg["tier"]=pd.cut(gg.stuff_plus,[0,95,100,105,110,200],labels=["<95","95-100","100-105","105-110","110+"])
    print(f"\n  {'Stuff+ tier':<12}{'n':>5}{'boom%':>8}{'bust%':>8}{'meanFP':>8}{'stdFP':>7}")
    for t,sub in gg.groupby("tier",observed=True):
        print(f"  {str(t):<12}{len(sub):>5}{sub.boom.mean():>8.1f}{sub.bust.mean():>8.1f}{sub.meanfp.mean():>8.1f}{sub.stdfp.mean():>7.1f}")

if __name__=="__main__":
    main()

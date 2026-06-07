"""Decompose Stuff+ into physics: which component (velo / IVB / HB / extension)
drives the FANTASY signal? + my staff's velo-vs-movement profile."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import pearsonr
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"xfp"))
from validate_fg_pitch_modeling_inseason import load  # noqa
ROOT=Path(__file__).resolve().parents[2]
FB=["FF","SI"]

def fb_profile(years):
    frames=[]
    for y in years:
        d=pd.read_parquet(ROOT/f"data/raw/statcast_{y}.parquet",
            columns=["pitcher","pitch_type","release_speed","pfx_z","pfx_x","release_extension","p_throws"])
        d=d[d.pitch_type.isin(FB)].dropna(subset=["release_speed","pfx_z","pfx_x"])
        d["ivb"]=d.pfx_z*12; d["hb"]=(d.pfx_x.abs())*12
        g=d.groupby("pitcher").agg(velo=("release_speed","mean"),ivb=("ivb","mean"),
            hb=("hb","mean"),ext=("release_extension","mean"),npf=("release_speed","size"))
        g["year"]=y; frames.append(g.reset_index())
    f=pd.concat(frames); return f[f.npf>=150]

def main():
    d=load()  # ros_fp, stuff_plus per pitcher-season 2021-25
    phys=fb_profile([2021,2022,2023,2024,2025])
    d=d.merge(phys,left_on=["mlb_id","year"],right_on=["pitcher","year"],how="inner")
    comp=["velo","ivb","hb","ext"]
    print(f"n pitcher-seasons w/ FB physics + ros_fp: {len(d)}\n")
    print("Univariate corr with RoS FP/start:")
    for c in comp:
        r,p=pearsonr(d[c],d.ros_fp); print(f"  {c:<5} r={r:+.3f} (p={p:.1e})")
    print(f"\n  (ref) stuff_plus r={pearsonr(d.stuff_plus,d.ros_fp)[0]:+.3f}")
    X=StandardScaler().fit_transform(d[comp]); m=LinearRegression().fit(X,d.ros_fp)
    print(f"\nMultivariate standardized coefs -> RoS FP (R2={m.score(X,d.ros_fp):.3f}):")
    for c,co in sorted(zip(comp,m.coef_),key=lambda t:-abs(t[1])):
        print(f"  {c:<5} {co:+.2f} FP/SD")
    # how much of Stuff+ is each component?
    print("\nWhat Stuff+ is made of (corr with stuff_plus):")
    for c in comp:
        print(f"  {c:<5} r={pearsonr(d[c],d.stuff_plus)[0]:+.3f}")
    # my staff profile (2026)
    print("\n=== MY STAFF 2026 — velo vs movement profile ===")
    p26=fb_profile([2026])
    import importlib; sys.path.insert(0,str(ROOT/"scripts/xfp"))
    from sp_stuff_model import build
    mine=build()[0]; mine=mine[mine.own=="MINE"][["mlb_id","player_name_fg","stuff_plus"]]
    mp=mine.merge(p26,left_on="mlb_id",right_on="pitcher",how="left")
    for c in comp:
        mp[c+"_z"]=((mp[c]-d[c].mean())/d[c].std()).round(1)
    print(mp[["player_name_fg","stuff_plus","velo","ivb","hb","ext","velo_z","ivb_z"]].sort_values("stuff_plus",ascending=False).to_string(index=False))
    print("\nvelo_z / ivb_z = SDs above/below the 2021-25 SP mean. High ivb_z w/ low velo_z = movement-driven (Messick-type).")

if __name__=="__main__":
    main()

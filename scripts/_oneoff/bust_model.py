"""Bust/floor model: what predicts a SP's bust rate (<5 FP starts) BEYOND Stuff+?
Stuff+ shifts the mean but not the variance, so this models the floor directly.

Per pitcher-season: bust% (from 31k-start panel) ~ season skill features (FG).
Candidates: stuff_plus, bb_pct, k_pct, gb_pct, hard_hit_pct, barrel_pct, swstr_pct.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import pearsonr
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
FEATS = ["stuff_plus","bb_pct","k_pct","gb_pct","hard_hit_pct","barrel_pct","swstr_pct"]

def main():
    # per pitcher-season bust/boom from the per-start panel
    panel = pd.read_parquet(ROOT/"data/research/_boom_stack_per_start_panel_cache.parquet")
    g = panel.groupby(["pitcher","year"]).agg(
        n=("fp","size"), bust=("fp",lambda x:(x<5).mean()*100),
        boom=("fp",lambda x:(x>=20).mean()*100), meanfp=("fp","mean")).reset_index()
    g = g[g.n>=12]
    # FG full-season features
    fg=[]
    for y in [2021,2022,2023,2024,2025]:
        f=pd.read_csv(ROOT/f"data/outputs/fangraphs_pitchers_{y}.csv")
        f["year"]=y; fg.append(f)
    fg=pd.concat(fg).rename(columns={"mlb_id":"pitcher"})
    for c in FEATS:
        fg[c]=pd.to_numeric(fg[c],errors="coerce")
    d=g.merge(fg[["pitcher","year"]+FEATS],on=["pitcher","year"]).dropna(subset=FEATS+["bust"])
    print(f"n pitcher-seasons (>=12 starts, FG-joined): {len(d)}")
    print(f"mean bust% = {d.bust.mean():.1f}\n")

    print("UNIVARIATE corr with bust% (what tracks a high-floor-risk arm):")
    for c in FEATS:
        r,p=pearsonr(d[c],d.bust)
        print(f"  {c:<14} r={r:+.3f}  (p={p:.1e})")

    # standardized multiple regression: which drive bust INDEPENDENTLY
    X=StandardScaler().fit_transform(d[FEATS]); y=d.bust.values
    m=LinearRegression().fit(X,y)
    order=sorted(zip(FEATS,m.coef_),key=lambda t:t[1])
    print(f"\nMULTIVARIATE standardized coefs (bust% per +1 SD, controlling others); R2={m.score(X,y):.3f}:")
    for c,co in order:
        print(f"  {c:<14} {co:+.2f} pp/SD")
    print("  (negative = REDUCES busts; positive = RAISES busts)")

    # apply to my 2026 staff to explain measured bust rates
    print("\n=== MY STAFF 2026 — floor drivers (why each busts) ===")
    cur=pd.read_csv(ROOT/"data/research/fg_asof/fg_pit_2026_current.csv").rename(columns={"mlb_id":"pitcher"})
    for c in FEATS:
        if c in cur.columns: cur[c]=pd.to_numeric(cur[c],errors="coerce")
    mine_names=["Glasnow","Messick","Bradish","Fried","Rodon","Valdez","Soriano","Peralta","Leiter","Warren"]
    # predicted bust from model, using only features present in the 2026 snapshot
    avail=[c for c in FEATS if c in cur.columns and cur[c].notna().sum()>0]
    sc=StandardScaler().fit(d[avail]); mm=LinearRegression().fit(sc.transform(d[avail]),y)
    sub=cur[cur["player_name_fg"].str.contains("|".join(mine_names),na=False)].copy()
    sub=sub.dropna(subset=avail)
    sub["pred_bust"]=mm.predict(sc.transform(sub[avail]))
    cols=["player_name_fg","stuff_plus","bb_pct","gb_pct","hard_hit_pct","barrel_pct","pred_bust"]
    cols=[c for c in cols if c in sub.columns]
    print(f"  features available in 2026 cur: {avail}")
    print(sub[cols].sort_values("pred_bust",ascending=False).to_string(index=False))

if __name__=="__main__":
    main()

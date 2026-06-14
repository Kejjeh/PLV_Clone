"""
Velo x Platoon SP decline-risk study (leakage-safe, as-of).
Question: does a PLATOON-split signal (alone or x velo decline) predict
RoS SP FP/start BETTER than the overall FB-velo decline flags we already
validated?

Output: data/research/validation_runs/velo_platoon_2026-06-13.md
Run:  PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/_oneoff/velo_platoon_study.py
"""
import numpy as np
import pandas as pd
from scipy import stats

CUTOFFS = [51, 72, 93, 114]
YEARS = [2021, 2022, 2023, 2024, 2025]
CACHE = "data/research/xfp_cache"

# ----------------------------------------------------------------------
# 1. Panel + forward target
# ----------------------------------------------------------------------
panel = pd.read_csv(f"{CACHE}/rolling_pitchers_2018_2026.csv")
panel["cutoff_date"] = pd.to_datetime(panel["cutoff_date"])

# prior-year season-end velo (max split_day per pitcher-year)
se = (panel.sort_values("split_day").groupby(["pitcher", "year"]).tail(1)
      [["pitcher", "year", "avg_velo_to"]]
      .rename(columns={"avg_velo_to": "season_end_velo"}))
se_prev = se.copy()
se_prev["year"] = se_prev["year"] + 1
se_prev = se_prev.rename(columns={"season_end_velo": "prev_season_end_velo"})

cells = panel[(panel.year.isin(YEARS)) & (panel.gs_to >= 5) &
              (panel.ros_gs >= 3) & (panel.split_day.isin(CUTOFFS))].copy()
cells = cells.merge(se_prev, on=["pitcher", "year"], how="left")
# overall velo-YoY delta (cumulative current velo minus prior-year season end)
cells["vYoY"] = cells["avg_velo_to"] - cells["prev_season_end_velo"]

keep = ["pitcher", "year", "split_day", "cutoff_date", "ros_fp_per_start",
        "ros_gs", "gs_to", "avg_velo_to", "swstr_pct_to", "k_pct_to",
        "fp_per_start_to", "vYoY"]
cells = cells[keep].reset_index(drop=True)
print(f"panel cells: {len(cells)}")

# ----------------------------------------------------------------------
# 2. As-of platoon features from pitch-level statcast (pitches < cutoff)
# ----------------------------------------------------------------------
def woba_outcomes(df):
    """Use statcast woba_value/woba_denom for true wOBA-against."""
    return df["woba_value"], df["woba_denom"]

plat_rows = []
for yr in YEARS:
    sc = pd.read_parquet(f"{CACHE}/statcast_{yr}.parquet",
                         columns=["game_date", "pitcher", "stand", "p_throws",
                                  "release_speed", "events", "description",
                                  "woba_value", "woba_denom", "pitch_type",
                                  "game_type"])
    sc = sc[sc.game_type == "R"]
    sc["game_date"] = pd.to_datetime(sc["game_date"])
    # same vs opposite hand
    sc["opp_hand"] = (sc["stand"] != sc["p_throws"])
    # fastball mask for velo (FF/SI/FC)
    sc["is_fb"] = sc["pitch_type"].isin(["FF", "SI", "FC"])
    cy = cells[cells.year == yr]
    cutoff_dates = cy[["split_day", "cutoff_date"]].drop_duplicates()
    for _, cd in cutoff_dates.iterrows():
        sd, cdate = cd["split_day"], cd["cutoff_date"]
        asof = sc[sc.game_date < cdate]
        if len(asof) == 0:
            continue
        for opp, sub in asof.groupby("opp_hand"):
            g = sub.groupby("pitcher")
            bf = g["woba_denom"].sum()           # PA denom
            wv = g["woba_value"].sum()
            woba = wv / bf.replace(0, np.nan)
            k = g["events"].apply(lambda e: (e == "strikeout").sum())
            sw = g["description"].apply(lambda d: d.isin(
                ["swinging_strike", "swinging_strike_blocked"]).sum())
            npitch = g.size()
            fbvel = sub[sub.is_fb].groupby("pitcher")["release_speed"].mean()
            tag = "opp" if opp else "same"
            out = pd.DataFrame({
                "pitcher": bf.index,
                f"bf_{tag}": bf.values,
                f"woba_{tag}": woba.values,
                f"kpct_{tag}": (k / bf.replace(0, np.nan)).values,
                f"swstr_{tag}": (sw / npitch.replace(0, np.nan)).values,
                f"fbvel_{tag}": fbvel.reindex(bf.index).values,
            })
            out["year"] = yr
            out["split_day"] = sd
            plat_rows.append(out)
    print(f"  processed {yr}")

# merge same/opp into one row per (pitcher, year, split_day)
opp_df = pd.concat([r for r in plat_rows if "woba_opp" in r.columns])
same_df = pd.concat([r for r in plat_rows if "woba_same" in r.columns])
plat = opp_df.merge(same_df, on=["pitcher", "year", "split_day"], how="outer")

# platoon-split constructs
plat["woba_split"] = plat["woba_opp"] - plat["woba_same"]   # +ve = worse vs opp
plat["kpct_split"] = plat["kpct_same"] - plat["kpct_opp"]   # +ve = fewer Ks vs opp (vuln)
plat["velo_split"] = plat["fbvel_same"] - plat["fbvel_opp"]
plat["opp_bf_frac"] = plat["bf_opp"] / (plat["bf_opp"] + plat["bf_same"])

df = cells.merge(plat, on=["pitcher", "year", "split_day"], how="left")
# coverage gate: need >=80 BF vs opposite hand for a stable split read
df["has_split"] = (df["bf_opp"] >= 80) & (df["bf_same"] >= 50)
print(f"cells with split coverage (>=80 opp BF): {df['has_split'].sum()} / {len(df)}")

# ----------------------------------------------------------------------
# 3. Partial correlation helper
# ----------------------------------------------------------------------
def partial_r(d, x, y, controls):
    sub = d[[x, y] + controls].dropna().astype(float)
    n = len(sub)
    if n < 30:
        return np.nan, np.nan, n
    import numpy.linalg as la
    C = np.column_stack([np.ones(n), sub[controls].values])
    def resid(v):
        beta, *_ = la.lstsq(C, v, rcond=None)
        return v - C @ beta
    rx, ry = resid(sub[x].values), resid(sub[y].values)
    if rx.std() == 0 or ry.std() == 0:
        return np.nan, np.nan, n
    r, p = stats.pearsonr(rx, ry)
    return r, p, n

# baseline level controls (Rule 9): whiff/K level + fp base
df["lvl"] = df["swstr_pct_to"].rank() + df["k_pct_to"].rank()
BASE = ["lvl", "fp_per_start_to"]
BASE_V = ["lvl", "fp_per_start_to", "vYoY"]

Y = "ros_fp_per_start"
constructs = ["woba_split", "kpct_split", "velo_split", "woba_opp",
              "kpct_opp", "opp_bf_frac", "fbvel_opp"]

dd = df[df.has_split].copy()
print(f"\nanalysis sample (split coverage): {len(dd)}")

lines = []
def L(s=""):
    print(s); lines.append(s)

L("## Partial-r table (sample = cells with >=80 opp BF)")
L(f"n analysis cells = {len(dd)}")
L("")
L("| construct | r over [level,fp] | p | r over [level,fp,vYoY] | p | n |")
L("|---|---|---|---|---|---|")
results = {}
for c in constructs:
    r1, p1, n1 = partial_r(dd, c, Y, BASE)
    r2, p2, n2 = partial_r(dd, c, Y, BASE_V)
    results[c] = (r1, p1, r2, p2, n1)
    L(f"| {c} | {r1:+.3f} | {p1:.3f} | {r2:+.3f} | {p2:.3f} | {n1} |")

# reference: overall velo decline on same analysis sample
rv1, pv1, nv1 = partial_r(dd, "vYoY", Y, BASE)
L("")
L(f"REFERENCE overall velo (vYoY) over [level,fp]: r={rv1:+.3f} p={pv1:.3f} n={nv1}")

# ----------------------------------------------------------------------
# 4. INTERACTION: velo decline x platoon vulnerability tertile
# ----------------------------------------------------------------------
L("")
L("## Interaction: velo-decline (vYoY) partial-r within platoon-vulnerability tertile")
L("vulnerability = woba_split (worse vs opposite hand). Tertile within sample.")
dd2 = dd.dropna(subset=["woba_split", "vYoY"]).copy()
dd2["vuln_tert"] = pd.qcut(dd2["woba_split"], 3, labels=["low", "mid", "high"])
L("")
L("| vuln tertile | vYoY partial-r over [level,fp] | p | n |")
L("|---|---|---|---|")
for t in ["low", "mid", "high"]:
    s = dd2[dd2.vuln_tert == t]
    r, p, n = partial_r(s, "vYoY", Y, BASE)
    L(f"| {t} | {r:+.3f} | {p:.3f} | {n} |")

# explicit product interaction term in full sample
dd2["vYoY_z"] = (dd2["vYoY"] - dd2["vYoY"].mean()) / dd2["vYoY"].std()
dd2["split_z"] = (dd2["woba_split"] - dd2["woba_split"].mean()) / dd2["woba_split"].std()
dd2["interact"] = dd2["vYoY_z"] * dd2["split_z"]
ri, pi, ni = partial_r(dd2, "interact", Y, BASE_V + ["woba_split"])
L("")
L(f"Explicit vYoY x woba_split interaction term, partial-r over [level,fp,vYoY,woba_split]: r={ri:+.3f} p={pi:.3f} n={ni}")

# ----------------------------------------------------------------------
# 5. DOWNSIDE: bust-rate gap (bust = bottom tercile ros within cell-year)
# ----------------------------------------------------------------------
L("")
L("## Downside: bust-rate gap (bust = bottom-tercile ros_fp_per_start)")
dd3 = dd.copy()
dd3["bust"] = dd3.groupby(["year", "split_day"])[Y].transform(
    lambda v: v <= v.quantile(0.333)).astype(int)
for c in ["woba_split", "vYoY"]:
    s = dd3.dropna(subset=[c])
    hi = s[s[c] >= s[c].quantile(0.667)]   # worst (high split / high vYoY=less decline)
    lo = s[s[c] <= s[c].quantile(0.333)]
    L(f"{c}: bust-rate top-tercile={hi.bust.mean():.3f}  bottom-tercile={lo.bust.mean():.3f}  "
      f"gap={hi.bust.mean()-lo.bust.mean():+.3f}")

with open("data/research/validation_runs/velo_platoon_2026-06-13.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("\nWROTE markdown body (header added separately)")

# stash key numbers for verdict
import json
print(json.dumps({k: [round(x,3) if isinstance(x,float) and not np.isnan(x) else None for x in v]
                  for k,v in results.items()}, indent=0))

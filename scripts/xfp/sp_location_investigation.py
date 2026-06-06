"""
sp_location_investigation.py — deeper look at Location+ x Stuff+ for SP fantasy.

Three parts:
  A. Identify the "command-artist" type (high Location+, low Stuff+) and cross-
     reference with our archetype model (CONTROL/WALK_AVOID grades, archetype label).
  B. Does Location+ MODULATE how stuff converts to FP? (the Eury Perez hypothesis:
     elite stuff + terrible location underperforms its stuff-implied projection.)
  C. Disciplined combinatorial search over location-family features + interactions,
     scored by cross-year lift with Bonferroni context (NOT a free-for-all sweep).

All prediction uses as-of-June-6 FG metrics -> RoS FP/start (no leakage). Archetype
grades (full-season) are used for TYPE cross-reference only, never as predictors.
"""
from __future__ import annotations
import sys, itertools
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.linear_model import Ridge, LinearRegression
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_fg_pitch_modeling_inseason import load as load_hist  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
BASE = ["pre_fp", "k_pct", "bb_pct", "swstr_pct", "siera", "stuff_plus"]
TRAIN, HOLD = [2021, 2022, 2023], [2024, 2025]


def with_archetype(df):
    a = pd.read_csv(ROOT / "data" / "research" / "sp_ratings_master.csv")
    a = a.rename(columns={"pitcher": "mlb_id"})
    keep = ["mlb_id", "year", "archetype", "STUFF", "CONTROL", "MOVEMENT",
            "WALK_AVOID", "STRIKE_THROWING"]
    return df.merge(a[keep], on=["mlb_id", "year"], how="left")


def cross_year_r(tr, te, feats):
    s_tr, s_te = tr[feats + ["ros_fp"]].dropna(), te[feats + ["ros_fp"]].dropna()
    sc = StandardScaler().fit(s_tr[feats])
    m = Ridge(alpha=1.0).fit(sc.transform(s_tr[feats]), s_tr["ros_fp"])
    return pearsonr(m.predict(sc.transform(s_te[feats])), s_te["ros_fp"])[0], len(s_te)


def partial_r(df, x, y, ctrl):
    sub = df[[x, y] + ctrl].dropna()
    if len(sub) < 20: return np.nan, len(sub)
    Z = sub[ctrl].values
    rx = sub[x] - LinearRegression().fit(Z, sub[x]).predict(Z)
    ry = sub[y] - LinearRegression().fit(Z, sub[y]).predict(Z)
    return pearsonr(rx, ry)[0], len(sub)


def part_a(df):
    print("=" * 78)
    print("PART A — Command-artist type (high Location+, low Stuff+)")
    print("=" * 78)
    # tercile grid: mean ros_fp by stuff x location tercile
    df = df.copy()
    df["stuff_t"] = pd.qcut(df["stuff_plus"], 3, labels=["loStuff", "midStuff", "hiStuff"])
    df["loc_t"] = pd.qcut(df["location_plus"], 3, labels=["loLoc", "midLoc", "hiLoc"])
    grid = df.pivot_table("ros_fp", "stuff_t", "loc_t", aggfunc="mean", observed=True).round(1)
    cnt = df.pivot_table("ros_fp", "stuff_t", "loc_t", aggfunc="size", observed=True)
    print("\nMean RoS FP/start by Stuff x Location tercile (n in parens):")
    for si in grid.index:
        row = "  " + f"{si:<9}"
        for lj in grid.columns:
            row += f"{grid.loc[si,lj]:>6.1f}[{cnt.loc[si,lj]:>3}]"
        print(row)
    print("  cols: " + "  ".join(grid.columns))

    # FG location_plus vs our archetype command grades
    print("\nDoes FG Location+ measure our CONTROL? correlations:")
    for g in ["CONTROL", "WALK_AVOID", "STRIKE_THROWING", "STUFF"]:
        sub = df[["location_plus", g]].dropna()
        if len(sub) > 20:
            print(f"  location_plus vs {g:<16} r={pearsonr(sub['location_plus'],sub[g])[0]:+.3f} (n={len(sub)})")
    sub = df[["stuff_plus", "STUFF"]].dropna()
    print(f"  stuff_plus    vs STUFF            r={pearsonr(sub['stuff_plus'],sub['STUFF'])[0]:+.3f} (n={len(sub)})")

    # actual command artists who SUCCEEDED
    ca = df[(df["location_plus"] >= df["location_plus"].quantile(.80)) &
            (df["stuff_plus"] <= df["stuff_plus"].quantile(.40)) &
            (df["ros_fp"] >= 12)].sort_values("ros_fp", ascending=False)
    print(f"\nCommand artists who succeeded (Loc+ top20%, Stuff+ bot40%, RoS FP>=12): n={len(ca)}")
    print(f"  {'pitcher':<20}{'yr':>5}{'Stuff+':>8}{'Loc+':>7}{'rosFP':>7}{'CTRL':>6}  archetype")
    for _, r in ca.head(15).iterrows():
        nm = str(r.get('archetype', ''))
        print(f"  {str(r['player_name_fg'])[:19]:<20}{int(r['year']):>5}{r['stuff_plus']:>8.0f}"
              f"{r['location_plus']:>7.0f}{r['ros_fp']:>7.1f}{r.get('CONTROL',np.nan):>6.0f}  {nm}")


def part_b(df):
    print("\n" + "=" * 78)
    print("PART B — Does Location+ modulate stuff->FP conversion? (Perez hypothesis)")
    print("=" * 78)
    # location_plus already redundant with bb_pct?
    sub = df[["location_plus", "bb_pct"]].dropna()
    print(f"\ncorr(location_plus, bb_pct) = {pearsonr(sub['location_plus'],sub['bb_pct'])[0]:+.3f}"
          f"  (if strongly negative, location is already in baseline via BB%)")

    # partial r of location overall and WITHIN high-stuff
    r_all, n_all = partial_r(df, "location_plus", "ros_fp", BASE[:-1])  # control everything but stuff? no:
    r_all, n_all = partial_r(df, "location_plus", "ros_fp", BASE)       # control full baseline incl stuff
    print(f"\nlocation_plus partial r vs RoS FP | full baseline:  {r_all:+.3f} (n={n_all})")
    for lo, hi, lbl in [(110, 999, "hiStuff (>=110)"), (105, 110, "midStuff 105-110"),
                        (0, 105, "loStuff (<105)")]:
        d2 = df[(df["stuff_plus"] >= lo) & (df["stuff_plus"] < hi)]
        r, n = partial_r(d2, "location_plus", "ros_fp", ["pre_fp", "k_pct", "bb_pct", "swstr_pct", "siera"])
        rr, _ = (pearsonr(*d2[["location_plus","ros_fp"]].dropna().values.T) if len(d2.dropna(subset=["location_plus","ros_fp"]))>20 else (np.nan,0))
        print(f"  within {lbl:<18} partial r={r:+.3f}  raw r={rr:+.3f}  (n={n})")

    # Perez comps: high stuff, low location historically -> did they bounce?
    comps = df[(df["stuff_plus"] >= 112) & (df["location_plus"] <= 97)].copy()
    print(f"\nPerez-like comps (Stuff+>=112 & Loc+<=97), did stuff win or location drag? n={len(comps)}")
    print(f"  mean pre_fp={comps['pre_fp'].mean():.1f} -> mean RoS FP={comps['ros_fp'].mean():.1f} "
          f"(delta {comps['ros_fp'].mean()-comps['pre_fp'].mean():+.1f})")
    print(f"  vs high-stuff GOOD-location (Stuff+>=112 & Loc+>=103):")
    good = df[(df["stuff_plus"] >= 112) & (df["location_plus"] >= 103)]
    print(f"  mean pre_fp={good['pre_fp'].mean():.1f} -> mean RoS FP={good['ros_fp'].mean():.1f} "
          f"(delta {good['ros_fp'].mean()-good['pre_fp'].mean():+.1f}, n={len(good)})")
    print(f"  {'pitcher':<20}{'yr':>5}{'Stuff+':>8}{'Loc+':>7}{'preFP':>7}{'rosFP':>7}")
    for _, r in comps.sort_values("ros_fp").head(12).iterrows():
        print(f"  {str(r['player_name_fg'])[:19]:<20}{int(r['year']):>5}{r['stuff_plus']:>8.0f}"
              f"{r['location_plus']:>7.0f}{r['pre_fp']:>7.1f}{r['ros_fp']:>7.1f}")


def part_c(df):
    print("\n" + "=" * 78)
    print("PART C — Combinatorial search (cross-year lift over validated baseline)")
    print("=" * 78)
    d = df.copy()
    sc_s = (d["stuff_plus"] - d["stuff_plus"].mean())
    sc_l = (d["location_plus"] - d["location_plus"].mean())
    d["inter_sl"] = sc_s * sc_l
    d["ratio_sl"] = d["stuff_plus"] / d["location_plus"]
    d["deficit_sl"] = d["stuff_plus"] - d["location_plus"]
    d["loc_hi"] = d["location_plus"] * (d["stuff_plus"] >= 110).astype(int)
    d["loc_sq"] = (d["location_plus"] - d["location_plus"].mean()) ** 2
    cand = ["location_plus", "pitching_plus", "pb_command", "pb_stuff",
            "inter_sl", "ratio_sl", "deficit_sl", "loc_hi", "loc_sq"]
    tr, te = d[d.year.isin(TRAIN)], d[d.year.isin(HOLD)]
    base_r, nte = cross_year_r(tr, te, BASE)
    print(f"\nbaseline {BASE}\n  cross-year r = {base_r:.4f} (n_test={nte})")
    # single additions
    singles = []
    for c in cand:
        r, _ = cross_year_r(tr, te, BASE + [c])
        singles.append((c, r - base_r))
    # pairwise additions
    pairs = []
    for a, b in itertools.combinations(cand, 2):
        try:
            r, _ = cross_year_r(tr, te, BASE + [a, b])
            pairs.append((f"{a}+{b}", r - base_r))
        except Exception:
            pass
    n_tests = len(singles) + len(pairs)
    print(f"\nTests run: {len(singles)} singles + {len(pairs)} pairs = {n_tests}. "
          f"Bar = +0.005 cross-year gain; Bonferroni context alpha/{n_tests}.")
    print("\nSingle additions (gain vs baseline):")
    for c, g in sorted(singles, key=lambda x: -x[1]):
        print(f"  +{c:<14} {g:+.4f}  {'PASS' if g>=0.005 else ''}")
    print("\nTop 8 pairwise additions:")
    for c, g in sorted(pairs, key=lambda x: -x[1])[:8]:
        print(f"  +{c:<28} {g:+.4f}  {'PASS' if g>=0.005 else ''}")


def main():
    df = with_archetype(load_hist())
    print(f"Loaded {len(df)} SP-seasons (2021-25); archetype matched "
          f"{df['CONTROL'].notna().sum()}.\n")
    part_a(df)
    part_b(df)
    part_c(df)


if __name__ == "__main__":
    main()

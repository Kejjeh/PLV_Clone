"""
validate_fg_pitch_modeling_inseason.py
Pre-registered: data/research/validation_runs/fg_pitch_modeling_inseason_2026-06-06.md

In-season-leading validation of FanGraphs pitch-modeling metrics as predictors
of rest-of-season BrownU SP FP/start.

  metric measured as-of June 6  ->  FP/start over June 7 .. season end

Reports, per metric:
  - descriptive raw r (pooled) with RoS FP/start
  - Tier-1 partial r controlling for pre-cutoff FP/start  (the breakout signal)
  - Tier-2 partial r controlling for pre-FP + FG rate stats (rp3-proxy / Rule 9)
  - per-year Tier-2 partial r (sign consistency, 4-of-5 bar)
  - holdout Tier-2 partial r on 2024 & 2025
  - cross-year Ridge lift: r(Tier2) vs r(Tier2+metric), train 21-23 -> test 24-25
  - Bonferroni: bar = 0.05 / 5 candidates = 0.01
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
FG = ROOT / "data" / "research" / "fg_asof"

YEARS = [2021, 2022, 2023, 2024, 2025]
TRAIN = [2021, 2022, 2023]
HOLD = [2024, 2025]
METRICS = ["stuff_plus", "location_plus", "pitching_plus", "pb_stuff", "pb_command"]
RATE = ["k_pct", "bb_pct", "swstr_pct", "siera"]  # csw_pct empty on date-ranged pulls
N_TESTS = len(METRICS)
BONF = 0.05 / N_TESTS


def real_ip(ip):
    ip = pd.to_numeric(ip, errors="coerce")
    w = np.floor(ip)
    frac = np.round((ip - w) * 10)
    return (w * 3 + frac) / 3


def brownu_fp_per_start(d):
    rip = real_ip(d["ip"])
    for c in ["so", "h", "er", "bb", "hbp", "gs"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    fp = d["so"] + rip * 3.3 - d["h"] - 2 * d["er"] - d["bb"] - d["hbp"].fillna(0)
    return fp / d["gs"]


def load():
    frames = []
    for yr in YEARS:
        pre = pd.read_csv(FG / f"fg_pit_{yr}_pre.csv")
        ros = pd.read_csv(FG / f"fg_pit_{yr}_ros.csv")
        for d in (pre, ros):
            d["gs"] = pd.to_numeric(d["gs"], errors="coerce")
            d["g"] = pd.to_numeric(d["g"], errors="coerce")
        pre = pre[(pre["gs"] >= 5) & (pre["gs"] / pre["g"] >= 0.7)].copy()
        ros = ros[(ros["gs"] >= 5) & (ros["gs"] / ros["g"] >= 0.7)].copy()
        pre["pre_fp"] = brownu_fp_per_start(pre)
        ros["ros_fp"] = brownu_fp_per_start(ros)
        for c in METRICS + RATE:
            pre[c] = pd.to_numeric(pre[c], errors="coerce")
        keep_pre = ["mlb_id", "player_name_fg", "pre_fp"] + METRICS + RATE
        m = pre[keep_pre].merge(ros[["mlb_id", "ros_fp"]], on="mlb_id")
        m["year"] = yr
        frames.append(m)
    return pd.concat(frames, ignore_index=True)


def partial_r(df, x, y, controls):
    sub = df[[x, y] + controls].dropna()
    if len(sub) < 20:
        return np.nan, np.nan, len(sub)
    Z = sub[controls].values
    rx = sub[x].values - LinearRegression().fit(Z, sub[x]).predict(Z)
    ry = sub[y].values - LinearRegression().fit(Z, sub[y]).predict(Z)
    r, p = pearsonr(rx, ry)
    return r, p, len(sub)


def cross_year_r(train_df, test_df, feats):
    sub_tr = train_df[feats + ["ros_fp"]].dropna()
    sub_te = test_df[feats + ["ros_fp"]].dropna()
    sc = StandardScaler().fit(sub_tr[feats])
    Xtr, Xte = sc.transform(sub_tr[feats]), sc.transform(sub_te[feats])
    mdl = Ridge(alpha=1.0).fit(Xtr, sub_tr["ros_fp"])
    pred = mdl.predict(Xte)
    return pearsonr(pred, sub_te["ros_fp"])[0], len(sub_te)


def main():
    df = load()
    print(f"\nPooled n={len(df)}  | per-year: " +
          ", ".join(f"{y}:{(df.year==y).sum()}" for y in YEARS))
    print(f"RoS FP/start: mean={df.ros_fp.mean():.2f} sd={df.ros_fp.std():.2f}")
    print(f"Bonferroni bar: p < {BONF:.4f} (5 candidates)\n")

    print("=" * 92)
    print(f"{'metric':<15}{'raw_r':>8}{'T1_pr':>8}{'T1_p':>9}{'T2_pr':>8}{'T2_p':>9}{'bonf':>7}")
    print("-" * 92)
    results = {}
    for mtr in METRICS:
        raw = pearsonr(*df[[mtr, "ros_fp"]].dropna().values.T)[0]
        t1, t1p, _ = partial_r(df, mtr, "ros_fp", ["pre_fp"])
        t2, t2p, _ = partial_r(df, mtr, "ros_fp", ["pre_fp"] + RATE)
        passed = "PASS" if (abs(t2) >= 0.10 and t2p < BONF) else "no"
        results[mtr] = dict(raw=raw, t1=t1, t1p=t1p, t2=t2, t2p=t2p)
        print(f"{mtr:<15}{raw:>8.3f}{t1:>8.3f}{t1p:>9.4f}{t2:>8.3f}{t2p:>9.4f}{passed:>7}")
    print("=" * 92)
    print("raw_r = descriptive corr w/ RoS FP | T1 = partial controlling pre-FP")
    print("T2 = partial controlling pre-FP + rate stats (rp3-proxy / Rule 9 spirit)\n")

    # per-year Tier-2 sign consistency
    print("PER-YEAR Tier-2 partial r (sign consistency, bar 4-of-5):")
    print(f"{'metric':<15}" + "".join(f"{y:>9}" for y in YEARS) + f"{'signs':>10}")
    for mtr in METRICS:
        row, signs = [], 0
        base = results[mtr]["t2"]
        for y in YEARS:
            r, _, n = partial_r(df[df.year == y], mtr, "ros_fp", ["pre_fp"] + RATE)
            row.append(r)
            if not np.isnan(r) and np.sign(r) == np.sign(base):
                signs += 1
        print(f"{mtr:<15}" + "".join(f"{r:>9.3f}" for r in row) +
              f"{f'{signs}/5':>10}")
    print()

    # holdout Tier-2 partial r
    print("HOLDOUT Tier-2 partial r (bar >= 0.05 same sign):")
    for mtr in METRICS:
        r24, _, n24 = partial_r(df[df.year == 2024], mtr, "ros_fp", ["pre_fp"] + RATE)
        r25, _, n25 = partial_r(df[df.year == 2025], mtr, "ros_fp", ["pre_fp"] + RATE)
        print(f"  {mtr:<15} 2024: {r24:+.3f} (n={n24})   2025: {r25:+.3f} (n={n25})")
    print()

    # cross-year Ridge lift (headline Rule-9 +0.005 bar)
    tr, te = df[df.year.isin(TRAIN)], df[df.year.isin(HOLD)]
    base_r, nte = cross_year_r(tr, te, ["pre_fp"] + RATE)
    print(f"CROSS-YEAR Ridge r (train {TRAIN} -> test {HOLD}, n_test={nte}):")
    print(f"  baseline [pre_fp + rate stats]           r = {base_r:.4f}")
    for mtr in METRICS:
        r, _ = cross_year_r(tr, te, ["pre_fp"] + RATE + [mtr])
        print(f"  + {mtr:<18} r = {r:.4f}   gain = {r-base_r:+.4f}"
              f"  {'PASS' if r-base_r >= 0.005 else ''}")
    # all five together
    r_all, _ = cross_year_r(tr, te, ["pre_fp"] + RATE + METRICS)
    print(f"  + ALL 5 metrics            r = {r_all:.4f}   gain = {r_all-base_r:+.4f}")
    print()


if __name__ == "__main__":
    main()

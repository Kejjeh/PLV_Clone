"""
validate_fg_convergence.py — Rule 8 convergence curve for the FG pitch-modeling
in-season signal. Re-computes Tier-2 partial r for the stuff metrics at multiple
in-season cutoffs, confirming the signal is stable across the season (not an
artifact of the June-6 cutoff).

Cutoffs: 05-16 (early), 06-06 (primary, unsuffixed files), 06-27 (late).
A metric is convergence-stable if its partial r keeps the same sign and similar
magnitude across all available cutoffs.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.linear_model import LinearRegression

ROOT = Path(__file__).resolve().parents[2]
FG = ROOT / "data" / "research" / "fg_asof"
YEARS = [2021, 2022, 2023, 2024, 2025]
METRICS = ["stuff_plus", "location_plus", "pitching_plus", "pb_stuff", "pb_command"]
RATE = ["k_pct", "bb_pct", "swstr_pct", "siera"]
CUTOFFS = ["05-16", "06-06", "06-27"]


def real_ip(ip):
    ip = pd.to_numeric(ip, errors="coerce"); w = np.floor(ip)
    return (w * 3 + np.round((ip - w) * 10)) / 3


def fp_per_start(d):
    rip = real_ip(d["ip"])
    for c in ["so", "h", "er", "bb", "hbp", "gs"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return (d["so"] + rip * 3.3 - d["h"] - 2 * d["er"] - d["bb"] - d["hbp"].fillna(0)) / d["gs"]


def paths(yr, label, cut):
    # primary June-6 files are unsuffixed; convergence cutoffs are suffixed
    if cut == "06-06":
        return FG / f"fg_pit_{yr}_{label}.csv"
    return FG / f"fg_pit_{yr}_{label}_{cut}.csv"


def load_cutoff(cut):
    frames = []
    for yr in YEARS:
        pp, rp = paths(yr, "pre", cut), paths(yr, "ros", cut)
        if not (pp.exists() and rp.exists()):
            return None
        pre, ros = pd.read_csv(pp), pd.read_csv(rp)
        for d in (pre, ros):
            d["gs"] = pd.to_numeric(d["gs"], errors="coerce")
            d["g"] = pd.to_numeric(d["g"], errors="coerce")
        pre = pre[(pre["gs"] >= 5) & (pre["gs"] / pre["g"] >= 0.7)].copy()
        ros = ros[(ros["gs"] >= 5) & (ros["gs"] / ros["g"] >= 0.7)].copy()
        pre["pre_fp"] = fp_per_start(pre); ros["ros_fp"] = fp_per_start(ros)
        for c in METRICS + RATE:
            pre[c] = pd.to_numeric(pre[c], errors="coerce")
        m = pre[["mlb_id", "pre_fp"] + METRICS + RATE].merge(ros[["mlb_id", "ros_fp"]], on="mlb_id")
        frames.append(m)
    return pd.concat(frames, ignore_index=True)


def partial_r(df, x, y, controls):
    sub = df[[x, y] + controls].dropna()
    if len(sub) < 20:
        return np.nan, len(sub)
    Z = sub[controls].values
    rx = sub[x].values - LinearRegression().fit(Z, sub[x]).predict(Z)
    ry = sub[y].values - LinearRegression().fit(Z, sub[y]).predict(Z)
    return pearsonr(rx, ry)[0], len(sub)


def main():
    print("CONVERGENCE CURVE — Tier-2 partial r (controls: pre_fp + rate stats)\n")
    avail = []
    data = {}
    for cut in CUTOFFS:
        d = load_cutoff(cut)
        if d is not None:
            data[cut] = d; avail.append(cut)
    if not avail:
        print("No cutoff data found yet."); return
    hdr = f"{'metric':<15}" + "".join(f"{c+f' (n={len(data[c])})':>16}" for c in avail)
    print(hdr); print("-" * len(hdr))
    for mtr in METRICS:
        row = f"{mtr:<15}"
        for cut in avail:
            r, n = partial_r(data[cut], mtr, "ros_fp", ["pre_fp"] + RATE)
            row += f"{r:>16.3f}"
        print(row)
    print("\nStable = same sign + similar magnitude across all available cutoffs.")


if __name__ == "__main__":
    main()

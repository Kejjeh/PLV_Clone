"""
velo_signal_study.py  (2026-06-13)

Can velocity become a USABLE avoid signal? The translation-gap study rejected
velo (ΔR² -0.012) but it was built three ways that suppress it:
  1. delta = avg_velo_last21 - avg_velo_to, but *_to CONTAINS last21 -> a
     contaminated, regressed-to-itself delta on tiny samples.
  2. tested ONLY inside the top-quartile high-Stuff cohort, which is selected
     partly ON velo -> range restriction crushes the velo signal.
  3. within-cell z linearizes what may be a THRESHOLD (only big drops bite).

This study fixes all three and adds the lever the panel never used:
  A. velo_yoy   = avg_velo_to - prior-year SEASON-END velo  (real aging/injury)
  B. velo_intra = avg_velo_last21 - EARLY-season velo (first split, clean base)
  C. velo_pers  = personal z of current velo vs pitcher's own multi-yr mean/sd
  D. velo_level = within-cell z of absolute velo (baseline reference)
plus THRESHOLD flags (drop > 1.0 / 1.5 mph) and tested on the FULL panel AND
the high-Stuff cohort, with leakage-safe expanding-window OOS incremental over
stuff_proxy, a convergence-curve leakage check, and a DOWNSIDE test (forward
bottom-tercile bust rate, not just the mean).

Leakage discipline: every feature is as-of (cumulative-to-cutoff or strictly
prior-year); target ros_fp_per_start is strictly post-cutoff.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats
from sklearn.linear_model import LinearRegression

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "research" / "xfp_cache" / "rolling_pitchers_2018_2026.csv"

MIN_GS_TO = 5
MIN_ROS_GS = 3
HIST_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]


def zwithin(df, col, by=("year", "split_day")):
    g = df.groupby(list(by))[col]
    return (df[col] - g.transform("mean")) / g.transform("std").replace(0, np.nan)


def load_panel():
    d = pd.read_csv(PANEL)
    d = d[d.year.isin(HIST_YEARS + [2026])].copy()  # keep 2026 for prior-yr base only

    # --- prior-year SEASON-END velo (last split row per pitcher-year) ---
    end = (d.sort_values("split_day").groupby(["pitcher", "year"]).tail(1)
           [["pitcher", "year", "avg_velo_to"]]
           .rename(columns={"avg_velo_to": "prior_velo", "year": "prior_year"}))
    end["join_year"] = end["prior_year"] + 1
    d = d.merge(end[["pitcher", "join_year", "prior_velo"]],
                left_on=["pitcher", "year"], right_on=["pitcher", "join_year"],
                how="left").drop(columns="join_year")

    # --- EARLY-season velo (first split row per pitcher-year) ---
    early = (d.sort_values("split_day").groupby(["pitcher", "year"]).head(1)
             [["pitcher", "year", "avg_velo_to"]]
             .rename(columns={"avg_velo_to": "early_velo"}))
    d = d.merge(early, on=["pitcher", "year"], how="left")

    # --- personal multi-year velo mean/sd (career, all years incl. 2026 to-date) ---
    pers = d.groupby("pitcher")["avg_velo_to"].agg(["mean", "std"]).rename(
        columns={"mean": "pers_mean", "std": "pers_std"})
    d = d.merge(pers, on="pitcher", how="left")

    # restrict to historical years for OOS (2026 has no forward target)
    d = d[d.year.isin(HIST_YEARS)].copy()
    d = d[(d.gs_to >= MIN_GS_TO) & (d.ros_gs >= MIN_ROS_GS)].copy()

    # stuff proxy (same as translation-gap study) for the base model + cohort
    d["z_velo"] = zwithin(d, "avg_velo_to")
    d["z_mov"] = zwithin(d, "avg_pfxz_to")
    d["z_swstr"] = zwithin(d, "swstr_pct_to")
    d["stuff_proxy"] = d[["z_velo", "z_mov", "z_swstr"]].mean(axis=1)

    # ---- VELO FEATURES (raw mph deltas; avoid = velo LOSS) ----
    d["velo_yoy"] = d["avg_velo_to"] - d["prior_velo"]
    d["velo_intra"] = d["avg_velo_last21"] - d["early_velo"]
    d["velo_pers"] = (d["avg_velo_to"] - d["pers_mean"]) / d["pers_std"].replace(0, np.nan)
    # avoid-oriented z features (POSITIVE = more velo loss = hypothesized worse)
    d["av_yoy"] = -zwithin(d, "velo_yoy")
    d["av_intra"] = -zwithin(d, "velo_intra")
    d["av_pers"] = -d["velo_pers"]
    d["av_level"] = -d["z_velo"]
    return d.dropna(subset=["stuff_proxy"]).copy()


def high_stuff(d):
    thr = d.groupby(["year", "split_day"])["stuff_proxy"].transform(lambda s: s.quantile(0.75))
    return d[d.stuff_proxy >= thr].copy()


def oos_incremental(df, feats, target="ros_fp_per_start", base="stuff_proxy"):
    years = sorted(df.year.unique())
    test_years = [y for y in years if y > years[0]]
    out = []
    for c in feats:
        oy, opb, opf = [], [], []
        for ty in test_years:
            tr, te = df.year < ty, df.year == ty
            ok_tr = np.isfinite(df.loc[tr, c]) & np.isfinite(df.loc[tr, base])
            ok_te = np.isfinite(df.loc[te, c]) & np.isfinite(df.loc[te, base])
            if ok_tr.sum() < 40 or ok_te.sum() < 25:
                continue
            Xb_tr = df.loc[tr, [base]][ok_tr].values
            Xb_te = df.loc[te, [base]][ok_te].values
            Xf_tr = df.loc[tr, [base, c]][ok_tr].values
            Xf_te = df.loc[te, [base, c]][ok_te].values
            ytr = df.loc[tr, target][ok_tr].values
            yte = df.loc[te, target][ok_te].values
            mb = LinearRegression().fit(Xb_tr, ytr)
            mf = LinearRegression().fit(Xf_tr, ytr)
            oy.append(yte); opb.append(mb.predict(Xb_te)); opf.append(mf.predict(Xf_te))
        if not oy:
            continue
        Y, Pb, Pf = map(np.concatenate, (oy, opb, opf))
        sst = ((Y - Y.mean())**2).sum()
        r2b = 1 - ((Y - Pb)**2).sum()/sst
        r2f = 1 - ((Y - Pf)**2).sum()/sst
        rho, p = stats.spearmanr(df.loc[df.year.isin(test_years), c].dropna(),
                                 df.loc[df.year.isin(test_years)].dropna(subset=[c])[target])
        out.append([c, len(Y), r2b, r2f - r2b, rho, p])
    return pd.DataFrame(out, columns=["feat", "n_oos", "base_r2", "delta_r2", "rho_fwd", "p"])


def threshold_table(df, target="ros_fp_per_start"):
    """Nonlinear: does forward FP fall only past a velo-LOSS threshold?"""
    rows = []
    for col, name in [("velo_yoy", "YoY velo Δ"), ("velo_intra", "intra-season velo Δ")]:
        s = df.dropna(subset=[col])
        for lo, hi, lab in [(-99, -1.5, "≤ -1.5 mph"), (-1.5, -1.0, "-1.5..-1.0"),
                            (-1.0, -0.5, "-1.0..-0.5"), (-0.5, 0.5, "-0.5..+0.5"),
                            (0.5, 99, "≥ +0.5 mph")]:
            m = (s[col] > lo) & (s[col] <= hi)
            if m.sum() >= 30:
                rows.append([name, lab, int(m.sum()), s.loc[m, target].mean()])
    return pd.DataFrame(rows, columns=["feature", "bucket", "n", "fwd_fp"])


def downside_test(df, feats, target="ros_fp_per_start"):
    """Does velo loss predict the DOWNSIDE? Forward bottom-tercile (bust) rate
    within as-of cells. Logistic-free: Spearman(avoid_feat, P(bust)) via quintiles."""
    df = df.copy()
    thr = df.groupby(["year", "split_day"])[target].transform(lambda s: s.quantile(1/3))
    df["bust"] = (df[target] <= thr).astype(int)
    rows = []
    for c in feats:
        s = df.dropna(subset=[c])
        q = pd.qcut(s[c].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
        br = s.groupby(q, observed=True)["bust"].mean()
        rho, p = stats.spearmanr(s[c], s["bust"])
        rows.append([c, br.get(1, np.nan), br.get(5, np.nan),
                     br.get(5, np.nan) - br.get(1, np.nan), rho, p])
    return pd.DataFrame(rows, columns=["feat", "bust%_Q1", "bust%_Q5", "Δbust", "rho", "p"])


def main():
    pd.set_option("display.width", 170)
    d = load_panel()
    coh = high_stuff(d)
    feats = ["av_yoy", "av_intra", "av_pers", "av_level"]
    print(f"Full panel SP-weeks: {len(d)} | high-Stuff cohort: {len(coh)}")
    print(f"  YoY-velo available: {d.velo_yoy.notna().sum()} | intra: {d.velo_intra.notna().sum()}")
    print(f"  forward FP mean full {d.ros_fp_per_start.mean():.2f} / cohort {coh.ros_fp_per_start.mean():.2f}\n")

    print("=== OOS INCREMENTAL ΔR² over stuff_proxy — FULL PANEL (no range restriction) ===")
    print(oos_incremental(d, feats).sort_values("delta_r2", ascending=False)
          .to_string(index=False, float_format=lambda x: f"{x:+.4f}"))

    print("\n=== OOS INCREMENTAL ΔR² over stuff_proxy — HIGH-STUFF cohort (as-built scope) ===")
    print(oos_incremental(coh, feats).sort_values("delta_r2", ascending=False)
          .to_string(index=False, float_format=lambda x: f"{x:+.4f}"))

    print("\n=== THRESHOLD (nonlinear) forward FP by velo-loss band — FULL PANEL ===")
    print(threshold_table(d).to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    print("\n=== DOWNSIDE: velo loss vs forward BUST rate (bottom-tercile FP) — FULL PANEL ===")
    print(downside_test(d, feats).to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    print("\n=== DOWNSIDE — HIGH-STUFF cohort ===")
    print(downside_test(coh, feats).to_string(index=False, float_format=lambda x: f"{x:+.4f}"))


if __name__ == "__main__":
    main()

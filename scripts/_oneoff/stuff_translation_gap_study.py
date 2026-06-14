"""
stuff_translation_gap_study.py  (2026-06-13)

Leakage-safe OOS pitcher-week study: among HIGH-Stuff STARTING pitchers,
which pre-week indicators predict POOR forward BrownU FP/start?

FRAME: Stuff+ says "are the pitch traits good?" not "does he turn them into
outs/Ks/IP/value?". We build a Stuff Translation Gap (residual of skill-
translation metrics on the stuff measure) and OOS-test the 6 SP avoid buckets.
The strongest avoid signal should be DISAGREEMENT between stuff grade and the
actual skill-translation metric.

Substrate: data/research/xfp_cache/rolling_pitchers_2018_2026.csv
  - per-(pitcher, split_day) panel, all *_to cols cumulative-to-cutoff (leakage-safe)
  - FORWARD TARGET = ros_fp_per_start over ros_gs starts
Stuff measure (cohort selector): Statcast stuff-proxy from leakage-safe *_to cols
  (avg_velo_to + movement avg_pfxz_to + swstr_pct_to), built WITHIN each
  (year,split_day) cell so it is a pure as-of cross-sectional grade.
Real FG Stuff+ join used as a cross-check at the matching cutoffs.

RIGOR: expanding-window OOS (train years < test year), separate high-Stuff
cohort, convergence-curve leakage check across split_days, INCREMENTAL OOS lift
of each bucket OVER stuff-proxy alone (per lens_value_add_2026-06-11).
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "research" / "xfp_cache" / "rolling_pitchers_2018_2026.csv"
FG = ROOT / "data" / "research" / "fg_asof"

# SP cohort gate
MIN_GS_TO = 5      # enough starts to-cutoff to grade
MIN_ROS_GS = 3     # enough forward starts for a stable target
HIST_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]  # 2026 partial -> exclude from OOS target


def zwithin(df, col, by=("year", "split_day")):
    """Cross-sectional z-score within each as-of cell (pure as-of, no leakage)."""
    g = df.groupby(list(by))[col]
    return (df[col] - g.transform("mean")) / g.transform("std").replace(0, np.nan)


def resid_within(df, ycol, xcols, by=("year", "split_day")):
    """Residual of ycol on xcols, fit WITHIN each as-of cell (OLS, intercept).
    Negative residual on a translation metric = stuff not translating."""
    out = pd.Series(np.nan, index=df.index)
    for _, idx in df.groupby(list(by)).groups.items():
        sub = df.loc[idx]
        X = sub[xcols].values
        y = sub[ycol].values
        ok = np.isfinite(y) & np.all(np.isfinite(X), axis=1)
        if ok.sum() < 8:
            continue
        Xb = np.column_stack([np.ones(ok.sum()), X[ok]])
        beta, *_ = np.linalg.lstsq(Xb, y[ok], rcond=None)
        pred = Xb @ beta
        out.loc[sub.index[ok]] = y[ok] - pred
    return out


def load_panel():
    d = pd.read_csv(PANEL)
    d = d[d.year.isin(HIST_YEARS)].copy()
    d = d[(d.gs_to >= MIN_GS_TO) & (d.ros_gs >= MIN_ROS_GS)].copy()
    # --- Statcast stuff-proxy (as-of, within-cell z of velo + movement + swstr) ---
    d["z_velo"] = zwithin(d, "avg_velo_to")
    d["z_mov"] = zwithin(d, "avg_pfxz_to")        # vertical movement magnitude
    d["z_swstr"] = zwithin(d, "swstr_pct_to")
    d["stuff_proxy"] = d[["z_velo", "z_mov", "z_swstr"]].mean(axis=1)
    # --- Stuff Translation Gaps (residuals of translation metrics on stuff_proxy) ---
    # within each as-of cell so the gap is cross-sectional and leakage-free
    d["kbb_pct_to"] = d["k_pct_to"] - d["bb_pct_to"]
    d["gap_csw"] = resid_within(d, "c_plus_swstr_to", ["stuff_proxy"])   # CSW translation
    d["gap_swstr"] = resid_within(d, "swstr_pct_to", ["stuff_proxy"])    # whiff translation
    d["gap_kbb"] = resid_within(d, "kbb_pct_to", ["stuff_proxy"])        # K-BB translation
    return d.dropna(subset=["stuff_proxy"]).copy()


def high_stuff_cohort(d):
    """Top-quartile stuff_proxy WITHIN each as-of cell."""
    thr = d.groupby(["year", "split_day"])["stuff_proxy"].transform(
        lambda s: s.quantile(0.75))
    return d[d.stuff_proxy >= thr].copy()


# ---- The 6 SP avoid buckets: each a pre-week, as-of feature (higher = more "avoid") ----
# Sign convention: we define each so that POSITIVE => hypothesized WORSE forward FP.
def build_buckets(d):
    b = {}
    # (a) stuff-without-command: high BB%, low zone% -> walks/no strikes
    b["a_no_command"] = zwithin(d, "bb_pct_to") - zwithin(d, "zone_pct_to")
    # (b) stuff-without-whiffs: negative CSW/swstr/K-BB translation residual
    #     avoid = NEGATIVE residual, so flip sign: -gap
    b["b_no_whiffs_csw"] = -zwithin(d, "gap_csw")
    b["b_no_whiffs_swstr"] = -zwithin(d, "gap_swstr")
    b["b_no_whiffs_kbb"] = -zwithin(d, "gap_kbb")
    # (c) damage-prone: high barrel, hard-hit, xwOBA-on-contact
    b["c_damage"] = (zwithin(d, "barrel_pct_to") + zwithin(d, "hard_hit_pct_to")
                     + zwithin(d, "xwoba_on_contact_to")) / 3
    # (d) incomplete-arsenal: NOT derivable (no per-pitch arsenal / platoon / TTO in panel).
    #     Proxy attempt: low chase (o_swing) given stuff = hitters not fooled -> shallow arsenal.
    b["d_arsenal_proxy"] = -zwithin(d, "o_swing_pct_to")
    # (e) poor-workload: short outings. Proxy = low IP/start. We lack innings col, but
    #     low pitches/TBF per start is the only handle; use tbf_to/gs_to (batters faced per start).
    d["bf_per_start"] = d["tbf_to"] / d["gs_to"]
    b["e_short_outings"] = -zwithin(d, "bf_per_start")  # fewer BF/start -> shorter -> avoid
    # (f) declining-stuff: last21 velo below cumulative velo (fading)
    d["velo_delta"] = d["avg_velo_last21"] - d["avg_velo_to"]
    b["f_declining_velo"] = -zwithin(d, "velo_delta")   # negative delta -> avoid
    return pd.DataFrame(b, index=d.index)


def oos_incremental(cohort, buckets, target="ros_fp_per_start"):
    """Expanding-window OOS: train years < test year. Base = stuff_proxy alone.
    For each bucket measure incremental OOS predictive value via:
      - Spearman(bucket, residual of target on base)  [direction & strength]
      - ΔR² (OOS) of [base+bucket] over [base] pooled across test folds
    Returns per-bucket dict.
    """
    from sklearn.linear_model import LinearRegression
    df = cohort.copy()
    bk = buckets.loc[df.index]
    years = sorted(df.year.unique())
    test_years = [y for y in years if y > years[0]]  # need >=1 train year

    base_col = "stuff_proxy"
    results = {c: {"oos_resid_pred": [], "base_r2": [], "full_r2": [],
                   "n": 0, "corr_full": []} for c in bk.columns}

    # Pooled OOS predictions for ΔR²
    for c in bk.columns:
        oos_y, oos_base_pred, oos_full_pred = [], [], []
        for ty in test_years:
            tr = df.year < ty
            te = df.year == ty
            Xtr_b = df.loc[tr, [base_col]].values
            Xte_b = df.loc[te, [base_col]].values
            ytr = df.loc[tr, target].values
            yte = df.loc[te, target].values
            # full model adds the bucket
            xb_tr = bk.loc[df.index[tr], c].values.reshape(-1, 1)
            xb_te = bk.loc[df.index[te], c].values.reshape(-1, 1)
            okt = np.isfinite(xb_tr).ravel()
            oke = np.isfinite(xb_te).ravel()
            if okt.sum() < 30 or oke.sum() < 20:
                continue
            Xtr_f = np.column_stack([Xtr_b[okt], xb_tr[okt]])
            Xte_f = np.column_stack([Xte_b[oke], xb_te[oke]])
            mb = LinearRegression().fit(Xtr_b[okt], ytr[okt])
            mf = LinearRegression().fit(Xtr_f, ytr[okt])
            oos_y.append(yte[oke])
            oos_base_pred.append(mb.predict(Xte_b[oke]))
            oos_full_pred.append(mf.predict(Xte_f))
        if not oos_y:
            continue
        Y = np.concatenate(oos_y)
        Pb = np.concatenate(oos_base_pred)
        Pf = np.concatenate(oos_full_pred)
        ss_tot = ((Y - Y.mean()) ** 2).sum()
        r2_b = 1 - ((Y - Pb) ** 2).sum() / ss_tot
        r2_f = 1 - ((Y - Pf) ** 2).sum() / ss_tot
        # direction: spearman of bucket vs residual-on-base (OOS-ish: use full pooled)
        resid = Y - Pb
        bvals = []  # align bucket to the same OOS rows
        # rebuild bucket vector in same order
        idx_order = []
        for ty in test_years:
            te = df.year == ty
            xb_te = bk.loc[df.index[te], c].values
            oke = np.isfinite(xb_te)
            idx_order.append(xb_te[oke])
        Bvec = np.concatenate(idx_order)
        rho, p = stats.spearmanr(Bvec, resid)
        results[c] = {"n": len(Y), "base_r2": r2_b, "full_r2": r2_f,
                      "delta_r2": r2_f - r2_b, "spearman_vs_resid": rho,
                      "spearman_p": p}
    return results


def convergence_check(cohort, buckets, target="ros_fp_per_start"):
    """Leakage smoking-gun: per-split_day Spearman(bucket, target) within high-Stuff
    cohort. Identical lifts across ALL split_days = leakage (per
    feedback_convergence_curve_leakage_detector). A real as-of signal should vary
    (typically stronger early, weaker late as the RoS window shrinks)."""
    rows = []
    for c in buckets.columns:
        per = {}
        for sd in sorted(cohort.split_day.unique()):
            m = cohort.split_day == sd
            x = buckets.loc[cohort.index[m], c].values
            y = cohort.loc[m, target].values
            ok = np.isfinite(x) & np.isfinite(y)
            if ok.sum() < 40:
                continue
            rho, _ = stats.spearmanr(x[ok], y[ok])
            per[sd] = rho
        if per:
            vals = np.array(list(per.values()))
            rows.append({"bucket": c, "n_splits": len(vals),
                         "mean_rho": vals.mean(), "sd_rho": vals.std(),
                         "early": np.mean([per[s] for s in per if s <= 79]),
                         "late": np.mean([per[s] for s in per if s >= 135])})
    return pd.DataFrame(rows)


def fg_crosscheck(cohort):
    """Join real FG Stuff+ at matching cutoffs (06-06 -> split_day 65/72) and
    confirm the stuff-proxy cohort overlaps real high-Stuff+. Also confirm
    command/location does NOT predict forward FP (prior finding)."""
    out = []
    for yr in [2021, 2022, 2023, 2024, 2025]:
        f = FG / f"fg_pit_{yr}_pre.csv"
        if not f.exists():
            continue
        fg = pd.read_csv(f)[["mlb_id", "stuff_plus", "location_plus", "bb_pct"]]
        fg = fg.rename(columns={"mlb_id": "pitcher"})
        # nearest split_day to 06-06 ~ day 65/72
        sub = cohort[(cohort.year == yr) & (cohort.split_day.isin([65, 72]))]
        if sub.empty:
            continue
        # one row per pitcher (the 65 split if present)
        sub = sub.sort_values("split_day").drop_duplicates("pitcher", keep="first")
        m = sub.merge(fg, on="pitcher", how="inner")
        m = m.replace([np.inf, -np.inf], np.nan)
        out.append(m)
    if not out:
        return None
    allm = pd.concat(out, ignore_index=True)
    res = {}
    for col in ["stuff_plus", "location_plus", "bb_pct"]:
        ok = allm[col].notna() & allm.ros_fp_per_start.notna()
        if ok.sum() > 20:
            r, p = stats.spearmanr(allm.loc[ok, col], allm.loc[ok, "ros_fp_per_start"])
            res[col] = (r, p, ok.sum())
    # proxy vs real stuff+ correlation
    ok = allm.stuff_proxy.notna() & allm.stuff_plus.notna()
    res["proxy_vs_real_stuffplus"] = stats.spearmanr(
        allm.loc[ok, "stuff_proxy"], allm.loc[ok, "stuff_plus"])
    return res, len(allm)


def main():
    pd.set_option("display.width", 160)
    d = load_panel()
    print(f"Panel SP-weeks (hist yrs, gs_to>={MIN_GS_TO}, ros_gs>={MIN_ROS_GS}): {len(d)}")
    coh = high_stuff_cohort(d)
    print(f"HIGH-Stuff cohort (top-quartile stuff_proxy within cell): {len(coh)}")
    print(f"  forward ros_fp_per_start: mean {coh.ros_fp_per_start.mean():.2f} "
          f"sd {coh.ros_fp_per_start.std():.2f}")
    print(f"  full-panel forward mean {d.ros_fp_per_start.mean():.2f} "
          f"(high-Stuff edge {coh.ros_fp_per_start.mean()-d.ros_fp_per_start.mean():+.2f})\n")

    buckets = build_buckets(d).loc[coh.index]

    print("=== OOS INCREMENTAL VALUE OVER stuff_proxy ALONE (expanding window) ===")
    res = oos_incremental(coh, buckets)
    rows = []
    for c, r in res.items():
        if "delta_r2" in r:
            rows.append([c, r["n"], r["base_r2"], r["delta_r2"],
                         r["spearman_vs_resid"], r["spearman_p"]])
    rdf = pd.DataFrame(rows, columns=["bucket", "n_oos", "base_r2",
                                      "delta_r2", "rho_resid", "p"])
    rdf = rdf.sort_values("delta_r2", ascending=False)
    print(rdf.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))

    print("\n=== CONVERGENCE-CURVE LEAKAGE CHECK (per-split Spearman vs forward FP) ===")
    cc = convergence_check(coh, buckets)
    print(cc.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    print("(real as-of signal => 'early' stronger than 'late'; identical-across-all => leakage)")

    print("\n=== FG REAL Stuff+ / Location+ CROSS-CHECK (06-06 cutoff join) ===")
    fc = fg_crosscheck(coh)
    if fc:
        res2, nfg = fc
        print(f"  joined n={nfg}")
        for k, v in res2.items():
            if k == "proxy_vs_real_stuffplus":
                print(f"  proxy vs real Stuff+ : rho={v.correlation:+.3f}")
            else:
                print(f"  {k:14s} vs forward FP: rho={v[0]:+.3f} p={v[1]:.3g} n={v[2]}")

    # quintile readout for top validating buckets (practical rule)
    print("\n=== QUINTILE FORWARD FP BY BUCKET (high-Stuff cohort, Q5=most 'avoid') ===")
    for c in ["b_no_whiffs_csw", "c_damage", "a_no_command", "e_short_outings", "f_declining_velo"]:
        x = buckets[c]
        q = pd.qcut(x.rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
        means = coh.groupby(q, observed=True)["ros_fp_per_start"].mean()
        spread = means.get(5, np.nan) - means.get(1, np.nan)
        print(f"  {c:18s} Q1={means.get(1,np.nan):5.2f}  Q5={means.get(5,np.nan):5.2f}  "
              f"Q5-Q1={spread:+5.2f}")


if __name__ == "__main__":
    main()

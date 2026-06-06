"""
Does FanGraphs Location+ matter conditionally on Stuff+ for predicting a SP's
rest-of-season BrownU fantasy FP/start?

Prior finding (pooled, n~506 SP-seasons 2021-2025): Stuff+ partial r ~0.30,
Location+ raw r 0.02 / partial r -0.05 -> marginally useless on average.

This script asks: is Location+ useless at ALL Stuff+ levels, or does it "wake up"
once Stuff+ is high? Four lenses:
  1. Interaction OLS: ros_fp ~ stuff_c + loc_c + stuff_c:loc_c + controls
  2. Stratified partial-r of Location+ vs ros_fp (control pre_fp) within Stuff+ tiers
  3. 2D cell grid of mean ros_fp (and n) over Stuff+ x Location+ buckets
  4. Marginal dROS_fp per +10 Location+ evaluated at Stuff+ = 95..115

No statsmodels in env -> exact OLS via sklearn coefs + closed-form t-stats.
"""
import sys
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, "scripts/xfp")
from validate_fg_pitch_modeling_inseason import load  # noqa: E402

pd.set_option("display.width", 140)
pd.set_option("display.float_format", lambda v: f"{v:,.3f}")


def ols_with_tstats(X_no_const: np.ndarray, y: np.ndarray, names):
    """Exact OLS. X_no_const has no intercept column; we add one.
    Returns dict name->(coef, se, t, p) including 'const'."""
    n, k = X_no_const.shape
    X = np.column_stack([np.ones(n), X_no_const])
    cols = ["const"] + list(names)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = n - X.shape[1]
    sigma2 = (resid @ resid) / dof
    XtX_inv = np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(XtX_inv) * sigma2)
    t = beta / se
    p = 2 * stats.t.sf(np.abs(t), dof)
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2 = 1 - (resid @ resid) / ss_tot
    return {c: (b, s, tt, pp) for c, b, s, tt, pp in zip(cols, beta, se, t, p)}, r2, beta, cols


def partial_r(x, y, z):
    """Partial correlation of x and y controlling for matrix z (cols)."""
    z = np.column_stack([np.ones(len(x)), z])
    def resid(v):
        b, *_ = np.linalg.lstsq(z, v, rcond=None)
        return v - z @ b
    rx, ry = resid(x), resid(y)
    if rx.std() < 1e-12 or ry.std() < 1e-12:
        return np.nan
    return np.corrcoef(rx, ry)[0, 1]


def main():
    df = load().copy()
    ctrl_cols = ["pre_fp", "k_pct", "bb_pct", "swstr_pct", "siera"]
    need = ["stuff_plus", "location_plus", "ros_fp"] + ctrl_cols
    df = df.dropna(subset=need).reset_index(drop=True)
    n = len(df)
    print(f"N (complete cases) = {n}\n")

    # --- center stuff/location ---
    s_mean = df["stuff_plus"].mean()
    l_mean = df["location_plus"].mean()
    df["stuff_c"] = df["stuff_plus"] - s_mean
    df["loc_c"] = df["location_plus"] - l_mean
    df["stuff_x_loc"] = df["stuff_c"] * df["loc_c"]
    print(f"Centering: stuff mean={s_mean:.2f}, location mean={l_mean:.2f}\n")

    # ================================================================
    # 1. Interaction regression
    # ================================================================
    print("=" * 70)
    print("1. INTERACTION OLS  ros_fp ~ stuff_c + loc_c + stuff_c:loc_c + controls")
    print("=" * 70)
    feat = ["stuff_c", "loc_c", "stuff_x_loc"] + ctrl_cols
    X = df[feat].to_numpy(float)
    y = df["ros_fp"].to_numpy(float)
    res, r2, beta, cols = ols_with_tstats(X, y, feat)
    print(f"{'term':<14}{'coef':>10}{'se':>9}{'t':>8}{'p':>10}")
    for c in cols:
        b, se, t, p = res[c]
        print(f"{c:<14}{b:>10.4f}{se:>9.4f}{t:>8.2f}{p:>10.4f}")
    print(f"\nmodel R^2 = {r2:.4f}")
    ib, ise, it, ip = res["stuff_x_loc"]
    sign = "POSITIVE" if ib > 0 else "NEGATIVE"
    print(f"\nINTERACTION (stuff_c:loc_c): coef={ib:+.5f}  p={ip:.4f}  -> {sign}")
    print("Positive => Location+ helps MORE as Stuff+ rises (the user's hypothesis).")

    # keep regression pieces for step 4
    reg_beta = dict(zip(cols, beta))
    ctrl_means = {c: df[c].mean() for c in ctrl_cols}

    # ================================================================
    # 2. Stratified partial-r of Location+ vs ros_fp (control pre_fp)
    # ================================================================
    print("\n" + "=" * 70)
    print("2. STRATIFIED partial-r( location_plus , ros_fp | pre_fp )  by Stuff+ tier")
    print("=" * 70)
    sbins = [-np.inf, 100, 105, 110, np.inf]
    slabels = ["<100", "100-105", "105-110", ">=110"]
    df["stuff_tier"] = pd.cut(df["stuff_plus"], bins=sbins, labels=slabels, right=False)
    print(f"{'Stuff+ tier':<12}{'n':>5}{'partial_r(loc,ros|pre)':>26}{'raw_r(loc,ros)':>17}")
    for lab in slabels:
        sub = df[df["stuff_tier"] == lab]
        nn = len(sub)
        if nn < 4:
            print(f"{lab:<12}{nn:>5}{'(too few)':>26}")
            continue
        pr = partial_r(
            sub["location_plus"].to_numpy(float),
            sub["ros_fp"].to_numpy(float),
            sub[["pre_fp"]].to_numpy(float),
        )
        rr = np.corrcoef(sub["location_plus"], sub["ros_fp"])[0, 1]
        print(f"{lab:<12}{nn:>5}{pr:>26.3f}{rr:>17.3f}")

    # ================================================================
    # 3. 2D cell grid: mean ros_fp (n) over Stuff+ x Location+ buckets
    # ================================================================
    print("\n" + "=" * 70)
    print("3. 2D CELL GRID  mean ros_fp [n]   (rows=Stuff+, cols=Location+)")
    print("   cells with n<8 flagged * = UNRELIABLE")
    print("=" * 70)
    lbins = [-np.inf, 100, 105, 110, np.inf]
    llabels = ["<100", "100-105", "105-110", ">=110"]
    df["loc_tier"] = pd.cut(df["location_plus"], bins=lbins, labels=llabels, right=False)

    grid_mean = pd.DataFrame(index=slabels, columns=llabels, dtype=object)
    for sl in slabels:
        for ll in llabels:
            cell = df[(df["stuff_tier"] == sl) & (df["loc_tier"] == ll)]
            nn = len(cell)
            if nn == 0:
                grid_mean.loc[sl, ll] = "  -"
            else:
                m = cell["ros_fp"].mean()
                flag = "*" if nn < 8 else " "
                grid_mean.loc[sl, ll] = f"{m:5.2f}[{nn}]{flag}"
    print("Location+ ->")
    print(grid_mean.to_string())

    print("\nDirect read of the user's question (mean ros_fp):")
    def cellmean(sl, ll):
        c = df[(df["stuff_tier"] == sl) & (df["loc_tier"] == ll)]
        return (c["ros_fp"].mean(), len(c)) if len(c) else (np.nan, 0)
    for sl in ["100-105", ">=110"]:
        lo_m, lo_n = cellmean(sl, "100-105")
        hi_m, hi_n = cellmean(sl, "105-110")
        hh_m, hh_n = cellmean(sl, ">=110")
        print(f"  Stuff+ {sl}: Loc 100-105={lo_m:.2f}(n{lo_n})  "
              f"Loc 105-110={hi_m:.2f}(n{hi_n})  Loc>=110={hh_m:.2f}(n{hh_n})")

    # ================================================================
    # 4. Marginal value of +10 Location+ at varying Stuff+ (from step-1 model)
    # ================================================================
    print("\n" + "=" * 70)
    print("4. MARGINAL dROS_fp per +10 Location+  (from interaction model)")
    print("=" * 70)
    # dros/dloc = b_loc + b_inter * stuff_c  ; per +10 => *10
    b_loc = reg_beta["loc_c"]
    b_int = reg_beta["stuff_x_loc"]
    print(f"d(ros_fp)/d(loc) = {b_loc:+.5f} + ({b_int:+.5f}) * (stuff+ - {s_mean:.1f})")
    print(f"{'Stuff+':>8}{'slope/pt':>12}{'delta per +10 Loc+':>22}")
    for sp in [95, 100, 105, 110, 115]:
        slope = b_loc + b_int * (sp - s_mean)
        print(f"{sp:>8}{slope:>12.4f}{slope*10:>22.3f}")

    print("\nDONE.")


if __name__ == "__main__":
    main()

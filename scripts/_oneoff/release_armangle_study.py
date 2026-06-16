"""
release_armangle_study.py
=========================
Leakage-safe OOS study: does RELEASE-POINT / ARM-ANGLE drift add
SP decline-prediction signal OVER our existing overall-velo-decline flag?

Theory: velo loss is orthogonal to whiffs (it's an injury/fatigue channel).
Mechanics drift (release-point scatter/shift + arm-angle change) should
separate INJURY-GRADE velo loss (drop WITH arm-slot/release drift) from
BENIGN velo loss (drop WITH stable mechanics).

Methodology (matches the standing protocol):
  (1) Leakage-safe as-of features: built ONLY from pitches with
      game_date < cutoff_date. Cutoffs = split_day {51,72,93,114},
      years 2021-2025. Join to forward target ros_fp_per_start on
      (pitcher, year, split_day). Gate gs_to>=5 & ros_gs>=3.
  (2) Rule-9 baseline: control for whiff/K LEVEL = rank(swstr_pct_to)
      + rank(k_pct_to) AND fp_per_start_to. Report partial-r of each
      feature on ros_fp_per_start over:
        [level, fp]                       -- adds over results
        [level, fp, overall_velo_yoy]     -- THE BAR: beat overall velo
      overall_velo_yoy = (current FB velo as-of) - (prior-yr full-season FB velo).
  (3) Downside: bust = bottom tercile of ros_fp_per_start WITHIN each
      (year, split_day) cell. Report bust-gap (mean feature in bust vs
      non-bust, standardized).
  (4) KEY interaction: does velo-drop predict worse/bust harder WHEN
      mechanics ALSO drifted? (velo-drop x mechanics-drift interaction).
  (5) Honesty: a feature wins ONLY if it adds partial-r over BOTH bars at
      adequate n. Reject nulls plainly. Report coverage.

NOTE ON arm_angle COVERAGE: CLAUDE.md says arm_angle is "2025+ only", but
the LOCAL statcast parquet cache has arm_angle backfilled for 2021-2026
(Statcast retroactively computed it). So the YoY arm_angle feature has
FULL coverage here, not 2025-only. Flagged in the writeup.

All data LOCAL. No network.
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path

CACHE = Path("data/research/xfp_cache")
PANEL = CACHE / "rolling_pitchers_2018_2026.csv"
YEARS = [2021, 2022, 2023, 2024, 2025]
SPLIT_DAYS = [51, 72, 93, 114]
FB = {"FF", "SI", "FC"}
RECENT_DAYS = 21  # "recent" window before cutoff for drift-vs-baseline

REL_COLS = [
    "pitcher", "game_date", "pitch_type", "p_throws",
    "release_pos_x", "release_pos_z", "release_extension",
    "release_speed", "arm_angle",
]


def load_statcast(year):
    df = pd.read_parquet(CACHE / f"statcast_{year}.parquet", columns=REL_COLS)
    df = df[df["pitch_type"].isin(FB)].copy()
    df["game_date"] = pd.to_datetime(df["game_date"])
    for c in ["release_pos_x", "release_pos_z", "release_extension",
              "release_speed", "arm_angle"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["pitcher"] = df["pitcher"].astype("Int64")
    return df


def prior_year_fb_ref(year):
    """Prior full-season FB-only per-pitcher: velo + arm_angle + release_pos."""
    py = year - 1
    fp = CACHE / f"statcast_{py}.parquet"
    if not fp.exists():
        return None
    df = pd.read_parquet(fp, columns=REL_COLS)
    df = df[df["pitch_type"].isin(FB)].copy()
    for c in ["release_pos_x", "release_pos_z", "release_extension",
              "release_speed", "arm_angle"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["pitcher"] = df["pitcher"].astype("Int64")
    g = df.groupby("pitcher").agg(
        velo_prev=("release_speed", "mean"),
        arm_prev=("arm_angle", "mean"),
        relx_prev=("release_pos_x", "mean"),
        relz_prev=("release_pos_z", "mean"),
        ext_prev=("release_extension", "mean"),
        n_prev=("release_speed", "size"),
    ).reset_index()
    g = g[g["n_prev"] >= 100]  # require a real prior-year FB sample
    return g


def asof_features(sc, cutoff):
    """Per-pitcher as-of FB mechanics features (game_date < cutoff)."""
    cut = pd.Timestamp(cutoff)
    pre = sc[sc["game_date"] < cut]
    if pre.empty:
        return pd.DataFrame()
    rec_start = cut - pd.Timedelta(days=RECENT_DAYS)
    recent = pre[pre["game_date"] >= rec_start]

    # season-to-cutoff baseline aggregates
    base = pre.groupby("pitcher").agg(
        n_to=("release_speed", "size"),
        velo_to=("release_speed", "mean"),
        arm_to=("arm_angle", "mean"),
        relx_mean=("release_pos_x", "mean"),
        relz_mean=("release_pos_z", "mean"),
        relx_std=("release_pos_x", "std"),
        relz_std=("release_pos_z", "std"),
        ext_to=("release_extension", "mean"),
    )

    # recent window aggregates
    rec = recent.groupby("pitcher").agg(
        n_rec=("release_speed", "size"),
        velo_rec=("release_speed", "mean"),
        arm_rec=("arm_angle", "mean"),
        relx_rec=("release_pos_x", "mean"),
        relz_rec=("release_pos_z", "mean"),
        ext_rec=("release_extension", "mean"),
    )

    f = base.join(rec, how="left").reset_index()

    # --- release-point DRIFT: recent shift vs season baseline (abs, ft) ---
    f["relx_shift"] = (f["relx_rec"] - f["relx_mean"]).abs()
    f["relz_shift"] = (f["relz_rec"] - f["relz_mean"]).abs()
    # combined euclidean release shift (ft)
    f["rel_shift"] = np.sqrt(
        (f["relx_rec"] - f["relx_mean"]) ** 2
        + (f["relz_rec"] - f["relz_mean"]) ** 2
    )
    # release SCATTER (within-season std of release point) -- inconsistency
    f["rel_scatter"] = np.sqrt(f["relx_std"] ** 2 + f["relz_std"] ** 2)

    # --- extension change recent vs baseline (ft) ---
    f["ext_change"] = (f["ext_rec"] - f["ext_to"]).abs()

    # --- arm angle recent-vs-baseline shift (deg) ---
    f["arm_shift_recent"] = (f["arm_rec"] - f["arm_to"]).abs()

    return f


def zscore_within(df, col, grp=("year", "split_day")):
    g = df.groupby(list(grp))[col]
    mu = g.transform("mean")
    sd = g.transform("std").replace(0, np.nan)
    return (df[col] - mu) / sd


def partial_r(y, x, controls, df):
    """Partial correlation of x with y given controls (resid-on-resid)."""
    import numpy as np
    cols = [x] + list(controls)
    d = df[[y] + cols].dropna()
    n = len(d)
    if n < 30:
        return np.nan, n
    X = d[controls].to_numpy(float)
    X = np.column_stack([np.ones(len(d)), X])

    def resid(v):
        beta, *_ = np.linalg.lstsq(X, v, rcond=None)
        return v - X @ beta

    rx = resid(d[x].to_numpy(float)).ravel()
    ry = resid(d[y].to_numpy(float)).ravel()
    if rx.std() < 1e-9 or ry.std() < 1e-9:
        # x is (near-)collinear with controls -> partial-r undefined (e.g.
        # testing overall_velo_yoy while it is itself a control)
        return np.nan, n
    r = np.corrcoef(rx, ry)[0, 1]
    return r, n


def main():
    panel = pd.read_csv(PANEL)
    panel = panel[panel["year"].isin(YEARS) & panel["split_day"].isin(SPLIT_DAYS)].copy()
    panel = panel[(panel["gs_to"] >= 5) & (panel["ros_gs"] >= 3)].copy()
    panel["pitcher"] = panel["pitcher"].astype("Int64")

    rows = []
    cov = {}
    for yr in YEARS:
        sc = load_statcast(yr)
        prev = prior_year_fb_ref(yr)
        py = panel[panel["year"] == yr]
        for sd in SPLIT_DAYS:
            sub = py[py["split_day"] == sd]
            if sub.empty:
                continue
            cutoff = sub["cutoff_date"].iloc[0]
            feats = asof_features(sc, cutoff)
            if feats.empty:
                continue
            feats["year"] = yr
            feats["split_day"] = sd
            m = sub.merge(feats, on=["pitcher", "year", "split_day"], how="left")
            if prev is not None:
                m = m.merge(prev[["pitcher", "velo_prev", "arm_prev",
                                  "relx_prev", "relz_prev", "ext_prev"]],
                            on="pitcher", how="left")
            else:
                for c in ["velo_prev", "arm_prev", "relx_prev", "relz_prev", "ext_prev"]:
                    m[c] = np.nan
            rows.append(m)
    df = pd.concat(rows, ignore_index=True)

    # ---- overall_velo_yoy = current FB velo as-of - prior-yr full-season FB velo
    df["overall_velo_yoy"] = df["velo_to"] - df["velo_prev"]
    # ---- arm_angle YoY change (deg): current as-of arm vs prior full-season arm
    df["arm_yoy"] = (df["arm_to"] - df["arm_prev"]).abs()
    # ---- release-point YoY shift vs prior season (ft)
    df["rel_yoy"] = np.sqrt(
        (df["relx_mean"] - df["relx_prev"]) ** 2
        + (df["relz_mean"] - df["relz_prev"]) ** 2
    )
    df["ext_yoy"] = (df["ext_to"] - df["ext_prev"]).abs()

    # ---- composite MECHANICS-DRIFT score: z-sum of the within-season drift
    #      components (recent shift + scatter + ext change) + YoY arm/rel.
    drift_components = ["rel_shift", "rel_scatter", "ext_change",
                        "arm_shift_recent", "arm_yoy", "rel_yoy"]
    for c in drift_components:
        df[f"z_{c}"] = zscore_within(df, c)
    df["mech_drift"] = df[[f"z_{c}" for c in drift_components]].mean(axis=1)
    # within-season-only variant (no YoY) for the no-prior-year coverage case
    ws = ["rel_shift", "rel_scatter", "ext_change", "arm_shift_recent"]
    df["mech_drift_ws"] = df[[f"z_{c}" for c in ws]].mean(axis=1)

    # ---- baseline controls (Rule 9): whiff/K LEVEL + results level
    df["lvl_swstr"] = df.groupby(["year", "split_day"])["swstr_pct_to"].rank()
    df["lvl_k"] = df.groupby(["year", "split_day"])["k_pct_to"].rank()
    df["level"] = df["lvl_swstr"] + df["lvl_k"]
    # velo-drop signed (negative = lost velo). Use signed for interaction.
    df["velo_drop"] = df["overall_velo_yoy"]  # negative = decline

    Y = "ros_fp_per_start"

    # ---------------- COVERAGE ----------------
    cov_lines = []
    cov_lines.append(f"gated panel rows (2021-25, 4 cutoffs): {len(df)}")
    cov_lines.append(f"  with as-of FB release features (rel_shift): {df['rel_shift'].notna().sum()}")
    cov_lines.append(f"  with arm_shift_recent:                     {df['arm_shift_recent'].notna().sum()}")
    cov_lines.append(f"  with overall_velo_yoy (prior-yr ref):      {df['overall_velo_yoy'].notna().sum()}")
    cov_lines.append(f"  with arm_yoy:                              {df['arm_yoy'].notna().sum()}")
    cov_lines.append(f"  with mech_drift (full, needs YoY):         {df['mech_drift'].notna().sum()}")
    cov_lines.append(f"  with mech_drift_ws (within-season only):   {df['mech_drift_ws'].notna().sum()}")
    by_yr = df.groupby("year")["overall_velo_yoy"].apply(lambda s: s.notna().sum())
    cov_lines.append("  overall_velo_yoy non-null by year: " + str(by_yr.to_dict()))

    # ---------------- PARTIAL-R TABLE ----------------
    feats_to_test = [
        ("overall_velo_yoy", "REFERENCE: overall velo YoY (the bar)"),
        ("rel_shift",        "release-pt recent shift vs season (ft)"),
        ("rel_scatter",      "release-pt within-season scatter (ft)"),
        ("ext_change",       "extension recent-vs-season change (ft)"),
        ("arm_shift_recent", "arm-angle recent-vs-season shift (deg)"),
        ("arm_yoy",          "arm-angle YoY change (deg)"),
        ("rel_yoy",          "release-pt YoY shift (ft)"),
        ("ext_yoy",          "extension YoY change (ft)"),
        ("mech_drift",       "COMPOSITE mechanics-drift (full incl YoY)"),
        ("mech_drift_ws",    "COMPOSITE mechanics-drift (within-season only)"),
    ]
    table = []
    for f, desc in feats_to_test:
        r1, n1 = partial_r(Y, f, ["level", "fp_per_start_to"], df)
        r2, n2 = partial_r(Y, f, ["level", "fp_per_start_to", "overall_velo_yoy"], df)
        table.append((f, desc, r1, n1, r2, n2))

    # ---------------- BUST (bottom-tercile within cell) ----------------
    df["fp_terc"] = df.groupby(["year", "split_day"])[Y].transform(
        lambda s: pd.qcut(s, 3, labels=False, duplicates="drop")
    )
    df["bust"] = (df["fp_terc"] == 0).astype(int)
    bust_lines = []
    for f, desc in feats_to_test:
        d = df[[f, "bust"]].dropna()
        if len(d) < 50:
            bust_lines.append((f, desc, np.nan, np.nan, np.nan, len(d)))
            continue
        z = (d[f] - d[f].mean()) / d[f].std()
        gap = z[d["bust"] == 1].mean() - z[d["bust"] == 0].mean()
        bust_lines.append((f, desc, z[d["bust"] == 1].mean(),
                           z[d["bust"] == 0].mean(), gap, len(d)))

    # ---------------- KEY INTERACTION: velo-drop x mech-drift ----------------
    # Does losing velo hurt MORE when mechanics also drifted?
    di = df.dropna(subset=["velo_drop", "mech_drift_ws", Y]).copy()
    # standardize
    di["z_velo"] = (di["velo_drop"] - di["velo_drop"].mean()) / di["velo_drop"].std()
    di["z_mech"] = (di["mech_drift_ws"] - di["mech_drift_ws"].mean()) / di["mech_drift_ws"].std()
    di["inter"] = di["z_velo"] * di["z_mech"]
    # regression: ros_fp ~ level + fp + z_velo + z_mech + inter
    Xc = di[["level", "fp_per_start_to", "z_velo", "z_mech", "inter"]].to_numpy(float)
    Xc = np.column_stack([np.ones(len(di)), Xc])
    yv = di[Y].to_numpy(float)
    beta, *_ = np.linalg.lstsq(Xc, yv, rcond=None)
    yhat = Xc @ beta
    resid = yv - yhat
    # std errors
    n, k = Xc.shape
    s2 = (resid @ resid) / (n - k)
    cov_b = s2 * np.linalg.inv(Xc.T @ Xc)
    se = np.sqrt(np.diag(cov_b))
    tvals = beta / se
    names = ["intercept", "level", "fp_per_start_to", "z_velo", "z_mech", "interaction"]
    inter_lines = list(zip(names, beta, se, tvals))

    # 2x2 quadrant view of bust rate: velo-drop yes/no x mech-drift yes/no
    di["velo_lost"] = (di["velo_drop"] < di["velo_drop"].quantile(0.33)).astype(int)  # worst velo tercile
    di["mech_drifted"] = (di["mech_drift_ws"] > di["mech_drift_ws"].quantile(0.67)).astype(int)  # most drift
    # bust already carried on df rows; di is a subset of df so it is present
    if "bust" not in di.columns:
        di = di.merge(df[["pitcher", "year", "split_day", "bust"]],
                      on=["pitcher", "year", "split_day"], how="left")
    quad = di.groupby(["velo_lost", "mech_drifted"]).agg(
        n=(Y, "size"),
        mean_ros_fp=(Y, "mean"),
        bust_rate=("bust", "mean"),
    ).reset_index()

    # ---------------- PRINT ----------------
    print("=" * 78)
    print("RELEASE-POINT / ARM-ANGLE DRIFT — SP DECLINE SIGNAL STUDY")
    print("=" * 78)
    print("\n[COVERAGE]")
    for l in cov_lines:
        print("  " + l)

    print("\n[PARTIAL-R TABLE]  (target = ros_fp_per_start; sign: + = predicts MORE fp)")
    print(f"  {'feature':<20} {'partial-r [lvl,fp]':>18}  {'partial-r [+velo_yoy]':>22}   n")
    print("  " + "-" * 74)
    for f, desc, r1, n1, r2, n2 in table:
        s1 = f"{r1:+.3f}" if pd.notna(r1) else "  n/a"
        s2 = f"{r2:+.3f}" if pd.notna(r2) else "  n/a"
        print(f"  {f:<20} {s1:>18}  {s2:>22}   {n2}")
    print("  (negative partial-r on a DRIFT feature = drift -> WORSE forward fp = decline signal)")

    print("\n[BUST-GAP]  bust = bottom-tercile ros_fp within (year,split_day) cell")
    print(f"  {'feature':<20} {'z|bust':>8} {'z|ok':>8} {'gap(b-ok)':>10}   n")
    print("  " + "-" * 60)
    for f, desc, zb, zo, gap, nn in bust_lines:
        sb = f"{zb:+.3f}" if pd.notna(zb) else " n/a"
        so = f"{zo:+.3f}" if pd.notna(zo) else " n/a"
        sg = f"{gap:+.3f}" if pd.notna(gap) else " n/a"
        print(f"  {f:<20} {sb:>8} {so:>8} {sg:>10}   {nn}")
    print("  (positive gap on a DRIFT feature = busts have MORE drift = decline signal)")

    print("\n[KEY INTERACTION]  ros_fp ~ level + fp + z_velo + z_mech + (z_velo*z_mech)")
    print(f"  n = {len(di)}")
    print(f"  {'term':<18} {'beta':>9} {'se':>8} {'t':>7}")
    for nm, b, s, t in inter_lines:
        print(f"  {nm:<18} {b:>9.3f} {s:>8.3f} {t:>7.2f}")
    print("  (interaction t: NEGATIVE & |t|>2 => velo loss hurts MORE when mechanics also drifted)")

    print("\n[2x2 QUADRANT]  worst-velo-tercile x most-drift-tercile")
    print(f"  {'velo_lost':>9} {'mech_drift':>11} {'n':>5} {'mean_ros_fp':>12} {'bust_rate':>10}")
    for _, r in quad.iterrows():
        print(f"  {int(r['velo_lost']):>9} {int(r['mech_drifted']):>11} {int(r['n']):>5} "
              f"{r['mean_ros_fp']:>12.2f} {r['bust_rate']:>10.3f}")

    # save the panel for reproducibility
    out = CACHE.parent / "validation_runs" / "_release_armangle_panel.csv"
    keep = ["pitcher", "year", "split_day", Y, "fp_per_start_to", "level",
            "overall_velo_yoy", "rel_shift", "rel_scatter", "ext_change",
            "arm_shift_recent", "arm_yoy", "rel_yoy", "mech_drift",
            "mech_drift_ws", "bust"]
    df[keep].to_csv(out, index=False)
    print(f"\n[saved panel] {out}")


if __name__ == "__main__":
    main()

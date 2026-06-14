"""
workload_fatigue_study.py  (2026-06-13)

Leakage-safe OOS study for an SP DECLINE-RISK model (BrownU 8-team points).

QUESTION: Do WORKLOAD / FATIGUE signals predict SP rest-of-season decline
OVER our existing velo-decline flags?

Hypotheses tested:
  (a) Verducci effect -- big YoY innings/pitch JUMP -> 2nd-half fade/injury.
  (b) Cumulative season pitch / TBF load to cutoff.
  (c) Short-rest patterns (mean days-rest, short-rest start share).
  (d) Age-adjusted workload (load relative to age).
  (e) KEY interaction: heavy load AND losing velo (workload x velo-decline).

SUBSTRATE
  - Panel (FORWARD target + as-of base): rolling_pitchers_2018_2026.csv
    per-(pitcher,year,split_day): cutoff_date, ros_fp_per_start (FORWARD),
    ros_gs, gs_to, avg_velo_to, swstr_pct_to, k_pct_to, fp_per_start_to,
    tbf_to (cumulative TBF), pitches_to, pitches_last21.
  - Statcast pitch-level statcast_{2021..2026}.parquet for: per-start pitch
    counts / TBF, days-rest (pitcher_days_since_prev_game), and PRIOR-YEAR
    full-season pitch load + season-end velo (for Verducci YoY spike).

METHODOLOGY (matches house convention)
  (1) Leakage-safe AS-OF: statcast game_date < cutoff_date only; cutoffs
      split_day in {51,72,93,114}; years 2021-2025; join on (pitcher,year,split_day).
  (2) Baseline Rule 9 -- partial-r of each candidate on ros_fp_per_start,
      controlling for:
        BAR-A  level = rank(swstr_pct_to)+rank(k_pct_to)  AND  fp_per_start_to
        BAR-B  BAR-A + overall_velo_yoy   (THE BAR: beat overall velo)
      overall_velo_yoy = avg_velo_to - prior-yr-season-end velo.
  (3) Downside bust-gap: forward FP in the bottom workload tercile within cell.
  (4) Verducci YoY-IP-spike specific test + workload x velo-decline interaction.
  (5) Honesty: a workload flag WINS only if it adds over BOTH bars at adequate
      n; reject nulls plainly.

partial-r computed WITHIN each (year,split_day) cell via OLS residualization
(house resid_within convention), then pooled Fisher-z.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "research" / "xfp_cache"
PANEL = CACHE / "rolling_pitchers_2018_2026.csv"
OUT_MD = ROOT / "data" / "research" / "validation_runs" / "workload_fatigue_2026-06-13.md"

CUTOFF_SPLITDAYS = [51, 72, 93, 114]
TEST_YEARS = [2021, 2022, 2023, 2024, 2025]
MIN_GS_TO = 5
MIN_ROS_GS = 3
SHORT_REST_THRESH = 4  # days_rest <=4 => short rest start


# ----------------------------------------------------------------------------
# Statcast as-of feature derivation
# ----------------------------------------------------------------------------
def starts_from_statcast(year: int) -> pd.DataFrame:
    """Return start-level rows for `year`: (pitcher, game_pk, game_date,
    pitches, tbf, days_rest). A start = pitcher who threw the first at-bat of
    inning 1 for a half-inning (regular season only)."""
    fp = CACHE / f"statcast_{year}.parquet"
    cols = ["game_pk", "game_date", "pitcher", "inning", "inning_topbot",
            "at_bat_number", "pitch_number", "pitcher_days_since_prev_game",
            "game_type"]
    df = pd.read_parquet(fp, columns=cols)
    df = df[df.game_type == "R"].copy()
    df["game_date"] = pd.to_datetime(df["game_date"])
    # identify starters
    inn1 = df[df.inning == 1]
    idx = inn1.groupby(["game_pk", "inning_topbot"])["at_bat_number"].idxmin()
    starters = inn1.loc[idx, ["game_pk", "inning_topbot", "pitcher"]]
    sp_keys = set(zip(starters.game_pk, starters.pitcher))
    df["is_sp"] = [(g, p) in sp_keys for g, p in zip(df.game_pk, df.pitcher)]
    sp = df[df.is_sp]
    g = (sp.groupby(["pitcher", "game_pk", "game_date"])
            .agg(pitches=("pitch_number", "size"),
                 tbf=("at_bat_number", "nunique"),
                 days_rest=("pitcher_days_since_prev_game", "max"))
            .reset_index())
    return g


def prior_year_season_load(year: int) -> pd.DataFrame:
    """Prior-year FULL-season per-pitcher: total pitches, total starts, IP-proxy
    (tbf), pitches/start, and season-END velo (mean velo over last 21 days of
    that pitcher's appearances)."""
    g = starts_from_statcast(year)
    if g.empty:
        return pd.DataFrame(columns=["pitcher", "py_pitches", "py_starts",
                                     "py_tbf", "py_pitches_per_start"])
    agg = (g.groupby("pitcher")
             .agg(py_pitches=("pitches", "sum"),
                  py_starts=("pitches", "size"),
                  py_tbf=("tbf", "sum"))
             .reset_index())
    agg["py_pitches_per_start"] = agg.py_pitches / agg.py_starts
    # season-end velo: from full pitch-level, last 21 days of the season
    fp = CACHE / f"statcast_{year}.parquet"
    v = pd.read_parquet(fp, columns=["pitcher", "game_date", "release_speed",
                                     "game_type"])
    v = v[v.game_type == "R"].copy()
    v["game_date"] = pd.to_datetime(v["game_date"])
    season_end = v.game_date.max()
    vlast = v[v.game_date >= season_end - pd.Timedelta(days=21)]
    ve = (vlast.groupby("pitcher")["release_speed"].mean()
                .rename("py_season_end_velo").reset_index())
    agg = agg.merge(ve, on="pitcher", how="left")
    return agg


def asof_workload_features(year: int, cutoffs: dict) -> pd.DataFrame:
    """For each split_day cutoff, compute AS-OF (game_date < cutoff) per-pitcher
    workload features from this season's starts."""
    g = starts_from_statcast(year)
    rows = []
    for sd, cutoff in cutoffs.items():
        cut = pd.Timestamp(cutoff)
        sub = g[g.game_date < cut]
        if sub.empty:
            continue
        feat = (sub.groupby("pitcher")
                   .agg(n_starts=("pitches", "size"),
                        cum_pitches=("pitches", "sum"),
                        cum_tbf=("tbf", "sum"),
                        pitches_per_start=("pitches", "mean"),
                        mean_days_rest=("days_rest", "mean"),
                        min_days_rest=("days_rest", "min"))
                   .reset_index())
        # short-rest share
        sr = (sub.assign(short=(sub.days_rest <= SHORT_REST_THRESH).astype(float))
                 .groupby("pitcher")["short"].mean()
                 .rename("short_rest_share").reset_index())
        feat = feat.merge(sr, on="pitcher", how="left")
        feat["year"] = year
        feat["split_day"] = sd
        rows.append(feat)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


# ----------------------------------------------------------------------------
# Stats helpers (house convention)
# ----------------------------------------------------------------------------
def resid_within(df, ycol, xcols, by=("year", "split_day")):
    """Residual of ycol on xcols, fit WITHIN each as-of cell (OLS, intercept)."""
    out = pd.Series(np.nan, index=df.index)
    for _, idx in df.groupby(list(by)).groups.items():
        sub = df.loc[idx]
        X = sub[xcols].values.astype(float)
        y = sub[ycol].values.astype(float)
        ok = np.isfinite(y) & np.all(np.isfinite(X), axis=1)
        if ok.sum() < 8:
            continue
        Xb = np.column_stack([np.ones(ok.sum()), X[ok]])
        beta, *_ = np.linalg.lstsq(Xb, y[ok], rcond=None)
        out.loc[sub.index[ok]] = y[ok] - (Xb @ beta)
    return out


def partial_r(df, feat, target, controls):
    """Partial correlation of feat with target controlling for `controls`,
    computed within-cell (residualize both feat and target on controls), then
    pool. Returns (r, p, n)."""
    d = df.dropna(subset=[feat, target] + controls).copy()
    if len(d) < 30:
        return (np.nan, np.nan, len(d))
    ry = resid_within(d, target, controls)
    rx = resid_within(d, feat, controls)
    m = ry.notna() & rx.notna()
    if m.sum() < 30:
        return (np.nan, np.nan, int(m.sum()))
    r, p = stats.pearsonr(rx[m], ry[m])
    return (r, p, int(m.sum()))


def zwithin(df, col, by=("year", "split_day")):
    g = df.groupby(list(by))[col]
    return (df[col] - g.transform("mean")) / g.transform("std").replace(0, np.nan)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    # ---- panel (forward target + base as-of cols) ----
    pan = pd.read_csv(PANEL)
    pan = pan[pan.year.isin(TEST_YEARS) & pan.split_day.isin(CUTOFF_SPLITDAYS)].copy()
    pan = pan[(pan.gs_to >= MIN_GS_TO) & (pan.ros_gs >= MIN_ROS_GS)].copy()

    # cutoffs per (year, split_day)
    cut_map = (pan[["year", "split_day", "cutoff_date"]]
               .drop_duplicates()
               .set_index(["year", "split_day"])["cutoff_date"].to_dict())

    # ---- as-of statcast workload features ----
    asof_list = []
    py_velo_list = []
    for yr in TEST_YEARS:
        cutoffs = {sd: cut_map[(yr, sd)] for sd in CUTOFF_SPLITDAYS
                   if (yr, sd) in cut_map}
        asof_list.append(asof_workload_features(yr, cutoffs))
        # prior-year season load (yr-1)
        py = prior_year_season_load(yr - 1)
        py["year"] = yr
        py_velo_list.append(py)
    asof = pd.concat(asof_list, ignore_index=True)
    pyld = pd.concat(py_velo_list, ignore_index=True)

    # ---- merge everything on (pitcher, year, split_day) / (pitcher, year) ----
    df = pan.merge(asof, on=["pitcher", "year", "split_day"], how="left")
    df = df.merge(pyld, on=["pitcher", "year"], how="left")

    # ---- derived features ----
    # baseline LEVEL = rank(swstr)+rank(k) within cell
    def rank_within(col):
        return df.groupby(["year", "split_day"])[col].rank(pct=True)
    df["level"] = rank_within("swstr_pct_to") + rank_within("k_pct_to")

    # overall_velo_yoy = avg_velo_to - prior-yr season-end velo  (THE BAR)
    df["overall_velo_yoy"] = df.avg_velo_to - df.py_season_end_velo

    # season-to-date pace -> project full season pitch load by linear pace.
    # fraction of season elapsed by split_day (162-game season ~ 183 days from ~day 30 start).
    # Use cum_pitches scaled to a common 114-day reference so YoY spike is pace-based,
    # not contaminated by how far into the season the cutoff sits.
    # pace pitches = cum_pitches / n_starts * (prior-yr starts) -> projected season pitches
    df["proj_season_pitches"] = np.where(
        df.n_starts > 0,
        df.pitches_per_start * np.where(df.py_starts.notna() & (df.py_starts > 0),
                                        df.py_starts, 30.0),
        np.nan)
    # Verducci YoY spike: projected season pitch load minus prior-year actual
    df["verducci_pitch_jump"] = df.proj_season_pitches - df.py_pitches
    # ratio form (more standard Verducci): proj/prior
    df["verducci_pitch_ratio"] = df.proj_season_pitches / df.py_pitches
    # TBF version (IP proxy)
    df["proj_season_tbf"] = np.where(
        df.n_starts > 0,
        (df.cum_tbf / df.n_starts) * np.where(df.py_starts.notna() & (df.py_starts > 0),
                                              df.py_starts, 30.0),
        np.nan)
    df["verducci_tbf_jump"] = df.proj_season_tbf - df.py_tbf

    # cumulative load to cutoff (panel tbf_to is the canonical cumulative TBF)
    df["cum_pitches_to"] = df.pitches_to        # from panel
    df["cum_tbf_to"] = df.tbf_to                # from panel
    # heavy recent load (panel) = pitches in last 21d
    df["recent_load"] = df.pitches_last21

    # workload x velo-decline interaction:
    #   heavy cumulative load (within-cell z) * losing velo (negative velo_yoy)
    df["z_cumpitch"] = zwithin(df, "cum_pitches_to")
    df["z_recent"] = zwithin(df, "recent_load")
    df["z_verducci"] = zwithin(df, "verducci_pitch_jump")
    df["velo_decline"] = -df.overall_velo_yoy            # positive = losing velo
    df["z_velo_decline"] = zwithin(df, "velo_decline")
    df["load_x_velodecline"] = df.z_cumpitch * df.z_velo_decline
    df["verducci_x_velodecline"] = df.z_verducci * df.z_velo_decline

    target = "ros_fp_per_start"
    base_A = ["level", "fp_per_start_to"]
    base_B = ["level", "fp_per_start_to", "overall_velo_yoy"]

    candidates = {
        "cum_pitches_to (season load)": "cum_pitches_to",
        "cum_tbf_to (season TBF load)": "cum_tbf_to",
        "pitches_per_start": "pitches_per_start",
        "recent_load (pitches last21)": "recent_load",
        "mean_days_rest": "mean_days_rest",
        "min_days_rest": "min_days_rest",
        "short_rest_share (<=4d)": "short_rest_share",
        "verducci_pitch_jump (Verducci)": "verducci_pitch_jump",
        "verducci_pitch_ratio (Verducci)": "verducci_pitch_ratio",
        "verducci_tbf_jump (Verducci IP)": "verducci_tbf_jump",
        "load_x_velodecline (INTERACTION)": "load_x_velodecline",
        "verducci_x_velodecline (INTERACTION)": "verducci_x_velodecline",
    }

    # ---- partial-r table ----
    rows = []
    for name, col in candidates.items():
        rA = partial_r(df, col, target, base_A)
        rB = partial_r(df, col, target, base_B)
        # raw (uncontrolled) within-cell corr for reference
        d0 = df.dropna(subset=[col, target])
        raw = stats.pearsonr(*(lambda m: (d0[col][m], d0[target][m]))
                             (np.isfinite(d0[col]) & np.isfinite(d0[target])))[0] \
              if len(d0) > 30 else np.nan
        rows.append(dict(feature=name, raw_r=raw,
                         pr_A=rA[0], p_A=rA[1], n_A=rA[2],
                         pr_B=rB[0], p_B=rB[1], n_B=rB[2]))
    tbl = pd.DataFrame(rows)

    # ---- BAR reference: overall velo's own partial-r over BAR-A (what we must beat) ----
    velo_pr = partial_r(df, "overall_velo_yoy", target, base_A)

    # ---- Verducci downside bust-gap: bottom workload tercile within cell ----
    def tercile_busts(feat):
        d = df.dropna(subset=[feat, target]).copy()
        d["terc"] = d.groupby(["year", "split_day"])[feat].transform(
            lambda s: pd.qcut(s.rank(method="first"), 3, labels=["low", "mid", "high"])
            if s.notna().sum() >= 9 else np.nan)
        out = d.groupby("terc")[target].agg(["mean", "median", "count"])
        return out
    # For Verducci, the RISK tercile is HIGH jump; report forward FP by tercile.
    verd_terc = tercile_busts("verducci_pitch_jump")
    load_terc = tercile_busts("cum_pitches_to")
    # interaction tercile (high load_x_velodecline = both heavy load and losing velo)
    inter_terc = tercile_busts("load_x_velodecline")

    # ---- write report ----
    n_total = df[df.cum_pitches_to.notna()].shape[0]
    n_verd = df.dropna(subset=["verducci_pitch_jump", target]).shape[0]

    def fmt(r, p, n):
        if not np.isfinite(r):
            return f"  n={n} (insufficient)"
        star = "*" if (np.isfinite(p) and p < 0.05) else " "
        return f"r={r:+.3f}{star} p={p:.3f} n={n}"

    lines = []
    lines.append("# Workload / Fatigue OOS Study for SP Decline-Risk (2026-06-13)\n")
    lines.append("**Question:** Do WORKLOAD / FATIGUE signals predict SP "
                 "rest-of-season decline OVER our existing velo-decline flags?\n")
    lines.append("**Frame:** BrownU 8-team points. Forward target = "
                 "`ros_fp_per_start` (rest-of-season FP/start over `ros_gs` "
                 "starts). All features AS-OF the cutoff (leakage-safe).\n")
    lines.append("## Methodology\n")
    lines.append("- Leakage-safe as-of: statcast `game_date < cutoff_date`; "
                 f"cutoffs split_day in {CUTOFF_SPLITDAYS}; years {TEST_YEARS}; "
                 "join on (pitcher,year,split_day).")
    lines.append(f"- Gate: `gs_to>={MIN_GS_TO}` & `ros_gs>={MIN_ROS_GS}`.")
    lines.append("- Baseline Rule 9 partial-r controls:")
    lines.append("  - **BAR-A** = `level` [rank(swstr%_to)+rank(k%_to)] + "
                 "`fp_per_start_to`.")
    lines.append("  - **BAR-B** = BAR-A + `overall_velo_yoy` "
                 "(`avg_velo_to` - prior-yr season-end velo). *THE BAR: beat velo.*")
    lines.append("- partial-r = within-cell OLS residualization (house "
                 "`resid_within`), pooled.")
    lines.append(f"- Gated panel rows with workload join: **n={n_total}** "
                 f"(Verducci subset n={n_verd}).\n")

    lines.append("## THE BAR -- velo-decline's own incremental partial-r over BAR-A\n")
    lines.append(f"`overall_velo_yoy` partial-r over BAR-A: "
                 f"{fmt(*velo_pr)}\n")
    lines.append("A workload feature must beat this AND remain significant over "
                 "BAR-B (which already contains velo) to earn a flag.\n")

    lines.append("## Partial-r table (incremental over baselines)\n")
    lines.append("| Feature | raw r | partial-r over BAR-A | partial-r over BAR-B (+velo) |")
    lines.append("|---|---|---|---|")
    for _, r in tbl.iterrows():
        a = fmt(r.pr_A, r.p_A, r.n_A)
        b = fmt(r.pr_B, r.p_B, r.n_B)
        raws = f"{r.raw_r:+.3f}" if np.isfinite(r.raw_r) else "n/a"
        lines.append(f"| {r.feature} | {raws} | {a} | {b} |")
    lines.append("\n(`*` = p<0.05. Sign: positive partial-r = MORE of this "
                 "feature -> HIGHER forward FP. For a *decline* signal we want a "
                 "NEGATIVE, significant partial-r that survives BAR-B.)\n")

    lines.append("## Verducci YoY pitch-jump -- forward FP by tercile\n")
    lines.append("`verducci_pitch_jump` = (projected full-season pitches at "
                 "current pace) - (prior-year actual season pitches).\n")
    lines.append("| Jump tercile | mean ros_fp/start | median | n |")
    lines.append("|---|---|---|---|")
    for terc in ["low", "mid", "high"]:
        if terc in verd_terc.index:
            row = verd_terc.loc[terc]
            lines.append(f"| {terc} | {row['mean']:.2f} | {row['median']:.2f} | "
                         f"{int(row['count'])} |")
    lines.append("\n(Verducci predicts the HIGH-jump tercile fades. A real "
                 "effect = high tercile mean materially below low/mid.)\n")

    lines.append("## Cumulative season load -- forward FP by tercile\n")
    lines.append("| `cum_pitches_to` tercile | mean ros_fp/start | median | n |")
    lines.append("|---|---|---|---|")
    for terc in ["low", "mid", "high"]:
        if terc in load_terc.index:
            row = load_terc.loc[terc]
            lines.append(f"| {terc} | {row['mean']:.2f} | {row['median']:.2f} | "
                         f"{int(row['count'])} |")

    lines.append("\n## KEY interaction -- heavy load AND losing velo\n")
    lines.append("`load_x_velodecline` = z(cum_pitches_to) x z(velo_decline) "
                 "[velo_decline = -overall_velo_yoy]. High = heavy load AND "
                 "losing velo (the hypothesized worst quadrant).\n")
    lines.append("| `load_x_velodecline` tercile | mean ros_fp/start | median | n |")
    lines.append("|---|---|---|---|")
    for terc in ["low", "mid", "high"]:
        if terc in inter_terc.index:
            row = inter_terc.loc[terc]
            lines.append(f"| {terc} | {row['mean']:.2f} | {row['median']:.2f} | "
                         f"{int(row['count'])} |")

    # ---- verdict logic ----
    # A win requires: partial-r over BAR-B significant (p<0.05) AND |pr_B| beats
    # velo's |pr over A|, AND n adequate (>=200).
    velo_bar = abs(velo_pr[0]) if np.isfinite(velo_pr[0]) else 0.0
    winners = []
    for _, r in tbl.iterrows():
        if (np.isfinite(r.pr_B) and np.isfinite(r.p_B) and r.p_B < 0.05
                and r.n_B >= 200 and abs(r.pr_B) > velo_bar
                and np.isfinite(r.pr_A) and r.p_A < 0.05):
            winners.append((r.feature, r.pr_B, r.p_B, r.n_B))

    lines.append("\n## VERDICT\n")
    if winners:
        lines.append("**WIRE A WORKLOAD FLAG.** The following survive BOTH bars "
                     "(p<0.05 over BAR-A and BAR-B) and beat velo's own "
                     f"incremental |r|={velo_bar:.3f}:\n")
        for f, r, p, n in winners:
            lines.append(f"- `{f}`: partial-r over velo-inclusive baseline "
                         f"= {r:+.3f} (p={p:.3f}, n={n}).")
    else:
        lines.append("**DO NOT WIRE A WORKLOAD FLAG.** No workload/fatigue "
                     "feature -- Verducci YoY pitch jump, cumulative season "
                     "load, pitches/start, days-rest, OR the "
                     "load x velo-decline interaction -- clears BOTH bars at "
                     "adequate n. Specifically:")
        lines.append(f"  - Velo-decline alone over BAR-A: {fmt(*velo_pr)} "
                     "(this is the bar to beat).")
        # report best workload contender
        cand = tbl.dropna(subset=["pr_B"]).copy()
        if len(cand):
            cand["abs_b"] = cand.pr_B.abs()
            best = cand.sort_values("abs_b", ascending=False).iloc[0]
            lines.append(f"  - Best workload contender over BAR-B: "
                         f"`{best.feature}` {fmt(best.pr_B, best.p_B, int(best.n_B))} "
                         "-- does not clear.")
        lines.append("\nWorkload/fatigue is **subsumed by velo** for points "
                     "decline-risk: once you control for cumulative skill "
                     "(swstr/K/FP) and velo trajectory, raw innings/pitch load "
                     "carries no independent forward signal. Keep the existing "
                     "velo-decline flag; do not add a Verducci or "
                     "pitch-count flag.")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    # ---- console echo ----
    print("=" * 70)
    print("WORKLOAD / FATIGUE OOS STUDY")
    print("=" * 70)
    print(f"gated n (workload join) = {n_total};  Verducci subset n = {n_verd}")
    print(f"\nTHE BAR -- velo-decline partial-r over BAR-A: {fmt(*velo_pr)}")
    print("\nPartial-r table:")
    show = tbl.copy()
    for c in ["raw_r", "pr_A", "p_A", "pr_B", "p_B"]:
        show[c] = show[c].map(lambda v: f"{v:+.3f}" if np.isfinite(v) else "nan")
    print(show[["feature", "raw_r", "pr_A", "p_A", "n_A", "pr_B", "p_B", "n_B"]]
          .to_string(index=False))
    print("\nVerducci jump terciles (forward FP):")
    print(verd_terc.to_string())
    print("\nLoad x velo-decline interaction terciles (forward FP):")
    print(inter_terc.to_string())
    print(f"\nWINNERS (clear both bars): {[w[0] for w in winners] or 'NONE'}")
    print(f"\nReport -> {OUT_MD}")


if __name__ == "__main__":
    main()

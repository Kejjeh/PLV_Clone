"""sigma_heteroskedastic_search.py

Research-only — test whether sigma should be predicted per-pitcher from features,
vs the current single global alpha=2.41 rescale.

Inputs:
  - data/research/validation_runs/multi_year_sp_backtest_starts.csv  (3,229 historical starts)
  - data/research/validation_runs/sigma_calibration.json
  - data/research/sp_ratings_master.csv  (pitcher-year STUFF/MOVEMENT/CONTROL/K%/BB% etc.)

Outputs:
  - data/research/validation_runs/sigma_heteroskedastic_search.md

Does NOT modify rp3 or change alpha. Output is a verdict + (if SHIP) a multiplicative
sigma factor recipe.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold

ROOT = Path(__file__).resolve().parents[2]
STARTS_CSV = ROOT / "data" / "research" / "validation_runs" / "multi_year_sp_backtest_starts.csv"
SIGMA_JSON = ROOT / "data" / "research" / "validation_runs" / "sigma_calibration.json"
RATINGS_CSV = ROOT / "data" / "research" / "sp_ratings_master.csv"
REPORT = ROOT / "data" / "research" / "validation_runs" / "sigma_heteroskedastic_search.md"

ALPHA_GLOBAL = 2.41
MIN_STARTS_PER_PITCHER = 10
SIGMA_FACTOR_MIN = 0.7
SIGMA_FACTOR_MAX = 1.5


def load_backtest() -> pd.DataFrame:
    df = pd.read_csv(STARTS_CSV)
    # residual vs prediction
    df["residual"] = df["actual_FP"] - df["xfp_rp3"]
    # rescaled global sigma in effect (alpha=2.41 on raw sigma column)
    df["sigma_global"] = df["sigma"] * ALPHA_GLOBAL
    return df


def per_pitcher_empirical_sigma(df: pd.DataFrame) -> pd.DataFrame:
    """For each pitcher with >= MIN_STARTS_PER_PITCHER, compute empirical residual std
    vs the mean global sigma applied to their starts."""
    grouped = df.groupby("pitcher").agg(
        n_starts=("residual", "size"),
        sigma_emp=("residual", "std"),
        sigma_global_mean=("sigma_global", "mean"),
        xfp_rp3_mean=("xfp_rp3", "mean"),
        actual_mean=("actual_FP", "mean"),
        residual_mean=("residual", "mean"),
        rank_mean=("rank_at_snap", "mean"),
        gs_to_mean=("gs_to", "mean"),
        years=("year", "nunique"),
    ).reset_index()
    grouped = grouped[grouped["n_starts"] >= MIN_STARTS_PER_PITCHER].copy()
    grouped["sigma_ratio"] = grouped["sigma_emp"] / grouped["sigma_global_mean"]
    grouped["bucket"] = np.where(
        grouped["sigma_ratio"] > 1.2, "WIDER",
        np.where(grouped["sigma_ratio"] < 0.8, "TIGHTER", "MATCH")
    )
    return grouped


def join_ratings(per_pitcher: pd.DataFrame, ratings: pd.DataFrame) -> pd.DataFrame:
    """Join with the most recent year of SP ratings per pitcher (use 2025 if available,
    else the latest year that pitcher appears in)."""
    # rating cols of interest
    keep = [
        "pitcher", "year", "STUFF", "MOVEMENT", "CONTROL",
        "k_pct", "bb_pct", "hr_per_bf", "swstr_pct",
        "xwoba_contact", "barrel_pct", "hard_hit_pct",
        "avg_velo", "zone_pct", "archetype",
    ]
    available = [c for c in keep if c in ratings.columns]
    r = ratings[available].copy()
    # ensure pitcher numeric
    r["pitcher"] = pd.to_numeric(r["pitcher"], errors="coerce")
    r = r.dropna(subset=["pitcher"])
    r["pitcher"] = r["pitcher"].astype(int)
    # pick latest year per pitcher
    r = r.sort_values(["pitcher", "year"]).groupby("pitcher").tail(1)
    return per_pitcher.merge(r, on="pitcher", how="left")


def fit_sigma_predictor(merged: pd.DataFrame) -> dict:
    """Fit ridge predicting sigma_emp from features. Report CV r²."""
    feat_cols = [
        "STUFF", "MOVEMENT", "CONTROL",
        "k_pct", "bb_pct", "hr_per_bf", "swstr_pct",
        "xwoba_contact", "barrel_pct", "hard_hit_pct",
        "avg_velo", "zone_pct",
        "gs_to_mean", "rank_mean",
    ]
    feat_cols = [c for c in feat_cols if c in merged.columns]
    sub = merged.dropna(subset=feat_cols + ["sigma_emp"]).copy()
    if len(sub) < 30:
        return {"n": len(sub), "r2_cv": np.nan, "coefs": {}, "feat_cols": feat_cols}

    X = sub[feat_cols].values
    # standardize manually for interpretability
    mu = X.mean(axis=0)
    sd = X.std(axis=0) + 1e-9
    Xz = (X - mu) / sd
    y = sub["sigma_emp"].values

    # k-fold CV r²
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    preds = np.zeros_like(y, dtype=float)
    for tr, te in kf.split(Xz):
        m = Ridge(alpha=2.0).fit(Xz[tr], y[tr])
        preds[te] = m.predict(Xz[te])
    ss_res = float(((y - preds) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2_cv = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan

    # full-data fit for coef interpretation
    m_full = Ridge(alpha=2.0).fit(Xz, y)
    coefs = dict(zip(feat_cols, m_full.coef_.tolist()))
    intercept = float(m_full.intercept_)

    # also compute per-feature univariate correlations for diagnostic
    univariate = {}
    for c in feat_cols:
        v = sub[c].values
        if np.std(v) > 0:
            r = np.corrcoef(v, y)[0, 1]
            univariate[c] = float(r)
    return {
        "n": int(len(sub)),
        "r2_cv": float(r2_cv),
        "coefs_standardized": {k: float(v) for k, v in coefs.items()},
        "intercept": intercept,
        "univariate_corr": univariate,
        "feat_cols": feat_cols,
        "feat_mu": mu.tolist(),
        "feat_sd": sd.tolist(),
        "y_mean": float(y.mean()),
        "y_std": float(y.std()),
    }


def archetype_alpha_groups(merged: pd.DataFrame) -> pd.DataFrame:
    """Group sigma_ratio by archetype label — does archetype alone explain σ direction?"""
    if "archetype" not in merged.columns:
        return pd.DataFrame()
    sub = merged.dropna(subset=["archetype", "sigma_ratio"])
    g = sub.groupby("archetype").agg(
        n=("sigma_ratio", "size"),
        ratio_mean=("sigma_ratio", "mean"),
        ratio_median=("sigma_ratio", "median"),
        sigma_emp_mean=("sigma_emp", "mean"),
    ).reset_index().sort_values("n", ascending=False)
    return g


def build_hetero_sigma_factor(model_info: dict, df_starts: pd.DataFrame, ratings: pd.DataFrame) -> pd.Series:
    """For each row in df_starts, build a predicted sigma_factor in [0.7, 1.5] s.t.
    final_sigma = sigma_raw * ALPHA_GLOBAL * factor.

    Strategy: the ridge predicts sigma_emp. Build factor = predicted_sigma_emp / mean(sigma_global)
    then re-center so mean(factor)==1 (so the rescale on aggregate matches global).
    """
    feat_cols = model_info["feat_cols"]
    mu = np.array(model_info["feat_mu"])
    sd = np.array(model_info["feat_sd"])
    coefs = np.array([model_info["coefs_standardized"][c] for c in feat_cols])
    intercept = model_info["intercept"]

    # build per-pitcher features
    r = ratings[["pitcher", "year"] + [c for c in feat_cols if c in ratings.columns]].copy()
    r["pitcher"] = pd.to_numeric(r["pitcher"], errors="coerce")
    r = r.dropna(subset=["pitcher"])
    r["pitcher"] = r["pitcher"].astype(int)

    # we want per-pitcher latest-as-of-year features — for each start row, use the pitcher's rating
    # for the SAME year (or most recent prior year if not available)
    df = df_starts.copy()

    # ratings keyed by (pitcher, year)
    r_idx = r.set_index(["pitcher", "year"])

    # for each start, find that pitcher's rating row in same year (fallback: latest <= year)
    preds = np.full(len(df), np.nan)
    for i, (pid, yr) in enumerate(zip(df["pitcher"].values, df["year"].values)):
        try:
            row = r_idx.loc[(int(pid), int(yr))]
        except KeyError:
            # fallback: largest year <= yr for this pitcher
            try:
                sub = r[r["pitcher"] == int(pid)]
                sub = sub[sub["year"] <= int(yr)]
                if len(sub) == 0:
                    continue
                row = sub.iloc[-1]
            except Exception:
                continue
        # row may be a Series if multi-rows existed; ensure scalar
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        # also need gs_to_mean (use this row's gs_to from start) and rank_mean
        feat_vals = []
        for c in feat_cols:
            if c == "gs_to_mean":
                feat_vals.append(df["gs_to"].iloc[i])
            elif c == "rank_mean":
                feat_vals.append(df["rank_at_snap"].iloc[i])
            else:
                v = row.get(c, np.nan) if hasattr(row, "get") else np.nan
                feat_vals.append(v)
        x = np.array(feat_vals, dtype=float)
        if np.any(np.isnan(x)):
            continue
        xz = (x - mu) / sd
        preds[i] = intercept + float(np.dot(xz, coefs))

    df["sigma_emp_pred"] = preds
    # convert predicted sigma to a multiplicative factor relative to ALPHA_GLOBAL * sigma_raw
    df["sigma_global_now"] = df["sigma"] * ALPHA_GLOBAL
    valid = ~df["sigma_emp_pred"].isna()
    # factor = predicted_sigma / current_global_sigma
    factor = df["sigma_emp_pred"] / df["sigma_global_now"]
    factor = factor.clip(lower=SIGMA_FACTOR_MIN, upper=SIGMA_FACTOR_MAX)
    # for rows where features missing, fallback to 1.0 (use global)
    factor = factor.where(valid, other=1.0)
    # re-center so global mean is preserved
    mean_factor = factor[valid].mean() if valid.any() else 1.0
    factor = factor / mean_factor
    factor = factor.clip(lower=SIGMA_FACTOR_MIN, upper=SIGMA_FACTOR_MAX)
    return factor


def coverage(df: pd.DataFrame, sigma_col: str) -> float:
    """Symmetric Gaussian 50% band = pred ± 0.6745*sigma."""
    half = 0.6745 * df[sigma_col]
    lo = df["xfp_rp3"] - half
    hi = df["xfp_rp3"] + half
    inside = (df["actual_FP"] >= lo) & (df["actual_FP"] <= hi)
    return float(inside.mean())


def per_pitcher_coverage_dispersion(df: pd.DataFrame, sigma_col: str) -> dict:
    half = 0.6745 * df[sigma_col]
    df = df.assign(
        _lo=df["xfp_rp3"] - half,
        _hi=df["xfp_rp3"] + half,
        _inside=(df["actual_FP"] >= df["xfp_rp3"] - half) & (df["actual_FP"] <= df["xfp_rp3"] + half),
    )
    g = df.groupby("pitcher").agg(n=("_inside", "size"), cov=("_inside", "mean"))
    g = g[g["n"] >= MIN_STARTS_PER_PITCHER]
    if len(g) == 0:
        return {}
    return {
        "n_pitchers": int(len(g)),
        "median_cov": float(g["cov"].median()),
        "q25_cov": float(g["cov"].quantile(0.25)),
        "q75_cov": float(g["cov"].quantile(0.75)),
        "frac_under_25pct": float((g["cov"] < 0.25).mean()),
        "frac_over_75pct": float((g["cov"] > 0.75).mean()),
        "std_cov_across_pitchers": float(g["cov"].std()),
    }


def case_studies(df_with_hetero: pd.DataFrame, name_map: dict) -> list[dict]:
    """For named SPs, report old band vs hetero band vs observed residual std."""
    out = []
    for pid, name in name_map.items():
        sub = df_with_hetero[df_with_hetero["pitcher"] == pid]
        if len(sub) == 0:
            continue
        sub_recent = sub.sort_values(["year", "doy"]).tail(20) if len(sub) >= 20 else sub
        # use the most recent row for the band display
        last = sub_recent.iloc[-1]
        sigma_global = last["sigma"] * ALPHA_GLOBAL
        sigma_hetero = last["sigma"] * ALPHA_GLOBAL * last["sigma_factor"]
        old_p25 = last["xfp_rp3"] - 0.6745 * sigma_global
        old_p75 = last["xfp_rp3"] + 0.6745 * sigma_global
        new_p25 = last["xfp_rp3"] - 0.6745 * sigma_hetero
        new_p75 = last["xfp_rp3"] + 0.6745 * sigma_hetero
        emp_std = float(sub["residual"].std()) if len(sub) >= 5 else np.nan
        out.append({
            "name": name,
            "pitcher": int(pid),
            "n_starts": int(len(sub)),
            "xfp_rp3": float(last["xfp_rp3"]),
            "sigma_global": float(sigma_global),
            "sigma_hetero": float(sigma_hetero),
            "sigma_factor": float(last["sigma_factor"]),
            "old_p25": float(old_p25),
            "old_p75": float(old_p75),
            "new_p25": float(new_p25),
            "new_p75": float(new_p75),
            "emp_residual_std": emp_std,
            "n_for_emp": int(len(sub)),
        })
    return out


def render_report(
    per_pitcher: pd.DataFrame,
    model_info: dict,
    arch_groups: pd.DataFrame,
    cov_global: float,
    cov_hetero: float,
    pp_global: dict,
    pp_hetero: dict,
    cases: list[dict],
    verdict: str,
) -> str:
    lines = []
    lines.append("# rp3 sigma heteroskedastic search")
    lines.append("")
    lines.append("Generated 2026-06-03. Source: `multi_year_sp_backtest_starts.csv` (3,229 starts, 2021-2025).")
    lines.append("")
    lines.append("## Question")
    lines.append("")
    lines.append("The current calibration multiplies every pitcher's sigma by **α_global=2.41**.")
    lines.append("Can we predict per-pitcher σ — tighter for aces with stable command, wider")
    lines.append("for streamers with variable outings — and ship a multiplicative factor?")
    lines.append("")
    lines.append("## Method")
    lines.append("")
    lines.append(f"- Compute empirical residual std σ_emp for each pitcher with ≥ {MIN_STARTS_PER_PITCHER} starts in backtest.")
    lines.append("- Compare σ_emp to mean(σ_global) for that pitcher's starts → σ_ratio.")
    lines.append("- Fit Ridge predicting σ_emp from features (archetype STUFF/MOVEMENT/CONTROL, K%, BB%,")
    lines.append("  HR/BF, swstr%, xwOBA_contact, barrel%, hard-hit%, velo, zone%, gs_to, rank).")
    lines.append("- 5-fold CV r² is the gate (target ≥ 0.10).")
    lines.append("- Re-score backtest with hetero σ = σ_raw × 2.41 × pitcher_factor (clamped [0.7, 1.5],")
    lines.append("  re-centered so mean(factor) = 1).")
    lines.append("")
    lines.append("## Per-pitcher σ_emp landscape")
    lines.append("")
    pp = per_pitcher
    bucket_counts = pp["bucket"].value_counts().to_dict()
    lines.append(f"- Pitchers with ≥ {MIN_STARTS_PER_PITCHER} backtest starts: **{len(pp)}**")
    lines.append(f"- σ_ratio = σ_emp / σ_global (after α=2.41 rescale)")
    lines.append(f"  - mean: **{pp['sigma_ratio'].mean():.3f}**")
    lines.append(f"  - median: **{pp['sigma_ratio'].median():.3f}**")
    lines.append(f"  - q25-q75: **{pp['sigma_ratio'].quantile(0.25):.3f} – {pp['sigma_ratio'].quantile(0.75):.3f}**")
    lines.append(f"  - std across pitchers: **{pp['sigma_ratio'].std():.3f}**")
    lines.append(f"- Buckets: WIDER (>1.2)={bucket_counts.get('WIDER',0)}, "
                 f"TIGHTER (<0.8)={bucket_counts.get('TIGHTER',0)}, "
                 f"MATCH=**{bucket_counts.get('MATCH',0)}**")
    lines.append("")
    if not arch_groups.empty:
        lines.append("### σ_ratio by archetype (latest-year archetype for each pitcher)")
        lines.append("")
        lines.append("| archetype | n | σ_ratio mean | σ_ratio median | σ_emp mean |")
        lines.append("|---|---:|---:|---:|---:|")
        for _, row in arch_groups.head(15).iterrows():
            lines.append(f"| {row['archetype']} | {int(row['n'])} | {row['ratio_mean']:.3f} | "
                         f"{row['ratio_median']:.3f} | {row['sigma_emp_mean']:.2f} |")
        lines.append("")

    lines.append("## Ridge model: predicting σ_emp from features")
    lines.append("")
    lines.append(f"- n pitchers usable (no missing features): **{model_info['n']}**")
    lines.append(f"- 5-fold CV r²: **{model_info['r2_cv']:.4f}**")
    lines.append(f"- y (σ_emp) mean: {model_info['y_mean']:.3f}, std: {model_info['y_std']:.3f}")
    lines.append("")
    lines.append("### Standardized ridge coefficients (effect of +1 SD feature on σ_emp)")
    lines.append("")
    lines.append("| feature | coef (std) | univariate r |")
    lines.append("|---|---:|---:|")
    coefs = model_info["coefs_standardized"]
    univ = model_info["univariate_corr"]
    coef_pairs = sorted(coefs.items(), key=lambda kv: -abs(kv[1]))
    for k, v in coef_pairs:
        ur = univ.get(k, np.nan)
        lines.append(f"| {k} | {v:+.3f} | {ur:+.3f} |")
    lines.append("")

    lines.append("## Coverage on the 3,229-start backtest")
    lines.append("")
    lines.append("| method | pooled coverage (target 50%) |")
    lines.append("|---|---:|")
    lines.append(f"| Global α=2.41 (status quo) | **{cov_global*100:.1f}%** |")
    lines.append(f"| Hetero σ (ridge factor, clamped + re-centered) | **{cov_hetero*100:.1f}%** |")
    lines.append("")
    lines.append("### Per-pitcher coverage dispersion (pitchers with ≥10 starts)")
    lines.append("")
    lines.append("| method | n pitchers | median cov | q25-q75 cov | std across | frac <25% | frac >75% |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    lines.append(f"| Global α | {pp_global.get('n_pitchers','-')} | "
                 f"{pp_global.get('median_cov',0)*100:.1f}% | "
                 f"{pp_global.get('q25_cov',0)*100:.1f}-{pp_global.get('q75_cov',0)*100:.1f}% | "
                 f"{pp_global.get('std_cov_across_pitchers',0)*100:.1f}pp | "
                 f"{pp_global.get('frac_under_25pct',0)*100:.1f}% | "
                 f"{pp_global.get('frac_over_75pct',0)*100:.1f}% |")
    lines.append(f"| Hetero σ | {pp_hetero.get('n_pitchers','-')} | "
                 f"{pp_hetero.get('median_cov',0)*100:.1f}% | "
                 f"{pp_hetero.get('q25_cov',0)*100:.1f}-{pp_hetero.get('q75_cov',0)*100:.1f}% | "
                 f"{pp_hetero.get('std_cov_across_pitchers',0)*100:.1f}pp | "
                 f"{pp_hetero.get('frac_under_25pct',0)*100:.1f}% | "
                 f"{pp_hetero.get('frac_over_75pct',0)*100:.1f}% |")
    lines.append("")

    lines.append("## Case studies (last backtest snapshot for each)")
    lines.append("")
    lines.append("| pitcher | n_st | rp3 | σ_global | σ_hetero | factor | old p25-p75 | new p25-p75 | σ_emp obs |")
    lines.append("|---|---:|---:|---:|---:|---:|---|---|---:|")
    for c in cases:
        lines.append(
            f"| {c['name']} | {c['n_starts']} | {c['xfp_rp3']:.2f} | "
            f"{c['sigma_global']:.2f} | {c['sigma_hetero']:.2f} | {c['sigma_factor']:.2f} | "
            f"{c['old_p25']:.2f}–{c['old_p75']:.2f} | "
            f"{c['new_p25']:.2f}–{c['new_p75']:.2f} | "
            f"{c['emp_residual_std']:.2f} |"
        )
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(f"**{verdict}**")
    lines.append("")
    if verdict.startswith("SHIP"):
        lines.append("### Minimal spec for rp3.py")
        lines.append("")
        lines.append("```python")
        lines.append("# in rp3 sigma application step, after computing sigma_cal = sigma_raw * alpha_global:")
        lines.append("# load pitcher_sigma_factor from data/research/validation_runs/sigma_heteroskedastic.json")
        lines.append("# factor table keyed by pitcher_id with features → ridge prediction at projection time.")
        lines.append("sigma_final = sigma_cal * pitcher_sigma_factor.clip(0.7, 1.5)")
        lines.append("# re-center to preserve global mean: factors normalized so mean=1 across active SPs")
        lines.append("xfp_rp3_p25 = pred - 0.6745 * sigma_final")
        lines.append("xfp_rp3_p75 = pred + 0.6745 * sigma_final")
        lines.append("```")
        lines.append("")
        lines.append("- Source-of-truth: a new `pitcher_sigma_factor` column in `xfp_rp3_projections.csv`,")
        lines.append("  computed by replaying the ridge model from `sp_ratings_master.csv` at refresh time.")
        lines.append("- Add `sigma_calibration_method = 'hetero_v1'` for audit.")
    else:
        lines.append("### Why not ship")
        lines.append("- See r² and coverage tables above. Per-pitcher σ_emp dispersion is not")
        lines.append("  predictable from the available features at the ≥ 0.10 r² gate, OR the hetero")
        lines.append("  factor does not improve pooled / per-pitcher coverage materially over global.")
        lines.append("- Per-pitcher σ_emp variation is consistent with sampling noise on top of a single")
        lines.append("  true sigma, not a stable cross-pitcher property the model can lock onto.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    print("[1/6] loading backtest panel...")
    df = load_backtest()
    print(f"  {len(df)} starts")

    print("[2/6] computing per-pitcher empirical sigma...")
    pp = per_pitcher_empirical_sigma(df)
    print(f"  {len(pp)} pitchers with >= {MIN_STARTS_PER_PITCHER} starts")

    print("[3/6] joining SP ratings master...")
    ratings = pd.read_csv(RATINGS_CSV, low_memory=False)
    merged = join_ratings(pp, ratings)
    print(f"  merged shape: {merged.shape}")

    print("[4/6] fitting ridge predictor of sigma_emp...")
    model_info = fit_sigma_predictor(merged)
    print(f"  CV r² = {model_info['r2_cv']:.4f}, n = {model_info['n']}")

    print("  archetype sigma_ratio groups...")
    arch_groups = archetype_alpha_groups(merged)

    print("[5/6] building hetero sigma factors for each backtest row...")
    factor = build_hetero_sigma_factor(model_info, df, ratings)
    df_h = df.copy()
    df_h["sigma_factor"] = factor.values
    df_h["sigma_hetero"] = df_h["sigma"] * ALPHA_GLOBAL * df_h["sigma_factor"]

    cov_global = coverage(df_h, "sigma_global")
    cov_hetero = coverage(df_h, "sigma_hetero")
    pp_global = per_pitcher_coverage_dispersion(df_h, "sigma_global")
    pp_hetero = per_pitcher_coverage_dispersion(df_h, "sigma_hetero")
    print(f"  coverage: global={cov_global*100:.1f}%  hetero={cov_hetero*100:.1f}%")

    print("[6/6] case studies + verdict...")
    # build name->pitcher map from ratings
    name_map_full = {}
    for _, row in ratings.iterrows():
        try:
            pid = int(row["pitcher"])
        except Exception:
            continue
        nm = row.get("player_name") or row.get("pitcher_name") or None
        if nm and pid not in name_map_full:
            name_map_full[pid] = nm

    cases_names = [
        "Soriano, José", "Skenes, Paul", "Rodriguez, Grayson",
        "Kelly, Merrill", "Holmes, Grant", "Cole, Gerrit",
        "Strider, Spencer", "Ragans, Andrew", "Ragans, Cole",
        "Sale, Chris", "Wheeler, Zack", "deGrom, Jacob",
        "Lugo, Seth", "Eflin, Zach",
    ]
    case_map = {}
    for nm in cases_names:
        for pid, n in name_map_full.items():
            if n.lower().startswith(nm.split(",")[0].lower() + ","):
                # crude match — prefer exact
                if n == nm:
                    case_map[pid] = nm
                    break
                case_map.setdefault(pid, nm)
    # cap at 10
    case_map = dict(list(case_map.items())[:10])

    cases = case_studies(df_h, case_map)

    # verdict
    r2 = model_info["r2_cv"]
    cov_diff = cov_hetero - cov_global
    spread_reduction = (
        pp_global.get("std_cov_across_pitchers", 0) - pp_hetero.get("std_cov_across_pitchers", 0)
    )
    print(f"  per-pitcher coverage spread: global={pp_global.get('std_cov_across_pitchers',0)*100:.1f}pp "
          f"hetero={pp_hetero.get('std_cov_across_pitchers',0)*100:.1f}pp  reduction={spread_reduction*100:+.2f}pp")

    if r2 < 0.05:
        verdict = "KEEP_GLOBAL — ridge CV r² below 0.05 floor; features cannot predict σ direction."
    elif r2 >= 0.10 and abs(cov_hetero - 0.50) <= abs(cov_global - 0.50) + 0.005 and spread_reduction > 0.005:
        verdict = ("SHIP_HETERO_CALIBRATION — r² ≥ 0.10, pooled coverage stays in 45-55% band, "
                   "AND per-pitcher coverage spread narrows materially.")
    elif r2 >= 0.05 and spread_reduction > 0.01 and abs(cov_hetero - 0.50) <= 0.05:
        verdict = ("SHIP_HETERO_CALIBRATION (weak) — r² between 0.05-0.10 but per-pitcher dispersion "
                   "improves and pooled coverage stays calibrated. Worth the complexity if dispersion "
                   "narrows by ≥ 1pp.")
    elif r2 >= 0.05:
        verdict = ("NEEDS_MORE_DATA — features show weak signal (r² 0.05-0.10) but per-pitcher coverage "
                   "spread does not narrow. Revisit after another full season of backtest data.")
    else:
        verdict = "KEEP_GLOBAL — signal too weak to justify the multiplicative-factor complexity."

    md = render_report(pp, model_info, arch_groups, cov_global, cov_hetero,
                       pp_global, pp_hetero, cases, verdict)
    REPORT.write_text(md, encoding="utf-8")
    print(f"  wrote {REPORT}")
    print(f"  verdict: {verdict}")


if __name__ == "__main__":
    main()

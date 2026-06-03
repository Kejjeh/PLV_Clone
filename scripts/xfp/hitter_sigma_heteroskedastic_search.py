"""hitter_sigma_heteroskedastic_search.py

Research-only — test whether hitter sigma should be predicted per-hitter from
features, vs the current single global sigma used by rh3.

Pattern mirrors sigma_heteroskedastic_search.py (SP attempt). The SP attempt
failed (CV r2 = -0.218, n=138 pitchers, ~25 starts each). The hitter sample is
~5x larger (~641 batters, ~150+ games each), and the per-PA structure is finer
grain, so the signal-to-noise ratio is dramatically better.

Inputs:
  - data/research/validation_runs/hitter_boom_bust_panel.parquet (245k batter-games)
  - data/research/hitter_ratings_master.csv (batter-year archetype + Statcast)

Outputs:
  - data/research/validation_runs/hitter_sigma_heteroskedastic_search.md

Method per the SP pattern:
  - For each batter with >= 100 games, compute residual std of (fp_proxy/PA -
    batter_career_mean_fp_per_pa). This is sigma_emp per batter (per-PA scale).
  - Global sigma_g = pooled residual std across all batter-games on per-PA scale.
  - sigma_ratio = sigma_emp / global_sigma per batter.
  - Fit Ridge predicting sigma_emp from hitter features (CONTACT/POWER/DISCIPLINE
    20-80 ratings, k_pct, bb_pct, iso, hard_hit_pct, barrel_pct, sweet_spot_pct,
    chase_pct, contact_pct, ev90, sprint_speed, mean_lineup_spot).
  - 5-fold CV r2 is the gate (target >= 0.10).
  - Build hetero sigma factor (clamped [0.7, 1.5], re-centered to mean=1) and
    test coverage on the full game panel.

Does NOT modify rh3 or any production data.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "research" / "validation_runs" / "hitter_boom_bust_panel.parquet"
RATINGS = ROOT / "data" / "research" / "hitter_ratings_master.csv"
REPORT = ROOT / "data" / "research" / "validation_runs" / "hitter_sigma_heteroskedastic_search.md"

MIN_GAMES_PER_BATTER = 100
SIGMA_FACTOR_MIN = 0.7
SIGMA_FACTOR_MAX = 1.5

FEAT_COLS = [
    # archetype 20-80 ratings
    "CONTACT", "POWER", "DISCIPLINE",
    # rate skills
    "k_pct", "bb_pct", "iso", "hard_hit_pct", "barrel_pct", "sweet_spot_pct",
    "chase_pct", "contact_pct", "ev90", "sprint_speed",
    "xwoba_on_contact",
    # role / opportunity
    "mean_lineup_spot",
]


def load_panel() -> pd.DataFrame:
    df = pd.read_parquet(PANEL)
    df = df.dropna(subset=["fp_proxy", "PA"])
    df["fp_per_pa"] = df["fp_proxy"].astype(float) / df["PA"].astype(float)
    return df


def per_batter_empirical_sigma(df: pd.DataFrame) -> pd.DataFrame:
    """For each batter with >= MIN_GAMES_PER_BATTER games, compute the residual
    std of (fp_per_pa - batter_career_mean_fp_per_pa). PA-weighted variance to
    respect the per-PA semantics of rh3 sigma.
    """
    # batter career mean fp/PA (weighted by PA)
    grouped = df.groupby("batter")
    out = []
    for bid, sub in grouped:
        n = len(sub)
        if n < MIN_GAMES_PER_BATTER:
            continue
        # weighted mean per PA
        w = sub["PA"].astype(float).values
        x = sub["fp_per_pa"].astype(float).values
        mean_w = float(np.average(x, weights=w))
        # weighted residual std
        var_w = float(np.average((x - mean_w) ** 2, weights=w))
        sigma_emp = np.sqrt(var_w)
        # latest year of activity for ratings join
        latest_year = int(sub["year"].max())
        out.append({
            "batter": int(bid),
            "n_games": int(n),
            "total_pa": int(sub["PA"].sum()),
            "fp_per_pa_mean": mean_w,
            "sigma_emp": sigma_emp,
            "latest_year": latest_year,
        })
    pp = pd.DataFrame(out)
    return pp


def join_ratings(per_batter: pd.DataFrame, ratings: pd.DataFrame) -> pd.DataFrame:
    """Join with the most-recent-year row of hitter ratings per batter."""
    keep = ["batter", "year", "player_name"] + [c for c in FEAT_COLS if c in ratings.columns]
    r = ratings[keep].copy()
    r["batter"] = pd.to_numeric(r["batter"], errors="coerce")
    r = r.dropna(subset=["batter"])
    r["batter"] = r["batter"].astype(int)
    r = r.sort_values(["batter", "year"]).groupby("batter").tail(1)
    return per_batter.merge(r, on="batter", how="left")


def fit_sigma_predictor(merged: pd.DataFrame) -> dict:
    feat_cols = [c for c in FEAT_COLS if c in merged.columns]
    sub = merged.dropna(subset=feat_cols + ["sigma_emp"]).copy()
    if len(sub) < 30:
        return {"n": len(sub), "r2_cv": np.nan, "feat_cols": feat_cols}

    X = sub[feat_cols].values.astype(float)
    mu = X.mean(axis=0)
    sd = X.std(axis=0) + 1e-9
    Xz = (X - mu) / sd
    y = sub["sigma_emp"].values.astype(float)

    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    preds = np.zeros_like(y, dtype=float)
    for tr, te in kf.split(Xz):
        m = Ridge(alpha=2.0).fit(Xz[tr], y[tr])
        preds[te] = m.predict(Xz[te])
    ss_res = float(((y - preds) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2_cv = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan

    m_full = Ridge(alpha=2.0).fit(Xz, y)
    coefs = dict(zip(feat_cols, m_full.coef_.tolist()))
    intercept = float(m_full.intercept_)

    univariate = {}
    for c in feat_cols:
        v = sub[c].values.astype(float)
        if np.std(v) > 0:
            univariate[c] = float(np.corrcoef(v, y)[0, 1])

    return {
        "n": int(len(sub)),
        "r2_cv": float(r2_cv),
        "coefs_standardized": coefs,
        "intercept": intercept,
        "univariate_corr": univariate,
        "feat_cols": feat_cols,
        "feat_mu": mu.tolist(),
        "feat_sd": sd.tolist(),
        "y_mean": float(y.mean()),
        "y_std": float(y.std()),
        "y_pred_for_sub": preds.tolist(),
        "y_actual_for_sub": y.tolist(),
        "sub_batters": sub["batter"].tolist(),
    }


def archetype_alpha_groups(merged: pd.DataFrame, global_sigma: float) -> pd.DataFrame:
    if "archetype" not in merged.columns:
        # join from ratings if needed
        return pd.DataFrame()
    sub = merged.dropna(subset=["archetype", "sigma_emp"]).copy()
    sub["sigma_ratio"] = sub["sigma_emp"] / global_sigma
    g = sub.groupby("archetype").agg(
        n=("sigma_ratio", "size"),
        ratio_mean=("sigma_ratio", "mean"),
        ratio_median=("sigma_ratio", "median"),
        sigma_emp_mean=("sigma_emp", "mean"),
    ).reset_index().sort_values("n", ascending=False)
    return g


def coverage_global(df: pd.DataFrame, global_sigma_per_pa: float) -> float:
    """50% band coverage per game using per-PA global sigma converted to per-game
    via the game's PA count: sigma_g = sigma_pa * sqrt(PA) (Gaussian approx).
    Actual = fp_proxy; pred = batter_career_mean_fp_per_pa * PA.
    """
    # pred per game = mean * PA, sigma per game = sigma_pa * sqrt(PA)
    half = 0.6745 * global_sigma_per_pa * np.sqrt(df["PA"].astype(float))
    pred = df["pred_fp_game"]
    lo = pred - half
    hi = pred + half
    inside = (df["fp_proxy"] >= lo) & (df["fp_proxy"] <= hi)
    return float(inside.mean())


def coverage_hetero(df: pd.DataFrame, sigma_pa_per_row: np.ndarray) -> float:
    half = 0.6745 * sigma_pa_per_row * np.sqrt(df["PA"].astype(float).values)
    pred = df["pred_fp_game"].values
    lo = pred - half
    hi = pred + half
    inside = (df["fp_proxy"].values >= lo) & (df["fp_proxy"].values <= hi)
    return float(inside.mean())


def per_batter_coverage(df: pd.DataFrame, sigma_pa_per_row: np.ndarray, min_games: int = 50) -> dict:
    half = 0.6745 * sigma_pa_per_row * np.sqrt(df["PA"].astype(float).values)
    pred = df["pred_fp_game"].values
    inside = ((df["fp_proxy"].values >= pred - half) & (df["fp_proxy"].values <= pred + half)).astype(int)
    tmp = pd.DataFrame({"batter": df["batter"].values, "_in": inside})
    g = tmp.groupby("batter").agg(n=("_in", "size"), cov=("_in", "mean"))
    g = g[g["n"] >= min_games]
    if len(g) == 0:
        return {}
    return {
        "n_batters": int(len(g)),
        "median_cov": float(g["cov"].median()),
        "q25_cov": float(g["cov"].quantile(0.25)),
        "q75_cov": float(g["cov"].quantile(0.75)),
        "std_cov": float(g["cov"].std()),
        "frac_under_25pct": float((g["cov"] < 0.25).mean()),
        "frac_over_75pct": float((g["cov"] > 0.75).mean()),
    }


def main() -> None:
    print("[1/7] loading panel + ratings...")
    df = load_panel()
    print(f"  {len(df):,} batter-games")
    ratings = pd.read_csv(RATINGS, low_memory=False)
    # also keep archetype for diagnostic
    arch_keep = ["batter", "year", "archetype"]
    arch = ratings[arch_keep].sort_values(["batter", "year"]).groupby("batter").tail(1)

    print("[2/7] per-batter empirical sigma (per-PA)...")
    pp = per_batter_empirical_sigma(df)
    print(f"  {len(pp)} batters with >= {MIN_GAMES_PER_BATTER} games")
    print(f"  sigma_emp (per PA) mean={pp['sigma_emp'].mean():.4f}  median={pp['sigma_emp'].median():.4f}")
    print(f"  q25-q75: {pp['sigma_emp'].quantile(0.25):.4f} - {pp['sigma_emp'].quantile(0.75):.4f}")

    # pooled global sigma per PA (PA-weighted across all batter-games)
    w = df["PA"].astype(float).values
    x = df["fp_per_pa"].values
    # use batter-career mean as pred per game (this is the apples-to-apples baseline)
    batter_mean = df.groupby("batter").apply(
        lambda s: np.average(s["fp_per_pa"], weights=s["PA"].astype(float)),
        include_groups=False,
    )
    df = df.merge(batter_mean.rename("batter_mean_fp_per_pa"), on="batter", how="left")
    df["pred_fp_game"] = df["batter_mean_fp_per_pa"] * df["PA"].astype(float)
    df["resid_per_pa"] = df["fp_per_pa"] - df["batter_mean_fp_per_pa"]
    global_sigma_per_pa = float(np.sqrt(np.average(df["resid_per_pa"] ** 2, weights=w)))
    print(f"  GLOBAL sigma per PA (pooled) = {global_sigma_per_pa:.4f}")

    pp["sigma_ratio"] = pp["sigma_emp"] / global_sigma_per_pa
    pp["bucket"] = np.where(
        pp["sigma_ratio"] > 1.2, "WIDER",
        np.where(pp["sigma_ratio"] < 0.8, "TIGHTER", "MATCH")
    )

    print("[3/7] joining ratings...")
    merged = join_ratings(pp, ratings)
    # also attach archetype
    merged = merged.merge(arch[["batter", "archetype"]], on="batter", how="left")
    print(f"  merged shape: {merged.shape}")

    print("[4/7] ridge predictor of sigma_emp...")
    info = fit_sigma_predictor(merged)
    print(f"  n={info['n']}  CV r2 = {info['r2_cv']:.4f}")

    arch_groups = archetype_alpha_groups(merged, global_sigma_per_pa)

    print("[5/7] building per-row hetero sigma factor...")
    feat_cols = info["feat_cols"]
    mu = np.array(info["feat_mu"])
    sd = np.array(info["feat_sd"])
    coefs = np.array([info["coefs_standardized"][c] for c in feat_cols])
    intercept = info["intercept"]

    # per-batter predicted sigma_emp (from latest-year rating row)
    rating_lookup = ratings.sort_values(["batter", "year"]).groupby("batter").tail(1)
    rating_lookup = rating_lookup[["batter"] + [c for c in feat_cols if c in rating_lookup.columns]].copy()
    rating_lookup["batter"] = pd.to_numeric(rating_lookup["batter"], errors="coerce")
    rating_lookup = rating_lookup.dropna(subset=["batter"])
    rating_lookup["batter"] = rating_lookup["batter"].astype(int)

    feat_mat = rating_lookup[feat_cols].values.astype(float)
    ok = ~np.isnan(feat_mat).any(axis=1)
    pred_sigma = np.full(len(rating_lookup), np.nan)
    Xz = (feat_mat[ok] - mu) / sd
    pred_sigma[ok] = intercept + Xz @ coefs
    rating_lookup["sigma_pred"] = pred_sigma

    # build factor per batter
    rating_lookup["factor_raw"] = rating_lookup["sigma_pred"] / global_sigma_per_pa
    factor_valid = rating_lookup["factor_raw"].dropna()
    mean_factor = float(factor_valid.mean()) if len(factor_valid) else 1.0
    rating_lookup["factor"] = (rating_lookup["factor_raw"] / mean_factor).clip(
        SIGMA_FACTOR_MIN, SIGMA_FACTOR_MAX
    )
    rating_lookup["factor"] = rating_lookup["factor"].fillna(1.0)

    # broadcast to panel
    df = df.merge(rating_lookup[["batter", "factor", "sigma_pred"]], on="batter", how="left")
    df["factor"] = df["factor"].fillna(1.0)
    df["sigma_hetero_per_pa"] = global_sigma_per_pa * df["factor"]

    print("[6/7] coverage tests...")
    sigma_global_arr = np.full(len(df), global_sigma_per_pa)
    cov_g = coverage_hetero(df, sigma_global_arr)
    cov_h = coverage_hetero(df, df["sigma_hetero_per_pa"].values)
    print(f"  coverage GLOBAL  = {cov_g*100:.2f}%")
    print(f"  coverage HETERO  = {cov_h*100:.2f}%")

    pp_g = per_batter_coverage(df, sigma_global_arr)
    pp_h = per_batter_coverage(df, df["sigma_hetero_per_pa"].values)
    print(f"  per-batter cov spread:  global std={pp_g.get('std_cov',0)*100:.2f}pp  "
          f"hetero std={pp_h.get('std_cov',0)*100:.2f}pp")

    print("[7/7] case studies + verdict...")
    case_names = [
        "Eugenio Suárez", "Giancarlo Stanton", "Kyle Schwarber",
        "Luis Arraez", "Spencer Steer", "Bo Bichette",
        "Juan Soto", "Aaron Judge",
        "Ronald Acuña Jr.", "Bobby Witt Jr.",
    ]
    name_to_bid = (
        ratings[["batter", "player_name"]].dropna()
        .drop_duplicates("player_name").set_index("player_name")["batter"].to_dict()
    )
    cases = []
    for nm in case_names:
        # try a few name variants
        candidates = [nm]
        # strip accents fallback
        candidates.append(nm.replace("ñ", "n").replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u"))
        bid = None
        for c in candidates:
            if c in name_to_bid:
                bid = int(name_to_bid[c])
                break
        if bid is None:
            # substring match
            for k, v in name_to_bid.items():
                if k.lower().startswith(nm.split()[0].lower()) and nm.split()[-1].lower() in k.lower():
                    bid = int(v)
                    nm = k
                    break
        if bid is None:
            continue
        row_pp = pp[pp["batter"] == bid]
        row_rl = rating_lookup[rating_lookup["batter"] == bid]
        if len(row_pp) == 0 or len(row_rl) == 0:
            continue
        sigma_emp_obs = float(row_pp["sigma_emp"].iloc[0])
        n_games = int(row_pp["n_games"].iloc[0])
        factor = float(row_rl["factor"].iloc[0])
        sigma_hetero = global_sigma_per_pa * factor
        # build a "typical game" band (4 PA, batter mean)
        batter_pred_fp_per_pa = float(row_pp["fp_per_pa_mean"].iloc[0])
        typical_pa = 4.0
        pred_game = batter_pred_fp_per_pa * typical_pa
        half_g = 0.6745 * global_sigma_per_pa * np.sqrt(typical_pa)
        half_h = 0.6745 * sigma_hetero * np.sqrt(typical_pa)
        cases.append({
            "name": nm, "batter": bid, "n_games": n_games,
            "pred_per_pa": batter_pred_fp_per_pa,
            "pred_game": pred_game,
            "sigma_global_pa": global_sigma_per_pa,
            "sigma_hetero_pa": sigma_hetero,
            "factor": factor,
            "old_p25_g": pred_game - half_g, "old_p75_g": pred_game + half_g,
            "new_p25_g": pred_game - half_h, "new_p75_g": pred_game + half_h,
            "sigma_emp_obs": sigma_emp_obs,
        })

    # rank top features by |std coef|
    coef_pairs = sorted(info["coefs_standardized"].items(), key=lambda kv: -abs(kv[1]))
    top5 = coef_pairs[:5]

    r2 = info["r2_cv"]
    cov_diff = cov_h - cov_g
    spread_red = pp_g.get("std_cov", 0) - pp_h.get("std_cov", 0)

    if r2 < 0.05:
        verdict = "KEEP_GLOBAL — ridge CV r2 below 0.05 floor; features cannot predict per-hitter sigma direction."
    elif r2 >= 0.10 and abs(cov_h - 0.50) <= abs(cov_g - 0.50) + 0.005 and spread_red > 0.005:
        verdict = ("SHIP_HETERO_FOR_HITTERS — CV r2 >= 0.10, pooled coverage stays in band, "
                   "per-batter coverage spread narrows materially.")
    elif r2 >= 0.05 and spread_red > 0.01 and abs(cov_h - 0.50) <= 0.05:
        verdict = ("SHIP_HETERO_FOR_HITTERS (weak) — r2 0.05-0.10 but per-batter dispersion improves "
                   "and pooled coverage stays calibrated.")
    elif r2 >= 0.05:
        verdict = ("NEEDS_MORE_DATA — features show weak signal (r2 0.05-0.10) but per-batter coverage "
                   "spread does not narrow. Revisit after more data.")
    else:
        verdict = "KEEP_GLOBAL — signal too weak to justify hetero-sigma complexity."

    # write report
    lines: list[str] = []
    lines.append("# rh3 hitter sigma heteroskedastic search")
    lines.append("")
    lines.append("Generated 2026-06-03. Source: `hitter_boom_bust_panel.parquet` (245,712 batter-games, 2018-2025).")
    lines.append("")
    lines.append("## Question")
    lines.append("")
    lines.append("The current rh3 calibration uses a quartile-binned sigma indexed by split_day +")
    lines.append("predicted-quartile — effectively a near-global per-PA sigma (~0.103 FP/PA). The SP")
    lines.append("attempt (`sigma_heteroskedastic_search.md`) FAILED at CV r2=-0.218 because each pitcher")
    lines.append("has only ~25 starts. Hitters get ~600 PA/season — 25x the per-player sample. Can we")
    lines.append("predict per-hitter sigma from features and ship a multiplicative factor?")
    lines.append("")
    lines.append("## Method")
    lines.append("")
    lines.append(f"- Compute residual std of fp_per_pa vs each batter's career mean (PA-weighted)")
    lines.append(f"  for batters with >= {MIN_GAMES_PER_BATTER} games. This is `sigma_emp` per batter.")
    lines.append(f"- Global pooled per-PA sigma across all batter-games is the baseline.")
    lines.append(f"- Ridge predicts `sigma_emp` from {len(feat_cols)} hitter features. 5-fold CV r2.")
    lines.append(f"- Coverage tested on 245k games with sigma_per_game = sigma_pa * sqrt(PA),")
    lines.append(f"  band = pred +/- 0.6745*sigma (target 50%).")
    lines.append("")
    lines.append("## Per-batter sigma_emp landscape")
    lines.append("")
    lines.append(f"- Batters with >= {MIN_GAMES_PER_BATTER} games: **{len(pp)}**")
    lines.append(f"- GLOBAL pooled per-PA sigma: **{global_sigma_per_pa:.4f}** FP/PA")
    lines.append(f"- sigma_emp per batter (per PA):")
    lines.append(f"  - mean: **{pp['sigma_emp'].mean():.4f}**")
    lines.append(f"  - median: **{pp['sigma_emp'].median():.4f}**")
    lines.append(f"  - q25-q75: **{pp['sigma_emp'].quantile(0.25):.4f} – {pp['sigma_emp'].quantile(0.75):.4f}**")
    lines.append(f"  - std across batters: **{pp['sigma_emp'].std():.4f}**")
    lines.append(f"- sigma_ratio = sigma_emp / global:")
    lines.append(f"  - mean: **{pp['sigma_ratio'].mean():.3f}**  median: **{pp['sigma_ratio'].median():.3f}**")
    bc = pp["bucket"].value_counts().to_dict()
    lines.append(f"- Buckets: WIDER (>1.2)={bc.get('WIDER',0)}, TIGHTER (<0.8)={bc.get('TIGHTER',0)}, "
                 f"MATCH={bc.get('MATCH',0)}")
    lines.append("")
    if not arch_groups.empty:
        lines.append("### sigma_ratio by archetype (latest-year)")
        lines.append("")
        lines.append("| archetype | n | sigma_ratio mean | sigma_ratio median | sigma_emp mean |")
        lines.append("|---|---:|---:|---:|---:|")
        for _, row in arch_groups.head(15).iterrows():
            lines.append(f"| {row['archetype']} | {int(row['n'])} | {row['ratio_mean']:.3f} | "
                         f"{row['ratio_median']:.3f} | {row['sigma_emp_mean']:.4f} |")
        lines.append("")

    lines.append("## Ridge model: predicting sigma_emp from features")
    lines.append("")
    lines.append(f"- n batters usable: **{info['n']}**")
    lines.append(f"- 5-fold CV r2: **{info['r2_cv']:.4f}**")
    lines.append(f"- y (sigma_emp) mean: {info['y_mean']:.4f}, std: {info['y_std']:.4f}")
    lines.append("")
    lines.append("### Standardized coefficients (effect of +1 SD feature on sigma_emp)")
    lines.append("")
    lines.append("| feature | coef (std) | univariate r |")
    lines.append("|---|---:|---:|")
    for k, v in coef_pairs:
        ur = info["univariate_corr"].get(k, float("nan"))
        lines.append(f"| {k} | {v:+.5f} | {ur:+.3f} |")
    lines.append("")

    lines.append("## Coverage on 245k-game panel")
    lines.append("")
    lines.append("| method | pooled coverage (target 50%) |")
    lines.append("|---|---:|")
    lines.append(f"| GLOBAL sigma (status quo proxy) | **{cov_g*100:.2f}%** |")
    lines.append(f"| HETERO sigma (ridge factor, clamped + recentered) | **{cov_h*100:.2f}%** |")
    lines.append("")
    lines.append("### Per-batter coverage dispersion (>= 50 games)")
    lines.append("")
    lines.append("| method | n batters | median cov | q25-q75 cov | std across | frac <25% | frac >75% |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for nm, d in [("Global", pp_g), ("Hetero", pp_h)]:
        lines.append(f"| {nm} | {d.get('n_batters','-')} | "
                     f"{d.get('median_cov',0)*100:.1f}% | "
                     f"{d.get('q25_cov',0)*100:.1f}-{d.get('q75_cov',0)*100:.1f}% | "
                     f"{d.get('std_cov',0)*100:.2f}pp | "
                     f"{d.get('frac_under_25pct',0)*100:.1f}% | "
                     f"{d.get('frac_over_75pct',0)*100:.1f}% |")
    lines.append("")

    lines.append("## Case studies (typical 4-PA game band)")
    lines.append("")
    lines.append("| hitter | n_games | pred_FP/PA | pred_game | factor | sigma_global_pa | sigma_hetero_pa | old p25-p75 | new p25-p75 | sigma_emp_obs |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|---|---:|")
    for c in cases:
        lines.append(
            f"| {c['name']} | {c['n_games']} | {c['pred_per_pa']:.3f} | {c['pred_game']:.2f} | "
            f"{c['factor']:.2f} | {c['sigma_global_pa']:.4f} | {c['sigma_hetero_pa']:.4f} | "
            f"{c['old_p25_g']:.2f}–{c['old_p75_g']:.2f} | "
            f"{c['new_p25_g']:.2f}–{c['new_p75_g']:.2f} | "
            f"{c['sigma_emp_obs']:.4f} |"
        )
    lines.append("")

    lines.append("## Verdict")
    lines.append("")
    lines.append(f"**{verdict}**")
    lines.append("")
    lines.append("### Headline numbers")
    lines.append(f"- CV r2 of sigma prediction: **{r2:.4f}** (gate >= 0.10 strong, >= 0.05 weak)")
    lines.append(f"- Pooled coverage: global {cov_g*100:.2f}%  -> hetero {cov_h*100:.2f}%  "
                 f"(delta {cov_diff*100:+.2f}pp)")
    lines.append(f"- Per-batter coverage spread reduction: **{spread_red*100:+.2f}pp**")
    top_feat_str = ", ".join(f"{k} ({v:+.4f})" for k, v in top5)
    lines.append(f"- Top 5 sigma predictors (std coef): {top_feat_str}")
    lines.append("")
    if verdict.startswith("SHIP"):
        lines.append("### Minimal spec for rh3.py")
        lines.append("")
        lines.append("```python")
        lines.append("# After computing per-row sigma_pa via lookup_sigma(...):")
        lines.append("# load hitter_sigma_factor from data/research/validation_runs/hitter_sigma_factors.csv")
        lines.append("# factor keyed by batter, derived from ridge(features) / global, clamped + recentered.")
        lines.append("sigma_final_per_pa = sigma_pa * batter_sigma_factor.clip(0.7, 1.5)")
        lines.append("# re-centered so mean(factor) == 1 across active batters.")
        lines.append("xfp_rh3_p25 = pred_per_pa - 0.6745 * sigma_final_per_pa")
        lines.append("xfp_rh3_p75 = pred_per_pa + 0.6745 * sigma_final_per_pa")
        lines.append("```")
    else:
        lines.append("### Why not ship")
        lines.append("- Either CV r2 is below the 0.05 floor (features can't predict sigma direction),")
        lines.append("  OR hetero coverage does not improve pooled / per-batter calibration vs global.")
        lines.append("- Per-batter sigma_emp dispersion is consistent with sampling noise + boom/bust")
        lines.append("  game-level variance on top of a single near-shared true sigma, not a stable")
        lines.append("  cross-hitter property the model can lock onto with these features.")
    lines.append("")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"  wrote {REPORT}")
    print(f"  verdict: {verdict}")


if __name__ == "__main__":
    main()

"""
Swing Timing + Miss Distance vs Fantasy Points correlation study.
Fetches the new Savant bat-tracking leaderboard (2026), joins with our
rh3 (hitter) and rp3 (SP) projections, and reports Pearson + Spearman
correlations for each metric.

Run:
    python -X utf8 scripts/xfp/research/swing_timing_miss_dist_corr.py
"""

import io
import sys
import warnings
import requests
import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

SAVANT_URL = (
    "https://baseballsavant.mlb.com/leaderboard/bat-tracking/"
    "swing-timing-miss-distance?type={type}&season[]=2026&min=10&csv=true"
)

RH3_PATH = "data/outputs/xfp_rh3_projections.csv"
RP3_PATH = "data/outputs/xfp_rp3_projections.csv"

SAVANT_METRICS = [
    "miss_distance",
    "perfect_percent",
    "flawed_percent",
    "tied_up_percent",
    "centered_percent",
    "flailed_percent",
    "early_percent",
    "on_time_percent",
    "late_percent",
    "whiff_rate",
    "competitive_percent",
    "over_percent",
    "lined_up_percent",
    "under_percent",
]

HITTER_FP_COLS = [
    "prior_fp_per_pa",      # actual realized this season
    "xfp_rh3_per_pa",       # our model projection
    "xfp_rh3_per_game",
]

SP_FP_COLS = [
    "fp_per_start_to",      # actual realized this season
    "xfp_rp3_per_start",    # our model projection
]


def fetch_savant(player_type: str) -> pd.DataFrame:
    url = SAVANT_URL.format(type=player_type)
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.rename(columns={"id": "mlbam_id"}, inplace=True)
    # coerce numeric
    for col in SAVANT_METRICS + ["n_swings"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def corr_table(df: pd.DataFrame, fp_col: str, metrics: list[str]) -> pd.DataFrame:
    rows = []
    for m in metrics:
        if m not in df.columns:
            continue
        mask = df[[m, fp_col]].notna().all(axis=1)
        sub = df.loc[mask]
        n = len(sub)
        if n < 10:
            continue
        pr, pp = stats.pearsonr(sub[m], sub[fp_col])
        sr, sp = stats.spearmanr(sub[m], sub[fp_col])
        rows.append(
            {
                "metric": m,
                "n": n,
                "pearson_r": round(pr, 3),
                "p_pearson": round(pp, 4),
                "spearman_r": round(sr, 3),
                "p_spearman": round(sp, 4),
                "sig": "***" if pp < 0.001 else ("**" if pp < 0.01 else ("*" if pp < 0.05 else "")),
            }
        )
    return pd.DataFrame(rows).sort_values("pearson_r", key=abs, ascending=False)


def section(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def print_corr(df: pd.DataFrame, label: str) -> None:
    if df.empty:
        print(f"  [{label}] no data")
        return
    print(f"\n--- {label} (n varies per metric) ---")
    print(df.to_string(index=False))


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("Fetching Savant Swing Timing + Miss Distance leaderboards...")

    batter_sv = fetch_savant("batter")
    pitcher_sv = fetch_savant("pitcher")
    print(f"  Batters: {len(batter_sv)} rows | Pitchers: {len(pitcher_sv)} rows")

    # ── HITTERS ──────────────────────────────────────────────────────────────
    section("HITTER CORRELATIONS  (Savant metrics → FP/PA or FP/game)")

    rh3 = pd.read_csv(RH3_PATH)
    rh3_cols_needed = ["batter", "player_name", "team"] + [
        c for c in HITTER_FP_COLS if c in rh3.columns
    ]
    rh3 = rh3[rh3_cols_needed].rename(columns={"batter": "mlbam_id"})

    h_df = batter_sv.merge(rh3, on="mlbam_id", how="inner")
    print(f"  Joined hitters: {len(h_df)} players")

    available_fp_h = [c for c in HITTER_FP_COLS if c in h_df.columns]
    for fp_col in available_fp_h:
        tbl = corr_table(h_df, fp_col, SAVANT_METRICS)
        print_corr(tbl, f"vs {fp_col}")

    # ── HITTER PERCENTILE BREAKDOWN: top/bottom miss_distance ─────────────
    section("HITTER MISS DISTANCE QUINTILE BREAKDOWN  (vs prior_fp_per_pa)")
    if "prior_fp_per_pa" in h_df.columns and "miss_distance" in h_df.columns:
        sub = h_df[["player_name", "team", "miss_distance", "on_time_percent",
                     "perfect_percent", "whiff_rate", "prior_fp_per_pa"]].dropna()
        sub["md_quintile"] = pd.qcut(sub["miss_distance"], 5,
                                     labels=["Q1 (best)", "Q2", "Q3", "Q4", "Q5 (worst)"])
        summary = sub.groupby("md_quintile", observed=True).agg(
            n=("player_name", "count"),
            avg_miss_dist=("miss_distance", "mean"),
            avg_on_time=("on_time_percent", "mean"),
            avg_perfect=("perfect_percent", "mean"),
            avg_whiff=("whiff_rate", "mean"),
            avg_fp_per_pa=("prior_fp_per_pa", "mean"),
        ).round(3)
        print(summary.to_string())

    # ── BEST HITTERS (lowest miss distance + high on_time) ────────────────
    section("TOP 20 HITTERS  — Best Swing Contact Quality (min 100 swings)")
    h_filtered = h_df[h_df["n_swings"] >= 100].copy()
    h_filtered["contact_score"] = (
        -h_filtered["miss_distance"].rank(pct=True)   # lower = better
        + h_filtered["perfect_percent"].rank(pct=True)
        + h_filtered["on_time_percent"].rank(pct=True)
        - h_filtered["whiff_rate"].rank(pct=True)
    ) / 4
    top_h = h_filtered.nlargest(20, "contact_score")[
        ["player_name", "team", "miss_distance", "perfect_percent",
         "on_time_percent", "whiff_rate", "prior_fp_per_pa", "xfp_rh3_per_game",
         "n_swings"]
    ].round(3)
    print(top_h.to_string(index=False))

    # ── BOTTOM 20 HITTERS (worst contact quality) ─────────────────────────
    section("BOTTOM 20 HITTERS  — Worst Swing Contact Quality (min 100 swings)")
    bot_h = h_filtered.nsmallest(20, "contact_score")[
        ["player_name", "team", "miss_distance", "perfect_percent",
         "on_time_percent", "whiff_rate", "prior_fp_per_pa", "xfp_rh3_per_game",
         "n_swings"]
    ].round(3)
    print(bot_h.to_string(index=False))

    # ── SP CORRELATIONS ───────────────────────────────────────────────────
    section("SP CORRELATIONS  (Savant batter-side metrics → pitcher FP/start)")
    print("  (Using pitcher-side leaderboard: how the metrics describe what batters")
    print("   do vs each pitcher — higher miss_distance AGAINST = better for SP)")

    rp3 = pd.read_csv(RP3_PATH)
    rp3_cols_needed = ["pitcher", "player_name"] + [
        c for c in SP_FP_COLS if c in rp3.columns
    ]
    rp3 = rp3[rp3_cols_needed].rename(columns={"pitcher": "mlbam_id"})
    # drop marcel_il rows for SP actuals analysis
    if "data_quality_tag" in rp3.columns:
        rp3_clean = rp3[rp3.get("data_quality_tag", "").str.startswith("data_driven", na=False)]
    else:
        rp3_clean = rp3.copy()

    sp_df = pitcher_sv.merge(rp3, on="mlbam_id", how="inner")
    print(f"  Joined SPs: {len(sp_df)} players")

    available_fp_sp = [c for c in SP_FP_COLS if c in sp_df.columns]
    for fp_col in available_fp_sp:
        tbl = corr_table(sp_df, fp_col, SAVANT_METRICS)
        print_corr(tbl, f"vs {fp_col}")

    # ── SP QUINTILE BREAKDOWN ─────────────────────────────────────────────
    section("SP MISS DISTANCE QUINTILE BREAKDOWN  (vs fp_per_start_to)")
    if "fp_per_start_to" in sp_df.columns and "miss_distance" in sp_df.columns:
        sub = sp_df[["player_name", "miss_distance", "on_time_percent",
                     "perfect_percent", "whiff_rate", "fp_per_start_to"]].dropna()
        sub["md_quintile"] = pd.qcut(sub["miss_distance"], 5,
                                     labels=["Q1 (best SP)", "Q2", "Q3", "Q4", "Q5 (worst SP)"])
        summary = sub.groupby("md_quintile", observed=True).agg(
            n=("player_name", "count"),
            avg_miss_dist=("miss_distance", "mean"),
            avg_on_time=("on_time_percent", "mean"),
            avg_whiff_against=("whiff_rate", "mean"),
            avg_fp_per_start=("fp_per_start_to", "mean"),
        ).round(3)
        print(summary.to_string())
        print("\n  NOTE: For SPs, higher miss_distance *against* = batters missing more")
        print("        = better for pitcher (expect positive correlation with FP)")

    # ── INCREMENTAL VALUE vs existing model ───────────────────────────────
    section("INCREMENTAL R² CHECK  (does miss_distance add above xfp_rh3_per_pa?)")
    from sklearn.linear_model import LinearRegression
    from sklearn.model_selection import cross_val_score

    if "prior_fp_per_pa" in h_df.columns and "miss_distance" in h_df.columns:
        sub = h_df[["miss_distance", "xfp_rh3_per_pa", "prior_fp_per_pa"]].dropna()
        if len(sub) >= 30:
            y = sub["prior_fp_per_pa"].values
            X_base = sub[["xfp_rh3_per_pa"]].values
            X_full = sub[["xfp_rh3_per_pa", "miss_distance"]].values
            r2_base = cross_val_score(LinearRegression(), X_base, y, cv=5,
                                      scoring="r2").mean()
            r2_full = cross_val_score(LinearRegression(), X_full, y, cv=5,
                                      scoring="r2").mean()
            print(f"  CV R²  base (xfp_rh3_per_pa only):          {r2_base:.4f}")
            print(f"  CV R²  + miss_distance:                      {r2_full:.4f}")
            print(f"  ΔR²:                                         {r2_full - r2_base:+.4f}")

    # ── SAVE CSV ──────────────────────────────────────────────────────────
    out_path = "data/research/swing_timing_miss_dist_2026.csv"
    batter_sv["type"] = "batter"
    pitcher_sv["type"] = "pitcher"
    combined = pd.concat([batter_sv, pitcher_sv], ignore_index=True)
    combined.to_csv(out_path, index=False)
    print(f"\n  Raw Savant data saved → {out_path}")

    section("DONE")


if __name__ == "__main__":
    main()

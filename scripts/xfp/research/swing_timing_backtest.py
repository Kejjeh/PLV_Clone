"""
Swing Timing + Miss Distance — Historical Backtests
Fetches 2023-2026 from Savant, joins with our multi-year FP panels,
and runs a battery of forward-predictive tests against BrownU scoring.

Hypotheses tested:
  H1  same-year r(metric, FP/PA)              — baseline
  H2  forward r(metric_T, FP/PA_T+1)          — leading indicator?
  H3  ΔT quintile → ΔFP_T+1                  — does improvement persist?
  H4  compound breakout screen                 — precision / recall
  H5  compound decline screen                  — precision / recall
  H6  SP: lined_up_% + whiff_% → forward FP  — SP breakout/decline

Run:
    python -X utf8 scripts/xfp/research/swing_timing_backtest.py
"""

import io, sys, warnings
import requests
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import cross_val_score

warnings.filterwarnings("ignore")

# ── constants ────────────────────────────────────────────────────────────────

SAVANT_URL = (
    "https://baseballsavant.mlb.com/leaderboard/bat-tracking/"
    "swing-timing-miss-distance?type={type}&season[]={year}&min=50&csv=true"
)

HITTER_PANEL = "data/research/xfp_cache/hitters_multiyr_2015_2026.csv"
SP_PANEL     = "data/research/xfp_cache/sp_multiyr_2015_2025.csv"

# BrownU scoring penalty weight for K (important — distinguishes us from rate-stat lenses)
# High whiff_rate hurts FP more than standard AVG-based fantasy
BROWNWU_K_WEIGHT = 1.0   # 1 K = −1 FP

YEARS = [2023, 2024, 2025, 2026]

CORE_METRICS = [
    "miss_distance",
    "perfect_percent",
    "flawed_percent",
    "on_time_percent",
    "early_percent",
    "late_percent",
    "whiff_rate",
    "flailed_percent",
    "centered_percent",
    "lined_up_percent",
    "over_percent",
    "under_percent",
    "competitive_percent",
]

# PA / GS minimums for backtest inclusion
H_MIN_PA  = 200
SP_MIN_GS = 8


# ── fetch ────────────────────────────────────────────────────────────────────

def fetch_savant_year(player_type: str, year: int) -> pd.DataFrame:
    url = SAVANT_URL.format(type=player_type, year=year)
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code == 404:
        return pd.DataFrame()
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.rename(columns={"id": "mlbam_id"}, inplace=True)
    df["year"] = year
    for col in CORE_METRICS + ["n_swings"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def fetch_all(player_type: str) -> pd.DataFrame:
    frames = []
    for yr in YEARS:
        df = fetch_savant_year(player_type, yr)
        if not df.empty:
            frames.append(df)
            print(f"    {yr} {player_type}: {len(df)} rows")
        else:
            print(f"    {yr} {player_type}: no data")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ── helpers ──────────────────────────────────────────────────────────────────

def section(title: str) -> None:
    print(f"\n{'='*72}")
    print(f"  {title}")
    print(f"{'='*72}")


def corr_report(df, metric, fp_col, label=""):
    sub = df[[metric, fp_col]].dropna()
    if len(sub) < 15:
        return None
    pr, pp = stats.pearsonr(sub[metric], sub[fp_col])
    sr, sp = stats.spearmanr(sub[metric], sub[fp_col])
    sig = "***" if pp < 0.001 else ("**" if pp < 0.01 else ("*" if pp < 0.05 else "n.s."))
    return {"metric": metric, "target": fp_col, "label": label,
            "n": len(sub), "pearson_r": round(pr, 3),
            "spearman_r": round(sr, 3), "p": round(pp, 4), "sig": sig}


def quintile_forward(df, metric, fp_next_col):
    """Bucket metric (year T) into quintiles, show mean T+1 FP per bucket."""
    sub = df[[metric, fp_next_col]].dropna()
    if len(sub) < 30:
        return None
    sub = sub.copy()
    sub["q"] = pd.qcut(sub[metric], 5,
                        labels=["Q1 (best)", "Q2", "Q3", "Q4", "Q5 (worst)"])
    out = sub.groupby("q", observed=True)[fp_next_col].agg(["mean","std","count"]).round(3)
    out.columns = ["mean_fp_next", "std_fp_next", "n"]
    return out


def tier_hit_rate(df, signal_col, fp_delta_col, threshold=0.03):
    """For a binary signal, compute hit-rate: P(ΔFP > threshold | signal=1)."""
    sub = df[[signal_col, fp_delta_col]].dropna()
    yes = sub[sub[signal_col] == 1][fp_delta_col]
    no  = sub[sub[signal_col] == 0][fp_delta_col]
    if len(yes) < 5 or len(no) < 5:
        return None
    hit = (yes > threshold).mean()
    base = (no > threshold).mean()
    t, p = stats.ttest_ind(yes, no)
    return {"n_signal": len(yes), "n_base": len(no),
            "hit_rate": round(hit, 3), "base_rate": round(base, 3),
            "lift": round(hit - base, 3),
            "mean_delta_signal": round(yes.mean(), 4),
            "mean_delta_base":   round(no.mean(), 4),
            "t_stat": round(t, 2), "p": round(p, 4)}


# ── hitter backtests ──────────────────────────────────────────────────────────

def run_hitter_backtests(batter_sv: pd.DataFrame):

    # Load FP panel
    h = pd.read_csv(HITTER_PANEL)
    h = h[h["pa"] >= H_MIN_PA].copy()
    h["year"] = h["year"].astype(int)
    h = h.rename(columns={"batter": "mlbam_id"})

    # Merge savant with panel (same year)
    sv_h = batter_sv.copy()
    sv_h["mlbam_id"] = sv_h["mlbam_id"].astype(int)
    joined = sv_h.merge(h[["mlbam_id","year","fp_per_pa_actual","k_pct","xwoba_per_pa","pa"]],
                        on=["mlbam_id","year"], how="inner")
    print(f"\n  Hitter joined (same-year): {len(joined)} player-seasons")

    # ── H1: same-year correlations ────────────────────────────────────────
    section("H1  SAME-YEAR: Savant swing metric → actual FP/PA  (pooled 2023-2025)")
    rows = []
    pool = joined[joined["year"] < 2026].copy()
    for m in CORE_METRICS:
        r = corr_report(pool, m, "fp_per_pa_actual", label="same-year")
        if r:
            rows.append(r)
    tbl1 = pd.DataFrame(rows).sort_values("pearson_r", key=abs, ascending=False)
    print(tbl1[["metric","n","pearson_r","spearman_r","sig"]].to_string(index=False))

    # ── H2: forward (T → T+1) correlations ───────────────────────────────
    section("H2  FORWARD: metric at year T → FP/PA at year T+1  (2023→24, 2024→25)")
    # build T/T+1 panel
    h_t1 = h[["mlbam_id","year","fp_per_pa_actual"]].copy()
    h_t1["year_prev"] = h_t1["year"] - 1
    h_t1 = h_t1.rename(columns={"fp_per_pa_actual": "fp_next", "year": "year_next"})
    fwd = joined.merge(h_t1[["mlbam_id","year_prev","fp_next"]],
                       left_on=["mlbam_id","year"], right_on=["mlbam_id","year_prev"],
                       how="inner")
    fwd = fwd[fwd["year"] < 2026]  # exclude 2026 (T+1 not available)
    print(f"  Forward panel: {len(fwd)} player-seasons (T-to-T+1 pairs)")
    rows2 = []
    for m in CORE_METRICS:
        r = corr_report(fwd, m, "fp_next", label="T→T+1")
        if r:
            r["same_yr_r"] = tbl1.set_index("metric")["pearson_r"].get(m, np.nan)
            rows2.append(r)
    tbl2 = pd.DataFrame(rows2).sort_values("pearson_r", key=abs, ascending=False)
    tbl2["decay"] = (tbl2["pearson_r"] - tbl2["same_yr_r"]).round(3)
    print(tbl2[["metric","n","pearson_r","spearman_r","sig","same_yr_r","decay"]].to_string(index=False))

    # ── H3: YoY delta → next-year FP change ──────────────────────────────
    section("H3  DELTA PERSISTENCE: Δmetric (T vs T-1) → ΔFP (T+1 vs T)")
    # build T/T-1 delta
    h_prev = joined[["mlbam_id","year"] + CORE_METRICS].copy()
    h_prev["year_next"] = h_prev["year"] + 1
    delta_cols = {}
    for m in CORE_METRICS:
        h_prev[f"prev_{m}"] = h_prev[m]
    fwd2 = fwd.merge(
        h_prev[["mlbam_id","year_next"] + [f"prev_{m}" for m in CORE_METRICS]],
        left_on=["mlbam_id","year"], right_on=["mlbam_id","year_next"],
        how="inner"
    )
    fwd2["fp_delta"] = fwd2["fp_next"] - fwd2["fp_per_pa_actual"]
    rows3 = []
    for m in CORE_METRICS:
        if m in fwd2.columns and f"prev_{m}" in fwd2.columns:
            fwd2[f"d_{m}"] = fwd2[m] - fwd2[f"prev_{m}"]
            r = corr_report(fwd2, f"d_{m}", "fp_delta", label="Δ→ΔFP")
            if r:
                r["metric"] = m
                rows3.append(r)
    tbl3 = pd.DataFrame(rows3).sort_values("pearson_r", key=abs, ascending=False)
    print(f"  (n varies; measuring whether YoY swing improvement predicts YoY FP improvement)")
    print(tbl3[["metric","n","pearson_r","spearman_r","sig"]].to_string(index=False))

    # ── H4: Quintile T → avg FP T+1 ──────────────────────────────────────
    section("H4  FORWARD QUINTILE TIERS: metric_T quintile → avg FP/PA_{T+1}")
    key_metrics = ["perfect_percent", "on_time_percent", "whiff_rate",
                   "flailed_percent", "miss_distance", "lined_up_percent"]
    for m in key_metrics:
        tbl = quintile_forward(fwd, m, "fp_next")
        if tbl is not None:
            print(f"\n  {m}:")
            print(tbl.to_string())
            q1 = tbl["mean_fp_next"].iloc[0]
            q5 = tbl["mean_fp_next"].iloc[-1]
            print(f"  → Q1 vs Q5 spread: {q1 - q5:+.4f} FP/PA")

    # ── H5: Breakout compound screen ─────────────────────────────────────
    section("H5  BREAKOUT COMPOUND SCREEN  (hitter, T→T+1)")
    # Signal: perfect_pct improved by > pop median delta AND on_time improved AND whiff fell
    if len(fwd2) > 20:
        md_perf  = fwd2["d_perfect_percent"].median()
        md_ontime = fwd2["d_on_time_percent"].median()
        md_whiff = fwd2["d_whiff_rate"].median()
        fwd2["breakout_signal"] = (
            (fwd2["d_perfect_percent"] > md_perf) &
            (fwd2["d_on_time_percent"] > md_ontime) &
            (fwd2["d_whiff_rate"] < md_whiff)
        ).astype(int)
        hr = tier_hit_rate(fwd2, "breakout_signal", "fp_delta", threshold=0.02)
        if hr:
            print(f"  Compound breakout: improved perfect% + on_time% + falling whiff%")
            print(f"  Signal n={hr['n_signal']}, base n={hr['n_base']}")
            print(f"  Hit rate (ΔFP>+0.02/PA): signal={hr['hit_rate']:.1%} vs base={hr['base_rate']:.1%}")
            print(f"  Lift = {hr['lift']:+.1%}  |  mean ΔFPP: signal={hr['mean_delta_signal']:+.4f}  base={hr['mean_delta_base']:+.4f}")
            print(f"  t={hr['t_stat']:.2f}  p={hr['p']:.4f}")

    # ── H6: Decline compound screen ──────────────────────────────────────
    section("H6  DECLINE COMPOUND SCREEN  (hitter, T→T+1)")
    if len(fwd2) > 20:
        fwd2["decline_signal"] = (
            (fwd2["d_flailed_percent"] > abs(md_perf)) &   # reuse magnitude ref
            (fwd2["d_on_time_percent"] < md_ontime) &
            (fwd2["d_whiff_rate"] > abs(md_whiff))
        ).astype(int)
        hr2 = tier_hit_rate(fwd2, "decline_signal", "fp_delta", threshold=-0.02)
        if hr2:
            print(f"  Compound decline: flailed% rising + on_time% falling + whiff% rising")
            print(f"  Signal n={hr2['n_signal']}, base n={hr2['n_base']}")
            print(f"  Hit rate (ΔFP < -0.02/PA): signal={hr2['hit_rate']:.1%} vs base={hr2['base_rate']:.1%}")
            print(f"  Lift = {hr2['lift']:+.1%}  |  mean ΔFPP: signal={hr2['mean_delta_signal']:+.4f}  base={hr2['mean_delta_base']:+.4f}")
            print(f"  t={hr2['t_stat']:.2f}  p={hr2['p']:.4f}")

    # ── H7: Age-stratified early_percent signal ──────────────────────────
    section("H7  AGE STRATIFIED: early_percent + age → FP decline  (T→T+1)")
    # early_percent rising = bat is getting out front on fastballs = slowing bat speed
    # Hypothesis: this matters MORE for older hitters (age > 30)
    print("  Note: we don't have age in the panel — using career_pa proxy (career_pa > 3000 ≈ vet)")
    h_age = pd.read_csv(HITTER_PANEL)
    h_age["year"] = h_age["year"].astype(int)
    h_age = h_age.rename(columns={"batter": "mlbam_id"})
    career_pa = h_age.groupby("mlbam_id")["pa"].sum().reset_index().rename(columns={"pa": "career_pa_total"})
    fwd_age = fwd2.merge(career_pa, on="mlbam_id", how="left")
    fwd_age["is_vet"] = fwd_age["career_pa_total"] >= 3000
    for is_vet, label in [(True, "Veterans (career PA ≥ 3000)"), (False, "Young players (< 3000)")]:
        sub = fwd_age[fwd_age["is_vet"] == is_vet]
        r = corr_report(sub, "d_early_percent", "fp_delta", label=label)
        if r:
            print(f"\n  [{label}] n={r['n']}  r(Δearly% → ΔFP)={r['pearson_r']}  {r['sig']}")

    # ── H8: Incremental R² vs our existing model features ────────────────
    section("H8  INCREMENTAL R²: do swing timing metrics add above K%/xwOBA?  (T→T+1)")
    sub = fwd[["fp_next", "fp_per_pa_actual", "k_pct", "xwoba_per_pa"] +
               [m for m in CORE_METRICS if m in fwd.columns]].dropna()
    if len(sub) >= 30:
        y = sub["fp_next"].values
        # base: same-year FP + K% + xwOBA (what our model roughly uses)
        X_base = sub[["fp_per_pa_actual", "k_pct", "xwoba_per_pa"]].values
        r2_base = cross_val_score(LinearRegression(), X_base, y, cv=5, scoring="r2").mean()
        print(f"  Base CV-R² (prior FP + K% + xwOBA):  {r2_base:.4f}")
        for m in ["perfect_percent", "on_time_percent", "whiff_rate",
                  "miss_distance", "flailed_percent", "lined_up_percent"]:
            if m not in sub.columns:
                continue
            X_full = np.column_stack([X_base, sub[m].values])
            r2_full = cross_val_score(LinearRegression(), X_full, y, cv=5, scoring="r2").mean()
            print(f"  + {m:<22}  R²={r2_full:.4f}  ΔR²={r2_full - r2_base:+.5f}")

    # ── current-year candidates (2026 metrics → screen) ──────────────────
    section("H9  2026 SCREEN: Top breakout/decline hitter candidates (min 150 swings)")
    sv_2026 = batter_sv[batter_sv["year"] == 2026].copy()
    sv_2026 = sv_2026[sv_2026["n_swings"] >= 150]
    sv_2026_fp = sv_2026.merge(
        h[h["year"] == 2026][["mlbam_id","fp_per_pa_actual","k_pct","xwoba_per_pa","pa"]],
        on="mlbam_id", how="inner"
    )
    # get 2025 baseline for delta
    sv_2025 = batter_sv[batter_sv["year"] == 2025].copy()
    sv_delta = sv_2026_fp.merge(
        sv_2025[["mlbam_id"] + [f for f in CORE_METRICS if f in sv_2025.columns]],
        on="mlbam_id", suffixes=("_26", "_25"), how="inner"
    )
    # compute deltas
    for m in CORE_METRICS:
        if f"{m}_26" in sv_delta.columns and f"{m}_25" in sv_delta.columns:
            sv_delta[f"d_{m}"] = sv_delta[f"{m}_26"] - sv_delta[f"{m}_25"]

    if "d_perfect_percent" in sv_delta.columns:
        # breakout: large Δperfect% + Δon_time% + Δwhiff falling
        sv_delta["bo_score"] = (
            sv_delta.get("d_perfect_percent", 0).rank(pct=True) +
            sv_delta.get("d_on_time_percent", 0).rank(pct=True) -
            sv_delta.get("d_whiff_rate", 0).rank(pct=True)
        ) / 3
        sv_delta["dec_score"] = (
            sv_delta.get("d_flailed_percent", 0).rank(pct=True) -
            sv_delta.get("d_on_time_percent", 0).rank(pct=True) +
            sv_delta.get("d_whiff_rate", 0).rank(pct=True)
        ) / 3

        display_cols = ["name_26" if "name_26" in sv_delta.columns else "name",
                        "d_perfect_percent", "d_on_time_percent", "d_whiff_rate",
                        "d_flailed_percent", "fp_per_pa_actual", "pa"]
        name_col = "name_26" if "name_26" in sv_delta.columns else "name"
        show_cols = [c for c in [name_col, "d_perfect_percent", "d_on_time_percent",
                                  "d_whiff_rate", "d_flailed_percent",
                                  "fp_per_pa_actual", "pa"] if c in sv_delta.columns]

        print("\n  TOP BREAKOUT CANDIDATES (improving swing mechanics vs 2025):")
        bo = sv_delta.nlargest(15, "bo_score")[show_cols].round(4)
        print(bo.to_string(index=False))

        print("\n  TOP DECLINE CANDIDATES (deteriorating swing mechanics vs 2025):")
        dec = sv_delta.nsmallest(15, "dec_score")[show_cols].round(4)
        print(dec.to_string(index=False))

    return joined, fwd, fwd2


# ── SP backtests ──────────────────────────────────────────────────────────────

def run_sp_backtests(pitcher_sv: pd.DataFrame):

    sp = pd.read_csv(SP_PANEL)
    sp = sp[sp["gs"] >= SP_MIN_GS].copy()
    sp["year"] = sp["year"].astype(int)
    sp = sp.rename(columns={"pitcher": "mlbam_id"})

    sv_sp = pitcher_sv.copy()
    sv_sp["mlbam_id"] = sv_sp["mlbam_id"].astype(int)

    joined = sv_sp.merge(
        sp[["mlbam_id","year","fp_per_start_actual","k_pct","bb_pct","swstr_pct","gs"]],
        on=["mlbam_id","year"], how="inner"
    )
    print(f"\n  SP joined (same-year): {len(joined)} pitcher-seasons")

    # ── SP H1: same-year ─────────────────────────────────────────────────
    section("SP-H1  SAME-YEAR: Savant pitcher-side metric → FP/start  (pooled)")
    rows = []
    pool = joined[joined["year"] < 2026]
    for m in CORE_METRICS:
        r = corr_report(pool, m, "fp_per_start_actual", label="same-year")
        if r:
            rows.append(r)
    tbl = pd.DataFrame(rows).sort_values("pearson_r", key=abs, ascending=False)
    print(tbl[["metric","n","pearson_r","spearman_r","sig"]].to_string(index=False))

    # ── SP H2: forward T → T+1 ───────────────────────────────────────────
    section("SP-H2  FORWARD: pitcher metric_T → FP/start_{T+1}  (2023→24, 2024→25)")
    sp_t1 = sp[["mlbam_id","year","fp_per_start_actual"]].copy()
    sp_t1["year_prev"] = sp_t1["year"] - 1
    sp_t1 = sp_t1.rename(columns={"fp_per_start_actual": "fp_next"})
    fwd_sp = joined.merge(sp_t1[["mlbam_id","year_prev","fp_next"]],
                          left_on=["mlbam_id","year"], right_on=["mlbam_id","year_prev"],
                          how="inner")
    fwd_sp = fwd_sp[fwd_sp["year"] < 2026]
    print(f"  Forward SP panel: {len(fwd_sp)} pitcher-seasons")
    rows2 = []
    for m in CORE_METRICS:
        r = corr_report(fwd_sp, m, "fp_next", label="T→T+1")
        if r:
            rows2.append(r)
    tbl2 = pd.DataFrame(rows2).sort_values("pearson_r", key=abs, ascending=False)
    print(tbl2[["metric","n","pearson_r","spearman_r","sig"]].to_string(index=False))

    # ── SP H3: delta → next FP change ────────────────────────────────────
    section("SP-H3  SP DELTA: Δmetric (T-1→T) → ΔFP/start (T→T+1)")
    sp_prev = joined[["mlbam_id","year"] + [m for m in CORE_METRICS if m in joined.columns]].copy()
    sp_prev["year_next"] = sp_prev["year"] + 1
    fwd_sp2 = fwd_sp.merge(
        sp_prev[["mlbam_id","year_next"] + [m for m in CORE_METRICS if m in sp_prev.columns]],
        left_on=["mlbam_id","year"], right_on=["mlbam_id","year_next"],
        suffixes=("","_prev"), how="inner"
    )
    fwd_sp2["fp_delta"] = fwd_sp2["fp_next"] - fwd_sp2["fp_per_start_actual"]
    rows3 = []
    for m in CORE_METRICS:
        pcol = f"{m}_prev"
        if m in fwd_sp2.columns and pcol in fwd_sp2.columns:
            fwd_sp2[f"d_{m}"] = fwd_sp2[m] - fwd_sp2[pcol]
            r = corr_report(fwd_sp2, f"d_{m}", "fp_delta", label="Δ→ΔFP")
            if r:
                r["metric"] = m
                rows3.append(r)
    tbl3 = pd.DataFrame(rows3).sort_values("pearson_r", key=abs, ascending=False)
    print(tbl3[["metric","n","pearson_r","spearman_r","sig"]].to_string(index=False))

    # ── SP H4: quintile tiers T → T+1 ────────────────────────────────────
    section("SP-H4  FORWARD QUINTILE TIERS: SP metric_T quintile → avg FP/start_{T+1}")
    for m in ["whiff_rate", "lined_up_percent", "perfect_percent", "miss_distance"]:
        tbl = quintile_forward(fwd_sp, m, "fp_next")
        if tbl is not None:
            print(f"\n  {m} (batters-against):")
            print(tbl.to_string())
            q1 = tbl["mean_fp_next"].iloc[0]
            q5 = tbl["mean_fp_next"].iloc[-1]
            print(f"  → Q1 vs Q5: {q1 - q5:+.3f} FP/start")

    # ── SP H5: incremental R² ────────────────────────────────────────────
    section("SP-H5  INCREMENTAL R²: add swing metrics above K%/SwStr?  (T→T+1)")
    sub = fwd_sp[["fp_next","fp_per_start_actual","k_pct","swstr_pct","bb_pct"] +
                  [m for m in CORE_METRICS if m in fwd_sp.columns]].dropna()
    if len(sub) >= 30:
        y = sub["fp_next"].values
        X_base = sub[["fp_per_start_actual","k_pct","swstr_pct","bb_pct"]].values
        r2_base = cross_val_score(LinearRegression(), X_base, y, cv=5, scoring="r2").mean()
        print(f"  Base CV-R² (prior FP + K% + SwStr% + BB%):  {r2_base:.4f}")
        for m in ["whiff_rate", "lined_up_percent", "perfect_percent", "miss_distance",
                  "flawed_percent", "under_percent"]:
            if m not in sub.columns:
                continue
            X_full = np.column_stack([X_base, sub[m].values])
            r2_full = cross_val_score(LinearRegression(), X_full, y, cv=5, scoring="r2").mean()
            print(f"  + {m:<22}  R²={r2_full:.4f}  ΔR²={r2_full - r2_base:+.5f}")

    # ── SP H6: 2026 screen ────────────────────────────────────────────────
    section("SP-H6  2026 SP SCREEN: mechanics-improving vs deteriorating vs 2025")
    sv_sp_26 = pitcher_sv[pitcher_sv["year"] == 2026].copy()
    sv_sp_25 = pitcher_sv[pitcher_sv["year"] == 2025].copy()
    sv_sp_delta = sv_sp_26.merge(
        sv_sp_25[["mlbam_id"] + [m for m in CORE_METRICS if m in sv_sp_25.columns]],
        on="mlbam_id", suffixes=("_26","_25"), how="inner"
    )
    for m in CORE_METRICS:
        if f"{m}_26" in sv_sp_delta.columns and f"{m}_25" in sv_sp_delta.columns:
            sv_sp_delta[f"d_{m}"] = sv_sp_delta[f"{m}_26"] - sv_sp_delta[f"{m}_25"]

    sv_sp_delta = sv_sp_delta.merge(
        joined[joined["year"] == 2026][["mlbam_id","fp_per_start_actual","gs"]],
        on="mlbam_id", how="left"
    )

    if "d_whiff_rate" in sv_sp_delta.columns:
        # Good for SP: more whiff_rate against + less lined_up + less perfect%
        sv_sp_delta["sp_bo_score"] = (
             sv_sp_delta.get("d_whiff_rate", pd.Series(0, index=sv_sp_delta.index)).rank(pct=True) -
             sv_sp_delta.get("d_lined_up_percent", pd.Series(0, index=sv_sp_delta.index)).rank(pct=True) -
             sv_sp_delta.get("d_perfect_percent", pd.Series(0, index=sv_sp_delta.index)).rank(pct=True)
        ) / 3

        name_col = "name_26" if "name_26" in sv_sp_delta.columns else "name"
        show = [c for c in [name_col, "d_whiff_rate", "d_lined_up_percent",
                             "d_perfect_percent", "fp_per_start_actual", "gs"]
                if c in sv_sp_delta.columns]

        print("\n  TOP SP BREAKOUT (batters whiffing more, lining up less vs 2025):")
        print(sv_sp_delta.nlargest(12, "sp_bo_score")[show].round(4).to_string(index=False))

        print("\n  TOP SP DECLINE (batters lining up more, whiffing less vs 2025):")
        print(sv_sp_delta.nsmallest(12, "sp_bo_score")[show].round(4).to_string(index=False))

    return joined, fwd_sp


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("Fetching Savant bat tracking (2023-2026)...")
    batter_sv  = fetch_all("batter")
    pitcher_sv = fetch_all("pitcher")
    print(f"\n  Total batter rows: {len(batter_sv)}")
    print(f"  Total pitcher rows: {len(pitcher_sv)}")

    h_joined, h_fwd, h_fwd2 = run_hitter_backtests(batter_sv)
    sp_joined, sp_fwd = run_sp_backtests(pitcher_sv)

    # Save combined Savant panel
    batter_sv["player_type"]  = "batter"
    pitcher_sv["player_type"] = "pitcher"
    out = pd.concat([batter_sv, pitcher_sv], ignore_index=True)
    out.to_csv("data/research/swing_timing_miss_dist_2023_2026.csv", index=False)
    print("\n  Multi-year Savant data saved → data/research/swing_timing_miss_dist_2023_2026.csv")

    section("BACKTEST COMPLETE")


if __name__ == "__main__":
    main()

"""
validate_weather_bust.py — pre-registered validation of game-time weather as a
feature for the SP per-start bust (floor) model.

Prereg: data/research/validation_runs/weather_bust_2026-07-10.md (locked first).
Baseline: byte-for-byte replication of sp_floor_model (same panel builder,
same TRAIN/TEST years, same scaler+logit recipe, FULL 5-feature baseline per
Rule 9). Three candidate cells, Bonferroni 3:

  1. temp_f            — game-time temperature (F)
  2. wind_out_component— wind mph x field-relative out-to-CF factor
  3. temp_x_park       — (temp-70) x (park HR factor T-1 lagged - 100)/100

Gates (all required per cell): paired-bootstrap 98.33% CI on TEST dAUC
excludes 0; dAUC >= +0.005; augmented quintile calibration monotone
(0.5pp tolerance). Reported non-gating: per-year dAUC signs, tail-lift
(top vs bottom decile of p_aug - p_base), coefficient sign.

Joins by game_pk only (mlbam). Weather at TRAIN time is realized game-time
weather — Rule 8 upper bound; production would need a forecast source.
"""
from __future__ import annotations
from pathlib import Path
import re
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data/research/_boom_stack_per_start_panel_cache.parquet"
WEATHER = ROOT / "data/research/xfp_cache/game_weather.csv"
PARK = ROOT / "data/research/xfp_cache/park_factors_savant.csv"

FEATS = ["prior_k_pct", "prior_bb_pct", "lineup_xfp", "days_rest", "n_prior_starts"]
BUST = 5.0
TRAIN = [2018, 2019, 2021, 2022]
TEST = [2023, 2024, 2025]

N_BOOT = 1000
CI_ALPHA = 0.05 / 3          # Bonferroni 3 -> 98.33% CI
GATE_DAUC = 0.005
CAL_TOL = 0.005              # 0.5pp quintile inversion tolerance
SEED = 20260710

# Locked direction-factor table (MLB field-relative wind strings)
DIR_FACTOR = {
    "Out To CF": 1.0, "Out To LF": 0.7071, "Out To RF": 0.7071,
    "In From CF": -1.0, "In From LF": -0.7071, "In From RF": -0.7071,
    # L To R / R To L / None / Varies / Calm -> 0.0 (default)
}

# Locked venue alias map: weather.venue -> park_factors.venue_name
VENUE_ALIAS = {
    "AT&T Park": "Oracle Park",
    "Guaranteed Rate Field": "Rate Field",
    "Minute Maid Park": "Daikin Park",
    "SunTrust Park": "Truist Park",
    "Marlins Park": "loanDepot park",
    "Miller Park": "American Family Field",
    "Safeco Field": "T-Mobile Park",
    "Dodger Stadium": "UNIQLO Field at Dodger Stadium",
}


# ---------------------------------------------------------------- substrate
def build_panel():
    """Verbatim copy of sp_floor_model.build_panel() (production recipe)."""
    p = pd.read_parquet(PANEL).sort_values(["pitcher", "year", "game_date"]).copy()
    p["game_date"] = pd.to_datetime(p["game_date"])
    g = p.groupby(["pitcher", "year"], group_keys=False)
    p["cum_K"] = g["actual_K"].cumsum() - p["actual_K"]
    p["cum_BB"] = g["actual_BB"].cumsum() - p["actual_BB"]
    p["cum_PA"] = g["actual_PA"].cumsum() - p["actual_PA"]
    p["prior_k_pct"] = p["cum_K"] / p["cum_PA"]
    p["prior_bb_pct"] = p["cum_BB"] / p["cum_PA"]
    p["days_rest"] = g["game_date"].diff().dt.days.clip(3, 7)
    p["bust"] = (p["fp"] < BUST).astype(int)
    p = p[(p["n_prior_starts"] >= 4) & (p["cum_PA"] >= 40)].dropna(subset=FEATS + ["bust"])
    return p


def parse_wind(wind_str, dome, condition):
    """'16 mph, In From RF' -> signed out-to-CF component. Dome/roof -> 0."""
    if dome or (isinstance(condition, str) and condition in ("Dome", "Roof Closed")):
        return 0.0
    if not isinstance(wind_str, str):
        return 0.0
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*mph\s*,\s*(.+)$", wind_str)
    if not m:
        return 0.0
    speed = float(m.group(1))
    direction = m.group(2).strip()
    return speed * DIR_FACTOR.get(direction, 0.0)


def build_weather_features():
    w = pd.read_csv(WEATHER)
    # rescheduled/postponed games appear twice (same game_pk, two dates,
    # identical weather) -> keep the later listing per game_pk
    w = w.sort_values("game_date").drop_duplicates("game_pk", keep="last")
    w["year"] = pd.to_datetime(w["game_date"]).dt.year
    w = w[w["year"].between(2018, 2025)].copy()
    w["wind_out_component"] = [
        parse_wind(ws, dm, cd) for ws, dm, cd in zip(w["wind"], w["dome"], w["condition"])
    ]
    # park HR factor, T-1 lagged, preferred rolling window per prereg
    pf = pd.read_csv(PARK)
    pf = (pf.sort_values("n_years_rolling")
            .groupby(["key_year", "venue_name"], as_index=False).last())
    pf = pf[["key_year", "venue_name", "index_hr"]]
    w["venue_pf"] = w["venue"].replace(VENUE_ALIAS)
    # need key_year == game year - 1 (T-1 lag)
    w = w.merge(
        pf.assign(game_year=pf["key_year"] + 1)
          .rename(columns={"venue_name": "venue_pf", "index_hr": "index_hr_lag1"})
          [["game_year", "venue_pf", "index_hr_lag1"]],
        left_on=["year", "venue_pf"], right_on=["game_year", "venue_pf"], how="left")
    w["index_hr_lag1"] = w["index_hr_lag1"].fillna(100.0)  # special-event venues -> neutral
    return w[["game_pk", "temp_f", "wind_out_component", "index_hr_lag1"]]


# ---------------------------------------------------------------- evaluation
def fit_score(tr, te, feats):
    sc = StandardScaler().fit(tr[feats])
    m = LogisticRegression(max_iter=1000).fit(sc.transform(tr[feats]), tr["bust"])
    p_tr_model = (sc, m)
    p_te = m.predict_proba(sc.transform(te[feats]))[:, 1]
    return p_te, m, sc


def quintile_calibration(y, p):
    q = pd.qcut(p, 5, labels=False, duplicates="drop")
    rates = pd.Series(y).groupby(q).mean().values
    mono = all(rates[i + 1] >= rates[i] - CAL_TOL for i in range(len(rates) - 1))
    return rates, mono


def bootstrap_dauc(y, p_base, p_aug, n=N_BOOT, seed=SEED):
    rng = np.random.default_rng(seed)
    y = np.asarray(y); p_base = np.asarray(p_base); p_aug = np.asarray(p_aug)
    idx_all = np.arange(len(y))
    draws = np.empty(n)
    for i in range(n):
        idx = rng.choice(idx_all, size=len(y), replace=True)
        if y[idx].min() == y[idx].max():          # degenerate resample
            draws[i] = 0.0
            continue
        draws[i] = roc_auc_score(y[idx], p_aug[idx]) - roc_auc_score(y[idx], p_base[idx])
    lo, hi = np.quantile(draws, [CI_ALPHA / 2, 1 - CI_ALPHA / 2])
    return lo, hi


def main():
    print("=== weather_bust validation (prereg 2026-07-10, Bonferroni 3) ===\n")
    panel = build_panel()
    wx = build_weather_features()
    n0 = len(panel)
    d = panel.merge(wx, on="game_pk", how="left")
    assert len(d) == n0, "game_pk join fanned out"

    # Step 2.5 recap: join coverage on the final panel
    print("Step 2.5 recap — weather coverage on the filtered panel:")
    cov = d.groupby("year").agg(
        n=("game_pk", "size"),
        temp_join=("temp_f", lambda s: s.notna().mean()),
        wind_join=("wind_out_component", lambda s: s.notna().mean()))
    print(cov.to_string(float_format=lambda x: f"{x:.4f}"), "\n")

    # imputation per prereg: temp -> TRAIN median; wind -> 0
    tr_mask = d["year"].isin(TRAIN)
    temp_med = d.loc[tr_mask, "temp_f"].median()
    d["temp_f"] = d["temp_f"].fillna(temp_med)
    d["wind_out_component"] = d["wind_out_component"].fillna(0.0)
    d["temp_x_park"] = (d["temp_f"] - 70.0) * (d["index_hr_lag1"] - 100.0) / 100.0

    tr, te = d[d["year"].isin(TRAIN)].copy(), d[d["year"].isin(TEST)].copy()
    print(f"panel rows: train {len(tr)} {TRAIN}, test {len(te)} {TEST}")
    print(f"bust base rate: train {tr.bust.mean()*100:.1f}%  test {te.bust.mean()*100:.1f}%\n")

    p_base, m_base, _ = fit_score(tr, te, FEATS)
    auc_base = roc_auc_score(te["bust"], p_base)
    rates_b, mono_b = quintile_calibration(te["bust"].values, p_base)
    print(f"BASELINE (full 5-feat sp_floor recipe) TEST AUC = {auc_base:.4f}")
    print(f"  baseline quintile bust rates: {[f'{r*100:.1f}%' for r in rates_b]}  monotone={mono_b}\n")

    cells = [
        ("temp_f", "+"),
        ("wind_out_component", "+"),
        ("temp_x_park", "+"),
    ]
    results = []
    for col, exp_sign in cells:
        feats_aug = FEATS + [col]
        p_aug, m_aug, _ = fit_score(tr, te, feats_aug)
        auc_aug = roc_auc_score(te["bust"], p_aug)
        dauc = auc_aug - auc_base
        lo, hi = bootstrap_dauc(te["bust"].values, p_base, p_aug)
        rates_a, mono_a = quintile_calibration(te["bust"].values, p_aug)
        coef = m_aug.coef_[0][-1]
        sign_ok = (coef > 0) if exp_sign == "+" else (coef < 0)

        # per-year test dAUC
        yr_signs = {}
        for y in TEST:
            m = te["year"].values == y
            yr_signs[y] = (roc_auc_score(te["bust"].values[m], p_aug[m])
                           - roc_auc_score(te["bust"].values[m], p_base[m]))

        # tail lift: top vs bottom decile of the weather-risk shift
        shift = p_aug - p_base
        qhi = shift >= np.quantile(shift, 0.9)
        qlo = shift <= np.quantile(shift, 0.1)
        bust_hi = te["bust"].values[qhi].mean()
        bust_lo = te["bust"].values[qlo].mean()

        ci_excl = (lo > 0) or (hi < 0)
        passes = ci_excl and (dauc >= GATE_DAUC) and mono_a
        verdict = "PASS" if passes else "REJECTED"
        results.append((col, dauc, lo, hi, mono_a, coef, sign_ok, yr_signs,
                        bust_hi, bust_lo, verdict))

        print(f"--- cell: {col} ---")
        print(f"  TEST AUC {auc_aug:.4f}  dAUC {dauc:+.4f}   "
              f"98.33% CI [{lo:+.4f}, {hi:+.4f}]  CI-excl-0: {ci_excl}")
        print(f"  coef (std) {coef:+.4f}  expected {exp_sign}  sign_ok={sign_ok}")
        print(f"  calibration quintiles: {[f'{r*100:.1f}%' for r in rates_a]}  monotone={mono_a}")
        print(f"  per-year dAUC: " + "  ".join(f"{y}:{v:+.4f}" for y, v in yr_signs.items()))
        print(f"  tail-lift: top-decile weather-risk bust {bust_hi*100:.1f}% "
              f"vs bottom-decile {bust_lo*100:.1f}%  (base {te.bust.mean()*100:.1f}%)")
        print(f"  gates: CI-excl {ci_excl} | dAUC>=+0.005 {dauc >= GATE_DAUC} | "
              f"cal-mono {mono_a}  ->  {verdict}\n")

    # all-3 joint (reported, non-gating)
    feats_all = FEATS + [c for c, _ in cells]
    p_all, _, _ = fit_score(tr, te, feats_all)
    auc_all = roc_auc_score(te["bust"], p_all)
    print(f"joint all-3-cells TEST AUC = {auc_all:.4f}  (dAUC {auc_all-auc_base:+.4f}, non-gating)\n")

    print("=== SUMMARY ===")
    for col, dauc, lo, hi, mono, coef, sign_ok, _, bh, bl, v in results:
        print(f"  {col:<20} dAUC {dauc:+.4f} CI[{lo:+.4f},{hi:+.4f}] "
              f"coef {coef:+.3f} cal={mono} tail {bh*100:.0f}%/{bl*100:.0f}%  {v}")


if __name__ == "__main__":
    main()

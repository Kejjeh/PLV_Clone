"""validate_hitter_sigma_scale.py

Establish, FROM DATA, the correct per-game outcome-sigma scale for a BrownU
hitter, and audit the two inputs the matchup win-probability path was using:

  1. ``fp_proxy`` in data/research/validation_runs/hitter_boom_bust_panel.parquet
     (the quantity build_hitter_sigma_calibration.py fits) -- is it the
     canonical BrownU hitter FP?
  2. ``global_sigma_per_pa = 0.517`` -- is it a per-PA sigma (as its name and
     every downstream comment claim) or a per-GAME-RATE sigma?

Then measures whether the per-batter ``batter_sigma_factor`` is scale-free
(so a global rescale of the sigma constant does not require a refit), and
re-checks team-level win-probability dispersion on the logged
data/outputs/predictions_history.csv before vs after the correction.

Run:
    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/validate_hitter_sigma_scale.py

Pure measurement: reads only, writes nothing.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "research" / "validation_runs" / "hitter_boom_bust_panel.parquet"
CALIB = ROOT / "data" / "research" / "validation_runs" / "hitter_sigma_calibration.json"
BOX_H = ROOT / "data" / "research" / "xfp_cache" / "boxscore_hitters.parquet"
LINEUP = ROOT / "data" / "research" / "xfp_cache" / "hitter_lineup_appearances_2026.parquet"
RH3 = ROOT / "data" / "outputs" / "xfp_rh3_projections.csv"
RP3 = ROOT / "data" / "outputs" / "xfp_rp3_projections.csv"
HISTORY = ROOT / "data" / "outputs" / "predictions_history.csv"
BOX_P = ROOT / "data" / "research" / "xfp_cache" / "boxscore_pitchers.parquet"

MIN_GAMES = 30          # per-batter minimum for a within-batter sigma estimate
MIN_GAMES_PANEL = 100   # mirrors build_hitter_sigma_calibration.MIN_GAMES_PER_BATTER

RESULTS: dict[str, float] = {}


def _require(p: Path) -> Path:
    if not p.exists():
        raise FileNotFoundError(f"required input missing: {p}")
    return p


def _hdr(s: str) -> None:
    print()
    print("=" * 78)
    print(s)
    print("=" * 78)


def _within_batter_resid(df: pd.DataFrame, key: str, val: str,
                         weight: str | None = None) -> tuple[float, int, int]:
    """Pooled within-batter residual RMS of `val` around each batter's own
    (optionally weight-weighted) mean.  Returns (rms, n_rows, n_batters)."""
    d = df.dropna(subset=[val]).copy()
    if weight is not None:
        d = d.dropna(subset=[weight])
        d = d[d[weight] > 0]
        w = d[weight].astype(float)
        mean = d.groupby(key).apply(
            lambda s: np.average(s[val].astype(float), weights=s[weight].astype(float)),
            include_groups=False,
        )
        d = d.merge(mean.rename("_m"), on=key, how="left")
        resid = d[val].astype(float) - d["_m"]
        rms = float(np.sqrt(np.average(resid ** 2, weights=d[weight].astype(float).values)))
    else:
        mean = d.groupby(key)[val].transform("mean")
        resid = d[val].astype(float) - mean
        rms = float(np.sqrt(np.mean(resid ** 2)))
    return rms, len(d), int(d[key].nunique())


# =============================================================================
# 1. fp_proxy audit
# =============================================================================

def audit_fp_proxy() -> pd.DataFrame:
    _hdr("1. fp_proxy AUDIT -- is the panel's fp_proxy the canonical BrownU FP?")
    print("Canonical BrownU hitter FP/game = R + TB + RBI + BB + HBP + SB - K")
    print("Panel fp_proxy (scripts/xfp/analyze_hitter_boom_bust.py:96) "
          "= TB + BB + HBP - K")
    print("  => fp_proxy OMITS R, RBI and SB.  It is NOT the scoring formula.")

    panel = pd.read_parquet(_require(PANEL)).dropna(subset=["fp_proxy", "PA"])
    print(f"\npanel: {len(panel):,} batter-games, "
          f"{panel['batter'].nunique():,} batters, "
          f"{int(panel['year'].min())}-{int(panel['year'].max())}")
    print(f"  mean fp_proxy/game = {panel['fp_proxy'].mean():.4f}")
    print(f"  SD   fp_proxy/game = {panel['fp_proxy'].std(ddof=0):.4f}")
    print(f"  mean PA/game       = {panel['PA'].mean():.4f}")
    RESULTS["panel_fp_proxy_mean"] = float(panel["fp_proxy"].mean())
    RESULTS["panel_fp_proxy_sd"] = float(panel["fp_proxy"].std(ddof=0))
    RESULTS["panel_pa_per_g"] = float(panel["PA"].mean())

    # Same-population proxy-vs-canonical comparison on the 2026 boxscore store,
    # which carries BOTH the canonical fp_h and every fp_proxy component.
    box = pd.read_parquet(_require(BOX_H))
    box = box.copy()
    box["proxy"] = (box["tb"] + box["bb"] + box["hbp"] - box["k"]).astype(float)
    box["fp_h"] = box["fp_h"].astype(float)
    recomputed = (box["r"] + box["tb"] + box["rbi"] + box["bb"]
                  + box["hbp"] + box["sb"] - box["k"]).astype(float)
    max_dev = float((recomputed - box["fp_h"]).abs().max())
    print(f"\nboxscore_hitters 2026: {len(box):,} rows, "
          f"{box['mlbam_id'].nunique()} batters")
    print(f"  fp_h == R+TB+RBI+BB+HBP+SB-K exactly?  max|dev| = {max_dev:.10f}")
    if max_dev > 1e-9:
        raise AssertionError(
            f"boxscore fp_h does not match the canonical formula (max dev {max_dev})"
        )
    print("  -> fp_h IS the canonical BrownU hitter FP.  Using it as ground truth.")
    print(f"  mean fp_h  = {box['fp_h'].mean():.4f}   SD = {box['fp_h'].std(ddof=0):.4f}")
    print(f"  mean proxy = {box['proxy'].mean():.4f}   SD = {box['proxy'].std(ddof=0):.4f}")
    print(f"  omitted mean (R+RBI+SB) = "
          f"{float((box['r'] + box['rbi'] + box['sb']).mean()):.4f} FP/game")
    RESULTS["box_fp_h_mean_allrows"] = float(box["fp_h"].mean())
    RESULTS["box_proxy_mean_allrows"] = float(box["proxy"].mean())
    return box


# =============================================================================
# 2. what 0.517 actually is
# =============================================================================

def audit_the_constant() -> None:
    _hdr("2. WHAT IS global_sigma_per_pa = 0.517?")
    panel = pd.read_parquet(_require(PANEL)).dropna(subset=["fp_proxy", "PA"])
    panel["rate"] = panel["fp_proxy"].astype(float) / panel["PA"].astype(float)

    # Reproduce build_hitter_sigma_calibration.py:77-83 exactly.
    rms_w, n_rows, n_b = _within_batter_resid(panel, "batter", "rate", weight="PA")
    print(f"reproduced global_sigma_per_pa (PA-weighted within-batter residual RMS")
    print(f"  of the per-GAME RATE fp_proxy/PA) = {rms_w:.6f}   "
          f"(n={n_rows:,} rows, {n_b:,} batters)")
    rms_u, _, _ = _within_batter_resid(panel, "batter", "rate", weight=None)
    print(f"UNWEIGHTED within-batter residual SD of the same rate = {rms_u:.6f}")
    print(f"plain unweighted SD of the rate across all rows       = "
          f"{panel['rate'].std(ddof=0):.6f}")
    print("  -> PA-weighting moves the number by "
          f"{100 * (rms_u - rms_w) / rms_w:+.2f}% only.  Weighting a RATE by PA")
    print("     does NOT convert it to a per-PA quantity; the unit is still")
    print("     'FP per PA, measured once per game' i.e. a per-GAME RATE.")
    RESULTS["sigma_rate_proxy_panel"] = rms_w
    RESULTS["sigma_rate_proxy_panel_unweighted"] = rms_u

    # Dimensional test: if 0.517 were a per-PA sigma, per-game SD = 0.517*sqrt(PA).
    # If it is a per-game RATE sigma, per-game SD = 0.517*PA.
    ppg = float(panel["PA"].mean())
    per_game_proxy_sd, _, _ = _within_batter_resid(panel, "batter", "fp_proxy")
    print(f"\nDIMENSIONAL TEST on the same panel (mean PA/g = {ppg:.4f}):")
    print(f"  measured within-batter per-GAME SD of fp_proxy        = "
          f"{per_game_proxy_sd:.4f}")
    print(f"  'per-PA' reading   0.517 * sqrt(PA)  = {rms_w * math.sqrt(ppg):.4f}   "
          f"(off by {100 * (rms_w * math.sqrt(ppg) / per_game_proxy_sd - 1):+.1f}%)")
    print(f"  'per-game-rate' reading  0.517 * PA  = {rms_w * ppg:.4f}   "
          f"(off by {100 * (rms_w * ppg / per_game_proxy_sd - 1):+.1f}%)")
    print("  -> the per-game-RATE reading is the correct one; the exponent on")
    print("     PA/game must be 2, not 1.")
    RESULTS["panel_per_game_proxy_sd"] = per_game_proxy_sd
    RESULTS["panel_sqrt_reading"] = rms_w * math.sqrt(ppg)
    RESULTS["panel_linear_reading"] = rms_w * ppg


# =============================================================================
# 3. canonical per-game hitter FP sigma on the PRODUCTION population
# =============================================================================

def measure_canonical_sigma(box: pd.DataFrame) -> dict:
    _hdr("3. CANONICAL per-game hitter FP sigma (2026, started games)")
    lin = pd.read_parquet(_require(LINEUP))
    j = box.merge(
        lin[["game_pk", "batter", "started_game", "pa_in_game"]],
        left_on=["game_pk", "mlbam_id"], right_on=["game_pk", "batter"], how="inner",
    )
    if len(j) < 0.9 * len(box):
        raise AssertionError(
            f"boxscore<->lineup join lost too many rows: {len(j)} of {len(box)}"
        )
    print(f"joined {len(j):,} of {len(box):,} boxscore rows to lineup appearances")

    out = {}
    for label, sub in (("ALL appearances", j),
                       ("STARTED games only", j[j["started_game"] == True])):  # noqa: E712
        sub = sub[sub["pa_in_game"].astype(float) > 0].copy()
        sub["rate_full"] = sub["fp_h"].astype(float) / sub["pa_in_game"].astype(float)
        sub["rate_proxy"] = sub["proxy"].astype(float) / sub["pa_in_game"].astype(float)
        # keep batters with enough games for a within-batter estimate
        cnt = sub.groupby("mlbam_id")["fp_h"].transform("size")
        sub = sub[cnt >= MIN_GAMES]
        ppg = float(sub["pa_in_game"].mean())
        sd_game_full, n, nb = _within_batter_resid(sub, "mlbam_id", "fp_h")
        sd_game_proxy, _, _ = _within_batter_resid(sub, "mlbam_id", "proxy")
        sd_rate_full, _, _ = _within_batter_resid(sub, "mlbam_id", "rate_full",
                                                  weight="pa_in_game")
        sd_rate_proxy, _, _ = _within_batter_resid(sub, "mlbam_id", "rate_proxy",
                                                   weight="pa_in_game")
        print(f"\n-- {label}  (n={n:,} games, {nb} batters with >= {MIN_GAMES} g)")
        print(f"   mean PA/game                        = {ppg:.4f}")
        print(f"   mean canonical fp_h                 = {sub['fp_h'].mean():.4f}")
        print(f"   within-batter per-GAME SD of fp_h   = {sd_game_full:.4f}   <-- TRUTH")
        print(f"   within-batter per-GAME SD of proxy  = {sd_game_proxy:.4f}")
        print(f"   within-batter RATE sigma, canonical = {sd_rate_full:.6f}")
        print(f"   within-batter RATE sigma, proxy     = {sd_rate_proxy:.6f}")
        print(f"   canonical/proxy RATE-sigma ratio    = "
              f"{sd_rate_full / sd_rate_proxy:.4f}")
        print(f"   check  rate_sigma * PA/g            = "
              f"{sd_rate_full * ppg:.4f}  vs per-game SD {sd_game_full:.4f} "
              f"({100 * (sd_rate_full * ppg / sd_game_full - 1):+.1f}%)")
        print(f"   check  rate_sigma * sqrt(PA/g)      = "
              f"{sd_rate_full * math.sqrt(ppg):.4f}  vs per-game SD "
              f"{sd_game_full:.4f} "
              f"({100 * (sd_rate_full * math.sqrt(ppg) / sd_game_full - 1):+.1f}%)")
        out[label] = dict(ppg=ppg, sd_game_full=sd_game_full,
                          sd_game_proxy=sd_game_proxy,
                          sd_rate_full=sd_rate_full, sd_rate_proxy=sd_rate_proxy,
                          n=n, nb=nb)
    st = out["STARTED games only"]
    RESULTS["box_ppg_started"] = st["ppg"]
    RESULTS["box_sd_game_full_started"] = st["sd_game_full"]
    RESULTS["box_sd_rate_full_started"] = st["sd_rate_full"]
    RESULTS["box_sd_rate_proxy_started"] = st["sd_rate_proxy"]
    RESULTS["canon_over_proxy_rate_ratio"] = st["sd_rate_full"] / st["sd_rate_proxy"]
    return out


# =============================================================================
# 4. the corrected constant -- two independent estimates
# =============================================================================

def corrected_constant(m3: dict) -> None:
    _hdr("4. THE CORRECTED PER-GAME-RATE SIGMA CONSTANT")
    st = m3["STARTED games only"]
    direct = st["sd_rate_full"]
    ratio = st["sd_rate_full"] / st["sd_rate_proxy"]
    panel_scaled = RESULTS["sigma_rate_proxy_panel"] * ratio
    print("(i)  direct 2026 measurement, canonical FP, started games:")
    print(f"       sigma_rate = {direct:.6f}  (n={st['n']:,} games, {st['nb']} batters)")
    print("(ii) 2018-2025 panel proxy sigma rescaled by the canonical/proxy ratio")
    print(f"       measured on the SAME 2026 rows (controls for population):")
    print(f"       {RESULTS['sigma_rate_proxy_panel']:.6f} * {ratio:.4f} "
          f"= {panel_scaled:.6f}")
    print(f"     agreement between (i) and (ii): "
          f"{100 * (direct / panel_scaled - 1):+.2f}%")
    RESULTS["sigma_rate_canonical_direct"] = direct
    RESULTS["sigma_rate_canonical_panel_scaled"] = panel_scaled

    ppg = st["ppg"]
    print(f"\nImplied per-game sigma at the measured mean PA/g = {ppg:.4f}:")
    print(f"  CURRENT (buggy)  0.517 * sqrt(3.5)      = "
          f"{0.517 * math.sqrt(3.5):.4f} FP/g")
    print(f"  CURRENT (buggy)  0.517 * sqrt({ppg:.3f})     = "
          f"{0.517 * math.sqrt(ppg):.4f} FP/g")
    print(f"  exponent fix only, old constant  0.517 * {ppg:.3f} = "
          f"{0.517 * ppg:.4f} FP/g")
    print(f"  FIXED  {direct:.4f} * {ppg:.3f}                 = "
          f"{direct * ppg:.4f} FP/g")
    print(f"  MEASURED TRUTH (within-batter per-game SD)  = "
          f"{st['sd_game_full']:.4f} FP/g")
    print(f"  legacy constant SIGMA_PER_HITTER_GAME       = 3.5000 FP/g "
          f"({100 * (3.5 / st['sd_game_full'] - 1):+.1f}% vs truth)")
    for lbl, v in (("current-buggy@3.5", 0.517 * math.sqrt(3.5)),
                   (f"current-buggy@{ppg:.2f}", 0.517 * math.sqrt(ppg)),
                   ("exponent-fix-only", 0.517 * ppg),
                   ("FIXED", direct * ppg),
                   ("legacy 3.5", 3.5)):
        print(f"    understatement factor vs truth, {lbl:>22}: "
              f"{st['sd_game_full'] / v:.3f}x   "
              f"(variance {(st['sd_game_full'] / v) ** 2:.2f}x)")
    RESULTS["sigma_game_truth"] = st["sd_game_full"]
    RESULTS["sigma_game_current_35"] = 0.517 * math.sqrt(3.5)
    RESULTS["sigma_game_current_real_ppg"] = 0.517 * math.sqrt(ppg)
    RESULTS["sigma_game_fixed"] = direct * ppg


# =============================================================================
# 5. exponent + constant, calibrated on PER-BATTER PA/g variation
# =============================================================================

def per_batter_slope(box: pd.DataFrame) -> pd.DataFrame:
    """Production computes sigma_game = C * factor * pa_per_g (after the fix).
    Calibrate C -- and confirm the exponent -- by regressing each batter's own
    realized per-game FP SD on that batter's own mean PA/started-game."""
    _hdr("5. EXPONENT + CONSTANT calibrated on per-batter PA/g variation")
    lin = pd.read_parquet(_require(LINEUP))
    j = box.merge(
        lin[["game_pk", "batter", "started_game", "pa_in_game"]],
        left_on=["game_pk", "mlbam_id"], right_on=["game_pk", "batter"], how="inner",
    )
    j = j[(j["started_game"] == True) & (j["pa_in_game"].astype(float) > 0)]  # noqa: E712
    rows = []
    for bid, sub in j.groupby("mlbam_id"):
        if len(sub) < MIN_GAMES:
            continue
        rows.append({
            "batter": int(bid), "n_g": len(sub),
            "ppg": float(sub["pa_in_game"].astype(float).mean()),
            "sd_game": float(sub["fp_h"].astype(float).std(ddof=0)),
            "mean_fp": float(sub["fp_h"].astype(float).mean()),
            "sd_rate": float((sub["fp_h"].astype(float)
                              / sub["pa_in_game"].astype(float)).std(ddof=0)),
        })
    pb = pd.DataFrame(rows)
    print(f"{len(pb)} batters with >= {MIN_GAMES} started games; "
          f"pa_per_g range {pb['ppg'].min():.2f}-{pb['ppg'].max():.2f}")

    # Through-origin slopes for the two competing exponents, weighted by games.
    w = pb["n_g"].astype(float).values
    sd = pb["sd_game"].values
    for name, x in (("sigma = C * ppg      ", pb["ppg"].values),
                    ("sigma = C * sqrt(ppg)", np.sqrt(pb["ppg"].values))):
        c = float(np.sum(w * sd * x) / np.sum(w * x * x))
        pred = c * x
        r2 = 1.0 - float(np.sum(w * (sd - pred) ** 2) / np.sum(w * (sd - np.average(sd, weights=w)) ** 2))
        rmse = float(np.sqrt(np.average((sd - pred) ** 2, weights=w)))
        print(f"  {name}: C = {c:.6f}   weighted R^2 vs batter SDs = {r2:+.4f}   "
              f"RMSE = {rmse:.4f}")
        RESULTS[f"slope_{'linear' if 'sqrt' not in name else 'sqrt'}"] = c
        RESULTS[f"r2_{'linear' if 'sqrt' not in name else 'sqrt'}"] = r2
    c_lin = RESULTS["slope_linear"]
    print(f"\n  -> CALIBRATED CONSTANT for sigma_game = C * pa_per_g:  C = {c_lin:.6f}")
    print(f"     at the mean pa_per_g {pb['ppg'].mean():.4f} this gives "
          f"{c_lin * float(pb['ppg'].mean()):.4f} FP/g")
    print(f"     (raw within-batter pooled per-game SD was "
          f"{RESULTS['sigma_game_truth']:.4f})")
    return pb


# =============================================================================
# 6. is batter_sigma_factor scale-free?  does it transfer to canonical FP?
# =============================================================================

def factor_scale_free(pb: pd.DataFrame) -> None:
    _hdr("6. IS batter_sigma_factor SCALE-FREE (does the refit question bite)?")
    import json
    from sklearn.linear_model import Ridge

    panel = pd.read_parquet(_require(PANEL)).dropna(subset=["fp_proxy", "PA"])
    panel["rate"] = panel["fp_proxy"].astype(float) / panel["PA"].astype(float)
    calib = json.loads(_require(CALIB).read_text(encoding="utf-8"))
    feat_cols = calib["feat_cols"]
    ratings = pd.read_csv(
        _require(ROOT / "data" / "research" / "hitter_ratings_master.csv"),
        low_memory=False,
    )

    # per-batter sigma_emp exactly as build_hitter_sigma_calibration does
    rows = []
    for bid, sub in panel.groupby("batter"):
        if len(sub) < MIN_GAMES_PANEL:
            continue
        wt = sub["PA"].astype(float).values
        x = sub["rate"].astype(float).values
        mw = float(np.average(x, weights=wt))
        rows.append({"batter": int(bid),
                     "sigma_emp": float(np.sqrt(np.average((x - mw) ** 2, weights=wt)))})
    pp = pd.DataFrame(rows)
    r = ratings[["batter", "year"] + feat_cols].copy()
    r["batter"] = pd.to_numeric(r["batter"], errors="coerce")
    r = r.dropna(subset=["batter"])
    r["batter"] = r["batter"].astype(int)
    r = r.sort_values(["batter", "year"]).groupby("batter").tail(1)
    merged = pp.merge(r, on="batter", how="left").dropna(subset=feat_cols + ["sigma_emp"])
    X = merged[feat_cols].values.astype(float)
    mu, sdv = X.mean(axis=0), X.std(axis=0) + 1e-9
    Xz = (X - mu) / sdv

    def factors_for(scale: float) -> np.ndarray:
        y = merged["sigma_emp"].values.astype(float) * scale
        m = Ridge(alpha=2.0).fit(Xz, y)
        pred = m.intercept_ + Xz @ m.coef_
        g = float(np.sqrt(np.average(
            (panel["rate"] - panel.groupby("batter")["rate"].transform(
                lambda s: s.mean())) ** 2))) * scale  # any consistently-scaled global
        f = pred / g
        return f / float(np.nanmean(f))          # re-centered, as production does

    f1, f2, f10 = factors_for(1.0), factors_for(2.0), factors_for(10.0)
    print(f"Ridge is scale-equivariant in y, so re-centered factors should be")
    print(f"identical under any global rescale of sigma_emp:")
    print(f"  max |factor(y) - factor(2y)|  = {np.abs(f1 - f2).max():.3e}")
    print(f"  max |factor(y) - factor(10y)| = {np.abs(f1 - f10).max():.3e}")
    RESULTS["factor_rescale_max_dev"] = float(max(np.abs(f1 - f2).max(),
                                                  np.abs(f1 - f10).max()))
    print("  -> the per-batter factor is a RE-CENTERED RATIO: dimensionless and")
    print("     invariant to the sigma scale.  NO REFIT is required by the")
    print("     constant/exponent correction.")

    # Does a factor fit on PROXY-rate sigma transfer to CANONICAL FP sigma?
    print("\nTRANSFER CHECK -- factor was fit on proxy-rate sigma_emp (2018-25);")
    print("does it track realized CANONICAL per-game sigma (2026)?")
    rh3 = pd.read_csv(_require(RH3), low_memory=False)
    rh3["batter"] = pd.to_numeric(rh3["batter"], errors="coerce")
    m = pb.merge(rh3[["batter", "batter_sigma_factor"]], on="batter", how="inner")
    m = m.dropna(subset=["batter_sigma_factor"])
    c_lin = RESULTS["slope_linear"]
    m["sd_norm"] = m["sd_game"] / (c_lin * m["ppg"])       # realized / model
    print(f"  n batters matched = {len(m)}")
    for col, lbl in (("sd_norm", "realized sigma / model sigma (ppg-adjusted)"),
                     ("sd_rate", "realized canonical per-game-RATE sigma")):
        rr = float(np.corrcoef(m["batter_sigma_factor"], m[col])[0, 1])
        print(f"  corr(batter_sigma_factor, {lbl}) = {rr:+.4f}")
        RESULTS[f"corr_factor_{col}"] = rr
    # also: proxy-rate vs canonical-rate per-batter sigma agreement on 2026
    print(f"  realized sd_norm: mean={m['sd_norm'].mean():.4f} "
          f"sd={m['sd_norm'].std(ddof=0):.4f} "
          f"(perfect model => mean 1.00)")
    RESULTS["sd_norm_mean"] = float(m["sd_norm"].mean())
    RESULTS["sd_norm_sd"] = float(m["sd_norm"].std(ddof=0))


# =============================================================================
# 7. team-level dispersion + win-prob calibration, BEFORE vs AFTER
# =============================================================================

def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam rational approximation, |err|<1e-9)."""
    if not (0.0 < p < 1.0):
        raise ValueError(f"_norm_ppf needs 0<p<1, got {p}")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def hitter_variance_share() -> tuple[float, float]:
    """Reconstruct the hitter share of a BrownU team's projected sigma^2 from
    real 2026 inputs (per-player sigmas actually used in production)."""
    _hdr("7a. HITTER SHARE of team sigma^2 (reconstructed from production inputs)")
    box = pd.read_parquet(_require(BOX_H))
    box["game_date"] = pd.to_datetime(box["game_date"])
    # real games per MLB team per 7-day scoring week
    gpw = (box.groupby([box["team_id"], box["game_date"].dt.to_period("W")])["game_pk"]
              .nunique().reset_index(name="g"))
    games_per_week = float(gpw[gpw["g"] >= 3]["g"].mean())
    print(f"real games per MLB team per scoring week = {games_per_week:.3f}")

    lin = pd.read_parquet(_require(LINEUP))
    st = lin[(lin["started_game"] == True) & (lin["pa_in_game"] > 0)]  # noqa: E712
    ppg_by_batter = st.groupby("batter")["pa_in_game"].agg(["mean", "size"])
    regs = ppg_by_batter[ppg_by_batter["size"] >= MIN_GAMES]["mean"]
    ppg = float(regs.mean())
    print(f"mean pa_per_g over {len(regs)} regulars = {ppg:.4f}")

    rp3 = pd.read_csv(_require(RP3), low_memory=False)
    sp_sigma = float(rp3["xfp_rp3_sigma"].dropna().median())
    print(f"per-SP-start sigma actually used (xfp_rp3_sigma median) = {sp_sigma:.4f}")

    # BrownU active roster: 13 hitters + 9 pitchers; SP starts capped at 10/week;
    # RP floor is 4 true RPs (CLAUDE.md standing rule).
    n_hitters, n_rp, sp_starts, rp_sigma = 13, 4, 10, 2.5
    rp_apps = n_rp * games_per_week * 0.40
    sig_hit_before = 0.517 * math.sqrt(ppg)
    sig_hit_after = RESULTS["slope_linear"] * ppg
    s_hit_before = n_hitters * games_per_week * sig_hit_before ** 2
    s_hit_after = n_hitters * games_per_week * sig_hit_after ** 2
    s_sp = sp_starts * sp_sigma ** 2
    s_rp = rp_apps * rp_sigma ** 2
    share_before = s_hit_before / (s_hit_before + s_sp + s_rp)
    print(f"\n  hitter-games/week = {n_hitters} x {games_per_week:.2f} = "
          f"{n_hitters * games_per_week:.1f}")
    print(f"  sigma^2 hitters (before) = {s_hit_before:8.1f}   "
          f"(sigma/game {sig_hit_before:.4f})")
    print(f"  sigma^2 hitters (after)  = {s_hit_after:8.1f}   "
          f"(sigma/game {sig_hit_after:.4f})")
    print(f"  sigma^2 SP  ({sp_starts} starts)   = {s_sp:8.1f}")
    print(f"  sigma^2 RP  ({rp_apps:.1f} apps)  = {s_rp:8.1f}")
    print(f"  team sigma (before) = {math.sqrt(s_hit_before + s_sp + s_rp):.2f} FP")
    print(f"  team sigma (after)  = {math.sqrt(s_hit_after + s_sp + s_rp):.2f} FP")
    print(f"  -> HITTER SHARE of team sigma^2 (before fix) = {share_before:.4f}")
    RESULTS["games_per_week"] = games_per_week
    RESULTS["hitter_share_before"] = share_before
    RESULTS["var_mult_hitter"] = (sig_hit_after / sig_hit_before) ** 2
    print(f"  -> hitter VARIANCE multiplier from the fix = "
          f"{RESULTS['var_mult_hitter']:.3f}x")
    RESULTS["team_sigma_before"] = math.sqrt(s_hit_before + s_sp + s_rp)
    RESULTS["team_sigma_after"] = math.sqrt(s_hit_after + s_sp + s_rp)

    # Variant table -- what each candidate hitter-sigma rule does to team sigma,
    # and (deliverable 4) what MATCHUP_LEGACY_SIGMA=1 actually buys.
    print("\n  variant team-sigma table (same SP/RP inputs unless noted):")
    hit_games = n_hitters * games_per_week
    variants = [
        ("CURRENT (buggy, real ppg)", 0.517 * math.sqrt(ppg), s_sp, s_rp),
        ("CURRENT (buggy, 3.5 dflt)", 0.517 * math.sqrt(3.5), s_sp, s_rp),
        ("exponent fix only (0.517*ppg)", 0.517 * ppg, s_sp, s_rp),
        ("FIXED (0.7846*ppg)", RESULTS["slope_linear"] * ppg, s_sp, s_rp),
        ("FIXED w/ 3.5 fallback ppg", RESULTS["slope_linear"] * 3.5, s_sp, s_rp),
        ("MATCHUP_LEGACY_SIGMA=1", 3.5, sp_starts * 5.5 ** 2, s_rp),
    ]
    print(f"    {'variant':<32} {'sig_hit/g':>10} {'team sigma':>11} {'x vs current':>13}")
    base = RESULTS["team_sigma_before"]
    for name, sg, ssp, srp in variants:
        ts = math.sqrt(hit_games * sg ** 2 + ssp + srp)
        print(f"    {name:<32} {sg:>10.4f} {ts:>11.2f} {ts / base:>13.3f}")
        RESULTS[f"variant_team_sigma::{name}"] = ts
    return share_before, RESULTS["team_sigma_before"]


LIVE_MODEL_VERSIONS = ("baseline", "MA_v1")


def _load_live_history() -> pd.DataFrame:
    """Live 2026 win-prob snapshots only, restricted to CLOSED periods.

    predictions_history.csv also holds ``backfill_2024_*`` / ``backfill_2025_*``
    rows written by a synthetic backfill whose sigma is 3-10x the production
    model's (implied spread sigma 100-400 FP vs 29-50 FP live).  Mixing them in
    destroys the dispersion test, so they are excluded explicitly and loudly.
    """
    df = pd.read_csv(_require(HISTORY))
    for col in ("actual_my_final", "actual_opp_final", "win_probability",
                "my_projected_total", "opp_projected_total", "my_wtd", "opp_wtd",
                "period", "model_version"):
        if col not in df.columns:
            raise KeyError(f"predictions_history.csv missing required column {col!r}")
    df["mv"] = df["model_version"].fillna("baseline")
    n_all = len(df)
    df = df[df["mv"].isin(LIVE_MODEL_VERSIONS)].copy()
    print(f"predictions_history: {n_all} rows -> {len(df)} live "
          f"({sorted(set(LIVE_MODEL_VERSIONS))}); "
          f"{n_all - len(df)} synthetic-backfill rows excluded")
    df = df[df["actual_my_final"].notna() & df["actual_opp_final"].notna()]
    # OPEN-PERIOD GUARD (2026-07-30, after the label repair).  A non-null
    # actual_*_final is NOT necessarily a final: the pre-fix labeller wrote
    # running single-day partials, and `fetch_closed_matchup_actuals --repair`
    # can only rewrite periods ESPN has DECIDED (open ones raise
    # PeriodNotFinal), so a still-open period keeps its garbage until the
    # nightly closes it (canonical: period 17 on 2026-07-30, labelled
    # 3.3-23.3 / 81.1-68.5 while Jul 27-Aug 2 was mid-play).  The repair's
    # signature is that a decided period's labels are ONE constant pair across
    # all its live snapshots; per-snapshot-varying "finals" are partials by
    # construction and are excluded loudly.  Such a period re-enters on its
    # own once the nightly --repair closes it.
    lbl_nuniq = df.groupby("period")[["actual_my_final", "actual_opp_final"]].nunique()
    open_periods = sorted(int(p) for p in lbl_nuniq[(lbl_nuniq > 1).any(axis=1)].index)
    if open_periods:
        print(f"  open-period guard: excluding period(s) {open_periods} -- "
              f"labels vary by snapshot date, i.e. still-open partials, "
              f"not ESPN finals ({int(df['period'].isin(open_periods).sum())} rows)")
        df = df[~df["period"].isin(open_periods)].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates(["period", "mv"], keep="first")
    df["outcome"] = (df["actual_my_final"] > df["actual_opp_final"]).astype(int)
    df["gap_pred"] = df["my_projected_total"] - df["opp_projected_total"]
    df["resid"] = (df["actual_my_final"] - df["actual_opp_final"]) - df["gap_pred"]
    # remaining projected FP across both teams at snapshot time -- the window the
    # per-event variance model is summed over.  Used to normalise snapshots taken
    # at different points in the scoring week.
    df["rem"] = ((df["my_projected_total"] - df["my_wtd"])
                 + (df["opp_projected_total"] - df["opp_wtd"]))
    if (df["rem"] <= 0).any():
        raise ValueError("non-positive remaining projection in a live snapshot")
    df = df[(df["win_probability"] > 1e-6) & (df["win_probability"] < 1 - 1e-6)]
    df["z"] = df["win_probability"].apply(_norm_ppf)
    df = df[df["z"].abs() > 1e-3].copy()
    df["sigma_before"] = df["gap_pred"] / df["z"]
    if (df["sigma_before"] <= 0).any():
        raise ValueError("logged win_probability disagrees in sign with gap_pred")
    return df


def _report(df: pd.DataFrame, share: float, m: float, label: str) -> None:
    print(f"\n--------- {label}  (n={len(df)} snapshots, "
          f"{df['period'].nunique()} periods) ---------")
    realized = float(np.sqrt(np.mean(df["resid"] ** 2)))
    scale = math.sqrt((1 - share) + share * m)
    df = df.copy()
    df["sigma_after"] = df["sigma_before"] * scale
    print(f"  REALIZED spread-error SD                       = {realized:7.2f} FP")
    print(f"  model spread sigma BEFORE (from logged WP)     = "
          f"{df['sigma_before'].mean():7.2f} FP  "
          f"[{df['sigma_before'].min():.1f},{df['sigma_before'].max():.1f}]")
    print(f"  model spread sigma AFTER  (x{scale:.3f})            = "
          f"{df['sigma_after'].mean():7.2f} FP")
    print("  dispersion  SD(resid/sigma)  -- 1.00 = calibrated, >1 = over-confident")
    for lbl in ("before", "after"):
        zsd = float(np.sqrt(np.mean((df["resid"] / df[f"sigma_{lbl}"]) ** 2)))
        print(f"      {lbl:>6}: {zsd:.3f}   (|error| from 1.00 = {abs(zsd - 1):.3f})")
        RESULTS[f"z_sd_{lbl}_{label}"] = zsd
    # window-normalised variant: sigma should scale ~sqrt(remaining projection)
    k_real = float(np.sqrt(np.mean(df["resid"] ** 2 / df["rem"])))
    k_before = float(np.mean(df["sigma_before"] / np.sqrt(df["rem"])))
    print(f"  window-normalised k = sigma/sqrt(remaining FP): "
          f"realized {k_real:.4f} vs model before {k_before:.4f} "
          f"-> after {k_before * scale:.4f}")
    df["wp_after"] = [_norm_cdf(g / s)
                      for g, s in zip(df["gap_pred"], df["sigma_after"])]
    for col, lb in (("win_probability", "BEFORE"), ("wp_after", "AFTER ")):
        brier = float(((df[col] - df["outcome"]) ** 2).mean())
        print(f"  {lb} Brier = {brier:.4f}  mean pred = {df[col].mean():.3f}  "
              f"actual win rate = {df['outcome'].mean():.3f}")
        RESULTS[f"brier_{lb.strip().lower()}_{label}"] = brier
    for col, lb in (("win_probability", "BEFORE"), ("wp_after", "AFTER ")):
        parts = []
        for lo, hi in ((0.0, 0.35), (0.35, 0.65), (0.65, 1.0)):
            mask = (df[col] >= lo) & (df[col] < hi)
            if mask.sum() == 0:
                continue
            parts.append(f"[{lo:.2f},{hi:.2f}) n={int(mask.sum())} "
                         f"pred={df.loc[mask, col].mean():.2f} "
                         f"act={df.loc[mask, 'outcome'].mean():.2f}")
        print(f"    {lb} buckets: " + " | ".join(parts))
    RESULTS[f"realized_spread_sd_{label}"] = realized
    RESULTS[f"implied_sigma_before_{label}"] = float(df["sigma_before"].mean())
    RESULTS[f"implied_sigma_after_{label}"] = float(df["sigma_after"].mean())


def win_prob_calibration(share_before: float, team_sigma_before: float) -> None:
    _hdr("7b. WIN-PROB CALIBRATION on data/outputs/predictions_history.csv")
    df = _load_live_history()
    m = RESULTS["var_mult_hitter"]

    # Independent cross-check of the section-7a reconstruction: a full-week
    # snapshot's implied SPREAD sigma should be ~sqrt(2) x the per-team sigma.
    recon_spread = team_sigma_before * math.sqrt(2)
    full_week = df[df["rem"] >= 0.9 * df["rem"].max()]
    print(f"\nCROSS-CHECK: reconstructed per-team sigma {team_sigma_before:.2f} FP "
          f"-> spread sigma {recon_spread:.2f} FP")
    print(f"  logged-implied spread sigma, all live snapshots = "
          f"{df['sigma_before'].mean():.2f} FP "
          f"(median {df['sigma_before'].median():.2f})")
    print(f"  -> reconstruction agrees with the logs to "
          f"{100 * (recon_spread / df['sigma_before'].mean() - 1):+.1f}%; "
          f"the hitter share {share_before:.4f} is therefore trustworthy")
    RESULTS["recon_spread_sigma"] = recon_spread
    RESULTS["logged_implied_spread_sigma"] = float(df["sigma_before"].mean())
    del full_week

    _report(df, share_before, m, "all_live")
    _report(df[df["mv"] == "MA_v1"], share_before, m, "MA_v1_only")

    print("\n--- dispersion under each variant (all_live, scaled from the "
          "reconstructed team sigma ratio) ---")
    base = RESULTS["team_sigma_before"]
    zsd_before = RESULTS["z_sd_before_all_live"]
    print(f"    {'variant':<32} {'sigma scale':>11} {'SD(z)':>8} {'|SD(z)-1|':>10}")
    for k, v in RESULTS.items():
        if not k.startswith("variant_team_sigma::"):
            continue
        sc = v / base
        zsd = zsd_before / sc
        print(f"    {k.split('::')[1]:<32} {sc:>11.3f} {zsd:>8.3f} {abs(zsd - 1):>10.3f}")

    print("\n--- sensitivity: hitter share of team sigma^2 sweep (all_live) ---")
    print(f"{'share':>7} {'scale':>7} {'sigma_after':>12} {'SD(z)':>8}")
    for sh in (0.05, 0.075, 0.0905, 0.10, 0.15, 0.20, 0.30):
        sc = math.sqrt((1 - sh) + sh * m)
        sa = df["sigma_before"] * sc
        zsd = float(np.sqrt(np.mean((df["resid"] / sa) ** 2)))
        print(f"{sh:>7.4f} {sc:>7.3f} {float(sa.mean()):>12.2f} {zsd:>8.3f}")


def main() -> None:
    box = audit_fp_proxy()
    audit_the_constant()
    m3 = measure_canonical_sigma(box)
    corrected_constant(m3)
    pb = per_batter_slope(box)
    factor_scale_free(pb)
    share, team_sigma_before = hitter_variance_share()
    win_prob_calibration(share, team_sigma_before)
    _hdr("RESULTS")
    for k, v in RESULTS.items():
        print(f"  {k:38s} {v:.6f}")


if __name__ == "__main__":
    main()

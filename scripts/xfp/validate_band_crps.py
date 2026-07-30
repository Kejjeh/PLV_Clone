"""B3 — distributional calibration of the rh3/rp3 predictive bands (CRPS/pinball).

Pre-registration: data/research/validation_runs/band_crps_calibration_2026-07-29.md
MEASUREMENT ONLY. This script must not write to sigma_calibration.json,
hitter_sigma_calibration.json, or any model bundle.

Two independent panels:

  PANEL A (rest-of-season AVERAGE frame) — reuses verdict_backtest.py's panel
    builders verbatim, then re-emits the bands under BOTH sigma variants per
    bucket so the contrast is exactly paired.
      H  : global sigma          vs  hetero sigma (raw * batter_sigma_factor)
      SP : display sigma (x2.41) vs  decision sigma (raw)

  PANEL B (single-EVENT frame) — re-runs the 2026-07-10 sigma-study pair
    construction from data/research/sigma_study_cache/{rh3,rp3}_*.csv snapshots
    against boxscore actuals, then scores the same two contrasts.

Scoring: closed-form Gaussian CRPS (properscoring not installed), pinball loss
at 0.25/0.75 against the PUBLISHED (clip-at-zero) band edges, plus interval
coverage at 50% and 80% so the numbers are comparable to the 2026-07-10 read.
"""
from __future__ import annotations

import glob
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CACHE = ROOT / "data" / "research" / "sigma_study_cache"
OUTDIR = ROOT / "data" / "research" / "validation_runs"

Z25 = 0.6745
Z10 = 1.2816
MAX_GAP_DAYS = 10           # matches run_sigma_study.py
N_BOOT = 2000
SEED = 20260729
MIN_CLUSTERS = 200          # Rule 5: below this a cell is UNDERPOWERED
ECON_FLOOR = 0.02           # declared 2% relative CRPS floor
FDR_Q = 0.05

_SQRT_PI_INV = 1.0 / np.sqrt(np.pi)


# --------------------------------------------------------------------------- #
# Proper scoring rules (hand-rolled — properscoring is not installed)
# --------------------------------------------------------------------------- #
def crps_gaussian(mu, sigma, y):
    """Closed-form CRPS of N(mu, sigma) against observation y.

    CRPS = sigma * ( z*(2*Phi(z)-1) + 2*phi(z) - 1/sqrt(pi) ),  z = (y-mu)/sigma

    Returns NaN where sigma <= 0 or any input is non-finite (callers DROP those
    rows and report the count; we never silently floor sigma).
    """
    mu = np.asarray(mu, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(mu) & np.isfinite(sigma) & np.isfinite(y) & (sigma > 0)
    out = np.full(mu.shape, np.nan)
    if not ok.any():
        return out
    z = (y[ok] - mu[ok]) / sigma[ok]
    out[ok] = sigma[ok] * (z * (2.0 * norm.cdf(z) - 1.0)
                           + 2.0 * norm.pdf(z) - _SQRT_PI_INV)
    return out


def crps_lognormal_moment_matched(mu, sigma, y):
    """Exact CRPS of the lognormal that sp_bench_mc._lognormal_draws builds.

    sp_bench_mc moment-matches: s2 = ln(1 + sigma^2/mu^2), lmu = ln(mu) - s2/2,
    i.e. E[X] = mu, SD[X] = sigma. Closed form (Baran & Lerch 2015):

      CRPS = y*(2*Phi(w) - 1) - 2*exp(lmu + s2/2)
                 * ( Phi(w - s) + Phi(s/sqrt(2)) - 1 ),   w = (ln y - lmu)/s

    Undefined for y <= 0 (a lognormal assigns zero mass there), so those rows
    return NaN and are reported separately — that is itself the finding for
    negative-FP starts.
    """
    mu = np.asarray(mu, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    y = np.asarray(y, dtype=float)
    out = np.full(mu.shape, np.nan)
    ok = (np.isfinite(mu) & np.isfinite(sigma) & np.isfinite(y)
          & (sigma > 0) & (mu > 0) & (y > 0))
    if not ok.any():
        return out
    m, s_sd, yy = mu[ok], sigma[ok], y[ok]
    s2 = np.log1p((s_sd * s_sd) / (m * m))
    s = np.sqrt(s2)
    lmu = np.log(m) - s2 / 2.0
    w = (np.log(yy) - lmu) / s
    out[ok] = (yy * (2.0 * norm.cdf(w) - 1.0)
               - 2.0 * np.exp(lmu + s2 / 2.0)
               * (norm.cdf(w - s) + norm.cdf(s / np.sqrt(2.0)) - 1.0))
    return out


def pinball(y, qhat, q):
    y = np.asarray(y, dtype=float)
    qhat = np.asarray(qhat, dtype=float)
    d = y - qhat
    return np.maximum(q * d, (q - 1.0) * d)


def score_block(mu, sigma, y, p25, p75):
    """-> DataFrame of per-row scores for one (bucket, band) cell."""
    mu = np.asarray(mu, float)
    sigma = np.asarray(sigma, float)
    y = np.asarray(y, float)
    return pd.DataFrame({
        "crps": crps_gaussian(mu, sigma, y),
        "pin25": pinball(y, p25, 0.25),
        "pin75": pinball(y, p75, 0.75),
        "cov50": ((y >= p25) & (y <= p75)).astype(float),
        "cov80": ((y >= mu - Z10 * sigma) & (y <= mu + Z10 * sigma)).astype(float),
    })


def band_edges(mu, sigma, clip_zero=True):
    lo = mu - Z25 * sigma
    hi = mu + Z25 * sigma
    if clip_zero:
        lo = np.clip(lo, 0.0, None)
    return lo, hi


# --------------------------------------------------------------------------- #
# Paired, player-clustered bootstrap + BH-FDR
# --------------------------------------------------------------------------- #
def paired_cluster_bootstrap(df, col_a, col_b, cluster_col, n_boot=N_BOOT, seed=SEED):
    """Bootstrap mean(col_b) - mean(col_a), resampling CLUSTERS with replacement.

    Returns dict with the point difference, percentile CI, two-sided bootstrap
    p, and cluster/row counts.
    """
    d = df.dropna(subset=[col_a, col_b, cluster_col])
    if d.empty:
        return None
    clusters = d[cluster_col].to_numpy()
    uniq, inv = np.unique(clusters, return_inverse=True)
    # index rows by cluster once
    order = np.argsort(inv, kind="stable")
    inv_sorted = inv[order]
    starts = np.searchsorted(inv_sorted, np.arange(len(uniq)), side="left")
    ends = np.searchsorted(inv_sorted, np.arange(len(uniq)), side="right")
    rows_by_cluster = [order[starts[i]:ends[i]] for i in range(len(uniq))]

    a = d[col_a].to_numpy(float)
    b = d[col_b].to_numpy(float)
    point = float(b.mean() - a.mean())

    rng = np.random.default_rng(seed)
    diffs = np.empty(n_boot)
    n_c = len(uniq)
    for i in range(n_boot):
        pick = rng.integers(0, n_c, n_c)
        idx = np.concatenate([rows_by_cluster[j] for j in pick])
        diffs[i] = b[idx].mean() - a[idx].mean()
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    frac_ge = float((diffs >= 0).mean())
    frac_le = float((diffs <= 0).mean())
    p = min(1.0, 2.0 * min(frac_ge, frac_le))
    p = max(p, 1.0 / (2.0 * n_boot))
    return {"diff": point, "ci_lo": float(lo), "ci_hi": float(hi), "p": p,
            "n_rows": int(len(d)), "n_clusters": int(n_c),
            "mean_a": float(a.mean()), "mean_b": float(b.mean())}


def bh_fdr(pvals, q=FDR_Q):
    p = np.asarray(pvals, float)
    m = len(p)
    order = np.argsort(p)
    thresh = q * (np.arange(1, m + 1) / m)
    passed = p[order] <= thresh
    k = np.where(passed)[0]
    cutoff = p[order][k.max()] if len(k) else -1.0
    return p <= cutoff


# --------------------------------------------------------------------------- #
# Reporting helpers
# --------------------------------------------------------------------------- #
def cell_summary(name, sc, extra=None):
    d = sc.dropna(subset=["crps"])
    row = {
        "cell": name, "n": len(d),
        "CRPS": round(float(d["crps"].mean()), 5) if len(d) else np.nan,
        "pin25": round(float(d["pin25"].mean()), 5) if len(d) else np.nan,
        "pin75": round(float(d["pin75"].mean()), 5) if len(d) else np.nan,
        "cov50_%": round(float(d["cov50"].mean()) * 100, 1) if len(d) else np.nan,
        "cov80_%": round(float(d["cov80"].mean()) * 100, 1) if len(d) else np.nan,
    }
    if extra:
        row.update(extra)
    return row


def print_table(rows, title):
    print(f"\n--- {title} ---")
    if not rows:
        print("  (empty)")
        return
    print(pd.DataFrame(rows).to_string(index=False))


# =========================================================================== #
# PANEL A — rest-of-season average frame (verdict_backtest host)
# =========================================================================== #
def panel_a():
    import joblib
    from plv_clone.models.xfp import rh3 as RH3
    from plv_clone.models.xfp import rp3 as RP3
    from plv_clone.models.xfp.hitter_sigma_hetero import (
        load_calibration as load_hetero_calib,
        compute_batter_sigma_factors,
    )
    from scripts.xfp.verdict_backtest import (
        build_hitter_panel, build_pitcher_panel, lookup_sigma_vec,
    )

    print("\n" + "=" * 78)
    print("PANEL A — rest-of-season AVERAGE frame (verdict_backtest panels)")
    print("=" * 78)

    # ---------------- hitters: global vs hetero ---------------- #
    h_roll, _h_multi = build_hitter_panel()
    b = joblib.load(RH3.MODEL_PKL)
    pipe, feats = b["pipeline"], b["features"]
    ci_table, overall_sigma = b["ci_table"], b["overall_sigma"]
    pred_buckets = {int(k): np.array(v) for k, v in b["pred_buckets"].items()}

    hetero_calib = load_hetero_calib()
    ratings = pd.read_csv(RH3.HITTER_RATINGS_MASTER, low_memory=False)

    rows = []
    d26 = h_roll[h_roll["year"] == 2026]
    for split in sorted(d26["split_day"].unique()):
        sub = d26[(d26["split_day"] == split)
                  & (d26["pa_to"] >= RH3.EVAL_PA_MIN)].copy()
        sub = sub.dropna(subset=feats)
        if sub.empty:
            continue
        proj = pipe.predict(sub[feats].values)
        sig_g = lookup_sigma_vec(ci_table, overall_sigma, int(split), proj, pred_buckets)
        # hetero factor: re-centered across THIS split's active batters, exactly
        # as rh3.main() does for the latest split.
        active = set(sub["batter"].astype(int).tolist())
        fmap = compute_batter_sigma_factors(ratings, hetero_calib, batter_subset=active)
        factor = np.array([fmap.get(int(bid), 1.0) for bid in sub["batter"]], float)
        rows.append(pd.DataFrame({
            "player": sub["batter"].astype(int).values,
            "split_day": int(split),
            "proj": proj,
            "sigma_global": sig_g,
            "sigma_hetero": sig_g * factor,
            "factor": factor,
            "realized": sub["ros_full_fp_per_pa"].values,
            "fwd_events": sub["ros_pa"].values,
        }))
    H = pd.concat(rows, ignore_index=True)
    H = H[(H["fwd_events"] >= RH3.ROS_PA_MIN) & H["realized"].notna()].copy()
    H["tier"] = H.groupby("split_day")["proj"].transform(
        lambda s: pd.qcut(s, 3, labels=["T3_low", "T2_mid", "T1_high"], duplicates="drop"))
    print(f"\nH rows={len(H)}  players={H['player'].nunique()}  "
          f"splits={sorted(H['split_day'].unique())}")
    print(f"  mean forward PA per row = {H['fwd_events'].mean():.1f} "
          f"(RoS window is TRUNCATED at the data cutoff, not a full 162)")
    print(f"  hetero factor: mean={H['factor'].mean():.4f} "
          f"min={H['factor'].min():.3f} max={H['factor'].max():.3f} "
          f"n_at_1.0={(H['factor'] == 1.0).sum()}")

    # ---------------- starters: display vs decision ---------------- #
    p_roll = build_pitcher_panel()
    b = joblib.load(RP3.MODEL_PKL)
    ppipe, pfeats = b["pipeline"], b["features"]
    pci, psig = b["ci_table"], b["overall_sigma"]
    pbk = {int(k): np.array(v) for k, v in b["pred_buckets"].items()}
    alpha = float(RP3._load_sigma_calibration().get("alpha_global", 1.0))
    print(f"\nrp3 alpha_global = {alpha}")

    rows = []
    d26 = p_roll[p_roll["year"] == 2026]
    for split in sorted(d26["split_day"].unique()):
        sub = d26[(d26["split_day"] == split)
                  & (d26["gs_to"] >= RP3.EVAL_GS_MIN)].copy()
        sub = sub.dropna(subset=pfeats)
        if sub.empty:
            continue
        proj = ppipe.predict(sub[pfeats].values)
        sig_raw = lookup_sigma_vec(pci, psig, int(split), proj, pbk)
        rows.append(pd.DataFrame({
            "player": sub["pitcher"].astype(int).values,
            "split_day": int(split),
            "proj": proj,
            "sigma_decision": sig_raw,
            "sigma_display": sig_raw * alpha,
            "realized": sub["ros_fp_per_start"].values,
            "fwd_events": sub["ros_gs"].values,
            "on_il": sub.get("is_on_il_at_split", pd.Series(0, index=sub.index)).values,
        }))
    SP = pd.concat(rows, ignore_index=True)
    SP = SP[(SP["fwd_events"] >= RP3.ROS_GS_MIN) & (SP["on_il"] == 0)
            & SP["realized"].notna()].copy()
    SP["tier"] = SP.groupby("split_day")["proj"].transform(
        lambda s: pd.qcut(s, 3, labels=["T3_low", "T2_mid", "T1_high"], duplicates="drop"))
    print(f"\nSP rows={len(SP)}  players={SP['player'].nunique()}  "
          f"splits={sorted(SP['split_day'].unique())}")
    print(f"  mean forward GS per row = {SP['fwd_events'].mean():.1f}")

    return H, SP


# =========================================================================== #
# PANEL B — single-event frame (2026-07-10 sigma-study pair construction)
# =========================================================================== #
def load_snapshots(prefix, cols):
    frames = []
    for path in sorted(glob.glob(str(CACHE / f"{prefix}_*.csv"))):
        base = os.path.basename(path)
        m = re.search(r"(\d{4}-\d{2}-\d{2})", base)
        if not m:
            continue
        df = pd.read_csv(path)
        keep = [c for c in cols if c in df.columns]
        df = df[keep].copy()
        df["snap_date"] = pd.Timestamp(m.group(1))
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def panel_b():
    print("\n" + "=" * 78)
    print("PANEL B — single-EVENT frame (sigma_study_cache snapshots)")
    print("=" * 78)

    # ---------------- rp3: display vs decision ---------------- #
    snap = load_snapshots("rp3", [
        "pitcher", "player_name", "data_quality_tag", "xfp_rp3_per_start",
        "xfp_rp3_sigma", "xfp_rp3_sigma_raw", "xfp_rp3_p25", "xfp_rp3_p75",
        "xfp_rp3_decision_p25", "xfp_rp3_decision_p75",
    ])
    print(f"rp3 snapshots: {snap['snap_date'].nunique()} dates "
          f"{snap['snap_date'].min().date()}..{snap['snap_date'].max().date()}, "
          f"{len(snap)} rows")
    n_marcel = int((snap["data_quality_tag"] == "marcel_il").sum())
    snap = snap[snap["data_quality_tag"] != "marcel_il"]
    snap = snap.dropna(subset=["xfp_rp3_per_start", "xfp_rp3_sigma",
                               "xfp_rp3_sigma_raw", "xfp_rp3_p25", "xfp_rp3_p75"])
    print(f"  excluded marcel_il rows: {n_marcel}; usable snapshot rows: {len(snap)}")
    snap["tier"] = (snap.groupby("snap_date")["xfp_rp3_per_start"]
                    .transform(lambda s: pd.qcut(s, 3, labels=["T3_low", "T2_mid", "T1_high"])))

    box = pd.read_parquet(ROOT / "data/research/xfp_cache/boxscore_pitchers.parquet")
    starts = box[box["gs"] == 1][["game_pk", "game_date", "mlbam_id", "fp_sp"]].copy()
    starts["game_date"] = pd.to_datetime(starts["game_date"])
    starts = starts.rename(columns={"mlbam_id": "pitcher", "fp_sp": "actual"})
    starts = starts.sort_values("game_date")

    pairs = pd.merge_asof(
        starts, snap.sort_values("snap_date"), by="pitcher",
        left_on="game_date", right_on="snap_date",
        allow_exact_matches=False,
        tolerance=pd.Timedelta(days=MAX_GAP_DAYS), direction="backward")
    pairs = pairs.dropna(subset=["snap_date"])
    assert not pairs.duplicated(["pitcher", "game_pk"]).any()
    pairs["gap_days"] = (pairs["game_date"] - pairs["snap_date"]).dt.days
    pairs["gap_bucket"] = pd.cut(pairs["gap_days"], [0, 2, 5, 10],
                                 labels=["1-2d", "3-5d", "6-10d"])
    print(f"\nrp3 single-start pairs: n={len(pairs)} "
          f"pitchers={pairs['pitcher'].nunique()}")
    print("  SANITY vs 2026-07-10 (868 pairs, cov50 44.9%, cov80 74.0%):")
    cov50 = ((pairs["actual"] >= pairs["xfp_rp3_p25"])
             & (pairs["actual"] <= pairs["xfp_rp3_p75"])).mean()
    lo10 = pairs["xfp_rp3_per_start"] - Z10 * pairs["xfp_rp3_sigma"]
    hi10 = pairs["xfp_rp3_per_start"] + Z10 * pairs["xfp_rp3_sigma"]
    cov80 = ((pairs["actual"] >= lo10) & (pairs["actual"] <= hi10)).mean()
    print(f"    reproduced display-band cov50={cov50*100:.1f}%  cov80={cov80*100:.1f}%")

    # ---------------- rh3: global vs hetero ---------------- #
    hsnap = load_snapshots("rh3", [
        "batter", "player_name", "xfp_rh3_per_pa", "xfp_rh3_per_game",
        "xfp_rh3_sigma", "xfp_rh3_sigma_global", "xfp_rh3_sigma_hetero",
        "batter_sigma_factor", "xfp_rh3_p25", "xfp_rh3_p75",
    ])
    hsnap = hsnap.dropna(subset=["xfp_rh3_per_pa", "xfp_rh3_sigma_global",
                                 "xfp_rh3_sigma_hetero"])
    print(f"\nrh3 snapshots: {hsnap['snap_date'].nunique()} dates, {len(hsnap)} rows")

    hbox = pd.read_parquet(ROOT / "data/research/xfp_cache/boxscore_hitters.parquet")
    games = hbox[["game_pk", "game_date", "mlbam_id", "fp_h"]].copy()
    games["game_date"] = pd.to_datetime(games["game_date"])
    games = games.rename(columns={"mlbam_id": "batter"}).sort_values("game_date")
    sc = pd.read_parquet(ROOT / "data/research/xfp_cache/statcast_2026.parquet",
                         columns=["game_pk", "batter", "at_bat_number"])
    pa = (sc.groupby(["game_pk", "batter"])["at_bat_number"].nunique()
          .rename("pa_game").reset_index())
    games = games.merge(pa, on=["game_pk", "batter"], how="inner")
    games = games[games["pa_game"] > 0]

    hpairs = pd.merge_asof(
        games, hsnap.sort_values("snap_date"), by="batter",
        left_on="game_date", right_on="snap_date",
        allow_exact_matches=False,
        tolerance=pd.Timedelta(days=MAX_GAP_DAYS), direction="backward")
    hpairs = hpairs.dropna(subset=["snap_date"])
    hpairs = (hpairs.sort_values("game_date")
              .drop_duplicates(["batter", "snap_date"], keep="first"))
    hpairs["actual"] = hpairs["fp_h"] / hpairs["pa_game"]
    hpairs["gap_days"] = (hpairs["game_date"] - hpairs["snap_date"]).dt.days
    hpairs["gap_bucket"] = pd.cut(hpairs["gap_days"], [0, 2, 5, 10],
                                  labels=["1-2d", "3-5d", "6-10d"])
    hpairs["tier"] = (hpairs.groupby("snap_date")["xfp_rh3_per_game"]
                      .transform(lambda s: pd.qcut(s, 3, labels=["T3_low", "T2_mid", "T1_high"])))
    print(f"rh3 single-game pairs: n={len(hpairs)} batters={hpairs['batter'].nunique()}")
    print(f"  hetero factor: mean={hpairs['batter_sigma_factor'].mean():.4f} "
          f"min={hpairs['batter_sigma_factor'].min():.3f} "
          f"max={hpairs['batter_sigma_factor'].max():.3f}")
    return hpairs, pairs


# =========================================================================== #
def score_contrast(label, df, mu_col, sig_a, sig_b, name_a, name_b,
                   y_col="actual", cluster="player", slices=()):
    """Score one paired contrast; returns (summary_rows, boot_result, scored df)."""
    mu = df[mu_col].to_numpy(float)
    y = df[y_col].to_numpy(float)
    out = df.copy()
    for tag, sc_col in ((name_a, sig_a), (name_b, sig_b)):
        s = df[sc_col].to_numpy(float)
        lo, hi = band_edges(mu, s, clip_zero=True)
        blk = score_block(mu, s, y, lo, hi)
        for c in blk.columns:
            out[f"{c}__{tag}"] = blk[c].values
    rows = [
        cell_summary(f"{label} :: {name_a}",
                     out[[f"{c}__{name_a}" for c in
                          ("crps", "pin25", "pin75", "cov50", "cov80")]]
                     .rename(columns=lambda c: c.split("__")[0])),
        cell_summary(f"{label} :: {name_b}",
                     out[[f"{c}__{name_b}" for c in
                          ("crps", "pin25", "pin75", "cov50", "cov80")]]
                     .rename(columns=lambda c: c.split("__")[0])),
    ]
    boot = paired_cluster_bootstrap(out, f"crps__{name_a}", f"crps__{name_b}",
                                    cluster)
    slice_rows = []
    for scol in slices:
        if scol not in out.columns:
            continue
        for val, sub in out.groupby(scol, observed=True):
            for tag in (name_a, name_b):
                slice_rows.append(cell_summary(
                    f"{label} [{scol}={val}] :: {tag}",
                    sub[[f"{c}__{tag}" for c in
                         ("crps", "pin25", "pin75", "cov50", "cov80")]]
                    .rename(columns=lambda c: c.split("__")[0])))
    return rows, boot, slice_rows, out


def main():
    pd.set_option("display.width", 200)
    H_a, SP_a = panel_a()
    H_b, SP_b = panel_b()

    primary_rows, slice_rows, boots = [], [], {}

    r, boot, sl, H_a_sc = score_contrast(
        "A1 rh3 RoS-avg (FP/PA)", H_a, "proj", "sigma_global", "sigma_hetero",
        "global", "hetero", y_col="realized", slices=("tier",))
    primary_rows += r; slice_rows += sl; boots["A1"] = boot

    r, boot, sl, SP_a_sc = score_contrast(
        "A2 rp3 RoS-avg (FP/start)", SP_a, "proj", "sigma_display",
        "sigma_decision", "display_x2.41", "decision_raw",
        y_col="realized", slices=("tier",))
    primary_rows += r; slice_rows += sl; boots["A2"] = boot

    r, boot, sl, H_b_sc = score_contrast(
        "B1 rh3 next-game (FP/PA)", H_b, "xfp_rh3_per_pa", "xfp_rh3_sigma_global",
        "xfp_rh3_sigma_hetero", "global", "hetero",
        y_col="actual", cluster="batter", slices=("tier", "gap_bucket"))
    primary_rows += r; slice_rows += sl; boots["B1"] = boot

    r, boot, sl, SP_b_sc = score_contrast(
        "B2 rp3 next-start (FP/start)", SP_b, "xfp_rp3_per_start",
        "xfp_rp3_sigma", "xfp_rp3_sigma_raw", "display_x2.41", "decision_raw",
        y_col="actual", cluster="pitcher",
        slices=("tier", "gap_bucket", "data_quality_tag"))
    primary_rows += r; slice_rows += sl; boots["B2"] = boot

    print_table(primary_rows, "PRIMARY CELLS — CRPS / pinball / coverage")
    print_table(slice_rows, "DESCRIPTIVE SLICES")

    # ---- paired contrasts + BH-FDR ---- #
    print("\n--- PAIRED CONTRASTS (mean CRPS_B - mean CRPS_A; negative = B better) ---")
    keys = ["A1", "A2", "B1", "B2"]
    ptab = []
    for k in keys:
        bt = boots[k]
        rel = bt["diff"] / bt["mean_a"] if bt["mean_a"] else np.nan
        ptab.append({
            "cell": k, "n_rows": bt["n_rows"], "n_clusters": bt["n_clusters"],
            "CRPS_A": round(bt["mean_a"], 5), "CRPS_B": round(bt["mean_b"], 5),
            "dCRPS": round(bt["diff"], 6),
            "rel_%": round(rel * 100, 2),
            "ci95": f"[{bt['ci_lo']:+.6f}, {bt['ci_hi']:+.6f}]",
            "boot_p": bt["p"],
            "underpowered": bt["n_clusters"] < MIN_CLUSTERS,
        })
    ptab = pd.DataFrame(ptab)
    ptab["bh_pass"] = bh_fdr(ptab["boot_p"].to_numpy())
    ptab["econ_pass"] = ptab["rel_%"].abs() >= ECON_FLOOR * 100
    ptab["ci_excl_0"] = [not (float(s.split(",")[0][1:]) <= 0 <= float(s.split(",")[1][:-1]))
                         for s in ptab["ci95"]]
    print(ptab.to_string(index=False))

    # ---- lognormal side-cell (descriptive, declared) ---- #
    print("\n--- DESCRIPTIVE SIDE-CELL: lognormal CRPS (sp_bench_mc's sampler) ---")
    print("  NOTE: declared as a 200k-draw MC estimator; replaced with the EXACT")
    print("  closed form for the same functional (strict improvement, verified")
    print("  below against a 200k-draw MC on 50 random rows).")
    lb = SP_b_sc.copy()
    for tag, col in (("display_x2.41", "xfp_rp3_sigma"),
                     ("decision_raw", "xfp_rp3_sigma_raw")):
        ln = crps_lognormal_moment_matched(lb["xfp_rp3_per_start"], lb[col], lb["actual"])
        gs = lb[f"crps__{tag}"].to_numpy(float)
        m = np.isfinite(ln)
        print(f"  {tag:<14} lognormal CRPS={np.nanmean(ln):.4f} (n={int(m.sum())}) "
              f"vs Gaussian CRPS={np.nanmean(gs[m]):.4f} on the SAME rows | "
              f"rows with actual<=0 (lognormal assigns 0 mass) = {int((~m).sum())}")
    n_neg = int((lb["actual"] <= 0).sum())
    print(f"  negative-or-zero-FP starts in panel: {n_neg} / {len(lb)} "
          f"({n_neg/len(lb)*100:.1f}%) — structurally unscorable by a lognormal")
    # MC verification of the closed form
    rng = np.random.default_rng(SEED)
    idx = rng.choice(np.where(lb["actual"] > 0)[0], size=min(50, int((lb['actual'] > 0).sum())),
                     replace=False)
    errs = []
    for i in idx:
        mu_i = float(lb["xfp_rp3_per_start"].iloc[i])
        s_i = float(lb["xfp_rp3_sigma"].iloc[i])
        y_i = float(lb["actual"].iloc[i])
        if mu_i <= 0 or s_i <= 0:
            continue
        s2 = np.log1p(s_i ** 2 / mu_i ** 2)
        lmu = np.log(mu_i) - s2 / 2
        x = rng.lognormal(lmu, np.sqrt(s2), 200_000)
        xs = np.sort(x)
        m_ = len(xs)
        e1 = np.abs(xs - y_i).mean()
        e2 = (2.0 / (m_ * m_)) * np.sum((2 * np.arange(1, m_ + 1) - m_ - 1) * xs)
        mc = e1 - 0.5 * e2
        cf = float(crps_lognormal_moment_matched([mu_i], [s_i], [y_i])[0])
        errs.append(abs(mc - cf) / max(cf, 1e-9))
    print(f"  closed-form vs 200k-draw MC on {len(errs)} rows: "
          f"max rel err = {max(errs):.2e}, mean = {np.mean(errs):.2e}")

    # ---- POST-HOC DIAGNOSTICS (NOT pre-registered, NOT gated) ---- #
    print("\n" + "=" * 78)
    print("POST-HOC DIAGNOSTICS — added AFTER seeing the primary result.")
    print("NOT pre-registered, NOT gated, cannot promote anything. Included")
    print("because the primary result is frame-dependent and these locate the")
    print("CRPS optimum inside each frame.")
    print("=" * 78)

    def crps_optimal_scale(mu, sigma_base, y, grid=None):
        """argmin_c mean CRPS(mu, c*sigma_base, y). Descriptive only."""
        if grid is None:
            grid = np.arange(0.20, 6.005, 0.01)
        mu = np.asarray(mu, float); sb = np.asarray(sigma_base, float)
        y = np.asarray(y, float)
        best_c, best_v = np.nan, np.inf
        curve = []
        for c in grid:
            v = float(np.nanmean(crps_gaussian(mu, c * sb, y)))
            curve.append((c, v))
            if v < best_v:
                best_v, best_c = v, c
        return best_c, best_v, curve

    print("\n--- CRPS-optimal multiplier on the RAW LOO sigma, per frame ---")
    diag = []
    for lbl, df, mucol, rawcol, ycol, cur in (
        ("A2 rp3 RoS-average", SP_a_sc, "proj", "sigma_decision", "realized", 1.00),
        ("B2 rp3 single-start", SP_b_sc, "xfp_rp3_per_start", "xfp_rp3_sigma_raw",
         "actual", 2.41),
    ):
        c, v, _ = crps_optimal_scale(df[mucol], df[rawcol], df[ycol])
        cur_v = float(np.nanmean(crps_gaussian(df[mucol], cur * df[rawcol], df[ycol])))
        diag.append({"frame": lbl, "n": len(df), "c_star": round(float(c), 2),
                     "CRPS_at_c_star": round(v, 5),
                     "band_in_use": cur, "CRPS_at_band_in_use": round(cur_v, 5),
                     "loss_vs_optimum_%": round((cur_v / v - 1) * 100, 2)})
    print(pd.DataFrame(diag).to_string(index=False))
    print(f"\n  mean forward GS per RoS row = {SP_a_sc['fwd_events'].mean():.2f} "
          f"-> sqrt(k) = {np.sqrt(SP_a_sc['fwd_events'].mean()):.2f}")
    print("  (a k-start AVERAGE has ~1/sqrt(k) the SD of a single start, which is")
    print("   why one alpha cannot serve both frames.)")

    print("\n--- rh3: what the HITTER MC path actually draws ---")
    print("  build_matchup_dashboard.GLOBAL_SIGMA_PA_FP = 0.517 is the empirical")
    print("  per-PA OUTCOME sigma (== hitter_sigma_calibration.global_sigma_per_pa),")
    print("  scaled by batter_sigma_factor. It is NOT xfp_rh3_sigma (a rate-CI).")
    hb = H_b_sc.copy()
    for tag, s_pa in (("outcome_sigma_global", 0.517 * np.ones(len(hb))),
                      ("outcome_sigma_hetero", 0.517 * hb["batter_sigma_factor"].to_numpy(float))):
        s_rate = s_pa / np.sqrt(hb["pa_game"].to_numpy(float))
        lo, hi = band_edges(hb["xfp_rh3_per_pa"].to_numpy(float), s_rate)
        blk = score_block(hb["xfp_rh3_per_pa"], s_rate, hb["actual"], lo, hi)
        print("  " + str(cell_summary(f"B1-posthoc consumer band :: {tag}", blk)))
    for tag, col in (("rh3_CI_global", "xfp_rh3_sigma_global"),
                     ("rh3_CI_hetero", "xfp_rh3_sigma_hetero")):
        print(f"  (for contrast) mean {tag} = {hb[col].mean():.4f} per-PA vs "
              f"consumer per-PA-rate sigma "
              f"{float(np.mean(0.517 / np.sqrt(hb['pa_game']))):.4f}")
    s_rate = 0.517 / np.sqrt(hb["pa_game"].to_numpy(float))
    c_h, v_h, _ = crps_optimal_scale(hb["xfp_rh3_per_pa"], s_rate, hb["actual"])
    print(f"  CRPS-optimal multiplier on the consumer band: c*={c_h:.2f} "
          f"(CRPS {v_h:.5f} vs {0.53959:.5f} at c=1)")
    r = hb["actual"].to_numpy(float)
    print(f"  empirical single-game per-PA rate: sd={r.std():.4f} "
          f"mean={r.mean():.4f} median={np.median(r):.4f} "
          f"skew={float(pd.Series(r).skew()):.2f} "
          f"share_exactly_0={(r == 0).mean()*100:.1f}% "
          f"share_<=0={(r <= 0).mean()*100:.1f}%")
    print("  -> the single-game per-PA rate is discrete, zero-inflated and right-")
    print("     skewed; a symmetric Gaussian 50% band is the WRONG diagnostic for")
    print("     it. MC consumers sum over games (CLT applies at the weekly total),")
    print("     so this row-level coverage does NOT indict P(win).")

    # ---- BUG VERIFICATION (post-hoc; found while running the above) ---- #
    print("\n" + "=" * 78)
    print("BUG VERIFICATION — hitter per-game variance in the matchup MC")
    print("matchup_projection.project_hitter (src/plv_clone/matchup_projection.py")
    print("line 258):  sigma2 = n * (sigma_pa**2) * ppg,  sigma_pa = 0.517*factor")
    print("=" * 78)
    panel = pd.read_parquet(ROOT / "data/research/validation_runs/hitter_boom_bust_panel.parquet")
    panel = panel.dropna(subset=["fp_proxy", "PA"])
    panel = panel[panel["PA"] > 0]
    panel["rate"] = panel["fp_proxy"].astype(float) / panel["PA"].astype(float)
    bm = (panel.groupby("batter")
          .apply(lambda s: np.average(s["rate"], weights=s["PA"].astype(float)),
                 include_groups=False))
    panel = panel.join(bm.rename("bmean"), on="batter")
    res = panel["rate"] - panel["bmean"]
    w = panel["PA"].astype(float).to_numpy()
    pa_wrms = float(np.sqrt(np.average(res ** 2, weights=w)))
    unw_sd = float(panel["rate"].std())
    game_sd = float(panel["fp_proxy"].std())
    mean_pa = float(panel["PA"].mean())
    print(f"  panel: {len(panel)} batter-games, mean PA/game = {mean_pa:.3f}")
    print(f"  PA-weighted RMS of per-game-RATE residual = {pa_wrms:.4f}  "
          f"<-- this is the stored 'global_sigma_per_pa' (0.517)")
    print(f"  UNWEIGHTED SD of the per-game RATE           = {unw_sd:.4f}")
    print("  -> the two are the SAME number. The PA-weighting does NOT convert a")
    print("     game rate into a per-PA sigma, so 0.517 is a per-GAME-RATE sigma")
    print("     that is being consumed as if it were a per-PA sigma.")
    print(f"\n  TRUTH: empirical SD of per-game hitter FP = {game_sd:.4f} FP/g")
    cur = 0.517 * np.sqrt(3.5)
    fixed_35 = 0.517 * 3.5
    fixed_true = 0.517 * mean_pa
    print(f"  current code   sigma_g = 0.517*sqrt(3.5)      = {cur:.4f}  "
          f"(variance understated {(game_sd/cur)**2:.2f}x)")
    print(f"  ppg^2 scaling  sigma_g = 0.517*3.5            = {fixed_35:.4f}")
    print(f"  ppg^2 @ true   sigma_g = 0.517*{mean_pa:.2f}         = {fixed_true:.4f}  "
          f"-> matches the empirical {game_sd:.3f} to "
          f"{abs(fixed_true/game_sd-1)*100:.1f}%")
    print(f"  legacy const   sigma_g = 3.5                  = 3.5000  "
          f"(variance OVERstated {(3.5/game_sd)**2:.2f}x)")
    print("\n  => sigma2 needs ppg SQUARED, not ppg. The 'improved' hetero path is")
    print("     ~2.4x too NARROW in sigma (~5.7x in variance); the legacy constant")
    print("     it replaced was closer to the truth. This makes matchup P(win),")
    print("     run_matchup_leverage and run_season_sim OVERCONFIDENT.")
    print("  NOT FIXED HERE — this study is measurement-only. Needs its own")
    print("     pre-registered run before any production sigma changes.")

    # ---- persist panels ---- #
    for nm, df in (("crps_panelA_hitters", H_a_sc), ("crps_panelA_starters", SP_a_sc),
                   ("crps_panelB_hitters", H_b_sc), ("crps_panelB_starters", SP_b_sc)):
        df.to_csv(OUTDIR / f"_{nm}.csv", index=False)
    ptab.to_csv(OUTDIR / "_crps_contrasts.csv", index=False)
    pd.DataFrame(primary_rows).to_csv(OUTDIR / "_crps_primary_cells.csv", index=False)
    pd.DataFrame(slice_rows).to_csv(OUTDIR / "_crps_slices.csv", index=False)
    print(f"\nWrote panels + tables to {OUTDIR}/_crps_*.csv")
    print("\nRP / rprs2: NO CRPS COMPUTED — declared unscorable in-season "
          "(full-season-total projection vs season-to-date actual).")


if __name__ == "__main__":
    main()

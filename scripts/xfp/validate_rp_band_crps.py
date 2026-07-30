"""I4 — distributional calibration of the RELIEVER band, single-appearance frame.

Pre-registration: data/research/validation_runs/rp_band_crps_2026-07-30.md

MEASUREMENT ONLY.  This script writes nothing outside
``data/research/validation_runs/`` and imports production modules read-only.
It must never mutate ``SIGMA_PER_RP_GAME``, ``xfp_rprs2_projections.csv``, or
any model bundle.

Why this study exists
---------------------
``band_crps_calibration_2026-07-29.md`` declared rprs2 UNSCORABLE in-season
because rprs2 publishes a rest-of-season TOTAL band that cannot be scored
against a partial-season actual.  That is correct for the RoS frame and
irrelevant for the frame the Monte Carlo actually draws in:
``leverage_engine._rp_total_draws`` draws ONE APPEARANCE at a time, so a
single-appearance panel has no frame mismatch at all.

What production actually does (verified by reading, not assumed):

* ``build_matchup_dashboard.py:568`` derives ``(xfp_p75 - xfp_p25)/1.35`` into
  ``rprs2_map[nk]['sigma']`` — and **never reads it**.  The RP branch consumes
  only ``role`` / ``mlbam`` / ``xfp_ros``.
* The scale that reaches the MC is the flat constant
  ``SIGMA_PER_RP_GAME = 2.5``: ``project_rp`` sets
  ``sigma2 = expected_appearances * 2.5**2`` and ``leverage_engine.py:388``
  inverts it back to ``sigma_app = sqrt(sigma2/units) == 2.5``.
* The location is ``(xfp_ros / days_remaining_season) / 0.35``.

So the incumbent forecast is ``N(mu_PROD, 2.5)`` per appearance, blended with an
empirical bootstrap by ``_blend_draws``.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RESEARCH = ROOT / "data" / "research"
OUTDIR = RESEARCH / "validation_runs"
HIST = RESEARCH / "player_projection_history.parquet"
BOX_P = RESEARCH / "xfp_cache" / "boxscore_pitchers.parquet"
RPRS2 = ROOT / "data" / "outputs" / "xfp_rprs2_projections.csv"

# ── production constants, mirrored (values asserted against source at runtime) ─
SIGMA_PER_RP_GAME = 2.5          # build_matchup_dashboard.py:343
DEFAULT_RP_APP_RATE = 0.35       # MatchupConfig.default_rp_app_rate
SEASON_END = pd.Timestamp("2026-09-28")
K_PRIOR_RP = 10                  # leverage_engine.K_PRIOR_RP
EMP_LAST_N_RP = 20               # leverage_engine.EMP_LAST_N['RP']

Z25 = 0.6745
Z10 = 1.2816
N_BOOT = 2000
SEED = 20260730
MIN_CLUSTERS = 200               # Rule 5 floor, declared
ECON_FLOOR = 0.02                # 2% relative CRPS, declared
FDR_Q = 0.05
TRAIN_FRAC = 0.60                # first 60% of snapshot dates
C_GRID = np.round(np.arange(0.40, 4.0001, 0.02), 4)
N_MIX_DRAWS = 2000               # ensemble size for the mixture CRPS

_SQRT_PI_INV = 1.0 / math.sqrt(math.pi)


# --------------------------------------------------------------------------- #
# Proper scoring rules
# --------------------------------------------------------------------------- #
def crps_gaussian(mu, sigma, y):
    """Closed-form CRPS of N(mu, sigma) vs y (Gneiting & Raftery 2007 eq. 21).

    NaN where sigma <= 0 or any input is non-finite.  Callers DROP those rows
    and report the count — sigma is never silently floored (House Rule 1).
    """
    mu = np.asarray(mu, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    y = np.asarray(y, dtype=float)
    mu, sigma, y = np.broadcast_arrays(mu, sigma, y)
    ok = np.isfinite(mu) & np.isfinite(sigma) & np.isfinite(y) & (sigma > 0)
    out = np.full(mu.shape, np.nan, dtype=float)
    if not ok.any():
        return out
    z = (y[ok] - mu[ok]) / sigma[ok]
    out[ok] = sigma[ok] * (z * (2.0 * norm.cdf(z) - 1.0)
                           + 2.0 * norm.pdf(z) - _SQRT_PI_INV)
    return out


def crps_ensemble(samples, y):
    """Fair (unbiased-shape) ensemble CRPS, O(m log m) per row.

        CRPS = (1/m) sum_j |x_j - y| - (1/(2 m^2)) sum_j sum_k |x_j - x_k|

    with the sorted identity
        sum_j sum_k |x_j - x_k| = 2 * sum_j (2j - m - 1) x_(j),  j = 1..m.

    ``samples`` is (n_rows, m); ``y`` is (n_rows,).  Returns (n_rows,).
    """
    x = np.asarray(samples, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.ndim != 2:
        raise ValueError(f"samples must be 2-D (n_rows, m), got shape {x.shape}")
    if x.shape[0] != y.shape[0]:
        raise ValueError(f"row mismatch: samples {x.shape[0]} vs y {y.shape[0]}")
    if not np.isfinite(x).all():
        raise ValueError("non-finite value in ensemble samples")
    m = x.shape[1]
    term1 = np.abs(x - y[:, None]).mean(axis=1)
    xs = np.sort(x, axis=1)
    j = np.arange(1, m + 1, dtype=float)
    pair_sum = 2.0 * (xs * (2.0 * j - m - 1.0)).sum(axis=1)
    return term1 - pair_sum / (2.0 * m * m)


def pinball(y, qhat, q):
    d = np.asarray(y, dtype=float) - np.asarray(qhat, dtype=float)
    return np.maximum(q * d, (q - 1.0) * d)


def implied_per_appearance_sigma(p25, p75, n_exp):
    """RoS-total band -> per-appearance sigma under declared assumption A1.

    ``sigma_total = (p75 - p25) / 1.35``  (normal-IQR identity — exactly the
    algebra at ``build_matchup_dashboard.py:568``), then
    ``sigma_app = sigma_total / sqrt(n_exp)``.

    RAISES on a non-positive band width or a non-positive expected-appearance
    count instead of returning a negative/inf sigma.  The production derivation
    has no such guard, and ``xfp_rprs2_projections.csv`` really does ship rows
    with ``p75 < p25`` (the ``clip(lower=0)`` at ``rprs2.py:409`` breaks the IQR
    identity for low projections), so the silent path yields a NEGATIVE sigma.
    """
    width = float(p75) - float(p25)
    if not np.isfinite(width) or width <= 0:
        raise ValueError(
            f"non-positive rprs2 band width {width!r} (p25={p25!r}, p75={p75!r}): "
            "the normal-IQR identity does not hold for this row"
        )
    n = float(n_exp)
    if not np.isfinite(n) or n <= 0:
        raise ValueError(f"expected-appearance count must be > 0, got {n_exp!r}")
    return (width / 1.35) / math.sqrt(n)


# --------------------------------------------------------------------------- #
# Paired, player-clustered bootstrap + BH-FDR  (same machinery as B3)
# --------------------------------------------------------------------------- #
def paired_cluster_bootstrap(df, col_a, col_b, cluster_col,
                             n_boot=N_BOOT, seed=SEED):
    d = df.dropna(subset=[col_a, col_b, cluster_col])
    if d.empty:
        raise ValueError(f"empty paired panel for {col_a} vs {col_b}")
    uniq, inv = np.unique(d[cluster_col].to_numpy(), return_inverse=True)
    order = np.argsort(inv, kind="stable")
    inv_sorted = inv[order]
    starts = np.searchsorted(inv_sorted, np.arange(len(uniq)), side="left")
    ends = np.searchsorted(inv_sorted, np.arange(len(uniq)), side="right")
    rows_by_cluster = [order[starts[i]:ends[i]] for i in range(len(uniq))]

    a = d[col_a].to_numpy(float)
    b = d[col_b].to_numpy(float)
    rng = np.random.default_rng(seed)
    n_c = len(uniq)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        idx = np.concatenate([rows_by_cluster[j] for j in rng.integers(0, n_c, n_c)])
        diffs[i] = b[idx].mean() - a[idx].mean()
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    p = min(1.0, 2.0 * min(float((diffs >= 0).mean()), float((diffs <= 0).mean())))
    return {"diff": float(b.mean() - a.mean()),
            "ci_lo": float(lo), "ci_hi": float(hi),
            "p": max(p, 1.0 / (2.0 * n_boot)),
            "n_rows": int(len(d)), "n_clusters": int(n_c),
            "mean_a": float(a.mean()), "mean_b": float(b.mean())}


def bh_fdr(pvals, q=FDR_Q):
    p = np.asarray(pvals, dtype=float)
    m = len(p)
    order = np.argsort(p)
    passed = p[order] <= q * (np.arange(1, m + 1) / m)
    k = np.where(passed)[0]
    cutoff = p[order][k.max()] if len(k) else -1.0
    return p <= cutoff


# --------------------------------------------------------------------------- #
# Panel construction
# --------------------------------------------------------------------------- #
def measured_team_games_per_day(box: pd.DataFrame) -> float:
    """MEASURED 2026 team-games per team per calendar day (not assumed)."""
    per_day = box.groupby("game_date").apply(
        lambda d: d[["game_pk", "team_id"]].drop_duplicates().shape[0],
        include_groups=False,
    )
    if per_day.empty:
        raise ValueError("boxscore store has no dated rows")
    return float(per_day.mean()) / 30.0


def build_panel(verbose=True):
    """One row per (snapshot_date, reliever) -> FIRST relief appearance after it."""
    for p in (HIST, BOX_P, RPRS2):
        if not p.exists():
            raise FileNotFoundError(f"required input missing: {p}")

    hist = pd.read_parquet(HIST)
    need = {"snapshot_date", "player_type", "mlbam_id", "proj_per", "proj_volume"}
    missing = need - set(hist.columns)
    if missing:
        raise KeyError(f"player_projection_history is missing {sorted(missing)}")

    rp = hist[hist["player_type"] == "RP"].copy()
    rp = rp[rp["mlbam_id"].notna()].copy()
    rp["mlbam_id"] = rp["mlbam_id"].astype(int)
    rp["sd"] = pd.to_datetime(rp["snapshot_date"].astype(str))

    box = pd.read_parquet(BOX_P)
    box["game_date"] = box["game_date"].astype(str)
    relief = box[box["gs"] == 0][["mlbam_id", "game_date", "game_pk", "fp_rp"]].copy()
    relief["ev"] = pd.to_datetime(relief["game_date"])
    relief["mlbam_id"] = relief["mlbam_id"].astype(int)

    gpd = measured_team_games_per_day(box)

    left = (rp[["sd", "snapshot_date", "mlbam_id", "proj_per", "proj_volume"]]
            .sort_values("sd"))
    right = relief.sort_values("ev")
    panel = pd.merge_asof(left, right, left_on="sd", right_on="ev",
                          by="mlbam_id", direction="forward",
                          allow_exact_matches=False)

    n_all = len(panel)
    panel = panel[panel["ev"].notna()].copy()
    n_matched = len(panel)

    panel["days_rem"] = (SEASON_END - panel["sd"]).dt.days.clip(lower=1)
    panel["gap_days"] = (panel["ev"] - panel["sd"]).dt.days
    panel["y"] = panel["fp_rp"].astype(float)

    # location A2: production formula, verbatim from matchup_projection.project_rp
    panel["mu_prod"] = (panel["proj_per"] / panel["days_rem"]) / DEFAULT_RP_APP_RATE
    # expected remaining appearances under the measured league game rate
    panel["n_exp"] = panel["proj_volume"] * panel["days_rem"] * gpd
    panel["mu_vol"] = np.where(panel["n_exp"] > 0,
                               panel["proj_per"] / panel["n_exp"], np.nan)

    # a negative RoS total has no per-appearance interpretation -> DROP, count it
    n_before = len(panel)
    panel = panel[panel["proj_per"] > 0].copy()
    n_dropped_neg = n_before - len(panel)

    if verbose:
        print(f"  measured team-games/team/day (2026) = {gpd:.4f}")
        print(f"  snapshot RP rows {n_all:,} -> matched to a next appearance "
              f"{n_matched:,} -> proj_per>0 {len(panel):,} "
              f"(dropped {n_dropped_neg} non-positive RoS)")
        print(f"  clusters (relievers) = {panel['mlbam_id'].nunique()}, "
              f"snapshot dates = {panel['snapshot_date'].nunique()}")
    panel.attrs["gpd"] = gpd
    panel.attrs["n_dropped_neg"] = n_dropped_neg
    return panel


def attach_band(panel: pd.DataFrame, verbose=True) -> pd.DataFrame:
    """Two band-derived scales.

    ``sigma_band``     — S_BAND: RoS band -> per-appearance under assumption A1
                         (divide by sqrt(N_exp)).
    ``sigma_band_raw`` — the value ``build_matchup_dashboard.py:568`` actually
                         stores, ``(xfp_p75 - xfp_p25)/1.35`` on the FULL-YEAR
                         band with NO frame conversion.  That is dead in the
                         dashboard but LIVE in ``run_season_sim.py:288-290``,
                         which reads it straight into ``sigma_app`` — a
                         per-appearance slot.  Scored so the cost is a number.
    """
    rp = pd.read_csv(RPRS2)
    for c in ("pitcher", "xfp_ros_p25", "xfp_ros_p75", "xfp_p25", "xfp_p75"):
        if c not in rp.columns:
            raise KeyError(f"xfp_rprs2_projections.csv missing column {c!r}")
    rp = rp[rp["pitcher"].notna()].copy()
    rp["pitcher"] = rp["pitcher"].astype(int)
    band = rp.set_index("pitcher")[["xfp_ros_p25", "xfp_ros_p75",
                                    "xfp_p25", "xfp_p75"]]

    p25 = panel["mlbam_id"].map(band["xfp_ros_p25"]).to_numpy()
    p75 = panel["mlbam_id"].map(band["xfp_ros_p75"]).to_numpy()
    fy25 = panel["mlbam_id"].map(band["xfp_p25"]).to_numpy()
    fy75 = panel["mlbam_id"].map(band["xfp_p75"]).to_numpy()
    n_exp = panel["n_exp"].to_numpy()

    out = np.full(len(panel), np.nan)
    n_nomatch = n_bad_width = n_bad_nexp = 0
    for i in range(len(panel)):
        if not (np.isfinite(p25[i]) and np.isfinite(p75[i])):
            n_nomatch += 1
            continue
        if not (np.isfinite(p75[i] - p25[i]) and (p75[i] - p25[i]) > 0):
            n_bad_width += 1      # counted, never floored (House Rule 1)
            continue
        if not (np.isfinite(n_exp[i]) and n_exp[i] > 0):
            n_bad_nexp += 1
            continue
        out[i] = implied_per_appearance_sigma(p25[i], p75[i], n_exp[i])

    raw = (fy75 - fy25) / 1.35            # exactly the dashboard's expression
    raw = np.where(np.isfinite(raw), raw, np.nan)

    panel = panel.copy()
    panel["sigma_band"] = out
    panel["sigma_band_raw"] = raw
    if verbose:
        print(f"  S_BAND (A1): usable {int(np.isfinite(out).sum()):,} rows | "
              f"{n_nomatch:,} no published band | "
              f"{n_bad_width:,} rejected: p75<=p25 | "
              f"{n_bad_nexp:,} rejected: no volume -> N_exp<=0")
        pos = raw[np.isfinite(raw) & (raw > 0)]
        print(f"  S_BAND_RAW (run_season_sim's actual sigma_app): "
              f"usable {len(pos):,} rows, mean {pos.mean():.2f} FP, "
              f"median {np.median(pos):.2f} FP")
    panel.attrs["band_nomatch"] = n_nomatch
    panel.attrs["band_bad_width"] = n_bad_width
    panel.attrs["band_bad_nexp"] = n_bad_nexp
    return panel


def attach_prior_history(panel: pd.DataFrame) -> pd.DataFrame:
    """Leakage-safe last-20 relief FP strictly BEFORE each snapshot date.

    Mirrors ``leverage_engine.emp_series(mlbam, 'RP', before=..., last_n=20)``.
    """
    box = pd.read_parquet(BOX_P)
    box["game_date"] = box["game_date"].astype(str)
    relief = box[box["gs"] == 0][["mlbam_id", "game_date", "game_pk", "fp_rp"]].copy()
    relief["mlbam_id"] = relief["mlbam_id"].astype(int)
    relief = relief.sort_values(["mlbam_id", "game_date", "game_pk"])
    by_pid = {pid: (g["game_date"].to_numpy(), g["fp_rp"].to_numpy(float))
              for pid, g in relief.groupby("mlbam_id")}

    hist_list, n_emp = [], []
    for pid, sd in zip(panel["mlbam_id"].to_numpy(),
                       panel["snapshot_date"].astype(str).to_numpy()):
        dates, vals = by_pid.get(pid, (np.array([]), np.array([])))
        k = int(np.searchsorted(dates, sd, side="left")) if len(dates) else 0
        prior = vals[:k][-EMP_LAST_N_RP:]
        hist_list.append(prior)
        n_emp.append(len(prior))
    panel = panel.copy()
    panel["n_emp"] = n_emp
    panel.attrs["emp"] = hist_list
    return panel


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def score_gaussian(mu, sigma, y):
    mu = np.asarray(mu, float)
    sigma = np.asarray(sigma, float)
    y = np.asarray(y, float)
    lo, hi = mu - Z25 * sigma, mu + Z25 * sigma
    return pd.DataFrame({
        "crps": crps_gaussian(mu, sigma, y),
        "pin25": pinball(y, lo, 0.25),
        "pin75": pinball(y, hi, 0.75),
        "cov50": ((y >= lo) & (y <= hi)).astype(float),
        "cov80": ((y >= mu - Z10 * sigma) & (y <= mu + Z10 * sigma)).astype(float),
    })


def mixture_samples(panel, mu, sigma, rng, m=N_MIX_DRAWS):
    """Draw the EXACT production mixture `_blend_draws` produces, per row.

    w = n_emp/(n_emp+K_PRIOR_RP); with prob w bootstrap the pitcher's own prior
    relief FP, else N(mu, sigma).
    """
    emp = panel.attrs["emp"]
    n = len(panel)
    mu = np.asarray(mu, float)
    sigma = np.asarray(sigma, float)
    out = rng.normal(mu[:, None], np.maximum(sigma, 1e-6)[:, None], size=(n, m))
    n_emp = panel["n_emp"].to_numpy()
    w = n_emp / (n_emp + K_PRIOR_RP)
    u = rng.random((n, m))
    for i in range(n):
        if n_emp[i] == 0:
            continue
        mask = u[i] < w[i]
        k = int(mask.sum())
        if k:
            out[i, mask] = rng.choice(emp[i], size=k, replace=True)
    return out


def mixture_crps(panel, mu, sigma, seed):
    rng = np.random.default_rng(seed)
    y = panel["y"].to_numpy(float)
    n = len(panel)
    chunk = 2000
    res = np.empty(n)
    for s in range(0, n, chunk):
        e = min(s + chunk, n)
        sub = panel.iloc[s:e]
        sub.attrs["emp"] = panel.attrs["emp"][s:e]
        smp = mixture_samples(sub, mu[s:e], sigma[s:e], rng)
        res[s:e] = crps_ensemble(smp, y[s:e])
    return res


def c_star(panel, rows, mu_col, kind, seed=SEED, grid=C_GRID):
    """CRPS-minimizing multiplier on SIGMA_PER_RP_GAME over `grid`.

    ALIGNMENT BUG FIXED 2026-07-30 (found by adversarial review). `panel.loc[rows]`
    is a LABEL selection, but pandas propagates `.attrs` through it unchanged — so
    the subset frame carried the FULL `emp` list, and `mixture_crps` then sliced
    that list POSITIONALLY (`attrs['emp'][s:e]`) against a non-contiguous subset.
    Every row past the first got a different pitcher's appearance history, and it
    was silent because the slice LENGTH still matched: 3,515 of 3,516 TEST rows
    were mispaired. TRAIN escaped only because it happens to be a contiguous
    prefix. Re-aligning here (the same pattern already used for `t_mix` below)
    moved the mixture TEST result from c*=1.30 / CRPS 2.31112 to
    c*=1.50 / CRPS 2.17215 — which makes c* MORE stable across folds, not less.
    """
    sub = panel.loc[rows].copy()
    if "emp" in panel.attrs:
        pos = panel.index.get_indexer(sub.index)
        if (pos < 0).any():
            raise KeyError(
                "c_star: some selected rows are not in the panel index; refusing "
                "to pair empirical histories positionally")
        sub.attrs["emp"] = [panel.attrs["emp"][i] for i in pos]
    mu = sub[mu_col].to_numpy(float)
    y = sub["y"].to_numpy(float)
    curve = []
    for c in grid:
        s = np.full(len(sub), c * SIGMA_PER_RP_GAME)
        if kind == "gauss":
            v = crps_gaussian(mu, s, y)
        else:
            v = mixture_crps(sub, mu, s, seed)
        curve.append(float(np.nanmean(v)))
    curve = np.asarray(curve)
    i = int(np.nanargmin(curve))
    return float(grid[i]), float(curve[i]), pd.DataFrame({"c": grid, "crps": curve})


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    print("=" * 78)
    print("I4 — RP predictive band, single-appearance frame (CRPS/pinball)")
    print("pre-reg: data/research/validation_runs/rp_band_crps_2026-07-30.md")
    print("=" * 78)

    print("\n[1] panel")
    panel = build_panel()
    panel = attach_band(panel)
    panel = attach_prior_history(panel)
    emp_all = panel.attrs["emp"]

    dates = sorted(panel["snapshot_date"].astype(str).unique())
    n_train = int(round(len(dates) * TRAIN_FRAC))
    train_dates, test_dates = set(dates[:n_train]), set(dates[n_train:])
    sd = panel["snapshot_date"].astype(str)
    panel["split"] = np.where(sd.isin(train_dates), "train", "test")
    print(f"  TRAIN {len(train_dates)} dates ({dates[0]}..{dates[n_train-1]})  "
          f"n={int((panel['split']=='train').sum()):,}")
    print(f"  TEST  {len(test_dates)} dates ({dates[n_train]}..{dates[-1]})  "
          f"n={int((panel['split']=='test').sum()):,}")

    tr = panel["split"] == "train"
    te = panel["split"] == "test"

    # model-free reference
    box = pd.read_parquet(BOX_P)
    rel = box[box["gs"] == 0].copy()
    pm = rel.groupby("mlbam_id")["fp_rp"].transform("mean")
    within_sd = float((rel["fp_rp"] - pm).std())
    print(f"\n  reference: pooled WITHIN-pitcher per-appearance SD = {within_sd:.4f} FP")
    print(f"  reference: production draws sigma = {SIGMA_PER_RP_GAME} FP")
    print(f"  reference: panel y mean={panel['y'].mean():.4f} sd={panel['y'].std():.4f}; "
          f"mu_prod mean={panel['mu_prod'].mean():.4f}")

    # ---------------- c* search on TRAIN ----------------
    print("\n[2] c* search (TRAIN only)")
    c_g, crps_g, curve_g = c_star(panel, tr, "mu_prod", "gauss")
    print(f"  Gaussian  c*_train = {c_g:.2f}  (sigma = {c_g*SIGMA_PER_RP_GAME:.3f} FP), "
          f"train CRPS {crps_g:.5f}")
    # mixture c* on a coarser grid (each point is a 2000-draw ensemble)
    coarse = np.round(np.arange(0.40, 4.0001, 0.10), 4)
    c_m, crps_m, curve_m = c_star(panel, tr, "mu_prod", "mix", grid=coarse)
    print(f"  Mixture   c*_train = {c_m:.2f}  (sigma = {c_m*SIGMA_PER_RP_GAME:.3f} FP), "
          f"train CRPS {crps_m:.5f}")
    curve_g.to_csv(OUTDIR / "_rp_crps_curve_gauss.csv", index=False)
    curve_m.to_csv(OUTDIR / "_rp_crps_curve_mix.csv", index=False)

    # TEST-side curve (descriptive: is c* stable out of sample?)
    c_g_te, _, curve_g_te = c_star(panel, te, "mu_prod", "gauss")
    c_m_te, _, curve_m_te = c_star(panel, te, "mu_prod", "mix", grid=coarse)
    print(f"  [descriptive] c* refit on TEST: Gaussian {c_g_te:.2f}, mixture {c_m_te:.2f}")
    curve_g_te.to_csv(OUTDIR / "_rp_crps_curve_gauss_test.csv", index=False)
    curve_m_te.to_csv(OUTDIR / "_rp_crps_curve_mix_test.csv", index=False)

    # ---------------- primary cells ----------------
    print("\n[3] primary cells")
    rows, contrasts = [], []

    def add_cell(name, sc, tag):
        d = sc.dropna(subset=["crps"])
        rows.append({"cell": name, "band": tag, "n": len(d),
                     "CRPS": round(float(d["crps"].mean()), 5),
                     "pin25": round(float(d["pin25"].mean()), 5),
                     "pin75": round(float(d["pin75"].mean()), 5),
                     "cov50_%": round(float(d["cov50"].mean()) * 100, 1),
                     "cov80_%": round(float(d["cov80"].mean()) * 100, 1)})

    # R1 — Gaussian, TEST, prod sigma vs c*_train sigma
    t = panel.loc[te]
    mu_t = t["mu_prod"].to_numpy(float)
    y_t = t["y"].to_numpy(float)
    s_prod = np.full(len(t), SIGMA_PER_RP_GAME)
    s_cstar = np.full(len(t), c_g * SIGMA_PER_RP_GAME)
    sc_a = score_gaussian(mu_t, s_prod, y_t)
    sc_b = score_gaussian(mu_t, s_cstar, y_t)
    add_cell("R1 gauss TEST", sc_a, f"prod sigma={SIGMA_PER_RP_GAME}")
    add_cell("R1 gauss TEST", sc_b, f"c*={c_g:.2f} sigma={c_g*SIGMA_PER_RP_GAME:.2f}")
    r1 = pd.DataFrame({"a": sc_a["crps"].to_numpy(), "b": sc_b["crps"].to_numpy(),
                       "cl": t["mlbam_id"].to_numpy()})
    contrasts.append(("R1 prod->c* (gauss, TEST)",
                      paired_cluster_bootstrap(r1, "a", "b", "cl")))

    # R2 — Gaussian, all rows with a usable S_BAND, prod sigma vs S_BAND
    bmask = panel["sigma_band"].notna()
    bsub = panel.loc[bmask]
    mu_b = bsub["mu_prod"].to_numpy(float)
    y_b = bsub["y"].to_numpy(float)
    sc_a2 = score_gaussian(mu_b, np.full(len(bsub), SIGMA_PER_RP_GAME), y_b)
    sc_b2 = score_gaussian(mu_b, bsub["sigma_band"].to_numpy(float), y_b)
    add_cell("R2 gauss BAND-rows", sc_a2, f"prod sigma={SIGMA_PER_RP_GAME}")
    add_cell("R2 gauss BAND-rows", sc_b2, "S_BAND (A1)")
    r2 = pd.DataFrame({"a": sc_a2["crps"].to_numpy(), "b": sc_b2["crps"].to_numpy(),
                       "cl": bsub["mlbam_id"].to_numpy()})
    contrasts.append(("R2 prod->S_BAND (gauss)",
                      paired_cluster_bootstrap(r2, "a", "b", "cl")))
    print(f"  S_BAND mean per-appearance sigma = "
          f"{float(bsub['sigma_band'].mean()):.3f} FP "
          f"(median {float(bsub['sigma_band'].median()):.3f})")

    # R2b (DESCRIPTIVE, declared post-hoc): run_season_sim's actual sigma_app —
    # the full-year band sigma used verbatim as a per-appearance scale.
    rawmask = panel["sigma_band_raw"].notna() & (panel["sigma_band_raw"] > 0)
    rsub = panel.loc[rawmask]
    y_r = rsub["y"].to_numpy(float)
    mu_r = rsub["mu_prod"].to_numpy(float)
    sc_a2b = score_gaussian(mu_r, np.full(len(rsub), SIGMA_PER_RP_GAME), y_r)
    sc_b2b = score_gaussian(mu_r, rsub["sigma_band_raw"].to_numpy(float), y_r)
    add_cell("R2b* gauss RAW-band", sc_a2b, f"prod sigma={SIGMA_PER_RP_GAME}")
    add_cell("R2b* gauss RAW-band", sc_b2b, "S_BAND_RAW (season_sim)")
    r2b = pd.DataFrame({"a": sc_a2b["crps"].to_numpy(), "b": sc_b2b["crps"].to_numpy(),
                        "cl": rsub["mlbam_id"].to_numpy()})
    boot_2b = paired_cluster_bootstrap(r2b, "a", "b", "cl")
    print(f"  R2b* [DESCRIPTIVE, not gated, not in FDR] prod->S_BAND_RAW: "
          f"CRPS {boot_2b['mean_a']:.4f} -> {boot_2b['mean_b']:.4f} "
          f"({boot_2b['diff'] / boot_2b['mean_a'] * 100:+.1f}%), "
          f"n={boot_2b['n_rows']:,} clusters={boot_2b['n_clusters']}")

    # R3 — production MIXTURE, TEST, prod sigma vs c*mix_train sigma
    t_mix = panel.loc[te].copy()
    t_mix.attrs["emp"] = [emp_all[i] for i in np.where(te.to_numpy())[0]]
    mix_a = mixture_crps(t_mix, mu_t, s_prod, SEED)
    mix_b = mixture_crps(t_mix, mu_t, np.full(len(t_mix), c_m * SIGMA_PER_RP_GAME),
                         SEED)
    rows.append({"cell": "R3 MIXTURE TEST", "band": f"prod sigma={SIGMA_PER_RP_GAME}",
                 "n": len(mix_a), "CRPS": round(float(np.mean(mix_a)), 5),
                 "pin25": np.nan, "pin75": np.nan,
                 "cov50_%": np.nan, "cov80_%": np.nan})
    rows.append({"cell": "R3 MIXTURE TEST", "band": f"c*mix={c_m:.2f}",
                 "n": len(mix_b), "CRPS": round(float(np.mean(mix_b)), 5),
                 "pin25": np.nan, "pin75": np.nan,
                 "cov50_%": np.nan, "cov80_%": np.nan})
    r3 = pd.DataFrame({"a": mix_a, "b": mix_b, "cl": t_mix["mlbam_id"].to_numpy()})
    contrasts.append(("R3 prod->c*mix (MIXTURE, TEST)",
                      paired_cluster_bootstrap(r3, "a", "b", "cl")))

    # R4 — location contrast, TEST rows with a volume-based mu, sigma fixed
    vmask = te & panel["mu_vol"].notna() & np.isfinite(panel["mu_vol"])
    v = panel.loc[vmask]
    y_v = v["y"].to_numpy(float)
    s_v = np.full(len(v), SIGMA_PER_RP_GAME)
    sc_a4 = score_gaussian(v["mu_prod"].to_numpy(float), s_v, y_v)
    sc_b4 = score_gaussian(v["mu_vol"].to_numpy(float), s_v, y_v)
    add_cell("R4 gauss TEST+vol", sc_a4, "mu_PROD")
    add_cell("R4 gauss TEST+vol", sc_b4, "mu_VOL")
    r4 = pd.DataFrame({"a": sc_a4["crps"].to_numpy(), "b": sc_b4["crps"].to_numpy(),
                       "cl": v["mlbam_id"].to_numpy()})
    contrasts.append(("R4 mu_PROD->mu_VOL (gauss, TEST)",
                      paired_cluster_bootstrap(r4, "a", "b", "cl")))

    cells = pd.DataFrame(rows)
    print("\n--- primary cells ---")
    print(cells.to_string(index=False))
    cells.to_csv(OUTDIR / "_rp_crps_primary_cells.csv", index=False)

    # ---------------- inference table ----------------
    ct = []
    for name, r in contrasts:
        rel = r["diff"] / r["mean_a"] if r["mean_a"] else np.nan
        ct.append({"contrast": name, "n_rows": r["n_rows"],
                   "n_clusters": r["n_clusters"],
                   "CRPS_A": round(r["mean_a"], 5), "CRPS_B": round(r["mean_b"], 5),
                   "dCRPS": round(r["diff"], 5), "rel_%": round(rel * 100, 2),
                   "ci_lo": round(r["ci_lo"], 5), "ci_hi": round(r["ci_hi"], 5),
                   "boot_p": r["p"],
                   "econ_pass": abs(rel) >= ECON_FLOOR,
                   "underpowered": r["n_clusters"] < MIN_CLUSTERS})
    ctd = pd.DataFrame(ct)
    ctd["bh_pass"] = bh_fdr(ctd["boot_p"].to_numpy())
    print("\n--- paired player-clustered bootstrap (2000 reps, seed 20260730) ---")
    print(ctd.to_string(index=False))
    ctd.to_csv(OUTDIR / "_rp_crps_contrasts.csv", index=False)

    # ---------------- R4 stopping rule ----------------
    d1 = abs(ctd.loc[ctd["contrast"].str.startswith("R1"), "dCRPS"].iloc[0])
    d4 = abs(ctd.loc[ctd["contrast"].str.startswith("R4"), "dCRPS"].iloc[0])
    confounded = d4 >= d1
    print(f"\n[4] R4 stopping rule: |dCRPS(R4)|={d4:.5f} vs |dCRPS(R1)|={d1:.5f} "
          f"-> {'CONFOUNDED (location dominates)' if confounded else 'sigma finding stands'}")

    # R4 robustness (DESCRIPTIVE): mu_VOL = xfp_ros / N_exp explodes when
    # proj_volume is near zero, so the R4 magnitude may be a tail artifact.
    # Restrict to rows with a non-degenerate expected-appearance count.
    for floor in (5.0, 10.0):
        m = vmask & (panel["n_exp"] >= floor)
        vv = panel.loc[m]
        if len(vv) < 50:
            print(f"  [R4 robustness] N_exp>={floor:g}: only {len(vv)} rows — skipped")
            continue
        sv = np.full(len(vv), SIGMA_PER_RP_GAME)
        aa = crps_gaussian(vv["mu_prod"].to_numpy(float), sv, vv["y"].to_numpy(float))
        bb = crps_gaussian(vv["mu_vol"].to_numpy(float), sv, vv["y"].to_numpy(float))
        rr = pd.DataFrame({"a": aa, "b": bb, "cl": vv["mlbam_id"].to_numpy()})
        bo = paired_cluster_bootstrap(rr, "a", "b", "cl")
        print(f"  [R4 robustness] N_exp>={floor:g}: n={bo['n_rows']:,} "
              f"clusters={bo['n_clusters']} dCRPS={bo['diff']:+.5f} "
              f"({bo['diff']/bo['mean_a']*100:+.2f}%) CI[{bo['ci_lo']:+.4f},"
              f"{bo['ci_hi']:+.4f}] p={bo['p']:.4f}")

    # ---------------- post-hoc: does the location bias drive c*? ------------
    # DECLARED POST-HOC (not pre-registered, not gated, not in the FDR set).
    # The R4 stopping rule only proves that ONE alternative location is worse.
    # It does not show mu_PROD is unbiased — and it is not. Fit the simplest
    # possible correction on TRAIN ONLY, apply to TEST, refit c*. If c* falls
    # materially, the pre-reg c* is absorbing mean error, which is exactly the
    # confounding the stopping rule was written to catch.
    print("\n[4b] POST-HOC location-bias diagnostic (TRAIN-fitted, TEST-applied)")
    tr_p = panel.loc[tr]
    add_off = float(tr_p["y"].mean() - tr_p["mu_prod"].mean())
    mul_off = (float(tr_p["y"].mean() / tr_p["mu_prod"].mean())
               if tr_p["mu_prod"].mean() else np.nan)
    print(f"  TRAIN bias: mean(y)={tr_p['y'].mean():.4f} "
          f"mean(mu_PROD)={tr_p['mu_prod'].mean():.4f} -> "
          f"additive {add_off:+.4f} FP, multiplicative x{mul_off:.4f}")
    for lbl, mu_adj in (("additive", panel["mu_prod"] + add_off),
                        ("multiplicative", panel["mu_prod"] * mul_off)):
        panel["_mu_adj"] = mu_adj
        c_adj, crps_adj, _ = c_star(panel, tr, "_mu_adj", "gauss")
        mu_te = panel.loc[te, "_mu_adj"].to_numpy(float)
        crps_te_prod = float(np.nanmean(crps_gaussian(mu_te, s_prod, y_t)))
        crps_te_star = float(np.nanmean(
            crps_gaussian(mu_te, np.full(len(t), c_adj * SIGMA_PER_RP_GAME), y_t)))
        print(f"  {lbl:15s}: c*_train {c_adj:.2f} (sigma {c_adj*SIGMA_PER_RP_GAME:.2f} FP) | "
              f"TEST CRPS at prod sigma {crps_te_prod:.5f}, at c* {crps_te_star:.5f} "
              f"({(crps_te_star - crps_te_prod) / crps_te_prod * 100:+.2f}%)")
    panel.drop(columns=["_mu_adj"], inplace=True)

    # ---------------- descriptive slices ----------------
    print("\n[5] descriptive slices (TEST, Gaussian, prod vs c*)")
    t2 = panel.loc[te].copy()
    t2["crps_prod"] = sc_a["crps"].to_numpy()
    t2["crps_cstar"] = sc_b["crps"].to_numpy()
    t2["cov50_prod"] = sc_a["cov50"].to_numpy()
    t2["cov50_cstar"] = sc_b["cov50"].to_numpy()
    t2["gap_bucket"] = pd.cut(t2["gap_days"], [0, 1, 3, 7, 999],
                              labels=["1d", "2-3d", "4-7d", "8+d"])
    t2["nemp_bucket"] = pd.cut(t2["n_emp"], [-1, 4, 9, 19, 999],
                               labels=["0-4", "5-9", "10-19", "20"])
    t2["tercile"] = pd.qcut(t2["mu_prod"], 3, labels=["T3_low", "T2_mid", "T1_high"])
    slices = []
    for key in ("gap_bucket", "nemp_bucket", "tercile"):
        for lv, g in t2.groupby(key, observed=True):
            slices.append({"slice": key, "level": str(lv), "n": len(g),
                           "clusters": g["mlbam_id"].nunique(),
                           "CRPS_prod": round(float(g["crps_prod"].mean()), 5),
                           "CRPS_cstar": round(float(g["crps_cstar"].mean()), 5),
                           "cov50_prod_%": round(float(g["cov50_prod"].mean()) * 100, 1),
                           "cov50_cstar_%": round(float(g["cov50_cstar"].mean()) * 100, 1)})
    sl = pd.DataFrame(slices)
    print(sl.to_string(index=False))
    sl.to_csv(OUTDIR / "_rp_crps_slices.csv", index=False)

    # ---------------- the dead / negative-width band rows ----------------
    rp_csv = pd.read_csv(RPRS2)
    w = rp_csv["xfp_ros_p75"] - rp_csv["xfp_ros_p25"]
    bad = rp_csv.loc[w <= 0, ["name_api", "xfp_ros", "xfp_ros_p25", "xfp_ros_p75"]]
    print(f"\n[6] published rprs2 rows with p75 <= p25: {len(bad)} of {len(rp_csv)}")
    if len(bad):
        print(bad.to_string(index=False))
        print("     naive (p75-p25)/1.35 for these =",
              np.round(((bad['xfp_ros_p75'] - bad['xfp_ros_p25']) / 1.35).to_numpy(), 2))

    panel.drop(columns=[c for c in ("sd", "ev") if c in panel.columns]).to_csv(
        OUTDIR / "_rp_crps_panel.csv", index=False)
    print("\nwrote _rp_crps_{panel,primary_cells,contrasts,slices,curve_*}.csv")
    return {"c_gauss": c_g, "c_mix": c_m, "confounded": confounded,
            "cells": cells, "contrasts": ctd}


if __name__ == "__main__":
    main()

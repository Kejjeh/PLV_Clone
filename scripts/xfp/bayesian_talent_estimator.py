"""
bayesian_talent_estimator.py
Bayesian posterior talent estimation using conjugate normal-normal update.

For each hitter:
  Prior:       career rolling-150 xwOBA distribution (mean μ₀, variance σ₀²)
  Likelihood:  observed recent L21d PA events (observed mean x̄, n observations)
  Posterior:   updated estimate of "true talent level" with 95% credible interval

Recency weighting (v2): the prior mean and variance are computed using
exponential decay weights:
  w_i = exp(-decay_lambda * years_ago_i)
where years_ago_i = (today - window_end_date_i) / 365.25.
Default decay_lambda=0.20 (half-life ~3.5 years). Use 0.0 for unweighted.
"""

import sys
import math
from pathlib import Path
from datetime import date

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

CACHE_DIR = REPO / "data" / "research" / "xfp_cache"
RH3_PATH = REPO / "data" / "outputs" / "xfp_rh3_projections.csv"

YEARS = list(range(2015, 2027))
XWOBA_WITHIN_PLAYER_SD = 0.39   # population within-PA xwOBA sd
LEAGUE_AVG_XWOBA = 0.320
PA_PER_GAME = 3.8
XWOBA_TO_FP_SLOPE = 4.5         # rough linear: fp_per_pa ≈ xwOBA * 4.5 - 1.2
XWOBA_TO_FP_INTERCEPT = -1.2
TARGET_FP = 200.0
MIN_OBS_FOR_SAMPLE_VAR = 10     # fallback to XWOBA_WITHIN_PLAYER_SD² if fewer obs


def _parquet_glob() -> str:
    """Return a DuckDB-compatible glob string for all statcast parquets."""
    paths = [str(CACHE_DIR / f"statcast_{yr}.parquet") for yr in YEARS]
    existing = [p for p in paths if Path(p).exists()]
    if not existing:
        raise FileNotFoundError(f"No statcast parquets found in {CACHE_DIR}")
    escaped = ", ".join(f"'{p.replace(chr(92), '/')}'" for p in existing)
    return f"[{escaped}]"


def _weighted_variance(values: np.ndarray, weights: np.ndarray, mu: float) -> float:
    """
    Reliability-weighted variance (Bessel-corrected for reliability weights).

    V1 = sum(w), V2 = sum(w^2)
    weighted_var = (V1 / (V1**2 - V2)) * sum(w * (x - mu)**2)
    """
    V1 = float(np.sum(weights))
    V2 = float(np.sum(weights ** 2))
    denom = V1 ** 2 - V2
    if denom <= 0:
        # Only one effective observation — fall back to simple weighted variance
        return float(np.average((values - mu) ** 2, weights=weights))
    return float((V1 / denom) * np.sum(weights * (values - mu) ** 2))


def _years_ago_array(game_dates: pd.Series, today: date) -> np.ndarray:
    """Convert a Series of dates to a float array of years before today."""
    return (today - pd.to_datetime(game_dates).dt.date.apply(
        lambda d: d
    )).apply(lambda td: td.days / 365.25).values


def batch_bayesian_talent(
    batter_ids: list[int],
    decay_lambda: float = 0.20,
) -> dict[int, dict]:
    """Bayesian posterior talent estimation per batter.

    Parameters
    ----------
    batter_ids : list[int]
        MLB batter IDs (Statcast `batter` column).
    decay_lambda : float
        Exponential decay rate for recency weighting of the career prior.
        Default 0.20 (half-life ~3.5 years). Use 0.0 for unweighted.

    Returns
    -------
    dict mapping batter_id -> result dict.
    """
    if not batter_ids:
        return {}

    today = date.today()
    ids_csv = ", ".join(str(b) for b in batter_ids)
    parquet_glob = _parquet_glob()

    sql = f"""
    WITH all_events AS (
        SELECT
            batter,
            CAST(game_date AS DATE) AS game_date,
            estimated_woba_using_speedangle AS xwoba
        FROM read_parquet({parquet_glob})
        WHERE batter IN ({ids_csv})
          AND events IS NOT NULL AND events != ''
          AND estimated_woba_using_speedangle IS NOT NULL
    ),
    ranked AS (
        SELECT
            batter,
            game_date,
            xwoba,
            ROW_NUMBER() OVER (PARTITION BY batter ORDER BY game_date) AS rn,
            COUNT(*) OVER (PARTITION BY batter) AS total_pa
        FROM all_events
    ),
    rolling AS (
        SELECT
            batter,
            rn,
            total_pa,
            xwoba,
            game_date,
            AVG(xwoba) OVER (
                PARTITION BY batter
                ORDER BY rn
                ROWS BETWEEN 149 PRECEDING AND CURRENT ROW
            ) AS roll150
        FROM ranked
    )
    SELECT batter, rn, total_pa, roll150, xwoba, game_date
    FROM rolling
    ORDER BY batter, rn
    """

    db = duckdb.connect()
    df = db.execute(sql).df()
    db.close()

    if df.empty:
        return {}

    # Convert game_date to proper date type
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.date

    # --- Load rh3 for fp_per_pa_career lookup ---
    rh3_lookup: dict[int, float] = {}
    if RH3_PATH.exists():
        rh3 = pd.read_csv(RH3_PATH)
        rh3_lookup = dict(zip(rh3["batter"].astype(int), rh3["prior_fp_per_pa"]))

    results: dict[int, dict] = {}

    for batter_id in batter_ids:
        bdf = df[df["batter"] == batter_id].copy()
        if bdf.empty:
            continue

        # ── Prior: career rolling-150 distribution ──────────────────────────
        roll_rows = bdf[bdf["rn"] >= 150].copy()
        roll150_vals = roll_rows["roll150"].dropna().values
        if len(roll150_vals) < 2:
            continue

        # ── Recency weights for the prior ───────────────────────────────────
        roll_dates = roll_rows["game_date"].dropna().values  # window-end dates
        years_ago = np.array(
            [(today - (d if isinstance(d, date) else pd.Timestamp(d).date())).days / 365.25
             for d in roll_dates],
            dtype=float,
        )

        if decay_lambda == 0.0:
            weights = np.ones(len(roll150_vals), dtype=float)
            weights /= weights.sum()
        else:
            weights = np.exp(-decay_lambda * years_ago)
            weights /= weights.sum()

        # Effective sample size
        effective_n = float(1.0 / np.sum(weights ** 2))

        # Unweighted prior (kept for comparison)
        prior_mu_unweighted = float(np.mean(roll150_vals))
        prior_sigma2_unweighted = float(np.var(roll150_vals, ddof=1))
        prior_sigma_unweighted = math.sqrt(max(prior_sigma2_unweighted, 1e-8))

        # Weighted prior
        prior_mu_weighted = float(np.average(roll150_vals, weights=weights))
        prior_sigma2_weighted = _weighted_variance(roll150_vals, weights, prior_mu_weighted)
        prior_sigma2_weighted = max(prior_sigma2_weighted, 1e-8)
        prior_sigma_weighted = math.sqrt(prior_sigma2_weighted)

        # Use weighted as the primary prior
        prior_mu = prior_mu_weighted
        prior_sigma2 = prior_sigma2_weighted
        prior_sigma = prior_sigma_weighted

        # ── Recent L21d events ───────────────────────────────────────────────
        max_date = bdf["game_date"].max()
        cutoff = pd.Timestamp(max_date) - pd.Timedelta(days=21)
        l21_mask = bdf["game_date"] >= cutoff.date()
        l21df = bdf[l21_mask]

        l21_xwoba = l21df["xwoba"].dropna().values
        obs_n = int(len(l21_xwoba))
        obs_mean = float(np.mean(l21_xwoba)) if obs_n > 0 else prior_mu

        # Within-player xwOBA variance (fallback if too few obs)
        if obs_n >= MIN_OBS_FOR_SAMPLE_VAR:
            obs_variance = float(np.var(l21_xwoba, ddof=1))
            obs_variance = max(obs_variance, 1e-8)
        else:
            obs_variance = XWOBA_WITHIN_PLAYER_SD ** 2

        # ── Conjugate Normal-Normal posterior update ─────────────────────────
        within_var = XWOBA_WITHIN_PLAYER_SD ** 2   # σ_ε² (fixed)
        precision_prior = 1.0 / prior_sigma2
        precision_likelihood = obs_n / within_var if obs_n > 0 else 0.0
        posterior_precision = precision_prior + precision_likelihood

        posterior_mu = (
            precision_prior * prior_mu + precision_likelihood * obs_mean
        ) / posterior_precision
        posterior_sigma2 = 1.0 / posterior_precision
        posterior_sigma = math.sqrt(posterior_sigma2)

        # 95% credible interval
        ci_low = posterior_mu - 1.96 * posterior_sigma
        ci_high = posterior_mu + 1.96 * posterior_sigma

        # P(true talent > career median) — using weighted prior_mu as career median
        p_above_career_median = float(
            1.0 - stats.norm.cdf(prior_mu, loc=posterior_mu, scale=posterior_sigma)
        )

        # P(true talent > league average 0.320)
        p_above_avg = float(
            1.0 - stats.norm.cdf(LEAGUE_AVG_XWOBA, loc=posterior_mu, scale=posterior_sigma)
        )

        # Shrinkage diagnostics
        talent_gap_vs_prior = float(posterior_mu - prior_mu)
        if abs(obs_mean - prior_mu) > 1e-10:
            shrinkage_factor = abs(posterior_mu - prior_mu) / abs(obs_mean - prior_mu)
        else:
            shrinkage_factor = 0.0
        shrinkage_factor = float(np.clip(shrinkage_factor, 0.0, 1.0))

        # Unweighted posterior (for comparison)
        precision_prior_uw = 1.0 / (prior_sigma2_unweighted or 1e-8)
        posterior_precision_uw = precision_prior_uw + precision_likelihood
        posterior_mu_unweighted = (
            precision_prior_uw * prior_mu_unweighted + precision_likelihood * obs_mean
        ) / posterior_precision_uw

        # ── Games to 200 RoS FP ─────────────────────────────────────────────
        if batter_id in rh3_lookup:
            fp_per_pa_career = float(rh3_lookup[batter_id])
        else:
            fp_per_pa_career = float(
                posterior_mu * XWOBA_TO_FP_SLOPE + XWOBA_TO_FP_INTERCEPT
            )

        fp_per_game = fp_per_pa_career * PA_PER_GAME
        games_to_200fp = TARGET_FP / fp_per_game if fp_per_game > 0 else float("inf")

        results[batter_id] = {
            # Primary (recency-weighted) prior
            "prior_mu": round(prior_mu_weighted, 4),
            "prior_sigma": round(prior_sigma_weighted, 4),
            # Unweighted prior (for comparison)
            "prior_mu_unweighted": round(prior_mu_unweighted, 4),
            "prior_sigma_unweighted": round(prior_sigma_unweighted, 4),
            # Recency metadata
            "decay_lambda": decay_lambda,
            "effective_n_windows": round(effective_n, 1),
            # Observations
            "obs_mean_l21d": round(obs_mean, 4),
            "obs_n_l21d": obs_n,
            # Posterior (from weighted prior)
            "posterior_mu": round(posterior_mu, 4),
            "posterior_sigma": round(posterior_sigma, 4),
            "posterior_mu_unweighted": round(posterior_mu_unweighted, 4),
            # Credible interval and probabilities
            "ci_95_low": round(ci_low, 4),
            "ci_95_high": round(ci_high, 4),
            "p_true_talent_above_career_median": round(p_above_career_median, 4),
            "p_true_talent_above_avg": round(p_above_avg, 4),
            # Shrinkage
            "talent_gap_vs_prior": round(talent_gap_vs_prior, 4),
            "shrinkage_factor": round(shrinkage_factor, 4),
            # FP projection
            "fp_per_pa_career": round(fp_per_pa_career, 4),
            "games_to_200fp": round(games_to_200fp, 1),
        }

    return results


if __name__ == "__main__":
    # Test batters: Vlad Guerrero Jr., Manny Machado, Freddie Freeman,
    #               Josh Naylor, Bo Bichette
    TEST_BATTERS = {
        665489: "Vlad Guerrero Jr.",
        592518: "Manny Machado",
        518692: "Freddie Freeman",
        665750: "Josh Naylor",
        666182: "Bo Bichette",
    }

    print("=" * 72)
    print("Bayesian Talent Estimator - Test Run (2026-05-25)")
    print("=" * 72)

    results = batch_bayesian_talent(list(TEST_BATTERS.keys()), decay_lambda=0.20)

    # ── Comparison table ─────────────────────────────────────────────────────
    print("\n" + "=" * 100)
    print("Recency weighting comparison (lambda=0.20 vs unweighted)")
    print("=" * 100)
    hdr = (
        f"{'Player':<25} "
        f"{'prior_mu_uw':>11} {'prior_mu_w':>10} {'d_prior':>7} | "
        f"{'post_mu_uw':>10} {'post_mu_w':>10} {'d_post':>7}"
    )
    print(hdr)
    print("-" * 100)

    for bid, name in TEST_BATTERS.items():
        r = results.get(bid)
        if r is None:
            print(f"  {name:<23} NO DATA")
            continue
        mu_uw = r["prior_mu_unweighted"]
        mu_w = r["prior_mu"]
        d_prior = mu_w - mu_uw
        post_uw = r["posterior_mu_unweighted"]
        post_w = r["posterior_mu"]
        d_post = post_w - post_uw
        print(
            f"  {name:<23} "
            f"{mu_uw:>11.4f} {mu_w:>10.4f} {d_prior:>+7.4f} | "
            f"{post_uw:>10.4f} {post_w:>10.4f} {d_post:>+7.4f}"
        )

    print()

    # ── Per-batter detail ─────────────────────────────────────────────────────
    for bid, name in TEST_BATTERS.items():
        if bid not in results:
            print(f"\n{name} ({bid}): NO DATA\n")
            continue

        r = results[bid]
        print(f"\n{name}  (batter_id={bid})")
        print(f"  Prior (career roll-150, weighted):  mu={r['prior_mu']:.4f}  sd={r['prior_sigma']:.4f}")
        print(f"  Prior (unweighted):                 mu={r['prior_mu_unweighted']:.4f}  "
              f"sd={r['prior_sigma_unweighted']:.4f}  "
              f"d_mu={r['prior_mu']-r['prior_mu_unweighted']:+.4f}")
        print(f"  Effective windows (recency):        {r['effective_n_windows']:.1f}  "
              f"(decay_lambda={r['decay_lambda']})")
        print(f"  Observed L21d:                      xbar={r['obs_mean_l21d']:.4f}  "
              f"n={r['obs_n_l21d']} PA")
        print(f"  Posterior talent (weighted prior):  mu={r['posterior_mu']:.4f}  "
              f"sd={r['posterior_sigma']:.4f}")
        print(f"  Posterior talent (unweighted prior):mu={r['posterior_mu_unweighted']:.4f}")
        print(f"  95% CI:                             [{r['ci_95_low']:.4f}, {r['ci_95_high']:.4f}]")
        print(f"  P(talent > career avg):             {r['p_true_talent_above_career_median']:.1%}")
        print(f"  P(talent > lg avg .320):            {r['p_true_talent_above_avg']:.1%}")
        print(f"  Talent gap vs prior:                {r['talent_gap_vs_prior']:+.4f}  "
              f"(shrinkage factor={r['shrinkage_factor']:.3f})")
        print(f"  FP/PA (career):                     {r['fp_per_pa_career']:.4f}")
        print(f"  Games to 200 RoS FP:                {r['games_to_200fp']:.1f} games")
    print()

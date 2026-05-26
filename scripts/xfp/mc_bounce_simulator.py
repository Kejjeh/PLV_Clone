"""
mc_bounce_simulator.py
----------------------
10,000 bootstrap simulations per slumping hitter, drawn from their own
career rolling-150 xwOBA distribution, to answer:
  "What is the probability this player bounces back over the next 30 PA?"

Recency weighting (v2): each rolling-150 window is weighted by
  w = exp(-decay_lambda * years_ago)
where years_ago = (today - window_end_date) / 365.25.
Default decay_lambda=0.20 gives a half-life of ~3.5 years.
Pass decay_lambda=0.0 to recover uniform (unweighted) sampling.

Usage (module):
    from scripts.xfp.mc_bounce_simulator import batch_mc_bounce
    results = batch_mc_bounce([665742, 592518])
    # with recency weighting:
    results = batch_mc_bounce([665742, 592518], decay_lambda=0.20)

Usage (CLI test — 5 well-known batters):
    python scripts/xfp/mc_bounce_simulator.py
"""

import sys
from pathlib import Path
from datetime import date

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import numpy as np
import pandas as pd
import duckdb

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CACHE_DIR = REPO / "data" / "research" / "xfp_cache"
PARQUET_YEARS = list(range(2015, 2027))  # 2015 through 2026 inclusive

NAME_RESOLUTION_CSV = CACHE_DIR / "name_resolution_2026.csv"


# ---------------------------------------------------------------------------
# DuckDB query builder
# ---------------------------------------------------------------------------

def _build_union_all(ids_csv: str) -> str:
    """Return a UNION ALL block over all year parquets for the given batter IDs."""
    selects = []
    for year in PARQUET_YEARS:
        path = CACHE_DIR / f"statcast_{year}.parquet"
        if not path.exists():
            continue
        selects.append(
            f"  SELECT batter, game_date, estimated_woba_using_speedangle AS xwoba\n"
            f"  FROM read_parquet('{path.as_posix()}')\n"
            f"  WHERE batter IN ({ids_csv})\n"
            f"    AND events IS NOT NULL AND events != ''\n"
            f"    AND estimated_woba_using_speedangle IS NOT NULL"
        )
    return "\nUNION ALL\n".join(selects)


def _fetch_rolling150(batter_ids: list[int]) -> dict[int, dict]:
    """
    Run a single DuckDB query across all year parquets and return, per batter:
      - windows: np.ndarray of rolling-150 xwOBA values (rn >= 150)
      - game_dates: np.ndarray of corresponding window-end dates (as date objects)
      - current_l150: the last rolling-150 value (rn == total_pa)
    """
    if not batter_ids:
        return {}

    ids_csv = ", ".join(str(b) for b in batter_ids)
    union_block = _build_union_all(ids_csv)

    sql = f"""
WITH all_events AS (
{union_block}
),
ranked AS (
  SELECT
    batter,
    CAST(game_date AS DATE) AS game_date,
    xwoba,
    ROW_NUMBER() OVER (PARTITION BY batter ORDER BY game_date) AS rn,
    COUNT(*) OVER (PARTITION BY batter)                         AS total_pa
  FROM all_events
),
rolling AS (
  SELECT
    batter,
    rn,
    total_pa,
    game_date,
    AVG(xwoba) OVER (
      PARTITION BY batter
      ORDER BY rn
      ROWS BETWEEN 149 PRECEDING AND CURRENT ROW
    ) AS roll150
  FROM ranked
)
SELECT batter, rn, total_pa, game_date, roll150
FROM rolling
WHERE rn >= 150
ORDER BY batter, rn
"""

    con = duckdb.connect()
    rows = con.execute(sql).fetchall()  # (batter, rn, total_pa, game_date, roll150)
    con.close()

    # Group by batter
    raw: dict[int, list] = {}
    total_pa_map: dict[int, int] = {}
    for batter, rn, total_pa, game_date, roll150 in rows:
        raw.setdefault(batter, []).append((rn, game_date, roll150))
        total_pa_map[batter] = total_pa

    result = {}
    for batter, window_rows in raw.items():
        total_pa = total_pa_map[batter]
        windows = np.array([r150 for _, _, r150 in window_rows], dtype=float)
        game_dates = [gd for _, gd, _ in window_rows]
        # current form anchor = roll150 where rn == total_pa (last row)
        last_rows = [r150 for rn, _, r150 in window_rows if rn == total_pa]
        current_l150 = last_rows[-1] if last_rows else windows[-1]
        result[batter] = {
            "windows": windows,
            "game_dates": game_dates,
            "current_l150": current_l150,
        }

    return result


# ---------------------------------------------------------------------------
# Recency weight helper
# ---------------------------------------------------------------------------

def _compute_recency_weights(
    game_dates: list,
    decay_lambda: float,
    today: date | None = None,
) -> np.ndarray:
    """
    Compute normalized exponential decay weights for a list of window-end dates.

    Parameters
    ----------
    game_dates : list of date-like
        End date of each rolling-150 window (the current row's game_date).
    decay_lambda : float
        Decay rate. 0.0 → uniform weights. 0.20 → half-life ~3.5 years.
    today : date, optional
        Reference date (defaults to date.today()).

    Returns
    -------
    np.ndarray of shape (n,)
        Normalized weights summing to 1.0.
    """
    if today is None:
        today = date.today()

    if decay_lambda == 0.0:
        n = len(game_dates)
        return np.ones(n, dtype=float) / n

    years_ago = np.array(
        [(today - (gd if isinstance(gd, date) else pd.Timestamp(gd).date())).days / 365.25
         for gd in game_dates],
        dtype=float,
    )
    weights = np.exp(-decay_lambda * years_ago)
    weights /= weights.sum()
    return weights


# ---------------------------------------------------------------------------
# Core simulation
# ---------------------------------------------------------------------------

def _simulate_one(
    career_dist: np.ndarray,
    game_dates: list,
    current_l150: float,
    n_sim: int,
    rng: np.random.Generator,
    decay_lambda: float = 0.20,
    today: date | None = None,
) -> dict:
    """Run MC simulation for a single batter given their career_dist array."""
    if today is None:
        today = date.today()

    # Unweighted stats (for comparison)
    career_mean_unweighted = float(np.mean(career_dist))
    career_median_unweighted = float(np.median(career_dist))
    career_p25 = float(np.percentile(career_dist, 25))
    career_p75 = float(np.percentile(career_dist, 75))

    # Recency weights
    weights = _compute_recency_weights(game_dates, decay_lambda, today)

    # Weighted career mean and median
    career_mean_weighted = float(np.average(career_dist, weights=weights))
    # Weighted median: find value x such that sum(w[i] where dist[i]<=x) >= 0.5
    sort_idx = np.argsort(career_dist)
    cumw = np.cumsum(weights[sort_idx])
    median_idx = np.searchsorted(cumw, 0.5)
    career_median_weighted = float(career_dist[sort_idx[min(median_idx, len(career_dist) - 1)]])

    # Effective sample size after weighting
    effective_n = float(1.0 / np.sum(weights ** 2))

    # Bootstrap: sample with recency weights
    indices = rng.choice(len(career_dist), size=n_sim, replace=True, p=weights)
    samples = career_dist[indices]

    # Shrink toward weighted career mean for 30-PA horizon
    career_mean = career_mean_weighted  # use weighted as the anchor
    sim_30pa = (30.0 * samples + 150.0 * career_mean) / 180.0

    p_bounce_above_median = float(np.mean(sim_30pa > career_median_weighted))
    p_bounce_above_current = float(np.mean(sim_30pa > current_l150))

    # Also compute unweighted bounce probability for comparison
    samples_uw = rng.choice(career_dist, size=n_sim, replace=True)
    sim_30pa_uw = (30.0 * samples_uw + 150.0 * career_mean_unweighted) / 180.0
    p_bounce_above_median_uw = float(np.mean(sim_30pa_uw > career_median_unweighted))

    return {
        "n_career_windows": int(len(career_dist)),
        "career_mean": career_mean_weighted,           # weighted (primary)
        "career_mean_unweighted": career_mean_unweighted,
        "career_median": career_median_weighted,
        "career_p25": career_p25,
        "career_p75": career_p75,
        "current_l150": float(current_l150),
        "p_bounce_above_median": round(p_bounce_above_median, 4),
        "p_bounce_above_median_unweighted": round(p_bounce_above_median_uw, 4),
        "p_bounce_above_current": round(p_bounce_above_current, 4),
        "expected_xwoba_30pa": round(float(np.mean(sim_30pa)), 4),
        "sim_p5": round(float(np.percentile(sim_30pa, 5)), 4),
        "sim_p25": round(float(np.percentile(sim_30pa, 25)), 4),
        "sim_p50": round(float(np.percentile(sim_30pa, 50)), 4),
        "sim_p75": round(float(np.percentile(sim_30pa, 75)), 4),
        "sim_p95": round(float(np.percentile(sim_30pa, 95)), 4),
        "ci_95_low": round(float(np.percentile(sim_30pa, 2.5)), 4),
        "ci_95_high": round(float(np.percentile(sim_30pa, 97.5)), 4),
        "decay_lambda": decay_lambda,
        "effective_n_windows": round(effective_n, 1),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def batch_mc_bounce(
    batter_ids: list[int],
    n_sim: int = 10_000,
    decay_lambda: float = 0.20,
) -> dict[int, dict]:
    """
    For each batter_id, return MC bounce stats keyed by batter_id.

    Parameters
    ----------
    batter_ids : list[int]
        MLBAM batter IDs.
    n_sim : int
        Number of bootstrap simulations (default 10,000).
    decay_lambda : float
        Exponential decay rate for recency weighting (default 0.20).
        Half-life = ln(2) / lambda ≈ 3.5 years at lambda=0.20.
        Use 0.0 for uniform (unweighted) sampling.

    Returns
    -------
    dict[int, dict]
        Per-batter result dict. If a batter has fewer than 150 career PA
        events (< 1 rolling window), returns {"insufficient": True}.
    """
    rng = np.random.default_rng(seed=42)
    today = date.today()

    rolling_data = _fetch_rolling150(batter_ids)

    output: dict[int, dict] = {}
    for batter_id in batter_ids:
        if batter_id not in rolling_data:
            output[batter_id] = {"insufficient": True}
            continue

        career_dist = rolling_data[batter_id]["windows"]
        game_dates = rolling_data[batter_id]["game_dates"]
        current_l150 = rolling_data[batter_id]["current_l150"]

        if len(career_dist) == 0:
            output[batter_id] = {"insufficient": True}
            continue

        output[batter_id] = _simulate_one(
            career_dist, game_dates, current_l150, n_sim, rng,
            decay_lambda=decay_lambda, today=today,
        )

    return output


# ---------------------------------------------------------------------------
# __main__ — test with 5 well-known batters
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Loading name resolution cache: {NAME_RESOLUTION_CSV}")
    name_df = pd.read_csv(NAME_RESOLUTION_CSV)

    TEST_NAMES = [
        "Vladimir Guerrero Jr.",
        "Manny Machado",
        "Freddie Freeman",
        "Josh Naylor",
        "Bo Bichette",
    ]

    # Resolve batter IDs — match on player_name (case-insensitive)
    name_df["_name_lower"] = name_df["player_name"].str.lower()

    test_batters: list[tuple[str, int]] = []
    for name in TEST_NAMES:
        matches = name_df[name_df["_name_lower"] == name.lower()]
        if matches.empty:
            # Try partial match
            matches = name_df[name_df["player_name"].str.contains(
                name.split()[-1], case=False, na=False
            )]
        if matches.empty:
            print(f"  WARNING: could not resolve '{name}' — skipping")
            continue
        row = matches.iloc[0]
        bid = int(row["batter_mlbam"])
        test_batters.append((row["player_name"], bid))
        print(f"  Resolved: {row['player_name']} -> {bid}")

    if not test_batters:
        print("No batters resolved. Check name_resolution_2026.csv.")
        sys.exit(1)

    batter_ids = [bid for _, bid in test_batters]
    id_to_name = {bid: name for name, bid in test_batters}

    print(f"\nRunning batch_mc_bounce for {len(batter_ids)} batters "
          f"(n_sim=10,000, decay_lambda=0.20)...\n")

    results_weighted = batch_mc_bounce(batter_ids, n_sim=10_000, decay_lambda=0.20)
    results_uniform = batch_mc_bounce(batter_ids, n_sim=10_000, decay_lambda=0.0)

    # ── Comparison table ─────────────────────────────────────────────────────
    print("\n" + "=" * 90)
    print("MC BOUNCE SIMULATOR - Recency weighting comparison (lambda=0.20 vs uniform)")
    print("=" * 90)
    hdr = f"{'Player':<25} {'prior_mu_uw':>11} {'prior_mu_w':>10} {'d_mu':>7} | {'P(bounce)_uw':>12} {'P(bounce)_w':>11} {'d_p':>7} | {'eff_n':>6}"
    print(hdr)
    print("-" * 90)

    for bid, name in zip(batter_ids, [n for n, _ in test_batters]):
        rw = results_weighted.get(bid, {})
        ru = results_uniform.get(bid, {})
        if rw.get("insufficient") or ru.get("insufficient"):
            print(f"  {name:<23} INSUFFICIENT DATA")
            continue
        mu_uw = ru["career_mean"]
        mu_w = rw["career_mean"]
        d_mu = mu_w - mu_uw
        p_uw = ru["p_bounce_above_median"]
        p_w = rw["p_bounce_above_median"]
        d_p = p_w - p_uw
        eff_n = rw["effective_n_windows"]
        print(f"  {name:<23} {mu_uw:>11.4f} {mu_w:>10.4f} {d_mu:>+7.4f} | "
              f"{p_uw:>12.1%} {p_w:>11.1%} {d_p:>+7.1%} | {eff_n:>6.1f}")

    print()

    # ── Per-batter detail ─────────────────────────────────────────────────────
    sep = "-" * 64
    for bid, (name, _) in zip(batter_ids, test_batters):
        res = results_weighted.get(bid, {})
        print(sep)
        print(f"  {name}  (MLBAM {bid})")
        print(sep)
        if res.get("insufficient"):
            print("  INSUFFICIENT DATA (< 150 career PA events)")
            continue
        print(f"  Career windows (n)           : {res['n_career_windows']}")
        print(f"  Effective windows (recency)  : {res['effective_n_windows']:.1f}")
        print(f"  Decay lambda                 : {res['decay_lambda']}")
        print(f"  Career mean xwOBA (weighted) : {res['career_mean']:.4f}  "
              f"(unweighted: {res['career_mean_unweighted']:.4f}  "
              f"d={res['career_mean']-res['career_mean_unweighted']:+.4f})")
        print(f"  Career median xwOBA          : {res['career_median']:.4f}")
        print(f"  Career p25 / p75             : {res['career_p25']:.4f} / {res['career_p75']:.4f}")
        print(f"  Current L150 xwOBA           : {res['current_l150']:.4f}")
        print()
        print(f"  --- 30-PA bounce simulation (n=10,000, lambda=0.20) ---")
        print(f"  Expected xwOBA (30 PA)       : {res['expected_xwoba_30pa']:.4f}")
        print(f"  P(bounce > career median, w) : {res['p_bounce_above_median']:.1%}  "
              f"(unweighted: {res['p_bounce_above_median_unweighted']:.1%})")
        print(f"  P(bounce > current L150)     : {res['p_bounce_above_current']:.1%}")
        print(f"  Sim p5  / p95                : {res['sim_p5']:.4f} / {res['sim_p95']:.4f}")
        print(f"  Sim p25 / p75                : {res['sim_p25']:.4f} / {res['sim_p75']:.4f}")
        print(f"  Sim median                   : {res['sim_p50']:.4f}")
        print(f"  95% CI                       : [{res['ci_95_low']:.4f}, {res['ci_95_high']:.4f}]")
        print()

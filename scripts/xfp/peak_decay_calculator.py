"""
peak_decay_calculator.py
========================
Compute peak-form survival curves from 2015-2025 Statcast data.

For all career PEAK windows (career percentile >= 90th), build:
  - League-wide P(still performing >= 80th pct after N PA) curves
  - Split by PROCESS_DRIVEN / PROCESS_DRIVEN_STRONG / OUTCOME_DRIVEN / UNCLASSIFIED
  - Per-target-batter decay stats for currently-PEAK 2026 players
  - Wilson score 95% confidence intervals on every survival curve checkpoint

Public API
----------
get_league_peak_survival_curves() -> dict
    Pre-compute (and cache to JSON) league-wide survival curves.

batch_peak_decay(batter_ids: list[int]) -> dict[int, dict]
    For each batter currently in PEAK form, compute peak decay stats.
    Backward compatible: return dict now includes CI keys per checkpoint.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

# ---------------------------------------------------------------------------
# Repo paths
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

CACHE_DIR = REPO / "data" / "research" / "xfp_cache"
RESEARCH_DIR = REPO / "data" / "research"

SURVIVAL_JSON = RESEARCH_DIR / "peak_survival_curves.json"
SURVIVAL_CACHE_PARQUET = CACHE_DIR / "peak_survival_cache.parquet"
SUST_CSV = RESEARCH_DIR / "league_sust_full_2026-05-25.csv"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PEAK_PERCENTILE = 0.90       # threshold to be "in PEAK form"
SURVIVAL_PERCENTILE = 0.80   # threshold to be "still performing well"
MIN_CAREER_PA = 150          # minimum career PA to enter analysis
# Process classifier thresholds (Option B: OR logic, lower bar)
HARD_HIT_EV_THRESHOLD = 92.0  # avg EV threshold for STRONG power signal
K_RATE_THRESHOLD = 0.22       # K% threshold (below = disciplined)
MIN_BF_FOR_EV = 10            # min batted balls to trust EV measurement
LOOKBACK_PA = 30              # PA window for process classification pre-peak
CHECKPOINTS = [30, 60, 90, 120, 150, 180]  # PA checkpoints for survival

HIST_YEARS = list(range(2015, 2026))  # 2015-2025 (not 2026)

# ---------------------------------------------------------------------------
# Wilson score CI helper
# ---------------------------------------------------------------------------

def wilson_ci(n_survived: int, n_total: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a proportion.

    Parameters
    ----------
    n_survived : int
        Number of "successes" (peaks that survived to checkpoint).
    n_total : int
        Total observations (peaks with enough future data at checkpoint).
    confidence : float
        Confidence level, default 0.95 for 95% CI.

    Returns
    -------
    (ci_low, ci_high) : tuple of floats, clamped to [0, 1].
    """
    if n_total == 0:
        return (0.0, 1.0)
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    p_hat = n_survived / n_total
    denom = 1 + z ** 2 / n_total
    center = (p_hat + z ** 2 / (2 * n_total)) / denom
    margin = (
        z * np.sqrt(p_hat * (1 - p_hat) / n_total + z ** 2 / (4 * n_total ** 2)) / denom
    )
    return (max(0.0, center - margin), min(1.0, center + margin))


# ---------------------------------------------------------------------------
# DuckDB helpers
# ---------------------------------------------------------------------------

def _get_con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect()


def _parquet_glob(years: list[int]) -> str:
    """Return a DuckDB-compatible glob string for the given years."""
    paths = [str(CACHE_DIR / f"statcast_{y}.parquet").replace("\\", "/") for y in years]
    return paths


def _load_statcast_pa_level(years: list[int]) -> pd.DataFrame:
    """
    Load pitch-level data for the given years and aggregate to PA level.
    Returns one row per (batter, pa_idx) with:
      - xwoba: estimated_woba_using_speedangle (mean over PA, NaN if no batted ball)
      - avg_ev: mean launch speed on batted ball events
      - strikeout: 1 if PA ended in strikeout
      - woba_denom: 1 if PA counts (woba_denom=1)
      - game_date: date of last pitch in PA
    """
    con = _get_con()
    parquet_list = _parquet_glob(years)
    pl_str = "[" + ", ".join(f"'{p}'" for p in parquet_list) + "]"

    query = f"""
    WITH raw AS (
        SELECT
            batter,
            game_year,
            game_date,
            at_bat_number,
            game_pk,
            estimated_woba_using_speedangle AS xwoba_pitch,
            launch_speed,
            woba_denom,
            events,
            description
        FROM read_parquet({pl_str})
        WHERE game_type = 'R'
    ),
    pa_agg AS (
        SELECT
            batter,
            game_year,
            game_pk,
            at_bat_number,
            MAX(game_date)                                  AS game_date,
            -- woba_denom=1 means this PA counts toward official stats
            MAX(CASE WHEN woba_denom = 1 THEN 1 ELSE 0 END) AS is_pa,
            -- xwOBA: use estimated_woba for any plate appearance with a value
            AVG(CASE WHEN xwoba_pitch IS NOT NULL THEN xwoba_pitch END) AS xwoba,
            -- EV: avg launch speed on batted ball events
            AVG(CASE WHEN launch_speed IS NOT NULL AND launch_speed > 0
                        THEN launch_speed END)              AS avg_ev,
            -- count of batted balls in this PA (for min-sample check)
            SUM(CASE WHEN launch_speed IS NOT NULL AND launch_speed > 0
                        THEN 1 ELSE 0 END)                  AS n_batted_balls,
            -- Strikeout flag: any events = strikeout*
            MAX(CASE WHEN events LIKE 'strikeout%' THEN 1 ELSE 0 END) AS is_k
        FROM raw
        GROUP BY batter, game_year, game_pk, at_bat_number
    )
    SELECT *
    FROM pa_agg
    WHERE is_pa = 1
    ORDER BY batter, game_date, game_pk, at_bat_number
    """
    print("  Loading PA-level data from Statcast parquets (this may take 30-120s)...")
    t0 = time.time()
    df = con.execute(query).fetchdf()
    print(f"  Loaded {len(df):,} PAs in {time.time()-t0:.1f}s")
    return df


def _build_rolling_windows(df: pd.DataFrame, window: int = 150) -> pd.DataFrame:
    """
    For each batter, compute rolling-N xwOBA using a sliding window of `window` PAs.
    Returns df with columns: batter, rn (sequential PA row number per batter),
    rolling_xwoba (mean xwOBA over last `window` PAs).
    """
    df = df.sort_values(["batter", "game_date", "game_pk", "at_bat_number"]).reset_index(drop=True)
    df["rn"] = df.groupby("batter").cumcount() + 1

    def rolling_xwoba(sub: pd.DataFrame) -> pd.Series:
        return sub["xwoba"].rolling(window, min_periods=window // 2).mean()

    df["rolling_xwoba"] = df.groupby("batter", group_keys=False).apply(rolling_xwoba)
    return df


# ---------------------------------------------------------------------------
# Core: compute peak windows
# ---------------------------------------------------------------------------

def _find_peak_windows(df_rolling: pd.DataFrame) -> pd.DataFrame:
    """
    Find all (batter, rn) points where:
      - total career PA at that point >= MIN_CAREER_PA
      - rolling_xwoba is at >= 90th career percentile for that batter
      - year is <= 2025 (historical)
    Returns df with [batter, rn, rolling_xwoba, career_p90, career_p80, game_year].
    """
    print("  Computing per-batter career percentiles...")

    pctls = (
        df_rolling.dropna(subset=["rolling_xwoba"])
        .groupby("batter")["rolling_xwoba"]
        .quantile([0.80, 0.90])
        .unstack()
        .rename(columns={0.80: "career_p80", 0.90: "career_p90"})
        .reset_index()
    )

    df = df_rolling.merge(pctls, on="batter", how="left")

    df["is_peak"] = (
        (df["rolling_xwoba"] >= df["career_p90"])
        & (df["rn"] >= MIN_CAREER_PA)
        & (df["game_year"] <= 2025)
    )

    peak_windows = df[df["is_peak"]].copy()
    print(f"  Found {len(peak_windows):,} PEAK snapshots across {peak_windows['batter'].nunique():,} batters")
    return peak_windows, df


# ---------------------------------------------------------------------------
# Process classification (Option B: OR logic + PROCESS_DRIVEN_STRONG)
# ---------------------------------------------------------------------------

def _classify_peak_windows(peak_windows: pd.DataFrame, df_full: pd.DataFrame) -> pd.DataFrame:
    """
    For each PEAK window, look at the 30 PA *before* the peak snapshot
    and classify as:
      - PROCESS_DRIVEN_STRONG : avg_ev > 92 AND k_pct < 0.22 (both signals)
      - PROCESS_DRIVEN        : avg_ev > 92 OR k_pct < 0.22 (at least one signal)
      - OUTCOME_DRIVEN        : neither signal
      - UNCLASSIFIED          : < 10 total PA in window, or < MIN_BF_FOR_EV batted balls
                                (previously these fell silently into OUTCOME_DRIVEN)

    NOTE: EV signal requires >= MIN_BF_FOR_EV batted balls in window.
          If fewer, EV signal is treated as absent (not False) for classification.
    """
    print("  Classifying PEAK windows by process proxy (Option B: OR logic)...")

    pa_data = df_full[["batter", "rn", "avg_ev", "is_k", "n_batted_balls"]].copy()

    results = []
    peak_by_batter = peak_windows.groupby("batter")
    pa_by_batter = {b: g for b, g in pa_data.groupby("batter")}

    for batter, peak_grp in peak_by_batter:
        if batter not in pa_by_batter:
            continue
        pa_grp = pa_by_batter[batter].set_index("rn")

        for _, row in peak_grp.iterrows():
            R = int(row["rn"])
            window_slice = pa_grp.loc[
                pa_grp.index.isin(range(max(1, R - LOOKBACK_PA), R))
            ]

            if len(window_slice) < 10:
                peak_type = "UNCLASSIFIED"
            else:
                ev_vals = window_slice["avg_ev"].dropna()
                n_bf = int(window_slice["n_batted_balls"].sum()) if "n_batted_balls" in window_slice.columns else len(ev_vals)
                k_vals = window_slice["is_k"]
                k_rate = k_vals.mean()

                # Power signal: require min batted balls for EV to be meaningful
                if n_bf >= MIN_BF_FOR_EV and len(ev_vals) > 0:
                    hard_hit = ev_vals.mean() > HARD_HIT_EV_THRESHOLD
                else:
                    hard_hit = None  # insufficient sample — treat as "absent"

                low_k = k_rate < K_RATE_THRESHOLD

                # Option B classifier
                if hard_hit is True and low_k:
                    peak_type = "PROCESS_DRIVEN_STRONG"
                elif hard_hit is True or low_k:
                    peak_type = "PROCESS_DRIVEN"
                elif hard_hit is None:
                    # Can't measure EV, but can measure K — if low_k it would have hit above
                    # So: hard_hit=None AND low_k=False → UNCLASSIFIED (can't confirm either)
                    peak_type = "UNCLASSIFIED"
                else:
                    # hard_hit=False AND low_k=False → OUTCOME_DRIVEN
                    peak_type = "OUTCOME_DRIVEN"

            results.append({
                "batter": batter,
                "rn": R,
                "peak_type": peak_type,
                "career_p80": row["career_p80"],
                "career_p90": row["career_p90"],
                "rolling_xwoba": row["rolling_xwoba"],
                "game_year": row.get("game_year", np.nan),
            })

    classified = pd.DataFrame(results)
    counts = classified["peak_type"].value_counts()
    total = len(classified)
    print(f"  Classification breakdown (n={total:,}):")
    for k, v in counts.items():
        print(f"    {k:30s}: {v:>8,}  ({v/total:.1%})")
    return classified


# ---------------------------------------------------------------------------
# Survival curve computation (with Wilson CIs)
# ---------------------------------------------------------------------------

def _build_ci_curve(sub: pd.DataFrame) -> dict:
    """
    For a sub-DataFrame of survival rows, build a checkpoint dict with:
      survival, ci_low, ci_high, n_total, n_survived
    Uses Wilson score interval.
    """
    curve = {}
    for cp in CHECKPOINTS:
        col = f"surv_{cp}"
        valid = sub[col].dropna()
        n_total = len(valid)
        if n_total < 5:
            curve[str(cp)] = {
                "survival": None,
                "ci_low": None,
                "ci_high": None,
                "n_total": n_total,
                "n_survived": int(valid.sum()) if n_total > 0 else 0,
            }
        else:
            n_survived = int(valid.sum())
            survival = float(valid.mean())
            ci_low, ci_high = wilson_ci(n_survived, n_total)
            curve[str(cp)] = {
                "survival": round(survival, 4),
                "ci_low": round(ci_low, 4),
                "ci_high": round(ci_high, 4),
                "n_total": n_total,
                "n_survived": n_survived,
            }
    return curve


def _compute_survival_curves(
    classified_peaks: pd.DataFrame,
    df_full: pd.DataFrame,
) -> dict:
    """
    For each PEAK window, check survival at each checkpoint PA.
    Survival = rolling_xwoba in [R+1 .. R+checkpoint] >= career_p80.
    Returns enriched curves dict with Wilson CIs per checkpoint and group.
    """
    print("  Computing survival curves at checkpoints:", CHECKPOINTS)

    rolling_by_batter = {
        b: g.set_index("rn")["rolling_xwoba"]
        for b, g in df_full.groupby("batter")
    }

    survival_rows = []
    for _, row in classified_peaks.iterrows():
        batter = row["batter"]
        R = int(row["rn"])
        p80 = row["career_p80"]
        peak_type = row["peak_type"]

        if batter not in rolling_by_batter:
            continue

        roll = rolling_by_batter[batter]
        rec = {"batter": batter, "rn": R, "peak_type": peak_type, "career_p80": p80}

        for cp in CHECKPOINTS:
            future_rns = range(R + 1, R + cp + 1)
            future_vals = roll.reindex(future_rns).dropna()
            if len(future_vals) < cp // 3:
                rec[f"surv_{cp}"] = np.nan
            else:
                rec[f"surv_{cp}"] = 1 if future_vals.mean() >= p80 else 0

        survival_rows.append(rec)

    surv_df = pd.DataFrame(survival_rows)

    # ---- Build curves for each group ----
    all_curve = _build_ci_curve(surv_df)

    proc_strong_sub = surv_df[surv_df["peak_type"] == "PROCESS_DRIVEN_STRONG"]
    proc_broad_sub = surv_df[surv_df["peak_type"].isin(["PROCESS_DRIVEN", "PROCESS_DRIVEN_STRONG"])]
    proc_narrow_sub = surv_df[surv_df["peak_type"] == "PROCESS_DRIVEN"]
    outc_sub = surv_df[surv_df["peak_type"] == "OUTCOME_DRIVEN"]
    uncl_sub = surv_df[surv_df["peak_type"] == "UNCLASSIFIED"]

    proc_broad_curve = _build_ci_curve(proc_broad_sub)
    proc_strong_curve = _build_ci_curve(proc_strong_sub)
    proc_narrow_curve = _build_ci_curve(proc_narrow_sub)
    outc_curve = _build_ci_curve(outc_sub)

    def median_survival_from_ci_curve(ci_curve: dict) -> int:
        """PA at which survival drops below 50%."""
        for cp in CHECKPOINTS:
            entry = ci_curve.get(str(cp), {})
            surv = entry.get("survival")
            if surv is not None and surv < 0.50:
                return cp
        return CHECKPOINTS[-1] + 30

    n_by_type = surv_df["peak_type"].value_counts().to_dict()

    result = {
        # Survival curves — new structured format with CI
        "all": all_curve,
        "PROCESS_DRIVEN": proc_broad_curve,          # OR logic (broad)
        "PROCESS_DRIVEN_STRONG": proc_strong_curve,  # AND logic (both signals)
        "PROCESS_DRIVEN_NARROW": proc_narrow_curve,  # exactly one signal
        "OUTCOME_DRIVEN": outc_curve,
        # Classification counts
        "n_peaks_total": len(surv_df),
        "n_process_driven_broad": len(proc_broad_sub),
        "n_process_driven_strong": len(proc_strong_sub),
        "n_process_driven_narrow": len(proc_narrow_sub),
        "n_outcome_driven": len(outc_sub),
        "n_unclassified": len(uncl_sub),
        "classification_pct": {
            k: round(v / len(surv_df), 4) for k, v in n_by_type.items()
        },
        # Median survival (legacy summary)
        "median_survival_pa_all": median_survival_from_ci_curve(all_curve),
        "median_survival_pa_process": median_survival_from_ci_curve(proc_broad_curve),
        "median_survival_pa_process_strong": median_survival_from_ci_curve(proc_strong_curve),
        "median_survival_pa_outcome": median_survival_from_ci_curve(outc_curve),
    }
    return result, surv_df


# ---------------------------------------------------------------------------
# Main public API: league-wide survival curves
# ---------------------------------------------------------------------------

def get_league_peak_survival_curves(force_recompute: bool = False) -> dict:
    """
    Pre-compute the league-wide survival curves once (cached to JSON).

    If the cache exists and force_recompute is False, load from JSON.
    Otherwise, run the full DuckDB pipeline over 2015-2025 parquets.
    """
    if SURVIVAL_JSON.exists() and not force_recompute:
        print(f"Loading cached survival curves from {SURVIVAL_JSON}")
        with open(SURVIVAL_JSON) as f:
            return json.load(f)

    print("=" * 60)
    print("Computing league-wide peak survival curves (2015-2025)")
    print("=" * 60)

    if SURVIVAL_CACHE_PARQUET.exists() and not force_recompute:
        print(f"Loading PA cache from {SURVIVAL_CACHE_PARQUET}")
        df_pa = pd.read_parquet(SURVIVAL_CACHE_PARQUET)
        # Ensure n_batted_balls column exists (cache may predate this column)
        if "n_batted_balls" not in df_pa.columns:
            print("  Cache missing n_batted_balls — forcing fresh load...")
            df_pa = _load_statcast_pa_level(HIST_YEARS)
            df_pa.to_parquet(SURVIVAL_CACHE_PARQUET, index=False)
    else:
        t0 = time.time()
        df_pa = _load_statcast_pa_level(HIST_YEARS)
        elapsed = time.time() - t0
        if elapsed > 20:
            print(f"  Caching PA data to {SURVIVAL_CACHE_PARQUET} ...")
            df_pa.to_parquet(SURVIVAL_CACHE_PARQUET, index=False)

    print("  Building 150-PA rolling xwOBA windows...")
    df_rolling = _build_rolling_windows(df_pa, window=150)

    peak_windows, df_full = _find_peak_windows(df_rolling)

    classified = _classify_peak_windows(peak_windows, df_full)

    curves, surv_df = _compute_survival_curves(classified, df_full)

    print(f"\nWriting survival curves to {SURVIVAL_JSON}")
    with open(SURVIVAL_JSON, "w") as f:
        json.dump(curves, f, indent=2)

    return curves


# ---------------------------------------------------------------------------
# Part 2: Per-batter decay stats
# ---------------------------------------------------------------------------

def _load_sust_csv() -> Optional[pd.DataFrame]:
    """Load today's sustainability CSV if it exists."""
    for candidate in [
        SUST_CSV,
        RESEARCH_DIR / "league_sust_full_2026-05-24.csv",
    ]:
        if candidate.exists():
            return pd.read_csv(candidate)
    return None


def _classify_batter_peak_type(batter_id: int, sust_df: Optional[pd.DataFrame]) -> tuple[str, float]:
    """
    Return (peak_type, current_percentile) for a batter.
    Recognizes PROCESS_DRIVEN_STRONG, PROCESS_DRIVEN, OUTCOME_DRIVEN, UNCLASSIFIED.
    """
    if sust_df is not None:
        row = sust_df[sust_df["batter"] == batter_id]
        if not row.empty:
            peak_type = str(row["peak_type"].iloc[0])
            pct = float(row["career_%ile"].iloc[0]) if "career_%ile" in row.columns else 0.0
            upper = peak_type.upper()
            if "STRONG" in upper:
                peak_type = "PROCESS_DRIVEN_STRONG"
            elif "PROCESS" in upper:
                peak_type = "PROCESS_DRIVEN"
            elif "OUTCOME" in upper:
                peak_type = "OUTCOME_DRIVEN"
            else:
                peak_type = "UNCLASSIFIED"
            return peak_type, pct
    return "UNCLASSIFIED", 0.0


def _get_survival_for_type(curves: dict, peak_type: str) -> dict:
    """Return the survival CI curve dict for a given peak type."""
    if peak_type in curves:
        return curves[peak_type]
    # PROCESS_DRIVEN_STRONG falls through to PROCESS_DRIVEN (broad)
    if peak_type == "PROCESS_DRIVEN_STRONG" and "PROCESS_DRIVEN" in curves:
        return curves["PROCESS_DRIVEN_STRONG"]
    return curves.get("all", {})


def _survival_at(ci_curve: dict, cp: int) -> tuple[Optional[float], Optional[float], Optional[float], int]:
    """Extract (survival, ci_low, ci_high, n_total) from a CI curve at checkpoint cp."""
    entry = ci_curve.get(str(cp)) or ci_curve.get(cp) or {}
    return (
        entry.get("survival"),
        entry.get("ci_low"),
        entry.get("ci_high"),
        entry.get("n_total", 0),
    )


def _weeks_to_reversion(ci_curve: dict) -> float:
    """
    Estimate weeks until 50% probability of reversion.
    Assumes ~4.5 PA/game, ~6 games/week → ~27 PA/week.
    """
    PA_PER_WEEK = 27.0
    for cp in CHECKPOINTS:
        surv, _, _, _ = _survival_at(ci_curve, cp)
        if surv is not None and surv < 0.50:
            return round(cp / PA_PER_WEEK, 1)
    return round(CHECKPOINTS[-1] / PA_PER_WEEK + 1.0, 1)


def batch_peak_decay(batter_ids: list[int]) -> dict[int, dict]:
    """
    For each batter currently in PEAK form, compute peak decay stats.

    Parameters
    ----------
    batter_ids : list[int]
        MLBAM batter IDs (should be players currently in PEAK form).

    Returns
    -------
    dict mapping batter_id -> decay stats dict.

    Backward compatible: adds CI keys alongside existing keys.
    New keys per checkpoint (example for 30PA):
      p_still_peak_30pa, p_still_peak_30pa_ci_low, p_still_peak_30pa_ci_high
    Plus: ci_n_sample (n_total at 30PA checkpoint, smallest reliable sample).
    """
    curves = get_league_peak_survival_curves()
    sust_df = _load_sust_csv()

    results = {}
    for batter_id in batter_ids:
        peak_type, current_pct = _classify_batter_peak_type(batter_id, sust_df)
        ci_curve = _get_survival_for_type(curves, peak_type)

        # Extract per-checkpoint values
        p30, p30_lo, p30_hi, n30 = _survival_at(ci_curve, 30)
        p60, p60_lo, p60_hi, n60 = _survival_at(ci_curve, 60)
        p90, p90_lo, p90_hi, n90 = _survival_at(ci_curve, 90)
        p120, p120_lo, p120_hi, n120 = _survival_at(ci_curve, 120)

        # Trade window heuristic
        if p30 is not None and p30 > 0.70:
            trade_window = "HOLD_SHORT"
        elif p30 is not None and p30 > 0.50:
            trade_window = "HOLD_SHORT"
        else:
            trade_window = "SELL_NOW"

        weeks_rev = _weeks_to_reversion(ci_curve)

        # n historical comps
        if peak_type == "PROCESS_DRIVEN_STRONG":
            n_comps = curves.get("n_process_driven_strong", 0)
        elif peak_type == "PROCESS_DRIVEN":
            n_comps = curves.get("n_process_driven_broad", 0)
        elif peak_type == "OUTCOME_DRIVEN":
            n_comps = curves.get("n_outcome_driven", 0)
        else:
            n_comps = curves.get("n_peaks_total", 0)

        def _r(v):
            return round(v, 3) if v is not None else None

        results[batter_id] = {
            "peak_type": peak_type,
            "current_percentile": round(current_pct, 3),
            # Point estimates (backward compat)
            "p_still_peak_30pa": _r(p30),
            "p_still_peak_30pa_ci_low": _r(p30_lo),
            "p_still_peak_30pa_ci_high": _r(p30_hi),
            "p_still_peak_60pa": _r(p60),
            "p_still_peak_60pa_ci_low": _r(p60_lo),
            "p_still_peak_60pa_ci_high": _r(p60_hi),
            "p_still_peak_90pa": _r(p90),
            "p_still_peak_90pa_ci_low": _r(p90_lo),
            "p_still_peak_90pa_ci_high": _r(p90_hi),
            "p_still_peak_120pa": _r(p120),
            "p_still_peak_120pa_ci_low": _r(p120_lo),
            "p_still_peak_120pa_ci_high": _r(p120_hi),
            "ci_n_sample": n30,  # n at 30PA checkpoint (widest CI = smallest sample)
            "expected_weeks_to_reversion": weeks_rev,
            "historical_peak_comps": n_comps,
            "trade_window": trade_window,
            "survival_curve": {
                str(cp): _survival_at(ci_curve, cp)[0]
                for cp in CHECKPOINTS
            },
            "survival_curve_ci": {
                str(cp): {
                    "survival": _r(_survival_at(ci_curve, cp)[0]),
                    "ci_low": _r(_survival_at(ci_curve, cp)[1]),
                    "ci_high": _r(_survival_at(ci_curve, cp)[2]),
                    "n_total": _survival_at(ci_curve, cp)[3],
                }
                for cp in CHECKPOINTS
            },
        }

    return results


# ---------------------------------------------------------------------------
# __main__: compute curves and test on target batters
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Peak decay survival curves")
    parser.add_argument("--recompute", action="store_true",
                        help="Force recompute even if cache exists")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("PART 1: League-wide peak survival curves (2015-2025)")
    print("=" * 60)
    curves = get_league_peak_survival_curves(force_recompute=args.recompute)

    print("\n--- CLASSIFICATION DISTRIBUTION ---")
    print(f"Total PEAK windows analyzed   : {curves['n_peaks_total']:,}")
    print(f"  PROCESS_DRIVEN (broad)      : {curves['n_process_driven_broad']:,}  ({curves['n_process_driven_broad']/curves['n_peaks_total']:.1%})")
    print(f"  PROCESS_DRIVEN_STRONG       : {curves['n_process_driven_strong']:,}  ({curves['n_process_driven_strong']/curves['n_peaks_total']:.1%})")
    print(f"  PROCESS_DRIVEN_NARROW       : {curves['n_process_driven_narrow']:,}  ({curves['n_process_driven_narrow']/curves['n_peaks_total']:.1%})")
    print(f"  OUTCOME_DRIVEN              : {curves['n_outcome_driven']:,}  ({curves['n_outcome_driven']/curves['n_peaks_total']:.1%})")
    print(f"  UNCLASSIFIED                : {curves['n_unclassified']:,}  ({curves['n_unclassified']/curves['n_peaks_total']:.1%})")

    print("\n--- SURVIVAL CURVES WITH WILSON 95% CIs ---")

    def fmt_ci_curve(label: str, ci_curve: dict):
        parts = []
        for cp in CHECKPOINTS:
            entry = ci_curve.get(str(cp)) or {}
            s = entry.get("survival")
            lo = entry.get("ci_low")
            hi = entry.get("ci_high")
            n = entry.get("n_total", 0)
            if s is None:
                parts.append(f"{cp}PA: N/A")
            else:
                parts.append(f"{cp}PA: {s:.3f} [{lo:.3f},{hi:.3f}] n={n:,}")
        print(f"\n  {label}:")
        for p in parts:
            print(f"    {p}")

    fmt_ci_curve("ALL", curves["all"])
    fmt_ci_curve("PROCESS_DRIVEN (broad OR)", curves.get("PROCESS_DRIVEN", {}))
    fmt_ci_curve("PROCESS_DRIVEN_STRONG (AND)", curves.get("PROCESS_DRIVEN_STRONG", {}))
    fmt_ci_curve("OUTCOME_DRIVEN", curves.get("OUTCOME_DRIVEN", {}))

    print("\n--- MEDIAN SURVIVAL (PA at which 50% have decayed below 80th pct) ---")
    print(f"  ALL                         : {curves['median_survival_pa_all']} PA")
    print(f"  PROCESS_DRIVEN (broad)      : {curves['median_survival_pa_process']} PA")
    print(f"  PROCESS_DRIVEN_STRONG       : {curves['median_survival_pa_process_strong']} PA")
    print(f"  OUTCOME_DRIVEN              : {curves['median_survival_pa_outcome']} PA")

    print("\n--- CI WIDTH DIAGNOSTIC ---")
    for group_key, label in [
        ("PROCESS_DRIVEN", "PROCESS_DRIVEN (broad)"),
        ("PROCESS_DRIVEN_STRONG", "PROCESS_DRIVEN_STRONG"),
        ("OUTCOME_DRIVEN", "OUTCOME_DRIVEN"),
    ]:
        ci_curve = curves.get(group_key, {})
        for cp in [30, 90]:
            entry = ci_curve.get(str(cp)) or {}
            s = entry.get("survival")
            lo = entry.get("ci_low")
            hi = entry.get("ci_high")
            n = entry.get("n_total", 0)
            if s is not None:
                width = round(hi - lo, 4) if hi and lo else "N/A"
                print(f"  {label:35s} @ {cp}PA: width={width}  n={n:,}")

    print("\n" + "=" * 60)
    print("PART 2: Per-batter decay stats for target batters")
    print("=" * 60)

    test_batters = {
        647304: "Josh Naylor (OUTCOME_DRIVEN)",
        680777: "Ryan Jeffers (PROCESS_DRIVEN)",
        695506: "Jac Caglianone (PROCESS_DRIVEN)",
    }

    decay = batch_peak_decay(list(test_batters.keys()))

    for batter_id, label in test_batters.items():
        d = decay.get(batter_id, {})
        print(f"\n{label} (mlbam={batter_id})")
        print(f"  Peak type              : {d.get('peak_type')}")
        pct = d.get('current_percentile')
        print(f"  Current percentile     : {pct:.1%}" if pct else "  Current percentile     : N/A")
        print(f"  Trade window           : {d.get('trade_window')}")
        print(f"  Exp weeks to reversion : {d.get('expected_weeks_to_reversion', 'N/A')}")
        print(f"  Historical comps (n)   : {d.get('historical_peak_comps', 0):,}")
        print(f"  CI sample n (30PA)     : {d.get('ci_n_sample', 'N/A'):,}" if isinstance(d.get('ci_n_sample'), int) else f"  CI sample n (30PA)     : {d.get('ci_n_sample', 'N/A')}")
        print(f"  Survival + CI:")
        sci = d.get("survival_curve_ci", {})
        for cp in [30, 60, 90, 120, 150, 180]:
            entry = sci.get(str(cp)) or {}
            s = entry.get("survival")
            lo = entry.get("ci_low")
            hi = entry.get("ci_high")
            n = entry.get("n_total", 0)
            if s is None:
                print(f"    +{cp:3d}PA : N/A")
            else:
                print(f"    +{cp:3d}PA : {s:.3f}  [{lo:.3f}, {hi:.3f}]  n={n:,}")

    print(f"\nSurvival curves written to: {SURVIVAL_JSON}")

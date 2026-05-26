"""Bounce probability calibration backtest — walk-forward 2023-2025.

Validates whether the historical comp matcher's predicted bounce probabilities
are calibrated: do players predicted at 63% bounce actually bounce at 63%?

Method:
  1. Build out-of-sample snapshots for 2023-2025 (30-PA milestones, rn>=150)
  2. For each snapshot, find matching comps from 2015-2022 ONLY (hold-out)
  3. Predict p_bounce from those comps (fraction where next_30pa > snap_l150 + 0.010)
  4. Observe actual next-30-PA xwOBA within 2023-2025 data
  5. Build calibration curve in 5 probability buckets
  6. Compute ECE, Brier score, log-loss
  7. Optional isotonic recalibration if ECE > 0.07

Usage:
    python scripts/xfp/bounce_calibration_backtest.py
    python scripts/xfp/bounce_calibration_backtest.py --no-recal   # skip isotonic fit
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

CACHE_DIR = REPO / "data" / "research" / "xfp_cache"
HIST_SNAP_PATH = CACHE_DIR / "historical_comp_snapshots.parquet"
REPORT_PATH = REPO / "data" / "research" / "bounce_calibration_report_2026-05-25.md"
RAW_CSV_PATH = REPO / "data" / "research" / "calibration_data_2023_2025.csv"
RECAL_MAP_PATH = REPO / "data" / "research" / "bounce_calibration_map.json"

HIST_YEARS = list(range(2015, 2023))   # training set — never touch 2023-2025
TEST_YEARS = list(range(2023, 2026))   # out-of-sample

BOUNCE_THRESH = 0.010
MIN_COMPS = 5
MIN_NEXT_PA = 30

# Calibration probability buckets
BUCKETS = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.001)]
BUCKET_LABELS = ["[0-20%)", "[20-40%)", "[40-60%)", "[60-80%)", "[80-100%]"]


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------

def _parquet_path(year: int) -> str:
    return (CACHE_DIR / f"statcast_{year}.parquet").as_posix()


def _union_sql(years: list[int]) -> str:
    parts = []
    for y in years:
        p = _parquet_path(y)
        parts.append(
            f"SELECT batter, game_date, estimated_woba_using_speedangle AS xwoba, {y} AS year "
            f"FROM read_parquet('{p}') "
            f"WHERE events IS NOT NULL AND events != '' "
            f"AND estimated_woba_using_speedangle IS NOT NULL"
        )
    return " UNION ALL ".join(parts)


# ---------------------------------------------------------------------------
# Step 1: Build out-of-sample snapshots for 2023-2025
# ---------------------------------------------------------------------------

def build_oos_snapshots(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Build 30-PA milestone snapshots for 2023-2025, using only career data
    available up to each snapshot (i.e. 2015 through snapshot date inclusive).

    Returns a DataFrame with columns:
      batter, snap_rn, snap_date, snap_l150, snap_percentile, snap_total_pa,
      snap_month, actual_next_30pa_xwoba, n_next_30
    """
    print("[oos-snapshots] building 2023-2025 out-of-sample snapshots...")
    t0 = time.time()

    # Load ALL years 2015-2025 to compute career context at each snapshot
    all_union = _union_sql(list(range(2015, 2026)))

    # Test-year filter: only flag events from 2023-2025 as potential milestones
    test_years_sql = ",".join(str(y) for y in TEST_YEARS)

    sql = f"""
    WITH all_events AS (
        {all_union}
    ),
    ranked AS (
        SELECT batter, game_date, xwoba, year,
               EXTRACT(MONTH FROM CAST(game_date AS DATE)) AS month,
               ROW_NUMBER() OVER (PARTITION BY batter ORDER BY game_date, xwoba) AS rn
        FROM all_events
    ),
    rolling AS (
        SELECT batter, rn, game_date, month, xwoba, year,
               AVG(xwoba) OVER (
                   PARTITION BY batter ORDER BY rn
                   ROWS BETWEEN 149 PRECEDING AND CURRENT ROW
               ) AS roll150
        FROM ranked
    ),
    -- Percentile for each row: fraction of rolling-150 windows before current that are lower
    -- We compute this within batter using only rows up to the milestone (cumulative pct)
    pct_all AS (
        SELECT batter, rn, roll150,
               PERCENT_RANK() OVER (PARTITION BY batter ORDER BY roll150) AS pct_rank_all
        FROM rolling
        WHERE rn >= 150
    ),
    milestones AS (
        SELECT r.batter, r.rn, r.game_date, r.month, r.xwoba, r.year,
               r.roll150, pb.pct_rank_all AS snap_percentile
        FROM rolling r
        JOIN pct_all pb ON pb.batter = r.batter AND pb.rn = r.rn
        -- Only milestone rows that fall in the TEST years
        WHERE r.rn >= 150 AND r.rn % 30 = 0 AND r.year IN ({test_years_sql})
    ),
    -- Compute actual next 30 PA outcomes from ALL 2015-2025 data
    next_pa AS (
        SELECT
            m.batter,
            m.rn AS snap_rn,
            m.game_date AS snap_date,
            m.roll150 AS snap_l150,
            COALESCE(m.snap_percentile, 0.5) AS snap_percentile,
            -- total PA from 2015 through snapshot date (career PA at snap)
            m.rn AS snap_total_pa,
            m.month AS snap_month,
            AVG(e.xwoba) FILTER (WHERE e.rn > m.rn AND e.rn <= m.rn + 30) AS actual_next_30pa_xwoba,
            COUNT(e.xwoba) FILTER (WHERE e.rn > m.rn AND e.rn <= m.rn + 30) AS n_next_30
        FROM milestones m
        JOIN rolling e ON e.batter = m.batter
        GROUP BY m.batter, m.rn, m.game_date, m.roll150, m.snap_percentile, m.month
    )
    SELECT * FROM next_pa
    WHERE n_next_30 >= {MIN_NEXT_PA}
    """

    df = con.execute(sql).df()
    elapsed = time.time() - t0
    print(f"[oos-snapshots] {len(df):,} snapshots built in {elapsed:.1f}s")
    return df


# ---------------------------------------------------------------------------
# Step 2: Load 2015-2022 historical comps (the training set)
# ---------------------------------------------------------------------------

def load_hist_comps(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Load historical comp snapshots filtered to 2015-2022 only."""
    print("[hist-comps] loading 2015-2022 historical comps...")
    if not HIST_SNAP_PATH.exists():
        raise FileNotFoundError(
            f"Historical snapshot cache not found: {HIST_SNAP_PATH}\n"
            "Run historical_comp_matcher.py once to build it."
        )

    sql = f"""
    SELECT batter, snap_l150, snap_total_pa, snap_month, snap_percentile,
           next_30pa_xwoba, snap_date
    FROM read_parquet('{HIST_SNAP_PATH.as_posix()}')
    WHERE CAST(YEAR(CAST(snap_date AS DATE)) AS INTEGER) <= 2022
      AND next_30pa_xwoba IS NOT NULL
    """
    df = con.execute(sql).df()
    print(f"[hist-comps] {len(df):,} 2015-2022 comp snapshots loaded")
    return df


# ---------------------------------------------------------------------------
# Step 3: Match each OOS snapshot against historical comps and predict p_bounce
# ---------------------------------------------------------------------------

def predict_bounce_probs(
    oos_df: pd.DataFrame,
    hist_df: pd.DataFrame,
    percentile_window: float = 0.10,
    pa_window: float = 0.20,
    month_window: int = 1,
) -> pd.DataFrame:
    """For each OOS snapshot, find matching 2015-2022 comps and predict p_bounce."""
    print(f"[predict] matching {len(oos_df):,} OOS snapshots against {len(hist_df):,} hist comps...")
    t0 = time.time()

    # Pre-convert hist arrays for vectorised matching
    h_pct = hist_df["snap_percentile"].values
    h_pa = hist_df["snap_total_pa"].values
    h_month = hist_df["snap_month"].values
    h_l150 = hist_df["snap_l150"].values
    h_next30 = hist_df["next_30pa_xwoba"].values

    records = []
    n_no_comps = 0

    for _, row in oos_df.iterrows():
        snap_pct = row["snap_percentile"]
        snap_pa = row["snap_total_pa"]
        snap_month = int(row["snap_month"])
        snap_l150 = row["snap_l150"]
        batter = int(row["batter"])

        # Month filter (modular wrap)
        valid_months = set()
        for m in range(snap_month - month_window, snap_month + month_window + 1):
            valid_months.add(((m - 1) % 12) + 1)

        mask = (
            (np.abs(h_pct - snap_pct) <= percentile_window)
            & (h_pa >= snap_pa * (1 - pa_window))
            & (h_pa <= snap_pa * (1 + pa_window))
            & np.isin(h_month, list(valid_months))
            & ~np.isnan(h_next30)
        )

        comp_l150 = h_l150[mask]
        comp_next30 = h_next30[mask]
        n_comps = mask.sum()

        if n_comps < MIN_COMPS:
            n_no_comps += 1
            continue

        predicted_p_bounce = float(np.mean(comp_next30 > comp_l150 + BOUNCE_THRESH))
        actual_bounced = int(
            float(row["actual_next_30pa_xwoba"]) > snap_l150 + BOUNCE_THRESH
        )

        records.append({
            "batter": batter,
            "snap_date": row["snap_date"],
            "snap_rn": int(row["snap_rn"]),
            "snap_percentile": snap_pct,
            "snap_l150": snap_l150,
            "snap_month": snap_month,
            "snap_total_pa": snap_pa,
            "actual_next_30pa_xwoba": float(row["actual_next_30pa_xwoba"]),
            "actual_bounced": actual_bounced,
            "predicted_p_bounce": predicted_p_bounce,
            "n_comps": n_comps,
        })

    elapsed = time.time() - t0
    print(f"[predict] {len(records):,} snapshots with predictions "
          f"({n_no_comps:,} dropped — insufficient comps) in {elapsed:.1f}s")
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Step 4-5: Calibration metrics
# ---------------------------------------------------------------------------

def calibration_table(df: pd.DataFrame, label: str = "all") -> pd.DataFrame:
    """Build calibration curve table from prediction DataFrame."""
    rows = []
    for (lo, hi), bucket_label in zip(BUCKETS, BUCKET_LABELS):
        mask = (df["predicted_p_bounce"] >= lo) & (df["predicted_p_bounce"] < hi)
        sub = df[mask]
        n = len(sub)
        if n == 0:
            rows.append({
                "bucket": bucket_label,
                "n": 0,
                "mean_predicted": float("nan"),
                "actual_bounce_rate": float("nan"),
                "calibration_error": float("nan"),
            })
        else:
            mean_pred = sub["predicted_p_bounce"].mean()
            actual_rate = sub["actual_bounced"].mean()
            rows.append({
                "bucket": bucket_label,
                "n": n,
                "mean_predicted": mean_pred,
                "actual_bounce_rate": actual_rate,
                "calibration_error": abs(mean_pred - actual_rate),
            })
    return pd.DataFrame(rows)


def compute_ece(cal_df: pd.DataFrame, n_total: int) -> float:
    ece = 0.0
    for _, row in cal_df.iterrows():
        if row["n"] > 0 and not np.isnan(row["calibration_error"]):
            ece += (row["n"] / n_total) * row["calibration_error"]
    return ece


def compute_brier(df: pd.DataFrame) -> float:
    return float(np.mean((df["predicted_p_bounce"] - df["actual_bounced"]) ** 2))


def compute_log_loss(df: pd.DataFrame, eps: float = 1e-7) -> float:
    p = df["predicted_p_bounce"].clip(eps, 1 - eps).values
    y = df["actual_bounced"].values
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


# ---------------------------------------------------------------------------
# Step 7: Isotonic recalibration
# ---------------------------------------------------------------------------

def fit_isotonic(df: pd.DataFrame) -> dict:
    """Fit isotonic regression and save calibration map."""
    try:
        from sklearn.isotonic import IsotonicRegression
    except ImportError:
        print("[recal] sklearn not available — skipping isotonic recalibration")
        return {}

    ir = IsotonicRegression(out_of_bounds="clip")
    x = df["predicted_p_bounce"].values
    y = df["actual_bounced"].values
    ir.fit(x, y)

    # Build a lookup table at 0.01 increments
    grid = np.linspace(0.0, 1.0, 101)
    calibrated = ir.predict(grid)
    mapping = {round(float(g), 2): round(float(c), 4) for g, c in zip(grid, calibrated)}

    RECAL_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RECAL_MAP_PATH, "w") as f:
        json.dump(mapping, f, indent=2)
    print(f"[recal] calibration map saved to {RECAL_MAP_PATH.name}")
    return mapping


# ---------------------------------------------------------------------------
# Step 6: Write report
# ---------------------------------------------------------------------------

def verdict(ece: float, cal_df: pd.DataFrame) -> tuple[str, str]:
    """Return (verdict_label, recommendation)."""
    # Find systematic direction of error
    valid = cal_df.dropna(subset=["mean_predicted", "actual_bounce_rate"])
    if len(valid) == 0:
        return "UNKNOWN", "Insufficient data for verdict."

    over_count = (valid["mean_predicted"] > valid["actual_bounce_rate"]).sum()
    under_count = (valid["mean_predicted"] < valid["actual_bounce_rate"]).sum()

    if ece < 0.05:
        label = "WELL_CALIBRATED"
        rec = "No threshold adjustment needed. Model probabilities can be used directly."
    elif ece < 0.10:
        label = "ACCEPTABLE"
        if over_count > under_count:
            rec = (
                "Slight overconfidence detected. Consider applying a small shrinkage: "
                "calibrated_p = 0.9 * raw_p + 0.05 (or use the isotonic map)."
            )
        else:
            rec = (
                "Slight underconfidence detected. Model may under-report bounce probability. "
                "Consider applying isotonic recalibration."
            )
    else:
        if over_count > under_count:
            label = "OVERCONFIDENT"
            rec = (
                "Model is systematically overconfident. "
                "Apply isotonic recalibration before using probabilities for decisions."
            )
        else:
            label = "UNDERCONFIDENT"
            rec = (
                "Model is systematically underconfident. "
                "Apply isotonic recalibration before using probabilities for decisions."
            )
    return label, rec


def format_cal_table(cal_df: pd.DataFrame) -> str:
    header = "| Predicted bucket | n | Mean predicted | Actual bounce rate | Error |\n"
    sep = "|---|---|---|---|---|\n"
    rows = []
    for _, r in cal_df.iterrows():
        if r["n"] == 0:
            rows.append(f"| {r['bucket']} | 0 | — | — | — |")
        else:
            rows.append(
                f"| {r['bucket']} | {int(r['n'])} "
                f"| {r['mean_predicted']:.1%} "
                f"| {r['actual_bounce_rate']:.1%} "
                f"| {r['calibration_error']:.3f} |"
            )
    return header + sep + "\n".join(rows)


def write_report(
    df: pd.DataFrame,
    cal_all: pd.DataFrame,
    cal_slump: pd.DataFrame,
    cal_peak: pd.DataFrame,
    brier: float,
    ll: float,
    ece: float,
    verdict_label: str,
    verdict_rec: str,
    did_recal: bool,
) -> None:
    n_total = len(df)
    n_slump = (df["snap_percentile"] < 0.20).sum()
    n_peak = (df["snap_percentile"] > 0.80).sum()
    ece_slump = compute_ece(cal_slump, n_slump) if n_slump > 0 else float("nan")
    ece_peak = compute_ece(cal_peak, n_peak) if n_peak > 0 else float("nan")

    lines = [
        "# Bounce probability calibration — 2023-2025 walk-forward backtest",
        "",
        "## Overall calibration",
        f"- Brier score: {brier:.4f} (perfect = 0, random = 0.25)",
        f"- Log loss: {ll:.4f}",
        f"- Expected calibration error (ECE): {ece:.4f} (< 0.05 = well-calibrated)",
        f"- N snapshots with predictions: {n_total:,}",
        "",
        "## Calibration curve",
        "",
        format_cal_table(cal_all),
        "",
        f"## Slumper-specific calibration (career %ile < 20th) — n={n_slump:,}, ECE={ece_slump:.4f}",
        "",
        format_cal_table(cal_slump),
        "",
        f"## Peaker-specific calibration (career %ile > 80th) — n={n_peak:,}, ECE={ece_peak:.4f}",
        "",
        format_cal_table(cal_peak),
        "",
        "## Verdict",
        f"**{verdict_label}**",
        "",
        verdict_rec,
    ]

    if did_recal:
        lines += [
            "",
            f"Isotonic recalibration map saved to `{RECAL_MAP_PATH.name}` "
            "(100-point grid, apply via lookup before surfacing probabilities).",
        ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"[report] written to {REPORT_PATH.name}")


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------

def print_summary(
    cal_all: pd.DataFrame,
    brier: float,
    ll: float,
    ece: float,
    verdict_label: str,
    verdict_rec: str,
) -> None:
    print("\n" + "=" * 62)
    print("  BOUNCE PROBABILITY CALIBRATION — 2023-2025 WALK-FORWARD")
    print("=" * 62)
    print(f"  Brier score : {brier:.4f}  (random baseline = 0.25)")
    print(f"  Log loss    : {ll:.4f}")
    print(f"  ECE         : {ece:.4f}  (< 0.05 = well-calibrated)")
    print()
    print("  Calibration curve:")
    print(f"  {'Bucket':<14} {'n':>6}  {'Mean pred':>10}  {'Actual':>10}  {'Error':>8}")
    print(f"  {'-'*14} {'-'*6}  {'-'*10}  {'-'*10}  {'-'*8}")
    for _, r in cal_all.iterrows():
        if r["n"] == 0:
            print(f"  {r['bucket']:<14} {'0':>6}  {'—':>10}  {'—':>10}  {'—':>8}")
        else:
            print(
                f"  {r['bucket']:<14} {int(r['n']):>6}  "
                f"{r['mean_predicted']:>10.1%}  "
                f"{r['actual_bounce_rate']:>10.1%}  "
                f"{r['calibration_error']:>8.3f}"
            )
    print()
    print(f"  Verdict: {verdict_label}")
    print(f"  {verdict_rec}")
    print("=" * 62)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_backtest(skip_recal: bool = False) -> None:
    con = duckdb.connect()

    # Step 1: build OOS snapshots
    oos_df = build_oos_snapshots(con)

    # Step 2: load historical comps (2015-2022 only)
    hist_df = load_hist_comps(con)
    con.close()

    # Step 3: predict bounce probabilities
    pred_df = predict_bounce_probs(oos_df, hist_df)

    if len(pred_df) < 20:
        print(f"[ERROR] Only {len(pred_df)} snapshots with predictions — insufficient for calibration.")
        return

    # Save raw data
    RAW_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    pred_df.to_csv(RAW_CSV_PATH, index=False)
    print(f"[data] raw predictions saved to {RAW_CSV_PATH.name}")

    # Steps 4-5: calibration metrics
    brier = compute_brier(pred_df)
    ll = compute_log_loss(pred_df)

    cal_all = calibration_table(pred_df, "all")
    ece = compute_ece(cal_all, len(pred_df))

    slump_df = pred_df[pred_df["snap_percentile"] < 0.20]
    peak_df = pred_df[pred_df["snap_percentile"] > 0.80]
    cal_slump = calibration_table(slump_df, "slump")
    cal_peak = calibration_table(peak_df, "peak")

    verdict_label, verdict_rec = verdict(ece, cal_all)

    # Step 7: isotonic recalibration if needed
    did_recal = False
    if not skip_recal and ece > 0.07:
        print(f"[recal] ECE={ece:.4f} > 0.07 — fitting isotonic recalibration...")
        fit_isotonic(pred_df)
        did_recal = True

    # Step 6: write report
    write_report(
        pred_df, cal_all, cal_slump, cal_peak,
        brier, ll, ece, verdict_label, verdict_rec, did_recal,
    )

    # Print summary
    print_summary(cal_all, brier, ll, ece, verdict_label, verdict_rec)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bounce probability calibration backtest")
    parser.add_argument(
        "--no-recal", action="store_true",
        help="Skip isotonic recalibration even if ECE > 0.07",
    )
    args = parser.parse_args()
    run_backtest(skip_recal=args.no_recal)


if __name__ == "__main__":
    main()

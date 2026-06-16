"""Test for survivorship bias in shrinkage k calibration sample.

Existing calibrate_shrinkage_k.py picks top-200 hitters / top-100 SPs by
CURRENT rh3/rp3 rank (as of 2026-06-06). This biases the sample toward
players who survived 2024-2025 well enough to still be top-ranked today.

This script:
1. Builds a TIME-CORRECT sample: at each as_of date, identify top-200
   hitters / top-100 SPs by ROLLING 60-day FP/g rank (computed from
   MLB Stats API gameLog as-of that date).
2. Re-runs shrinkage k calibration on the time-correct sample.
3. Compares composition + optimal k + per-lens lifts.

Wider candidate pool: top-500 hitters / top-300 SPs by current rh3/rp3
(superset). For each as_of date, we re-rank from observed actuals (no
look-ahead) and select top-N.

Output: data/research/validation_runs/survivorship_bias_check_2026-06-06.md
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path("c:/Users/Joshua/plv_clone")
OUT_MD = ROOT / "data/research/validation_runs/survivorship_bias_check_2026-06-06.md"
CACHE_DIR = ROOT / "data/research/_cache_survivorship"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Wider superset to find peak-then-faded players
SUPERSET_H = 500
SUPERSET_SP = 300
# Final pool size at each as_of (matches original calibration)
TOP_H = 200
TOP_SP = 100
# Use a 6-date subset for the time-correct calibration (~300 SP snapshots, ~1000 H)
AS_OF_DATES = [
    date(2024, 6, 1), date(2024, 7, 1), date(2024, 8, 1),
    date(2025, 6, 1), date(2025, 7, 1), date(2025, 8, 1),
]
PRIOR_SEASONS_NEEDED = [2023, 2024, 2025]
K_VALUES = [20, 40, 80, 150, 300, 500]
TIMEOUT = 20
WORKERS = 12


# ---------- Scoring (copied from calibrate_shrinkage_k.py) ----------
def parse_ip(ip) -> float:
    if ip is None or ip == "":
        return 0.0
    s = str(ip)
    try:
        whole, frac = s.split(".")
        return int(whole) + int(frac) / 3.0
    except Exception:
        try:
            return float(s)
        except Exception:
            return 0.0


def fp_hitter(row):
    r = int(row.get("runs", 0) or 0)
    tb = row.get("totalBases")
    if tb is None or tb == "":
        h = int(row.get("hits", 0) or 0)
        d = int(row.get("doubles", 0) or 0)
        t = int(row.get("triples", 0) or 0)
        hr = int(row.get("homeRuns", 0) or 0)
        singles = h - d - t - hr
        tb = singles + 2 * d + 3 * t + 4 * hr
    tb = int(tb or 0)
    rbi = int(row.get("rbi", 0) or 0)
    bb = int(row.get("baseOnBalls", 0) or 0)
    hbp = int(row.get("hitByPitch", 0) or 0)
    sb = int(row.get("stolenBases", 0) or 0)
    k = int(row.get("strikeOuts", 0) or 0)
    pa = int(row.get("plateAppearances", 0) or 0)
    return r + tb + rbi + bb + hbp + sb - k, pa


def fp_sp(row):
    gs = int(row.get("gamesStarted", 0) or 0)
    if gs < 1:
        return None
    ip = parse_ip(row.get("inningsPitched", 0))
    k = int(row.get("strikeOuts", 0) or 0)
    h = int(row.get("hits", 0) or 0)
    er = int(row.get("earnedRuns", 0) or 0)
    bb = int(row.get("baseOnBalls", 0) or 0)
    hbp = int(row.get("hitByPitch", 0) or 0)
    return k + ip * 3.3 - h - 2 * er - bb - hbp


def fetch_gamelog(pid: int, group: str, season: int) -> list[dict]:
    url = (
        f"https://statsapi.mlb.com/api/v1/people/{pid}/stats"
        f"?stats=gameLog&season={season}&group={group}"
    )
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        j = r.json()
        st = j.get("stats", [])
        if not st:
            return []
        splits = st[0].get("splits", [])
        rows = []
        for sp in splits:
            d = sp.get("date")
            stat = sp.get("stat", {})
            stat["_date"] = d
            rows.append(stat)
        return rows
    except Exception:
        return []


def parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def build_player_logs(ids: list[int], group: str, label: str) -> dict[int, pd.DataFrame]:
    cache_pkl = CACHE_DIR / f"logs_{label}.parquet"
    if cache_pkl.exists():
        print(f"  loading cached {label} logs from {cache_pkl}", file=sys.stderr)
        df = pd.read_parquet(cache_pkl)
        out = {}
        for pid, sub in df.groupby("pid"):
            out[int(pid)] = sub[["date", "fp", "pa_or_gs"]].reset_index(drop=True)
        return out

    out: dict[int, pd.DataFrame] = {}
    tasks = [(pid, season) for pid in ids for season in PRIOR_SEASONS_NEEDED]
    print(f"  fetching {len(tasks)} gamelogs ({group})...", file=sys.stderr)
    raw: dict[int, list[list[dict]]] = {pid: [] for pid in ids}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_gamelog, pid, group, season): (pid, season) for pid, season in tasks}
        done = 0
        for f in as_completed(futs):
            pid, season = futs[f]
            try:
                rows = f.result()
            except Exception:
                rows = []
            raw[pid].append(rows)
            done += 1
            if done % 200 == 0:
                print(f"    {done}/{len(tasks)}", file=sys.stderr)
    all_recs = []
    for pid, batches in raw.items():
        records = []
        for batch in batches:
            for r in batch:
                d = parse_date(r.get("_date", ""))
                if d is None:
                    continue
                if group == "hitting":
                    fp, pa = fp_hitter(r)
                    if pa <= 0:
                        continue
                    records.append((d, fp, pa))
                else:
                    fp = fp_sp(r)
                    if fp is None:
                        continue
                    records.append((d, fp, 1))
        if records:
            df = pd.DataFrame(records, columns=["date", "fp", "pa_or_gs"])
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
            out[pid] = df
            for _, r in df.iterrows():
                all_recs.append({"pid": pid, "date": r["date"], "fp": r["fp"], "pa_or_gs": r["pa_or_gs"]})
    if all_recs:
        pd.DataFrame(all_recs).to_parquet(cache_pkl)
    return out


# ---------- Time-correct ranking at each as_of ----------
def rank_by_rolling_60d(logs: dict[int, pd.DataFrame], as_of: date, group: str) -> dict[int, float]:
    """Rank players by rolling-60d FP/game (hitter) or FP/start (SP)
    using games observed strictly before as_of."""
    ranks = {}
    as_of_ts = pd.Timestamp(as_of)
    lo = as_of_ts - timedelta(days=60)
    for pid, df in logs.items():
        sub = df[(df["date"] >= lo) & (df["date"] < as_of_ts)]
        if group == "hitting":
            pa = int(sub["pa_or_gs"].sum())
            if pa < 30 or len(sub) < 8:
                continue
        else:
            if len(sub) < 4:
                continue
        ranks[pid] = sub["fp"].mean()
    return ranks


def select_top_at_as_of(rolling: dict[int, float], top_n: int) -> list[int]:
    sorted_pids = sorted(rolling.items(), key=lambda kv: -kv[1])
    return [pid for pid, _ in sorted_pids[:top_n]]


# ---------- Snapshot building (same shape as original) ----------
def build_snapshots_hitter_for_pids(logs, pid_by_asof: dict[date, list[int]]) -> pd.DataFrame:
    rows = []
    for as_of, pids in pid_by_asof.items():
        for pid in pids:
            df = logs.get(pid)
            if df is None:
                continue
            past = df[df["date"] < pd.Timestamp(as_of)]
            future = df[(df["date"] >= pd.Timestamp(as_of)) &
                        (df["date"] < pd.Timestamp(as_of + timedelta(days=30)))]
            l21 = past[past["date"] >= pd.Timestamp(as_of - timedelta(days=21))]
            l42 = past[past["date"] >= pd.Timestamp(as_of - timedelta(days=42))]
            pa_l21 = int(l21["pa_or_gs"].sum())
            n_l21 = len(l21)
            if pa_l21 < 10 or n_l21 < 3:
                continue
            l21_avg = l21["fp"].mean()
            l42_avg = l42["fp"].mean() if len(l42) >= 3 else np.nan
            py = past[past["date"].dt.year == as_of.year - 1]
            py2 = past[past["date"].dt.year == as_of.year - 2]
            prior_avg = py["fp"].mean() if len(py) >= 20 else np.nan
            prior2_avg = py2["fp"].mean() if len(py2) >= 20 else np.nan
            if len(future) < 5:
                continue
            target = future["fp"].mean()
            rows.append({
                "pid": pid, "as_of": as_of, "n_l21": n_l21,
                "l21_avg": l21_avg, "l42_avg": l42_avg,
                "prior_avg": prior_avg, "prior2_avg": prior2_avg,
                "target": target, "n_future": len(future),
            })
    return pd.DataFrame(rows)


def build_snapshots_sp_for_pids(logs, pid_by_asof: dict[date, list[int]]) -> pd.DataFrame:
    rows = []
    for as_of, pids in pid_by_asof.items():
        for pid in pids:
            df = logs.get(pid)
            if df is None:
                continue
            past = df[df["date"] < pd.Timestamp(as_of)]
            future = df[df["date"] >= pd.Timestamp(as_of)]
            l21 = past[past["date"] >= pd.Timestamp(as_of - timedelta(days=21))]
            l42 = past[past["date"] >= pd.Timestamp(as_of - timedelta(days=42))]
            n_l21 = len(l21)
            if n_l21 < 2:
                continue
            l21_avg = l21["fp"].mean()
            l42_avg = l42["fp"].mean() if len(l42) >= 3 else np.nan
            py = past[past["date"].dt.year == as_of.year - 1]
            py2 = past[past["date"].dt.year == as_of.year - 2]
            prior_avg = py["fp"].mean() if len(py) >= 5 else np.nan
            prior2_avg = py2["fp"].mean() if len(py2) >= 5 else np.nan
            if len(future) < 3:
                continue
            target = future.head(5)["fp"].mean()
            rows.append({
                "pid": pid, "as_of": as_of, "n_l21": n_l21,
                "l21_avg": l21_avg, "l42_avg": l42_avg,
                "prior_avg": prior_avg, "prior2_avg": prior2_avg,
                "target": target, "n_future": min(len(future), 5),
            })
    return pd.DataFrame(rows)


def compute_predictions(snap):
    df = snap.copy()
    df["pred_L21"] = df["l21_avg"]
    df["pred_L42"] = df["l42_avg"]
    df["pred_prior"] = df["prior_avg"]
    for k in K_VALUES:
        df[f"pred_k{k}"] = (df["n_l21"] * df["l21_avg"] + k * df["prior_avg"]) / (df["n_l21"] + k)
    twoyr = 0.6 * df["prior_avg"] + 0.4 * df["prior2_avg"]
    twoyr = twoyr.where(df["prior2_avg"].notna(), df["prior_avg"])
    df["pred_2yrK80"] = (df["n_l21"] * df["l21_avg"] + 80 * twoyr) / (df["n_l21"] + 80)
    return df


def metrics(y, yhat):
    mask = (~pd.isna(y)) & (~pd.isna(yhat))
    y = y[mask].to_numpy()
    yhat = yhat[mask].to_numpy()
    if len(y) < 5:
        return dict(n=len(y), mae=np.nan, rmse=np.nan, r2=np.nan, median=np.nan)
    err = yhat - y
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    median = float(np.median(np.abs(err)))
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return dict(n=int(len(y)), mae=mae, rmse=rmse, r2=r2, median=median)


PREDICTORS = (
    ["pred_L21", "pred_prior", "pred_L42"]
    + [f"pred_k{k}" for k in K_VALUES]
    + ["pred_2yrK80"]
)
PRED_LABELS = {
    "pred_L21": "pure L21",
    "pred_L42": "pure L42",
    "pred_prior": "pure prior year",
    **{f"pred_k{k}": f"shrink k={k}{' (current)' if k == 80 else ''}" for k in K_VALUES},
    "pred_2yrK80": "two-year prior shrunk k=80",
}


def evaluate(df):
    out = []
    for p in PREDICTORS:
        m = metrics(df["target"], df[p])
        m["predictor"] = PRED_LABELS.get(p, p)
        out.append(m)
    return pd.DataFrame(out)[["predictor", "n", "mae", "rmse", "r2", "median"]]


def fmt_table(df, cols=("mae", "rmse", "r2", "median")):
    header = "| Predictor | " + " | ".join(c.upper() for c in cols) + " | N |"
    sep = "| --- " * (len(cols) + 2) + "|"
    lines = [header, sep]
    for _, row in df.iterrows():
        vals = []
        for c in cols:
            v = row[c]
            vals.append(f"{v:.3f}" if pd.notna(v) else "—")
        lines.append(f"| {row['predictor']} | " + " | ".join(vals) + f" | {row['n']} |")
    return "\n".join(lines)


def main():
    print("Loading projections…", file=sys.stderr)
    h_df = pd.read_csv(ROOT / "data/outputs/xfp_rh3_projections.csv")
    sp_df = pd.read_csv(ROOT / "data/outputs/xfp_rp3_projections.csv")

    h_super_ids = h_df.sort_values("rank").head(SUPERSET_H)["batter"].astype(int).tolist()
    sp_super_ids = sp_df.sort_values("rank").head(SUPERSET_SP)["pitcher"].astype(int).tolist()
    h_current_top = set(h_df.sort_values("rank").head(TOP_H)["batter"].astype(int).tolist())
    sp_current_top = set(sp_df.sort_values("rank").head(TOP_SP)["pitcher"].astype(int).tolist())

    print(f"Hitter superset: {len(h_super_ids)}  SP superset: {len(sp_super_ids)}", file=sys.stderr)

    print("Fetching hitter gamelogs (superset)…", file=sys.stderr)
    h_logs = build_player_logs(h_super_ids, "hitting", "h_super")
    print("Fetching SP gamelogs (superset)…", file=sys.stderr)
    sp_logs = build_player_logs(sp_super_ids, "pitching", "sp_super")
    print(f"  hitter logs: {len(h_logs)}  SP logs: {len(sp_logs)}", file=sys.stderr)

    # Time-correct top-N at each as_of
    h_pid_by_asof = {}
    sp_pid_by_asof = {}
    for d in AS_OF_DATES:
        h_rolling = rank_by_rolling_60d(h_logs, d, "hitting")
        sp_rolling = rank_by_rolling_60d(sp_logs, d, "pitching")
        h_pid_by_asof[d] = select_top_at_as_of(h_rolling, TOP_H)
        sp_pid_by_asof[d] = select_top_at_as_of(sp_rolling, TOP_SP)
        print(f"  as_of {d}: H top {len(h_pid_by_asof[d])}  SP top {len(sp_pid_by_asof[d])}", file=sys.stderr)

    # Build snapshots using TIME-CORRECT pid lists
    print("Building time-correct hitter snapshots…", file=sys.stderr)
    h_snap_tc = build_snapshots_hitter_for_pids(h_logs, h_pid_by_asof)
    print(f"  hitter snapshots (time-correct): {len(h_snap_tc)}", file=sys.stderr)
    print("Building time-correct SP snapshots…", file=sys.stderr)
    sp_snap_tc = build_snapshots_sp_for_pids(sp_logs, sp_pid_by_asof)
    print(f"  SP snapshots (time-correct): {len(sp_snap_tc)}", file=sys.stderr)

    h_snap_tc = compute_predictions(h_snap_tc)
    sp_snap_tc = compute_predictions(sp_snap_tc)

    # Load original current-rank snapshots, subset to same as_of dates
    h_orig = pd.read_parquet(ROOT / "data/research/validation_runs/shrinkage_h_snap_2026-06-06.parquet")
    sp_orig = pd.read_parquet(ROOT / "data/research/validation_runs/shrinkage_sp_snap_2026-06-06.parquet")
    h_orig["as_of"] = pd.to_datetime(h_orig["as_of"]).dt.date
    sp_orig["as_of"] = pd.to_datetime(sp_orig["as_of"]).dt.date
    h_orig_sub = h_orig[h_orig["as_of"].isin(AS_OF_DATES)].copy()
    sp_orig_sub = sp_orig[sp_orig["as_of"].isin(AS_OF_DATES)].copy()

    # Composition comparison
    h_orig_pids = set(h_orig_sub["pid"].astype(int).tolist())
    h_tc_pids = set(h_snap_tc["pid"].astype(int).tolist()) if len(h_snap_tc) else set()
    sp_orig_pids = set(sp_orig_sub["pid"].astype(int).tolist())
    sp_tc_pids = set(sp_snap_tc["pid"].astype(int).tolist()) if len(sp_snap_tc) else set()

    h_in_tc_not_orig = h_tc_pids - h_orig_pids  # peak-then-faded players NEW in time-correct
    h_in_orig_not_tc = h_orig_pids - h_tc_pids  # survivor-only players DROPPED in time-correct
    h_overlap = h_tc_pids & h_orig_pids
    sp_in_tc_not_orig = sp_tc_pids - sp_orig_pids
    sp_in_orig_not_tc = sp_orig_pids - sp_tc_pids
    sp_overlap = sp_tc_pids & sp_orig_pids

    # Per-(pid, as_of) pair comparison
    h_orig_pairs = set(zip(h_orig_sub["pid"].astype(int), h_orig_sub["as_of"]))
    h_tc_pairs = set(zip(h_snap_tc["pid"].astype(int), h_snap_tc["as_of"])) if len(h_snap_tc) else set()
    sp_orig_pairs = set(zip(sp_orig_sub["pid"].astype(int), sp_orig_sub["as_of"]))
    sp_tc_pairs = set(zip(sp_snap_tc["pid"].astype(int), sp_snap_tc["as_of"])) if len(sp_snap_tc) else set()

    # Evaluate both samples
    h_eval_orig = evaluate(h_orig_sub.dropna(subset=["pred_k80"]))
    h_eval_tc = evaluate(h_snap_tc.dropna(subset=["pred_k80"])) if len(h_snap_tc) else pd.DataFrame()
    sp_eval_orig = evaluate(sp_orig_sub.dropna(subset=["pred_k80"]))
    sp_eval_tc = evaluate(sp_snap_tc.dropna(subset=["pred_k80"])) if len(sp_snap_tc) else pd.DataFrame()

    # Build name lookup
    h_name = dict(zip(h_df["batter"].astype(int), h_df["player_name"]))
    sp_name = dict(zip(sp_df["pitcher"].astype(int), sp_df["player_name"]))

    # Find examples of "missing" players (in orig pool but dropped from time-correct)
    sample_missing_h = sorted(list(h_in_orig_not_tc))[:10]
    sample_added_h = sorted(list(h_in_tc_not_orig))[:10]
    sample_missing_sp = sorted(list(sp_in_orig_not_tc))[:10]
    sample_added_sp = sorted(list(sp_in_tc_not_orig))[:10]

    # Best shrink k by sample
    SHRINK_LABELS = {f"shrink k={k}{' (current)' if k == 80 else ''}" for k in K_VALUES}

    def best_shrink(ev):
        if len(ev) == 0:
            return "n/a", np.nan
        sub = ev[ev["predictor"].isin(SHRINK_LABELS)]
        if len(sub) == 0:
            return "n/a", np.nan
        r = sub.sort_values("mae").iloc[0]
        return r["predictor"], r["mae"]

    h_best_orig = best_shrink(h_eval_orig)
    h_best_tc = best_shrink(h_eval_tc)
    sp_best_orig = best_shrink(sp_eval_orig)
    sp_best_tc = best_shrink(sp_eval_tc)

    # Per-predictor lift = (pure_L21 MAE - shrink_k MAE) — how much each predictor beats baseline
    def lift_table(ev):
        if len(ev) == 0:
            return pd.DataFrame()
        l21 = ev.loc[ev["predictor"] == "pure L21", "mae"].values
        if len(l21) == 0:
            return pd.DataFrame()
        baseline = l21[0]
        ev = ev.copy()
        ev["lift_vs_L21"] = baseline - ev["mae"]
        return ev[["predictor", "mae", "lift_vs_L21", "n"]]

    h_lift_orig = lift_table(h_eval_orig)
    h_lift_tc = lift_table(h_eval_tc)
    sp_lift_orig = lift_table(sp_eval_orig)
    sp_lift_tc = lift_table(sp_eval_tc)

    # Severity: |Δk| (move in optimal k) + |Δlift_best| (move in best-predictor MAE lift)
    def severity_assessment(orig_best, tc_best, orig_lift, tc_lift, label):
        if pd.isna(orig_best[1]) or pd.isna(tc_best[1]):
            return f"- {label}: insufficient data\n"
        delta_mae = tc_best[1] - orig_best[1]  # positive = TC harder (less inflated)
        # Best predictor lift difference (orig vs tc) — how much does the best beat pure_L21?
        if len(orig_lift) and len(tc_lift):
            orig_best_lift = orig_lift.loc[orig_lift["predictor"] == orig_best[0], "lift_vs_L21"]
            tc_best_lift = tc_lift.loc[tc_lift["predictor"] == tc_best[0], "lift_vs_L21"]
            orig_best_lift = orig_best_lift.iloc[0] if len(orig_best_lift) else np.nan
            tc_best_lift = tc_best_lift.iloc[0] if len(tc_best_lift) else np.nan
            lift_inflation = orig_best_lift - tc_best_lift
        else:
            lift_inflation = np.nan
        # Heuristic — for hitters where MAE base is ~0.6-0.9: small=<0.02, moderate=0.02-0.05, severe=>0.05
        # For SPs where MAE base is ~3.5-4.5: small=<0.20, moderate=0.20-0.50, severe=>0.50
        return delta_mae, lift_inflation

    h_sev = severity_assessment(h_best_orig, h_best_tc, h_lift_orig, h_lift_tc, "Hitter")
    sp_sev = severity_assessment(sp_best_orig, sp_best_tc, sp_lift_orig, sp_lift_tc, "SP")

    # Targets distribution (orig vs TC) — is the time-correct sample tougher?
    h_orig_target_mean = h_orig_sub["target"].mean()
    h_tc_target_mean = h_snap_tc["target"].mean() if len(h_snap_tc) else np.nan
    sp_orig_target_mean = sp_orig_sub["target"].mean()
    sp_tc_target_mean = sp_snap_tc["target"].mean() if len(sp_snap_tc) else np.nan

    # ---- Write markdown ----
    lines = []
    lines.append("# Survivorship Bias Check — Shrinkage k Calibration")
    lines.append("")
    lines.append("**Hypothesis:** Existing shrinkage backtest (`shrinkage_calibration_2026-06-06.md`) drew the player pool from CURRENT (2026-06-06) rh3/rp3 top-200 H / top-100 SP, which excludes 2024-2025 players who started ranked but dropped out by today. This inflates measured lift because survivors are easier to predict (stable, healthy, prime-aged).")
    lines.append("")
    lines.append("## Method")
    lines.append(f"- **Time-correct sample:** at each as_of, rank candidates from a superset (top-{SUPERSET_H} H / top-{SUPERSET_SP} SP by current rh3/rp3) by their ROLLING 60-day FP/g (hitter) or FP/start (SP) computed from MLB Stats API gameLog strictly before as_of. Take top-{TOP_H} H / top-{TOP_SP} SP.")
    lines.append(f"- **as_of dates** (6 of original 10, to keep runtime bounded): {', '.join(d.isoformat() for d in AS_OF_DATES)}")
    lines.append(f"- **Original sample (subset):** same as `shrinkage_calibration_2026-06-06.md` but filtered to the 6 as_of dates above. Pool = top-200 H / top-100 SP by CURRENT rh3/rp3.")
    lines.append("- **Shrinkage families re-evaluated**: pure L21, pure L42, pure prior, shrink k in [20, 40, 80, 150, 300, 500], two-year prior shrunk k=80.")
    lines.append("- **Caveat (acknowledged):** superset itself is top-500/300 by CURRENT rh3/rp3, so true unicorns who washed out by 2026 are still excluded. This test catches 'top-200 today vs top-500 today peak-then-faded' but not 'never in current top-500'.")
    lines.append("")

    lines.append("## Sample composition comparison")
    lines.append("")
    lines.append("### Hitter pool")
    lines.append(f"- Original sample (current-rank top-200, subset to 6 as_of dates): **{len(h_orig_sub)}** snapshots, **{len(h_orig_pids)}** unique pids")
    lines.append(f"- Time-correct sample (rolling-60d top-200 at each as_of): **{len(h_snap_tc)}** snapshots, **{len(h_tc_pids)}** unique pids")
    lines.append(f"- Pid overlap: **{len(h_overlap)}** in both pools")
    lines.append(f"- Pids ONLY in original (survivors): **{len(h_in_orig_not_tc)}** — current top-200 but not top-200 by rolling-60d at any tested as_of")
    lines.append(f"- Pids ONLY in time-correct (peak-then-faded or rookies who broke out): **{len(h_in_tc_not_orig)}** — these are the survivorship-bias-excluded players")
    lines.append(f"- (pid, as_of) pair overlap: **{len(h_orig_pairs & h_tc_pairs)}** / orig={len(h_orig_pairs)} / tc={len(h_tc_pairs)}")
    if sample_missing_h:
        lines.append("- Example survivors-only (in orig sample, dropped from time-correct):")
        for pid in sample_missing_h:
            lines.append(f"  - {h_name.get(pid, pid)} (pid {pid})")
    if sample_added_h:
        lines.append("- Example peak-then-faded (in time-correct, dropped from orig sample):")
        for pid in sample_added_h:
            lines.append(f"  - {h_name.get(pid, pid)} (pid {pid})")
    lines.append("")
    lines.append("### SP pool")
    lines.append(f"- Original sample (current-rank top-100, subset to 6 as_of dates): **{len(sp_orig_sub)}** snapshots, **{len(sp_orig_pids)}** unique pids")
    lines.append(f"- Time-correct sample (rolling-60d top-100 at each as_of): **{len(sp_snap_tc)}** snapshots, **{len(sp_tc_pids)}** unique pids")
    lines.append(f"- Pid overlap: **{len(sp_overlap)}** in both pools")
    lines.append(f"- Pids ONLY in original (survivors): **{len(sp_in_orig_not_tc)}**")
    lines.append(f"- Pids ONLY in time-correct: **{len(sp_in_tc_not_orig)}**")
    lines.append(f"- (pid, as_of) pair overlap: **{len(sp_orig_pairs & sp_tc_pairs)}** / orig={len(sp_orig_pairs)} / tc={len(sp_tc_pairs)}")
    if sample_missing_sp:
        lines.append("- Example survivors-only:")
        for pid in sample_missing_sp:
            lines.append(f"  - {sp_name.get(pid, pid)} (pid {pid})")
    if sample_added_sp:
        lines.append("- Example peak-then-faded:")
        for pid in sample_added_sp:
            lines.append(f"  - {sp_name.get(pid, pid)} (pid {pid})")
    lines.append("")

    lines.append("## Target distribution (sample difficulty)")
    lines.append("")
    lines.append("| Stratum | Original mean target | Time-correct mean target | Δ (orig − tc) |")
    lines.append("| --- | --- | --- | --- |")
    lines.append(f"| Hitter target FP/g | {h_orig_target_mean:.3f} | {h_tc_target_mean:.3f} | {h_orig_target_mean - h_tc_target_mean:+.3f} |")
    lines.append(f"| SP target FP/start | {sp_orig_target_mean:.3f} | {sp_tc_target_mean:.3f} | {sp_orig_target_mean - sp_tc_target_mean:+.3f} |")
    lines.append("")
    lines.append("Interpretation: positive Δ = original sample has higher-scoring targets on average = survivors are easier to predict (production hugs the mean).")
    lines.append("")

    lines.append("## Pooled results — original sample (6 as_of dates only)")
    lines.append("")
    lines.append("### Hitter")
    lines.append(fmt_table(h_eval_orig))
    lines.append("")
    lines.append("### SP")
    lines.append(fmt_table(sp_eval_orig))
    lines.append("")

    lines.append("## Pooled results — time-correct sample")
    lines.append("")
    lines.append("### Hitter")
    lines.append(fmt_table(h_eval_tc) if len(h_eval_tc) else "_insufficient data_")
    lines.append("")
    lines.append("### SP")
    lines.append(fmt_table(sp_eval_tc) if len(sp_eval_tc) else "_insufficient data_")
    lines.append("")

    lines.append("## Optimal shrinkage k by sample")
    lines.append("")
    lines.append("| Position | Original optimal k | Original MAE | Time-correct optimal k | Time-correct MAE | Δ MAE |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    lines.append(f"| Hitter | {h_best_orig[0]} | {h_best_orig[1]:.3f} | {h_best_tc[0]} | {h_best_tc[1]:.3f} | {h_best_tc[1] - h_best_orig[1]:+.3f} |")
    lines.append(f"| SP | {sp_best_orig[0]} | {sp_best_orig[1]:.3f} | {sp_best_tc[0]} | {sp_best_tc[1]:.3f} | {sp_best_tc[1] - sp_best_orig[1]:+.3f} |")
    lines.append("")

    lines.append("## Per-predictor lift comparison")
    lines.append("")
    lines.append("Lift = (pure L21 MAE) − (predictor MAE). Higher = better lift over pure-recent baseline.")
    lines.append("")
    lines.append("### Hitter")
    lines.append("| Predictor | Orig MAE | Orig lift | TC MAE | TC lift | Inflation (orig − tc) |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for p in PREDICTORS:
        label = PRED_LABELS[p]
        o = h_lift_orig[h_lift_orig["predictor"] == label]
        t = h_lift_tc[h_lift_tc["predictor"] == label] if len(h_lift_tc) else pd.DataFrame()
        if len(o) and len(t):
            o_mae, o_lift = o.iloc[0]["mae"], o.iloc[0]["lift_vs_L21"]
            t_mae, t_lift = t.iloc[0]["mae"], t.iloc[0]["lift_vs_L21"]
            lines.append(f"| {label} | {o_mae:.3f} | {o_lift:+.3f} | {t_mae:.3f} | {t_lift:+.3f} | {o_lift - t_lift:+.3f} |")
    lines.append("")
    lines.append("### SP")
    lines.append("| Predictor | Orig MAE | Orig lift | TC MAE | TC lift | Inflation (orig − tc) |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for p in PREDICTORS:
        label = PRED_LABELS[p]
        o = sp_lift_orig[sp_lift_orig["predictor"] == label]
        t = sp_lift_tc[sp_lift_tc["predictor"] == label] if len(sp_lift_tc) else pd.DataFrame()
        if len(o) and len(t):
            o_mae, o_lift = o.iloc[0]["mae"], o.iloc[0]["lift_vs_L21"]
            t_mae, t_lift = t.iloc[0]["mae"], t.iloc[0]["lift_vs_L21"]
            lines.append(f"| {label} | {o_mae:.3f} | {o_lift:+.3f} | {t_mae:.3f} | {t_lift:+.3f} | {o_lift - t_lift:+.3f} |")
    lines.append("")

    # Severity classification
    def classify(delta_mae, lift_inflation, base_scale, low, mod, sev):
        if pd.isna(delta_mae):
            return "INSUFFICIENT DATA"
        ad = abs(delta_mae)
        ai = abs(lift_inflation) if not pd.isna(lift_inflation) else 0
        worst = max(ad, ai)
        if worst < low * base_scale:
            return "LOW (no caveat needed)"
        if worst < mod * base_scale:
            return "MODERATE (add caveat to prior backtest summaries)"
        if worst < sev * base_scale:
            return "MEANINGFUL (recommend re-running calibration with time-correct sample)"
        return "SEVERE (existing calibration likely wrong; re-run mandatory)"

    h_delta = h_sev[0] if isinstance(h_sev, tuple) else np.nan
    h_inflation = h_sev[1] if isinstance(h_sev, tuple) else np.nan
    sp_delta = sp_sev[0] if isinstance(sp_sev, tuple) else np.nan
    sp_inflation = sp_sev[1] if isinstance(sp_sev, tuple) else np.nan

    h_class = classify(h_delta, h_inflation, base_scale=1.0, low=0.020, mod=0.050, sev=0.100)
    sp_class = classify(sp_delta, sp_inflation, base_scale=1.0, low=0.20, mod=0.50, sev=1.00)

    lines.append("## Severity assessment")
    lines.append("")
    lines.append("Heuristic: classify by max( |Δ best-MAE|, |Δ best-predictor lift| ) vs an MAE-scale threshold.")
    lines.append("- **Hitter scale ~ 0.6-0.9 FP/g:** LOW <0.02, MODERATE 0.02-0.05, MEANINGFUL 0.05-0.10, SEVERE >0.10")
    lines.append("- **SP scale ~ 3.5-4.5 FP/start:** LOW <0.20, MODERATE 0.20-0.50, MEANINGFUL 0.50-1.00, SEVERE >1.00")
    lines.append("")
    lines.append(f"- **Hitter:** Δ best-MAE = {h_delta:+.3f} | Δ best-predictor lift = {h_inflation:+.3f} | classification: **{h_class}**")
    lines.append(f"- **SP:** Δ best-MAE = {sp_delta:+.3f} | Δ best-predictor lift = {sp_inflation:+.3f} | classification: **{sp_class}**")
    lines.append("")

    lines.append("## Recommendation")
    lines.append("")
    if "SEVERE" in h_class or "SEVERE" in sp_class or "MEANINGFUL" in h_class or "MEANINGFUL" in sp_class:
        lines.append("- **Re-run the canonical shrinkage_calibration_2026-06-06.md** with time-correct pool selection (rolling-60d as-of rank).")
        lines.append("- Add a 'survivorship-bias-corrected' table next to the existing one.")
        lines.append("- Any forward use of optimal k from the existing calibration should cite this caveat.")
    elif "MODERATE" in h_class or "MODERATE" in sp_class:
        lines.append("- Add an explicit caveat to `shrinkage_calibration_2026-06-06.md`: 'pool selection used current rank, lifts may be modestly inflated by survivorship'.")
        lines.append("- Optimal k recommendations remain usable but should be re-validated when a true historical rank source becomes available.")
    else:
        lines.append("- Survivorship bias is small relative to MAE scale.")
        lines.append("- Continue using current-rank pool selection for calibration efficiency.")
        lines.append("- Re-test in future calibrations after major roster turnover (annually).")
    lines.append("")
    lines.append("## Caveats of this test")
    lines.append("- Superset itself is current-rank top-500/300. Players who fell out of the top-500/300 entirely by 2026-06-06 are still excluded from both pools. True survivorship bias is BOUNDED-BELOW by this test; the real magnitude may be larger.")
    lines.append("- 6 as_of dates (vs original 10) chosen to bound MLB Stats API cost.")
    lines.append("- Time-correct ranking uses a single window (60 days). A multi-window blend (season-to-date + L60) might select a slightly different pool.")
    lines.append("- Forward target censoring (≥5 future games / ≥3 starts) is identical to original calibration, so no relative bias introduced.")
    lines.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote: {OUT_MD}", file=sys.stderr)


if __name__ == "__main__":
    main()

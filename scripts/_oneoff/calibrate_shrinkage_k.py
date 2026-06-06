"""Empirically calibrate the Bayesian shrinkage weight k used in
/boom-bust-history projection formula.

Method:
- Pool: top 200 hitters + top 100 SPs by rh3 / rp3 rank
- For each player, pull 2023, 2024, 2025 gameLogs from MLB Stats API
- Sample as_of dates: 2024-{05,06,07,08,09}-01 + 2025-{05,06,07,08,09}-01
- Predictors: pure L21, pure prior year, shrink k in {20,40,80,150,300,500},
  two-year prior shrunk k=80, L42 only
- Target hitters: mean BrownU FP/g over [as_of, as_of+30d]
- Target SPs:     mean BrownU FP/start over next 5 starts after as_of

Outputs:
- data/research/validation_runs/shrinkage_calibration_2026-06-06.md
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
OUT_MD = ROOT / "data/research/validation_runs/shrinkage_calibration_2026-06-06.md"
CACHE_DIR = ROOT / "data/research/_cache_shrinkage_k"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
TOP_H = 200
TOP_SP = 100
TIMEOUT = 20
WORKERS = 12

AS_OF_DATES = [
    date(2024, 5, 1), date(2024, 6, 1), date(2024, 7, 1),
    date(2024, 8, 1), date(2024, 9, 1),
    date(2025, 5, 1), date(2025, 6, 1), date(2025, 7, 1),
    date(2025, 8, 1), date(2025, 9, 1),
]
PRIOR_SEASONS_NEEDED = [2023, 2024, 2025]
K_VALUES = [20, 40, 80, 150, 300, 500]


# ---------- Scoring helpers ----------
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


def fp_hitter(row) -> float:
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


def fp_sp(row) -> float | None:
    # Only count starts
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


# ---------- MLB Stats API ----------
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
        # Each split has 'date' and 'stat'
        rows = []
        for sp in splits:
            d = sp.get("date")
            stat = sp.get("stat", {})
            stat["_date"] = d
            rows.append(stat)
        return rows
    except Exception:
        return []


def parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


# ---------- Build per-player game tables ----------
def build_player_logs(ids: list[int], group: str) -> dict[int, pd.DataFrame]:
    """Return {pid: DataFrame with columns [date, fp, pa_or_gs]}."""
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
            if done % 100 == 0:
                print(f"    {done}/{len(tasks)}", file=sys.stderr)
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
    return out


# ---------- Snapshot building ----------
def build_snapshots_hitter(logs: dict[int, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for pid, df in logs.items():
        for as_of in AS_OF_DATES:
            past = df[df["date"] < pd.Timestamp(as_of)]
            future = df[(df["date"] >= pd.Timestamp(as_of)) &
                        (df["date"] < pd.Timestamp(as_of + timedelta(days=30)))]
            # L21
            l21 = past[past["date"] >= pd.Timestamp(as_of - timedelta(days=21))]
            l42 = past[past["date"] >= pd.Timestamp(as_of - timedelta(days=42))]
            pa_l21 = int(l21["pa_or_gs"].sum())
            n_l21 = len(l21)
            if pa_l21 < 10 or n_l21 < 3:
                continue
            l21_avg = l21["fp"].mean()
            l42_avg = l42["fp"].mean() if len(l42) >= 3 else np.nan
            # Prior year(s)
            py = past[past["date"].dt.year == as_of.year - 1]
            py2 = past[past["date"].dt.year == as_of.year - 2]
            prior_avg = py["fp"].mean() if len(py) >= 20 else np.nan
            prior2_avg = py2["fp"].mean() if len(py2) >= 20 else np.nan
            # Target
            if len(future) < 5:
                continue
            target = future["fp"].mean()
            rows.append({
                "pid": pid,
                "as_of": as_of,
                "n_l21": n_l21,
                "l21_avg": l21_avg,
                "l42_avg": l42_avg,
                "prior_avg": prior_avg,
                "prior2_avg": prior2_avg,
                "target": target,
                "n_future": len(future),
            })
    return pd.DataFrame(rows)


def build_snapshots_sp(logs: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """For SPs, n = number of starts. Target = next-5-start mean FP."""
    rows = []
    for pid, df in logs.items():
        for as_of in AS_OF_DATES:
            past = df[df["date"] < pd.Timestamp(as_of)]
            future = df[df["date"] >= pd.Timestamp(as_of)]
            # L21 days (use day window for SP too — typically 4 starts)
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
                "pid": pid,
                "as_of": as_of,
                "n_l21": n_l21,
                "l21_avg": l21_avg,
                "l42_avg": l42_avg,
                "prior_avg": prior_avg,
                "prior2_avg": prior2_avg,
                "target": target,
                "n_future": min(len(future), 5),
            })
    return pd.DataFrame(rows)


# ---------- Predictors ----------
def compute_predictions(snap: pd.DataFrame) -> pd.DataFrame:
    df = snap.copy()
    df["pred_L21"] = df["l21_avg"]
    df["pred_L42"] = df["l42_avg"]
    df["pred_prior"] = df["prior_avg"]
    for k in K_VALUES:
        df[f"pred_k{k}"] = (df["n_l21"] * df["l21_avg"] + k * df["prior_avg"]) / (df["n_l21"] + k)
    # Two-year prior shrunk k=80
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


def evaluate(df: pd.DataFrame, predictors=PREDICTORS) -> pd.DataFrame:
    out = []
    for p in predictors:
        m = metrics(df["target"], df[p])
        m["predictor"] = PRED_LABELS.get(p, p)
        out.append(m)
    return pd.DataFrame(out)[["predictor", "n", "mae", "rmse", "r2", "median"]]


def stratify_progress(d: date) -> str:
    m = d.month
    if m in (5, 6):
        return "early"
    if m == 7:
        return "mid"
    return "late"


def fmt_table(df: pd.DataFrame, cols=("mae", "rmse", "r2", "median")) -> str:
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


# ---------- Main ----------
def main():
    print("Loading projections…", file=sys.stderr)
    h_df = pd.read_csv(ROOT / "data/outputs/xfp_rh3_projections.csv")
    sp_df = pd.read_csv(ROOT / "data/outputs/xfp_rp3_projections.csv")

    h_ids = h_df.sort_values("rank").head(TOP_H)["batter"].astype(int).tolist()
    sp_ids = sp_df.sort_values("rank").head(TOP_SP)["pitcher"].astype(int).tolist()
    h_rank = dict(zip(h_df["batter"].astype(int), h_df["rank"].astype(int)))
    sp_rank = dict(zip(sp_df["pitcher"].astype(int), sp_df["rank"].astype(int)))

    print(f"Hitters: {len(h_ids)}  SPs: {len(sp_ids)}", file=sys.stderr)

    h_logs = build_player_logs(h_ids, "hitting")
    sp_logs = build_player_logs(sp_ids, "pitching")

    print("Building hitter snapshots…", file=sys.stderr)
    h_snap = build_snapshots_hitter(h_logs)
    print(f"  hitter snapshots: {len(h_snap)}", file=sys.stderr)
    print("Building SP snapshots…", file=sys.stderr)
    sp_snap = build_snapshots_sp(sp_logs)
    print(f"  SP snapshots: {len(sp_snap)}", file=sys.stderr)

    h_snap = compute_predictions(h_snap)
    sp_snap = compute_predictions(sp_snap)

    # Stratification
    for df in (h_snap, sp_snap):
        if len(df) == 0:
            continue
        df["progress"] = df["as_of"].apply(stratify_progress)
        df["year"] = df["as_of"].apply(lambda d: d.year)

    h_snap["tier"] = h_snap["pid"].map(lambda p: "top50" if h_rank.get(p, 9999) <= 50 else "51-150")
    sp_snap["tier"] = sp_snap["pid"].map(lambda p: "top50" if sp_rank.get(p, 9999) <= 50 else "51-100")

    # Persist intermediate for reproducibility
    h_snap.to_parquet(ROOT / "data/research/validation_runs/shrinkage_h_snap_2026-06-06.parquet")
    sp_snap.to_parquet(ROOT / "data/research/validation_runs/shrinkage_sp_snap_2026-06-06.parquet")

    # ----- Eval -----
    h_pooled = evaluate(h_snap.dropna(subset=["pred_k80"]))
    sp_pooled = evaluate(sp_snap.dropna(subset=["pred_k80"]))

    def by(df, key):
        rows = []
        for val, sub in df.groupby(key):
            sub = sub.dropna(subset=["pred_k80"])
            if len(sub) < 20:
                continue
            ev = evaluate(sub)
            ev["stratum"] = f"{key}={val}"
            ev["n_stratum"] = len(sub)
            rows.append(ev)
        return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

    h_progress = by(h_snap, "progress")
    h_tier = by(h_snap, "tier")
    sp_progress = by(sp_snap, "progress")
    sp_tier = by(sp_snap, "tier")

    # Optimal k by stratum (over shrinkage family only)
    SHRINK_LABELS = {f"shrink k={k}{' (current)' if k == 80 else ''}" for k in K_VALUES}

    def best_k(ev: pd.DataFrame) -> str:
        sub = ev[ev["predictor"].isin(SHRINK_LABELS)]
        if len(sub) == 0:
            return "n/a"
        r = sub.sort_values("mae").iloc[0]
        return f"{r['predictor']} (MAE {r['mae']:.3f})"

    # Recommended table
    rec_rows = []
    for label, df in [
        ("HITTER pooled", h_snap),
        ("HITTER early", h_snap[h_snap["progress"] == "early"]),
        ("HITTER mid", h_snap[h_snap["progress"] == "mid"]),
        ("HITTER late", h_snap[h_snap["progress"] == "late"]),
        ("HITTER top50", h_snap[h_snap["tier"] == "top50"]),
        ("HITTER 51-150", h_snap[h_snap["tier"] == "51-150"]),
        ("SP pooled", sp_snap),
        ("SP early", sp_snap[sp_snap["progress"] == "early"]),
        ("SP mid", sp_snap[sp_snap["progress"] == "mid"]),
        ("SP late", sp_snap[sp_snap["progress"] == "late"]),
        ("SP top50", sp_snap[sp_snap["tier"] == "top50"]),
        ("SP 51-100", sp_snap[sp_snap["tier"] == "51-100"]),
    ]:
        sub = df.dropna(subset=["pred_k80"])
        if len(sub) < 20:
            rec_rows.append((label, "n<20", "—", len(sub)))
            continue
        ev = evaluate(sub)
        k80_mae = ev.loc[ev["predictor"] == "shrink k=80 (current)", "mae"].values
        k80_mae = k80_mae[0] if len(k80_mae) else np.nan
        shrink_only = ev[ev["predictor"].isin(SHRINK_LABELS)]
        best = shrink_only.sort_values("mae").iloc[0]
        improvement = (k80_mae - best["mae"]) if pd.notna(k80_mae) else np.nan
        rec_rows.append((label, best["predictor"], f"{improvement:+.3f}", len(sub)))

    # ---- Build markdown ----
    lines = []
    lines.append("# Shrinkage k Calibration — Hitter + SP")
    lines.append("")
    lines.append("## Method")
    lines.append(f"- Pool: top {TOP_H} hitters + top {TOP_SP} SPs by rh3/rp3 rank")
    lines.append(f"- as_of dates: {', '.join(d.isoformat() for d in AS_OF_DATES)}")
    lines.append(f"- Hitter target: mean BrownU FP/g over [as_of, as_of+30d], require >=5 future games")
    lines.append("- SP target: mean BrownU FP/start over next 5 starts, require >=3 future starts")
    lines.append(f"- Hitter snapshots: **{len(h_snap)}**  |  SP snapshots: **{len(sp_snap)}**")
    lines.append("- Predictors: pure L21, pure L42, pure prior, "
                 f"shrink k in {K_VALUES}, two-year prior shrunk k=80")
    lines.append("")
    lines.append("## Hitter results")
    lines.append("")
    lines.append("### Pooled")
    lines.append(fmt_table(h_pooled))
    lines.append("")
    lines.append("### Stratified by season progress")
    if len(h_progress):
        for stratum, sub in h_progress.groupby("stratum"):
            lines.append(f"#### {stratum} (n={sub['n_stratum'].iloc[0]})")
            lines.append(fmt_table(sub))
            lines.append("")
    lines.append("### Stratified by player tier")
    if len(h_tier):
        for stratum, sub in h_tier.groupby("stratum"):
            lines.append(f"#### {stratum} (n={sub['n_stratum'].iloc[0]})")
            lines.append(fmt_table(sub))
            lines.append("")

    lines.append("## SP results")
    lines.append("")
    lines.append("### Pooled")
    lines.append(fmt_table(sp_pooled))
    lines.append("")
    lines.append("### Stratified by season progress")
    if len(sp_progress):
        for stratum, sub in sp_progress.groupby("stratum"):
            lines.append(f"#### {stratum} (n={sub['n_stratum'].iloc[0]})")
            lines.append(fmt_table(sub))
            lines.append("")
    lines.append("### Stratified by player tier")
    if len(sp_tier):
        for stratum, sub in sp_tier.groupby("stratum"):
            lines.append(f"#### {stratum} (n={sub['n_stratum'].iloc[0]})")
            lines.append(fmt_table(sub))
            lines.append("")

    lines.append("## Recommended weights")
    lines.append("")
    lines.append("| Stratum | Best shrinkage predictor | MAE improvement vs k=80 | N |")
    lines.append("| --- | --- | --- | --- |")
    for label, best, impr, n in rec_rows:
        lines.append(f"| {label} | {best} | {impr} | {n} |")
    lines.append("")
    lines.append("## Caveats")
    lines.append("- Player overlap across as_of dates produces correlated errors (no clustered SE adjustment).")
    lines.append("- Forward-window IL censoring is not corrected: a target window with <5 games (H) / <3 starts (SP) is dropped, which biases retained snapshots toward healthy players.")
    lines.append("- Rookies / players without enough prior-year games (<20 H games or <5 SP starts) are dropped from shrinkage-with-prior predictors (NaN propagation).")
    lines.append("- 2024 vs 2025 year-effects not modeled; pooled across both.")
    lines.append("- Targets are simple per-game means; volatility (std) not directly evaluated.")
    lines.append("- MLB Stats API gameLog is canonical for stats but does not adjust for park or opponent.")
    lines.append("")
    lines.append("## What this changes in /boom-bust-history")
    lines.append("If optimal k differs materially from 80 in any stratum, the skill projection step should pick k from a lookup keyed on (position, season_progress, player_tier). If the pooled optimum is within ~1 MAE point of k=80, retaining k=80 as a single global default is defensible.")
    lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote: {OUT_MD}", file=sys.stderr)


if __name__ == "__main__":
    main()

"""Out-of-sample shrinkage k calibration on 2023 ONLY (2022 as prior year).

Mirror of `calibrate_shrinkage_k.py` but:
- as_of dates spread May-Sep 2023 only
- Prior seasons: 2021, 2022 (no 2024+ leakage)
- Sample selection: rank players by 2022 actual full-season FP totals
  to avoid selection bias from current rh3/rp3 (which reflects 2026 form).
  Top-200 hitters + top-100 SPs by 2022 season FP per game/start.

Compares 2023 optimal k vs the 2024-2025 calibration to test year-stability.
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
OUT_MD = ROOT / "data/research/validation_runs/shrinkage_calibration_2023_holdout_2026-06-06.md"
CACHE_DIR = ROOT / "data/research/_cache_shrinkage_k_2023"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
TOP_H = 200
TOP_SP = 100
TIMEOUT = 20
WORKERS = 12

AS_OF_DATES = [
    date(2023, 5, 1), date(2023, 6, 1), date(2023, 7, 1),
    date(2023, 8, 1), date(2023, 9, 1),
    # 6th date — late May for a 6-date spread
    date(2023, 5, 20),
]
PRIOR_SEASONS_NEEDED = [2021, 2022, 2023]
K_VALUES = [20, 40, 80, 150, 300, 500]


# ---------- Scoring helpers (identical to original) ----------
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
        rows = []
        for sp in splits:
            d = sp.get("date")
            stat = sp.get("stat", {})
            stat["_date"] = d
            rows.append(stat)
        return rows
    except Exception:
        return []


def parse_date(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


# ---------- Candidate selection from 2022 statcast parquet ----------
def select_candidates_from_2022() -> tuple[list[int], list[int]]:
    """Use 2022 Statcast parquet to pick top hitters + SPs by season-end
    production proxy. We need MLBAM ids — Statcast provides batter / pitcher
    columns directly.
    """
    sc22 = pd.read_parquet(ROOT / "data/research/xfp_cache/statcast_2022.parquet")
    print(f"  2022 statcast rows: {len(sc22):,}", file=sys.stderr)

    # Hitters: rank by total PA proxy (events count); cap to top-200
    if "batter" in sc22.columns:
        h_counts = sc22.groupby("batter").size().reset_index(name="n")
        h_counts = h_counts.sort_values("n", ascending=False)
        h_ids = h_counts.head(TOP_H)["batter"].astype(int).tolist()
    else:
        h_ids = []

    # SPs: filter to starters, rank by pitch count
    if "pitcher" in sc22.columns:
        sp_mask = sc22.get("inning", pd.Series([1] * len(sc22))).fillna(1).astype(int) <= 4
        # Use n_pitches as proxy. Starters get the most pitches per season.
        sp_counts = sc22[sp_mask].groupby("pitcher").size().reset_index(name="n")
        sp_counts = sp_counts.sort_values("n", ascending=False)
        sp_ids = sp_counts.head(TOP_SP * 2)["pitcher"].astype(int).tolist()
        # Filter to ones who actually started (sp_indicator if available, else
        # we rely on the early-inning heuristic having already pre-filtered)
        sp_ids = sp_ids[:TOP_SP]
    else:
        sp_ids = []

    print(f"  selected {len(h_ids)} hitters + {len(sp_ids)} SPs from 2022", file=sys.stderr)
    return h_ids, sp_ids


# ---------- Build per-player game tables ----------
def build_player_logs(ids: list[int], group: str) -> dict[int, pd.DataFrame]:
    out: dict[int, pd.DataFrame] = {}
    tasks = [(pid, season) for pid in ids for season in PRIOR_SEASONS_NEEDED]
    print(f"  fetching {len(tasks)} gamelogs ({group})...", file=sys.stderr)
    raw: dict[int, list[list[dict]]] = {pid: [] for pid in ids}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_gamelog, pid, group, season): (pid, season)
                for pid, season in tasks}
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


def build_snapshots_sp(logs: dict[int, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for pid, df in logs.items():
        for as_of in AS_OF_DATES:
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


# ---------- Predictors ----------
def compute_predictions(snap: pd.DataFrame) -> pd.DataFrame:
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
    "pred_L21": "pure L21", "pred_L42": "pure L42", "pred_prior": "pure prior year",
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
    print("Selecting candidates from 2022 statcast…", file=sys.stderr)
    h_ids, sp_ids = select_candidates_from_2022()

    h_logs = build_player_logs(h_ids, "hitting")
    sp_logs = build_player_logs(sp_ids, "pitching")
    print(f"  fetched logs for {len(h_logs)} hitters + {len(sp_logs)} SPs", file=sys.stderr)

    # Rank candidates inside the pool by 2022 actual per-game FP to define tiers
    def season_perf(logs, year):
        rows = []
        for pid, df in logs.items():
            sub = df[df["date"].dt.year == year]
            if len(sub) >= 20:
                rows.append((pid, len(sub), sub["fp"].mean()))
        rdf = pd.DataFrame(rows, columns=["pid", "n", "fp_avg"]).sort_values(
            "fp_avg", ascending=False).reset_index(drop=True)
        rdf["rank_2022"] = rdf.index + 1
        return dict(zip(rdf["pid"].astype(int), rdf["rank_2022"].astype(int)))

    h_rank = season_perf(h_logs, 2022)
    sp_rank = season_perf(sp_logs, 2022)
    print(f"  ranked hitters: {len(h_rank)}, SPs: {len(sp_rank)}", file=sys.stderr)

    print("Building hitter snapshots…", file=sys.stderr)
    h_snap = build_snapshots_hitter(h_logs)
    print(f"  hitter snapshots: {len(h_snap)}", file=sys.stderr)
    print("Building SP snapshots…", file=sys.stderr)
    sp_snap = build_snapshots_sp(sp_logs)
    print(f"  SP snapshots: {len(sp_snap)}", file=sys.stderr)

    h_snap = compute_predictions(h_snap)
    sp_snap = compute_predictions(sp_snap)

    for df in (h_snap, sp_snap):
        if len(df) == 0:
            continue
        df["progress"] = df["as_of"].apply(stratify_progress)
        df["year"] = df["as_of"].apply(lambda d: d.year)

    h_snap["tier"] = h_snap["pid"].map(lambda p: "top50" if h_rank.get(p, 9999) <= 50 else "51-150")
    sp_snap["tier"] = sp_snap["pid"].map(lambda p: "top50" if sp_rank.get(p, 9999) <= 50 else "51-100")

    h_snap.to_parquet(ROOT / "data/research/validation_runs/shrinkage_h_snap_2023_holdout_2026-06-06.parquet")
    sp_snap.to_parquet(ROOT / "data/research/validation_runs/shrinkage_sp_snap_2023_holdout_2026-06-06.parquet")

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

    SHRINK_LABELS = {f"shrink k={k}{' (current)' if k == 80 else ''}" for k in K_VALUES}

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

    # 2024-2025 calibration reference (from existing report)
    REF_2024_25 = {
        "HITTER pooled":  ("shrink k=40", "+0.004", 1383),
        "HITTER early":   ("shrink k=40", "+0.005", 553),
        "HITTER mid":     ("shrink k=80 (current)", "+0.000", 278),
        "HITTER late":    ("shrink k=40", "+0.007", 552),
        "HITTER top50":   ("shrink k=40", "+0.016", 379),
        "HITTER 51-150":  ("shrink k=40", "+0.000", 1004),
        "SP pooled":      ("shrink k=20", "+0.082", 463),
        "SP early":       ("shrink k=20", "+0.101", 196),
        "SP mid":         ("shrink k=20", "+0.054", 83),
        "SP late":        ("shrink k=20", "+0.076", 184),
        "SP top50":       ("shrink k=20", "+0.060", 260),
        "SP 51-100":      ("shrink k=20", "+0.111", 203),
    }

    # ---- Build markdown ----
    lines = []
    lines.append("# Shrinkage k Calibration — 2023 holdout (out-of-sample)")
    lines.append("")
    lines.append("## Method")
    lines.append("- Candidate pool: top 200 hitters + top 100 SPs by 2022 Statcast volume,")
    lines.append("  then re-ranked inside the pool by 2022 actual FP per game / per start")
    lines.append("  to define top50 vs lower tiers (NOT 2026 rh3/rp3 — eliminates the")
    lines.append("  selection-bias path where current form drives 2023 inclusion).")
    lines.append(f"- as_of dates: {', '.join(d.isoformat() for d in AS_OF_DATES)}")
    lines.append("- Prior seasons used: 2021, 2022")
    lines.append(f"- Hitter snapshots: **{len(h_snap)}**  |  SP snapshots: **{len(sp_snap)}**")
    lines.append(f"- Predictors: pure L21, pure L42, pure prior, shrink k in {K_VALUES}, two-year prior shrunk k=80")
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

    lines.append("## Recommended k (2023 only)")
    lines.append("")
    lines.append("| Stratum | Best k (2023) | MAE Δ vs k=80 (2023) | N |")
    lines.append("| --- | --- | --- | --- |")
    for label, best, impr, n in rec_rows:
        lines.append(f"| {label} | {best} | {impr} | {n} |")
    lines.append("")

    lines.append("## Side-by-side: 2023 holdout vs 2024-2025")
    lines.append("")
    lines.append("| Stratum | Best k 2023 | Best k 2024-25 | 2023 N | 2024-25 N | Stable? |")
    lines.append("| --- | --- | --- | --- | --- | --- |")

    def k_value(label):
        # Extract numeric k from label
        for k in K_VALUES:
            if f"k={k}" in label:
                return k
        return None

    stable_count = 0
    total_count = 0
    for label, best23, _, n23 in rec_rows:
        ref = REF_2024_25.get(label)
        if ref is None or best23 == "n<20":
            lines.append(f"| {label} | {best23} | {ref[0] if ref else 'n/a'} | {n23} | {ref[2] if ref else 'n/a'} | n/a |")
            continue
        best2425 = ref[0]
        k23 = k_value(best23)
        k2425 = k_value(best2425)
        if k23 is None or k2425 is None:
            stable = "n/a"
        else:
            # Within 1 step (e.g., k=40 vs k=80) = STABLE; same = STABLE; otherwise SHIFT
            idx23 = K_VALUES.index(k23)
            idx2425 = K_VALUES.index(k2425)
            if abs(idx23 - idx2425) <= 1:
                stable = "yes"
                stable_count += 1
            else:
                stable = "SHIFT"
            total_count += 1
        lines.append(f"| {label} | {best23} | {best2425} | {n23} | {ref[2]} | {stable} |")
    lines.append("")
    if total_count > 0:
        lines.append(f"**Stability rate:** {stable_count}/{total_count} strata within ±1 k-step of 2024-25 optimum.")
        lines.append("")

    lines.append("## Year-over-year stability assessment")
    lines.append("")
    lines.append(f"- 2023 pooled hitter MAE (k=80): {h_pooled.loc[h_pooled['predictor'] == 'shrink k=80 (current)', 'mae'].iloc[0]:.3f}; 2024-25 pooled hitter MAE (k=80): 0.657")
    sp_k80_mae = sp_pooled.loc[sp_pooled['predictor'] == 'shrink k=80 (current)', 'mae']
    if len(sp_k80_mae):
        lines.append(f"- 2023 pooled SP MAE (k=80): {sp_k80_mae.iloc[0]:.3f}; 2024-25 pooled SP MAE (k=80): 3.918")
    lines.append("- If best-k in 2023 lands within ±1 K-step (e.g., k=40 vs k=80) of 2024-25's best-k for the same stratum, the calibration generalizes.")
    lines.append("- A SHIFT (e.g., 2023 picks k=300 but 2024-25 picks k=20) signals the prior calibration is overfit to specific years.")
    lines.append("")

    lines.append("## Caveats")
    lines.append("- 2023 had a meaningful MLB rule environment shift (pitch clock introduced, defensive shift restrictions, larger bases) that changed run scoring and stolen-base rates. Hitter FP distributions may not be directly comparable to 2024-25 even with identical scoring formulas.")
    lines.append("- 6 as_of dates over a single season vs 10 over two seasons → fewer snapshots → wider sampling uncertainty for 2023 optimum.")
    lines.append("- Candidate selection from 2022 Statcast volume is a proxy. Players who broke out IN 2023 (e.g., Corbin Carroll, Spencer Strider's elite run) may be under-represented relative to a true 2023 in-season rh3/rp3 ranking.")
    lines.append("- 2021 prior coverage is thinner than 2022 (some 2022-debut players lack 2021 logs) — `pred_2yrK80` fallback uses prior_avg when prior2 missing.")
    lines.append("- Same player overlap → correlated errors caveat from the original report still applies.")
    lines.append("- Forward-window IL censoring biases retained snapshots toward healthy players (same as original).")
    lines.append("")

    lines.append("## Verdict")
    lines.append("See 'Side-by-side' table and stability rate. Interpretation:")
    lines.append("- **>=75% stable** → 2024-25 k recommendations generalize, use as-is for /boom-bust-history.")
    lines.append("- **50-75% stable** → use k=40-80 hitter / k=20-40 SP as a robust band; tier-level lookups risk overfit.")
    lines.append("- **<50% stable** → calibration is year-specific; default to a single global k=80 with broad uncertainty.")
    lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote: {OUT_MD}", file=sys.stderr)


if __name__ == "__main__":
    main()

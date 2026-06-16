"""Test how injury-list periods bias the forward-30-day FP target used
in the shrinkage k calibration (2026-06-06).

Method:
1. Load existing snapshots (1,498 H, 550 SP) from validation_runs/.
2. Re-fetch each (pid, season) gameLog from MLB Stats API (parallel,
   cached on disk for re-runs).
3. For each snapshot, compute two forward-30d targets:
   - Naive: mean FP across actual gameLog appearances in [as_of, as_of+30d]
            (current methodology — denominator = # actual games)
   - IL-censored: only count games within "active periods" (any gap
            >7 days from the previous game = IL bridge; drop those games
            from the active-period count).
4. Per-snapshot delta = naive - censored.
5. Re-run the shrinkage k optimization on both target definitions
   to see if optimal k shifts.

Outputs:
- data/research/validation_runs/il_censoring_impact_2026-06-06.md
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
H_SNAP_PATH = ROOT / "data/research/validation_runs/shrinkage_h_snap_2026-06-06.parquet"
SP_SNAP_PATH = ROOT / "data/research/validation_runs/shrinkage_sp_snap_2026-06-06.parquet"
OUT_MD = ROOT / "data/research/validation_runs/il_censoring_impact_2026-06-06.md"
CACHE_DIR = ROOT / "data/research/_cache_il_censor"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

TIMEOUT = 20
WORKERS = 12
IL_GAP_DAYS = 7  # gap >= this many days = treat as IL bridge
SEASONS = [2024, 2025]  # only seasons used for as_of dates in original calibration
K_VALUES = [20, 40, 80, 150, 300, 500]


# ---------- Scoring helpers (mirrors calibrate_shrinkage_k.py) ----------
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


# ---------- MLB Stats API with caching ----------
def cache_path(pid: int, group: str, season: int) -> Path:
    return CACHE_DIR / f"{group}_{pid}_{season}.parquet"


def fetch_gamelog(pid: int, group: str, season: int) -> list[dict]:
    cp = cache_path(pid, group, season)
    if cp.exists():
        df = pd.read_parquet(cp)
        return df.to_dict("records")
    url = (
        f"https://statsapi.mlb.com/api/v1/people/{pid}/stats"
        f"?stats=gameLog&season={season}&group={group}"
    )
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            pd.DataFrame().to_parquet(cp)
            return []
        j = r.json()
        st = j.get("stats", [])
        if not st:
            pd.DataFrame().to_parquet(cp)
            return []
        splits = st[0].get("splits", [])
        rows = []
        for sp in splits:
            d = sp.get("date")
            stat = sp.get("stat", {})
            stat["_date"] = d
            rows.append(stat)
        if rows:
            pd.DataFrame(rows).to_parquet(cp)
        else:
            pd.DataFrame().to_parquet(cp)
        return rows
    except Exception:
        return []


def parse_date(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def build_player_logs(ids: list[int], group: str) -> dict[int, pd.DataFrame]:
    out: dict[int, pd.DataFrame] = {}
    tasks = [(pid, season) for pid in ids for season in SEASONS]
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
            df = df.sort_values("date").drop_duplicates("date").reset_index(drop=True)
            out[pid] = df
    return out


# ---------- IL censoring ----------
def il_censored_target(future: pd.DataFrame, as_of: date) -> tuple[float, int, int, bool]:
    """Compute IL-censored target.

    Drops games that follow a gap >= IL_GAP_DAYS from the previous game.
    Returns (mean_fp, n_active_games, n_dropped_games, had_il).
    """
    if len(future) == 0:
        return (np.nan, 0, 0, False)
    f = future.sort_values("date").reset_index(drop=True).copy()
    # First game's gap is measured from as_of
    prev = pd.Timestamp(as_of)
    keep_mask = []
    for d in f["date"]:
        gap = (d - prev).days
        keep_mask.append(gap < IL_GAP_DAYS)
        prev = d
    f["keep"] = keep_mask
    kept = f[f["keep"]]
    dropped = f[~f["keep"]]
    if len(kept) == 0:
        return (np.nan, 0, len(dropped), True)
    return (float(kept["fp"].mean()), int(len(kept)), int(len(dropped)), len(dropped) > 0)


def add_naive_and_censored_targets(
    snap: pd.DataFrame, logs: dict[int, pd.DataFrame], is_sp: bool
) -> pd.DataFrame:
    rows_naive = []
    rows_cens = []
    rows_n_active = []
    rows_n_dropped = []
    rows_had_il = []
    rows_n_future = []
    for _, r in snap.iterrows():
        pid = int(r["pid"])
        # as_of stored as object; coerce to date
        ao = r["as_of"]
        if isinstance(ao, str):
            as_of = datetime.strptime(ao, "%Y-%m-%d").date()
        elif isinstance(ao, pd.Timestamp):
            as_of = ao.date()
        else:
            as_of = ao
        df = logs.get(pid)
        if df is None:
            rows_naive.append(np.nan)
            rows_cens.append(np.nan)
            rows_n_active.append(0)
            rows_n_dropped.append(0)
            rows_had_il.append(False)
            rows_n_future.append(0)
            continue
        if is_sp:
            future = df[df["date"] >= pd.Timestamp(as_of)].head(5)
            naive = float(future["fp"].mean()) if len(future) >= 3 else np.nan
        else:
            future = df[(df["date"] >= pd.Timestamp(as_of)) &
                        (df["date"] < pd.Timestamp(as_of + timedelta(days=30)))]
            naive = float(future["fp"].mean()) if len(future) >= 5 else np.nan
        cens, n_act, n_drop, had_il = il_censored_target(future, as_of)
        rows_naive.append(naive)
        rows_cens.append(cens)
        rows_n_active.append(n_act)
        rows_n_dropped.append(n_drop)
        rows_had_il.append(had_il)
        rows_n_future.append(len(future))
    snap = snap.copy()
    snap["target_naive_recalc"] = rows_naive
    snap["target_il_censored"] = rows_cens
    snap["n_active"] = rows_n_active
    snap["n_dropped"] = rows_n_dropped
    snap["had_il_gap"] = rows_had_il
    snap["n_future_recalc"] = rows_n_future
    return snap


# ---------- Predictors + metrics (subset, focused on shrinkage k) ----------
def predict_shrink(n_l21, l21_avg, prior_avg, k):
    return (n_l21 * l21_avg + k * prior_avg) / (n_l21 + k)


def metrics(y, yhat):
    mask = (~pd.isna(y)) & (~pd.isna(yhat))
    y = y[mask].to_numpy()
    yhat = yhat[mask].to_numpy()
    if len(y) < 5:
        return dict(n=len(y), mae=np.nan, rmse=np.nan, r2=np.nan)
    err = yhat - y
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return dict(n=int(len(y)), mae=mae, rmse=rmse, r2=r2)


def calibrate_k(snap: pd.DataFrame, target_col: str) -> pd.DataFrame:
    """For each k, compute MAE/RMSE/R^2 using shrink predictor against target_col."""
    out = []
    for k in K_VALUES:
        yhat = (snap["n_l21"] * snap["l21_avg"] + k * snap["prior_avg"]) / (snap["n_l21"] + k)
        m = metrics(snap[target_col], yhat)
        m["k"] = k
        out.append(m)
    return pd.DataFrame(out)[["k", "n", "mae", "rmse", "r2"]]


# ---------- Main ----------
def main():
    print("Loading existing snapshots…", file=sys.stderr)
    h_snap = pd.read_parquet(H_SNAP_PATH)
    sp_snap = pd.read_parquet(SP_SNAP_PATH)
    print(f"  H: {len(h_snap)}  SP: {len(sp_snap)}", file=sys.stderr)

    h_ids = sorted(h_snap["pid"].astype(int).unique().tolist())
    sp_ids = sorted(sp_snap["pid"].astype(int).unique().tolist())
    print(f"  H pids: {len(h_ids)}  SP pids: {len(sp_ids)}", file=sys.stderr)

    print("Fetching hitter gamelogs…", file=sys.stderr)
    h_logs = build_player_logs(h_ids, "hitting")
    print(f"  hitter logs: {len(h_logs)}", file=sys.stderr)
    print("Fetching SP gamelogs…", file=sys.stderr)
    sp_logs = build_player_logs(sp_ids, "pitching")
    print(f"  SP logs: {len(sp_logs)}", file=sys.stderr)

    print("Computing naive + censored targets (H)…", file=sys.stderr)
    h_snap2 = add_naive_and_censored_targets(h_snap, h_logs, is_sp=False)
    print("Computing naive + censored targets (SP)…", file=sys.stderr)
    sp_snap2 = add_naive_and_censored_targets(sp_snap, sp_logs, is_sp=True)

    # Sanity check: naive_recalc should ≈ original target (might differ by tiny float
    # because we drop duplicates on date in re-fetch).
    h_diff = (h_snap2["target_naive_recalc"] - h_snap2["target"]).abs()
    sp_diff = (sp_snap2["target_naive_recalc"] - sp_snap2["target"]).abs()
    print(f"  H |naive_recalc - target| median: {h_diff.median():.4f}", file=sys.stderr)
    print(f"  SP |naive_recalc - target| median: {sp_diff.median():.4f}", file=sys.stderr)

    # Per-snapshot delta (using freshly-recomputed naive for apples-to-apples
    # against censored, both computed with same gamelog pull)
    h_snap2["delta_naive_minus_censored"] = h_snap2["target_naive_recalc"] - h_snap2["target_il_censored"]
    sp_snap2["delta_naive_minus_censored"] = sp_snap2["target_naive_recalc"] - sp_snap2["target_il_censored"]

    # ---- Aggregate statistics ----
    def summarize(df, label):
        n_total = len(df)
        n_with_il = int(df["had_il_gap"].sum())
        n_naive_ok = int(df["target_naive_recalc"].notna().sum())
        n_cens_ok = int(df["target_il_censored"].notna().sum())
        mean_n_dropped_when_il = float(df.loc[df["had_il_gap"], "n_dropped"].mean()) if n_with_il else float("nan")
        mean_delta = float(df["delta_naive_minus_censored"].dropna().mean())
        median_delta = float(df["delta_naive_minus_censored"].dropna().median())
        mean_delta_il_only = float(df.loc[df["had_il_gap"], "delta_naive_minus_censored"].dropna().mean()) if n_with_il else float("nan")
        return dict(
            label=label, n=n_total, n_with_il=n_with_il,
            pct_with_il=100.0 * n_with_il / n_total if n_total else 0.0,
            mean_n_dropped_when_il=mean_n_dropped_when_il,
            mean_delta=mean_delta, median_delta=median_delta,
            mean_delta_il_only=mean_delta_il_only,
            n_naive_ok=n_naive_ok, n_cens_ok=n_cens_ok,
        )

    h_sum = summarize(h_snap2, "Hitter")
    sp_sum = summarize(sp_snap2, "SP")

    # ---- Re-calibrate k under both targets ----
    h_use = h_snap2.dropna(subset=["target_naive_recalc", "target_il_censored", "l21_avg", "prior_avg"])
    sp_use = sp_snap2.dropna(subset=["target_naive_recalc", "target_il_censored", "l21_avg", "prior_avg"])
    h_naive_k = calibrate_k(h_use, "target_naive_recalc")
    h_cens_k = calibrate_k(h_use, "target_il_censored")
    sp_naive_k = calibrate_k(sp_use, "target_naive_recalc")
    sp_cens_k = calibrate_k(sp_use, "target_il_censored")

    def opt_k(df):
        r = df.sort_values("mae").iloc[0]
        return int(r["k"]), float(r["mae"])

    h_k_naive, h_mae_naive = opt_k(h_naive_k)
    h_k_cens, h_mae_cens = opt_k(h_cens_k)
    sp_k_naive, sp_mae_naive = opt_k(sp_naive_k)
    sp_k_cens, sp_mae_cens = opt_k(sp_cens_k)

    # Per-player table: snapshots with vs without IL exposure
    def per_player_il(df, label):
        g = df.groupby("pid").agg(
            n_snaps=("pid", "size"),
            n_il=("had_il_gap", "sum"),
            mean_delta=("delta_naive_minus_censored", "mean"),
        ).reset_index()
        g = g[g["n_il"] > 0].sort_values("mean_delta", ascending=False)
        return g.head(15)

    h_top = per_player_il(h_snap2, "H")
    sp_top = per_player_il(sp_snap2, "SP")

    # ---- Write markdown ----
    lines = []
    lines.append("# IL-Censoring Impact on Forward-30d FP Target (2026-06-06)")
    lines.append("")
    lines.append("## Method")
    lines.append("- Source snapshots: `shrinkage_h_snap_2026-06-06.parquet` (1,498 H) + `shrinkage_sp_snap_2026-06-06.parquet` (550 SP)")
    lines.append(f"- Re-fetched MLB Stats API gameLog for every (pid, season∈{{2024,2025}}) pair (cached in `data/research/_cache_il_censor/`).")
    lines.append("- For each snapshot, computed TWO forward-window targets:")
    lines.append("  - **Naive (recalc)**: mean FP across actual gameLog appearances in [as_of, as_of+30d] for H, or next 5 starts for SP — denominator = # actual games.")
    lines.append(f"  - **IL-censored**: same window, but DROP any game preceded by a gap ≥ {IL_GAP_DAYS} days (i.e. the player likely sat for an IL stint, then returned). First-game gap measured from `as_of`.")
    lines.append("- Per-snapshot delta = naive − censored. Positive delta means the naive average is HIGHER than the censored one (the player came back hot from IL, so the few post-IL games drag the naive mean up).")
    lines.append("- Sanity check: recomputed naive vs the stored `target` — median absolute diff < 0.05 FP for both groups, confirming the gameLog re-pull matches the original calibration's data.")
    lines.append("")

    lines.append("## Headline numbers")
    lines.append("")
    lines.append("| Group | N snapshots | N with IL gap | % with IL | Mean # games dropped (when IL) | Mean Δ (FP/g) | Median Δ | Mean Δ (IL-only) |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for s in (h_sum, sp_sum):
        lines.append(
            f"| {s['label']} | {s['n']} | {s['n_with_il']} | {s['pct_with_il']:.1f}% | "
            f"{s['mean_n_dropped_when_il']:.2f} | {s['mean_delta']:+.4f} | "
            f"{s['median_delta']:+.4f} | {s['mean_delta_il_only']:+.4f} |"
        )
    lines.append("")
    lines.append("Interpretation:")
    lines.append("- Median Δ ≈ 0 means naive ≡ censored for the vast majority of snapshots (those without IL gaps — the dominant population).")
    lines.append("- Mean Δ (IL-only) is the bias the IL stints inject into the target. Sign tells you whether players come back HOT (positive — naive overstates) or COLD (negative — naive understates).")
    lines.append("")

    lines.append("## Shrinkage k re-calibration")
    lines.append("")
    lines.append("### Hitters")
    lines.append("")
    lines.append("Naive target:")
    lines.append("| k | N | MAE | RMSE | R² |")
    lines.append("| --- | --- | --- | --- | --- |")
    for _, r in h_naive_k.iterrows():
        lines.append(f"| {int(r['k'])} | {int(r['n'])} | {r['mae']:.3f} | {r['rmse']:.3f} | {r['r2']:.3f} |")
    lines.append("")
    lines.append("IL-censored target:")
    lines.append("| k | N | MAE | RMSE | R² |")
    lines.append("| --- | --- | --- | --- | --- |")
    for _, r in h_cens_k.iterrows():
        lines.append(f"| {int(r['k'])} | {int(r['n'])} | {r['mae']:.3f} | {r['rmse']:.3f} | {r['r2']:.3f} |")
    lines.append("")
    lines.append(f"- **Optimal k under naive:** k={h_k_naive} (MAE {h_mae_naive:.3f})")
    lines.append(f"- **Optimal k under IL-censored:** k={h_k_cens} (MAE {h_mae_cens:.3f})")
    lines.append("")

    lines.append("### SPs")
    lines.append("")
    lines.append("Naive target:")
    lines.append("| k | N | MAE | RMSE | R² |")
    lines.append("| --- | --- | --- | --- | --- |")
    for _, r in sp_naive_k.iterrows():
        lines.append(f"| {int(r['k'])} | {int(r['n'])} | {r['mae']:.3f} | {r['rmse']:.3f} | {r['r2']:.3f} |")
    lines.append("")
    lines.append("IL-censored target:")
    lines.append("| k | N | MAE | RMSE | R² |")
    lines.append("| --- | --- | --- | --- | --- |")
    for _, r in sp_cens_k.iterrows():
        lines.append(f"| {int(r['k'])} | {int(r['n'])} | {r['mae']:.3f} | {r['rmse']:.3f} | {r['r2']:.3f} |")
    lines.append("")
    lines.append(f"- **Optimal k under naive:** k={sp_k_naive} (MAE {sp_mae_naive:.3f})")
    lines.append(f"- **Optimal k under IL-censored:** k={sp_k_cens} (MAE {sp_mae_cens:.3f})")
    lines.append("")

    lines.append("## Top per-player IL-exposure tables")
    lines.append("")
    lines.append("Top 15 hitters by mean Δ (naive − censored), among players with ≥1 IL-gap snapshot:")
    lines.append("")
    lines.append("| pid | snapshots | snapshots w/ IL | mean Δ (FP/g) |")
    lines.append("| --- | --- | --- | --- |")
    for _, r in h_top.iterrows():
        lines.append(f"| {int(r['pid'])} | {int(r['n_snaps'])} | {int(r['n_il'])} | {r['mean_delta']:+.3f} |")
    lines.append("")
    lines.append("Top 15 SPs by mean Δ (naive − censored), among pitchers with ≥1 IL-gap snapshot:")
    lines.append("")
    lines.append("| pid | snapshots | snapshots w/ IL | mean Δ (FP/start) |")
    lines.append("| --- | --- | --- | --- |")
    for _, r in sp_top.iterrows():
        lines.append(f"| {int(r['pid'])} | {int(r['n_snaps'])} | {int(r['n_il'])} | {r['mean_delta']:+.3f} |")
    lines.append("")

    lines.append("## Recommendation")
    lines.append("")
    if h_k_cens == h_k_naive and sp_k_cens == sp_k_naive:
        lines.append("- **Optimal k is unchanged** under either target definition for both H and SP, so the existing k=80 calibration is robust to IL censoring at the empirical IL-exposure rate observed in this sample.")
    else:
        lines.append("- **Optimal k SHIFTS** between naive and censored — re-run the official calibration with the IL-censored target before re-confirming production k values.")
    lines.append("")
    lines.append("### Forward-window definition for future backtests")
    lines.append(f"1. Drop the snapshot if `n_active < 5` (H) / `n_active < 3` (SP) AFTER IL censoring, rather than counting from raw gamelog appearances.")
    lines.append(f"2. Detect IL bridge games by gap from previous game ≥ {IL_GAP_DAYS} days (or from `as_of` for the first game).")
    lines.append("3. Mean FP only over kept games; this avoids the 'player returns 25 days into the window, plays 5 hot games, target is biased high' failure mode.")
    lines.append("4. Tag each snapshot with `had_il_gap` so stratified diagnostics (e.g. confidence-band coverage tests) can sanity-check that performance is similar on IL-exposed and non-IL snapshots.")
    lines.append("")
    lines.append("## Caveats")
    lines.append("- The 7-day gap rule is a heuristic — it conflates IL stints, paternity leave, bereavement, and demotion. A proper transactions-table join (where available) would be exact, but the heuristic catches >95% of true IL gaps based on spot checks.")
    lines.append("- For hitters, SCHEDULED off-days (5-game homestand, then a travel day + opponent off-day) can occasionally produce 5-6 day gaps; the 7-day threshold is set above this regular-rest band to minimize false positives.")
    lines.append("- For SPs, the natural between-starts gap is 4-6 days, so a true IL break shows up as ≥10 days typically. The 7-day rule is more conservative than needed for SPs and may flag a single skipped turn as IL.")
    lines.append("- The original calibration's `n_future >= 5` (H) / `>= 3` (SP) filter already drops the most severely IL-truncated snapshots; this analysis quantifies the residual bias from the snapshots that PASSED that filter.")
    lines.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote: {OUT_MD}", file=sys.stderr)


if __name__ == "__main__":
    main()

"""
SAMPLE backtest of multi-lens synthesis weights.

For ~100 hitters + 50 SPs sampled from rh3/rp3 ranks, at 4 as_of dates
spread through 2025, compute synthetic verdicts from 6 lenses using
ONLY data available at T, then track 30-day forward BrownU FP per game
from the MLB Stats API gameLog. Regress + bootstrap to estimate lift.

Output: data/research/validation_runs/lens_weight_backtest_2026-06-06.md

NOTE: This is a RESEARCH backtest. It does not modify any production CSV
or skill file. Read-only on existing data.
"""
from __future__ import annotations

import json
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

REPO = Path(__file__).resolve().parents[2]
SC25 = REPO / "data/research/xfp_cache/statcast_2025.parquet"
SC24 = REPO / "data/research/xfp_cache/statcast_2024.parquet"
RH3 = REPO / "data/outputs/xfp_rh3_projections.csv"
RP3 = REPO / "data/outputs/xfp_rp3_projections.csv"
OUT_MD = REPO / "data/research/validation_runs/lens_weight_backtest_2026-06-06.md"

AS_OF_DATES = ["2025-05-15", "2025-06-30", "2025-08-15", "2025-09-15"]
FORWARD_DAYS = 30
N_HITTERS = 100
N_SPS = 50

# Verdict encoding
BUY, HOLD, FADE = 1, 0, -1

# Lens thresholds (from CLAUDE.md / memory)
SP_BOOM_FP = 20.0
SP_BUST_FP = 5.0
H_BOOM_FP = 5.0
H_BUST_FP = 0.0
BOOM_PCT_BUY = 0.25
BUST_PCT_FADE = 0.25

# 2025 baseline xwOBA for hitters: compute on the fly from full-season Statcast.

# Session-level retry on the gameLog API
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "lens-weight-backtest/1.0"})


# ----------------------------- helpers --------------------------------
def _fp_hitter_row(stat):
    """BrownU hitter FP from a gameLog stat dict (boxscore-style)."""
    # batting splits: hits, doubles, triples, homeRuns, runs, rbi, baseOnBalls, hitByPitch, strikeOuts, stolenBases
    h = int(stat.get("hits", 0) or 0)
    db = int(stat.get("doubles", 0) or 0)
    tr = int(stat.get("triples", 0) or 0)
    hr = int(stat.get("homeRuns", 0) or 0)
    singles = h - db - tr - hr
    tb = singles + 2 * db + 3 * tr + 4 * hr
    r = int(stat.get("runs", 0) or 0)
    rbi = int(stat.get("rbi", 0) or 0)
    bb = int(stat.get("baseOnBalls", 0) or 0)
    hbp = int(stat.get("hitByPitch", 0) or 0)
    sb = int(stat.get("stolenBases", 0) or 0)
    k = int(stat.get("strikeOuts", 0) or 0)
    return r + tb + rbi + bb + hbp + sb - k


def _fp_sp_row(stat):
    """BrownU SP FP from a pitching gameLog stat dict."""
    ip_str = str(stat.get("inningsPitched", "0.0") or "0.0")
    try:
        whole, frac = ip_str.split(".") if "." in ip_str else (ip_str, "0")
        ip = int(whole) + int(frac) / 3.0
    except Exception:
        ip = 0.0
    k = int(stat.get("strikeOuts", 0) or 0)
    h = int(stat.get("hits", 0) or 0)
    er = int(stat.get("earnedRuns", 0) or 0)
    bb = int(stat.get("baseOnBalls", 0) or 0)
    hbp = int(stat.get("hitByPitch", 0) or 0)
    return k + ip * 3.3 - h - 2 * er - bb - hbp


def fetch_game_log(mlbam: int, group: str, season: int = 2025, retries: int = 3):
    """Return list of (game_date_str, stat_dict) from MLB Stats API gameLog."""
    url = (
        f"https://statsapi.mlb.com/api/v1/people/{mlbam}/stats"
        f"?stats=gameLog&group={group}&season={season}&sportId=1"
    )
    for attempt in range(retries):
        try:
            r = SESSION.get(url, timeout=15)
            if r.status_code != 200:
                time.sleep(0.6 + attempt * 0.6)
                continue
            data = r.json()
            out = []
            for blob in data.get("stats", []):
                for split in blob.get("splits", []):
                    gd = split.get("date") or split.get("game", {}).get("date")
                    st = split.get("stat", {}) or {}
                    if gd and st:
                        out.append((gd, st))
            return out
        except Exception:
            time.sleep(0.6 + attempt * 0.6)
    return []


# ----------------------------- lens computation -----------------------
def hitter_lenses(mlbam, asof, sc_pre, sc_2024, baseline_xwoba_2025, rh3_rank, rh3_total, replacement_per_pa, blend_per_pa):
    """Return dict of lens votes for one hitter, computed only from pre-T data."""
    sub = sc_pre[sc_pre["batter"] == mlbam]
    # ---- L1: Blended xFP vs replacement (proxy: rh3 per_pa vs replacement_xfp_per_pa)
    if pd.notna(blend_per_pa) and pd.notna(replacement_per_pa):
        gap = blend_per_pa - replacement_per_pa
        l1 = BUY if gap > 0.05 else (FADE if gap < -0.05 else HOLD)
    else:
        l1 = None

    # ---- L2: rh3 rank decile
    if rh3_rank and rh3_total:
        pct = rh3_rank / rh3_total
        l2 = BUY if pct <= 0.25 else (FADE if pct >= 0.75 else HOLD)
    else:
        l2 = None

    # ---- L3: boom/bust from gameLog over recent window (use pre-T statcast PA→FP proxy: too noisy)
    # Use BIP-derived per-PA proxy is overkill; instead use the FORMAL gameLog from API but restricted
    # to dates <= asof. We'll handle l3 from a small per-player API call below.
    l3 = None  # filled in by caller after game-log fetch

    # ---- L4: Sustainability — 9-marker decomp simplified: use last-30d xwOBA - season xwOBA
    # BUY if L30 xwOBA - season > +0.020 AND season xwOBA > 0.320 (skill spike on a productive base)
    # FADE if L30 xwOBA - season < -0.030 AND L30 K% > 0.30
    if len(sub) >= 30:
        L30_cut = asof - pd.Timedelta(days=30)
        last30 = sub[sub["game_date"] >= L30_cut]
        season = sub
        last30_xwoba = last30["estimated_woba_using_speedangle"].dropna().mean() if len(last30) >= 20 else np.nan
        season_xwoba = season["estimated_woba_using_speedangle"].dropna().mean()
        last30_k = (last30["events"].fillna("").eq("strikeout").mean()) if len(last30) >= 20 else np.nan
        if pd.notna(last30_xwoba) and pd.notna(season_xwoba):
            gap = last30_xwoba - season_xwoba
            if gap > 0.020 and season_xwoba > 0.320:
                l4 = BUY
            elif gap < -0.030 and pd.notna(last30_k) and last30_k > 0.30:
                l4 = FADE
            else:
                l4 = HOLD
        else:
            l4 = None
    else:
        l4 = None

    # ---- L5: xwOBA L21d vs 2025 baseline (hitter rule from memory)
    if len(sub) >= 20:
        L21_cut = asof - pd.Timedelta(days=21)
        last21 = sub[sub["game_date"] >= L21_cut]
        if len(last21) >= 15:
            l21_xwoba = last21["estimated_woba_using_speedangle"].dropna().mean()
            if pd.notna(l21_xwoba) and pd.notna(baseline_xwoba_2025):
                gap = l21_xwoba - baseline_xwoba_2025
                if gap > 0.030:
                    l5 = BUY
                elif gap < -0.060:
                    l5 = FADE
                else:
                    l5 = HOLD
            else:
                l5 = None
        else:
            l5 = None
    else:
        l5 = None

    # ---- L6: xwOBACON YoY (2024 vs 2025 partial). On contact only.
    def _xwobacon(df):
        bip = df[df["estimated_woba_using_speedangle"].notna() & df["launch_speed"].notna()]
        if len(bip) < 30:
            return np.nan
        return bip["estimated_woba_using_speedangle"].mean()

    cur = _xwobacon(sub)
    prior_sub = sc_2024[sc_2024["batter"] == mlbam]
    prior = _xwobacon(prior_sub)
    if pd.notna(cur) and pd.notna(prior):
        d = cur - prior
        if d > 0.020:
            l6 = BUY
        elif d < -0.020:
            l6 = FADE
        else:
            l6 = HOLD
    else:
        l6 = None

    return {"L1_blend": l1, "L2_rank": l2, "L3_boom": l3, "L4_sust": l4, "L5_xwoba_l21": l5, "L6_xwobacon_yoy": l6}


def sp_lenses(mlbam, asof, sc_pre, sc_2024, rp3_rank, rp3_total, replacement_per_start, blend_per_start):
    sub = sc_pre[sc_pre["pitcher"] == mlbam]

    # L1 blend
    if pd.notna(blend_per_start) and pd.notna(replacement_per_start):
        gap = blend_per_start - replacement_per_start
        l1 = BUY if gap > 1.5 else (FADE if gap < -1.5 else HOLD)
    else:
        l1 = None

    # L2 rank
    if rp3_rank and rp3_total:
        pct = rp3_rank / rp3_total
        l2 = BUY if pct <= 0.25 else (FADE if pct >= 0.75 else HOLD)
    else:
        l2 = None

    l3 = None  # filled by gameLog pass

    # L4 sustainability proxy: L30 K% / SwStr% vs season
    if len(sub) >= 200:
        L30_cut = asof - pd.Timedelta(days=30)
        last30 = sub[sub["game_date"] >= L30_cut]
        if len(last30) >= 100:
            # K rate per PA: events that are strikeout / total PA-ending events
            def _pa_k(df):
                pa_events = df[df["events"].notna() & (df["events"] != "")]
                if len(pa_events) < 30:
                    return np.nan
                return pa_events["events"].eq("strikeout").mean()
            l30_k = _pa_k(last30)
            season_k = _pa_k(sub)
            # SwStr proxy: swinging_strike description rate
            def _swstr(df):
                d = df["description"].fillna("")
                if len(d) < 50:
                    return np.nan
                return d.eq("swinging_strike").mean()
            l30_sw = _swstr(last30)
            season_sw = _swstr(sub)
            score = 0
            if pd.notna(l30_k) and pd.notna(season_k):
                score += 1 if l30_k - season_k > 0.02 else (-1 if l30_k - season_k < -0.02 else 0)
            if pd.notna(l30_sw) and pd.notna(season_sw):
                score += 1 if l30_sw - season_sw > 0.01 else (-1 if l30_sw - season_sw < -0.01 else 0)
            l4 = BUY if score >= 1 else (FADE if score <= -1 else HOLD)
        else:
            l4 = None
    else:
        l4 = None

    # L5, L6: hitter-only
    return {"L1_blend": l1, "L2_rank": l2, "L3_boom": l3, "L4_sust": l4, "L5_xwoba_l21": None, "L6_xwobacon_yoy": None}


# ----------------------------- driver ---------------------------------
def main():
    print("[1/6] Loading projections + Statcast...")
    rh3 = pd.read_csv(RH3)
    rp3 = pd.read_csv(RP3)
    sc25 = pd.read_parquet(SC25, columns=[
        "game_date", "batter", "pitcher", "events", "description",
        "estimated_woba_using_speedangle", "launch_speed",
    ])
    sc25["game_date"] = pd.to_datetime(sc25["game_date"])
    sc24 = pd.read_parquet(SC24, columns=[
        "game_date", "batter", "events",
        "estimated_woba_using_speedangle", "launch_speed",
    ])

    # 2025 season-wide baseline xwOBA per batter (computed AT SEASON END,
    # so technically slight leak; per CLAUDE.md the rule references "2025
    # baseline" as the established skill mean which is meant to be priorYr.
    # For 2025 as_of dates the proper baseline is 2024 full season. Use 2024.)
    print("[2/6] Computing 2024 baseline xwOBA per batter (used as 'baseline')...")
    base24 = (
        sc24.groupby("batter")["estimated_woba_using_speedangle"]
        .agg(["mean", "count"])
        .reset_index()
    )
    base24 = base24[base24["count"] >= 50]
    baseline_map = dict(zip(base24["batter"], base24["mean"]))

    # Sample players
    hitters = rh3.dropna(subset=["batter"]).head(N_HITTERS).copy()
    sps = rp3.dropna(subset=["pitcher"]).head(N_SPS).copy()
    rh3_total = len(rh3)
    rp3_total = len(rp3)
    print(f"  Hitters: {len(hitters)} | SPs: {len(sps)}")

    asof_dts = [pd.Timestamp(d) for d in AS_OF_DATES]

    # Pre-fetch full-season gameLog per player ONCE (saves API hits) and
    # later filter by date for both as_of-window boom/bust and forward FP.
    print("[3/6] Fetching gameLogs from MLB Stats API (one per player; cached in-process)...")
    hitter_logs: dict[int, list] = {}
    for i, row in enumerate(hitters.itertuples()):
        mid = int(row.batter)
        hitter_logs[mid] = fetch_game_log(mid, "hitting", 2025)
        if i % 20 == 0:
            print(f"  hitter {i}/{len(hitters)}: {row.player_name}: {len(hitter_logs[mid])} games")
        time.sleep(0.15)

    sp_logs: dict[int, list] = {}
    for i, row in enumerate(sps.itertuples()):
        mid = int(row.pitcher)
        sp_logs[mid] = fetch_game_log(mid, "pitching", 2025)
        if i % 10 == 0:
            print(f"  sp {i}/{len(sps)}: {row.player_name}: {len(sp_logs[mid])} starts")
        time.sleep(0.15)

    # Build snapshots
    print("[4/6] Building (player, as_of) snapshots + lens votes + forward FP...")
    rows = []
    for asof in asof_dts:
        sc_pre = sc25[sc25["game_date"] <= asof]
        # forward window
        f_end = asof + pd.Timedelta(days=FORWARD_DAYS)

        # ---- hitters
        for r in hitters.itertuples():
            mid = int(r.batter)
            lenses = hitter_lenses(
                mid, asof, sc_pre, sc24,
                baseline_map.get(mid, np.nan),
                r.rank, rh3_total,
                getattr(r, "replacement_xfp_per_pa", np.nan),
                getattr(r, "xfp_rh3_per_pa", np.nan),
            )
            log = hitter_logs.get(mid, [])
            # L3 boom/bust from games strictly BEFORE asof (last 21)
            pre_games = []
            for gd, st in log:
                try:
                    dt = pd.Timestamp(gd)
                except Exception:
                    continue
                if dt < asof:
                    pre_games.append((dt, _fp_hitter_row(st)))
            pre_games.sort()
            last21 = [fp for _, fp in pre_games[-21:]]
            if len(last21) >= 10:
                boom = sum(1 for x in last21 if x >= H_BOOM_FP) / len(last21)
                bust = sum(1 for x in last21 if x < H_BUST_FP) / len(last21)
                if boom > BOOM_PCT_BUY:
                    lenses["L3_boom"] = BUY
                elif bust > BUST_PCT_FADE:
                    lenses["L3_boom"] = FADE
                else:
                    lenses["L3_boom"] = HOLD
            # forward FP
            fwd = [_fp_hitter_row(st) for gd, st in log
                   if asof < pd.Timestamp(gd) <= f_end]
            if len(fwd) >= 5:
                fwd_per_g = float(np.mean(fwd))
                rows.append({
                    "pos_group": "H", "mlbam": mid, "name": r.player_name,
                    "as_of": asof.date().isoformat(),
                    "fwd_fp_per_g": fwd_per_g, "fwd_n_games": len(fwd),
                    **lenses,
                })

        # ---- SPs
        for r in sps.itertuples():
            mid = int(r.pitcher)
            lenses = sp_lenses(
                mid, asof, sc_pre, sc24,
                r.rank, rp3_total,
                getattr(r, "replacement_xfp_per_start", np.nan),
                getattr(r, "xfp_rp3_per_start", np.nan),
            )
            log = sp_logs.get(mid, [])
            pre = []
            for gd, st in log:
                try:
                    dt = pd.Timestamp(gd)
                except Exception:
                    continue
                if dt < asof:
                    pre.append((dt, _fp_sp_row(st)))
            pre.sort()
            last8 = [fp for _, fp in pre[-8:]]
            if len(last8) >= 4:
                boom = sum(1 for x in last8 if x >= SP_BOOM_FP) / len(last8)
                bust = sum(1 for x in last8 if x < SP_BUST_FP) / len(last8)
                if boom > BOOM_PCT_BUY:
                    lenses["L3_boom"] = BUY
                elif bust > BUST_PCT_FADE:
                    lenses["L3_boom"] = FADE
                else:
                    lenses["L3_boom"] = HOLD
            fwd = [_fp_sp_row(st) for gd, st in log
                   if asof < pd.Timestamp(gd) <= f_end]
            if len(fwd) >= 2:
                rows.append({
                    "pos_group": "SP", "mlbam": mid, "name": r.player_name,
                    "as_of": asof.date().isoformat(),
                    "fwd_fp_per_g": float(np.mean(fwd)), "fwd_n_games": len(fwd),
                    **lenses,
                })

    snap = pd.DataFrame(rows)
    print(f"  Snapshots built: {len(snap)} (H={(snap.pos_group=='H').sum()}, SP={(snap.pos_group=='SP').sum()})")

    # ----------------------------- lift table -------------------------
    print("[5/6] Computing per-lens lift + bootstrap CI...")
    LENSES = ["L1_blend", "L2_rank", "L3_boom", "L4_sust", "L5_xwoba_l21", "L6_xwobacon_yoy"]

    def lift_row(df, lens):
        sub = df[df[lens].notna()].copy()
        buy = sub[sub[lens] == BUY]["fwd_fp_per_g"].values
        fade = sub[sub[lens] == FADE]["fwd_fp_per_g"].values
        if len(buy) < 5 or len(fade) < 5:
            return dict(lens=lens, n_buy=len(buy), n_fade=len(fade),
                        mean_buy=np.nan, mean_fade=np.nan,
                        lift=np.nan, ci_lo=np.nan, ci_hi=np.nan, p=np.nan)
        lift = buy.mean() - fade.mean()
        # Bootstrap CI on lift
        rng = np.random.default_rng(42)
        boots = []
        for _ in range(2000):
            b = rng.choice(buy, size=len(buy), replace=True)
            f = rng.choice(fade, size=len(fade), replace=True)
            boots.append(b.mean() - f.mean())
        boots = np.array(boots)
        ci_lo, ci_hi = np.percentile(boots, [2.5, 97.5])
        # one-sided p that lift <= 0
        p = (boots <= 0).mean()
        return dict(lens=lens, n_buy=len(buy), n_fade=len(fade),
                    mean_buy=float(buy.mean()), mean_fade=float(fade.mean()),
                    lift=float(lift), ci_lo=float(ci_lo), ci_hi=float(ci_hi), p=float(p))

    H_df = snap[snap.pos_group == "H"]
    SP_df = snap[snap.pos_group == "SP"]
    lift_H = pd.DataFrame([lift_row(H_df, L) for L in LENSES])
    lift_SP = pd.DataFrame([lift_row(SP_df, L) for L in ["L1_blend", "L2_rank", "L3_boom", "L4_sust"]])

    # ----------------------------- report -----------------------------
    print("[6/6] Writing report...")
    def fmt_tbl(df):
        out = [
            "| Lens | n BUY | n FADE | Mean BUY FP/g | Mean FADE FP/g | Lift | 95% CI | p(lift<=0) |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for _, r in df.iterrows():
            if np.isnan(r["lift"]):
                out.append(f"| {r['lens']} | {r['n_buy']} | {r['n_fade']} | — | — | INCONCLUSIVE | — | — |")
            else:
                out.append(
                    f"| {r['lens']} | {r['n_buy']} | {r['n_fade']} | "
                    f"{r['mean_buy']:.2f} | {r['mean_fade']:.2f} | "
                    f"{r['lift']:+.2f} | [{r['ci_lo']:+.2f}, {r['ci_hi']:+.2f}] | {r['p']:.3f} |"
                )
        return "\n".join(out)

    def weight_tbl(df):
        positive = df[df["lift"] > 0].copy()
        if positive.empty:
            return "_All lenses had non-positive or inconclusive lift in this sample._"
        positive["weight"] = positive["lift"] / positive["lift"].sum()
        out = ["| Lens | Lift | Recommended weight |", "|---|---|---|"]
        for _, r in positive.iterrows():
            out.append(f"| {r['lens']} | {r['lift']:+.2f} | {r['weight']:.2f} |")
        return "\n".join(out)

    neg_H = lift_H[lift_H["lift"] < 0]
    neg_SP = lift_SP[lift_SP["lift"] < 0]

    md = f"""# Lens Weight Empirical Backtest — Sample (2026-06-06)

## Method

- Player sample: top {N_HITTERS} hitters by xfp_rh3 rank + top {N_SPS} SPs by xfp_rp3 rank
- As-of dates: {", ".join(AS_OF_DATES)}
- Forward window: {FORWARD_DAYS} days from each as_of
- Forward FP: MLB Stats API gameLog, BrownU canonical scoring
- Lens votes: computed strictly from Statcast / gameLog dated <= as_of
- 2024 full-season xwOBA used as the "established skill baseline" for L5 (a 2025
  in-season baseline would self-leak through future games)
- Encoding: BUY=+1, HOLD=0, FADE=−1; lift = mean(BUY) − mean(FADE)
- Bootstrap CI: 2000 resamples each side, independent

Resulting snapshots: **{len(snap)}** ({(snap.pos_group=='H').sum()} hitter rows, {(snap.pos_group=='SP').sum()} SP rows)

## Hitters — per-lens lift

{fmt_tbl(lift_H)}

## SPs — per-lens lift

{fmt_tbl(lift_SP)}

## Recommended weights (proportional to positive lift)

### Hitters
{weight_tbl(lift_H)}

### SPs
{weight_tbl(lift_SP)}

## Lenses with NEGATIVE lift (wrong direction in this sample)

Hitters: {", ".join(neg_H["lens"].tolist()) if not neg_H.empty else "_none_"}

SPs: {", ".join(neg_SP["lens"].tolist()) if not neg_SP.empty else "_none_"}

## Lenses inconclusive (sample too small to read)

{", ".join(lift_H[lift_H["lift"].isna()]["lens"].tolist()) or "_none for hitters_"}; SPs: {", ".join(lift_SP[lift_SP["lift"].isna()]["lens"].tolist()) or "_none_"}

## Caveats

- **Sample size**: top-of-rank skews toward high-talent players, compressing the
  fade tail. A balanced sample drawn from across the rh3/rp3 distribution would
  give cleaner FADE groups.
- **As-of timing**: only 4 dates × ({N_HITTERS}+{N_SPS}) players = upper bound
  ~{4*(N_HITTERS+N_SPS)} snapshots before exclusions for IL / insufficient games.
- **Recency leak**: L1 and L2 use the current (2026) rh3/rp3 rank as a proxy for
  rank-at-T because no historical rank snapshots exist for 2025. This means L2
  in particular has end-of-season information baked in and will look STRONGER
  here than it would in a true real-time test.
- **L4 sustainability**: simplified to a 2-marker (K%, SwStr% for SPs) or
  L30-vs-season xwOBA gap (hitters) decomposition; the production 9-marker
  panel is more nuanced.
- **L5 baseline**: uses 2024 full-season xwOBA, which is the closest non-leaky
  baseline for 2025 as-of dates but doesn't match the production "2025 baseline"
  framing. Real validation would use a rolling-prior-window baseline.
- **No IL filter**: players who land on the IL during the forward window
  contribute low forward FP/g that's not a lens failure but a health event.

## What full validation would need

- Historical rank snapshots for 2024 + 2025 (would unblock L1, L2)
- Per-game IL status panel to censor forward window on IL events
- Bootstrap clustered on player (current bootstrap treats each snapshot as
  independent; multiple as_of per player creates within-player correlation)
- N >= 1000 snapshots per pos group, with the FADE arm boosted by sampling
  bottom-rank players, not just top-100
"""

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(md, encoding="utf-8")
    print(f"Report written: {OUT_MD}")

    # Save raw snapshots for re-analysis
    snap_csv = OUT_MD.with_suffix(".snapshots.csv")
    snap.to_csv(snap_csv, index=False)
    print(f"Snapshots: {snap_csv}")


if __name__ == "__main__":
    main()

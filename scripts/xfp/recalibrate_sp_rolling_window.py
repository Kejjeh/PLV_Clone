"""
Re-calibrate SP rolling-window good-start persistence table using 2021-2025 Statcast data.
Formula: fp_proxy_per_bf = (K - BB - H - HR) / BF   (matches sp-breakout-signal skill)
Good start: fp_proxy_per_bf >= -0.0476
Outputs results to data/research/mc_rolling_window_results.txt
"""

import pandas as pd
import numpy as np
import pyarrow.parquet as pq
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

REPO = Path(r"c:\Users\Joshua\plv_clone")
CACHE = REPO / "data/research/xfp_cache"
OUTPUT = REPO / "data/research/mc_rolling_window_results.txt"

YEARS = [2021, 2022, 2023, 2024, 2025]
GS_THRESHOLD = -0.0476   # fp_proxy/bf >= this = good start
MIN_BF = 10
N_BOOTSTRAP = 10_000
RNG_SEED = 42

PA_END_EVENTS = {
    "strikeout", "strikeout_double_play",
    "walk", "intent_walk", "hit_by_pitch",
    "single", "double", "triple", "home_run",
    "field_out", "force_out", "grounded_into_double_play",
    "double_play", "triple_play",
    "fielders_choice", "fielders_choice_out",
    "sac_fly", "sac_fly_double_play", "sac_bunt",
    "sac_bunt_double_play", "catcher_interf",
    "field_error", "other_out", "truncated_pa",
}


def load_statcast(years):
    frames = []
    for yr in years:
        path = CACHE / f"statcast_{yr}.parquet"
        if not path.exists():
            print(f"  WARNING: {path} not found, skipping")
            continue
        df = pd.read_parquet(path, columns=[
            "pitcher", "game_pk", "game_date", "events",
            "inning_topbot",
        ])
        df["season"] = yr
        frames.append(df)
        print(f"  {yr}: {len(df):,} pitches")
    return pd.concat(frames, ignore_index=True)


def compute_per_start_stats(df):
    """
    Aggregate pitch-level Statcast to per-start stats.
    fp_proxy_per_bf = (K - BB - H - HR) / BF
    """
    d = df.copy()
    d["is_k"]   = d["events"].isin(["strikeout", "strikeout_double_play"]).astype(int)
    d["is_bb"]  = d["events"].isin(["walk", "intent_walk"]).astype(int)
    d["is_hbp"] = d["events"].isin(["hit_by_pitch"]).astype(int)
    d["is_h"]   = d["events"].isin(["single", "double", "triple", "home_run"]).astype(int)
    d["is_hr"]  = d["events"].isin(["home_run"]).astype(int)
    d["is_pa"]  = d["events"].isin(PA_END_EVENTS).astype(int)

    grp = d.groupby(["pitcher", "game_pk", "game_date", "season"]).agg(
        K=("is_k", "sum"),
        BB=("is_bb", "sum"),
        HBP=("is_hbp", "sum"),
        H=("is_h", "sum"),
        HR=("is_hr", "sum"),
        BF=("is_pa", "sum"),
    ).reset_index()

    grp["fp_proxy"] = grp["K"] - grp["BB"] - grp["H"] - grp["HR"]
    grp["fp_proxy_per_bf"] = np.where(
        grp["BF"] > 0, grp["fp_proxy"] / grp["BF"], np.nan
    )
    return grp


def build_start_sequences(game_df):
    """
    For each pitcher-season, sort starts by game_date, compute rolling windows.
    Returns DataFrame of (pitcher, season, start_idx, is_good, prev_N_goods, prev_N_seq).
    """
    game_df = game_df[game_df["BF"] >= MIN_BF].copy()
    game_df["is_good"] = (game_df["fp_proxy_per_bf"] >= GS_THRESHOLD).astype(int)
    game_df["game_date"] = pd.to_datetime(game_df["game_date"])
    game_df = game_df.sort_values(["pitcher", "season", "game_date"]).reset_index(drop=True)

    records = []
    for (pitcher, season), grp in game_df.groupby(["pitcher", "season"]):
        goods = grp["is_good"].tolist()
        n = len(goods)
        for i in range(n):
            row = {
                "pitcher": pitcher,
                "season": season,
                "start_idx": i,
                "is_good": goods[i],
            }
            for w in [3, 4, 5]:
                if i >= w:
                    window = goods[i-w:i]
                    row[f"prev_{w}_goods"] = sum(window)
                    # sequence string: e.g. "011" means bad, good, good (last = most recent)
                    row[f"prev_{w}_seq"] = "".join(str(g) for g in window)
                else:
                    row[f"prev_{w}_goods"] = None
                    row[f"prev_{w}_seq"] = None
            records.append(row)
    return pd.DataFrame(records)


def bootstrap_rate(arr, n_boot=N_BOOTSTRAP, seed=RNG_SEED):
    arr = np.asarray(arr, dtype=float)
    n = len(arr)
    if n == 0:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    boots = rng.choice(arr, size=(n_boot, n), replace=True).mean(axis=1)
    return boots.mean(), np.percentile(boots, 2.5), np.percentile(boots, 97.5)


def main():
    print("Loading Statcast data 2021-2025...")
    df = load_statcast(YEARS)
    print(f"  Total: {len(df):,} pitches")

    print("\nComputing per-start fp_proxy...")
    game_df = compute_per_start_stats(df)

    # SP filter: exclude relief appearances (BF < 10 or very short outings)
    # Also filter to "starting" appearances only
    # A start = first appearance in a game for a pitcher (low inning_topbot appearance)
    # We don't have a direct "is_starter" flag so use BF >= 15 as SP proxy
    # (SP starts typically have BF 18-30; RP outings <10)
    game_df_sp = game_df[game_df["BF"] >= MIN_BF].copy()
    print(f"  {len(game_df_sp):,} SP starts (BF>={MIN_BF})")
    print(f"  fp_proxy_per_bf distribution:")
    for pct in [10, 25, 50, 65, 75, 90]:
        val = game_df_sp["fp_proxy_per_bf"].quantile(pct/100)
        print(f"    {pct}th pct: {val:.4f}")
    gs_pct = (game_df_sp["fp_proxy_per_bf"] >= GS_THRESHOLD).mean()
    print(f"  Good-start rate (threshold={GS_THRESHOLD}): {gs_pct:.3f} ({gs_pct*100:.1f}%)")

    print("\nBuilding start sequences...")
    seq_df = build_start_sequences(game_df_sp)
    print(f"  {len(seq_df):,} pitcher-start records")

    # Baseline: starts where we have at least L3 window
    baseline_df = seq_df[seq_df["prev_3_goods"].notna()]
    baseline_arr = baseline_df["is_good"].values
    base_rate, base_lo, base_hi = bootstrap_rate(baseline_arr)
    n_baseline = len(baseline_arr)
    print(f"  Baseline: n={n_baseline:,}  rate={base_rate:.3f} ({base_rate*100:.1f}%)")

    # Rolling window patterns
    patterns = [
        ("2/3", "prev_3_goods", 2),
        ("3/4", "prev_4_goods", 3),
        ("4/5", "prev_5_goods", 4),
        ("3/3", "prev_3_goods", 3),
        ("4/4", "prev_4_goods", 4),
        ("5/5", "prev_5_goods", 5),
        ("2/4", "prev_4_goods", 2),
        ("3/5", "prev_5_goods", 3),
    ]

    old_rates = {
        "2/3": 0.351, "3/4": 0.428, "4/5": 0.494,
        "3/3": 0.508, "4/4": 0.582, "5/5": 0.661,
        "2/4": 0.289, "3/5": 0.355,
    }
    old_base = 0.254

    tiers = {
        "2/3": "WATCH", "3/4": "ACTIONABLE", "4/5": "STRONG",
        "3/3": "STRONG", "4/4": "LOCK", "5/5": "LOCK",
        "2/4": "NOISE", "3/5": "WATCH",
    }

    print("\nBootstrapping window patterns...")
    results = []
    for label, col, k in patterns:
        mask = seq_df[col] == k
        sub = seq_df[mask]["is_good"].values
        rate, lo, hi = bootstrap_rate(sub)
        results.append({
            "label": label, "rate": rate, "lo": lo, "hi": hi,
            "n": len(sub),
            "old_rate": old_rates.get(label, np.nan),
        })
        print(f"  {label}: n={len(sub):,}  rate={rate*100:.1f}%  CI=[{lo*100:.1f}%,{hi*100:.1f}%]")

    # Order test: 2/3 window — three sequences
    print("\nOrder test (2/3 window)...")
    order_df = seq_df[seq_df["prev_3_goods"] == 2].copy()
    # seq encoding: prev3_seq = [start_i-3, start_i-2, start_i-1]
    # bad-GG = "011", G-bad-G = "101", GG-bad = "110"
    order_results = {}
    for seq_pat, name in [("011", "bad-GG"), ("101", "G-bad-G"), ("110", "GG-bad")]:
        sub = order_df[order_df["prev_3_seq"] == seq_pat]["is_good"].values
        r, lo, hi = bootstrap_rate(sub)
        order_results[name] = (r, lo, hi, len(sub))
        print(f"  {name}: n={len(sub):,}  rate={r*100:.1f}%  CI=[{lo*100:.1f}%,{hi*100:.1f}%]")
    ord_rates = [v[0] for v in order_results.values() if not np.isnan(v[0])]
    max_diff_ord = (max(ord_rates) - min(ord_rates)) * 100 if ord_rates else np.nan

    # Consecutive streak table
    print("\nConsecutive streak table...")
    # For each start i, compute how many consecutive good starts BEFORE start i
    streak_records = []
    for (pitcher, season), grp in seq_df.groupby(["pitcher", "season"]):
        goods = grp.sort_values("start_idx")["is_good"].tolist()
        n = len(goods)
        for i in range(1, n):  # need at least 1 prior start
            streak = 0
            for j in range(i-1, -1, -1):
                if goods[j] == 1:
                    streak += 1
                else:
                    break
            streak_records.append({
                "is_good": goods[i],
                "streak": streak,
            })
    streak_df = pd.DataFrame(streak_records)
    # Baseline for streaks: all starts with streak >= 1 (at least 1 prior good)
    streak_base_arr = streak_df[streak_df["streak"] >= 1]["is_good"].values
    streak_base_rate, _, _ = bootstrap_rate(streak_base_arr)

    streak_results = []
    for s in [2, 3, 4, 5, 7]:
        sub = streak_df[streak_df["streak"] >= s]["is_good"].values
        r, lo, hi = bootstrap_rate(sub)
        streak_results.append((s, r, lo, hi, len(sub)))
        print(f"  Streak>={s}: n={len(sub):,}  rate={r*100:.1f}%")

    # Drift check
    drift_notes = []
    for r in results:
        if np.isnan(r["old_rate"]):
            continue
        diff = r["rate"] - r["old_rate"]
        tag = "DRIFT" if abs(diff) > 0.03 else ("minor" if abs(diff) > 0.015 else "stable")
        # Check if new rate is outside old plausible CI (approximate with ±2*sqrt(p*(1-p)/n))
        old_r = r["old_rate"]
        old_se = np.sqrt(old_r * (1 - old_r) / 33063)  # approx n from original
        outside = "|" if abs(diff) > 2 * old_se else " "
        drift_notes.append(
            f"  {r['label']:<4}: NEW={r['rate']*100:.1f}%  OLD={old_r*100:.1f}%  "
            f"diff={diff*100:+.1f}pp  {outside} {tag}"
        )

    # Format output
    lines = []
    lines.append("=" * 76)
    lines.append("ROLLING WINDOW PERSISTENCE TABLE (2021-2025 re-calibration)")
    lines.append(f"Formula: fp_proxy_per_bf = (K - BB - H - HR) / BF")
    lines.append(f"Good-start threshold: fp_proxy_per_bf >= {GS_THRESHOLD}")
    lines.append(f"Min BF per start: {MIN_BF}")
    lines.append(f"Bootstrap: {N_BOOTSTRAP:,} iterations, seed={RNG_SEED}")
    lines.append(f"Seasons: {YEARS}")
    lines.append("=" * 76)
    lines.append("")
    lines.append(f"Baseline next-start good-start rate: {base_rate*100:.1f}%  "
                 f"CI=[{base_lo*100:.1f}%, {base_hi*100:.1f}%]  n={n_baseline:,}")
    lines.append(f"  Prior calibration (2018-2025): {old_base*100:.1f}%")
    lines.append("")
    lines.append(f"{'Window':<8} {'Rate':>6}  {'Delta':>7}  {'CI [lo, hi]':>18}  {'n':>6}  Tier")
    lines.append("-" * 76)
    for r in results:
        delta = (r["rate"] - base_rate) * 100
        lines.append(
            f"{r['label']:<8} {r['rate']*100:>5.1f}%  {delta:>+6.1f}pp  "
            f"[{r['lo']*100:.1f}%, {r['hi']*100:.1f}%]  {r['n']:>6,}  {tiers.get(r['label'],'')}"
        )
    lines.append("")
    lines.append("ORDER TEST (2/3 window — does position of bad start matter?)")
    lines.append("-" * 76)
    for name, (r, lo, hi, n) in order_results.items():
        lines.append(f"  {name:<12}: {r*100:.1f}%  CI=[{lo*100:.1f}%, {hi*100:.1f}%]  n={n:,}")
    lines.append(f"  Max spread: {max_diff_ord:.1f}pp")
    if max_diff_ord <= 2.0:
        lines.append("  VERDICT: Order doesn't matter (<=2pp) — window count is sufficient")
    elif max_diff_ord <= 5.0:
        lines.append("  VERDICT: Marginal ordering effect (2-5pp) — monitor but not actionable")
    else:
        lines.append("  VERDICT: Ordering matters (>5pp) — consider sequence-aware model")
    lines.append("")
    lines.append("CONSECUTIVE STREAK TABLE (different baseline: streak >= 1)")
    lines.append("-" * 76)
    lines.append(f"  Streak>=1 baseline: {streak_base_rate*100:.1f}%  (prior: 45.8%)")
    for s, r, lo, hi, n in streak_results:
        delta = (r - streak_base_rate) * 100
        lines.append(
            f"  Streak>={s}: {r*100:.1f}%  {delta:>+.1f}pp  "
            f"CI=[{lo*100:.1f}%, {hi*100:.1f}%]  n={n:,}"
        )
    lines.append("")
    lines.append("DRIFT CHECK vs 2018-2025 calibration")
    lines.append("-" * 76)
    for note in drift_notes:
        lines.append(note)
    lines.append("")
    lines.append("SIGNAL TIER RECOMMENDATIONS")
    lines.append("-" * 76)
    for r in results:
        delta_new = r["rate"] - base_rate
        delta_old = r["old_rate"] - old_base if not np.isnan(r["old_rate"]) else 0
        tier = tiers.get(r["label"], "?")
        shift = (delta_new - delta_old) * 100
        if abs(shift) > 5:
            lines.append(f"  {r['label']}: signal lift shifted {shift:+.1f}pp vs old — REVIEW tier {tier}")
        else:
            lines.append(f"  {r['label']}: lift={delta_new*100:+.1f}pp (was {delta_old*100:+.1f}pp) — tier {tier} holds")
    lines.append("")
    lines.append("METHODOLOGY NOTES")
    lines.append("-" * 76)
    lines.append("- fp_proxy_per_bf = (K - BB - H - HR) / BF (exact match to sp-breakout-signal skill)")
    lines.append("- No ER term (consistent with skill definition)")
    lines.append("- BF >= 10 filter to exclude sub-SP relief outings")
    lines.append("- Sequences: '1'=good, '0'=bad, left-to-right = oldest-to-most-recent")
    lines.append("- 2020 COVID season excluded; 2026 data excluded (partial year)")
    lines.append("=" * 76)

    output_text = "\n".join(lines)
    print("\n" + output_text)
    OUTPUT.write_text(output_text, encoding="utf-8")
    print(f"\nSaved to {OUTPUT}")


if __name__ == "__main__":
    main()

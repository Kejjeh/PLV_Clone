"""
Monte Carlo bootstrap validation of stuff_contact_composite signal for SPs.
Harrison archetype: fp_proxy blind early, but elite contact suppression.

fp_proxy_per_bf = (K - BB - H - HR) / BF
Threshold: -0.0476 (65th percentile, 2018-2025 calibration per sp-breakout-signal skill)

Usage: python scripts/mc_harrison_composite.py
"""
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path("data/research/xfp_cache")
OUT_FILE = Path("data/research/mc_harrison_composite_results.txt")

TRAIN_YEARS = [2021, 2022, 2023, 2024]
HOLDOUT_YEAR = 2025
FPP_THRESHOLD = -0.0476   # fp_proxy "fired" if fpp/bf >= this
MIN_GS_TOTAL = 10         # minimum total GS in season
EARLY_GS = 6              # first N starts define "early" window
N_BOOTSTRAP = 10_000
RNG_SEED = 42


def process_year(year: int) -> pd.DataFrame:
    """
    Load statcast parquet for a year and return pitcher-season records
    with early/RoS split features.

    Returns DataFrame with columns:
      pitcher, year, early_gs, early_fpp_per_bf,
      early_whiff_pct, early_csw_pct, early_xwoba_contact, early_ev_mean,
      early_babip, ros_gs, ros_fpp_per_bf, ros_success
    """
    print(f"  Loading statcast_{year}.parquet...")
    df = pd.read_parquet(DATA_DIR / f"statcast_{year}.parquet")

    # ── STEP 1: Identify SP starts ──────────────────────────────────────────
    game_stats = (
        df.groupby(["pitcher", "game_pk", "game_date"])
        .agg(n_pitches=("pitch_type", "count"), min_inning=("inning", "min"))
        .reset_index()
    )
    # SP = pitched from inning 1 with >= 40 pitches (filters out long relievers)
    starts = game_stats[
        (game_stats["min_inning"] == 1) & (game_stats["n_pitches"] >= 40)
    ].copy()
    starts = starts.sort_values(["pitcher", "game_date"]).reset_index(drop=True)
    starts["gs_num"] = starts.groupby("pitcher").cumcount() + 1

    n_pitchers = starts["pitcher"].nunique()
    n_starts_total = len(starts)
    print(f"  SP starts found: {n_starts_total} | unique pitchers: {n_pitchers}")

    # ── STEP 2: Filter to SP pitches only ───────────────────────────────────
    sp_pks = set(zip(starts["pitcher"].tolist(), starts["game_pk"].tolist()))
    df["_sp_key"] = list(zip(df["pitcher"].tolist(), df["game_pk"].tolist()))
    df_sp = df[df["_sp_key"].isin(sp_pks)].copy()
    df_sp.drop(columns=["_sp_key"], inplace=True)

    # ── STEP 3: Pitch-level metrics ─────────────────────────────────────────
    desc = df_sp["description"]
    df_sp["is_swstr"] = desc.isin(["swinging_strike", "swinging_strike_blocked", "foul_tip"])
    df_sp["is_swing"] = desc.isin([
        "swinging_strike", "swinging_strike_blocked", "foul_tip",
        "hit_into_play", "foul", "foul_bunt", "bunt_foul_tip", "missed_bunt",
    ])
    df_sp["is_cstr"] = desc == "called_strike"
    df_sp["has_launch"] = df_sp["launch_speed"].notna()
    # xwoba only on contact (balls in play with launch data)
    df_sp["xwoba_bip"] = df_sp["estimated_woba_using_speedangle"].where(df_sp["has_launch"])
    df_sp["ev_bip"] = df_sp["launch_speed"].where(df_sp["has_launch"])

    # ── STEP 4: PA-level events (fp_proxy components) ───────────────────────
    pa = df_sp[df_sp["events"].notna()].copy()
    pa["is_k"]   = pa["events"].isin(["strikeout", "strikeout_double_play"])
    pa["is_bb"]  = pa["events"].isin(["walk", "intent_walk"])
    pa["is_h"]   = pa["events"].isin(["single", "double", "triple", "home_run"])
    pa["is_hr"]  = pa["events"] == "home_run"

    # Per-game raw counts
    game_pa = pa.groupby(["pitcher", "game_pk"]).agg(
        K=("is_k", "sum"),
        BB=("is_bb", "sum"),
        H=("is_h", "sum"),
        HR=("is_hr", "sum"),
        BF=("is_k", "count"),   # BF = total PA events
    ).reset_index()
    # fp_proxy_per_bf = (K - BB - H - HR) / BF  (per sp-breakout-signal calibration)
    game_pa["fpp_bf"] = (
        game_pa["K"] - game_pa["BB"] - game_pa["H"] - game_pa["HR"]
    ) / game_pa["BF"].clip(lower=1)

    # Per-game pitch counts (for whiff, csw, xwoba, ev)
    game_pitch = df_sp.groupby(["pitcher", "game_pk"]).agg(
        swstr_n=("is_swstr", "sum"),
        swing_n=("is_swing", "sum"),
        cstr_n=("is_cstr", "sum"),
        pitch_n=("pitch_type", "count"),
        xwoba_bip_sum=("xwoba_bip", "sum"),
        xwoba_bip_n=("has_launch", "sum"),
        ev_bip_sum=("ev_bip", "sum"),
        ev_bip_n=("has_launch", "sum"),
    ).reset_index()

    # ── STEP 5: Merge into per-game table with start number ─────────────────
    game_all = starts.merge(game_pa, on=["pitcher", "game_pk"], how="left")
    game_all = game_all.merge(game_pitch, on=["pitcher", "game_pk"], how="left")

    # ── STEP 6: Filter to pitchers with MIN_GS_TOTAL+ starts ────────────────
    total_gs = game_all.groupby("pitcher")["gs_num"].max().reset_index(name="total_gs")
    eligible = set(total_gs.loc[total_gs["total_gs"] >= MIN_GS_TOTAL, "pitcher"])
    game_all = game_all[game_all["pitcher"].isin(eligible)].copy()
    print(f"  Eligible pitchers ({MIN_GS_TOTAL}+ GS): {len(eligible)}")

    # ── STEP 7: Early window (first EARLY_GS starts) ─────────────────────────
    early = game_all[game_all["gs_num"] <= EARLY_GS]
    early_agg = early.groupby("pitcher").agg(
        early_gs=("gs_num", "count"),
        # fp_proxy raw counts
        e_K=("K", "sum"), e_BB=("BB", "sum"),
        e_H=("H", "sum"), e_HR=("HR", "sum"),
        e_BF=("BF", "sum"),
        # pitch raw counts
        e_swstr=("swstr_n", "sum"),
        e_swing=("swing_n", "sum"),
        e_cstr=("cstr_n", "sum"),
        e_pitches=("pitch_n", "sum"),
        # contact
        e_xwoba_sum=("xwoba_bip_sum", "sum"),
        e_xwoba_n=("xwoba_bip_n", "sum"),
        e_ev_sum=("ev_bip_sum", "sum"),
        e_ev_n=("ev_bip_n", "sum"),
    ).reset_index()

    # Compute rates
    early_agg["early_fpp_per_bf"] = (
        early_agg["e_K"] - early_agg["e_BB"] - early_agg["e_H"] - early_agg["e_HR"]
    ) / early_agg["e_BF"].clip(lower=1)
    early_agg["early_whiff_pct"] = early_agg["e_swstr"] / early_agg["e_swing"].clip(lower=1)
    early_agg["early_csw_pct"]   = (
        (early_agg["e_swstr"] + early_agg["e_cstr"]) / early_agg["e_pitches"].clip(lower=1)
    )
    early_agg["early_xwoba_contact"] = (
        early_agg["e_xwoba_sum"] / early_agg["e_xwoba_n"].clip(lower=1)
    )
    early_agg["early_ev_mean"] = (
        early_agg["e_ev_sum"] / early_agg["e_ev_n"].clip(lower=1)
    )
    # BABIP proxy = (H - HR) / (BF - K - BB - HR)
    babip_num   = (early_agg["e_H"] - early_agg["e_HR"]).clip(lower=0)
    babip_denom = (early_agg["e_BF"] - early_agg["e_K"] - early_agg["e_BB"] - early_agg["e_HR"]).clip(lower=1)
    early_agg["early_babip"] = babip_num / babip_denom

    # ── STEP 8: RoS window (starts 7+) ──────────────────────────────────────
    ros = game_all[game_all["gs_num"] > EARLY_GS]
    ros_agg = ros.groupby("pitcher").agg(
        ros_gs=("gs_num", "count"),
        ros_K=("K", "sum"), ros_BB=("BB", "sum"),
        ros_H=("H", "sum"), ros_HR=("HR", "sum"),
        ros_BF=("BF", "sum"),
    ).reset_index()
    ros_agg["ros_fpp_per_bf"] = (
        ros_agg["ros_K"] - ros_agg["ros_BB"] - ros_agg["ros_H"] - ros_agg["ros_HR"]
    ) / ros_agg["ros_BF"].clip(lower=1)
    ros_agg["ros_success"] = (ros_agg["ros_fpp_per_bf"] >= FPP_THRESHOLD).astype(int)

    # ── STEP 9: Combine early + RoS (inner join = only pitchers in both) ─────
    season = early_agg.merge(ros_agg, on="pitcher", how="inner")
    season["year"] = year
    print(f"  Pitcher-seasons (early + RoS): {len(season)}")
    return season


def bootstrap_precision(pool_success: np.ndarray, n_iter: int = N_BOOTSTRAP, rng=None):
    """Bootstrap mean and 95% CI for precision from a binary success array."""
    if rng is None:
        rng = np.random.default_rng(RNG_SEED)
    n = len(pool_success)
    if n == 0:
        return np.nan, np.nan, np.nan
    boot = rng.choice(pool_success, size=(n_iter, n), replace=True).mean(axis=1)
    return boot.mean(), np.percentile(boot, 2.5), np.percentile(boot, 97.5)


def analyze(all_data: pd.DataFrame, label: str, rng) -> list[str]:
    lines = []
    lines.append(f"\n{'='*70}")
    lines.append(f" {label}")
    lines.append(f"{'='*70}")

    blind = all_data[all_data["early_fpp_per_bf"] < FPP_THRESHOLD].copy()
    lines.append(f"\nAll pitcher-seasons ({MIN_GS_TOTAL}+ GS, with RoS data): {len(all_data)}")
    lines.append(
        f"fp_proxy BLIND early (fpp/bf < {FPP_THRESHOLD}): {len(blind)} "
        f"({len(blind)/max(len(all_data),1)*100:.1f}%)"
    )

    if len(blind) == 0:
        lines.append("  No fp_proxy-blind pitcher-seasons. Skipping.")
        return lines

    base_prec = blind["ros_success"].mean()
    base_n = len(blind)
    lines.append(f"\nBaseline (fp_proxy blind, no signal): RoS success = {base_prec*100:.1f}% (n={base_n})")

    # ── T1: whiff >= 26% AND xwoba_contact <= X ──────────────────────────────
    lines.append("\n--- T1: whiff >= 26% AND xwoba_contact <= X ---")
    for xw in [0.280, 0.300, 0.310, 0.320, 0.330]:
        mask = (blind["early_whiff_pct"] >= 0.26) & (blind["early_xwoba_contact"] <= xw)
        n_sig = int(mask.sum())
        if n_sig == 0:
            lines.append(f"  whiff>=26 AND xwoba<={xw:.3f}: n=0 — skip")
            continue
        prec, lo, hi = bootstrap_precision(blind.loc[mask, "ros_success"].values, rng=rng)
        lift = prec - base_prec
        lines.append(
            f"  whiff>=26 AND xwoba<={xw:.3f}: "
            f"precision={prec*100:.1f}%, lift={lift*100:+.1f}pp "
            f"[CI: {lo*100:.1f}%-{hi*100:.1f}%], n={n_sig}"
        )

    # ── T2: csw >= 30% AND xwoba_contact <= X ───────────────────────────────
    lines.append("\n--- T2: csw >= 30% AND xwoba_contact <= X ---")
    for xw in [0.280, 0.300, 0.310]:
        mask = (blind["early_csw_pct"] >= 0.30) & (blind["early_xwoba_contact"] <= xw)
        n_sig = int(mask.sum())
        if n_sig == 0:
            lines.append(f"  csw>=30 AND xwoba<={xw:.3f}: n=0 — skip")
            continue
        prec, lo, hi = bootstrap_precision(blind.loc[mask, "ros_success"].values, rng=rng)
        lift = prec - base_prec
        lines.append(
            f"  csw>=30 AND xwoba<={xw:.3f}: "
            f"precision={prec*100:.1f}%, lift={lift*100:+.1f}pp "
            f"[CI: {lo*100:.1f}%-{hi*100:.1f}%], n={n_sig}"
        )

    # ── T3: whiff >= Y AND xwoba_contact <= 0.320 ───────────────────────────
    lines.append("\n--- T3: whiff >= Y AND xwoba_contact <= 0.320 ---")
    for wh in [0.22, 0.24, 0.26, 0.28]:
        mask = (blind["early_whiff_pct"] >= wh) & (blind["early_xwoba_contact"] <= 0.320)
        n_sig = int(mask.sum())
        if n_sig == 0:
            lines.append(f"  whiff>={wh:.2f} AND xwoba<=0.320: n=0 — skip")
            continue
        prec, lo, hi = bootstrap_precision(blind.loc[mask, "ros_success"].values, rng=rng)
        lift = prec - base_prec
        lines.append(
            f"  whiff>={wh:.2f} AND xwoba<=0.320: "
            f"precision={prec*100:.1f}%, lift={lift*100:+.1f}pp "
            f"[CI: {lo*100:.1f}%-{hi*100:.1f}%], n={n_sig}"
        )

    # ── EV gate ──────────────────────────────────────────────────────────────
    lines.append("\n--- avg_ev gate (added to whiff>=26 AND xwoba<=0.320) ---")
    for ev in [85, 87, 89]:
        mask = (
            (blind["early_whiff_pct"] >= 0.26)
            & (blind["early_xwoba_contact"] <= 0.320)
            & (blind["early_ev_mean"] < ev)
        )
        n_sig = int(mask.sum())
        if n_sig == 0:
            lines.append(f"  + ev<{ev}: n=0 — skip")
            continue
        prec, lo, hi = bootstrap_precision(blind.loc[mask, "ros_success"].values, rng=rng)
        lift = prec - base_prec
        lines.append(
            f"  whiff>=26 AND xwoba<=0.320 AND ev<{ev}: "
            f"precision={prec*100:.1f}%, lift={lift*100:+.1f}pp "
            f"[CI: {lo*100:.1f}%-{hi*100:.1f}%], n={n_sig}"
        )

    # ── Exhaustive sweep for optimal combos ──────────────────────────────────
    lines.append("\n--- OPTIMAL COMPOSITE (exhaustive sweep) ---")
    best_prec_row = None
    best_recall_row = None
    for wh in [0.22, 0.24, 0.26, 0.28]:
        for xw in [0.280, 0.300, 0.310, 0.320, 0.330]:
            mask = (blind["early_whiff_pct"] >= wh) & (blind["early_xwoba_contact"] <= xw)
            n_sig = int(mask.sum())
            if n_sig == 0:
                continue
            prec, lo, hi = bootstrap_precision(blind.loc[mask, "ros_success"].values, rng=rng)
            lift = prec - base_prec
            recall = n_sig / base_n
            row = (prec, lift, lo, hi, n_sig, recall, f"whiff>={wh:.2f} AND xwoba<={xw:.3f}")
            if best_prec_row is None or prec > best_prec_row[0]:
                best_prec_row = row
            if best_recall_row is None or recall > best_recall_row[5]:
                best_recall_row = row
    for combo_type, row in [("Best precision", best_prec_row), ("Best recall   ", best_recall_row)]:
        if row:
            prec, lift, lo, hi, n_sig, recall, lbl = row
            lines.append(
                f"  {combo_type}: {lbl} -> precision={prec*100:.1f}%, "
                f"lift={lift*100:+.1f}pp [CI: {lo*100:.1f}%-{hi*100:.1f}%], "
                f"n={n_sig} (recall={recall*100:.1f}%)"
            )

    # ── BABIP interaction ─────────────────────────────────────────────────────
    lines.append("\n--- BABIP INTERACTION (among whiff>=26 AND xwoba<=0.320 fires) ---")
    comp_mask = (blind["early_whiff_pct"] >= 0.26) & (blind["early_xwoba_contact"] <= 0.320)
    comp = blind[comp_mask]
    if len(comp) == 0:
        lines.append("  No composite-firing pitchers.")
    else:
        for lbl_b, sub_mask in [
            ("BABIP > 0.350", comp["early_babip"] > 0.350),
            ("BABIP <= 0.350", comp["early_babip"] <= 0.350),
        ]:
            sub = comp[sub_mask]
            n_sub = len(sub)
            if n_sub == 0:
                lines.append(f"  {lbl_b}: n=0")
                continue
            prec = sub["ros_success"].mean()
            lines.append(f"  Among composite-firing: {lbl_b}: success={prec*100:.1f}%, n={n_sub}")

    return lines


def main():
    rng = np.random.default_rng(RNG_SEED)
    output = []
    output.append("HARRISON COMPOSITE CALIBRATION")
    output.append("Monte Carlo Bootstrap Validation (10,000 iterations)")
    output.append(f"fp_proxy formula: (K - BB - H - HR) / BF  (per sp-breakout-signal calibration)")
    output.append(f"fp_proxy threshold: {FPP_THRESHOLD} (65th pctile, 2018-2025)")
    output.append(f"Early window: first {EARLY_GS} GS | Min total GS: {MIN_GS_TOTAL}")
    output.append(f"Training years: {TRAIN_YEARS} | Holdout: {HOLDOUT_YEAR}")
    output.append(f"RoS success = RoS fpp/bf >= {FPP_THRESHOLD}")

    print("=== Building training data ===")
    train_seasons = []
    for yr in TRAIN_YEARS:
        print(f"\nYear {yr}:")
        s = process_year(yr)
        train_seasons.append(s)

    train_all = pd.concat(train_seasons, ignore_index=True)
    output += analyze(train_all, f"TRAINING: {TRAIN_YEARS} (pooled)", rng)

    # Per-year summary in training
    output.append("\n\n--- PER-YEAR SUMMARY (training) ---")
    for yr in TRAIN_YEARS:
        yr_data = train_all[train_all["year"] == yr]
        blind = yr_data[yr_data["early_fpp_per_bf"] < FPP_THRESHOLD]
        if len(blind) == 0:
            output.append(f"\n{yr}: No fp_proxy-blind pitcher-seasons (n_all={len(yr_data)})")
            continue
        base = blind["ros_success"].mean()
        mask = (blind["early_whiff_pct"] >= 0.26) & (blind["early_xwoba_contact"] <= 0.320)
        n_sig = int(mask.sum())
        if n_sig > 0:
            prec, lo, hi = bootstrap_precision(blind.loc[mask, "ros_success"].values, rng=rng)
            lift = prec - base
            output.append(
                f"\n{yr}: blind n={len(blind)}, baseline={base*100:.1f}% | "
                f"whiff>=26 AND xwoba<=0.320: prec={prec*100:.1f}%, lift={lift*100:+.1f}pp "
                f"[CI:{lo*100:.1f}%-{hi*100:.1f}%], n={n_sig}"
            )
        else:
            output.append(
                f"\n{yr}: blind n={len(blind)}, baseline={base*100:.1f}% | "
                f"composite (whiff>=26 AND xwoba<=0.320): n=0 — no fires"
            )

    # Holdout
    print(f"\n=== Holdout: {HOLDOUT_YEAR} ===")
    holdout = process_year(HOLDOUT_YEAR)
    output += analyze(holdout, f"2025 HOLDOUT", rng)

    output.append("\n\n" + "=" * 70)
    output.append("METHODOLOGY NOTES")
    output.append("=" * 70)
    output.append("- SP identified as: pitcher with min inning = 1 AND >= 40 pitches in game.")
    output.append("- fp_proxy_per_bf = (K - BB - H - HR) / BF  (matches sp-breakout-signal calibration)")
    output.append("- whiff_pct = (swinging_strike + swinging_strike_blocked + foul_tip) / swings")
    output.append("- csw_pct = (swinging_strike variants + called_strike) / total_pitches")
    output.append("- xwoba_contact = sum(estimated_woba_using_speedangle WHERE launch_speed IS NOT NULL) / n_bip")
    output.append("- ev_mean = mean(launch_speed WHERE launch_speed IS NOT NULL)")
    output.append("- BABIP proxy = (H - HR) / (BF - K - BB - HR)")
    output.append("- Bootstrap: 10,000 resamplings of the signal-firing pool (with replacement)")
    output.append("- RoS = starts 7 through end of season (GS > 6)")

    result = "\n".join(output)
    print("\n" + result)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(result, encoding="utf-8")
    print(f"\n\nSaved: {OUT_FILE}")


if __name__ == "__main__":
    main()

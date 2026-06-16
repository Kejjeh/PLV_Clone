"""
Deep-dive bat-tracking research across ALL Savant leaderboards.
New datasets vs previous run:
  - bat_tracking main (bat speed, blast, swing length, swords)
  - swing_path / attack_angle (ideal_attack_angle_rate, intercept position)
  - pitch-type splits (FF fastball vs SL slider vs CH changeup timing)
  - pitcher-side swing path (where batters make contact AGAINST each SP)

Analyses:
  A. Metric stability (year-to-year r) — which metrics are stable enough to forecast?
  B. bat_speed / blast / swords → FP forward prediction
  C. attack_angle tier → FP (BrownU scoring penalizes too-flat or too-steep)
  D. ideal_attack_angle_rate → FP forward + quintile
  E. swords (bad-pitch Ks) → FP forward (BrownU penalty: K = −1 FP)
  F. swing_length (shorter = quicker = higher contact) → FP
  G. Interaction: bat_speed × lined_up% composite
  H. Pitch-type splits: late-on-fastball vs late-on-breaking-ball profiles
  I. Non-linear: bat_speed decile → FP (is there a floor threshold?)
  J. SP intercept position (pitcher-side) → FP/start forward
  K. Power-tier analysis: high-bat_speed hitters with poor timing — is power real?
  L. 2026 screens: breakout/decline using bat_speed + attack angle + swords YoY delta

Run:
    python -X utf8 scripts/xfp/research/swing_deep_dive.py
"""

import io, sys, warnings, time, concurrent.futures
import requests
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import cross_val_score

warnings.filterwarnings("ignore")

HEADERS = {"User-Agent": "Mozilla/5.0"}
HITTER_PANEL = "data/research/xfp_cache/hitters_multiyr_2015_2026.csv"
SP_PANEL     = "data/research/xfp_cache/sp_multiyr_2015_2025.csv"
YEARS = [2023, 2024, 2025, 2026]
H_MIN_PA  = 200
SP_MIN_GS = 8

# ── fetch helpers ────────────────────────────────────────────────────────────

def get(url, label=""):
    try:
        r = requests.get(url, timeout=30, headers=HEADERS)
        if r.status_code == 404:
            print(f"  [404] {label}")
            return pd.DataFrame()
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        return df
    except Exception as e:
        print(f"  [ERR] {label}: {e}")
        return pd.DataFrame()


def fetch_bat_tracking(player_type, year):
    url = (f"https://baseballsavant.mlb.com/leaderboard/bat-tracking"
           f"?gameType=Regular&minSwings=q&minGroupSwings=1"
           f"&seasonStart={year}&seasonEnd={year}&type={player_type}&csv=true")
    df = get(url, f"bat_tracking {player_type} {year}")
    if not df.empty:
        df["year"] = year
        df["player_type"] = player_type
        df.rename(columns={"id": "mlbam_id"}, inplace=True)
    return df


def fetch_attack_angle(player_type, year):
    url = (f"https://baseballsavant.mlb.com/leaderboard/bat-tracking/swing-path-attack-angle"
           f"?gameType=Regular&minSwings=q&minGroupSwings=1"
           f"&seasonStart={year}&seasonEnd={year}&type={player_type}&csv=true")
    df = get(url, f"attack_angle {player_type} {year}")
    if not df.empty:
        df["year"] = year
        df["player_type"] = player_type
        df.rename(columns={"id": "mlbam_id"}, inplace=True)
    return df


def fetch_timing(player_type, year):
    # timing leaderboard uses season[]= (different schema from bat-tracking main)
    url = (f"https://baseballsavant.mlb.com/leaderboard/bat-tracking/swing-timing-miss-distance"
           f"?type={player_type}&season[]={year}&min=50&csv=true")
    df = get(url, f"timing {player_type} {year}")
    if not df.empty:
        df["year"] = year
        df.rename(columns={"id": "mlbam_id"}, inplace=True)
    return df


def fetch_bat_tracking_pitch(player_type, year, pitch_code):
    """Bat-tracking metrics split by pitch type via pitchType= param."""
    url = (f"https://baseballsavant.mlb.com/leaderboard/bat-tracking"
           f"?gameType=Regular&minSwings=q&minGroupSwings=1"
           f"&seasonStart={year}&seasonEnd={year}&type={player_type}"
           f"&pitchType={pitch_code}&csv=true")
    df = get(url, f"bt_{player_type} {pitch_code} {year}")
    if not df.empty:
        df["year"] = year
        df["pitch_type"] = pitch_code
        df.rename(columns={"id": "mlbam_id"}, inplace=True)
    return df


def fetch_timing_by_pitch(player_type, year):
    """Swing timing/miss-distance split by individual pitch type.

    Uses split[]=api_pitch_type_group03 which returns one row per
    (player, pitch_type) with api_pitch_type column = FF/SL/CH etc.
    Confirmed working URL:
    /swing-timing-miss-distance?type=batter&season[]=2026&splitYear=1
      &min=1&split[]=api_pitch_type_group03&minSplit=1&gameType[]=R
    """
    url = (f"https://baseballsavant.mlb.com/leaderboard/bat-tracking/"
           f"swing-timing-miss-distance?type={player_type}"
           f"&season[]={year}&splitYear=1&min=1"
           f"&split[]=api_pitch_type_group03&minSplit=1&gameType[]=R&csv=true")
    df = get(url, f"timing_by_pt {player_type} {year}")
    if not df.empty:
        df["year"] = year
        df.rename(columns={"id": "mlbam_id"}, inplace=True)
    return df


# ── utility ──────────────────────────────────────────────────────────────────

def section(title):
    print(f"\n{'='*72}")
    print(f"  {title}")
    print(f"{'='*72}")


def corr(df, x, y, label=""):
    sub = df[[x, y]].dropna()
    if len(sub) < 15: return None
    pr, pp = stats.pearsonr(sub[x], sub[y])
    sr, _ = stats.spearmanr(sub[x], sub[y])
    sig = "***" if pp < 0.001 else ("**" if pp < 0.01 else ("*" if pp < 0.05 else "n.s."))
    return dict(x=x, y=y, n=len(sub), r=round(pr,3), rho=round(sr,3), p=round(pp,4), sig=sig, label=label)


def quintile_table(df, metric, target, q=5, ascending=False):
    sub = df[[metric, target]].dropna()
    if len(sub) < q*5: return None
    labels = [f"Q{i+1}" for i in range(q)]
    if ascending:
        labels[0] = f"Q1 (lowest {metric[:8]})"
        labels[-1] = f"Q5 (highest {metric[:8]})"
    else:
        labels[0] = f"Q1 (best)"
        labels[-1] = f"Q5 (worst)"
    sub = sub.copy()
    sub["q"] = pd.qcut(sub[metric], q, labels=labels)
    out = sub.groupby("q", observed=True)[target].agg(["mean","std","count"]).round(3)
    out.columns = [f"mean_{target[:8]}", f"std", "n"]
    spread = out[f"mean_{target[:8]}"].iloc[0] - out[f"mean_{target[:8]}"].iloc[-1]
    return out, round(spread, 4)


def yoy_corr(panel, metric, fp_col, panel_fp):
    """Year T metric → Year T+1 FP."""
    fwd = panel.merge(
        panel_fp[["mlbam_id","year","fp_next"]],
        left_on=["mlbam_id","year"], right_on=["mlbam_id","year_prev"],
        how="inner"
    )
    return corr(fwd, metric, "fp_next", label="T→T+1")


def build_fp_next(fp_df, id_col, fp_col):
    """Build T+1 lookup."""
    t1 = fp_df[[id_col,"year",fp_col]].copy()
    t1["year_prev"] = t1["year"] - 1
    t1 = t1.rename(columns={fp_col: "fp_next", "year": "year_next", id_col: "mlbam_id"})
    return t1[["mlbam_id","year_prev","fp_next"]]


# ── LOAD PANELS ──────────────────────────────────────────────────────────────

def load_panels():
    h = pd.read_csv(HITTER_PANEL)
    h = h[h["pa"] >= H_MIN_PA].copy()
    h["year"] = h["year"].astype(int)
    h.rename(columns={"batter": "mlbam_id"}, inplace=True)
    h["mlbam_id"] = h["mlbam_id"].astype(int)

    sp = pd.read_csv(SP_PANEL)
    sp = sp[sp["gs"] >= SP_MIN_GS].copy()
    sp["year"] = sp["year"].astype(int)
    sp.rename(columns={"pitcher": "mlbam_id"}, inplace=True)
    sp["mlbam_id"] = sp["mlbam_id"].astype(int)
    return h, sp


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Loading FP panels...")
    h_panel, sp_panel = load_panels()

    # FP next-year lookups
    h_fp_next  = build_fp_next(h_panel,  "mlbam_id", "fp_per_pa_actual")
    sp_fp_next = build_fp_next(sp_panel, "mlbam_id", "fp_per_start_actual")

    # ── FETCH ALL DATA IN PARALLEL ────────────────────────────────────────
    print("\nFetching Savant data (parallel)...")
    tasks = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        for yr in YEARS:
            tasks[f"bt_h_{yr}"]  = ex.submit(fetch_bat_tracking, "batter",  yr)
            tasks[f"bt_p_{yr}"]  = ex.submit(fetch_bat_tracking, "pitcher", yr)
            tasks[f"aa_h_{yr}"]  = ex.submit(fetch_attack_angle, "batter",  yr)
            tasks[f"aa_p_{yr}"]  = ex.submit(fetch_attack_angle, "pitcher", yr)
            tasks[f"tm_h_{yr}"]  = ex.submit(fetch_timing,       "batter",  yr)
        # pitch-type splits: bat-tracking main with pitchType= (multi-year)
        for pt in ["FF","SL","CH","CU","SI","FC","FS"]:
            for yr in YEARS:
                tasks[f"pt_h_{pt}_{yr}"] = ex.submit(fetch_bat_tracking_pitch, "batter",  yr, pt)
                tasks[f"pt_p_{pt}_{yr}"] = ex.submit(fetch_bat_tracking_pitch, "pitcher", yr, pt)
        # timing leaderboard split by pitch type (one row per player×pitch_type)
        for yr in YEARS:
            tasks[f"tm_pt_h_{yr}"] = ex.submit(fetch_timing_by_pitch, "batter",  yr)
            tasks[f"tm_pt_p_{yr}"] = ex.submit(fetch_timing_by_pitch, "pitcher", yr)

    results = {k: v.result() for k, v in tasks.items()}
    print(f"  Fetch complete.")

    def safe_concat(dfs):
        valid = [d for d in dfs if d is not None and not d.empty]
        return pd.concat(valid, ignore_index=True) if valid else pd.DataFrame()

    # Assemble panels
    bt_h  = safe_concat([results[f"bt_h_{yr}"]  for yr in YEARS])
    bt_p  = safe_concat([results[f"bt_p_{yr}"]  for yr in YEARS])
    aa_h  = safe_concat([results[f"aa_h_{yr}"]  for yr in YEARS])
    aa_p  = safe_concat([results[f"aa_p_{yr}"]  for yr in YEARS])
    tm_h  = safe_concat([results[f"tm_h_{yr}"]  for yr in YEARS])
    PT_CODES = ["FF","SL","CH","CU","SI","FC","FS"]
    pt_h_dfs = {pt: safe_concat([results[f"pt_h_{pt}_{yr}"] for yr in YEARS]) for pt in PT_CODES}
    pt_p_dfs = {pt: safe_concat([results[f"pt_p_{pt}_{yr}"] for yr in YEARS]) for pt in PT_CODES}
    tm_pt_h  = safe_concat([results[f"tm_pt_h_{yr}"] for yr in YEARS])
    tm_pt_p  = safe_concat([results[f"tm_pt_p_{yr}"] for yr in YEARS])

    for name, df in [("bat_tracking_h", bt_h), ("bat_tracking_p", bt_p),
                     ("attack_angle_h", aa_h), ("attack_angle_p", aa_p), ("timing_h", tm_h)]:
        print(f"  {name}: {len(df)} rows ({df['year'].nunique() if not df.empty else 0} years)")
    for pt, df in pt_h_dfs.items():
        if not df.empty:
            print(f"  bt_pitch_h_{pt}: {len(df)} rows ({df['year'].nunique()} years)")

    # Coerce numeric
    num_bt = ["avg_bat_speed","hard_swing_rate","squared_up_per_bat_contact","squared_up_per_swing",
              "blast_per_bat_contact","blast_per_swing","swing_length","swords","batter_run_value",
              "whiff_per_swing","batted_ball_event_per_swing","swings_competitive","contact"]
    num_aa = ["avg_bat_speed","swing_tilt","attack_angle","attack_direction","ideal_attack_angle_rate",
              "avg_intercept_y_vs_plate","avg_intercept_y_vs_batter","avg_batter_y_position","competitive_swings"]
    num_tm = ["miss_distance","perfect_percent","flawed_percent","on_time_percent","early_percent",
              "late_percent","whiff_rate","flailed_percent","centered_percent","lined_up_percent",
              "over_percent","under_percent","competitive_percent","n_swings"]
    for df in [bt_h, bt_p, aa_h, aa_p]:
        for c in num_bt + num_aa:
            if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce")
    for df in [tm_h]:
        for c in num_tm:
            if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce")

    # Force mlbam_id int
    for df in [bt_h, bt_p, aa_h, aa_p, tm_h]:
        if not df.empty and "mlbam_id" in df.columns:
            df["mlbam_id"] = pd.to_numeric(df["mlbam_id"], errors="coerce").astype("Int64")

    # ════════════════════════════════════════════════════════════════════════
    # A. METRIC STABILITY (year-to-year r)
    # ════════════════════════════════════════════════════════════════════════
    section("A.  METRIC STABILITY  (year-to-year Pearson r, paired players)")

    def stability_panel(df, metrics):
        rows = []
        for yr in sorted(df["year"].unique()):
            prev_yr = yr - 1
            prev = df[df["year"] == prev_yr][["mlbam_id"] + [m for m in metrics if m in df.columns]]
            curr = df[df["year"] == yr][["mlbam_id"] + [m for m in metrics if m in df.columns]]
            if prev.empty or curr.empty: continue
            joined = prev.merge(curr, on="mlbam_id", suffixes=("_t0","_t1"))
            for m in metrics:
                if f"{m}_t0" in joined.columns and f"{m}_t1" in joined.columns:
                    sub = joined[[f"{m}_t0",f"{m}_t1"]].dropna()
                    if len(sub) < 20: continue
                    pr, _ = stats.pearsonr(sub[f"{m}_t0"], sub[f"{m}_t1"])
                    rows.append({"metric": m, "yr_pair": f"{prev_yr}→{yr}", "n": len(sub), "r": round(pr,3)})
        return pd.DataFrame(rows)

    bt_metrics = ["avg_bat_speed","hard_swing_rate","blast_per_swing","swing_length",
                  "swords","whiff_per_swing","squared_up_per_swing"]
    aa_metrics = ["attack_angle","swing_tilt","ideal_attack_angle_rate","avg_intercept_y_vs_plate"]
    tm_metrics = ["whiff_rate","perfect_percent","lined_up_percent","on_time_percent",
                  "miss_distance","flailed_percent"]

    print("\n  Bat-tracking stability:")
    stab_bt = stability_panel(bt_h, bt_metrics)
    if not stab_bt.empty:
        print(stab_bt.pivot(index="metric", columns="yr_pair", values="r").round(3).to_string())

    print("\n  Attack-angle stability:")
    stab_aa = stability_panel(aa_h, aa_metrics)
    if not stab_aa.empty:
        print(stab_aa.pivot(index="metric", columns="yr_pair", values="r").round(3).to_string())

    print("\n  Timing/miss stability:")
    stab_tm = stability_panel(tm_h, tm_metrics)
    if not stab_tm.empty:
        print(stab_tm.pivot(index="metric", columns="yr_pair", values="r").round(3).to_string())

    # ════════════════════════════════════════════════════════════════════════
    # B. BAT SPEED + BLAST + SWORDS → FP (same-year + forward)
    # ════════════════════════════════════════════════════════════════════════
    section("B.  BAT SPEED / BLAST / SWORDS → FP/PA  (same-year + T→T+1)")

    bt_joined = bt_h.merge(
        h_panel[["mlbam_id","year","fp_per_pa_actual","k_pct","xwoba_per_pa","pa"]],
        on=["mlbam_id","year"], how="inner"
    )
    # Compute derived columns before subsetting so slices inherit them
    if "swords" in bt_joined.columns and "swings_competitive" in bt_joined.columns:
        bt_joined["swords_rate"] = bt_joined["swords"] / bt_joined["swings_competitive"].clip(lower=1)
    bt_joined_pool = bt_joined[bt_joined["year"] < 2026].copy()
    print(f"\n  Bat-tracking joined (hitters): {len(bt_joined)} rows  "
          f"({len(bt_joined_pool)} excl. 2026)")

    bt_targets = ["avg_bat_speed","hard_swing_rate","blast_per_swing","swing_length",
                  "swords","whiff_per_swing","squared_up_per_swing","batter_run_value"]

    print("\n  SAME-YEAR correlations vs fp_per_pa_actual:")
    rows = [r for m in bt_targets if (r := corr(bt_joined_pool, m, "fp_per_pa_actual", "same-yr")) is not None]
    print(pd.DataFrame(rows)[["x","n","r","rho","sig"]].sort_values("r", key=abs, ascending=False).to_string(index=False))

    # Forward T→T+1
    bt_fwd = bt_joined.merge(h_fp_next, left_on=["mlbam_id","year"], right_on=["mlbam_id","year_prev"], how="inner")
    bt_fwd = bt_fwd[bt_fwd["year"] < 2026]
    print(f"\n  FORWARD T→T+1 ({len(bt_fwd)} pairs):")
    rows_fwd = [r for m in bt_targets if (r := corr(bt_fwd, m, "fp_next", "T→T+1")) is not None]
    print(pd.DataFrame(rows_fwd)[["x","n","r","rho","sig"]].sort_values("r", key=abs, ascending=False).to_string(index=False))

    # ════════════════════════════════════════════════════════════════════════
    # C. ATTACK ANGLE TIER → FP  (BrownU optimal zone)
    # ════════════════════════════════════════════════════════════════════════
    section("C.  ATTACK ANGLE TIER → FP/PA  (is there a sweet spot?)")

    aa_joined = aa_h.merge(
        h_panel[["mlbam_id","year","fp_per_pa_actual","pa"]],
        on=["mlbam_id","year"], how="inner"
    )
    aa_pool = aa_joined[aa_joined["year"] < 2026]
    print(f"\n  Attack angle joined: {len(aa_joined)} rows")

    # Non-linear: bin attack_angle (0-5, 5-10, 10-15, 15-20, 20-25, 25+)
    if "attack_angle" in aa_pool.columns and "fp_per_pa_actual" in aa_pool.columns:
        sub = aa_pool[["attack_angle","fp_per_pa_actual","ideal_attack_angle_rate"]].dropna()
        bins = [0, 4, 8, 12, 16, 20, 99]
        labels_b = ["0-4°","4-8°","8-12°","12-16°","16-20°","20°+"]
        sub["aa_bin"] = pd.cut(sub["attack_angle"], bins=bins, labels=labels_b, right=False)
        print("\n  Attack angle bin → avg FP/PA (same year):")
        print(sub.groupby("aa_bin", observed=True)["fp_per_pa_actual"].agg(["mean","count"]).round(3).to_string())

    # Correlations
    aa_metrics_test = ["attack_angle","swing_tilt","ideal_attack_angle_rate","avg_intercept_y_vs_plate"]
    rows_aa = [r for m in aa_metrics_test if (r := corr(aa_pool, m, "fp_per_pa_actual", "same-yr")) is not None]
    print("\n  Correlations vs fp_per_pa_actual:")
    print(pd.DataFrame(rows_aa)[["x","n","r","rho","sig"]].sort_values("r", key=abs, ascending=False).to_string(index=False))

    # Forward
    aa_fwd = aa_joined.merge(h_fp_next, left_on=["mlbam_id","year"], right_on=["mlbam_id","year_prev"], how="inner")
    aa_fwd = aa_fwd[aa_fwd["year"] < 2026]
    rows_aa_fwd = [r for m in aa_metrics_test if (r := corr(aa_fwd, m, "fp_next", "T→T+1")) is not None]
    print(f"\n  Forward T→T+1 ({len(aa_fwd)} pairs):")
    print(pd.DataFrame(rows_aa_fwd)[["x","n","r","rho","sig"]].sort_values("r", key=abs, ascending=False).to_string(index=False))

    # ════════════════════════════════════════════════════════════════════════
    # D. IDEAL ATTACK ANGLE RATE QUINTILE → FP NEXT YEAR
    # ════════════════════════════════════════════════════════════════════════
    section("D.  ideal_attack_angle_rate QUINTILE → avg FP/PA T+1")
    if not aa_fwd.empty and "ideal_attack_angle_rate" in aa_fwd.columns:
        result = quintile_table(aa_fwd, "ideal_attack_angle_rate", "fp_next")
        if result:
            tbl, spread = result
            print(tbl.to_string())
            print(f"  Q1 vs Q5 spread: {spread:+.4f} FP/PA")

    # ════════════════════════════════════════════════════════════════════════
    # E. SWORDS → FP  (BrownU K-penalty amplifies this signal)
    # ════════════════════════════════════════════════════════════════════════
    section("E.  SWORDS (bad-pitch Ks) → FP/PA  —  BrownU K penalty amplifier")
    print("  'swords' = swings at pitches outside competitive zone that result in strikeouts")
    print("  BrownU: K = -1 FP, so swords is a direct FP tax on top of the miss signal.\n")

    if "swords_rate" in bt_joined_pool.columns:
        # swords_rate already computed above; propagate to fwd panel
        if "swords_rate" not in bt_fwd.columns and "swords" in bt_fwd.columns:
            bt_fwd["swords_rate"] = bt_fwd["swords"] / bt_fwd["swings_competitive"].clip(lower=1)

        r_same = corr(bt_joined_pool, "swords_rate", "fp_per_pa_actual", "same-yr")
        r_fwd  = corr(bt_fwd,         "swords_rate", "fp_next",          "T→T+1")
        r_k    = corr(bt_joined_pool, "swords_rate", "k_pct",            "→K%")
        for r in [r_same, r_fwd, r_k]:
            if r: print(f"  swords_rate {r['label']:10s}: r={r['r']:.3f}  rho={r['rho']:.3f}  {r['sig']}")

        print("\n  swords_rate quintile → FP/PA same year:")
        result = quintile_table(bt_joined_pool, "swords_rate", "fp_per_pa_actual", ascending=True)
        if result:
            tbl, spread = result
            print(tbl.to_string())
            print(f"  Low-swords vs high-swords: {spread:+.4f} FP/PA")

    # ════════════════════════════════════════════════════════════════════════
    # F. SWING LENGTH → FP  (shorter = quicker = better zone coverage)
    # ════════════════════════════════════════════════════════════════════════
    section("F.  SWING LENGTH → FP  (shorter swing = faster bat path = better contact)")
    if "swing_length" in bt_joined.columns:
        r_same = corr(bt_joined_pool, "swing_length", "fp_per_pa_actual", "same-yr")
        r_fwd  = corr(bt_fwd,         "swing_length", "fp_next",          "T→T+1")
        r_k    = corr(bt_joined_pool, "swing_length", "k_pct",            "→K%")
        for r in [r_same, r_fwd, r_k]:
            if r: print(f"  swing_length {r['label']:10s}: r={r['r']:.3f}  rho={r['rho']:.3f}  {r['sig']}")

        print("\n  swing_length quintile → FP/PA T+1 (forward):")
        if not bt_fwd.empty:
            result = quintile_table(bt_fwd, "swing_length", "fp_next", ascending=True)
            if result:
                tbl, spread = result
                print(tbl.to_string())
                print(f"  Short-swing vs long-swing forward spread: {spread:+.4f} FP/PA")

    # ════════════════════════════════════════════════════════════════════════
    # G. INTERACTION: bat_speed × lined_up_percent → FP
    # ════════════════════════════════════════════════════════════════════════
    section("G.  INTERACTION: bat_speed × lined_up% composite → FP")
    bt_tm = bt_joined.merge(
        tm_h[["mlbam_id","year","lined_up_percent","whiff_rate","perfect_percent"]],
        on=["mlbam_id","year"], how="inner"
    )
    bt_tm_pool = bt_tm[bt_tm["year"] < 2026]
    if len(bt_tm_pool) >= 30 and "avg_bat_speed" in bt_tm_pool.columns:
        bt_tm_pool = bt_tm_pool.copy()
        bt_tm_pool["speed_contact_score"] = (
            bt_tm_pool["avg_bat_speed"].rank(pct=True) +
            bt_tm_pool["lined_up_percent"].rank(pct=True) -
            bt_tm_pool["whiff_rate"].rank(pct=True)
        ) / 3
        r = corr(bt_tm_pool, "speed_contact_score", "fp_per_pa_actual", "composite")
        if r: print(f"  speed_contact_score → FP/PA: r={r['r']:.3f}  {r['sig']}  (n={r['n']})")

        # vs individual components
        for m in ["avg_bat_speed","lined_up_percent","whiff_rate"]:
            rc = corr(bt_tm_pool, m, "fp_per_pa_actual", m)
            if rc: print(f"  {m:<25s} → FP/PA: r={rc['r']:.3f}  {rc['sig']}")

    # ════════════════════════════════════════════════════════════════════════
    # H. PITCH-TYPE SPLITS: bat speed / blast / swords by pitch type
    # ════════════════════════════════════════════════════════════════════════
    section("H.  PITCH-TYPE SPLITS: blast/swords by pitch type → FP  (bat-tracking main)")
    print("  pitchType= param confirmed working. FF/SL/CH/CU/SI/FC/FS.")
    print("  Key questions: does blast_FF vs blast_SL carry different FP signal?")
    print("  Does swords_SL (breaking-ball chases) predict K%/FP better than overall swords?\n")

    PT_METRICS = ["avg_bat_speed","blast_per_swing","swords","hard_swing_rate","squared_up_per_swing"]

    # --- H1. Same-year correlation by pitch type (pooled multi-year) ---
    print("  H1. Same-year r(pitch-type metric, FP/PA) — pooled 2023-2025:")
    pt_corr_rows = []
    for pt, pt_df in pt_h_dfs.items():
        if pt_df.empty: continue
        merged = pt_df.merge(
            h_panel[["mlbam_id","year","fp_per_pa_actual","k_pct"]],
            on=["mlbam_id","year"], how="inner"
        )
        merged = merged[merged["year"] < 2026]
        for m in PT_METRICS:
            if m not in merged.columns: continue
            rc = corr(merged, m, "fp_per_pa_actual", pt)
            if rc:
                rc["pitch"] = pt
                rc["metric"] = m
                pt_corr_rows.append(rc)

    if pt_corr_rows:
        pt_tbl = pd.DataFrame(pt_corr_rows)
        pivot = pt_tbl.pivot_table(index="metric", columns="pitch", values="r", aggfunc="first").round(3)
        print(pivot.to_string())

    # --- H2. Forward T→T+1 by pitch type ---
    print("\n  H2. Forward r(pitch-type metric T, FP/PA T+1):")
    pt_fwd_rows = []
    for pt, pt_df in pt_h_dfs.items():
        if pt_df.empty: continue
        merged = pt_df.merge(
            h_panel[["mlbam_id","year","fp_per_pa_actual","k_pct"]],
            on=["mlbam_id","year"], how="inner"
        )
        merged_fwd = merged.merge(h_fp_next,
            left_on=["mlbam_id","year"], right_on=["mlbam_id","year_prev"], how="inner")
        merged_fwd = merged_fwd[merged_fwd["year"] < 2026]
        for m in PT_METRICS:
            if m not in merged_fwd.columns: continue
            rc = corr(merged_fwd, m, "fp_next", pt)
            if rc:
                rc["pitch"] = pt
                rc["metric"] = m
                pt_fwd_rows.append(rc)

    if pt_fwd_rows:
        pt_fwd_tbl = pd.DataFrame(pt_fwd_rows)
        pivot_fwd = pt_fwd_tbl.pivot_table(index="metric", columns="pitch", values="r", aggfunc="first").round(3)
        print(pivot_fwd.to_string())

    # --- H3. Wide-format: blast_FF - blast_SL as a "FB dominance" feature ---
    print("\n  H3. blast_FF − blast_SL gap → FP (does FB-specific contact add signal?)")
    if not pt_h_dfs.get("FF", pd.DataFrame()).empty and not pt_h_dfs.get("SL", pd.DataFrame()).empty:
        ff_df = pt_h_dfs["FF"][["mlbam_id","year","blast_per_swing","avg_bat_speed","swords"]].rename(
            columns={"blast_per_swing":"blast_FF","avg_bat_speed":"spd_FF","swords":"swords_FF"})
        sl_df = pt_h_dfs["SL"][["mlbam_id","year","blast_per_swing","swords"]].rename(
            columns={"blast_per_swing":"blast_SL","swords":"swords_SL"})
        cu_df = pt_h_dfs.get("CU", pd.DataFrame())
        wide = ff_df.merge(sl_df, on=["mlbam_id","year"], how="inner")
        if not cu_df.empty:
            cu_sub = cu_df[["mlbam_id","year","swords"]].rename(columns={"swords":"swords_CU"})
            wide = wide.merge(cu_sub, on=["mlbam_id","year"], how="left")
        wide = wide.merge(
            h_panel[["mlbam_id","year","fp_per_pa_actual","k_pct"]], on=["mlbam_id","year"], how="inner")
        wide_pool = wide[wide["year"] < 2026].copy()
        wide_pool["blast_FF_minus_SL"] = wide_pool["blast_FF"] - wide_pool["blast_SL"]
        wide_pool["swords_breaking"] = wide_pool["swords_SL"] + wide_pool.get("swords_CU", 0).fillna(0)

        wide_fwd = wide.merge(h_fp_next, left_on=["mlbam_id","year"], right_on=["mlbam_id","year_prev"], how="inner")
        wide_fwd = wide_fwd[wide_fwd["year"] < 2026].copy()
        wide_fwd["blast_FF_minus_SL"] = wide_fwd["blast_FF"] - wide_fwd["blast_SL"]
        wide_fwd["swords_breaking"] = wide_fwd["swords_SL"] + wide_fwd.get("swords_CU", 0).fillna(0)

        print(f"  Wide panel (FF × SL joined): {len(wide_pool)} rows (pool) / {len(wide_fwd)} (forward)")
        for feat, label in [
            ("blast_FF",         "blast_FF alone   "),
            ("blast_SL",         "blast_SL alone   "),
            ("blast_FF_minus_SL","blast_FF − blast_SL"),
            ("swords_FF",        "swords_FF (FB chases)"),
            ("swords_SL",        "swords_SL (SL chases)"),
            ("swords_breaking",  "swords_SL+CU combined"),
        ]:
            if feat not in wide_pool.columns: continue
            rs = corr(wide_pool, feat, "fp_per_pa_actual", "same-yr")
            rf = corr(wide_fwd,  feat, "fp_next",          "T→T+1")
            rs_str = f"r={rs['r']:+.3f} {rs['sig']}" if rs else "n/a"
            rf_str = f"r={rf['r']:+.3f} {rf['sig']}" if rf else "n/a"
            print(f"  {label:<24s}  same-yr {rs_str:<16}  fwd {rf_str}")

    # --- H4. SP side: which pitch type blast/swords predicts SP FP best? ---
    print("\n  H4. SP induced: pitch-type blast/swords → SP FP/start (forward):")
    sp_pt_rows = []
    for pt, pt_df in pt_p_dfs.items():
        if pt_df.empty: continue
        merged = pt_df.merge(
            sp_panel[["mlbam_id","year","fp_per_start_actual"]], on=["mlbam_id","year"], how="inner")
        fwd = merged.merge(sp_fp_next,
            left_on=["mlbam_id","year"], right_on=["mlbam_id","year_prev"], how="inner")
        fwd = fwd[fwd["year"] < 2026]
        for m in ["blast_per_swing","avg_bat_speed","swords","hard_swing_rate"]:
            if m not in fwd.columns: continue
            rc = corr(fwd, m, "fp_next", pt)
            if rc:
                rc["pitch"] = pt
                rc["metric"] = m
                sp_pt_rows.append(rc)

    if sp_pt_rows:
        sp_pt_tbl = pd.DataFrame(sp_pt_rows)
        print(sp_pt_tbl.pivot_table(index="metric", columns="pitch", values="r", aggfunc="first").round(3).to_string())

    # ════════════════════════════════════════════════════════════════════════
    # H5. TIMING BY PITCH TYPE (swing-timing-miss-distance + api_pitch_type_group03)
    # ════════════════════════════════════════════════════════════════════════
    section("H5. SWING TIMING split by pitch type  (lined_up% / whiff_rate per PT)")
    print("  Source: swing-timing-miss-distance leaderboard with split[]=api_pitch_type_group03")
    print("  Returns one row per (player × api_pitch_type) — FF/SL/CH/CU/SI etc.\n")

    # Coerce timing columns
    TM_METRICS = ["whiff_rate","lined_up_percent","perfect_percent","on_time_percent",
                  "late_percent","early_percent","miss_distance","flailed_percent"]
    for df in [tm_pt_h, tm_pt_p]:
        if df.empty: continue
        for c in TM_METRICS + ["n_swings"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        if "mlbam_id" in df.columns:
            df["mlbam_id"] = pd.to_numeric(df["mlbam_id"], errors="coerce").astype("Int64")

    MAIN_PT = ["FF","SL","CH","CU","SI"]
    PT_TIMING_METRICS = ["whiff_rate","lined_up_percent","miss_distance","perfect_percent","on_time_percent"]

    def run_timing_pt_analysis(tm_df, fp_df, fp_next_df, fp_col, fp_next_col, label):
        """Per-pitch-type timing correlations: iterate pitch types, join, compute r."""
        if tm_df.empty or "api_pitch_type" not in tm_df.columns:
            print(f"  {label}: no data"); return []

        # coerce numerics
        tm_df = tm_df.copy()
        for c in PT_TIMING_METRICS + ["n_swings"]:
            if c in tm_df.columns:
                tm_df[c] = pd.to_numeric(tm_df[c], errors="coerce")
        tm_df["mlbam_id"] = pd.to_numeric(tm_df["mlbam_id"], errors="coerce").astype(int)

        all_rows = []
        fwd_rows = []
        gap_data = {}  # pitch_type → {metric: series} for gap analysis

        for pt_val in MAIN_PT:
            sub = tm_df[tm_df["api_pitch_type"] == pt_val].copy()
            if sub.empty: continue

            # same-year join
            merged = sub.merge(fp_df, on=["mlbam_id","year"], how="inner")
            merged_pool = merged[merged["year"] < 2026]

            # forward join
            merged_fwd = merged.merge(
                fp_next_df, left_on=["mlbam_id","year"], right_on=["mlbam_id","year_prev"], how="inner")
            merged_fwd = merged_fwd[merged_fwd["year"] < 2026]

            gap_data[pt_val] = merged_pool

            for m in PT_TIMING_METRICS:
                if m not in merged_pool.columns: continue
                col_name = f"{m}_{pt_val}"
                rs = corr(merged_pool, m, fp_col,      f"{pt_val} same")
                rf = corr(merged_fwd,  m, fp_next_col, f"{pt_val} fwd")
                if rs: rs["metric_pt"] = col_name; all_rows.append(rs)
                if rf: rf["metric_pt"] = col_name; fwd_rows.append(rf)

        print(f"\n  {label} — same-year r by pitch type:")
        if all_rows:
            t = pd.DataFrame(all_rows)
            t["metric"] = t["metric_pt"].str.rsplit("_", n=1).str[0]
            t["pt"]     = t["metric_pt"].str.rsplit("_", n=1).str[1]
            pivot_s = t.pivot_table(index="metric", columns="pt", values="r", aggfunc="first").round(3)
            print(pivot_s.to_string())

        print(f"\n  {label} — forward T→T+1 r by pitch type (ranked):")
        if fwd_rows:
            tf = pd.DataFrame(fwd_rows).sort_values("r", key=abs, ascending=False)
            print(tf[["metric_pt","n","r","rho","sig"]].head(15).to_string(index=False))

        # FF vs SL gap (same-year, needs both)
        if "FF" in gap_data and "SL" in gap_data:
            print(f"\n  {label} — FF vs SL metric gap → {fp_col}:")
            ff_df2 = gap_data["FF"][["mlbam_id","year"] + [m for m in PT_TIMING_METRICS if m in gap_data["FF"].columns]]
            sl_df2 = gap_data["SL"][["mlbam_id","year"] + [m for m in PT_TIMING_METRICS if m in gap_data["SL"].columns]]
            merged_gap = ff_df2.merge(sl_df2, on=["mlbam_id","year"], suffixes=("_FF","_SL"), how="inner")
            merged_gap = merged_gap.merge(fp_df, on=["mlbam_id","year"], how="inner")
            for base in ["whiff_rate","lined_up_percent","miss_distance"]:
                fc, sc = f"{base}_FF", f"{base}_SL"
                if fc in merged_gap.columns and sc in merged_gap.columns:
                    merged_gap[f"{base}_gap"] = merged_gap[fc] - merged_gap[sc]
                    rc = corr(merged_gap, f"{base}_gap", fp_col, "FF−SL gap")
                    if rc: print(f"    {base}_FF−SL: r={rc['r']:+.3f} {rc['sig']}  (n={rc['n']})")

        return fwd_rows

    print(f"  Hitter timing-by-pitch: {len(tm_pt_h)} rows | "
          f"pitch types: {sorted(tm_pt_h['api_pitch_type'].dropna().unique()) if not tm_pt_h.empty else []}")
    print(f"  SP timing-by-pitch:     {len(tm_pt_p)} rows")

    h_panel_int = h_panel.copy()
    h_panel_int["mlbam_id"] = h_panel_int["mlbam_id"].astype(int)
    h_fp_next_int = h_fp_next.copy()
    h_fp_next_int["mlbam_id"] = h_fp_next_int["mlbam_id"].astype(int)
    sp_panel_int = sp_panel.copy()
    sp_panel_int["mlbam_id"] = sp_panel_int["mlbam_id"].astype(int)
    sp_fp_next_int = sp_fp_next.copy()
    sp_fp_next_int["mlbam_id"] = sp_fp_next_int["mlbam_id"].astype(int)

    run_timing_pt_analysis(
        tm_pt_h,
        h_panel_int[["mlbam_id","year","fp_per_pa_actual","k_pct"]],
        h_fp_next_int, "fp_per_pa_actual", "fp_next",
        "H5a HITTER timing by pitch type"
    )
    run_timing_pt_analysis(
        tm_pt_p,
        sp_panel_int[["mlbam_id","year","fp_per_start_actual"]],
        sp_fp_next_int, "fp_per_start_actual", "fp_next",
        "H5c SP timing by pitch type (induced)"
    )

    # ════════════════════════════════════════════════════════════════════════
    # I. NON-LINEAR: bat_speed DECILE → FP (floor threshold?)
    # ════════════════════════════════════════════════════════════════════════
    section("I.  NON-LINEAR: bat_speed decile → FP/PA  (is there a <65 mph floor?)")
    if "avg_bat_speed" in bt_joined_pool.columns:
        sub = bt_joined_pool[["avg_bat_speed","fp_per_pa_actual"]].dropna()
        sub = sub.copy()
        sub["decile"] = pd.qcut(sub["avg_bat_speed"], 10,
                                labels=[f"D{i+1}" for i in range(10)])
        print("\n  bat_speed decile → avg FP/PA (same year, pooled 2023-2025):")
        print(sub.groupby("decile", observed=True)["fp_per_pa_actual"].agg(
            avg_bat_speed_approx=lambda x: sub.loc[x.index,"avg_bat_speed"].mean(),
            mean_fp=("mean"), n=("count")).round(3).to_string())

    # ════════════════════════════════════════════════════════════════════════
    # J. SP: intercept position (pitcher-side) → FP/start
    # ════════════════════════════════════════════════════════════════════════
    section("J.  SP INTERCEPT POSITION (pitcher-side) → FP/start forward")

    aa_p_joined = aa_p.merge(
        sp_panel[["mlbam_id","year","fp_per_start_actual","k_pct","gs"]],
        on=["mlbam_id","year"], how="inner"
    )
    aa_p_pool = aa_p_joined[aa_p_joined["year"] < 2026]
    print(f"\n  SP attack-angle joined: {len(aa_p_joined)} rows")

    sp_aa_metrics = ["attack_angle","ideal_attack_angle_rate","avg_intercept_y_vs_plate",
                     "avg_intercept_y_vs_batter","swing_tilt","attack_direction"]
    rows_sp = [r for m in sp_aa_metrics if m in aa_p_pool.columns
               if (r := corr(aa_p_pool, m, "fp_per_start_actual", "same-yr")) is not None]
    print("\n  SAME-YEAR (batters-against metrics → SP FP/start):")
    if rows_sp:
        print(pd.DataFrame(rows_sp)[["x","n","r","rho","sig"]].sort_values("r",key=abs,ascending=False).to_string(index=False))

    aa_p_fwd = aa_p_joined.merge(sp_fp_next, left_on=["mlbam_id","year"], right_on=["mlbam_id","year_prev"], how="inner")
    aa_p_fwd = aa_p_fwd[aa_p_fwd["year"] < 2026]
    rows_sp_fwd = [r for m in sp_aa_metrics if m in aa_p_fwd.columns
                   if (r := corr(aa_p_fwd, m, "fp_next", "T→T+1")) is not None]
    print(f"\n  FORWARD T→T+1 ({len(aa_p_fwd)} pairs):")
    if rows_sp_fwd:
        print(pd.DataFrame(rows_sp_fwd)[["x","n","r","rho","sig"]].sort_values("r",key=abs,ascending=False).to_string(index=False))

    # Quintile: avg_intercept_y_vs_plate → SP FP next year
    if "avg_intercept_y_vs_plate" in aa_p_fwd.columns:
        print("\n  avg_intercept_y_vs_plate quintile → FP/start T+1:")
        result = quintile_table(aa_p_fwd, "avg_intercept_y_vs_plate", "fp_next", ascending=True)
        if result:
            tbl, spread = result
            print(tbl.to_string())
            print(f"  Spread: {spread:+.3f} FP/start")

    # ════════════════════════════════════════════════════════════════════════
    # K. POWER-TIER ANALYSIS: high bat speed hitters with poor timing
    # ════════════════════════════════════════════════════════════════════════
    section("K.  POWER-TIER: fast-bat hitters with poor contact metrics  (2026)")
    print("  Question: do power hitters with bad timing still produce in BrownU scoring?")

    if not bt_tm_pool.empty and "avg_bat_speed" in bt_tm_pool.columns:
        sub = bt_tm_pool[["mlbam_id","avg_bat_speed","lined_up_percent","whiff_rate",
                           "fp_per_pa_actual","k_pct"]].dropna()
        # Split by bat speed tier (top/bottom half)
        med_speed = sub["avg_bat_speed"].median()
        for tier, mask, label in [
            (1, sub["avg_bat_speed"] >= med_speed, f"Fast bat (≥{med_speed:.1f} mph)"),
            (0, sub["avg_bat_speed"] < med_speed,  f"Slow bat (<{med_speed:.1f} mph)")
        ]:
            seg = sub[mask]
            r_lined = corr(seg, "lined_up_percent", "fp_per_pa_actual", label)
            r_whiff = corr(seg, "whiff_rate",       "fp_per_pa_actual", label)
            print(f"\n  [{label}] n={len(seg)}")
            if r_lined: print(f"    lined_up% → FP: r={r_lined['r']:.3f} {r_lined['sig']}")
            if r_whiff: print(f"    whiff_rate → FP: r={r_whiff['r']:.3f} {r_whiff['sig']}")

    # ════════════════════════════════════════════════════════════════════════
    # L. 2026 SCREENS: YoY changes bat speed + attack angle + swords
    # ════════════════════════════════════════════════════════════════════════
    section("L.  2026 SCREENS  — YoY delta bat_speed + ideal_attack_angle + swords")

    bt_26 = bt_h[bt_h["year"]==2026][["mlbam_id","name","avg_bat_speed","blast_per_swing",
                                       "swords","hard_swing_rate","swing_length","swings_competitive"]].copy()
    bt_25 = bt_h[bt_h["year"]==2025][["mlbam_id","avg_bat_speed","blast_per_swing",
                                       "swords","hard_swing_rate","swing_length","swings_competitive"]].copy()
    aa_26 = aa_h[aa_h["year"]==2026][["mlbam_id","ideal_attack_angle_rate","attack_angle","avg_intercept_y_vs_plate"]].copy()
    aa_25 = aa_h[aa_h["year"]==2025][["mlbam_id","ideal_attack_angle_rate","attack_angle"]].copy()

    delta = bt_26.merge(bt_25, on="mlbam_id", suffixes=("_26","_25"), how="inner")
    delta = delta.merge(aa_26, on="mlbam_id", how="left")
    delta = delta.merge(aa_25, on="mlbam_id", suffixes=("","_25"), how="left")
    delta = delta.merge(
        h_panel[h_panel["year"]==2026][["mlbam_id","fp_per_pa_actual","pa","xwoba_per_pa"]],
        on="mlbam_id", how="left"
    )

    delta["d_bat_speed"]    = delta["avg_bat_speed_26"] - delta["avg_bat_speed_25"]
    delta["d_blast"]        = delta["blast_per_swing_26"] - delta["blast_per_swing_25"]
    delta["swords_rate_26"] = delta["swords_26"] / delta["swings_competitive_26"].clip(lower=1)
    delta["swords_rate_25"] = delta["swords_25"] / delta["swings_competitive_25"].clip(lower=1)
    delta["d_swords"]       = delta["swords_rate_26"] - delta["swords_rate_25"]
    delta["d_ideal_aa"]     = delta.get("ideal_attack_angle_rate","") - delta.get("ideal_attack_angle_rate_25","") \
                              if "ideal_attack_angle_rate_25" in delta.columns else 0

    name_col = "name_26" if "name_26" in delta.columns else "name"
    show = [c for c in [name_col,"d_bat_speed","d_blast","d_swords","d_ideal_aa",
                        "avg_bat_speed_26","fp_per_pa_actual","pa"] if c in delta.columns]

    delta["breakout_score"] = (
        delta["d_bat_speed"].rank(pct=True) +
        delta["d_blast"].rank(pct=True) -
        delta["d_swords"].rank(pct=True)
    ) / 3
    delta["decline_score"] = (
        -delta["d_bat_speed"].rank(pct=True) -
        delta["d_blast"].rank(pct=True) +
        delta["d_swords"].rank(pct=True)
    ) / 3

    min_pa = 100
    delta_filtered = delta[delta["pa"].fillna(0) >= min_pa]

    print(f"\n  Delta panel: {len(delta)} players  ({len(delta_filtered)} with ≥{min_pa} PA)")
    print(f"\n  TOP BREAKOUT (rising bat speed + blast, falling swords rate):")
    print(delta_filtered.nlargest(15, "breakout_score")[show].round(4).to_string(index=False))

    print(f"\n  TOP DECLINE (falling bat speed + blast, rising swords rate):")
    print(delta_filtered.nlargest(15, "decline_score")[show].round(4).to_string(index=False))

    # ════════════════════════════════════════════════════════════════════════
    # M. SP BAT SPEED INDUCED: does pitcher bat-tracking data predict FP?
    # ════════════════════════════════════════════════════════════════════════
    section("M.  SP INDUCED BAT SPEED (pitcher-side bat tracking) → FP/start")
    print("  Pitcher-side bat tracking shows what batters swing like AGAINST each pitcher.")
    print("  Lower avg_bat_speed induced = pitcher limits bat speed = harder pitches/deception.\n")

    bt_p_joined = bt_p.merge(
        sp_panel[["mlbam_id","year","fp_per_start_actual","k_pct","gs"]],
        on=["mlbam_id","year"], how="inner"
    )
    bt_p_pool = bt_p_joined[bt_p_joined["year"] < 2026]
    print(f"  SP bat-tracking joined: {len(bt_p_joined)} rows")

    sp_bt_metrics = ["avg_bat_speed","hard_swing_rate","blast_per_swing","swing_length",
                     "swords","whiff_per_swing","batter_run_value"]
    rows_sp_bt = [r for m in sp_bt_metrics if m in bt_p_pool.columns
                  if (r := corr(bt_p_pool, m, "fp_per_start_actual", "same-yr")) is not None]
    print("\n  SAME-YEAR (induced bat mechanics → SP FP/start):")
    if rows_sp_bt:
        print(pd.DataFrame(rows_sp_bt)[["x","n","r","rho","sig"]].sort_values("r",key=abs,ascending=False).to_string(index=False))

    # Forward
    bt_p_fwd = bt_p_joined.merge(sp_fp_next, left_on=["mlbam_id","year"], right_on=["mlbam_id","year_prev"], how="inner")
    bt_p_fwd = bt_p_fwd[bt_p_fwd["year"] < 2026]
    rows_sp_bt_fwd = [r for m in sp_bt_metrics if m in bt_p_fwd.columns
                      if (r := corr(bt_p_fwd, m, "fp_next", "T→T+1")) is not None]
    print(f"\n  FORWARD T→T+1 ({len(bt_p_fwd)} pairs):")
    if rows_sp_bt_fwd:
        print(pd.DataFrame(rows_sp_bt_fwd)[["x","n","r","rho","sig"]].sort_values("r",key=abs,ascending=False).to_string(index=False))

    # Quintile: induced avg_bat_speed → SP FP next year
    if "avg_bat_speed" in bt_p_fwd.columns:
        print("\n  Induced avg_bat_speed quintile → FP/start T+1 (lower = better for SP):")
        result = quintile_table(bt_p_fwd, "avg_bat_speed", "fp_next", ascending=True)
        if result:
            tbl, spread = result
            print(tbl.to_string())
            print(f"  Spread: {spread:+.3f} FP/start")

    # ════════════════════════════════════════════════════════════════════════
    # N. INCREMENTAL R²: bat_speed + attack_angle ABOVE our model's K%/xwOBA
    # ════════════════════════════════════════════════════════════════════════
    section("N.  INCREMENTAL R²: new bat metrics add above K%/xwOBA?  (T→T+1)")

    # Merge everything for hitters
    mega = (bt_joined
            .merge(aa_joined[["mlbam_id","year","ideal_attack_angle_rate","attack_angle",
                               "avg_intercept_y_vs_plate"]], on=["mlbam_id","year"], how="left")
            .merge(h_fp_next, left_on=["mlbam_id","year"], right_on=["mlbam_id","year_prev"], how="inner"))
    mega = mega[mega["year"] < 2026].dropna(subset=["fp_next","fp_per_pa_actual","k_pct","xwoba_per_pa"])
    print(f"  Mega hitter panel: {len(mega)} rows")

    if len(mega) >= 30:
        y = mega["fp_next"].values
        base_feats = ["fp_per_pa_actual","k_pct","xwoba_per_pa"]
        X_base = mega[base_feats].fillna(0).values
        r2_base = cross_val_score(LinearRegression(), X_base, y, cv=5, scoring="r2").mean()
        print(f"\n  Base CV-R² (fp_prev + k% + xwOBA): {r2_base:.4f}")

        for m in ["avg_bat_speed","blast_per_swing","swords_rate","swing_length",
                  "ideal_attack_angle_rate","hard_swing_rate"]:
            if m not in mega.columns: continue
            col = mega[m].fillna(mega[m].median()).values
            X_full = np.column_stack([X_base, col])
            r2_f = cross_val_score(LinearRegression(), X_full, y, cv=5, scoring="r2").mean()
            print(f"  + {m:<28s}  R²={r2_f:.4f}  ΔR²={r2_f - r2_base:+.5f}")

    # ════════════════════════════════════════════════════════════════════════
    # SAVE outputs
    # ════════════════════════════════════════════════════════════════════════
    out_path = "data/research/bat_tracking_all_2023_2026.csv"
    combined = pd.concat([
        bt_h.assign(source="bat_tracking_batter"),
        bt_p.assign(source="bat_tracking_pitcher"),
        aa_h.assign(source="attack_angle_batter"),
        aa_p.assign(source="attack_angle_pitcher"),
    ], ignore_index=True)
    combined.to_csv(out_path, index=False)
    print(f"\n  All bat-tracking data saved → {out_path}")

    section("COMPLETE")


if __name__ == "__main__":
    main()

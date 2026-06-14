"""
velo_tto_study.py — Leakage-safe study: do TIMES-THROUGH-ORDER (TTO) signals
(in-game velo fade, 3rd-time-through penalty) predict RoS SP performance better
than the validated overall-velo decline flags?

Run: PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/_oneoff/velo_tto_study.py
Writes: data/research/validation_runs/velo_tto_2026-06-13.md
"""
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data/research/xfp_cache"
OUT = ROOT / "data/research/validation_runs/velo_tto_2026-06-13.md"

YEARS = [2021, 2022, 2023, 2024, 2025]
SPLIT_DAYS = [51, 72, 93, 114]
FB_TYPES = {"FF", "SI", "FC"}  # four-seam, sinker, cutter

# ---------------------------------------------------------------------------
# 1. Load rolling panel target/baseline
# ---------------------------------------------------------------------------
roll = pd.read_csv(CACHE / "rolling_pitchers_2018_2026.csv")
roll = roll[
    roll.year.isin(YEARS)
    & roll.split_day.isin(SPLIT_DAYS)
    & (roll.gs_to >= 5)
    & (roll.ros_gs >= 3)
].copy()
roll["cutoff_date"] = pd.to_datetime(roll["cutoff_date"])
print(f"panel cells (gated, 4 split-days): {len(roll)}")

# ---------------------------------------------------------------------------
# 2. Build leakage-safe AS-OF TTO features per (pitcher, year, cutoff)
#    Using NATIVE n_thruorder_pitcher (full coverage, true TTO).
#    For each pitch with game_date < cutoff that season:
#      TTO1 = n_thruorder==1, TTO2==2, TTO3plus = >=3
#    In-game velo fade = mean FB velo TTO3+ minus TTO1.
#    TTO penalty = wOBA (or K%) TTO3+ minus TTO1 over PAs.
# ---------------------------------------------------------------------------
COLS = [
    "game_date", "pitcher", "release_speed", "pitch_type",
    "n_thruorder_pitcher", "woba_value", "woba_denom", "events",
    "at_bat_number", "game_pk",
]

# accumulate per (pitcher, year) keyed dict-of-cutoff aggregations
# We process each year once, sorted by date, and snapshot at each cutoff.
feat_rows = []
for yr in YEARS:
    sc = pd.read_parquet(CACHE / f"statcast_{yr}.parquet", columns=COLS)
    sc["game_date"] = pd.to_datetime(sc["game_date"])
    # restrict to regular pitches with a thruorder value
    sc = sc[sc["n_thruorder_pitcher"].notna()].copy()
    sc["n_thruorder_pitcher"] = sc["n_thruorder_pitcher"].astype(int)
    sc["is_fb"] = sc["pitch_type"].isin(FB_TYPES)
    sc["tto_bucket"] = np.where(
        sc["n_thruorder_pitcher"] == 1, 1,
        np.where(sc["n_thruorder_pitcher"] == 2, 2, 3),
    )
    # PA-level rows: one row per (game_pk, pitcher, at_bat_number) with woba
    pa = sc[sc["woba_denom"].notna()].copy()
    pa["woba_denom"] = pd.to_numeric(pa["woba_denom"], errors="coerce")
    pa["woba_value"] = pd.to_numeric(pa["woba_value"], errors="coerce")
    pa["is_k"] = pa["events"].isin(["strikeout", "strikeout_double_play"])
    pa = pa[pa["woba_denom"] > 0]

    cutoffs = sorted(roll[roll.year == yr]["cutoff_date"].unique())
    for cut in cutoffs:
        cut = pd.Timestamp(cut)
        fb = sc[(sc.game_date < cut) & sc.is_fb]
        # mean FB velo by tto bucket per pitcher
        velo = (
            fb.groupby(["pitcher", "tto_bucket"])["release_speed"]
            .agg(["mean", "count"])
            .unstack("tto_bucket")
        )
        # wOBA / K% by tto bucket per pitcher
        pcut = pa[pa.game_date < cut]
        woba = (
            pcut.groupby(["pitcher", "tto_bucket"])
            .agg(
                woba_sum=("woba_value", "sum"),
                woba_den=("woba_denom", "sum"),
                k_sum=("is_k", "sum"),
                pa_n=("woba_denom", "count"),
            )
        )
        # assemble per pitcher
        pids = velo.index.union(woba.index.get_level_values(0).unique())
        for pid in velo.index:
            try:
                v1 = velo.loc[pid, ("mean", 1)]
                v3 = velo.loc[pid, ("mean", 3)]
                n1 = velo.loc[pid, ("count", 1)]
                n3 = velo.loc[pid, ("count", 3)]
            except KeyError:
                continue
            rec = {"pitcher": pid, "year": yr, "cutoff_date": cut}
            rec["fb_velo_tto1"] = v1
            rec["fb_velo_tto3"] = v3
            rec["fb_n_tto1"] = n1
            rec["fb_n_tto3"] = n3
            # in-game fade: negative = loses velo by 3rd time
            if pd.notna(v1) and pd.notna(v3) and n3 >= 30:
                rec["ingame_fade"] = v3 - v1
            else:
                rec["ingame_fade"] = np.nan
            # wOBA / K% penalty
            try:
                w1s = woba.loc[(pid, 1), "woba_sum"]; w1d = woba.loc[(pid, 1), "woba_den"]
                k1 = woba.loc[(pid, 1), "k_sum"]; p1 = woba.loc[(pid, 1), "pa_n"]
            except KeyError:
                w1s = w1d = k1 = p1 = np.nan
            try:
                w3s = woba.loc[(pid, 3), "woba_sum"]; w3d = woba.loc[(pid, 3), "woba_den"]
                k3 = woba.loc[(pid, 3), "k_sum"]; p3 = woba.loc[(pid, 3), "pa_n"]
            except KeyError:
                w3s = w3d = k3 = p3 = np.nan
            if pd.notna(w1d) and pd.notna(w3d) and w1d >= 20 and w3d >= 20:
                rec["woba_penalty"] = (w3s / w3d) - (w1s / w1d)
                rec["k_penalty"] = (k3 / p3) - (k1 / p1)
                rec["tto3_pa"] = p3
            else:
                rec["woba_penalty"] = np.nan
                rec["k_penalty"] = np.nan
                rec["tto3_pa"] = p3 if pd.notna(p3) else np.nan
            feat_rows.append(rec)
    print(f"  {yr}: done ({len(feat_rows)} feat rows cumulative)")

feat = pd.DataFrame(feat_rows)
print(f"feature rows: {len(feat)}")

# ---------------------------------------------------------------------------
# 3. Join to panel target/baseline
# ---------------------------------------------------------------------------
df = roll.merge(feat, on=["pitcher", "year", "cutoff_date"], how="inner")
print(f"joined rows: {len(df)}")

# Overall velo YoY delta (proxy for the validated overall-velo decline lens).
# Build vYoY = current cumulative avg_velo_to minus prior-year season-end velo.
# Prior-year season-end = the latest split_day row for that pitcher in year-1.
allroll = pd.read_csv(CACHE / "rolling_pitchers_2018_2026.csv")
allroll["cutoff_date"] = pd.to_datetime(allroll["cutoff_date"])
prev_end = (
    allroll.sort_values("split_day")
    .groupby(["pitcher", "year"])
    .agg(prior_velo=("avg_velo_to", "last"))
    .reset_index()
)
prev_end["join_year"] = prev_end["year"] + 1
df = df.merge(
    prev_end[["pitcher", "join_year", "prior_velo"]].rename(columns={"join_year": "year"}),
    on=["pitcher", "year"], how="left",
)
df["velo_yoy"] = df["avg_velo_to"] - df["prior_velo"]

# ---------------------------------------------------------------------------
# 4. Partial correlation helper
# ---------------------------------------------------------------------------
def rankz(s):
    return s.rank()

def partial_r(data, x, y, controls):
    d = data[[x, y] + controls].dropna()
    n = len(d)
    if n < 50:
        return np.nan, n
    import numpy.linalg as la
    C = np.column_stack([np.ones(n)] + [d[c].values for c in controls])
    def resid(v):
        beta, *_ = la.lstsq(C, v, rcond=None)
        return v - C @ beta
    rx = resid(d[x].values.astype(float))
    ry = resid(d[y].values.astype(float))
    if rx.std() == 0 or ry.std() == 0:
        return np.nan, n
    r = np.corrcoef(rx, ry)[0, 1]
    return r, n

# Baseline controls: whiff/K LEVEL (rank) + fp_per_start_to
df["lvl"] = rankz(df["swstr_pct_to"]) + rankz(df["k_pct_to"])
TARGET = "ros_fp_per_start"
BASE = ["lvl", "fp_per_start_to"]
BASE_VELO = ["lvl", "fp_per_start_to", "velo_yoy"]

constructs = {
    "ingame_fade (v3-v1)": "ingame_fade",
    "woba_penalty (tto3-tto1)": "woba_penalty",
    "k_penalty (tto3-tto1)": "k_penalty",
    "fb_velo_tto1 (level)": "fb_velo_tto1",
}

print("\n=== PARTIAL-R over [level, fp_base] ===")
res = {}
for name, col in constructs.items():
    r, n = partial_r(df, col, TARGET, BASE)
    rv, nv = partial_r(df, col, TARGET, BASE_VELO)
    res[name] = (r, n, rv, nv)
    print(f"{name:28s} pr={r:+.4f} (n={n})  | over+velo pr={rv:+.4f} (n={nv})")

# Reference: overall velo_yoy itself over base
r_velo, n_velo = partial_r(df, "velo_yoy", TARGET, BASE)
print(f"\n[ref] velo_yoy over base       pr={r_velo:+.4f} (n={n_velo})")

# ---------------------------------------------------------------------------
# 5. Interaction: in-game fade x season-long velo decline
# ---------------------------------------------------------------------------
sub = df.dropna(subset=["ingame_fade", "velo_yoy", TARGET]).copy()
fade_lo = sub["ingame_fade"] <= sub["ingame_fade"].quantile(0.33)   # fades most (most negative)
yoy_lo = sub["velo_yoy"] <= sub["velo_yoy"].quantile(0.33)          # losing velo YoY
both = fade_lo & yoy_lo
neither = (~fade_lo) & (~yoy_lo)
bust_thr = sub[TARGET].quantile(0.333)
print("\n=== INTERACTION: in-game fade x season velo decline ===")
print(f"n sub={len(sub)} bust_thr(ros_fp/start p33)={bust_thr:.2f}")
def grp(mask, lbl):
    g = sub[mask]
    return f"{lbl:32s} n={len(g):4d} meanRoS={g[TARGET].mean():.2f} bust%={(g[TARGET]<bust_thr).mean()*100:.1f}"
print(grp(both, "BOTH fade & losing velo"))
print(grp(fade_lo & ~yoy_lo, "fade only"))
print(grp(~fade_lo & yoy_lo, "losing velo only"))
print(grp(neither, "NEITHER"))

# interaction partial-r: fade*yoy product term over base+main effects
df["fade_x_yoy"] = df["ingame_fade"] * df["velo_yoy"]
r_int, n_int = partial_r(df, "fade_x_yoy", TARGET, ["lvl", "fp_per_start_to", "ingame_fade", "velo_yoy"])
print(f"interaction term partial-r over [base, fade, yoy]: pr={r_int:+.4f} (n={n_int})")

# ---------------------------------------------------------------------------
# 6. Downside: bust-rate gap by fade tercile
# ---------------------------------------------------------------------------
print("\n=== BUST-RATE by ingame_fade tercile ===")
sub["fade_terc"] = pd.qcut(sub["ingame_fade"], 3, labels=["mostfade", "mid", "leastfade"])
bt = sub.groupby("fade_terc", observed=True).agg(
    n=(TARGET, "size"), meanRoS=(TARGET, "mean"),
    bustpct=(TARGET, lambda s: (s < bust_thr).mean() * 100),
)
print(bt.to_string())

# ---------------------------------------------------------------------------
# Write markdown
# ---------------------------------------------------------------------------
def fmt(name):
    r, n, rv, nv = res[name]
    return f"| {name} | {r:+.4f} | {n} | {rv:+.4f} | {nv} |"

both_g = sub[both]; nei_g = sub[neither]
fo_g = sub[fade_lo & ~yoy_lo]; vo_g = sub[~fade_lo & yoy_lo]

md = f"""# Velo / Times-Through-Order (TTO) decline-signal study

- **signal:** in-game velo fade (FB velo TTO3+ minus TTO1), 3rd-time-through wOBA/K% penalty, fade x season-velo interaction
- **outcome:** rest-of-season BrownU SP FP/start (`ros_fp_per_start`)
- **verdict:** see VERDICT section
- **date:** 2026-06-13
- **script:** `scripts/_oneoff/velo_tto_study.py`

## Methods

- **Panel:** `rolling_pitchers_2018_2026.csv`, years 2021-2025, split_days {{51,72,93,114}}, gated `gs_to>=5 & ros_gs>=3`. Joined feature rows: **{len(df)}**.
- **TTO definition:** native Statcast `n_thruorder_pitcher` (full coverage, true times-through-order, NOT the batter-order proxy). TTO1 = thruorder 1, TTO2 = 2, TTO3+ = >=3.
- **Leakage-safe AS-OF:** for each (pitcher, year, cutoff) all TTO features built ONLY from pitches with `game_date < cutoff_date` that season.
- **In-game fade** = mean FB (FF/SI/FC) `release_speed` in TTO3+ minus TTO1, gated >=30 FB pitches in TTO3+.
- **TTO penalty** = (wOBA TTO3+ minus TTO1) and (K%/PA TTO3+ minus TTO1), gated >=20 PA each bucket.
- **Baseline (Rule 9):** controls = whiff/K LEVEL `rank(swstr_pct_to)+rank(k_pct_to)` + `fp_per_start_to`. Second bar adds **overall velo YoY** (`avg_velo_to` minus prior-year season-end velo) — the real bar.

## Partial-r tables

| construct | pr over [level, fp_base] | n | pr over [level, fp_base, velo_yoy] | n |
|---|---|---|---|---|
{fmt("ingame_fade (v3-v1)")}
{fmt("woba_penalty (tto3-tto1)")}
{fmt("k_penalty (tto3-tto1)")}
{fmt("fb_velo_tto1 (level)")}

Reference — **overall velo_yoy** over [level, fp_base]: **{r_velo:+.4f}** (n={n_velo}).

(Sign convention: positive partial-r = higher feature value -> higher forward FP. For `ingame_fade`, more-negative = loses more velo within game; a POSITIVE pr means fading is BAD as expected.)

## Interaction: in-game fade x season-long velo decline

bust threshold = p33 of ros_fp_per_start = {bust_thr:.2f} FP/start. n sub = {len(sub)}.

| group | n | mean RoS FP/start | bust% |
|---|---|---|---|
| BOTH fade & losing velo YoY | {len(both_g)} | {both_g[TARGET].mean():.2f} | {(both_g[TARGET]<bust_thr).mean()*100:.1f} |
| fade only | {len(fo_g)} | {fo_g[TARGET].mean():.2f} | {(fo_g[TARGET]<bust_thr).mean()*100:.1f} |
| losing velo only | {len(vo_g)} | {vo_g[TARGET].mean():.2f} | {(vo_g[TARGET]<bust_thr).mean()*100:.1f} |
| NEITHER | {len(nei_g)} | {nei_g[TARGET].mean():.2f} | {(nei_g[TARGET]<bust_thr).mean()*100:.1f} |

Interaction product term (`fade x velo_yoy`) partial-r over [base, fade, velo_yoy]: **{r_int:+.4f}** (n={n_int}).

## Downside: bust-rate by in-game fade tercile

{bt.to_string()}

## VERDICT

{{VERDICT}}
"""

OUT.write_text(md, encoding="utf-8")
print(f"\nwrote {OUT}")
# stash key numbers for verdict
print("\nKEYNUMS", dict(
    fade_base=res["ingame_fade (v3-v1)"][0],
    fade_velo=res["ingame_fade (v3-v1)"][2],
    woba_base=res["woba_penalty (tto3-tto1)"][0],
    woba_velo=res["woba_penalty (tto3-tto1)"][2],
    k_base=res["k_penalty (tto3-tto1)"][0],
    velo_ref=r_velo, interaction=r_int,
))

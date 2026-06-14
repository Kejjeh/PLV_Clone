"""
bat_tracking_study.py  — EXPLORATORY, leakage-safe OOS study (2026-06-13)

QUESTION
--------
Does BAT-TRACKING decline (bat_speed, swing_length) predict a hitter's
rest-of-season decline — the hitter-side analog of SP velo decline, which
we currently have NOTHING like?

DATA (all LOCAL)
----------------
Pitch-level Statcast: data/research/xfp_cache/statcast_{2024,2025,2026}.parquet
  bat_speed / swing_length exist ONLY 2024+ (Statcast bat-tracking era).
  -> 2024 & 2025 are the only usable full train/test years. 2026 is partial
     (season in progress as of 2026-06-13) so it can only serve as a
     held-out forward window for 2025-anchored cutoffs, NOT as its own
     full-season test. COVERAGE IS THE BIG CONSTRAINT: effectively 2 years.

METHODOLOGY (leakage-safe AS-OF)
--------------------------------
For each (year in {2024,2025}, cutoff_date) we split that season's pitches
into a TO-DATE window (game_date < cutoff, the only data the feature is
allowed to see) and a FORWARD window (game_date >= cutoff, the target).

  * TO-DATE features (per batter, computed ONLY from < cutoff swings):
      - bat_speed_todate         : mean bat_speed on swings
      - bat_speed_recent_l21d    : mean bat_speed last 21d before cutoff
      - bat_speed_decline        : recent_l21d - todate   (negative = slowing)
      - bat_speed_decline_vs_peak: recent_l21d - rolling-peak (best 21d window)
      - swing_length_todate / _recent / _shift
      - fast_swing_rate decline  : pct of swings >= 75 mph, recent vs to-date
      - bat_speed on COMPETITIVE swings (description in swinging/foul/hit_into_play,
        excludes bunts via swing_length floor)
      - YoY 2024->2025 bat_speed delta (season means; only for year==2025)
      - to-date CONTACT-QUALITY LEVEL controls (Rule 9 baseline):
          xwoba_on_contact_todate (mean est_woba on BIP)
          core_fp_per_pa_todate   (the to-date level of the SAME target metric)

  * FORWARD target (computed ONLY from >= cutoff PAs):
      core_fp_per_pa_fwd = (TB + BB + HBP - K) / PA
      xwoba_per_pa_fwd   = mean estimated_woba_using_speedangle over PAs

      *** SUBSTITUTION NOTE (stated plainly) ***
      Full BrownU hitter FP = R + TB + RBI + BB + HBP + SB - K. Pitch-level
      Statcast does NOT carry R / RBI / SB (baserunning/game-state outcomes),
      so we use a CORE-FP/PA proxy = (TB+BB+HBP-K)/PA, i.e. the components of
      BrownU hitter scoring that ARE derivable from PA outcomes, plus a
      parallel xwOBA/PA target. R/RBI/SB add lineup- and context-dependent
      noise but are ~correlated with TB; the proxy captures the bat-driven
      core. Treat absolute magnitudes as proxy units, not BrownU FP/game.

BASELINE (Rule 9 spirit)
------------------------
Partial correlation of each bat-tracking DECLINE feature with the FORWARD
target, AFTER residualizing out a baseline of:
    [ to-date contact-quality LEVEL (xwoba_on_contact_todate),
      to-date level of the target itself (core_fp_per_pa_todate) ].
This is the honest test: does bat-speed DECLINE add anything once we already
know how good / how productive the hitter has been to-date?

OUTPUTS
-------
  - partial-r table (raw r, partial r vs baseline, n) per feature x target
  - downside "bust-gap": forward outcome of biggest-decliners vs rest
  - writes data/research/validation_runs/bat_tracking_decline_2026-06-13.md
"""

import os
import sys
import numpy as np
import pandas as pd
from scipy import stats

CACHE = "data/research/xfp_cache"
OUT_MD = "data/research/validation_runs/bat_tracking_decline_2026-06-13.md"

PA_FLOOR_TODATE = 120     # min to-date PAs to have a stable feature
PA_FLOOR_FWD = 80         # min forward PAs to have a stable target
SWING_FLOOR_TODATE = 60   # min to-date swings w/ bat_speed
L21D = pd.Timedelta(days=21)
FAST_SWING_MPH = 75.0     # "fast swing" threshold (near league-avg ~71-72)

# competitive-swing descriptions (real swings, not takes/blocked-balls)
COMPETITIVE = {
    "hit_into_play", "foul", "swinging_strike", "swinging_strike_blocked",
    "foul_tip", "foul_bunt",  # foul_bunt rare; bunts mostly excluded by speed
}

TB_MAP = {"single": 1, "double": 2, "triple": 3, "home_run": 4}


def load_year(year):
    cols = [
        "bat_speed", "swing_length", "estimated_woba_using_speedangle",
        "woba_value", "woba_denom", "batter", "stand", "game_date",
        "events", "description",
    ]
    df = pd.read_parquet(f"{CACHE}/statcast_{year}.parquet", columns=cols)
    df["game_date"] = pd.to_datetime(df["game_date"])
    return df


def todate_features(sw, cutoff):
    """sw = swings (bat_speed notnull) before cutoff. Returns per-batter dict."""
    recent = sw[sw["game_date"] >= (cutoff - L21D)]
    g = sw.groupby("batter")
    out = pd.DataFrame({
        "bat_speed_todate": g["bat_speed"].mean(),
        "swing_length_todate": g["swing_length"].mean(),
        "n_swings_todate": g["bat_speed"].size(),
    })
    # fast-swing rate to-date
    out["fast_rate_todate"] = g.apply(
        lambda x: (x["bat_speed"] >= FAST_SWING_MPH).mean(), include_groups=False
    )
    # competitive-swing bat_speed to-date
    comp = sw[sw["description"].isin(COMPETITIVE)]
    out["bat_speed_comp_todate"] = comp.groupby("batter")["bat_speed"].mean()

    # recent (l21d) versions
    rg = recent.groupby("batter")
    out["bat_speed_recent"] = rg["bat_speed"].mean()
    out["swing_length_recent"] = rg["swing_length"].mean()
    out["fast_rate_recent"] = rg.apply(
        lambda x: (x["bat_speed"] >= FAST_SWING_MPH).mean(), include_groups=False
    ) if len(recent) else np.nan
    out["n_swings_recent"] = rg["bat_speed"].size()

    # rolling 21d PEAK bat_speed (best 21d mean before cutoff), per batter
    def peak_21d(x):
        x = x.sort_values("game_date")
        s = x.set_index("game_date")["bat_speed"]
        if s.empty:
            return np.nan
        roll = s.rolling("21D").mean()
        return roll.max()
    out["bat_speed_peak21"] = sw.groupby("batter").apply(peak_21d, include_groups=False)

    # DECLINE features (negative = getting worse)
    out["bs_decline_recent"] = out["bat_speed_recent"] - out["bat_speed_todate"]
    out["bs_decline_vs_peak"] = out["bat_speed_recent"] - out["bat_speed_peak21"]
    out["sl_shift_recent"] = out["swing_length_recent"] - out["swing_length_todate"]
    out["fast_rate_decline"] = out["fast_rate_recent"] - out["fast_rate_todate"]

    return out


def todate_quality_and_level(allpa, cutoff):
    """Rule-9 baseline controls from < cutoff PAs."""
    pa = allpa[(allpa["game_date"] < cutoff) & (allpa["woba_denom"] > 0)].copy()
    pa["tb"] = pa["events"].map(TB_MAP).fillna(0)
    pa["is_bb"] = pa["events"].isin(["walk", "intent_walk"]).astype(int)
    pa["is_hbp"] = (pa["events"] == "hit_by_pitch").astype(int)
    pa["is_k"] = pa["events"].isin(
        ["strikeout", "strikeout_double_play"]).astype(int)
    pa["core_fp"] = pa["tb"] + pa["is_bb"] + pa["is_hbp"] - pa["is_k"]
    g = pa.groupby("batter")
    bip = pa[pa["estimated_woba_using_speedangle"].notna()]
    out = pd.DataFrame({
        "pa_todate": g.size(),
        "core_fp_per_pa_todate": g["core_fp"].sum() / g.size(),
        "xwoba_on_contact_todate":
            bip.groupby("batter")["estimated_woba_using_speedangle"].mean(),
    })
    return out


def forward_target(allpa, cutoff):
    """Forward core-FP/PA proxy + forward xwOBA/PA from >= cutoff PAs."""
    pa = allpa[(allpa["game_date"] >= cutoff) & (allpa["woba_denom"] > 0)].copy()
    pa["tb"] = pa["events"].map(TB_MAP).fillna(0)
    pa["is_bb"] = pa["events"].isin(["walk", "intent_walk"]).astype(int)
    pa["is_hbp"] = (pa["events"] == "hit_by_pitch").astype(int)
    pa["is_k"] = pa["events"].isin(
        ["strikeout", "strikeout_double_play"]).astype(int)
    pa["core_fp"] = pa["tb"] + pa["is_bb"] + pa["is_hbp"] - pa["is_k"]
    g = pa.groupby("batter")
    out = pd.DataFrame({
        "pa_fwd": g.size(),
        "core_fp_per_pa_fwd": g["core_fp"].sum() / g.size(),
        "xwoba_per_pa_fwd":
            g["estimated_woba_using_speedangle"].mean(),
    })
    return out


def partial_r(y, x, controls):
    """Partial correlation of x with y controlling for `controls` (DataFrame).
    Residualize x and y on controls via OLS (numpy), correlate residuals."""
    m = np.column_stack([np.ones(len(controls))] + [controls[c].values for c in controls.columns])
    def resid(v):
        beta, *_ = np.linalg.lstsq(m, v, rcond=None)
        return v - m @ beta
    xr = resid(x.values.astype(float))
    yr = resid(y.values.astype(float))
    r, p = stats.pearsonr(xr, yr)
    return r, p


def build_panel(cutoffs_by_year, yoy_means):
    rows = []
    for year, cutoffs in cutoffs_by_year.items():
        df = load_year(year)
        swings = df[df["bat_speed"].notna()].copy()
        for cutoff in cutoffs:
            cutoff = pd.Timestamp(cutoff)
            sw_to = swings[swings["game_date"] < cutoff]
            if len(sw_to) == 0:
                continue
            feats = todate_features(sw_to, cutoff)
            qual = todate_quality_and_level(df, cutoff)
            tgt = forward_target(df, cutoff)
            panel = feats.join(qual, how="inner").join(tgt, how="inner")
            panel = panel.reset_index().rename(columns={"index": "batter"})
            panel["year"] = year
            panel["cutoff"] = cutoff
            # attach YoY bat_speed delta (2024->2025) for 2025 cutoffs
            if year == 2025 and yoy_means is not None:
                panel = panel.merge(yoy_means, on="batter", how="left")
            else:
                panel["bs_yoy_delta"] = np.nan
            rows.append(panel)
    full = pd.concat(rows, ignore_index=True)
    # filters
    full = full[(full["pa_todate"] >= PA_FLOOR_TODATE) &
                (full["pa_fwd"] >= PA_FLOOR_FWD) &
                (full["n_swings_todate"] >= SWING_FLOOR_TODATE)]
    return full.reset_index(drop=True)


def yoy_bat_speed():
    """Season-mean bat_speed 2024 vs 2025 -> delta (2025 minus 2024)."""
    out = {}
    for year in (2024, 2025):
        df = load_year(year)
        sw = df[df["bat_speed"].notna()]
        out[year] = sw.groupby("batter")["bat_speed"].mean()
    delta = (out[2025] - out[2024]).rename("bs_yoy_delta").reset_index()
    return delta


def main():
    print("Loading YoY bat_speed means (2024 vs 2025)...")
    yoy = yoy_bat_speed()

    # cutoffs: mid-May, mid-June, mid-July of each full year (leaves a real
    # forward window). 2026 NOT used as a cutoff year (partial season).
    cutoffs_by_year = {
        2024: ["2024-05-20", "2024-06-20", "2024-07-20"],
        2025: ["2025-05-20", "2025-06-20", "2025-07-20"],
    }
    print("Building leakage-safe as-of panel...")
    panel = build_panel(cutoffs_by_year, yoy)
    print(f"Panel rows (batter x cutoff): {len(panel)}  "
          f"unique batters: {panel['batter'].nunique()}")

    feats = [
        ("bs_decline_recent", "bat_speed recent(L21d) - to-date mean"),
        ("bs_decline_vs_peak", "bat_speed recent(L21d) - rolling 21d peak"),
        ("sl_shift_recent", "swing_length recent - to-date"),
        ("fast_rate_decline", "fast-swing(>=75mph) rate recent - to-date"),
        ("bs_yoy_delta", "bat_speed YoY 2024->2025 (season means)"),
    ]
    targets = [
        ("core_fp_per_pa_fwd", "forward CORE-FP/PA proxy (TB+BB+HBP-K)/PA"),
        ("xwoba_per_pa_fwd", "forward xwOBA/PA"),
    ]
    baseline_cols = ["xwoba_on_contact_todate", "core_fp_per_pa_todate"]

    results = []
    for tcol, tlabel in targets:
        for fcol, flabel in feats:
            sub = panel.dropna(subset=[fcol, tcol] + baseline_cols)
            n = len(sub)
            if n < 25:
                results.append((tlabel, flabel, n, np.nan, np.nan, np.nan, np.nan))
                continue
            raw_r, raw_p = stats.pearsonr(sub[fcol], sub[tcol])
            pr, pp = partial_r(sub[tcol], sub[fcol], sub[baseline_cols])
            results.append((tlabel, flabel, n, raw_r, raw_p, pr, pp))

    res_df = pd.DataFrame(results, columns=[
        "target", "feature", "n", "raw_r", "raw_p", "partial_r", "partial_p"])

    # ---- downside bust-gap: biggest decliners vs rest (on bs_decline_vs_peak) ----
    bust_lines = []
    for tcol, tlabel in targets:
        sub = panel.dropna(subset=["bs_decline_vs_peak", tcol])
        if len(sub) < 40:
            continue
        q = sub["bs_decline_vs_peak"].quantile(0.20)  # worst 20% decliners
        decl = sub[sub["bs_decline_vs_peak"] <= q]
        rest = sub[sub["bs_decline_vs_peak"] > q]
        gap = decl[tcol].mean() - rest[tcol].mean()
        # bust rate: forward in bottom-quartile of forward outcome
        thresh = sub[tcol].quantile(0.25)
        bust_decl = (decl[tcol] <= thresh).mean()
        bust_rest = (rest[tcol] <= thresh).mean()
        bust_lines.append(
            (tlabel, len(decl), decl[tcol].mean(), rest[tcol].mean(),
             gap, bust_decl, bust_rest))

    bust_df = pd.DataFrame(bust_lines, columns=[
        "target", "n_decliners", "decliner_mean_fwd", "rest_mean_fwd",
        "gap", "bust_rate_decliners", "bust_rate_rest"])

    # ---- print ----
    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", 20)
    print("\n=== PARTIAL-R TABLE (vs baseline: to-date xwOBAcon + to-date core-FP level) ===")
    print(res_df.to_string(index=False,
          float_format=lambda v: f"{v:.4f}"))
    print("\n=== DOWNSIDE BUST-GAP (worst-20% bat_speed-vs-peak decliners vs rest) ===")
    print(bust_df.to_string(index=False,
          float_format=lambda v: f"{v:.4f}"))

    write_md(res_df, bust_df, panel)
    print(f"\nWrote {OUT_MD}")


def write_md(res_df, bust_df, panel):
    def md_table(df):
        cols = list(df.columns)
        lines = ["| " + " | ".join(cols) + " |",
                 "|" + "|".join(["---"] * len(cols)) + "|"]
        for _, r in df.iterrows():
            vals = []
            for c in cols:
                v = r[c]
                if isinstance(v, float):
                    vals.append(f"{v:.4f}" if not pd.isna(v) else "n/a")
                else:
                    vals.append(str(v))
            lines.append("| " + " | ".join(vals) + " |")
        return "\n".join(lines)

    n_rows = len(panel)
    n_bat = panel["batter"].nunique()
    n_cut = panel.groupby(["year", "cutoff"]).size()

    md = f"""# Bat-Tracking Decline as a Hitter-Decline Lens — Leakage-Safe OOS Study

**Date:** 2026-06-13  **Status:** EXPLORATORY (net-new lens, NOT promoted)
**Author:** automated study (`scripts/_oneoff/bat_tracking_study.py`)

## Question
Does **bat-tracking decline** (bat_speed, swing_length) predict a hitter's
**rest-of-season decline** — the hitter-side analog of SP velo decline, which
the model currently has **no equivalent of**?

## Coverage constraint (read this first)
Statcast `bat_speed` / `swing_length` exist **only 2024+**. That leaves
**2 usable full seasons (2024, 2025)** for an as-of train/test. 2026 is a
partial season (study run 2026-06-13) and is **excluded as a cutoff year** —
it cannot supply a full forward window. **Everything below is 2-year evidence.
Do not overclaim.**

## Design (leakage-safe as-of)
For each `(year in {{2024,2025}}, cutoff in {{mid-May, mid-Jun, mid-Jul}})`:
- **Features** computed ONLY from swings/PAs **before** the cutoff.
- **Target** computed ONLY from PAs **on/after** the cutoff.
- Panel = batter × cutoff. Filters: ≥{PA_FLOOR_TODATE} to-date PA, ≥{PA_FLOOR_FWD}
  forward PA, ≥{SWING_FLOOR_TODATE} to-date swings with bat_speed.
- **Panel size: {n_rows} (batter×cutoff) rows, {n_bat} unique batters, 6 cutoffs.**

### Forward-target proxy (stated plainly)
BrownU hitter FP = `R + TB + RBI + BB + HBP + SB − K`. Pitch-level Statcast
does **not** carry R / RBI / SB (baserunning + game-state outcomes), so the
forward target is a **CORE-FP/PA proxy = (TB + BB + HBP − K) / PA** — the
BrownU scoring components that ARE derivable from PA outcomes — plus a parallel
**forward xwOBA/PA**. R/RBI/SB are correlated with TB and on-base, so the proxy
captures the bat-driven core; absolute magnitudes are **proxy units**, not
BrownU FP/game.

### Baseline (Rule-9 spirit)
Partial-r residualizes each decline feature **and** the target on a baseline of
`[to-date xwOBA-on-contact LEVEL, to-date core-FP/PA LEVEL]`. Honest test:
does bat-speed *decline* add anything once we already know how good and how
productive the hitter has been to-date?

## Partial-r table
(raw_r = unconditional; partial_r = after baseline; positive feature = LESS
decline, so a positive partial_r means "more decline → worse forward outcome".)

{md_table(res_df)}

## Downside bust-gap
Worst-20% decliners on `bat_speed recent(L21d) − rolling-21d peak` vs the rest.
`gap` < 0 means decliners do WORSE forward (proxy units). `bust_rate_*` =
share landing in the bottom forward quartile.

{md_table(bust_df)}

## Read / verdict
See the returned summary. Key honesty points:
- 2-year coverage; treat as directional, NOT a validated signal.
- Forward target is a contact/discipline **proxy** (no R/RBI/SB).
- Partial-r is the load-bearing number — raw-r can be inflated by the simple
  fact that good hitters both swing faster and produce more.
- This is EXPLORATORY per the multi-testing protocol; promotion to rh3 would
  require `/validate-feature` with the full Rule-9 production baseline and
  ≥1 more season of bat-tracking data.
"""
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write(md)


if __name__ == "__main__":
    main()

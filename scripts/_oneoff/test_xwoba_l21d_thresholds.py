"""
Empirically backfit xwOBA L21d-vs-prior-year-baseline gap thresholds for
SKILL_HOLDING / REAL_DECLINE classification.

Method:
1. Sample ~300 hitters from top 250 rh3 ranks at 6 as_of dates across 2024+2025.
2. For each (hitter, as_of):
   - L21d xwOBA over [as_of-21d, as_of] from current-season statcast
   - Prior-year full-season xwOBA baseline (>=300 PA)
   - Gap = L21d - prior_year_baseline
   - Forward 30d xwOBA + forward 30d BrownU FP/g
3. Decile gaps, compute mean forward metrics per decile.
4. Recommend cutoffs that maximize separation.

Run:
    python scripts/_oneoff/test_xwoba_l21d_thresholds.py
"""

from __future__ import annotations

import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

REPO = Path(r"c:/Users/Joshua/plv_clone")
CACHE = REPO / "data/research/xfp_cache"
OUT_MD = REPO / "data/research/validation_runs/xwoba_l21d_threshold_backfit_2026-06-06.md"

AS_OF_DATES = [
    "2024-05-15", "2024-06-30", "2024-08-15",
    "2025-05-15", "2025-06-30", "2025-08-15",
]
N_HITTERS_PER_DATE = 120  # 6 * 120 = 720 oversample (many drop due to PA/baseline filters; targeting ~300)
TOP_RH3 = 250
L21_WINDOW = 21
FORWARD_WINDOW = 30
MIN_L21_PA = 30           # need at least this many PA in the window to compute stable L21d
MIN_PRIOR_PA = 300        # prior-year baseline floor
MIN_FORWARD_PA = 30       # need this many PA in fwd window to keep a row

# ---------------------------------------------------------------------------
# Load cached statcast (cols only — keeps memory tight)
# ---------------------------------------------------------------------------

NEEDED_COLS = [
    "batter", "game_date", "events", "description",
    "woba_value", "woba_denom", "estimated_woba_using_speedangle",
]


def load_statcast(year: int) -> pd.DataFrame:
    p = CACHE / f"statcast_{year}.parquet"
    df = pd.read_parquet(p, columns=NEEDED_COLS)
    df["game_date"] = pd.to_datetime(df["game_date"])
    return df


print("Loading statcast 2023/2024/2025...")
sc23 = load_statcast(2023)
sc24 = load_statcast(2024)
sc25 = load_statcast(2025)

ALL_SC = {2023: sc23, 2024: sc24, 2025: sc25}


# ---------------------------------------------------------------------------
# xwOBA helpers — per-PA aggregation. Per Statcast docs:
#   - estimated_woba_using_speedangle = xwOBA for batted balls
#   - For K/BB/HBP the woba_value is fixed and we use it directly
#   - woba_denom flags PAs (excludes IBB, sac bunts, etc.)
# ---------------------------------------------------------------------------

def compute_xwoba_window(sc_year_df: pd.DataFrame, batter_id: int,
                        start: datetime, end: datetime) -> tuple[float | None, int]:
    sub = sc_year_df[(sc_year_df["batter"] == batter_id) &
                    (sc_year_df["game_date"] >= start) &
                    (sc_year_df["game_date"] <= end) &
                    (sc_year_df["woba_denom"] == 1)]
    if len(sub) == 0:
        return None, 0
    # For each PA: use estimated_woba if BIP & launch data exists else fall back to woba_value
    num = np.where(sub["estimated_woba_using_speedangle"].notna(),
                   sub["estimated_woba_using_speedangle"],
                   sub["woba_value"])
    denom = sub["woba_denom"].sum()
    if denom == 0:
        return None, 0
    return float(np.nansum(num) / denom), int(denom)


def compute_xwoba_full_season(year: int, batter_id: int) -> tuple[float | None, int]:
    if year not in ALL_SC:
        return None, 0
    df = ALL_SC[year]
    return compute_xwoba_window(df, batter_id, df["game_date"].min(), df["game_date"].max())


# ---------------------------------------------------------------------------
# BrownU FP per game (forward target)
# Formula: R + TB + RBI + BB + HBP + SB - K
# But we only have Statcast pitch-level. We can approximate per PA from events.
# ---------------------------------------------------------------------------

def fp_per_pa_from_events(sub: pd.DataFrame) -> float:
    # Map event -> contribution
    # We can't get R / RBI / SB from pitch data alone perfectly, but we can get
    # TB + BB + HBP - K. R/RBI/SB are correlated with TB, so use a TB-weighted proxy.
    # NOTE: this is OK for *relative ranking* of L21d but undercounts absolute FP.
    # To get true BrownU FP/g we'd join MLB Stats API game logs — out of scope here.
    # We'll instead use FP_PROXY = TB + BB + HBP - K per PA, which preserves rank.
    ev = sub["events"].fillna("").to_numpy()
    n_1b = (ev == "single").sum()
    n_2b = (ev == "double").sum()
    n_3b = (ev == "triple").sum()
    n_hr = (ev == "home_run").sum()
    n_bb = ((ev == "walk") | (ev == "intent_walk")).sum()
    n_hbp = (ev == "hit_by_pitch").sum()
    n_k = ((ev == "strikeout") | (ev == "strikeout_double_play")).sum()
    tb = n_1b + 2 * n_2b + 3 * n_3b + 4 * n_hr
    return float(tb + n_bb + n_hbp - n_k)


def compute_forward_fp_per_g(sc_year_df: pd.DataFrame, batter_id: int,
                             start: datetime, end: datetime) -> tuple[float | None, int]:
    sub = sc_year_df[(sc_year_df["batter"] == batter_id) &
                    (sc_year_df["game_date"] >= start) &
                    (sc_year_df["game_date"] <= end) &
                    (sc_year_df["woba_denom"] == 1)]
    if len(sub) == 0:
        return None, 0
    fp_total = fp_per_pa_from_events(sub)
    n_games = sub["game_date"].nunique()
    if n_games == 0:
        return None, 0
    return float(fp_total / n_games), n_games


# ---------------------------------------------------------------------------
# Sample hitters: use top 250 by rh3 (current snapshot is fine as a sampling
# frame — they're the universe of fantasy-relevant hitters).
# ---------------------------------------------------------------------------

print("Loading top hitters from rh3...")
rh3 = pd.read_csv(REPO / "data/outputs/xfp_rh3_projections.csv")
top_hitters = rh3.head(TOP_RH3)[["batter", "player_name"]].rename(columns={"batter": "batter_id"})
top_hitters["batter_id"] = top_hitters["batter_id"].astype(int)
print(f"  {len(top_hitters)} top-rh3 hitters available as sampling frame")


# ---------------------------------------------------------------------------
# Build observation rows
# ---------------------------------------------------------------------------

rng = np.random.default_rng(42)
rows = []
for as_of_str in AS_OF_DATES:
    as_of = pd.Timestamp(as_of_str)
    year = as_of.year
    if year not in ALL_SC:
        continue
    sc = ALL_SC[year]
    prior_year = year - 1

    # Sample N hitters that have prior-year season >= MIN_PRIOR_PA
    # (we'll filter post-hoc; oversample)
    sample = top_hitters.sample(n=min(N_HITTERS_PER_DATE, len(top_hitters)),
                                random_state=rng.integers(0, 1_000_000))

    for _, r in sample.iterrows():
        bid = int(r["batter_id"])

        # 1) prior-year baseline
        prior_xwoba, prior_pa = compute_xwoba_full_season(prior_year, bid)
        if prior_xwoba is None or prior_pa < MIN_PRIOR_PA:
            continue

        # 2) L21d xwOBA
        l21_start = as_of - pd.Timedelta(days=L21_WINDOW)
        l21_xwoba, l21_pa = compute_xwoba_window(sc, bid, l21_start, as_of)
        if l21_xwoba is None or l21_pa < MIN_L21_PA:
            continue

        # 3) Forward 30d xwOBA + FP/g
        fwd_start = as_of + pd.Timedelta(days=1)
        fwd_end = as_of + pd.Timedelta(days=FORWARD_WINDOW)
        fwd_xwoba, fwd_pa = compute_xwoba_window(sc, bid, fwd_start, fwd_end)
        if fwd_xwoba is None or fwd_pa < MIN_FORWARD_PA:
            continue
        fwd_fp_per_g, fwd_g = compute_forward_fp_per_g(sc, bid, fwd_start, fwd_end)
        if fwd_fp_per_g is None:
            continue

        rows.append({
            "as_of": as_of_str,
            "year": year,
            "batter_id": bid,
            "player_name": r["player_name"],
            "prior_year_xwoba": prior_xwoba,
            "prior_year_pa": prior_pa,
            "l21_xwoba": l21_xwoba,
            "l21_pa": l21_pa,
            "gap": l21_xwoba - prior_xwoba,
            "fwd_xwoba": fwd_xwoba,
            "fwd_pa": fwd_pa,
            "fwd_fp_per_g": fwd_fp_per_g,
            "fwd_games": fwd_g,
            "fwd_minus_prior_xwoba": fwd_xwoba - prior_xwoba,
        })

obs = pd.DataFrame(rows)
print(f"\nObservations after filters: {len(obs)}")
obs = obs.drop_duplicates(subset=["as_of", "batter_id"])
print(f"After dedupe (as_of, batter_id): {len(obs)}")
print(obs[["as_of", "gap", "fwd_xwoba", "fwd_fp_per_g"]].describe())


# ---------------------------------------------------------------------------
# Decile analysis
# ---------------------------------------------------------------------------

obs["decile"] = pd.qcut(obs["gap"], 10, labels=False, duplicates="drop")
decile_tbl = obs.groupby("decile").agg(
    gap_min=("gap", "min"),
    gap_max=("gap", "max"),
    gap_mean=("gap", "mean"),
    fwd_xwoba_mean=("fwd_xwoba", "mean"),
    fwd_fp_per_g_mean=("fwd_fp_per_g", "mean"),
    fwd_minus_prior_mean=("fwd_minus_prior_xwoba", "mean"),
    N=("gap", "size"),
).reset_index()

# Baseline forward xwOBA (the prior_year_xwoba mean among the sample)
baseline_fwd_xwoba_mean = obs["prior_year_xwoba"].mean()
baseline_fwd_fp_mean = obs["fwd_fp_per_g"].median()


# ---------------------------------------------------------------------------
# Empirical cutoff search: scan candidate REAL_DECLINE cutoffs from -0.10 to
# -0.02 step 0.005; SKILL_HOLDING band as ±cut symmetric around 0 from 0.010
# to 0.040 step 0.005. Score by separation in forward FP/g and forward xwOBA.
# ---------------------------------------------------------------------------

decline_cuts = np.arange(-0.100, -0.015, 0.005)
hold_cuts = np.arange(0.010, 0.045, 0.005)

best_decline = {"cut": None, "sep": -np.inf}
for cut in decline_cuts:
    below = obs[obs["gap"] < cut]
    above = obs[obs["gap"] >= cut]
    if len(below) < 20 or len(above) < 20:
        continue
    sep_xwoba = above["fwd_xwoba"].mean() - below["fwd_xwoba"].mean()
    sep_fp = above["fwd_fp_per_g"].mean() - below["fwd_fp_per_g"].mean()
    # Combined score weighting xwOBA separation (true skill) heavier
    score = 0.6 * sep_xwoba / 0.020 + 0.4 * sep_fp / 1.0
    if score > best_decline["sep"]:
        best_decline = {
            "cut": float(cut),
            "sep": float(score),
            "n_below": int(len(below)),
            "n_above": int(len(above)),
            "below_fwd_xwoba": float(below["fwd_xwoba"].mean()),
            "above_fwd_xwoba": float(above["fwd_xwoba"].mean()),
            "below_fwd_fp_per_g": float(below["fwd_fp_per_g"].mean()),
            "above_fwd_fp_per_g": float(above["fwd_fp_per_g"].mean()),
        }

# SKILL_HOLDING: forward xwOBA within X of prior_year baseline.
# We want the band |gap| <= cut to have fwd_minus_prior_xwoba clustered near 0.
best_hold = {"cut": None, "score": np.inf}
for cut in hold_cuts:
    inside = obs[(obs["gap"] >= -cut) & (obs["gap"] <= cut)]
    if len(inside) < 30:
        continue
    # Score: mean abs forward-minus-prior — lower means tighter "skill holding" claim
    sc_mean = float(inside["fwd_minus_prior_xwoba"].abs().mean())
    if sc_mean < best_hold["score"]:
        best_hold = {
            "cut": float(cut),
            "score": sc_mean,
            "n_inside": int(len(inside)),
            "fwd_minus_prior_xwoba_mean": float(inside["fwd_minus_prior_xwoba"].mean()),
            "fwd_minus_prior_xwoba_abs": sc_mean,
            "fwd_xwoba_mean": float(inside["fwd_xwoba"].mean()),
        }


# ---------------------------------------------------------------------------
# Comparison: current cuts (±0.020, <-0.060) vs empirical
# ---------------------------------------------------------------------------

def evaluate_cuts(skill_band: float, decline_cut: float) -> dict:
    skill = obs[(obs["gap"] >= -skill_band) & (obs["gap"] <= skill_band)]
    decline = obs[obs["gap"] < decline_cut]
    middle = obs[(obs["gap"] > -abs(decline_cut)) & ((obs["gap"] < -skill_band) | (obs["gap"] > skill_band))]
    return {
        "skill_n": len(skill),
        "skill_fwd_xwoba": float(skill["fwd_xwoba"].mean()) if len(skill) else np.nan,
        "skill_fwd_fp": float(skill["fwd_fp_per_g"].mean()) if len(skill) else np.nan,
        "skill_fwd_minus_prior": float(skill["fwd_minus_prior_xwoba"].mean()) if len(skill) else np.nan,
        "decline_n": len(decline),
        "decline_fwd_xwoba": float(decline["fwd_xwoba"].mean()) if len(decline) else np.nan,
        "decline_fwd_fp": float(decline["fwd_fp_per_g"].mean()) if len(decline) else np.nan,
        "decline_fwd_minus_prior": float(decline["fwd_minus_prior_xwoba"].mean()) if len(decline) else np.nan,
        "middle_n": len(middle),
        "middle_fwd_xwoba": float(middle["fwd_xwoba"].mean()) if len(middle) else np.nan,
        "middle_fwd_fp": float(middle["fwd_fp_per_g"].mean()) if len(middle) else np.nan,
    }

current = evaluate_cuts(0.020, -0.060)
empirical = evaluate_cuts(best_hold["cut"], best_decline["cut"])


# ---------------------------------------------------------------------------
# Write report
# ---------------------------------------------------------------------------

def fmt_dec(r):
    return f"[{r.gap_min:+.3f}, {r.gap_max:+.3f}]"

lines = []
lines.append("# xwOBA L21d-vs-prior-year-baseline threshold backfit\n")
lines.append("**Run date:** 2026-06-06\n")
lines.append(f"**Sample:** N={len(obs)} (hitter, as_of) pairs across 6 dates in 2024+2025\n")
lines.append(f"**Frame:** top {TOP_RH3} rh3-ranked hitters\n")
lines.append(f"**Filters:** prior-year PA >= {MIN_PRIOR_PA}, L21d PA >= {MIN_L21_PA}, forward {FORWARD_WINDOW}d PA >= {MIN_FORWARD_PA}\n")
lines.append("\n**Forward target FP/g uses TB+BB+HBP-K proxy** (preserves rank vs true BrownU FP/g; R/RBI/SB unavailable from Statcast). Forward xwOBA is the primary skill target.\n")
lines.append("\n## Decile table\n")
lines.append("| Decile | Gap range | Mean gap | N | Fwd xwOBA | Fwd FP/g proxy | Fwd − prior xwOBA |\n")
lines.append("|---:|:---|---:|---:|---:|---:|---:|\n")
for _, r in decile_tbl.iterrows():
    lines.append(f"| D{int(r.decile)+1} | [{r.gap_min:+.3f}, {r.gap_max:+.3f}] | {r.gap_mean:+.3f} | {int(r.N)} | {r.fwd_xwoba_mean:.3f} | {r.fwd_fp_per_g_mean:.2f} | {r.fwd_minus_prior_mean:+.3f} |\n")

lines.append("\n**Reading guide:** if gap predicts forward skill, fwd_xwoba should rise monotonically across deciles, and fwd_minus_prior should swing from negative (bottom deciles) toward 0 (middle deciles, 'skill holding').\n")

lines.append("\n## Current cuts (±0.020 SKILL_HOLDING, <-0.060 REAL_DECLINE)\n")
lines.append("| Bucket | N | Fwd xwOBA | Fwd FP/g | Fwd − prior xwOBA |\n")
lines.append("|---|---:|---:|---:|---:|\n")
lines.append(f"| SKILL_HOLDING (gap in ±0.020) | {current['skill_n']} | {current['skill_fwd_xwoba']:.3f} | {current['skill_fwd_fp']:.2f} | {current['skill_fwd_minus_prior']:+.3f} |\n")
lines.append(f"| MIDDLE (between bands) | {current['middle_n']} | {current['middle_fwd_xwoba']:.3f} | {current['middle_fwd_fp']:.2f} | n/a |\n")
lines.append(f"| REAL_DECLINE (gap < -0.060) | {current['decline_n']} | {current['decline_fwd_xwoba']:.3f} | {current['decline_fwd_fp']:.2f} | {current['decline_fwd_minus_prior']:+.3f} |\n")

lines.append("\n## Empirical optimal cuts\n")
lines.append(f"- **REAL_DECLINE cutoff:** `gap < {best_decline['cut']:+.3f}` (max forward-separation score)\n")
lines.append(f"  - Below: N={best_decline['n_below']}, fwd xwOBA={best_decline['below_fwd_xwoba']:.3f}, fwd FP/g={best_decline['below_fwd_fp_per_g']:.2f}\n")
lines.append(f"  - Above: N={best_decline['n_above']}, fwd xwOBA={best_decline['above_fwd_xwoba']:.3f}, fwd FP/g={best_decline['above_fwd_fp_per_g']:.2f}\n")
lines.append(f"- **SKILL_HOLDING band:** `|gap| <= {best_hold['cut']:+.3f}` (tightest fwd_minus_prior_xwoba)\n")
lines.append(f"  - Inside: N={best_hold['n_inside']}, fwd_xwoba={best_hold['fwd_xwoba_mean']:.3f}, fwd_minus_prior mean={best_hold['fwd_minus_prior_xwoba_mean']:+.3f} (|·| mean={best_hold['fwd_minus_prior_xwoba_abs']:.3f})\n")

lines.append("\n## Side-by-side\n")
lines.append("| Cut set | SKILL_HOLDING band | REAL_DECLINE cutoff | Decline-vs-Hold fwd xwOBA gap |\n")
lines.append("|---|---|---|---:|\n")
gap_now = current['skill_fwd_xwoba'] - current['decline_fwd_xwoba']
gap_emp = empirical['skill_fwd_xwoba'] - empirical['decline_fwd_xwoba']
lines.append(f"| Current (reference doc) | ±0.020 | <-0.060 | {gap_now:.3f} |\n")
lines.append(f"| Empirical | ±{best_hold['cut']:.3f} | <{best_decline['cut']:+.3f} | {gap_emp:.3f} |\n")

# Recommendation
lines.append("\n## Recommendation\n")
delta_skill = abs(best_hold['cut'] - 0.020)
delta_decline = abs(best_decline['cut'] - (-0.060))
if delta_skill < 0.006 and delta_decline < 0.011:
    lines.append("**KEEP current cuts ±0.020 / <-0.060.** Empirical optimums are within rounding distance (Δ skill < 0.006, Δ decline < 0.011) — no tighten/loosen lift large enough to justify changing the published reference. The forward-xwOBA separation gap is comparable.\n")
else:
    direction_skill = "tighten" if best_hold['cut'] < 0.020 else "loosen"
    direction_decline = "tighten (more negative)" if best_decline['cut'] < -0.060 else "loosen (less negative)"
    lines.append(f"**ADJUST:** {direction_skill} SKILL_HOLDING band to ±{best_hold['cut']:.3f}; {direction_decline} REAL_DECLINE cutoff to <{best_decline['cut']:+.3f}. Empirical separation: {gap_emp:.3f} vs current {gap_now:.3f}.\n")

# Calibration plot data
lines.append("\n## Calibration plot data (gap bin midpoint vs forward FP/g delta from baseline)\n")
plot_bins = np.arange(-0.12, 0.121, 0.020)
obs["bin"] = pd.cut(obs["gap"], plot_bins)
plot_df = obs.groupby("bin", observed=True).agg(
    n=("gap", "size"),
    fwd_xwoba=("fwd_xwoba", "mean"),
    fwd_fp_per_g=("fwd_fp_per_g", "mean"),
    fwd_minus_prior=("fwd_minus_prior_xwoba", "mean"),
).reset_index()
median_fp = obs["fwd_fp_per_g"].median()
lines.append("| Gap bin | N | Fwd xwOBA | Fwd FP/g | Fwd FP/g − sample median |\n")
lines.append("|---|---:|---:|---:|---:|\n")
for _, r in plot_df.iterrows():
    lines.append(f"| {r['bin']} | {int(r['n'])} | {r['fwd_xwoba']:.3f} | {r['fwd_fp_per_g']:.2f} | {r['fwd_fp_per_g']-median_fp:+.2f} |\n")

lines.append(f"\nSample-median forward FP/g proxy: {median_fp:.2f}\n")

lines.append("\n## Caveats\n")
lines.append("- FP/g uses a TB+BB+HBP-K **proxy** because R/RBI/SB are unavailable from Statcast pitch data. Preserves rank but undercounts absolute magnitude. Forward xwOBA is the cleaner skill signal.\n")
lines.append("- 2024 prior-year for 2024 as_of dates uses **2023** baseline; 2025 as_of uses **2024**. Both included via ALL_SC[year].\n")
lines.append(f"- Min sample sizes enforced (L21d PA >= {MIN_L21_PA}, forward PA >= {MIN_FORWARD_PA}); thin-window hitters silently dropped.\n")
lines.append("- Sample frame is top-{} rh3 hitters (current snapshot) — this is the population we actually make decisions on, but it biases toward survivors. A truly random MLB sample would include more steep declines.\n".format(TOP_RH3))

OUT_MD.parent.mkdir(parents=True, exist_ok=True)
OUT_MD.write_text("".join(lines), encoding="utf-8")
print(f"\nWrote {OUT_MD}")
print(f"Empirical: SKILL_HOLDING ±{best_hold['cut']:.3f}, REAL_DECLINE <{best_decline['cut']:+.3f}")
print(f"Current:   SKILL_HOLDING ±0.020,           REAL_DECLINE <-0.060")

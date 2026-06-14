"""
Spin-rate / spin-axis decline as an SP DECLINE-RISK signal — leakage-safe OOS study.

QUESTION: does SPIN-RATE / SPIN-AXIS decline add decline-prediction signal OVER
our existing overall-velo-decline flags? Theory (post-sticky-stuff era): spin
decline often LEADS velo decline, so it could be an earlier stuff-erosion / injury
signal. THE BAR: a spin construct only wins if it beats partial-r over BOTH
(a) level+FP baseline AND (b) level+FP+overall-velo-YoY, at adequate n.

Methodology mirrors velo_pitchtype_study.py exactly:
  - Panel rolling_pitchers_2018_2026.csv, gate gs_to>=5 & ros_gs>=3.
  - Years 2021-2025, cutoffs split_day in {51,72,93,114} (~4/season).
  - Leakage-safe AS-OF: pitch-level spin from game_date < cutoff_date only.
  - YoY delta = as-of construct minus PRIOR full-season construct.
  - Baseline (Rule 9): level=rank(swstr_pct_to)+rank(k_pct_to); fp_base=fp_per_start_to.
  - Bar 1 partial-r over [level, fp_base]; Bar 2 (THE bar) ALSO over overall-velo YoY.
  - Bust gap = bust-rate(worst-decline tercile) - bust-rate(best tercile);
    bust = bottom-tercile ros_fp_per_start within (year, split_day) cell.
  - Sign: positive partial-r => higher spin (less decline) -> higher fwd FP,
    i.e. spin decline is bad. Positive bust gap => declining tercile busts more.

Output: data/research/validation_runs/spin_decline_2026-06-13.md
"""
import os
import numpy as np
import pandas as pd

CACHE = "data/research/xfp_cache"
ROLL = f"{CACHE}/rolling_pitchers_2018_2026.csv"
OUT_MD = "data/research/validation_runs/spin_decline_2026-06-13.md"

YEARS = [2021, 2022, 2023, 2024, 2025]
CUTOFFS = [51, 72, 93, 114]

FB_TYPES = ["FF", "SI", "FC"]          # fastball group
BREAK_TYPES = ["SL", "CU", "ST", "KC", "SV"]  # breaking group (spin-led shapes)
MIN_TYPE_PITCHES = 30      # as-of per-type min
MIN_PRIOR_PITCHES = 50     # prior full-season per-type min


# ------------------------------------------------------------------ helpers
def circ_dist_deg(a, b):
    """Smallest circular distance between two angles in degrees (0-360, wraps)."""
    d = np.abs(a - b) % 360.0
    return np.minimum(d, 360.0 - d)


def partial_r(df, x, y, controls):
    """Partial correlation of x with y controlling for `controls` (list).
    Residualize x and y on [1, controls] via OLS, correlate residuals."""
    cols = [x, y] + controls
    d = df[cols].dropna()
    if len(d) < 30:
        return np.nan, len(d)
    C = np.column_stack([np.ones(len(d))] + [d[c].values for c in controls])

    def resid(v):
        beta, *_ = np.linalg.lstsq(C, v, rcond=None)
        return v - C @ beta

    rx = resid(d[x].values.astype(float))
    ry = resid(d[y].values.astype(float))
    if rx.std() == 0 or ry.std() == 0:
        return np.nan, len(d)
    return float(np.corrcoef(rx, ry)[0, 1]), len(d)


def bust_gap(df, feat):
    """Worst-decline-tercile bust rate minus best-tercile bust rate.
    bust = bottom-tercile ros_fp within (year,split_day). feat: lower=more decline."""
    d = df[[feat, "ros_fp_per_start", "year", "split_day"]].dropna().copy()
    if len(d) < 60:
        return np.nan
    # bust label per cell
    d["bust"] = (
        d.groupby(["year", "split_day"])["ros_fp_per_start"]
        .transform(lambda s: s <= s.quantile(1 / 3.0))
        .astype(float)
    )
    try:
        d["terc"] = pd.qcut(d[feat], 3, labels=["worst", "mid", "best"], duplicates="drop")
    except ValueError:
        return np.nan
    if d["terc"].nunique() < 3:
        return np.nan
    worst = d.loc[d.terc == "worst", "bust"].mean()
    best = d.loc[d.terc == "best", "bust"].mean()
    return float(worst - best)


# ------------------------------------------------------------------ load panel
print("loading rolling panel ...")
panel = pd.read_csv(ROLL)
panel = panel[(panel.gs_to >= 5) & (panel.ros_gs >= 3)]
panel = panel[panel.year.isin(YEARS) & panel.split_day.isin(CUTOFFS)].copy()
panel["cutoff_date"] = pd.to_datetime(panel["cutoff_date"])
print("gated panel rows:", len(panel))

# ------------------------------------------------------------------ load statcast (SP-relevant cols)
SC_COLS = ["pitch_type", "game_date", "release_speed", "release_spin_rate",
           "spin_axis", "pitcher", "p_throws"]
sc = {}
for y in YEARS:
    df = pd.read_parquet(f"{CACHE}/statcast_{y}.parquet", columns=SC_COLS)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.dropna(subset=["release_spin_rate", "release_speed"])
    sc[y] = df
    # prior year full-season (need y-1)
    py = y - 1
    if py not in sc and py not in YEARS:
        pdf = pd.read_parquet(f"{CACHE}/statcast_{py}.parquet", columns=SC_COLS)
        pdf["game_date"] = pd.to_datetime(pdf["game_date"])
        pdf = pdf.dropna(subset=["release_spin_rate", "release_speed"])
        sc[py] = pdf
print("statcast years loaded:", sorted(sc.keys()))


# ------------------------------------------------------------------ prior-year FULL-SEASON aggregates per pitcher
def season_aggs(df):
    """Per pitcher: overall velo, FB-group spin, per-type spin, per-type axis, bauer."""
    g = df.groupby("pitcher")
    out = pd.DataFrame(index=g.size().index)
    out["velo_all"] = g["release_speed"].mean()
    out["n_all"] = g.size()
    # per-type
    for grp, types, tag in [(FB_TYPES, FB_TYPES, "fb"), (BREAK_TYPES, BREAK_TYPES, "brk")]:
        sub = df[df.pitch_type.isin(types)]
        gg = sub.groupby("pitcher")
        out[f"spin_{tag}"] = gg["release_spin_rate"].mean()
        out[f"velo_{tag}"] = gg["release_speed"].mean()
        out[f"n_{tag}"] = gg.size()
    for t in ["FF", "SI", "SL", "CU"]:
        sub = df[df.pitch_type == t]
        gg = sub.groupby("pitcher")
        out[f"spin_{t}"] = gg["release_spin_rate"].mean()
        out[f"n_{t}"] = gg.size()
        # circular mean axis
        ax = gg["spin_axis"].apply(
            lambda s: np.degrees(np.arctan2(
                np.sin(np.radians(s)).mean(), np.cos(np.radians(s)).mean())) % 360
        )
        out[f"axis_{t}"] = ax
    return out


print("computing prior-year season aggregates ...")
prior = {}
for y in YEARS:
    prior[y] = season_aggs(sc[y - 1])

# ------------------------------------------------------------------ build features per panel row
print("building as-of features ...")
rows = []
for (y, cut), grp in panel.groupby(["year", "split_day"]):
    sy = sc[y]
    cutoff = grp["cutoff_date"].iloc[0]
    asof = sy[sy.game_date < cutoff]
    if len(asof) == 0:
        continue
    agg = season_aggs(asof)  # as-of aggregates per pitcher (same shape)
    # season-peak: rolling 14-day window spin peak before cutoff (FB group) for in-season drop
    fb = asof[asof.pitch_type.isin(FB_TYPES)].copy()
    fb["wk"] = (fb["game_date"] - fb["game_date"].min()).dt.days // 14
    peak = (
        fb.groupby(["pitcher", "wk"])["release_spin_rate"].mean()
        .groupby("pitcher").max()
    )
    cur_fb = fb.groupby("pitcher")["release_spin_rate"].mean()
    pj = prior[y]
    for _, r in grp.iterrows():
        p = r["pitcher"]
        if p not in agg.index:
            continue
        a = agg.loc[p].fillna(np.nan)

        def cnt(d, key):
            v = d.get(key, 0)
            return 0 if (v is None or pd.isna(v)) else float(v)

        rec = {"pitcher": p, "year": y, "split_day": cut,
               "ros_fp_per_start": r["ros_fp_per_start"],
               "swstr_pct_to": r["swstr_pct_to"], "k_pct_to": r["k_pct_to"],
               "fp_per_start_to": r["fp_per_start_to"], "avg_velo_to": r["avg_velo_to"]}
        # prior row
        pr = pj.loc[p] if p in pj.index else None

        # --- overall velo YoY (THE reference bar) : as-of velo - prior full-season velo
        if pr is not None and not np.isnan(pr["velo_all"]):
            rec["velo_yoy"] = a["velo_all"] - pr["velo_all"]

        # --- F1: FB-group spin YoY (as-of fb spin - prior fb spin)
        if (pr is not None and cnt(a, "n_fb") >= MIN_TYPE_PITCHES
                and cnt(pr, "n_fb") >= MIN_PRIOR_PITCHES):
            rec["fb_spin_yoy"] = a["spin_fb"] - pr["spin_fb"]

        # --- F2: in-season spin drop vs season-peak (as-of only, no prior needed)
        if p in peak.index and p in cur_fb.index and peak[p] > 0:
            rec["fb_spin_inseason"] = cur_fb[p] - peak[p]  # <=0, more negative = bigger drop

        # --- F3: spin-axis SHIFT YoY (FF), circular distance (NEGATED so larger shift = more "decline")
        if (pr is not None and cnt(a, "n_FF") >= MIN_TYPE_PITCHES
                and cnt(pr, "n_FF") >= MIN_PRIOR_PITCHES
                and not pd.isna(a["axis_FF"]) and not pd.isna(pr["axis_FF"])):
            shift = circ_dist_deg(a["axis_FF"], pr["axis_FF"])
            rec["ff_axis_shift"] = -shift  # sign: less shift -> higher (good), so positive r expected
            rec["ff_axis_shift_raw"] = shift

        # --- F4: spin-to-velo (Bauer units = spin/velo) YoY decline, FB group
        if (pr is not None and cnt(a, "n_fb") >= MIN_TYPE_PITCHES and cnt(pr, "n_fb") >= MIN_PRIOR_PITCHES
                and a["velo_fb"] > 0 and pr["velo_fb"] > 0):
            bauer_now = a["spin_fb"] / a["velo_fb"]
            bauer_prior = pr["spin_fb"] / pr["velo_fb"]
            rec["fb_bauer_yoy"] = bauer_now - bauer_prior

        # --- F5: per-pitch-type spin decline: FF, SI, SL, CU
        for t in ["FF", "SI", "SL", "CU"]:
            if (pr is not None and cnt(a, f"n_{t}") >= MIN_TYPE_PITCHES
                    and cnt(pr, f"n_{t}") >= MIN_PRIOR_PITCHES
                    and not pd.isna(a[f"spin_{t}"]) and not pd.isna(pr[f"spin_{t}"])):
                rec[f"{t.lower()}_spin_yoy"] = a[f"spin_{t}"] - pr[f"spin_{t}"]

        # --- breaking-ball group spin YoY
        if (pr is not None and cnt(a, "n_brk") >= MIN_TYPE_PITCHES and cnt(pr, "n_brk") >= MIN_PRIOR_PITCHES):
            rec["brk_spin_yoy"] = a["spin_brk"] - pr["spin_brk"]

        rows.append(rec)

feat = pd.DataFrame(rows)
print("feature rows:", len(feat))

# spin x velo INTERACTION (both dropping = worst). standardized product.
def z(s):
    return (s - s.mean()) / s.std(ddof=0)

both = feat.dropna(subset=["fb_spin_yoy", "velo_yoy"]).copy()
# build interaction on the common support, merge back
inter = z(both["fb_spin_yoy"]) * z(both["velo_yoy"])
feat.loc[both.index, "spin_x_velo"] = inter.values
# also a simple "both-drop" min(z) signal: how far the WORSE of the two has fallen
feat.loc[both.index, "spin_velo_mindrop"] = np.minimum(
    z(both["fb_spin_yoy"]).values, z(both["velo_yoy"]).values)

# ------------------------------------------------------------------ baseline controls
feat["level"] = feat["swstr_pct_to"].rank() + feat["k_pct_to"].rank()
feat["fp_base"] = feat["fp_per_start_to"]

# ------------------------------------------------------------------ evaluate
CONSTRUCTS = [
    ("FB-group spin YoY (FF/SI/FC)", "fb_spin_yoy"),
    ("FF spin YoY", "ff_spin_yoy"),
    ("SI spin YoY", "si_spin_yoy"),
    ("SL spin YoY", "sl_spin_yoy"),
    ("CU spin YoY", "cu_spin_yoy"),
    ("Breaking-group spin YoY (SL/CU/ST..)", "brk_spin_yoy"),
    ("FB spin in-season drop vs peak", "fb_spin_inseason"),
    ("FF spin-axis shift YoY (circular)", "ff_axis_shift"),
    ("FB Bauer-units (spin/velo) YoY", "fb_bauer_yoy"),
    ("spin x velo interaction (z*z)", "spin_x_velo"),
    ("spin/velo worse-of-two drop (min z)", "spin_velo_mindrop"),
]

results = []
for name, col in CONSTRUCTS:
    r1, n1 = partial_r(feat, col, "ros_fp_per_start", ["level", "fp_base"])
    r2, n2 = partial_r(feat, col, "ros_fp_per_start", ["level", "fp_base", "velo_yoy"])
    bg = bust_gap(feat, col)
    # also: collinearity with velo_yoy (how redundant is it?)
    rc, _ = partial_r(feat, col, "velo_yoy", [])  # raw corr w/ velo_yoy
    results.append((name, col, r1, r2, bg, n2, rc))

# reference: overall velo YoY itself
rv1, nv1 = partial_r(feat, "velo_yoy", "ros_fp_per_start", ["level", "fp_base"])
bgv = bust_gap(feat, "velo_yoy")

res_df = pd.DataFrame(results, columns=[
    "construct", "col", "r_level_fp", "r_also_velo", "bust_gap", "n", "corr_w_velo"])

# ------------------------------------------------------------------ verdict logic
# win = beats BOTH bars at adequate n: r_level_fp > rv1 AND r_also_velo materially > 0 AND n>=2000
def classify(row):
    if pd.isna(row.r_level_fp) or pd.isna(row.r_also_velo):
        return "NO-DATA"
    if row.n < 1500:
        return "REJECT-coverage"
    beats_bar1 = row.r_level_fp >= rv1 - 0.005
    adds_over_velo = row.r_also_velo >= 0.03
    if beats_bar1 and adds_over_velo and row.n >= 2000:
        return "WIN"
    if adds_over_velo and row.n >= 2000:
        return "COMPLEMENT(not-replace)"
    return "NULL"

res_df["verdict"] = res_df.apply(classify, axis=1)

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)
print("\n=== REFERENCE overall velo YoY: r(level+fp)=%.3f  bust_gap=%.3f  n=%d ==="
      % (rv1, bgv, nv1))
print(res_df.to_string(index=False))

# ------------------------------------------------------------------ write MD
def f(x):
    return "%.3f" % x if pd.notna(x) else "n/a"

lines = []
lines.append("---")
lines.append("signal: spin-rate / spin-axis decline (SP decline-risk board)")
lines.append("outcome: ros_fp_per_start (BrownU FP/start over post-cutoff starts)")
win_any = (res_df.verdict == "WIN").any()
comp_any = (res_df.verdict == "COMPLEMENT(not-replace)").any()
if win_any:
    vshort = "WIN — a spin construct beats overall-velo decline"
elif comp_any:
    vshort = "NULL (replace) / COMPLEMENT — spin adds marginal info but does NOT replace velo"
else:
    vshort = "NULL — spin decline is redundant with / weaker than overall-velo decline"
lines.append(f"verdict: {vshort}")
lines.append("date: 2026-06-13")
lines.append("script: scripts/_oneoff/spin_decline_study.py")
lines.append("---")
lines.append("")
lines.append("# Spin-rate / spin-axis decline vs overall-velo decline — leakage-safe OOS study")
lines.append("")
lines.append("## Question / theory")
lines.append("")
lines.append("Post-sticky-stuff era (2021 crackdown onward), spin decline is hypothesized to "
             "LEAD velo decline as an earlier stuff-erosion / injury signal. We test whether ANY "
             "spin construct adds OOS decline-prediction signal OVER our existing overall-velo "
             "YoY flag. THE BAR: a construct wins only if it beats partial-r over BOTH "
             "(a) level+FP and (b) level+FP+overall-velo-YoY, at adequate n (>=2000).")
lines.append("")
lines.append("## Methods")
lines.append("")
lines.append(f"- Panel `rolling_pitchers_2018_2026.csv`; gate gs_to>=5 & ros_gs>=3; "
             f"years {YEARS}; cutoffs split_day {CUTOFFS} (~4/season). Gated rows: {len(panel)}.")
lines.append("- Leakage-safe AS-OF: all spin/velo aggregates use only pitches with "
             "`game_date < cutoff_date`; per-type min 30 as-of / 50 prior-year pitches.")
lines.append("- YoY delta = as-of construct minus PRIOR full-season construct (per pitcher).")
lines.append("- Spin-axis shift = circular distance in degrees (wraparound handled via "
             "atan2 circular mean + min(d, 360-d)); NEGATED so 'less shift' aligns +r.")
lines.append("- Bauer units = release_spin_rate / release_speed (FB group).")
lines.append("- spin x velo interaction = z(fb_spin_yoy) * z(velo_yoy); "
             "min-z = worse-of-the-two standardized drop.")
lines.append("- Baseline (Rule 9): level = rank(swstr_pct_to)+rank(k_pct_to); fp_base = fp_per_start_to.")
lines.append("- Bar 1 = partial-r over [level, fp_base]; Bar 2 (THE bar) ALSO controls overall-velo YoY.")
lines.append("- Bust gap = bust-rate(worst-decline tercile) - bust-rate(best tercile); "
             "bust = bottom-tercile ros_fp within (year,split_day).")
lines.append("- Sign: +partial-r => higher spin (less decline) -> higher fwd FP (decline is bad). "
             "+bust gap => declining tercile busts more.")
lines.append("")
lines.append("## Partial-r table")
lines.append("")
lines.append("| Construct | r over level+FP | r ALSO over velo-YoY | bust gap | corr w/ velo-YoY | n | verdict |")
lines.append("|---|---|---|---|---|---|---|")
for _, rr in res_df.iterrows():
    lines.append(f"| {rr.construct} | {f(rr.r_level_fp)} | {f(rr.r_also_velo)} | "
                 f"{f(rr.bust_gap)} | {f(rr.corr_w_velo)} | {int(rr.n) if pd.notna(rr.n) else 0} | {rr.verdict} |")
lines.append(f"| [REF] Overall velo YoY | {f(rv1)} | n/a | {f(bgv)} | 1.000 | {nv1} | reference |")
lines.append("")
lines.append(f"Feature rows: **{len(feat)}**. Reference overall-velo YoY partial-r over level+FP = **{f(rv1)}**.")
lines.append("")
lines.append("## Verdict")
lines.append("")
lines.append(f"**{vshort.upper()}.**")
lines.append("")
# auto narrative
best = res_df.dropna(subset=["r_level_fp"]).sort_values("r_also_velo", ascending=False)
lines.append("Key reads (auto-generated):")
for _, rr in best.head(4).iterrows():
    lines.append(f"- **{rr.construct}**: raw r {f(rr.r_level_fp)} (vs velo {f(rv1)}), "
                 f"marginal-over-velo {f(rr.r_also_velo)}, corr-with-velo {f(rr.corr_w_velo)}, "
                 f"n={int(rr.n) if pd.notna(rr.n) else 0} -> {rr.verdict}.")
lines.append("")
lines.append("### Honesty notes")
lines.append("- A spin construct that is highly correlated with velo-YoY (corr_w_velo near +1) and "
             "whose marginal-over-velo partial-r collapses is COLLINEAR / redundant, not a new signal.")
lines.append("- Per-type spin (FF/SI/SL/CU) and prior-year-dependent constructs lose coverage "
             "(per-type + prior-year pitch gates); judge them at their n, not the headline n.")
lines.append("- Wins require beating BOTH bars at n>=2000 (team lens rule). Coverage-limited slices "
             "that pass on n<2000 are rejected as self-selected subsets, not roster-wide flags.")

with open(OUT_MD, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print("\nwrote", OUT_MD)

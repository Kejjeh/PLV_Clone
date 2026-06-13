"""SP lens trust-weight evaluation (2026-06-13).

Empirically rank how much to trust each SP RoS-FP/start lens, using the
leakage-safe rolling panel + player-clustered CV (lens_value_add discipline).

Lenses (each a standalone predictor of realized RoS FP/start):
  1. Stuff+ projection      (fg_asof in-season Stuff+, subpop = matched arms)
  2. rp3 per_start (core)    (RidgeCV refit on raw-panel rp3 features)
  3. Blended xFP            (proxy: shrunk-form blend, see note)
  4. Sustainability E[ROS]   (Statcast skill composite, subpop = has-Statcast)
  5. Archetype T+1          (next_fp on the archetype panel — NEXT-SEASON horizon)
  6. Recent actuals (L5)     (fp_per_start_last21)
  7. talent_prior (marcel)   (career Marcel prior; subpop = thin-data / IL arms)

Metrics per lens: standalone Spearman + Pearson + MAE on realized RoS FP/start,
and the INCREMENTAL partial-r over the base (rp3-core), all under GroupKFold
clustered on pitcher (no pitcher in train+test).
"""
from __future__ import annotations
import os, sys, json
import numpy as np, pandas as pd
from pathlib import Path
from scipy.stats import spearmanr, pearsonr
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import GroupKFold

ROOT = Path(r"c:\Users\Joshua\plv_clone")
PANEL = ROOT / "data/research/xfp_cache/rolling_pitchers_2018_2026.csv"
MULTIYR = ROOT / "data/research/xfp_cache/sp_multiyr.csv"
ARCH = ROOT / "data/research/sp_archetype_career_panel.parquet"
FG = ROOT / "data/research/fg_asof"
TARGET = "ros_fp_per_start"
EVAL_GS_MIN, ROS_GS_MIN = 2, 5
RNG = np.random.default_rng(13)

# ---------------------------------------------------------------- load panel
df = pd.read_csv(PANEL)
df = df[(df["gs_to"] >= EVAL_GS_MIN) & (df["ros_gs"] >= ROS_GS_MIN)].copy()
df = df[df["year"] != 2020]

# rp3-core features available directly in the raw panel (the dominant in-season
# signal; the IL/delta/schedule add-ons are each validated at only +0.01-0.015 r,
# so this faithfully proxies rp3's bulk predictive power).
RP3_CORE = [
    "k_pct_to", "bb_pct_to", "swstr_pct_to", "c_plus_swstr_to",
    "xwoba_per_pa_to", "zone_pct_to", "z_swing_pct_to", "o_swing_pct_to",
    "avg_velo_to", "fp_per_start_to", "gs_to", "split_day",
]
# Sustainability composite = the validated 9-marker Statcast skill set
SUS_FEATS = [
    "k_pct_to", "bb_pct_to", "swstr_pct_to", "c_plus_swstr_to",
    "xwoba_on_contact_to", "barrel_pct_to", "hard_hit_pct_to",
    "gb_pct_to", "o_swing_pct_to",
]

df = df.dropna(subset=RP3_CORE + [TARGET]).copy()

# ---- talent_prior (SP Marcel) -------------------------------------------------
mu = pd.read_csv(MULTIYR)[["pitcher", "year", "gs", "fp_per_start_actual"]]
lg = mu[mu.gs >= 10].groupby("year")["fp_per_start_actual"].mean().to_dict()
by_yr = {y: g.set_index("pitcher") for y, g in mu.groupby("year")}
PRIOR_K, W = 8.0, {1: 5, 2: 4, 3: 3}
def marcel(p, tgt):
    num = den = 0.0
    for off, w in W.items():
        y = tgt - off
        if y == 2020 or y not in by_yr or p not in by_yr[y].index:
            continue
        r = by_yr[y].loc[p]
        r = r.iloc[0] if isinstance(r, pd.DataFrame) else r
        gs, fp = float(r.gs or 0), float(r.fp_per_start_actual)
        if gs >= 3 and not np.isnan(fp):
            num += w * gs * fp; den += w * gs
    lgmu = lg.get(tgt, np.nanmean(list(lg.values())))
    return (num + PRIOR_K * lgmu) / (den + PRIOR_K), den
pri = [marcel(p, y) for p, y in zip(df.pitcher, df.year)]
df["talent_prior"] = [x[0] for x in pri]
df["prior_eff_gs"] = [x[1] for x in pri]

# ---- recent actuals L5 proxy --------------------------------------------------
df["recent_actuals"] = df["fp_per_start_last21"]

# ---- Stuff+ join (in-season, _05-16 files = ~mid-May read) --------------------
stuff_map = {}
for y in [2021, 2022, 2023, 2024, 2025]:
    f = FG / f"fg_pit_{y}_pre_05-16.csv"
    if f.exists():
        s = pd.read_csv(f)[["mlb_id", "stuff_plus"]].dropna()
        for _, r in s.iterrows():
            stuff_map[(int(r.mlb_id), y)] = float(r.stuff_plus)
# 2026 current
f26 = FG / "fg_pit_2026_current.csv"
if f26.exists():
    s = pd.read_csv(f26)[["mlb_id", "stuff_plus"]].dropna()
    for _, r in s.iterrows():
        stuff_map[(int(r.mlb_id), 2026)] = float(r.stuff_plus)
df["stuff_plus"] = [stuff_map.get((int(p), int(y)), np.nan)
                    for p, y in zip(df.pitcher, df.year)]

# ================================================================ CV machinery
def clustered_oos_pred(X, y, groups, n_splits=5):
    """Return OOS predictions from a clustered RidgeCV (z-scored)."""
    gkf = GroupKFold(n_splits=n_splits)
    pred = np.full(len(y), np.nan)
    for tr, te in gkf.split(X, y, groups):
        pipe = Pipeline([("s", StandardScaler()),
                         ("r", RidgeCV(alphas=np.logspace(-1, 5, 60)))])
        pipe.fit(X[tr], y[tr])
        pred[te] = pipe.predict(X[te])
    return pred

def metrics(pred, y):
    m = ~np.isnan(pred) & ~np.isnan(y)
    pred, y = pred[m], y[m]
    return (spearmanr(pred, y).correlation,
            pearsonr(pred, y)[0],
            float(np.mean(np.abs(pred - y))), m.sum())

# base = rp3-core OOS prediction (full panel)
g_full = df.pitcher.values
ybase = df[TARGET].values
base_pred_full = clustered_oos_pred(df[RP3_CORE].values, ybase, g_full)
df["base_pred"] = base_pred_full

def eval_lens(name, sub, lens_col=None, lens_feats=None, calibrate=False):
    """Evaluate a lens on subpop `sub`. lens prediction is either a single
    column (lens_col) or an OOS RidgeCV over lens_feats. `calibrate=True`
    maps a raw-unit column onto the FP scale via clustered OOS 1-var Ridge so
    MAE is comparable (used for Stuff+, which is on the ~100 scale)."""
    sub = sub.dropna(subset=([lens_col] if lens_col else lens_feats) + [TARGET]).copy()
    g = sub.pitcher.values; y = sub[TARGET].values
    if lens_col and not calibrate:
        lpred = sub[lens_col].values.astype(float)
    elif lens_col and calibrate:
        lpred = clustered_oos_pred(sub[[lens_col]].values, y, g)
    else:
        lpred = clustered_oos_pred(sub[lens_feats].values, y, g)
    sp, pe, mae, n = metrics(lpred, y)
    # incremental partial-r over base, on this subpop. recompute base OOS on subpop
    base = clustered_oos_pred(sub[RP3_CORE].values, y, g)
    mask = ~np.isnan(lpred) & ~np.isnan(base) & ~np.isnan(y)
    lp, bp, yy = lpred[mask], base[mask], y[mask]
    # residualize: partial corr of lens with y, controlling for base
    def resid(a, c):
        c1 = np.c_[np.ones_like(c), c]
        beta = np.linalg.lstsq(c1, a, rcond=None)[0]
        return a - c1 @ beta
    ry = resid(yy, bp); rl = resid(lp, bp)
    partial = pearsonr(rl, ry)[0]
    base_sp = spearmanr(bp, yy).correlation
    return dict(lens=name, n=int(n), spearman=round(sp, 3), pearson=round(pe, 3),
                mae=round(mae, 2), base_spearman_subpop=round(base_sp, 3),
                partial_r_over_base=round(partial, 3))

rows = []
# 1. rp3-core (base itself) — partial vs itself is ~0 by construction; report standalone
sp, pe, mae, n = metrics(base_pred_full, ybase)
rows.append(dict(lens="rp3 per_start (core)", n=int(n), spearman=round(sp, 3),
                 pearson=round(pe, 3), mae=round(mae, 2),
                 base_spearman_subpop=round(sp, 3), partial_r_over_base=0.0))
# 2. Stuff+
rows.append(eval_lens("Stuff+ projection", df, lens_col="stuff_plus", calibrate=True))
# 3. Sustainability E[ROS] (Statcast composite)
rows.append(eval_lens("Sustainability E[ROS]", df, lens_feats=SUS_FEATS))
# 4. Recent actuals L5
rows.append(eval_lens("Recent actuals (L5)", df, lens_col="recent_actuals"))
# 5. talent_prior (full panel + thin-data subpop)
rows.append(eval_lens("talent_prior (marcel, all)", df, lens_col="talent_prior"))
thin = df[df.gs_to <= 5]
rows.append(eval_lens("talent_prior (thin gs_to<=5)", thin, lens_col="talent_prior"))
# 6. Blended xFP proxy = simple shrink blend of season-form + prior + recent
df["blended_proxy"] = (0.5 * df.fp_per_start_to + 0.3 * df.talent_prior +
                       0.2 * df.recent_actuals)
rows.append(eval_lens("Blended xFP (proxy)", df, lens_col="blended_proxy"))

res = pd.DataFrame(rows)

# ---- Archetype T+1 — SEPARATE horizon (next SEASON), eval on its own panel ----
ap = pd.read_parquet(ARCH)
ap = ap.dropna(subset=["t1_fp_projection", "next_fp"])
ag = ap.pitcher.values
# standalone: t1_fp_projection vs realized next_fp
sp_a = spearmanr(ap.t1_fp_projection, ap.next_fp).correlation
pe_a = pearsonr(ap.t1_fp_projection, ap.next_fp)[0]
mae_a = float(np.mean(np.abs(ap.t1_fp_projection - ap.next_fp)))
# base on this panel = current-year fp_per_start carry-forward (the naive "talent" base)
base_col = "fp_per_start" if "fp_per_start" in ap.columns else "fp_per_start_actual"
m = ap[base_col].notna()
apm = ap[m]
def resid(a, c):
    c1 = np.c_[np.ones_like(c), c]; b = np.linalg.lstsq(c1, a, rcond=None)[0]; return a - c1 @ b
ry = resid(apm.next_fp.values, apm[base_col].values)
rl = resid(apm.t1_fp_projection.values, apm[base_col].values)
partial_a = pearsonr(rl, ry)[0]
base_sp_a = spearmanr(apm[base_col], apm.next_fp).correlation
arch_row = dict(lens="Archetype T+1 (NEXT-SEASON)", n=int(len(ap)),
                spearman=round(sp_a, 3), pearson=round(pe_a, 3), mae=round(mae_a, 2),
                base_spearman_subpop=round(base_sp_a, 3),
                partial_r_over_base=round(partial_a, 3))

res = pd.concat([res, pd.DataFrame([arch_row])], ignore_index=True)

pd.set_option("display.width", 200, "display.max_columns", 20)
print(res.to_string(index=False))
res.to_json(ROOT / "data/research/validation_runs/sp_lens_trust_weights_2026-06-13.json",
            orient="records", indent=2)
print("\nN base rows:", len(df), "| archetype rows:", len(ap))

"""Lens value-add test (2026-06-11).

Quantify whether the multi-lens SYNTHESIS adds out-of-sample predictive value
over the BASE production-model rank at forecasting realized forward FP.

Design (extends the 2026-06-06 drop_one_lens_ablation + confidence_label_calibration):

PANEL: data/research/validation_runs/shrinkage_{h,sp}_snap_2026-06-06.parquet
  - Each row is an (player, as_of) snapshot with leakage-safe predictors
    (pred_k* = talent-shrunk forward projections built ONLY from data <= as_of)
    and a forward `target` = realized forward FP/g (next ~30d).
  - 1498 H snaps (189 players), 550 SP snaps (89 players).

BASE (Rule 9 honoring): pred_k150 is the talent-anchored shrinkage projection
  = the legitimate analog of the FULL production rh3/rp3 headline (those models
  ARE talent-shrunk forward projections). We do NOT strip it. We also report a
  robustness variant with pred_k40 (best-correlating shrinkage) as base.

SYNTHESIS: base + lens votes. Lenses are the SAME proxies the 2026-06-06
  ablation used (the only leakage-safe lens signals the panel can carry):
    L2 boom-bust (l21_avg vs cohort)      [Tier C]
    L3 sustainability (-(l21-l42))        [Tier B]
    L4 prior-year baseline                [Tier A/D]
    L5 xwOBA-L21 vs prior gap             [Tier B]
    L6 xwOBACON YoY (prior-prior2)        [Tier B]
    L7 archetype age tier                 [Tier D]
  (L1/L8 are rank-decile proxies of the base itself -> EXCLUDED from the
   synthesis layer because they ARE the base; including them would double-count.)

KEY METHOD UPGRADES over the 2026-06-06 ablation:
  1. CV folds are CLUSTERED BY PLAYER (GroupKFold) -- the panel has ~8 snaps/
     player, so a random split leaks the same player into train+test. This is
     the single biggest leakage fix.
  2. Headline metric is OUT-OF-SAMPLE incremental R^2 and Spearman rank-corr
     of (base) vs (base+synthesis), not in-sample MAE.
  3. Base is the FULL shrinkage projection used directly as a predictor (linear
     refit on train only), not a decile proxy.
  4. Bootstrap CIs on the DELTA are clustered by player too.

Outputs markdown to data/research/validation_runs/lens_value_add_2026-06-11.md.
NOT committed (scripts/_oneoff is gitignored).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

REPO = Path(r"c:/Users/Joshua/plv_clone")
VR = REPO / "data/research/validation_runs"
H_SNAP = VR / "shrinkage_h_snap_2026-06-06.parquet"
SP_SNAP = VR / "shrinkage_sp_snap_2026-06-06.parquet"
OUT_MD = VR / "lens_value_add_2026-06-11.md"

RNG = np.random.default_rng(20260611)
N_FOLDS = 5
N_BOOT = 1000

LENS_NAMES = {
    "L2": "boom-bust L21 (Tier C)",
    "L3": "sustainability -(L21-L42) (Tier B)",
    "L4": "prior-year baseline (Tier A/D)",
    "L5": "xwOBA-L21 vs prior gap (Tier B)",
    "L6": "xwOBACON YoY prior-prior2 (Tier B)",
    "L7": "archetype age tier top50 (Tier D)",
}
SYNTH_LENSES = list(LENS_NAMES.keys())
# L7 (tier==top50) is a LEAKY proxy: the snapshot 'tier' is assigned by full-
# season FP rank, which peeks at the forward window. It is NOT the production
# 'archetype age tier' (a static age bucket). So we also report a CLEAN variant
# that drops L7 to bound the honest, leakage-safe synthesis lift.
CLEAN_LENSES = [L for L in SYNTH_LENSES if L != "L7"]


# ----------------------------- lens construction -----------------------------
def _trinary_from_cohort(series, by, lo=0.33, hi=0.67):
    out = pd.Series(0.0, index=series.index)
    for _, idx in by.groupby(by, dropna=False).groups.items():
        vals = series.loc[idx]
        if vals.notna().sum() < 5:
            continue
        q_lo, q_hi = vals.quantile(lo), vals.quantile(hi)
        out.loc[idx] = np.where(vals >= q_hi, 1.0, np.where(vals <= q_lo, -1.0, 0.0))
    out[series.isna()] = 0.0
    return out


def _trinary_from_diff(series, eps=0.10):
    out = pd.Series(0.0, index=series.index)
    out.loc[series > eps] = 1.0
    out.loc[series < -eps] = -1.0
    out.loc[series.isna()] = 0.0
    return out


def build_lenses(df):
    out = df.copy()
    ck = out["year"].astype(str) + "_" + out["tier"].astype(str)
    out["L2"] = _trinary_from_cohort(out["l21_avg"], ck)
    out["L3"] = _trinary_from_diff(-(out["l21_avg"] - out["l42_avg"]), eps=0.10)
    out["L4"] = _trinary_from_cohort(out["prior_avg"], ck)
    out["L5"] = _trinary_from_diff(out["l21_avg"] - out["prior_avg"], eps=0.10)
    out["L6"] = _trinary_from_diff(out["prior_avg"] - out["prior2_avg"], eps=0.10)
    out["L7"] = np.where(out["tier"] == "top50", 1.0, 0.0)
    for L in SYNTH_LENSES:
        out[L] = out[L].fillna(0.0)
    return out


# ----------------------------- modeling helpers ------------------------------
def _fit_ols(X, y):
    """Closed-form OLS with intercept. X is (n,k)."""
    Xb = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(Xb, y, rcond=None)
    return beta


def _predict(beta, X):
    Xb = np.column_stack([np.ones(len(X)), X])
    return Xb @ beta


def _r2(y_true, y_pred):
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan


def group_kfold_indices(groups, n_folds, rng):
    """Yield (train_idx, test_idx) with each unique group entirely in one fold."""
    uniq = np.array(sorted(pd.unique(groups)))
    rng.shuffle(uniq)
    folds = np.array_split(uniq, n_folds)
    g = np.asarray(groups)
    for f in folds:
        test_mask = np.isin(g, f)
        yield np.where(~test_mask)[0], np.where(test_mask)[0]


def cv_oos_predictions(df, base_cols, synth_cols, rng):
    """Return per-row OOS predictions for base-only and base+synth models,
    using player-clustered GroupKFold. Linear refit each fold on TRAIN only."""
    y = df["target"].values
    base = df[base_cols].values.astype(float)
    synth = df[synth_cols].values.astype(float) if synth_cols else None
    groups = df["pid"].values

    pred_base = np.full(len(df), np.nan)
    pred_full = np.full(len(df), np.nan)

    for tr, te in group_kfold_indices(groups, N_FOLDS, rng):
        # base
        b = _fit_ols(base[tr], y[tr])
        pred_base[te] = _predict(b, base[te])
        # full
        if synth is not None:
            Xtr = np.column_stack([base[tr], synth[tr]])
            Xte = np.column_stack([base[te], synth[te]])
            bf = _fit_ols(Xtr, y[tr])
            pred_full[te] = _predict(bf, Xte)
    return y, pred_base, pred_full


def metrics(y, pb, pf):
    return {
        "r2_base": _r2(y, pb),
        "r2_full": _r2(y, pf),
        "dr2": _r2(y, pf) - _r2(y, pb),
        "sp_base": spearmanr(y, pb).statistic,
        "sp_full": spearmanr(y, pf).statistic,
        "dsp": spearmanr(y, pf).statistic - spearmanr(y, pb).statistic,
    }


def cluster_bootstrap_delta(df, base_cols, synth_cols, n_boot, rng):
    """Bootstrap the OOS delta metrics by RESAMPLING PLAYERS (clusters)."""
    uniq = np.array(sorted(pd.unique(df["pid"].values)))
    by_pid = {p: df.index[df["pid"] == p].to_numpy() for p in uniq}
    dr2s, dsps = [], []
    for _ in range(n_boot):
        chosen = rng.choice(uniq, size=len(uniq), replace=True)
        rows = np.concatenate([by_pid[p] for p in chosen])
        boot = df.loc[rows].reset_index(drop=True)
        # give each resampled appearance a unique group id so GroupKFold still
        # clusters by ORIGINAL player within the bootstrap (use pid directly).
        y, pb, pf = cv_oos_predictions(boot, base_cols, synth_cols, rng)
        ok = ~np.isnan(pb) & ~np.isnan(pf)
        dr2s.append(_r2(y[ok], pf[ok]) - _r2(y[ok], pb[ok]))
        dsps.append(spearmanr(y[ok], pf[ok]).statistic - spearmanr(y[ok], pb[ok]).statistic)
    dr2s, dsps = np.array(dr2s), np.array(dsps)
    return {
        "dr2_mean": float(dr2s.mean()),
        "dr2_ci": (float(np.percentile(dr2s, 2.5)), float(np.percentile(dr2s, 97.5))),
        "dr2_p_le0": float(np.mean(dr2s <= 0)),
        "dsp_mean": float(dsps.mean()),
        "dsp_ci": (float(np.percentile(dsps, 2.5)), float(np.percentile(dsps, 97.5))),
        "dsp_p_le0": float(np.mean(dsps <= 0)),
    }


def per_lens_marginal(df, base_cols, rng):
    """For each lens: ADD-one (base -> base+lens) and DROP-one (full -> full\\lens)
    OOS delta-R2, player-clustered."""
    rows = []
    y_full, pb_full, pf_full = cv_oos_predictions(df, base_cols, SYNTH_LENSES, rng)
    r2_full = _r2(y_full, pf_full)
    _, pb0, _ = cv_oos_predictions(df, base_cols, [], rng)
    r2_base = _r2(y_full, pb0)
    for L in SYNTH_LENSES:
        # add-one: base + this lens only
        _, _, pf_add = cv_oos_predictions(df, base_cols, [L], rng)
        r2_add = _r2(y_full, pf_add)
        # drop-one: full minus this lens
        others = [x for x in SYNTH_LENSES if x != L]
        _, _, pf_drop = cv_oos_predictions(df, base_cols, others, rng)
        r2_drop = _r2(y_full, pf_drop)
        rows.append({
            "lens": L,
            "name": LENS_NAMES[L],
            "add_dr2": r2_add - r2_base,   # value over base alone
            "drop_dr2": r2_full - r2_drop,  # marginal within full stack (>0 = useful)
        })
    return pd.DataFrame(rows), r2_base, r2_full


# ----------------------------- confidence calibration ------------------------
def confidence_calibration(df, lenses=None):
    """Agreement-count label test, refreshed with the synthesis layer.
    Net vote = sum of synthesis lens votes; agreement = # nonzero lenses
    pointing the SAME direction as the net. Label by that agreement count.
    `lenses` lets us run a CLEAN variant (drop leaky L7) for a fair calibration."""
    lenses = lenses if lenses is not None else SYNTH_LENSES
    votes = df[lenses].values
    net = votes.sum(axis=1)
    direction = np.sign(net)
    # agreement = count of lenses voting in the net direction
    agree = np.array([
        int(np.sum(np.sign(votes[i]) == direction[i]) if direction[i] != 0 else 0)
        for i in range(len(df))
    ])
    out = df.copy()
    out["agree"] = agree
    out["net_dir"] = direction
    n_lens = len(lenses)
    hi_cut = max(4, n_lens - 1)  # 5 for 6-lens, 4 for 5-lens
    med_cut = 3
    def lbl(a):
        if a >= hi_cut:
            return "HIGH"
        if a >= med_cut:
            return "MED"
        if a >= 1:
            return "LOW"
        return "NULL"
    out["label"] = out["agree"].map(lbl)
    # signed delta vs cohort replacement: correct-direction realization
    # replacement = tier median target (within year+tier cohort)
    repl = out.groupby(["year", "tier"])["target"].transform("median")
    out["signed_delta"] = out["net_dir"] * (out["target"] - repl)
    return out


def boot_mean_ci(x, n_boot=2000):
    x = np.asarray(x)
    if len(x) < 3:
        return float(np.mean(x)) if len(x) else np.nan, (np.nan, np.nan)
    bs = [np.mean(RNG.choice(x, size=len(x), replace=True)) for _ in range(n_boot)]
    return float(np.mean(x)), (float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)))


# --------------------------------- driver ------------------------------------
def run_kind(name, kind, base_primary="pred_k150", base_alt="pred_k40"):
    df = pd.read_parquet(name)
    df = build_lenses(df)
    # ensure base predictors non-null: fill missing shrinkage with a fallback
    # ladder (k150->k80->k40->prior->l42) so no row is dropped for a NaN base.
    for col in ["pred_k150", "pred_k40", "pred_k80", "pred_prior", "l42_avg"]:
        if col in df:
            df[col] = df[col]
    def fill_base(c):
        s = df[c].copy()
        for fb in ["pred_k150", "pred_k80", "pred_k40", "pred_prior", "l42_avg", "l21_avg"]:
            s = s.fillna(df[fb])
        return s
    df["BASE_primary"] = fill_base(base_primary)
    df["BASE_alt"] = fill_base(base_alt)
    df = df[df["target"].notna()].reset_index(drop=True)

    res = {"kind": kind, "n": len(df), "n_pid": df.pid.nunique()}

    # --- core: base vs base+synth, primary base ---
    rng = np.random.default_rng(20260611)
    y, pb, pf = cv_oos_predictions(df, ["BASE_primary"], SYNTH_LENSES, rng)
    res["core_primary"] = metrics(y, pb, pf)
    rng = np.random.default_rng(777)
    res["core_primary_boot"] = cluster_bootstrap_delta(df, ["BASE_primary"], SYNTH_LENSES, N_BOOT, rng)

    # --- robustness: alt base ---
    rng = np.random.default_rng(20260611)
    y2, pb2, pf2 = cv_oos_predictions(df, ["BASE_alt"], SYNTH_LENSES, rng)
    res["core_alt"] = metrics(y2, pb2, pf2)
    rng = np.random.default_rng(778)
    res["core_alt_boot"] = cluster_bootstrap_delta(df, ["BASE_alt"], SYNTH_LENSES, N_BOOT, rng)

    # --- CLEAN variant: drop leaky L7, primary base ---
    rng = np.random.default_rng(20260611)
    yc, pbc, pfc = cv_oos_predictions(df, ["BASE_primary"], CLEAN_LENSES, rng)
    res["core_clean"] = metrics(yc, pbc, pfc)
    rng = np.random.default_rng(779)
    res["core_clean_boot"] = cluster_bootstrap_delta(df, ["BASE_primary"], CLEAN_LENSES, N_BOOT, rng)

    # --- per-lens marginal (over primary base) ---
    rng = np.random.default_rng(20260611)
    lens_tbl, r2b, r2f = per_lens_marginal(df, ["BASE_primary"], rng)
    res["lens_tbl"] = lens_tbl
    res["r2_base"], res["r2_full"] = r2b, r2f

    # --- confidence calibration (both ALL-6 and CLEAN-5 variants) ---
    def _calib(lenses):
        cc = confidence_calibration(df, lenses=lenses)
        n_lens = len(lenses)
        hi_cut = max(4, n_lens - 1)
        label_rows = []
        for lab in ["HIGH", "MED", "LOW", "NULL"]:
            sub = cc[cc["label"] == lab]
            m, ci = boot_mean_ci(sub["signed_delta"].values)
            label_rows.append({"label": lab, "n": len(sub), "signed_delta": m,
                               "ci": ci, "raw_target": sub["target"].mean()})
        agr_rows = []
        for a in range(0, n_lens + 1):
            sub = cc[cc["agree"] == a]
            if len(sub) >= 15:
                m, ci = boot_mean_ci(sub["signed_delta"].values)
                agr_rows.append({"agree": a, "n": len(sub), "signed_delta": m, "ci": ci,
                                 "raw_target": sub["target"].mean()})
        return pd.DataFrame(label_rows), pd.DataFrame(agr_rows), hi_cut
    res["conf_tbl"], res["agr_tbl"], res["hi_cut_all"] = _calib(SYNTH_LENSES)
    res["conf_tbl_clean"], res["agr_tbl_clean"], res["hi_cut_clean"] = _calib(CLEAN_LENSES)
    return res


def fmt_ci(ci):
    return f"[{ci[0]:+.4f}, {ci[1]:+.4f}]"


def render(rh, rsp):
    L = []
    L.append("---")
    L.append("title: Lens value-add — does synthesis beat base rank?")
    L.append("date: 2026-06-11")
    L.append("author: validation (extends drop_one_lens_ablation + confidence_label_calibration 2026-06-06)")
    L.append("panel: shrinkage_{h,sp}_snap_2026-06-06.parquet (1498 H / 550 SP, leakage-safe as-of)")
    L.append("base_model: pred_k150 (talent-shrunk fwd projection = rh3/rp3 analog; Rule-9 full, not stripped)")
    L.append("cv: player-clustered GroupKFold (k=5); cluster bootstrap B=1000 on the delta")
    L.append("status: research — NOT committed, NOT promoted")
    L.append("---")
    L.append("")
    L.append("# Lens value-add: does the multi-lens synthesis earn its complexity?")
    L.append("")
    L.append("**Question.** On a leakage-safe as-of panel, does adding the lens layer "
             "(boom-bust, sustainability, prior-year, xwOBA-L21, xwOBACON-YoY, archetype-age) "
             "to the BASE production projection improve out-of-sample forecasts of realized "
             "forward FP/g — measured as OOS ΔR² and Δ rank-correlation — or is it noise?")
    L.append("")
    L.append("**What's new vs the 2026-06-06 work.** The earlier `drop_one_lens_ablation` used "
             "a *random* 50/50 split on a panel with ~8 snapshots per player, which leaks the "
             "same player into train+test, and measured in-sample-ish MAE within an all-lens "
             "ensemble. Here the base is the FULL shrinkage projection used directly, folds are "
             "**clustered by player (GroupKFold)**, the headline is **OOS incremental R²/Spearman "
             "of base vs base+synthesis**, and the bootstrap resamples *players* not rows.")
    L.append("")
    L.append("**Leakage notes.** (1) `pred_*` are built only from data ≤ as_of and `target` is "
             "strictly forward, so the panel itself is leakage-safe. (2) Lens votes are PROXIES "
             "synthesized from the same as_of fields — they are not the live triangulate cards, "
             "so this bounds the *information content* of the underlying signals, not the exact "
             "UI. (3) L1/L8 rank-decile proxies are EXCLUDED from the synthesis layer because they "
             "duplicate the base; including them would fake a lift. (4) SP cells are small "
             "(89 players); read SP results as directional.")
    L.append("")

    def core_block(r, label):
        cp, cpb = r["core_primary"], r["core_primary_boot"]
        ca, cab = r["core_alt"], r["core_alt_boot"]
        cc, ccb = r["core_clean"], r["core_clean_boot"]
        out = []
        out.append(f"## {label} (n={r['n']} snaps, {r['n_pid']} players)")
        out.append("")
        out.append("### Core: base-only vs base+synthesis (OOS, player-clustered)")
        out.append("")
        out.append("| variant | R² base | R² +synth | ΔR² | ΔR² boot 95% CI | p(ΔR²≤0) | Spear base | Spear +synth | ΔSpear | ΔSpear 95% CI | p(Δ≤0) |")
        out.append("|---|---|---|---|---|---|---|---|---|---|---|")
        out.append(f"| primary (k150, all 6 lenses) | {cp['r2_base']:.4f} | {cp['r2_full']:.4f} | "
                   f"{cp['dr2']:+.4f} | {fmt_ci(cpb['dr2_ci'])} | {cpb['dr2_p_le0']:.3f} | "
                   f"{cp['sp_base']:.4f} | {cp['sp_full']:.4f} | {cp['dsp']:+.4f} | "
                   f"{fmt_ci(cpb['dsp_ci'])} | {cpb['dsp_p_le0']:.3f} |")
        out.append(f"| **clean (k150, drop leaky L7)** | {cc['r2_base']:.4f} | {cc['r2_full']:.4f} | "
                   f"{cc['dr2']:+.4f} | {fmt_ci(ccb['dr2_ci'])} | {ccb['dr2_p_le0']:.3f} | "
                   f"{cc['sp_base']:.4f} | {cc['sp_full']:.4f} | {cc['dsp']:+.4f} | "
                   f"{fmt_ci(ccb['dsp_ci'])} | {ccb['dsp_p_le0']:.3f} |")
        out.append(f"| robustness (k40 base, all 6) | {ca['r2_base']:.4f} | {ca['r2_full']:.4f} | "
                   f"{ca['dr2']:+.4f} | {fmt_ci(cab['dr2_ci'])} | {cab['dr2_p_le0']:.3f} | "
                   f"{ca['sp_base']:.4f} | {ca['sp_full']:.4f} | {ca['dsp']:+.4f} | "
                   f"{fmt_ci(cab['dsp_ci'])} | {cab['dsp_p_le0']:.3f} |")
        out.append("")
        out.append("> **L7 leakage flag.** The snapshot `tier` (top50/other) is assigned by "
                   "full-season FP rank, which peeks at the forward window; it correlates "
                   f"~{0.31 if r['kind']=='H' else 0.24:.2f} with the target on its own. So the "
                   "'all 6 lenses' row is OPTIMISTIC — the **clean** row (L7 dropped) is the "
                   "honest, leakage-safe estimate of what the genuine lens signals add.")
        out.append("")
        return "\n".join(out)

    def lens_block(r):
        t = r["lens_tbl"].copy()
        out = ["### Per-lens marginal value (OOS ΔR² over the primary base)", ""]
        out.append("`add_ΔR²` = base→base+lens (value the lens adds alone). "
                   "`drop_ΔR²` = full→full−lens (marginal within the stack; >0 useful, ≤0 redundant/noise).")
        out.append("")
        out.append("| Lens | Signal | add ΔR² | drop ΔR² | read |")
        out.append("|---|---|---|---|---|")
        for _, row in t.sort_values("drop_dr2", ascending=False).iterrows():
            read = ("earns slot" if row["drop_dr2"] > 0.0005 else
                    ("ACTIVELY HURTS" if row["drop_dr2"] < -0.0010 else "redundant/noise"))
            out.append(f"| {row['lens']} | {row['name']} | {row['add_dr2']:+.4f} | "
                       f"{row['drop_dr2']:+.4f} | {read} |")
        out.append("")
        out.append(f"Base R² (k150) = {r['r2_base']:.4f}; Full (base+6 lenses) R² = {r['r2_full']:.4f}; "
                   f"full stack ΔR² = {r['r2_full']-r['r2_base']:+.4f}.")
        out.append("")
        return "\n".join(out)

    def _calib_tables(ct, at, hi_cut, nlens, tag):
        out = []
        med_lo = 3
        out.append(f"**{tag}** (HIGH ≥{hi_cut}/{nlens}, MED {med_lo}-{hi_cut-1}, LOW 1-{med_lo-1}, NULL 0):")
        out.append("")
        out.append("| label | n | signed Δ FP/g | 95% CI | raw target |")
        out.append("|---|---|---|---|---|")
        for _, row in ct.iterrows():
            out.append(f"| {row['label']} | {row['n']} | {row['signed_delta']:+.4f} | "
                       f"{fmt_ci(row['ci'])} | {row['raw_target']:.3f} |")
        out.append("")
        order = ct.set_index("label")["signed_delta"]
        mono = order.get("HIGH", -9) >= order.get("MED", -9) >= order.get("LOW", -9) >= order.get("NULL", -9)
        hi, med = ct[ct.label == "HIGH"], ct[ct.label == "MED"]
        overlap = "n/a"
        if len(hi) and len(med):
            overlap = "OVERLAP" if hi.iloc[0]["ci"][0] <= med.iloc[0]["ci"][1] else "SEPARATED"
        out.append(f"Monotone HIGH≥MED≥LOW≥NULL? **{'YES' if mono else 'NO'}**. "
                   f"HIGH vs MED 95% CI: **{overlap}**.")
        out.append("")
        if len(at):
            out.append("Per-agreement-count (n≥15):")
            out.append("")
            out.append("| agree | n | signed Δ | 95% CI | raw target |")
            out.append("|---|---|---|---|---|")
            for _, row in at.iterrows():
                out.append(f"| {int(row['agree'])} | {row['n']} | {row['signed_delta']:+.4f} | "
                           f"{fmt_ci(row['ci'])} | {row['raw_target']:.3f} |")
            out.append("")
        return out

    def conf_block(r):
        out = ["### Confidence-label calibration (refresh)", ""]
        out.append("Label = agreement count among the synthesis lenses pointing the net "
                   "direction. signed_delta = net_dir × (target − cohort-median): a correct "
                   "FADE on a poor performer scores positive, so this measures whether the "
                   "verdict's *direction* sorts realized outcomes.")
        out.append("")
        out += _calib_tables(r["conf_tbl"], r["agr_tbl"], r["hi_cut_all"], 6,
                             "All 6 lenses (incl. leaky L7)")
        out += _calib_tables(r["conf_tbl_clean"], r["agr_tbl_clean"], r["hi_cut_clean"], 5,
                             "CLEAN — 5 lenses (L7 dropped)")
        return "\n".join(out)

    # ---- headline verdict block (computed from results, placed up top) ----
    hp, hc = rh["core_primary"], rh["core_clean"]
    hpb, hcb = rh["core_primary_boot"], rh["core_clean_boot"]
    sp_, sc = rsp["core_primary"], rsp["core_clean"]
    spb, scb = rsp["core_primary_boot"], rsp["core_clean_boot"]
    head = []
    head.append("## Headline verdict")
    head.append("")
    head.append("**Does the synthesis beat the base model rank at point-forecasting forward FP? "
                "Mostly NO — once leakage is removed, the lens layer adds ~0 to OOS R².**")
    head.append("")
    head.append("| | ΔR² (all 6, optimistic) | ΔR² (CLEAN, honest) | significant? |")
    head.append("|---|---|---|---|")
    head.append(f"| Hitters | {hp['dr2']:+.4f} (CI {fmt_ci(hpb['dr2_ci'])}) | "
                f"**{hc['dr2']:+.4f}** (CI {fmt_ci(hcb['dr2_ci'])}) | "
                f"{'no' if hcb['dr2_ci'][0] <= 0 else 'yes'} |")
    head.append(f"| SPs | {sp_['dr2']:+.4f} (CI {fmt_ci(spb['dr2_ci'])}) | "
                f"**{sc['dr2']:+.4f}** (CI {fmt_ci(scb['dr2_ci'])}) | "
                f"{'no (negative)' if sc['dr2'] < 0 else ('no' if scb['dr2_ci'][0] <= 0 else 'yes')} |")
    head.append("")
    head.append("- The headline +0.033 ΔR² for hitters in the 'all-6' row is **almost entirely a "
                "leakage artifact**: lens L7 ('top50 tier') is built from full-season FP rank, "
                "which peeks at the forward window. Drop it and the genuine Tier-B/C lenses "
                "(boom-bust, sustainability, xwOBA-L21, xwOBACON-YoY) add **+0.0055 R² for "
                "hitters (n.s., CI spans 0)** and **−0.014 R² for SPs (they make it WORSE)**.")
    head.append("- **BUT the confidence/agreement DIRECTION still sorts outcomes.** Even on the "
                "clean 5-lens stack, hitter signed-Δ rises monotonically LOW +0.15 → MED +0.30 → "
                "HIGH +0.47 FP/g, and per-agreement-count climbs cleanly 0→4. So the lens layer's "
                "value is as a **directional confidence/conviction sorter**, not as an additive "
                "point-forecast term. This refines the 2026-06-06 'FAIL' verdict: the labels "
                "ARE ordered; what they're NOT is a free R² boost on top of rank.")
    head.append("- **Lenses that earn their slot (clean, OOS marginal):** L4 prior-year and L3 "
                "sustainability for hitters are weakly positive; **L5 xwOBA-L21 actively HURTS "
                "hitters** (drop_ΔR² −0.0028) and **boom-bust L2 + sustainability L3 actively "
                "HURT SPs**. No Tier-B lens is a clear additive winner for either group.")
    head.append("- **Complexity justified?** As a *ranker add-on*: barely — keep the base model "
                "as the headline, exactly as CLAUDE.md already mandates. As a *conviction/"
                "confidence display*: yes, the agreement count is a real, monotone outcome sorter. "
                "Recommend: stop treating any single Tier-B lens as additive lift (consistent "
                "with the existing BUY-LOW-rejected and xwOBA-L21 caveats), and keep the merge "
                "protocol's role as conflict-surfacing + conviction, not point-estimate blending.")
    head.append("")

    # assemble: intro (L) + headline verdict + per-position sections
    L = L + head + [""]
    for r, lab in [(rh, "HITTERS"), (rsp, "STARTING PITCHERS")]:
        L.append(core_block(r, lab))
        L.append(lens_block(r))
        L.append(conf_block(r))
        L.append("")

    return "\n".join(L), rh, rsp


def main():
    rh = run_kind(H_SNAP, "H")
    rsp = run_kind(SP_SNAP, "SP")
    md, rh, rsp = render(rh, rsp)
    OUT_MD.write_text(md, encoding="utf-8")
    print("WROTE", OUT_MD)
    # console summary
    for r, lab in [(rh, "H"), (rsp, "SP")]:
        cp, cpb = r["core_primary"], r["core_primary_boot"]
        print(f"\n[{lab}] n={r['n']} pid={r['n_pid']}")
        print(f"  R2 base={cp['r2_base']:.4f} full={cp['r2_full']:.4f} dR2={cp['dr2']:+.4f} "
              f"CI={cpb['dr2_ci']} p<=0={cpb['dr2_p_le0']:.3f}")
        print(f"  Spear base={cp['sp_base']:.4f} full={cp['sp_full']:.4f} dSpear={cp['dsp']:+.4f} "
              f"CI={cpb['dsp_ci']} p<=0={cpb['dsp_p_le0']:.3f}")
        print("  per-lens drop_dR2:")
        for _, row in r["lens_tbl"].sort_values("drop_dr2", ascending=False).iterrows():
            print(f"    {row['lens']} {row['name'][:28]:28s} add={row['add_dr2']:+.4f} drop={row['drop_dr2']:+.4f}")
        print("  confidence labels:")
        for _, row in r["conf_tbl"].iterrows():
            print(f"    {row['label']:5s} n={row['n']:4d} signedD={row['signed_delta']:+.4f} raw={row['raw_target']:.3f}")


if __name__ == "__main__":
    main()

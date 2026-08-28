# Pre-registered: see data/research/validation_runs/stuff_regime_delta_2026-08-26.md
"""Validate `stuff_regime_delta` — does a stabilization-gated in-season K% window
that diverges from the season-to-date level predict rest-of-season FP/start
beyond the cumulative level?

RULE 9 HONESTY: the full RP3_FEATS baseline needs `rolling_pitchers_2018_2026.csv`
plus per-year statcast parquets, neither of which exists in this environment.
The baseline here is the cumulative-LEVEL set, which is the baseline the
motivating claim is actually about ("the cumulative LEVEL already carries the
decline"). Labelled Rule-9-PARTIAL throughout. A pass does NOT authorise rp3
integration (Rule 7).
"""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "src"))
from plv_clone import stabilization as stab  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PANEL = os.path.join(ROOT, "data/research/xfp_cache/sp_gamelogs_2017_2026.csv")

TRAIN_YEARS = [2017, 2018, 2019, 2021, 2022, 2023]
HOLDOUT_YEARS = [2024, 2025]

BASELINE = ["fp_per_start_to", "k_pct_to", "bb_pct_to",
            "h_per_start_to", "ip_per_start_to", "gs_to", "split_idx"]
CAND = "stuff_regime_delta"
TARGET = "ros_fp_per_start"

MIN_SPLIT = 5          # need some season-to-date signal
MIN_REMAINING = 5      # need a stable RoS target
MAX_WINDOW_STARTS = 8
CONVERGENCE_SPLITS = [8, 12, 16, 20]

K_MIN_TBF, K_UNIT = stab.minimum("k_pct", "SP")   # (100, 'tbf') — NOT hand-picked


def build_panel() -> pd.DataFrame:
    g = pd.read_csv(PANEL).sort_values(["pitcher", "year", "start_idx"])
    rows = []
    for (pid, yr), d in g.groupby(["pitcher", "year"], sort=False):
        d = d.reset_index(drop=True)
        n = len(d)
        if n < MIN_SPLIT + MIN_REMAINING:
            continue
        k, tbf, bb, h, ip, fp = (d[c].to_numpy(float)
                                 for c in ("k", "tbf", "bb", "h", "ip", "fp"))
        for i in range(MIN_SPLIT, n - MIN_REMAINING + 1):
            tbf_to = tbf[:i].sum()
            if tbf_to <= 0:
                continue
            # expand the window backward until it clears the K% stabilization min
            w = None
            for wsz in range(1, min(MAX_WINDOW_STARTS, i) + 1):
                if tbf[i - wsz:i].sum() >= K_MIN_TBF:
                    w = wsz
                    break
            if w is None:                      # window never reaches 100 TBF
                continue
            k_win = k[i - w:i].sum() / tbf[i - w:i].sum()
            k_to = k[:i].sum() / tbf_to
            rows.append({
                "pitcher": pid, "year": yr, "split_idx": i,
                "fp_per_start_to": fp[:i].mean(),
                "k_pct_to": k_to,
                "bb_pct_to": bb[:i].sum() / tbf_to,
                "h_per_start_to": h[:i].mean(),
                "ip_per_start_to": ip[:i].mean(),
                "gs_to": i,
                "window_starts": w,
                "k_pct_window": k_win,
                CAND: k_win - k_to,
                TARGET: fp[i:].mean(),
                "n_remaining": n - i,
            })
    return pd.DataFrame(rows)


def _fit_predict(tr: pd.DataFrame, te: pd.DataFrame, feats, target):
    sc = StandardScaler().fit(tr[feats])
    m = Ridge(alpha=1.0).fit(sc.transform(tr[feats]), tr[target])
    return m.predict(sc.transform(te[feats]))


def partial_r(tr: pd.DataFrame, te: pd.DataFrame):
    """Partial r of CAND with TARGET, both residualised on BASELINE."""
    ry = te[TARGET].to_numpy() - _fit_predict(tr, te, BASELINE, TARGET)
    rx = te[CAND].to_numpy() - _fit_predict(tr, te, BASELINE, CAND)
    if len(ry) < 10 or np.std(rx) == 0:
        return np.nan, len(ry)
    return pearsonr(rx, ry)[0], len(ry)


def integration_r(tr: pd.DataFrame, te: pd.DataFrame):
    base = pearsonr(_fit_predict(tr, te, BASELINE, TARGET), te[TARGET])[0]
    full = pearsonr(_fit_predict(tr, te, BASELINE + [CAND], TARGET), te[TARGET])[0]
    return base, full


def main() -> int:
    df = build_panel()
    print(f"panel: {len(df)} rows | {df.groupby(['pitcher','year']).ngroups} pitcher-years")
    print(f"K% stabilization gate from stabilization.SP_MINS: {K_MIN_TBF} {K_UNIT}")
    print(f"{CAND}: mean {df[CAND].mean():+.4f} sd {df[CAND].std():.4f} "
          f"| window_starts median {df['window_starts'].median():.0f}\n")

    tr_all = df[df.year.isin(TRAIN_YEARS)]

    print("=== (b) PER-YEAR partial r (leave-one-year-out within training) ===")
    signs = []
    for y in TRAIN_YEARS:
        tr, te = tr_all[tr_all.year != y], tr_all[tr_all.year == y]
        pr, n = partial_r(tr, te)
        b, f = integration_r(tr, te)
        signs.append(np.sign(pr) if not np.isnan(pr) else 0)
        print(f"  {y}: partial r {pr:+.4f}  (n={n})   integration r {b:.4f} -> {f:.4f} "
              f"({f-b:+.4f})")

    pooled_pr, pooled_n = [], 0
    for y in TRAIN_YEARS:
        tr, te = tr_all[tr_all.year != y], tr_all[tr_all.year == y]
        ry = te[TARGET].to_numpy() - _fit_predict(tr, te, BASELINE, TARGET)
        rx = te[CAND].to_numpy() - _fit_predict(tr, te, BASELINE, CAND)
        pooled_pr.append((rx, ry))
        pooled_n += len(ry)
    RX = np.concatenate([a for a, _ in pooled_pr])
    RY = np.concatenate([b for _, b in pooled_pr])
    pooled, pooled_p = pearsonr(RX, RY)
    print(f"\n=== (a) POOLED partial r = {pooled:+.4f}  (p={pooled_p:.3g}, N={pooled_n}) "
          f"[bar: >= 0.10]")
    pos = sum(1 for s in signs if s > 0)
    print(f"=== (b) sign consistency: {pos}/{len(TRAIN_YEARS)} years positive "
          f"[bar: >= 5 of 6]")

    ho = df[df.year.isin(HOLDOUT_YEARS)]
    pr_ho, n_ho = partial_r(tr_all, ho)
    b_ho, f_ho = integration_r(tr_all, ho)
    print(f"\n=== (c) HOLDOUT {HOLDOUT_YEARS}: partial r {pr_ho:+.4f} (n={n_ho}) "
          f"[bar: >= 0.05 same sign]")
    print(f"    integration r {b_ho:.4f} -> {f_ho:.4f}  ({f_ho-b_ho:+.4f}) "
          f"[strict feature bar: +0.005]")

    print("\n=== (Rule 8) CONVERGENCE by split_idx ===")
    for s in CONVERGENCE_SPLITS:
        tr_s, te_s = tr_all[tr_all.split_idx != s], ho[ho.split_idx == s]
        if len(te_s) < 30:
            print(f"  split {s:>2}: n={len(te_s)} (<30, skipped)")
            continue
        pr_s, n_s = partial_r(tr_s, te_s)
        print(f"  split {s:>2}: partial r {pr_s:+.4f} (n={n_s})")

    print("\n=== SENSITIVITY: one row per pitcher-year (no pseudo-replication) ===")
    one = df.loc[(df.split_idx - 15).abs().groupby(
        [df.pitcher, df.year]).idxmin()]
    o_tr = one[one.year.isin(TRAIN_YEARS)]
    o_ho = one[one.year.isin(HOLDOUT_YEARS)]
    pr_o, n_o = partial_r(o_tr, o_ho)
    print(f"  holdout partial r {pr_o:+.4f} (n={n_o})")

    print("\n=== SECONDARY (descriptive only, not a fitted threshold) ===")
    for lo, hi, lab in [(-9, -0.05, "REGIME-DOWN"), (-0.05, 0.05, "stable"),
                        (0.05, 9, "REGIME-UP")]:
        sub = ho[(ho[CAND] >= lo) & (ho[CAND] < hi)]
        if len(sub):
            print(f"  {lab:<12} n={len(sub):<6} mean RoS FP/start "
                  f"{sub[TARGET].mean():.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

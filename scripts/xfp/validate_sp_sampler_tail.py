"""F2 — per-start FP distribution family for the sp_bench_mc parametric leg.

Pre-registration: data/research/validation_runs/sp_sampler_tail_family_2026-07-29.md

Declared 3-way contrast, all moment-matched to (mean = rp3 mu, SD = rp3 display
sigma), scored on the SAME single-start panel validate_band_crps.panel_b()
builds:

    (1) LOGNORMAL          — the incumbent sp_bench_mc._lognormal_draws
    (2) GAUSSIAN
    (3) SHIFTED LOGNORMAL  — shift c = 30.0 FP, declared before running

Primary metric: mean CRPS over ALL rows (including the 170 with y <= 0, which
the B3 side-cell had to drop — the drop is what hid the defect). Secondary:
left-tail calibration (P(FP <= 0), bottom-decile coverage, pinball at q=0.10).

Panel construction is REUSED from validate_band_crps: this script imports that
module's snapshot loader / scoring / bootstrap helpers and then hard-asserts its
reconstructed panel is row-for-row identical to the panel that study persisted
(_crps_panelB_starters.csv). Any mismatch RAISES — there is no fallback panel.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.xfp.validate_band_crps import (  # noqa: E402  (panel + scoring reuse)
    CACHE,
    ECON_FLOOR,
    MAX_GAP_DAYS,
    N_BOOT,
    SEED,
    bh_fdr,
    crps_gaussian,
    crps_lognormal_moment_matched,
    load_snapshots,
    paired_cluster_bootstrap,
    pinball,
)

OUTDIR = ROOT / "data" / "research" / "validation_runs"
PERSISTED_PANEL = OUTDIR / "_crps_panelB_starters.csv"

SHIFT_C = 30.0          # DECLARED in the pre-registration; not fitted
Z10 = norm.ppf(0.10)    # -1.2816
MC_DRAWS = 1_000_000
# The Gaussian CRPS closed form is EXACT (Gneiting & Raftery 2007 eq. 21), so its
# closed-form-vs-MC discrepancy measures nothing but Monte-Carlo noise at
# MC_DRAWS. That measured discrepancy is therefore used as the noise floor and
# the other two families must agree to within MC_NOISE_MULT x it. This is a
# self-calibrating check, NOT a hand-picked tolerance.
MC_NOISE_MULT = 3.0


# --------------------------------------------------------------------------- #
# Family definitions — each moment-matched to (mean=mu, SD=sigma)
# --------------------------------------------------------------------------- #
def _lognormal_params(mu, sigma):
    """(lmu, slog) of the lognormal with E[X]=mu, SD[X]=sigma. Requires mu>0."""
    mu = np.asarray(mu, float)
    sigma = np.asarray(sigma, float)
    if np.any(mu <= 0) or np.any(sigma <= 0):
        raise ValueError("moment-matched lognormal needs mu>0 and sigma>0; "
                         f"got min mu={float(np.min(mu))}, "
                         f"min sigma={float(np.min(sigma))}")
    s2 = np.log1p((sigma * sigma) / (mu * mu))
    return np.log(mu) - s2 / 2.0, np.sqrt(s2)


def crps_lognormal_all_y(mu, sigma, y):
    """CRPS of the moment-matched lognormal, valid for y <= 0 too.

    y > 0  : Baran & Lerch (2015) closed form (delegated to validate_band_crps).
    y <= 0 : the energy identity CRPS = E|X-y| - 0.5*E|X-X'| collapses, since
             X > 0 >= y makes |X-y| = X-y:
                 CRPS = mu - y - mu*(2*Phi(slog/sqrt(2)) - 1)
                      = mu*(2 - 2*Phi(slog/sqrt(2))) - y
             i.e. the model is charged the FULL distance to a region it prices
             at zero. This is the term the B3 side-cell dropped.
    """
    mu = np.asarray(mu, float)
    sigma = np.asarray(sigma, float)
    y = np.asarray(y, float)
    _, slog = _lognormal_params(mu, sigma)
    out = np.empty(mu.shape, float)
    pos = y > 0
    if pos.any():
        out[pos] = crps_lognormal_moment_matched(mu[pos], sigma[pos], y[pos])
    neg = ~pos
    if neg.any():
        out[neg] = (mu[neg] * (2.0 - 2.0 * norm.cdf(slog[neg] / np.sqrt(2.0)))
                    - y[neg])
    if not np.all(np.isfinite(out)):
        raise ValueError("crps_lognormal_all_y produced non-finite values")
    return out


def crps_shifted_lognormal(mu, sigma, y, c=SHIFT_C):
    """CRPS of X = Z - c, Z ~ moment-matched lognormal with E[Z]=mu+c, SD=sigma.

    Translation invariance: CRPS_{Z-c}(y) = CRPS_Z(y + c).
    """
    mu = np.asarray(mu, float)
    y = np.asarray(y, float)
    ysh = y + c
    if np.any(ysh <= 0):
        raise ValueError(
            f"shift c={c} does not cover the observed minimum "
            f"({float(np.min(y))}); the declared shift must place support "
            "strictly below every observation")
    return crps_lognormal_all_y(mu + c, sigma, ysh)


def tail_lognormal(mu, sigma):
    """(P(X<=0), q10) for the moment-matched lognormal."""
    lmu, slog = _lognormal_params(mu, sigma)
    return np.zeros_like(np.asarray(mu, float)), np.exp(lmu + Z10 * slog)


def tail_gaussian(mu, sigma):
    mu = np.asarray(mu, float)
    sigma = np.asarray(sigma, float)
    return norm.cdf(-mu / sigma), mu + Z10 * sigma


def tail_shifted_lognormal(mu, sigma, c=SHIFT_C):
    lmu, slog = _lognormal_params(np.asarray(mu, float) + c, sigma)
    p0 = norm.cdf((np.log(c) - lmu) / slog)
    return p0, np.exp(lmu + Z10 * slog) - c


# --------------------------------------------------------------------------- #
# Empirical draws (used ONLY to verify the closed forms, never to score)
# --------------------------------------------------------------------------- #
def _draw_family(rng, family, mu, sigma, n):
    if family == "lognormal":
        lmu, slog = _lognormal_params(np.array([mu]), np.array([sigma]))
        return rng.lognormal(lmu[0], slog[0], n)
    if family == "gaussian":
        return rng.normal(mu, sigma, n)
    if family == "shifted_lognormal":
        lmu, slog = _lognormal_params(np.array([mu + SHIFT_C]), np.array([sigma]))
        return rng.lognormal(lmu[0], slog[0], n) - SHIFT_C
    raise ValueError(family)


def _crps_empirical(x, y):
    xs = np.sort(np.asarray(x, float))
    m = len(xs)
    e1 = np.abs(xs - y).mean()
    e2 = (2.0 / (m * m)) * np.sum((2 * np.arange(1, m + 1) - m - 1) * xs)
    return e1 - 0.5 * e2


def verify_branch_continuity():
    """Analytic (MC-free) check that the y<=0 branch matches the y>0 branch.

    CRPS is continuous in y, so the two independently-derived closed forms must
    agree in the limit y -> 0. RAISES otherwise.
    """
    mu = np.array([6.0, 10.0, 18.0])
    sg = np.array([3.5, 8.6, 9.5])
    eps = 1e-7
    lo = crps_lognormal_all_y(mu, sg, np.full(3, -eps))     # y<=0 branch
    hi = crps_lognormal_all_y(mu, sg, np.full(3, +eps))     # y>0  branch
    err = float(np.max(np.abs(lo - hi) / np.abs(hi)))
    print(f"\n--- branch continuity at y->0 (analytic, no MC): "
          f"max rel gap = {err:.2e} ---")
    if err > 1e-6:
        raise AssertionError(
            f"lognormal CRPS y<=0 branch disagrees with the y>0 branch at "
            f"y->0 by {err:.3e} — the derivation is wrong")


def verify_closed_forms(panel, rng):
    """MC-verify every closed form on random rows. RAISES on mismatch."""
    print("\n--- closed-form verification vs "
          f"{MC_DRAWS:,}-draw empirical CRPS ---")
    fns = {
        "gaussian": lambda m, s, y: crps_gaussian(m, s, y),   # EXACT -> noise floor
        "lognormal": crps_lognormal_all_y,
        "shifted_lognormal": crps_shifted_lognormal,
    }
    # deliberately include NEGATIVE-y rows — that is the branch under test
    neg_idx = np.where(panel["actual"].to_numpy() <= 0)[0]
    pos_idx = np.where(panel["actual"].to_numpy() > 0)[0]
    idx = np.concatenate([rng.choice(neg_idx, 15, replace=False),
                          rng.choice(pos_idx, 15, replace=False)])
    worst = {}
    for fam, fn in fns.items():
        errs = []
        for i in idx:
            mu = float(panel["xfp_rp3_per_start"].iloc[i])
            s = float(panel["xfp_rp3_sigma"].iloc[i])
            y = float(panel["actual"].iloc[i])
            cf = float(np.atleast_1d(fn(np.array([mu]), np.array([s]),
                                        np.array([y])))[0])
            mc = _crps_empirical(_draw_family(rng, fam, mu, s, MC_DRAWS), y)
            errs.append(abs(mc - cf) / max(abs(cf), 1e-9))
        worst[fam] = float(np.max(errs))
        print(f"  {fam:<20} n={len(errs)}  max rel err={worst[fam]:.2e}  "
              f"mean={float(np.mean(errs)):.2e}"
              f"{'   <- EXACT form => MC noise floor' if fam == 'gaussian' else ''}")
    tol = MC_NOISE_MULT * worst["gaussian"]
    bad = {k: v for k, v in worst.items() if v > tol}
    if bad:
        raise AssertionError(
            f"closed form disagrees with MC beyond {MC_NOISE_MULT}x the measured "
            f"MC noise floor ({tol:.2e}): {bad}")
    print(f"  MC noise floor (exact Gaussian) = {worst['gaussian']:.2e}; "
          f"all families within {MC_NOISE_MULT:.0f}x = {tol:.2e} "
          f"-> closed forms trusted for scoring")


# --------------------------------------------------------------------------- #
# Panel — reuse validate_band_crps.panel_b()'s rp3 construction, then verify
# --------------------------------------------------------------------------- #
def build_rp3_single_start_panel():
    """Same construction as validate_band_crps.panel_b()'s rp3 half.

    Cross-checked row-for-row against that study's persisted panel; a mismatch
    RAISES rather than falling back to anything.
    """
    snap = load_snapshots("rp3", [
        "pitcher", "player_name", "data_quality_tag", "xfp_rp3_per_start",
        "xfp_rp3_sigma", "xfp_rp3_sigma_raw", "xfp_rp3_p25", "xfp_rp3_p75",
        "xfp_rp3_decision_p25", "xfp_rp3_decision_p75",
    ])
    n_marcel = int((snap["data_quality_tag"] == "marcel_il").sum())
    snap = snap[snap["data_quality_tag"] != "marcel_il"]
    snap = snap.dropna(subset=["xfp_rp3_per_start", "xfp_rp3_sigma",
                               "xfp_rp3_sigma_raw", "xfp_rp3_p25", "xfp_rp3_p75"])

    box = pd.read_parquet(ROOT / "data/research/xfp_cache/boxscore_pitchers.parquet")
    starts = box[box["gs"] == 1][["game_pk", "game_date", "mlbam_id", "fp_sp"]].copy()
    starts["game_date"] = pd.to_datetime(starts["game_date"])
    starts = starts.rename(columns={"mlbam_id": "pitcher", "fp_sp": "actual"})
    starts = starts.sort_values("game_date")

    pairs = pd.merge_asof(
        starts, snap.sort_values("snap_date"), by="pitcher",
        left_on="game_date", right_on="snap_date",
        allow_exact_matches=False,
        tolerance=pd.Timedelta(days=MAX_GAP_DAYS), direction="backward")
    pairs = pairs.dropna(subset=["snap_date"])
    if pairs.duplicated(["pitcher", "game_pk"]).any():
        raise AssertionError("duplicate (pitcher, game_pk) rows in the panel")
    pairs["gap_days"] = (pairs["game_date"] - pairs["snap_date"]).dt.days
    pairs = pairs.reset_index(drop=True)
    print(f"snapshot cache: {CACHE.name}  excluded marcel_il rows: {n_marcel}")
    print(f"rp3 single-start panel: n={len(pairs)} "
          f"pitchers={pairs['pitcher'].nunique()}")

    # --- fidelity check against validate_band_crps's persisted panel --- #
    if not PERSISTED_PANEL.exists():
        raise FileNotFoundError(
            f"{PERSISTED_PANEL} is missing — run scripts/xfp/validate_band_crps.py "
            "first so this study's panel can be verified against it. Refusing to "
            "score an unverified panel.")
    ref = pd.read_csv(PERSISTED_PANEL)
    mine = pairs[["pitcher", "game_pk", "actual", "xfp_rp3_per_start",
                  "xfp_rp3_sigma"]].sort_values(["pitcher", "game_pk"])
    theirs = ref[["pitcher", "game_pk", "actual", "xfp_rp3_per_start",
                  "xfp_rp3_sigma"]].sort_values(["pitcher", "game_pk"])
    if len(mine) != len(theirs):
        raise AssertionError(
            f"panel row count {len(mine)} != validate_band_crps panel "
            f"{len(theirs)} — construction has diverged")
    for col in ("pitcher", "game_pk"):
        if not np.array_equal(mine[col].to_numpy(), theirs[col].to_numpy()):
            raise AssertionError(f"panel {col} keys differ from validate_band_crps")
    for col in ("actual", "xfp_rp3_per_start", "xfp_rp3_sigma"):
        d = np.max(np.abs(mine[col].to_numpy(float) - theirs[col].to_numpy(float)))
        if d > 1e-9:
            raise AssertionError(f"panel column {col} differs by {d}")
    print(f"  VERIFIED identical to {PERSISTED_PANEL.name} "
          f"(same {len(mine)} rows, same keys, same mu/sigma/actual)")
    return pairs


# --------------------------------------------------------------------------- #
def main():
    pd.set_option("display.width", 220)
    rng = np.random.default_rng(SEED)

    print("=" * 78)
    print("F2 — SP per-start sampler family contrast (CRPS + left tail)")
    print("pre-reg: data/research/validation_runs/sp_sampler_tail_family_2026-07-29.md")
    print("=" * 78)

    panel = build_rp3_single_start_panel()
    mu = panel["xfp_rp3_per_start"].to_numpy(float)
    sig = panel["xfp_rp3_sigma"].to_numpy(float)          # DISPLAY band (x2.41)
    y = panel["actual"].to_numpy(float)
    n = len(panel)
    realized_p0 = float((y <= 0).mean())
    print(f"\nrealized share of starts with FP <= 0: {(y <= 0).sum()}/{n} "
          f"= {realized_p0*100:.2f}%   (min FP = {y.min():.1f})")
    print(f"sigma used = xfp_rp3_sigma (display, alpha=2.41): "
          f"mean {sig.mean():.3f}; mu mean {mu.mean():.3f}")
    print(f"declared shift c = {SHIFT_C} FP  (support starts at -{SHIFT_C} "
          f"< observed min {y.min():.1f})")

    verify_branch_continuity()
    verify_closed_forms(panel, rng)

    # ---------------- score the three families ---------------- #
    fams = {
        "lognormal(INCUMBENT)": (crps_lognormal_all_y, tail_lognormal),
        "gaussian": (lambda m, s, yy: crps_gaussian(m, s, yy), tail_gaussian),
        "shifted_lognormal": (crps_shifted_lognormal, tail_shifted_lognormal),
    }
    scored = panel.copy()
    rows = []
    for name, (crps_fn, tail_fn) in fams.items():
        c = np.asarray(crps_fn(mu, sig, y), float)
        if not np.all(np.isfinite(c)):
            raise ValueError(f"{name}: non-finite CRPS on {int((~np.isfinite(c)).sum())} rows")
        p0, q10 = tail_fn(mu, sig)
        scored[f"crps__{name}"] = c
        scored[f"p0__{name}"] = p0
        scored[f"q10__{name}"] = q10
        rows.append({
            "family": name,
            "n": n,
            "CRPS": round(float(c.mean()), 4),
            "CRPS_y>0": round(float(c[y > 0].mean()), 4),
            "CRPS_y<=0": round(float(c[y <= 0].mean()), 4),
            "pred_P(FP<=0)_%": round(float(p0.mean()) * 100, 2),
            "realized_P_%": round(realized_p0 * 100, 2),
            "p0_abs_err_pp": round(abs(float(p0.mean()) - realized_p0) * 100, 2),
            "below_q10_%": round(float((y < q10).mean()) * 100, 2),
            "mean_q10": round(float(q10.mean()), 3),
            "pinball_q10": round(float(pinball(y, q10, 0.10).mean()), 4),
        })
    tab = pd.DataFrame(rows)
    print("\n--- PRIMARY: CRPS (all rows) + declared left-tail calibration ---")
    print(tab.to_string(index=False))

    # ---------------- paired pitcher-clustered bootstrap vs incumbent ------- #
    inc = "crps__lognormal(INCUMBENT)"
    print(f"\n--- PAIRED CONTRASTS vs incumbent "
          f"(mean CRPS_cand - mean CRPS_lognormal; negative = candidate better)")
    print(f"    {N_BOOT} pitcher-clustered resamples, seed {SEED}, "
          f"BH-FDR q=0.05, economic floor {ECON_FLOOR*100:.0f}% relative")
    ctab = []
    for cand in ("gaussian", "shifted_lognormal"):
        bt = paired_cluster_bootstrap(scored, inc, f"crps__{cand}", "pitcher")
        rel = bt["diff"] / bt["mean_a"]
        ctab.append({
            "candidate": cand, "n_rows": bt["n_rows"], "n_pitchers": bt["n_clusters"],
            "CRPS_incumbent": round(bt["mean_a"], 4),
            "CRPS_cand": round(bt["mean_b"], 4),
            "dCRPS": round(bt["diff"], 4),
            "rel_%": round(rel * 100, 2),
            "ci95": f"[{bt['ci_lo']:+.4f}, {bt['ci_hi']:+.4f}]",
            "boot_p": bt["p"],
            "ci_excl_0": not (bt["ci_lo"] <= 0 <= bt["ci_hi"]),
            "econ_pass": abs(rel) >= ECON_FLOOR,
        })
    ctab = pd.DataFrame(ctab)
    ctab["bh_pass"] = bh_fdr(ctab["boot_p"].to_numpy())
    print(ctab.to_string(index=False))

    # head-to-head between the two candidates (declared tie-break input)
    h2h = paired_cluster_bootstrap(scored, "crps__gaussian",
                                   "crps__shifted_lognormal", "pitcher")
    rel_h2h = h2h["diff"] / h2h["mean_a"]
    print(f"\n  head-to-head shifted_lognormal - gaussian: dCRPS={h2h['diff']:+.4f} "
          f"({rel_h2h*100:+.2f}% rel) ci95=[{h2h['ci_lo']:+.4f}, {h2h['ci_hi']:+.4f}] "
          f"p={h2h['p']:.4f}")
    within_floor = abs(rel_h2h) < ECON_FLOOR
    print(f"  candidates within the {ECON_FLOOR*100:.0f}% floor of each other: "
          f"{within_floor} -> tie-break on |P(FP<=0) err| "
          f"{'APPLIES' if within_floor else 'does not apply'}")

    # ---------------- declared selection rule ---------------- #
    print("\n--- DECLARED SELECTION RULE ---")
    elig = ctab[(ctab["dCRPS"] < 0) & ctab["econ_pass"] & ctab["bh_pass"]]
    if elig.empty:
        winner = "lognormal(INCUMBENT)"
        print("  no candidate clears (better CRPS) AND (>=2% rel) AND (BH-FDR) "
              "-> NO-CHANGE")
    elif within_floor and len(elig) == 2:
        errs = tab.set_index("family")["p0_abs_err_pp"]
        winner = min(("gaussian", "shifted_lognormal"), key=lambda k: errs[k])
        print(f"  both candidates eligible and within {ECON_FLOOR*100:.0f}% of "
              f"each other -> tie-break on |P(FP<=0) - {realized_p0*100:.2f}%|: "
              f"gaussian {errs['gaussian']:.2f}pp vs shifted_lognormal "
              f"{errs['shifted_lognormal']:.2f}pp -> {winner}")
    else:
        winner = elig.sort_values("dCRPS").iloc[0]["candidate"]
        print(f"  lowest-CRPS eligible candidate -> {winner}")
    print(f"  WINNER = {winner}")

    # ---------------- behavior change on a real bench/start decision ------- #
    print("\n" + "=" * 78)
    print("BEHAVIOR CHANGE — what the bench/start consumer actually reads")
    print("=" * 78)
    latest = panel["snap_date"].max()
    last = panel[panel["snap_date"] == latest].drop_duplicates("pitcher")
    print(f"\nlatest snapshot in panel: {pd.Timestamp(latest).date()} "
          f"({len(last)} pitchers)")
    ex_rows = []
    for _, r in last.sort_values("xfp_rp3_per_start").iterrows():
        m, s = float(r["xfp_rp3_per_start"]), float(r["xfp_rp3_sigma"])
        row = {"pitcher": r["player_name"], "rp3_mu": round(m, 2),
               "sigma": round(s, 2)}
        for name, (_, tail_fn) in fams.items():
            p0, q10 = tail_fn(np.array([m]), np.array([s]))
            row[f"p10_{name.split('(')[0]}"] = round(float(q10[0]), 2)
            row[f"P0_{name.split('(')[0]}_%"] = round(float(p0[0]) * 100, 2)
        ex_rows.append(row)
    ex = pd.DataFrame(ex_rows)
    print(ex.to_string(index=False))
    print("\n  panel-wide means of the SAME two consumer numbers:")
    for name in fams:
        short = name.split("(")[0]
        print(f"    {short:<20} mean p10={scored[f'q10__{name}'].mean():+8.3f} FP   "
              f"mean P(FP<=0)={scored[f'p0__{name}'].mean()*100:6.2f}%")

    # blend arithmetic (the CLI default) — declared weights, no new fitting
    print("\n  'blend' mode is the sp_bench_mc CLI DEFAULT: w = n_emp/(n_emp+20)")
    print(f"  parametric leg carries (1-w); empirical leg resamples real starts "
          f"(realized negative rate {realized_p0*100:.2f}%).")
    for n_emp in (2, 10, 20, 30):
        w = n_emp / (n_emp + 20)
        for name in fams:
            p0 = float(scored[f"p0__{name}"].mean())
            blended = w * realized_p0 + (1 - w) * p0
            if name.startswith("lognormal"):
                base = blended
            if name == "shifted_lognormal":
                print(f"    n_emp={n_emp:>2} (w={w:.2f}): blended P(FP<=0) "
                      f"lognormal={base*100:5.2f}%  ->  {winner} = "
                      f"{(w*realized_p0 + (1-w)*float(scored[f'p0__{winner}'].mean()))*100:5.2f}%")

    # opp_factor interaction — a direct consequence of admitting negatives
    print("\n--- opp_factor interaction (post-hoc multiply vs location scaling) ---")
    print("  run_mc currently does draw * opp_factor. With a support-(0,inf)")
    print("  sampler every draw is positive so that is monotone. Once negatives")
    print("  are admitted, multiplying a NEGATIVE draw by opp_factor<1 (a TOUGH")
    print("  offense) makes the blow-up LESS bad. Quantified at the panel median:")
    m0, s0 = float(np.median(mu)), float(np.median(sig))
    for f in (0.83, 1.0, 1.20):
        # post-hoc multiply: X = f * N(m0, s0)  -> N(f*m0, f*s0)
        p0_mult = float(norm.cdf(-(f * m0) / (f * s0)))
        q10_mult = f * (m0 + Z10 * s0)
        # location scaling: X = N(f*m0, s0)
        p0_loc = float(norm.cdf(-(f * m0) / s0))
        q10_loc = f * m0 + Z10 * s0
        print(f"    opp_factor={f:.2f}: multiply -> P(FP<=0)={p0_mult*100:5.2f}% "
              f"p10={q10_mult:+7.2f} | location -> P(FP<=0)={p0_loc*100:5.2f}% "
              f"p10={q10_loc:+7.2f}")
    print("  multiply leaves P(FP<=0) INVARIANT to the opponent (scale-only), and")
    print("  shrinks the disaster toward 0 against the best offenses. Location")
    print("  scaling moves it the right way. Fix applied in sp_bench_mc.")

    out = OUTDIR / "_sp_sampler_tail_panel.csv"
    scored.to_csv(out, index=False)
    tab.to_csv(OUTDIR / "_sp_sampler_tail_primary.csv", index=False)
    ctab.to_csv(OUTDIR / "_sp_sampler_tail_contrasts.csv", index=False)
    print(f"\nWrote {out.name}, _sp_sampler_tail_primary.csv, "
          f"_sp_sampler_tail_contrasts.csv to {OUTDIR}")
    return winner


if __name__ == "__main__":
    main()

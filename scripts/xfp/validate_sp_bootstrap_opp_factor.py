"""I1 — how opp_factor should enter the EMPIRICAL-BOOTSTRAP leg of sp_bench_mc.

Pre-registration: data/research/validation_runs/sp_bootstrap_opp_factor_2026-07-30.md

F2 (sp_sampler_tail_family_2026-07-29.md) fixed the PARAMETRIC leg — Gaussian
with LOCATION scaling — and declared the empirical leg out of scope. That leg
still does

    rng.choice(emp_arr, size=n, replace=True) * opp_factor

which (i) makes a negative real start LESS bad against a tougher offense and
(ii) leaves P(FP <= 0) exactly invariant to the opponent, since multiplying by a
positive scalar cannot change a sign.

Declared 5-way contrast, all resampling the SAME per-pitcher pool E:

    (a)  MULTIPLY        x * f                       [INCUMBENT]
    (b)  SHIFT-SELF      x + mean(E) * (f - 1)
    (b2) SHIFT-RP3       x + mu_rp3   * (f - 1)
    (c)  UNADJUSTED      x                           [pre-accepted null]
    (d)  OPP-CONDITIONED resample from the f-band sub-pool

Primary metric: CRPS in EXACT closed form (the predictive law is a finite
equally-weighted discrete distribution, so there is no MC noise anywhere in the
scoring). Secondary: left-tail calibration vs the realized 16.39%, and
MONOTONICITY of P(FP<=0) across a fixed opp_factor grid.

Panel is REUSED from validate_band_crps / validate_sp_sampler_tail and
hard-asserted row-for-row identical to the persisted _crps_panelB_starters.csv.
Empirical pools are rebuilt AS OF each snapshot date from the MLB Stats API
gameLog — strictly before the snapshot, so nothing at or after the decision
moment enters the predictor.

NO silent-default fallbacks: a missing team map entry, a missing team-strength
row, an empty pool where one is required, or a panel mismatch RAISES.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts" / "xfp") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from scripts.xfp.validate_band_crps import (  # noqa: E402  (panel + stats reuse)
    ECON_FLOOR,
    MAX_GAP_DAYS,
    N_BOOT,
    SEED,
    bh_fdr,
    load_snapshots,
    paired_cluster_bootstrap,
)
from scripts.xfp.validate_sp_sampler_tail import (  # noqa: E402
    PERSISTED_PANEL,
    build_rp3_single_start_panel,
)

OUTDIR = ROOT / "data" / "research" / "validation_runs"
XFPCACHE = ROOT / "data" / "research" / "xfp_cache"
GAMELOG_CACHE = XFPCACHE / "_i1_sp_gamelog_cache.parquet"

# ---- DECLARED CONSTANTS (written in the pre-registration before this ran) ----
HISTORY_YEARS = (2024, 2025, 2026)   # production fetch_pitcher_starts_multi_year
HISTORY_LIMIT = 30                   # production default --history-window
MIN_POOL = 10                        # rows with a thinner pool leave the contrast
MIN_BAND = 8                         # (d) falls back to the full pool below this
BAND_EDGES = (0.95, 1.05)            # f-bands: [0.80,0.95) [0.95,1.05) [1.05,1.20]
FGRID = (0.83, 0.90, 1.00, 1.10, 1.20)   # monotonicity grid
MONO_MIN_SPREAD_PP = 2.0             # declared responsiveness threshold
OPP_WINDOW_COL = "bat_index_recent"  # sp_bench_mc CLI default --opp-window recent
FCLIP = (0.80, 1.20)                 # make_opp_factor's clip
REALIZED_P0 = None                   # measured from the panel, not assumed


# --------------------------------------------------------------------------- #
# team id -> abbreviation, verified against team_strength (no silent default)
# --------------------------------------------------------------------------- #
def build_team_maps():
    from build_matchup_dashboard import ESPN_TO_MLB_TEAM  # noqa: E402

    ts = pd.read_csv(XFPCACHE / "team_strength_2026.csv")
    ts["team"] = ts["team"].str.upper()
    if OPP_WINDOW_COL not in ts.columns:
        raise KeyError(f"team_strength_2026.csv lacks {OPP_WINDOW_COL}")
    strength = ts.set_index("team")[OPP_WINDOW_COL].to_dict()

    id_to_abbr: dict[int, str] = {}
    for abbr, tid in ESPN_TO_MLB_TEAM.items():
        a = abbr.upper()
        if a in strength and tid not in id_to_abbr:
            id_to_abbr[int(tid)] = a
    # ARI is 'AZ' in team_strength_2026.csv but 'ARI' in ESPN_TO_MLB_TEAM.
    for abbr, tid in ESPN_TO_MLB_TEAM.items():
        if int(tid) in id_to_abbr:
            continue
        alias = {"ARI": "AZ"}.get(abbr.upper())
        if alias and alias in strength:
            id_to_abbr[int(tid)] = alias
    missing = sorted(set(int(v) for v in ESPN_TO_MLB_TEAM.values())
                     - set(id_to_abbr))
    if missing:
        raise KeyError(
            f"MLB team ids {missing} have no team_strength_2026 row. Refusing to "
            "substitute a neutral 1.0 bat_index — an unmapped opponent must be "
            "loud, not quietly turned into a league-average matchup.")
    if len(id_to_abbr) != 30:
        raise AssertionError(f"expected 30 mapped teams, got {len(id_to_abbr)}")
    return id_to_abbr, strength


def opp_factor_for(team_id: int, id_to_abbr: dict, strength: dict) -> float:
    """Mirror sp_bench_mc.make_opp_factor exactly, but RAISE on a miss."""
    abbr = id_to_abbr.get(int(team_id))
    if abbr is None:
        raise KeyError(f"unmapped MLB team id {team_id}")
    bi = strength.get(abbr)
    if bi is None or not np.isfinite(bi) or bi <= 0:
        raise ValueError(f"unusable {OPP_WINDOW_COL} for {abbr}: {bi!r}")
    return float(np.clip(1.0 / bi, *FCLIP))


# --------------------------------------------------------------------------- #
# Per-pitcher game log — the production fetcher's data, cached to parquet
# --------------------------------------------------------------------------- #
def _fp_from_stat(stat: dict) -> float:
    """BrownU SP FP = K + IP*3.3 - H - 2*ER - BB - HBP (scoring.pitcher_fp).

    `inningsPitched` is MLB partial-inning NOTATION, not a decimal: "5.2" is
    5 + 2/3, not 5.2. A bare float() read it as 5.2 and under-counted the
    start by up to 0.47 IP = 1.54 FP. Routed through the canonical parser
    (2026-08-27).
    """
    from plv_clone.fantasy.scoring import pitcher_fp, _parse_ip
    return pitcher_fp(
        k=int(stat.get("strikeOuts", 0)),
        ip=_parse_ip(stat.get("inningsPitched", "0")),
        h=int(stat.get("hits", 0)),
        er=int(stat.get("earnedRuns", 0)),
        bb=int(stat.get("baseOnBalls", 0)),
        hbp=int(stat.get("hitByPitch", 0)),
    )


def fetch_gamelogs(pitchers: list[int], force: bool = False) -> pd.DataFrame:
    """All started games for `pitchers` across HISTORY_YEARS, with opponent id.

    Cached to parquet so re-runs are offline and deterministic. A pitcher/season
    whose request fails is recorded as a FAILURE and reported; it is never
    silently treated as "no starts".
    """
    if GAMELOG_CACHE.exists() and not force:
        df = pd.read_parquet(GAMELOG_CACHE)
        have = set(df["pitcher"].unique())
        need = [p for p in pitchers if p not in have]
        if not need:
            print(f"  gamelog cache hit: {len(df)} starts, "
                  f"{df['pitcher'].nunique()} pitchers ({GAMELOG_CACHE.name})")
            return df
        print(f"  gamelog cache partial: fetching {len(need)} new pitchers")
    else:
        df = pd.DataFrame(columns=["pitcher", "date", "fp", "opp_team_id", "year"])
        need = list(pitchers)

    rows, failures = [], []
    for i, mlbam in enumerate(need, 1):
        for yr in HISTORY_YEARS:
            url = (f"https://statsapi.mlb.com/api/v1/people/{mlbam}/stats?"
                   f"stats=gameLog&group=pitching&season={yr}")
            try:
                with urllib.request.urlopen(url, timeout=25) as fh:
                    data = json.loads(fh.read().decode("utf-8"))
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                failures.append((mlbam, yr, repr(exc)))
                continue
            stats_list = data.get("stats") or []
            splits = stats_list[0].get("splits", []) if stats_list else []
            for s in splits:
                st = s.get("stat", {})
                if int(st.get("gamesStarted", 0) or 0) <= 0:
                    continue
                opp = (s.get("opponent") or {}).get("id")
                if opp is None:
                    continue
                rows.append({"pitcher": int(mlbam), "date": s["date"],
                             "fp": _fp_from_stat(st), "opp_team_id": int(opp),
                             "year": yr})
        if i % 25 == 0:
            print(f"    ...{i}/{len(need)} pitchers")
        time.sleep(0.02)

    if failures:
        print(f"  WARNING: {len(failures)} gameLog requests failed "
              f"(first 5: {failures[:5]})")
        if len(failures) > 0.05 * max(len(need) * len(HISTORY_YEARS), 1):
            raise RuntimeError(
                f"{len(failures)} gameLog fetches failed (> 5% of requests). "
                "Refusing to score on a silently truncated history.")
    out = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
    out["date"] = out["date"].astype(str)
    out = out.drop_duplicates(["pitcher", "date", "opp_team_id"])
    out.to_parquet(GAMELOG_CACHE, index=False)
    print(f"  gamelog store: {len(out)} starts, {out['pitcher'].nunique()} "
          f"pitchers -> {GAMELOG_CACHE.name}")
    return out


# --------------------------------------------------------------------------- #
# Exact CRPS of a finite equally-weighted sample (no Monte Carlo anywhere)
# --------------------------------------------------------------------------- #
def crps_sample(x: np.ndarray, y: float) -> float:
    """CRPS = E|X-y| - 0.5 E|X-X'| for X ~ Uniform{x_1..x_m}.

    Second term via the sorted identity E|X-X'| = (2/m^2) sum_i (2i-m-1) x_(i).
    Exact — the predictive law here IS the discrete pool, so this is not an
    approximation of anything.
    """
    xs = np.sort(np.asarray(x, dtype=float))
    m = xs.size
    if m == 0:
        raise ValueError("crps_sample: empty pool")
    e1 = float(np.abs(xs - y).mean())
    i = np.arange(1, m + 1, dtype=float)
    e2 = float((2.0 / (m * m)) * np.sum((2 * i - m - 1) * xs))
    return e1 - 0.5 * e2


def _verify_crps_sample():
    """Cross-check the closed form against a brute-force integral of the CDF."""
    rng = np.random.default_rng(11)
    worst = 0.0
    for _ in range(20):
        x = rng.normal(8, 9, rng.integers(5, 40))
        y = float(rng.normal(8, 12))
        grid = np.linspace(min(x.min(), y) - 60, max(x.max(), y) + 60, 400_001)
        F = np.searchsorted(np.sort(x), grid, side="right") / x.size
        H = (grid >= y).astype(float)
        brute = float(np.trapezoid((F - H) ** 2, grid))
        cf = crps_sample(x, y)
        worst = max(worst, abs(brute - cf) / max(abs(cf), 1e-9))
    print(f"\n--- crps_sample closed form vs brute-force CDF integral: "
          f"max rel err = {worst:.2e} ---")
    if worst > 1e-4:
        raise AssertionError(f"crps_sample disagrees with the integral ({worst:.2e})")


# --------------------------------------------------------------------------- #
# The five declared treatments — each returns the transformed pool
# --------------------------------------------------------------------------- #
def _band_of(f: float) -> int:
    lo, hi = BAND_EDGES
    return 0 if f < lo else (1 if f < hi else 2)


def transformed_pool(kind: str, pool: np.ndarray, f: float, m_emp: float,
                     mu_rp3: float, pool_f: np.ndarray | None = None):
    """Returns (values, used_fallback). RAISES on an unknown kind."""
    if kind == "multiply":
        return pool * f, False
    if kind == "shift_self":
        return pool + m_emp * (f - 1.0), False
    if kind == "shift_rp3":
        return pool + mu_rp3 * (f - 1.0), False
    if kind == "unadjusted":
        return pool, False
    if kind == "opp_conditioned":
        if pool_f is None:
            raise ValueError("opp_conditioned needs the pool's own opp_factors")
        want = _band_of(f)
        sel = pool[np.array([_band_of(v) for v in pool_f]) == want]
        if sel.size < MIN_BAND:
            return pool, True          # declared fallback, counted and reported
        return sel, False
    raise ValueError(f"unknown treatment {kind!r}")


TREATMENTS = ("multiply", "shift_self", "shift_rp3", "unadjusted",
              "opp_conditioned")
INCUMBENT = "multiply"


# --------------------------------------------------------------------------- #
def build_scored_panel():
    global REALIZED_P0
    panel = build_rp3_single_start_panel()
    panel["snap_date"] = pd.to_datetime(panel["snap_date"])
    panel["game_date"] = pd.to_datetime(panel["game_date"])
    y_all = panel["actual"].to_numpy(float)
    REALIZED_P0 = float((y_all <= 0).mean())
    print(f"\nrealized P(FP<=0) on the panel: {(y_all <= 0).sum()}/{len(panel)} "
          f"= {REALIZED_P0*100:.2f}%  (min {y_all.min():.1f})")
    print(f"panel window: snapshots {panel['snap_date'].min().date()} .. "
          f"{panel['snap_date'].max().date()}; starts "
          f"{panel['game_date'].min().date()} .. {panel['game_date'].max().date()}")

    id_to_abbr, strength = build_team_maps()

    # opponent of the SCORED start: the other team in that game_pk (boxscore)
    box = pd.read_parquet(XFPCACHE / "boxscore_pitchers.parquet")
    teams_in_game = (box.groupby("game_pk")["team_id"]
                        .agg(lambda s: sorted(set(int(v) for v in s))))
    own_team = (box[box["gs"] == 1].drop_duplicates(["game_pk", "mlbam_id"])
                   .set_index(["game_pk", "mlbam_id"])["team_id"].to_dict())

    opp_ids, bad = [], 0
    for _, r in panel.iterrows():
        gp, pid = int(r["game_pk"]), int(r["pitcher"])
        mine = own_team.get((gp, pid))
        both = teams_in_game.get(gp)
        if mine is None or both is None or len(both) != 2:
            opp_ids.append(None)
            bad += 1
            continue
        other = [t for t in both if t != int(mine)]
        opp_ids.append(other[0] if len(other) == 1 else None)
        if len(other) != 1:
            bad += 1
    panel["opp_team_id"] = opp_ids
    if bad:
        print(f"  {bad} rows could not resolve an opponent from the boxscore "
              f"store — DROPPED (never given a neutral factor)")
    panel = panel[panel["opp_team_id"].notna()].copy()
    panel["opp_team_id"] = panel["opp_team_id"].astype(int)
    panel["opp_factor"] = [opp_factor_for(t, id_to_abbr, strength)
                           for t in panel["opp_team_id"]]
    print(f"  opp_factor: n={len(panel)} mean {panel['opp_factor'].mean():.4f} "
          f"min {panel['opp_factor'].min():.3f} max {panel['opp_factor'].max():.3f}")

    # ---- empirical pools AS OF the snapshot date ---- #
    print(f"\nbuilding empirical pools (<= {HISTORY_LIMIT} starts, "
          f"{HISTORY_YEARS}, strictly BEFORE each snapshot)...")
    logs = fetch_gamelogs(sorted(panel["pitcher"].unique().tolist()))
    logs["date_dt"] = pd.to_datetime(logs["date"])
    by_p = {int(p): g.sort_values("date_dt", ascending=False)
            for p, g in logs.groupby("pitcher")}

    pools, pool_fs, sizes, band_sizes, fallbacks = [], [], [], [], []
    for _, r in panel.iterrows():
        g = by_p.get(int(r["pitcher"]))
        if g is None:
            pools.append(np.array([])); pool_fs.append(np.array([]))
            sizes.append(0); band_sizes.append(0); fallbacks.append(True)
            continue
        prior = g[g["date_dt"] < r["snap_date"]].head(HISTORY_LIMIT)
        vals = prior["fp"].to_numpy(float)
        fs = np.array([opp_factor_for(t, id_to_abbr, strength)
                       for t in prior["opp_team_id"]], dtype=float)
        pools.append(vals); pool_fs.append(fs); sizes.append(vals.size)
        want = _band_of(float(r["opp_factor"]))
        nb = int(np.sum([_band_of(v) == want for v in fs])) if fs.size else 0
        band_sizes.append(nb)
        fallbacks.append(nb < MIN_BAND)
    panel["pool"] = pools
    panel["pool_f"] = pool_fs
    panel["n_pool"] = sizes
    panel["n_band"] = band_sizes
    panel["band_fallback"] = fallbacks

    dropped = int((panel["n_pool"] < MIN_POOL).sum())
    print(f"  pool size: median {int(np.median(sizes))} mean "
          f"{np.mean(sizes):.1f}; rows with n_pool < {MIN_POOL}: {dropped} "
          f"({dropped/len(panel)*100:.1f}%) -> DROPPED per pre-registration")
    panel = panel[panel["n_pool"] >= MIN_POOL].copy().reset_index(drop=True)
    print(f"  scored panel: n={len(panel)} starts, "
          f"{panel['pitcher'].nunique()} pitchers")
    print(f"  (d) opp-conditioned band pool: median {int(np.median(panel['n_band']))} "
          f"mean {panel['n_band'].mean():.1f}; fallback-to-full rate "
          f"{panel['band_fallback'].mean()*100:.1f}%")
    return panel


def score(panel: pd.DataFrame) -> pd.DataFrame:
    """Attach per-row CRPS / P(FP<=0) / q10 for every treatment."""
    out = {t: {"crps": [], "p0": [], "q10": [], "mean": [], "sd": []}
           for t in TREATMENTS}
    for _, r in panel.iterrows():
        pool = r["pool"]
        f = float(r["opp_factor"])
        m_emp = float(pool.mean())
        mu_rp3 = float(r["xfp_rp3_per_start"])
        y = float(r["actual"])
        for t in TREATMENTS:
            vals, _ = transformed_pool(t, pool, f, m_emp, mu_rp3, r["pool_f"])
            out[t]["crps"].append(crps_sample(vals, y))
            out[t]["p0"].append(float((vals <= 0).mean()))
            out[t]["q10"].append(float(np.percentile(vals, 10)))
            out[t]["mean"].append(float(vals.mean()))
            out[t]["sd"].append(float(vals.std(ddof=0)))
    sc = panel.copy()
    for t in TREATMENTS:
        for k, v in out[t].items():
            sc[f"{k}__{t}"] = v
    return sc


def monotonicity(panel: pd.DataFrame) -> pd.DataFrame:
    """P(FP<=0) across the DECLARED opp_factor grid, at each row's own pool."""
    rows = []
    for t in TREATMENTS:
        p0s = []
        for f in FGRID:
            vals_p0 = []
            for _, r in panel.iterrows():
                pool = r["pool"]
                m_emp = float(pool.mean())
                vals, _ = transformed_pool(t, pool, f, m_emp,
                                           float(r["xfp_rp3_per_start"]),
                                           r["pool_f"])
                vals_p0.append(float((vals <= 0).mean()))
            p0s.append(float(np.mean(vals_p0)))
        arr = np.array(p0s)
        spread_pp = (arr.max() - arr.min()) * 100
        non_incr = bool(np.all(np.diff(arr) <= 1e-12))
        rows.append({
            "treatment": t,
            **{f"P0@f={f:.2f}_%": round(p * 100, 2) for f, p in zip(FGRID, p0s)},
            "spread_pp": round(spread_pp, 2),
            "non_increasing": non_incr,
            "mono_pass": bool(non_incr and spread_pp >= MONO_MIN_SPREAD_PP),
        })
    return pd.DataFrame(rows)


def main():
    pd.set_option("display.width", 240)
    print("=" * 78)
    print("I1 — empirical-bootstrap leg: how opp_factor should enter")
    print("pre-reg: data/research/validation_runs/sp_bootstrap_opp_factor_2026-07-30.md")
    print("=" * 78)

    _verify_crps_sample()
    panel = build_scored_panel()
    sc = score(panel)

    # ---------- correctness check declared in expected_sign ---------- #
    dmean = float(np.max(np.abs(sc["mean__multiply"] - sc["mean__shift_self"])))
    print(f"\n--- construction check: |mean(multiply) - mean(shift_self)| max = "
          f"{dmean:.2e} (must be ~0 — the two differ in SHAPE only) ---")
    if dmean > 1e-9:
        raise AssertionError("multiply and shift_self should share a mean")
    sd_ratio = (sc["sd__multiply"] / sc["sd__unadjusted"]).to_numpy()
    print(f"    SD(multiply)/SD(pool) tracks f exactly: max dev from f = "
          f"{float(np.max(np.abs(sd_ratio - sc['opp_factor'].to_numpy()))):.2e}")

    # ---------- PRIMARY table ---------- #
    y = sc["actual"].to_numpy(float)
    rows = []
    for t in TREATMENTS:
        q10 = sc[f"q10__{t}"].to_numpy(float)
        rows.append({
            "treatment": t + (" (INCUMBENT)" if t == INCUMBENT else ""),
            "n": len(sc),
            "CRPS": round(float(sc[f"crps__{t}"].mean()), 4),
            "CRPS_y>0": round(float(sc.loc[y > 0, f"crps__{t}"].mean()), 4),
            "CRPS_y<=0": round(float(sc.loc[y <= 0, f"crps__{t}"].mean()), 4),
            "pred_P(FP<=0)_%": round(float(sc[f"p0__{t}"].mean()) * 100, 2),
            "p0_abs_err_pp": round(abs(float(sc[f"p0__{t}"].mean())
                                       - REALIZED_P0) * 100, 2),
            "mean_q10": round(float(q10.mean()), 3),
            "below_q10_%": round(float((y < q10).mean()) * 100, 2),
        })
    tab = pd.DataFrame(rows)
    print(f"\n--- PRIMARY: exact CRPS + declared left-tail calibration "
          f"(realized P(FP<=0) = {REALIZED_P0*100:.2f}%) ---")
    print(tab.to_string(index=False))

    # ---------- paired pitcher-clustered bootstrap vs incumbent ---------- #
    print(f"\n--- PAIRED CONTRASTS vs {INCUMBENT} (negative = candidate better) ---")
    print(f"    {N_BOOT} pitcher-clustered resamples, seed {SEED}, BH-FDR q=0.05 "
          f"over 4, economic floor {ECON_FLOOR*100:.0f}% relative")
    ctab = []
    for cand in [t for t in TREATMENTS if t != INCUMBENT]:
        bt = paired_cluster_bootstrap(sc, f"crps__{INCUMBENT}", f"crps__{cand}",
                                      "pitcher")
        rel = bt["diff"] / bt["mean_a"]
        ctab.append({
            "candidate": cand, "n_rows": bt["n_rows"],
            "n_pitchers": bt["n_clusters"],
            "CRPS_incumbent": round(bt["mean_a"], 4),
            "CRPS_cand": round(bt["mean_b"], 4),
            "dCRPS": round(bt["diff"], 4),
            "rel_%": round(rel * 100, 2),
            "ci95": f"[{bt['ci_lo']:+.4f}, {bt['ci_hi']:+.4f}]",
            "boot_p": round(bt["p"], 5),
            "ci_excl_0": not (bt["ci_lo"] <= 0 <= bt["ci_hi"]),
            "econ_pass": bool(abs(rel) >= ECON_FLOOR),
            "_rel": rel, "_ci_lo": bt["ci_lo"], "_ci_hi": bt["ci_hi"],
            "_mean_a": bt["mean_a"],
        })
    ctab = pd.DataFrame(ctab)
    ctab["bh_pass"] = bh_fdr(ctab["boot_p"].to_numpy())
    print(ctab.drop(columns=[c for c in ctab.columns
                             if c.startswith("_")]).to_string(index=False))

    # ---------- SECONDARY: monotonicity on the declared grid ---------- #
    mono = monotonicity(panel)
    print(f"\n--- SECONDARY: P(FP<=0) across the DECLARED opp_factor grid "
          f"(pass = non-increasing AND spread >= {MONO_MIN_SPREAD_PP}pp) ---")
    print(mono.to_string(index=False))

    # ---------- DECLARED SELECTION RULE ---------- #
    print("\n--- DECLARED SELECTION RULE ---")
    thin_reject = (float(np.median(panel["n_band"])) < MIN_BAND
                   or float(panel["band_fallback"].mean()) > 0.40)
    if thin_reject:
        print(f"  (d) opp_conditioned REJECTED ON THINNESS (pre-committed): "
              f"median band pool {float(np.median(panel['n_band'])):.0f} "
              f"(< {MIN_BAND}) or fallback rate "
              f"{panel['band_fallback'].mean()*100:.1f}% (> 40%)")
    step1 = ctab[(ctab["dCRPS"] < 0) & ctab["econ_pass"] & ctab["bh_pass"]]
    if thin_reject:
        step1 = step1[step1["candidate"] != "opp_conditioned"]
    if not step1.empty:
        winner = step1.sort_values("dCRPS").iloc[0]["candidate"]
        print(f"  step 1 fires: {winner} beats the incumbent by "
              f"{step1.sort_values('dCRPS').iloc[0]['rel_%']:.2f}% rel and "
              f"passes BH-FDR")
    else:
        print(f"  step 1 does NOT fire: no candidate clears the "
              f"{ECON_FLOOR*100:.0f}% CRPS floor + BH-FDR -> "
              f"CRPS has not separated the treatments")
        mono_ok = set(mono.loc[mono["mono_pass"], "treatment"])
        # do-no-harm: CI must not place the candidate materially WORSE
        harmless = []
        for _, r in ctab.iterrows():
            if thin_reject and r["candidate"] == "opp_conditioned":
                continue
            worse_bound = r["_ci_hi"] / r["_mean_a"]   # most-adverse end, relative
            if worse_bound < ECON_FLOOR:
                harmless.append(r["candidate"])
        print(f"  do-no-harm survivors (adverse CI end < "
              f"+{ECON_FLOOR*100:.0f}% rel): {harmless}")
        print(f"  monotonicity survivors: {sorted(mono_ok)}")
        elig = [c for c in harmless if c in mono_ok]
        if not elig:
            winner = "NO-CHANGE"
            print("  step 2 empty -> NO-CHANGE / document the attenuation")
        else:
            errs = {c: abs(float(sc[f"p0__{c}"].mean()) - REALIZED_P0)
                    for c in elig}
            winner = min(errs, key=errs.get)
            print("  step 2 tie-break on |P(FP<=0) - "
                  f"{REALIZED_P0*100:.2f}%|: "
                  + ", ".join(f"{c} {v*100:.2f}pp" for c, v in
                              sorted(errs.items(), key=lambda kv: kv[1])))
    print(f"\n  WINNER = {winner}")

    # ---------- POST-HOC diagnostic (NOT pre-registered) ---------- #
    # The incumbent can score a SMALLER |P(FP<=0) - realized| on the pooled
    # average precisely BECAUSE it is unresponsive: an unconditional constant
    # sits near the unconditional rate by construction. The question that
    # actually matters is whether the realized blow-up rate MOVES with
    # opp_factor at all — if it does not, responsiveness is decoration.
    print("\n--- POST-HOC (not pre-registered): conditional left-tail "
          "calibration by opp_factor half ---")
    med_f = float(sc["opp_factor"].median())
    ph = []
    for lab, mask in (("TOUGHER (f <= median)", sc["opp_factor"] <= med_f),
                      ("EASIER  (f >  median)", sc["opp_factor"] > med_f)):
        sub = sc[mask]
        row = {"half": lab, "n": len(sub),
               "mean_f": round(float(sub["opp_factor"].mean()), 4),
               "realized_P0_%": round(float((sub["actual"] <= 0).mean()) * 100, 2)}
        for t in TREATMENTS:
            row[f"pred_{t}_%"] = round(float(sub[f"p0__{t}"].mean()) * 100, 2)
        ph.append(row)
    ph = pd.DataFrame(ph)
    print(f"  median opp_factor = {med_f:.4f}; panel f range "
          f"[{sc['opp_factor'].min():.3f}, {sc['opp_factor'].max():.3f}] — "
          f"much narrower than the clip {FCLIP}")
    print(ph.to_string(index=False))
    d_real = float(ph.loc[0, "realized_P0_%"] - ph.loc[1, "realized_P0_%"])
    print(f"  realized P(FP<=0) is {d_real:+.2f}pp higher against the tougher "
          f"half; predicted deltas: "
          + ", ".join(f"{t} {ph.loc[0, f'pred_{t}_%'] - ph.loc[1, f'pred_{t}_%']:+.2f}pp"
                      for t in TREATMENTS))
    ph.to_csv(OUTDIR / "_i1_bootstrap_opp_factor_conditional.csv", index=False)

    # ---------- behaviour change on the numbers the skill prints ---------- #
    print("\n" + "=" * 78)
    print("BEHAVIOUR CHANGE — the two numbers a bench/start call surfaces")
    print("=" * 78)
    print("\n  panel-wide means:")
    for t in TREATMENTS:
        print(f"    {t:<18} mean p10={sc[f'q10__{t}'].mean():+8.3f} FP   "
              f"mean P(FP<=0)={sc[f'p0__{t}'].mean()*100:6.2f}%   "
              f"CRPS={sc[f'crps__{t}'].mean():.4f}")

    if winner not in ("NO-CHANGE", INCUMBENT):
        print(f"\n  representative rows (largest |f - 1|), {INCUMBENT} -> {winner}:")
        ex = sc.assign(_d=(sc["opp_factor"] - 1).abs()).nlargest(8, "_d")
        show = ex[["player_name", "opp_factor", "n_pool",
                   f"q10__{INCUMBENT}", f"q10__{winner}",
                   f"p0__{INCUMBENT}", f"p0__{winner}"]].copy()
        show[f"p0__{INCUMBENT}"] = (show[f"p0__{INCUMBENT}"] * 100).round(2)
        show[f"p0__{winner}"] = (show[f"p0__{winner}"] * 100).round(2)
        print(show.round(3).to_string(index=False))

    # ---------- blend dilution (the CLI default) ---------- #
    print("\n  'blend' is the sp_bench_mc CLI DEFAULT: the empirical leg carries "
          "w = m/(m+20)")
    for m in (2, 10, 20, 30):
        w = m / (m + 20)
        print(f"    m={m:>2} -> w={w:.2f}: an empirical-leg change moves the "
              f"blended sampler by {w*100:.0f}% of its own size")

    sc_out = sc.drop(columns=["pool", "pool_f"])
    sc_out.to_csv(OUTDIR / "_i1_bootstrap_opp_factor_panel.csv", index=False)
    tab.to_csv(OUTDIR / "_i1_bootstrap_opp_factor_primary.csv", index=False)
    ctab.drop(columns=[c for c in ctab.columns if c.startswith("_")]).to_csv(
        OUTDIR / "_i1_bootstrap_opp_factor_contrasts.csv", index=False)
    mono.to_csv(OUTDIR / "_i1_bootstrap_opp_factor_monotonicity.csv", index=False)
    print(f"\nWrote _i1_bootstrap_opp_factor_{{panel,primary,contrasts,"
          f"monotonicity}}.csv to {OUTDIR}")
    return winner


if __name__ == "__main__":
    main()

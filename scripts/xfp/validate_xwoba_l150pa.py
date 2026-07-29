"""Pre-registered: see data/research/validation_runs/xwoba_L150pa_2026-07-28.md

Rule 9 validation of `xwoba_L150pa` as an rh3 candidate feature.

Baseline = the FULL production RH3_FEATS list (21 features), imported live from
`plv_clone.models.xfp.rh3` so it cannot drift from production. Feature assembly
and the LOO gate reuse the helpers in
`scripts/xfp/research/validate_rh3_breakout_signals.py` (same prior table, same
shrinkage specs, same cross_year_eval) so this run is structurally identical to
the prior rh3 candidate sweeps.

MATCHED SAMPLE: cross_year_eval drops rows with any NaN feature. The candidate is
NaN early in a season (fewer than 150 PA banked), so the baseline is RE-MEASURED
on the candidate's own non-null frame. Comparing an extended model on a shrunken
frame against a baseline on the full frame would be a Rule 9 violation by the
back door.

Usage:  python scripts/xfp/validate_xwoba_l150pa.py [--rebuild]
"""
from __future__ import annotations

import importlib.util as _iu
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

ROLLING_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'rolling_hitters_2018_2026.csv'
MULTIYR_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'hitters_multiyr_2015_2026.csv'
STATCAST = ROOT / 'data' / 'research' / 'xfp_cache' / 'statcast_{yr}.parquet'
FEAT_CACHE = ROOT / '.cache' / 'xwoba_l150pa_feature.csv'

WINDOW_PA = 150
SC_YEARS = [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]  # 2017 = lookback for 2018

# --- import the existing rh3 candidate harness (Rule 9 baseline machinery) ----
_h_path = ROOT / 'scripts' / 'xfp' / 'research' / 'validate_rh3_breakout_signals.py'
_spec = _iu.spec_from_file_location('_rh3_harness', _h_path)
H = _iu.module_from_spec(_spec)
_spec.loader.exec_module(H)

# The harness sets ROOT = Path(__file__).parents[2], which resolves to `scripts/`
# (it lives one level deeper, in scripts/xfp/research/). All three of its optional
# baseline inputs therefore .exists()==False and get filled with 0.0 — a silently
# DEGRADED baseline with three constant features. Override with correct paths so
# the Rule 9 baseline here is the real production one. (Flagged 2026-07-28.)
H.H2_LOCKED = ROOT / 'data' / 'outputs' / 'seasonality_h2_locked.csv'
H.XWOBA_RESID = ROOT / 'data' / 'outputs' / 'hitter_xwoba_residual.csv'
H.ROS_OPP_SP = ROOT / 'data' / 'research' / 'xfp_cache' / 'ros_opp_sp_xwoba_per_hitter.csv'
for _p in (H.H2_LOCKED, H.XWOBA_RESID, H.ROS_OPP_SP):
    if not _p.exists():
        raise SystemExit(f'ABORT — baseline input missing, Rule 9 violation: {_p}')

from plv_clone.models.xfp.rh3 import RH3_FEATS, TARGET  # noqa: E402  live production list


# ---------------------------------------------------------------------------
# Step A — build the candidate feature per (batter, year, split_day)
# ---------------------------------------------------------------------------
def build_feature(cutoffs: pd.DataFrame) -> pd.DataFrame:
    """cutoffs: unique (batter, year, split_day, cutoff_date) rows from the rolling frame.

    Returns those keys plus:
      xwoba_L150pa_within -- last 150 PA, window entirely within the current season
      xwoba_L150pa_cross  -- last 150 PA, window may span into the prior season
      n_pa_season_at_cut  -- season-to-date PA at the cutoff (join sanity check vs pa_to)
    """
    frames = []
    for yr in SC_YEARS:
        p = Path(str(STATCAST).format(yr=yr))
        if not p.exists():
            print(f'  statcast {yr}: MISSING (skipped)')
            continue
        sc = pd.read_parquet(p, columns=['batter', 'game_date', 'game_pk', 'at_bat_number',
                                         'woba_denom', 'woba_value',
                                         'estimated_woba_using_speedangle'])
        sc = sc[sc.woba_denom == 1].copy()
        # Savant xwOBA: estimated wOBA on batted balls, actual wOBA value on K/BB/HBP
        sc['xw'] = sc.estimated_woba_using_speedangle.fillna(sc.woba_value)
        sc = sc.dropna(subset=['xw'])
        sc['game_date'] = pd.to_datetime(sc['game_date'])
        sc['sc_year'] = yr
        frames.append(sc[['batter', 'game_date', 'game_pk', 'at_bat_number', 'xw', 'sc_year']])
        print(f'  statcast {yr}: {len(sc):,} PA')

    pa = pd.concat(frames, ignore_index=True)
    pa = pa.sort_values(['batter', 'game_date', 'game_pk', 'at_bat_number'])

    out = []
    cut_by_batter = {b: g for b, g in cutoffs.groupby('batter')}
    for b, g in pa.groupby('batter', sort=False):
        cuts = cut_by_batter.get(b)
        if cuts is None:
            continue
        dates = g.game_date.to_numpy()
        yrs = g.sc_year.to_numpy()
        cum = np.concatenate([[0.0], np.cumsum(g.xw.to_numpy(float))])
        for r in cuts.itertuples(index=False):
            cd = np.datetime64(r.cutoff_date)
            idx = int(np.searchsorted(dates, cd, side='right'))   # PAs through cutoff, inclusive
            n_season = int((yrs[:idx] == r.year).sum())
            if idx >= WINDOW_PA:
                val = (cum[idx] - cum[idx - WINDOW_PA]) / WINDOW_PA
            else:
                val = np.nan
            out.append({
                'batter': b, 'year': r.year, 'split_day': r.split_day,
                'xwoba_L150pa_cross': val,
                # identical window; differs only in whether it is allowed to
                # reach back past the season boundary
                'xwoba_L150pa_within': val if n_season >= WINDOW_PA else np.nan,
                'n_pa_season_at_cut': n_season,
            })
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# Step B — assemble the production baseline frame (mirrors rh3.main())
# ---------------------------------------------------------------------------
def assemble() -> pd.DataFrame:
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)
    rolling['cutoff_date'] = pd.to_datetime(rolling['cutoff_date'])

    if FEAT_CACHE.exists() and '--rebuild' not in sys.argv:
        feat = pd.read_csv(FEAT_CACHE)
        print(f'candidate feature: loaded cache ({len(feat):,} rows)')
    else:
        print('Building candidate feature from statcast...')
        keys = rolling[['batter', 'year', 'split_day', 'cutoff_date']].drop_duplicates()
        feat = build_feature(keys)
        FEAT_CACHE.parent.mkdir(exist_ok=True)
        feat.to_csv(FEAT_CACHE, index=False)
        print(f'candidate feature: built {len(feat):,} rows -> {FEAT_CACHE}')

    rolling = rolling.merge(feat, on=['batter', 'year', 'split_day'], how='left')

    # ---- baseline feature assembly, identical to the breakout-signal harness ----
    years_needed = sorted(rolling['year'].unique())
    prior = H.build_prior_table(multiyr, years_needed)
    rolling = rolling.merge(prior, on=['batter', 'year'], how='left')
    league_mu = float(multiyr[multiyr['pa'] >= 200]['fp_per_pa_actual'].mean())
    rolling['prior_fp_per_pa'] = rolling['prior_fp_per_pa'].fillna(league_mu)
    rolling['prior_pa_eff'] = rolling['prior_pa_eff'].fillna(0.0)

    if H.H2_LOCKED.exists():
        h2 = pd.read_csv(H.H2_LOCKED)[['batter', 'lift_h2_aug150']]
        rolling = rolling.merge(h2, on='batter', how='left')
    rolling['lift_h2_aug150'] = rolling.get('lift_h2_aug150', pd.Series(0.0, index=rolling.index)).fillna(0.0)

    if H.XWOBA_RESID.exists():
        xw = pd.read_csv(H.XWOBA_RESID)[['batter', 'xwoba_residual_career']]
        rolling = rolling.merge(xw, on='batter', how='left')
    rolling['xwoba_residual_career'] = rolling.get(
        'xwoba_residual_career', pd.Series(0.0, index=rolling.index)).fillna(0.0)

    first_year = multiyr.groupby('batter')['year'].min().to_dict()
    rolling['career_stage'] = rolling.apply(
        lambda r: r['year'] - first_year.get(r['batter'], r['year']), axis=1)

    if H.ROS_OPP_SP.exists():
        opp = pd.read_csv(H.ROS_OPP_SP)[['batter', 'year', 'split_day',
                                         'ros_opp_sp_xwoba_weighted']]
        rolling = rolling.merge(opp, on=['batter', 'year', 'split_day'], how='left')
        ym = rolling.groupby('year')['ros_opp_sp_xwoba_weighted'].transform('mean')
        rolling['ros_opp_sp_xwoba_weighted'] = (rolling['ros_opp_sp_xwoba_weighted']
                                                .fillna(ym)
                                                .fillna(rolling['ros_opp_sp_xwoba_weighted'].mean()))
    else:
        raise SystemExit('ros_opp_sp_xwoba_weighted missing — baseline would be degraded')

    # bx_prior_h — promoted to RH3_FEATS 2026-07-10, after the breakout-signal
    # harness was written, so its hardcoded RH3_FEATS copy predates it. Mirrors
    # rh3.main() lines ~373-395.
    bx_path = ROOT / 'data' / 'research' / 'xfp_cache' / 'bx_priors_2018_2026.csv'
    if not bx_path.exists():
        raise SystemExit(f'ABORT — baseline input missing, Rule 9 violation: {bx_path}')
    bx = pd.read_csv(bx_path)[['mlbam', 'year', 'bx_prior_h']].rename(
        columns={'mlbam': 'batter'})
    rolling = rolling.merge(bx, on=['batter', 'year'], how='left')
    ym = rolling.groupby('year')['bx_prior_h'].transform('mean')
    rolling['bx_prior_h'] = (rolling['bx_prior_h'].fillna(ym)
                             .fillna(rolling['bx_prior_h'].mean()))

    rolling = H.apply_shrinkage(rolling, H.TRAIN_YEARS, H.SHRINK_SPEC_TO)
    rolling = H.apply_shrinkage(rolling, H.TRAIN_YEARS, H.SHRINK_SPEC_LAST21)
    for col in [r + '_sh' for r in H.SHRINK_SPEC_LAST21]:
        if col in rolling.columns:
            mu = rolling.loc[rolling['year'].isin(H.TRAIN_YEARS), col].mean(skipna=True)
            rolling[col] = rolling[col].fillna(mu)
    rolling['pa_last21'] = rolling['pa_last21'].fillna(0).astype(float)
    return rolling


def gate_report(rolling, base_feats, cand, label):
    """Matched-frame baseline vs extended. Returns the delta dict."""
    frame = rolling[rolling[cand].notna()].copy()
    per_b, ov_b = H.cross_year_eval(frame, base_feats)
    per_e, ov_e = H.cross_year_eval(frame, base_feats + [cand])
    d = ov_e['r'] - ov_b['r']

    print(f'\n{"-"*66}\nCANDIDATE: {label}\n{"-"*66}')
    print(f'matched frame: {len(frame):,} rows  (full frame {len(rolling):,})')
    print(f'  baseline r (matched frame) = {ov_b["r"]:.4f}   n={ov_b["n"]}')
    print(f'  extended r                 = {ov_e["r"]:.4f}   n={ov_e["n"]}')
    print(f'  DELTA r                    = {d:+.4f}   gate >= +0.005 -> '
          f'{"PASS" if d >= 0.005 else "FAIL"}')

    per_d = {y: round(per_e.get(y, {}).get('r', np.nan) - per_b.get(y, {}).get('r', np.nan), 4)
             for y in sorted(per_b)}
    valid = {y: v for y, v in per_d.items() if not np.isnan(v)}
    pos = sum(1 for v in valid.values() if v > 0)
    print(f'  per-year delta-r: {per_d}')
    print(f'  positive years: {pos}/{len(valid)}  (bar: >=5 of 7)')
    hold = {y: per_d.get(y) for y in H.HOLDOUT_YEARS if y in per_d}
    print(f'  HOLDOUT {hold}  -> {"PASS" if hold and all(v > 0 for v in hold.values()) else "FAIL"}')

    verdict = ('PASS' if (d >= 0.005 and pos >= 5 and hold and all(v > 0 for v in hold.values()))
               else 'MARGINAL' if d > 0 else 'REJECTED')
    print(f'  VERDICT: {verdict}')
    return {'delta': d, 'per_year': per_d, 'holdout': hold, 'verdict': verdict,
            'n': len(frame), 'base_r': ov_b['r'], 'ext_r': ov_e['r']}


def main():
    print('=' * 66)
    print('RULE 9 VALIDATION — xwoba_L150pa -> rh3')
    print('=' * 66)
    rolling = assemble()

    base = [f for f in RH3_FEATS if f in rolling.columns]
    missing = [f for f in RH3_FEATS if f not in rolling.columns]
    print(f'\nBaseline: {len(base)}/{len(RH3_FEATS)} production features')
    if missing:
        raise SystemExit(f'ABORT — baseline incomplete, Rule 9 violation: {missing}')

    # join sanity: our season-to-date PA count at the cutoff vs the frame's own pa_to
    chk = rolling.dropna(subset=['n_pa_season_at_cut'])
    corr = np.corrcoef(chk['n_pa_season_at_cut'], chk['pa_to'])[0, 1]
    print(f'join sanity: corr(n_pa_season_at_cut, pa_to) = {corr:.4f}  '
          f'(mean abs diff {np.mean(np.abs(chk.n_pa_season_at_cut - chk.pa_to)):.1f} PA)')

    elig = rolling[(rolling.pa_to >= H.EVAL_PA_MIN) & (rolling.ros_pa >= H.ROS_PA_MIN)
                   & (rolling.year != 2020)]
    print('\ncandidate coverage on the eligible frame:')
    for c in ['xwoba_L150pa_within', 'xwoba_L150pa_cross']:
        print(f'  {c:22s} {elig[c].notna().sum():,}/{len(elig):,} '
              f'({100*elig[c].notna().mean():.1f}%)')
    cov = (elig.assign(ok=elig.xwoba_L150pa_within.notna())
           .groupby('split_day').ok.mean().mul(100).round(0).astype(int).to_dict())
    print(f'  _within coverage by split_day (%): {cov}')

    # -- full-frame baseline for reference (NOT the comparison number) --------
    per_ref, ov_ref = H.cross_year_eval(rolling, base)
    print(f'\nreference: full-frame baseline r = {ov_ref["r"]:.4f} n={ov_ref["n"]}')
    print(f'  per-year: { {y: v["r"] for y, v in sorted(per_ref.items())} }')

    results = {}
    for cand, label in [('xwoba_L150pa_within', 'xwoba_L150pa (within-season window)'),
                        ('xwoba_L150pa_cross', 'xwoba_L150pa (window may span seasons)')]:
        results[cand] = gate_report(rolling, base, cand, label)

    # -- Rule 8 convergence curve on the better variant -----------------------
    best = max(results, key=lambda k: results[k]['delta'])
    print(f'\n{"="*66}\nRULE 8 CONVERGENCE CURVE — {best} (TRAIN_ONLY years)\n{"="*66}')
    frame = rolling[rolling[best].notna()].copy()
    cc = H.convergence_curve(frame, base, base + [best])
    for sd, dr in sorted(cc.items()):
        bar = '' if dr is None else ('+' if dr > 0 else '-')
        print(f'  split_day={sd:>3}: delta_r={dr}  {bar}')
    vals = [v for v in cc.values() if v is not None]
    if vals:
        print(f'  cutoffs with positive delta: {sum(1 for v in vals if v > 0)}/{len(vals)}')
        print(f'  median delta across cutoffs: {np.median(vals):+.4f}')

    # -- Rule 4 / diagnosis: is the failure REDUNDANCY or ABSENCE of signal? ---
    print(f'\n{"="*66}\nREDUNDANCY DIAGNOSTIC\n{"="*66}')
    from sklearn.linear_model import RidgeCV
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    for cand in ['xwoba_L150pa_within', 'xwoba_L150pa_cross']:
        f = rolling.dropna(subset=base + [cand, TARGET])
        f = f[(f.pa_to >= H.EVAL_PA_MIN) & (f.ros_pa >= H.ROS_PA_MIN) & (f.year != 2020)]
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 40), cv=5))])
        pipe.fit(f[base].values, f[cand].values)
        r2 = float(np.corrcoef(pipe.predict(f[base].values), f[cand].values)[0, 1] ** 2)
        # unique part of the candidate, vs the target
        resid = f[cand].values - pipe.predict(f[base].values)
        r_uni = float(np.corrcoef(resid, f[TARGET].values)[0, 1])
        # marginal, for contrast
        r_marg = float(np.corrcoef(f[cand].values, f[TARGET].values)[0, 1])
        print(f'  {cand}:')
        print(f'    reconstructible from the 22 baseline feats: R2 = {r2:.3f}')
        print(f'    marginal r vs target                      : {r_marg:+.3f}')
        print(f'    r of its UNIQUE residual vs target        : {r_uni:+.3f}')

    print(f'\n{"="*66}\nSUMMARY\n{"="*66}')
    for c, r in results.items():
        print(f'  {c:22s} delta={r["delta"]:+.4f}  n={r["n"]:,}  {r["verdict"]}')


if __name__ == '__main__':
    main()

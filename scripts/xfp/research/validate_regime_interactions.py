"""validate_regime_interactions.py — 4-cell regime / ball-era interaction sweep.

Pre-registered: data/research/validation_runs/regime_interactions_2026-07-10.md
(Bonferroni family N=4; gates locked BEFORE any results were computed).

Cells:
  R1 (rh3)  sb_x_newrules      = sb_per_pa_to_sh  x I[year >= 2023]   expected +
  R2 (rh3)  barrel_x_ball_env  = barrel_pct_to_sh x env_c             expected +
  R3 (rp3)  hr_risk_x_ball_env = barrel_pct_to_f  x env_c             expected -
            (augmented baseline = RP3_FEATS + barrel_pct_to_f; the
             interaction is the only registered delta)
  R4 (rp3)  swstr_x_sticky     = swstr_pct_to_sh  x I[year >= 2022]   expected + (low conf)

env = league_hr_per_barrel_to, the league-wide P(HR | barrel) to-date at each
(year, split_day) cutoff — the live-ball / drag proxy. Cache:
data/research/xfp_cache/league_hr_env_by_year_split.csv (built here if missing).
env_c = env centered at its TRAIN_YEARS cell mean (one constant).

Run with:
    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/ci/run_summary.py -- \
        python scripts/xfp/validate_regime_interactions.py --stage rh3
Stages: env | rh3 | rp3   (run separately to stay inside foreground timeouts)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plv_clone.paths import ROOT  # noqa: E402

CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
ENV_CSV = CACHE / 'league_hr_env_by_year_split.csv'
ROLLING_FILES = [
    CACHE / 'rolling_hitters_2018_2026.csv',
    CACHE / 'rolling_pitchers_2018_2026.csv',
]
TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]


# ---------------------------------------------------------------------------
# Stage 0: env cache (idempotent)
# ---------------------------------------------------------------------------

def build_env_cache(force: bool = False) -> pd.DataFrame:
    if ENV_CSV.exists() and not force:
        return pd.read_csv(ENV_CSV)

    triples = []
    for f in ROLLING_FILES:
        df = pd.read_csv(f, usecols=['year', 'split_day', 'cutoff_date'])
        triples.append(df.drop_duplicates())
    tri = pd.concat(triples, ignore_index=True).drop_duplicates()
    # If hitter/pitcher files ever disagree on cutoff for a (year, split_day),
    # take the max cutoff (should not happen — both cap at max data date).
    tri = (tri.groupby(['year', 'split_day'], as_index=False)['cutoff_date']
              .max().sort_values(['year', 'split_day']))

    rows = []
    for year, grp in tri.groupby('year'):
        sc_path = CACHE / f'statcast_{int(year)}.parquet'
        if not sc_path.exists():
            print(f'  [env] statcast_{year}.parquet missing — skip')
            continue
        sc = pd.read_parquet(
            sc_path, columns=['game_date', 'launch_speed_angle', 'events'])
        bb = sc[sc['launch_speed_angle'] == 6].copy()  # Savant barrels
        bb['game_date'] = pd.to_datetime(bb['game_date'])
        bb = bb.sort_values('game_date')
        gd = bb['game_date'].to_numpy()
        cum_hr = np.cumsum((bb['events'] == 'home_run').to_numpy().astype(int))
        for _, r in grp.iterrows():
            cutoff = np.datetime64(pd.Timestamp(r['cutoff_date']))
            idx = int(np.searchsorted(gd, cutoff, side='right'))
            n_bar = idx
            n_hr = int(cum_hr[idx - 1]) if idx > 0 else 0
            rows.append({
                'year': int(year), 'split_day': int(r['split_day']),
                'cutoff_date': r['cutoff_date'],
                'barrels_to': n_bar, 'hr_on_barrels_to': n_hr,
                'league_hr_per_barrel_to': (n_hr / n_bar) if n_bar else np.nan,
            })
        print(f'  [env] {year}: {len(grp)} cutoffs, season barrels={len(bb)}')
    env = pd.DataFrame(rows)
    env.to_csv(ENV_CSV, index=False)
    print(f'  [env] wrote {ENV_CSV} ({len(env)} rows)')
    return env


def env_fingerprint(env: pd.DataFrame) -> None:
    print('\n=== League HR-per-barrel fingerprint (full-season = max split_day) ===')
    last = env.sort_values('split_day').groupby('year').tail(1)
    for _, r in last.sort_values('year').iterrows():
        print(f"  {int(r['year'])}: HR/barrel = {r['league_hr_per_barrel_to']:.4f}  "
              f"(HR {int(r['hr_on_barrels_to'])} / barrels {int(r['barrels_to'])})")
    train_mu = env.loc[env['year'].isin(TRAIN_YEARS), 'league_hr_per_barrel_to'].mean()
    print(f"  centering constant (TRAIN_YEARS cell mean): {train_mu:.4f}")


def env_center_constant(env: pd.DataFrame) -> float:
    return float(env.loc[env['year'].isin(TRAIN_YEARS),
                         'league_hr_per_barrel_to'].mean())


def merge_env(rolling: pd.DataFrame, env: pd.DataFrame) -> pd.DataFrame:
    e = env[['year', 'split_day', 'league_hr_per_barrel_to']]
    out = rolling.merge(e, on=['year', 'split_day'], how='left')
    n_miss = out['league_hr_per_barrel_to'].isna().sum()
    print(f'  env join: {n_miss} / {len(out)} rows missing env (filled year-mean then global)')
    ym = out.groupby('year')['league_hr_per_barrel_to'].transform('mean')
    out['league_hr_per_barrel_to'] = out['league_hr_per_barrel_to'].fillna(ym)
    out['league_hr_per_barrel_to'] = out['league_hr_per_barrel_to'].fillna(
        out['league_hr_per_barrel_to'].mean())
    return out


# ---------------------------------------------------------------------------
# Shared reporting
# ---------------------------------------------------------------------------

def report_cell(name: str, r9: dict, r_base: float, r_full: float,
                n: int, coef: float, expected_sign: str,
                era_years: list[int] | None = None,
                pre_era_years: list[int] | None = None) -> None:
    print(f'\n===== CELL {name} =====')
    print(f'  baseline r = {r_base:.4f}   +cand r = {r_full:.4f}   n = {n}')
    print(f'  pooled lift = {r9["lift"]:+.4f}   (gate >= +0.005)')
    print('  per-year lift:')
    for y, d in r9['per_year_lift'].items():
        tag = ''
        if era_years and y in era_years:
            tag = '  [post-era]'
        print(f'    {y}: {d:+.4f}{tag}')
    print(f'  sign consistency: {r9["sign_match_years"]}/{r9["n_total_years"]}')
    print(f'  holdout (2024-25) mean lift: {r9["holdout_lift"]:+.4f}')
    sign_ok = ((expected_sign == '+' and coef > 0)
               or (expected_sign == '-' and coef < 0))
    print(f'  coef = {coef:+.5f}  expected {expected_sign}  '
          f'{"OK" if sign_ok else "WRONG SIGN"}')
    if era_years:
        post = [r9['per_year_lift'][y] for y in era_years
                if y in r9['per_year_lift']]
        pre = [r9['per_year_lift'][y] for y in (pre_era_years or [])
               if y in r9['per_year_lift']]
        n_pos_post = sum(1 for d in post if d > 0)
        both_hold = all(r9['per_year_lift'].get(y, -1) > 0 for y in (2024, 2025))
        pre_mean = float(np.mean(pre)) if pre else np.nan
        print(f'  [adapted era gate] post-era positive: {n_pos_post}/{len(post)}; '
              f'both holdouts positive: {both_hold}; '
              f'pre-era mean lift: {pre_mean:+.4f} (floor -0.002)')


# ---------------------------------------------------------------------------
# Stage A: rh3 (R1, R2)
# ---------------------------------------------------------------------------

def run_rh3(env: pd.DataFrame) -> None:
    from plv_clone.models.xfp import rh3
    from _validate_rh3_v3_helper import load_and_prep_rh3_inputs, _cye
    from lib.rule9 import rule9_lift

    print('\n################ rh3 cells (R1, R2) ################')
    rolling = load_and_prep_rh3_inputs()
    rolling = merge_env(rolling, env)
    mu = env_center_constant(env)
    rolling['env_c'] = rolling['league_hr_per_barrel_to'] - mu

    rolling['sb_x_newrules'] = (
        rolling['sb_per_pa_to_sh'] * (rolling['year'] >= 2023).astype(float))
    rolling['barrel_x_ball_env'] = rolling['barrel_pct_to_sh'] * rolling['env_c']

    feats_base = list(rh3.RH3_FEATS)
    print(f'\n[rh3] baseline eval ({len(feats_base)} feats)...')
    py_b, ov_b = _cye(rolling, feats_base)
    print(f'[rh3] baseline r = {ov_b["r"]:.4f}  n = {ov_b["n"]}')

    for cell, cand, exp, era, pre_era in [
        ('R1 sb_x_newrules', 'sb_x_newrules', '+',
         [2023, 2024, 2025], [2018, 2019, 2021, 2022]),
        ('R2 barrel_x_ball_env', 'barrel_x_ball_env', '+', None, None),
    ]:
        print(f'\n[rh3] extended eval: {cand} ...')
        py_f, ov_f = _cye(rolling, feats_base + [cand])
        r9 = rule9_lift(py_b, py_f, r_base=ov_b['r'], r_full=ov_f['r'])
        pipe, _ = rh3.train_final(rolling, feats_base + [cand])
        coef = dict(zip(feats_base + [cand], pipe.named_steps['r'].coef_))[cand]
        report_cell(cell, r9, ov_b['r'], ov_f['r'], ov_f['n'], coef, exp,
                    era_years=era, pre_era_years=pre_era)


# ---------------------------------------------------------------------------
# Stage B: rp3 (R3, R4)
# ---------------------------------------------------------------------------

def run_rp3(env: pd.DataFrame) -> None:
    from plv_clone.models.xfp import rp3
    from _rp3_validation_harness import prep_rolling, _cye, RP3_FEATS
    from lib.rule9 import rule9_lift

    print('\n################ rp3 cells (R3, R4) ################')
    rolling = prep_rolling()
    rolling = merge_env(rolling, env)
    mu = env_center_constant(env)
    rolling['env_c'] = rolling['league_hr_per_barrel_to'] - mu

    # R3 main effect: raw barrel_pct_to (no _sh in rp3 substrate — prereg'd),
    # NaN -> TRAIN_YEARS mean fill.
    bar_mu = rolling.loc[rolling['year'].isin(TRAIN_YEARS), 'barrel_pct_to'].mean()
    rolling['barrel_pct_to_f'] = rolling['barrel_pct_to'].fillna(bar_mu)
    n_nan = rolling['barrel_pct_to'].isna().sum()
    print(f'  barrel_pct_to NaN: {n_nan}/{len(rolling)} (filled {bar_mu:.4f})')
    rolling['hr_risk_x_ball_env'] = rolling['barrel_pct_to_f'] * rolling['env_c']
    rolling['swstr_x_sticky'] = (
        rolling['swstr_pct_to_sh'] * (rolling['year'] >= 2022).astype(float))

    feats_base = list(RP3_FEATS)
    print(f'\n[rp3] baseline eval ({len(feats_base)} feats)...')
    py_b, ov_b = _cye(rolling, feats_base)
    print(f'[rp3] baseline r = {ov_b["r"]:.4f}  n = {ov_b["n"]}')

    # --- R4 (vs pure production baseline) ---
    print('\n[rp3] extended eval: swstr_x_sticky ...')
    py_f, ov_f = _cye(rolling, feats_base + ['swstr_x_sticky'])
    r9 = rule9_lift(py_b, py_f, r_base=ov_b['r'], r_full=ov_f['r'])
    pipe, _ = rp3.train_final(rolling, feats_base + ['swstr_x_sticky'])
    coef = dict(zip(feats_base + ['swstr_x_sticky'],
                    pipe.named_steps['r'].coef_))['swstr_x_sticky']
    report_cell('R4 swstr_x_sticky', r9, ov_b['r'], ov_f['r'], ov_f['n'],
                coef, '+', era_years=[2022, 2023, 2024, 2025],
                pre_era_years=[2018, 2019, 2021])

    # --- R3 (augmented baseline per prereg) ---
    aug = feats_base + ['barrel_pct_to_f']
    print('\n[rp3] augmented baseline eval (+ barrel_pct_to_f) ...')
    py_a, ov_a = _cye(rolling, aug)
    main_lift = ov_a['r'] - ov_b['r']
    print(f'  [informational only] main-effect lift vs RP3_FEATS: {main_lift:+.4f} '
          f'(r {ov_b["r"]:.4f} -> {ov_a["r"]:.4f})')

    print('\n[rp3] extended eval: hr_risk_x_ball_env ...')
    py_f3, ov_f3 = _cye(rolling, aug + ['hr_risk_x_ball_env'])
    r9_3 = rule9_lift(py_a, py_f3, r_base=ov_a['r'], r_full=ov_f3['r'])
    pipe3, _ = rp3.train_final(rolling, aug + ['hr_risk_x_ball_env'])
    coef3 = dict(zip(aug + ['hr_risk_x_ball_env'],
                     pipe3.named_steps['r'].coef_))['hr_risk_x_ball_env']
    report_cell('R3 hr_risk_x_ball_env (vs augmented baseline)', r9_3,
                ov_a['r'], ov_f3['r'], ov_f3['n'], coef3, '-')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage', choices=['env', 'rh3', 'rp3', 'all'],
                    default='all')
    ap.add_argument('--force-env', action='store_true')
    args = ap.parse_args()

    env = build_env_cache(force=args.force_env)
    env_fingerprint(env)
    if args.stage in ('rh3', 'all'):
        run_rh3(env)
    if args.stage in ('rp3', 'all'):
        run_rp3(env)


if __name__ == '__main__':
    main()

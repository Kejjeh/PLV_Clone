"""
xfp_h6_pipeline.py — H6 adds Savant expected-stats features to H2 pool.

FG was blocked in this session (Cloudflare 403); Savant's expected_statistics
endpoint is open and provides the same underlying data — xBA, xSLG, xwOBA
are computed by Statcast and surface on Savant directly.

For each year 2015–2026 we pull:
  ba, est_ba, slg, est_slg, woba, est_woba, est_*_minus_*_diff
and merge by (batter, year) onto the substrate.

These are "season-level" stats already computed by Statcast (vs the substrate's
per-pitch aggregations). They function as Tier-S talent labels.

Decision gate: ships if cross_year_r ≥ H2 + 0.01 AND |power_bias_hi| ≤ 1.0.
"""
from __future__ import annotations
import sys
import time
from io import StringIO
from pathlib import Path
import warnings
import numpy as np
import pandas as pd
import requests

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
SUBSTRATE = ROOT / 'data' / 'research' / 'xfp_cache' / 'hitters_multiyr_2015_2026.csv'
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'

sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))
from xfp_h_eval import cross_year_evaluate, score_fn, fmt_result, EVAL_MIN_PA
from xfp_h4_pipeline import add_team_run_env

H2_FEATS = [
    'iso', 'k_pct', 'hr_per_pa', 'hard_hit_pct', 'contact_pct', 'whiff_pct',
    'swstr_pct', 'bb_pct', 'z_contact_pct', 'chase_pct', 'in_play_pct',
    'sprint_speed', 'sb_per_pa',
]


def fetch_savant_expected(year: int) -> pd.DataFrame:
    cache = CACHE / f'savant_expected_batter_{year}.csv'
    if cache.exists():
        df = pd.read_csv(cache)
        print(f'  [{year}] cached: {len(df)} rows', flush=True)
        return df
    url = (
        'https://baseballsavant.mlb.com/leaderboard/expected_statistics'
        f'?type=batter&year={year}&min=50&csv=true'
    )
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
    except Exception as exc:
        print(f'  [{year}] fetch failed: {exc}', flush=True)
        return pd.DataFrame()
    df.to_csv(cache, index=False)
    print(f'  [{year}] fetched: {len(df)} rows', flush=True)
    return df


def build_substrate_with_savant() -> pd.DataFrame:
    df = pd.read_csv(SUBSTRATE)
    sav_rows = []
    for yr in sorted(df['year'].unique()):
        s = fetch_savant_expected(int(yr))
        if s.empty:
            continue
        # Standardize cols and merge keys
        s = s.rename(columns={'player_id': 'batter', 'year': 'sav_year'})
        s['batter'] = pd.to_numeric(s['batter'], errors='coerce').astype('Int64')
        s = s.dropna(subset=['batter']).copy()
        s['batter'] = s['batter'].astype(int)
        s['year'] = s['sav_year']
        # Pick the columns we want
        keep = ['batter', 'year', 'ba', 'est_ba', 'slg', 'est_slg', 'woba', 'est_woba',
                'est_ba_minus_ba_diff', 'est_slg_minus_slg_diff', 'est_woba_minus_woba_diff']
        sav_rows.append(s[[c for c in keep if c in s.columns]])
        time.sleep(0.15)
    if not sav_rows:
        return df
    sav = pd.concat(sav_rows, ignore_index=True)
    # Rename to avoid clashing with substrate col names
    sav = sav.rename(columns={
        'ba':                       'sav_ba',
        'est_ba':                   'sav_xba',
        'slg':                      'sav_slg',
        'est_slg':                  'sav_xslg',
        'woba':                     'sav_woba',
        'est_woba':                 'sav_xwoba',
        'est_ba_minus_ba_diff':     'sav_xba_diff',
        'est_slg_minus_slg_diff':   'sav_xslg_diff',
        'est_woba_minus_woba_diff': 'sav_xwoba_diff',
    })
    df = df.merge(sav, on=['batter', 'year'], how='left')
    return df


def main():
    df = build_substrate_with_savant()
    df = add_team_run_env(df)
    print(f'\n=== H6 — substrate {len(df)} rows (with Savant + team_env) ===')

    sav_cols = ['sav_xwoba', 'sav_xslg', 'sav_xba', 'sav_woba', 'sav_slg', 'sav_ba',
                'sav_xwoba_diff', 'sav_xslg_diff', 'sav_xba_diff']
    sub = df[df['pa'] >= EVAL_MIN_PA]
    print('Savant feature coverage on ≥300 PA cohort:')
    for c in sav_cols:
        if c in df.columns:
            n = sub[c].notna().sum()
            print(f'  {c:20s}  {n}/{len(sub)}  ({n/max(len(sub),1):.0%})')
    print()

    # H2 reference
    h2 = cross_year_evaluate(df.dropna(subset=H2_FEATS + ['fp_per_pa_actual']),
                              H2_FEATS, label='H2 (production)')
    print(f'H2 reference:\n  {fmt_result(h2)}\n')

    # Correlation screen on Savant features
    print('--- Cross-year correlation screen on Savant features ---')
    from xfp_h_corr_screen import screen_one
    screen_rows = []
    for c in sav_cols:
        if c in df.columns:
            r = screen_one(df, c)
            print(f'  {c:20s}  mean_cor={r["mean_cor"]}  '
                  f'min={r["min_cor"]} max={r["max_cor"]}  rec={r["recommendation"]}')
            screen_rows.append(r)
    print()
    sav_keep = [r['feature'] for r in screen_rows
                if r['recommendation'] in ('KEEP', 'WATCH') and not pd.isna(r['mean_cor'])]
    print(f'Savant KEEP+WATCH: {sav_keep}')
    print()

    # H6 = H2 + Savant survivors
    H6_POOL = H2_FEATS + sav_keep
    print(f'--- H6 BE on {len(H6_POOL)}-feature pool ---')
    df_pool = df.dropna(subset=H6_POOL + ['fp_per_pa_actual']).copy()
    print(f'After dropna: {len(df_pool)} rows ({(df_pool["pa"]>=300).sum()} ≥300 PA)\n')

    res = cross_year_evaluate(df_pool, H6_POOL, label=f'H6 pool[{len(H6_POOL)}]')
    s_full = score_fn(res['r'], res['power_bias_hi'])
    print('  ' + fmt_result(res))
    print(f'  vs H2: r {res["r"] - h2["r"]:+.4f}, score {s_full - score_fn(h2["r"], h2["power_bias_hi"]):+.4f}\n')

    # Backward elimination
    cur = list(H6_POOL)
    history = [(list(cur), res, s_full)]
    best_score, best_feats, best_res = s_full, list(cur), res
    step = 0
    while len(cur) > 5:
        step += 1
        candidates = []
        for f in cur:
            trial = [x for x in cur if x != f]
            r = cross_year_evaluate(df_pool, trial, label=f'-{f}')
            sc = score_fn(r['r'], r['power_bias_hi'])
            candidates.append((f, r, sc))
        candidates.sort(key=lambda x: -x[2])
        f_drop, r_top, sc_top = candidates[0]
        if step <= 6 or sc_top > best_score - 0.02:
            print(f'Step {step}: drop {f_drop:<22s}  r={r_top["r"]:.4f}  score={sc_top:.4f}  (was {best_score:.4f})')
        cur = [x for x in cur if x != f_drop]
        history.append((list(cur), r_top, sc_top))
        if sc_top > best_score + 0.0001:
            best_score = sc_top
            best_feats = list(cur)
            best_res = r_top
            print(f'  ↑ NEW BEST score={best_score:.4f}, feats={len(best_feats)}')
        elif sc_top < best_score - 0.05:
            print('  ↓ score dropped > 0.05; stopping BE')
            break

    # Also try: H6 + team_run_env_lag1 (full combo)
    print('\n--- H6 + team_run_env_lag1 (full combo) ---')
    H6_FULL = best_feats + ['team_run_env_lag1']
    df_full = df.dropna(subset=H6_FULL + ['fp_per_pa_actual']).copy()
    res_full = cross_year_evaluate(df_full, H6_FULL, label=f'H6 winner + team_env')
    s_full_combo = score_fn(res_full['r'], res_full['power_bias_hi'])
    print('  ' + fmt_result(res_full))
    print(f'  vs H2: r {res_full["r"] - h2["r"]:+.4f}, score {s_full_combo - score_fn(h2["r"], h2["power_bias_hi"]):+.4f}')

    print('\n=== H6 winner ===')
    print('  ' + fmt_result(best_res))
    print(f'  Features ({len(best_feats)}): {best_feats}')

    print('\n=== Decision gate (H6 alone) ===')
    target_r = h2['r'] + 0.01
    print(f'  cross_year_r {best_res["r"]:.4f} ≥ H2 + 0.01 = {target_r:.4f}? {"PASS" if best_res["r"] >= target_r else "FAIL"}')
    print(f'  |power_bias_hi| {abs(best_res["power_bias_hi"]):.4f} ≤ 1.0? {"PASS" if abs(best_res["power_bias_hi"]) <= 1.0 else "FAIL"}')
    print(f'  Score {best_score:.4f} > H2 {score_fn(h2["r"], h2["power_bias_hi"]):.4f}? {"PASS" if best_score > score_fn(h2["r"], h2["power_bias_hi"]) else "FAIL"}')

    print('\n=== Decision gate (H6 + team_env combo) ===')
    print(f'  cross_year_r {res_full["r"]:.4f} ≥ H2 + 0.01 = {target_r:.4f}? {"PASS" if res_full["r"] >= target_r else "FAIL"}')
    print(f'  Score {s_full_combo:.4f} > H2 {score_fn(h2["r"], h2["power_bias_hi"]):.4f}? {"PASS" if s_full_combo > score_fn(h2["r"], h2["power_bias_hi"]) else "FAIL"}')

    out = []
    for feats, r, sc in history:
        out.append({'n_feats': len(feats), 'features': '|'.join(feats),
                    'r': r['r'], 'power_bias_hi': r['power_bias_hi'],
                    'team_context_bias': r['team_context_bias'],
                    'rmse': r['rmse'], 'mae': r['mae'], 'n': r['n'], 'score_T1': sc})
    pd.DataFrame(out).to_csv(ROOT / 'data' / 'research' / 'xfp_h6_be_log.csv', index=False)
    print('\nWrote BE log → data/research/xfp_h6_be_log.csv')
    print(f'\nH6_FEATS = {best_feats}')
    print(f'H6_FEATS_WITH_TEAM_ENV = {H6_FULL}')


if __name__ == '__main__':
    main()

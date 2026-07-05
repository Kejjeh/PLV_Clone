"""per_start_predictor_battle.py — compare every per-start predictor head-to-head.

For each qualifying SP start (2024-2025), build predictors and regress against
actual outcomes:

  Targets:
    actual_K, actual_BB, actual_H, actual_FP (K + IP*3.3 - H - 2*ER - BB - HBP)

  Predictors (independent variables tested individually + combined):
    P1 baseline_K       = pitcher overall career swstr% × swings_in_start
    P2 arsenal_xK       = sum(pitch_mix × batter_whiff%_by_type) / 3
    P3 pitcher_pitch_xK = pitcher's own per-pitch-type swstr% × pitch usage
                          (the pitcher-side "stuff per pitch" angle)
    P4 lineup_xfp       = mean of opposing batters' PRIOR-career fp_per_pa
    P5 pitcher_xfp      = pitcher's own PRIOR-career fp_per_start

  Combined: linear blend, all 5

Output: data/research/per_start_predictor_battle.csv (per-start rows)
        + console r-table comparing predictors

This answers the user's questions:
  - Pitch arsenal × batter (P2) vs pitcher's own per-pitch process (P3)
  - Lineup quality alone (P4) — "can we predict pitcher's past fp from lineup?"
  - SoS via xFP composites (P4 incorporates xFP-based lineup quality)
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path('c:/Users/Joshua/plv_clone')
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'
RES = ROOT / 'data' / 'research'

PITCH_GROUPS = {
    'FF': 'FB', 'FT': 'FB', 'FA': 'FB',
    'FC': 'CT', 'SI': 'SI',
    'SL': 'SL', 'ST': 'SL', 'SV': 'SL',
    'CU': 'CB', 'KC': 'CB', 'CS': 'CB', 'EP': 'CB',
    'CH': 'CH', 'FS': 'SP', 'FO': 'SP',
}
SWINGS = {'foul', 'foul_tip', 'hit_into_play', 'swinging_strike',
          'swinging_strike_blocked', 'missed_bunt'}
WHIFFS = {'swinging_strike', 'swinging_strike_blocked'}
PA_EVENTS = {
    'single', 'double', 'triple', 'home_run', 'walk', 'intent_walk', 'hit_by_pitch',
    'strikeout', 'strikeout_double_play', 'field_out', 'force_out',
    'grounded_into_double_play', 'sac_fly', 'sac_bunt', 'fielders_choice',
    'fielders_choice_out', 'double_play', 'triple_play', 'field_error', 'catcher_interf',
}


def main():
    RES.mkdir(parents=True, exist_ok=True)

    print('[1] Loading career profiles...')
    # Batter weakness (item 2 substrate)
    bw = pd.read_csv(OUT / 'batter_pitch_weakness.csv')
    b_whiff = {}
    for _, r in bw.iterrows():
        if pd.isna(r.get('whiff_per_swing')):
            continue
        b_whiff.setdefault(int(r['batter']), {})[r['ptg']] = float(r['whiff_per_swing']) / 100.0
    global_b_whiff = float(np.nanmean([v for d in b_whiff.values() for v in d.values()])) if b_whiff else 0.25
    print(f'   batter pitch weakness: {len(b_whiff)} batters, global={global_b_whiff:.3f}')

    # Batter prior-career fp_per_pa
    bp = pd.read_csv(CACHE / 'batter_prior_career.csv') if (CACHE / 'batter_prior_career.csv').exists() else None
    if bp is None:
        from scripts.xfp.strength_of_schedule import build_batter_career_priors
        bp = build_batter_career_priors()
    bp = bp.dropna(subset=['prior_career_fp_per_pa'])
    bp_lookup = {(int(r.batter), int(r.year)): float(r.prior_career_fp_per_pa) for r in bp.itertuples()}

    # Pitcher prior-career fp/start
    pp = pd.read_csv(CACHE / 'pitcher_prior_career.csv') if (CACHE / 'pitcher_prior_career.csv').exists() else None
    pp = pp.dropna(subset=['prior_career_fp_per_start'])
    pp_lookup = {(int(r.pitcher), int(r.year)): float(r.prior_career_fp_per_start) for r in pp.itertuples()}

    print('[2] Building per-pitcher per-pitch swstr% (2015-2025, exc. 2020)...')
    p_stuff = {}  # {(pitcher, pitch_group): swstr_per_pitch}
    for year in [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]:
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=['pitcher', 'pitch_type', 'description'])
        df = df[df['pitch_type'].notna()].copy()
        df['ptg'] = df['pitch_type'].map(PITCH_GROUPS).fillna('OTHER')
        df['whiff'] = df['description'].isin(WHIFFS).astype(int)
        df['swing'] = df['description'].isin(SWINGS).astype(int)
        agg = df.groupby(['pitcher', 'ptg'], as_index=False).agg(
            pitches=('description', 'count'), swings=('swing', 'sum'), whiffs=('whiff', 'sum'))
        for _, r in agg.iterrows():
            if r['swings'] >= 30:
                p_stuff.setdefault(int(r['pitcher']), {})[r['ptg']] = float(r['whiffs']) / float(r['swings'])
    global_p_stuff = float(np.nanmean([v for d in p_stuff.values() for v in d.values()])) if p_stuff else 0.10
    print(f'   pitcher per-pitch stuff: {len(p_stuff)} pitchers')

    print('[3] Aggregating per-start predictors and outcomes (2015-2025, exc. 2020)...')
    rows = []
    for year in [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]:
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=[
            'game_pk', 'pitcher', 'batter', 'pitch_type', 'description', 'inning', 'events',
            'outs_when_up', 'post_bat_score', 'bat_score'])

        # SP-only: pitcher in inning 1
        sp_games = df[df['inning'] == 1].groupby(['game_pk', 'pitcher']).size().reset_index().rename(columns={0: '_n'})
        sp_games = sp_games[['game_pk', 'pitcher']].drop_duplicates()
        df = df.merge(sp_games, on=['game_pk', 'pitcher'], how='inner')

        df = df[df['pitch_type'].notna()].copy()
        df['ptg'] = df['pitch_type'].map(PITCH_GROUPS).fillna('OTHER')
        df['swing'] = df['description'].isin(SWINGS).astype(int)
        df['whiff'] = df['description'].isin(WHIFFS).astype(int)

        # Per-pitcher overall swstr% within this year
        ov = df.groupby('pitcher', as_index=False).agg(
            tot_swing=('swing', 'sum'), tot_whiff=('whiff', 'sum'))
        ov['p_overall_swstr'] = ov['tot_whiff'] / ov['tot_swing'].replace(0, np.nan)
        p_overall = dict(zip(ov['pitcher'], ov['p_overall_swstr']))

        # Per-pitch lookups for this year
        df['b_whiff_rate'] = df.apply(
            lambda r: b_whiff.get(int(r['batter']), {}).get(r['ptg'], np.nan), axis=1)
        df['b_whiff_rate'] = df['b_whiff_rate'].fillna(global_b_whiff)
        df['p_stuff_rate'] = df.apply(
            lambda r: p_stuff.get(int(r['pitcher']), {}).get(r['ptg'], np.nan), axis=1)
        df['p_stuff_rate'] = df['p_stuff_rate'].fillna(global_p_stuff)

        # Per-PA outcome flags
        df['pa_terminal'] = df['events'].isin(PA_EVENTS).astype(int)
        df['is_K'] = df['events'].isin({'strikeout', 'strikeout_double_play'}).astype(int)
        df['is_BB'] = df['events'].isin({'walk', 'intent_walk'}).astype(int)
        df['is_HBP'] = (df['events'] == 'hit_by_pitch').astype(int)
        df['is_H'] = df['events'].isin({'single', 'double', 'triple', 'home_run'}).astype(int)
        df['runs_on_pa'] = (df['post_bat_score'] - df['bat_score']).fillna(0)

        # Per-start aggregation
        per_start = df.groupby(['game_pk', 'pitcher'], as_index=False).agg(
            pitches=('description', 'count'),
            swings=('swing', 'sum'),
            whiffs=('whiff', 'sum'),
            actual_K=('is_K', 'sum'),
            actual_BB=('is_BB', 'sum'),
            actual_HBP=('is_HBP', 'sum'),
            actual_H=('is_H', 'sum'),
            actual_PA=('pa_terminal', 'sum'),
            runs_allowed=('runs_on_pa', 'sum'),
            arsenal_xWhiff=('b_whiff_rate', lambda x: (x * df.loc[x.index, 'swing']).sum()),
            stuff_xWhiff=('p_stuff_rate', lambda x: (x * df.loc[x.index, 'swing']).sum()),
        )

        # Estimate IP from outs (PA - hits/walks/HBP/etc are outs roughly)
        # Cleaner: outs_recorded = PA - H - BB - HBP - errors. Use: outs ≈ PA - on-base events
        per_start['outs_est'] = (per_start['actual_PA'] - per_start['actual_H']
                                 - per_start['actual_BB'] - per_start['actual_HBP'])
        per_start['outs_est'] = per_start['outs_est'].clip(lower=0)
        per_start['ip'] = per_start['outs_est'] / 3.0

        # Approximate FP using ER ≈ runs_allowed (close enough for fantasy)
        # item 13: vectorized — owner is scoring.pitcher_fp scalar; kept inline for perf
        per_start['actual_FP'] = (per_start['actual_K'] + per_start['ip'] * 3.3
                                  - per_start['actual_H'] - 2 * per_start['runs_allowed']
                                  - per_start['actual_BB'] - per_start['actual_HBP'])

        # Predictors
        per_start['p_overall_swstr'] = per_start['pitcher'].map(p_overall).fillna(global_p_stuff)
        per_start['baseline_xK'] = per_start['p_overall_swstr'] * per_start['swings'] / 3.0
        per_start['arsenal_xK'] = per_start['arsenal_xWhiff'] / 3.0
        per_start['stuff_xK'] = per_start['stuff_xWhiff'] / 3.0

        # Lineup quality (mean of opposing batters' prior-career fp/PA)
        per_start['lineup_xfp_proxy'] = np.nan
        per_start['pitcher_xfp_proxy'] = np.nan
        df['_pkey'] = df['game_pk'].astype(str) + '_' + df['pitcher'].astype(str)
        df_pa = df[df['pa_terminal'] == 1][['game_pk', 'pitcher', 'batter']].drop_duplicates(['game_pk', 'pitcher', 'batter'])
        df_pa['lineup_xfp_pa'] = df_pa['batter'].apply(lambda b: bp_lookup.get((int(b), year), np.nan))
        lineup_avg = df_pa.dropna(subset=['lineup_xfp_pa']).groupby(
            ['game_pk', 'pitcher'], as_index=False).agg(
            lineup_xfp=('lineup_xfp_pa', 'mean'), lineup_n=('lineup_xfp_pa', 'count'))
        per_start = per_start.merge(lineup_avg, on=['game_pk', 'pitcher'], how='left')

        # Pitcher's own prior-career fp/start (from career priors lookup)
        per_start['pitcher_xfp'] = per_start['pitcher'].apply(
            lambda p: pp_lookup.get((int(p), year), np.nan))

        # Filter qualifying starts
        per_start = per_start[(per_start['actual_PA'] >= 10) & (per_start['swings'] >= 25)
                              & per_start['lineup_xfp'].notna()]
        per_start['year'] = year
        rows.append(per_start)

    if not rows:
        print('  no data'); return
    full = pd.concat(rows, ignore_index=True)
    print(f'   total qualifying starts: {len(full)}')

    print('\n[4] Per-predictor correlation table:')
    print(f'{"predictor":<32s} | {"target":<12s} | {"r":>7s} | {"R^2":>6s} | {"MAE":>5s} | n')
    print('-' * 80)
    targets = {'actual_K': 'K', 'actual_BB': 'BB', 'actual_H': 'H', 'actual_FP': 'FP'}
    predictors = {
        'baseline_xK   (pitcher swstr% × swings)': 'baseline_xK',
        'arsenal_xK    (pitch_mix × batter whiff)': 'arsenal_xK',
        'stuff_xK      (pitcher per-pitch swstr%)': 'stuff_xK',
        'lineup_xfp    (mean opposing batter fp/PA)': 'lineup_xfp',
        'pitcher_xfp   (pitcher prior-career fp/G)': 'pitcher_xfp',
    }
    for plabel, pcol in predictors.items():
        for tcol, tlabel in targets.items():
            sub = full.dropna(subset=[pcol, tcol])
            if len(sub) < 30:
                continue
            r = float(np.corrcoef(sub[pcol], sub[tcol])[0, 1])
            r2 = r * r
            mae = float(np.mean(np.abs(sub[pcol] - sub[tcol]))) if 'xK' in pcol else None
            mae_s = f'{mae:5.2f}' if mae else '  -  '
            print(f'{plabel:<32s} | {tlabel:<12s} | {r:>+7.4f} | {r2:>6.3f} | {mae_s} | {len(sub)}')
        print()

    print('[5] Combined regressions — best blend test:')
    from sklearn.linear_model import LinearRegression
    for tcol, tlabel in [('actual_K', 'K'), ('actual_FP', 'FP')]:
        # All five predictors
        sub = full.dropna(subset=['baseline_xK', 'arsenal_xK', 'stuff_xK', 'lineup_xfp', 'pitcher_xfp', tcol])
        if len(sub) < 30:
            continue
        X = sub[['baseline_xK', 'arsenal_xK', 'stuff_xK', 'lineup_xfp', 'pitcher_xfp']].values
        y = sub[tcol].values
        m = LinearRegression().fit(X, y)
        pred = m.predict(X)
        r = float(np.corrcoef(pred, y)[0, 1])
        print(f'  Target = {tlabel}  (n={len(sub)})  Combined r={r:.4f}  R^2={r*r:.3f}')
        print(f'    coefs: baseline={m.coef_[0]:+.3f}  arsenal={m.coef_[1]:+.3f}  stuff={m.coef_[2]:+.3f}  '
              f'lineup={m.coef_[3]:+.3f}  pitcher_xfp={m.coef_[4]:+.3f}')
        # Step-wise: just lineup_xfp
        m2 = LinearRegression().fit(sub[['lineup_xfp']].values, y)
        r_lineup = float(np.corrcoef(m2.predict(sub[['lineup_xfp']].values), y)[0, 1])
        # Just pitcher_xfp
        m3 = LinearRegression().fit(sub[['pitcher_xfp']].values, y)
        r_pitcher = float(np.corrcoef(m3.predict(sub[['pitcher_xfp']].values), y)[0, 1])
        # Both: lineup + pitcher_xfp
        m4 = LinearRegression().fit(sub[['lineup_xfp', 'pitcher_xfp']].values, y)
        r_both = float(np.corrcoef(m4.predict(sub[['lineup_xfp', 'pitcher_xfp']].values), y)[0, 1])
        print(f'    isolation: lineup_xfp ALONE r={r_lineup:.4f}  pitcher_xfp ALONE r={r_pitcher:.4f}  '
              f'lineup+pitcher r={r_both:.4f}  Δ_combo={r_both - r_pitcher:+.4f}')
        print()

    fname = RES / 'per_start_predictor_battle.csv'
    full.to_csv(fname, index=False)
    print(f'  wrote {fname}')


if __name__ == '__main__':
    main()

"""pitch_arsenal_per_start_test.py — does pitch-arsenal × batter beat baseline per-start?

Test: predict each START's outcomes (K count, BB count, FP) using
  baseline: pitcher's overall swstr% × pitches in start
  matchup:  sum_pitch_type( pitch_mix% × batter_whiff%_on_that_type ) × pitches in start

For each starter outing in 2024-2025:
  - Load every PA in the start (statcast filtered to game_pk + pitcher)
  - For each batter faced, look up career whiff% by pitch group (using
    batter_pitch_weakness.csv for years 2022-2025 data)
  - For each PA, count pitches by group and compute expected whiff = mix × b_whiff
  - Sum to game-level: expected_K (proxy = expected_swstr * 0.5? — calibrate)

Compare predicted K count per start to actual K count per start.

Output:
  data/research/pitch_arsenal_per_start.csv
    columns: game_pk, pitcher, baseline_xK, matchup_xK, actual_K, ...

Reports:
  Pearson r (baseline vs actual)
  Pearson r (matchup vs actual)
  Δr — does matchup beat baseline?
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
PA_TERMINATORS = {
    'single', 'double', 'triple', 'home_run',
    'walk', 'intent_walk', 'hit_by_pitch',
    'strikeout', 'strikeout_double_play',
    'field_out', 'force_out', 'grounded_into_double_play',
    'sac_fly', 'sac_bunt', 'fielders_choice', 'fielders_choice_out',
    'double_play', 'triple_play', 'field_error', 'catcher_interf',
}


def load_batter_whiff_lookup() -> dict:
    """{batter: {pitch_group: whiff_per_swing}} — career level."""
    p = OUT / 'batter_pitch_weakness.csv'
    if not p.exists():
        return {}
    bw = pd.read_csv(p)
    out = {}
    for _, r in bw.iterrows():
        b = int(r['batter']); ptg = r['ptg']; w = r.get('whiff_per_swing')
        if pd.isna(w):
            continue
        out.setdefault(b, {})[ptg] = float(w) / 100.0  # convert to 0-1
    return out


def main():
    RES.mkdir(parents=True, exist_ok=True)
    print('[1] Loading batter whiff% by pitch group...')
    b_whiff = load_batter_whiff_lookup()
    print(f'   {len(b_whiff)} batters with profile')

    print('[2] Aggregating per-start pitcher pitch counts + expected whiffs...')
    rows = []
    for year in [2024, 2025]:
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=[
            'game_pk', 'pitcher', 'batter', 'pitch_type', 'description',
            'inning', 'events'])
        # Restrict to SP-style outings: pitcher appearing in inning 1
        sp_games = df[df['inning'] == 1].groupby(['game_pk', 'pitcher']).size().reset_index().rename(columns={0: '_n'})
        sp_games = sp_games[['game_pk', 'pitcher']].drop_duplicates()
        df = df.merge(sp_games, on=['game_pk', 'pitcher'], how='inner')
        df = df[df['pitch_type'].notna() & df['batter'].notna()].copy()
        df['ptg'] = df['pitch_type'].map(PITCH_GROUPS).fillna('OTHER')
        df['swing'] = df['description'].isin(SWINGS).astype(int)
        df['whiff'] = df['description'].isin(WHIFFS).astype(int)

        # Per-start pitcher overall swstr% (baseline expected whiffs)
        per_start = df.groupby(['game_pk', 'pitcher'], as_index=False).agg(
            pitches=('description', 'count'),
            swings=('swing', 'sum'),
            whiffs=('whiff', 'sum'),
            actual_K=('events', lambda x: x.isin({'strikeout', 'strikeout_double_play'}).sum()),
            actual_BB=('events', lambda x: x.isin({'walk', 'intent_walk'}).sum()),
            actual_PA=('events', lambda x: x.isin(PA_TERMINATORS).sum()),
        )
        per_start['baseline_swstr_rate'] = per_start['whiffs'] / per_start['swings'].replace(0, np.nan)

        # Per-start matchup-expected: for each pitch in the start, look up batter's
        # whiff% on that pitch type and sum. Then divide by total swings to get
        # matchup-expected whiff rate per swing.
        df_swings = df[df['swing'] == 1].copy()
        df_swings['b_whiff_rate'] = df_swings.apply(
            lambda r: b_whiff.get(int(r['batter']), {}).get(r['ptg'], np.nan), axis=1)
        # If batter has no profile, fall back to overall mean
        global_mean = float(np.nanmean([v for d in b_whiff.values() for v in d.values()])) if b_whiff else 0.25
        df_swings['b_whiff_rate'] = df_swings['b_whiff_rate'].fillna(global_mean)
        matchup = df_swings.groupby(['game_pk', 'pitcher'], as_index=False).agg(
            matchup_xWhiff=('b_whiff_rate', 'sum'),  # sum of expected whiffs across swings
            n_swings=('b_whiff_rate', 'count'))
        per_start = per_start.merge(matchup, on=['game_pk', 'pitcher'], how='left')

        # Convert to expected K count: a K typically takes ~3 whiffs. Approximate
        # expected_K = expected_total_whiffs / 3.0  (callibration is rough but
        # both predictors get the same conversion so ranking comparison is fair)
        per_start['baseline_xK'] = per_start['baseline_swstr_rate'] * per_start['swings'] / 3.0
        per_start['matchup_xK'] = per_start['matchup_xWhiff'] / 3.0
        per_start['year'] = year

        # Filter to legitimate starts (≥ 10 PA and ≥ 30 swings)
        per_start = per_start[(per_start['actual_PA'] >= 10) & (per_start['n_swings'] >= 30)]
        rows.append(per_start)

    if not rows:
        print('  no data'); return
    full = pd.concat(rows, ignore_index=True)
    print(f'   {len(full)} qualifying starts')

    # Correlations
    print('\n[3] Per-start correlations:')
    for pred_col, label in [('baseline_xK', 'baseline (pitcher overall swstr%)'),
                             ('matchup_xK', 'matchup (pitch-arsenal × batter whiff%)')]:
        sub = full.dropna(subset=[pred_col, 'actual_K'])
        if len(sub) >= 30:
            r = float(np.corrcoef(sub[pred_col], sub['actual_K'])[0, 1])
            mae = float(np.mean(np.abs(sub[pred_col] - sub['actual_K'])))
            print(f'   {label:<48s}: r={r:.4f}  MAE={mae:.2f}  n={len(sub)}')

    # Combined (linear blend ax + by) test: take residual correlation
    sub = full.dropna(subset=['baseline_xK', 'matchup_xK', 'actual_K'])
    if len(sub) >= 30:
        from sklearn.linear_model import LinearRegression
        X = sub[['baseline_xK', 'matchup_xK']].values
        y = sub['actual_K'].values
        m = LinearRegression().fit(X, y)
        pred = m.predict(X)
        r_combo = float(np.corrcoef(pred, y)[0, 1])
        print(f'\n   COMBINED (least-squares blend baseline+matchup): r={r_combo:.4f}')
        print(f'   coefs: baseline={m.coef_[0]:.3f}  matchup={m.coef_[1]:.3f}  intercept={m.intercept_:.2f}')

    # Per-year breakdown
    print('\n[4] By year:')
    for year, sub in full.groupby('year'):
        rb = float(np.corrcoef(sub['baseline_xK'].fillna(0), sub['actual_K'])[0, 1])
        rm = float(np.corrcoef(sub['matchup_xK'].fillna(0), sub['actual_K'])[0, 1])
        print(f'   {year}: baseline r={rb:.4f}  matchup r={rm:.4f}  Delta={rm-rb:+.4f}  n={len(sub)}')

    fname = RES / 'pitch_arsenal_per_start.csv'
    full.to_csv(fname, index=False)
    print(f'\n  wrote {fname}')


if __name__ == '__main__':
    main()

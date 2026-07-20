"""playoff_peak_pitchers.py — SP version of late-season peak analysis.

Mirror of playoff_peak_analysis.py for SPs: do any starting pitchers
historically peak in the last ~45 days of the regular season?

Method:
  - For each (SP, year), compute fp_per_start in playoff window vs earlier
  - Filter to SPs with ≥3 starts in each window for sample stability
  - Career rollup PA-weighted
  - Cross-year stability

Output:
  data/research/playoff_peak_pitchers.csv
"""
from __future__ import annotations
from datetime import timedelta
from pathlib import Path
import sys
import pandas as pd
from plv_clone.projections import PROJECTIONS
import numpy as np

from plv_clone.paths import ROOT
from plv_clone.league_config import MY_TEAM_NAME
sys.path.insert(0, str(ROOT))
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'
RES = ROOT / 'data' / 'research'

PA_EVENTS = {
    'single', 'double', 'triple', 'home_run', 'walk', 'intent_walk', 'hit_by_pitch',
    'strikeout', 'strikeout_double_play', 'field_out', 'force_out',
    'grounded_into_double_play', 'sac_fly', 'sac_bunt', 'fielders_choice',
    'fielders_choice_out', 'double_play', 'triple_play', 'field_error', 'catcher_interf',
}

PLAYOFF_WINDOW_DAYS = 45
MIN_STARTS_PER_WINDOW = 3


def _per_year_aggs(year: int) -> pd.DataFrame:
    path = CACHE / f'statcast_{year}.parquet'
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path, columns=['game_date', 'game_pk', 'pitcher',
                                          'events', 'inning',
                                          'bat_score', 'post_bat_score'])
    df['game_date'] = pd.to_datetime(df['game_date'])
    # SP filter: pitcher appeared in inning 1 of the game
    sp_games = df[df['inning'] == 1].groupby(['game_pk', 'pitcher']).size().reset_index(name='_n')
    sp_games = sp_games[['game_pk', 'pitcher']]
    df = df.merge(sp_games, on=['game_pk', 'pitcher'], how='inner')
    if df.empty: return pd.DataFrame()

    season_end = df['game_date'].max()
    playoff_start = season_end - timedelta(days=PLAYOFF_WINDOW_DAYS)
    df['in_playoff'] = (df['game_date'] >= playoff_start).astype(int)

    # Compute per-start FP using formula
    pa = df[df['events'].isin(PA_EVENTS)].copy()
    pa['k'] = pa['events'].isin({'strikeout', 'strikeout_double_play'}).astype(int)
    pa['bb'] = pa['events'].isin({'walk', 'intent_walk'}).astype(int)
    pa['hbp'] = (pa['events'] == 'hit_by_pitch').astype(int)
    pa['h'] = pa['events'].isin({'single', 'double', 'triple', 'home_run'}).astype(int)
    pa['runs'] = (pa['post_bat_score'] - pa['bat_score']).fillna(0).clip(lower=0)
    pa['outs'] = (~pa['events'].isin({'single','double','triple','home_run','walk',
                                       'intent_walk','hit_by_pitch','field_error','catcher_interf'})).astype(int)

    # Per game-start aggregation
    per_start = pa.groupby(['pitcher', 'game_pk', 'in_playoff'], as_index=False).agg(
        k=('k','sum'), bb=('bb','sum'), hbp=('hbp','sum'), h=('h','sum'),
        runs=('runs','sum'), outs=('outs','sum'))
    per_start['ip'] = per_start['outs'] / 3.0
    per_start['fp'] = (per_start['k'] + per_start['ip'] * 3.3 - per_start['h']
                       - 2 * per_start['runs'] - per_start['bb'] - per_start['hbp'])

    # Aggregate per (pitcher, in_playoff)
    agg = per_start.groupby(['pitcher', 'in_playoff'], as_index=False).agg(
        starts=('game_pk', 'nunique'), fp=('fp', 'sum'))
    pivot = agg.pivot(index='pitcher', columns='in_playoff',
                       values=['starts', 'fp']).fillna(0)
    pivot.columns = [f'{m}_{int(c)}' for m, c in pivot.columns]
    pivot = pivot.rename(columns={'starts_0': 'starts_pre', 'starts_1': 'starts_playoff',
                                    'fp_0': 'fp_pre', 'fp_1': 'fp_playoff'})
    pivot['year'] = year
    return pivot.reset_index()


def main():
    frames = [_per_year_aggs(y) for y in [2015, 2016, 2017, 2018, 2019, 2021,
                                            2022, 2023, 2024, 2025]]
    full = pd.concat(frames, ignore_index=True)
    full = full[(full['starts_pre'] >= MIN_STARTS_PER_WINDOW)
                 & (full['starts_playoff'] >= MIN_STARTS_PER_WINDOW)]
    full['rate_pre'] = full['fp_pre'] / full['starts_pre']
    full['rate_playoff'] = full['fp_playoff'] / full['starts_playoff']
    full['lift_pct'] = ((full['rate_playoff'] - full['rate_pre'])
                       / full['rate_pre'].replace(0, np.nan).abs() * 100)
    print(f'Qualifying SP-years: {len(full)}')
    print(f'  Mean playoff_lift_pct: {full["lift_pct"].mean():.2f}%')
    print(f'  Median: {full["lift_pct"].median():.2f}%')
    print(f'  Std: {full["lift_pct"].std():.2f}%')

    # Cross-year stability
    pairs = []
    for pid, sub in full.groupby('pitcher'):
        sub = sub.sort_values('year').dropna(subset=['lift_pct'])
        if len(sub) < 2: continue
        for i in range(len(sub) - 1):
            try:
                pairs.append((float(sub.iloc[i]['lift_pct']),
                              float(sub.iloc[i + 1]['lift_pct'])))
            except Exception:
                pass
    pa = np.array([p[0] for p in pairs], dtype=float)
    pb = np.array([p[1] for p in pairs], dtype=float)
    ok = ~(np.isnan(pa) | np.isnan(pb) | np.isinf(pa) | np.isinf(pb))
    if ok.sum() >= 30:
        r = float(np.corrcoef(pa[ok], pb[ok])[0, 1])
        print(f'\nConsecutive-year r: {r:.4f}  (n_pairs={ok.sum()})')
        print(f'  If |r| >= 0.20 → stable signal; < 0.10 → noise')

    # Career rollup
    career = full.groupby('pitcher').agg(
        n_qual_years=('year', 'count'),
        starts_pre=('starts_pre', 'sum'),
        starts_playoff=('starts_playoff', 'sum'),
        fp_pre=('fp_pre', 'sum'),
        fp_playoff=('fp_playoff', 'sum'),
        lift_std=('lift_pct', 'std'),
    ).reset_index()
    career = career[career['n_qual_years'] >= 3]
    career['career_rate_pre'] = career['fp_pre'] / career['starts_pre']
    career['career_rate_playoff'] = career['fp_playoff'] / career['starts_playoff']
    career['career_playoff_lift_pct'] = (
        (career['career_rate_playoff'] - career['career_rate_pre'])
        / career['career_rate_pre'].replace(0, np.nan).abs() * 100)

    # Attach names
    rp = PROJECTIONS.rp3()[['pitcher', 'player_name']]
    rp = rp.drop_duplicates('pitcher')
    career = career.merge(rp, on='pitcher', how='left')

    credible = career[(career['n_qual_years'] >= 4)
                       & career['career_playoff_lift_pct'].notna()]
    credible = credible.sort_values('career_playoff_lift_pct', ascending=False)

    print(f'\n=== Top 15 SP late-season PEAKERS (≥4 qualifying years) ===')
    print(f'{"PITCHER":<25s} {"YRS":>4s} {"PRE_gs":>7s} {"PO_gs":>7s} {"LIFT%":>8s} {"STD":>7s}')
    for _, r in credible.head(15).iterrows():
        nm = r.get('player_name')
        if not isinstance(nm, str): nm = '(unknown)'
        print(f'  {nm:<25s} {r["n_qual_years"]:>4d} {r["starts_pre"]:>7.0f} '
              f'{r["starts_playoff"]:>7.0f} {r["career_playoff_lift_pct"]:>+8.2f}% '
              f'{r["lift_std"]:>7.1f}')

    print(f'\n=== Top 15 SP late-season DECLINERS ===')
    for _, r in credible.tail(15)[::-1].iterrows():
        nm = r.get('player_name')
        if not isinstance(nm, str): nm = '(unknown)'
        print(f'  {nm:<25s} {r["n_qual_years"]:>4d} {r["starts_pre"]:>7.0f} '
              f'{r["starts_playoff"]:>7.0f} {r["career_playoff_lift_pct"]:>+8.2f}% '
              f'{r["lift_std"]:>7.1f}')

    # Cross-ref Ligers SPs
    from plv_clone.league_state import LeagueState
    league = LeagueState()._get_league()
    my_team = next(t for t in league.teams if t.team_name == MY_TEAM_NAME)
    my_names = {p.name for p in my_team.roster
                 if 'SP' in (getattr(p, 'eligibleSlots', None) or [])}
    print(f'\n=== LIGERS SPs — career playoff lift ===')
    print(f'{"PITCHER":<25s} {"LIFT%":>8s} {"YRS":>4s} {"PRE_gs":>7s} {"PO_gs":>7s}')
    for nm in sorted(my_names):
        # rp3 stores "Last, First" — match by last name first
        last = nm.split()[-1]
        match = career[career['player_name'].fillna('').str.contains(last, case=False, na=False)]
        if match.empty: continue
        r = match.iloc[0]
        sig = ''
        if r['n_qual_years'] >= 4 and r['career_playoff_lift_pct'] >= 5:
            sig = '⭐ PEAKER'
        elif r['n_qual_years'] >= 4 and r['career_playoff_lift_pct'] <= -5:
            sig = '⚠ DECLINER'
        nm_disp = r['player_name'] if isinstance(r['player_name'], str) else nm
        print(f'  {nm_disp:<25s} {r["career_playoff_lift_pct"]:>+8.2f}% '
              f'{r["n_qual_years"]:>4d} {r["starts_pre"]:>7.0f} '
              f'{r["starts_playoff"]:>7.0f}  {sig}')

    career.to_csv(RES / 'playoff_peak_pitchers.csv', index=False)
    print(f'\nwrote {RES / "playoff_peak_pitchers.csv"} ({len(career)} qualifying SPs)')


if __name__ == '__main__':
    main()

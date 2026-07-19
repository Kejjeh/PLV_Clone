"""playoff_peak_analysis.py — find batters/SPs who historically peak in playoff weeks.

The H2 lift feature (already in production) captures second-half tilt
(Aug 1 onward). But the FANTASY playoff window is much narrower — last
~6 weeks of the MLB regular season. Some players might be "true late-season
peakers" with a specifically-timed surge.

Method:
  1. Define playoff window = last 45 days of statcast each year (~ Aug 15 → Sep 30)
  2. For each (batter, year), compute fp_per_pa inside vs outside the window
  3. peak_lift = (playoff_window_rate - other_rate) / other_rate * 100
  4. Career-weight by PA in each window across 2015-2025 (exc 2020)
  5. Cross-year stability: does year-T peak_lift predict year-T+1 peak_lift?
     If r >= 0.20, there's stable signal. If <0.10, mostly noise.

Output:
  data/research/playoff_peak_hitters.csv (per-batter career lift + stability)
  data/research/playoff_peak_pitchers.csv (per-SP career lift)
  prints top stable peakers + Ligers-roster cross-reference
"""
from __future__ import annotations
from datetime import timedelta
from pathlib import Path
import sys
import pandas as pd
from plv_clone.projections import PROJECTIONS
import numpy as np
from plv_clone.league_config import MY_TEAM_NAME

ROOT = Path('c:/Users/Joshua/plv_clone')
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

PLAYOFF_WINDOW_DAYS = 45  # last 45 days of statcast each year ≈ Aug 15 → Sep 30
MIN_PA_PER_WINDOW = 50    # need decent sample in each window to count year


def _build_year_aggs(year: int):
    """Return per-batter (pa_pre, fp_pre, pa_playoff, fp_playoff) for this year."""
    path = CACHE / f'statcast_{year}.parquet'
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path, columns=['game_date', 'batter', 'events'])
    df['game_date'] = pd.to_datetime(df['game_date'])
    df = df[df['events'].isin(PA_EVENTS)].copy()
    if df.empty:
        return pd.DataFrame()

    season_end = df['game_date'].max()
    playoff_start = season_end - timedelta(days=PLAYOFF_WINDOW_DAYS)
    df['in_playoff'] = (df['game_date'] >= playoff_start).astype(int)

    df['tb'] = df['events'].map({'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}).fillna(0).astype(int)
    df['bb'] = df['events'].isin({'walk', 'intent_walk'}).astype(int)
    df['hbp'] = (df['events'] == 'hit_by_pitch').astype(int)
    df['k'] = df['events'].isin({'strikeout', 'strikeout_double_play'}).astype(int)
    df['core_fp'] = df['tb'] + df['bb'] + df['hbp'] - df['k']
    df['pa'] = 1

    agg = df.groupby(['batter', 'in_playoff'], as_index=False).agg(
        pa=('pa', 'sum'), fp=('core_fp', 'sum'))
    pivot = agg.pivot(index='batter', columns='in_playoff', values=['pa', 'fp']).fillna(0)
    pivot.columns = [f'{m}_{int(c)}' for m, c in pivot.columns]
    pivot = pivot.rename(columns={'pa_0': 'pa_pre', 'pa_1': 'pa_playoff',
                                    'fp_0': 'fp_pre', 'fp_1': 'fp_playoff'})
    pivot['year'] = year
    return pivot.reset_index()


def main():
    RES.mkdir(parents=True, exist_ok=True)
    frames = []
    for year in [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]:
        frames.append(_build_year_aggs(year))
    full = pd.concat(frames, ignore_index=True)
    full = full[(full['pa_pre'] >= MIN_PA_PER_WINDOW) & (full['pa_playoff'] >= MIN_PA_PER_WINDOW)]
    full['rate_pre'] = full['fp_pre'] / full['pa_pre']
    full['rate_playoff'] = full['fp_playoff'] / full['pa_playoff']
    # Year-level lift in percent
    full['lift_pct'] = ((full['rate_playoff'] - full['rate_pre'])
                       / full['rate_pre'].replace(0, np.nan).abs() * 100)
    print(f'Total qualifying batter-years: {len(full)}')
    print(f'  Mean year-level playoff_lift_pct: {full["lift_pct"].mean():.2f}%')
    print(f'  Median: {full["lift_pct"].median():.2f}%')
    print(f'  Std: {full["lift_pct"].std():.2f}%')

    # Career career rollup per batter (PA-weighted)
    career = full.groupby('batter').agg(
        n_qual_years=('year', 'count'),
        pa_pre=('pa_pre', 'sum'),
        pa_playoff=('pa_playoff', 'sum'),
        fp_pre=('fp_pre', 'sum'),
        fp_playoff=('fp_playoff', 'sum'),
        lift_std=('lift_pct', 'std'),
    ).reset_index()
    career = career[career['n_qual_years'] >= 3]  # ≥3 years of qualifying data
    career['career_rate_pre'] = career['fp_pre'] / career['pa_pre']
    career['career_rate_playoff'] = career['fp_playoff'] / career['pa_playoff']
    career['career_playoff_lift_pct'] = (
        (career['career_rate_playoff'] - career['career_rate_pre'])
        / career['career_rate_pre'].replace(0, np.nan).abs() * 100)

    # Cross-year stability: r between consecutive-year lift
    print('\n=== Cross-year stability of year-level playoff_lift_pct ===')
    pairs = []
    for batter, sub in full.groupby('batter'):
        sub = sub.sort_values('year').dropna(subset=['lift_pct'])
        if len(sub) < 2: continue
        for i in range(len(sub) - 1):
            a, b = sub.iloc[i]['lift_pct'], sub.iloc[i + 1]['lift_pct']
            try:
                pairs.append((float(a), float(b)))
            except (TypeError, ValueError):
                pass
    if pairs:
        pa = np.array([p[0] for p in pairs], dtype=float)
        pb = np.array([p[1] for p in pairs], dtype=float)
        ok = ~(np.isnan(pa) | np.isnan(pb) | np.isinf(pa) | np.isinf(pb))
        if ok.sum() >= 30:
            r = float(np.corrcoef(pa[ok], pb[ok])[0, 1])
            print(f'  consecutive-year r: {r:.4f}  (n_pairs={ok.sum()})')
            print(f'  If |r| >= 0.20 → stable signal; < 0.10 → noise')
        else:
            print(f'  insufficient clean pairs ({ok.sum()})')

    # Attach names
    rh = PROJECTIONS.rh3()[['batter', 'player_name', 'team', 'primary_position']]
    rh = rh.drop_duplicates('batter')
    career = career.merge(rh, on='batter', how='left')

    # Filter to credible peakers: at least 4 qualifying years + low std + high lift
    credible = career[(career['n_qual_years'] >= 4)
                      & (career['career_playoff_lift_pct'].notna())]
    credible = credible.sort_values('career_playoff_lift_pct', ascending=False)

    print(f'\n=== Top 20 STABLE late-season PEAKERS (≥4 qualifying years) ===')
    print(f'{"PLAYER":<25s} {"YRS":>4s} {"PRE_pa":>7s} {"PO_pa":>7s} {"LIFT%":>8s} {"STD":>7s}')
    for _, r in credible.head(20).iterrows():
        nm = r.get('player_name')
        if not isinstance(nm, str): nm = '(unknown)'
        print(f'  {nm:<25s} {r["n_qual_years"]:>4d} {r["pa_pre"]:>7.0f} '
              f'{r["pa_playoff"]:>7.0f} {r["career_playoff_lift_pct"]:>+8.2f}% '
              f'{r["lift_std"]:>7.1f}')

    print(f'\n=== Top 20 STABLE late-season DECLINERS ===')
    for _, r in credible.tail(20)[::-1].iterrows():
        nm = r.get('player_name')
        if not isinstance(nm, str): nm = '(unknown)'
        print(f'  {nm:<25s} {r["n_qual_years"]:>4d} {r["pa_pre"]:>7.0f} '
              f'{r["pa_playoff"]:>7.0f} {r["career_playoff_lift_pct"]:>+8.2f}% '
              f'{r["lift_std"]:>7.1f}')

    # Save full output
    career = career.sort_values('career_playoff_lift_pct', ascending=False)
    career.to_csv(RES / 'playoff_peak_hitters.csv', index=False)
    print(f'\nwrote {RES / "playoff_peak_hitters.csv"} ({len(career)} qualifying batters)')

    # Cross-reference with Ligers roster + top FAs
    from plv_clone.league_state import LeagueState
    league = LeagueState()._get_league()
    my_team = next(t for t in league.teams if t.team_name == MY_TEAM_NAME)
    my_names = {p.name for p in my_team.roster}
    print(f'\n=== LIGERS ROSTER — career playoff lift ===')
    print(f'{"PLAYER":<25s} {"LIFT%":>8s} {"YRS":>4s} {"STD":>7s}')
    for nm in sorted(my_names):
        match = career[career['player_name'] == nm]
        if match.empty:
            continue
        r = match.iloc[0]
        sig = ''
        if r['n_qual_years'] >= 4 and r['career_playoff_lift_pct'] >= 5:
            sig = '⭐ PEAKER'
        elif r['n_qual_years'] >= 4 and r['career_playoff_lift_pct'] <= -5:
            sig = '⚠ DECLINER'
        print(f'  {nm:<25s} {r["career_playoff_lift_pct"]:>+8.2f}% '
              f'{r["n_qual_years"]:>4d} {r["lift_std"]:>7.1f}  {sig}')


if __name__ == '__main__':
    main()

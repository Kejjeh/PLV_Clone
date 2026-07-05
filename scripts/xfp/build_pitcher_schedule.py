"""
build_pitcher_schedule.py — pitcher next-N starts via MLB Stats API.

For each MLB team, pulls the upcoming 14-day schedule with probablePitcher.
Output: data/research/xfp_cache/pitcher_schedule_2026.csv
  Columns: pitcher (mlb_id), pitcher_name, team, opp_team, game_date,
           is_home, start_idx (1 = next start, 2 = second-next, ...)

For each pitcher we keep the next 2 scheduled starts; downstream RP3 reads
this and computes opponent-strength adjusted xFP for the next 2 starts.
"""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
import warnings
import requests
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

import sys as _sys
def _warn(section, exc):
    print(f"WARN {section}: {exc}", file=_sys.stderr)

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = CACHE / 'pitcher_schedule_2026.csv'

DAYS_AHEAD = 14
MAX_STARTS_PER_PITCHER = 2

# Full name -> Statcast abbreviation (matches team_strength_2026.csv)
TEAM_ABBREV = {
    'Arizona Diamondbacks': 'AZ',  'Atlanta Braves': 'ATL',
    'Baltimore Orioles': 'BAL',   'Boston Red Sox': 'BOS',
    'Chicago Cubs': 'CHC',         'Chicago White Sox': 'CWS',
    'Cincinnati Reds': 'CIN',      'Cleveland Guardians': 'CLE',
    'Colorado Rockies': 'COL',     'Detroit Tigers': 'DET',
    'Houston Astros': 'HOU',       'Kansas City Royals': 'KC',
    'Los Angeles Angels': 'LAA',   'Los Angeles Dodgers': 'LAD',
    'Miami Marlins': 'MIA',        'Milwaukee Brewers': 'MIL',
    'Minnesota Twins': 'MIN',      'New York Mets': 'NYM',
    'New York Yankees': 'NYY',     'Athletics': 'ATH',
    'Oakland Athletics': 'ATH',
    'Philadelphia Phillies': 'PHI', 'Pittsburgh Pirates': 'PIT',
    'San Diego Padres': 'SD',      'San Francisco Giants': 'SF',
    'Seattle Mariners': 'SEA',     'St. Louis Cardinals': 'STL',
    'Tampa Bay Rays': 'TB',        'Texas Rangers': 'TEX',
    'Toronto Blue Jays': 'TOR',    'Washington Nationals': 'WSH',
}


def fetch_schedule(start: date, end: date) -> list[dict]:
    """Pull MLB regular-season games + probablePitcher between dates.

    NOT migrated to mlb_stats.get_schedule (item 9-tail, checked 2026-07-04):
    this fetch hydrates ONLY probablePitcher (no team), so it emits team NAMES
    ("Washington Nationals") which main() then maps to abbrevs via TEAM_ABBREV
    and writes to the `team`/`opp_team` columns of pitcher_schedule_2026.csv.
    get_schedule hydrates team → returns ABBREVIATIONS, which would silently
    change those cached columns (live-diffed: name vs abbr on every row). Left
    as-is to keep the model-adjacent CSV byte-stable; revisit only with a
    byte-diff of pitcher_schedule_2026.csv + a downstream-consumer audit.
    """
    url = (
        'https://statsapi.mlb.com/api/v1/schedule'
        f'?sportId=1&startDate={start.isoformat()}&endDate={end.isoformat()}'
        '&hydrate=probablePitcher'
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    rows = []
    for d in data.get('dates', []):
        gd = d.get('date')
        for g in d.get('games', []):
            if g.get('gameType') != 'R':
                continue
            home = g.get('teams', {}).get('home', {})
            away = g.get('teams', {}).get('away', {})
            home_team = (home.get('team') or {}).get('abbreviation') or (home.get('team') or {}).get('name')
            away_team = (away.get('team') or {}).get('abbreviation') or (away.get('team') or {}).get('name')
            home_pp = home.get('probablePitcher') or {}
            away_pp = away.get('probablePitcher') or {}
            if home_pp.get('id'):
                rows.append({
                    'game_date': gd,
                    'pitcher': int(home_pp['id']),
                    'pitcher_name': home_pp.get('fullName'),
                    'team': home_team,
                    'opp_team': away_team,
                    'is_home': 1,
                })
            if away_pp.get('id'):
                rows.append({
                    'game_date': gd,
                    'pitcher': int(away_pp['id']),
                    'pitcher_name': away_pp.get('fullName'),
                    'team': away_team,
                    'opp_team': home_team,
                    'is_home': 0,
                })
    return rows


def main():
    today = date.today()
    end = today + timedelta(days=DAYS_AHEAD)
    print(f'Fetching MLB schedule {today} → {end} (probablePitcher hydrate)...')
    rows = fetch_schedule(today, end)
    if not rows:
        print('No scheduled games returned.')
        return
    df = pd.DataFrame(rows)
    df['game_date'] = pd.to_datetime(df['game_date'])
    df['team_abbrev'] = df['team'].map(TEAM_ABBREV).fillna(df['team'])
    df['opp_team_abbrev'] = df['opp_team'].map(TEAM_ABBREV).fillna(df['opp_team'])
    df['park_team'] = df.apply(
        lambda r: r['team_abbrev'] if r['is_home'] == 1 else r['opp_team_abbrev'], axis=1)
    # Park factor
    # Park factor from the OWNER (audit 2026-07-04): the pooled CSV blended
    # Coliseum years into ATH / the Trop into TB. _park_R_map is PA-weighted
    # pf_R with the VENUE_ERAS clamp. Semantic note: pf_R (run factor) replaces
    # the legacy park_factor column; both are relative multipliers around 1.0.
    try:
        import sys as _sys
        _lib = str(ROOT / 'scripts' / 'xfp')
        if _lib not in _sys.path:
            _sys.path.insert(0, _lib)
        from lib.extra_lenses import _park_R_map
        pf_map = _park_R_map()
        df['park_factor'] = df['park_team'].map(pf_map).fillna(1.0)
    except Exception as e:
        _warn('park_factor_map', e)
        df['park_factor'] = 1.0

    # Platoon factor: pitcher's expected xwOBA vs THIS opponent's L/R lineup mix,
    # divided by their expected vs league-average mix (~30% LHB / 70% RHB).
    # platoon_factor > 1 = matchup harder than usual; < 1 = easier.
    splits_path = ROOT / 'data' / 'research' / 'xfp_cache' / 'pitcher_splits.csv'
    team_hand_path = ROOT / 'data' / 'research' / 'xfp_cache' / 'team_handedness.csv'
    if splits_path.exists() and team_hand_path.exists():
        splits = pd.read_csv(splits_path)
        team_hand = pd.read_csv(team_hand_path)
        # Aggregate splits across recent years (2023-2025) for stability
        recent = splits[splits['year'].isin([2023, 2024, 2025])].copy()
        recent['tbf_vs_L'] = recent['tbf_vs_L'].fillna(0)
        recent['tbf_vs_R'] = recent['tbf_vs_R'].fillna(0)
        recent['wv_L'] = recent['xwoba_vs_L'] * recent['tbf_vs_L']
        recent['wv_R'] = recent['xwoba_vs_R'] * recent['tbf_vs_R']
        agg = recent.groupby(['pitcher','p_throws']).agg(
            tbf_vs_L=('tbf_vs_L','sum'),
            tbf_vs_R=('tbf_vs_R','sum'),
            wv_L=('wv_L','sum'),
            wv_R=('wv_R','sum'),
        ).reset_index()
        agg['xwoba_vs_L_agg'] = agg['wv_L'] / agg['tbf_vs_L'].replace(0, np.nan)
        agg['xwoba_vs_R_agg'] = agg['wv_R'] / agg['tbf_vs_R'].replace(0, np.nan)
        # Backfill missing splits with league-average
        league_xwoba_L = float(agg['xwoba_vs_L_agg'].mean())
        league_xwoba_R = float(agg['xwoba_vs_R_agg'].mean())
        agg['xwoba_vs_L_agg'] = agg['xwoba_vs_L_agg'].fillna(league_xwoba_L)
        agg['xwoba_vs_R_agg'] = agg['xwoba_vs_R_agg'].fillna(league_xwoba_R)
        # Require min sample to use individual splits (else fall back to league avg by p_throws)
        thin_sample = (agg['tbf_vs_L'] + agg['tbf_vs_R']) < 80
        agg.loc[thin_sample & (agg['p_throws']=='L'), 'xwoba_vs_L_agg'] = 0.312
        agg.loc[thin_sample & (agg['p_throws']=='L'), 'xwoba_vs_R_agg'] = 0.339
        agg.loc[thin_sample & (agg['p_throws']=='R'), 'xwoba_vs_L_agg'] = 0.348
        agg.loc[thin_sample & (agg['p_throws']=='R'), 'xwoba_vs_R_agg'] = 0.332

        # Team handedness — use 2025 mix as best forward-looking estimate
        team25 = team_hand[team_hand['year']==2025][['team_abbr','pct_lhb','pct_rhb']]

        df = df.merge(agg[['pitcher','xwoba_vs_L_agg','xwoba_vs_R_agg']],
                      on='pitcher', how='left')
        # Fill missing with league avg by p_throws is hard without p_throws on df; use overall avg
        df['xwoba_vs_L_agg'] = df['xwoba_vs_L_agg'].fillna(league_xwoba_L)
        df['xwoba_vs_R_agg'] = df['xwoba_vs_R_agg'].fillna(league_xwoba_R)

        df = df.merge(team25.rename(columns={'team_abbr':'opp_team_abbrev',
                                               'pct_lhb':'opp_pct_lhb',
                                               'pct_rhb':'opp_pct_rhb'}),
                      on='opp_team_abbrev', how='left')
        # League-avg mix fallback
        df['opp_pct_lhb'] = df['opp_pct_lhb'].fillna(0.30)
        df['opp_pct_rhb'] = df['opp_pct_rhb'].fillna(0.70)

        df['expected_xwoba_vs_opp']  = (df['opp_pct_lhb'] * df['xwoba_vs_L_agg']
                                         + df['opp_pct_rhb'] * df['xwoba_vs_R_agg'])
        df['expected_xwoba_vs_avg']  = (0.30 * df['xwoba_vs_L_agg']
                                         + 0.70 * df['xwoba_vs_R_agg'])
        df['platoon_factor'] = (df['expected_xwoba_vs_opp']
                                / df['expected_xwoba_vs_avg'].replace(0, np.nan)).fillna(1.0)
    else:
        df['platoon_factor'] = 1.0

    df = df.sort_values(['pitcher', 'game_date']).reset_index(drop=True)
    df['start_idx'] = df.groupby('pitcher').cumcount() + 1
    df = df[df['start_idx'] <= MAX_STARTS_PER_PITCHER]
    # Don't clobber a good schedule with nothing. An empty/near-empty result is an API
    # outage, not a real "no probables" day (there are always probables a few days out).
    # Raise BEFORE the atomic write so the existing file survives and the fail-soft
    # refresh wrapper logs a failed step instead of silently shipping a stale schedule.
    if df.empty:
        raise ValueError('pitcher_schedule build produced 0 probable starts — likely '
                         'an MLB schedule API outage. Keeping the existing file.')
    # Atomic write — temp file then rename so concurrent readers (boom_stack
    # consumers) never see a half-written CSV.
    tmp = OUT.with_suffix('.csv.tmp')
    df.to_csv(tmp, index=False)
    import os
    os.replace(tmp, OUT)
    date_min = pd.to_datetime(df['game_date']).min().date()
    date_max = pd.to_datetime(df['game_date']).max().date()
    print(f'Wrote {OUT}: {len(df)} probable starts ({df["pitcher"].nunique()} pitchers), '
          f'dates {date_min} → {date_max}')
    print('Sample:')
    sample_cols = ['pitcher', 'pitcher_name', 'team', 'opp_team', 'game_date', 'start_idx']
    print(df[sample_cols].head(10).to_string(index=False))


if __name__ == '__main__':
    main()

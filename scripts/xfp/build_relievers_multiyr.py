"""build_relievers_multiyr.py — per-(reliever, year) substrate for RP models.

Mirrors `build_sp_multiyr.py` but for relievers. Filters statcast pitches to
non-starter appearances (pitcher entered after inning 1), aggregates per-pitcher
rate stats, and joins MLB Stats API counting stats (saves, holds, blown saves).

RP eligibility: from MLB API, pitcher must have G ≥ 20 AND GS ≤ 5 in that
season. (5 GS allows for openers / spot starters / two-way roles.)

Role classification (saves-focused per user spec):
  - 'closer'   : SV ≥ 15 OR (SV+SVO ≥ 20)
  - 'setup'    : HLD ≥ 15 (not closer)
  - 'middle'   : G ≥ 30 (not above)
  - 'long_low' : G < 30 (low-leverage / spot)

Fantasy points formula (user's ESPN scoring):
  FP = K + IP*3.3 + SV*5 + HLD*3 - BB - 2*ER - H - HBP

Output: data/research/xfp_cache/relievers_multiyr_2018_2026.csv
"""
from __future__ import annotations
import json
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = CACHE / 'relievers_multiyr_2018_2026.csv'

YEARS = [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]

SWING_DESC = {'swinging_strike','swinging_strike_blocked','foul','foul_tip',
              'hit_into_play','foul_bunt','missed_bunt'}
SWSTR_DESC = {'swinging_strike','swinging_strike_blocked','foul_tip','missed_bunt'}

# RP eligibility (per-year)
MIN_G = 20
MAX_GS = 5

# Scoring (user's ESPN)
def fp_from(k, ip, sv, hld, bb, er, h, hbp):
    return k + ip*3.3 + sv*5 + hld*3 - bb - 2*er - h - hbp


def classify_role(g, gs, sv, svo, hld) -> str:
    if (sv or 0) >= 15 or ((sv or 0) + (svo or 0)) >= 20:
        return 'closer'
    if (hld or 0) >= 15:
        return 'setup'
    if (g or 0) >= 30:
        return 'middle'
    return 'long_low'


def annotate_pitches(d: pd.DataFrame) -> pd.DataFrame:
    desc = d['description'].fillna('')
    ev = d['events'].fillna('')

    d['in_zone']  = (d['zone'] >= 1) & (d['zone'] <= 9)
    d['is_swing'] = desc.isin(SWING_DESC)
    d['is_swstr'] = desc.isin(SWSTR_DESC)
    d['is_contact'] = d['is_swing'] & ~d['is_swstr']
    d['is_called_strike'] = desc == 'called_strike'
    d['z_swing']   = d['is_swing']   & d['in_zone']
    d['o_swing']   = d['is_swing']   & ~d['in_zone']

    d['is_pa_end'] = ev != ''
    d['is_k']      = ev == 'strikeout'
    d['is_bb']     = ev == 'walk'
    d['is_hbp']    = ev == 'hit_by_pitch'
    d['is_h']      = ev.isin({'single','double','triple','home_run'})
    d['is_hr']     = ev == 'home_run'
    d['is_bip']    = d['is_pa_end'] & ~d['is_k'] & ~d['is_bb'] & ~d['is_hbp']

    woba_v = pd.to_numeric(d.get('woba_value'), errors='coerce')
    woba_d = pd.to_numeric(d.get('woba_denom'), errors='coerce')
    xwoba = pd.to_numeric(d.get('estimated_woba_using_speedangle'), errors='coerce')
    d['woba_v_pa'] = woba_v
    bip_with = d['is_bip'] & xwoba.notna()
    d.loc[bip_with, 'woba_v_pa'] = xwoba[bip_with]
    d['woba_d_pa'] = woba_d
    return d


def aggregate_window(pitches: pd.DataFrame) -> pd.DataFrame:
    g = pitches.groupby('pitcher')
    agg = g.agg(
        pitches      =('pitcher', 'size'),
        tbf          =('is_pa_end', 'sum'),
        bip          =('is_bip', 'sum'),
        in_zone      =('in_zone', 'sum'),
        swing        =('is_swing', 'sum'),
        contact      =('is_contact', 'sum'),
        swstr        =('is_swstr', 'sum'),
        called_strike=('is_called_strike', 'sum'),
        z_swing      =('z_swing', 'sum'),
        o_swing      =('o_swing', 'sum'),
        avg_velo     =('release_speed', 'mean'),
        avg_pfxz     =('pfx_z', 'mean'),
        woba_v_sum   =('woba_v_pa', 'sum'),
        woba_d_sum   =('woba_d_pa', 'sum'),
    ).reset_index()
    pn = agg['pitches'].replace(0, np.nan)
    sw = agg['swing'].replace(0, np.nan)
    iz = agg['in_zone'].replace(0, np.nan)
    out_zone = (agg['pitches'] - agg['in_zone']).replace(0, np.nan)
    tbf = agg['tbf'].replace(0, np.nan)
    agg['swstr_pct']    = agg['swstr'] / pn
    agg['c_plus_swstr'] = (agg['called_strike'] + agg['swstr']) / pn
    agg['zone_pct']     = agg['in_zone'] / pn
    agg['z_swing_pct']  = agg['z_swing'] / iz
    agg['o_swing_pct']  = agg['o_swing'] / out_zone
    agg['contact_pct']  = agg['contact'] / sw
    agg['xwoba_per_pa'] = agg['woba_v_sum'] / agg['woba_d_sum'].replace(0, np.nan)
    return agg


def relief_pitches_only(pitches_anno: pd.DataFrame, pitches_full: pd.DataFrame) -> pd.DataFrame:
    """Restrict to relief appearances: filter out pitches thrown by the SP
    (the pitcher who started the inning_topbot half)."""
    p = pitches_full.copy()
    p['inning'] = pd.to_numeric(p['inning'], errors='coerce')
    starts = (p[p['inning'] == 1]
              .groupby(['game_pk', 'inning_topbot'])['pitcher']
              .first().reset_index().rename(columns={'pitcher': 'starter_id'}))
    p_marked = pitches_anno.merge(starts, on=['game_pk', 'inning_topbot'], how='left')
    return p_marked[p_marked['pitcher'] != p_marked['starter_id']].copy()


def build_year(year: int) -> pd.DataFrame:
    sc_path = CACHE / f'statcast_{year}.parquet'
    cnt_path = CACHE / f'pitcher_counting_stats_{year}.json'
    if not sc_path.exists() or not cnt_path.exists():
        return pd.DataFrame()
    print(f'[{year}] loading statcast...', flush=True)
    pitches = pd.read_parquet(sc_path)
    pitches['game_date'] = pd.to_datetime(pitches['game_date'])
    pitches_anno = annotate_pitches(pitches)
    relief = relief_pitches_only(pitches_anno, pitches)
    print(f'  relief pitches: {len(relief):,} of {len(pitches):,} '
          f'({100*len(relief)/max(len(pitches),1):.1f}%)')
    rates = aggregate_window(relief)

    # Counting stats from MLB Stats API
    cnt = json.loads(cnt_path.read_text())
    cnt_df = pd.DataFrame(cnt)
    # IP comes as e.g. "65.1" meaning 65 + 1/3.  Normalize.
    def parse_ip(v):
        if v is None or pd.isna(v):
            return np.nan
        s = str(v)
        if '.' in s:
            whole, frac = s.split('.', 1)
            return float(whole) + (1/3 if frac.startswith('1') else 2/3 if frac.startswith('2') else 0)
        return float(v)
    cnt_df['ip'] = cnt_df['inningsPitched'].map(parse_ip)
    cnt_keep = cnt_df[['pitcher', 'name', 'season', 'team_abbr',
                       'gamesPitched', 'gamesStarted', 'gamesFinished',
                       'ip', 'battersFaced',
                       'wins', 'losses', 'saves', 'saveOpportunities', 'holds',
                       'blownSaves', 'strikeOuts', 'baseOnBalls', 'hits',
                       'earnedRuns', 'homeRuns', 'hitByPitch', 'era', 'whip']]
    cnt_keep = cnt_keep.rename(columns={
        'gamesPitched': 'g',
        'gamesStarted': 'gs',
        'gamesFinished': 'gf',
        'battersFaced': 'tbf_api',
        'saves': 'sv',
        'saveOpportunities': 'svo',
        'holds': 'hld',
        'blownSaves': 'bs',
        'strikeOuts': 'k',
        'baseOnBalls': 'bb',
        'hits': 'h',
        'earnedRuns': 'er',
        'homeRuns': 'hr_allowed',
        'hitByPitch': 'hbp',
    })
    cnt_keep['era'] = pd.to_numeric(cnt_keep['era'], errors='coerce')
    cnt_keep['whip'] = pd.to_numeric(cnt_keep['whip'], errors='coerce')

    # RP eligibility
    rp = cnt_keep[(cnt_keep['g'] >= MIN_G) & (cnt_keep['gs'] <= MAX_GS)].copy()
    rp['role'] = rp.apply(lambda r: classify_role(r['g'], r['gs'], r['sv'], r['svo'], r['hld']),
                          axis=1)
    print(f'  RP-eligible (G≥{MIN_G}, GS≤{MAX_GS}): {len(rp)}')

    # Compute FP from counting stats
    rp['fp'] = (rp['k'] + rp['ip']*3.3 + rp['sv']*5 + rp['hld']*3
                - rp['bb'] - 2*rp['er'] - rp['h'] - rp['hbp']).round(2)
    rp['fp_per_g'] = (rp['fp'] / rp['g'].replace(0, np.nan)).round(3)
    rp['fp_per_ip'] = (rp['fp'] / rp['ip'].replace(0, np.nan)).round(3)
    rp['k_pct'] = (rp['k'] / rp['tbf_api'].replace(0, np.nan)).round(4)
    rp['bb_pct'] = (rp['bb'] / rp['tbf_api'].replace(0, np.nan)).round(4)

    # Join statcast rates
    merged = rp.merge(rates, on='pitcher', how='left')
    merged['year'] = year
    return merged


def main():
    print('=== build_relievers_multiyr ===', flush=True)
    frames = []
    for yr in YEARS:
        df = build_year(yr)
        if not df.empty:
            print(f'  [{yr}] {len(df)} RP-year rows')
            frames.append(df)
    if not frames:
        print('No data — abort'); return
    big = pd.concat(frames, ignore_index=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    big.to_csv(OUT, index=False)
    print(f'\nWrote {OUT}: {len(big)} rows')

    # Verification print-outs
    print('\n--- Role distribution by year ---')
    print(big.groupby(['year', 'role']).size().unstack(fill_value=0).to_string())

    print('\n--- 2025 top 10 RPs by FP ---')
    s25 = big[big['year'] == 2025].sort_values('fp', ascending=False).head(10)
    print(s25[['name','team_abbr','role','g','ip','sv','hld','bs','k','bb','er','fp','fp_per_g']].to_string(index=False))

    print('\n--- 2024 top 10 RPs by FP ---')
    s24 = big[big['year'] == 2024].sort_values('fp', ascending=False).head(10)
    print(s24[['name','team_abbr','role','g','ip','sv','hld','bs','k','bb','er','fp','fp_per_g']].to_string(index=False))

    print('\n--- Closer Y/Y stability check (2024 closer who is 2025 closer?) ---')
    c24 = set(big[(big['year']==2024) & (big['role']=='closer')]['pitcher'])
    c25 = set(big[(big['year']==2025) & (big['role']=='closer')]['pitcher'])
    overlap = c24 & c25
    print(f'  2024 closers: {len(c24)},  2025 closers: {len(c25)},  '
          f'overlap: {len(overlap)} ({100*len(overlap)/max(len(c24),1):.0f}% of 24)')

    print('\n--- Statcast rate coverage in RP rows ---')
    cov = big.groupby('year').agg(
        n=('pitcher','size'),
        with_rates=('xwoba_per_pa', lambda s: int(s.notna().sum()))
    )
    print(cov.to_string())


if __name__ == '__main__':
    main()

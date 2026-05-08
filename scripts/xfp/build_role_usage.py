"""build_role_usage.py — per-(pitcher, year, game) appearance summary.

Derives, from statcast pitch-level data, for each pitcher's appearance in a
game:
  - gf : 1 if pitcher threw the final pitch of the game
  - sv : approximate save (GF + winning team + lead at exit ≤ 3 OR IP ≥ 3)
  - hld: approximate hold (appearance + winning team + lead at entry ∈ [1,3]
         + not GF + lead held)
  - lead_at_entry, lead_at_exit, ip_in_appearance, game_date

Output: data/research/xfp_cache/role_usage_appearances_{year}.parquet
        per (pitcher, game_pk) row.
"""
from __future__ import annotations
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')
ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]


def per_game_appearances(p: pd.DataFrame) -> pd.DataFrame:
    """Compute per-(pitcher, game) appearance summary."""
    p = p.copy()
    # Ordering within game: inning ascending, then at_bat_number, then pitch_number
    p['inning']         = pd.to_numeric(p['inning'], errors='coerce').fillna(0)
    p['at_bat_number']  = pd.to_numeric(p['at_bat_number'], errors='coerce').fillna(0)
    p['pitch_number']   = pd.to_numeric(p['pitch_number'], errors='coerce').fillna(0)
    p['_topbot_order']  = (p['inning_topbot'] == 'Bot').astype(int)  # Top before Bot
    p['_order'] = (p['inning'] * 1e7
                   + p['_topbot_order'] * 1e5
                   + p['at_bat_number'] * 100
                   + p['pitch_number']).astype('int64')

    # Pitcher's team per pitch
    p['pitcher_team'] = np.where(p['inning_topbot'] == 'Top', p['home_team'], p['away_team'])
    p['opp_team']     = np.where(p['inning_topbot'] == 'Top', p['away_team'], p['home_team'])

    p['bat_score'] = pd.to_numeric(p.get('bat_score'), errors='coerce').fillna(0)
    p['fld_score'] = pd.to_numeric(p.get('fld_score'), errors='coerce').fillna(0)
    p['post_bat_score'] = pd.to_numeric(p.get('post_bat_score'), errors='coerce').fillna(0)
    p['post_fld_score'] = pd.to_numeric(p.get('post_fld_score'), errors='coerce').fillna(0)
    p['post_home_score'] = pd.to_numeric(p.get('post_home_score'), errors='coerce').fillna(0)
    p['post_away_score'] = pd.to_numeric(p.get('post_away_score'), errors='coerce').fillna(0)

    # IP (outs) per pitch — count out-events
    ev = p['events'].fillna('')
    out_events = {'strikeout','field_out','grounded_into_double_play','sac_fly',
                  'sac_bunt','force_out','double_play','triple_play',
                  'fielders_choice_out','caught_stealing_2b','caught_stealing_3b',
                  'caught_stealing_home','other_out'}
    p['outs_made'] = ev.isin(out_events).astype(int)
    p.loc[ev.isin(['grounded_into_double_play','double_play']), 'outs_made'] = 2
    p.loc[ev == 'triple_play', 'outs_made'] = 3

    # Per-game final scores (max post scores)
    game_final = p.groupby('game_pk').agg(
        final_home=('post_home_score', 'max'),
        final_away=('post_away_score', 'max'),
        game_date=('game_date', 'first'),
    ).reset_index()
    game_final['winner'] = np.where(game_final['final_home'] > game_final['final_away'], 'home',
                                    np.where(game_final['final_away'] > game_final['final_home'], 'away', 'tie'))

    # Per-game LAST pitch — pitcher who finishes the game gets GF
    p_sorted = p.sort_values(['game_pk', '_order'])
    last_pitch_per_game = p_sorted.groupby('game_pk').tail(1)[['game_pk','pitcher','pitcher_team','_order']]
    last_pitch_per_game = last_pitch_per_game.rename(columns={'pitcher': 'finisher_pitcher'})

    # Per-(game, pitcher) appearance summary
    g = p_sorted.groupby(['game_pk', 'pitcher'])
    apps = g.agg(
        first_order=('_order', 'min'),
        last_order=('_order', 'max'),
        outs_in_app=('outs_made', 'sum'),
        first_bat_score=('bat_score', 'first'),  # opp score at entry
        first_fld_score=('fld_score', 'first'),  # pitcher's team score at entry
        last_post_bat=('post_bat_score', 'last'),
        last_post_fld=('post_fld_score', 'last'),
        pitcher_team=('pitcher_team', 'first'),
        opp_team=('opp_team', 'first'),
    ).reset_index()
    apps['ip_in_app'] = apps['outs_in_app'] / 3.0
    apps['lead_at_entry'] = apps['first_fld_score'] - apps['first_bat_score']
    apps['lead_at_exit']  = apps['last_post_fld'] - apps['last_post_bat']

    # Merge in game-level info
    apps = apps.merge(game_final[['game_pk','game_date','winner','final_home','final_away']],
                      on='game_pk', how='left')
    apps = apps.merge(last_pitch_per_game[['game_pk','finisher_pitcher']],
                      on='game_pk', how='left')

    # Pitcher's team won?
    apps['pitcher_team_won'] = ((apps['pitcher_team'] == apps['home_team_label_helper'])
                                if 'home_team_label_helper' in apps.columns else False)
    # Recompute via direct match
    apps['_team_was_home'] = (apps['pitcher_team'] == apps['pitcher_team'])  # always true; placeholder
    # Determine if pitcher's team is home or away
    p_first = p_sorted.groupby(['game_pk','pitcher']).head(1)[['game_pk','pitcher','home_team','away_team','pitcher_team']]
    p_first['team_is_home'] = (p_first['pitcher_team'] == p_first['home_team'])
    apps = apps.merge(p_first[['game_pk','pitcher','team_is_home']], on=['game_pk','pitcher'], how='left')
    apps['pitcher_team_won'] = (
        (apps['team_is_home'] & (apps['final_home'] > apps['final_away'])) |
        (~apps['team_is_home'] & (apps['final_away'] > apps['final_home']))
    )

    # GF: pitcher threw the final pitch of the game
    apps['gf'] = (apps['pitcher'] == apps['finisher_pitcher']).astype(int)

    # SV: GF + team won + (lead at exit ∈ [1,3]) OR (lead at exit > 3 AND ip ≥ 3)
    sv_close = apps['gf'].astype(bool) & apps['pitcher_team_won'] & \
               (apps['lead_at_exit'] >= 1) & (apps['lead_at_exit'] <= 3)
    sv_long  = apps['gf'].astype(bool) & apps['pitcher_team_won'] & \
               (apps['lead_at_exit'] > 3) & (apps['ip_in_app'] >= 3.0)
    apps['sv'] = (sv_close | sv_long).astype(int)

    # HLD: appearance + team won + lead at entry ∈ [1,3] + NOT GF + lead held + ≥1 out
    hld_cond = (
        (apps['gf'] == 0) & apps['pitcher_team_won'] &
        (apps['lead_at_entry'] >= 1) & (apps['lead_at_entry'] <= 3) &
        (apps['lead_at_exit'] >= 1) & (apps['outs_in_app'] >= 1)
    )
    apps['hld'] = hld_cond.astype(int)

    # Blown save approximation: GF + team didn't win + lead at entry > 0
    apps['blown_sv'] = ((apps['gf'] == 1) & (~apps['pitcher_team_won']) &
                        (apps['lead_at_entry'] >= 1)).astype(int)

    keep = ['game_pk','pitcher','game_date','pitcher_team','team_is_home',
            'first_order','last_order','outs_in_app','ip_in_app',
            'lead_at_entry','lead_at_exit',
            'pitcher_team_won','gf','sv','hld','blown_sv']
    return apps[keep]


def build_year(year: int) -> pd.DataFrame:
    sc_path = CACHE / f'statcast_{year}.parquet'
    if not sc_path.exists():
        return pd.DataFrame()
    print(f'[{year}] loading statcast...', flush=True)
    keep_cols = ['game_pk','game_date','pitcher','inning','inning_topbot',
                 'at_bat_number','pitch_number','events',
                 'home_team','away_team','bat_score','fld_score',
                 'post_bat_score','post_fld_score','post_home_score','post_away_score']
    pitches = pd.read_parquet(sc_path, columns=keep_cols)
    pitches['game_date'] = pd.to_datetime(pitches['game_date'])
    apps = per_game_appearances(pitches)
    print(f'  appearances: {len(apps)}, GFs: {apps["gf"].sum()}, '
          f'SVs: {apps["sv"].sum()}, HLDs: {apps["hld"].sum()}, '
          f'BSs: {apps["blown_sv"].sum()}')
    return apps


def main():
    print('=== build_role_usage ===')
    for yr in YEARS:
        out_path = CACHE / f'role_usage_appearances_{yr}.parquet'
        apps = build_year(yr)
        if apps.empty:
            continue
        apps['year'] = yr
        apps.to_parquet(out_path, index=False)
        print(f'  wrote {out_path.name}')


if __name__ == '__main__':
    main()

"""skill_health_check.py — compare a player's 2026 underlying skill vs career.

The slump-precedent module says X player will likely bounce based on
career history of similar slumps. But that assumes the player's
underlying skills haven't shifted. This script audits the SKILL side:
EV, K%, BB%, whiff%, barrel%, hard-hit%, bat speed (2024+).

For each target player:
  - Pull 2026 statcast data
  - Compute each underlying metric
  - Compare vs 2018-2025 career baseline (PA-weighted)
  - Flag any that are 1+ standard deviation worse (RED) or 0.5+ SD worse (YELLOW)

A player with all-green underlying = the slump is variance, hold.
A player with RED on EV / bat speed / fastball whiff = lose faith.

Output:
  Console table per player
  data/research/skill_health_{name}.csv
"""
from __future__ import annotations
from pathlib import Path
import sys
import pandas as pd
import numpy as np

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
RES = ROOT / 'data' / 'research'
OUT = ROOT / 'data' / 'outputs'

PA_EVENTS = {
    'single', 'double', 'triple', 'home_run', 'walk', 'intent_walk', 'hit_by_pitch',
    'strikeout', 'strikeout_double_play', 'field_out', 'force_out',
    'grounded_into_double_play', 'sac_fly', 'sac_bunt', 'fielders_choice',
    'fielders_choice_out', 'double_play', 'triple_play', 'field_error', 'catcher_interf',
}
SWINGS = {'foul', 'foul_tip', 'hit_into_play', 'swinging_strike',
          'swinging_strike_blocked', 'missed_bunt'}
WHIFFS = {'swinging_strike', 'swinging_strike_blocked'}
FASTBALL_TYPES = {'FF', 'SI', 'FT', 'FA'}


def _aggregate_player(batter_id: int, year: int) -> dict | None:
    path = CACHE / f'statcast_{year}.parquet'
    if not path.exists():
        return None
    df = pd.read_parquet(path, columns=['batter', 'events', 'description',
                                          'pitch_type', 'launch_speed', 'launch_angle'])
    # bat_speed may not exist pre-2024 — try-best load
    try:
        df_bs = pd.read_parquet(path, columns=['batter', 'bat_speed'])
        df['bat_speed'] = df_bs['bat_speed']
    except Exception:
        df['bat_speed'] = np.nan
    df = df[df['batter'] == batter_id].copy()
    if df.empty: return None

    pa = df[df['events'].isin(PA_EVENTS)].copy()
    if pa.empty: return None

    pa_count = len(pa)
    k = pa['events'].isin({'strikeout', 'strikeout_double_play'}).sum()
    bb = pa['events'].isin({'walk', 'intent_walk'}).sum()

    # Pitch-level swings/whiffs across ALL pitches
    df['is_swing'] = df['description'].isin(SWINGS)
    df['is_whiff'] = df['description'].isin(WHIFFS)
    df['is_fastball'] = df['pitch_type'].isin(FASTBALL_TYPES)
    fb = df[df['is_fastball']]
    fb_swings = fb['is_swing'].sum()
    fb_whiffs = fb['is_whiff'].sum()
    overall_swings = df['is_swing'].sum()
    overall_whiffs = df['is_whiff'].sum()

    # BBE: rows with launch_speed populated
    bbe = df[df['launch_speed'].notna()].copy()
    ev = float(bbe['launch_speed'].mean()) if len(bbe) > 0 else np.nan
    ev90 = float(np.percentile(bbe['launch_speed'], 90)) if len(bbe) > 0 else np.nan
    hard_hit = float((bbe['launch_speed'] >= 95).mean() * 100) if len(bbe) > 0 else np.nan
    # Barrel: ev>=98 AND launch_angle in [26, 30] (simplified)
    barrel = float(((bbe['launch_speed'] >= 98) &
                     bbe['launch_angle'].between(26, 30)).mean() * 100) if len(bbe) > 0 else np.nan

    bs = df['bat_speed'] if 'bat_speed' in df.columns else None
    bat_speed = float(bs.mean()) if (bs is not None and bs.notna().any()) else np.nan

    return {
        'year': year, 'pa': pa_count,
        'k_pct': float(k / pa_count * 100),
        'bb_pct': float(bb / pa_count * 100),
        'swstr_pct': float(overall_whiffs / max(len(df), 1) * 100),
        'whiff_per_swing_pct': float(overall_whiffs / max(overall_swings, 1) * 100),
        'fb_whiff_per_swing_pct': float(fb_whiffs / max(fb_swings, 1) * 100) if fb_swings > 0 else np.nan,
        'ev': ev, 'ev90': ev90,
        'hard_hit_pct': hard_hit, 'barrel_pct': barrel,
        'bat_speed': bat_speed,
        'bbe': len(bbe),
    }


def main():
    rh = pd.read_csv(OUT / 'xfp_rh3_projections.csv')
    targets = [('Bo Bichette', None), ('Salvador Perez', None)]

    summary_rows = []
    for name, _ in targets:
        row = rh[rh['player_name'] == name]
        if row.empty:
            print(f'{name}: not in rh3'); continue
        bid = int(row.iloc[0]['batter'])

        # Per-year data
        year_data = []
        for y in [2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]:
            d = _aggregate_player(bid, y)
            if d: year_data.append(d)
        if not year_data: continue

        df = pd.DataFrame(year_data)
        cur = df[df['year'] == 2026].iloc[0]
        career = df[df['year'] < 2026]

        # PA-weighted career averages
        def pa_weighted(col):
            valid = career.dropna(subset=[col])
            if valid['pa'].sum() == 0:
                return np.nan
            return float((valid[col] * valid['pa']).sum() / valid['pa'].sum())

        def career_std(col):
            valid = career.dropna(subset=[col])
            if len(valid) < 2: return np.nan
            return float(valid[col].std())

        print(f'\n{"=" * 78}')
        print(f'{name} — underlying skill health check')
        print(f'{"=" * 78}')
        print(f'  2026 sample: {cur["pa"]} PA, {cur["bbe"]} BBE')
        print(f'  Career sample: {career["pa"].sum()} PA across {len(career)} years (2018-2025 exc 2020)\n')

        metrics = [
            ('K%', 'k_pct', 'lower better'),
            ('BB%', 'bb_pct', 'higher better'),
            ('Overall whiff/swing %', 'whiff_per_swing_pct', 'lower better'),
            ('FASTBALL whiff/swing %', 'fb_whiff_per_swing_pct', 'lower better'),
            ('Avg EV', 'ev', 'higher better'),
            ('EV90', 'ev90', 'higher better'),
            ('Hard-hit %', 'hard_hit_pct', 'higher better'),
            ('Barrel %', 'barrel_pct', 'higher better'),
            ('Bat speed (2024+)', 'bat_speed', 'higher better'),
        ]
        print(f'{"METRIC":<28s} {"2026":>10s} {"CAR":>10s} {"Δ":>9s} {"σ":>7s} {"FLAG":<12s} {"NOTE"}')
        for label, col, direction in metrics:
            cur_v = cur.get(col)
            car_v = pa_weighted(col)
            std_v = career_std(col)
            if pd.isna(cur_v) or pd.isna(car_v):
                continue
            delta = cur_v - car_v
            # Worsening direction
            worse = (delta > 0) if 'lower better' in direction else (delta < 0)
            if pd.notna(std_v) and std_v > 0:
                z = (-delta if 'lower better' in direction else delta) / std_v
                # z negative when "worse"
                flag = 'RED' if z <= -1.0 else ('YELLOW' if z <= -0.5 else 'green')
            else:
                z = np.nan
                flag = 'n/a'
            note = ''
            if flag == 'RED': note = '⚠ potential skill decline'
            elif flag == 'YELLOW': note = 'slight decline'
            print(f'  {label:<28s} {cur_v:>10.2f} {car_v:>10.2f} {delta:>+9.2f} '
                  f'{std_v if pd.notna(std_v) else 0:>7.2f} {flag:<12s} {note}')
            summary_rows.append({
                'player': name, 'metric': label, 'cur_2026': round(cur_v, 2),
                'career_avg': round(car_v, 2), 'delta': round(delta, 2),
                'career_std': round(std_v, 2) if pd.notna(std_v) else None,
                'flag': flag,
            })

        # Verdict
        flags_for_player = [s['flag'] for s in summary_rows if s['player'] == name]
        red_count = flags_for_player.count('RED')
        yellow_count = flags_for_player.count('YELLOW')
        print(f'\n  VERDICT: {red_count} RED flags, {yellow_count} YELLOW flags.')
        if red_count >= 2:
            print(f'  → Underlying skills SHOW DEGRADATION — slump may be real, not just variance')
        elif red_count == 1 or yellow_count >= 3:
            print(f'  → Mixed signals; underlying mostly intact but watch closely')
        else:
            print(f'  → Underlying skills LOOK HEALTHY — slump is most likely variance + bad luck')

    pd.DataFrame(summary_rows).to_csv(RES / 'skill_health_check.csv', index=False)
    print(f'\nwrote {RES / "skill_health_check.csv"}')


if __name__ == '__main__':
    main()

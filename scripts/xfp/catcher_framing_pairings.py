"""catcher_framing_pairings.py — catcher framing rate + pitcher-catcher pair fp.

Framing rate (per catcher): called_strikes / (called_strikes + balls) on pitches
in the "shadow zone" (just outside the rule-book zone). Higher = better framer.

Pairing fp (per pitcher × catcher): mean fp/start when this pitcher works with
this catcher, across career.

Output:
  data/outputs/catcher_framing.csv   (per catcher framing rate)
  data/outputs/pitcher_catcher_pairs.csv  (per pitcher: best/worst catcher)
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path('c:/Users/Joshua/plv_clone')
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'

OUT_EVENTS = {
    'strikeout','strikeout_double_play','field_out','grounded_into_double_play',
    'sac_fly','sac_bunt','force_out','double_play','triple_play',
    'fielders_choice_out','other_out',
    'caught_stealing_2b','caught_stealing_3b','caught_stealing_home',
}
TWO_OUT_EVENTS = {'grounded_into_double_play','double_play'}
PA_EVENTS = {
    'single','double','triple','home_run','walk','intent_walk',
    'hit_by_pitch','strikeout','strikeout_double_play',
    'field_out','force_out','grounded_into_double_play','sac_fly','sac_bunt',
    'fielders_choice','fielders_choice_out','double_play','triple_play',
    'field_error','catcher_interf',
}


def catcher_framing(years=range(2020, 2026)) -> pd.DataFrame:
    """Per-catcher career framing rate (recent years for stability)."""
    frames = []
    for year in years:
        if year == 2020: continue
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists(): continue
        df = pd.read_parquet(path, columns=['fielder_2','description','plate_x','plate_z','sz_top','sz_bot'])
        # Only taken pitches
        df = df[df['description'].isin({'called_strike','ball','blocked_ball'})].copy()
        if df.empty: continue
        # Define shadow zone: ~2 inches outside rulebook zone
        pz = df['plate_z']
        px = df['plate_x'].abs()
        sz_top = df['sz_top']; sz_bot = df['sz_bot']
        # In zone: |x| < 0.83 (10in) and z between sz_bot and sz_top
        in_zone = (px <= 0.83) & (pz <= sz_top) & (pz >= sz_bot)
        # Shadow: just outside (0.83-1.0 in x, or 1-2 in z above/below)
        shadow_x = (px > 0.83) & (px <= 1.0) & (pz <= sz_top + 0.2) & (pz >= sz_bot - 0.2)
        shadow_z_top = (px <= 1.0) & (pz > sz_top) & (pz <= sz_top + 0.2)
        shadow_z_bot = (px <= 1.0) & (pz < sz_bot) & (pz >= sz_bot - 0.2)
        df['shadow'] = (shadow_x | shadow_z_top | shadow_z_bot)
        df['in_zone'] = in_zone
        df['called_strike'] = (df['description'] == 'called_strike').astype(int)
        # Framing only meaningful in shadow zone
        sh = df[df['shadow']].dropna(subset=['fielder_2'])
        agg = sh.groupby('fielder_2', as_index=False).agg(
            shadow_pitches=('called_strike','count'),
            shadow_called_strikes=('called_strike','sum'))
        frames.append(agg)
    if not frames: return pd.DataFrame()
    full = pd.concat(frames, ignore_index=True)
    full = full.groupby('fielder_2', as_index=False).agg(
        shadow_pitches=('shadow_pitches','sum'),
        shadow_called_strikes=('shadow_called_strikes','sum'))
    full = full[full['shadow_pitches'] >= 200]
    full['framing_rate'] = full['shadow_called_strikes']/full['shadow_pitches']
    league_mean = (full['shadow_called_strikes'].sum() / full['shadow_pitches'].sum())
    full['framing_lift_pct'] = ((full['framing_rate'] - league_mean) / league_mean * 100).round(2)
    full = full.rename(columns={'fielder_2':'catcher'})
    full = full.sort_values('framing_lift_pct', ascending=False).reset_index(drop=True)
    return full


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fr = catcher_framing()
    if fr.empty:
        print('  no framing data'); return
    # Attach catcher names from pitcher_counting (which has hitter names too via similar source)
    # Actually fielder_2 is a player_id; pull names from hitters_multiyr or similar
    h_multi = pd.read_csv(CACHE / 'hitters_multiyr_2015_2026.csv')
    names = h_multi[['batter','player_name']].drop_duplicates('batter')
    names = names.rename(columns={'batter':'catcher'})
    fr = fr.merge(names, on='catcher', how='left')
    out = OUT / 'catcher_framing.csv'
    fr.to_csv(out, index=False)
    print(f'  wrote {out} ({len(fr)} catchers)')
    print('  top 10 framers:')
    print(fr.head(10)[['player_name','shadow_pitches','framing_rate','framing_lift_pct']].to_string(index=False))
    print('  bottom 5 framers:')
    print(fr.tail(5)[['player_name','shadow_pitches','framing_rate','framing_lift_pct']].to_string(index=False))


if __name__ == '__main__':
    main()

"""Analyze Jared Jones MiLB rehab — velo, command, arsenal, per-outing."""
import pandas as pd
pd.set_option('display.width', 240)
pd.set_option('display.max_columns', 30)

df = pd.read_csv('data/research/jared_jones_milb_2026.csv')
df['game_date'] = pd.to_datetime(df['game_date'])
print(f"Total MiLB pitches 2026: {len(df)}")
print(f"Date range: {df['game_date'].min().date()} → {df['game_date'].max().date()}")
print(f"Games (distinct game_pk): {df['game_pk'].nunique()}")
print(f"Levels (sport_id, if column exists): {df.columns[df.columns.str.contains('sport', case=False)].tolist()}")
# home/away teams (MiLB affiliate names)
print(f"Home teams faced: {df['home_team'].unique().tolist()}")
print(f"Away teams: {df['away_team'].unique().tolist()}")

# ---- Per-outing summary ----
print("\n=== PER-OUTING SUMMARY ===")
outings = df.groupby('game_date').agg(
    pitches=('pitch_type','count'),
    fb_velo=('release_speed', lambda x: x[df.loc[x.index,'pitch_type'].isin(['FF','FT','SI'])].mean()),
    max_velo=('release_speed','max'),
    swstr=('description', lambda x: (x.isin(['swinging_strike','foul_tip'])).sum()),
    swings=('description', lambda x: (x.isin(['swinging_strike','foul','foul_tip','hit_into_play','foul_bunt','missed_bunt'])).sum()),
    strikes=('type', lambda x: (x == 'S').sum()),
    balls=('type', lambda x: (x == 'B').sum()),
    in_zone=('zone', lambda x: ((x >= 1) & (x <= 9)).sum()),
).reset_index()
outings['whiff_per_swing'] = (outings['swstr'] / outings['swings']).round(3)
outings['strike_pct'] = (outings['strikes'] / (outings['strikes'] + outings['balls'])).round(3)
outings['zone_pct'] = (outings['in_zone'] / outings['pitches']).round(3)
outings['swstr_pct'] = (outings['swstr'] / outings['pitches']).round(3)
for c in ['fb_velo','max_velo']:
    outings[c] = outings[c].round(2)
print(outings.to_string(index=False))

# ---- Per-pitch-type arsenal ----
print("\n=== ARSENAL (full MiLB 2026 sample) ===")
ars = df.groupby('pitch_type').agg(
    n=('pitch_type','count'),
    usage_pct=('pitch_type', lambda x: len(x) / len(df)),
    velo=('release_speed','mean'),
    velo_max=('release_speed','max'),
    pfx_z=('pfx_z', lambda x: (x * 12).mean()),  # convert to inches
    pfx_x=('pfx_x', lambda x: (x * 12).mean()),
    ext=('release_extension','mean'),
    spin=('release_spin_rate','mean'),
    swings=('description', lambda x: (x.isin(['swinging_strike','foul','foul_tip','hit_into_play','foul_bunt','missed_bunt'])).sum()),
    whiffs=('description', lambda x: (x.isin(['swinging_strike','foul_tip','missed_bunt'])).sum()),
    in_zone=('zone', lambda x: ((x >= 1) & (x <= 9)).sum()),
).reset_index()
ars['whiff_per_swing'] = (ars['whiffs'] / ars['swings']).round(3)
ars['zone_pct'] = (ars['in_zone'] / ars['n']).round(3)
ars['usage_pct'] = ars['usage_pct'].round(3)
for c in ['velo','velo_max','pfx_z','pfx_x','ext','spin']:
    ars[c] = ars[c].round(2)
ars = ars.sort_values('n', ascending=False)
show = ['pitch_type','n','usage_pct','velo','velo_max','pfx_z','pfx_x','ext','spin','whiff_per_swing','zone_pct']
print(ars[show].to_string(index=False))

# ---- Command indicators (strikes, walks, K — full season) ----
print("\n=== COMMAND / OUTCOME (full MiLB 2026) ===")
# PA-level
pa = df.dropna(subset=['at_bat_number']).copy()
pa_grp = pa.groupby(['game_pk','at_bat_number']).agg(
    events=('events', lambda x: x.dropna().iloc[0] if len(x.dropna()) else ''),
    reached_2k=('strikes', lambda x: (x == 2).any()),
).reset_index()
total_pa = (pa_grp['events'] != '').sum()
k = (pa_grp['events'] == 'strikeout').sum()
bb = (pa_grp['events'] == 'walk').sum()
hbp = (pa_grp['events'] == 'hit_by_pitch').sum()
print(f"  TBF (events-complete PAs): {total_pa}")
print(f"  K:  {k}  ({k/total_pa*100:.1f}%)")
print(f"  BB: {bb}  ({bb/total_pa*100:.1f}%)")
print(f"  HBP:{hbp}  ({hbp/total_pa*100:.1f}%)")
print(f"  K/BB ratio: {k/max(bb,1):.2f}")

# Strike% and zone%
strikes = (df['type'] == 'S').sum()
balls = (df['type'] == 'B').sum()
print(f"\n  Strike%: {strikes/(strikes+balls)*100:.1f}%")
print(f"  Zone%:   {((df['zone']>=1) & (df['zone']<=9)).sum() / len(df) * 100:.1f}%")
print(f"  CSW%:    {(df['description'].isin(['called_strike','swinging_strike','foul_tip'])).sum() / len(df) * 100:.1f}%")
print(f"  SwStr%:  {(df['description'].isin(['swinging_strike','foul_tip'])).sum() / len(df) * 100:.1f}%")

# ---- Comparison to 2024 MLB baseline ----
print("\n=== COMPARISON: 2024 MLB vs 2026 MiLB rehab ===")
print("                  | 2024 MLB | 2026 MiLB |")
print("------------------|----------|-----------|")
print(f"  FB avg velo     | 97.33    | {ars[ars['pitch_type']=='FF']['velo'].iloc[0] if 'FF' in ars['pitch_type'].values else 'n/a':5}     |")
print(f"  FB max velo     | n/a      | {ars[ars['pitch_type']=='FF']['velo_max'].iloc[0] if 'FF' in ars['pitch_type'].values else 'n/a':5}     |")
print(f"  K%              | 26.3%    | {k/total_pa*100:.1f}%      |")
print(f"  BB%             | 7.6%     | {bb/total_pa*100:.1f}%      |")
print(f"  SwStr%          | 15.0%    | {(df['description'].isin(['swinging_strike','foul_tip'])).sum()/len(df)*100:.1f}%      |")
print(f"  CSW%            | 30.1%    | {(df['description'].isin(['called_strike','swinging_strike','foul_tip'])).sum()/len(df)*100:.1f}%      |")

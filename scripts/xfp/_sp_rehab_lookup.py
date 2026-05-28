"""Generic SP rehab-data lookup via Baseball Savant minors filter.

Usage: python _sp_rehab_lookup.py <pitcher_mlbam_id> [name]
"""
import sys
import urllib.request, io
import pandas as pd
pd.set_option('display.width', 240)
pd.set_option('display.max_columns', 30)

def pull_milb(pid, start='2026-03-01', end='2026-05-28'):
    url = (
        "https://baseballsavant.mlb.com/statcast_search/csv?"
        "all=true"
        "&hfPT=&hfAB=&hfBBT=&hfPR=&hfZ=&stadium=&hfBBL=&hfNewZones="
        "&hfGT=R%7CPO%7CS%7C&hfC=&hfSea=2026%7C&hfSit=&player_type=pitcher"
        f"&hfOuts=&opponent=&pitcher_throws=&batter_stands=&hfSA=&game_date_gt={start}&game_date_lt={end}"
        f"&hfInfield=&team=&position=&hfOutfield=&hfRO=&home_road=&hfFlag=&hfPull=&metric_1="
        f"&hfInn=&min_pitches=0&min_results=0&group_by=name&sort_col=pitches&player_event_sort=api_p_release_speed"
        f"&sort_order=desc&min_pas=0&pitchers_lookup%5B%5D={pid}&minors=true&type=details"
    )
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    return pd.read_csv(io.BytesIO(data))


def summarize(df, name, pid):
    if df.empty:
        print(f"\n>>> {name} (pid={pid}): NO MiLB pitches in 2026")
        return
    df['game_date'] = pd.to_datetime(df['game_date'])
    print(f"\n>>> {name} (pid={pid})")
    print(f"  MiLB pitches: {len(df)}  |  Games: {df['game_pk'].nunique()}  |  Date range: {df['game_date'].min().date()} → {df['game_date'].max().date()}")
    print(f"  Affiliates: {sorted(set(df['home_team'].unique().tolist() + df['away_team'].unique().tolist()))}")

    # Per-outing
    outings = df.groupby('game_date').agg(
        pitches=('pitch_type','count'),
        fb_velo=('release_speed', lambda x: x[df.loc[x.index,'pitch_type'].isin(['FF','FT','SI'])].mean()),
        max_velo=('release_speed','max'),
        swstr=('description', lambda x: (x.isin(['swinging_strike','foul_tip','missed_bunt'])).sum()),
        swings=('description', lambda x: (x.isin(['swinging_strike','foul','foul_tip','hit_into_play','foul_bunt','missed_bunt'])).sum()),
        strikes=('type', lambda x: (x == 'S').sum()),
        balls=('type', lambda x: (x == 'B').sum()),
        in_zone=('zone', lambda x: ((x >= 1) & (x <= 9)).sum()),
    ).reset_index()
    outings['whiff_sw'] = (outings['swstr'] / outings['swings']).round(3)
    outings['strike_pct'] = (outings['strikes'] / (outings['strikes'] + outings['balls'])).round(3)
    outings['zone_pct'] = (outings['in_zone'] / outings['pitches']).round(3)
    outings['swstr_pct'] = (outings['swstr'] / outings['pitches']).round(3)
    for c in ['fb_velo','max_velo']:
        outings[c] = outings[c].round(2)
    print("\n  Per-outing:")
    print(outings[['game_date','pitches','fb_velo','max_velo','strike_pct','zone_pct','whiff_sw','swstr_pct']].to_string(index=False))

    # Arsenal
    ars = df.groupby('pitch_type').agg(
        n=('pitch_type','count'),
        velo=('release_speed','mean'),
        velo_max=('release_speed','max'),
        pfx_z=('pfx_z', lambda x: (x * 12).mean()),
        ext=('release_extension','mean'),
        swings=('description', lambda x: (x.isin(['swinging_strike','foul','foul_tip','hit_into_play','foul_bunt','missed_bunt'])).sum()),
        whiffs=('description', lambda x: (x.isin(['swinging_strike','foul_tip','missed_bunt'])).sum()),
        in_zone=('zone', lambda x: ((x >= 1) & (x <= 9)).sum()),
    ).reset_index()
    ars['whiff_sw'] = (ars['whiffs'] / ars['swings']).round(3)
    ars['zone_pct'] = (ars['in_zone'] / ars['n']).round(3)
    ars['usage'] = (ars['n'] / len(df)).round(3)
    for c in ['velo','velo_max','pfx_z','ext']:
        ars[c] = ars[c].round(2)
    ars = ars.sort_values('n', ascending=False)
    print("\n  Arsenal:")
    print(ars[['pitch_type','n','usage','velo','velo_max','pfx_z','ext','whiff_sw','zone_pct']].to_string(index=False))

    # Outcomes
    pa = df.dropna(subset=['at_bat_number']).copy()
    pa_grp = pa.groupby(['game_pk','at_bat_number']).agg(events=('events', lambda x: x.dropna().iloc[0] if len(x.dropna()) else '')).reset_index()
    total_pa = (pa_grp['events'] != '').sum()
    if total_pa:
        k = (pa_grp['events'] == 'strikeout').sum()
        bb = (pa_grp['events'] == 'walk').sum()
        print(f"\n  Outcomes: TBF={total_pa}  K={k} ({k/total_pa*100:.1f}%)  BB={bb} ({bb/total_pa*100:.1f}%)  K/BB={k/max(bb,1):.2f}")
        print(f"  CSW%: {(df['description'].isin(['called_strike','swinging_strike','foul_tip'])).sum()/len(df)*100:.1f}%   SwStr%: {(df['description'].isin(['swinging_strike','foul_tip'])).sum()/len(df)*100:.1f}%")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        # Default: Arrighetti
        targets = [('Spencer Arrighetti', 681293)]
    else:
        pid = int(sys.argv[1])
        name = sys.argv[2] if len(sys.argv) > 2 else f"pid={pid}"
        targets = [(name, pid)]

    for name, pid in targets:
        try:
            df = pull_milb(pid)
            summarize(df, name, pid)
            df.to_csv(f'data/research/milb_rehab_{pid}_2026.csv', index=False)
        except Exception as e:
            print(f"  err for {name}: {e}")

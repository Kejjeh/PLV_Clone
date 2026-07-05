"""slump_precedent.py — career rolling-window precedent for current performance.

For each fantasy-relevant player, asks: "has this player ever had a streak this
bad in their career, and if so, what happened next?" Computes:
  - cur_rate_core      current 2026 rolling rate (core_fp/PA for hitters,
                       fp/start for SPs, fp/appearance for RPs)
  - pct_rank           current rate's percentile vs all historical rolling
                       windows of the same length in the player's own career
  - n_comparable       count of historical windows at-or-below current rate
  - bounce_pct         % of comparable windows where the next-200-PA (or
                       next-10-start / next-25-appearance) rate exceeded the
                       slump rate
  - median_next_rate   median of the post-slump rate
  - median_delta       median rebound (next - slump)

Outputs:
  data/outputs/slump_precedent_hitters_2026.csv
  data/outputs/slump_precedent_sps_2026.csv
  data/outputs/slump_precedent_rps_2026.csv

Usage:
  python scripts/xfp/slump_precedent.py            # all 3 modes
  python scripts/xfp/slump_precedent.py hitters    # one mode

NOTE: core_fp formula:
  Hitters:  TB + BB + HBP - K   (excludes R, RBI, SB — see caveats)
  SP:       K + IP*3.3 - H - 2*ER - BB - HBP   (per-start)
  RP:       K + IP*3.3 - H - 2*ER - BB - HBP   (per-appearance, no sv/hld bonus)
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from plv_clone.projections import PROJECTIONS

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'

YEARS = list(range(2015, 2027))

PA_EVENTS = {
    'single', 'double', 'triple', 'home_run',
    'walk', 'intent_walk',
    'hit_by_pitch', 'strikeout', 'strikeout_double_play',
    'field_out', 'force_out', 'grounded_into_double_play',
    'sac_fly', 'sac_bunt', 'fielders_choice', 'fielders_choice_out',
    'double_play', 'triple_play', 'field_error', 'catcher_interf',
}
OUT_EVENTS = {
    'strikeout', 'strikeout_double_play', 'field_out', 'grounded_into_double_play',
    'sac_fly', 'sac_bunt', 'force_out', 'double_play', 'triple_play',
    'fielders_choice_out', 'other_out',
    'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
}
TWO_OUT_EVENTS = {'grounded_into_double_play', 'double_play'}


# ─────────────────────────────────────────────────────────────────────────────
# Hitter side
# ─────────────────────────────────────────────────────────────────────────────

def hitter_per_game(batter_id: int) -> pd.DataFrame:
    """Per-game core_fp (TB + BB + HBP - K) and PA for one batter, all years."""
    frames = []
    for year in YEARS:
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists():
            continue
        df = pd.read_parquet(
            path,
            columns=['game_pk', 'game_date', 'batter', 'events'],
            filters=[('batter', '=', batter_id)],
        )
        if df.empty:
            continue
        df = df[df['events'].isin(PA_EVENTS)].copy()
        df['year'] = year
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df['tb'] = df['events'].map({'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}).fillna(0).astype(int)
    df['bb'] = df['events'].isin({'walk', 'intent_walk'}).astype(int)
    df['hbp'] = (df['events'] == 'hit_by_pitch').astype(int)
    df['k'] = df['events'].isin({'strikeout', 'strikeout_double_play'}).astype(int)
    df['pa'] = 1
    g = df.groupby(['year', 'game_date', 'game_pk'], as_index=False).agg(
        tb=('tb', 'sum'), bb=('bb', 'sum'), hbp=('hbp', 'sum'),
        k=('k', 'sum'), pa=('pa', 'sum'),
    )
    g['core_fp'] = g['tb'] + g['bb'] + g['hbp'] - g['k']
    return g.sort_values('game_date').reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Pitcher side (SP per-start, RP per-appearance)
# ─────────────────────────────────────────────────────────────────────────────

def _load_pitcher_year(year: int, pitcher_id: int) -> pd.DataFrame:
    path = CACHE / f'statcast_{year}.parquet'
    if not path.exists():
        return pd.DataFrame()
    cols = ['game_pk', 'game_date', 'pitcher', 'inning', 'inning_topbot',
            'events', 'bat_score', 'post_bat_score', 'at_bat_number']
    df = pd.read_parquet(path, columns=cols, filters=[('pitcher', '=', pitcher_id)])
    if df.empty:
        return df
    df['year'] = year
    return df


def _identify_starter(year: int) -> pd.DataFrame:
    """For each (game_pk, inning_topbot) the inning-1 pitcher = SP for that side.
    Returns one row per (game_pk, inning_topbot, starter_id)."""
    path = CACHE / f'statcast_{year}.parquet'
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path, columns=['game_pk', 'inning', 'inning_topbot', 'pitcher', 'at_bat_number'])
    df = df[df['inning'] == 1].sort_values(['game_pk', 'inning_topbot', 'at_bat_number'])
    starters = df.groupby(['game_pk', 'inning_topbot'])['pitcher'].first().reset_index()
    starters.columns = ['game_pk', 'inning_topbot', 'starter_id']
    return starters


def pitcher_per_appearance(pitcher_id: int) -> pd.DataFrame:
    """Per-appearance pitching stats. Marks each as SP or RP based on whether the
    pitcher started that side of the inning."""
    frames = []
    for year in YEARS:
        df = _load_pitcher_year(year, pitcher_id)
        if df.empty:
            continue
        starters = _identify_starter(year)
        if starters.empty:
            continue
        df = df.merge(starters, on=['game_pk', 'inning_topbot'], how='left')
        df['is_sp'] = (df['pitcher'] == df['starter_id']).astype(int)
        ev = df['events'].fillna('')
        df['k'] = ev.isin({'strikeout', 'strikeout_double_play'}).astype(int)
        df['bb'] = ev.isin({'walk', 'intent_walk'}).astype(int)
        df['hbp'] = (ev == 'hit_by_pitch').astype(int)
        df['h'] = ev.isin({'single', 'double', 'triple', 'home_run'}).astype(int)
        df['outs'] = ev.isin(OUT_EVENTS).astype(int)
        df.loc[ev.isin(TWO_OUT_EVENTS), 'outs'] = 2
        df['is_pa_end'] = (ev != '') & ev.isin(PA_EVENTS)
        runs = (pd.to_numeric(df['post_bat_score'], errors='coerce')
                - pd.to_numeric(df['bat_score'], errors='coerce')).clip(lower=0)
        df['er'] = runs.where(df['is_pa_end'], 0)
        df['year'] = year
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    appearance = df.groupby(['year', 'game_date', 'game_pk', 'is_sp'], as_index=False).agg(
        k=('k', 'sum'), bb=('bb', 'sum'), hbp=('hbp', 'sum'),
        h=('h', 'sum'), outs=('outs', 'sum'), er=('er', 'sum'),
    )
    appearance['ip'] = appearance['outs'] / 3
    # item 13: vectorized — owner is scoring.pitcher_fp scalar; kept inline for perf
    appearance['fp'] = (appearance['k'] + appearance['ip'] * 3.3
                        - appearance['h'] - 2 * appearance['er']
                        - appearance['bb'] - appearance['hbp'])
    return appearance.sort_values('game_date').reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Slump precedent core analysis (mode-agnostic)
# ─────────────────────────────────────────────────────────────────────────────

def slump_precedent(history: pd.DataFrame, *,
                    cur_year: int = 2026,
                    metric_col: str = 'core_fp',
                    denom_col: str = 'pa',
                    next_n: int = 200,
                    min_cur_n: int = 5) -> dict:
    """Compute the slump-precedent metrics from a per-game/appearance history.

    metric_col / denom_col define the rate. For hitters: (core_fp, pa).
    For SP/RP: (fp, 1) — we compare per-start/appearance averages.
    next_n: when computing post-slump performance, accumulate this many denom
            units after the window ends (200 PAs ≈ 1/3 of a season for hitters;
            for SP/RP we pass denom=1 so this is # of starts/appearances).
    """
    if history.empty:
        return {}
    cur = history[history['year'] == cur_year]
    if len(cur) < min_cur_n:
        return {}
    N = len(cur)
    cur_metric = float(cur[metric_col].sum())
    cur_denom = float(cur[denom_col].sum())
    if cur_denom <= 0:
        return {}
    cur_rate = cur_metric / cur_denom

    hist = history.sort_values('game_date').reset_index(drop=True).copy()
    hist['roll_metric'] = hist[metric_col].rolling(N, min_periods=N).sum()
    hist['roll_denom'] = hist[denom_col].rolling(N, min_periods=N).sum()
    hist['roll_rate'] = hist['roll_metric'] / hist['roll_denom']
    valid = hist.dropna(subset=['roll_rate'])
    historical = valid[valid['year'] < cur_year]
    if historical.empty:
        return {'cur_n': N, 'cur_rate': cur_rate, 'pct_rank': None,
                'n_comparable': 0, 'bounce_pct': None, 'median_next_rate': None,
                'median_delta': None, 'unprecedented': True}

    pct = float((historical['roll_rate'] <= cur_rate).mean() * 100)
    n_worse = int((historical['roll_rate'] <= cur_rate).sum())
    if n_worse == 0:
        return {'cur_n': N, 'cur_rate': cur_rate, 'pct_rank': pct,
                'n_comparable': 0, 'bounce_pct': None, 'median_next_rate': None,
                'median_delta': None, 'unprecedented': True}

    bad = historical[historical['roll_rate'] <= cur_rate]
    bounce = []
    for end_idx in bad.index:
        after = hist.loc[end_idx + 1: end_idx + 200]  # up to 200 future games
        cum_d = 0.0
        rows = []
        for _, gr in after.iterrows():
            rows.append(gr)
            cum_d += float(gr[denom_col])
            if cum_d >= next_n:
                break
        if not rows:
            continue
        sub = pd.DataFrame(rows)
        nd = float(sub[denom_col].sum())
        # Require at least 50% of next_n target to count
        if nd < 0.5 * next_n:
            continue
        nr = float(sub[metric_col].sum()) / nd
        sl = float(hist.loc[end_idx, 'roll_rate'])
        bounce.append({'next_rate': nr, 'slump_rate': sl, 'delta': nr - sl})
    if not bounce:
        return {'cur_n': N, 'cur_rate': cur_rate, 'pct_rank': pct,
                'n_comparable': n_worse, 'bounce_pct': None,
                'median_next_rate': None, 'median_delta': None, 'unprecedented': False}

    br = pd.DataFrame(bounce)
    return {
        'cur_n': N,
        'cur_rate': round(cur_rate, 4),
        'pct_rank': round(pct, 1),
        'n_comparable': n_worse,
        'n_bounce_eval': len(br),
        'bounce_pct': round(float((br['delta'] > 0).mean() * 100), 1),
        'median_next_rate': round(float(br['next_rate'].median()), 4),
        'median_delta': round(float(br['delta'].median()), 4),
        'unprecedented': False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Batch drivers
# ─────────────────────────────────────────────────────────────────────────────

def run_hitters(min_2026_pa: int = 50, min_2026_games: int = 12) -> pd.DataFrame:
    print(f'[slump] hitter mode: scanning rh3 projection batters with ≥{min_2026_pa} 2026 PA')
    rh = PROJECTIONS.rh3()
    rh = rh[rh['pa_to'] >= min_2026_pa]
    rows = []
    for i, r in enumerate(rh.itertuples(), 1):
        bid = int(r.batter)
        name = r.player_name
        history = hitter_per_game(bid)
        if history.empty:
            continue
        s = slump_precedent(history, metric_col='core_fp', denom_col='pa', next_n=200,
                            min_cur_n=min_2026_games)
        if not s:
            continue
        s['batter'] = bid
        s['player_name'] = name
        s['team'] = getattr(r, 'team', None)
        rows.append(s)
        if i % 50 == 0:
            print(f'  ...{i}/{len(rh)} processed')
    df = pd.DataFrame(rows)
    if df.empty:
        print('  no rows')
        return df
    df = df[['batter', 'player_name', 'team', 'cur_n', 'cur_rate',
             'pct_rank', 'n_comparable', 'n_bounce_eval', 'bounce_pct',
             'median_next_rate', 'median_delta', 'unprecedented']]
    out = OUT / 'slump_precedent_hitters_2026.csv'
    df.to_csv(out, index=False)
    print(f'  wrote {out} ({len(df)} rows)')
    return df


def run_pitchers(role: str, min_2026_apps: int = 3) -> pd.DataFrame:
    """role: 'SP' or 'RP'. SP filtered to is_sp=1 appearances; RP to is_sp=0."""
    is_sp = (role == 'SP')
    fname_role = 'sps' if is_sp else 'rps'
    print(f'[slump] pitcher mode: {role}, ≥{min_2026_apps} 2026 appearances')
    if is_sp:
        proj = PROJECTIONS.rp3()
        proj = proj[proj['gs_to'] >= min_2026_apps]
        id_col, name_col = 'pitcher', 'player_name'
    else:
        # RP universe: rolling_relievers with names from pitcher_counting
        import json
        rp_roll = pd.read_csv(CACHE / 'rolling_relievers_2018_2026.csv')
        rp_roll = rp_roll[rp_roll['year'] == 2026].sort_values('split_day').drop_duplicates('pitcher', keep='last')
        rp_roll = rp_roll[rp_roll['g_to'] >= min_2026_apps]
        with open(CACHE / 'pitcher_counting_stats_2026.json') as f:
            pcs = pd.DataFrame(json.load(f))[['pitcher', 'name']]
        proj = rp_roll.merge(pcs, on='pitcher', how='left')
        id_col, name_col = 'pitcher', 'name'

    rows = []
    for i, r in enumerate(proj.itertuples(), 1):
        pid = int(getattr(r, id_col))
        name = getattr(r, name_col, None)
        history = pitcher_per_appearance(pid)
        if history.empty:
            continue
        history = history[history['is_sp'] == (1 if is_sp else 0)]
        if history.empty:
            continue
        s = slump_precedent(history, metric_col='fp', denom_col='outs', next_n=300,
                            min_cur_n=min_2026_apps)
        # Use outs as denom (more granular than appearance count). next_n=300 outs ≈ 100 IP.
        if not s:
            continue
        s['pitcher'] = pid
        s['player_name'] = name
        rows.append(s)
        if i % 30 == 0:
            print(f'  ...{i}/{len(proj)} processed')
    df = pd.DataFrame(rows)
    if df.empty:
        print('  no rows')
        return df
    df = df[['pitcher', 'player_name', 'cur_n', 'cur_rate',
             'pct_rank', 'n_comparable', 'n_bounce_eval', 'bounce_pct',
             'median_next_rate', 'median_delta', 'unprecedented']]
    out = OUT / f'slump_precedent_{fname_role}_2026.csv'
    df.to_csv(out, index=False)
    print(f'  wrote {out} ({len(df)} rows)')
    return df


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    args = set(sys.argv[1:]) or {'hitters', 'sps', 'rps'}
    if 'hitters' in args:
        run_hitters()
    if 'sps' in args:
        run_pitchers('SP')
    if 'rps' in args:
        run_pitchers('RP')


if __name__ == '__main__':
    main()

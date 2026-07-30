"""bench_tracker.py — tracks 'coulda started' — bench scoring vs starters.

Each week:
  - Pull each Ligers player's actual fp earned that week
  - Snapshot the active/bench lineup as set
  - Compute: for each bench player, did they out-score a starter at their
    eligible slot? Sum the "coulda gained" FP.

Cumulative metric: how many FP/week am I leaving on the bench?
Higher = worse lineup-setting habit. Calibrates whether the daily slot-fill
decisions match what actually happened.

Snapshots are saved to data/research/bench_snapshots/{week}.json. Run
this weekly after the matchup completes.

Output:
  data/outputs/bench_tracker.json (cumulative summary)
"""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
import json
import sys
import pandas as pd

from plv_clone.projections import PROJECTIONS
from plv_clone.paths import ROOT
from plv_clone.fantasy.scoring import pitcher_fp
from plv_clone.league_config import MY_TEAM_NAME
sys.path.insert(0, str(ROOT))
from scripts.xfp.lib.bucket_dispatch import _flip_lastfirst  # noqa: E402  shared 'Last, First' flip (audit item 9)
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'
SNAPS = ROOT / 'data' / 'research' / 'bench_snapshots'

PA_EVENTS = {'single', 'double', 'triple', 'home_run', 'walk', 'intent_walk',
             'hit_by_pitch', 'strikeout', 'strikeout_double_play',
             'field_out', 'force_out', 'grounded_into_double_play',
             'sac_fly', 'sac_bunt', 'fielders_choice', 'fielders_choice_out',
             'double_play', 'triple_play', 'field_error', 'catcher_interf'}


def player_fp_in_window(pid: int, is_pitcher: bool, year: int,
                          start: pd.Timestamp, end: pd.Timestamp) -> float:
    """Compute fp earned by a player in [start, end]. Uses core_fp formula."""
    path = CACHE / f'statcast_{year}.parquet'
    if not path.exists():
        return 0.0
    if is_pitcher:
        df = pd.read_parquet(path, columns=['game_date', 'pitcher', 'events',
                                              'bat_score', 'post_bat_score'])
        df['game_date'] = pd.to_datetime(df['game_date'])
        df = df[(df['pitcher'] == pid) & (df['game_date'] >= start)
                & (df['game_date'] <= end)]
        pa = df[df['events'].isin(PA_EVENTS)].copy()
        if pa.empty: return 0.0
        pa['k'] = pa['events'].isin({'strikeout', 'strikeout_double_play'}).astype(int)
        pa['bb'] = pa['events'].isin({'walk', 'intent_walk'}).astype(int)
        pa['hbp'] = (pa['events'] == 'hit_by_pitch').astype(int)
        pa['h'] = pa['events'].isin({'single', 'double', 'triple', 'home_run'}).astype(int)
        pa['runs'] = (pa['post_bat_score'] - pa['bat_score']).fillna(0).clip(lower=0)
        pa['outs'] = (~pa['events'].isin({'single','double','triple','home_run','walk',
                                            'intent_walk','hit_by_pitch','field_error','catcher_interf'})).astype(int)
        ip = pa['outs'].sum() / 3.0
        return float(pitcher_fp(
            k=pa['k'].sum(), ip=ip, h=pa['h'].sum(),
            er=pa['runs'].sum(), bb=pa['bb'].sum(), hbp=pa['hbp'].sum(),
        ))
    else:
        df = pd.read_parquet(path, columns=['game_date', 'batter', 'events'])
        df['game_date'] = pd.to_datetime(df['game_date'])
        df = df[(df['batter'] == pid) & (df['game_date'] >= start)
                & (df['game_date'] <= end) & df['events'].isin(PA_EVENTS)]
        if df.empty: return 0.0
        tb = df['events'].map({'single':1,'double':2,'triple':3,'home_run':4}).fillna(0).sum()
        bb = df['events'].isin({'walk','intent_walk'}).sum()
        hbp = (df['events'] == 'hit_by_pitch').sum()
        k = df['events'].isin({'strikeout','strikeout_double_play'}).sum()
        hr = (df['events'] == 'home_run').sum()  # R proxy
        return float(tb + hr + bb + hbp - k)


def main():
    SNAPS.mkdir(parents=True, exist_ok=True)
    from plv_clone.league_state import LeagueState
    league = LeagueState()._get_league()
    my_team = next(t for t in league.teams if t.team_name == MY_TEAM_NAME)

    # For each player on roster, compute fp earned last week
    week_end = pd.Timestamp(date.today())
    week_start = week_end - timedelta(days=6)

    rows = []
    for p in my_team.roster:
        is_pit = bool(set(getattr(p, 'eligibleSlots', None) or []) & {'SP', 'RP', 'P'})
        # ESPN's playerId is NOT the MLB ID. Look up via rh3/rp3 player_name match.
        fp = 0.0
        try:
            # Best-effort: pull mlb_id from name lookup. Use a collision-safe full
            # normalized name (handles 'Last, First' + accents) — NEVER a surname
            # substring, which grabs the wrong same-name player (Will vs Austin
            # Warren, the Garcias). (collision fix 2026-06-26)
            # OWNER: name_match.safe_name_key — it already flips "Last, First",
            # strips accents, and collapses apostrophes/periods/hyphens. The local
            # copy this replaced missed curly-vs-straight apostrophes.
            from plv_clone.utils.name_match import safe_name_key as _nm

            tgt = _nm(p.name)
            if is_pit:
                rp = PROJECTIONS.rp3()
                m = rp[rp['player_name'].fillna('').apply(_nm) == tgt]
                if not m.empty:
                    mlb_id = int(m.iloc[0]['pitcher'])
                    fp = player_fp_in_window(mlb_id, True, 2026, week_start, week_end)
            else:
                rh = PROJECTIONS.rh3()
                m = rh[rh['player_name'].fillna('').apply(_nm) == tgt]
                if not m.empty:
                    mlb_id = int(m.iloc[0]['batter'])
                    fp = player_fp_in_window(mlb_id, False, 2026, week_start, week_end)
        except Exception:
            pass
        rows.append({
            'name': p.name, 'is_pit': is_pit,
            'lineup_slot': getattr(p, 'lineupSlot', '?'),
            'fp_this_week': round(fp, 1),
        })

    df = pd.DataFrame(rows)
    df = df.sort_values('fp_this_week', ascending=False)

    # Distinguish started (any non-BE/IL slot) vs benched (BE)
    df['started'] = ~df['lineup_slot'].isin(['BE', 'IL', '?'])
    started = df[df['started']]
    bench = df[~df['started'] & (df['lineup_slot'] != 'IL')]

    # "Coulda started": any bench player whose fp_this_week > the minimum starter at their eligible slot
    coulda = bench[bench['fp_this_week'] > started['fp_this_week'].min()]
    total_left_on_bench = coulda['fp_this_week'].sum()

    print(f'\n=== Week ending {week_end.date()} bench analysis ===')
    print(f'Starters total FP: {started["fp_this_week"].sum():.1f}')
    print(f'Active bench total FP: {bench["fp_this_week"].sum():.1f}')
    print(f'Bench players who out-scored at least one starter: {len(coulda)}')
    print(f'Suggested left-on-bench: {total_left_on_bench:.1f} FP')

    # Save snapshot
    snap_path = SNAPS / f'{week_start.date()}.json'
    snap = {
        'week_start': str(week_start.date()),
        'week_end': str(week_end.date()),
        'starters': started.to_dict(orient='records'),
        'bench': bench.to_dict(orient='records'),
        'left_on_bench': total_left_on_bench,
    }
    with open(snap_path, 'w', encoding='utf-8') as f:
        json.dump(snap, f, separators=(',', ':'), default=str)
    print(f'\nwrote snapshot {snap_path}')

    # Cumulative
    snaps = sorted(SNAPS.glob('*.json'))
    cumulative = []
    for sp in snaps:
        d = json.loads(sp.read_text(encoding='utf-8'))
        cumulative.append({'week': d['week_start'],
                            'left_on_bench': d.get('left_on_bench', 0)})
    payload = {'snapshots': cumulative,
                'cumulative_left_on_bench': sum(c['left_on_bench'] for c in cumulative),
                'this_week_detail': df.to_dict(orient='records')}
    with open(OUT / 'bench_tracker.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, separators=(',', ':'), default=str)


if __name__ == '__main__':
    main()

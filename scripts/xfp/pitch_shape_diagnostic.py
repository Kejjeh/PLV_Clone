"""pitch_shape_diagnostic.py — per-pitch-type velocity/movement vs career.

For each target pitcher, breaks down 2026 stuff by pitch type and compares
to their career baseline. Flags material declines that the rp3 model
(which uses blended cumulative velo) can't see — the kind of stuff-shape
read PL writes about ("Strider's slider down to 85 mph", "Sheehan's
velocity dropping in-game").

Usage:
  python scripts/xfp/pitch_shape_diagnostic.py "Spencer Strider" "Emmet Sheehan"
"""
from __future__ import annotations
import sys
import unicodedata
import re
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'

# Career baseline = last 3 full prior seasons (2023-2025)
CAREER_YEARS = [2023, 2024, 2025]
CURRENT_YEAR = 2026

PITCH_LABELS = {
    'FF': '4-seam', 'SI': 'sinker', 'FC': 'cutter', 'FT': '2-seam',
    'FA': 'fastball', 'SL': 'slider', 'ST': 'sweeper', 'SV': 'slurve',
    'CU': 'curve', 'KC': 'knuckle-curve', 'CS': 'slow curve',
    'CH': 'changeup', 'FS': 'splitter', 'SC': 'screwball',
    'EP': 'eephus', 'KN': 'knuckleball',
}


def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    parts = re.findall(r'[a-z]+', s)
    return ''.join(sorted(parts))


def load_pitcher_data(pid: int, years: list[int]) -> pd.DataFrame:
    frames = []
    for y in years:
        path = CACHE / f'statcast_{y}.parquet'
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=['pitcher', 'pitch_type', 'release_speed',
                                              'pfx_x', 'pfx_z', 'release_extension',
                                              'release_spin_rate'])
        sub = df[df['pitcher'] == pid].copy()
        if not sub.empty:
            sub['year'] = y
            frames.append(sub)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def aggregate_by_pitch_type(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return pd.DataFrame()
    grp = df.groupby('pitch_type').agg(
        n_pitches=('release_speed', 'size'),
        velo=('release_speed', 'mean'),
        ivb=('pfx_z', 'mean'),     # inches of induced vertical break (Statcast in feet-ish? actually feet)
        hb=('pfx_x', 'mean'),
        ext=('release_extension', 'mean'),
        spin=('release_spin_rate', 'mean'),
    )
    grp['ivb_in'] = grp['ivb'] * 12  # convert ft → inches (Statcast pfx_z is in feet)
    grp['hb_in'] = grp['hb'] * 12
    return grp


def lookup_pitcher_id(name: str) -> int | None:
    """Find pitcher MLBAM id via statcast files (search for matching player_name)."""
    nk = _norm(name)
    # The statcast cache doesn't have player_name for pitcher — we need an external lookup.
    # Use sp_multiyr or relievers_multiyr which has both pitcher id and player_name.
    sp = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv', usecols=['pitcher', 'player_name'])
    rp = pd.read_csv(CACHE / 'relievers_multiyr_2018_2026.csv', usecols=['pitcher', 'name'])
    rp = rp.rename(columns={'name': 'player_name'})
    pool = pd.concat([sp, rp]).drop_duplicates('pitcher')
    pool['nk'] = pool['player_name'].map(_norm)
    m = pool[pool['nk'] == nk]
    if m.empty:
        return None
    return int(m.iloc[0]['pitcher'])


def report(name: str):
    pid = lookup_pitcher_id(name)
    if pid is None:
        print(f'  {name}: pitcher ID not found in substrate')
        return
    df = load_pitcher_data(pid, CAREER_YEARS + [CURRENT_YEAR])
    if df.empty:
        print(f'  {name}: no statcast rows')
        return

    career = aggregate_by_pitch_type(df[df['year'].isin(CAREER_YEARS)])
    current = aggregate_by_pitch_type(df[df['year'] == CURRENT_YEAR])

    print(f'\n{"="*80}')
    print(f'  {name} (id {pid}) — pitch-shape: 2026 vs {CAREER_YEARS[0]}-{CAREER_YEARS[-1]} baseline')
    print(f'{"="*80}')
    print(f'\n  {"PITCH":<12s} {"USAGE%":>7s} {"VELO":>11s} {"iVB(in)":>11s} {"HB(in)":>11s} {"EXT(ft)":>11s} {"flags"}')
    total_current = current['n_pitches'].sum() if not current.empty else 0
    if total_current == 0:
        print(f'  No 2026 pitches yet')
        return

    for pitch in current.index:
        c_row = current.loc[pitch]
        usage = c_row['n_pitches'] / total_current * 100
        car = career.loc[pitch] if pitch in career.index else None
        flags = []

        def cmp(curr, base, name_, threshold, lower_is_warning=False):
            if pd.isna(curr) or pd.isna(base): return ''
            delta = curr - base
            sig = ''
            if abs(delta) >= threshold:
                if (lower_is_warning and delta < -threshold) or (not lower_is_warning and abs(delta) >= threshold):
                    sig = f'{name_}{delta:+.2f}'
            return sig

        velo_s = f'{c_row["velo"]:.1f}'
        ivb_s = f'{c_row["ivb_in"]:.1f}'
        hb_s = f'{c_row["hb_in"]:.1f}'
        ext_s = f'{c_row["ext"]:.2f}' if pd.notna(c_row["ext"]) else '?'
        if car is not None:
            velo_d = c_row['velo'] - car['velo']
            ivb_d = c_row['ivb_in'] - car['ivb_in']
            hb_d = c_row['hb_in'] - car['hb_in']
            ext_d = (c_row['ext'] - car['ext']) if pd.notna(c_row['ext']) and pd.notna(car['ext']) else 0
            velo_s = f'{c_row["velo"]:.1f}({velo_d:+.2f})'
            ivb_s = f'{c_row["ivb_in"]:.1f}({ivb_d:+.2f})'
            hb_s = f'{c_row["hb_in"]:.1f}({hb_d:+.2f})'
            ext_s = f'{c_row["ext"]:.2f}({ext_d:+.2f})' if pd.notna(c_row["ext"]) and pd.notna(car["ext"]) else '?'
            if abs(velo_d) >= 1.0:
                flags.append(f'VELO{velo_d:+.1f}')
            if abs(ivb_d) >= 1.5:
                flags.append(f'iVB{ivb_d:+.1f}')
            if abs(hb_d) >= 1.5:
                flags.append(f'HB{hb_d:+.1f}')
            if abs(ext_d) >= 0.15:
                flags.append(f'EXT{ext_d:+.2f}')

        label = PITCH_LABELS.get(pitch, pitch)
        print(f'  {label:<12s} {usage:>6.1f}% {velo_s:>11s} {ivb_s:>11s} {hb_s:>11s} '
              f'{ext_s:>11s} {", ".join(flags)}')


def main():
    targets = sys.argv[1:] if len(sys.argv) > 1 else [
        'Spencer Strider', 'Emmet Sheehan', 'Carlos Rodon', 'Kyle Bradish',
        'Hunter Greene', 'Tyler Glasnow', 'Eury Perez', 'Sonny Gray',
        'Framber Valdez',
    ]
    for name in targets:
        report(name)


if __name__ == '__main__':
    main()

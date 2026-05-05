"""Pull 2015-2020 Statcast in monthly chunks."""
from __future__ import annotations
import time, warnings
from pathlib import Path
import pandas as pd
warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
CACHE.mkdir(parents=True, exist_ok=True)

YEARS = [2015, 2016, 2017, 2018, 2019, 2020]

# 2020 was 60-game season Jul-Sep
SEASON_DATES = {
    2015: [('04-05','05-31'),('06-01','07-31'),('08-01','09-30'),('10-01','10-15')],
    2016: [('04-03','05-31'),('06-01','07-31'),('08-01','09-30'),('10-01','10-15')],
    2017: [('04-02','05-31'),('06-01','07-31'),('08-01','09-30'),('10-01','10-15')],
    2018: [('03-29','05-31'),('06-01','07-31'),('08-01','09-30'),('10-01','10-15')],
    2019: [('03-20','05-31'),('06-01','07-31'),('08-01','09-30'),('10-01','10-15')],
    2020: [('07-23','08-31'),('09-01','09-30')],
}

def pull_year(year):
    cache_path = CACHE / f'statcast_{year}.parquet'
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        print(f'[{year}] cached: {len(df):,} pitches', flush=True)
        return df
    import pybaseball as pb
    pb.cache.enable()
    frames = []
    for start_m, end_m in SEASON_DATES[year]:
        try:
            t0 = time.time()
            chunk = pb.statcast(f'{year}-{start_m}', f'{year}-{end_m}', verbose=False)
            if chunk is not None and len(chunk) > 0:
                chunk = chunk[chunk['game_type'] == 'R'].copy()
                frames.append(chunk)
                print(f'  {year}-{start_m}: {len(chunk):,} pitches in {time.time()-t0:.0f}s', flush=True)
        except Exception as e:
            print(f'  {year}-{start_m}: FAILED {e}', flush=True)
    if not frames:
        print(f'[{year}] NO DATA', flush=True)
        return None
    df = pd.concat(frames, ignore_index=True)
    df.to_parquet(cache_path, index=False)
    print(f'[{year}] total {len(df):,} pitches saved', flush=True)
    return df

if __name__ == '__main__':
    for yr in YEARS:
        try:
            pull_year(yr)
        except Exception as e:
            print(f'[{yr}] outer-fail: {e}', flush=True)
    print('=== ALL YEARS DONE ===', flush=True)

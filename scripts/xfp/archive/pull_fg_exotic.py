"""
pull_fg_exotic.py - Try multiple exotic methods to pull FanGraphs Stuff+/Pitching+ history.

Methods attempted (in order, bail on first success per year):
  1. cloudscraper + JSON API
  2. cloudscraper + HTML leaderboard + pandas.read_html (Google-Sheets-IMPORTHTML style)
  3. curl_cffi with multiple impersonation profiles
  4. Plain requests to FG legacy leaders.aspx with &csv=1 export
  5. As fallback, save raw HTML for manual inspection

Output: data/outputs/fangraphs_pitchers_{year}.csv with same column schema as fetch_fangraphs.py.
"""
from __future__ import annotations
import sys, time, json, re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / 'data' / 'outputs'

YEARS = [2020, 2021, 2022, 2023, 2024, 2025]

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')

# Column map for FG leaderboard rows (post-2014 advanced+stuff)
PITCHER_COLS = {
    'xMLBAMID':'mlb_id','Name':'player_name_fg','Team':'team','Season':'season',
    'IP':'ip','G':'g','GS':'gs','ERA':'era','FIP':'fip','xFIP':'xfip','SIERA':'siera',
    'xERA':'xera','WHIP':'whip','K%':'k_pct','BB%':'bb_pct','K-BB%':'k_minus_bb_pct',
    'SwStr%':'swstr_pct','CSW%':'csw_pct','C+SwStr%':'c_plus_swstr_pct','HR/FB':'hr_fb',
    'GB%':'gb_pct','LOB%':'lob_pct','Barrel%':'barrel_pct','HardHit%':'hard_hit_pct',
    'EV':'avg_ev','sp_stuff':'stuff_plus','sp_location':'location_plus',
    'sp_pitching':'pitching_plus','pb_stuff':'pb_stuff','pb_command':'pb_command',
    'pb_xRV100':'pb_xrv100',
}

def clean_name(raw):
    if not isinstance(raw, str): return str(raw)
    return re.sub(r'<[^>]+>', '', raw).strip()


# ===============================================================
# METHOD 1: cloudscraper + JSON API
# ===============================================================
def method_1_cloudscraper_api(year: int):
    import cloudscraper
    scraper = cloudscraper.create_scraper(browser={'browser':'chrome','platform':'windows'})
    url = 'https://www.fangraphs.com/api/leaders/major-league/data'
    params = {'pos':'all','stats':'pit','lg':'all','qual':'10','season':year,'season1':year,
              'month':0,'team':0,'pageitems':500,'pagenum':1,'ind':0,'type':8}
    try:
        r = scraper.get(url, params=params, timeout=30)
        if r.status_code != 200:
            return None, f'HTTP {r.status_code}'
        data = r.json()
        rows = data.get('data', [])
        if not rows: return None, 'no data rows'
        return _extract(rows), None
    except Exception as e:
        return None, str(e)


# ===============================================================
# METHOD 2: cloudscraper + HTML leaderboard + pandas.read_html
# ===============================================================
def method_2_cloudscraper_html(year: int):
    import cloudscraper
    scraper = cloudscraper.create_scraper(browser={'browser':'chrome','platform':'windows'})
    # Modern FG leaderboards URL
    url = f'https://www.fangraphs.com/leaders/major-league?pos=all&stats=pit&lg=all&qual=10&type=8&season={year}&season1={year}&ind=0&pagenum=1&pageitems=500'
    try:
        r = scraper.get(url, timeout=30)
        if r.status_code != 200:
            return None, f'HTTP {r.status_code}'
        # pandas.read_html on the HTML
        tables = pd.read_html(r.text)
        if not tables: return None, 'no tables found'
        # Heuristic: pick the largest table (the leaderboard)
        candidate = max(tables, key=lambda t: len(t))
        # Filter to expected columns
        renamed = candidate.rename(columns={k:v for k,v in PITCHER_COLS.items() if k in candidate.columns})
        out_cols = [v for v in PITCHER_COLS.values() if v in renamed.columns]
        if 'mlb_id' not in renamed.columns:
            return None, f'mlb_id missing; tables found: {len(tables)}, biggest: {candidate.shape}'
        return renamed[out_cols].copy(), None
    except Exception as e:
        return None, str(e)


# ===============================================================
# METHOD 3: curl_cffi with multiple impersonation profiles
# ===============================================================
def method_3_curlcffi(year: int):
    try:
        from curl_cffi import requests as cfr
    except ImportError:
        return None, 'curl_cffi not installed'
    url = 'https://www.fangraphs.com/api/leaders/major-league/data'
    params = {'pos':'all','stats':'pit','lg':'all','qual':'10','season':year,'season1':year,
              'month':0,'team':0,'pageitems':500,'pagenum':1,'ind':0,'type':8}
    profiles = ['chrome120','chrome124','chrome131','safari17_0','firefox133']
    for prof in profiles:
        try:
            r = cfr.get(url, params=params, impersonate=prof, timeout=30,
                         headers={'User-Agent':UA,'Accept':'application/json',
                                   'Origin':'https://www.fangraphs.com',
                                   'Referer':'https://www.fangraphs.com/leaders/major-league?'})
            if r.status_code == 200:
                rows = r.json().get('data', [])
                if rows:
                    return _extract(rows), None
        except Exception as e:
            continue
    return None, 'all curl_cffi profiles failed'


# ===============================================================
# METHOD 4: legacy leaders.aspx with CSV download
# ===============================================================
def method_4_legacy_csv(year: int):
    import cloudscraper
    scraper = cloudscraper.create_scraper(browser={'browser':'chrome','platform':'windows'})
    # Legacy URL with CSV export
    url = f'https://www.fangraphs.com/leaders.aspx?pos=all&stats=pit&lg=all&qual=10&type=8&season={year}&month=0&season1={year}&ind=0&team=0&rost=0&age=0&filter=&players=0&page=1_500'
    try:
        r = scraper.get(url, timeout=30)
        if r.status_code != 200:
            return None, f'HTTP {r.status_code} (legacy URL)'
        tables = pd.read_html(r.text)
        if not tables: return None, 'no tables'
        candidate = max(tables, key=lambda t: len(t))
        renamed = candidate.rename(columns={k:v for k,v in PITCHER_COLS.items() if k in candidate.columns})
        out_cols = [v for v in PITCHER_COLS.values() if v in renamed.columns]
        if 'mlb_id' not in renamed.columns:
            return None, f'no mlb_id; biggest table: {candidate.shape}, cols: {list(candidate.columns)[:10]}'
        return renamed[out_cols].copy(), None
    except Exception as e:
        return None, f'{type(e).__name__}: {e}'


def _extract(rows):
    """Convert FG JSON rows to DataFrame with normalized column names."""
    records = []
    for row in rows:
        rec = {}
        for src, dst in PITCHER_COLS.items():
            v = row.get(src)
            if isinstance(v, str) and '<' in v:
                v = clean_name(v)
            rec[dst] = v
        records.append(rec)
    df = pd.DataFrame(records)
    if 'mlb_id' in df.columns:
        df['mlb_id'] = pd.to_numeric(df['mlb_id'], errors='coerce').astype('Int64')
    pct_cols = [c for c in df.columns if c.endswith('_pct')]
    for c in pct_cols:
        df[c] = pd.to_numeric(df[c], errors='coerce')
        if df[c].dropna().between(0, 1).all():
            df[c] = (df[c] * 100).round(2)
    return df


def pull_year(year: int):
    out_path = OUTPUTS / f'fangraphs_pitchers_{year}.csv'
    if out_path.exists():
        existing = pd.read_csv(out_path)
        if len(existing) > 100 and 'stuff_plus' in existing.columns and existing['stuff_plus'].notna().sum() > 50:
            print(f'[{year}] already has {len(existing)} rows + stuff_plus; skipping')
            return True

    methods = [
        ('cloudscraper-api', method_1_cloudscraper_api),
        ('cloudscraper-html', method_2_cloudscraper_html),
        ('curl_cffi-multi', method_3_curlcffi),
        ('legacy-csv', method_4_legacy_csv),
    ]
    for name, fn in methods:
        df, err = fn(year)
        if df is not None and len(df) > 50:
            stuff_pres = df['stuff_plus'].notna().sum() if 'stuff_plus' in df.columns else 0
            df.to_csv(out_path, index=False)
            print(f'[{year}] SUCCESS via {name}: {len(df)} rows, stuff_plus={stuff_pres} populated -> {out_path.name}')
            return True
        else:
            print(f'[{year}] {name}: {err}')
        time.sleep(1.5)
    print(f'[{year}] ALL METHODS FAILED')
    return False


if __name__ == '__main__':
    successes = 0
    for yr in YEARS:
        ok = pull_year(yr)
        if ok: successes += 1
        time.sleep(2.0)
    print(f'\n=== {successes}/{len(YEARS)} years pulled ===')

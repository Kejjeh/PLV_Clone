"""
pull_fg_rp_leverage.py — FanGraphs RP leverage scraper.

Mirrors pull_fg_undetected.py pattern (visible undetected-chromedriver session,
Cloudflare warm-up via leaderboard page navigation, then JSON-API call inside
the browser context to inherit CF cookies).

Difference vs the pitcher scraper:
  - stats=rel (relief leaderboard)
  - qual=15 (15 IP minimum — captures nearly all RP qualifiers)
  - Different column set focused on leverage / inherited runners

Output: data/research/xfp_cache/fangraphs_rp_leverage_2018_2026.csv
"""
from __future__ import annotations
import sys, time, re, json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / 'data' / 'research' / 'xfp_cache'
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / 'fangraphs_rp_leverage_2018_2026.csv'

# 2017-2026 minus 2020 (COVID-short, excluded from RP archetype panel)
YEARS = [2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]

# FG relief-leaderboard column mapping.
# Source columns picked from the FG `stats=rel&type=8` leaderboard schema.
# Identity + usage + leverage + inherited-runner + outcome-rate display.
RP_COLS = {
    # Identity
    'xMLBAMID':  'mlb_id',
    'Name':      'player_name_fg',
    'Team':      'team',
    'Season':    'season',
    'Age':       'age',
    # Usage
    'G':         'g',
    'GS':        'gs',
    'IP':        'ip',
    'SV':        'sv',
    'HLD':       'hld',
    'SD':        'shutdowns',
    'MD':        'meltdowns',
    # Leverage (the prize)
    'pLI':       'pli',
    'gmLI':      'gmli',
    'exLI':      'exli',
    'inLI':      'inli',
    'WPA':       'wpa',
    'WPA/LI':    'wpa_per_li',
    'RE24':      're24',
    'REW':       'rew',
    # Inherited runners
    'IR':        'inherited_runners',
    'IR-S%':     'inherited_stranded_pct',   # FG newer key
    'IS%':       'inherited_stranded_pct',   # FG older key (same data, different name)
    # Outcome rates (sanity)
    'ERA':       'era',
    'FIP':       'fip',
    'K%':        'k_pct',
    'BB%':       'bb_pct',
    'Barrel%':   'barrel_pct',
    'HardHit%':  'hard_hit_pct',
    'LOB%':      'lob_pct',
}


def clean_name(raw):
    if not isinstance(raw, str): return str(raw)
    return re.sub(r'<[^>]+>', '', raw).strip()


def parse_pct(v):
    """Parse '82.3%' or 0.823 or 82.3 → 82.3 (a percentage 0-100 scale)."""
    if v is None: return None
    if isinstance(v, str):
        v = v.replace('%', '').strip()
        if v == '' or v == '-': return None
        try:
            v = float(v)
        except ValueError:
            return None
    if isinstance(v, (int, float)):
        # If FG returns 0-1 range, scale to 0-100
        if 0 <= v <= 1:
            return round(v * 100, 2)
        return round(float(v), 2)
    return None


def fetch_year(driver, year: int):
    """Fetch year via JSON API call inside browser session (Cloudflare cookies set)."""
    api_url = (f'https://www.fangraphs.com/api/leaders/major-league/data?'
               f'pos=all&stats=rel&lg=all&qual=15&season={year}&season1={year}'
               f'&month=0&team=0&pageitems=500&pagenum=1&ind=0&type=8')

    # Warm up via leaderboard page so CF cookies set
    leaderboard_url = (f'https://www.fangraphs.com/leaders/major-league?'
                       f'stats=rel&season={year}&type=8')
    print(f'  [{year}] navigating to leaderboard page (warming session)...', flush=True)
    driver.get(leaderboard_url)
    time.sleep(8)  # let CF challenge complete + page render

    # Trigger fetch in browser context
    print(f'  [{year}] fetching API via browser fetch()...', flush=True)
    js = f'''
    return await new Promise((resolve) => {{
        fetch("{api_url}", {{credentials: "include"}})
            .then(r => r.text().then(t => resolve({{status: r.status, body: t}})))
            .catch(e => resolve({{status: 0, body: String(e)}}));
    }});
    '''
    response = driver.execute_script(js)
    status = response.get('status')
    if status != 200:
        return None, f'HTTP {status}; body[:200]={response.get("body", "")[:200]}'

    try:
        data = json.loads(response['body'])
    except Exception as e:
        return None, f'JSON parse failed: {e}'

    rows = data.get('data', [])
    if not rows:
        return None, 'no data rows'

    # Diagnostic: print available keys from first row so we can confirm column
    # names match what RP_COLS expects.
    sample_keys = set(rows[0].keys()) if rows else set()
    expected_present = sum(1 for k in RP_COLS if k in sample_keys)
    print(f'  [{year}] {len(rows)} rows, {expected_present}/{len(RP_COLS)} '
          f'expected RP_COLS present in payload', flush=True)
    missing_critical = [k for k in ('gmLI', 'pLI', 'IR', 'WPA') if k not in sample_keys]
    if missing_critical:
        print(f'  [{year}] WARN: missing critical leverage cols: {missing_critical}', flush=True)
        # Sample 30 keys to help debug naming differences
        sample = sorted(list(sample_keys))[:50]
        print(f'  [{year}] sample of {len(sample_keys)} available keys: {sample[:40]}', flush=True)

    records = []
    for row in rows:
        rec = {}
        for src, dst in RP_COLS.items():
            if src not in row:
                continue
            v = row.get(src)
            if isinstance(v, str) and '<' in v:
                v = clean_name(v)
            # Percentage-like columns
            if dst in ('inherited_stranded_pct', 'k_pct', 'bb_pct',
                       'barrel_pct', 'hard_hit_pct', 'lob_pct'):
                rec[dst] = parse_pct(v)
            else:
                rec[dst] = v
        records.append(rec)

    df = pd.DataFrame(records)
    if 'mlb_id' in df.columns:
        df['mlb_id'] = pd.to_numeric(df['mlb_id'], errors='coerce').astype('Int64')

    # Numeric coercion on leverage / counting cols
    for c in ('pli', 'gmli', 'exli', 'inli', 'wpa', 'wpa_per_li', 're24', 'rew',
              'ip', 'g', 'gs', 'sv', 'hld', 'shutdowns', 'meltdowns',
              'inherited_runners', 'era', 'fip', 'age'):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')

    return df, None


# Re-pull cadence for the CURRENT season. The cached-skip below only asked
# "are all YEARS present?", which is permanently true once the in-progress
# season has ANY rows -- so the current year froze at whatever date it was
# first pulled and never refreshed. Found 2026-08-18: both this cache and the
# BRef IR cache sat at 2026-05-30 (80.6 days) while the daily refresh reported
# them as [FAIL] degraded, matching only 76.7% of the live reliever pool.
CURRENT_SEASON_MAX_AGE_DAYS = 7


def _current_season_stale(path, years) -> bool:
    """True if `years` includes the in-progress season and `path` is older than
    CURRENT_SEASON_MAX_AGE_DAYS. Completed seasons never go stale."""
    import datetime as _dt
    this_year = _dt.date.today().year
    if this_year not in years:
        return False
    age_days = (_dt.datetime.now()
                - _dt.datetime.fromtimestamp(path.stat().st_mtime)).days
    return age_days > CURRENT_SEASON_MAX_AGE_DAYS


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true',
                    help='re-pull even if the cache looks complete')
    args, _ = ap.parse_known_args()
    import undetected_chromedriver as uc

    # Already-cached merged output → skip if reasonable.
    if OUT_PATH.exists() and not args.force:
        try:
            ex = pd.read_csv(OUT_PATH)
            cached_years = set(int(y) for y in ex['season'].dropna().unique())
            if (all(y in cached_years for y in YEARS) and 'gmli' in ex.columns \
                    and ex['gmli'].notna().sum() > 500
                    and not _current_season_stale(OUT_PATH, YEARS)):
                print(f'Cached {OUT_PATH.name} has all years + gmli populated — skip.', flush=True)
                return
        except Exception:
            pass

    print('Launching undetected Chrome (visible, not headless)...', flush=True)
    options = uc.ChromeOptions()
    # Run NOT headless — Cloudflare detects headless mode
    options.add_argument('--disable-blink-features=AutomationControlled')
    driver = uc.Chrome(options=options, version_main=147)  # match installed Chrome 147

    all_frames = []
    successes = 0
    try:
        for yr in YEARS:
            per_year_path = OUT_DIR / f'fangraphs_rp_leverage_{yr}.csv'
            if per_year_path.exists():
                try:
                    cached = pd.read_csv(per_year_path)
                    if len(cached) > 50 and 'gmli' in cached.columns \
                            and cached['gmli'].notna().sum() > 30:
                        print(f'[{yr}] per-year cached -> using ({len(cached)} rows)')
                        all_frames.append(cached)
                        successes += 1
                        continue
                except Exception:
                    pass

            try:
                df, err = fetch_year(driver, yr)
                if df is not None and len(df) > 30:
                    gmli_n = df['gmli'].notna().sum() if 'gmli' in df.columns else 0
                    df.to_csv(per_year_path, index=False)
                    all_frames.append(df)
                    print(f'[{yr}] SUCCESS: {len(df)} rows, gmli={gmli_n} populated')
                    successes += 1
                else:
                    print(f'[{yr}] FAILED: {err}')
            except Exception as e:
                print(f'[{yr}] EXCEPTION: {e}')
            time.sleep(3)
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    if all_frames:
        merged = pd.concat(all_frames, ignore_index=True)
        merged.to_csv(OUT_PATH, index=False)
        print(f'\nMerged {len(merged)} rows -> {OUT_PATH}')
    print(f'\n=== {successes}/{len(YEARS)} years pulled ===', flush=True)


if __name__ == '__main__':
    main()

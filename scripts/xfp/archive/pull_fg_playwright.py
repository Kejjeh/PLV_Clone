"""
pull_fg_playwright.py - Use playwright headless Chromium to fetch FG with full JS rendering.
This handles Cloudflare's challenge that blocks plain HTTP scrapers.
"""
from __future__ import annotations
import sys, time, re, asyncio
from pathlib import Path
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
OUTPUTS = ROOT / 'data' / 'outputs'

YEARS = [2020, 2021, 2022, 2023, 2024, 2025]

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


async def fetch_year_async(page, year: int):
    """Fetch one year's pitcher leaderboard by scraping rendered DOM (post-JS)."""
    # Use type=8 (advanced/standard) for the leaderboard page
    leaderboard_url = (f'https://www.fangraphs.com/leaders/major-league?'
                        f'pos=all&stats=pit&lg=all&qual=10&type=8&season={year}&season1={year}'
                        f'&ind=0&pagenum=1&pageitems=500')
    print(f'  [{year}] navigating to leaderboard page...', flush=True)
    try:
        await page.goto(leaderboard_url, wait_until='networkidle', timeout=90000)
    except Exception as e:
        print(f'  [{year}] navigation timeout, continuing: {e}', flush=True)
    # Wait for leaderboard table to render (rgMasterTable id is the FG leaderboard React table)
    try:
        await page.wait_for_selector('table.rgMasterTable, table.table-fixed, div.leaders-major__table table', timeout=15000)
    except Exception:
        pass
    await page.wait_for_timeout(3000)

    # Save HTML for parse + sanity
    html = await page.content()
    if 'Just a moment' in html or 'cf-' in html and 'challenge' in html.lower():
        return None, 'Cloudflare challenge in HTML'

    # Use pandas.read_html with all tables (Google-Sheets-IMPORTHTML style)
    try:
        tables = pd.read_html(html)
    except ValueError as e:
        return None, f'no tables: {e}'

    if not tables:
        return None, 'pandas found 0 tables'

    print(f'  [{year}] found {len(tables)} tables; sizes: {[t.shape for t in tables]}', flush=True)

    # The leaderboard is the largest table. Find it.
    candidate = max(tables, key=lambda t: len(t))
    print(f'  [{year}] biggest table: {candidate.shape}, cols sample: {list(candidate.columns)[:8]}', flush=True)

    # Look for FG-style columns; the leaderboard table on rendered page uses different names
    # than the JSON API. The HTML leaderboard usually shows: #, Name, Team, IP, K%, BB%, ...
    # Stuff+ / Location+ / Pitching+ are columns when type=8 + advanced is selected.
    # We may need to explicitly check column existence.
    # Save the raw table even without FG-style renaming for debug.
    debug_path = OUTPUTS / f'fangraphs_pitchers_{year}_raw.csv'
    candidate.to_csv(debug_path, index=False)
    print(f'  [{year}] raw table saved to {debug_path.name} for inspection', flush=True)

    # Try FG renaming
    renamed = candidate.rename(columns={k:v for k,v in PITCHER_COLS.items() if k in candidate.columns})
    matched_cols = [v for v in PITCHER_COLS.values() if v in renamed.columns]
    print(f'  [{year}] matched FG cols: {matched_cols}', flush=True)
    if 'stuff_plus' not in matched_cols:
        return None, f'no Stuff+ column found in rendered table'
    return renamed[matched_cols].copy(), None


async def main_async():
    from playwright.async_api import async_playwright
    successes = 0
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800},
        )
        page = await context.new_page()

        for yr in YEARS:
            out_path = OUTPUTS / f'fangraphs_pitchers_{yr}.csv'
            if out_path.exists():
                ex = pd.read_csv(out_path)
                if len(ex) > 100 and 'stuff_plus' in ex.columns and ex['stuff_plus'].notna().sum() > 50:
                    print(f'[{yr}] cached -> skipping')
                    continue

            try:
                df, err = await fetch_year_async(page, yr)
                if df is not None and len(df) > 50:
                    stuff_n = df['stuff_plus'].notna().sum() if 'stuff_plus' in df.columns else 0
                    df.to_csv(out_path, index=False)
                    print(f'[{yr}] SUCCESS: {len(df)} rows, stuff_plus={stuff_n} populated')
                    successes += 1
                else:
                    print(f'[{yr}] FAILED: {err}')
            except Exception as e:
                print(f'[{yr}] EXCEPTION: {e}')

            await page.wait_for_timeout(2000)  # be polite

        await browser.close()
    print(f'\n=== {successes}/{len(YEARS)} years pulled ===')


if __name__ == '__main__':
    asyncio.run(main_async())

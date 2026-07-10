"""
pull_fg_asof_rp_0615.py — historical AS-OF FanGraphs Stuff+ snapshots for the
rprs2 (RP) Stuff+ validation (2026-07-09).

For each season 2021-2025 pulls TWO windows via the FG leaders date-range API
(month=1000):
  • 0615 window : {Y}-03-01 .. {Y}-06-15   (as-of / in-season framing)
  • full window : {Y}-03-01 .. {Y}-11-30   (full season)
Plus 2026 season-start .. today (0709).

Differences vs the 2026-06-06 fg_asof_scrape.py pulls:
  • pageitems=3000 (the old pulls were capped at 500 rows/page — that cap
    truncates the qual=0 pool and disproportionately drops RELIEVERS, the
    exact population this validation needs).
  • cutoff June 15 (old was June 6 / May 16).

Cloudflare blocks plain requests (403 verified 2026-07-09), so this reuses the
undetected-chromedriver machinery from pull_fg_undetected.py (worked 2026-07-08
with version_main=148). Polite: >= 2s between requests, everything cached —
existing non-trivial CSVs are never re-fetched.

Outputs: data/research/fg_asof/fg_pit_asof_{year}_0615.csv
         data/research/fg_asof/fg_pit_asof_{year}_full.csv
         data/research/fg_asof/fg_pit_asof_2026_0709.csv
"""
from __future__ import annotations
import sys, time, json, re
from pathlib import Path
import pandas as pd
import undetected_chromedriver as uc

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "fg_asof"
OUT.mkdir(parents=True, exist_ok=True)

YEARS = [2021, 2022, 2023, 2024, 2025]

COLS = {
    'xMLBAMID': 'mlb_id', 'Name': 'player_name_fg', 'Team': 'team',
    'IP': 'ip', 'G': 'g', 'GS': 'gs', 'TBF': 'tbf',
    'SO': 'so', 'H': 'h', 'ER': 'er', 'R': 'r', 'BB': 'bb', 'HBP': 'hbp', 'HR': 'hr',
    'ERA': 'era', 'FIP': 'fip', 'xFIP': 'xfip', 'SIERA': 'siera',
    'K%': 'k_pct', 'BB%': 'bb_pct', 'SwStr%': 'swstr_pct', 'CSW%': 'csw_pct',
    'sp_stuff': 'stuff_plus', 'sp_location': 'location_plus', 'sp_pitching': 'pitching_plus',
    'pb_stuff': 'pb_stuff', 'pb_command': 'pb_command', 'pb_xRV100': 'pb_xrv100',
}

WARM = 'https://www.fangraphs.com/leaders/major-league?stats=pit&season=2025&type=8'


def clean(v):
    return re.sub(r'<[^>]+>', '', v).strip() if isinstance(v, str) else v


def api_url(year: int, start: str, end: str) -> str:
    return (f'https://www.fangraphs.com/api/leaders/major-league/data?'
            f'pos=all&stats=pit&lg=all&qual=0&season={year}&season1={year}'
            f'&startdate={start}&enddate={end}&month=1000&team=0'
            f'&pageitems=3000&pagenum=1&ind=0&type=8')


def fetch(driver, year: int, start: str, end: str, label: str):
    url = api_url(year, start, end)
    for attempt in range(3):
        try:
            js = f'''return await new Promise((res)=>{{fetch("{url}",{{credentials:"include"}})
                .then(r=>r.text().then(t=>res({{status:r.status,body:t}})))
                .catch(e=>res({{status:0,body:String(e)}}));}});'''
            resp = driver.execute_script(js)
            if resp.get('status') != 200:
                print(f"  [{year} {label}] attempt {attempt+1}: HTTP {resp.get('status')}", flush=True)
                time.sleep(5); driver.get(WARM); time.sleep(8); continue
            rows = json.loads(resp['body']).get('data', [])
            if not rows:
                print(f"  [{year} {label}] attempt {attempt+1}: 0 rows", flush=True)
                time.sleep(5); continue
            if len(rows) >= 3000:
                print(f"  [{year} {label}] WARNING: hit pageitems cap ({len(rows)})", flush=True)
            recs = [{dst: clean(r.get(src)) for src, dst in COLS.items()} for r in rows]
            df = pd.DataFrame(recs)
            df['mlb_id'] = pd.to_numeric(df['mlb_id'], errors='coerce').astype('Int64')
            return df
        except Exception as e:
            print(f"  [{year} {label}] attempt {attempt+1} EXC: {type(e).__name__} {str(e)[:100]}", flush=True)
            time.sleep(6)
            try:
                driver.get(WARM); time.sleep(8)
            except Exception:
                pass
    return None


def main() -> int:
    pulls = []
    for yr in YEARS:
        pulls.append((yr, f"{yr}-03-01", f"{yr}-06-15", f"fg_pit_asof_{yr}_0615.csv", "0615"))
        pulls.append((yr, f"{yr}-03-01", f"{yr}-11-30", f"fg_pit_asof_{yr}_full.csv", "full"))
    pulls.append((2026, "2026-03-01", "2026-07-09", "fg_pit_asof_2026_0709.csv", "0709"))

    # skip anything already cached
    todo = []
    for yr, s, e, fname, label in pulls:
        p = OUT / fname
        if p.exists():
            try:
                if len(pd.read_csv(p)) > 100:
                    print(f"[{yr} {label}] cached -> skip ({fname})", flush=True)
                    continue
            except Exception:
                pass
        todo.append((yr, s, e, fname, label))
    if not todo:
        print("All pulls cached — nothing to do.")
        return 0

    print(f"Launching undetected Chrome for {len(todo)} pulls...", flush=True)
    opts = uc.ChromeOptions()
    opts.add_argument('--disable-blink-features=AutomationControlled')
    try:
        driver = uc.Chrome(options=opts, version_main=148)
    except Exception as e:
        print(f"version_main=148 failed ({e}); retrying auto-detect...", flush=True)
        opts = uc.ChromeOptions()
        opts.add_argument('--disable-blink-features=AutomationControlled')
        driver = uc.Chrome(options=opts)

    ok = 0
    try:
        driver.get(WARM); time.sleep(12)
        for yr, s, e, fname, label in todo:
            df = fetch(driver, yr, s, e, label)
            if df is not None and len(df) > 100:
                df.to_csv(OUT / fname, index=False)
                nst = df['stuff_plus'].notna().sum()
                nid = df['mlb_id'].notna().sum()
                print(f"[{yr} {label}] SUCCESS {len(df)} rows, stuff+={nst}, mlb_id={nid} -> {fname}", flush=True)
                ok += 1
            else:
                print(f"[{yr} {label}] FAILED", flush=True)
            time.sleep(3)   # politeness: >= 2s between requests
        print(f"\n=== {ok}/{len(todo)} pulls ok ===", flush=True)
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    return 0 if ok == len(todo) else 1


if __name__ == '__main__':
    sys.exit(main())

"""
fg_asof_scrape.py — pull as-of-cutoff + rest-of-season FG pitcher snapshots
for the in-season-leading validation of Stuff+/Location+/Pitching+/PitchingBot.

For each season 2021-2025 (2020 excluded — COVID short season):
  • PRE window  : season start .. CUTOFF (June 6)  -> metrics measured here
  • ROS window  : CUTOFF+1     .. season end       -> outcome FP/start here

Single reused browser session, retry on Cloudflare connection resets.
Outputs CSVs to data/research/fg_asof/.
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
CUTOFF_MD = "06-06"      # as-of date (mimics today's 2026-06-06 deployment point)
SEASON_END_MD = "11-01"

# metrics + counting stats. FG type=8 returns these uppercase keys.
COLS = {
    'xMLBAMID':'mlb_id','Name':'player_name_fg','Team':'team','Season':'season',
    'IP':'ip','G':'g','GS':'gs','TBF':'tbf',
    'SO':'so','H':'h','ER':'er','R':'r','BB':'bb','HBP':'hbp','HR':'hr',
    'ERA':'era','FIP':'fip','xFIP':'xfip','SIERA':'siera',
    'K%':'k_pct','BB%':'bb_pct','SwStr%':'swstr_pct','CSW%':'csw_pct',
    'sp_stuff':'stuff_plus','sp_location':'location_plus','sp_pitching':'pitching_plus',
    'pb_stuff':'pb_stuff','pb_command':'pb_command','pb_xRV100':'pb_xrv100',
}

def clean(v):
    return re.sub(r'<[^>]+>','',v).strip() if isinstance(v,str) else v

def api_url(year, start, end):
    return (f'https://www.fangraphs.com/api/leaders/major-league/data?'
            f'pos=all&stats=pit&lg=all&qual=0&season={year}&season1={year}'
            f'&startdate={start}&enddate={end}&month=1000&team=0'
            f'&pageitems=500&pagenum=1&ind=0&type=8')

def fetch(driver, year, start, end, label, dump_keys=False):
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
            if dump_keys:
                print("  RAW KEYS:", sorted(rows[0].keys()), flush=True)
            recs = [{dst: clean(r.get(src)) for src,dst in COLS.items()} for r in rows]
            df = pd.DataFrame(recs)
            df['mlb_id'] = pd.to_numeric(df['mlb_id'], errors='coerce').astype('Int64')
            return df
        except Exception as e:
            print(f"  [{year} {label}] attempt {attempt+1} EXC: {type(e).__name__} {str(e)[:80]}", flush=True)
            time.sleep(6)
            try: driver.get(WARM); time.sleep(8)
            except Exception: pass
    return None

WARM = 'https://www.fangraphs.com/leaders/major-league?stats=pit&season=2024&type=8'

def main():
    opts = uc.ChromeOptions()
    opts.add_argument('--disable-blink-features=AutomationControlled')
    driver = uc.Chrome(options=opts, version_main=148)
    ok = 0
    try:
        print("Warming session...", flush=True)
        driver.get(WARM); time.sleep(12)
        first = True
        for yr in YEARS:
            cut = f"{yr}-{CUTOFF_MD}"
            for label, start, end in [
                ("pre", f"{yr}-03-01", cut),
                ("ros", f"{yr}-06-07", f"{yr}-{SEASON_END_MD}"),
            ]:
                p = OUT / f"fg_pit_{yr}_{label}.csv"
                if p.exists() and len(pd.read_csv(p)) > 50:
                    print(f"[{yr} {label}] cached", flush=True); ok += 1; continue
                df = fetch(driver, yr, start, end, label, dump_keys=first)
                first = False
                if df is not None and len(df) > 50:
                    df.to_csv(p, index=False)
                    nst = df['stuff_plus'].notna().sum()
                    print(f"[{yr} {label}] SUCCESS {len(df)} rows, stuff+={nst} -> {p.name}", flush=True)
                    ok += 1
                else:
                    print(f"[{yr} {label}] FAILED", flush=True)
                time.sleep(3)
        print(f"\n=== {ok}/{len(YEARS)*2} pulls ok ===", flush=True)
    finally:
        try: driver.quit()
        except Exception: pass

if __name__ == '__main__':
    sys.exit(main())

"""
pull_fg_asof_rp_windows.py — MULTI-WINDOW historical as-of FanGraphs Stuff+
snapshots for the rprs2 (RP) stuff_plus_asof MULTI-SPLIT validation
(2026-07-09; prereg data/research/validation_runs/
rp_stuff_plus_asof_multisplit_2026-07-09.md).

Generalizes pull_fg_asof_rp_0615.py (left untouched) from one fixed June-15
window to the full window schedule needed to serve EVERY rolling_relievers
split_day without leakage:

  2021-2025 : {Y}-03-01 .. {Y}-{MM-DD} for MM-DD in
              05-01, 06-01, 06-15, 07-01, 08-01, 09-01
  2026      : 2026-03-01 .. 2026-{MM-DD} for MM-DD in 05-01, 06-01, 07-01
              (production continuity; the daily current-season value comes
              from fg_pit_2026_current.csv via refresh step 0.8)

Everything cached + idempotent: existing non-trivial CSVs (>100 rows) are
never re-fetched — the _0615 files pulled earlier today are reused as-is.

Cloudflare blocks plain requests (403 verified 2026-07-09), so this reuses
the undetected-chromedriver machinery (version_main=148 worked 2026-07-08/09).
Polite: >= 2s between requests.

Outputs: data/research/fg_asof/fg_pit_asof_{year}_{MMDD}.csv
"""
from __future__ import annotations
import sys, time, json, re
from pathlib import Path
import pandas as pd
import undetected_chromedriver as uc

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "fg_asof"
OUT.mkdir(parents=True, exist_ok=True)

HIST_YEARS = [2021, 2022, 2023, 2024, 2025]
HIST_ENDS = ["05-01", "06-01", "06-15", "07-01", "08-01", "09-01"]
CUR_YEAR = 2026
CUR_ENDS = ["05-01", "06-01", "07-01"]

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

# exception type names that mean the driver SESSION is dead (relaunch needed,
# retrying the same session is pointless — observed 2026-07-09 first run:
# one ProtocolError then endless MaxRetryError against the dead local port)
DEAD_SESSION_EXC = ('MaxRetryError', 'ProtocolError', 'ConnectionResetError',
                    'NewConnectionError', 'InvalidSessionIdException',
                    'NoSuchWindowException', 'WebDriverException')


class DeadSession(Exception):
    pass


def new_driver():
    opts = uc.ChromeOptions()
    opts.add_argument('--disable-blink-features=AutomationControlled')
    try:
        d = uc.Chrome(options=opts, version_main=148)
    except Exception as e:
        print(f"version_main=148 failed ({e}); retrying auto-detect...", flush=True)
        opts = uc.ChromeOptions()
        opts.add_argument('--disable-blink-features=AutomationControlled')
        d = uc.Chrome(options=opts)
    d.get(WARM)
    time.sleep(12)
    return d


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
            name = type(e).__name__
            print(f"  [{year} {label}] attempt {attempt+1} EXC: {name} {str(e)[:100]}", flush=True)
            if name in DEAD_SESSION_EXC:
                raise DeadSession(name)   # session is gone — relaunch, don't retry it
            time.sleep(6)
            try:
                driver.get(WARM); time.sleep(8)
            except Exception:
                pass
    return None


def main() -> int:
    pulls = []
    for yr in HIST_YEARS:
        for end in HIST_ENDS:
            mmdd = end.replace('-', '')
            pulls.append((yr, f"{yr}-03-01", f"{yr}-{end}", f"fg_pit_asof_{yr}_{mmdd}.csv", mmdd))
    for end in CUR_ENDS:
        mmdd = end.replace('-', '')
        pulls.append((CUR_YEAR, f"{CUR_YEAR}-03-01", f"{CUR_YEAR}-{end}",
                      f"fg_pit_asof_{CUR_YEAR}_{mmdd}.csv", mmdd))

    # idempotent: skip anything already cached with a non-trivial row count
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
    driver = new_driver()
    relaunches_left = 4
    ok = 0
    try:
        for yr, s, e, fname, label in todo:
            df = None
            for _pass in range(2):   # second pass = after a driver relaunch
                try:
                    df = fetch(driver, yr, s, e, label)
                    break
                except DeadSession as ds:
                    print(f"[{yr} {label}] dead driver session ({ds}); "
                          f"relaunching ({relaunches_left} left)...", flush=True)
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    if relaunches_left <= 0:
                        print("No relaunches left — stopping run, keeping cache.", flush=True)
                        raise SystemExit(1)
                    relaunches_left -= 1
                    time.sleep(5)
                    driver = new_driver()
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

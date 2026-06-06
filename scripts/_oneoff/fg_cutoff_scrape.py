"""Pull FG pre+ros snapshots at an arbitrary cutoff (for the convergence curve).
Usage: python fg_cutoff_scrape.py MM-DD
Reuses one browser session; same retry logic as fg_asof_scrape.py."""
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
    'xMLBAMID':'mlb_id','Name':'player_name_fg','Season':'season',
    'IP':'ip','G':'g','GS':'gs','SO':'so','H':'h','ER':'er','BB':'bb','HBP':'hbp',
    'K%':'k_pct','BB%':'bb_pct','SwStr%':'swstr_pct','SIERA':'siera',
    'sp_stuff':'stuff_plus','sp_location':'location_plus','sp_pitching':'pitching_plus',
    'pb_stuff':'pb_stuff','pb_command':'pb_command',
}
WARM = 'https://www.fangraphs.com/leaders/major-league?stats=pit&season=2024&type=8'

def clean(v): return re.sub(r'<[^>]+>','',v).strip() if isinstance(v,str) else v
def url(y,s,e): return (f'https://www.fangraphs.com/api/leaders/major-league/data?'
    f'pos=all&stats=pit&lg=all&qual=0&season={y}&season1={y}&startdate={s}&enddate={e}'
    f'&month=1000&team=0&pageitems=500&pagenum=1&ind=0&type=8')

def fetch(driver,y,s,e):
    for a in range(3):
        try:
            js=f'''return await new Promise((r)=>{{fetch("{url(y,s,e)}",{{credentials:"include"}})
                .then(x=>x.text().then(t=>r({{status:x.status,body:t}}))).catch(z=>r({{status:0,body:String(z)}}));}});'''
            resp=driver.execute_script(js)
            if resp.get('status')!=200: time.sleep(5); driver.get(WARM); time.sleep(8); continue
            rows=json.loads(resp['body']).get('data',[])
            if not rows: time.sleep(5); continue
            df=pd.DataFrame([{d:clean(rr.get(sk)) for sk,d in COLS.items()} for rr in rows])
            df['mlb_id']=pd.to_numeric(df['mlb_id'],errors='coerce').astype('Int64')
            return df
        except Exception as ex:
            print("  EXC",type(ex).__name__,str(ex)[:60],flush=True); time.sleep(6)
            try: driver.get(WARM); time.sleep(8)
            except Exception: pass
    return None

def main():
    cut=sys.argv[1]  # MM-DD
    o=uc.ChromeOptions(); o.add_argument('--disable-blink-features=AutomationControlled')
    driver=uc.Chrome(options=o,version_main=148); ok=0
    try:
        driver.get(WARM); time.sleep(12)
        for yr in YEARS:
            for label,s,e in [("pre",f"{yr}-03-01",f"{yr}-{cut}"),("ros",f"{yr}-{cut}",f"{yr}-11-01")]:
                # ros startdate = cutoff+1 day handled loosely; use cutoff as boundary (overlap 1 day negligible)
                p=OUT/f"fg_pit_{yr}_{label}_{cut}.csv"
                if p.exists() and len(pd.read_csv(p))>50: print(f"[{yr} {label} {cut}] cached",flush=True); ok+=1; continue
                df=fetch(driver,yr,s,e)
                if df is not None and len(df)>50:
                    df.to_csv(p,index=False); ok+=1
                    print(f"[{yr} {label} {cut}] OK {len(df)} stuff+={df['stuff_plus'].notna().sum()}",flush=True)
                else: print(f"[{yr} {label} {cut}] FAIL",flush=True)
                time.sleep(3)
        print(f"=== {ok}/{len(YEARS)*2} ok for {cut} ===",flush=True)
    finally:
        try: driver.quit()
        except Exception: pass

if __name__=='__main__': main()

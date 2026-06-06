"""Pull 2026 season-to-date FG pitcher snapshot WITH counting stats (for the
live Stuff+ breakout tool). Foreground only."""
from __future__ import annotations
import time, json, re
from pathlib import Path
import pandas as pd
import undetected_chromedriver as uc

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "fg_asof"
COLS = {
    'xMLBAMID':'mlb_id','Name':'player_name_fg','Team':'team','Season':'season',
    'IP':'ip','G':'g','GS':'gs','SO':'so','H':'h','ER':'er','BB':'bb','HBP':'hbp',
    'K%':'k_pct','BB%':'bb_pct','SwStr%':'swstr_pct','SIERA':'siera',
    'sp_stuff':'stuff_plus','sp_location':'location_plus','sp_pitching':'pitching_plus',
    'pb_stuff':'pb_stuff','pb_command':'pb_command',
}
WARM = 'https://www.fangraphs.com/leaders/major-league?stats=pit&season=2026&type=8'
def clean(v): return re.sub(r'<[^>]+>','',v).strip() if isinstance(v,str) else v

def main():
    url=('https://www.fangraphs.com/api/leaders/major-league/data?'
         'pos=all&stats=pit&lg=all&qual=0&season=2026&season1=2026'
         '&startdate=2026-03-01&enddate=2026-12-31&month=1000&team=0'
         '&pageitems=1000&pagenum=1&ind=0&type=8')
    o=uc.ChromeOptions(); o.add_argument('--disable-blink-features=AutomationControlled')
    d=uc.Chrome(options=o,version_main=148)
    try:
        d.get(WARM); time.sleep(12)
        for a in range(3):
            js=f'''return await new Promise((r)=>{{fetch("{url}",{{credentials:"include"}})
                .then(x=>x.text().then(t=>r({{status:x.status,body:t}}))).catch(z=>r({{status:0,body:String(z)}}));}});'''
            resp=d.execute_script(js)
            if resp.get('status')==200: break
            time.sleep(5); d.get(WARM); time.sleep(8)
        rows=json.loads(resp['body']).get('data',[])
        df=pd.DataFrame([{dst:clean(rr.get(sk)) for sk,dst in COLS.items()} for rr in rows])
        df['mlb_id']=pd.to_numeric(df['mlb_id'],errors='coerce').astype('Int64')
        p=OUT/'fg_pit_2026_current.csv'; df.to_csv(p,index=False)
        print(f"OK {len(df)} rows, stuff+={df['stuff_plus'].notna().sum()} -> {p.name}",flush=True)
    finally:
        try: d.quit()
        except Exception: pass

if __name__=='__main__': main()

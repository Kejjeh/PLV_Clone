"""How far back does Savant's bat-tracking leaderboard actually serve data?
Probe 2019-2026. Guard against the obs-1870 trap: if seasonStart is ignored,
Savant returns the CURRENT season (2026) for every year. So we fingerprint each
year and flag any year whose data == 2026's (=> not really available)."""
import io, time
import pandas as pd
import requests

BASE = ("https://baseballsavant.mlb.com/leaderboard/bat-tracking"
        "?gameType=Regular&minSwings=q&minGroupSwings=1"
        "&seasonStart={y}&seasonEnd={y}&type=batter&csv=true")
HDR = {"User-Agent": "Mozilla/5.0 (research; plv_clone validate-feature)"}

def pull(y):
    url = BASE.format(y=y)
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HDR, timeout=45)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            return df
        except Exception as e:
            if attempt == 2:
                return f"ERROR: {type(e).__name__}: {e}"
            time.sleep(3)

def fp(df):
    """fingerprint: sorted (id, bat_speed) for first 5 ids by id."""
    idc = 'id' if 'id' in df.columns else ('mlbam_id' if 'mlbam_id' in df.columns else df.columns[0])
    bs = [c for c in df.columns if 'bat_speed' in c.lower()]
    bsc = bs[0] if bs else None
    d = df[[idc] + ([bsc] if bsc else [])].dropna().sort_values(idc).head(5)
    return tuple(map(tuple, d.values)), bsc

results = {}
for y in [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]:
    df = pull(y)
    if isinstance(df, str):
        print(f"{y}: {df}")
        continue
    f, bsc = fp(df)
    mean_bs = df[bsc].mean() if bsc else float('nan')
    results[y] = {'n': len(df), 'fp': f, 'mean_bs': mean_bs}
    print(f"{y}: rows={len(df):4d}  mean_bat_speed={mean_bs:.3f}  fp_first_id={f[0] if f else None}")

# duplicate / defaulting detection
print("\n--- duplicate check (== 2026 means year not really served) ---")
ref = results.get(2026, {}).get('fp')
for y, d in results.items():
    same_as_2026 = (d['fp'] == ref and y != 2026)
    print(f"{y}: {'*** SAME AS 2026 (param ignored, not served)' if same_as_2026 else 'distinct'}")

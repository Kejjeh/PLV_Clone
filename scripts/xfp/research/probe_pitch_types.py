import io, requests
import pandas as pd

HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE = "https://baseballsavant.mlb.com/leaderboard/bat-tracking"

def probe(label, url):
    r = requests.get(url, timeout=30, headers=HEADERS)
    df = pd.read_csv(io.StringIO(r.text))
    if df.empty:
        print(f"  {label}: EMPTY")
        return
    spd = df["avg_bat_speed"].mean()
    blast = df["blast_per_swing"].mean()
    sw = df["swords"].mean()
    print(f"  {label}: {len(df)} rows  bat_speed={spd:.3f}  blast={blast:.4f}  swords={sw:.3f}")

for yr in [2023, 2024, 2025]:
    print(f"\nYear {yr}:")
    probe("overall", f"{BASE}?gameType=Regular&minSwings=q&minGroupSwings=1&seasonStart={yr}&seasonEnd={yr}&type=batter&csv=true")
    for pt in ["FF", "SL", "CH", "CU", "SI", "FS", "KC", "FC"]:
        probe(f"pitchType={pt}", f"{BASE}?gameType=Regular&minSwings=q&minGroupSwings=1&seasonStart={yr}&seasonEnd={yr}&type=batter&pitchType={pt}&csv=true")

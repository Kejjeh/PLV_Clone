import io, warnings
import requests, pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")
HEADERS = {"User-Agent": "Mozilla/5.0"}
HITTER_PANEL = "data/research/xfp_cache/hitters_multiyr_2015_2026.csv"
YEARS = [2023, 2024, 2025, 2026]
MAIN_PT = ["FF", "SL", "CH", "CU", "SI"]
METRICS = ["whiff_rate", "lined_up_percent", "miss_distance"]

frames = []
for yr in YEARS:
    url = (f"https://baseballsavant.mlb.com/leaderboard/bat-tracking/"
           f"swing-timing-miss-distance?type=batter&season[]={yr}&splitYear=1"
           f"&min=1&split[]=api_pitch_type_group03&minSplit=1&gameType[]=R&csv=true")
    r = requests.get(url, timeout=30, headers=HEADERS)
    df = pd.read_csv(io.StringIO(r.text))
    if not df.empty:
        df["year"] = yr
        df.rename(columns={"id": "mlbam_id"}, inplace=True)
        for c in METRICS + ["n_swings"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df["mlbam_id"] = pd.to_numeric(df["mlbam_id"], errors="coerce").astype("Int64")
        frames.append(df)

tm = pd.concat(frames, ignore_index=True)
print(f"Raw: {len(tm)} rows  |  pitch types: {sorted(tm['api_pitch_type'].dropna().unique())}")

# Pivot wide
parts = []
for pt_val in MAIN_PT:
    sub = tm[tm["api_pitch_type"] == pt_val][["mlbam_id", "year"] + METRICS].copy()
    sub = sub.rename(columns={m: f"{m}_{pt_val}" for m in METRICS})
    parts.append(sub)
wide = parts[0]
for p in parts[1:]:
    wide = wide.merge(p, on=["mlbam_id", "year"], how="outer")

print(f"\nWide shape: {wide.shape}")
print(f"Cols: {list(wide.columns)}")
for pt in MAIN_PT:
    col = f"whiff_rate_{pt}"
    print(f"  {col} non-null: {wide[col].notna().sum()}")

# Load FP panel and join
h = pd.read_csv(HITTER_PANEL)
h = h[h["pa"] >= 200].copy()
h["year"] = h["year"].astype(int)
h.rename(columns={"batter": "mlbam_id"}, inplace=True)
h["mlbam_id"] = h["mlbam_id"].astype("Int64")

joined = wide.merge(h[["mlbam_id", "year", "fp_per_pa_actual"]], on=["mlbam_id", "year"], how="inner")
print(f"\nJoined with FP panel: {len(joined)} rows")

for pt in MAIN_PT:
    col = f"whiff_rate_{pt}"
    sub = joined[[col, "fp_per_pa_actual"]].dropna()
    if len(sub) >= 15:
        r, p = stats.pearsonr(sub[col], sub["fp_per_pa_actual"])
        sig = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "n.s."))
        print(f"  whiff_rate_{pt} → FP: r={r:.3f} {sig}  (n={len(sub)})")
    else:
        print(f"  whiff_rate_{pt}: only {len(sub)} rows after dropna")

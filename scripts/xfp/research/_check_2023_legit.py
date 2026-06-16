"""Is the '2023' bat-tracking column a genuine season or relabeled 2024?
Test: find players present ONLY in 2023 (absent 2024/25/26). If 2023 were
relabeled 2024, there'd be ~none. Real 2023-only players = retired-after-2023
vets => 2023 is a genuine distinct season."""
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
df = pd.read_csv(ROOT / 'data' / 'research' / 'bat_tracking_all_2023_2026.csv')
df = df[df['player_type'].astype(str).str.lower().str.startswith('bat')]
# unique (id, name, year)
g = df.groupby('mlbam_id').agg(name=('name','first'),
                               years=('year', lambda s: sorted(set(s)))).reset_index()
only2023 = g[g['years'].apply(lambda ys: ys == [2023])]
only2026 = g[g['years'].apply(lambda ys: ys == [2026])]
all4 = g[g['years'].apply(lambda ys: ys == [2023,2024,2025,2026])]
print(f"unique hitters total: {len(g)}")
print(f"present in ALL 4 years (2023-2026): {len(all4)}")
print(f"present ONLY in 2023: {len(only2023)}")
print("  sample 2023-only names:", list(only2023['name'].head(15)))
print(f"present ONLY in 2026 (rookies/debuts): {len(only2026)}")
print("  sample 2026-only names:", list(only2026['name'].head(15)))
# year-count distribution
from collections import Counter
print("hitters by #years present:", dict(sorted(Counter(g['years'].apply(len)).items())))

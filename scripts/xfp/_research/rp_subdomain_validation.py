"""
RP sub-domain validation — YoY stability tests for proposed RP archetype dimensions.

Mirrors the SP archetype YoY validation discipline. Tests:
  A — YoY r for SWING_MISS, CALLED_STRIKE, DAMAGE_SUPP, GB_TENDENCY, WALK_AVOID, velo
  B — YoY r for L/R splits (RP-specific re-test after SP failure)
  C — Role persistence (CLOSER/SETUP/MIDDLE/MOPUP) confusion
  D — gmLI YoY (if data present)
  E — IP_per_appearance YoY

Cohort: G >= 20 AND TBF >= 50 in BOTH years of the YoY pair. Years 2018-2025.

Outputs: scripts/xfp/_research/RP_VALIDATION_<test>.csv + console summary.
"""
from __future__ import annotations
import os, json
import numpy as np
import pandas as pd
import pyarrow.dataset as ds

ROOT = r"c:\Users\Joshua\plv_clone"
RP_CSV    = f"{ROOT}/data/research/xfp_cache/relievers_multiyr_2018_2026.csv"
SPLITS_CSV = f"{ROOT}/data/research/xfp_cache/pitcher_splits.csv"
STATCAST_GLOB = f"{ROOT}/data/research/xfp_cache/statcast_*.parquet"
OUT_DIR = f"{ROOT}/scripts/xfp/_research"

YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
G_FLOOR = 20
TBF_FLOOR = 50


def cohort(df: pd.DataFrame) -> pd.DataFrame:
    """RP cohort floor — applied consistently across years."""
    return df[(df['g'] >= G_FLOOR) & (df['tbf_api'] >= TBF_FLOOR)].copy()


def yoy_pairs(df: pd.DataFrame, key: str = 'pitcher', value_cols=None) -> pd.DataFrame:
    """Build (pitcher, year_t, year_t+1) pair table with values from both."""
    if value_cols is None:
        value_cols = [c for c in df.columns if c not in (key, 'year')]
    df = df[[key, 'year'] + value_cols].copy()
    df_next = df.copy()
    df_next['year'] = df_next['year'] - 1
    merged = df.merge(df_next, on=[key, 'year'], suffixes=('_t', '_tp1'))
    return merged


def pearson_r(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    m = ~(np.isnan(a) | np.isnan(b))
    if m.sum() < 5:
        return float('nan'), int(m.sum())
    return float(np.corrcoef(a[m], b[m])[0, 1]), int(m.sum())


def verdict(r):
    if np.isnan(r):
        return "INSUFFICIENT"
    if r >= 0.40:
        return "KEEP"
    if r >= 0.20:
        return "MAYBE"
    return "DROP"


# ──────────────────────────────────────────────────────────────────────────────
# Load RP base
# ──────────────────────────────────────────────────────────────────────────────
print("[load] relievers_multiyr_2018_2026.csv")
rp = pd.read_csv(RP_CSV)
rp = rp[rp['year'].isin(YEARS)]
rp_co = cohort(rp)
print(f"  RP cohort rows (g>={G_FLOOR}, tbf>={TBF_FLOOR}, 2018-2025): {len(rp_co)}")
print(f"  by year: {rp_co.groupby('year').size().to_dict()}")

# Compute IP per appearance for test E
# rp has 'ip' (innings pitched float). ip / g
rp_co['ip_per_g'] = rp_co['ip'] / rp_co['g'].replace(0, np.nan)

# ──────────────────────────────────────────────────────────────────────────────
# Build GB_TENDENCY (gb_pct) and DAMAGE_SUPP (barrel_pct) from statcast
# ──────────────────────────────────────────────────────────────────────────────
print("\n[load] deriving gb_pct + barrel_pct from statcast for RP cohort")
gb_rows = []
for y in YEARS:
    pq_path = f"{ROOT}/data/research/xfp_cache/statcast_{y}.parquet"
    if not os.path.exists(pq_path):
        print(f"  missing: {pq_path}")
        continue
    cols = ['pitcher', 'bb_type', 'launch_angle', 'launch_speed', 'launch_speed_angle',
            'estimated_woba_using_speedangle', 'description']
    sc = pd.read_parquet(pq_path, columns=cols)
    # BIP only (not null bb_type)
    bip = sc[sc['bb_type'].notna() & (sc['bb_type'] != '')].copy()
    # GB pct
    grp = bip.groupby('pitcher').agg(
        bip_n=('bb_type', 'size'),
        gb_n=('bb_type', lambda x: (x == 'ground_ball').sum()),
        # launch_speed_angle == 6 corresponds to a Statcast "barrel"
        barrel_n=('launch_speed_angle', lambda x: (x == 6).sum()),
        xwoba_contact_sum=('estimated_woba_using_speedangle', 'sum'),
        xwoba_contact_n=('estimated_woba_using_speedangle', lambda x: x.notna().sum()),
    ).reset_index()
    grp['gb_pct'] = grp['gb_n'] / grp['bip_n']
    grp['barrel_pct'] = grp['barrel_n'] / grp['bip_n']
    grp['xwoba_contact'] = grp['xwoba_contact_sum'] / grp['xwoba_contact_n'].replace(0, np.nan)
    grp['year'] = y
    gb_rows.append(grp[['pitcher', 'year', 'bip_n', 'gb_pct', 'barrel_pct', 'xwoba_contact']])
    print(f"  {y}: {len(grp)} pitchers from BIP")
gb_df = pd.concat(gb_rows, ignore_index=True)

# Merge gb/barrel/xwoba_contact onto RP cohort
rp_co = rp_co.merge(gb_df, on=['pitcher', 'year'], how='left')
print(f"  RP cohort gb_pct null rate: {rp_co['gb_pct'].isna().mean():.3f}")
print(f"  RP cohort barrel_pct null rate: {rp_co['barrel_pct'].isna().mean():.3f}")
print(f"  RP cohort xwoba_contact null rate: {rp_co['xwoba_contact'].isna().mean():.3f}")

# ──────────────────────────────────────────────────────────────────────────────
# TEST A — YoY stability of proposed sub-domains
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("TEST A — YoY stability of proposed RP rate sub-domains")
print("=" * 70)

A_METRICS = {
    'SWING_MISS (swstr_pct)': 'swstr_pct',
    'SWING_MISS (c_plus_swstr CSW)': 'c_plus_swstr',
    'CALLED_STRIKE (called_strike rate)': 'called_strike_rate',
    'DAMAGE_SUPP (xwoba_contact)': 'xwoba_contact',
    'DAMAGE_SUPP (barrel_pct)': 'barrel_pct',
    'GB_TENDENCY (gb_pct)': 'gb_pct',
    'WALK_AVOID (bb_pct)': 'bb_pct',
    'velo_rating (avg_velo)': 'avg_velo',
    'K_RATE (k_pct, reference)': 'k_pct',
    'xwoba_per_pa (overall reference)': 'xwoba_per_pa',
}
# Derive called_strike rate
rp_co['called_strike_rate'] = rp_co['called_strike'] / rp_co['pitches'].replace(0, np.nan)

# Apply cohort to BOTH years of every pair (same cohort def)
a_results = []
for label, col in A_METRICS.items():
    sub = rp_co[['pitcher', 'year', col]].dropna(subset=[col])
    pairs = yoy_pairs(sub, value_cols=[col])
    # pairs has col_t and col_tp1
    r, n = pearson_r(pairs[f'{col}_t'], pairs[f'{col}_tp1'])
    a_results.append({
        'metric': label,
        'column': col,
        'n_pairs': n,
        'r': round(r, 4) if not np.isnan(r) else None,
        'verdict': verdict(r),
    })
    print(f"  {label:40s}  n={n:5d}  r={r:+.4f}  → {verdict(r)}")

a_df = pd.DataFrame(a_results)
a_df.to_csv(f"{OUT_DIR}/RP_VALIDATION_A.csv", index=False)

# ──────────────────────────────────────────────────────────────────────────────
# TEST B — RE-TEST L/R splits for RPs
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("TEST B — L/R splits YoY for RPs (re-test after SP failure)")
print("=" * 70)

splits = pd.read_csv(SPLITS_CSV)
print(f"  splits file years: {sorted(splits['year'].unique())}")
print(f"  splits file shape: {splits.shape}")

# Restrict splits to RP cohort
rp_keys = rp_co[['pitcher', 'year']].drop_duplicates()
splits_rp = splits.merge(rp_keys, on=['pitcher', 'year'], how='inner')
print(f"  splits restricted to RP cohort: {len(splits_rp)}")

# We need each split row to also clear a TBF-vs-side floor or the corr is dominated by noise.
TBF_SIDE_FLOOR = 25  # ~25 TBF vs a side is a reasonable floor for xwoba stability

b_results = []
for side, tbf_col in [('vs_L', 'tbf_vs_L'), ('vs_R', 'tbf_vs_R')]:
    val_col = f'xwoba_{side}'
    s = splits_rp[(splits_rp[tbf_col] >= TBF_SIDE_FLOOR)][['pitcher', 'year', 'p_throws', val_col]].dropna()
    # Overall
    pairs = yoy_pairs(s[['pitcher', 'year', val_col]], value_cols=[val_col])
    r, n = pearson_r(pairs[f'{val_col}_t'], pairs[f'{val_col}_tp1'])
    b_results.append({'cohort': 'ALL_RPs', 'side': side, 'n_pairs': n, 'r': round(r, 4) if not np.isnan(r) else None, 'verdict': verdict(r)})
    print(f"  ALL_RPs   xwoba_{side:4s}  n={n:5d}  r={r:+.4f}  → {verdict(r)}")
    # By handedness
    for hand in ['R', 'L']:
        s_h = s[s['p_throws'] == hand][['pitcher', 'year', val_col]]
        pairs_h = yoy_pairs(s_h, value_cols=[val_col])
        r_h, n_h = pearson_r(pairs_h[f'{val_col}_t'], pairs_h[f'{val_col}_tp1'])
        b_results.append({'cohort': f'{hand}HP', 'side': side, 'n_pairs': n_h,
                          'r': round(r_h, 4) if not np.isnan(r_h) else None, 'verdict': verdict(r_h)})
        print(f"  {hand}HP only  xwoba_{side:4s}  n={n_h:5d}  r={r_h:+.4f}  → {verdict(r_h)}")

b_df = pd.DataFrame(b_results)
b_df.to_csv(f"{OUT_DIR}/RP_VALIDATION_B.csv", index=False)

# ──────────────────────────────────────────────────────────────────────────────
# TEST C — Role persistence YoY
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("TEST C — Role persistence YoY")
print("=" * 70)


def role_of(row):
    if row['sv'] >= 15:
        return 'CLOSER'
    if row['hld'] >= 15:
        return 'SETUP'
    if row['g'] >= 30:
        return 'MIDDLE'
    return 'MOPUP'


rp_co['role'] = rp_co.apply(role_of, axis=1)
roles = rp_co[['pitcher', 'year', 'role']]
pairs = yoy_pairs(roles, value_cols=['role'])
confusion = pairs.groupby(['role_t', 'role_tp1']).size().unstack(fill_value=0)
totals = confusion.sum(axis=1)
persistence = pd.DataFrame({
    'role': confusion.index,
    'n_year_t': totals.values,
    'persist_pct': [confusion.loc[r, r] / totals[r] if totals[r] > 0 else float('nan') for r in confusion.index],
})
print("\nConfusion matrix (rows=year_t role, cols=year_t+1 role, normalized by row):")
norm = confusion.div(totals, axis=0)
print(norm.round(3))
print("\nDiagonal persistence rates:")
for _, row in persistence.iterrows():
    pct = row['persist_pct']
    print(f"  {row['role']:8s}  n_t={int(row['n_year_t']):4d}  persist={pct:.1%}")

confusion.to_csv(f"{OUT_DIR}/RP_VALIDATION_C_confusion.csv")
persistence.to_csv(f"{OUT_DIR}/RP_VALIDATION_C_persistence.csv", index=False)

# Cramer's V proxy for overall stability (chi-square would be heavier).
# Per role we report the persist_pct.
overall_persist = (pairs['role_t'] == pairs['role_tp1']).mean()
print(f"\n  Overall any-role persistence (4-class match): {overall_persist:.1%}  n_pairs={len(pairs)}")

# ──────────────────────────────────────────────────────────────────────────────
# TEST D — gmLI stability
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("TEST D — gmLI YoY")
print("=" * 70)
# Search columns
candidate_cols = []
for f in ['xfp_cache/relievers_multiyr_2018_2026.csv',
          'xfp_cache/rolling_relievers_2018_2026.csv',
          'xfp_cache/rp3_training_frame_full.csv']:
    full = f"{ROOT}/data/research/{f}"
    if os.path.exists(full):
        head = pd.read_csv(full, nrows=2)
        cs = [c for c in head.columns if 'li' in c.lower() and len(c) <= 8]
        if cs:
            candidate_cols.append((f, cs))
if not candidate_cols:
    print("  gmLI: NOT PRESENT in any candidate file. Verdict: BLOCKED (need FanGraphs scrape).")
    d_status = "BLOCKED - data absent"
else:
    print(f"  Found candidate cols: {candidate_cols}")
    d_status = "FOUND - see candidate cols, manual review needed"

with open(f"{OUT_DIR}/RP_VALIDATION_D.csv", 'w') as fh:
    fh.write(f"test,status\nD_gmLI,{d_status}\n")

# ──────────────────────────────────────────────────────────────────────────────
# TEST E — IP per appearance YoY
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("TEST E — IP per appearance YoY")
print("=" * 70)
ip_sub = rp_co[['pitcher', 'year', 'ip_per_g']].dropna()
pairs_e = yoy_pairs(ip_sub, value_cols=['ip_per_g'])
r_e, n_e = pearson_r(pairs_e['ip_per_g_t'], pairs_e['ip_per_g_tp1'])
print(f"  IP_per_appearance  n={n_e}  r={r_e:+.4f}  → {verdict(r_e)}")
pd.DataFrame([{'metric': 'ip_per_appearance', 'n_pairs': n_e, 'r': round(r_e, 4),
               'verdict': verdict(r_e)}]).to_csv(f"{OUT_DIR}/RP_VALIDATION_E.csv", index=False)

# ──────────────────────────────────────────────────────────────────────────────
# Bundle everything as JSON for report builder
# ──────────────────────────────────────────────────────────────────────────────
summary = {
    'cohort_floor': {'G_min': G_FLOOR, 'TBF_min': TBF_FLOOR, 'TBF_side_min_B': TBF_SIDE_FLOOR},
    'years_pairs': '2018-2019, ..., 2024-2025',
    'test_A': a_results,
    'test_B': b_results,
    'test_C': {
        'persistence': persistence.to_dict(orient='records'),
        'overall_any_role_match': float(overall_persist),
        'confusion_normalized': norm.round(3).to_dict(),
    },
    'test_D_status': d_status,
    'test_E': {'metric': 'ip_per_appearance', 'n_pairs': int(n_e), 'r': round(r_e, 4), 'verdict': verdict(r_e)},
}
with open(f"{OUT_DIR}/RP_VALIDATION_summary.json", 'w') as fh:
    json.dump(summary, fh, indent=2, default=str)
print(f"\n[done] summary → {OUT_DIR}/RP_VALIDATION_summary.json")

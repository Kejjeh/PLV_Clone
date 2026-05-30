"""
hitter_subdomain_validation.py — YoY stability tests for proposed hitter
archetype sub-domains. Mirrors RP/SP archetype YoY validation discipline.

For each current hitter sub-domain (the inputs to CONTACT / POWER /
DISCIPLINE / SB in build_hitter_archetypes.py), compute the year-over-year
Pearson r at the player-year level for cohort 2018-2025 (drop 2026 — in-
progress). Population: hitters with PA >= 250 in both year T and year T+1.

Bar (mirrors RP): r >= 0.40 = KEEP, 0.20-0.40 = MAYBE, < 0.20 = DROP.

Outputs:
  scripts/xfp/_research/HITTER_VALIDATION_A_raw_inputs.csv     — r_* underlying rate columns
  scripts/xfp/_research/HITTER_VALIDATION_B_subdomains.csv     — 12 main sub-domain ratings
  scripts/xfp/_research/HITTER_VALIDATION_C_alternatives.csv   — alternative metrics tested for failures
  scripts/xfp/_research/HITTER_VALIDATION_summary.json
"""
from __future__ import annotations
import os, json
import numpy as np
import pandas as pd

ROOT = r"c:\Users\Joshua\plv_clone"
HIT_CSV = f"{ROOT}/data/research/xfp_cache/hitters_multiyr_2015_2026.csv"
OUT_DIR = f"{ROOT}/scripts/xfp/_research"

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]  # drop COVID 2020 + in-progress 2026
PA_FLOOR = 250  # FULL tier from build_hitter_archetypes.py


def cohort(df: pd.DataFrame) -> pd.DataFrame:
    """Hitter cohort floor — PA >= 250, exclude 2020 COVID year."""
    return df[(df['pa'] >= PA_FLOOR) & (df['year'].isin(YEARS))].copy()


def yoy_pairs(df: pd.DataFrame, key: str = 'batter', value_cols=None) -> pd.DataFrame:
    if value_cols is None:
        value_cols = [c for c in df.columns if c not in (key, 'year')]
    df = df[[key, 'year'] + value_cols].copy()
    df_next = df.copy()
    df_next['year'] = df_next['year'] - 1
    merged = df.merge(df_next, on=[key, 'year'], suffixes=('_t', '_tp1'))
    # Drop pairs that straddle 2020 (e.g., 2019->2020 or 2020->2021)
    # Since 2020 is excluded from input via cohort(), this is automatic, but the
    # YoY gap construction can still produce 2019->2020 ghost pairs if 2020 had
    # any rows. cohort() filters them so the merge gives 0 there. We additionally
    # forbid year_t == 2019 (would pair to 2020 which is absent) and year_t == 2020.
    merged = merged[merged['year'].between(2018, 2024)]  # year_t valid range
    merged = merged[merged['year'] != 2019]              # no 2019->2020 pair (2020 absent)
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
# Load + derive
# ──────────────────────────────────────────────────────────────────────────────
print(f"[load] {HIT_CSV}")
h = pd.read_csv(HIT_CSV)
print(f"  rows raw: {len(h)}")

# Derive babip + sb_per_opp + o_contact_pct + 2b3b_rate + spray entropy
# (mirror build_hitter_archetypes.py derivations exactly).
denom_babip = (h['ab'] - h['k'] - h['hr']).clip(lower=1)
h['babip'] = ((h['h'] - h['hr']) / denom_babip).clip(lower=0, upper=1)

opp_sb = (h['b1'] + h['bb'] + h['hbp']).clip(lower=1)
h['sb_per_opp'] = (h['sb'] / opp_sb).clip(lower=0)

h['o_contact'] = (h['contact'] - h['z_contact']).clip(lower=0)
h['o_contact_pct'] = (h['o_contact'] / h['o_swing'].clip(lower=1)).clip(0, 1)

h['rate_2b3b'] = ((h['b2'] + h['b3']) / h['pa'].clip(lower=1)).clip(lower=0)


def _spray_entropy(row):
    vals = [row.get('pull_pct'), row.get('cent_pct'), row.get('oppo_pct')]
    vals = [v for v in vals if pd.notna(v) and v > 0]
    if not vals:
        return np.nan
    s = sum(vals)
    return -sum((v / s) * np.log(v / s) for v in vals) if s else np.nan


h['spray_entropy'] = h.apply(_spray_entropy, axis=1)

h_co = cohort(h)
print(f"  cohort rows (PA>={PA_FLOOR}, years {YEARS}): {len(h_co)}")
print(f"  by year: {h_co.groupby('year').size().to_dict()}")

# Mirror sprint imputation in build_hitter_archetypes (fill NaN with year mean).
if h_co['sprint_speed'].notna().any():
    h_co['sprint_speed_filled'] = h_co['sprint_speed'].fillna(
        h_co.groupby('year')['sprint_speed'].transform('mean')
    )
else:
    h_co['sprint_speed_filled'] = np.nan

# ──────────────────────────────────────────────────────────────────────────────
# TEST A — YoY stability of the underlying RATE inputs (the r_* columns)
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("TEST A — YoY stability of underlying r_* rate inputs")
print("=" * 70)

A_METRICS = {
    'r_Contact (contact_pct)':         'contact_pct',
    'r_ZContact (z_contact_pct)':      'z_contact_pct',
    'r_OContact (o_contact_pct)':      'o_contact_pct',
    'r_K (k_pct)':                     'k_pct',
    'r_BABIP (babip)':                 'babip',
    'r_xCON (xwoba_on_contact)':       'xwoba_on_contact',
    'r_SprayEnt (spray_entropy)':      'spray_entropy',
    'r_Barrel (barrel_pct)':           'barrel_pct',
    'r_HardHit (hard_hit_pct)':        'hard_hit_pct',
    'r_SweetSpot (sweet_spot_pct)':    'sweet_spot_pct',
    'r_EV90 (ev90)':                   'ev90',
    'r_ISO (iso)':                     'iso',
    'r_HRrate (hr_per_pa)':            'hr_per_pa',
    'r_PullFB (pull_fb_pct)':          'pull_fb_pct',
    'r_BB (bb_pct)':                   'bb_pct',
    'r_Chase (chase_pct)':             'chase_pct',
    'r_ZSwing (z_swing_pct)':          'z_swing_pct',
    'r_HBP (hbp_pct)':                 'hbp_pct',
    'r_SBrate (sb_per_opp)':           'sb_per_opp',
    'r_Sprint (sprint_speed)':         'sprint_speed_filled',
}

a_results = []
for label, col in A_METRICS.items():
    if col not in h_co.columns:
        print(f"  {label:36s}  MISSING column {col}")
        continue
    sub = h_co[['batter', 'year', col]].dropna(subset=[col])
    pairs = yoy_pairs(sub, value_cols=[col])
    r, n = pearson_r(pairs[f'{col}_t'], pairs[f'{col}_tp1'])
    a_results.append({
        'metric': label, 'column': col, 'n_pairs': n,
        'r': round(r, 4) if not np.isnan(r) else None, 'verdict': verdict(r),
    })
    print(f"  {label:36s}  n={n:5d}  r={r:+.4f}  → {verdict(r)}")

a_df = pd.DataFrame(a_results)
a_df.to_csv(f"{OUT_DIR}/HITTER_VALIDATION_A_raw_inputs.csv", index=False)

# ──────────────────────────────────────────────────────────────────────────────
# TEST B — YoY stability of the 12 SUB-DOMAIN composite ratings
# Build them the same way build_hitter_archetypes.py does: each sub-domain
# is a (within-year) mean of underlying rates, then we test YoY r of that
# composite. We compute on the underlying RAW means (skip the 20-80 rescale —
# the rescale is monotonic within year, so Pearson r vs same monotonic
# rescale next year is identical to Pearson r on the raw means).
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("TEST B — YoY stability of the 12 sub-domain composites")
print("=" * 70)


def zscore_within_year(s, grouper):
    mu = grouper.transform('mean')
    sd = grouper.transform('std').replace(0, np.nan)
    return (s - mu) / sd


# Build year-scaled z-score versions of each input (mirrors rating_20_80 sans
# the 50+10z+clip, which is monotonic — Pearson is invariant to monotonic
# rescale within year, but the BETWEEN-year identity uses the same scale so
# we use z to make the "mean of components" composite well-defined).
g = h_co.groupby('year')
for col, invert in [
    ('contact_pct', False), ('z_contact_pct', False), ('o_contact_pct', False),
    ('k_pct', True), ('babip', False), ('xwoba_on_contact', False),
    ('spray_entropy', False),
    ('barrel_pct', False), ('hard_hit_pct', False), ('ev90', False),
    ('sweet_spot_pct', False), ('pull_fb_pct', False),
    ('iso', False), ('hr_per_pa', False),
    ('bb_pct', False), ('chase_pct', True), ('z_swing_pct', False), ('hbp_pct', False),
    ('sprint_speed_filled', False), ('sb_per_opp', False),
]:
    if col not in h_co.columns:
        continue
    z = zscore_within_year(h_co[col], g[col])
    if invert:
        z = -z
    h_co[f'z_{col}'] = z

# Sub-domain composites = mean of underlying z-scores (matches build script's
# rating_20_80 composition). For single-input subdomains, equivalent to the
# z-score itself.
SUBDOMAIN_INPUTS = {
    'Z_CONTACT':       ['z_z_contact_pct'],
    'O_CONTACT':       ['z_o_contact_pct'],
    'K_AVOIDANCE':     ['z_k_pct'],
    'CONTACT_QUALITY': ['z_xwoba_on_contact'],
    'SPRAY_PROFILE':   ['z_spray_entropy'],
    'RAW_POWER':       ['z_hard_hit_pct', 'z_barrel_pct', 'z_ev90'],
    'LAUNCH_OPTIM':    ['z_sweet_spot_pct', 'z_pull_fb_pct'],
    'DAMAGE_PROD':     ['z_iso', 'z_hr_per_pa'],
    'PATIENCE':        ['z_bb_pct', 'z_chase_pct', 'z_hbp_pct'],
    'AGGRESSION':      ['z_z_swing_pct'],
    'SPEED_TOOL':      ['z_sprint_speed_filled'],
    'SB_CONVERSION':   ['z_sb_per_opp'],
}

for sd, cols in SUBDOMAIN_INPUTS.items():
    present = [c for c in cols if c in h_co.columns]
    if not present:
        h_co[f'sd_{sd}'] = np.nan
    else:
        h_co[f'sd_{sd}'] = h_co[present].mean(axis=1)

b_results = []
for sd in SUBDOMAIN_INPUTS:
    col = f'sd_{sd}'
    sub = h_co[['batter', 'year', col]].dropna(subset=[col])
    pairs = yoy_pairs(sub, value_cols=[col])
    r, n = pearson_r(pairs[f'{col}_t'], pairs[f'{col}_tp1'])
    b_results.append({
        'subdomain': sd, 'inputs': '+'.join(SUBDOMAIN_INPUTS[sd]),
        'n_pairs': n, 'r': round(r, 4) if not np.isnan(r) else None,
        'verdict': verdict(r),
    })
    print(f"  {sd:18s} ({len(SUBDOMAIN_INPUTS[sd])} input)  n={n:5d}  r={r:+.4f}  → {verdict(r)}")

b_df = pd.DataFrame(b_results)
b_df.to_csv(f"{OUT_DIR}/HITTER_VALIDATION_B_subdomains.csv", index=False)

# ──────────────────────────────────────────────────────────────────────────────
# TEST C — Alternative metrics for any failing sub-domain
# Test plausible replacement signals so we have a recommendation.
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("TEST C — Alternative metrics for failing sub-domains")
print("=" * 70)

C_ALTS = {
    # Alternative SPRAY_PROFILE signals
    'ALT_SPRAY_pull_pct':       'pull_pct',
    'ALT_SPRAY_oppo_pct':       'oppo_pct',
    'ALT_SPRAY_pull_fb_pct':    'pull_fb_pct',   # already an input to LAUNCH_OPTIM, but as a standalone test
    # Alternative CONTACT_QUALITY signals
    'ALT_CONTACT_QUALITY_xwoba_bip': 'xwoba_bip',
    'ALT_CONTACT_QUALITY_avg_ev':    'avg_ev',
    # Alternative LAUNCH_OPTIM signals
    'ALT_LAUNCH_blast_rate':       'blast_rate',
    'ALT_LAUNCH_squared_up_rate':  'squared_up_rate',
    'ALT_LAUNCH_avg_swing_speed':  'avg_swing_speed',
    # SB_CONVERSION alternatives (in case it fails)
    'ALT_SB_sb_per_pa':           'sb_per_pa',
    # Reference / sanity: overall production
    'REF_xwoba_per_pa':          'xwoba_per_pa',
    'REF_fp_per_pa_actual':      'fp_per_pa_actual',
    # Additional bat-tracking that might compensate for failures
    'REF_avg_swing_speed':       'avg_swing_speed',
    'REF_blast_rate':            'blast_rate',
}

c_results = []
for label, col in C_ALTS.items():
    if col not in h_co.columns:
        print(f"  {label:38s}  MISSING column {col}")
        continue
    sub = h_co[['batter', 'year', col]].dropna(subset=[col])
    pairs = yoy_pairs(sub, value_cols=[col])
    r, n = pearson_r(pairs[f'{col}_t'], pairs[f'{col}_tp1'])
    c_results.append({
        'metric': label, 'column': col, 'n_pairs': n,
        'r': round(r, 4) if not np.isnan(r) else None, 'verdict': verdict(r),
    })
    print(f"  {label:38s}  n={n:5d}  r={r:+.4f}  → {verdict(r)}")

c_df = pd.DataFrame(c_results)
c_df.to_csv(f"{OUT_DIR}/HITTER_VALIDATION_C_alternatives.csv", index=False)

# ──────────────────────────────────────────────────────────────────────────────
# Bundle
# ──────────────────────────────────────────────────────────────────────────────
summary = {
    'cohort_floor': {'PA_min': PA_FLOOR, 'years': YEARS},
    'test_A_raw_inputs': a_results,
    'test_B_subdomains': b_results,
    'test_C_alternatives': c_results,
    'methodology': (
        'YoY Pearson r at batter-year level. Cohort: PA>=250 in BOTH year T and T+1. '
        'Bar: r>=0.40 KEEP, 0.20-0.40 MAYBE, <0.20 DROP. '
        '2020 excluded (COVID short season). 2026 excluded (in-progress). '
        'YoY pairs: 2018->2019, 2021->2022, 2022->2023, 2023->2024, 2024->2025.'
    ),
}
with open(f"{OUT_DIR}/HITTER_VALIDATION_summary.json", 'w') as fh:
    json.dump(summary, fh, indent=2, default=str)
print(f"\n[done] summary -> {OUT_DIR}/HITTER_VALIDATION_summary.json")

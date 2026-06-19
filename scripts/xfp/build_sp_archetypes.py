"""
build_sp_archetypes.py — daily build of SP 20-80 ratings + archetype labels +
trajectories + stickiness + comp panel.

Outputs (all written to data/research/):
  sp_ratings_master.csv               — 1,300+ pitcher-years 2015-2026 with full 20-80 ratings
  sp_archetype_career_panel.parquet   — same data + T+1/T+2 outcomes for comp matching
  sp_archetype_definitions.json       — 27 cell labels with descriptions
  sp_archetype_stickiness.json        — year-over-year retention rates per archetype
  sp_decline_signals.json             — historical decline-rate baselines and tested composites

Run as part of refresh_dashboards.py daily pipeline.
"""
from __future__ import annotations
import pandas as pd, numpy as np, json
from pathlib import Path
import pyarrow.parquet as pq

from plv_clone.paths import ROOT as REPO
HIST_CSV   = REPO / 'data/research/xfp_cache/sp_multiyr_2015_2025.csv'  # actually has 2015-2026
PITCH_DIR  = REPO / 'data/processed/pitch_features'                    # pitch-level parquets 2021-2026
AGE_CSV    = REPO / 'data/outputs/sp_age_career.csv'                    # pitcher / year / age / career_year
BIRTHDATE_CSV = REPO / 'data/research/xfp_cache/milb_pitcher_ages.csv' # birthDate fallback
OUT_DIR    = REPO / 'data/research'

# Pitch type groups (MLB Statcast pitch_type codes)
FB_TYPES = ['FF','FT','SI','FC']
SL_TYPES = ['SL','ST','SV']
CB_TYPES = ['CU','KC','CS','SC']
CH_TYPES = ['CH']
FS_TYPES = ['FS','FO']

# ──────────────────────────────────────────────────────────────────────────────
# 27 archetype cells (S/M/C bucket triple → label + description)
# ──────────────────────────────────────────────────────────────────────────────
ARCHETYPES = {
    'PLUS/PLUS/PLUS':    ('MT_RUSHMORE',          'Triple-plus elite: Kershaw 15-16, Skubal 24, deGrom 18'),
    'PLUS/PLUS/AVG':     ('STUFF_PLUS_MOVE',      'High K + HR suppression: Burnes 21, Sale 24, Arrieta 15'),
    'PLUS/PLUS/MINUS':   ('STUFF_MOVE_WILD',      'High K + HR suppress, wild: Snell 24, Castillo 19'),
    'PLUS/AVG/PLUS':     ('STUFF_PLUS_CTRL',      'High K + plus control: Scherzer, Cole peak, Skubal'),
    'PLUS/AVG/AVG':      ('PURE_STUFF',           'K-driven, avg rest: Strider 23, Glasnow, Soriano 26'),
    'PLUS/AVG/MINUS':    ('WILD_FIREBALLER',      'High K + walk problems: Snell, McClanahan, Cease 22'),
    'PLUS/MINUS/PLUS':   ('K_AND_CTRL_HR_RISK',   'K+control, HR-prone: rare'),
    'PLUS/MINUS/AVG':    ('STUFF_NO_MOVE',        'K but HR risk: 2019 Cole style'),
    'PLUS/MINUS/MINUS':  ('PURE_STUFF_LIABILITY', 'High K only, walk+HR risk: Greene 22, Ragans 26'),
    'AVG/PLUS/PLUS':     ('MOVE_CTRL_ACE',        'Sinker-control elite: Hendricks, Greinke aging, Skenes 26'),
    'AVG/PLUS/AVG':      ('PURE_MOVEMENT',        'GB/HR-suppress: Arrieta, Alcantara 22, Fried 22'),
    'AVG/PLUS/MINUS':    ('MOVE_WILD',            'Movement without command: Arrieta 16, Greene 24'),
    'AVG/AVG/PLUS':      ('PURE_CONTROL',         'Walk-avoidance specialist: Verlander 22, Woo 25, Bassitt'),
    'AVG/AVG/AVG':       ('AVERAGE_4_5',          'Generic mid-rotation — most common archetype'),
    'AVG/AVG/MINUS':     ('WILD_MID',             'Mediocre + walks: Senga 23, Blanco 24, Gore'),
    'AVG/MINUS/PLUS':    ('CTRL_HR_PRONE',        'Control without movement: Imanaga 25, Fiers 18'),
    'AVG/MINUS/AVG':     ('GENERIC_HR_PRONE',     'Avg stuff, HR-prone: Kennedy 16, Rodón 24'),
    'AVG/MINUS/MINUS':   ('BAD_BIG_INNINGS',      'No suppression, walks: Archer 19, Gray 22'),
    'MINUS/PLUS/PLUS':   ('SOFT_TOSS_ARTIST',     'Low K, plus move/control: Keuchel-lite'),
    'MINUS/PLUS/AVG':    ('SINKER_ONLY',          'Pure GB pitcher, no K'),
    'MINUS/PLUS/MINUS':  ('SINKER_WILD',          'Pure GB + walks'),
    'MINUS/AVG/PLUS':    ('JUNKBALLER',           'Low K, avg move, plus control: Colon 16, Cueto 22, McGreevy 26'),
    'MINUS/AVG/AVG':     ('FILLER',               'Below-K average rest: Leake, Williams 18, Fedde 26'),
    'MINUS/AVG/MINUS':   ('LIABILITY',            'Below-K + walks: Rodón 18, Keller 19'),
    'MINUS/MINUS/PLUS':  ('PIT_CHF_CTRL',         'Control-only, gets hit hard: Paddack 25, Hughes 15'),
    'MINUS/MINUS/AVG':   ('PIT_CHF',              'Below-K, HR-prone: Gonsolin 23, Heaney 25'),
    'MINUS/MINUS/MINUS': ('FRINGE',               'Below everything'),
}

# Sample-stability floor (K% stabilizes at ~70 TBF ≈ 6 starts; below this, ratings
# are dominated by single-game noise). All years use the same RATED floor so rookies
# and mid-season call-ups are visible. FULL tier flags 20+ GS as the durable cut.
GS_FLOOR_RATED = 6
GS_FLOOR_FULL = 20


# Shared 20-80 scouting helpers live in the archetype_engine toolkit.
import sys as _sys
_sys.path.insert(0, str(REPO))
from scripts.xfp.lib.archetype_engine import (  # noqa: E402
    rating_20_80, bucket, boundary_distance, boundary_tier_label,
    age_tier as _eng_age_tier,
)


def stuff_subtype(row):
    """K_DRIVEN / WHIFF_LED / CSW_LED / BALANCED based on component spread."""
    vals = {'K_DRIVEN': row['r_K'], 'WHIFF_LED': row['r_SwStr'], 'CSW_LED': row['r_CSW']}
    if max(vals.values()) - min(vals.values()) < 8:
        return 'BALANCED'
    return max(vals, key=vals.get)


def velo_tier(row):
    """POWER (velo>=60) / BALANCED (40-59) / FINESSE (<40) — qualifier on STUFF dimension.
    Tested 2026-05-28: velo partial r vs FP after S+M+C control = +0.065 (small but real).
    Insufficient for 4th domain; useful as a stuff sub-classifier."""
    v = row.get('velo_rating', 50)
    if v >= 60: return 'POWER'
    if v >= 40: return 'BALANCED'
    return 'FINESSE'


def age_tier(age):
    """SPs peak ~1 year later than hitters; age-matched comps reduce T+1 FP/s
    MAE ~4% (2026-05-28, n=440)."""
    return _eng_age_tier(age, pre_max=26, peak_max=31)


def attach_age(qual):
    """Merge age data from sp_age_career.csv with birthdate fallback for missing rows."""
    if AGE_CSV.exists():
        ages = pd.read_csv(AGE_CSV)
        qual = qual.merge(ages[['pitcher', 'year', 'age', 'career_year']],
                          on=['pitcher', 'year'], how='left')
    else:
        qual['age'] = np.nan
        qual['career_year'] = np.nan

    # Birthdate fallback for missing-age rows (typically 2026 callups)
    missing = qual['age'].isna().sum()
    if missing > 0 and BIRTHDATE_CSV.exists():
        bd = pd.read_csv(BIRTHDATE_CSV)
        bd['birthDate'] = pd.to_datetime(bd['birthDate'], errors='coerce')
        bd_map = dict(zip(bd['pitcher'], bd['birthDate']))

        def derive(row):
            if pd.notna(row['age']):
                return row['age']
            d = bd_map.get(row['pitcher'])
            if pd.notna(d):
                return int(row['year']) - d.year - (1 if d.month > 6 else 0)
            return np.nan
        qual['age'] = qual.apply(derive, axis=1)

    qual['age_tier'] = qual['age'].apply(age_tier)
    return qual


def build_pitch_arsenal(years=(2021, 2022, 2023, 2024, 2025, 2026)):
    """Aggregate pitch-type usage per (pitcher, year) from pitch_features parquets.
    Returns DataFrame with primary_group, secondary_group, pitch_archetype, arsenal_entropy.
    Coverage: 2021+ only (parquet files start in 2021)."""
    dfs = []
    for yr in years:
        files = list((PITCH_DIR / f'year={yr}').glob('*.parquet'))
        if not files:
            continue
        t = pq.read_table(str(files[0]), columns=['pitcher', 'pitch_type']).to_pandas()
        t['year'] = yr
        dfs.append(t)

    if not dfs:
        return pd.DataFrame(columns=['pitcher','year','primary_group','secondary_group','pitch_archetype','arsenal_entropy'])

    pitches = pd.concat(dfs, ignore_index=True)
    agg = (pitches.dropna(subset=['pitch_type'])
           .groupby(['pitcher','year','pitch_type'])
           .size().reset_index(name='count'))
    total = agg.groupby(['pitcher','year'])['count'].sum().reset_index(name='total')
    agg = agg.merge(total, on=['pitcher','year'])
    agg['pct'] = agg['count'] / agg['total']

    pivot = agg.pivot_table(index=['pitcher','year'], columns='pitch_type',
                            values='pct', fill_value=0).reset_index()

    def get_pct(row, types):
        return sum(row.get(t, 0) for t in types)

    pivot['FB_pct'] = pivot.apply(lambda r: get_pct(r, FB_TYPES), axis=1)
    pivot['SL_pct'] = pivot.apply(lambda r: get_pct(r, SL_TYPES), axis=1)
    pivot['CB_pct'] = pivot.apply(lambda r: get_pct(r, CB_TYPES), axis=1)
    pivot['CH_pct'] = pivot.apply(lambda r: get_pct(r, CH_TYPES), axis=1)
    pivot['FS_pct'] = pivot.apply(lambda r: get_pct(r, FS_TYPES), axis=1)

    pcts = ['FB_pct','SL_pct','CB_pct','CH_pct','FS_pct']
    pivot['primary_pct']   = pivot[pcts].max(axis=1)
    pivot['primary_group'] = pivot[pcts].idxmax(axis=1).str.replace('_pct','')

    def second_group(row):
        vals = [(row['FB_pct'],'FB'),(row['SL_pct'],'SL'),(row['CB_pct'],'CB'),
                (row['CH_pct'],'CH'),(row['FS_pct'],'FS')]
        vals.sort(reverse=True)
        return vals[1][1] if vals[1][0] > 0.10 else None
    pivot['secondary_group'] = pivot.apply(second_group, axis=1)

    def entropy(row):
        ps = [row[c] for c in pcts if row[c] > 0.01]
        return -sum(p * np.log2(p) for p in ps) if ps else 0
    pivot['arsenal_entropy'] = pivot.apply(entropy, axis=1)

    def pitch_arch(row):
        pri = row['primary_group']; sec = row['secondary_group']
        if row['primary_pct'] >= 0.55:
            return f'{pri}_HEAVY'
        if pd.isna(sec) or sec == pri:
            return f'{pri}_LED'
        return f'{pri}_{sec}'
    pivot['pitch_archetype'] = pivot.apply(pitch_arch, axis=1)

    return pivot[['pitcher','year','primary_group','secondary_group','primary_pct',
                  'arsenal_entropy','pitch_archetype',
                  'FB_pct','SL_pct','CB_pct','CH_pct','FS_pct']]


def build_ratings_panel(current_year=2026):
    """Build the full 2015-current panel with 20-80 ratings + archetype labels."""
    m = pd.read_csv(HIST_CSV)
    m['hr_per_bf'] = m['hr'] / m['tbf'].clip(lower=1)

    # Apply GS floor: every year uses the sample-stability floor so debutants
    # and mid-season call-ups are visible. data_tier flags durable vs partial.
    qual = m[m['gs'] >= GS_FLOOR_RATED].copy()
    qual = qual[qual['year'] != 2020]  # exclude COVID short season
    qual['data_tier'] = np.where(qual['gs'] >= GS_FLOOR_FULL, 'FULL', 'PARTIAL')
    qual['zone_pct'] = qual['in_zone'] / qual['pitches'].clip(lower=1)

    g = qual.groupby('year')

    # STUFF components (3): K%, SwStr%, CSW%
    qual['r_K']     = rating_20_80(qual['k_pct'],         g['k_pct']).round(0).astype(int)
    qual['r_SwStr'] = rating_20_80(qual['swstr_pct'],     g['swstr_pct']).round(0).astype(int)
    qual['r_CSW']   = rating_20_80(qual['c_plus_swstr'],  g['c_plus_swstr']).round(0).astype(int)

    # MOVEMENT components (5): HR/BF, Barrel%, HardHit%, GB%, xwOBA-contact
    qual['r_HRrate']   = rating_20_80(qual['hr_per_bf'],     g['hr_per_bf'],     invert=True).round(0).astype(int)
    qual['r_Barrel']   = rating_20_80(qual['barrel_pct'],    g['barrel_pct'],    invert=True).round(0).astype(int)
    qual['r_HardHit']  = rating_20_80(qual['hard_hit_pct'],  g['hard_hit_pct'],  invert=True).round(0).astype(int)
    qual['r_GB']       = rating_20_80(qual['gb_pct'],        g['gb_pct']).round(0).astype(int)
    qual['r_xCON']     = rating_20_80(qual['xwoba_contact'], g['xwoba_contact'], invert=True).round(0).astype(int)

    # CONTROL components (1): BB%
    qual['r_BB'] = rating_20_80(qual['bb_pct'], g['bb_pct'], invert=True).round(0).astype(int)
    qual['r_ZonePct'] = rating_20_80(qual['zone_pct'], g['zone_pct']).round(0).astype(int)

    # Sub-domain ratings — computed FIRST. Each is the simple mean of its
    # components, then re-rated 20-80 within year. Domains below are then
    # empirically-weighted sums of these sub-domain ratings.
    qual['_SWING_MISS_raw']    = qual[['r_SwStr','r_K']].mean(axis=1)
    qual['_CALLED_STRIKE_raw'] = qual['r_CSW']
    qual['_DAMAGE_SUPP_raw']   = qual[['r_HRrate','r_Barrel','r_HardHit','r_xCON']].mean(axis=1)
    qual['_GB_TENDENCY_raw']   = qual['r_GB']
    qual['_WALK_AVOID_raw']    = qual['r_BB']
    qual['_STRIKE_THROWING_raw'] = qual['r_ZonePct']
    g_sub = qual.groupby('year')
    qual['SWING_MISS']    = rating_20_80(qual['_SWING_MISS_raw'],    g_sub['_SWING_MISS_raw']).round(0).astype(int)
    qual['CALLED_STRIKE'] = rating_20_80(qual['_CALLED_STRIKE_raw'], g_sub['_CALLED_STRIKE_raw']).round(0).astype(int)
    qual['DAMAGE_SUPP']   = rating_20_80(qual['_DAMAGE_SUPP_raw'],   g_sub['_DAMAGE_SUPP_raw']).round(0).astype(int)
    qual['GB_TENDENCY']   = rating_20_80(qual['_GB_TENDENCY_raw'],   g_sub['_GB_TENDENCY_raw']).round(0).astype(int)
    qual['WALK_AVOID']    = rating_20_80(qual['_WALK_AVOID_raw'],    g_sub['_WALK_AVOID_raw']).round(0).astype(int)
    qual['STRIKE_THROWING'] = rating_20_80(qual['_STRIKE_THROWING_raw'], g_sub['_STRIKE_THROWING_raw']).round(0).astype(int)
    qual = qual.drop(columns=['_SWING_MISS_raw','_CALLED_STRIKE_raw','_DAMAGE_SUPP_raw','_GB_TENDENCY_raw','_WALK_AVOID_raw','_STRIKE_THROWING_raw'])

    # Domain composites — empirically-weighted sums of sub-domain ratings,
    # re-rated to 20-80 within year. Weights from OLS regression of
    # fp_per_start on sub-domain ratings (FULL pool n=1,205):
    #   STUFF    = 0.628 SWING_MISS  + 0.372 CALLED_STRIKE  (rounded 0.65/0.35)
    #   MOVEMENT = 0.837 DAMAGE_SUPP + 0.163 GB_TENDENCY    (rounded 0.85/0.15)
    #   CONTROL  = 1.00 WALK_AVOID
    g2 = qual.groupby('year')
    qual['_STUFF_raw']    = 0.65 * qual['SWING_MISS']  + 0.35 * qual['CALLED_STRIKE']
    qual['_MOVEMENT_raw'] = 0.85 * qual['DAMAGE_SUPP'] + 0.15 * qual['GB_TENDENCY']
    qual['STUFF']    = rating_20_80(qual['_STUFF_raw'],    g2['_STUFF_raw']).round(0).astype(int)
    qual['MOVEMENT'] = rating_20_80(qual['_MOVEMENT_raw'], g2['_MOVEMENT_raw']).round(0).astype(int)
    # CONTROL now has 2 sub-domains. Empirical weights from OLS:
    #   WALK_AVOID 0.893 / STRIKE_THROWING 0.107 — rounded.
    qual['_CONTROL_raw'] = 0.90 * qual['WALK_AVOID'] + 0.10 * qual['STRIKE_THROWING']
    qual['CONTROL'] = rating_20_80(qual['_CONTROL_raw'], qual.groupby('year')['_CONTROL_raw']).round(0).astype(int)
    qual = qual.drop(columns=['_STUFF_raw','_MOVEMENT_raw','_CONTROL_raw'])

    # Overall composite — weighted mean of the three archetype-driving domains,
    # then re-rated within year to a clean 20-80 distribution. Weights derived
    # from OLS regression of fp_per_start ~ STUFF + MOVEMENT + CONTROL on the
    # FULL-tier pool. Refit after dropping r_GB from MOVEMENT composite.
    # New empirical 0.47/0.36/0.17 (R²=0.75) on FULL-tier n=1,205 — rounded
    # weights unchanged.
    # Velo intentionally excluded (sub-classifier, not part of archetype identity).
    OVERALL_W = {'STUFF': 0.50, 'MOVEMENT': 0.35, 'CONTROL': 0.15}
    qual['_OVERALL_raw'] = (qual['STUFF']    * OVERALL_W['STUFF']
                          + qual['MOVEMENT'] * OVERALL_W['MOVEMENT']
                          + qual['CONTROL']  * OVERALL_W['CONTROL'])
    qual['OVERALL'] = rating_20_80(qual['_OVERALL_raw'],
                                    qual.groupby('year')['_OVERALL_raw']).round(0).astype(int)
    qual = qual.drop(columns=['_OVERALL_raw'])

    # Velocity rating (sub-classifier within STUFF; not a 4th domain)
    qual['velo_rating'] = rating_20_80(qual['avg_velo'], g['avg_velo']).round(0).astype(int)
    qual['velo_tier'] = qual.apply(velo_tier, axis=1)

    # Age + age tier (added 2026-05-28)
    qual = attach_age(qual)

    # Boundary distance per domain + min + tier (added 2026-05-28)
    qual['bd_S'] = qual['STUFF'].apply(boundary_distance)
    qual['bd_M'] = qual['MOVEMENT'].apply(boundary_distance)
    qual['bd_C'] = qual['CONTROL'].apply(boundary_distance)
    qual['boundary_distance'] = qual[['bd_S', 'bd_M', 'bd_C']].min(axis=1)
    qual['boundary_tier'] = qual['boundary_distance'].apply(boundary_tier_label)

    # Cells + archetype labels
    qual['cell'] = qual['STUFF'].apply(bucket) + '/' + qual['MOVEMENT'].apply(bucket) + '/' + qual['CONTROL'].apply(bucket)
    qual['archetype'] = qual['cell'].map(lambda x: ARCHETYPES.get(x, ('UNKNOWN', '-'))[0])
    qual['stuff_subtype'] = qual.apply(stuff_subtype, axis=1)

    # Within-year FP rank
    qual['fp_per_start'] = qual['fp_per_start_actual']
    # Use a fresh groupby on current qual — attach_age() above can reshape row indices
    # and the original `g` becomes stale, producing NaN ranks after assignment.
    qual['rank_in_year'] = qual.groupby('year')['fp_per_start_actual'].rank(ascending=False, method='min')

    # T+1 FP projection — linear model + SWING_MISS × WALK_AVOID interaction.
    # Refit 2026-05-28 with the interaction term (E test): R² 0.358 → 0.414.
    # Main effects on SWING_MISS and WALK_AVOID go slightly negative because
    # the interaction absorbs the bulk of the "elite stuff with control" signal.
    T1_SP_INTERCEPT = 5.67540
    T1_SP_BETAS = {
        'SWING_MISS':    -0.02019,
        'CALLED_STRIKE':  0.03617,
        'DAMAGE_SUPP':    0.02963,
        'GB_TENDENCY':   -0.00145,
        'WALK_AVOID':    -0.10736,
        'velo_rating':    0.03779,
        'age':           -0.05181,
    }
    T1_SP_INTERACTION = 0.00314  # SWING_MISS × WALK_AVOID
    qual['t1_fp_proj_raw'] = T1_SP_INTERCEPT + sum(
        qual[k].fillna(50) * v for k, v in T1_SP_BETAS.items()
    ) + T1_SP_INTERACTION * qual['SWING_MISS'].fillna(50) * qual['WALK_AVOID'].fillna(50)
    qual['t1_fp_projection'] = qual['t1_fp_proj_raw'].clip(lower=2.0, upper=22.0).round(2)
    qual = qual.drop(columns=['t1_fp_proj_raw'])

    # T+2 FP projection — linear (no interaction tested; not enough sample).
    # Sample n=290 from FULL pool. R² = 0.39 (close to T+1). For dynasty/keeper.
    # SWING_MISS dominates (+0.15); age coefficient is sharper at T+2 (-0.15
    # vs T+1's -0.05) — confirms age dominates longer horizons.
    T2_SP_INTERCEPT = -0.59491
    T2_SP_BETAS = {
        'SWING_MISS':    0.15162,
        'CALLED_STRIKE': 0.02281,
        'DAMAGE_SUPP':   0.04651,
        'GB_TENDENCY':   0.00427,
        'WALK_AVOID':    0.03159,
        'velo_rating':   0.05569,
        'age':          -0.14705,
    }
    qual['t2_fp_proj_raw'] = T2_SP_INTERCEPT + sum(
        qual[k].fillna(50) * v for k, v in T2_SP_BETAS.items()
    )
    qual['t2_fp_projection'] = qual['t2_fp_proj_raw'].clip(lower=2.0, upper=22.0).round(2)
    qual = qual.drop(columns=['t2_fp_proj_raw'])

    # Trajectory alerts — 3-year OVERALL slope + career percentile.
    # Slope = linear-regression slope of OVERALL on year over the last 3 seasons
    # (including current). Career percentile = where current OVERALL sits within
    # this player's own historical distribution.
    idkey = 'pitcher'
    qual_sorted = qual.sort_values([idkey, 'year'])[[idkey, 'year', 'OVERALL']].copy()

    def _trajectory_metrics(group):
        g = group.sort_values('year').reset_index(drop=True)
        g['OVERALL_slope_3yr'] = np.nan
        g['OVERALL_career_pct'] = np.nan
        for i in range(len(g)):
            # Slope from last 3 (or fewer) seasons up to and including current
            window = g.iloc[max(0, i-2):i+1]
            if len(window) >= 2 and window['year'].max() - window['year'].min() >= 1:
                slope = np.polyfit(window['year'].values, window['OVERALL'].values, 1)[0]
                g.loc[g.index[i], 'OVERALL_slope_3yr'] = slope
            # Career percentile: where current overall sits in player's history (inclusive)
            career = g.iloc[:i+1]['OVERALL']
            g.loc[g.index[i], 'OVERALL_career_pct'] = (career < g.loc[g.index[i], 'OVERALL']).sum() / len(career)
        return g

    qual_sorted = qual_sorted.groupby(idkey, group_keys=False)[[idkey, 'year', 'OVERALL']].apply(_trajectory_metrics)
    qual_sorted['OVERALL_slope_3yr'] = qual_sorted['OVERALL_slope_3yr'].round(2)
    qual_sorted['OVERALL_career_pct'] = qual_sorted['OVERALL_career_pct'].round(3)

    # Trajectory flag
    def _traj_flag(row):
        s = row['OVERALL_slope_3yr']
        p = row['OVERALL_career_pct']
        if pd.notna(s) and s >= 3.0: return 'TRENDING_UP'
        if pd.notna(s) and s <= -3.0: return 'TRENDING_DOWN'
        if pd.notna(p) and p >= 0.90: return 'CAREER_HIGH'
        if pd.notna(p) and p <= 0.10: return 'CAREER_LOW'
        return 'STABLE'
    qual_sorted['traj_flag'] = qual_sorted.apply(_traj_flag, axis=1)

    # Merge back into qual (preserve row order)
    qual = qual.merge(
        qual_sorted[[idkey, 'year', 'OVERALL_slope_3yr', 'OVERALL_career_pct', 'traj_flag']],
        on=[idkey, 'year'], how='left'
    )

    return qual


def compute_stickiness(qual):
    """Year-over-year retention rate per archetype + age-tier breakdown."""
    careers = qual.sort_values(['pitcher', 'year']).reset_index(drop=True)
    careers['next_arch'] = careers.groupby('pitcher')['archetype'].shift(-1)
    careers['next_year'] = careers.groupby('pitcher')['year'].shift(-1)
    careers['next_fp']   = careers.groupby('pitcher')['fp_per_start'].shift(-1)
    careers['year_gap']  = careers['next_year'] - careers['year']
    current_year = int(qual['year'].max())
    trans = careers[(careers['year_gap'] == 1) & (careers['next_year'] != current_year)]

    out = {}
    for arch in qual['archetype'].unique():
        sub = trans[trans['archetype'] == arch]
        if len(sub) < 8: continue
        n_total = len(sub)
        n_stick = int((sub['next_arch'] == arch).sum())
        top_to = sub['next_arch'].value_counts().head(3).to_dict()
        entry = {
            'n_total_transitions': n_total,
            'n_stayed': n_stick,
            'retention_pct': round(100 * n_stick / n_total, 1),
            'top_destinations': [[k, int(v), round(100 * v / n_total, 1)] for k, v in top_to.items()],
            'fp_if_stayed': round(float(sub[sub['next_arch'] == arch]['next_fp'].mean()), 2),
            'fp_if_left':   round(float(sub[sub['next_arch'] != arch]['next_fp'].mean()), 2),
            'by_age_tier': {},
        }
        # Per age tier
        for tier in ['PRE_PEAK', 'PEAK', 'POST_PEAK']:
            sub_t = sub[sub['age_tier'] == tier]
            if len(sub_t) < 5: continue
            ret = float((sub_t['next_arch'] == arch).mean())
            entry['by_age_tier'][tier] = {
                'n': int(len(sub_t)),
                'retention_pct': round(100 * ret, 1),
            }
        out[arch] = entry
    return out


def compute_decline_baselines(qual):
    """Decline-rate baselines for context (not actionable signal — see calibration notes)."""
    careers = qual.sort_values(['pitcher','year']).reset_index(drop=True)
    arch_q = qual.groupby('archetype')['fp_per_start'].mean()
    careers['arch_q'] = careers['archetype'].map(arch_q)
    careers['next_fp'] = careers.groupby('pitcher')['fp_per_start'].shift(-1)
    careers['next_arch_q'] = careers.groupby('pitcher')['arch_q'].shift(-1)
    careers['next_year'] = careers.groupby('pitcher')['year'].shift(-1)
    valid = careers[careers['next_year'] == careers['year'] + 1]

    # Baseline: overall T+1 decline rate
    decline_mask = (valid['next_fp'] - valid['fp_per_start'] <= -3) | \
                   (valid['next_arch_q'] - valid['arch_q'] <= -2)
    base = float(decline_mask.mean())
    elite = valid[valid['fp_per_start'] >= 14]
    elite_decline = float(((elite['next_fp'] - elite['fp_per_start'] <= -3) |
                           (elite['next_arch_q'] - elite['arch_q'] <= -2)).mean())

    return {
        'all_t_plus_1_decline_rate': round(base, 3),
        'elite_t_plus_1_decline_rate': round(elite_decline, 3),
        'methodology_note': (
            'Pre-decline process drops (STUFF/velo/SwStr decreases at year T) actually correlate '
            'with LOWER T+1 decline rate, not higher — mean reversion already absorbed. '
            'Elite tier (FP/s>=14) has 59% T+1 decline baseline regardless of process indicators. '
            'Use elite_decline_rate as base-rate context, not as an actionable alert.'
        ),
    }


def build_career_panel(qual):
    """Add T+1 / T+2 outcomes for comp matching."""
    careers = qual.sort_values(['pitcher', 'year']).reset_index(drop=True)
    careers['next_fp']    = careers.groupby('pitcher')['fp_per_start'].shift(-1)
    careers['next_arch']  = careers.groupby('pitcher')['archetype'].shift(-1)
    careers['next_year']  = careers.groupby('pitcher')['year'].shift(-1)
    careers['t2_fp']      = careers.groupby('pitcher')['fp_per_start'].shift(-2)
    careers['t2_year']    = careers.groupby('pitcher')['year'].shift(-2)

    # Pretty display name
    careers['name'] = careers['player_name'].apply(
        lambda s: s.split(',',1)[1].strip()+' '+s.split(',',1)[0].strip() if isinstance(s,str) and ',' in s else s
    )
    return careers


def main():
    print('Building SP archetype panel...', flush=True)
    qual = build_ratings_panel()
    print(f'  panel: {len(qual)} pitcher-years, {qual["pitcher"].nunique()} unique pitchers', flush=True)

    # Build & merge pitch arsenal (2021+ only)
    print('Building pitch-arsenal data (2021+)...', flush=True)
    arsenal = build_pitch_arsenal()
    qual = qual.merge(arsenal, on=['pitcher','year'], how='left')
    n_arsenal = qual['pitch_archetype'].notna().sum()
    print(f'  arsenal joined: {n_arsenal} of {len(qual)} pitcher-years have pitch data', flush=True)

    # Master ratings CSV (human-readable)
    master_cols = ['year','rank_in_year','pitcher','player_name','gs','tbf','fp_per_start','t1_fp_projection','t2_fp_projection','data_tier',
                   'OVERALL','OVERALL_slope_3yr','OVERALL_career_pct','traj_flag',
                   'STUFF','MOVEMENT','CONTROL',
                   'SWING_MISS','CALLED_STRIKE','DAMAGE_SUPP','GB_TENDENCY','WALK_AVOID','STRIKE_THROWING',
                   'archetype','stuff_subtype','cell',
                   'velo_rating','velo_tier','pitch_archetype','primary_group','secondary_group',
                   'age','age_tier','career_year',
                   'bd_S','bd_M','bd_C','boundary_distance','boundary_tier',
                   'r_K','r_SwStr','r_CSW','r_HRrate','r_Barrel','r_HardHit','r_GB','r_xCON','r_BB','r_ZonePct',
                   'k_pct','bb_pct','hr_per_bf','swstr_pct','c_plus_swstr','xwoba_contact',
                   'barrel_pct','hard_hit_pct','gb_pct','avg_velo','zone_pct',
                   'FB_pct','SL_pct','CB_pct','CH_pct','FS_pct','arsenal_entropy']
    master = qual[master_cols].sort_values(['year','rank_in_year']).copy()
    master['fp_per_start'] = master['fp_per_start'].round(2)
    for col, factor, prec in [('k_pct',100,1),('bb_pct',100,1),('hr_per_bf',100,2),
                               ('swstr_pct',100,1),('c_plus_swstr',100,1),('xwoba_contact',1,3),
                               ('barrel_pct',100,1),('hard_hit_pct',100,1),('gb_pct',100,1),('avg_velo',1,1),
                               ('zone_pct',100,1)]:
        master[col] = (master[col] * factor).round(prec)
    for col in ['FB_pct','SL_pct','CB_pct','CH_pct','FS_pct']:
        master[col] = (master[col] * 100).round(1)
    master['arsenal_entropy'] = master['arsenal_entropy'].round(2)
    master.to_csv(OUT_DIR / 'sp_ratings_master.csv', index=False, encoding='utf-8')
    print(f'  wrote sp_ratings_master.csv', flush=True)

    # Career panel for comps
    careers = build_career_panel(qual)
    careers.to_parquet(OUT_DIR / 'sp_archetype_career_panel.parquet', index=False)
    print('  wrote sp_archetype_career_panel.parquet', flush=True)

    # Definitions
    defs = {k: {'label': v[0], 'description': v[1]} for k, v in ARCHETYPES.items()}
    with open(OUT_DIR / 'sp_archetype_definitions.json', 'w', encoding='utf-8') as f:
        json.dump(defs, f, indent=2)
    print('  wrote sp_archetype_definitions.json', flush=True)

    # Stickiness
    stick = compute_stickiness(qual)
    with open(OUT_DIR / 'sp_archetype_stickiness.json', 'w', encoding='utf-8') as f:
        json.dump(stick, f, indent=2)
    print(f'  wrote sp_archetype_stickiness.json ({len(stick)} archetypes)', flush=True)

    # Decline baselines
    decl = compute_decline_baselines(qual)
    with open(OUT_DIR / 'sp_decline_baselines.json', 'w', encoding='utf-8') as f:
        json.dump(decl, f, indent=2)
    print('  wrote sp_decline_baselines.json', flush=True)

    # Boundary tier validation stats (for SKILL to reference)
    careers = qual.sort_values(['pitcher', 'year']).reset_index(drop=True)
    careers['next_arch'] = careers.groupby('pitcher')['archetype'].shift(-1)
    careers['next_year'] = careers.groupby('pitcher')['year'].shift(-1)
    current = int(qual['year'].max())
    trans = careers[(careers['next_year'] == careers['year'] + 1) &
                    (careers['next_year'] != current)].copy()
    trans['stayed'] = (trans['archetype'] == trans['next_arch']).astype(int)
    boundary_stats = {}
    for tier in ['EDGE', 'NEAR_EDGE', 'SOLID']:
        sub = trans[trans['boundary_tier'] == tier]
        if len(sub) >= 10:
            boundary_stats[tier] = {
                'n_transitions': int(len(sub)),
                'retention_pct': round(100 * float(sub['stayed'].mean()), 1),
            }
    with open(OUT_DIR / 'sp_boundary_validation.json', 'w', encoding='utf-8') as f:
        json.dump(boundary_stats, f, indent=2)
    print('  wrote sp_boundary_validation.json', flush=True)

    print('\nDone.', flush=True)


if __name__ == '__main__':
    main()

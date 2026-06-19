"""
build_rp_archetypes.py — daily build of RP 20-80 ratings + archetype labels +
trajectories + stickiness + comp panel. RP analog of build_sp_archetypes.py.

Outputs (all written to data/research/):
  rp_ratings_master.csv             — RP-years 2017-2026 (ex-2020) with full 20-80 ratings
  rp_archetype_career_panel.parquet — same data + T+1/T+2 outcomes for comp matching
  rp_archetype_definitions.json     — 27 cell labels with descriptions
  rp_archetype_stickiness.json      — year-over-year retention rates per archetype
  rp_decline_baselines.json         — historical decline-rate baselines
  rp_boundary_validation.json       — boundary tier retention stats

Validated sub-domain inputs (YoY r per RP_SUBDOMAIN_VALIDATION.md):
  VELO          r=0.93   relievers_multiyr.avg_velo
  GB_TENDENCY   r=0.71   rp_damage_gb_2018_2026.gb_pct (statcast-derived)
  SWING_MISS    r=0.63   relievers_multiyr.swstr_pct
  CALLED_STRIKE r=0.61   relievers_multiyr.called_strike / pitches
  BULK_IP       r=0.47   relievers_multiyr.ip / g
  WALK_AVOID    r=0.44   relievers_multiyr.bb_pct (inverted)

DAMAGE_SUPP (xwoba_contact / barrel_pct) FAILED YoY validation (r=0.12-0.20)
and is NOT a rated sub-domain. barrel_pct / hard_hit_pct / xwobacon are
included as display columns only.

Empirical OLS findings (n=2,087 RP-years 2018-2026, ex-2020):
  fp_per_g ~ 6 sub-domains: R²=0.475
    SWING_MISS β=+0.59 (dominant), CALLED_STRIKE β=+0.32,
    BULK_IP β=+0.28, WALK_AVOID β=+0.24, VELO β=+0.20, GB_TENDENCY β=+0.01

Domain composition (chosen 2026-05-28):
  STUFF       = 0.85 SWING_MISS  + 0.15 VELO
  CONTROL     = 0.85 WALK_AVOID  + 0.15 CALLED_STRIKE
  BATTED_BALL = 0.50 GB_TENDENCY + 0.50 BULK_IP

NOTE on BATTED_BALL: empirical regression on fp_per_g gives GB_TENDENCY
near-zero weight (β=-0.001) — a GB-heavy reliever does NOT out-fp a K-heavy
one. But GB_TENDENCY YoY r=0.71 confirms it's a real, stable skill axis
(canonical sinkerballer identity). We use 0.50/0.50 within BATTED_BALL
rather than 0.10/0.90 because the domain exists for archetype identity, not
solely for fp prediction — the same way the SP build keeps GB_TENDENCY for
identity even though SwingMiss carries most of the fp signal.

T+1 / T+2 RP fp_per_g R² (n=927 T+1 pairs, n=380 T+2 triplets):
  T+1: R²=0.246
  T+2: R²=0.259
RP outcomes are inherently noisier than SP (SP T+1 = 0.41) because of low
RP TBF per season — accept this.

Run as part of refresh_dashboards.py daily pipeline (Phase 2 — not wired yet).
"""
from __future__ import annotations
import pandas as pd
import numpy as np
import json
from pathlib import Path

from plv_clone.paths import ROOT as REPO
RP_MULTIYR    = REPO / 'data/research/xfp_cache/relievers_multiyr_2018_2026.csv'
RP_BIP_CSV    = REPO / 'data/research/xfp_cache/rp_damage_gb_2018_2026.csv'
AGE_CSV       = REPO / 'data/outputs/sp_age_career.csv'
BIRTHDATE_CSV = REPO / 'data/research/xfp_cache/milb_pitcher_ages.csv'
RPRS2_CSV     = REPO / 'data/outputs/xfp_rprs2_projections.csv'
SPLITS_CSV    = REPO / 'data/research/xfp_cache/pitcher_splits.csv'
FG_LEVERAGE_CSV = REPO / 'data/research/xfp_cache/fangraphs_rp_leverage_2018_2026.csv'
BREF_IR_CSV     = REPO / 'data/research/xfp_cache/rp_ir_is_2018_2026.csv'
OUT_DIR       = REPO / 'data/research'

# Sample-stability floor — matches RP_SUBDOMAIN_VALIDATION cohort
G_FLOOR_RATED = 20
TBF_FLOOR_RATED = 50
G_FLOOR_FULL = 40      # FULL tier: more durable sample (~half-season equivalent)

# ──────────────────────────────────────────────────────────────────────────────
# 27 archetype cells — STUFF / CONTROL / BATTED_BALL (S/C/B bucket triple)
# ──────────────────────────────────────────────────────────────────────────────
ARCHETYPES = {
    # All-PLUS
    'PLUS/PLUS/PLUS':    ('ELITE_CLOSER_STUFF',     'Triple-plus reliever: closer-grade stuff + control + bulk/GB. Edwin Diaz peak, Felix Bautista 23.'),
    'PLUS/PLUS/AVG':     ('LATE_INNING_STUFF_CTRL', 'High-K + low-walk late-inning weapon: Hader peak, Iglesias 24.'),
    'PLUS/PLUS/MINUS':   ('K_AND_CTRL_LITE_BULK',   'High-K + control, light bulk usage: short-burst closer pattern.'),
    'PLUS/AVG/PLUS':     ('STUFF_GB_HYBRID',        'Whiff + worm-burner profile, walks ok: Devin Williams blend.'),
    'PLUS/AVG/AVG':      ('PURE_STUFF_RP',          'K-driven RP: Mason Miller, Helsley pre-decline.'),
    'PLUS/AVG/MINUS':    ('STUFF_NO_BULK',          'High-K short-burst, avg control, light volume: setup-style.'),
    'PLUS/MINUS/PLUS':   ('WILD_GB_STUFF',          'High-K + GB but walks problem: rare; Aroldis-class outliers.'),
    'PLUS/MINUS/AVG':    ('WILD_FIREBALLER_RP',     'High-K, walk-prone, avg batted-ball: Chapman 23, Jansen 21.'),
    'PLUS/MINUS/MINUS':  ('WILD_HIGH_LEVERAGE',     'Stuff carries despite walks, short bursts: Estevez 24 style.'),
    # MIDDLE STUFF
    'AVG/PLUS/PLUS':     ('GB_INNINGS_EATER',       'Sinker-heavy multi-inning workhorse: Holmes 23, Bednar 22.'),
    'AVG/PLUS/AVG':      ('COMMAND_MIDDLE',         'Avg stuff + plus control, generic middle-relief: workhorse.'),
    'AVG/PLUS/MINUS':    ('CONTROL_RP_LITE',        'Avg stuff + control, light usage: matchup setup.'),
    'AVG/AVG/PLUS':      ('BULK_GB_RP',             'Avg everything except GB + multi-inning: bulk options.'),
    'AVG/AVG/AVG':       ('GENERIC_MIDDLE',         'Mid-tier middle relief — most common archetype.'),
    'AVG/AVG/MINUS':     ('LIGHT_USE_MIDDLE',       'Generic stuff + control, low IP/G: short-leash.'),
    'AVG/MINUS/PLUS':    ('GB_BULK_WILD',           'GB+bulk innings but walks problem: long-relief rough.'),
    'AVG/MINUS/AVG':     ('AVG_STUFF_WILD',         'Avg stuff + walks: bottom of bullpen.'),
    'AVG/MINUS/MINUS':   ('WILD_LIGHT_USE',         'Walks + light volume: fringe reliever.'),
    # MINUS STUFF
    'MINUS/PLUS/PLUS':   ('SOFT_GB_INNINGS_EATER',  'Low-K + GB + bulk: classic long-relief grinder.'),
    'MINUS/PLUS/AVG':    ('PITCH_TO_CONTACT_RP',    'Low-K + plus control: junkball middle relief.'),
    'MINUS/PLUS/MINUS':  ('CONTROL_LITE_USE',       'Low-K + control, light usage: matchup.'),
    'MINUS/AVG/PLUS':    ('LOW_K_GB_BULK',          'Low-K + GB + bulk: pure long-relief filler.'),
    'MINUS/AVG/AVG':     ('FILLER_RP',              'Below-K average rest: replacement-level RP.'),
    'MINUS/AVG/MINUS':   ('LOW_K_LIGHT_USE',        'Below-K, avg control, light IP/G: dispensable.'),
    'MINUS/MINUS/PLUS':  ('GB_WALK_GRINDER',        'GB + bulk despite walks: emergency long man.'),
    'MINUS/MINUS/AVG':   ('STRUGGLING_RP',          'Below-K + walks, avg batted-ball: replacement-level.'),
    'MINUS/MINUS/MINUS': ('FRINGE_RP',              'Below everything — bottom-of-roster RP.'),
}

# Domain composition weights (chosen 2026-05-28; see module docstring for rationale)
STUFF_W       = {'SWING_MISS': 0.85, 'VELO': 0.15}
CONTROL_W     = {'WALK_AVOID': 0.85, 'CALLED_STRIKE': 0.15}
BATTED_BALL_W = {'GB_TENDENCY': 0.50, 'BULK_IP': 0.50}

# Overall composite weights — empirical, with BATTED_BALL down-weighted (low fp signal)
OVERALL_W = {'STUFF': 0.55, 'CONTROL': 0.30, 'BATTED_BALL': 0.15}

# T+1 model (fit 2026-05-28; n=927 RP-year pairs 2018-2025, target=next_year fp_per_g)
T1_INTERCEPT = -4.24504
T1_BETAS = {
    'SWING_MISS':    0.05370,
    'CALLED_STRIKE': 0.02936,
    'VELO':          0.03345,
    'WALK_AVOID':    0.01352,
    'GB_TENDENCY':  -0.00391,
    'BULK_IP':       0.01096,
    'age':           0.01392,
}

# T+2 model (fit 2026-05-28; n=380 RP-year triplets 2018-2024, target=year+2 fp_per_g)
T2_INTERCEPT = -2.10874
T2_BETAS = {
    'SWING_MISS':    0.05125,
    'CALLED_STRIKE': 0.02585,
    'VELO':          0.03104,
    'WALK_AVOID':    0.01616,
    'GB_TENDENCY':  -0.01084,
    'BULK_IP':       0.00031,
    'age':          -0.01665,
}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers (mirror sp build)
# ──────────────────────────────────────────────────────────────────────────────
# Shared 20-80 scouting helpers live in the archetype_engine toolkit.
import sys as _sys
_sys.path.insert(0, str(REPO))
from scripts.xfp.lib.archetype_engine import (  # noqa: E402
    rating_20_80, bucket, boundary_distance, boundary_tier_label,
    age_tier as _eng_age_tier,
)


def stuff_subtype(row):
    """K_DRIVEN / WHIFF_LED / VELO_LED / BALANCED — sub-classifier within STUFF."""
    vals = {'K_DRIVEN': row.get('r_K', 50),
            'WHIFF_LED': row.get('SWING_MISS', 50),
            'VELO_LED': row.get('VELO', 50)}
    if max(vals.values()) - min(vals.values()) < 8:
        return 'BALANCED'
    return max(vals, key=vals.get)


def velo_tier(row):
    """POWER / BALANCED / FINESSE based on velo rating."""
    v = row.get('VELO', 50)
    if v >= 60: return 'POWER'
    if v >= 40: return 'BALANCED'
    return 'FINESSE'


def age_tier(age):
    """RP age tiers mirror hitter windows (peaks ~26-30 for K-stuff arms)."""
    return _eng_age_tier(age, pre_max=25, peak_max=30)


def attach_age(qual):
    """Merge age data from sp_age_career.csv with birthdate fallback."""
    if AGE_CSV.exists():
        ages = pd.read_csv(AGE_CSV)
        qual = qual.merge(ages[['pitcher', 'year', 'age', 'career_year']],
                          on=['pitcher', 'year'], how='left')
    else:
        qual['age'] = np.nan
        qual['career_year'] = np.nan

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


# ──────────────────────────────────────────────────────────────────────────────
# Main panel construction
# ──────────────────────────────────────────────────────────────────────────────
def build_ratings_panel():
    """Build 2018-current panel with 20-80 ratings + archetype labels + projections."""
    rp = pd.read_csv(RP_MULTIYR)

    # Cohort floor: G>=20 AND TBF>=50, exclude COVID-short 2020
    qual = rp[(rp['g'] >= G_FLOOR_RATED) & (rp['tbf_api'] >= TBF_FLOOR_RATED)].copy()
    qual = qual[qual['year'] != 2020].copy()
    qual['data_tier'] = np.where(qual['g'] >= G_FLOOR_FULL, 'FULL', 'PARTIAL')

    # Derived RP inputs
    qual['called_strike_rate'] = qual['called_strike'] / qual['pitches'].replace(0, np.nan)
    qual['ip_per_appearance'] = qual['ip'] / qual['g'].replace(0, np.nan)

    # Merge statcast-derived BIP aggregates (gb_pct + display barrel/hh/xwobacon)
    bip = pd.read_csv(RP_BIP_CSV)
    qual = qual.merge(bip, on=['pitcher', 'year'], how='left')

    # Sub-domain ratings (6 validated axes)
    g = qual.groupby('year')
    qual['SWING_MISS']    = rating_20_80(qual['swstr_pct'],          g['swstr_pct']).round(0).astype(int)
    qual['CALLED_STRIKE'] = rating_20_80(qual['called_strike_rate'], g['called_strike_rate']).round(0).astype(int)
    qual['VELO']          = rating_20_80(qual['avg_velo'],           g['avg_velo']).round(0).astype(int)
    qual['WALK_AVOID']    = rating_20_80(qual['bb_pct'],             g['bb_pct'], invert=True).round(0).astype(int)
    qual['GB_TENDENCY']   = rating_20_80(qual['gb_pct'],             g['gb_pct']).round(0).astype(int)
    qual['BULK_IP']       = rating_20_80(qual['ip_per_appearance'],  g['ip_per_appearance']).round(0).astype(int)

    # K% reference rating (used for stuff_subtype, not in domain composition)
    qual['r_K'] = rating_20_80(qual['k_pct'], g['k_pct']).round(0).astype(int)

    # Domain composites — weighted sum of sub-domains, re-rated 20-80 within year
    qual['_STUFF_raw'] = (STUFF_W['SWING_MISS'] * qual['SWING_MISS'] +
                          STUFF_W['VELO']       * qual['VELO'])
    qual['_CONTROL_raw'] = (CONTROL_W['WALK_AVOID']    * qual['WALK_AVOID'] +
                            CONTROL_W['CALLED_STRIKE'] * qual['CALLED_STRIKE'])
    qual['_BATTED_BALL_raw'] = (BATTED_BALL_W['GB_TENDENCY'] * qual['GB_TENDENCY'] +
                                BATTED_BALL_W['BULK_IP']     * qual['BULK_IP'])
    g2 = qual.groupby('year')
    qual['STUFF']       = rating_20_80(qual['_STUFF_raw'],       g2['_STUFF_raw']).round(0).astype(int)
    qual['CONTROL']     = rating_20_80(qual['_CONTROL_raw'],     g2['_CONTROL_raw']).round(0).astype(int)
    qual['BATTED_BALL'] = rating_20_80(qual['_BATTED_BALL_raw'], g2['_BATTED_BALL_raw']).round(0).astype(int)
    qual = qual.drop(columns=['_STUFF_raw', '_CONTROL_raw', '_BATTED_BALL_raw'])

    # Overall composite — weighted mean of 3 domains, re-rated within-year
    qual['_OVERALL_raw'] = (qual['STUFF']       * OVERALL_W['STUFF'] +
                            qual['CONTROL']     * OVERALL_W['CONTROL'] +
                            qual['BATTED_BALL'] * OVERALL_W['BATTED_BALL'])
    qual['OVERALL'] = rating_20_80(qual['_OVERALL_raw'],
                                    qual.groupby('year')['_OVERALL_raw']).round(0).astype(int)
    qual = qual.drop(columns=['_OVERALL_raw'])

    # Velo tier (sub-classifier on STUFF)
    qual['velo_tier'] = qual.apply(velo_tier, axis=1)

    # Age + tier
    qual = attach_age(qual)

    # Boundary distance + tier
    qual['bd_S'] = qual['STUFF'].apply(boundary_distance)
    qual['bd_C'] = qual['CONTROL'].apply(boundary_distance)
    qual['bd_B'] = qual['BATTED_BALL'].apply(boundary_distance)
    qual['boundary_distance'] = qual[['bd_S', 'bd_C', 'bd_B']].min(axis=1)
    qual['boundary_tier'] = qual['boundary_distance'].apply(boundary_tier_label)

    # Cells + archetype labels (S/C/B order — matches buckets above)
    qual['cell'] = (qual['STUFF'].apply(bucket) + '/' +
                    qual['CONTROL'].apply(bucket) + '/' +
                    qual['BATTED_BALL'].apply(bucket))
    qual['archetype'] = qual['cell'].map(lambda x: ARCHETYPES.get(x, ('UNKNOWN', '-'))[0])
    qual['stuff_subtype'] = qual.apply(stuff_subtype, axis=1)

    # Display-only tags (not rated, not in archetype label)
    qual['CLOSER'] = (qual['sv'] >= 15)
    qual['HIGH_LEVERAGE'] = qual['CLOSER'] | (qual['hld'] >= 15)
    qual['MULTI_INNING_BULK'] = (qual['ip_per_appearance'] >= 1.3)

    # ── FanGraphs leverage join (gmLI / pLI / WPA / Shutdowns / Meltdowns) ───
    # 2018-2026 ex-2020. ~100% join coverage on eligible cohort (verified
    # 2026-05-29). gmLI replaces the binary HIGH_LEVERAGE tag where present.
    # IR / IS% (inherited-runner stranded%) come from Baseball-Reference via
    # pull_bref_rp_ir.py — FG's combined-stats type=8 endpoint does NOT
    # expose them (confirmed by 544-key dump 2026-05-29). The Baseball-Reference
    # path ships the FIREMAN tag: stranded% ≥ 80% AND IR ≥ 20.
    if FG_LEVERAGE_CSV.exists():
        lev = pd.read_csv(FG_LEVERAGE_CSV)
        lev['mlb_id'] = pd.to_numeric(lev['mlb_id'], errors='coerce').astype('Int64')
        lev['season'] = pd.to_numeric(lev['season'], errors='coerce').astype('Int64')
        keep = ['mlb_id', 'season', 'gmli', 'pli', 'exli', 'inli',
                'wpa', 'wpa_per_li', 're24', 'rew',
                'shutdowns', 'meltdowns']
        keep = [c for c in keep if c in lev.columns]
        lev_slim = lev[keep].drop_duplicates(['mlb_id', 'season'])
        # Cast qual keys for clean join
        qual['pitcher'] = pd.to_numeric(qual['pitcher'], errors='coerce').astype('Int64')
        qual['year']    = pd.to_numeric(qual['year'],    errors='coerce').astype('Int64')
        qual = qual.merge(
            lev_slim,
            left_on=['pitcher', 'year'],
            right_on=['mlb_id', 'season'],
            how='left',
        ).drop(columns=['mlb_id', 'season'], errors='ignore')

        # leverage_tier — continuous gmLI replaces binary HIGH_LEVERAGE where data exists
        def _leverage_tier(row):
            g = row.get('gmli')
            if pd.notna(g):
                if g >= 1.5:  return 'ELITE_LEVERAGE'
                if g >= 1.2:  return 'HIGH_LEVERAGE'
                if g >= 0.85: return 'MID_LEVERAGE'
                if g >= 0.5:  return 'LOW_LEVERAGE'
                return 'GARBAGE_TIME'
            # Fallback to SV/HLD-derived binary when gmLI is null
            return 'HIGH_LEVERAGE' if row.get('HIGH_LEVERAGE', False) else 'MID_LEVERAGE'
        qual['leverage_tier'] = qual.apply(_leverage_tier, axis=1)

    else:
        # No leverage cache → leverage_tier from binary HIGH_LEVERAGE only
        qual['gmli'] = np.nan
        qual['pli']  = np.nan
        qual['exli'] = np.nan
        qual['inli'] = np.nan
        qual['wpa']  = np.nan
        qual['wpa_per_li'] = np.nan
        qual['re24'] = np.nan
        qual['rew']  = np.nan
        qual['shutdowns'] = np.nan
        qual['meltdowns'] = np.nan
        qual['leverage_tier'] = np.where(qual['HIGH_LEVERAGE'], 'HIGH_LEVERAGE', 'MID_LEVERAGE')

    # ── Baseball-Reference IR / IS% join (fireman skill) ────────────────────
    # Output of pull_bref_rp_ir.py. is_pct is STRANDED% (we invert BBRef's
    # scored% so higher = better, consistent with FG IR-S% convention).
    # FIREMAN = (inherited_stranded_pct >= 80) AND (ir >= 20).
    # 99.7% join coverage on the qualifying RP cohort (verified 2026-05-30).
    if BREF_IR_CSV.exists():
        bref = pd.read_csv(BREF_IR_CSV)
        bref['mlb_id'] = pd.to_numeric(bref['mlb_id'], errors='coerce').astype('Int64')
        bref['season'] = pd.to_numeric(bref['season'], errors='coerce').astype('Int64')
        keep_ir = ['mlb_id', 'season', 'ir', 'is_pct']
        keep_ir = [c for c in keep_ir if c in bref.columns]
        bref_slim = (bref[keep_ir]
                     .dropna(subset=['mlb_id', 'season'])
                     .drop_duplicates(['mlb_id', 'season']))
        bref_slim = bref_slim.rename(columns={'is_pct': 'inherited_stranded_pct'})
        # Cast qual keys for clean join (idempotent — leverage merge already did this)
        qual['pitcher'] = pd.to_numeric(qual['pitcher'], errors='coerce').astype('Int64')
        qual['year']    = pd.to_numeric(qual['year'],    errors='coerce').astype('Int64')
        qual = qual.merge(
            bref_slim,
            left_on=['pitcher', 'year'],
            right_on=['mlb_id', 'season'],
            how='left',
        ).drop(columns=['mlb_id', 'season'], errors='ignore')
        # FIREMAN: validated fireman role — strands ≥80% of inherited runners
        # on a meaningful sample (≥20 IR opportunities). Pure 9th-inning
        # closers have fewer IR opportunities and won't tag positive.
        qual['FIREMAN'] = (
            (qual['inherited_stranded_pct'].fillna(-1) >= 80.0) &
            (qual['ir'].fillna(0) >= 20)
        )
    else:
        qual['ir'] = np.nan
        qual['inherited_stranded_pct'] = np.nan
        qual['FIREMAN'] = False

    # Optional platoon tag — only computable for 2022+ with sufficient TBF
    if SPLITS_CSV.exists():
        splits = pd.read_csv(SPLITS_CSV)
        # OBVIOUS_PLATOON_GUY: same-handed batters dominate (xwoba vs same-side < .260 w/ >=50 TBF)
        def is_platoon(row):
            if pd.isna(row.get('p_throws')):
                return False
            if row['p_throws'] == 'R':
                tbf_same = row.get('tbf_vs_R', np.nan)
                xw_same = row.get('xwoba_vs_R', np.nan)
            elif row['p_throws'] == 'L':
                tbf_same = row.get('tbf_vs_L', np.nan)
                xw_same = row.get('xwoba_vs_L', np.nan)
            else:
                return False
            if pd.isna(tbf_same) or pd.isna(xw_same):
                return False
            return (tbf_same >= 50) and (xw_same < 0.260)
        splits['OBVIOUS_PLATOON_GUY'] = splits.apply(is_platoon, axis=1)
        qual = qual.merge(splits[['pitcher', 'year', 'OBVIOUS_PLATOON_GUY']],
                          on=['pitcher', 'year'], how='left')
        qual['OBVIOUS_PLATOON_GUY'] = qual['OBVIOUS_PLATOON_GUY'].fillna(False)
    else:
        qual['OBVIOUS_PLATOON_GUY'] = False

    # FP per game (target/display)
    qual['fp_per_g'] = qual['fp_per_g'].round(3)
    qual['rank_in_year'] = qual.groupby('year')['fp_per_g'].rank(ascending=False, method='min')

    # T+1 / T+2 projections (linear, embedded coefficients)
    def project(beta_dict, intercept):
        out = intercept + sum(
            qual[k].fillna(50) * v for k, v in beta_dict.items() if k != 'age'
        )
        if 'age' in beta_dict:
            out = out + beta_dict['age'] * qual['age'].fillna(qual['age'].median())
        return out

    qual['t1_fp_projection'] = project(T1_BETAS, T1_INTERCEPT).clip(lower=-1.0, upper=10.0).round(2)
    qual['t2_fp_projection'] = project(T2_BETAS, T2_INTERCEPT).clip(lower=-1.0, upper=10.0).round(2)

    # Trajectory metrics — 3-yr OVERALL slope + career percentile
    idkey = 'pitcher'
    qual_sorted = qual.sort_values([idkey, 'year'])[[idkey, 'year', 'OVERALL']].copy()

    def _trajectory_metrics(group):
        gg = group.sort_values('year').reset_index(drop=True)
        gg['OVERALL_slope_3yr'] = np.nan
        gg['OVERALL_career_pct'] = np.nan
        for i in range(len(gg)):
            window = gg.iloc[max(0, i-2):i+1]
            if len(window) >= 2 and window['year'].max() - window['year'].min() >= 1:
                slope = np.polyfit(window['year'].values, window['OVERALL'].values, 1)[0]
                gg.loc[gg.index[i], 'OVERALL_slope_3yr'] = slope
            career = gg.iloc[:i+1]['OVERALL']
            gg.loc[gg.index[i], 'OVERALL_career_pct'] = (career < gg.loc[gg.index[i], 'OVERALL']).sum() / len(career)
        return gg

    qual_sorted = qual_sorted.groupby(idkey, group_keys=False)[[idkey, 'year', 'OVERALL']].apply(_trajectory_metrics)
    qual_sorted['OVERALL_slope_3yr'] = qual_sorted['OVERALL_slope_3yr'].round(2)
    qual_sorted['OVERALL_career_pct'] = qual_sorted['OVERALL_career_pct'].round(3)

    def _traj_flag(row):
        s = row['OVERALL_slope_3yr']
        p = row['OVERALL_career_pct']
        if pd.notna(s) and s >= 3.0: return 'TRENDING_UP'
        if pd.notna(s) and s <= -3.0: return 'TRENDING_DOWN'
        if pd.notna(p) and p >= 0.90: return 'CAREER_HIGH'
        if pd.notna(p) and p <= 0.10: return 'CAREER_LOW'
        return 'STABLE'
    qual_sorted['traj_flag'] = qual_sorted.apply(_traj_flag, axis=1)

    qual = qual.merge(
        qual_sorted[[idkey, 'year', 'OVERALL_slope_3yr', 'OVERALL_career_pct', 'traj_flag']],
        on=[idkey, 'year'], how='left'
    )

    # Display name (relievers_multiyr 'name' is already "First Last")
    qual['player_name'] = qual['name']

    return qual


def compute_stickiness(qual):
    """Year-over-year retention rate per archetype + age-tier breakdown."""
    careers = qual.sort_values(['pitcher', 'year']).reset_index(drop=True)
    careers['next_arch'] = careers.groupby('pitcher')['archetype'].shift(-1)
    careers['next_year'] = careers.groupby('pitcher')['year'].shift(-1)
    careers['next_fp']   = careers.groupby('pitcher')['fp_per_g'].shift(-1)
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
            'fp_if_stayed': round(float(sub[sub['next_arch'] == arch]['next_fp'].mean()), 2)
                            if (sub['next_arch'] == arch).any() else None,
            'fp_if_left':   round(float(sub[sub['next_arch'] != arch]['next_fp'].mean()), 2)
                            if (sub['next_arch'] != arch).any() else None,
            'by_age_tier': {},
        }
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
    """T+1 / T+2 decline-rate baselines by archetype tier."""
    careers = qual.sort_values(['pitcher', 'year']).reset_index(drop=True)
    arch_q = qual.groupby('archetype')['fp_per_g'].mean()
    careers['arch_q'] = careers['archetype'].map(arch_q)
    careers['next_fp']     = careers.groupby('pitcher')['fp_per_g'].shift(-1)
    careers['next_arch_q'] = careers.groupby('pitcher')['arch_q'].shift(-1)
    careers['next_year']   = careers.groupby('pitcher')['year'].shift(-1)
    valid = careers[careers['next_year'] == careers['year'] + 1]

    # Decline = -1 fp/g drop OR -0.5 archetype-mean drop (RP scale ~3.0)
    decline_mask = ((valid['next_fp'] - valid['fp_per_g'] <= -1.0) |
                    (valid['next_arch_q'] - valid['arch_q'] <= -0.5))
    base = float(decline_mask.mean())
    elite = valid[valid['fp_per_g'] >= 4.5]
    elite_decline = float(((elite['next_fp'] - elite['fp_per_g'] <= -1.0) |
                           (elite['next_arch_q'] - elite['arch_q'] <= -0.5)).mean())

    return {
        'all_t_plus_1_decline_rate': round(base, 3),
        'elite_t_plus_1_decline_rate': round(elite_decline, 3),
        'decline_threshold': 'next_fp_per_g - fp_per_g <= -1.0 OR arch_quality drop <= -0.5',
        'elite_definition': 'fp_per_g >= 4.5 (top ~15% of RPs)',
        'methodology_note': (
            'RP T+1 decline rates are higher than SP because of small-sample noise '
            '(median 198 TBF/year vs SP 500-700). Use these as base-rate context, '
            'not as actionable alerts on individual RPs.'
        ),
    }


def build_career_panel(qual):
    """Add T+1 / T+2 outcomes for comp matching."""
    careers = qual.sort_values(['pitcher', 'year']).reset_index(drop=True)
    careers['next_fp']   = careers.groupby('pitcher')['fp_per_g'].shift(-1)
    careers['next_arch'] = careers.groupby('pitcher')['archetype'].shift(-1)
    careers['next_year'] = careers.groupby('pitcher')['year'].shift(-1)
    careers['t2_fp']     = careers.groupby('pitcher')['fp_per_g'].shift(-2)
    careers['t2_year']   = careers.groupby('pitcher')['year'].shift(-2)
    careers['name'] = careers['player_name']
    return careers


def main():
    print('Building RP archetype panel...', flush=True)
    qual = build_ratings_panel()
    print(f'  panel: {len(qual)} RP-years, {qual["pitcher"].nunique()} unique pitchers', flush=True)
    print(f'  year coverage: {sorted(qual["year"].unique().tolist())}', flush=True)
    print(f'  data_tier: {qual["data_tier"].value_counts().to_dict()}', flush=True)

    # Master CSV column order (RP-adapted from SP)
    master_cols = ['year', 'rank_in_year', 'pitcher', 'player_name', 'team_abbr',
                   'g', 'gs', 'tbf', 'sv', 'hld', 'ip_per_appearance',
                   'fp_per_g', 't1_fp_projection', 't2_fp_projection', 'data_tier',
                   'OVERALL', 'OVERALL_slope_3yr', 'OVERALL_career_pct', 'traj_flag',
                   'STUFF', 'CONTROL', 'BATTED_BALL',
                   'SWING_MISS', 'CALLED_STRIKE', 'VELO', 'WALK_AVOID', 'GB_TENDENCY', 'BULK_IP',
                   'archetype', 'stuff_subtype', 'cell',
                   'velo_tier',
                   'age', 'age_tier', 'career_year',
                   'bd_S', 'bd_C', 'bd_B', 'boundary_distance', 'boundary_tier',
                   'CLOSER', 'HIGH_LEVERAGE', 'MULTI_INNING_BULK', 'OBVIOUS_PLATOON_GUY',
                   'leverage_tier', 'FIREMAN',
                   'gmli', 'pli', 'exli', 'inli', 'wpa', 'wpa_per_li', 're24', 'rew',
                   'shutdowns', 'meltdowns',
                   'ir', 'inherited_stranded_pct',
                   'r_K',
                   'k_pct', 'bb_pct', 'swstr_pct', 'c_plus_swstr', 'called_strike_rate',
                   'avg_velo', 'gb_pct', 'barrel_pct', 'hard_hit_pct', 'xwobacon',
                   'xwoba_per_pa', 'role', 'n_bip']
    # Map team_abbr if present, else fill
    if 'team_abbr' not in qual.columns:
        qual['team_abbr'] = ''
    if 'tbf' not in qual.columns:
        qual['tbf'] = qual.get('tbf_api', np.nan)
    master = qual[master_cols].sort_values(['year', 'rank_in_year']).copy()

    # Pct formatting (display-friendly)
    for col, factor, prec in [('k_pct', 100, 1), ('bb_pct', 100, 1),
                              ('swstr_pct', 100, 1), ('c_plus_swstr', 100, 1),
                              ('called_strike_rate', 100, 1),
                              ('gb_pct', 100, 1), ('barrel_pct', 100, 1),
                              ('hard_hit_pct', 100, 1), ('xwobacon', 1, 3),
                              ('xwoba_per_pa', 1, 3), ('avg_velo', 1, 1),
                              ('ip_per_appearance', 1, 2)]:
        if col in master.columns:
            master[col] = (master[col] * factor).round(prec)

    out_master = OUT_DIR / 'rp_ratings_master.csv'
    master.to_csv(out_master, index=False, encoding='utf-8')
    print(f'  wrote {out_master.name}: {len(master)} rows', flush=True)

    # Definitions JSON
    defs = {k: {'label': v[0], 'description': v[1]} for k, v in ARCHETYPES.items()}
    with open(OUT_DIR / 'rp_archetype_definitions.json', 'w', encoding='utf-8') as f:
        json.dump(defs, f, indent=2)
    print('  wrote rp_archetype_definitions.json', flush=True)

    # Stickiness
    stick = compute_stickiness(qual)
    with open(OUT_DIR / 'rp_archetype_stickiness.json', 'w', encoding='utf-8') as f:
        json.dump(stick, f, indent=2)
    print(f'  wrote rp_archetype_stickiness.json ({len(stick)} archetypes)', flush=True)

    # Decline baselines
    decl = compute_decline_baselines(qual)
    with open(OUT_DIR / 'rp_decline_baselines.json', 'w', encoding='utf-8') as f:
        json.dump(decl, f, indent=2)
    print('  wrote rp_decline_baselines.json', flush=True)

    # Boundary tier validation (EDGE / NEAR_EDGE / SOLID T+1 retention)
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
    with open(OUT_DIR / 'rp_boundary_validation.json', 'w', encoding='utf-8') as f:
        json.dump(boundary_stats, f, indent=2)
    print(f'  wrote rp_boundary_validation.json ({boundary_stats})', flush=True)

    # Career panel for comps
    panel = build_career_panel(qual)
    panel_path = OUT_DIR / 'rp_archetype_career_panel.parquet'
    panel.to_parquet(panel_path, index=False)
    print(f'  wrote {panel_path.name}', flush=True)

    # Spot-checks
    print('\n[spot-check] known elite closers — 2025 / 2026 rows:', flush=True)
    spot_names = ['Edwin Díaz', 'Edwin Diaz', 'Félix Bautista', 'Felix Bautista',
                  'Devin Williams', 'Mason Miller', 'Emmanuel Clase', 'Josh Hader',
                  'Ryan Helsley']
    for nm in spot_names:
        rows = master[(master['player_name'] == nm) & (master['year'].isin([2025, 2026]))]
        for _, r in rows.iterrows():
            print(f'   {nm:25s} {int(r["year"])}: archetype={r["archetype"]:25s}  '
                  f'STUFF={int(r["STUFF"])}/CTL={int(r["CONTROL"])}/BB={int(r["BATTED_BALL"])}  '
                  f'CLOSER={bool(r["CLOSER"])}  SV={int(r["sv"])}  '
                  f'fp/g={r["fp_per_g"]:.2f}', flush=True)

    print('\nDone.', flush=True)


if __name__ == '__main__':
    main()

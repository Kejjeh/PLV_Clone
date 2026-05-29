"""
build_hitter_archetypes.py — daily build of hitter 20-80 ratings + archetype
labels + trajectories + stickiness + comp panel.

Parallel to build_sp_archetypes.py but for batters.

Domains (3 drive the archetype, SB is an orthogonal overlay):
  CONTACT     — bat-to-ball + K-avoidance + BIP production
                components: contact_pct, k_pct (inv), BABIP, xwoba_on_contact
  POWER       — quality-of-contact for extra-base damage
                components: barrel_pct, hard_hit_pct, iso, hr_per_pa, pull_fb_pct
  DISCIPLINE  — plate approach (eye)
                components: bb_pct, chase_pct (inv), z_swing_pct
  SB (overlay) — SB rate per opportunity + sprint speed
                tier: HI_SB / MOD_SB / NON_RUNNER

Outputs (all to data/research/):
  hitter_ratings_master.csv               — pitcher-year-equivalent, all 20-80 ratings
  hitter_archetype_career_panel.parquet   — same + T+1/T+2 outcomes
  hitter_archetype_definitions.json       — 27 cell labels + descriptions
  hitter_archetype_stickiness.json        — YoY retention per archetype
  hitter_decline_baselines.json           — historical decline base rates
  hitter_boundary_validation.json         — EDGE/NEAR_EDGE/SOLID retention
"""
from __future__ import annotations
import pandas as pd, numpy as np, json
from pathlib import Path

REPO = Path(r'c:\Users\Joshua\plv_clone')
HIST_CSV = REPO / 'data/research/xfp_cache/hitters_multiyr_2015_2026.csv'
AGE_CSV  = REPO / 'data/outputs/hitter_age_career.csv'
PARK_CSV = REPO / 'data/research/xfp_cache/park_factors_2018_2026.csv'
OUT_DIR  = REPO / 'data/research'

# Sample-stability floor (BB% stabilizes ~120 PA; 100 is the practical edge
# where rate-based 20-80 ratings are still meaningful). All years use the same
# RATED floor so rookies and mid-season call-ups are visible. FULL tier flags
# 250+ PA as the durable cut.
PA_FLOOR_RATED = 100
PA_FLOOR_FULL = 250

# ──────────────────────────────────────────────────────────────────────────────
# 27 archetype cells (C/P/D bucket triple → label + description)
# ──────────────────────────────────────────────────────────────────────────────
ARCHETYPES = {
    'PLUS/PLUS/PLUS':    ('GOAT_TIER',          'Triple-plus elite hitter: Trout peak, Judge 22, Soto 24'),
    'PLUS/PLUS/AVG':     ('CONTACT_POWER',      'Hits + hits hard: Vlad Jr, Freeman, Acuña peak'),
    'PLUS/PLUS/MINUS':   ('AGGRESSIVE_STAR',    'Contact + power but chases: Acuña 23-style aggression'),
    'PLUS/AVG/PLUS':     ('CONTACT_EYE',        'Bat-to-ball + walks, modest pop: Devers good yrs, Verdugo'),
    'PLUS/AVG/AVG':      ('PURE_HITTER',        'High BA, average pop & eye: Arraez, McNeil, Bregman'),
    'PLUS/AVG/MINUS':    ('CONTACT_HACKER',     'Hits everything, no walks: Yandy Diaz-lite'),
    'PLUS/MINUS/PLUS':   ('SLAP_AND_WALK',      'Bat control + eye, no power: Bichette down years'),
    'PLUS/MINUS/AVG':    ('SLAP_HITTER',        'Contact specialist, no pop: LeMahieu, Merrifield'),
    'PLUS/MINUS/MINUS':  ('AGGRESSIVE_SLAP',    'High contact, no pop, no walks: bench piece'),
    'AVG/PLUS/PLUS':     ('POWER_EYE',          'Power + walks, K-OK: Schwarber, Olson, Soto-lite'),
    'AVG/PLUS/AVG':      ('POWER_HITTER',       'Classic slugger: Olson, Stanton good yrs, Riley'),
    'AVG/PLUS/MINUS':    ('ALL_OR_NOTHING',     'Power, K-prone, chases: Gallo, Schwarber, Stanton late'),
    'AVG/AVG/PLUS':      ('BALANCED_EYE',       'Average bat with patience: Will Smith, Riley some yrs'),
    'AVG/AVG/AVG':       ('AVERAGE_HITTER',     'Generic mid-tier — most common archetype'),
    'AVG/AVG/MINUS':     ('AVG_HACKER',         'Average everything but chases: Salvy Perez, Tellez'),
    'AVG/MINUS/PLUS':    ('SECONDARY_LEADOFF',  'Patient leadoff, no pop: Edman, Benintendi'),
    'AVG/MINUS/AVG':     ('GENERIC_NO_POWER',   'Average everything, no pop: utility profile'),
    'AVG/MINUS/MINUS':   ('NO_POWER_HACKER',    'No pop, chases: 4A bat'),
    'MINUS/PLUS/PLUS':   ('THREE_TRUE_OUTCOMES','HR + BB + K: Gallo, Adolis García, Cal Raleigh'),
    'MINUS/PLUS/AVG':    ('POWER_K',            'Power-only, K-heavy: Stanton late, classic slugger-K'),
    'MINUS/PLUS/MINUS':  ('POWER_HACKER',       'Power + K + chase: Báez, Adolis at worst'),
    'MINUS/AVG/PLUS':    ('PATIENT_K',          'Walks, no pop, K-prone: bench bat type'),
    'MINUS/AVG/AVG':     ('BACKUP_BAT',         'Below-K, average rest: replacement-tier'),
    'MINUS/AVG/MINUS':   ('K_PRONE_FILLER',     'Below-K + chase + no walks'),
    'MINUS/MINUS/PLUS':  ('WALK_ONLY_FRINGE',   'Only skill is the walk: fringe bench'),
    'MINUS/MINUS/AVG':   ('FRINGE',             'Below-K, below-power, average eye'),
    'MINUS/MINUS/MINUS': ('BUST',               'Below everything: AAAA bat'),
}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers (mirrors build_sp_archetypes.py)
# ──────────────────────────────────────────────────────────────────────────────
def rating_20_80(series, grouper, invert=False):
    """20-80 scouting scale: 50=mean, 10pts=1 SD, capped [20,80], within-year scaled."""
    mu = grouper.transform('mean')
    sd = grouper.transform('std').replace(0, np.nan)
    z = (series - mu) / sd
    if invert:
        z = -z
    return (50 + 10 * z).clip(20, 80)


def bucket(rating):
    if rating >= 60: return 'PLUS'
    if rating >= 40: return 'AVG'
    return 'MINUS'


def contact_subtype(row):
    """PURE_CONTACT / CONTACT_QUALITY / BAT_TO_BALL_KING / CHASE_CONTACT based
    on component spread within the CONTACT domain."""
    skill_avg   = (row['r_Contact'] + row['r_K']) / 2     # bat-to-ball skill
    quality_avg = (row['r_BABIP'] + row['r_xCON']) / 2    # contact production
    if skill_avg >= 60 and quality_avg >= 60:
        return 'BAT_TO_BALL_KING'
    if skill_avg >= quality_avg + 8:
        return 'PURE_CONTACT'      # bat-to-ball drives
    if quality_avg >= skill_avg + 8:
        return 'CONTACT_QUALITY'   # production drives, more swing-and-miss
    return 'BALANCED'


def power_subtype(row):
    """ELITE_RAW / BARREL_KING / PULL_LIFT / PURE_HR / GAP_POWER / BALANCED.
    Identified by which Power component leads."""
    vals = {
        'BARREL_KING': row['r_Barrel'],
        'ELITE_RAW':   row['r_HardHit'],
        'PURE_HR':     row['r_HRrate'],
        'PULL_LIFT':   row['r_PullFB'],
    }
    # Gap-power detector: high ISO with low HR rate (doubles/triples driven)
    if row.get('iso', 0) > 0 and row['r_ISO'] >= 55 and row['r_HRrate'] < row['r_ISO'] - 10:
        return 'GAP_POWER'
    if max(vals.values()) - min(vals.values()) < 8:
        return 'BALANCED'
    return max(vals, key=vals.get)


def discipline_subtype(row):
    """PURE_PATIENCE / SELECTIVE_AGGRESSIVE / PASSIVE_WALKS / BALANCED."""
    if row['r_Chase'] >= 60 and row['r_ZSwing'] >= 55:
        return 'SELECTIVE_AGGRESSIVE'
    if row['r_BB'] >= 60 and row['r_Chase'] >= 55:
        return 'PURE_PATIENCE'
    if row['r_BB'] >= 60 and row['r_ZSwing'] < 45:
        return 'PASSIVE_WALKS'
    return 'BALANCED'


def sb_tier(row):
    """HI_SB / MOD_SB / NON_RUNNER overlay tag."""
    sb_rating = row.get('r_SB', 50)
    if sb_rating >= 60: return 'HI_SB'
    if sb_rating >= 45: return 'MOD_SB'
    return 'NON_RUNNER'


def spray_archetype(row):
    """PULL_HEAVY / BALANCED_SPRAY / OPPO_LEAN — parallel to SP pitch_archetype."""
    pull = row.get('pull_pct', np.nan)
    oppo = row.get('oppo_pct', np.nan)
    if pd.isna(pull) or pd.isna(oppo):
        return None
    if pull >= 0.45:
        return 'PULL_HEAVY'
    if oppo >= 0.30:
        return 'OPPO_LEAN'
    return 'BALANCED_SPRAY'


def age_tier(age):
    """PRE_PEAK (<=25) / PEAK (26-30) / POST_PEAK (31+).
    Hitters peak ~1 year earlier than SPs (Mike Lichtman aging-curve work)."""
    if pd.isna(age): return None
    if age <= 25: return 'PRE_PEAK'
    if age <= 30: return 'PEAK'
    return 'POST_PEAK'


def boundary_distance(rating):
    return int(min(abs(rating - 40), abs(rating - 60)))


def boundary_tier_label(d):
    if d <= 2: return 'EDGE'
    if d <= 5: return 'NEAR_EDGE'
    return 'SOLID'


def attach_age(qual):
    """Merge hitter age data; mirror SP path."""
    if AGE_CSV.exists():
        ages = pd.read_csv(AGE_CSV)
        qual = qual.merge(ages[['batter', 'year', 'age', 'career_year']],
                          on=['batter', 'year'], how='left')
    else:
        qual['age'] = np.nan
        qual['career_year'] = np.nan
    qual['age_tier'] = qual['age'].apply(age_tier)
    return qual


def derive_babip(df):
    """BABIP = (H - HR) / (AB - K - HR). Standard MLB formula (ignores SF, ~small)."""
    denom = (df['ab'] - df['k'] - df['hr']).clip(lower=1)
    return ((df['h'] - df['hr']) / denom).clip(lower=0, upper=1)


def derive_2b3b_rate(df):
    """Gap-power rate: doubles + triples per PA."""
    return ((df['b2'] + df['b3']) / df['pa'].clip(lower=1)).clip(lower=0)


def derive_sb_per_opp(df):
    """SB / (singles + walks + HBP) — denominator is roughly times-reached-1B."""
    opp = (df['b1'] + df['bb'] + df['hbp']).clip(lower=1)
    return (df['sb'] / opp).clip(lower=0)


# ──────────────────────────────────────────────────────────────────────────────
# Main panel build
# ──────────────────────────────────────────────────────────────────────────────
def build_ratings_panel(current_year=2026):
    m = pd.read_csv(HIST_CSV)

    # Derived metrics
    m['babip']        = derive_babip(m)
    m['rate_2b3b']    = derive_2b3b_rate(m)
    m['sb_per_opp']   = derive_sb_per_opp(m)
    # O-Contact% = chase contact rate = (contact - z_contact) / o_swing
    m['o_contact']     = (m['contact'] - m['z_contact']).clip(lower=0)
    m['o_contact_pct'] = (m['o_contact'] / m['o_swing'].clip(lower=1)).clip(0, 1)

    # Apply PA floor: every year uses the sample-stability floor so debutants
    # and mid-season call-ups are visible. data_tier flags durable vs partial.
    qual = m[m['pa'] >= PA_FLOOR_RATED].copy()
    qual = qual[qual['year'] != 2020]   # exclude COVID
    qual['data_tier'] = np.where(qual['pa'] >= PA_FLOOR_FULL, 'FULL', 'PARTIAL')

    g = qual.groupby('year')

    # CONTACT components — bat-to-ball + K avoidance + BIP quality + spray diversity
    qual['r_Contact']  = rating_20_80(qual['contact_pct'],      g['contact_pct']).round(0).astype(int)
    # Z-Contact / O-Contact split: kept primarily for diagnostic distinction
    # (Judge = elite Z, weak O; Yandy Diaz = opposite). They feed the new
    # Z_CONTACT / O_CONTACT sub-domains; r_Contact retained for backwards compat.
    qual['r_ZContact'] = rating_20_80(qual['z_contact_pct'],    g['z_contact_pct']).round(0).astype(int)
    qual['r_OContact'] = rating_20_80(qual['o_contact_pct'],    g['o_contact_pct']).round(0).astype(int)
    qual['r_K']        = rating_20_80(qual['k_pct'],            g['k_pct'], invert=True).round(0).astype(int)
    qual['r_BABIP']   = rating_20_80(qual['babip'],            g['babip']).round(0).astype(int)
    qual['r_xCON']    = rating_20_80(qual['xwoba_on_contact'], g['xwoba_on_contact']).round(0).astype(int)
    # Spray entropy — captures spray diversity (high entropy = balanced pull/cent/oppo,
    # predicts BABIP stability under shifts). YoY r ~0.52.
    def _spray_entropy(row):
        vals = [row.get('pull_pct'), row.get('cent_pct'), row.get('oppo_pct')]
        vals = [v for v in vals if pd.notna(v) and v > 0]
        if not vals: return np.nan
        s = sum(vals)
        return -sum((v/s) * np.log(v/s) for v in vals) if s else np.nan
    qual['spray_entropy'] = qual.apply(_spray_entropy, axis=1)
    qual['r_SprayEnt'] = rating_20_80(qual['spray_entropy'],   g['spray_entropy']).round(0).astype(int)

    # POWER components — quality + launch optimization + production
    qual['r_Barrel']  = rating_20_80(qual['barrel_pct'],       g['barrel_pct']).round(0).astype(int)
    qual['r_HardHit'] = rating_20_80(qual['hard_hit_pct'],     g['hard_hit_pct']).round(0).astype(int)
    qual['r_ISO']     = rating_20_80(qual['iso'],              g['iso']).round(0).astype(int)
    qual['r_HRrate']  = rating_20_80(qual['hr_per_pa'],        g['hr_per_pa']).round(0).astype(int)
    qual['r_PullFB']  = rating_20_80(qual['pull_fb_pct'],      g['pull_fb_pct']).round(0).astype(int)
    # Launch-optimization components — sweet spot rate + EV90 (top-end EV).
    # EV90 has excellent YoY r=0.87 — one of the most stable hitter metrics.
    qual['r_SweetSpot'] = rating_20_80(qual['sweet_spot_pct'], g['sweet_spot_pct']).round(0).astype(int)
    qual['r_EV90']      = rating_20_80(qual['ev90'],           g['ev90']).round(0).astype(int)

    # DISCIPLINE components — eye + HBP (each HBP = +1 FP, same as a walk)
    qual['r_BB']      = rating_20_80(qual['bb_pct'],           g['bb_pct']).round(0).astype(int)
    qual['r_Chase']   = rating_20_80(qual['chase_pct'],        g['chase_pct'], invert=True).round(0).astype(int)
    qual['r_ZSwing']  = rating_20_80(qual['z_swing_pct'],      g['z_swing_pct']).round(0).astype(int)
    qual['r_HBP']     = rating_20_80(qual['hbp_pct'],          g['hbp_pct']).round(0).astype(int)

    # SB overlay components (2) — sb rate + sprint speed (sprint missing pre-2017)
    qual['r_SBrate']  = rating_20_80(qual['sb_per_opp'],       g['sb_per_opp']).round(0).astype(int)
    if 'sprint_speed' in qual.columns and qual['sprint_speed'].notna().any():
        sprint = qual['sprint_speed'].fillna(qual.groupby('year')['sprint_speed'].transform('mean'))
        qual['r_Sprint'] = rating_20_80(sprint, g['sprint_speed']).round(0).astype(int)
    else:
        qual['r_Sprint'] = 50

    # Sub-domain ratings (intermediate layer). Each maps a coherent slice of a
    # domain. Computed FIRST: components → simple mean → re-rated 20-80 within
    # year. Domains are then computed as empirically-weighted sums of these
    # sub-domain ratings (see below).
    qual['_Z_CONTACT_raw']       = qual['r_ZContact']
    qual['_O_CONTACT_raw']       = qual['r_OContact']
    qual['_K_AVOIDANCE_raw']     = qual['r_K']
    qual['_CONTACT_QUALITY_raw'] = qual['r_xCON']
    qual['_SPRAY_PROFILE_raw']   = qual['r_SprayEnt']
    qual['_RAW_POWER_raw']       = qual[['r_HardHit','r_Barrel','r_EV90']].mean(axis=1)
    qual['_LAUNCH_OPTIM_raw']    = qual[['r_SweetSpot','r_PullFB']].mean(axis=1)
    qual['_DAMAGE_PROD_raw']     = qual[['r_ISO','r_HRrate']].mean(axis=1)
    qual['_PATIENCE_raw']        = qual[['r_BB','r_Chase','r_HBP']].mean(axis=1)
    qual['_AGGRESSION_raw']      = qual['r_ZSwing']
    qual['_SPEED_TOOL_raw']      = qual['r_Sprint']
    qual['_SB_CONVERSION_raw']   = qual['r_SBrate']
    g_sub = qual.groupby('year')
    qual['Z_CONTACT']       = rating_20_80(qual['_Z_CONTACT_raw'],       g_sub['_Z_CONTACT_raw']).round(0).astype(int)
    qual['O_CONTACT']       = rating_20_80(qual['_O_CONTACT_raw'],       g_sub['_O_CONTACT_raw']).round(0).astype(int)
    qual['K_AVOIDANCE']     = rating_20_80(qual['_K_AVOIDANCE_raw'],     g_sub['_K_AVOIDANCE_raw']).round(0).astype(int)
    qual['CONTACT_QUALITY'] = rating_20_80(qual['_CONTACT_QUALITY_raw'], g_sub['_CONTACT_QUALITY_raw']).round(0).astype(int)
    qual['SPRAY_PROFILE']   = rating_20_80(qual['_SPRAY_PROFILE_raw'],   g_sub['_SPRAY_PROFILE_raw']).round(0).astype(int)
    qual['RAW_POWER']       = rating_20_80(qual['_RAW_POWER_raw'],       g_sub['_RAW_POWER_raw']).round(0).astype(int)
    qual['LAUNCH_OPTIM']    = rating_20_80(qual['_LAUNCH_OPTIM_raw'],    g_sub['_LAUNCH_OPTIM_raw']).round(0).astype(int)
    qual['DAMAGE_PROD']     = rating_20_80(qual['_DAMAGE_PROD_raw'],     g_sub['_DAMAGE_PROD_raw']).round(0).astype(int)
    qual['PATIENCE']        = rating_20_80(qual['_PATIENCE_raw'],        g_sub['_PATIENCE_raw']).round(0).astype(int)
    qual['AGGRESSION']      = rating_20_80(qual['_AGGRESSION_raw'],      g_sub['_AGGRESSION_raw']).round(0).astype(int)
    qual['SPEED_TOOL']      = rating_20_80(qual['_SPEED_TOOL_raw'],      g_sub['_SPEED_TOOL_raw']).round(0).astype(int)
    qual['SB_CONVERSION']   = rating_20_80(qual['_SB_CONVERSION_raw'],   g_sub['_SB_CONVERSION_raw']).round(0).astype(int)
    qual = qual.drop(columns=['_Z_CONTACT_raw','_O_CONTACT_raw','_K_AVOIDANCE_raw',
                                '_CONTACT_QUALITY_raw','_SPRAY_PROFILE_raw',
                                '_RAW_POWER_raw','_LAUNCH_OPTIM_raw','_DAMAGE_PROD_raw',
                                '_PATIENCE_raw','_AGGRESSION_raw','_SPEED_TOOL_raw','_SB_CONVERSION_raw'])

    # Domain composites — weighted sum of SUB-DOMAIN ratings, re-rated to 20-80
    # within year. Sub-domain weights derived from OLS regression of fp_per_pa
    # on the sub-domain ratings (FULL pool n=3,163). Empirical weights:
    #   CONTACT    = 0.465 B2B + 0.461 QUALITY + 0.074 SPRAY  (rounded 0.45/0.45/0.10)
    #   POWER      = 0.233 RAW + 0.080 LAUNCH  + 0.687 PROD   (rounded 0.25/0.10/0.65)
    #   DISCIPLINE = 0.695 PATIENCE + 0.305 AGGRESSION         (rounded 0.70/0.30)
    #   SB         = 0.338 SPEED   + 0.662 CONVERSION          (rounded 0.30/0.70)
    # This properly weights xwOBACON (Quality) at 45% of CONTACT instead of 25%
    # under the prior equal-mean architecture, and DAMAGE_PROD at 65% of POWER
    # instead of 14%. Better reflects what actually drives FP/PA.
    # CONTACT now decomposes into 5 sub-domains. Empirical weights from OLS
    # regression of fp_per_pa on the 5 sub-domain ratings (FULL pool n=3,163):
    #   Z_CONTACT=0.03 / O_CONTACT=0.01 / K_AVOIDANCE=0.47 / QUALITY=0.42 / SPRAY=0.08
    # Rounded with token weights for Z/O (their signal collapses behind K_AVOID
    # in the regression — they're kept primarily for diagnostic distinction:
    # Judge has elite Z, weak O; Yandy Diaz has the opposite).
    qual['_CONTACT_raw']    = (0.05 * qual['Z_CONTACT']
                              + 0.05 * qual['O_CONTACT']
                              + 0.45 * qual['K_AVOIDANCE']
                              + 0.40 * qual['CONTACT_QUALITY']
                              + 0.05 * qual['SPRAY_PROFILE'])
    qual['_POWER_raw']      = (0.25 * qual['RAW_POWER']
                              + 0.10 * qual['LAUNCH_OPTIM']
                              + 0.65 * qual['DAMAGE_PROD'])
    qual['_DISCIPLINE_raw'] = (0.70 * qual['PATIENCE']
                              + 0.30 * qual['AGGRESSION'])
    qual['_SB_raw']         = (0.30 * qual['SPEED_TOOL']
                              + 0.70 * qual['SB_CONVERSION'])
    g2 = qual.groupby('year')
    qual['CONTACT']    = rating_20_80(qual['_CONTACT_raw'],    g2['_CONTACT_raw']).round(0).astype(int)
    qual['POWER']      = rating_20_80(qual['_POWER_raw'],      g2['_POWER_raw']).round(0).astype(int)
    qual['DISCIPLINE'] = rating_20_80(qual['_DISCIPLINE_raw'], g2['_DISCIPLINE_raw']).round(0).astype(int)
    qual['SB']         = rating_20_80(qual['_SB_raw'],         g2['_SB_raw']).round(0).astype(int)
    qual = qual.drop(columns=['_CONTACT_raw','_POWER_raw','_DISCIPLINE_raw','_SB_raw'])

    # BABIP luck context — career mean + delta from career mean per batter-year.
    # Year-to-year BABIP stability is r~0.39 (mostly noise); large deltas usually
    # indicate batted-ball luck. Threshold +-0.030 chosen to roughly correspond
    # to ~1 SD of within-batter year-to-year BABIP variance.
    career_babip = qual.groupby('batter')['babip'].transform('mean')
    qual['babip_career'] = career_babip.round(3)
    qual['babip_delta']  = (qual['babip'] - qual['babip_career']).round(3)
    qual['babip_luck_flag'] = qual['babip_delta'].apply(
        lambda d: 'HOT' if d >= 0.030 else ('COLD' if d <= -0.030 else 'NORMAL'))

    # Overall composite — weighted mean of the three archetype-driving domains,
    # then re-rated within year to a clean 20-80 distribution. Refit after the
    # 2026-05 expansion: CONTACT now includes SprayEnt; POWER now includes
    # SweetSpot+EV90+PullFB (LAUNCH_OPTIM sub-domain); DISCIPLINE now includes
    # HBP. New empirical OLS: 0.565/0.328/0.107 (R²=0.60) on FULL-tier pool.
    # Rounded for clean numbers; user can tune in dashboard discussion.
    # SB intentionally excluded (overlay, not part of archetype identity).
    OVERALL_W = {'CONTACT': 0.55, 'POWER': 0.35, 'DISCIPLINE': 0.10}
    qual['_OVERALL_raw'] = (qual['CONTACT']    * OVERALL_W['CONTACT']
                          + qual['POWER']      * OVERALL_W['POWER']
                          + qual['DISCIPLINE'] * OVERALL_W['DISCIPLINE'])
    qual['OVERALL'] = rating_20_80(qual['_OVERALL_raw'],
                                    qual.groupby('year')['_OVERALL_raw']).round(0).astype(int)
    qual = qual.drop(columns=['_OVERALL_raw'])

    # Age tier (added 2026-05-28)
    qual = attach_age(qual)

    # Boundary distance per domain + min + tier
    qual['bd_C'] = qual['CONTACT'].apply(boundary_distance)
    qual['bd_P'] = qual['POWER'].apply(boundary_distance)
    qual['bd_D'] = qual['DISCIPLINE'].apply(boundary_distance)
    qual['boundary_distance'] = qual[['bd_C','bd_P','bd_D']].min(axis=1)
    qual['boundary_tier'] = qual['boundary_distance'].apply(boundary_tier_label)

    # Cells + archetype labels (Contact / Power / Discipline drive the matrix)
    qual['cell'] = (qual['CONTACT'].apply(bucket) + '/'
                   + qual['POWER'].apply(bucket) + '/'
                   + qual['DISCIPLINE'].apply(bucket))
    qual['archetype']           = qual['cell'].map(lambda x: ARCHETYPES.get(x, ('UNKNOWN','-'))[0])
    qual['contact_subtype']     = qual.apply(contact_subtype, axis=1)
    qual['power_subtype']       = qual.apply(power_subtype, axis=1)
    qual['discipline_subtype']  = qual.apply(discipline_subtype, axis=1)
    qual['sb_tier']             = qual.apply(sb_tier, axis=1)
    qual['spray_archetype']     = qual.apply(spray_archetype, axis=1)

    # Within-year FP rank (per PA) — fresh groupby; attach_age() reshapes indices
    # and the earlier `g` becomes stale.
    qual['fp_per_pa'] = qual['fp_per_pa_actual']
    qual['rank_in_year'] = qual.groupby('year')['fp_per_pa_actual'].rank(ascending=False, method='min')

    # Park-adjusted HR rate (transparency column, never feeds composites).
    # Loaded from park_factors_2018_2026.csv. hr_per_pa_parkadj = hr_per_pa / pf_HR;
    # Coors (pf_HR ~1.3-1.4) deflated, Petco (~0.85) inflated. T+1 mover regression
    # shows +0.012 R² lift — below ship bar for composite swap, but useful display.
    # Placed AFTER all other ratings so the park-factor merge doesn't disturb the
    # within-year groupbys used upstream.
    if PARK_CSV.exists():
        pf = pd.read_csv(PARK_CSV)[['year','team_abbr','pf_HR']]
        pf = pf.rename(columns={'team_abbr': 'team'}).drop_duplicates(['year','team'])
        qual = qual.merge(pf, on=['year','team'], how='left')
        qual['pf_HR'] = qual['pf_HR'].fillna(1.0)
        qual['hr_per_pa_parkadj'] = qual['hr_per_pa'] / qual['pf_HR']
        adj = rating_20_80(qual['hr_per_pa_parkadj'], qual.groupby('year')['hr_per_pa_parkadj'])
        qual['r_HRrate_parkadj'] = adj.fillna(qual['r_HRrate']).round(0).astype(int)
        qual['hr_parkadj_delta'] = (qual['r_HRrate_parkadj'] - qual['r_HRrate']).fillna(0).astype(int)
    else:
        qual['pf_HR'] = 1.0
        qual['hr_per_pa_parkadj'] = qual['hr_per_pa']
        qual['r_HRrate_parkadj'] = qual['r_HRrate']
        qual['hr_parkadj_delta'] = 0

    # T+1 FP/PA projection — linear combo of sub-domain ratings + age.
    # Coefficients from OLS regression of next-year fp_per_pa on these features.
    T1_HITTER_INTERCEPT = -0.59929
    T1_HITTER_BETAS = {
        'Z_CONTACT': 0.00117, 'O_CONTACT': 0.00294, 'K_AVOIDANCE': 0.00535,
        'CONTACT_QUALITY': -0.00018, 'SPRAY_PROFILE': -0.00022,
        'RAW_POWER': 0.00626, 'LAUNCH_OPTIM': 0.00086, 'DAMAGE_PROD': 0.00151,
        'PATIENCE': 0.00125, 'AGGRESSION': 0.00100,
        'SPEED_TOOL': 0.00132, 'SB_CONVERSION': 0.00147,
        'age': -0.00284,
    }
    qual['t1_fp_proj_raw'] = T1_HITTER_INTERCEPT + sum(
        qual[k].fillna(50) * v for k, v in T1_HITTER_BETAS.items()
    )
    qual['t1_fp_projection'] = qual['t1_fp_proj_raw'].clip(lower=0.1, upper=1.2).round(3)
    qual = qual.drop(columns=['t1_fp_proj_raw'])

    # Trajectory alerts — 3-year OVERALL slope + career percentile.
    # Slope = linear-regression slope of OVERALL on year over the last 3 seasons
    # (including current). Career percentile = where current OVERALL sits within
    # this player's own historical distribution.
    idkey = 'batter'
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
    """YoY archetype retention + per-age-tier breakdown."""
    careers = qual.sort_values(['batter','year']).reset_index(drop=True)
    careers['next_arch'] = careers.groupby('batter')['archetype'].shift(-1)
    careers['next_year'] = careers.groupby('batter')['year'].shift(-1)
    careers['next_fp']   = careers.groupby('batter')['fp_per_pa'].shift(-1)
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
            'fp_if_stayed': round(float(sub[sub['next_arch'] == arch]['next_fp'].mean()), 3),
            'fp_if_left':   round(float(sub[sub['next_arch'] != arch]['next_fp'].mean()), 3),
            'by_age_tier': {},
        }
        for tier in ['PRE_PEAK','PEAK','POST_PEAK']:
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
    """T+1 decline rate base rates, overall + elite tier."""
    careers = qual.sort_values(['batter','year']).reset_index(drop=True)
    arch_q = qual.groupby('archetype')['fp_per_pa'].mean()
    careers['arch_q'] = careers['archetype'].map(arch_q)
    careers['next_fp']     = careers.groupby('batter')['fp_per_pa'].shift(-1)
    careers['next_arch_q'] = careers.groupby('batter')['arch_q'].shift(-1)
    careers['next_year']   = careers.groupby('batter')['year'].shift(-1)
    valid = careers[careers['next_year'] == careers['year'] + 1]

    # FP_per_PA is small (~0.5-1.0), so a -0.1 drop is meaningful
    decline_mask = (valid['next_fp'] - valid['fp_per_pa'] <= -0.10) | \
                   (valid['next_arch_q'] - valid['arch_q'] <= -0.10)
    base = float(decline_mask.mean())
    elite_threshold = qual['fp_per_pa'].quantile(0.90)
    elite = valid[valid['fp_per_pa'] >= elite_threshold]
    elite_decline = float(((elite['next_fp'] - elite['fp_per_pa'] <= -0.10) |
                           (elite['next_arch_q'] - elite['arch_q'] <= -0.10)).mean())

    return {
        'all_t_plus_1_decline_rate': round(base, 3),
        'elite_t_plus_1_decline_rate': round(elite_decline, 3),
        'elite_threshold_fp_per_pa': round(float(elite_threshold), 3),
        'methodology_note': (
            'Decline = FP/PA drop of >= 0.10 OR archetype-mean drop of >= 0.10. '
            'Use elite_decline_rate as base-rate context, not actionable signal '
            '(parallel to SP finding: pre-decline process drops correlate with '
            'mean-reversion, not amplified decline).'
        ),
    }


def build_career_panel(qual):
    """Attach T+1 / T+2 outcomes for comp matching."""
    careers = qual.sort_values(['batter','year']).reset_index(drop=True)
    careers['next_fp']   = careers.groupby('batter')['fp_per_pa'].shift(-1)
    careers['next_arch'] = careers.groupby('batter')['archetype'].shift(-1)
    careers['next_year'] = careers.groupby('batter')['year'].shift(-1)
    careers['t2_fp']     = careers.groupby('batter')['fp_per_pa'].shift(-2)
    careers['t2_year']   = careers.groupby('batter')['year'].shift(-2)

    careers['name'] = careers['player_name'].apply(
        lambda s: s.split(',',1)[1].strip()+' '+s.split(',',1)[0].strip()
                  if isinstance(s, str) and ',' in s else s
    )
    return careers


def main():
    print('Building hitter archetype panel...', flush=True)
    qual = build_ratings_panel()
    print(f'  panel: {len(qual)} batter-years, {qual["batter"].nunique()} unique batters',
          flush=True)

    # Master ratings CSV (human-readable)
    master_cols = [
        'year','rank_in_year','batter','player_name','team','pa','fp_per_pa','t1_fp_projection','data_tier',
        'OVERALL','OVERALL_slope_3yr','OVERALL_career_pct','traj_flag',
        'CONTACT','POWER','DISCIPLINE','SB',
        'Z_CONTACT','O_CONTACT','K_AVOIDANCE','CONTACT_QUALITY','SPRAY_PROFILE',
        'RAW_POWER','LAUNCH_OPTIM','DAMAGE_PROD',
        'PATIENCE','AGGRESSION','SPEED_TOOL','SB_CONVERSION',
        'archetype','contact_subtype','power_subtype','discipline_subtype',
        'sb_tier','spray_archetype','cell',
        'age','age_tier','career_year',
        'bd_C','bd_P','bd_D','boundary_distance','boundary_tier',
        'r_Contact','r_K','r_BABIP','r_xCON','r_SprayEnt',
        'r_ZContact','r_OContact',
        'r_Barrel','r_HardHit','r_SweetSpot','r_EV90','r_PullFB','r_ISO','r_HRrate','r_HRrate_parkadj','hr_parkadj_delta','pf_HR',
        'r_BB','r_Chase','r_HBP','r_ZSwing',
        'r_SBrate','r_Sprint',
        'contact_pct','k_pct','babip','babip_career','babip_delta','babip_luck_flag','xwoba_on_contact',
        'z_contact_pct','o_contact_pct',
        'barrel_pct','hard_hit_pct','sweet_spot_pct','ev90','iso','hr_per_pa','pull_fb_pct',
        'bb_pct','chase_pct','hbp_pct','z_swing_pct',
        'sb_per_opp','sprint_speed',
        'pull_pct','cent_pct','oppo_pct','spray_entropy',
    ]
    # Some cols may be missing in older years — keep only what exists
    master_cols = [c for c in master_cols if c in qual.columns]
    master = qual[master_cols].sort_values(['year','rank_in_year']).copy()

    master['fp_per_pa'] = master['fp_per_pa'].round(3)
    for col, factor, prec in [
        ('contact_pct',100,1),('k_pct',100,1),('babip',1,3),('xwoba_on_contact',1,3),
        ('barrel_pct',100,1),('hard_hit_pct',100,1),('iso',1,3),
        ('hr_per_pa',100,2),('pull_fb_pct',100,1),
        ('bb_pct',100,1),('chase_pct',100,1),('z_swing_pct',100,1),
        ('sb_per_opp',100,1),('sprint_speed',1,1),
        ('pull_pct',100,1),('cent_pct',100,1),('oppo_pct',100,1),
    ]:
        if col in master.columns:
            master[col] = (master[col] * factor).round(prec)
    master.to_csv(OUT_DIR / 'hitter_ratings_master.csv', index=False, encoding='utf-8')
    print('  wrote hitter_ratings_master.csv', flush=True)

    # Career panel (for comps)
    careers = build_career_panel(qual)
    careers.to_parquet(OUT_DIR / 'hitter_archetype_career_panel.parquet', index=False)
    print('  wrote hitter_archetype_career_panel.parquet', flush=True)

    # Definitions
    defs = {k: {'label': v[0], 'description': v[1]} for k,v in ARCHETYPES.items()}
    with open(OUT_DIR / 'hitter_archetype_definitions.json','w',encoding='utf-8') as f:
        json.dump(defs, f, indent=2)
    print('  wrote hitter_archetype_definitions.json', flush=True)

    # Stickiness
    stick = compute_stickiness(qual)
    with open(OUT_DIR / 'hitter_archetype_stickiness.json','w',encoding='utf-8') as f:
        json.dump(stick, f, indent=2)
    print(f'  wrote hitter_archetype_stickiness.json ({len(stick)} archetypes)', flush=True)

    # Decline baselines
    decl = compute_decline_baselines(qual)
    with open(OUT_DIR / 'hitter_decline_baselines.json','w',encoding='utf-8') as f:
        json.dump(decl, f, indent=2)
    print('  wrote hitter_decline_baselines.json', flush=True)

    # Boundary tier validation stats
    careers2 = qual.sort_values(['batter','year']).reset_index(drop=True)
    careers2['next_arch'] = careers2.groupby('batter')['archetype'].shift(-1)
    careers2['next_year'] = careers2.groupby('batter')['year'].shift(-1)
    current = int(qual['year'].max())
    trans = careers2[(careers2['next_year'] == careers2['year'] + 1) &
                     (careers2['next_year'] != current)].copy()
    trans['stayed'] = (trans['archetype'] == trans['next_arch']).astype(int)
    boundary_stats = {}
    for tier in ['EDGE','NEAR_EDGE','SOLID']:
        sub = trans[trans['boundary_tier'] == tier]
        if len(sub) >= 10:
            boundary_stats[tier] = {
                'n_transitions': int(len(sub)),
                'retention_pct': round(100 * float(sub['stayed'].mean()), 1),
            }
    with open(OUT_DIR / 'hitter_boundary_validation.json','w',encoding='utf-8') as f:
        json.dump(boundary_stats, f, indent=2)
    print('  wrote hitter_boundary_validation.json', flush=True)

    print('\nDone.', flush=True)


if __name__ == '__main__':
    main()

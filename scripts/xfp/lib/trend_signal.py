"""Physical-trend engine: who is getting better/worse from fast-stabilizing
physical signals. HITTERS -> bat speed (validated early-warning detector,
see data/research/validation_runs/early_season_bat_speed_2026-06-16.md).
PITCHERS -> fastball velocity (validated + in rp3; induced bat speed was
REJECTED for pitchers, same file Part D).

DISPLAY/CONTEXT ONLY — never moves an rh3/rp3 projection. Bat speed/velo are
NECESSARY-NOT-SUFFICIENT: a rise flags the physical tool moving (breakout watch),
confirmed by the contact/results column as it stabilizes.

Computed from raw statcast_{year}.parquet via exact game_date split — no
leaderboard date-param ambiguity.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
C = ROOT / 'data' / 'research' / 'xfp_cache'
PA_EVENTS = {'single','double','triple','home_run','strikeout','strikeout_double_play',
             'walk','intent_walk','hit_by_pitch','field_out','force_out',
             'grounded_into_double_play','double_play','triple_play','fielders_choice',
             'fielders_choice_out','field_error','sac_fly','sac_fly_double_play','sac_bunt','catcher_interf'}

# stabilization points (split-half r>=0.70), for the min-sample gates below
HIT_MIN_SW_CUR, HIT_MIN_SW_BASE = 80, 200     # bat speed stabilizes ~20 swings; gate well above
PIT_MIN_FB_CUR, PIT_MIN_FB_BASE = 50, 100
# 3-axis hitter physical profile (slice_frontier_2026-06-16): bat speed + attack
# angle (swing path) + fast-swing% (intent) — each adds OOS CV R2 over bat speed
# alone (0.495 -> 0.536), non-redundant. AA_OPT = population-optimal attack angle
# (~15-16deg argmax xwOBACON); attack angle is scored as movement TOWARD this band.
AA_OPT = 15.0


def _hitter_season(y: int, min_sw: int) -> pd.DataFrame:
    df = pd.read_parquet(C / f'statcast_{y}.parquet',
                         columns=['batter', 'type', 'estimated_woba_using_speedangle', 'bat_speed', 'attack_angle'])
    sw = df[df['bat_speed'].notna() & (df['bat_speed'] > 10)].copy()
    sw['_fast'] = (sw['bat_speed'] >= 75).astype(float)
    g = sw.groupby('batter').agg(bat_speed=('bat_speed', 'mean'),
                                 attack_angle=('attack_angle', 'mean'),
                                 fast_swing=('_fast', 'mean'),
                                 n_sw=('bat_speed', 'size'))
    bip = df[df['type'] == 'X']
    g['xwobacon'] = bip.groupby('batter')['estimated_woba_using_speedangle'].mean()
    return g[g['n_sw'] >= min_sw]


def _pitcher_season(y: int, min_fb: int) -> pd.DataFrame:
    df = pd.read_parquet(C / f'statcast_{y}.parquet',
                         columns=['pitcher', 'pitch_type', 'release_speed', 'events', 'woba_value', 'woba_denom'])
    fb = df[df['pitch_type'].isin(['FF', 'SI'])]
    g = fb.groupby('pitcher').agg(velo=('release_speed', 'mean'), n_fb=('release_speed', 'size'))
    pa = df[df['events'].isin(PA_EVENTS)]
    o = pa.groupby('pitcher').agg(wd=('woba_denom', lambda s: s.fillna(0).sum()),
                                  wv=('woba_value', lambda s: s.fillna(0).sum()))
    g['xwoba_allow'] = o['wv'] / o['wd']
    return g[g['n_fb'] >= min_fb]


def hitter_trend_table(cur: int = 2026, base: int = 2025) -> pd.DataFrame:
    """3-axis physical-trend table: bat speed (how hard) + attack angle (swing
    path, scored toward the AA_OPT band) + fast-swing% (intent). Each z-scored;
    z_comp is the equal-weight composite."""
    c, b = _hitter_season(cur, HIT_MIN_SW_CUR), _hitter_season(base, HIT_MIN_SW_BASE)
    t = c.join(b[['bat_speed', 'attack_angle', 'fast_swing', 'xwobacon']], rsuffix='_base', how='inner')
    t['d_bat_speed'] = t['bat_speed'] - t['bat_speed_base']
    t['d_fast_swing'] = t['fast_swing'] - t['fast_swing_base']
    t['d_attack_angle'] = t['attack_angle'] - t['attack_angle_base']
    # direction-aware: positive = swing path moved TOWARD the productive band
    t['aa_toward'] = (t['attack_angle_base'] - AA_OPT).abs() - (t['attack_angle'] - AA_OPT).abs()
    t['d_xwobacon'] = t['xwobacon'] - t['xwobacon_base']
    t['z_bs'] = t['d_bat_speed'] / t['d_bat_speed'].std()
    t['z_fast'] = t['d_fast_swing'] / t['d_fast_swing'].std()
    t['z_aa'] = t['aa_toward'] / t['aa_toward'].std()
    t['z_comp'] = t[['z_bs', 'z_fast', 'z_aa']].mean(axis=1)
    t['z'] = t['z_bs']  # back-compat
    return t


def pitcher_trend_table(cur: int = 2026, base: int = 2025) -> pd.DataFrame:
    c, b = _pitcher_season(cur, PIT_MIN_FB_CUR), _pitcher_season(base, PIT_MIN_FB_BASE)
    t = c.join(b[['velo', 'xwoba_allow']], rsuffix='_base', how='inner')
    t['d_velo'] = t['velo'] - t['velo_base']
    t['d_xwoba_allow'] = t['xwoba_allow'] - t['xwoba_allow_base']
    t['z'] = t['d_velo'] / t['d_velo'].std()
    return t


def _confirm_phrase(prim: int, conf_good: int, metric: str) -> str:
    """Sign-aware confirmation. prim = +1 riser / -1 decliner. conf_good = +1 if
    the confirmation metric moved the GOOD way, -1 the bad way, 0 flat."""
    if conf_good == 0:
        return f"{metric} not yet"
    if conf_good == prim:
        return f"{metric} confirming"
    return f"{metric} diverging (tool moved, {metric} hasn't)"


def tag_hitter(row) -> str:
    """3-axis composite tag. Lists whichever axes are driving the move (|z|>=1.0)."""
    zc, dx = row['z_comp'], row['d_xwobacon']
    parts = []
    if abs(row['z_bs']) >= 1.0:
        parts.append(f"bat speed {row['d_bat_speed']:+.1f}mph")
    if abs(row['z_fast']) >= 1.0:
        parts.append(f"intent {row['z_fast']:+.1f}σ")
    if abs(row['z_aa']) >= 1.0:
        parts.append(f"swing-path {'toward' if row['z_aa'] > 0 else 'off'}-band {row['z_aa']:+.1f}σ")
    drivers = ', '.join(parts) if parts else f"bat speed {row['d_bat_speed']:+.1f}mph"
    conf_good = 1 if dx > 0.02 else (-1 if dx < -0.02 else 0)   # contact up = good
    if zc >= 1.0:
        return f"\U0001f53a breakout watch (phys {zc:+.1f}σ) — {drivers}; {_confirm_phrase(1, conf_good, 'contact')}"
    if zc <= -1.0:
        return f"\U0001f53b decline watch (phys {zc:+.1f}σ) — {drivers}; {_confirm_phrase(-1, conf_good, 'contact')}"
    return f"• stable (phys {zc:+.1f}σ) — bat speed {row['d_bat_speed']:+.1f}mph"


def tag_pitcher(row) -> str:
    z, d, dx = row['z'], row['d_velo'], row['d_xwoba_allow']
    conf_good = 1 if dx < -0.02 else (-1 if dx > 0.02 else 0)   # xwOBA-allowed down = good
    if z >= 1.5:
        return f"\U0001f53a FB velo {d:+.1f} mph ({z:+.1f}σ) — stuff-up watch, {_confirm_phrase(1, conf_good, 'results')}"
    if z <= -1.5:
        return f"\U0001f53b FB velo {d:+.1f} mph ({z:+.1f}σ) — velo decline/health watch, {_confirm_phrase(-1, conf_good, 'results')}"
    return f"• FB velo {d:+.1f} mph ({z:+.1f}σ) — stable"


def trend_for_mlbam(mlbam: int, role: str, hit_tbl=None, pit_tbl=None):
    """Return (tag_str, row_dict) for a resolved MLBAM id, or (None, None)."""
    is_p = str(role).upper() in {'SP', 'RP', 'P'}
    tbl = (pit_tbl if pit_tbl is not None else pitcher_trend_table()) if is_p else \
          (hit_tbl if hit_tbl is not None else hitter_trend_table())
    if mlbam not in tbl.index:
        return None, None
    row = tbl.loc[mlbam]
    return (tag_pitcher(row) if is_p else tag_hitter(row)), row.to_dict()

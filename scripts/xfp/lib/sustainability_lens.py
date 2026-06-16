"""sustainability_lens.py — K%/SwStr%/xwOBACON trajectory lens for /triangulate.

Pulled from pre-built multiyr caches (sp_multiyr.csv, hitters_multiyr_2015_2026.csv,
batter_rolling_features.csv). Display/conviction layer — does NOT modify rh3/rp3/rprs2
point estimates (CLAUDE.md #13).

Verdict taxonomy
----------------
SP/RP:  BREAKOUT_REAL | IMPROVING | STABLE | SOFT_DECLINE | STRUCTURAL_DECLINE |
        INSUFFICIENT_DATA
H:      BREAKOUT_REAL | SUSTAINABLE | NARROW | HOT_STREAK | SOFT_DECLINE |
        STRUCTURAL_DECLINE | INSUFFICIENT_DATA
"""
from __future__ import annotations
import functools, os
import pandas as pd

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))


# ── cached loaders ────────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def _sp_multiyr() -> pd.DataFrame:
    path = os.path.join(_ROOT, 'data', 'research', 'xfp_cache', 'sp_multiyr.csv')
    df = pd.read_csv(path)
    if 'pitcher' in df.columns:
        df['_pid'] = pd.to_numeric(df['pitcher'], errors='coerce')
    return df


@functools.lru_cache(maxsize=1)
def _h_multiyr() -> pd.DataFrame:
    path = os.path.join(_ROOT, 'data', 'research', 'xfp_cache', 'hitters_multiyr_2015_2026.csv')
    return pd.read_csv(path)


@functools.lru_cache(maxsize=1)
def _h_rolling() -> pd.DataFrame:
    path = os.path.join(_ROOT, 'data', 'research', 'xfp_cache', 'batter_rolling_features.csv')
    return pd.read_csv(path)


# ── verdict classifiers ───────────────────────────────────────────────────────

def _classify_sp(k24, k25, k26, sw24, sw25, sw26):
    """Return (verdict, detail) from K%/SwStr% multi-year trend."""
    if k26 is not None and k25 is not None:
        dk = k26 - k25
    elif k25 is not None and k24 is not None:
        dk = k25 - k24
    else:
        return 'INSUFFICIENT_DATA', 'fewer than 2 seasons of K% data'

    dsw = None
    if sw26 is not None and sw25 is not None:
        dsw = sw26 - sw25
    elif sw25 is not None and sw24 is not None:
        dsw = sw25 - sw24

    # Structural: two consecutive years both down >2pp
    structural = (
        k26 is not None and k25 is not None and k24 is not None
        and (k25 - k24) < -0.02
        and (k26 - k25) < -0.02
    )
    if structural:
        total = (k26 - k24) if k24 is not None else dk
        detail = (
            "K% %.1f%%->%.1f%%->%.1f%% (%+.1fpp over 2yr) — consecutive erosion." %
            (k24 * 100, k25 * 100, k26 * 100, total * 100)
        )
        if dsw is not None and dsw < -0.01:
            detail += " SwStr%% also down %+.1fpp." % (dsw * 100,)
        return 'STRUCTURAL_DECLINE', detail

    if dk > 0.03 and dsw is not None and dsw > 0.015:
        return 'BREAKOUT_REAL', (
            "K%% +%.1fpp & SwStr%% +%.1fpp — both metrics confirm breakout." %
            (dk * 100, dsw * 100)
        )

    if dk > 0.02 or (dsw is not None and dsw > 0.01):
        return 'IMPROVING', "K%% %+.1fpp, SwStr%% %+.1fpp — meaningful improvement." % (dk * 100, (dsw or 0) * 100)

    if dk < -0.04 or (dsw is not None and dsw < -0.02):
        return 'SOFT_DECLINE', "K%% %+.1fpp, SwStr%% %+.1fpp — significant step down." % (dk * 100, (dsw or 0) * 100)

    if dk < -0.02 or (dsw is not None and dsw < -0.01):
        return 'SOFT_DECLINE', "K%% %+.1fpp, SwStr%% %+.1fpp — mild erosion." % (dk * 100, (dsw or 0) * 100)

    return 'STABLE', "K%% %+.1fpp, SwStr%% %+.1fpp — within noise band." % (dk * 100, (dsw or 0) * 100)


def _classify_h(xw24, xw25, xw26, xw_l21, k26, brl26):
    """Return (verdict, detail) from xwOBACON trajectory + L21d."""
    curr = xw26 if xw26 is not None else xw25
    prev = xw25 if xw26 is not None else xw24
    if curr is None or prev is None:
        return 'INSUFFICIENT_DATA', 'insufficient multiyr data'

    dyoy = curr - prev

    structural = (
        xw26 is not None and xw25 is not None and xw24 is not None
        and (xw25 - xw24) < -0.03
        and (xw26 - xw25) < -0.03
    )
    if structural:
        total = (xw26 - xw24) if xw24 is not None else dyoy
        return 'STRUCTURAL_DECLINE', (
            "xwOBACON %.3f->%.3f->%.3f (%+.3f over 2yr) — consecutive decline." %
            (xw24, xw25, xw26, total)
        )

    l21_below = xw_l21 is not None and curr is not None and (curr - xw_l21) > 0.04
    narrow = k26 is not None and k26 > 0.30

    if dyoy > 0.04:
        if l21_below:
            return 'HOT_STREAK', (
                "xwOBACON %+.3f YoY but L21d %.3f well below season %.3f — season may be running hot." %
                (dyoy, xw_l21, curr)
            )
        detail = "xwOBACON %.3f (%+.3f YoY)" % (curr, dyoy)
        if xw_l21 is not None:
            detail += ", L21d %.3f (%+.3f vs season)." % (xw_l21, xw_l21 - curr)
        if narrow:
            detail += " K%% %.1f%% limits ceiling." % (k26 * 100,)
            return 'NARROW', detail
        return 'BREAKOUT_REAL', detail

    if -0.02 <= dyoy <= 0.04:
        if l21_below:
            return 'HOT_STREAK', (
                "Season stable (%.3f) but L21d %.3f cooling (%.3f below season)." %
                (curr, xw_l21, curr - xw_l21)
            )
        detail = "xwOBACON %.3f (%+.3f YoY) — stable contact." % (curr, dyoy)
        if xw_l21 is not None:
            detail += " L21d %.3f." % (xw_l21,)
        if narrow:
            detail += " K%% %.1f%% caps upside." % (k26 * 100,)
        return 'SUSTAINABLE', detail

    if -0.05 <= dyoy < -0.02:
        detail = "xwOBACON %+.3f YoY (%.3f->%.3f) — modest erosion." % (dyoy, prev, curr)
        if xw_l21 is not None and xw_l21 > curr:
            detail += " L21d %.3f recovering." % (xw_l21,)
        return 'SOFT_DECLINE', detail

    detail = "xwOBACON %+.3f YoY (%.3f->%.3f) — significant step down." % (dyoy, prev, curr)
    if xw_l21 is not None:
        detail += " L21d %.3f." % (xw_l21,)
    return 'SOFT_DECLINE', detail


# ── public API ────────────────────────────────────────────────────────────────

def sustainability_sp(pitcher_id):
    """Sustainability lens dict for an SP/RP by MLBAM pitcher_id."""
    df = _sp_multiyr()
    rows = pd.DataFrame()
    if '_pid' in df.columns and pitcher_id is not None:
        try:
            rows = df[df['_pid'] == int(pitcher_id)].sort_values('year')
        except (TypeError, ValueError):
            pass

    def _yr(yr, col):
        r = rows[rows['year'] == yr]
        if r.empty or col not in rows.columns:
            return None
        v = r[col].values[0]
        try:
            return float(v) if pd.notna(v) else None
        except (TypeError, ValueError):
            return None

    k24  = _yr(2024, 'k_pct');     k25  = _yr(2025, 'k_pct');     k26  = _yr(2026, 'k_pct')
    sw24 = _yr(2024, 'swstr_pct'); sw25 = _yr(2025, 'swstr_pct'); sw26 = _yr(2026, 'swstr_pct')
    bb24 = _yr(2024, 'bb_pct');    bb25 = _yr(2025, 'bb_pct');    bb26 = _yr(2026, 'bb_pct')
    v25  = _yr(2025, 'avg_velo');  v26  = _yr(2026, 'avg_velo')

    dk  = (k26 - k25)   if (k26  is not None and k25  is not None) else \
          (k25 - k24)   if (k25  is not None and k24  is not None) else None
    ds  = (sw26 - sw25) if (sw26 is not None and sw25 is not None) else \
          (sw25 - sw24) if (sw25 is not None and sw24 is not None) else None

    verdict, detail = _classify_sp(k24, k25, k26, sw24, sw25, sw26)
    return {
        'bucket': 'SP',
        'k_pct_24': k24,   'k_pct_25': k25,   'k_pct_26': k26,
        'swstr_pct_24': sw24, 'swstr_pct_25': sw25, 'swstr_pct_26': sw26,
        'bb_pct_24': bb24, 'bb_pct_25': bb25, 'bb_pct_26': bb26,
        'avg_velo_25': v25, 'avg_velo_26': v26,
        'delta_k_yoy': dk,
        'delta_swstr_yoy': ds,
        'process_verdict': verdict,
        'process_detail': detail,
    }


def sustainability_h(batter_id):
    """Sustainability lens dict for H by MLBAM batter_id."""
    bid = int(batter_id)
    myr   = _h_multiyr()
    hrows = myr[myr['batter'] == bid].sort_values('year')
    rol   = _h_rolling()
    lrow  = rol[rol['batter'] == bid]

    def _yr(yr, col):
        r = hrows[hrows['year'] == yr]
        if r.empty or col not in hrows.columns:
            return None
        v = r[col].values[0]
        try:
            return float(v) if pd.notna(v) else None
        except (TypeError, ValueError):
            return None

    def _l(col):
        if lrow.empty or col not in lrow.columns:
            return None
        v = lrow[col].values[0]
        try:
            return float(v) if pd.notna(v) else None
        except (TypeError, ValueError):
            return None

    xw24 = _yr(2024, 'xwoba_on_contact')
    xw25 = _yr(2025, 'xwoba_on_contact')
    xw26 = _yr(2026, 'xwoba_on_contact')
    brl26 = _yr(2026, 'barrel_pct');   hh26  = _yr(2026, 'hard_hit_pct')
    k26   = _yr(2026, 'k_pct');        bb26  = _yr(2026, 'bb_pct')

    xw_l21  = _l('xwoba_on_contact_l21d')
    brl_l21 = _l('barrel_pct_l21d');   hh_l21 = _l('hard_hit_pct_l21d')
    k_l21   = _l('k_pct_l21d');        n_pa   = _l('n_pa_l21d')

    dyoy = (xw26 - xw25) if (xw26 is not None and xw25 is not None) else \
           (xw25 - xw24) if (xw25 is not None and xw24 is not None) else None

    verdict, detail = _classify_h(xw24, xw25, xw26, xw_l21, k26, brl26)
    return {
        'bucket': 'H',
        'xwobacon_24': xw24, 'xwobacon_25': xw25, 'xwobacon_26': xw26,
        'xwobacon_l21d': xw_l21,
        'barrel_pct_26': brl26,  'barrel_pct_l21d': brl_l21,
        'hard_hit_pct_26': hh26, 'hard_hit_pct_l21d': hh_l21,
        'k_pct_26': k26,   'k_pct_l21d': k_l21,
        'bb_pct_26': bb26,
        'n_pa_l21d': n_pa,
        'delta_yoy': dyoy,
        'process_verdict': verdict,
        'process_detail': detail,
    }


# ── display helpers ───────────────────────────────────────────────────────────

_ICONS = {
    'BREAKOUT_REAL':      'BREAKOUT',
    'IMPROVING':          'IMPROVING',
    'SUSTAINABLE':        'SUSTAINABLE',
    'STABLE':             'STABLE',
    'NARROW':             'NARROW',
    'HOT_STREAK':         'HOT-STREAK',
    'SOFT_DECLINE':       'SOFT_DECLINE',
    'STRUCTURAL_DECLINE': 'STRUCTURAL_DECLINE',
    'INSUFFICIENT_DATA':  'NO_DATA',
}

_VERDICT_EMOJI = {
    'BREAKOUT_REAL':      '[+] ',
    'IMPROVING':          '[^] ',
    'SUSTAINABLE':        '[ok]',
    'STABLE':             '[ok]',
    'NARROW':             '[~] ',
    'HOT_STREAK':         '[~] ',
    'SOFT_DECLINE':       '[!] ',
    'STRUCTURAL_DECLINE': '[!!]',
    'INSUFFICIENT_DATA':  '[-] ',
}


def verdict_label(v):
    return _ICONS.get(v, v)


def verdict_prefix(v):
    return _VERDICT_EMOJI.get(v, '')


def is_structural_decline(sl):
    return sl.get('process_verdict') == 'STRUCTURAL_DECLINE'

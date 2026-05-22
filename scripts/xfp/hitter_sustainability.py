"""Hitter sustainability decomposition (mirrors pitcher_sustainability.py).

Augments rh3 (the validated ROS hitter projection) with a 9-marker Statcast
skill decomposition. The headline ROS number is rh3.per_game.

The 9-marker hitter skill checklist:
  avg_ev          (+) — exit velocity
  ev90            (+) — 90th-percentile exit velocity
  hard_hit_pct    (+) — % of contact at 95+ mph
  barrel_pct      (+) — % of contact in the barrel zone
  xwoba_on_contact (+) — expected wOBA on contact (marker only, not in decomp)
  k_pct           (-) — strikeout rate
  bb_pct          (+) — walk rate
  o_swing_pct     (-) — chase rate (swings outside zone)
  sweet_spot_pct  (+) — % of contact in the 8-32° launch window

Buckets + signals match pitcher tool semantics.

FP scoring (BrownU hitter): R + TB + RBI + BB + HBP + SB − K per game.

Usage:
    python scripts/xfp/hitter_sustainability.py --players "Aaron Judge,Bo Bichette"
    python scripts/xfp/hitter_sustainability.py --scope my-roster
    python scripts/xfp/hitter_sustainability.py --scope fa-pool --min-2026-fp 3.0
"""
from __future__ import annotations
import argparse
import sys
import unicodedata
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'

DIVERGENCE_THRESHOLD = 0.4  # FP/game (hitter scale ~2-4, lower than pitcher's ~10-15)

# (column, direction, label, materiality threshold for "real" change)
MARKERS = [
    ('avg_ev',           '+', 'AvgEV (mph)',  1.0),
    ('ev90',             '+', 'EV90 (mph)',   1.5),
    ('hard_hit_pct',     '+', 'HardHit%',     0.030),
    ('barrel_pct',       '+', 'Barrel%',      0.015),
    ('xwoba_on_contact', '+', 'xwOBAcon',     0.020),
    ('k_pct',            '-', 'K%',           0.020),
    ('bb_pct',           '+', 'BB%',          0.015),
    ('o_swing_pct',      '-', 'Chase%',       0.020),
    ('sweet_spot_pct',   '+', 'SweetSp%',     0.020),
]


def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    parts = re.findall(r'[a-z]+', s)
    return ''.join(sorted(parts))


def load_rh3_map() -> dict:
    """Load rh3 projections keyed by normalized name → {per_game, sigma}.

    No schedule-adjusted variant exists for hitters (unlike rp3) — use
    xfp_rh3_per_game directly.
    """
    try:
        rh3 = pd.read_csv(OUT / 'xfp_rh3_projections.csv')
    except Exception:
        return {}
    rh3['_nk'] = rh3['player_name'].map(_norm)
    out = {}
    for _, r in rh3.iterrows():
        per_game = r.get('xfp_rh3_per_game')
        sigma = r.get('xfp_rh3_sigma')
        out[r['_nk']] = {
            'per_game': float(per_game) if pd.notna(per_game) else None,
            'sigma': float(sigma) if pd.notna(sigma) else None,
        }
    return out


def load_hitter_rows(h: pd.DataFrame, name: str):
    """Return dict {year: row} for the requested hitter."""
    h['_nk'] = h['player_name'].map(_norm)
    nk = _norm(name)
    rows = h[h['_nk'] == nk]
    if rows.empty:
        parts = name.split()
        if len(parts) == 2:
            alt = f"{parts[1]}, {parts[0]}"
            rows = h[h['_nk'] == _norm(alt)]
    if rows.empty:
        return {}
    return {int(r['year']): r for _, r in rows.iterrows()}


def pick_baseline_year(rows: dict, current_year: int = 2026) -> int | None:
    priors = sorted([y for y in rows if y < current_year], reverse=True)
    return priors[0] if priors else None


PA_PER_GAME_LEAGUE = 3.5  # matches rh3 pipeline convention (xfp_rh3_per_game = per_pa × 3.5)


def compute_fp_per_game(row: pd.Series) -> float | None:
    """Hitter BrownU FP per game, using the SAME 3.5 PA-per-game convention as
    rh3 so the sustainability tool's number is directly comparable to rh3.per_game.

    The rh3 model uses PA_PER_GAME_LEAGUE = 3.5 (a league constant); using the
    same here keeps divergence_signal honest. Real per-game PA for everyday
    starters is closer to 4.0-4.5, so the per-game numbers under-count
    counting stats slightly — but this matches the projection we're checking
    against.
    """
    pa = float(row.get('pa', 0) or 0)
    if pa <= 0:
        return None
    fp_total = (float(row.get('r', 0) or 0)
                + float(row.get('tb', 0) or 0)
                + float(row.get('rbi', 0) or 0)
                + float(row.get('bb', 0) or 0)
                + float(row.get('hbp', 0) or 0)
                + float(row.get('sb', 0) or 0)
                - float(row.get('k', row.get('so', 0)) or 0))
    fp_per_pa = fp_total / pa
    return fp_per_pa * PA_PER_GAME_LEAGUE


MIN_2026_GAMES_FOR_CLASSIFY = 20  # hitter games (≈ 80 PA min)


def classify(rows: dict) -> dict:
    """Return per-hitter dict with marker analysis + bucket verdict."""
    if 2026 in rows:
        # Use PA/4 as games proxy
        pa_2026 = float(rows[2026].get('pa', 0) or 0)
        n_games_2026 = pa_2026 / 4.0
    else:
        n_games_2026 = 0

    if 2026 not in rows or n_games_2026 < MIN_2026_GAMES_FOR_CLASSIFY:
        prior_years = sorted([y for y in rows if y < 2026], reverse=True)
        if len(prior_years) < 2:
            if 2026 not in rows:
                return {'bucket': 'NO_2026_DATA',
                        'verdict': 'no 2026 PA in cache (likely new callup or IL)'}
            return {'bucket': 'NO_BASELINE',
                    'verdict': 'only 2026 data — no prior year to compare',
                    'current_year': 2026, 'gs_2026': int(n_games_2026),
                    'fp_2026': compute_fp_per_game(rows[2026]) or 0}
        cur_year = prior_years[0]
        base_year = prior_years[1]
        cur = rows[cur_year]
        prior = rows[base_year]
        small_2026_note = (f' (2026 sample {int(n_games_2026)} games too small; '
                           f'using {cur_year} vs {base_year} as proxy)') if 2026 in rows else ''
    else:
        cur = rows[2026]
        base_year = pick_baseline_year(rows)
        if base_year is None:
            return {
                'bucket': 'NO_BASELINE',
                'verdict': 'only 2026 data — no prior year to compare',
                'current_year': 2026, 'gs_2026': int(n_games_2026),
                'fp_2026': compute_fp_per_game(cur) or 0,
            }
        prior = rows[base_year]
        small_2026_note = ''
        cur_year = 2026

    marker_results = []
    n_favorable = 0
    n_material = 0
    for col, direction, label, thresh in MARKERS:
        try:
            cur_v = float(cur[col])
            prior_v = float(prior[col])
        except (KeyError, ValueError, TypeError):
            continue
        delta = cur_v - prior_v
        favorable = (delta > 0 and direction == '+') or (delta < 0 and direction == '-')
        material = abs(delta) >= thresh
        if favorable:
            n_favorable += 1
        if favorable and material:
            n_material += 1
        marker_results.append({
            'label': label, 'cur': cur_v, 'prior': prior_v, 'delta': delta,
            'favorable': favorable, 'material': material,
        })

    fp_prior = compute_fp_per_game(prior) or 0
    fp_cur = compute_fp_per_game(cur) or 0
    fp_delta = fp_cur - fp_prior

    # Bucket logic — hitter scale: |fp_delta| threshold is 0.5 FP/game (vs 2.0 for pitchers)
    if fp_delta >= 0.5 and n_material >= 7:
        bucket = 'LEGIT'
    elif fp_delta >= 0.5 and n_material >= 5:
        bucket = 'IMPROVING'
    elif fp_delta >= 0.5 and n_material <= 3:
        bucket = 'NOISE'
    elif fp_delta <= -0.5 and n_material <= 2:
        bucket = 'REGRESS'
    elif fp_delta <= -0.5:
        bucket = 'BAD_LUCK'
    elif abs(fp_delta) < 0.5:
        bucket = 'STABLE'
    else:
        bucket = 'MIXED'

    # Skill decomp (drop xwOBA — same as pitcher v2)
    #   K% (favorable: down): each fewer K = +1 FP. PA-per-game ≈ 4.
    #   BB% (favorable: up): each extra BB = +1 FP.
    #   Barrel% (favorable: up): each extra barrel ≈ +0.13 HR × 4 FP.
    pa_per_game = PA_PER_GAME_LEAGUE  # match rh3 convention
    k_delta = float(cur.get('k_pct', 0)) - float(prior.get('k_pct', 0))
    bb_delta = float(cur.get('bb_pct', 0)) - float(prior.get('bb_pct', 0))
    barrel_delta = float(cur.get('barrel_pct', 0)) - float(prior.get('barrel_pct', 0))
    skill_fp_k = -k_delta * pa_per_game * 1.0
    skill_fp_bb = bb_delta * pa_per_game * 1.0
    skill_fp_barrel = barrel_delta * pa_per_game * 0.13 * 4.0
    skill_attributable = skill_fp_k + skill_fp_bb + skill_fp_barrel
    luck_attributable = fp_delta - skill_attributable

    actual_2026_fp = (compute_fp_per_game(rows[2026])
                      if 2026 in rows and float(rows[2026].get('pa', 0) or 0) > 0
                      else None)

    return {
        'bucket': bucket,
        'base_year': base_year, 'cur_year': cur_year,
        'gs_prior': int(float(prior.get('pa', 0)) / 4.0),
        'gs_2026': int(float(cur.get('pa', 0)) / 4.0),
        'fp_prior': fp_prior,
        'fp_2026': fp_cur,
        'fp_delta': fp_delta,
        'n_favorable': n_favorable, 'n_material': n_material,
        'skill_attributable': skill_attributable,
        'luck_attributable': luck_attributable,
        'markers': marker_results,
        'small_2026_note': small_2026_note,
        'actual_2026_fp': actual_2026_fp,
        'actual_2026_n': int(float(rows[2026].get('pa', 0)) / 4.0) if 2026 in rows else 0,
    }


def fetch_hitter_games_recent(mlbam: int, limit: int = 15) -> list[dict]:
    """Most-recent `limit` 2026 games with FP computed from gameLog."""
    from urllib.request import Request, urlopen
    import json
    url = (f'https://statsapi.mlb.com/api/v1/people/{mlbam}/stats?'
           f'stats=gameLog&group=hitting&season=2026')
    try:
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
    except Exception:
        return []
    stats_list = data.get('stats') or []
    splits = stats_list[0].get('splits', []) if stats_list else []
    games = []
    for s in splits:
        st = s.get('stat', {})
        pa = int(st.get('plateAppearances', 0))
        if pa == 0:
            continue
        # FP = R + TB + RBI + BB + HBP + SB − K
        fp = (int(st.get('runs', 0))
              + int(st.get('totalBases', 0))
              + int(st.get('rbi', 0))
              + int(st.get('baseOnBalls', 0))
              + int(st.get('hitByPitch', 0))
              + int(st.get('stolenBases', 0))
              - int(st.get('strikeOuts', 0)))
        games.append({'date': s.get('date'), 'fp': fp, 'pa': pa})
    games.sort(key=lambda x: x['date'] or '', reverse=True)
    return games[:limit]


def staleness_score(mlbam: int | None, rh3_per_game: float | None,
                     rh3_sigma: float | None, last_n_games: int = 15):
    """For hitters: (recent_mean_fp_per_game − rh3.per_game) / (rh3_sigma * PA_PER_GAME).

    The rh3 sigma is per-PA so we scale by PA_PER_GAME to compare to per-game means.
    |score| > 1.5 → rh3 materially stale.
    """
    if (mlbam is None or rh3_per_game is None
            or rh3_sigma is None or rh3_sigma <= 0):
        return None
    games = fetch_hitter_games_recent(mlbam, limit=last_n_games)
    if len(games) < 5:
        return None
    recent_mean = sum(g['fp'] for g in games) / len(games)
    # rh3 sigma is per-PA; convert to per-game scale
    sigma_per_game = rh3_sigma * PA_PER_GAME_LEAGUE
    if sigma_per_game <= 0:
        return None
    return {
        'score': (recent_mean - rh3_per_game) / sigma_per_game,
        'recent_mean': recent_mean,
        'n_sampled': len(games),
    }


def divergence_signal(my_ev: float, rh3_per_game: float, bucket: str) -> tuple[str, str]:
    """Same logic as pitcher tool's divergence_signal, hitter-scaled."""
    if rh3_per_game is None:
        return ('NO_RH3', 'rh3 has no projection for this hitter')
    gap = my_ev - rh3_per_game
    if abs(gap) < DIVERGENCE_THRESHOLD:
        if bucket in ('LEGIT', 'IMPROVING'):
            return ('AGREE_BULLISH', 'sustainability + rh3 both bullish')
        elif bucket in ('REGRESS', 'NOISE'):
            return ('AGREE_BEARISH', 'sustainability + rh3 both bearish')
        else:
            return ('AGREE', 'sustainability + rh3 within noise')
    elif gap > DIVERGENCE_THRESHOLD:
        if bucket in ('LEGIT', 'IMPROVING'):
            return ('BUY_LOW', 'skill signals strong but rh3 conservative — '
                                'model may be lagging the breakout')
        elif bucket == 'NOISE':
            return ('SELL_HIGH', 'production up but skills do not support — '
                                  'rh3 already conservative, regression coming')
        elif bucket == 'BAD_LUCK':
            return ('BUY_LOW', 'production down but skills holding — '
                                'rh3 may catch the bounce')
        else:
            return ('DISAGREE', f'sustainability E[ROS]={my_ev:.2f} '
                                 f'>> rh3={rh3_per_game:.2f} — investigate')
    else:
        if bucket == 'REGRESS':
            return ('SELL_HIGH', 'skill regression real but rh3 still bullish — '
                                  'sell now before model catches up')
        else:
            return ('DISAGREE', f'sustainability E[ROS]={my_ev:.2f} '
                                 f'<< rh3={rh3_per_game:.2f} — investigate')


def ros_expectation(c: dict) -> dict:
    if c['bucket'] in ('NO_2026_DATA', 'NO_BASELINE'):
        return {}
    fp_cur = c['fp_2026']
    fp_prior = c['fp_prior']
    bucket = c['bucket']
    bucket_p = {
        'LEGIT':    [0.40, 0.45, 0.15],
        'IMPROVING':[0.25, 0.50, 0.25],
        'MIXED':    [0.20, 0.40, 0.40],
        'NOISE':    [0.10, 0.30, 0.60],
        'STABLE':   [0.20, 0.60, 0.20],
        'BAD_LUCK': [0.40, 0.40, 0.20],
        'REGRESS':  [0.10, 0.30, 0.60],
    }
    p = bucket_p.get(bucket, [0.25, 0.50, 0.25])
    bull = fp_cur
    base = 0.5 * fp_cur + 0.5 * fp_prior
    bear = fp_prior
    ev = p[0] * bull + p[1] * base + p[2] * bear
    return {'bull': bull, 'base': base, 'bear': bear,
            'p_bull': p[0], 'p_base': p[1], 'p_bear': p[2], 'ev': ev}


# ─── Roster / FA scope helpers ────────────────────────────────────────
HITTER_POSITIONS = {'C', '1B', '2B', '3B', 'SS', 'OF', 'LF', 'CF', 'RF', 'DH', 'UT'}


def get_my_hitter_names() -> list[str]:
    from app.espn_connector import get_my_roster_with_injuries
    df = get_my_roster_with_injuries()
    hitters = df[(df['position'].isin(HITTER_POSITIONS)) & (~df['injured'])]
    return hitters['player_name'].tolist()


def get_fa_hitter_names(min_2026_fp: float, hitters_multiyr: pd.DataFrame) -> list[str]:
    from app.espn_connector import _get_league
    league = _get_league()
    fas = league.free_agents(size=2000)
    fa_hitters = [p.name for p in fas if (p.position or '?') in HITTER_POSITIONS]
    h = hitters_multiyr.copy()
    h['_nk'] = h['player_name'].map(_norm)
    cur_yr = h[h['year'] == 2026]
    by_nk = {r['_nk']: r for _, r in cur_yr.iterrows()}
    qualified = []
    for n in fa_hitters:
        r = by_nk.get(_norm(n))
        if r is not None:
            fp = compute_fp_per_game(r)
            if fp is not None and fp >= min_2026_fp:
                qualified.append((n, fp))
    qualified.sort(key=lambda x: -x[1])
    return [n for n, _ in qualified]


# ─── Output ───────────────────────────────────────────────────────────
BUCKET_EMOJI = {
    'LEGIT': '✓✓ LEGIT', 'IMPROVING': '✓  IMPROV', 'STABLE': '·  STABLE',
    'MIXED': '~  MIXED', 'NOISE': '?  NOISE', 'BAD_LUCK': '!  UNLUCKY',
    'REGRESS': 'x  REGRES', 'NO_2026_DATA': '— no 26', 'NO_BASELINE': '— no prior',
}
SIGNAL_PREFIX = {
    'BUY_LOW': '↑ BUY-LOW   ', 'SELL_HIGH': '↓ SELL-HIGH ',
    'AGREE_BULLISH': '✓ CONFIRM   ', 'AGREE_BEARISH': '✗ CONFIRM   ',
    'AGREE': '· AGREE     ', 'WATCH_REGRESS': '! WATCH-RGR ',
    'WATCH_NOISE': '! WATCH-NSE ', 'DISAGREE': '? INVESTIGAT',
    'NO_RH3': '— no rh3    ',
}


def print_per_hitter(name: str, c: dict, ros: dict, rh3_info: dict | None):
    print(f'\n--- {name} ---')
    bucket = c.get('bucket', '?')
    rh3_per_game = rh3_info.get('per_game') if rh3_info else None
    rh3_sigma = rh3_info.get('sigma') if rh3_info else None
    rh3_str = f"{rh3_per_game:.2f}" if rh3_per_game is not None else "n/a"
    sigma_str = f" σ={rh3_sigma:.3f}" if rh3_sigma is not None else ""
    print(f"  rh3 per_game: {rh3_str}{sigma_str}  ← validated model (headline)")
    print(f"  Bucket: {BUCKET_EMOJI.get(bucket, bucket)}  ← confidence layer on rh3")
    if bucket in ('NO_2026_DATA', 'NO_BASELINE'):
        print(f"  {c.get('verdict','')}")
        if 'fp_2026' in c:
            print(f"  2026 (~{c.get('gs_2026','?')}g): FP/g={c['fp_2026']:.2f}")
        return
    note = c.get('small_2026_note', '')
    if note:
        print(f"  ⚠ {note.strip(' (').rstrip(')')}")
    print(f"  {c['base_year']} (~{c['gs_prior']}g): FP/g={c['fp_prior']:.2f}")
    print(f"  {c['cur_year']} (~{c['gs_2026']}g): FP/g={c['fp_2026']:.2f}  "
          f"Δ={c['fp_delta']:+.2f}  ({c['n_material']}/{len(c['markers'])} skills materially favorable)")
    if c.get('actual_2026_fp') is not None and c['cur_year'] != 2026:
        print(f"  2026 actual (~{c['actual_2026_n']}g): FP/g={c['actual_2026_fp']:.2f}  "
              f"(small sample — not used in classification)")
    print(f"  {'Metric':<13} {'Prior':>8} {'2026':>8} {'Δ':>8}  {'Sign':<3}")
    for m in c['markers']:
        sign = '✓' if m['favorable'] and m['material'] else ('·' if m['favorable'] else '✗')
        # Velocity labels show 1-2 decimals, percentages show 3
        is_velo = 'mph' in m['label']
        prior_str = f"{m['prior']:.2f}" if is_velo else f"{m['prior']:.3f}"
        cur_str = f"{m['cur']:.2f}" if is_velo else f"{m['cur']:.3f}"
        delta_str = f"{m['delta']:+.2f}" if is_velo else f"{m['delta']:+.3f}"
        print(f"  {m['label']:<13} {prior_str:>8} {cur_str:>8} {delta_str:>8}  {sign}")
    print(f"  FP decomposition: skill≈{c['skill_attributable']:+.2f}  "
          f"luck≈{c['luck_attributable']:+.2f}")
    if ros:
        print(f"  sustainability E[ROS]: bull={ros['bull']:.2f} ({ros['p_bull']*100:.0f}%)  "
              f"base={ros['base']:.2f} ({ros['p_base']*100:.0f}%)  "
              f"bear={ros['bear']:.2f} ({ros['p_bear']*100:.0f}%)  "
              f"→ E={ros['ev']:.2f}")
        if rh3_per_game is not None:
            sig, interp = divergence_signal(ros['ev'], rh3_per_game, bucket)
            gap = ros['ev'] - rh3_per_game
            print(f"  Signal: {SIGNAL_PREFIX.get(sig, sig)}  (gap={gap:+.2f} FP/g) — {interp}")


def print_summary_table(results: list[dict]):
    print(f'\n\n=== SUMMARY (sorted by rh3 per_game desc) ===')
    print(f'{"Hitter":<24} {"rh3":>6} {"Sus":<8} {"Bucket":<12} {"2026":>6} {"Skill":>6} {"Signal":<14}')
    print('-' * 95)
    for r in results:
        cls = r['classification']
        bucket = cls.get('bucket', '?')
        rh3_info = r.get('rh3') or {}
        rh3_pg = rh3_info.get('per_game')
        rh3_str = f"{rh3_pg:.2f}" if rh3_pg is not None else "  n/a"
        if bucket in ('NO_2026_DATA', 'NO_BASELINE'):
            print(f"{r['name']:<24} {rh3_str:>6} {'n/a':<8} {BUCKET_EMOJI[bucket]:<12} "
                  f"{cls.get('fp_2026', 0):>6.2f} {'n/a':>6} {'NO_RH3' if rh3_pg is None else '·  AGREE'}")
            continue
        ros = r.get('ros', {})
        my_ev = ros.get('ev', 0)
        sus_str = f"{my_ev:.2f}"
        if rh3_pg is not None:
            sig, _ = divergence_signal(my_ev, rh3_pg, bucket)
        else:
            sig = 'NO_RH3'
        sig_label = SIGNAL_PREFIX.get(sig, sig).strip()
        skill_str = f"{cls.get('skill_attributable', 0):+.2f}"
        print(f"{r['name']:<24} {rh3_str:>6} {sus_str:<8} {BUCKET_EMOJI[bucket]:<12} "
              f"{cls['fp_2026']:>6.2f} {skill_str:>6} {sig_label:<14}")


def main():
    parser = argparse.ArgumentParser(description='Hitter sustainability decomposition')
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument('--players', help='Comma-separated hitter names')
    g.add_argument('--scope', choices=['my-roster', 'fa-pool'])
    parser.add_argument('--min-2026-fp', type=float, default=3.0,
                        help='Min 2026 fp/game floor for FA pool scope (default 3.0)')
    parser.add_argument('--brief', action='store_true',
                        help='Skip per-hitter detail; summary table only')
    args = parser.parse_args()

    h = pd.read_csv(CACHE / 'hitters_multiyr_2015_2026.csv')
    rh3_map = load_rh3_map()

    if args.players:
        names = [n.strip() for n in args.players.split(',')]
    elif args.scope == 'my-roster':
        names = get_my_hitter_names()
        print(f'My roster hitters (healthy, n={len(names)}): {names}')
    else:
        names = get_fa_hitter_names(args.min_2026_fp, h)
        print(f'FA pool hitters with 2026 FP/g >= {args.min_2026_fp} '
              f'(n={len(names)}): {names[:20]}{"..." if len(names)>20 else ""}')

    # MLBAM lookup
    sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))
    try:
        from build_matchup_dashboard import player_mlbam_lookup, _resolve_mlbam_via_api
    except Exception:
        player_mlbam_lookup = lambda x: None
        _resolve_mlbam_via_api = lambda x: None

    results = []
    for n in names:
        rows = load_hitter_rows(h, n)
        cls = classify(rows) if rows else {'bucket': 'NOT_FOUND',
                                              'verdict': f'no rows in hitters_multiyr for "{n}"'}
        ros = ros_expectation(cls)
        rh3_info = rh3_map.get(_norm(n))
        # W3: staleness
        stale = None
        if rh3_info:
            mlbam = player_mlbam_lookup(n) or _resolve_mlbam_via_api(n)
            stale = staleness_score(mlbam, rh3_info.get('per_game'),
                                     rh3_info.get('sigma'))
        results.append({'name': n, 'classification': cls, 'ros': ros,
                        'rh3': rh3_info, 'staleness': stale})
        if not args.brief:
            print_per_hitter(n, cls, ros, rh3_info)
            if stale is not None:
                marker = '⚠' if abs(stale['score']) > 1.5 else '·'
                print(f"  {marker} rh3 staleness: recent_mean={stale['recent_mean']:.2f} "
                      f"vs rh3={rh3_info['per_game']:.2f}  (score={stale['score']:+.2f}σ, "
                      f"n={stale['n_sampled']})")
        # W4: log this call
        try:
            from sustainability_logger import log_call
            sig = None
            if rh3_info and ros and 'ev' in ros:
                sig, _ = divergence_signal(ros['ev'], rh3_info.get('per_game'),
                                            cls.get('bucket'))
            mlbam_for_log = (player_mlbam_lookup(n) or _resolve_mlbam_via_api(n)) if rh3_info else None
            log_call(
                scope=args.scope or 'adhoc',
                player_id=mlbam_for_log,
                player_name=n, kind='hitter',
                bucket=cls.get('bucket'),
                signal=sig,
                model_at_call=(rh3_info or {}).get('per_game'),
                sus_ev_at_call=(ros or {}).get('ev'),
                skill_attributable=cls.get('skill_attributable'),
                luck_attributable=cls.get('luck_attributable'),
                staleness_score=(stale or {}).get('score'),
                n_2026=cls.get('gs_2026'),
            )
        except Exception:
            pass

    def sort_key(r):
        rh3 = r.get('rh3') or {}
        if rh3.get('per_game') is not None:
            return -rh3['per_game']
        ros = r.get('ros', {})
        if ros and 'ev' in ros:
            return -ros['ev']
        return -r['classification'].get('fp_2026', 0)
    results.sort(key=sort_key)
    print_summary_table(results)

    # Actionable signals
    print(f'\n=== ACTIONABLE SIGNALS ===')
    buy_low, sell_high = [], []
    for r in results:
        cls = r['classification']
        ros = r.get('ros') or {}
        rh3 = r.get('rh3') or {}
        if rh3.get('per_game') is None or 'ev' not in ros:
            continue
        sig, interp = divergence_signal(ros['ev'], rh3['per_game'], cls.get('bucket'))
        if sig == 'BUY_LOW':
            buy_low.append((r['name'], rh3['per_game'], ros['ev'], interp))
        elif sig == 'SELL_HIGH':
            sell_high.append((r['name'], rh3['per_game'], ros['ev'], interp))
    if buy_low:
        print('  BUY-LOW (sustainability bullish, rh3 hasn\'t caught up):')
        for n, rh, ev, msg in buy_low:
            print(f'    {n:<22} rh3={rh:.2f}  sus E[ROS]={ev:.2f}  Δ={ev-rh:+.2f}  — {msg}')
    if sell_high:
        print('  SELL-HIGH (sustainability bearish, rh3 still high):')
        for n, rh, ev, msg in sell_high:
            print(f'    {n:<22} rh3={rh:.2f}  sus E[ROS]={ev:.2f}  Δ={ev-rh:+.2f}  — {msg}')
    if not buy_low and not sell_high:
        print('  (none — sustainability and rh3 in agreement)')

    # W3: RH3-STALE
    stale_pos, stale_neg = [], []
    for r in results:
        s = r.get('staleness')
        rh3 = r.get('rh3') or {}
        if s is None or rh3.get('per_game') is None:
            continue
        if abs(s['score']) > 1.5:
            entry = (r['name'], rh3['per_game'], s['recent_mean'], s['score'], s['n_sampled'])
            if s['score'] > 0:
                stale_pos.append(entry)
            else:
                stale_neg.append(entry)
    if stale_pos:
        print('  RH3-STALE (recent runs hot — rh3 will likely catch up):')
        for n, rh, rm, sc, ns in stale_pos:
            print(f'    {n:<22} rh3={rh:.2f}  recent_mean={rm:.2f} (n={ns}g)  staleness={sc:+.2f}σ')
    if stale_neg:
        print('  RH3-STALE (recent runs cold — rh3 may fall):')
        for n, rh, rm, sc, ns in stale_neg:
            print(f'    {n:<22} rh3={rh:.2f}  recent_mean={rm:.2f} (n={ns}g)  staleness={sc:+.2f}σ')


if __name__ == '__main__':
    main()

"""build_subseason_variance_bands — era-general within-player FP variance bands.

Deliverable recommended by the 2026-07-10 sub-season horizon probe
(data/research/boxscore_era/subseason_horizons_2026-07-10.md §4): honest sigma
inputs for /matchup-leverage and /season-sim, keyed by
(player_type H/SP/RP, horizon game/week/month, volume tier T1/T2/T3,
 era 2010-14 / 2015-19 / 2021-25).

Rule 13: variance/decision layer only — never touches rh3/rp3/rprs2.

Two subcommands
  pull     — stratified MLB Stats API gameLog panel: per year, top ~200 hitters
             by PA + top ~80 SPs by GS + top ~60 fantasy-relevant RPs
             (G + 2*(SV+HLD) score), years 2010-2019 + 2021-2025 (2020 short
             season excluded; era buckets match). Batched
             people?personIds=...&hydrate=stats(gameLog) (10 ids/call) with a
             fields= trim, ~0.5 s between requests (polite, <=2 req/s).
             Resume-safe: per player-season gz JSON under
             data/research/xfp_cache/variance_gamelog_raw/{year}/ — existing
             files are skipped; rerun any year chunk freely.
  compute  — per player-season BrownU FP per game/start/appearance, then
             within-player SD at horizons {game, week (Mon-Sun), month} +
             empirical shrinkage k per cell. Writes
               data/research/xfp_cache/subseason_variance_panel.csv  (per
                 player-season x horizon diagnostics)
               data/research/xfp_cache/subseason_variance_bands.csv  (the
                 production bands table consumed by lib/variance_bands.py)

Scoring (BrownU):
  H  FP/game = R + TB + RBI + BB + HBP + SB - K          (all games, PA >= 1)
  SP FP/start = K + IP*3.3 - H - 2*ER - BB - HBP         (starts only)
  RP FP/app   = SP formula + 5*SV + 3*HLD                (relief apps only)

Definitions
  horizon=game : unit = game/start/appearance. sd_fp_per_unit ==
                 sd_fp_total_per_horizon == within-player SD of per-unit FP.
  horizon=week : Mon-Sun windows. sd_fp_per_unit = within-player SD of the
                 window per-unit rate (H: FP/PA, SP: FP/start, RP: FP/app);
                 sd_fp_total_per_horizon = within-player SD of the window
                 total FP. Qualifying windows: H PA>=15, SP starts>=1,
                 RP apps>=2; player needs >=8 qualifying weeks.
  horizon=month: calendar months; H PA>=50, SP starts>=3, RP apps>=6;
                 player needs >=3 qualifying months.
  shrink_k     : empirical shrinkage of a window mean toward the player's
                 season mean. For each qualifying window, regress the
                 leave-window-out season per-unit rate on the window per-unit
                 rate across all windows in the cell; slope b ~= n/(n+k) at
                 the mean window size n_bar, so k = n_bar*(1-b)/b (units of
                 the per-unit denominator: PA for H, starts SP, apps RP).
                 Cells with < MIN_SHRINK_WINDOWS windows fall back to the
                 era-pooled (all-tier) estimate; shrink_k_source says which.

Usage
  python scripts/xfp/build_subseason_variance_bands.py pull --years 2010-2014
  python scripts/xfp/build_subseason_variance_bands.py pull --years 2015-2019
  python scripts/xfp/build_subseason_variance_bands.py pull --years 2021-2025
  python scripts/xfp/build_subseason_variance_bands.py compute
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'data' / 'research' / 'xfp_cache' / 'variance_gamelog_raw'
PANEL_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'subseason_variance_panel.csv'
BANDS_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'subseason_variance_bands.csv'

BASE = 'https://statsapi.mlb.com/api/v1'
SLEEP = 0.5                    # polite: <= 2 req/s
BATCH = 10                     # personIds per hydrate call (payload control)
N_HITTERS, N_SP, N_RP = 200, 80, 60
YEARS_ALL = list(range(2010, 2020)) + list(range(2021, 2026))   # 2020 excluded

ERAS = {'2010-14': range(2010, 2015), '2015-19': range(2015, 2020),
        '2021-25': range(2021, 2026)}

H_FIELDS = ['plateAppearances', 'runs', 'totalBases', 'rbi', 'baseOnBalls',
            'hitByPitch', 'stolenBases', 'strikeOuts']
P_FIELDS = ['strikeOuts', 'inningsPitched', 'hits', 'earnedRuns', 'baseOnBalls',
            'hitBatsmen', 'saves', 'holds', 'gamesStarted', 'gamesPlayed']

MIN_SHRINK_WINDOWS = 150

# qualifying thresholds: (min units per window, min qualifying windows)
QUAL = {
    ('H', 'game'): (1, 40), ('H', 'week'): (15, 8), ('H', 'month'): (50, 3),
    ('SP', 'game'): (1, 10), ('SP', 'week'): (1, 8), ('SP', 'month'): (3, 3),
    ('RP', 'game'): (1, 20), ('RP', 'week'): (2, 8), ('RP', 'month'): (6, 3),
}


def _log(msg):
    print(msg, flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# PULL
# ─────────────────────────────────────────────────────────────────────────────

def _session():
    import requests
    s = requests.Session()
    s.headers.update({'User-Agent': 'plv-clone-research/1.0'})
    return s


def _get(sess, url, **params):
    for attempt in range(4):
        try:
            r = sess.get(url, params=params, timeout=90)
            r.raise_for_status()
            time.sleep(SLEEP)
            return r.json()
        except Exception as e:  # noqa: BLE001 — retry with backoff, then raise
            if attempt == 3:
                raise
            _log(f'    retry {attempt + 1} after {type(e).__name__}: {e}')
            time.sleep(5 * (attempt + 1))
    return None


def _leaderboard(sess, year, group, sort_stat, limit):
    j = _get(sess, f'{BASE}/stats', stats='season', group=group, season=year,
             sortStat=sort_stat, playerPool='all', limit=limit)
    return j['stats'][0]['splits'] if j.get('stats') else []


def _select_year_roster(sess, year):
    """-> list of (player_id, name, role) for one season."""
    out, seen = [], set()
    # hitters: top N_HITTERS by PA
    for s in _leaderboard(sess, year, 'hitting', 'plateAppearances', N_HITTERS):
        pid = s['player']['id']
        if pid not in seen:
            seen.add(pid)
            out.append((pid, s['player']['fullName'], 'H'))
    # pitchers: one wide pull by gamesPlayed captures both SPs and RPs, then a
    # second by inningsPitched to be safe for SP coverage.
    rows = {}
    for sort_stat in ('gamesPlayed', 'inningsPitched'):
        for s in _leaderboard(sess, year, 'pitching', sort_stat, 350):
            rows[s['player']['id']] = s
    sps, rps = [], []
    for pid, s in rows.items():
        st = s['stat']
        gs = int(st.get('gamesStarted') or 0)
        g = int(st.get('gamesPlayed') or 0)
        sv = int(st.get('saves') or 0)
        hld = int(st.get('holds') or 0)
        if g <= 0:
            continue
        if gs >= 10 and gs / g >= 0.5:
            sps.append((gs, pid, s['player']['fullName']))
        elif gs / g < 0.2:
            rps.append((g + 2 * (sv + hld), pid, s['player']['fullName']))
    sps.sort(reverse=True)
    rps.sort(reverse=True)
    p_seen = set()
    for gs, pid, name in sps[:N_SP]:
        if pid not in p_seen:
            p_seen.add(pid)
            out.append((pid, name, 'SP'))
    for score, pid, name in rps[:N_RP]:
        if pid not in p_seen:
            p_seen.add(pid)
            out.append((pid, name, 'RP'))
    return out


def _fields_param(group):
    stat_fields = H_FIELDS if group == 'hitting' else P_FIELDS
    return ','.join(['people', 'id', 'fullName', 'stats', 'splits', 'date',
                     'stat'] + stat_fields)


def _pull_year(sess, year):
    ydir = RAW / str(year)
    ydir.mkdir(parents=True, exist_ok=True)
    manifest_path = ydir / 'roster.json'
    if manifest_path.exists():
        roster = [tuple(r) for r in json.loads(manifest_path.read_text())]
        _log(f'  {year}: roster manifest cached ({len(roster)} players)')
    else:
        roster = _select_year_roster(sess, year)
        manifest_path.write_text(json.dumps(roster))
        _log(f'  {year}: selected {len(roster)} players '
             f'(H={sum(1 for r in roster if r[2] == "H")}, '
             f'SP={sum(1 for r in roster if r[2] == "SP")}, '
             f'RP={sum(1 for r in roster if r[2] == "RP")})')

    def fpath(pid, role):
        tag = 'H' if role == 'H' else 'P'
        return ydir / f'{tag}_{pid}.json.gz'

    todo = [(pid, name, role) for pid, name, role in roster
            if not fpath(pid, role).exists()]
    if not todo:
        _log(f'  {year}: all {len(roster)} player-seasons cached — skip')
        return 0
    _log(f'  {year}: pulling {len(todo)} player-seasons '
         f'({len(roster) - len(todo)} cached)')
    n_saved = 0
    for group, role_filter in (('hitting', ('H',)), ('pitching', ('SP', 'RP'))):
        subset = [t for t in todo if t[2] in role_filter]
        role_by_id = {pid: role for pid, _, role in subset}
        for i in range(0, len(subset), BATCH):
            chunk = subset[i:i + BATCH]
            ids = ','.join(str(pid) for pid, _, _ in chunk)
            j = _get(sess, f'{BASE}/people', personIds=ids,
                     hydrate=f'stats(group=[{group}],type=[gameLog],season={year})',
                     fields=_fields_param(group))
            got = {p['id']: p for p in j.get('people', [])}
            for pid, name, role in chunk:
                p = got.get(pid)
                splits = []
                if p:
                    for st in p.get('stats', []):
                        splits = st.get('splits', []) or splits
                rec = {'id': pid, 'name': name, 'role': role, 'season': year,
                       'games': [{'date': s.get('date'), **(s.get('stat') or {})}
                                 for s in splits]}
                with gzip.open(fpath(pid, role), 'wt', encoding='utf-8') as f:
                    json.dump(rec, f)
                n_saved += 1
            _log(f'    {year} {group}: {min(i + BATCH, len(subset))}/{len(subset)} '
                 f'player-seasons saved')
    return n_saved


def cmd_pull(years):
    sess = _session()
    t0 = time.time()
    total = 0
    for y in years:
        total += _pull_year(sess, y)
        _log(f'  [{time.time() - t0:6.0f}s] year {y} done (cumulative new: {total})')
    _log(f'PULL DONE: {total} new player-seasons in {time.time() - t0:.0f}s')


# ─────────────────────────────────────────────────────────────────────────────
# COMPUTE
# ─────────────────────────────────────────────────────────────────────────────

def _ip(v) -> float:
    """'6.1' -> 6.333..., '0.2' -> 0.667."""
    try:
        s = str(v or '0')
        whole, _, frac = s.partition('.')
        return int(whole or 0) + int(frac or 0) / 3.0
    except Exception:  # noqa: BLE001
        return 0.0


def _f(g, k) -> float:
    try:
        return float(g.get(k) or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def _game_rows(rec):
    """-> DataFrame(date, fp, units) of scoring-eligible games for one
    player-season. units: PA for H, 1 per start (SP) / appearance (RP)."""
    role = rec['role']
    rows = []
    for g in rec.get('games', []):
        d = g.get('date')
        if not d:
            continue
        if role == 'H':
            pa = _f(g, 'plateAppearances')
            if pa < 1:
                continue
            fp = (_f(g, 'runs') + _f(g, 'totalBases') + _f(g, 'rbi')
                  + _f(g, 'baseOnBalls') + _f(g, 'hitByPitch')
                  + _f(g, 'stolenBases') - _f(g, 'strikeOuts'))
            rows.append((d, fp, pa))
        else:
            gs = _f(g, 'gamesStarted')
            if role == 'SP' and gs < 1:
                continue          # SP variance = starts only (relief cameos out)
            if role == 'RP' and gs >= 1:
                continue          # RP variance = relief appearances only
            fp = (_f(g, 'strikeOuts') + _ip(g.get('inningsPitched')) * 3.3
                  - _f(g, 'hits') - 2 * _f(g, 'earnedRuns')
                  - _f(g, 'baseOnBalls') - _f(g, 'hitBatsmen'))
            if role == 'RP':
                from plv_clone.fantasy.scoring import DEFAULT as _SC
                fp += _SC.sv * _f(g, 'saves') + _SC.hd * _f(g, 'holds')
            rows.append((d, fp, 1.0))
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=['date', 'fp', 'units'])
    df['date'] = pd.to_datetime(df['date'])
    return df.sort_values('date').reset_index(drop=True)


def _windows(df, horizon):
    """Aggregate game rows to horizon windows -> DataFrame(fp, units)."""
    if horizon == 'game':
        return df[['fp', 'units']].copy()
    if horizon == 'week':
        key = df['date'].dt.to_period('W-SUN')      # Mon-Sun weeks
    else:
        key = df['date'].dt.to_period('M')
    return df.groupby(key)[['fp', 'units']].sum().reset_index(drop=True)


def _era_of(year):
    for era, rng in ERAS.items():
        if year in rng:
            return era
    return None


def cmd_compute():
    t0 = time.time()
    panel_rows = []          # per player-season x horizon
    shrink_obs = []          # per qualifying window: (ptype, horizon, era, tier?, x, y, n)
    seasons = []             # (ptype, era, year, pid, season_units) for terciles

    files = sorted(RAW.glob('*/[HP]_*.json.gz'))
    _log(f'compute: {len(files)} cached player-season files')
    per_player = {}          # (ptype, era, year, pid) -> dict of horizon stats
    for i, fp_path in enumerate(files):
        if i % 500 == 0:
            _log(f'  [{time.time() - t0:5.0f}s] {i}/{len(files)}')
        with gzip.open(fp_path, 'rt', encoding='utf-8') as f:
            rec = json.load(f)
        era = _era_of(rec['season'])
        if era is None:
            continue
        df = _game_rows(rec)
        if df is None or df.empty:
            continue
        ptype = rec['role']
        season_units = float(df['units'].sum())     # PA / starts / apps
        season_fp = float(df['fp'].sum())
        key = (ptype, era, rec['season'], rec['id'])
        seasons.append((*key, season_units))
        hstats = {}
        for horizon in ('game', 'week', 'month'):
            min_units, min_windows = QUAL[(ptype, horizon)]
            w = _windows(df, horizon)
            q = w[w['units'] >= min_units]
            if len(q) < min_windows:
                continue
            rate = q['fp'] / q['units']
            hstats[horizon] = {
                'n_windows': int(len(q)),
                'var_per_unit': float(rate.var(ddof=1)),
                'var_total': float(q['fp'].var(ddof=1)),
                'mean_total': float(q['fp'].mean()),
                'mean_rate': float(season_fp / season_units) if season_units else np.nan,
            }
            # shrink observations: leave-window-out season rate vs window rate
            if season_units > q['units'].max():
                for fp_w, u_w in zip(q['fp'], q['units']):
                    rest_u = season_units - u_w
                    if rest_u <= 0:
                        continue
                    y = (season_fp - fp_w) / rest_u
                    shrink_obs.append((ptype, horizon, era, rec['season'],
                                       rec['id'], fp_w / u_w, y, u_w))
        if hstats:
            per_player[key] = hstats

    # volume terciles within (ptype, era)
    sdf = pd.DataFrame(seasons, columns=['ptype', 'era', 'year', 'pid', 'season_units'])
    sdf['tier'] = (sdf.groupby(['ptype', 'era'])['season_units']
                   .transform(lambda s: pd.qcut(s.rank(method='first'), 3,
                                                labels=['T1', 'T2', 'T3'])))
    tier_of = {(r.ptype, r.era, r.year, r.pid): str(r.tier) for r in sdf.itertuples()}

    for key, hstats in per_player.items():
        ptype, era, year, pid = key
        tier = tier_of.get(key)
        for horizon, st in hstats.items():
            panel_rows.append({
                'ptype': ptype, 'era': era, 'year': year, 'pid': pid,
                'tier': tier, 'horizon': horizon, **st})
    panel = pd.DataFrame(panel_rows)
    panel.to_csv(PANEL_CSV, index=False)
    _log(f'panel: {len(panel)} player-season x horizon rows -> {PANEL_CSV.name}')

    sh = pd.DataFrame(shrink_obs, columns=['ptype', 'horizon', 'era', 'year',
                                           'pid', 'x', 'y', 'n_units'])
    sh['tier'] = [tier_of.get((p, e, yr, pid)) for p, e, yr, pid in
                  zip(sh['ptype'], sh['era'], sh['year'], sh['pid'])]

    def _fit_k(g):
        """slope of loo season rate on window rate -> k = n_bar*(1-b)/b."""
        if len(g) < 30:
            return np.nan, len(g)
        x, y = g['x'].to_numpy(float), g['y'].to_numpy(float)
        vx = x.var()
        if vx <= 0:
            return np.nan, len(g)
        b = float(np.cov(x, y, ddof=1)[0, 1] / x.var(ddof=1))
        b = min(max(b, 1e-4), 0.9999)
        n_bar = float(g['n_units'].mean())
        return float(np.clip(n_bar * (1 - b) / b, 0.0, 20000.0)), len(g)

    # era-pooled shrink (fallback) then per-cell
    k_pooled = {}
    for (pt, hz, era), g in sh.groupby(['ptype', 'horizon', 'era']):
        k_pooled[(pt, hz, era)] = _fit_k(g)

    bands = []
    for (pt, hz, era, tier), g in panel.groupby(['ptype', 'horizon', 'era', 'tier'],
                                                observed=True):
        cell_sh = sh[(sh['ptype'] == pt) & (sh['horizon'] == hz)
                     & (sh['era'] == era) & (sh['tier'] == tier)]
        k_cell, nw = _fit_k(cell_sh)
        if nw >= MIN_SHRINK_WINDOWS and np.isfinite(k_cell):
            k, ksrc = k_cell, 'cell'
        else:
            k, ksrc = k_pooled.get((pt, hz, era), (np.nan, 0))[0], 'era_pooled'
        bands.append({
            'player_type': pt, 'horizon': hz, 'tier': tier, 'era': era,
            'sd_fp_per_unit': round(float(np.sqrt(g['var_per_unit'].mean())), 4),
            'sd_fp_total_per_horizon': round(float(np.sqrt(g['var_total'].mean())), 3),
            'mean_fp_total_per_horizon': round(float(g['mean_total'].mean()), 3),
            'shrink_k': round(float(k), 2) if np.isfinite(k) else np.nan,
            'shrink_k_source': ksrc,
            'n_player_seasons': int(len(g)),
            'n_windows': int(g['n_windows'].sum()),
        })
    bands_df = pd.DataFrame(bands).sort_values(
        ['player_type', 'horizon', 'era', 'tier']).reset_index(drop=True)
    bands_df.to_csv(BANDS_CSV, index=False)
    _log(f'bands: {len(bands_df)} cells -> {BANDS_CSV}')

    # sanity summary
    _log('\n== sanity ==')
    for pt in ('H', 'SP', 'RP'):
        for hz in ('game', 'week', 'month'):
            sub = bands_df[(bands_df.player_type == pt) & (bands_df.horizon == hz)]
            if sub.empty:
                continue
            _log(f'  {pt:>2} {hz:<5} sd_per_unit {sub.sd_fp_per_unit.mean():7.4f}  '
                 f'sd_total {sub.sd_fp_total_per_horizon.mean():6.2f}  '
                 f'k~{sub.shrink_k.median():8.1f}  n={sub.n_player_seasons.sum()}')
    h = bands_df[(bands_df.player_type == 'H')]
    wk = h[h.horizon == 'week']['sd_fp_per_unit'].mean()
    mo = h[h.horizon == 'month']['sd_fp_per_unit'].mean()
    if mo:
        _log(f'  sqrt-n check: hitter weekly/monthly per-PA SD ratio = '
             f'{wk / mo:.2f} (expect ~2.0)')
    _log(f'COMPUTE DONE in {time.time() - t0:.0f}s')


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p_pull = sub.add_parser('pull')
    p_pull.add_argument('--years', default='2010-2025',
                        help='e.g. 2010-2014 or 2015,2016 (2020 always skipped)')
    sub.add_parser('compute')
    args = ap.parse_args()
    if args.cmd == 'pull':
        years = []
        for part in args.years.split(','):
            part = part.strip()
            if '-' in part:
                a, b = part.split('-')
                years += [y for y in range(int(a), int(b) + 1)]
            elif part:
                years.append(int(part))
        years = [y for y in sorted(set(years)) if y in YEARS_ALL]
        _log(f'pull years: {years}')
        cmd_pull(years)
    else:
        cmd_compute()


if __name__ == '__main__':
    sys.exit(main())

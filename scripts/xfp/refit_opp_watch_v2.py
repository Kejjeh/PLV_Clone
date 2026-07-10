"""refit_opp_watch_v2.py — panel-data refit + chronological backtest for opponent_action_predictor.

Pre-registered design: data/research/validation_runs/opp_watch_v2_refit_2026-07-10.md
(header frozen BEFORE this script produced results). Do not change the event
window, split, features, or metric here without re-pre-registering.

Outputs:
  - console report (v1 vs v2 held-out top-12 hit rates, per team + pooled)
  - data/research/opp_watch_v2_weights.json  (fitted coefficients, refit on
    the FULL window only if the held-out gate passes; the gate decision itself
    uses the train-only fit)

Usage:
  PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/refit_opp_watch_v2.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from plv_clone.paths import ROOT
from plv_clone.utils.name_match import join_key as _norm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from opponent_action_predictor import PROFILES, DEFAULT_PROFILE, _score_player_for_add

RES = ROOT / 'data' / 'research'
TRI = RES / 'triangulate_universe'
TX_PARQ = RES / 'transactions_history.parquet'
PANEL = RES / 'player_projection_history.parquet'
PL_CACHE = RES / 'pl_cache'
BOX_H = RES / 'xfp_cache' / 'boxscore_hitters.parquet'
BOX_P = RES / 'xfp_cache' / 'boxscore_pitchers.parquet'
WEIGHTS_OUT = RES / 'opp_watch_v2_weights.json'

WIN_START, WIN_END = date(2026, 6, 5), date(2026, 7, 9)
FEATS = ['pl', 'traj', 'model', 'outcome', 'role', 'd7', 'd14', 'fp_l7', 'v1_prior']


# ---------------------------------------------------------------- data loads
def load_panel():
    p = pd.read_parquet(PANEL)
    p['snapshot_date'] = pd.to_datetime(p['snapshot_date']).dt.date
    p['k'] = p['player_name'].map(_norm)
    return p


def load_adds():
    tx = pd.read_parquet(TX_PARQ)
    tx['d'] = pd.to_datetime(tx['date']).dt.date
    tx = tx.sort_values('ts_ms').reset_index(drop=True)
    adds = tx[tx['action_str'].str.contains('ADD', na=False)].copy()
    adds = adds[(adds['d'] >= WIN_START) & (adds['d'] <= WIN_END)]
    return tx, adds


def resolve_add_mlbam(adds: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """mlbam from ledger when present; else unambiguous normalized full-name match vs panel."""
    name_map = panel.groupby('k')['mlbam_id'].nunique()
    uniq = set(name_map[name_map == 1].index)
    k2id = panel[panel['k'].isin(uniq)].groupby('k')['mlbam_id'].first().to_dict()
    out = []
    for _, r in adds.iterrows():
        mid = r['mlbam_id']
        if pd.isna(mid):
            mid = k2id.get(_norm(r['player_name']), np.nan)  # skip-on-ambiguous
        out.append(mid)
    adds = adds.copy()
    adds['mlbam_res'] = out
    return adds


# ------------------------------------------------- ownership reconstruction
def build_ownership_ledger(tx: pd.DataFrame):
    """Rostered-name-key set per date, from 06-04 roster json + tx roll-forward."""
    rosters = json.load(open(TRI / 'all_team_rosters.json'))
    rostered = {_norm(p['name']) for team in rosters.values() for p in team}
    baseline = date(2026, 6, 4)
    events = tx[tx['d'] >= baseline].sort_values('ts_ms')
    # daily snapshots: state as of END of each date
    states, cur = {}, set(rostered)
    all_dates = pd.date_range(baseline, WIN_END + timedelta(days=1)).date
    ev_by_date = defaultdict(list)
    for _, r in events.iterrows():
        ev_by_date[r['d']].append(r)
    for dt in all_dates:
        for r in ev_by_date.get(dt, []):
            k = _norm(r['player_name'])
            if 'ADD' in r['action_str']:
                cur.add(k)
            else:
                cur.discard(k)
        states[dt] = frozenset(cur)
    return states


# ----------------------------------------------------------- pl_cache as-of
_PL_PAT = {
    'SP': re.compile(r'pl_(?:sps_)?top100_(\d{4}-\d{2}-\d{2})\.json$'),
    'H': re.compile(r'pl_hitters_top150_(\d{4}-\d{2}-\d{2})\.json$'),
    'RP': re.compile(r'pl_closers_(\d{4}-\d{2}-\d{2})\.json$'),
}


def load_pl_series():
    """bucket -> sorted [(date, {name_key: rank})]."""
    series = {b: [] for b in _PL_PAT}
    for f in PL_CACHE.glob('*.json'):
        for b, pat in _PL_PAT.items():
            m = pat.match(f.name)
            if not m:
                continue
            try:
                d = date.fromisoformat(m.group(1))
                ranks = json.load(open(f, encoding='utf-8')).get('ranks') or []
                if isinstance(ranks, dict):
                    ranks = list(ranks.items())
                series[b].append((d, {_norm(n): int(r) for n, r in ranks}))
            except Exception:
                pass
    for b in series:
        series[b].sort(key=lambda t: t[0])
    return series


def pl_rank_asof(series, bucket, asof, k):
    best = None
    for d, ranks in series.get(bucket, []):
        if d <= asof:
            best = ranks
        else:
            break
    return best.get(k) if best else None


# ------------------------------------------------- nightly triangulate as-of
def nightly_asof(asof: date, cache={}):
    """Latest triangulate_nightly file dated <= asof; backfill to earliest (06-23)."""
    files = sorted(TRI.glob('triangulate_nightly_????-??-??.csv'))
    dates = [date.fromisoformat(f.stem[-10:]) for f in files]
    pick = None
    for f, d in zip(files, dates):
        if d <= asof:
            pick = f
    if pick is None:
        pick = files[0]  # earliest (2026-06-23) backfill for pre-06-23 events
    if pick not in cache:
        t = pd.read_csv(pick, usecols=['player_name', 'arche_traj'])
        t['k'] = t['player_name'].map(_norm)
        cache[pick] = t.drop_duplicates('k').set_index('k')['arche_traj'].to_dict()
    return cache[pick]


# ------------------------------------------------------------- boxscore FP
def load_box():
    h = pd.read_parquet(BOX_H)[['game_date', 'mlbam_id', 'fp_h']].rename(columns={'fp_h': 'fp'})
    p = pd.read_parquet(BOX_P)[['game_date', 'mlbam_id', 'gs', 'fp_sp', 'fp_rp']]
    p['fp'] = np.where(p['gs'] > 0, p['fp_sp'], p['fp_rp'])
    box = pd.concat([h[['game_date', 'mlbam_id', 'fp']], p[['game_date', 'mlbam_id', 'fp']]])
    box['game_date'] = pd.to_datetime(box['game_date']).dt.date
    return box


def fp_l7(box, mid, d):
    if pd.isna(mid):
        return 0.0
    m = box[(box['mlbam_id'] == mid) & (box['game_date'] < d) & (box['game_date'] >= d - timedelta(days=7))]
    return float(np.clip(m['fp'].sum() / 30.0, 0, 1.5))


# ------------------------------------------------------------ feature build
def snap_lookup(panel):
    dates = sorted(panel['snapshot_date'].unique())
    by_date = {d: g.set_index('mlbam_id') for d, g in panel.groupby('snapshot_date')}
    return dates, by_date


def nearest_snap(dates, target, tol=3):
    cands = [d for d in dates if abs((d - target).days) <= tol]
    return min(cands, key=lambda d: abs((d - target).days)) if cands else None


def v1_row_from_feats(f):
    """Adapter: as-of features -> the row dict v1's _score_player_for_add reads."""
    return pd.Series({
        'pl_rank': f['pl_rank_raw'], 'arche_traj': f['arche_traj_raw'],
        'model_rank': f['model_rank_raw'], 'model_rep_delta': f['rep_delta_raw'],
        'model_recform': f['recform_raw'], 'bucket': f['bucket'],
        'model_signal': f['signal_raw'],
    })


def build_events():
    panel = load_panel()
    tx, adds = load_adds()
    adds = resolve_add_mlbam(adds, panel)
    ledger = build_ownership_ledger(tx)
    pl_series = load_pl_series()
    box = load_box()
    snap_dates, snap_by_date = snap_lookup(panel)

    events, skipped = [], defaultdict(int)
    for _, ev in adds.iterrows():
        D, team = ev['d'], ev['team_name']
        asof_cands = [d for d in snap_dates if d < D]
        if not asof_cands:
            skipped['no_prior_snapshot'] += 1
            continue
        A = max(asof_cands)
        if (D - A).days > 7:
            skipped['snapshot_too_stale'] += 1
            continue
        mid = ev['mlbam_res']
        snap = snap_by_date[A]
        if pd.isna(mid) or mid not in snap.index:
            skipped['add_player_not_in_snapshot'] += 1
            continue
        # candidate pool: snapshot A minus rostered as of end of A (added player forced in)
        rost = ledger.get(A, frozenset())
        pool = snap[~snap['k'].isin(rost)]
        if mid not in pool.index:
            pool = pd.concat([pool, snap.loc[[mid]]])
        # trailing snapshots for delta-rank
        A7 = nearest_snap(snap_dates, A - timedelta(days=7))
        A14 = nearest_snap(snap_dates, A - timedelta(days=14))
        traj_map = nightly_asof(A)
        profile = PROFILES.get(team, DEFAULT_PROFILE)

        rows = []
        for pid, r in pool.iterrows():
            b = {'H': 'H', 'SP': 'SP', 'RP': 'RP'}.get(r['player_type'], 'H')
            plr = pl_rank_asof(pl_series, b, A, r['k'])
            pl_den = 150.0 if b == 'H' else 100.0
            pl_s = max(0.0, 1 - plr / pl_den) if plr else 0.0
            traj_raw = str(traj_map.get(r['k']) or '')
            traj_s = 1.0 if 'TRENDING_UP' in traj_raw else (0.5 if 'STABLE' in traj_raw else 0.0)
            mrank = int(r['rank'])
            model_s = max(0.0, 1 - mrank / 100.0)
            rd = float(r['replacement_delta']) if pd.notna(r['replacement_delta']) else 0.0
            rf = float(r['recency_form_gap']) if pd.notna(r['recency_form_gap']) else 0.0
            outcome_s = float(np.clip((rd + 0.5 * rf) / 1.5, 0, 1))
            sig = str(r['signal'])
            role_s = 1.0 if (b == 'RP' and sig == 'add') else (0.4 if b == 'RP' else 0.0)

            def _drank(Aprev):
                if Aprev is None:
                    return 0.0
                prev = snap_by_date[Aprev]
                if pid not in prev.index:
                    return 0.0
                pr = prev.loc[pid]
                pr_rank = int(pr['rank']) if not isinstance(pr, pd.DataFrame) else int(pr['rank'].iloc[0])
                return float(np.clip((pr_rank - mrank) / 100.0, -1, 1))

            f = {
                'pl': pl_s, 'traj': traj_s, 'model': model_s, 'outcome': outcome_s,
                'role': role_s, 'd7': _drank(A7), 'd14': _drank(A14),
                'fp_l7': fp_l7(box, pid, D),
                # raw fields for the v1 adapter
                'pl_rank_raw': plr, 'arche_traj_raw': traj_raw, 'model_rank_raw': mrank,
                'rep_delta_raw': rd, 'recform_raw': rf, 'bucket': b, 'signal_raw': sig,
            }
            v1_s, _ = _score_player_for_add(v1_row_from_feats(f), profile)
            f['v1_prior'] = v1_s
            f.update({'mlbam_id': pid, 'label': int(pid == mid)})
            rows.append(f)
        edf = pd.DataFrame(rows)
        events.append({'team': team, 'date': D, 'ts': ev['ts_ms'], 'added_mlbam': mid,
                       'added_name': ev['player_name'], 'asof': A, 'df': edf})
    return events, dict(skipped)


# ----------------------------------------------------------------- backtest
def hit_rates(events, scorer, ks=(12, 25)):
    per_team = defaultdict(lambda: defaultdict(int))
    ranks = []
    for ev in events:
        df = ev['df']
        s = scorer(df, ev['team'])
        order = np.argsort(-s, kind='stable')
        pos = int(np.where(df['label'].values[order] == 1)[0][0]) + 1
        ranks.append(pos)
        per_team[ev['team']]['n'] += 1
        for k in ks:
            per_team[ev['team']][f'top{k}'] += int(pos <= k)
    pooled = {'n': len(events), 'median_rank': float(np.median(ranks)) if ranks else None}
    for k in ks:
        pooled[f'top{k}'] = sum(t[f'top{k}'] for t in per_team.values())
        pooled[f'top{k}_rate'] = pooled[f'top{k}'] / max(1, pooled['n'])
    return pooled, {t: dict(v) for t, v in per_team.items()}, ranks


def v1_scorer(df, team):
    return df['v1_prior'].values


def make_v2_scorer(coefs, intercept):
    def score(df, team):
        X = df[FEATS].values
        return X @ np.array([coefs[f] for f in FEATS]) + intercept
    return score


def fit_v2(events):
    from sklearn.linear_model import LogisticRegression
    X = pd.concat([ev['df'][FEATS + ['label']] for ev in events], ignore_index=True)
    clf = LogisticRegression(C=1.0, class_weight='balanced', max_iter=2000)
    clf.fit(X[FEATS].values, X['label'].values)
    coefs = dict(zip(FEATS, clf.coef_[0].tolist()))
    return coefs, float(clf.intercept_[0])


def main():
    events, skipped = build_events()
    events.sort(key=lambda e: e['ts'])
    n = len(events)
    print(f'Usable events: {n}  (skipped: {skipped})')
    per_team_n = defaultdict(int)
    for ev in events:
        per_team_n[ev['team']] += 1
    print('per-team n:', dict(sorted(per_team_n.items(), key=lambda x: -x[1])))
    if n < 40:
        print('UNDERPOWERED: <40 usable adds in window. Keeping v1.')
        return

    split = int(round(n * 0.70))
    train, test = events[:split], events[split:]
    print(f'Chronological split: train {len(train)} events '
          f'({train[0]["date"]} -> {train[-1]["date"]}), '
          f'test {len(test)} events ({test[0]["date"]} -> {test[-1]["date"]})')

    coefs, b0 = fit_v2(train)
    print('\nTrain-fit v2 coefficients (pooled logistic):')
    for f in FEATS:
        print(f'  {f:10s} {coefs[f]:+.4f}')
    print(f'  intercept  {b0:+.4f}')

    v2 = make_v2_scorer(coefs, b0)
    for name, scorer in [('v1', v1_scorer), ('v2', v2)]:
        for label, evs in [('TRAIN', train), ('TEST (held-out)', test)]:
            pooled, per_team, _ = hit_rates(evs, scorer)
            print(f'\n{name} — {label}: top12 {pooled["top12"]}/{pooled["n"]} '
                  f'({pooled["top12_rate"]:.1%})  top25 {pooled["top25"]}/{pooled["n"]} '
                  f'({pooled["top25_rate"]:.1%})  median rank {pooled["median_rank"]:.0f}')
            if 'TEST' in label:
                for t, v in sorted(per_team.items(), key=lambda x: -x[1]['n']):
                    print(f'    {t:28s} n={v["n"]:2d}  top12 {v["top12"]}/{v["n"]}')

    # sensitivity: pooled excluding Josh's own team
    test_opp = [e for e in test if e['team'] != 'New York Ligers']
    for name, scorer in [('v1', v1_scorer), ('v2', v2)]:
        pooled, _, _ = hit_rates(test_opp, scorer)
        print(f'{name} — TEST excl. NYL: top12 {pooled["top12"]}/{pooled["n"]} ({pooled["top12_rate"]:.1%})')

    # gate
    p_v1, _, _ = hit_rates(test, v1_scorer)
    p_v2, _, _ = hit_rates(test, v2)
    ship = p_v2['top12_rate'] >= p_v1['top12_rate']
    print(f'\nGATE: v2 test top12 {p_v2["top12_rate"]:.1%} vs v1 {p_v1["top12_rate"]:.1%} '
          f'-> {"SHIP v2" if ship else "KEEP v1"}')
    if ship:
        full_coefs, full_b0 = fit_v2(events)  # refit on full window for deploy
        out = {
            'version': 'v2_2026-07-10', 'features': FEATS,
            'coefs': full_coefs, 'intercept': full_b0,
            'fit_window': [str(WIN_START), str(WIN_END)], 'n_events': n,
            'gate': {'test_top12_v2': p_v2['top12_rate'], 'test_top12_v1': p_v1['top12_rate'],
                     'test_n': p_v1['n']},
            'note': 'pooled logistic; per-team behavior enters via v1_prior feature; '
                    'pre-registered in validation_runs/opp_watch_v2_refit_2026-07-10.md',
        }
        WEIGHTS_OUT.write_text(json.dumps(out, indent=2), encoding='utf-8')
        print(f'Wrote {WEIGHTS_OUT}')
        print('Full-window deploy coefficients:')
        for f in FEATS:
            print(f'  {f:10s} {full_coefs[f]:+.4f}')


if __name__ == '__main__':
    main()

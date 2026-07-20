"""recent_signal_tournament.py — which current-season recent signal best predicts forward FP?

Head-to-head tournament on the 2026 in-season panel: every recent-results
signal family, one harness, ranked by forward predictive power.

Design (same leakage-safe skeleton as process_fp_correlation_lab):
  anchors spaced 21d (non-overlapping fwd windows), target = forward-21d
  FP/g (boxscore), floors on every window, player-clustered bootstrap on
  the incremental column, BH-FDR q=0.10 across the incremental family.

Pre-registered contestants (Rule 3 — ALL reported every run):
  outcome    : fp_g            (boxscore FP/g)         x {L21, season}
  plate      : woba_actual, k_pct, bb_pct              x {L21, season}
  ex-stats   : xwobacon                                x {L21, season}
  power      : hardhit_pct, barrel_pct, ev90           x {L21, season}
  bat-track  : bat_speed, fast_swing_pct               x {L21, season}
  decision   : chase_pct, decision_gap                 x {L21, season}
  contact    : whiff_pct                               x {L21, season}
  model      : rh3 proj (logged snapshot as-of anchor) [anchors >= 2026-06-04]

Columns reported:
  raw_r   — Spearman vs forward FP/g (the leaderboard)
  incr_r  — partial Spearman beyond SEASON FP/g level (the honesty column)
Composite round: leave-one-anchor-out ridge on ranks — does any combo beat
season FP/g alone out-of-sample?

Rule 13: research leaderboard. Nothing here re-ranks anyone; FDR-pass ->
Rule-9 diff vs RH3_FEATS BEFORE proposing (see whiff_pct_trailing21 run).

Usage:
  PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/recent_signal_tournament.py
Output: data/outputs/recent_signal_tournament.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CACHE = 'data/research/xfp_cache'
SNAP = 'data/research/player_projection_history.parquet'
OUT = 'data/outputs/recent_signal_tournament.csv'
FWD_D, TRAIL_D = 21, 21
MIN_FWD_G, MIN_SEASON_G = 10, 20
MIN_W_PITCH, MIN_W_EV = 60, 40
MIN_S_PITCH, MIN_S_EV = 300, 150
N_BOOT, FDR_Q = 500, 0.10
RNG = np.random.default_rng(20260718)

SWING = {'hit_into_play', 'foul', 'swinging_strike', 'swinging_strike_blocked',
         'foul_tip', 'foul_bunt', 'missed_bunt', 'bunt_foul_tip'}
WHIFF = {'swinging_strike', 'swinging_strike_blocked'}
K_EV = {'strikeout', 'strikeout_double_play'}
BB_EV = {'walk'}


def _sig(g: pd.DataFrame, min_pitch: int, min_ev: int) -> dict | None:
    n = len(g)
    ev = g.dropna(subset=['events'])
    if n < min_pitch or len(ev) < min_ev:
        return None
    iz, oz = int(g['inzone'].sum()), int(g['ozone'].sum())
    if iz < 15 or oz < 15:
        return None
    sw = g[g['swing']]
    bs = sw['bat_speed'].dropna()
    bip = g[g['description'] == 'hit_into_play']
    ls = bip['launch_speed'].dropna()
    zsw = g.loc[g['inzone'], 'swing'].mean() * 100
    chase = g.loc[g['ozone'], 'swing'].mean() * 100
    wd = g['woba_denom'].sum()
    return dict(
        woba_actual=(g['woba_value'].sum() / wd) if wd else np.nan,
        k_pct=100 * ev['events'].isin(K_EV).mean(),
        bb_pct=100 * ev['events'].isin(BB_EV).mean(),
        xwobacon=bip['estimated_woba_using_speedangle'].mean(),
        hardhit_pct=(100 * ls.ge(95).mean()) if len(ls) else np.nan,
        barrel_pct=(100 * bip['launch_speed_angle'].eq(6).mean()) if len(bip) else np.nan,
        ev90=ls.quantile(0.9) if len(ls) >= 10 else np.nan,
        bat_speed=bs.mean() if len(bs) else np.nan,
        fast_swing_pct=(100 * bs.ge(75).mean()) if len(bs) else np.nan,
        chase_pct=chase, decision_gap=zsw - chase,
        whiff_pct=(100 * g['whiff'].sum() / len(sw)) if len(sw) else np.nan,
    )


BASE_SIGS = ['woba_actual', 'k_pct', 'bb_pct', 'xwobacon', 'hardhit_pct',
             'barrel_pct', 'ev90', 'bat_speed', 'fast_swing_pct',
             'chase_pct', 'decision_gap', 'whiff_pct']


def build_panel() -> pd.DataFrame:
    sc = pd.read_parquet(f'{CACHE}/statcast_2026.parquet', columns=[
        'batter', 'game_date', 'description', 'zone', 'events',
        'estimated_woba_using_speedangle', 'woba_value', 'woba_denom',
        'launch_speed', 'launch_speed_angle', 'bat_speed'])
    sc['game_date'] = pd.to_datetime(sc['game_date'], errors='coerce')
    sc = sc.dropna(subset=['game_date'])
    sc['swing'] = sc['description'].isin(SWING)
    sc['whiff'] = sc['description'].isin(WHIFF)
    sc['inzone'] = sc['zone'].between(1, 9)
    sc['ozone'] = sc['zone'].between(11, 14)

    bx = pd.read_parquet(f'{CACHE}/boxscore_hitters.parquet')
    bx['game_date'] = pd.to_datetime(bx['game_date'])

    snap = pd.read_parquet(SNAP)
    snap = snap[snap['player_type'] == 'H'].copy()
    snap['snapshot_date'] = pd.to_datetime(snap['snapshot_date'])

    last = min(sc['game_date'].max(), bx['game_date'].max())
    anchors = pd.date_range(bx['game_date'].min() + pd.Timedelta(days=28),
                            last - pd.Timedelta(days=FWD_D), freq=f'{FWD_D}D')
    rows = []
    for t in anchors:
        w = sc[(sc['game_date'] > t - pd.Timedelta(days=TRAIL_D)) & (sc['game_date'] <= t)]
        s = sc[sc['game_date'] <= t]
        fwd = bx[(bx['game_date'] > t) & (bx['game_date'] <= t + pd.Timedelta(days=FWD_D))]
        sea = bx[bx['game_date'] <= t]
        l21 = bx[(bx['game_date'] > t - pd.Timedelta(days=TRAIL_D)) & (bx['game_date'] <= t)]
        fwd_g = fwd.groupby('mlbam_id')['fp_h'].agg(['mean', 'size'])
        sea_g = sea.groupby('mlbam_id')['fp_h'].agg(['mean', 'size'])
        l21_g = l21.groupby('mlbam_id')['fp_h'].agg(['mean', 'size'])
        # nearest logged rh3 snapshot at/before anchor (within 3d)
        sd = snap[snap['snapshot_date'] <= t]
        rh3 = pd.DataFrame()
        if not sd.empty and (t - sd['snapshot_date'].max()).days <= 3:
            rh3 = sd[sd['snapshot_date'] == sd['snapshot_date'].max()].set_index('mlbam_id')
        wm = {b: _sig(g, MIN_W_PITCH, MIN_W_EV) for b, g in w.groupby('batter')}
        sm = {b: _sig(g, MIN_S_PITCH, MIN_S_EV) for b, g in s.groupby('batter')}
        for b in fwd_g.index.intersection(sea_g.index):
            if fwd_g.loc[b, 'size'] < MIN_FWD_G or sea_g.loc[b, 'size'] < MIN_SEASON_G:
                continue
            wsig, ssig = wm.get(b), sm.get(b)
            if wsig is None or ssig is None:
                continue
            row = dict(anchor=t, batter=b,
                       fwd_fp=fwd_g.loc[b, 'mean'],
                       fp_g_season=sea_g.loc[b, 'mean'],
                       fp_g_l21=l21_g.loc[b, 'mean'] if (b in l21_g.index and l21_g.loc[b, 'size'] >= 5) else np.nan)
            for k in BASE_SIGS:
                row[f'{k}_l21'] = wsig[k]
                row[f'{k}_season'] = ssig[k]
            if len(rh3) and b in rh3.index:
                r = rh3.loc[b]
                r = r.iloc[0] if isinstance(r, pd.DataFrame) else r
                pv = r.get('proj_volume')
                row['rh3_proj'] = (r['proj_per'] * pv) if pd.notna(pv) else r['proj_per']
            rows.append(row)
    return pd.DataFrame(rows)


def _partial(x, y, controls):
    xr = pd.Series(x).rank().to_numpy(); yr = pd.Series(y).rank().to_numpy()
    Z = np.column_stack([np.ones(len(xr))] + [pd.Series(c).rank().to_numpy() for c in controls])
    rx = xr - Z @ np.linalg.lstsq(Z, xr, rcond=None)[0]
    ry = yr - Z @ np.linalg.lstsq(Z, yr, rcond=None)[0]
    if rx.std() == 0 or ry.std() == 0:
        return np.nan
    return float(np.corrcoef(rx, ry)[0, 1])


def _spear(x, y):
    return _partial(x, y, [])


def _boot_incr(df, col):
    players = df['batter'].unique()
    groups = {p: g for p, g in df.groupby('batter')}
    vals = []
    for _ in range(N_BOOT):
        pick = RNG.choice(players, size=len(players), replace=True)
        b = pd.concat([groups[p] for p in pick], ignore_index=True)
        vals.append(_partial(b[col], b['fwd_fp'], [b['fp_g_season']]))
    vals = np.array([v for v in vals if not np.isnan(v)])
    if len(vals) < 100:
        return np.nan, np.nan, np.nan
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return lo, hi, max(2 * min((vals <= 0).mean(), (vals >= 0).mean()), 1 / len(vals))


def main() -> int:
    panel = build_panel()
    print(f"panel: {len(panel)} obs | {panel['batter'].nunique()} players | "
          f"{panel['anchor'].nunique()} anchors | rh3 rows: {panel['rh3_proj'].notna().sum() if 'rh3_proj' in panel else 0}")

    contestants = (['fp_g_season', 'fp_g_l21'] +
                   [f'{k}_{w}' for k in BASE_SIGS for w in ('l21', 'season')] +
                   (['rh3_proj'] if 'rh3_proj' in panel.columns else []))
    res = []
    for c in contestants:
        sub = panel.dropna(subset=[c, 'fwd_fp', 'fp_g_season'])
        if len(sub) < 100:
            continue
        raw = _spear(sub[c], sub['fwd_fp'])
        incr = np.nan if c == 'fp_g_season' else _partial(sub[c], sub['fwd_fp'], [sub['fp_g_season']])
        lo = hi = p = np.nan
        if c != 'fp_g_season':
            lo, hi, p = _boot_incr(sub, c)
        res.append(dict(signal=c, n=len(sub), raw_r=raw, incr_r=incr,
                        ci_lo=lo, ci_hi=hi, p=p))
    res = pd.DataFrame(res)
    ranked = res.reindex(res['raw_r'].abs().sort_values(ascending=False).index)
    with_p = res.dropna(subset=['p']).sort_values('p').reset_index(drop=True)
    m = len(with_p)
    bh = {r['signal']: (i + 1) / m * FDR_Q for i, r in with_p.iterrows()}
    still, passes = True, {}
    for _, r in with_p.iterrows():
        still = still and (r['p'] <= bh[r['signal']])
        passes[r['signal']] = still
    ranked['fdr_pass'] = ranked['signal'].map(passes).fillna(False)

    print(f"\n{'signal':<22}{'n':>6}{'raw_r':>8}{'incr_r':>8}{'95% CI':>19}{'p':>8}  FDR")
    for _, r in ranked.iterrows():
        ci = f"[{r['ci_lo']:+.3f},{r['ci_hi']:+.3f}]" if pd.notna(r['ci_lo']) else ''
        pp = f"{r['p']:.3f}" if pd.notna(r['p']) else '—'
        flag = '*** PASS' if r['fdr_pass'] else ''
        ir = f"{r['incr_r']:+.3f}" if pd.notna(r['incr_r']) else '  ctrl'
        print(f"{r['signal']:<22}{r['n']:>6}{r['raw_r']:>+8.3f}{ir:>8}{ci:>19}{pp:>8}  {flag}")

    # composite round — leave-one-anchor-out, ridge on ranks
    from sklearn.linear_model import Ridge
    top_incr = [r['signal'] for _, r in ranked.iterrows() if r['fdr_pass']][:3]
    sets = {'season_fp alone': ['fp_g_season'],
            'season_fp + top-3 FDR': ['fp_g_season'] + top_incr,
            'kitchen sink (all)': [c for c in contestants if c != 'rh3_proj']}
    print(f"\n=== COMPOSITE (leave-one-anchor-out CV) ===  top-3 FDR: {top_incr}")
    comp_rows = []
    for name, feats in sets.items():
        sub = panel.dropna(subset=feats + ['fwd_fp']).copy()
        preds, acts = [], []
        for hold in sub['anchor'].unique():
            tr, te = sub[sub['anchor'] != hold], sub[sub['anchor'] == hold]
            if len(tr) < 100 or len(te) < 30:
                continue
            Xtr = tr[feats].rank(pct=True).to_numpy(); Xte = te[feats].rank(pct=True).to_numpy()
            mdl = Ridge(alpha=1.0).fit(Xtr, tr['fwd_fp'].rank(pct=True).to_numpy())
            preds += list(mdl.predict(Xte)); acts += list(te['fwd_fp'])
        r = _spear(np.array(preds), np.array(acts))
        comp_rows.append(dict(signal=f'COMPOSITE::{name}', n=len(preds), raw_r=r))
        print(f"  {name:<26} n={len(preds):>5}  OOS Spearman = {r:+.3f}")

    out = pd.concat([ranked, pd.DataFrame(comp_rows)], ignore_index=True)
    out.insert(0, 'run_date', pd.Timestamp.today().date().isoformat())
    out.to_csv(OUT, index=False)
    print(f"\nledger -> {OUT}")
    print("Rule 13: research leaderboard; FDR-pass -> Rule-9 diff vs RH3_FEATS before proposing.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

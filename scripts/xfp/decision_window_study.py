"""decision_window_study.py — how recent a hitter DECISION trend is signal.

Question: for plate-discipline / swing-decision metrics, what trailing window
length carries real information — and about what?

Two pre-registered tests per (metric, window) cell:
  T1 PERSISTENCE (2024+2025+2026 statcast): partial Spearman of
     metric-in-window-W (ending at anchor t) vs metric-in-next-21d,
     controlling for the hitter's PRE-window season baseline. >0 with CI
     excluding 0 = a recent change is (partly) real, not noise. The
     stabilization curve across W answers "how recent is predictive."
  T2 FP RELEVANCE (2026 only, boxscore FP): partial Spearman of
     delta_W (window minus pre-window baseline) vs forward-21d FP/g,
     controlling for season-to-date FP/g level. Tests whether a recent
     decision SHIFT predicts scoring beyond the level. Rule-13 prior: ~0.

Pre-registered family (Rule 3 sweep context — FDR within each test family):
  metrics : chase_pct, z_swing_pct, decision_gap, swing_pct   (4)
  windows : 7, 14, 21, 30, 45 days                            (5)
  cells   : 20 per test. BH-FDR q=0.10 per family.
Whiff/contact excluded — contact-skill axis, closed REJECTED 2026-07-17
(already in rh3). This study targets the TRACKER window choice (display /
Rule 13 context lens), NOT an rh3 candidate.

Anchors spaced 21d (non-overlapping forward windows), player-clustered
bootstrap CIs. Output: data/outputs/decision_window_study.csv.

Usage:
  PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/decision_window_study.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CACHE = 'data/research/xfp_cache'
OUT = 'data/outputs/decision_window_study.csv'
YEARS_T1 = [2024, 2025, 2026]
WINDOWS = [7, 14, 21, 30, 45]
METRICS = ['chase_pct', 'z_swing_pct', 'decision_gap', 'swing_pct']
FWD_D = 21
ANCHOR_SPACING = 21
MIN_FWD_PITCH = 150
MIN_BASE_PITCH = 300
MIN_FWD_G = 10
MIN_SEASON_G = 20
N_BOOT = 600
FDR_Q = 0.10
RNG = np.random.default_rng(20260718)

SWING = {'hit_into_play', 'foul', 'swinging_strike', 'swinging_strike_blocked',
         'foul_tip', 'foul_bunt', 'missed_bunt', 'bunt_foul_tip'}


def _min_pitch(w: int) -> int:
    return max(40, 3 * w)


def _load_year(year: int) -> pd.DataFrame:
    df = pd.read_parquet(f'{CACHE}/statcast_{year}.parquet',
                         columns=['batter', 'game_date', 'description', 'zone'])
    df['game_date'] = pd.to_datetime(df['game_date'], errors='coerce')
    df = df.dropna(subset=['game_date'])
    df['swing'] = df['description'].isin(SWING)
    df['inzone'] = df['zone'].between(1, 9)
    df['ozone'] = df['zone'].between(11, 14)
    return df


def _metrics(g: pd.DataFrame) -> dict | None:
    n = len(g)
    iz, oz = int(g['inzone'].sum()), int(g['ozone'].sum())
    if iz < 15 or oz < 15:
        return None
    zsw = g.loc[g['inzone'], 'swing'].mean() * 100
    chase = g.loc[g['ozone'], 'swing'].mean() * 100
    return dict(n_pitch=n, chase_pct=chase, z_swing_pct=zsw,
                decision_gap=zsw - chase, swing_pct=g['swing'].mean() * 100)


def _anchors(df: pd.DataFrame) -> pd.DatetimeIndex:
    lo = df['game_date'].min() + pd.Timedelta(days=45)   # room for W=45 + baseline
    hi = df['game_date'].max() - pd.Timedelta(days=FWD_D)
    return pd.date_range(lo, hi, freq=f'{ANCHOR_SPACING}D')


def build_t1_panel() -> pd.DataFrame:
    rows = []
    for year in YEARS_T1:
        sc = _load_year(year)
        for t in _anchors(sc):
            fwd = sc[(sc['game_date'] > t) & (sc['game_date'] <= t + pd.Timedelta(days=FWD_D))]
            fwd_m = {b: _metrics(g) for b, g in fwd.groupby('batter') if len(g) >= MIN_FWD_PITCH}
            for w in WINDOWS:
                win = sc[(sc['game_date'] > t - pd.Timedelta(days=w)) & (sc['game_date'] <= t)]
                base = sc[sc['game_date'] <= t - pd.Timedelta(days=w)]
                base_m = {b: _metrics(g) for b, g in base.groupby('batter') if len(g) >= MIN_BASE_PITCH}
                for b, g in win.groupby('batter'):
                    if len(g) < _min_pitch(w):
                        continue
                    wm = _metrics(g)
                    fm = fwd_m.get(b)
                    bm = base_m.get(b)
                    if wm is None or fm is None or bm is None:
                        continue
                    row = dict(year=year, anchor=t, batter=b, window=w)
                    for m in METRICS:
                        row[f'{m}_w'] = wm[m]
                        row[f'{m}_base'] = bm[m]
                        row[f'{m}_fwd'] = fm[m]
                    rows.append(row)
    return pd.DataFrame(rows)


def build_t2_panel(t1: pd.DataFrame) -> pd.DataFrame:
    bx = pd.read_parquet(f'{CACHE}/boxscore_hitters.parquet')
    bx['game_date'] = pd.to_datetime(bx['game_date'])
    sub = t1[t1['year'] == 2026].copy()
    out = []
    for t, g in sub.groupby('anchor'):
        fwd = bx[(bx['game_date'] > t) & (bx['game_date'] <= t + pd.Timedelta(days=FWD_D))]
        sea = bx[bx['game_date'] <= t]
        fwd_g = fwd.groupby('mlbam_id')['fp_h'].agg(['mean', 'size'])
        sea_g = sea.groupby('mlbam_id')['fp_h'].agg(['mean', 'size'])
        for _, r in g.iterrows():
            b = r['batter']
            if b not in fwd_g.index or b not in sea_g.index:
                continue
            if fwd_g.loc[b, 'size'] < MIN_FWD_G or sea_g.loc[b, 'size'] < MIN_SEASON_G:
                continue
            d = r.to_dict()
            d['fwd_fp'] = fwd_g.loc[b, 'mean']
            d['season_fp'] = sea_g.loc[b, 'mean']
            out.append(d)
    return pd.DataFrame(out)


def _partial(x, y, controls) -> float:
    xr = pd.Series(x).rank().to_numpy()
    yr = pd.Series(y).rank().to_numpy()
    Z = np.column_stack([np.ones(len(xr))] +
                        [pd.Series(c).rank().to_numpy() for c in controls])
    rx = xr - Z @ np.linalg.lstsq(Z, xr, rcond=None)[0]
    ry = yr - Z @ np.linalg.lstsq(Z, yr, rcond=None)[0]
    if rx.std() == 0 or ry.std() == 0:
        return np.nan
    return float(np.corrcoef(rx, ry)[0, 1])


def _boot(df: pd.DataFrame, fn) -> tuple:
    players = df['batter'].unique()
    groups = {p: g for p, g in df.groupby('batter')}
    vals = []
    for _ in range(N_BOOT):
        pick = RNG.choice(players, size=len(players), replace=True)
        vals.append(fn(pd.concat([groups[p] for p in pick], ignore_index=True)))
    vals = np.array([v for v in vals if not np.isnan(v)])
    if len(vals) < 100:
        return np.nan, np.nan, np.nan
    lo, hi = np.percentile(vals, [2.5, 97.5])
    p = 2 * min((vals <= 0).mean(), (vals >= 0).mean())
    return lo, hi, max(p, 1 / len(vals))


def _fdr(res: pd.DataFrame) -> pd.DataFrame:
    res = res.sort_values('p').reset_index(drop=True)
    m = len(res)
    res['bh'] = [(i + 1) / m * FDR_Q for i in range(m)]
    ok, still = [], True
    for _, r in res.iterrows():
        still = still and (r['p'] <= r['bh'])
        ok.append(still)
    res['fdr_pass'] = ok
    return res


def main() -> int:
    t1 = build_t1_panel()
    print(f"T1 panel: {len(t1)} obs | {t1['batter'].nunique()} players | "
          f"{t1.groupby(['year'])['anchor'].nunique().to_dict()} anchors/yr")

    r1 = []
    for m in METRICS:
        for w in WINDOWS:
            sub = t1[(t1['window'] == w)].dropna(subset=[f'{m}_w', f'{m}_fwd', f'{m}_base'])
            if len(sub) < 100:
                continue
            fn = lambda b, _m=m: _partial(b[f'{_m}_w'], b[f'{_m}_fwd'], [b[f'{_m}_base']])
            r = fn(sub)
            lo, hi, p = _boot(sub, fn)
            r1.append(dict(test='T1_persistence', metric=m, window=w, n=len(sub),
                           partial_r=r, ci_lo=lo, ci_hi=hi, p=p))
    r1 = _fdr(pd.DataFrame(r1))

    t2 = build_t2_panel(t1)
    print(f"T2 panel (2026): {len(t2)} obs | {t2['batter'].nunique()} players")
    r2 = []
    for m in METRICS:
        for w in WINDOWS:
            sub = t2[(t2['window'] == w)].dropna(
                subset=[f'{m}_w', f'{m}_base', 'fwd_fp', 'season_fp'])
            if len(sub) < 100:
                continue
            sub = sub.assign(delta=sub[f'{m}_w'] - sub[f'{m}_base'])
            fn = lambda b: _partial(b['delta'], b['fwd_fp'], [b['season_fp']])
            r = fn(sub)
            lo, hi, p = _boot(sub, fn)
            r2.append(dict(test='T2_fp_relevance', metric=m, window=w, n=len(sub),
                           partial_r=r, ci_lo=lo, ci_hi=hi, p=p))
    r2 = _fdr(pd.DataFrame(r2))

    res = pd.concat([r1, r2], ignore_index=True)
    res.insert(0, 'run_date', pd.Timestamp.today().date().isoformat())
    res.to_csv(OUT, index=False)

    for name, rr in [('T1 PERSISTENCE (does a recent decision change stick?)', r1),
                     ('T2 FP RELEVANCE (does a recent shift predict scoring?)', r2)]:
        print(f"\n=== {name} ===")
        print(f"{'metric':<14}{'W':>4}{'n':>7}{'r':>8}{'95% CI':>19}{'p':>8}  FDR")
        for _, r in rr.sort_values(['metric', 'window']).iterrows():
            flag = '*** PASS' if r['fdr_pass'] else ''
            print(f"{r['metric']:<14}{r['window']:>4}{r['n']:>7}{r['partial_r']:>8.3f}"
                  f"   [{r['ci_lo']:>+.3f},{r['ci_hi']:>+.3f}]{r['p']:>8.3f}  {flag}")
    print(f"\nledger -> {OUT}")
    print("Rule 13: tracker-window evidence, display/context only — not an rh3 candidate.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

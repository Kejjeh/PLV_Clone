"""PART 2 — in-season BAT-SPEED DELTA vs rh3 (the delta-family re-open test).

Pre-registered: data/research/validation_runs/bat_speed_stabilization_and_delta_2026-07-29.md

The 60-cell in-season-delta family was CLOSED 2026-07-29 with 0 finalists, and
in-season bat-speed deltas were named its SOLE re-open condition (no
window-capable bat-speed store existed then). `bat_speed_daily.parquet` now
exists, so this is that test.

Construction (leakage-safe by design — both windows end at or before the
snapshot cutoff):
    RECENT  = swings in (C - L, C]
    EARLIER = swings in (C - 2L, C - L]
    d = mean(RECENT) - mean(EARLIER)
Every snapshot therefore consumes a 2L-day swing span, so NON-OVERLAPPING
snapshots within a batter-year are spaced >= 2L days (stricter than the
delta-grid's >= L, which was correct there because EARLIER was cumulative).

Funnel: BH-FDR(q=.05) + |r|>=.05 floor on the 2024-2025 screen -> 2026 holdout
gate -> Rule 9 integration vs ALL 22 RH3_FEATS (bar +0.005).

RULE-5 CONSTRAINT, declared before the run: bat tracking starts in 2024, so
only 3 season cohorts exist (2024, 2025, 2026 — the last partial). The
>=5-cohort year-consistency gate is UNREACHABLE; any PASS here is EXPLORATORY
and may NOT move RH3_FEATS.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

warnings.filterwarnings('ignore')
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from sklearn.linear_model import LinearRegression, RidgeCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from plv_clone.models.xfp.rh3 import (
    RH3_FEATS, TARGET, EVAL_PA_MIN, ROS_PA_MIN, ROLLING_CSV, MULTIYR_CSV,
)
from validate_inseason_discipline import attach_production_features

STORE = ROOT / 'data' / 'research' / 'bat_speed_daily.parquet'

BAT_YEARS = [2024, 2025, 2026]      # every season with bat tracking
SCREEN = [2024, 2025]
HOLDOUT = [2026]

# Declared cells: 2 metrics x 3 lags. Snapshots spaced >= 2L, first at >= 2L.
LAGS = [21, 42, 63]
NONOVERLAP = {21: [44, 86, 128, 170], 42: [86, 170], 63: [128]}
# metric -> (daily value col, expected sign)
CANDS = {'bat_speed': ('mean_bat_speed', +1),
         'fast_swing': ('fast_swing_rate', +1)}

# Part-1 empirical minimum, applied to BOTH windows. The declared rule is
# "r>=0.50 crossing, ceil to nearest 25 swings"; Part 1's crossing sits at or
# below its smallest resolvable bucket (mid 27 swings, forward r +0.736), which
# the ceil rule turns into 50. Conservative and mechanically faithful.
MIN_SWINGS = 50
MIN_ROWS_CELL = 300        # below this -> UNDERPOWERED (Rule 5), not failed
MIN_ROWS_HOLDOUT = 150


def load_daily() -> pd.DataFrame:
    d = pd.read_parquet(STORE)
    d['game_date'] = pd.to_datetime(d['game_date'])
    d['n_swings'] = pd.to_numeric(d['n_swings'], errors='coerce')
    for c in ('mean_bat_speed', 'fast_swing_rate'):
        d[c] = pd.to_numeric(d[c], errors='coerce')
        d['_w_' + c] = d[c] * d['n_swings']
    return d[d['n_swings'].notna() & (d['n_swings'] > 0)]


def _wmean(daily: pd.DataFrame, lo, hi, cols) -> pd.DataFrame:
    """Swing-weighted per-batter means over game_date in (lo, hi]."""
    s = daily[(daily['game_date'] > lo) & (daily['game_date'] <= hi)]
    g = s.groupby('batter').agg(
        sw=('n_swings', 'sum'),
        **{'w_' + c: ('_w_' + c, 'sum') for c in cols})
    for c in cols:
        g[c] = g['w_' + c] / g['sw']
    return g[['sw'] + list(cols)]


def build_frame(rolling: pd.DataFrame, daily: pd.DataFrame, L: int) -> pd.DataFrame:
    """One non-overlapping delta frame for lag L."""
    cols = [v for v, _ in CANDS.values()]
    parts = []
    for (yr, sd), grp in rolling.groupby(['year', 'split_day']):
        if sd not in NONOVERLAP[L]:
            continue
        cds = pd.to_datetime(grp['cutoff_date']).unique()
        assert len(cds) == 1, f'cutoff_date not unique for {yr}/{sd}: {cds}'
        C = pd.Timestamp(cds[0])
        dy = daily[daily['game_date'].dt.year == yr]
        rec = _wmean(dy, C - pd.Timedelta(days=L), C, cols)
        ear = _wmean(dy, C - pd.Timedelta(days=2 * L), C - pd.Timedelta(days=L), cols)
        lvl = _wmean(dy, pd.Timestamp(f'{yr}-01-01'), C, cols)   # season-to-date level
        j = grp.set_index('batter')
        for c in cols:
            j['rec_' + c] = rec[c]
            j['ear_' + c] = ear[c]
            j['lvl_' + c] = lvl[c]
        j['sw_rec'], j['sw_ear'], j['sw_lvl'] = rec['sw'], ear['sw'], lvl['sw']
        parts.append(j.reset_index())
    if not parts:
        return pd.DataFrame()
    df = pd.concat(parts, ignore_index=True)
    gate = (df['sw_rec'] >= MIN_SWINGS) & (df['sw_ear'] >= MIN_SWINGS)
    for name, (col, sign) in CANDS.items():
        d = (df['rec_' + col] - df['ear_' + col]).where(gate)
        df['d_' + name] = d
        g = d.groupby([df['year'], df['split_day']])
        df['dz_' + name] = sign * (d - g.transform('mean')) / g.transform('std')
    return df


def partial_r(df, cand, ctrl, y=TARGET):
    X = df[ctrl].values
    r1 = df[cand].values - LinearRegression().fit(X, df[cand].values).predict(X)
    r2 = df[y].values - LinearRegression().fit(X, df[y].values).predict(X)
    if r1.std() < 1e-12 or r2.std() < 1e-12:
        return np.nan, np.nan, len(df)
    r = float(np.corrcoef(r1, r2)[0, 1])
    dfree = len(df) - len(ctrl) - 2
    t = r * np.sqrt(dfree / max(1e-12, 1 - r * r))
    return r, 2 * sps.t.sf(abs(t), dfree), len(df)


def make_pipe():
    return Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])


def cross_year_r(df, feats):
    """Leave-one-cohort-out mean r. Only 3 cohorts exist — weakly powered."""
    rs = {}
    for held in sorted(df['year'].unique()):
        tr, te = df[df['year'] != held], df[df['year'] == held]
        if len(tr) < 200 or len(te) < 30:
            continue
        pipe = make_pipe()
        pipe.fit(tr[feats].values, tr[TARGET].values)
        rs[int(held)] = float(np.corrcoef(pipe.predict(te[feats].values),
                                         te[TARGET].values)[0, 1])
    return (float(np.mean(list(rs.values()))) if rs else np.nan), rs


def main() -> int:
    rolling = attach_production_features(pd.read_csv(ROLLING_CSV),
                                         pd.read_csv(MULTIYR_CSV))
    rolling = rolling.dropna(subset=RH3_FEATS + [TARGET])
    rolling = rolling[(rolling['pa_to'] >= EVAL_PA_MIN)
                      & (rolling['ros_pa'] >= ROS_PA_MIN)
                      & (rolling['year'].isin(BAT_YEARS))]
    print(f'production frame, bat-tracking years: {len(rolling)} rows '
          f'{dict(rolling.groupby("year").size())}')
    print(f'RULE 5: only {rolling["year"].nunique()} cohorts exist '
          f'(bat tracking starts 2024) -> year-consistency gate UNREACHABLE; '
          f'any PASS is EXPLORATORY.\n')

    daily = load_daily()
    frames = {L: build_frame(rolling, daily, L) for L in LAGS}
    for L in LAGS:
        f = frames[L]
        n = {k: int(v) for k, v in f.groupby('year').size().items()} if len(f) else {}
        print(f'lag {L:>3}d frame: {len(f):>5} rows (splits {NONOVERLAP[L]}) {n}')

    # ---- STAGE 1: screen on 2024-2025, BH-FDR across all 6 declared cells ----
    cells = []
    for L in LAGS:
        f = frames[L]
        for name, (col, _) in CANDS.items():
            cand, ctrl = 'dz_' + name, ['lvl_' + col, 'prior_fp_per_pa', 'pa_to']
            sub = (f[f['year'].isin(SCREEN)].dropna(subset=[cand] + ctrl)
                   if len(f) else pd.DataFrame())
            if len(sub) < MIN_ROWS_CELL:
                cells.append(dict(metric=name, lag=L, r=np.nan, p=np.nan,
                                  n=len(sub), status='UNDERPOWERED'))
                continue
            r, p, n = partial_r(sub, cand, ctrl)
            cells.append(dict(metric=name, lag=L, r=r, p=p, n=n, status=''))
    C = pd.DataFrame(cells)

    tested = C[C['p'].notna()].sort_values('p').reset_index(drop=True)
    m = len(tested)
    if m:
        tested['bh_crit'] = 0.05 * (tested.index + 1) / m
        k = tested['p'] <= tested['bh_crit']
        cut = tested.index[k].max() if k.any() else -1
        tested['fdr_pass'] = tested.index <= cut
        tested['screen_pass'] = (tested['fdr_pass'] & (tested['r'] >= 0.05))
        C = C.merge(tested[['metric', 'lag', 'fdr_pass', 'screen_pass']],
                    on=['metric', 'lag'], how='left')
    else:
        C['fdr_pass'] = C['screen_pass'] = False

    print(f'\n[stage 1] screen years {SCREEN}; {m}/6 cells testable '
          f'({6 - m} UNDERPOWERED at <{MIN_ROWS_CELL} rows). '
          f'BH-FDR q=.05 pass: {int(C["fdr_pass"].fillna(False).sum())}; '
          f'+ |r|>=.05 & correct sign: {int(C["screen_pass"].fillna(False).sum())}')
    print(f'\n{"cell":<22} {"n":>6} {"partial r":>10} {"p":>9}  flags')
    for _, c in C.iterrows():
        if c['status'] == 'UNDERPOWERED':
            print(f'   {c["metric"] + " lag" + str(c["lag"]):<19} {c["n"]:>6} '
                  f'{"n/a":>10} {"n/a":>9}  UNDERPOWERED')
            continue
        fl = ('** screen pass' if c['screen_pass'] else
              ('*  FDR only' if c['fdr_pass'] else ''))
        print(f'   {c["metric"] + " lag" + str(c["lag"]):<19} {c["n"]:>6} '
              f'{c["r"]:>+10.4f} {c["p"]:>9.4g}  {fl}')

    # ---- STAGE 2: 2026 holdout gate ----
    surv = C[C['screen_pass'] == True]  # noqa: E712
    print(f'\n[stage 2] holdout {HOLDOUT} gate on {len(surv)} screen survivor(s):')
    finalists = []
    for _, c in surv.iterrows():
        f = frames[c['lag']]
        name = c['metric']
        cand = 'dz_' + name
        ctrl = ['lvl_' + CANDS[name][0], 'prior_fp_per_pa', 'pa_to']
        sub = f[f['year'].isin(HOLDOUT)].dropna(subset=[cand] + ctrl)
        r, p, n = partial_r(sub, cand, ctrl)
        if n < MIN_ROWS_HOLDOUT:
            print(f'   {name:<12} lag{c["lag"]:>3}  train {c["r"]:+.4f}  '
                  f'holdout n={n} < {MIN_ROWS_HOLDOUT} -> UNDERPOWERED '
                  f'(cannot advance)')
            continue
        ok = (not pd.isna(r)) and r >= 0.05
        print(f'   {name:<12} lag{c["lag"]:>3}  train {c["r"]:+.4f}  '
              f'holdout {r:+.4f} (n={n})  -> {"ADVANCE" if ok else "DIES"}')
        if ok:
            finalists.append((name, int(c['lag'])))
    if not len(surv):
        print('   none — nothing survived stage 1.')

    # ---- STAGE 3: Rule 9 integration vs ALL 22 RH3_FEATS ----
    print(f'\n[stage 3] Rule 9 integration ({len(finalists)} finalist(s)), '
          f'baseline = ALL {len(RH3_FEATS)} RH3_FEATS:')
    for name, L in finalists:
        df = frames[L].dropna(subset=RH3_FEATS + [TARGET, 'dz_' + name])
        base, pyb = cross_year_r(df, RH3_FEATS)
        plus, pyf = cross_year_r(df, RH3_FEATS + ['dz_' + name])
        d = plus - base
        print(f'   {name:<12} lag{L:>3}  base {base:+.4f} -> +cand {plus:+.4f}  '
              f'delta {d:+.4f}  {"PASS" if d >= 0.005 else "FAIL (<+0.005)"}  '
              f'(n={len(df)})')
        print(f'      per-cohort base {pyb}')
        print(f'      per-cohort +cand {pyf}')
    if not finalists:
        print('   none — family stays closed.')

    # ---- STAGE 3b: DIAGNOSTIC ONLY — Rule 9 for every testable cell ----
    # NOT a promotion path. Reported so the memo can state what the integration
    # test would have said instead of leaving a gap, and so a near-miss screen
    # cell cannot later be re-litigated as "never actually integration-tested".
    print('\n[stage 3b] DIAGNOSTIC (post-hoc, cannot promote — these cells did '
          'not clear stage 1/2):')
    for _, c in C[C['p'].notna()].iterrows():
        name, L = c['metric'], int(c['lag'])
        if (name, L) in finalists:
            continue
        df = frames[L].dropna(subset=RH3_FEATS + [TARGET, 'dz_' + name])
        if len(df) < 300:
            print(f'   {name:<12} lag{L:>3}  n={len(df)} too small')
            continue
        base, pyb = cross_year_r(df, RH3_FEATS)
        plus, pyf = cross_year_r(df, RH3_FEATS + ['dz_' + name])
        print(f'   {name:<12} lag{L:>3}  base {base:+.4f} -> +cand {plus:+.4f}  '
              f'delta {plus - base:+.4f}   (n={len(df)}, cohorts '
              f'{sorted(pyf)})')

    # ---- Descriptive: raw distribution of the deltas (for the memo) ----
    print('\n[descriptive] delta distributions (gated rows only):')
    for L in LAGS:
        f = frames[L]
        for name in CANDS:
            s = f['d_' + name].dropna() if len(f) else pd.Series(dtype=float)
            if not len(s):
                continue
            print(f'   d_{name:<11} lag{L:>3}  n={len(s):>5}  '
                  f'mean {s.mean():+.3f}  sd {s.std():.3f}  '
                  f'p10 {s.quantile(.10):+.3f}  p90 {s.quantile(.90):+.3f}')
    print('\ndone.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

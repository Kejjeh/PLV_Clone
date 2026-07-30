"""diagnose_pwin_mean_bias.py — is the P(win) layer's MEAN actually biased?

Track I5, 2026-07-30. Companion memo:
``data/research/validation_runs/pwin_mean_bias_2026-07-30.md``.

Yesterday's F1 track fixed the VARIANCE of the win-probability model (hitter
per-game sigma was understated ~9.7x).  The review that followed reported a
remaining ~7pp OPTIMISTIC bias in the MEAN::

    all_live: mean predicted 0.499 vs actual win rate 0.429
    MA_v1   : mean predicted 0.475 vs actual 0.400

This script asks whether that bias is real.  It does four things the previous
harness did not:

1. **Partitions ``predictions_history.csv`` loudly.**  The file mixes three
   populations: 141 synthetic ``backfill_2024_*`` / ``backfill_2025_*`` rows
   (implied spread sigma 100-400 FP), 25 pre-shadow-logging rows with a NULL
   ``model_version``, and the live ``baseline`` / ``MA_v1`` rows (29-56 FP).
   The old harness ``fillna('baseline')``'d the NULL rows, silently pooling a
   third model version into ``baseline``.  Every exclusion is printed.

2. **Re-derives the ACTUALS from ESPN.**  ``fetch_closed_matchup_actuals.py``
   wrote *in-progress single-day* scores into five of eleven live periods as
   if they were finals (period 13 was stored 25.7-64.5; the true final is
   322.1-331.3).  Grading calibration against those labels is meaningless.

3. **Drops out-of-window snapshots.**  Two periods carry snapshots logged
   AFTER the period had already closed (period 11's only two rows are dated
   2026-06-15, one day after the period ended; period 15 has a 2026-07-20 row).
   Those rows project a full remaining week onto a finished matchup.

4. **Tests the bias with the right null.**  Win/loss outcomes are Bernoulli
   with heterogeneous p, so the reference distribution for "sum of wins" is
   Poisson-binomial, and the continuous margin residual gets a
   period-clustered bootstrap.  n is 10 completed periods; the whole point is
   to say whether 7pp is separable from that.

Usage::

    python scripts/xfp/diagnose_pwin_mean_bias.py                 # cached ESPN
    python scripts/xfp/diagnose_pwin_mean_bias.py --refresh-espn  # re-pull
    python scripts/xfp/diagnose_pwin_mean_bias.py --json out.json

Read-only with respect to ``predictions_history.csv`` — the corrections are
applied IN MEMORY.  To rewrite the store, run
``python scripts/xfp/fetch_closed_matchup_actuals.py --repair``.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

HISTORY = ROOT / 'data' / 'outputs' / 'predictions_history.csv'
ESPN_CACHE = ROOT / 'data' / 'research' / 'espn_matchup_finals_2026.json'

LIVE_VERSIONS = ('baseline', 'MA_v1')
LEGACY_NULL = '__null_model_version__'
SYNTHETIC_PREFIX = 'backfill_'

REQUIRED_COLS = ('period', 'date', 'my_wtd', 'my_projected_total', 'opp_wtd',
                 'opp_projected_total', 'win_probability', 'actual_my_final',
                 'actual_opp_final', 'model_version')


# --------------------------------------------------------------------------
# pure helpers (unit-tested in tests/test_pwin_mean_bias.py)
# --------------------------------------------------------------------------
def partition_history(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Split predictions_history into live vs excluded, loudly.

    Returns (live_df with an ``mv`` column, report dict).  Raises on a missing
    required column rather than defaulting it — a silent default here is what
    let the synthetic rows invert the dispersion statistic in the first place.
    """
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise KeyError(f'predictions_history.csv missing required columns: {missing}')
    df = df.copy()
    df['mv'] = df['model_version'].fillna(LEGACY_NULL)
    is_syn = df['mv'].str.startswith(SYNTHETIC_PREFIX)
    is_legacy = df['mv'] == LEGACY_NULL
    is_live = df['mv'].isin(LIVE_VERSIONS)
    unknown = ~(is_syn | is_legacy | is_live)
    if unknown.any():
        raise ValueError(
            f'unrecognised model_version values: {sorted(df.loc[unknown, "mv"].unique())}')
    report = {
        'n_total': int(len(df)),
        'n_synthetic_excluded': int(is_syn.sum()),
        'n_legacy_null_mv_excluded': int(is_legacy.sum()),
        'n_live': int(is_live.sum()),
        'synthetic_versions': sorted(df.loc[is_syn, 'mv'].unique()),
        'legacy_null_periods': sorted(int(p) for p in df.loc[is_legacy, 'period'].unique()),
    }
    return df[is_live].copy(), report


def poisson_binomial(p: np.ndarray, outcome: np.ndarray) -> dict:
    """Exact-moment test of 'were there fewer wins than predicted?'.

    Wins are independent Bernoulli with heterogeneous p, so
    E[wins] = sum(p), Var[wins] = sum(p(1-p)).  Returns the z of the observed
    win count and a two-sided normal p-value.  With ~10 matchups the normal
    approximation to the Poisson-binomial is adequate for a "is this even
    close to significant?" question, which is all it is used for.
    """
    p = np.asarray(p, dtype=float)
    outcome = np.asarray(outcome, dtype=float)
    if p.shape != outcome.shape:
        raise ValueError('p and outcome must be the same shape')
    if len(p) == 0:
        raise ValueError('poisson_binomial called on an empty sample')
    exp = float(p.sum())
    var = float((p * (1.0 - p)).sum())
    obs = float(outcome.sum())
    if var <= 0:
        raise ValueError('degenerate Poisson-binomial: all probabilities are 0 or 1')
    sd = math.sqrt(var)
    z = (obs - exp) / sd
    pval = math.erfc(abs(z) / math.sqrt(2.0))
    return {'expected_wins': exp, 'observed_wins': obs, 'sd_wins': sd,
            'z': z, 'p_two_sided': pval, 'n': int(len(p))}


def cluster_bootstrap_ci(values, clusters, n_boot: int = 20000, seed: int = 1729,
                         alpha: float = 0.05) -> dict:
    """Mean of `values` with a CI from resampling whole `clusters` (= periods).

    Snapshots inside one scoring period share the same realised outcome, so
    they are not independent; the cluster is the period.
    """
    values = np.asarray(values, dtype=float)
    clusters = np.asarray(clusters)
    if len(values) != len(clusters):
        raise ValueError('values and clusters must align')
    if len(values) == 0:
        raise ValueError('cluster_bootstrap_ci called on an empty sample')
    uniq = np.unique(clusters)
    per = np.array([values[clusters == c].mean() for c in uniq])
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(uniq), size=(n_boot, len(uniq)))
    boot = per[draws].mean(axis=1)
    return {'mean': float(values.mean()),
            'mean_of_cluster_means': float(per.mean()),
            'lo': float(np.percentile(boot, 100 * alpha / 2)),
            'hi': float(np.percentile(boot, 100 * (1 - alpha / 2))),
            'n_obs': int(len(values)), 'n_clusters': int(len(uniq))}


def in_window(dates, periods, windows: dict) -> np.ndarray:
    """Boolean mask: was the snapshot logged INSIDE its own period's window?"""
    out = []
    for d, p in zip(dates, periods):
        w = windows.get(int(p))
        if w is None:
            raise KeyError(f'no window known for period {int(p)}')
        out.append(w['start'] <= str(d) <= w['end'])
    return np.asarray(out)


# --------------------------------------------------------------------------
# ESPN truth cache
# --------------------------------------------------------------------------
def refresh_espn_cache(path: Path = ESPN_CACHE) -> dict:
    """Pull authoritative period finals + period windows from ESPN, cache them."""
    from datetime import date
    from plv_clone.league_state import LeagueState
    from scripts.xfp.lib.period_meta import resolve_period_meta
    from scripts.xfp.fetch_closed_matchup_actuals import (
        finals_from_schedule, PeriodNotFinal, MatchupNotFound)

    league = LeagueState()._get_league()
    mine = [t.team_id for t in league.teams if 'Ligers' in (t.team_name or '')]
    if len(mine) != 1:
        raise MatchupNotFound(f'expected one Ligers team, got {mine}')
    my_id = int(mine[0])
    data = league.espn_request.league_get(params={'view': ['mMatchupScore']})
    schedule = data['schedule']
    periods = sorted({int(m['matchupPeriodId']) for m in schedule
                      if 'matchupPeriodId' in m})
    today = date.today()
    finals, windows, open_periods = {}, {}, []
    for p in periods:
        meta = resolve_period_meta(league, p, today=today)
        windows[str(p)] = {'start': meta['week_start'].isoformat(),
                           'end': meta['week_end'].isoformat(),
                           'weeks': int(meta['weeks']), 'sp_cap': int(meta['sp_cap'])}
        try:
            my_f, opp_f = finals_from_schedule(schedule, my_id, p)
        except PeriodNotFinal:
            open_periods.append(p)
            continue
        except MatchupNotFound:
            continue
        finals[str(p)] = {'my': my_f, 'opp': opp_f}
    payload = {'pulled_at': pd.Timestamp.now().isoformat(), 'my_team_id': my_id,
               'finals': finals, 'windows': windows, 'open_periods': open_periods}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(f'ESPN cache refreshed -> {path} '
          f'({len(finals)} decided periods, open={open_periods})')
    return payload


def load_espn_cache(path: Path = ESPN_CACHE) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f'{path} missing. Run with --refresh-espn (needs ESPN credentials).')
    return json.loads(path.read_text(encoding='utf-8'))


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------
#: team-sigma before / after the 2026-07-29 F1 hitter-variance fix, as reported
#: in that track's own summary.  Their harness applies a hitter-share-weighted
#: multiplier; this ratio reproduces the same net team-sigma change and is used
#: only to ask "what does the POST-fix sigma look like against CORRECT labels".
F1_TEAM_SIGMA_BEFORE = 30.03
F1_TEAM_SIGMA_AFTER = 39.65


def dispersion_check(raw: pd.DataFrame, cache: dict, n_boot: int = 20000) -> dict:
    """Re-run the F1 dispersion statistic on ESPN-corrected labels.

    The F1 track concluded the win-prob model was OVER-confident
    (SD(resid/sigma) 1.379 -> 1.045 after widening hitter sigma).  That
    statistic is a ratio of a realised residual to a model sigma, and the
    residual was computed from the corrupted actuals.  Recomputing it on ESPN
    finals is a direct check of whether the widening was warranted.

    Panel construction deliberately mirrors ``validate_hitter_sigma_scale.
    _load_live_history`` (mv fillna baseline, first snapshot per period x mv)
    so the numbers are comparable to that memo's, restricted to periods ESPN
    has decided.
    """
    finals = {int(k): v for k, v in cache['finals'].items()}
    d = raw.copy()
    d['mv'] = d['model_version'].fillna('baseline')
    d = d[d['mv'].isin(LIVE_VERSIONS)]
    d = d[d['actual_my_final'].notna() & d['actual_opp_final'].notna()].copy()
    d['date'] = pd.to_datetime(d['date'])
    d = (d.sort_values(['date', 'timestamp'], kind='mergesort')
          .drop_duplicates(['period', 'mv'], keep='first'))
    d = d[[int(p) in finals for p in d['period']]].copy()
    d['gap'] = d['my_projected_total'] - d['opp_projected_total']
    d['r_logged'] = (d['actual_my_final'] - d['actual_opp_final']) - d['gap']
    d['r_true'] = np.array([finals[int(p)]['my'] - finals[int(p)]['opp']
                            for p in d['period']]) - d['gap']
    d = d[(d['win_probability'] > 1e-6) & (d['win_probability'] < 1 - 1e-6)].copy()
    d['z'] = [_norm_ppf(p) for p in d['win_probability']]
    d = d[d['z'].abs() > 1e-3].copy()
    d['sigma'] = d['gap'] / d['z']
    if (d['sigma'] <= 0).any():
        raise ValueError('logged win_probability disagrees in sign with the gap')

    scale = F1_TEAM_SIGMA_AFTER / F1_TEAM_SIGMA_BEFORE
    periods = np.array(sorted(d['period'].unique()))
    rng = np.random.default_rng(11)
    draws = rng.integers(0, len(periods), size=(n_boot, len(periods)))
    out = {'n': int(len(d)), 'n_periods': int(len(periods)),
           'f1_scale_applied': scale}
    print(f'  panel = F1 construction restricted to ESPN-decided periods: '
          f'n={len(d)} snapshots over {len(periods)} periods')
    print(f'  realised spread SD, as-logged labels  = '
          f'{math.sqrt(float((d["r_logged"] ** 2).mean())):6.2f} FP')
    print(f'  realised spread SD, ESPN finals       = '
          f'{math.sqrt(float((d["r_true"] ** 2).mean())):6.2f} FP')
    print('  SD(resid/sigma)  1.00 = calibrated, >1 over-confident, <1 too wide')
    for lbl, col, sc in (('pre-F1 model, as-logged labels ', 'r_logged', 1.0),
                         ('pre-F1 model, ESPN finals      ', 'r_true', 1.0),
                         ('post-F1 model, ESPN finals     ', 'r_true', scale)):
        ss = np.array([float(((d.loc[d['period'] == p, col]
                               / (d.loc[d['period'] == p, 'sigma'] * sc)) ** 2).sum())
                       for p in periods])
        cc = np.array([int((d['period'] == p).sum()) for p in periods])
        pt = math.sqrt(ss.sum() / cc.sum())
        boot = np.sqrt(ss[draws].sum(axis=1) / cc[draws].sum(axis=1))
        lo, hi = (float(x) for x in np.percentile(boot, [2.5, 97.5]))
        print(f'    {lbl} = {pt:.3f}  95% CI [{lo:.3f}, {hi:.3f}]')
        out[lbl.strip()] = {'dispersion': pt, 'lo': lo, 'hi': hi}
    return out


def _norm_ppf(p: float) -> float:
    from statistics import NormalDist
    return NormalDist().inv_cdf(float(p))


def _hdr(t):
    print('\n' + '=' * 78)
    print(t)
    print('=' * 78)


def build_panel(df_live: pd.DataFrame, cache: dict) -> tuple[pd.DataFrame, dict]:
    """Attach ESPN truth, flag corruption + out-of-window rows, return the panel."""
    finals = {int(k): v for k, v in cache['finals'].items()}
    windows = {int(k): v for k, v in cache['windows'].items()}
    d = df_live.copy()
    d['date'] = pd.to_datetime(d['date']).dt.strftime('%Y-%m-%d')

    d['period_decided'] = [int(p) in finals for p in d['period']]
    open_dropped = int((~d['period_decided']).sum())
    open_periods = sorted({int(p) for p, ok in zip(d['period'], d['period_decided'])
                           if not ok})
    d = d[d['period_decided']].copy()

    d['true_my'] = [finals[int(p)]['my'] for p in d['period']]
    d['true_opp'] = [finals[int(p)]['opp'] for p in d['period']]
    d['inw'] = in_window(d['date'], d['period'], windows)
    n_oow = int((~d['inw']).sum())
    oow = d.loc[~d['inw'], ['period', 'date']].drop_duplicates()

    # corruption audit on the logged labels
    corrupt = []
    for p in sorted(d['period'].unique()):
        sub = d[d['period'] == p]
        logged = sub[['actual_my_final', 'actual_opp_final']].dropna()
        if logged.empty:
            continue
        lm, lo_ = float(logged.iloc[0, 0]), float(logged.iloc[0, 1])
        tm, to = finals[int(p)]['my'], finals[int(p)]['opp']
        if abs(lm - tm) > 0.05 or abs(lo_ - to) > 0.05:
            corrupt.append({'period': int(p), 'logged_my': lm, 'logged_opp': lo_,
                            'true_my': tm, 'true_opp': to,
                            'logged_outcome': int(lm > lo_),
                            'true_outcome': int(tm > to)})

    d = d[d['inw']].copy()
    d['outcome'] = (d['true_my'] > d['true_opp']).astype(int)
    d['e_my'] = d['true_my'] - d['my_projected_total']
    d['e_opp'] = d['true_opp'] - d['opp_projected_total']
    d['resid'] = (d['true_my'] - d['true_opp']) - (d['my_projected_total']
                                                   - d['opp_projected_total'])
    rem_my = d['my_projected_total'] - d['my_wtd']
    rem_opp = d['opp_projected_total'] - d['opp_wtd']
    if (rem_my <= 0).any() or (rem_opp <= 0).any():
        raise ValueError('non-positive remaining projection in an in-window snapshot')
    d['frac_my'] = (d['true_my'] - d['my_wtd']) / rem_my - 1.0
    d['frac_opp'] = (d['true_opp'] - d['opp_wtd']) / rem_opp - 1.0
    d['frac_gap'] = d['frac_opp'] - d['frac_my']
    meta = {'open_periods_dropped': open_periods, 'open_rows_dropped': open_dropped,
            'out_of_window_rows': n_oow,
            'out_of_window_period_days': int(len(oow)),
            'out_of_window': oow.to_dict('records'),
            'corrupted_actuals': corrupt}
    return d, meta


def collapse_to_periods(sub: pd.DataFrame, prob_col: str,
                        out_col: str) -> pd.DataFrame:
    """One row per scoring period: mean predicted p, and the single outcome.

    Snapshots inside a period all resolve to the SAME win/loss, so treating
    them as independent Bernoulli trials multiplies the apparent sample size
    by ~18x and manufactures significance (an all-snapshot Poisson-binomial
    reports z=-3.2 where the period-level test reports z=-1.0).  The period is
    the experimental unit.
    """
    g = sub.groupby('period')
    out = g[out_col].nunique()
    if (out > 1).any():
        raise ValueError('a period carries two different outcomes — bad join')
    return pd.DataFrame({'p': g[prob_col].mean(), 'outcome': g[out_col].first()})


def _calib_block(sub: pd.DataFrame, prob_col: str, out_col: str, label: str,
                 n_boot: int = 20000) -> dict:
    coll = collapse_to_periods(sub, prob_col, out_col)
    pbin = poisson_binomial(coll['p'].values, coll['outcome'].values)
    mean_pred = float(coll['p'].mean())
    actual = float(coll['outcome'].mean())
    brier = float(((coll['p'] - coll['outcome']) ** 2).mean())
    gapci = cluster_bootstrap_ci(coll['outcome'] - coll['p'], coll.index,
                                 n_boot=n_boot)
    print(f'  {label:<10} snapshots={len(sub):>4} periods={len(coll):>2}  '
          f'mean_pred={mean_pred:.3f}  actual={actual:.3f}  '
          f'gap={actual - mean_pred:+.3f} [{gapci["lo"]:+.3f},{gapci["hi"]:+.3f}]  '
          f'Brier={brier:.4f}')
    print(f'  {"":<10} period-level Poisson-binomial: E[wins]={pbin["expected_wins"]:.2f} '
          f'obs={pbin["observed_wins"]:.0f} sd={pbin["sd_wins"]:.2f} '
          f'z={pbin["z"]:+.2f}  p={pbin["p_two_sided"]:.3f}')
    return {'label': label, 'n_snapshots': int(len(sub)), 'periods': int(len(coll)),
            'mean_pred': mean_pred, 'actual': actual, 'gap': actual - mean_pred,
            'gap_ci': [gapci['lo'], gapci['hi']], 'brier': brier, **pbin}


def main() -> dict:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--refresh-espn', action='store_true')
    ap.add_argument('--json', type=str, default=None)
    ap.add_argument('--n-boot', type=int, default=20000)
    args = ap.parse_args()

    cache = refresh_espn_cache() if args.refresh_espn else load_espn_cache()
    R: dict = {'espn_pulled_at': cache['pulled_at']}

    if not HISTORY.exists():
        raise FileNotFoundError(f'{HISTORY} missing')
    raw = pd.read_csv(HISTORY)
    live, rep = partition_history(raw)
    R['partition'] = rep

    _hdr('1. POPULATION PARTITION (every exclusion is loud)')
    print(f'  predictions_history.csv rows                    : {rep["n_total"]}')
    print(f'  SYNTHETIC backfill rows excluded                : '
          f'{rep["n_synthetic_excluded"]}  {rep["synthetic_versions"]}')
    print(f'  legacy NULL model_version rows excluded         : '
          f'{rep["n_legacy_null_mv_excluded"]}  (periods {rep["legacy_null_periods"]})')
    print('    ^ the previous harness fillna\'d these to "baseline", pooling a third')
    print('      model version into the baseline arm.')
    print(f'  live baseline / MA_v1 rows kept                 : {rep["n_live"]}')

    panel, meta = build_panel(live, cache)
    R['panel_meta'] = meta

    _hdr('2. ACTUALS AUDIT — what the calibration harness has been grading against')
    print(f'  periods still OPEN (no ESPN winner), dropped    : '
          f'{meta["open_periods_dropped"]} ({meta["open_rows_dropped"]} rows)')
    print(f'  snapshots logged OUTSIDE their own period window: '
          f'{meta["out_of_window_rows"]} rows on '
          f'{meta["out_of_window_period_days"]} (period, date) pairs '
          f'{meta["out_of_window"]}')
    print('    ^ these project a full remaining week onto an already-finished matchup.')
    print()
    if meta['corrupted_actuals']:
        print('  *** CORRUPTED actual_my_final / actual_opp_final in the store ***')
        print(f'  {"per":>4} {"logged":>17} {"ESPN final":>17} {"logged W":>9} {"true W":>7}')
        for c in meta['corrupted_actuals']:
            print(f'  {c["period"]:>4} {c["logged_my"]:>8.1f}-{c["logged_opp"]:<8.1f} '
                  f'{c["true_my"]:>8.1f}-{c["true_opp"]:<8.1f} '
                  f'{c["logged_outcome"]:>9} {c["true_outcome"]:>7}'
                  + ('   <-- OUTCOME FLIP' if c['logged_outcome'] != c['true_outcome']
                     else ''))
        flips = sum(c['logged_outcome'] != c['true_outcome']
                    for c in meta['corrupted_actuals'])
        print(f'  {len(meta["corrupted_actuals"])} corrupted periods, {flips} outcome flip(s).')
    else:
        print('  no corrupted actuals found.')

    _hdr('3. WIN-PROB MEAN CALIBRATION (period is the experimental unit)')
    R['calibration'] = {}
    first = (panel.sort_values(['date', 'timestamp'], kind='mergesort')
                  .drop_duplicates(['period', 'mv'], keep='first'))
    panel = panel.copy()
    panel['logged_outcome'] = (panel['actual_my_final']
                               > panel['actual_opp_final']).astype(int)
    first_logged = first.assign(
        logged_outcome=(first['actual_my_final'] > first['actual_opp_final']).astype(int))
    for anchor_label, sub_all, ocol in (
            ('FIRST snapshot / period, AS-LOGGED actuals', first_logged, 'logged_outcome'),
            ('FIRST snapshot / period, ESPN-CORRECTED', first, 'outcome'),
            ('ALL in-window snapshots, ESPN-CORRECTED', panel, 'outcome')):
        print(f'\n  --- {anchor_label} ---')
        for mv in ('ALL', *LIVE_VERSIONS):
            s = sub_all if mv == 'ALL' else sub_all[sub_all['mv'] == mv]
            if s.empty:
                continue
            R['calibration'][f'{anchor_label}|{mv}'] = _calib_block(
                s, 'win_probability', ocol, f'{mv}', n_boot=args.n_boot)

    _hdr('3b. ATTRIBUTION LADDER — where the reported -7pp actually comes from')
    finals = {int(k): v for k, v in cache['finals'].items()}
    windows = {int(k): v for k, v in cache['windows'].items()}
    rep_df = raw.copy()
    rep_df['mv'] = rep_df['model_version'].fillna('baseline')   # the OLD relabel
    rep_df = rep_df[rep_df['mv'].isin(LIVE_VERSIONS)]
    rep_df = rep_df[rep_df['actual_my_final'].notna()
                    & rep_df['actual_opp_final'].notna()].copy()
    rep_df['date'] = pd.to_datetime(rep_df['date']).dt.strftime('%Y-%m-%d')
    rep_df = (rep_df.sort_values(['date', 'timestamp'], kind='mergesort')
                    .drop_duplicates(['period', 'mv'], keep='first'))
    rep_df['o'] = (rep_df['actual_my_final'] > rep_df['actual_opp_final']).astype(int)
    ladder, R['ladder'] = [], []
    steps = [('prior harness (as reviewed)', rep_df)]
    s1 = rep_df[rep_df['model_version'].notna()]
    steps.append(('  - drop legacy NULL model_version', s1))
    s2 = s1[[int(p) in finals for p in s1['period']]]
    steps.append(('  - drop periods ESPN calls UNDECIDED', s2))
    s3 = s2[in_window(s2['date'], s2['period'], windows)]
    steps.append(('  - drop out-of-window snapshots', s3))
    s4 = s3.copy()
    s4['o'] = [int(finals[int(p)]['my'] > finals[int(p)]['opp']) for p in s4['period']]
    steps.append(('  - use ESPN finals, not logged actuals', s4))
    for name, s in steps:
        if s.empty:
            continue
        line = {'step': name, 'n': int(len(s)), 'periods': int(s['period'].nunique()),
                'mean_pred': float(s['win_probability'].mean()),
                'actual': float(s['o'].mean()),
                'brier': float(((s['win_probability'] - s['o']) ** 2).mean())}
        line['gap'] = line['actual'] - line['mean_pred']
        ladder.append(line)
        print(f'  {name:<40} n={line["n"]:>3} per={line["periods"]:>2}  '
              f'pred={line["mean_pred"]:.3f}  act={line["actual"]:.3f}  '
              f'gap={line["gap"]:+.3f}  Brier={line["brier"]:.4f}')
    R['ladder'] = ladder

    _hdr('4. WHERE THE MEAN LIVES — margin residual (period-clustered bootstrap)')
    R['margin'] = {}
    print('  resid = (true_my - true_opp) - (proj_my - proj_opp);  0 = unbiased mean.')
    for mv in ('ALL', *LIVE_VERSIONS):
        s = first if mv == 'ALL' else first[first['mv'] == mv]
        if s.empty:
            continue
        ci = cluster_bootstrap_ci(s['resid'], s['period'], n_boot=args.n_boot)
        sd = float(s['resid'].std(ddof=1))
        print(f'  {mv:<10} mean resid = {ci["mean"]:+7.2f} FP  '
              f'95% CI [{ci["lo"]:+7.2f}, {ci["hi"]:+7.2f}]  '
              f'SD={sd:.1f}  n={ci["n_obs"]} over {ci["n_clusters"]} periods')
        R['margin'][mv] = {**ci, 'sd': sd}

    _hdr('4b. DOWNSTREAM — what the corrupted labels did to the F1 VARIANCE verdict')
    R['dispersion'] = dispersion_check(raw, cache, n_boot=args.n_boot)

    _hdr('5. HYPOTHESIS 1 / 3 — is one SIDE mis-projected?')
    R['sides'] = {}
    print('  frac_my  = realised_remaining / projected_remaining - 1 for MY side')
    print('  frac_opp = same for the OPPONENT.  frac_gap = frac_opp - frac_my.')
    print('  H1 (my side over-projected) => frac_my < 0.')
    print('  H3 (opponent churn under-projects them) => frac_opp > 0 and frac_gap > 0.')
    # Periods whose calendar window spans more than one week: the dashboard's
    # projection horizon only reached the first Sunday, so both sides are
    # under-projected by roughly a week of scoring (see section 6 / the memo).
    multiweek = sorted(int(p) for p, w in cache['windows'].items()
                       if (pd.Timestamp(w['end']) - pd.Timestamp(w['start'])).days > 7)
    R['multiweek_periods'] = multiweek
    for tag, s0 in (('all periods', first),
                    (f'ex multi-week periods {multiweek} (window bug)',
                     first[~first['period'].isin(multiweek)])):
        print(f'\n  --- {tag} ---')
        for mv in ('ALL', *LIVE_VERSIONS):
            s = s0 if mv == 'ALL' else s0[s0['mv'] == mv]
            if s.empty:
                continue
            a = cluster_bootstrap_ci(s['frac_my'], s['period'], n_boot=args.n_boot)
            b = cluster_bootstrap_ci(s['frac_opp'], s['period'], n_boot=args.n_boot)
            g = cluster_bootstrap_ci(s['frac_gap'], s['period'], n_boot=args.n_boot)
            print(f'  {mv:<10} frac_my {a["mean"]:+.3f} [{a["lo"]:+.3f},{a["hi"]:+.3f}]  '
                  f'frac_opp {b["mean"]:+.3f} [{b["lo"]:+.3f},{b["hi"]:+.3f}]  '
                  f'frac_gap {g["mean"]:+.3f} [{g["lo"]:+.3f},{g["hi"]:+.3f}]')
            R['sides'][f'{tag}|{mv}'] = {'frac_my': a, 'frac_opp': b, 'frac_gap': g}

    _hdr('6. PER-PERIOD DETAIL (first snapshot, baseline arm)')
    show = first[first['mv'] == 'baseline'][
        ['period', 'date', 'my_wtd', 'my_projected_total', 'true_my', 'e_my',
         'opp_wtd', 'opp_projected_total', 'true_opp', 'e_opp', 'resid',
         'win_probability', 'outcome']]
    with pd.option_context('display.width', 250, 'display.max_columns', 50):
        print(show.sort_values('period').to_string(index=False))

    if args.json:
        Path(args.json).write_text(json.dumps(R, indent=2, default=float),
                                   encoding='utf-8')
        print(f'\nwrote {args.json}')
    return R


if __name__ == '__main__':
    main()

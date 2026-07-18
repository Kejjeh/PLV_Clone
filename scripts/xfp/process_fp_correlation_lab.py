"""process_fp_correlation_lab.py — engineered process metrics vs forward BrownU FP.

The discovery harness the swing-decision work plugs into: for every hitter and
every anchor date, compute trailing-21d PROCESS metrics from pitch-level
statcast, then correlate with FORWARD-21d realized FP/g (boxscore store) —
raw AND incremental (partial, controlling for season-to-date FP/g level,
per window_predictive_validity_2026-06-26: the season level is the best
predictor, so a process metric only matters if it adds signal BEYOND it).

Anti-fooling machinery (reference_multitesting_protocol.md):
  - Rule 8: the metric family below is PRE-REGISTERED in this header; the
    lab reports ALL of them every run, never a cherry-picked subset.
  - Non-overlapping forward windows (anchors spaced == horizon).
  - Player-clustered bootstrap (resample batters, not rows) for CIs + p.
  - Benjamini-Hochberg FDR (q=0.10) across the incremental family — the
    incremental test is the decision-relevant one.
  - Rule 13: output is a RESEARCH LEDGER. Nothing here touches rh3. A
    metric that survives FDR here earns a /validate-feature run, no more.

Pre-registered metric family (12):
  chase_pct, z_swing_pct, decision_gap, whiff_pct, swstr_pct,
  xwobacon, bat_speed, fast_swing_pct, attack_angle_dev15,
  swing_length, hardhit_pct, contact_pct

Usage:
  PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/process_fp_correlation_lab.py
Output: data/outputs/process_fp_corr_lab.csv + console report.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

STATCAST = 'data/research/xfp_cache/statcast_2026.parquet'
BOXSCORE = 'data/research/xfp_cache/boxscore_hitters.parquet'
OUT = 'data/outputs/process_fp_corr_lab.csv'

TRAIL_D = 21          # trailing process window (validated recent-form window)
FWD_D = 21            # forward target horizon
MIN_TRAIL_PITCH = 150 # trailing sample floor
MIN_FWD_G = 10        # forward games floor
MIN_SEASON_G = 20     # season-level control floor
N_BOOT = 1000
FDR_Q = 0.10
RNG = np.random.default_rng(20260717)

SWING = {'hit_into_play', 'foul', 'swinging_strike', 'swinging_strike_blocked',
         'foul_tip', 'foul_bunt', 'missed_bunt', 'bunt_foul_tip'}
WHIFF = {'swinging_strike', 'swinging_strike_blocked'}


def _pitch_flags(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['swing'] = df['description'].isin(SWING)
    df['whiff'] = df['description'].isin(WHIFF)
    df['inzone'] = df['zone'].between(1, 9)
    df['ozone'] = df['zone'].between(11, 14)
    df['bip'] = df['description'].eq('hit_into_play')
    return df


def _proc_metrics(g: pd.DataFrame) -> dict:
    n = len(g)
    sw = int(g['swing'].sum())
    iz, oz = int(g['inzone'].sum()), int(g['ozone'].sum())
    zsw = g.loc[g['inzone'], 'swing'].mean() * 100 if iz else np.nan
    chase = g.loc[g['ozone'], 'swing'].mean() * 100 if oz else np.nan
    swings = g[g['swing']]
    bs = swings['bat_speed'].dropna()
    aa = swings['attack_angle'].dropna()
    bip = g[g['bip']]
    return dict(
        n_pitch=n,
        chase_pct=chase,
        z_swing_pct=zsw,
        decision_gap=(zsw - chase) if not (np.isnan(zsw) or np.isnan(chase)) else np.nan,
        whiff_pct=(g['whiff'].sum() / sw * 100) if sw else np.nan,
        swstr_pct=g['whiff'].mean() * 100,
        xwobacon=bip['estimated_woba_using_speedangle'].mean(),
        bat_speed=bs.mean(),
        fast_swing_pct=(bs.ge(75).mean() * 100) if len(bs) else np.nan,
        attack_angle_dev15=(aa - 15).abs().mean() if len(aa) else np.nan,
        swing_length=swings['swing_length'].mean(),
        hardhit_pct=(bip['launch_speed'].ge(95).mean() * 100) if len(bip) else np.nan,
        contact_pct=(1 - g['whiff'].sum() / sw) * 100 if sw else np.nan,
    )


METRICS = ['chase_pct', 'z_swing_pct', 'decision_gap', 'whiff_pct', 'swstr_pct',
           'xwobacon', 'bat_speed', 'fast_swing_pct', 'attack_angle_dev15',
           'swing_length', 'hardhit_pct', 'contact_pct']


def build_panel() -> pd.DataFrame:
    sc = pd.read_parquet(STATCAST, columns=[
        'batter', 'game_date', 'description', 'zone',
        'estimated_woba_using_speedangle', 'bat_speed', 'attack_angle',
        'swing_length', 'launch_speed'])
    sc['game_date'] = pd.to_datetime(sc['game_date'], errors='coerce')
    sc = _pitch_flags(sc.dropna(subset=['game_date']))

    bx = pd.read_parquet(BOXSCORE)
    bx['game_date'] = pd.to_datetime(bx['game_date'])

    last = min(sc['game_date'].max(), bx['game_date'].max())
    first = bx['game_date'].min()
    # non-overlapping forward windows: anchors spaced FWD_D apart
    anchors = pd.date_range(first + pd.Timedelta(days=28),
                            last - pd.Timedelta(days=FWD_D), freq=f'{FWD_D}D')
    rows = []
    for t in anchors:
        tr = sc[(sc['game_date'] > t - pd.Timedelta(days=TRAIL_D)) & (sc['game_date'] <= t)]
        fwd = bx[(bx['game_date'] > t) & (bx['game_date'] <= t + pd.Timedelta(days=FWD_D))]
        season = bx[bx['game_date'] <= t]
        fwd_g = fwd.groupby('mlbam_id').agg(fwd_fp=('fp_h', 'mean'), fwd_n=('fp_h', 'size'))
        sea_g = season.groupby('mlbam_id').agg(season_fp=('fp_h', 'mean'), season_n=('fp_h', 'size'))
        for bid, g in tr.groupby('batter'):
            if len(g) < MIN_TRAIL_PITCH or bid not in fwd_g.index or bid not in sea_g.index:
                continue
            if fwd_g.loc[bid, 'fwd_n'] < MIN_FWD_G or sea_g.loc[bid, 'season_n'] < MIN_SEASON_G:
                continue
            rows.append(dict(anchor=t, batter=bid,
                             season_fp=sea_g.loc[bid, 'season_fp'],
                             fwd_fp=fwd_g.loc[bid, 'fwd_fp'],
                             **_proc_metrics(g)))
    return pd.DataFrame(rows)


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    xr = pd.Series(x).rank().to_numpy()
    yr = pd.Series(y).rank().to_numpy()
    if xr.std() == 0 or yr.std() == 0:
        return np.nan
    return float(np.corrcoef(xr, yr)[0, 1])


def _partial_spearman(x, y, z) -> float:
    """Spearman of x,y with control z rank-regressed out of both."""
    xr = pd.Series(x).rank().to_numpy()
    yr = pd.Series(y).rank().to_numpy()
    zr = pd.Series(z).rank().to_numpy()
    zc = np.column_stack([np.ones_like(zr), zr])
    rx = xr - zc @ np.linalg.lstsq(zc, xr, rcond=None)[0]
    ry = yr - zc @ np.linalg.lstsq(zc, yr, rcond=None)[0]
    if rx.std() == 0 or ry.std() == 0:
        return np.nan
    return float(np.corrcoef(rx, ry)[0, 1])


def _cluster_boot(df: pd.DataFrame, col: str, stat_fn) -> tuple:
    """Player-clustered bootstrap: resample batters with replacement."""
    players = df['batter'].unique()
    groups = {p: g for p, g in df.groupby('batter')}
    stats = []
    for _ in range(N_BOOT):
        pick = RNG.choice(players, size=len(players), replace=True)
        boot = pd.concat([groups[p] for p in pick], ignore_index=True)
        stats.append(stat_fn(boot))
    stats = np.array([s for s in stats if not np.isnan(s)])
    if len(stats) < 100:
        return np.nan, np.nan, np.nan
    lo, hi = np.percentile(stats, [2.5, 97.5])
    p = 2 * min((stats <= 0).mean(), (stats >= 0).mean())
    return lo, hi, max(p, 1 / len(stats))


def main() -> int:
    panel = build_panel()
    n_obs, n_players = len(panel), panel['batter'].nunique()
    n_anchors = panel['anchor'].nunique()
    print(f"panel: {n_obs} obs | {n_players} players | {n_anchors} non-overlapping anchors")
    print(f"anchors: {sorted(panel['anchor'].dt.date.unique())}")

    results = []
    for m in METRICS:
        sub = panel.dropna(subset=[m, 'fwd_fp', 'season_fp'])
        if len(sub) < 50:
            continue
        raw = _spearman(sub[m].to_numpy(), sub['fwd_fp'].to_numpy())
        inc = _partial_spearman(sub[m].to_numpy(), sub['fwd_fp'].to_numpy(),
                                sub['season_fp'].to_numpy())
        lo, hi, p = _cluster_boot(
            sub, m, lambda b, _m=m: _partial_spearman(
                b[_m].to_numpy(), b['fwd_fp'].to_numpy(), b['season_fp'].to_numpy()))
        results.append(dict(metric=m, n=len(sub), raw_spearman=raw,
                            incr_partial=inc, ci_lo=lo, ci_hi=hi, p_boot=p))

    res = pd.DataFrame(results).sort_values('p_boot')
    # Benjamini-Hochberg across the incremental family
    mtot = len(res)
    res['bh_thresh'] = [(i + 1) / mtot * FDR_Q for i in range(mtot)]
    passed, still = [], True
    for _, r in res.iterrows():
        still = still and (r['p_boot'] <= r['bh_thresh'])
        passed.append(still)
    res['fdr_pass'] = passed
    # baseline reference: how strong is the control itself?
    base = _spearman(panel['season_fp'].to_numpy(), panel['fwd_fp'].to_numpy())

    print(f"\nBASELINE control: season-to-date FP/g -> fwd FP/g  Spearman = {base:.3f}")
    print(f"\n{'metric':<20}{'n':>6}{'raw_r':>8}{'incr_r':>8}{'95% CI':>18}{'p':>8}  FDR")
    for _, r in res.iterrows():
        flag = '*** PASS' if r['fdr_pass'] else ''
        print(f"{r['metric']:<20}{r['n']:>6}{r['raw_spearman']:>8.3f}{r['incr_partial']:>8.3f}"
              f"   [{r['ci_lo']:>+.3f},{r['ci_hi']:>+.3f}]{r['p_boot']:>8.3f}  {flag}")
    res.insert(0, 'run_date', pd.Timestamp.today().date().isoformat())
    res.insert(1, 'baseline_spearman', base)
    res.to_csv(OUT, index=False)
    print(f"\nledger -> {OUT}")
    print("Rule 13: research ledger only. FDR-pass -> /validate-feature, never straight to rh3.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

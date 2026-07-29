"""build_model_scorecard.py — MODEL SCORECARD + DATA-HEALTH engine.

The permanent, repeatable measurement backbone for the production models
(rh3 / rp3 / rprs2 + the 2026-07-09 volume companions). Two sections:

1. FORWARD ACCURACY — at anchor snapshots ~7/14/21/28 days back (whichever
   exist in data/research/player_projection_history.parquet), score each
   model's projections against realized forward BrownU FP from the boxscore
   parquets. Joins are mlbam_id ONLY. Hitters are denominated per-PA
   (realized PA counted from statcast_2026.parquet at_bat_number), SPs
   per-start, RPs per-appearance (rprs2 proj is a RoS TOTAL, so RP metrics
   are rank-only). Volume floors are applied and REPORTED (survivorship:
   every forward metric is conditional on "kept playing").

2. DATA HEALTH — regression tripwires, each printing PASS/WARN/FAIL with a
   number. Motivated by the 2026-07-09 discovery that rp3's three IL
   features had been dead for ~6 weeks (join match rate 0.45%, invisible
   to LOO r). Each check is fail-soft: a missing input yields SKIP with a
   clear message, never a crash.

Outputs (idempotent — same-day re-run replaces same-day rows):
  data/outputs/model_scorecard.csv           (long: date, section, metric,
                                              segment, value, status, note)
  data/outputs/model_scorecard.md            (compact rendered scorecard)
  data/research/model_scorecard_history.csv  (dated history, appended)

Methodology lessons baked in (from the 2026-06-26 forward retro):
  * evaluate on >=20-day forward windows / >=4 realized starts where
    possible; shorter anchors are shown but flagged;
  * forward Spearman ~0.3-0.4 is the HONEST baseline (same-period r 0.77+
    is inflated) — don't panic on 0.35, panic on a sustained slide;
  * the mild positive bias on heavy-usage regulars is expected
    (conditional on volume) — context only, never a recalibration reason.

Run:  PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/build_model_scorecard.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- paths ---
try:
    from plv_clone.paths import ROOT
except Exception:  # fail-soft: derive from this file's location
    ROOT = Path(__file__).resolve().parents[2]

RESEARCH = ROOT / 'data' / 'research'
CACHE = RESEARCH / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'

HISTORY_PARQUET = RESEARCH / 'player_projection_history.parquet'
BOX_H = CACHE / 'boxscore_hitters.parquet'
BOX_P = CACHE / 'boxscore_pitchers.parquet'
STATCAST_2026 = CACHE / 'statcast_2026.parquet'
ROLLING_P_CSV = CACHE / 'rolling_pitchers_2018_2026.csv'
ROLLING_H_CSV = CACHE / 'rolling_hitters_2018_2026.csv'
ROLLING_R_CSV = CACHE / 'rolling_relievers_2018_2026.csv'
IL_CSV = CACHE / 'il_split_features_2018_2026.csv'
IL_TX_JSON = CACHE / 'il_transactions_2026.json'
ROS_SCHED_CSV = CACHE / 'ros_schedule_features_2018_2026.csv'
FG_ASOF_DIR = RESEARCH / 'fg_asof'
FG_PROJ_CACHE_DIR = RESEARCH / 'fg_proj_cache'
RH3_CSV = OUT / 'xfp_rh3_projections.csv'
RP3_CSV = OUT / 'xfp_rp3_projections.csv'
RPRS2_CSV = OUT / 'xfp_rprs2_projections.csv'
CONSOLE_JSON = OUT / 'console_data.json'
TRI_NIGHTLY_DIR = RESEARCH / 'triangulate_universe'
XFP_MODEL_DOCS = ROOT / 'xfp-model' / 'docs'
ESPN_SNAPSHOT_DIR = RESEARCH / 'espn_snapshot'
GOLDEN_STASH_DIR = ROOT / 'data' / 'models' / '.golden_stash'

SCORECARD_CSV = OUT / 'model_scorecard.csv'
SCORECARD_MD = OUT / 'model_scorecard.md'
SCORECARD_HISTORY = RESEARCH / 'model_scorecard_history.csv'

TODAY = date.today()
SEASON_START_2026 = date(2026, 3, 26)   # lib/season_dates.py anchor
ANCHOR_OFFSETS = [7, 14, 21, 28]

ROWS: list[dict] = []


def add_row(section: str, metric: str, segment: str, value, status: str,
            note: str = '') -> None:
    if isinstance(value, (float, np.floating)) and np.isfinite(value):
        value = round(float(value), 4)
    elif isinstance(value, (int, np.integer)):
        value = int(value)
    elif value is None or (isinstance(value, float) and not np.isfinite(value)):
        value = ''
    ROWS.append({
        'date': TODAY.isoformat(), 'section': section, 'metric': metric,
        'segment': segment, 'value': value, 'status': status, 'note': note,
    })


def _spearman(a: pd.Series, b: pd.Series) -> float:
    m = a.notna() & b.notna()
    if m.sum() < 10:
        return float('nan')
    return float(pd.Series(a[m]).corr(pd.Series(b[m]), method='spearman'))


# =========================================================================
# SECTION 1 — FORWARD ACCURACY
# =========================================================================

def _load_history() -> pd.DataFrame | None:
    if not HISTORY_PARQUET.exists():
        add_row('forward_accuracy', 'history_panel', 'all', None, 'SKIP',
                f'missing {HISTORY_PARQUET.name}')
        return None
    df = pd.read_parquet(HISTORY_PARQUET)
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date']).dt.date
    return df


def _load_boxscores():
    bh = pd.read_parquet(BOX_H)
    bp = pd.read_parquet(BOX_P)
    for b in (bh, bp):
        b['game_date'] = pd.to_datetime(b['game_date']).dt.date
    return bh, bp


def _load_statcast_pa() -> pd.DataFrame | None:
    """Per (batter, game_date, game_pk) PA counts from statcast pitch data."""
    if not STATCAST_2026.exists():
        return None
    sc = pd.read_parquet(
        STATCAST_2026,
        columns=['batter', 'game_date', 'game_pk', 'at_bat_number'])
    sc['game_date'] = pd.to_datetime(sc['game_date']).dt.date
    pa = (sc.drop_duplicates(['game_pk', 'at_bat_number'])
            .groupby(['batter', 'game_date', 'game_pk'])
            .size().rename('pa').reset_index())
    return pa


def _pick_anchors(dates_avail: list[date]) -> list[tuple[str, date]]:
    """Nearest available snapshot date to each target offset (within 3d)."""
    anchors, used = [], set()
    for off in ANCHOR_OFFSETS:
        target = TODAY - timedelta(days=off)
        cands = [d for d in dates_avail
                 if abs((d - target).days) <= 3 and d not in used]
        if not cands:
            continue
        best = min(cands, key=lambda d: abs((d - target).days))
        used.add(best)
        anchors.append((f'{off}d', best))
    return anchors


def _team_games(bh, bp, start, end) -> pd.Series:
    g = pd.concat([bh[['game_pk', 'game_date', 'team_id']],
                   bp[['game_pk', 'game_date', 'team_id']]])
    g = g[(g['game_date'] >= start) & (g['game_date'] <= end)]
    g = g.drop_duplicates(['game_pk', 'team_id'])
    return g.groupby('team_id').size()


def _modal_team(box: pd.DataFrame, start, end) -> pd.Series:
    w = box[(box['game_date'] >= start) & (box['game_date'] <= end)]
    if w.empty:
        return pd.Series(dtype='int64')
    return (w.groupby(['mlbam_id', 'team_id']).size().reset_index(name='n')
             .sort_values('n', ascending=False)
             .drop_duplicates('mlbam_id')
             .set_index('mlbam_id')['team_id'])


def _tercile_bias(dfm: pd.DataFrame, anchor_label: str, model: str) -> None:
    """bias = mean(proj - realized rate), MAE, by projection tercile."""
    if len(dfm) < 30:
        return
    try:
        dfm = dfm.copy()
        dfm['terc'] = pd.qcut(dfm['proj_per'], 3,
                              labels=['T1_low', 'T2_mid', 'T3_high'])
    except ValueError:
        return
    for terc, sub in dfm.groupby('terc', observed=True):
        err = sub['proj_per'] - sub['fwd_rate']
        add_row('forward_accuracy', f'{model}_bias_{anchor_label}', str(terc),
                err.mean(), 'INFO', f'n={len(sub)} MAE={err.abs().mean():.3f}')


def _backfill_maps(hist: pd.DataFrame):
    """position / data_quality_tag exist only since 2026-07-09 — build
    latest-known per-player maps so older anchors can be sliced (approx,
    flagged in notes)."""
    h = hist[(hist['player_type'] == 'H') & hist['position'].notna()]
    h = h.sort_values('snapshot_date').drop_duplicates('mlbam_id', keep='last')
    pos_map = dict(zip(h['mlbam_id'], h['position']))
    if RH3_CSV.exists():  # extra coverage from the live rh3 CSV
        try:
            rh3 = pd.read_csv(RH3_CSV, usecols=['batter', 'primary_position'])
            for k, v in zip(rh3['batter'], rh3['primary_position']):
                pos_map.setdefault(int(k), v)
        except Exception:
            pass
    s = hist[(hist['player_type'] == 'SP') & hist['data_quality_tag'].notna()]
    s = s.sort_values('snapshot_date').drop_duplicates('mlbam_id', keep='last')
    tag_map = dict(zip(s['mlbam_id'], s['data_quality_tag']))
    return pos_map, tag_map


def _eval_anchor(anchor_label: str, anchor: date, hist: pd.DataFrame,
                 bh: pd.DataFrame, bp: pd.DataFrame,
                 pa_panel: pd.DataFrame | None,
                 pos_map: dict, tag_map: dict, fwd_end: date) -> None:
    fwd_days = (fwd_end - anchor).days + 1
    snap = hist[hist['snapshot_date'] == anchor]
    note_win = f'anchor={anchor} fwd_days={fwd_days}'
    add_row('forward_accuracy', f'window_{anchor_label}', 'all', fwd_days,
            'INFO', note_win)

    # forward boxscore slices (games ON the anchor date are forward — the
    # snapshot was built that morning from data through anchor-1)
    fbh = bh[(bh['game_date'] >= anchor) & (bh['game_date'] <= fwd_end)]
    fbp = bp[(bp['game_date'] >= anchor) & (bp['game_date'] <= fwd_end)]

    # ---- HITTERS (rh3): per-PA ------------------------------------------
    hs = snap[snap['player_type'] == 'H'].dropna(subset=['proj_per'])
    hs = hs.drop_duplicates('mlbam_id')
    if not hs.empty and pa_panel is not None:
        fpa = (pa_panel[(pa_panel['game_date'] >= anchor)
                        & (pa_panel['game_date'] <= fwd_end)]
               .groupby('batter')['pa'].sum())
        ffp = fbh.groupby('mlbam_id')['fp_h'].sum()
        m = hs[['mlbam_id', 'proj_per', 'prior_per', 'position']].copy()
        m['fwd_pa'] = m['mlbam_id'].map(fpa)
        m['fwd_fp'] = m['mlbam_id'].map(ffp)
        pa_floor = max(15, int(round(1.2 * fwd_days)))
        m = m.dropna(subset=['fwd_pa', 'fwd_fp'])
        m = m[m['fwd_pa'] >= pa_floor]
        m['fwd_rate'] = m['fwd_fp'] / m['fwd_pa']
        base_note = f'{note_win} n={len(m)} pa_floor={pa_floor} (survivorship: conditional on volume)'
        add_row('forward_accuracy', f'rh3_spearman_rate_{anchor_label}', 'all',
                _spearman(m['proj_per'], m['fwd_rate']),
                'INFO' if len(m) >= 30 else 'INSUFFICIENT', base_note)
        add_row('forward_accuracy', f'rh3_spearman_total_{anchor_label}', 'all',
                _spearman(m['proj_per'], m['fwd_fp']), 'INFO',
                f'n={len(m)} rate-model vs fwd TOTAL fp')
        mp = m.dropna(subset=['prior_per'])
        if len(mp) >= 30:
            d = (_spearman(mp['proj_per'], mp['fwd_rate'])
                 - _spearman(mp['prior_per'], mp['fwd_rate']))
            add_row('forward_accuracy', f'rh3_vs_prior_delta_{anchor_label}',
                    'all', d, 'INFO',
                    f'n={len(mp)} spearman(model)-spearman(prior); >0 = in-season layer earning')
        _tercile_bias(m, anchor_label, 'rh3')
        # position slice: C vs rest
        m['pos_eff'] = m['position']
        miss = m['pos_eff'].isna()
        m.loc[miss, 'pos_eff'] = m.loc[miss, 'mlbam_id'].map(pos_map)
        bf = ' (position backfilled from latest snapshot)' if miss.any() else ''
        for seg, sub in [('C', m[m['pos_eff'] == 'C']),
                         ('non_C', m[m['pos_eff'].notna() & (m['pos_eff'] != 'C')])]:
            add_row('forward_accuracy', f'rh3_spearman_rate_{anchor_label}',
                    seg, _spearman(sub['proj_per'], sub['fwd_rate']),
                    'INFO' if len(sub) >= 15 else 'INSUFFICIENT',
                    f'n={len(sub)}{bf}')

    # ---- SP (rp3): per-start --------------------------------------------
    ss = snap[snap['player_type'] == 'SP'].dropna(subset=['proj_per'])
    ss = ss.drop_duplicates('mlbam_id')
    if not ss.empty:
        starts = fbp[fbp['gs'] == 1]
        agg = starts.groupby('mlbam_id').agg(fwd_starts=('gs', 'sum'),
                                             fwd_fp=('fp_sp', 'sum'))
        m = ss[['mlbam_id', 'proj_per', 'prior_per', 'data_quality_tag']].merge(
            agg, on='mlbam_id', how='inner')
        gs_floor = 4 if fwd_days >= 20 else (2 if fwd_days >= 7 else 1)
        m = m[m['fwd_starts'] >= gs_floor]
        m['fwd_rate'] = m['fwd_fp'] / m['fwd_starts']
        base_note = f'{note_win} n={len(m)} start_floor={gs_floor} (survivorship: conditional on volume)'
        add_row('forward_accuracy', f'rp3_spearman_rate_{anchor_label}', 'all',
                _spearman(m['proj_per'], m['fwd_rate']),
                'INFO' if len(m) >= 30 else 'INSUFFICIENT', base_note)
        add_row('forward_accuracy', f'rp3_spearman_total_{anchor_label}', 'all',
                _spearman(m['proj_per'], m['fwd_fp']), 'INFO',
                f'n={len(m)} rate-model vs fwd TOTAL fp')
        mp = m.dropna(subset=['prior_per'])
        if len(mp) >= 30:
            d = (_spearman(mp['proj_per'], mp['fwd_rate'])
                 - _spearman(mp['prior_per'], mp['fwd_rate']))
            add_row('forward_accuracy', f'rp3_vs_prior_delta_{anchor_label}',
                    'all', d, 'INFO',
                    f'n={len(mp)} spearman(model)-spearman(prior); >0 = in-season layer earning')
        _tercile_bias(m, anchor_label, 'rp3')
        # data_quality_tag slice
        m['tag_eff'] = m['data_quality_tag']
        miss = m['tag_eff'].isna()
        m.loc[miss, 'tag_eff'] = m.loc[miss, 'mlbam_id'].map(tag_map)
        bf = ' (tag backfilled from latest snapshot — approx for old anchors)' if miss.any() else ''
        m['tag_grp'] = np.where(
            m['tag_eff'].astype(str).str.startswith('data_driven'), 'data_driven',
            np.where(m['tag_eff'] == 'marcel_il', 'marcel_il', 'other'))
        for seg, sub in m.groupby('tag_grp'):
            if seg == 'other' and len(sub) < 10:
                continue
            add_row('forward_accuracy', f'rp3_spearman_rate_{anchor_label}',
                    seg, _spearman(sub['proj_per'], sub['fwd_rate']),
                    'INFO' if len(sub) >= 15 else 'INSUFFICIENT',
                    f'n={len(sub)}{bf}')

    # ---- RP (rprs2): proj is a RoS TOTAL -> rank-only metrics ------------
    rs = snap[snap['player_type'] == 'RP'].dropna(subset=['proj_per'])
    rs = rs.drop_duplicates('mlbam_id')
    if not rs.empty:
        relief = fbp[fbp['gs'] == 0]
        agg = relief.groupby('mlbam_id').agg(fwd_apps=('gs', 'size'),
                                             fwd_fp=('fp_rp', 'sum'))
        m = rs[['mlbam_id', 'proj_per']].merge(agg, on='mlbam_id', how='inner')
        app_floor = max(3, fwd_days // 4)
        m = m[m['fwd_apps'] >= app_floor]
        m['fwd_rate'] = m['fwd_fp'] / m['fwd_apps']
        add_row('forward_accuracy', f'rprs2_spearman_total_{anchor_label}', 'all',
                _spearman(m['proj_per'], m['fwd_fp']),
                'INFO' if len(m) >= 30 else 'INSUFFICIENT',
                f'{note_win} n={len(m)} app_floor={app_floor} proj=RoS-total (rank-only; incl sv/hld)')
        add_row('forward_accuracy', f'rprs2_spearman_rate_{anchor_label}', 'all',
                _spearman(m['proj_per'], m['fwd_rate']), 'INFO',
                f'n={len(m)} vs fwd fp/appearance')


def _eval_volume(anchor_label: str, anchor: date, hist: pd.DataFrame,
                 bh: pd.DataFrame, bp: pd.DataFrame,
                 pa_panel: pd.DataFrame | None, fwd_end: date) -> None:
    """Volume skill: Spearman(proj_volume, realized fwd PA/starts per
    team-game) vs the naive backward-pace comparator. The volume models
    shipped 2026-07-09 — this scorecard is their ongoing referee."""
    fwd_days = (fwd_end - anchor).days + 1
    snap = hist[hist['snapshot_date'] == anchor]
    tg_fwd = _team_games(bh, bp, anchor, fwd_end)
    tg_back = _team_games(bh, bp, SEASON_START_2026, anchor - timedelta(days=1))
    enough = (fwd_days >= 5)

    # ---- hitter volume: PA per team-game --------------------------------
    hs = snap[(snap['player_type'] == 'H')].dropna(subset=['proj_volume'])
    hs = hs.drop_duplicates('mlbam_id')
    if not hs.empty and pa_panel is not None:
        team_fwd = _modal_team(bh, anchor, fwd_end)
        team_back = _modal_team(bh, SEASON_START_2026, anchor - timedelta(days=1))
        fpa = (pa_panel[(pa_panel['game_date'] >= anchor)
                        & (pa_panel['game_date'] <= fwd_end)]
               .groupby('batter')['pa'].sum())
        bpa = (pa_panel[pa_panel['game_date'] < anchor]
               .groupby('batter')['pa'].sum())
        m = hs[['mlbam_id', 'proj_volume']].copy()
        m['fwd_pa'] = m['mlbam_id'].map(fpa)
        m['tg_f'] = m['mlbam_id'].map(team_fwd).map(tg_fwd)
        m['back_pa'] = m['mlbam_id'].map(bpa)
        m['tg_b'] = m['mlbam_id'].map(team_back).map(tg_back)
        m = m.dropna(subset=['fwd_pa', 'tg_f', 'back_pa', 'tg_b'])
        m = m[(m['tg_f'] > 0) & (m['tg_b'] > 0)]
        m['realized'] = m['fwd_pa'] / m['tg_f']
        m['naive'] = m['back_pa'] / m['tg_b']
        st = 'INFO' if (enough and len(m) >= 30) else 'INSUFFICIENT'
        r_model = _spearman(m['proj_volume'], m['realized'])
        r_naive = _spearman(m['naive'], m['realized'])
        note = (f'anchor={anchor} fwd_days={fwd_days} n={len(m)}; '
                f'naive(backward PA pace)={r_naive:.3f}' if np.isfinite(r_naive)
                else f'anchor={anchor} fwd_days={fwd_days} n={len(m)}')
        add_row('forward_accuracy', f'vol_h_spearman_{anchor_label}', 'model',
                r_model, st, note)
        add_row('forward_accuracy', f'vol_h_spearman_{anchor_label}', 'naive',
                r_naive, st, 'backward season PA-pace comparator')
        if np.isfinite(r_model) and np.isfinite(r_naive):
            add_row('forward_accuracy', f'vol_h_edge_vs_naive_{anchor_label}',
                    'all', r_model - r_naive, st,
                    'validated 2026-07-09 at +0.074 — watch for decay')

    # ---- SP volume: GS per team-game -------------------------------------
    ss = snap[(snap['player_type'] == 'SP')].dropna(subset=['proj_volume'])
    ss = ss.drop_duplicates('mlbam_id')
    if not ss.empty:
        team_fwd = _modal_team(bp, anchor, fwd_end)
        team_back = _modal_team(bp, SEASON_START_2026, anchor - timedelta(days=1))
        f_gs = (bp[(bp['game_date'] >= anchor) & (bp['game_date'] <= fwd_end)]
                .groupby('mlbam_id')['gs'].sum())
        b_gs = (bp[bp['game_date'] < anchor].groupby('mlbam_id')['gs'].sum())
        m = ss[['mlbam_id', 'proj_volume']].copy()
        m['fwd_gs'] = m['mlbam_id'].map(f_gs)
        m['tg_f'] = m['mlbam_id'].map(team_fwd).map(tg_fwd)
        m['back_gs'] = m['mlbam_id'].map(b_gs)
        m['tg_b'] = m['mlbam_id'].map(team_back).map(tg_back)
        m = m.dropna(subset=['fwd_gs', 'tg_f', 'back_gs', 'tg_b'])
        m = m[(m['tg_f'] > 0) & (m['tg_b'] > 0)]
        m['realized'] = m['fwd_gs'] / m['tg_f']
        m['naive'] = m['back_gs'] / m['tg_b']
        st = 'INFO' if (enough and len(m) >= 30) else 'INSUFFICIENT'
        r_model = _spearman(m['proj_volume'], m['realized'])
        r_naive = _spearman(m['naive'], m['realized'])
        add_row('forward_accuracy', f'vol_sp_spearman_{anchor_label}', 'model',
                r_model, st, f'anchor={anchor} fwd_days={fwd_days} n={len(m)}')
        add_row('forward_accuracy', f'vol_sp_spearman_{anchor_label}', 'naive',
                r_naive, st, 'backward season GS-pace comparator')
        if np.isfinite(r_model) and np.isfinite(r_naive):
            add_row('forward_accuracy', f'vol_sp_edge_vs_naive_{anchor_label}',
                    'all', r_model - r_naive, st,
                    'validated 2026-07-09 at +0.100 — watch for decay')


def run_forward_accuracy() -> None:
    hist = _load_history()
    if hist is None:
        return
    try:
        bh, bp = _load_boxscores()
    except Exception as e:
        add_row('forward_accuracy', 'boxscores', 'all', None, 'SKIP',
                f'boxscore load failed: {e}')
        return
    try:
        pa_panel = _load_statcast_pa()
    except Exception as e:
        pa_panel = None
        add_row('forward_accuracy', 'statcast_pa', 'all', None, 'SKIP',
                f'statcast PA count failed (hitter rate metrics degraded): {e}')

    fwd_end = min(bh['game_date'].max(), bp['game_date'].max())
    dates_avail = sorted(hist['snapshot_date'].unique())
    pos_map, tag_map = _backfill_maps(hist)

    anchors = _pick_anchors(list(dates_avail))
    if not anchors:
        add_row('forward_accuracy', 'anchors', 'all', 0, 'SKIP',
                'no usable anchor snapshots found')
        return
    for label, anchor in anchors:
        if (fwd_end - anchor).days < 3:
            add_row('forward_accuracy', f'window_{label}', 'all',
                    (fwd_end - anchor).days, 'INSUFFICIENT',
                    f'anchor={anchor} too close to boxscore frontier {fwd_end}')
            continue
        _eval_anchor(label, anchor, hist, bh, bp, pa_panel,
                     pos_map, tag_map, fwd_end)

    # volume skill: earliest snapshot carrying proj_volume (2026-07-09+),
    # plus any regular anchor that has it
    vol_dates = sorted(hist.loc[hist['proj_volume'].notna(),
                                'snapshot_date'].unique())
    if vol_dates:
        vol_anchor = vol_dates[0]
        if (fwd_end - vol_anchor).days < 1:
            add_row('forward_accuracy', 'volume_skill', 'all', None,
                    'INSUFFICIENT',
                    f'earliest proj_volume snapshot is {vol_anchor}; no forward '
                    f'games realized yet (boxscore frontier {fwd_end}). First '
                    'meaningful read ~5+ days after — keep running weekly.')
        else:
            label = f'volD{(TODAY - vol_anchor).days}'
            _eval_volume(label, vol_anchor, hist, bh, bp, pa_panel, fwd_end)
    else:
        add_row('forward_accuracy', 'volume_skill', 'all', None, 'SKIP',
                'no snapshot rows carry proj_volume yet')


# =========================================================================
# SECTION 2 — DATA HEALTH (regression tripwires)
# =========================================================================

def _run_check(name: str, fn) -> None:
    try:
        fn()
    except Exception as e:
        add_row('data_health', name, 'all', None, 'SKIP',
                f'check crashed / input missing: {type(e).__name__}: {e}')


def check_il_join() -> None:
    """The 2026-07-09 canonical bug: rolling x il_split_features join match
    rate collapsed to 0.45% (healthy ~27-32%). FAIL <5%, WARN <20%."""
    if not (ROLLING_P_CSV.exists() and IL_CSV.exists()):
        add_row('data_health', 'il_join_match_rate', 'all', None, 'SKIP',
                'rolling or il_split_features CSV missing')
        return
    rolling = pd.read_csv(ROLLING_P_CSV,
                          usecols=['pitcher', 'year', 'split_day'])
    il = pd.read_csv(IL_CSV)
    merged = rolling.merge(il, on=['pitcher', 'year', 'split_day'], how='left')
    merged['hit'] = merged['il_stints_to'].fillna(0) > 0
    # primary tripwire: whole-substrate match rate
    rate = float(merged['hit'].mean())
    status = 'FAIL' if rate < 0.05 else ('WARN' if rate < 0.20 else 'PASS')
    add_row('data_health', 'il_join_match_rate', 'all_years', rate, status,
            f'healthy ~0.27-0.32; the 2026-07-09 dead-join bug read 0.0045 (n={len(merged)})')
    # 2026 segment: season-to-date stints are structurally lower mid-season,
    # so calibrate against prior years AT THE SAME split_day (excluding years
    # with no IL coverage at all, e.g. 2018)
    cur = merged[merged['year'] == 2026]
    if cur.empty:
        add_row('data_health', 'il_join_match_rate', '2026', None, 'FAIL',
                'no 2026 rows on the rolling grid')
        return
    cur_rate = float(cur['hit'].mean())
    sd_max = int(cur['split_day'].max())
    hist = merged[(merged['year'] < 2026) & (merged['split_day'] <= sd_max)]
    yr_rates = hist.groupby('year')['hit'].mean()
    comp = float(yr_rates[yr_rates > 0].mean()) if (yr_rates > 0).any() else float('nan')
    ratio = cur_rate / comp if comp and np.isfinite(comp) else float('nan')
    status = ('FAIL' if (not np.isfinite(ratio) or ratio < 0.25)
              else 'WARN' if ratio < 0.55 else 'PASS')
    add_row('data_health', 'il_join_match_rate', '2026', cur_rate, status,
            f'ratio {ratio:.2f} vs prior-year same-split-day comparator '
            f'{comp:.3f} (n={len(cur)}); collapse (<0.25x) = dead join')


def check_il_grid_coverage() -> None:
    """The IL cache's (year, split_day) grid must cover every rolling
    substrate's grid EXACTLY — the rp3/harness IL join is an exact merge on
    (pitcher, year, split_day), so a missing grid cell silently un-joins
    every pitcher at that split (the 2026-07-09 root cause: rolling moved
    to a weekly grid while the IL cache stayed monthly). refresh_all.py now
    builds IL features AFTER the rolling substrates; any missing cell here
    means that ordering (or the grid derivation) regressed. Complements
    il_join_match_rate, which measures the CONSEQUENCE (match rate) rather
    than the cause (grid drift)."""
    if not IL_CSV.exists():
        add_row('data_health', 'il_grid_coverage', 'all', None, 'SKIP',
                'il_split_features CSV missing')
        return
    il = pd.read_csv(IL_CSV, usecols=['year', 'split_day']).drop_duplicates()
    il_grid = {(int(y), int(s)) for y, s in il.itertuples(index=False)}
    for label, path in [('rolling_pitchers', ROLLING_P_CSV),
                        ('rolling_hitters', ROLLING_H_CSV),
                        ('rolling_relievers', ROLLING_R_CSV)]:
        if not path.exists():
            add_row('data_health', 'il_grid_coverage', label, None, 'SKIP',
                    f'{path.name} missing')
            continue
        d = pd.read_csv(path, usecols=['year', 'split_day']).drop_duplicates()
        need = {(int(y), int(s)) for y, s in d.itertuples(index=False)}
        missing = sorted(need - il_grid)
        status = 'FAIL' if missing else 'PASS'
        preview = ', '.join(f'{y}/{s}' for y, s in missing[:8])
        note = (f'{len(missing)}/{len(need)} substrate grid cells absent from '
                f'IL cache' + (f' (first: {preview})' if missing else ''))
        add_row('data_health', 'il_grid_coverage', label,
                len(missing), status, note)


def check_il_tx_json_freshness() -> None:
    """il_transactions_2026.json self-refresh liveness. The refetch in
    build_il_split_features triggers whenever the newest cached event is
    >STALE_AFTER_DAYS(=3) old, so in-season the file mtime naturally cycles
    every ~4 days; an mtime older than ~8 days means the self-refresh
    stopped running (the 2026-05-06 frozen-cache failure mode, which held
    the JSON at 1,807 events for 6 weeks). Newest-EVENT staleness is
    WARN-only by design: during league-wide pauses (the ASG break) no IL
    transactions occur anywhere, so an event-date FAIL would false-fire
    exactly when nothing is wrong."""
    if not IL_TX_JSON.exists():
        add_row('data_health', 'il_tx_json_freshness', 'all', None, 'SKIP',
                f'missing {IL_TX_JSON.name}')
        return
    mtime_age = (datetime.now()
                 - datetime.fromtimestamp(os.path.getmtime(IL_TX_JSON))).days
    status = 'FAIL' if mtime_age > 8 else ('WARN' if mtime_age > 5 else 'PASS')
    add_row('data_health', 'il_tx_json_freshness', 'file_mtime', mtime_age,
            status, 'proves the STALE_AFTER_DAYS self-refresh is running '
            '(in-season natural cycle ~4d)')
    try:
        rows = json.loads(IL_TX_JSON.read_text(encoding='utf-8'))
        max_d = max((r.get('date') or '') for r in rows) if rows else ''
    except Exception as e:
        add_row('data_health', 'il_tx_json_freshness', 'newest_event', None,
                'WARN', f'JSON unreadable: {type(e).__name__}: {e}')
        return
    if not max_d:
        add_row('data_health', 'il_tx_json_freshness', 'newest_event', None,
                'WARN', 'no dated events in cache')
        return
    ev_age = (TODAY - date.fromisoformat(max_d[:10])).days
    status = 'WARN' if ev_age > 7 else 'PASS'
    add_row('data_health', 'il_tx_json_freshness', 'newest_event', ev_age,
            status, f'newest IL event {max_d[:10]} (WARN-only: ASG break / '
            'transaction lulls are legitimate)')


def check_ros_opp_xwoba() -> None:
    """NaN-pre-fill rate of ros_opp_xwoba_weighted on the 2026 rolling grid."""
    if not (ROLLING_P_CSV.exists() and ROS_SCHED_CSV.exists()):
        add_row('data_health', 'ros_opp_xwoba_nan_rate', '2026', None, 'SKIP',
                'rolling or ros_schedule_features CSV missing')
        return
    rolling = pd.read_csv(ROLLING_P_CSV,
                          usecols=['pitcher', 'year', 'split_day'])
    rolling = rolling[rolling['year'] == 2026]
    ros = pd.read_csv(ROS_SCHED_CSV)
    merged = rolling.merge(ros, on=['pitcher', 'year', 'split_day'], how='left')
    nan_rate = float(merged['ros_opp_xwoba_weighted'].isna().mean())
    status = 'FAIL' if nan_rate > 0.50 else ('WARN' if nan_rate > 0.20 else 'PASS')
    add_row('data_health', 'ros_opp_xwoba_nan_rate', '2026', nan_rate, status,
            f'fraction of 2026 rolling rows with no schedule-strength value pre-fill (n={len(merged)})')


def check_ros_cache_frozen() -> None:
    """Frozen-cache detector: ros cache max split_day vs rolling grid and
    vs the calendar season day."""
    if not ROS_SCHED_CSV.exists():
        add_row('data_health', 'ros_cache_split_day_lag', 'all', None, 'SKIP',
                'ros_schedule_features CSV missing')
        return
    ros = pd.read_csv(ROS_SCHED_CSV, usecols=['year', 'split_day'])
    ros26 = ros[ros['year'] == 2026]
    if ros26.empty:
        add_row('data_health', 'ros_cache_split_day_lag', 'all', None, 'FAIL',
                'no 2026 rows in ros schedule cache at all')
        return
    ros_max = int(ros26['split_day'].max())
    season_day = (TODAY - SEASON_START_2026).days
    lag_cal = season_day - ros_max
    seg_notes = [f'ros max split_day={ros_max}, season day={season_day}']
    if ROLLING_P_CSV.exists():
        roll = pd.read_csv(ROLLING_P_CSV, usecols=['year', 'split_day'])
        roll_max = int(roll.loc[roll['year'] == 2026, 'split_day'].max())
        lag_roll = roll_max - ros_max
        status = 'FAIL' if lag_roll > 14 else ('WARN' if lag_roll > 7 else 'PASS')
        add_row('data_health', 'ros_cache_split_day_lag', 'vs_rolling_grid',
                lag_roll, status,
                f'rolling 2026 max split_day={roll_max}; ' + seg_notes[0])
    status = 'FAIL' if lag_cal > 21 else ('WARN' if lag_cal > 10 else 'PASS')
    add_row('data_health', 'ros_cache_split_day_lag', 'vs_calendar', lag_cal,
            status, seg_notes[0] + ' (weekly grid: some lag is normal)')


def _date_lag_check(name: str, path: Path, date_getter, warn: int, fail: int,
                    note: str = '') -> None:
    if not path.exists():
        add_row('data_health', name, 'all', None, 'SKIP', f'missing {path.name}')
        return
    max_d = date_getter(path)
    lag = (TODAY - max_d).days
    status = 'FAIL' if lag >= fail else ('WARN' if lag >= warn else 'PASS')
    add_row('data_health', name, 'all', lag, status,
            f'max date {max_d} ({note})' if note else f'max date {max_d}')


def check_statcast_lag() -> None:
    def getter(p):
        d = pd.read_parquet(p, columns=['game_date'])['game_date'].max()
        return pd.to_datetime(d).date()
    _date_lag_check('statcast_max_date_lag_days', STATCAST_2026, getter,
                    warn=3, fail=5,
                    note='gf bridge should keep this at ~1 day')


def check_boxscore_lag() -> None:
    def getter(p):
        d = pd.read_parquet(p, columns=['game_date'])['game_date'].max()
        return pd.to_datetime(d).date()
    _date_lag_check('boxscore_hitters_lag_days', BOX_H, getter, warn=3, fail=5)
    _date_lag_check('boxscore_pitchers_lag_days', BOX_P, getter, warn=3, fail=5)


def check_fg_snapshot_age() -> None:
    """FG 2026 'current' snapshot age — SILENT-SCRAPE-FAILURE tripwire.

    fg_2026_current.py is a DAILY refresh step (0.8), but it's an
    undetected-chromedriver scrape that (a) flakes often and (b) exits 0 even
    when chromedriver crashes — so the refresh's fail-soft `run()` prints ✓
    while the file never updates. Age is therefore the ONLY signal that the
    scrape has been failing. Thresholds are DAILY-tight (a daily step 3+ days
    old means ≥2 consecutive silent failures), not the multi-day-cadence
    thresholds used for weekly caches. Canonical: 2026-07-20, FG frozen 6d at
    7/14 across daily auto-refreshes while every run logged success.
    """
    pats = sorted(glob.glob(str(FG_ASOF_DIR / 'fg_*_2026_current.csv')))
    if not pats:
        # a daily step producing NOTHING is worse than a stale file
        add_row('data_health', 'fg_scrape_silent_fail', 'all', None,
                'FAIL', 'no fg_*_2026_current.csv in fg_asof — the daily FG '
                'scrape (step 0.8) has never succeeded / output is missing')
        return
    for p in pats:
        age = (datetime.now() - datetime.fromtimestamp(os.path.getmtime(p))).days
        # daily step: >2d WARN (≥1 missed daily scrape), >5d FAIL (a week of
        # silent flakes — Stuff+/floor/sustainability are frozen)
        status = 'FAIL' if age > 5 else ('WARN' if age > 2 else 'PASS')
        note = 'mtime-based; daily step (0.8)'
        if status != 'PASS':
            note += (f' — FG scrape appears to be SILENTLY FAILING '
                     f'({age}d since last successful update; it exits 0 on '
                     f'chromedriver crash). Run scripts/_oneoff/fg_2026_current.py '
                     f'in an interactive shell with a working Chrome.')
        add_row('data_health', 'fg_scrape_silent_fail', Path(p).name,
                age, status, note)


def check_fg_proj_cache_gaps() -> None:
    """fg_proj_cache accumulation: missing days + system completeness in
    the last 14 calendar days."""
    files = glob.glob(str(FG_PROJ_CACHE_DIR / '*.csv'))
    dated = {}
    for f in files:
        name = Path(f).name
        if len(name) > 10 and name[4] == '-' and name[7] == '-':
            try:
                d = date.fromisoformat(name[:10])
            except ValueError:
                continue
            dated.setdefault(d, set()).add(name[11:].replace('.csv', ''))
    if not dated:
        add_row('data_health', 'fg_proj_cache_missing_days_14d', 'all', None,
                'SKIP', 'no dated files in fg_proj_cache')
        return
    # inception-aware: the cache only began accumulating on its earliest
    # dated file — days before inception are not "missed" (subsystem
    # shipped 2026-07-09; don't fail it for not existing in June)
    inception = min(dated)
    last14 = [TODAY - timedelta(days=i) for i in range(14)]
    window = [d for d in last14 if d >= inception]
    missing = [d for d in window if d not in dated]
    trunc = (f' (window truncated to inception {inception}: '
             f'{len(window)}d observed)') if len(window) < 14 else ''
    status = ('FAIL' if len(missing) > 5 else
              'WARN' if len(missing) > 2 else 'PASS')
    add_row('data_health', 'fg_proj_cache_missing_days_14d', 'all',
            len(missing), status,
            ('missing: ' + (', '.join(str(d) for d in sorted(missing)) or 'none'))
            + trunc)
    # per-system completeness on the latest cached date
    expected = set().union(*[dated[d] for d in last14 if d in dated])
    latest = max(d for d in dated if d in last14) if any(d in dated for d in last14) else max(dated)
    absent = sorted(expected - dated[latest])
    status = 'WARN' if absent else 'PASS'
    add_row('data_health', 'fg_proj_cache_systems_latest', str(latest),
            len(dated[latest]), status,
            f'{len(dated[latest])}/{len(expected)} systems; absent: '
            + (', '.join(absent) or 'none'))


def check_projection_rowcounts(hist: pd.DataFrame | None) -> None:
    """Row-count delta per model vs ~7d ago (>20% swing = WARN, >40% FAIL),
    computed from the projection-history panel (data-driven, no CSV
    archaeology needed)."""
    if hist is None or hist.empty:
        add_row('data_health', 'proj_rowcount_delta_7d', 'all', None, 'SKIP',
                'no projection history panel')
        return
    counts = (hist.groupby(['snapshot_date', 'player_type']).size()
                  .rename('n').reset_index())
    latest = counts['snapshot_date'].max()
    target = latest - timedelta(days=7)
    dates = sorted(counts['snapshot_date'].unique())
    past_cands = [d for d in dates if abs((d - target).days) <= 3 and d < latest]
    if not past_cands:
        add_row('data_health', 'proj_rowcount_delta_7d', 'all', None, 'SKIP',
                'no snapshot near 7d ago to compare against')
        return
    past = min(past_cands, key=lambda d: abs((d - target).days))
    for ptype, model in [('H', 'rh3'), ('SP', 'rp3'), ('RP', 'rprs2')]:
        now_n = counts.loc[(counts['snapshot_date'] == latest)
                           & (counts['player_type'] == ptype), 'n']
        old_n = counts.loc[(counts['snapshot_date'] == past)
                           & (counts['player_type'] == ptype), 'n']
        if now_n.empty or old_n.empty:
            add_row('data_health', 'proj_rowcount_delta_7d', model, None,
                    'SKIP', f'missing {ptype} rows at {latest} or {past}')
            continue
        now_v, old_v = int(now_n.iloc[0]), int(old_n.iloc[0])
        pct = (now_v - old_v) / old_v if old_v else float('nan')
        status = ('FAIL' if abs(pct) > 0.40 else
                  'WARN' if abs(pct) > 0.20 else 'PASS')
        add_row('data_health', 'proj_rowcount_delta_7d', model, pct, status,
                f'{old_v} rows @ {past} -> {now_v} rows @ {latest}')


def check_proj_volume_fill(hist: pd.DataFrame | None) -> None:
    """proj_volume fill rate on the latest snapshot (H and SP; RP has no
    volume model yet)."""
    if hist is None or hist.empty:
        add_row('data_health', 'proj_volume_fill_rate', 'all', None, 'SKIP',
                'no projection history panel')
        return
    latest = hist['snapshot_date'].max()
    snap = hist[hist['snapshot_date'] == latest]
    for ptype, model in [('H', 'hitter'), ('SP', 'sp')]:
        sub = snap[snap['player_type'] == ptype]
        if sub.empty:
            add_row('data_health', 'proj_volume_fill_rate', model, None,
                    'SKIP', f'no {ptype} rows at {latest}')
            continue
        rate = float(sub['proj_volume'].notna().mean())
        status = ('FAIL' if rate < 0.30 else
                  'WARN' if rate < 0.60 else 'PASS')
        add_row('data_health', 'proj_volume_fill_rate', model, rate, status,
                f'{sub["proj_volume"].notna().sum()}/{len(sub)} rows @ {latest} '
                '(tail-rank players legitimately lack a volume row)')


# -------------------------------------------------------------------------
# DRIFT SENTINELS (added 2026-07-29)
#
# Motivation: the Max Muncy collision gate rotted SILENTLY. `resolve_batter_id`
# went from "refuses to guess" to "returns the wrong player" because ESPN's team
# code for the Athletics drifted to "Oak" while KNOWN_COLLISIONS still keyed
# "ATH", and the gate then fell through to a position hint that no longer
# separated the two players. Nothing alerted; it surfaced only because a live FA
# board produced an obviously wrong row. These three checks make that class of
# rot loud and nightly. All are OFFLINE — they read committed artifacts only.
# -------------------------------------------------------------------------

ROSTER_HISTORY_PARQUET = RESEARCH / 'matchup_rosters_history.parquet'
FA_SNAPSHOT_DIR = RESEARCH / 'fa_snapshots'


def _live_espn_team_codes() -> set:
    """The ESPN `pro_team` vocabulary, offline, from the roster history panel.

    This is the vocabulary that actually reaches the resolvers at runtime
    ('Oak', 'ChW', 'Wsh', ...) — distinct from the Statcast codes the model CSVs
    carry ('ATH', 'CWS', 'WSH'). The whole point of the reachability check is
    that these two vocabularies must be bridged by team_key().
    """
    df = pd.read_parquet(ROSTER_HISTORY_PARQUET, columns=['snapshot_date', 'pro_team'])
    df = df[df['pro_team'].notna() & (df['pro_team'].astype(str).str.strip() != '')]
    if df.empty:
        return set()
    # last 30 days is plenty to see all 30 clubs, and keeps a long-dead
    # abbreviation from a prior season out of the vocabulary
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date']).dt.date
    recent = df[df['snapshot_date'] >= (TODAY - timedelta(days=30))]
    use = recent if not recent.empty else df
    return {str(t).strip() for t in use['pro_team'].unique()}


def check_collision_team_reachability() -> None:
    """Every KNOWN_COLLISIONS team hint must be reachable from a LIVE ESPN code.

    The 2026-07-29 failure: KNOWN_COLLISIONS['Max Muncy'] carried team 'ATH',
    ESPN reported 'Oak', team_key had no OAK->ATH bridge in the gate's compare,
    so the team filter matched zero candidates and the resolver fell through.
    FAIL on any entry no live code can reach — that entry's disambiguator is dead.
    """
    from plv_clone.utils.name_match import (
        KNOWN_COLLISIONS, KNOWN_PITCHER_COLLISIONS, team_key)

    if not ROSTER_HISTORY_PARQUET.exists():
        add_row('data_health', 'collision_team_reachability', 'all', None,
                'SKIP', 'matchup_rosters_history.parquet missing')
        return
    espn = _live_espn_team_codes()
    if not espn:
        add_row('data_health', 'collision_team_reachability', 'all', None,
                'SKIP', 'no pro_team values in roster history')
        return
    reachable = {team_key(c) for c in espn}

    unreachable, n_entries = [], 0
    for label, table in (('H', KNOWN_COLLISIONS), ('P', KNOWN_PITCHER_COLLISIONS)):
        for name, cands in table.items():
            for ct, _hint, mlbam in cands:
                n_entries += 1
                if team_key(ct) not in reachable:
                    unreachable.append(f'{label}:{name}/{ct}->{team_key(ct)}({mlbam})')

    rate = 1.0 - (len(unreachable) / n_entries) if n_entries else float('nan')
    status = 'PASS' if not unreachable else 'FAIL'
    note = (f'{n_entries - len(unreachable)}/{n_entries} collision team hints '
            f'reachable from {len(espn)} live ESPN codes')
    if unreachable:
        note += ' | DEAD: ' + '; '.join(unreachable[:6])
        note += ' — the resolver will fall through and may return the WRONG player'
    add_row('data_health', 'collision_team_reachability', 'all', rate, status, note)


def check_collision_smoke() -> None:
    """Canonical resolver cases, asserted. Pure table lookups — no data files.

    These are the exact inputs that have burned us. If any returns the wrong id,
    or a should-refuse case silently resolves, the gate is broken again.
    """
    from plv_clone.utils.name_match import resolve_batter_id, resolve_pitcher_id

    cases = [
        # (callable, kwargs, expected, why this case exists)
        ('Max Muncy Oak+3B', lambda: resolve_batter_id(
            'Max Muncy', team='Oak', position='3B'), 691777,
         'the 2026-07-29 bug: ESPN team spelling + a position hint that no '
         'longer separates the two Muncys'),
        ('Max Muncy ATH', lambda: resolve_batter_id(
            'Max Muncy', team='ATH'), 691777, 'statcast team spelling'),
        ('Max Muncy LAD', lambda: resolve_batter_id(
            'Max Muncy', team='LAD'), 571970, 'the established veteran'),
        ('Max Muncy hintless', lambda: resolve_batter_id('Max Muncy'), None,
         'must refuse to guess'),
        ('Max Muncy pos-only 3B', lambda: resolve_batter_id(
            'Max Muncy', position='3B'), None,
         'both Muncys list 3B now — ambiguous, must refuse'),
        ('Max Muncy wrong team', lambda: resolve_batter_id(
            'Max Muncy', team='NYY'), None,
         'a stale team hint must refuse, never fall through to position'),
        ('Luis Garcia Jr WSH', lambda: resolve_batter_id(
            'Luis Garcia Jr.', team='WSH'), 671277, 'unaccented suffix spelling'),
        ('Logan Allen SDP', lambda: resolve_pitcher_id(
            'Logan Allen', team='SDP'), 663531,
         'FanGraphs team spelling; role=SP matches BOTH Allens so a '
         'fall-through would return the CLE arm'),
        ('Logan Allen CLE', lambda: resolve_pitcher_id(
            'Logan Allen', team='CLE'), 671106, 'the current rotation arm'),
        ('Logan Allen role-only', lambda: resolve_pitcher_id(
            'Logan Allen', role='SP'), None, 'ambiguous, must refuse'),
        ('Eury Perez MIA', lambda: resolve_pitcher_id(
            'Eury Perez', team='MIA'), 691587, 'accent-drift resolution force'),
        ('Jose Soriano hintless', lambda: resolve_pitcher_id(
            'Jose Soriano'), 667755, 'single-candidate force resolves hintless'),
    ]
    failures = []
    for label, fn, expected, _why in cases:
        try:
            got = fn()
        except Exception as e:
            failures.append(f'{label}: raised {type(e).__name__}')
            continue
        if got != expected:
            failures.append(f'{label}: got {got}, want {expected}')

    status = 'PASS' if not failures else 'FAIL'
    note = f'{len(cases) - len(failures)}/{len(cases)} canonical resolver cases'
    if failures:
        note += ' | BROKEN: ' + '; '.join(failures[:5])
    add_row('data_health', 'collision_smoke', 'all',
            (len(cases) - len(failures)) / len(cases), status, note)


def check_fa_join_coverage() -> None:
    """% of the FA pool that joins to its projection CSV, vs a trailing baseline.

    A silent normalizer/schema drift shows up here before it shows up in a bad
    recommendation: the O'Hearn curly-apostrophe bug (2026-07-28) and the
    Muncy team drift both manifest as join coverage quietly falling. Joins on
    MLBAM id — the collision-safe key — so this measures DATA drift, not name
    matching. WARN at -5pp vs the trailing mean, FAIL at -15pp.
    """
    specs = [
        ('H', FA_SNAPSHOT_DIR / 'fa_pool_H_latest.parquet', RH3_CSV, 'batter'),
        ('SP', FA_SNAPSHOT_DIR / 'fa_pool_SP_latest.parquet', RP3_CSV, 'pitcher'),
        ('RP', FA_SNAPSHOT_DIR / 'fa_pool_RP_latest.parquet', RPRS2_CSV, 'pitcher'),
    ]
    hist = None
    if SCORECARD_HISTORY.exists():
        try:
            h = pd.read_csv(SCORECARD_HISTORY)
            hist = h[(h['metric'] == 'fa_join_coverage')]
        except Exception:
            hist = None

    for seg, snap_p, proj_p, id_col in specs:
        if not (snap_p.exists() and proj_p.exists()):
            add_row('data_health', 'fa_join_coverage', seg, None, 'SKIP',
                    f'missing {snap_p.name if not snap_p.exists() else proj_p.name}')
            continue
        snap = pd.read_parquet(snap_p, columns=['mlbam_id'])
        ids = pd.to_numeric(snap['mlbam_id'], errors='coerce').dropna().astype(int)
        if ids.empty:
            add_row('data_health', 'fa_join_coverage', seg, None, 'SKIP',
                    'no mlbam ids in snapshot')
            continue
        proj = pd.read_csv(proj_p, usecols=[id_col])
        pool = set(pd.to_numeric(proj[id_col], errors='coerce').dropna().astype(int))
        rate = float(ids.isin(pool).mean())

        base = float('nan')
        if hist is not None:
            prior = hist[(hist['segment'] == seg)]
            prior = prior[prior['date'] != TODAY.isoformat()]
            vals = pd.to_numeric(prior['value'], errors='coerce').dropna()
            if len(vals) >= 3:
                base = float(vals.tail(7).mean())
        if np.isfinite(base):
            delta = rate - base
            status = ('FAIL' if delta <= -0.15 else
                      'WARN' if delta <= -0.05 else 'PASS')
            note = (f'{int(ids.isin(pool).sum())}/{len(ids)} FA {seg} rows join '
                    f'{proj_p.name} by mlbam; {delta:+.3f} vs trailing mean '
                    f'{base:.3f} (WARN -0.05 / FAIL -0.15)')
        else:
            # No baseline yet — report the level, don't invent a threshold.
            status = 'FAIL' if rate < 0.40 else ('WARN' if rate < 0.70 else 'PASS')
            note = (f'{int(ids.isin(pool).sum())}/{len(ids)} FA {seg} rows join '
                    f'{proj_p.name} by mlbam; no trailing baseline yet '
                    f'(need 3+ prior days) — absolute floors 0.70/0.40 applied')
        add_row('data_health', 'fa_join_coverage', seg, rate, status, note)


def run_data_health() -> None:
    hist = None
    if HISTORY_PARQUET.exists():
        try:
            hist = pd.read_parquet(
                HISTORY_PARQUET,
                columns=['snapshot_date', 'player_type', 'proj_volume'])
            hist['snapshot_date'] = pd.to_datetime(hist['snapshot_date']).dt.date
        except Exception:
            hist = None
    _run_check('il_join_match_rate', check_il_join)
    _run_check('il_grid_coverage', check_il_grid_coverage)
    _run_check('il_tx_json_freshness', check_il_tx_json_freshness)
    _run_check('ros_opp_xwoba_nan_rate', check_ros_opp_xwoba)
    _run_check('ros_cache_split_day_lag', check_ros_cache_frozen)
    _run_check('statcast_max_date_lag_days', check_statcast_lag)
    _run_check('boxscore_lag_days', check_boxscore_lag)
    _run_check('fg_scrape_silent_fail', check_fg_snapshot_age)
    _run_check('fg_proj_cache_gaps', check_fg_proj_cache_gaps)
    _run_check('proj_rowcount_delta_7d',
               lambda: check_projection_rowcounts(hist))
    _run_check('proj_volume_fill_rate', lambda: check_proj_volume_fill(hist))
    # Drift sentinels (2026-07-29) — silent-rot detection for the name/id layer
    _run_check('collision_team_reachability', check_collision_team_reachability)
    _run_check('collision_smoke', check_collision_smoke)
    _run_check('fa_join_coverage', check_fa_join_coverage)


# =========================================================================
# SECTION 3 — PIPELINE STALENESS (freshness tripwires)
# =========================================================================

def _run_staleness_check(name: str, fn) -> None:
    """Fail-soft wrapper: an errored staleness check reports WARN (a check
    that cannot run is itself a mild staleness signal), never a crash."""
    try:
        fn()
    except Exception as e:
        add_row('pipeline_staleness', name, 'all', None, 'WARN',
                f'check errored: {type(e).__name__}: {e}')


def _mtime(p: Path) -> datetime:
    return datetime.fromtimestamp(os.path.getmtime(p))


def check_console_data_freshness() -> None:
    """The 2026-07-18 trap: models rebuilt but console_data.json not
    regenerated -> the decision console silently serves stale numbers.
    console_data.json mtime must be >= the newest of its model inputs."""
    if not CONSOLE_JSON.exists():
        add_row('pipeline_staleness', 'console_data_freshness', 'all', None,
                'SKIP', f'missing {CONSOLE_JSON.name}')
        return
    inputs = [RH3_CSV, RP3_CSV, RPRS2_CSV, BOX_H]
    present = [p for p in inputs if p.exists()]
    if not present:
        add_row('pipeline_staleness', 'console_data_freshness', 'all', None,
                'SKIP', 'no model-input files present to compare against')
        return
    newest = max(present, key=lambda p: os.path.getmtime(p))
    lag_h = (_mtime(newest) - _mtime(CONSOLE_JSON)).total_seconds() / 3600
    status = 'PASS' if lag_h <= 0 else 'WARN'
    add_row('pipeline_staleness', 'console_data_freshness', 'all',
            round(max(lag_h, 0.0), 1), status,
            f'console_data.json vs newest input {newest.name}; hours behind '
            '(>0 = stale decision console — the 2026-07-18 trap)')


def check_tri_nightly_freshness() -> None:
    """The triangulate nightly must have run within the last 26h; its
    _cards.json sidecar missing is WARN-only (first-night tolerance — the
    FA cards fall back to the flat batch)."""
    files = [Path(p) for p in
             glob.glob(str(TRI_NIGHTLY_DIR / 'triangulate_nightly_*.json'))
             if not p.endswith('_cards.json')]
    if not files:
        add_row('pipeline_staleness', 'tri_nightly_freshness', 'nightly_json',
                None, 'FAIL', 'no triangulate_nightly_*.json found at all')
        return
    freshest = max(files, key=lambda p: os.path.getmtime(p))
    age_h = (datetime.now() - _mtime(freshest)).total_seconds() / 3600
    status = 'PASS' if age_h < 26 else 'FAIL'
    add_row('pipeline_staleness', 'tri_nightly_freshness', 'nightly_json',
            round(age_h, 1), status,
            f'freshest {freshest.name}; age hours (>=26h = nightly not running)')
    cards = freshest.with_name(freshest.stem + '_cards.json')
    status = 'PASS' if cards.exists() else 'WARN'
    add_row('pipeline_staleness', 'tri_nightly_freshness', 'cards_sidecar',
            int(cards.exists()), status,
            f'{cards.name} ' + ('present' if cards.exists() else
            'missing (first-night tolerance; FA cards fall back to flat batch)'))


def check_publish_freshness() -> None:
    """Stuck-publish detector: each GitHub Pages artifact must not lag
    console_data.json by more than 26h (one missed daily publish)."""
    if not XFP_MODEL_DOCS.exists():
        add_row('pipeline_staleness', 'publish_freshness', 'all', None,
                'SKIP', 'xfp-model/docs absent (sibling repo not checked out '
                'on this machine) — publish check not applicable')
        return
    if not CONSOLE_JSON.exists():
        add_row('pipeline_staleness', 'publish_freshness', 'all', None,
                'SKIP', f'missing {CONSOLE_JSON.name} reference point')
        return
    ref = _mtime(CONSOLE_JSON)
    for page in ('index', 'matchup', 'triangulate', 'xfp_board'):
        p = XFP_MODEL_DOCS / f'{page}.html'
        if not p.exists():
            add_row('pipeline_staleness', 'publish_freshness', page, None,
                    'WARN', f'{p.name} missing from xfp-model/docs')
            continue
        lag_h = (ref - _mtime(p)).total_seconds() / 3600
        status = 'WARN' if lag_h > 26 else 'PASS'
        add_row('pipeline_staleness', 'publish_freshness', page,
                round(max(lag_h, 0.0), 1), status,
                'hours behind console_data.json (>26h = stuck publish)')


def check_espn_snapshot_ttl() -> None:
    """The intra-refresh ESPN snapshot should be consumed and cleared; a
    file lingering past 4x its TTL (env PLV_ESPN_SNAPSHOT_TTL_MIN, default
    240 min) means a refresh crashed mid-flight and left it behind."""
    try:
        ttl_min = float(os.environ.get('PLV_ESPN_SNAPSHOT_TTL_MIN', '240'))
    except ValueError:
        ttl_min = 240.0
    files = ([p for p in ESPN_SNAPSHOT_DIR.iterdir() if p.is_file()]
             if ESPN_SNAPSHOT_DIR.exists() else [])
    if not files:
        add_row('pipeline_staleness', 'espn_snapshot_ttl', 'all', 0, 'PASS',
                'no snapshot files present (snapshot only exists refresh-side)')
        return
    oldest = min(files, key=lambda p: os.path.getmtime(p))
    age_min = (datetime.now() - _mtime(oldest)).total_seconds() / 60
    status = 'WARN' if age_min > 4 * ttl_min else 'PASS'
    add_row('pipeline_staleness', 'espn_snapshot_ttl', 'all',
            round(age_min, 0), status,
            f'oldest {oldest.name} age minutes vs TTL {ttl_min:.0f}min '
            f'(WARN >{4 * ttl_min:.0f}min = stale snapshot lingering)')


def check_trajectory_endpoint() -> None:
    """The frozen-trajectory class (04-25 -> 06-20 style: archetype
    trajectory endpoints stuck weeks behind while the nightly kept
    publishing). Implementation (documented): the nightly CSV's
    `traj_last_label` column carries the trajectory ENDPOINT as MM-DD for
    weekly-cadence rows ('#N' start-index labels are skipped) — the max
    parsed endpoint must be within 3 days of the file's own date. Falls
    back to a `snapshot*` date column max vs file date if traj_last_label
    is absent."""
    files = [Path(p) for p in
             glob.glob(str(TRI_NIGHTLY_DIR / 'triangulate_nightly_*.json'))
             if not p.endswith('_cards.json')]
    if not files:
        add_row('pipeline_staleness', 'trajectory_endpoint', 'all', None,
                'SKIP', 'no triangulate nightly files to inspect')
        return
    freshest = max(files, key=lambda p: os.path.getmtime(p))
    csv_path = freshest.with_suffix('.csv')
    if not csv_path.exists():
        add_row('pipeline_staleness', 'trajectory_endpoint', 'all', None,
                'WARN', f'nightly CSV sibling {csv_path.name} missing')
        return
    # the file's own date: from the filename (triangulate_nightly_YYYY-MM-DD)
    try:
        file_date = date.fromisoformat(csv_path.stem[-10:])
    except ValueError:
        file_date = _mtime(csv_path).date()
    header = pd.read_csv(csv_path, nrows=0).columns
    traj_cols = [c for c in header if 'traj' in c and 'last' in c]
    date_col = next((c for c in traj_cols if c == 'traj_last_label'),
                    traj_cols[0] if traj_cols else None)
    endpoints: list[date] = []
    if date_col is not None:
        vals = pd.read_csv(csv_path, usecols=[date_col])[date_col].dropna()
        for v in vals.astype(str):
            if len(v) == 5 and v[2] == '-':  # MM-DD endpoint label
                try:
                    d = date(file_date.year, int(v[:2]), int(v[3:]))
                except ValueError:
                    continue
                if d > file_date + timedelta(days=7):  # year wrap
                    d = d.replace(year=file_date.year - 1)
                endpoints.append(d)
    src = f'{date_col} MM-DD endpoints'
    if not endpoints:  # fallback: a snapshot/date column
        snap_col = next((c for c in header if 'snapshot' in c.lower()), None)
        if snap_col is not None:
            vals = pd.to_datetime(
                pd.read_csv(csv_path, usecols=[snap_col])[snap_col],
                errors='coerce').dropna()
            endpoints = [d.date() for d in vals]
            src = f'{snap_col} column max'
    if not endpoints:
        add_row('pipeline_staleness', 'trajectory_endpoint', 'all', None,
                'WARN', 'no identifiable trajectory-endpoint / snapshot date '
                f'column in {csv_path.name}')
        return
    gap = (file_date - max(endpoints)).days
    status = 'PASS' if gap <= 3 else 'WARN'
    add_row('pipeline_staleness', 'trajectory_endpoint', 'all', gap, status,
            f'max endpoint {max(endpoints)} vs file date {file_date} via '
            f'{src} (gap >3d = frozen 04-25->06-20 trajectory class)')


def check_golden_stash_leftover() -> None:
    """A crashed /golden-run leaves model pkls stashed in
    data/models/.golden_stash/ — production would then run on the swapped-in
    goldens. Any subdir = FAIL until restored."""
    if not GOLDEN_STASH_DIR.exists():
        add_row('pipeline_staleness', 'golden_stash_leftover', 'all', 0,
                'PASS', 'no .golden_stash dir (nothing stashed)')
        return
    subdirs = sorted(p.name for p in GOLDEN_STASH_DIR.iterdir() if p.is_dir())
    if subdirs:
        add_row('pipeline_staleness', 'golden_stash_leftover', 'all',
                len(subdirs), 'FAIL',
                'crashed /golden-run left model pkls stashed '
                f'({", ".join(subdirs[:5])}) — run '
                '`python scripts/ci/golden_run.py --restore`')
    else:
        add_row('pipeline_staleness', 'golden_stash_leftover', 'all', 0,
                'PASS', '.golden_stash present but empty')


def run_pipeline_staleness() -> None:
    _run_staleness_check('console_data_freshness', check_console_data_freshness)
    _run_staleness_check('tri_nightly_freshness', check_tri_nightly_freshness)
    _run_staleness_check('publish_freshness', check_publish_freshness)
    _run_staleness_check('espn_snapshot_ttl', check_espn_snapshot_ttl)
    _run_staleness_check('trajectory_endpoint', check_trajectory_endpoint)
    _run_staleness_check('golden_stash_leftover', check_golden_stash_leftover)


# =========================================================================
# OUTPUT
# =========================================================================

def _render_md(df: pd.DataFrame) -> str:
    lines = [f'# Model scorecard — {TODAY.isoformat()}', '']
    health = df[df['section'] == 'data_health']
    stale = df[df['section'] == 'pipeline_staleness']
    n_fail = (health['status'] == 'FAIL').sum()
    n_warn = (health['status'] == 'WARN').sum()
    n_skip = (health['status'] == 'SKIP').sum()
    lines.append(f'**Data health:** {(health["status"] == "PASS").sum()} PASS'
                 f' / {n_warn} WARN / {n_fail} FAIL / {n_skip} SKIP')
    lines.append(f'**Pipeline staleness:** {(stale["status"] == "PASS").sum()} PASS'
                 f' / {(stale["status"] == "WARN").sum()} WARN'
                 f' / {(stale["status"] == "FAIL").sum()} FAIL'
                 f' / {(stale["status"] == "SKIP").sum()} SKIP')
    lines.append('')
    lines.append('## Data-health tripwires')
    lines.append('')
    lines.append('| check | segment | value | status | note |')
    lines.append('|---|---|---|---|---|')
    for _, r in health.iterrows():
        lines.append(f'| {r["metric"]} | {r["segment"]} | {r["value"]} '
                     f'| {r["status"]} | {r["note"]} |')
    lines.append('')
    lines.append('## Pipeline-staleness tripwires')
    lines.append('')
    lines.append('| check | segment | value | status | note |')
    lines.append('|---|---|---|---|---|')
    for _, r in stale.iterrows():
        lines.append(f'| {r["metric"]} | {r["segment"]} | {r["value"]} '
                     f'| {r["status"]} | {r["note"]} |')
    lines.append('')
    lines.append('## Forward accuracy')
    lines.append('')
    lines.append('Honest baseline (2026-06-26 forward retro): rh3 ~0.35 / '
                 'rp3 ~0.40 forward Spearman over 2-3 weeks. All metrics '
                 'conditional on forward-volume floors (survivorship).')
    lines.append('')
    fa = df[df['section'] == 'forward_accuracy']
    lines.append('| metric | segment | value | status | note |')
    lines.append('|---|---|---|---|---|')
    for _, r in fa.iterrows():
        lines.append(f'| {r["metric"]} | {r["segment"]} | {r["value"]} '
                     f'| {r["status"]} | {r["note"]} |')
    lines.append('')
    lines.append('_Generated by scripts/xfp/build_model_scorecard.py. '
                 'History accumulates in data/research/model_scorecard_history.csv._')
    return '\n'.join(lines) + '\n'


def main() -> int:
    print(f'=== model scorecard {TODAY.isoformat()} ===')
    run_forward_accuracy()
    run_data_health()
    run_pipeline_staleness()

    df = pd.DataFrame(ROWS, columns=['date', 'section', 'metric', 'segment',
                                     'value', 'status', 'note'])
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(SCORECARD_CSV, index=False)
    SCORECARD_MD.write_text(_render_md(df), encoding='utf-8')

    # dated history (idempotent: replace any same-day rows)
    if SCORECARD_HISTORY.exists():
        hist_df = pd.read_csv(SCORECARD_HISTORY)
        hist_df = hist_df[hist_df['date'] != TODAY.isoformat()]
        hist_df = pd.concat([hist_df, df], ignore_index=True)
    else:
        hist_df = df
    hist_df.to_csv(SCORECARD_HISTORY, index=False)

    # ---- console summary -------------------------------------------------
    health = df[df['section'] == 'data_health']
    stale = df[df['section'] == 'pipeline_staleness']
    fa = df[df['section'] == 'forward_accuracy']
    print('\n--- DATA HEALTH ---')
    for _, r in health.iterrows():
        print(f'  [{r["status"]:^6}] {r["metric"]} ({r["segment"]}): '
              f'{r["value"]}  {r["note"]}')
    print('\n--- PIPELINE STALENESS ---')
    for _, r in stale.iterrows():
        print(f'  [{r["status"]:^6}] {r["metric"]} ({r["segment"]}): '
              f'{r["value"]}  {r["note"]}')
    print('\n--- FORWARD ACCURACY (headline: spearman_rate, all) ---')
    head = fa[fa['metric'].str.contains('spearman|vs_prior_delta|edge_vs_naive')
              & (fa['segment'].isin(['all', 'model']))]
    for _, r in head.iterrows():
        print(f'  [{r["status"]:^12}] {r["metric"]}: {r["value"]}  ({r["note"]})')
    trip = pd.concat([health, stale])
    n_fail = (trip['status'] == 'FAIL').sum()
    n_warn = (trip['status'] == 'WARN').sum()
    print(f'\nSummary: {n_fail} FAIL, {n_warn} WARN tripwires '
          f'(data health + pipeline staleness). '
          f'{len(df)} rows -> {SCORECARD_CSV.name} / {SCORECARD_MD.name}; '
          f'history {len(hist_df)} rows.')
    return 1 if n_fail else 0


if __name__ == '__main__':
    sys.exit(main())

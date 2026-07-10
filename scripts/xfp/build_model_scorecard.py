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
IL_CSV = CACHE / 'il_split_features_2018_2026.csv'
ROS_SCHED_CSV = CACHE / 'ros_schedule_features_2018_2026.csv'
FG_ASOF_DIR = RESEARCH / 'fg_asof'
FG_PROJ_CACHE_DIR = RESEARCH / 'fg_proj_cache'
RH3_CSV = OUT / 'xfp_rh3_projections.csv'

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
    """FG 2026 'current' snapshot age via file mtime. Stale >5d = WARN."""
    pats = sorted(glob.glob(str(FG_ASOF_DIR / 'fg_*_2026_current.csv')))
    if not pats:
        add_row('data_health', 'fg_2026_snapshot_age_days', 'all', None,
                'SKIP', 'no fg_*_2026_current.csv found in fg_asof')
        return
    for p in pats:
        age = (datetime.now() - datetime.fromtimestamp(os.path.getmtime(p))).days
        status = 'FAIL' if age > 10 else ('WARN' if age > 5 else 'PASS')
        add_row('data_health', 'fg_2026_snapshot_age_days', Path(p).name,
                age, status, 'mtime-based')


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
    _run_check('ros_opp_xwoba_nan_rate', check_ros_opp_xwoba)
    _run_check('ros_cache_split_day_lag', check_ros_cache_frozen)
    _run_check('statcast_max_date_lag_days', check_statcast_lag)
    _run_check('boxscore_lag_days', check_boxscore_lag)
    _run_check('fg_2026_snapshot_age_days', check_fg_snapshot_age)
    _run_check('fg_proj_cache_gaps', check_fg_proj_cache_gaps)
    _run_check('proj_rowcount_delta_7d',
               lambda: check_projection_rowcounts(hist))
    _run_check('proj_volume_fill_rate', lambda: check_proj_volume_fill(hist))


# =========================================================================
# OUTPUT
# =========================================================================

def _render_md(df: pd.DataFrame) -> str:
    lines = [f'# Model scorecard — {TODAY.isoformat()}', '']
    health = df[df['section'] == 'data_health']
    n_fail = (health['status'] == 'FAIL').sum()
    n_warn = (health['status'] == 'WARN').sum()
    n_skip = (health['status'] == 'SKIP').sum()
    lines.append(f'**Data health:** {(health["status"] == "PASS").sum()} PASS'
                 f' / {n_warn} WARN / {n_fail} FAIL / {n_skip} SKIP')
    lines.append('')
    lines.append('## Data-health tripwires')
    lines.append('')
    lines.append('| check | segment | value | status | note |')
    lines.append('|---|---|---|---|---|')
    for _, r in health.iterrows():
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
    fa = df[df['section'] == 'forward_accuracy']
    print('\n--- DATA HEALTH ---')
    for _, r in health.iterrows():
        print(f'  [{r["status"]:^6}] {r["metric"]} ({r["segment"]}): '
              f'{r["value"]}  {r["note"]}')
    print('\n--- FORWARD ACCURACY (headline: spearman_rate, all) ---')
    head = fa[fa['metric'].str.contains('spearman|vs_prior_delta|edge_vs_naive')
              & (fa['segment'].isin(['all', 'model']))]
    for _, r in head.iterrows():
        print(f'  [{r["status"]:^12}] {r["metric"]}: {r["value"]}  ({r["note"]})')
    n_fail = (health['status'] == 'FAIL').sum()
    n_warn = (health['status'] == 'WARN').sum()
    print(f'\nSummary: {n_fail} FAIL, {n_warn} WARN tripwires. '
          f'{len(df)} rows -> {SCORECARD_CSV.name} / {SCORECARD_MD.name}; '
          f'history {len(hist_df)} rows.')
    return 1 if n_fail else 0


if __name__ == '__main__':
    sys.exit(main())

"""build_player_projection_history.py — append today's per-player projection snapshot to a growing panel.

Mirrors the pattern in build_boom_stack_history_panel.py: idempotent, atomic,
schema-stable.

Why: predictions_history.csv is matchup-level only. The opponent-action
predictor needs per-player Δ-rank tracking — "did Late Night add player X
right after player X's rh3 jumped 30 ranks?" can't be answered without a
per-player daily panel.

Inputs (current state):
  data/outputs/xfp_rh3_projections.csv
  data/outputs/xfp_rp3_projections.csv
  data/outputs/xfp_rprs2_projections.csv

Output:
  data/research/player_projection_history.parquet

Schema (stable):
  snapshot_date         date  (today)
  player_type           str   ('H' | 'SP' | 'RP')
  mlbam_id              int64 (batter / pitcher column)
  player_name           str
  rank                  int
  proj_per              float (xfp_rh3_per_pa | xfp_rp3_per_start | xfp_ros)
  prior_per             float (prior_fp_per_pa | prior_fp_per_start | null for rprs2)
  recency_form_gap      float
  replacement_delta     float
  signal                str
  position              str   (hitter primary_position from rh3; null for SP/RP)
                              [added 2026-07-09 for forward-error attribution]
  data_quality_tag      str   (SP only, from rp3: marcel_il vs data_driven_*;
                              null for H/RP) [added 2026-07-09]
  proj_volume           float (reserved — NaN until a volume model ships;
                              column exists now so the schema stays stable)
                              [added 2026-07-09]

Lens columns [added 2026-07-11, workstream A2 — forward-log the lenses that
CANNOT be reconstructed as-of later, so a common-basis forward-Spearman table
becomes computable in ~4-6 weeks]. Sourcing rule: OFFLINE ONLY — every value
comes from an artifact an earlier refresh step already wrote (PL cache 2.85,
archetype panels 2.6/2.7/2.8, boom pools 3.85/4.45, batter_rolling 1b,
injury cache 4.05). Zero live HTTP here. Each source carries an *_asof stamp
so forward analysis never pretends freshness. All fail-soft: a missing
artifact leaves NaN, never crashes the append.

  pl_rank               float (PL Top-150/100/Closers rank; NaN = unranked
                              or cache missing)
  pl_asof               str   (PL cache fetched date)
  arche_overall         float (archetype OVERALL 20-80, current-year row)
  arche_traj            str   (traj_flag)
  arche_cell            str   (3-letter cell)
  boom_stack            float (SP: full-pool 4.45; H: daily slate 3.85 —
                              H is SPARSE by design, only today's scheduled
                              hitters have a value; that IS the as-of truth)
  boom_asof             str   (source JSON date)
  xwoba_l21d            float (H only: xwoba_on_contact_l21d from
                              batter_rolling_features — the CLAUDE.md #8
                              drop-check diagnostic, not reconstructable
                              later because the cache holds one current row)
  espn_status           str   (IL flag, injured-rostered subset only)
  espn_return_date      str   (ESPN ESTIMATED return date — the E1.5b
                              estimate log; calibrate vs actual activations
                              once ~6-8 wks accrue)
  espn_injury_type      str
  injury_asof           str   (injury cache fetched date)

Deliberately NOT logged (pre-registered exclusions, plan 2026-07-11):
ownership%% (needs a live ESPN pull — violates the offline rule) and
sustainability verdict (no refresh artifact carries it; the 4.72b snapshot
CSV was checked and has no sustainability column — do not bolt a live
engine call on here to get one).

Backward compatibility: rows appended before a schema bump lack the newer
columns; pd.concat aligns on the union schema so old rows read back with
NaN there — a full-parquet read stays valid across schema bumps.

Idempotent on (snapshot_date, player_type, mlbam_id) — re-running on the same
day with the same source is a no-op.
"""
from __future__ import annotations

import glob as _glob
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from plv_clone.paths import ROOT
OUT = ROOT / 'data' / 'outputs'
RESEARCH = ROOT / 'data' / 'research'
PANEL = RESEARCH / 'player_projection_history.parquet'

TODAY = date.today().isoformat()


def _load_one(csv_name: str, player_type: str) -> pd.DataFrame:
    df = pd.read_csv(OUT / csv_name)
    id_col = 'batter' if player_type == 'H' else 'pitcher'
    proj_col = {
        'H': 'xfp_rh3_per_pa',
        'SP': 'xfp_rp3_per_start',
        'RP': 'xfp_ros',
    }[player_type]
    prior_col = {
        'H': 'prior_fp_per_pa',
        'SP': 'prior_fp_per_start',
        'RP': None,
    }[player_type]
    name_col = 'player_name' if 'player_name' in df.columns else 'name_api'
    # position: hitter primary position only (rh3 column); null for SP/RP
    position = df.get('primary_position') if player_type == 'H' else pd.NA
    # data_quality_tag: SP only (rp3 column: marcel_il vs data_driven_*)
    dq_tag = df.get('data_quality_tag') if player_type == 'SP' else pd.NA
    out = pd.DataFrame({
        'snapshot_date': TODAY,
        'player_type': player_type,
        'mlbam_id': df[id_col],
        'player_name': df[name_col],
        'rank': df['rank'],
        'proj_per': df[proj_col],
        'prior_per': df[prior_col] if prior_col else pd.NA,
        'recency_form_gap': df.get('recency_form_gap'),
        'replacement_delta': df.get('replacement_delta'),
        'signal': df.get('signal'),
        'position': position,
        'data_quality_tag': dq_tag,
        'proj_volume': float('nan'),
    })
    out = _attach_proj_volume(out, player_type)
    return out


# Volume-model outputs (validated 2026-07-09: hitter PASS +0.074 Spearman vs
# naive pace; SP PASS +0.100 — see hitter/sp_volume_model_2026-07-09.md;
# RP PASS +0.127 2026-07-10 — see rp_volume_model_2026-07-10.md).
# Units: H = proj RoS PA per team game; SP = proj RoS GS per team game;
# RP = proj RoS relief appearances (G) per team game.
_VOLUME_SOURCES = {
    'H': ('xfp_volume_projections.csv', 'proj_ros_pa_per_teamgame'),
    'SP': ('xfp_sp_volume_projections.csv', 'proj_ros_gs_per_teamgame'),
    'RP': ('xfp_rp_volume_projections.csv', 'proj_ros_g_per_teamgame'),
}


def _attach_proj_volume(out: pd.DataFrame, player_type: str) -> pd.DataFrame:
    src = _VOLUME_SOURCES.get(player_type)
    if src is None:
        return out
    csv_name, vol_col = src
    path = OUT / csv_name
    if not path.exists():
        print(f'  ! proj_volume: {csv_name} not found — {player_type} stays NaN')
        return out
    vol = pd.read_csv(path)[['mlbam_id', vol_col]].dropna()
    vol_map = dict(zip(vol['mlbam_id'].astype(int), vol[vol_col].astype(float)))
    out['proj_volume'] = out['mlbam_id'].map(vol_map)
    n = out['proj_volume'].notna().sum()
    print(f'  proj_volume ({player_type}): {n}/{len(out)} rows filled from {csv_name}')
    return out


# ---------------------------------------------------------------------------
# Lens enrichment (A2, 2026-07-11) — offline artifact joins, each fail-soft.
# ---------------------------------------------------------------------------

_ARCHE_PANELS = {
    'SP': (RESEARCH / 'sp_archetype_career_panel.parquet', 'pitcher'),
    'H': (RESEARCH / 'hitter_archetype_career_panel.parquet', 'batter'),
    'RP': (RESEARCH / 'rp_archetype_career_panel.parquet', 'pitcher'),
}

_BOOM_SOURCES = {
    'SP': ('sp_boom_stack_full_pool_*.json', 'pitcher_id'),
    'H': ('hitter_boom_stack_*.json', 'batter_id'),
}

_CUR_YEAR = int(TODAY[:4])


def _note(msg: str) -> None:
    print(f'  {msg}')


def _attach_pl_rank(out: pd.DataFrame, player_type: str) -> pd.DataFrame:
    try:
        try:
            from scripts.xfp.lib.pl_cache import pl_rank
        except ImportError:
            from lib.pl_cache import pl_rank
        ranks, dates = [], []
        for name in out['player_name']:
            rk, dt = pl_rank(str(name), player_type)
            ranks.append(float(rk) if isinstance(rk, (int, float)) else float('nan'))
            dates.append(dt)
        out['pl_rank'] = ranks
        out['pl_asof'] = dates
        n = out['pl_rank'].notna().sum()
        _note(f'pl_rank ({player_type}): {n}/{len(out)} ranked')
    except Exception as e:
        _note(f'! pl_rank ({player_type}) skipped: {type(e).__name__}: {e}')
    return out


def _attach_archetype(out: pd.DataFrame, player_type: str) -> pd.DataFrame:
    path, id_col = _ARCHE_PANELS[player_type]
    try:
        panel = pd.read_parquet(
            path, columns=[id_col, 'year', 'OVERALL', 'traj_flag', 'cell'])
        cur = panel[panel['year'] == _CUR_YEAR].drop_duplicates(id_col, keep='last')
        cur = cur.set_index(cur[id_col].astype(int))
        ids = out['mlbam_id'].astype(int)
        out['arche_overall'] = ids.map(cur['OVERALL'])
        out['arche_traj'] = ids.map(cur['traj_flag'])
        out['arche_cell'] = ids.map(cur['cell'])
        _note(f'archetype ({player_type}): {out["arche_overall"].notna().sum()}'
              f'/{len(out)} matched from {path.name}')
    except Exception as e:
        _note(f'! archetype ({player_type}) skipped: {type(e).__name__}: {e}')
    return out


def _attach_boom(out: pd.DataFrame, player_type: str) -> pd.DataFrame:
    src = _BOOM_SOURCES.get(player_type)
    if src is None:
        return out
    pattern, id_key = src
    try:
        files = sorted(_glob.glob(str(OUT / pattern)))
        if not files:
            _note(f'! boom_stack ({player_type}): no {pattern} files')
            return out
        latest = files[-1]  # dated filenames sort chronologically
        asof = Path(latest).stem.rsplit('_', 1)[-1]
        cands = json.loads(Path(latest).read_text(encoding='utf-8')).get('candidates', [])
        boom_map = {int(c[id_key]): c.get('boom_stack')
                    for c in cands if c.get(id_key) is not None}
        out['boom_stack'] = out['mlbam_id'].astype(int).map(boom_map)
        out['boom_asof'] = asof
        _note(f'boom_stack ({player_type}): {out["boom_stack"].notna().sum()}'
              f'/{len(out)} from {Path(latest).name}'
              + (' [sparse by design: daily slate only]' if player_type == 'H' else ''))
    except Exception as e:
        _note(f'! boom_stack ({player_type}) skipped: {type(e).__name__}: {e}')
    return out


def _attach_xwoba_l21d(out: pd.DataFrame, player_type: str) -> pd.DataFrame:
    if player_type != 'H':
        return out
    try:
        brf = pd.read_csv(RESEARCH / 'xfp_cache' / 'batter_rolling_features.csv',
                          usecols=['batter', 'xwoba_on_contact_l21d'])
        m = dict(zip(brf['batter'].astype(int), brf['xwoba_on_contact_l21d']))
        out['xwoba_l21d'] = out['mlbam_id'].astype(int).map(m)
        _note(f'xwoba_l21d (H): {out["xwoba_l21d"].notna().sum()}/{len(out)}')
    except Exception as e:
        _note(f'! xwoba_l21d skipped: {type(e).__name__}: {e}')
    return out


def _attach_injury(out: pd.DataFrame) -> pd.DataFrame:
    try:
        try:
            from scripts.xfp.lib.injury_status import load_injury_details
        except ImportError:
            from lib.injury_status import load_injury_details
        try:
            from plv_clone.utils.name_match import _normalize
        except ImportError:
            _normalize = str.lower
        details, fetched = load_injury_details()
        if not details:
            _note('injury details: cache empty or pre-details schema — NaN')
            return out
        keys = out['player_name'].map(lambda n: _normalize(str(n)))
        out['espn_status'] = keys.map(lambda k: (details.get(k) or {}).get('status'))
        out['espn_return_date'] = keys.map(lambda k: (details.get(k) or {}).get('return_date'))
        out['espn_injury_type'] = keys.map(lambda k: (details.get(k) or {}).get('injury_type'))
        out['injury_asof'] = fetched
        _note(f'injury details: {out["espn_status"].notna().sum()}/{len(out)} '
              f'flagged (injured-rostered subset only, asof {fetched})')
    except Exception as e:
        _note(f'! injury details skipped: {type(e).__name__}: {e}')
    return out


def _enrich_lenses(out: pd.DataFrame, player_type: str) -> pd.DataFrame:
    out = _attach_pl_rank(out, player_type)
    out = _attach_archetype(out, player_type)
    out = _attach_boom(out, player_type)
    out = _attach_xwoba_l21d(out, player_type)
    return out


def main() -> int:
    print('=== player projection history append ===')
    parts = []
    for csv_name, ptype in [
        ('xfp_rh3_projections.csv', 'H'),
        ('xfp_rp3_projections.csv', 'SP'),
        ('xfp_rprs2_projections.csv', 'RP'),
    ]:
        try:
            parts.append(_enrich_lenses(_load_one(csv_name, ptype), ptype))
        except FileNotFoundError:
            print(f'  ! skip {csv_name} (not found)')
            continue
    new = pd.concat(parts, ignore_index=True)
    new = _attach_injury(new)
    print(f'  today {TODAY}: {len(new)} rows assembled (H={(new.player_type=="H").sum()}  SP={(new.player_type=="SP").sum()}  RP={(new.player_type=="RP").sum()})')

    if PANEL.exists():
        existing = pd.read_parquet(PANEL)
        have_key = set(zip(existing['snapshot_date'].astype(str),
                           existing['player_type'].astype(str),
                           existing['mlbam_id'].astype(str)))
        new_key = list(zip(new['snapshot_date'].astype(str),
                           new['player_type'].astype(str),
                           new['mlbam_id'].astype(str)))
        mask = [k not in have_key for k in new_key]
        to_add = new[mask]
        if to_add.empty:
            print(f'  panel already has today; no-op. existing rows: {len(existing)}')
            return 0
        combined = pd.concat([existing, to_add], ignore_index=True)
    else:
        combined = new

    PANEL.parent.mkdir(parents=True, exist_ok=True)
    tmp = PANEL.with_suffix('.parquet.tmp')
    combined.to_parquet(tmp, index=False)
    tmp.replace(PANEL)
    print(f'  wrote {PANEL.name} ({len(combined)} total rows)')
    return 0


if __name__ == '__main__':
    sys.exit(main())

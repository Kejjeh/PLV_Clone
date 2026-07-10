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

Backward compatibility: rows appended before 2026-07-09 lack the three new
columns; pd.concat aligns on the union schema so old rows read back with
NaN there — a full-parquet read stays valid across the schema bump.

Idempotent on (snapshot_date, player_type, mlbam_id) — re-running on the same
day with the same source is a no-op.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

from plv_clone.paths import ROOT
OUT = ROOT / 'data' / 'outputs'
PANEL = ROOT / 'data' / 'research' / 'player_projection_history.parquet'

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
# naive pace; SP PASS +0.100 — see hitter/sp_volume_model_2026-07-09.md).
# Units: H = proj RoS PA per team game; SP = proj RoS GS per team game.
# RP has no volume model yet — stays NaN.
_VOLUME_SOURCES = {
    'H': ('xfp_volume_projections.csv', 'proj_ros_pa_per_teamgame'),
    'SP': ('xfp_sp_volume_projections.csv', 'proj_ros_gs_per_teamgame'),
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


def main() -> int:
    print('=== player projection history append ===')
    parts = []
    for csv_name, ptype in [
        ('xfp_rh3_projections.csv', 'H'),
        ('xfp_rp3_projections.csv', 'SP'),
        ('xfp_rprs2_projections.csv', 'RP'),
    ]:
        try:
            parts.append(_load_one(csv_name, ptype))
        except FileNotFoundError:
            print(f'  ! skip {csv_name} (not found)')
            continue
    new = pd.concat(parts, ignore_index=True)
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

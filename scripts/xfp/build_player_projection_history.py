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

Idempotent on (snapshot_date, player_type, mlbam_id) — re-running on the same
day with the same source is a no-op.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
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
    })
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

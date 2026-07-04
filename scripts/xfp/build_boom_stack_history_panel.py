"""build_boom_stack_history_panel.py — append daily boom_stack snapshots to a growing panel.

Aggregates the existing date-stamped daily outputs:
  - data/outputs/sp_boom_stack_full_pool_<YYYY-MM-DD>.json
  - data/outputs/hitter_boom_stack_<YYYY-MM-DD>.json

into a single growing Parquet at:
  data/research/boom_stack_history_panel.parquet

Purpose: archive boom_stack and its components per-player per-day so that in
~12-16 weeks we have enough panel data to test whether boom_stack predicts
residual team scoring (see boom_stack_residual_test.md). The live builders
read statcast/team_strength/lineups at compute time, none of which are
recoverable for prior days, so we must snapshot forward.

Idempotent: only appends records for snapshot_dates not already in the panel.
Atomic: writes to a temp file then renames.

Schema (stable):
  snapshot_date           date  (from filename)
  player_type             str   ('SP' or 'H')
  mlbam_id                int64
  player_name             str
  team                    str
  opp_team                str
  is_home                 bool
  game_date               str   (nullable)
  boom_stack              int
  boom_components_json    str   (json blob — the boom_components dict)
  boom_detail_summary_json str  (json blob — full detail)
  boom_rate_expected      float
  bust_rate_expected      float
  boom_mean_fp_expected   float
  tier                    str   (SP-only; null for H)
  matchup_tier            str
  rp3_or_rh3_per          float
  signal                  str
  data_quality_tag        str
  anti_predictive         bool  (SP skill_spike_anti_predictive)
  high_k_arm              bool  (SP season_only_tags.high_k_pitcher.is_high_k)
  framing_quintile        int   (SP season_only_tags.catcher_framing.framing_quintile)
  il_return_flag          bool  (SP season_only_tags.il_return.is_first_back_long_il)
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from plv_clone.paths import ROOT
OUT_DIR = ROOT / 'data' / 'outputs'
PANEL = ROOT / 'data' / 'research' / 'boom_stack_history_panel.parquet'

SP_GLOB = 'sp_boom_stack_full_pool_*.json'
H_GLOB = 'hitter_boom_stack_*.json'

DATE_RE = re.compile(r'(\d{4}-\d{2}-\d{2})\.json$')


def _date_from_name(p: Path) -> str | None:
    m = DATE_RE.search(p.name)
    return m.group(1) if m else None


def _safe_get(d, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur if cur is not None else default


def _extract_sp(rec: dict, snapshot_date: str) -> dict:
    season = rec.get('season_only_tags') or {}
    return {
        'snapshot_date': snapshot_date,
        'player_type': 'SP',
        'mlbam_id': rec.get('pitcher_id'),
        'player_name': rec.get('pitcher_name'),
        'team': rec.get('team'),
        'opp_team': rec.get('opp_team'),
        'is_home': rec.get('is_home'),
        'game_date': rec.get('game_date'),
        'boom_stack': rec.get('boom_stack'),
        'boom_components_json': json.dumps(rec.get('boom_components') or {}, default=str),
        'boom_detail_summary_json': json.dumps(rec.get('boom_detail_summary') or {}, default=str),
        'boom_rate_expected': rec.get('boom_rate_expected'),
        'bust_rate_expected': rec.get('boom_bust_rate_expected'),
        'boom_mean_fp_expected': rec.get('boom_mean_fp_expected'),
        'tier': rec.get('tier'),
        'matchup_tier': rec.get('matchup_tier'),
        'rp3_or_rh3_per': rec.get('rp3_per_start'),
        'signal': rec.get('rp3_signal'),
        'data_quality_tag': rec.get('data_quality_tag'),
        'anti_predictive': rec.get('skill_spike_anti_predictive'),
        'high_k_arm': _safe_get(season, 'high_k_pitcher', 'is_high_k'),
        'framing_quintile': _safe_get(season, 'catcher_framing', 'framing_quintile'),
        'il_return_flag': _safe_get(season, 'il_return', 'is_first_back_long_il'),
    }


def _extract_h(rec: dict, snapshot_date: str) -> dict:
    return {
        'snapshot_date': snapshot_date,
        'player_type': 'H',
        'mlbam_id': rec.get('batter_id'),
        'player_name': rec.get('player_name'),
        'team': rec.get('team'),
        'opp_team': rec.get('opp_team'),
        'is_home': rec.get('is_home'),
        'game_date': rec.get('game_date'),
        'boom_stack': rec.get('boom_stack'),
        'boom_components_json': json.dumps(rec.get('boom_components') or {}, default=str),
        'boom_detail_summary_json': json.dumps(rec.get('boom_detail_summary') or {}, default=str),
        'boom_rate_expected': rec.get('boom_rate_expected'),
        'bust_rate_expected': rec.get('bust_rate_expected'),
        'boom_mean_fp_expected': rec.get('boom_mean_fp_expected'),
        'tier': None,
        'matchup_tier': rec.get('matchup_tier'),
        'rp3_or_rh3_per': rec.get('rh3_per_game'),
        'signal': rec.get('rh3_signal'),
        'data_quality_tag': None,
        'anti_predictive': None,
        'high_k_arm': None,
        'framing_quintile': None,
        'il_return_flag': None,
    }


def _load_existing() -> tuple[pd.DataFrame, set[tuple[str, str]]]:
    if not PANEL.exists():
        return pd.DataFrame(), set()
    df = pd.read_parquet(PANEL)
    keys = set(zip(df['snapshot_date'].astype(str), df['player_type'].astype(str)))
    return df, keys


def _atomic_write(df: pd.DataFrame) -> None:
    PANEL.parent.mkdir(parents=True, exist_ok=True)
    tmp = PANEL.with_suffix('.parquet.tmp')
    df.to_parquet(tmp, index=False)
    tmp.replace(PANEL)


def main():
    existing, have_keys = _load_existing()
    new_rows: list[dict] = []
    new_files = 0

    for pattern, extractor, ptype in [
        (SP_GLOB, _extract_sp, 'SP'),
        (H_GLOB, _extract_h, 'H'),
    ]:
        for fp in sorted(OUT_DIR.glob(pattern)):
            d = _date_from_name(fp)
            if not d:
                continue
            if (d, ptype) in have_keys:
                continue
            try:
                payload = json.loads(fp.read_text(encoding='utf-8'))
            except Exception as e:
                print(f'  ! skip {fp.name}: {e}')
                continue
            cands = payload.get('candidates') or []
            for rec in cands:
                try:
                    new_rows.append(extractor(rec, d))
                except Exception as e:
                    print(f'  ! row error in {fp.name}: {e}')
            new_files += 1

    if not new_rows:
        n_total = len(existing)
        if n_total:
            dr = f"{existing['snapshot_date'].min()}..{existing['snapshot_date'].max()}"
        else:
            dr = 'empty'
        print(f'Appended 0 records from 0 new snapshot files; panel now contains {n_total} total records covering {dr}')
        return

    new_df = pd.DataFrame(new_rows)
    if not existing.empty:
        # Align columns — handle gracefully if schema evolves.
        for c in new_df.columns:
            if c not in existing.columns:
                existing[c] = None
        for c in existing.columns:
            if c not in new_df.columns:
                new_df[c] = None
        combined = pd.concat([existing, new_df[existing.columns]], ignore_index=True)
    else:
        combined = new_df

    _atomic_write(combined)
    dr = f"{combined['snapshot_date'].min()}..{combined['snapshot_date'].max()}"
    print(f'Appended {len(new_rows)} records from {new_files} new snapshot files; '
          f'panel now contains {len(combined)} total records covering {dr}')


if __name__ == '__main__':
    main()

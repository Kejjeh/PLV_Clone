"""Append sustainability calls to data/research/sustainability_history.csv.

Called silently by pitcher_sustainability and hitter_sustainability tools
on every run. One row per per-player classification. The companion script
validate_sustainability.py backfills actual outcomes 4-8 weeks later.
"""
from __future__ import annotations
import csv
from datetime import datetime
from pathlib import Path

ROOT = Path('c:/Users/Joshua/plv_clone')
HISTORY = ROOT / 'data' / 'research' / 'sustainability_history.csv'

SCHEMA = [
    'timestamp', 'call_date', 'scope',
    'player_id', 'player_name', 'kind',
    'bucket', 'signal', 'model_at_call', 'sus_ev_at_call',
    'skill_attributable', 'luck_attributable', 'staleness_score',
    'n_2026',
    'actual_fp_per_unit_4wk_post', 'actual_fp_per_unit_8wk_post',
    'backfill_date_4wk', 'backfill_date_8wk',
]


def _ensure_header():
    if not HISTORY.exists() or HISTORY.stat().st_size == 0:
        HISTORY.parent.mkdir(parents=True, exist_ok=True)
        with HISTORY.open('w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(SCHEMA)


def log_call(*, scope: str, player_id, player_name: str, kind: str,
             bucket: str, signal: str, model_at_call,
             sus_ev_at_call, skill_attributable, luck_attributable,
             staleness_score, n_2026):
    """Append one row. All fields except player_id may be None (written as '')."""
    _ensure_header()
    row = {
        'timestamp': datetime.now().isoformat(timespec='seconds'),
        'call_date': datetime.now().strftime('%Y-%m-%d'),
        'scope': scope,
        'player_id': player_id if player_id else '',
        'player_name': player_name,
        'kind': kind,
        'bucket': bucket or '',
        'signal': signal or '',
        'model_at_call': f'{model_at_call:.4f}' if model_at_call is not None else '',
        'sus_ev_at_call': f'{sus_ev_at_call:.4f}' if sus_ev_at_call is not None else '',
        'skill_attributable': f'{skill_attributable:.4f}' if skill_attributable is not None else '',
        'luck_attributable': f'{luck_attributable:.4f}' if luck_attributable is not None else '',
        'staleness_score': f'{staleness_score:.4f}' if staleness_score is not None else '',
        'n_2026': n_2026 if n_2026 is not None else '',
        'actual_fp_per_unit_4wk_post': '',
        'actual_fp_per_unit_8wk_post': '',
        'backfill_date_4wk': '',
        'backfill_date_8wk': '',
    }
    with HISTORY.open('a', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow([row[c] for c in SCHEMA])

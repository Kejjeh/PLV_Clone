"""Retention prune for dated snapshot families in data/outputs (issue #44).

These families are already gitignored ("consumers only read the LATEST"),
but they accumulated to 261 MB on disk and every sorted(glob(...))[-1]
consumer walks the whole directory. Deleting old dated copies is
behavior-preserving; the undated/_latest pointers are never touched.

fa_snapshots is deliberately NOT pruned here — run_positional_board.py has
a dated-file glob fallback into that tree.
"""
from datetime import date, timedelta
from pathlib import Path
import re

# Dated families safe to prune: <stem>_YYYY-MM-DD*.<ext>
SNAPSHOT_FAMILIES = (
    'closer_leaders_2*',
    'sp_boom_stack_full_pool_2*',
    'stream_the_stack_2*',
    'live_blend_xfp_2*',
    'hitter_boom_stack_2*',
    'streamer_decision_2*',
    'sp_rp_stuff_windows_2*',
    'xwoba_l225_2*',
)

_DATE_RE = re.compile(r'(\d{4}-\d{2}-\d{2})')

KEEP_DAYS = 30


def prune_dated_snapshots(out_dir, keep_days: int = KEEP_DAYS,
                          today: date | None = None) -> list:
    """Delete dated snapshot files older than keep_days. Returns deleted paths.
    A file whose name carries no parseable date is never touched."""
    out_dir = Path(out_dir)
    today = today or date.today()
    cutoff = (today - timedelta(days=keep_days)).isoformat()
    deleted = []
    for pat in SNAPSHOT_FAMILIES:
        for f in out_dir.glob(pat):
            m = _DATE_RE.search(f.name)
            if not m or 'latest' in f.name:
                continue
            if m.group(1) < cutoff:
                try:
                    f.unlink()
                    deleted.append(f)
                except OSError:
                    pass
    return deleted

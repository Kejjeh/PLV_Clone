"""Issue #33 — the stuff board must rank on FB velo, gated on FB sample."""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'scripts' / 'xfp') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

import build_sp_rp_stuff_windows as bw


def test_fb_fullness_gate_exists_and_has_threshold():
    assert bw.FB_VELO_MIN_N >= 30


def test_sort_key_is_fb_velo():
    """All-pitch velo mis-ranks mix-heavy arms (Detmers 88.7 all-pitch vs
    94.0 FB), so the board order must key on the FB column."""
    src = (ROOT / 'scripts' / 'xfp' / 'build_sp_rp_stuff_windows.py').read_text(encoding='utf-8')
    assert 'sort_values(["role", "fb_velo_window", "velo_window"]' in src


def test_shipped_board_gates_fb_sample():
    df = pd.read_csv('data/outputs/sp_rp_stuff_windows.csv')
    assert 'fb_velo_window_full' in df.columns
    assert (df.loc[df['fb_velo_window_full'], 'fb_velo_window_n'] >= bw.FB_VELO_MIN_N).all()

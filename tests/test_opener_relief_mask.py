"""Issue #31 — ONE opener definition must drive both the GS gate and the
relief-pitch mask. An opener (<=30-pitch nominal starter) is a reliever by
usage: his outings were already excluded from gs_to, but relief_pitches_only
still treated him as the game's starter and dropped his pitches from the
relief aggregates (Mason Montgomery lost ~5 IP of real relief production).
"""
import pandas as pd

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'scripts' / 'xfp') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

from build_rolling_relievers import relief_pitches_only, true_starts, OPENER_MAX_PITCHES


def _game(game_pk, starter, starter_pitches, bulk, bulk_pitches):
    rows = []
    for i in range(starter_pitches):
        rows.append({'game_pk': game_pk, 'inning_topbot': 'Top', 'inning': 1,
                     'pitcher': starter})
    for i in range(bulk_pitches):
        rows.append({'game_pk': game_pk, 'inning_topbot': 'Top', 'inning': 3,
                     'pitcher': bulk})
    return rows


def test_opener_pitches_count_as_relief():
    opener, bulk, real_sp = 111, 222, 333
    full = pd.DataFrame(
        _game(1, opener, 15, bulk, 60)      # opener game: 15-pitch "start"
        + _game(2, real_sp, 90, bulk, 20))  # normal game: 90-pitch starter
    anno = full.copy()
    relief = relief_pitches_only(anno, full)
    # the opener's 15 pitches ARE relief production
    assert (relief['pitcher'] == opener).sum() == 15
    # the true starter's pitches are still excluded
    assert (relief['pitcher'] == real_sp).sum() == 0
    # the bulk reliever keeps everything
    assert (relief['pitcher'] == bulk).sum() == 80


def test_true_starts_excludes_openers():
    full = pd.DataFrame(_game(1, 111, 15, 222, 60) + _game(2, 333, 90, 222, 20))
    st = true_starts(full)
    assert set(st['starter_id']) == {333}
    assert (st['starter_pitches'] > OPENER_MAX_PITCHES).all()


def test_opener_game_relievers_survive_nullable_dtypes():
    """Regression: with Arrow/nullable Int64 (the real parquet dtype),
    `pitcher != <NA>` is NA — which silently DROPPED every reliever in an
    opener game instead of keeping the opener's pitches."""
    full = pd.DataFrame(_game(1, 111, 15, 222, 60) + _game(2, 333, 90, 222, 20))
    full['pitcher'] = full['pitcher'].astype('Int64')
    relief = relief_pitches_only(full.copy(), full)
    assert (relief['pitcher'] == 222).sum() == 80
    assert (relief['pitcher'] == 111).sum() == 15

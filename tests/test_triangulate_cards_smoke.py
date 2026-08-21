"""Issue #43 — smoke coverage for the triangulate rendering boundary.

triangulate_core is well covered but the card renderer had zero tests: a
card-only field rename rendered as blank/None in user-facing output with a
green suite. One render per bucket catches the whole class.
"""
import sys
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'scripts' / 'xfp') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

pytestmark = pytest.mark.skipif(
    not (ROOT / 'data' / 'outputs' / 'xfp_rh3_projections.csv').exists(),
    reason='projection artifacts not built in this checkout')


def _one_name(csv, name_col):
    import pandas as pd
    df = pd.read_csv(ROOT / 'data' / 'outputs' / csv)
    return str(df.iloc[0][name_col])


@pytest.mark.parametrize('bucket,csv,name_col', [
    ('H', 'xfp_rh3_projections.csv', 'player_name'),
    ('SP', 'xfp_rp3_projections.csv', 'player_name'),
    ('RP', 'xfp_rprs2_projections.csv', 'name_api'),
])
def test_card_renders_without_literal_none(bucket, csv, name_col):
    from lib.triangulate_core import triangulate_player
    from lib.triangulate_cards import build_card_data, _card_html, _verdict_class
    name = _one_name(csv, name_col)
    result = triangulate_player(name)
    if result is None:
        pytest.skip(f'{name} did not resolve in this checkout')
    card = build_card_data(result)
    card['vclass'] = _verdict_class(card)  # as build_triangulate_dashboard does
    html = _card_html(card, 0)
    assert name.split()[-1] in html
    # user-visible text must not leak Python None/nan
    text = re.sub(r'<[^>]+>', ' ', html)
    assert ' None ' not in text and ' nan ' not in text


def test_schedule_idx_is_normalised_and_none_safe():
    from lib import schedule_strength as ss
    ss._CACHE = None
    idx = ss._build_index()
    if idx:
        vals = list(idx.values())
        assert 0.0 <= min(vals) and max(vals) <= 1.0
    assert ss.schedule_idx_for('not-an-id') is None
    assert ss.schedule_idx_for(None) is None

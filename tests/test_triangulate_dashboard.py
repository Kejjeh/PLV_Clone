"""Tests for the triangulate dashboard's pure card-data extraction."""
from scripts.xfp.build_triangulate_dashboard import build_card_data


def _result(**over):
    base = {
        'player': {'display_name': 'Aaron Judge', 'team': 'NYY'},
        'bucket': 'H', 'verdict': '🏥 ON IL (TEN_DAY_DL) — talent read only: BUY',
        'verdict_top': 'MIXED', 'override_tag': 'IL', 'il_status': 'TEN_DAY_DL',
        'confidence': 0.75, 'confidence_n_aligned': 3, 'confidence_n_available': 4,
        'pl_main': 'UR', 'model_rank': 4, 'model_proj': 2.48,
        'model': {'signal': 'STRONG'}, 'arche_label': 'GOAT_TIER',
        'arche_overall': 75, 'arche_traj': 'STABLE',
        'arche': {'have': True, 't1_fp': 5.1}, 'blended_xfp': 3.2,
        'rationale': 'model #4 endorses', 'watch_list': ['x'],
    }
    base.update(over)
    return base


def test_build_card_data_surfaces_il_and_lenses():
    c = build_card_data(_result())
    assert c['name'] == 'Aaron Judge' and c['bucket'] == 'H' and c['team'] == 'NYY'
    assert c['il_status'] == 'TEN_DAY_DL'
    assert c['is_il'] is True                      # derived flag for the badge
    assert c['pl_rank'] == 'UR' and c['model_rank'] == 4
    assert c['arche_label'] == 'GOAT_TIER' and c['arche_t1'] == 5.1
    assert c['watch_list'] == ['x']


def test_build_card_data_healthy_player_no_il():
    c = build_card_data(_result(il_status=None, override_tag=None))
    assert c['is_il'] is False and c['il_status'] is None


def test_build_card_data_tolerates_sparse_result():
    c = build_card_data({'player': {'display_name': 'X'}, 'bucket': 'SP'})
    assert c['name'] == 'X' and c['bucket'] == 'SP'
    assert c['is_il'] is False and c['watch_list'] == []

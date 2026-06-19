"""Tests for the triangulate dashboard's pure card-data extraction."""
from scripts.xfp.build_triangulate_dashboard import build_card_data


def _hitter(**over):
    base = {
        'player': {'display_name': 'Aaron Judge', 'team': 'NYY'},
        'bucket': 'H',
        'verdict': '🏥 ON IL (TEN_DAY_DL) — talent read only: BUY',
        'verdict_top': 'MIXED', 'override_tag': 'IL', 'il_status': 'TEN_DAY_DL',
        'confidence': 0.75, 'confidence_n_aligned': 3, 'confidence_n_available': 4,
        'pl_main': 'UR', 'pl_main_date': '2026-06-09',
        'model_rank': 4, 'model_proj': 2.48,
        'model': {
            'signal': 'STRONG', 'proj_label': 'elite', 'p25': 1.9, 'p75': 3.1,
            'sigma': 0.6, 'data_quality_tag': 'data_driven',
            'hitter_boom_stack': 3, 'hitter_boom_rate_expected': 0.41,
            'hitter_boom_bust_expected': 0.12, 'sustainability': 'LEGIT',
            'process_verdict': 'ELITE',
        },
        'arche_label': 'GOAT_TIER', 'arche_overall': 75, 'arche_traj': 'STABLE',
        'arche': {'have': True, 't1_fp': 5.1, 't2_fp': 4.9, 'cell': 'P+/C+/D+',
                  'slope_3yr': 0.2, 'career_pct': 0.95, 'boundary_tier': 'SOLID',
                  'age_tier': 'PEAK'},
        'blended_xfp': 3.2, 'blended_ci': (2.6, 3.8), 'value_tier': 'ELITE',
        'replacement_delta': 1.4,
        'rationale': 'model #4 endorses', 'watch_list': ['x'],
    }
    base.update(over)
    return base


def _sp(**over):
    base = {
        'player': {'display_name': 'Tarik Skubal', 'team': 'DET'}, 'bucket': 'SP',
        'verdict': 'BUY', 'verdict_top': 'BUY', 'il_status': None,
        'pl_main': 12, 'model_rank': 3, 'model_proj': 18.4,
        'model': {
            'signal': 'RISING', 'boom_stack': 3, 'boom_tier': 'A',
            'boom_rate_expected': 0.38, 'boom_bust_rate_expected': 0.10,
            'boom_mean_fp_expected': 19.2, 'decline_tier': 'STABLE',
            'velo_severity': None, 'recform_tag': 'HOT', 'recform_z': 1.4,
            'is_high_k_arm': True, 'high_k_z_score': 2.1,
            'is_elite_framer': True, 'is_framing_tax': False,
            'sustainability': 'IMPROVING',
        },
        'arche': {'have': True, 't1_fp': 17.0, 'cell': 'S+/M+/C+',
                  'velo_tier': 'POWER', 'stuff_subtype': 'WHIFF_LED'},
        'value_tier': 'ELITE', 'watch_list': [],
    }
    base.update(over)
    return base


def test_hitter_card_surfaces_all_lenses():
    c = build_card_data(_hitter())
    assert c['name'] == 'Aaron Judge' and c['is_il'] is True
    # model band + quality
    assert c['model']['p25'] == 1.9 and c['model']['p75'] == 3.1
    assert c['model']['dq_tag'] == 'data_driven'
    # boom uses the HITTER boom fields for a hitter
    assert c['boom']['stack'] == 3 and c['boom']['boom_rate'] == 0.41
    assert c['boom']['bust_rate'] == 0.12
    assert c['sustainability'] == 'LEGIT'
    # archetype depth
    assert c['arche']['cell'] == 'P+/C+/D+' and c['arche']['t2'] == 4.9
    assert c['arche']['career_pct'] == 0.95 and c['arche']['boundary'] == 'SOLID'
    # blend
    assert c['blend']['value_tier'] == 'ELITE' and c['blend']['ci'] == (2.6, 3.8)
    assert c['blend']['rep_delta'] == 1.4


def test_sp_card_uses_sp_boom_and_signals():
    c = build_card_data(_sp())
    assert c['bucket'] == 'SP' and c['is_il'] is False
    # boom uses the SP boom fields for an SP
    assert c['boom']['stack'] == 3 and c['boom']['tier'] == 'A'
    assert c['boom']['mean_fp'] == 19.2
    # SP-only signal panel
    assert c['sp']['recform_tag'] == 'HOT' and c['sp']['high_k'] is True
    assert c['sp']['elite_framer'] is True and c['sp']['decline_tier'] == 'STABLE'
    assert c['arche']['velo_tier'] == 'POWER' and c['arche']['stuff_subtype'] == 'WHIFF_LED'


def test_build_card_data_tolerates_sparse_result():
    c = build_card_data({'player': {'display_name': 'X'}, 'bucket': 'SP'})
    assert c['name'] == 'X' and c['is_il'] is False and c['watch_list'] == []
    assert c['boom']['stack'] is None and c['arche']['have'] is False
    assert c['sp']['recform_tag'] is None and c['model']['p25'] is None

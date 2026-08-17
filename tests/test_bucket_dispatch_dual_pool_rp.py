"""resolve_player()/_find_by_id() must not default a real dual-pool RP to
the SP model just because the search order checks SP before RP — issue
#27, the repo's #1 documented mistake pattern (rank an RP with rp3, not
rprs2) reintroduced via triangulate's own independent bucket detector.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.xfp.lib import bucket_dispatch as bd  # noqa: E402
from scripts.xfp.lib import cached_data as cd      # noqa: E402


@pytest.fixture
def dual_pool_swingman(tmp_path, monkeypatch):
    """'Cole Sample' clears rp3's inclusion bar (gs_to=2, a spot start or
    two) but is fundamentally a reliever, also present in rprs2 with real
    appearance volume — the confirmed 2026-08-16 live-data pattern (Cole
    Sulser, Cionel Perez, etc: 11 real dual-pool pitchers)."""
    h = pd.DataFrame([dict(batter=1, player_name='Nobody Hitter', team='SEA',
                           primary_position='2B', rank=400, xfp_rh3_per_game=0.5)])
    hp = tmp_path / 'rh3.csv'
    h.to_csv(hp, index=False)

    sp = pd.DataFrame([
        dict(pitcher=555, player_name='Sample, Cole', team='PHI', rank=200,
             xfp_rp3_per_start=8.0, gs_to=2),
        dict(pitcher=999, player_name='Genuine, Starter', team='NYY', rank=10,
             xfp_rp3_per_start=15.0, gs_to=22),
    ])
    spp = tmp_path / 'rp3.csv'
    sp.to_csv(spp, index=False)

    rp = pd.DataFrame([dict(pitcher=555, name_api='Cole Sample', rank=50,
                            xfp_ros=60.0)])
    rpp = tmp_path / 'rprs2.csv'
    rp.to_csv(rpp, index=False)

    monkeypatch.setitem(bd.PROJECTIONS, 'H', str(hp))
    monkeypatch.setitem(bd.PROJECTIONS, 'SP', str(spp))
    monkeypatch.setitem(bd.PROJECTIONS, 'RP', str(rpp))
    for b in ('H', 'SP', 'RP'):
        monkeypatch.setitem(bd.ARCHETYPE_PANELS, b,
                            str(tmp_path / f'missing_{b}.parquet'))
    cd._load_projection_at.cache_clear()
    cd._load_archetype_at.cache_clear()
    yield bd
    cd._load_projection_at.cache_clear()
    cd._load_archetype_at.cache_clear()


def test_dual_pool_thin_starts_resolves_to_rp_by_default(dual_pool_swingman):
    """No hint given (the /triangulate default): a name in BOTH pools with
    only a couple real starts (gs_to=2, below the data_driven_full bar)
    must resolve to bucket='RP', not silently default to 'SP'."""
    r = dual_pool_swingman.resolve_player('Cole Sample')
    assert r is not None
    assert r['bucket'] == 'RP'
    assert r['id'] == 555


def test_dual_pool_by_id_also_prefers_rp(dual_pool_swingman):
    """_find_by_id has the same default-order bug for id-based lookups."""
    r = dual_pool_swingman._find_by_id(555, 'Cole Sample', None)
    assert r is not None
    assert r['bucket'] == 'RP'


def test_genuine_starter_with_dual_pool_membership_still_resolves_sp(dual_pool_swingman):
    """A pitcher with real rotation volume (gs_to=22) who ALSO happens to
    have an rprs2 row must stay SP — the fix is a bounded nudge for thin-
    start swingmen, not a blanket 'prefer RP' rule."""
    r = dual_pool_swingman.resolve_player('Genuine, Starter')
    assert r is not None
    assert r['bucket'] == 'SP'


def test_explicit_sp_hint_still_honored_even_for_a_swingman(dual_pool_swingman):
    """An explicit position=/hint='SP' request is a deliberate ask and must
    not be overridden by the dual-pool nudge."""
    r = dual_pool_swingman.resolve_player('Cole Sample', 'SP')
    assert r is not None
    assert r['bucket'] == 'SP'

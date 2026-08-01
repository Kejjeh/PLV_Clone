"""Rule-10 regression tests for resolve_player() in scripts/xfp/lib/bucket_dispatch.py.

Audit C4 (docs/production_audit_2026-07-30.md): resolve_player() silently
returned m.iloc[0] on a multi-row name-key match (stderr WARN, wrong player)
and never consulted KNOWN_COLLISIONS. The contract locked here mirrors the
canonical resolvers in plv_clone.utils.name_match: refuse to guess (None +
loud stderr) on any ambiguous name, resolve via team/position hints when
supplied, and stay byte-identical for unambiguous names.

Fixtures are fully hermetic: synthetic projection CSVs in tmp_path patched
into bucket_dispatch.PROJECTIONS / ARCHETYPE_PANELS (the established pattern
from tests/test_no_silent_zero_inputs.py — monkeypatch the module path
constants, clear the mtime-keyed lru caches, never touch live data).
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
def synth_pools(tmp_path, monkeypatch):
    """Synthetic H/SP/RP projection pools with two name collisions:

    - 'Max Muncy' x2 (the canonical KNOWN_COLLISIONS pair, 571970 LAD vs
      691777 ATH), and
    - 'Alex Rivera' x2 (a fictional pair NOT in any collision table, so it
      exercises the generic multi-match path, not the collision gate).
    Archetype panels are pointed at nonexistent paths (loader returns None).
    """
    h = pd.DataFrame([
        dict(batter=571970, player_name='Max Muncy', team='LAD',
             primary_position='3B', rank=60, xfp_rh3_per_game=1.97),
        dict(batter=691777, player_name='Max Muncy', team='ATH',
             primary_position='SS', rank=436, xfp_rh3_per_game=1.27),
        dict(batter=111, player_name='Alex Rivera', team='SEA',
             primary_position='2B', rank=10, xfp_rh3_per_game=3.10),
        dict(batter=222, player_name='Alex Rivera', team='TEX',
             primary_position='C', rank=300, xfp_rh3_per_game=0.90),
        dict(batter=656941, player_name='Kyle Schwarber', team='PHI',
             primary_position='DH', rank=3, xfp_rh3_per_game=4.50),
    ])
    hp = tmp_path / 'rh3.csv'
    h.to_csv(hp, index=False)
    sp = pd.DataFrame([dict(pitcher=433587, player_name='Verlander, Justin',
                            rank=50, xfp_rp3_per_start=10.0, team='SF')])
    spp = tmp_path / 'rp3.csv'
    sp.to_csv(spp, index=False)
    rp = pd.DataFrame([dict(pitcher=100, name_api='Some Reliever',
                            rank=1, xfp_ros=50.0)])
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


def test_resolver_refuses_ambiguous_name_without_disambiguator(synth_pools, capsys):
    """Two pool rows share a name key and the caller supplied no
    team/position: the resolver returns None with a loud stderr message —
    never the first row (the silently-wrong-player bug)."""
    # Generic multi-match (name NOT in KNOWN_COLLISIONS).
    assert synth_pools.resolve_player('Alex Rivera', 'H') is None
    # Known collision (KNOWN_COLLISIONS gate) — same refusal contract as
    # resolve_batter_id('Max Muncy') is None.
    assert synth_pools.resolve_player('Max Muncy', 'H') is None
    err = capsys.readouterr().err
    assert 'Alex Rivera' in err
    assert 'Max Muncy' in err


def test_resolver_team_or_position_hint_selects_the_named_player(synth_pools):
    """The widened hint: team= (canonicalized through team_key, so ESPN's
    'Oak' == the model CSVs' 'ATH') or position= selects exactly one player
    from an ambiguous name — including the Athletics Max Muncy by team."""
    # KNOWN_COLLISIONS gate path: caller names the Athletics.
    r = synth_pools.resolve_player('Max Muncy', 'H', team='ATH')
    assert r is not None
    assert r['id'] == 691777
    assert r['team'] == 'ATH'
    # ESPN team-code alias for the same club.
    r2 = synth_pools.resolve_player('Max Muncy', 'H', team='Oak')
    assert r2 is not None and r2['id'] == 691777
    # Generic multi-match path: team hint filters the pool rows.
    r3 = synth_pools.resolve_player('Alex Rivera', 'H', team='TEX')
    assert r3 is not None and r3['id'] == 222
    # Position hint works when no team was given.
    r4 = synth_pools.resolve_player('Alex Rivera', 'H', position='C')
    assert r4 is not None and r4['id'] == 222
    # A team hint matching NO row refuses rather than guessing.
    assert synth_pools.resolve_player('Alex Rivera', 'H', team='NYY') is None
    # Unambiguous names resolve exactly as before, hints or not.
    r5 = synth_pools.resolve_player('Kyle Schwarber', 'H')
    assert r5 is not None and r5['id'] == 656941


def test_collision_name_with_single_pooled_candidate_resolves_with_breadcrumb(
        tmp_path, monkeypatch, capsys):
    """The over-refusal regression (review round 2, 2026-07-30): a name in
    KNOWN_COLLISIONS whose colliding twin has NO row in any pool is not
    ambiguous IN THE POOLS — hintless resolution must return the single
    pooled candidate (pre-C4 behavior for Will Smith / Jacob Wilson / Luis
    Garcia Jr.), with a stderr breadcrumb naming the resolved team so the
    collision risk stays visible. Refusing here broke the entire hintless
    triangulate surface for real, rosterable players."""
    h = pd.DataFrame([
        dict(batter=571970, player_name='Max Muncy', team='LAD',
             primary_position='3B', rank=60, xfp_rh3_per_game=1.97),
        dict(batter=656941, player_name='Kyle Schwarber', team='PHI',
             primary_position='DH', rank=3, xfp_rh3_per_game=4.50),
    ])
    hp = tmp_path / 'rh3.csv'
    h.to_csv(hp, index=False)
    sp = pd.DataFrame([dict(pitcher=433587, player_name='Verlander, Justin',
                            rank=50, xfp_rp3_per_start=10.0, team='SF')])
    spp = tmp_path / 'rp3.csv'; sp.to_csv(spp, index=False)
    rp = pd.DataFrame([dict(pitcher=100, name_api='Some Reliever',
                            rank=1, xfp_ros=50.0)])
    rpp = tmp_path / 'rprs2.csv'; rp.to_csv(rpp, index=False)
    monkeypatch.setitem(bd.PROJECTIONS, 'H', str(hp))
    monkeypatch.setitem(bd.PROJECTIONS, 'SP', str(spp))
    monkeypatch.setitem(bd.PROJECTIONS, 'RP', str(rpp))
    for b in ('H', 'SP', 'RP'):
        monkeypatch.setitem(bd.ARCHETYPE_PANELS, b,
                            str(tmp_path / f'missing_{b}.parquet'))
    cd._load_projection_at.cache_clear()
    cd._load_archetype_at.cache_clear()
    try:
        r = bd.resolve_player('Max Muncy', 'H')
        assert r is not None, (
            'single pooled candidate for a collision-table name must resolve, '
            'not refuse — hintless triangulate broke on exactly this')
        assert r['id'] == 571970
        err = capsys.readouterr().err
        assert 'Max Muncy' in err and 'LAD' in err, (
            'the collision risk must stay visible via a breadcrumb')
    finally:
        cd._load_projection_at.cache_clear()
        cd._load_archetype_at.cache_clear()

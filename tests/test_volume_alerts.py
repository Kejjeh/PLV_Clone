"""Volume-alert classification: catch role changes, not model shrinkage.

WHY THIS EXISTS
The volume model (xfp_volume_pipeline) already accounts for playing-time
change — it reads pa_last21, lineup_spot_to and the IL features. What did NOT
exist was anything that TELLS Josh when a role moves: /volume-watch is
on-demand, so a Matt-Chapman-shaped collapse (pa_last21 = 0 while naive season
pace still says 3.20 PA/team-game) sat unflagged until someone thought to look.

THE TRAP THIS PINS
The obvious trigger — `proj_ros_pa_per_teamgame - naive_pace` — is WRONG as a
role-loss detector. That model gap carries league-wide shrinkage toward the
mean (2026-08-01: mean -0.109, SD 0.604), so on any given night EVERY hitter
on a roster shows a negative gap and the alert is pure noise. The 2026-08-01
board showed all 12 of Josh's healthy hitters as "faders" at the 74th-97th
volume percentile — none of them had actually lost playing time.

So role-LOSS keys on RECENT vs SEASON pace (pa_last21 / team games in that
window), which shrinkage cannot manufacture. Role-GAIN may use the model gap
because shrinkage points the other way — a large POSITIVE gap is signal
against the prior, not with it.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.xfp.lib.volume_alerts import (  # noqa: E402
    IL_ZERO, ROLE_GAIN, ROLE_LOSS, SIDES, build_alert_rows, is_new_signal,
    recent_pace,
)


# ── recent_pace: the primitive the loss signal stands on ────────────────────
def test_recent_pace_is_pa_over_team_games_in_window():
    assert recent_pace(65, 18) == pytest.approx(65 / 18)


def test_recent_pace_returns_none_when_team_games_unknown_or_zero():
    """A zero/absent team-game count must NOT read as 'played zero PA'.

    Dividing by it would render the entire league as a role-loss alert on any
    night the schedule join breaks — the single most dangerous failure mode
    for a step that emails Josh.
    """
    assert recent_pace(0, 0) is None
    assert recent_pace(40, None) is None
    assert recent_pace(None, 18) is None


# ── the Chapman case: the signal this whole step exists to catch ────────────
def _row(name, naive, proj, pa_last21, **kw):
    base = dict(player_name=name, naive_pace=naive,
                proj_ros_pa_per_teamgame=proj, pa_last21=pa_last21,
                pa_per_teamgame_to=naive, team='SF', is_on_il_at_split=0)
    base.update(kw)
    return base


def test_regular_who_stopped_playing_is_flagged_role_loss():
    """Chapman 2026-08-01: season pace 3.20, ZERO PA in the last 21 days."""
    df = pd.DataFrame([_row('Matt Chapman', 3.20, 1.92, 0)])
    out = build_alert_rows(df, team_games_l21={'SF': 18},
                           owned={'matt chapman'}, fa=set())
    assert len(out) == 1
    assert out.iloc[0]['signal'] == ROLE_LOSS
    assert out.iloc[0]['recent_pace'] == pytest.approx(0.0)
    assert 'Matt Chapman' in out.iloc[0]['player_name']


def test_healthy_regular_is_not_flagged():
    df = pd.DataFrame([_row('Corbin Carroll', 4.17, 3.66, 70)])
    out = build_alert_rows(df, team_games_l21={'SF': 18},
                           owned={'corbin carroll'}, fa=set())
    assert out.empty


def test_model_shrinkage_alone_never_fires_a_loss_alert():
    """THE regression that motivates the design.

    Every one of these is a real 2026-08-01 row where proj << naive purely
    from shrinkage, while the player kept playing every day. If the detector
    keys on the model gap, all four alert and the step is unusable.
    """
    rows = [
        _row('Bo Bichette', 4.279, 3.470, 64),
        _row('Pete Alonso', 4.373, 3.591, 70),
        _row('Max Muncy', 3.473, 2.499, 53),
        _row('Luis Arraez', 4.173, 3.560, 65),
    ]
    df = pd.DataFrame(rows)
    owned = {r['player_name'].lower() for r in rows}
    out = build_alert_rows(df, team_games_l21={'SF': 18}, owned=owned, fa=set())
    assert out.empty, f'shrinkage fired a false alert: {out.to_dict("records")}'


def test_real_near_miss_bellinger_shape_does_fire():
    """CALIBRATION PIN (live data, 2026-08-01). Cody Bellinger fell from a
    3.954 season pace to 39 PA over NYY's 14 games = 2.786 PA/team-game —
    roughly a whole lineup spot of work gone. At the first-cut ratio gate of
    0.70 he missed by 0.018 and stayed silent, which is precisely the kind of
    demotion this step exists to surface. The gate is 0.75; this test is what
    stops a future tightening from re-hiding him.
    """
    df = pd.DataFrame([_row('Cody Bellinger', 3.954, 2.726, 39)])
    out = build_alert_rows(df, team_games_l21={'SF': 14},
                           owned={'cody bellinger'}, fa=set())
    assert len(out) == 1
    assert out.iloc[0]['signal'] == ROLE_LOSS


def test_healthy_everyday_regulars_stay_silent_at_the_calibrated_gate():
    """The other half of the calibration. These are live 2026-08-01 rows for
    Josh's actual everyday bats; all sit at ~0.95-1.00 of season pace, far
    from the 0.75 gate. If a future loosening starts firing on these, the
    alert has become noise and this test fails first.
    """
    rows = [
        _row('Bo Bichette', 4.279, 3.470, 64),
        _row('Luis Arraez', 4.173, 3.560, 65),
        _row('Pete Alonso', 4.373, 3.591, 70),
        _row('Corbin Carroll', 4.173, 3.659, 70),
    ]
    df = pd.DataFrame(rows)
    out = build_alert_rows(df, team_games_l21={'SF': 16},
                           owned={r['player_name'].lower() for r in rows},
                           fa=set())
    assert out.empty, f'gate is now firing on healthy regulars: {out.to_dict("records")}'


def test_il_player_is_labelled_not_reported_as_role_loss():
    """Judge is on the IL — zero recent PA is KNOWN, not news."""
    df = pd.DataFrame([_row('Aaron Judge', 2.373, 2.160, 0,
                            is_on_il_at_split=1)])
    out = build_alert_rows(df, team_games_l21={'SF': 18},
                           owned={'aaron judge'}, fa=set())
    assert (out.empty) or (out.iloc[0]['signal'] != ROLE_LOSS)


# ── role gain: FA opportunity ──────────────────────────────────────────────
def test_fa_with_confirmed_expanded_role_is_flagged_gain():
    """Jasson Dominguez 2026-08-01: naive 1.84 -> proj 3.09, 69 PA in L21."""
    df = pd.DataFrame([_row('Jasson Dominguez', 1.836, 3.089, 69)])
    out = build_alert_rows(df, team_games_l21={'SF': 18},
                           owned=set(), fa={'jasson dominguez'})
    assert len(out) == 1
    assert out.iloc[0]['signal'] == ROLE_GAIN


def test_fa_model_gain_not_confirmed_by_playing_time_is_suppressed():
    """A big model gap on a player who is barely playing is a projection
    artifact (a callup with almost no denominator), not an opportunity."""
    df = pd.DataFrame([_row('Bench Guy', 0.49, 2.51, 8)])
    out = build_alert_rows(df, team_games_l21={'SF': 18},
                           owned=set(), fa={'bench guy'})
    assert out.empty


def test_unowned_unlisted_players_are_ignored_entirely():
    df = pd.DataFrame([_row('Some Opponent Bat', 3.20, 1.92, 0)])
    out = build_alert_rows(df, team_games_l21={'SF': 18},
                           owned=set(), fa=set())
    assert out.empty


def test_missing_team_games_yields_no_alerts_not_a_flood():
    """If the schedule join fails outright, emit NOTHING rather than
    classify the entire roster as collapsed."""
    df = pd.DataFrame([_row('Matt Chapman', 3.20, 1.92, 0)])
    out = build_alert_rows(df, team_games_l21={}, owned={'matt chapman'},
                           fa=set())
    assert out.empty


def test_output_is_sorted_by_severity_desc():
    rows = [
        _row('Mild Drop', 3.0, 2.4, 30),      # recent 1.67 vs 3.0
        _row('Severe Drop', 3.4, 1.5, 0),     # recent 0.00 vs 3.4
    ]
    df = pd.DataFrame(rows)
    out = build_alert_rows(df, team_games_l21={'SF': 18},
                           owned={'mild drop', 'severe drop'}, fa=set())
    assert list(out['player_name']) == ['Severe Drop', 'Mild Drop']
    assert out.iloc[0]['severity'] > out.iloc[1]['severity']


# ═══════════════════════════════════════════════════════════════════════════
# SP / RP sides — calibrated separately because their windows are LUMPY
#
# A 21-day window holds ~65 PA for a hitter but only ~3-4 starts for an SP and
# ~6-8 appearances for an RP, so one skipped turn is a 25% swing that means
# nothing. Gates calibrated against live 2026-08-01 distributions:
#   SP healthy regulars ratio p05 0.53 / p10 0.73 / p25 0.94; IL median 0.00.
#      healthy abs drop p90 0.050, p95 0.061; IL median drop 0.072.
#   RP healthy regulars ratio p05 0.23 / p10 0.71 / p25 0.91; IL median 0.00.
#      healthy abs drop p90 0.109, p95 0.245; IL median drop 0.164.
# Hence SP (0.60 ratio, 0.060 abs) and RP (0.55 ratio, 0.120 abs): both sit
# below the healthy p10 and above the healthy p90 drop, while every IL case
# clears comfortably.
# ═══════════════════════════════════════════════════════════════════════════
def _sp_row(name, season, last21, **kw):
    base = dict(player_name=name, team='DET', naive_pace=season,
                gs_per_teamgame_to=season, proj_ros_gs_per_teamgame=season,
                gs_last21=last21, is_on_il_at_split=0)
    base.update(kw)
    return base


def _rp_row(name, season, last21, **kw):
    base = dict(player_name=name, team='ATL', naive_pace=season,
                g_per_teamgame_to=season, proj_ros_g_per_teamgame=season,
                g_last21=last21, is_on_il_at_split=0)
    base.update(kw)
    return base


def test_sp_csv_lastfirst_and_accented_names_still_match_the_roster():
    """REGRESSION (caught live, 2026-08-01). The SP volume CSV writes
    'Sánchez, Cristopher' / 'Soriano, José' — 'Last, First' WITH accents —
    while the ESPN roster says 'Jose Soriano'. A naive lower().strip() key
    matched ZERO of 29 roster names, so the entire SP side was silently dead:
    it produced no rows, logged no error, and would have reported a permanent
    all-clear no matter how many starts an owned arm lost.

    Keying must therefore flip 'Last, First' and strip accents (the
    _flip_lastfirst + safe_name_key composition the rest of the repo uses).
    """
    df = pd.DataFrame([
        _sp_row('Soriano, José', 0.194, 1),
        _sp_row('Sánchez, Cristopher', 0.194, 0),
    ])
    out = build_alert_rows(
        df, side='SP', team_games_l21={'DET': 18},
        owned={'Jose Soriano', 'Cristopher Sanchez'}, fa=set())
    assert len(out) == 2, (
        'accented "Last, First" names did not match the roster — the SP side '
        f'is dead again: {out.to_dict("records")}')
    assert set(out['signal']) == {ROLE_LOSS}


def test_per_row_team_games_column_wins_over_the_team_code_map():
    """REGRESSION (caught live, 2026-08-01). 20 of 272 rows in the SP volume
    CSV carry team = NaN (Hunter Greene among them), so a team-CODE lookup
    can never resolve them and they silently drop out of the alert forever —
    fail-safe, but a permanent blind spot on 7% of the SP pool.

    The runner therefore resolves games-in-window per PLAYER via mlbam and
    hands it down as a `team_games_l21` column, which must take precedence
    over the code map.
    """
    row = _sp_row('Greene, Hunter', 0.194, 1)
    row['team'] = float('nan')
    row['team_games_l21'] = 18
    out = build_alert_rows(pd.DataFrame([row]), side='SP',
                           team_games_l21={}, owned={'hunter greene'},
                           fa=set())
    assert len(out) == 1
    assert out.iloc[0]['signal'] == ROLE_LOSS


def test_sides_registry_exposes_three_calibrated_specs():
    assert set(SIDES) == {'H', 'SP', 'RP'}
    assert SIDES['SP'].last21_col == 'gs_last21'
    assert SIDES['RP'].last21_col == 'g_last21'
    assert SIDES['H'].last21_col == 'pa_last21'


def test_sp_one_skipped_start_is_normal_rotation_wobble_and_stays_silent():
    """3 starts instead of 4 in 18 team games: ratio 0.86. Every fifth-day
    starter does this; alerting here would make the step unusable."""
    df = pd.DataFrame([_sp_row('Healthy Ace', 0.194, 3)])
    out = build_alert_rows(df, side='SP', team_games_l21={'DET': 18},
                           owned={'healthy ace'}, fa=set())
    assert out.empty


def test_sp_losing_the_rotation_spot_fires():
    """1 start in 18 team games against a 0.194 season pace: ratio 0.29."""
    df = pd.DataFrame([_sp_row('Demoted Arm', 0.194, 1)])
    out = build_alert_rows(df, side='SP', team_games_l21={'DET': 18},
                           owned={'demoted arm'}, fa=set())
    assert len(out) == 1
    assert out.iloc[0]['signal'] == ROLE_LOSS


def test_sp_on_il_is_labelled_il_not_role_loss():
    df = pd.DataFrame([_sp_row('Hurt Arm', 0.194, 0, is_on_il_at_split=1)])
    out = build_alert_rows(df, side='SP', team_games_l21={'DET': 18},
                           owned={'hurt arm'}, fa=set())
    assert len(out) == 1
    assert out.iloc[0]['signal'] == IL_ZERO


def test_sp_swingman_below_min_season_pace_never_alerts():
    """A 0.06 season pace is not a rotation piece; his zero is not news."""
    df = pd.DataFrame([_sp_row('Swing Man', 0.06, 0)])
    out = build_alert_rows(df, side='SP', team_games_l21={'DET': 18},
                           owned={'swing man'}, fa=set())
    assert out.empty


def test_rp_normal_usage_wobble_stays_silent():
    """6 appearances in 18 games vs a 0.35 season pace: ratio 0.95."""
    df = pd.DataFrame([_rp_row('Setup Guy', 0.35, 6)])
    out = build_alert_rows(df, side='RP', team_games_l21={'ATL': 18},
                           owned={'setup guy'}, fa=set())
    assert out.empty


def test_rp_falling_out_of_the_bullpen_mix_fires():
    """2 appearances in 18 games vs 0.35: ratio 0.32, drop 0.239."""
    df = pd.DataFrame([_rp_row('Buried Arm', 0.35, 2)])
    out = build_alert_rows(df, side='RP', team_games_l21={'ATL': 18},
                           owned={'buried arm'}, fa=set())
    assert len(out) == 1
    assert out.iloc[0]['signal'] == ROLE_LOSS


# ═══════════════════════════════════════════════════════════════════════════
# Freshness — an alert must fire on the TRANSITION, not every night after
# ═══════════════════════════════════════════════════════════════════════════
def test_first_ever_run_bootstraps_and_alerts_nothing():
    """prior=None means no history exists for this side yet. Recording the
    state without alerting is the only safe bootstrap: the alternative is
    every IL'd and benched player on the roster paging at once on night one.
    """
    assert is_new_signal(None, 'bo bichette', ROLE_LOSS) is False


def test_player_absent_from_prior_run_is_new():
    assert is_new_signal({'someone else': ROLE_LOSS}, 'new guy',
                         ROLE_LOSS) is True


def test_same_signal_as_last_night_is_not_new():
    """Judge has been IL_ZERO for weeks — that is not tonight's news."""
    assert is_new_signal({'aaron judge': IL_ZERO}, 'aaron judge',
                         IL_ZERO) is False


def test_changed_signal_is_new():
    """A player who was merely losing time and has now landed on the IL is a
    fresh event even though he alerted yesterday."""
    assert is_new_signal({'cody bellinger': ROLE_LOSS}, 'cody bellinger',
                         IL_ZERO) is True


def test_build_alert_rows_stamps_is_new_from_prior_state():
    rows = [_row('Fresh Drop', 3.4, 1.5, 0), _row('Old News', 3.4, 1.5, 0)]
    df = pd.DataFrame(rows)
    out = build_alert_rows(
        df, team_games_l21={'SF': 18},
        owned={'fresh drop', 'old news'}, fa=set(),
        prior={'old news': ROLE_LOSS})
    got = dict(zip(out['player_name'], out['is_new']))
    assert bool(got['Fresh Drop']) is True
    assert bool(got['Old News']) is False


def test_history_key_round_trips_with_the_lookup_key():
    """REGRESSION (caught live, 2026-08-01). The history writer keyed on a
    naive player_name.lower() while the lookup used the accent- and
    'Last, First'-aware _key(). Every accented or comma-formatted name
    therefore failed to match its OWN recorded state and re-reported as NEW
    every single night — a freshness check that is silently always-fresh is
    worse than no freshness check at all.

    Whatever the writer stores must be exactly what is_new_signal looks up.
    """
    from scripts.xfp.lib.volume_alerts import _key

    for raw in ['Soriano, José', 'Sánchez, Cristopher', 'Luis García Jr.',
                'Dylan Lee']:
        stored = _key(raw)                       # what _append_history writes
        assert is_new_signal({stored: ROLE_GAIN}, _key(raw),
                             ROLE_GAIN) is False, (
            f'{raw!r} does not match its own recorded key')


def test_bootstrap_run_marks_every_row_not_new():
    rows = [_row('A', 3.4, 1.5, 0), _row('B', 3.4, 1.5, 0)]
    df = pd.DataFrame(rows)
    out = build_alert_rows(df, team_games_l21={'SF': 18},
                           owned={'a', 'b'}, fa=set(), prior=None)
    assert len(out) == 2
    assert not out['is_new'].any()

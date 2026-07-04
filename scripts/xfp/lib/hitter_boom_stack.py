"""hitter_boom_stack — live-prediction computation for hitter triangulate cards.

Hitter analog of `boom_stack.py` (SP). Validated 2026-06-03 via
`scripts/xfp/analyze_hitter_boom_bust.py` — SHIP-CAUTIOUS as ADVISORY TAG.
See `data/research/validation_runs/hitter_boom_bust_deep_dive.md`.

Three components per hitter at "now":

  1. skill_spike_hitter: last-10g xwOBA - season xwOBA >= +0.040 AND
     last-10g K% - season K% <= -3 pp. Computed live from
     `data/research/xfp_cache/statcast_2026.parquet`. Requires >=20 prior
     games of season data for stable comparators; else 0.

  2. recform_hot_hitter: last-10g FP/g - season FP/g >= +1.5 where FP is
     the SAME fp_proxy used in the validation (TB + BB + HBP - K, not full
     FP) so the threshold is in the validated unit.

  3. opp_soft_hitter: opposing SP's `xfp_rp3_per_start` is in the BOTTOM
     tertile across the 2026 rp3 panel. Weak opposing SP = soft opp for
     the hitter. If `opp_sp_id` is None (no confirmed probable for today),
     component is 0 and `reason='no_opp_sp'`.

  4. lineup_amp_hitter: own boom_stack(1+2+3) >= 1 AND >= 2 OTHER
     starters on the hitter's team today also have boom_stack(1+2+3) >= 1.
     "Other starters" is determined by today's confirmed MLB lineup (via
     MLB Stats API). If the lineup isn't posted yet, fall back to the
     hitter's team's TOP 9 BY rh3 in `xfp_rh3_projections.csv` as the
     expected starting nine. Validated 2026-06-03 via
     `analyze_hitter_lineup_correlation.py`: +2.1 pp within-stratum
     boom-rate lift on own_stack >= 1 (year-stable 7/7 years +1.4 to
     +3.0 pp). Recursive guard — when computing teammates' stacks we
     pass `skip_lineup_amp=True` so component 4 never recurses on
     itself. See `data/research/validation_runs/hitter_lineup_correlation.md`.

`boom_stack = c1 + c2 + c3 + c4 ∈ {0, 1, 2, 3, 4}`.

DISPLAY TAG ONLY. Not a feature in RH3_FEATS. Not a verdict override.

Per-stack outcomes (n=245,712 starter-games, 2018-2025; PA>=4 filter,
fp_proxy = TB+BB+HBP-K, boom_game = fp_proxy >= 80th pct ~ 5+):

  stack=0: 23.9% boom rate, 43.4% bust rate (n=161,766)
  stack=1: 25.6% boom rate, 40.7% bust rate (n=75,234)
  stack=2: 27.5% boom rate, 40.2% bust rate (n=7,971)
  stack=3: 30.6% boom rate, 37.5% bust rate (n=741)

Stack=3 vs stack=0 edge: +6.7 pp boom rate, -5.9 pp bust rate, +0.46 mean
fp_proxy. Year-by-year stability (2018-2025): all 7 years positive edge
(+2.3 to +5.3 pp on stack 2+ vs 0). Note that stack=3 STILL busts 37.5%
of the time — boom_stack shifts the distribution, not the floor.

Caveat: SB / R / RBI are not in fp_proxy because statcast is pitch-level.
Boom rate is therefore on the TB+BB+HBP-K subset of FP variance (~49% of
full FP, season-aggregate r=0.98 with full FP).
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from functools import lru_cache
from typing import Optional

import numpy as np
import pandas as pd

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
_STATCAST_2026 = os.path.join(_REPO_ROOT, 'data', 'research', 'xfp_cache', 'statcast_2026.parquet')
_BOXSCORE_H = os.path.join(_REPO_ROOT, 'data', 'research', 'xfp_cache', 'boxscore_hitters.parquet')
_RP3_PROJ = os.path.join(_REPO_ROOT, 'data', 'outputs', 'xfp_rp3_projections.csv')
_RH3_PROJ = os.path.join(_REPO_ROOT, 'data', 'outputs', 'xfp_rh3_projections.csv')


def _warn(section: str, exc: BaseException) -> None:
    """One-line stderr breadcrumb for fail-soft handlers (audit 2026-07-04:
    silent excepts hide dead components for weeks). Semantics unchanged — loud only."""
    import sys
    print(f"  ⚠ [hitter_boom_stack.{section}] suppressed {type(exc).__name__}: {exc}", file=sys.stderr)

# Expected boom/bust by stack (from hitter validation report, 2026-06-03).
# stack=4 is EXTRAPOLATED — no direct cell exists in the validation panel
# because lineup_amp was not part of the original 3-component stack. We
# anchor stack=4 to two sources from `hitter_lineup_correlation.md`:
#   (a) the heatmap cell own_stack=2 + 3+ teammates_stack2 = 32.5% boom rate
#       (n=268) — the closest analog to "own stack lit + lineup amp"
#   (b) team-level lineup_stack2=3+ team-day boom rate = 33.8% (n=396)
# We adopt 34.0% (≈mean of 32.5 and 33.8 rounded) as the extrapolated boom
# rate for stack=4 and 35.0% for bust (interpolating the stack 0→3 trend
# of ~−2 pp per step, from 37.5% at stack=3 → 35.0% at stack=4). mean_fp
# extrapolated linearly from the 0→3 slope (+0.15/step).
#
# SB note (2026-06-28): these rates are on the no-SB fp_proxy (TB+BB+HBP-K). The live
# components below are now SB-AWARE (_load_batter_games_2026 joins boxscore SB). Using
# the new multi-year store, the SB-inclusive boom rate was MEASURED on the same 245k
# panel (scripts/_oneoff/rederive_hitter_sb.py): a UNIFORM +1.3pp at every stack
# (0: 23.9→25.2, 3: 30.6→32.1) that PRESERVES the stack 0→3 EDGE (+6.7→+6.9pp). Since
# the edge is what boom_stack discriminates on and the shift is uniform + sub-2pp, the
# tables are LEFT as-is (the displayed absolute boom% runs ~1.3pp light for speedsters
# whose SB lifts FP — documented, not a discrimination error). Re-derive on 2023+ SB-
# inclusive FP if an exact absolute rate is ever needed. See boom_bust_cutoff_recalibration_2026-06-28.md.
BOOM_RATE_BY_STACK = {0: 0.239, 1: 0.256, 2: 0.275, 3: 0.306, 4: 0.340}
BUST_RATE_BY_STACK = {0: 0.434, 1: 0.407, 2: 0.402, 3: 0.375, 4: 0.350}
MEAN_FP_PROXY_BY_STACK = {0: 1.12, 1: 1.27, 2: 1.35, 3: 1.58, 4: 1.73}

# Event sets (mirror analyze_hitter_boom_bust.py)
K_EVENTS = {'strikeout', 'strikeout_double_play', 'strikeout_triple_play'}
BB_EVENTS = {'walk', 'intent_walk'}
HBP_EVENTS = {'hit_by_pitch'}
H_EVENTS = {'single', 'double', 'triple', 'home_run'}
TB_MAP = {'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}
PA_EVENTS = K_EVENTS | BB_EVENTS | HBP_EVENTS | H_EVENTS | {
    'field_out', 'force_out', 'grounded_into_double_play', 'sac_fly',
    'field_error', 'sac_bunt', 'fielders_choice', 'double_play',
    'truncated_pa', 'fielders_choice_out', 'catcher_interf',
    'sac_fly_double_play', 'triple_play',
}

# Minimum games for stable season comparator before flagging skill/recform.
MIN_PRIOR_GAMES = 20


# ---------------------------------------------------------------------------
# Cached helpers
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)

def _today_et():
    """Date in America/New_York (audit 2026-07-04): the hourly UTC runner made
    date.today() flip to TOMORROW during 8pm-2am ET games — Sunday-night builds
    computed NEXT week's matchup mid-game and excluded tonight's games."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo('America/New_York')).date()


def _load_batter_games_2026() -> pd.DataFrame:
    """Per-(batter, game) panel for 2026 — same construction as
    analyze_hitter_boom_bust.py (one row per PA, aggregated to game).

    Columns: batter, game_pk, game_date, PA, K, BB, HBP, TB, fp_proxy, xwoba_pg.
    """
    cols = ['game_pk', 'game_date', 'batter', 'events',
            'estimated_woba_using_speedangle', 'at_bat_number']
    df = pd.read_parquet(_STATCAST_2026, columns=cols)
    df['game_date'] = pd.to_datetime(df['game_date'])
    df = df[df['events'].notna() & df['events'].isin(PA_EVENTS)].copy()
    # one row per PA — events column only fires on the terminal pitch
    df = df.drop_duplicates(subset=['game_pk', 'at_bat_number'], keep='last')

    df['K'] = df['events'].isin(K_EVENTS).astype(int)
    df['BB'] = df['events'].isin(BB_EVENTS).astype(int)
    df['HBP'] = df['events'].isin(HBP_EVENTS).astype(int)
    df['TB'] = df['events'].map(TB_MAP).fillna(0).astype(int)
    df['xwoba'] = df['estimated_woba_using_speedangle']

    g = df.groupby(['batter', 'game_pk', 'game_date']).agg(
        PA=('events', 'size'),
        K=('K', 'sum'),
        BB=('BB', 'sum'),
        HBP=('HBP', 'sum'),
        TB=('TB', 'sum'),
        xwoba_sum=('xwoba', 'sum'),
        xwoba_n=('xwoba', 'count'),
    ).reset_index()
    # SB is a base-running event (not in pitch-level statcast), so it is joined from
    # the boxscore (mlbam-keyed) to close the SB gap: fp_proxy now matches the full
    # BrownU hitter scoring (R/RBI still absent — game-level, not modeled here).
    # This makes the recform_hot component catch SB-DRIVEN recent form (a speedster on
    # a stealing tear); for stable-SB hitters the SB term cancels in the L10-vs-season
    # delta, so it is a no-op there. Display/context tag (CLAUDE.md #13). NOTE: the
    # historical BOOM_RATE_BY_STACK outcome tables remain calibrated on the no-SB
    # fp_proxy (245k panel, 2018-25 — no multi-year per-game SB to re-derive); the
    # resulting bias is small (SB is ~2.4% of median hitter FP) and concentrated in
    # speedsters. See boom_bust_cutoff_recalibration_2026-06-28.md (SB-gap note).
    try:
        _box = pd.read_parquet(_BOXSCORE_H, columns=['mlbam_id', 'game_pk', 'sb'])
        # cast BOTH merge keys to int64 — a dtype mismatch (object vs int after parquet
        # round-trip) would silently yield all-NaN -> fillna(0) -> the SB gap re-opens
        # with NO error. Cast guards against that.
        _box['mlbam_id'] = _box['mlbam_id'].astype('int64')
        _box['game_pk'] = _box['game_pk'].astype('int64')
        g['batter'] = g['batter'].astype('int64')
        g['game_pk'] = g['game_pk'].astype('int64')
        _sb = _box.groupby(['mlbam_id', 'game_pk'])['sb'].sum()
        g = g.merge(_sb.rename('SB'), left_on=['batter', 'game_pk'], right_index=True, how='left')
        g['SB'] = g['SB'].fillna(0).astype(int)
        if g['SB'].sum() == 0:  # file read OK but 0 matched => key bug, not a real 0; surface it
            import warnings
            warnings.warn("hitter_boom_stack: SB merge matched 0 rows — possible key dtype mismatch")
    except Exception:
        g['SB'] = 0  # boxscore absent (legit fallback) -> components fall back to no-SB fp_proxy
    g['fp_proxy'] = g['TB'] + g['BB'] + g['HBP'] + g['SB'] - g['K']
    g['xwoba_pg'] = g['xwoba_sum'] / g['xwoba_n'].replace(0, np.nan)
    g['batter'] = g['batter'].astype('int64')
    g = g.sort_values(['batter', 'game_date']).reset_index(drop=True)
    return g


@lru_cache(maxsize=1)
def _load_soft_sp_tertile() -> tuple[float, dict]:
    """Return (33rd-percentile xfp_rp3_per_start, {pitcher_id: rp3_per_start}).

    Soft opp for hitter = WEAK SP (low rp3 projection). Bottom tertile.
    """
    df = pd.read_csv(_RP3_PROJ)
    proj = df['xfp_rp3_per_start'].dropna()
    p33 = float(np.percentile(proj.values, 100.0 / 3.0))
    by_pid = {}
    for _, r in df.iterrows():
        pid = r.get('pitcher')
        v = r.get('xfp_rp3_per_start')
        try:
            if pd.notna(pid) and pd.notna(v):
                by_pid[int(pid)] = float(v)
        except (TypeError, ValueError):
            continue
    return p33, by_pid


# ---------------------------------------------------------------------------
# Component computations
# ---------------------------------------------------------------------------
def _component_skill_spike_hitter(batter_id: int, today: date) -> tuple[int, dict]:
    """Component 1: last-10g xwOBA - season xwOBA >= +0.040 AND last-10g K% -
    season K% <= -3 pp. Requires >= MIN_PRIOR_GAMES of season data.
    """
    games = _load_batter_games_2026()
    my = games[games['batter'] == int(batter_id)].copy()
    detail = {'n_games_2026': int(len(my)), 'reason': None}
    # Only count games strictly before `today` to mirror leakage-safe construction
    my = my[my['game_date'].dt.date < today]
    if len(my) < MIN_PRIOR_GAMES:
        detail['reason'] = 'insufficient_games'
        return 0, detail
    season_pa = int(my['PA'].sum())
    season_k_pct = float(my['K'].sum() / max(season_pa, 1))
    # weighted xwoba by PA (xwoba_pg already a per-PA average; PA-weight it)
    valid_xw = my[my['xwoba_pg'].notna()]
    if len(valid_xw) == 0:
        detail['reason'] = 'no_xwoba'
        return 0, detail
    season_xwoba = float(
        (valid_xw['xwoba_pg'] * valid_xw['PA']).sum()
        / max(valid_xw['PA'].sum(), 1)
    )
    last10 = my.tail(10)
    l10_pa = int(last10['PA'].sum())
    if l10_pa == 0:
        detail['reason'] = 'l10_no_pa'
        return 0, detail
    l10_k_pct = float(last10['K'].sum() / max(l10_pa, 1))
    l10_valid = last10[last10['xwoba_pg'].notna()]
    if l10_valid['PA'].sum() == 0:
        detail['reason'] = 'l10_no_xwoba'
        return 0, detail
    l10_xwoba = float(
        (l10_valid['xwoba_pg'] * l10_valid['PA']).sum()
        / max(l10_valid['PA'].sum(), 1)
    )
    dxw = l10_xwoba - season_xwoba
    dK_pp = (l10_k_pct - season_k_pct) * 100.0
    detail.update({
        'season_xwoba': season_xwoba,
        'season_k_pct': season_k_pct,
        'last10_xwoba': l10_xwoba,
        'last10_k_pct': l10_k_pct,
        'delta_xwoba': dxw,
        'delta_k_pp': dK_pp,
    })
    fired = int((dxw >= 0.040) and (dK_pp <= -3.0))
    return fired, detail


def _component_recform_hot_hitter(batter_id: int, today: date) -> tuple[int, dict]:
    """Component 2: last-10g fp_proxy/g - season fp_proxy/g >= +1.5.
    Uses fp_proxy (TB + BB + HBP - K) — the SAME unit as the validation panel.
    """
    games = _load_batter_games_2026()
    my = games[games['batter'] == int(batter_id)].copy()
    detail = {'n_games_2026': int(len(my)), 'reason': None}
    my = my[my['game_date'].dt.date < today]
    if len(my) < MIN_PRIOR_GAMES:
        detail['reason'] = 'insufficient_games'
        return 0, detail
    season_fp = float(my['fp_proxy'].mean())
    last10 = my.tail(10)
    if len(last10) < 5:
        detail['reason'] = 'l10_too_few'
        return 0, detail
    l10_fp = float(last10['fp_proxy'].mean())
    delta = l10_fp - season_fp
    detail.update({
        'season_fp_proxy_per_g': season_fp,
        'last10_fp_proxy_per_g': l10_fp,
        'delta': delta,
    })
    fired = int(delta >= 1.5)
    return fired, detail


def _component_opp_soft_hitter(opp_sp_id: Optional[int]) -> tuple[int, dict]:
    """Component 3: opposing SP's xfp_rp3_per_start in BOTTOM tertile (weak SP)."""
    detail = {'opp_sp_id': opp_sp_id}
    if opp_sp_id is None:
        detail['reason'] = 'no_opp_sp'
        return 0, detail
    p33, by_pid = _load_soft_sp_tertile()
    detail['soft_p33_threshold'] = p33
    try:
        opp_sp_id = int(opp_sp_id)
    except (TypeError, ValueError):
        detail['reason'] = 'opp_sp_id_not_int'
        return 0, detail
    if opp_sp_id not in by_pid:
        detail['reason'] = 'opp_sp_not_in_rp3'
        return 0, detail
    opp_proj = by_pid[opp_sp_id]
    detail['opp_sp_rp3_per_start'] = opp_proj
    fired = int(opp_proj <= p33)
    return fired, detail


# ---------------------------------------------------------------------------
# Component 4 — lineup_amp_hitter
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_rh3_team_map() -> pd.DataFrame:
    """Load batter→team→rh3_per_game from the rh3 projections CSV.

    Used to (a) look up a hitter's team and (b) enumerate the team's TOP
    9 BY rh3 as the fallback expected-starters set when the MLB Stats
    API lineup isn't posted yet.
    """
    cols = ['batter', 'team', 'xfp_rh3_per_game', 'primary_position']
    df = pd.read_csv(_RH3_PROJ, usecols=cols)
    df = df.dropna(subset=['batter', 'team'])
    df['batter'] = df['batter'].astype('int64')
    return df


@lru_cache(maxsize=1)
def _todays_team_to_lineup(today_iso: str) -> dict[str, list[int]]:
    """Map MLB team abbrev -> list of confirmed-lineup batter MLBAM ids.

    Single MLB Stats API call per script invocation. Returns empty dict
    on failure or when no lineups are posted yet — caller will fall back
    to top-9-by-rh3.
    """
    try:
        import json
        import urllib.request
        url = (f'https://statsapi.mlb.com/api/v1/schedule?sportId=1'
               f'&startDate={today_iso}&endDate={today_iso}'
               f'&hydrate=lineups,team')
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        _warn("lineups_fetch", e)
        return {}
    out: dict[str, list[int]] = {}
    for d_block in data.get('dates', []):
        for g in d_block.get('games', []):
            lineups = g.get('lineups') or {}
            for side, team_key in (('homePlayers', 'home'), ('awayPlayers', 'away')):
                players = lineups.get(side) or []
                if not players:
                    continue
                team_block = g.get('teams', {}).get(team_key, {}).get('team', {}) or {}
                abbr = (team_block.get('abbreviation') or '').upper()
                if not abbr:
                    continue
                ids = []
                for p in players:
                    pid = p.get('id')
                    if pid is not None:
                        try:
                            ids.append(int(pid))
                        except (TypeError, ValueError):
                            continue
                if ids:
                    out[abbr] = ids
    return out


def _resolve_team_expected_lineup(team: Optional[str],
                                   today: date) -> list[int]:
    """Return list of MLBAM batter ids expected to start for `team` today.

    Strategy: prefer confirmed MLB Stats API lineup; fall back to TOP 9
    BY rh3 in xfp_rh3_projections.csv. Returns [] on failure.
    """
    if not team or not isinstance(team, str):
        return []
    sched = _todays_team_to_lineup(today.isoformat())
    norm = _TEAM_ABBR_MAP.get(team.upper(), team.upper())
    confirmed = sched.get(norm) or sched.get(team.upper())
    if confirmed:
        return list(confirmed)
    # Fallback: top 9 by rh3 for the team
    try:
        rh3 = _load_rh3_team_map()
        candidates = rh3[rh3['team'].str.upper() == team.upper()]
        if len(candidates) == 0 and norm != team.upper():
            candidates = rh3[rh3['team'].str.upper() == norm]
        if len(candidates) == 0:
            return []
        top9 = candidates.nlargest(9, 'xfp_rh3_per_game')
        return [int(x) for x in top9['batter'].tolist()]
    except Exception as e:
        _warn("proj_top9", e)
        return []


def _lookup_team_for_batter(batter_id: int) -> Optional[str]:
    """Quick reverse-lookup: batter MLBAM id → team abbrev from rh3 csv."""
    try:
        rh3 = _load_rh3_team_map()
        row = rh3[rh3['batter'] == int(batter_id)]
        if len(row) == 0:
            return None
        t = row.iloc[0]['team']
        return str(t) if isinstance(t, str) else None
    except Exception as e:
        _warn("team_for_batter", e)
        return None


def _component_lineup_amp_hitter(
    batter_id: int,
    own_components_total: int,
    team: Optional[str],
    today: date,
) -> tuple[int, dict]:
    """Component 4: own boom_stack(c1+c2+c3) >= 1 AND >= 2 OTHER teammates
    in today's expected lineup ALSO have boom_stack(c1+c2+c3) >= 1.

    Recursive guard: teammate stacks are computed with skip_lineup_amp=True
    so this component never recurses on itself.
    """
    detail = {'team': team, 'own_components_total': own_components_total}
    if own_components_total < 1:
        detail['reason'] = 'own_stack_lt_1'
        return 0, detail
    lineup = _resolve_team_expected_lineup(team, today)
    if not lineup:
        detail['reason'] = 'no_lineup_or_team'
        return 0, detail
    # Resolve today's opp_sp once for this team (same for whole lineup)
    opp_sp_id_team = resolve_opp_sp_id_for_today(team, today)
    n_teammates_lit = 0
    teammates_checked = 0
    for tid in lineup:
        if int(tid) == int(batter_id):
            continue
        teammates_checked += 1
        try:
            sub = compute_hitter_boom_stack(
                batter_id=int(tid),
                opp_sp_id=opp_sp_id_team,
                today=today,
                skip_lineup_amp=True,
            )
            if sub.get('boom_stack', 0) >= 1:
                n_teammates_lit += 1
        except Exception as e:
            _warn(f"lineup_amp.teammate_{tid}", e)
            continue
    detail.update({
        'teammates_checked': teammates_checked,
        'n_teammates_lit': n_teammates_lit,
        'lineup_source': 'confirmed_or_top9',
    })
    fired = int(n_teammates_lit >= 2)
    return fired, detail


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def compute_hitter_boom_stack(
    batter_id: int,
    opp_sp_id: Optional[int],
    today: Optional[date] = None,
    skip_lineup_amp: bool = False,
    team: Optional[str] = None,
) -> dict:
    """Compute hitter boom_stack for a single batter at `today`.

    Args:
        batter_id: MLBAM batter id
        opp_sp_id: MLBAM pitcher id of today's opposing starter (None if no
            confirmed probable yet — component 3 will be 0 with reason set)
        today: optional override; defaults to _today_et()

    Returns:
        {
          'boom_stack': int 0-3,
          'components': {'skill_spike_hitter': 0|1, 'recform_hot_hitter': 0|1,
                          'opp_soft_hitter': 0|1},
          'detail': {...per-component diagnostics...},
          'boom_rate_expected': float,
          'bust_rate_expected': float,
          'mean_fp_proxy_expected': float,
        }
    """
    if today is None:
        today = _today_et()
    c1, d1 = _component_skill_spike_hitter(batter_id, today)
    c2, d2 = _component_recform_hot_hitter(batter_id, today)
    c3, d3 = _component_opp_soft_hitter(opp_sp_id)
    own_3comp = int(c1 + c2 + c3)
    if skip_lineup_amp:
        # Recursive guard path: teammates' contributions for component 4
        # use ONLY components 1-3. Return a 3-component stack capped at 3.
        return {
            'boom_stack': own_3comp,
            'components': {
                'skill_spike_hitter': c1,
                'recform_hot_hitter': c2,
                'opp_soft_hitter': c3,
                'lineup_amp_hitter': 0,
            },
            'detail': {
                'skill_spike_hitter': d1,
                'recform_hot_hitter': d2,
                'opp_soft_hitter': d3,
                'lineup_amp_hitter': {'reason': 'skipped_for_recursion_guard'},
            },
            'boom_rate_expected': BOOM_RATE_BY_STACK[own_3comp],
            'bust_rate_expected': BUST_RATE_BY_STACK[own_3comp],
            'mean_fp_proxy_expected': MEAN_FP_PROXY_BY_STACK[own_3comp],
        }
    # Top-level (non-recursive) path: compute component 4 from teammates.
    team_used = team or _lookup_team_for_batter(batter_id)
    c4, d4 = _component_lineup_amp_hitter(
        batter_id=int(batter_id),
        own_components_total=own_3comp,
        team=team_used,
        today=today,
    )
    total = int(c1 + c2 + c3 + c4)
    return {
        'boom_stack': total,
        'components': {
            'skill_spike_hitter': c1,
            'recform_hot_hitter': c2,
            'opp_soft_hitter': c3,
            'lineup_amp_hitter': c4,
        },
        'detail': {
            'skill_spike_hitter': d1,
            'recform_hot_hitter': d2,
            'opp_soft_hitter': d3,
            'lineup_amp_hitter': d4,
        },
        'boom_rate_expected': BOOM_RATE_BY_STACK[total],
        'bust_rate_expected': BUST_RATE_BY_STACK[total],
        'mean_fp_proxy_expected': MEAN_FP_PROXY_BY_STACK[total],
    }


# ---------------------------------------------------------------------------
# Today's opp-SP resolver (cached per-script invocation)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _todays_team_to_opp_sp(today_iso: str) -> dict[str, int]:
    """Map (hitter's MLB team abbrev) -> (opposing SP MLBAM id) for `today`.

    Single MLB Stats API call per script invocation. Returns empty dict on
    failure (defensive — caller will fall back to no opp SP).
    """
    try:
        import json
        import urllib.request
        url = (f'https://statsapi.mlb.com/api/v1/schedule?sportId=1'
               f'&startDate={today_iso}&endDate={today_iso}'
               f'&hydrate=probablePitcher,team')
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        _warn("probables_fetch", e)
        return {}
    result: dict[str, int] = {}
    for d_block in data.get('dates', []):
        for g in d_block.get('games', []):
            home = g.get('teams', {}).get('home', {})
            away = g.get('teams', {}).get('away', {})
            home_abbr = (home.get('team', {}) or {}).get('abbreviation', '').upper()
            away_abbr = (away.get('team', {}) or {}).get('abbreviation', '').upper()
            home_p = home.get('probablePitcher') or {}
            away_p = away.get('probablePitcher') or {}
            home_pid = home_p.get('id')
            away_pid = away_p.get('id')
            # Hitter team -> OPPOSING SP id
            if home_abbr and away_pid:
                result[home_abbr] = int(away_pid)
            if away_abbr and home_pid:
                result[away_abbr] = int(home_pid)
    return result


# Normalize ESPN/rh3 team strings to MLB Stats API abbrevs.
# (audit 2026-07-04: 'ATH'->'OAK' was backwards for 2026 — the StatsAPI uses
# ATH post-move, so Athletics hitters never matched a scheduled opponent and
# never received an opp-SP boom component.)
_TEAM_ABBR_MAP = {
    'AZ': 'AZ', 'ARI': 'AZ',
    'ATH': 'ATH', 'OAK': 'ATH',
    'CWS': 'CWS', 'CHW': 'CWS',
    'WSH': 'WSH', 'WAS': 'WSH',
    'SF': 'SF', 'SFG': 'SF',
    'SD': 'SD', 'SDP': 'SD',
    'TB': 'TB', 'TBR': 'TB',
    'KC': 'KC', 'KCR': 'KC',
}


def resolve_opp_sp_id_for_today(team: Optional[str], today: Optional[date] = None) -> Optional[int]:
    """Lookup today's opposing SP MLBAM id for a hitter from `team`.

    Returns None if the team isn't playing, the probable isn't confirmed,
    or the API call fails. The MLB Stats API uses canonical 3-letter
    abbreviations; we normalize a few common variants.
    """
    if not team or not isinstance(team, str):
        return None
    if today is None:
        today = _today_et()
    sched = _todays_team_to_opp_sp(today.isoformat())
    if not sched:
        return None
    norm = _TEAM_ABBR_MAP.get(team.upper(), team.upper())
    # Try normalized first, then raw
    return sched.get(norm) or sched.get(team.upper())

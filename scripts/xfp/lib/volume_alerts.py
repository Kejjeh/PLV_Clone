"""volume_alerts — turn the forward-volume models into a nightly WARNING.

WHAT THIS IS FOR
The volume models (xfp_volume / xfp_sp_volume / xfp_rp_volume, refresh steps
4.91-4.93) already ACCOUNT for playing-time change: pa_last21, lineup_spot_to,
il_stints_to, days_on_il_to and is_on_il_at_split are all features, which is
why they beat naive season pace by +0.074 Spearman (7/7 years). What was
missing was anything that TELLS you a role moved. `/volume-watch` is
on-demand, so a collapse only surfaced when someone thought to look —
2026-08-01 found Matt Chapman at ZERO PA in 21 days while rh3's naive
`expected_pa_remaining` still projected him at a full-time 3.20 PA/team-game.

WHY ROLE-LOSS DOES NOT USE THE MODEL GAP
The tempting trigger is `proj_ros_pa_per_teamgame - naive_pace`. It is wrong.
That gap carries league-wide shrinkage toward the mean (measured 2026-08-01:
mean -0.109, SD 0.604 across 792 rows), so on a normal night EVERY hitter on a
roster shows a negative gap. The same day's board listed all 12 of Josh's
healthy hitters as "faders" while they sat at the 74th-97th volume percentile
and none had lost a start. Keying on that would make the alert pure noise, and
a noisy alert is worse than none — it trains you to ignore the line.

So:
  ROLE_LOSS  <- RECENT vs SEASON pace (pa_last21 / team games in that window).
                Shrinkage cannot manufacture this; only a real bench/injury can.
  ROLE_GAIN  <- the model gap IS admissible here, because shrinkage points
                DOWN: a large positive gap is signal against the prior, not
                with it. Still requires playing-time CONFIRMATION so a callup
                with a tiny denominator cannot fire it.

Rule 13: display/decision layer. Nothing here moves rh3/rp3/rprs2.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from plv_clone.utils.name_match import safe_name_key as _safe_name_key
from scripts.xfp.lib.bucket_dispatch import _flip_lastfirst

ROLE_LOSS = 'ROLE_LOSS'
ROLE_GAIN = 'ROLE_GAIN'
IL_ZERO = 'IL_ZERO'


@dataclass(frozen=True)
class SideSpec:
    """Per-bucket columns + gates. Gates differ by an order of magnitude AND
    by noisiness, so they cannot be shared: a 21-day window holds ~65 PA for a
    hitter but only ~3-4 starts for an SP, where one skipped turn is a 25%
    swing that means nothing.
    """
    side: str
    proj_col: str
    season_col: str
    last21_col: str
    unit: str
    min_season: float
    loss_ratio: float
    loss_min_abs: float
    gain_min_gap: float
    gain_min_recent: float


# ── gates, CALIBRATED against live 2026-08-01 distributions ─────────────────
# Method (identical for all three): find where healthy REGULARS actually sit,
# then set the ratio gate below their 10th percentile and the absolute gate
# above their 90th-percentile drop, so a normal week cannot fire while every
# IL-flagged case clears comfortably.
#
#   H   healthy everyday bats sit at 0.95-1.00 of season pace. The first cut
#       of 0.70 silently dropped Cody Bellinger (3.954 -> 2.786, a whole
#       lineup spot of work) by 0.018 -> 0.75.
#   SP  healthy regulars ratio p05 0.53 / p10 0.73 / p25 0.94, abs drop p90
#       0.050 / p95 0.061; IL-flagged median ratio 0.00, median drop 0.072.
#       One skipped turn is ratio ~0.86 and must stay silent -> 0.60 / 0.060.
#   RP  healthy regulars ratio p05 0.23 / p10 0.71 / p25 0.91, abs drop p90
#       0.109 / p95 0.245; IL-flagged median ratio 0.00, median drop 0.164.
#       Bullpen usage is the lumpiest of the three -> 0.55 / 0.120.
#
# Both edges of every gate are pinned by tests.
SIDES: dict[str, SideSpec] = {
    'H': SideSpec(
        side='H', proj_col='proj_ros_pa_per_teamgame',
        season_col='pa_per_teamgame_to', last21_col='pa_last21', unit='PA',
        min_season=2.00, loss_ratio=0.75, loss_min_abs=0.80,
        gain_min_gap=1.00, gain_min_recent=2.50),
    'SP': SideSpec(
        side='SP', proj_col='proj_ros_gs_per_teamgame',
        season_col='gs_per_teamgame_to', last21_col='gs_last21', unit='GS',
        min_season=0.100, loss_ratio=0.60, loss_min_abs=0.060,
        gain_min_gap=0.050, gain_min_recent=0.150),
    'RP': SideSpec(
        side='RP', proj_col='proj_ros_g_per_teamgame',
        season_col='g_per_teamgame_to', last21_col='g_last21', unit='G',
        min_season=0.180, loss_ratio=0.55, loss_min_abs=0.120,
        gain_min_gap=0.080, gain_min_recent=0.250),
}

# Back-compat aliases (hitter gates) for any caller importing the flat names.
MIN_SEASON_PACE = SIDES['H'].min_season
LOSS_RATIO = SIDES['H'].loss_ratio
LOSS_MIN_ABS = SIDES['H'].loss_min_abs
GAIN_MIN_GAP = SIDES['H'].gain_min_gap
GAIN_MIN_RECENT = SIDES['H'].gain_min_recent


def is_new_signal(prior, key: str, signal: str) -> bool:
    """Did this signal CHANGE since the last recorded run?

    An alert must fire on the transition, not every night for six weeks
    afterwards — that is precisely the Judge case ("IL_ZERO since June" is not
    tonight's news) and it applies equally to a benching that persists.

    prior is None => no history exists for this side yet. Bootstrap by
    recording state and alerting NOTHING: the alternative is every IL'd and
    benched player paging at once on night one, which would discredit the
    whole line before it ever carried real news.
    """
    if prior is None:
        return False
    return prior.get(key) != signal


def recent_pace(pa_last21, team_games_l21):
    """PA per team-game over the trailing window, or None when unknowable.

    None (never 0.0) when the team-game count is missing or zero: dividing by
    it would render an entire league as collapsed on any night the schedule
    join breaks, which is the most dangerous failure mode for a step whose
    whole job is to email a warning.
    """
    if pa_last21 is None or team_games_l21 is None:
        return None
    try:
        pa = float(pa_last21)
        tg = float(team_games_l21)
    except (TypeError, ValueError):
        return None
    if pd.isna(pa) or pd.isna(tg) or tg <= 0:
        return None
    return pa / tg


def _key(name) -> str:
    """Canonical join key, accent- AND 'Last, First'-safe.

    REGRESSION GUARD (caught live 2026-08-01): the SP volume CSV writes
    'Sánchez, Cristopher' / 'Soriano, José' while the ESPN roster says
    'Jose Soriano'. A plain lower().strip() matched ZERO of 29 roster names,
    so the whole SP side produced no rows, raised nothing, and would have
    reported a permanent all-clear however many starts an owned arm lost.
    Flip the comma form first, then use the repo's accent-stripping
    safe_name_key so both spellings land on 'jose soriano'.
    """
    return _safe_name_key(_flip_lastfirst(str(name).strip()))


def classify(*, season_pace, recent, model_gap, on_il, is_owned, is_fa,
             spec: SideSpec | None = None):
    """-> (signal, severity) or (None, 0.0). Pure; no IO, no frame."""
    spec = spec or SIDES['H']
    if recent is None:
        return None, 0.0

    if is_owned:
        if season_pace is None or pd.isna(season_pace):
            return None, 0.0
        if season_pace < spec.min_season:
            return None, 0.0
        drop = season_pace - recent
        if drop >= spec.loss_min_abs and recent <= spec.loss_ratio * season_pace:
            # An IL'd player's zero is KNOWN, not news — label it so it can be
            # reported separately without masquerading as a fresh benching.
            return (IL_ZERO if on_il else ROLE_LOSS), float(drop)
        return None, 0.0

    if is_fa:
        if model_gap is None or pd.isna(model_gap):
            return None, 0.0
        if model_gap >= spec.gain_min_gap and recent >= spec.gain_min_recent:
            return ROLE_GAIN, float(model_gap)
    return None, 0.0


def build_alert_rows(vol_df: pd.DataFrame, *, team_games_l21: dict,
                     owned: set, fa: set, side: str = 'H',
                     prior=None) -> pd.DataFrame:
    """Classify one volume frame into alert rows, severity-sorted.

    side selects the SideSpec ('H' | 'SP' | 'RP'); the frame must carry that
    spec's columns plus player_name, team, naive_pace and is_on_il_at_split.
    team_games_l21 maps team code -> games that club played in the window.
    prior maps player key -> last run's signal (None on a bootstrap run); it
    only stamps `is_new` and never suppresses a row, so the CSV always shows
    the full current state while the marker can fire on transitions alone.
    """
    spec = SIDES[side]
    cols = ['player_name', 'team', 'side', 'signal', 'is_new', 'severity',
            'season_pace', 'recent_pace', 'events_last21', 'unit', 'proj_vol',
            'naive_pace', 'model_gap']
    if vol_df is None or not len(vol_df):
        return pd.DataFrame(columns=cols)

    owned = {_key(o) for o in (owned or set())}
    fa = {_key(f) for f in (fa or set())}
    out = []
    for _, r in vol_df.iterrows():
        nm = r.get('player_name')
        k = _key(nm)
        is_owned, is_fa = k in owned, k in fa
        if not (is_owned or is_fa):
            continue
        season = r.get('naive_pace')
        if season is None or pd.isna(season):
            season = r.get(spec.season_col)
        proj = r.get(spec.proj_col)
        # Per-row games-in-window wins over the team-CODE map: 20 of 272 rows
        # in the SP volume CSV carry team = NaN, and a code lookup can never
        # resolve those. The runner supplies this column per PLAYER via mlbam.
        tg_row = r.get('team_games_l21')
        if tg_row is None or pd.isna(tg_row):
            tg_row = team_games_l21.get(r.get('team'))
        rec = recent_pace(r.get(spec.last21_col), tg_row)
        gap = (None if (proj is None or pd.isna(proj)
                        or season is None or pd.isna(season))
               else float(proj) - float(season))
        sig, sev = classify(
            season_pace=season, recent=rec, model_gap=gap,
            on_il=bool(r.get('is_on_il_at_split')),
            is_owned=is_owned, is_fa=is_fa, spec=spec)
        if not sig:
            continue
        out.append(dict(player_name=nm, team=r.get('team'), side=spec.side,
                        signal=sig, is_new=is_new_signal(prior, k, sig),
                        severity=round(sev, 3), season_pace=season,
                        recent_pace=rec,
                        events_last21=r.get(spec.last21_col),
                        unit=spec.unit, proj_vol=proj, naive_pace=season,
                        model_gap=gap))
    if not out:
        return pd.DataFrame(columns=cols)
    return (pd.DataFrame(out)
            .sort_values('severity', ascending=False)
            .reset_index(drop=True))

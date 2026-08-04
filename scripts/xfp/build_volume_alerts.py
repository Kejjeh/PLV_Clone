"""build_volume_alerts — nightly playing-time WARNING (refresh step 4.945).

Reads all three validated volume projections (steps 4.91/4.92/4.93 — hitter,
SP, RP) and flags:
  ROLE_LOSS  a player Josh OWNS whose recent pace has collapsed vs his season
             pace (the Matt-Chapman case: 0 PA in 21 days while naive season
             pace still said 3.20 PA/team-game)
  IL_ZERO    same shape, but the player is flagged IL — known, not news
  ROLE_GAIN  a FREE AGENT whose model volume runs materially above naive pace
             AND who is confirmed to be playing now (the Jasson-Dominguez /
             Wyatt-Langford case: 1.84 -> 3.09 PA/team-game)

Each side carries its own calibrated gates (see SIDES in lib/volume_alerts.py):
a 21-day window holds ~65 PA for a hitter but only ~3-4 starts for an SP, so
one skipped turn is a 25% swing that must stay silent.

FRESHNESS: every row is stamped is_new against the previous run, recorded in
data/research/volume_alert_history.parquet. Only a TRANSITION marks the commit
— "Judge has been IL since June" is not tonight's news, and a benching that
persists for six weeks must not re-page for six weeks. A side with no history
bootstraps silently (records state, alerts nothing).

Classification logic + its rationale live in lib/volume_alerts.py; this module
is the IO shell (CSV read, team-game derivation, live ownership, CSV write).

NON-GATING BY CONSTRUCTION: every failure path prints and exits 0. This step
must never be the reason a 140-minute refresh loses a day of data. It writes
data/outputs/volume_alerts.csv, which the daily-refresh workflow reads to
prepend an ALERT[] marker to the commit message.

KNOWN LIMIT: an RP who keeps his appearance count but LOSES the save role
(closer -> middle relief) is invisible here — volume is unchanged. That role
change lives in rprs2's gf_pct_to / sv_per_g_to, not in this surface.

Rule 13: display/decision layer — never moves rh3/rp3/rprs2.
"""
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, '.')

import pandas as pd  # noqa: E402

from scripts.xfp.lib.volume_alerts import (  # noqa: E402
    IL_ZERO, ROLE_GAIN, ROLE_LOSS, _key, build_alert_rows,
)

VOL_CSV = Path('data/outputs/xfp_volume_projections.csv')
SP_CSV = Path('data/outputs/xfp_sp_volume_projections.csv')
RP_CSV = Path('data/outputs/xfp_rp_volume_projections.csv')
BOX = Path('data/research/xfp_cache/boxscore_hitters.parquet')
BOX_P = Path('data/research/xfp_cache/boxscore_pitchers.parquet')
OUT_CSV = Path('data/outputs/volume_alerts.csv')
HIST = Path('data/research/volume_alert_history.parquet')
WINDOW_DAYS = 21

SIDE_SOURCES = [('H', VOL_CSV), ('SP', SP_CSV), ('RP', RP_CSV)]


def _load_prior(side: str):
    """Last recorded signal per player for this side, or None if no history.

    None is the BOOTSTRAP signal and is meaningfully different from an empty
    dict: it tells build_alert_rows to stamp everything is_new=False so the
    first run records state without paging about every long-standing IL stint.
    A side that has never been recorded bootstraps independently, so adding
    SP/RP later cannot flood the line either.
    """
    if not HIST.exists():
        return None
    try:
        h = pd.read_parquet(HIST)
    except Exception:                              # noqa: BLE001
        return None
    h = h[h['side'] == side]
    if not len(h):
        return None
    last = h['run_date'].max()
    cur = h[h['run_date'] == last]
    return dict(zip(cur['player_key'], cur['signal']))


def _append_history(rows: pd.DataFrame, run_date: str) -> None:
    """Atomic tmp+replace append, matching the persist_transactions idiom.

    player_key MUST come from lib.volume_alerts._key — the same accent- and
    'Last, First'-aware function the lookup uses. A naive lower() here (the
    first cut) meant every accented or comma-formatted name failed to match
    its own recorded state, so 12 rows re-reported as NEW every single night:
    a freshness check that is silently always-fresh is worse than none.
    """
    rec = pd.DataFrame({
        'run_date': run_date,
        'side': rows['side'],
        'player_key': rows['player_name'].map(_key),
        'player_name': rows['player_name'],
        'signal': rows['signal'],
    })
    if HIST.exists():
        try:
            old = pd.read_parquet(HIST)
            rec = pd.concat([old[old['run_date'] != run_date], rec],
                            ignore_index=True)
        except Exception as exc:                   # noqa: BLE001
            print(f'  volume-alerts: history unreadable ({exc}) — '
                  'starting a fresh panel')
    HIST.parent.mkdir(parents=True, exist_ok=True)
    tmp = HIST.with_suffix('.tmp.parquet')
    rec.to_parquet(tmp, index=False)
    tmp.replace(HIST)


def _team_games_l21(vol: pd.DataFrame) -> dict:
    """team code -> games that club played in the trailing window.

    Derived from the boxscore store's own team_id rather than any hardcoded
    abbreviation map: map each player's mlbam to his modal team_id over the
    season, count that club's distinct game dates in the window, then carry
    the count back to the volume CSV's team STRING via the modal team_id per
    code. Abbreviation drift therefore cannot silently zero a club (which
    would read as 'everyone benched').
    """
    # BOTH stores: boxscore_hitters carries no pitchers, so an mlbam-keyed map
    # built from it alone leaves every SP/RP unresolvable — which is exactly
    # how the 20 NaN-team SP rows stayed skipped on the first attempt.
    parts = []
    for p in (BOX, BOX_P):
        if p.exists():
            parts.append(pd.read_parquet(
                p, columns=['game_date', 'mlbam_id', 'team_id']))
    if not parts:
        raise FileNotFoundError(f'neither {BOX} nor {BOX_P} exists')
    box = pd.concat(parts, ignore_index=True)
    box['game_date'] = pd.to_datetime(box['game_date'])
    cutoff = box['game_date'].max() - pd.Timedelta(days=WINDOW_DAYS)
    win = box[box['game_date'] > cutoff]
    games_by_team = win.groupby('team_id')['game_date'].nunique().to_dict()

    modal = (box.groupby(['mlbam_id', 'team_id']).size()
                .reset_index(name='n')
                .sort_values('n', ascending=False)
                .drop_duplicates('mlbam_id')
                .set_index('mlbam_id')['team_id'].to_dict())
    v = vol[['mlbam_id', 'team']].dropna().copy()
    v['team_id'] = v['mlbam_id'].map(modal)
    pairs = (v.dropna(subset=['team_id']).groupby(['team', 'team_id']).size()
              .reset_index(name='n').sort_values('n', ascending=False)
              .drop_duplicates('team'))
    by_code = {r['team']: games_by_team.get(r['team_id'], 0)
               for _, r in pairs.iterrows()}
    by_mlbam = {m: games_by_team.get(t, 0) for m, t in modal.items()}
    return by_code, by_mlbam


def _attach_team_games(df: pd.DataFrame, by_code: dict, by_mlbam: dict):
    """Per-player games-in-window column + a visible unresolved count.

    Resolving via mlbam rather than the team STRING is what rescues the 20 of
    272 SP rows whose `team` is NaN (Hunter Greene among them). Those rows
    were fail-safe — recent_pace returns None, so they simply never alerted —
    but that is a permanent silent blind spot on 7% of the SP pool, which is
    exactly the shape of thing this whole step exists to stop.
    """
    if 'mlbam_id' in df.columns:
        df = df.copy()
        df['team_games_l21'] = df['mlbam_id'].map(by_mlbam)
        miss = df['team_games_l21'].isna() & df['team'].map(
            lambda t: t not in by_code)
        n_miss = int(miss.sum())
    else:
        df = df.copy()
        df['team_games_l21'] = None
        n_miss = 0
    return df, n_miss


def main() -> int:
    if not VOL_CSV.exists():
        print(f'  volume-alerts: {VOL_CSV} absent (step 4.91 did not run) — '
              'NOT an all-clear, no alerts computed')
        return 0
    vol = pd.read_csv(VOL_CSV)

    try:
        tg, tg_by_mlbam = _team_games_l21(vol)
    except Exception as exc:                       # noqa: BLE001
        print(f'  volume-alerts: team-game derivation failed ({exc}) — '
              'no alerts computed (NOT an all-clear)')
        return 0
    if not tg or max(tg.values(), default=0) == 0:
        print('  volume-alerts: no team games resolved in the window — '
              'no alerts computed (NOT an all-clear)')
        return 0

    try:
        from app.espn_connector import (get_free_agents,
                                        get_my_roster_with_injuries)
        owned = set(get_my_roster_with_injuries()['player_name'])
        fa = set(get_free_agents(size=2000)['player_name'])
    except Exception as exc:                       # noqa: BLE001
        print(f'  volume-alerts: ESPN ownership unavailable ({exc}) — '
              'no alerts computed (NOT an all-clear)')
        return 0

    frames = []
    for side, path in SIDE_SOURCES:
        if not path.exists():
            print(f'  volume-alerts: {path} absent — {side} side skipped '
                  '(NOT an all-clear)')
            continue
        try:
            df = pd.read_csv(path)
            df, n_miss = _attach_team_games(df, tg, tg_by_mlbam)
            if n_miss:
                print(f'  volume-alerts: {side} — {n_miss} row(s) could not '
                      'resolve games-in-window (skipped, NOT an all-clear)')
            frames.append(build_alert_rows(
                df, side=side, team_games_l21=tg, owned=owned, fa=fa,
                prior=_load_prior(side)))
        except Exception as exc:                   # noqa: BLE001
            print(f'  volume-alerts: {side} side failed ({exc}) — skipped '
                  '(NOT an all-clear)')
    rows = (pd.concat(frames, ignore_index=True) if frames
            else pd.DataFrame(columns=['player_name', 'side', 'signal',
                                       'is_new']))
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(OUT_CSV, index=False)

    run_date = pd.Timestamp.today().strftime('%Y-%m-%d')
    if len(rows):
        try:
            _append_history(rows, run_date)
        except Exception as exc:                   # noqa: BLE001
            print(f'  volume-alerts: history append failed ({exc}) — '
                  'tomorrow bootstraps again (non-gating)')

    def _n(sig, new_only=False):
        if not len(rows):
            return 0
        m = rows['signal'] == sig
        if new_only:
            m &= rows['is_new'].astype(bool)
        return int(m.sum())

    print('  volume-alerts: %d ROLE_LOSS (%d NEW), %d ROLE_GAIN (%d NEW), '
          '%d IL_ZERO (%d NEW) -> %s'
          % (_n(ROLE_LOSS), _n(ROLE_LOSS, True), _n(ROLE_GAIN),
             _n(ROLE_GAIN, True), _n(IL_ZERO), _n(IL_ZERO, True), OUT_CSV))
    for _, r in rows[rows['signal'] != ROLE_GAIN].head(15).iterrows():
        print('    %-3s %-9s %-24s %s season %.3f -> recent %.3f %s/tg '
              '(L21 %s, sev %.3f)'
              % (r['side'], r['signal'], r['player_name'],
                 'NEW ' if r['is_new'] else '    ', float(r['season_pace']),
                 float(r['recent_pace']), r['unit'], r['events_last21'],
                 r['severity']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

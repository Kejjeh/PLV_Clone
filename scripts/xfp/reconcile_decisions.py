"""reconcile_decisions — join EXECUTED transactions to the Delta-P(win) surface.

THE GAP THIS CLOSES
-------------------
Josh executes moves in the ESPN UI, not through this repo. So the two halves of a
decision live in different stores and never meet:

  data/research/transactions_history.parquet   WHAT he did
  data/research/dpwin_history.parquet          WHAT we thought each option was worth

Until they are joined there is no way to ask "was that the right call?", because
the alternative that was passed on is only recorded on the dpwin side.

WHAT IT DOES
------------
1. Reads Josh's ADD/DROP transactions in a recent window.
2. Collapses same-timestamp ADD+DROP pairs into a single ``swap``.
3. Stamps ``executed_at`` on any existing v3 record that matches.
4. For an executed move with NO logged decision, auto-creates a v3 record from
   the dpwin_history run that was current at the time, choosing as the REJECTED
   alternative the best *unexecuted* same-bucket candidate from that same run.

That last step is the one that makes the ledger usable at all: Josh is never going
to log a decision before clicking, so almost every record has to be reconstructed
after the fact. It is honest because both legs come from the surface as it existed
BEFORE the move — no hindsight enters.

THREE REALITIES OF THE ACTUAL DATA (each cost a rewrite of the first design)
----------------------------------------------------------------------------
* ``action_str`` values are ``FA ADDED`` / ``WAIVER ADDED`` / ``DROPPED`` — there
  is no bare ``ADDED``.
* ``mlbam_id`` is **mostly NaN** in this store. So an id join is the exception and
  a normalized-name join is the primary path. It uses ``safe_name_key`` (which
  collapses the curly-vs-straight apostrophe that already caused the O'Hearn
  mis-key) and REPORTS every name-only match, because a name join is exactly where
  a same-name collision would enter this pipeline.
* ``position`` is **empty-string for every live row** (all 410 as of 2026-07-30),
  so it can never determine the H/SP/RP bucket. The bucket is resolved instead
  from, in order: the attributed dpwin row's own ``add_bucket``/``drop_bucket``,
  the collision-safe id resolvers + projection-CSV classification, and
  projection-map name membership. When nothing yields a bucket the move is
  counted UNATTRIBUTABLE — a defaulted 'H' would grade a pitcher add against a
  hitter counterfactual on the hitter game log.

MATCHING PRECEDENCE, and why date proximity is only a fallback: ``source_run_id``
is exact when present. Otherwise the run is chosen as the LATEST run whose full
``generated_at`` timestamp precedes the transaction (C8, 2026-07-30) — a
same-day run generated AFTER the click can never grade it; when every run in
the window post-dates the transaction, the move is reported unattributed.

Runs nightly as refresh_dashboards.py step 0.65, immediately AFTER
persist_transactions.py (step 0.6) — fail-soft, non-gating. Unmatched executed
moves are printed loudly: a permanent reconciliation gap is a real cost, not a
rounding error.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

import pandas as pd

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))

from plv_clone.decisions.logger import (  # noqa: E402
    DECISIONS_ROOT, DecisionRecord, _atomic_write_json, build_executed_record,
    log_decision, is_executed_record,
)
from plv_clone.utils.name_match import (  # noqa: E402
    classify_pitcher_bucket, resolve_batter_id, resolve_pitcher_id,
    safe_name_key,
)
from scripts.xfp.lib import dpwin_history  # noqa: E402

TX_PARQUET = ROOT / 'data' / 'research' / 'transactions_history.parquet'
MY_TEAM = 'New York Ligers'

# Projection maps: membership is the third-line bucket source (SP wins the
# rp3 ∩ rprs2 overlap, matching classify_pitcher_bucket's canonical rule).
RP3_CSV = ROOT / 'data' / 'outputs' / 'xfp_rp3_projections.csv'
RPRS2_CSV = ROOT / 'data' / 'outputs' / 'xfp_rprs2_projections.csv'
RH3_CSV = ROOT / 'data' / 'outputs' / 'xfp_rh3_projections.csv'

ADD_ACTIONS = {'FA ADDED', 'WAIVER ADDED', 'ADDED'}
DROP_ACTIONS = {'DROPPED'}

# How far after a run a transaction may still be attributed to it. Two days
# covers "saw the board Monday, executed Tuesday" without reaching across a
# subsequent run.
ATTRIBUTION_DAYS = 2


def load_my_transactions(days: int = 30, path: Path | None = None) -> pd.DataFrame:
    p = Path(path) if path is not None else TX_PARQUET
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    df = df[df['team_name'] == MY_TEAM].copy()
    if df.empty:
        return df
    df['date'] = pd.to_datetime(df['date']).dt.date
    cutoff = date.today() - timedelta(days=days)
    df = df[df['date'] >= cutoff]
    df['kind'] = df['action_str'].map(
        lambda a: 'add' if str(a).upper() in ADD_ACTIONS
        else ('drop' if str(a).upper() in DROP_ACTIONS else None))
    unknown = df[df['kind'].isna()]['action_str'].unique().tolist()
    if unknown:
        # Loud rather than silently dropped: a new ESPN action string would
        # otherwise make moves vanish from the ledger without a trace.
        print(f'  WARN unrecognized action_str values skipped: {unknown} '
              f'— add them to ADD_ACTIONS/DROP_ACTIONS if they are real moves')
    return df[df['kind'].notna()].sort_values('ts_ms')


def collapse_swaps(tx: pd.DataFrame) -> list[dict]:
    """Group same-timestamp ADD+DROP into one ``swap`` event."""
    events: list[dict] = []
    if tx.empty:
        return events
    for ts, grp in tx.groupby('ts_ms', sort=True):
        adds = grp[grp['kind'] == 'add'].to_dict('records')
        drops = grp[grp['kind'] == 'drop'].to_dict('records')
        when = datetime.fromtimestamp(int(ts) / 1000.0)
        while adds or drops:
            a = adds.pop(0) if adds else None
            d = drops.pop(0) if drops else None
            events.append({
                'ts_ms': int(ts), 'when': when,
                'date': (a or d)['date'],
                'action': 'swap' if (a and d) else ('add' if a else 'drop'),
                'add': a, 'drop': d,
            })
    return events


def _bucket_from_dpwin_row(hist: pd.DataFrame, run_id: str | None,
                           name: str | None) -> str | None:
    """Bucket from the attributed run's own row for this player.

    The surface already classified every candidate it scored, so the matched
    dpwin row's ``add_bucket`` (or ``drop_bucket``) is the most authoritative
    source there is — the transactions store's ``position`` column is
    empty-string for every live row and must never be consulted.
    """
    if not run_id or not name or hist.empty:
        return None
    k = safe_name_key(name)
    sub = hist[hist['run_id'] == run_id]
    for name_col, bucket_col in (('add_name', 'add_bucket'),
                                 ('drop_name', 'drop_bucket')):
        if name_col not in sub.columns:
            continue
        hit = sub[sub[name_col].map(
            lambda n: pd.notna(n) and safe_name_key(n) == k)]
        if hit.empty:
            continue
        b = hit.iloc[0].get(bucket_col)
        if pd.notna(b) and str(b) in ('H', 'SP', 'RP'):
            return str(b)
    return None


def _bucket_via_resolver(name: str, team: str | None = None) -> str | None:
    """Collision-safe id resolution -> bucket.

    A pitcher id classifies SP/RP through the projection CSVs
    (classify_pitcher_bucket); a batter id is 'H'. A name that resolves as
    BOTH pitcher and batter is two-way ambiguity — refuse rather than guess.
    """
    try:
        pid = resolve_pitcher_id(name, team=team)
    except Exception as e:
        print(f'  WARN pitcher-id resolver failed for {name!r}: {e}')
        pid = None
    try:
        bid = resolve_batter_id(name, team=team)
    except Exception as e:
        print(f'  WARN batter-id resolver failed for {name!r}: {e}')
        bid = None
    p_bucket = None
    if pid is not None:
        try:
            p_bucket = classify_pitcher_bucket(
                pid, rp3_path=str(RP3_CSV), rprs2_path=str(RPRS2_CSV))
        except Exception as e:
            print(f'  WARN pitcher bucket classify failed for {name!r}: {e}')
    if p_bucket and bid is None:
        return p_bucket
    if bid is not None and pid is None:
        return 'H'
    return None


def _bucket_via_projection_maps(name: str) -> str | None:
    """Bucket by name membership in the rp3 / rprs2 / rh3 projection outputs.

    rp3 stores names as "Last, First" — flipped before keying. A name found in
    both a pitcher map and the hitter map is ambiguous -> None; SP wins the
    rp3/rprs2 overlap (mid-season SP-to-RP move, classify's canonical rule).
    """
    k = safe_name_key(name)
    hits: list[str] = []
    for path, col, bucket in ((RP3_CSV, 'player_name', 'SP'),
                              (RPRS2_CSV, 'name_api', 'RP'),
                              (RH3_CSV, 'player_name', 'H')):
        p = Path(path)
        if not p.exists():
            continue
        try:
            names = pd.read_csv(p, usecols=[col])[col].dropna()
        except Exception as e:
            print(f'  WARN could not read projection map {p.name}: {e}')
            continue
        keys = set()
        for n in names:
            n = str(n)
            if ',' in n:
                last, _, first = n.partition(',')
                n = f'{first.strip()} {last.strip()}'
            keys.add(safe_name_key(n))
        if k in keys:
            hits.append(bucket)
    if not hits:
        return None
    if 'H' in hits and len(hits) > 1:
        return None
    return 'SP' if 'SP' in hits else hits[0]


def _resolve_bucket(hist: pd.DataFrame, run_id: str | None,
                    rec: dict | None) -> tuple[str | None, str]:
    """(bucket, source) for an executed move — never a silent 'H' default.

    Precedence: the attributed run's own row -> the collision-safe id
    resolvers -> projection-map name membership -> (None, 'unresolved').
    """
    name = (rec or {}).get('player_name')
    b = _bucket_from_dpwin_row(hist, run_id, name)
    if b:
        return b, 'dpwin_row'
    if name:
        b = _bucket_via_resolver(name, team=(rec or {}).get('pro_team'))
        if b:
            return b, 'resolver'
        b = _bucket_via_projection_maps(name)
        if b:
            return b, 'projection_map'
    # No source could bucket the player. Refusing is the honest outcome: a
    # defaulted 'H' would draw a hitter counterfactual and grade a pitcher on
    # the hitter game log.
    return None, 'unresolved'


def find_run(hist: pd.DataFrame, when: datetime | date) -> tuple[str | None, str]:
    """The latest dpwin run whose surface EXISTED at *when*.

    Eligibility is ``generated_at <= when`` (full timestamp — a 10:42 run can
    never explain a 09:00 click; hindsight must not enter the ledger), still
    bounded below by ATTRIBUTION_DAYS on snapshot_date. A date-only *when* is
    treated as end-of-day (the surface current as of that day).
    """
    if hist.empty:
        return None, 'no dpwin history'
    if isinstance(when, datetime):
        when_ts = when
    else:
        when_ts = datetime.combine(when, dtime.max)
    when_date = when_ts.date()
    lo = (when_date - timedelta(days=ATTRIBUTION_DAYS)).isoformat()
    sub = hist[(hist['snapshot_date'].astype(str) <= when_date.isoformat())
               & (hist['snapshot_date'].astype(str) >= lo)]
    if sub.empty:
        return None, (f'no dpwin run within {ATTRIBUTION_DAYS}d before '
                      f'{when_date} — move cannot be attributed to a surface')
    gen = pd.to_datetime(sub['generated_at'], errors='coerce')
    n_unparseable = int(gen.isna().sum())
    if n_unparseable:
        # Without a timestamp we cannot PROVE the surface preceded the move,
        # so such rows are ineligible — loud, never silent.
        print(f'  WARN {n_unparseable} dpwin row(s) in window have an '
              f'unparseable generated_at — excluded from attribution')
    eligible = sub[gen.notna() & (gen <= when_ts)]
    if eligible.empty:
        return None, (f'every dpwin run in the {ATTRIBUTION_DAYS}d window '
                      f'post-dates the {when_ts:%Y-%m-%d %H:%M} transaction — '
                      f'a surface that did not exist yet cannot have '
                      f'motivated the move')
    chosen = eligible.loc[gen[eligible.index].idxmax(), 'run_id']
    n_runs = eligible['run_id'].nunique()
    note = 'exact-day run' if n_runs == 1 else (
        f'{n_runs} candidate runs preceded the move, took latest ({chosen})')
    return str(chosen), note


def pick_rejected(hist: pd.DataFrame, run_id: str, bucket: str,
                  executed_name: str | None) -> dict | None:
    """Best *unexecuted* same-bucket ADD candidate from the same run.

    This is the counterfactual: what the surface said was the next-best option at
    the time. Excluding the executed player is the whole point — comparing a move
    to itself grades nothing.
    """
    sub = hist[(hist['run_id'] == run_id)
               & (hist['add_bucket'] == bucket)
               & (hist['add_name'].notna())]
    if sub.empty:
        return None
    if executed_name:
        k = safe_name_key(executed_name)
        sub = sub[sub['add_name'].map(lambda n: safe_name_key(n) != k)]
    if sub.empty:
        return None
    best = sub.sort_values('dpwin', ascending=False).iloc[0]
    return {'name': best['add_name'],
            'mlbam': (int(best['add_mlbam']) if best['add_mlbam'] else None),
            'bucket': best['add_bucket'],
            'dpwin': float(best['dpwin']) if pd.notna(best['dpwin']) else None,
            'dtitle_equity_pp': (float(best['dtitle_equity_pp'])
                                 if pd.notna(best.get('dtitle_equity_pp')) else None)}


def find_executed_dpwin(hist: pd.DataFrame, run_id: str, name: str) -> dict | None:
    """The surface's own dpwin for the move Josh actually made, if it was scored."""
    sub = hist[(hist['run_id'] == run_id) & (hist['add_name'].notna())]
    if sub.empty:
        return None
    k = safe_name_key(name)
    hit = sub[sub['add_name'].map(lambda n: safe_name_key(n) == k)]
    if hit.empty:
        return None
    r = hit.sort_values('dpwin', ascending=False).iloc[0]
    return {'dpwin': float(r['dpwin']) if pd.notna(r['dpwin']) else None,
            'regime': r.get('regime'),
            'base_pwin': (float(r['base_pwin']) if pd.notna(r.get('base_pwin'))
                          else None),
            'dtitle_equity_pp': (float(r['dtitle_equity_pp'])
                                 if pd.notna(r.get('dtitle_equity_pp')) else None)}


def stamp_open_records(*, name: str | None, mlbam: int | None, when: datetime,
                       root: Path | None = None, dry_run: bool = False,
                       window_days: int = ATTRIBUTION_DAYS,
                       action: str | None = None) -> list[Path]:
    """Stamp ``executed_at`` on OPEN v3 records matching this executed move.

    An open record is a logged decision (``action`` set) that was never
    executed (``executed_at`` None) — e.g. an optimizer/leverage advice record
    logged BEFORE Josh clicked. Matching is by mlbam when both sides carry
    one, else the safe name key, over snapshot_dates within ``window_days``
    before the transaction; when the executed ``action`` kind is supplied, a
    record is stamped only if its own action agrees (an executed ADD never
    closes a logged DROP of the same player — different decisions; a logged
    swap counts as either leg). Returns the stamped paths; the caller skips
    auto-creation for a stamped move so one decision never becomes two
    records.
    """
    kinds = None
    if action:
        kinds = {'add': {'add', 'swap'}, 'drop': {'drop', 'swap'}}.get(
            str(action).lower())
    if root is None:
        # Re-resolve at call time so monkeypatching the logger works.
        import plv_clone.decisions.logger as _logger
        root = _logger.DECISIONS_ROOT
    root = Path(root)
    if not root.exists():
        return []
    k = safe_name_key(name) if name else None
    lo = when.date() - timedelta(days=window_days)
    hi = when.date()
    stamped: list[Path] = []
    for day_dir in sorted(root.iterdir()):
        if not day_dir.is_dir():
            continue
        try:
            day = date.fromisoformat(day_dir.name)
        except ValueError:
            continue
        if not (lo <= day <= hi):
            continue
        for f in sorted(day_dir.glob('*.json')):
            try:
                payload = json.loads(f.read_text(encoding='utf-8'))
            except Exception as e:
                print(f'  WARN unreadable decision file {f.name}: {e}')
                continue
            if not isinstance(payload, dict):
                continue    # scorecard-style files are LISTS — not records
            if payload.get('action') is None:
                continue                      # verdict record, not a move
            if kinds is not None and str(payload['action']).lower() not in kinds:
                continue                      # wrong decision kind for this move
            if payload.get('executed_at'):
                continue                      # already executed/stamped
            rec_mlbam = payload.get('mlbam_id')
            if mlbam is not None and rec_mlbam is not None:
                match = int(rec_mlbam) == int(mlbam)
            else:
                match = bool(k) and safe_name_key(
                    payload.get('player_name') or '') == k
            if not match:
                continue
            payload['executed_at'] = when.isoformat(timespec='seconds')
            if not dry_run:
                _atomic_write_json(f, payload)
            stamped.append(f)
    return stamped


def reconcile(*, days: int = 30, dry_run: bool = False,
              tx_path: Path | None = None, hist_path: Path | None = None,
              root: Path | None = None, verbose: bool = True) -> dict:
    tx = load_my_transactions(days=days, path=tx_path)
    hist = dpwin_history.load(hist_path)
    events = collapse_swaps(tx)
    stats = {'events': len(events), 'created': 0, 'stamped': 0,
             'unattributed': 0, 'no_bucket': 0, 'no_alternative': 0,
             'name_only_matches': 0, 'records': []}

    if verbose:
        print(f'  {len(events)} executed move(s) in the last {days}d; '
              f'dpwin history has {len(hist)} rows / '
              f'{hist["run_id"].nunique() if not hist.empty else 0} runs')

    for ev in events:
        chosen = ev['add'] or ev['drop']
        name = chosen.get('player_name')
        mlbam = chosen.get('mlbam_id')
        mlbam = int(mlbam) if pd.notna(mlbam) else None

        # Docstring step 3: a decision that was LOGGED before the click just
        # needs its execution recorded — stamping beats auto-creating a
        # duplicate, and it works even when no surface is attributable.
        stamped = stamp_open_records(name=name, mlbam=mlbam, when=ev['when'],
                                     root=root, dry_run=dry_run,
                                     action=ev.get('action'))
        if stamped:
            stats['stamped'] += len(stamped)
            if verbose:
                print(f'  = {ev["action"].upper():5} {name}: stamped '
                      f'executed_at on {len(stamped)} logged decision '
                      f'record(s) — no duplicate created')
            continue

        run_id, note = find_run(hist, ev['when'])

        if run_id is None:
            stats['unattributed'] += 1
            if verbose:
                print(f'  - {ev["action"].upper():5} {name}: {note}')
            continue

        bucket, bucket_source = _resolve_bucket(hist, run_id, chosen)
        if bucket is None:
            # Never default 'H'. A move we cannot bucket cannot be honestly
            # graded, so it joins the unattributable count — loudly.
            stats['no_bucket'] += 1
            stats['unattributed'] += 1
            if verbose:
                print(f'  - {ev["action"].upper():5} {name}: no bucket from the '
                      f'surface, the resolvers, or the projection maps — '
                      f'unattributable (refusing to default to H)')
            continue

        exec_info = find_executed_dpwin(hist, run_id, name) if ev['add'] else None
        rejected = (pick_rejected(hist, run_id, bucket, name)
                    if ev['add'] else None)
        if ev['add'] and rejected is None:
            stats['no_alternative'] += 1

        if mlbam is None:
            # The store's mlbam_id is mostly NaN, so this is the normal path, not
            # an error — but it is where a same-name collision would enter, so it
            # is counted and reported.
            stats['name_only_matches'] += 1

        rec = build_executed_record(
            snapshot_date=ev['date'].isoformat(),
            player_name=name, mlbam_id=mlbam, bucket=bucket,
            action=ev['action'],
            executed_at=ev['when'].isoformat(timespec='seconds'),
            rejected=rejected,
            dpwin_chosen=(exec_info or {}).get('dpwin'),
            dpwin_rejected=(rejected or {}).get('dpwin'),
            source_run_id=run_id,
            regime=(exec_info or {}).get('regime'),
            base_pwin=(exec_info or {}).get('base_pwin'),
            dtitle_equity_chosen=(exec_info or {}).get('dtitle_equity_pp'),
            reason_tag='auto_reconciled',
            inputs={'reconciled_from': 'transactions_history',
                    'run_match_note': note,
                    'dropped_name': (ev['drop'] or {}).get('player_name'),
                    'id_source': 'mlbam' if mlbam else 'name_only',
                    'bucket_source': bucket_source},
        )
        stats['records'].append(rec)
        if verbose:
            alt = rejected['name'] if rejected else 'NONE RECORDED'
            dp = (exec_info or {}).get('dpwin')
            dps = f'{dp*100:+.2f}pp' if dp is not None else 'not scored'
            print(f'  + {ev["action"].upper():5} {name} ({bucket}) '
                  f'dpwin {dps} | passed on: {alt}')
        if not dry_run:
            log_decision(rec, root=root)
            stats['created'] += 1

    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--days', type=int, default=30)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    print('=== reconcile_decisions — executed moves x the dpwin surface ===')
    s = reconcile(days=args.days, dry_run=args.dry_run)
    print(f'\n  events {s["events"]} | records {"(dry)" if args.dry_run else s["created"]} '
          f'| stamped {s["stamped"]} | unattributed {s["unattributed"]} '
          f'(no-bucket {s["no_bucket"]}) | no-alternative {s["no_alternative"]} '
          f'| name-only ids {s["name_only_matches"]}')
    if s['unattributed']:
        print(f'  NOTE {s["unattributed"]} executed move(s) had no dpwin surface '
              f'within {ATTRIBUTION_DAYS}d — those decisions can never be graded. '
              f'Run /matchup-leverage or the optimizer BEFORE executing to close '
              f'this gap going forward.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

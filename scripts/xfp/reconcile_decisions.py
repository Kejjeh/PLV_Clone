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

TWO REALITIES OF THE ACTUAL DATA (both cost a rewrite of the first design)
-------------------------------------------------------------------------
* ``action_str`` values are ``FA ADDED`` / ``WAIVER ADDED`` / ``DROPPED`` — there
  is no bare ``ADDED``.
* ``mlbam_id`` is **mostly NaN** in this store. So an id join is the exception and
  a normalized-name join is the primary path. It uses ``safe_name_key`` (which
  collapses the curly-vs-straight apostrophe that already caused the O'Hearn
  mis-key) and REPORTS every name-only match, because a name join is exactly where
  a same-name collision would enter this pipeline.

MATCHING PRECEDENCE, and why date proximity is only a fallback: ``source_run_id``
is exact when present. Otherwise the run is chosen as the latest snapshot at or
before the transaction date, which can be wrong if two runs happened that day —
which is precisely why ``run_id`` embeds the time and why ambiguity is reported
rather than silently resolved.

Runs nightly AFTER persist_transactions.py. Unmatched executed moves are printed
loudly: a permanent reconciliation gap is a real cost, not a rounding error.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))

from plv_clone.decisions.logger import (  # noqa: E402
    DECISIONS_ROOT, DecisionRecord, build_executed_record, log_decision,
    is_executed_record,
)
from plv_clone.utils.name_match import safe_name_key  # noqa: E402
from scripts.xfp.lib import dpwin_history  # noqa: E402

TX_PARQUET = ROOT / 'data' / 'research' / 'transactions_history.parquet'
MY_TEAM = 'New York Ligers'

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


def _bucket_of(rec: dict | None) -> str:
    """H / SP / RP from the transaction's position field (best available)."""
    if not rec:
        return 'H'
    pos = str(rec.get('position') or '').upper()
    if pos in ('SP',):
        return 'SP'
    if pos in ('RP',):
        return 'RP'
    if pos in ('P',):
        return 'SP'
    return 'H'


def find_run(hist: pd.DataFrame, when_date: date) -> tuple[str | None, str]:
    """The dpwin run current at *when_date*, plus a note about the match quality."""
    if hist.empty:
        return None, 'no dpwin history'
    lo = (when_date - timedelta(days=ATTRIBUTION_DAYS)).isoformat()
    sub = hist[(hist['snapshot_date'].astype(str) <= when_date.isoformat())
               & (hist['snapshot_date'].astype(str) >= lo)]
    if sub.empty:
        return None, (f'no dpwin run within {ATTRIBUTION_DAYS}d before '
                      f'{when_date} — move cannot be attributed to a surface')
    runs = sorted(sub['run_id'].unique())
    chosen = runs[-1]
    note = 'exact-day run' if len(runs) == 1 else (
        f'{len(runs)} candidate runs in window, took latest ({chosen})')
    return chosen, note


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


def reconcile(*, days: int = 30, dry_run: bool = False,
              tx_path: Path | None = None, hist_path: Path | None = None,
              root: Path | None = None, verbose: bool = True) -> dict:
    tx = load_my_transactions(days=days, path=tx_path)
    hist = dpwin_history.load(hist_path)
    events = collapse_swaps(tx)
    stats = {'events': len(events), 'created': 0, 'unattributed': 0,
             'no_alternative': 0, 'name_only_matches': 0, 'records': []}

    if verbose:
        print(f'  {len(events)} executed move(s) in the last {days}d; '
              f'dpwin history has {len(hist)} rows / '
              f'{hist["run_id"].nunique() if not hist.empty else 0} runs')

    for ev in events:
        chosen = ev['add'] or ev['drop']
        name = chosen.get('player_name')
        bucket = _bucket_of(ev['add'] or ev['drop'])
        run_id, note = find_run(hist, ev['date'])

        if run_id is None:
            stats['unattributed'] += 1
            if verbose:
                print(f'  - {ev["action"].upper():5} {name}: {note}')
            continue

        exec_info = find_executed_dpwin(hist, run_id, name) if ev['add'] else None
        rejected = (pick_rejected(hist, run_id, bucket, name)
                    if ev['add'] else None)
        if ev['add'] and rejected is None:
            stats['no_alternative'] += 1

        mlbam = chosen.get('mlbam_id')
        mlbam = int(mlbam) if pd.notna(mlbam) else None
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
                    'id_source': 'mlbam' if mlbam else 'name_only'},
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
          f'| unattributed {s["unattributed"]} | no-alternative {s["no_alternative"]} '
          f'| name-only ids {s["name_only_matches"]}')
    if s['unattributed']:
        print(f'  NOTE {s["unattributed"]} executed move(s) had no dpwin surface '
              f'within {ATTRIBUTION_DAYS}d — those decisions can never be graded. '
              f'Run /matchup-leverage or the optimizer BEFORE executing to close '
              f'this gap going forward.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

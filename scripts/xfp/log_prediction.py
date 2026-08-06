# -*- coding: utf-8 -*-
"""Log a falsifiable prediction at the moment advice is given.

This is the missing half of the decision ledger. The optimizer records what
Josh CHOSE; this records what Claude CLAIMED, with a number and a deadline, so
that six weeks later the scorecard can say who was right instead of telling
another story about it.

The friction is deliberately near zero, because a discipline that costs a
minute per verdict will not survive contact with a live season.

    # absolute claim
    python scripts/xfp/log_prediction.py \
        --player "Trent Grisham" --bucket H --days 21 --at-least 60 \
        --claim "Grisham clears 60 FP over the next three weeks as the everyday CF"

    # relative claim -- the one that matters, because it is the counterfactual
    python scripts/xfp/log_prediction.py \
        --player "Trent Grisham" --bucket H --vs "Ezequiel Duran" \
        --days 21 --margin 15 \
        --claim "Grisham outscores Duran by 15+ FP over 21 days"

Settlement happens in the nightly settle_decisions run once the horizon
elapses. Nothing here peeks at outcomes.
"""
from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))

from plv_clone.decisions.logger import (                    # noqa: E402
    build_prediction_record, log_decision)
from plv_clone.decisions.prediction import build_prediction  # noqa: E402
from plv_clone.utils.name_match import (                     # noqa: E402
    resolve_batter_id, resolve_pitcher_id)

BUCKETS = ('H', 'SP', 'RP')


def _resolve(name: str, bucket: str, team: str | None) -> int | None:
    """mlbam via the collision-aware resolver, never a bare name match.

    A prediction keyed to the wrong Duran settles against the wrong player and
    is worse than no record at all, so an unresolvable name is surfaced rather
    than guessed.
    """
    try:
        if bucket == 'H':
            return resolve_batter_id(name, team=team)
        return resolve_pitcher_id(name, team=team,
                                  role=('sp' if bucket == 'SP' else 'rp'))
    except Exception as exc:
        print(f'  ! could not resolve {name!r}: {exc}')
        return None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--player', required=True)
    p.add_argument('--bucket', required=True, choices=BUCKETS)
    p.add_argument('--claim', required=True,
                   help='the claim in plain words, as it would be quoted back')
    p.add_argument('--days', type=int, required=True, help='settlement horizon')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--at-least', type=float, metavar='FP',
                   help='subject scores at least this many total FP')
    g.add_argument('--at-most', type=float, metavar='FP',
                   help='subject scores at most this many total FP')
    g.add_argument('--margin', type=float, metavar='FP',
                   help='subject outscores --vs by at least this many FP')
    p.add_argument('--vs', help='comparator name (required with --margin)')
    p.add_argument('--team', help='team hint for name resolution')
    p.add_argument('--vs-team', help='team hint for the comparator')
    p.add_argument('--reason', help='short reason tag')
    p.add_argument('--confidence', type=float,
                   help='0-1; how sure the claim is, stated up front')
    p.add_argument('--made-by', default='claude')
    p.add_argument('--date', help='override the stated-on date (YYYY-MM-DD)')
    a = p.parse_args()

    if a.margin is not None and not a.vs:
        p.error('--margin needs --vs: a margin claim compares against somebody')

    stated_on = (datetime.date.fromisoformat(a.date) if a.date
                 else datetime.date.today())

    mlbam = _resolve(a.player, a.bucket, a.team)
    vs_mlbam = _resolve(a.vs, a.bucket, a.vs_team) if a.vs else None
    if a.vs and vs_mlbam is None:
        print('  refusing to log: the comparator could not be resolved, so the '
              'claim could not be settled against the right player')
        return 1

    if a.margin is not None:
        pred = build_prediction(
            claim=a.claim, metric='fp_margin_vs', threshold=a.margin,
            window_days=a.days, stated_on=stated_on, direction='at_least',
            made_by=a.made_by, vs_name=a.vs, vs_mlbam=vs_mlbam)
    else:
        at_most = a.at_most is not None
        pred = build_prediction(
            claim=a.claim, metric='total_fp',
            threshold=(a.at_most if at_most else a.at_least),
            window_days=a.days, stated_on=stated_on,
            direction=('at_most' if at_most else 'at_least'),
            made_by=a.made_by)

    rec = build_prediction_record(
        snapshot_date=stated_on.isoformat(), player_name=a.player,
        mlbam_id=mlbam, bucket=a.bucket, prediction=pred,
        reason_tag=a.reason, confidence=a.confidence)
    path = log_decision(rec)

    print(f'logged {rec.decision_id}')
    print(f'  claim   : {pred.claim}')
    print(f'  settles : {pred.metric} {pred.direction.replace("_", " ")} '
          f'{pred.threshold:g} FP by {pred.horizon_end}')
    if pred.vs_name:
        print(f'  against : {pred.vs_name} ({vs_mlbam})')
    if mlbam is None:
        print('  WARNING : subject unresolved — this record will settle as '
              'UNSETTLEABLE unless the id is added')
    print(f'  -> {path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

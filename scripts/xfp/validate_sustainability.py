"""Backfill actual outcomes for sustainability calls + report residuals.

For each row in sustainability_history.csv where call_date is ≥28 days ago
and actual_fp_per_unit_4wk_post is not yet populated, pull the player's
gameLog from call_date+1 to call_date+28 and compute mean FP per unit
(per-start for pitchers, per-game for hitters).

Run weekly. After ≥30 backfilled rows, prints MAE comparing model_at_call
vs sus_ev_at_call against actual outcomes per bucket.

Usage:
    python scripts/xfp/validate_sustainability.py             # do backfill
    python scripts/xfp/validate_sustainability.py --dry-run   # report only
    python scripts/xfp/validate_sustainability.py --residuals # show validation stats
"""
from __future__ import annotations
import argparse
import csv
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path('c:/Users/Joshua/plv_clone')
HISTORY = ROOT / 'data' / 'research' / 'sustainability_history.csv'
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))


def _fetch_json(url):
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _sp_fp(stat):
    """BrownU SP FP formula."""
    ip = float(stat.get('inningsPitched', '0') or 0)
    h = int(stat.get('hits', 0))
    er = int(stat.get('earnedRuns', 0))
    bb = int(stat.get('baseOnBalls', 0))
    k = int(stat.get('strikeOuts', 0))
    hbp = int(stat.get('hitByPitch', 0))
    return k + ip * 3.3 - h - 2 * er - bb - hbp


def _hitter_fp(stat):
    """BrownU hitter FP formula."""
    return (int(stat.get('runs', 0)) + int(stat.get('totalBases', 0))
            + int(stat.get('rbi', 0)) + int(stat.get('baseOnBalls', 0))
            + int(stat.get('hitByPitch', 0)) + int(stat.get('stolenBases', 0))
            - int(stat.get('strikeOuts', 0)))


def actual_fp_per_unit(mlbam: int, kind: str, start_date: str, end_date: str,
                        year: int = 2026):
    """Returns (mean_fp_per_unit, n_units) over [start_date, end_date]."""
    group = 'pitching' if kind == 'pitcher' else 'hitting'
    url = (f'https://statsapi.mlb.com/api/v1/people/{mlbam}/stats?'
           f'stats=gameLog&group={group}&season={year}')
    try:
        data = _fetch_json(url)
    except Exception:
        return None, 0
    stats_list = data.get('stats') or []
    splits = stats_list[0].get('splits', []) if stats_list else []
    fps = []
    for s in splits:
        d = s.get('date', '')
        if not (start_date <= d <= end_date):
            continue
        st = s.get('stat', {})
        if kind == 'pitcher':
            if int(st.get('gamesStarted', 0)) == 0:
                continue
            fps.append(_sp_fp(st))
        else:
            if int(st.get('plateAppearances', 0)) == 0:
                continue
            fps.append(_hitter_fp(st))
    if not fps:
        return None, 0
    return sum(fps) / len(fps), len(fps)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true',
                        help='Report what would be backfilled without writing')
    parser.add_argument('--residuals', action='store_true',
                        help='Print MAE comparison of model vs sustainability vs actual')
    args = parser.parse_args()

    if not HISTORY.exists():
        print(f'No history file at {HISTORY}')
        return

    rows = []
    with HISTORY.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    today = datetime.now().date()

    # Backfill phase
    if not args.residuals:
        eligible_4wk = 0
        eligible_8wk = 0
        for row in rows:
            try:
                call_date = datetime.strptime(row['call_date'], '%Y-%m-%d').date()
            except (ValueError, KeyError):
                continue
            mlbam = row.get('player_id')
            if not mlbam:
                continue
            if (today - call_date).days >= 28 and not row.get('actual_fp_per_unit_4wk_post'):
                eligible_4wk += 1
            if (today - call_date).days >= 56 and not row.get('actual_fp_per_unit_8wk_post'):
                eligible_8wk += 1

        print(f'sustainability_history rows: {len(rows)}')
        print(f'  4wk backfill candidates: {eligible_4wk}')
        print(f'  8wk backfill candidates: {eligible_8wk}')

        if args.dry_run:
            return

        if eligible_4wk + eligible_8wk == 0:
            print('  No rows ready for backfill — re-run after some calls are 28d+ old.')
            return

        # Actual backfill
        updates = 0
        for row in rows:
            try:
                call_date = datetime.strptime(row['call_date'], '%Y-%m-%d').date()
            except (ValueError, KeyError):
                continue
            mlbam = row.get('player_id')
            if not mlbam:
                continue
            mlbam = int(mlbam)
            kind = row.get('kind', 'pitcher')
            # 4-week backfill
            if (today - call_date).days >= 28 and not row.get('actual_fp_per_unit_4wk_post'):
                start = (call_date + timedelta(days=1)).isoformat()
                end = (call_date + timedelta(days=28)).isoformat()
                mean_fp, n = actual_fp_per_unit(mlbam, kind, start, end)
                if mean_fp is not None and n >= 2:
                    row['actual_fp_per_unit_4wk_post'] = f'{mean_fp:.4f}'
                    row['backfill_date_4wk'] = today.isoformat()
                    updates += 1
                    print(f'  4wk: {row["player_name"]:<22} n={n}  actual_mean={mean_fp:.2f}  '
                          f'(model_at_call={row.get("model_at_call","?")})')
            # 8-week backfill
            if (today - call_date).days >= 56 and not row.get('actual_fp_per_unit_8wk_post'):
                start = (call_date + timedelta(days=1)).isoformat()
                end = (call_date + timedelta(days=56)).isoformat()
                mean_fp, n = actual_fp_per_unit(mlbam, kind, start, end)
                if mean_fp is not None and n >= 4:
                    row['actual_fp_per_unit_8wk_post'] = f'{mean_fp:.4f}'
                    row['backfill_date_8wk'] = today.isoformat()
                    updates += 1
                    print(f'  8wk: {row["player_name"]:<22} n={n}  actual_mean={mean_fp:.2f}')

        if updates:
            with HISTORY.open('w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=reader.fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            print(f'\nWrote {updates} backfilled fields → {HISTORY}')
        else:
            print('\nNo updates written.')

    # Residuals report
    if args.residuals:
        from collections import defaultdict
        bucket_stats = defaultdict(lambda: {'n': 0, 'mae_model': 0.0, 'mae_sus': 0.0})
        for row in rows:
            actual = row.get('actual_fp_per_unit_4wk_post')
            if not actual:
                continue
            try:
                actual = float(actual)
                model = float(row.get('model_at_call') or 'nan')
                sus = float(row.get('sus_ev_at_call') or 'nan')
                bucket = row.get('bucket', '?')
            except ValueError:
                continue
            if model != model or sus != sus:  # NaN check
                continue
            bs = bucket_stats[bucket]
            bs['n'] += 1
            bs['mae_model'] += abs(model - actual)
            bs['mae_sus'] += abs(sus - actual)

        if not bucket_stats:
            print('No backfilled rows yet — can\'t compute residuals. Re-run after ≥4 weeks.')
            return

        print(f'\n=== Residuals (actual_4wk vs model vs sus_ev) ===')
        print(f'{"Bucket":<12} {"n":>4} {"MAE_model":>10} {"MAE_sus":>10} {"better":<12}')
        print('-' * 55)
        total = {'n': 0, 'mae_model': 0.0, 'mae_sus': 0.0}
        for b, s in sorted(bucket_stats.items()):
            mae_m = s['mae_model'] / s['n']
            mae_s = s['mae_sus'] / s['n']
            better = 'sus' if mae_s < mae_m else 'model' if mae_m < mae_s else 'tie'
            print(f'{b:<12} {s["n"]:>4} {mae_m:>10.3f} {mae_s:>10.3f} {better:<12}')
            total['n'] += s['n']
            total['mae_model'] += s['mae_model']
            total['mae_sus'] += s['mae_sus']
        print('-' * 55)
        if total['n']:
            print(f"{'TOTAL':<12} {total['n']:>4} "
                  f"{total['mae_model']/total['n']:>10.3f} "
                  f"{total['mae_sus']/total['n']:>10.3f}")


if __name__ == '__main__':
    main()

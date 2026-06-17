"""fetch_roster_return_dates.py — focused IL / return-date snapshot.

Pulls the live roster via `get_my_roster_with_injuries()` and prints a
clean table of every injured player with ESPN's structured return date
(from the public athlete endpoint inside `get_injury_details`).

No model joins, no FA scan — just "who's hurt, what is it, when are they
back." Designed to be runnable on a local box with ESPN cookies set,
output piped or saved for downstream use.

Usage:
    python -X utf8 scripts/xfp/fetch_roster_return_dates.py
    python -X utf8 scripts/xfp/fetch_roster_return_dates.py --save
    python -X utf8 scripts/xfp/fetch_roster_return_dates.py --names "Max Fried,Carlos Rodon"

Outputs (with --save):
    data/research/decisions/<today>/roster_return_dates_<today>.md
    data/research/decisions/<today>/roster_return_dates_<today>.json
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import date
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.espn_connector import get_my_roster_with_injuries  # noqa: E402


def _fmt_injury(row) -> str:
    parts = [str(row.get('injury_type') or '').strip(),
             str(row.get('injury_detail') or '').strip()]
    side = str(row.get('injury_side') or '').strip()
    base = ' '.join(p for p in parts if p) or '—'
    return f"{base} ({side})" if side else base


def _select(roster_df, names_filter: list[str] | None):
    if names_filter:
        wanted = {n.strip().lower() for n in names_filter if n.strip()}
        return roster_df[roster_df['player_name'].str.lower().isin(wanted)].copy()
    return roster_df.copy()


def _render_markdown(roster_df, today: date) -> str:
    out = []
    out.append(f"# Roster return dates — {today.isoformat()}\n")

    n_total = len(roster_df)
    n_injured = int(roster_df['injured'].sum()) if 'injured' in roster_df.columns else 0
    il_slot = int((roster_df['lineup_slot'] == 'IL').sum()) if 'lineup_slot' in roster_df.columns else 0
    out.append(f"_{n_total} players on roster | {n_injured} injured | {il_slot} in IL slot_\n")

    if not n_injured:
        out.append("**No injured players on roster.**\n")
        return '\n'.join(out)

    il_df = roster_df[roster_df['injured']].copy()
    if 'days_until_return' in il_df.columns:
        il_df = il_df.sort_values('days_until_return', na_position='last')

    out.append("## IL / DTD timeline\n")
    out.append("| Player | Pos | Slot | Status | Injury | Return | Days | Frees IL? |")
    out.append("|---|---|---|---|---|---|---|---|")
    for _, r in il_df.iterrows():
        frees = "Yes" if r.get('lineup_slot') == 'IL' else "No"
        ret = r.get('return_date')
        ret_str = ret.isoformat() if hasattr(ret, 'isoformat') else (str(ret) if ret else '—')
        days = r.get('days_until_return')
        days_str = str(int(days)) if days == days and days is not None else '—'  # NaN check
        out.append(
            f"| {r.get('player_name','?')} "
            f"| {r.get('position','')} "
            f"| {r.get('lineup_slot','')} "
            f"| {r.get('status_code') or r.get('injury_status','')} "
            f"| {_fmt_injury(r)} "
            f"| {ret_str} "
            f"| {days_str} "
            f"| {frees} |"
        )

    # Summary buckets
    has_days = il_df['days_until_return'].dropna()
    if len(has_days):
        out.append("")
        out.append(f"_Summary: {(has_days <= 7).sum()} return ≤7d, "
                   f"{(has_days <= 14).sum()} ≤14d, "
                   f"{(has_days <= 30).sum()} ≤30d._")

    # Missing-data note
    n_missing = int(il_df['return_date'].isna().sum()) if 'return_date' in il_df.columns else 0
    if n_missing:
        out.append("")
        out.append(f"_⚠ {n_missing} injured players have no ETA from ESPN — check ESPN.com injury report manually._")

    return '\n'.join(out) + '\n'


def _render_json(roster_df, today: date) -> dict:
    if not int(roster_df['injured'].sum()):
        return {'snapshot_date': today.isoformat(), 'injured': []}
    il_df = roster_df[roster_df['injured']].copy()
    records = []
    for _, r in il_df.iterrows():
        ret = r.get('return_date')
        ret_str = ret.isoformat() if hasattr(ret, 'isoformat') else (str(ret) if ret else None)
        days = r.get('days_until_return')
        records.append({
            'player_name': r.get('player_name'),
            'player_id': int(r['player_id']) if r.get('player_id') == r.get('player_id') else None,
            'position': r.get('position'),
            'pro_team': r.get('pro_team'),
            'lineup_slot': r.get('lineup_slot'),
            'injury_status': r.get('injury_status'),
            'status_code': r.get('status_code'),
            'injury_type': r.get('injury_type'),
            'injury_detail': r.get('injury_detail'),
            'injury_side': r.get('injury_side'),
            'return_date': ret_str,
            'days_until_return': int(days) if days == days and days is not None else None,
            'short_comment': r.get('short_comment'),
        })
    return {'snapshot_date': today.isoformat(), 'injured': records}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--save', action='store_true',
                        help='Write markdown + json under data/research/decisions/<today>/')
    parser.add_argument('--names', default='',
                        help='Comma-separated player names to filter (default: full roster).')
    parser.add_argument('--out-dir', default=None,
                        help='Override output directory (only with --save).')
    args = parser.parse_args()

    today = date.today()

    try:
        roster = get_my_roster_with_injuries()
    except Exception as exc:
        print(f"FATAL: could not fetch roster: {exc}", file=sys.stderr)
        print("Ensure ESPN_LEAGUE_ID / ESPN_S2 / ESPN_SWID are set and `espn-api` is installed.",
              file=sys.stderr)
        return 2

    if roster is None or roster.empty:
        print("Empty roster returned — auth ok but no players?", file=sys.stderr)
        return 1

    names_filter = [n for n in args.names.split(',') if n.strip()] if args.names else None
    filtered = _select(roster, names_filter)
    if names_filter and filtered.empty:
        print(f"No roster rows matched: {names_filter}", file=sys.stderr)
        return 1

    md = _render_markdown(filtered, today)
    print(md)

    if args.save:
        out_dir = Path(args.out_dir) if args.out_dir else (
            _REPO_ROOT / 'data' / 'research' / 'decisions' / today.isoformat()
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        md_path = out_dir / f'roster_return_dates_{today.isoformat()}.md'
        json_path = out_dir / f'roster_return_dates_{today.isoformat()}.json'
        md_path.write_text(md, encoding='utf-8')
        json_path.write_text(
            json.dumps(_render_json(filtered, today), indent=2, default=str),
            encoding='utf-8',
        )
        print(f"\nWrote:\n  {md_path}\n  {json_path}", file=sys.stderr)

    return 0


if __name__ == '__main__':
    sys.exit(main())

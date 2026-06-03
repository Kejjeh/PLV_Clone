"""stream_the_stack — daily ranked FA SP streamer recommender filtered by boom_stack.

Pulls MLB Stats API confirmed probables for the next 3 days, intersects with the
ESPN league FA pool (SPs only), runs Connelly-Early roster verification on each,
computes boom_stack live per pitcher per start, and emits a ranked markdown
report + JSON sidecar.

Outputs:
  data/outputs/stream_the_stack_<YYYY-MM-DD>.md
  data/outputs/stream_the_stack_<YYYY-MM-DD>.json

Usage:
  python -X utf8 scripts/xfp/stream_the_stack.py
  python -X utf8 scripts/xfp/stream_the_stack.py --days 3 --min-rp3 0

Notes:
  - "FA" verified via league.teams roster scan (NOT percent_owned). Connelly Early rule.
  - boom_stack is a DISPLAY TAG only — see reference_boom_stack_tag.md.
  - Stack=0 candidates are excluded from output (below baseline boom rate).
  - rp3 rank is the headline projection; boom_stack is the right-tail confidence layer.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

# Ensure repo modules are importable.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / 'src'))

from scripts.xfp.lib.boom_stack import (  # noqa: E402
    compute_boom_stack,
    BOOM_RATE_BY_STACK,
    MEAN_FP_BY_STACK,
)

_STATSAPI = 'https://statsapi.mlb.com/api/v1'
_RP3_CSV = _REPO_ROOT / 'data' / 'outputs' / 'xfp_rp3_projections.csv'
_TEAM_STRENGTH_CSV = _REPO_ROOT / 'data' / 'research' / 'xfp_cache' / 'team_strength_2026.csv'
_SP_MULTIYR_CSV = _REPO_ROOT / 'data' / 'research' / 'xfp_cache' / 'sp_multiyr_2015_2025.csv'
_OUT_DIR = _REPO_ROOT / 'data' / 'outputs'


# ---------------------------------------------------------------------------
# MLB Stats API: confirmed probables window
# ---------------------------------------------------------------------------
def fetch_confirmed_probables(start_d: date, end_d: date) -> list[dict]:
    """Return [{pitcher_id, pitcher_name, team_abbr, opp_abbr, game_date, is_home}].

    Only pitchers with a *confirmed* probablePitcher entry are returned. Rotation-gap
    predictions are intentionally NOT used here — streaming decisions need confirmed
    starts, not maybes.
    """
    url = (
        f'{_STATSAPI}/schedule?sportId=1'
        f'&startDate={start_d.isoformat()}&endDate={end_d.isoformat()}'
        f'&hydrate=probablePitcher,team'
    )
    try:
        data = requests.get(url, timeout=20).json()
    except Exception as e:
        print(f'  ! MLB Stats API fetch failed: {e}', file=sys.stderr)
        return []

    rows: list[dict] = []
    for d_block in data.get('dates', []):
        for game in d_block.get('games', []):
            game_date_str = game.get('gameDate', '')[:10]
            try:
                gd = datetime.fromisoformat(game_date_str).date()
            except Exception:
                continue
            if not (start_d <= gd <= end_d):
                continue
            home = (game.get('teams') or {}).get('home') or {}
            away = (game.get('teams') or {}).get('away') or {}
            home_abbr = ((home.get('team') or {}).get('abbreviation') or '?').upper()
            away_abbr = ((away.get('team') or {}).get('abbreviation') or '?').upper()
            for side, opp_abbr, is_home in ((home, away_abbr, True), (away, home_abbr, False)):
                p = side.get('probablePitcher') or {}
                pid = p.get('id')
                if not pid:
                    continue
                rows.append({
                    'pitcher_id': int(pid),
                    'pitcher_name': p.get('fullName') or '',
                    'team_abbr': ((side.get('team') or {}).get('abbreviation') or '?').upper(),
                    'opp_abbr': opp_abbr,
                    'game_date': gd.isoformat(),
                    'is_home': is_home,
                })
    return rows


# ---------------------------------------------------------------------------
# ESPN FA pool + roster verification
# ---------------------------------------------------------------------------
def _norm_name(s: str) -> str:
    """Match the normalization used across plv_clone: lowercase, strip accents/punct."""
    import unicodedata
    if not s:
        return ''
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    return ''.join(ch for ch in s.lower() if ch.isalnum())


def load_fa_sp_pool() -> pd.DataFrame:
    """Return DataFrame[name, espn_id, pro_team, percent_owned, position] for ESPN FA SPs."""
    from app.espn_connector import _get_league, get_all_teams
    league = _get_league()
    fas = league.free_agents(size=2000)

    rows = []
    for p in fas:
        pos = getattr(p, 'position', '') or ''
        if pos != 'SP':
            continue
        rows.append({
            'fa_name': p.name,
            'espn_id': getattr(p, 'playerId', None),
            'pro_team': getattr(p, 'proTeam', '') or '',
            'percent_owned': getattr(p, 'percent_owned', 0.0),
            'position': pos,
            'injury_status': getattr(p, 'injuryStatus', '') or '',
        })
    fa_df = pd.DataFrame(rows)

    # Connelly Early cross-check — drop any "FA" that appears on a team roster.
    teams = get_all_teams()
    rostered_norm = set(teams['player_name'].dropna().map(_norm_name).tolist())
    if not fa_df.empty:
        fa_df['_norm'] = fa_df['fa_name'].map(_norm_name)
        before = len(fa_df)
        fa_df = fa_df[~fa_df['_norm'].isin(rostered_norm)].copy()
        dropped = before - len(fa_df)
        if dropped:
            print(f'  Connelly Early filter dropped {dropped} pseudo-FAs found on rosters')
        fa_df = fa_df.drop(columns=['_norm'])
    return fa_df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Name → MLBAM ID mapping
# ---------------------------------------------------------------------------
def _flip_lastfirst(s: str) -> str:
    """Convert 'Last, First' (or 'Last, First Jr.') → 'First Last'.

    Returns the input unchanged if no comma is present.
    """
    if not isinstance(s, str) or ',' not in s:
        return s
    parts = [p.strip() for p in s.split(',', 1)]
    if len(parts) != 2:
        return s
    return f'{parts[1]} {parts[0]}'


def build_name_to_mlbam() -> dict[str, int]:
    """Build {normalized_name: mlbam_pitcher_id} from sp_multiyr cache.

    sp_multiyr stores names as 'Last, First' (e.g. 'Misiorowski, Jacob'). ESPN
    uses 'First Last'. We normalize BOTH forms so either lookup direction works.
    """
    try:
        df = pd.read_csv(_SP_MULTIYR_CSV, usecols=['pitcher', 'player_name'])
    except Exception as e:
        print(f'  ! cannot read sp_multiyr cache: {e}', file=sys.stderr)
        return {}
    df['pitcher'] = df['pitcher'].astype('int64')
    # Most recent year row dominates after dedup on (name, id) pair
    df = df.drop_duplicates(['player_name', 'pitcher'], keep='last')

    out: dict[str, int] = {}
    for name, pid in zip(df['player_name'], df['pitcher']):
        if not isinstance(name, str):
            continue
        # Raw "Last, First" key
        out.setdefault(_norm_name(name), int(pid))
        # Flipped "First Last" key (ESPN-style)
        flipped = _flip_lastfirst(name)
        if flipped != name:
            out.setdefault(_norm_name(flipped), int(pid))
    return out


# ---------------------------------------------------------------------------
# rp3 + team_strength loaders
# ---------------------------------------------------------------------------
def load_rp3() -> pd.DataFrame:
    df = pd.read_csv(_RP3_CSV)
    df['pitcher'] = df['pitcher'].astype('int64')
    return df


def load_team_strength() -> pd.DataFrame:
    return pd.read_csv(_TEAM_STRENGTH_CSV)


# ---------------------------------------------------------------------------
# Main composition
# ---------------------------------------------------------------------------
def assemble_candidates(days: int) -> tuple[list[dict], dict]:
    """Build the ranked candidate list. Returns (candidates, summary_stats)."""
    today = date.today()
    end_d = today + timedelta(days=days - 1)

    print(f'Window: {today} → {end_d} ({days} days)')

    # 1. confirmed probables
    probables = fetch_confirmed_probables(today, end_d)
    print(f'  {len(probables)} confirmed probable-starts in window')

    # 2. FA SP pool (with Connelly Early cross-check)
    fa_sp = load_fa_sp_pool()
    print(f'  {len(fa_sp)} verified FA SPs in league')

    # 3. name → mlbam map
    name_to_mlbam = build_name_to_mlbam()

    fa_mlbam_set: set[int] = set()
    fa_by_mlbam: dict[int, dict] = {}
    for _, row in fa_sp.iterrows():
        nk = _norm_name(row['fa_name'])
        mlbam = name_to_mlbam.get(nk)
        if mlbam is None:
            continue
        fa_mlbam_set.add(mlbam)
        fa_by_mlbam[mlbam] = row.to_dict()

    print(f'  {len(fa_mlbam_set)} FA SPs resolved to MLBAM IDs')

    # 4. intersect FA SPs with confirmed probables
    fa_starts = [p for p in probables if p['pitcher_id'] in fa_mlbam_set]
    print(f'  {len(fa_starts)} FA SP starts in window')

    # 5. join rp3 + team_strength
    rp3 = load_rp3()
    rp3_by_pid = {int(r['pitcher']): r for _, r in rp3.iterrows()}
    ts = load_team_strength()
    ts_by_team = {row['team']: row for _, row in ts.iterrows()}

    candidates: list[dict] = []
    for start in fa_starts:
        pid = start['pitcher_id']
        fa_meta = fa_by_mlbam.get(pid, {})
        rp3_row = rp3_by_pid.get(pid)

        # rp3 fields (default to None if not in rp3)
        rp3_per_start = float(rp3_row['xfp_rp3_per_start']) if rp3_row is not None and pd.notna(rp3_row['xfp_rp3_per_start']) else None
        rp3_p25 = float(rp3_row['xfp_rp3_p25']) if rp3_row is not None and pd.notna(rp3_row.get('xfp_rp3_p25')) else None
        rp3_p75 = float(rp3_row['xfp_rp3_p75']) if rp3_row is not None and pd.notna(rp3_row.get('xfp_rp3_p75')) else None
        rp3_rank = int(rp3_row['rank']) if rp3_row is not None and pd.notna(rp3_row['rank']) else None
        dq_tag = rp3_row['data_quality_tag'] if rp3_row is not None else None
        rfg = float(rp3_row['recency_form_gap']) if rp3_row is not None and pd.notna(rp3_row.get('recency_form_gap')) else None
        rp3_signal = rp3_row['signal'] if rp3_row is not None and 'signal' in rp3_row.index else None

        # opp bat_index_recent
        opp_team = start['opp_abbr']
        opp_row = ts_by_team.get(opp_team)
        opp_bri = float(opp_row['bat_index_recent']) if opp_row is not None and pd.notna(opp_row.get('bat_index_recent')) else None

        # boom_stack live
        try:
            bs = compute_boom_stack(
                pitcher_id=pid,
                recency_form_gap=rfg,
                next_opp_team=opp_team,
            )
            boom_stack = bs['boom_stack']
            boom_components = bs['components']
            boom_detail = bs['detail']
            boom_rate_exp = bs['boom_rate_expected']
            boom_mean_fp = bs['mean_fp_expected']
        except Exception as e:
            print(f'    ! boom_stack failed for pid={pid}: {e}', file=sys.stderr)
            boom_stack = None
            boom_components = None
            boom_detail = None
            boom_rate_exp = None
            boom_mean_fp = None

        # matchup tier
        if opp_bri is None:
            matchup_tier = 'unknown'
        elif opp_bri <= 0.97:
            matchup_tier = 'soft'
        elif opp_bri <= 1.03:
            matchup_tier = 'neutral'
        else:
            matchup_tier = 'tough'

        candidates.append({
            'pitcher_id': pid,
            'pitcher_name': start['pitcher_name'] or fa_meta.get('fa_name'),
            'team': start['team_abbr'],
            'opp_team': opp_team,
            'is_home': start['is_home'],
            'game_date': start['game_date'],
            'rp3_rank': rp3_rank,
            'rp3_per_start': rp3_per_start,
            'rp3_p25': rp3_p25,
            'rp3_p75': rp3_p75,
            'rp3_signal': rp3_signal,
            'data_quality_tag': dq_tag,
            'recency_form_gap': rfg,
            'opp_bat_index_recent': opp_bri,
            'matchup_tier': matchup_tier,
            'boom_stack': boom_stack,
            'boom_components': boom_components,
            'boom_detail_summary': _summarize_boom_detail(boom_detail) if boom_detail else None,
            'boom_rate_expected': boom_rate_exp,
            'boom_mean_fp_expected': boom_mean_fp,
            'percent_owned': fa_meta.get('percent_owned', 0.0),
            'pro_team': fa_meta.get('pro_team', ''),
            'injury_status': fa_meta.get('injury_status', ''),
        })

    # Distribution before filtering for summary
    dist = {0: 0, 1: 0, 2: 0, 3: 0, 'none': 0}
    for c in candidates:
        bs = c['boom_stack']
        if bs is None:
            dist['none'] += 1
        else:
            dist[bs] = dist.get(bs, 0) + 1

    # Filter: skip stack=0 in output (below-baseline boom). Keep None too — represents
    # non-streamer-class (e.g., rank<50). For symmetry we keep them in JSON but skip
    # in markdown body unless they're stack=2+.
    summary = {
        'window_start': today.isoformat(),
        'window_end': end_d.isoformat(),
        'n_probables_total': len(probables),
        'n_fa_sps_in_league': len(fa_sp),
        'n_fa_sps_resolved_mlbam': len(fa_mlbam_set),
        'n_fa_sp_starts_in_window': len(fa_starts),
        'boom_stack_distribution': {str(k): v for k, v in dist.items()},
    }
    return candidates, summary


def _summarize_boom_detail(detail: dict) -> dict:
    """Compact the boom_stack per-component diagnostic for the JSON sidecar."""
    out = {}
    ss = detail.get('skill_spike', {})
    if ss:
        out['skill_spike'] = {
            'n_starts_2026': ss.get('n_starts_2026'),
            'delta_k_pp': round(ss['delta_k_pp'], 2) if 'delta_k_pp' in ss else None,
            'delta_bb_pp': round(ss['delta_bb_pp'], 2) if 'delta_bb_pp' in ss else None,
            'reason': ss.get('reason'),
        }
    rh = detail.get('recform_hot', {})
    if rh:
        rfg = rh.get('recency_form_gap')
        out['recform_hot'] = {'recency_form_gap': round(rfg, 2) if rfg is not None else None}
    os_ = detail.get('opp_soft', {})
    if os_:
        out['opp_soft'] = {
            'opp_bat_index_recent': round(os_['opp_bat_index_recent'], 4) if 'opp_bat_index_recent' in os_ else None,
            'soft_p33_threshold': round(os_['soft_p33_threshold'], 4) if 'soft_p33_threshold' in os_ else None,
            'reason': os_.get('reason'),
        }
    return out


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------
def rank_candidates(candidates: list[dict]) -> list[dict]:
    """Sort: boom_stack desc, rp3 per-start desc, percent_owned asc."""
    def sort_key(c):
        bs = c['boom_stack'] if c['boom_stack'] is not None else -1
        rp3 = c['rp3_per_start'] if c['rp3_per_start'] is not None else -999
        own = c['percent_owned'] if c['percent_owned'] is not None else 100.0
        return (-bs, -rp3, own)
    return sorted(candidates, key=sort_key)


def verdict_for(c: dict) -> str:
    """Verdict per candidate based on stack tier + matchup + rp3 rank."""
    bs = c['boom_stack']
    if bs is None:
        return 'SKIP (no boom_stack — non-streamer or missing rp3)'
    if bs >= 3:
        return 'BOOM SHOT — all 3 components lit; high-leverage stream'
    if bs == 2:
        return 'STREAM — meaningful boom edge; preferred play of the day'
    if bs == 1:
        return 'MODEST EDGE — usable streamer; consider matchup only if no stack=2+'
    return 'PASS — at or below baseline boom rate'


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------
def _fmt(val, fmt='.2f', fallback='—'):
    if val is None:
        return fallback
    try:
        if pd.isna(val):
            return fallback
    except Exception:
        pass
    try:
        return format(val, fmt)
    except Exception:
        return str(val)


def write_markdown(candidates: list[dict], summary: dict, out_path: Path) -> None:
    """Write the human-readable markdown report."""
    stack_3 = [c for c in candidates if c['boom_stack'] == 3]
    stack_2 = [c for c in candidates if c['boom_stack'] == 2]
    stack_1 = [c for c in candidates if c['boom_stack'] == 1]
    # Stack 0 + None intentionally omitted from body per spec.

    lines: list[str] = []
    lines.append(f'# stream_the_stack — {summary["window_start"]} → {summary["window_end"]}')
    lines.append('')
    lines.append(
        f'Confirmed FA SP starts in window: **{summary["n_fa_sp_starts_in_window"]}**. '
        f'Boom-stack distribution: {summary["boom_stack_distribution"]}.'
    )
    lines.append('')
    lines.append('> boom_stack = skill_spike + recform_hot + opp_soft (each 0|1). '
                 'See `reference_boom_stack_tag.md`. Display tag only; rp3 carries the '
                 'point estimate.')
    lines.append('')

    def _section(title: str, rows: list[dict]) -> None:
        lines.append(f'## {title}')
        lines.append('')
        if not rows:
            lines.append('_(none today)_')
            lines.append('')
            return
        lines.append(
            '| pitcher | team | date | opp | rp3 (p25–p75) | dq_tag | stack | boom% exp | matchup | own% | verdict |'
        )
        lines.append('|---|---|---|---|---|---|---|---|---|---|---|')
        for c in rows:
            rp3_cell = (
                f'{_fmt(c["rp3_per_start"], ".1f")} '
                f'({_fmt(c["rp3_p25"], ".1f")}-{_fmt(c["rp3_p75"], ".1f")})'
                + (f' #{c["rp3_rank"]}' if c['rp3_rank'] is not None else '')
            )
            stack_cell = f'{c["boom_stack"]}/3' if c['boom_stack'] is not None else '—'
            ha = '@' if not c.get('is_home', False) else 'vs'
            opp_cell = f'{ha}{c["opp_team"]}'
            lines.append(
                f'| {c["pitcher_name"]} | {c["team"]} | {c["game_date"]} | {opp_cell} | '
                f'{rp3_cell} | {c.get("data_quality_tag") or "—"} | {stack_cell} | '
                f'{_fmt((c["boom_rate_expected"] or 0) * 100, ".1f")}% | '
                f'{c["matchup_tier"]} | {_fmt(c["percent_owned"], ".0f")} | '
                f'{verdict_for(c)} |'
            )
        lines.append('')

    _section(f'STACK=3 candidates (BOOM SHOTS, n={len(stack_3)})', stack_3)
    _section(f'STACK=2+ candidates (high-leverage boom shots, n={len(stack_2)})', stack_2)
    _section(f'STACK=1 candidates (modest edge, n={len(stack_1)})', stack_1)

    if not stack_3 and not stack_2:
        lines.append('## Note')
        lines.append('')
        lines.append(
            '_No stack=2+ candidates today. This is expected — stack=2+ is rare (~10% of '
            'streamer pool). Check back tomorrow; the windowed scan refreshes each day._'
        )
        lines.append('')

    lines.append('---')
    lines.append('')
    lines.append('### Diagnostic footer')
    lines.append('')
    lines.append(f'- Confirmed probables in window: {summary["n_probables_total"]}')
    lines.append(f'- FA SPs in league (after Connelly Early filter): {summary["n_fa_sps_in_league"]}')
    lines.append(f'- FA SPs resolved to MLBAM: {summary["n_fa_sps_resolved_mlbam"]}')
    lines.append(f'- FA SP starts in window: {summary["n_fa_sp_starts_in_window"]}')
    lines.append('')

    out_path.write_text('\n'.join(lines), encoding='utf-8')


def write_json(candidates: list[dict], summary: dict, out_path: Path) -> None:
    payload = {
        'summary': summary,
        'candidates': candidates,
        'generated_at': datetime.now().isoformat(),
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding='utf-8')


# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------
def print_console_summary(candidates: list[dict], summary: dict) -> None:
    print()
    print('=' * 78)
    print(f'stream_the_stack — {summary["window_start"]} → {summary["window_end"]}')
    print('=' * 78)
    dist = summary['boom_stack_distribution']
    print(f'Distribution: stack=3:{dist.get("3", 0)}  stack=2:{dist.get("2", 0)}  '
          f'stack=1:{dist.get("1", 0)}  stack=0:{dist.get("0", 0)}  none:{dist.get("none", 0)}')
    print()

    stack_2plus = [c for c in candidates if c['boom_stack'] is not None and c['boom_stack'] >= 2]
    if stack_2plus:
        print(f'STACK=2+ candidates ({len(stack_2plus)}):')
        for c in stack_2plus:
            ha = '@' if not c.get('is_home', False) else 'vs'
            print(
                f'  [{c["boom_stack"]}/3] {c["pitcher_name"]:<25s} '
                f'{c["team"]} {ha}{c["opp_team"]} {c["game_date"]}  '
                f'rp3={_fmt(c["rp3_per_start"], ".1f")} '
                f'(rank #{c["rp3_rank"] if c["rp3_rank"] is not None else "—"})  '
                f'boom%~{_fmt((c["boom_rate_expected"] or 0)*100, ".1f")}%  '
                f'own={_fmt(c["percent_owned"], ".0f")}%'
            )
    else:
        print('STACK=2+ candidates: none today (expected — stack=2+ is ~10% of streamer pool).')
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--days', type=int, default=3,
                    help='Days forward from today (inclusive) to scan. Default 3.')
    ap.add_argument('--min-rp3', type=float, default=None,
                    help='Optional minimum xfp_rp3_per_start floor (e.g. 8.0).')
    args = ap.parse_args()

    candidates, summary = assemble_candidates(days=args.days)

    if args.min_rp3 is not None:
        before = len(candidates)
        candidates = [
            c for c in candidates
            if c['rp3_per_start'] is not None and c['rp3_per_start'] >= args.min_rp3
        ]
        print(f'  --min-rp3 {args.min_rp3} filter: {before} -> {len(candidates)}')

    candidates = rank_candidates(candidates)

    today_str = summary['window_start']
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = _OUT_DIR / f'stream_the_stack_{today_str}.md'
    json_path = _OUT_DIR / f'stream_the_stack_{today_str}.json'
    write_markdown(candidates, summary, md_path)
    write_json(candidates, summary, json_path)

    print(f'  -> {md_path}')
    print(f'  -> {json_path}')
    print_console_summary(candidates, summary)


if __name__ == '__main__':
    main()

"""build_hitter_boom_stack_daily — pre-batched hitter boom_stack for the
profiles dashboard Boom/Bust/Variance tab.

Mirror of `stream_the_stack.py` (the SP version), but for hitters. Pulls
MLB Stats API today+tomorrow scheduled games, identifies each team's
starting lineup (posted lineups when available; top-9 by rh3 fallback),
and runs `compute_hitter_boom_stack` per batter, emitting:

  data/outputs/hitter_boom_stack_<YYYY-MM-DD>.md
  data/outputs/hitter_boom_stack_<YYYY-MM-DD>.json

JSON schema mirrors the SP stream JSON so the profiles dashboard build
can consume it the same way (`by_batter` map keyed by str(batter_id)).

Usage:
  python -X utf8 scripts/xfp/build_hitter_boom_stack_daily.py
  python -X utf8 scripts/xfp/build_hitter_boom_stack_daily.py --days 2

Notes:
  - boom_stack is a DISPLAY TAG. See lib/hitter_boom_stack.py docstring.
  - Stack range is 0-4 (4 components incl. lineup_amp).
  - Fail-soft per-batter: a single bad lookup never crashes the batch.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / 'src'))

from scripts.xfp.lib.hitter_boom_stack import (  # noqa: E402
    compute_hitter_boom_stack,
    resolve_opp_sp_id_for_today,
    BOOM_RATE_BY_STACK,
    BUST_RATE_BY_STACK,
    MEAN_FP_PROXY_BY_STACK,
    _TEAM_ABBR_MAP,
)

_STATSAPI = 'https://statsapi.mlb.com/api/v1'
_RH3_CSV = _REPO_ROOT / 'data' / 'outputs' / 'xfp_rh3_projections.csv'
_OUT_DIR = _REPO_ROOT / 'data' / 'outputs'


def _warn(section, exc):
    print(f"WARN {section}: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# MLB Stats API: today's games + lineups (or fallback set)
# ---------------------------------------------------------------------------
def fetch_games_and_lineups(start_d: date, end_d: date) -> list[dict]:
    """Return list of {game_date, home_abbr, away_abbr, home_lineup, away_lineup,
    home_sp_id, away_sp_id} where each lineup is a list[int] of batter MLBAM ids.

    Lineups come from MLB Stats API `hydrate=lineups` when posted; empty list
    when not yet posted (caller will fallback to top-9-by-rh3).
    """
    url = (
        f'{_STATSAPI}/schedule?sportId=1'
        f'&startDate={start_d.isoformat()}&endDate={end_d.isoformat()}'
        f'&hydrate=lineups,probablePitcher,team'
    )
    try:
        data = requests.get(url, timeout=20).json()
    except Exception as e:
        print(f'  ! MLB Stats API fetch failed: {e}', file=sys.stderr)
        return []

    out: list[dict] = []
    for d_block in data.get('dates', []):
        for game in d_block.get('games', []):
            game_date_str = game.get('gameDate', '')[:10]
            try:
                gd = datetime.fromisoformat(game_date_str).date()
            except Exception as e:
                _warn(f'game_date_parse({game_date_str!r})', e)
                continue
            if not (start_d <= gd <= end_d):
                continue
            home = (game.get('teams') or {}).get('home') or {}
            away = (game.get('teams') or {}).get('away') or {}
            home_abbr = ((home.get('team') or {}).get('abbreviation') or '?').upper()
            away_abbr = ((away.get('team') or {}).get('abbreviation') or '?').upper()

            lineups = game.get('lineups') or {}
            def _ids(side_key):
                pls = lineups.get(side_key) or []
                ids = []
                for p in pls:
                    pid = p.get('id')
                    if pid is not None:
                        try:
                            ids.append(int(pid))
                        except (TypeError, ValueError):
                            continue
                return ids
            home_lineup = _ids('homePlayers')
            away_lineup = _ids('awayPlayers')

            home_sp = (home.get('probablePitcher') or {}).get('id')
            away_sp = (away.get('probablePitcher') or {}).get('id')

            out.append({
                'game_date': gd.isoformat(),
                'home_abbr': home_abbr,
                'away_abbr': away_abbr,
                'home_lineup': home_lineup,
                'away_lineup': away_lineup,
                'home_sp_id': int(home_sp) if home_sp else None,
                'away_sp_id': int(away_sp) if away_sp else None,
            })
    return out


# ---------------------------------------------------------------------------
# rh3 loader (for fallback top-9 + headline projection)
# ---------------------------------------------------------------------------
def load_rh3() -> pd.DataFrame:
    df = pd.read_csv(_RH3_CSV)
    df['batter'] = df['batter'].astype('int64')
    return df


def top9_by_rh3(rh3_df: pd.DataFrame, team_abbr: str) -> list[int]:
    """Fallback: team's top 9 by xfp_rh3_per_game."""
    norm = _TEAM_ABBR_MAP.get(team_abbr.upper(), team_abbr.upper())
    cand = rh3_df[rh3_df['team'].str.upper().isin({team_abbr.upper(), norm})]
    if cand.empty:
        return []
    return [int(b) for b in cand.nlargest(9, 'xfp_rh3_per_game')['batter'].tolist()]


# ---------------------------------------------------------------------------
# Per-batter compute
# ---------------------------------------------------------------------------
def _summarize_detail(detail: dict) -> dict:
    """Compact the per-component diagnostic for the JSON sidecar — mirrors the
    SP `_summarize_boom_detail` shape so the profiles renderer can chip it.
    """
    out: dict = {}
    ss = detail.get('skill_spike_hitter', {}) or {}
    if ss:
        out['skill_spike_hitter'] = {
            'n_games_2026': ss.get('n_games_2026'),
            'delta_xwoba': round(ss['delta_xwoba'], 4) if 'delta_xwoba' in ss else None,
            'delta_k_pp': round(ss['delta_k_pp'], 2) if 'delta_k_pp' in ss else None,
            'season_xwoba': round(ss['season_xwoba'], 4) if 'season_xwoba' in ss else None,
            'last10_xwoba': round(ss['last10_xwoba'], 4) if 'last10_xwoba' in ss else None,
            'reason': ss.get('reason'),
        }
    rf = detail.get('recform_hot_hitter', {}) or {}
    if rf:
        out['recform_hot_hitter'] = {
            'n_games_2026': rf.get('n_games_2026'),
            'season_fp_proxy_per_g': round(rf['season_fp_proxy_per_g'], 2) if 'season_fp_proxy_per_g' in rf else None,
            'last10_fp_proxy_per_g': round(rf['last10_fp_proxy_per_g'], 2) if 'last10_fp_proxy_per_g' in rf else None,
            'delta': round(rf['delta'], 2) if 'delta' in rf else None,
            'reason': rf.get('reason'),
        }
    os_ = detail.get('opp_soft_hitter', {}) or {}
    if os_:
        out['opp_soft_hitter'] = {
            'opp_sp_id': os_.get('opp_sp_id'),
            'opp_sp_rp3_per_start': round(os_['opp_sp_rp3_per_start'], 2) if 'opp_sp_rp3_per_start' in os_ else None,
            'soft_p33_threshold': round(os_['soft_p33_threshold'], 2) if 'soft_p33_threshold' in os_ else None,
            'reason': os_.get('reason'),
        }
    la = detail.get('lineup_amp_hitter', {}) or {}
    if la:
        out['lineup_amp_hitter'] = {
            'team': la.get('team'),
            'own_components_total': la.get('own_components_total'),
            'teammates_checked': la.get('teammates_checked'),
            'n_teammates_lit': la.get('n_teammates_lit'),
            'reason': la.get('reason'),
        }
    return out


def build_candidate(batter_id: int, team_abbr: str, opp_team: str,
                    is_home: bool, game_date: str, opp_sp_id: Optional[int],
                    rh3_row: Optional[pd.Series], today: date) -> Optional[dict]:
    """Compute boom_stack for one batter + pack into the JSON candidate shape."""
    try:
        bs = compute_hitter_boom_stack(
            batter_id=int(batter_id),
            opp_sp_id=opp_sp_id,
            today=today,
            team=team_abbr,
        )
    except Exception as e:
        print(f'    ! boom_stack failed for batter={batter_id}: {e}', file=sys.stderr)
        return None

    # rh3 headline fields
    rh3_per_game = rh3_p25 = rh3_p75 = None
    rh3_rank = None
    sigma = None
    signal = None
    player_name = None
    if rh3_row is not None:
        def _f(k):
            v = rh3_row.get(k)
            try:
                return float(v) if pd.notna(v) else None
            except Exception:
                return None
        rh3_per_game = _f('xfp_rh3_per_game')
        rh3_p25 = _f('xfp_rh3_p25')
        rh3_p75 = _f('xfp_rh3_p75')
        sigma = _f('xfp_rh3_sigma')
        try:
            rh3_rank = int(rh3_row['rank']) if pd.notna(rh3_row.get('rank')) else None
        except Exception:
            rh3_rank = None
        signal = rh3_row.get('signal') if 'signal' in rh3_row.index else None
        player_name = rh3_row.get('player_name')

    # Matchup tier from opp SP — invert SP framing: weak opp SP = "soft" matchup
    # for the hitter. We already get this signal via opp_soft_hitter component.
    opp_soft_detail = (bs.get('detail') or {}).get('opp_soft_hitter') or {}
    opp_proj = opp_soft_detail.get('opp_sp_rp3_per_start')
    p33 = opp_soft_detail.get('soft_p33_threshold')
    if opp_proj is None or p33 is None:
        matchup_tier = 'unknown'
    elif opp_proj <= p33:
        matchup_tier = 'soft'
    elif opp_proj <= p33 + 4.0:  # rough upper third boundary
        matchup_tier = 'neutral'
    else:
        matchup_tier = 'tough'

    return {
        'batter_id': int(batter_id),
        'player_name': player_name,
        'team': team_abbr,
        'opp_team': opp_team,
        'is_home': is_home,
        'game_date': game_date,
        'opp_sp_id': opp_sp_id,
        'rh3_rank': rh3_rank,
        'rh3_per_game': rh3_per_game,
        'rh3_p25': rh3_p25,
        'rh3_p75': rh3_p75,
        'rh3_sigma': sigma,
        'rh3_signal': signal,
        'matchup_tier': matchup_tier,
        'boom_stack': bs.get('boom_stack'),
        'boom_components': bs.get('components'),
        'boom_detail_summary': _summarize_detail(bs.get('detail') or {}),
        'boom_rate_expected': bs.get('boom_rate_expected'),
        'bust_rate_expected': bs.get('bust_rate_expected'),
        'boom_mean_fp_expected': bs.get('mean_fp_proxy_expected'),
    }


# ---------------------------------------------------------------------------
# Main assembly
# ---------------------------------------------------------------------------
def assemble_candidates(days: int) -> tuple[list[dict], dict]:
    today = date.today()
    end_d = today + timedelta(days=days - 1)
    print(f'Window: {today} → {end_d} ({days} days)')

    games = fetch_games_and_lineups(today, end_d)
    print(f'  {len(games)} scheduled games in window')

    rh3 = load_rh3()
    rh3_by_batter = {int(r['batter']): r for _, r in rh3.iterrows()}

    candidates: list[dict] = []
    seen: set[tuple[int, str]] = set()  # (batter_id, game_date)

    n_confirmed_lineups = 0
    n_fallback_lineups = 0

    for game in games:
        gd = game['game_date']
        for side, team_abbr, opp_team, lineup, opp_sp_id, is_home in (
            ('home', game['home_abbr'], game['away_abbr'], game['home_lineup'], game['away_sp_id'], True),
            ('away', game['away_abbr'], game['home_abbr'], game['away_lineup'], game['home_sp_id'], False),
        ):
            if lineup:
                n_confirmed_lineups += 1
                batters = lineup
            else:
                batters = top9_by_rh3(rh3, team_abbr)
                if batters:
                    n_fallback_lineups += 1
            for bid in batters:
                key = (int(bid), gd)
                if key in seen:
                    continue
                seen.add(key)
                rh3_row = rh3_by_batter.get(int(bid))
                # Use the per-team API lookup if opp_sp_id missing here
                opp_for_batter = opp_sp_id
                if opp_for_batter is None:
                    try:
                        opp_for_batter = resolve_opp_sp_id_for_today(team_abbr, today)
                    except Exception as e:
                        _warn(f'resolve_opp_sp({team_abbr})', e)
                        opp_for_batter = None
                cand = build_candidate(
                    batter_id=int(bid),
                    team_abbr=team_abbr,
                    opp_team=opp_team,
                    is_home=is_home,
                    game_date=gd,
                    opp_sp_id=opp_for_batter,
                    rh3_row=rh3_row,
                    today=today,
                )
                if cand is not None:
                    candidates.append(cand)

    print(f'  lineups: {n_confirmed_lineups} confirmed, {n_fallback_lineups} top-9-fallback')
    print(f'  {len(candidates)} batter-game candidates computed')

    dist = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 'none': 0}
    for c in candidates:
        bs = c['boom_stack']
        if bs is None:
            dist['none'] += 1
        else:
            dist[bs] = dist.get(bs, 0) + 1

    summary = {
        'window_start': today.isoformat(),
        'window_end': end_d.isoformat(),
        'n_games_in_window': len(games),
        'n_confirmed_lineups': n_confirmed_lineups,
        'n_fallback_lineups': n_fallback_lineups,
        'n_candidates': len(candidates),
        'boom_stack_distribution': {str(k): v for k, v in dist.items()},
    }
    return candidates, summary


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
    lines: list[str] = []
    lines.append(f'# hitter_boom_stack — {summary["window_start"]} → {summary["window_end"]}')
    lines.append('')
    lines.append(
        f'Batter-game candidates: **{summary["n_candidates"]}** '
        f'(across {summary["n_games_in_window"]} games; '
        f'{summary["n_confirmed_lineups"]} confirmed lineups, '
        f'{summary["n_fallback_lineups"]} top-9 fallback).'
    )
    lines.append('')
    lines.append(f'Boom-stack distribution: {summary["boom_stack_distribution"]}.')
    lines.append('')
    lines.append('> boom_stack = skill_spike_hitter + recform_hot_hitter + opp_soft_hitter + lineup_amp_hitter (each 0|1). '
                 'See `lib/hitter_boom_stack.py`. DISPLAY TAG only; rh3 carries the point estimate.')
    lines.append('')

    by_stack: dict[int, list[dict]] = {0: [], 1: [], 2: [], 3: [], 4: []}
    for c in candidates:
        bs = c['boom_stack']
        if bs in by_stack:
            by_stack[bs].append(c)

    for stack in (4, 3, 2):
        rows = by_stack[stack]
        rows = sorted(rows, key=lambda r: (r['rh3_per_game'] or -999), reverse=True)
        lines.append(f'## STACK={stack} candidates (n={len(rows)})')
        lines.append('')
        if not rows:
            lines.append('_(none today)_')
            lines.append('')
            continue
        lines.append('| batter | team | date | opp | rh3 (p25–p75) | stack | boom% exp | matchup |')
        lines.append('|---|---|---|---|---|---|---|---|')
        for c in rows:
            ha = 'vs' if c.get('is_home') else '@'
            rh3_cell = (
                f'{_fmt(c["rh3_per_game"], ".2f")} '
                f'({_fmt(c["rh3_p25"], ".2f")}-{_fmt(c["rh3_p75"], ".2f")})'
                + (f' #{c["rh3_rank"]}' if c.get('rh3_rank') is not None else '')
            )
            lines.append(
                f'| {c.get("player_name") or c["batter_id"]} | {c["team"]} | {c["game_date"]} | '
                f'{ha}{c["opp_team"]} | {rh3_cell} | {c["boom_stack"]}/4 | '
                f'{_fmt((c["boom_rate_expected"] or 0)*100, ".1f")}% | {c["matchup_tier"]} |'
            )
        lines.append('')

    lines.append('---')
    lines.append('')
    lines.append('### Diagnostic footer')
    lines.append('')
    lines.append(f'- Games in window: {summary["n_games_in_window"]}')
    lines.append(f'- Confirmed lineups: {summary["n_confirmed_lineups"]}')
    lines.append(f'- Top-9-by-rh3 fallbacks: {summary["n_fallback_lineups"]}')
    lines.append(f'- Candidates computed: {summary["n_candidates"]}')
    lines.append('')

    out_path.write_text('\n'.join(lines), encoding='utf-8')


def write_json(candidates: list[dict], summary: dict, out_path: Path) -> None:
    payload = {
        'summary': summary,
        'candidates': candidates,
        'generated_at': datetime.now().isoformat(),
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding='utf-8')


def print_console_summary(candidates: list[dict], summary: dict) -> None:
    print()
    print('=' * 78)
    print(f'hitter_boom_stack — {summary["window_start"]} → {summary["window_end"]}')
    print('=' * 78)
    dist = summary['boom_stack_distribution']
    print(f'Distribution: stack=4:{dist.get("4", 0)}  stack=3:{dist.get("3", 0)}  '
          f'stack=2:{dist.get("2", 0)}  stack=1:{dist.get("1", 0)}  '
          f'stack=0:{dist.get("0", 0)}  none:{dist.get("none", 0)}')
    print()
    stack_3plus = [c for c in candidates if (c['boom_stack'] or 0) >= 3]
    if stack_3plus:
        stack_3plus = sorted(stack_3plus, key=lambda r: (r['rh3_per_game'] or -999), reverse=True)
        print(f'STACK=3+ candidates ({len(stack_3plus)}):')
        for c in stack_3plus[:20]:
            ha = 'vs' if c.get('is_home') else '@'
            print(
                f'  [{c["boom_stack"]}/4] {(c.get("player_name") or str(c["batter_id"])):<24s} '
                f'{c["team"]} {ha}{c["opp_team"]} {c["game_date"]}  '
                f'rh3={_fmt(c["rh3_per_game"], ".2f")} '
                f'(rank #{c["rh3_rank"] if c.get("rh3_rank") is not None else "—"})  '
                f'boom%~{_fmt((c["boom_rate_expected"] or 0)*100, ".1f")}%'
            )
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--days', type=int, default=2,
                    help='Days forward from today (inclusive). Default 2 (today + tomorrow).')
    args = ap.parse_args()

    candidates, summary = assemble_candidates(days=args.days)

    today_str = summary['window_start']
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = _OUT_DIR / f'hitter_boom_stack_{today_str}.md'
    json_path = _OUT_DIR / f'hitter_boom_stack_{today_str}.json'
    write_markdown(candidates, summary, md_path)
    write_json(candidates, summary, json_path)

    print(f'  -> {md_path}')
    print(f'  -> {json_path}')
    print_console_summary(candidates, summary)


if __name__ == '__main__':
    main()

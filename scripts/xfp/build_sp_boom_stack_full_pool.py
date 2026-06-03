"""build_sp_boom_stack_full_pool — pre-batch boom_stack for the ENTIRE SP universe.

Companion to stream_the_stack.py. stream_the_stack only covers SPs with a
confirmed probable in the rolling 3-day window (~15-25 SPs). This script covers
ALL ~300 SPs in xfp_rp3_projections.csv so the profiles dashboard's Boom/Bust
tab populates for ANY rostered/relevant SP, not just imminent starters.

For each SP:
  - compute_boom_stack(pid, recency_form_gap, next_opp_team, rp3_rank)
  - compute_high_k_pitcher(pid)
  - compute_catcher_framing(modal_team)
  - compute_il_return_flag(pid)

When `next_opp_team` is missing (no scheduled probable), opp_soft and
park_friendly silently degrade to 0 but the rest still computes — the
record is emitted with `has_upcoming_start=False` and a `season_only_tags`
block carrying HIGH-K / catcher framing / IL return signals that don't
depend on a confirmed start.

Outputs:
  data/outputs/sp_boom_stack_full_pool_<YYYY-MM-DD>.json
  data/outputs/sp_boom_stack_full_pool_<YYYY-MM-DD>.md

JSON schema is a SUPERSET of stream_the_stack so the existing consumer
(build_player_profiles_dashboard.load_boom_stack_payload) keeps working.
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / 'src'))

from scripts.xfp.lib.boom_stack import (  # noqa: E402
    compute_boom_stack,
    compute_high_k_pitcher,
)
from scripts.xfp.lib.catcher_framing import compute_catcher_framing  # noqa: E402
from scripts.xfp.lib.il_return_flag import compute_il_return_flag  # noqa: E402
from scripts.xfp.stream_the_stack import fetch_confirmed_probables  # noqa: E402
from datetime import timedelta  # noqa: E402

_RP3_CSV = _REPO_ROOT / 'data' / 'outputs' / 'xfp_rp3_projections.csv'
_PITCHER_SCHEDULE = _REPO_ROOT / 'data' / 'research' / 'xfp_cache' / 'pitcher_schedule_2026.csv'
_SP_MULTIYR = _REPO_ROOT / 'data' / 'research' / 'xfp_cache' / 'sp_multiyr_2015_2025.csv'
_TEAM_STRENGTH = _REPO_ROOT / 'data' / 'research' / 'xfp_cache' / 'team_strength_2026.csv'
_OUT_DIR = _REPO_ROOT / 'data' / 'outputs'


def _summarize_boom_detail(detail: dict) -> dict:
    """Mirror stream_the_stack._summarize_boom_detail for JSON-side compactness."""
    if not detail:
        return {}
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
    pf = detail.get('park_friendly', {})
    if pf:
        out['park_friendly'] = {
            'park_team': pf.get('park_team'),
            'pf_wOBA': round(pf['pf_wOBA'], 4) if pf.get('pf_wOBA') is not None else None,
            'reason': pf.get('reason'),
        }
    return out


def _load_team_strength_map() -> dict:
    try:
        ts = pd.read_csv(_TEAM_STRENGTH)
        return {row['team']: row for _, row in ts.iterrows()}
    except Exception:
        return {}


def _load_modal_team_map() -> dict[int, str]:
    """Build {pitcher_id: modal_team} from pitcher_schedule + sp_multiyr fallback.

    For SPs without ANY scheduled start (e.g. Hunter Greene with no 2026 starts),
    fall back to the most-recent-year team in sp_multiyr.
    """
    modal: dict[int, str] = {}
    try:
        sched = pd.read_csv(_PITCHER_SCHEDULE)
        sched['pitcher'] = sched['pitcher'].astype('int64', errors='ignore')
        # Modal 3-letter abbrev across the pitcher's scheduled rows. `team` is
        # the full team name (e.g. 'Atlanta Braves'); `team_abbrev` is the
        # 3-letter code (e.g. 'ATL') that catcher_framing keys on.
        team_col = 'team_abbrev' if 'team_abbrev' in sched.columns else 'team'
        for pid, grp in sched.groupby('pitcher'):
            mode = grp[team_col].mode()
            if not mode.empty:
                modal[int(pid)] = str(mode.iloc[0])
    except Exception as e:
        print(f'  ! pitcher_schedule load failed: {e}', file=sys.stderr)

    # Fallback: derive pitcher_team from 2026 statcast (home_team when
    # inning_topbot=='Top', else away_team). Catches IL'd / no-2026-start SPs
    # that have ANY 2026 pitches (e.g. Glasnow). For zero-2026-start SPs
    # (e.g. Greene), this still yields None — accepted; framing degrades to None.
    try:
        import numpy as np
        sc = pd.read_parquet(
            _REPO_ROOT / 'data' / 'research' / 'xfp_cache' / 'statcast_2026.parquet',
            columns=['pitcher', 'home_team', 'away_team', 'inning_topbot'],
        )
        sc['pitcher_team'] = np.where(
            sc['inning_topbot'] == 'Top', sc['home_team'], sc['away_team']
        )
        sc['pitcher'] = sc['pitcher'].astype('int64', errors='ignore')
        sc_modal = (
            sc.groupby('pitcher')['pitcher_team']
              .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else None)
        )
        for pid, team in sc_modal.items():
            if team is not None and pd.notna(team):
                modal.setdefault(int(pid), str(team))
    except Exception as e:
        print(f'  ! statcast modal-team fallback failed: {e}', file=sys.stderr)

    return modal


def _next_scheduled_for(pid: int, sched_by_pid: dict) -> dict:
    """Return next-start dict {game_date, opp_team, team, is_home} or {} if none."""
    rows = sched_by_pid.get(int(pid))
    if rows is None or rows.empty:
        return {}
    rows = rows.copy()
    rows['game_date'] = pd.to_datetime(rows['game_date'])
    today = pd.Timestamp(date.today())
    future = rows[rows['game_date'] >= today].sort_values('game_date')
    if future.empty:
        return {}
    r = future.iloc[0]
    # Prefer 3-letter abbreviations for downstream lookups.
    opp = r.get('opp_team_abbrev') if 'opp_team_abbrev' in r and pd.notna(r.get('opp_team_abbrev')) else r.get('opp_team')
    team = r.get('team_abbrev') if 'team_abbrev' in r and pd.notna(r.get('team_abbrev')) else r.get('team')
    return {
        'game_date': r['game_date'].strftime('%Y-%m-%d'),
        'opp_team': opp,
        'team': team,
        'is_home': bool(r.get('is_home')) if pd.notna(r.get('is_home')) else None,
    }


def build_candidates() -> tuple[list[dict], dict]:
    rp3 = pd.read_csv(_RP3_CSV)
    rp3['pitcher'] = rp3['pitcher'].astype('int64')
    print(f'  {len(rp3)} SPs in xfp_rp3_projections.csv')

    modal_team_map = _load_modal_team_map()
    ts_map = _load_team_strength_map()

    # Pre-build sched_by_pid so _next_scheduled_for is O(1). Combines the cached
    # pitcher_schedule file (historical) with a fresh MLB Stats API probables
    # pull for the next 3 days (forward) so we actually see upcoming starts.
    sched_by_pid: dict = {}
    try:
        sched = pd.read_csv(_PITCHER_SCHEDULE)
        sched['pitcher'] = sched['pitcher'].astype('int64', errors='ignore')
        for pid, grp in sched.groupby('pitcher'):
            sched_by_pid[int(pid)] = grp
    except Exception as e:
        print(f'  ! pitcher_schedule load for next-start lookup failed: {e}', file=sys.stderr)

    # Live probables (next 3 days, forward) — augments the stale cache.
    try:
        today = date.today()
        end = today + timedelta(days=3)
        probs = fetch_confirmed_probables(today, end)
        if probs:
            extra_rows = []
            for p in probs:
                extra_rows.append({
                    'pitcher': int(p['pitcher_id']),
                    'game_date': p['game_date'],
                    'team': p.get('team_abbr'),
                    'opp_team': p.get('opp_abbr'),
                    'opp_team_abbrev': p.get('opp_abbr'),
                    'is_home': p.get('is_home'),
                })
            extra_df = pd.DataFrame(extra_rows)
            for pid, grp in extra_df.groupby('pitcher'):
                prior = sched_by_pid.get(int(pid))
                if prior is None:
                    sched_by_pid[int(pid)] = grp
                else:
                    sched_by_pid[int(pid)] = pd.concat([prior, grp], ignore_index=True)
            print(f'  fetched {len(probs)} live probables (today + {3} days)')
    except Exception as e:
        print(f'  ! live probables fetch failed: {e}', file=sys.stderr)

    candidates: list[dict] = []
    n_with_start = 0
    n_season_only = 0
    n_errors = 0

    for _, row in rp3.iterrows():
        pid = int(row['pitcher'])
        name = row.get('player_name') or ''
        rp3_rank = int(row['rank']) if pd.notna(row.get('rank')) else None
        rp3_per_start = float(row['xfp_rp3_per_start']) if pd.notna(row.get('xfp_rp3_per_start')) else None
        rp3_p25 = float(row['xfp_rp3_p25']) if pd.notna(row.get('xfp_rp3_p25')) else None
        rp3_p75 = float(row['xfp_rp3_p75']) if pd.notna(row.get('xfp_rp3_p75')) else None
        rfg = float(row['recency_form_gap']) if pd.notna(row.get('recency_form_gap')) else None
        dq_tag = row.get('data_quality_tag')
        rp3_signal = row.get('signal')
        next_opp_team = row.get('next_opp_team') if pd.notna(row.get('next_opp_team')) else None

        # Next-start window info (game_date / is_home / team) from pitcher_schedule.
        next_start = _next_scheduled_for(pid, sched_by_pid)
        has_upcoming_start = bool(next_start)
        # Prefer the rp3 next_opp_team (already aligned with rp3 projection
        # context); fall back to schedule if rp3 missing one.
        opp_for_boom = next_opp_team or next_start.get('opp_team')

        try:
            bs = compute_boom_stack(
                pitcher_id=pid,
                recency_form_gap=rfg,
                next_opp_team=opp_for_boom,
                rp3_rank=rp3_rank,
            )
        except Exception as e:
            n_errors += 1
            print(f'    ! compute_boom_stack failed for {name} ({pid}): {e}', file=sys.stderr)
            bs = None

        try:
            hk = compute_high_k_pitcher(pid)
        except Exception as e:
            print(f'    ! compute_high_k_pitcher failed for {name} ({pid}): {e}', file=sys.stderr)
            hk = None

        modal_team = modal_team_map.get(pid) or next_start.get('team')
        try:
            framing = compute_catcher_framing(modal_team)
        except Exception as e:
            print(f'    ! compute_catcher_framing failed for {name} ({pid}): {e}', file=sys.stderr)
            framing = None

        try:
            il = compute_il_return_flag(pid)
        except Exception as e:
            print(f'    ! compute_il_return_flag failed for {name} ({pid}): {e}', file=sys.stderr)
            il = None

        # opp bat_index_recent for matchup_tier
        opp_bri = None
        if opp_for_boom and opp_for_boom in ts_map:
            v = ts_map[opp_for_boom].get('bat_index_recent')
            opp_bri = float(v) if pd.notna(v) else None

        if opp_bri is None:
            matchup_tier = 'unknown'
        elif opp_bri <= 0.97:
            matchup_tier = 'soft'
        elif opp_bri <= 1.03:
            matchup_tier = 'neutral'
        else:
            matchup_tier = 'tough'

        # Season-only tags (always populated; useful when has_upcoming_start=False)
        season_only_tags = {
            'high_k_pitcher': hk,
            'catcher_framing': framing,
            'il_return': il,
        }

        rec = {
            'pitcher_id': pid,
            'pitcher_name': name,
            'team': modal_team,
            'opp_team': opp_for_boom,
            'is_home': next_start.get('is_home'),
            'game_date': next_start.get('game_date'),
            'has_upcoming_start': has_upcoming_start,
            'rp3_rank': rp3_rank,
            'rp3_per_start': rp3_per_start,
            'rp3_p25': rp3_p25,
            'rp3_p75': rp3_p75,
            'rp3_signal': rp3_signal,
            'data_quality_tag': dq_tag,
            'recency_form_gap': rfg,
            'opp_bat_index_recent': opp_bri,
            'matchup_tier': matchup_tier,
            'boom_stack': bs['boom_stack'] if bs else None,
            'boom_components': bs['components'] if bs else None,
            'boom_detail_summary': _summarize_boom_detail(bs['detail']) if bs else None,
            'boom_rate_expected': bs['boom_rate_expected'] if bs else None,
            'boom_bust_rate_expected': bs.get('bust_rate_expected') if bs else None,
            'boom_mean_fp_expected': bs['mean_fp_expected'] if bs else None,
            'tier': bs.get('tier') if bs else None,
            'skill_spike_anti_predictive': bs.get('skill_spike_anti_predictive') if bs else None,
            'season_only_tags': season_only_tags,
            # Window-active stream_the_stack rows leave these blank; mirror them.
            'percent_owned': None,
            'pro_team': None,
            'injury_status': None,
        }
        candidates.append(rec)
        if has_upcoming_start:
            n_with_start += 1
        else:
            n_season_only += 1

    summary = {
        'window_start': date.today().isoformat(),
        'window_end': date.today().isoformat(),
        'n_sps_total': len(rp3),
        'n_with_upcoming_start': n_with_start,
        'n_season_only': n_season_only,
        'n_errors': n_errors,
    }
    return candidates, summary


def write_json(candidates: list[dict], summary: dict, out_path: Path) -> None:
    payload = {
        'summary': summary,
        'candidates': candidates,
        'generated_at': datetime.now().isoformat(),
        'source': 'build_sp_boom_stack_full_pool',
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding='utf-8')


def write_markdown(candidates: list[dict], summary: dict, out_path: Path) -> None:
    def composite(c):
        bs = c['boom_stack'] if c['boom_stack'] is not None else -1
        rp3 = c['rp3_per_start'] if c['rp3_per_start'] is not None else -999
        return (-bs, -rp3)

    ranked = sorted(candidates, key=composite)
    top20 = ranked[:20]

    lines = []
    lines.append(f'# sp_boom_stack_full_pool — {summary["window_start"]}')
    lines.append('')
    lines.append(
        f'SPs processed: **{summary["n_sps_total"]}** '
        f'(upcoming start: {summary["n_with_upcoming_start"]}, '
        f'season-only: {summary["n_season_only"]}, errors: {summary["n_errors"]}).'
    )
    lines.append('')
    lines.append('## Top 20 by composite (boom_stack desc, rp3 desc)')
    lines.append('')
    lines.append('| pitcher | rank | rp3 | tier | stack | upcoming | opp | matchup | HIGH-K | framing |')
    lines.append('|---|---|---|---|---|---|---|---|---|---|')
    for c in top20:
        hk = (c.get('season_only_tags') or {}).get('high_k_pitcher') or {}
        cf = (c.get('season_only_tags') or {}).get('catcher_framing') or {}
        hk_cell = 'Y' if hk.get('is_high_k') else '—'
        cf_cell = ('ELITE' if cf.get('is_elite_framer')
                   else ('TAX' if cf.get('is_framing_tax') else '—'))
        bs = c['boom_stack'] if c['boom_stack'] is not None else '—'
        lines.append(
            f'| {c["pitcher_name"]} | {c.get("rp3_rank") or "—"} | '
            f'{(round(c["rp3_per_start"],1) if c["rp3_per_start"] is not None else "—")} | '
            f'{c.get("tier") or "—"} | {bs} | '
            f'{"Y" if c["has_upcoming_start"] else "—"} | '
            f'{c.get("opp_team") or "—"} | {c["matchup_tier"]} | '
            f'{hk_cell} | {cf_cell} |'
        )
    lines.append('')
    out_path.write_text('\n'.join(lines), encoding='utf-8')


def main():
    print('Building sp_boom_stack_full_pool ...')
    candidates, summary = build_candidates()
    today_str = summary['window_start']
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = _OUT_DIR / f'sp_boom_stack_full_pool_{today_str}.json'
    md_path = _OUT_DIR / f'sp_boom_stack_full_pool_{today_str}.md'
    write_json(candidates, summary, json_path)
    write_markdown(candidates, summary, md_path)
    print(f'  -> {json_path}')
    print(f'  -> {md_path}')
    print(f'  total: {summary["n_sps_total"]}  '
          f'upcoming: {summary["n_with_upcoming_start"]}  '
          f'season-only: {summary["n_season_only"]}  '
          f'errors: {summary["n_errors"]}')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        sys.exit(1)

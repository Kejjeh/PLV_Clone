"""Per-player synthetic calibration backfill with lineup-slot annotation.

Richer companion to ``build_synthetic_calibration_panel.py`` — instead of
emitting only team-total per-week rows, this walks every closed scoring
period of 2024 + 2025 in the BrownU league and emits one row per
(period, team, player) with:

  * lineup_slot (game-time slot — the slot-aware question's load-bearing field)
  * was_active (slot not in {BE, IL, IR})
  * projected_fp_naive_avg — Bayesian-shrunk season-to-date per-player FP/g
  * projected_fp_last5 — mean of player's last-5 actual scoring-period FP/g
  * actual_fp — what they actually scored that period
  * residuals against each projection

What this enables (per slot_aware_fp_test.md):
  * Slot-aware projection mechanism test (does BE actually score less than
    active for the same player-week?)
  * Per-player residual decomposition
  * Cross-validation of the existing team-total predictions_history.csv

What this is NOT:
  * Not a substitute for rh3/rp3 projections. The projection columns are
    last-N-games proxies, used to ISOLATE the slot/structural question
    independent of model quality.

Output: ``data/research/calibration_panel_per_player.parquet`` (atomic write).
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data' / 'research' / 'calibration_panel_per_player.parquet'
TEAM_OUT = ROOT / 'data' / 'research' / 'calibration_panel_team_rollup.parquet'
load_dotenv(ROOT / '.env')

# Make the src layout importable.
from plv_clone.utils.name_match import resolve_batter_id, resolve_pitcher_id  # noqa: E402

BE_SLOTS = {'BE', 'IL', 'IR'}
PITCHER_POS = {'SP', 'RP', 'P'}


# Auth home is plv_clone.espn (single source): get_league(year) carries the
# credential check, retry/backoff, and auth-error fast-fail this bare copy
# lacked, and is year-aware for the multi-year backfill loop.
from plv_clone.espn import get_league as _get_league  # noqa: E402


def _resolve_mlbam(name: str, position: str, pro_team: Optional[str]) -> Optional[int]:
    """Best-effort name→MLBAM resolution using the name_match helpers.

    Returns None on failure — caller keeps the row but mlbam_id is NaN."""
    try:
        if position and position.upper() in PITCHER_POS:
            role = 'SP' if position.upper() == 'SP' else ('RP' if position.upper() == 'RP' else None)
            return resolve_pitcher_id(name, team=pro_team, role=role)
        return resolve_batter_id(name, team=pro_team, position=position)
    except Exception:
        return None


def _bayes_shrunk_avg(player_history: list[float], league_mu: float, prior_k: float) -> float:
    """Bayesian-shrunk season-to-date FP/g toward league mean.

    player_history: per-period FP totals BEFORE the projected period.
    """
    n = len(player_history)
    if n == 0:
        return float(league_mu)
    team_mu = float(sum(player_history) / n)
    return (n * team_mu + prior_k * league_mu) / (n + prior_k)


def _last_n_avg(player_history: list[float], n: int = 5) -> Optional[float]:
    if not player_history:
        return None
    h = player_history[-n:]
    return float(sum(h) / len(h))


def build_year(year: int, prior_k: float = 3.0) -> pd.DataFrame:
    league = _get_league(year)
    reg_weeks = int(getattr(league.settings, 'reg_season_count', 20))
    print(f'[{year}] regular season weeks: {reg_weeks}')

    # Step 1: walk every period and collect (period, team_id, team_name, player_name,
    # position, pro_team, slot, points). We need this raw before we can compute
    # per-player rolling projections.
    # ESPN historical quirk: `box_scores(matchup_period=mp)` returns the
    # correct matchup arrangement and the canonical `home_score` total for
    # that week, but home_lineup/away_lineup come back empty. Supplying
    # `scoring_period=sp` populates lineups, but only for that single day.
    # So we must iterate sp values within each mp and SUM player points.
    # We discover the sp range per mp adaptively: start where the previous
    # mp ended, expand sp by 1 until cumulative active points match
    # home_score (within tolerance). This avoids the ~4k-call brute force.

    def _aggregate_sp(mp: int, sp: int, player_pts: dict, team_info: dict,
                      team_totals: dict, team_target: dict):
        """Pull one scoring_period for one matchup_period; mutate caches."""
        try:
            bs_list = league.box_scores(matchup_period=mp, scoring_period=sp)
        except Exception as e:
            print(f'    mp{mp} sp{sp}: fetch failed {e}')
            return
        for bs in bs_list:
            for side in ('home', 'away'):
                team = getattr(bs, f'{side}_team', None)
                lineup = getattr(bs, f'{side}_lineup', []) or []
                if team is None or team == 0:
                    continue
                team_id = getattr(team, 'team_id', None)
                if team_id is None:
                    continue
                team_info.setdefault(team_id, {
                    'team_name': getattr(team, 'team_name', '') or '',
                })
                team_target[team_id] = float(getattr(bs, f'{side}_score', 0.0) or 0.0)
                for bp in lineup:
                    pos = getattr(bp, 'position', '') or ''
                    slot = getattr(bp, 'slot_position', '') or ''
                    pts = float(getattr(bp, 'points', 0.0) or 0.0)
                    pro = getattr(bp, 'proTeam', '') or ''
                    key = (team_id, bp.name, pos, pro)
                    rec = player_pts.setdefault(key, {'slot': slot, 'pts': 0.0})
                    rec['pts'] += pts
                    if slot not in BE_SLOTS:
                        rec['slot'] = slot
                    if pts != 0.0 and slot not in BE_SLOTS:
                        team_totals[team_id] = team_totals.get(team_id, 0.0) + pts

    rows = []
    sp_cursor = 1  # rolling scoring_period start
    sp_hard_cap = 220  # safety
    TOL = 30.0  # cumulative-pts tolerance — generous to avoid overrun into next mp
    MAX_SPAN = 9   # typical mp = 7 days; cap tight to prevent next-mp bleed
    MIN_SPAN = 5   # min days before allowing early-stop

    for period in range(1, reg_weeks + 1):
        player_pts: dict[tuple, dict] = {}
        team_info: dict[int, dict] = {}
        team_totals: dict[int, float] = {}
        team_target: dict[int, float] = {}
        sp_start = sp_cursor
        sp = sp_start
        sps_consumed = 0
        prev_totals = None
        # Opening matchup runs long (MLB opening week is ~13 days).
        max_span = 14 if period == 1 else MAX_SPAN
        # Expand sp range until summed active pts ≈ home_score for all teams.
        while sp <= sp_hard_cap and sps_consumed < max_span:
            _aggregate_sp(period, sp, player_pts, team_info, team_totals, team_target)
            sps_consumed += 1
            sp += 1
            if not team_target:
                # No matchup data for this mp at all — stop early.
                break
            done = all(
                abs(team_totals.get(tid, 0.0) - team_target.get(tid, 0.0)) <= TOL
                for tid in team_target
            )
            if done and sps_consumed >= MIN_SPAN:
                break
        sp_cursor = sp  # advance to next mp's start

        if not team_info:
            print(f'  p{period}: no lineup data (sp tried {sp_start}..{sp-1})')
            continue

        for (team_id, name, pos, pro), rec in player_pts.items():
            rows.append({
                'year': year,
                'period': period,
                'team_id': team_id,
                'team_name': team_info[team_id]['team_name'],
                'player_name': name,
                'position': pos,
                'pro_team': pro,
                'lineup_slot': rec['slot'],
                'actual_fp': rec['pts'],
            })
        # Reconciliation report
        diffs = ', '.join(
            f'{team_info[tid]["team_name"][:10]}:{team_totals.get(tid,0):.0f}/{team_target.get(tid,0):.0f}'
            for tid in sorted(team_target)
        )
        print(f'  p{period}: sp {sp_start}..{sp-1} ({sps_consumed} days), '
              f'{len(player_pts)} player-rows | {diffs}')

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['was_active'] = ~df['lineup_slot'].isin(BE_SLOTS)
    print(f'[{year}] raw player-period rows: {len(df)}; active share: {df["was_active"].mean():.2%}')

    # Step 2: compute league per-period mean of ACTIVE player FP/g for shrinkage.
    league_means_by_period = (
        df[df['was_active']]
        .groupby('period')['actual_fp']
        .mean()
        .to_dict()
    )
    # Use cumulative through period N-1 as the "league mean" prior.
    sorted_periods = sorted(league_means_by_period)

    def league_mu_through(p: int) -> float:
        prior_vals = [league_means_by_period[q] for q in sorted_periods if q < p]
        if not prior_vals:
            return 0.0
        return float(sum(prior_vals) / len(prior_vals))

    # Step 3: per-player rolling history. Sort by (player_name, period) and
    # compute the projection columns using ONLY periods strictly before the
    # current one.
    df = df.sort_values(['player_name', 'period']).reset_index(drop=True)
    projected_naive = []
    projected_last5 = []
    histories: dict[str, list[float]] = {}
    for r in df.itertuples(index=False):
        hist = histories.setdefault(r.player_name, [])
        lmu = league_mu_through(r.period)
        projected_naive.append(_bayes_shrunk_avg(hist, lmu, prior_k))
        projected_last5.append(_last_n_avg(hist, n=5))
        hist.append(r.actual_fp)
    df['projected_fp_naive_avg'] = projected_naive
    df['projected_fp_last5'] = projected_last5
    df['residual_naive'] = df['actual_fp'] - df['projected_fp_naive_avg']
    df['residual_last5'] = df.apply(
        lambda x: (x['actual_fp'] - x['projected_fp_last5'])
        if pd.notna(x['projected_fp_last5']) else pd.NA,
        axis=1,
    )

    # Step 4: resolve mlbam_id once per (name, position, pro_team) unique triple.
    print(f'[{year}] resolving mlbam ids for {df[["player_name","position","pro_team"]].drop_duplicates().shape[0]} unique players...')
    uniq = df[['player_name', 'position', 'pro_team']].drop_duplicates().reset_index(drop=True)
    mlbam = []
    for r in uniq.itertuples(index=False):
        mlbam.append(_resolve_mlbam(r.player_name, r.position, r.pro_team))
    uniq['mlbam_id'] = mlbam
    df = df.merge(uniq, on=['player_name', 'position', 'pro_team'], how='left')
    print(f'[{year}] mlbam resolved: {df["mlbam_id"].notna().mean():.1%}')

    df['is_synthetic'] = True
    df['backfill_year'] = year
    return df


def _box_scores_kwargs(league):
    # Helper: detect whether the installed espn-api supports a `year` kwarg
    # on box_scores. Older versions don't.
    try:
        import inspect
        return inspect.signature(league.box_scores).parameters
    except Exception:
        return {}


def write_panel(df: pd.DataFrame, path: Path) -> None:
    """Atomic parquet write — temp file → rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp.parquet')
    df.to_parquet(tmp, index=False)
    if path.exists():
        path.unlink()
    tmp.rename(path)
    print(f'Wrote {path} ({len(df)} rows).')


def team_rollup(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate active-only to team-week totals for cross-check vs
    predictions_history.csv."""
    active = df[df['was_active']].copy()
    grouped = active.groupby(['year', 'period', 'team_id', 'team_name'], as_index=False).agg(
        actual_team_fp=('actual_fp', 'sum'),
        projected_team_naive=('projected_fp_naive_avg', 'sum'),
        projected_team_last5=('projected_fp_last5', 'sum'),
        n_active=('player_name', 'count'),
    )
    grouped['residual_naive'] = grouped['actual_team_fp'] - grouped['projected_team_naive']
    return grouped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--years', nargs='+', type=int, default=[2024, 2025])
    ap.add_argument('--prior-k', type=float, default=3.0)
    ap.add_argument('--force', action='store_true',
                    help='rebuild even if output parquet exists')
    args = ap.parse_args()

    if OUT.exists() and not args.force:
        print(f'{OUT} already exists. Pass --force to rebuild. Skipping.')
        return

    panels = []
    for y in args.years:
        try:
            p = build_year(y, prior_k=args.prior_k)
            if not p.empty:
                panels.append(p)
        except Exception as e:
            print(f'[{y}] build failed: {e}')

    if not panels:
        print('No panels built. Exiting.')
        return

    full = pd.concat(panels, ignore_index=True)
    print('\n=== Panel summary ===')
    print('Rows by (year, period):')
    print(full.groupby(['year', 'period']).size().to_string())
    print('\nActive vs bench (overall):')
    print(full['was_active'].value_counts(dropna=False).to_string())
    print('\nSlot distribution:')
    print(full['lineup_slot'].value_counts().head(15).to_string())

    write_panel(full, OUT)
    rollup = team_rollup(full)
    write_panel(rollup, TEAM_OUT)


if __name__ == '__main__':
    main()

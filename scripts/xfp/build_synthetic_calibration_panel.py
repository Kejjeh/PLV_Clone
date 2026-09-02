"""Synthetic calibration backfill from prior-season ESPN box scores.

Walks every closed matchup period of `year` (default 2025) in the BrownU
league, generates an HONEST out-of-sample projection for each matchup using
ONLY information that would have been available before that week
(Bayesian-shrunk season-to-date team average), computes win_probability
via the same normal-CDF formula used in build_matchup_dashboard.py, and
appends the row to predictions_history.csv with `is_synthetic=True` and
`model_version='backfill_<year>_bayes_shrink'`.

What this validates:
  * The win-probability mechanism (gap / sigma -> normal CDF), independent
    of rh3/rp3 quality. Calibration here tells us whether OUR sigma and
    normal-approx assumption are well-tuned.
  * NOT the rh3/rp3 projection itself. For that, we still need live 2026
    weeks to close out.

Honesty caveats baked in:
  * Skip period 1 (no prior data to shrink to).
  * Skip playoff weeks (period > regular_season_count).
  * Mark every row is_synthetic=True so live and backfill stay separable
    in calibration analysis.
  * model_version stamped `backfill_<year>_bayes_shrink` so it never gets
    bucketed with live rh3/rp3 predictions.
"""
from __future__ import annotations
import argparse
import math
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ROOT / 'data' / 'outputs' / 'predictions_history.csv'
load_dotenv(ROOT / '.env')


def _win_probability(my_proj, opp_proj, sigma_total):
    if sigma_total <= 0:
        return 1.0 if my_proj > opp_proj else 0.0
    z = (my_proj - opp_proj) / sigma_total
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


# Auth home is plv_clone.espn (single source): get_league(year) carries the
# credential check, retry/backoff, and auth-error fast-fail this bare copy
# lacked, and is year-aware for the historical backfill seasons.
from plv_clone.espn import get_league as _get_league  # noqa: E402


def build_panel(year: int = 2025, prior_k: float = 3.0) -> pd.DataFrame:
    league = _get_league(year)
    reg_weeks = int(getattr(league.settings, 'reg_season_count', 20))

    # Step 1: gather all (period, team_name, score) tuples for regular season
    rows = []
    for period in range(1, reg_weeks + 1):
        try:
            bs_list = league.box_scores(matchup_period=period)
        except Exception as e:
            print(f'  p{period}: fetch failed {e}')
            continue
        for bs in bs_list:
            if not (bs.home_team and bs.away_team):
                continue  # bye/playoff structure
            rows.append({
                'period': period,
                'home_team': bs.home_team.team_name,
                'home_score': float(bs.home_score),
                'away_team': bs.away_team.team_name,
                'away_score': float(bs.away_score),
            })
    if not rows:
        return pd.DataFrame()
    matchups = pd.DataFrame(rows)
    print(f'[{year}] regular-season matchups gathered: {len(matchups)} across {matchups["period"].nunique()} periods')

    # Step 2: long-form per-team-per-week scores for rolling avg computation
    long = pd.concat([
        matchups[['period', 'home_team', 'home_score']].rename(columns={'home_team': 'team', 'home_score': 'score'}),
        matchups[['period', 'away_team', 'away_score']].rename(columns={'away_team': 'team', 'away_score': 'score'}),
    ], ignore_index=True).sort_values(['team', 'period']).reset_index(drop=True)

    # Step 3: for each matchup p, project home/away using ONLY data through p-1
    out = []
    for _, m in matchups.iterrows():
        p = m['period']
        prior = long[long['period'] < p]
        if prior.empty:
            continue  # need at least 1 prior week
        league_mu = prior['score'].mean()
        league_sd = prior.groupby('period')['score'].mean().std(ddof=1)
        # Per-team weekly sigma (variation in a team's weekly score) — use league pooled
        team_weekly_sd = prior['score'].std(ddof=1)
        if pd.isna(team_weekly_sd) or team_weekly_sd <= 0:
            team_weekly_sd = 80.0  # fallback

        def project(team):
            prior_team = prior[prior['team'] == team]['score']
            n = len(prior_team)
            team_mu = prior_team.mean() if n > 0 else league_mu
            # Bayesian shrink toward league mean with weight prior_k
            shrunk = (n * team_mu + prior_k * league_mu) / (n + prior_k)
            return shrunk

        my_proj = project(m['home_team'])
        opp_proj = project(m['away_team'])
        sigma_each2 = team_weekly_sd ** 2
        sigma_total = math.sqrt(2 * sigma_each2)
        wp = _win_probability(my_proj, opp_proj, sigma_total)

        out.append({
            'timestamp': datetime.now().isoformat(),
            'date': f'{year}-W{int(p):02d}',
            'period': int(p),
            'my_team': m['home_team'],
            'opp_team': m['away_team'],
            'my_wtd': 0.0,
            'my_projected_total': round(my_proj, 2),
            'opp_wtd': 0.0,
            'opp_projected_total': round(opp_proj, 2),
            'win_probability': round(wp, 4),
            'actual_my_final': round(m['home_score'], 2),
            'actual_opp_final': round(m['away_score'], 2),
            'model_version': f'backfill_{year}_bayes_shrink',
            'is_synthetic': True,
            'backfill_year': year,
        })
    return pd.DataFrame(out)


def append_to_history(panel: pd.DataFrame) -> int:
    if panel.empty:
        print('No rows to append.')
        return 0
    if HISTORY.exists():
        existing = pd.read_csv(HISTORY)
    else:
        existing = pd.DataFrame()

    # Ensure new columns exist on existing rows
    for c in ('is_synthetic', 'backfill_year'):
        if c not in existing.columns:
            existing[c] = pd.NA
    # Default existing live rows to is_synthetic=False
    if 'is_synthetic' in existing.columns:
        mask = existing['is_synthetic'].isna()
        existing.loc[mask, 'is_synthetic'] = False

    # Dedupe: don't append a (model_version, period, my_team, opp_team) already present
    if not existing.empty and 'model_version' in existing.columns:
        key_cols = ['model_version', 'period', 'my_team', 'opp_team']
        existing_keys = set(map(tuple, existing[key_cols].fillna('').astype(str).values.tolist()))
        panel_keys = panel[key_cols].fillna('').astype(str)
        keep_mask = [tuple(r) not in existing_keys for r in panel_keys.values.tolist()]
        panel = panel.loc[keep_mask].reset_index(drop=True)
        print(f'After dedupe: {len(panel)} new rows to append.')

    combined = pd.concat([existing, panel], ignore_index=True)
    combined.to_csv(HISTORY, index=False)
    print(f'Wrote {HISTORY} ({len(combined)} total rows; +{len(panel)} synthetic).')
    return len(panel)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int, default=2025)
    ap.add_argument('--prior-k', type=float, default=3.0,
                    help='Bayesian shrinkage weight toward league mean.')
    args = ap.parse_args()

    panel = build_panel(year=args.year, prior_k=args.prior_k)
    print(f'Built panel: {len(panel)} synthetic rows.')
    if not panel.empty:
        wp = panel['win_probability']
        print(f'  win_prob distribution: min={wp.min():.3f} med={wp.median():.3f} max={wp.max():.3f}')
        print(f'  buckets: 0-25:{((wp>=0)&(wp<.25)).sum()}  25-50:{((wp>=.25)&(wp<.5)).sum()}  50-75:{((wp>=.5)&(wp<.75)).sum()}  75-100:{((wp>=.75)&(wp<=1)).sum()}')
    append_to_history(panel)


if __name__ == '__main__':
    main()

"""opponent_action_predictor.py — predict opponent next-move from transaction patterns.

Two-stage:
  1. TRIGGER — P(team T transacts in next 24-48h), using day-of-week + time-since-last-tx.
  2. TARGET — given trigger, score rostered players for DROP and FAs for ADD.

v1 LIMITATION (2026-06-04): the projection-history + PL-history panels just
started accumulating today. Δ-rank features require ≥2 dated snapshots and
will come online ~2026-06-11. Until then we use **per-opponent behavioral
profiles** — hardcoded feature weights derived from the manager-rating
audit (see plan: hidden-percolating-harp.md). Each profile reflects what
that manager appears to value (PL rank vs raw outcomes vs trajectory).

Once the panels have 2+ weeks of data, swap _hardcoded_profile() for a
logistic / ranker fit from the panel. The CLI surface stays the same.

Usage:
  python scripts/xfp/opponent_action_predictor.py --team "Late Night Bettsing"
  python scripts/xfp/opponent_action_predictor.py --all-teams
  python scripts/xfp/opponent_action_predictor.py --team "Frendy's Fantastic Team" --top 10
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from plv_clone.paths import ROOT
TRI = ROOT / 'data' / 'research' / 'triangulate_universe'
TX_PARQ = ROOT / 'data' / 'research' / 'transactions_history.parquet'
PANEL = ROOT / 'data' / 'research' / 'player_projection_history.parquet'


def _norm(s: str) -> str:
    return unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().lower().strip()


# Per-opponent behavioral profiles (v1: hardcoded from manager-rating audit).
# Higher weight = manager pays more attention to that signal.
#   pl_rank_weight    : how much they follow Pitcher List ranking
#   archetype_traj    : how much they buy TRENDING_UP archetypes
#   model_rank_weight : how much they align with our rh3/rp3
#   outcome_heat      : how much they chase raw recent-form / box-score
#   role_change       : how aggressively they re-shuffle RPs on role moves
#   draft_capital     : how protective of late-round picks they are (lower = more willing to drop)
PROFILES = {
    'Late Night Bettsing':       dict(pl=0.40, traj=0.30, model=0.10, outcome=0.05, role=0.10, draft=0.05),
    'New York Ligers':           dict(pl=0.15, traj=0.25, model=0.40, outcome=0.05, role=0.10, draft=0.05),  # Josh's own model + process
    "Frendy's Fantastic Team":   dict(pl=0.30, traj=0.05, model=0.05, outcome=0.50, role=0.05, draft=0.05),  # outcome chaser
    'Team Solomon':              dict(pl=0.30, traj=0.10, model=0.10, outcome=0.30, role=0.15, draft=0.05),  # save chaser
    "Boone's Bad Bullpen":       dict(pl=0.20, traj=0.15, model=0.15, outcome=0.25, role=0.20, draft=0.05),  # coin flip
    'U Just Lost To Edwin Diaz': dict(pl=0.25, traj=0.20, model=0.20, outcome=0.20, role=0.10, draft=0.05),  # balanced sharpshooter
    '2015 Draft First Round':    dict(pl=0.15, traj=0.10, model=0.20, outcome=0.10, role=0.05, draft=0.40),  # set-and-forget
    'Treasure Island Mashers':   dict(pl=0.20, traj=0.10, model=0.20, outcome=0.20, role=0.10, draft=0.20),  # asleep — uniform priors
}

DEFAULT_PROFILE = dict(pl=0.20, traj=0.20, model=0.20, outcome=0.20, role=0.10, draft=0.10)


def load_data():
    tri_res = pd.read_csv(TRI / 'triangulate_results.csv')
    tri_res['k'] = tri_res['player_name'].apply(_norm)
    rosters = json.load(open(TRI / 'all_team_rosters.json'))
    tx = pd.read_csv(TRI / 'all_transactions.csv')
    tx['dt'] = pd.to_datetime(tx['date'], unit='ms')
    fa = pd.read_csv(TRI / 'fa_above_50fp.csv')
    fa['k'] = fa['player_name'].apply(_norm)
    return tri_res, rosters, tx, fa


def trigger_score(team_name: str, tx: pd.DataFrame, today: date) -> dict:
    """Return P(transact in next 24-48h) + the components driving it."""
    team_tx = tx[tx['team'] == team_name].sort_values('dt')
    if team_tx.empty:
        return {'p_transact_24h': 0.0, 'reason': 'no_tx_history'}
    last_dt = team_tx['dt'].max().date()
    days_since = (today - last_dt).days
    weekday = today.weekday()  # 0=Mon ... 6=Sun

    # Empirical day-of-week rate per team
    dow_rate = team_tx['dt'].dt.weekday.value_counts(normalize=True).reindex(range(7), fill_value=0).to_dict()
    # Recency-weighted base rate: last 21 days carries more signal than season avg.
    cutoff_21 = pd.Timestamp(today) - pd.Timedelta(days=21)
    recent = team_tx[team_tx['dt'] >= cutoff_21]
    recent_rate = len(recent) / 21.0
    span_days = max(1, (team_tx['dt'].max() - team_tx['dt'].min()).days)
    season_rate = len(team_tx) / span_days
    # Blend: 70% recent, 30% season — shrinks rookie sparse teams toward season avg.
    base_rate = 0.7 * recent_rate + 0.3 * season_rate

    # Calibrated v1: P(transact today) ≈ base_rate × dow_mult.
    # base_rate is per-team avg transactions/day (a binary day-rate proxy).
    # dow_mult clamped to [0.5, 1.8]. No pressure term in v1 — backtest showed
    # it over-corrects with 71 days of data. Re-enable once panel has 6+ months.
    # Backtest 2026-05-20→06-02 (14-day holdout): Brier 0.08-0.18 across teams.
    dow_mult = max(0.5, min(1.8, 7 * dow_rate.get(weekday, 0)))
    p_24h = min(0.85, base_rate * dow_mult)

    return {
        'p_transact_24h': round(p_24h, 3),
        'base_rate_per_day': round(base_rate, 3),
        'days_since_last_tx': days_since,
        'weekday': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][weekday],
        'dow_multiplier': round(dow_mult, 2),
        'last_tx_date': str(last_dt),
    }


def _score_player_for_add(row: pd.Series, w: dict) -> tuple[float, dict]:
    """Score a verified FA for 'this opponent likely adds them'."""
    # Normalize component scores to roughly [0, 1].
    pl_rank = row.get('pl_rank') if pd.notna(row.get('pl_rank')) else None
    try:
        pl_rank = int(pl_rank) if pl_rank is not None else None
    except Exception:
        pl_rank = None
    pl_score = max(0.0, 1.0 - (pl_rank / 150.0)) if pl_rank else 0.0

    traj = str(row.get('arche_traj') or '')
    traj_score = 1.0 if 'TRENDING_UP' in traj else (0.5 if 'STABLE' in traj else 0.0)

    mdl = row.get('model_rank')
    try:
        mdl = int(mdl) if pd.notna(mdl) else None
    except Exception:
        mdl = None
    model_score = max(0.0, 1.0 - (mdl / 100.0)) if mdl else 0.0

    # Outcome heat ≈ replacement_delta + recency_form_gap (clipped)
    rd = row.get('model_rep_delta')
    rd = float(rd) if pd.notna(rd) else 0.0
    rf = row.get('model_recform')
    rf = float(rf) if pd.notna(rf) else 0.0
    outcome_score = max(0.0, min(1.0, (rd + 0.5 * rf) / 1.5))

    # Role-change RP heuristic: RP with rprs2 signal "add" and OVERALL >= 55
    role_score = 0.0
    if row.get('bucket') == 'RP' and str(row.get('model_signal')) == 'add':
        role_score = 1.0
    elif row.get('bucket') == 'RP':
        role_score = 0.4

    components = {
        'pl': round(pl_score, 3),
        'traj': round(traj_score, 3),
        'model': round(model_score, 3),
        'outcome': round(outcome_score, 3),
        'role': round(role_score, 3),
    }
    score = (
        w['pl']      * pl_score      +
        w['traj']    * traj_score    +
        w['model']   * model_score   +
        w['outcome'] * outcome_score +
        w['role']    * role_score
    )
    return score, components


def _score_player_for_drop(row: pd.Series, w: dict, draft_round: int | None,
                           injured: bool, lineup_slot: str) -> tuple[float, dict]:
    """Score a rostered player for 'this opponent likely drops them'."""
    mdl = row.get('model_rank')
    try:
        mdl = int(mdl) if pd.notna(mdl) else None
    except Exception:
        mdl = None
    bad_mdl_score = min(1.0, mdl / 200.0) if mdl else 0.5

    traj = str(row.get('arche_traj') or '')
    bad_traj_score = 1.0 if 'TRENDING_DOWN' in traj or 'CAREER_LOW' in traj else 0.0

    rf = row.get('model_recform')
    rf = float(rf) if pd.notna(rf) else 0.0
    cold_recform = max(0.0, min(1.0, -rf / 1.5))

    # FADE/CAUTION verdict bumps drop score regardless of profile
    v = str(row.get('verdict_top') or '')
    verdict_bump = 0.5 if v in ('FADE', 'CAUTION') else (0.2 if v == 'MIXED' else 0.0)

    # Draft capital — late picks (R20+) are easier to drop
    late_pick = 1.0 if (draft_round and draft_round >= 20) else (0.3 if draft_round and draft_round >= 12 else 0.0)

    # BE-injured (not IL) is a drag — likely drop candidate
    be_injured = 1.0 if (injured and lineup_slot == 'BE') else 0.0

    # Weighted: bad model + bad traj + cold form + verdict + late-pick (inverted from add weights)
    score = (
        0.30 * bad_mdl_score +
        0.25 * bad_traj_score +
        0.15 * cold_recform +
        0.15 * verdict_bump +
        (1 - w.get('draft', 0.1)) * 0.10 * late_pick +
        0.10 * be_injured
    )
    components = {
        'bad_mdl': round(bad_mdl_score, 3),
        'bad_traj': round(bad_traj_score, 3),
        'cold_recform': round(cold_recform, 3),
        'verdict_bump': round(verdict_bump, 3),
        'late_pick': round(late_pick, 3),
        'be_injured': round(be_injured, 3),
    }
    return score, components


def predict_team(team_name: str, top: int = 5) -> dict:
    tri_res, rosters, tx, fa = load_data()
    today = date.today()
    profile = PROFILES.get(team_name, DEFAULT_PROFILE)

    # TRIGGER
    trig = trigger_score(team_name, tx, today)

    # ADD candidates — score every verified FA
    fa_with_tri = fa.merge(tri_res, left_on='k', right_on='k', how='left', suffixes=('', '_tri'))
    add_scores = []
    for _, r in fa_with_tri.iterrows():
        s, comps = _score_player_for_add(r, profile)
        add_scores.append({'player': r['player_name'], 'bucket': r['bucket'],
                           'pl_rank': r.get('pl_rank'), 'mdl_rank': r.get('model_rank'),
                           'arche_traj': r.get('arche_traj'), 'verdict': r.get('verdict_top'),
                           'score': round(s, 4), 'components': comps})
    add_scores.sort(key=lambda x: -x['score'])

    # DROP candidates — score every rostered player
    if team_name not in rosters:
        return {'team': team_name, 'error': f'team not found in rosters: {list(rosters.keys())}'}

    # Build draft lookup for this team
    draft = pd.read_csv(TRI / 'draft.csv')
    team_draft = draft[draft['team'] == team_name]
    draft_map = {_norm(r['player']): int(r['round']) for _, r in team_draft.iterrows()}

    # Marginal-upgrade drop model: drop_score = (best available FA add-score) -
    # (own player's add-score) + a smaller "drop pressure" term from
    # bad_mdl/bad_traj. A player is droppable when an FA the manager would
    # value more is available AND the roster player has weak intrinsic value.
    # Per-bucket: SPs are drop candidates only if FA SPs are better; same H/RP.
    top_fa_by_bucket = {}
    for bucket in ('H', 'SP', 'RP'):
        fa_b = [a for a in add_scores if a['bucket'] == bucket]
        if fa_b:
            top_fa_by_bucket[bucket] = fa_b[0]['score']  # best available

    drop_scores = []
    for p in rosters[team_name]:
        k = _norm(p['name'])
        tri_row = tri_res[tri_res['k'] == k]
        if tri_row.empty:
            continue
        r = tri_row.iloc[0]
        d_round = draft_map.get(k)
        bucket = r.get('bucket')
        own_add_score, _ = _score_player_for_add(r, profile)
        best_fa = top_fa_by_bucket.get(bucket, 0.0)
        marginal_upgrade = max(0.0, best_fa - own_add_score)
        # Drop pressure: intrinsic signals the player is bad regardless of alternatives
        intrinsic, comps = _score_player_for_drop(r, profile, d_round, p.get('injured'), p.get('lineup_slot'))
        # Late-round draft pick + IL slot = held cheaply, less likely to be dropped
        held_cheap = 1.0 if p.get('lineup_slot') == 'IL' else 0.0
        s_final = 0.6 * marginal_upgrade + 0.4 * intrinsic - 0.3 * held_cheap
        comps['marginal_upgrade'] = round(marginal_upgrade, 3)
        comps['own_add_score'] = round(own_add_score, 3)
        comps['best_fa_in_bucket'] = round(best_fa, 3)
        comps['held_cheap_IL'] = held_cheap
        drop_scores.append({'player': p['name'], 'bucket': bucket,
                            'mdl_rank': r.get('model_rank'), 'arche_traj': r.get('arche_traj'),
                            'verdict': r.get('verdict_top'), 'draft_round': d_round,
                            'lineup_slot': p.get('lineup_slot'),
                            'score': round(s_final, 4), 'components': comps})
    drop_scores.sort(key=lambda x: -x['score'])

    return {
        'team': team_name,
        'profile_name': team_name if team_name in PROFILES else 'DEFAULT',
        'profile_weights': profile,
        'trigger': trig,
        'top_adds': add_scores[:top],
        'top_drops': drop_scores[:top],
    }


def format_report(pred: dict) -> str:
    if 'error' in pred:
        return f"ERROR: {pred['error']}\n"
    t = pred['trigger']
    lines = [
        f"\n=== Opponent action prediction — {pred['team']} ===",
        f"Profile: {pred['profile_name']}  (pl={pred['profile_weights']['pl']:.2f}  traj={pred['profile_weights']['traj']:.2f}  model={pred['profile_weights']['model']:.2f}  outcome={pred['profile_weights']['outcome']:.2f}  role={pred['profile_weights']['role']:.2f})",
        f"",
        f"TRIGGER  P(transact in 24h) = {t['p_transact_24h']:.3f}",
        f"  base rate {t['base_rate_per_day']}/day · days since last tx: {t['days_since_last_tx']} ({t['last_tx_date']}) · today is {t['weekday']} (dow_mult={t['dow_multiplier']})",
        f"",
        f"TOP ADD CANDIDATES (verified FAs):",
    ]
    for i, a in enumerate(pred['top_adds'], 1):
        lines.append(f"  {i}. {a['player']:25s} [{a['bucket']}]  score={a['score']:.3f}  PL={a['pl_rank']}  mdl={a['mdl_rank']}  traj={a['arche_traj']}  verdict={a['verdict']}")
    lines.append("")
    lines.append("TOP DROP CANDIDATES (their current roster):")
    for i, d in enumerate(pred['top_drops'], 1):
        lines.append(f"  {i}. {d['player']:25s} [{d['bucket']}]  score={d['score']:.3f}  mdl={d['mdl_rank']}  R{d['draft_round']}  slot={d['lineup_slot']}  verdict={d['verdict']}  traj={d['arche_traj']}")
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--team', type=str)
    ap.add_argument('--all-teams', action='store_true')
    ap.add_argument('--top', type=int, default=5)
    args = ap.parse_args()

    if not args.team and not args.all_teams:
        ap.error('pass --team "Team Name" or --all-teams')

    teams = list(PROFILES.keys()) if args.all_teams else [args.team]
    for t in teams:
        pred = predict_team(t, top=args.top)
        print(format_report(pred))


if __name__ == '__main__':
    main()

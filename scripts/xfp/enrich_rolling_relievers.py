"""enrich_rolling_relievers.py — add team-context features to rolling RP substrate.

Adds two new feature blocks targeting the role-context gap surfaced by the user:

1. team_abbr (resolved from MLB API team_id)
2. prior_closer_on_il : 1 if pitcher's TEAM had a top-SV pitcher in year T-1
   (>= 15 SV) AND that pitcher is currently on IL at the cutoff date AND that
   prior closer is NOT this pitcher. Captures "temp closer covering for IL"
   pattern (Suarez covering for Iglesias).
3. is_team_prior_closer : 1 if THIS pitcher was the team's top SV pitcher last
   year (the "incumbent" returns from IL signal — same-year role retention).

Output: data/research/xfp_cache/rolling_relievers_2018_2026.csv (overwrites)
        with new columns appended.
"""
from __future__ import annotations
import json
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = CACHE / 'rolling_relievers_2018_2026.csv'

TEAM_ID_TO_ABBR = json.loads((CACHE / 'mlb_teams.json').read_text())


def load_pitcher_team_map(year: int) -> dict[int, str]:
    """Map pitcher_id -> team_abbr for a given year, from counting stats."""
    cnt = json.loads((CACHE / f'pitcher_counting_stats_{year}.json').read_text())
    out = {}
    for r in cnt:
        pid = r.get('pitcher')
        tid = r.get('team_id')
        if pid and tid:
            out[int(pid)] = TEAM_ID_TO_ABBR.get(str(tid))
    return out


def identify_team_prior_closer(multiyr: pd.DataFrame, year: int,
                                pitcher_team: dict[int, str]) -> dict[str, dict]:
    """For each team, find the prior-year top-SV pitcher (>= 15 SV).
    Returns {team_abbr: {pitcher_id, sv}}."""
    py = multiyr[multiyr['year'] == year - 1].copy()
    if py.empty:
        return {}
    # Attach team from same-year counting stats
    pt_prev = load_pitcher_team_map(year - 1)
    py['team'] = py['pitcher'].map(pt_prev)
    py = py[py['team'].notna() & (py['sv'] >= 15)]
    if py.empty:
        return {}
    py = py.sort_values('sv', ascending=False)
    out = {}
    for _, row in py.iterrows():
        team = row['team']
        if team not in out:
            out[team] = {'pitcher': int(row['pitcher']), 'sv': int(row['sv']),
                         'name': row.get('name')}
    return out


def main():
    print('=== enrich_rolling_relievers ===')
    rolling = pd.read_csv(OUT)
    print(f'rolling rows: {len(rolling)}')
    multiyr = pd.read_csv(CACHE / 'relievers_multiyr_2018_2026.csv')

    # IL features (per pitcher, year, split_day)
    il = pd.read_csv(CACHE / 'il_split_features_2018_2026.csv')
    # Group by (pid, yr) -> sorted list of (split_day, is_on_il, days_since_return)
    il_by_pid_yr: dict[tuple[int, int], list[tuple[int, bool, float]]] = {}
    for _, r in il.iterrows():
        key = (int(r['pitcher']), int(r['year']))
        il_by_pid_yr.setdefault(key, []).append(
            (int(r['split_day']), bool(r['is_on_il_at_split']),
             float(r['days_since_il_return']) if pd.notna(r['days_since_il_return']) else np.nan)
        )
    for k in il_by_pid_yr:
        il_by_pid_yr[k].sort()  # by split_day asc

    def il_state_at(pid: int, yr: int, sd: int) -> tuple[bool, float]:
        """Return (on_il, days_since_return) using closest available IL split_day
        whose value is <= sd (so we don't peek into the future)."""
        rows = il_by_pid_yr.get((pid, yr))
        if not rows:
            return (False, np.nan)
        last = None
        for s, on_il, dsr in rows:
            if s <= sd:
                last = (s, on_il, dsr)
            else:
                break
        if last is None:
            # No prior split_day available — use the earliest (defensive default)
            return (False, np.nan)
        return (last[1], last[2])

    # For each row, attach team and team-context features
    new_team = []
    new_prior_closer_on_il = []
    new_is_team_prior_closer = []
    new_prior_closer_returned_recently = []  # 1 if PC returned from IL within last 14 days
    new_prior_closer_days_since_return = []  # raw days; large = healthy/never-IL

    # Per-year prior-closer lookup
    prior_closer_by_year = {}
    pitcher_team_by_year = {}
    for yr in sorted(rolling['year'].unique()):
        pitcher_team_by_year[yr] = load_pitcher_team_map(yr) if (CACHE / f'pitcher_counting_stats_{yr}.json').exists() else {}
        prior_closer_by_year[yr] = identify_team_prior_closer(multiyr, yr, pitcher_team_by_year[yr])
        n_with_closer = sum(1 for v in prior_closer_by_year[yr].values() if v)
        print(f'  [{yr}] teams with prior-yr top closer (>=15 SV): {n_with_closer}')

    for _, row in rolling.iterrows():
        pid = int(row['pitcher'])
        yr = int(row['year'])
        sd = int(row['split_day'])
        pt = pitcher_team_by_year.get(yr, {})
        team = pt.get(pid)
        new_team.append(team)

        prior_closers = prior_closer_by_year.get(yr, {})
        if team and team in prior_closers:
            pc = prior_closers[team]
            is_self = (pc['pitcher'] == pid)
            if is_self:
                new_is_team_prior_closer.append(1)
                new_prior_closer_on_il.append(0)
                new_prior_closer_returned_recently.append(0)
                new_prior_closer_days_since_return.append(999)  # self => "always healthy as far as PC is concerned"
            else:
                new_is_team_prior_closer.append(0)
                pc_on_il, pc_dsr = il_state_at(pc['pitcher'], yr, sd)
                new_prior_closer_on_il.append(int(pc_on_il))
                returned_recently = (not pc_on_il) and pd.notna(pc_dsr) and (0 <= pc_dsr <= 14)
                new_prior_closer_returned_recently.append(int(returned_recently))
                new_prior_closer_days_since_return.append(float(pc_dsr) if pd.notna(pc_dsr) else 999.0)
        else:
            new_is_team_prior_closer.append(0)
            new_prior_closer_on_il.append(0)
            new_prior_closer_returned_recently.append(0)
            new_prior_closer_days_since_return.append(999.0)

    rolling['team_abbr'] = new_team
    rolling['prior_closer_on_il'] = new_prior_closer_on_il
    rolling['is_team_prior_closer'] = new_is_team_prior_closer
    rolling['prior_closer_returned_recently'] = new_prior_closer_returned_recently
    rolling['prior_closer_days_since_return'] = new_prior_closer_days_since_return

    # Backfill missing lag features for rookies / returnees:
    # use long_low role default + population-mean values.
    pop_means = {
        'sv_lag1': float(multiyr['sv'].mean()),
        'hld_lag1': float(multiyr['hld'].mean()),
        'g_lag1': float(multiyr['g'].mean()),
        'ip_lag1': float(multiyr['ip'].mean()),
        'fp_per_g_lag1': float(multiyr['fp_per_g'].mean()),
        'fp_lag1': float(multiyr['fp'].mean()),
    }
    for col, mu in pop_means.items():
        rolling[col] = rolling[col].fillna(mu)
    # role one-hot defaults: long_low (all role flags = 0)
    for col in ['role_closer_lag1', 'role_setup_lag1', 'role_middle_lag1']:
        rolling[col] = rolling[col].fillna(0)

    # Add lag-1 rate variants of role-usage (sv_per_g_lag1, gf_pct_lag1)
    # — derived from the prior-year multiyr aggregate, not from rolling.
    multiyr_rates = multiyr[['pitcher','year','g','sv','hld']].copy()
    multiyr_rates['sv_per_g'] = multiyr_rates['sv'] / multiyr_rates['g'].replace(0, np.nan)
    multiyr_rates['hld_per_g'] = multiyr_rates['hld'] / multiyr_rates['g'].replace(0, np.nan)
    # Approximate gf_per_g for prior year: closers GF most appearances; use SV+HLD as proxy
    # (we don't have historical GF in multiyr). For lag, sv_per_g is the primary signal.
    multiyr_rates['year_target'] = multiyr_rates['year'] + 1
    rate_lag = multiyr_rates[['pitcher','year_target','sv_per_g','hld_per_g']].rename(
        columns={'sv_per_g':'sv_per_g_lag1', 'hld_per_g':'hld_per_g_lag1'})
    rolling = rolling.merge(rate_lag, left_on=['pitcher','year'],
                             right_on=['pitcher','year_target'], how='left')
    rolling = rolling.drop(columns=['year_target'], errors='ignore')
    rolling['sv_per_g_lag1']  = rolling['sv_per_g_lag1'].fillna(0.0)
    rolling['hld_per_g_lag1'] = rolling['hld_per_g_lag1'].fillna(0.0)

    rolling.to_csv(OUT, index=False)
    print(f'\nWrote {OUT}: {len(rolling)} rows')
    print(f'  team_abbr coverage: {rolling["team_abbr"].notna().sum()} / {len(rolling)}')
    print(f'  prior_closer_on_il=1: {(rolling["prior_closer_on_il"]==1).sum()}')
    print(f'  is_team_prior_closer=1: {(rolling["is_team_prior_closer"]==1).sum()}')

    # Spot-check 2026 ATL: who's flagged as temp_closer (prior_closer_on_il=1)?
    print('\n--- 2026 ATL relievers (Suarez/Iglesias case) ---')
    atl = rolling[(rolling['year']==2026) & (rolling['team_abbr']=='ATL')
                  & (rolling['split_day']==rolling[rolling['year']==2026]['split_day'].max())]
    cols = ['pitcher','team_abbr','split_day','g_to','prior_closer_on_il','is_team_prior_closer','sv_lag1','hld_lag1']
    print(atl[cols].to_string(index=False))


if __name__ == '__main__':
    main()

"""validate_bust_stack_v2_context.py — test bust_stack v2 (game-context).

Pre-registered: data/research/validation_runs/bust_stack_v2_context_2026-06-03.md

Components (all using only pre-start data):
  (1) flag_first_back_long_IL : days since pitcher's prior start in same year >= 30
  (2) flag_short_rest         : statcast pitcher_days_since_prev_game <= 4 (and > 0)
  (3) flag_taxed_bullpen      : SP team's bullpen IP in prior 3 calendar days >= 8.0
  (4) flag_extreme_prior      : pitcher's prior start had pitches >= 110 OR ip < 3.0
  (5) flag_day_after_night    : SP's team had a game the prior calendar day

Outputs:
  - bust_stack_v2_context_results.json
"""
from __future__ import annotations
import json
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
RESEARCH = ROOT / 'data' / 'research'
OUT_DIR = RESEARCH / 'validation_runs'

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]


def load_panel_and_context():
    """Load per-start panel + attach team, rest days, pitches, prior-start gaps,
    bullpen usage, and prior-day team game indicator."""
    # Step 1: base per-start
    p = pd.read_csv(RESEARCH / 'per_start_predictor_battle.csv')
    p = p[p['year'].isin(YEARS)].copy()
    p = p[p['actual_PA'] >= 5].copy()
    print(f'  base per-start rows: {len(p)}')

    all_meta = []
    all_pitches_per_start = []
    all_team_games = []  # (team, game_date, game_pk)
    all_pitcher_starts_team = []  # (pitcher, game_pk, team, game_date)
    all_all_pitcher_outings = []  # (pitcher, game_pk, team, game_date, outs)

    for y in YEARS:
        sc = pd.read_parquet(
            CACHE / f'statcast_{y}.parquet',
            columns=['game_pk', 'game_date', 'pitcher',
                     'home_team', 'away_team', 'inning', 'inning_topbot',
                     'pitcher_days_since_prev_game', 'events']
        )
        sc['game_date'] = pd.to_datetime(sc['game_date'])

        # game-level meta
        meta = sc[['game_pk', 'game_date', 'home_team', 'away_team']].drop_duplicates('game_pk')
        all_meta.append(meta)

        # Identify SP of each (game_pk, side):
        # Inning 1 Top  -> home pitches -> SP team = home
        # Inning 1 Bot  -> away pitches -> SP team = away
        i1 = sc[sc['inning'] == 1].copy()
        i1_top = i1[i1['inning_topbot'] == 'Top']
        i1_bot = i1[i1['inning_topbot'] == 'Bot']
        # The SP is the first pitcher who appeared in that half-inning
        sp_top = i1_top.groupby('game_pk').first().reset_index()
        sp_top['sp_team'] = sp_top['home_team']
        sp_top = sp_top[['game_pk', 'pitcher', 'sp_team', 'game_date']].rename(
            columns={'pitcher': 'sp_pitcher'})
        sp_bot = i1_bot.groupby('game_pk').first().reset_index()
        sp_bot['sp_team'] = sp_bot['away_team']
        sp_bot = sp_bot[['game_pk', 'pitcher', 'sp_team', 'game_date']].rename(
            columns={'pitcher': 'sp_pitcher'})
        sp_combo = pd.concat([sp_top, sp_bot], ignore_index=True)
        all_pitcher_starts_team.append(sp_combo)

        # Outs / IP per (pitcher, game_pk) — for prior pitch / extreme + bullpen
        # outs = sum of (events in {strikeout,field_out,force_out,grounded_into_dp,sac_fly,sac_bunt,double_play,triple_play,other_out,fielders_choice_out})
        out_events = {'strikeout', 'field_out', 'force_out', 'grounded_into_double_play',
                       'sac_fly', 'sac_bunt', 'double_play', 'triple_play',
                       'fielders_choice_out', 'caught_stealing_2b', 'caught_stealing_3b',
                       'caught_stealing_home', 'pickoff_caught_stealing_2b',
                       'pickoff_caught_stealing_3b', 'pickoff_caught_stealing_home',
                       'pickoff_1b', 'pickoff_2b', 'pickoff_3b', 'strikeout_double_play',
                       'sac_fly_double_play'}
            # count pitch-level outs by events column
        sc['_is_out'] = sc['events'].isin(out_events).astype(int)
        sc['_is_pitch'] = 1
        per_app = (sc.groupby(['pitcher', 'game_pk', 'game_date'])
                     .agg(outs=('_is_out', 'sum'),
                          pitches=('_is_pitch', 'sum'),
                          home_team=('home_team', 'first'),
                          away_team=('away_team', 'first'))
                     .reset_index())
        per_app['year'] = y
        all_all_pitcher_outings.append(per_app)

    meta_all = pd.concat(all_meta, ignore_index=True).drop_duplicates('game_pk')
    sp_all = pd.concat(all_pitcher_starts_team, ignore_index=True)
    outings_all = pd.concat(all_all_pitcher_outings, ignore_index=True)
    print(f'  meta rows: {len(meta_all)}  sp_team rows: {len(sp_all)}  outings rows: {len(outings_all)}')

    # Merge dates + sp_team into p
    p['pitcher'] = p['pitcher'].astype('int64')
    p = p.merge(meta_all[['game_pk', 'game_date', 'home_team', 'away_team']],
                on='game_pk', how='left')
    p = p.dropna(subset=['game_date'])

    # Attach SP team: for each (game_pk, pitcher) — which side did they pitch?
    sp_lookup = sp_all.rename(columns={'sp_pitcher': 'pitcher'})[['game_pk', 'pitcher', 'sp_team']]
    p = p.merge(sp_lookup, on=['game_pk', 'pitcher'], how='left')

    # Attach pitches + days_since for THIS start
    days_since = []
    pitches_this = []
    for y in YEARS:
        sc = pd.read_parquet(CACHE / f'statcast_{y}.parquet',
                             columns=['game_pk', 'pitcher',
                                      'pitcher_days_since_prev_game'])
        ds = (sc.groupby(['game_pk', 'pitcher'])['pitcher_days_since_prev_game']
                .first().reset_index())
        days_since.append(ds)
    ds_all = pd.concat(days_since, ignore_index=True)
    p = p.merge(ds_all, on=['game_pk', 'pitcher'], how='left')

    # p already has 'pitches' column from per_start_predictor_battle.csv — no merge needed

    p = p.sort_values(['pitcher', 'year', 'game_date']).reset_index(drop=True)
    return p, outings_all, sp_all, meta_all


def build_context_panel(p, outings_all, sp_all, meta_all):
    # ---------- component 1: first back long IL (gap >= 30 days) ----------
    p['prev_start_date'] = p.groupby(['pitcher', 'year'])['game_date'].shift(1)
    p['gap_days'] = (p['game_date'] - p['prev_start_date']).dt.days
    p['flag_first_back_long_IL'] = ((p['gap_days'] >= 30) & p['gap_days'].notna()).astype(int)

    # ---------- component 2: short rest ----------
    dsp = pd.to_numeric(p['pitcher_days_since_prev_game'], errors='coerce')
    p['flag_short_rest'] = ((dsp >= 1) & (dsp <= 4)).fillna(False).astype(int)

    # ---------- component 4: extreme prior start ----------
    p['prev_ip'] = p.groupby(['pitcher', 'year'])['ip'].shift(1)
    p['prev_pitches'] = p.groupby(['pitcher', 'year'])['pitches'].shift(1)
    p['flag_extreme_prior'] = (
        ((p['prev_pitches'] >= 110) | (p['prev_ip'] < 3.0)) & p['prev_ip'].notna()
    ).astype(int)

    # ---------- component 3: taxed bullpen ----------
    # For each game_pk's SP team: sum IP of all OTHER pitchers on that team in prior 3 days.
    # outings_all = all pitcher appearances. To attribute team: each pitcher belongs to
    # home or away team of that game. The SP of the game = sp_all entries; non-SP = bullpen.
    # First annotate outings with team and SP-or-not.
    o = outings_all.copy()
    # Attach SP-of-game from sp_all so we can tell if this outing was the SP
    sp_idx = sp_all.set_index(['game_pk'])[['sp_pitcher', 'sp_team']]
    # For multiple SP entries per game_pk (home + away), need both. Reshape:
    sp_wide = sp_all.pivot_table(index='game_pk', columns='sp_team',
                                  values='sp_pitcher', aggfunc='first')
    # Determine each outing's team: pitcher's team for that game = the team for which
    # they're listed as SP if they're a SP; otherwise determine from inning_topbot...
    # We don't carry inning_topbot here. Use simpler heuristic — for each (pitcher, game_pk)
    # match against sp_all to set team if SP; else mark team unknown.
    o = o.merge(sp_all[['game_pk', 'sp_pitcher', 'sp_team']],
                left_on=['game_pk', 'pitcher'], right_on=['game_pk', 'sp_pitcher'], how='left')
    # For non-SP outings, team is unknown from this merge. We'll re-derive using a second pass
    # — for each non-SP pitcher outing, team = home_team if their inning_topbot first appearance
    # was 'Top' else away_team. We need to re-load that pitcher-level inning_topbot...
    # Simpler: for bullpen usage we'll re-process at scan time with statcast.
    # Mark whether this outing is the SP for the game:
    o['is_sp'] = o['sp_pitcher'].notna().astype(int)

    # Re-derive team for ALL pitcher outings from statcast: pitcher first appearance
    # inning_topbot -> team. We'll do this year by year to avoid blowing memory.
    team_per_outing = []
    for y in YEARS:
        sc = pd.read_parquet(CACHE / f'statcast_{y}.parquet',
                             columns=['game_pk', 'pitcher', 'inning_topbot',
                                      'home_team', 'away_team', 'game_date'])
        sc['game_date'] = pd.to_datetime(sc['game_date'])
        first_app = (sc.groupby(['pitcher', 'game_pk'])
                       .first().reset_index())
        first_app['team'] = np.where(first_app['inning_topbot'] == 'Top',
                                      first_app['home_team'], first_app['away_team'])
        team_per_outing.append(first_app[['pitcher', 'game_pk', 'team', 'game_date']])
    tpo = pd.concat(team_per_outing, ignore_index=True)
    o = o.merge(tpo[['pitcher', 'game_pk', 'team']], on=['pitcher', 'game_pk'], how='left')
    o['ip'] = o['outs'] / 3.0

    # Now: for each (team, game_date) pair, sum bullpen (non-SP) IP. Then for each start,
    # lookup team + game_date and sum across [date-3, date-1].
    bull = o[o['is_sp'] == 0].copy()
    team_date_ip = (bull.groupby(['team', 'game_date'])['ip'].sum().reset_index()
                        .rename(columns={'ip': 'bullpen_ip'}))
    # Build a fast lookup
    team_date_ip = team_date_ip.sort_values(['team', 'game_date'])
    # For each (team, target_date): sum bullpen_ip where game_date in [target-3, target-1]
    # Use a merge_asof-like approach: for each target row, loop teams.
    bp_by_team = {t: g.set_index('game_date')['bullpen_ip']
                  for t, g in team_date_ip.groupby('team')}

    def taxed_bullpen_ip(row):
        t = row['sp_team']
        d = row['game_date']
        if pd.isna(t) or t not in bp_by_team:
            return np.nan
        s = bp_by_team[t]
        # sum of values where index in [d-3, d-1]
        start = d - pd.Timedelta(days=3)
        end = d - pd.Timedelta(days=1)
        return float(s.loc[(s.index >= start) & (s.index <= end)].sum())

    p['bullpen_ip_prior3d'] = p.apply(taxed_bullpen_ip, axis=1)
    p['flag_taxed_bullpen'] = (p['bullpen_ip_prior3d'] >= 8.0).astype(int)

    # ---------- component 5: day after night (proxy: prior-day team game) ----------
    # team_date set = all (team, game_date) the team played
    home_games = meta_all[['home_team', 'game_date']].rename(columns={'home_team': 'team'})
    away_games = meta_all[['away_team', 'game_date']].rename(columns={'away_team': 'team'})
    team_games = pd.concat([home_games, away_games], ignore_index=True).drop_duplicates()
    team_game_set = set(zip(team_games['team'], pd.to_datetime(team_games['game_date'])))

    def prior_day_played(row):
        t = row['sp_team']
        if pd.isna(t):
            return 0
        d = row['game_date'] - pd.Timedelta(days=1)
        return int((t, d) in team_game_set)

    p['flag_day_after_night'] = p.apply(prior_day_played, axis=1)

    # bust outcome
    p['fp'] = p['actual_FP']
    p['bust_outcome'] = (p['fp'] < 0.0).astype(int)
    p['ym'] = p['game_date'].dt.to_period('M').astype(str)

    flags = ['flag_first_back_long_IL', 'flag_short_rest', 'flag_taxed_bullpen',
             'flag_extreme_prior', 'flag_day_after_night']
    p['bust_stack_v2'] = p[flags].sum(axis=1).astype(int)

    return p, flags


def per_component(panel, comps):
    out = {}
    for c in comps:
        m = panel[c] == 1
        n1 = int(m.sum()); n0 = int((~m).sum())
        b1 = panel.loc[m, 'bust_outcome'].mean() if n1 else float('nan')
        b0 = panel.loc[~m, 'bust_outcome'].mean() if n0 else float('nan')
        lift = (b1 - b0) * 100.0
        bk1 = int(panel.loc[m, 'bust_outcome'].sum()); nb1 = n1 - bk1
        bk0 = int(panel.loc[~m, 'bust_outcome'].sum()); nb0 = n0 - bk0
        table = np.array([[bk1, nb1], [bk0, nb0]])
        if min(table.sum(0)) >= 5 and min(table.sum(1)) >= 5:
            chi2, p, _, _ = chi2_contingency(table)
        else:
            chi2, p = float('nan'), float('nan')
        out[c] = dict(n_flag1=n1, n_flag0=n0,
                      bust_rate_flag1=float(b1), bust_rate_flag0=float(b0),
                      lift_pp=float(lift), chi2=float(chi2), p_value=float(p),
                      fire_rate=n1/max(len(panel),1))
    return out


def stack_bust_rate(panel, stack_col, max_n):
    buckets = {}
    for b in range(max_n + 1):
        m = panel[stack_col] == b
        n = int(m.sum())
        busts = int(panel.loc[m, 'bust_outcome'].sum())
        buckets[b] = dict(n=n, busts=busts,
                          bust_rate=busts/n if n else float('nan'),
                          mean_fp=float(panel.loc[m, 'fp'].mean()) if n else float('nan'))
    lo = panel[panel[stack_col] == 0]
    hi = panel[panel[stack_col] >= 3]
    if len(hi) >= 10 and len(lo) >= 10:
        tbl = np.array([
            [int(hi['bust_outcome'].sum()), int((1 - hi['bust_outcome']).sum())],
            [int(lo['bust_outcome'].sum()), int((1 - lo['bust_outcome']).sum())]])
        chi2, p, _, _ = chi2_contingency(tbl)
    else:
        chi2, p = float('nan'), float('nan')
    return dict(buckets=buckets,
                chi2_hi_vs_low=dict(chi2=float(chi2), p_value=float(p),
                                     low_n=len(lo), hi_n=len(hi),
                                     low_bust_rate=float(lo['bust_outcome'].mean()) if len(lo) else None,
                                     hi_bust_rate=float(hi['bust_outcome'].mean()) if len(hi) else None))


def yearly_stability(panel, stack_col):
    out = {}
    for y, grp in panel.groupby('year'):
        lo = grp[grp[stack_col] == 0]; hi = grp[grp[stack_col] >= 3]
        if len(lo) < 50 or len(hi) < 10:
            continue
        out[int(y)] = dict(n=len(grp),
                           bust_rate_stack0=float(lo['bust_outcome'].mean()),
                           bust_rate_stack3plus=float(hi['bust_outcome'].mean()),
                           lift_pp=float((hi['bust_outcome'].mean() - lo['bust_outcome'].mean()) * 100.0),
                           n_stack0=len(lo), n_stack3plus=len(hi))
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print('=== validate_bust_stack_v2_context ===')
    print('Step 1: load + attach context...')
    p, outings, sp_all, meta_all = load_panel_and_context()
    print(f'  attached panel n={len(p)}, sp_team filled={p["sp_team"].notna().sum()}')

    print('Step 2: build context features...')
    panel, flags = build_context_panel(p, outings, sp_all, meta_all)
    print(f'  panel rows: {len(panel)}')
    for c in flags:
        n1 = int(panel[c].sum())
        print(f'    {c}: fire={panel[c].mean():.3%}  n_flag=1={n1}')
    print(f'  bust base rate: {panel["bust_outcome"].mean():.3%}')
    print('  bust_stack_v2 distribution:')
    print(panel['bust_stack_v2'].value_counts().sort_index().to_string())

    print('\nStep 3: per-component edge...')
    comp_results = per_component(panel, flags)
    for c, r in comp_results.items():
        print(f'  {c}: flag1 bust={r["bust_rate_flag1"]:.3%}  flag0={r["bust_rate_flag0"]:.3%}  '
              f'lift={r["lift_pp"]:+.2f}pp  chi2={r["chi2"]:.2f}  p={r["p_value"]:.4g}  '
              f'n1={r["n_flag1"]}')

    print('\nStep 4: stack-sum bust rate...')
    stack_results = stack_bust_rate(panel, 'bust_stack_v2', max_n=5)
    for b, info in stack_results['buckets'].items():
        print(f'  stack={b}: n={info["n"]:>5d}  busts={info["busts"]:>4d}  '
              f'rate={info["bust_rate"]:.3%}  mean_fp={info["mean_fp"]:.2f}')
    cs = stack_results['chi2_hi_vs_low']
    print(f'  Chi² stack>=3 vs ==0: chi2={cs["chi2"]:.3f}  p={cs["p_value"]:.4g}')
    print(f'    lo_n={cs["low_n"]} rate={cs["low_bust_rate"]}  '
          f'hi_n={cs["hi_n"]} rate={cs["hi_bust_rate"]}')

    print('\nStep 5: yearly stability...')
    yearly = yearly_stability(panel, 'bust_stack_v2')
    for y, info in sorted(yearly.items()):
        print(f'  {y}: stack=0={info["bust_rate_stack0"]:.3%}  '
              f'stack>=3={info["bust_rate_stack3plus"]:.3%}  '
              f'lift={info["lift_pp"]:+.2f}pp  (n0={info["n_stack0"]} n3+={info["n_stack3plus"]})')

    # Independence with boom_stack (load cached)
    print('\nStep 6: independence with boom_stack components...')
    boom = pd.read_parquet(RESEARCH / '_boom_stack_per_start_panel_cache.parquet')
    indep = panel.merge(boom[['pitcher', 'game_pk',
                               'flag_skill_spike', 'flag_recform_hot',
                               'flag_opp_soft', 'boom_stack']],
                         on=['pitcher', 'game_pk'], how='inner')
    print(f'  joined rows: {len(indep)}')
    corr_matrix = {}
    boom_cs = ['flag_skill_spike', 'flag_recform_hot', 'flag_opp_soft']
    for bc in flags:
        corr_matrix[bc] = {bo: float(indep[bc].corr(indep[bo])) for bo in boom_cs}
        for bo, v in corr_matrix[bc].items():
            print(f'    corr({bc}, {bo}) = {v:+.3f}')

    # 2D heat n + bust rate
    heat_n, heat_bust = {}, {}
    for bo in [0, 1, 2, 3]:
        heat_n[bo] = {}; heat_bust[bo] = {}
        for bu in [0, 1, 2, 3, 4, 5]:
            m = (indep['boom_stack'] == bo) & (indep['bust_stack_v2'] == bu)
            n = int(m.sum())
            heat_n[bo][bu] = n
            heat_bust[bo][bu] = float(indep.loc[m, 'bust_outcome'].mean()) if n else float('nan')

    output = dict(
        panel_size=len(panel),
        bust_base_rate=float(panel['bust_outcome'].mean()),
        flag_fire_rates={c: float(panel[c].mean()) for c in flags},
        bust_stack_distribution=panel['bust_stack_v2'].value_counts().sort_index().to_dict(),
        per_component=comp_results,
        stack=stack_results,
        yearly_stability=yearly,
        independence={'corr_matrix': corr_matrix,
                      'heatmap_n': heat_n, 'heatmap_bust': heat_bust},
    )
    out_json = OUT_DIR / 'bust_stack_v2_context_results.json'
    with open(out_json, 'w') as fh:
        json.dump(output, fh, indent=2,
                  default=lambda x: None if (isinstance(x, float) and np.isnan(x)) else float(x))
    print(f'\nWrote {out_json}')
    return output


if __name__ == '__main__':
    main()

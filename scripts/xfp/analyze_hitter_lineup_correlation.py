"""analyze_hitter_lineup_correlation.py — does lineup-wide stack predict
team boom days? Does an individual hitter's boom rate AMPLIFY when 3+
of his lineup-mates also have boom_stack >= 2 going in?

Research-only — does NOT modify the engine. Produces a verdict report
at data/research/validation_runs/hitter_lineup_correlation.md.

Pipeline:
  1. Load the hitter panel (245k batter-game rows, 2018-2025).
  2. Join each (batter, game_pk) to that batter's team-for-the-day from
     statcast (home_team / away_team via inning_topbot).
  3. For each (team, game_pk, game_date), build:
       - lineup_stack2_count  = # starters with boom_stack >= 2
       - lineup_stack1_count  = # starters with boom_stack >= 1
       - team_fp_proxy        = sum of fp_proxy across the 9-ish starters
       - opp_starter          = the SP every batter on this team faces
                                 (same for all, by construction)
       - team_opp_soft        = whether opp_starter is in SP top tertile
                                 (soft = high xwoba_to_date)
  4. Define team_boom = team_fp_proxy >= 80th pct empirical threshold.
  5. Quantify:
       (a) individual hitter boom rate by own boom_stack x # teammates_stack2
       (b) team boom rate by lineup_stack2_count
       (c) year-by-year stability
       (d) does lineup_stack_count add lift beyond opp_soft (which is
           already a team-level signal)?
       (e) lineup_stack_amplification flag edge.

Strict framing — every component is leakage-safe because boom_stack
itself was built leakage-safe in analyze_hitter_boom_bust.py.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT_DIR = ROOT / 'data' / 'research' / 'validation_runs'
PANEL_PATH = OUT_DIR / 'hitter_boom_bust_panel.parquet'

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]


def load_panel() -> pd.DataFrame:
    p = pd.read_parquet(PANEL_PATH)
    print(f'  hitter panel loaded: {len(p):,} batter-game rows')
    return p


def attach_batter_team(panel: pd.DataFrame) -> pd.DataFrame:
    """For each (batter, game_pk) in the panel, derive batter_team =
    away_team if their PAs were Top-inning, else home_team. Pulls from
    statcast cache by year."""
    out_chunks = []
    for y in YEARS:
        sub = panel[panel['year'] == y]
        if len(sub) == 0:
            continue
        sc = pd.read_parquet(CACHE / f'statcast_{y}.parquet',
                              columns=['game_pk', 'batter', 'home_team',
                                       'away_team', 'inning_topbot'])
        # one row per (game_pk, batter) — majority half-inning
        half = (sc.groupby(['game_pk', 'batter'])['inning_topbot']
                  .agg(lambda s: s.value_counts().index[0]).reset_index())
        teams = sc[['game_pk', 'home_team', 'away_team']].drop_duplicates(
            subset=['game_pk'])
        half = half.merge(teams, on='game_pk', how='left')
        half['batter_team'] = np.where(half['inning_topbot'] == 'Top',
                                        half['away_team'], half['home_team'])
        half = half[['game_pk', 'batter', 'batter_team']]
        sub_j = sub.merge(half, on=['game_pk', 'batter'], how='left')
        out_chunks.append(sub_j)
        print(f'    year {y}: matched team for '
              f'{sub_j["batter_team"].notna().sum():,} / {len(sub_j):,} rows')
    out = pd.concat(out_chunks, ignore_index=True)
    return out


def build_team_day_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Aggregate to (team, game_pk, game_date) — the team-day level."""
    # drop rows w/o team (shouldn't happen)
    panel = panel.dropna(subset=['batter_team']).copy()
    g = panel.groupby(['batter_team', 'game_pk', 'game_date', 'year']).agg(
        n_starters=('batter', 'size'),
        n_stack1=('boom_stack', lambda s: int((s >= 1).sum())),
        n_stack2=('boom_stack', lambda s: int((s >= 2).sum())),
        n_stack3=('boom_stack', lambda s: int((s >= 3).sum())),
        team_fp_proxy=('fp_proxy', 'sum'),
        team_n_boom=('boom_game', 'sum'),
        team_n_bust=('bust_game', 'sum'),
        opp_starter=('opp_starter', 'first'),  # same SP for every hitter on a team
        team_opp_soft=('flag_opp_soft', 'max'),  # any hitter sees the SP -> all do
        mean_season_fp=('season_fp_per_g', 'mean'),
    ).reset_index()
    return g


def teammate_count_per_hitter(panel: pd.DataFrame) -> pd.DataFrame:
    """For each (batter, game_pk) row, compute # OTHER starters on the
    same team-day with boom_stack >= 2 (excluding self)."""
    grp = panel.groupby(['batter_team', 'game_pk'])
    panel['team_n_stack2'] = grp['boom_stack'].transform(lambda s: (s >= 2).sum())
    panel['own_stack2'] = (panel['boom_stack'] >= 2).astype(int)
    panel['teammates_stack2'] = panel['team_n_stack2'] - panel['own_stack2']
    panel['team_n_stack1'] = grp['boom_stack'].transform(lambda s: (s >= 1).sum())
    panel['own_stack1'] = (panel['boom_stack'] >= 1).astype(int)
    panel['teammates_stack1'] = panel['team_n_stack1'] - panel['own_stack1']
    return panel


def main():
    print('Loading hitter panel...')
    panel = load_panel()
    print('Attaching batter team-for-the-day from statcast...')
    panel = attach_batter_team(panel)
    print(f'After team join: {len(panel):,} rows')

    print('Computing per-hitter teammate counts...')
    panel = teammate_count_per_hitter(panel)

    print('Building team-day panel...')
    td = build_team_day_panel(panel)
    print(f'  team-day rows: {len(td):,}')

    # team_boom = team_fp_proxy >= empirical 80th pct
    team_boom_thr = float(td['team_fp_proxy'].quantile(0.80))
    print(f'  team-day 80th-pct fp_proxy: {team_boom_thr:.2f}')
    td['team_boom'] = (td['team_fp_proxy'] >= team_boom_thr).astype(int)

    # Bucket lineup_stack2_count
    def bucket(n):
        if n == 0: return '0'
        if n == 1: return '1'
        if n == 2: return '2'
        return '3+'
    td['stack2_bucket'] = td['n_stack2'].apply(bucket)

    # ---- Step 3 — Individual hitter boom rate by (own_stack, teammates_stack2) ----
    print('\nStep 3 — building (own_stack x teammates_stack2) heatmap...')
    panel['teammates_stack2_bucket'] = panel['teammates_stack2'].apply(bucket)
    heatmap_n = panel.pivot_table(
        index='boom_stack', columns='teammates_stack2_bucket',
        values='boom_game', aggfunc='count', fill_value=0)
    heatmap_rate = panel.pivot_table(
        index='boom_stack', columns='teammates_stack2_bucket',
        values='boom_game', aggfunc='mean', fill_value=np.nan) * 100

    # ---- Step 4 — Team-level boom rate by lineup_stack_count ----
    print('Step 4 — team boom rate by lineup_stack2_count...')
    team_summary = td.groupby('stack2_bucket').agg(
        n_team_days=('team_boom', 'size'),
        team_boom_rate=('team_boom', 'mean'),
        mean_team_fp=('team_fp_proxy', 'mean'),
        median_team_fp=('team_fp_proxy', 'median'),
    ).reset_index()
    team_summary['team_boom_rate'] = team_summary['team_boom_rate'] * 100

    # Year-by-year stability — team boom rate at stack2_bucket=3+ vs =0
    print('  year-by-year stability...')
    yr_stab = []
    for yr in sorted(td['year'].unique()):
        sub = td[td['year'] == yr]
        low = sub[sub['stack2_bucket'] == '0']
        hi = sub[sub['stack2_bucket'] == '3+']
        if len(low) == 0 or len(hi) == 0:
            continue
        yr_stab.append({
            'year': int(yr),
            'n_low': len(low),
            'n_hi': len(hi),
            'low_boom_rate': low['team_boom'].mean() * 100,
            'hi_boom_rate': hi['team_boom'].mean() * 100,
            'edge_pp': hi['team_boom'].mean() * 100 - low['team_boom'].mean() * 100,
        })

    # ---- Independence vs opp_soft ----
    print('  independence vs opp_soft...')
    indep = []
    for opp_soft in [0, 1]:
        sub = td[td['team_opp_soft'] == opp_soft]
        if len(sub) == 0:
            continue
        for bk in ['0', '1', '2', '3+']:
            s2 = sub[sub['stack2_bucket'] == bk]
            if len(s2) == 0:
                continue
            indep.append({
                'opp_soft': opp_soft,
                'stack2_bucket': bk,
                'n': len(s2),
                'team_boom_rate': s2['team_boom'].mean() * 100,
                'mean_team_fp': s2['team_fp_proxy'].mean(),
            })

    # opp_soft independence — within-stratum stack2_bucket edge.
    # Require min-n=30 on the high cell; if 3+ cell is too thin (mechanical
    # sparsity inside normal_opp because opp_soft contributes to boom_stack),
    # fall back to the 2-bucket.
    indep_edges = []
    indep_used = []
    for opp_soft in [0, 1]:
        rows = [r for r in indep if r['opp_soft'] == opp_soft]
        low = [r for r in rows if r['stack2_bucket'] == '0']
        hi3 = [r for r in rows if r['stack2_bucket'] == '3+']
        hi2 = [r for r in rows if r['stack2_bucket'] == '2']
        if not low:
            continue
        if hi3 and hi3[0]['n'] >= 30:
            edge = hi3[0]['team_boom_rate'] - low[0]['team_boom_rate']
            indep_edges.append(edge)
            indep_used.append((opp_soft, '3+', hi3[0]['n'], edge))
        elif hi2 and hi2[0]['n'] >= 30:
            edge = hi2[0]['team_boom_rate'] - low[0]['team_boom_rate']
            indep_edges.append(edge)
            indep_used.append((opp_soft, '2 (3+ too thin)', hi2[0]['n'], edge))
    avg_indep = float(np.mean(indep_edges)) if indep_edges else 0.0

    # ---- Step 5 — lineup_stack_amplification flag ----
    # Fires when: own boom_stack >= 1 AND >= 2 teammates also have stack >= 1
    print('Step 5 — lineup_stack_amplification flag...')
    panel['lineup_amp'] = ((panel['boom_stack'] >= 1)
                           & (panel['teammates_stack1'] >= 2)).astype(int)
    amp_summary = panel.groupby('lineup_amp').agg(
        n=('boom_game', 'size'),
        boom_rate=('boom_game', 'mean'),
        bust_rate=('bust_game', 'mean'),
        mean_fp=('fp_proxy', 'mean'),
    ).reset_index()
    amp_summary['boom_rate'] *= 100
    amp_summary['bust_rate'] *= 100

    # Year-by-year amp flag
    amp_yr = []
    for yr in sorted(panel['year'].unique()):
        sub = panel[panel['year'] == yr]
        on = sub[sub['lineup_amp'] == 1]
        off = sub[sub['lineup_amp'] == 0]
        if len(on) == 0 or len(off) == 0:
            continue
        amp_yr.append({
            'year': int(yr),
            'n_on': len(on),
            'on_rate': on['boom_game'].mean() * 100,
            'off_rate': off['boom_game'].mean() * 100,
            'edge_pp': on['boom_game'].mean() * 100 - off['boom_game'].mean() * 100,
        })

    # ---- Lineup amp INDEPENDENCE: does it add lift on top of own boom_stack? ----
    # Stratify by own boom_stack and see if the amp flag still adds lift.
    print('  amp independence vs own boom_stack...')
    amp_strat = []
    for own_stack in [0, 1, 2, 3]:
        sub = panel[panel['boom_stack'] == own_stack]
        for amp in [0, 1]:
            s2 = sub[sub['lineup_amp'] == amp]
            if len(s2) == 0:
                continue
            amp_strat.append({
                'own_stack': own_stack,
                'lineup_amp': amp,
                'n': len(s2),
                'boom_rate': s2['boom_game'].mean() * 100,
                'bust_rate': s2['bust_game'].mean() * 100,
            })

    # ---- Build report ----
    R = []
    R.append('# Hitter Lineup Correlation — Do teammates booming predict you booming?')
    R.append('')
    R.append(f'Generated 2026-06-03. Built from hitter_boom_bust_panel.parquet '
             f'({len(panel):,} batter-game rows, {len(td):,} team-day rows, '
             f'years {YEARS}).')
    R.append('')
    R.append('## Framing')
    R.append('')
    R.append('- `boom_stack` is the validated per-hitter pre-game signal (skill_spike + '
             'recform_hot + opp_soft), built leakage-safe in '
             '`analyze_hitter_boom_bust.py`.')
    R.append('- `lineup_stack2_count` = # starters on a team-day with `boom_stack >= 2` '
             'going IN to the game. Computed at PRE-game time (boom_stack uses only '
             'data strictly prior to the game).')
    R.append('- `teammates_stack2` = `lineup_stack2_count` minus self (the right '
             'measure for individual amplification).')
    R.append(f'- `team_boom`: team\'s total fp_proxy across all its starters that day '
             f'>= {team_boom_thr:.1f} (empirical 80th pct of team-days).')
    R.append('- `team_opp_soft`: the team is facing an SP whose prior-only xwoba_to '
             'is in the top tertile within (year, month). Identical for every hitter '
             'on the team by construction.')
    R.append('')

    R.append('## 1. Heatmap — individual hitter boom rate by (own_stack x teammates_stack2)')
    R.append('')
    cols = ['0', '1', '2', '3+']
    R.append('Rate (%) of boom_game by own boom_stack (rows) and # OTHER teammates '
             'with stack >= 2 (cols):')
    R.append('')
    R.append('| own_stack | ' + ' | '.join(cols) + ' |')
    R.append('|---' + '|---' * len(cols) + '|')
    for own in [0, 1, 2, 3]:
        if own not in heatmap_rate.index:
            continue
        row = f'| {own} '
        for c in cols:
            r = heatmap_rate.loc[own, c] if c in heatmap_rate.columns else np.nan
            n = heatmap_n.loc[own, c] if c in heatmap_n.columns else 0
            if pd.isna(r) or n < 50:
                row += f'| - '
            else:
                row += f'| {r:.1f}% (n={int(n):,}) '
        row += '|'
        R.append(row)

    R.append('')
    R.append('**Read:** moving DOWN a column shows the own_stack edge holding teammate-count fixed. '
             'Moving RIGHT across a row shows the teammate amplification holding own_stack fixed.')

    # Compute the headline amp delta from heatmap: own=2, teammates 0 vs 3+
    def cell(o, t):
        if o not in heatmap_rate.index: return None, 0
        if t not in heatmap_rate.columns: return None, 0
        r = heatmap_rate.loc[o, t]
        n = heatmap_n.loc[o, t]
        if pd.isna(r) or n < 50: return None, n
        return r, n

    R.append('')
    R.append('**Headline amplification reads:**')
    for own in [1, 2]:
        r0, n0 = cell(own, '0')
        r3, n3 = cell(own, '3+')
        if r0 is not None and r3 is not None:
            R.append(f'- own_stack={own}: boom rate {r0:.1f}% (n={n0:,}) at 0 teammates_stack2 '
                     f'-> {r3:.1f}% (n={n3:,}) at 3+ teammates. Delta {r3-r0:+.1f} pp.')

    R.append('')
    R.append('## 2. Team-level boom rate by lineup_stack2_count')
    R.append('')
    R.append('| lineup_stack2_count | n_team_days | mean team fp_proxy | team_boom rate |')
    R.append('|---|---|---|---|')
    for bk in cols:
        sub = team_summary[team_summary['stack2_bucket'] == bk]
        if len(sub) == 0:
            continue
        r = sub.iloc[0]
        R.append(f'| {bk} | {int(r["n_team_days"]):,} | {r["mean_team_fp"]:.2f} '
                 f'| {r["team_boom_rate"]:.1f}% |')

    if len(team_summary):
        base = team_summary[team_summary['stack2_bucket'] == '0']['team_boom_rate']
        hi = team_summary[team_summary['stack2_bucket'] == '3+']['team_boom_rate']
        if len(base) and len(hi):
            R.append('')
            R.append(f'**Team boom edge (lineup_stack2 = 3+ vs = 0): '
                     f'{hi.iloc[0]-base.iloc[0]:+.1f} pp**')

    R.append('')
    R.append('## 3. Year-by-year stability — team boom rate edge')
    R.append('')
    R.append('| year | n(=0) | n(=3+) | rate(=0) | rate(=3+) | edge |')
    R.append('|---|---|---|---|---|---|')
    for r in yr_stab:
        R.append(f'| {r["year"]} | {r["n_low"]:,} | {r["n_hi"]:,} | '
                 f'{r["low_boom_rate"]:.1f}% | {r["hi_boom_rate"]:.1f}% | '
                 f'{r["edge_pp"]:+.1f} pp |')

    R.append('')
    R.append('## 4. Independence vs opp_soft — does lineup_stack add lift on top of opp_soft?')
    R.append('')
    R.append('opp_soft is already team-level (every hitter on the team faces the same '
             'SP). If lineup_stack2 is mostly a proxy for opp_soft, stratifying by '
             'opp_soft should flatten the edge.')
    R.append('')
    R.append('| opp_soft | stack2_bucket | n | team_boom rate | mean team fp_proxy |')
    R.append('|---|---|---|---|---|')
    for r in indep:
        R.append(f'| {r["opp_soft"]} | {r["stack2_bucket"]} | {r["n"]:,} | '
                 f'{r["team_boom_rate"]:.1f}% | {r["mean_team_fp"]:.2f} |')

    # Compute edge within each opp_soft stratum
    R.append('')
    R.append('**Within-stratum edge (high vs =0), using min-n=30 on high cell:**')
    for opp_soft, bucket_used, n_hi, edge in indep_used:
        label = 'soft opp' if opp_soft == 1 else 'normal opp'
        R.append(f'- {label}: lineup_stack2 = {bucket_used} (n={n_hi}) vs = 0 '
                 f'= {edge:+.1f} pp')
    R.append('')
    R.append('Note: in the normal-opp stratum the (lineup_stack2=3+) cell is '
             'mechanically sparse because opp_soft is one of the three flags '
             'that drives a hitter\'s individual boom_stack to 2+. We therefore '
             'fall back to the 2-bucket on the normal-opp side, which still has '
             'a reasonable sample.')

    R.append('')
    R.append('## 5. lineup_stack_amplification flag')
    R.append('')
    R.append('Flag fires when: own boom_stack >= 1 AND >= 2 other teammates also have '
             'boom_stack >= 1 going in.')
    R.append('')
    R.append('| lineup_amp | n | boom rate | bust rate | mean fp_proxy |')
    R.append('|---|---|---|---|---|')
    for _, r in amp_summary.iterrows():
        R.append(f'| {int(r["lineup_amp"])} | {int(r["n"]):,} | {r["boom_rate"]:.1f}% | '
                 f'{r["bust_rate"]:.1f}% | {r["mean_fp"]:.2f} |')

    if len(amp_summary) == 2:
        on = amp_summary[amp_summary['lineup_amp'] == 1].iloc[0]
        off = amp_summary[amp_summary['lineup_amp'] == 0].iloc[0]
        amp_edge = on['boom_rate'] - off['boom_rate']
        R.append('')
        R.append(f'**lineup_stack_amplification raw edge: {amp_edge:+.1f} pp boom rate**')

    R.append('')
    R.append('### 5a. Amp flag year-by-year')
    R.append('')
    R.append('| year | n(on) | rate(on) | rate(off) | edge |')
    R.append('|---|---|---|---|---|')
    for r in amp_yr:
        R.append(f'| {r["year"]} | {r["n_on"]:,} | {r["on_rate"]:.1f}% | '
                 f'{r["off_rate"]:.1f}% | {r["edge_pp"]:+.1f} pp |')

    R.append('')
    R.append('### 5b. Amp flag INDEPENDENCE — does it add lift on top of own boom_stack?')
    R.append('')
    R.append('Stratify by own boom_stack. If amp is just a proxy for own stack, the '
             'within-stratum edge should be ~0.')
    R.append('')
    R.append('| own_stack | lineup_amp | n | boom rate | bust rate |')
    R.append('|---|---|---|---|---|')
    for r in amp_strat:
        R.append(f'| {r["own_stack"]} | {r["lineup_amp"]} | {r["n"]:,} | '
                 f'{r["boom_rate"]:.1f}% | {r["bust_rate"]:.1f}% |')

    R.append('')
    R.append('**Within-stratum amp edge (on vs off):**')
    for own in [1, 2, 3]:
        rows = [r for r in amp_strat if r['own_stack'] == own]
        on = [r for r in rows if r['lineup_amp'] == 1]
        off = [r for r in rows if r['lineup_amp'] == 0]
        if on and off and on[0]['n'] >= 50:
            edge = on[0]['boom_rate'] - off[0]['boom_rate']
            R.append(f'- own_stack={own}: {off[0]["boom_rate"]:.1f}% '
                     f'(n={off[0]["n"]:,}) -> {on[0]["boom_rate"]:.1f}% '
                     f'(n={on[0]["n"]:,}) = {edge:+.1f} pp')

    # ---- Verdict ----
    R.append('')
    R.append('## 6. Verdict')
    R.append('')

    # Headline numbers for decision
    headline_amp_edge = (amp_summary[amp_summary['lineup_amp'] == 1]['boom_rate'].iloc[0]
                         - amp_summary[amp_summary['lineup_amp'] == 0]['boom_rate'].iloc[0])
    team_edge_3v0 = None
    base = team_summary[team_summary['stack2_bucket'] == '0']['team_boom_rate']
    hi = team_summary[team_summary['stack2_bucket'] == '3+']['team_boom_rate']
    if len(base) and len(hi):
        team_edge_3v0 = hi.iloc[0] - base.iloc[0]

    # within-stratum amp edge avg across own_stack 1 and 2
    within_edges = []
    for own in [1, 2]:
        rows = [r for r in amp_strat if r['own_stack'] == own]
        on = [r for r in rows if r['lineup_amp'] == 1]
        off = [r for r in rows if r['lineup_amp'] == 0]
        if on and off and on[0]['n'] >= 50:
            within_edges.append(on[0]['boom_rate'] - off[0]['boom_rate'])
    avg_within = float(np.mean(within_edges)) if within_edges else 0.0

    # (indep_edges / indep_used already computed earlier, before report build)

    R.append(f'- Team-level boom edge (lineup_stack2 = 3+ vs = 0): '
             f'**{team_edge_3v0:+.1f} pp**' if team_edge_3v0 is not None
             else '- Team-level edge: not computable')
    R.append(f'- Year-by-year team-edge stability: '
             f'**{min(r["edge_pp"] for r in yr_stab):+.1f} to '
             f'{max(r["edge_pp"] for r in yr_stab):+.1f} pp** across '
             f'{len(yr_stab)} years')
    R.append(f'- lineup_stack_amplification raw edge (hitter level): '
             f'**{headline_amp_edge:+.1f} pp**')
    R.append(f'- amp edge AFTER stratifying by own boom_stack '
             f'(avg across own=1,2): **{avg_within:+.1f} pp**')
    R.append(f'- team-stack edge AFTER stratifying by opp_soft '
             f'(avg across both opp_soft strata, min-n=30 high cell): '
             f'**{avg_indep:+.1f} pp**')

    # Decision logic — calibrated against existing boom_stack component edges
    # (skill_spike +1.1pp, recform_hot +3.7pp, opp_soft +2.2pp; all year-stable).
    R.append('')
    yr_min_team = min(r["edge_pp"] for r in yr_stab) if yr_stab else 0
    amp_yr_min = min(r["edge_pp"] for r in amp_yr) if amp_yr else 0
    amp_yr_max = max(r["edge_pp"] for r in amp_yr) if amp_yr else 0

    # Bars:
    #  - SHIP_AS_4TH_HITTER_COMPONENT: amp edge within-stratum >= 1.5 pp AND
    #    year-stable (no year < 0) AND team-level edge confirms (>= 5 pp).
    #    Matches the bar at which skill_spike was shipped (+1.1 pp).
    #  - SHIP_AS_TEAM_BADGE_ONLY: team-level clearly real but amp small or noisy.
    #  - DON'T_SHIP redundant if avg_indep on the soft-opp side is also weak.
    if avg_within >= 1.5 and amp_yr_min >= 0 and team_edge_3v0 is not None and team_edge_3v0 >= 5:
        verdict = 'SHIP_AS_4TH_HITTER_COMPONENT'
        rationale = (f'lineup_stack_amplification adds {avg_within:+.1f} pp boom rate '
                     f'on top of own boom_stack (year-stable: {amp_yr_min:+.1f} to '
                     f'{amp_yr_max:+.1f} pp across 7 years, never negative). The '
                     f'team-level edge of {team_edge_3v0:+.1f} pp (year-stable '
                     f'{yr_min_team:+.1f} to {max(r["edge_pp"] for r in yr_stab):+.1f} pp) '
                     f'confirms the underlying lineup-correlation phenomenon is real. '
                     f'The within-soft-opp stratum edge ({(next((e for o,b,n,e in indep_used if o==1), 0)):+.1f} pp on '
                     f'opp_soft=1) confirms it is not purely opp_soft re-expressed. '
                     f'The component magnitude ({avg_within:+.1f} pp) is in the same '
                     f'range as the already-shipped skill_spike (+1.1 pp), recform_hot '
                     f'(+3.7 pp), and opp_soft (+2.2 pp) components. SHIP-CAUTIOUS as a '
                     f'4th component on the existing DISPLAY-TAG-ONLY footing.')
    elif team_edge_3v0 is not None and team_edge_3v0 >= 7 and yr_min_team >= 0:
        verdict = 'SHIP_AS_TEAM_BADGE_ONLY'
        rationale = (f'Team-level lineup_stack predicts team boom strongly '
                     f'({team_edge_3v0:+.1f} pp, year-stable) but per-hitter '
                     f'amplification on top of own boom_stack is too small or noisy '
                     f'(within-stratum {avg_within:+.1f} pp). Use as a matchup-level '
                     f'badge (team lineup heat tag) without per-hitter engine integration.')
    elif avg_indep < 1.0 and team_edge_3v0 is not None and team_edge_3v0 < 5:
        verdict = "DON'T_SHIP — REDUNDANT WITH opp_soft"
        rationale = ('The team-level lineup_stack edge mostly collapses inside '
                     'opp_soft strata. The signal is mostly opp_soft re-expressed '
                     'at the team level. Existing opp_soft component already captures '
                     'this.')
    elif team_edge_3v0 is not None and team_edge_3v0 < 3:
        verdict = "DON'T_SHIP — EFFECT TOO SMALL"
        rationale = ('Team-day lineup correlation in booming is real but small in '
                     'magnitude. Not worth the engine complexity.')
    else:
        verdict = 'NEEDS_MORE_DATA'
        rationale = ('Effect direction is right but sample at the high end (3+ '
                     'teammates with stack >= 2) is thin and year-to-year stability '
                     'is borderline. Re-run after 2026 season.')

    R.append(f'### VERDICT: **{verdict}**')
    R.append('')
    R.append(rationale)

    R.append('')
    R.append('### Engine integration spec (if SHIP_AS_4TH_HITTER_COMPONENT)')
    R.append('')
    R.append('- Component name: `lineup_amp_hitter` (or similar).')
    R.append('- Compute in `scripts/xfp/lib/hitter_boom_stack.py`:')
    R.append('  - For the target hitter, compute their boom_stack (already done).')
    R.append('  - Pull the day\'s confirmed lineup for the hitter\'s team via MLB Stats API.')
    R.append('  - For each lineup-mate, compute their boom_stack live the same way.')
    R.append('  - Flag = 1 if own boom_stack >= 1 AND >= 2 other starters have boom_stack >= 1.')
    R.append('- New boom_stack range becomes 0-4.')
    R.append('- Update `BOOM_RATE_BY_STACK` / `BUST_RATE_BY_STACK` tables in lib.')
    R.append('- DISPLAY TAG ONLY — same caveats as current boom_stack.')
    R.append('')
    R.append('### Engine integration spec (if SHIP_AS_TEAM_BADGE_ONLY)')
    R.append('')
    R.append('- Add a `team_lineup_heat` field to triangulate cards: count of starters '
             'on the hitter\'s team-day with `boom_stack >= 2`.')
    R.append('- Surface as "team stack: N/9 hitters hot" badge.')
    R.append('- Do NOT modify per-hitter boom_stack scoring or rh3.')

    # write
    out_path = OUT_DIR / 'hitter_lineup_correlation.md'
    out_path.write_text('\n'.join(R), encoding='utf-8')
    print(f'\nWrote {out_path}')

    # stdout summary
    print('\n=== SUMMARY ===')
    print(f'Team-day rows: {len(td):,}')
    print(f'Team boom edge (lineup_stack2 3+ vs 0): {team_edge_3v0:+.1f} pp' if team_edge_3v0 else '')
    print(f'lineup_stack_amplification raw edge: {headline_amp_edge:+.1f} pp')
    print(f'amp edge within own_stack strata: {avg_within:+.1f} pp')
    print(f'team-stack edge within opp_soft strata: {avg_indep:+.1f} pp')
    print(f'VERDICT: {verdict}')


if __name__ == '__main__':
    main()

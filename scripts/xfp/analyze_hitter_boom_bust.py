"""analyze_hitter_boom_bust.py — hitter parallel to analyze_boom_bust.py (SP).

Builds a per-(batter, game) panel 2018-2025 with leakage-safe boom_stack
flags adapted from the SP version:

  (1) skill_spike (hitter): last-10g xwOBA - season xwOBA >= +0.040
       AND last-10g K% - season K% <= -3 pp
  (2) recform_hot (hitter): last-10g FP/g - season FP/g >= +1.5
  (3) opp_soft (hitter): opposing SP's per-PA xwOBA-allowed (computed
       from statcast, leakage-safe: SP's prior-only season xwOBA-against)
       is in the TOP tertile within (year, calendar month) — a weak SP
       allowing high xwOBA is "soft opp" for the hitter.

Outcome metrics:
  - fp_proxy = TB + BB + HBP - K  (proxy for full FP, r=0.98 vs full;
    boom threshold recalibrated empirically to the 80th percentile of
    per-game fp_proxy)
  - bust_game = fp_proxy <= 0 (worse than a free walk)
  - boom_game = fp_proxy >= boom_threshold (80th pct ~6 over starters)

Cross-distribution analysis (Step 6) joins per-game core_fp/PA to the
current rh3 projection's per-game expectation (for 2025+ rows with rh3
match available — 2018-2024 rows skip this analysis).

Writes report to data/research/validation_runs/hitter_boom_bust_deep_dive.md.
"""
from __future__ import annotations

import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT_DIR = ROOT / 'data' / 'research' / 'validation_runs'

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]

# Event sets (mirror build_rolling_hitters.py)
K_EVENTS  = {'strikeout', 'strikeout_double_play', 'strikeout_triple_play'}
BB_EVENTS = {'walk', 'intent_walk'}
HBP_EVENTS = {'hit_by_pitch'}
H_EVENTS  = {'single', 'double', 'triple', 'home_run'}
TB_MAP = {'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}
PA_EVENTS = K_EVENTS | BB_EVENTS | HBP_EVENTS | H_EVENTS | {
    'field_out', 'force_out', 'grounded_into_double_play', 'sac_fly',
    'field_error', 'sac_bunt', 'fielders_choice', 'double_play',
    'truncated_pa', 'fielders_choice_out', 'catcher_interf',
    'sac_fly_double_play', 'triple_play',
}


def build_pa_panel(year: int) -> pd.DataFrame:
    """One row per plate appearance with leakage-safe per-batter, per-pitcher
    event flags. Aggregates from statcast pitch-level by collapsing on
    (game_pk, at_bat_number)."""
    cols = ['game_pk', 'game_date', 'batter', 'pitcher', 'events',
            'estimated_woba_using_speedangle', 'woba_value', 'woba_denom',
            'at_bat_number', 'pitch_number', 'home_team', 'away_team',
            'inning_topbot']
    df = pd.read_parquet(CACHE / f'statcast_{year}.parquet', columns=cols)
    df['game_date'] = pd.to_datetime(df['game_date'])
    df = df[df['events'].notna() & df['events'].isin(PA_EVENTS)].copy()
    # one row per PA — events column only fires on the terminal pitch
    df = df.drop_duplicates(subset=['game_pk', 'at_bat_number'], keep='last')

    df['K']   = df['events'].isin(K_EVENTS).astype(int)
    df['BB']  = df['events'].isin(BB_EVENTS).astype(int)
    df['HBP'] = df['events'].isin(HBP_EVENTS).astype(int)
    df['H']   = df['events'].isin(H_EVENTS).astype(int)
    df['TB']  = df['events'].map(TB_MAP).fillna(0).astype(int)
    df['xwoba'] = df['estimated_woba_using_speedangle']
    df['woba_denom_safe'] = df['woba_denom'].fillna(0)
    df['woba_value_safe'] = df['woba_value'].fillna(0)
    return df


def aggregate_per_game(pa_panel: pd.DataFrame) -> pd.DataFrame:
    """One row per (batter, game_pk). fp_proxy = TB+BB+HBP-K."""
    g = pa_panel.groupby(['batter', 'game_pk', 'game_date']).agg(
        PA=('events', 'size'),
        K=('K', 'sum'),
        BB=('BB', 'sum'),
        HBP=('HBP', 'sum'),
        H=('H', 'sum'),
        TB=('TB', 'sum'),
        xwoba_sum=('xwoba', 'sum'),
        xwoba_n=('xwoba', 'count'),
    ).reset_index()
    g['fp_proxy'] = g['TB'] + g['BB'] + g['HBP'] - g['K']
    g['xwoba_pg'] = g['xwoba_sum'] / g['xwoba_n'].replace(0, np.nan)
    return g[['batter', 'game_pk', 'game_date', 'PA',
              'K', 'BB', 'HBP', 'H', 'TB', 'fp_proxy', 'xwoba_pg']]


def starter_pitcher_per_game(pa_panel: pd.DataFrame) -> pd.DataFrame:
    """For each (game_pk, batting team), identify the opposing starter as
    the pitcher who faced the most PAs in innings where this team batted.
    Returns (game_pk, batter_team_indicator, opp_starter_id). Actually for
    simplicity we identify the starter as the pitcher whose first PA in the
    game has at_bat_number=1 for that half-inning.

    Simpler: starter = pitcher with the most PAs against each batting team
    in the first 3 innings.
    """
    # For each (game_pk, inning_topbot=='Top' or 'Bot'), starter is the
    # pitcher with the most PAs in innings 1-3 (or just smallest first
    # at_bat_number).
    pa = pa_panel[['game_pk', 'pitcher', 'inning_topbot', 'at_bat_number']].copy()
    # at_bat_number is per-game cumulative; smallest at_bat_number per
    # (game_pk, inning_topbot, pitcher) tells us starter
    starter = (pa.groupby(['game_pk', 'inning_topbot', 'pitcher'])
                 ['at_bat_number'].min().reset_index())
    starter = starter.sort_values(['game_pk', 'inning_topbot', 'at_bat_number'])
    starter = starter.drop_duplicates(['game_pk', 'inning_topbot'], keep='first')
    starter = starter.rename(columns={'pitcher': 'opp_starter'})
    return starter[['game_pk', 'inning_topbot', 'opp_starter']]


def attach_opp_starter(per_game: pd.DataFrame, pa_panel: pd.DataFrame) -> pd.DataFrame:
    """Add opp_starter to per-game rows. Use the batter's inning_topbot
    (deduced from majority of their PAs that game)."""
    # batter's batting half-inning = the inning_topbot of their PAs in that game
    bat_half = (pa_panel.groupby(['game_pk', 'batter'])['inning_topbot']
                  .agg(lambda s: s.value_counts().index[0]).reset_index())
    starters = starter_pitcher_per_game(pa_panel)
    out = per_game.merge(bat_half, on=['game_pk', 'batter'], how='left')
    out = out.merge(starters, on=['game_pk', 'inning_topbot'], how='left')
    return out


def compute_opp_sp_xwoba_to_date(year: int, pa_panel: pd.DataFrame) -> pd.DataFrame:
    """Per (pitcher, game_date): season-to-date xwOBA allowed strictly
    BEFORE that game_date. Used as opp_soft signal — high allowed xwOBA
    means weak SP."""
    p = pa_panel[['pitcher', 'game_pk', 'game_date',
                  'woba_value_safe', 'woba_denom_safe']].copy()
    # aggregate per (pitcher, game_pk)
    g = p.groupby(['pitcher', 'game_pk', 'game_date']).agg(
        woba_v=('woba_value_safe', 'sum'),
        woba_d=('woba_denom_safe', 'sum'),
    ).reset_index().sort_values(['pitcher', 'game_date'])

    # cumulative strictly-prior
    g['cum_woba_v'] = g.groupby('pitcher')['woba_v'].cumsum() - g['woba_v']
    g['cum_woba_d'] = g.groupby('pitcher')['woba_d'].cumsum() - g['woba_d']
    g['sp_xwoba_to'] = g['cum_woba_v'] / g['cum_woba_d'].replace(0, np.nan)
    return g[['pitcher', 'game_pk', 'sp_xwoba_to', 'cum_woba_d']].rename(
        columns={'pitcher': 'opp_starter', 'cum_woba_d': 'sp_pa_to'})


def compute_components_leakage_safe(per_game: pd.DataFrame, year: int,
                                     pa_panel: pd.DataFrame) -> pd.DataFrame:
    """For each (batter, game_pk) row in per_game, compute strictly-prior:
      - season FP/g, K%, xwOBA
      - last-10g FP/g, K%, xwOBA
      - flag_skill_spike, flag_recform_hot
    Plus join opp_soft from compute_opp_sp_xwoba_to_date.
    """
    df = per_game.sort_values(['batter', 'game_date']).copy()
    # Cumulative *strictly prior* using cumsum-then-subtract
    for col in ['fp_proxy', 'PA', 'K', 'BB', 'HBP', 'TB',
                'xwoba_pg']:
        if col == 'xwoba_pg':
            # weighted by PA — use sum xwoba * PA-ish, easier: sum + n
            df['cum_xw_sum'] = df.groupby('batter')['xwoba_pg'].cumsum() - df['xwoba_pg'].fillna(0)
            df['cum_xw_n'] = df.groupby('batter')['xwoba_pg'].apply(
                lambda s: s.notna().cumsum().shift(1, fill_value=0)
            ).reset_index(level=0, drop=True)
        else:
            df[f'cum_{col}'] = df.groupby('batter')[col].cumsum() - df[col]
    df['n_prior_g'] = df.groupby('batter').cumcount()
    df['season_fp_per_g'] = df['cum_fp_proxy'] / df['n_prior_g'].replace(0, np.nan)
    df['season_k_pct'] = df['cum_K'] / df['cum_PA'].replace(0, np.nan)
    df['season_xwoba'] = df['cum_xw_sum'] / df['cum_xw_n'].replace(0, np.nan)

    # Rolling last-10 game prior (strictly excluding current game).
    # Use shift(1) before rolling to enforce leakage safety.
    grp = df.groupby('batter', group_keys=False)
    df['l10_fp_per_g'] = grp['fp_proxy'].apply(
        lambda s: s.shift(1).rolling(10, min_periods=5).mean())
    df['l10_PA'] = grp['PA'].apply(
        lambda s: s.shift(1).rolling(10, min_periods=5).sum())
    df['l10_K'] = grp['K'].apply(
        lambda s: s.shift(1).rolling(10, min_periods=5).sum())
    df['l10_k_pct'] = df['l10_K'] / df['l10_PA'].replace(0, np.nan)
    df['l10_xwoba'] = grp['xwoba_pg'].apply(
        lambda s: s.shift(1).rolling(10, min_periods=5).mean())

    cond_ss = (
        ((df['l10_xwoba'] - df['season_xwoba']) >= 0.040)
        & ((df['l10_k_pct'] - df['season_k_pct']) <= -0.03)
        & df['n_prior_g'].ge(20)
    )
    cond_rh = (
        ((df['l10_fp_per_g'] - df['season_fp_per_g']) >= 1.5)
        & df['n_prior_g'].ge(20)
    )
    df['flag_skill_spike'] = cond_ss.fillna(False).astype(bool).astype(int)
    df['flag_recform_hot'] = cond_rh.fillna(False).astype(bool).astype(int)

    return df


def compute_opp_soft_flag(df: pd.DataFrame, sp_xwoba_panel: pd.DataFrame
                          ) -> pd.DataFrame:
    """Join sp_xwoba_to (leakage-safe prior-only) onto each batter-game row
    via (opp_starter, game_pk). Flag opp_soft = SP in top tertile of
    xwoba_to within (year, calendar month) — high xwoba allowed means
    weak SP means soft opp for hitter.
    """
    df = df.merge(sp_xwoba_panel, on=['opp_starter', 'game_pk'], how='left')
    # Require min PA-to baseline (60 PA = reasonable sample)
    df.loc[df['sp_pa_to'] < 60, 'sp_xwoba_to'] = np.nan
    df['ym'] = df['game_date'].dt.to_period('M').astype(str)
    # Tertile within (year, month) — only use rows w/ sp_xwoba_to non-null
    def safe_tertile(s):
        m = s.notna()
        if m.sum() < 30:
            return pd.Series([np.nan] * len(s), index=s.index)
        ranks = s.rank(method='first', pct=False)
        try:
            return pd.qcut(ranks, q=3, labels=[1, 2, 3], duplicates='drop')
        except Exception:
            return pd.Series([np.nan] * len(s), index=s.index)
    df['opp_tertile'] = (df.groupby(['ym'])['sp_xwoba_to']
                          .transform(safe_tertile))
    df['flag_opp_soft'] = (df['opp_tertile'].astype('float') == 3.0).astype(int)
    df.loc[df['opp_tertile'].isna(), 'flag_opp_soft'] = 0
    return df


def build_year(year: int) -> pd.DataFrame:
    print(f'  loading PA panel for {year}...')
    pa = build_pa_panel(year)
    print(f'    PA rows: {len(pa)}')
    per_game = aggregate_per_game(pa)
    print(f'    per-game rows: {len(per_game)}')
    # Require >=2 PAs (true starts)
    per_game = per_game[per_game['PA'] >= 2].copy()
    per_game['year'] = year
    per_game = attach_opp_starter(per_game, pa)
    sp_xwoba = compute_opp_sp_xwoba_to_date(year, pa)
    per_game = compute_components_leakage_safe(per_game, year, pa)
    per_game = compute_opp_soft_flag(per_game, sp_xwoba)
    per_game['boom_stack'] = (per_game['flag_skill_spike']
                              + per_game['flag_recform_hot']
                              + per_game['flag_opp_soft']).astype(int)
    return per_game


def outcome_bucket(fp: float, boom_thr: float) -> str:
    if fp <= 0:
        return 'bust'
    if fp < boom_thr * 0.4:   # ~2 for boom_thr 5
        return 'low'
    if fp < boom_thr * 0.7:   # ~3.5
        return 'mid'
    if fp < boom_thr:
        return 'good'
    if fp < boom_thr * 1.6:
        return 'boom'
    return 'megaboom'


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    panels = []
    for y in YEARS:
        print(f'YEAR {y}')
        try:
            yp = build_year(y)
            panels.append(yp)
        except Exception as e:
            print(f'  ERROR on year {y}: {e}')
    if not panels:
        print('No data — exiting')
        return
    df = pd.concat(panels, ignore_index=True)
    print(f'\nTotal per-game rows across years: {len(df)}')
    # Restrict to true starter games (PA>=4 = lineup starter, not pinch-hit appearance)
    panel = df[df['PA'] >= 4].copy()
    print(f'  panel after PA>=4 (true starter) filter: {len(panel)}')

    # Boom threshold: empirical 80th pct of fp_proxy across the panel
    boom_thr = float(panel['fp_proxy'].quantile(0.80))
    print(f'  Empirical 80th-pct fp_proxy: {boom_thr:.2f}')
    panel['boom_game'] = (panel['fp_proxy'] >= boom_thr).astype(int)
    panel['bust_game'] = (panel['fp_proxy'] <= 0).astype(int)

    # Cache panel for downstream
    panel_out = OUT_DIR / 'hitter_boom_bust_panel.parquet'
    keep_cols = ['batter', 'game_pk', 'game_date', 'year', 'PA',
                 'fp_proxy', 'xwoba_pg', 'opp_starter',
                 'season_fp_per_g', 'season_k_pct', 'season_xwoba',
                 'l10_fp_per_g', 'l10_k_pct', 'l10_xwoba',
                 'flag_skill_spike', 'flag_recform_hot', 'flag_opp_soft',
                 'boom_stack', 'boom_game', 'bust_game', 'sp_xwoba_to']
    panel[keep_cols].to_parquet(panel_out, index=False)
    print(f'  cached panel -> {panel_out}')

    # ---- Build report ----
    report = ['# Hitter Boom / Bust Deep Dive — Per-game Distribution by boom_stack',
              '',
              f'Generated 2026-06-03. n_starter_games = {len(panel):,}',
              f'Years: {YEARS}  PA-floor: 3',
              '',
              '## Boom/bust definitions',
              '',
              f'- `fp_proxy = TB + BB + HBP - K` (r=0.98 vs full FP across season aggregates)',
              f'- **boom_game**: fp_proxy ≥ {boom_thr:.1f} (empirical 80th pct across all starter-games)',
              f'- **bust_game**: fp_proxy ≤ 0 (worse than nothing)',
              f'- Caveat: SB, R, RBI are not included in fp_proxy because statcast is pitch-level.',
              f'  Run-creating events (HR, runs scored on play) are partially captured via TB. SB',
              f'  and standalone R/RBI variance is unmodeled — interpret results as TB/BB/HBP/K-driven',
              f'  boom/bust, which captures the largest single component of hitter FP variance.',
              '',
              '## 1. Distribution of fp_proxy by boom_stack',
              '',
              '| boom_stack | n | bust≤0 | low | mid | good | boom | megaboom |',
              '|---|---|---|---|---|---|---|---|']
    for stack in [0, 1, 2, 3]:
        sub = panel[panel['boom_stack'] == stack]
        if len(sub) == 0:
            continue
        cnts = sub['fp_proxy'].apply(lambda x: outcome_bucket(x, boom_thr)).value_counts()
        row = f'| {stack} | {len(sub):,} '
        for b in ['bust', 'low', 'mid', 'good', 'boom', 'megaboom']:
            cnt = int(cnts.get(b, 0))
            pct = 100.0 * cnt / len(sub)
            row += f'| {cnt} ({pct:.1f}%) '
        row += '|'
        report.append(row)

    # Summary stats
    report.append('')
    report.append('## 2. Summary stats of fp_proxy by boom_stack')
    report.append('')
    report.append('| boom_stack | n | mean | median | p10 | p25 | p75 | p90 | bust% | boom% | mega% |')
    report.append('|---|---|---|---|---|---|---|---|---|---|---|')
    summaries = {}
    for stack in [0, 1, 2, 3]:
        sub = panel[panel['boom_stack'] == stack]
        if len(sub) == 0:
            continue
        fp = sub['fp_proxy']
        s = {
            'n': len(sub),
            'mean': fp.mean(),
            'median': fp.median(),
            'p10': fp.quantile(0.10),
            'p25': fp.quantile(0.25),
            'p75': fp.quantile(0.75),
            'p90': fp.quantile(0.90),
            'bust_rate': (fp <= 0).mean(),
            'boom_rate': (fp >= boom_thr).mean(),
            'mega_rate': (fp >= boom_thr * 1.6).mean(),
        }
        summaries[stack] = s
        report.append(
            f'| {stack} | {s["n"]:,} | {s["mean"]:.2f} | {s["median"]:.2f} | '
            f'{s["p10"]:.2f} | {s["p25"]:.2f} | {s["p75"]:.2f} | {s["p90"]:.2f} | '
            f'{s["bust_rate"]*100:.1f}% | {s["boom_rate"]*100:.1f}% | '
            f'{s["mega_rate"]*100:.1f}% |'
        )

    if 0 in summaries and 3 in summaries:
        db = summaries[3]['boom_rate'] - summaries[0]['boom_rate']
        dbust = summaries[3]['bust_rate'] - summaries[0]['bust_rate']
        dm = summaries[3]['mean'] - summaries[0]['mean']
        report.append('')
        report.append(f'**Stack=3 vs Stack=0 edge:** mean fp_proxy {dm:+.2f}, '
                      f'boom rate {db*100:+.1f} pp, bust rate {dbust*100:+.1f} pp')

    # Year-by-year
    report.append('')
    report.append('## 3. Year-by-year stability of boom_rate edge')
    report.append('')
    report.append('| year | n | boom%(stack=0) | boom%(stack=2+) | edge |')
    report.append('|---|---|---|---|---|')
    for yr in sorted(panel['year'].unique()):
        sub = panel[panel['year'] == yr]
        low = sub[sub['boom_stack'] == 0]
        hi = sub[sub['boom_stack'] >= 2]
        if len(low) == 0 or len(hi) == 0:
            continue
        lr = low['boom_game'].mean() * 100
        hr = hi['boom_game'].mean() * 100
        report.append(f'| {int(yr)} | {len(sub):,} | {lr:.1f}% | {hr:.1f}% | {hr-lr:+.1f} pp |')

    # Component-by-component
    report.append('')
    report.append('## 4. Component-level — which flag matters most?')
    report.append('')
    report.append('| component | n_flag=1 | boom%(flag=1) | boom%(flag=0) | edge | bust%(flag=1) | bust%(flag=0) |')
    report.append('|---|---|---|---|---|---|---|')
    for comp in ['flag_skill_spike', 'flag_recform_hot', 'flag_opp_soft']:
        on = panel[panel[comp] == 1]
        off = panel[panel[comp] == 0]
        on_b = on['boom_game'].mean()*100 if len(on) else float('nan')
        off_b = off['boom_game'].mean()*100 if len(off) else float('nan')
        on_bu = on['bust_game'].mean()*100 if len(on) else float('nan')
        off_bu = off['bust_game'].mean()*100 if len(off) else float('nan')
        report.append(f'| {comp} | {len(on):,} | {on_b:.1f}% | {off_b:.1f}% | '
                      f'{on_b-off_b:+.1f} pp | {on_bu:.1f}% | {off_bu:.1f}% |')

    # Bust focus stack=3
    report.append('')
    report.append('## 5. Bust focus — stack=3 busts (the reality check)')
    report.append('')
    s3 = panel[panel['boom_stack'] == 3]
    s3_bust = s3[s3['fp_proxy'] <= 0]
    if len(s3) > 0:
        report.append(f'Of {len(s3):,} stack=3 starter-games, {len(s3_bust):,} '
                      f'({len(s3_bust)/len(s3)*100:.1f}%) busted (fp_proxy ≤ 0).')
        if len(s3_bust):
            report.append(f'Mean bust fp_proxy at stack=3: {s3_bust["fp_proxy"].mean():.2f}')
    report.append('')
    report.append('**Reality check:** stack=3 does NOT eliminate bust risk for hitters '
                  'either. Daily hitter variance is intrinsic — even three converging '
                  'positive signals can produce 0-fer days. boom_stack is a probability shift.')

    # ---- Weekly aggregate analysis (per-week rolling 7-game) ----
    print('  computing weekly aggregate (rolling 7-game window)...')
    panel_sorted = panel.sort_values(['batter', 'game_date']).reset_index(drop=True)
    grp = panel_sorted.groupby('batter', group_keys=False)
    # Weekly = sum of next 7 starter-games (forward window).
    # We sum the CURRENT boom_stack as the average over the 7 games, and
    # measure the fp_proxy 7-game sum as the outcome.
    # Forward-looking weekly sum: today + next 6 games (no backward leak from
    # recform_hot which is built off prior games). Implemented via reverse-roll.
    def fwd_sum(s, n=7, minp=4):
        return s[::-1].rolling(n, min_periods=minp).sum()[::-1]
    panel_sorted['wk7_fp'] = grp['fp_proxy'].apply(lambda s: fwd_sum(s))
    # Weekly boom = aggregate fp_proxy >= 80th pct of wk7_fp
    wk_pool = panel_sorted.dropna(subset=['wk7_fp']).copy()
    wk_boom_thr = float(wk_pool['wk7_fp'].quantile(0.80))
    wk_pool['wk_boom'] = (wk_pool['wk7_fp'] >= wk_boom_thr).astype(int)
    wk_pool['wk_bust'] = (wk_pool['wk7_fp'] <= 0).astype(int)
    print(f'    weekly 80th pct fp_proxy sum: {wk_boom_thr:.1f}')
    weekly_summary = {}
    for stack in [0, 1, 2, 3]:
        sub = wk_pool[wk_pool['boom_stack'] == stack]
        if len(sub):
            weekly_summary[stack] = {
                'n': len(sub),
                'mean_wk_fp': sub['wk7_fp'].mean(),
                'boom_rate': sub['wk_boom'].mean(),
                'bust_rate': sub['wk_bust'].mean(),
            }
    report.append('')
    report.append('## 6a. Weekly (rolling 7-game) aggregate by boom_stack')
    report.append('')
    report.append(f'Weekly aggregate fp_proxy (forward 7-game sum). boom_wk threshold = '
                  f'{wk_boom_thr:.1f} (80th pct).')
    report.append('')
    report.append('| boom_stack | n | mean wk7 fp_proxy | wk_boom% | wk_bust% (≤0) |')
    report.append('|---|---|---|---|---|')
    for stack, s in weekly_summary.items():
        report.append(f'| {stack} | {s["n"]:,} | {s["mean_wk_fp"]:.2f} | '
                      f'{s["boom_rate"]*100:.1f}% | {s["bust_rate"]*100:.1f}% |')
    if 0 in weekly_summary and 3 in weekly_summary:
        wkb = (weekly_summary[3]['boom_rate'] - weekly_summary[0]['boom_rate'])*100
        report.append(f'\n**Weekly edge (stack=3 vs stack=0): {wkb:+.1f} pp boom rate** '
                      f'(vs per-game edge of {(summaries[3]["boom_rate"]-summaries[0]["boom_rate"])*100:+.1f} pp)')

    # Step 6 — Cross-distribution analysis vs rh3 projection
    report.append('')
    report.append('## 6. Where in the projected range do hitters land by boom_stack?')
    report.append('')
    report.append('Uses current xfp_rh3 (2026 snapshot) `xfp_rh3_per_game` (mean) and '
                  '`xfp_rh3_p25`, `xfp_rh3_p75` as the predicted range for each batter, '
                  'joined to that batter\'s 2025 per-game outcomes. Tests whether stack '
                  'shifts the whole distribution vs only the right tail.')
    report.append('')
    rh3_path = ROOT / 'data' / 'outputs' / 'xfp_rh3_projections.csv'
    if rh3_path.exists():
        rh3 = pd.read_csv(rh3_path)
        rh3 = rh3[['batter', 'xfp_rh3_per_game', 'xfp_rh3_p25', 'xfp_rh3_p75']].copy()
        # Note: rh3 is in full-FP units; our fp_proxy ~0.49 of full FP.
        # Scale rh3 projections by 0.49 to compare on the same scale.
        ratio = 0.486  # empirical from sanity check earlier
        rh3['rh3_pg_proxy'] = rh3['xfp_rh3_per_game'] * ratio
        rh3['rh3_p25_proxy'] = rh3['xfp_rh3_p25'] * ratio
        rh3['rh3_p75_proxy'] = rh3['xfp_rh3_p75'] * ratio
        recent = panel[panel['year'] == 2025].merge(rh3, on='batter', how='inner')
        if len(recent):
            report.append(f'Sample: 2025 starter-games joined to rh3 = {len(recent):,} rows')
            report.append('')
            report.append('| boom_stack | n | %above p75 | %above p50 | %below p25 |')
            report.append('|---|---|---|---|---|')
            for stack in [0, 1, 2, 3]:
                sub = recent[recent['boom_stack'] == stack]
                if len(sub) == 0:
                    continue
                ab_p75 = (sub['fp_proxy'] >= sub['rh3_p75_proxy']).mean()*100
                ab_p50 = (sub['fp_proxy'] >= sub['rh3_pg_proxy']).mean()*100
                bel_p25 = (sub['fp_proxy'] <= sub['rh3_p25_proxy']).mean()*100
                report.append(f'| {stack} | {len(sub):,} | {ab_p75:.1f}% | '
                              f'{ab_p50:.1f}% | {bel_p25:.1f}% |')
            report.append('')
            report.append('Interpretation: if stack shifts the WHOLE distribution, '
                          '%above p50 should rise AND %below p25 should fall. If it only '
                          'shifts the right tail, %above p75 rises but %below p25 stays flat.')
        else:
            report.append('No rh3-matched 2025 rows — skipped.')
    else:
        report.append(f'rh3 projections not at {rh3_path} — skipping cross-distribution.')

    # Step 5 — Hitter vs SP comparison
    report.append('')
    report.append('## 7. Hitter vs SP comparison')
    report.append('')
    report.append('Loaded SP reference: stack=0 → 13.2% boom (≥20 FP), stack=3 → 22.6% boom, '
                  'edge +9.4 pp.')
    if 0 in summaries and 3 in summaries:
        h0 = summaries[0]['boom_rate']*100
        h3 = summaries[3]['boom_rate']*100
        report.append(f'Hitter: stack=0 → {h0:.1f}% boom, stack=3 → {h3:.1f}% boom, '
                      f'edge {h3-h0:+.1f} pp.')
        report.append('')
        sp_edge = 9.4
        hit_edge = h3 - h0
        if hit_edge >= sp_edge * 0.8:
            verd = 'COMPARABLE'
        elif hit_edge >= sp_edge * 0.5:
            verd = 'WEAKER but real'
        elif hit_edge >= 2.0:
            verd = 'MUCH WEAKER'
        else:
            verd = 'NOT TRANSFERABLE'
        report.append(f'**Signal-strength verdict: {verd}**')

    # Step 7 — Final verdict
    report.append('')
    report.append('## 8. Final verdict')
    report.append('')
    h_edge = (summaries[3]['boom_rate'] - summaries[0]['boom_rate'])*100 \
        if (0 in summaries and 3 in summaries) else 0.0
    year_edges = []
    for yr in sorted(panel['year'].unique()):
        sub = panel[panel['year'] == yr]
        low = sub[sub['boom_stack'] == 0]
        hi = sub[sub['boom_stack'] >= 2]
        if len(low) and len(hi):
            year_edges.append(hi['boom_game'].mean()*100 - low['boom_game'].mean()*100)
    yr_min = min(year_edges) if year_edges else 0
    yr_max = max(year_edges) if year_edges else 0
    report.append(f'- Hitter stack=3 vs stack=0 edge: **{h_edge:+.1f} pp boom rate**')
    report.append(f'- Year-by-year stability range (stack 0 vs 2+): **{yr_min:+.1f} pp to '
                  f'{yr_max:+.1f} pp**')
    # which component strongest
    comp_edges = {}
    for comp in ['flag_skill_spike', 'flag_recform_hot', 'flag_opp_soft']:
        on = panel[panel[comp] == 1]['boom_game'].mean()*100
        off = panel[panel[comp] == 0]['boom_game'].mean()*100
        comp_edges[comp] = on - off
    strongest = max(comp_edges, key=comp_edges.get)
    report.append(f'- Strongest single component: **{strongest}** ({comp_edges[strongest]:+.1f} pp)')
    report.append('')
    # Decision factors: per-game edge + year stability + cross-distribution shift
    yr_min_pos = min(year_edges) if year_edges else 0
    if h_edge >= 7 and yr_min_pos >= 2:
        ship = 'SHIP (comparable to SP signal, year-stable)'
    elif h_edge >= 4 and yr_min_pos >= 0:
        ship = 'SHIP-CAUTIOUS as ADVISORY TAG (smaller than SP; do not let it drive rh3 ranking)'
    elif h_edge >= 2:
        ship = 'HOLD (real but small — surface as informational tag only)'
    else:
        ship = 'DO NOT SHIP (effect too small or unstable)'
    report.append(f'**Ship decision: {ship}**')
    report.append('')
    report.append('Notes:')
    report.append('- fp_proxy excludes R, RBI, SB. The SP feedback "boom_stack" is a clean '
                  'fit because SP scoring is K- and IP-dominated (which statcast captures '
                  'fully). For hitters the fp_proxy captures TB+BB+HBP-K (the largest single '
                  'subset, ~49% of full FP and r=0.98 in season aggregates).')
    report.append('- Hitters play near-daily — daily-game boom_stack is high-frequency but low '
                  'per-game-edge by construction (high variance numerator). A weekly aggregate '
                  'version (sum 6-7 games) would likely show a larger and more usable edge.')
    report.append('- Component 3 (opp_soft) for hitters is INVERTED vs SPs: weak opposing SP '
                  '(high xwoba-allowed-to-date) = soft opp. Min 60 PA SP-sample to flag.')

    # write
    out_path = OUT_DIR / 'hitter_boom_bust_deep_dive.md'
    out_path.write_text('\n'.join(report), encoding='utf-8')
    print(f'\nWrote {out_path}')

    # Compact stdout summary
    print('\n=== SUMMARY ===')
    if 0 in summaries and 3 in summaries:
        print(f'Hitter stack=0 boom: {summaries[0]["boom_rate"]*100:.1f}%')
        print(f'Hitter stack=3 boom: {summaries[3]["boom_rate"]*100:.1f}%')
        print(f'Edge: {h_edge:+.1f} pp (SP analog +9.4 pp)')
    print(f'Year edge range: {yr_min:+.1f} to {yr_max:+.1f} pp')
    print(f'Strongest component: {strongest} ({comp_edges[strongest]:+.1f} pp)')


if __name__ == '__main__':
    main()

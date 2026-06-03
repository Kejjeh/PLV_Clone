"""validate_bust_stack.py — test bust_stack_v1.

Pre-registered: data/research/validation_runs/bust_stack_2026-06-03.md

bust_stack per-start (Mode B primary) = sum of 4 downward-process binary flags
computed using only data strictly before the start's game_date:

  (1) velo_decline_3g:    last-3-start mean FB velo - season-mean FB velo <= -1.0 mph
  (2) command_collapse:   last-3-start BB% - season BB% >= +3 pp
  (3) opp_tough_lineup:   that start's OWN lineup_xfp is in TOP tertile within
                          (year, calendar month) cohort
  (4) recent_short_outings: of last 2 starts, EITHER had ip < 5.0 OR runs_allowed > 4

Bonus component (tested separately, NOT in main stack):
  (5) velo_below_career:  season FB velo z-score within (year, month) SP cohort <= -0.5

Outputs:
  - bust_stack_validation_results.json
  - bust_stack_validation.md (verdict report — built by accompanying script call)
"""
from __future__ import annotations
import sys
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

FB_TYPES = ('FF', 'FT', 'SI')


# ---------------------------------------------------------------------------
# Load per-start panel with game_date + FB velo attached
# ---------------------------------------------------------------------------
def load_per_start_with_dates_and_velo() -> pd.DataFrame:
    p = pd.read_csv(RESEARCH / 'per_start_predictor_battle.csv')
    p = p[p['year'].isin(YEARS)].copy()
    print(f'  per_start rows in target years: {len(p)}')

    date_frames = []
    velo_frames = []
    for y in YEARS:
        sc = pd.read_parquet(CACHE / f'statcast_{y}.parquet',
                             columns=['game_pk', 'game_date', 'pitcher',
                                      'pitch_type', 'release_speed'])
        sc['game_date'] = pd.to_datetime(sc['game_date'])
        # Dates
        dates = sc[['game_pk', 'game_date']].drop_duplicates('game_pk')
        date_frames.append(dates)
        # FB velo per (pitcher, game_pk)
        fb = sc[sc['pitch_type'].isin(FB_TYPES)]
        v = (fb.groupby(['pitcher', 'game_pk'])
                .agg(fb_pitches=('release_speed', 'count'),
                     fb_velo=('release_speed', 'mean'))
                .reset_index())
        velo_frames.append(v)

    dates = pd.concat(date_frames, ignore_index=True).drop_duplicates('game_pk')
    velo = pd.concat(velo_frames, ignore_index=True)

    p = p.merge(dates, on='game_pk', how='left')
    p = p.dropna(subset=['game_date'])
    p['pitcher'] = p['pitcher'].astype('int64')
    p = p.merge(velo, on=['pitcher', 'game_pk'], how='left')

    # K%/BB% per start
    p['k_pct'] = p['actual_K'] / p['actual_PA'].clip(lower=1)
    p['bb_pct'] = p['actual_BB'] / p['actual_PA'].clip(lower=1)
    p['fp'] = p['actual_FP']
    p = p[p['actual_PA'] >= 5].copy()

    cols = ['pitcher', 'year', 'game_pk', 'game_date',
            'actual_PA', 'actual_K', 'actual_BB', 'k_pct', 'bb_pct',
            'ip', 'runs_allowed',
            'fp', 'lineup_xfp', 'fb_pitches', 'fb_velo']
    return p[cols].sort_values(['pitcher', 'year', 'game_date']).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Build per-start bust panel
# ---------------------------------------------------------------------------
def build_per_start_bust_stack(starts: pd.DataFrame) -> pd.DataFrame:
    """For each per-start row: components 1, 2, 4 use strictly-prior starts;
    component 3 uses the start's own lineup_xfp (pre-game knowable)."""
    rows = []
    for (pid, yr), grp in starts.groupby(['pitcher', 'year'], sort=False):
        grp = grp.sort_values('game_date').reset_index(drop=True)
        for i, row in grp.iterrows():
            prior = grp.iloc[:i]
            n_prior = len(prior)
            base = row.to_dict()
            base['n_prior_starts'] = n_prior

            # Component 2: command collapse (BB% rise) — needs >=3 prior
            if n_prior >= 3:
                sBB = prior['actual_BB'].sum() / max(prior['actual_PA'].sum(), 1)
                last3 = prior.tail(3)
                l3BB = last3['actual_BB'].sum() / max(last3['actual_PA'].sum(), 1)
                dBB_pp = (l3BB - sBB) * 100.0
                f_cc = int(dBB_pp >= 3.0)
            else:
                f_cc = 0

            # Component 1: velo decline — needs >=3 prior starts WITH FB velo recorded
            prior_v = prior.dropna(subset=['fb_velo'])
            if len(prior_v) >= 3:
                season_velo = prior_v['fb_velo'].mean()
                l3v = prior_v.tail(3)
                last3_velo = l3v['fb_velo'].mean()
                dv = last3_velo - season_velo
                f_vd = int(dv <= -1.0)
            else:
                f_vd = 0

            # Component 4: recent short outings — last 2 prior starts
            if n_prior >= 2:
                last2 = prior.tail(2)
                short_or_blowup = (
                    (last2['ip'].fillna(99) < 5.0) |
                    (last2['runs_allowed'].fillna(0) > 4)
                )
                f_rs = int(bool(short_or_blowup.any()))
            else:
                f_rs = 0

            base.update({
                'flag_velo_decline': f_vd,
                'flag_command_collapse': f_cc,
                'flag_recent_short': f_rs,
            })
            rows.append(base)
    out = pd.DataFrame(rows)

    # Component 3: opp_tough = top tertile of lineup_xfp within (year, month)
    out['ym'] = out['game_date'].dt.to_period('M').astype(str)
    out['opp_tertile'] = (
        out.groupby(['year', 'ym'])['lineup_xfp']
           .transform(lambda s: pd.qcut(s.rank(method='first'), q=3,
                                         labels=[1, 2, 3], duplicates='drop')
                                if s.notna().sum() >= 30 else pd.Series([np.nan]*len(s), index=s.index))
    )
    # Top tertile (tough offense = HIGH lineup_xfp)
    out['flag_opp_tough'] = (out['opp_tertile'].astype('float') == 3.0).astype(int)
    out.loc[out['opp_tertile'].isna(), 'flag_opp_tough'] = 0

    # Main bust_stack (4 components)
    out['bust_stack'] = (
        out['flag_velo_decline']
        + out['flag_command_collapse']
        + out['flag_opp_tough']
        + out['flag_recent_short']
    ).astype(int)

    out['bust_outcome'] = (out['fp'] < 0.0).astype(int)

    # Bonus: velo_below_career — z-score of season FB velo within (year, ym) SP cohort
    # Per-pitcher rolling-to-date mean FB velo BEFORE this start
    out = out.sort_values(['pitcher', 'year', 'game_date']).reset_index(drop=True)
    # Compute season-to-date mean velo per pitcher up to (but not including) row i.
    def season_velo_to_date(group):
        v = group['fb_velo']
        cum_sum = v.fillna(0).cumsum().shift(1)
        cum_n = v.notna().astype(int).cumsum().shift(1)
        return cum_sum / cum_n.replace(0, np.nan)
    out['season_velo_prior'] = out.groupby(['pitcher', 'year']).apply(
        season_velo_to_date).reset_index(level=[0, 1], drop=True)
    # Cohort z within (year, ym)
    out['velo_z'] = (
        out.groupby(['year', 'ym'])['season_velo_prior']
           .transform(lambda s: (s - s.mean()) / s.std(ddof=0) if s.notna().sum() >= 30 else pd.Series([np.nan]*len(s), index=s.index))
    )
    out['flag_velo_below_career'] = (out['velo_z'] <= -0.5).astype(int)
    out.loc[out['velo_z'].isna(), 'flag_velo_below_career'] = 0

    return out


# ---------------------------------------------------------------------------
# Per-component bust edge
# ---------------------------------------------------------------------------
def per_component_edge(panel: pd.DataFrame, comps: list[str]) -> dict:
    out = {}
    n_total = len(panel)
    base_rate = float(panel['bust_outcome'].mean())
    for c in comps:
        m = panel[c] == 1
        n1 = int(m.sum())
        n0 = int((~m).sum())
        bust1 = float(panel.loc[m, 'bust_outcome'].mean()) if n1 > 0 else float('nan')
        bust0 = float(panel.loc[~m, 'bust_outcome'].mean()) if n0 > 0 else float('nan')
        lift_pp = (bust1 - bust0) * 100.0
        # 2x2 chi²
        b1 = int(panel.loc[m, 'bust_outcome'].sum()); nb1 = n1 - b1
        b0 = int(panel.loc[~m, 'bust_outcome'].sum()); nb0 = n0 - b0
        table = np.array([[b1, nb1], [b0, nb0]])
        if min(table.sum(axis=0)) >= 5 and min(table.sum(axis=1)) >= 5:
            chi2, p, _, _ = chi2_contingency(table)
        else:
            chi2, p = float('nan'), float('nan')
        out[c] = {
            'n_flag1': n1, 'n_flag0': n0,
            'bust_rate_flag1': bust1, 'bust_rate_flag0': bust0,
            'lift_pp': lift_pp,
            'chi2': float(chi2), 'p_value': float(p),
            'base_rate': base_rate, 'fire_rate': n1 / max(n_total, 1),
        }
    return out


# ---------------------------------------------------------------------------
# Stack-sum bust rate
# ---------------------------------------------------------------------------
def stack_bust_rate(panel: pd.DataFrame, stack_col: str, max_n: int = 4) -> dict:
    buckets = {}
    for b in range(max_n + 1):
        m = panel[stack_col] == b
        n = int(m.sum())
        busts = int(panel.loc[m, 'bust_outcome'].sum())
        rate = busts / n if n > 0 else float('nan')
        buckets[b] = {
            'n': n, 'busts': busts, 'bust_rate': rate,
            'mean_fp': float(panel.loc[m, 'fp'].mean()) if n > 0 else float('nan'),
            'mean_bust_fp': float(panel.loc[m & (panel['bust_outcome'] == 1), 'fp'].mean()) if busts > 0 else float('nan'),
        }
    # Chi² for stack >= 3 vs == 0
    low = panel[panel[stack_col] == 0]
    hi = panel[panel[stack_col] >= 3]
    if len(hi) >= 10 and len(low) >= 10:
        table = np.array([
            [int(hi['bust_outcome'].sum()),  int((1 - hi['bust_outcome']).sum())],
            [int(low['bust_outcome'].sum()), int((1 - low['bust_outcome']).sum())],
        ])
        chi2, p, _, _ = chi2_contingency(table)
    else:
        chi2, p = float('nan'), float('nan')
    return {
        'buckets': buckets,
        'chi2_hi_vs_low': {'chi2': float(chi2), 'p_value': float(p),
                           'low_n': int(len(low)), 'hi_n': int(len(hi)),
                           'low_bust_rate': float(low['bust_outcome'].mean()) if len(low) else None,
                           'hi_bust_rate': float(hi['bust_outcome'].mean()) if len(hi) else None,
                           },
    }


# ---------------------------------------------------------------------------
# Year-by-year stability
# ---------------------------------------------------------------------------
def yearly_stability(panel: pd.DataFrame, stack_col: str) -> dict:
    out = {}
    for y, grp in panel.groupby('year'):
        n_lo = int((grp[stack_col] == 0).sum())
        n_hi = int((grp[stack_col] >= 3).sum())
        if n_lo < 50 or n_hi < 10:
            continue
        r_lo = float(grp.loc[grp[stack_col] == 0, 'bust_outcome'].mean())
        r_hi = float(grp.loc[grp[stack_col] >= 3, 'bust_outcome'].mean())
        out[int(y)] = {
            'n': int(len(grp)),
            'bust_rate_stack0': r_lo,
            'bust_rate_stack3plus': r_hi,
            'lift_pp': (r_hi - r_lo) * 100.0,
            'n_stack0': n_lo, 'n_stack3plus': n_hi,
        }
    return out


# ---------------------------------------------------------------------------
# Independence with boom_stack components
# ---------------------------------------------------------------------------
def independence_with_boom(panel: pd.DataFrame) -> dict:
    """Build the boom_stack components on the same panel and report correlation
    of each bust component with each boom component."""
    p = panel.copy()
    # boom components — replicate streamer_boom_stack pattern, per-start
    rows = []
    for (pid, yr), grp in p.groupby(['pitcher', 'year'], sort=False):
        grp = grp.sort_values('game_date').reset_index(drop=True)
        for i in range(len(grp)):
            prior = grp.iloc[:i]
            if len(prior) < 3:
                rows.append({'idx': grp.iloc[i].name,
                             'boom_skill_spike': 0, 'boom_recform_hot': 0})
                continue
            sK = prior['actual_K'].sum() / max(prior['actual_PA'].sum(), 1)
            sBB = prior['actual_BB'].sum() / max(prior['actual_PA'].sum(), 1)
            sFP = prior['fp'].mean()
            last3 = prior.tail(3)
            l3K = last3['actual_K'].sum() / max(last3['actual_PA'].sum(), 1)
            l3BB = last3['actual_BB'].sum() / max(last3['actual_PA'].sum(), 1)
            l3FP = last3['fp'].mean()
            dK_pp = (l3K - sK) * 100.0
            dBB_pp = (l3BB - sBB) * 100.0
            dFP = l3FP - sFP
            f_ss = int((dK_pp >= 3.0) and (dBB_pp <= -1.0))
            f_rh = int(dFP >= 3.0)
            rows.append({'idx': grp.iloc[i].name,
                         'boom_skill_spike': f_ss, 'boom_recform_hot': f_rh})
    bdf = pd.DataFrame(rows).set_index('idx')
    p = p.join(bdf, how='left')
    p['boom_opp_soft'] = (p['opp_tertile'].astype('float') == 1.0).astype(int)
    p[['boom_skill_spike', 'boom_recform_hot', 'boom_opp_soft']] = (
        p[['boom_skill_spike', 'boom_recform_hot', 'boom_opp_soft']].fillna(0).astype(int))
    p['boom_stack'] = p['boom_skill_spike'] + p['boom_recform_hot'] + p['boom_opp_soft']

    bust_cs = ['flag_velo_decline', 'flag_command_collapse',
               'flag_opp_tough', 'flag_recent_short']
    boom_cs = ['boom_skill_spike', 'boom_recform_hot', 'boom_opp_soft']
    corr_matrix = {}
    for bc in bust_cs:
        corr_matrix[bc] = {bo: float(p[bc].corr(p[bo])) for bo in boom_cs}

    # 2D heatmap boom_stack x bust_stack
    heat_n = {}
    heat_bust = {}
    heat_boom = {}
    heat_meanfp = {}
    for bo in [0, 1, 2, 3]:
        heat_n[bo] = {}
        heat_bust[bo] = {}
        heat_boom[bo] = {}
        heat_meanfp[bo] = {}
        for bu in [0, 1, 2, 3, 4]:
            m = (p['boom_stack'] == bo) & (p['bust_stack'] == bu)
            n = int(m.sum())
            heat_n[bo][bu] = n
            if n > 0:
                heat_bust[bo][bu] = float(p.loc[m, 'bust_outcome'].mean())
                heat_boom[bo][bu] = float((p.loc[m, 'fp'] >= 20).mean())
                heat_meanfp[bo][bu] = float(p.loc[m, 'fp'].mean())
            else:
                heat_bust[bo][bu] = float('nan')
                heat_boom[bo][bu] = float('nan')
                heat_meanfp[bo][bu] = float('nan')

    return {
        'corr_matrix': corr_matrix,
        'heatmap_n':       heat_n,
        'heatmap_bust':    heat_bust,
        'heatmap_boom':    heat_boom,
        'heatmap_mean_fp': heat_meanfp,
    }


# ---------------------------------------------------------------------------
# Tier amplification
# ---------------------------------------------------------------------------
def per_tier_bust(panel: pd.DataFrame) -> dict:
    """Tier by per-start rolling fp_per_start quartile within (year, ym).

    Use a 4-tier split keyed to streamer/backend/sp2_sp3/ace pattern.
    """
    p = panel.copy()
    p = p.sort_values(['pitcher', 'year', 'game_date'])
    p['cum_fp'] = p.groupby(['pitcher', 'year'])['fp'].cumsum() - p['fp']
    p['cum_n'] = p.groupby(['pitcher', 'year']).cumcount()
    p['rolling_fp'] = p['cum_fp'] / p['cum_n'].replace(0, np.nan)
    p['rolling_fp_pct'] = (p.groupby(['year', 'ym'])['rolling_fp']
                            .transform(lambda s: s.rank(pct=True)))

    def tier(pct):
        if pd.isna(pct):
            return None
        if pct >= 0.85:
            return 'ace'
        if pct >= 0.60:
            return 'sp2_sp3'
        if pct >= 0.40:
            return 'backend'
        return 'streamer'

    p['tier'] = p['rolling_fp_pct'].apply(tier)
    out = {}
    for t in ['ace', 'sp2_sp3', 'backend', 'streamer']:
        sub = p[p['tier'] == t]
        buckets = {}
        for b in range(5):
            m = sub['bust_stack'] == b
            n = int(m.sum())
            buckets[b] = {
                'n': n,
                'bust_rate': float(sub.loc[m, 'bust_outcome'].mean()) if n > 0 else float('nan'),
                'mean_fp': float(sub.loc[m, 'fp'].mean()) if n > 0 else float('nan'),
            }
        out[t] = {'n': int(len(sub)), 'buckets': buckets}
    return out


# ---------------------------------------------------------------------------
# Bonus: 5-component stack with velo_below_career
# ---------------------------------------------------------------------------
def stack5_bust(panel: pd.DataFrame) -> dict:
    p = panel.copy()
    p['bust_stack5'] = p['bust_stack'] + p['flag_velo_below_career']
    return stack_bust_rate(p, 'bust_stack5', max_n=5)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print('=== validate_bust_stack ===')

    print('Step 1: load per-start panel + game_date + FB velo...')
    starts = load_per_start_with_dates_and_velo()
    print(f'  per-start rows: {len(starts)}')
    print(f'  rows with FB velo: {starts["fb_velo"].notna().sum()} '
          f'({starts["fb_velo"].notna().mean():.1%})')

    print('Step 2: build per-start bust panel...')
    panel = build_per_start_bust_stack(starts)
    print(f'  panel rows: {len(panel)}')
    flag_cols = ['flag_velo_decline', 'flag_command_collapse',
                 'flag_opp_tough', 'flag_recent_short',
                 'flag_velo_below_career']
    print('  flag fire rates:')
    for c in flag_cols:
        print(f'    {c}: {panel[c].mean():.3%}  (n_flag=1 = {int(panel[c].sum())})')
    print('  bust_stack distribution:')
    print(panel['bust_stack'].value_counts().sort_index().to_string())
    print(f'  bust base rate (fp<0): {panel["bust_outcome"].mean():.3%}')

    print('\nStep 3: per-component bust edge...')
    comp_results = per_component_edge(panel,
                                       ['flag_velo_decline', 'flag_command_collapse',
                                        'flag_opp_tough', 'flag_recent_short',
                                        'flag_velo_below_career'])
    for c, r in comp_results.items():
        print(f'  {c}: flag1 bust={r["bust_rate_flag1"]:.3%}  flag0={r["bust_rate_flag0"]:.3%}  '
              f'lift={r["lift_pp"]:+.2f}pp  chi2={r["chi2"]:.2f}  p={r["p_value"]:.4g}  '
              f'n1={r["n_flag1"]}')

    print('\nStep 4: stack-sum bust rate (main 4-component bust_stack)...')
    stack_results = stack_bust_rate(panel, 'bust_stack', max_n=4)
    for b, info in stack_results['buckets'].items():
        print(f'  stack={b}: n={info["n"]:>5d}  busts={info["busts"]:>4d}  '
              f'rate={info["bust_rate"]:.3%}  mean_fp={info["mean_fp"]:.2f}')
    cs = stack_results['chi2_hi_vs_low']
    print(f'  Chi² (stack>=3 vs ==0): chi2={cs["chi2"]:.3f}  p={cs["p_value"]:.4g}')
    print(f'    low(n={cs["low_n"]}) rate={cs["low_bust_rate"]:.3%}  '
          f'hi(n={cs["hi_n"]}) rate={cs["hi_bust_rate"]:.3%}')

    print('\nStep 5: year-by-year stability...')
    yearly = yearly_stability(panel, 'bust_stack')
    for y, info in sorted(yearly.items()):
        print(f'  {y}: stack=0 bust={info["bust_rate_stack0"]:.3%}  '
              f'stack>=3 bust={info["bust_rate_stack3plus"]:.3%}  '
              f'lift={info["lift_pp"]:+.2f}pp  (n0={info["n_stack0"]} n3+={info["n_stack3plus"]})')

    print('\nStep 6: independence with boom_stack + heatmap...')
    indep = independence_with_boom(panel)
    print('  bust x boom component corr matrix:')
    for bc, row in indep['corr_matrix'].items():
        for boc, v in row.items():
            print(f'    corr({bc}, {boc}) = {v:+.3f}')
    print('  boom_stack x bust_stack n-cell heatmap:')
    print(f'    {"":12} {"bust=0":>8} {"bust=1":>8} {"bust=2":>8} {"bust=3":>8} {"bust=4":>8}')
    for bo in [0, 1, 2, 3]:
        cells = [f'{indep["heatmap_n"][bo][bu]:>8d}' for bu in range(5)]
        print(f'    boom={bo}:   ' + ' '.join(cells))
    print('  boom_stack x bust_stack BUST RATE heatmap:')
    for bo in [0, 1, 2, 3]:
        cells = []
        for bu in range(5):
            v = indep['heatmap_bust'][bo][bu]
            cells.append(f'{v:>7.2%}' if not np.isnan(v) else '    n/a')
        print(f'    boom={bo}:   ' + ' '.join(cells))

    print('\nStep 7: per-tier bust amplification...')
    tier = per_tier_bust(panel)
    for t, info in tier.items():
        print(f'  tier={t} (n={info["n"]}):')
        for b, c in info['buckets'].items():
            print(f'    stack={b}: n={c["n"]:>4d}  bust={c["bust_rate"]:.3%}  '
                  f'mean_fp={c["mean_fp"]:.2f}' if c["n"] > 0 else
                  f'    stack={b}: n=0')

    print('\nStep 8: bonus — 5-component stack with velo_below_career...')
    stack5 = stack5_bust(panel)
    for b, info in stack5['buckets'].items():
        print(f'  stack5={b}: n={info["n"]:>5d}  busts={info["busts"]:>4d}  '
              f'rate={info["bust_rate"]:.3%}  mean_fp={info["mean_fp"]:.2f}')

    # Save
    output = {
        'panel_size': len(panel),
        'flag_fire_rates': {c: float(panel[c].mean()) for c in flag_cols},
        'bust_stack_distribution': panel['bust_stack'].value_counts().sort_index().to_dict(),
        'bust_base_rate': float(panel['bust_outcome'].mean()),
        'per_component': comp_results,
        'stack_4comp': stack_results,
        'stack_5comp': stack5,
        'yearly_stability': yearly,
        'independence_with_boom': indep,
        'per_tier': tier,
    }
    out_json = OUT_DIR / 'bust_stack_v1_results.json'
    with open(out_json, 'w') as fh:
        json.dump(output, fh, indent=2, default=lambda x: None if (isinstance(x, float) and np.isnan(x)) else float(x))
    print(f'\nWrote {out_json}')

    return output


if __name__ == '__main__':
    main()

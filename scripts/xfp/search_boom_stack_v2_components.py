"""search_boom_stack_v2_components.py

Search for a 4th orthogonal component to add to streamer_boom_stack_v1.

v1 components (from validate_streamer_boom_stack.py, Mode B per-start):
  - flag_skill_spike   : last3 K% >= +3pp, BB% <= -1pp vs season
  - flag_recform_hot   : last3 FP >= +3 vs season
  - flag_opp_soft      : opp lineup_xfp in bottom tertile within (year, month)

Candidates (4th component) tested here:
  C1 velo_spike       : last3 mean velo of primary FB >= +0.5 mph vs season
  C2 csw_spike        : last3 CSW% >= +3 pp vs season
  C3 mix_change       : primary pitch usage shift |Δ| >= 10 pp in last3 vs season
  C4 park_friendly    : venue park HR factor <= 25th pct (pitcher-friendly venue)
  C5 high_k_pitcher   : season K% z-score vs league >= +0.5

For each candidate, compute on the streamer-pool subset (same definition as v1):
  Step 2: boom rate at candidate=1 vs candidate=0 + chi-squared
  Step 3: marginal lift at v1 stack=3 (boom rate with vs without candidate)
  Step 4: correlation with each existing v1 flag (orthogonality)
  Step 5: year-by-year stability

Writes data/research/validation_runs/boom_stack_v2_search.md + .json
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
CSW_DESCS = {'called_strike', 'swinging_strike', 'swinging_strike_blocked',
             'foul_tip', 'missed_bunt'}
FB_TYPES = {'FF', 'FT', 'SI', 'FC'}  # fastball family


# ---------------------------------------------------------------------------
# Step 1 — Load per-start panel with game_date attached
# ---------------------------------------------------------------------------
def load_per_start_with_dates() -> pd.DataFrame:
    p = pd.read_csv(RESEARCH / 'per_start_predictor_battle.csv')
    p = p[p['year'].isin(YEARS)].copy()
    date_frames = []
    for y in YEARS:
        sc = pd.read_parquet(CACHE / f'statcast_{y}.parquet',
                             columns=['game_pk', 'game_date', 'home_team'])
        sc = sc.drop_duplicates('game_pk')
        date_frames.append(sc)
    dates = pd.concat(date_frames, ignore_index=True).drop_duplicates('game_pk')
    dates['game_date'] = pd.to_datetime(dates['game_date'])
    p = p.merge(dates, on='game_pk', how='left')
    p = p.dropna(subset=['game_date'])
    p['pitcher'] = p['pitcher'].astype('int64')
    p['k_pct'] = p['actual_K'] / p['actual_PA'].clip(lower=1)
    p['bb_pct'] = p['actual_BB'] / p['actual_PA'].clip(lower=1)
    p['fp'] = p['actual_FP']
    p = p[p['actual_PA'] >= 5].copy()
    return p[['pitcher', 'year', 'game_pk', 'game_date', 'home_team',
              'actual_PA', 'actual_K', 'actual_BB', 'k_pct', 'bb_pct',
              'fp', 'lineup_xfp']].sort_values(['pitcher', 'year', 'game_date'])


# ---------------------------------------------------------------------------
# Step 2 — Build per-start pitch-level features (velo of FB, CSW%, primary pitch share)
# ---------------------------------------------------------------------------
def build_per_start_pitch_features() -> pd.DataFrame:
    print('Step 2: building per-start pitch-level features (velo / csw / mix)...')
    frames = []
    for y in YEARS:
        print(f'  year {y}...')
        sc = pd.read_parquet(CACHE / f'statcast_{y}.parquet',
                             columns=['game_pk', 'pitcher', 'pitch_type',
                                      'description', 'release_speed'])
        sc = sc.dropna(subset=['pitcher', 'pitch_type'])
        sc['pitcher'] = sc['pitcher'].astype('int64')
        sc['is_csw'] = sc['description'].isin(CSW_DESCS).astype(int)
        sc['is_fb'] = sc['pitch_type'].isin(FB_TYPES).astype(int)
        # Per start aggregates
        agg = sc.groupby(['game_pk', 'pitcher']).agg(
            n_pitches=('pitch_type', 'size'),
            csw=('is_csw', 'sum'),
            fb_velo_sum=('release_speed', lambda s: s[sc.loc[s.index, 'is_fb'] == 1].sum()),
            fb_velo_n=('is_fb', 'sum'),
        ).reset_index()
        # Primary pitch share per start
        pp = sc.groupby(['game_pk', 'pitcher', 'pitch_type']).size().reset_index(name='n')
        pp_top = pp.sort_values('n', ascending=False).groupby(['game_pk', 'pitcher']).head(1)
        pp_top = pp_top.rename(columns={'pitch_type': 'primary_pt', 'n': 'primary_n'})
        agg = agg.merge(pp_top[['game_pk', 'pitcher', 'primary_pt', 'primary_n']],
                        on=['game_pk', 'pitcher'], how='left')
        agg['year'] = y
        frames.append(agg)
    out = pd.concat(frames, ignore_index=True)
    out['csw_pct'] = out['csw'] / out['n_pitches'].clip(lower=1)
    out['fb_velo'] = np.where(out['fb_velo_n'] > 0,
                              out['fb_velo_sum'] / out['fb_velo_n'].replace(0, np.nan),
                              np.nan)
    out['primary_share'] = out['primary_n'] / out['n_pitches'].clip(lower=1)
    return out[['game_pk', 'pitcher', 'year', 'n_pitches',
                'csw_pct', 'fb_velo', 'primary_pt', 'primary_share']]


# ---------------------------------------------------------------------------
# Step 3 — Build per-start v1 boom_stack panel (replicate Mode B)
# ---------------------------------------------------------------------------
def build_v1_per_start(starts: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (pid, yr), grp in starts.groupby(['pitcher', 'year'], sort=False):
        grp = grp.sort_values('game_date').reset_index(drop=True)
        for i, row in grp.iterrows():
            prior = grp.iloc[:i]
            if len(prior) < 3:
                rows.append({**row.to_dict(),
                             'flag_skill_spike': 0,
                             'flag_recform_hot': 0,
                             'n_prior_starts': len(prior)})
                continue
            sK = prior['actual_K'].sum() / max(prior['actual_PA'].sum(), 1)
            sBB = prior['actual_BB'].sum() / max(prior['actual_PA'].sum(), 1)
            sFP = prior['fp'].mean()
            last3 = prior.tail(3)
            l3K = last3['actual_K'].sum() / max(last3['actual_PA'].sum(), 1)
            l3BB = last3['actual_BB'].sum() / max(last3['actual_PA'].sum(), 1)
            l3FP = last3['fp'].mean()
            rows.append({**row.to_dict(),
                         'flag_skill_spike': int(((l3K - sK) * 100 >= 3.0) and
                                                 ((l3BB - sBB) * 100 <= -1.0)),
                         'flag_recform_hot': int((l3FP - sFP) >= 3.0),
                         'n_prior_starts': len(prior)})
    out = pd.DataFrame(rows)
    out['ym'] = out['game_date'].dt.to_period('M').astype(str)
    out['opp_tertile'] = (
        out.groupby(['year', 'ym'])['lineup_xfp']
           .transform(lambda s: pd.qcut(s.rank(method='first'), q=3,
                                         labels=[1, 2, 3], duplicates='drop')
                                if s.notna().sum() >= 30 else pd.Series([np.nan]*len(s), index=s.index))
    )
    out['flag_opp_soft'] = (out['opp_tertile'].astype('float') == 1.0).astype(int)
    out.loc[out['opp_tertile'].isna(), 'flag_opp_soft'] = 0
    out['boom_stack_v1'] = (out['flag_skill_spike']
                            + out['flag_recform_hot']
                            + out['flag_opp_soft'])
    out['boom_outcome'] = (out['fp'] >= 20.0).astype(int)
    return out


# ---------------------------------------------------------------------------
# Step 4 — Merge pitch features + build pre-start rolling, then candidate flags
# ---------------------------------------------------------------------------
def add_candidates(panel: pd.DataFrame, pitch_feats: pd.DataFrame,
                   park: pd.DataFrame) -> pd.DataFrame:
    panel = panel.merge(pitch_feats, on=['game_pk', 'pitcher', 'year'], how='left')

    # For velo / csw / mix, compute strictly-prior season + last3
    panel = panel.sort_values(['pitcher', 'year', 'game_date']).reset_index(drop=True)

    def rolling_prior(group_cols, target):
        # cumulative-prior mean (excluding current row)
        g = panel.groupby(group_cols)
        cum_sum = g[target].cumsum() - panel[target].fillna(0)
        cum_n = g[target].apply(lambda s: s.notna().cumsum().shift(fill_value=0)).reset_index(level=group_cols, drop=True)
        cum_n = cum_n.reindex(panel.index)
        season_mean = cum_sum / cum_n.replace(0, np.nan)
        # last3 prior mean (rolling window 3 of strictly prior)
        last3 = (g[target].shift(1).rolling(3, min_periods=1).mean())
        return season_mean, last3

    # velo
    s_velo, l3_velo = rolling_prior(['pitcher', 'year'], 'fb_velo')
    panel['season_velo'] = s_velo
    panel['last3_velo'] = l3_velo
    panel['velo_delta'] = panel['last3_velo'] - panel['season_velo']

    # csw
    s_csw, l3_csw = rolling_prior(['pitcher', 'year'], 'csw_pct')
    panel['season_csw'] = s_csw
    panel['last3_csw'] = l3_csw
    panel['csw_delta_pp'] = (panel['last3_csw'] - panel['season_csw']) * 100.0

    # primary pitch usage shift - need to compute per primary_pt
    # Simpler proxy: just primary_share variation
    s_ps, l3_ps = rolling_prior(['pitcher', 'year'], 'primary_share')
    panel['season_primary_share'] = s_ps
    panel['last3_primary_share'] = l3_ps
    panel['mix_delta_pp'] = (panel['last3_primary_share'] - panel['season_primary_share']) * 100.0

    # park factor — venue is home_team of game
    park_lookup = park.set_index(['year', 'team_abbr'])
    pf_hr = panel.apply(
        lambda r: park_lookup.loc[(int(r['year']), r['home_team']), 'pf_HR']
                   if (int(r['year']), r['home_team']) in park_lookup.index else np.nan,
        axis=1,
    )
    panel['pf_HR'] = pf_hr.astype(float)

    # Per-year park-friendly threshold (25th pct = pitcher-friendly)
    panel['pf_HR_25pct'] = panel.groupby('year')['pf_HR'].transform(lambda s: s.quantile(0.25))

    # Season K% per pitcher (cumulative prior)
    panel['k_prior_sum'] = panel.groupby(['pitcher', 'year'])['actual_K'].cumsum() - panel['actual_K']
    panel['pa_prior_sum'] = panel.groupby(['pitcher', 'year'])['actual_PA'].cumsum() - panel['actual_PA']
    panel['season_k_pct'] = panel['k_prior_sum'] / panel['pa_prior_sum'].replace(0, np.nan)
    # League K% in (year, ym) as denominator z-score
    def _z(s):
        sd = s.std(ddof=0)
        if sd is None or not np.isfinite(sd) or sd == 0:
            return pd.Series(np.zeros(len(s)), index=s.index)
        return (s - s.mean()) / sd
    panel['k_pct_z'] = panel.groupby(['year', 'ym'])['season_k_pct'].transform(_z)

    # Candidate flags
    panel['cand_velo_spike'] = ((panel['velo_delta'] >= 0.5) &
                                panel['n_prior_starts'].ge(3)).astype(int)
    panel['cand_csw_spike'] = ((panel['csw_delta_pp'] >= 3.0) &
                               panel['n_prior_starts'].ge(3)).astype(int)
    panel['cand_mix_change'] = ((panel['mix_delta_pp'].abs() >= 10.0) &
                                panel['n_prior_starts'].ge(3)).astype(int)
    panel['cand_park_friendly'] = (panel['pf_HR'] <= panel['pf_HR_25pct']).astype(int)
    panel['cand_high_k_pitcher'] = ((panel['k_pct_z'] >= 0.5) &
                                    panel['n_prior_starts'].ge(3)).astype(int)
    return panel


# ---------------------------------------------------------------------------
# Step 5 — Streamer-pool subset (same definition as v1)
# ---------------------------------------------------------------------------
def streamer_subset(panel: pd.DataFrame) -> pd.DataFrame:
    df = panel.sort_values(['pitcher', 'year', 'game_date']).copy()
    df['cum_fp'] = df.groupby(['pitcher', 'year'])['fp'].cumsum() - df['fp']
    df['cum_n'] = df.groupby(['pitcher', 'year']).cumcount()
    df['rolling_fp'] = df['cum_fp'] / df['cum_n'].replace(0, np.nan)
    df['rolling_fp_pct'] = (
        df.groupby(['year', 'ym'])['rolling_fp']
          .transform(lambda s: s.rank(pct=True))
    )
    return df[(df['rolling_fp_pct'].notna()) &
              (df['rolling_fp_pct'] <= 0.50) &
              (df['cum_n'] >= 3)].copy()


# ---------------------------------------------------------------------------
# Step 6 — Per-candidate analysis
# ---------------------------------------------------------------------------
def analyze_candidate(streamer: pd.DataFrame, cand: str,
                      v1_flags: list[str]) -> dict:
    res: dict = {'candidate': cand}
    sub = streamer[streamer[cand].notna()].copy()
    n_total = len(sub)
    f1 = sub[sub[cand] == 1]
    f0 = sub[sub[cand] == 0]
    res['flag_rate'] = float(sub[cand].mean())
    res['n_flag1'] = int(len(f1))
    res['n_flag0'] = int(len(f0))
    res['boom_rate_flag1'] = float(f1['boom_outcome'].mean()) if len(f1) else None
    res['boom_rate_flag0'] = float(f0['boom_outcome'].mean()) if len(f0) else None
    if len(f1) >= 5 and len(f0) >= 5:
        tbl = np.array([
            [int(f1['boom_outcome'].sum()), int((1 - f1['boom_outcome']).sum())],
            [int(f0['boom_outcome'].sum()), int((1 - f0['boom_outcome']).sum())],
        ])
        chi2, p, _, _ = chi2_contingency(tbl)
        res['chi2'] = float(chi2)
        res['p_value'] = float(p)
    else:
        res['chi2'] = None
        res['p_value'] = None

    # Marginal at v1 stack=3
    s3 = sub[sub['boom_stack_v1'] == 3]
    s3_1 = s3[s3[cand] == 1]
    s3_0 = s3[s3[cand] == 0]
    res['stack3_n'] = int(len(s3))
    res['stack3_baseline_boom'] = float(s3['boom_outcome'].mean()) if len(s3) else None
    res['stack3_cand1_n'] = int(len(s3_1))
    res['stack3_cand0_n'] = int(len(s3_0))
    res['stack3_cand1_boom'] = float(s3_1['boom_outcome'].mean()) if len(s3_1) else None
    res['stack3_cand0_boom'] = float(s3_0['boom_outcome'].mean()) if len(s3_0) else None
    res['stack3_marginal_lift_pp'] = (
        (res['stack3_cand1_boom'] - res['stack3_cand0_boom']) * 100
        if res['stack3_cand1_boom'] is not None and res['stack3_cand0_boom'] is not None
        else None
    )

    # Independence — Pearson correlation with each v1 flag
    corrs = {}
    for f in v1_flags:
        if sub[cand].std() > 0 and sub[f].std() > 0:
            corrs[f] = float(sub[cand].corr(sub[f]))
        else:
            corrs[f] = None
    res['corr_with_v1_flags'] = corrs
    res['max_abs_corr_v1'] = (max(abs(v) for v in corrs.values() if v is not None)
                              if any(v is not None for v in corrs.values()) else None)

    # Year-by-year stability
    yby = {}
    for yr in sorted(sub['year'].unique()):
        ys = sub[sub['year'] == yr]
        y1 = ys[ys[cand] == 1]
        y0 = ys[ys[cand] == 0]
        if len(y1) < 30 or len(y0) < 30:
            yby[int(yr)] = {'skipped': True, 'n1': len(y1), 'n0': len(y0)}
            continue
        yby[int(yr)] = {
            'n_flag1': int(len(y1)), 'n_flag0': int(len(y0)),
            'boom_rate_flag1': float(y1['boom_outcome'].mean()),
            'boom_rate_flag0': float(y0['boom_outcome'].mean()),
            'edge_pp': float((y1['boom_outcome'].mean() - y0['boom_outcome'].mean()) * 100),
        }
    res['year_by_year'] = yby
    pos_years = sum(1 for y, info in yby.items()
                    if not info.get('skipped') and info['edge_pp'] > 0)
    res['n_years_positive'] = pos_years
    res['n_years_evaluated'] = sum(1 for v in yby.values() if not v.get('skipped'))
    return res


# ---------------------------------------------------------------------------
# Step 7 — Main + report
# ---------------------------------------------------------------------------
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print('=== boom_stack v2 component search ===')

    print('Step 1: load per-start panel with dates...')
    starts = load_per_start_with_dates()
    print(f'  per-start rows: {len(starts)}')

    pitch_feats = build_per_start_pitch_features()
    print(f'  pitch-feature rows: {len(pitch_feats)}')

    print('Step 3: build v1 per-start panel (replicate Mode B)...')
    panel = build_v1_per_start(starts)
    print(f'  v1 panel rows: {len(panel)}')

    print('Step 4: load park factors...')
    park = pd.read_csv(CACHE / 'park_factors_2018_2026.csv')
    print(f'  park rows: {len(park)}')

    print('Step 5: add candidate features...')
    panel = add_candidates(panel, pitch_feats, park)

    print('Step 6: filter to streamer pool...')
    streamer = streamer_subset(panel)
    print(f'  streamer pool n: {len(streamer)}')
    print(f'  stack=3 cohort n: {int((streamer["boom_stack_v1"] == 3).sum())}')

    print('  candidate flag rates (streamer pool):')
    candidates = ['cand_velo_spike', 'cand_csw_spike', 'cand_mix_change',
                  'cand_park_friendly', 'cand_high_k_pitcher']
    for c in candidates:
        print(f'    {c}: {streamer[c].mean():.3%}  (non-null: {streamer[c].notna().sum()})')

    v1_flags = ['flag_skill_spike', 'flag_recform_hot', 'flag_opp_soft']

    print('\nStep 7: per-candidate analysis...')
    results = []
    for c in candidates:
        print(f'\n--- {c} ---')
        r = analyze_candidate(streamer, c, v1_flags)
        results.append(r)
        print(f'  flag rate: {r["flag_rate"]:.3%}  (n1={r["n_flag1"]}, n0={r["n_flag0"]})')
        if r['boom_rate_flag1'] is not None:
            edge_pp = (r['boom_rate_flag1'] - r['boom_rate_flag0']) * 100
            print(f'  boom rate: cand=1 {r["boom_rate_flag1"]:.3%}  '
                  f'cand=0 {r["boom_rate_flag0"]:.3%}  edge={edge_pp:+.2f}pp')
        if r['p_value'] is not None:
            print(f'  chi2 p={r["p_value"]:.4g}')
        print(f'  stack=3 cohort n={r["stack3_n"]}  baseline boom={r["stack3_baseline_boom"]:.3%}')
        if r['stack3_marginal_lift_pp'] is not None:
            print(f'  stack=3 cand=1 boom={r["stack3_cand1_boom"]:.3%} (n={r["stack3_cand1_n"]})  '
                  f'cand=0 boom={r["stack3_cand0_boom"]:.3%} (n={r["stack3_cand0_n"]})  '
                  f'marginal={r["stack3_marginal_lift_pp"]:+.2f}pp')
        print(f'  max |corr| with v1 flags: {r["max_abs_corr_v1"]:.3f}'
              if r['max_abs_corr_v1'] is not None else '  corr: N/A')
        print(f'  year-by-year positive: {r["n_years_positive"]}/{r["n_years_evaluated"]}')

    # Winner selection
    print('\n=== WINNER SELECTION ===')
    print('Criteria: stack=3 marginal lift >= +3 pp, max corr |v1| < 0.4, '
          'positive year-by-year in >= 4 years')
    winners = []
    for r in results:
        if r['stack3_marginal_lift_pp'] is None or r['max_abs_corr_v1'] is None:
            continue
        if (r['stack3_marginal_lift_pp'] >= 3.0
            and r['max_abs_corr_v1'] < 0.4
            and r['n_years_positive'] >= 4):
            winners.append(r)
            print(f'  CANDIDATE WINNER: {r["candidate"]}')
            print(f'    stack=3 lift: {r["stack3_marginal_lift_pp"]:+.2f}pp')
            print(f'    max |corr v1|: {r["max_abs_corr_v1"]:.3f}')
            print(f'    positive years: {r["n_years_positive"]}/{r["n_years_evaluated"]}')

    if not winners:
        print('  NO WINNER — v1 appears already saturated at stack=3 boom rate.')
    elif len(winners) == 1:
        print(f'\n  Sole winner: {winners[0]["candidate"]}')
    else:
        winners.sort(key=lambda r: (-r['n_years_positive'], -r['stack3_marginal_lift_pp']))
        print(f'\n  Multi-winner — selecting most stable: {winners[0]["candidate"]}')

    # Persist
    out_json = OUT_DIR / 'boom_stack_v2_search_results.json'
    payload = {
        'streamer_pool_n': int(len(streamer)),
        'stack3_cohort_n': int((streamer['boom_stack_v1'] == 3).sum()),
        'candidates': results,
        'winners': [w['candidate'] for w in winners],
    }
    with open(out_json, 'w') as fh:
        json.dump(payload, fh, indent=2, default=float)
    print(f'\nWrote {out_json}')
    # Save streamer panel for re-use in report builder
    cols = ['pitcher', 'year', 'game_pk', 'game_date', 'fp', 'boom_outcome',
            'boom_stack_v1', 'flag_skill_spike', 'flag_recform_hot', 'flag_opp_soft',
            *candidates]
    streamer[cols].to_csv(OUT_DIR / 'boom_stack_v2_streamer_panel.csv', index=False)
    print('Wrote boom_stack_v2_streamer_panel.csv')


if __name__ == '__main__':
    main()

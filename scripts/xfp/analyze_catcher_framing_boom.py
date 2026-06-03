"""analyze_catcher_framing_boom.py

Quantify the effect of catcher framing on SP boom rate.

Inputs (already cached):
  - data/research/_boom_stack_per_start_panel_cache.parquet
      per-start panel with boom_stack pre-features and boom_outcome
  - data/research/xfp_cache/sp_per_start_catcher_2018_2025.csv
      per-start catcher of record (fielder_2 modal)
  - data/research/xfp_cache/catcher_framing_2017_2025.csv
      per (catcher, year) framing_runs_per_100

Steps:
  1. Merge boom panel + per-start catcher + season framing.
  2. Per-season quintile of framing_runs_per_100 (Q1=worst .. Q5=best).
  3. Boom rate per quintile (overall + within boom_stack tier).
  4. Within-pitcher fixed-effects test (mandatory): does the SAME pitcher
     boom more with a top-quintile catcher than a bottom-quintile one?
  5. Build 2026 framing leaderboard from statcast_2026.parquet using the
     same shadow-zone formula as build_catcher_framing.py.
  6. Map today's roster SPs -> team primary 2026 catcher -> quintile.
  7. Write report.
"""
from __future__ import annotations
from pathlib import Path
import json
import pandas as pd
import numpy as np

ROOT = Path('c:/Users/Joshua/plv_clone')
RESEARCH = ROOT / 'data' / 'research'
CACHE = RESEARCH / 'xfp_cache'
OUT_DIR = RESEARCH / 'validation_runs'
OUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = OUT_DIR / 'catcher_framing_boom_modifier.md'


# --------------------------------------------------------------------- helpers
def shadow_zone_framing(year: int) -> pd.DataFrame:
    """Replicate build_catcher_framing.py shadow-zone formula for given year.
    Returns per (catcher_mlbam, year) framing_runs / framing_runs_per_100."""
    path = CACHE / f'statcast_{year}.parquet'
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(
        path,
        columns=['fielder_2', 'description', 'plate_x', 'plate_z', 'sz_top', 'sz_bot'],
    )
    df = df[df['description'].isin({'called_strike', 'ball', 'blocked_ball'})].copy()
    if df.empty:
        return pd.DataFrame()
    px = df['plate_x'].abs()
    pz = df['plate_z']
    sz_top = df['sz_top']
    sz_bot = df['sz_bot']
    in_zone = (px <= 0.83) & (pz <= sz_top) & (pz >= sz_bot)
    shadow_x = (px > 0.83) & (px <= 1.0) & (pz <= sz_top + 0.2) & (pz >= sz_bot - 0.2)
    shadow_z_top = (px <= 1.0) & (pz > sz_top) & (pz <= sz_top + 0.2)
    shadow_z_bot = (px <= 1.0) & (pz < sz_bot) & (pz >= sz_bot - 0.2)
    df['shadow'] = (shadow_x | shadow_z_top | shadow_z_bot) & ~in_zone
    df['called_strike'] = (df['description'] == 'called_strike').astype(int)
    sh = df[df['shadow']].copy()
    if sh.empty:
        return pd.DataFrame()
    lg = sh['called_strike'].mean()
    g = sh.groupby('fielder_2').agg(
        shadow_pitches=('shadow', 'size'),
        shadow_called_strikes=('called_strike', 'sum'),
    ).reset_index()
    g = g[g['shadow_pitches'] >= 100].copy()
    g['framing_rate'] = g['shadow_called_strikes'] / g['shadow_pitches']
    g['framing_rate_lg'] = lg
    # 0.13 runs per called strike above mean, per 100 shadow pitches
    g['framing_runs_per_100'] = (g['framing_rate'] - lg) * 0.13 * 100
    g['framing_runs'] = (g['framing_rate'] - lg) * g['shadow_pitches'] * 0.13
    g['year'] = year
    g = g.rename(columns={'fielder_2': 'catcher_mlbam'})
    return g[['catcher_mlbam', 'year', 'shadow_pitches', 'shadow_called_strikes',
              'framing_rate', 'framing_rate_lg', 'framing_runs_per_100', 'framing_runs']]


def assign_quintile_within_year(s: pd.Series) -> pd.Series:
    """Quintile assignment within a single year, robust to ties."""
    return pd.qcut(s.rank(method='first'), 5, labels=[1, 2, 3, 4, 5]).astype(int)


def lookup_catcher_names(ids: list[int]) -> dict[int, str]:
    try:
        from pybaseball import playerid_reverse_lookup
    except Exception:
        return {i: str(i) for i in ids}
    if not ids:
        return {}
    df = playerid_reverse_lookup(ids, key_type='mlbam')
    out = {}
    for _, row in df.iterrows():
        out[int(row['key_mlbam'])] = f"{row['name_first'].title()} {row['name_last'].title()}"
    for i in ids:
        out.setdefault(int(i), str(i))
    return out


# --------------------------------------------------------------------- main
def main() -> None:
    print('[1/7] Loading boom-stack panel and catcher attributions...')
    boom = pd.read_parquet(RESEARCH / '_boom_stack_per_start_panel_cache.parquet')
    catchers = pd.read_csv(CACHE / 'sp_per_start_catcher_2018_2025.csv')
    fr = pd.read_csv(CACHE / 'catcher_framing_2017_2025.csv')

    # Restrict framing rows to meaningful sample for season-level rate
    fr_q = fr[fr['shadow_pitches'] >= 300].copy()  # ~half-season threshold
    fr_q['framing_quintile'] = (
        fr_q.groupby('year')['framing_runs_per_100']
        .transform(lambda s: assign_quintile_within_year(s))
    )

    print('[2/7] Joining boom panel <- catcher <- framing...')
    # Normalize game_date types
    boom['game_date'] = pd.to_datetime(boom['game_date']).dt.strftime('%Y-%m-%d')
    catchers['game_date'] = pd.to_datetime(catchers['game_date']).dt.strftime('%Y-%m-%d')
    panel = boom.merge(catchers, on=['pitcher', 'game_pk', 'game_date', 'year'], how='left')
    panel = panel.merge(
        fr_q[['catcher_mlbam', 'year', 'framing_runs_per_100', 'framing_quintile']],
        on=['catcher_mlbam', 'year'], how='left',
    )

    n_total = len(panel)
    n_match = panel['framing_quintile'].notna().sum()
    print(f"   matched {n_match}/{n_total} starts ({100*n_match/n_total:.1f}%)")
    panel_m = panel.dropna(subset=['framing_quintile']).copy()
    panel_m['framing_quintile'] = panel_m['framing_quintile'].astype(int)

    print('[3/7] Boom rate per framing quintile...')
    by_q = panel_m.groupby('framing_quintile').agg(
        n_starts=('boom_outcome', 'size'),
        boom_rate=('boom_outcome', 'mean'),
        median_fp=('fp', 'median'),
        mean_fp=('fp', 'mean'),
        p10_fp=('fp', lambda s: s.quantile(0.10)),
        p90_fp=('fp', lambda s: s.quantile(0.90)),
    ).reset_index()
    print(by_q.to_string(index=False))

    # Marginal effect within boom_stack tier
    print('\n[4/7] Boom rate per (boom_stack, framing_quintile)...')
    by_qb = panel_m.groupby(['boom_stack', 'framing_quintile']).agg(
        n=('boom_outcome', 'size'),
        boom_rate=('boom_outcome', 'mean'),
    ).reset_index()
    pivot = by_qb.pivot(index='boom_stack', columns='framing_quintile', values='boom_rate')
    counts = by_qb.pivot(index='boom_stack', columns='framing_quintile', values='n')
    print('boom_rate pivot:'); print(pivot.round(3).to_string())
    print('counts pivot:'); print(counts.to_string())

    # Year-by-year stability — Q5 vs Q1 boom-rate gap
    print('\n[5a/7] Year-by-year Q5-vs-Q1 boom-rate gap...')
    yearly = []
    for yr, sub in panel_m.groupby('year'):
        q1 = sub[sub['framing_quintile'] == 1]['boom_outcome'].mean()
        q5 = sub[sub['framing_quintile'] == 5]['boom_outcome'].mean()
        n1 = (sub['framing_quintile'] == 1).sum()
        n5 = (sub['framing_quintile'] == 5).sum()
        yearly.append({'year': int(yr), 'q1_n': n1, 'q1_boom': q1, 'q5_n': n5, 'q5_boom': q5,
                       'gap_q5_minus_q1': q5 - q1})
    yearly_df = pd.DataFrame(yearly)
    print(yearly_df.to_string(index=False))

    # within-pitcher fixed-effects test
    print('\n[5b/7] Within-pitcher fixed-effects test (THE validity check)...')
    # Approach: per pitcher, compute mean boom rate; subtract from each start.
    # Then regress residual boom on Q5 vs Q1 dummy.
    pit_mean = panel_m.groupby('pitcher')['boom_outcome'].transform('mean')
    panel_m['boom_resid'] = panel_m['boom_outcome'] - pit_mean
    # Need pitchers with starts across multiple quintiles
    pit_q_counts = panel_m.groupby('pitcher')['framing_quintile'].nunique()
    multi_q_pitchers = pit_q_counts[pit_q_counts >= 2].index
    sub = panel_m[panel_m['pitcher'].isin(multi_q_pitchers)].copy()
    print(f"   {len(multi_q_pitchers)} pitchers have starts across >=2 framing quintiles")
    print(f"   {len(sub)} starts in within-pitcher sample")
    wp_by_q = sub.groupby('framing_quintile').agg(
        n=('boom_resid', 'size'),
        boom_resid=('boom_resid', 'mean'),
    ).reset_index()
    print('   Within-pitcher residual boom rate (>=0 means above own mean):')
    print('  ', wp_by_q.to_string(index=False).replace('\n', '\n   '))

    # Stricter: only pitchers with BOTH Q1 and Q5 exposure
    has_q1 = sub.groupby('pitcher')['framing_quintile'].apply(lambda x: 1 in set(x))
    has_q5 = sub.groupby('pitcher')['framing_quintile'].apply(lambda x: 5 in set(x))
    both_pitchers = has_q1[has_q1 & has_q5].index
    print(f"\n   STRICT: {len(both_pitchers)} pitchers with BOTH Q1 and Q5 exposure")
    strict_q1 = sub[(sub['pitcher'].isin(both_pitchers)) & (sub['framing_quintile'] == 1)]
    strict_q5 = sub[(sub['pitcher'].isin(both_pitchers)) & (sub['framing_quintile'] == 5)]
    if len(strict_q1) > 0 and len(strict_q5) > 0:
        # Paired difference: mean within each pitcher then average
        pit_q1 = strict_q1.groupby('pitcher')['boom_outcome'].mean()
        pit_q5 = strict_q5.groupby('pitcher')['boom_outcome'].mean()
        paired = pd.DataFrame({'q1': pit_q1, 'q5': pit_q5}).dropna()
        paired['diff'] = paired['q5'] - paired['q1']
        print(f"   {len(paired)} paired pitchers (both Q1+Q5 with starts)")
        print(f"   mean Q5 boom: {paired['q5'].mean():.4f}")
        print(f"   mean Q1 boom: {paired['q1'].mean():.4f}")
        print(f"   mean within-pitcher gap (Q5-Q1): {paired['diff'].mean():+.4f}")
        # t-test on paired diff
        from scipy import stats
        t, p = stats.ttest_1samp(paired['diff'], 0)
        print(f"   paired t-test t={t:.3f} p={p:.4f}")
        wp_paired = {
            'n_pitchers': int(len(paired)),
            'mean_q5_boom': float(paired['q5'].mean()),
            'mean_q1_boom': float(paired['q1'].mean()),
            'mean_gap_q5_minus_q1': float(paired['diff'].mean()),
            't_stat': float(t),
            'p_value': float(p),
        }
    else:
        wp_paired = {'n_pitchers': 0, 'note': 'insufficient overlap'}

    # 2026 framing leaderboard
    print('\n[6/7] Building 2026 catcher framing from statcast_2026.parquet...')
    fr_2026 = shadow_zone_framing(2026)
    print(f"   2026 catchers >=100 shadow pitches: {len(fr_2026)}")
    fr_2026_q = fr_2026[fr_2026['shadow_pitches'] >= 300].copy()
    if len(fr_2026_q) >= 5:
        fr_2026_q['framing_quintile'] = assign_quintile_within_year(
            fr_2026_q['framing_runs_per_100']
        )
    else:
        fr_2026_q['framing_quintile'] = np.nan
    print(f"   2026 catchers >=300 shadow pitches (quintile sample): {len(fr_2026_q)}")
    fr_2026_q = fr_2026_q.sort_values('framing_runs_per_100', ascending=False)
    top5_ids = fr_2026_q['catcher_mlbam'].head(5).tolist()
    bot5_ids = fr_2026_q['catcher_mlbam'].tail(5).tolist()
    name_map = lookup_catcher_names(top5_ids + bot5_ids)

    print('\n   2026 TOP 5 framers:')
    for _, r in fr_2026_q.head(5).iterrows():
        nm = name_map.get(int(r['catcher_mlbam']), str(int(r['catcher_mlbam'])))
        print(f"   {nm}: +{r['framing_runs_per_100']:.3f} runs/100 (shadow_n={int(r['shadow_pitches'])})")
    print('\n   2026 BOTTOM 5 framers:')
    for _, r in fr_2026_q.tail(5).iterrows():
        nm = name_map.get(int(r['catcher_mlbam']), str(int(r['catcher_mlbam'])))
        print(f"   {nm}: {r['framing_runs_per_100']:+.3f} runs/100 (shadow_n={int(r['shadow_pitches'])})")

    # Today's roster: SP -> primary catcher (2026 modal) -> framing quintile
    print('\n[7/7] Mapping rotation SPs -> primary 2026 catcher -> quintile...')
    # Use the same modal approach as build_sp_per_start_catcher.py but on 2026 cache
    sc26 = pd.read_parquet(
        CACHE / 'statcast_2026.parquet',
        columns=['pitcher', 'fielder_2', 'game_pk'],
    )
    primary26 = (
        sc26.groupby(['pitcher', 'fielder_2']).size().reset_index(name='n')
        .sort_values(['pitcher', 'n'], ascending=[True, False])
        .drop_duplicates('pitcher')
        .rename(columns={'fielder_2': 'primary_catcher_mlbam'})
    )

    # Resolve user's rotation by name
    target_pitchers = [
        'Jose Soriano', 'Freddy Peralta', 'Kyle Bradish', 'Will Warren',
        'Carlos Rodón', 'Framber Valdez', 'Merrill Kelly',
        'Clay Holmes', 'Slade Cecconi',  # streamers
    ]
    # Manual overrides for known-tricky names
    MANUAL_IDS = {
        'Carlos Rodón': 607074,
        'Clay Holmes': 605280,
        'Quinn Mathews': 696133,  # MiLB, may not be in 2026 statcast
    }
    # Pitcher IDs: use a simple statcast-derived map
    pit_ids = dict(MANUAL_IDS)
    try:
        from pybaseball import playerid_lookup
        for nm in target_pitchers:
            if nm in pit_ids:
                continue
            parts = nm.split(' ', 1)
            if len(parts) == 2:
                first, last = parts
                try:
                    res = playerid_lookup(last, first, fuzzy=True)
                    res = res[pd.to_numeric(res['mlb_played_last'], errors='coerce').fillna(0) >= 2024]
                    if not res.empty:
                        pit_ids[nm] = int(res.iloc[0]['key_mlbam'])
                except Exception:
                    pass
    except Exception:
        pass
    print(f"   resolved {len(pit_ids)}/{len(target_pitchers)} pitcher IDs")

    roster_rows = []
    for nm, pid in pit_ids.items():
        row = primary26[primary26['pitcher'] == pid]
        if row.empty:
            roster_rows.append({'sp': nm, 'mlbam': pid, 'catcher': None,
                                'framing_r100': None, 'quintile': None})
            continue
        cid = int(row.iloc[0]['primary_catcher_mlbam'])
        fr_row = fr_2026_q[fr_2026_q['catcher_mlbam'] == cid]
        if fr_row.empty:
            # Fall back to wider table for low-sample
            fr_row = fr_2026[fr_2026['catcher_mlbam'] == cid]
            if fr_row.empty:
                roster_rows.append({'sp': nm, 'mlbam': pid, 'catcher': cid,
                                    'framing_r100': None, 'quintile': None})
                continue
        roster_rows.append({
            'sp': nm, 'mlbam': pid, 'catcher': cid,
            'framing_r100': float(fr_row.iloc[0]['framing_runs_per_100']),
            'quintile': int(fr_row.iloc[0].get('framing_quintile', 0)) if 'framing_quintile' in fr_row.columns and pd.notna(fr_row.iloc[0].get('framing_quintile')) else None,
        })
    catcher_ids_needed = [r['catcher'] for r in roster_rows if r['catcher']]
    catcher_names = lookup_catcher_names(catcher_ids_needed)
    for r in roster_rows:
        r['catcher_name'] = catcher_names.get(r['catcher']) if r['catcher'] else None

    print('   Roster snapshot:')
    for r in roster_rows:
        print(f"   {r['sp']:<22} -> {str(r['catcher_name'] or '?'):<22} "
              f"r/100={r['framing_r100']!s:>8}  Q={r['quintile']}")

    # Persist results for the report writer
    results = {
        'n_total_starts_panel': int(n_total),
        'n_matched': int(n_match),
        'match_rate': float(n_match / n_total),
        'by_quintile': by_q.to_dict('records'),
        'by_quintile_x_boom_stack': by_qb.to_dict('records'),
        'yearly_q5_minus_q1': yearly_df.to_dict('records'),
        'within_pitcher_residual': wp_by_q.to_dict('records'),
        'within_pitcher_paired': wp_paired,
        'framing_2026_top5': [
            {'mlbam': int(r['catcher_mlbam']),
             'name': name_map.get(int(r['catcher_mlbam']), str(int(r['catcher_mlbam']))),
             'r_per_100': float(r['framing_runs_per_100']),
             'shadow_n': int(r['shadow_pitches'])}
            for _, r in fr_2026_q.head(5).iterrows()
        ],
        'framing_2026_bot5': [
            {'mlbam': int(r['catcher_mlbam']),
             'name': name_map.get(int(r['catcher_mlbam']), str(int(r['catcher_mlbam']))),
             'r_per_100': float(r['framing_runs_per_100']),
             'shadow_n': int(r['shadow_pitches'])}
            for _, r in fr_2026_q.tail(5).iterrows()
        ],
        'roster_snapshot': roster_rows,
    }
    json_path = OUT_DIR / 'catcher_framing_boom_modifier_data.json'
    with open(json_path, 'w') as fh:
        json.dump(results, fh, indent=2, default=str)
    print(f"\nWrote results JSON -> {json_path}")
    return results


if __name__ == '__main__':
    main()

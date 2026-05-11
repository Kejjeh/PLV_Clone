"""starts_per_week_analysis.py — how often do SPs actually pitch 2x in a Mon-Sun week?

Answers the question: "Are we over-projecting aces by assuming 2 starts/week?"

For each (pitcher, ISO Mon-Sun week) in 2024 + 2025 statcast:
  Count starts. SP-only proxy: pitcher appeared in inning 1.

Reports:
  - Per-week distribution of starts per SP (0, 1, 2, 3+)
  - Per-SP fraction of weeks with 2+ starts
  - Top 10 SPs by 2-start-week rate
  - Per-SP average starts-per-week (vs theoretical 1.4 if every 5 days)
  - Best estimate of "weekly fp" multiplier per SP

Output:
  data/research/starts_per_week.csv
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
RES = ROOT / 'data' / 'research'

# MLB regular season usually mid-March to late September
SEASON_DATES = {2024: ('2024-03-25', '2024-09-30'),
                2025: ('2025-03-24', '2025-09-29')}


def main():
    RES.mkdir(parents=True, exist_ok=True)
    rows = []
    for year, (start_d, end_d) in SEASON_DATES.items():
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=['game_date', 'game_pk', 'pitcher', 'inning'])
        df['game_date'] = pd.to_datetime(df['game_date'])
        df = df[(df['game_date'] >= pd.Timestamp(start_d))
                & (df['game_date'] <= pd.Timestamp(end_d))]
        # Identify SP starts: pitcher in inning 1 of a game
        sp_starts = df[df['inning'] == 1].groupby(['pitcher', 'game_pk', 'game_date']).size().reset_index(name='_n')
        sp_starts['iso_week'] = sp_starts['game_date'].dt.to_period('W-SUN').apply(lambda r: r.start_time)
        sp_starts['year'] = year
        rows.append(sp_starts)
    if not rows:
        print('no data'); return
    df = pd.concat(rows, ignore_index=True)

    # Per (pitcher, iso_week) start counts
    per_week = df.groupby(['pitcher', 'year', 'iso_week']).size().reset_index(name='starts')

    print(f'Total SP-weeks across 2024-2025: {len(per_week)}')
    print(f'\nDistribution of starts per ISO week (Mon-Sun):')
    dist = per_week['starts'].value_counts().sort_index()
    total = len(per_week)
    for k, v in dist.items():
        print(f'  {k} start(s)/week: {v:>6,} weeks  ({v/total*100:.1f}%)')

    # SPs with min 20 weeks of activity (full-time SP)
    sp_activity = per_week.groupby('pitcher')['iso_week'].count().reset_index(name='active_weeks')
    full_time = sp_activity[sp_activity['active_weeks'] >= 20]['pitcher']
    pw_ft = per_week[per_week['pitcher'].isin(full_time)]
    print(f'\nFull-time SPs (≥20 active weeks in 2024-2025): {len(full_time)}')

    avg_starts = pw_ft.groupby('pitcher')['starts'].mean().reset_index(name='avg_per_active_week')
    two_plus = pw_ft.groupby('pitcher').apply(
        lambda g: (g['starts'] >= 2).mean()).reset_index(name='pct_2plus_weeks')
    avg_starts = avg_starts.merge(two_plus, on='pitcher')

    print(f'\nFull-time SPs — average starts per active week (mean across SPs): '
          f'{avg_starts["avg_per_active_week"].mean():.3f}')
    print(f'Full-time SPs — pct of weeks with 2+ starts (mean): '
          f'{avg_starts["pct_2plus_weeks"].mean()*100:.1f}%')
    print(f'                                              (median): '
          f'{avg_starts["pct_2plus_weeks"].median()*100:.1f}%')

    print('\nTop 15 SPs by 2-start-week rate:')
    # Add names from rp3 if available
    rp = pd.read_csv(ROOT / 'data' / 'outputs' / 'xfp_rp3_projections.csv')[['pitcher', 'player_name']].drop_duplicates('pitcher')
    avg_starts = avg_starts.merge(rp, on='pitcher', how='left')
    top = avg_starts.sort_values('pct_2plus_weeks', ascending=False).head(15)
    for _, r in top.iterrows():
        nm = r.get('player_name') or '(unknown)'
        print(f'  {nm:<28s} {r["pct_2plus_weeks"]*100:>5.1f}% 2+ weeks  '
              f'(avg {r["avg_per_active_week"]:.2f} starts/active week)')

    # League-average multiplier
    print('\n=== Headline finding ===')
    league_avg_per_week = avg_starts['avg_per_active_week'].mean()
    pct_2plus = avg_starts['pct_2plus_weeks'].mean()
    print(f'League-average SP starts per ACTIVE week: {league_avg_per_week:.3f}')
    print(f'League-average pct of weeks with 2+ starts: {pct_2plus*100:.1f}%')
    print(f'A 26-week season × {league_avg_per_week:.2f}/wk ≈ {league_avg_per_week*26:.1f} starts')
    print(f'(For comparison: a full-time SP making 30 starts ÷ 26 active weeks = 1.15/week)')

    avg_starts.to_csv(RES / 'starts_per_week.csv', index=False)
    print(f'\nwrote {RES / "starts_per_week.csv"}')


if __name__ == '__main__':
    main()

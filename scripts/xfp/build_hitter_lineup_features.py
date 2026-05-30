"""
build_hitter_lineup_features.py — derive per (batter, year) lineup-spot
features from the per-game lineup appearance cache.

The structural-leverage signal for hitters (the gmLI analog from RPs): batting
order spot consistency. Empirical foundation from the external-signals research
audit (2026-05-30):

  mean_lineup_spot   YoY r = 0.682  (n=1,118 pairs, 250+ PA cohort)
  top5_share         YoY r = 0.647
  Same-year vs FP/PA r = ±0.55  (stronger than xwoba_per_pa)
  Predictive next-year FP/PA r = ±0.35 — ~80% as predictive as the rate-skill
                                          baseline and ORTHOGONAL.

These are DISPLAY-ONLY context signals; they do NOT feed any of the 4 rated
domains (CONTACT / POWER / DISCIPLINE / SB). Same role as gmLI on the RP side.

Input:  data/research/xfp_cache/hitter_lineup_appearances_<year>.parquet
        Schema: game_pk, batter, lineup_spot (float 1-9), started_game (bool),
                pa_in_game (int), game_date (datetime), year (int).
        One row per (batter, game) — players in starting lineup get spot 1-9,
        late-game subs are excluded (lineup_spot null for non-starters).

Output: data/research/xfp_cache/hitter_lineup_features_2018_2026.csv
        Per (batter, year):
            n_games, mean_lineup_spot, median_lineup_spot, mode_lineup_spot,
            mode_share, top5_share, top3_share, bottom_share,
            lineup_spot_entropy, lineup_role_tier
        Floor: n_games >= 20 (avoids April small-sample noise).

Tier resolution order (LEADOFF > HEART_OF_ORDER > TOP_ORDER > MIDDLE_ORDER >
                       BOTTOM_ORDER > ROTATIONAL) — see docstrings inline.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path

REPO = Path(r'c:\Users\Joshua\plv_clone')
CACHE = REPO / 'data' / 'research' / 'xfp_cache'
OUT_CSV = CACHE / 'hitter_lineup_features_2018_2026.csv'

YEARS = list(range(2018, 2027))
N_GAMES_FLOOR = 20


def _classify_tier(row) -> str:
    """Resolve lineup_role_tier with priority order:
    LEADOFF > HEART_OF_ORDER > TOP_ORDER > MIDDLE_ORDER > BOTTOM_ORDER > ROTATIONAL.
    """
    mean_spot   = row['mean_lineup_spot']
    mode_spot   = row['mode_lineup_spot']
    mode_share  = row['mode_share']
    top3_share  = row['top3_share']
    top5_share  = row['top5_share']
    bottom_share = row['bottom_share']

    # 1. LEADOFF — mean ≤ 1.8 AND mostly at the same spot
    if mean_spot <= 1.8 and mode_share >= 0.5:
        return 'LEADOFF'

    # 2. HEART_OF_ORDER — locked-in at spot 3/4/5 (≥50% of games at one of those spots)
    #    Catches the classic cleanup hitter. Must come before TOP_ORDER (a heart hitter
    #    with secondary 1-2 spot games could otherwise hit the top3 gate).
    if mode_spot in (3, 4, 5) and mode_share >= 0.5:
        return 'HEART_OF_ORDER'

    # 3. TOP_ORDER — ≥70% of games in spots 1-3 (and not LEADOFF; the leadoff
    #    branch above already grabbed pure leadoffs).
    if top3_share >= 0.70:
        return 'TOP_ORDER'

    # 4. MIDDLE_ORDER — ≥75% in spots 1-5 but <70% in 1-3 → mostly hitting 4-5
    if top5_share >= 0.75 and top3_share < 0.70:
        return 'MIDDLE_ORDER'

    # 5. BOTTOM_ORDER — ≥50% of games in spots 7-9
    if bottom_share >= 0.50:
        return 'BOTTOM_ORDER'

    # 6. ROTATIONAL — shuffled across many spots (mode_share < 0.40)
    if mode_share < 0.40:
        return 'ROTATIONAL'

    # Fallback bucket for the gap (mode_share 0.40-0.50 but doesn't hit any
    # heart/top/middle/bottom rule). These tend to be utility bats who get
    # most starts at one spot but with frequent moves; group with MIDDLE_ORDER
    # as the most-fitting structural label, OR ROTATIONAL if the mode is low.
    if top5_share >= 0.55:
        return 'MIDDLE_ORDER'
    return 'ROTATIONAL'


def _entropy_nats(spots: pd.Series) -> float:
    """Shannon entropy over the spot distribution (in nats)."""
    counts = spots.value_counts(normalize=True)
    p = counts.values
    p = p[p > 0]
    return float(-(p * np.log(p)).sum())


def main():
    print('Building hitter lineup features 2018-2026...', flush=True)
    frames = []
    for y in YEARS:
        p = CACHE / f'hitter_lineup_appearances_{y}.parquet'
        if not p.exists():
            print(f'  skip {y} — file missing', flush=True)
            continue
        df = pd.read_parquet(p)
        frames.append(df)
        print(f'  loaded {y}: {len(df):,} appearances', flush=True)

    if not frames:
        print('ERR: no input files', flush=True)
        return

    all_apps = pd.concat(frames, ignore_index=True)
    # Keep only starting-lineup appearances (non-null lineup_spot).
    starts = all_apps[all_apps['lineup_spot'].notna()].copy()
    starts['lineup_spot'] = starts['lineup_spot'].astype(int)

    print(f'\n  total starting-lineup rows: {len(starts):,}', flush=True)

    # Per (batter, year) aggregations
    rows = []
    for (batter, year), grp in starts.groupby(['batter', 'year']):
        spots = grp['lineup_spot']
        n = len(spots)
        if n < N_GAMES_FLOOR:
            continue
        vc = spots.value_counts()
        mode_spot = int(vc.index[0])
        mode_share = float(vc.iloc[0] / n)
        top3 = float((spots <= 3).sum() / n)
        top5 = float((spots <= 5).sum() / n)
        bottom = float((spots >= 7).sum() / n)
        rows.append({
            'batter': int(batter),
            'year': int(year),
            'n_games': int(n),
            'mean_lineup_spot':   round(float(spots.mean()), 3),
            'median_lineup_spot': float(spots.median()),
            'mode_lineup_spot':   mode_spot,
            'mode_share':         round(mode_share, 3),
            'top5_share':         round(top5, 3),
            'top3_share':         round(top3, 3),
            'bottom_share':       round(bottom, 3),
            'lineup_spot_entropy': round(_entropy_nats(spots), 3),
        })

    out = pd.DataFrame(rows)
    out['lineup_role_tier'] = out.apply(_classify_tier, axis=1)

    out = out[[
        'batter', 'year', 'n_games',
        'mean_lineup_spot', 'median_lineup_spot', 'mode_lineup_spot',
        'mode_share', 'top5_share', 'top3_share', 'bottom_share',
        'lineup_spot_entropy', 'lineup_role_tier',
    ]].sort_values(['year', 'batter']).reset_index(drop=True)

    out.to_csv(OUT_CSV, index=False, encoding='utf-8')
    print(f'\n  wrote {OUT_CSV.name}: {len(out):,} (batter, year) rows', flush=True)

    # ── Summary stats ─────────────────────────────────────────────────
    print('\nPer-year row counts:')
    print(out.groupby('year').size().to_string())

    print('\nTier distribution (all years):')
    tier_order = ['LEADOFF', 'TOP_ORDER', 'HEART_OF_ORDER', 'MIDDLE_ORDER',
                  'BOTTOM_ORDER', 'ROTATIONAL']
    tier_counts = out['lineup_role_tier'].value_counts().reindex(tier_order, fill_value=0)
    total = len(out)
    for tier, ct in tier_counts.items():
        print(f'  {tier:<16} {ct:>5}  ({100*ct/total:>4.1f}%)')

    print('\nTier x year crosstab:')
    ctab = pd.crosstab(out['year'], out['lineup_role_tier'])
    ctab = ctab.reindex(columns=tier_order, fill_value=0)
    print(ctab.to_string())


if __name__ == '__main__':
    main()

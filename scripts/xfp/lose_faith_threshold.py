"""lose_faith_threshold.py — at what slump depth does bounce-back rate collapse?

For each target player, walk a grid of hypothetical "season-to-date rate"
levels (from current down to bottom 1% of career). At each rate, compute
the slump precedent (n_comparable historical windows, bounce_pct).

This produces a CURVE: bounce_pct as a function of how deep the slump is.
The "lose-faith threshold" is where bounce_pct first drops below 50%.

Inputs: Bichette, Sal Perez (and any others passed).
Output:
  data/research/lose_faith_curves.csv
  Console table showing each player's:
    - current state
    - bounce_pct at progressively deeper slump levels
    - point where bounce_pct < 50% (the "lose faith" line)
"""
from __future__ import annotations
from pathlib import Path
import sys
import pandas as pd
import numpy as np

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
RES = ROOT / 'data' / 'research'

from scripts.xfp.slump_precedent import hitter_per_game


def slump_precedent_at_rate(history: pd.DataFrame, target_rate: float, N: int,
                              metric_col: str = 'core_fp', denom_col: str = 'pa',
                              next_n: int = 200) -> dict:
    """Compute bounce metrics if current rate were target_rate over N games."""
    if history.empty:
        return {}
    hist = history.sort_values('game_date').reset_index(drop=True).copy()
    hist['roll_metric'] = hist[metric_col].rolling(N, min_periods=N).sum()
    hist['roll_denom'] = hist[denom_col].rolling(N, min_periods=N).sum()
    hist['roll_rate'] = hist['roll_metric'] / hist['roll_denom']
    valid = hist.dropna(subset=['roll_rate'])
    historical = valid[valid['year'] < 2026]
    if historical.empty:
        return {}

    pct = float((historical['roll_rate'] <= target_rate).mean() * 100)
    n_worse = int((historical['roll_rate'] <= target_rate).sum())
    if n_worse < 5:
        return {'target_rate': target_rate, 'pct_rank': pct, 'n_comparable': n_worse,
                'bounce_pct': None, 'median_next_rate': None}

    bad = historical[historical['roll_rate'] <= target_rate]
    bounce = []
    for end_idx in bad.index:
        after = hist.loc[end_idx + 1: end_idx + 200]
        cum_d = 0.0
        rows = []
        for _, gr in after.iterrows():
            rows.append(gr)
            cum_d += float(gr[denom_col])
            if cum_d >= next_n:
                break
        if not rows:
            continue
        sub = pd.DataFrame(rows)
        nd = float(sub[denom_col].sum())
        if nd < 0.5 * next_n:
            continue
        nr = float(sub[metric_col].sum()) / nd
        sl = float(hist.loc[end_idx, 'roll_rate'])
        bounce.append({'next_rate': nr, 'slump_rate': sl, 'delta': nr - sl})
    if not bounce:
        return {'target_rate': target_rate, 'pct_rank': pct, 'n_comparable': n_worse,
                'bounce_pct': None, 'median_next_rate': None}
    br = pd.DataFrame(bounce)
    return {
        'target_rate': round(target_rate, 4),
        'pct_rank': round(pct, 1),
        'n_comparable': n_worse,
        'n_bounce_eval': len(br),
        'bounce_pct': round(float((br['delta'] > 0).mean() * 100), 1),
        'median_next_rate': round(float(br['next_rate'].median()), 4),
        'median_delta': round(float(br['delta'].median()), 4),
    }


def main():
    rh = pd.read_csv(ROOT / 'data' / 'outputs' / 'xfp_rh3_projections.csv')
    targets = [('Bo Bichette', None), ('Salvador Perez', None)]
    target_rows = []
    for name, _ in targets:
        row = rh[rh['player_name'] == name]
        if row.empty:
            print(f'{name}: not in rh3'); continue
        bid = int(row.iloc[0]['batter'])
        hist = hitter_per_game(bid)
        cur = hist[hist['year'] == 2026]
        # ACTUAL 2026-to-date rate (raw, not projection-shrunken)
        if cur['pa'].sum() > 0:
            cur_actual = float(cur['core_fp'].sum() / cur['pa'].sum())
        else:
            cur_actual = float(row.iloc[0]['xfp_rh3_per_pa'])
        target_rows.append((name, bid, cur_actual))

    out_rows = []
    for name, bid, cur_rate in target_rows:
        print(f'\n{"=" * 70}\n{name} — slump severity curve\n{"=" * 70}')
        hist = hitter_per_game(bid)
        if hist.empty:
            print('  no history'); continue
        N = len(hist[hist['year'] == 2026])
        print(f'  Current 2026 games: {N}, current rate: {cur_rate:.4f}')

        # Career baseline = pre-2026 core_fp/PA average (matches slump module's metric).
        # The rh3 prior_fp_per_pa includes R/RBI/SB which slump precedent doesn't
        # have — DO NOT compare to that.
        pre26 = hist[hist['year'] < 2026]
        career_rate = float(pre26['core_fp'].sum() / pre26['pa'].sum()) if pre26['pa'].sum() > 0 else cur_rate
        print(f'  Career CORE_FP rate (pre-2026): {career_rate:.4f}')
        print(f'  Current vs career: {(cur_rate - career_rate) / career_rate * 100:+.1f}%')

        # Walk from career baseline DOWN through current actual rate and beyond
        max_rate = career_rate * 1.0
        min_rate = max(cur_rate * 0.50, 0.05)
        rates = np.linspace(max_rate, min_rate, 14)
        rates = sorted(set([round(r, 4) for r in rates]), reverse=True)
        print(f'\n{"RATE":>7s} {"vs CAR":>8s} {"PCT":>6s} {"N_COMP":>7s} {"BOUNCE%":>9s} {"NEXT":>7s} {"DELTA":>7s}')
        for r in rates:
            metrics = slump_precedent_at_rate(hist, r, N)
            if not metrics:
                continue
            rel = (r - career_rate) / career_rate * 100
            bp = metrics.get('bounce_pct')
            bp_s = f'{bp:.1f}%' if bp is not None else 'n/a'
            nr = metrics.get('median_next_rate')
            nr_s = f'{nr:.3f}' if nr is not None else 'n/a'
            dl = metrics.get('median_delta')
            dl_s = f'{dl:+.3f}' if dl is not None else 'n/a'
            print(f'  {r:>7.4f} {rel:>+7.1f}% {metrics["pct_rank"]:>5.1f}% '
                  f'{metrics["n_comparable"]:>7d} {bp_s:>9s} {nr_s:>7s} {dl_s:>7s}')
            out_rows.append({
                'player': name, 'target_rate': r,
                'pct_below_career': round(rel, 1),
                'pct_rank': metrics['pct_rank'],
                'n_comparable': metrics['n_comparable'],
                'bounce_pct': bp,
                'median_next_rate': nr,
                'median_delta': dl,
            })

        # Find "lose-faith" line
        rows_with_bp = [r for r in out_rows if r['player'] == name and r['bounce_pct'] is not None]
        if rows_with_bp:
            below_50 = [r for r in rows_with_bp if r['bounce_pct'] < 50]
            below_75 = [r for r in rows_with_bp if r['bounce_pct'] < 75]
            print(f'\n  Bounce-back drops below 75% at: rate <= '
                  f'{below_75[0]["target_rate"] if below_75 else "(never in tested range)"}')
            print(f'  Bounce-back drops below 50% at: rate <= '
                  f'{below_50[0]["target_rate"] if below_50 else "(never in tested range)"}')

    if out_rows:
        pd.DataFrame(out_rows).to_csv(RES / 'lose_faith_curves.csv', index=False)
        print(f'\nwrote {RES / "lose_faith_curves.csv"}')


if __name__ == '__main__':
    main()

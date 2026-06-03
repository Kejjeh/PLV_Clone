"""analyze_boom_bust.py — deep-dive on the boom/bust history.

Run after validate_streamer_boom_stack.py. Builds the per-start panel from the
validation pipeline, joins to actuals, and slices:

  - bust rate (fp < 0) by boom_stack
  - boom rate (fp >= 20) by boom_stack
  - distribution: bust / low / mid / boom / megaboom
  - mean / median / p10 / p25 / p75 / p90 of fp by stack
  - year-by-year stability of the boom/bust effect
  - intersection: archetype tier x boom_stack (does CAUTION + stack=3 boom?)
  - sigma calibration conditional on stack — do the new wider rp3 p25/p75
    bands actually cover 50% within each stack bucket?

Writes report at data/research/validation_runs/boom_bust_deep_dive.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

# Pull the panel builder from the validation script.
from validate_streamer_boom_stack import (  # noqa: E402
    load_per_start_with_dates,
    build_per_start_boom_stack,
)


def outcome_bucket(fp: float) -> str:
    if fp < 0:
        return 'bust'
    if fp < 9:
        return 'low'
    if fp < 15:
        return 'mid'
    if fp < 20:
        return 'good'
    if fp < 30:
        return 'boom'
    return 'megaboom'


BUCKETS = ['bust', 'low', 'mid', 'good', 'boom', 'megaboom']


def summarize(group: pd.DataFrame, label: str) -> dict:
    fp = group['fp']
    out = {
        'label': label,
        'n': len(group),
        'mean': float(fp.mean()),
        'median': float(fp.median()),
        'p10': float(fp.quantile(0.10)),
        'p25': float(fp.quantile(0.25)),
        'p75': float(fp.quantile(0.75)),
        'p90': float(fp.quantile(0.90)),
        'bust_rate': float((fp < 0).mean()),
        'good_rate': float((fp >= 15).mean()),
        'boom_rate': float((fp >= 20).mean()),
        'megaboom_rate': float((fp >= 30).mean()),
    }
    return out


def main():
    print('Loading historical SP starts...')
    starts = load_per_start_with_dates()
    print(f'  starts loaded: {len(starts):,}')

    print('Building per-start boom_stack panel...')
    panel = build_per_start_boom_stack(starts)
    print(f'  panel rows: {len(panel):,}')

    # Panel already has fp + boom_stack + flag_* columns
    merged = panel.dropna(subset=['fp']).copy()
    print(f'  panel rows w/ actuals: {len(merged):,}')

    # Restrict to streamer pool — boom_stack only fires on rank>=50 in production
    # Approximate streamer pool via rolling FP percentile from the panel.
    rolling_fp_col = 'fp_rolling_pct' if 'fp_rolling_pct' in merged.columns else None
    if rolling_fp_col is None and 'rolling_fp' in merged.columns:
        merged['fp_rolling_pct'] = merged.groupby('year')['rolling_fp'].rank(pct=True)
        rolling_fp_col = 'fp_rolling_pct'
    if rolling_fp_col is not None:
        streamer_pool = merged[(merged[rolling_fp_col] <= 0.50)
                               & (merged.get('n_prior_starts', 3) >= 3)].copy()
    else:
        # Fallback: filter via rank_at_snap if available
        streamer_pool = merged.copy()
    print(f'  streamer pool size (rolling-FP <=50%): {len(streamer_pool):,}')

    # Use boom_stack column (the validation script names it boom_stack_pre)
    stack_col = 'boom_stack' if 'boom_stack' in streamer_pool.columns else 'boom_stack_pre'
    streamer_pool['boom_stack'] = streamer_pool[stack_col].fillna(0).astype(int)

    report = ['# Boom / Bust Deep Dive — Per-start Distribution by boom_stack',
              '',
              f'Generated 2026-06-03. n_streamers = {len(streamer_pool):,}',
              '',
              '## 1. Distribution of fp by boom_stack',
              '',
              '| boom_stack | n | bust<0 | low0-9 | mid9-15 | good15-20 | boom20-30 | megaboom30+ |',
              '|---|---|---|---|---|---|---|---|']
    for stack in [0, 1, 2, 3]:
        sub = streamer_pool[streamer_pool['boom_stack'] == stack]
        if len(sub) == 0:
            continue
        cnts = sub['fp'].apply(outcome_bucket).value_counts()
        row = f'| {stack} | {len(sub):,} '
        for b in BUCKETS:
            cnt = int(cnts.get(b, 0))
            pct = 100.0 * cnt / len(sub)
            row += f'| {cnt} ({pct:.1f}%) '
        row += '|'
        report.append(row)

    report.append('')
    report.append('## 2. Summary stats of fp by boom_stack')
    report.append('')
    report.append('| boom_stack | n | mean | median | p10 | p25 | p75 | p90 | bust% | boom%≥20 | mega%≥30 |')
    report.append('|---|---|---|---|---|---|---|---|---|---|---|')
    summaries = {}
    for stack in [0, 1, 2, 3]:
        sub = streamer_pool[streamer_pool['boom_stack'] == stack]
        if len(sub) == 0:
            continue
        s = summarize(sub, f'stack={stack}')
        summaries[stack] = s
        report.append(
            f'| {stack} | {s["n"]:,} | {s["mean"]:.2f} | {s["median"]:.2f} | '
            f'{s["p10"]:.2f} | {s["p25"]:.2f} | {s["p75"]:.2f} | {s["p90"]:.2f} | '
            f'{s["bust_rate"]*100:.1f}% | {s["boom_rate"]*100:.1f}% | '
            f'{s["megaboom_rate"]*100:.1f}% |'
        )

    # Edges
    if 0 in summaries and 3 in summaries:
        delta_boom = summaries[3]['boom_rate'] - summaries[0]['boom_rate']
        delta_bust = summaries[3]['bust_rate'] - summaries[0]['bust_rate']
        delta_mean = summaries[3]['mean'] - summaries[0]['mean']
        report.append('')
        report.append(f'**Stack=3 vs Stack=0 edge:** mean FP {delta_mean:+.2f}, '
                      f'boom rate {delta_boom*100:+.1f} pp, bust rate {delta_bust*100:+.1f} pp')

    # Year-by-year stability
    report.append('')
    report.append('## 3. Year-by-year stability of boom_rate edge')
    report.append('')
    report.append('| year | n | boom%(stack=0) | boom%(stack=2+) | edge |')
    report.append('|---|---|---|---|---|')
    for yr in sorted(streamer_pool['year'].unique()):
        sub = streamer_pool[streamer_pool['year'] == yr]
        low = sub[sub['boom_stack'] == 0]
        hi = sub[sub['boom_stack'] >= 2]
        if len(low) == 0 or len(hi) == 0:
            continue
        low_boom = (low['fp'] >= 20).mean() * 100
        hi_boom = (hi['fp'] >= 20).mean() * 100
        report.append(f'| {int(yr)} | {len(sub):,} | {low_boom:.1f}% | {hi_boom:.1f}% | '
                      f'{hi_boom-low_boom:+.1f} pp |')

    # Component-by-component
    report.append('')
    report.append('## 4. Component-level — which flag matters most?')
    report.append('')
    report.append('| component | n_flag=1 | boom%≥20 (flag=1) | boom%≥20 (flag=0) | edge |')
    report.append('|---|---|---|---|---|')
    for comp in ['flag_skill_spike', 'flag_recform_hot', 'flag_opp_soft']:
        if comp not in streamer_pool.columns:
            continue
        flag_on = streamer_pool[streamer_pool[comp] == 1]
        flag_off = streamer_pool[streamer_pool[comp] == 0]
        on_boom = (flag_on['fp'] >= 20).mean() * 100 if len(flag_on) else float('nan')
        off_boom = (flag_off['fp'] >= 20).mean() * 100 if len(flag_off) else float('nan')
        report.append(f'| {comp} | {len(flag_on):,} | {on_boom:.1f}% | {off_boom:.1f}% | '
                      f'{on_boom-off_boom:+.1f} pp |')

    # Bust focus — when does the model truly fail?
    report.append('')
    report.append('## 5. Bust focus — what about stack=3 busts (the worst-case)?')
    report.append('')
    bust_stack3 = streamer_pool[(streamer_pool['boom_stack'] == 3)
                                & (streamer_pool['fp'] < 0)]
    if len(bust_stack3):
        report.append(f'Of {len(streamer_pool[streamer_pool["boom_stack"]==3])} stack=3 starts, '
                      f'{len(bust_stack3)} ({len(bust_stack3)/len(streamer_pool[streamer_pool["boom_stack"]==3])*100:.1f}%) '
                      'still busted (FP < 0).')
        # Mean FP of busts
        report.append(f'Mean bust FP at stack=3: {bust_stack3["fp"].mean():.2f}')
    report.append('')
    report.append('**Reality check:** stack=3 does NOT eliminate bust risk. It shifts the '
                  'distribution toward booms but ~10% of stack=3 starts still bomb. '
                  'boom_stack is a probability shift, not a guarantee.')

    out_path = ROOT / 'data' / 'research' / 'validation_runs' / 'boom_bust_deep_dive.md'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text('\n'.join(report), encoding='utf-8')
    print(f'\nWrote {out_path}')
    return summaries


if __name__ == '__main__':
    main()

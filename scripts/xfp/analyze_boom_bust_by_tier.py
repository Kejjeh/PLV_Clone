"""analyze_boom_bust_by_tier.py — tier-stratified boom_bust deep-dive.

Hypothesis: stack=3 effect AMPLIFIES with pitcher quality. Established SPs
(aces, SP2/3, backend) with boom_stack=3 might boom HARDER than streamers.

Stratification: each pitcher-year is binned by their season-end FP-per-start
rank within that year:
  - Ace      = rank #1-10   (top ~10%)
  - SP2/3    = rank #11-30
  - Backend  = rank #31-50
  - Streamer = rank #51+

We use season-end FP rank (within year, min 8 starts) rather than rolling
fp_pct because (a) we want the pitcher's TRUE talent tier, not a noisy
in-season proxy that gets reshuffled every week, and (b) the existing
backtest tier file uses pitcher-year tier too. This avoids conflating
"backend SP having a hot stretch and getting binned as Ace" with a real
ace.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

from validate_streamer_boom_stack import (  # noqa: E402
    load_per_start_with_dates,
    build_per_start_boom_stack,
)


CACHE_PANEL = ROOT / 'data' / 'research' / '_boom_stack_per_start_panel_cache.parquet'
OUT_PATH = ROOT / 'data' / 'research' / 'validation_runs' / 'boom_stack_by_tier.md'

TIER_DEF = [
    ('Ace',      1, 10),
    ('SP2_SP3', 11, 30),
    ('Backend', 31, 50),
    ('Streamer', 51, 10_000),
]


def outcome_bucket(fp: float) -> str:
    if fp < 0: return 'bust'
    if fp < 9: return 'low'
    if fp < 15: return 'mid'
    if fp < 20: return 'good'
    if fp < 30: return 'boom'
    return 'megaboom'


BUCKETS = ['bust', 'low', 'mid', 'good', 'boom', 'megaboom']


def assign_tier(panel: pd.DataFrame, min_starts: int = 8) -> pd.DataFrame:
    """Assign each pitcher-year to a tier via within-year FP-per-start rank.

    Min 8 starts in the year to be ranked (filters opener / spot-start noise).
    Pitchers below threshold are dropped (not 'streamer'; they're a 5th category
    of unsignaled spot starters).
    """
    agg = (panel.groupby(['pitcher', 'year'])
                 .agg(starts=('fp', 'size'), fp_mean=('fp', 'mean'))
                 .reset_index())
    agg = agg[agg['starts'] >= min_starts].copy()
    agg['rank_in_year'] = (agg.groupby('year')['fp_mean']
                               .rank(ascending=False, method='first'))
    def tier_of(r):
        for name, lo, hi in TIER_DEF:
            if lo <= r <= hi:
                return name
        return None
    agg['tier'] = agg['rank_in_year'].astype(int).map(tier_of)
    return agg[['pitcher', 'year', 'starts', 'fp_mean', 'rank_in_year', 'tier']]


def summarize(group: pd.DataFrame) -> dict:
    fp = group['fp']
    if len(fp) == 0:
        return {'n': 0}
    return {
        'n': len(group),
        'mean': float(fp.mean()),
        'median': float(fp.median()),
        'p10': float(fp.quantile(0.10)),
        'p25': float(fp.quantile(0.25)),
        'p75': float(fp.quantile(0.75)),
        'p90': float(fp.quantile(0.90)),
        'bust_rate': float((fp < 0).mean()),
        'boom_rate': float((fp >= 20).mean()),
        'megaboom_rate': float((fp >= 30).mean()),
    }


def main():
    if CACHE_PANEL.exists():
        print(f'Loading cached panel from {CACHE_PANEL.name}...')
        panel = pd.read_parquet(CACHE_PANEL)
    else:
        print('Building panel from scratch...')
        starts = load_per_start_with_dates()
        panel = build_per_start_boom_stack(starts)
        panel.to_parquet(CACHE_PANEL)
    print(f'  panel rows: {len(panel):,}')

    panel = panel.dropna(subset=['fp']).copy()
    panel['boom_stack'] = panel['boom_stack'].fillna(0).astype(int)

    # Assign tiers
    tier_map = assign_tier(panel, min_starts=8)
    print(f'  pitcher-years with >=8 starts: {len(tier_map):,}')
    print('  tier breakdown (pitcher-years):')
    print(tier_map['tier'].value_counts().to_string())

    # Join tier back to per-start
    panel = panel.merge(tier_map[['pitcher', 'year', 'tier', 'rank_in_year']],
                        on=['pitcher', 'year'], how='inner')
    print(f'  per-start rows after tier filter (>=8 starts only): {len(panel):,}')
    print('  tier breakdown (starts):')
    print(panel['tier'].value_counts().to_string())

    # Filter: require n_prior_starts >= 3 so boom_stack reflects real signal
    panel = panel[panel['n_prior_starts'] >= 3].copy()
    print(f'  per-start rows after n_prior_starts>=3: {len(panel):,}')

    # ---- BUILD REPORT ----
    lines = [
        '# Boom_Stack by Pitcher Tier — Amplification Hypothesis Test',
        '',
        'Generated 2026-06-03. Cross-tier analysis of stack=3 boom-rate.',
        '',
        '**Setup**',
        '',
        '- Per-start panel: 31,713 SP starts 2018-2025 (PA >= 5, n_prior_starts >= 3)',
        '- Tier assignment: each pitcher-year ranked by season-end FP-per-start',
        '  within year (min 8 starts in year)',
        '- Ace = rank #1-10 / SP2_SP3 = #11-30 / Backend = #31-50 / Streamer = #51+',
        '- boom_stack = sum of flag_skill_spike + flag_recform_hot + flag_opp_soft',
        '  (range 0-3), computed strictly from prior-to-game info',
        '',
        '**Tier sample sizes (per-start, n_prior_starts >= 3):**',
        '',
        '| tier | n_starts | mean_fp | median_fp |',
        '|---|---|---|---|',
    ]
    for tname, _, _ in TIER_DEF:
        sub = panel[panel['tier'] == tname]
        if len(sub) == 0:
            continue
        lines.append(f'| {tname} | {len(sub):,} | {sub["fp"].mean():.2f} | {sub["fp"].median():.2f} |')

    # ----- Per-tier distribution by boom_stack -----
    lines += ['', '## 1. Distribution of FP by boom_stack — per tier', '']
    tier_summaries = {}  # tier -> stack -> summary
    for tname, _, _ in TIER_DEF:
        tsub = panel[panel['tier'] == tname]
        if len(tsub) == 0:
            continue
        lines.append(f'### {tname}  (n = {len(tsub):,} starts)')
        lines.append('')
        lines.append('| stack | n | bust<0 | low0-9 | mid9-15 | good15-20 | boom20-30 | mega30+ |')
        lines.append('|---|---|---|---|---|---|---|---|')
        for stk in [0, 1, 2, 3]:
            ssub = tsub[tsub['boom_stack'] == stk]
            if len(ssub) == 0:
                lines.append(f'| {stk} | 0 | -- | -- | -- | -- | -- | -- |')
                continue
            cnts = ssub['fp'].apply(outcome_bucket).value_counts()
            row = f'| {stk} | {len(ssub):,} '
            for b in BUCKETS:
                cnt = int(cnts.get(b, 0))
                pct = 100.0 * cnt / len(ssub)
                row += f'| {cnt} ({pct:.1f}%) '
            row += '|'
            lines.append(row)
        lines.append('')
        lines.append('**Summary stats by stack:**')
        lines.append('')
        lines.append('| stack | n | mean | median | p10 | p25 | p75 | p90 | bust% | boom%≥20 | mega%≥30 |')
        lines.append('|---|---|---|---|---|---|---|---|---|---|---|')
        tier_summaries[tname] = {}
        for stk in [0, 1, 2, 3]:
            ssub = tsub[tsub['boom_stack'] == stk]
            if len(ssub) == 0:
                continue
            s = summarize(ssub)
            tier_summaries[tname][stk] = s
            lines.append(
                f'| {stk} | {s["n"]:,} | {s["mean"]:.2f} | {s["median"]:.2f} | '
                f'{s["p10"]:.2f} | {s["p25"]:.2f} | {s["p75"]:.2f} | {s["p90"]:.2f} | '
                f'{s["bust_rate"]*100:.1f}% | {s["boom_rate"]*100:.1f}% | '
                f'{s["megaboom_rate"]*100:.1f}% |'
            )
        # Edge
        if 0 in tier_summaries[tname] and 3 in tier_summaries[tname]:
            dm = tier_summaries[tname][3]['mean'] - tier_summaries[tname][0]['mean']
            db = tier_summaries[tname][3]['boom_rate'] - tier_summaries[tname][0]['boom_rate']
            dbst = tier_summaries[tname][3]['bust_rate'] - tier_summaries[tname][0]['bust_rate']
            lines.append('')
            lines.append(f'**Stack=3 vs Stack=0 edge ({tname}):** mean FP {dm:+.2f}, '
                         f'boom rate {db*100:+.1f} pp, bust rate {dbst*100:+.1f} pp')
        lines.append('')

    # ----- AMPLIFICATION HYPOTHESIS -----
    lines += ['## 2. Amplification hypothesis — does stack=3 boom-rate scale with tier?',
              '',
              '| tier | n(stack=3) | stack=0 boom% | stack=3 boom% | edge (pp) | mean_fp(stk=3) |',
              '|---|---|---|---|---|---|']
    for tname, _, _ in TIER_DEF:
        if tname not in tier_summaries:
            continue
        s0 = tier_summaries[tname].get(0)
        s3 = tier_summaries[tname].get(3)
        if s0 is None or s3 is None:
            continue
        edge = (s3['boom_rate'] - s0['boom_rate']) * 100
        lines.append(
            f'| {tname} | {s3["n"]:,} | {s0["boom_rate"]*100:.1f}% | '
            f'{s3["boom_rate"]*100:.1f}% | {edge:+.1f} | {s3["mean"]:.2f} |'
        )
    lines.append('')

    # Verdict on amplification
    tier_order = ['Streamer', 'Backend', 'SP2_SP3', 'Ace']
    boom3 = []
    for t in tier_order:
        if t in tier_summaries and 3 in tier_summaries[t]:
            boom3.append((t, tier_summaries[t][3]['boom_rate'], tier_summaries[t][3]['n']))
    if len(boom3) >= 3:
        rates = [r for _, r, _ in boom3]
        if all(rates[i] <= rates[i+1] for i in range(len(rates)-1)):
            verdict = 'CONFIRMED — stack=3 boom-rate monotonically increases from streamer to ace'
        elif all(rates[i] >= rates[i+1] for i in range(len(rates)-1)):
            verdict = 'INVERTED — streamer tier IS the sweet spot; better SPs gain less'
        else:
            # Compute correlation between tier rank (0=streamer..3=ace) and boom rate
            ranks = list(range(len(rates)))
            corr = np.corrcoef(ranks, rates)[0, 1]
            if corr > 0.5:
                verdict = f'PARTIAL CONFIRM — directional but not monotone (corr tier↑ vs boom%: {corr:+.2f})'
            elif corr < -0.5:
                verdict = f'PARTIAL INVERSION — directional inverse (corr tier↑ vs boom%: {corr:+.2f})'
            else:
                verdict = f'FLAT — no clear amplification or inversion (corr tier↑ vs boom%: {corr:+.2f})'
        lines.append(f'**Verdict on amplification hypothesis: {verdict}**')
        lines.append('')
        for t, r, n in boom3:
            lines.append(f'  - {t} stack=3: {r*100:.1f}% boom rate (n={n})')
    lines.append('')

    # ----- COMPONENT BREAKDOWN PER TIER -----
    lines += ['## 3. Per-tier component breakdown — which flag matters most?',
              '',
              '| tier | component | n(flag=1) | boom% (flag=1) | boom% (flag=0) | edge (pp) |',
              '|---|---|---|---|---|---|']
    for tname, _, _ in TIER_DEF:
        tsub = panel[panel['tier'] == tname]
        if len(tsub) == 0:
            continue
        for comp in ['flag_skill_spike', 'flag_recform_hot', 'flag_opp_soft']:
            on = tsub[tsub[comp] == 1]
            off = tsub[tsub[comp] == 0]
            if len(on) == 0 or len(off) == 0:
                continue
            on_b = (on['fp'] >= 20).mean() * 100
            off_b = (off['fp'] >= 20).mean() * 100
            lines.append(f'| {tname} | {comp} | {len(on):,} | {on_b:.1f}% | '
                         f'{off_b:.1f}% | {on_b-off_b:+.1f} |')
    lines.append('')

    # Dominant component per tier
    lines += ['### Dominant component per tier', '']
    for tname, _, _ in TIER_DEF:
        tsub = panel[panel['tier'] == tname]
        if len(tsub) == 0:
            continue
        edges = {}
        for comp in ['flag_skill_spike', 'flag_recform_hot', 'flag_opp_soft']:
            on = tsub[tsub[comp] == 1]
            off = tsub[tsub[comp] == 0]
            if len(on) < 20 or len(off) < 20:
                continue
            on_b = (on['fp'] >= 20).mean() * 100
            off_b = (off['fp'] >= 20).mean() * 100
            edges[comp] = on_b - off_b
        if edges:
            dominant = max(edges, key=edges.get)
            lines.append(f'- **{tname}**: dominant = `{dominant}` ({edges[dominant]:+.1f} pp); '
                         f'all edges = ' + ', '.join(f'{c}: {e:+.1f}pp' for c, e in edges.items()))
    lines.append('')

    # ----- σ CALIBRATION (p25-p75 cover ~50%?) -----
    lines += ['## 4. Distribution width per tier — IQR (p75-p25) by stack',
              '',
              'Sanity check: do high-stack outcomes have wider distributions (more boom risk/reward)?',
              '',
              '| tier | stack | n | p25 | p75 | IQR | p90 | mean |',
              '|---|---|---|---|---|---|---|---|']
    for tname, _, _ in TIER_DEF:
        if tname not in tier_summaries:
            continue
        for stk in [0, 1, 2, 3]:
            s = tier_summaries[tname].get(stk)
            if s is None:
                continue
            iqr = s['p75'] - s['p25']
            lines.append(f'| {tname} | {stk} | {s["n"]:,} | {s["p25"]:.1f} | '
                         f'{s["p75"]:.1f} | {iqr:.1f} | {s["p90"]:.1f} | {s["mean"]:.2f} |')
    lines.append('')

    # ----- FORECASTING USE CASE -----
    lines += ['## 5. Forecasting application — projecting a stack=2 / stack=3 game',
              '',
              'For any tier × stack combination, use the per-tier table above:',
              '',
              'Example reads:']
    # Ace stack=2
    for tname in ['Ace', 'SP2_SP3', 'Backend']:
        if tname not in tier_summaries:
            continue
        for stk in [2, 3]:
            s = tier_summaries[tname].get(stk)
            if s is None:
                continue
            lines.append(f'- **{tname} stack={stk}** → expect mean {s["mean"]:.1f} FP, '
                         f'p25-p75 [{s["p25"]:.1f}, {s["p75"]:.1f}], '
                         f'boom rate {s["boom_rate"]*100:.1f}%, bust rate {s["bust_rate"]*100:.1f}%')
    lines.append('')

    # ----- CONSTANT DROP RECOMMENDATION -----
    lines += ['## 6. Verdict on STREAMER_RANK_FLOOR=50 constant', '']
    # Get all-tier mean boom edge stack=3 vs stack=0
    if 'Backend' in tier_summaries and 0 in tier_summaries['Backend'] and 3 in tier_summaries['Backend']:
        bk_edge = (tier_summaries['Backend'][3]['boom_rate']
                   - tier_summaries['Backend'][0]['boom_rate']) * 100
    else:
        bk_edge = float('nan')
    if 'SP2_SP3' in tier_summaries and 0 in tier_summaries['SP2_SP3'] and 3 in tier_summaries['SP2_SP3']:
        sp23_edge = (tier_summaries['SP2_SP3'][3]['boom_rate']
                     - tier_summaries['SP2_SP3'][0]['boom_rate']) * 100
    else:
        sp23_edge = float('nan')
    if 'Ace' in tier_summaries and 0 in tier_summaries['Ace'] and 3 in tier_summaries['Ace']:
        ace_edge = (tier_summaries['Ace'][3]['boom_rate']
                    - tier_summaries['Ace'][0]['boom_rate']) * 100
        ace_n3 = tier_summaries['Ace'][3]['n']
    else:
        ace_edge = float('nan')
        ace_n3 = 0
    if 'Streamer' in tier_summaries and 0 in tier_summaries['Streamer'] and 3 in tier_summaries['Streamer']:
        str_edge = (tier_summaries['Streamer'][3]['boom_rate']
                    - tier_summaries['Streamer'][0]['boom_rate']) * 100
    else:
        str_edge = float('nan')

    lines.append(f'- Streamer (rank 51+) stack=3 vs 0 boom edge: **{str_edge:+.1f} pp**')
    lines.append(f'- Backend (rank 31-50) stack=3 vs 0 boom edge: **{bk_edge:+.1f} pp**')
    lines.append(f'- SP2/SP3 (rank 11-30) stack=3 vs 0 boom edge: **{sp23_edge:+.1f} pp**')
    lines.append(f'- Ace (rank 1-10) stack=3 vs 0 boom edge: **{ace_edge:+.1f} pp** (n={ace_n3})')
    lines.append('')

    if not np.isnan(bk_edge) and not np.isnan(sp23_edge):
        non_streamer_edges_meaningful = (bk_edge >= 3.0) or (sp23_edge >= 3.0)
        if non_streamer_edges_meaningful:
            rec = ('**RECOMMENDATION: DROP `STREAMER_RANK_FLOOR=50` and surface boom_stack '
                   'for all tiers.** The signal is non-negligible for Backend and SP2/SP3 '
                   'rosters as well, and the production engine should expose it for any pitcher '
                   'with stack >= 2.')
        else:
            rec = ('**RECOMMENDATION: KEEP `STREAMER_RANK_FLOOR=50`.** The amplification '
                   'is absent in non-streamer tiers; boom_stack remains a streamer-only signal.')
    else:
        rec = '**RECOMMENDATION: insufficient sample to decide; expand panel.**'
    lines.append(rec)
    lines.append('')

    # Save tier_summaries to JSON for reuse
    import json
    json_path = ROOT / 'data' / 'research' / 'validation_runs' / 'boom_stack_by_tier_summaries.json'
    with open(json_path, 'w') as fh:
        json.dump({t: {str(s): v for s, v in sd.items()}
                   for t, sd in tier_summaries.items()}, fh, indent=2, default=float)
    print(f'\nSummaries written to {json_path}')

    OUT_PATH.write_text('\n'.join(lines), encoding='utf-8')
    print(f'Report written to {OUT_PATH}')


if __name__ == '__main__':
    main()

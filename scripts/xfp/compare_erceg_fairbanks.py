"""compare_erceg_fairbanks.py — head-to-head Erceg vs Fairbanks.

Career-level RP comparison + current rprs2 projection + closer role context.
"""
from __future__ import annotations
from pathlib import Path
import sys
import pandas as pd

from plv_clone.projections import PROJECTIONS

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'data' / 'outputs'
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'


def main():
    rel = pd.read_csv(CACHE / 'relievers_multiyr_2018_2026.csv')
    rprs2 = PROJECTIONS.rprs2()

    erceg = rel[rel['name'].str.contains('Erceg', case=False, na=False)]
    fairbanks = rel[rel['name'].str.contains('Fairbanks', case=False, na=False)]

    cols = ['season', 'team_abbr', 'g', 'gs', 'ip', 'sv', 'svo', 'hld',
            'era', 'whip', 'k_pct', 'bb_pct', 'swstr_pct', 'xwoba_per_pa',
            'fp_per_g', 'fp_per_ip']

    print(f'=== Lucas Erceg — career RP line ({len(erceg)} seasons) ===')
    print(erceg[cols].to_string(index=False))

    print(f'\n=== Pete Fairbanks — career RP line ({len(fairbanks)} seasons) ===')
    print(fairbanks[cols].to_string(index=False))

    # Career totals (weighted by IP)
    def career(df):
        if df.empty: return {}
        total_ip = df['ip'].sum()
        total_tbf = df['tbf_api'].sum() if 'tbf_api' in df else df['tbf'].sum()
        total_k = df['k'].sum()
        total_bb = df['bb'].sum()
        total_er = df['er'].sum()
        total_h = df['h'].sum()
        return {
            'IP': total_ip,
            'G': df['g'].sum(),
            'SV': df['sv'].sum(),
            'HLD': df['hld'].sum(),
            'ERA': total_er * 9 / total_ip if total_ip else 0,
            'WHIP': (total_h + total_bb) / total_ip if total_ip else 0,
            'K%': total_k / total_tbf * 100 if total_tbf else 0,
            'BB%': total_bb / total_tbf * 100 if total_tbf else 0,
            'K-BB%': (total_k - total_bb) / total_tbf * 100 if total_tbf else 0,
            'swstr%': (df['swstr'].sum() / df['pitches'].sum() * 100) if df['pitches'].sum() else 0,
            'xwOBA': (df['woba_v_sum'].sum() / df['tbf_api'].sum()) if df['tbf_api'].sum() else 0,
        }

    print(f'\n=== Career totals (weighted) ===')
    e_car = career(erceg)
    f_car = career(fairbanks)
    print(f'{"METRIC":<10s} {"ERCEG":>10s} {"FAIRBANKS":>12s} {"DELTA":>10s}')
    for k in ['IP', 'G', 'SV', 'HLD', 'ERA', 'WHIP', 'K%', 'BB%', 'K-BB%', 'swstr%', 'xwOBA']:
        e = e_car.get(k, 0)
        f = f_car.get(k, 0)
        delta = f - e if isinstance(f, (int, float)) else 0
        if k in ('ERA', 'WHIP', 'BB%', 'xwOBA'):
            arrow = ' ← Fairbanks better' if delta < 0 else ' ← Erceg better'
        else:
            arrow = ' ← Fairbanks better' if delta > 0 else ' ← Erceg better'
        if k in ('K%', 'BB%', 'K-BB%', 'swstr%'):
            print(f'  {k:<10s} {e:>10.1f} {f:>12.1f} {delta:>+10.1f}{arrow}')
        elif k == 'xwOBA':
            print(f'  {k:<10s} {e:>10.3f} {f:>12.3f} {delta:>+10.3f}{arrow}')
        elif k in ('ERA', 'WHIP'):
            print(f'  {k:<10s} {e:>10.2f} {f:>12.2f} {delta:>+10.2f}{arrow}')
        else:
            print(f'  {k:<10s} {e:>10.0f} {f:>12.0f} {delta:>+10.0f}{arrow}')

    print(f'\n=== Current rprs2 projection (RP save/hold role model) ===')
    cols_p = ['name_api', 'role_lag1', 'sv_lag1', 'hld_lag1', 'sv_2026', 'hld_2026',
              'fp_actual_2026', 'xfp_full_year', 'xfp_p25', 'xfp_p75', 'xfp_ros']
    cols_p = [c for c in cols_p if c in rprs2.columns]
    for name in ['Erceg', 'Fairbanks']:
        m = rprs2[rprs2['name_api'].str.contains(name, case=False, na=False)]
        if not m.empty:
            r = m.iloc[0]
            print(f'\n  {name}:')
            for c in cols_p:
                print(f'    {c}: {r[c]}')
        else:
            print(f'  {name}: NOT in rprs2')

    # Last 3 seasons recent form
    print(f'\n=== 2023-2026 only (recent form, what matters most) ===')
    for name, df in [('Erceg', erceg), ('Fairbanks', fairbanks)]:
        sub = df[df['season'] >= 2023]
        if sub.empty: continue
        c = career(sub)
        print(f'  {name}: {sub["ip"].sum():.0f} IP | ERA {c["ERA"]:.2f} | '
              f'K% {c["K%"]:.1f} | BB% {c["BB%"]:.1f} | '
              f'K-BB% {c["K-BB%"]:.1f} | xwOBA {c["xwOBA"]:.3f}')


if __name__ == '__main__':
    main()

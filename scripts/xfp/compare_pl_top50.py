"""compare_pl_top50.py — compare PitcherList Top 50 closer rankings vs model.

Loads my RP RoS projections + the PL Top 50 list, compares ranks, highlights
agreements / disagreements. Also spot-checks the SV+HLD past-week leaders.
"""
from __future__ import annotations
import json
import re
import unicodedata
from pathlib import Path
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
PROJ = pd.read_csv(ROOT / 'data/outputs/xfp_rprs1_projections.csv')

# Map RP RoS rank by name
from plv_clone.utils.name_match import safe_name_key as name_norm  # noqa: E402  OWNER — never re-derive

# Recompute RoS rank (current proj is sorted by xfp_full_year)
PROJ['ros_rank'] = PROJ['xfp_ros'].rank(ascending=False, method='min').astype('Int64')

LOOKUP = {}
for _, r in PROJ.iterrows():
    LOOKUP[name_norm(r['name_api'])] = r

def find(name: str):
    return LOOKUP.get(name_norm(name))


PL_TOP50 = [
    (1,  'Mason Miller',         'SD'),  (2,  'Jhoan Duran',          'PHI'),
    (3,  'Bryan Baker',          'TB'),  (4,  'Louis Varland',        'TOR'),
    (5,  'Aroldis Chapman',      'BOS'), (6,  'Daniel Palencia',      'CHC'),
    (7,  'Cade Smith',           'CLE'), (8,  'Andres Munoz',         'SEA'),
    (9,  'Devin Williams',       'NYM'), (10, 'Jacob Latz',           'TEX'),
    (11, "Riley O'Brien",        'STL'), (12, 'Paul Sewald',          'ARI'),
    (13, 'David Bednar',         'NYY'), (14, 'Raisel Iglesias',      'ATL'),
    (15, 'Jack Perkins',         'ATH'), (16, 'Abner Uribe',          'MIL'),
    (17, 'Tanner Scott',         'LAD'), (18, 'Kenley Jansen',        'DET'),
    (19, 'Seranthony Dominguez', 'CWS'), (20, 'Lucas Erceg',          'KC'),
    (21, 'Caleb Kilian',         'SF'),  (22, 'Gregory Soto',         'PIT'),
    (23, 'Ryan Zeferjahn',       'LAA'), (24, 'Gus Varland',          'WSH'),
    (25, 'Rico Garcia',          'BAL'), (26, 'Trevor Megill',        'MIL'),
    (27, 'Jeff Hoffman',         'TOR'), (28, 'Robert Suarez',        'ATL'),
    (29, 'Graham Ashcraft',      'CIN'), (30, 'Tony Santillan',       'CIN'),
    (31, 'Kyle Finnegan',        'DET'), (32, 'Keaton Winn',          'SF'),
    (33, 'Alex Vesia',           'LAD'), (34, 'Tyler Phillips',       'MIA'),
    (35, 'Bryan King',           'HOU'), (36, 'Sam Bachman',          'LAA'),
    (37, 'Dennis Santana',       'PIT'), (38, 'Anthony Nunez',        'BAL'),
    (39, 'Blake Treinen',        'LAD'), (40, 'Luke Weaver',          'NYM'),
    (41, 'Camilo Doval',         'NYY'), (42, 'Enyel De Los Santos',  'HOU'),
    (43, 'Daniel Lynch IV',      'KC'),  (44, 'Ryan Walker',          'SF'),
    (45, 'Mason Montgomery',     'PIT'), (46, 'Grant Taylor',         'CWS'),
    (47, 'Juan Morillo',         'ARI'), (48, 'Erik Sabrowski',       'CLE'),
    (49, 'Dylan Lee',            'ATL'), (50, 'Kirby Yates',          'LAA'),
]

SV_HLD_LEADERS_LAST_WEEK = [
    ('JoJo Romero',     4),
    ('Lucas Erceg',     3),
    ('Tyler Kinley',    3),
    ("Riley O'Brien",   3),
    ('Ian Seymour',     3),
    ('George Soriano',  3),
]


def main():
    print('═' * 100)
    print('PL TOP 50 CLOSERS — head-to-head vs model RoS rank')
    print('═' * 100)
    rows = []
    for pl_rank, name, team in PL_TOP50:
        rec = find(name)
        if rec is None:
            rows.append({'pl_rank': pl_rank, 'name': name, 'team': team,
                         'model_rank': None, 'ros_fp': None, 'role': None,
                         'sv_now': None, 'sig': None, 'note': 'MISSING'})
        else:
            rows.append({
                'pl_rank': pl_rank, 'name': name, 'team': team,
                'model_rank': int(rec['ros_rank']) if pd.notna(rec['ros_rank']) else None,
                'ros_fp': float(rec['xfp_ros']) if pd.notna(rec['xfp_ros']) else None,
                'role': rec.get('role_lag1') or '—',
                'sv_now': int(rec['sv_2026']) if pd.notna(rec['sv_2026']) else None,
                'sig': (rec.get('signal') or 'hold').upper(),
                'note': '',
            })
    df = pd.DataFrame(rows)
    df['delta'] = df.apply(
        lambda r: (r['pl_rank'] - r['model_rank']) if r['model_rank'] is not None else None, axis=1)

    print(f'{"PL#":<4} {"Player":<22} {"Team":<5} {"My#":<5} {"RoS FP":<8} {"PriorRole":<10} {"SV":<3} {"Sig":<5} {"Δ(PL-Mine)":<10} Note')
    print('-' * 100)
    for _, r in df.iterrows():
        delta_str = (f'{int(r["delta"]):+d}' if pd.notna(r["delta"]) else '—')
        print(f'{r["pl_rank"]:<4} {r["name"]:<22} {r["team"]:<5} '
              f'{(str(r["model_rank"]) if r["model_rank"] is not None else "—"):<5} '
              f'{(f"{r["ros_fp"]:.1f}" if r["ros_fp"] is not None else "—"):<8} '
              f'{(r["role"] or "—"):<10} '
              f'{(str(r["sv_now"]) if r["sv_now"] is not None else "—"):<3} '
              f'{r["sig"] or "—":<5} '
              f'{delta_str:<10} {r["note"]}')

    # Rank correlation
    cov = df.dropna(subset=['model_rank'])
    if len(cov) >= 5:
        from scipy.stats import spearmanr
        rho, _ = spearmanr(cov['pl_rank'], cov['model_rank'])
        print(f'\nSpearman rank correlation (PL vs model, n={len(cov)}): ρ = {rho:.3f}')

    # Biggest agreements + biggest disagreements
    print('\n--- BIGGEST AGREEMENTS (model and PL both bullish) ---')
    cov2 = cov.copy()
    cov2['avg_rank'] = (cov2['pl_rank'] + cov2['model_rank']) / 2
    print(cov2.nsmallest(10, 'avg_rank')[['pl_rank','model_rank','name','team','ros_fp','sig']].to_string(index=False))

    print('\n--- BIGGEST DISAGREEMENTS — PL HIGH, model LOW (model says fade) ---')
    print(cov2.nlargest(10, 'delta')[['pl_rank','model_rank','name','team','ros_fp','sig','role']].to_string(index=False))

    print('\n--- BIGGEST DISAGREEMENTS — model HIGH, PL LOW (model says hidden gem) ---')
    print(cov2.nsmallest(10, 'delta')[['pl_rank','model_rank','name','team','ros_fp','sig','role']].to_string(index=False))

    print('\n═' * 50)
    print('SV+HLD LAST-WEEK LEADERS (PL article)')
    print('═' * 50)
    for name, sv_hld in SV_HLD_LEADERS_LAST_WEEK:
        rec = find(name)
        if rec is None:
            print(f'  {name:<22s} ({sv_hld} SV+HLD): NOT IN MODEL')
        else:
            print(f'  {name:<22s} ({sv_hld} SV+HLD)  '
                  f'role_lag1={rec.get("role_lag1") or "—":<8s}  '
                  f'sv_now={int(rec["sv_2026"]):<2}  '
                  f'RoS={float(rec["xfp_ros"]):.1f} FP  '
                  f'sig={(rec.get("signal") or "hold").upper()}  '
                  f'#{int(rec["ros_rank"])}')


if __name__ == '__main__':
    main()

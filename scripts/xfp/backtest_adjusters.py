"""Backtest the MA0-MA7 adjuster chain by diffing per-player projections
adjusters-on vs adjusters-off on the CURRENT week.

This is NOT a true out-of-sample test (we don't have a closed-and-actualized
Period 8 yet). It measures the MAGNITUDE of each adjuster's effect on the
projection so we can:
  1. Identify which adjusters change projections meaningfully vs noise
  2. Spot any adjuster producing extreme values (sign of miscalibration)
  3. After Period 8 closes (Sun 5/24), compare predicted-vs-actual with
     adjusters on vs off — the true accuracy validation

Output: data/research/backtest_adjusters.csv with per-player rows:
  player, position, fp_off, fp_on, delta_fp, recent_factor, lineup_factor,
  park_factor, platoon_factor, il_factor

And a summary printed to stdout.
"""
from __future__ import annotations
import os
import sys
import json
from pathlib import Path

import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

# Import the build module's pieces. We'll call project_player() twice
# (once with _ADJUSTERS_ON=False, once True) and diff.
import build_matchup_dashboard as build  # noqa: E402

OUT = ROOT / 'data' / 'research' / 'backtest_adjusters.csv'


def _project_all(my_lineup, opp_lineup, schedules_by_team, rh3_map, rp3_map,
                 rp3_by_mlbam, rprs2_map, ts_map, today, week_end):
    """Project all players, return {player_name: projection_dict}."""
    out = {}
    for p in my_lineup + opp_lineup:
        proj = build.project_player(
            p, schedules_by_team, rh3_map, rp3_map, rp3_by_mlbam,
            rprs2_map, ts_map, today, week_end,
        )
        out[p.name] = {
            'team_side': 'my' if p in my_lineup else 'opp',
            'pos': p.position or '?',
            'fp': proj['fp'],
            'units': proj['units'],
            'breakdown': proj['breakdown'],
            'sigma2': proj['sigma2'],
        }
    return out


def main():
    from datetime import date, timedelta
    print('Loading matchup context...')
    mu = build.get_matchup()
    rh3_map, rp3_map, rp3_by_mlbam, rprs2_map, ts_map = build.load_projections()
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    # Fetch schedules (same as build.main does)
    all_teams = set()
    for p in mu['my_lineup'] + mu['opp_lineup']:
        team_id = build.ESPN_TO_MLB_TEAM.get((p.proTeam or '').upper())
        if team_id: all_teams.add(team_id)
    schedules_by_team = {tid: build.get_team_schedule(tid, today.isoformat(),
                                                       week_end.isoformat())
                          for tid in all_teams}

    # ──────── PASS 1: ADJUSTERS OFF ────────
    print('\nPass 1: adjusters OFF (baseline xfp)')
    build._ADJUSTERS_ON = False
    build._HITTER_FORM, build._SP_FORM, build._LINEUP = {}, {}, {}
    build._PARK, build._PSPLIT, build._CALIB = {}, {}, 1.0
    proj_off = _project_all(mu['my_lineup'], mu['opp_lineup'], schedules_by_team,
                             rh3_map, rp3_map, rp3_by_mlbam, rprs2_map, ts_map,
                             today, week_end)

    # ──────── PASS 2: ADJUSTERS ON ────────
    print('Pass 2: adjusters ON (MA1-MA7)')
    build._ADJUSTERS_ON = True
    build._HITTER_FORM, build._SP_FORM = build.load_recent_form_maps()
    build._LINEUP = build.load_lineup_map()
    build._PARK = build.load_park_factors()
    build._PSPLIT = build.load_pitcher_splits()
    build._BAT_SIDE = build.load_bat_side_map()
    build._CALIB = build.load_calibration_scalar()
    print(f'  caches loaded: hitter_form={len(build._HITTER_FORM)} sp_form={len(build._SP_FORM)} '
          f'lineup={len(build._LINEUP)} park={len(build._PARK)} pitcher_splits={len(build._PSPLIT)} '
          f'bat_side={len(build._BAT_SIDE)} calib={build._CALIB:.3f}')
    proj_on = _project_all(mu['my_lineup'], mu['opp_lineup'], schedules_by_team,
                            rh3_map, rp3_map, rp3_by_mlbam, rprs2_map, ts_map,
                            today, week_end)

    # ──────── PASS 3-7: ISOLATE EACH ADJUSTER (one at a time, others off) ────────
    isolated_results = {}
    adjuster_specs = {
        'MA2_recent': lambda: (setattr(build, '_HITTER_FORM', build.load_recent_form_maps()[0]),
                                setattr(build, '_SP_FORM', build.load_recent_form_maps()[1])),
        'MA3_lineup':  lambda: setattr(build, '_LINEUP', build.load_lineup_map()),
        'MA4_park':    lambda: setattr(build, '_PARK', build.load_park_factors()),
        'MA5_platoon': lambda: (setattr(build, '_PSPLIT', build.load_pitcher_splits()),
                                  setattr(build, '_BAT_SIDE', build.load_bat_side_map())),
    }
    for name, loader in adjuster_specs.items():
        # Reset all caches to off-state, then enable only this one
        build._HITTER_FORM, build._SP_FORM, build._LINEUP = {}, {}, {}
        build._PARK, build._PSPLIT, build._BAT_SIDE = {}, {}, {}
        build._CALIB = 1.0
        loader()  # populate only this adjuster's caches
        proj_iso = _project_all(mu['my_lineup'], mu['opp_lineup'], schedules_by_team,
                                  rh3_map, rp3_map, rp3_by_mlbam, rprs2_map, ts_map,
                                  today, week_end)
        my_sum = sum(proj_iso[p.name]['fp'] for p in mu['my_lineup'])
        opp_sum = sum(proj_iso[p.name]['fp'] for p in mu['opp_lineup'])
        isolated_results[name] = (my_sum, opp_sum)
        print(f'  isolated {name}: my={my_sum:.1f}, opp={opp_sum:.1f}')

    # ──────── DIFF + ATTRIBUTION ────────
    rows = []
    for name, off in proj_off.items():
        on = proj_on.get(name, {'fp': 0, 'breakdown': []})
        # Extract first-breakdown adjuster factors as representative (varies per game)
        bd_on = on['breakdown'][0] if on['breakdown'] else {}
        recent = bd_on.get('recent_factor', 1.0)
        lineup = bd_on.get('lineup_factor', 1.0)
        park = bd_on.get('park_factor', 1.0)
        platoon = bd_on.get('platoon_factor', 1.0)
        il = bd_on.get('il_factor', 1.0)
        rows.append({
            'player': name,
            'team_side': off['team_side'],
            'pos': off['pos'],
            'units': off['units'],
            'fp_off': round(off['fp'], 2),
            'fp_on': round(on['fp'], 2),
            'delta_fp': round(on['fp'] - off['fp'], 2),
            'recent_factor': round(recent, 3),
            'lineup_factor': round(lineup, 3),
            'park_factor': round(park, 3),
            'platoon_factor': round(platoon, 3),
            'il_factor': round(il, 3),
        })

    df = pd.DataFrame(rows).sort_values(['team_side', 'fp_off'], ascending=[True, False])

    # ──────── REPORT ────────
    print(f'\n{"="*100}\nADJUSTER IMPACT BACKTEST — Week {mu["period"]} ({today.isoformat()})')
    print('='*100)

    for side in ('my', 'opp'):
        sub = df[df['team_side'] == side]
        sum_off = sub['fp_off'].sum()
        sum_on = sub['fp_on'].sum()
        delta = sum_on - sum_off
        team_label = mu["mine"].team_name if side == 'my' else mu["opp"].team_name
        print(f'\n{team_label} ({side}):')
        print(f'  Total FP off: {sum_off:>7.1f}')
        print(f'  Total FP on:  {sum_on:>7.1f}')
        print(f'  Delta:        {delta:>+7.1f} ({delta/sum_off*100:+.1f}%)')

    # Per-player table
    print('\n--- Per-player delta (top mover from baseline by abs |delta|) ---')
    print(f'{"Player":<25} {"Side":<4} {"Pos":<4} {"FP_off":>7} {"FP_on":>7} {"Δ FP":>7} '
          f'{"recent":>7} {"lineup":>7} {"park":>6} {"platoon":>8} {"IL":>5}')
    movers = df.iloc[(df['delta_fp'].abs()).argsort()[::-1]].head(20)
    for _, r in movers.iterrows():
        print(f'{r["player"]:<25} {r["team_side"]:<4} {r["pos"]:<4} {r["fp_off"]:>7.1f} '
              f'{r["fp_on"]:>7.1f} {r["delta_fp"]:>+7.2f} {r["recent_factor"]:>7.3f} '
              f'{r["lineup_factor"]:>7.3f} {r["park_factor"]:>6.3f} '
              f'{r["platoon_factor"]:>8.3f} {r["il_factor"]:>5.3f}')

    # Per-adjuster summary
    print('\n--- Per-adjuster magnitude summary (across all rostered players with units > 0) ---')
    active = df[df['units'] > 0].copy() if 'units' in df.columns else df
    for col in ['recent_factor', 'lineup_factor', 'park_factor', 'platoon_factor', 'il_factor']:
        vals = active[col].dropna()
        nonneutral = vals[(vals < 0.99) | (vals > 1.01)]
        print(f'  {col:<16}: mean={vals.mean():.3f}  median={vals.median():.3f}  '
              f'min={vals.min():.3f}  max={vals.max():.3f}  '
              f'n_nonneutral={len(nonneutral)}/{len(vals)}')

    # Sigma comparison
    sigma2_off_my = sum(proj_off[p.name]['sigma2'] for p in mu['my_lineup'])
    sigma2_on_my = sum(proj_on[p.name]['sigma2'] for p in mu['my_lineup'])
    sigma2_off_opp = sum(proj_off[p.name]['sigma2'] for p in mu['opp_lineup'])
    sigma2_on_opp = sum(proj_on[p.name]['sigma2'] for p in mu['opp_lineup'])
    print(f'\n--- σ² total ---')
    print(f'  Ligers σ²: off {sigma2_off_my:.0f}, on {sigma2_on_my:.0f} '
          f'({(sigma2_on_my-sigma2_off_my)/sigma2_off_my*100:+.1f}%)')
    print(f'  Opp σ²:    off {sigma2_off_opp:.0f}, on {sigma2_on_opp:.0f} '
          f'({(sigma2_on_opp-sigma2_off_opp)/sigma2_off_opp*100:+.1f}%)')

    # Save CSV
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f'\nFull per-player table → {OUT}')

    # Asymmetry diagnostic
    my_delta_pct = (df[df.team_side=='my']['fp_on'].sum() - df[df.team_side=='my']['fp_off'].sum()) / max(df[df.team_side=='my']['fp_off'].sum(), 1) * 100
    opp_delta_pct = (df[df.team_side=='opp']['fp_on'].sum() - df[df.team_side=='opp']['fp_off'].sum()) / max(df[df.team_side=='opp']['fp_off'].sum(), 1) * 100
    print(f'\n--- ASYMMETRY CHECK ---')
    print(f'  My team delta:    {my_delta_pct:+.1f}%')
    print(f'  Opp team delta:   {opp_delta_pct:+.1f}%')
    asymmetry = my_delta_pct - opp_delta_pct
    print(f'  Asymmetry:        {asymmetry:+.1f}pp (>10pp = adjusters hitting one team harder, investigate)')

    if abs(asymmetry) > 10:
        print(f'  ⚠ Adjusters apply UNEVENLY across teams. Likely cause: my roster has different '
              f'shape (e.g., more cooling players) than opp. Confirm by looking at top movers above.')

    # ──────── ISOLATED-ADJUSTER CONTRIBUTION ────────
    print(f'\n--- ISOLATED ADJUSTER CONTRIBUTION (others off) ---')
    print(f'  Baseline (all off):  my={sum(proj_off[p.name]["fp"] for p in mu["my_lineup"]):.1f}  '
          f'opp={sum(proj_off[p.name]["fp"] for p in mu["opp_lineup"]):.1f}')
    base_my = sum(proj_off[p.name]['fp'] for p in mu['my_lineup'])
    base_opp = sum(proj_off[p.name]['fp'] for p in mu['opp_lineup'])
    for name, (iso_my, iso_opp) in isolated_results.items():
        dmy = iso_my - base_my
        dopp = iso_opp - base_opp
        print(f'  {name:<14}: my={iso_my:.1f} ({dmy:+.1f})  opp={iso_opp:.1f} ({dopp:+.1f})  '
              f'asym={(dmy/base_my - dopp/base_opp)*100:+.1f}pp')


if __name__ == '__main__':
    main()

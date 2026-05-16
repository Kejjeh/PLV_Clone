"""fix_il_flag_from_espn.py — override stale IL flags with live ESPN status.

The xfp_rp3_pipeline uses a pre-computed `is_on_il_at_split` flag from
historical IL transactions that may be stale by days/weeks. For 2026
projections we want ESPN's live injuryStatus.

This script:
  1. Loads xfp_rp3_projections.csv
  2. For each 2026 pitcher in the file, looks up ESPN injuryStatus
  3. If ESPN says ACTIVE (no IL slot, not currently injured), overrides
     is_on_il_at_split → 0 and recomputes the RoS estimate using full
     SP_REMAINING_STARTS instead of the IL-discounted count.
  4. Writes data/outputs/xfp_rp3_projections_il_fixed.csv

Output replaces the projections used by sp_rank/dashboard for the
"current FA pool / current staff" displays.
"""
from __future__ import annotations
from pathlib import Path
import sys
import unicodedata
import re
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'data' / 'outputs'

SP_REMAINING_STARTS = 24
IL_DISCOUNT_STARTS = 4  # what we subtract for IL'd SPs

IL_STATUSES = {'TEN_DAY_DL', 'FIFTEEN_DAY_DL', 'SIXTY_DAY_DL',
                'DAY_TO_DAY', 'INJURY_RESERVE', 'OUT', 'SUSPENSION',
                'PATERNITY'}


def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    parts = re.findall(r'[a-z]+', s)
    return ''.join(sorted(parts))


def main():
    rp3 = pd.read_csv(OUT / 'xfp_rp3_projections.csv')
    print(f'Loaded xfp_rp3_projections.csv: {len(rp3)} rows')

    rp3['nk'] = rp3['player_name'].map(_norm)
    rp3['original_is_il'] = rp3['is_on_il_at_split'].copy()

    # Build ESPN injury map for all 2026 pitchers
    from app import espn_connector as ec
    league = ec._get_league()

    # Build comprehensive injury map across rostered + FA pool
    injury_map = {}  # nk -> (espn_status, espn_lineup_slot, on_team)
    for t in league.teams:
        for p in t.roster:
            injury = getattr(p, 'injuryStatus', 'ACTIVE')
            slot = getattr(p, 'lineupSlot', '?')
            injury_map[_norm(p.name)] = (injury, slot, 'rostered')

    fas = league.free_agents(size=1500)
    for fa in fas:
        nk = _norm(fa.name)
        if nk not in injury_map:
            injury = getattr(fa, 'injuryStatus', 'ACTIVE')
            slot = getattr(fa, 'lineupSlot', '?')
            injury_map[nk] = (injury, slot, 'fa')

    print(f'ESPN status pool: {len(injury_map)} players')

    # Override the flag
    n_was_il_now_active = 0
    n_was_active_now_il = 0
    overrides = []
    for idx, row in rp3.iterrows():
        nk = row['nk']
        espn = injury_map.get(nk)
        if espn is None:
            continue
        injury, slot, _ = espn
        # ESPN says active: on roster, not in IL slot, injury status normal
        is_il_per_espn = (injury in IL_STATUSES) or (slot == 'IL') or (slot == 'INJURY_RESERVE')
        was_il = int(row.get('is_on_il_at_split', 0) or 0) == 1
        if was_il and not is_il_per_espn:
            rp3.at[idx, 'is_on_il_at_split'] = 0
            n_was_il_now_active += 1
            overrides.append((row['player_name'], 'IL→active', injury, slot))
        elif (not was_il) and is_il_per_espn and injury != 'ACTIVE':
            rp3.at[idx, 'is_on_il_at_split'] = 1
            n_was_active_now_il += 1
            overrides.append((row['player_name'], 'active→IL', injury, slot))

    print(f'  Was-IL → now-active per ESPN: {n_was_il_now_active}')
    print(f'  Was-active → now-IL per ESPN: {n_was_active_now_il}')
    print(f'\n  Notable overrides (top 30):')
    for name, kind, injury, slot in overrides[:30]:
        print(f'    {kind:<14s} {name:<24s} ESPN injury={injury}, slot={slot}')

    # Recompute RoS using new IL flag
    def starts_for_row(r):
        return (SP_REMAINING_STARTS - IL_DISCOUNT_STARTS) if r['is_on_il_at_split'] == 1 else SP_REMAINING_STARTS

    per_start_col = 'xfp_rp3_per_start_sched'
    if per_start_col not in rp3.columns:
        per_start_col = 'xfp_rp3_per_start'
    rp3['gs_rem_fixed'] = rp3.apply(starts_for_row, axis=1)
    rp3['ros_fixed'] = rp3[per_start_col] * rp3['gs_rem_fixed']

    # Also update signal if model previously labeled 'il'
    def fix_signal(r):
        sig = r.get('signal', '?')
        if sig == 'il' and r['is_on_il_at_split'] == 0:
            return 'hold'  # was IL, now healthy → reset to hold
        return sig
    rp3['signal_fixed'] = rp3.apply(fix_signal, axis=1)

    out_csv = OUT / 'xfp_rp3_projections_il_fixed.csv'
    rp3.to_csv(out_csv, index=False)
    print(f'\nwrote {out_csv}')

    # Show updated rankings for the previously-IL-flagged players
    flipped = rp3[(rp3['original_is_il'] == 1) & (rp3['is_on_il_at_split'] == 0)].sort_values('ros_fixed', ascending=False)
    print(f'\n  Updated RoS for previously-IL pitchers now flagged active:')
    print(f'  {"PLAYER":<24s} {"per_GS":>7s} {"OLD_RoS":>8s} {"NEW_RoS":>8s} {"GAIN":>6s}')
    for _, r in flipped.head(20).iterrows():
        old_ros = r[per_start_col] * (SP_REMAINING_STARTS - IL_DISCOUNT_STARTS)
        new_ros = r['ros_fixed']
        print(f'  {r["player_name"]:<24s} {r[per_start_col]:>7.2f} {old_ros:>8.1f} {new_ros:>8.1f} {new_ros-old_ros:>+6.1f}')


if __name__ == '__main__':
    main()

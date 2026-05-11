"""playoff_ros.py — per-player projection weighted toward playoff weeks.

BrownU playoff matchups (per ESPN league settings): periods 21-23. Two of
those are 2-week matchups (22 = [24,25], 23 = [26,27] roughly). So
"playoff weeks" = last ~6 weeks of MLB regular season.

For each player on the Ligers roster + top FAs:
  playoff_ros = xfp_per_pa × expected_PA_in_playoff_window
              ≈ xfp_per_pa × (PA_remaining × playoff_share)

where playoff_share = 6 playoff weeks / ~20 RoS weeks ≈ 30% of remaining PA.
SP: per_start × playoff_starts (with 1.19/week × 6 weeks ≈ 7 starts).
RP: per-game × playoff games (RP makes ~3-4 apps/week × 6 weeks ≈ 22).

Plus: rough schedule strength check — if a player's team plays a soft
opposing pitching staff during playoff weeks, value bumps; tough staff
trims. Uses pitcher_sos.csv if available.

Outputs:
  data/outputs/playoff_ros_hitters.csv (batter, name, ros, playoff_ros)
  data/outputs/playoff_ros_pitchers.csv (pitcher, name, ros, playoff_ros)
  data/outputs/playoff_ros.json (dashboard payload)
"""
from __future__ import annotations
from pathlib import Path
import json
import sys
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'data' / 'outputs'

PLAYOFF_WEEKS = 6        # last 6 weeks of MLB regular season
RoS_WEEKS_TOTAL = 20     # approximate weeks remaining at start of season
HEALTHY_SP_STARTS_PER_WEEK = 1.19


def main():
    # Hitters: scale RoS by playoff-share
    rh = pd.read_csv(OUT / 'xfp_rh3_projections.csv')
    rh['playoff_share'] = PLAYOFF_WEEKS / RoS_WEEKS_TOTAL  # 30%
    # Some players' PA is more concentrated in playoffs (e.g., late callups, IL
    # returnees). For most, evenly distributed across RoS.
    rh['playoff_ros'] = (rh['expected_total_fp_remaining'].fillna(0)
                          * rh['playoff_share']).round(1)
    rh_out = rh[['batter', 'player_name', 'team', 'primary_position',
                  'xfp_rh3_per_pa', 'expected_total_fp_remaining',
                  'playoff_ros', 'signal']].copy()
    rh_out = rh_out.sort_values('playoff_ros', ascending=False)
    rh_out.to_csv(OUT / 'playoff_ros_hitters.csv', index=False)
    print(f'wrote playoff_ros_hitters.csv ({len(rh_out)} hitters)')

    # SPs: per_start × ~7 playoff starts
    rp = pd.read_csv(OUT / 'xfp_rp3_projections.csv')
    playoff_starts = round(HEALTHY_SP_STARTS_PER_WEEK * PLAYOFF_WEEKS, 1)  # ~7.14
    rp['playoff_ros'] = (rp['xfp_rp3_per_start'].fillna(0) * playoff_starts).round(1)
    rp_out = rp[['pitcher', 'player_name', 'xfp_rp3_per_start',
                  'playoff_ros', 'signal', 'prior_source']].copy()
    rp_out = rp_out.sort_values('playoff_ros', ascending=False)
    rp_out.to_csv(OUT / 'playoff_ros_pitchers.csv', index=False)
    print(f'wrote playoff_ros_pitchers.csv ({len(rp_out)} pitchers)')

    # RPs
    rprs2_path = OUT / 'xfp_rprs2_projections.csv'
    if rprs2_path.exists():
        rps = pd.read_csv(rprs2_path)
        # xfp_ros covers full RoS; playoff portion = share
        rps['playoff_ros'] = (rps['xfp_ros'].fillna(0)
                              * (PLAYOFF_WEEKS / RoS_WEEKS_TOTAL)).round(1)
        rps_out = rps[['pitcher', 'name_api', 'xfp_ros', 'playoff_ros',
                        'signal']].copy()
        rps_out = rps_out.sort_values('playoff_ros', ascending=False)
        rps_out.to_csv(OUT / 'playoff_ros_relievers.csv', index=False)
        print(f'wrote playoff_ros_relievers.csv ({len(rps_out)} RPs)')

    # JSON payload for dashboard
    payload = {
        'playoff_weeks': PLAYOFF_WEEKS,
        'ros_weeks_total': RoS_WEEKS_TOTAL,
        'playoff_share': round(PLAYOFF_WEEKS / RoS_WEEKS_TOTAL, 3),
        'top_hitter_playoff_picks': rh_out.head(40).to_dict(orient='records'),
        'top_pitcher_playoff_picks': rp_out.head(40).to_dict(orient='records'),
    }
    with open(OUT / 'playoff_ros.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, separators=(',', ':'), default=str)
    print(f'wrote playoff_ros.json')


if __name__ == '__main__':
    main()

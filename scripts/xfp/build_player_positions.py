"""build_player_positions.py — nightly live player position map (MLB API).

Severs the ADR-0009 master_hitter edge: rh3 / rh3_april / xfp_h2_lock used to
take hitter positions from data/outputs/master_hitter_2026.csv, written by the
dormant PLV chain (weekly `plv update`, step 1.98) — so a call-up could sit
positionless for up to 7 days and the ACTIVE layer depended on the DORMANT one
executing. This driver refreshes the same position map that chain used
(plv_clone.data.player_positions.build_position_map — /sports/1/players for
the FULL season universe, fielding GS for ESPN-style eligibility) into

    data/reference/player_positions_{SEASON_YEAR}.json

which the three consumers read via player_positions.load_position_frame().

Registered as a NON-gating refresh_all stage before the H2/RH3 stages: on a
failed pull, build_position_map refuses to overwrite the cache (empty-frame
guard), the consumers read the previous night's file, and positions degrade
by one day instead of the run dying.
"""
from __future__ import annotations

import sys

from plv_clone.data.player_positions import build_position_map
from plv_clone.league_config import SEASON_YEAR
from plv_clone.paths import DATA


def main() -> int:
    cache_dir = DATA / "reference"
    # max_cache_age_days=0 forces a live rebuild every run; the refuse-to-
    # overwrite-with-empty guard inside build_position_map keeps the previous
    # cache when the API pull fails.
    df = build_position_map(SEASON_YEAR, cache_dir=cache_dir, max_cache_age_days=0)
    if df.empty:
        prior = cache_dir / f"player_positions_{SEASON_YEAR}.json"
        if prior.exists():
            print(f"WARN: live position pull failed — consumers keep the "
                  f"existing {prior.name}")
        else:
            print("WARN: live position pull failed and no prior cache exists "
                  "— consumers will fall back to the legacy master_hitter CSV")
        return 0  # fail-soft by construction; the stage is non-gating anyway
    n_pos = int(df["primary_position"].ne("").sum())
    print(f"player_positions_{SEASON_YEAR}.json: {len(df)} players, "
          f"{n_pos} with a primary position")
    return 0


if __name__ == "__main__":
    sys.exit(main())

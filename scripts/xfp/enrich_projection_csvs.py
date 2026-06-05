"""enrich_projection_csvs.py — Phase 3 / Agent 1.

Adds validated prior-season feature columns to the three production projection
CSVs so a downstream blend scorer can join on the existing player IDs without
re-deriving them.

Columns added to ALL THREE (rh3, rp3, rprs2):
  - slope_3yr_prior        (from ratings_master year=2025, OVERALL_slope_3yr;
                            fallback: 0 for <3yr / rookies — explicit zero,
                            not NaN, because the (traj × OVR) feature treats
                            no-prior-evidence as a flat slope.)
  - arche_overall_prior    (OVERALL from year=2025; NaN if absent)
  - traj_career_low_prior  (bool: traj_flag=='CAREER_LOW' from year=2025;
                            False if absent)

Columns added to xfp_rp3 ONLY (SP-specific, computed from statcast_2025):
  - high_k_z_year_prior    (z-score of 2025 season K% within (year=2025, month)
                            cohort; >=3 starts to qualify, else NaN)
  - shadow_velo_pct_prior  (percentile of 2025 FB velo within 2025 SP pop with
                            >=200 pitches; NaN if absent)
  - shadow_bb_pct_prior    (percentile of INVERTED BB% — high pct = good
                            control — within same 2025 SP pop; NaN if absent)

Hard rules embedded:
  - 2020 COVID exclusion: not applicable here (we only read 2025), but call it
    out: any future broadening MUST exclude year=2020.
  - NaN propagation: never silently impute with mean/median.
  - Player ID safety: ratings_master + statcast both carry mlbam IDs, so we
    join on the ID column directly (batter / pitcher). NO name->id dicts.

Re-run safety: atomic write (tmp + os.replace), idempotent.

Wired into refresh_dashboards.py as step 2.95.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
OUT = ROOT / 'data' / 'outputs'
RES = ROOT / 'data' / 'research'

RH3 = OUT / 'xfp_rh3_projections.csv'
RP3 = OUT / 'xfp_rp3_projections.csv'
RPRS2 = OUT / 'xfp_rprs2_projections.csv'

HIT_MASTER = RES / 'hitter_ratings_master.csv'
SP_MASTER = RES / 'sp_ratings_master.csv'
RP_MASTER = RES / 'rp_ratings_master.csv'

STATCAST_2025 = ROOT / 'data' / 'raw' / 'statcast_2025.parquet'

PRIOR_YEAR = 2025
# Hard guard — never use 2020 (COVID) in any rolling computation. Today this
# script only reads PRIOR_YEAR=2025, but if you broaden the window, exclude 2020.
EXCLUDED_YEARS = {2020}


def _load_prior(master_path: Path, id_col: str) -> pd.DataFrame:
    df = pd.read_csv(master_path, usecols=['year', id_col, 'OVERALL',
                                           'OVERALL_slope_3yr', 'traj_flag'])
    df = df[~df['year'].isin(EXCLUDED_YEARS)]
    prior = df[df['year'] == PRIOR_YEAR].copy()
    prior = prior.rename(columns={
        'OVERALL': 'arche_overall_prior',
        'OVERALL_slope_3yr': 'slope_3yr_prior',
        'traj_flag': '_traj_flag_prior',
    })
    prior['traj_career_low_prior'] = (prior['_traj_flag_prior'] == 'CAREER_LOW')
    # fallback: 0 for slope (rookies / <3yr history). NOT NaN — see module
    # docstring: a missing slope is interpreted as "flat trajectory" so the
    # (traj_career_low × OVR) interaction term degrades gracefully.
    prior['slope_3yr_prior'] = prior['slope_3yr_prior'].fillna(0.0)
    return prior[[id_col, 'arche_overall_prior', 'slope_3yr_prior',
                  'traj_career_low_prior']]


def _enrich_cross_type(proj_path: Path, id_col: str, master_path: Path) -> pd.DataFrame:
    proj = pd.read_csv(proj_path)
    prior = _load_prior(master_path, id_col)
    # Drop any pre-existing enrichment cols so re-run is idempotent.
    for c in ['arche_overall_prior', 'slope_3yr_prior', 'traj_career_low_prior']:
        if c in proj.columns:
            proj = proj.drop(columns=[c])
    merged = proj.merge(prior, on=id_col, how='left')
    # For players not in prior-year master, slope -> 0 (rookie), traj -> False,
    # OVR -> NaN (genuinely unknown).
    merged['slope_3yr_prior'] = merged['slope_3yr_prior'].fillna(0.0)
    merged['traj_career_low_prior'] = merged['traj_career_low_prior'].fillna(False).astype(bool)
    return merged


def _compute_sp_statcast_priors() -> pd.DataFrame:
    """Return per-pitcher 2025 stats: high_k_z_year_prior, shadow_velo_pct_prior,
    shadow_bb_pct_prior. Keyed on mlbam `pitcher` ID."""
    import duckdb

    con = duckdb.connect()
    # Per-pitcher per-month K% (SP definition: pitch in inning 1 with outs=0,
    # bases empty — approximated by "started as pitcher of record". Cheap proxy
    # used elsewhere: at_bat_number=1 AND inning=1 indicates SP. Use that.)
    # For K%, we want a per-(pitcher, month) row, then z-score within month
    # cohort across all SPs (>=3 starts).
    q = f"""
    WITH sc AS (
      SELECT pitcher,
             date_trunc('month', CAST(game_date AS DATE)) AS gm,
             game_pk, inning, at_bat_number, events,
             pitch_type, release_speed, description, balls, strikes,
             CASE WHEN events IS NOT NULL AND events != '' THEN 1 ELSE 0 END is_pa_end
      FROM read_parquet('{STATCAST_2025.as_posix()}')
    ),
    starts AS (
      -- SP-start identification: first PA of the game (inning=1, at_bat_number=1)
      SELECT DISTINCT pitcher, game_pk
      FROM sc
      WHERE inning = 1 AND at_bat_number = 1
    ),
    sp_pa AS (
      SELECT sc.pitcher, sc.gm, sc.events, sc.is_pa_end
      FROM sc
      JOIN starts USING (pitcher, game_pk)
    ),
    sp_pitches AS (
      SELECT sc.pitcher, sc.pitch_type, sc.release_speed, sc.description,
             sc.balls, sc.strikes, sc.events, sc.is_pa_end
      FROM sc
      JOIN starts USING (pitcher, game_pk)
    ),
    monthly AS (
      SELECT pitcher, gm,
             1.0*SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) / NULLIF(SUM(is_pa_end),0) AS k_pct_m
      FROM sp_pa
      GROUP BY pitcher, gm
      HAVING SUM(is_pa_end) >= 20  -- ~3 starts of TBF
    ),
    season AS (
      SELECT pitcher,
             COUNT(DISTINCT game_pk) AS gs,
             COUNT(*) AS n_pitches,
             AVG(CASE WHEN pitch_type IN ('FF','SI','FC') THEN release_speed END) AS fb_velo,
             1.0*SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) / NULLIF(SUM(is_pa_end),0) AS k_pct_season,
             1.0*SUM(CASE WHEN events='walk' THEN 1 ELSE 0 END) / NULLIF(SUM(is_pa_end),0) AS bb_pct_season
      FROM sp_pitches
      LEFT JOIN starts USING (pitcher)
      GROUP BY pitcher
    )
    SELECT s.pitcher, s.gs, s.n_pitches, s.fb_velo, s.k_pct_season, s.bb_pct_season,
           AVG(m.k_pct_m) AS k_pct_m_avg
    FROM season s
    LEFT JOIN monthly m USING (pitcher)
    GROUP BY s.pitcher, s.gs, s.n_pitches, s.fb_velo, s.k_pct_season, s.bb_pct_season
    """
    season = con.execute(q).df()

    # high_k_z_year_prior: z-score season K% within the (year, month) cohort.
    # Spec says cohort = (year, month) — for a season aggregate we use the
    # mean of monthly z-scores across the player's active months.
    monthly_q = f"""
    WITH sc AS (
      SELECT pitcher, game_pk, inning, at_bat_number,
             date_trunc('month', CAST(game_date AS DATE)) AS gm, events,
             CASE WHEN events IS NOT NULL AND events != '' THEN 1 ELSE 0 END is_pa_end
      FROM read_parquet('{STATCAST_2025.as_posix()}')
    ),
    starts AS (
      SELECT DISTINCT pitcher, game_pk FROM sc
      WHERE inning = 1 AND at_bat_number = 1
    ),
    sp_pa AS (
      SELECT sc.pitcher, sc.gm, sc.events, sc.is_pa_end, sc.game_pk
      FROM sc JOIN starts USING (pitcher, game_pk)
    )
    SELECT pitcher, gm,
           COUNT(DISTINCT game_pk) AS gs_m,
           1.0*SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) / NULLIF(SUM(is_pa_end),0) AS k_pct_m
    FROM sp_pa
    GROUP BY pitcher, gm
    HAVING SUM(is_pa_end) >= 20
    """
    monthly = con.execute(monthly_q).df()
    # Within-month z across pitchers meeting the threshold.
    monthly['k_pct_m_z'] = monthly.groupby('gm')['k_pct_m'].transform(
        lambda s: (s - s.mean()) / s.std(ddof=0) if s.std(ddof=0) > 0 else np.nan)
    # Season-level: weighted by gs_m, but only for pitchers with >=3 total starts.
    z_season = (monthly.groupby('pitcher')
                .apply(lambda d: np.average(d['k_pct_m_z'].dropna(),
                                            weights=d.loc[d['k_pct_m_z'].notna(), 'gs_m'])
                       if d['k_pct_m_z'].notna().any() else np.nan)
                .rename('high_k_z_year_prior').reset_index())
    gs_total = monthly.groupby('pitcher')['gs_m'].sum().rename('gs_total').reset_index()
    z_season = z_season.merge(gs_total, on='pitcher')
    # 3-start floor
    z_season.loc[z_season['gs_total'] < 3, 'high_k_z_year_prior'] = np.nan

    # Shadow velo / bb percentiles — population = SPs with >=200 pitches in 2025.
    POP_FLOOR = 200
    pop = season[season['n_pitches'] >= POP_FLOOR].copy()
    # FB velo percentile (higher = better)
    velo_vals = pop['fb_velo'].dropna().values
    def velo_pct(v):
        if pd.isna(v):
            return np.nan
        return float((velo_vals < v).mean() * 100)
    season['shadow_velo_pct_prior'] = season['fb_velo'].apply(
        lambda v: velo_pct(v) if pd.notna(v) and v >= 0 else np.nan)
    # BB% percentile, INVERTED so higher = better control
    bb_vals = pop['bb_pct_season'].dropna().values
    def bb_pct_inv(v):
        if pd.isna(v):
            return np.nan
        return float((bb_vals > v).mean() * 100)  # inverted: higher pct = lower BB%
    season['shadow_bb_pct_prior'] = season['bb_pct_season'].apply(bb_pct_inv)

    # Only emit values for pitchers in the population (>=200 pitches).
    season.loc[season['n_pitches'] < POP_FLOOR, 'shadow_velo_pct_prior'] = np.nan
    season.loc[season['n_pitches'] < POP_FLOOR, 'shadow_bb_pct_prior'] = np.nan

    out = season[['pitcher', 'shadow_velo_pct_prior', 'shadow_bb_pct_prior']].merge(
        z_season[['pitcher', 'high_k_z_year_prior']], on='pitcher', how='outer')
    return out


def _atomic_write(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + '.tmp')
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)


def main():
    print('[enrich] reading projections + ratings_master')
    rh3 = _enrich_cross_type(RH3, 'batter', HIT_MASTER)
    rp3 = _enrich_cross_type(RP3, 'pitcher', SP_MASTER)
    rprs2 = _enrich_cross_type(RPRS2, 'pitcher', RP_MASTER)

    print('[enrich] computing SP statcast priors (2025)')
    sp_priors = _compute_sp_statcast_priors()
    for c in ['high_k_z_year_prior', 'shadow_velo_pct_prior', 'shadow_bb_pct_prior']:
        if c in rp3.columns:
            rp3 = rp3.drop(columns=[c])
    rp3 = rp3.merge(sp_priors, on='pitcher', how='left')

    # Report coverage
    def cov(df, c):
        return f'{df[c].notna().mean()*100:.1f}%'
    print(f'  rh3 ({len(rh3)} rows): cols={len(rh3.columns)} '
          f'slope_cov={cov(rh3,"slope_3yr_prior")} '
          f'ovr_cov={cov(rh3,"arche_overall_prior")} '
          f'cl_cov={cov(rh3,"traj_career_low_prior")}')
    print(f'  rp3 ({len(rp3)} rows): cols={len(rp3.columns)} '
          f'slope_cov={cov(rp3,"slope_3yr_prior")} '
          f'ovr_cov={cov(rp3,"arche_overall_prior")} '
          f'kz_cov={cov(rp3,"high_k_z_year_prior")} '
          f'velo_cov={cov(rp3,"shadow_velo_pct_prior")} '
          f'bb_cov={cov(rp3,"shadow_bb_pct_prior")}')
    print(f'  rprs2 ({len(rprs2)} rows): cols={len(rprs2.columns)} '
          f'slope_cov={cov(rprs2,"slope_3yr_prior")} '
          f'ovr_cov={cov(rprs2,"arche_overall_prior")}')

    _atomic_write(rh3, RH3)
    _atomic_write(rp3, RP3)
    _atomic_write(rprs2, RPRS2)
    print('[enrich] OK — atomic writes complete')


if __name__ == '__main__':
    main()

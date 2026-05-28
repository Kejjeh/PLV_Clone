"""
Monte Carlo Bootstrap Analysis: SP Early-Start Signal Thresholds
Validates Signal A (fp_proxy/bf) and Meyer archetype (fp_proxy + whiff_pct)
"""

import duckdb
import numpy as np
import pandas as pd
from itertools import product
import sys
import os

OUTPUT_FILE = r"C:\Users\Joshua\plv_clone\data\research\mc_signal_a_results.txt"
DATA_DIR = r"C:\Users\Joshua\plv_clone\data\research\xfp_cache"
FPP_THRESHOLD = -0.0476  # Good-start threshold (existing calibration)
N_BOOTSTRAP = 10000
SEED = 42

rng = np.random.default_rng(SEED)

def log(msg, f=None):
    print(msg, flush=True)
    if f:
        f.write(msg + "\n")
        f.flush()

def build_per_start_df(years):
    """Query statcast parquets and compute per-start SP metrics."""
    con = duckdb.connect()

    files = [f"'{DATA_DIR}/statcast_{y}.parquet'" for y in years]
    union_clause = " UNION ALL ".join([f"SELECT * FROM read_parquet({f})" for f in files])

    # Identify SPs: use at_bat_number and inning to filter — pitcher must start
    # We use: first appearance in a game = inning 1 (or close to it), at_bat_number ordering
    # Key fields: pitcher, game_pk, game_date, events, description, type
    # BF = count of distinct at_bat_number where pitcher appears first in game
    # K = strikeout events, BB = walk events, H = hit events, HR = home run events
    # swinging_strike for whiff

    query = f"""
    WITH raw AS (
        SELECT
            pitcher,
            player_name,
            game_pk,
            game_date,
            game_year,
            at_bat_number,
            events,
            description,
            inning
        FROM ({union_clause})
        WHERE game_type = 'R'
    ),
    -- Identify starter games: pitcher appears in inning 1
    starter_games AS (
        SELECT DISTINCT pitcher, game_pk
        FROM raw
        WHERE inning = 1
    ),
    -- Filter to starters only, then compute per-game aggregates
    starter_pitches AS (
        SELECT r.*
        FROM raw r
        INNER JOIN starter_games sg ON r.pitcher = sg.pitcher AND r.game_pk = sg.game_pk
    ),
    -- PA-level: one row per pitcher-game-at_bat with the terminal event
    pa_events AS (
        SELECT
            pitcher,
            game_pk,
            at_bat_number,
            MAX(events) AS event
        FROM starter_pitches
        GROUP BY pitcher, game_pk, at_bat_number
    ),
    -- Game-level PA outcomes
    game_pa AS (
        SELECT
            pitcher,
            game_pk,
            COUNT(*) AS bf,
            SUM(CASE WHEN event IN ('strikeout','strikeout_double_play') THEN 1 ELSE 0 END) AS k,
            SUM(CASE WHEN event IN ('walk','intent_walk') THEN 1 ELSE 0 END) AS bb,
            SUM(CASE WHEN event IN ('single','double','triple','home_run') THEN 1 ELSE 0 END) AS h,
            SUM(CASE WHEN event = 'home_run' THEN 1 ELSE 0 END) AS hr
        FROM pa_events
        GROUP BY pitcher, game_pk
    ),
    -- Game-level whiff stats from pitch-level
    game_whiff AS (
        SELECT
            pitcher,
            game_pk,
            SUM(CASE WHEN description IN ('swinging_strike','swinging_strike_blocked','foul_tip') THEN 1 ELSE 0 END) AS swinging_strikes,
            SUM(CASE WHEN description IN ('swinging_strike','swinging_strike_blocked','foul_tip',
                'foul','hit_into_play','hit_into_play_no_out','hit_into_play_score',
                'foul_bunt','missed_bunt') THEN 1 ELSE 0 END) AS swings
        FROM starter_pitches
        GROUP BY pitcher, game_pk
    ),
    -- Game metadata
    game_meta AS (
        SELECT pitcher, game_pk, MIN(game_date) AS game_date, MAX(game_year) AS game_year, MAX(player_name) AS player_name
        FROM starter_pitches
        GROUP BY pitcher, game_pk
    )
    SELECT
        m.pitcher,
        m.player_name,
        m.game_pk,
        m.game_date,
        m.game_year,
        p.bf,
        p.k,
        p.bb,
        p.h,
        p.hr,
        w.swinging_strikes,
        w.swings,
        CAST(p.k - p.bb - p.h - p.hr AS DOUBLE) / p.bf AS fpp_per_bf,
        CASE WHEN w.swings > 0 THEN CAST(w.swinging_strikes AS DOUBLE) / w.swings ELSE NULL END AS whiff_pct
    FROM game_meta m
    JOIN game_pa p ON m.pitcher = p.pitcher AND m.game_pk = p.game_pk
    JOIN game_whiff w ON m.pitcher = w.pitcher AND m.game_pk = w.game_pk
    WHERE p.bf >= 10
    ORDER BY m.pitcher, m.game_year, m.game_date
    """

    print("Querying statcast data...", flush=True)
    df = con.execute(query).df()
    con.close()
    print(f"  Loaded {len(df):,} qualifying starts", flush=True)
    return df


def build_pitcher_seasons(df, early_n):
    """
    For each pitcher-season with >= (early_n + 4) starts,
    compute early metrics (first early_n GS) and RoS metrics (remaining GS).
    Returns DataFrame with one row per pitcher-season.
    """
    records = []
    for (pitcher, year), grp in df.groupby(['pitcher', 'game_year']):
        grp = grp.sort_values('game_date').reset_index(drop=True)
        total_gs = len(grp)
        if total_gs < early_n + 4:
            continue

        early = grp.iloc[:early_n]
        ros = grp.iloc[early_n:]

        # Early metrics
        early_bf = early['bf'].sum()
        early_fpp = (early['k'].sum() - early['bb'].sum() - early['h'].sum() - early['hr'].sum()) / early_bf
        # Whiff: aggregate across early starts
        e_sw = early['swinging_strikes'].sum()
        e_swings = early['swings'].sum()
        early_whiff = e_sw / e_swings if e_swings > 0 else np.nan

        # RoS metrics
        ros_bf = ros['bf'].sum()
        ros_fpp = (ros['k'].sum() - ros['bb'].sum() - ros['h'].sum() - ros['hr'].sum()) / ros_bf

        records.append({
            'pitcher': pitcher,
            'player_name': grp['player_name'].iloc[0],
            'year': year,
            'gs_total': total_gs,
            'early_fpp': early_fpp,
            'early_whiff': early_whiff * 100,  # convert to pct
            'ros_fpp': ros_fpp,
            'ros_success': ros_fpp >= FPP_THRESHOLD,
        })

    return pd.DataFrame(records)


def bootstrap_cell(mask_signal, mask_success, n_boot=N_BOOTSTRAP):
    """
    mask_signal: boolean array, who meets the signal criteria
    mask_success: boolean array, who has RoS success
    Returns: n_signal, precision, baseline_precision, lift, ci_lo, ci_hi, recall
    """
    n_total = len(mask_signal)
    n_signal = mask_signal.sum()
    n_success_total = mask_success.sum()

    if n_signal == 0 or n_total - n_signal == 0:
        return n_signal, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan

    precision = mask_success[mask_signal].mean()
    baseline = mask_success[~mask_signal].mean()
    lift = precision - baseline
    recall = mask_success[mask_signal].sum() / n_success_total if n_success_total > 0 else 0

    # Bootstrap
    idx = np.arange(n_total)
    sig_arr = mask_signal.astype(float)
    suc_arr = mask_success.astype(float)

    lifts = []
    for _ in range(n_boot):
        s = rng.choice(idx, size=n_total, replace=True)
        sig_s = sig_arr[s]
        suc_s = suc_arr[s]
        n_sig = sig_s.sum()
        n_nonsig = (1 - sig_s).sum()
        if n_sig == 0 or n_nonsig == 0:
            lifts.append(lift)
            continue
        prec_b = (sig_s * suc_s).sum() / n_sig
        base_b = ((1 - sig_s) * suc_s).sum() / n_nonsig
        lifts.append(prec_b - base_b)

    lifts = np.array(lifts)
    ci_lo = np.percentile(lifts, 2.5)
    ci_hi = np.percentile(lifts, 97.5)

    return n_signal, precision, baseline, lift, ci_lo, ci_hi, recall


def run_analysis(ps_df, years_label, f, top_results=None):
    """Run full grid search. Returns list of result dicts."""
    windows = [4, 5, 6, 7, 8]
    fpp_thresholds = [-0.02, 0.00, 0.02, 0.04, 0.06]
    whiff_thresholds = [0, 22, 24, 26, 28]

    results = []

    log(f"\n{'='*70}", f)
    log(f"SIGNAL A CALIBRATION — {years_label}", f)
    log(f"{'='*70}", f)
    log(f"(showing cells where lift > 5pp AND n >= 10)", f)
    log("", f)

    for N in windows:
        # Build pitcher-season table for this window
        ps = build_pitcher_seasons(ps_df, N)
        if len(ps) == 0:
            continue

        mask_success = ps['ros_success'].values
        early_fpp = ps['early_fpp'].values
        early_whiff = ps['early_whiff'].values

        log(f"N={N} GS window: {len(ps)} pitcher-seasons", f)

        for T, W in product(fpp_thresholds, whiff_thresholds):
            if W == 0:
                mask_signal = early_fpp >= T
            else:
                mask_signal = (early_fpp >= T) & (early_whiff >= W)

            n_sig, prec, base, lift, ci_lo, ci_hi, recall = bootstrap_cell(
                mask_signal, mask_success
            )

            if np.isnan(lift):
                continue

            row = {
                'N': N, 'T': T, 'W': W,
                'n': int(n_sig),
                'precision': prec,
                'baseline': base,
                'lift': lift,
                'ci_lo': ci_lo,
                'ci_hi': ci_hi,
                'recall': recall,
                'f1': 2 * prec * recall / (prec + recall) if (prec + recall) > 0 else 0,
            }
            results.append(row)

            if lift > 0.05 and n_sig >= 10:
                w_label = f"W={W}" if W > 0 else "W=0 "
                log(
                    f"  N={N}, T={T:+.2f}, {w_label}:  "
                    f"n={n_sig:3d}, precision={prec*100:.1f}%, "
                    f"lift={lift*100:+.1f}pp [CI: {ci_lo*100:+.1f} to {ci_hi*100:+.1f}], "
                    f"recall={recall*100:.1f}%",
                    f
                )

    if not results:
        log("No results.", f)
        return results

    rdf = pd.DataFrame(results)
    passing = rdf[(rdf['lift'] > 0.05) & (rdf['n'] >= 10)]

    log("", f)
    log("OPTIMAL THRESHOLDS:", f)

    if len(passing) > 0:
        best_prec = passing.loc[passing['precision'].idxmax()].to_dict()
        log(
            f"  Best precision: N={int(best_prec['N'])}, T={best_prec['T']:+.2f}, W={int(best_prec['W'])}:  "
            f"precision={best_prec['precision']*100:.1f}%  n={int(best_prec['n'])}  "
            f"lift={best_prec['lift']*100:+.1f}pp  recall={best_prec['recall']*100:.1f}%",
            f
        )

        best_lift = passing.loc[passing['lift'].idxmax()].to_dict()
        log(
            f"  Best lift:      N={int(best_lift['N'])}, T={best_lift['T']:+.2f}, W={int(best_lift['W'])}:  "
            f"lift={best_lift['lift']*100:+.1f}pp [CI: {best_lift['ci_lo']*100:+.1f} to {best_lift['ci_hi']*100:+.1f}]  "
            f"n={int(best_lift['n'])}",
            f
        )

        best_f1 = passing.loc[passing['f1'].idxmax()].to_dict()
        log(
            f"  Best F1:        N={int(best_f1['N'])}, T={best_f1['T']:+.2f}, W={int(best_f1['W'])}:  "
            f"F1={best_f1['f1']:.3f}  precision={best_f1['precision']*100:.1f}%  recall={best_f1['recall']*100:.1f}%  "
            f"n={int(best_f1['n'])}",
            f
        )

        if top_results is not None:
            top_results.extend([
                ('best_prec', best_prec),
                ('best_lift', best_lift),
                ('best_f1', best_f1),
            ])
    else:
        log("  No cells passed (lift > 5pp, n >= 10).", f)

    return results


def main():
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    with open(OUTPUT_FILE, 'w') as f:
        log("MC Bootstrap Analysis: SP Early-Start Signal Thresholds", f)
        log(f"Good-start threshold: fp_proxy/bf >= {FPP_THRESHOLD}", f)
        log(f"Bootstrap iterations: {N_BOOTSTRAP:,}", f)
        log("", f)

        # Load all years
        all_years = [2021, 2022, 2023, 2024, 2025]
        log("Loading per-start data for 2021-2025...", f)
        df_all = build_per_start_df(all_years)

        log(f"Columns: {list(df_all.columns)}", f)
        log(f"Years present: {sorted(df_all['game_year'].unique())}", f)
        log(f"Sample fpp_per_bf stats:", f)
        log(str(df_all['fpp_per_bf'].describe()), f)
        log("", f)

        # Training set: 2021-2024
        train_df = df_all[df_all['game_year'].isin([2021, 2022, 2023, 2024])].copy()
        test_df = df_all[df_all['game_year'] == 2025].copy()

        log(f"Training: {len(train_df):,} starts | Test (2025): {len(test_df):,} starts", f)

        top_results = []
        train_results = run_analysis(train_df, "TRAINING 2021-2024", f, top_results)

        # 2025 holdout
        log("", f)
        log("="*70, f)
        log("2025 HOLDOUT VALIDATION", f)
        log("="*70, f)

        if top_results:
            log("(Using optimal thresholds from training set)", f)
            log("", f)

            # For holdout, evaluate the top thresholds explicitly
            holdout_windows = set()
            for label, row in top_results:
                holdout_windows.add(int(row['N']))

            for N in sorted(holdout_windows):
                ps_test = build_pitcher_seasons(test_df, N)
                if len(ps_test) == 0:
                    log(f"N={N}: insufficient 2025 data", f)
                    continue

                mask_success_t = ps_test['ros_success'].values
                early_fpp_t = ps_test['early_fpp'].values
                early_whiff_t = ps_test['early_whiff'].values

                log(f"N={N} GS window: {len(ps_test)} pitcher-seasons (2025)", f)

                for label, row in top_results:
                    if int(row['N']) != N:
                        continue
                    T, W = row['T'], int(row['W'])

                    if W == 0:
                        mask_signal = early_fpp_t >= T
                    else:
                        mask_signal = (early_fpp_t >= T) & (early_whiff_t >= W)

                    n_sig, prec, base, lift, ci_lo, ci_hi, recall = bootstrap_cell(
                        mask_signal, mask_success_t
                    )

                    w_label = f"W={W}" if W > 0 else "W=0 "
                    if not np.isnan(lift):
                        log(
                            f"  [{label}] N={N}, T={T:+.2f}, {w_label}:  "
                            f"n={n_sig}, precision={prec*100:.1f}%, "
                            f"lift={lift*100:+.1f}pp [CI: {ci_lo*100:+.1f} to {ci_hi*100:+.1f}], "
                            f"recall={recall*100:.1f}%",
                            f
                        )

        # Also run full grid on 2025 for reference
        log("", f)
        log("Full 2025 grid (cells where lift > 5pp, n >= 10):", f)
        run_analysis(test_df, "2025 HOLDOUT (full grid)", f)

        log("", f)
        log(f"Results saved to: {OUTPUT_FILE}", f)

    print(f"\nDone. Full results at: {OUTPUT_FILE}", flush=True)


if __name__ == "__main__":
    main()

"""Full league-wide roster deep audit — v4 (statistical deepening + calibration).

Hitter layers:
  1. Career-form bucket     — rolling-150 xwOBA career percentile
  2. 9-marker sustainability classify()
  3. Slump signals          — bounce_pct, shrunk gap, xwOBACON, anchor_in_CI
  4. Process metrics        — bat speed, whiff%, chase%, Z-contact%, EV90 per window
  5. Slump trajectory       — rolling-30 xwOBA path, K% decomp, pitch-mix (slumpers)
  6. PEAK validator         — process-driven vs outcome-driven (peakers)
  6b. Injury signals        — ESPN DTD/IL status; classify_injury_impact() flags SLUMP_EXPLAINED

Statistical deepening (v3+v4):
  7. MC bounce simulator    — 10k bootstrap sims; recency-weighted (λ=0.20, ~3.5yr half-life)
  8. Bayesian talent        — conjugate normal-normal; recency-weighted prior (λ=0.20)
  9. Historical comp match  — 54k real 2015-2025 snapshots; age-matched (±3yr window)
  10. Peak decay calc       — survival curves by peak type; Wilson score CIs

Pitcher layer:
  11. SP career-form        — rolling 5-start k_rate percentile + velo trend

v4 upgrades (2026-05-25):
  - MC + Bayesian: decay_lambda=0.20 exponential recency weighting on career distributions
  - Historical comps: age_window=3 (age-matched ±3yr); Freeman 384→104 comps (49% bounce)
  - Peak survival: Wilson score CIs on all survival probabilities (±0.2-0.4pp)
  - Injury integration: 18/125 hitters flagged; Altuve SLUMP_EXPLAINED
  - Calibration validated: ECE=0.0197 on 15,778 out-of-sample snapshots (2023-2025); Brier=0.2221

cross_verdict requires: slump_bounce_pct, shrunk_gap, anchor_in_CI, xwOBACON,
AND process_verdict before calling CONSENSUS_DROP. IMPROVING process or
anchor_in_CI always overrides DROP.
"""
from __future__ import annotations

import sys
import unicodedata
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from plv_clone.projections import PROJECTIONS

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))

from plv_clone.utils.name_match import lookup_batter_id_cached       # noqa
from scripts.xfp.hitter_sustainability import classify, _norm         # noqa
from scripts.xfp.process_metrics_batch import batch_process_metrics   # noqa
from scripts.xfp.slump_trajectory_batch import batch_slump_trajectory # noqa
from scripts.xfp.peak_breakout_validator import batch_peak_validator   # noqa
from scripts.xfp.sp_career_form_batch import (                        # noqa
    batch_sp_career_form, build_sp_id_map,
)
from scripts.xfp.mc_bounce_simulator import batch_mc_bounce           # noqa
from scripts.xfp.bayesian_talent_estimator import batch_bayesian_talent  # noqa
from scripts.xfp.historical_comp_matcher import batch_historical_comps   # noqa
from scripts.xfp.peak_decay_calculator import (                          # noqa
    batch_peak_decay, get_league_peak_survival_curves,
)
from app.espn_connector import _get_league              # noqa
from plv_clone.league_state import LeagueState          # noqa
from scripts.xfp.injury_signals import (                               # noqa
    batch_injury_status, classify_injury_impact, enrich_from_roster_df,
)
from plv_clone.league_config import MY_TEAM_NAME

MY_TEAM = MY_TEAM_NAME
TODAY = date.today().isoformat()
CURRENT_MONTH = date.today().month
CACHE = ROOT / "data" / "research" / "xfp_cache"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def resolve(name: str, team: str, pos: str):
    bid = lookup_batter_id_cached(name, team=team, position=pos)
    if bid is not None:
        return bid
    return lookup_batter_id_cached(_strip(name), team=team, position=pos)


def build_career_form_dict() -> dict[int, dict]:
    cf = pd.read_csv(CACHE / "batter_rolling_features.csv")
    out: dict[int, dict] = {}
    for _, r in cf.iterrows():
        p = r.get("career_percentile")
        if pd.isna(p):
            fb = "INSUFFICIENT"
        elif p >= 0.90:
            fb = "PEAK"
        elif p >= 0.80:
            fb = "HIGH"
        elif p >= 0.60:
            fb = "ABOVE_MEDIAN"
        elif p >= 0.40:
            fb = "TYPICAL"
        elif p >= 0.20:
            fb = "BELOW_MEDIAN"
        else:
            fb = "SLUMPING"
        out[int(r["batter"])] = {
            "total_pa": int(r.get("total_career_pa", 0) or 0),
            "current_l150": round(float(r.get("current_l150_xwoba", 0) or 0), 3),
            "career_percentile": round(float(p or 0), 3),
            "career_l150_median": float(r.get("career_l150_median", 0) or 0),
            "form_bucket": fb,
        }
    return out


def batch_slump_diagnostics(batter_ids: list[int]) -> dict[int, dict]:
    """L21d xwOBACON, Bayesian shrinkage, anchor_in_CI, calendar history."""
    import duckdb
    if not batter_ids:
        return {}
    ids_csv = ",".join(str(b) for b in batter_ids)
    con = duckdb.connect()
    parq_26 = (CACHE / "statcast_2026.parquet").as_posix()
    try:
        ev = con.execute(f"""
            SELECT batter, game_date::DATE gd,
                   estimated_woba_using_speedangle xwoba, launch_speed,
                   EXTRACT(MONTH FROM game_date) mo
            FROM read_parquet('{parq_26}')
            WHERE batter IN ({ids_csv})
              AND events IS NOT NULL AND events != ''
              AND estimated_woba_using_speedangle IS NOT NULL
            ORDER BY batter, game_date
        """).df()
    except Exception as e:
        print(f"  [warn] 2026 query failed: {e}")
        return {}

    cal_parts = []
    for yr in range(2019, 2026):
        p = CACHE / f"statcast_{yr}.parquet"
        if not p.exists():
            continue
        try:
            part = con.execute(f"""
                SELECT batter, {yr} yr,
                       AVG(estimated_woba_using_speedangle) xwoba, COUNT(*) pa
                FROM read_parquet('{p.as_posix()}')
                WHERE batter IN ({ids_csv})
                  AND events IS NOT NULL AND events != ''
                  AND estimated_woba_using_speedangle IS NOT NULL
                  AND EXTRACT(MONTH FROM game_date) = {CURRENT_MONTH}
                GROUP BY batter
            """).df()
            cal_parts.append(part)
        except Exception:
            pass
    cal_df = pd.concat(cal_parts) if cal_parts else pd.DataFrame()

    result: dict[int, dict] = {}
    for bid in batter_ids:
        bev = ev[ev["batter"] == bid].reset_index(drop=True)
        if bev.empty:
            result[bid] = {}
            continue
        n_total = len(bev)
        l21d_rows = bev.tail(21)
        n_l21d = len(l21d_rows)
        l21d_xwoba = l21d_rows["xwoba"].mean() if n_l21d else None
        l21d_contact = l21d_rows[l21d_rows["launch_speed"].notna()]
        l21d_xwobacon = l21d_contact["xwoba"].mean() if len(l21d_contact) else None
        pre_rows = bev.iloc[:-21] if n_total > 21 else bev.iloc[:0]
        if len(pre_rows) >= 50:
            anchor = pre_rows.tail(150)["xwoba"].mean()
            anchor_n = min(len(pre_rows), 150)
        elif n_total >= 50:
            anchor = bev["xwoba"].mean()
            anchor_n = n_total
        else:
            anchor, anchor_n = None, 0
        k = 150
        if l21d_xwoba is not None and anchor is not None:
            shrunk = (n_l21d * l21d_xwoba + k * anchor) / (n_l21d + k)
            shrunk_gap = round(shrunk - anchor, 4)
        else:
            shrunk_gap = None
        if l21d_xwoba is not None and n_l21d > 0:
            se = 0.39 / np.sqrt(n_l21d)
            ci = (round(l21d_xwoba - 1.96 * se, 3), round(l21d_xwoba + 1.96 * se, 3))
            anchor_in_ci = anchor is not None and ci[0] <= anchor <= ci[1]
        else:
            ci, anchor_in_ci = None, False
        if not cal_df.empty and "batter" in cal_df.columns:
            cb = cal_df[cal_df["batter"] == bid].sort_values("yr")
            cal_hist = {int(r["yr"]): {"xwoba": round(float(r["xwoba"]), 3), "pa": int(r["pa"])}
                        for _, r in cb.iterrows() if r["pa"] >= 15}
        else:
            cal_hist = {}
        result[bid] = {
            "n_l21d": n_l21d,
            "l21d_xwoba": round(float(l21d_xwoba), 3) if l21d_xwoba is not None else None,
            "l21d_xwobacon": round(float(l21d_xwobacon), 3) if l21d_xwobacon is not None else None,
            "anchor_xwoba": round(float(anchor), 3) if anchor is not None else None,
            "anchor_n": anchor_n,
            "shrunk_gap": shrunk_gap,
            "anchor_in_ci": anchor_in_ci,
            "cal_hist": cal_hist,
        }
    return result


def pos_group(pos: str) -> str:
    mapping = {"C": "C", "1B": "1B", "2B": "2B", "3B": "3B", "SS": "SS"}
    if pos in mapping:
        return mapping[pos]
    if pos in ("LF", "RF", "CF"):
        return "OF"
    return "UTIL/DH"


# ── Cross-verdict (all five signals) ─────────────────────────────────────────

def cross_verdict_full(
    form: str,
    sust_bucket: str,
    slump_bounce_pct,
    shrunk_gap,
    anchor_in_ci: bool,
    xwobacon_gap,
    process_verdict: str,
    slump_source: str,
) -> tuple[str, str]:
    """Five-signal verdict: career-form + sustainability + bounce history +
    Bayesian shrinkage + process metrics. Returns (verdict, rationale)."""

    if form == "INSUFFICIENT":
        return "INSUFFICIENT_DATA", "no career sample"

    bp = float(slump_bounce_pct) if slump_bounce_pct is not None and not pd.isna(slump_bounce_pct) else None
    sg = float(shrunk_gap) if shrunk_gap is not None else None

    if form == "SLUMPING":
        # Layer 1: process metrics override — if process is IMPROVING, always hold
        if process_verdict == "IMPROVING":
            return "CONSENSUS_HOLD_BOUNCE", (
                f"process IMPROVING (whiff/chase/Z-contact) despite career-low percentile — "
                f"outcome noise, not skill decline"
            )
        # Layer 2: statistical noise test
        if anchor_in_ci:
            return "HOLD_NOISE", "L21d CI includes anchor — statistically indistinguishable from baseline"
        # Layer 3: K% decomp source
        if slump_source == "BABIP_DRIVEN":
            return "CONSENSUS_HOLD_BOUNCE", "K-decomp: BABIP-driven (outs on contact up, K% stable/down)"
        # Layer 4: high bounce history
        if bp is not None and bp >= 75:
            if sg is None or sg > -0.030:
                return "CONSENSUS_HOLD_BOUNCE", f"{bp:.0f}% historical bounce rate; shrunk gap {sg:+.3f}" if sg else f"{bp:.0f}% historical bounce rate"
        # Layer 5: xwOBACON intact
        if xwobacon_gap is not None and abs(xwobacon_gap) < 0.040:
            return "CONSENSUS_HOLD_BOUNCE", f"xwOBACON gap {xwobacon_gap:+.3f} — contact quality intact"
        # All signals agree: structural
        if (sust_bucket == "REGRESS"
                and process_verdict in ("DECLINING", "MIXED")
                and sg is not None and sg < -0.030
                and (bp is None or bp < 50)):
            bp_str = f"{bp:.0f}%" if bp is not None else "N/A"
            return "CONSENSUS_DROP", (
                f"REGRESS + process {process_verdict} + shrunk {sg:+.3f} + bounce_pct {bp_str}"
            )
        return "SLUMP_AMBIGUOUS", "mixed signals — run /slump-or-decline for full decomp"

    if form == "BELOW_MEDIAN":
        if sust_bucket == "REGRESS" and process_verdict == "DECLINING" and sg is not None and sg < -0.030:
            return "FADING", f"below-median + REGRESS + process DECLINING + shrunk {sg:+.3f}"
        if sg is not None and sg > 0.020:
            return "BOUNCING_BACK", f"shrunk gap {sg:+.3f} — warming up"
        return "CONSENSUS_HOLD_TYPICAL", "below median, no structural decline confirmed"

    if form in ("TYPICAL", "ABOVE_MEDIAN"):
        if sust_bucket in ("LEGIT", "IMPROVING"):
            return "STRENGTHENING", "above baseline + sustainability improving"
        return "CONSENSUS_HOLD_TYPICAL", "baseline performer"

    if form == "HIGH":
        if (sg is not None and sg < -0.020) and sust_bucket == "REGRESS" and process_verdict == "DECLINING":
            return "SELL_HIGH_WARNING", f"HIGH form + REGRESS + process DECLINING + shrunk {sg:+.3f}"
        return "STABLE_HIGH", "high career form, holding"

    if form == "PEAK":
        if process_verdict == "DECLINING" and sust_bucket == "REGRESS":
            sg_str = f"{sg:+.3f}" if sg is not None else "N/A"
            return "SELL_HIGH_WARNING", f"PEAK form + process DECLINING + REGRESS (shrunk {sg_str})"
        return "CONSENSUS_HOLD_PEAK", "at career peak"

    return "UNCLASSIFIED", ""


# ── Report helpers ────────────────────────────────────────────────────────────

def _pct(v) -> str:
    """Format float as percentage string, or 'N/A'."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "N/A"
    return f"{float(v):.1%}"


def _f3(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "N/A"
    return f"{float(v):+.3f}" if float(v) < 0 else f"{float(v):.3f}"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    all_teams = LeagueState().all_teams()
    hitters  = all_teams[~all_teams["position"].isin(["SP", "RP", "P"])].copy()
    pitchers = all_teams[all_teams["position"].isin(["SP", "RP"])].copy()
    print(f"[1/11] {len(hitters)} hitters, {len(pitchers)} pitchers across "
          f"{all_teams['team_id'].nunique()} teams")

    hitters["batter"] = hitters.apply(
        lambda r: resolve(r["player_name"], r["pro_team"], r["position"]), axis=1)
    unres = hitters[hitters["batter"].isna()]
    if len(unres):
        print(f"  [warn] {len(unres)} unresolved: " + ", ".join(unres["player_name"]))
    hitters = hitters.dropna(subset=["batter"]).copy()
    hitters["batter"] = hitters["batter"].astype(int)
    print(f"[2/11] {len(hitters)} resolved")

    multiyr = pd.read_csv(CACHE / "hitters_multiyr_2015_2026.csv")
    multiyr["_nk"] = multiyr["player_name"].map(_norm)
    cf_dict = build_career_form_dict()

    rh3_df = PROJECTIONS.rh3()
    rh3_df["_nk"] = rh3_df["player_name"].map(_norm)
    rh3_lu: dict[str, dict] = {}
    for _, r in rh3_df.iterrows():
        rh3_lu[r["_nk"]] = {k: r.get(k) for k in [
            "xfp_rh3_per_pa", "xfp_rh3_per_game", "recency_form_gap",
            "signal", "rank", "replacement_delta",
            "slump_pct_rank", "slump_n_comparable", "slump_bounce_pct",
            "slump_next_rate", "slump_delta", "pa_last21",
        ]}

    # ── Step 3: 9-marker classify ─────────────────────────────────────────────
    print("[3/11] classify() per hitter...")
    records = []
    for _, row in hitters.iterrows():
        bid = int(row["batter"])
        name = row["player_name"]
        nk = _norm(name)
        sub = multiyr[multiyr["batter"] == bid]
        rows_by_year = {int(r["year"]): r for _, r in sub.iterrows()}
        c = classify(rows_by_year)
        cf = cf_dict.get(bid, {})
        rh3 = rh3_lu.get(nk, {})
        records.append({
            "team_name": row["team_name"], "player_name": name,
            "position": row["position"], "pos_group": pos_group(row["position"]),
            "batter": bid,
            "career_%ile": cf.get("career_percentile"),
            "career_l150_median": cf.get("career_l150_median"),
            "current_l150": cf.get("current_l150"),
            "form_bucket": cf.get("form_bucket", "INSUFFICIENT"),
            "sust_bucket": c.get("bucket", "N/A"),
            "fp_2026": round(c.get("fp_2026") or c.get("fp_cur", 0) or 0, 2),
            "fp_prior": round(c.get("fp_prior", 0) or 0, 2),
            "n_material": c.get("n_material", 0),
            "form_gap": rh3.get("recency_form_gap"),
            "rh3_per_pa": rh3.get("xfp_rh3_per_pa"),
            "rh3_per_game": rh3.get("xfp_rh3_per_game"),
            "rh3_signal": rh3.get("signal"),
            "rh3_rank": rh3.get("rank"),
            "replacement_delta": rh3.get("replacement_delta"),
            "slump_bounce_pct": rh3.get("slump_bounce_pct"),
            "slump_n_comparable": rh3.get("slump_n_comparable"),
            "slump_next_rate": rh3.get("slump_next_rate"),
            "slump_delta": rh3.get("slump_delta"),
            # filled below
            "n_l21d": None, "l21d_xwoba": None, "l21d_xwobacon": None,
            "anchor_xwoba": None, "shrunk_gap": None, "anchor_in_ci": False,
            "cal_hist": {},
            "process_verdict": "UNKNOWN", "process_notes": "",
            "whiff_pct_25": None, "whiff_pct_26": None, "whiff_pct_l21d": None,
            "chase_pct_25": None, "chase_pct_26": None, "chase_pct_l21d": None,
            "ev90_25": None, "ev90_26": None, "ev90_l21d": None,
            "avg_bat_speed_25": None, "avg_bat_speed_26": None,
            "slump_source": "UNKNOWN",
            "pitch_mix_shift": False, "pitch_mix_note": "",
            "peak_type": None, "peak_note": "",
            # injury integration (filled in Step 6b)
            "player_id": row.get("player_id"),
            "injury_class": "NONE",
            "injury_overlap": "NO_OVERLAP",
            "injury_note": "",
            "should_modify_verdict": False,
            # v3 statistical columns (filled below)
            "mc_p_bounce_median": None,
            "mc_p_bounce_current": None,
            "mc_expected_xwoba_30pa": None,
            "mc_ci95_low": None, "mc_ci95_high": None,
            "bayes_posterior_mu": None,
            "bayes_posterior_sigma": None,
            "bayes_ci95_low": None, "bayes_ci95_high": None,
            "bayes_p_above_career": None,
            "bayes_p_above_avg": None,
            "bayes_games_to_200fp": None,
            "hist_n_comps": None,
            "hist_p_bounce_30pa": None,
            "hist_p_bounce_60pa": None,
            "hist_median_next_30pa": None,
            "hist_p10_next_30pa": None, "hist_p90_next_30pa": None,
            "peak_p_still_peak_30pa": None,
            "peak_p_still_peak_60pa": None,
            "peak_expected_weeks_reversion": None,
            "peak_trade_window": None,
        })

    df = pd.DataFrame(records)

    # ── Step 4: slump diagnostics (Bayesian shrinkage + xwOBACON + calendar) ──
    slump_ids = df[df["form_bucket"].isin(["SLUMPING", "BELOW_MEDIAN"])]["batter"].unique().tolist()
    print(f"[4/11] slump diagnostics for {len(slump_ids)} players...")
    diag = batch_slump_diagnostics(slump_ids)
    for i, row in df.iterrows():
        d = diag.get(row["batter"], {})
        if d:
            for col in ("n_l21d","l21d_xwoba","l21d_xwobacon","anchor_xwoba",
                        "shrunk_gap","anchor_in_ci","cal_hist"):
                df.at[i, col] = d.get(col, df.at[i, col])
    df["xwobacon_gap"] = df.apply(
        lambda r: round(float(r["l21d_xwobacon"]) - float(r["anchor_xwoba"]), 3)
        if pd.notna(r.get("l21d_xwobacon")) and pd.notna(r.get("anchor_xwoba")) else None,
        axis=1)

    # ── Step 5: process metrics (all hitters) ─────────────────────────────────
    all_ids = df["batter"].unique().tolist()
    print(f"[5/11] process metrics for {len(all_ids)} hitters...")
    proc = batch_process_metrics(all_ids)
    for i, row in df.iterrows():
        p = proc.get(row["batter"], {})
        if p:
            df.at[i, "process_verdict"] = p.get("process_verdict", "UNKNOWN")
            df.at[i, "process_notes"]   = p.get("process_notes", "")
            df.at[i, "whiff_pct_25"]    = (p.get("2025") or {}).get("whiff_pct")
            df.at[i, "whiff_pct_26"]    = (p.get("2026_szn") or {}).get("whiff_pct")
            df.at[i, "whiff_pct_l21d"]  = (p.get("l21d") or {}).get("whiff_pct")
            df.at[i, "chase_pct_25"]    = (p.get("2025") or {}).get("chase_pct")
            df.at[i, "chase_pct_26"]    = (p.get("2026_szn") or {}).get("chase_pct")
            df.at[i, "chase_pct_l21d"]  = (p.get("l21d") or {}).get("chase_pct")
            df.at[i, "ev90_25"]         = (p.get("2025") or {}).get("ev90")
            df.at[i, "ev90_26"]         = (p.get("2026_szn") or {}).get("ev90")
            df.at[i, "ev90_l21d"]       = (p.get("l21d") or {}).get("ev90")
            df.at[i, "avg_bat_speed_25"] = (p.get("2025") or {}).get("avg_bat_speed")
            df.at[i, "avg_bat_speed_26"] = (p.get("2026_szn") or {}).get("avg_bat_speed")

    # ── Step 6: slump trajectory (slumpers only) ──────────────────────────────
    print(f"[6/11] slump trajectory for {len(slump_ids)} slumpers...")
    traj = batch_slump_trajectory(slump_ids)
    for i, row in df.iterrows():
        t = traj.get(row["batter"], {})
        if t:
            kd = t.get("k_decomp", {})
            df.at[i, "slump_source"]    = kd.get("slump_source", "UNKNOWN")
            pm = t.get("pitch_mix", {})
            df.at[i, "pitch_mix_shift"] = pm.get("shift_flag", False)
            df.at[i, "pitch_mix_note"]  = pm.get("shift_note", "")

    # ── Step 6b: Injury signal integration ───────────────────────────────────
    print("[6b/11] Injury signal integration...")
    espn_pids = df["player_id"].dropna().astype(int).tolist()
    injury_lu: dict[int, dict] = {}
    if espn_pids:
        injury_lu = batch_injury_status(espn_pids)
        # Backfill from roster df using injured / injury_status columns
        injury_lu = enrich_from_roster_df(espn_pids, hitters, injury_lu)
    else:
        print("  [warn] No ESPN player_ids found — injury integration skipped")

    # Build slump_start_date lookup by ESPN player_id (via batter → player_id map)
    batter_to_pid: dict[int, int] = {}
    for _, row in df.iterrows():
        pid = row.get("player_id")
        bid = row.get("batter")
        if pid is not None and bid is not None:
            try:
                batter_to_pid[int(bid)] = int(pid)
            except (ValueError, TypeError):
                pass

    slump_start_by_pid: dict[int, str | None] = {}
    for bid, tdata in traj.items():
        pid = batter_to_pid.get(int(bid))
        if pid is not None:
            slump_start_by_pid[pid] = tdata.get("slump_start_date")

    # Classify impact and write columns back to df
    for i, row in df.iterrows():
        pid = row.get("player_id")
        if pid is None:
            continue
        try:
            pid_int = int(pid)
        except (ValueError, TypeError):
            continue
        status = injury_lu.get(pid_int, {})
        if not status:
            continue
        slump_start = slump_start_by_pid.get(pid_int)
        impact = classify_injury_impact(status, slump_start)
        df.at[i, "injury_class"]        = impact["injury_class"]
        df.at[i, "injury_overlap"]      = impact["injury_overlap"]
        df.at[i, "injury_note"]         = impact["injury_note"]
        df.at[i, "should_modify_verdict"] = impact["should_modify_verdict"]

    n_injured = (df["injury_class"] != "NONE").sum()
    n_explained = (df["injury_overlap"] == "SLUMP_EXPLAINED").sum()
    n_possible  = (df["injury_overlap"] == "POSSIBLE_FACTOR").sum()
    print(f"  Rostered hitters with any injury flag: {n_injured}")
    print(f"  Slumpers with SLUMP_EXPLAINED overlap:  {n_explained}")
    print(f"  Slumpers with POSSIBLE_FACTOR overlap:  {n_possible}")

    # ── Step 7: PEAK validator ────────────────────────────────────────────────
    peak_ids = df[df["form_bucket"] == "PEAK"]["batter"].unique().tolist()
    print(f"[7/11] PEAK validator for {len(peak_ids)} peakers...")
    peak_res = batch_peak_validator(peak_ids)
    for i, row in df.iterrows():
        pv = peak_res.get(row["batter"], {})
        if pv:
            df.at[i, "peak_type"] = pv.get("peak_type")
            df.at[i, "peak_note"] = pv.get("peak_note", "")
            pt = pv.get("peak_type")
            if pt == "OUTCOME_DRIVEN":
                df.at[i, "process_verdict"] = "DECLINING"
            elif pt == "PROCESS_DRIVEN":
                df.at[i, "process_verdict"] = "IMPROVING"

    # ── Step 8 (v3): MC bounce simulator ─────────────────────────────────────
    print(f"[8/11] MC bounce simulator ({len(all_ids)} hitters, 10k sims each)...")
    mc_res = batch_mc_bounce(all_ids, n_sim=10_000, decay_lambda=0.20)
    for i, row in df.iterrows():
        mc = mc_res.get(row["batter"], {})
        if mc and not mc.get("insufficient"):
            df.at[i, "mc_p_bounce_median"]    = mc.get("p_bounce_above_median")
            df.at[i, "mc_p_bounce_current"]   = mc.get("p_bounce_above_current")
            df.at[i, "mc_expected_xwoba_30pa"] = mc.get("expected_xwoba_30pa")
            df.at[i, "mc_ci95_low"]           = mc.get("ci_95_low")
            df.at[i, "mc_ci95_high"]          = mc.get("ci_95_high")

    # ── Step 9 (v3): Bayesian talent estimator ────────────────────────────────
    print(f"[9/11] Bayesian talent estimation ({len(all_ids)} hitters)...")
    bayes_res = batch_bayesian_talent(all_ids, decay_lambda=0.20)
    for i, row in df.iterrows():
        b = bayes_res.get(row["batter"], {})
        if b:
            df.at[i, "bayes_posterior_mu"]    = b.get("posterior_mu")
            df.at[i, "bayes_posterior_sigma"] = b.get("posterior_sigma")
            df.at[i, "bayes_ci95_low"]        = b.get("ci_95_low")
            df.at[i, "bayes_ci95_high"]       = b.get("ci_95_high")
            df.at[i, "bayes_p_above_career"]  = b.get("p_true_talent_above_career_median")
            df.at[i, "bayes_p_above_avg"]     = b.get("p_true_talent_above_avg")
            df.at[i, "bayes_games_to_200fp"]  = b.get("games_to_200fp")

    # ── Step 10 (v3): Historical comp matcher ─────────────────────────────────
    # Run on slumpers + peakers (most actionable)
    stat_ids = list(set(slump_ids + peak_ids))
    print(f"[10/11] Historical comp matcher ({len(stat_ids)} players)...")
    comp_res = batch_historical_comps(stat_ids, age_window=3)
    for i, row in df.iterrows():
        c = comp_res.get(row["batter"], {})
        if c and not c.get("insufficient_comps"):
            df.at[i, "hist_n_comps"]         = c.get("n_comps")
            df.at[i, "hist_p_bounce_30pa"]   = c.get("p_bounced_30pa")
            df.at[i, "hist_p_bounce_60pa"]   = c.get("p_bounced_60pa")
            df.at[i, "hist_median_next_30pa"]= c.get("median_next_30pa")
            df.at[i, "hist_p10_next_30pa"]   = c.get("p10_next_30pa")
            df.at[i, "hist_p90_next_30pa"]   = c.get("p90_next_30pa")

    # Peak decay
    if peak_ids:
        print(f"  Peak decay curves for {len(peak_ids)} peakers...")
        decay_res = batch_peak_decay(peak_ids)
        for i, row in df.iterrows():
            d = decay_res.get(row["batter"], {})
            if d:
                df.at[i, "peak_p_still_peak_30pa"]          = d.get("p_still_peak_30pa")
                df.at[i, "peak_p_still_peak_60pa"]          = d.get("p_still_peak_60pa")
                df.at[i, "peak_p_still_peak_30pa_ci_low"]   = d.get("p_still_peak_30pa_ci_low")
                df.at[i, "peak_p_still_peak_30pa_ci_high"]  = d.get("p_still_peak_30pa_ci_high")
                df.at[i, "peak_p_still_peak_60pa_ci_low"]   = d.get("p_still_peak_60pa_ci_low")
                df.at[i, "peak_p_still_peak_60pa_ci_high"]  = d.get("p_still_peak_60pa_ci_high")
                df.at[i, "peak_expected_weeks_reversion"]   = d.get("expected_weeks_to_reversion")
                df.at[i, "peak_trade_window"]               = d.get("trade_window")

    # ── cross_verdict ─────────────────────────────────────────────────────────
    print("[11/11] cross_verdict + writing report...")
    verdicts = df.apply(lambda r: cross_verdict_full(
        r["form_bucket"], r["sust_bucket"],
        r.get("slump_bounce_pct"), r.get("shrunk_gap"),
        bool(r.get("anchor_in_ci", False)), r.get("xwobacon_gap"),
        r.get("process_verdict", "UNKNOWN"),
        r.get("slump_source", "UNKNOWN"),
    ), axis=1)
    df["cross_verdict"]     = verdicts.apply(lambda x: x[0])
    df["verdict_rationale"] = verdicts.apply(lambda x: x[1])

    # Append injury modifier to verdict_rationale where applicable
    for i, row in df.iterrows():
        if row.get("should_modify_verdict"):
            suffix = " [NOTE: injury overlap — slump may be health-driven, not skill signal]"
            df.at[i, "verdict_rationale"] = str(row["verdict_rationale"]) + suffix

    df.to_csv(ROOT / f"data/research/league_sust_full_{TODAY}.csv", index=False)

    # ── Pitcher SP career-form ────────────────────────────────────────────────
    import unicodedata as _ud

    def _ascii(s: str) -> str:
        """Strip accents: 'Jesús' → 'Jesus', 'Ján' → 'Jan'."""
        return _ud.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")

    def _to_first_last(name: str) -> str:
        """Convert 'Last, First' → 'First Last'. Pass-through if no comma."""
        if "," in name:
            parts = [p.strip() for p in name.split(",", 1)]
            return f"{parts[1]} {parts[0]}"
        return name

    rp3 = PROJECTIONS.rp3()
    rprs2 = PROJECTIONS.rprs2()
    rprs2_col = "xfp_ros" if "xfp_ros" in rprs2.columns else rprs2.columns[-1]
    # rp3 uses "Last, First" format; ESPN roster uses "First Last" — build both-way lookup
    # Also store accent-stripped variants so "Jesús" matches ESPN's "Jesus" etc.
    rp3_lu_proj: dict[str, float] = {}
    rp3_gap_lu: dict[str, float] = {}
    for _, pr in rp3.iterrows():
        if not isinstance(pr["player_name"], str):
            continue
        first_last = _to_first_last(pr["player_name"])
        for key in (pr["player_name"], first_last, _ascii(pr["player_name"]), _ascii(first_last)):
            rp3_lu_proj[key] = pr["xfp_rp3_per_start"]
            rp3_gap_lu[key]  = pr.get("recency_form_gap")
    rprs2_lu    = dict(zip(rprs2["name_api"], rprs2[rprs2_col]))
    pitchers = pitchers.copy()
    pitchers["proj"]     = pitchers.apply(
        lambda r: rp3_lu_proj.get(r["player_name"]) if r["position"] == "SP"
        else rprs2_lu.get(r["player_name"]), axis=1)
    pitchers["form_gap"] = pitchers.apply(
        lambda r: rp3_gap_lu.get(r["player_name"]) if r["position"] == "SP" else None, axis=1)

    sp_id_map = build_sp_id_map()
    sp_ids = [sp_id_map[n] for n in pitchers[pitchers["position"] == "SP"]["player_name"]
              if n in sp_id_map]
    sp_ids = [int(x) for x in set(sp_ids)]
    sp_form = batch_sp_career_form(sp_ids)
    sp_form_lu = {v: sp_form.get(k, {}) for k, v in sp_id_map.items()}

    def sp_form_row(name):
        return sp_form_lu.get(name, {})

    pitchers["k_form"]      = pitchers["player_name"].apply(lambda n: sp_form_row(n).get("k_form_bucket", ""))
    pitchers["velo_form"]   = pitchers["player_name"].apply(lambda n: sp_form_row(n).get("velo_form_bucket", ""))
    pitchers["velo_delta"]  = pitchers["player_name"].apply(lambda n: sp_form_row(n).get("velo_delta"))
    pitchers["velo_flag"]   = pitchers["player_name"].apply(lambda n: sp_form_row(n).get("velo_flag", False))
    pitchers["l5_k_rate"]   = pitchers["player_name"].apply(lambda n: sp_form_row(n).get("current_l5_k_rate"))
    pitchers["career_k_pct"]= pitchers["player_name"].apply(lambda n: sp_form_row(n).get("career_k_percentile"))

    # ── Report ────────────────────────────────────────────────────────────────
    lines: list[str] = []
    lines.append(f"# League-wide roster deep audit (v4 — statistical + calibrated) — {TODAY}\n")
    lines.append(
        f"**Hitters:** {len(df)} | "
        f"**Slumpers analyzed:** {len(slump_ids)} | "
        f"**PEAK validated:** {len(peak_ids)} | "
        f"**MC sims:** 10,000/player (λ=0.20 recency decay) | "
        f"**Historical comps:** 2015-2025 Statcast (age-matched ±3yr) | "
        f"**SP career-form:** {len(sp_ids)} SPs\n"
    )
    lines.append(
        "> **CONSENSUS_DROP gate:** requires REGRESS + process DECLINING/MIXED "
        "+ shrunk_gap < −0.030 + bounce_pct < 50%. "
        "IMPROVING process or anchor_in_CI always overrides to HOLD.\n"
    )
    lines.append(
        "> **v4 upgrades:** recency-weighted MC + Bayesian (λ=0.20), age-matched comps (±3yr), "
        "Wilson CIs on survival curves, injury signal integration (ESPN DTD/IL).\n"
    )
    lines.append(
        "> **Calibration:** ECE=0.0197 (WELL_CALIBRATED, threshold < 0.05), "
        "Brier=0.2221, validated on 15,778 out-of-sample snapshots (2023-2025 holdout). "
        "_Known limitation: adjacent rolling-150 windows share 149/150 events — "
        "precision is slightly overstated vs true i.i.d._\n"
    )

    # ── Power ranking ─────────────────────────────────────────────────────────
    lines.append("## Power ranking\n")
    power = df.groupby("team_name").agg(
        n           =("player_name", "count"),
        mean_pct    =("career_%ile", "mean"),
        n_peak      =("form_bucket", lambda s: (s == "PEAK").sum()),
        n_high      =("form_bucket", lambda s: (s == "HIGH").sum()),
        n_slump     =("form_bucket", lambda s: (s == "SLUMPING").sum()),
        n_improving =("process_verdict", lambda s: (s == "IMPROVING").sum()),
        n_declining =("process_verdict", lambda s: (s == "DECLINING").sum()),
        n_bounce    =("cross_verdict", lambda s: s.isin(["CONSENSUS_HOLD_BOUNCE","HOLD_NOISE"]).sum()),
        n_drop      =("cross_verdict", lambda s: (s == "CONSENSUS_DROP").sum()),
        mean_rh3    =("rh3_per_pa", "mean"),
        mean_bayes_p_avg=("bayes_p_above_avg", "mean"),
    ).round(3)
    pitch_sum = pitchers[pitchers["position"] == "SP"].dropna(subset=["proj"]).groupby("team_name")["proj"].sum().round(1)
    power["sp_proj"] = pitch_sum
    power = power.sort_values("mean_rh3", ascending=False)
    power.insert(0, "rank", range(1, len(power) + 1))
    lines.append(power.to_markdown())
    lines.append("")

    # ── Per-team position breakdown ───────────────────────────────────────────
    lines.append("\n## Per-team position breakdown\n")
    hitter_cols = [
        "player_name", "career_%ile", "current_l150", "form_bucket",
        "sust_bucket", "process_verdict",
        "whiff_pct_25", "whiff_pct_l21d",
        "ev90_25", "ev90_l21d",
        "slump_bounce_pct", "shrunk_gap", "anchor_in_ci",
        "mc_p_bounce_median", "bayes_p_above_avg", "bayes_games_to_200fp",
        "hist_n_comps", "hist_p_bounce_30pa",
        "slump_source", "rh3_per_pa", "rh3_signal",
        "peak_type", "peak_trade_window",
        "cross_verdict",
        "injury_class", "injury_note",
    ]
    sp_cols = ["player_name", "proj", "form_gap", "k_form", "velo_form",
               "velo_delta", "velo_flag", "l5_k_rate", "career_k_pct"]

    for tname in [MY_TEAM] + sorted([t for t in df["team_name"].unique() if t != MY_TEAM]):
        marker = " ← YOU" if tname == MY_TEAM else ""
        lines.append(f"\n### {tname}{marker}\n")
        th = df[df["team_name"] == tname]
        tp = pitchers[pitchers["team_name"] == tname]

        for pg in ["C", "1B", "2B", "3B", "SS", "OF", "UTIL/DH"]:
            grp = th[th["pos_group"] == pg].sort_values("rh3_per_pa", ascending=False)
            if grp.empty:
                continue
            lines.append(f"**{pg}**\n")
            present = [c for c in hitter_cols if c in grp.columns]
            lines.append(grp[present].round(3).to_markdown(index=False))
            lines.append("")

        sp_grp = tp[tp["position"] == "SP"].sort_values("proj", ascending=False)
        rp_grp = tp[tp["position"] == "RP"].sort_values("proj", ascending=False)
        if not sp_grp.empty:
            lines.append("**SP**\n")
            present_sp = [c for c in sp_cols if c in sp_grp.columns]
            lines.append(sp_grp[present_sp].round(3).to_markdown(index=False))
            lines.append("")
        if not rp_grp.empty:
            lines.append("**RP**\n")
            lines.append(rp_grp[["player_name", "proj"]].round(3).to_markdown(index=False))
            lines.append("")

    # ── Slump detail cards (v3) ───────────────────────────────────────────────
    lines.append("\n## Slump detail cards (v3 — with MC + Bayesian + historical comps)\n")
    slumpers = df[df["form_bucket"] == "SLUMPING"].sort_values("rh3_per_pa", ascending=False)
    for _, r in slumpers.iterrows():
        lines.append(f"\n### {r['player_name']} ({r['team_name']}, {r['position']})\n")
        lines.append(f"- **Career %ile:** {r['career_%ile']:.1%}  "
                     f"| **Sust:** {r['sust_bucket']}  "
                     f"| **Process:** {r['process_verdict']}\n")

        # Injury line (only surface if injured)
        inj_cls = r.get("injury_class", "NONE")
        if inj_cls and inj_cls != "NONE":
            inj_note = r.get("injury_note") or inj_cls
            lines.append(f"- **Injury:** {inj_note}"
                         + (" — Slump may be health-driven." if r.get("should_modify_verdict") else "")
                         + "\n")

        # v2 signals
        bp = r.get("slump_bounce_pct")
        nc = r.get("slump_n_comparable")
        sd = r.get("slump_delta")
        if pd.notna(bp) and pd.notna(nc):
            lines.append(f"- **Bounce history (rh3):** {bp:.0f}% of {nc:.0f} comparables bounced  "
                         f"| uplift: {sd:+.3f}/PA\n" if pd.notna(sd) else
                         f"- **Bounce history (rh3):** {bp:.0f}% of {nc:.0f} comparables bounced\n")
        if pd.notna(r.get("shrunk_gap")):
            aic = "YES — noise" if r["anchor_in_ci"] else "No"
            lines.append(f"- **Bayesian shrunk gap:** {r['shrunk_gap']:+.3f}  "
                         f"| anchor: {r['anchor_xwoba']:.3f}  "
                         f"| anchor_in_CI: {aic}\n")
        if pd.notna(r.get("xwobacon_gap")):
            note = "contact intact (BABIP)" if abs(r["xwobacon_gap"]) < 0.040 else "contact declining"
            lines.append(f"- **xwOBACON gap:** {r['xwobacon_gap']:+.3f} ({note})\n")
        if pd.notna(r.get("whiff_pct_25")) and pd.notna(r.get("whiff_pct_l21d")):
            lines.append(f"- **Process:** whiff% {r['whiff_pct_25']:.1f}→{r['whiff_pct_l21d']:.1f}  "
                         f"chase% {r['chase_pct_25']:.1f}→{r['chase_pct_l21d']:.1f}  "
                         f"EV90 {r['ev90_25']:.1f}→{r['ev90_l21d']:.1f}\n")

        # v3: MC bounce
        if pd.notna(r.get("mc_p_bounce_median")):
            lines.append(
                f"- **MC bounce (10k sims):** P(next 30PA > career median) = "
                f"**{r['mc_p_bounce_median']:.1%}**  "
                f"| Expected xwOBA: {r['mc_expected_xwoba_30pa']:.3f}  "
                f"| 95% CI: [{r['mc_ci95_low']:.3f}, {r['mc_ci95_high']:.3f}]\n"
            )

        # v3: Bayesian posterior
        if pd.notna(r.get("bayes_posterior_mu")):
            lines.append(
                f"- **Bayesian talent:** posterior μ = {r['bayes_posterior_mu']:.3f}  "
                f"| 95% CI: [{r['bayes_ci95_low']:.3f}, {r['bayes_ci95_high']:.3f}]  "
                f"| P(talent > career median) = {r['bayes_p_above_career']:.1%}  "
                f"| P(talent > league avg .320) = **{r['bayes_p_above_avg']:.1%}**  "
                f"| Games to 200 FP: {r['bayes_games_to_200fp']:.0f}\n"
                if pd.notna(r.get("bayes_games_to_200fp")) else
                f"- **Bayesian talent:** posterior μ = {r['bayes_posterior_mu']:.3f}  "
                f"| 95% CI: [{r['bayes_ci95_low']:.3f}, {r['bayes_ci95_high']:.3f}]  "
                f"| P(talent > league avg .320) = **{r['bayes_p_above_avg']:.1%}**\n"
            )

        # v3/v4: Historical comps (age-matched ±3yr)
        if pd.notna(r.get("hist_n_comps")) and r["hist_n_comps"] >= 5:
            lines.append(
                f"- **Historical comps (2015-25, age-matched):** {r['hist_n_comps']:.0f} comparables at "
                f"similar career %ile/PA/month/age  "
                f"| P(bounce 30PA) = **{r['hist_p_bounce_30pa']:.1%}**  "
                f"| P(bounce 60PA) = {r['hist_p_bounce_60pa']:.1%}  "
                f"| Median next-30PA xwOBA: {r['hist_median_next_30pa']:.3f}  "
                f"| 10-90 range: [{r['hist_p10_next_30pa']:.3f}, {r['hist_p90_next_30pa']:.3f}]\n"
            )

        ss = r.get("slump_source", "UNKNOWN")
        if ss not in ("UNKNOWN", "HOLDING"):
            lines.append(f"- **K-decomp source:** {ss}\n")

        if r.get("process_notes"):
            lines.append(f"- **Process notes:** {r['process_notes']}\n")

        cal = r.get("cal_hist") or {}
        if isinstance(cal, dict) and cal:
            month_name = date(2026, CURRENT_MONTH, 1).strftime("%B")
            cal_str = "  |  ".join(
                f"{yr}: {v['xwoba']:.3f} ({v['pa']}PA)" for yr, v in sorted(cal.items()))
            lines.append(f"- **{month_name} career history:** {cal_str}\n")

        lines.append(f"- **VERDICT:** {r['cross_verdict']} — {r['verdict_rationale']}\n")

    # ── PEAK detail cards (v3) ────────────────────────────────────────────────
    lines.append("\n## PEAK player validator (v3 — with survival curves)\n")
    peakers = df[df["form_bucket"] == "PEAK"].sort_values("rh3_per_pa", ascending=False)
    for _, r in peakers.iterrows():
        pt = r.get("peak_type") or "UNCONFIRMED"
        lines.append(f"\n### {r['player_name']} ({r['team_name']}, {r['position']}) — {pt}\n")
        lines.append(f"- **Career %ile:** {r['career_%ile']:.1%}  "
                     f"| **rh3:** {r['rh3_per_pa']:.3f}  "
                     f"| **Sust:** {r['sust_bucket']}\n")

        # Bayesian: peakers should have high P > avg
        if pd.notna(r.get("bayes_p_above_avg")):
            lines.append(
                f"- **Bayesian talent:** posterior μ = {r['bayes_posterior_mu']:.3f}  "
                f"| P(true talent > .320) = **{r['bayes_p_above_avg']:.1%}**  "
                f"| P(true talent > career median) = {r['bayes_p_above_career']:.1%}\n"
            )

        # Historical comps (from comp matcher, peak mode)
        if pd.notna(r.get("hist_n_comps")) and r["hist_n_comps"] >= 5:
            lines.append(
                f"- **Historical comps:** {r['hist_n_comps']:.0f} real peak comps (2015-25)  "
                f"| P(meaningful bounce upward from current) = {r['hist_p_bounce_30pa']:.1%}  "
                f"| Median next-30PA xwOBA: {r['hist_median_next_30pa']:.3f}\n"
            )

        # Peak survival curves
        if pd.notna(r.get("peak_p_still_peak_30pa")):
            ci30_lo = r.get("peak_p_still_peak_30pa_ci_low")
            ci30_hi = r.get("peak_p_still_peak_30pa_ci_high")
            ci60_lo = r.get("peak_p_still_peak_60pa_ci_low")
            ci60_hi = r.get("peak_p_still_peak_60pa_ci_high")
            ci30_str = (f" [{ci30_lo:.1%}, {ci30_hi:.1%}]"
                        if pd.notna(ci30_lo) and pd.notna(ci30_hi) else "")
            ci60_str = (f" [{ci60_lo:.1%}, {ci60_hi:.1%}]"
                        if pd.notna(ci60_lo) and pd.notna(ci60_hi) else "")
            lines.append(
                f"- **Peak survival:** P(still PEAK at +30PA) = **{r['peak_p_still_peak_30pa']:.1%}**{ci30_str}  "
                f"| +60PA = {r['peak_p_still_peak_60pa']:.1%}{ci60_str}  "
                f"| Expected weeks to reversion: {r['peak_expected_weeks_reversion']:.1f}  "
                f"| Trade window: **{r['peak_trade_window']}**\n"
            )

        if r.get("peak_note"):
            lines.append(f"- {r['peak_note']}\n")
        lines.append(f"- **Trade implication:** {r['cross_verdict']} — {r['verdict_rationale']}\n")

    # ── SP velo flags ─────────────────────────────────────────────────────────
    lines.append("\n## SP velo flags (> 1.0 mph drop, injury/fatigue signal)\n")
    flagged = pitchers[pitchers["velo_flag"] == True].sort_values("proj", ascending=False)
    if len(flagged):
        lines.append(flagged[["team_name", "player_name", "proj", "velo_delta",
                               "l5_k_rate", "k_form"]].round(3).to_markdown(index=False))
    else:
        lines.append("_No SP velo flags this week._")

    # ── Statistical summary box ───────────────────────────────────────────────
    lines.append("\n## Statistical confidence summary\n")
    lines.append("_For each slumper, the convergence of 4 independent statistical tests:_\n")
    lines.append("| Player | MC P(bounce) | Bayes P(>avg) | Hist comps | Hist P(bounce 30PA) | Injury | Verdict |\n")
    lines.append("|---|---|---|---|---|---|---|\n")
    stat_slumpers = df[df["form_bucket"] == "SLUMPING"].sort_values("rh3_per_pa", ascending=False)
    for _, r in stat_slumpers.iterrows():
        mc_pct = _pct(r.get("mc_p_bounce_median"))
        bayes_pct = _pct(r.get("bayes_p_above_avg"))
        n_comps = f"{r['hist_n_comps']:.0f}" if pd.notna(r.get("hist_n_comps")) else "N/A"
        hist_pct = _pct(r.get("hist_p_bounce_30pa"))
        inj_cls = r.get("injury_class") or "NONE"
        lines.append(
            f"| {r['player_name']} | {mc_pct} | {bayes_pct} | {n_comps} | {hist_pct} | {inj_cls} | {r['cross_verdict']} |\n"
        )

    # ── Waiver wire targets — rival slumpers bouncing back ────────────────────
    lines.append("\n## Waiver wire targets — slumpers bouncing back\n")
    lines.append("_Statistically supported bounce candidates on rival rosters — "
                 "watch for drops or offer a low-cost add._\n")
    ww_targets = df[
        (df["team_name"] != MY_TEAM)
        & (df["cross_verdict"].isin(["CONSENSUS_HOLD_BOUNCE", "HOLD_NOISE", "BOUNCING_BACK"]))
        & (df["replacement_delta"].fillna(0) > 0.002)
    ].sort_values("rh3_per_pa", ascending=False).head(20)
    if len(ww_targets):
        lines.append(ww_targets[[
            "team_name", "player_name", "position", "career_%ile", "form_bucket",
            "process_verdict",
            "mc_p_bounce_median", "bayes_p_above_avg", "hist_p_bounce_30pa",
            "rh3_per_pa", "replacement_delta", "cross_verdict",
        ]].round(3).to_markdown(index=False))
    else:
        lines.append("_None qualifying._")

    # ── FA add candidates ─────────────────────────────────────────────────────
    lines.append("\n## FA add candidates\n")
    lines.append(
        "_Available free agents with model projections. "
        "Ownership < 90% in this 8-team league._\n"
    )
    try:
        _league = _get_league()
        fa_players = _league.free_agents(size=2000)

        # Build enrichment lookup from df (already computed hitter stats)
        # Uses _norm (same key as rh3_lu)
        hitter_enrich = {}
        for _, row in df.iterrows():
            hitter_enrich[_norm(row["player_name"])] = row

        fa_hit, fa_sp, fa_rp = [], [], []
        for p in fa_players:
            pname = getattr(p, "name", "") or ""
            pos = getattr(p, "position", "") or ""
            owned = getattr(p, "percent_owned", 0.0) or 0.0
            if owned >= 90:
                continue
            nk = _norm(pname)

            if pos in ("SP",):
                # Look up rp3 projection
                proj_val = rp3_lu_proj.get(pname) or rp3_lu_proj.get(_ascii(pname))
                gap_val = rp3_gap_lu.get(pname) or rp3_gap_lu.get(_ascii(pname))
                if proj_val is None:
                    continue
                fa_sp.append({
                    "player_name": pname,
                    "owned_%": round(owned, 1),
                    "rp3_proj/start": round(float(proj_val), 2),
                    "form_gap": round(float(gap_val), 2) if gap_val is not None else None,
                })
            elif pos in ("RP",):
                # Look up rprs2 projection
                proj_val = rprs2_lu.get(pname)
                if proj_val is None:
                    continue
                fa_rp.append({
                    "player_name": pname,
                    "owned_%": round(owned, 1),
                    "rprs2_proj_ros": round(float(proj_val), 1) if pd.notna(proj_val) else None,
                })
            else:
                # Hitter — look up rh3 + career form
                rh3_row = rh3_lu.get(nk, {})
                proj_val = rh3_row.get("xfp_rh3_per_pa")
                if proj_val is None:
                    continue
                enrich = hitter_enrich.get(nk, {})
                fa_hit.append({
                    "player_name": pname,
                    "position": pos,
                    "owned_%": round(owned, 1),
                    "xfp_rh3_per_pa": round(float(proj_val), 3),
                    "rh3_signal": rh3_row.get("signal", ""),
                    "form_bucket": enrich.get("form_bucket", "N/A") if hasattr(enrich, "get") else "N/A",
                    "process_verdict": enrich.get("process_verdict", "") if hasattr(enrich, "get") else "",
                    "career_%ile": round(enrich["career_%ile"], 3) if hasattr(enrich, "get") and pd.notna(enrich.get("career_%ile")) else None,
                    "cross_verdict": enrich.get("cross_verdict", "") if hasattr(enrich, "get") else "",
                })

        lines.append("### FA hitters (top 15 by rh3 projection)\n")
        if fa_hit:
            fa_hit_df = (
                pd.DataFrame(fa_hit)
                .sort_values("xfp_rh3_per_pa", ascending=False)
                .head(15)
            )
            lines.append(fa_hit_df.to_markdown(index=False))
        else:
            lines.append("_No FA hitters found in rh3 projections._")

        lines.append("\n### FA starting pitchers (top 10 by rp3 projection)\n")
        if fa_sp:
            fa_sp_df = (
                pd.DataFrame(fa_sp)
                .sort_values("rp3_proj/start", ascending=False)
                .head(10)
            )
            lines.append(fa_sp_df.to_markdown(index=False))
        else:
            lines.append("_No FA SPs found in rp3 projections._")

        lines.append("\n### FA relief pitchers (top 10 by rprs2 projection)\n")
        if fa_rp:
            fa_rp_df = (
                pd.DataFrame(fa_rp)
                .dropna(subset=["rprs2_proj_ros"])
                .sort_values("rprs2_proj_ros", ascending=False)
                .head(10)
            )
            lines.append(fa_rp_df.to_markdown(index=False))
        else:
            lines.append("_No FA RPs found in rprs2 projections._")

    except Exception as _e:
        lines.append(f"_FA fetch failed: {_e}_")

    # ── Watch list — your players showing peak regression risk ────────────────
    lines.append("\n## Watch list — your players showing peak regression risk\n")
    lines.append("_Consider dropping or monitoring before value fades._\n")
    my_sell = df[(df["team_name"] == MY_TEAM) & (df["cross_verdict"] == "SELL_HIGH_WARNING")]
    if len(my_sell):
        lines.append(my_sell[[
            "player_name", "position", "career_%ile", "form_bucket",
            "process_verdict", "peak_type",
            "bayes_p_above_avg", "peak_p_still_peak_30pa",
            "rh3_per_pa", "cross_verdict",
        ]].round(3).to_markdown(index=False))
    else:
        lines.append("_None._")

    # ── Optional trade context ────────────────────────────────────────────────
    lines.append("\n---\n\n## Optional — trade context (if relevant)\n")

    lines.append("\n### Trade targets — rival slumpers to buy\n")
    trade_targets = df[
        (df["team_name"] != MY_TEAM)
        & (df["cross_verdict"].isin(["CONSENSUS_HOLD_BOUNCE", "HOLD_NOISE", "BOUNCING_BACK"]))
        & (df["replacement_delta"].fillna(0) > 0.002)
    ].sort_values("rh3_per_pa", ascending=False).head(20)
    if len(trade_targets):
        lines.append(trade_targets[[
            "team_name", "player_name", "position", "career_%ile", "form_bucket",
            "process_verdict",
            "mc_p_bounce_median", "bayes_p_above_avg", "hist_p_bounce_30pa",
            "rh3_per_pa", "replacement_delta", "cross_verdict",
        ]].round(3).to_markdown(index=False))
    else:
        lines.append("_None qualifying._")

    # ── Rival peakers cooling ─────────────────────────────────────────────────
    lines.append("\n### Rival peakers cooling\n")
    rival_sell = df[
        (df["team_name"] != MY_TEAM) & (df["cross_verdict"] == "SELL_HIGH_WARNING")
    ].sort_values("rh3_per_pa", ascending=False)
    if len(rival_sell):
        lines.append(rival_sell[[
            "team_name", "player_name", "position", "career_%ile",
            "form_bucket", "peak_type", "process_verdict",
            "bayes_p_above_avg", "peak_p_still_peak_30pa", "peak_expected_weeks_reversion",
            "rh3_per_pa", "cross_verdict",
        ]].round(3).to_markdown(index=False))
    else:
        lines.append("_None._")

    out = ROOT / f"data/research/roster_deep_audit_league_full_{TODAY}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Done — {out}")
    print(f"  Slumpers with MC bounce:       {stat_slumpers['mc_p_bounce_median'].notna().sum()}")
    print(f"  Slumpers with Bayesian talent: {stat_slumpers['bayes_posterior_mu'].notna().sum()}")
    print(f"  Slumpers with hist comps:      {stat_slumpers['hist_n_comps'].notna().sum()}")
    print(f"  Peakers with decay curves:     {peakers['peak_p_still_peak_30pa'].notna().sum()}")


if __name__ == "__main__":
    main()

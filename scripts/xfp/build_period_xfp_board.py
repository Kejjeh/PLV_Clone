"""build_period_xfp_board — availability-aware, period-conditional xFP board.

Composes (2026-08-12, TDD build):
  rates       : xfp_rh3 (per-PA) / xfp_rp3 (per-start) — untouched, Rule 13
  volume      : lib.availability.ros_volume (IL-return overlay, else model)
  calendar    : lib.playoff_calendar (per-period windows, rotation starts,
                cap absorption) consuming resolve_period_meta + sp_cap_for_period
Outputs data/outputs/period_xfp_board.csv with xfp_p{20,21,22,23} + ros_total.

Board-level policy (documented, not hidden): a returning SP's ramp discount
(0.6 effective starts) is charged to his FIRST period back.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import app.espn_connector as ec  # noqa: E402
from app.espn_connector import get_all_teams, get_injury_details  # noqa: E402
from lib.availability import (ROTATION_LEN, SP_RAMP_DISCOUNT_STARTS,  # noqa: E402
                              pace_forward_ros_fp, ros_volume,
                              when_active_pa_rate)
from lib.period_meta import resolve_period_meta  # noqa: E402
from lib.pitcher_role import build_role_lookup, roster_buckets  # noqa: E402
from lib.playoff_calendar import (ROTATION_EFFICIENCY, cap_status,  # noqa: E402
                                  hitter_period_xfp, sp_starts_in_window)
from lib.playoff_reach import reach_probabilities, reach_weighted_total  # noqa: E402
from lib.title_equity import load_payload  # noqa: E402
from build_matchup_dashboard import fetch_schedules_by_team  # noqa: E402
from plv_clone.mlb_stats import _team_abbr_map  # noqa: E402
from plv_clone.utils.name_match import resolve_batter_id, resolve_pitcher_id  # noqa: E402

PERIODS = (20, 21, 22, 23)
TODAY = date.today()

# FA targets ride along with the roster (name, team hint, bucket)
FA_TARGETS = [("Oneil Cruz", "PIT", "H")]


from plv_clone.utils.name_match import safe_name_key as _norm  # noqa: E402


def main() -> None:
    league = ec._get_league()

    # ── period windows + caps from the existing seams
    windows: dict[int, tuple[date, date]] = {}
    caps: dict[int, int] = {}
    for p in PERIODS:
        meta = resolve_period_meta(league, p)
        lo = meta.get("week_start")
        hi = meta.get("week_end")
        if isinstance(lo, datetime):
            lo = lo.date()
        if isinstance(hi, datetime):
            hi = hi.date()
        windows[p] = (lo, hi)
        caps[p] = int(meta.get("cap", meta.get("sp_cap", 10)))
    print("periods:", {p: (str(w[0]), str(w[1]), f"cap {caps[p]}") for p, w in windows.items()})

    # ── P(you actually play period p). Summing p21+p22+p23 undiscounted asserts
    # P(reach the championship round) = 1.0; the sim says P(title) = 0.157, so
    # the deep rounds were being credited ~3-4x their expected weight and, being
    # the biggest buckets, were driving the sort (audit 2026-08-14).
    rp = reach_probabilities(load_payload())
    reach = rp["reach"]
    if reach is None:
        print(f"  WARN: reach weights UNAVAILABLE — {rp['note']}\n"
              f"        ros_reachwt_diag will be blank. NOT falling back to an "
              f"unweighted sum: that IS the assertion being avoided.",
              file=sys.stderr)
    else:
        print("reach P(play period): "
              + ", ".join(f"p{p}={reach[p]:.3f}" for p in PERIODS if p in reach)
              + f"   [{rp['status']}] {rp['note']}")

    # ── one schedule pull covering all windows, bucketed by MLB team id
    # Reach BACK before every SP's last start: sp_starts_in_window phases the
    # rotation off games elapsed since the last start, so a schedule beginning
    # at TODAY carries no phase at all and collapses every arm onto one lattice
    # (shipped defect, 2026-08-14). Forward consumers all re-filter on >= TODAY
    # or on an explicit window, so widening backwards is inert for them.
    sched_start = min(TODAY, windows[PERIODS[0]][0]) - timedelta(days=21)
    sched_end = windows[PERIODS[-1]][1]
    abbr_by_id = _team_abbr_map()
    id_by_abbr = {v: k for k, v in abbr_by_id.items()}
    all_ids = list(abbr_by_id)
    sched = fetch_schedules_by_team(all_ids, str(sched_start), str(sched_end))

    def team_dates(mlb_team_id: int) -> list[date]:
        out = []
        for g in sched.get(mlb_team_id, []):
            d = g.get("date") or g.get("block_date") or g.get("gameDate", "")[:10]
            if d:
                out.append(date.fromisoformat(str(d)[:10]))
        # One entry per TEAM GAME, not per calendar date: set() silently
        # collapsed doubleheaders, undercounting both PA opportunities and
        # rotation turns. Every consumer here counts/filters, so multiplicity
        # is what they want.
        return sorted(out)

    # ── model tables
    rh3 = pd.read_csv(_ROOT / "data/outputs/xfp_rh3_projections.csv")
    rp3 = pd.read_csv(_ROOT / "data/outputs/xfp_rp3_projections.csv")
    hv = pd.read_csv(_ROOT / "data/outputs/xfp_volume_projections.csv")
    # SP volume companion — the starter-side twin of hv. The headline uses it so
    # both buckets are built by the same pace-forward primitive (audit
    # 2026-08-14); the availability lattice stays in the *_diag columns.
    spv = pd.read_csv(_ROOT / "data/outputs/xfp_sp_volume_projections.csv")
    sc26 = pd.read_parquet(_ROOT / "data/research/xfp_cache/statcast_2026.parquet",
                           columns=["game_pk", "game_date", "at_bat_number",
                                    "batter", "pitcher"])
    rp3["_k"] = rp3["player_name"].map(
        lambda n: _norm(" ".join(reversed(str(n).split(", ")))) if ", " in str(n) else _norm(n))

    # ── assemble the player set: my roster + FA targets
    teams = get_all_teams()
    mine = teams[teams["team_name"] == "New York Ligers"].copy()
    inj = get_injury_details(list(mine["player_id"].astype(int)))
    ret_by_espn = {}
    if inj is not None and not inj.empty:
        for _, r in inj.iterrows():
            rd = r.get("return_date")
            if pd.notna(rd):
                ret_by_espn[int(r["player_id"])] = date.fromisoformat(str(rd)[:10])

    # Role truth, not ESPN's .position tag: build_role_lookup resolves
    # dual-eligible arms on real gamesStarted. Bucketing off the tag silently
    # dropped Detmers (tag 'RP', 23 starts) and under-counted rotation starts
    # against the period cap by 3.0 in p22 — fixed 2026-08-14.
    role_lookup = build_role_lookup(mine[mine["position"].isin(("SP", "RP", "P"))],
                                    rp3_df=rp3, rprs2_df=None)
    buckets = roster_buckets(mine, role_lookup)
    bucket_of = {n: b for b, names in buckets.items() for n in names}

    players = [(r["player_name"], r["pro_team"], bucket_of.get(r["player_name"], "H"),
                r["lineup_slot"], r["injury_status"], int(r["player_id"]), "MINE")
               for _, r in mine.iterrows()]

    fa_pool = league.free_agents(size=2000)          # pulled ONCE, not per target
    for nm, tm, bucket in FA_TARGETS:
        match = next((p for p in fa_pool if _norm(p.name) == _norm(nm)), None)
        if match is None:
            print(f"  WARN: FA target {nm!r} not in the FA pool — skipped "
                  f"(rostered elsewhere, or name drift)", file=sys.stderr)
            continue
        players.append((nm, tm, bucket, "FA", getattr(match, "injuryStatus", ""),
                        int(match.playerId), "FA-TARGET"))

    fa_ids = [x[5] for x in players if x[6] == "FA-TARGET" and x[5]]
    if fa_ids:
        inj_fa = get_injury_details(fa_ids)
        if inj_fa is not None and not inj_fa.empty:
            for _, r in inj_fa.iterrows():
                rd = r.get("return_date")
                if pd.notna(rd):
                    ret_by_espn[int(r["player_id"])] = date.fromisoformat(str(rd)[:10])

    rows, sp_period_arms = [], {p: [] for p in PERIODS}
    for nm, pro, pos, slot, inj_st, espn_id, tag in players:
        team_id = id_by_abbr.get(str(pro).upper())
        if team_id is None:
            # ESPN abbreviations differ from MLB in a few cases (Ari/AZ, ChW/CWS)
            fix = {"ARI": "AZ", "CHW": "CWS", "WSH": "WSH", "OAK": "ATH",
                   "SDP": "SD", "SFG": "SF", "TBR": "TB", "KCR": "KC"}.get(
                str(pro).upper(), None)
            team_id = id_by_abbr.get(fix) if fix else None
            if team_id is None:
                print(f"  WARN: no MLB team id for {nm} (pro_team={pro!r}) — "
                      f"period xFP will be zero", file=sys.stderr)
        tdates_all = team_dates(team_id) if team_id else []
        on_il = str(slot) == "IL" or "DL" in str(inj_st)
        ret = ret_by_espn.get(espn_id) if espn_id else None

        if str(pos) == "RP":
            continue      # true RPs are steady-state weekly assets; out of scope
        if str(pos) == "SP":
            k = _norm(nm)
            m = rp3[rp3["_k"] == k]
            if m.empty:
                print(f"  WARN: {nm} is role-SP but absent from rp3 — skipped",
                      file=sys.stderr)
                continue
            rate = float(m.iloc[0]["xfp_rp3_per_start"])
            qual = str(m.iloc[0]["data_quality_tag"])
            pid = resolve_pitcher_id(nm, team=str(pro), role="SP")
            d = sc26[sc26["pitcher"] == pid]
            last_start = (max(pd.to_datetime(d["game_date"]).dt.date)
                          if not d.empty else TODAY - timedelta(days=5))
            per_period, ramp_charged = {}, False
            for p in PERIODS:
                lo, hi = windows[p]
                if on_il and ret is not None:
                    # A team activates a starter to TAKE a rotation turn, so his
                    # first start is the first game back, then every 5th after.
                    # (Phasing off a faked "day before activation" pushed it to
                    # the 5th game back AND then charged the ramp — a double
                    # penalty that zeroed Glasnow/Pivetta in p20/p21.)
                    after_ret = [d_ for d_ in tdates_all if d_ >= ret]
                    lattice = after_ret[::ROTATION_LEN]
                    starts = float(sum(1 for d_ in lattice if lo <= d_ <= hi))
                    # Same lattice, same ~6% optimism — calibrate before the
                    # ramp discount so the two corrections compose in the
                    # documented order (audit 2026-08-14).
                    starts *= ROTATION_EFFICIENCY
                    if starts and not ramp_charged:
                        starts = max(0.0, starts - SP_RAMP_DISCOUNT_STARTS)
                        ramp_charged = True
                elif on_il:
                    starts = 0.0                          # IL, no return date: honest zero
                else:
                    starts = sp_starts_in_window(team_dates=tdates_all,
                                                 last_start_date=last_start,
                                                 window=(lo, hi)) * ROTATION_EFFICIENCY
                per_period[p] = starts
                if tag == "MINE":
                    sp_period_arms[p].append((rate, float(starts)))
            n_rem = len([d_ for d_ in tdates_all if d_ >= TODAY])
            sv = spv[spv["mlbam_id"] == pid] if pid else spv.iloc[0:0]
            gs_tg = float(sv.iloc[0]["proj_ros_gs_per_teamgame"]) if not sv.empty else None
            if gs_tg is None:
                print(f"  WARN: {nm} has no SP volume row — headline ros_total "
                      f"blank (period diagnostics still emitted)", file=sys.stderr)
            head = pace_forward_ros_fp(rate=rate, per_teamgame=gs_tg,
                                       team_games_remaining=n_rem)
            per_period_fp = {p: rate * per_period[p] for p in PERIODS}
            rw = (None if reach is None
                  else reach_weighted_total(per_period_fp, reach))
            rows.append({"player": nm, "bucket": "SP", "tag": tag, "inj": inj_st,
                         "mlbam": pid, "return_date_used": ret,
                         "snapshot_date": TODAY,
                         "model_pa_per_teamgame": round(gs_tg, 4) if gs_tg else None,
                         "team_games_remaining": n_rem,
                         "rate": round(rate, 2), "qual": qual,
                         # `qual` is the rp3 MODEL-quality tag; `vol_source` is
                         # the VOLUME construction. The prospective-overlay
                         # cohort filters on the latter, and conflating them in
                         # one column made the ledger ambiguous (audit
                         # 2026-08-14).
                         "vol_source": ("pace_forward_sp_volume" if gs_tg
                                        else "no_sp_volume"),
                         **{f"starts_p{p}": round(per_period[p], 1) for p in PERIODS},
                         **{f"xfp_p{p}_diag": round(per_period_fp[p], 1) for p in PERIODS},
                         # HEADLINE = pace-forward, same construction as hitters.
                         "ros_total": round(head, 1) if head is not None else None,
                         # The availability-lattice sum that USED to be the
                         # headline; Study C's gate failure applies to the
                         # method, not to one bucket.
                         "ros_overlay_diag": round(sum(per_period_fp.values()), 1),
                         "ros_reachwt_diag": round(rw, 1) if rw is not None else None})
        else:
            pid = resolve_batter_id(nm, team=str(pro))
            h = rh3[rh3["batter"] == pid] if pid else rh3.iloc[0:0]
            v = hv[hv["mlbam_id"] == pid] if pid else hv.iloc[0:0]
            if h.empty:
                continue
            rate = float(h.iloc[0]["xfp_rh3_per_pa"])
            model_pa_tg = float(v.iloc[0]["proj_ros_pa_per_teamgame"]) if not v.empty else 3.3
            wa = when_active_pa_rate(sc26, pid, min_games=10) if pid else None
            vol = ros_volume(
                {"bucket": "H", "status": "IL" if on_il else "ACTIVE",
                 "model_pa_per_teamgame": model_pa_tg,
                 "when_active_pa_per_game": wa if wa else model_pa_tg,
                 "return_date": ret},
                team_remaining_dates=[d_ for d_ in tdates_all if d_ >= TODAY],
                today=TODAY)
            pa_tg = (vol["proj_ros_pa"] / max(1, len([d_ for d_ in tdates_all
                                                      if d_ >= TODAY])))
            eff_rate_pa = wa if (on_il and ret and wa) else model_pa_tg
            per_period = {}
            for p in PERIODS:
                lo, hi = windows[p]
                w_dates = [d_ for d_ in tdates_all if lo <= d_ <= hi]
                per_period[p] = hitter_period_xfp(
                    rate_fp_per_pa=rate, pa_per_teamgame=eff_rate_pa,
                    team_dates_in_window=w_dates,
                    return_date=ret if on_il else None)
            n_rem = len([d_ for d_ in tdates_all if d_ >= TODAY])
            head = pace_forward_ros_fp(rate=rate, per_teamgame=model_pa_tg,
                                       team_games_remaining=n_rem)
            rw = (None if reach is None
                  else reach_weighted_total({p: per_period[p] for p in PERIODS},
                                            reach))
            rows.append({"player": nm, "bucket": "H", "tag": tag, "inj": inj_st,
                         # settle-protocol fields (prereg_overlay_prospective):
                         # the ledger must carry the return date USED and an
                         # mlbam key, or the cohort cannot be scored later.
                         "mlbam": pid, "return_date_used": ret,
                         "snapshot_date": TODAY,
                         "model_pa_per_teamgame": round(model_pa_tg, 3),
                         "team_games_remaining": n_rem,
                         "rate": round(rate, 3), "qual": vol["source"],
                         "vol_source": vol["source"],
                         "flags": ",".join(vol["flags"]),
                         "when_active_pa": round(wa, 2) if wa else None,
                         # HEADLINE = the shipped pace-forward construction.
                         # Study C (2026-08-12) FAILED the overlay's auto-ship
                         # gate; availability-aware numbers are *_diag only.
                         "ros_total": round(head, 1) if head is not None else None,
                         **{f"xfp_p{p}_diag": round(per_period[p], 1) for p in PERIODS},
                         "ros_overlay_diag": round(vol["proj_ros_pa"] * rate, 1),
                         "ros_reachwt_diag": round(rw, 1) if rw is not None else None})

    out = pd.DataFrame(rows).sort_values(["bucket", "ros_total"], ascending=[True, False])
    dest = _ROOT / "data/outputs/period_xfp_board.csv"
    out.to_csv(dest, index=False)
    # Prospective ledger (prereg_overlay_prospective_2026-08-12.md): dated,
    # append-only snapshots so the ESPN-return-date overlay variant can be
    # settled against realized PA — the follow-up Study C could not run
    # historically (no archived ESPN return dates).
    snap_dir = _ROOT / "data/research/validation_runs/overlay_prospective"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap = snap_dir / f"predictions_{TODAY.isoformat()}.csv"
    required = {"player", "bucket", "mlbam", "return_date_used", "snapshot_date",
                "qual", "vol_source", "model_pa_per_teamgame",
                "team_games_remaining", "ros_total", "ros_overlay_diag",
                "ros_reachwt_diag"}
    missing = required - set(out.columns)
    if missing:
        # Fail loudly: a ledger missing settle fields is worse than no ledger,
        # because it looks like evidence and cannot be scored.
        raise SystemExit(f"ledger schema incomplete, refusing to write: {sorted(missing)}")
    if not snap.exists():
        out.to_csv(snap, index=False)
        print(f"prospective ledger snapshot -> {snap}")
    print("NOTE: xfp_p*_diag / ros_overlay_diag / ros_reachwt_diag are "
          "DIAGNOSTIC (Study C gate failed for auto-ship); headline ros_total "
          "is pace-forward (rate x volume x remaining team games) for BOTH "
          "buckets. ros_reachwt_diag additionally discounts each playoff "
          "period by P(you play it).")
    pd.set_option("display.width", 300)
    pd.set_option("display.max_columns", 40)
    print(out.to_string(index=False))

    print("\n=== MY SP PERIOD TOTALS (cap-absorbed vs raw) ===")
    absorbed_by_p = {}
    for p in PERIODS:
        st = cap_status(sp_period_arms[p], cap=caps[p])
        absorbed_by_p[p] = st["absorbed"]
        w = f", reach {reach[p]:.2f}" if reach and p in reach else ""
        tail = (f"BINDING, spilling {st['starts'] - st['cap']:.1f} starts "
                f"= {st['lost_fp']:.0f} FP" if st["binding"]
                else f"slack, {st['room']:.1f} starts of room")
        print(f"  p{p}: {st['starts']:.1f} starts vs cap {caps[p]} -> raw "
              f"{st['raw']:.0f} FP, cap-absorbed {st['absorbed']:.0f} FP{w} "
              f"({tail})")
    if reach:
        tot = reach_weighted_total(absorbed_by_p, reach)
        print(f"  reach-weighted cap-absorbed rotation FP: {tot:.0f} "
              f"(vs {sum(absorbed_by_p.values()):.0f} unweighted)")
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main()

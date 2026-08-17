"""Build the unified xFP dashboard (pitchers + hitters + ESPN My Team).

Generates a self-contained HTML file with React+Babel inline, embedded
pitcher AND hitter projection data, five tabs (My Team / Pitchers /
Hitters / Analysis / Model Info), quadrant charts, favorites in
localStorage, and PLV color/typography.

The "My Team" tab pulls roster + ESPN data from the PLV process_report
dashboard's MY_TEAM payload. SPs are matched to xFP V11 and hitters
to xFP H2 so you can compare your full roster to the league leaderboards.

Outputs:
  - data/outputs/xfp_dashboard.html
  - xfp-model/docs/index.html  (byte-identical copy for GitHub Pages)
"""
from __future__ import annotations
import json
import re
import shutil
import unicodedata
from datetime import date
from pathlib import Path

import joblib
import pandas as pd
from plv_clone.league_config import MY_TEAM_NAME

ROOT = Path(__file__).resolve().parents[2]
# V12 is now the primary pitcher projection (V11 + il_60_stints_lag1).
# V11 stays in the dataset as a comparison column.
V12_PROJ_CSV = ROOT / 'data' / 'outputs' / 'xfp_v12_projections.csv'
PROJ_CSV = ROOT / 'data' / 'outputs' / 'xfp_v11_projections.csv'  # legacy fallback
MULTI_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'sp_multiyr_2015_2025.csv'
MODEL_PKL = ROOT / 'data' / 'models' / 'xfp_v11_pipeline.pkl'
V12_MODEL_PKL = ROOT / 'data' / 'models' / 'xfp_v12_pipeline.pkl'
H2_PROJ_CSV = ROOT / 'data' / 'outputs' / 'xfp_h2_projections.csv'
H2_MODEL_PKL = ROOT / 'data' / 'models' / 'xfp_h2_pipeline.pkl'
# Rest-of-Season (within-season) projections — added 2026-05-06 for in-season use
RH1_PROJ_CSV = ROOT / 'data' / 'outputs' / 'xfp_rh3_projections.csv'
RP1_PROJ_CSV = ROOT / 'data' / 'outputs' / 'xfp_rp3_projections.csv'
# Reliever projections — added 2026-05-06
# RP-RS2 (current): RP-RS1 + statcast-derived in-season role-usage features
# (gf_pct_to, sv_per_g_to, hld_per_g_to). Stratified-validated +0.033 overall,
# +0.074 on role-change subset.
RP_RPRS1_PROJ_CSV = ROOT / 'data' / 'outputs' / 'xfp_rprs2_projections.csv'  # in-season RoS
RP_RPS1_PROJ_CSV  = ROOT / 'data' / 'outputs' / 'xfp_rps1_projections.csv'   # cross-year
PLV_HTML = ROOT / 'data' / 'outputs' / 'process_report_2026.html'
OUT_PRIMARY = ROOT / 'data' / 'outputs' / 'xfp_dashboard.html'
OUT_DOCS = ROOT / 'xfp-model' / 'docs' / 'index.html'


# ─── Name normalization ───────────────────────────────────────────────────────

# Name join key — OWNER: plv_clone.utils.name_match.safe_name_key. Order-
# PRESERVING, space-separated ("kyle schwarber"), collapses curly-vs-straight
# apostrophes, C.J./CJ and hyphens. NEVER re-derive locally: a local copy
# mis-keyed Ryan O'Hearn's U+2019 apostrophe and printed an opponent's player
# as a FREE AGENT (2026-07-28). NOT join_key — that one sorts tokens and drops
# separators, which is a different (order-independent) key.
from plv_clone.utils.name_match import safe_name_key as _norm  # noqa: E402


def xfp_name_key(name: str) -> tuple[str, str]:
    """`Verlander, Justin` → (`verlander`, `justin`)."""
    if ',' in name:
        last, first = name.split(',', 1)
    else:
        parts = name.strip().split()
        last, first = parts[-1], ' '.join(parts[:-1])
    return (_norm(last), _norm(first))


def plv_name_key(name: str) -> tuple[str, str]:
    """`Max Fried` → (`fried`, `max`)."""
    parts = name.strip().split()
    if len(parts) < 2:
        return (_norm(name), '')
    return (_norm(parts[-1]), _norm(' '.join(parts[:-1])))


def find_xfp_record(plv_name: str, by_key: dict, *, mlbam=None,
                    by_id: dict | None = None) -> dict | None:
    """Match an ESPN payload row against the xFP records.

    ID FIRST (review round 2, 2026-07-30): when the payload row carries an
    mlbId and an id-index was built, the match is by id — the name dict is
    keyed on bare (last, first) and last-write-wins, so with two same-name
    players it holds only ONE of them and a name join returns whichever
    survived (the wrong Max Muncy when Josh rosters the other). The name path
    below remains for id-less rows only.

    Name path: strict (last, first) match after accent-stripping
    normalization. Fallback accepts a unique last-name match only when the
    first names share a 3-char prefix — this catches `Cam Schlittler ↔
    Schlittler, Cam` while rejecting the `Robert Suarez ↔ Ranger Suarez`
    collision.
    """
    if mlbam is not None and by_id:
        try:
            rec = by_id.get(int(mlbam))
        except (TypeError, ValueError):
            rec = None
        if rec is not None:
            return rec
    last, first = plv_name_key(plv_name)
    rec = by_key.get((last, first))
    if rec is not None:
        return rec
    candidates = []
    for k, v in by_key.items():
        if k[0] != last:
            continue
        a, b = first or '', k[1] or ''
        n = min(len(a), len(b), 3)
        if n > 0 and a[:n] == b[:n]:
            candidates.append((k, v))
    return candidates[0][1] if len(candidates) == 1 else None


# ─── ESPN payload extraction (from PLV dashboard) ─────────────────────────────

def _clean_team_hint(v):
    """Normalize a record's team field to a usable hint or None (NaN-safe)."""
    if v is None or (isinstance(v, float) and v != v):
        return None
    s = str(v).strip()
    return s or None


def _label_roster_status(records: list[dict], name_key_fn,
                          my_team_name: str = MY_TEAM_NAME) -> None:
    """In-place: set rec['roster'] to 'mine' | 'taken' | 'fa' based on ESPN league rosters.

    Default-fall-through is 'fa'. Player on my team -> 'mine'.
    Player on any other team -> 'taken'.

    Join contract (audit C5, 2026-07-30): roster identity is
    (safe_name_key, team) via build_safe_name_index / safe_lookup — never a
    bare name key, which last-write-wins collapsed the two Max Muncy mlbIds
    into one roster label on the shipped dashboard. A record whose MLB team
    contradicts the rostered player's team is the OTHER same-name player and
    stays 'fa'; a same-key roster pair that no team tiebreak can separate
    raises at build time instead of mislabelling all of them. `name_key_fn`
    is retained for signature compatibility but no longer drives the join.
    """
    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT))
        from plv_clone.league_state import LeagueState
        teams = LeagueState().all_teams()
    except Exception as e:
        print(f'  [_label_roster_status] ESPN unavailable, defaulting to fa: {e}')
        return  # ESPN unavailable; leave existing labels

    from plv_clone.utils.name_match import (
        build_safe_name_index, safe_lookup, safe_name_key, team_key)

    pro = teams['pro_team'] if 'pro_team' in teams.columns else None
    idx = build_safe_name_index(teams['player_name'], pro)

    # Build-time assertion: two rostered players may share a name key only
    # when a team tiebreak can separate them — otherwise every same-key
    # record's label would be a guess.
    for k, cands in idx.items():
        if len(cands) > 1:
            tks = [t for _lbl, t in cands]
            if None in tks or len(set(tks)) != len(tks):
                raise ValueError(
                    f"_label_roster_status: {len(cands)} rostered players "
                    f"collapse to name key {k!r} without a team tiebreak "
                    f"({tks}) — refusing to label; fix the roster feed")

    for rec in records:
        if rec.get('roster') == 'mine':
            continue  # preserve my-team merge's existing label
        nm = rec.get('name') or rec.get('player_name') or ''
        rec_team = (_clean_team_hint(rec.get('team'))
                    or _clean_team_hint(rec.get('proTeam')))
        cands = idx.get(safe_name_key(nm))
        lbl = None
        if cands and len(cands) == 1:
            lbl, cand_tk = cands[0]
            # Same name, but a DIFFERENT MLB team on both sides: this record
            # is the other same-name player, not the rostered one.
            if (rec_team is not None and cand_tk is not None
                    and team_key(rec_team) != cand_tk):
                lbl = None
        elif cands:
            lbl = safe_lookup(nm, idx, team=rec_team)
            if lbl is None:
                print(f"  [_label_roster_status] AMBIGUOUS: {nm!r} matches "
                      f"{len(cands)} rostered players and record team "
                      f"{rec_team!r} does not separate them — leaving 'fa'")
        if lbl is None:
            rec['roster'] = 'fa'
            continue
        team = teams.loc[lbl, 'team_name']
        if team == my_team_name:
            rec['roster'] = 'mine'
        else:
            rec['roster'] = 'taken'
            rec['taken_by_team'] = team


def extract_my_team() -> dict | None:
    if not PLV_HTML.exists():
        return None
    s = PLV_HTML.read_text(encoding='utf-8')
    m = re.search(r'window\.MY_TEAM\s*=\s*(\{.+?\n\});', s, re.DOTALL)
    if not m:
        return None
    return json.loads(m.group(1))


# ─── Records ──────────────────────────────────────────────────────────────────

def build_records() -> tuple[list[dict], dict, list[dict]]:
    proj = pd.read_csv(PROJ_CSV)
    multi = pd.read_csv(MULTI_CSV)
    latest = (
        multi.sort_values(['pitcher', 'year'])
             .groupby('pitcher')
             .tail(1)[['pitcher', 'swstr_pct']]
    )
    proj = proj.merge(latest, on='pitcher', how='left')

    # V12 — the new primary projection (V11 + il_60_stints_lag1).
    # Merge xfp_v12 + il_60_stints_lag1 as new columns on top of the V11 base
    # so existing fields (stuff_xfp, ip_premium, ip_trend) still flow through.
    if V12_PROJ_CSV.exists():
        v12 = pd.read_csv(V12_PROJ_CSV)
        v12_keep = ['pitcher', 'xfp_v12', 'il_60_stints_lag1', 'rank_v12']
        v12_keep = [c for c in v12_keep if c in v12.columns]
        proj = proj.merge(v12[v12_keep], on='pitcher', how='left')

    # RP1 — Rest-of-Season FP/start projection (in-season prediction).
    # Distinct from V12: V12 predicts year T+1 from full year T data;
    # RP1 predicts the REMAINDER of year T from year-T-to-date features.
    if RP1_PROJ_CSV.exists():
        rp1 = pd.read_csv(RP1_PROJ_CSV)
        rp1_keep = ['pitcher', 'xfp_rp3_per_start', 'gs_to', 'fp_per_start_to',
                    'fp_per_start_last21', 'recency_form_gap',
                    'xfp_rp3_p25', 'xfp_rp3_p75', 'xfp_rp3_sigma',
                    'next_opp_team', 'next2_avg_bat_index',
                    'xfp_rp3_per_start_sched', 'is_on_il_at_split',
                    'replacement_xfp_per_start', 'replacement_delta', 'signal',
                    'prior_source', 'data_quality_tag', 'player_name',
                    'slump_pct_rank', 'slump_n_comparable', 'slump_bounce_pct',
                    'slump_next_rate', 'slump_delta']
        rp1_keep = [c for c in rp1_keep if c in rp1.columns]
        # Rename rp1's player_name so it doesn't collide; we'll use it as a fallback
        rp1_subset = rp1[rp1_keep].rename(columns={'player_name': 'rp1_player_name'})
        proj = proj.merge(rp1_subset, on='pitcher', how='outer')
        if 'xfp_rp3_per_start' in proj.columns:
            proj = proj.rename(columns={'xfp_rp3_per_start': 'xfp_rp1_per_start'})
        # For rookie rows that only exist in rp1 (MiLB-derived), backfill name
        if 'rp1_player_name' in proj.columns:
            proj['player_name'] = proj['player_name'].fillna(proj['rp1_player_name'])

    def num(v, dp=None):
        if pd.isna(v):
            return None
        v = float(v)
        return round(v, dp) if dp is not None else v

    records = []
    for _, r in proj.iterrows():
        # Skip rows with no pitcher id (corrupt) or no usable name
        if pd.isna(r.get('pitcher')):
            continue
        if pd.isna(r.get('player_name')):
            # Rookie / minor-leaguer with no MLB name source — drop quietly
            continue
        gs_val = int(r['gs_2026']) if pd.notna(r.get('gs_2026')) else None
        fp_actual_val = num(r.get('fp_per_start_actual_2026'), 2)
        # Cumulative FP for the season (≥ 5 GS gate so the number is meaningful).
        fp_total_val = (
            round(gs_val * fp_actual_val, 1)
            if gs_val is not None and gs_val >= 5 and fp_actual_val is not None
            else None
        )
        # V12 is the new primary projection. Falls back to V11 for pitchers V12 doesn't cover.
        xfp_v11_val = num(r.get('xfp_v11'), 2) if pd.notna(r.get('xfp_v11')) else None
        xfp_primary = num(r.get('xfp_v12'), 2) if pd.notna(r.get('xfp_v12')) else xfp_v11_val
        # Residual: how far off the primary projection is from per-start actual.
        # Positive = over-projection, Negative = pitcher outperforming.
        residual_val = (
            round(xfp_primary - fp_actual_val, 2)
            if fp_actual_val is not None and gs_val is not None and gs_val >= 5 and xfp_primary is not None
            else None
        )
        # IL feature value for transparency
        il60 = int(r['il_60_stints_lag1']) if pd.notna(r.get('il_60_stints_lag1')) else 0
        # RP1 — Rest-of-Season prediction (within-season). Different from xfpV12
        # which is a year-over-year season-aggregate projection.
        ros_per_start = num(r.get('xfp_rp1_per_start'), 2) if pd.notna(r.get('xfp_rp1_per_start')) else None
        gs_to_val = int(r['gs_to']) if pd.notna(r.get('gs_to')) else None
        # RoS-decision-layer columns (R3): CI bounds, schedule adjustment, signal
        ros_p25 = num(r.get('xfp_rp3_p25'), 2)
        ros_p75 = num(r.get('xfp_rp3_p75'), 2)
        ros_sched = num(r.get('xfp_rp3_per_start_sched'), 2)
        ros_recency_gap = num(r.get('recency_form_gap'), 2)
        ros_repl = num(r.get('replacement_xfp_per_start'), 2)
        ros_repl_delta = num(r.get('replacement_delta'), 2)
        next_opp = r.get('next_opp_team') if pd.notna(r.get('next_opp_team')) else None
        next2_idx = num(r.get('next2_avg_bat_index'), 3)
        _il_val = r.get('is_on_il_at_split')
        on_il = bool(int(_il_val)) if pd.notna(_il_val) else False
        signal = r.get('signal') if pd.notna(r.get('signal')) else 'hold'
        prior_source = r.get('prior_source') if pd.notna(r.get('prior_source')) else None
        dq_tag = r.get('data_quality_tag') if pd.notna(r.get('data_quality_tag')) else None
        slump_pct = num(r.get('slump_pct_rank'), 1)
        slump_n = int(r['slump_n_comparable']) if pd.notna(r.get('slump_n_comparable')) else None
        slump_bounce = num(r.get('slump_bounce_pct'), 1)
        slump_next = num(r.get('slump_next_rate'), 3)
        slump_delta = num(r.get('slump_delta'), 3)
        records.append({
            'mlbId': int(r['pitcher']),
            'name': r['player_name'],
            'xfpV12': xfp_primary,
            'xfpV11': xfp_v11_val,
            'xfpV85': num(r['xfp_v8_5'], 2),
            'xfpRoS': ros_per_start,        # Rest-of-Season FP/start projection
            'xfpRoSp25': ros_p25,
            'xfpRoSp75': ros_p75,
            'xfpRoSSched': ros_sched,
            'recencyGap': ros_recency_gap,
            'nextOpp': next_opp,
            'next2OppIdx': next2_idx,
            'onIL': on_il,
            'replXfp': ros_repl,
            'replDelta': ros_repl_delta,
            'signal': signal,
            'priorSource': prior_source,    # 'mlb_lag' | 'milb_translation' | 'league_mean'
            'dataQualityTag': dq_tag,       # 'marcel_il' etc — LOW-CONF badge (gotcha #1)
            'slumpPct': slump_pct,          # 0-100; lower = rarer in own career
            'slumpN': slump_n,
            'slumpBouncePct': slump_bounce,
            'slumpNextRate': slump_next,
            'slumpDelta': slump_delta,
            'gsToDate': gs_to_val,          # starts already made
            'deltaV12V11': round(xfp_primary - xfp_v11_val, 2)
                if (xfp_primary is not None and xfp_v11_val is not None) else None,
            'il60Lag1': il60,
            'delta': residual_val,
            'fpTotal': fp_total_val,
            'stuffXfp': num(r.get('stuff_xfp'), 2),
            'ipPremium': num(r.get('ip_premium'), 2),
            'ipTrend': r.get('ip_trend'),
            'kPct': num(r.get('k_pct_2026'), 3),
            'swstrPct': num(r.get('swstr_pct'), 3),
            'gs': gs_val,
            'fpActual': fp_actual_val,
            'hasFG': bool(r['v11_has_pitching_plus']) if pd.notna(r.get('v11_has_pitching_plus')) else False,
            'rollingIp': num(r.get('rolling_ip_last5'), 2),
            # ESPN fields (filled from MY_TEAM where available)
            'roster': 'fa',             # 'mine' | 'taken' | 'fa' (set finally by _label_roster_status)
            'espnPos': None,
            'proTeam': None,
            'pctOwned': None,
            'fpProjEspn': None,
            'fpTotalEspn': None,
            'fpPerGameEspn': None,
            'gpEspn': None,
        })

    # Compute SP projected RoS TOTAL FP = xfpRoS × estimated remaining starts.
    # Estimated remaining starts uses elapsed-fraction extrapolation, calibrated
    # against historical actuals. Empirical calibration ratios (actual/formula),
    # measured on 2018-2025 data:
    #   split  formula            actual ratio
    #   30     gs × 5.17           0.87  (formula over-predicts)
    #   60     gs × 2.08           1.08  (slight under)
    #   90     gs × 1.06           1.29
    #   120    gs × 0.54           1.66  (formula under-predicts; surviving SPs stay healthy)
    # We interpolate between these for the current elapsed_days.
    from datetime import date as _date
    season_start = pd.Timestamp('2026-03-26')
    elapsed_days = max((pd.Timestamp(_date.today()) - season_start).days, 1)
    season_days = 185
    fraction_played = min(elapsed_days / season_days, 0.95)
    raw_factor = (1.0 / fraction_played - 1.0)

    # Calibration interpolation table
    _calib_table = [(30, 0.87), (60, 1.08), (90, 1.29), (120, 1.66)]
    if elapsed_days <= 30:
        calib = 0.87
    elif elapsed_days >= 120:
        calib = 1.66
    else:
        for (a, ca), (b, cb) in zip(_calib_table[:-1], _calib_table[1:]):
            if a <= elapsed_days <= b:
                calib = ca + (cb - ca) * (elapsed_days - a) / (b - a)
                break
        else:
            calib = 1.0
    sp_remaining_factor = raw_factor * calib

    for rec in records:
        gs = rec.get('gsToDate')
        ros = rec.get('xfpRoS')
        if gs is None or ros is None or gs == 0:
            rec['rosTotalFp'] = None
            rec['rosTotalFpSched'] = None
        else:
            # Cap at max plausible remaining starts (32 max minus what's done)
            rem_starts = min(gs * sp_remaining_factor, max(32 - gs, 0))
            rec['rosTotalFp'] = round(ros * rem_starts, 1)
            sched = rec.get('xfpRoSSched')
            rec['rosTotalFpSched'] = round(sched * rem_starts, 1) if sched is not None else None

    # Position-aware total replacement: top-60 SPs by rosTotalFp = replacement
    sp_with_total = [r for r in records if r.get('rosTotalFp') is not None]
    sp_with_total.sort(key=lambda r: -r['rosTotalFp'])
    from league_config import SP_REPLACEMENT_RANK as SP_REPL_RANK
    if len(sp_with_total) >= SP_REPL_RANK:
        sp_repl_total = float(sp_with_total[SP_REPL_RANK - 1]['rosTotalFp'])
    elif sp_with_total:
        sp_repl_total = float(sp_with_total[-1]['rosTotalFp'])
    else:
        sp_repl_total = 0.0
    for rec in records:
        if rec.get('rosTotalFp') is not None:
            rec['rosReplTotal'] = round(sp_repl_total, 1)
            rec['rosReplDeltaTotal'] = round(rec['rosTotalFp'] - sp_repl_total, 1)
        else:
            rec['rosReplTotal'] = None
            rec['rosReplDeltaTotal'] = None

    # Default SP sort = projected RoS TOTAL FP (matches hitter behaviour).
    records.sort(key=lambda x: -(x['rosTotalFp'] if x['rosTotalFp'] is not None else -1))
    for i, rec in enumerate(records):
        rec['rank'] = i + 1

    # Reliever records (separate model — RP-RS1 RoS + RP-S1 cross-year)
    rp_records = build_reliever_records()
    rp_by_key: dict[tuple[str, str], dict] = {xfp_name_key(r['name']): r for r in rp_records}
    rp_by_id: dict[int, dict] = {r['mlbId']: r for r in rp_records if r.get('mlbId')}

    # ESPN merge — id-index first (the name dict is lossy on shared names)
    by_key: dict[tuple[str, str], dict] = {xfp_name_key(r['name']): r for r in records}
    by_id: dict[int, dict] = {r['mlbId']: r for r in records if r.get('mlbId')}

    my_team_raw = extract_my_team()
    my_team_payload: dict = {'teamName': None, 'pitchers': []}

    if my_team_raw:
        my_team_payload['teamName'] = my_team_raw.get('teamName')
        for p in my_team_raw.get('pitchers', []):
            espn_pos = p.get('espnPos') or ''
            role = 'SP' if 'SP' in espn_pos else ('RP' if 'RP' in espn_pos else (espn_pos or '—'))
            # Match SPs against the SP xFP universe; RPs against the RP universe.
            xfp_rec = (find_xfp_record(p['name'], by_key, mlbam=p.get('mlbId'),
                                       by_id=by_id)
                       if role == 'SP' else None)
            rp_rec  = (find_xfp_record(p['name'], rp_by_key, mlbam=p.get('mlbId'),
                                       by_id=rp_by_id)
                       if role == 'RP' else None)
            if xfp_rec is not None:
                xfp_rec['roster'] = 'mine'
                xfp_rec['espnPos'] = espn_pos
                xfp_rec['proTeam'] = p.get('proTeam')
                xfp_rec['pctOwned'] = p.get('pctOwned') if isinstance(p.get('pctOwned'), (int, float)) else None
                xfp_rec['fpProjEspn'] = p.get('fpProj') if isinstance(p.get('fpProj'), (int, float)) else None
                xfp_rec['fpTotalEspn'] = p.get('fpTotal') if isinstance(p.get('fpTotal'), (int, float)) else None
                xfp_rec['fpPerGameEspn'] = p.get('fpPerGame') if isinstance(p.get('fpPerGame'), (int, float)) else None
                xfp_rec['gpEspn'] = p.get('gp') if isinstance(p.get('gp'), int) else None
            if rp_rec is not None:
                rp_rec['roster'] = 'mine'
                rp_rec['espnPos'] = espn_pos
                rp_rec['proTeam'] = p.get('proTeam')
                rp_rec['pctOwned'] = p.get('pctOwned') if isinstance(p.get('pctOwned'), (int, float)) else None

            my_team_payload['pitchers'].append({
                'name': p['name'],
                'role': role,
                'espnPos': espn_pos,
                'proTeam': p.get('proTeam'),
                'pctOwned': p.get('pctOwned') if isinstance(p.get('pctOwned'), (int, float)) else None,
                'gp': p.get('gp') if isinstance(p.get('gp'), int) else None,
                'fpTotal': p.get('fpTotal') if isinstance(p.get('fpTotal'), (int, float)) else None,
                'fpProj': p.get('fpProj') if isinstance(p.get('fpProj'), (int, float)) else None,
                'fpPerGame': p.get('fpPerGame') if isinstance(p.get('fpPerGame'), (int, float)) else None,
                'mlbId': xfp_rec['mlbId'] if xfp_rec else (rp_rec['mlbId'] if rp_rec else None),
                'xfpV11': xfp_rec['xfpV11'] if xfp_rec else None,
                'xfpRank': xfp_rec['rank'] if xfp_rec else (rp_rec['rank'] if rp_rec else None),
                'kPct': xfp_rec['kPct'] if xfp_rec else None,
                'ipTrend': xfp_rec['ipTrend'] if xfp_rec else None,
                'fpActual': xfp_rec['fpActual'] if xfp_rec else None,
                'gs': xfp_rec['gs'] if xfp_rec else None,
                # RP-specific model output (RP-RS1)
                'rpRoSFp': rp_rec['rpRoSFp'] if rp_rec else None,
                'rpFullYear': rp_rec['rpFullYear'] if rp_rec else None,
                'rpReplDelta': rp_rec['rpReplDelta'] if rp_rec else None,
                'rpSignal': rp_rec['rpSignal'] if rp_rec else None,
                'rpRolePrior': rp_rec['rpRolePrior'] if rp_rec else None,
            })

    # Tag every record with league-wide roster status (mine / taken / fa)
    _label_roster_status(records, xfp_name_key)
    _label_roster_status(rp_records, xfp_name_key)
    return records, my_team_payload, rp_records


def build_reliever_records() -> list[dict]:
    """Build reliever records from RP-RS1 (RoS) + RP-S1 (cross-year) projections.

    Returns a list of dicts with model output for each covered RP. Used to
    populate dashboard My-Team RP rows and the reliever leaderboard.
    """
    if not RP_RPRS1_PROJ_CSV.exists():
        return []
    ros = pd.read_csv(RP_RPRS1_PROJ_CSV)
    cy = pd.read_csv(RP_RPS1_PROJ_CSV) if RP_RPS1_PROJ_CSV.exists() else pd.DataFrame()

    if not cy.empty:
        cy_keep = cy[['pitcher', 'xfp_rps1_total']].rename(
            columns={'xfp_rps1_total': 'xfp_cross_year'})
        ros = ros.merge(cy_keep, on='pitcher', how='left')

    def num(v, dp=None):
        if pd.isna(v):
            return None
        v = float(v)
        return round(v, dp) if dp is not None else v

    records = []
    for _, r in ros.iterrows():
        records.append({
            'mlbId':         int(r['pitcher']),
            'name':          r.get('name_api') or '',
            'rank':          int(r['rank']),
            'rpRolePrior':   r.get('role_lag1'),
            'svPriorYr':     int(r['sv_lag1']) if pd.notna(r.get('sv_lag1')) else None,
            'hldPriorYr':    int(r['hld_lag1']) if pd.notna(r.get('hld_lag1')) else None,
            'gToDate':       int(r['g_to']) if pd.notna(r.get('g_to')) else None,
            'sv2026':        int(r['sv_2026']) if pd.notna(r.get('sv_2026')) else None,
            'hld2026':       int(r['hld_2026']) if pd.notna(r.get('hld_2026')) else None,
            'fpActual':      num(r.get('fp_actual_2026'), 1),
            'rpFullYear':    num(r.get('xfp_full_year'), 1),
            'rpFullYearP25': num(r.get('xfp_p25'), 1),
            'rpFullYearP75': num(r.get('xfp_p75'), 1),
            'rpRoSFp':       num(r.get('xfp_ros'), 1),
            'rpRoSFpP25':    num(r.get('xfp_ros_p25'), 1),
            'rpRoSFpP75':    num(r.get('xfp_ros_p75'), 1),
            'rpReplXfp':     num(r.get('replacement_xfp'), 1),
            'rpReplDelta':   num(r.get('replacement_delta'), 1),
            'rpSignal':      r.get('signal') or 'hold',
            'rpCrossYear':   num(r.get('xfp_cross_year'), 1),
            'roster':       'fa',
            'espnPos':       None,
            'proTeam':       None,
            'pctOwned':      None,
        })
    return records


def build_hitter_records() -> tuple[list[dict], list[dict]]:
    """Returns (hitter_records, my_team_hitter_payload)."""
    if not H2_PROJ_CSV.exists():
        return [], []

    proj = pd.read_csv(H2_PROJ_CSV)

    # RH1 — Rest-of-Season FP/PA. Merge alongside H2 (year-T+1 projection).
    if RH1_PROJ_CSV.exists():
        rh1 = pd.read_csv(RH1_PROJ_CSV)
        rh1_keep = ['batter', 'xfp_rh3_per_pa', 'pa_to', 'pa_last21',
                    'xfp_rh3_p25', 'xfp_rh3_p75', 'xfp_rh3_sigma',
                    'recency_form_gap',
                    'expected_pa_remaining', 'expected_total_fp_remaining',
                    'replacement_xfp_per_pa', 'replacement_delta', 'signal',
                    'slump_pct_rank', 'slump_n_comparable', 'slump_bounce_pct',
                    'slump_next_rate', 'slump_delta']
        rh1_keep = [c for c in rh1_keep if c in rh1.columns]
        proj = proj.merge(rh1[rh1_keep], on='batter', how='left')
        if 'xfp_rh3_per_pa' in proj.columns:
            proj = proj.rename(columns={'xfp_rh3_per_pa': 'xfp_rh1_per_pa'})

    def num(v, dp=None):
        if pd.isna(v):
            return None
        v = float(v)
        return round(v, dp) if dp is not None else v

    records: list[dict] = []
    for _, r in proj.iterrows():
        # FP total = xfp per PA × current PA (counting stat for the season so far)
        # rather than projecting forward — matches what hitter_points UI shows
        pa_2026 = num(r.get('pa_2026'))
        fp_actual_per_pa = num(r.get('fp_per_pa_actual_2026'), 4)
        fp_total_actual = num(r.get('fp_total_actual_2026'), 1)
        # Residual: positive = H2 over-projects, negative = hitter outperforming
        delta = (
            round(num(r['xfp_h2_per_pa'], 4) - fp_actual_per_pa, 4)
            if fp_actual_per_pa is not None and pa_2026 is not None and pa_2026 >= 50
            else None
        )
        # RoS hitter projection (xfp_rh1) — within-season prediction
        ros_per_pa = num(r.get('xfp_rh1_per_pa'), 4) if pd.notna(r.get('xfp_rh1_per_pa')) else None
        ros_per_game = round(ros_per_pa * 3.5, 2) if ros_per_pa is not None else None
        pa_to_date = int(r['pa_to']) if pd.notna(r.get('pa_to')) else None
        # R3 decision-layer: CIs, recency form, replacement-level deltas, PA-aware total
        ros_p25 = num(r.get('xfp_rh3_p25'), 4)
        ros_p75 = num(r.get('xfp_rh3_p75'), 4)
        recency_gap = num(r.get('recency_form_gap'), 4)
        repl_xfp = num(r.get('replacement_xfp_per_pa'), 4)
        repl_delta = num(r.get('replacement_delta'), 4)
        exp_pa_rem = num(r.get('expected_pa_remaining'))
        exp_total_fp = num(r.get('expected_total_fp_remaining'), 1)
        signal_h = r.get('signal') if pd.notna(r.get('signal')) else 'hold'
        pa_last21 = num(r.get('pa_last21'))
        slump_pct_h = num(r.get('slump_pct_rank'), 1)
        slump_n_h = int(r['slump_n_comparable']) if pd.notna(r.get('slump_n_comparable')) else None
        slump_bounce_h = num(r.get('slump_bounce_pct'), 1)
        slump_next_h = num(r.get('slump_next_rate'), 3)
        slump_delta_h = num(r.get('slump_delta'), 3)
        records.append({
            'mlbId':        int(r['batter']),
            'name':         r.get('player_name') or '',
            'pos':          r.get('primary_position') if pd.notna(r.get('primary_position')) else None,
            'fpos':         r.get('fantasy_positions_display') if pd.notna(r.get('fantasy_positions_display')) else None,
            'team':         r.get('team_2026') if pd.notna(r.get('team_2026')) else None,
            'slumpPct':     slump_pct_h,
            'slumpN':       slump_n_h,
            'slumpBouncePct': slump_bounce_h,
            'slumpNextRate':  slump_next_h,
            'slumpDelta':     slump_delta_h,
            'xfpPerPa':     num(r['xfp_h2_per_pa'], 4),
            'coreXfpPerPa': num(r.get('core_xfp_per_pa'), 4),
            'xfpFullFp':    num(r.get('xfp_h2_full_fp'), 2),    # × 3.5 PA/game
            'xfpRoSPerPa':  ros_per_pa,                          # NEW: rest-of-season FP/PA
            'xfpRoSFullFp': ros_per_game,                        # NEW: × 3.5 PA/game
            'xfpRoSp25':    ros_p25,                             # CI lower (FP/PA)
            'xfpRoSp75':    ros_p75,                             # CI upper (FP/PA)
            'recencyGap':   recency_gap,                         # last21 xwoba − season-to-date
            'paLast21':     pa_last21,
            'expPaRem':     exp_pa_rem,                          # projected PA over rest of season
            'expTotalFp':   exp_total_fp,                        # projected total FP rest-of-season
            'replXfp':      repl_xfp,
            'replDelta':    repl_delta,                          # xfp − replacement (FP/PA)
            'signal':       signal_h,                            # 'add'|'hold'|'drop'
            'paToDate':     pa_to_date,                          # NEW: PA cumulated so far
            'paPremium':    num(r.get('pa_premium'), 3),
            'pa':           int(pa_2026) if pa_2026 is not None else None,
            'fpPerPaActual': fp_actual_per_pa,
            'fpTotal':      fp_total_actual,
            'delta':        delta,
            'r':            int(r['r_2026']) if pd.notna(r.get('r_2026')) else None,
            'rbi':          int(r['rbi_2026']) if pd.notna(r.get('rbi_2026')) else None,
            'hr':           int(r['hr_2026']) if pd.notna(r.get('hr_2026')) else None,
            'cohort':       r.get('cohort'),
            'weight2026':   num(r.get('weight_2026'), 3),
            'hasBatTrack':  bool(r.get('has_bat_tracking', False)),
            # ESPN-merge fields (filled per my-team match)
            'roster':       'fa',
            'espnPos':      None,
            'pctOwned':     None,
            'fpProjEspn':   None,
            'fpTotalEspn':  None,
            'fpPerGameEspn':None,
            'gpEspn':       None,
        })

    # Compute position-aware TOTAL-FP replacement levels and Δ.
    # Source: league_config.HITTER_REPLACEMENT_RANK (8-team — this user's league)
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent))
    from league_config import HITTER_REPLACEMENT_RANK as REPL_RANK_TOTAL

    def _norm_pos(p):
        if not isinstance(p, str): return 'UTIL'
        p = p.upper().strip()
        if p in ('LF','CF','RF','OF'): return 'OF'
        if p in ('C','1B','2B','SS','3B','DH'): return p
        return 'UTIL'

    by_pos: dict[str, list] = {}
    for rec in records:
        if rec.get('expTotalFp') is None:
            continue
        pos = _norm_pos(rec.get('pos'))
        by_pos.setdefault(pos, []).append(rec)
    repl_total: dict[str, float] = {}
    for pos, lst in by_pos.items():
        lst.sort(key=lambda r: -(r['expTotalFp'] or 0))
        n = REPL_RANK_TOTAL.get(pos, 24)
        if len(lst) >= n:
            repl_total[pos] = float(lst[n - 1]['expTotalFp'] or 0)
        elif lst:
            repl_total[pos] = float(lst[-1]['expTotalFp'] or 0)
        else:
            repl_total[pos] = 0.0
    for rec in records:
        if rec.get('expTotalFp') is None:
            rec['replTotal'] = None
            rec['replDeltaTotal'] = None
            continue
        pos = _norm_pos(rec.get('pos'))
        rec['replTotal'] = round(repl_total.get(pos, 0.0), 1)
        rec['replDeltaTotal'] = round(rec['expTotalFp'] - rec['replTotal'], 1)

    # Default sort = TOTAL projected FP (the metric fantasy decisions actually rank on)
    # Hitters without expTotalFp (insufficient PA) sort to the bottom.
    records.sort(key=lambda x: -(x['expTotalFp'] if x['expTotalFp'] is not None else -1))
    for i, rec in enumerate(records):
        rec['rank'] = i + 1

    # ESPN merge — pull MY_TEAM hitters. Id-index first: the name dict is
    # lossy on shared names (both Muncys collapse to one key).
    by_key: dict[tuple[str, str], dict] = {}
    by_id: dict[int, dict] = {}
    for r in records:
        # Hitter names are "First Last" (from master_hitter / Chadwick), so
        # we use plv_name_key for both sides.
        by_key[plv_name_key(r['name'])] = r
        if r.get('mlbId'):
            by_id[int(r['mlbId'])] = r

    my_team_raw = extract_my_team()
    hitter_payload: list[dict] = []
    if my_team_raw:
        for h in my_team_raw.get('hitters', []):
            espn_pos = h.get('espnPos') or h.get('pos') or ''
            xfp_rec = find_xfp_record(h.get('name', '') or h.get('cleanName', ''),
                                      by_key, mlbam=h.get('mlbId'), by_id=by_id)
            if xfp_rec is not None:
                xfp_rec['roster']        = 'mine'
                xfp_rec['espnPos']       = espn_pos
                xfp_rec['pctOwned']      = h.get('pctOwned') if isinstance(h.get('pctOwned'), (int, float)) else None
                xfp_rec['fpProjEspn']    = h.get('fpProj') if isinstance(h.get('fpProj'), (int, float)) else None
                xfp_rec['fpTotalEspn']   = h.get('fpTotal') if isinstance(h.get('fpTotal'), (int, float)) else None
                xfp_rec['fpPerGameEspn'] = h.get('fpPerGame') if isinstance(h.get('fpPerGame'), (int, float)) else None
                xfp_rec['gpEspn']        = h.get('gp') if isinstance(h.get('gp'), int) else None

            hitter_payload.append({
                'name':       h.get('name') or h.get('cleanName'),
                'cleanName':  h.get('cleanName') or h.get('name'),
                'mlbId':      h.get('mlbId') or (xfp_rec['mlbId'] if xfp_rec else None),
                'espnPos':    espn_pos,
                'fpos':       h.get('fpos'),
                'proTeam':    h.get('proTeam'),
                'pctOwned':   h.get('pctOwned') if isinstance(h.get('pctOwned'), (int, float)) else None,
                'gp':         h.get('gp') if isinstance(h.get('gp'), int) else None,
                'fpTotal':    h.get('fpTotal') if isinstance(h.get('fpTotal'), (int, float)) else None,
                'fpProj':     h.get('fpProj') if isinstance(h.get('fpProj'), (int, float)) else None,
                'fpPerGame':  h.get('fpPerGame') if isinstance(h.get('fpPerGame'), (int, float)) else None,
                # xFP fields when matched
                'xfpPerPa':       xfp_rec['xfpPerPa'] if xfp_rec else None,
                'coreXfpPerPa':   xfp_rec['coreXfpPerPa'] if xfp_rec else None,
                'xfpFullFp':      xfp_rec['xfpFullFp'] if xfp_rec else None,
                'xfpRank':        xfp_rec['rank'] if xfp_rec else None,
                'pa':             xfp_rec['pa'] if xfp_rec else None,
                'fpPerPaActual':  xfp_rec['fpPerPaActual'] if xfp_rec else None,
                'cohort':         xfp_rec['cohort'] if xfp_rec else None,
                'pos':            xfp_rec['pos'] if xfp_rec else h.get('pos'),
                'team':           xfp_rec['team'] if xfp_rec else h.get('proTeam'),
            })

    # Tag every hitter record with league-wide roster status
    _label_roster_status(records, xfp_name_key)
    return records, hitter_payload


def build_h2_meta() -> dict:
    if not H2_MODEL_PKL.exists():
        return {}
    bundle = joblib.load(H2_MODEL_PKL)
    pipe_full = bundle['pipeline_full']
    ridge = pipe_full.named_steps['r']
    feats = bundle['features']
    coefs = [
        {'feat': f, 'coef': round(float(c), 4)}
        for f, c in zip(feats, ridge.coef_)
    ]
    coefs.sort(key=lambda x: -abs(x['coef']))
    return {
        'version':         bundle.get('version', 'h2'),
        'features':        feats,
        'coefficients':    coefs,
        'intercept':       round(float(ridge.intercept_), 4),
        'alpha':           round(float(ridge.alpha_), 3),
        'crossYearR':      round(float(bundle['cross_year_r']), 4),
        'powerBiasHi':     round(float(bundle['power_bias_hi']), 4),
        'teamContextBias': round(float(bundle['team_context_bias']), 4),
        'scoreT1':         round(float(bundle['score_T1']), 4),
        'formula':         bundle['formula'],
        'trainedDate':     bundle['trained_date'],
        'nTrain':          int(bundle['n_train_full']),
        'trainingYears':   bundle['training_years'],
        'paPerGame':       bundle['pa_per_game'],
        'ytdR':            round(float(bundle.get('ytd_r_2026') or 0), 4),
        'ytdMae':          round(float(bundle.get('ytd_mae_2026') or 0), 4),
        'ytdN':            int(bundle.get('ytd_n_2026') or 0),
        'priorXwoba':      list(bundle.get('prior_xwoba', [80, 0.305])),
        'priorContact':    list(bundle.get('prior_contact', [200, 0.755])),
        'note':            bundle.get('note', ''),
    }


def _compute_data_thru() -> str | None:
    """Latest FINALIZED game date in the statcast panel, for the masthead's
    'DATA THRU' stamp. Excludes the gf_provisional bridge rows (same-day
    in-progress feed) so the stamp matches the 'data through yesterday'
    doctrine. Returns 'YYYY-MM-DD' or None on any read problem."""
    try:
        p = ROOT / 'data' / 'research' / 'xfp_cache' / 'statcast_2026.parquet'
        if not p.exists():
            return None
        df = pd.read_parquet(p, columns=['game_date', 'source'])
        final = df[df['source'].astype(str) != 'gf_provisional']
        gd = (final if len(final) else df)['game_date']
        return str(pd.to_datetime(gd).max().date())
    except Exception:
        return None


def build_meta() -> dict:
    bundle = joblib.load(MODEL_PKL)
    pipe = bundle['pipeline']
    ridge = pipe.named_steps['r']
    feats = bundle['features']
    coefs = [
        {'feat': f, 'coef': round(float(c), 3)}
        for f, c in zip(feats, ridge.coef_)
    ]
    coefs.sort(key=lambda x: -abs(x['coef']))
    return {
        'features': feats,
        'coefficients': coefs,
        'intercept': round(float(ridge.intercept_), 3),
        'alpha': round(float(ridge.alpha_), 3),
        'crossYearR': round(float(bundle['cross_year_r']), 3),
        'kBiasHi': round(float(bundle['k_bias_hi']), 3),
        'scoreCurrent': round(float(bundle['score_current']), 3),
        'scoreT1': round(float(bundle['score_tolerance_T1']), 3),
        'formula': bundle['formula'],
        'trainedDate': bundle['trained_date'],
        'dataThru': _compute_data_thru(),
        'nTrain': int(bundle['n_train']),
        'trainingYears': bundle.get('training_years', '2020-2025'),
        'ytdR': round(float(bundle.get('ytd_r_2026', 0)), 3),
        'ytdMae': round(float(bundle.get('ytd_mae_2026', 0)), 3),
        'comparison': bundle.get('comparison'),
    }


# HTML_TEMPLATE lives in lib/index_dashboard_template.py (audit T48 second
# attempt 2026-08-01: the r""" literal MOVED VERBATIM -- source bytes
# unchanged; one-time string-level proof recorded in that module's docstring,
# permanent guards in tests/test_index_dashboard_template.py). It is a RAW
# constant, deliberately NOT an f-string: every `{}` in the JSX is literal,
# so there is no brace-doubling hazard, and render_app() takes no parameters
# because the literal has zero interpolation points and zero free names.
# Substitution stays the 12 named __TOKEN__ .replace() calls in main().
try:
    from lib.index_dashboard_template import render_app
except ImportError:  # imported as scripts.xfp.build_index_dashboard (tests)
    from .lib.index_dashboard_template import render_app
HTML_TEMPLATE = render_app()


# ═══════════════════════════════════════════════════════════════════════════════
# Team Audit payload — position-by-position roster eval + FA leaderboards
# ═══════════════════════════════════════════════════════════════════════════════

# Name join key — OWNER: name_match.safe_name_key. safe_name_key already does the
# "Last, First" flip and the accent strip this used to hand-roll, and additionally
# collapses curly-vs-straight apostrophes (the Ryan O'Hearn miss, 2026-07-28).
from plv_clone.utils.name_match import safe_name_key as _norm_audit  # noqa: E402


def _marcel_fp(multiyr: pd.DataFrame, player_id: int, id_col: str,
               fp_col: str, gs_col: str, year_col: str = 'year') -> dict | None:
    """Compute 3-year weighted Marcel for a player, weights 5/4/3 on yr T-1/T-2/T-3."""
    sub = multiyr[multiyr[id_col] == player_id].sort_values(year_col)
    if sub.empty:
        return None
    last_y = int(sub[year_col].max())
    target_years = [last_y, last_y - 1, last_y - 2]
    target_years = [y for y in target_years if y != 2020]
    weights = {target_years[0]: 5}
    if len(target_years) > 1:
        weights[target_years[1]] = 4
    if len(target_years) > 2:
        weights[target_years[2]] = 3
    num = den = 0.0
    yrs_used = []
    for y, w in weights.items():
        row = sub[sub[year_col] == y]
        if row.empty:
            continue
        fp = float(row[fp_col].iloc[0])
        gs = float(row[gs_col].iloc[0])
        num += fp * w * gs
        den += w * gs
        yrs_used.append(y)
    if den == 0:
        return None
    return {'marcel_3yr': round(num / den, 2),
            'marcel_years': yrs_used,
            'marcel_basis': 'gs-weighted' if 'gs' in gs_col.lower() else 'sample-weighted'}


def _bucket_position(espn_pos: str | None) -> str:
    p = (espn_pos or '').upper()
    if p in ('SP', 'P'):
        return 'SP'
    if p == 'RP':
        return 'RP'
    if p == 'C':
        return 'C'
    if p == '1B':
        return '1B'
    if p == '2B':
        return '2B'
    if p == '3B':
        return '3B'
    if p == 'SS':
        return 'SS'
    if p in ('OF', 'LF', 'CF', 'RF', 'DH'):
        return 'OF'
    return p or 'UTIL'


def _commentary(player: dict) -> str:
    """Auto-generate one-line commentary from rank/slump fields."""
    rk = player.get('rank')
    sig = player.get('signal')
    sp = player.get('slump_pct')
    bp = player.get('slump_bounce')
    role = player.get('role')

    if player.get('marcel_3yr') is not None and player.get('rank') is None:
        return (f"On IL or no 2026 sample. 3-year weighted Marcel projects "
                f"{player['marcel_3yr']:.2f} FP/start when activated.")

    parts = []
    if sig == 'add':
        parts.append("ADD signal — currently producing above replacement.")
    elif sig == 'drop':
        parts.append("DROP signal — currently below replacement.")
    if sp is not None and bp is not None:
        if sp < 20 and bp >= 90:
            parts.append(f"Buy-low signature: {sp:.0f}-th percentile cold streak, "
                         f"{bp:.0f}% historical bounce-back.")
        elif sp < 5 and bp < 60:
            parts.append(f"FADE warning: {sp:.0f}-th percentile, only {bp:.0f}% bounce.")
        elif sp >= 90 and bp < 60:
            parts.append(f"Peak performance ({sp:.0f}-th percentile) with only {bp:.0f}% sustain — fade risk.")
        elif sp >= 90:
            parts.append(f"At peak ({sp:.0f}-th percentile of own career).")
    if rk is not None:
        rank_text = f"Mdl rank #{rk}"
        if role in ('SP', 'RP'):
            rank_text += f" {role}"
        parts.append(rank_text + ".")
    return ' '.join(parts) if parts else 'No commentary available.'


def build_team_audit() -> dict:
    """Build the full Team Audit payload for the dashboard."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT))
        from plv_clone.league_state import LeagueState
        ls = LeagueState()
    except Exception as e:
        print(f'[audit] LeagueState unavailable: {e}')
        return {'error': str(e)}

    try:
        teams = ls.all_teams()
        standings = ls.standings()
    except Exception as e:
        print(f'[audit] ESPN fetch failed: {e}')
        return {'error': str(e)}

    if teams.empty:
        return {'error': 'no teams returned'}

    # Build lookups
    rh = pd.read_csv(ROOT / 'data/outputs/xfp_rh3_projections.csv')
    rh['key'] = rh['player_name'].apply(_norm_audit)
    rh_dedup = rh.sort_values(['key', 'pa_to'], ascending=[True, False]).drop_duplicates('key', keep='first')
    rh_lookup = {r['key']: r.to_dict() for _, r in rh_dedup.iterrows()}

    rp_sp = pd.read_csv(ROOT / 'data/outputs/xfp_rp3_projections.csv')
    rp_sp['key'] = rp_sp['player_name'].apply(_norm_audit)
    sp_lookup = {r['key']: r.to_dict() for _, r in rp_sp.iterrows()}

    pcs_path = ROOT / 'data/research/xfp_cache/pitcher_counting_stats_2026.json'
    if pcs_path.exists():
        with open(pcs_path) as f:
            pcs = pd.DataFrame(json.load(f))[['pitcher', 'name']]
    else:
        pcs = pd.DataFrame(columns=['pitcher', 'name'])
    rp_roll = pd.read_csv(ROOT / 'data/research/xfp_cache/rolling_relievers_2018_2026.csv')
    rp_roll = rp_roll[rp_roll['year'] == 2026].sort_values('split_day').drop_duplicates('pitcher', keep='last')
    rp_roll = rp_roll.merge(pcs, on='pitcher', how='left')
    rp_roll = rp_roll.sort_values('fp_with_role_to', ascending=False).reset_index(drop=True)
    rp_roll['rp_rank'] = rp_roll.index + 1
    rp_roll['key'] = rp_roll['name'].fillna('').apply(_norm_audit)
    rp_lookup = {r['key']: r.to_dict() for _, r in rp_roll.iterrows() if r['key']}

    # Multi-year sources for Marcel of IL/no-2026 players + actual YTD totals
    sp_multiyr = pd.read_csv(ROOT / 'data/research/xfp_cache/sp_multiyr_2015_2025.csv')
    rp_multiyr = pd.read_csv(ROOT / 'data/research/xfp_cache/relievers_multiyr_2018_2026.csv')
    h_multiyr = pd.read_csv(ROOT / 'data/research/xfp_cache/hitters_multiyr_2015_2026.csv')
    # 2026 actual YTD totals for hitters (perceived value)
    h_2026 = h_multiyr[h_multiyr['year'] == 2026][['batter', 'pa', 'fp_total']].rename(
        columns={'pa': 'pa_2026', 'fp_total': 'fp_total_2026'})
    if not h_2026.empty:
        rh = rh.merge(h_2026, on='batter', how='left')
        rh_dedup = rh.sort_values(['key', 'pa_to'], ascending=[True, False]).drop_duplicates('key', keep='first')
        rh_lookup = {r['key']: r.to_dict() for _, r in rh_dedup.iterrows()}

    # SP remaining-starts factor (matches dashboard SP RoS calc)
    SP_REM_FACTOR = 1.42
    RP_REM_FACTOR = 1.42

    # Slump precedent merges (already in rh3/rp3)
    def _eval_player(name: str, espn_pos: str) -> dict:
        k = _norm_audit(name)
        bucket = _bucket_position(espn_pos)
        out = {'name': name, 'espn_pos': espn_pos, 'bucket': bucket,
               'rank': None, 'fp_per': None, 'sample': 0,
               'signal': None, 'slump_pct': None, 'slump_n': None,
               'slump_bounce': None, 'slump_next': None,
               'marcel_3yr': None, 'marcel_years': None, 'role': None,
               'ytd_fp': 0.0, 'ros_fp': 0.0}
        if bucket == 'SP':
            r = sp_lookup.get(k)
            if r and pd.notna(r.get('xfp_rp3_per_start_sched') or r.get('xfp_rp3_per_start')):
                fp_per = float(r.get('xfp_rp3_per_start_sched') or r.get('xfp_rp3_per_start'))
                gs = int(r.get('gs_to') or 0)
                out['rank'] = int(r['rank'])
                out['fp_per'] = fp_per
                out['sample'] = gs
                out['signal'] = r.get('signal')
                out['role'] = 'SP'
                ytd_per = float(r.get('fp_per_start_to') or fp_per)
                out['ytd_fp'] = ytd_per * gs
                out['ros_fp'] = fp_per * gs * SP_REM_FACTOR
                if pd.notna(r.get('slump_pct_rank')):
                    out['slump_pct'] = float(r['slump_pct_rank'])
                if pd.notna(r.get('slump_n_comparable')):
                    out['slump_n'] = int(r['slump_n_comparable'])
                if pd.notna(r.get('slump_bounce_pct')):
                    out['slump_bounce'] = float(r['slump_bounce_pct'])
                if pd.notna(r.get('slump_next_rate')):
                    out['slump_next'] = float(r['slump_next_rate'])
            else:
                row = sp_multiyr[sp_multiyr['player_name'].str.replace(' ', '').str.lower()
                                 .apply(lambda s: _norm_audit(s) == k if pd.notna(s) else False)]
                if not row.empty:
                    pid = int(row['pitcher'].iloc[0])
                    m = _marcel_fp(sp_multiyr, pid, 'pitcher',
                                   'fp_per_start_actual', 'gs')
                    if m:
                        out.update(m)
                        out['role'] = 'SP'
                        # IL stash projected over remaining ~14 starts (rough)
                        out['ros_fp'] = float(m['marcel_3yr']) * 14
        elif bucket == 'RP':
            r = rp_lookup.get(k)
            if r:
                fp_to = float(r.get('fp_with_role_to') or 0)
                out['rank'] = int(r['rp_rank'])
                out['fp_per'] = fp_to
                out['sample'] = int(r.get('g_to') or 0)
                out['role'] = 'RP'
                out['ytd_fp'] = fp_to
                out['ros_fp'] = fp_to * RP_REM_FACTOR
            else:
                row = rp_multiyr[rp_multiyr['name'].fillna('').apply(lambda s: _norm_audit(s) == k)]
                if not row.empty:
                    pid = int(row['pitcher'].iloc[0])
                    m = _marcel_fp(rp_multiyr, pid, 'pitcher', 'fp_per_g', 'g', year_col='season')
                    if m:
                        out.update(m)
                        out['role'] = 'RP'
                        out['ros_fp'] = float(m['marcel_3yr']) * 30
        else:
            r = rh_lookup.get(k)
            if r and pd.notna(r.get('xfp_rh3_per_game')):
                out['rank'] = int(r['rank'])
                out['fp_per'] = float(r['xfp_rh3_per_game'])
                out['sample'] = int(r.get('pa_to') or 0)
                out['signal'] = r.get('signal')
                out['role'] = 'H'
                out['ros_fp'] = float(r.get('expected_total_fp_remaining') or 0)
                # Actual YTD totals from hitters_multiyr 2026 (joined above as fp_total_2026)
                actual_ytd = r.get('fp_total_2026')
                if pd.notna(actual_ytd) and actual_ytd:
                    out['ytd_fp'] = float(actual_ytd)
                else:
                    out['ytd_fp'] = float(r.get('xfp_rh3_per_pa') or 0) * out['sample']
                out['repl_delta'] = float(r.get('replacement_delta') or 0)
                if pd.notna(r.get('slump_pct_rank')):
                    out['slump_pct'] = float(r['slump_pct_rank'])
                if pd.notna(r.get('slump_n_comparable')):
                    out['slump_n'] = int(r['slump_n_comparable'])
                if pd.notna(r.get('slump_bounce_pct')):
                    out['slump_bounce'] = float(r['slump_bounce_pct'])
                if pd.notna(r.get('slump_next_rate')):
                    out['slump_next'] = float(r['slump_next_rate'])
            else:
                row = h_multiyr[h_multiyr['player_name'].fillna('')
                                .apply(lambda s: _norm_audit(s) == k)]
                if not row.empty:
                    bid = int(row['batter'].iloc[0])
                    m = _marcel_fp(h_multiyr, bid, 'batter', 'fp_per_pa_actual', 'pa')
                    if m:
                        out.update(m)
                        out['role'] = 'H'
                        out['ros_fp'] = float(m['marcel_3yr']) * 400
        out['commentary'] = _commentary(out)
        return out

    # Determine MY_TEAM
    my_team_name = MY_TEAM_NAME
    rostered_keys = set(teams['player_name'].apply(_norm_audit))

    # Compute roster_buckets for EVERY team (mine + 7 opponents)
    all_team_buckets = {}
    for tname, grp in teams.groupby('team_name'):
        b = {'C': [], '1B': [], '2B': [], '3B': [], 'SS': [], 'OF': [], 'SP': [], 'RP': []}
        for _, p in grp.iterrows():
            ev = _eval_player(p['player_name'], p['position'])
            bk = ev['bucket']
            if bk in b:
                b[bk].append(ev)
            else:
                b.setdefault(bk, []).append(ev)
        all_team_buckets[tname] = b

    buckets = all_team_buckets.get(my_team_name, {})

    # FA leaderboards by position
    def _fa_hitters(pos_filter, n=5) -> list[dict]:
        cands = []
        for _, r in rh.iterrows():
            if r['key'] in rostered_keys:
                continue
            prim_raw = r.get('primary_position')
            prim = prim_raw.upper() if isinstance(prim_raw, str) else ''
            if pos_filter == 'OF':
                if not (prim in ('OF', 'LF', 'CF', 'RF') or 'OF' in prim):
                    continue
            elif prim != pos_filter:
                continue
            cands.append({
                'name': r['player_name'],
                'team': r.get('team'),
                'pos': prim,
                'rank': int(r['rank']),
                'fp_per': float(r.get('xfp_rh3_per_game') or 0),
                'ros_total': float(r.get('expected_total_fp_remaining') or 0),
                'repl_delta': float(r.get('replacement_delta') or 0),
                'signal': r.get('signal'),
                'slump_pct': float(r['slump_pct_rank']) if pd.notna(r.get('slump_pct_rank')) else None,
                'slump_bounce': float(r['slump_bounce_pct']) if pd.notna(r.get('slump_bounce_pct')) else None,
                'slump_next': float(r['slump_next_rate']) if pd.notna(r.get('slump_next_rate')) else None,
            })
        return sorted(cands, key=lambda x: -x['ros_total'])[:n]

    fa_sp = []
    for _, r in rp_sp.iterrows():
        if r['key'] in rostered_keys:
            continue
        v = r.get('xfp_rp3_per_start_sched') or r.get('xfp_rp3_per_start')
        if pd.isna(v):
            continue
        fa_sp.append({
            'name': r['player_name'],
            'rank': int(r['rank']),
            'fp_per': float(v),
            'sample': int(r.get('gs_to') or 0),
            'signal': r.get('signal'),
            'repl_delta': float(r.get('replacement_delta') or 0),
            'slump_pct': float(r['slump_pct_rank']) if pd.notna(r.get('slump_pct_rank')) else None,
            'slump_bounce': float(r['slump_bounce_pct']) if pd.notna(r.get('slump_bounce_pct')) else None,
            'slump_next': float(r['slump_next_rate']) if pd.notna(r.get('slump_next_rate')) else None,
        })
    fa_sp = sorted(fa_sp, key=lambda x: -x['fp_per'])[:10]

    fa_rp = []
    for _, r in rp_roll.iterrows():
        if r['key'] in rostered_keys or not r.get('name'):
            continue
        fa_rp.append({
            'name': r['name'],
            'rank': int(r['rp_rank']),
            'fp_per': float(r.get('fp_with_role_to') or 0),
            'sample': int(r.get('g_to') or 0),
            'role': r.get('role_lag1'),
            'sv': int(r.get('sv_to') or 0),
            'hld': int(r.get('hld_to') or 0),
        })
    fa_rp = sorted(fa_rp, key=lambda x: -x['fp_per'])[:10]

    fa = {
        'C':  _fa_hitters('C'),
        '1B': _fa_hitters('1B'),
        '2B': _fa_hitters('2B'),
        '3B': _fa_hitters('3B'),
        'SS': _fa_hitters('SS'),
        'OF': _fa_hitters('OF'),
        'SP': fa_sp,
        'RP': fa_rp,
    }

    # Standings (for context)
    st_rows = []
    if not standings.empty:
        for _, r in standings.iterrows():
            st_rows.append({
                'team_name': r['team_name'],
                'wins': int(r.get('wins') or 0),
                'losses': int(r.get('losses') or 0),
                'is_mine': r['team_name'] == my_team_name,
            })

    # ── Trade finder ─────────────────────────────────────────────────────────
    # Goal: surface 1-for-1 swaps where (a) the model says I gain forward RoS FP
    # and (b) the trade looks roughly fair from the season-to-date totals,
    # so the opposing team is plausibly willing to accept.
    #
    # Definitions:
    #   ytd_diff   = ytd_fp(theirs) - ytd_fp(mine)    rear-view "perceived" delta
    #   model_gain = ros_fp(theirs) - ros_fp(mine)    forward-looking edge for me
    #
    # Required filters:
    #   - both players have a model rank (no IL-only deals we can't price)
    #   - model_gain >= 25 FP                meaningful forward edge
    #   - |ytd_diff| <= 30 FP                looks roughly fair on rear-view
    #     (positive = they think they're losing YTD; negative = I think I'm losing.
    #      Both extremes get filtered so the trade is "plausibly proposable")
    # Same-bucket only for v1 (catcher-for-catcher, OF-for-OF, etc.)

    def _trade_pairs(my_buckets: dict, their_buckets: dict, max_total: int = 25) -> list[dict]:
        suggestions = []
        for bk in ['C', '1B', '2B', '3B', 'SS', 'OF', 'SP', 'RP']:
            mine_list = my_buckets.get(bk, [])
            theirs_list = their_buckets.get(bk, [])
            for mine in mine_list:
                if mine.get('rank') is None or (mine.get('ros_fp') or 0) <= 0:
                    continue
                for theirs in theirs_list:
                    if theirs.get('rank') is None or (theirs.get('ros_fp') or 0) <= 0:
                        continue
                    ytd_diff = (theirs.get('ytd_fp') or 0) - (mine.get('ytd_fp') or 0)
                    model_gain = (theirs.get('ros_fp') or 0) - (mine.get('ros_fp') or 0)
                    if model_gain < 25:
                        continue
                    if abs(ytd_diff) > 30:
                        continue
                    suggestions.append({
                        'bucket': bk,
                        'mine': {
                            'name': mine['name'], 'rank': mine.get('rank'),
                            'ytd_fp': round(mine.get('ytd_fp') or 0, 1),
                            'ros_fp': round(mine.get('ros_fp') or 0, 1),
                            'slump_pct': mine.get('slump_pct'),
                            'slump_bounce': mine.get('slump_bounce'),
                            'signal': mine.get('signal'),
                        },
                        'theirs': {
                            'name': theirs['name'], 'rank': theirs.get('rank'),
                            'ytd_fp': round(theirs.get('ytd_fp') or 0, 1),
                            'ros_fp': round(theirs.get('ros_fp') or 0, 1),
                            'slump_pct': theirs.get('slump_pct'),
                            'slump_bounce': theirs.get('slump_bounce'),
                            'signal': theirs.get('signal'),
                        },
                        'perceived_diff': round(ytd_diff, 1),
                        'model_diff': round(model_gain, 1),
                        'edge_for_me': round(model_gain, 1),  # the actual RoS upside I gain
                    })
        suggestions.sort(key=lambda s: -s['edge_for_me'])
        return suggestions[:max_total]

    trades = {}
    for tname in all_team_buckets:
        if tname == my_team_name:
            continue
        trades[tname] = _trade_pairs(buckets, all_team_buckets[tname])

    return {
        'my_team_name': my_team_name,
        'as_of_date': str(date.today()),
        'standings': st_rows,
        'roster_buckets': buckets,
        'all_team_buckets': all_team_buckets,
        'fa': fa,
        'trades_vs': trades,
    }


def build_advisory_payload():
    """Aggregate advisory CSVs (decision-support, not model features) into JSON.
    Five panels: velocity drop, ensemble divergence, TTO penalty, bullpen quality,
    pitch matchup weakness."""
    out = {'velocity': [], 'ensemble_hitters_overbull': [], 'ensemble_hitters_underbull': [],
           'ensemble_pitchers_overbull': [], 'ensemble_pitchers_underbull': [],
           'tto_penalty': [], 'bullpen_2026': [], 'pitch_weakness_top': []}

    def _round(d, cols, n=3):
        for k in cols:
            if k in d and d[k] is not None and not pd.isna(d[k]):
                d[k] = round(float(d[k]), n)
            elif k in d and pd.isna(d[k]):
                d[k] = None
        return d

    out_dir = ROOT / 'data' / 'outputs'

    # 1. SP velocity drop alerts — active 2026 SPs only
    p = out_dir / 'sp_velocity_trend.csv'
    if p.exists():
        v = pd.read_csv(p)
        v = v[v['starts_2026'].fillna(0) > 0]
        v = v.sort_values('velo_drop_mph')
        cols = ['player_name', 'starts_n', 'starts_2026', 'career_velo',
                'last5_velo', 'last5_2026_velo', 'velo_drop_mph', 'alert', 'last_start_date']
        for r in v[cols].head(60).to_dict(orient='records'):
            out['velocity'].append(_round(r, ['career_velo', 'last5_velo', 'last5_2026_velo', 'velo_drop_mph'], 2))

    # 2. Ensemble divergence (hitters)
    p = out_dir / 'projection_ensemble_hitters.csv'
    if p.exists():
        eh = pd.read_csv(p)
        if 'ext_mean_fp_per_pa' in eh.columns and eh['ext_mean_fp_per_pa'].notna().any():
            eh = eh.dropna(subset=['ext_mean_fp_per_pa', 'xfp_rh3_per_pa']).copy()
            eh['divergence'] = eh['xfp_rh3_per_pa'] - eh['ext_mean_fp_per_pa']
            cols_h = ['player_name', 'team', 'xfp_rh3_per_pa', 'ext_mean_fp_per_pa',
                      'ensemble_fp_per_pa', 'divergence', 'ext_n_systems']
            avail = [c for c in cols_h if c in eh.columns]
            top = eh.sort_values('divergence', ascending=False).head(25)
            bot = eh.sort_values('divergence').head(25)
            for r in top[avail].to_dict(orient='records'):
                out['ensemble_hitters_overbull'].append(_round(r, ['xfp_rh3_per_pa', 'ext_mean_fp_per_pa', 'ensemble_fp_per_pa', 'divergence'], 4))
            for r in bot[avail].to_dict(orient='records'):
                out['ensemble_hitters_underbull'].append(_round(r, ['xfp_rh3_per_pa', 'ext_mean_fp_per_pa', 'ensemble_fp_per_pa', 'divergence'], 4))

    # 2b. Ensemble divergence (pitchers)
    p = out_dir / 'projection_ensemble_pitchers.csv'
    if p.exists():
        ep = pd.read_csv(p)
        if 'ext_mean_fp_per_g' in ep.columns and ep['ext_mean_fp_per_g'].notna().any():
            ep = ep.dropna(subset=['ext_mean_fp_per_g', 'xfp_rp3_per_start']).copy()
            ep['divergence'] = ep['xfp_rp3_per_start'] - ep['ext_mean_fp_per_g']
            cols_p = ['player_name', 'xfp_rp3_per_start', 'ext_mean_fp_per_g',
                      'ensemble_fp_per_start', 'divergence', 'ext_n_systems']
            avail = [c for c in cols_p if c in ep.columns]
            top = ep.sort_values('divergence', ascending=False).head(25)
            bot = ep.sort_values('divergence').head(25)
            for r in top[avail].to_dict(orient='records'):
                out['ensemble_pitchers_overbull'].append(_round(r, ['xfp_rp3_per_start', 'ext_mean_fp_per_g', 'ensemble_fp_per_start', 'divergence'], 2))
            for r in bot[avail].to_dict(orient='records'):
                out['ensemble_pitchers_underbull'].append(_round(r, ['xfp_rp3_per_start', 'ext_mean_fp_per_g', 'ensemble_fp_per_start', 'divergence'], 2))

    # 3. TTO penalty (3rd-time-through hurts most)
    p = out_dir / 'sp_lineup_pass.csv'
    if p.exists():
        t = pd.read_csv(p)
        if 'tto3_minus_tto1' in t.columns:
            t = t.dropna(subset=['tto3_minus_tto1', 'player_name'])
            t = t[t['tto3_pa'].fillna(0) >= 200]
            cols_t = ['player_name', 'total_pa', 'tto1_rate', 'tto2_rate', 'tto3_rate', 'tto3_minus_tto1']
            avail = [c for c in cols_t if c in t.columns]
            for r in t.sort_values('tto3_minus_tto1').head(40)[avail].to_dict(orient='records'):
                out['tto_penalty'].append(_round(r, ['tto1_rate', 'tto2_rate', 'tto3_rate', 'tto3_minus_tto1'], 4))

    # 4. Bullpen quality — 2026
    p = out_dir / 'bullpen_quality.csv'
    if p.exists():
        b = pd.read_csv(p)
        b = b[b['year'] == 2026].sort_values('bullpen_fp_per_ip', ascending=False)
        cols_b = ['team', 'bullpen_fp_per_ip', 'n_rps', 'bullpen_ip']
        for r in b[cols_b].to_dict(orient='records'):
            out['bullpen_2026'].append(_round(r, ['bullpen_fp_per_ip', 'bullpen_ip'], 3))

    # 5. Pitch arsenal weakness (top whiff% per pitch group, hitters w/ ≥100 swings)
    p = out_dir / 'batter_pitch_weakness.csv'
    if p.exists():
        bw = pd.read_csv(p)
        bw = bw[bw['swings'].fillna(0) >= 100].dropna(subset=['player_name', 'whiff_per_swing'])
        # For each pitch group, top-20 whiff hitters
        for ptg, sub in bw.groupby('ptg'):
            top = sub.sort_values('whiff_per_swing', ascending=False).head(20)
            for r in top[['player_name', 'ptg', 'swings', 'whiff_per_swing', 'xwoba_avg']].to_dict(orient='records'):
                out['pitch_weakness_top'].append(_round(r, ['whiff_per_swing', 'xwoba_avg'], 3))

    # 6. Lineup optimizer (Tier 2)
    p = out_dir / 'lineup_optimizer.json'
    if p.exists():
        try:
            import json as _json
            with open(p, 'r', encoding='utf-8') as f:
                out['lineup_optimizer'] = _json.load(f)
        except Exception:
            out['lineup_optimizer'] = None

    # 7. Opponent scouting (Tier 2)
    p = out_dir / 'opponent_scouting.json'
    if p.exists():
        try:
            import json as _json
            with open(p, 'r', encoding='utf-8') as f:
                out['opponent_scouting'] = _json.load(f)
        except Exception:
            out['opponent_scouting'] = None

    # 8. Opponent lineup overlap (Tier 2 deepening)
    p = out_dir / 'opponent_lineup_overlap.json'
    if p.exists():
        try:
            import json as _json
            with open(p, 'r', encoding='utf-8') as f:
                out['lineup_overlap'] = _json.load(f)
        except Exception:
            out['lineup_overlap'] = None

    # 9. Smart trade finder (Tier 3)
    p = out_dir / 'smart_trade_finder.json'
    if p.exists():
        try:
            import json as _json
            with open(p, 'r', encoding='utf-8') as f:
                out['smart_trade_finder'] = _json.load(f)
        except Exception:
            out['smart_trade_finder'] = None

    # 10. Waiver watch (Tier 3)
    p = out_dir / 'waiver_watch.json'
    if p.exists():
        try:
            import json as _json
            with open(p, 'r', encoding='utf-8') as f:
                out['waiver_watch'] = _json.load(f)
        except Exception:
            out['waiver_watch'] = None

    # 11+ Tier 3 deepening artifacts (load all, render compactly)
    for key, fname in [
        ('playoff_ros', 'playoff_ros.json'),
        ('two_start_alerts', 'two_start_alerts.json'),
        ('punt_detector', 'punt_detector.json'),
        ('save_handcuffs', 'save_handcuffs.json'),
        ('monte_carlo', 'monte_carlo.json'),
        ('bench_tracker', 'bench_tracker.json'),
        ('eligibility_changes', 'eligibility_changes.json'),
    ]:
        p = out_dir / fname
        if p.exists():
            try:
                import json as _json
                with open(p, 'r', encoding='utf-8') as f:
                    out[key] = _json.load(f)
            except Exception:
                out[key] = None

    return out


def main():
    records, my_team, rp_records = build_records()
    hitter_records, hitter_payload = build_hitter_records()
    my_team['hitters'] = hitter_payload  # combine into one MY_TEAM payload
    meta = build_meta()
    h2_meta = build_h2_meta()
    audit = build_team_audit()
    advisory = build_advisory_payload()

    proj_json     = json.dumps(records, separators=(',', ':'))
    meta_json     = json.dumps(meta, separators=(',', ':'))
    my_team_json  = json.dumps(my_team, separators=(',', ':'))
    hitters_json  = json.dumps(hitter_records, separators=(',', ':'))
    relievers_json= json.dumps(rp_records, separators=(',', ':'))
    h2_meta_json  = json.dumps(h2_meta, separators=(',', ':'))
    audit_json    = json.dumps(audit, separators=(',', ':'))
    advisory_json = json.dumps(advisory, separators=(',', ':'))

    # Weekly fp substrate for trade simulator UI
    weekly_path = ROOT / 'data' / 'outputs' / 'weekly_fp_substrate.json'
    if weekly_path.exists():
        with open(weekly_path, 'r', encoding='utf-8') as f:
            weekly_json = f.read()
    else:
        weekly_json = '{"weeks":{},"players":[]}'

    # Decision-console payload (written by the matchup build / refresh
    # step 4.3 (was 4.52) CLI). Index is a PURE CONSUMER: stale or missing
    # -> literal null and the Decision tab shows a "not built today"
    # notice, never fetches.
    decision_json = 'null'
    decision_path = ROOT / 'data' / 'outputs' / 'console_data.json'
    try:
        from datetime import date as _date
        _dc = json.loads(decision_path.read_text(encoding='utf-8'))
        if (_dc.get('schema_version') == 1
                and str(_dc.get('generated_at', ''))[:10] == _date.today().isoformat()):
            # escape </ so free-text fields can't close the <script> block
            decision_json = json.dumps(_dc, separators=(',', ':')).replace('</', '<\\/')
        else:
            print(f"  decision console payload stale "
                  f"({str(_dc.get('generated_at', ''))[:10]}) — Decision tab shows notice")
    except Exception as _e:
        print(f"  decision console payload unavailable ({type(_e).__name__}) — Decision tab shows notice")

    from lib.dashboard_chrome import topnav as _topnav, theme_boot_js as _theme_boot_js
    html = (HTML_TEMPLATE
            .replace('__TOPNAV__', _topnav('index'))
            .replace('__THEME_BOOT__', _theme_boot_js())
            .replace('__PROJECTIONS_JSON__', proj_json)
            .replace('__META_JSON__', meta_json)
            .replace('__H2_META_JSON__', h2_meta_json)
            .replace('__HITTERS_JSON__', hitters_json)
            .replace('__RELIEVERS_JSON__', relievers_json)
            .replace('__MY_TEAM_JSON__', my_team_json)
            .replace('__AUDIT_JSON__', audit_json)
            .replace('__ADVISORY_JSON__', advisory_json)
            .replace('__WEEKLY_JSON__', weekly_json)
            .replace('__DECISION_JSON__', decision_json))

    OUT_PRIMARY.write_text(html, encoding='utf-8')
    OUT_DOCS.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(OUT_PRIMARY, OUT_DOCS)

    size_kb = OUT_PRIMARY.stat().st_size // 1024
    primary_bytes = OUT_PRIMARY.read_bytes()
    docs_bytes = OUT_DOCS.read_bytes()
    assert primary_bytes == docs_bytes, "primary and docs HTML are not byte-identical"

    n_mine_p = sum(1 for r in records if r['roster'] == 'mine')
    n_mine_h = sum(1 for r in hitter_records if r['roster'] == 'mine')
    print(f"wrote {OUT_PRIMARY} ({size_kb} KB, {len(records)} pitchers + {len(hitter_records)} hitters, "
          f"{n_mine_p} P / {n_mine_h} H on '{my_team.get('teamName') or '—'}')")
    print(f"wrote {OUT_DOCS} (byte-identical)")


if __name__ == '__main__':
    main()

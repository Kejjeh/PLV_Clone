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
PLV_HTML = ROOT / 'data' / 'outputs' / 'process_report_2026.html'
OUT_PRIMARY = ROOT / 'data' / 'outputs' / 'xfp_dashboard.html'
OUT_DOCS = ROOT / 'xfp-model' / 'docs' / 'index.html'


# ─── Name normalization ───────────────────────────────────────────────────────

def _strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')


def _norm(s: str) -> str:
    return re.sub(r'[^a-z]+', '', _strip_accents(s).lower())


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


def find_xfp_record(plv_name: str, by_key: dict) -> dict | None:
    """Match a PLV-style name against the xFP records dict.

    Strict (last, first) match after accent-stripping normalization. Fallback
    accepts a unique last-name match only when the first names share a 3-char
    prefix — this catches `Cam Schlittler ↔ Schlittler, Cam` while rejecting
    the `Robert Suarez ↔ Ranger Suarez` collision.
    """
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

def extract_my_team() -> dict | None:
    if not PLV_HTML.exists():
        return None
    s = PLV_HTML.read_text(encoding='utf-8')
    m = re.search(r'window\.MY_TEAM\s*=\s*(\{.+?\n\});', s, re.DOTALL)
    if not m:
        return None
    return json.loads(m.group(1))


# ─── Records ──────────────────────────────────────────────────────────────────

def build_records() -> tuple[list[dict], dict]:
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

    def num(v, dp=None):
        if pd.isna(v):
            return None
        v = float(v)
        return round(v, dp) if dp is not None else v

    records = []
    for _, r in proj.iterrows():
        gs_val = int(r['gs_2026']) if pd.notna(r['gs_2026']) else None
        fp_actual_val = num(r['fp_per_start_actual_2026'], 2)
        # Cumulative FP for the season (≥ 5 GS gate so the number is meaningful).
        fp_total_val = (
            round(gs_val * fp_actual_val, 1)
            if gs_val is not None and gs_val >= 5 and fp_actual_val is not None
            else None
        )
        # V12 is the new primary projection. Falls back to V11 for pitchers V12 doesn't cover.
        xfp_primary = num(r.get('xfp_v12'), 2) if pd.notna(r.get('xfp_v12')) else num(r['xfp_v11'], 2)
        # Residual: how far off the primary projection is from per-start actual.
        # Positive = over-projection, Negative = pitcher outperforming.
        residual_val = (
            round(xfp_primary - fp_actual_val, 2)
            if fp_actual_val is not None and gs_val is not None and gs_val >= 5 and xfp_primary is not None
            else None
        )
        # IL feature value for transparency
        il60 = int(r['il_60_stints_lag1']) if pd.notna(r.get('il_60_stints_lag1')) else 0
        records.append({
            'mlbId': int(r['pitcher']),
            'name': r['player_name'],
            'xfpV12': xfp_primary,
            'xfpV11': num(r['xfp_v11'], 2),
            'xfpV85': num(r['xfp_v8_5'], 2),
            'deltaV12V11': round(xfp_primary - num(r['xfp_v11'], 2), 2)
                if (xfp_primary is not None and pd.notna(r['xfp_v11'])) else None,
            'il60Lag1': il60,
            'delta': residual_val,
            'fpTotal': fp_total_val,
            'stuffXfp': num(r['stuff_xfp'], 2),
            'ipPremium': num(r['ip_premium'], 2),
            'ipTrend': r['ip_trend'],
            'kPct': num(r['k_pct_2026'], 3),
            'swstrPct': num(r.get('swstr_pct'), 3),
            'gs': gs_val,
            'fpActual': fp_actual_val,
            'hasFG': bool(r['v11_has_pitching_plus']),
            'rollingIp': num(r['rolling_ip_last5'], 2),
            # ESPN fields (filled from MY_TEAM where available)
            'roster': 'other',          # 'mine' | 'other'
            'espnPos': None,
            'proTeam': None,
            'pctOwned': None,
            'fpProjEspn': None,
            'fpTotalEspn': None,
            'fpPerGameEspn': None,
            'gpEspn': None,
        })

    records.sort(key=lambda x: -x['xfpV11'])
    for i, rec in enumerate(records):
        rec['rank'] = i + 1

    # ESPN merge
    by_key: dict[tuple[str, str], dict] = {xfp_name_key(r['name']): r for r in records}

    my_team_raw = extract_my_team()
    my_team_payload: dict = {'teamName': None, 'pitchers': []}

    if my_team_raw:
        my_team_payload['teamName'] = my_team_raw.get('teamName')
        for p in my_team_raw.get('pitchers', []):
            espn_pos = p.get('espnPos') or ''
            role = 'SP' if 'SP' in espn_pos else ('RP' if 'RP' in espn_pos else (espn_pos or '—'))
            # Only match SPs against the xFP universe (SP-only model).
            xfp_rec = find_xfp_record(p['name'], by_key) if role == 'SP' else None
            if xfp_rec is not None:
                xfp_rec['roster'] = 'mine'
                xfp_rec['espnPos'] = espn_pos
                xfp_rec['proTeam'] = p.get('proTeam')
                xfp_rec['pctOwned'] = p.get('pctOwned') if isinstance(p.get('pctOwned'), (int, float)) else None
                xfp_rec['fpProjEspn'] = p.get('fpProj') if isinstance(p.get('fpProj'), (int, float)) else None
                xfp_rec['fpTotalEspn'] = p.get('fpTotal') if isinstance(p.get('fpTotal'), (int, float)) else None
                xfp_rec['fpPerGameEspn'] = p.get('fpPerGame') if isinstance(p.get('fpPerGame'), (int, float)) else None
                xfp_rec['gpEspn'] = p.get('gp') if isinstance(p.get('gp'), int) else None

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
                'mlbId': xfp_rec['mlbId'] if xfp_rec else None,
                'xfpV11': xfp_rec['xfpV11'] if xfp_rec else None,
                'xfpRank': xfp_rec['rank'] if xfp_rec else None,
                'kPct': xfp_rec['kPct'] if xfp_rec else None,
                'ipTrend': xfp_rec['ipTrend'] if xfp_rec else None,
                'fpActual': xfp_rec['fpActual'] if xfp_rec else None,
                'gs': xfp_rec['gs'] if xfp_rec else None,
            })

    return records, my_team_payload


def build_hitter_records() -> tuple[list[dict], list[dict]]:
    """Returns (hitter_records, my_team_hitter_payload)."""
    if not H2_PROJ_CSV.exists():
        return [], []

    proj = pd.read_csv(H2_PROJ_CSV)

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
        records.append({
            'mlbId':        int(r['batter']),
            'name':         r.get('player_name') or '',
            'pos':          r.get('primary_position') if pd.notna(r.get('primary_position')) else None,
            'fpos':         r.get('fantasy_positions_display') if pd.notna(r.get('fantasy_positions_display')) else None,
            'team':         r.get('team_2026') if pd.notna(r.get('team_2026')) else None,
            'xfpPerPa':     num(r['xfp_h2_per_pa'], 4),
            'coreXfpPerPa': num(r.get('core_xfp_per_pa'), 4),
            'xfpFullFp':    num(r.get('xfp_h2_full_fp'), 2),    # × 3.5 PA/game
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
            'roster':       'other',
            'espnPos':      None,
            'pctOwned':     None,
            'fpProjEspn':   None,
            'fpTotalEspn':  None,
            'fpPerGameEspn':None,
            'gpEspn':       None,
        })

    # Sort by xFP per PA descending and assign ranks
    records.sort(key=lambda x: -(x['xfpPerPa'] if x['xfpPerPa'] is not None else 0))
    for i, rec in enumerate(records):
        rec['rank'] = i + 1

    # ESPN merge — pull MY_TEAM hitters
    by_key: dict[tuple[str, str], dict] = {}
    for r in records:
        # Hitter names are "First Last" (from master_hitter / Chadwick), so
        # we use plv_name_key for both sides.
        by_key[plv_name_key(r['name'])] = r

    my_team_raw = extract_my_team()
    hitter_payload: list[dict] = []
    if my_team_raw:
        for h in my_team_raw.get('hitters', []):
            espn_pos = h.get('espnPos') or h.get('pos') or ''
            xfp_rec = find_xfp_record(h.get('name', '') or h.get('cleanName', ''), by_key)
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
        'nTrain': int(bundle['n_train']),
        'trainingYears': bundle.get('training_years', '2020-2025'),
        'ytdR': round(float(bundle.get('ytd_r_2026', 0)), 3),
        'ytdMae': round(float(bundle.get('ytd_mae_2026', 0)), 3),
        'comparison': bundle.get('comparison'),
    }


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>SP xFP Model — V11 Production</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Source+Serif+4:ital,wght@0,400;0,500;0,600;1,400;1,500&display=swap" rel="stylesheet" />
<style>html,body{margin:0;padding:0;}*{box-sizing:border-box;}</style>
<script>
window.XFP_META = __META_JSON__;
window.XFP_H2_META = __H2_META_JSON__;
window.XFP_PROJECTIONS = __PROJECTIONS_JSON__;
window.XFP_HITTERS = __HITTERS_JSON__;
window.XFP_MY_TEAM = __MY_TEAM_JSON__;
</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react/18.3.1/umd/react.production.min.js" crossorigin></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.3.1/umd/react-dom.production.min.js" crossorigin></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.5/babel.min.js" crossorigin></script>
</head>
<body>
<div id="root"></div>
<script type="text/babel">
// ═══ Constants ════════════════════════════════════════════════════════════════
const TABS = ['my-team', 'projections', 'hitters', 'analysis', 'model'];
const TAB_LABELS = { 'my-team': 'My Team', projections: 'Pitchers', hitters: 'Hitters', analysis: 'Analysis', model: 'Model Info' };
const MONO  = '"IBM Plex Mono", ui-monospace, monospace';
const SERIF = '"Source Serif 4", "Source Serif Pro", "Iowan Old Style", Georgia, serif';

const TIER = (xfp) => {
  if (xfp >= 17) return 'Elite';
  if (xfp >= 14) return 'Strong';
  if (xfp >= 11) return 'Solid';
  return 'Streamer';
};

const K_TIERS = [
  { key: 'all',     label: 'All K%' },
  { key: 'elite',   label: 'Elite K (>28%)',  test: k => k != null && k > 0.28 },
  { key: 'high',    label: 'High K (22-28%)', test: k => k != null && k >= 0.22 && k <= 0.28 },
  { key: 'contact', label: 'Contact (<22%)',  test: k => k != null && k < 0.22 },
];

// ═══ Utilities ════════════════════════════════════════════════════════════════
const fmt = (n, d = 1) => {
  if (n == null || (typeof n === 'number' && Number.isNaN(n))) return '—';
  if (typeof n !== 'number') return n;
  return n.toFixed(d);
};
const fmtPct = (n, d = 1) => n == null ? '—' : (n * 100).toFixed(d) + '%';
const fmtSign = (n, d = 2) => {
  if (n == null) return '—';
  const s = n.toFixed(d);
  return n > 0 ? '+' + s : s;
};

function pearsonR(xs, ys) {
  const n = xs.length;
  if (n < 2) return NaN;
  const mx = xs.reduce((a,b)=>a+b,0)/n, my = ys.reduce((a,b)=>a+b,0)/n;
  let num = 0, dx = 0, dy = 0;
  for (let i=0;i<n;i++){ num += (xs[i]-mx)*(ys[i]-my); dx += (xs[i]-mx)**2; dy += (ys[i]-my)**2; }
  return num / Math.sqrt(dx*dy);
}
function median(arr) {
  const s = [...arr].sort((a,b)=>a-b);
  const n = s.length;
  if (!n) return 0;
  return n % 2 ? s[(n-1)>>1] : (s[n/2-1]+s[n/2])/2;
}

function exportCSV(rows, cols, filename = 'xfp_v11_projections.csv') {
  const escape = v => {
    if (v == null) return '';
    const s = String(v);
    return s.includes(',') || s.includes('"') ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const header = cols.join(',');
  const body = rows.map(r => cols.map(c => escape(r[c])).join(',')).join('\n');
  const blob = new Blob([header + '\n' + body], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

function dataCell(colors, color) {
  return {
    padding: '7px 8px', textAlign: 'right',
    fontFamily: MONO, fontSize: 11, fontVariantNumeric: 'tabular-nums',
    color: color || colors.text,
  };
}
function editorialBtn(colors) {
  return {
    padding: '5px 10px', fontSize: 10, fontFamily: MONO, letterSpacing: 1.2,
    background: colors.panel, color: colors.text,
    border: `1px solid ${colors.border}`, borderRadius: 2,
    cursor: 'pointer', textTransform: 'uppercase', fontWeight: 500,
  };
}
function makeEditorialHeat(dark) {
  return (v, min, max) => {
    if (typeof v !== 'number' || Number.isNaN(v)) return 'transparent';
    const t = Math.max(0, Math.min(1, (v - min) / (max - min)));
    if (dark) {
      return t < 0.5
        ? `oklch(${0.22 + (1 - t * 2) * 0.02} 0 0 / 0)`
        : `oklch(0.55 ${0.04 + (t - 0.5) * 0.18} 35 / ${0.10 + (t - 0.5) * 0.40})`;
    }
    return t < 0.5
      ? `oklch(0.97 0 0 / 0)`
      : `oklch(0.65 ${0.04 + (t - 0.5) * 0.20} 35 / ${0.06 + (t - 0.5) * 0.30})`;
  };
}

// ═══ SortTh ═══════════════════════════════════════════════════════════════════
function SortTh({ col, label, align = 'r', width, sortCol, sortDir, onSort, colors }) {
  const active = sortCol === col;
  return (
    <th onClick={() => onSort(col)} style={{
      textAlign: align === 'l' ? 'left' : 'right', padding: '8px 8px',
      fontSize: 9, fontWeight: 600, letterSpacing: 1.5, textTransform: 'uppercase',
      fontFamily: MONO, whiteSpace: 'nowrap', minWidth: width,
      cursor: 'pointer', userSelect: 'none',
      color: active ? colors.accent : colors.dim,
      background: colors.bg,
    }}>
      {label}{active ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''}
    </th>
  );
}

// ═══ Section heading ══════════════════════════════════════════════════════════
function SectionHeading({ num, label, right, colors }) {
  return (
    <div style={{ padding: '20px 32px 10px', display:'flex', alignItems:'baseline', gap:14 }}>
      <span style={{ fontSize:10, letterSpacing:3, textTransform:'uppercase', color:colors.accent, fontFamily:MONO, flexShrink:0 }}>§ {num}</span>
      <h2 style={{ fontSize:22, fontWeight:400, margin:0, fontStyle:'italic', letterSpacing:-0.3, whiteSpace:'nowrap', flexShrink:0 }}>{label}</h2>
      <div style={{ flex:1, borderBottom:`1px solid ${colors.border}`, marginBottom:6, minWidth:20 }} />
      {right && <span style={{ fontSize:10, color:colors.dim, fontFamily:MONO, letterSpacing:1, whiteSpace:'nowrap', flexShrink:0 }}>{right}</span>}
    </div>
  );
}

// ═══ Projections Table ════════════════════════════════════════════════════════
function ProjectionsTable({ rows, colors, editorialHeat, sortCol, sortDir, onSort, favorites, toggleFavorite, expanded, setExpanded }) {
  return (
    <div style={{ overflow: 'auto' }}>
      <table style={{ width:'100%', borderCollapse:'collapse', fontVariantNumeric:'tabular-nums' }}>
        <thead>
          <tr style={{ borderBottom: `2px solid ${colors.text}` }}>
            <th style={{ padding:'8px 8px', fontSize:11, color:colors.dim, width:30, textAlign:'left' }}>★</th>
            <SortTh col="rank"     label="Rk"        align="l" width={36}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="name"     label="Pitcher"   align="l" width={170} sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="xfpV12"   label="xFP V12"   width={70}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="xfpV11"   label="V11"       width={56}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="il60Lag1" label="IL60"      width={48}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="fpTotal"  label="FP Total"  width={64}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="delta"    label="Δ vs Act"  width={64}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="stuffXfp" label="Stuff"     width={56}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="ipPremium" label="IP Prem"  width={60}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="ipTrend"  label="Trend"     width={70}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="kPct"     label="K%"        width={50}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="swstrPct" label="SwStr%"    width={56}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="gs"       label="GS"        width={36}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="fpActual" label="2026 FP"   width={60}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="roster"  label="Own"        width={56}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <th style={{ padding:'8px 8px', fontSize:9, color:colors.dim, fontWeight:600, letterSpacing:1.5, textTransform:'uppercase', fontFamily:MONO, textAlign:'center', width:30 }}>FG</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p, idx) => {
            const isFav = favorites.includes(p.mlbId);
            const isExp = expanded === p.mlbId;
            const tier = TIER(p.xfpV12);
            const tierColor = tier === 'Elite' ? colors.accent : tier === 'Strong' ? colors.pos : tier === 'Solid' ? colors.text : colors.dim;
            const trendStyle = p.ipTrend === 'HIGH'
              ? { color:colors.pos, border:`1px solid ${colors.pos}` }
              : p.ipTrend === 'LOW'
              ? { color:colors.warn, border:`1px solid ${colors.warn}` }
              : { color:colors.dim, border:`1px solid ${colors.border}` };
            return (
              <React.Fragment key={p.mlbId}>
                <tr onClick={() => setExpanded(isExp ? null : p.mlbId)}
                    style={{ borderBottom: `1px solid ${colors.faint}`, cursor: 'pointer',
                             background: isExp ? colors.panel : 'transparent' }}>
                  <td style={{ padding:'7px 8px', textAlign:'center' }}>
                    <span onClick={(e) => { e.stopPropagation(); toggleFavorite(p.mlbId); }}
                      style={{ color: isFav ? colors.accent : colors.faint,
                               cursor:'pointer', fontSize:13 }}>★</span>
                  </td>
                  <td style={{ padding:'7px 8px', fontSize:14, fontFamily:SERIF, fontStyle:'italic',
                               color: p.rank <= 3 ? colors.accent : colors.dim }}>{p.rank}</td>
                  <td style={{ padding:'7px 8px', whiteSpace:'nowrap' }}>
                    <span style={{ fontSize:14, fontWeight:500 }}>{p.name}</span>
                  </td>
                  <td style={{ padding:'5px 8px', textAlign:'right',
                               background: editorialHeat(p.xfpV12, 8, 17) }}>
                    <span style={{ fontSize:17, fontFamily:SERIF, fontStyle:'italic',
                                   color:tierColor, fontVariantNumeric:'tabular-nums' }}>
                      {fmt(p.xfpV12, 2)}
                    </span>
                  </td>
                  <td style={dataCell(colors, colors.dim)}>{fmt(p.xfpV11, 2)}</td>
                  <td style={dataCell(colors, p.il60Lag1 > 0 ? colors.warn : colors.faint)}>
                    {p.il60Lag1 > 0 ? p.il60Lag1 : '—'}
                  </td>
                  <td style={dataCell(colors, p.fpTotal == null ? colors.faint : colors.text)}>
                    {p.fpTotal == null ? '—' : fmt(p.fpTotal, 1)}
                  </td>
                  <td style={dataCell(colors, p.delta == null ? colors.faint : p.delta > 0.5 ? colors.neg : p.delta < -0.5 ? colors.pos : colors.dim)}>
                    {p.delta == null ? '—' : fmtSign(p.delta, 2)}
                  </td>
                  <td style={dataCell(colors)}>{fmt(p.stuffXfp, 2)}</td>
                  <td style={dataCell(colors, p.ipPremium > 0.1 ? colors.pos : p.ipPremium < -0.1 ? colors.neg : colors.dim)}>
                    {fmtSign(p.ipPremium, 2)}
                  </td>
                  <td style={{ padding:'7px 8px', textAlign:'center' }}>
                    <span style={{ ...trendStyle, padding:'1px 6px', fontFamily:MONO,
                                   fontSize:9, letterSpacing:1, borderRadius:2 }}>
                      {p.ipTrend}
                    </span>
                  </td>
                  <td style={dataCell(colors, p.kPct == null ? colors.faint : p.kPct > 0.28 ? colors.accent : colors.text)}>
                    {p.kPct == null ? '—' : fmtPct(p.kPct, 1)}
                  </td>
                  <td style={dataCell(colors, colors.dim)}>{p.swstrPct == null ? '—' : fmtPct(p.swstrPct, 1)}</td>
                  <td style={dataCell(colors, p.gs == null ? colors.faint : colors.dim)}>{p.gs ?? '—'}</td>
                  <td style={dataCell(colors, p.fpActual == null ? colors.faint : (p.gs ?? 0) >= 5 ? colors.text : colors.dim)}>
                    {(p.gs ?? 0) >= 5 ? fmt(p.fpActual, 2) : '—'}
                  </td>
                  <td style={{ padding:'7px 8px', textAlign:'right' }}>
                    {p.roster === 'mine' ? (
                      <span style={{ padding:'1px 6px', border:`1px solid ${colors.accent}`,
                                     color:colors.accent, fontFamily:MONO, fontSize:9,
                                     letterSpacing:1, borderRadius:2, whiteSpace:'nowrap' }}>
                        ★ MINE
                      </span>
                    ) : (
                      <span style={{ color:colors.faint, fontFamily:MONO, fontSize:9, letterSpacing:1 }}>—</span>
                    )}
                  </td>
                  <td style={{ padding:'7px 8px', textAlign:'center', fontSize:11,
                               color: p.hasFG ? colors.pos : colors.faint }}>
                    {p.hasFG ? '✓' : '·'}
                  </td>
                </tr>
                {isExp && (
                  <tr>
                    <td colSpan={17} style={{ padding:'14px 24px', background:colors.stripe, borderBottom:`1px solid ${colors.faint}` }}>
                      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:24 }}>
                        <div>
                          <div style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO, marginBottom:6 }}>Tier · {tier}</div>
                          <div style={{ fontSize:13, fontStyle:'italic', color:colors.text }}>
                            xFP V11 of <span style={{ color:tierColor, fontWeight:600 }}>{fmt(p.xfpV11, 2)}</span> ranks {p.name} #{p.rank} on the pre-season board.
                          </div>
                          <div style={{ marginTop:8, fontSize:11, color:colors.dim, fontFamily:MONO }}>
                            Stuff-only baseline: {fmt(p.stuffXfp, 2)} ·
                            IP premium: {fmtSign(p.ipPremium, 2)} ·
                            Last-5 IP: {p.rollingIp == null ? '—' : fmt(p.rollingIp, 2)}
                          </div>
                        </div>
                        <div>
                          <div style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO, marginBottom:6 }}>2026 YTD reality</div>
                          <div style={{ display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:'6px 14px' }}>
                            {[['GS', p.gs ?? '—'],
                              ['FP/start', (p.gs ?? 0) >= 5 ? fmt(p.fpActual, 2) : '—'],
                              ['FP total', p.fpTotal == null ? '—' : fmt(p.fpTotal, 1)],
                              ['K%', p.kPct == null ? '—' : fmtPct(p.kPct, 1)],
                              ['SwStr%', p.swstrPct == null ? '—' : fmtPct(p.swstrPct, 1)],
                              ['Δ vs actual', p.delta == null ? '—' : fmtSign(p.delta, 2)],
                              ['Trend', p.ipTrend]].map(([lbl, val]) => (
                              <div key={lbl}>
                                <div style={{ fontSize:8, letterSpacing:2, color:colors.dim, fontFamily:MONO, textTransform:'uppercase' }}>{lbl}</div>
                                <div style={{ fontSize:13, fontFamily:MONO, color:colors.text }}>{val}</div>
                              </div>
                            ))}
                          </div>
                        </div>
                        <div style={{ display:'flex', alignItems:'center', justifyContent:'flex-end', gap:8 }}>
                          <button onClick={(e) => { e.stopPropagation(); toggleFavorite(p.mlbId); }}
                            style={{ ...editorialBtn(colors),
                                     background: isFav ? colors.accent : colors.panel,
                                     color: isFav ? '#fff' : colors.text,
                                     borderColor: isFav ? colors.accent : colors.border }}>
                            ★ {isFav ? 'UNSTAR' : 'STAR'}
                          </button>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ═══ Quadrant chart ═══════════════════════════════════════════════════════════
function QuadrantChart({ data, xKey, yKey, xLabel, yLabel, xCenter, yCenter, quadLabels, colors, highlightId, onHighlight, xDp = 2, yDp = 2 }) {
  const W = 720, H = 460, PAD = { top: 28, right: 130, bottom: 50, left: 70 };
  const cw = W - PAD.left - PAD.right;
  const ch = H - PAD.top - PAD.bottom;

  const valid = data.filter(d => typeof d[xKey] === 'number' && typeof d[yKey] === 'number'
                                 && !Number.isNaN(d[xKey]) && !Number.isNaN(d[yKey]));
  if (valid.length === 0) return (
    <div style={{ padding:32, color:colors.dim, fontStyle:'italic', textAlign:'center' }}>
      No data points (need 2026 GS ≥ 5).
    </div>
  );

  const xs = valid.map(d => d[xKey]);
  const ys = valid.map(d => d[yKey]);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMin = Math.min(...ys), yMax = Math.max(...ys);
  const xPad = (xMax - xMin) * 0.06 || 0.1;
  const yPad = (yMax - yMin) * 0.06 || 0.1;
  const xLo = xMin - xPad, xHi = xMax + xPad;
  const yLo = yMin - yPad, yHi = yMax + yPad;
  const xc = xCenter ?? median(xs);
  const yc = yCenter ?? median(ys);

  const sx = v => PAD.left + ((v - xLo) / (xHi - xLo)) * cw;
  const sy = v => PAD.top + ch - ((v - yLo) / (yHi - yLo)) * ch;

  const xTicks = Array.from({length:5}, (_,i) => xLo + (xHi-xLo)*(i+0.5)/5);
  const yTicks = Array.from({length:5}, (_,i) => yLo + (yHi-yLo)*(i+0.5)/5);

  const hoverPt = highlightId ? valid.find(p => p.mlbId === highlightId) : null;
  let ttx = 0, tty = 0;
  if (hoverPt) {
    const cx = sx(hoverPt[xKey]), cy = sy(hoverPt[yKey]);
    ttx = cx + 12 + 160 > W - PAD.right ? cx - 172 : cx + 12;
    tty = cy - 64 < PAD.top ? cy + 8 : cy - 64;
  }

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display:'block' }}
         onMouseLeave={() => onHighlight(null)}>
      {yTicks.map((v,i) => (
        <line key={`gy${i}`} x1={PAD.left} x2={PAD.left+cw} y1={sy(v)} y2={sy(v)}
              stroke={colors.faint} strokeWidth={0.5} />
      ))}
      {xTicks.map((v,i) => (
        <line key={`gx${i}`} x1={sx(v)} x2={sx(v)} y1={PAD.top} y2={PAD.top+ch}
              stroke={colors.faint} strokeWidth={0.5} />
      ))}
      <line x1={PAD.left} x2={PAD.left+cw} y1={PAD.top+ch} y2={PAD.top+ch} stroke={colors.border} strokeWidth={1} />
      <line x1={PAD.left} x2={PAD.left}     y1={PAD.top}    y2={PAD.top+ch} stroke={colors.border} strokeWidth={1} />

      <line x1={sx(xc)} x2={sx(xc)} y1={PAD.top} y2={PAD.top+ch}
            stroke={colors.dim} strokeWidth={1} strokeDasharray="5 3" opacity={0.55} />
      <line x1={PAD.left} x2={PAD.left+cw} y1={sy(yc)} y2={sy(yc)}
            stroke={colors.dim} strokeWidth={1} strokeDasharray="5 3" opacity={0.55} />

      {/* quadrant labels in corners */}
      {quadLabels && (
        <>
          <text x={PAD.left+cw-6} y={PAD.top+12} textAnchor="end" fontSize={9} fill={colors.pos}
                fontFamily={MONO} letterSpacing={1.5} opacity={0.85}>
            {quadLabels.tr}
          </text>
          <text x={PAD.left+6} y={PAD.top+12} textAnchor="start" fontSize={9} fill={colors.warn}
                fontFamily={MONO} letterSpacing={1.5} opacity={0.85}>
            {quadLabels.tl}
          </text>
          <text x={PAD.left+cw-6} y={PAD.top+ch-6} textAnchor="end" fontSize={9} fill={colors.warn}
                fontFamily={MONO} letterSpacing={1.5} opacity={0.85}>
            {quadLabels.br}
          </text>
          <text x={PAD.left+6} y={PAD.top+ch-6} textAnchor="start" fontSize={9} fill={colors.neg}
                fontFamily={MONO} letterSpacing={1.5} opacity={0.85}>
            {quadLabels.bl}
          </text>
        </>
      )}

      {valid.map(p => {
        const x = p[xKey], y = p[yKey];
        const isHot  = x >= xc && y >= yc;
        const isCold = x <  xc && y <  yc;
        const dotColor = p.highlighted ? colors.accent : isHot ? colors.pos : isCold ? colors.neg : colors.dim;
        const dotR = p.highlighted ? 5.5 : 3.5;
        const dimmed = highlightId && highlightId !== p.mlbId;
        return (
          <g key={p.mlbId} onMouseEnter={() => onHighlight(p.mlbId)}>
            <circle cx={sx(x)} cy={sy(y)} r={dotR} fill={dotColor}
                    opacity={dimmed ? 0.18 : p.highlighted ? 0.95 : 0.65}
                    stroke={highlightId === p.mlbId ? colors.text : 'none'} strokeWidth={1.5}
                    style={{ cursor:'pointer' }} />
            {p.highlighted && !highlightId && (
              <text x={sx(x)+7} y={sy(y)+3} fontSize={8.5} fill={dotColor} fontFamily={MONO}
                    style={{ pointerEvents:'none' }}>
                {p.name.split(',')[0]}
              </text>
            )}
          </g>
        );
      })}

      {hoverPt && (
        <g style={{ pointerEvents:'none' }}>
          <rect x={ttx} y={tty} width={160} height={62} rx={2}
                fill={colors.panel} stroke={colors.border} strokeWidth={1} opacity={0.97} />
          <text x={ttx+7} y={tty+15} fontSize={11} fill={colors.text} fontFamily={SERIF} fontStyle="italic">
            {hoverPt.name}
          </text>
          <text x={ttx+7} y={tty+30} fontSize={9} fill={colors.dim} fontFamily={MONO}>
            {xLabel}: {hoverPt[xKey].toFixed(xDp)}
          </text>
          <text x={ttx+7} y={tty+43} fontSize={9} fill={colors.dim} fontFamily={MONO}>
            {yLabel}: {hoverPt[yKey].toFixed(yDp)}
          </text>
          <text x={ttx+7} y={tty+56} fontSize={9} fill={hoverPt.ipTrend === 'HIGH' ? colors.pos : hoverPt.ipTrend === 'LOW' ? colors.warn : colors.dim} fontFamily={MONO}>
            {hoverPt.ipTrend} · K%: {hoverPt.kPct == null ? '—' : (hoverPt.kPct*100).toFixed(1)}
          </text>
        </g>
      )}

      <text x={PAD.left + cw/2} y={H-12} textAnchor="middle" fontSize={11} fill={colors.dim} fontFamily={MONO}>{xLabel}</text>
      <text x={18} y={PAD.top + ch/2} textAnchor="middle" fontSize={11} fill={colors.dim} fontFamily={MONO}
            transform={`rotate(-90 18 ${PAD.top + ch/2})`}>{yLabel}</text>
      <text x={W - PAD.right - 2} y={PAD.top - 8} textAnchor="end" fontSize={9.5} fill={colors.accent} fontFamily={MONO}>
        r = {isNaN(pearsonR(xs,ys)) ? '—' : pearsonR(xs,ys).toFixed(3)} · n = {valid.length}
      </text>
      {xTicks.map((v,i) => (
        <text key={`tx${i}`} x={sx(v)} y={PAD.top+ch+15} textAnchor="middle" fontSize={9} fill={colors.dim} fontFamily={MONO}>
          {v.toFixed(xDp)}
        </text>
      ))}
      {yTicks.map((v,i) => (
        <text key={`ty${i}`} x={PAD.left-7} y={sy(v)+3} textAnchor="end" fontSize={9} fill={colors.dim} fontFamily={MONO}>
          {v.toFixed(yDp)}
        </text>
      ))}
    </svg>
  );
}

// ═══ K% distribution chart ════════════════════════════════════════════════════
function KDistributionChart({ data, colors }) {
  const W = 720, H = 280, PAD = { top: 28, right: 30, bottom: 50, left: 60 };
  const cw = W - PAD.left - PAD.right;
  const ch = H - PAD.top - PAD.bottom;
  const valid = data.filter(d => d.kPct != null && d.delta != null);
  if (valid.length === 0) return null;

  // Bucket K% into bins from 10% to 38%, mean residual per bucket.
  const lo = 0.10, hi = 0.38, nBins = 14;
  const bins = Array.from({length: nBins}, () => ({ count: 0, deltaSum: 0 }));
  valid.forEach(p => {
    const t = (p.kPct - lo) / (hi - lo);
    const i = Math.max(0, Math.min(nBins-1, Math.floor(t * nBins)));
    bins[i].count += 1;
    bins[i].deltaSum += p.delta;
  });
  const maxCount = Math.max(...bins.map(b => b.count), 1);
  const bw = cw / nBins;

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display:'block' }}>
      <text x={W/2} y={18} textAnchor="middle" fontSize={11} fill={colors.dim} fontFamily={MONO}
            letterSpacing={1.5} textTransform="uppercase">
        K% bucket · bar height = pitcher count · fill = mean (V11 − actual)
      </text>
      {bins.map((b, i) => {
        const x = PAD.left + i * bw;
        const h = (b.count / maxCount) * ch;
        const meanDelta = b.count > 0 ? b.deltaSum / b.count : 0;
        // Positive residual = V11 over-projecting (red), negative = pitchers
        // outperforming projection (green).
        const fill = meanDelta > 0.5 ? colors.neg : meanDelta < -0.5 ? colors.pos : colors.dim;
        const opacity = Math.min(1, 0.3 + Math.abs(meanDelta) * 0.4);
        return (
          <g key={i}>
            <rect x={x+1} y={PAD.top+ch-h} width={bw-2} height={h}
                  fill={fill} opacity={opacity} />
            {b.count > 0 && (
              <text x={x + bw/2} y={PAD.top+ch-h-4} textAnchor="middle" fontSize={8.5}
                    fill={colors.dim} fontFamily={MONO}>
                {meanDelta >= 0 ? '+' : ''}{meanDelta.toFixed(2)}
              </text>
            )}
          </g>
        );
      })}
      <line x1={PAD.left} x2={PAD.left+cw} y1={PAD.top+ch} y2={PAD.top+ch} stroke={colors.border} strokeWidth={1} />
      {[0.12, 0.18, 0.22, 0.28, 0.32, 0.38].map((tk, i) => {
        const x = PAD.left + ((tk - lo) / (hi - lo)) * cw;
        return (
          <text key={i} x={x} y={PAD.top+ch+18} textAnchor="middle" fontSize={9} fill={colors.dim} fontFamily={MONO}>
            {(tk*100).toFixed(0)}%
          </text>
        );
      })}
      <text x={PAD.left+cw/2} y={H-8} textAnchor="middle" fontSize={10} fill={colors.dim} fontFamily={MONO}>K rate</text>
    </svg>
  );
}

// ═══ Filter Bar ═══════════════════════════════════════════════════════════════
function FilterBar({ search, setSearch, ipTrend, setIpTrend, kTier, setKTier,
                     xfpMin, setXfpMin, xfpMax, setXfpMax, favOnly, setFavOnly,
                     roster, setRoster, hasMyTeam, onReset, count, total, colors }) {
  return (
    <div style={{ padding:'10px 32px', display:'flex', gap:14, alignItems:'center',
                  fontSize:10, fontFamily:MONO, textTransform:'uppercase', letterSpacing:1.5,
                  borderBottom:`1px solid ${colors.border}`, background:colors.stripe, flexWrap:'wrap' }}>
      <div style={{ position:'relative' }}>
        <input placeholder="search pitcher..." value={search} onChange={e => setSearch(e.target.value)}
          style={{ padding:'4px 10px 4px 22px', border:`1px solid ${colors.border}`, borderRadius:2,
                   background:colors.panel, color:colors.text, fontSize:11, width:160, outline:'none',
                   fontFamily:SERIF, fontStyle:'italic' }} />
        <svg width="11" height="11" viewBox="0 0 11 11" fill="none" stroke={colors.dim} strokeWidth="1.5"
             style={{ position:'absolute', left:7, top:8 }}>
          <circle cx="4.5" cy="4.5" r="3.5" /><path d="M7.5 7.5l2.5 2.5" strokeLinecap="round" />
        </svg>
      </div>

      <label style={{ color:colors.dim, display:'flex', alignItems:'center', gap:6 }}>Trend
        <select value={ipTrend} onChange={e => setIpTrend(e.target.value)}
          style={{ padding:'3px 6px', border:`1px solid ${colors.border}`, borderRadius:2,
                   background:colors.panel, color:colors.accent, fontFamily:MONO, fontSize:10 }}>
          <option value="all">All</option>
          <option value="HIGH">HIGH (deeper)</option>
          <option value="NORMAL">NORMAL</option>
          <option value="LOW">LOW (managed)</option>
        </select>
      </label>

      <label style={{ color:colors.dim, display:'flex', alignItems:'center', gap:6 }}>K%
        <select value={kTier} onChange={e => setKTier(e.target.value)}
          style={{ padding:'3px 6px', border:`1px solid ${colors.border}`, borderRadius:2,
                   background:colors.panel, color:colors.accent, fontFamily:MONO, fontSize:10 }}>
          {K_TIERS.map(t => <option key={t.key} value={t.key}>{t.label}</option>)}
        </select>
      </label>

      <label style={{ color:colors.dim, display:'flex', alignItems:'center', gap:6 }}>xFP ≥
        <input type="number" value={xfpMin} onChange={e => setXfpMin(+e.target.value || 0)} step="0.5"
          style={{ width:50, padding:'3px 6px', border:`1px solid ${colors.border}`, borderRadius:2,
                   background:colors.panel, color:colors.accent, fontFamily:MONO, fontSize:11, textAlign:'right' }} />
      </label>
      <label style={{ color:colors.dim, display:'flex', alignItems:'center', gap:6 }}>≤
        <input type="number" value={xfpMax} onChange={e => setXfpMax(+e.target.value || 0)} step="0.5"
          style={{ width:50, padding:'3px 6px', border:`1px solid ${colors.border}`, borderRadius:2,
                   background:colors.panel, color:colors.accent, fontFamily:MONO, fontSize:11, textAlign:'right' }} />
      </label>

      {hasMyTeam && (
        <label style={{ color:colors.dim, display:'flex', alignItems:'center', gap:6 }}>Roster
          {[
            { k:'all',   l:'All' },
            { k:'mine',  l:'My Team' },
            { k:'other', l:'Available' },
          ].map(opt => (
            <button key={opt.k} onClick={() => setRoster(opt.k)}
              style={{ padding:'3px 8px', fontSize:10, fontFamily:MONO, letterSpacing:1,
                       textTransform:'uppercase',
                       border:`1px solid ${roster===opt.k ? colors.accent : colors.border}`,
                       borderRadius:2,
                       background: roster===opt.k ? colors.accent : colors.panel,
                       color: roster===opt.k ? '#fff' : colors.dim, cursor:'pointer' }}>
              {opt.l}
            </button>
          ))}
        </label>
      )}

      <button onClick={() => setFavOnly(!favOnly)}
        style={{ padding:'3px 9px', fontSize:10, fontFamily:MONO, letterSpacing:1, textTransform:'uppercase',
                 border:`1px solid ${favOnly ? colors.accent : colors.border}`, borderRadius:2,
                 background: favOnly ? colors.accent : colors.panel,
                 color: favOnly ? '#fff' : colors.dim, cursor:'pointer' }}>
        ★ Favorites
      </button>

      <button onClick={onReset} style={editorialBtn(colors)}>Reset</button>

      <div style={{ flex:1 }} />
      <span style={{ color:colors.dim }}>{count} / {total} pitchers</span>
    </div>
  );
}

// ═══ Watchlist strip ══════════════════════════════════════════════════════════
function WatchlistStrip({ favorites, allRows, toggleFavorite, colors }) {
  const stars = favorites
    .map(id => allRows.find(r => r.mlbId === id))
    .filter(Boolean)
    .sort((a,b) => b.xfpV11 - a.xfpV11);
  return (
    <div style={{ padding:'12px 32px', borderBottom:`1px solid ${colors.border}`,
                  display:'flex', gap:14, alignItems:'center', flexWrap:'wrap' }}>
      <span style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO }}>
        ★ My Watchlist
      </span>
      {stars.length === 0 ? (
        <span style={{ fontStyle:'italic', fontSize:12, color:colors.dim }}>
          None pinned. Click ★ on any row to follow.
        </span>
      ) : stars.map(p => (
        <span key={p.mlbId} style={{
          display:'inline-flex', gap:8, alignItems:'center',
          padding:'3px 10px', borderRadius:2,
          border:`1px solid ${colors.accent}`, whiteSpace:'nowrap',
        }}>
          <span style={{ fontStyle:'italic', fontSize:13 }}>{p.name}</span>
          <span style={{ fontFamily:MONO, fontSize:10, color:colors.accent }}>{fmt(p.xfpV11, 2)}</span>
          <span onClick={() => toggleFavorite(p.mlbId)}
            style={{ color:colors.faint, fontSize:13, lineHeight:1, cursor:'pointer' }}>×</span>
        </span>
      ))}
    </div>
  );
}

// ═══ Main app ═════════════════════════════════════════════════════════════════
function Dashboard({ dark }) {
  const colors = dark ? {
    bg: '#1a1815', panel: '#211e1a', stripe: '#1d1b17', border: '#34302a', text: '#f5f1ea',
    dim: '#8d8579', faint: '#3a352e', accent: '#d97757',
    pos: '#7fb069', neg: '#c1666b', warn: '#d4a945',
  } : {
    bg: '#f7f3ec', panel: '#fdfaf3', stripe: '#f3eee4', border: '#e3dccb', text: '#1a1815',
    dim: '#7a7261', faint: '#d4ccba', accent: '#a8421f',
    pos: '#56753f', neg: '#9d3540', warn: '#a8761f',
  };
  const editorialHeat = makeEditorialHeat(dark);

  const myTeam = window.XFP_MY_TEAM || { teamName: null, pitchers: [] };
  const hasMyTeam = !!(myTeam.teamName && myTeam.pitchers && myTeam.pitchers.length);
  const [activeTab, setActiveTab] = React.useState(hasMyTeam ? 'my-team' : 'projections');

  // Favorites — localStorage-backed
  const [favorites, setFavorites] = React.useState(() => {
    try {
      const raw = localStorage.getItem('xfp_favorites');
      return raw ? JSON.parse(raw) : [];
    } catch { return []; }
  });
  React.useEffect(() => {
    try { localStorage.setItem('xfp_favorites', JSON.stringify(favorites)); } catch {}
  }, [favorites]);
  const toggleFavorite = (id) => setFavorites(prev =>
    prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);

  // Filters (shared between Projections and Analysis)
  const [search, setSearch]     = React.useState('');
  const [ipTrend, setIpTrend]   = React.useState('all');
  const [kTier, setKTier]       = React.useState('all');
  const [xfpMin, setXfpMin]     = React.useState(0);
  const [xfpMax, setXfpMax]     = React.useState(20);
  const [favOnly, setFavOnly]   = React.useState(false);
  const [roster, setRoster]     = React.useState('all'); // 'all' | 'mine' | 'other'

  // Projections sort + expand
  const [sortCol, setSortCol]   = React.useState('xfpV12');
  const [sortDir, setSortDir]   = React.useState('desc');
  const [expanded, setExpanded] = React.useState(null);

  // Analysis hover
  const [hoverId, setHoverId]   = React.useState(null);

  const onReset = () => {
    setSearch(''); setIpTrend('all'); setKTier('all');
    setXfpMin(0); setXfpMax(20); setFavOnly(false); setRoster('all');
  };

  const allRows = window.XFP_PROJECTIONS;
  const meta = window.XFP_META;
  const hitterRows = window.XFP_HITTERS || [];
  const h2Meta = window.XFP_H2_META || null;

  // Apply filters
  const filtered = React.useMemo(() => {
    const kFn = K_TIERS.find(t => t.key === kTier)?.test;
    let rows = allRows.filter(p => {
      if (search && !p.name.toLowerCase().includes(search.toLowerCase())) return false;
      if (ipTrend !== 'all' && p.ipTrend !== ipTrend) return false;
      if (kFn && !kFn(p.kPct)) return false;
      if (p.xfpV11 < xfpMin || p.xfpV11 > xfpMax) return false;
      if (favOnly && !favorites.includes(p.mlbId)) return false;
      if (roster !== 'all' && p.roster !== roster) return false;
      return true;
    });
    return rows;
  }, [allRows, search, ipTrend, kTier, xfpMin, xfpMax, favOnly, favorites, roster]);

  // Sort rows
  const sortedRows = React.useMemo(() => {
    const rows = [...filtered].sort((a, b) => {
      const av = a[sortCol], bv = b[sortCol];
      const aNum = typeof av === 'number' ? av : (av == null ? -Infinity : null);
      const bNum = typeof bv === 'number' ? bv : (bv == null ? -Infinity : null);
      if (typeof av === 'string' && typeof bv === 'string') {
        return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
      }
      const an = aNum == null ? -Infinity : aNum;
      const bn = bNum == null ? -Infinity : bNum;
      return sortDir === 'asc' ? an - bn : bn - an;
    });
    return rows.map((p, i) => ({ ...p, rank: i + 1 }));
  }, [filtered, sortCol, sortDir]);

  function handleSort(col) {
    if (sortCol === col) setSortDir(d => d === 'desc' ? 'asc' : 'desc');
    else { setSortCol(col); setSortDir('desc'); }
  }

  // Analysis tab data points
  const analysisRows = React.useMemo(() =>
    filtered.map(p => ({ ...p, highlighted: favorites.includes(p.mlbId) })),
    [filtered, favorites]);

  const ytdRows = analysisRows.filter(p => p.gs != null && p.gs >= 5 && p.fpActual != null);

  return (
    <div style={{
      background: colors.bg, color: colors.text,
      fontFamily: SERIF, fontSize: 13, lineHeight: 1.5, minHeight: '100vh',
    }}>
      {/* Masthead */}
      <div style={{ padding:'20px 32px 14px', borderBottom:`2px solid ${colors.text}`,
                    display:'flex', alignItems:'baseline', justifyContent:'space-between', gap:24, flexWrap:'wrap' }}>
        <div>
          <div style={{ fontSize:9, letterSpacing:4, textTransform:'uppercase', color:colors.dim, fontFamily:MONO }}>
            V12 PRODUCTION (V11 + IL) · 2026 SEASON · BUILD {meta.trainedDate}
            {hasMyTeam && <span style={{ color:colors.accent, marginLeft:10 }}>· {myTeam.teamName}</span>}
          </div>
          <h1 style={{ fontSize:32, fontWeight:400, margin:'2px 0 0', letterSpacing:-0.5, fontStyle:'italic', whiteSpace:'nowrap' }}>
            SP xFP Model
          </h1>
        </div>
        <div style={{ display:'flex', gap:10, alignItems:'center', fontFamily:MONO, fontSize:10,
                      letterSpacing:1.2, color:colors.dim, textTransform:'uppercase' }}>
          <span>{allRows.length} SPs</span>
          <span style={{ color:colors.faint }}>·</span>
          <span>cross-yr r {meta.crossYearR}</span>
          <span style={{ color:colors.faint }}>·</span>
          <span>YTD r {meta.ytdR}</span>
          <button onClick={() => exportCSV(sortedRows,
            ['rank','mlbId','name','xfpV11','fpTotal','fpActual','delta','stuffXfp','ipPremium','ipTrend','kPct','swstrPct','gs','hasFG'],
            'xfp_v11_projections.csv')}
            style={{ ...editorialBtn(colors), marginLeft:6 }}>CSV</button>
        </div>
      </div>

      {/* Section nav */}
      <div style={{ padding:'10px 32px', borderBottom:`1px solid ${colors.border}`,
                    display:'flex', gap:24, fontSize:10, letterSpacing:2, textTransform:'uppercase',
                    fontFamily:MONO, alignItems:'center', flexWrap:'wrap' }}>
        {TABS.map(t => (
          <span key={t} onClick={() => setActiveTab(t)} style={{
            color: activeTab === t ? colors.text : colors.dim,
            fontWeight: activeTab === t ? 600 : 400,
            cursor: 'pointer',
            borderBottom: activeTab === t ? `2px solid ${colors.accent}` : 'none',
            paddingBottom: 4, marginBottom: -11,
          }}>{TAB_LABELS[t]}</span>
        ))}
      </div>

      {activeTab === 'my-team' && (
        <MyTeamTab myTeam={myTeam} allRows={allRows} colors={colors}
          editorialHeat={editorialHeat} favorites={favorites}
          toggleFavorite={toggleFavorite} setActiveTab={setActiveTab}
          setSearch={setSearch} />
      )}

      {(activeTab === 'projections' || activeTab === 'analysis') && (
        <>
          <FilterBar
            search={search} setSearch={setSearch}
            ipTrend={ipTrend} setIpTrend={setIpTrend}
            kTier={kTier} setKTier={setKTier}
            xfpMin={xfpMin} setXfpMin={setXfpMin}
            xfpMax={xfpMax} setXfpMax={setXfpMax}
            favOnly={favOnly} setFavOnly={setFavOnly}
            roster={roster} setRoster={setRoster} hasMyTeam={hasMyTeam}
            onReset={onReset} count={filtered.length} total={allRows.length} colors={colors} />
          <WatchlistStrip favorites={favorites} allRows={allRows}
            toggleFavorite={toggleFavorite} colors={colors} />
        </>
      )}

      {activeTab === 'projections' && (
        <>
          <SectionHeading num="I" label="Projections Leaderboard"
            right={`SORTED BY ${sortCol.toUpperCase()} ${sortDir === 'desc' ? '↓' : '↑'}`} colors={colors} />
          <div style={{ padding:'0 32px 24px' }}>
            <ProjectionsTable rows={sortedRows} colors={colors} editorialHeat={editorialHeat}
              sortCol={sortCol} sortDir={sortDir} onSort={handleSort}
              favorites={favorites} toggleFavorite={toggleFavorite}
              expanded={expanded} setExpanded={setExpanded} />
            <div style={{ paddingTop:10, fontSize:10, color:colors.dim, fontFamily:MONO,
                          letterSpacing:1, textAlign:'right' }}>
              ↳ CLICK ROW TO EXPAND · ★ TO PIN · CLICK HEADER TO SORT
            </div>
          </div>
        </>
      )}

      {activeTab === 'analysis' && (
        <AnalysisTab rows={analysisRows} ytdRows={ytdRows} colors={colors}
          hoverId={hoverId} setHoverId={setHoverId} setActiveTab={setActiveTab} />
      )}

      {activeTab === 'hitters' && (
        <HittersTab hitters={hitterRows} colors={colors} editorialHeat={editorialHeat}
          favorites={favorites} toggleFavorite={toggleFavorite} h2Meta={h2Meta} />
      )}

      {activeTab === 'model' && (
        <ModelTab meta={meta} h2Meta={h2Meta} colors={colors} />
      )}

      <div style={{ padding:'24px 32px', borderTop:`1px solid ${colors.border}`, marginTop:32,
                    fontSize:10, fontFamily:MONO, color:colors.dim, letterSpacing:1, textTransform:'uppercase' }}>
        Pitchers: V11 (SP only, Statcast + FG Pitching+) · Hitters: H2 (Ridge, 13 features) ·
        <a href="https://github.com/Kejjeh/xfp-model" style={{ color:colors.accent, marginLeft:6 }}>github.com/Kejjeh/xfp-model</a>
      </div>
    </div>
  );
}

// ═══ Analysis tab ═════════════════════════════════════════════════════════════
function AnalysisTab({ rows, ytdRows, colors, hoverId, setHoverId }) {
  return (
    <>
      <SectionHeading num="I" label="Projection vs Reality"
        right={`2026 YTD · n=${ytdRows.length} (gs ≥ 5)`} colors={colors} />
      <div style={{ padding:'0 32px 18px' }}>
        <QuadrantChart data={ytdRows} xKey="xfpV11" yKey="fpActual"
          xLabel="xFP V11 (projected FP/start)" yLabel="2026 actual FP/start"
          colors={colors} highlightId={hoverId} onHighlight={setHoverId}
          xDp={2} yDp={2}
          quadLabels={{ tr:'DELIVERING', tl:'OUTPERFORMING', br:'UNDERPERFORMING', bl:'AVOID' }} />
      </div>

      <SectionHeading num="II" label="Stuff vs Durability"
        right={`n=${rows.length}`} colors={colors} />
      <div style={{ padding:'0 32px 18px' }}>
        <QuadrantChart data={rows} xKey="stuffXfp" yKey="ipPremium"
          xLabel="Stuff xFP (pure stuff @ league avg IP)"
          yLabel="IP premium (FP from going deeper)"
          xCenter={null} yCenter={0}
          colors={colors} highlightId={hoverId} onHighlight={setHoverId}
          xDp={2} yDp={2}
          quadLabels={{ tr:'WORKHORSES', tl:'VOLUME ARMS', br:'STUFF SPECIALISTS', bl:'STREAMERS' }} />
      </div>

      <SectionHeading num="III" label="K% Residual · V11 vs Actual"
        right="bar fill = mean (V11 − actual FP/start)" colors={colors} />
      <div style={{ padding:'0 32px 32px' }}>
        <KDistributionChart data={rows} colors={colors} />
        <div style={{ paddingTop:12, fontSize:11, color:colors.dim, fontStyle:'italic' }}>
          Each bar = pitcher count in that K-bucket. Fill color = average residual
          (V11 expected − 2026 actual FP/start) across pitchers with ≥ 5 GS.
          Red = V11 over-projecting; green = pitchers outperforming projection.
        </div>
      </div>
    </>
  );
}

// ═══ Hitters tab ══════════════════════════════════════════════════════════════
function HittersTab({ hitters, colors, editorialHeat, favorites, toggleFavorite, h2Meta }) {
  const [hSort, setHSort] = React.useState({ col: 'xfpPerPa', dir: 'desc' });
  const [hPos,  setHPos]  = React.useState('all');     // 'all' | 'C' | '1B' | ... | 'OF' | 'DH'
  const [hMinPa, setHMinPa] = React.useState(50);
  const [hRoster, setHRoster] = React.useState('all'); // 'all' | 'mine' | 'other'
  const [hCohort, setHCohort] = React.useState('all'); // 'all' | 'blended' | '2025_only' | '2026_only'

  const POS_OPTIONS = ['C', '1B', '2B', '3B', 'SS', 'OF', 'DH'];

  const hasMine = hitters.some(h => h.roster === 'mine');

  // Filter
  const filtered = hitters.filter(h => {
    if (hPos !== 'all') {
      const pos = h.pos || '';
      const fpos = (h.fpos || '').split(/[,\s|]+/).map(s => s.trim());
      if (pos !== hPos && !fpos.includes(hPos)) return false;
    }
    if (hRoster === 'mine' && h.roster !== 'mine') return false;
    if (hRoster === 'other' && h.roster === 'mine') return false;
    if (hCohort !== 'all' && h.cohort !== hCohort) return false;
    if (h.pa != null && h.pa < hMinPa) return false;
    if (h.pa == null && hMinPa > 0) return false;  // skip 2025-only when min PA > 0
    return true;
  });
  const sorted = sortRows(filtered, hSort.col, hSort.dir);

  function handleSort(col) {
    if (hSort.col === col) setHSort({ col, dir: hSort.dir === 'desc' ? 'asc' : 'desc' });
    else setHSort({ col, dir: 'desc' });
  }

  return (
    <>
      {/* Filter bar */}
      <div style={{ padding:'10px 32px', display:'flex', gap:14, alignItems:'center',
                    fontSize:10, fontFamily:MONO, textTransform:'uppercase', letterSpacing:1.5,
                    borderBottom:`1px solid ${colors.border}`, background:colors.stripe, flexWrap:'wrap' }}>
        <div style={{ display:'flex', gap:4, alignItems:'center' }}>
          <span style={{ color:colors.dim, marginRight:4 }}>Pos</span>
          {['All', ...POS_OPTIONS].map(p => {
            const active = (p === 'All' && hPos === 'all') || hPos === p;
            return (
              <span key={p} onClick={() => setHPos(p === 'All' ? 'all' : p)} style={{
                padding:'2px 7px', borderRadius:2, cursor:'pointer', fontSize:10,
                fontFamily:MONO, letterSpacing:1, textTransform:'uppercase',
                border:`1px solid ${active ? colors.accent : colors.border}`,
                color: active ? colors.accent : colors.dim,
                background: active ? `${colors.accent}18` : 'transparent',
              }}>{p}</span>
            );
          })}
        </div>
        <label style={{ color:colors.dim, display:'flex', alignItems:'center', gap:6 }}>Min PA
          <input type="number" value={hMinPa} onChange={e => setHMinPa(+e.target.value || 0)}
            style={{ width:48, padding:'2px 6px', border:`1px solid ${colors.border}`, borderRadius:2,
                     background:colors.panel, color:colors.accent, fontFamily:MONO, fontSize:11, textAlign:'right' }} />
        </label>
        <label style={{ color:colors.dim, display:'flex', alignItems:'center', gap:6 }}>Cohort
          <select value={hCohort} onChange={e => setHCohort(e.target.value)}
            style={{ padding:'2px 4px', border:`1px solid ${colors.border}`, borderRadius:2,
                     background:colors.panel, color:colors.accent, fontFamily:MONO, fontSize:11 }}>
            <option value="all">All</option>
            <option value="blended">Blended (25+26)</option>
            <option value="2025_only">2025 only</option>
            <option value="2026_only">2026 only</option>
          </select>
        </label>
        {hasMine && (
          <label style={{ color:colors.dim, display:'flex', alignItems:'center', gap:6 }}>Roster
            {[
              { k:'all',   l:'All' },
              { k:'mine',  l:'My Team' },
              { k:'other', l:'Available' },
            ].map(opt => (
              <button key={opt.k} onClick={() => setHRoster(opt.k)}
                style={{ padding:'3px 8px', fontSize:10, fontFamily:MONO, letterSpacing:1, textTransform:'uppercase',
                         border:`1px solid ${hRoster===opt.k ? colors.accent : colors.border}`, borderRadius:2,
                         background: hRoster===opt.k ? colors.accent : colors.panel,
                         color: hRoster===opt.k ? '#fff' : colors.dim, cursor:'pointer' }}>{opt.l}</button>
            ))}
          </label>
        )}
        <button onClick={() => { setHPos('all'); setHMinPa(50); setHRoster('all'); setHCohort('all'); }}
          style={editorialBtn(colors)}>Reset</button>
        <div style={{ flex:1 }} />
        <span style={{ color:colors.dim }}>{filtered.length} / {hitters.length} hitters</span>
      </div>

      <SectionHeading num="I" label="Hitter Projections (xFP H2)"
        right={`SORTED BY ${hSort.col.toUpperCase()} ${hSort.dir === 'desc' ? '↓' : '↑'}`} colors={colors} />
      <div style={{ padding:'0 32px 24px', overflow:'auto' }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontVariantNumeric:'tabular-nums' }}>
          <thead>
            <tr style={{ borderBottom:`2px solid ${colors.text}` }}>
              <th style={{ padding:'8px 8px', textAlign:'left', fontSize:9, color:colors.dim,
                           fontWeight:600, letterSpacing:1.5, textTransform:'uppercase', fontFamily:MONO, width:30 }}>★</th>
              <SortTh col="rank"          label="Rk"        align="l" width={36}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="name"          label="Hitter"    align="l" width={170} sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="pos"           label="Pos"       align="l" width={48}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="team"          label="Tm"        align="l" width={42}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="xfpPerPa"      label="xFP/PA"    width={70}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="xfpFullFp"     label="xFP/G"     width={64}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="coreXfpPerPa"  label="Core/PA"   width={64}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="paPremium"     label="PA Prem"   width={64}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="pa"            label="PA"        width={42}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="fpPerPaActual" label="Act/PA"    width={64}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="delta"         label="Δ vs Act"  width={68}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="fpTotal"       label="FP Tot"    width={56}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="hr"            label="HR"        width={36}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="cohort"        label="Cohort"    align="l" width={70}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="roster"        label="Own"       width={56}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
            </tr>
          </thead>
          <tbody>
            {sorted.map((h, idx) => {
              const isFav = favorites.includes(h.mlbId);
              const cohortColor = h.cohort === 'blended' ? colors.pos
                : h.cohort === '2026_only' ? colors.warn
                : h.cohort === '2025_only' ? colors.dim : colors.faint;
              return (
                <tr key={h.mlbId} style={{ borderBottom:`1px solid ${colors.faint}` }}>
                  <td style={{ padding:'7px 8px', textAlign:'center' }}>
                    <span onClick={() => toggleFavorite(h.mlbId)}
                      style={{ color: isFav ? colors.accent : colors.faint, cursor:'pointer', fontSize:13 }}>★</span>
                  </td>
                  <td style={{ padding:'7px 8px', fontSize:14, fontFamily:SERIF, fontStyle:'italic',
                               color: h.rank <= 3 ? colors.accent : colors.dim }}>{h.rank}</td>
                  <td style={{ padding:'7px 8px', whiteSpace:'nowrap' }}>
                    <span style={{ fontSize:14, fontWeight:500 }}>{h.name}</span>
                  </td>
                  <td style={{ padding:'7px 8px', fontSize:11, color:colors.dim, fontFamily:MONO }}>{h.pos || '—'}</td>
                  <td style={{ padding:'7px 8px', fontSize:11, color:colors.dim, fontFamily:MONO }}>{h.team || '—'}</td>
                  <td style={{ padding:'5px 8px', textAlign:'right',
                               background: editorialHeat(h.xfpPerPa, 0.3, 0.85) }}>
                    <span style={{ fontSize:16, fontFamily:SERIF, fontStyle:'italic',
                                   color: h.xfpPerPa != null ? colors.accent : colors.faint,
                                   fontVariantNumeric:'tabular-nums' }}>
                      {h.xfpPerPa == null ? '—' : h.xfpPerPa.toFixed(3)}
                    </span>
                  </td>
                  <td style={dataCell(colors)}>{h.xfpFullFp == null ? '—' : h.xfpFullFp.toFixed(2)}</td>
                  <td style={dataCell(colors, colors.dim)}>{h.coreXfpPerPa == null ? '—' : h.coreXfpPerPa.toFixed(3)}</td>
                  <td style={dataCell(colors, h.paPremium > 0.05 ? colors.pos : h.paPremium < -0.05 ? colors.neg : colors.dim)}>
                    {h.paPremium == null ? '—' : fmtSign(h.paPremium, 2)}
                  </td>
                  <td style={dataCell(colors, colors.dim)}>{h.pa ?? '—'}</td>
                  <td style={dataCell(colors, h.fpPerPaActual == null ? colors.faint : colors.text)}>
                    {h.fpPerPaActual == null ? '—' : h.fpPerPaActual.toFixed(3)}
                  </td>
                  <td style={dataCell(colors, h.delta == null ? colors.faint : h.delta > 0.05 ? colors.neg : h.delta < -0.05 ? colors.pos : colors.dim)}>
                    {h.delta == null ? '—' : fmtSign(h.delta, 3)}
                  </td>
                  <td style={dataCell(colors)}>{h.fpTotal == null ? '—' : h.fpTotal.toFixed(0)}</td>
                  <td style={dataCell(colors, colors.dim)}>{h.hr ?? '—'}</td>
                  <td style={{ padding:'7px 8px', textAlign:'left', fontSize:9, fontFamily:MONO,
                               letterSpacing:1, color: cohortColor }}>{h.cohort || '—'}</td>
                  <td style={{ padding:'7px 8px', textAlign:'right' }}>
                    {h.roster === 'mine' ? (
                      <span style={{ padding:'1px 6px', border:`1px solid ${colors.accent}`,
                                     color:colors.accent, fontFamily:MONO, fontSize:9,
                                     letterSpacing:1, borderRadius:2, whiteSpace:'nowrap' }}>★ MINE</span>
                    ) : (
                      <span style={{ color:colors.faint, fontFamily:MONO, fontSize:9 }}>—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div style={{ paddingTop:10, fontSize:10, color:colors.dim, fontFamily:MONO,
                      letterSpacing:1, textAlign:'right' }}>
          ↳ CLICK ANY HEADER TO SORT · ★ TO PIN · COHORT = BLENDED IS MOST RELIABLE
        </div>
        {h2Meta && (
          <div style={{ marginTop:14, padding:'8px 12px', background:colors.stripe, borderLeft:`3px solid ${colors.accent}`,
                        fontSize:11, color:colors.dim, fontStyle:'italic', lineHeight:1.5 }}>
            xFP H2 (Ridge, {h2Meta.features.length} features). Cross-year r {h2Meta.crossYearR},
            YTD r {h2Meta.ytdR} (n={h2Meta.ytdN}, PA ≥ 80).
            Trained on {h2Meta.nTrain} hitter-seasons, mid-season blend with Bayesian shrinkage on contact-quality metrics.
          </div>
        )}
      </div>
    </>
  );
}


// Generic sort: numeric → numeric, string → localeCompare, nulls always last.
function sortRows(rows, col, dir) {
  return [...rows].sort((a, b) => {
    const av = a[col], bv = b[col];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === 'string' && typeof bv === 'string') {
      return dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
    }
    return dir === 'asc' ? av - bv : bv - av;
  });
}

// ═══ My Team tab ══════════════════════════════════════════════════════════════
function MyTeamTab({ myTeam, allRows, colors, editorialHeat, favorites, toggleFavorite, setActiveTab, setSearch }) {
  const rotation = myTeam.pitchers.filter(p => p.role === 'SP');
  const bullpen  = myTeam.pitchers.filter(p => p.role === 'RP');

  // Per-table sort state — each table can be sorted independently.
  const [rotSort, setRotSort]     = React.useState({ col: 'xfpV11',   dir: 'desc' });
  const [availSort, setAvailSort] = React.useState({ col: 'xfpV11',   dir: 'desc' });
  const [bpSort, setBpSort]       = React.useState({ col: 'fpTotal',  dir: 'desc' });

  function makeSortHandler(state, setState) {
    return (col) => {
      if (state.col === col) setState({ col, dir: state.dir === 'desc' ? 'asc' : 'desc' });
      else setState({ col, dir: 'desc' });
    };
  }

  // Mean xFP of my rotation (matched only)
  const matched = rotation.filter(p => p.xfpV11 != null);
  const meanXfp = matched.length
    ? matched.reduce((s, p) => s + p.xfpV11, 0) / matched.length
    : null;

  // Add/Drop suggestions: top non-roster SPs vs bottom roster SPs
  const myIds = new Set(myTeam.pitchers.map(p => p.mlbId).filter(Boolean));
  const allAvailable = allRows.filter(r => !myIds.has(r.mlbId));
  const available = allAvailable.slice(0, 25); // top 25 by xFP V11 (allRows is pre-sorted)
  const myWeakest = matched.length
    ? [...matched].sort((a, b) => a.xfpV11 - b.xfpV11).slice(0, 5)
    : [];
  const swaps = [];
  for (const drop of myWeakest) {
    for (const add of available) {
      if (add.xfpV11 > drop.xfpV11 + 0.5) {
        swaps.push({ drop, add, gain: add.xfpV11 - drop.xfpV11 });
        break; // best available drop pair
      }
    }
  }
  swaps.sort((a, b) => b.gain - a.gain);

  // Sorted views for the three on-screen tables.
  const rotationDisplay = sortRows(rotation, rotSort.col, rotSort.dir);
  const availableDisplay = sortRows(allAvailable, availSort.col, availSort.dir).slice(0, 15);
  const bullpenDisplay  = sortRows(bullpen, bpSort.col, bpSort.dir);

  const handleRotSort   = makeSortHandler(rotSort,   setRotSort);
  const handleAvailSort = makeSortHandler(availSort, setAvailSort);
  const handleBpSort    = makeSortHandler(bpSort,    setBpSort);

  return (
    <>
      {/* Hero */}
      <div style={{ padding:'24px 32px 18px', borderBottom:`1px solid ${colors.border}`,
                    display:'grid', gridTemplateColumns:'1.2fr 1fr', gap:32 }}>
        <div>
          <div style={{ fontSize:10, letterSpacing:3, textTransform:'uppercase',
                        color:colors.accent, fontFamily:MONO, marginBottom:8 }}>
            Lede · ESPN Connector
          </div>
          <h2 style={{ fontSize:26, fontWeight:400, lineHeight:1.15, margin:0, letterSpacing:-0.5 }}>
            <span style={{ fontStyle:'italic' }}>{myTeam.teamName}</span> ·{' '}
            <span style={{ color:colors.accent, fontVariantNumeric:'tabular-nums' }}>
              {rotation.length}
            </span> SP /{' '}
            <span style={{ color:colors.accent, fontVariantNumeric:'tabular-nums' }}>
              {bullpen.length}
            </span> RP
          </h2>
          <p style={{ fontSize:13, color:colors.dim, margin:'8px 0 0', fontStyle:'italic', lineHeight:1.5 }}>
            Rotation averages an xFP V11 of{' '}
            <span style={{ color:colors.accent, fontVariantNumeric:'tabular-nums' }}>
              {meanXfp == null ? '—' : meanXfp.toFixed(2)}
            </span>{' '}FP/start across {matched.length} of {rotation.length} arms with V11 coverage.
            {' '}{swaps.length > 0 && (<>The model flags <strong>{swaps.length}</strong> potential xFP-positive swaps below.</>)}
          </p>
        </div>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'12px 24px' }}>
          {[
            { lbl:'Top Rotation Arm',
              p: matched[0] ? matched.reduce((b,p) => p.xfpV11 > b.xfpV11 ? p : b, matched[0]) : null,
              vKey: 'xfpV11' },
            { lbl:'Weakest Slot',
              p: myWeakest[0] || null, vKey: 'xfpV11' },
            { lbl:'Best Available',
              p: available[0] || null, vKey: 'xfpV11' },
            { lbl:'Best Swap Gain',
              custom: swaps[0]
                ? `+${swaps[0].gain.toFixed(2)} FP/start (${(swaps[0].add.name || '').split(',')[0]} → ${(swaps[0].drop.name || '').split(' ').pop()})`
                : '—' },
          ].map((c, i) => (
            <div key={i} style={{ borderTop:`1px solid ${colors.faint}`, paddingTop:6 }}>
              <div style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO }}>{c.lbl}</div>
              {c.custom != null ? (
                <div style={{ fontSize:14, marginTop:4, color:colors.accent, fontFamily:SERIF, fontStyle:'italic' }}>
                  {c.custom}
                </div>
              ) : c.p ? (
                <>
                  <div style={{ fontSize:20, fontFamily:SERIF, fontStyle:'italic', color:colors.accent, lineHeight:1, marginTop:4 }}>
                    {fmt(c.p[c.vKey], 2)}
                  </div>
                  <div style={{ fontSize:11, marginTop:4 }}>{c.p.name}</div>
                </>
              ) : (
                <div style={{ fontSize:14, color:colors.dim, marginTop:4 }}>—</div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Rotation table */}
      <SectionHeading num="I" label="My Rotation"
        right={`${rotation.length} SP · CLICK ANY HEADER TO SORT`} colors={colors} />
      <div style={{ padding:'0 32px 8px', overflow:'auto' }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontVariantNumeric:'tabular-nums' }}>
          <thead>
            <tr style={{ borderBottom:`2px solid ${colors.text}` }}>
              <th style={{ padding:'8px 8px', textAlign:'left', fontSize:9, color:colors.dim,
                           fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase', fontWeight:600 }}>#</th>
              <SortTh col="name"      label="Pitcher"   align="l" width={170} sortCol={rotSort.col} sortDir={rotSort.dir} onSort={handleRotSort} colors={colors} />
              <SortTh col="proTeam"   label="Team"      align="l" width={50}  sortCol={rotSort.col} sortDir={rotSort.dir} onSort={handleRotSort} colors={colors} />
              <SortTh col="xfpV11"    label="xFP V11"   width={70}  sortCol={rotSort.col} sortDir={rotSort.dir} onSort={handleRotSort} colors={colors} />
              <SortTh col="xfpRank"   label="Rank"      width={50}  sortCol={rotSort.col} sortDir={rotSort.dir} onSort={handleRotSort} colors={colors} />
              <SortTh col="kPct"      label="K%"        width={50}  sortCol={rotSort.col} sortDir={rotSort.dir} onSort={handleRotSort} colors={colors} />
              <SortTh col="ipTrend"   label="Trend"     width={70}  sortCol={rotSort.col} sortDir={rotSort.dir} onSort={handleRotSort} colors={colors} />
              <SortTh col="gs"        label="GS"        width={36}  sortCol={rotSort.col} sortDir={rotSort.dir} onSort={handleRotSort} colors={colors} />
              <SortTh col="fpActual"  label="2026 FP"   width={60}  sortCol={rotSort.col} sortDir={rotSort.dir} onSort={handleRotSort} colors={colors} />
              <SortTh col="fpPerGame" label="ESPN FP/G" width={70}  sortCol={rotSort.col} sortDir={rotSort.dir} onSort={handleRotSort} colors={colors} />
              <SortTh col="pctOwned"  label="% Owned"   width={64}  sortCol={rotSort.col} sortDir={rotSort.dir} onSort={handleRotSort} colors={colors} />
              <th style={{ padding:'8px 8px', textAlign:'right', fontSize:9, color:colors.dim,
                           fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase', fontWeight:600 }}></th>
            </tr>
          </thead>
          <tbody>
            {rotationDisplay.map((p, idx) => {
              const isFav = p.mlbId != null && favorites.includes(p.mlbId);
              const trendStyle = p.ipTrend === 'HIGH'
                ? { color:colors.pos, border:`1px solid ${colors.pos}` }
                : p.ipTrend === 'LOW'
                ? { color:colors.warn, border:`1px solid ${colors.warn}` }
                : { color:colors.dim, border:`1px solid ${colors.border}` };
              return (
                <tr key={p.name} style={{ borderBottom:`1px solid ${colors.faint}` }}>
                  <td style={{ padding:'7px 8px', fontSize:14, fontFamily:SERIF, fontStyle:'italic',
                               color: idx < 3 ? colors.accent : colors.dim }}>{idx + 1}</td>
                  <td style={{ padding:'7px 8px', whiteSpace:'nowrap' }}>
                    {p.mlbId != null && (
                      <span onClick={() => toggleFavorite(p.mlbId)}
                        style={{ color: isFav ? colors.accent : colors.faint,
                                 cursor:'pointer', fontSize:11, marginRight:6 }}>★</span>
                    )}
                    <span style={{ fontSize:14, fontWeight:500 }}>{p.name}</span>
                  </td>
                  <td style={{ padding:'7px 8px', fontSize:11, color:colors.dim, fontFamily:MONO }}>
                    {p.proTeam || '—'}
                  </td>
                  <td style={{ padding:'5px 8px', textAlign:'right',
                               background: editorialHeat(p.xfpV11, 8, 17) }}>
                    <span style={{ fontSize:17, fontFamily:SERIF, fontStyle:'italic',
                                   color: p.xfpV11 != null ? colors.accent : colors.faint }}>
                      {p.xfpV11 == null ? '—' : fmt(p.xfpV11, 2)}
                    </span>
                  </td>
                  <td style={dataCell(colors, colors.dim)}>
                    {p.xfpRank == null ? '—' : '#' + p.xfpRank}
                  </td>
                  <td style={dataCell(colors, p.kPct == null ? colors.faint : colors.text)}>
                    {p.kPct == null ? '—' : fmtPct(p.kPct, 1)}
                  </td>
                  <td style={{ padding:'7px 8px', textAlign:'right' }}>
                    {p.ipTrend ? (
                      <span style={{ ...trendStyle, padding:'1px 6px', fontFamily:MONO,
                                     fontSize:9, letterSpacing:1, borderRadius:2 }}>
                        {p.ipTrend}
                      </span>
                    ) : <span style={{ color:colors.faint }}>—</span>}
                  </td>
                  <td style={dataCell(colors, colors.dim)}>{p.gs == null ? '—' : p.gs}</td>
                  <td style={dataCell(colors, p.fpActual == null ? colors.faint : colors.text)}>
                    {p.fpActual == null || (p.gs ?? 0) < 5 ? '—' : fmt(p.fpActual, 2)}
                  </td>
                  <td style={dataCell(colors, colors.dim)}>
                    {p.fpPerGame == null ? '—' : fmt(p.fpPerGame, 2)}
                  </td>
                  <td style={dataCell(colors, colors.dim)}>
                    {p.pctOwned == null ? '—' : fmt(p.pctOwned, 1) + '%'}
                  </td>
                  <td style={{ padding:'7px 8px', textAlign:'right' }}>
                    {p.xfpV11 == null ? (
                      <span style={{ color:colors.warn, fontSize:9, fontFamily:MONO,
                                     letterSpacing:1, padding:'1px 6px',
                                     border:`1px solid ${colors.warn}`, borderRadius:2 }}>
                        NO V11
                      </span>
                    ) : (
                      <span style={{ color:colors.faint, fontSize:9, fontFamily:MONO }}>—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div style={{ paddingTop:6, fontSize:10, color:colors.dim, fontFamily:MONO,
                      letterSpacing:1, fontStyle:'italic' }}>
          ↳ "NO V11" tag = pitcher not in V11 universe (rookie debut without FG Pitching+ history)
        </div>
      </div>

      {/* Add/Drop suggestions */}
      <SectionHeading num="II" label="Add / Drop Targets"
        right={swaps.length > 0 ? `${swaps.length} SUGGESTED` : 'NO POSITIVE SWAPS'} colors={colors} />
      <div style={{ padding:'0 32px 8px' }}>
        {swaps.length === 0 ? (
          <div style={{ padding:'14px 0', fontSize:13, fontStyle:'italic', color:colors.dim }}>
            Your rotation already projects above the available pool. No xFP-positive swaps to flag.
          </div>
        ) : (
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(360px, 1fr))', gap:14 }}>
            {swaps.map((s, i) => (
              <div key={i} style={{ borderTop:`2px solid ${colors.accent}`, paddingTop:10 }}>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline' }}>
                  <span style={{ fontSize:9, letterSpacing:2, color:colors.dim, fontFamily:MONO,
                                 textTransform:'uppercase' }}>Swap #{i + 1}</span>
                  <span style={{ fontSize:14, fontStyle:'italic', fontFamily:SERIF, color:colors.pos }}>
                    +{s.gain.toFixed(2)} FP/start
                  </span>
                </div>
                <div style={{ marginTop:8, display:'grid', gridTemplateColumns:'1fr 24px 1fr', gap:8, alignItems:'center' }}>
                  <div style={{ padding:'8px 10px', border:`1px solid ${colors.neg}`, borderRadius:2, background:colors.stripe }}>
                    <div style={{ fontSize:9, letterSpacing:2, color:colors.neg, fontFamily:MONO,
                                  textTransform:'uppercase' }}>Drop</div>
                    <div style={{ fontSize:13, fontStyle:'italic', fontFamily:SERIF, color:colors.text, marginTop:2 }}>
                      {s.drop.name}
                    </div>
                    <div style={{ fontSize:11, color:colors.dim, fontFamily:MONO, marginTop:4 }}>
                      xFP {fmt(s.drop.xfpV11, 2)} · {s.drop.ipTrend ?? '—'} · #{s.drop.xfpRank ?? '—'}
                    </div>
                  </div>
                  <div style={{ textAlign:'center', fontSize:18, color:colors.accent }}>→</div>
                  <div style={{ padding:'8px 10px', border:`1px solid ${colors.pos}`, borderRadius:2, background:colors.stripe }}>
                    <div style={{ fontSize:9, letterSpacing:2, color:colors.pos, fontFamily:MONO,
                                  textTransform:'uppercase' }}>Add</div>
                    <div style={{ fontSize:13, fontStyle:'italic', fontFamily:SERIF, color:colors.text, marginTop:2 }}>
                      {s.add.name}
                    </div>
                    <div style={{ fontSize:11, color:colors.dim, fontFamily:MONO, marginTop:4 }}>
                      xFP {fmt(s.add.xfpV11, 2)} · {s.add.ipTrend} · #{s.add.rank}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <div style={{ padding:'4px 32px 18px', fontSize:11, fontStyle:'italic', color:colors.dim }}>
        Caveat: "available" = any SP not currently on your roster. Some may be rostered on other
        league teams. Verify ownership in ESPN before adding/dropping.
      </div>

      {/* Available leaderboard */}
      <SectionHeading num="III" label="Top Available SPs"
        right="NOT ON YOUR ROSTER · CLICK ANY HEADER TO SORT" colors={colors} />
      <div style={{ padding:'0 32px 8px' }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontVariantNumeric:'tabular-nums' }}>
          <thead>
            <tr style={{ borderBottom:`2px solid ${colors.text}` }}>
              <th style={{ padding:'8px 8px', textAlign:'left', fontSize:9, color:colors.dim,
                           fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase', fontWeight:600 }}>#</th>
              <SortTh col="name"     label="Pitcher"   align="l" width={170} sortCol={availSort.col} sortDir={availSort.dir} onSort={handleAvailSort} colors={colors} />
              <SortTh col="xfpV11"   label="xFP V11"   width={70}  sortCol={availSort.col} sortDir={availSort.dir} onSort={handleAvailSort} colors={colors} />
              <SortTh col="stuffXfp" label="Stuff"     width={56}  sortCol={availSort.col} sortDir={availSort.dir} onSort={handleAvailSort} colors={colors} />
              <SortTh col="ipPremium" label="IP Prem"  width={64}  sortCol={availSort.col} sortDir={availSort.dir} onSort={handleAvailSort} colors={colors} />
              <SortTh col="ipTrend"  label="Trend"     width={70}  sortCol={availSort.col} sortDir={availSort.dir} onSort={handleAvailSort} colors={colors} />
              <SortTh col="kPct"     label="K%"        width={50}  sortCol={availSort.col} sortDir={availSort.dir} onSort={handleAvailSort} colors={colors} />
              <SortTh col="swstrPct" label="SwStr%"    width={56}  sortCol={availSort.col} sortDir={availSort.dir} onSort={handleAvailSort} colors={colors} />
              <SortTh col="gs"       label="GS"        width={36}  sortCol={availSort.col} sortDir={availSort.dir} onSort={handleAvailSort} colors={colors} />
              <SortTh col="fpActual" label="2026 FP"   width={60}  sortCol={availSort.col} sortDir={availSort.dir} onSort={handleAvailSort} colors={colors} />
            </tr>
          </thead>
          <tbody>
            {availableDisplay.map((p, idx) => {
              const isFav = favorites.includes(p.mlbId);
              const trendStyle = p.ipTrend === 'HIGH'
                ? { color:colors.pos, border:`1px solid ${colors.pos}` }
                : p.ipTrend === 'LOW'
                ? { color:colors.warn, border:`1px solid ${colors.warn}` }
                : { color:colors.dim, border:`1px solid ${colors.border}` };
              return (
                <tr key={p.mlbId} style={{ borderBottom:`1px solid ${colors.faint}` }}>
                  <td style={{ padding:'7px 8px', fontSize:14, fontFamily:SERIF, fontStyle:'italic',
                               color: idx < 3 ? colors.accent : colors.dim }}>{idx + 1}</td>
                  <td style={{ padding:'7px 8px', whiteSpace:'nowrap' }}>
                    <span onClick={() => toggleFavorite(p.mlbId)}
                      style={{ color: isFav ? colors.accent : colors.faint,
                               cursor:'pointer', fontSize:11, marginRight:6 }}>★</span>
                    <span style={{ fontSize:14, fontWeight:500 }}>{p.name}</span>
                  </td>
                  <td style={{ padding:'5px 8px', textAlign:'right',
                               background: editorialHeat(p.xfpV11, 8, 17) }}>
                    <span style={{ fontSize:16, fontFamily:SERIF, fontStyle:'italic', color:colors.accent }}>
                      {fmt(p.xfpV11, 2)}
                    </span>
                  </td>
                  <td style={dataCell(colors)}>{fmt(p.stuffXfp, 2)}</td>
                  <td style={dataCell(colors, p.ipPremium > 0.1 ? colors.pos : p.ipPremium < -0.1 ? colors.neg : colors.dim)}>
                    {fmtSign(p.ipPremium, 2)}
                  </td>
                  <td style={{ padding:'7px 8px', textAlign:'right' }}>
                    <span style={{ ...trendStyle, padding:'1px 6px', fontFamily:MONO,
                                   fontSize:9, letterSpacing:1, borderRadius:2 }}>
                      {p.ipTrend}
                    </span>
                  </td>
                  <td style={dataCell(colors, p.kPct == null ? colors.faint : colors.text)}>
                    {p.kPct == null ? '—' : fmtPct(p.kPct, 1)}
                  </td>
                  <td style={dataCell(colors, colors.dim)}>{p.swstrPct == null ? '—' : fmtPct(p.swstrPct, 1)}</td>
                  <td style={dataCell(colors, colors.dim)}>{p.gs ?? '—'}</td>
                  <td style={dataCell(colors, p.fpActual == null || (p.gs ?? 0) < 5 ? colors.faint : colors.text)}>
                    {p.fpActual == null || (p.gs ?? 0) < 5 ? '—' : fmt(p.fpActual, 2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div style={{ paddingTop:8, fontSize:10, color:colors.dim, fontFamily:MONO, letterSpacing:1 }}>
          <span style={{ color:colors.accent, cursor:'pointer' }}
            onClick={() => { setActiveTab('projections'); setSearch(''); }}>
            ↳ See full projections leaderboard →
          </span>
        </div>
      </div>

      {/* Bullpen */}
      {bullpen.length > 0 && (
        <>
          <SectionHeading num="IV" label="My Bullpen"
            right={`${bullpen.length} RP · CLICK ANY HEADER TO SORT`} colors={colors} />
          <div style={{ padding:'0 32px 24px' }}>
            <table style={{ width:'100%', borderCollapse:'collapse', fontVariantNumeric:'tabular-nums' }}>
              <thead>
                <tr style={{ borderBottom:`2px solid ${colors.text}` }}>
                  <th style={{ padding:'8px 8px', textAlign:'left', fontSize:9, color:colors.dim,
                               fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase', fontWeight:600 }}>#</th>
                  <SortTh col="name"      label="Pitcher"   align="l" width={170} sortCol={bpSort.col} sortDir={bpSort.dir} onSort={handleBpSort} colors={colors} />
                  <SortTh col="proTeam"   label="Team"      align="l" width={50}  sortCol={bpSort.col} sortDir={bpSort.dir} onSort={handleBpSort} colors={colors} />
                  <SortTh col="gp"        label="GS/G"      width={50}  sortCol={bpSort.col} sortDir={bpSort.dir} onSort={handleBpSort} colors={colors} />
                  <SortTh col="fpTotal"   label="ESPN FP"   width={64}  sortCol={bpSort.col} sortDir={bpSort.dir} onSort={handleBpSort} colors={colors} />
                  <SortTh col="fpPerGame" label="ESPN FP/G" width={72}  sortCol={bpSort.col} sortDir={bpSort.dir} onSort={handleBpSort} colors={colors} />
                  <SortTh col="pctOwned"  label="% Owned"   width={64}  sortCol={bpSort.col} sortDir={bpSort.dir} onSort={handleBpSort} colors={colors} />
                </tr>
              </thead>
              <tbody>
                {bullpenDisplay.map((p, idx) => (
                  <tr key={p.name} style={{ borderBottom:`1px solid ${colors.faint}` }}>
                    <td style={{ padding:'7px 8px', fontSize:13, fontFamily:SERIF, fontStyle:'italic', color:colors.dim }}>{idx + 1}</td>
                    <td style={{ padding:'7px 8px', fontSize:14, fontWeight:500 }}>{p.name}</td>
                    <td style={{ padding:'7px 8px', fontSize:11, color:colors.dim, fontFamily:MONO }}>{p.proTeam || '—'}</td>
                    <td style={dataCell(colors, colors.dim)}>{p.gp ?? '—'}</td>
                    <td style={dataCell(colors)}>{p.fpTotal == null ? '—' : fmt(p.fpTotal, 1)}</td>
                    <td style={dataCell(colors)}>{p.fpPerGame == null ? '—' : fmt(p.fpPerGame, 2)}</td>
                    <td style={dataCell(colors, colors.dim)}>{p.pctOwned == null ? '—' : fmt(p.pctOwned, 1) + '%'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── My Lineup (hitters with xFP H2) ──────────────────────────────── */}
      <MyLineupSection myTeam={myTeam} colors={colors} editorialHeat={editorialHeat}
        favorites={favorites} toggleFavorite={toggleFavorite} />
    </>
  );
}

// ═══ My Lineup section (hitters within My Team tab) ═══════════════════════════
function MyLineupSection({ myTeam, colors, editorialHeat, favorites, toggleFavorite }) {
  const hitters = (myTeam.hitters || []);
  if (hitters.length === 0) return null;

  const [hSort, setHSort] = React.useState({ col: 'xfpPerPa', dir: 'desc' });
  function handleSort(col) {
    if (hSort.col === col) setHSort({ col, dir: hSort.dir === 'desc' ? 'asc' : 'desc' });
    else setHSort({ col, dir: 'desc' });
  }
  const sorted = sortRows(hitters, hSort.col, hSort.dir);
  const matched = hitters.filter(h => h.xfpPerPa != null);
  const meanXfpPerPa = matched.length
    ? matched.reduce((s, h) => s + h.xfpPerPa, 0) / matched.length
    : null;

  return (
    <>
      <SectionHeading num="V" label="My Lineup"
        right={`${hitters.length} HITTERS · ${matched.length} WITH xFP H2 COVERAGE`} colors={colors} />
      <div style={{ padding:'0 32px 8px' }}>
        <div style={{ marginBottom:10, fontSize:12, fontStyle:'italic', color:colors.dim }}>
          {meanXfpPerPa != null && (
            <>
              Mean xFP/PA across matched lineup: <span style={{ color:colors.accent, fontFamily:MONO, fontVariantNumeric:'tabular-nums' }}>{meanXfpPerPa.toFixed(3)}</span>
              {' · '}× 3.5 PA/G ≈ <span style={{ color:colors.accent, fontFamily:MONO, fontVariantNumeric:'tabular-nums' }}>{(meanXfpPerPa * 3.5).toFixed(2)}</span> FP/game per slot.
            </>
          )}
        </div>
      </div>
      <div style={{ padding:'0 32px 24px', overflow:'auto' }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontVariantNumeric:'tabular-nums' }}>
          <thead>
            <tr style={{ borderBottom:`2px solid ${colors.text}` }}>
              <th style={{ padding:'8px 8px', textAlign:'left', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase', fontWeight:600 }}>#</th>
              <SortTh col="name"          label="Hitter"  align="l" width={170} sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="espnPos"       label="Slot"    align="l" width={50}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="proTeam"       label="Tm"      align="l" width={42}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="xfpPerPa"      label="xFP/PA"  width={70}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="xfpFullFp"     label="xFP/G"   width={64}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="xfpRank"       label="Rk"      width={42}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="pa"            label="PA"      width={42}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="fpPerPaActual" label="Act/PA"  width={64}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="cohort"        label="Cohort"  align="l" width={70}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="fpTotal"       label="ESPN FP" width={68}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="fpPerGame"     label="ESPN FP/G" width={70} sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="pctOwned"      label="% Owned" width={62}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
            </tr>
          </thead>
          <tbody>
            {sorted.map((h, idx) => {
              const isFav = h.mlbId != null && favorites.includes(h.mlbId);
              const cohortColor = h.cohort === 'blended' ? colors.pos
                : h.cohort === '2026_only' ? colors.warn
                : h.cohort === '2025_only' ? colors.dim : colors.faint;
              return (
                <tr key={h.name} style={{ borderBottom:`1px solid ${colors.faint}` }}>
                  <td style={{ padding:'7px 8px', fontSize:14, fontFamily:SERIF, fontStyle:'italic',
                               color: idx < 3 ? colors.accent : colors.dim }}>{idx + 1}</td>
                  <td style={{ padding:'7px 8px', whiteSpace:'nowrap' }}>
                    {h.mlbId != null && (
                      <span onClick={() => toggleFavorite(h.mlbId)}
                        style={{ color: isFav ? colors.accent : colors.faint, cursor:'pointer',
                                 fontSize:11, marginRight:6 }}>★</span>
                    )}
                    <span style={{ fontSize:14, fontWeight:500 }}>{h.name}</span>
                  </td>
                  <td style={{ padding:'7px 8px', fontSize:11, color:colors.dim, fontFamily:MONO }}>{h.espnPos || h.pos || '—'}</td>
                  <td style={{ padding:'7px 8px', fontSize:11, color:colors.dim, fontFamily:MONO }}>{h.proTeam || h.team || '—'}</td>
                  <td style={{ padding:'5px 8px', textAlign:'right',
                               background: editorialHeat(h.xfpPerPa, 0.3, 0.85) }}>
                    <span style={{ fontSize:16, fontFamily:SERIF, fontStyle:'italic',
                                   color: h.xfpPerPa != null ? colors.accent : colors.faint }}>
                      {h.xfpPerPa == null ? '—' : h.xfpPerPa.toFixed(3)}
                    </span>
                  </td>
                  <td style={dataCell(colors)}>{h.xfpFullFp == null ? '—' : h.xfpFullFp.toFixed(2)}</td>
                  <td style={dataCell(colors, colors.dim)}>{h.xfpRank == null ? '—' : '#' + h.xfpRank}</td>
                  <td style={dataCell(colors, colors.dim)}>{h.pa ?? '—'}</td>
                  <td style={dataCell(colors, h.fpPerPaActual == null ? colors.faint : colors.text)}>
                    {h.fpPerPaActual == null ? '—' : h.fpPerPaActual.toFixed(3)}
                  </td>
                  <td style={{ padding:'7px 8px', textAlign:'left', fontSize:9, fontFamily:MONO, letterSpacing:1, color:cohortColor }}>
                    {h.cohort || '—'}
                  </td>
                  <td style={dataCell(colors)}>{h.fpTotal == null ? '—' : fmt(h.fpTotal, 1)}</td>
                  <td style={dataCell(colors)}>{h.fpPerGame == null ? '—' : fmt(h.fpPerGame, 2)}</td>
                  <td style={dataCell(colors, colors.dim)}>{h.pctOwned == null ? '—' : fmt(h.pctOwned, 1) + '%'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ═══ Model Info tab ═══════════════════════════════════════════════════════════
function ModelTab({ meta, h2Meta, colors }) {
  const accuracyRows = [
    { metric: 'Cross-year r',         v8: 0.558, v85: 0.600, v11: meta.crossYearR },
    { metric: 'k_bias_hi',            v8: 0.241, v85: 0.466, v11: meta.kBiasHi },
    { metric: 'Score (T=1.0)',        v8: 1.800, v85: 1.800, v11: meta.scoreT1 },
    { metric: '2026 YTD r (gs ≥ 5)',  v8: null,  v85: 0.475, v11: meta.ytdR },
    { metric: '2026 YTD MAE',         v8: null,  v85: 3.484, v11: meta.ytdMae },
  ];
  const archetypes = [
    { name: 'Schlittler',  takeaway: 'Mid-season swstr surge (+4.4 ppt 2025→2026); blended 2026 inputs lifted V11.' },
    { name: 'Glasnow',     takeaway: 'Healthy stuff; V11 captures the velo + pitching_plus jump.' },
    { name: 'Imanaga',     takeaway: 'Sample-weighted blend of 2025+2026 raises projection; FG Pitching+ supports.' },
    { name: 'Fried',       takeaway: 'Contact-manager archetype; bb_pfxz + xwoba_per_pa keep him appropriately scored.' },
    { name: 'Woodruff',    takeaway: 'Process model can\'t see injury — known overprojection until Phase 13 (injury history).' },
    { name: 'Ragans',      takeaway: 'Same archetype as Woodruff: stuff still grades elite, but availability is unsolved.' },
  ];
  const versions = [
    { v: 'V8',   feats: '4-feat core (swstr, c_plus_swstr, xwoba_per_pa, xwoba_x_swstr)', r: 0.558, status: 'frozen' },
    { v: 'V8.5', feats: 'V8 + bb_pfxz + pfxz_spread + pitch_entropy + ip_resid_lag1 + k_pct_lag1 (+ lag interactions)',  r: 0.600, status: 'superseded' },
    { v: 'V11',  feats: 'V8.5 + pitching_plus + fp_strike_pct (14 features total)', r: 0.614, status: 'production' },
  ];

  return (
    <>
      <SectionHeading num="I" label="Accuracy" right="V8 / V8.5 / V11 SIDE-BY-SIDE" colors={colors} />
      <div style={{ padding:'0 32px 24px' }}>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:16, marginBottom:18 }}>
          {[
            { lbl: 'Cross-year r', v: meta.crossYearR, sub: 'leave-one-out 2015-2025 transitions, n=854' },
            { lbl: '2026 YTD r',   v: meta.ytdR, sub: 'live deployment correlation, gs ≥ 5' },
            { lbl: '2026 YTD MAE', v: meta.ytdMae, sub: 'mean absolute error, FP/start' },
          ].map(c => (
            <div key={c.lbl} style={{ borderTop:`2px solid ${colors.accent}`, paddingTop:8 }}>
              <div style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO }}>{c.lbl}</div>
              <div style={{ fontSize:30, fontFamily:SERIF, fontStyle:'italic', color:colors.accent, lineHeight:1.1, marginTop:4 }}>
                {typeof c.v === 'number' ? c.v.toFixed(3) : '—'}
              </div>
              <div style={{ fontSize:10, color:colors.dim, fontStyle:'italic', marginTop:4 }}>{c.sub}</div>
            </div>
          ))}
        </div>
        <table style={{ width:'100%', borderCollapse:'collapse', fontVariantNumeric:'tabular-nums' }}>
          <thead>
            <tr style={{ borderBottom:`2px solid ${colors.text}` }}>
              <th style={{ padding:'8px', textAlign:'left', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Metric</th>
              <th style={{ padding:'8px', textAlign:'right', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>V8 (frozen)</th>
              <th style={{ padding:'8px', textAlign:'right', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>V8.5</th>
              <th style={{ padding:'8px', textAlign:'right', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>V11 (prod)</th>
            </tr>
          </thead>
          <tbody>
            {accuracyRows.map(r => (
              <tr key={r.metric} style={{ borderBottom:`1px solid ${colors.faint}` }}>
                <td style={{ padding:'7px 8px', fontSize:13 }}>{r.metric}</td>
                <td style={{ ...dataCell(colors, colors.dim) }}>{r.v8 == null ? '—' : r.v8.toFixed(3)}</td>
                <td style={{ ...dataCell(colors, colors.dim) }}>{r.v85.toFixed(3)}</td>
                <td style={{ ...dataCell(colors, colors.accent), fontWeight:600 }}>{r.v11.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <SectionHeading num="II" label="Features & Coefficients"
        right={`${meta.features.length} features · alpha=${meta.alpha} · intercept=${meta.intercept}`} colors={colors} />
      <div style={{ padding:'0 32px 24px' }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontVariantNumeric:'tabular-nums' }}>
          <thead>
            <tr style={{ borderBottom:`2px solid ${colors.text}` }}>
              <th style={{ padding:'8px', textAlign:'left', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Feature</th>
              <th style={{ padding:'8px', textAlign:'right', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Standardized coef</th>
              <th style={{ padding:'8px', textAlign:'left', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Direction</th>
            </tr>
          </thead>
          <tbody>
            {meta.coefficients.map(c => (
              <tr key={c.feat} style={{ borderBottom:`1px solid ${colors.faint}` }}>
                <td style={{ padding:'7px 8px', fontSize:13, fontFamily:MONO }}>{c.feat}</td>
                <td style={{ ...dataCell(colors, c.coef > 0 ? colors.pos : colors.neg), fontWeight:600 }}>
                  {c.coef > 0 ? '+' : ''}{c.coef.toFixed(3)}
                </td>
                <td style={{ padding:'7px 8px', fontSize:11, color:colors.dim }}>
                  {c.coef > 0 ? '↑ raises xFP' : '↓ lowers xFP'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <SectionHeading num="III" label="Archetype Notes" colors={colors} />
      <div style={{ padding:'0 32px 24px', display:'grid', gridTemplateColumns:'repeat(2, 1fr)', gap:16 }}>
        {archetypes.map(a => (
          <div key={a.name} style={{ borderTop:`1px solid ${colors.faint}`, paddingTop:8 }}>
            <div style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO }}>Archetype</div>
            <div style={{ fontSize:18, fontFamily:SERIF, fontStyle:'italic', color:colors.accent, marginTop:2 }}>{a.name}</div>
            <div style={{ fontSize:12, color:colors.text, marginTop:6, lineHeight:1.5 }}>{a.takeaway}</div>
          </div>
        ))}
      </div>

      <SectionHeading num="IV" label="Version History" colors={colors} />
      <div style={{ padding:'0 32px 24px' }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontVariantNumeric:'tabular-nums' }}>
          <thead>
            <tr style={{ borderBottom:`2px solid ${colors.text}` }}>
              <th style={{ padding:'8px', textAlign:'left', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Ver</th>
              <th style={{ padding:'8px', textAlign:'left', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Features</th>
              <th style={{ padding:'8px', textAlign:'right', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Cross-yr r</th>
              <th style={{ padding:'8px', textAlign:'left', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {versions.map(v => (
              <tr key={v.v} style={{ borderBottom:`1px solid ${colors.faint}` }}>
                <td style={{ padding:'7px 8px', fontSize:13, fontFamily:MONO, fontWeight:600,
                             color: v.status === 'production' ? colors.accent : colors.text }}>{v.v}</td>
                <td style={{ padding:'7px 8px', fontSize:11, color:colors.dim }}>{v.feats}</td>
                <td style={dataCell(colors, v.status === 'production' ? colors.accent : colors.text)}>{v.r.toFixed(3)}</td>
                <td style={{ padding:'7px 8px', fontSize:10, fontFamily:MONO, letterSpacing:1, textTransform:'uppercase',
                             color: v.status === 'production' ? colors.accent : v.status === 'superseded' ? colors.dim : colors.warn }}>
                  {v.status}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <SectionHeading num="V" label="Methodology" colors={colors} />
      <div style={{ padding:'0 32px 32px', display:'grid', gridTemplateColumns:'1fr 1fr', gap:24 }}>
        <div>
          <div style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO, marginBottom:8 }}>Scoring Formula</div>
          <div style={{ fontSize:13, fontFamily:MONO, color:colors.text, padding:'10px 14px',
                        background:colors.stripe, borderLeft:`3px solid ${colors.accent}` }}>
            ESPN: K×1 + IP×3.3 − H×1 − ER×2 − BB×1 − HBP×1
          </div>
          <div style={{ fontSize:12, color:colors.dim, marginTop:12, lineHeight:1.6, fontStyle:'italic' }}>
            V11 is a Ridge regression (StandardScaler → RidgeCV α={meta.alpha}) trained on
            {' '}{meta.nTrain} SP-seasons from {meta.trainingYears}. Mid-season inputs are
            sample-weighted blends of 2025 + 2026 (V8.1 layer). The non-circular constraint forbids
            per-start K/IP/H/ER/BB/HBP from appearing as features.
          </div>
        </div>
        <div>
          <div style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO, marginBottom:8 }}>Refresh Mid-Season</div>
          <pre style={{ fontSize:11, fontFamily:MONO, color:colors.text, padding:'10px 14px',
                        background:colors.stripe, borderLeft:`3px solid ${colors.accent}`,
                        margin:0, whiteSpace:'pre-wrap', lineHeight:1.5 }}>{`# 1. FanGraphs Pitching+ (undetected-chromedriver)
python scripts/xfp/pull_fg_undetected.py

# 2. Re-aggregate Statcast if 2026.parquet refreshed
python scripts/xfp/build_sp_multiyr.py

# 3. Re-blend, re-project, rebuild dashboard
python scripts/xfp/xfp_v11_lock.py
python scripts/xfp/build_v11_dashboard_v2.py

# 4. Push to refresh GitHub Pages
git -C xfp-model add docs/index.html
git -C xfp-model commit -m "data: refresh"
git -C xfp-model push`}</pre>
        </div>
      </div>

      {/* ── Hitter (H2) model section ───────────────────────────────────── */}
      {h2Meta && h2Meta.features && (
        <>
          <SectionHeading num="VI" label="Hitter Model — H2 (parallel to V11)"
            right={`${h2Meta.features.length} FEATURES · RIDGE`} colors={colors} />
          <div style={{ padding:'0 32px 24px' }}>
            <div style={{ display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:16, marginBottom:18 }}>
              {[
                { lbl: 'Cross-year r',   v: h2Meta.crossYearR, sub: 'leave-one-out 2018–2025 transitions' },
                { lbl: '2026 YTD r',     v: h2Meta.ytdR, sub: `live deployment, PA ≥ 80, n=${h2Meta.ytdN}` },
                { lbl: '2026 YTD MAE',   v: h2Meta.ytdMae, sub: 'mean absolute error, FP/PA' },
              ].map(c => (
                <div key={c.lbl} style={{ borderTop:`2px solid ${colors.accent}`, paddingTop:8 }}>
                  <div style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO }}>{c.lbl}</div>
                  <div style={{ fontSize:30, fontFamily:SERIF, fontStyle:'italic', color:colors.accent, lineHeight:1.1, marginTop:4 }}>
                    {typeof c.v === 'number' ? c.v.toFixed(3) : '—'}
                  </div>
                  <div style={{ fontSize:10, color:colors.dim, fontStyle:'italic', marginTop:4 }}>{c.sub}</div>
                </div>
              ))}
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:24 }}>
              <div>
                <div style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO, marginBottom:8 }}>Bias diagnostics</div>
                <div style={{ fontSize:13, fontFamily:MONO, color:colors.text, padding:'8px 12px',
                              background:colors.stripe, borderLeft:`3px solid ${colors.accent}` }}>
                  power_bias_hi: {h2Meta.powerBiasHi >= 0 ? '+' : ''}{h2Meta.powerBiasHi.toFixed(3)}<br/>
                  team_context_bias: {h2Meta.teamContextBias >= 0 ? '+' : ''}{h2Meta.teamContextBias.toFixed(3)}<br/>
                  score (T=1.0): {h2Meta.scoreT1.toFixed(3)}
                </div>
              </div>
              <div>
                <div style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO, marginBottom:8 }}>Bayesian shrinkage priors</div>
                <div style={{ fontSize:12, fontFamily:MONO, color:colors.text, padding:'8px 12px',
                              background:colors.stripe, borderLeft:`3px solid ${colors.accent}` }}>
                  xwoba_on_contact: PRIOR_N={h2Meta.priorXwoba[0]}, PRIOR_MEAN={h2Meta.priorXwoba[1]}<br/>
                  contact_pct: PRIOR_N={h2Meta.priorContact[0]}, PRIOR_MEAN={h2Meta.priorContact[1]}<br/>
                  pa_per_game (display): {h2Meta.paPerGame}
                </div>
              </div>
            </div>
            <table style={{ width:'100%', borderCollapse:'collapse', fontVariantNumeric:'tabular-nums', marginTop:18 }}>
              <thead>
                <tr style={{ borderBottom:`2px solid ${colors.text}` }}>
                  <th style={{ padding:'8px', textAlign:'left', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Feature</th>
                  <th style={{ padding:'8px', textAlign:'right', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Standardized coef</th>
                  <th style={{ padding:'8px', textAlign:'left', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Direction</th>
                </tr>
              </thead>
              <tbody>
                {h2Meta.coefficients.map(c => (
                  <tr key={c.feat} style={{ borderBottom:`1px solid ${colors.faint}` }}>
                    <td style={{ padding:'7px 8px', fontSize:13, fontFamily:MONO }}>{c.feat}</td>
                    <td style={{ ...dataCell(colors, c.coef > 0 ? colors.pos : colors.neg), fontWeight:600 }}>
                      {c.coef > 0 ? '+' : ''}{c.coef.toFixed(4)}
                    </td>
                    <td style={{ padding:'7px 8px', fontSize:11, color:colors.dim }}>
                      {c.coef > 0 ? '↑ raises xFP/PA' : '↓ lowers xFP/PA'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ marginTop:14, fontSize:11, color:colors.dim, fontStyle:'italic', lineHeight:1.6 }}>
              <strong>Caveat — team context.</strong> H2 has no per-team run-environment feature.
              R and RBI are noisy across teams (a hitter who moves Yankees → A's keeps his xwOBA but loses ~30 RBI of lineup protection).
              The team_context_bias diagnostic above tracks this gap; if it grows past ±0.05 the model will need a team feature.
            </div>
          </div>
        </>
      )}
    </>
  );
}

// ═══ Theme toggle + root ══════════════════════════════════════════════════════
function ThemeToggle({ dark, setDark }) {
  return (
    <div style={{
      position:'fixed', top:10, right:14, zIndex:100,
      display:'flex', gap:4, padding:3, borderRadius:6,
      background:'rgba(255,255,255,0.85)', border:'1px solid rgba(0,0,0,.1)',
      fontFamily:'monospace', fontSize:11,
    }}>
      {['Light', 'Dark'].map((m, i) => {
        const active = dark === (i === 1);
        return (
          <button key={m} onClick={() => setDark(i === 1)} style={{
            padding:'3px 10px', borderRadius:4, border:'none', cursor:'pointer',
            background: active ? '#1a1a1a' : 'transparent',
            color: active ? '#fff' : '#555', fontWeight:500, fontSize:11,
          }}>{m}</button>
        );
      })}
    </div>
  );
}

function App() {
  const [dark, setDark] = React.useState(false);
  return (
    <div style={{ position:'relative', minHeight:'100vh' }}>
      <ThemeToggle dark={dark} setDark={setDark} />
      <Dashboard dark={dark} />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
</script>
</body>
</html>
"""


def main():
    records, my_team = build_records()
    hitter_records, hitter_payload = build_hitter_records()
    my_team['hitters'] = hitter_payload  # combine into one MY_TEAM payload
    meta = build_meta()
    h2_meta = build_h2_meta()

    proj_json    = json.dumps(records, separators=(',', ':'))
    meta_json    = json.dumps(meta, separators=(',', ':'))
    my_team_json = json.dumps(my_team, separators=(',', ':'))
    hitters_json = json.dumps(hitter_records, separators=(',', ':'))
    h2_meta_json = json.dumps(h2_meta, separators=(',', ':'))

    html = (HTML_TEMPLATE
            .replace('__PROJECTIONS_JSON__', proj_json)
            .replace('__META_JSON__', meta_json)
            .replace('__H2_META_JSON__', h2_meta_json)
            .replace('__HITTERS_JSON__', hitters_json)
            .replace('__MY_TEAM_JSON__', my_team_json))

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

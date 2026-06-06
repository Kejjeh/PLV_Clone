"""validate_buylow_signal.py — PR 8 BUY-LOW signal validation backtest.

Pre-registration: data/research/validation_runs/buylow_panel_prereg_2026-06-06.md

Tests whether hitter BUY-LOW candidates (composite_pct >= 0.75 AND rh3_pct <= 0.25)
at as-of date D produce a positive mean residual FP/PA over [D+30d, D+60d] vs
the rh3 projection at D.

Per plan v11 Decision 12, the production process-panel CSV ships WITHOUT a
``buylow_flag`` column until this validation passes. Per Decision 13, the
testable universe is 2024-2025 only (no 2023 snapshots), with snapshot gap rule
and max snapshot age of 31 days.

Hard 2020 exclusion is enforced upstream (no 2020 dates anywhere in the loop).

Outputs:
  data/research/validation_runs/buylow_panel_results_2026-06-06.md
  data/research/validation_runs/buylow_panel_results_2026-06-06.json

Usage:
  python -X utf8 scripts/xfp/validate_buylow_signal.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.xfp.lib.season_dates import season_start  # noqa: E402

CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
SNAPSHOT_DIR = ROOT / 'data' / 'research' / 'projection_snapshots'
VAL_DIR = ROOT / 'data' / 'research' / 'validation_runs'
OUT_MD = VAL_DIR / 'buylow_panel_results_2026-06-06.md'
OUT_JSON = VAL_DIR / 'buylow_panel_results_2026-06-06.json'

# Canonical statcast event sets (mirrors src/plv_clone/fantasy/hitter_points.py
# and scripts/xfp/build_weekly_fp_substrate.py).
PA_EVENTS = {
    'single', 'double', 'triple', 'home_run', 'walk', 'intent_walk',
    'hit_by_pitch', 'strikeout', 'strikeout_double_play',
    'field_out', 'force_out', 'grounded_into_double_play',
    'sac_fly', 'sac_bunt', 'fielders_choice', 'fielders_choice_out',
    'double_play', 'triple_play', 'field_error', 'catcher_interf',
    'sac_fly_double_play', 'strikeout_triple_play', 'truncated_pa',
}
TB_MAP = {'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}
K_EVENTS = {'strikeout', 'strikeout_double_play', 'strikeout_triple_play'}
BB_EVENTS = {'walk', 'intent_walk'}

MAX_SNAPSHOT_GAP_DAYS = 31
MIN_FORWARD_PA = 30
COMPOSITE_PCT_CUT = 0.75
RH3_PCT_CUT = 0.25


@dataclass
class TestPoint:
    year: int
    anchor: date
    snapshot_date: Optional[date]
    snapshot_gap_days: Optional[int]
    status: str  # 'ok', 'snapshot_missing', 'gap_too_large', 'covid_exclude'
    n_candidates: int = 0
    n_with_forward: int = 0
    mean_residual: Optional[float] = None
    sd_residual: Optional[float] = None


def _pick_snapshot(anchor: date) -> tuple[Optional[date], Optional[int]]:
    """Return the snapshot date closest to anchor within 31 days.

    Searches data/research/projection_snapshots/YYYY-MM-DD/ for directories
    containing xfp_rh3_projections.csv. Returns (snapshot_date, gap_days) or
    (None, None) if no snapshot is within the 31-day cap.
    """
    if not SNAPSHOT_DIR.exists():
        return None, None
    candidates = []
    for d in SNAPSHOT_DIR.iterdir():
        if not d.is_dir():
            continue
        rh3 = d / 'xfp_rh3_projections.csv'
        if not rh3.exists():
            continue
        try:
            snap_date = date.fromisoformat(d.name)
        except ValueError:
            continue
        gap = abs((snap_date - anchor).days)
        if gap <= MAX_SNAPSHOT_GAP_DAYS:
            candidates.append((gap, snap_date))
    if not candidates:
        return None, None
    candidates.sort()
    best_gap, best_date = candidates[0]
    return best_date, best_gap


def _pre_registered_anchors() -> list[tuple[int, date]]:
    """Year + anchor (every 30d from season_start, 4 per year)."""
    anchors = []
    for yr in (2024, 2025):
        ss = season_start(yr)
        for k in (1, 2, 3, 4):  # +30d, +60d, +90d, +120d
            anchors.append((yr, ss + timedelta(days=30 * k)))
    return anchors


def _build_process_panel(as_of: date) -> Path:
    """Invoke build_process_panel.py --as-of D and return the hitter CSV path."""
    script = ROOT / 'scripts' / 'xfp' / 'build_process_panel.py'
    hitter_out = ROOT / 'data' / 'outputs' / f'_buylow_hitter_panel_{as_of.isoformat()}.csv'
    sp_out = ROOT / 'data' / 'outputs' / f'_buylow_sp_panel_{as_of.isoformat()}.csv'
    cmd = [
        sys.executable, '-X', 'utf8', str(script),
        '--as-of', as_of.isoformat(),
        '--hitter-out', str(hitter_out),
        '--sp-out', str(sp_out),
    ]
    print(f'[buylow_validate]   running process_panel --as-of {as_of}', flush=True)
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr, file=sys.stderr)
        raise RuntimeError(f'build_process_panel failed for as-of {as_of}')
    return hitter_out


def _load_snapshot_rh3(snap_date: date) -> pd.DataFrame:
    path = SNAPSHOT_DIR / snap_date.isoformat() / 'xfp_rh3_projections.csv'
    rh3 = pd.read_csv(path)
    if 'batter' not in rh3.columns or 'xfp_rh3_per_pa' not in rh3.columns:
        raise RuntimeError(f'snapshot at {snap_date} missing required columns')
    return rh3[['batter', 'xfp_rh3_per_pa']].copy()


def _actual_fp_per_pa_window(
    year: int,
    candidates: pd.DataFrame,
    window_start: date,
    window_end: date,
    sb_rate_lookup: dict[int, float],
) -> pd.DataFrame:
    """For each candidate batter, compute (PA, actual_fp_per_pa) over [start, end].

    Mirrors the canonical hitter-FP formula used in build_weekly_fp_substrate.py:
      FP = TB + R(=HR proxy) + RBI(=post_bat_score - bat_score) + BB + HBP + SB - K
      SB = sb_rate_year * PA   (year-level rate from hitters_multiyr)

    The HR-as-R proxy is the standard convention in this repo for window-level
    aggregations from statcast — we cannot reconstruct true R without tracking
    runner state across PAs in an inning. See bench_tracker.py + build_weekly_fp_substrate.py.
    """
    parquet = CACHE / f'statcast_{year}.parquet'
    if not parquet.exists():
        raise RuntimeError(f'statcast_{year}.parquet not found')

    needed_ids = set(candidates['batter'].astype(int).tolist())
    df = pd.read_parquet(
        parquet,
        columns=['game_date', 'batter', 'events', 'bat_score', 'post_bat_score'],
    )
    df['game_date'] = pd.to_datetime(df['game_date']).dt.date
    df = df[
        df['batter'].isin(needed_ids)
        & (df['game_date'] >= window_start)
        & (df['game_date'] <= window_end)
        & df['events'].isin(PA_EVENTS)
    ].copy()
    if df.empty:
        return pd.DataFrame(columns=['batter', 'pa_fwd', 'actual_fp_per_pa'])

    df['tb'] = df['events'].map(TB_MAP).fillna(0).astype(int)
    df['bb'] = df['events'].isin(BB_EVENTS).astype(int)
    df['hbp'] = (df['events'] == 'hit_by_pitch').astype(int)
    df['k'] = df['events'].isin(K_EVENTS).astype(int)
    df['hr'] = (df['events'] == 'home_run').astype(int)
    df['rbi'] = (df['post_bat_score'] - df['bat_score']).fillna(0).clip(lower=0)

    agg = df.groupby('batter').agg(
        pa_fwd=('events', 'count'),
        tb=('tb', 'sum'),
        bb=('bb', 'sum'),
        hbp=('hbp', 'sum'),
        k=('k', 'sum'),
        hr=('hr', 'sum'),
        rbi=('rbi', 'sum'),
    ).reset_index()

    agg['sb_rate'] = agg['batter'].map(sb_rate_lookup).fillna(0.020)
    agg['sb'] = agg['sb_rate'] * agg['pa_fwd']
    agg['fp_total'] = (
        agg['tb'] + agg['hr'] + agg['rbi'] + agg['bb'] + agg['hbp']
        + agg['sb'] - agg['k']
    )
    agg['actual_fp_per_pa'] = agg['fp_total'] / agg['pa_fwd'].clip(lower=1)
    return agg[['batter', 'pa_fwd', 'actual_fp_per_pa']]


def _sb_rate_lookup(year: int) -> dict[int, float]:
    h = pd.read_csv(
        CACHE / 'hitters_multiyr_2015_2026.csv',
        usecols=['batter', 'year', 'sb_per_pa'],
    )
    h = h[h['year'] == year]
    return dict(zip(h['batter'].astype(int), h['sb_per_pa'].astype(float)))


def _run_one_point(year: int, anchor: date) -> tuple[TestPoint, pd.DataFrame]:
    snap_date, gap = _pick_snapshot(anchor)
    if snap_date is None:
        return TestPoint(
            year=year, anchor=anchor, snapshot_date=None,
            snapshot_gap_days=None, status='snapshot_missing',
        ), pd.DataFrame()

    print(f'[buylow_validate] {year} anchor={anchor} -> snap={snap_date} gap={gap}d', flush=True)

    hitter_panel_csv = _build_process_panel(snap_date)
    panel = pd.read_csv(hitter_panel_csv)
    if 'composite' not in panel.columns or 'batter' not in panel.columns:
        raise RuntimeError(f'panel missing composite/batter cols at {snap_date}')

    panel = panel[panel['composite'].notna()].copy()
    panel['composite_pct'] = panel['composite'].rank(pct=True)

    rh3 = _load_snapshot_rh3(snap_date)
    rh3['rh3_pct'] = rh3['xfp_rh3_per_pa'].rank(pct=True)

    merged = panel[['batter', 'composite', 'composite_pct']].merge(
        rh3[['batter', 'xfp_rh3_per_pa', 'rh3_pct']],
        on='batter',
        how='inner',
    )

    flagged = merged[
        (merged['composite_pct'] >= COMPOSITE_PCT_CUT)
        & (merged['rh3_pct'] <= RH3_PCT_CUT)
    ].copy()
    n_flagged = len(flagged)
    if n_flagged == 0:
        return TestPoint(
            year=year, anchor=anchor, snapshot_date=snap_date,
            snapshot_gap_days=gap, status='ok', n_candidates=0,
        ), pd.DataFrame()

    window_start = snap_date + timedelta(days=30)
    window_end = snap_date + timedelta(days=60)
    sb_lookup = _sb_rate_lookup(year)
    actuals = _actual_fp_per_pa_window(year, flagged, window_start, window_end, sb_lookup)

    cand = flagged.merge(actuals, on='batter', how='left')
    cand['snap_date'] = snap_date.isoformat()
    cand['year'] = year
    cand['anchor'] = anchor.isoformat()
    cand['window_start'] = window_start.isoformat()
    cand['window_end'] = window_end.isoformat()

    eligible = cand[(cand['pa_fwd'] >= MIN_FORWARD_PA) & cand['actual_fp_per_pa'].notna()].copy()
    eligible['residual'] = eligible['actual_fp_per_pa'] - eligible['xfp_rh3_per_pa']

    pt = TestPoint(
        year=year, anchor=anchor, snapshot_date=snap_date,
        snapshot_gap_days=gap, status='ok',
        n_candidates=n_flagged, n_with_forward=len(eligible),
        mean_residual=float(eligible['residual'].mean()) if len(eligible) else None,
        sd_residual=float(eligible['residual'].std(ddof=1)) if len(eligible) > 1 else None,
    )
    return pt, eligible


def _summarize(points: list[TestPoint], cands_df: pd.DataFrame) -> dict:
    pooled = cands_df.copy()
    by_year = {}
    for yr in (2024, 2025):
        sub = pooled[pooled['year'] == yr]
        if len(sub) == 0:
            by_year[yr] = {'n': 0, 'mean': None, 'sd': None, 'ci_lo': None, 'ci_hi': None}
            continue
        n = len(sub)
        m = float(sub['residual'].mean())
        sd = float(sub['residual'].std(ddof=1)) if n > 1 else float('nan')
        se = sd / np.sqrt(n) if n > 1 else float('nan')
        by_year[yr] = {
            'n': n, 'mean': m, 'sd': sd,
            'ci_lo': m - 1.96 * se if n > 1 else None,
            'ci_hi': m + 1.96 * se if n > 1 else None,
        }
    n_p = len(pooled)
    if n_p > 1:
        m_p = float(pooled['residual'].mean())
        sd_p = float(pooled['residual'].std(ddof=1))
        se_p = sd_p / np.sqrt(n_p)
        pooled_summary = {
            'n': n_p, 'mean': m_p, 'sd': sd_p,
            'ci_lo': m_p - 1.96 * se_p, 'ci_hi': m_p + 1.96 * se_p,
        }
    else:
        pooled_summary = {'n': n_p, 'mean': None, 'sd': None, 'ci_lo': None, 'ci_hi': None}
    return {'pooled': pooled_summary, 'by_year': by_year}


def _verdict(summary: dict) -> tuple[str, list[str]]:
    failures = []
    pooled = summary['pooled']
    by_year = summary['by_year']

    if pooled['n'] is None or pooled['n'] < 30:
        failures.append(f"n_pooled={pooled['n']} < 30")
    if pooled['mean'] is None or pooled['mean'] < 0.015:
        failures.append(f"mean_residual={pooled['mean']} < +0.015 FP/PA")
    if pooled['ci_lo'] is None or pooled['ci_lo'] <= 0:
        failures.append(f"CI lower bound={pooled['ci_lo']} <= 0")
    y24, y25 = by_year.get(2024, {}), by_year.get(2025, {})
    if y24.get('mean') is not None and y25.get('mean') is not None:
        if (y24['mean'] >= 0) != (y25['mean'] >= 0):
            failures.append(f"sign flip: 2024={y24['mean']:.4f} vs 2025={y25['mean']:.4f}")
    else:
        failures.append('one or both years have no candidates with forward window')

    if not failures:
        return 'PASS', []
    return 'FAIL', failures


def main() -> None:
    points: list[TestPoint] = []
    all_eligible: list[pd.DataFrame] = []
    for yr, anchor in _pre_registered_anchors():
        try:
            pt, elig = _run_one_point(yr, anchor)
        except Exception as e:
            print(f'[buylow_validate] ERROR at {yr}/{anchor}: {e}', file=sys.stderr)
            raise
        points.append(pt)
        if len(elig):
            all_eligible.append(elig)

    cand_df = (
        pd.concat(all_eligible, ignore_index=True)
        if all_eligible else pd.DataFrame(columns=['year', 'residual'])
    )
    summary = _summarize(points, cand_df)
    verdict, failures = _verdict(summary)

    # JSON dump
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    json_payload = {
        'prereg': 'buylow_panel_prereg_2026-06-06.md',
        'verdict': verdict,
        'failures': failures,
        'pass_criteria': {
            'composite_pct_cut': COMPOSITE_PCT_CUT,
            'rh3_pct_cut': RH3_PCT_CUT,
            'min_forward_pa': MIN_FORWARD_PA,
            'min_pooled_n': 30,
            'min_pooled_mean': 0.015,
            'window_start_offset_d': 30,
            'window_end_offset_d': 60,
        },
        'summary': summary,
        'points': [
            {
                'year': pt.year,
                'anchor': pt.anchor.isoformat(),
                'snapshot_date': pt.snapshot_date.isoformat() if pt.snapshot_date else None,
                'snapshot_gap_days': pt.snapshot_gap_days,
                'status': pt.status,
                'n_candidates': pt.n_candidates,
                'n_with_forward': pt.n_with_forward,
                'mean_residual': pt.mean_residual,
                'sd_residual': pt.sd_residual,
            }
            for pt in points
        ],
    }
    OUT_JSON.write_text(json.dumps(json_payload, indent=2))

    # Markdown report
    lines = [
        '# BUY-LOW signal validation results — 2026-06-06',
        '',
        'Pre-registration: `data/research/validation_runs/buylow_panel_prereg_2026-06-06.md`',
        '',
        f'## Verdict: **{verdict}**',
        '',
    ]
    if failures:
        lines.append('### Pass-criterion failures:')
        for f in failures:
            lines.append(f'- {f}')
        lines.append('')
    lines += [
        '## Pass criteria (from pre-reg)',
        '- Pooled mean residual >= +0.015 FP/PA',
        '- Pooled 95% CI lower bound > 0',
        '- Pooled N >= 30',
        '- No sign flip between 2024 and 2025 means',
        '',
        '## Pooled summary',
        f"- N: {summary['pooled']['n']}",
        f"- Mean residual: {summary['pooled']['mean']}",
        f"- SD: {summary['pooled']['sd']}",
        f"- 95% CI: [{summary['pooled']['ci_lo']}, {summary['pooled']['ci_hi']}]",
        '',
        '## Per-year summary',
    ]
    for yr in (2024, 2025):
        s = summary['by_year'][yr]
        lines += [
            f'### {yr}',
            f"- N: {s['n']}",
            f"- Mean residual: {s['mean']}",
            f"- 95% CI: [{s['ci_lo']}, {s['ci_hi']}]",
            '',
        ]
    lines += [
        '## Per-as-of-date detail',
        '',
        '| Year | Anchor | Snapshot | Gap (d) | Status | N flagged | N w/ forward | Mean residual |',
        '|------|--------|----------|---------|--------|-----------|--------------|---------------|',
    ]
    for pt in points:
        snap = pt.snapshot_date.isoformat() if pt.snapshot_date else '—'
        gap = pt.snapshot_gap_days if pt.snapshot_gap_days is not None else '—'
        mr = f"{pt.mean_residual:.4f}" if pt.mean_residual is not None else '—'
        lines.append(
            f"| {pt.year} | {pt.anchor.isoformat()} | {snap} | {gap} | "
            f"{pt.status} | {pt.n_candidates} | {pt.n_with_forward} | {mr} |"
        )
    lines += ['', '## Audit trail', '']
    if verdict == 'PASS':
        lines += [
            'Verdict is PASS. Per pre-reg, this means BUY-LOW is READY TO SHIP as a',
            'display flag on the production process-panel CSV. The actual CSV change',
            'is a SEPARATE follow-up PR — this commit ships ONLY the validation.',
        ]
    else:
        lines += [
            'Verdict is FAIL. Per plan v11 Decision 12, `buylow_flag` will NOT be',
            'added to the production process-panel CSV. The BUY-LOW conjecture as',
            'pre-registered (composite_pct >= 0.75 AND rh3_pct <= 0.25) does not',
            'predict positive T+30 to T+60 residual vs the model at the bar required',
            'by the 9-rule multi-testing protocol.',
        ]
    OUT_MD.write_text('\n'.join(lines), encoding='utf-8')
    print(f'\n[buylow_validate] wrote {OUT_MD}')
    print(f'[buylow_validate] wrote {OUT_JSON}')
    print(f'[buylow_validate] verdict: {verdict}')
    if failures:
        for f in failures:
            print(f'  - {f}')


if __name__ == '__main__':
    main()

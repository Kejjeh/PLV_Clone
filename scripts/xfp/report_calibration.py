"""Calibration reporter for predictions_history.csv.

Reads `data/outputs/predictions_history.csv`, filters to backfilled rows
(actual_my_final not null), and computes per-model-version:

  * MAE / RMSE / bias for my_total and opp_total
  * Win-probability calibration buckets (0-25, 25-50, 50-75, 75-100):
    predicted win rate vs actual win rate
  * Minimum-N gate: if any active bucket has N < MIN_N, that bucket is
    flagged INSUFFICIENT. If no bucket clears N >= MIN_N for any model,
    we skip writing the JSON summary.

Outputs:
  * data/outputs/projection_accuracy_report.md  (always overwritten)
  * data/outputs/calibration_summary.json       (written iff at least one
                                                  bucket has N >= MIN_N for
                                                  at least one model)

Idempotent. Safe to run any time. No-op if history is empty.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ROOT / 'data' / 'outputs' / 'predictions_history.csv'
REPORT = ROOT / 'data' / 'outputs' / 'projection_accuracy_report.md'
SUMMARY = ROOT / 'data' / 'outputs' / 'calibration_summary.json'

MIN_N_PER_BUCKET = 5
WP_BUCKETS = [(0.0, 0.25), (0.25, 0.50), (0.50, 0.75), (0.75, 1.0001)]


def _bucket_label(lo: float, hi: float) -> str:
    return f'{lo:.2f}-{min(hi, 1.0):.2f}'


def _model_label(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)) or v == '' or pd.isna(v):
        return 'baseline_pre_versioning'
    return str(v)


def _err_stats(proj: pd.Series, actual: pd.Series) -> dict:
    err = proj - actual
    return {
        'n': int(len(err)),
        'mae': float(err.abs().mean()) if len(err) else float('nan'),
        'rmse': float(np.sqrt((err ** 2).mean())) if len(err) else float('nan'),
        'bias': float(err.mean()) if len(err) else float('nan'),
    }


def _win_prob_calibration(sub: pd.DataFrame) -> list[dict]:
    """For each WP bucket: n, mean predicted win prob, actual win rate."""
    out = []
    for lo, hi in WP_BUCKETS:
        b = sub[(sub['win_probability'] >= lo) & (sub['win_probability'] < hi)]
        n = int(len(b))
        if n == 0:
            out.append({
                'bucket': _bucket_label(lo, hi),
                'lo': lo, 'hi': min(hi, 1.0),
                'n': 0,
                'mean_predicted': None,
                'actual_win_rate': None,
                'abs_gap': None,
                'sufficient': False,
            })
            continue
        actual_win = (b['actual_my_final'] > b['actual_opp_final']).mean()
        mean_pred = b['win_probability'].mean()
        out.append({
            'bucket': _bucket_label(lo, hi),
            'lo': lo, 'hi': min(hi, 1.0),
            'n': n,
            'mean_predicted': float(mean_pred),
            'actual_win_rate': float(actual_win),
            'abs_gap': float(abs(mean_pred - actual_win)),
            'sufficient': n >= MIN_N_PER_BUCKET,
        })
    return out


def build_report() -> tuple[str, dict]:
    if not HISTORY.exists():
        return f'# Projection Accuracy Report\n\nNo predictions_history at {HISTORY}.\n', {}

    df = pd.read_csv(HISTORY)
    df['model_version'] = df['model_version'].apply(_model_label)
    df = df.dropna(subset=['actual_my_final', 'actual_opp_final']).copy()

    today = datetime.now().strftime('%Y-%m-%d')
    lines: list[str] = []
    lines.append(f'# Projection Accuracy Report\n')
    lines.append(f'**Generated:** {today}  ')
    lines.append(f'**Source:** `data/outputs/predictions_history.csv`  ')
    lines.append(f'**Backfilled rows:** {len(df)}  ')
    lines.append(f'**Minimum N per bucket to trust:** {MIN_N_PER_BUCKET}\n')

    if len(df) == 0:
        lines.append('\nNo backfilled rows yet. Run `scripts/xfp/fetch_closed_matchup_actuals.py` once at least one period closes.\n')
        REPORT.write_text('\n'.join(lines), encoding='utf-8')
        return '\n'.join(lines), {}

    # 1. Periods covered
    periods = sorted(df['period'].unique().tolist())
    lines.append('## 1. Periods covered\n')
    lines.append('| Period | n rows | my_final | opp_final | model_versions |')
    lines.append('|---|---|---|---|---|')
    for p in periods:
        sub = df[df['period'] == p]
        models = ', '.join(sorted(sub['model_version'].unique()))
        my_f = sub['actual_my_final'].iloc[0]
        opp_f = sub['actual_opp_final'].iloc[0]
        lines.append(f'| {int(p)} | {len(sub)} | {my_f:.1f} | {opp_f:.1f} | {models} |')
    lines.append('')

    # 2. Per-model error metrics (all snapshots)
    lines.append('## 2. Error metrics — all snapshots\n')
    lines.append('Error = projected − actual. Bias > 0 means model over-projects.\n')
    lines.append('| Model | n | my MAE | my RMSE | my bias | opp MAE | opp RMSE | opp bias |')
    lines.append('|---|---|---|---|---|---|---|---|')
    per_model_metrics: dict[str, dict] = {}
    for m, sub in df.groupby('model_version'):
        my = _err_stats(sub['my_projected_total'], sub['actual_my_final'])
        opp = _err_stats(sub['opp_projected_total'], sub['actual_opp_final'])
        per_model_metrics[m] = {'my': my, 'opp': opp}
        lines.append(
            f'| `{m}` | {my["n"]} | {my["mae"]:.1f} | {my["rmse"]:.1f} | '
            f'{my["bias"]:+.1f} | {opp["mae"]:.1f} | {opp["rmse"]:.1f} | {opp["bias"]:+.1f} |'
        )
    lines.append('')

    # 3. Per-model error metrics (latest snapshot per (period, model) only)
    lines.append('## 3. Error metrics — latest snapshot per (period, model)\n')
    lines.append("This is the \"what the dashboard showed at end of week\" view.\n")
    df_sorted = df.sort_values('timestamp') if 'timestamp' in df.columns else df.sort_values('date')
    latest = df_sorted.groupby(['period', 'model_version']).tail(1)
    lines.append('| Period | Model | proj my | actual my | err my | proj opp | actual opp | err opp |')
    lines.append('|---|---|---|---|---|---|---|---|')
    for _, r in latest.sort_values(['period', 'model_version']).iterrows():
        em = r['my_projected_total'] - r['actual_my_final']
        eo = r['opp_projected_total'] - r['actual_opp_final']
        lines.append(
            f'| {int(r["period"])} | `{r["model_version"]}` | '
            f'{r["my_projected_total"]:.1f} | {r["actual_my_final"]:.1f} | {em:+.1f} | '
            f'{r["opp_projected_total"]:.1f} | {r["actual_opp_final"]:.1f} | {eo:+.1f} |'
        )
    lines.append('')

    # 4. Win-probability calibration
    lines.append('## 4. Win-probability calibration\n')
    lines.append(f'Buckets on raw `win_probability`. A well-calibrated model has mean predicted ≈ actual win rate. Buckets with N < {MIN_N_PER_BUCKET} are flagged INSUFFICIENT.\n')

    per_model_calib: dict[str, list[dict]] = {}
    any_sufficient = False
    for m, sub in df.groupby('model_version'):
        buckets = _win_prob_calibration(sub)
        per_model_calib[m] = buckets
        lines.append(f'### `{m}` (n={len(sub)})\n')
        lines.append('| Bucket | n | mean predicted | actual win rate | abs gap | status |')
        lines.append('|---|---|---|---|---|---|')
        for b in buckets:
            if b['n'] == 0:
                lines.append(f'| {b["bucket"]} | 0 | — | — | — | empty |')
                continue
            status = 'OK' if b['sufficient'] else 'INSUFFICIENT'
            if b['sufficient']:
                any_sufficient = True
            lines.append(
                f'| {b["bucket"]} | {b["n"]} | {b["mean_predicted"]:.3f} | '
                f'{b["actual_win_rate"]:.3f} | {b["abs_gap"]:.3f} | {status} |'
            )
        lines.append('')

    # 5. Verdict
    lines.append('## 5. Verdict\n')
    if not any_sufficient:
        lines.append(
            f'**INSUFFICIENT** — no win-probability bucket has reached N ≥ {MIN_N_PER_BUCKET} across enough closed periods. '
            'Need more closed weeks before calibration can be trusted.\n'
        )
    else:
        lines.append(
            f'At least one bucket has N ≥ {MIN_N_PER_BUCKET}. See `data/outputs/calibration_summary.json` '
            'for the machine-readable summary consumed by the calibration gate.\n'
        )

    lines.append('\n---\n')
    lines.append('Re-generated by `scripts/xfp/report_calibration.py` — overwritten on every refresh.\n')

    report_text = '\n'.join(lines)
    REPORT.write_text(report_text, encoding='utf-8')

    summary = {
        'generated_at': today,
        'n_backfilled_rows': int(len(df)),
        'periods_covered': [int(p) for p in periods],
        'min_n_per_bucket': MIN_N_PER_BUCKET,
        'any_bucket_sufficient': bool(any_sufficient),
        'models': {
            m: {
                'error_metrics': per_model_metrics[m],
                'win_prob_calibration': per_model_calib[m],
            }
            for m in per_model_metrics
        },
    }

    if any_sufficient:
        SUMMARY.write_text(json.dumps(summary, indent=2), encoding='utf-8')

    return report_text, summary


def main():
    report_text, summary = build_report()
    if not summary:
        print('No data to report.')
        return
    n_models = len(summary.get('models', {}))
    print(f'Wrote {REPORT} ({len(report_text)} bytes, {n_models} model(s)).')
    if summary.get('any_bucket_sufficient'):
        print(f'Wrote {SUMMARY} (>=1 bucket has N >= {MIN_N_PER_BUCKET}).')
    else:
        print(f'No bucket reached N >= {MIN_N_PER_BUCKET}; INSUFFICIENT verdict. JSON summary not written.')


if __name__ == '__main__':
    main()

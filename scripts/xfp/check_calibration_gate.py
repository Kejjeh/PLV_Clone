"""Calibration gate - exit 0 if well-calibrated, 1 otherwise.

Reads `data/outputs/calibration_summary.json` (written by
`scripts/xfp/report_calibration.py`).

Definitions:
  * "well-calibrated" = for every bucket with N >= MIN_N_PER_BUCKET,
    |mean_predicted_win_prob - actual_win_rate| <= MAX_ABS_GAP.
  * If JSON missing OR no model has any bucket with N >= MIN_N_PER_BUCKET,
    we report INSUFFICIENT and exit 0 (cannot fail what we cannot measure).
  * If outcomes lack W/L diversity (all wins or all losses across the
    backfilled sample), we report INSUFFICIENT and exit 0. Calibration
    cannot be assessed when every observed outcome is the same direction.
  * If any sufficient bucket has abs_gap > MAX_ABS_GAP, we exit 1 and
    print the offending bucket(s).

Intended use: a cheap CI-style check we can wire into refresh_dashboards
or a Monday-morning routine. Catches "model became miscalibrated" silently.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUMMARY = ROOT / 'data' / 'outputs' / 'calibration_summary.json'

MAX_ABS_GAP = 0.15  # 15-percentage-point tolerance between predicted and actual win rate
MIN_N_PER_BUCKET = 5  # mirrors report_calibration.py
MIN_DISTINCT_PERIODS = 5  # need >= N closed periods before trusting any verdict


def _has_outcome_diversity(data: dict) -> bool:
    """At least one win AND one loss must appear in the backfilled sample."""
    seen_win = False
    seen_loss = False
    for m in data.get('models', {}).values():
        for b in m.get('win_prob_calibration', []):
            rate = b.get('actual_win_rate')
            n = b.get('n', 0)
            if n == 0 or rate is None:
                continue
            if rate < 1.0:
                seen_loss = True
            if rate > 0.0:
                seen_win = True
    return seen_win and seen_loss


def main() -> int:
    if not SUMMARY.exists():
        print(f'INSUFFICIENT - no calibration_summary.json yet at {SUMMARY}.')
        print('Run `scripts/xfp/report_calibration.py` after at least one period closes.')
        return 0

    data = json.loads(SUMMARY.read_text(encoding='utf-8'))
    models = data.get('models', {})
    if not models:
        print('INSUFFICIENT - calibration_summary.json contains no models.')
        return 0

    n_periods = len(data.get('periods_covered', []))
    if n_periods < MIN_DISTINCT_PERIODS:
        print(f'INSUFFICIENT - only {n_periods} closed period(s); need >= {MIN_DISTINCT_PERIODS} before calibration is trustworthy.')
        return 0

    if not _has_outcome_diversity(data):
        print('INSUFFICIENT - all backfilled outcomes are same-direction (all wins or all losses).')
        print('Cannot validate calibration without mixed W/L outcomes. Gate is a pass-through.')
        return 0

    any_sufficient = False
    failures: list[str] = []
    for model_name, m in models.items():
        for b in m.get('win_prob_calibration', []):
            if not b.get('sufficient'):
                continue
            any_sufficient = True
            gap = b.get('abs_gap')
            if gap is None:
                continue
            if gap > MAX_ABS_GAP:
                failures.append(
                    f'  {model_name} bucket {b["bucket"]} '
                    f'(n={b["n"]}): predicted={b["mean_predicted"]:.3f} '
                    f'actual={b["actual_win_rate"]:.3f} gap={gap:.3f} > {MAX_ABS_GAP}'
                )

    if not any_sufficient:
        print(f'INSUFFICIENT - no bucket has reached N >= {MIN_N_PER_BUCKET} for any model.')
        print('Calibration gate is a pass-through until more periods close.')
        return 0

    if failures:
        print(f'MISCALIBRATED - {len(failures)} bucket(s) exceed |gap| > {MAX_ABS_GAP}:')
        for f in failures:
            print(f)
        print('\nInvestigate the model that owns these buckets. See docs/calibration.md.')
        return 1

    print(f'OK - all sufficient (N >= {MIN_N_PER_BUCKET}) buckets within |gap| <= {MAX_ABS_GAP}.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

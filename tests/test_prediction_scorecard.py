# -*- coding: utf-8 -*-
"""§10 of the verdict scorecard — the prediction book.

The properties worth locking are the ones that stop the section flattering
whoever made the claims: open claims must stay visible, a thin book must not
be quoted as a hit rate, and misses must be named.
"""
import importlib
import json
from dataclasses import asdict
from datetime import date

import pytest

from plv_clone.decisions.logger import build_prediction_record
from plv_clone.decisions.prediction import build_prediction

TODAY = date(2026, 8, 27)


@pytest.fixture
def scorecard(tmp_path, monkeypatch):
    mod = importlib.import_module('scripts.xfp.run_verdict_scorecard')
    monkeypatch.setattr(mod, 'DECISIONS_ROOT', tmp_path)
    return mod


def _write(root, name, bucket, *, threshold, made_by, settlement=None,
           stated=date(2026, 8, 5), days=21, claim=None):
    pred = build_prediction(
        claim=claim or f'{name} clears {threshold} FP', metric='total_fp',
        threshold=threshold, window_days=days, stated_on=stated, made_by=made_by)
    rec = build_prediction_record(
        snapshot_date=stated.isoformat(), player_name=name, mlbam_id=1,
        bucket=bucket, prediction=pred)
    payload = asdict(rec)
    if settlement:
        payload['prediction_settlement'] = settlement
    d = root / stated.isoformat()
    d.mkdir(parents=True, exist_ok=True)
    (d / f'{rec.decision_id}.json').write_text(json.dumps(payload), encoding='utf-8')


def test_empty_book_tells_you_how_to_start(scorecard, tmp_path, capsys):
    scorecard._prediction_section(TODAY)
    out = capsys.readouterr().out
    assert 'no predictions logged yet' in out
    assert 'log_prediction.py' in out


def test_open_claims_are_listed_with_their_deadlines(scorecard, tmp_path, capsys):
    _write(tmp_path, 'Trent Grisham', 'H', threshold=60, made_by='claude',
           claim='Grisham clears 60 FP in three weeks')
    scorecard._prediction_section(TODAY)
    out = capsys.readouterr().out
    assert 'OPEN CLAIMS (1)' in out
    assert 'Grisham clears 60 FP in three weeks' in out
    assert '2026-08-26' in out


def test_a_thin_book_refuses_to_pose_as_skill(scorecard, tmp_path, capsys):
    _write(tmp_path, 'A', 'H', threshold=60, made_by='claude',
           settlement={'status': 'HIT', 'margin': 5.0, 'threshold': 60.0})
    scorecard._prediction_section(TODAY)
    out = capsys.readouterr().out
    assert 'too few to read as skill' in out


def test_misses_are_named_not_buried(scorecard, tmp_path, capsys):
    _write(tmp_path, 'Whiffed Guy', 'H', threshold=60, made_by='claude',
           claim='Whiffed Guy clears 60 FP',
           settlement={'status': 'MISS', 'margin': -22.0, 'threshold': 60.0})
    scorecard._prediction_section(TODAY)
    out = capsys.readouterr().out
    assert 'MISSES (1)' in out
    assert 'Whiffed Guy clears 60 FP' in out
    assert '-22.0' in out


def test_book_is_split_by_author(scorecard, tmp_path, capsys):
    _write(tmp_path, 'A', 'H', threshold=60, made_by='claude',
           settlement={'status': 'HIT', 'margin': 3.0, 'threshold': 60.0})
    _write(tmp_path, 'B', 'H', threshold=40, made_by='josh',
           settlement={'status': 'MISS', 'margin': -8.0, 'threshold': 40.0})
    scorecard._prediction_section(TODAY)
    out = capsys.readouterr().out
    assert 'claude' in out and 'josh' in out
    assert 'author' in out


def test_settled_mirror_wins_over_the_source_copy(scorecard, tmp_path, capsys):
    """The same decision_id in both trees must count once, graded."""
    _write(tmp_path, 'Dup', 'H', threshold=60, made_by='claude')
    src = next((tmp_path / '2026-08-05').glob('*.json'))
    payload = json.loads(src.read_text(encoding='utf-8'))
    payload['prediction_settlement'] = {'status': 'HIT', 'margin': 1.0,
                                        'threshold': 60.0}
    mirror = tmp_path / 'settled' / '2026-08-05'
    mirror.mkdir(parents=True, exist_ok=True)
    (mirror / src.name).write_text(json.dumps(payload), encoding='utf-8')

    scorecard._prediction_section(TODAY)
    out = capsys.readouterr().out
    assert 'n=1' in out                      # counted once, not twice
    assert 'OPEN CLAIMS' not in out          # the graded copy won


def test_paired_loader_still_works_after_the_refactor(scorecard, tmp_path):
    # _load_paired_records was rewritten onto the shared walker; it must still
    # return only records carrying a counterfactual settlement
    _write(tmp_path, 'A', 'H', threshold=60, made_by='claude')
    assert scorecard._load_paired_records(TODAY) == []
    assert len(scorecard._load_prediction_records()) == 1

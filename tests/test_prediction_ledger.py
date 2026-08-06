# -*- coding: utf-8 -*-
"""Falsifiable-prediction ledger (schema v4).

The properties that make the ledger worth keeping are the ones that stop it
flattering whoever wrote the claim: a claim must be falsifiable to be logged,
it cannot be settled before its horizon, and a player who never played scores
zero rather than being excused.
"""
import json
from dataclasses import asdict
from datetime import date

import pytest

from plv_clone.decisions.logger import (
    DecisionRecord, build_prediction_record, is_prediction_record, log_decision)
from plv_clone.decisions.prediction import (
    HIT, MISS, PENDING, UNSETTLEABLE, build_prediction, is_ripe, score_book,
    settle_prediction)

STATED = date(2026, 8, 5)


def _pred(**kw):
    base = dict(claim='Grisham clears 60 FP in three weeks', metric='total_fp',
                threshold=60.0, window_days=21, stated_on=STATED)
    base.update(kw)
    return build_prediction(**base)


class TestClaimConstruction:
    def test_horizon_is_derived_from_the_window(self):
        assert _pred().horizon_end == '2026-08-26'

    def test_rejects_a_claim_with_no_words(self):
        with pytest.raises(ValueError):
            _pred(claim='   ')

    def test_rejects_an_unknown_metric(self):
        with pytest.raises(ValueError, match='metric'):
            _pred(metric='vibes')

    def test_rejects_a_zero_or_negative_window(self):
        with pytest.raises(ValueError, match='window_days'):
            _pred(window_days=0)

    def test_margin_claim_requires_a_comparator(self):
        with pytest.raises(ValueError, match='compares against'):
            _pred(metric='fp_margin_vs', threshold=15.0)

    def test_the_claim_is_immutable_once_made(self):
        p = _pred()
        with pytest.raises(Exception):
            p.threshold = 5.0        # frozen: a target cannot be moved later


class TestSettlement:
    def test_never_settles_before_the_horizon(self):
        out = settle_prediction(_pred().as_dict(), realized=999.0,
                                today=date(2026, 8, 25))
        assert out['status'] == PENDING

    def test_settles_on_the_horizon_date_itself(self):
        assert is_ripe(_pred().as_dict(), date(2026, 8, 26))

    def test_hit_and_miss_around_the_threshold(self):
        p = _pred().as_dict()
        after = date(2026, 8, 27)
        assert settle_prediction(p, realized=72.0, today=after)['status'] == HIT
        assert settle_prediction(p, realized=48.0, today=after)['status'] == MISS

    def test_exactly_on_the_threshold_counts_as_a_hit_for_at_least(self):
        out = settle_prediction(_pred().as_dict(), realized=60.0,
                                today=date(2026, 8, 27))
        assert out['status'] == HIT
        assert out['margin'] == 0.0

    def test_at_most_direction_inverts(self):
        p = _pred(direction='at_most', threshold=20.0,
                  claim='Duran stays under 20 FP').as_dict()
        after = date(2026, 8, 27)
        assert settle_prediction(p, realized=9.0, today=after)['status'] == HIT
        assert settle_prediction(p, realized=31.0, today=after)['status'] == MISS

    def test_zero_playing_time_settles_it_does_not_excuse(self):
        # the house rule: playing time is part of what was predicted
        out = settle_prediction(_pred().as_dict(), realized=0.0,
                                today=date(2026, 8, 27))
        assert out['status'] == MISS
        assert out['realized'] == 0.0

    def test_a_failed_lookup_is_unsettleable_not_a_miss(self):
        out = settle_prediction(_pred().as_dict(), realized=None,
                                today=date(2026, 8, 27))
        assert out['status'] == UNSETTLEABLE

    def test_margin_claim_compares_the_two_players(self):
        p = _pred(metric='fp_margin_vs', threshold=15.0, vs_name='Ezequiel Duran',
                  vs_mlbam=677649,
                  claim='Grisham outscores Duran by 15+').as_dict()
        after = date(2026, 8, 27)
        win = settle_prediction(p, realized=70.0, comparator_realized=40.0,
                                today=after)
        assert win['status'] == HIT and win['observed'] == 30.0
        lose = settle_prediction(p, realized=70.0, comparator_realized=65.0,
                                 today=after)
        assert lose['status'] == MISS and lose['observed'] == 5.0

    def test_margin_claim_needs_the_comparator_resolved(self):
        p = _pred(metric='fp_margin_vs', threshold=15.0, vs_name='X',
                  vs_mlbam=1).as_dict()
        out = settle_prediction(p, realized=70.0, comparator_realized=None,
                                today=date(2026, 8, 27))
        assert out['status'] == UNSETTLEABLE


class TestRecord:
    def test_round_trips_through_disk(self, tmp_path, monkeypatch):
        import plv_clone.decisions.logger as lg
        monkeypatch.setattr(lg, 'DECISIONS_ROOT', tmp_path)
        rec = build_prediction_record(
            snapshot_date=STATED.isoformat(), player_name='Trent Grisham',
            mlbam_id=596019, bucket='H', prediction=_pred())
        path = log_decision(rec)
        payload = json.loads(path.read_text(encoding='utf-8'))
        back = DecisionRecord(**payload)
        assert back.record_schema == 4
        assert is_prediction_record(back)
        assert back.prediction['threshold'] == 60.0
        assert back.prediction_settlement is None

    def test_refuses_a_claim_that_cannot_be_settled(self):
        with pytest.raises(ValueError, match='cannot be settled'):
            build_prediction_record(
                snapshot_date=STATED.isoformat(), player_name='X',
                mlbam_id=1, bucket='H',
                prediction={'claim': 'he will be good', 'metric': 'total_fp',
                            'threshold': None, 'horizon_end': '2026-08-26'})

    def test_legacy_records_still_parse(self):
        # v1/v2/v3 payloads predate every v4 field and must keep loading
        legacy = {'decision_id': 'x', 'snapshot_date': '2026-06-01',
                  'player_name': 'Old', 'mlbam_id': 1, 'bucket': 'H',
                  'verdict_top': 'BUY', 'reason_tag': None, 'confidence': None}
        rec = DecisionRecord(**legacy)
        assert rec.prediction is None
        assert not is_prediction_record(rec)
        assert 'prediction' in asdict(rec)


class TestBook:
    def test_pending_is_reported_not_hidden(self):
        book = [{'status': HIT, 'margin': 10.0}, {'status': MISS, 'margin': -5.0},
                {'status': PENDING}, {'status': UNSETTLEABLE}]
        s = score_book(book)
        assert s['n_total'] == 4 and s['n_resolved'] == 2
        assert s['n_pending'] == 1 and s['n_unsettleable'] == 1
        assert s['hit_rate'] == 0.5

    def test_an_unresolved_book_quotes_no_hit_rate(self):
        s = score_book([{'status': PENDING}, {'status': PENDING}])
        assert s['hit_rate'] is None
        assert s['n_resolved'] == 0

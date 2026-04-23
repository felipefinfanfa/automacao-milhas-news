"""Testes da sequência de 3 dias de e-mail."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from src.email.sequence import (
    get_day1_sent_at,
    has_sent,
    record_sent,
    schedule_followup_days,
    should_send_day,
)


def _make_session(day1_sent_at=None, already_sent_day=None):
    session = MagicMock()

    def query_side_effect(model):
        mock_query = MagicMock()

        def filter_by_side_effect(**kwargs):
            mock_filter = MagicMock()
            day = kwargs.get("day_number")
            if already_sent_day is not None and day == already_sent_day:
                mock_filter.first.return_value = MagicMock()
            elif day == 1 and day1_sent_at is not None:
                log_mock = MagicMock()
                log_mock.sent_at = day1_sent_at
                mock_filter.first.return_value = log_mock
            else:
                mock_filter.first.return_value = None
            return mock_filter

        mock_query.filter_by.side_effect = filter_by_side_effect
        return mock_query

    session.query.side_effect = query_side_effect
    session.add = MagicMock()
    session.commit = MagicMock()
    return session


USER_ID = "user-111"
PROMO_ID = "promo-222"


def test_should_send_day1_when_not_sent():
    session = _make_session()
    assert should_send_day(session, USER_ID, PROMO_ID, 1, None) is True


def test_should_not_send_day1_when_already_sent():
    session = _make_session(already_sent_day=1)
    assert should_send_day(session, USER_ID, PROMO_ID, 1, None) is False


def test_day2_not_sent_if_promo_expired(past_date):
    session = _make_session(day1_sent_at=past_date - timedelta(hours=48))
    assert should_send_day(session, USER_ID, PROMO_ID, 2, past_date) is False


def test_day2_not_sent_before_24h():
    now = datetime.now(timezone.utc)
    day1_sent = now - timedelta(hours=12)
    session = _make_session(day1_sent_at=day1_sent)
    future_end = now + timedelta(days=10)
    assert should_send_day(session, USER_ID, PROMO_ID, 2, future_end) is False


def test_day2_sent_after_24h():
    now = datetime.now(timezone.utc)
    day1_sent = now - timedelta(hours=25)
    session = _make_session(day1_sent_at=day1_sent)
    future_end = now + timedelta(days=10)
    assert should_send_day(session, USER_ID, PROMO_ID, 2, future_end) is True


def test_day3_not_sent_without_day1():
    session = _make_session()
    assert should_send_day(session, USER_ID, PROMO_ID, 3, None) is False


def test_promo_extension_does_not_restart_sequence():
    """Prorrogação de promoção (end_date alterada) não reinicia a sequência."""
    now = datetime.now(timezone.utc)
    day1_sent = now - timedelta(hours=50)
    session = _make_session(day1_sent_at=day1_sent, already_sent_day=2)

    new_end = now + timedelta(days=30)
    assert should_send_day(session, USER_ID, PROMO_ID, 2, new_end) is False
    assert should_send_day(session, USER_ID, PROMO_ID, 3, new_end) is True


def test_schedule_followup_days_skips_expired():
    """Quando a promo expira antes do Dia 2, nenhum job deve ser agendado."""
    scheduler = MagicMock()
    session = MagicMock()
    now = datetime.now(timezone.utc)
    day1_sent = now - timedelta(hours=1)
    # Promo expira em 10h — antes do Dia 2 (24h) e Dia 3 (48h)
    promo_expires_soon = now + timedelta(hours=10)

    schedule_followup_days(
        scheduler=scheduler,
        session=session,
        user_id=USER_ID,
        promo_id=PROMO_ID,
        day1_sent_at=day1_sent,
        promo_ends_at=promo_expires_soon,
        send_callback=MagicMock(),
    )

    scheduler.add_job.assert_not_called()


def test_schedule_followup_days_schedules_both(future_date):
    scheduler = MagicMock()
    session = MagicMock()
    day1_sent = datetime.now(timezone.utc)

    schedule_followup_days(
        scheduler=scheduler,
        session=session,
        user_id=USER_ID,
        promo_id=PROMO_ID,
        day1_sent_at=day1_sent,
        promo_ends_at=future_date,
        send_callback=MagicMock(),
    )

    assert scheduler.add_job.call_count == 2

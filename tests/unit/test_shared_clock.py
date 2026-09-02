"""Unit tests — shared/clock.py"""

from datetime import UTC, timedelta

from razorguard.shared.clock import is_expired, utcnow, utcnow_plus


def test_utcnow_is_timezone_aware():
    now = utcnow()
    assert now.tzinfo is not None
    assert now.tzinfo == UTC


def test_utcnow_plus_future():
    future = utcnow_plus(seconds=60)
    assert future > utcnow()


def test_is_expired_past():
    past = utcnow() - timedelta(seconds=1)
    assert is_expired(past)


def test_is_expired_future():
    future = utcnow() + timedelta(seconds=60)
    assert not is_expired(future)

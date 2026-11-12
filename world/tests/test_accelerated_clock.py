"""AcceleratedClock (#129): game time flows at GAME_CLOCK_SPEED × real time,
from an anchor stored on the GameClock row, and can be frozen and resumed.

Real time is driven by patching `timezone.now` as seen from `world.clocks`
and `world.models`, so every test controls both clocks exactly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from racing.models import Race
from world.clocks import AcceleratedClock, MockClock
from world.models import GameClock

REAL_START = datetime(2026, 11, 12, 12, 0, tzinfo=dt_timezone.utc)
GAME_START = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)


class RealTime:
    """A controllable stand-in for django.utils.timezone.now."""

    def __init__(self, at: datetime):
        self.at = at

    def __call__(self) -> datetime:
        return self.at

    def pass_(self, delta: timedelta) -> None:
        self.at += delta


@pytest.fixture
def real(monkeypatch):
    clock = RealTime(REAL_START)
    monkeypatch.setattr("world.clocks.timezone.now", clock)
    monkeypatch.setattr("world.models.timezone.now", clock)
    return clock


@pytest.fixture
def accelerated(db, real):
    with override_settings(GAME_CLOCK_SPEED=24):
        clock = AcceleratedClock()
        clock.set(GAME_START)
        yield clock


def test_one_real_hour_is_one_game_day(accelerated, real):
    real.pass_(timedelta(hours=1))
    assert accelerated.now() == GAME_START + timedelta(days=1)


def test_time_moves_between_two_reads(accelerated, real):
    first = accelerated.now()
    real.pass_(timedelta(seconds=1))
    assert accelerated.now() == first + timedelta(seconds=24)


def test_set_re_anchors_and_time_flows_on_from_the_new_value(accelerated, real):
    real.pass_(timedelta(hours=3))
    target = GAME_START + timedelta(days=30)
    accelerated.set(target)
    assert accelerated.now() == target
    real.pass_(timedelta(minutes=30))
    assert accelerated.now() == target + timedelta(hours=12)


def test_advance_by_keeps_the_time_that_already_flowed(accelerated, real):
    real.pass_(timedelta(hours=1))  # one game day flowed since the anchor
    accelerated.advance_by(timedelta(hours=2))
    assert accelerated.now() == GAME_START + timedelta(days=1, hours=2)


def test_freeze_holds_time_and_resume_continues_without_a_jump(accelerated, real):
    real.pass_(timedelta(hours=1))
    assert accelerated.freeze() is True
    frozen_at = accelerated.now()
    assert frozen_at == GAME_START + timedelta(days=1)

    real.pass_(timedelta(hours=10))
    assert accelerated.now() == frozen_at
    assert accelerated.frozen is True

    assert accelerated.resume() is True
    assert accelerated.now() == frozen_at
    real.pass_(timedelta(hours=1))
    assert accelerated.now() == frozen_at + timedelta(days=1)


def test_freeze_and_resume_are_idempotent(accelerated, real):
    assert accelerated.resume() is False
    assert accelerated.freeze() is True
    real.pass_(timedelta(hours=1))
    assert accelerated.freeze() is False
    assert accelerated.now() == GAME_START


def test_set_while_frozen_moves_the_frozen_moment_and_stays_frozen(accelerated, real):
    accelerated.freeze()
    target = GAME_START + timedelta(days=7)
    accelerated.set(target)
    real.pass_(timedelta(hours=5))
    assert accelerated.now() == target
    assert accelerated.frozen is True


def test_advance_to_next_due_looks_after_the_flowed_time(accelerated, real):
    real.pass_(timedelta(hours=1))  # now GAME_START + 1 day
    for name, offset in (("Already passed", timedelta(hours=12)),
                         ("Next", timedelta(days=2))):
        Race.objects.create(
            name=name, course=[{"length": 500.0, "gradient": 0.0}],
            starts_at=GAME_START + offset, status=Race.Status.SCHEDULED,
        )
    accelerated.advance_to_next_due()
    assert accelerated.now() == GAME_START + timedelta(days=2)


def test_a_never_anchored_row_starts_flowing_from_current(db, real):
    GameClock.objects.create(pk=1, current=GAME_START, anchored_at=None)
    with override_settings(GAME_CLOCK_SPEED=24):
        clock = AcceleratedClock()
        assert clock.now() == GAME_START
        real.pass_(timedelta(hours=1))
        assert clock.now() == GAME_START + timedelta(days=1)


def test_the_migration_anchors_a_clock_row_that_predates_it(db, real):
    from importlib import import_module

    from django.apps import apps

    GameClock.objects.create(pk=1, current=GAME_START, anchored_at=None)
    import_module("world.migrations.0023_accelerated_clock").anchor_existing_clock(apps, None)
    assert GameClock.load().anchored_at == REAL_START


@pytest.mark.parametrize("speed", [0, -3, 1.5, "24", True])
def test_a_bad_speed_is_refused(accelerated, speed):
    with override_settings(GAME_CLOCK_SPEED=speed):
        with pytest.raises(ImproperlyConfigured):
            accelerated.now()


def test_the_mock_clock_stays_stopped_whatever_the_anchor_says(db, real):
    clock = MockClock()
    clock.set(GAME_START)
    real.pass_(timedelta(hours=5))
    assert clock.now() == GAME_START
    clock.advance_by(timedelta(hours=1))
    assert clock.now() == GAME_START + timedelta(hours=1)


def test_switching_from_mock_to_accelerated_flows_from_the_last_write(db, real):
    MockClock().set(GAME_START)
    real.pass_(timedelta(hours=1))
    with override_settings(GAME_CLOCK_SPEED=24):
        # The mock clock's write anchored at REAL_START, so an hour has flowed.
        assert AcceleratedClock().now() == GAME_START + timedelta(days=1)


def test_the_accelerated_clock_is_a_mock_clock():
    # Every `mock_clock` and `seed_world --set-clock` guard is an isinstance
    # check on MockClock; the subclass is what lets them work on staging.
    assert isinstance(AcceleratedClock(), MockClock)

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from racing.models import Race
from world.clocks import MockClock, RealClock
from world.models import GameClock


def test_real_clock_returns_current_real_time():
    before = timezone.now()
    result = RealClock().now()
    after = timezone.now()

    assert before <= result <= after


def test_mock_clock_now_reads_the_stored_row(db):
    clock = GameClock.load()

    assert MockClock().now() == clock.current


def test_mock_clock_set_moves_the_stored_row(db):
    GameClock.load()
    target = timezone.now() + timedelta(days=30)

    MockClock().set(target)

    assert GameClock.load().current == target


def test_mock_clock_advance_by_adds_a_delta(db):
    clock = GameClock.load()
    before = clock.current

    MockClock().advance_by(timedelta(hours=6))

    assert GameClock.load().current == before + timedelta(hours=6)


def test_mock_clock_advance_to_next_due_jumps_to_the_next_scheduled_race(db):
    clock = GameClock.load()
    due_at = clock.current + timedelta(hours=3)
    Race.objects.create(
        name="Next Up", course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=due_at, status=Race.Status.SCHEDULED,
    )

    MockClock().advance_to_next_due()

    assert GameClock.load().current == due_at


def test_mock_clock_advance_to_next_due_does_nothing_when_none_scheduled(db):
    clock = GameClock.load()
    before = clock.current

    MockClock().advance_to_next_due()

    assert GameClock.load().current == before

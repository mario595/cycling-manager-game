"""Automatic seasons (#129): with AUTO_DECLARE_SEASONS on, the tick declares
the next season of the world calendar once at most one declared season has
not yet ended — so a running world never runs out of calendar."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.test import override_settings

from racing.models import Race
from schedule.models import Season, SeasonTransition
from world.clocks import MockClock
from world.services import tick
from world.world_setup import build_world

START = datetime(2030, 1, 7, tzinfo=dt_timezone.utc)  # a Monday


@pytest.fixture
def calendar(tmp_path, monkeypatch):
    """A raceless twelve-week season keeps these ticks fast: what is under
    test is the calendar bookkeeping, not the racing."""
    path = tmp_path / "calendar.json"
    path.write_text(json.dumps({
        "number": 1, "starts_at": "2027-03-01T00:00:00Z", "races": [],
    }))
    monkeypatch.setattr("world.world_setup.WORLD_CALENDAR", path)
    return path


def world(calendar, seasons: int):
    """Exactly `seasons` seasons: the building tick runs with the rule off,
    whatever the test then turns on."""
    with override_settings(AUTO_DECLARE_SEASONS=False):
        _build(calendar, seasons)


def _build(calendar, seasons: int):
    build_world(
        starts_at=START, seasons=seasons, teams=2, trainers=1,
        calendar=calendar, set_clock=True,
    )


def numbers():
    return list(Season.objects.order_by("number").values_list("number", flat=True))


def test_off_by_default(db, calendar):
    world(calendar, seasons=1)
    run = tick()
    assert run.seasons_declared == 0
    assert numbers() == [1]


@override_settings(AUTO_DECLARE_SEASONS=True)
def test_nothing_is_declared_while_two_seasons_are_ahead(db, calendar):
    world(calendar, seasons=2)
    assert tick().seasons_declared == 0
    assert numbers() == [1, 2]


@override_settings(AUTO_DECLARE_SEASONS=True)
def test_the_next_season_is_declared_when_one_is_left(db, calendar):
    world(calendar, seasons=2)
    second = Season.objects.get(number=2)
    MockClock().set(second.starts_at + timedelta(hours=1))

    run = tick()

    assert run.seasons_declared == 1
    assert numbers() == [1, 2, 3]
    assert Season.objects.get(number=3).starts_at == second.ends_at
    # Two seasons ahead again, so the next tick declares nothing.
    assert tick().seasons_declared == 0


@override_settings(AUTO_DECLARE_SEASONS=True)
def test_an_outage_past_the_last_season_still_opens_the_next(db, calendar):
    world(calendar, seasons=1)
    MockClock().set(Season.objects.get(number=1).ends_at + timedelta(days=1))

    run = tick()

    assert run.seasons_declared == 1
    assert run.seasons_closed == 1
    assert run.seasons_opened == 1
    assert numbers() == [1, 2]
    assert SeasonTransition.objects.filter(
        season__number=2, kind=SeasonTransition.Kind.OPENED,
    ).exists()


@override_settings(AUTO_DECLARE_SEASONS=True)
def test_a_world_with_no_seasons_is_left_alone(db, calendar):
    assert tick().seasons_declared == 0
    assert numbers() == []


@override_settings(AUTO_DECLARE_SEASONS=True)
def test_a_broken_calendar_is_recorded_and_the_tick_carries_on(db, calendar, monkeypatch):
    world(calendar, seasons=1)
    race = Race.objects.create(
        name="Still Raced", course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=MockClock().now(), status=Race.Status.SCHEDULED,
    )
    monkeypatch.setattr("world.world_setup.WORLD_CALENDAR", calendar.parent / "missing.json")

    run = tick()

    assert run.seasons_declared == 0
    assert "automatic season" in run.error
    assert run.finished_at is not None
    assert numbers() == [1]
    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED
    assert run.races_finished == 1

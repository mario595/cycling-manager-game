from __future__ import annotations

from datetime import timedelta

from django.test import override_settings
from rest_framework.test import APIClient

import world.services as world_services
from racing.models import Race
from schedule.models import Season, Week
from world.services import now


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_clock_endpoint_returns_current_game_time(db):
    # MockClock, not whatever GAME_CLOCK_CLASS a developer's environment
    # happens to be running: against RealClock, two separate now() reads
    # (the view's and this assertion's) would almost never match exactly.
    world_services._clock = None
    try:
        response = APIClient().get("/api/world/clock/")

        assert response.status_code == 200
        assert response.data["current"] == now().isoformat().replace("+00:00", "Z")
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_position_endpoint_reports_the_current_week(db):
    world_services._clock = None
    try:
        season = Season.objects.create(number=1, starts_at=now())
        Week.objects.create(
            season=season, number=1,
            starts_at=season.starts_at, ends_at=season.starts_at + timedelta(weeks=1),
        )

        response = APIClient().get("/api/schedule/position/")

        assert response.status_code == 200
        assert response.data["state"] == "in_season"
        assert response.data["season"] == 1
        assert response.data["week"] == 1
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_position_endpoint_reports_no_season_when_none_declared(db):
    world_services._clock = None
    try:
        response = APIClient().get("/api/schedule/position/")

        assert response.status_code == 200
        assert response.data["state"] == "no_season"
        assert response.data["season"] is None
        assert response.data["week"] is None
    finally:
        world_services._clock = None


def _create_season_with_weeks(starts_at) -> Season:
    season = Season.objects.create(number=1, starts_at=starts_at)
    for week_number in range(1, 13):
        week_start = starts_at + timedelta(weeks=week_number - 1)
        Week.objects.create(
            season=season, number=week_number,
            starts_at=week_start, ends_at=week_start + timedelta(weeks=1),
        )
    return season


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_calendar_returns_twelve_weeks(db):
    world_services._clock = None
    try:
        season = _create_season_with_weeks(now())
        week_one = Week.objects.get(season=season, number=1)
        Race.objects.create(
            name="Opening Classic",
            course=[{"length": 40000.0, "gradient": 0.0}],
            starts_at=week_one.starts_at + timedelta(hours=14),
            week=week_one,
        )

        response = APIClient().get("/api/schedule/calendar/")

        assert response.status_code == 200
        assert len(response.data["weeks"]) == 12
        non_empty = [w for w in response.data["weeks"] if w["races"]]
        assert len(non_empty) == 1
        assert non_empty[0]["races"][0]["name"] == "Opening Classic"
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_calendar_reports_off_season_with_no_weeks(db):
    world_services._clock = None
    try:
        _create_season_with_weeks(now() - timedelta(weeks=13))

        response = APIClient().get("/api/schedule/calendar/")

        assert response.status_code == 200
        assert response.data["state"] == "off_season"
        assert response.data["weeks"] == []
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_calendar_reports_no_season_before_any_is_declared(db):
    world_services._clock = None
    try:
        response = APIClient().get("/api/schedule/calendar/")

        assert response.status_code == 200
        assert response.data["state"] == "no_season"
        assert response.data["weeks"] == []
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_calendar_race_carries_status_and_distance(db):
    world_services._clock = None
    try:
        season = _create_season_with_weeks(now())
        week_one = Week.objects.get(season=season, number=1)
        Race.objects.create(
            name="Opening Classic",
            course=[{"length": 40000.0, "gradient": 0.0}, {"length": 10000.0, "gradient": 0.0}],
            starts_at=week_one.starts_at + timedelta(hours=14),
            week=week_one,
        )

        response = APIClient().get("/api/schedule/calendar/")

        race_data = next(w for w in response.data["weeks"] if w["races"])["races"][0]
        assert race_data["status"] == "scheduled"
        assert race_data["distance_km"] == 50.0
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_calendar_is_public(db):
    world_services._clock = None
    try:
        client = APIClient()
        assert client.get("/api/schedule/calendar/").status_code == 200
    finally:
        world_services._clock = None

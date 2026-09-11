from __future__ import annotations

from datetime import timedelta

from django.test import override_settings
from rest_framework.test import APIClient

import world.services as world_services
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

from __future__ import annotations

from rest_framework.test import APIClient

from world.models import GameClock


def test_clock_endpoint_returns_current_game_time(db):
    clock = GameClock.load()

    response = APIClient().get("/api/world/clock/")

    assert response.status_code == 200
    assert response.data["current"] == clock.current.isoformat().replace("+00:00", "Z")
    assert response.data["catch_up_hours"] == clock.catch_up_hours
    assert response.data["last_tick"] is None

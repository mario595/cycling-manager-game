from __future__ import annotations

from rest_framework.test import APIClient

from world.services import now


def test_clock_endpoint_returns_current_game_time(db):
    response = APIClient().get("/api/world/clock/")

    assert response.status_code == 200
    assert response.data["current"] == now().isoformat().replace("+00:00", "Z")

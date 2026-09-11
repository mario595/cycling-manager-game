from __future__ import annotations

from django.test import override_settings
from rest_framework.test import APIClient

import world.services as world_services
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

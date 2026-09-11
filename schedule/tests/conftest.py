from __future__ import annotations

import pytest
from django.test import override_settings

import world.services as world_services


@pytest.fixture(autouse=True)
def _use_mock_clock():
    """Copied from world/tests/conftest.py rather than imported across
    packages. Tests here need a clock they can set deterministically —
    load_season checks whether a season has started against
    world.services.now() — regardless of what GAME_CLOCK_CLASS a
    developer's local environment happens to be running.
    """
    world_services._clock = None
    with override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock"):
        yield
    world_services._clock = None

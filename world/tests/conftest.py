from __future__ import annotations

import pytest
from django.test import override_settings

import world.services as world_services


@pytest.fixture(autouse=True)
def _use_mock_clock():
    """Tests in this package need a clock they can set and step
    deterministically, regardless of what GAME_CLOCK_CLASS a developer's
    local environment happens to be running (dev.py's own default can be
    overridden by the GAME_CLOCK_CLASS env var — see config/settings/dev.py).
    Force MockClock here so the suite's behaviour never depends on that.

    world.services.get_clock() caches its resolved Clock at module level, so
    the cache is reset before and after every test — a test that further
    overrides GAME_CLOCK_CLASS itself (e.g. the RealClock guard test) would
    otherwise keep talking to whichever clock an earlier test resolved
    first.
    """
    world_services._clock = None
    with override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock"):
        yield
    world_services._clock = None

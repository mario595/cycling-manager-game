from __future__ import annotations

import pytest

import world.services as world_services


@pytest.fixture(autouse=True)
def _reset_clock_singleton():
    """world.services.get_clock() caches its resolved Clock at module level.
    A test that overrides settings.GAME_CLOCK_CLASS (e.g. @override_settings)
    would otherwise keep talking to whichever clock an earlier test resolved
    first. Reset before and after every test in this package."""
    world_services._clock = None
    yield
    world_services._clock = None

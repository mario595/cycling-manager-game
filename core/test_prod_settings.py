"""prod.py reads its tunables from the environment, and never the clock."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest import mock

import pytest

REQUIRED = {
    "DJANGO_SECRET_KEY": "test-secret",
    "POSTGRES_DB": "db",
    "POSTGRES_USER": "user",
    "POSTGRES_PASSWORD": "pw",
}


def load_prod(**env):
    """Import config.settings.prod afresh under exactly this environment."""
    sys.modules.pop("config.settings.prod", None)
    with mock.patch.dict("os.environ", {**REQUIRED, **env}, clear=True):
        with mock.patch("sentry_sdk.init") as sentry_init:
            module = importlib.import_module("config.settings.prod")
    sys.modules.pop("config.settings.prod", None)
    return module, sentry_init


def test_defaults_are_todays_behaviour():
    prod, sentry_init = load_prod()

    assert prod.SECURE_SSL_REDIRECT is True
    assert prod.MEDIA_ROOT == prod.BASE_DIR / "media"
    sentry_init.assert_not_called()


def test_media_root_and_ssl_redirect_can_be_overridden():
    prod, _ = load_prod(DJANGO_MEDIA_ROOT="/data/media", DJANGO_SECURE_SSL_REDIRECT="0")

    assert prod.MEDIA_ROOT == Path("/data/media")
    assert prod.SECURE_SSL_REDIRECT is False


def test_sentry_starts_only_with_a_dsn():
    _, sentry_init = load_prod(SENTRY_DSN="https://key@sentry.example/1")

    sentry_init.assert_called_once()
    assert sentry_init.call_args.kwargs["send_default_pii"] is False


def test_the_clock_is_never_taken_from_the_environment():
    prod, _ = load_prod(GAME_CLOCK_CLASS="world.clocks.MockClock")

    assert prod.GAME_CLOCK_CLASS == "world.clocks.RealClock"


def test_a_missing_secret_still_fails_loudly():
    sys.modules.pop("config.settings.prod", None)
    with mock.patch.dict("os.environ", {}, clear=True):
        with pytest.raises(KeyError):
            importlib.import_module("config.settings.prod")
    sys.modules.pop("config.settings.prod", None)

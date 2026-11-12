"""The staging settings module (#129) is production plus an accelerated
clock and a wipeable world — and production itself stays on the real clock.

Each module is loaded in a fresh interpreter with the env vars `prod.py`
requires. Importing it here instead would re-run `prod.py`'s
`DATABASES["default"].update(...)` on the very dict the running suite is
connected with.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / "config" / "settings"
NAMES = (
    "GAME_CLOCK_CLASS", "GAME_CLOCK_SPEED", "ALLOW_WORLD_RESET",
    "AUTO_DECLARE_SEASONS", "DEBUG", "SESSION_COOKIE_SECURE",
)

PROD_ENV = {
    "DJANGO_SECRET_KEY": "test-only",
    "DJANGO_ALLOWED_HOSTS": "staging.example",
    "POSTGRES_DB": "db",
    "POSTGRES_USER": "user",
    "POSTGRES_PASSWORD": "pw",
}


def _load(name: str, **extra_env: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("GAME_CLOCK_CLASS", "SENTRY_DSN")}
    env.update(PROD_ENV, **extra_env)
    code = (
        "import importlib, json; "
        f"m = importlib.import_module('config.settings.{name}'); "
        f"print(json.dumps({{n: getattr(m, n, None) for n in {NAMES!r}}}))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env,
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def test_staging_is_production_on_the_accelerated_clock():
    staging = _load("staging")
    assert staging["GAME_CLOCK_CLASS"] == "world.clocks.AcceleratedClock"
    assert staging["GAME_CLOCK_SPEED"] == 24
    assert staging["ALLOW_WORLD_RESET"] is True
    assert staging["AUTO_DECLARE_SEASONS"] is True
    assert staging["DEBUG"] is False
    assert staging["SESSION_COOKIE_SECURE"] is True


def test_production_stays_on_the_real_clock_whatever_the_environment():
    prod = _load("prod", GAME_CLOCK_CLASS="world.clocks.AcceleratedClock")
    assert prod["GAME_CLOCK_CLASS"] == "world.clocks.RealClock"
    assert prod["GAME_CLOCK_SPEED"] == 1
    assert prod["ALLOW_WORLD_RESET"] is False
    assert prod["AUTO_DECLARE_SEASONS"] is True


def test_the_accelerated_clock_is_named_only_by_staging():
    assignment = 'GAME_CLOCK_CLASS = "world.clocks.AcceleratedClock"'
    named = [p.name for p in SETTINGS.glob("*.py") if assignment in p.read_text()]
    assert named == ["staging.py"]


@pytest.mark.parametrize("name", ["base", "dev"])
def test_development_does_not_declare_seasons_on_its_own(name):
    assert _load(name)["AUTO_DECLARE_SEASONS"] is False

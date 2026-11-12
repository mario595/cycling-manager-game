"""fly.toml describes the deployed world (#136; deploy/README.md).

A typo here only shows up as a broken deploy, so the few values the machine
cannot run without are checked in CI. No database needed.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLY = tomllib.loads((ROOT / "fly.toml").read_text())


def test_the_settings_module_exists():
    module = FLY["env"]["DJANGO_SETTINGS_MODULE"]
    assert (ROOT / (module.replace(".", "/") + ".py")).is_file(), module


def test_staging_runs_the_accelerated_settings_on_a_five_minute_tick():
    # Milestone 1. #133 switches these to prod, production and hourly.
    env = FLY["env"]
    assert env["DJANGO_SETTINGS_MODULE"] == "config.settings.staging"
    assert env["SENTRY_ENVIRONMENT"] == "staging"
    assert env["TICK_SCHEDULE"] == "*/5 * * * *"


def test_the_tick_schedule_is_a_five_field_cron_expression():
    assert len(FLY["env"]["TICK_SCHEDULE"].split()) == 5


def test_the_allowed_host_is_the_apps_own_address():
    hosts = FLY["env"]["DJANGO_ALLOWED_HOSTS"].split(",")
    assert f"{FLY['app']}.fly.dev" in hosts


def test_the_machine_never_stops():
    # The tick runs inside the machine (world/README.md, "Deployment requirement").
    http = FLY["http_service"]
    assert http["auto_stop_machines"] == "off"
    assert http["min_machines_running"] >= 1


def test_no_secret_is_committed():
    secret = {"DJANGO_SECRET_KEY", "POSTGRES_PASSWORD", "SENTRY_DSN",
              "HEALTHCHECKS_TICK_URL", "BACKUP_S3_SECRET_ACCESS_KEY"}
    assert not secret & set(FLY["env"])

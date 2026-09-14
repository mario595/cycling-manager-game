"""Local development settings.

The database is PostgreSQL, same as production — see `base.py` for why, and
`docker-compose.yml` for the local instance. Start it with `docker compose up -d`
before running migrations or the server.

Override any of `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` /
`POSTGRES_HOST` / `POSTGRES_PORT` in the environment to point at a different
database (a natively installed one, say) without touching this file.
"""

from __future__ import annotations

import os

from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# Vite's dev server, for when the SPA runs standalone with hot reload instead
# of being served from Django's static files.
CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]

# RealClock by default, same as prod, so a normal dev session just shows the
# actual time with no manual resyncing. Switch to the mock clock only for a
# session where you deliberately want to fast-forward a season:
#   GAME_CLOCK_CLASS=world.clocks.MockClock manage.py runserver
# Unlike prod.py, this IS read from the environment — dev is exactly where a
# code path to override it is wanted. See world/README.md, "Which clock runs
# where".
GAME_CLOCK_CLASS = os.environ.get("GAME_CLOCK_CLASS", "world.clocks.RealClock")

# No password strength requirements locally — testing registration
# shouldn't mean fighting CommonPasswordValidator for a throwaway account.
# prod.py never overrides AUTH_PASSWORD_VALIDATORS, so this has no way to
# leak into production; it only ever applies when DJANGO_SETTINGS_MODULE
# points at this file.
AUTH_PASSWORD_VALIDATORS: list[dict] = []

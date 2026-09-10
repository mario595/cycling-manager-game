"""Local development settings.

The database is PostgreSQL, same as production — see `base.py` for why, and
`docker-compose.yml` for the local instance. Start it with `docker compose up -d`
before running migrations or the server.

Override any of `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` /
`POSTGRES_HOST` / `POSTGRES_PORT` in the environment to point at a different
database (a natively installed one, say) without touching this file.
"""

from __future__ import annotations

from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# Vite's dev server, for when the SPA runs standalone with hot reload instead
# of being served from Django's static files.
CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]

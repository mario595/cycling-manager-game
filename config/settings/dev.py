"""Local development settings.

The database is PostgreSQL, same as production — see `base.py` for why, and
`docker-compose.yml` for the local instance. Start it with `docker compose up -d`
before running migrations or the server.

Override any of `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` /
`POSTGRES_HOST` / `POSTGRES_PORT` in the environment to point at a different
database (a natively installed one, say) without touching this file.

Each git worktree gets its own database and its own dev-server port, so
parallel agents do not collide. `scripts/dev_db.py` creates the database;
`config/worktree.py` explains the scheme.
"""

from __future__ import annotations

import os

from config.worktree import database_name, test_database_name

from .base import *  # noqa: F403

# One Postgres, one database per worktree. Several agents work in parallel in
# separate worktrees; without this they share `cycling_manager` and
# `test_cycling_manager`, and drop each other's test database mid-run or apply
# two branches' migrations to one schema. The name comes from the worktree
# directory, so there is nothing to remember and nothing to pass. The main
# checkout keeps the plain names — see `config/worktree.py`.
#
# An explicit POSTGRES_DB still wins, for pointing at a database by hand.
if "POSTGRES_DB" not in os.environ:
    DATABASES["default"]["NAME"] = database_name()  # noqa: F405
DATABASES["default"]["TEST"] = {"NAME": test_database_name()}  # noqa: F405

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# Vite's dev server, for when the SPA runs standalone with hot reload instead
# of being served from Django's static files.
CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]

# frontend/'s dev server proxies /api to Django on a different port, so a
# browser sees the frontend's origin (localhost:5174) on an authenticated
# write, not Django's own. DRF's SessionAuthentication only enforces CSRF
# once a session exists, so an anonymous write (register) never exercised
# this — the first authenticated one (e.g. teams/claim/, racing/squad/) does,
# and Django's origin check 403s without this. Production is unaffected:
# frontend/dist/ is served same-origin there, so no cross-port origin ever
# appears — see frontend/README.md, "How it is served".
CSRF_TRUSTED_ORIGINS = ["http://localhost:5174"]

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

# Django's default hasher (PBKDF2) is deliberately slow — ~1.8s per
# create_user() call — which is correct for production and pointless for
# throwaway test/dev accounts. MD5PasswordHasher is Django's own documented
# recommendation for speeding up tests. Like AUTH_PASSWORD_VALIDATORS above,
# this only applies when DJANGO_SETTINGS_MODULE points at this file — prod.py
# never imports dev.py, so this has no way to reach a real deployment.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

"""Settings shared by every environment.

Environment-specific settings live in `dev.py` and `prod.py`, which both start
by importing everything from here. `DJANGO_SETTINGS_MODULE` picks one of those
two; nothing should point at this file directly.
"""

from __future__ import annotations

import os
from pathlib import Path

# BASE_DIR is the repository root: config/settings/base.py -> up three levels.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")

DEBUG = False
ALLOWED_HOSTS: list[str] = []


# --- Applications ---------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "drf_spectacular",
]

# Game domains. Each is a Django app with its own README.md.
# Apps are added here as features need them — see AGENTS.md for the roadmap
# of domains that are planned but not yet built.
LOCAL_APPS = [
    "core",
    "accounts",
    "riders",
    "teams",
    "transfers",
    "staff",
    "economy",
    "schedule",
    "racing",
    "competitions",
    "world",
    "api",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves the built React bundle and Django's static files
    # without a separate web server. See "Frontend" below.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # The real Vite build takes precedence; the committed placeholder in
        # `templates/` keeps a fresh clone runnable before anyone builds the
        # frontend. See frontend/README.md.
        "DIRS": [
            BASE_DIR / "frontend" / "dist",
            BASE_DIR / "frontend" / "templates",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --- Auth -----------------------------------------------------------------

# Set before the first migration on purpose: swapping the user model after
# migrations exist is painful in Django, and we know we will want extra
# fields on the player account eventually.
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- I18N -----------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# --- Static & media -------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# The built React SPA lands here; WhiteNoise picks it up.
STATICFILES_DIRS = [d for d in [BASE_DIR / "frontend" / "dist"] if d.exists()]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"


# --- Database -------------------------------------------------------------

# PostgreSQL everywhere, development included. Running the same engine locally
# as in production is the point: SQLite quietly differs on JSON querying,
# constraint enforcement and transaction behaviour, and those differences
# surface as bugs that only appear after deploy.
#
# `docker compose up -d` starts a local Postgres matching these defaults.
# Production overrides them with real credentials from the environment.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "cycling_manager"),
        "USER": os.environ.get("POSTGRES_USER", "cycling"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "cycling"),
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "5433"),
        "CONN_MAX_AGE": 600,
    }
}

# Race logs are written through Django's storage API (never with raw open()),
# so moving them off the local disk to object storage is a settings change
# rather than a code change. See racing/README.md.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Subdirectory of the default storage where race logs are kept.
RACE_LOG_STORAGE_PREFIX = "race_logs"


# --- Game clock -------------------------------------------------------------

# Which world.clocks.Clock the game runs on. Defaults to RealClock here so
# that inheriting base.py without an override (as prod.py does) is safe by
# construction. dev.py overrides this to MockClock. Deliberately NOT read
# from the environment the way POSTGRES_* is — see world/README.md, "Which
# clock runs where": a non-real clock must never be a live-game possibility,
# and an env var is a code path that could put one there by accident.
GAME_CLOCK_CLASS = "world.clocks.RealClock"


# --- DRF ------------------------------------------------------------------

REST_FRAMEWORK = {
    # Session first, token second — order is load-bearing. DRF takes the
    # 401-vs-403 choice from the first class, so an anonymous request stays a
    # 403 as before; and SessionAuthentication only enforces CSRF when it is
    # the class that authenticated, so a token request carrying no session
    # cookie needs no CSRF token. See api/README.md, Authentication (#130).
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "api.authentication.GameTokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # Only token requests are counted (api/throttling.py).
    "DEFAULT_THROTTLE_CLASSES": [
        "api.throttling.TokenRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "token": "60/min",
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# The OpenAPI schema (/api/schema/) and its docs page (/api/docs/), for LLM
# managers and anyone else playing through the API (#130). DESCRIPTION holds
# the conventions every endpoint shares, so each endpoint's own description
# only has to say what the action does in the game. See api/README.md,
# Schema and docs.
SPECTACULAR_SETTINGS = {
    "TITLE": "Cycling Manager API",
    "VERSION": "1",
    "DESCRIPTION": """
You manage one professional cycling team in a shared, persistent world. This
API is the same one the game's own web app uses: every action a manager can
take in the browser is here, under exactly the same rules, and nothing else.

**Authentication.** Send `Authorization: Bearer <token>` on every request. A
token belongs to one account and is issued by the game's operator. A missing,
wrong or revoked token gets a `403` with a JSON `detail`. Writes made with a
token need no CSRF token and no cookie. **Do not send cookies with a token
request:** a request that carries a session cookie (registering or logging in
sets one) is treated as a browser request and needs a CSRF token, so its
writes fail with a `403` even though the token is valid.

**Your team.** Endpoints never take a team id: "your team" is always the team
the token's account manages. An account that manages no team gets a `403`
from team endpoints and can claim one (`POST /api/teams/claim/`).

**Rate limit.** 60 requests a minute per account. Past that you get a `429`
with a `Retry-After` header saying how many seconds to wait.

**Money** is a whole number of the game's currency (shown to players with a
`$` prefix). Never a decimal.

**Rider attributes** (`climb`, `sprint`, `flat`, `resistance`,
`positioning`) and **freshness** are on a 0–10 display scale, higher is
better. A rider's hidden traits, such as potential, are never shown.

**Game time.** The world runs on a game clock (`GET /api/world/clock/`). A
season is twelve weeks with races on fixed days; weekly things (wages,
training, youth intake, sponsorship payments) happen at each week boundary,
and auctions resolve as their deadlines pass. Timestamps are ISO 8601 UTC in
game time.

**Errors.** A `400` means the request was malformed or broke a game rule, a
`403` that you may not do it (not logged in, no team), a `404` that the thing
does not exist, and a `409` that the world's current state refuses it. Each
carries a human-readable `detail` (or per-field messages for a `400`). Every
path ends with a slash; an unknown path gets a JSON `404`.
""".strip(),
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
    "COMPONENT_SPLIT_REQUEST": True,
}


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Whether `seed_world --reset` may wipe the game world (world/world_setup.py,
# wipe_world). Off here and so in production, which never turns it on; dev.py
# turns it on, and the staging settings (#129) must turn it on explicitly.
ALLOW_WORLD_RESET = False

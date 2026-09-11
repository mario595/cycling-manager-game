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
]

# Game domains. Each is a Django app with its own README.md.
# Apps are added here as features need them — see AGENTS.md for the roadmap
# of domains that are planned but not yet built.
LOCAL_APPS = [
    "core",
    "accounts",
    "riders",
    "teams",
    "racing",
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


# --- DRF ------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

"""Production settings.

Everything that differs from development is read from the environment, so the
same image runs anywhere. Nothing secret is committed.
"""

from __future__ import annotations

import os

from .base import *  # noqa: F403

DEBUG = False

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h]

# `base.py` already configures PostgreSQL, but with development-friendly
# defaults. Here the credentials are mandatory: reading them with [] rather
# than .get() means a missing variable fails loudly at startup instead of
# silently falling back to the well-known local password.
DATABASES["default"].update(  # noqa: F405
    {
        "NAME": os.environ["POSTGRES_DB"],
        "USER": os.environ["POSTGRES_USER"],
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
)

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# When race logs outgrow the local disk, swap STORAGES["default"] here for an
# S3-compatible backend (Cloudflare R2 is the frugal pick: 10GB free, no
# egress fees) via django-storages. No application code changes.

# The tick declares the next season of the world calendar by itself once only
# one declared season is left to play, so a running world never runs out of
# calendar (#129; world/README.md, *Automatic seasons*). Staging inherits it.
AUTO_DECLARE_SEASONS = True

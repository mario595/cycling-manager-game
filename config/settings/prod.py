"""Production settings.

Everything that differs from development is read from the environment, so the
same image runs anywhere. Nothing secret is committed.
"""

from __future__ import annotations

import os
from pathlib import Path

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

# On by default. Only the local run of the production image
# (deploy/compose.local.yml) turns it off, because nothing terminates TLS in
# front of it there. On Fly, TLS ends at Fly's proxy, which sets
# X-Forwarded-Proto (SECURE_PROXY_SSL_HEADER below).
SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "1") != "0"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Race logs live under MEDIA_ROOT. On Fly that is the persistent volume,
# /data/media (fly.toml); the default keeps a plain checkout working.
MEDIA_ROOT = Path(os.environ.get("DJANGO_MEDIA_ROOT", str(MEDIA_ROOT)))  # noqa: F405

# Error reporting (deploy/README.md, "Monitoring"). Off unless a DSN is set,
# so the image runs anywhere without a Sentry account.
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        send_default_pii=False,
        traces_sample_rate=0.0,
    )

# When race logs outgrow the local disk, swap STORAGES["default"] here for an
# S3-compatible backend (Cloudflare R2 is the frugal pick: 10GB free, no
# egress fees) via django-storages. No application code changes.

# The tick declares the next season of the world calendar by itself once only
# one declared season is left to play, so a running world never runs out of
# calendar (#129; world/README.md, *Automatic seasons*). Staging inherits it.
AUTO_DECLARE_SEASONS = True

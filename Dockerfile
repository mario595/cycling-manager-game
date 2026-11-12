# syntax=docker/dockerfile:1
#
# The production image. Three stages (see deploy/README.md):
#
#   frontend  builds the React SPA (and the race_player sources it imports)
#   web       the standard Django image: gunicorn + WhiteNoise, no database
#   allinone  web + PostgreSQL + the tick scheduler on one machine (fly.toml)
#
# Moving the database to its own machine later means deploying `web`
# instead of `allinone`; nothing in `web` knows Postgres is local.

# --- frontend ---------------------------------------------------------------
FROM node:20-slim AS frontend
WORKDIR /src
# frontend/ imports race_player/src directly, so tsc needs race_player's own
# node_modules on disk (the same reason CI installs both).
COPY race_player/package.json race_player/package-lock.json race_player/
RUN cd race_player && npm ci
COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci
COPY race_player/ race_player/
COPY frontend/ frontend/
RUN cd frontend && npm run build

# --- web ----------------------------------------------------------------------
# The Debian release is pinned too (trixie), because the all-in-one stage's
# Postgres major version comes from it: see below.
FROM python:3.12.11-slim-trixie AS web
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod
WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
    && chown app:app /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=app:app . .
COPY --chown=app:app --from=frontend /src/frontend/dist frontend/dist

USER app
# collectstatic needs settings but no database or secrets: base.py has
# development defaults for both, and nothing here connects.
RUN DJANGO_SETTINGS_MODULE=config.settings.base python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["gunicorn", "config.wsgi", "--config", "deploy/gunicorn.conf.py"]

# --- allinone -----------------------------------------------------------------
FROM web AS allinone
USER root

# PostgreSQL's MAJOR VERSION IS PINNED. The data directory on the volume is
# only readable by the major that wrote it, so a silent bump would stop the
# live world from booting. Changing PG_MAJOR is a migration: dump with the old
# image, restore with the new (deploy/README.md, "Upgrading Postgres"). Trixie
# ships 17; a base image on another Debian release fails this install loudly.
# Dumps are taken and restored with these same binaries, locally too, so the
# dev/CI Postgres 16 never has to read one. curl fetches supercronic below.
ARG PG_MAJOR=17
RUN apt-get update \
    && apt-get install -y --no-install-recommends "postgresql-${PG_MAJOR}" curl \
    && rm -rf /var/lib/apt/lists/*

# This Postgres's own tools (pg_dump, pg_restore, ...) first on PATH, for the
# backup and restore scripts and the entrypoint.
RUN ln -s "/usr/lib/postgresql/${PG_MAJOR}/bin" /usr/local/pgbin \
    && test -x /usr/local/pgbin/postgres
ENV PATH=/usr/local/pgbin:$PATH \
    PG_MAJOR=${PG_MAJOR}

# supercronic: cron for containers. It never overlaps two runs of the same
# job and reports failed jobs to Sentry. Pinned by version and checksum.
ARG SUPERCRONIC_VERSION=v0.2.38
ARG TARGETARCH
RUN set -eu; \
    case "${TARGETARCH:-amd64}" in \
      amd64) sum=231b2af8bcd526c129549920fa870ec2e00e85874ed0ae03fff26306ca1c8e31 ;; \
      arm64) sum=5df56e7402254890757365c3acdae361c9f309cbab4ca57fa4b8be06e0505bbd ;; \
      *) echo "unsupported arch ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /usr/local/bin/supercronic \
      "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${TARGETARCH:-amd64}"; \
    echo "${sum}  /usr/local/bin/supercronic" | sha256sum -c -; \
    chmod +x /usr/local/bin/supercronic

ENV DATA_DIR=/data \
    PGDATA=/data/postgres \
    DJANGO_MEDIA_ROOT=/data/media \
    POSTGRES_HOST=127.0.0.1 \
    POSTGRES_PORT=5432

# The entrypoint starts as root (to own the volume and start Postgres as
# `postgres`), then runs the app and the scheduler as `app`.
ENTRYPOINT ["/app/deploy/entrypoint-allinone.sh"]
CMD []

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
FROM python:3.12.11-slim AS web
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod
WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
COPY --from=frontend /src/frontend/dist frontend/dist

# collectstatic needs settings but no database or secrets: base.py has
# development defaults for both, and nothing here connects.
RUN DJANGO_SETTINGS_MODULE=config.settings.base python manage.py collectstatic --noinput \
    && chown -R app:app /app

USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi", "--config", "deploy/gunicorn.conf.py"]

# --- allinone -----------------------------------------------------------------
FROM web AS allinone
USER root

# Debian's own PostgreSQL (17 on trixie). Dumps are taken and restored with
# these same binaries, locally too, so the dev/CI Postgres 16 never has to
# read one. curl fetches supercronic below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql curl \
    && rm -rf /var/lib/apt/lists/*

# Put this Postgres's own tools (pg_dump, pg_restore, ...) first on PATH,
# whatever its major version, for the backup and restore scripts.
RUN ln -s "$(ls -d /usr/lib/postgresql/*/bin | sort -V | tail -1)" /usr/local/pgbin
ENV PATH=/usr/local/pgbin:$PATH

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

#!/bin/bash
# The all-in-one machine's supervisor (deploy/README.md, "What runs where").
#
# 1. Own the volume, and initialise the database cluster on first boot.
# 2. Start PostgreSQL (localhost only) and wait for it.
# 3. Migrate. This is here rather than in Fly's release_command, which runs on
#    a throwaway machine that cannot see a database living on this volume.
# 4. Start the scheduler and gunicorn as the unprivileged `app` user.
# 5. Wait for the first of the three to exit, stop the rest, and exit with
#    its status, so Fly restarts the whole machine rather than leaving it
#    half-alive.
#
# With arguments it runs them as `app` once Postgres is up and migrated
# instead of the services, e.g. a one-off `manage.py seed_world` locally.
set -euo pipefail

: "${POSTGRES_DB:?}" "${POSTGRES_USER:?}" "${POSTGRES_PASSWORD:?}"

PGBIN=/usr/local/pgbin  # the image links its Postgres version here (Dockerfile)
as_postgres() { HOME=/var/lib/postgresql setpriv --reuid=postgres --regid=postgres --init-groups "$@"; }
as_app() { HOME=/app setpriv --reuid=app --regid=app --init-groups "$@"; }
log() { echo "[entrypoint] $*"; }

mkdir -p "$DATA_DIR" "$PGDATA" "$DJANGO_MEDIA_ROOT" /run/postgresql
chown postgres:postgres "$PGDATA" /run/postgresql
chmod 700 "$PGDATA"
chown app:app "$DJANGO_MEDIA_ROOT"

if [ ! -s "$PGDATA/PG_VERSION" ]; then
    log "first boot: initialising the database cluster in $PGDATA"
    pwfile=$(mktemp)
    printf '%s' "$POSTGRES_PASSWORD" > "$pwfile"
    chown postgres "$pwfile"
    as_postgres "$PGBIN/initdb" -D "$PGDATA" -U "$POSTGRES_USER" \
        --pwfile="$pwfile" --auth=scram-sha-256 --encoding=UTF8 --locale=C.UTF-8
    rm -f "$pwfile"
    # Small on purpose: the whole machine has 512 MB (deploy/README.md).
    cat >> "$PGDATA/postgresql.conf" <<CONF

# --- cycling-manager all-in-one (deploy/entrypoint-allinone.sh) ---
listen_addresses = '127.0.0.1'
max_connections = 20
shared_buffers = 64MB
work_mem = 4MB
maintenance_work_mem = 32MB
effective_cache_size = 192MB
CONF
    fresh_cluster=1
fi

log "starting PostgreSQL"
as_postgres "$PGBIN/postgres" -D "$PGDATA" &
pg_pid=$!

for _ in $(seq 1 60); do
    if as_postgres "$PGBIN/pg_isready" -q -h 127.0.0.1 -p "$POSTGRES_PORT"; then break; fi
    kill -0 "$pg_pid" 2>/dev/null || { log "PostgreSQL exited during startup"; exit 1; }
    sleep 1
done

if [ "${fresh_cluster:-0}" = 1 ]; then
    log "creating database $POSTGRES_DB"
    PGPASSWORD="$POSTGRES_PASSWORD" as_postgres "$PGBIN/createdb" \
        -h 127.0.0.1 -p "$POSTGRES_PORT" -U "$POSTGRES_USER" "$POSTGRES_DB"
fi

log "migrating"
as_app python manage.py migrate --noinput

if [ "$#" -gt 0 ]; then
    log "running one-off command: $*"
    status=0
    as_app "$@" || status=$?
    as_postgres "$PGBIN/pg_ctl" -D "$PGDATA" -m fast -w stop >/dev/null
    exit "$status"
fi

sentry_flag=()
[ -n "${SENTRY_DSN:-}" ] && sentry_flag=(-sentry-dsn "$SENTRY_DSN")

log "starting the scheduler"
as_app /usr/local/bin/supercronic -passthrough-logs "${sentry_flag[@]}" /app/deploy/crontab &
cron_pid=$!

log "starting gunicorn"
as_app gunicorn config.wsgi --config deploy/gunicorn.conf.py &
web_pid=$!

shutdown() {
    log "stopping"
    kill -TERM "$web_pid" "$cron_pid" 2>/dev/null || true
    wait "$web_pid" "$cron_pid" 2>/dev/null || true
    as_postgres "$PGBIN/pg_ctl" -D "$PGDATA" -m fast -w stop >/dev/null 2>&1 || true
}
trap 'shutdown; exit 0' TERM INT

status=0
wait -n "$pg_pid" "$cron_pid" "$web_pid" || status=$?
log "a service exited (status $status); shutting the machine down"
shutdown
exit "$status"

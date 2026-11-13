#!/bin/sh
# Run the tick; on success, ping healthchecks.io so a stopped tick is noticed.
# A failed tick exits non-zero, which supercronic reports to Sentry, and sends
# no ping, which healthchecks.io notices after its grace period.
set -eu
# A stop sends SIGTERM to the tick as well as to supercronic (#136: seen on
# Fly, where the tick died within a second of "[entrypoint] stopping"). Ignore
# it, so the tick gets the entrypoint's STOP_GRACE (90 s) to finish, as
# deploy/README.md promises. An ignored signal stays ignored in the python
# child. A tick still running after the grace is SIGKILLed, and the next tick
# picks its race up again (world/README.md).
trap '' TERM
cd /app
python manage.py tick
if [ -n "${HEALTHCHECKS_TICK_URL:-}" ]; then
    python -c 'import os, urllib.request; urllib.request.urlopen(os.environ["HEALTHCHECKS_TICK_URL"], timeout=10)' \
        || echo "tick ok, but the healthchecks.io ping failed" >&2
fi

#!/bin/sh
# Run the tick; on success, ping healthchecks.io so a stopped tick is noticed.
# A failed tick exits non-zero, which supercronic reports to Sentry, and sends
# no ping, which healthchecks.io notices after its grace period.
set -eu
cd /app
python manage.py tick
if [ -n "${HEALTHCHECKS_TICK_URL:-}" ]; then
    python -c 'import os, urllib.request; urllib.request.urlopen(os.environ["HEALTHCHECKS_TICK_URL"], timeout=10)' \
        || echo "tick ok, but the healthchecks.io ping failed" >&2
fi

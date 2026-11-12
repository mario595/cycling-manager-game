#!/bin/sh
# Run the tick; on success, ping healthchecks.io so a stopped tick is noticed.
# A failed tick exits non-zero, which supercronic reports to Sentry, and sends
# no ping, which healthchecks.io notices after its grace period.
#
# TICK_ADVANCE_BY (e.g. "2h"), when set, first moves the mock clock forward by
# that much: the accelerated world (#129). `mock_clock` refuses to run unless
# the settings module configures MockClock, so on the real clock a stray
# TICK_ADVANCE_BY fails the job loudly rather than bending time.
set -eu
cd /app
if [ -n "${TICK_ADVANCE_BY:-}" ]; then
    python manage.py mock_clock advance --by "$TICK_ADVANCE_BY"
fi
python manage.py tick
if [ -n "${HEALTHCHECKS_TICK_URL:-}" ]; then
    python -c 'import os, urllib.request; urllib.request.urlopen(os.environ["HEALTHCHECKS_TICK_URL"], timeout=10)' \
        || echo "tick ok, but the healthchecks.io ping failed" >&2
fi

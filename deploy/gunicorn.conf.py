"""gunicorn settings for the production image (deploy/README.md).

Two sync workers fit the 512 MB machine with room for Postgres and a
race-simulating tick (about 95 MB for both workers, measured). WEB_CONCURRENCY
overrides the count.
"""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
timeout = 60
# Recycle workers now and then, so a slow leak can never grow into an
# out-of-memory kill of the whole machine.
max_requests = 1000
max_requests_jitter = 100
accesslog = "-"
errorlog = "-"
forwarded_allow_ips = "*"

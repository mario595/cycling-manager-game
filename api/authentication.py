"""The API token authenticator the settings actually use (#130).

Subclasses `accounts.authentication.ApiTokenAuthentication` only to stamp
the manager's game-time `last_seen_at`, so a token-only agent counts as seen
by the inactivity rule exactly as a human who logs in does
(world/README.md, inactivity; accounts/README.md, Last seen is game time).
"""

from __future__ import annotations

from datetime import timedelta

from accounts.authentication import ApiTokenAuthentication
from api.services import touch_last_seen
from world.services import now

# Inactivity is counted in weeks, so stamping at most once per game hour
# loses nothing and keeps an UPDATE off nearly every request.
LAST_SEEN_RESOLUTION = timedelta(hours=1)


class GameTokenAuthentication(ApiTokenAuthentication):
    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        at = now()
        # abs(): MockClock can be set backwards in dev; a stamp from the
        # "future" must still be replaced, as a login would replace it.
        if user.last_seen_at is None or abs(at - user.last_seen_at) >= LAST_SEEN_RESOLUTION:
            touch_last_seen(user, at)
        return user, token

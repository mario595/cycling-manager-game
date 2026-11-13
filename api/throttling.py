"""Rate limiting for API-token requests only (#130).

Counted per user (UserRateThrottle's cache key), so reissuing a token does
not reset the count. Browser sessions are never throttled. The count lives
in the default cache, which is per-process LocMemCache: with N workers the
real ceiling is N times the rate. See api/README.md, Authentication.
"""

from __future__ import annotations

from rest_framework.throttling import UserRateThrottle

from accounts.models import ApiToken


class TokenRateThrottle(UserRateThrottle):
    scope = "token"

    def allow_request(self, request, view):
        if not isinstance(request.auth, ApiToken):
            return True
        return super().allow_request(request, view)

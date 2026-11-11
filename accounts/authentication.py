"""API token authentication (#130).

`Authorization: Bearer <key>`. This class only resolves the key to a user;
stamping game-time last-seen needs `world.services.now()`, which `accounts/`
may not import, so `api.authentication.GameTokenAuthentication` subclasses
this and does it there — the same split as the login view. See
accounts/README.md, API tokens.
"""

from __future__ import annotations

from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed

from accounts.tokens import user_for_key


class ApiTokenAuthentication(TokenAuthentication):
    keyword = "Bearer"

    def authenticate_credentials(self, key):
        found = user_for_key(key)
        if found is None:
            raise AuthenticationFailed("Invalid token.")
        return found

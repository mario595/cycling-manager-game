"""Issuing, revoking and resolving API tokens (#130).

The raw key exists in clear only in `issue_token`'s return value. Everything
else works on its hash. See accounts/README.md, API tokens.
"""

from __future__ import annotations

import hashlib
import secrets

from django.db import transaction

from accounts.models import ApiToken, User

TOKEN_PREFIX = "cm_"
PREFIX_LENGTH = 8


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def issue_token(user: User) -> str:
    """Replace any token the user has and return the new raw key.

    Delete-then-create in one transaction, so the old key stops working the
    moment the new one exists — one token per account is the rule.
    """
    key = TOKEN_PREFIX + secrets.token_urlsafe(32)
    with transaction.atomic():
        ApiToken.objects.filter(user=user).delete()
        ApiToken.objects.create(
            user=user,
            key_hash=hash_key(key),
            prefix=key[len(TOKEN_PREFIX):len(TOKEN_PREFIX) + PREFIX_LENGTH],
        )
    return key


def revoke_token(user: User) -> bool:
    """Delete the user's token. True if there was one to delete."""
    deleted, _ = ApiToken.objects.filter(user=user).delete()
    return deleted > 0


def user_for_key(key: str) -> tuple[User, ApiToken] | None:
    """The active user a raw key belongs to, with its token row, or None."""
    token = ApiToken.objects.select_related("user").filter(key_hash=hash_key(key)).first()
    if token is None or not token.user.is_active:
        return None
    return token.user, token

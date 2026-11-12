from __future__ import annotations

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.text import slugify


class UserManager(BaseUserManager):
    """Creates users keyed on email. `username` is still a required, unique
    column inherited from AbstractUser, so it is derived rather than asked
    for — see specs/player-accounts-plan.md, D1."""

    use_in_migrations = True

    def _derive_username(self, email: str) -> str:
        base = slugify(email.split("@")[0])[:30] or "player"
        candidate = base
        suffix = 1
        while self.model.objects.filter(username=candidate).exists():
            suffix += 1
            candidate = f"{base}{suffix}"
        return candidate

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email)
        extra.setdefault("username", self._derive_username(email))
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra)


class User(AbstractUser):
    """A player account.

    It exists from the first migration because swapping `AUTH_USER_MODEL`
    after migrations have been applied is painful in Django, and we know
    player-specific fields are coming.

    A user manages at most one team per game world; that link lives on
    `teams.Team.manager`, not here, so the team side owns the relationship.

    Login is by email, not username: `username` stays on the model (dropping
    it would mean rewriting onto `AbstractBaseUser`, more than this needed)
    but is derived from the email at creation time rather than chosen by the
    player. See specs/player-accounts-plan.md, D1.
    """

    email = models.EmailField(unique=True)

    display_name = models.CharField(
        max_length=50,
        blank=True,
        help_text="Public name shown to other managers. Falls back to username.",
    )

    last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Game time of the user's most recent login — NOT django.contrib.auth's "
            "last_login, which is real time. Null means never logged in. Written "
            "only by api.services.touch_last_seen; see world/README.md, The clock "
            "discipline rule, and accounts/README.md, Last seen is game time."
        ),
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    def __str__(self) -> str:
        return self.display_name or self.username


class ApiToken(models.Model):
    """A user's one API token, for playing through the API without a browser
    session (#130). Only a SHA-256 of the key is stored, so a token cannot be
    read back out of the database: it is shown once, at issue, and lost after
    that. Plain SHA-256 rather than a slow password hash is deliberate — the key
    is 32 random bytes, so there is nothing to brute-force, and a slow hash
    would tax every request. See accounts/README.md, API tokens.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="api_token")
    key_hash = models.CharField(max_length=64, unique=True)
    prefix = models.CharField(
        max_length=8,
        help_text="First characters of the key after cm_, so a token can be recognised but not rebuilt.",
    )
    # Real time, not game time: this is operator metadata, not game state.
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.user.email} cm_{self.prefix}…"

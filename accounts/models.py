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

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    def __str__(self) -> str:
        return self.display_name or self.username

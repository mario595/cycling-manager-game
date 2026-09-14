from __future__ import annotations

import pytest
from django.db import IntegrityError

from accounts.models import User


def test_create_user_derives_a_username_from_the_email(db):
    # normalize_email lowercases only the domain (RFC 5321: the local part is
    # case-sensitive), so "Mario" survives — username derivation lowercases
    # it separately via slugify.
    user = User.objects.create_user(email="Mario@Example.com", password="s0meth1ng-good")

    assert user.email == "Mario@example.com"
    assert user.username == "mario"


def test_create_user_rejects_a_duplicate_email(db):
    User.objects.create_user(email="mario@example.com", password="s0meth1ng-good")

    with pytest.raises(IntegrityError):
        User.objects.create_user(email="mario@example.com", password="s0meth1ng-else")


def test_derived_usernames_do_not_collide(db):
    first = User.objects.create_user(email="mario@a.com", password="s0meth1ng-good")
    second = User.objects.create_user(email="mario@b.com", password="s0meth1ng-good")

    assert first.username == "mario"
    assert second.username == "mario2"


def test_create_superuser_is_staff_and_superuser(db):
    user = User.objects.create_superuser(email="admin@example.com", password="s0meth1ng-good")

    assert user.is_staff
    assert user.is_superuser

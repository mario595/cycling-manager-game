from __future__ import annotations

import pytest
from django.db import IntegrityError
from django.test import override_settings
from rest_framework.test import APIClient

from accounts.models import User
from accounts.serializers import RegisterSerializer

# dev.py turns password strength checking off (registering a throwaway local
# account shouldn't mean fighting CommonPasswordValidator), so this test
# forces the real, base.py validators back on rather than relying on
# whatever DJANGO_SETTINGS_MODULE the test run happens to use.
STRICT_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


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


@override_settings(AUTH_PASSWORD_VALIDATORS=STRICT_PASSWORD_VALIDATORS)
def test_register_serializer_rejects_a_weak_password(db):
    serializer = RegisterSerializer(data={
        "email": "mario@example.com",
        "password": "password",
        "display_name": "Mario",
    })

    assert not serializer.is_valid()
    assert "password" in serializer.errors


def test_register_serializer_rejects_a_duplicate_email_case_insensitively(db):
    User.objects.create_user(email="mario@example.com", password="s0meth1ng-good")

    serializer = RegisterSerializer(data={
        "email": "Mario@Example.com",
        "password": "s0meth1ng-else",
        "display_name": "Mario Two",
    })

    assert not serializer.is_valid()
    assert "email" in serializer.errors


def test_register_creates_a_user_and_logs_them_in(db):
    client = APIClient()

    response = client.post("/api/accounts/register/", {
        "email": "mario@example.com",
        "password": "s0meth1ng-good",
        "display_name": "Mario",
    }, format="json")

    assert response.status_code == 201
    assert User.objects.filter(email="mario@example.com").exists()
    assert "_auth_user_id" in client.session


def test_login_succeeds_with_correct_credentials(db):
    User.objects.create_user(email="mario@example.com", password="s0meth1ng-good", display_name="Mario")
    client = APIClient()

    response = client.post("/api/accounts/login/", {
        "email": "mario@example.com",
        "password": "s0meth1ng-good",
    }, format="json")

    assert response.status_code == 200
    assert response.data["display_name"] == "Mario"
    assert "_auth_user_id" in client.session


def test_login_fails_identically_for_unknown_email_and_wrong_password(db):
    User.objects.create_user(email="mario@example.com", password="s0meth1ng-good")

    unknown_email = APIClient().post("/api/accounts/login/", {
        "email": "nobody@example.com",
        "password": "whatever-1",
    }, format="json")
    wrong_password = APIClient().post("/api/accounts/login/", {
        "email": "mario@example.com",
        "password": "wrong-password-1",
    }, format="json")

    assert unknown_email.status_code == wrong_password.status_code == 400
    assert unknown_email.data == wrong_password.data


def test_logout_ends_the_session(db):
    User.objects.create_user(email="mario@example.com", password="s0meth1ng-good")
    client = APIClient()
    client.post("/api/accounts/login/", {
        "email": "mario@example.com",
        "password": "s0meth1ng-good",
    }, format="json")

    response = client.post("/api/accounts/logout/")

    assert response.status_code == 204
    assert "_auth_user_id" not in client.session

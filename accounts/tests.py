from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.db import IntegrityError
from django.test import override_settings
from rest_framework.test import APIClient

from accounts.models import ApiToken, User
from accounts.serializers import RegisterSerializer
from accounts.tokens import hash_key, issue_token, revoke_token, user_for_key

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


def test_last_seen_at_defaults_to_null(db):
    user = User.objects.create_user(email="mario@example.com", password="s0meth1ng-good")

    assert user.last_seen_at is None


# --- API tokens (#130) ------------------------------------------------------


@pytest.fixture
def player(db):
    return User.objects.create_user(email="agent@example.com", password="s0meth1ng-good")


def test_issue_token_stores_only_a_hash(player):
    key = issue_token(player)

    token = ApiToken.objects.get(user=player)
    assert key.startswith("cm_")
    assert token.key_hash == hash_key(key)
    assert key not in (token.key_hash, token.prefix)
    assert key[3:].startswith(token.prefix)
    assert user_for_key(key) == (player, token)


def test_reissuing_replaces_the_old_token(player):
    old = issue_token(player)
    new = issue_token(player)

    assert ApiToken.objects.filter(user=player).count() == 1
    assert user_for_key(old) is None
    assert user_for_key(new)[0] == player


def test_revoke_removes_the_token(player):
    key = issue_token(player)

    assert revoke_token(player) is True
    assert user_for_key(key) is None
    assert revoke_token(player) is False


def test_an_inactive_users_key_resolves_to_nobody(player):
    key = issue_token(player)
    player.is_active = False
    player.save()

    assert user_for_key(key) is None


def test_unknown_key_resolves_to_nobody(db):
    assert user_for_key("cm_nope") is None


def test_issue_command_prints_the_key_once(player):
    out = StringIO()
    call_command("issue_api_token", "AGENT@example.com", stdout=out, stderr=StringIO())

    key = out.getvalue().strip()
    assert user_for_key(key)[0] == player


def test_revoke_command(player):
    key = issue_token(player)
    out = StringIO()
    call_command("revoke_api_token", "agent@example.com", stdout=out)

    assert "revoked" in out.getvalue()
    assert user_for_key(key) is None


@pytest.mark.parametrize("command", ["issue_api_token", "revoke_api_token"])
def test_token_commands_reject_an_unknown_email(db, command):
    with pytest.raises(CommandError):
        call_command(command, "nobody@example.com", stdout=StringIO(), stderr=StringIO())

"""Tests for the shared, non-domain pieces: the /healthz check (config/health.py)."""

from __future__ import annotations

from unittest import mock

import pytest
from django.db import OperationalError


@pytest.mark.django_db
def test_healthz_is_ok_with_a_working_database(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.content == b"ok"


@pytest.mark.django_db
def test_healthz_is_503_when_the_database_is_down(client):
    with mock.patch("config.health.connection") as connection:
        connection.cursor.side_effect = OperationalError("connection refused")
        response = client.get("/healthz")

    assert response.status_code == 503


@pytest.mark.django_db
def test_healthz_ignores_allowed_hosts(client, settings):
    settings.ALLOWED_HOSTS = ["game.example"]

    response = client.get("/healthz", HTTP_HOST="172.19.0.2:8000")

    assert response.status_code == 200


@pytest.mark.django_db
def test_healthz_is_not_redirected_to_https(client, settings):
    settings.SECURE_SSL_REDIRECT = True

    response = client.get("/healthz")

    assert response.status_code == 200


@pytest.mark.django_db
def test_other_paths_still_go_through_the_stack(client, settings):
    settings.SECURE_SSL_REDIRECT = True

    response = client.get("/api/")

    assert response.status_code == 301

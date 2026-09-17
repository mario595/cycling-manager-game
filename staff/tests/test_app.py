from __future__ import annotations

from django.apps import apps


def test_staff_app_is_installed():
    assert apps.is_installed("staff")

"""The field's current pay level (#166): one read, shared by every caller
that prices a rider in a live world. See riders.models.FieldLevel."""

from __future__ import annotations

from .models import FieldLevel


def current_field_factor() -> float:
    """The newest measured field factor, or 1.0 before any season close."""
    latest = FieldLevel.objects.order_by("-pk").values_list("factor", flat=True).first()
    return 1.0 if latest is None else latest

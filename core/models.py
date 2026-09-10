from __future__ import annotations

from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base adding wall-clock creation/update stamps.

    Note these are *real* timestamps, not in-game dates. Game time is a
    separate concept that will live in `world/` when that app exists; never
    infer an in-game date from `created_at`.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

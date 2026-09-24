from __future__ import annotations

import importlib

from django.apps import apps

from riders.models import RiderAttributeSnapshot

_migration = importlib.import_module(
    "riders.migrations.0010_backfill_rider_attribute_snapshots"
)
backfill_baseline_snapshots = _migration.backfill_baseline_snapshots


def test_backfill_gives_every_rider_a_baseline_snapshot(db, rider):
    backfill_baseline_snapshots(apps, None)

    snapshot = RiderAttributeSnapshot.objects.get(rider=rider, week=None)
    assert snapshot.climb == rider.climb // 10


def test_backfill_is_idempotent(db, rider):
    backfill_baseline_snapshots(apps, None)
    backfill_baseline_snapshots(apps, None)

    assert RiderAttributeSnapshot.objects.filter(rider=rider, week=None).count() == 1


def test_backfill_skips_a_rider_that_already_has_a_baseline(db, rider):
    RiderAttributeSnapshot.objects.create(
        rider=rider, week=None, climb=1, sprint=1, flat=1, resistance=1, positioning=1,
    )

    backfill_baseline_snapshots(apps, None)

    snapshot = RiderAttributeSnapshot.objects.get(rider=rider, week=None)
    assert snapshot.climb == 1  # untouched, not overwritten by the backfill

# Generated for #95 — see specs/archive/rider-attribute-history-plan.md, W5.

from django.db import migrations

_BATCH_SIZE = 500
_ATTRIBUTES = ("climb", "sprint", "flat", "resistance", "positioning")


def backfill_baseline_snapshots(apps, schema_editor):
    """Every rider that existed before this feature shipped gets a baseline
    (week=None) snapshot at their current displayed values, so their graph
    does not start empty. Guarded against re-running: a rider that already
    has a baseline is skipped. Imported inside the function, not at module
    scope: to_display_scale reads only a plain int, so it works unchanged
    against a historical Rider from apps.get_model()."""
    from riders.display import to_display_scale

    Rider = apps.get_model("riders", "Rider")
    RiderAttributeSnapshot = apps.get_model("riders", "RiderAttributeSnapshot")

    already_snapshotted = set(
        RiderAttributeSnapshot.objects.filter(week=None).values_list("rider_id", flat=True)
    )
    riders = Rider.objects.exclude(pk__in=already_snapshotted)

    rows = [
        RiderAttributeSnapshot(
            rider=rider,
            week=None,
            **{name: to_display_scale(getattr(rider, name)) for name in _ATTRIBUTES},
        )
        for rider in riders
    ]
    RiderAttributeSnapshot.objects.bulk_create(rows, batch_size=_BATCH_SIZE)


def remove_baseline_snapshots(apps, schema_editor):
    RiderAttributeSnapshot = apps.get_model("riders", "RiderAttributeSnapshot")
    RiderAttributeSnapshot.objects.filter(week=None).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('riders', '0009_riderattributesnapshot'),
    ]

    operations = [
        migrations.RunPython(backfill_baseline_snapshots, remove_baseline_snapshots),
    ]

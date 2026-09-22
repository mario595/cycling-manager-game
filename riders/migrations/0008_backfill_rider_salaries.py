# Generated for #25 — see specs/rider-salaries-plan.md, W3.

from django.db import migrations

_BATCH_SIZE = 500


def backfill_weekly_salary(apps, schema_editor):
    """Every rider that existed before this feature shipped gets a real
    salary, computed the same way a newly generated rider's is. Imported
    inside the function, not at module scope: a historical Rider from
    apps.get_model() has no custom methods, but weekly_salary_for only
    reads plain fields (speciality, the five attributes, age), so it works
    against one unmodified."""
    from riders.pricing import weekly_salary_for

    Rider = apps.get_model("riders", "Rider")
    riders = list(Rider.objects.all())
    for rider in riders:
        rider.weekly_salary = weekly_salary_for(rider)
    Rider.objects.bulk_update(riders, ["weekly_salary"], batch_size=_BATCH_SIZE)


class Migration(migrations.Migration):

    dependencies = [
        ('riders', '0007_rider_weekly_salary'),
    ]

    operations = [
        migrations.RunPython(backfill_weekly_salary, migrations.RunPython.noop),
    ]

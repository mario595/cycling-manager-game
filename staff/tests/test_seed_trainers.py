from __future__ import annotations

from django.core.management import call_command

from staff.models import Trainer


def test_seed_creates_a_pool(db):
    call_command("seed_trainers", count=5)

    assert Trainer.objects.filter(team__isnull=True).count() == 5


def test_seed_does_not_touch_existing_trainers(db, trainer, team):
    trainer.team = team
    trainer.save()

    call_command("seed_trainers", count=3)

    trainer.refresh_from_db()
    assert trainer.team_id == team.pk
    assert Trainer.objects.count() == 4

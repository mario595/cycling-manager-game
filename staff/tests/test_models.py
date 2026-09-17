from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from schedule.models import Season, Week
from staff.models import DEFAULT_FOCUS, Trainer, TrainingFocus, TrainingWeekReport


def test_pool_trainer_has_no_team(trainer):
    assert trainer.team is None


def test_speciality_is_the_highest_skill(trainer):
    assert trainer.speciality == "climb"


def test_a_team_cannot_have_two_trainers(trainer, team):
    trainer.team = team
    trainer.save()

    second = Trainer(
        name="Coach Two",
        climb=30,
        sprint=90,
        flat=45,
        resistance=50,
        positioning=35,
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            second.team = team
            second.save()


def test_skill_below_one_is_rejected(trainer):
    trainer.climb = 0
    with pytest.raises(ValidationError):
        trainer.full_clean()


def test_skill_above_100_is_rejected(trainer):
    trainer.climb = 101
    with pytest.raises(ValidationError):
        trainer.full_clean()


def test_one_focus_per_team(team):
    TrainingFocus.objects.create(team=team, attribute="climb")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            TrainingFocus.objects.create(team=team, attribute="sprint")


def test_one_report_per_team_per_week(db, team):
    monday = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    season = Season.objects.create(number=1, starts_at=monday)
    week = Week.objects.create(
        season=season, number=1, starts_at=monday, ends_at=monday + timedelta(weeks=1),
    )
    TrainingWeekReport.objects.create(team=team, week=week)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            TrainingWeekReport.objects.create(team=team, week=week)


def test_focus_defaults_to_the_first_engine_attribute():
    assert DEFAULT_FOCUS == "climb"

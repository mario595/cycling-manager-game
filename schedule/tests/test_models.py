from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from schedule.models import SEASON_WEEKS, Season, SeasonTransition

MONDAY = datetime(2027, 3, 1, 0, 0, 0, tzinfo=dt_timezone.utc)


def test_ends_at_is_twelve_weeks_after_start(db):
    season = Season.objects.create(number=1, starts_at=MONDAY)

    assert (season.ends_at - season.starts_at).days == SEASON_WEEKS * 7


def test_rejects_a_start_that_is_not_a_monday_midnight(db):
    tuesday = MONDAY.replace(day=2)
    season = Season(number=1, starts_at=tuesday)

    with pytest.raises(ValidationError):
        season.clean()


def test_rejects_an_overlapping_season(db):
    Season.objects.create(number=1, starts_at=MONDAY)
    overlapping_start = MONDAY.replace(day=15)  # inside season 1's twelve weeks, still a Monday
    season_2 = Season(number=2, starts_at=overlapping_start)

    with pytest.raises(ValidationError):
        season_2.clean()


def test_duplicate_transition_is_rejected(db):
    season = Season.objects.create(number=1, starts_at=MONDAY)
    SeasonTransition.objects.create(
        season=season, kind=SeasonTransition.Kind.OPENED, occurred_at=MONDAY,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            SeasonTransition.objects.create(
                season=season, kind=SeasonTransition.Kind.OPENED, occurred_at=MONDAY,
            )

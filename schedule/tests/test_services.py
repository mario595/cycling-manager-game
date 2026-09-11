from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from schedule.models import SEASON_WEEKS, Season, SeasonTransition, Week
from schedule.services import current_position, process_transitions

MONDAY = datetime(2027, 3, 1, 0, 0, 0, tzinfo=dt_timezone.utc)


def make_season_with_weeks(number: int, starts_at: datetime) -> Season:
    season = Season.objects.create(number=number, starts_at=starts_at)
    for week_number in range(1, SEASON_WEEKS + 1):
        week_start = season.starts_at + timedelta(weeks=week_number - 1)
        Week.objects.create(
            season=season,
            number=week_number,
            starts_at=week_start,
            ends_at=week_start + timedelta(weeks=1),
        )
    return season


@pytest.mark.parametrize("week_number", [1, 6, 12])
def test_in_season_reports_the_right_week(db, week_number):
    season = make_season_with_weeks(1, MONDAY)
    at = season.starts_at + timedelta(weeks=week_number - 1, hours=1)

    position = current_position(at)

    assert position.state == "in_season"
    assert position.season == season
    assert position.week.number == week_number


def test_the_instant_a_season_ends_is_off_season(db):
    season = make_season_with_weeks(1, MONDAY)

    position = current_position(season.ends_at)

    assert position.state == "off_season"
    assert position.season == season


def test_the_instant_a_season_starts_is_week_one(db):
    season = make_season_with_weeks(1, MONDAY)

    at_start = current_position(season.starts_at)
    just_before = current_position(season.starts_at - timedelta(microseconds=1))

    assert at_start.state == "in_season"
    assert at_start.week.number == 1
    assert just_before.state == "no_season"


def test_off_season_names_the_season_that_just_finished(db):
    season_1 = make_season_with_weeks(1, MONDAY)
    # Declared but not started yet — the naive "highest number" implementation
    # would report this one instead of the season that just ended.
    Season.objects.create(number=2, starts_at=season_1.ends_at + timedelta(weeks=4))

    position = current_position(season_1.ends_at)

    assert position.state == "off_season"
    assert position.season == season_1


def test_no_season_before_anything_is_declared(db):
    position = current_position(MONDAY)

    assert position.state == "no_season"
    assert position.season is None
    assert position.week is None


def test_records_opened_when_the_start_has_passed(db):
    season = Season.objects.create(number=1, starts_at=MONDAY)

    written = process_transitions(season.starts_at + timedelta(hours=1))

    assert len(written) == 1
    assert written[0].kind == SeasonTransition.Kind.OPENED
    assert written[0].season == season
    assert written[0].occurred_at == season.starts_at


def test_records_nothing_twice(db):
    season = Season.objects.create(number=1, starts_at=MONDAY)
    at = season.starts_at + timedelta(hours=1)

    process_transitions(at)
    process_transitions(at)

    assert SeasonTransition.objects.filter(season=season, kind=SeasonTransition.Kind.OPENED).count() == 1


def test_catch_up_records_every_missed_boundary_in_order(db):
    past_season = Season.objects.create(number=1, starts_at=MONDAY)
    running_season = Season.objects.create(
        number=2, starts_at=past_season.ends_at + timedelta(weeks=4),
    )
    at = running_season.starts_at + timedelta(hours=1)

    written = process_transitions(at)

    past_transitions = {t.kind: t for t in written if t.season == past_season}
    running_transitions = {t.kind: t for t in written if t.season == running_season}

    assert set(past_transitions) == {SeasonTransition.Kind.OPENED, SeasonTransition.Kind.CLOSED}
    assert set(running_transitions) == {SeasonTransition.Kind.OPENED}
    assert past_transitions[SeasonTransition.Kind.OPENED].occurred_at == past_season.starts_at
    assert past_transitions[SeasonTransition.Kind.CLOSED].occurred_at == past_season.ends_at
    assert running_transitions[SeasonTransition.Kind.OPENED].occurred_at == running_season.starts_at

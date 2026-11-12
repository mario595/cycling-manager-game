from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.utils import timezone

from accounts.models import User
from feedback.models import Report
from feedback.services import (
    DAILY_REPORT_LIMIT,
    LIMIT_WINDOW,
    ReportLimitReached,
    reports_for,
    submit_report,
)
from teams.models import Team

# Far from the wall clock, so a test can tell the game clock from the real one.
GAME_TIME = datetime(2031, 3, 4, 12, 0, tzinfo=dt_timezone.utc)


def _submit(author, team=None, **overrides):
    fields = {
        "category": Report.Category.BUG,
        "text": "Something is off.",
        "location": "/finances",
        "team": team,
        "season_number": 1,
        "week_number": 3,
        "game_time": GAME_TIME,
    }
    fields.update(overrides)
    return submit_report(author, **fields)


@pytest.fixture
def author(db):
    return User.objects.create_user(email="agent@example.com", password="s0meth1ng-good")


def test_submit_stores_the_context_and_copies_the_team_name(author):
    team = Team.objects.create(name="Blue Team", code="BLU", manager=author)
    before = timezone.now()

    report = _submit(author, team=team)

    assert report.team == team
    assert report.team_name == "Blue Team"
    assert (report.season_number, report.week_number) == (1, 3)
    assert report.location == "/finances"
    assert report.game_time == GAME_TIME
    # created_at is the real clock, not the game clock.
    assert before <= report.created_at <= timezone.now()


def test_a_team_less_author_can_report(author):
    report = _submit(author, team=None, season_number=None, week_number=None)

    assert report.team is None
    assert report.team_name == ""
    assert report.season_number is None


def test_the_report_past_the_daily_limit_is_refused_with_a_retry_time(author):
    for _ in range(DAILY_REPORT_LIMIT):
        _submit(author)
    oldest = timezone.now() - timedelta(hours=5)
    first = Report.objects.order_by("created_at").first()
    Report.objects.filter(pk=first.pk).update(created_at=oldest)

    with pytest.raises(ReportLimitReached) as raised:
        _submit(author)

    assert raised.value.retry_at == oldest + LIMIT_WINDOW
    assert Report.objects.count() == DAILY_REPORT_LIMIT


def test_reports_older_than_the_window_do_not_count(author):
    for _ in range(DAILY_REPORT_LIMIT):
        _submit(author)
    Report.objects.update(created_at=timezone.now() - LIMIT_WINDOW - timedelta(minutes=1))

    _submit(author)

    assert Report.objects.count() == DAILY_REPORT_LIMIT + 1


def test_another_authors_reports_do_not_count(author):
    other = User.objects.create_user(email="other@example.com", password="s0meth1ng-good")
    for _ in range(DAILY_REPORT_LIMIT):
        _submit(other)

    _submit(author)

    assert Report.objects.filter(author=author).count() == 1


def test_reports_for_lists_only_the_authors_own_newest_first(author):
    other = User.objects.create_user(email="other@example.com", password="s0meth1ng-good")
    older = _submit(author)
    newer = _submit(author)
    _submit(other)
    Report.objects.filter(pk=older.pk).update(created_at=timezone.now() - timedelta(hours=1))

    assert list(reports_for(author)) == [newer, older]

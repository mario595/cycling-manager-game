"""The report-a-problem endpoint (#131). Kept out of api/tests.py, which is
already the size of a small book.

Every test runs under MockClock with the game clock years away from the
wall clock: under RealClock the two are equal, and a test could not tell a
report stamped with the wrong one from a right one."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

import world.models as world_models
import world.services as world_services
from accounts.models import User
from feedback.models import Report
from feedback.services import DAILY_REPORT_LIMIT
from schedule.models import Season, Week
from teams.models import ManagerialSpell, Team
from teams.services import release_team

URL = "/api/feedback/reports/"
GAME_NOW = datetime(2031, 3, 10, 9, 30, tzinfo=dt_timezone.utc)


@pytest.fixture(autouse=True)
def mock_clock(db):
    with override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock"):
        world_services._clock = None
        world_models.GameClock.load()
        world_services.get_clock().set(GAME_NOW)
        yield
        world_services._clock = None


@pytest.fixture
def season_in_week_two(db):
    season = Season.objects.create(number=3, starts_at=GAME_NOW - timedelta(days=10))
    for n in (1, 2):
        Week.objects.create(
            season=season,
            number=n,
            starts_at=season.starts_at + timedelta(weeks=n - 1),
            ends_at=season.starts_at + timedelta(weeks=n),
        )
    return season


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _manager():
    user = User.objects.create_user(email="agent@example.com", password="s0meth1ng-good")
    Team.objects.create(name="Agent Team", code="AGT", manager=user)
    return user


def test_a_report_records_its_context_in_season(season_in_week_two):
    user = _manager()
    before = timezone.now()

    response = _client(user).post(
        URL, {"category": "bug", "text": "Wages doubled.", "location": "/finances"}, format="json"
    )

    assert response.status_code == 201
    body = response.data
    assert body["category"] == "bug"
    assert body["team_name"] == "Agent Team"
    assert (body["season_number"], body["week_number"]) == (3, 2)
    assert body["location"] == "/finances"
    assert body["status"] == "new"
    report = Report.objects.get()
    assert report.team == user.team
    # The game clock, and separately the wall clock — never one for the other.
    assert report.game_time == GAME_NOW
    assert before <= report.created_at <= timezone.now()


def test_a_team_less_user_can_report(season_in_week_two):
    user = User.objects.create_user(email="new@example.com", password="s0meth1ng-good")

    response = _client(user).post(URL, {"category": "looks_wrong", "text": "Claim screen is blank."}, format="json")

    assert response.status_code == 201
    assert response.data["team_name"] == ""
    assert response.data["location"] == ""
    assert Report.objects.get().team is None


def test_off_season_leaves_season_and_week_empty(db):
    # A season that has finished: current_position() still names it, and the
    # report must not claim to belong to it.
    Season.objects.create(number=1, starts_at=GAME_NOW - timedelta(weeks=20))
    user = _manager()

    response = _client(user).post(URL, {"category": "balance", "text": "Off-season is long."}, format="json")

    assert response.status_code == 201
    assert response.data["season_number"] is None
    assert response.data["week_number"] is None


def test_before_any_season_leaves_season_and_week_empty(db):
    response = _client(_manager()).post(URL, {"category": "suggestion", "text": "Hi."}, format="json")

    assert response.status_code == 201
    assert response.data["season_number"] is None


def test_an_anonymous_visitor_cannot_report(db):
    response = APIClient().post(URL, {"category": "bug", "text": "x"}, format="json")

    assert response.status_code == 403


@pytest.mark.parametrize(
    "payload",
    [
        {"category": "bug", "text": "   "},
        {"category": "bug", "text": "x" * 4001},
        {"category": "rant", "text": "x"},
        {"category": "bug", "text": "x", "location": "/" * 301},
    ],
    ids=["blank text", "text too long", "unknown category", "location too long"],
)
def test_malformed_reports_are_refused(db, payload):
    response = _client(_manager()).post(URL, payload, format="json")

    assert response.status_code == 400
    assert Report.objects.count() == 0


def test_the_report_past_the_daily_limit_gets_a_429_with_a_retry_time(db):
    client = _client(_manager())
    for _ in range(DAILY_REPORT_LIMIT):
        assert client.post(URL, {"category": "bug", "text": "again"}, format="json").status_code == 201

    response = client.post(URL, {"category": "bug", "text": "again"}, format="json")

    assert response.status_code == 429
    assert "24 hours" in response.data["detail"]
    assert response.data["retry_at"] > timezone.now()
    assert Report.objects.count() == DAILY_REPORT_LIMIT


def test_the_list_is_the_callers_own_reports_without_the_triage_note(db):
    user = _manager()
    other = User.objects.create_user(email="other@example.com", password="s0meth1ng-good")
    _client(user).post(URL, {"category": "bug", "text": "mine"}, format="json")
    _client(other).post(URL, {"category": "bug", "text": "theirs"}, format="json")
    Report.objects.filter(text="mine").update(
        status=Report.Status.TRIAGED,
        github_issue_url="https://github.com/mario595/cycling-manager/issues/1",
        triage_note="Private.",
    )

    response = _client(user).get(URL)

    assert response.status_code == 200
    assert [r["text"] for r in response.data] == ["mine"]
    assert response.data[0]["status"] == "triaged"
    assert response.data[0]["github_issue_url"].endswith("/issues/1")
    assert "triage_note" not in response.data[0]


def test_a_report_keeps_its_team_after_the_manager_loses_it(season_in_week_two):
    user = _manager()
    team = user.team
    _client(user).post(URL, {"category": "bug", "text": "before release"}, format="json")

    release_team(team, reason=ManagerialSpell.Reason.INACTIVITY, at=GAME_NOW)
    team.name = "Renamed By Next Manager"
    team.save()
    user.refresh_from_db()

    response = _client(user).get(URL)

    assert response.data[0]["team_name"] == "Agent Team"
    assert Report.objects.get().team == team

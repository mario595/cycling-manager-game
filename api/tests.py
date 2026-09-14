from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

import world.services as world_services
from racing.models import Race, RaceSquad
from riders.models import Rider
from schedule.models import Season, Week
from teams.models import Team
from world.services import now

from accounts.models import User


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_clock_endpoint_returns_current_game_time(db):
    # MockClock, not whatever GAME_CLOCK_CLASS a developer's environment
    # happens to be running: against RealClock, two separate now() reads
    # (the view's and this assertion's) would almost never match exactly.
    world_services._clock = None
    try:
        response = APIClient().get("/api/world/clock/")

        assert response.status_code == 200
        assert response.data["current"] == now().isoformat().replace("+00:00", "Z")
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_position_endpoint_reports_the_current_week(db):
    world_services._clock = None
    try:
        season = Season.objects.create(number=1, starts_at=now())
        Week.objects.create(
            season=season, number=1,
            starts_at=season.starts_at, ends_at=season.starts_at + timedelta(weeks=1),
        )

        response = APIClient().get("/api/schedule/position/")

        assert response.status_code == 200
        assert response.data["state"] == "in_season"
        assert response.data["season"] == 1
        assert response.data["week"] == 1
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_position_endpoint_reports_no_season_when_none_declared(db):
    world_services._clock = None
    try:
        response = APIClient().get("/api/schedule/position/")

        assert response.status_code == 200
        assert response.data["state"] == "no_season"
        assert response.data["season"] is None
        assert response.data["week"] is None
    finally:
        world_services._clock = None


def _create_season_with_weeks(starts_at) -> Season:
    season = Season.objects.create(number=1, starts_at=starts_at)
    for week_number in range(1, 13):
        week_start = starts_at + timedelta(weeks=week_number - 1)
        Week.objects.create(
            season=season, number=week_number,
            starts_at=week_start, ends_at=week_start + timedelta(weeks=1),
        )
    return season


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_calendar_returns_twelve_weeks(db):
    world_services._clock = None
    try:
        season = _create_season_with_weeks(now())
        week_one = Week.objects.get(season=season, number=1)
        Race.objects.create(
            name="Opening Classic",
            course=[{"length": 40000.0, "gradient": 0.0}],
            starts_at=week_one.starts_at + timedelta(hours=14),
            week=week_one,
        )

        response = APIClient().get("/api/schedule/calendar/")

        assert response.status_code == 200
        assert len(response.data["weeks"]) == 12
        non_empty = [w for w in response.data["weeks"] if w["races"]]
        assert len(non_empty) == 1
        assert non_empty[0]["races"][0]["name"] == "Opening Classic"
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_calendar_reports_off_season_with_no_weeks(db):
    world_services._clock = None
    try:
        _create_season_with_weeks(now() - timedelta(weeks=13))

        response = APIClient().get("/api/schedule/calendar/")

        assert response.status_code == 200
        assert response.data["state"] == "off_season"
        assert response.data["weeks"] == []
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_calendar_reports_no_season_before_any_is_declared(db):
    world_services._clock = None
    try:
        response = APIClient().get("/api/schedule/calendar/")

        assert response.status_code == 200
        assert response.data["state"] == "no_season"
        assert response.data["weeks"] == []
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_calendar_race_carries_status_and_distance(db):
    world_services._clock = None
    try:
        season = _create_season_with_weeks(now())
        week_one = Week.objects.get(season=season, number=1)
        Race.objects.create(
            name="Opening Classic",
            course=[{"length": 40000.0, "gradient": 0.0}, {"length": 10000.0, "gradient": 0.0}],
            starts_at=week_one.starts_at + timedelta(hours=14),
            week=week_one,
        )

        response = APIClient().get("/api/schedule/calendar/")

        race_data = next(w for w in response.data["weeks"] if w["races"])["races"][0]
        assert race_data["status"] == "scheduled"
        assert race_data["distance_km"] == 50.0
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_calendar_is_public(db):
    world_services._clock = None
    try:
        client = APIClient()
        assert client.get("/api/schedule/calendar/").status_code == 200
    finally:
        world_services._clock = None


def test_me_reports_anonymous_for_a_visitor(db):
    response = APIClient().get("/api/accounts/me/")

    assert response.status_code == 200
    assert response.data["authenticated"] is False
    assert response.data["display_name"] is None
    assert response.data["team"] is None


def test_me_reports_the_logged_in_player_and_their_team(db):
    user = User.objects.create_user(email="mario@example.com", password="s0meth1ng-good", display_name="Mario")
    Team.objects.create(name="Squad Team", code="SQD", manager=user)
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/api/accounts/me/")

    assert response.status_code == 200
    assert response.data["authenticated"] is True
    assert response.data["display_name"] == "Mario"
    assert response.data["team"]["name"] == "Squad Team"


def test_me_reports_null_team_for_a_player_without_one(db):
    user = User.objects.create_user(email="mario@example.com", password="s0meth1ng-good")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/api/accounts/me/")

    assert response.status_code == 200
    assert response.data["authenticated"] is True
    assert response.data["team"] is None


def test_me_sets_the_csrf_cookie(db):
    response = APIClient(enforce_csrf_checks=True).get("/api/accounts/me/")

    assert response.status_code == 200
    assert "csrftoken" in response.cookies


@pytest.fixture
def squad_team(db) -> Team:
    return Team.objects.create(name="Squad Team", code="SQD")


@pytest.fixture
def squad_riders(db, squad_team) -> list[Rider]:
    return [
        Rider.objects.create(
            name=f"Squad Rider {i}", team=squad_team,
            role=Rider.Role.LEADER if i == 0 else Rider.Role.SUPPORT,
            climb=50, sprint=50, flat=50, resistance=50, positioning=50,
        )
        for i in range(4)
    ]


@pytest.fixture
def squad_race(db) -> Race:
    return Race.objects.create(
        name="Squad Check Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
    )


def test_squad_endpoint_returns_a_suggestion_for_an_unpicked_race(squad_race, squad_riders):
    team = squad_riders[0].team
    client = APIClient()

    response = client.get(f"/api/racing/races/{squad_race.pk}/squads/{team.pk}/")

    assert response.status_code == 200
    assert response.data["saved"] is False
    selected = [c for c in response.data["candidates"] if c["selected"]]
    assert len(selected) == 4


def test_putting_a_squad_saves_it_and_returns_it(squad_race, squad_riders):
    team = squad_riders[0].team
    client = APIClient()
    body = {
        "rider_ids": [r.pk for r in squad_riders],
        "leader_id": squad_riders[1].pk,
    }

    response = client.put(
        f"/api/racing/races/{squad_race.pk}/squads/{team.pk}/", body, format="json",
    )

    assert response.status_code == 200
    assert response.data["saved"] is True
    squad = RaceSquad.objects.get(race=squad_race, team=team)
    assert squad.members.count() == 4
    assert squad.members.get(is_leader=True).rider_id == squad_riders[1].pk


def test_putting_five_riders_is_a_400(squad_race, squad_riders):
    team = squad_riders[0].team
    extra = Rider.objects.create(
        name="Extra Rider", team=team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    client = APIClient()
    body = {
        "rider_ids": [r.pk for r in squad_riders] + [extra.pk],
        "leader_id": squad_riders[0].pk,
    }

    response = client.put(
        f"/api/racing/races/{squad_race.pk}/squads/{team.pk}/", body, format="json",
    )

    assert response.status_code == 400


def test_putting_a_squad_for_a_finished_race_is_a_400(squad_race, squad_riders):
    team = squad_riders[0].team
    squad_race.status = Race.Status.FINISHED
    squad_race.save(update_fields=["status"])
    client = APIClient()
    body = {
        "rider_ids": [r.pk for r in squad_riders],
        "leader_id": squad_riders[0].pk,
    }

    response = client.put(
        f"/api/racing/races/{squad_race.pk}/squads/{team.pk}/", body, format="json",
    )

    assert response.status_code == 400


def test_unknown_race_or_team_is_a_404(squad_race, squad_riders):
    team = squad_riders[0].team
    client = APIClient()

    assert client.get(f"/api/racing/races/999999/squads/{team.pk}/").status_code == 404
    assert client.get(f"/api/racing/races/{squad_race.pk}/squads/999999/").status_code == 404

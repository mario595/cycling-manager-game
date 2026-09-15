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
def squad_manager(db) -> User:
    return User.objects.create_user(email="squad-manager@example.com", password="s0meth1ng-good")


@pytest.fixture
def squad_team(db, squad_manager) -> Team:
    return Team.objects.create(name="Squad Team", code="SQD", manager=squad_manager)


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


@pytest.fixture
def squad_client(squad_manager) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=squad_manager)
    return client


def test_squad_requires_authentication(squad_race, squad_riders):
    client = APIClient()

    response = client.get(f"/api/racing/races/{squad_race.pk}/squad/")

    assert response.status_code == 403


def test_squad_forbids_a_player_with_no_team(squad_race, squad_riders):
    manager_without_a_team = User.objects.create_user(
        email="no-team@example.com", password="s0meth1ng-good",
    )
    client = APIClient()
    client.force_authenticate(user=manager_without_a_team)

    response = client.get(f"/api/racing/races/{squad_race.pk}/squad/")

    assert response.status_code == 403


def test_squad_returns_the_callers_own_team(squad_race, squad_riders, squad_client):
    response = squad_client.get(f"/api/racing/races/{squad_race.pk}/squad/")

    assert response.status_code == 200
    assert response.data["saved"] is False
    selected = [c for c in response.data["candidates"] if c["selected"]]
    assert len(selected) == 4


def test_squad_put_saves_for_the_callers_own_team(squad_race, squad_riders, squad_team, squad_client):
    body = {
        "rider_ids": [r.pk for r in squad_riders],
        "leader_id": squad_riders[1].pk,
    }

    response = squad_client.put(f"/api/racing/races/{squad_race.pk}/squad/", body, format="json")

    assert response.status_code == 200
    assert response.data["saved"] is True
    squad = RaceSquad.objects.get(race=squad_race, team=squad_team)
    assert squad.members.count() == 4
    assert squad.members.get(is_leader=True).rider_id == squad_riders[1].pk


def test_putting_five_riders_is_a_400(squad_race, squad_riders, squad_team, squad_client):
    extra = Rider.objects.create(
        name="Extra Rider", team=squad_team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    body = {
        "rider_ids": [r.pk for r in squad_riders] + [extra.pk],
        "leader_id": squad_riders[0].pk,
    }

    response = squad_client.put(f"/api/racing/races/{squad_race.pk}/squad/", body, format="json")

    assert response.status_code == 400


def test_putting_a_squad_for_a_finished_race_is_a_400(squad_race, squad_riders, squad_client):
    squad_race.status = Race.Status.FINISHED
    squad_race.save(update_fields=["status"])
    body = {
        "rider_ids": [r.pk for r in squad_riders],
        "leader_id": squad_riders[0].pk,
    }

    response = squad_client.put(f"/api/racing/races/{squad_race.pk}/squad/", body, format="json")

    assert response.status_code == 400


def test_unknown_race_is_a_404(squad_client):
    assert squad_client.get("/api/racing/races/999999/squad/").status_code == 404


def test_squad_candidates_use_display_scale(squad_race, squad_riders, squad_client):
    """Load-bearing: the squad screen shows 0-10, not the stored 1-100 —
    see specs/rider-attributes.md, *Display scale*."""
    rider = squad_riders[0]
    rider.climb = 94
    rider.save(update_fields=["climb"])

    response = squad_client.get(f"/api/racing/races/{squad_race.pk}/squad/")

    candidate = next(c for c in response.data["candidates"] if c["id"] == rider.pk)
    assert candidate["climb"] == 9


@pytest.fixture
def roster_manager(db) -> User:
    return User.objects.create_user(email="roster-manager@example.com", password="s0meth1ng-good")


@pytest.fixture
def roster_team(db, roster_manager) -> Team:
    return Team.objects.create(name="Roster Team", code="ROS", manager=roster_manager)


@pytest.fixture
def roster_rider(db, roster_team) -> Rider:
    return Rider.objects.create(
        name="Roster Rider", team=roster_team,
        speciality=Rider.Speciality.CLIMBER, age=24,
        height_cm=170, weight_kg=60,
        climb=94, sprint=30, flat=40, resistance=80, positioning=52,
    )


@pytest.fixture
def roster_client(roster_manager) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=roster_manager)
    return client


def test_rider_list_requires_authentication(roster_rider):
    client = APIClient()

    assert client.get("/api/riders/").status_code == 403


def test_rider_list_forbids_a_player_with_no_team(db):
    manager_without_a_team = User.objects.create_user(
        email="no-team-roster@example.com", password="s0meth1ng-good",
    )
    client = APIClient()
    client.force_authenticate(user=manager_without_a_team)

    assert client.get("/api/riders/").status_code == 403


def test_rider_list_returns_the_callers_own_team(roster_rider, roster_client):
    response = roster_client.get("/api/riders/")

    assert response.status_code == 200
    assert len(response.data) == 1
    rider_data = response.data[0]
    assert rider_data["id"] == roster_rider.pk
    assert rider_data["name"] == "Roster Rider"
    assert rider_data["speciality"] == "Climber"
    assert rider_data["age"] == 24
    assert rider_data["height_cm"] == 170
    assert rider_data["weight_kg"] == 60
    assert rider_data["climb"] == 9  # display scale, not the stored 94


def test_rider_serializer_hides_traits(roster_rider, roster_client):
    """Load-bearing: the hidden traits must never reach the player. A test
    asserting only the visible fields would pass even if this leaked —
    assert on absence."""
    response = roster_client.get("/api/riders/")

    rider_data = response.data[0]
    for hidden_field in (
        "potential", "peak_age", "decline_rate",
        "injury_proneness", "training_affinity",
    ):
        assert hidden_field not in rider_data


@pytest.fixture
def claimant(db) -> User:
    return User.objects.create_user(email="claimant@example.com", password="s0meth1ng-good")


@pytest.fixture
def claim_client(claimant) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=claimant)
    return client


def test_claim_requires_authentication(db):
    Team.objects.create(name="Unclaimed Team", code="UNC")
    client = APIClient()

    response = client.post("/api/teams/claim/", {"name": "New Name", "code": "NEW"}, format="json")

    assert response.status_code == 403


def test_claim_returns_the_new_team(db, claim_client):
    Team.objects.create(name="Unclaimed Team", code="UNC")

    response = claim_client.post(
        "/api/teams/claim/", {"name": "Mountain Goats", "code": "MGO"}, format="json",
    )

    assert response.status_code == 201
    assert response.data["name"] == "Mountain Goats"
    assert response.data["code"] == "MGO"


def test_claim_twice_is_409(db, claim_client):
    Team.objects.create(name="Unclaimed Team", code="UNC")
    Team.objects.create(name="Another Team", code="ANO")

    first = claim_client.post(
        "/api/teams/claim/", {"name": "Mountain Goats", "code": "MGO"}, format="json",
    )
    second = claim_client.post(
        "/api/teams/claim/", {"name": "Second Try", "code": "SEC"}, format="json",
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_claim_with_no_teams_available_is_409(db, claim_client):
    response = claim_client.post(
        "/api/teams/claim/", {"name": "Mountain Goats", "code": "MGO"}, format="json",
    )

    assert response.status_code == 409


def test_claim_lowercase_code_is_accepted_and_uppercased(db, claim_client):
    Team.objects.create(name="Unclaimed Team", code="UNC")

    response = claim_client.post(
        "/api/teams/claim/", {"name": "Mountain Goats", "code": "mgo"}, format="json",
    )

    assert response.status_code == 201
    assert response.data["code"] == "MGO"


def test_claim_duplicate_name_is_400(db, claim_client):
    other_manager = User.objects.create_user(
        email="other-manager@example.com", password="s0meth1ng-good",
    )
    Team.objects.create(name="Taken Name", code="TKN", manager=other_manager)
    Team.objects.create(name="Unclaimed Team", code="UNC")

    response = claim_client.post(
        "/api/teams/claim/", {"name": "Taken Name", "code": "MGO"}, format="json",
    )

    assert response.status_code == 400

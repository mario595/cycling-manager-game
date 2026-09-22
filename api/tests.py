from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

import world.services as world_services
from competitions.scoring import points_for, prize_for
from competitions.services import score_race
from economy.models import STARTING_BALANCE, LedgerEntry
from racing.models import Race, RaceResult, RaceSquad
from riders.display import to_display_scale
from riders.models import DISPLAY_MAX, Rider
from schedule.models import SEASON_WEEKS, Season, Week
from staff.models import Trainer, TrainingWeekReport
from staff.pricing import hire_fee, weekly_salary
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
        client = APIClient()
        user = User.objects.create_user(email="clock@example.com", password="s0meth1ng-good")
        client.force_authenticate(user=user)
        response = client.get("/api/world/clock/")

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

        client = APIClient()
        user = User.objects.create_user(email="position@example.com", password="s0meth1ng-good")
        client.force_authenticate(user=user)
        response = client.get("/api/schedule/position/")

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
        client = APIClient()
        user = User.objects.create_user(email="position@example.com", password="s0meth1ng-good")
        client.force_authenticate(user=user)
        response = client.get("/api/schedule/position/")

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

        client = APIClient()
        user = User.objects.create_user(email="calendar@example.com", password="s0meth1ng-good")
        client.force_authenticate(user=user)
        response = client.get("/api/schedule/calendar/")

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

        client = APIClient()
        user = User.objects.create_user(email="calendar@example.com", password="s0meth1ng-good")
        client.force_authenticate(user=user)
        response = client.get("/api/schedule/calendar/")

        assert response.status_code == 200
        assert response.data["state"] == "off_season"
        assert response.data["weeks"] == []
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_calendar_reports_no_season_before_any_is_declared(db):
    world_services._clock = None
    try:
        client = APIClient()
        user = User.objects.create_user(email="calendar@example.com", password="s0meth1ng-good")
        client.force_authenticate(user=user)
        response = client.get("/api/schedule/calendar/")

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

        client = APIClient()
        user = User.objects.create_user(email="calendar@example.com", password="s0meth1ng-good")
        client.force_authenticate(user=user)
        response = client.get("/api/schedule/calendar/")

        race_data = next(w for w in response.data["weeks"] if w["races"])["races"][0]
        assert race_data["status"] == "scheduled"
        assert race_data["distance_km"] == 50.0
    finally:
        world_services._clock = None


def test_clock_requires_login(db):
    client = APIClient()

    assert client.get("/api/world/clock/").status_code == 403

    user = User.objects.create_user(email="clocker@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    assert client.get("/api/world/clock/").status_code == 200


def test_position_requires_login(db):
    client = APIClient()

    assert client.get("/api/schedule/position/").status_code == 403

    user = User.objects.create_user(email="positioner@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    assert client.get("/api/schedule/position/").status_code == 200


def test_calendar_requires_login(db):
    client = APIClient()

    assert client.get("/api/schedule/calendar/").status_code == 403

    user = User.objects.create_user(email="calendars@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    assert client.get("/api/schedule/calendar/").status_code == 200


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


def test_squad_riders_include_freshness_on_display_scale(squad_race, squad_riders, squad_client):
    rider = squad_riders[0]
    rider.freshness = 30
    rider.save(update_fields=["freshness"])

    response = squad_client.get(f"/api/racing/races/{squad_race.pk}/squad/")

    candidate = next(c for c in response.data["candidates"] if c["id"] == rider.pk)
    assert candidate["freshness"] == to_display_scale(30)
    assert not isinstance(candidate["freshness"], str)


def test_squad_riders_never_expose_recovery_rate(squad_race, squad_riders, squad_client):
    response = squad_client.get(f"/api/racing/races/{squad_race.pk}/squad/")

    assert "recovery_rate" not in response.data["candidates"][0]


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
    assert rider_data["weekly_salary"] == roster_rider.weekly_salary


def test_rider_serializer_hides_traits(roster_rider, roster_client):
    """Load-bearing: the hidden traits must never reach the player. A test
    asserting only the visible fields would pass even if this leaked —
    assert on absence."""
    response = roster_client.get("/api/riders/")

    rider_data = response.data[0]
    for hidden_field in (
        "potential", "peak_age", "decline_rate",
        "injury_proneness", "training_affinity", "recovery_rate",
    ):
        assert hidden_field not in rider_data


def test_rider_list_includes_freshness_on_display_scale(roster_rider, roster_client):
    roster_rider.freshness = 30
    roster_rider.save(update_fields=["freshness"])

    response = roster_client.get("/api/riders/")

    assert response.data[0]["freshness"] == to_display_scale(30)


def test_rider_list_never_exposes_recovery_rate(roster_rider, roster_client):
    response = roster_client.get("/api/riders/")

    assert "recovery_rate" not in response.data[0]


def test_rider_list_weekly_salary_is_exact_not_display_scale(roster_rider, roster_client):
    roster_rider.weekly_salary = 3450
    roster_rider.save(update_fields=["weekly_salary"])

    response = roster_client.get("/api/riders/")

    assert response.data[0]["weekly_salary"] == 3450


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


@pytest.fixture
def finished_race_with_points(db) -> Race:
    team = Team.objects.create(name="Results Team", code="RES")
    rider = Rider.objects.create(
        name="Winner", team=team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    race = Race.objects.create(
        name="Results Check Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
    )
    RaceResult.objects.create(race=race, rider=rider, position=1, finish_time=1000.0)
    score_race(race)
    return race


def test_race_results_returns_order_and_points(finished_race_with_points):
    client = APIClient()
    user = User.objects.create_user(email="viewer@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{finished_race_with_points.pk}/results/")

    assert response.status_code == 200
    assert response.data["race"]["status"] == "finished"
    assert response.data["results"][0]["position"] == 1
    assert response.data["results"][0]["finished"] is True
    assert response.data["points"][0]["points"] == 20


def test_points_include_teams_that_scored_nothing(finished_race_with_points):
    """Load-bearing: starters come from RaceSquad, not from the distinct
    teams in results — a team entered in the race but with no result row
    still gets a zero row. See specs/race-detail-view-plan.md, D3."""
    non_scoring = Team.objects.create(name="Zero Team", code="ZRO")
    RaceSquad.objects.create(race=finished_race_with_points, team=non_scoring)

    client = APIClient()
    user = User.objects.create_user(email="viewer5@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{finished_race_with_points.pk}/results/")

    assert response.status_code == 200
    zero_row = next(p for p in response.data["points"] if p["team"]["id"] == non_scoring.pk)
    assert zero_row["points"] == 0
    assert zero_row["position"] is None
    assert response.data["points"][0]["team"]["id"] != non_scoring.pk


def test_unfinished_race_results_404(db):
    race = Race.objects.create(
        name="Not Yet Run", course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.SCHEDULED,
    )
    client = APIClient()
    user = User.objects.create_user(email="viewer2@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/results/")

    assert response.status_code == 404


def test_race_results_includes_prize_per_team(finished_race_with_points):
    at = datetime(2027, 3, 2, 0, 0, tzinfo=dt_timezone.utc)
    team = finished_race_with_points.points.get().team
    for position, amount in [(1, 20_000), (5, 8_000)]:
        LedgerEntry.objects.create(
            team=team, kind=LedgerEntry.Kind.PRIZE_MONEY, amount=amount,
            occurred_at=at, race=finished_race_with_points, position=position,
            description=f"Prize money — {finished_race_with_points.name}",
        )

    client = APIClient()
    user = User.objects.create_user(email="viewer3@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{finished_race_with_points.pk}/results/")

    assert response.status_code == 200
    scored_row = next(
        p for p in response.data["points"]
        if p["team"]["id"] == team.pk and p["position"] is not None
    )
    assert scored_row["prize"] == 28_000


def test_race_results_prize_is_zero_for_unplaced_starters(finished_race_with_points):
    non_scoring = Team.objects.create(name="Zero Team", code="ZRO")
    RaceSquad.objects.create(race=finished_race_with_points, team=non_scoring)

    client = APIClient()
    user = User.objects.create_user(email="viewer4@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{finished_race_with_points.pk}/results/")

    assert response.status_code == 200
    zero_row = next(p for p in response.data["points"] if p["team"]["id"] == non_scoring.pk)
    assert zero_row["points"] == 0
    assert zero_row["prize"] == 0


def test_race_results_requires_login(finished_race_with_points):
    client = APIClient()

    response = client.get(f"/api/racing/races/{finished_race_with_points.pk}/results/")

    assert response.status_code == 403


def test_race_detail_returns_course_and_distance(db):
    race = Race.objects.create(
        name="Route Detail Race",
        course=[{"length": 40000.0, "gradient": 0.0}, {"length": 10000.0, "gradient": 0.03}],
        status=Race.Status.SCHEDULED,
    )
    client = APIClient()
    user = User.objects.create_user(email="race-detail@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/")

    assert response.status_code == 200
    assert response.data["id"] == race.pk
    assert response.data["name"] == "Route Detail Race"
    assert response.data["status"] == "scheduled"
    assert response.data["distance_km"] == 50.0
    assert response.data["course"] == [
        {"length": 40000.0, "gradient": 0.0},
        {"length": 10000.0, "gradient": 0.03},
    ]


def test_race_detail_includes_payout_table(db):
    race = Race.objects.create(
        name="Payout Detail Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.SCHEDULED,
    )
    client = APIClient()
    user = User.objects.create_user(email="race-payout@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/")

    assert response.status_code == 200
    assert response.data["payout"] == [
        {"position": position, "points": points_for(position), "prize": prize_for(position)}
        for position in range(1, 11)
    ]


def test_race_detail_available_without_a_team(db):
    race = Race.objects.create(
        name="Team-less Race", course=[{"length": 40000.0, "gradient": 0.0}],
    )
    manager_without_a_team = User.objects.create_user(
        email="no-team-detail@example.com", password="s0meth1ng-good",
    )
    client = APIClient()
    client.force_authenticate(user=manager_without_a_team)

    response = client.get(f"/api/racing/races/{race.pk}/")

    assert response.status_code == 200


def test_race_detail_requires_login(db):
    race = Race.objects.create(
        name="Private Race", course=[{"length": 40000.0, "gradient": 0.0}],
    )
    client = APIClient()

    response = client.get(f"/api/racing/races/{race.pk}/")

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


def make_season_with_weeks(number: int, starts_at) -> Season:
    season = Season.objects.create(number=number, starts_at=starts_at)
    for week_number in range(1, SEASON_WEEKS + 1):
        week_start = season.starts_at + timedelta(weeks=week_number - 1)
        Week.objects.create(
            season=season, number=week_number,
            starts_at=week_start, ends_at=week_start + timedelta(weeks=1),
        )
    return season


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_standings_returns_ranked_table(db):
    world_services._clock = None
    try:
        season = make_season_with_weeks(1, now().replace(hour=0, minute=0, second=0, microsecond=0))
        week = season.weeks.get(number=1)
        team = Team.objects.create(name="Standings Team", code="STA")
        rider = Rider.objects.create(
            name="Winner", team=team,
            climb=50, sprint=50, flat=50, resistance=50, positioning=50,
        )
        race = Race.objects.create(
            name="Standings Check Race",
            course=[{"length": 40000.0, "gradient": 0.0}],
            status=Race.Status.FINISHED, week=week, starts_at=week.starts_at,
        )
        RaceResult.objects.create(race=race, rider=rider, position=1, finish_time=1000.0)
        score_race(race)

        client = APIClient()
        user = User.objects.create_user(email="viewer3@example.com", password="s0meth1ng-good")
        client.force_authenticate(user=user)

        response = client.get("/api/competitions/standings/")

        assert response.status_code == 200
        assert response.data["state"] == "in_season"
        assert response.data["standings"][0]["rank"] == 1
        assert response.data["standings"][0]["team"]["code"] == "STA"
        assert response.data["standings"][0]["points"] == 20
    finally:
        world_services._clock = None


def test_standings_no_season_returns_empty(db):
    client = APIClient()
    user = User.objects.create_user(email="viewer4@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get("/api/competitions/standings/")

    assert response.status_code == 200
    assert response.data["state"] == "no_season"
    assert response.data["standings"] == []


def test_standings_requires_login(db):
    client = APIClient()

    response = client.get("/api/competitions/standings/")

    assert response.status_code == 403


def test_rider_serializer_has_no_role(roster_rider, roster_client):
    """Leadership is a per-race property, not a fact about a rider — see
    specs/leadership-is-per-race.md."""
    response = roster_client.get("/api/riders/")

    assert "role" not in response.data[0]


def test_squad_candidates_have_no_role(squad_race, squad_riders, squad_client):
    """Leadership is a per-race property, held by is_leader — see
    specs/leadership-is-per-race.md."""
    response = squad_client.get(f"/api/racing/races/{squad_race.pk}/squad/")

    assert "role" not in response.data["candidates"][0]


@pytest.fixture
def staff_manager(db) -> User:
    return User.objects.create_user(email="staff-manager@example.com", password="s0meth1ng-good")


@pytest.fixture
def staff_team(db, staff_manager) -> Team:
    return Team.objects.create(name="Staff Team", code="STF", manager=staff_manager)


@pytest.fixture
def staff_client(staff_manager) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=staff_manager)
    return client


@pytest.fixture
def pool_trainer(db) -> Trainer:
    return Trainer.objects.create(
        name="Coach One", climb=90, sprint=40, flat=45, resistance=50, positioning=35,
    )


def test_staff_requires_authentication(db):
    client = APIClient()

    assert client.get("/api/staff/").status_code == 403


def test_staff_without_a_team_is_403(db):
    manager_without_a_team = User.objects.create_user(
        email="no-team-staff@example.com", password="s0meth1ng-good",
    )
    client = APIClient()
    client.force_authenticate(user=manager_without_a_team)

    assert client.get("/api/staff/").status_code == 403


def test_staff_shows_the_pool_when_the_slot_is_empty(staff_client, staff_team, pool_trainer):
    response = staff_client.get("/api/staff/")

    assert response.status_code == 200
    assert response.data["trainer"] is None
    assert len(response.data["pool"]) == 1
    assert response.data["pool"][0]["id"] == pool_trainer.pk


def test_staff_shows_the_trainer_when_hired(staff_client, staff_team, pool_trainer):
    pool_trainer.team = staff_team
    pool_trainer.save()

    response = staff_client.get("/api/staff/")

    assert response.data["trainer"]["id"] == pool_trainer.pk
    assert response.data["pool"] == []


def test_staff_payload_carries_prices_and_balance(staff_client, staff_team, pool_trainer):
    make_ledger_entry(
        staff_team, "starting_balance", STARTING_BALANCE, now(), "Starting balance",
    )

    response = staff_client.get("/api/staff/")

    assert response.data["balance"] == STARTING_BALANCE
    trainer = response.data["pool"][0]
    assert trainer["hire_fee"] == hire_fee(pool_trainer)
    assert trainer["weekly_salary"] == weekly_salary(pool_trainer)


def test_staff_skills_are_on_the_display_scale(staff_client, staff_team, pool_trainer):
    response = staff_client.get("/api/staff/")

    skills = response.data["pool"][0]["skills"]
    for value in skills.values():
        assert 0 <= value <= DISPLAY_MAX
    assert skills["climb"] == 9  # display scale, not the stored 90


def test_hire_fills_the_slot(staff_client, staff_team, pool_trainer):
    # A hire now costs a fee, so the team needs a balance for it to go
    # through — the plain unaffordable case is its own test below.
    make_ledger_entry(
        staff_team, "starting_balance", STARTING_BALANCE, now(), "Starting balance",
    )

    response = staff_client.post("/api/staff/trainer/hire/", {"trainer_id": pool_trainer.pk})

    assert response.status_code == 204
    follow_up = staff_client.get("/api/staff/")
    assert follow_up.data["trainer"]["id"] == pool_trainer.pk


def test_hire_debits_the_fee(staff_client, staff_team, pool_trainer):
    make_ledger_entry(
        staff_team, "starting_balance", STARTING_BALANCE, now(), "Starting balance",
    )

    response = staff_client.post("/api/staff/trainer/hire/", {"trainer_id": pool_trainer.pk})

    assert response.status_code == 204
    follow_up = staff_client.get("/api/staff/")
    assert follow_up.data["balance"] == STARTING_BALANCE - hire_fee(pool_trainer)
    fee_entry = LedgerEntry.objects.get(team=staff_team, kind="trainer_fee")
    assert fee_entry.amount == -hire_fee(pool_trainer)
    assert pool_trainer.name in fee_entry.description


def test_hire_refused_when_balance_too_low(staff_client, staff_team, pool_trainer):
    make_ledger_entry(staff_team, "starting_balance", 100, now(), "Starting balance")

    response = staff_client.post("/api/staff/trainer/hire/", {"trainer_id": pool_trainer.pk})

    assert response.status_code == 409
    pool_trainer.refresh_from_db()
    assert pool_trainer.team_id is None
    assert not LedgerEntry.objects.filter(team=staff_team, kind="trainer_fee").exists()


def test_fire_refunds_nothing(staff_client, staff_team, pool_trainer):
    make_ledger_entry(
        staff_team, "starting_balance", STARTING_BALANCE, now(), "Starting balance",
    )
    staff_client.post("/api/staff/trainer/hire/", {"trainer_id": pool_trainer.pk})

    response = staff_client.post("/api/staff/trainer/fire/")

    assert response.status_code == 204
    follow_up = staff_client.get("/api/staff/")
    assert follow_up.data["balance"] == STARTING_BALANCE - hire_fee(pool_trainer)


def test_hire_an_already_hired_trainer_returns_409(staff_client, staff_team, pool_trainer):
    other_manager = User.objects.create_user(email="other-staff@example.com", password="s0meth1ng-good")
    other_team = Team.objects.create(name="Other Staff Team", code="OST", manager=other_manager)
    pool_trainer.team = other_team
    pool_trainer.save()

    response = staff_client.post("/api/staff/trainer/hire/", {"trainer_id": pool_trainer.pk})

    assert response.status_code == 409


def test_hire_when_slot_occupied_returns_409(staff_client, staff_team, pool_trainer):
    hired = Trainer.objects.create(
        name="Coach Two", team=staff_team,
        climb=30, sprint=90, flat=45, resistance=50, positioning=35,
    )

    response = staff_client.post("/api/staff/trainer/hire/", {"trainer_id": pool_trainer.pk})

    assert response.status_code == 409
    hired.refresh_from_db()
    assert hired.team_id == staff_team.pk


def test_fire_empties_the_slot(staff_client, staff_team, pool_trainer):
    pool_trainer.team = staff_team
    pool_trainer.save()

    response = staff_client.post("/api/staff/trainer/fire/")

    assert response.status_code == 204
    follow_up = staff_client.get("/api/staff/")
    assert follow_up.data["trainer"] is None
    assert any(t["id"] == pool_trainer.pk for t in follow_up.data["pool"])


def test_fire_with_no_trainer_returns_409(staff_client, staff_team):
    response = staff_client.post("/api/staff/trainer/fire/")

    assert response.status_code == 409


def test_hire_cannot_target_another_teams_trainer(staff_client, staff_team):
    other_manager = User.objects.create_user(email="employed-staff@example.com", password="s0meth1ng-good")
    other_team = Team.objects.create(name="Employed Team", code="EMP", manager=other_manager)
    employed = Trainer.objects.create(
        name="Coach Three", team=other_team,
        climb=90, sprint=40, flat=45, resistance=50, positioning=35,
    )

    response = staff_client.post("/api/staff/trainer/hire/", {"trainer_id": employed.pk})

    assert response.status_code == 409
    employed.refresh_from_db()
    assert employed.team_id == other_team.pk


def test_training_get_without_trainer_has_no_focus(staff_client, staff_team):
    response = staff_client.get("/api/staff/training/")

    assert response.status_code == 200
    assert response.data["has_trainer"] is False
    assert response.data["focus"] is None
    assert response.data["last_week"] is None
    assert set(response.data["options"]) == set(["climb", "sprint", "flat", "resistance", "positioning"])


def test_training_put_sets_focus(staff_client, staff_team):
    # Hire a trainer first so the team has a focus decision to make.
    trainer = Trainer.objects.create(
        name="Coach", team=staff_team,
        climb=90, sprint=40, flat=45, resistance=50, positioning=35,
    )

    response = staff_client.put("/api/staff/training/", {"attribute": "sprint"}, format="json")
    follow_up = staff_client.get("/api/staff/training/")

    assert response.status_code == 204
    assert follow_up.data["has_trainer"] is True
    assert follow_up.data["focus"] == "sprint"


def test_training_put_without_trainer_is_409(staff_client, staff_team):
    response = staff_client.put("/api/staff/training/", {"attribute": "climb"}, format="json")

    assert response.status_code == 409


def test_training_never_exposes_training_affinity(staff_client, staff_team):
    monday = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    season = Season.objects.create(number=1, starts_at=monday)
    week = Week.objects.create(
        season=season, number=1, starts_at=monday, ends_at=monday + timedelta(weeks=1),
    )
    rider = Rider.objects.create(
        name="Trainee", team=staff_team,
        climb=89, sprint=40, flat=40, resistance=40, positioning=40,
        training_affinity={"climb": 1.5, "sprint": 0.5, "flat": 1.0, "resistance": 1.0, "positioning": 1.0},
    )
    TrainingWeekReport.objects.create(
        team=staff_team, week=week, attribute="climb",
        changes=[{
            "rider_id": rider.pk, "rider_name": rider.name, "team_id": staff_team.pk,
            "attribute": "climb", "from": 8, "to": 9,
        }],
    )

    response = staff_client.get("/api/staff/training/")

    assert response.status_code == 200
    body = json.dumps(response.data)
    assert "training_affinity" not in body
    change = response.data["last_week"]["changes"][0]
    assert change["from_value"] == 8
    assert change["to_value"] == 9


@pytest.fixture
def finances_manager(db) -> User:
    return User.objects.create_user(email="finances-manager@example.com", password="s0meth1ng-good")


@pytest.fixture
def finances_team(db, finances_manager) -> Team:
    return Team.objects.create(name="Finances Team", code="FIN", manager=finances_manager)


@pytest.fixture
def finances_client(finances_manager) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=finances_manager)
    return client


def make_ledger_entry(team, kind, amount, occurred_at, description):
    from economy.models import LedgerEntry
    return LedgerEntry.objects.create(
        team=team, kind=kind, amount=amount,
        occurred_at=occurred_at, description=description,
    )


def make_fanbase_entry(team, kind, delta, occurred_at, *, week=None, points=0):
    from economy.models import FanbaseEntry
    return FanbaseEntry.objects.create(
        team=team, kind=kind, delta=delta, occurred_at=occurred_at,
        week=week, points=points,
    )


def test_finances_requires_a_session(finances_team):
    client = APIClient()

    response = client.get("/api/economy/finances/")

    assert response.status_code == 403


def test_finances_returns_balance_and_entries(finances_client, finances_team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    make_ledger_entry(
        finances_team, "starting_balance", 500_000, at, "Starting balance",
    )
    make_ledger_entry(
        finances_team, "wages", -14_400, at + timedelta(weeks=1), "Weekly wages",
    )

    response = finances_client.get("/api/economy/finances/")

    assert response.status_code == 200
    assert response.data["balance"] == 485_600
    assert len(response.data["entries"]) == 2


def test_entries_are_newest_first_with_running_balance(finances_client, finances_team):
    """Load-bearing: D7's off-by-one lives here. The oldest entry's
    `balance_after` must equal the starting balance, and the newest must
    equal the current `balance`."""
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    make_ledger_entry(
        finances_team, "starting_balance", 500_000, at, "Starting balance",
    )
    make_ledger_entry(
        finances_team, "wages", -14_400, at + timedelta(weeks=1), "Weekly wages",
    )
    make_ledger_entry(
        finances_team, "wages", -14_400, at + timedelta(weeks=2), "Weekly wages",
    )

    response = finances_client.get("/api/economy/finances/")

    entries = response.data["entries"]
    assert [e["kind"] for e in entries] == ["wages", "wages", "starting_balance"]
    assert entries[-1]["balance_after"] == 500_000
    assert entries[0]["balance_after"] == 471_200
    assert entries[0]["balance_after"] == response.data["balance"]


def test_finances_for_a_user_with_no_team(db):
    manager_without_a_team = User.objects.create_user(
        email="no-team-finances@example.com", password="s0meth1ng-good",
    )
    client = APIClient()
    client.force_authenticate(user=manager_without_a_team)

    response = client.get("/api/economy/finances/")

    assert response.status_code == 200
    assert response.data["balance"] == 0
    assert response.data["weekly_wage_bill"] == 0
    assert response.data["entries"] == []


def test_finances_weekly_wage_bill_is_current_roster_payroll(finances_client, finances_team):
    # Deliberately not the ledger's last wages entry — the bill reflects
    # the roster as it stands now, per FinancesSerializer's docstring.
    attrs = dict(climb=50, sprint=50, flat=50, resistance=50, positioning=50)
    Rider.objects.create(team=finances_team, name="A", weekly_salary=1500, **attrs)
    Rider.objects.create(team=finances_team, name="B", weekly_salary=2200, **attrs)

    response = finances_client.get("/api/economy/finances/")

    assert response.status_code == 200
    assert response.data["weekly_wage_bill"] == 3700


def test_finances_includes_fanbase_and_weekly_change(finances_client, finances_team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    make_fanbase_entry(finances_team, "starting", 10_000, at)
    make_fanbase_entry(
        finances_team, "weekly", 650, at + timedelta(weeks=1), points=20,
    )
    make_fanbase_entry(
        finances_team, "weekly", -200, at + timedelta(weeks=2),
    )

    response = finances_client.get("/api/economy/finances/")

    assert response.status_code == 200
    assert response.data["fanbase"] == 10_450
    assert response.data["fanbase_change"] == -200


def test_finances_fanbase_change_is_zero_before_any_weekly_entry(finances_client, finances_team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    make_fanbase_entry(finances_team, "starting", 10_000, at)

    response = finances_client.get("/api/economy/finances/")

    assert response.status_code == 200
    assert response.data["fanbase"] == 10_000
    assert response.data["fanbase_change"] == 0


def test_finances_without_a_team_returns_zero_fanbase(db):
    manager_without_a_team = User.objects.create_user(
        email="no-team-finances-fanbase@example.com", password="s0meth1ng-good",
    )
    client = APIClient()
    client.force_authenticate(user=manager_without_a_team)

    response = client.get("/api/economy/finances/")

    assert response.status_code == 200
    assert response.data["fanbase"] == 0
    assert response.data["fanbase_change"] == 0


def test_merchandise_entry_serializes_with_its_kind(finances_client, finances_team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    make_ledger_entry(
        finances_team, "starting_balance", 500_000, at, "Starting balance",
    )
    make_ledger_entry(
        finances_team, "merchandise", 400, at + timedelta(weeks=1),
        "Merchandise revenue",
    )

    response = finances_client.get("/api/economy/finances/")

    assert response.status_code == 200
    entry = response.data["entries"][0]
    assert entry["kind"] == "merchandise"
    assert entry["amount"] == 400


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_finances_history_built_through_services_orders_by_game_time(db):
    """The regression test for review finding 1: every ledger entry must be
    stamped with *game* time, never the wall clock. A season dated 2027
    against a wall clock that reads one year earlier is exactly the trap —
    had opening balance / takeover used timezone.now(), they'd sort as the
    oldest rows and the newest-first order and running balance would invert.
    Serve the history from games, not read it off the page: opening balance,
    a week of wages, then a claim, each through the real services callers
    use, passing world.services.now() as `at`.
    """
    world_services._clock = None
    try:
        from economy.services import charge_weekly_wages, ensure_opening_balance
        from teams.services import claim_team
        from world.services import get_clock, now

        clock: MockClock = get_clock()
        season_start = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
        # The world's clock lives a year in the future of the wall clock this
        # test runs under. That divergence is the bug's fuel. load() first:
        # MockClock.set() reads the GameClock row, which load() creates.
        import world.models as world_models
        world_models.GameClock.load()
        clock.set(season_start - timedelta(days=1))

        unmanaged = Team.objects.create(name="Pool Team", code="POL")
        Rider.objects.create(
            name="Pool Rider", team=unmanaged,
            climb=60, sprint=60, flat=60, resistance=60, positioning=60,
        )
        user = User.objects.create_user(
            email="claim-finances@example.com", password="s0meth1ng-good",
        )

        ensure_opening_balance(unmanaged, at=now())   # stamped 2027-02-28

        season = Season.objects.create(number=1, starts_at=season_start)
        week = Week.objects.create(
            season=season, number=1,
            starts_at=season_start, ends_at=season_start + timedelta(weeks=1),
        )
        charge_weekly_wages(week)                      # stamped week.starts_at (2027-03-01)

        clock.set(season_start + timedelta(days=7))
        claim_team(user, name="Claimed Team", code="CLM", roster_size=0, at=now())

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get("/api/economy/finances/")
        assert response.status_code == 200

        entries = response.data["entries"]
        assert [e["kind"] for e in entries] == ["takeover", "wages", "starting_balance"]
        # Newest first, each balance_after chaining onto the previous one.
        assert entries[0]["occurred_at"] == "2027-03-08T00:00:00Z"
        assert entries[1]["occurred_at"] == "2027-03-01T00:00:00Z"
        assert entries[2]["occurred_at"] == "2027-02-28T00:00:00Z"
        assert entries[2]["balance_after"] == 500_000
        assert entries[1]["balance_after"] == 500_000 - 1_200
        assert entries[0]["balance_after"] == 500_000
        assert entries[0]["balance_after"] == response.data["balance"]
    finally:
        world_services._clock = None


@pytest.fixture
def sponsors_manager(db) -> User:
    return User.objects.create_user(email="sponsors-manager@example.com", password="s0meth1ng-good")


@pytest.fixture
def sponsors_team(db, sponsors_manager) -> Team:
    return Team.objects.create(name="Sponsors Team", code="SPN", manager=sponsors_manager)


@pytest.fixture
def sponsors_client(sponsors_manager) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=sponsors_manager)
    return client


@pytest.fixture
def sponsors_season(db):
    """An in-season MockClock position, so current_position(now()) resolves
    to a real Season for SponsorsView — the same shape sponsors_team needs
    to generate offers against. Resets the clock after the test, matching
    the clock/finances tests above."""
    world_services._clock = None
    season_start = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    season = Season.objects.create(number=1, starts_at=season_start)
    Week.objects.create(
        season=season, number=1,
        starts_at=season_start, ends_at=season_start + timedelta(weeks=1),
    )
    with override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock"):
        clock = world_services.get_clock()
        clock.now()  # GameClock.load() — creates the row set() requires
        clock.set(season_start + timedelta(hours=1))
        yield season
    world_services._clock = None


def test_sponsors_requires_authentication(db):
    client = APIClient()

    assert client.get("/api/economy/sponsors/").status_code == 403


def test_sponsors_without_a_team_is_empty_not_403(db):
    manager_without_a_team = User.objects.create_user(
        email="no-team-sponsors@example.com", password="s0meth1ng-good",
    )
    client = APIClient()
    client.force_authenticate(user=manager_without_a_team)

    response = client.get("/api/economy/sponsors/")

    assert response.status_code == 200
    assert response.data == {"contract": None, "offers": []}


def test_sponsors_returns_a_round_for_a_new_team(sponsors_client, sponsors_team, sponsors_season):
    response = sponsors_client.get("/api/economy/sponsors/")

    assert response.status_code == 200
    assert response.data["contract"] is None
    assert len(response.data["offers"]) == 3
    assert {o["profile"] for o in response.data["offers"]} == {"steady", "balanced", "demanding"}


def test_sponsors_returns_the_contract_once_signed(sponsors_client, sponsors_team, sponsors_season):
    first = sponsors_client.get("/api/economy/sponsors/")
    offer_id = first.data["offers"][0]["id"]
    sponsors_client.post("/api/economy/sponsors/sign/", {"offer_id": offer_id})

    response = sponsors_client.get("/api/economy/sponsors/")

    assert response.data["offers"] == []
    assert response.data["contract"]["sponsor_name"] == first.data["offers"][0]["sponsor_name"]


def test_sign_creates_the_contract(sponsors_client, sponsors_team, sponsors_season):
    round_response = sponsors_client.get("/api/economy/sponsors/")
    offer_id = round_response.data["offers"][0]["id"]

    response = sponsors_client.post("/api/economy/sponsors/sign/", {"offer_id": offer_id})

    assert response.status_code == 204
    from economy.models import SponsorContract
    assert SponsorContract.objects.filter(team=sponsors_team).count() == 1


def test_sign_twice_is_409(sponsors_client, sponsors_team, sponsors_season):
    round_response = sponsors_client.get("/api/economy/sponsors/")
    offers = round_response.data["offers"]
    sponsors_client.post("/api/economy/sponsors/sign/", {"offer_id": offers[0]["id"]})

    response = sponsors_client.post("/api/economy/sponsors/sign/", {"offer_id": offers[1]["id"]})

    assert response.status_code == 409


def test_sign_someone_elses_offer_is_409(sponsors_client, sponsors_team, sponsors_season):
    other_manager = User.objects.create_user(email="other-sponsors@example.com", password="s0meth1ng-good")
    other_team = Team.objects.create(name="Other Sponsors Team", code="OSP", manager=other_manager)
    from economy.services import ensure_offer_round
    other_offers = ensure_offer_round(other_team, sponsors_season, at=now())

    response = sponsors_client.post("/api/economy/sponsors/sign/", {"offer_id": other_offers[0].pk})

    assert response.status_code == 409

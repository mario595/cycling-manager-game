from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

import pytest

from riders.generation import SPECIALITY_PROFILES
from riders.models import ENGINE_ATTRIBUTES, Rider
from riders.pricing import weekly_salary_for
from riders.services import (
    FRESHNESS_FLOOR,
    FRESHNESS_MAX,
    MAX_ATTRIBUTE,
    MIN_ATTRIBUTE,
    PENALTY_AT_FLOOR,
    _settle,
    advance_ages,
    apply_race_cost,
    apply_weekly_growth,
    apply_weekly_recovery,
    attribute_ceilings,
    freshness_multiplier,
    mark_team_change,
    recovery_amount,
    reprice_all,
    training_deltas,
    weekly_deltas,
)
from teams.models import Team


def make_rider(**overrides) -> Rider:
    defaults = dict(
        name="Test Rider",
        speciality=Rider.Speciality.CLIMBER,
        age=20,
        potential=80,
        peak_age=27,
        decline_rate=50,
        climb=40,
        sprint=40,
        flat=40,
        resistance=40,
        positioning=40,
    )
    defaults.update(overrides)
    return Rider(**defaults)


def test_a_climbers_climb_ceiling_exceeds_their_sprint_ceiling():
    rider = make_rider(speciality=Rider.Speciality.CLIMBER, potential=80)

    ceilings = attribute_ceilings(rider)

    assert ceilings["climb"] > ceilings["sprint"]


def test_ceilings_scale_potential_by_speciality_profile():
    rider = make_rider(speciality=Rider.Speciality.CLIMBER, potential=80)
    profile = SPECIALITY_PROFILES[Rider.Speciality.CLIMBER]
    mean_weight = sum(profile.values()) / len(profile)

    ceilings = attribute_ceilings(rider)

    assert ceilings["climb"] == pytest.approx(80 * (profile["climb"] / mean_weight))
    assert ceilings["sprint"] == pytest.approx(80 * (profile["sprint"] / mean_weight))


def test_a_young_rider_below_potential_grows():
    rider = make_rider(age=20, peak_age=27, climb=40, potential=90)

    deltas = weekly_deltas(rider, weeks=1)

    assert deltas["climb"] > 0


def test_a_season_of_growth_for_a_young_rider_is_10_to_20_stored_points():
    # Spec (In scope #7): "a full season of growth ... is worth roughly
    # one to two points on the 0-10 display scale" — 10 to 20 stored
    # points. A young, promising-but-unfinished rider — climb 45, comparable
    # to what generation.py actually produces, with room left below a
    # realistic potential of 65 — is the representative case this promise
    # is about, not an extreme gap.
    rider = make_rider(age=20, peak_age=27, climb=45, potential=65)

    season_delta = weekly_deltas(rider, weeks=12)["climb"]

    assert 10 <= season_delta <= 20


def test_a_season_of_decline_for_a_veteran_is_10_to_20_stored_points():
    # Spec (In scope #7): "a rider deep in decline loses about the same
    # over a season." An average decline_rate, comfortably past peak (at
    # or beyond DECLINE_YEARS_CAP, where decline has finished
    # accelerating) is the representative deep-decline case, not an edge
    # case — most riders past their peak eventually reach it.
    rider = make_rider(age=34, peak_age=27, decline_rate=50)

    season_delta = weekly_deltas(rider, weeks=12)["climb"]

    assert -20 <= season_delta <= -10


def test_a_rider_past_peak_age_declines():
    rider = make_rider(age=30, peak_age=27, decline_rate=50)

    deltas = weekly_deltas(rider, weeks=1)

    for name in ENGINE_ATTRIBUTES:
        assert deltas[name] < 0


def test_decline_accelerates_with_years_past_peak():
    one_year_past = make_rider(age=28, peak_age=27, decline_rate=50)
    three_years_past = make_rider(age=30, peak_age=27, decline_rate=50)

    delta_one = weekly_deltas(one_year_past, weeks=1)["climb"]
    delta_three = weekly_deltas(three_years_past, weeks=1)["climb"]

    assert abs(delta_three) > abs(delta_one)


def test_decline_stops_accelerating_past_the_years_cap():
    # A veteran many years past peak must not keep losing more every
    # season forever — DECLINE_YEARS_CAP is what stops per-week decline
    # from scaling without bound the longer a rider has been past their
    # peak (a slice of the population this game generates: age caps at
    # 40, peak_age can be as young as 22).
    three_years_past = make_rider(age=30, peak_age=27, decline_rate=50)
    ten_years_past = make_rider(age=37, peak_age=27, decline_rate=50)

    delta_three = weekly_deltas(three_years_past, weeks=1)["climb"]
    delta_ten = weekly_deltas(ten_years_past, weeks=1)["climb"]

    assert delta_three == delta_ten


def test_a_higher_decline_rate_falls_faster():
    slow = make_rider(age=30, peak_age=27, decline_rate=10)
    fast = make_rider(age=30, peak_age=27, decline_rate=90)

    delta_slow = weekly_deltas(slow, weeks=1)["climb"]
    delta_fast = weekly_deltas(fast, weeks=1)["climb"]

    assert abs(delta_fast) > abs(delta_slow)


def test_a_rider_at_their_ceiling_below_peak_does_not_move():
    rider = make_rider(age=20, peak_age=27, potential=1, speciality=Rider.Speciality.ROULEUR)
    # Force every attribute to already sit at or above its ceiling.
    ceilings = attribute_ceilings(rider)
    for name in ENGINE_ATTRIBUTES:
        setattr(rider, name, max(1, round(ceilings[name]) + 5))

    deltas = weekly_deltas(rider, weeks=1)

    for name in ENGINE_ATTRIBUTES:
        assert deltas[name] == 0.0


def test_four_weeks_of_growth_equals_four_applications_of_one_week():
    rider = make_rider(age=20, peak_age=27, potential=90, climb=40)

    batched = weekly_deltas(rider, weeks=4)["climb"]

    # Apply one week's delta four times by hand, mutating a copy's climb
    # each time, to prove the closed-form batch calculation is exact
    # rather than an approximation.
    iterative_rider = make_rider(age=20, peak_age=27, potential=90, climb=40)
    for _ in range(4):
        step = weekly_deltas(iterative_rider, weeks=1)["climb"]
        iterative_rider.climb = iterative_rider.climb + step

    iterative_total = iterative_rider.climb - 40

    assert batched == pytest.approx(iterative_total, abs=1e-9)


def test_fractional_growth_accumulates_across_weeks_instead_of_being_lost(db):
    # A weekly delta under 1.0 must still add up over many weeks rather
    # than being rounded to 0 (truncated) or to 1 (rounded) every time.
    # `flat` is close to its own ceiling here while `climb` still has a
    # wide gap, so its weekly delta is the small, sub-1.0 one to watch.
    rider = Rider.objects.create(
        name="Young Climber",
        speciality=Rider.Speciality.CLIMBER,
        age=26,
        peak_age=27,
        potential=70,
        decline_rate=50,
        climb=60,
        sprint=40,
        flat=52,
        resistance=40,
        positioning=40,
    )
    weekly_flat_delta = weekly_deltas(rider, weeks=1)["flat"]
    assert 0 < weekly_flat_delta < 1

    for _ in range(7):
        apply_weekly_growth(weeks=1)
        rider.refresh_from_db()
    # Seven weeks of ~0.14/week accumulates to just under 1.0 of debt —
    # the attribute has not moved yet, proving the fraction was not
    # discarded on any single week.
    assert rider.flat == 52

    apply_weekly_growth(weeks=1)
    rider.refresh_from_db()
    # The eighth week tips accumulated debt over 1.0 and the stored
    # integer attribute finally moves — proving it was carried, not lost.
    assert rider.flat == 53


def test_attributes_never_leave_the_1_100_range(db):
    rider = Rider.objects.create(
        name="Ancient Rider",
        speciality=Rider.Speciality.CLIMBER,
        age=40,
        peak_age=22,
        potential=100,
        decline_rate=100,
        climb=1,
        sprint=1,
        flat=1,
        resistance=1,
        positioning=1,
    )

    apply_weekly_growth(weeks=500)
    rider.refresh_from_db()

    for name in ENGINE_ATTRIBUTES:
        assert MIN_ATTRIBUTE <= getattr(rider, name) <= MAX_ATTRIBUTE


def test_training_delta_scales_with_trainer_skill():
    rider = make_rider(speciality=Rider.Speciality.CLIMBER)
    weak = training_deltas(rider, focus="climb", trainer_skill=30, raced_attributes=[])
    strong = training_deltas(rider, focus="climb", trainer_skill=90, raced_attributes=[])

    assert 0 < weak["climb"] < strong["climb"]


def test_off_speciality_training_is_never_zero():
    rider = make_rider(speciality=Rider.Speciality.CLIMBER)
    rider.training_affinity = {"climb": 1.45, "sprint": 0.55}

    deltas = training_deltas(rider, focus="sprint", trainer_skill=30, raced_attributes=[])

    # A trainer working outside their speciality still improves the rider —
    # "not a substitute", never silence — just clearly less than in it.
    assert deltas["sprint"] > 0


def test_injured_rider_gets_nothing(monkeypatch):
    monkeypatch.setattr("riders.services.is_injured", lambda rider: True)
    rider = make_rider()

    deltas = training_deltas(
        rider, focus="climb", trainer_skill=90, raced_attributes=["climb", "sprint"],
    )

    assert all(value == 0.0 for value in deltas.values())


def test_training_and_growth_settle_through_one_debt(db):
    # The load-bearing test this plan exists for: a training delta and a
    # growth delta in the same week must settle through ONE debt ledger —
    # each at ~0.6, individually truncated to a zero carry, together worth
    # one stored point. A second pass after apply_weekly_growth would give
    # an answer of zero and this test fails.
    rider = Rider.objects.create(
        name="Trainee",
        speciality=Rider.Speciality.CLIMBER,
        age=20,
        peak_age=27,
        potential=80,
        decline_rate=50,
        climb=99,
        sprint=40,
        flat=40,
        resistance=40,
        positioning=40,
    )
    growth = weekly_deltas(rider, weeks=1)["climb"]
    assert 0 < growth < 1

    records = apply_weekly_growth(weeks=1, extra_deltas={rider.pk: {"climb": 0.6}})
    rider.refresh_from_db()

    assert rider.climb == 100
    assert records == [{
        "rider_id": rider.pk,
        "rider_name": "Trainee",
        "team_id": None,
        "attribute": "climb",
        "from": 9,
        "to": 10,
    }]


def test_debt_does_not_accumulate_once_an_attribute_is_clamped():
    new_value, remainder = _settle(current=MIN_ATTRIBUTE, debt=-0.9, delta=-0.9)

    assert new_value == MIN_ATTRIBUTE
    assert remainder == 0.0


def test_mark_team_change_sets_joined_or_unattached(db):
    team = Team.objects.create(name="Team Alpha", code="ALP")
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    later = datetime(2027, 3, 8, 0, 0, tzinfo=dt_timezone.utc)
    free_agent = Rider.objects.create(
        name="Free Agent", team=None, unattached_since=at,
        climb=1, sprint=1, flat=1, resistance=1, positioning=1,
    )
    on_roster = Rider.objects.create(
        name="On Roster", team=team, joined_team_at=at,
        climb=1, sprint=1, flat=1, resistance=1, positioning=1,
    )

    mark_team_change([free_agent], team_now=team, at=later)
    mark_team_change([on_roster], team_now=None, at=later)

    free_agent.refresh_from_db()
    on_roster.refresh_from_db()
    assert free_agent.joined_team_at == later
    assert free_agent.unattached_since is None
    assert on_roster.unattached_since == later
    assert on_roster.joined_team_at == at  # untouched by a release


def test_ageing_advances_every_rider_including_free_agents(db):
    rostered = Rider.objects.create(name="Rostered", age=25, climb=1, sprint=1, flat=1, resistance=1, positioning=1)
    free_agent = Rider.objects.create(name="Free Agent", team=None, age=25, climb=1, sprint=1, flat=1, resistance=1, positioning=1)

    changed = advance_ages()

    rostered.refresh_from_db()
    free_agent.refresh_from_db()
    assert changed == 2
    assert rostered.age == 26
    assert free_agent.age == 26


def test_ageing_stops_at_the_model_maximum(db):
    rider = Rider.objects.create(name="Veteran", age=40, climb=1, sprint=1, flat=1, resistance=1, positioning=1)

    advance_ages()
    rider.refresh_from_db()

    assert rider.age == 40


def make_repriced_rider(name: str, salary_move: int) -> Rider:
    """A rider whose stored salary is off the formula's value by
    `salary_move`, so reprice_all() moves it by exactly that amount."""
    rider = Rider.objects.create(
        name=name,
        speciality=Rider.Speciality.CLIMBER,
        age=25,
        climb=70,
        sprint=40,
        flat=40,
        resistance=40,
        positioning=40,
    )
    target = weekly_salary_for(rider)
    rider.weekly_salary = target - salary_move
    rider.save(update_fields=["weekly_salary"])
    return rider


def test_reprice_all_updates_every_rider_salary(db):
    rider = Rider.objects.create(
        name="Breakout Climber",
        speciality=Rider.Speciality.CLIMBER,
        age=25,
        climb=70,
        sprint=40,
        flat=40,
        resistance=40,
        positioning=40,
    )
    expected = weekly_salary_for(rider)
    rider.weekly_salary = 1200
    rider.save(update_fields=["weekly_salary"])

    changes = reprice_all()
    rider.refresh_from_db()

    assert changes[0]["to"] == expected
    assert rider.weekly_salary == expected


def test_reprice_all_reports_only_changes_over_threshold(db):
    small = make_repriced_rider("Moved Fifty", salary_move=50)
    large = make_repriced_rider("Moved Two Hundred", salary_move=200)

    changes = reprice_all()

    # D4: the write is unconditional — the 50-move rider is still stored at
    # the exact formula value, even though it is not worth reporting.
    small.refresh_from_db()
    large.refresh_from_db()
    assert small.weekly_salary == weekly_salary_for(small)
    assert large.weekly_salary == weekly_salary_for(large)

    returned = {change["rider_name"] for change in changes}
    assert returned == {"Moved Two Hundred"}


def test_reprice_all_returns_before_and_after(db):
    rider = make_repriced_rider("Raised Rider", salary_move=200)

    changes = reprice_all()

    assert changes == [{
        "rider_id": rider.pk,
        "rider_name": "Raised Rider",
        "team_id": rider.team_id,
        "from": rider.weekly_salary,
        "to": weekly_salary_for(rider),
    }]


def test_reprice_all_includes_free_agents(db):
    rider = make_repriced_rider("Free Agent", salary_move=200)
    rider.team = None
    rider.save(update_fields=["team"])

    changes = reprice_all()
    rider.refresh_from_db()

    assert changes[0]["team_id"] is None
    assert rider.weekly_salary == weekly_salary_for(rider)


def test_reprice_all_is_stable_when_nothing_changed(db):
    make_repriced_rider("Stable Rider", salary_move=200)

    first_run = reprice_all()
    second_run = reprice_all()

    assert len(first_run) == 1
    assert second_run == []


def test_freshness_multiplier_is_one_at_full():
    assert freshness_multiplier(FRESHNESS_MAX) == 1.0


def test_freshness_multiplier_is_penalty_at_floor():
    assert freshness_multiplier(FRESHNESS_FLOOR) == PENALTY_AT_FLOOR


def test_freshness_multiplier_clamps_out_of_range_input():
    # A freshness outside [FLOOR, MAX] (only reachable via admin or a
    # fixture) must never scale attributes *above* their stored value.
    assert freshness_multiplier(200) == 1.0
    assert freshness_multiplier(0) == PENALTY_AT_FLOOR


def test_recovery_amount_maps_recovery_rate_linearly():
    slow = make_rider(recovery_rate=MIN_ATTRIBUTE)
    fast = make_rider(recovery_rate=MAX_ATTRIBUTE)
    average = make_rider(recovery_rate=50)

    assert recovery_amount(slow) == 8
    assert recovery_amount(fast) == 20
    assert 8 < recovery_amount(average) < 20


def test_apply_race_cost_floors_at_minimum(db):
    rider = Rider.objects.create(
        name="Racer", climb=1, sprint=1, flat=1, resistance=1, positioning=1, freshness=40,
    )

    changed = apply_race_cost([rider.pk])
    rider.refresh_from_db()

    assert changed == 1
    assert rider.freshness == FRESHNESS_FLOOR  # 40 - 25 = 15, floored to 20


def test_apply_race_cost_never_drops_below_the_floor(db):
    rider = Rider.objects.create(
        name="Exhausted", climb=1, sprint=1, flat=1, resistance=1, positioning=1, freshness=FRESHNESS_FLOOR + 2,
    )

    changed = apply_race_cost([rider.pk])
    rider.refresh_from_db()

    assert changed == 1
    assert rider.freshness == FRESHNESS_FLOOR


def test_apply_weekly_recovery_caps_at_full(db):
    rider = Rider.objects.create(
        name="Rested", climb=1, sprint=1, flat=1, resistance=1, positioning=1,
        freshness=FRESHNESS_MAX - 5, recovery_rate=MAX_ATTRIBUTE,
    )

    changed = apply_weekly_recovery(exclude_ids=set())
    rider.refresh_from_db()

    assert changed == 1
    assert rider.freshness == FRESHNESS_MAX


def test_apply_weekly_recovery_skips_excluded_riders(db):
    racer = Rider.objects.create(
        name="Racer", climb=1, sprint=1, flat=1, resistance=1, positioning=1, freshness=60,
    )
    rested = Rider.objects.create(
        name="Rested", climb=1, sprint=1, flat=1, resistance=1, positioning=1, freshness=60,
    )

    changed = apply_weekly_recovery(exclude_ids={racer.pk})
    racer.refresh_from_db()
    rested.refresh_from_db()

    assert changed == 1
    assert racer.freshness == 60
    assert rested.freshness > 60

from __future__ import annotations

import random
from datetime import datetime, timezone as dt_timezone

import pytest
from django.apps import apps

from riders.development_squad import LEVELS
from riders.display import to_display_scale
from riders.models import ENGINE_ATTRIBUTES, DevelopmentSquad, Rider, RiderAttributeSnapshot
from riders.pricing import weekly_salary_for
from riders.services import _settle, attribute_ceilings, weekly_deltas
from riders.youth_intake import generate_youth_rider
from riders.youth_triage import (
    SPELL_WEEKS,
    NotYourProspect,
    ProspectListed,
    RosterFull,
    belongs_to,
    discard,
    free_places,
    graduate,
    graduates,
    in_squad,
    promote,
    release_graduates,
    squad_development_deltas,
)
from teams.models import Team

#: Game time, not wall clock — the same convention every riders/ test uses.
AT = datetime(2027, 3, 1, tzinfo=dt_timezone.utc)
LATER = datetime(2027, 4, 5, tzinfo=dt_timezone.utc)


@pytest.fixture
def squad(team) -> DevelopmentSquad:
    return DevelopmentSquad.objects.create(
        team=team, level=DevelopmentSquad.Level.REGIONAL, opened_at=AT,
    )


@pytest.fixture
def other_team(db) -> Team:
    return Team.objects.create(
        name="Team Beta", code="BET", primary_colour="#0000FF",
    )


def _squad_rider(squad, *, name="Youth") -> Rider:
    return Rider.objects.create(
        name=name,
        climb=30,
        sprint=25,
        flat=28,
        resistance=26,
        positioning=24,
        development_squad=squad,
        intake_at=AT,
    )


def _graduate(squad, *, name="Graduated") -> Rider:
    rider = _squad_rider(squad, name=name)
    rider.graduated_at = LATER
    rider.save(update_fields=["graduated_at", "updated_at"])
    return rider


# --- The partition: in_squad, graduates, free_places ---------------------


def test_in_squad_and_graduates_partition_the_squad(squad):
    in_place = _squad_rider(squad, name="Still Here")
    graduated = _graduate(squad)

    assert list(in_squad(squad)) == [in_place]
    assert list(graduates(squad)) == [graduated]


def test_free_places_counts_only_riders_in_the_squad(squad):
    """A graduate has left the squad and freed their place — that is the whole
    point of graduating them rather than deleting them."""
    for index in range(3):
        _squad_rider(squad, name=f"Youth {index}")
    _graduate(squad)

    assert in_squad(squad).count() == 3
    assert free_places(squad) == LEVELS[squad.level].places - 3


def test_free_places_is_zero_when_the_squad_is_full_and_never_negative(squad):
    for index in range(LEVELS[squad.level].places):
        _squad_rider(squad, name=f"Youth {index}")

    assert free_places(squad) == 0

    extra = _squad_rider(squad, name="One Too Many")
    assert free_places(squad) == 0
    assert extra.pk is not None


def test_free_places_is_the_levels_places_when_the_squad_is_empty(squad):
    assert free_places(squad) == LEVELS[squad.level].places


# --- belongs_to ----------------------------------------------------------


def test_belongs_to_is_true_for_a_roster_rider(team, rider):
    assert belongs_to(rider, team)


def test_belongs_to_is_true_for_a_graduate_of_the_team(team, squad):
    assert belongs_to(_graduate(squad), team)


def test_belongs_to_is_false_for_a_rider_still_in_the_squad(team, squad):
    """The market may only sell a graduate: listing someone mid-spell would
    let a squad be emptied for a profit instead of by a decision."""
    assert not belongs_to(_squad_rider(squad), team)


def test_belongs_to_is_false_for_another_teams_graduate(squad, other_team):
    assert not belongs_to(_graduate(squad), other_team)


# --- graduate ------------------------------------------------------------


def test_graduate_stamps_every_in_squad_rider_it_is_given(squad):
    first = _squad_rider(squad, name="First")
    second = _squad_rider(squad, name="Second")

    assert graduate([first.pk, second.pk], at=LATER) == 2

    for rider in (first, second):
        rider.refresh_from_db()
        assert rider.graduated_at == LATER
    assert in_squad(squad).count() == 0
    assert graduates(squad).count() == 2


def test_graduate_leaves_an_already_graduated_rider_alone(squad):
    """graduated_at is history and is never re-stamped."""
    already = _graduate(squad)

    assert graduate([already.pk], at=datetime(2027, 9, 1, tzinfo=dt_timezone.utc)) == 0

    already.refresh_from_db()
    assert already.graduated_at == LATER


def test_graduate_is_a_no_op_for_a_promoted_rider(team, squad, other_team):
    """A promoted rider has development_squad cleared, so the conditional
    UPDATE skips them rather than resurrecting a squad link."""
    promoted = _squad_rider(squad)
    promote(team, promoted.pk, at=LATER, roster_cap=30)

    assert graduate([promoted.pk], at=LATER) == 0

    promoted.refresh_from_db()
    assert promoted.development_squad_id is None
    assert promoted.graduated_at is None


# --- release_graduates ---------------------------------------------------


def test_release_graduates_stamps_unattached_since_and_clears_the_squad(squad):
    released = _graduate(squad)

    assert release_graduates([released.pk], at=LATER) == [released.pk]

    released.refresh_from_db()
    assert released.development_squad_id is None
    assert released.unattached_since == LATER


def test_release_graduates_ignores_riders_still_in_the_squad(squad):
    """Only graduates leave. A rider mid-spell stays put, because their place
    and their spell are the manager's to end with a decision."""
    staying = _squad_rider(squad)

    assert release_graduates([staying.pk], at=LATER) == []

    staying.refresh_from_db()
    assert staying.development_squad_id == squad.pk
    assert staying.unattached_since is None


def test_release_graduates_ignores_a_rider_who_already_left(team, squad):
    promoted = _squad_rider(squad)
    promote(team, promoted.pk, at=LATER, roster_cap=30)

    assert release_graduates([promoted.pk], at=LATER) == []

    promoted.refresh_from_db()
    assert promoted.team_id == team.pk
    assert promoted.unattached_since is None


# --- promote -------------------------------------------------------------


def test_promote_sets_the_team_and_clears_the_squad_in_one_save(team, squad):
    """Both fields move together: rider_not_on_roster_and_in_squad is checked
    per statement, so two saves would put the rider in two places at once."""
    youth = _squad_rider(squad)

    promoted = promote(team, youth.pk, at=LATER, roster_cap=30)

    assert promoted.team_id == team.pk
    assert promoted.development_squad_id is None


def test_promote_sets_the_salary_to_the_formula_value_at_that_moment(team, squad):
    youth = _squad_rider(squad)
    youth.weekly_salary = 1  # generation's value, not the promoted one

    promoted = promote(team, youth.pk, at=LATER, roster_cap=30)

    assert promoted.weekly_salary == weekly_salary_for(promoted)


def test_promote_stamps_joined_team_at(team, squad):
    youth = _squad_rider(squad)

    promoted = promote(team, youth.pk, at=LATER, roster_cap=30)

    assert promoted.joined_team_at == LATER
    assert promoted.unattached_since is None


def test_promote_works_on_a_graduate(team, squad):
    """A manager may also promote someone who has finished their spell."""
    graduated = _graduate(squad)

    promoted = promote(team, graduated.pk, at=LATER, roster_cap=30)

    assert promoted.team_id == team.pk
    assert promoted.development_squad_id is None
    assert promoted.graduated_at == LATER


def test_promote_refuses_at_the_roster_cap(team, squad, other_team):
    for index in range(3):
        Rider.objects.create(
            name=f"Roster {index}",
            team=team,
            climb=50,
            sprint=50,
            flat=50,
            resistance=50,
            positioning=50,
        )
    youth = _squad_rider(squad)

    with pytest.raises(RosterFull):
        promote(team, youth.pk, at=LATER, roster_cap=3)

    youth.refresh_from_db()
    assert youth.development_squad_id == squad.pk


def test_promote_refuses_another_teams_rider(team, squad, other_team):
    youth = _squad_rider(squad)

    with pytest.raises(NotYourProspect):
        promote(other_team, youth.pk, at=LATER, roster_cap=30)

    youth.refresh_from_db()
    assert youth.development_squad_id == squad.pk
    assert youth.team_id is None


def test_promote_refuses_a_rider_who_is_not_a_prospect(team, rider):
    with pytest.raises(NotYourProspect):
        promote(team, rider.pk, at=LATER, roster_cap=30)

    rider.refresh_from_db()
    assert rider.development_squad_id is None


# --- discard -------------------------------------------------------------


def test_discard_deletes_the_rider_and_their_snapshots(team, squad):
    youth = _squad_rider(squad)
    RiderAttributeSnapshot.objects.create(
        rider=youth, week=None,
        climb=3, sprint=2, flat=2, resistance=2, positioning=2,
    )

    discard(team, youth.pk)

    assert not Rider.objects.filter(pk=youth.pk).exists()
    assert not RiderAttributeSnapshot.objects.filter(rider_id=youth.pk).exists()


def test_discard_works_on_a_graduate(team, squad):
    graduated = _graduate(squad)

    discard(team, graduated.pk)

    assert not Rider.objects.filter(pk=graduated.pk).exists()


def test_discard_runs_the_check(team, squad):
    youth = _squad_rider(squad)
    seen = []

    # The pk is read inside the callback: delete() nulls it on the instance it
    # is called on, and the callback is handed that same instance.
    discard(team, youth.pk, check=lambda r: seen.append(r.pk))

    assert seen == [youth.pk]


def test_discard_is_rolled_back_when_the_check_raises(team, squad):
    youth = _squad_rider(squad)

    def refuse(_rider):
        raise ProspectListed("Your listing for this rider is still open.")

    with pytest.raises(ProspectListed):
        discard(team, youth.pk, check=refuse)

    assert Rider.objects.filter(pk=youth.pk).exists()


def test_discard_refuses_another_teams_rider(squad, other_team):
    youth = _squad_rider(squad)

    with pytest.raises(NotYourProspect):
        discard(other_team, youth.pk)

    assert Rider.objects.filter(pk=youth.pk).exists()


def test_squad_riders_have_no_race_history_dependents(team, squad):
    """The precondition that makes discard's plain delete() safe.

    A squad rider has never raced, so the only row anywhere that points at one
    is their attribute snapshot, which cascades. If a future ticket lets squad
    riders race, RaceResult and RaceSquadRider rows start pointing at them,
    this test fails, and discard has to be rethought rather than quietly
    cascade away a rider's history.

    Checked across every model in the project, not a hand-written list, so a
    new relation to Rider fails the test even if nobody thought to add it here.
    """
    youth = _squad_rider(squad)
    RiderAttributeSnapshot.objects.create(
        rider=youth, week=None,
        climb=3, sprint=2, flat=2, resistance=2, positioning=2,
    )

    pointing_at_youth = {
        f"{model._meta.label}.{field.name}"
        for model in apps.get_models()
        for field in model._meta.get_fields()
        if field.is_relation and field.auto_created is False
        and field.related_model is Rider
        and model.objects.filter(**{field.name: youth}).exists()
    }

    assert pointing_at_youth == {"riders.RiderAttributeSnapshot.rider"}

    discard(team, youth.pk)
    assert not Rider.objects.filter(pk=youth.pk).exists()



# --- squad development deltas --------------------------------------------


def _at_ceiling(rider: Rider) -> Rider:
    """`rider` with every attribute sitting exactly on its per-attribute
    ceiling. The values are left as floats because
    `squad_development_deltas` is a pure read of the instance and a ceiling is
    itself a float — rounding down would leave a gap the rider can still grow
    into, and rounding up would model a state no code path produces."""
    ceilings = attribute_ceilings(rider)
    for name in ENGINE_ATTRIBUTES:
        setattr(rider, name, ceilings[name])
    return rider


def _total_movement(rider: Rider) -> dict[str, float]:
    """One week of attribute movement as the growth pass would apply it: the
    age curve plus squad development, which is how `extra_deltas` is fed."""
    base = weekly_deltas(rider)
    extra = squad_development_deltas(rider)
    return {name: base[name] + extra[name] for name in ENGINE_ATTRIBUTES}


def test_squad_development_never_passes_ceiling(squad):
    """The min(gap, ...) cap. A rider already on their ceiling gets no growth
    at all — squad development is not a licence to exceed a hidden potential,
    whatever the floor says."""
    assert set(_total_movement(_at_ceiling(_squad_rider(squad))).values()) == {0.0}


def test_squad_development_stops_at_the_ceiling(squad):
    """One week's movement never closes more than the gap that is left, so no
    number of weeks can carry a rider past their ceiling."""
    rider = _squad_rider(squad)
    ceilings = attribute_ceilings(rider)

    for name, movement in _total_movement(rider).items():
        gap = ceilings[name] - getattr(rider, name)
        assert 0.0 <= movement <= gap


def test_squad_development_is_per_attribute_not_per_rider(squad):
    """A rider whose strongest attribute is maxed still has four others to
    grow, so the cap applies attribute by attribute."""
    rider = _at_ceiling(_squad_rider(squad))
    ceilings = attribute_ceilings(rider)
    for name, ceiling in ceilings.items():
        setattr(rider, name, ceiling * 0.5)
    maxed = max(ENGINE_ATTRIBUTES, key=lambda name: ceilings[name])
    setattr(rider, maxed, ceilings[maxed])

    movement = _total_movement(rider)

    assert movement[maxed] == 0.0
    assert any(value > 0 for value in movement.values())


def test_squad_development_tracks_potential(squad):
    """Two riders with identical attributes, different hidden potential. The
    one with more room develops faster — which is the whole clue the spec
    sells: growth rate is evidence of a ceiling the player never sees."""
    modest = _squad_rider(squad, name="Modest")
    roomy = _squad_rider(squad, name="Roomy")
    roomy.potential = min(100, modest.potential + 40)

    modest_movement = _total_movement(modest)
    roomy_movement = _total_movement(roomy)

    for name in ENGINE_ATTRIBUTES:
        assert roomy_movement[name] > modest_movement[name]


def test_every_youth_gains_over_a_spell(db):
    """The load-bearing test of the spec's "every rider ends their spell
    better than they arrived" promise.

    Simulated in memory — no database, no ticking — by applying fourteen
    weeks of the age curve plus squad development through the real `_settle`,
    so the settlement and rounding are the production ones and not a model of
    them.

    If this fails after a change to the squad constants, the *tuning* is
    wrong, not the test: the floor exists precisely to deliver this.
    """
    rng = random.Random(20270301)

    for level in sorted(LEVELS):
        for _ in range(2000):
            rider = generate_youth_rider(level, rng=rng)
            before = sum(
                to_display_scale(getattr(rider, name)) for name in ENGINE_ATTRIBUTES
            )
            debt = {}

            for _week in range(SPELL_WEEKS):
                base = weekly_deltas(rider)
                extra = squad_development_deltas(rider)
                for name in ENGINE_ATTRIBUTES:
                    value, remainder = _settle(
                        getattr(rider, name),
                        debt.get(name, 0.0),
                        base[name] + extra[name],
                    )
                    setattr(rider, name, value)
                    debt[name] = remainder

            after = sum(
                to_display_scale(getattr(rider, name)) for name in ENGINE_ATTRIBUTES
            )
            assert after > before, (
                f"a level {level} youth finished their spell with no visible "
                f"gain ({before} -> {after})"
            )

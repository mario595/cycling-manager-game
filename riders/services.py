"""Growth, decline and ageing: the age curve made live.

Pure functions over the Rider table. This module knows nothing about
seasons, weeks or the clock — `riders/` may not import `schedule/` or
`world/` (AGENTS.md). The caller (world.services.tick) decides when these
run and how many weeks to apply.
"""

from __future__ import annotations

from collections.abc import Iterable

from django.db import transaction
from django.db.models import F, Value
from django.db.models.functions import Greatest

from .departures import record_departures
from .display import to_display_scale
from .generation import PEAK_AGE_RANGE, SPECIALITY_PROFILES
from .field_level import current_field_factor
from .models import ENGINE_ATTRIBUTES, Departure, FieldLevel, Rider, RiderAttributeSnapshot
from .pricing import SALARY_REVIEW_THRESHOLD, solve_field_factor, weekly_salary_for

#: Fewer rostered riders than this and a season close leaves the field level
#: where it was: too small a field to say what the world pays (#166, spec's
#: *Rules and edge cases*). About four teams' worth.
FIELD_MIN_RIDERS = 40

#: Fraction of the remaining gap to its ceiling an attribute closes each
#: week, at maximum growth. Tuned so a young rider well below potential
#: gains 10-20 stored points across a twelve-week season — one to two
#: points on the floored 0-10 display scale (riders/display.py).
WEEKLY_GROWTH_FRACTION = 0.035

#: Stored points a rider at decline_rate 100 loses per week, per year past
#: peak_age (capped at DECLINE_YEARS_CAP). Tuned so a rider several years
#: past peak with an *average* decline rate (50) loses roughly one to two
#: display points across a season — the spec's promised band
#: (specs/rider-growth-and-decline.md, In scope #7) for the representative
#: case, not just the ceiling — rather than compounding without bound the
#: longer a rider remains active without an age-driven exit.
WEEKLY_DECLINE_UNIT = 0.006

#: Years past peak_age after which decline stops accelerating and holds
#: steady. Decline still "accelerates rather than being linear" for a
#: rider newly past their peak — the part of the curve where it matters
#: for a manager's decision — without an 18-years-past-peak veteran (the
#: model's age cap of 40 against the youngest possible peak_age of 22)
#: losing an implausible amount in one season.
DECLINE_YEARS_CAP = 3

#: Trainer effect per week per trainer skill point: `WEEKLY_TRAINING_UNIT *
#: trainer_skill * affinity`. Tuned so a trainer at 85 in their speciality
#: with a rider on affinity 1.2 gives `0.010 * 85 * 1.2 ≈ 1.02` stored
#: points a week — about twelve across a season, just over one display
#: level — while the same trainer on a 30-score off-speciality skill gives
#: ~0.36/week, clearly worse but never zero (the spec's "not a substitute"
#: framing from specs/weekly-training-focus-plan.md, Design decision 8).
WEEKLY_TRAINING_UNIT = 0.010

#: Stored points a finished race earns toward each attribute it trained.
#: "Much less" than trainer training: a rider racing most weeks gains ~2-3
#: points a season from racing alone, so trainers stay the main lever.
RACE_TRAINING_UNIT = 0.25

MIN_ATTRIBUTE = 1
MAX_ATTRIBUTE = 100

#: Freshness is stored 1-100 and shown 0-10 through the shared
#: to_display_scale — the same convention as every attribute and every
#: trainer skill. MAX is what a rider starts at and what rest returns
#: toward; FLOOR is the "low floor" the spec decided: a rider parked there
#: is a visible handicap, not a rounding error.
FRESHNESS_MAX = 100
FRESHNESS_FLOOR = 20

#: Freshness deducted when a rider finishes one race. The spec requires a
#: race to cost more than a week of rest returns (RECOVERY_MAX is 20), so
#: that racing every week nets negative and only a rotation across the
#: squad keeps a rider consistently near full.
RACE_FRESHNESS_COST = 25

#: Per-stage cost inside a stage race — less than one full race, so a full
#: tour still costs more than one race: a 7-stage tour costs 70, above one
#: race (25) but below wrecking a fresh rider (floor is 20). See
#: specs/archive/stage-races.md, Decisions taken.
STAGE_FRESHNESS_COST = 10

#: Weekly recovery range a hidden recovery_rate of 1-100 maps onto
#: linearly. At the average rate (~14/week), a rider racing every week
#: nets -11/week and reaches the floor from full in about seven weeks —
#: within a twelve-week season.
RECOVERY_MIN = 8
RECOVERY_MAX = 20

#: Attribute multiplier at FRESHNESS_FLOOR: a 20% cut, clearly visible in
#: results without making the rider a non-participant. Multiplier is
#: linear in freshness between FRESHNESS_FLOOR and FRESHNESS_MAX.
PENALTY_AT_FLOOR = 0.80

#: The age band every rider retires inside, 33 to 38 (MIN + SPAN). No rider
#: leaves the game young, and everyone eventually does; where in the band is
#: the rider's own business, derived from their traits. See retirement_age.
RETIREMENT_AGE_MIN = 33
RETIREMENT_AGE_SPAN = 5


def mark_team_change(riders: Iterable[Rider], *, team_now, at) -> None:
    """Stamp joined_team_at or unattached_since on every rider in
    `riders` to reflect a team change happening `at` (game time).

    `team_now` is the new team value (a Team, or None for a release) —
    every rider in the iterable is assumed to be changing to this same
    value in this same call, the same assumption claim_team's bulk
    operations already make.

    Does not touch `.team` itself (callers already save it — bulk_create,
    QuerySet.update(), or an individual .save()); it persists only the
    timing field(s) it stamps, via its own bulk_update.
    """
    riders = list(riders)
    if not riders:
        return
    if team_now is None:
        for rider in riders:
            rider.unattached_since = at
        Rider.objects.bulk_update(riders, ["unattached_since"])
    else:
        for rider in riders:
            rider.joined_team_at = at
            rider.unattached_since = None
        Rider.objects.bulk_update(riders, ["joined_team_at", "unattached_since"])


def retire_riders(rider_ids: Iterable[int], *, at) -> int:
    """Retire every still-active free agent in `rider_ids`, as of `at`
    (game time). Returns rows updated.

    One UPDATE whose WHERE re-checks team IS NULL and retired_at IS NULL —
    that re-check, not a lock, is what makes a concurrent sign_free_agent
    safe (plan D5). A rider signed or already retired in the meantime is
    silently skipped, never an error.
    """
    return Rider.objects.filter(
        pk__in=list(rider_ids), team__isnull=True, retired_at__isnull=True,
    ).update(retired_at=at)


def attribute_ceilings(rider: Rider) -> dict[str, float]:
    """Per-attribute ceilings preserving the rider's speciality shape.

    `potential` is one number but a rider has five attributes. Growing
    them all toward `potential` would flatten every rider into the same
    profile by their peak age and destroy speciality. Scaling by the same
    SPECIALITY_PROFILES weights that generated the rider keeps the shape
    the player already sees. See the plan's Design decision 3.
    """
    profile = SPECIALITY_PROFILES[rider.speciality]
    mean_weight = sum(profile.values()) / len(profile)
    return {
        name: rider.potential * (profile[name] / mean_weight)
        for name in ENGINE_ATTRIBUTES
    }


def weekly_deltas(rider: Rider, weeks: int = 1) -> dict[str, float]:
    """Fractional attribute movement over `weeks` weeks.

    Two halves joined at peak_age, not one polynomial — growth speed and
    decline speed are governed by different traits (potential vs
    decline_rate) and must be tunable apart. See Design decision 4.

    `weeks > 1` is exact, not iterated: closing fraction `f` of the gap
    `w` times closes `1 - (1-f)**w` of it. A four-week catch-up is one
    calculation, not four passes over the table (Design decision 7).
    """
    ceilings = attribute_ceilings(rider)
    deltas: dict[str, float] = {}

    if rider.age < rider.peak_age:
        # Geometric approach: fast while the gap is wide, tapering to
        # nothing as the rider nears both their ceiling and their peak.
        # This *is* the rising half of the parabola.
        closed = 1 - (1 - WEEKLY_GROWTH_FRACTION) ** weeks
        for name in ENGINE_ATTRIBUTES:
            gap = ceilings[name] - getattr(rider, name)
            # Clamped at zero: a young rider already at their ceiling
            # holds, never falls. Only the decline half lowers an
            # attribute (Design decision 10).
            deltas[name] = max(0.0, gap) * closed
    else:
        years_past = min(rider.age - rider.peak_age, DECLINE_YEARS_CAP)
        per_week = WEEKLY_DECLINE_UNIT * rider.decline_rate * years_past
        for name in ENGINE_ATTRIBUTES:
            deltas[name] = -per_week * weeks

    return deltas


def _settle(current: int, debt: float, delta: float) -> tuple[int, float]:
    """Fold `delta` into the accumulated `debt` and move out whole points.

    int() truncates toward zero, which is what both directions need: a
    debt of 2.7 yields +2 with 0.7 carried, and a debt of -2.7 yields -2
    with -0.7 carried. Using round() or floor() here would leak a point
    in one direction and is the likeliest bug in this file.
    """
    total = debt + delta
    whole = int(total)
    remainder = total - whole
    new_value = max(MIN_ATTRIBUTE, min(MAX_ATTRIBUTE, current + whole))
    # Clamped at the boundary: drop the carried remainder so it cannot
    # accumulate into a debt that never applies.
    if new_value != current + whole:
        remainder = 0.0
    return new_value, remainder


def is_injured(rider: Rider) -> bool:
    """Whether a rider sits out training this week.

    Always False until #41 (injuries) lands and gives this a real answer.
    A deliberate placeholder, not an oversight: the spec requires injured
    riders to be skipped, and #41 owns the data model that decides what
    "injured" means.
    """
    return False


def training_deltas(
    rider: Rider,
    *,
    focus: str | None,
    trainer_skill: int | None,
    raced_attributes: list[str],
) -> dict[str, float]:
    """This week's training movement for one rider, before settling.

    Trainer effect and race effect are additive (spec: "not a substitute
    for it"). Returns 0.0 for every attribute when the rider is injured.
    Never returns a negative value — training only ever raises.
    """
    if is_injured(rider):
        return {name: 0.0 for name in ENGINE_ATTRIBUTES}

    deltas = {name: 0.0 for name in ENGINE_ATTRIBUTES}
    if focus is not None and trainer_skill is not None:
        affinity = rider.training_affinity.get(focus, 1.0)
        deltas[focus] += WEEKLY_TRAINING_UNIT * trainer_skill * affinity
    for name in raced_attributes:
        deltas[name] += RACE_TRAINING_UNIT
    return deltas


def apply_weekly_growth(
    weeks: int = 1,
    extra_deltas: dict[int, dict[str, float]] | None = None,
) -> list[dict]:
    """Move every rider along their age curve, plus any extra per-rider
    deltas, settling both through one growth_debt ledger.

    `extra_deltas` is {rider_id: {attribute: delta}}. Returns one record
    per rider whose *displayed* value changed, so the caller can build a
    training report without re-reading the table.
    """
    records: list[dict] = []
    riders_to_update: list[Rider] = []
    for rider in Rider.objects.active():
        deltas = weekly_deltas(rider, weeks=weeks)
        extra = extra_deltas.get(rider.pk, {}) if extra_deltas else {}
        debt = dict(rider.growth_debt)
        for name in ENGINE_ATTRIBUTES:
            current = getattr(rider, name)
            new_value, remainder = _settle(
                current, debt.get(name, 0.0), deltas[name] + extra.get(name, 0.0),
            )
            debt[name] = remainder
            if new_value != current:
                setattr(rider, name, new_value)
                before = to_display_scale(current)
                after = to_display_scale(new_value)
                if after != before:
                    records.append({
                        "rider_id": rider.pk,
                        "rider_name": rider.name,
                        "team_id": rider.team_id,
                        "attribute": name,
                        "from": before,
                        "to": after,
                    })
        rider.growth_debt = debt
        riders_to_update.append(rider)

    Rider.objects.bulk_update(riders_to_update, [*ENGINE_ATTRIBUTES, "growth_debt"])
    return records


def retirement_age(rider: Rider) -> int:
    """The age this rider retires at — derived, never stored.

    A pure function of the two immutable hidden traits set at generation
    (`peak_age` and `decline_rate`), so it is stable for a rider's whole
    life and needs no backfill for existing rows. A late peaker and a slow
    decliner play on; a fast decliner goes sooner — the weighting (3 for
    peak age, 2 for decline rate) makes peak age the bigger driver, so a
    player watching many careers can learn "late bloomers last". The result
    never leaves the RETIREMENT_AGE_MIN..MIN+SPAN band, whichever extreme
    the traits take (see riders/README.md, *Retiring by age*).
    """
    low, high = PEAK_AGE_RANGE
    peak_share = min(1.0, max(0.0, (rider.peak_age - low) / (high - low)))
    staying_power = (100 - rider.decline_rate) / 99
    return RETIREMENT_AGE_MIN + round(3 * peak_share + 2 * staying_power)


def is_due_to_retire(rider: Rider) -> bool:
    """Whether this rider has reached their retirement age.

    False for a retired rider whatever their age, which is what lets the
    API mark riders without ever tagging one who is already gone.
    """
    return rider.retired_at is None and rider.age >= retirement_age(rider)


def retire_due_riders(*, at) -> list[int]:
    """Retire every active rider whose age has reached their retirement
    age, as of `at` (game time). Clears the team and development_squad and
    stamps retired_at in one UPDATE so retired_rider_has_no_team and
    retired_rider_not_in_squad both hold row by row. Returns the ids
    actually retired. Pure with respect to seasons: world decides when.

    Clearing development_squad here is a backstop for #34 (no squad rider
    can reach the retirement window under this ticket alone), not a path
    exercised today — without it a future promotion bug would turn into a
    crashed season close instead of an IntegrityError at the point it
    actually happened."""
    due = [
        rider.pk
        for rider in Rider.objects.active().only("id", "age", "peak_age", "decline_rate")
        if rider.age >= retirement_age(rider)
    ]
    if due:
        # One transaction for the read, the UPDATE and the record: the
        # UPDATE clears `team`, so who each rider left is read first, and a
        # departure must exist exactly when the retirement does (#158).
        # Only roster riders are recorded; clearing a squad is the backstop
        # described above, not a departure anyone can see.
        with transaction.atomic():
            leaving = list(
                Rider.objects.select_for_update()
                .filter(pk__in=due, retired_at__isnull=True, team__isnull=False)
                .only("id", "name", "speciality", "age", "team_id")
            )
            Rider.objects.filter(pk__in=due, retired_at__isnull=True).update(
                team=None, development_squad=None, retired_at=at,
            )
            record_departures(
                leaving,
                team_by_rider={rider.pk: rider.team_id for rider in leaving},
                kind=Departure.Kind.RETIRED,
                at=at,
            )
    return due


def advance_ages() -> int:
    """Advance every rider's age by one, capped at the model's maximum.

    A rider at the cap holds there. The world retires riders at a season
    close *before* calling this, so a rider leaves the game at the age the
    player last saw rather than ageing into and out of it in one step —
    see retire_due_riders above. One UPDATE statement via F(), not a
    per-row loop.
    """
    return Rider.objects.active().filter(age__lt=40).update(age=F("age") + 1)


def measure_field_level(riders: list[Rider]) -> float:
    """Solve and record the field's pay level from `riders`' rostered ones
    (team set: free agents, development squad youth and retired riders are
    not the field), returning the factor now in force.

    A field under FIELD_MIN_RIDERS records nothing and keeps the current
    factor. Otherwise one FieldLevel row is appended (#166)."""
    field = [r for r in riders if r.team_id is not None]
    if len(field) < FIELD_MIN_RIDERS:
        return current_field_factor()
    factor = solve_field_factor(field)
    FieldLevel.objects.create(factor=factor)
    return factor


def reprice_all() -> list[dict]:
    """Recompute every rider's weekly_salary from riders.pricing and save.

    Returns one record per rider whose salary moved by at least
    SALARY_REVIEW_THRESHOLD: {"rider_id", "rider_name", "team_id",
    "from", "to"} in whole credits. Every rider's salary is written
    regardless of the threshold; the threshold filters only what is
    returned (plan D4).

    Since #166 it first measures the field (measure_field_level) and prices
    every rider against it, so the field's average wage stays level as the
    world gets stronger.

    Pure with respect to time, like advance_ages() and
    apply_weekly_growth(): this app knows nothing about seasons or the
    clock. world.services.tick() decides when to call it.
    """
    riders = list(Rider.objects.active().only(
        "id", "name", "team_id", "speciality", "age",
        "weekly_salary", *ENGINE_ATTRIBUTES,
    ))
    factor = measure_field_level(riders)

    changes = []
    updated = []
    for rider in riders:
        new_salary = weekly_salary_for(rider, factor)
        if new_salary == rider.weekly_salary:
            continue
        if abs(new_salary - rider.weekly_salary) >= SALARY_REVIEW_THRESHOLD:
            changes.append({
                "rider_id": rider.pk,
                "rider_name": rider.name,
                "team_id": rider.team_id,
                "from": rider.weekly_salary,
                "to": new_salary,
            })
        rider.weekly_salary = new_salary
        updated.append(rider)

    Rider.objects.bulk_update(updated, ["weekly_salary"], batch_size=500)
    return changes


def freshness_multiplier(freshness: int) -> float:
    """Attribute scaling for a rider at this freshness.

    1.0 at FRESHNESS_MAX, PENALTY_AT_FLOOR at FRESHNESS_FLOOR, linear
    between. Input is clamped, so a value outside the range (only
    reachable via admin) can never scale attributes *up*.
    """
    clamped = max(FRESHNESS_FLOOR, min(FRESHNESS_MAX, freshness))
    return PENALTY_AT_FLOOR + (
        (1 - PENALTY_AT_FLOOR)
        * (clamped - FRESHNESS_FLOOR)
        / (FRESHNESS_MAX - FRESHNESS_FLOOR)
    )


def recovery_amount(rider: Rider) -> int:
    """Freshness this rider regains in a week of rest.

    Maps recovery_rate 1-100 onto RECOVERY_MIN..RECOVERY_MAX linearly.
    """
    fraction = (rider.recovery_rate - MIN_ATTRIBUTE) / (MAX_ATTRIBUTE - MIN_ATTRIBUTE)
    return round(RECOVERY_MIN + fraction * (RECOVERY_MAX - RECOVERY_MIN))


def apply_race_cost(rider_ids: list[int], *, cost: int = RACE_FRESHNESS_COST) -> int:
    """Deduct `cost` from each rider, floored at FRESHNESS_FLOOR. One UPDATE
    via Greatest/F, not a per-row loop. Returns the number of rows updated.

    `cost` defaults to RACE_FRESHNESS_COST for a one-day race;
    `racing.services.simulate_race` passes STAGE_FRESHNESS_COST for a stage
    — see specs/archive/stage-races.md.
    """
    return Rider.objects.filter(pk__in=rider_ids).update(
        freshness=Greatest(
            Value(FRESHNESS_FLOOR),
            F("freshness") - cost,
        )
    )


def apply_weekly_recovery(*, exclude_ids: set[int]) -> int:
    """Restore one week of freshness to every rider not in exclude_ids,
    capped at FRESHNESS_MAX. Returns rows updated.
    """
    to_update: list[Rider] = []
    for rider in Rider.objects.active().exclude(pk__in=exclude_ids):
        restored = min(FRESHNESS_MAX, rider.freshness + recovery_amount(rider))
        if restored != rider.freshness:
            rider.freshness = restored
            to_update.append(rider)
    Rider.objects.bulk_update(to_update, ["freshness"])
    return len(to_update)


def _display_values(rider: Rider) -> dict[str, int]:
    """This rider's five attributes on the 0-10 scale the player sees."""
    return {name: to_display_scale(getattr(rider, name)) for name in ENGINE_ATTRIBUTES}


def record_initial_snapshots(riders: list[Rider]) -> int:
    """Baseline snapshot (week=None) for each newly created rider.

    Call immediately after Rider.objects.bulk_create, with the list
    bulk_create returned — its instances carry the primary keys the
    unsaved list passed to generate_roster/generate_rider does not.
    Returns the number of rows written.
    """
    rows = [
        RiderAttributeSnapshot(rider=rider, week=None, **_display_values(rider))
        for rider in riders
    ]
    RiderAttributeSnapshot.objects.bulk_create(rows)
    return len(rows)


def record_week_snapshots(rider_ids: list[int], *, week_id: int) -> int:
    """One snapshot per rider whose displayed value moved this week.

    `week_id` is a plain int, not a Week: riders/ may not import schedule/
    (AGENTS.md). ignore_conflicts guards the (rider, week) unique constraint
    the same way _write_training_reports tolerates a duplicate report,
    without needing a per-row transaction. Returns the number of rows
    attempted (bulk_create with ignore_conflicts does not report how many
    were actually inserted).
    """
    riders = Rider.objects.filter(pk__in=rider_ids)
    rows = [
        RiderAttributeSnapshot(rider=rider, week_id=week_id, **_display_values(rider))
        for rider in riders
    ]
    RiderAttributeSnapshot.objects.bulk_create(rows, ignore_conflicts=True)
    return len(rows)

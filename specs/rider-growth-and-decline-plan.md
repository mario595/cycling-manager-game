# Rider growth and decline — Implementation Plan

**Spec:** `specs/rider-growth-and-decline.md` · **Issue:** #58 · **Status:** proposed
**Apps touched:** `riders/`, `schedule/`, `world/`

## Context you need

Riders already carry everything this feature reads. `riders/models.py` defines
`Rider` with five engine attributes (`climb`, `sprint`, `flat`, `resistance`,
`positioning`, each 1-100), a visible `age` (18-40), and three hidden traits
this ticket makes live for the first time: `potential` (1-100), `peak_age`
(22-34) and `decline_rate` (1-100). They are stored, validated and generated
(`riders/generation.py`) but **nothing reads them today** — see
`riders/README.md`, *Visible vs hidden*.

`riders/generation.py` holds `SPECIALITY_PROFILES`: a per-speciality weighting
of the five attributes where each row sums to ~5.0. A Climber's `climb` weight
is 1.45 and their `sprint` weight 0.55. Generation multiplies `quality` by
these weights to roll a rider's starting attributes. **This plan reuses that
same table as the shape growth must preserve** — see Design decision 3.

`riders/display.py`'s `to_display_scale(value)` maps stored 1-100 onto the
player's 0-10 scale. **It floors (`value // 10`), it does not round** —
`riders/README.md` currently says `round(value / 10)` and is stale on this
point; the code is authoritative and this plan is tuned against flooring. A
stored move of 10 is worth exactly one display point.

`world/services.py`'s `tick()` is the only entry point that processes due
work. It reads `now()` once, threads it through as `at`, then: calls
`schedule.services.process_transitions(at)`, reclaims interrupted races,
claims due races under a row lock, and executes them outside the lock.
`world/README.md` documents the clock discipline and the exactly-once
guarantee.

`schedule/models.py` has `Season`, `Week` (twelve rows per season, each with
`starts_at`/`ends_at`) and `SeasonTransition` — an exactly-once record of a
season boundary being crossed, guaranteed by a `UniqueConstraint` on
`(season, kind)`, with `IntegrityError` caught per-row. **`Week` rows exist
but nothing ever fires when one opens.** That hook is this ticket's to build;
`schedule/README.md`'s *Exactly-once* section is the pattern to copy.

Dependency direction (`AGENTS.md`): `riders -> core, teams`, `schedule ->
core`, and `world/` may import everything while nothing may import `world/`.
`riders/` must not import `schedule/` or `world/`, which is why the growth
service takes its inputs as plain arguments (Design decision 6).

## Goal

When this is done:

- Every `Rider` in the database — rostered or free agent — has their five
  attributes adjusted once per game week along a curve derived from their own
  `potential`, `peak_age` and `decline_rate`.
- That curve is an inverted parabola in age: fast growth while young and below
  potential, negligible movement through the prime, decline past `peak_age`.
- Growth preserves speciality shape — a Climber's `climb` approaches a higher
  ceiling than their `sprint`.
- Every rider's `age` advances by one when a season closes.
- The weekly step and the ageing step each happen exactly once per week and
  per season respectively, even when ticks are missed, duplicated or run
  concurrently.
- No new API field, serializer change or frontend work exists.

## Design decisions (settled — implement these, do not substitute)

**1. A new `WeekTransition` model in `schedule/`, mirroring `SeasonTransition`.**
The weekly hook needs the same exactly-once guarantee season boundaries have,
for the same reason: a tick that runs three weeks late must apply three weeks
of growth, not one, and two concurrent ticks must apply one. Copy the shape
exactly — a `UniqueConstraint`, a per-row `transaction.atomic()`, and
`IntegrityError` caught and treated as success.

**Do not** derive "has this week been processed?" from a timestamp on `Rider`
(e.g. `last_grown_at`). That puts the exactly-once guarantee on 600 rows
instead of one, and a partial failure mid-population leaves the world in a
state where some riders have advanced and others have not, with nothing
recording which. The transition row is the ledger; rider updates are its
effect.

**2. Ageing hangs off the existing `SeasonTransition`, not a new mechanism.**
`process_transitions()` already writes a `CLOSED` row exactly once per season.
Ageing is triggered from the list of `CLOSED` transitions that call returns.
`schedule/README.md` says that row "is the hook later features will attach
to" — this is the first feature to attach to it, as designed.

**3. Growth targets a per-attribute ceiling derived from `SPECIALITY_PROFILES`,
not `potential` directly.** This is the load-bearing decision of the whole
feature. `potential` is a single number; a rider has five attributes. Growing
every attribute toward `potential` makes every rider converge on a flat
profile by their peak age, which destroys speciality — a Climber at 30 would
have the same sprint as a Sprinter.

Instead, each attribute's ceiling is `potential * (profile_weight / mean
profile weight)`, clamped to 1-100. Since every `SPECIALITY_PROFILES` row sums
to ~5.0 over five attributes, the mean weight is ~1.0, so a Climber with
potential 80 has a climb ceiling of ~116 (clamped to 100) and a sprint ceiling
of ~44. The shape is preserved because it is the *same table* that produced
the rider's starting attributes.

**Do not** normalise so the ceilings sum to five times potential, and **do
not** rescale `SPECIALITY_PROFILES` — `riders/generation.py` documents that
changing a row's total is a balance decision, and this feature must read that
table without altering it.

**4. The curve is computed as two separate halves joined at `peak_age`,
not as a literal quadratic.** The spec describes an inverted parabola, and
that is the right mental model, but implementing it as one polynomial in age
ties growth speed and decline speed to the same coefficient — and
`decline_rate` exists precisely so they differ per rider.

Below `peak_age`: the attribute moves a fraction of its remaining gap to its
ceiling each week. This is geometric approach, which naturally produces the
parabola's shape — fast when the gap is large (young, far below ceiling),
tapering to nothing as the rider nears both their ceiling and their peak.

At or above `peak_age`: the attribute falls by an amount scaled by
`decline_rate` and by how many years past peak the rider is, so decline
accelerates rather than being linear.

The flat middle is not a third case and needs no code: a rider near their
peak age is by construction near their ceiling (the growth half has been
pulling them there for years), so the remaining gap is small and the weekly
movement rounds to nothing.

**5. Fractional movement accumulates in a per-rider remainder, so that
sub-1.0 weekly steps are not lost to rounding.** A week's growth is often
0.6 of a stored point. Rounding each week independently either discards it
entirely (`round(0.6) == 1` is wrong the other way — twelve weeks would give
twelve points, far too fast) or loses it (truncating to 0 means nothing ever
moves).

Store the fractional part in a new hidden `growth_debt` JSONField on `Rider`:
`{attribute_name: float}`. Each week, add the computed delta to the debt,
move the whole-number part into the attribute, keep the remainder. This makes
twelve weeks of 0.6 add up to 7 stored points, which is the intended
magnitude.

**Do not** convert the attributes to floats. The engine validates 1-100
integers (`race_engine/README.md`), `_attribute_field` enforces it, and the
six bundled courses are balanced against that range.

**6. The growth calculation lives in `riders/services.py` as a pure function
over plain arguments; `world/services.py` orchestrates it.** `riders/` may
not import `schedule/` or `world/` (`AGENTS.md`). So `riders.services` exposes
`apply_weekly_growth(weeks=1)` and `advance_ages()`, which know nothing about
seasons, weeks or the clock — the tick passes in how many weeks to apply.

**Do not** have `riders/` read `world.services.now()` or query `Week`.

**7. Catch-up applies every missed week's growth, in one batched calculation,
not one pass per week.** If a tick runs after four unprocessed weeks, four
`WeekTransition` rows are written and growth is applied with `weeks=4`. The
geometric approach makes this exact rather than approximate: applying a
fraction `f` of the gap four times is `1 - (1-f)**4` of the gap, which the
function computes directly.

**Do not** loop the whole population four times — a 600-rider world would do
2,400 row updates for one late tick.

**8. Ageing happens before growth in the same tick.** A rider who turns 33 at
a season boundary should be evaluated against the new age immediately.
`process_transitions()` already runs first in `tick()`, which makes this
ordering natural.

**9. `growth_debt` is hidden and never serialized**, like every other hidden
trait — `riders/README.md`'s rule. It is an implementation detail of the
curve, not a game concept.

**10. A rider at or above their per-attribute ceiling before `peak_age` does
not move.** The growth half moves toward the ceiling; a negative gap is
clamped to zero, not applied as a fall. Only the decline half (past
`peak_age`) ever lowers an attribute. This matches the spec's rule that a
young rider already at their ceiling does not fall just for being there.

## Data model

### `riders/models.py` — one new field on `Rider`

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `growth_debt` | `JSONField` | not null, blank=True | `dict` (callable) | Hidden. `{attribute_name: float}` over `ENGINE_ATTRIBUTES`. Accumulated fractional growth not yet applied to the integer attribute. Missing keys read as `0.0`. |

**Deviation from the table above:** `blank=True`, not `blank=False` as originally planned. `generate_rider()` never sets `growth_debt` (there is nothing to roll — a new rider starts with none), so it is left at its `{}` default; `full_clean()` then rejects an empty `JSONField` unless `blank=True`. `training_affinity` avoids this only because `generate_rider` always fills it with a non-empty dict. Caught by `riders/tests/test_generation.py::test_generated_rider_is_valid`, which already existed and calls `full_clean()` on 200 generated riders.

No index, no constraint — it is read and written only by the rider that owns
it, always by primary key.

Migration: `riders/migrations/0005_rider_growth_debt.py` (`makemigrations
riders`). Additive with a default, so no data migration and no backfill —
existing rows get `{}` and the service treats a missing key as `0.0`.

Update the `Rider` class docstring's list of hidden traits to include
`growth_debt`, and `age`'s `help_text` (currently "Static as of #57. Advanced
once per season by #58.") to say it is now advanced at each season close.
Same for `potential`, `peak_age` and `decline_rate`, whose help text all say
"once #58 lands".

### `schedule/models.py` — one new model

`WeekTransition`, mirroring `SeasonTransition`:

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `week` | `ForeignKey("schedule.Week", on_delete=CASCADE, related_name="transitions")` | not null | — | The week that opened. |
| `occurred_at` | `DateTimeField` | not null | — | Game time — the week's own `starts_at`, never the `at` the tick noticed it. Same rule as `SeasonTransition.occurred_at`. |
| `recorded_at` | `DateTimeField(auto_now_add=True)` | not null | — | Real time. |

`Meta`: `ordering = ["-occurred_at"]`, and
`constraints = [UniqueConstraint(fields=["week"], name="unique_week_transition")]`.

A `TimeStampedModel` is not used — `SeasonTransition` uses one, but it carries
both `kind` and a season; a week transition has exactly one kind, so
`recorded_at` alone matches `Week`'s own precedent of not being a
`TimeStampedModel` ("created only alongside its season and never touched
again").

Migration: `schedule/migrations/0002_weektransition.py`.

### `world/models.py` — two new counters on `TickRun`

| Field | Type | Default | Notes |
|---|---|---|---|
| `weeks_processed` | `PositiveSmallIntegerField` | `0` | How many week boundaries this tick recorded. |
| `riders_aged` | `PositiveIntegerField` | `0` | How many riders had their age advanced. |

Matches the existing `seasons_opened` / `seasons_closed` pattern — a tick must
be able to answer "did anything run, and did it work?" (`TickRun`'s docstring).

Migration: `world/migrations/000N_tickrun_growth_counters.py`.

## riders/services.py (new file)

```python
"""Growth, decline and ageing: the age curve made live.

Pure functions over the Rider table. This module knows nothing about
seasons, weeks or the clock — `riders/` may not import `schedule/` or
`world/` (AGENTS.md). The caller (world.services.tick) decides when these
run and how many weeks to apply.
"""

from __future__ import annotations

from .generation import SPECIALITY_PROFILES
from .models import ENGINE_ATTRIBUTES, Rider

#: Fraction of the remaining gap to its ceiling an attribute closes each
#: week, at maximum growth. Tuned so a young rider well below potential
#: gains 10-20 stored points across a twelve-week season — one to two
#: points on the floored 0-10 display scale (riders/display.py).
WEEKLY_GROWTH_FRACTION = 0.035

#: Stored points a rider at decline_rate 100 loses per week, per year past
#: peak_age. Tuned so a rider two years past peak with an average decline
#: rate loses roughly a display point across a season.
WEEKLY_DECLINE_UNIT = 0.010

MIN_ATTRIBUTE = 1
MAX_ATTRIBUTE = 100


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
```

`weekly_deltas(rider, weeks)` returns `dict[str, float]` — the fractional
change per attribute over `weeks` weeks. This is the function that holds the
curve, and it is where the natural first attempt is wrong, so it gets real
code:

```python
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
        years_past = rider.age - rider.peak_age
        per_week = WEEKLY_DECLINE_UNIT * rider.decline_rate * years_past
        for name in ENGINE_ATTRIBUTES:
            deltas[name] = -per_week * weeks

    return deltas
```

`apply_weekly_growth(weeks=1) -> int` iterates every `Rider`, computes deltas,
adds them into `growth_debt`, moves whole points into the attribute, clamps to
1-100, and `bulk_update`s. Returns the number of riders whose stored
attributes actually changed.

The debt mechanics — the part that is easy to get subtly wrong:

```python
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
```

`advance_ages() -> int` bumps every rider's `age` by one, clamped to the
model's `MaxValueValidator(40)` ceiling, and returns how many rows changed.
Use `F("age") + 1` with a `filter(age__lt=40)` so it is one UPDATE statement
rather than a per-row loop — a rider at 40 stays at 40 until retirement (#42)
exists.

## schedule/services.py

Add `process_week_transitions(at) -> list[WeekTransition]`, alongside the
existing `process_transitions`, following it exactly:

```python
def process_week_transitions(at: datetime) -> list[WeekTransition]:
    """Record every week boundary opened at or before `at` that has not
    been recorded yet, oldest first.

    Exactly-once comes from the unique constraint on `week`, NOT from the
    exclude() below — that only keeps the common case cheap. A concurrent
    tick loses the race at the INSERT and moves on. One atomic() per
    create, never one around the loop: an IntegrityError poisons the
    enclosing transaction in Django. Same shape as process_transitions;
    see schedule/README.md, *Exactly-once*.
    """
```

The queryset is `Week.objects.filter(starts_at__lte=at).exclude(
transitions__isnull=False).order_by("starts_at")`, and `occurred_at` is the
week's own `starts_at`.

## world/services.py

`tick()` gains one step between transitions and race claiming:

```python
    transitions = process_transitions(at)

    # Ageing before growth, so a rider who turned 33 at this boundary is
    # evaluated against their new age this same tick (Design decision 8).
    closed = [t for t in transitions if t.kind == SeasonTransition.Kind.CLOSED]
    riders_aged = advance_ages() * len(closed) and advance_ages()
```

That last line is deliberately **not** what to write — see Risks. The correct
form:

```python
    riders_aged = 0
    for _ in closed:
        riders_aged = advance_ages()

    weeks = process_week_transitions(at)
    if weeks:
        apply_weekly_growth(weeks=len(weeks))
```

Growth runs before race claiming, so a race processed in the same tick is
raced by riders who have already had that week's movement applied. Both new
counters are recorded on the `TickRun` row created just below.

Growth and ageing are **not** inside the claim transaction — they are
independent of race claiming and holding a lock across a full-table update
would extend exactly the starvation window `world/README.md` warns about.

## Work items

### W1 — `schedule/`: the week transition record — done
Add `WeekTransition` to `schedule/models.py`, its migration, and
`process_week_transitions(at)` to `schedule/services.py`. Nothing calls it
yet.
**Test:** `schedule/tests/test_services.py` —
`test_a_week_transition_is_recorded_once_per_week`,
`test_a_late_tick_records_every_missed_week`,
`test_recording_the_same_week_twice_writes_one_row`,
`test_occurred_at_is_the_weeks_own_start_not_the_tick_time`.
**Load-bearing:** the duplicate test must assert on row *count*, not on the
return value — the guarantee is the constraint, not the `exclude()`.

### W2 — `riders/`: the `growth_debt` field — done (see note)
Add the field, its migration, and update the `Rider` docstring plus the
`help_text` on `age`, `potential`, `peak_age` and `decline_rate` (all of
which currently say "once #58 lands").
**Test:** `riders/tests/test_models.py` —
`test_growth_debt_defaults_to_an_empty_dict`.

### W3 — `riders/services.py`: ceilings and the curve — done
Add the new module with `attribute_ceilings`, `weekly_deltas` and the tuning
constants. Pure functions on unsaved riders — no database writes yet.
**Test:** new `riders/tests/test_services.py` —
`test_a_climbers_climb_ceiling_exceeds_their_sprint_ceiling`,
`test_a_young_rider_below_potential_grows`,
`test_a_rider_past_peak_age_declines`,
`test_decline_accelerates_with_years_past_peak`,
`test_a_higher_decline_rate_falls_faster`,
`test_a_rider_at_their_ceiling_below_peak_does_not_move`,
`test_four_weeks_of_growth_equals_four_applications_of_one_week`.
**Load-bearing:** the last test is what proves the catch-up shortcut in
Design decision 7 is exact, not approximate. Assert to a tolerance of 1e-9.

### W4 — `riders/services.py`: applying growth and ageing — done
Add `_settle`, `apply_weekly_growth(weeks)` and `advance_ages()`.
**Test:** `riders/tests/test_services.py` —
`test_fractional_growth_accumulates_across_weeks_instead_of_being_lost`,
`test_attributes_never_leave_the_1_100_range`,
`test_debt_does_not_accumulate_once_an_attribute_is_clamped`,
`test_ageing_advances_every_rider_including_free_agents`,
`test_ageing_stops_at_the_model_maximum`.
**Load-bearing:** the first test is the whole reason `growth_debt` exists —
apply twelve single weeks to a rider whose weekly delta is under 1.0 and
assert the attribute moved by roughly 12× the weekly amount, not by 0 and
not by 12.

### W5 — `world/services.py`: wire it into the tick — done
Call `process_week_transitions` and `apply_weekly_growth` / `advance_ages`
from `tick()`, and record the two new `TickRun` counters (with their
migration).
**Test:** `world/tests/test_services.py` —
`test_a_tick_applies_one_week_of_growth`,
`test_a_tick_three_weeks_late_applies_three_weeks_of_growth`,
`test_two_ticks_in_the_same_week_apply_growth_once`,
`test_riders_age_when_a_season_closes`,
`test_riders_do_not_age_mid_season`,
`test_growth_is_applied_before_races_are_simulated`.
**Load-bearing:** `test_two_ticks_in_the_same_week_apply_growth_once` is the
regression that catches a broken exactly-once guarantee — the failure mode
this feature is most likely to ship with.

### W6 — documentation
See below. Its own commit.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6, and each leaves the suite green.

W1 and W2 are independent schema additions and could be done either way
round; W1 first because it is the piece with a correctness guarantee to
prove, and proving it against an untouched `riders/` keeps the failure
surface small.

W3 before W4 because the curve is pure arithmetic testable without a
database — get the shape right against unsaved `Rider()` instances before
any row is written. If the tuning constants turn out wrong, it is a
one-line change at this point and a data problem later.

W4 before W5 because `apply_weekly_growth` is the piece with the subtle
rounding, and it is far easier to debug called directly from a test than
through a tick.

W5 last: it is the only item that changes existing behaviour, and by then
everything it calls is proven.

**Commit after each work item.** W5 is the one that makes the feature live —
commit W1-W4 before starting it, so a revert of the wiring does not take the
tested machinery with it.

## Documentation update (required, not optional)

**`riders/README.md`**
- *Visible vs hidden*: add `growth_debt` to the hidden list. Update the
  bullet saying `potential`, `peak_age`, `decline_rate` "become live in
  growth/decline (#58)" to say they are live now, and describe what each
  does.
- **Fix the stale display-scale claim.** The section says
  `to_display_scale` uses `round(value / 10)`; the code floors
  (`value // 10`). Correct it, and note that this feature's magnitudes are
  tuned against flooring.
- New section, *The age curve*: the two halves, why the ceilings come from
  `SPECIALITY_PROFILES`, why `growth_debt` exists, and that `riders/` must
  not learn about weeks or the clock.
- *Future work*: note that decline has no floor and no retirement — #42.

**`schedule/README.md`**
- New section, *Week transitions*, alongside *Exactly-once*: what
  `WeekTransition` is, that it is the weekly counterpart of
  `SeasonTransition`, and that `occurred_at` is the week's own `starts_at`.
- Update *The transition hook ships empty* — it no longer does. Season close
  now advances every rider's age.

**`world/README.md`**
- *How a tick works*: add the new step between transitions and claiming, and
  say why growth sits outside the claim transaction.
- The numbered list currently runs 0-2; it becomes 0-3.

**`AGENTS.md`**
- The `riders/` row says "Growth/decline (#58) and freshness (#59) still to
  come." Drop the #58 half.

## Verification

```bash
.venv/bin/python -m pytest
```

Then prove it end to end against a real database, which unit tests cannot:

```bash
export GAME_CLOCK_CLASS=world.clocks.MockClock
.venv/bin/python manage.py load_season seasons/season-1.example.json
.venv/bin/python manage.py mock_clock set 2027-03-01T00:00:00
.venv/bin/python manage.py shell -c "
from riders.models import Rider
r = Rider.objects.filter(age__lt=24).order_by('potential').last()
print(r.pk, r.name, r.age, r.peak_age, r.potential, r.climb, r.sprint)
"
```

Note the id and values. Then advance a full season a week at a time and
re-read the same rider:

```bash
for i in $(seq 1 12); do
  .venv/bin/python manage.py mock_clock advance --by 7d
  .venv/bin/python manage.py tick
done
```

**What proves it:** the young rider's `climb` has risen by roughly 10-20
stored points, their `sprint` by visibly less (shape preserved), and `age`
by exactly 1 — not 12. A rider selected with `age__gt=peak_age` has fallen.

**The likeliest failure mode is growth being applied more than once per
week** — through a missed uniqueness check, or through `mock_clock advance`
crossing two week boundaries and the loop double-counting. The specific check:

```bash
.venv/bin/python manage.py shell -c "
from schedule.models import Week, WeekTransition
print('weeks elapsed:', Week.objects.count(), 'transitions:', WeekTransition.objects.count())
"
```

Transitions must never exceed elapsed weeks. Then run `manage.py tick` twice
in a row without moving the clock and confirm the rider's attributes are
**identical** before and after the second tick — a passing unit test that
mocks the transition query could not catch this, which is why it is here.

## Risks

| Risk | Mitigation |
|---|---|
| Growth applied per-tick instead of per-week — cron runs hourly, so this is 168× too fast and would be catastrophic within a day of real time. | `WeekTransition`'s unique constraint is the only gate. W5's `test_two_ticks_in_the_same_week_apply_growth_once`, plus the double-tick check in Verification. |
| The `advance_ages()` wiring written as a clever one-liner. The draft in the `world/services.py` section above shows a line that looks plausible and is wrong (`and` short-circuits, and it calls the function twice). Use the explicit loop shown below it. | Named here because it is exactly the kind of line a reader copies from a plan without reading. W5's ageing tests catch it. |
| `int()` in `_settle` replaced with `round()` or `math.floor()` by a reader who thinks truncation is a bug. | The docstring says why. `test_fractional_growth_accumulates_across_weeks_instead_of_being_lost` and the decline tests fail in opposite directions if it changes. |
| Attributes converging so every rider flattens into the same profile — the failure that silently destroys speciality and would only be noticed seasons later. | Design decision 3, and `test_a_climbers_climb_ceiling_exceeds_their_sprint_ceiling`. The Verification step checks `sprint` moved less than `climb` on a real Climber. |
| Tuning constants wrong by an order of magnitude — invisible in unit tests that only assert direction. | W3's tests must assert *magnitude* over a twelve-week season (10-20 stored points), not just `> 0`. The Verification run is the real check. |
| A full-table update on every tick becoming slow as the world grows. | `bulk_update` in batches, and growth sits outside the claim transaction. At a few hundred riders this is well under the ~8s a single race already takes; revisit past a few thousand. |
| `growth_debt` leaking into a serializer. | `riders/README.md`'s existing rule, restated in W6. `api/`'s serializers list fields explicitly, so this requires someone actively adding it. |

## Open questions

None blocking. Two tuning constants (`WEEKLY_GROWTH_FRACTION`,
`WEEKLY_DECLINE_UNIT`) are starting values derived from the spec's "one to
two display points per season" and should be adjusted once a season has been
watched end to end — that is a balance pass, not a design question.

# Weekly training focus — Implementation Plan

**Spec:** `specs/weekly-training-focus.md` · **Issue:** #36 · **Status:** proposed
**Apps touched:** `staff/`, `riders/`, `racing/`, `world/`, `api/`, `frontend/`

> **Blocked on [#71](https://github.com/mario595/cycling-manager/pull/71) (#58, rider growth and decline) merging to master.**
> That PR introduces `schedule.WeekTransition`, `schedule.services.process_week_transitions()`,
> `riders/services.py` and the `Rider.growth_debt` fractional-accumulation
> pattern. This plan builds directly on all four rather than duplicating them —
> see Design decision 1. Do not start W2 until #71 is on master.

## Context you need

The game already has everything this feature acts on except the training itself.

**Riders** (`riders/README.md`) have five engine attributes — `climb`, `sprint`,
`flat`, `resistance`, `positioning` — stored 1-100 and shown to the player on a
0-10 scale by `riders.display.to_display_scale`, which **floors** (58 → 5). Each
rider also carries `training_affinity`, a hidden `{attribute_name: float}`
JSONField generated from `SPECIALITY_PROFILES` with per-rider noise, so values
sit roughly in 0.47-1.67 and average ~1.0. It is stored, documented as "read by
weekly training once #36 lands", and **nothing reads it yet**. This feature is
what makes it live. Hidden traits are never serialized — that rule is absolute
(`riders/README.md`).

**Trainers** (`staff/README.md`, merged in #35) are `staff.Trainer` rows: a
nullable `OneToOneField` to `teams.Team` (null = in the shared pool), five skills
stored 1-100 with the same names as `ENGINE_ATTRIBUTES`, and a derived
`speciality` property returning the highest-scoring skill. Generation guarantees
exactly one clear maximum, with the speciality drawn from 70-95 and the other
four from 25-64 — **the 25 floor exists specifically for this feature**, so
off-speciality training is never zero. `staff.services.trainer_for(team)` returns
a team's trainer or `None`.

**The weekly hook** arrives with #71: `schedule.WeekTransition` is an
exactly-once row per `Week`, written by `process_week_transitions(at)` and
mirroring `SeasonTransition`'s shape (unique constraint, per-row `atomic()`,
`IntegrityError` caught as success). `world.services.tick()` already calls it and
passes the result to `riders.services.apply_weekly_growth(weeks=len(weeks))`.

**Races** (`racing/README.md`): `Race.course` is a JSON list of
`{length, gradient}` segments; `RaceResult` has one row per rider per race;
`Race.week` links a race to its `schedule.Week`. That is enough to answer both
"who raced in week N" and "what terrain was it".

### Repo rules this work is bound by

- **Dependency direction** (`AGENTS.md`): `riders -> core, teams`;
  `staff -> core, teams, riders`; `racing -> riders, teams, race_engine, schedule`.
  Only `world/` and `api/` may import everything, and nothing may import them.
  In particular **`riders/` may not import `schedule/`, `racing/`, `staff/` or
  `world/`** — which is why the orchestration in this plan lives in `world/`.
- **`race_engine/` imports nothing from Django, and only `racing/adapters.py`
  may import the engine.** The engine's `Terrain` enum is therefore off-limits
  to `riders/` and `staff/`; this feature classifies terrain itself, in
  `racing/` (Design decision 4).
- Tests are pytest: `.venv/bin/python -m pytest`.

## Goal

When this is done:

- A team with a trainer has a persisted weekly training focus — one of the five
  attributes — that the manager can change at any time, and that carries forward
  week to week on its own.
- At each week boundary, every non-injured rider on a team with a trainer moves
  on that week's focus attribute, scaled by the trainer's score in it and by the
  rider's hidden `training_affinity`.
- Every rider who raced that week moves a little on the attribute the race's
  terrain rewards, whether or not their team has a trainer.
- Both effects are additive, settle through the **same** `growth_debt` ledger
  #58 introduces, and never lower an attribute.
- The Training screen shows the current focus picker (only when a trainer is
  hired) and a list of riders whose 0-10 displayed value changed at the last
  rollover.
- All of it happens exactly once per week even when ticks are missed,
  duplicated, or run concurrently.

## Design decisions (settled — implement these, do not substitute)

**1. Reuse #58's `WeekTransition` and `growth_debt`; do not build a second
weekly mechanism.** #71 already solves "has this week been processed?" with an
exactly-once row, and "how do sub-1.0 weekly movements accumulate?" with
`Rider.growth_debt` plus `riders.services._settle()`. Training has both problems
identically.

**Do not** add a `training_debt` field, a `last_trained_at` timestamp on
`Rider`, or a second weekly transition model. Two debt ledgers over the same five
integer attributes means two independent truncations per week, which loses
roughly half a point per attribute per week and is invisible until a season has
passed.

**2. Training deltas and growth deltas are summed per attribute and settled
once.** `apply_weekly_growth()` currently computes `weekly_deltas(rider)` and
settles it. This feature widens that to accept an extra per-rider delta map and
add it before `_settle` runs. One pass over `Rider`, one `bulk_update`, one
rounding point.

**Do not** run a second pass after `apply_weekly_growth()` that reads the
attributes it just wrote — beyond double-truncation, it makes the order of the
two features observable to the player for no reason.

**3. A missed week applies that week's *own* focus, so the weekly loop cannot
collapse to a count.** `apply_weekly_growth(weeks=N)` legitimately multiplies
one delta by N, because the age curve does not change week to week. Training
does: week 3's focus may be `climb` and week 4's `sprint`, and the races run in
each week differ. So `world.services.tick()` must iterate the
`list[WeekTransition]` and compute training per week, rather than passing a
count.

This is the one place this feature diverges from #58's shape, and it is
load-bearing. A tick that runs three weeks late must apply three *different*
training weeks.

**Consequence for the focus value:** the focus is a single mutable field on the
team's trainer-slot state, so a three-weeks-late tick sees only today's focus and
applies it to all three weeks. That is accepted, not overlooked — a per-week
history of intended focus is a record nobody asked for, and a late tick is a
server-health problem, not a game mechanic. Note it in the README.

**4. Terrain classification lives in `racing/`, not `riders/` or the engine.**
The feature needs "what attribute does this course reward?". The engine has a
`Terrain` enum, but `race_engine/` may only be imported by `racing/adapters.py`,
and `riders/` may not import `racing/` at all. So:

- `racing/services.py` gains `course_training_attribute(course) -> str`, a pure
  function over the stored `Race.course` JSON — no engine import needed, since
  the JSON is already the segment list.
- It returns one attribute name, chosen by distance-weighted average gradient:
  a course averaging a meaningful climb rewards `climb`, a mostly-flat course
  rewards `flat`, and a course that is flat *and* short rewards `sprint`.
  `resistance` is rewarded by unusually long courses.
- `positioning` is deliberately never awarded by terrain — no course shape
  distinctly rewards draft skill, and inventing one would be arbitrary.

**Do not** import `race_engine.models.Terrain` anywhere outside
`racing/adapters.py`. **Do not** put this function in `riders/` — it would need
`Race`, which `riders/` may not import.

**5. The focus lives on a new `staff.TrainingFocus` model keyed to the team, not
a field on `Trainer`.** A focus is a property of a team's training programme, not
of the person hired: firing a trainer and hiring another should not silently
reset what the team was working on, and `Trainer` rows return to a shared pool
where a stale focus would be meaningless.

**Do not** add a `focus` CharField to `Trainer`. **Do not** put it on
`teams.Team` — that inverts the dependency graph (`teams` must not know about
`staff`), the same reasoning `staff/README.md` gives for `Trainer.team` being a
`OneToOneField` rather than an FK on `Team`.

**6. "Injured" resolves through a single helper that returns False today.**
#41 (injuries) does not exist. The spec requires injured riders to be skipped.
Implement `riders.services.is_injured(rider) -> bool` returning `False`, with a
docstring naming #41 as its future owner, and call it from the training pass.

**Do not** add an `is_injured` field to `Rider` — that is #41's data model
decision to make, and guessing it now means #41 either inherits a wrong shape or
migrates it away.

**7. The "what changed" list is computed from a stored snapshot, not recomputed
on read.** The Training screen must show which riders' *displayed* (0-10) value
moved at the last rollover. The stored attribute after the fact cannot tell you
what it was before.

So the training pass writes a `staff.TrainingWeekReport` row per team per week
holding the list of visible changes as JSON. The API reads the most recent one.

**Do not** try to derive this by diffing `Rider.updated_at`, and **do not** log
every rider — the spec says riders with no visible change are not listed, and at
~600 riders a full log per week is noise that grows forever.

**8. Effect magnitude is tuned so a focused season is worth about one display
point.** With `WEEKLY_TRAINING_UNIT` at 0.010: a trainer at 85 in their
speciality, a rider with affinity 1.2, gives `0.010 * 85 * 1.2 ≈ 1.02` stored
points per week — about 12 across a season, just over one display level. The
same trainer on a 30-score off-speciality skill gives ~0.36/week, ~4.3 a season:
clearly worse, never zero. Race-based training uses
`RACE_TRAINING_UNIT = 0.25` stored points per race, so a rider racing most weeks
gains ~2-3 points a season from racing alone — the spec's "much less" than
training.

These are starting values, not sacred. They live as named module constants with
this reasoning in a comment, the same way #58's `WEEKLY_GROWTH_FRACTION` does.

## Data model

### `staff.TrainingFocus` (new)

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `team` | `OneToOneField("teams.Team", on_delete=CASCADE, related_name="training_focus")` | no | — | One focus per team. Deleted with the team. |
| `attribute` | `CharField(max_length=12, choices=ATTRIBUTE_CHOICES)` | no | `"climb"` | One of `riders.models.ENGINE_ATTRIBUTES`. |
| `created_at` / `updated_at` | from `TimeStampedModel` | — | — | Real time. |

`ATTRIBUTE_CHOICES` is built in `staff/models.py` as
`[(name, name.title()) for name in ENGINE_ATTRIBUTES]` — `staff/` already
imports `ENGINE_ATTRIBUTES` from `riders.models`, so the names appear once.
`DEFAULT_FOCUS = ENGINE_ATTRIBUTES[0]` (`"climb"`) is defined alongside it and
is what both the field default and `focus_for()`'s no-row case return.

The row is created on demand (`get_or_create`) the first time a team sets or
reads a focus. A team with no row and no trainer simply has no focus.

### `staff.TrainingWeekReport` (new)

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `team` | `ForeignKey("teams.Team", on_delete=CASCADE, related_name="training_reports")` | no | — | |
| `week` | `ForeignKey("schedule.Week", on_delete=CASCADE, related_name="training_reports")` | no | — | **See the import note below.** |
| `attribute` | `CharField(max_length=12, blank=True)` | blank ok | `""` | The focus that was applied. Empty when the team had no trainer. |
| `changes` | `JSONField` | no | `list` | `[{"rider_id": int, "rider_name": str, "attribute": str, "from": int, "to": int}]`, display scale. Empty list is normal. |
| `created_at` / `updated_at` | from `TimeStampedModel` | — | — | |

Constraint: `UniqueConstraint(fields=["team", "week"], name="one_training_report_per_team_per_week")`.
This is a second line of defence only — `WeekTransition` is the real
exactly-once guarantee. Catch `IntegrityError` and continue, as
`process_transitions` does.

**Import note:** `staff -> schedule` is **not** in `AGENTS.md`'s dependency
graph. Use a **string reference** (`"schedule.Week"`) so `staff/models.py` needs
no import of `schedule/`, exactly as `racing/models.py` does for
`"teams.Team"` and `"riders.Rider"`. Add `schedule` to `staff`'s permitted
references in `AGENTS.md` and in `staff/README.md` in the same change (W7) — a
string FK is still a dependency and the graph must say so.

### `riders.Rider` — no new fields

`training_affinity` and `growth_debt` (from #71) are both already there. This
feature adds nothing to the model.

### Migrations

- `staff/migrations/0002_trainingfocus_trainingweekreport.py` — both models.

## `racing/services.py`

```python
#: Distance-weighted mean gradient (%) at or above which a course trains climb.
CLIMB_GRADIENT_THRESHOLD = 2.0
#: Courses at or under this length (m) with no real climbing train sprint.
SPRINT_MAX_DISTANCE = 120_000
#: Courses at or over this length (m) train resistance.
RESISTANCE_MIN_DISTANCE = 200_000


def course_training_attribute(course: list[dict]) -> str:
    """Which rider attribute racing this course rewards.

    Pure function over the stored Race.course JSON — deliberately not a
    read of race_engine.models.Terrain, which only racing/adapters.py may
    import (AGENTS.md). Never returns "positioning": no course shape
    distinctly rewards draft skill. See specs/weekly-training-focus-plan.md,
    Design decision 4.
    """
```

Order of checks: climbing wins if the weighted mean gradient clears the
threshold; otherwise length decides between `resistance` (long), `sprint`
(short) and `flat` (everything else). A course with no segments, or zero total
length, returns `"flat"` — do not divide by zero.

Also in `racing/services.py`:

```python
def riders_who_raced(week) -> dict[int, list[str]]:
    """{rider_id: [training attribute per race they finished]} for one week.

    One query over RaceResult joined to Race, not one query per race. A
    rider who raced twice in a week appears with two entries and is
    trained for both.
    """
```

## `riders/services.py`

Extend the module #71 creates. Two additions and one change:

```python
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
```

The signature takes `trainer_skill` as a plain int, not a `Trainer`: `riders/`
may not import `staff/`. The caller in `world/` reads the trainer and passes the
number.

Change `apply_weekly_growth` to accept and fold in an extra delta map:

```python
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
```

**This changes #71's return type** from `int` to `list[dict]`. Update #71's
caller in `world/services.py` and its tests in the same commit (W3). The record
shape is `{"rider_id", "rider_name", "team_id", "attribute", "from", "to"}` with
`from`/`to` already passed through `to_display_scale`.

The display-scale comparison must be computed **inside** the settle loop, from
the value before and after — that is the only point both are in hand.

## `staff/services.py`

```python
def focus_for(team) -> str | None:
    """The team's current training focus, or None if they have no trainer.

    A team with a trainer but no TrainingFocus row gets the default
    (DEFAULT_FOCUS) without a write — the row is only created when the
    manager actually chooses.
    """


def set_focus(team, attribute: str) -> TrainingFocus:
    """Set this week's focus. Raises NoTrainerHired if the team has no
    trainer — the spec is explicit that a team without one has no focus
    decision to make at all, so this is a 409 at the API, not a silent
    no-op."""


def latest_report(team) -> TrainingWeekReport | None:
    """The most recent week's report, for the Training screen."""
```

`ValueError` for an attribute outside `ENGINE_ATTRIBUTES`; the serializer's
`ChoiceField` should catch it first.

## `world/services.py`

The orchestration, because it is the only app that may import `staff`,
`riders`, `racing` and `schedule` together. Replace #71's two-line weekly block:

```python
weeks = process_week_transitions(at)
for week in weeks:                      # per week, NOT weeks=len(weeks)
    _apply_training_week(week)
```

```python
def _apply_training_week(week) -> None:
    """One week's growth and training, settled together.

    Iterated per week rather than collapsed into a count because each
    week has its own focus and its own races — see the plan's Design
    decision 3.
    """
    raced = riders_who_raced(week)                    # racing.services
    extra: dict[int, dict[str, float]] = {}
    focus_by_team: dict[int, str] = {}

    for trainer in Trainer.objects.filter(team__isnull=False).select_related("team"):
        focus = focus_for(trainer.team)
        if focus is None:
            continue
        focus_by_team[trainer.team_id] = focus
        skill = getattr(trainer, focus)
        for rider in trainer.team.riders.all():
            extra[rider.pk] = training_deltas(
                rider, focus=focus, trainer_skill=skill,
                raced_attributes=raced.get(rider.pk, []),
            )

    # Riders whose team has no trainer still get the race effect.
    for rider in Rider.objects.exclude(pk__in=extra):
        attrs = raced.get(rider.pk, [])
        if attrs:
            extra[rider.pk] = training_deltas(
                rider, focus=None, trainer_skill=None, raced_attributes=attrs,
            )

    changes = apply_weekly_growth(weeks=1, extra_deltas=extra)
    _write_training_reports(week, changes, focus_by_team)
```

`weeks=1` here, because the loop already runs once per week.

`_write_training_reports` groups `changes` by `team_id` and creates one
`TrainingWeekReport` per team that has a trainer, each inside its own
`transaction.atomic()` with `IntegrityError` caught — the same per-row shape
`process_transitions` uses, and for the same reason (an `IntegrityError`
poisons an enclosing transaction).

`TickRun` gains `riders_trained = PositiveIntegerField(default=0)`, set from
`len(changes)`, in `world/migrations/` — it is how an operator sees the pass ran.

## `api/`

**`api/serializers.py`**

```python
class TrainingChangeSerializer(serializers.Serializer):
    rider_id = serializers.IntegerField()
    rider_name = serializers.CharField()
    attribute = serializers.CharField()
    from_value = serializers.IntegerField(source="from")
    to_value = serializers.IntegerField(source="to")


class TrainingSerializer(serializers.Serializer):
    """The Training screen's whole state in one payload, the same shape
    rule StaffSerializer follows: every key always present, so the SPA
    branches on one response rather than calling three endpoints."""

    has_trainer = serializers.BooleanField()
    focus = serializers.CharField(allow_null=True)
    options = serializers.ListField(child=serializers.CharField())
    last_week = serializers.SerializerMethodField()   # null, or {attribute, changes}
```

`options` is `list(ENGINE_ATTRIBUTES)` — the SPA must not hardcode the five
names.

**Never serialize `training_affinity`.** It is a hidden trait; the report
carries only the before/after the player can already see.

**`api/views.py`** — `TrainingView(APIView)`, matching `StaffView` exactly:
team from `team_for(request.user)`, 403 when the user manages no team.

- `GET` returns `TrainingSerializer`.
- `PUT` sets the focus: `409` when the team has no trainer (well-formed request,
  world state refuses it — the same split `HireTrainerView` documents), `400`
  for an attribute outside the five.

**`api/urls.py`** — `path("staff/training/", TrainingView.as_view(), name="training")`.

## `frontend/`

`/training` is already a nav item rendering `Placeholder` (`frontend/src/navigation.ts`).

- **`frontend/src/api.ts`** — `TrainingState` interface, `getTraining()`,
  `setTrainingFocus(attribute)`.
- **`frontend/src/useTraining.ts`** — mirror `useStaff.ts`, including its
  60-second poll, so a rollover appears without a manual refresh.
- **`frontend/src/screens/Training.tsx`** — last week's changes panel on top
  (`"No visible changes last week."` when empty, the whole panel hidden when
  there is no report at all); focus picker below, rendered **only** when
  `has_trainer`, otherwise a line pointing at the Staff screen.
- **`frontend/src/App.tsx`** — add `'/training': Training` to `SCREENS`.

## Work items

### W1 — `racing/services.py`: course terrain → training attribute
Add `course_training_attribute()` and `riders_who_raced()` with the constants
above. No model changes, no dependency on #71 — **this item can be built and
merged before #71 lands.**
*Test:* `racing/tests.py::test_course_training_attribute_buckets` covering a
mountain course, a long flat course, a short flat course and an empty course;
`::test_riders_who_raced_groups_by_rider` covering a rider who raced twice in
one week. (`racing/` uses a flat `tests.py`, not a `tests/` package — unlike
`staff/` and `riders/`.)

**Done.**

### W2 — `staff/`: the two models
`TrainingFocus` and `TrainingWeekReport`, migration `0002`, admin registration.
`schedule.Week` referenced as a string.
*Test:* `staff/tests/test_models.py::test_one_focus_per_team` and
`::test_one_report_per_team_per_week` both assert `IntegrityError`.

### W3 — `riders/services.py`: training deltas, and one shared settle
`is_injured()`, `training_deltas()`, and the `extra_deltas` parameter plus new
return type on `apply_weekly_growth()`. **Update #71's existing caller and
tests in this commit** — the repo must be green at the end of it.
*Test:* `riders/tests/test_services.py::test_training_delta_scales_with_trainer_skill`,
`::test_off_speciality_training_is_never_zero`,
`::test_injured_rider_gets_nothing`,
`::test_training_and_growth_settle_through_one_debt` — the last asserts that a
0.6 training delta and a 0.6 growth delta in the same week yield **one** stored
point, not zero.
*Load-bearing:* that last test is the one that catches the double-truncation
this plan exists to avoid.

### W4 — `staff/services.py`: focus read/write
`focus_for`, `set_focus`, `latest_report`.
*Test:* `staff/tests/test_services.py::test_set_focus_requires_a_trainer`,
`::test_focus_defaults_without_writing_a_row`.

### W5 — `world/services.py`: the weekly pass
`_apply_training_week`, `_write_training_reports`, the per-week loop, and
`TickRun.riders_trained` with its migration.
*Test:* `world/tests/test_services.py::test_training_applies_once_per_week`,
`::test_three_missed_weeks_apply_three_training_weeks`,
`::test_rider_on_teamless_squad_still_gains_from_racing`,
`::test_concurrent_ticks_train_once`.
*Load-bearing:* the three-missed-weeks test is what proves Design decision 3 —
it must fail if someone "simplifies" the loop back to `weeks=len(weeks)`.

### W6 — `api/`: the Training endpoint
Serializers, `TrainingView`, URL.
*Test:* `api/tests.py::test_training_get_without_trainer_has_no_focus`,
`::test_training_put_sets_focus`, `::test_training_put_without_trainer_is_409`,
`::test_training_never_exposes_training_affinity`.

### W7 — docs
`staff/README.md`, `riders/README.md`, `world/README.md`, `racing/README.md`,
`AGENTS.md`. See below.

### W8 — `frontend/`: the Training screen
`api.ts`, `useTraining.ts`, `screens/Training.tsx`, `App.tsx`.
*Test:* manual, per Verification. The SPA has no test suite today.

## Execution order

W1 first: it is the only item with no dependency on #71, it is pure and
independently testable, and it gets the fiddliest classification logic settled
while the rest waits.

Then **stop until #71 merges.**

W2 → W3 → W4 next: data model, then the pure calculation, then the thin service
layer over it. W3 is the risky one and it is deliberately reached with both its
inputs (W1's terrain answer, W2's storage) already in place and tested.

W5 wires it to the clock — the first point the feature actually does anything,
and the right place to stop and verify by hand before building UI on top.

W6 → W8 expose it. W7 lands before W8 so the frontend work is not what is
holding up the documentation.

Commit at every W.

## Documentation update (required, not optional)

- **`staff/README.md`** — a *Weekly training* section: what `TrainingFocus` and
  `TrainingWeekReport` own, why the focus is keyed to the team and not to
  `Trainer` (Design decision 5), and the accepted late-tick behaviour from
  Design decision 3. Update *What `staff/` may import* to record the string
  reference to `schedule.Week`.
- **`riders/README.md`** — `training_affinity` moves from "inert" to live; say
  what reads it and that it is still never serialized. Note `is_injured()` as
  #41's placeholder.
- **`world/README.md`** — *How a tick works* gains the per-week training step,
  and states why it iterates weeks rather than passing a count.
- **`racing/README.md`** — `course_training_attribute()`, and why terrain is
  classified here rather than read from the engine's `Terrain`.
- **`AGENTS.md`** — `staff` gains `schedule` in the dependency graph; the
  `staff/` and `riders/` table rows get a line about weekly training.

## Verification

```bash
.venv/bin/python -m pytest
```

Then by hand, against a mock clock:

```bash
export GAME_CLOCK_CLASS=world.clocks.MockClock
.venv/bin/python manage.py load_season seasons/season-1.example.json
.venv/bin/python manage.py seed_trainers --count=5 --rng-seed=1
.venv/bin/python manage.py mock_clock set 2027-03-01T00:00
.venv/bin/python manage.py tick
```

1. Hire a trainer through the SPA, set the focus to their speciality, and note
   one rider's climb on the roster.
2. `mock_clock advance --by 1w` then `tick`. The Training screen's panel lists
   any rider whose displayed value moved; `TickRun.riders_trained` is non-zero.
3. Advance **three** weeks in one jump, then tick once. Three
   `WeekTransition` rows appear and three weeks of training are applied — not
   one. This is the check that catches the Design decision 3 regression.
4. Tick again immediately with no clock movement. Nothing changes: no new
   `WeekTransition`, no new report, no attribute movement.

**What actually proves it:** step 4 failing to be a no-op, or step 3 producing
one week of movement, are the two real failures. A passing W5 test suite that
only ever advances one week proves neither — which is why
`test_three_missed_weeks_apply_three_training_weeks` is named explicitly.

**Likeliest failure mode:** the shared-debt change in W3 silently breaking #58's
own growth numbers. `test_training_and_growth_settle_through_one_debt` is the
check; #71's existing growth tests must also still pass untouched.

## Risks

| Risk | Mitigation |
|---|---|
| #71 changes shape before merging, invalidating W3's assumptions about `apply_weekly_growth` and `growth_debt`. | W1 is independent; everything else waits for #71 to be on master. Re-read `riders/services.py` at W3 rather than trusting this plan's transcription of it. |
| The reader adds a `training_debt` field "for separation of concerns", reintroducing double truncation. | Design decision 1 says not to, and `test_training_and_growth_settle_through_one_debt` fails if they do. |
| The reader collapses the per-week loop to `weeks=len(weeks)` to match #58. | Design decision 3, plus `test_three_missed_weeks_apply_three_training_weeks`. |
| `training_affinity` leaks into the Training payload while building the report. | `test_training_never_exposes_training_affinity`; the report carries only display-scale before/after. |
| `course_training_attribute` thresholds misclassify the six bundled courses, making every race train `flat`. | W1's test uses real course shapes from `race_engine/configs/`; check the classification of all six by hand during verification. |
| Iterating `trainer.team.riders.all()` per trainer is N+1 across ~50 teams each week. | Acceptable at this size and run once a week by cron. If it matters, `prefetch_related("team__riders")` — noted, not done pre-emptively. |

## Open questions

None blocking. The effect-magnitude constants in Design decision 8 are starting
values to be tuned in play, not open design questions.

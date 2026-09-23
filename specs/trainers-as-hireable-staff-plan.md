# Trainers as hireable staff — Implementation Plan

**Spec:** `specs/trainers-as-hireable-staff.md` · **Issue:** #35 · **Status:** implemented
**Apps touched:** `staff/` (**new**), `world/`, `api/`, `frontend/`

## Context you need

The game is a Django + DRF backend with a single React SPA in `frontend/`.
Read `AGENTS.md` first for the app table and the dependency direction; this
plan is bound by both.

**What exists today that this work builds on:**

- **`teams.Team`** (`teams/models.py`) — has `name`, `code`, `primary_colour`,
  `secondary_colour`, and a nullable `manager` OneToOneField to
  `accounts.User`. `manager IS NULL` means AI-controlled. There is no staff
  of any kind.
- **`riders.Rider`** (`riders/models.py`) — the five engine attributes
  (`climb`, `sprint`, `flat`, `resistance`, `positioning`) are
  `PositiveSmallIntegerField`s **stored 1-100**, validated with
  `MinValueValidator(1)`/`MaxValueValidator(100)` by the `_attribute_field()`
  helper. The tuple `ENGINE_ATTRIBUTES` and the constant `DISPLAY_MAX = 10`
  both live in that module and are the shared vocabulary for these five
  names. See `riders/README.md`.
- **`riders/display.py::to_display_scale(value)`** — maps a stored 1-100
  value onto the 0-10 scale the player sees. **The implementation is
  `value // 10` (floor).** Every serializer that ships an attribute calls
  it; nothing else reimplements the mapping.
- **`riders/generation.py`** — the house pattern for seeded, deterministic
  generation: an `rng: random.Random | None = None` keyword argument
  throughout, module-level tuning constants with comments explaining why
  each number is what it is, and builders that return **unsaved** instances
  so callers can `bulk_create`.
- **`teams/services.py::claim_team`** — the closest precedent for a
  contended mutation. One `transaction.atomic()` block, a
  `select_for_update(skip_locked=True)` to grab an unmanaged team, a
  domain exception (`NoTeamAvailable`) for "the world's state refuses
  this".
- **`world/services.py::tick()`** — the one entry point cron calls. It
  calls `process_transitions(at)` from `schedule/` **before** claiming
  races, then simulates. `world/` is allowed to import everything; nothing
  may import `world/`.
- **`schedule/services.py::process_transitions(at)`** — records every
  crossed season boundary exactly once as a `SeasonTransition` row with a
  `Kind` of `OPENED` or `CLOSED`, returning the rows it wrote, oldest
  first. `schedule/README.md` is explicit that this ships empty on purpose
  and **is the hook later features attach to**. This plan is the first
  feature to attach to it.
- **`api/`** — one `urls.py`, one `views.py` of `APIView` subclasses, one
  `serializers.py`. `api/views.py::team_for(user)` resolves the caller's
  own team and is the established way a team-scoped endpoint finds its
  team; there is no team id in any URL. Default permission is
  `IsAuthenticated`. `api/serializers.py::_display_scale_attributes(obj)`
  already maps the five attributes through `to_display_scale`.
- **`frontend/src/navigation.ts`** — `NAV_SECTIONS` already contains
  `{ path: '/staff', name: 'Staff' }` under `TEAM`, and `App.tsx` generates
  a route per nav item, falling back to a shared `Placeholder`. **Wiring a
  screen means pointing that existing nav item at a real component** — no
  new route or nav entry is needed.
- **`frontend/src/api.ts`** — `writeJson` handles `'POST' | 'PUT'` only,
  and does the CSRF dance. `frontend/src/useRoster.ts` is the hook pattern:
  poll, hold `null` while loading, render nothing rather than fabricating
  data.
- **`frontend/src/screens/Roster.tsx`** — renders an attribute as
  `<Bar value={value * 10} fill={barColor(value * 10)} />`, because the API
  ships the 0-10 display scale and `Bar`/`barColor` expect 0-100.

**Repo rules this work is bound by:**

- `staff/` is a **new app**: it needs `startapp`, a `README.md`,
  an entry in `LOCAL_APPS` in `config/settings/base.py`, and its first
  migration, all in the same change.
- **Dependency direction.** `AGENTS.md` gives `staff -> core, teams,
  riders`. `staff/` must **not** import `world/`, `api/`, `schedule/` or
  `racing/`. In particular the season-boundary top-up is wired from
  `world/`, which calls into `staff/` — never the reverse.
- `race_engine/` is untouched by this work and must stay untouched.
- Tests are pytest, run `.venv/bin/python -m pytest`. A new app must be
  added to `testpaths` in `pyproject.toml` or its tests never run.
- Postgres in dev and prod alike.

**Not in this plan, because the spec put it out of scope:** any fee or
salary (that is #69), poaching, contract length, physio/scout slots, AI
teams hiring, and any training effect — #36 owns what a trainer *does*.
This ticket only makes a trainer exist, be hired, and be fired.

## Goal

When this is done:

1. A `staff.Trainer` row exists per generated trainer, with five 1-100
   skill scores and exactly one unambiguously highest.
2. A trainer with `team IS NULL` is in the shared pool; a trainer with a
   `team` fills that team's one slot, enforced by the database.
3. A manager can `GET` their staff state, `POST` to hire a named pool
   trainer, and `POST` to fire their current one — each immediate, free,
   and safe under two managers racing for the same trainer.
4. `world.services.tick()` tops the pool up when a season boundary is
   crossed, exactly once per boundary.
5. The `/staff` screen in the SPA shows either the pool (with each
   trainer's five scores as bars) or the hired trainer plus a Fire button.
6. `.venv/bin/python -m pytest` is green, and `staff` is in `testpaths`.

## Design decisions (settled — implement these, do not substitute)

**D1. Trainer skill scores are stored 1-100 and displayed 0-10, exactly
like rider attributes.** The spec says "a score from 1-10"; that is the
*player-facing* scale, and it is the display scale riders already use.
Store 1-100 and reuse `riders.display.to_display_scale` unchanged in the
serializer.

*Do not store 1-10.* Two reasons, both load-bearate: (a) #36 scales a
training effect off the trainer's score in the focused skill, and a 1-10
integer gives ten coarse buckets where the difference between "clear
speciality" and "second best" collapses; (b) the spec requires every score
to be far enough off the floor to produce a non-zero effect, which is
expressible at 1-100 resolution and barely expressible at 1-10. A single
display mapping already exists and `riders/README.md` says nothing else
should reimplement it — so reuse it rather than introducing a second scale
to the codebase.

**D2. `Trainer.team` is a `OneToOneField(null=True)`, and that is what
enforces the one-slot rule.** A trainer in the pool has `team = None`; a
hired trainer points at their employer. `OneToOneField` makes "two trainers
on one team" a database error rather than a rule in application code.

*Do not put a `trainer` FK on `Team`.* It would invert the dependency
(`teams/` must not know about `staff/` — the graph is `staff -> teams`),
and it would need a migration on `teams/` for a field only `staff/` cares
about. *Do not use a plain ForeignKey plus a uniqueness check in the
service* — the check races.

**D3. Hiring locks the specific trainer row with `select_for_update()` and
**no** `skip_locked`.** `claim_team` uses `skip_locked=True` because it
wants *any* unmanaged team and can happily skip a contended row. Hiring is
the opposite: the manager asked for **that** trainer. With
`skip_locked=True` a contended row would vanish from the queryset and the
service would report "not in the pool" — indistinguishable from a genuine
mistake. Block on the lock instead, then re-check `team_id is None` after
acquiring it and raise `TrainerNotAvailable` if the other transaction won.

This re-check after the lock is the load-bearing line of the whole feature.
Without it, two managers hiring the same trainer simultaneously both pass
the pre-check and the second silently steals the first's hire.

**D4. Firing is `POST /api/staff/trainer/fire/`, not `DELETE`.** Nothing is
deleted — the trainer's `team` is set back to `None` and the row survives
in the pool. `api.ts`'s `writeJson` only supports POST and PUT, so a POST
also means no new HTTP verb plumbing in the frontend. Modelling a state
change as a deletion would also invite a future reader to actually delete
the row, which would destroy a pool trainer.

**D5. Generation guarantees the speciality by construction, not by
retry.** Pick the speciality skill first, draw its score from a high band,
draw the other four from a lower band whose **top is strictly below the
speciality band's bottom**. Non-overlapping bands make "exactly one is
clearly highest" true by arithmetic — there is no rejection loop and no
possibility of a tie.

*Do not roll five independent scores and re-roll on a tie.* That is
unbounded work in the worst case and makes the "clearly highest" margin a
matter of luck rather than a guarantee. The spec's word is *clearly*: a
speciality one point above the runner-up satisfies "highest" but not
"clearly", and once displayed at 0-10 a 1-point gap frequently renders as
no gap at all.

**D6. The pool top-up is idempotent per boundary, driven by
`SeasonTransition` rows.** `world.services.tick()` already receives the
list of transitions `process_transitions(at)` actually wrote — and that
function is exactly-once by database constraint. Top up once per returned
transition. Because a transition row is written at most once ever, the
top-up cannot double-fire, even if `tick()` runs twice or catches up three
weeks late.

*Do not top up by comparing the pool size to a target on every tick.* That
fires on every tick rather than at a boundary, and makes the pool a
maintained level rather than something that grows at season boundaries as
the spec describes.

**D7. Top-up adds a fixed number of new trainers; it never deletes or
trims.** The spec says the pool "never runs dry" and explicitly says there
is no scarcity mechanic and no hard cap. Adding a fixed batch per boundary
satisfies that. Unhired trainers stay in the pool indefinitely — the spec's
"Pool volume" decision says trainers left unhired do not expire.

**D8. The world seeds an initial pool via a management command, not a data
migration.** `staff/management/commands/seed_trainers.py`. A data migration
that creates game content runs on every fresh database including every test
database, which would make every test start with a pool it did not ask for
and did not control. The existing `reset_riders` command is the precedent
for "generate game content on demand from the command line".

**D9. `staff/services.py` holds `hire_trainer` / `fire_trainer`; the view
holds no game logic.** Matches `teams/services.py` + `api.views.ClaimTeamView`.
The service raises domain exceptions (`TrainerNotAvailable`,
`SlotOccupied`, `NoTrainerHired`); the view maps them to status codes.

**D10. A team that is unmanaged is not specially blocked in the service.**
The API can only ever be reached by an authenticated user, and `team_for()`
resolves to that user's own team, which by definition has a manager. Adding
an "is this team managed?" guard inside `hire_trainer` would be validating
a condition the only caller makes impossible. AI teams simply never call
it — which is exactly what the spec's out-of-scope item says.

## Data model

### `staff.Trainer` (new)

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `id` | auto pk | — | — | |
| `created_at`, `updated_at` | from `core.models.TimeStampedModel` | — | auto | Subclass it, as every other model does. |
| `name` | `CharField(max_length=100)` | not null, not blank | — | Generated from the same name pools as riders. |
| `nationality` | `CharField(max_length=2, choices=...)` | not null, not blank | `"ES"` | Reuses `riders.models.Rider.Nationality.choices`; see below. |
| `team` | `OneToOneField("teams.Team", on_delete=models.SET_NULL, null=True, blank=True, related_name="trainer")` | **nullable** | `None` | `None` = in the shared pool. The one-slot rule (D2). `SET_NULL` so deleting a team returns its trainer to the pool rather than destroying it. |
| `climb` | `PositiveSmallIntegerField`, validators `Min(1)`, `Max(100)` | not null | — | 1-100 stored (D1). |
| `sprint` | same | not null | — | |
| `flat` | same | not null | — | |
| `resistance` | same | not null | — | |
| `positioning` | same | not null | — | |

`class Meta: ordering = ["name"]`.

**Field definition.** `riders.models._attribute_field(help_text)` is
private to that module and its docstring ties it to the engine. Define a
local `_skill_field(help_text)` in `staff/models.py` with the same
validators rather than importing the private helper across app boundaries.

**The five skill names come from `riders.models.ENGINE_ATTRIBUTES`.**
Import that tuple — do not retype the five strings. `staff -> riders` is
allowed by the dependency graph. Add a module comment saying the five
trainer skills are deliberately the same five names as a rider's engine
attributes, because #36 maps a training focus onto one of them.

**Nationality** reuses `Rider.Nationality.choices` and defaults to `"ES"` —
only Spain exists today. Do not define a second parallel choices class.

**A convenience property, not a field:**

```python
@property
def speciality(self) -> str:
    """The skill this trainer is best at. Derived, never stored — D5
    guarantees exactly one maximum, so `max` has no tie to break."""
    return max(ENGINE_ATTRIBUTES, key=lambda name: getattr(self, name))
```

**Migration:** `staff/migrations/0001_initial.py`, generated with
`makemigrations staff`. One migration, no data migration (D8).

## `staff/generation.py` (new)

Mirrors `riders/generation.py`'s shape: module constants with reasons, an
`rng` keyword argument, returns **unsaved** instances.

```python
#: The speciality skill is drawn from this band; the other four from
#: _OFF_SPECIALITY_BAND. The bands do not overlap — _OFF_SPECIALITY_BAND's
#: top (64) is strictly below _SPECIALITY_BAND's bottom (70) — which is
#: what makes "exactly one skill is clearly the highest" true by
#: construction rather than by luck (D5). A gap of at least 6 stored
#: points also survives the 0-10 display scale: floor(70/10)=7 against
#: floor(64/10)=6, so the speciality reads as visibly higher on the bars
#: the player actually sees.
_SPECIALITY_BAND = (70, 95)

#: Never starts at 1. The spec requires off-speciality training to always
#: be worth something once #36 reads these numbers, so the floor is well
#: clear of zero. Load-bearing: dropping this floor toward 1 would let a
#: trainer be effectively useless in four of five skills, which the spec
#: forbids.
_OFF_SPECIALITY_BAND = (25, 64)

#: New trainers added to the pool at each season boundary (D6/D7).
#: Generous on purpose — the spec says the pool must never be a scarcity
#: constraint.
TRAINERS_PER_SEASON_BOUNDARY = 8

#: Size of the initial pool created by `seed_trainers` (D8).
INITIAL_POOL_SIZE = 12


def generate_trainer(
    *,
    speciality: str | None = None,
    nationality: str | None = None,
    rng: random.Random | None = None,
) -> Trainer:
    """Build an unsaved Trainer with exactly one clearly-highest skill.

    `speciality` must be one of ENGINE_ATTRIBUTES; omitted means rolled.
    Returns unsaved so callers can bulk_create.
    """


def generate_trainer_pool(
    size: int, *, rng: random.Random | None = None
) -> list[Trainer]:
    """`size` unsaved pool trainers (team left None).

    Specialities are spread deterministically rather than rolled
    independently: cycle through ENGINE_ATTRIBUTES so a pool of 8 cannot
    come out as eight climb specialists. The spec promises a team "has a
    real choice" — five independent rolls do not guarantee that, and a
    pool with no sprint trainer in it is exactly the case a manager
    notices.
    """
```

Name generation reuses the rider pools: `from riders.generation import
FIRST_NAMES, LAST_NAMES`. They are module-level public dicts keyed by
nationality. Do not duplicate the name lists.

## `staff/services.py` (new)

The concurrency here is the part most likely to be got wrong, so this is
given as real code.

```python
class StaffError(Exception):
    """Base class for a staff change that cannot proceed."""


class TrainerNotAvailable(StaffError):
    """That trainer is not in the pool — hired by someone else, or never was."""


class SlotOccupied(StaffError):
    """The team already has a trainer; fire them first."""


class NoTrainerHired(StaffError):
    """The team has no trainer to fire."""


def hire_trainer(team, trainer_id: int) -> Trainer:
    """Move a pool trainer into `team`'s single slot.

    Locks the requested row for the duration, WITHOUT skip_locked: the
    caller asked for this specific trainer, so a contended row must make
    us wait and then report the truth, not silently behave as though the
    trainer never existed (D3).
    """
    with transaction.atomic():
        try:
            trainer = Trainer.objects.select_for_update().get(pk=trainer_id)
        except Trainer.DoesNotExist:
            raise TrainerNotAvailable("That trainer is not available.")

        # Re-checked AFTER the lock, not before it. This is the line that
        # makes two simultaneous hires of the same trainer safe: the loser
        # of the race arrives here with team_id already set and is told so,
        # rather than overwriting the winner's hire.
        if trainer.team_id is not None:
            raise TrainerNotAvailable("That trainer has already been hired.")

        if Trainer.objects.filter(team=team).exists():
            raise SlotOccupied("Your team already has a trainer.")

        trainer.team = team
        trainer.save(update_fields=["team", "updated_at"])
    return trainer


def fire_trainer(team) -> Trainer:
    """Return `team`'s trainer to the shared pool. No cooldown, no penalty
    — the row survives and is immediately hireable by anyone, including
    this team again."""
    with transaction.atomic():
        trainer = Trainer.objects.select_for_update().filter(team=team).first()
        if trainer is None:
            raise NoTrainerHired("Your team has no trainer to fire.")
        trainer.team = None
        trainer.save(update_fields=["team", "updated_at"])
    return trainer


def trainer_for(team) -> Trainer | None:
    """`team`'s trainer, or None. The read #36 will use at rollover."""
    return Trainer.objects.filter(team=team).first()


def available_trainers():
    """The shared pool, as a queryset. Every unemployed trainer, visible to
    every team."""
    return Trainer.objects.filter(team__isnull=True)


def top_up_pool(*, count: int | None = None, rng=None) -> list[Trainer]:
    """Add `count` new trainers to the shared pool. Called once per crossed
    season boundary from world.services.tick() — see D6. Never deletes or
    trims: the pool only grows (D7)."""
```

`SlotOccupied` is checked inside the same transaction as the hire so that
"fire then immediately hire" is correct under concurrency too.

## `world/services.py`

The only change outside the new app. `tick()` already holds the list of
transitions that were actually written.

```python
from staff.services import top_up_pool   # world/ may import anything

    transitions = process_transitions(at)

    # One top-up per crossed boundary. Idempotent for free: a
    # SeasonTransition row is written at most once ever (unique on
    # (season, kind)), so a tick that runs twice, or catches up three weeks
    # late, cannot double-fill the pool. See the plan's D6.
    for _ in transitions:
        top_up_pool()
```

Placed immediately after `process_transitions`, before race claiming, for
the same reason the comment there already gives: a race in the first week
of a newly opened season should be processed in a world whose boundary
work has already happened.

**Do not** add a `staff`-related counter to `TickRun` — that model's
fields are about races and seasons, and the spec asks for no reporting on
pool growth.

## `api/serializers.py`

```python
class TrainerSerializer(serializers.Serializer):
    """One trainer as the Staff screen needs them: identity and the five
    skills on the 0-10 display scale, never the stored 1-100 — the same
    rule every rider serializer follows (riders/display.py)."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    nationality = serializers.CharField()
    skills = serializers.SerializerMethodField()
    speciality = serializers.CharField()

    def get_skills(self, obj) -> dict[str, int]:
        return _display_scale_attributes(obj)


class StaffSerializer(serializers.Serializer):
    """The Staff screen's whole state: either a hired trainer or the pool.
    Both keys are always present — `trainer` null when the slot is empty,
    `pool` empty when it is filled — so the SPA branches on one payload
    rather than calling two endpoints."""

    trainer = TrainerSerializer(allow_null=True)
    pool = TrainerSerializer(many=True)
```

`_display_scale_attributes` already exists in this module and works on any
object with the five attribute names, so it works on a `Trainer`
unchanged — it branches on `isinstance(obj, dict)` and otherwise uses
`getattr`. Reuse it; do not write a second copy.

`speciality` serializes the model property from D5.

## `api/views.py`

```python
class StaffView(APIView):
    """The caller's own team's staff: the hired trainer, or the pool to
    hire from.

    No team id in the URL — the team is always the caller's own via
    team_for(), the same pattern as SquadView and RiderListView. Falls
    back to the project default, IsAuthenticated — do not re-add AllowAny.

    The pool is only populated in the response when the slot is empty:
    a team with a trainer has nothing to hire, and shipping the pool
    anyway would invite the SPA to offer a hire the API would reject.
    """

    def get(self, request):
        # team_for -> 403 when None, as every team-scoped endpoint does


class HireTrainerView(APIView):
    """Hire one pool trainer into the caller's empty slot.

    409, not 400, for "already hired" and "slot occupied": the request is
    well-formed but the world's state refuses it — the same split
    ClaimTeamView documents.
    """

    def post(self, request):
        # HireTrainerSerializer validates trainer_id is an integer
        # TrainerNotAvailable -> 409, SlotOccupied -> 409


class FireTrainerView(APIView):
    """Return the caller's trainer to the shared pool. POST, not DELETE —
    nothing is destroyed (D4)."""

    def post(self, request):
        # NoTrainerHired -> 409
```

`HireTrainerSerializer` is a two-line `serializers.Serializer` with
`trainer_id = serializers.IntegerField()`.

## `api/urls.py`

```python
path("staff/", StaffView.as_view(), name="staff"),
path("staff/trainer/hire/", HireTrainerView.as_view(), name="hire-trainer"),
path("staff/trainer/fire/", FireTrainerView.as_view(), name="fire-trainer"),
```

## `frontend/`

- **`src/api.ts`** — add the `Trainer` and `Staff` interfaces, `getStaff()`,
  `hireTrainer(trainerId)`, `fireTrainer()`. The two writes go through the
  existing `writeJson(url, 'POST', body)`; no change to `writeJson` itself
  is needed (D4).
- **`src/useStaff.ts`** (new) — same shape as `useRoster.ts`: poll, hold
  `null` while loading, expose `error`, and render nothing rather than
  fabricating a pool. Add a `refresh()` the screen calls after a hire or
  fire so the slot and pool update without waiting for the next poll.
- **`src/screens/Staff.tsx`** (new) — branch on `staff.trainer`:
  - filled: the trainer's name, speciality, five bars, and a Fire button;
  - empty: the pool as a list of cards, each with five bars and a Hire
    button, plus a line saying hiring is free.
  Render each skill as `<Bar value={value * 10} fill={barColor(value * 10)} />`
  — the API ships 0-10 and `Bar` expects 0-100, exactly as
  `Roster.tsx` does. There is **no Staff mockup in `design/`**, so follow
  `Roster.tsx`'s existing card-and-bar composition rather than inventing a
  new visual language.
- **`src/App.tsx`** — point the existing `/staff` nav item at the new
  screen. `navigation.ts` already has the entry; **do not add a nav item
  or a route**, just stop `/staff` falling through to `Placeholder`.
- Show the hire/fire failure message from the thrown `Error` inline. A 409
  is a real outcome here — someone else took that trainer — not an
  unexpected error, and the manager needs to see why the pool just
  changed under them.

## Work items

### W1 — `staff/`: the app skeleton
`.venv/bin/python manage.py startapp staff`; delete the unused
`views.py`/`tests.py` stubs and add a `tests/` package with
`__init__.py`; add `"staff"` to `LOCAL_APPS` in
`config/settings/base.py`; add `"staff"` to `testpaths` in
`pyproject.toml`; write `staff/README.md` (see Documentation).

**Test:** `staff/tests/test_app.py::test_staff_app_is_installed` — asserts
`django.apps.apps.is_installed("staff")`. Thin on purpose; W1 exists so
everything after it has somewhere to land.

### W2 — `staff/models.py`: the `Trainer` model
The model and fields per **Data model**, plus the `speciality` property and
migration `0001_initial`.

**Load-bearing:** `team` is a `OneToOneField`, not a `ForeignKey` (D2) —
this is what makes two trainers on one team impossible.

**Tests:** `staff/tests/test_models.py`
- `test_pool_trainer_has_no_team` — `team` defaults to `None`.
- `test_speciality_is_the_highest_skill` — construct a trainer with a known
  maximum and assert `speciality` returns it.
- `test_a_team_cannot_have_two_trainers` — assigning a second trainer to a
  team raises `IntegrityError`. This is the test that proves D2.
- `test_skill_below_one_is_rejected` / `test_skill_above_100_is_rejected` —
  `full_clean()` raises `ValidationError`.

### W3 — `staff/generation.py`: generating trainers
`generate_trainer`, `generate_trainer_pool`, and the band constants per
**`staff/generation.py`**.

**Load-bearing:** the two bands must not overlap (D5). Everything the
spec promises about a legible speciality rests on that.

**Tests:** `staff/tests/test_generation.py`
- `test_exactly_one_skill_is_highest` — over 200 seeded trainers, the
  maximum is never tied. Proves D5 by construction, not by sampling luck.
- `test_speciality_is_clearly_higher_on_the_display_scale` — for every
  generated trainer, `to_display_scale(speciality score)` is strictly
  greater than the display value of every other skill. This is the one
  that catches a band-overlap regression, which the tie test alone would
  not.
- `test_no_skill_sits_at_the_floor` — every score across many trainers is
  `>= _OFF_SPECIALITY_BAND[0]`, so #36 always has something to work with.
- `test_requested_speciality_is_honoured` — passing
  `speciality="sprint"` produces a trainer whose best skill is `sprint`.
- `test_generation_is_deterministic_for_a_seed` — two
  `random.Random(7)`-seeded calls give identical scores, matching
  `riders/tests/test_generation.py`'s discipline.
- `test_pool_covers_every_speciality` — `generate_trainer_pool(10)`
  contains all five specialities.
- `test_generated_trainers_are_unsaved` — `pk is None`.

### W4 — `staff/services.py`: hire, fire, read, top up
All five functions and the three exceptions per **`staff/services.py`**.

**Load-bearing:** the `trainer.team_id is not None` re-check **after**
`select_for_update()`, and the absence of `skip_locked` (D3).

**Tests:** `staff/tests/test_services.py`
- `test_hire_fills_the_slot` — `team` set, trainer leaves
  `available_trainers()`.
- `test_hire_a_trainer_already_hired_is_refused` — raises
  `TrainerNotAvailable`; the first team keeps them.
- `test_hire_when_slot_occupied_is_refused` — raises `SlotOccupied`.
- `test_hire_unknown_id_is_refused` — raises `TrainerNotAvailable`.
- `test_fire_returns_the_trainer_to_the_pool` — `team is None` and the
  trainer is back in `available_trainers()`; the row still exists.
- `test_fire_with_no_trainer_is_refused` — raises `NoTrainerHired`.
- `test_fired_trainer_can_be_rehired_by_the_same_team` — proves the
  no-cooldown rule from the spec's Rules and edge cases.
- `test_top_up_only_adds` — pool count rises by exactly
  `TRAINERS_PER_SEASON_BOUNDARY`; no existing trainer is modified and no
  hired trainer is touched.

### W5 — `world/services.py`: top up at a season boundary
The loop over `transitions` per **`world/services.py`**.

**Load-bearing:** iterate the **returned** transitions, not a size check
(D6). That is where idempotency comes from.

**Tests:** `world/tests/test_services.py` (extend the existing file)
- `test_tick_tops_up_the_pool_when_a_season_opens` — pool grows by the
  batch size.
- `test_a_second_tick_does_not_top_up_again` — two `tick()` calls across
  one boundary grow the pool once. **This is the test that proves D6**;
  without it a reader could "simplify" the loop into an unconditional
  top-up and nothing would fail.
- `test_tick_with_no_boundary_crossed_does_not_top_up` — pool unchanged.

### W6 — `staff/management/commands/seed_trainers.py`: the initial pool
A command creating `INITIAL_POOL_SIZE` pool trainers, with `--count` to
override and `--rng-seed` for reproducibility. Non-destructive: it **adds**
and never deletes, so unlike `reset_riders` it needs no `--yes`.

**Test:** `staff/tests/test_seed_trainers.py::test_seed_creates_a_pool` —
`call_command("seed_trainers", count=5)` creates five unemployed trainers.

### W7 — `api/`: serializers, views, urls
`TrainerSerializer`, `StaffSerializer`, `HireTrainerSerializer`,
`StaffView`, `HireTrainerView`, `FireTrainerView`, and the three url
patterns.

**Load-bearing:** skills ship through `_display_scale_attributes`, never
raw. A test must assert the response contains no value above
`DISPLAY_MAX`.

**Tests:** `api/tests.py` (the app's existing single test module)
- `test_staff_requires_authentication` — 403 anonymous.
- `test_staff_without_a_team_is_403`.
- `test_staff_shows_the_pool_when_the_slot_is_empty` — `trainer` is null,
  `pool` non-empty.
- `test_staff_shows_the_trainer_when_hired` — `trainer` non-null and
  `pool` empty.
- `test_staff_skills_are_on_the_display_scale` — every skill value is
  `0 <= v <= DISPLAY_MAX`. Proves the stored 1-100 never leaks (D1).
- `test_hire_fills_the_slot` — 200/201, then `GET` shows the trainer.
- `test_hire_an_already_hired_trainer_returns_409`.
- `test_hire_when_slot_occupied_returns_409`.
- `test_fire_empties_the_slot` — then `GET` shows the pool again.
- `test_fire_with_no_trainer_returns_409`.
- `test_hire_cannot_target_another_teams_trainer` — a trainer employed by
  another team returns 409, not 200. The authorisation case worth an
  explicit test.

### W8 — `frontend/`: the Staff screen
`api.ts` additions, `useStaff.ts`, `screens/Staff.tsx`, and the `App.tsx`
wiring, per **`frontend/`**.

**Test:** `frontend/` has no test setup in this repo — verify in the
browser per **Verification**. Do not introduce a test framework for this
ticket.

### W9 — documentation
Per **Documentation update** below. Land it as its own commit so the
README changes are reviewable separately from the code.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7 → W8 → W9.

The reasoning:

- **W1 first** because a new app must exist in `INSTALLED_APPS` and
  `testpaths` before any test in it runs at all. Skipping the `testpaths`
  line is the classic way to land a new app whose tests are green because
  they never execute.
- **W2 before W3** — generation returns model instances, so the model must
  exist. W2's `IntegrityError` test also pins the one-slot rule before any
  service relies on it.
- **W3 before W4** because the service tests need trainers to hire, and
  `top_up_pool` calls the generator.
- **W4 before W5** — `tick()` calls `top_up_pool`; building the callee
  first means W5 is a three-line change with a clear test rather than two
  moving parts at once.
- **W5 before W7** so the season-boundary behaviour is proven server-side
  before any of it is exposed over HTTP.
- **W6 before W7** because the API is hard to exercise by hand without a
  pool, and `seed_trainers` is how you get one.
- **W7 before W8** — the frontend needs real endpoints to call. Do not
  build the screen against a stub.
- **W9 last** so the READMEs describe what was actually built.

**Commit after every work item.** Each leaves the suite green: W1-W7 each
add their own passing tests, W8 is frontend-only, W9 is documentation.

## Documentation update (required, not optional)

**`staff/README.md` (new, in W1, completed in W9).** Sections:

- *What this app owns* — `Trainer`, the shared pool, hiring and firing.
  Explicitly **not** what a trainer *does* (that is #36) and **not** money
  (that is #69).
- *The one-slot rule* — why `team` is a `OneToOneField` on `Trainer`
  rather than an FK on `Team` (D2), and that the database enforces it.
- *Stored 1-100, displayed 0-10* — that trainer skills share riders'
  scale and go through `riders.display.to_display_scale`, and that
  storing 1-10 was considered and rejected (D1).
- *The pool is shared, and hiring is contended* — the
  `select_for_update()` without `skip_locked` plus the post-lock re-check,
  and why `skip_locked` is wrong here even though `claim_team` uses it
  (D3). Note that this is the app's one genuinely concurrent operation.
- *Generation guarantees the speciality* — the non-overlapping bands, the
  display-scale margin, and that the floor exists for #36's benefit (D5).
- *What `staff/` may import* — `core`, `teams`, `riders` only. Never
  `world/`, `api/`, `schedule/` or `racing/`. The season-boundary top-up
  is wired from `world/` calling in.
- *Future work* — fee and salary (#69), physio and scout slots, AI teams
  hiring (#45). One line each, pointing at the issue.

**`AGENTS.md`** — in the Game Domains table, change the `staff/` row from
*not yet* to **built**, `README.md`, and update its description to say
trainers are hireable and physio/scout are still to come. In the
*Dependency direction* block, `staff -> core, teams, riders` is already
listed; confirm it still reads correctly and leave it. Add `staff/` with
its `README.md` to the *Project Structure* tree.

**`riders/README.md`** — one line in the display-scale section noting that
`staff.Trainer` now shares the same stored 1-100 / displayed 0-10
convention and calls the same `to_display_scale`, so the mapping still has
exactly one implementation.

**`api/README.md`** — document the three new endpoints, their shapes, and
the 409-vs-400 split.

**`frontend/README.md`** — note that `/staff` is now a real screen rather
than a placeholder, and that it was built without a `design/` mockup by
following `Roster.tsx`'s card-and-bar composition.

**`world/README.md`** — one line: the season-boundary hook now has its
first consumer, the trainer pool top-up, and idempotency comes from
`process_transitions`' return value rather than from anything in `staff/`.

**Spec status** — set `specs/trainers-as-hireable-staff.md`'s `**Status:**`
to `implemented`. Per `AGENTS.md`, delete
`specs/trainers-as-hireable-staff.md` and
`specs/trainers-as-hireable-staff-plan.md` before opening the PR, once
every README above is updated.

## Verification

```bash
.venv/bin/python -m pytest
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_trainers --count 12
.venv/bin/python manage.py runserver
```

Then, logged in as a manager with a team, in the browser at `/staff`:

1. **The pool renders.** Twelve trainers, each with five bars. Confirm
   every card has one visibly tallest bar — that is D5 holding end to end,
   and it is the thing that silently breaks if the bands are ever made to
   overlap.
2. **Hire one.** The pool disappears and the trainer's card replaces it.
3. **Reload.** The trainer persists — proves the write landed, not just
   local state.
4. **Fire.** The pool returns *with that trainer in it* — count it; the row
   must survive, not vanish (D4).
5. **Re-hire the same trainer immediately.** Must succeed — the
   no-cooldown rule.

**The likeliest failure mode is the contended hire**, because it cannot
happen by clicking and will not show up in single-threaded tests. Check it
directly:

```bash
.venv/bin/python manage.py shell
```

```python
# Two teams, one trainer, two threads. Exactly one must win and the other
# must raise TrainerNotAvailable. A silent second success means the
# post-lock re-check in hire_trainer is missing or was moved before the
# lock (D3) — the exact defect the unit tests cannot see, because pytest
# runs each test in one transaction on one connection.
import threading
from staff.models import Trainer
from staff.services import hire_trainer, TrainerNotAvailable
from teams.models import Team

trainer = Trainer.objects.filter(team__isnull=True).first()
a, b = Team.objects.all()[:2]
outcomes = []

def attempt(team):
    from django.db import connection
    try:
        hire_trainer(team, trainer.pk)
        outcomes.append(("won", team.code))
    except TrainerNotAvailable:
        outcomes.append(("refused", team.code))
    finally:
        connection.close()

threads = [threading.Thread(target=attempt, args=(t,)) for t in (a, b)]
for t in threads: t.start()
for t in threads: t.join()
print(outcomes)   # exactly one "won", one "refused"
```

**Season boundary.** Use the mock clock to cross a boundary and confirm the
pool grows once:

```bash
.venv/bin/python manage.py shell -c "from staff.models import Trainer; print(Trainer.objects.count())"
# advance the mock clock past a season boundary, then:
.venv/bin/python manage.py tick
.venv/bin/python manage.py tick
.venv/bin/python manage.py shell -c "from staff.models import Trainer; print(Trainer.objects.count())"
```

The count must rise by exactly `TRAINERS_PER_SEASON_BOUNDARY` across
**both** ticks, not twice that. Two ticks is the point of the check — one
tick would pass even with the idempotency broken.

**Evidence that actually proves something:** the display-scale test
(W7) must be written against a trainer with a stored score above 10 —
otherwise it passes whether or not the mapping is applied, and proves
nothing. Same for the two-tick test: it must cross a real boundary, or it
passes trivially.

## Risks

| Risk | Mitigation |
|---|---|
| **Hiring races: two managers hire the same trainer and both succeed.** The most likely real defect, and invisible to the test suite because pytest runs each test in a single transaction on one connection. | `select_for_update()` with no `skip_locked`, and the `team_id is not None` re-check **after** the lock (D3). Verified by the threaded shell script in **Verification**, not by a unit test. |
| **A reader "simplifies" the hire lock to `skip_locked=True`** to match `claim_team`, turning a contended hire into a false "not available". | D3 states the difference and `staff/README.md` records it. `claim_team` wants *any* team; hiring wants *that* trainer. |
| **Trainer skills stored 1-10** because the spec says "1-10", losing the resolution #36 needs and adding a second scale to the codebase. | D1, plus the W7 test asserting the API never ships a value above `DISPLAY_MAX` — which only passes meaningfully if the stored value is larger. |
| **Generation bands drifted into overlap** by a later tuning edit, so the speciality stops being clearly highest and #36's premise quietly breaks. | `test_speciality_is_clearly_higher_on_the_display_scale` (W3) fails on any overlap, and the band constants carry comments saying the gap is load-bearing. |
| **Pool top-up double-fires**, or fires on every tick, flooding the pool. | Iterate `process_transitions`' return value (D6); `test_a_second_tick_does_not_top_up_again` (W5) is the guard. |
| **New app's tests never run** because `staff` was not added to `testpaths`, so the whole ticket looks green while unverified. | W1 does it, and `test_staff_app_is_installed` fails visibly if the app is misconfigured. Check the pytest summary's collected count actually rose. |
| **`staff/` imports `world/` or `schedule/`** to find the season boundary itself, inverting the dependency graph. | D6 wires it the other way: `world/` imports `staff/`. `staff/README.md`'s *What `staff/` may import* records it. |
| **A hidden rider trait leaks into the new serializer** by copying a rider serializer too literally. | `TrainerSerializer` is written field-by-field above; `Trainer` has no hidden traits to leak. Keep it an explicit `Serializer`, not a `ModelSerializer` with `fields = "__all__"`. |

## Open questions

None blocking.

Two observations, neither of which changes this plan — worth a follow-up
ticket rather than fixing here:

- **`riders/README.md` and `riders/generation.py` both describe
  `to_display_scale` as `round(value / 10)`, but the code is `value // 10`
  (floor)** — and `display.py`'s own docstring correctly says "Floors, not
  rounds". A stale doc in two places. This plan is written against the
  code's actual behaviour (floor), which is why the generation bands are
  chosen to clear a floor boundary rather than a rounding one.
- **`design/` has no Staff mockup**, so W8 has no visual reference. Handled
  by following `Roster.tsx`, and recorded in `frontend/README.md` so the
  next person knows the screen was not designed from an export.

# Season — Implementation Plan

**Spec:** `specs/season.md` · **Issue:** [#5](https://github.com/mario595/cycling-manager/issues/5) · **Status:** implemented
**Apps touched:** `schedule/` (**new**), `racing/`, `world/`, `api/`, `frontend/`, `config/`

## Context you need

Read `world/README.md` before anything else here. It describes a clock that was
built differently from how its own spec sounds, and that difference is the single
most important fact in this plan.

**What exists today:**

- `world/clocks.py` — a `Clock` ABC with one method, `now()`. `RealClock`
  (production, and the dev default) returns `timezone.now()` directly: **no
  state, no database row, no advancing**. `MockClock` (dev/test opt-in via the
  `GAME_CLOCK_CLASS` env var) reads the single `world.models.GameClock` row and
  can be moved by `manage.py mock_clock set|advance`.
- `world/services.py` — `now()` (the one sanctioned time read), `get_clock()`
  (resolves and caches the configured clock), and `tick()`.
- `world/services.tick()` — finds `scheduled` races whose `starts_at <= now()`,
  claims them with `SELECT ... FOR UPDATE` (flipping `scheduled → running`
  inside one transaction), then simulates them **outside** that transaction.
  Bounded by `GameClock.catch_up_max_races` (default 50). Writes a `TickRun`.
- `world/models.py` — `GameClock` (mock-clock value + the per-tick race cap) and
  `TickRun` (one row per tick).
- `racing/models.Race` — `name`, `course` JSON, wind settings, `seed`,
  `starts_at` (nullable game time), `status` (`scheduled`/`running`/`finished`/
  `failed`), `finished_at`. Index `race_due_idx` on `(status, starts_at)`.
- `racing/services.simulate_race(race, *, game_time)` — the only simulation
  entry point. `racing/` must never import `world/`.
- `api/` — one public endpoint, `GET /api/world/clock/` → `{"current": "..."}`,
  served by `ClockView` (`AllowAny`, overriding the project's `IsAuthenticated`
  default). `api/urls.py` is mounted at `/api/` in `config/urls.py` **above** the
  SPA catch-all.
- `frontend/src/useClock.ts` — polls the clock endpoint every 60 s and ticks
  client-side each second between polls. `Sidebar.tsx` renders the result,
  falling back to `TEAM.season` (`'SEASON 3 · WK 14'`) on error.
  `Layout.tsx` renders a mobile-only header; there is no desktop page header.
- Tests are pytest. `world/tests/conftest.py` forces `MockClock` for everything
  under `world/tests/` and resets `world.services._clock` around each test.

**What does not exist and is easy to assume does:**

- **There is no `schedule/` app.** This plan creates it.
- **There is no season, no week, no off-season, anywhere.** The season strings in
  the SPA are invented placeholder text in `frontend/src/placeholderData.ts`.
- **There is no race calendar (#7).** No race is created by any code path today;
  the first season will run twelve weeks with no races in it, exactly as
  `specs/season.md` says it should.
- **The clock does not advance and nothing "reaches" a moment.** `tick()` does
  not move time; it *processes what has become due*. This is the fact the
  next section is about.

**Repo rules this work is bound by:**

- Dependency direction (`AGENTS.md`): `world/` and `api/` may import anything;
  **nothing may import them.** So `schedule/` must not import `world/`, exactly
  as `racing/` does not.
- `race_engine/` imports nothing from Django. This plan does not touch the
  engine at all.
- Postgres in dev and prod. Tests run with `.venv/bin/python -m pytest`.
- A new app gets a `README.md`, an entry in `LOCAL_APPS`, and a `testpaths`
  entry in `pyproject.toml`, in the same change.

## Goal

When this is done:

- A `Season` row has a number, a start, an end twelve weeks later, and twelve
  `Week` rows, created by `manage.py load_season <file.json>` from an admin's
  JSON file.
- `schedule.services.current_position()` answers "which season and week is it?"
  — or "off-season after season N", or "no season has ever been declared" —
  from the clock's current time alone.
- A season opening and closing each happen exactly once, recorded as
  `SeasonTransition` rows written by the tick, and never by anyone looking at
  a page.
- A declared season cannot be edited or reloaded once it has started.
- `GET /api/schedule/position/` returns the current position, and the SPA shows
  `Season 1 · Week 3` / `Season 1 · Off-season` at the top of every page.
- A `Race` points at the `Week` it belongs to, and cannot be saved pointing at a
  `starts_at` outside that week.

## Design decisions (settled — implement these, do not substitute)

### 1. The current season and week are **derived from the clock**, not stored — load-bearing

This is the decision the rest of the plan hangs off, and it is the one most
likely to be got wrong, because `specs/season.md` is written in the language of
the clock's *original* design ("a season starts because the world's clock reached
its start moment").

That design is not what shipped. In production the clock is `RealClock`: it holds
no state and nothing advances it. `tick()` runs hourly and asks "what has become
due?" — it does not move time forward. There is therefore **nothing to store a
"current season" pointer on** that could be authoritative, and any such pointer
would be a cache of a pure function of `now()` that goes stale the moment a tick
is missed, the host sleeps, or two processes disagree.

So:

```python
# schedule/services.py
def current_position(at: datetime | None = None) -> Position
```

reads `now()` (defaulted, injectable for tests), finds the `Season` whose
`[starts_at, ends_at)` contains it, and computes the week from the offset. Two
queries at most, on an indexed range. **Do not** add a `Season.is_current`
boolean, a `CurrentSeason` singleton row, or a `WorldState.season_id` pointer.
A missed tick must never be able to make the game display the wrong week.

The endpoint and every read path use this function. Nothing reads a stored
"where are we" field, because there is not one.

### 2. Transitions are recorded, not depended on — and *that* is what the tick owns

Spec items 10 and 11 demand that starting and ending happen **exactly once** and
are not triggered by somebody looking at the game. Decision 1 makes the *display*
independent of any event firing — so what is the tick for?

It is for the side effects that later features will hang off the boundary:
promotion/relegation, contract renewal, salary reviews (all explicitly out of
scope here, `specs/season.md`). Those cannot be derived from `now()`; they must
happen once and leave a mark.

So the tick writes `SeasonTransition` rows — `(season, kind)` with
`kind ∈ {opened, closed}` — under a uniqueness constraint on exactly that pair.
Today nothing but the row itself results from a transition. That is deliberate
and must be said in the code: **the row is the hook, and it ships empty.**

`schedule.services.process_transitions(at)` is called from `world.services.tick()`
and:

1. finds every season with `starts_at <= at` and no `opened` row, oldest first,
   and writes one;
2. finds every season with `ends_at <= at` and no `closed` row, oldest first,
   and writes one.

Both run inside one transaction, and the **unique constraint is the exactly-once
guarantee** — not a check-then-insert, which races. See the code under
`schedule/services.py` below. **Do not** use `get_or_create` without catching
`IntegrityError`, and **do not** guard with an `if not exists` read outside a
transaction.

A tick that has been down for three weeks writes every transition it missed, in
order, on its next run. That is correct and wanted: a catch-up must not skip a
season boundary, or the features that later hook into it silently lose a cycle.

### 3. `Week` is a real row, because the calendar (#7) needs somewhere to hang

Spec item 4 is explicit that weeks are "a real period the game can place things
into", not a display derivation — and `specs/race-calendar.md` confirms it: a
season declares "which week and which day of the week each [race] falls on".

So `Week` is a model with a FK to `Season`, a `number` (1–12) and its own
`starts_at`/`ends_at`. Twelve rows are created with the season, in the same
transaction, by the loader.

**Do not** compute the week purely as `(now - season.starts_at).days // 7` and
skip the rows. The number *is* computed that way inside `current_position()` for
speed — but the rows must exist for `Race.week` to point at, and for #7 to place
races into next.

### 4. A season is declared by a JSON file loaded by a command, and is immutable once started

Spec items 8 and 9. `manage.py load_season path/to/season-1.json`:

```json
{
  "number": 1,
  "starts_at": "2027-03-01T00:00:00Z"
}
```

The command validates, creates the `Season` and its twelve `Week` rows in one
transaction, and prints what it made. Re-loading a file for a season that has
**already started** (`starts_at <= now()`) is a `CommandError`. Re-loading one
that has not started yet **replaces** it — a declared-but-not-started season is
still a draft, and an admin fixing a typo before it begins is the normal case.

**Do not** build a Django admin form, an API endpoint, or an interactive prompt
for this. `specs/season.md` rules an admin UI out explicitly, and the roadmap
made the same call on #8.

The file grows a `races` key when #7 lands. Write the loader so that an unknown
top-level key is **ignored with a warning**, not an error — this is the one place
a forward-compatibility allowance is worth it, because it is a hand-written admin
file and #7 is the very next issue.

### 5. Season numbers are unique and contiguity is checked, not enforced

`number` gets `unique=True`. Spec item 2 says numbers increase by one per season,
but the loader **warns** rather than refuses when a number skips (declaring
season 4 when 2 is the highest) — the admin may be reconstructing a world, and a
hard rule here buys nothing while being able to block a legitimate fix.

Overlapping date ranges are a different matter and **are** refused: two seasons
covering the same instant makes `current_position()` ambiguous, which is a real
defect rather than an odd-looking sequence. Use an exclusion check in the loader,
plus a `Season.clean()`; **do not** reach for a Postgres `ExclusionConstraint`
here — it needs the `btree_gist` extension, which is a migration-time database
privilege the deployment target is not yet known to have.

### 6. `Race.week` is the ownership link, and `starts_at` must sit inside it

Spec item 12: a race belongs to exactly one season and cannot be scheduled
outside its twelve weeks. The FK goes on `Race` pointing at `Week`, not at
`Season`: the week is the finer-grained truth and the season is reachable through
it (`race.week.season`). A race's season is never stored twice.

It is **nullable**, because every existing `Race` row has no week and because a
race simulated ad hoc in development is still useful. A null week means "not part
of any season", and such a race is unaffected by every rule here.

The containment rule is enforced in `Race.clean()` and called from
`Race.save()` — not by a database constraint, because the bound lives on a
different table (`Week.starts_at`/`ends_at`) and a `CheckConstraint` cannot
reach across rows.

**This puts a dependency on `racing/` importing `schedule/`**, which is new.
Record it in `AGENTS.md`: `racing -> riders, teams, race_engine, schedule`.
It is one-way and does not cycle — `schedule/` must not import `racing/`.

### 7. `world/` calls `schedule/`; `schedule/` never calls `world/`

Same seam as `racing/`. `schedule.services.current_position(at=None)` and
`process_transitions(at)` both take the time as a parameter, defaulting `at` to
`None` and resolving it through a **locally imported** `world.services.now()`
only in `current_position`.

Correction, because that is a contradiction as written: it is not acceptable for
`schedule/` to import `world/` at all. So:

- `process_transitions(at: datetime)` — `at` is **required**. `world.services.tick()`
  passes `now()`.
- `current_position(at: datetime)` — `at` is **required** too. The API view
  (in `api/`, which may import both) passes `now()`.

There is no default and no clock import anywhere in `schedule/`. This is what
keeps the app testable without a clock and keeps the dependency graph honest.
**Do not** add a convenience wrapper in `schedule/` that reads the clock.

### 8. The position is one API shape with an explicit `state`, not a nullable season

`GET /api/schedule/position/` returns one of three shapes, discriminated by a
`state` field:

```json
{"state": "in_season",  "season": 1, "week": 3,    "week_ends_at": "..."}
{"state": "off_season", "season": 1, "week": null, "week_ends_at": null}
{"state": "no_season",  "season": null, "week": null, "week_ends_at": null}
```

`off_season` carries the season that **just finished** (spec item 7). `no_season`
is the state before any season has ever been declared — distinct from the
off-season, because "Season 0 · Off-season" is a lie and the SPA must render
nothing rather than that.

**Do not** collapse these to "season is null means off-season". Two different
nulls meaning two different things is exactly the ambiguity that produces a
wrong label on a page.

The endpoint is `AllowAny`, matching the clock endpoint and for the same reason.

### 9. The SPA shows the position in a new page header, on every route

Spec: "at the top of the page", and explicitly **not** in the sidebar — the
sidebar's date display belongs to the clock and stays as it is.

`Layout.tsx` today renders a header only on mobile. Add a slim header bar that
renders on **both** breakpoints, carrying the position label; the existing
mobile header's contents stay where they are, with the position line added to
it rather than a second bar being stacked on top.

While loading, or on a failed fetch, the header renders **nothing** — no
placeholder, no `SEASON 3 · WK 14`. A failed season fetch must not invent a
season. This differs deliberately from the clock's fallback behaviour: a stale
date is harmless, a fabricated season number is not.

`DASHBOARD.eyebrow` in `placeholderData.ts` (`'SEASON 3 · WEEK 14 OF 38'`) is
still invented and still wrong. Replace its use in `Dashboard.tsx` with the real
position, and delete the key.

## Data model

### `schedule.models.Season` (new) — `schedule/migrations/0001_initial.py`

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `number` | `PositiveIntegerField` | no / no | — | `unique=True`, `db_index` implied by unique. Starts at 1. |
| `starts_at` | `DateTimeField` | no / no | — | **Game** time. Must be a week boundary (Monday 00:00 UTC) — validated in `clean()`, see below. |
| `ends_at` | `DateTimeField` | no / no | — | **Game** time. Derived: `starts_at + 12 weeks`. Stored, not computed on read, so range queries are indexable. |

Inherits `TimeStampedModel` (`core/models.py`) — `created_at`/`updated_at` are
**real** time, `starts_at`/`ends_at` are **game** time. Say so in the docstring,
exactly as `Race` does.

```python
SEASON_WEEKS = 12   # module-level constant in schedule/models.py
```

`Meta`:
```python
ordering = ["number"]
indexes = [models.Index(fields=["starts_at", "ends_at"], name="season_range_idx")]
```

`ends_at` is set in `save()` when not already set: `self.ends_at = self.starts_at + timedelta(weeks=SEASON_WEEKS)`.
Spec item 3: the end follows from the start and is not separately chosen — so the
loader never accepts an `ends_at` from the file.

`clean()` raises `ValidationError` when `starts_at` is not a Monday at 00:00:00
UTC (spec item 5 — the week boundary), and when the `[starts_at, ends_at)` range
overlaps another season's.

**Monday 00:00 UTC is the chosen boundary.** Any fixed choice satisfies the spec;
Monday is what "week 1" reads as to a European cycling audience, and UTC because
every other datetime in the project is UTC. State this in `schedule/README.md`
so #7 places its "day of the week" against a known anchor.

### `schedule.models.Week` (new) — same migration

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `season` | `ForeignKey(Season, on_delete=CASCADE, related_name="weeks")` | no | — | Cascade: a not-yet-started season being replaced takes its weeks with it. |
| `number` | `PositiveSmallIntegerField` | no / no | — | 1–12. |
| `starts_at` | `DateTimeField` | no / no | — | Game time. `season.starts_at + (number - 1) weeks`. |
| `ends_at` | `DateTimeField` | no / no | — | Game time. `starts_at + 1 week`. |

Not a `TimeStampedModel` — a `Week` is created only with its season and never
touched again; two real-time audit columns on twelve rows per season is noise.

`Meta`:
```python
ordering = ["season", "number"]
constraints = [
    models.UniqueConstraint(fields=["season", "number"], name="unique_week_per_season"),
]
indexes = [models.Index(fields=["starts_at", "ends_at"], name="week_range_idx")]
```

### `schedule.models.SeasonTransition` (new) — same migration

The exactly-once record. See decision 2.

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `season` | `ForeignKey(Season, on_delete=CASCADE, related_name="transitions")` | no | — | |
| `kind` | `CharField(max_length=10, choices=Kind)` | no / no | — | `opened` / `closed`. |
| `occurred_at` | `DateTimeField` | no / no | — | **Game** time the boundary was crossed — the season's own `starts_at`/`ends_at`, **not** the moment the tick noticed. A late tick must record the boundary, not its own lateness. |
| `recorded_at` | `DateTimeField` | no / no | `auto_now_add` | **Real** time the tick wrote it. The gap between this and `occurred_at` is how late the tick was. |

```python
class Kind(models.TextChoices):
    OPENED = "opened", "Opened"
    CLOSED = "closed", "Closed"
```

`Meta`:
```python
ordering = ["-occurred_at"]
constraints = [
    models.UniqueConstraint(fields=["season", "kind"], name="unique_transition_per_season"),
]
```

**That constraint is the exactly-once guarantee.** It is load-bearing; without it
two concurrent ticks both write an `opened` row and every future feature hooked
to the boundary fires twice.

### `racing.models.Race` — one field, `racing/migrations/0003_race_week.py`

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `week` | `ForeignKey("schedule.Week", on_delete=PROTECT, null=True, blank=True, related_name="races")` | yes / yes | `None` | Null = not part of any season. `PROTECT`, not `CASCADE`: deleting a week must never silently delete the races and results run in it. |

`PROTECT` also means a started season can never be deleted once it has races,
which is the behaviour spec item 9 wants and gets for free.

Plus `clean()` on `Race` enforcing containment (decision 6) — see the `racing/`
section below.

## `schedule/services.py` (new)

```python
@dataclass(frozen=True)
class Position:
    state: str                  # "in_season" | "off_season" | "no_season"
    season: Season | None
    week: Week | None

def current_position(at: datetime) -> Position: ...
def process_transitions(at: datetime) -> list[SeasonTransition]: ...
```

`current_position` — the read path, hit on every page load:

```python
def current_position(at: datetime) -> Position:
    """Where the world is, derived entirely from `at`. No stored pointer;
    see schedule/README.md — a missed tick must never be able to make the
    game display the wrong week.

    `at` is required and never defaulted from the clock: schedule/ must not
    import world/ (AGENTS.md).
    """
    season = Season.objects.filter(starts_at__lte=at, ends_at__gt=at).first()
    if season is not None:
        week = season.weeks.filter(starts_at__lte=at, ends_at__gt=at).first()
        return Position(state="in_season", season=season, week=week)

    finished = Season.objects.filter(ends_at__lte=at).order_by("-ends_at").first()
    if finished is not None:
        return Position(state="off_season", season=finished, week=None)

    return Position(state="no_season", season=None, week=None)
```

Three things that are easy to get wrong:

- **`ends_at__gt=at`, not `__gte`.** The range is half-open. A season ending at
  exactly `T` and the next starting at exactly `T` must not both match, and the
  instant `T` belongs to the new one.
- **The `off_season` branch looks at `ends_at__lte`, not "the highest number".**
  Seasons are declared in advance, so the highest-numbered season may not have
  started yet; "the one that just finished" is a date question.
- **A `Season` with no matching `Week` returns `week=None` while still
  `in_season`.** That cannot happen if the loader did its job, but the query must
  not raise if it ever does — a missing week row is a display gap, not a 500.

`process_transitions` — the write path, called only from the tick:

```python
def process_transitions(at: datetime) -> list[SeasonTransition]:
    """Record every season boundary crossed at or before `at` that has not
    been recorded yet, oldest first.

    Exactly-once comes from the unique constraint on (season, kind), NOT
    from the existence checks below — those only keep the common case cheap.
    A concurrent tick loses the race at the INSERT and moves on.

    Today a transition is only a row. It is the hook later features
    (promotion/relegation, contracts, salaries) attach to; it ships empty
    on purpose — see specs/season.md, "Out of scope".
    """
    written: list[SeasonTransition] = []
    plans = [
        (SeasonTransition.Kind.OPENED,
         Season.objects.filter(starts_at__lte=at).exclude(
             transitions__kind=SeasonTransition.Kind.OPENED).order_by("starts_at")),
        (SeasonTransition.Kind.CLOSED,
         Season.objects.filter(ends_at__lte=at).exclude(
             transitions__kind=SeasonTransition.Kind.CLOSED).order_by("ends_at")),
    ]
    for kind, queryset in plans:
        for season in queryset:
            moment = season.starts_at if kind == SeasonTransition.Kind.OPENED else season.ends_at
            try:
                with transaction.atomic():
                    written.append(SeasonTransition.objects.create(
                        season=season, kind=kind, occurred_at=moment,
                    ))
            except IntegrityError:
                # Another tick got there first. Correct outcome, not an error.
                continue
    return written
```

- **Each `create` is in its own `atomic()` block.** An `IntegrityError` marks the
  whole transaction unusable in Django; catching it *inside* one outer
  transaction and continuing would fail on the next statement with
  `TransactionManagementError`. This is the classic mistake here.
- **`occurred_at` is the season's own boundary**, never `at`. A tick three weeks
  late records when the season actually ended.
- The `opened` pass runs before the `closed` pass so that a catch-up spanning a
  whole season writes `opened` then `closed` in a sensible order.

## `world/services.py` — one call added to `tick()`

`world/` may import `schedule/`; the reverse is forbidden. Inside `tick()`,
**before** claiming races:

```python
from schedule.services import process_transitions
...
def tick() -> TickRun:
    max_races = GameClock.load().catch_up_max_races
    at = now()
    transitions = process_transitions(at)
    ...
    run.seasons_opened = sum(1 for t in transitions if t.kind == SeasonTransition.Kind.OPENED)
    run.seasons_closed = sum(1 for t in transitions if t.kind == SeasonTransition.Kind.CLOSED)
```

Transitions first, because a race in week 1 of a season that has just opened
should be processed in a world that has already recorded the opening.

Note `tick()` currently calls `now()` in three places (`_claim`, `_execute`, and
implicitly). Against `RealClock` those are three different instants. Read it
**once** into `at` at the top of `tick()` and thread it through `_claim(limit, at)`
and `_execute(ids, tick, at)`. This is a small correctness improvement the season
work makes worth doing, not a refactor for its own sake — leave everything else
in the module alone.

### `world.models.TickRun` — two fields, `world/migrations/0003_tickrun_seasons.py`

| Field | Type | Null/blank | Default |
|---|---|---|---|
| `seasons_opened` | `PositiveSmallIntegerField` | no / no | `0` |
| `seasons_closed` | `PositiveSmallIntegerField` | no / no | `0` |

Spec item 10's "did anything happen" must cover season boundaries too, or a
transition that failed to fire leaves no trace anywhere.

## `racing/models.py` — the containment rule

```python
def clean(self):
    super().clean()
    if self.week_id and self.starts_at:
        if not (self.week.starts_at <= self.starts_at < self.week.ends_at):
            raise ValidationError({
                "starts_at": f"must fall inside week {self.week.number} of season "
                             f"{self.week.season.number} "
                             f"({self.week.starts_at} to {self.week.ends_at})",
            })

def save(self, *args, **kwargs):
    self.full_clean(exclude=None) if ... # NO — see below
```

**Do not** call `full_clean()` from `save()`. It validates every field, turns
every existing `Race.objects.create(...)` in tests and fixtures into a
potential failure, and runs uniqueness queries on every write. Instead call the
single check explicitly:

```python
def save(self, *args, **kwargs):
    self.clean()          # only the containment rule; see clean() above
    super().save(*args, **kwargs)
```

`clean()` here does nothing at all when `week` is null, which every race today
is — so this is inert for existing rows and existing tests, and only bites when
#7 starts placing races into weeks.

Import `schedule.models` at module level in `racing/models.py`? **No** — the FK
is declared as the string `"schedule.Week"` and `clean()` reaches the week
through `self.week`, so `racing/` needs no import of `schedule/` in code at all.
The app-level dependency is real and goes in `AGENTS.md`, but the module stays
import-free of it. Keep it that way.

## `schedule/management/commands/load_season.py` (new)

```
manage.py load_season seasons/season-1.json
manage.py load_season seasons/season-1.json --replace
```

Behaviour:

1. Parse the JSON. Required keys: `number` (int ≥ 1), `starts_at` (ISO 8601).
   Unknown top-level keys are **warned about and ignored** (decision 4).
2. `starts_at` naive → made aware in UTC. Not a Monday 00:00:00 UTC →
   `CommandError` naming the nearest valid Monday.
3. If a season with that `number` exists:
   - it has started (`starts_at <= now()`) → `CommandError`, refuse absolutely,
     no `--replace` escape. Spec item 9.
   - it has not started → require `--replace`, then delete it (cascading its
     weeks) and recreate. Without the flag, `CommandError` saying the season
     exists and how to replace it.
4. Refuse an overlap with any other season's range (`CommandError`).
5. Warn — do not refuse — when `number` is not one more than the highest existing
   (decision 5).
6. Create the `Season` and its twelve `Week` rows in **one** `transaction.atomic()`.
7. Print the season number, its start, its end, and the twelve week boundaries.

The command reads the clock via `world.services.now()` for step 3 — that is
fine and correct: this is a **management command in `schedule/`**, and
`schedule/`'s *library* code is what must stay clock-free. Import it inside
`handle()`, not at module scope, and say why in a comment. If that reads as too
fine a distinction to the implementer: the rule protects `schedule/services.py`
and `schedule/models.py`; the command is an entry point, like `world/`'s own.

A sample file lands at `seasons/season-1.example.json` (**new** directory,
committed) so the format has somewhere to be read from.

## `api/` — the position endpoint

- `api/serializers.py` — add `PositionSerializer`: `state` (char), `season`
  (int, nullable), `week` (int, nullable), `week_ends_at` (datetime, nullable).
  Built from a plain dict in the view, matching how `ClockSerializer` is used.
- `api/views.py` — `PositionView(APIView)`, `permission_classes = [AllowAny]`:

```python
def get(self, request):
    position = current_position(now())
    return Response(PositionSerializer({
        "state": position.state,
        "season": position.season.number if position.season else None,
        "week": position.week.number if position.week else None,
        "week_ends_at": position.week.ends_at if position.week else None,
    }).data)
```

`api/` imports both `world.services.now` and `schedule.services.current_position`
— it is one of the two apps allowed to.

- `api/urls.py` — `path("schedule/position/", PositionView.as_view(), name="position")`.

`week_ends_at` is included because the SPA will want it for #7's calendar and it
costs nothing now. It is the only speculative field in this plan; everything else
is used by something this feature ships.

## `frontend/` changes

- `src/api.ts` — add `Position` (`state: 'in_season' | 'off_season' | 'no_season'`,
  `season: number | null`, `week: number | null`, `week_ends_at: string | null`)
  and `getPosition()`.
- `src/useSeason.ts` (**new**) — polls `/api/schedule/position/` every 60 s,
  same shape and lifecycle as `useClock.ts`. **No client-side interpolation**:
  unlike the clock, the week number does not visibly tick, so there is nothing to
  interpolate. Returns `{position, loading, error}`.
- `src/seasonLabel.ts` (**new**) — one pure function, so the label is written
  once and testable:

```ts
export function seasonLabel(position: Position | null): string | null {
  if (!position) return null
  if (position.state === 'no_season') return null
  if (position.state === 'off_season') return `Season ${position.season} · Off-season`
  return `Season ${position.season} · Week ${position.week}`
}
```

  `null` means render nothing (decision 9).
- `src/components/Layout.tsx` — a page header bar rendered on **both**
  breakpoints, showing the label. On mobile it goes into the existing header
  alongside the team name; on desktop it is a new slim bar above `<Outlet />`.
  Match the existing inline-style approach and `font.mono` for the label —
  the file has no CSS modules and this plan does not introduce any.
- `src/screens/Dashboard.tsx` — replace `DASHBOARD.eyebrow` with the real label
  (falling back to rendering no eyebrow when it is `null`).
- `src/placeholderData.ts` — delete the `eyebrow` key. Leave `TEAM.season`: it
  is still the clock's sidebar fallback and the comment there already says so.

## Work items

### W1 — `schedule/`: create the app
`startapp schedule`, delete the scaffold's `views.py` and `tests.py`, add
`"schedule"` to `LOCAL_APPS` in `config/settings/base.py`, add `schedule` to
`testpaths` in `pyproject.toml`, write `schedule/README.md` (sections per
*Documentation update*), create `schedule/tests/__init__.py`.
**Test:** `schedule/tests/test_app.py::test_schedule_app_is_installed` asserts
`apps.is_installed("schedule")`.

### W2 — `schedule/models.py`: `Season`, `Week`, `SeasonTransition`
All three models, `SEASON_WEEKS = 12`, `Season.save()` deriving `ends_at`,
`Season.clean()` (Monday boundary + overlap), migration `0001_initial`,
`schedule/admin.py` registering all three read-only.
**Load-bearing:** the `unique_transition_per_season` constraint — it is the
exactly-once guarantee, not an optimisation.
**Test:** `schedule/tests/test_models.py::test_ends_at_is_twelve_weeks_after_start`;
`::test_rejects_a_start_that_is_not_a_monday_midnight`;
`::test_rejects_an_overlapping_season`;
`::test_duplicate_transition_is_rejected` (create `(season, opened)` twice,
assert `IntegrityError`).

### W3 — `schedule/services.py`: `current_position`
The read path and its `Position` dataclass. No transitions yet.
**Load-bearing:** the half-open range (`ends_at__gt`), and the `off_season`
branch keying off `ends_at`, not the highest number.
**Test:** `schedule/tests/test_services.py` —
`::test_in_season_reports_the_right_week` (parametrise weeks 1, 6 and 12);
`::test_the_instant_a_season_ends_is_off_season`;
`::test_the_instant_a_season_starts_is_week_one` (the boundary both ways);
`::test_off_season_names_the_season_that_just_finished` (with a *later* season
already declared but not started — this is the case the naive "highest number"
implementation gets wrong);
`::test_no_season_before_anything_is_declared`.

### W4 — `schedule/services.py`: `process_transitions`
The write path, the per-create `atomic()` blocks, the `IntegrityError` catch.
**Load-bearing:** one `atomic()` **per create**, not one around the loop.
**Test:** `schedule/tests/test_services.py` —
`::test_records_opened_when_the_start_has_passed`;
`::test_records_nothing_twice` (call it twice, assert one row);
`::test_catch_up_records_every_missed_boundary_in_order` (a season entirely in
the past plus one running now; assert `opened`+`closed` for the first and
`opened` for the second, and that `occurred_at` equals each season's own
boundary, **not** the `at` passed in).

### W5 — `world/`: wire transitions into the tick
`process_transitions(at)` called first in `tick()`; `at = now()` read once and
threaded through `_claim` and `_execute`; `seasons_opened`/`seasons_closed` on
`TickRun` with migration `0003_tickrun_seasons`; the `tick` command's summary
line extended.
**Load-bearing:** transitions before race claiming.
**Test:** `world/tests/test_services.py::test_tick_records_a_season_opening`;
`::test_tick_does_not_record_a_transition_twice`;
`world/tests/test_tick_command.py::test_tick_summary_reports_season_transitions`.

### W6 — `racing/`: `Race.week` and the containment rule
The FK (`PROTECT`, nullable), `clean()`, `save()` calling `clean()` only,
migration `0003_race_week`, `week` added to `RaceAdmin.list_display`/`list_filter`,
docstring updated to say `week` is the season link.
**Load-bearing:** `clean()` must be a no-op when `week` is null — every existing
race is, and this must not break them.
**Test:** `racing/tests.py::test_race_without_a_week_saves_unchanged`;
`::test_race_inside_its_week_saves`;
`::test_race_outside_its_week_is_rejected` (one second after `week.ends_at`);
`::test_race_at_the_exact_week_start_is_accepted` (the half-open boundary again).

### W7 — `schedule/management/commands/load_season.py`
The command, its validation, `--replace`, the sample file at
`seasons/season-1.example.json`.
**Load-bearing:** refusing outright to touch a season that has already started,
with no `--replace` escape.
**Test:** `schedule/tests/test_load_season.py::test_creates_a_season_and_twelve_weeks`;
`::test_refuses_a_started_season_even_with_replace`;
`::test_replaces_a_declared_but_unstarted_season`;
`::test_refuses_a_non_monday_start`;
`::test_refuses_an_overlap`;
`::test_ignores_unknown_keys_with_a_warning` (a `races` key, per decision 4).
Use `MockClock` for the "has it started" checks — copy `world/tests/conftest.py`'s
`_use_mock_clock` fixture into `schedule/tests/conftest.py` rather than importing
it across packages.

### W8 — `api/`: the position endpoint
`PositionSerializer`, `PositionView`, the URL, `api/README.md` updated.
**Load-bearing:** `AllowAny` (the project default is `IsAuthenticated`).
**Test:** `api/tests.py::test_position_endpoint_reports_the_current_week`
(unauthenticated `APIClient`, `MockClock`);
`::test_position_endpoint_reports_no_season_when_none_declared` asserting
`state == "no_season"` and a 200, **not** a 404.

### W9 — `frontend/`: show the position
`api.ts`, `useSeason.ts`, `seasonLabel.ts`, `Layout.tsx`, `Dashboard.tsx`,
`placeholderData.ts`.
**Test:** there is no test runner in `frontend/` and this plan does not add one.
`npm --prefix frontend run build` (which runs `tsc -b`) must pass; the real
proof is the manual check in *Verification*.

### W10 — Documentation
`AGENTS.md` (app table, dependency direction), `racing/README.md`,
`world/README.md`, root `README.md`. `schedule/README.md` landed with W1.
**Test:** none. Reviewed, not tested.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7 → W8 → W9 → W10.

The reasoning, since the obvious order would be "loader first, so there is data":

- **W2 before anything that reads seasons**, because every later item needs the
  tables.
- **W3 before W4** deliberately. `current_position` is the whole player-visible
  feature and it depends on nothing but the models — proving it first means that
  when the transition machinery misbehaves later, the display is already known
  good. The reverse order leaves two suspects.
- **W5 before W6 and W7**, because the tick is where the exactly-once claim
  actually lives and it is worth having under test before the surface area grows.
- **W7 after W6** so the loader is written against a `Race.week` that exists —
  the loader does not create races today, but #7 will extend this very command,
  and writing it against the finished schema avoids a rewrite one issue later.
- **W8 and W9 last**: player-visible, and dependent on everything else being
  right.

**Commit at each W.** The repo is green after every one: W1–W4 are purely
additive and nothing calls them; W5 is the first wiring; W6 is inert while every
race has a null week.

## Documentation update (required, not optional)

### `schedule/README.md` (new, lands with W1)

Sections:
- **What this app owns** — seasons, weeks, the transition record. Not races
  (that is `racing/`), not the clock (`world/`), and not the calendar yet (#7).
- **Derived, not stored** — the decision-1 rule, stated as the app's central
  invariant: there is no "current season" field, `current_position()` is a pure
  function of the time passed in, and a missed tick can never make the game show
  the wrong week. Say explicitly that adding a cached pointer would be a
  regression, not an optimisation.
- **The week boundary** — Monday 00:00 UTC, why it is fixed, and that #7 places
  its "day of the week" against this anchor.
- **Exactly-once** — the `(season, kind)` unique constraint, the per-create
  `atomic()` block, and that `occurred_at` is the boundary rather than the tick's
  own time.
- **The transition hook ships empty** — nothing happens at a boundary today; the
  row exists for promotion/relegation, contracts and salaries to attach to.
- **Declaring a season** — the file format, the command, the immutability rule,
  and that the file grows a `races` key when #7 lands.
- **What `schedule/` may import** (`core`, and nothing else it needs today) and
  **what may import `schedule/`** (`racing`, `world`, `api`). State plainly that
  `schedule/` must never import `world/`, and that `load_season.py` reading the
  clock inside `handle()` is the deliberate, documented exception.

### `AGENTS.md` (W10)

- App table: `schedule/` → **built**, `README.md`. The current description
  ("Seasons, race types (classics, stage races, TTs), scheduling, race-specific
  rules") over-promises; narrow it to what exists: "Seasons and their twelve
  weeks. The race calendar (#7) lands here next."
- Dependency direction block: change `racing -> riders, teams, race_engine` to
  `racing -> riders, teams, race_engine, schedule`, and add
  `schedule -> core`. This is a real change to the documented graph and must not
  be left implicit.

### `racing/README.md` (W10)

- *What lives here* table: add `week` to the `Race` row, noting it is the link to
  `schedule.Week` and is nullable (a race outside any season).
- New short subsection **"A race belongs to a week"** — the containment rule,
  that it is enforced in `clean()` rather than a database constraint and why
  (the bound lives on another table), and that `PROTECT` is deliberate.

### `world/README.md` (W10)

- *How a tick works*: add the transition pass as step 0, before claiming races,
  and say why it runs first.
- *What this app owns*: mention that the tick now also records season boundaries,
  and point at `schedule/README.md` for what that means.

### `README.md` (root, W10)

One line under running it: declaring a season with
`manage.py load_season seasons/season-1.example.json`.

## Verification

Unit tests:

```bash
docker compose up -d
.venv/bin/python manage.py migrate
.venv/bin/python -m pytest
```

Also run the migration check, since this adds three migrations across two apps:

```bash
.venv/bin/python manage.py makemigrations --check --dry-run
```

**The end-to-end check that actually proves the feature.** It must be run against
the mock clock, because the whole point is watching a season boundary go past:

```bash
export GAME_CLOCK_CLASS=world.clocks.MockClock

.venv/bin/python manage.py mock_clock set 2027-02-22T12:00
.venv/bin/python manage.py load_season seasons/season-1.example.json   # starts 2027-03-01
.venv/bin/python manage.py tick

.venv/bin/python manage.py shell -c "
from schedule.services import current_position
from schedule.models import SeasonTransition
from world.services import now
p = current_position(now())
print(p.state, p.season and p.season.number, p.week and p.week.number)
print(list(SeasonTransition.objects.values_list('season__number', 'kind')))
"
```

Expect `no_season None None` and an empty transition list — the season is
declared but has not started, and nothing has fired.

Then step across the boundary:

```bash
.venv/bin/python manage.py mock_clock set 2027-03-01T00:00
.venv/bin/python manage.py tick     # expect "seasons opened 1"
.venv/bin/python manage.py mock_clock advance --by 14d
.venv/bin/python manage.py tick     # expect "seasons opened 0" — the hook fires once
```

`current_position` must now report `in_season 1 3`. **Then run `tick` a third
time and assert the transition count is still exactly one** — a passing first
tick proves nothing about exactly-once.

Finally step past the end (twelve weeks from `2027-03-01` is `2027-05-24T00:00`):

```bash
.venv/bin/python manage.py mock_clock set 2027-05-24T00:00
.venv/bin/python manage.py tick
```

`current_position` must report `off_season 1 None`, and there must be exactly one
`opened` and one `closed` row. The instant a season ends being off-season rather
than week 13 is the half-open-range bug this catches.

**The concurrency check**, which no unit test covers honestly — this is what
proves decision 2:

```bash
.venv/bin/python manage.py mock_clock set 2027-03-01T00:00
.venv/bin/python manage.py tick & .venv/bin/python manage.py tick & wait
.venv/bin/python manage.py shell -c "
from schedule.models import SeasonTransition
print(SeasonTransition.objects.count())
"
```

The count must be exactly 1. A count of 2 means the unique constraint is missing
or the code is doing check-then-insert. Note that a *crash* in one of the two
ticks is also a failure here — the `IntegrityError` must be caught and swallowed,
not propagated, so both processes exit 0.

**Frontend:**

```bash
npm --prefix frontend run build && .venv/bin/python manage.py runserver
```

Load `http://127.0.0.1:8000/` with the clock inside season 1 and confirm the
header reads `Season 1 · Week 3` on desktop **and** on a narrow viewport. Set the
clock past `ends_at` and confirm it becomes `Season 1 · Off-season` within 60
seconds. Then **delete every season** and confirm the header renders *nothing* —
not `Season null`, not the old `SEASON 3 · WEEK 14 OF 38`. That last check is the
one that catches decision 9 being implemented as a clock-style fallback.

## Risks

| Risk | Mitigation |
|---|---|
| **A "current season" field gets added.** The single likeliest mistake: the spec's language implies a season becomes current when the clock reaches it, and a `Season.is_current` boolean is the obvious reading. Against `RealClock` it goes stale on the first missed tick and the game shows the wrong week. | Decision 1, stated again as the central invariant in `schedule/README.md`. In review: grep `schedule/` for `is_current`, `current =`, and any boolean or FK that names the present. There must be none. |
| **The week boundary implemented with `>=` on both ends.** `ends_at__gte` makes the instant a season ends belong to both that season's week 12 and the off-season, and `current_position` returns whichever the query planner reached first. | The half-open rule in decision 1's code, plus `::test_the_instant_a_season_ends_is_off_season` and `::test_race_at_the_exact_week_start_is_accepted`. |
| **`IntegrityError` caught inside one outer transaction.** The natural way to write `process_transitions` is one `atomic()` around the loop. It passes single-process tests and then fails under concurrency with `TransactionManagementError` instead of continuing. | Decision 2's code, the per-create `atomic()` block, and the two-process check in *Verification* — which fails loudly on this, since one tick exits non-zero. |
| **`full_clean()` called from `Race.save()`.** The obvious way to make `clean()` run. It validates every field on every write, breaking existing fixtures and tests that create partial races. | W6 names it explicitly. In review: `racing/models.py` must call `self.clean()`, never `self.full_clean()`. |
| **The SPA invents a season while loading.** Copying `useClock`'s fallback pattern gives `SEASON 3 · WK 14` on a failed fetch — a fabricated season number shown as real. | Decision 9, `seasonLabel` returning `null`, and the "delete every season" step in *Verification*. |
| **`schedule/` grows a clock import.** `current_position()` would read much more nicely with `at=None` defaulting to `now()`, and someone will add it. It inverts the dependency direction. | Decision 7: `at` is required on both public functions. In review: `grep -rn "world" schedule/ --include=*.py` must match only `load_season.py`'s in-function import and the README. |
| **Twelve weeks of empty season looks broken.** The first season ships with no races (no #7 yet), so a player sees a week number and nothing else. | Accepted and explicitly expected by `specs/season.md`. #7 is the next issue in the roadmap's Phase 1; nothing is built here to paper over it. |
| **Nobody declares season 2.** The world sits in the off-season indefinitely. | That is the specified behaviour (item 11), not a failure. `TickRun.seasons_opened` staying 0 is the operator's signal; `world/README.md` gains no new alerting and none is wanted yet. |

## Open questions

None blocking.

One thing worth flagging to the spec's author rather than the implementer: the
spec describes season transitions in terms of the clock *reaching* a moment,
which matched the game clock's original design. What shipped is a stateless
production clock plus an hourly processing tick, so this plan delivers the same
player-visible behaviour by deriving position from the time and using the tick
only for the once-only record. Nothing in `specs/season.md`'s *In scope* or
*Decisions taken* changes as a result — item 10's "exactly once, not triggered by
anybody looking at the game" is satisfied by `SeasonTransition` — but the
mechanism is not the one the prose pictures, and `schedule/README.md` says so.

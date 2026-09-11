# Race calendar — Implementation Plan

**Spec:** `specs/race-calendar.md` · **Issue:** [#7](https://github.com/mario595/cycling-manager/issues/7) · **Status:** proposed
**Apps touched:** `schedule/`, `racing/`, `api/`, `frontend/`

## Context you need

This feature is an **extension of #5**, not a new thing beside it. Read
`specs/season-plan.md` first — specifically decisions 3, 4 and 6 and the
`load_season` section. Everything here plugs into machinery that plan builds.

### This plan assumes #5 has landed

#5 ([season](https://github.com/mario595/cycling-manager/issues/5)) is being
built in parallel. **Do not start this until its PR is merged.** The exact
surface this plan consumes:

| From #5 | Used here for |
|---|---|
| `schedule.models.Season` — `number`, `starts_at`, `ends_at` | The thing races are declared inside |
| `schedule.models.Week` — `season` FK, `number` (1–12), `starts_at`, `ends_at` | What a race is placed into |
| `schedule.models.SEASON_WEEKS = 12` | Validating a week number |
| **Monday 00:00 UTC** is the week anchor | What "day of the week" means |
| `racing.models.Race.week` — nullable FK to `Week`, `PROTECT` | Already exists; this plan fills it in |
| `Race.clean()` — containment: `week.starts_at <= starts_at < week.ends_at` | Already exists; this plan must satisfy it |
| `schedule/management/commands/load_season.py` | Extended here, not replaced |
| `schedule.services.current_position(at)` | The calendar endpoint reuses it |
| `seasons/season-1.example.json` | Grows a `races` key |
| `schedule/tests/conftest.py` — `_use_mock_clock` | Reused by this plan's tests |

If any of those names differ when you start, **reconcile before writing code**
— rename in this plan, do not build a parallel structure.

### What exists today (verified in the repo)

- `racing.models.Race` — `name`, `course` (JSONField: a list of
  `{length, gradient}`), `wind_enabled`, `wind_band`, `seed`, `starts_at`
  (nullable game time), `status` (`scheduled`/`running`/`finished`/`failed`),
  `finished_at`. Index `race_due_idx` on `(status, starts_at)`.
- `racing.adapters.to_engine_course(race)` — builds the engine `Course` from
  `race.course` by reading `s["length"]` and `s["gradient"]` off each element.
  **This is the shape a calendar-authored course must produce.**
- `race_engine.config._parse_course` — the engine's own validation of the same
  shape: a non-empty list, each segment needing `length` and `gradient`, both
  numeric, length strictly positive. This plan re-implements that validation in
  `schedule/` rather than importing it (see decision 4).
- `world.services.tick()` — claims `scheduled` races whose `starts_at <= now()`
  and simulates them. **Nothing in this plan touches the tick.** Placing a race
  with a `starts_at` is the entire mechanism by which it happens.
- `racing.services.simulate_race` — races every `Rider` in the database.
  The comment there ("Every rider in the database races: there is no squad
  selection yet (#37) and no calendar to say who is entered") is about squad
  selection, **not** about this feature. Leave it alone: spec item 4 says every
  team races every race, so "everyone races" is the correct behaviour, and
  narrowing it to a squad is #37.
- `api/` — one endpoint, `GET /api/world/clock/`. `api/urls.py` is mounted
  **above** the SPA catch-all in `config/urls.py`; a route added below it would
  return `index.html` instead of JSON.
- `frontend/src/navigation.ts` — already has `{ path: '/calendar', name: 'Calendar' }`
  under `RACING`. It currently renders `Placeholder`. Adding the screen is one
  line in `SCREENS` in `src/App.tsx`.
- `design/Cycling Manager UI.dc.html` has **no calendar screen**. The mockup
  contains Dashboard, Roster and Race day only. This screen is designed from the
  existing primitives (`Card`, `CardHeader`, `PageBody` in
  `src/components/primitives.tsx`) and `src/theme.ts`, not lifted from a mockup.

### Repo rules this work is bound by

- Dependency direction (`AGENTS.md`, as #5 leaves it): `racing -> riders, teams,
  race_engine, schedule`; `schedule -> core`. **`schedule/` must not import
  `racing/`** — that would cycle. Decision 2 is how this plan places races
  without breaking it.
- `race_engine/` imports nothing from Django, and only `racing/adapters.py`
  imports the engine. This plan does not touch the engine and must not add a
  second importer of it.
- Postgres in dev and prod. Tests are pytest, `.venv/bin/python -m pytest`.
- Race logs are records, never regenerated.

## Goal

When this is done:

- A season's JSON declaration carries a `races` list: each entry naming a week,
  a day of that week, a time, a race name, and an inline course.
- `manage.py load_season` creates the `Season`, its twelve `Week` rows **and**
  every declared `Race`, in one transaction — or creates none of them.
- A declared race has a `starts_at` on the right day, and the existing tick
  simulates it when that moment arrives, with no new tick machinery.
- Loading refuses: two races on one day, a week outside 1–12, a malformed
  course, and any change at all to a season that has already started.
- `GET /api/schedule/calendar/` returns the whole current season's twelve weeks
  with the race on each and its status.
- `/calendar` in the SPA renders those twelve weeks, showing empty weeks as
  deliberately empty and off-season as plainly nothing.

## Design decisions (settled — implement these, do not substitute)

### 1. A race's position is authored as `(week, day, time)` and stored as `(week FK, starts_at)` — load-bearing

The file says where a race is in season-relative terms:

```json
{ "week": 3, "day": "sunday", "time": "14:00", "name": "...", "course": [...] }
```

The database stores the resolved instant. `Race.starts_at` is computed at load
time:

```python
starts_at = week.starts_at + timedelta(days=DAY_INDEX[day], hours=h, minutes=m)
```

`week.starts_at` is a Monday 00:00 UTC (#5's anchor), so `DAY_INDEX` is
`{"monday": 0, ..., "sunday": 6}`.

**Do not** store the day-of-week or the week number on `Race` as extra columns.
`Race.week` plus `Race.starts_at` already carry it, `race.week.number` is the
week and `race.starts_at.weekday()` is the day. A third representation is a
third thing to keep consistent.

**Do not** compute `starts_at` from `season.starts_at + (week - 1) * 7 days`
and skip the `Week` row lookup. The row is the FK target and #5's
`Race.clean()` validates containment against it — resolving from the season
directly means a `week` FK and a `starts_at` that were derived independently,
which is exactly the drift the containment check exists to catch.

**Minutes are allowed but the tick is hourly.** `world/README.md` states cron
runs `tick` hourly. A race declared at `14:30` starts when the 15:00 tick runs.
That is acceptable and not worth solving; `schedule/README.md` says so, and the
loader **warns** when a time has non-zero minutes rather than refusing — an
admin may deliberately want ordering within an hour once a day holds more than
one race, which it cannot today.

### 2. `schedule/` builds races through a callable it is handed, never by importing `racing/`

The dependency graph after #5 is `racing -> schedule`. `schedule/` importing
`racing.models.Race` would cycle, and Django would resolve it (string FKs, lazy
app loading) which makes it worse: it would work, silently, and the documented
graph would be a lie.

So the loader declares what it wants and the command wires it up:

```python
# schedule/loaders.py — no racing import anywhere in this module
def build_season(data: dict, *, create_race: Callable[..., Any]) -> LoadResult
```

and the **management command** — an entry point, not library code — does the
import inside `handle()`:

```python
# schedule/management/commands/load_season.py
def handle(self, *args, **options):
    from racing.models import Race        # entry point, not library code —
    from world.services import now        # see schedule/README.md
```

This is the same exception #5 already carved out for `load_season` reading the
clock, and it is documented in the same place. **Do not** add
`from racing.models import Race` at the top of any module under `schedule/`,
and **do not** solve this with a signal, a registry, or `django.apps.apps.get_model`
— `get_model` is an import in disguise and hides the dependency from `grep`.

If that feels over-careful for one import: the rule is what keeps `schedule/`
loadable and testable without `racing/`, and the loader's tests exercise it with
a stub `create_race`, which is what makes them fast and focused.

### 3. One race per day is enforced in the loader, and backed by a database constraint

Spec item 2 and the "one race per day, full stop" rule.

Two layers, deliberately:

- **The loader** rejects a duplicate `(week, day)` pair before touching the
  database, with a message naming both races. This is the one an admin sees.
- **A `UniqueConstraint` on `Race`** over `(week, race_day)` where `race_day` is
  a stored `DateField`. This is what makes it true rather than merely checked.

That means one new column on `Race`, which contradicts decision 1's "do not add
a third representation" — so be clear about why it is not one: `race_day` is not
an authoring input and is never read to decide anything. It exists **solely** as
the constraint's target, because Postgres cannot build a unique index on
`DATE(starts_at)` through Django's `UniqueConstraint` without a functional index
expression, and the `Race` model is the only place the value can live. Set it in
`Race.save()` from `starts_at`, never by hand:

```python
self.race_day = self.starts_at.date() if self.starts_at else None
```

**Do not** make it editable in the admin, and **do not** read it anywhere.

Note the constraint is scoped to `(week, race_day)`, not `race_day` alone: a
race with a null week (an ad-hoc development race, which #5 explicitly allows)
must not collide with a season race, and Postgres treats nulls as distinct in a
unique index, which gives exactly that.

### 4. The course is validated in `schedule/`, duplicating the engine's rules on purpose

`race_engine.config._parse_course` already validates this shape. Importing it
would make `schedule/` the second importer of the engine, breaking the rule that
`racing/adapters.py` is the only one (`AGENTS.md`, `racing/README.md`).

Routing through `racing/` instead would mean `schedule -> racing`, which
decision 2 just ruled out.

So `schedule/loaders.py` re-implements the check — about fifteen lines:

```python
def _parse_course(raw: Any, path: str) -> list[dict[str, float]]:
    if not isinstance(raw, list) or not raw:
        raise SeasonFileError(f"{path} must be a non-empty list of segments")
    segments = []
    for i, seg in enumerate(raw):
        at = f"{path}[{i}]"
        if not isinstance(seg, dict):
            raise SeasonFileError(f"{at} must be an object")
        for key in ("length", "gradient"):
            if key not in seg:
                raise SeasonFileError(f"{at} is missing '{key}'")
        try:
            length, gradient = float(seg["length"]), float(seg["gradient"])
        except (TypeError, ValueError):
            raise SeasonFileError(f"{at}: length and gradient must be numbers")
        if length <= 0:
            raise SeasonFileError(f"{at}.length must be positive")
        segments.append({"length": length, "gradient": gradient})
    return segments
```

This is a genuine duplication and it is the right trade: fifteen lines of
validation against either a broken dependency rule or a new cross-app call path.
Say so in `schedule/README.md` so the next reader does not "fix" it.

The output shape is `{"length": float, "gradient": float}` — matching what
`racing.adapters.to_engine_course` reads. Normalising to floats at load time
means a course written with integer lengths is stored as floats, so the stored
JSON and the engine's view of it never differ.

### 5. Wind is per-race and optional, defaulting to the model's defaults

`Race` already has `wind_enabled` (default `True`) and `wind_band` (blank).
A race entry may carry an optional `wind` object, in the same shape the engine's
config uses:

```json
"wind": { "enabled": false }
"wind": { "band": "strong" }
```

Absent means the model defaults: wind on, band rolled from the seed. Validate
`band` against `{"calm", "light", "moderate", "strong"}` — the same set as
`race_engine.config._VALID_WIND_BANDS`, re-stated in `schedule/` for the same
reason as decision 4.

An optional `seed` (int) is accepted too, for a reproducible race. Absent means
null, which is the current behaviour.

This is a small surface and it is included because without it, every race a
season declares is identical in weather terms and there is no way to author the
windy classic the engine's wind work was built for.

### 6. The whole file is one transaction, and a started season is untouchable

#5's loader already creates `Season` + twelve `Week` rows in one
`transaction.atomic()`. Races go **inside that same block**. A file with a
malformed course in race 7 of 9 leaves no season, no weeks and no races — the
admin fixes the file and re-runs.

`--replace` on a not-yet-started season deletes it; `Week` cascades from
`Season`, but `Race.week` is `PROTECT`, so the delete **will raise
`ProtectedError`** once a season has races. That is #5's plan getting the
behaviour "for free" in a way that now breaks the replace path it also wants.

Resolve it explicitly: `--replace` deletes the season's races first, then the
season:

```python
Race.objects.filter(week__season=existing).delete()
existing.delete()
```

This is safe **only** because step 3 of the command has already refused any
season that has started, so no race being deleted can have been simulated.
Assert that rather than assume it: the delete is guarded by the same
`starts_at > now()` check, and `test_replace_refuses_after_start` proves it.

**Do not** change `Race.week` to `CASCADE` to make this simpler. `PROTECT` is
what stops a started season's results being deleted by an admin mistake, and
that is worth more than one explicit line in the replace path.

### 7. The calendar endpoint returns the whole season, shaped by week

`GET /api/schedule/calendar/` — one request, the whole season, because spec
item 5 says the full calendar is visible from the start and the screen renders
all twelve weeks at once. Paging or per-week fetching would be twelve requests
for a page that always shows everything.

```json
{
  "state": "in_season",
  "season": 1,
  "current_week": 3,
  "weeks": [
    {"number": 1, "starts_at": "...", "races": [
      {"id": 4, "name": "Omloop", "starts_at": "...", "status": "finished", "distance_km": 187.0}
    ]},
    {"number": 2, "starts_at": "...", "races": []},
    ...
  ]
}
```

- `state` and `season` mirror `/api/schedule/position/`'s vocabulary exactly
  (`in_season` / `off_season` / `no_season`), reusing
  `schedule.services.current_position`. Do not invent a fourth state.
- **`weeks` is always twelve entries when there is a season**, with `races: []`
  for an empty week. The client must not have to infer a gap from a missing
  key — spec: "weeks with no race are visibly weeks with no race, not gaps that
  look like missing data".
- **`races` is a list, zero to seven entries, ordered by `starts_at`.** The
  spec's rule is one race per *day*, not per week, so a Saturday/Sunday classics
  weekend is legal and the payload must be able to carry it. See *Open
  questions* — this is the one reading of the spec worth confirming.
- `off_season` and `no_season` return `weeks: []`. The spec's "no season, no
  calendar" — the screen renders the empty state, not a grid.
- `status` is `Race.status` verbatim (`scheduled`/`running`/`finished`/`failed`).
  **Do not** map it to the spec's three player-facing words in the API; the
  mapping is presentation and lives in the SPA (decision 8). `failed` has no
  player-facing word at all and the API must not have to invent one.
- `distance_km` is summed from the course server-side —
  `sum(s["length"] for s in race.course) / 1000` — because the client would
  otherwise need the whole course JSON to show one number.
- `AllowAny`, matching `/api/world/clock/` and `/api/schedule/position/` and
  for the same reason: no login flow exists in the SPA yet.

One query for the season, one for the weeks with `prefetch_related("races")`.
Twelve weeks and at most twelve races — no pagination, no N+1 worth chasing
beyond that prefetch.

### 8. Status words are mapped in the SPA, and `failed` is not hidden

Spec item 6: not yet happened / happening today / finished.

```ts
// frontend/src/raceStatus.ts
scheduled -> 'Upcoming'
running   -> 'Racing now'
finished  -> 'Result in'
failed    -> 'Not run'
```

`failed` is a real state the tick can produce (`world/services._execute` sets it
when a simulation throws) and the spec did not anticipate it. Showing "Not run"
is honest; folding it into "finished" would show a player a completed race with
no result, which is the worst of the options. Flag it in
`schedule/README.md` as a state the spec does not name.

### 9. The calendar screen is built from existing primitives, not a mockup

There is no calendar in `design/Cycling Manager UI.dc.html`. Rather than invent
a new visual language, the screen is a single `Card` containing twelve rows —
one per week — using the same row rhythm as the Roster screen's table and the
tokens in `src/theme.ts`. No new colours, no new primitive components.

A week row: the week number in `font.mono`, then either the race (day, name,
distance, status pill) or the words "No racing" in `color.muted`. The current
week is marked with `color.accentWash` as its background, matching how the
roster marks "your team".

**Do not** build a month-grid calendar. The season is twelve weeks with at most
one race each; a grid would be mostly empty cells, and the spec asks for "twelve
weeks, each showing whether a race falls on it".

Race rows **do not link anywhere** — the per-race screen is explicitly out of
scope and tracked as #47. Do not make them look clickable.

## Data model

### `racing.models.Race` — one field, `racing/migrations/0004_race_race_day.py`

(Numbered 0004 because #5's plan lands `0003_race_week`. Check the directory and
renumber if it differs.)

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `race_day` | `DateField` | yes / yes | `None` | **Not an input.** Derived in `save()` from `starts_at`. Exists only as the target of the one-race-per-day constraint (decision 3). |

`Meta` gains:

```python
constraints = [
    models.UniqueConstraint(
        fields=["week", "race_day"], name="one_race_per_day_per_week",
    ),
]
```

`save()` gains one line before `super().save()`, alongside the `self.clean()`
call #5 adds:

```python
self.race_day = self.starts_at.date() if self.starts_at else None
```

The migration must **backfill** `race_day` for existing rows, or the constraint
is built over stale nulls. Every existing race has a null `week`, so nulls are
harmless for the constraint — but a race with a `starts_at` and a null
`race_day` is an inconsistency that will confuse the next reader. Include a
`RunPython` backfill:

```python
def backfill(apps, schema_editor):
    Race = apps.get_model("racing", "Race")
    for race in Race.objects.filter(starts_at__isnull=False, race_day__isnull=True):
        Race.objects.filter(pk=race.pk).update(race_day=race.starts_at.date())
```

with `migrations.RunPython(backfill, migrations.RunPython.noop)`.

**No other model changes.** `Race.week`, `Race.starts_at` and `Race.clean()`'s
containment rule all arrive with #5, and `Season`/`Week` need nothing new.

## The season file format

`seasons/season-1.example.json` grows a `races` key:

```json
{
  "number": 1,
  "starts_at": "2027-03-01T00:00:00Z",
  "races": [
    {
      "week": 1,
      "day": "sunday",
      "time": "14:00",
      "name": "Opening Classic",
      "course": [
        { "length": 40000, "gradient": 0.0 },
        { "length": 12000, "gradient": 5.0 },
        { "length": 6000,  "gradient": -5.0 },
        { "length": 8000,  "gradient": 0.0 }
      ]
    },
    {
      "week": 3,
      "day": "saturday",
      "time": "13:00",
      "name": "Windy Coastal",
      "wind": { "band": "strong" },
      "seed": 12345,
      "course": [
        { "length": 60000, "gradient": 0.0 },
        { "length": 15000, "gradient": 1.0 }
      ]
    }
  ]
}
```

Per race entry:

| Key | Required | Type | Rules |
|---|---|---|---|
| `week` | yes | int | 1 ≤ week ≤ `SEASON_WEEKS` (12) |
| `day` | yes | str | lowercase `monday`…`sunday` |
| `time` | yes | str | `HH:MM`, 24-hour. Non-zero minutes warn (decision 1). |
| `name` | yes | str | non-empty, ≤ 150 chars (`Race.name`'s `max_length`) |
| `course` | yes | list | non-empty, decision 4's rules |
| `wind` | no | object | `{"enabled": bool, "band": str\|null}`, decision 5 |
| `seed` | no | int | stored on `Race.seed` |

`races` itself is optional and may be empty — a season with no racing is still a
valid season, and is exactly what #5 ships with.

## `schedule/loaders.py` (new)

#5's plan puts parsing inline in the command. Extract it here as this feature
lands, because the command is about to grow from ~40 lines to ~150 and the
parsing is the part worth testing without a database.

```python
class SeasonFileError(ValueError):
    """A season declaration file is malformed. Message is admin-facing."""

@dataclass(frozen=True)
class RaceDeclaration:
    week: int
    day: str
    time: time
    name: str
    course: list[dict[str, float]]
    wind_enabled: bool
    wind_band: str | None
    seed: int | None

@dataclass(frozen=True)
class SeasonDeclaration:
    number: int
    starts_at: datetime
    races: list[RaceDeclaration]
    warnings: list[str]

def parse_season_file(data: dict) -> SeasonDeclaration: ...
```

`parse_season_file` does **all** validation that does not need the database:
shape, types, ranges, the day names, the course, the wind band, and the
duplicate `(week, day)` check. It touches no models and imports nothing from
`racing/` or `world/` — which is what lets its tests run without a database.

The duplicate check, which is decision 3's admin-facing layer:

```python
seen: dict[tuple[int, str], str] = {}
for race in races:
    key = (race.week, race.day)
    if key in seen:
        raise SeasonFileError(
            f"two races on week {race.week} {race.day}: "
            f"{seen[key]!r} and {race.name!r}; at most one race per day"
        )
    seen[key] = race.name
```

Then the placement, which does need the database and lives in the command:

```python
def create_races(season, declarations, *, create_race) -> list:
    """`create_race` is `racing.models.Race.objects.create`, injected by the
    command. schedule/ must not import racing/ — see schedule/README.md."""
    weeks = {w.number: w for w in season.weeks.all()}
    created = []
    for d in declarations:
        week = weeks[d.week]            # existence guaranteed by parse-time range check
        starts_at = week.starts_at + timedelta(
            days=DAY_INDEX[d.day], hours=d.time.hour, minutes=d.time.minute,
        )
        created.append(create_race(
            week=week, name=d.name, course=d.course, starts_at=starts_at,
            wind_enabled=d.wind_enabled, wind_band=d.wind_band or "", seed=d.seed,
        ))
    return created
```

`starts_at` lands inside `[week.starts_at, week.ends_at)` by construction —
`DAY_INDEX` is 0–6 and the time is under 24 hours — so #5's `Race.clean()`
containment check passes. That is the check proving this arithmetic is right,
which is why `Race.objects.create` is used rather than `bulk_create`:
**`bulk_create` does not call `save()`**, so neither `clean()` nor the
`race_day` assignment would run. At most twelve rows; the loop is fine.

## `schedule/management/commands/load_season.py` — extended

#5's steps 1–7 stand. Changes:

- Step 1: `races` is now a **known** key, parsed rather than warned about. The
  unknown-key warning stays for everything else.
- Step 3's `--replace` path deletes races before the season (decision 6).
- Step 6's transaction now also creates the races.
- Step 7's output gains a line per race: `week 3 sat 13:00 — Windy Coastal (75.0 km)`,
  and a summary count.
- Warnings from `parse_season_file` are printed with `self.style.WARNING`.

The two imports inside `handle()` — `racing.models.Race` and
`world.services.now` — with the comment decision 2 requires.

## `api/` — the calendar endpoint

- `api/serializers.py` — `CalendarRaceSerializer` (`id`, `name`, `starts_at`,
  `status`, `distance_km`), `CalendarWeekSerializer` (`number`, `starts_at`,
  `race` — nullable, nested), `CalendarSerializer` (`state`, `season`,
  `current_week`, `weeks`). Built from plain dicts in the view, matching how
  `ClockSerializer` is already used.
- `api/views.py` — `CalendarView(APIView)`, `permission_classes = [AllowAny]`:

```python
def get(self, request):
    position = current_position(now())
    if position.season is None or position.state != "in_season":
        return Response(CalendarSerializer({
            "state": position.state,
            "season": position.season.number if position.season else None,
            "current_week": None,
            "weeks": [],
        }).data)

    weeks = position.season.weeks.prefetch_related("races").order_by("number")
    return Response(CalendarSerializer({
        "state": position.state,
        "season": position.season.number,
        "current_week": position.week.number if position.week else None,
        "weeks": [_week_payload(w) for w in weeks],
    }).data)
```

`_week_payload(week)` returns `{"number", "starts_at", "races": [...]}`, with
`races` built from `week.races.all()` sorted by `starts_at` — a list, not a
single object, per decision 7. An empty week is `races: []`, never a missing
key and never `null`.

- `api/urls.py` — `path("schedule/calendar/", CalendarView.as_view(), name="calendar")`.

## `frontend/` changes

- `src/api.ts` — `CalendarRace`, `CalendarWeek`, `Calendar` types and
  `getCalendar()`.
- `src/raceStatus.ts` (**new**) — decision 8's map, one pure function
  `raceStatusLabel(status: string): string`, plus a `raceStatusTone` returning
  which theme colour the pill uses (`color.muted` for scheduled, `color.accent`
  for running, `color.positive` for finished, `color.negative` for failed).
- `src/useCalendar.ts` (**new**) — fetches once on mount and polls every 60 s,
  the same lifecycle as `useClock.ts` / `useSeason.ts`. Returns
  `{calendar, loading, error}`. No client-side interpolation.
- `src/screens/Calendar.tsx` (**new**) — decision 9's screen. Four states:
  loading (render nothing, matching `useSeason`'s discipline), error (a short
  "Couldn't load the calendar" line — **not** invented data), `no_season` /
  `off_season` (the empty state, naming the season that finished when there is
  one), and `in_season` (the twelve rows).
- `src/App.tsx` — one line: `'/calendar': Calendar` in `SCREENS`.

The day label comes from the race's `starts_at`, formatted client-side
(`toLocaleDateString` with `{weekday: 'short'}` and `{hour, minute}`), not sent
by the API — the instant is the truth and the client already formats the clock.

## Work items

### W1 — `schedule/loaders.py`: parse the file — DONE
`SeasonFileError`, `RaceDeclaration`, `SeasonDeclaration`, `parse_season_file`,
`DAY_INDEX`, `_parse_course`, wind and seed parsing, the duplicate-day check.
Move #5's inline season parsing here at the same time, leaving the command
calling into it.
**Load-bearing:** no import of `racing/`, `world/` or `race_engine/` anywhere in
this module — that is what lets these tests run with no database.
**Test:** `schedule/tests/test_loaders.py` (no `django_db` marker on any of
these) —
`::test_parses_a_race_entry`;
`::test_rejects_a_week_outside_the_season` (0 and 13);
`::test_rejects_an_unknown_day`;
`::test_rejects_a_malformed_time`;
`::test_rejects_two_races_on_the_same_day` (asserting both names in the message);
`::test_accepts_two_races_in_one_week_on_different_days`;
`::test_rejects_an_empty_course`;
`::test_rejects_a_non_positive_segment_length`;
`::test_rejects_an_unknown_wind_band`;
`::test_warns_on_non_zero_minutes`;
`::test_races_key_is_optional`.

### W2 — `racing/`: `race_day` and the one-race-per-day constraint — DONE
The `DateField`, the `save()` assignment, the `UniqueConstraint`, migration
`0004_race_race_day` with the `RunPython` backfill.
**Load-bearing:** the constraint is `(week, race_day)`, not `race_day` alone —
null weeks must not collide.
**Test:** `racing/tests.py::test_race_day_is_derived_from_starts_at`;
`::test_two_races_on_one_day_of_one_week_are_rejected` (assert `IntegrityError`);
`::test_two_races_on_different_days_of_one_week_are_accepted`;
`::test_two_weekless_races_on_the_same_date_are_accepted` (the null-week case —
this is the one a `race_day`-only constraint breaks).

### W3 — `schedule/loaders.py`: `create_races` — DONE
The placement function and its injected `create_race`.
**Load-bearing:** `create_race` is injected, never imported; and it must be
`objects.create`, not `bulk_create` — `bulk_create` skips `save()` and so skips
both `clean()` and `race_day`.
**Test:** `schedule/tests/test_loaders.py` (these need `django_db`) —
`::test_places_a_race_on_the_right_instant` (week 3 sunday 14:00 of a season
starting 2027-03-01 is 2027-03-21T14:00Z — compute it by hand in the test, do
not re-derive it with the same arithmetic the code uses);
`::test_every_placed_race_satisfies_its_week_containment` (place one race on
each of the seven days of week 12 and call `full_clean()` on each — this is the
test that catches an off-by-one in `DAY_INDEX` or the week anchor).

### W4 — `load_season`: create races from the file
The command's extension: `races` parsed not warned, races created inside the
existing transaction, the `--replace` race deletion, the output lines.
**Load-bearing:** the `racing` and `world` imports are inside `handle()`; and
`--replace` deletes races before the season, guarded by the not-yet-started
check.
**Test:** `schedule/tests/test_load_season.py` —
`::test_creates_the_declared_races`;
`::test_a_malformed_race_creates_no_season_at_all` (a good race then a broken
one; assert `Season.objects.count() == 0` — this is the transaction test);
`::test_replace_deletes_the_previous_races`;
`::test_replace_refuses_after_start` (assert the season and its races survive);
`::test_races_key_is_optional_end_to_end` (a #5-era file still loads).

### W5 — `api/`: the calendar endpoint
`CalendarRaceSerializer`, `CalendarWeekSerializer`, `CalendarSerializer`,
`CalendarView`, the URL, `api/README.md`.
**Load-bearing:** twelve week entries always, `races: []` for an empty week —
not a shorter list; and `AllowAny`.
**Test:** `api/tests.py::test_calendar_returns_twelve_weeks`
(one race declared, assert `len(weeks) == 12` and exactly one non-empty
`races`);
`::test_calendar_reports_off_season_with_no_weeks`;
`::test_calendar_reports_no_season_before_any_is_declared` (200, not 404);
`::test_calendar_race_carries_status_and_distance`;
`::test_calendar_is_public` (unauthenticated client, 200).

### W6 — `frontend/`: the calendar screen
`api.ts`, `raceStatus.ts`, `useCalendar.ts`, `screens/Calendar.tsx`, the
`SCREENS` line in `App.tsx`.
**Test:** no test runner in `frontend/`, and this plan does not add one.
`npm --prefix frontend run build` (which runs `tsc -b`) must pass; the proof is
*Verification*.

### W7 — Documentation
`schedule/README.md`, `racing/README.md`, `frontend/README.md`, `AGENTS.md`,
root `README.md`. Sections named under *Documentation update*.
**Test:** none. Reviewed, not tested.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7.

- **W1 first and alone**, because it is the whole validation surface and it is
  database-free. Every rule an admin can break is provable before a single row
  exists, and a failure in W3 or W4 afterwards is unambiguously a placement or
  wiring problem rather than a parsing one.
- **W2 before W3.** `create_races` calls `save()`, which sets `race_day` and
  trips the constraint. Landing the column first means W3's tests fail for real
  reasons.
- **W3 before W4** so the arithmetic is proved directly, with a stub
  `create_race`, before the command wraps a transaction and a file around it.
  The reverse order debugs placement through two layers.
- **W4 before W5** because the endpoint needs data a real load produced, and the
  end-to-end check in *Verification* runs the command.
- **W6 last**, dependent on a working endpoint.

**Commit at each W.** The repo is green after every one: W1 is additive and
called only by its tests; W2 is inert for every existing race (all have null
weeks); W3 is called only by tests until W4.

## Documentation update (required, not optional)

### `schedule/README.md`

Extend the file #5 creates. New or changed sections:

- **What this app owns** — add the calendar: which races a season holds and
  where they sit. Still not the race itself (`racing/`) and not the tick
  (`world/`).
- **Declaring a season** — the `races` key, the full per-entry table from *The
  season file format* above, and a worked example. Replace #5's "the file grows
  a `races` key when #7 lands" with the fact that it has.
- **Placing a race** (new) — `(week, day, time)` in, `(week FK, starts_at)`
  stored. The Monday 00:00 UTC anchor and `DAY_INDEX`. That minutes are allowed
  but the tick is hourly, so a `14:30` race starts at the 15:00 tick.
- **One race per day** (new) — the two layers, and that `race_day` exists only
  as the constraint's target and is read by nothing.
- **Why the course is validated twice** (new) — decision 4, stated plainly so
  the duplication is not "fixed" into a rule violation.
- **What `schedule/` may import** — extend #5's section: `racing.models.Race`
  and `world.services.now` are imported **inside `handle()`** in
  `load_season.py` only, and `schedule/loaders.py` imports neither. Say that
  `apps.get_model` is not an acceptable way around this.
- **A status the spec does not name** (new) — `failed`, and that the SPA shows
  it as "Not run".

### `racing/README.md`

- *What lives here* table: add `race_day` to the `Race` row — derived, not
  authored, existing only for the one-race-per-day constraint.
- The "A race belongs to a week" subsection #5 adds: extend it with the
  constraint and with the fact that races are created by
  `schedule/`'s `load_season`, through an injected callable rather than an
  import, and why.

### `frontend/README.md`

- The route table: `/calendar` moves from "Placeholder" to "Built — twelve weeks
  from the API".
- *Where the data comes from*: the calendar is the first screen with no
  placeholder data at all. Note that its loading and error states render nothing
  rather than inventing a season, matching `useSeason`.

### `AGENTS.md`

- App table: `schedule/` description becomes "Seasons, their twelve weeks, and
  the race calendar declared within them." (#5 narrows it to seasons; this
  widens it back by exactly one feature.)
- Dependency direction: **no change.** `schedule -> core` still holds, because
  the `racing` and `world` imports are inside a management command's `handle()`.
  State that explicitly in the block's surrounding prose so a reader does not
  think it was overlooked.

### `README.md` (root)

The `load_season` line #5 adds gains a note that the example file now declares
races.

## Verification

Unit tests and the migration check:

```bash
docker compose up -d
.venv/bin/python manage.py migrate
.venv/bin/python -m pytest
.venv/bin/python manage.py makemigrations --check --dry-run
```

**The end-to-end check that actually proves the feature.** It needs riders in
the database, because `simulate_race` races every rider and raises on an empty
table:

```bash
export GAME_CLOCK_CLASS=world.clocks.MockClock

.venv/bin/python manage.py mock_clock set 2027-02-22T12:00
.venv/bin/python manage.py load_season seasons/season-1.example.json
```

Confirm the output lists each race with its week, day and distance. Then:

```bash
.venv/bin/python manage.py shell -c "
from racing.models import Race
for r in Race.objects.filter(week__isnull=False).order_by('starts_at'):
    print(r.week.season.number, r.week.number, r.starts_at.strftime('%a %Y-%m-%d %H:%M'), r.name)
"
```

**The day names printed must match the `day` values in the file.** That is the
check that catches the single likeliest bug in this feature — an off-by-one
between `DAY_INDEX` and the Monday anchor, which puts every race one day out and
is invisible in any test that derives the expected instant with the same
arithmetic as the code.

Then watch one race actually run, which is the proof that placement and the
existing tick fit together:

```bash
.venv/bin/python manage.py mock_clock advance --to-next
.venv/bin/python manage.py tick
.venv/bin/python manage.py shell -c "
from racing.models import Race
r = Race.objects.filter(week__isnull=False).order_by('starts_at').first()
print(r.name, r.status, r.results.count())
"
```

Expect `finished` and a non-zero result count. **A `failed` status here is a
real failure of this feature**, not an engine problem — it almost certainly
means the course JSON the loader stored is not the shape
`adapters.to_engine_course` reads.

The one-race-per-day rule, which no green path exercises:

```bash
# add a second race on the same week+day in a copy of the example file, then:
.venv/bin/python manage.py load_season /tmp/clash.json --replace
```

Must fail with a message naming both races, and leave the previous season
**intact** — check `Season.objects.count()` is unchanged and the original races
still exist. A partially-applied file is the failure mode decision 6 exists to
prevent.

The immutability rule:

```bash
.venv/bin/python manage.py mock_clock set 2027-03-02T12:00   # inside season 1
.venv/bin/python manage.py load_season seasons/season-1.example.json --replace
```

Must be refused, and the simulated race's results must still be there.

**Frontend:**

```bash
npm --prefix frontend run build && .venv/bin/python manage.py runserver
```

Open `/calendar` with the clock inside season 1 and confirm: twelve week rows,
the weeks with races showing day and name, the weeks without showing "No
racing" rather than being absent, the current week highlighted, and the already-
simulated race showing "Result in" while later ones show "Upcoming". Then set
the clock past the season's end and confirm the screen shows the off-season
empty state rather than a grid of twelve empty weeks.

## Risks

| Risk | Mitigation |
|---|---|
| **The day-of-week is off by one.** `DAY_INDEX` anchored to Sunday, or a week's `starts_at` not actually a Monday, puts every race a day out. A test that computes the expected instant with `week.starts_at + timedelta(days=DAY_INDEX[day])` passes regardless — it asserts the code against itself. | W3's `::test_places_a_race_on_the_right_instant` uses a **hand-computed literal** (`2027-03-21T14:00Z`), and *Verification* prints `%a` day names for comparison against the file. Both are needed; neither alone is enough. |
| **`schedule/` grows a top-level `racing` import.** The injected callable reads as ceremony for one import, and Django will resolve the direct import without complaint, so nothing fails — the documented dependency graph just becomes false. | Decision 2. In review: `grep -rn "racing\|world" schedule/ --include=*.py` must match only inside `load_season.handle()` and the README. `apps.get_model` counts as a violation and the README says so. |
| **`bulk_create` used for the races.** The obvious optimisation for a dozen inserts. It bypasses `save()`, so `race_day` is never set and `clean()`'s containment check never runs — the constraint then sits over nulls and silently permits two races on a day. | W3 names it. In review: `create_races` must call the injected callable per race. The `::test_two_races_on_one_day...` test only catches it if the rows went through `save()`, so this is a review check, not a test one. |
| **`--replace` hits `ProtectedError`.** #5's plan gives `Race.week` `PROTECT` and separately wants `--replace` to delete an unstarted season. The first season file anyone replaces will crash. | Decision 6's explicit race deletion, and `::test_replace_deletes_the_previous_races`. Do not change the FK to `CASCADE`. |
| **The empty week disappears from the response.** Building `weeks` from `Race` rows rather than from `Week` rows gives however many weeks have races. The screen then shows three weeks and looks broken — the exact thing the spec called out. | Decision 7, W5's `::test_calendar_returns_twelve_weeks`, and the *Verification* step that counts rows on the page. |
| **A course that loads but will not simulate.** The loader's validation and `adapters.to_engine_course`'s expectations could drift, and nothing catches it until a race runs and is marked `failed` — hours later, in a tick. | *Verification* runs one race to completion. Decision 4's normalisation to floats with the exact `{"length", "gradient"}` keys is what keeps the shapes identical; the duplication note in `schedule/README.md` is what stops someone changing one side. |
| **Every team races every race, and there are no squads.** A player sees a calendar implying their team rides everything, which is true today and will stop being true with #37. | Accepted; it is spec item 4 and explicitly what the spec wants. `simulate_race`'s existing comment already flags the #37 seam. Nothing here pre-empts it. |
| **A season declared with no races looks like the calendar is broken.** The #5-era example file has no `races` key and loads fine. | The screen's "No racing" per week is the answer, and `::test_races_key_is_optional_end_to_end` keeps the old file valid. |

## Open questions

None blocking.

One thing the spec's author may want to confirm rather than the implementer: the
spec's rule is *at most one race per **day***, and it is written throughout as
though that means one per week ("twelve weeks, each showing whether a race falls
on it"). This plan takes the literal rule — a week may hold up to seven races on
different days — because the stricter reading would forbid a perfectly ordinary
Saturday/Sunday classics weekend for no stated reason. The API and the screen
both carry a list per week as a result. If one-per-week was actually intended,
say so and it becomes a one-line check in `parse_season_file` plus a simpler
payload.

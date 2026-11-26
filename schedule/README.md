# Schedule — seasons, weeks, and the race calendar

## What this app owns

`Season`, `Week`, `SeasonTransition` and `WeekTransition` — the numbered
periods racing happens inside, and the exactly-once record of when a
season opens or closes and when a week opens — plus the race calendar:
which races a season's declaration file places into which week and day.
Not the race itself as a model (that is `racing.Race`, which a week's
`races` points at), and not the clock (`world/`).

## Derived, not stored

There is no "current season" field anywhere in this app. `current_position(at)`
is a pure function of the time passed in: it queries `Season`/`Week` ranges
and returns where `at` falls. A missed tick can never make the game display
the wrong week, because nothing caches "where we are" — every read asks the
question fresh.

**Adding a cached pointer (`Season.is_current`, a `CurrentSeason` singleton,
a `WorldState.season_id`) would be a regression, not an optimisation.** The
production clock (`world.clocks.RealClock`) holds no state and never
advances; `tick()` only processes what has *become* due. A stored pointer
would be a cache of `current_position()` with no reliable event to
invalidate it on.

`season_and_week_of(moments)` applies the same rule to many timestamps at
once: `(season, week)` numbers for each, `(season, None)` once that season
has ended, and `(None, None)` before any season. It costs two queries for the
whole list, where `current_position` would cost up to three per row. `api/`
uses it to date a team's departures (#158). A test checks it against
`current_position` case by case, so the two cannot drift apart.

## The week boundary

A season's `starts_at` must be a Monday at 00:00:00 UTC. This is an
arbitrary but fixed choice — any single fixed weekday would satisfy the
spec's "every week starts on the same day" rule, and Monday reads as "week
1" to a European cycling audience. UTC because every other datetime in the
project is UTC. The race calendar places every race's day of the week
against this same anchor — see *Placing a race*, below.

## Exactly-once

`SeasonTransition` has a `UniqueConstraint` on `(season, kind)`. That
constraint — not a check-then-insert — is what makes recording a
transition safe under concurrent ticks: `process_transitions()` wraps each
row's `create()` in its own `transaction.atomic()` block and catches
`IntegrityError` when a concurrent call wins the race. One `atomic()` per
create, never one around the whole loop — an `IntegrityError` poisons the
enclosing transaction in Django, so catching it inside a shared transaction
and continuing would fail the next statement with
`TransactionManagementError`.

`occurred_at` is the season's own `starts_at`/`ends_at` — the boundary that
was crossed — never the `at` passed to `process_transitions()`. A tick that
runs three weeks late still records the moment the season actually opened
or closed, not how late the tick was. (`recorded_at`, separately, is
`auto_now_add` real time — the gap between the two is exactly how late.)

## Season close now advances every rider's age

A season boundary is no longer inert: `world.services.tick()` reads the
`CLOSED` transitions `process_transitions()` returns and, for each one,
calls `riders.services.advance_ages()` — every rider in the game, rostered
or free agent, one year older. Promotion/relegation, contract renewal and
salary reviews (out of scope here, see `specs/archive/season.md`) remain
unattached; season close is not fully empty any more, but it is still far
from full.

## Week transitions

`WeekTransition` is the weekly counterpart of `SeasonTransition`: an
exactly-once record that a `Week` has opened, written by
`process_week_transitions()` and read by `world.services.tick()` to drive
weekly rider growth and decline
([#58](https://github.com/mario595/cycling-manager-game/issues/58)). A week has
only one kind of boundary — it opens; nothing closes it — so the unique
constraint is on `week` alone, not `(week, kind)` the way
`SeasonTransition` needs for two kinds.

Same shape as *Exactly-once*, above: the `UniqueConstraint` is the
guarantee, not the `exclude()` in `process_week_transitions()`, which only
keeps the common case cheap. `occurred_at` is the week's own `starts_at` —
the boundary that was crossed — never the `at` the tick passed in, for the
same reason `SeasonTransition.occurred_at` isn't either: a tick running
three weeks late must still record each week at the moment it actually
started.

## Declaring a season

```bash
manage.py load_season seasons/season-1.example.json
manage.py load_season seasons/season-1.example.json --replace
manage.py load_season seasons/season-2.example.json
```

The file is JSON: `number` (int, starting at 1), `starts_at` (ISO 8601,
must resolve to a Monday 00:00:00 UTC), and optional `races` and
`stage_races` lists. The command creates the `Season`, its twelve `Week`
rows and any declared races and stage races in one transaction — a
malformed entry anywhere in the file creates none of it, season included.

**There are two example seasons, and they abut.** `season-1.example.json`
opens 2027-03-01 and `season-2.example.json` opens 2027-05-24 — exactly
where season 1 ends, because `load_season` refuses an overlap and a
drifting date would break seeding outright. Season 2 is not there for its
races: it is what makes a **development squad's whole arc** visible in one
database (#34). A rider who arrives on week 4 graduates on week 18, which
is six weeks *into season 2*, so with only season 1 declared the
graduation, the decision window and the release to the free-agent pool can
never all be seen. Load both when working on that.

**`--number` and `--starts-at` override the file** (#139). They let one
calendar file serve every season of a world: `seed_world` and `add_season`
(`world/README.md`, *Building a world*) declare `seasons/world.json` again
and again, each time with the next number and the previous season's
`ends_at`:

```bash
manage.py load_season seasons/world.json --number 3 --starts-at 2027-08-16
```

Both are written into the parsed JSON *before* it is validated, so an
override obeys exactly the rules the file's own value does: a Monday at
00:00 UTC, and a positive number. A bare date means 00:00 UTC. There is no
second validation path to drift from the first.

A season that has already started (`starts_at <= now()`) can never be
touched again — `load_season` refuses outright, with no `--replace`
escape. A season declared but not yet started is still a draft: reloading
its file requires `--replace` and replaces it, races included (see
*Replacing a season with races*, below).

Unknown top-level keys, and unknown keys within a race entry, are warned
about and ignored, not rejected — the file is hand-edited by one admin, and
this is the one place a forward-compatibility allowance is worth it.

There is deliberately no admin UI, no API endpoint, and no interactive
prompt for declaring a season — see `specs/archive/season.md`'s *Out of scope*.

### The `races` list

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
        { "length": 12000, "gradient": 5.0 }
      ],
      "markers": [
        { "kind": "sprint", "name": "First Sprint", "distance": 40000, "weight": "major" },
        { "kind": "mountain", "name": "Final Top", "distance": 52000, "category": "hc" }
      ]
    },
    {
      "week": 3,
      "day": "saturday",
      "time": "13:00",
      "name": "Windy Coastal",
      "wind": { "band": "strong" },
      "seed": 12345,
      "course": [{ "length": 60000, "gradient": 0.0 }]
    }
  ]
}
```

| Key | Required | Notes |
|---|---|---|
| `week` | yes | 1 to `SEASON_WEEKS` (12). |
| `day` | yes | Lowercase `monday`…`sunday`. |
| `time` | yes | `HH:MM`, 24-hour. Non-zero minutes are accepted with a warning — see *Placing a race*. |
| `name` | yes | Non-empty, at most 150 characters (`Race.name`'s limit). |
| `course` | yes | A non-empty list of `{length, gradient}` segments — the engine's own shape. |
| `markers` | no | A list of `{kind, name, distance, weight?, category?}` named points on the course — same shape the engine's config parser accepts, validated here the same way the course is (*Why the course is validated twice*, below). `kind` is `sprint` \| `mountain`, `name` non-empty (≤ 100 chars), `distance` strictly inside the course length, so each error names `races[i].markers[j]` for the admin. `weight` is `minor` \| `standard` \| `major`, **sprint markers only** — a `weight` key on a mountain marker is rejected, because the two vocabularies mean different things and data authored under the wrong one would have to be reinterpreted later. `category` is `hc` \| `cat1` \| `cat2` \| `cat3`, **mountain markers only**, rejected on a sprint for the same reason. Both default when absent (`standard` and `cat2` respectively), so every season file written before sprint or mountain points keeps working unchanged. |
| `wind` | no | `{"enabled": bool, "band": "calm"\|"light"\|"moderate"\|"strong"}`. Absent means the model's defaults: wind on, band rolled from the seed. |
| `seed` | no | Stored on `Race.seed` for reproducibility. |

`races` may be empty or absent — a season with no racing is still a valid
season, and is exactly what the first season shipped with before this
feature existed.

### The `stage_races` list

```json
{
  "stage_races": [
    {
      "name": "Alpine Tour",
      "week": 6,
      "start_day": "monday",
      "time": "14:00",
      "stages": [
        { "course": [{ "length": 130000, "gradient": 0.0 }] },
        { "name": "Mountain Stage", "course": [{ "length": 90000, "gradient": 4.0 }] },
        { "course": [{ "length": 140000, "gradient": 0.0 }], "time": "13:00" }
      ]
    }
  ]
}
```

| Key | Required | Notes |
|---|---|---|
| `name` | yes | Non-empty, at most 120 characters (`StageRace.name`'s limit). |
| `week` | yes | 1 to `SEASON_WEEKS` (12), same as a race's `week`. |
| `start_day` | yes | Lowercase `monday`…`sunday` — the first stage's day. |
| `time` | yes | `HH:MM`, the default for every stage; a stage's own `time` overrides it. |
| `stages` | yes | 2 to 7 objects, one per stage, in order. Each takes `course` (required, same shape as a race's), and the optional `name`, `time`, `wind`, `seed`, `markers` a race entry takes — everything except `week`/`day`, which the stage race supplies. |

A stage race's stages land on `start_day`, `start_day + 1`, … in order, and
must not run past Sunday (`start_day` plus `len(stages) - 1` days ≤ 6) — see
`specs/archive/stage-races.md`, *Rules and edge cases*: a stage race is
always inside one calendar week. Each stage's `(week, day)` is checked
against the **same** one-race-per-day pool a one-day race's `(week, day)`
is, so a stage clashing with an ordinary race — or with another stage
race's stage — names both in the error, exactly like two one-day races
would (see *One race per day*, below).

A stage's `Race.name` is generated, never taken verbatim from the file:
`"<tour> — Stage <n>"`, or `"<tour> — Stage <n>: <stage name>"` when the
stage entry gives one. There is no way to set a stage's full name directly
— the numbering is part of the identity the calendar and results screens
read.

`stage_races` may be empty or absent, like `races`.

## Placing a race

A race entry says where it sits in season-relative terms — `(week, day,
time)`. The loader resolves that to what the database actually stores —
`(week` FK`, starts_at)` — using the week's own `starts_at` (a Monday
00:00 UTC, see *The week boundary*) as the anchor:

```python
starts_at = week.starts_at + timedelta(days=DAY_INDEX[day], hours=h, minutes=m)
```

`DAY_INDEX` runs Monday=0 through Sunday=6. This is the only place "day of
the week" is computed for a race — `race.starts_at.weekday()` recovers it
afterwards, and `race.week.number` recovers the week. Nothing else stores
either separately (`race_day`, below, is the one exception, and it exists
for a different reason).

**The tick is hourly, so a race's minutes are honoured but not urgent.** A
race declared at `14:30` starts at the next hourly tick after that moment,
not at `14:30` itself — see `world/README.md`, *How a tick works*. The
loader warns rather than refuses on non-zero minutes: an admin may want two
races on the same day ordered relative to each other once a day can hold
more than one, which it cannot today.

## One race per day

Spec: at most one race per calendar **day** (not per week — a Saturday and
Sunday race in the same week are both allowed). This holds across both
kinds of entry a season file declares — a one-day race and a stage race's
stage compete for the same day exactly like two one-day races would. Two
layers enforce it:

- **The loader** rejects a duplicate `(week, day)` pair while parsing the
  file — races and every stage of every stage race all feed the same
  `(week, day)` pool — naming both entries in the error, this is the
  message an admin actually sees.
- **`racing.models.Race`** carries a `UniqueConstraint` on
  `(week, race_day)`, where `race_day` is a `DateField` set in `save()`
  from `starts_at`. This is what makes the rule true at the database level,
  not merely checked at load time.

`race_day` exists **solely** as that constraint's target. It is never read
by anything, never editable, and is not a second source of truth for a
race's day — `starts_at` is, always. See `racing/README.md`.

## Why the course is validated twice

`race_engine.config._parse_course` already validates the `{length,
gradient}` segment shape. `schedule/loaders.py` re-implements the same
check rather than importing it, because either alternative breaks a rule
this project holds hard:

- Importing `race_engine` here would make `schedule/` the second module
  (besides `racing/adapters.py`) allowed to import the engine — see
  `racing/README.md`, *The core rule*.
- Routing the check through `racing/` instead (`schedule -> racing ->
  race_engine`) would mean `schedule/` importing `racing/`, which is
  backwards: the dependency runs `racing -> schedule`, one way.

Fifteen duplicated lines is the deliberate cost of keeping both rules
intact. **Do not** "fix" this duplication by adding either import — that is
this repo's actual mistake waiting to happen here, not a code smell.

Markers are validated the **same way, for the same reason**. `RaceMarker`
carries its own `clean()` check (`racing/README.md`, *Markers and
crossings*), the engine range-checks them on construction, and the loader
duplicates both — `kind` ∈ {sprint, mountain}, non-empty `name` ≤ 100 chars,
`0 < distance <= course length` — so an admin's typo is named
`races[i].markers[j].kind` at load time rather than surfacing as a
`RaceSetupError` from inside a simulation. Three copies of a ten-line rule is
still less than the one import that would violate the dependency direction.

`loaders.MARKER_WEIGHTS` and `loaders.MARKER_CATEGORIES` are the same
duplication for two fields: they repeat `RaceMarker.Weight`'s three values and
`RaceMarker.Category`'s four, because `loaders.py` may not import `racing/`.
`racing/tests.py::test_loader_weights_match_race_marker_weights` and
`test_loader_categories_match_race_marker_categories` are the drift tests —
they live on the `racing/` side because that is the app allowed to import
`schedule/`, not the reverse.

## Replacing a season with races

`--replace` on a not-yet-started season deletes it. `Race.week` and
`StageRace.week` are both `on_delete=PROTECT` (`racing/README.md`), so once
a season has races or stage races, deleting the `Season` directly raises
`ProtectedError` — the command therefore deletes races before stage races
before the season:

```python
Race.objects.filter(week__season=existing).delete()
StageRace.objects.filter(week__season=existing).delete()
existing.delete()
```

Races first, deliberately: `Race.stage_race` is *also* `PROTECT`, so a
`StageRace` cannot be deleted while any of its own stages still exist.

This is safe only because the not-yet-started check has already run: no
race being deleted here can have been simulated, because nothing in an
unstarted season's future can be due yet.

## A status the spec does not name

`specs/archive/race-calendar.md` describes three player-visible states: not yet
happened, happening today, finished. `Race.status` has a fourth,
`failed` — set by `world.services._execute` when a simulation raises. The
calendar's API returns it verbatim rather than inventing a fifth word or
folding it into `finished` (which would show a player a completed race
with no result); the SPA shows it as "Not run". See `frontend/README.md`.

## What `schedule/` may import

`core`, and nothing else it needs today. **`schedule/` must never import
`world/` or `racing/`** — either would invert the dependency direction in
`AGENTS.md` (`world/` may import everything; nothing may import `world/`;
`racing -> schedule`, one way, not the reverse).

The documented exceptions, all **inside `load_season.py`'s `handle()`**,
never at module scope and never in `schedule/loaders.py` or
`schedule/services.py`:

- `world.services.now()`, to check whether a season has already started.
- `racing.models.Race`, and `racing.services.create_race`, which replaces
  `Race.objects.create` as the callable injected into
  `schedule.loaders.create_races()` — a race with markers needs its
  `RaceMarker` rows created in the same transaction as the `Race` itself
  (`racing/README.md`, *Markers and crossings*). `loaders.py` itself never
  imports `racing/` at all. That injection is not ceremony:
  it is what keeps `schedule/loaders.py`'s tests running with no database
  and no import of `racing/`.
- `racing.models.StageRace`, and `racing.services.create_stage_race`, the
  same injected-callable shape for `schedule.loaders.create_stage_races()`
  — see `racing/README.md`, *Stage races*.

**`apps.get_model("racing", "Race")` is not an acceptable substitute** for
either of the above inside library code — it is an import in disguise that
`grep -rn "racing\|world" schedule/ --include=*.py` would miss.

## What may import `schedule/`

`racing/` (a `Race` points at the `Week` it belongs to, via a string FK —
see `racing/README.md`), `world/` (the tick calls `process_transitions()`),
and `api/` (the position and calendar endpoints call
`current_position()`).

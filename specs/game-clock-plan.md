# Game clock — Implementation Plan

**Spec:** `specs/game-clock.md` · **Issue:** [#6](https://github.com/mario595/cycling-manager/issues/6) · **Status:** proposed
**Apps touched:** `world/`, `racing/`, `api/`, `frontend/`, `config/`

## Context you need

This is a **revision** of an already-implemented feature. A first version
shipped on this branch with a stored `GameClock` row that `advance()` moved
forward under a row lock, approximating real time. The revised spec (see
`specs/game-clock.md`) rejects that: production's game time **is** real time,
read live, with nothing stored or advanced. A separate, swappable clock exists
purely for development and test, where a real engineer needs to freeze time or
jump to the next event without waiting for it.

Read `world/README.md` and `racing/README.md` before touching either app — this
plan changes decisions those files currently document as settled and both need
updating (see *Documentation update*).

**What exists today, and what of it survives:**

- `world.models.GameClock` — a `pk=1` row holding `current`, `last_advanced_at`,
  `catch_up_hours`. **Survives, repurposed**: it becomes the storage for the
  mock clock only. In production, with the real clock active, this row is
  never read or written. `last_advanced_at` is dropped — it existed to compute
  elapsed real time since the last advance, which no longer drives anything.
- `world.models.TickRun` — a record of one advance, currently including
  `from_game_time` / `to_game_time`. **Survives, trimmed**: there is no more
  "clock moved from X to Y"; a run either does or does not move the mock
  clock, and that is the mock clock's own business, not the tick's.
- `world.services.now()`, `advance()`, `_claim()`, `_execute()`,
  `_advance_days()`, `_reclaim_unfinished()`, `due_races()` — **all replaced**.
  The claim mechanism moves from locking the clock row to locking the due
  races themselves (Design decision 3), because there is no longer a clock row
  to lock in production.
- `world.management.commands.tick` — **kept, behaviour changes**. No longer
  takes `--to-next` / `--day`; those move to a new `mock_clock` command,
  because they are meaningless against the real clock and this command must
  work (and be the only command cron ever calls) regardless of which clock is
  configured.
- `world.management.commands.set_game_date` — **replaced** by
  `mock_clock set`, alongside `mock_clock advance` (to-next / by-amount) as
  subcommands of one mock-clock-only tool. Reason in Design decision 5.
- `racing.models.Race.starts_at` / `.status` / `.finished_at`,
  `racing.services.simulate_race(race, *, game_time)` — **unchanged**. Neither
  knows or cares which clock produced `game_time`; this plan does not touch
  `racing/` except its README.
- `api.serializers.GameClockSerializer`, `api.views.ClockView` — **changed**.
  The endpoint now serializes `world.services.now()` directly (whichever
  clock is active) rather than the `GameClock` row, since in production there
  is no row to read.
- `frontend/src/api.ts`, `useClock.ts`, `Sidebar.tsx` — **unchanged by this
  plan**. They already treat `current` as an opaque ISO datetime from the
  endpoint; nothing about the response shape changes.

**Repo rules that bind this work** (`AGENTS.md`):

- Dependency direction: `world/` and `api/` may import everything; nothing may
  import them. `racing/` must not import `world/` — unaffected by this plan.
- Postgres in dev and prod alike. Tests are pytest via
  `.venv/bin/python -m pytest`.
- A field that is only meaningful in one clock mode must say so in its
  `help_text`, since the model is now shared by two different runtime
  behaviours.

## Goal

When this is done:

- `world.services.now()` returns the literal current time in production
  (`RealClock`), with nothing stored and nothing to lock.
- `manage.py tick` finds races whose `starts_at` has passed and are still
  `scheduled`, claims each exactly once via a row lock on the race itself (not
  a clock row), and simulates them, capped per run at a configurable number of
  races so a large backlog cannot turn into one unbounded run.
- A developer can select `MockClock` per-environment (a Django setting), and
  while it is active, `manage.py mock_clock set <datetime>` and
  `manage.py mock_clock advance [--to-next | --by <duration>]` move it by
  hand; `tick` behaves exactly as in production once the mock clock has moved,
  finding and claiming whatever is now due.
- Selecting `MockClock` in production is not a supported configuration: `dev.py`
  defaults to it, `prod.py` defaults to `RealClock`, and nothing in `prod.py`
  can be overridden by environment variable to change that (Design decision 2).
- `GET /api/world/clock/` reports whichever clock is active, transparently to
  the frontend.
- Every tick run leaves a `TickRun` row recording what it found and did.

## Design decisions (settled — implement these, do not substitute)

### 1. `Clock` is an abstract class with one method: `now()`

```python
# world/clocks.py
class Clock(ABC):
    def now(self) -> datetime: ...
```

`RealClock.now()` returns `django.utils.timezone.now()` directly — no state,
no database read. `MockClock.now()` reads the stored `GameClock` row.

**Do not** give `Clock` any method beyond `now()`. Setting or advancing the
clock is `MockClock`-specific (Design decision 4) and must not appear on the
abstract type — a caller holding a `Clock` (which is what every piece of game
code holds) has no business moving it, only reading it. This is what makes
decision 9 of the spec ("game code reads the clock, never real time
directly") enforceable: the interface game code is handed literally cannot
move time.

### 2. The active clock is chosen by a Django setting, resolved once, lazily

```python
# config/settings/base.py
GAME_CLOCK_CLASS = "world.clocks.RealClock"   # base.py default

# config/settings/dev.py
GAME_CLOCK_CLASS = "world.clocks.MockClock"

# config/settings/prod.py — no override; inherits RealClock from base.py
```

`world/services.py` resolves the dotted path with `django.utils.module_loading
.import_string`, instantiates it once, and caches the instance at module
level (mirroring how `django.core.files.storage.default_storage` is a
lazily-instantiated singleton). **Do not** re-instantiate the clock on every
call to `now()` — `MockClock` is cheap to construct, but a future clock
implementation might not be, and re-instantiating hides that this is meant to
be one process-wide clock.

`prod.py` deliberately does **not** read `GAME_CLOCK_CLASS` from the
environment the way it reads `POSTGRES_*`. Every other production setting in
that file is env-driven by design (`prod.py`'s own docstring: "the same image
runs anywhere"), but the clock is the one exception: the spec is explicit that
a non-real clock must never be a live-game possibility, "not disabled, not
gated behind a permission, simply not a code path production runs." An env var
is a code path. A hardcoded absence of one is not.

### 3. Exactly-once: lock the due races, not a clock row — load-bearing

There is no clock row to lock against in production, so the row lock moves to
the races themselves:

```python
# world/services.py
def _claim(limit: int) -> list[int]:
    """Claim up to `limit` due races by flipping them SCHEDULED -> RUNNING
    inside a transaction holding a row lock on exactly those rows. Returns
    the claimed ids. No simulation happens here."""
    with transaction.atomic():
        ids = list(
            Race.objects.select_for_update()
            .filter(status=Race.Status.SCHEDULED, starts_at__isnull=False,
                     starts_at__lte=now())
            .order_by("starts_at")
            .values_list("pk", flat=True)[:limit]
        )
        Race.objects.filter(pk__in=ids).update(status=Race.Status.RUNNING)
    return ids
```

A second `tick` arriving while the first holds the lock blocks on
`select_for_update()`, then re-runs its own `filter(status=SCHEDULED, ...)`
after the first commits — the rows the first claimed are now `RUNNING` and no
longer match, so the second claims nothing. Same guarantee as the previous
design's clock-row lock, different lock target, because there is no longer a
single row whose lock naturally serialises every claim — the race rows
themselves now play that role.

**Do not** reach for `select_for_update(skip_locked=True)` here: skipping a
locked row would let a second concurrent tick claim *different* due races
while the first is still claiming, which is fine for correctness but means
two ticks are simulating concurrently with nothing coordinating log storage or
`RaceLog.update_or_create` between them. That concurrency is explicitly
deferred (spec, *Deferred*: "Several races worked out at the same time").
Until it is designed, one tick fully blocks the next.

### 4. `MockClock` owns its own mutation methods; `Clock` does not

```python
# world/clocks.py
class MockClock(Clock):
    def now(self) -> datetime: ...
    def set(self, when: datetime) -> None: ...
    def advance_to_next_due(self) -> None: ...
    def advance_by(self, delta: timedelta) -> None: ...
```

These are `MockClock`-only, called only from `manage.py mock_clock` (Design
decision 5), never from `world/services.py`'s tick logic. `tick` only ever
calls `now()` through the `Clock` interface, exactly like production —
this is what guarantees a developer stepping the mock clock forward is
indistinguishable, from `tick`'s point of view, from real time having simply
passed.

`advance_to_next_due()` needs to know what's due, which means `MockClock`
(living in `world/clocks.py`) queries `racing.models.Race`. This is allowed:
`world/` may import everything (`AGENTS.md`); the constraint is the reverse.

### 5. `mock_clock` is one command with subcommands, and refuses to run against `RealClock`

```
manage.py mock_clock set 2027-03-01T09:00
manage.py mock_clock advance --to-next
manage.py mock_clock advance --by 1d
manage.py mock_clock advance --by 6h
```

Every subcommand's `handle()` starts by checking
`isinstance(get_clock(), MockClock)` and raises `CommandError` immediately if
not — "this command only works when GAME_CLOCK_CLASS is world.clocks.MockClock;
current setting: <path>". This is the enforcement half of decision 2: the
setting keeps `RealClock` the only thing production can run, and this check
stops someone fat-fingering a mock-clock command against a production
database from doing anything at all.

**Do not** make `set_game_date` and `tick --to-next` / `tick --day` survive
as-is alongside the new command. One command, `mock_clock`, is the only place
that can move time, matching the spec's "developer, and only a developer" —
having two entry points (a flag on `tick` and a separate command) makes it
easy to add a new flag to `tick` later without remembering it must carry the
same `MockClock`-only guard.

`--by` parses a duration string (`1d`, `6h`, `30m`, or combinations like
`1d6h`) with a small hand-rolled parser — **do not** add a dependency for
this; the format is deliberately tiny and one regex covers it
(`re.findall(r"(\d+)([dhm])", value)`).

### 6. The backlog cap moves from hours to a race count

```python
# world/models.py
class GameClock(models.Model):
    ...
    catch_up_max_races = models.PositiveSmallIntegerField(default=50)
```

The old `catch_up_hours` capped how much *game time* one advance would move
through; there is no game-time movement to cap now, only a query result size.
`50` is a placeholder default with the same reasoning the old `72` hours had:
races are sparse today (no calendar yet), so this should never engage in
normal operation, and it is configuration precisely so it can be raised for an
exceptional recovery. **Do not** invent a time-based cap here (e.g. "races due
in the last 72 hours") — the spec's reframed rule is explicitly about backlog
size, not backlog age, because age is meaningless once the clock cannot lag.

This field stays on `GameClock` even though `GameClock` otherwise only backs
`MockClock`, because the cap applies to `tick`'s claim query regardless of
which clock is active — `tick` reads `GameClock.load().catch_up_max_races`
directly (a plain read, no lock needed: this value changes by admin action,
not by every tick).

### 7. `TickRun` drops the clock-movement fields, keeps the audit trail

```python
class TickRun(models.Model):
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    races_started = models.PositiveIntegerField(default=0)
    races_finished = models.PositiveIntegerField(default=0)
    capped = models.BooleanField(default=False)
    error = models.TextField(blank=True, default="")
```

`from_game_time` / `to_game_time` are removed — there is no clock movement a
tick causes; the mock clock moves independently, by hand, via `mock_clock`.
`trigger` is also removed: the old three values (`cron` / `to_next` / `day`)
described what moved the clock, which is no longer `tick`'s job. `tick` has
exactly one behaviour now regardless of caller, so there is nothing left to
distinguish.

**Load-bearing:** `races_started == races_finished` after a clean run is the
signal that nothing was left half-done; `capped=True` is the signal the claim
query hit `catch_up_max_races` and there may be more still due.

### 8. `now()` resolution: a lazy, cached, settings-driven singleton

```python
# world/services.py
from datetime import datetime
from django.conf import settings
from django.utils.module_loading import import_string

_clock = None

def get_clock() -> Clock:
    global _clock
    if _clock is None:
        _clock = import_string(settings.GAME_CLOCK_CLASS)()
    return _clock

def now() -> datetime:
    return get_clock().now()
```

`get_clock()` is exported (not underscore-prefixed) because `mock_clock`'s
commands need it to call `MockClock`-only methods and to perform the
`isinstance` guard from decision 5.

**Load-bearing for tests:** module-level caching means a test that overrides
`settings.GAME_CLOCK_CLASS` (e.g. `@override_settings`) must also reset
`world.services._clock = None`, or it keeps talking to whichever clock was
resolved first. Give the test suite a fixture for this (Work item W5) rather
than expecting every test file to remember the reset.

### 9. `GET /api/world/clock/` serializes `now()`, not a model instance

```python
# api/serializers.py
class ClockSerializer(serializers.Serializer):
    current = serializers.DateTimeField()

# api/views.py
class ClockView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        return Response(ClockSerializer({"current": now()}).data)
```

The old `GameClockSerializer` was a `ModelSerializer` over `GameClock`,
exposing `catch_up_hours` and `last_tick`. Neither survives on the response:
`catch_up_hours` was implementation detail leaking into a public API, not
something a player needs, and `last_tick` (the most recent `TickRun.finished_at`)
described clock health, not game time — worth having in an ops view later, not
in the player-facing endpoint. **Do not** carry them over for compatibility;
nothing in `frontend/` reads either field (verify: `grep -n "catch_up_hours\|
last_tick" frontend/src/*.ts` returns nothing outside `api.ts`'s old `Clock`
type, which this plan also trims — see W8).

## Data model

### `world.models.GameClock` — migration `world/migrations/0002_mock_clock.py`

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `id` | `BigAutoField` | no | — | Always 1, enforced by `load()`. Unchanged. |
| `current` | `DateTimeField` | no | — | The mock clock's value. **Only meaningful when `MockClock` is active** — say so in `help_text`. Unchanged type. |
| `last_advanced_at` | — | — | — | **Removed.** Drop the field. |
| `catch_up_hours` | — | — | — | **Removed**, replaced by `catch_up_max_races` below. |
| `catch_up_max_races` | `PositiveSmallIntegerField` | no | `50` | Per-tick cap on races claimed in one run. Read regardless of which clock is active. |

`GameClock.load()` is unchanged in shape (`get_or_create(pk=1, ...)`), but its
`defaults` drop `last_advanced_at`.

### `world.models.TickRun` — same migration

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `started_at` | `DateTimeField` | no | `auto_now_add` | Unchanged. |
| `finished_at` | `DateTimeField` | yes/yes | `None` | Unchanged. |
| `races_started` | `PositiveIntegerField` | no | `0` | Unchanged. |
| `races_finished` | `PositiveIntegerField` | no | `0` | Unchanged. |
| `capped` | `BooleanField` | no | `False` | Unchanged meaning, now means "the claim query hit `catch_up_max_races`". |
| `error` | `TextField` | blank/yes (`blank=True`, default `""`) | `""` | Unchanged. |
| `from_game_time` | — | — | — | **Removed.** |
| `to_game_time` | — | — | — | **Removed.** |
| `trigger` | — | — | — | **Removed**, and its `Trigger` `TextChoices` inner class with it. |

`Meta.ordering = ["-started_at"]` and the `-started_at` index are unchanged.

### `racing.models.Race`

No changes. `starts_at`, `status`, `finished_at` already exist and are
clock-implementation-agnostic (`racing/services.simulate_race` takes
`game_time` as a parameter regardless of where it came from).

## `world/clocks.py` (new)

```python
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from .models import GameClock


class Clock(ABC):
    @abstractmethod
    def now(self) -> datetime: ...


class RealClock(Clock):
    def now(self) -> datetime:
        return timezone.now()


class MockClock(Clock):
    """Development- and test-only clock, backed by the `GameClock` row.
    `world.services.get_clock()` is the only sanctioned way to obtain the
    active clock; do not import this class to bypass `mock_clock`'s
    isinstance guard."""

    def now(self) -> datetime:
        return GameClock.load().current

    def set(self, when: datetime) -> None:
        with transaction.atomic():
            clock = GameClock.objects.select_for_update().get(pk=1)
            clock.current = when
            clock.save(update_fields=["current"])

    def advance_by(self, delta: timedelta) -> None:
        with transaction.atomic():
            clock = GameClock.objects.select_for_update().get(pk=1)
            clock.current += delta
            clock.save(update_fields=["current"])

    def advance_to_next_due(self) -> None:
        """Jump straight to the next scheduled race's starts_at, or do
        nothing if none is scheduled after the current moment."""
        from racing.models import Race  # local import: see note below

        with transaction.atomic():
            clock = GameClock.objects.select_for_update().get(pk=1)
            nxt = (
                Race.objects.filter(
                    status=Race.Status.SCHEDULED, starts_at__isnull=False,
                    starts_at__gt=clock.current,
                )
                .order_by("starts_at")
                .first()
            )
            if nxt is not None:
                clock.current = nxt.starts_at
                clock.save(update_fields=["current"])
```

The import of `racing.models.Race` is local to `advance_to_next_due`, not at
module level, purely to keep `world/clocks.py`'s top-level imports free of
other-app models — `world/` is allowed to import `racing/` (`AGENTS.md`), this
is a style choice for this one file, not a dependency-direction requirement.
A reviewer should not read the local import as load-bearing.

`GameClock.load()` inside `MockClock` methods, not passed in, because
`MockClock` is only ever asked to move *the* clock — there is exactly one row,
same as before.

## `world/services.py` — rewritten

```python
from __future__ import annotations

import traceback
from datetime import datetime

from django.conf import settings
from django.db import transaction
from django.utils.module_loading import import_string

from racing.models import Race
from racing.services import simulate_race

from .clocks import Clock
from .models import GameClock, TickRun

_clock: Clock | None = None


def get_clock() -> Clock:
    global _clock
    if _clock is None:
        _clock = import_string(settings.GAME_CLOCK_CLASS)()
    return _clock


def now() -> datetime:
    return get_clock().now()


def _reclaim_unfinished() -> list[int]:
    """Race ids left RUNNING with no results by an interrupted run."""
    return list(
        Race.objects.filter(status=Race.Status.RUNNING, results__isnull=True)
        .order_by("starts_at")
        .values_list("pk", flat=True)
    )


def _claim(limit: int) -> list[int]:
    """Claim up to `limit` due races. See Design decision 3."""
    with transaction.atomic():
        ids = list(
            Race.objects.select_for_update()
            .filter(status=Race.Status.SCHEDULED, starts_at__isnull=False,
                     starts_at__lte=now())
            .order_by("starts_at")
            .values_list("pk", flat=True)[:limit]
        )
        Race.objects.filter(pk__in=ids).update(status=Race.Status.RUNNING)
    return ids


def _execute(race_ids: list[int], tick: TickRun) -> None:
    """Simulate each claimed race outside any lock. One broken course must
    not stop the run: recorded on the race and the tick, loop continues."""
    for race_id in race_ids:
        race = Race.objects.get(pk=race_id)
        try:
            simulate_race(race, game_time=now())
            tick.races_finished += 1
        except Exception:
            race.status = Race.Status.FAILED
            race.save(update_fields=["status"])
            tick.error += f"race {race_id}:\n{traceback.format_exc()}\n"


def tick() -> TickRun:
    """Find and process whatever is due, exactly once. The only entry point
    cron (or a developer, after moving the mock clock) ever calls."""
    max_races = GameClock.load().catch_up_max_races

    reclaimed = _reclaim_unfinished()
    claimed = _claim(limit=max_races - len(reclaimed))
    capped = len(reclaimed) + len(claimed) >= max_races

    run = TickRun.objects.create(races_started=len(claimed))
    _execute(reclaimed + claimed, run)
    run.capped = capped
    run.finished_at = timezone_now_for_tick_run()  # see note
    run.save(update_fields=["races_finished", "capped", "error", "finished_at"])
    return run
```

Notes the reader needs:

- **`tick()` replaces `advance()`.** No `trigger`, `to_next` or `days`
  parameters — those were about moving the clock, which `tick` no longer does.
  A developer who wants "the next event" calls
  `manage.py mock_clock advance --to-next` first, then `manage.py tick`, which
  now finds it due and runs it. Two commands, not one command with modes,
  matching decision 5.
- **`max_races - len(reclaimed)`**: reclaimed races count against the same cap
  as newly-claimed ones — a run that is mostly clearing a stranded backlog
  from a crash should not *also* claim a full cap's worth of newly-due races
  on top, or the cap stops bounding anything.
- **`finished_at` on `TickRun`** is real time regardless of which clock is
  active — it is a record of when the *check* ran, not game time. Use
  `django.utils.timezone.now()` directly here (not `now()` from this module),
  and say so in a comment: this is the one other sanctioned real-time read
  alongside `RealClock.now()` itself, because a `TickRun` audit log must be
  orderable by when it actually executed on the host, independent of which
  clock the game itself was running on.

## `world/management/commands/tick.py` — simplified

```python
class Command(BaseCommand):
    help = "Find and process whatever is due, exactly once. Run hourly from cron in production."

    def handle(self, *args, **options):
        run = world_services.tick()
        self.stdout.write(
            f"races started {run.races_started}, finished {run.races_finished} | "
            f"capped={run.capped}"
        )
        if run.error:
            self.stderr.write(run.error)
            raise CommandError("tick completed with errors")
```

No arguments. `--to-next` / `--day` are gone from this command (decision 5).

## `world/management/commands/mock_clock.py` (new, replaces `set_game_date.py`)

```
manage.py mock_clock set 2027-03-01T09:00
manage.py mock_clock advance --to-next
manage.py mock_clock advance --by 1d
manage.py mock_clock advance --by 6h
```

Implemented as one `Command` with a required positional `action`
(`set` / `advance`) via `add_subparsers`-style argument handling — follow
whatever subcommand pattern reads most like existing Django management
commands in this repo (there is no existing multi-subcommand command here to
copy; `argparse` subparsers are the standard-library-only way, so use those
rather than a third-party dependency).

Every code path starts:

```python
clock = world_services.get_clock()
if not isinstance(clock, MockClock):
    raise CommandError(
        f"mock_clock only works when GAME_CLOCK_CLASS is MockClock; "
        f"current setting: {settings.GAME_CLOCK_CLASS}"
    )
```

`--by` duration parsing: `re.findall(r"(\d+)([dhm])", value)`, building a
`timedelta` from the matched `(amount, unit)` pairs (`d`→days, `h`→hours,
`m`→minutes). Raise `CommandError` if the regex matches nothing (an
unparseable string like `--by soon`).

`set`'s datetime argument reuses the same parse-and-make-aware logic the old
`set_game_date` had (`parse_datetime`, then `timezone.make_aware` if naive) —
copy that, it does not change.

**Do not** carry over `set_game_date`'s backwards-past-a-finished-race guard.
That guard existed because rewinding a clock that *drives* due-checks past a
finished race would make it due again. Under this design the guard is still
correct and still needed for the same reason — keep it, but move it into
`mock_clock set`'s handler rather than dropping it; it is one of the few
pieces of business logic in the old command worth preserving as-is.

## `api/serializers.py` and `api/views.py`

See Design decision 9. `GameClockSerializer` → `ClockSerializer` (a plain
`serializers.Serializer`, not a `ModelSerializer` — there is no longer a
single model instance this response maps onto). `ClockView.get` calls
`world.services.now()` directly.

## `frontend/src/api.ts`

```typescript
export interface Clock {
  current: string
}
```

Drop `catch_up_hours` and `last_tick` from the type (Design decision 9). No
other change — `getClock()` still fetches the same URL and returns the same
shape minus those two fields, and nothing in `useClock.ts` or `Sidebar.tsx`
reads either field (confirmed by grep, see decision 9), so no cascading
change there.

## Work items

### W1 — `world/clocks.py`: `Clock`, `RealClock`, `MockClock`
New file, per the code in *`world/clocks.py` (new)* above.
**Test:** `world/tests/test_clocks.py::test_real_clock_returns_current_real_time`
(assert within a small tolerance of `django.utils.timezone.now()`);
`::test_mock_clock_now_reads_the_stored_row`;
`::test_mock_clock_set_moves_the_stored_row`;
`::test_mock_clock_advance_by_adds_a_delta`;
`::test_mock_clock_advance_to_next_due_jumps_to_the_next_scheduled_race`;
`::test_mock_clock_advance_to_next_due_does_nothing_when_none_scheduled`.

### W2 — `world/models.py`: trim `GameClock`, trim `TickRun`
Remove `last_advanced_at`, add `catch_up_max_races` (default `50`); remove
`from_game_time`, `to_game_time`, `trigger` and the `Trigger` choices class
from `TickRun`. Migration `world/migrations/0002_mock_clock.py`. Update
`world/admin.py`'s `list_display` on both (drop the removed fields).
**Load-bearing:** this is a destructive migration on fields that may hold data
in any environment this branch has already been deployed to informally (it has
not been deployed anywhere yet — confirm with `git log --oneline --
'*/settings/prod.py'` and the absence of a deployment target in
`specs/game-clock.md`'s Open questions before treating this as safe to just
drop; if genuinely nothing depends on the old columns, a straightforward
`RemoveField`/`AddField` migration is correct and no data preservation step is
needed).
**Test:** `world/tests/test_models.py::test_load_creates_single_clock` and
`::test_tick_run_orders_newest_first` are kept but updated to the trimmed
fields (no `last_advanced_at` in `load()`'s assertions; `TickRun.objects.create()`
calls in the test no longer pass `from_game_time`/`to_game_time`).

### W3 — `world/services.py`: `get_clock()`, `now()`, `tick()`
Full rewrite per the code above, replacing `advance()`, `_claim()`,
`_execute()`, `_advance_days()`. Keep `_reclaim_unfinished()` as-is (unchanged
logic, still correct: a `RUNNING` race with no results is still the crash
signature regardless of which clock is active).
**Load-bearing:** `select_for_update()` on the *race rows*, and simulation
running outside that transaction, same discipline as before, new lock target.
**Test:** `world/tests/test_services.py`, rewritten —
`::test_tick_with_nothing_scheduled_does_nothing` (spec item — a run with no
due races is valid and uneventful);
`::test_tick_runs_a_due_race_once`;
`::test_tick_is_capped_at_catch_up_max_races` (schedule more due races than
the cap, assert only `catch_up_max_races` are claimed and `TickRun.capped`);
`::test_second_tick_does_not_rerun_a_finished_race`;
`::test_interrupted_race_is_reclaimed` (a `RUNNING` race with no results is
picked up and finished, same as before);
`::test_race_failure_marks_failed_and_continues`.
Every test that needs a specific "now" uses `MockClock` (already the `dev.py`
/ test default — confirm `pyproject.toml`'s `DJANGO_SETTINGS_MODULE =
"config.settings.dev"` makes this automatic for the test run) and drives it
via `world.services.get_clock().set(...)` / `.advance_by(...)` directly rather
than going through the `mock_clock` management command — these are service
tests, not command tests.
**Also add:** a `conftest.py` fixture (or a helper in
`world/tests/__init__.py`) that resets `world.services._clock = None` after
each test — see Design decision 8's note on why this is required, not
optional, once more than one test touches `GAME_CLOCK_CLASS` indirectly via
`override_settings`.

### W4 — `world/management/commands/tick.py`: drop `--to-next` / `--day`
Simplify to the no-argument version above.
**Test:** `world/tests/test_tick_command.py::test_tick_command_runs_and_reports`
via `call_command("tick")`. Remove the old `::test_day_flag_...` and
`::test_to_next_and_day_together_is_an_error` cases — those flags no longer
exist on this command.

### W5 — `world/management/commands/mock_clock.py`: new command, delete `set_game_date.py`
Per the spec above, including the `MockClock`-only guard and the
backwards-past-a-finished-race check carried over into `set`.
**Load-bearing:** the `isinstance(clock, MockClock)` guard — this is the only
runtime enforcement that a misconfigured or mistaken invocation cannot move
time in an environment running `RealClock`.
**Test:** `world/tests/test_mock_clock_command.py::test_set_moves_the_clock`;
`::test_advance_to_next_moves_to_the_next_due_race`;
`::test_advance_by_parses_duration_strings` (cover `1d`, `6h`, `1d6h`);
`::test_refuses_to_rewind_past_a_finished_race_without_force`;
`::test_raises_when_real_clock_is_active` (use `@override_settings
(GAME_CLOCK_CLASS="world.clocks.RealClock")` plus the `_clock` reset fixture
from W3, assert `CommandError`).
Delete `world/tests/test_set_game_date.py`.

### W6 — `api/`: serialize `now()` instead of the `GameClock` model
`ClockSerializer` (plain `Serializer`), `ClockView.get` calling
`world.services.now()`. `api/urls.py` unchanged.
**Test:** `api/tests.py::test_clock_endpoint_returns_current_game_time` —
update the assertion to compare against `world.services.now()` rather than a
`GameClock` instance's `.current`; drop the old assertions on
`catch_up_hours` / `last_tick` (fields no longer in the response).

### W7 — `frontend/src/api.ts`: trim the `Clock` type
Remove `catch_up_hours` and `last_tick` from the `Clock` interface.
**Test:** none (matches the original plan's W9 — no frontend test runner
exists). `npm run build` (`tsc -b`) is the gate: it must still pass, and it
will only fail here if something elsewhere in `frontend/` reads either
removed field, which the decision 9 grep already ruled out.

### W8 — Documentation
`world/README.md`, `racing/README.md`, `AGENTS.md`, root `README.md` — see
*Documentation update*.
**Test:** none. Reviewed, not tested.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7 → W8.

- **W1 before W2** — `MockClock` needs `GameClock.load()`, but W1 is written
  against the *current* (pre-trim) model shape and W2 trims it in the same
  migration step. In practice, land W1 and W2 together in implementation if
  it is awkward to have `MockClock` reference fields being removed in the very
  next commit — but keep them as two commits: W1 introduces the clock
  abstraction and can be reviewed on the old model shape (it only touches
  `current`, which survives), W2 is the destructive model change reviewed on
  its own.
- **W3 depends on both** — `tick()` needs `Clock` (W1) and the trimmed
  `TickRun` (W2).
- **W4 and W5 depend on W3** — both are thin command wrappers around
  `world.services`.
- **W6 depends on W3** — the endpoint calls `now()`.
- **W7 is independent of the backend items** but sequenced after W6 so the
  frontend change is reviewed against the API shape it actually matches.
- **W8 last**, once behaviour is final.

**Commit at each W.** Note that this plan, unlike a from-scratch feature, is
replacing already-merged-pending code (PR #48) rather than adding to an empty
surface — the repo is *not* green after W1 alone the way a new app's first
commit would be, because W1 introduces `Clock`/`RealClock`/`MockClock` without
yet wiring `world/services.py` to use them, so the old `advance()`-based
tests keep passing against the old code until W3 replaces them. This is fine:
W1's own new tests (`test_clocks.py`) pass in isolation, and the full suite
stays green throughout because nothing is deleted before its replacement
lands in the same or a later commit within this sequence.

## Documentation update (required, not optional)

### `world/README.md` — substantial rewrite

- **What this app owns** — add `world/clocks.py` (`Clock`, `RealClock`,
  `MockClock`) to the list.
- **Replace "The clock discipline rule"** — restate as: game code reads
  `world.services.now()`, which reads whichever `Clock` is configured via
  `GAME_CLOCK_CLASS`; there is no longer a "one sanctioned exception" for
  `last_advanced_at`, because that field is gone. Add the new one sanctioned
  exception: `TickRun.finished_at`, which uses real time directly regardless
  of the active clock, and why (Design decision `tick()`'s note).
- **Replace "How an advance works" and "Exactly-once"** — rewrite around
  `tick()`'s claim-then-execute split and the row lock on due races (Design
  decision 3), not the old clock-row lock. Keep the two-phase framing
  (claim inside a transaction, execute outside it) — that part is unchanged
  and still the reason simulation never appears inside `transaction.atomic()`.
- **Replace "The 72-hour cap"** — becomes "The catch-up cap":
  `catch_up_max_races`, a race count not an hour count, same reasoning
  (configuration, raised for exceptional recovery).
- **Replace "Running the tick"** — `manage.py tick` (no flags now) run hourly
  from cron; `manage.py mock_clock set|advance` for development, and that it
  refuses to run unless `GAME_CLOCK_CLASS` is `MockClock`.
- **New section, "Which clock runs where"** — `dev.py` → `MockClock`, `prod.py`
  → `RealClock`, and that this is not overridable by environment variable in
  `prod.py` (Design decision 2), stated as a security-relevant fact, not just
  a default.

### `racing/README.md` — one section

- **"Triggering simulations"** — currently says `world/` "owns the tick and
  calls `racing.services.simulate_race`". Still true; add one sentence that
  `world/` may run against either a real or a mock clock, and `racing/` never
  knows or cares which — `simulate_race`'s `game_time` parameter is why.

### `AGENTS.md`

No app-table changes (`world/` and `api/` are already marked **built**). If
the dependency-direction diagram or app descriptions mention "the tick" in a
way that implies clock-advancing, check and reword to "finds and processes
due work" — a small wording pass, not a structural one.

### `README.md` (root)

The line added by the previous version ("the tick command and that a
development world is stepped with `manage.py tick --day`") is now wrong —
`tick --day` no longer exists. Replace with: the tick command, and that a
development clock is stepped with `manage.py mock_clock advance`.

## Verification

Unit tests:

```bash
docker compose up -d
.venv/bin/python manage.py migrate
.venv/bin/python -m pytest
```

**The end-to-end check that actually proves the feature:**

```bash
.venv/bin/python manage.py mock_clock set 2027-03-01T09:00
.venv/bin/python manage.py shell -c "
from racing.models import Race
from django.utils.dateparse import parse_datetime
import json
cfg = json.load(open('race_engine/configs/sprinters_classic.json'))['race']
Race.objects.create(name='E2E', course=cfg['course'], starts_at=parse_datetime('2027-03-01T14:00:00Z'))
"
.venv/bin/python manage.py mock_clock advance --to-next
.venv/bin/python manage.py tick
.venv/bin/python manage.py shell -c "
from racing.models import Race, RaceResult
r = Race.objects.get(name='E2E')
print(r.status, r.finished_at, RaceResult.objects.filter(race=r).count())
"
```

Expect: `finished`, `finished_at` of `2027-03-01T14:00:00Z` (the moment the
mock clock was advanced to, not any later moment — there is no "day step" to
conflate it with now, which is exactly what the previous version's real bug
was), a result row per rider.

**Then run `manage.py tick` a second time.** The race must stay `finished`
with the same result count — proves exactly-once still holds with the new
lock target.

**The concurrency check** (unchanged in spirit from the previous version, now
locking races instead of a clock row):

```bash
# after seeding one due race, with the mock clock already advanced past it:
.venv/bin/python manage.py tick &
.venv/bin/python manage.py tick &
wait
.venv/bin/python -c "
import django, os; os.environ['DJANGO_SETTINGS_MODULE']='config.settings.dev'; django.setup()
from racing.models import RaceResult
print(RaceResult.objects.count())
"
```

Count must equal the rider count exactly, same failure signature as before: a
doubled count means the lock did not do its job, and a race condition here
would surface as a failed second tick (a `UniqueConstraint` violation on
`RaceResult`), not silent duplication.

**The `RealClock` sanity check**, new to this revision — nothing in the
previous version's verification actually exercised production's clock at all:

```bash
DJANGO_SETTINGS_MODULE=config.settings.prod \
DJANGO_SECRET_KEY=x POSTGRES_DB=cycling_manager POSTGRES_USER=cycling POSTGRES_PASSWORD=cycling \
  .venv/bin/python -c "
import django, os; django.setup()
from world.services import now
from django.utils import timezone
print(abs((now() - timezone.now()).total_seconds()) < 1)
"
```

Expect `True` — proves `prod.py`'s settings actually resolve to `RealClock`
and that it reads live time, not a stale default. This is the check that
would have caught a `GAME_CLOCK_CLASS` typo or a `prod.py` that accidentally
inherited `dev.py`'s override.

**Frontend:** unchanged from before —
`npm --prefix frontend run build && .venv/bin/python manage.py runserver`,
confirm the sidebar shows a date/time that visibly advances every second
(already built in the previous version's W9 — this plan does not touch
`useClock.ts`'s polling behaviour) and matches real time to within the 60s
poll interval, since `RealClock` is what `dev.py` would use if `GAME_CLOCK_CLASS`
were flipped — but `dev.py` defaults to `MockClock`, so the manual check
should instead confirm the sidebar advances from wherever `mock_clock set`
left it, once a developer has moved it there.

## Risks

| Risk | Mitigation |
|---|---|
| **The module-level `_clock` singleton goes stale across a settings override in tests.** A test using `@override_settings(GAME_CLOCK_CLASS=...)` sees no effect because `get_clock()` already cached the old instance from an earlier test. | W3's required `conftest.py` fixture resetting `world.services._clock = None`. Review any new test touching `GAME_CLOCK_CLASS` for this fixture's presence. |
| **A `mock_clock` invocation slips through against `RealClock` in a misconfigured environment.** | The `isinstance` guard in every subcommand (decision 5), tested explicitly by `::test_raises_when_real_clock_is_active`. |
| **`select_for_update()` on the races table causes more lock contention than the old single-row lock**, once the calendar (#7) puts real density of races on the clock and many are due in the same claim. | Accepted for now — the spec explicitly defers "several races worked out at the same time"; this plan does not attempt to solve a problem that does not exist yet with today's near-empty calendar. Revisit when #7 lands. |
| **`catch_up_max_races` interacting with `_reclaim_unfinished()`'s count** — if reclaimed races alone exceed the cap, `_claim(limit=max_races - len(reclaimed))` goes negative, and a Python slice with a negative stop silently returns nothing (not an error), which could look like "capped" when actually nothing new was claimed. | `tick()` should clamp with `max(0, max_races - len(reclaimed))` — call this out explicitly in W3's implementation, and add a test case for "reclaimed alone exceeds the cap" to `test_tick_is_capped_at_catch_up_max_races`. |
| **Removing `TickRun.trigger` loses the ability to tell "was this a cron run or a developer's manual `tick` invocation" from the audit log.** | Accepted per decision 7 — `tick()` has one behaviour now regardless of caller, so the distinction described nothing real to keep. If this is missed operationally later, it is cheap to re-add as a field the *management command* stamps, not something `tick()` itself needs to know. |
| **A reviewer expects `tick --to-next` / `--day` to still exist** because they are named in the still-open PR #48's description and the old `world/README.md`. | *Documentation update* rewrites both. Flag this explicitly in the PR body update: name the removed flags and point at `mock_clock` as the replacement, so review does not flag it as an accidental regression. |

## Open questions

None blocking. The spec's open question (hosting) is unaffected by this
revision — an always-on host with an hourly scheduled task is still the
requirement, regardless of which clock implementation backs `now()`.

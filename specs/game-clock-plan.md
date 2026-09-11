# Game clock — Implementation Plan

**Spec:** `specs/game-clock.md` · **Issue:** [#6](https://github.com/mario595/cycling-manager/issues/6) · **Status:** proposed
**Apps touched:** `world/` (**new**), `racing/`, `api/` (**new**), `frontend/`, `config/`

## Context you need

The repo today is a fast, Django-free race simulator (`race_engine/`) with a thin
Django layer around it. Read `racing/README.md` before anything else in this
plan — it holds the rules this work is bound by.

**What exists:**

- `racing/models.py` — `Race` (name, `course` JSON, wind settings, seed),
  `RaceLog` (a `FileField` pointer plus metadata), `RaceResult` (one row per
  rider per race). A `Race` has **no date and no status**; nothing schedules it.
- `racing/adapters.py` — the **only** module permitted to import `race_engine`.
  It converts a `riders.Rider` row to an engine dataclass, a `Race.course` JSON
  blob to an engine `Course`, and a list of teams to the log's colour map. It
  converts; it does not run anything.
- `race_engine.models.run_race(riders, course, log_path=..., seed=..., team_codes=..., wind=..., wind_band=...)`
  → `list[RiderState]`, each with `.rider`, `.finish_time` (int seconds or
  `None`). It writes the JSONL log itself, through a raw `open()`.
- `core/models.TimeStampedModel` — abstract `created_at` / `updated_at`. Its
  docstring already says these are wall-clock, **never** in-game dates, and that
  game time will live in `world/`.
- `config/settings/{base,dev,prod}.py`; `LOCAL_APPS` in `base.py`; `config/urls.py`
  has a commented-out `path("api/", include("api.urls"))` waiting for this work.
- `frontend/` — a React SPA scaffold with **no API calls at all**. Every value
  comes from `src/placeholderData.ts`. `TEAM.season` (`'SEASON 3 · WK 14'`) is
  rendered in `Sidebar.tsx`; `DASHBOARD.eyebrow` is rendered in `Dashboard.tsx`.
  `vite.config.ts` already proxies `/api` to Django on :8000.

**What does not exist and is easy to assume does:**

- **There is no code anywhere that simulates a `Race` into a `RaceLog` and
  `RaceResult` rows.** `grep -rn "RaceLog.objects" --include=*.py .` returns
  nothing. The engine has only ever been driven by `python -m race_engine`,
  which writes to `race_player/public/` and touches no database. Part of this
  plan builds that service, because the clock has nothing to trigger otherwise.
- There is no `management/` directory in any app. This plan adds the first ones.
- There is no `api/` app, no serializer, no DRF view, no `api/urls.py`.
- There is no season and no calendar (#5, #7). A `Race` gets a start time here
  and nothing more; `schedule/` will own the calendar later.

**Repo rules that bind this work:**

- `race_engine/` imports nothing from Django, ever. Only `racing/adapters.py`
  imports the engine. This plan does not change either.
- Dependency direction (`AGENTS.md`): `world/` and `api/` may know about
  everything; **nothing may import them.** So `racing/` must not import `world/`.
- Postgres in dev and prod alike. Tests are pytest via `.venv/bin/python -m pytest`.
- Race logs are authoritative records, never regenerated.

## Goal

When this is done:

- A single `GameClock` row holds the world's current game datetime, and
  `world.services.now()` is the one way any code asks what time it is.
- `python manage.py tick` advances that clock to the next due moment, fires what
  is due, and is safe to run from cron every hour — concurrently, or interrupted
  mid-run, without anything firing twice.
- A `Race` carries a game-time `starts_at` and a status that moves
  `scheduled → running → finished`, and a due race is actually simulated: its
  log file and `RaceResult` rows are written.
- A developer can run `manage.py tick --to-next` or `manage.py tick --day` to
  walk a world forward deliberately.
- Every advance writes a `TickRun` row recording what it did.
- The SPA shows the game date and time, fetched from `GET /api/world/clock/`.

## Design decisions (settled — implement these, do not substitute)

### 1. The clock is a single row, pinned to `pk=1`, and read through a service

`world.models.GameClock` is a normal model with `id` forced to 1 by
`GameClock.load()`. **Do not** use a settings value, a cache key, a
`django-solo` dependency, or a `Singleton` metaclass.

A row is the right shape because the clock must participate in the same
transaction and the same row lock as the work an advance does. A cached or
in-memory clock cannot give the exactly-once guarantee that spec item 4
demands, and that guarantee is the entire reason this feature is built first.

**All reads go through `world.services.now()`**, never `GameClock.objects.get()`
in calling code. That indirection is what makes spec item 11 ("game code reads
the game clock, never `datetime.now()`") enforceable later, and it is the only
thing later features have to remember.

### 2. Exactly-once comes from `SELECT ... FOR UPDATE` on the clock row — load-bearing

Every advance opens a transaction and takes a row lock on the clock **first**:

```python
with transaction.atomic():
    clock = GameClock.objects.select_for_update().get(pk=1)
    ...
```

A second `tick` process arriving while the first holds the lock blocks until the
first commits, then re-reads a clock that has already moved past the work it was
about to do. That is the whole concurrency design.

**Do not** reach for `select_for_update(nowait=True)` or a
`skip_locked` variant here: a blocked second tick that then finds nothing to do
is the correct behaviour, and a tick that errors out because another was running
is worse than one that waits. **Do not** substitute a Postgres advisory lock —
it works, but it is a second mechanism to reason about when the row lock the
transaction already needs is sufficient.

This is the single load-bearing detail in the plan. If it is got wrong, nothing
downstream is trustworthy and the failure only shows up under concurrency.

### 3. Work is claimed by a status transition inside the lock, executed outside it

Spec: *"Becoming due and being carried out are separate things."* A race takes
~8 real seconds. Holding a database transaction open for that — times however
many races a catch-up finds — is how you end up with lock contention and a
tick the host kills mid-transaction.

So each step of an advance is two phases:

1. **Claim (inside the transaction, holding the clock lock):** move the clock
   to the due moment, flip every race due at that moment from `scheduled` to
   `running`, collect their ids, commit.
2. **Execute (outside any transaction):** simulate each claimed race, then write
   its results and flip it to `finished` in its own small transaction.

A crash between the phases leaves a race `running` with no results. That is
exactly the state spec item 5 describes as *racing now*, and the next tick
re-claims it (see decision 4). **Do not** simulate inside the clock transaction.

### 4. A `running` race with no results is re-claimed by the next tick

Because claiming is a status flip and execution is separate, a killed tick can
strand a race in `running`. `advance()` therefore begins by re-claiming any race
that is `running` and has no `RaceResult` rows, and executing it, **before**
looking at the clock at all.

This is what makes "still only ever run once" true across a restart: the flip to
`running` is the claim, and `finished` is only ever written together with the
results in one transaction. A race is never simulated twice because a second
simulation would have to find it `scheduled`, and it is not.

**Do not** handle this with a timeout ("re-run anything `running` for more than
N minutes"). There is one tick process; there is no legitimate concurrent owner
to race with, and a timeout would be a guess.

### 5. Advancing means jumping to the next due moment, not stepping hour by hour

`advance()` asks "what is the earliest `starts_at` after the current clock, and
is it within the cap?" — and moves there. It does not loop in one-hour
increments. With nothing scheduled (the state this ships in), an advance is one
query and one `UPDATE`, which is what makes an hourly cron nudge free.

The horizon of an advance is `min(next_due, now + cap)` where `cap` is 72 hours
of game time (spec). When nothing is due inside the horizon, the clock moves to
the horizon and the run ends uneventfully — spec item 9.

### 6. Real time drives the clock; the clock does not drive itself

In production one game week passes in one real week (spec item 3), so the clock
must not advance further than real time has. `advance()` computes a **real-time
ceiling**: `clock.current + (real_now - clock.last_advanced_at)`, capped at 72
hours. The world therefore tracks real time by construction, including across an
outage — item 6's catch-up is simply a large elapsed real interval — and cannot
run ahead of it.

`--to-next` and `--day` (developer stepping, item 8) bypass the ceiling but
**not** the exactly-once machinery. That is the only difference between a
developer step and a production nudge, and it is why there is no speed
multiplier anywhere: stepping *is* the fast-forward.

`last_advanced_at` is real wall-clock (`django.utils.timezone.now()`) and is the
**one** place in game code permitted to read real time. Say so in the code.

### 7. `racing/` owns simulation; `world/` calls it — never the reverse

`AGENTS.md` forbids `racing/` importing `world/`. So:

- `racing/services.py` (**new**) gets `simulate_race(race)` — knows how to run
  one race and record it, knows nothing about time.
- `world/services.py` imports `racing` and calls it.

`world/` is allowed to import everything; that is its job. When `schedule/`
arrives it will register its own due-work in the same shape.

**Do not** put a `Race.simulate()` method on the model and call it from the
clock — the seam is `racing/services.py`, matching how `adapters.py` already
isolates engine knowledge.

### 8. The log file goes through Django storage, with one unavoidable temp file

`racing/README.md` is explicit: logs are written through Django's storage API,
never a raw `open()`. But `race_engine.run_race` takes a filesystem `log_path`
and opens it itself, and the engine may not learn about Django.

Resolution: `simulate_race` runs the engine into a `tempfile.TemporaryDirectory`,
then saves the finished file into the `RaceLog.file` `FileField`. One extra copy
per race, paid once, in exchange for keeping both rules intact. **Do not** pass a
storage path into the engine and **do not** give the engine a file-like
parameter — that is engine surgery for a Django convenience.

### 9. `api/` is created now, minimally, because the clock needs the first endpoint

Spec item 2 requires the date visible to the player. That needs an endpoint, and
`AGENTS.md` says DRF routers aggregating each app's serializers live in `api/`.
One app, one `urls.py`, one view, wired into `config/urls.py` at the line
already commented there.

The clock endpoint is **public** (`AllowAny`), overriding the project-wide
`IsAuthenticated` default in `REST_FRAMEWORK`. The world's date is not private,
and there is no login flow in the SPA yet — an authenticated endpoint would
render the feature invisible.

### 10. Game datetimes are timezone-aware UTC `DateTimeField`s

`USE_TZ = True` and `TIME_ZONE = "UTC"` already. Game time uses the same aware
UTC datetimes as real time — different meaning, identical representation. **Do
not** invent a custom field, an integer offset-from-epoch, or a naive datetime;
the mixing hazard is real but it is addressed by naming (`starts_at` is game
time, `created_at` is real) and by routing every read through
`world.services.now()`, not by a type.

## Data model

### `world.models.GameClock` (new) — `world/migrations/0001_initial.py`

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `id` | `BigAutoField` | no | — | Always 1. Enforced by `load()`, not by a constraint. |
| `current` | `DateTimeField` | no | — | The world's game datetime, aware UTC. Set at creation. |
| `last_advanced_at` | `DateTimeField` | no | — | **Real** wall-clock time of the last successful advance. |
| `catch_up_hours` | `PositiveSmallIntegerField` | no | `72` | Per-advance cap, in game hours. Configuration, per spec. |

Not a `TimeStampedModel` — `created_at`/`updated_at` on the clock itself would be
three timestamps of three different kinds on one row, which is the confusion this
feature exists to remove.

```python
@classmethod
def load(cls) -> GameClock:
    """The one clock row, created at the current real time on first call."""
    now = timezone.now()
    obj, _ = cls.objects.get_or_create(
        pk=1, defaults={"current": now, "last_advanced_at": now},
    )
    return obj
```

### `world.models.TickRun` (new) — same migration

Spec item 10: each advance leaves a record.

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `started_at` | `DateTimeField` | no | `auto_now_add` | Real time. |
| `finished_at` | `DateTimeField` | yes / yes | `None` | Real time. Null means the run did not complete. |
| `from_game_time` | `DateTimeField` | no | — | Clock before. |
| `to_game_time` | `DateTimeField` | no | — | Clock after. Equal to `from_game_time` when nothing moved. |
| `races_started` | `PositiveIntegerField` | no | `0` | Races claimed this run. |
| `races_finished` | `PositiveIntegerField` | no | `0` | Races whose results were written this run. |
| `capped` | `BooleanField` | no | `False` | True when the 72-hour cap limited the advance. |
| `trigger` | `CharField(max_length=20, choices=Trigger)` | no | `CRON` | `cron` / `to_next` / `day`. |
| `error` | `TextField` | no / yes (`blank=True`) | `""` | Traceback if the run failed. Empty on success. |

`Meta.ordering = ["-started_at"]`, and `models.Index(fields=["-started_at"])`.

### `racing.models.Race` — changes, `racing/migrations/0002_race_schedule.py`

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `starts_at` | `DateTimeField` | yes / yes | `None` | **Game** time, on the hour. Null = unscheduled; such a race is never picked up by a tick. |
| `status` | `CharField(max_length=12, choices=Status)` | no | `SCHEDULED` | See below. |
| `finished_at` | `DateTimeField` | yes / yes | `None` | **Game** time the result was recorded. |

```python
class Status(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    RUNNING = "running", "Racing now"
    FINISHED = "finished", "Finished"
    FAILED = "failed", "Failed"
```

Choices live on the model as a `TextChoices` inner class, matching
`riders.Rider.Role`. `FAILED` is not in the spec's three states but is required:
a race whose simulation raises must not sit `running` forever being re-claimed on
every tick. It is an operator-visible dead end, shown to the player as finished
without a result.

Index: `models.Index(fields=["status", "starts_at"], name="race_due_idx")` — the
due query filters on exactly this pair and runs on every tick.

Docstring update on `Race`: `starts_at` and `finished_at` are **game** time;
`created_at`/`updated_at` (from `TimeStampedModel`) are real time.

No changes to `RaceLog` or `RaceResult`.

## `world/services.py` (new)

The module every later feature will import. Four public functions.

```python
def now() -> datetime:
    """The current game time. Every piece of game code asks here, never
    `timezone.now()` / `datetime.now()`."""

def advance(trigger: str = TickRun.Trigger.CRON, to_next: bool = False,
            days: int = 0) -> TickRun:
    """Advance the world once and return the record of what happened."""

def due_races(before: datetime) -> QuerySet[Race]:
    """Scheduled races whose start time is at or before `before`."""

def _reclaim_unfinished() -> list[int]:
    """Race ids left `running` with no results by an interrupted run."""
```

The claim phase, written out because the natural first attempt gets it wrong:

```python
def _claim(clock_pk: int, to_next: bool, days: int) -> tuple[datetime, datetime, list[int], bool]:
    """Move the clock and claim what is due. Returns (before, after, race_ids, capped).

    Everything here runs inside one transaction holding a row lock on the
    clock. It does NO simulation: races are only flipped to RUNNING, and the
    work happens after this returns and the lock is released.
    """
    with transaction.atomic():
        clock = GameClock.objects.select_for_update().get(pk=clock_pk)
        before = clock.current
        cap = timedelta(hours=clock.catch_up_hours)

        if days:
            horizon, capped = before + timedelta(days=days), False
        elif to_next:
            nxt = due_races_after(before).first()
            horizon = nxt.starts_at if nxt else before
            capped = False
        else:
            # Production: never move further than real time has, nor than the cap.
            # `timezone.now()` here is the ONE sanctioned read of real time.
            elapsed = timezone.now() - clock.last_advanced_at
            horizon = before + min(elapsed, cap)
            capped = elapsed > cap

        race_ids = list(
            Race.objects.filter(
                status=Race.Status.SCHEDULED,
                starts_at__isnull=False,
                starts_at__gt=before,
                starts_at__lte=horizon,
            ).order_by("starts_at").values_list("pk", flat=True)
        )
        Race.objects.filter(pk__in=race_ids).update(status=Race.Status.RUNNING)

        clock.current = horizon
        clock.last_advanced_at = timezone.now()
        clock.save(update_fields=["current", "last_advanced_at"])

    return before, horizon, race_ids, capped
```

Three details that are load-bearing and easy to drop:

- **`starts_at__gt=before`**, not `__gte`. A race exactly at the current clock
  was claimed by the advance that reached that moment; `__gte` re-claims it,
  which is only harmless because status filtering catches it — do not rely on
  that.
- **`.update()`, not a loop of `.save()`.** One statement, inside the lock,
  atomic against a concurrent reader.
- **`clock.last_advanced_at = timezone.now()`** is assigned *after* the work is
  laid out, not read once at the top. It anchors the next advance's elapsed
  calculation, so drift here compounds.

`advance()` then, outside the transaction, calls `racing.services.simulate_race`
for each reclaimed id and each claimed id in order, counting successes, and
writes the `TickRun`. An exception from one race is caught, recorded on that
`Race` as `FAILED`, appended to `TickRun.error`, and the loop continues — one
broken course must not stop the world.

**`--day` processes everything within the day** (spec item 8) by looping
`_claim(days=0, to_next=True)` until the clock passes `before + 1 day`, then
setting the clock to exactly that. Write it as a loop over `_claim`; do not
reimplement the claim logic a second time.

## `world/management/commands/tick.py` (new)

```
manage.py tick                # production nudge: advance by elapsed real time, capped
manage.py tick --to-next      # jump to the next scheduled moment
manage.py tick --day          # advance one game day, processing everything in it
manage.py tick --day 7        # seven of them
```

`--to-next` and `--day` are mutually exclusive; the command errors with
`CommandError` if both are given. It prints a one-line summary — clock before,
clock after, races started, races finished, whether capped — and exits non-zero
if `TickRun.error` is non-empty, so cron mail carries a real signal.

## `world/management/commands/set_game_date.py` (new)

`manage.py set_game_date 2027-03-01T09:00` — sets `current` and resets
`last_advanced_at` to real now. Development and admin only; the spec puts a
player-facing version out of scope. It refuses to move the clock **backwards**
past a `finished` race unless `--force` is given, because a rewound clock makes
already-run races due again in a world that has their results.

## `racing/services.py` (new)

```python
def simulate_race(race: Race, *, game_time: datetime) -> list[RaceResult]:
    """Run one race through the engine and record it.

    `game_time` is the world's current game time, passed in because `racing/`
    may not import `world/` (AGENTS.md). It is stored as `Race.finished_at`.

    Assumes the caller has already claimed the race (status RUNNING). Writes
    the log through Django storage, the results in one transaction, and flips
    the race to FINISHED. Idempotent only in the sense that a FINISHED race is
    refused: call it once per claim.
    """
```

Shape, with the parts that are easy to get wrong spelled out:

```python
def simulate_race(race: Race, *, game_time: datetime) -> list[RaceResult]:
    if race.status == Race.Status.FINISHED:
        raise ValueError(f"{race} is already finished")

    db_riders = list(Rider.objects.select_related("team"))
    if not db_riders:
        raise ValueError("no riders to race")
    # to_team_codes takes Teams, so free agents contribute none — the adapter
    # already races a teamless rider as their own one-person team.
    teams = [r.team for r in db_riders if r.team_id]

    engine_riders = [to_engine_rider(r) for r in db_riders]
    course = to_engine_course(race)

    # The engine writes the log itself with a raw open(), and it may not learn
    # about Django. So it writes to a temp file and we hand the finished file
    # to storage. See racing/README.md — logs never bypass the storage API.
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / f"race-{race.pk}.jsonl"
        states = run_race_via_adapter(          # racing/adapters.py — see below
            engine_riders, course, str(log_path), race.seed,
            to_team_codes(teams), race.wind_enabled, race.wind_band or None,
        )
        tick_count = sum(1 for _ in log_path.open())
        size = log_path.stat().st_size
        with log_path.open("rb") as fh:
            saved = ContentFile(fh.read(), name=f"race-{race.pk}.jsonl")

    by_pk = {str(r.pk): r for r in db_riders}
    finishers = sorted(
        states,
        key=lambda s: (s.finish_time is None, s.finish_time if s.finish_time is not None else 0),
    )

    with transaction.atomic():
        RaceLog.objects.update_or_create(
            race=race,
            defaults={"file": saved, "tick_count": tick_count, "size_bytes": size},
        )
        results = RaceResult.objects.bulk_create([
            RaceResult(
                race=race, rider=by_pk[s.rider.id], position=i,
                finish_time=float(s.finish_time) if s.finish_time is not None else None,
            )
            for i, s in enumerate(finishers, start=1)
        ])
        race.status = Race.Status.FINISHED
        race.finished_at = game_time      # passed in; racing/ must not import world/
        race.save(update_fields=["status", "finished_at"])
    return results
```

Notes the reader needs:

- **`racing/` must not import `world/`** (`AGENTS.md`). `finished_at` is
  therefore a **parameter**: `simulate_race(race, *, game_time: datetime)`. The
  clock passes its own `current`. Do not import `world.services` here.
- **`RaceResult` has a `unique_position_per_race` constraint**, so position must
  be dense and start at 1. Non-finishers still get positions, ordered after
  every finisher — the sort key above does that.
- Every rider in the database races, because there is no squad selection yet
  (#37) and no calendar to say who is entered. Say so in a comment; it is a
  deliberate placeholder, not an oversight.
- `bulk_create` inside the same transaction as the status flip is what makes
  decision 4's "running with no results" a reliable crash signal.

## `racing/adapters.py` — one addition

`run_race` lives in `race_engine`, so only this module may call it. Add:

```python
def run_race_via_adapter(riders, course, log_path, seed, team_codes, wind, wind_band):
    """Call the engine's `run_race`. Exists so `racing/services.py` can run a
    race without importing `race_engine` — see this file's module docstring."""
    from race_engine.models import run_race
    return run_race(riders, course, log_path=log_path, seed=seed, verbose=False,
                    team_codes=team_codes, wind=wind, wind_band=wind_band)
```

`verbose=False` matters: the engine's progress printer writes `\r`-terminated
lines to stderr, which turns cron mail into noise.

## `api/` (new app)

- `api/apps.py`, added to `LOCAL_APPS` in `config/settings/base.py`.
- `api/serializers.py` — `GameClockSerializer`: read-only `current`,
  `catch_up_hours`, plus a `SerializerMethodField` `last_tick` returning the most
  recent `TickRun.finished_at` (or null). No migration; `api/` owns no models,
  so it gets `migrations/__init__.py` and nothing else.
- `api/views.py` — `ClockView(APIView)` with `permission_classes = [AllowAny]`
  (decision 9) and a `get` returning the serialized clock.
- `api/urls.py` — `app_name = "api"`, `path("world/clock/", ClockView.as_view(), name="clock")`.
- `config/urls.py` — uncomment/replace with `path("api/", include("api.urls"))`,
  **above** the SPA catch-all. The catch-all is a `<path:unused>` and will
  swallow `/api/...` if ordered after it.

`GET /api/world/clock/` → `{"current": "2026-09-11T14:00:00Z", "catch_up_hours": 72, "last_tick": "..."}`.

## `frontend/` changes

The SPA has never made a fetch. Keep the first one small.

- `src/api.ts` (**new**) — `getClock(): Promise<Clock>` hitting
  `/api/world/clock/`. Relative URL: Vite already proxies `/api` to :8000 in
  dev, and in production Django serves both.
- `src/useClock.ts` (**new**) — a hook returning `{clock, loading, error}`.
  Polls every 60 s with `setInterval`, cleared on unmount. Polling, not a
  websocket: an hourly clock does not need a socket, and a socket needs ASGI.
- `src/components/Sidebar.tsx` — replace the hard-coded `TEAM.season` in the
  footer with the formatted game date, falling back to `TEAM.season` while
  loading or on error. Formatting stays in the component
  (`toLocaleDateString` + `HH:00`), in `font.mono` per the existing style.
- `src/placeholderData.ts` — leave `TEAM.season` in place as the fallback, with
  a comment saying it is now only a fallback. Do not delete it;
  `DASHBOARD.eyebrow` still uses the same invented season.

A failed fetch must not blank the sidebar. The fallback is the requirement, not
a nicety — the clock endpoint being down should not take the UI with it.

## Work items

### W1 — `world/`: create the app ✅ done
`startapp world`, delete `views.py` and `tests.py` from the scaffold, add
`"world"` to `LOCAL_APPS`, write `world/README.md` (sections per
*Documentation update*), add `world` to `testpaths` in `pyproject.toml`.
Nothing else — this lands on its own so everything after it has a home.
**Test:** `world/tests/test_app.py::test_world_app_is_installed` asserts
`apps.is_installed("world")`.

### W2 — `world/models.py`: `GameClock` and `TickRun` ✅ done
Both models, `GameClock.load()`, migration `0001_initial`, `world/admin.py`
registering both read-mostly.
**Test:** `world/tests/test_models.py::test_load_creates_single_clock` — call
`load()` twice, assert one row and `pk == 1`;
`::test_tick_run_orders_newest_first`.

### W3 — `racing/models.py`: `starts_at`, `status`, `finished_at` ✅ done
The three fields, the `Status` choices, the `race_due_idx` index, migration
`0002_race_schedule`, updated docstring, `status` and `starts_at` added to
`RaceAdmin.list_display` and `list_filter`.
**Load-bearing:** `starts_at` must be nullable — every existing `Race` row has
no schedule, and a non-null field would need a fabricated default game date.
**Test:** `racing/tests.py::test_race_defaults_to_scheduled_and_unscheduled`.

### W4 — `racing/services.py` + `racing/adapters.py`: `simulate_race` ✅ done
`run_race_via_adapter` in the adapter; `simulate_race(race, *, game_time)` in
the service. No clock involvement.
**Load-bearing:** the temp-file-then-storage path (decision 8), and dense
positions starting at 1 (the `unique_position_per_race` constraint).
**Test:** `racing/tests.py::test_simulate_race_writes_log_and_results` — a tiny
2-segment course and four riders; assert a `RaceLog` row exists with
`tick_count > 0`, `RaceResult` positions are `[1, 2, 3, 4]` with no gaps, and
`race.status == FINISHED`. Also `::test_simulate_race_refuses_finished_race`.

### W5 — `world/services.py`: `now()`, `_claim`, `advance()`
The full advance, including `_reclaim_unfinished` and the real-time ceiling.
`advance()` calls `racing.services.simulate_race`.
**Load-bearing:** `select_for_update()` on the clock row, and simulation running
outside that transaction.
**Test:** `world/tests/test_services.py` —
`::test_advance_with_nothing_scheduled_moves_time_only` (spec item 9),
`::test_advance_runs_a_due_race_once`,
`::test_advance_is_capped_at_catch_up_hours` (set `last_advanced_at` back 200 h,
assert the clock moved exactly 72 h and `TickRun.capped`),
`::test_second_advance_does_not_rerun_a_finished_race`,
`::test_interrupted_race_is_reclaimed` (create a `RUNNING` race with no results,
advance, assert it finishes and no duplicate `RaceResult` rows appear),
`::test_race_failure_marks_failed_and_continues` (a race with a malformed
`course`, plus a good one after it; assert the good one still ran).

### W6 — `world/management/commands/tick.py`
The command, its flags, its summary line, its non-zero exit on error.
**Test:** `world/tests/test_tick_command.py::test_tick_advances_clock` via
`call_command("tick")`; `::test_day_flag_processes_races_within_the_day`;
`::test_to_next_and_day_together_is_an_error` asserting `CommandError`.

### W7 — `world/management/commands/set_game_date.py`
Including the backwards-past-a-finished-race guard.
**Test:** `world/tests/test_set_game_date.py::test_sets_clock`;
`::test_refuses_to_rewind_past_a_finished_race_without_force`.

### W8 — `api/`: the app and the clock endpoint
`startapp api`, `LOCAL_APPS`, `migrations/__init__.py`, serializer, view,
`api/urls.py`, wire into `config/urls.py` above the catch-all, `api/README.md`,
add `api` to `testpaths`.
**Load-bearing:** `AllowAny` (the project default is `IsAuthenticated`) and URL
ordering before the SPA catch-all.
**Test:** `api/tests.py::test_clock_endpoint_returns_current_game_time` using the
DRF `APIClient` **unauthenticated** — an authenticated test would pass while the
real SPA got a 403.

### W9 — `frontend/`: show the clock
`src/api.ts`, `src/useClock.ts`, `Sidebar.tsx` wiring, the placeholder comment.
**Test:** no test runner exists in `frontend/` and this plan does not add one.
Proved by the manual check in *Verification*; `npm --prefix frontend run build`
must pass (it runs `tsc -b`), which is the real gate on this item.

### W10 — Documentation
`racing/README.md`, `AGENTS.md`, `README.md` per *Documentation update*.
`world/README.md` and `api/README.md` land with W1 and W8, not here.
**Test:** none. Reviewed, not tested.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7 → W8 → W9 → W10, and it is worth saying why
this order and not the obvious "clock first, then everything else":

- **W1–W2 first** because the app and its models are what every later item
  imports, and they are trivially verifiable on their own.
- **W3 and W4 before W5** — deliberately. W4 proves the hardest untested thing in
  the feature (a race actually simulating into the database) *without* any clock
  or concurrency in the picture. If the engine-to-storage path is broken, you
  find out in a test you can read, not inside a transaction-and-lock test where
  three things could be at fault.
- **W5 then W6** — the service is where the correctness lives; the command is a
  thin wrapper. Test the service directly, not through `call_command`.
- **W8 and W9 last** because they are the only player-visible part and they
  depend on nothing the earlier items need.

**Commit at each W.** The repo is green after every one: W1–W3 are additive,
W4 adds a service nothing calls yet, W5 wires them together.

## Documentation update (required, not optional)

### `world/README.md` (new, lands with W1)

Sections: **What this app owns** (the clock, the tick, nothing else yet);
**The clock discipline rule** — stated as the project rule the spec asks for:
*game code reads `world.services.now()`, never `timezone.now()` or
`datetime.now()`, when deciding whether something scheduled is due*, with the
one sanctioned exception (`last_advanced_at`) named and explained;
**How an advance works** — the two phases, and why simulation is outside the
lock; **Exactly-once** — the row lock, and the reclaim-on-restart rule;
**The 72-hour cap** — what it is, when it engages, that it is configuration;
**Running the tick** — the cron line, and the developer flags;
**What `world/` may import** (everything) and **what may import `world/`**
(nothing).

### `api/README.md` (new, lands with W8)

What lives here (routers and serializers aggregating other apps, no models);
the one endpoint that exists; that `/api/` must stay above the SPA catch-all;
that the project default is `IsAuthenticated` and the clock deliberately is not.

### `racing/README.md` (W10)

- **"Triggering simulations"** — replace "run from cron" with: `world/` owns the
  tick and calls `racing.services.simulate_race`; the deployment assumption is
  now **hourly**, not daily, per `specs/game-clock.md`. The spec calls out this
  change explicitly; make it here rather than leaving a stale sentence.
- **"What lives here"** table — add `starts_at`, `status`, `finished_at` to the
  `Race` row and note that those are game time.
- **New subsection "Simulating a race"** — `racing/services.py`, the temp-file
  hop and why (decision 8), and that `racing/` must never import `world/`.

### `AGENTS.md` (W10)

App table: `world/` → **built**, `README.md`, description "the game clock and
the tick"; `api/` → **built**, `README.md`. Both already have rows; change the
status column rather than adding rows.

### `README.md` (root, W10)

One line under running it: the tick command and that a development world is
stepped with `manage.py tick --day`.

## Verification

Unit tests:

```bash
docker compose up -d
.venv/bin/python manage.py migrate
.venv/bin/python -m pytest
```

**The end-to-end check that actually proves the feature**, because the unit
tests each prove one piece:

```bash
.venv/bin/python manage.py set_game_date 2027-03-01T09:00
.venv/bin/python manage.py shell -c "
from racing.models import Race
from django.utils.dateparse import parse_datetime
import json
# The bundled configs nest the course under a 'race' key; Race.course wants the list itself.
cfg = json.load(open('race_engine/configs/sprinters_classic.json'))['race']
Race.objects.create(name='E2E', course=cfg['course'], starts_at=parse_datetime('2027-03-01T14:00:00Z'))
"
.venv/bin/python manage.py tick --day
.venv/bin/python manage.py shell -c "
from racing.models import Race, RaceResult
from world.models import GameClock, TickRun
r = Race.objects.get(name='E2E')
print(r.status, r.finished_at, RaceResult.objects.filter(race=r).count())
print(GameClock.load().current)
print(TickRun.objects.first().__dict__)
"
```

Expect: `finished`, a `finished_at` of `14:00`, a result row per rider, a clock
at `2027-03-02T09:00`, and a `TickRun` with `races_started == races_finished == 1`.
`sprinters_classic.json` is a 130 km flat course — the fastest of the bundled
six to run. Note it takes real seconds, not milliseconds.

**Then run `tick --day` a second time.** The race must stay `finished` with the
same number of `RaceResult` rows. This is the check that catches the likeliest
failure mode below — a passing first run proves nothing about exactly-once.

**The concurrency check**, which no unit test covers honestly:

```bash
.venv/bin/python manage.py set_game_date 2027-03-01T09:00
# re-create the E2E race exactly as above, then:
.venv/bin/python manage.py tick --day &
.venv/bin/python manage.py tick --day &
wait
.venv/bin/python -c "
import django, os; os.environ['DJANGO_SETTINGS_MODULE']='config.settings.dev'; django.setup()
from racing.models import RaceResult
print(RaceResult.objects.count())
"
```

The count must equal the rider count exactly. A doubled count means the row lock
is not doing its job — and note that this would **not** surface as an error,
because `bulk_create` with duplicate positions violates
`unique_position_per_race` and raises, so the symptom is a failed second tick
rather than silent duplication. Either outcome is a failure; only a clean second
run passes.

**Frontend:**

```bash
npm --prefix frontend run build && .venv/bin/python manage.py runserver
```

Load `http://127.0.0.1:8000/`, confirm the sidebar footer shows the game date
(not `SEASON 3 · WK 14`), run `manage.py tick --day` in another shell, and
confirm the date advances within 60 seconds without a page reload. Then stop
Django's ability to answer by requesting `/api/world/clock/` against a stopped
server — the sidebar must fall back, not blank.

## Risks

| Risk | Mitigation |
|---|---|
| **Simulation left inside the clock transaction.** The natural way to write `advance()` is one `atomic()` block around everything. It passes every test, then holds a row lock for eight seconds per race in production. | Decision 3 and the `_claim` code above. Review for it specifically: `simulate_race` must not appear inside any `with transaction.atomic()` in `world/services.py`. |
| **Exactly-once believed rather than proven.** Single-process tests always pass. | The two-process concurrency check in *Verification*, plus `::test_second_advance_does_not_rerun_a_finished_race` and `::test_interrupted_race_is_reclaimed`. |
| **Game time and real time mixed.** Both are aware UTC datetimes; nothing in the type system stops `timezone.now()` being compared to `starts_at`. | Naming (`starts_at`/`finished_at` = game, `created_at`/`last_advanced_at` = real), the rule in `world/README.md`, and the single sanctioned real-time read in `_claim`. Spec defers automated enforcement. |
| **A race that always raises blocks every tick.** Without the `FAILED` state, a bad course is re-claimed forever. | `Race.Status.FAILED` (W3), the per-race try/except in W5, and `::test_race_failure_marks_failed_and_continues`. |
| **`/api/` swallowed by the SPA catch-all.** `config/urls.py` ends with `<path:unused>`; appending the API include gives a 200 of HTML where JSON was expected. | W8 names the ordering; `api/tests.py` hits the real URL through the project's URLconf, which fails loudly if ordering is wrong. |
| **Hosting sleeps the app.** The spec's own open question. A platform that idles the app cannot nudge the world, and races start late. | Out of this feature's hands. Recorded in `world/README.md` as a deployment requirement, and already logged against the deployment decision in the spec. |
| **A long catch-up costs ~8 s per race.** The 72-hour cap bounds it, but a dense future calendar could still make one tick long. | The cap is configuration (`GameClock.catch_up_hours`). Revisit when #7 puts real race density on the calendar; the spec defers parallel execution deliberately. |

## Open questions

None blocking. The spec's open question — where the game is hosted — constrains
deployment, not this implementation, and is already recorded against the
deployment decision.

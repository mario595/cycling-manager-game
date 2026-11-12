# The accelerated staging world — Implementation Plan

**Spec:** `specs/staging-clock.md` · **Issue:** #129 · **Status:** approved
**Apps touched:** `world/`, `config/settings/`

## Context you need

Every game rule reads time through `world.services.now()`, which goes to the
`Clock` named by `settings.GAME_CLOCK_CLASS` (`world/README.md`, *The clock
discipline rule* and *Which clock runs where*). There are two clocks today:
`RealClock` (production) and `MockClock`, a stopped clock kept in the single
`world.GameClock` row and moved by hand with `manage.py mock_clock`. The
`mock_clock` command and `seed_world --set-clock` both refuse to run unless the
active clock `isinstance(..., MockClock)`.

`manage.py tick` reads `now()` once and processes whatever is due. The deploy
image (#128, branch `claude/project-thread-7p565x`) runs `deploy/tick.sh` from
supercronic on the schedule `TICK_SCHEDULE`, with an optional
`TICK_ADVANCE_BY` that runs `mock_clock advance --by` first. This plan uses
that interface without editing it. Staging sets `TICK_SCHEDULE="*/5 * * * *"`
and leaves `TICK_ADVANCE_BY` unset, because the clock moves by itself.

`seed_world` (#139) builds four seasons. `world.world_setup.add_season()`
appends the next one from `seasons/world.json`.

`prod.py` is env-driven, but its clock is deliberately not, and staging gets
its own settings module for the same reason (spec, *In scope* 1).

## Goal

- `config/settings/staging.py` inherits `prod.py` and changes only the clock
  (accelerated, 24×) and `ALLOW_WORLD_RESET = True`.
- Under the accelerated clock, game time moves at 24× real time between any two
  reads, can be frozen and resumed, and can still be set or moved with
  `mock_clock`.
- `mock_clock status` reports game time, speed and whether the clock is frozen.
- With `AUTO_DECLARE_SEASONS` on (production and staging), the tick declares the
  next season whenever at most one declared season has not yet ended.

## Design decisions (settled — implement these, do not substitute)

1. **`AcceleratedClock` subclasses `MockClock`.** It is the same stored clock,
   except that time flows between writes. Subclassing means `mock_clock`,
   `seed_world --set-clock` and every `isinstance(clock, MockClock)` guard work
   unchanged. Do **not** write a third, unrelated clock class: every guard would
   then need a second `isinstance`.
2. **The stored row is an anchor, not a running total.** `GameClock.current` is
   the game time at the moment `GameClock.anchored_at` (real time) was written.
   `now()` is `current + (real_now − anchored_at) × speed`, or just `current`
   when frozen. Every write (set, advance, freeze, resume) first computes the
   effective game time under `select_for_update`, then re-anchors:
   `current = <new game time>`, `anchored_at = real_now`. Load-bearing: never do
   `current += delta` on the accelerated clock. That would ignore the time that
   has flowed since the last anchor. `MockClock` ignores `anchored_at`, but it
   still writes the field, so changing the class in settings never meets an
   old anchor.
3. **The speed is `settings.GAME_CLOCK_SPEED`**, an int, read on each `now()`
   call (so `override_settings` works in tests). `base.py` sets it to `1`, and
   `staging.py` to `24`. `AcceleratedClock` raises `ImproperlyConfigured` if the
   speed is below 1. It is not read from the environment (spec, *Decisions
   taken* 3).
4. **Freeze is a stored flag, `GameClock.frozen`.** It is stored rather than kept
   in memory because gunicorn workers and the cron tick are separate processes.
   `freeze()` and `resume()` live only on `AcceleratedClock`. `mock_clock freeze`
   and `mock_clock resume` on a plain `MockClock` refuse with "the mock clock is
   always stopped". Both are idempotent and return whether anything changed.
5. **`anchored_at` uses `django.utils.timezone.now()`.** This is the second
   sanctioned real-time read in `world/`, next to `TickRun.finished_at`. Record
   it in the README's clock discipline section.
6. **Automatic seasons run at the start of `tick()`, before
   `process_transitions`.** After a long outage that crosses the last season's
   end, the next season is then already declared when the close is recorded, so
   the open follows in the same tick. The rule is
   `Season.objects.filter(ends_at__gt=at).count() <= 1`, with at least one
   season declared, and it calls `add_season()` **once** per tick. A world with
   no seasons (a fresh dev database) is left alone. One season per tick is
   enough: the rule fires as soon as the last declared season opens, a full
   season ahead.
7. **`AUTO_DECLARE_SEASONS`** is `False` in `base.py` (so dev and tests are
   unaffected) and `True` in `prod.py` (so staging inherits it). The calendar is
   `world_setup.WORLD_CALENDAR`. A failure is caught and written to
   `TickRun.error`, the way the AI market's failures are. A broken calendar must
   not stop races.
8. **`TickRun.seasons_declared`** counts the seasons declared (0 or 1), for
   diagnosis, like the other counters.

## Data model

`world/migrations/0023_accelerated_clock.py`:

- `GameClock.anchored_at`: `DateTimeField(null=True, blank=True)`, real time.
  Null means it has never been anchored, and `AcceleratedClock` then treats the
  clock as anchored "now" (time starts flowing from `current`).
- `GameClock.frozen`: `BooleanField(default=False)`. Only meaningful under
  `AcceleratedClock`.
- `TickRun.seasons_declared`: `PositiveSmallIntegerField(default=0)`.

`GameClock.load()` defaults `anchored_at` to the same real `now` as `current`.

## world/clocks.py

```python
class MockClock(Clock):
    def now(self) -> datetime: return self._effective(GameClock.load(), timezone.now())
    def _effective(self, row, real_now) -> datetime: return row.current   # stopped
    def _write(self, row, game_time, real_now) -> None  # sets current + anchored_at, saves
    def set(self, when) / advance_by(delta) / advance_to_next_due()       # lock row, compute effective, _write

class AcceleratedClock(MockClock):
    @property speed -> int
    def _effective(self, row, real_now): frozen/no-anchor -> current; else current + (real_now - anchored_at) * speed
    def freeze(self) -> bool
    def resume(self) -> bool
    @property frozen -> bool
```

`advance_to_next_due` searches for races after the *effective* time, not after
`row.current`.

## world/management/commands/mock_clock.py

Add the subcommands `freeze`, `resume` and `status`. `status` prints three lines:
`game time: …`, `speed: 24x` (or `stopped` for `MockClock`), `frozen: yes/no`.

## world/services.py

`_declare_next_season_if_needed(at) -> tuple[int, str]`, called first in
`tick()`. It returns `(declared, error)`, and its results go on the `TickRun`.
Pass `stdout=io.StringIO()` to `add_season`, so the cron log isn't filled with
`load_season` output.

## config/settings

- `base.py`: `GAME_CLOCK_SPEED = 1`, `AUTO_DECLARE_SEASONS = False`, each with a comment.
- `prod.py`: `AUTO_DECLARE_SEASONS = True`.
- `staging.py` (new): `from .prod import *`, `GAME_CLOCK_CLASS =
  "world.clocks.AcceleratedClock"`, `GAME_CLOCK_SPEED = 24`, `ALLOW_WORLD_RESET =
  True`. Nothing else, so staging stays the production game.

## Work items

### W1 — `world/`: AcceleratedClock with freeze and resume
Migration, model fields and clock classes. Tests in `world/tests/test_clocks.py`,
with `timezone.now` patched in `world.clocks`:
- one real hour moves game time one day at speed 24;
- `set` and `advance_by` re-anchor, and time flows on from the new value;
- freeze holds the time, resume continues from the frozen value with no jump,
  and both are idempotent;
- `set` while frozen moves the frozen value and stays frozen;
- `MockClock` behaviour is unchanged;
- `advance_to_next_due` uses the effective time.

### W2 — `mock_clock`: freeze, resume and status
Tests in `world/tests/test_mock_clock_command.py`: each subcommand on the
accelerated clock, the refusal on a plain `MockClock`, and the status output.

### W3 — `config/settings/staging.py`
Test (`world/tests/test_staging_settings.py`): import the module with the
required env vars set, and assert the clock class, a speed of 24,
`ALLOW_WORLD_RESET`, `AUTO_DECLARE_SEASONS` and `DEBUG is False`. Also assert
that `prod.py`'s clock is `RealClock`, so prod can never inherit the
accelerated clock.

### W4 — tick: automatic seasons
Tests in `world/tests/test_tick.py` or a new `test_auto_seasons.py`, built with
`build_world(seasons=2)`:
- off by default: no season is added;
- on: nothing happens while two seasons are ahead; one is added when one
  remains, and it starts at the last season's `ends_at`;
- across an outage that passes the last season's end, the next season is
  declared and opened in one tick;
- a failing calendar is recorded on `TickRun.error` and the races still run.

### W5 — Docs and the agents' briefing
See below.

## Documentation update (required, not optional)

- `world/README.md`: *Which clock runs where* gets the staging row. *The clock
  discipline rule* gets `anchored_at`. New sections: *The accelerated clock
  (#129)* (the anchor maths, freeze/resume/status, catch-up after downtime, and
  freezing before planned downtime longer than about three real days) and
  *Automatic seasons*. Change the *Building a world* line that says keeping
  seasons supplied "belongs to the deployment".
- `world/STAGING_BRIEFING.md` (new): the agents' briefing, linked from the
  README for #132.
- `AGENTS.md`: the `world/` row mentions the accelerated clock and automatic
  seasons.
- Move the spec and the plan to `specs/archive/` with `Status: implemented`.

## Verification

Run the full suite. Then a manual run on the accelerated clock: `seed_world
--set-clock`, `mock_clock status`, wait a minute (24 game minutes), `status`
again, `freeze`, `tick`, `status`. The likeliest bug is a write that adds the
delta to the stale `current` and drops the flowed time. The re-anchor tests
catch it.

## Risks

| Risk | Mitigation |
|---|---|
| Production ends up on the accelerated clock. | The clock is only set in `staging.py`. The W3 test asserts prod's clock is real. |
| A write loses the time that has flowed. | Decision 2, tested in W1. |
| Automatic seasons fire in tests or dev. | Off in `base.py`, and tests use dev settings. |
| `prod.py` conflicts with #128's edits. | The change is one line at the end of the file. |
| A stray `TICK_ADVANCE_BY` on staging doubles the speed. | Documented: leave it unset on staging. |

## Open questions

None.

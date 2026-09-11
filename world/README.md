# World — the game clock and the tick

## Why this exists

Nothing in the game has a sense of *when* it is without a clock — no season,
no calendar, no wage day, no training week, and no race that starts on its
own. For the player, the clock is what turns a simulator into a world: a
race arrives because the date arrived, is shown as racing now while it is
being worked out, and has a result once it's known. If the player is away
for a while, the races that were scheduled in the meantime have results
waiting when they come back — nothing they did caused any of it; time
passed, and the world responded.

## What this app owns

The single source of truth for what time it is in the game, and the machinery
that finds and processes due work: `world/clocks.py` (`Clock`, `RealClock`,
`MockClock`), `GameClock`, `TickRun`, and the `tick` and `mock_clock`
management commands. Nothing else yet — no season, no calendar, no AI
decisions. Those are later work for this app (see `AGENTS.md`).

## The clock discipline rule

Game code reads `world.services.now()`, never `timezone.now()` or
`datetime.now()`, when deciding whether something scheduled is due.
`now()` reads whichever `Clock` is configured
(`settings.GAME_CLOCK_CLASS`) — real, live time in production, a
developer-controlled mock clock in dev and test.

The one sanctioned exception is `TickRun.finished_at`, set with
`django.utils.timezone.now()` inside `world/services.py`. That field records
when a check actually ran on the host — real time, regardless of which clock
the game itself is running on — and is not a stand-in for "is X due?"
anywhere.

There is no automated enforcement of this rule yet. It is a project
convention, not a constraint the code checks — worth revisiting once there
is enough timed behaviour elsewhere in the game for the rule to be worth
policing; today there is almost none.

## Which clock runs where

`settings.GAME_CLOCK_CLASS` names the active `Clock`, resolved once and
cached by `world.services.get_clock()`.

| Setting file | Clock | Notes |
|---|---|---|
| `config/settings/base.py` | `world.clocks.RealClock` | The default. No state, no database — `now()` returns `timezone.now()` directly. |
| `config/settings/dev.py` | `world.clocks.RealClock` | Same as prod by default, so a normal dev session just shows the actual time with no manual resyncing. **Read from the `GAME_CLOCK_CLASS` environment variable** — set it to `world.clocks.MockClock` for a session where you deliberately want to fast-forward a season, e.g. `GAME_CLOCK_CLASS=world.clocks.MockClock manage.py runserver`. |
| `config/settings/prod.py` | *(inherits `RealClock` from `base.py`)* | **Deliberately not read from the environment**, unlike `dev.py`. Every other production setting in `prod.py` is env-driven, but the clock is the one exception: a non-real clock must never be a live-game possibility — not disabled, not gated behind a permission, simply not a code path production runs. An environment variable is a code path in `dev.py`, by design; it is not one in `prod.py`, also by design. |

`manage.py mock_clock` refuses to run — raising `CommandError` — unless the
active clock is `MockClock`. This is the runtime enforcement that a mistaken
invocation cannot move time in an environment running `RealClock`.

**Tests always run against `MockClock`**, regardless of what `GAME_CLOCK_CLASS`
a developer's shell happens to have set — `world/tests/conftest.py`'s
`_use_mock_clock` fixture forces it for every test under `world/tests/`, and
`api/tests.py`'s clock test does the same locally. This is what makes the
suite deterministic: against `RealClock`, two separate `now()` reads
a millisecond apart would almost never compare equal.

## How a tick works

`manage.py tick` — the only entry point cron, or a developer, ever calls —
finds and processes whatever is due, in two phases:

1. **Claim** — inside one transaction, holding a row lock on the due race
   rows themselves (not a clock row — there is no longer one to lock in
   production): every `scheduled` race whose `starts_at` is at or before
   `now()` is flipped to `running`, up to `catch_up_max_races` at a time.
2. **Execute** — outside any transaction: simulate each claimed race and
   record its result.

Simulation is deliberately outside the claim transaction. A race takes real,
measurable time (~8 seconds); holding a database lock for that long, times
however many races a backlog holds, is how a tick ends up starving every
other reader and getting killed mid-transaction by the host.

## Exactly-once

The row lock (`SELECT ... FOR UPDATE` on exactly the due race rows) is what
makes a tick safe to run concurrently or interrupted: a second `tick`
arriving while one is in progress blocks on the lock, then re-runs its own
filter after the first commits — the rows just claimed are now `running` and
no longer match, so the second tick claims nothing.

Because claiming and executing are separate, a killed tick can strand a race
`running` with no results. The next call to `tick()` re-claims any such
race — found by `status=RUNNING` with no `RaceResult` rows — and executes it
before looking for anything newly due. A race only ever finishes once,
because `finished` is written together with its results in one transaction,
and a second simulation would need to find the race `scheduled`, which it
will not.

## The catch-up cap

`GameClock.catch_up_max_races` (default `50`) bounds how many due races one
tick will claim — reclaimed and newly-claimed races together count against
the same cap. Beyond it, `TickRun.capped` is set and the rest is picked up by
the next tick. This is configuration, not a fixed rule — it exists so an
exceptional backlog can be recovered from by raising it temporarily.

Unlike the previous design, there is no "clock catching up" — the game's
time is always the true current time. What can lag is *processing*: races
that fell due while nothing was checking are still worked out, in order, the
next time a tick runs.

## Running the tick

Production runs this hourly, from cron:

```bash
manage.py tick
```

A developer moves the mock clock by hand instead, then ticks to process
whatever that made due:

```bash
manage.py mock_clock set 2027-03-01T09:00   # jump to an exact moment
manage.py mock_clock advance --to-next      # jump to the next scheduled race
manage.py mock_clock advance --by 1d        # move forward by a duration
manage.py mock_clock advance --by 1d6h      # durations compose: 1 day 6 hours
manage.py tick                              # then process what's now due
```

Every `mock_clock` subcommand refuses to run unless `GAME_CLOCK_CLASS` is
`MockClock`.

## What is deliberately not built

- **No player control over the clock at all.** No pausing, no skipping, no
  per-player time — the clock is shared world state, moved only by
  `mock_clock` in development or by cron in production.
- **No in-game admin screen for the mock clock.** A command line tool is
  enough for now.
- **No parallel race processing.** A tick works through claimed races one at
  a time. Fine while a game day holds at most a handful of races; the
  frugal next step, once that stops being true, is a queue held in the
  database the game already has, with workers claiming races — no broker
  service needed.

## Deployment requirement

Production must be an **always-on host with a reliable hourly scheduled
task** running `manage.py tick`. A platform that sleeps idle applications
cannot check for due work while asleep, and races start late by however long
the sleep lasted — such platforms are ruled out by this feature. The task
also needs to run long enough to work out a day's races, currently around
eight seconds each.

## What `world/` may import

Everything. `world/` and `api/` are the two apps allowed to know about every
other domain (`AGENTS.md`), because the tick is where all scheduled work
across the game gets triggered from. `world/clocks.py`'s `MockClock` imports
`racing.models.Race` locally (inside `advance_to_next_due`) to find the next
scheduled race — allowed by the dependency direction, done locally purely to
keep the file's top-level imports scoped to `world/`'s own models.

## What may import `world/`

Nothing. In particular `racing/` must not import `world/` — see
`racing/README.md`'s *Simulating a race* section for how `finished_at` is
passed in rather than read from the clock directly.

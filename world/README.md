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
management commands. No calendar, no AI decisions — later work for this app
(see `AGENTS.md`).

The tick also records season and week boundaries as they're crossed, via
`schedule.services.process_transitions()` and
`process_week_transitions()` — see `schedule/README.md` for what a
transition is and why it's a row rather than an action — and, off the back
of those, advances every rider's age at a season close and applies each
week's growth plus the team's weekly training
([#58](https://github.com/mario595/cycling-manager/issues/58),
[#36](https://github.com/mario595/cycling-manager/issues/36); see
`riders/README.md`, *The age curve* and *Weekly training*).

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
reads `now()` once, then finds and processes whatever is due, in four steps:

0. **Transitions** — `schedule.services.process_transitions(at)` records any
   season boundary crossed at or before `now()` that hasn't been recorded
   yet (see `schedule/README.md`, *Exactly-once*). This runs **before**
   claiming races: a race in week 1 of a season that has just opened should
   be processed in a world that has already recorded the opening.
   Immediately after, `tick()` calls `staff.services.top_up_pool()` once
   per transition `process_transitions` actually wrote — the season-boundary
   hook's first consumer. Idempotency comes from that return value, not
   from anything tracked in `staff/`: a `SeasonTransition` row is written at
   most once ever, so a tick that runs twice, or catches up several weeks
   late, cannot top up the trainer pool twice for the same boundary. See
   `staff/README.md`.
1. **Ageing, growth, training and wages** — for every `CLOSED` transition
   `process_transitions` returned, every rider's age advances by one
   (`riders.services.advance_ages()`). Then
   `schedule.services.process_week_transitions(at)` records any week
   boundary opened at or before `now()` that hasn't been recorded yet (see
   `schedule/README.md`, *Week transitions*), and each recorded transition
   is applied **one week at a time**:
   `world.services._apply_training_week(week)` moves every rider along
   their age curve via `riders.services.apply_weekly_growth(weeks=1,
   extra_deltas=...)`, adding that week's training deltas — the trainer's
   focused skill and last week's racing — through the one `growth_debt`
   ledger, writes a per-team `staff.TrainingWeekReport` of the
   display-scale changes it made, and then settles freshness:
   `riders.services.apply_weekly_recovery(exclude_ids=set(raced))` restores
   one week's recovery to every rider who did **not** finish a race in the
   week being settled ([#59](https://github.com/mario595/cycling-manager/issues/59);
   see `riders/README.md`, *Freshness*). Recovery follows the same per-week
   shape as training — one pass per `CLOSED` transition, never collapsed for
   a late tick — because whether a rider raced differs week to week.
   [#58](https://github.com/mario595/cycling-manager/issues/58)'s single
   `apply_weekly_growth(weeks=len(weeks))` call is gone, deliberately:
   training cannot collapse to a count, because each week has its own focus
   and its own races — a tick that runs three weeks late must apply three
   *different* training weeks ([#36](https://github.com/mario595/cycling-manager/issues/36),
   the plan's Design decision 3; see `staff/README.md`, *Weekly training*).
   The same per-transition loop charges every team its wages for the week
   just closed — `economy.services.charge_weekly_wages(week)`, one combined
   `wages` entry per team per week, dated to `week.starts_at`
   (`economy/README.md`). The entry count is summed onto the tick's
   `TickRun.wage_entries` counter (the column added by
   `world/migrations/0006`), so each `TickRun` row records how many wage
   entries its parse wrote; idempotency is the `(team, week)` constraint,
   the same defence `charge_weekly_wages` and `WeekTransition` lean on.
   The same loop then settles the week's economy side (#21):
   `economy.services.apply_weekly_fanbase(week, points_by_team=...)`
   adjusts every team's fanbase and `economy.services.pay_merchandise(week)`
   pays each team its merchandise income — **in that order** (merchandise is
   paid on the *now-updated* fanbase), and both off the week that just
   *completed*, exactly as training reads it (see *Training's race half reads
   the week that just completed* below). `points_by_team` comes from
   `competitions.services.points_by_team(week)`: this is where
   `competitions/` meets `economy/`, because neither may import the other
   (`economy/README.md`, *Why `economy/` does not query `RacePoints`*).
   Each write is once per `(team, week)`, backed by the two `economy/`
   constraints, and the rows each parse writes land on the new
   `TickRun.fanbase_entries` / `TickRun.merchandise_entries` counters
   (the columns added by `world/migrations/0007`).
   Ageing runs before growth, so a rider who turned 33 at this same
   boundary is evaluated against the new age immediately. None of this
   touches a race row, so it runs outside the claim transaction below, the
   same as race simulation does and for the same reason: a full-table
   update must not extend the lock window race claiming holds.
2. **Claim** — inside one transaction, holding a row lock on the due race
   rows themselves (not a clock row — there is no longer one to lock in
   production): every `scheduled` race whose `starts_at` is at or before
   `now()` is flipped to `running`, up to `catch_up_max_races` at a time.
3. **Execute** — outside any transaction: simulate each claimed race,
   record its result, then score it (`competitions.services.score_race`).

**Training's race half reads the week that just completed, not the one being
entered.** A `WeekTransition` is written when a week *opens*, and the steps
above apply growth and training before claiming the races due now — so a
week's own races have not run yet at the moment its training is settled.
`_apply_training_week` therefore asks `_completed_week(week)` (the same
season's week `number - 1`) for `racing.services.riders_who_raced`, meaning
entering week N rewards week N-1's racing. Week 1 has no preceding week and
trains nothing from racing; a rider on a team with no trainer still gains
the race effect, just no report. This offsets the tick's internal ordering,
not the season's — a manager planning against the calendar sees a raced
week credited at the boundary into the next week.

**Scoring happens here, not inside `racing.services.simulate_race`.**
`racing/` may not import `competitions/` — that would invert the
dependency graph (`AGENTS.md`) — so the tick, which already imports both
to orchestrate them, is where a finished race's points are awarded. A race
that simulates but fails to score is treated as a broken race: the
existing per-race `try`/`except` in `_execute` marks it `FAILED` and
records the traceback, without stopping the rest of the tick.

`now()` is read once at the top of `tick()` and threaded through every step
as `at`, rather than re-read at each one — against `RealClock` those would
otherwise be three slightly different instants.

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

# World — the game clock and the tick

## What this app owns

The single source of truth for what time it is in the game, and the machinery
that moves that time forward: `GameClock`, `TickRun`, and the `tick` and
`set_game_date` management commands. Nothing else yet — no season, no
calendar, no AI decisions. Those are later work for this app (see
`AGENTS.md`).

## The clock discipline rule

Game code reads `world.services.now()`, never `timezone.now()` or
`datetime.now()`, when deciding whether something scheduled is due.

The one sanctioned exception is `last_advanced_at`, read with
`django.utils.timezone.now()` inside `world/services.py` when computing how
far real time has moved since the last advance. That is the only place in
game code permitted to read real time, and it exists to drive the clock, not
to answer "is X due?" for any feature.

There is no automated enforcement of this rule yet (see `specs/game-clock.md`,
*Deferred*). It is a project convention, not a constraint the code checks.

## How an advance works

An advance happens in two phases:

1. **Claim** — inside one transaction, holding a row lock on the clock: figure
   out how far time should move, flip every race due within that horizon from
   `scheduled` to `running`, move the clock, commit.
2. **Execute** — outside any transaction: simulate each claimed race and
   record its result.

Simulation is deliberately outside the claim transaction. A race takes real,
measurable time (~8 seconds); holding a database lock for that long, times
however many races a catch-up finds, is how a tick ends up starving every
other reader and getting killed mid-transaction by the host.

## Exactly-once

The row lock (`SELECT ... FOR UPDATE` on the single `GameClock` row) is what
makes an advance safe to run concurrently or interrupted: a second `tick`
arriving while one is in progress blocks on the lock, then re-reads a clock
that has already moved past the work it was about to do.

Because claiming and executing are separate, a killed tick can strand a race
`running` with no results. The next call to `advance()` re-claims any such
race — found by `status=RUNNING` with no `RaceResult` rows — and executes it
before looking at the clock at all. A race only ever finishes once, because
`finished` is written together with its results in one transaction, and a
second simulation would need to find the race `scheduled`, which it will not.

## The 72-hour cap

`GameClock.catch_up_hours` (default `72`) bounds how much game time a single
advance will work through. Beyond the cap, the clock moves as far as the cap
allows and `TickRun.capped` is set; the rest is picked up by the next advance.
This is configuration, not a fixed rule — it exists so an exceptional outage
can be recovered from by raising it temporarily, without changing the game.

`--to-next` and `--day` (developer stepping) bypass the cap, but not the
exactly-once machinery — that is the only difference between a developer step
and a production nudge.

## Running the tick

Production runs this hourly, from cron:

```bash
manage.py tick
```

A developer moves a world forward deliberately instead:

```bash
manage.py tick --to-next      # jump to the next scheduled moment
manage.py tick --day          # advance one game day, processing everything in it
manage.py tick --day 7        # seven of them
```

`manage.py set_game_date <ISO datetime>` sets the clock directly. Development
and admin use only — there is no player-facing way to move the clock.

## What `world/` may import

Everything. `world/` and `api/` are the two apps allowed to know about every
other domain (`AGENTS.md`), because the tick is where all scheduled work
across the game gets triggered from.

## What may import `world/`

Nothing. In particular `racing/` must not import `world/` — see
`racing/README.md`'s *Simulating a race* section for how `finished_at` is
passed in rather than read from the clock directly.

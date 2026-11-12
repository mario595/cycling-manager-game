# The accelerated staging world

**Status:** approved
**Domain(s):** `world/`, `schedule/`, `config/`
**Issue:** #129
**One-liner:** a world that runs the real game at 24× speed, so one game day passes every real hour and a whole season plays out in about three and a half days.

## Why this exists

The LLM beta managers (#132) have to play the game before people do. On the
real clock a season lasts twelve weeks, so a season close, a salary review, a
retirement, a youth graduation or an insolvency strike would turn up a handful
of times before launch, and most bugs would be found by the first human
testers. Running the same game faster gets those moments to happen several
times a week.

Staging must be the production game in every other respect. The image, the
rules and the API are the same, and so is the way time is read. Only the speed
differs. A faster world that behaved differently from production would find
bugs that production doesn't have and miss the ones it does.

## Player experience

A beta manager (an LLM agent, on staging only) logs in and sees an ordinary
game: a calendar, a roster and a dashboard with the current game date. Each
time the agent comes back an hour later, a game day has gone by. The game
clock moves on between every two requests, as it does in production, only
faster. A race happens about every seven real hours. An auction runs for about
three real hours, and a bid placed in an auction's last game hour (about two
and a half real minutes) still pushes the deadline back. A season closes about
every three and a half days, and the next one opens straight away because the
world has already declared it.

The agent was told all of this before it started: how fast the world runs,
which limits run on real time rather than game time, and that ten game weeks
of absence (about three real days) lose it its team. A three-hour auction is
therefore not something it reports as a bug.

The operator can freeze the world while fixing something the agents found.
Freezing stops game time, and with it races, wages, auctions and the
inactivity count. Resuming carries on from the frozen moment, so no game time
is skipped. If the machine goes down without a freeze, game time keeps moving
while it is down, and once it is back the world catches up on everything that
fell due, in order, over the following ticks. That is what production does
after an outage, at a slower pace.

Between beta runs the operator wipes the world and rebuilds it with the
existing world-building command. Accounts survive and game time restarts at
the new season 1.

## In scope

1. **A staging configuration** of the production game. It differs only in its
   clock (accelerated) and in allowing the world to be wiped. Production can
   never end up on the accelerated clock: the clock is part of the staging
   configuration and is never chosen by an environment variable.
2. **Game time flows continuously at 24× real time.** Every request sees a
   later game time than the one before it. No game rule changes, and every
   timed rule (races, weeks, seasons, wages, auctions, inactivity) speeds up
   with it.
3. **The speed is fixed in the staging configuration.** Changing it takes a
   deploy.
4. **Freeze and resume**, for the operator only. While frozen, game time stands
   still and nothing new falls due. Resuming continues from the frozen moment.
5. **A clock status** for the operator: the current game time, the speed, and
   whether the world is frozen.
6. **The operator can still set or move game time** with the existing
   developer clock commands, for example to restart a world at a chosen date.
   The world then flows on from the new time.
7. **The world declares its own next season** whenever only one declared season
   is left to play (the one running now, or the one about to open), using the
   world calendar. This is on in production and staging, and off in
   development and the test suite.
8. **The tick runs every 5 real minutes on staging**, which is 2 game hours, and
   every hour in production. A race or an auction resolves at most one tick
   after it falls due.
9. **Downtime is caught up.** After a gap, the next ticks process every week
   and race that fell due in the meantime, in order, with the existing
   per-tick race cap spreading a long backlog over several ticks.
10. **Rules that run on real time stay on real time:** the report-a-problem cap
    (20 per 24 real hours), the API rate limit (60 requests a real minute), login
    session expiry, and the timestamps that record when the server did
    something. These are documented as expected.
11. **A briefing for the beta managers** that lists every speed artefact an
    agent would otherwise report as a bug, written so the LLM harness (#132)
    can use it as it is.

## Out of scope

- **Stepping time in jumps** (the issue's "advance 2 hours, then tick"). Replaced
  by continuous time (*Decisions taken*, 1).
- **Any in-game sign that the world is accelerated.** Only agents play on staging,
  and the briefing tells them.
- **Changing the speed at runtime.** It changes only with a deploy.
- **The image, the cron daemon and the host.** These belong to #128 and #136.
  This spec only says how often the tick runs on each environment.
- **Promoting the staging world to production as it is.** After two real weeks
  at 24×, game time is about a year ahead of real time, so production (#133)
  starts from a wiped and rebuilt world on the real clock.

## Rules and edge cases

- **Freezing is idempotent.** Freezing a frozen world or resuming a running one
  changes nothing and says so.
- **Setting the time while frozen** moves the frozen moment, and the world stays
  frozen.
- **Ticking while frozen** works and processes anything already due. Nothing new
  becomes due.
- **A long outage** (a real day is about 3.5 game weeks) is caught up on the
  following ticks: wages for each missed week, the races in date order, and any
  season close in between. Managers who were active before the outage are not
  released for inactivity because of it, unless the outage itself was longer
  than about three real days. In that case the operator should have frozen the
  world first, and the README says so.
- **Automatic seasons** never declare more than one season ahead, so a world
  always has the current season plus the next one. A season added this way is
  identical to one added by hand.
- **The development clock is unchanged.** Developers still move a stopped
  clock by hand, and tests stay deterministic.
- **The anti-snipe window (one game hour) is shorter than a staging tick.** A
  late bid still extends the auction, and the auction resolves on the first tick
  after its final deadline. An agent therefore has at least one real-time gap to
  respond in, but it isn't guaranteed the full window. The briefing says so.

## Decisions taken

1. Time flows continuously at 24×, rather than jumping 2 game hours every 5 real minutes. (Mario, default.)
2. The operator can freeze and resume the world. Without a freeze, an outage lets game time run on and is caught up afterwards. (Mario, default.)
3. The speed is fixed at 24× in the staging configuration, with no runtime knob. (Mario, default.)
4. The world declares the next season by itself, without a separate scheduled job. It does this in production and staging, but not in development or tests, because their small calendars and season-crossing tests would grow seasons nobody declared. (Mario agreed to "everywhere"; narrowed when scoping, see the thread.)
5. The tick runs every 5 real minutes on staging and hourly in production. How often it runs is a setting of the deploy image (#128). (Mario, default.)
6. Real-time rules (report cap, rate limit, session expiry) stay on real time and are documented. The inactivity release stays at ten game weeks. (Mario, default.)
7. The agents learn about the speed from a written briefing. Nothing in the game tells them. (Mario, default.)

## Open questions

None.

## Deferred

- **An admin screen for the clock.** Command-line freeze, resume and status are enough for one operator.
- **Telling a human that a world is accelerated.** Only needed if humans ever play on an accelerated world, which no milestone plans.

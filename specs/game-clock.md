# Game clock

**Status:** proposed
**Domain(s):** `world/` (new), with obligations on `racing/` and `frontend/`
**One-liner:** The game world sits at a point in time that advances on its own, and everything that happens on a schedule happens because that clock reached it.

## Why this exists

Today a race happens because somebody runs a command. Nothing in the game has a
sense of *when* it is, so nothing can happen on its own. Without a clock there is
no season, no calendar, no wage day, no training week — every one of those
features would otherwise have to invent its own notion of time, and they would
each invent a slightly different one.

For the player, the clock is what turns a simulator into a world. Races arrive
because the date arrived. The game moves while they are not looking, and when
they come back, things have happened.

## Player experience

A player logs in and the game tells them when they are: a date and a time, in a
season. That display is always there — it is the answer to "is this thing live?"

They know a race is scheduled for Sunday at 14:00 because the calendar says so.
On Sunday they come back and the race is marked as racing now, because the world
has passed 14:00 and the race is being worked out. A little later it has a
result, and the race is done. Nothing the player did caused any of this; time
passed, and the world responded.

If the player goes away for a fortnight, they return to a world that moved on
without them. The races that were scheduled while they were gone have results.
The date is roughly where they would expect it to be, given how long they were
away.

A developer building the game has the same world, but can push it. They step the
clock to the next scheduled thing, or jump a whole day at a time, and watch a
season play out in an afternoon instead of over months.

## In scope

1. The world has a single current date and time, shared by every player. There is
   no per-player time.
2. The current date and time is visible to a player wherever they are in the game.
3. The world advances on its own, without anybody asking it to. In normal
   operation game time keeps pace with real time: one game week passes in one
   real week.
4. Anything scheduled to happen at a moment in game time happens when the world
   reaches that moment, and happens **exactly once** — never twice, even if the
   world is advanced twice or an advance is interrupted partway through.
5. A race whose start time has passed but whose outcome is not yet worked out is
   shown to the player as racing now. When the outcome is known, it is shown as
   finished with its result.
6. If the world has not advanced for a while — the host was asleep, a run was
   missed — the next advance catches up through the missed time in order, so that
   scheduled things still happen and still happen in the right sequence.
7. Catch-up is capped: a single advance will only work through so much missed
   time. Beyond that cap the world advances as far as the cap allows and picks up
   the rest next time.
8. A developer can step the world forward deliberately: to the next scheduled
   moment, or by a whole day at a time. Stepping a day processes everything
   scheduled within it.
9. Advancing the world when nothing is scheduled is a valid, complete,
   uneventful operation: the time moves and nothing else happens.
10. Each advance leaves a record of what it did — how far time moved and what
    happened as a result — so that "did the world tick?" is an answerable
    question.
11. Game code reads the game clock, never real-world time, when deciding whether
    something scheduled is due.

## Out of scope

- **A configurable clock speed** — the original issue asked for "controllable
  speed" and "simulate months in minutes". Cut. There is no speed setting and no
  multiplier; there is one operation that advances the world, invoked frequently
  by the game in production and deliberately by a developer in development. A
  season is fast-forwarded by stepping it, not by turning a dial. This also
  removes the parked worry about how a sped-up clock interacts with work that
  assumes a real week has passed — nothing is sped up.
- **Any player control over the clock.** No pausing, no skipping, no per-player
  time. The clock is world state.
- **An in-game admin screen for setting the date.** Later.
- **Deciding what is actually scheduled.** The clock provides the moment; the
  race calendar (#7) and the season (#5) provide the things that sit on it. This
  spec commits only that scheduled things fire.
- **Running many races at once across multiple workers.** Later — see Deferred.
- **Automated enforcement that game code never reads real-world time.** Later.

## Rules and edge cases

**The clock carries a time of day, not just a date.** A race starts at 14:00, not
"on the 12th". Wages, training and anything else scheduled likewise name a time.
This is a deliberate revision of an earlier, simpler design in which the world
only knew the date: it was chosen because races landing at their stated hour is
player-visible, and because "at what time does this happen?" is a question every
later timed feature will otherwise have to dodge.

**Advancing means advancing to the next scheduled moment.** The world moves
forward to the next thing that is due, deals with it, and carries on. Stepping a
day is a convenience built on top of this: it means "keep doing that until a day
has passed".

**In production the world is nudged once an hour.** Because a race scheduled for
14:00 should start near 14:00, the world must be given the chance to advance far
more often than once a day. Hourly is enough, and the overwhelmingly common
outcome is that nothing is due and the advance finishes immediately. This is a
change of deployment assumption from the once-a-day tick previously anticipated
in `racing/README.md`, and is noted there deliberately.

**Events are therefore scheduled on the hour.** An hourly nudge means the finest
schedulable moment is a whole hour — a race starts at 14:00, never at 14:20.
This is accepted, not worked around: nothing in the game needs minute precision,
and it keeps both the clock and the calendar simpler.

**Hosting must support an always-on app with an hourly scheduled task.** A
platform that sleeps idle applications cannot nudge the world while asleep, and
races would start late by however long the sleep lasted. This is a requirement on
the deployment decision, which is still open — see `Open questions`.

**Exactly once is the hard requirement.** Two advances running at the same time,
or one interrupted halfway, must not produce two races, two wage payments, or a
half-processed day that is then processed again from the start. Everything timed
that is built afterwards inherits this guarantee, which is the main reason the
clock is built first.

**Becoming due and being carried out are separate things.** When the world
reaches a race's start time, the race becomes due. Something then works it out
and records the result. In the first version these happen back to back, but the
handoff between them survives a restart: a race that became due and was not
finished is still due afterwards, and is still only ever run once. This is what
makes it possible to later have several things working out races at the same
time without touching the clock.

**Catching up favours honesty about the date over immediacy of results.**
After a long gap the world may reach its correct date while some races that
became due along the way are still being worked out. A player may briefly see
several races marked racing now. This is correct and preferable to a world whose
date is wrong.

**Catch-up is capped at 72 hours of game time per advance**, to stop a very long
outage turning into one enormous unattended run. On an always-on host an outage
is measured in hours, so three days is an order of magnitude more than expected
and the cap should never engage in normal operation — an ordinary restart or
deploy is absorbed invisibly by the next hourly advance. It engages only after
something unusual, which is precisely when a bounded run is wanted. After an
outage longer than 72 hours the world takes several advances to get current, and
is visibly behind real time until it does; that is preferred to a single run long
enough for the host to kill it partway. The cost of catching up is dominated by
races, not by clock steps, and a day holds few races.

The cap is configuration, not a fixed rule, so it can be raised temporarily to
recover from an exceptional outage without changing the game.

**A race takes real, measurable time to work out.** A 100 km race with 16 riders
takes roughly eight seconds. This is why simulating an entire season on demand
was rejected as a way of fast-forwarding, and why a developer's day-step is
expected to take a noticeable moment when that day holds races.

**Nothing is scheduled yet.** When this is built there is no calendar and no
season, so advancing the world moves the time and does nothing else. That is the
expected and correct first state.

## Decisions taken

- **Smallest unit of world time** — originally a game day; revised to a date
  *and* time of day, so races start at their stated hour and other timed features
  can name a time.
- **What the player sees** — the current date and time, always visible. No
  countdown to the next event; that belongs to the race calendar (#7).
- **Missed runs** — catch up through the missed time in order, rather than
  skipping it or letting the game drift behind real time.
- **Fast-forward** — a deliberate step (to the next scheduled moment, or a whole
  day), repeated. Not a speed multiplier, and not a bulk skip that discards
  races.
- **Catch-up cost** — capped per advance, rather than queueing races separately
  or accepting an unbounded run.
- **Who may move the clock** — nobody player-facing. Developer and admin only,
  from outside the game's UI.
- **Race status while being worked out** — shown as racing now, rather than
  hidden until finished or blocking the clock from advancing.
- **Clock discipline** — stated as a project rule in `world/README.md`, with no
  automated enforcement in this version.
- **How races are triggered** — scheduled work driven by the world, with no
  separate job-queue service. Carried over from `racing/README.md`, not
  re-decided here.
- **How often production advances the world** — once an hour, which fixes the
  finest schedulable moment at a whole hour. Accepted as a limitation.
- **How much missed time one advance absorbs** — 72 hours of game time, on the
  assumption of an always-on host where outages are measured in hours. Held as
  configuration so it can be raised for an exceptional recovery.

## Open questions

**Where the game is hosted.** Not a question this feature answers, but this
feature constrains it. Whatever platform is chosen must support an
always-on application with a reliable hourly scheduled task, and must allow that
task to run long enough to work out a day's races — currently around eight
seconds per race. Platforms that sleep idle applications are ruled out by this
feature: a sleeping world does not advance, and races start late by the length of
the sleep. Record this against the deployment decision.

## Deferred

- **Several races worked out at the same time** — the natural next step once a
  game day routinely holds more races than one advance should sit through. The
  frugal form is a queue held in the database the game already has, with workers
  claiming races; no broker service is needed. Waiting because there is currently
  no way for a day to hold more than one race, so there is nothing to run in
  parallel and no scheduling model to build the consumer against.
- **An in-game admin screen for setting the date** — waiting for a reason beyond
  convenience; the roadmap already judged a purpose-built admin tool premature.
- **Automated enforcement that game code reads the game clock** — waiting until
  there is enough timed behaviour for the rule to be worth policing. Today there
  is almost none.
- **Slimming the race log format** — not part of this feature, but it is what
  makes a long catch-up cheap, so it is worth doing before race volume grows.

# Game clock

**Status:** implemented
**Domain(s):** `world/` (new), with obligations on `racing/` and `frontend/`
**One-liner:** The game runs on real time — one game hour is one real hour, always — and a developer can swap in a clock they control by hand, entirely for testing, without production ever knowing the difference.

## Why this exists

Today a race happens because somebody runs a command. Nothing in the game has a
sense of *when* it is, so nothing can happen on its own. Without a clock there is
no season, no calendar, no wage day, no training week — every one of those
features would otherwise have to invent its own notion of time, and they would
each invent a slightly different one.

For the player, the clock is what turns a simulator into a world. Races arrive
because the date arrived. The game moves while they are not looking, and when
they come back, things have happened. Because the game clock is simply real
time, this is the most literal version of that promise: the world's time is
never anything other than the actual current time.

For a developer, testing a feature that fires next Tuesday should not mean
waiting until Tuesday. They need a clock they can freeze, jump forward, or set
to an arbitrary moment — used only at their own machine, never affecting how
the live game behaves.

## Player experience

A player logs in and the game tells them when they are: a date and a time, in a
season. That display is always there — it is the answer to "is this thing live?"
It is, quite simply, the real time, because that is what the game clock is.

They know a race is scheduled for Sunday at 14:00 because the calendar says so.
On Sunday they come back and the race is marked as racing now, because the
moment has arrived and the race is being worked out. A little later it has a
result, and the race is done. Nothing the player did caused any of this; time
passed, and the world responded — because the world's time is their time.

If the player goes away for a fortnight, they return to a world that moved on
without them. The races that were scheduled while they were gone have results,
worked out in the order they fell due once the game was next able to check.

A developer building the game experiences something different by design: their
clock can be told to sit still, or to jump straight to the next scheduled
event, or to jump forward by a chosen amount — so they can watch a season play
out in an afternoon instead of over real weeks. This is a tool for their own
testing. It has no effect on what any player, anywhere, ever sees.

## In scope

1. In production, the game's time **is** real time. There is no separate value
   that "advances" — asking the game what time it is always gets the true
   current moment.
2. The current date and time is visible to a player wherever they are in the
   game.
3. Anything scheduled to happen at a moment in time happens once that moment
   arrives, and happens **exactly once** — never twice, even if the game checks
   twice in quick succession, or a check is interrupted partway through.
4. A race whose start time has passed but whose outcome is not yet worked out is
   shown to the player as racing now. When the outcome is known, it is shown as
   finished with its result.
5. If the game has not checked for due races for a while — the host was asleep,
   a run was missed — the races that fell due in the meantime are worked out in
   order once it checks again, so nothing scheduled is silently skipped.
6. That catch-up is bounded: a single run will only work through so large a
   backlog of overdue races. Beyond that bound it processes as much as it will
   and picks up the rest next time.
7. A developer, and only a developer, can run the game against a clock they
   control instead of real time: frozen at a moment of their choosing, jumped
   straight to the next scheduled event, or moved forward by a chosen amount.
   This exists purely for manual testing and is never available to a player or
   present in the live game.
8. Each check for due work leaves a record of what it found and did, so that
   "did anything run, and did it work?" is an answerable question.
9. Game code asks the game clock what time it is, never real-world time
   directly — even though, in production, the answer is always the same thing.
   This is what makes the developer's controllable clock possible without
   touching any of the code that reads the time.

## Out of scope

- **A configurable clock speed for players, or any player control over time.**
  No pausing, no skipping, no per-player time, no speed dial. The only party who
  can move time away from "real" is a developer, and only outside the live game.
- **An in-game admin screen for controlling the developer clock.** A command
  line tool is enough for now. Later.
- **Deciding what is actually scheduled.** The clock answers "what time is it";
  the race calendar (#7) and the season (#5) decide what sits on the calendar.
  This spec commits only that scheduled things fire once their moment arrives.
- **Running many races at once across multiple workers.** Later — see Deferred.
- **Automated enforcement that game code never reads real-world time directly.**
  Later.

## Rules and edge cases

**The clock carries a time of day, not just a date.** A race starts at 14:00,
not "on the 12th". Wages, training and anything else scheduled likewise name a
time.

**In production the game checks for due work once an hour.** Because a race
scheduled for 14:00 should start near 14:00, the game needs to check often. An
hourly check is enough, and the overwhelmingly common outcome is that nothing
is due. This is a change of deployment assumption from the once-a-day tick
previously anticipated in `racing/README.md`, and is noted there deliberately.

**Events are therefore scheduled on the hour.** An hourly check means the
finest schedulable moment is a whole hour — a race starts at 14:00, never at
14:20. This is accepted, not worked around: nothing in the game needs minute
precision, and it keeps the calendar simpler.

**Hosting must support an always-on app with an hourly scheduled task.** A
platform that sleeps idle applications cannot check for due work while asleep,
and races would start late by however long the sleep lasted. This is a
requirement on the deployment decision, which is still open — see
`Open questions`.

**Exactly once is the hard requirement.** Two checks running at the same time,
or one interrupted halfway, must not produce two races, two wage payments, or
work redone from the start. Everything timed that is built afterwards inherits
this guarantee, which is the main reason the clock is built first.

**Becoming due and being carried out are separate things.** When a race's start
time arrives, the race becomes due. Something then works it out and records the
result. In the first version these happen back to back, but the handoff between
them survives a restart: a race that became due and was not finished is still
due afterwards, and is still only ever run once. This is what makes it possible
to later have several things working out races at the same time without any
extra coordination.

**Catching up is about unworked races, not a stale clock.** Because the game's
time is always the true current time, the date shown to a player is never
wrong or behind. What can lag is *processing*: races that fell due while the
game was not checking (an outage, a missed run) are still worked out, in the
order they fell due, the next time it checks. A player may briefly see several
races marked racing now at once after a long gap. That is correct and expected
— the date they see was never wrong, only the results were still catching up.

**The backlog a single run will work through is capped**, to stop a very long
outage turning into one enormous unattended run. On an always-on host an
outage is measured in hours, so a large backlog should never occur in normal
operation — an ordinary restart or deploy is absorbed invisibly by the next
hourly check. The cap engages only after something unusual, which is precisely
when a bounded run is wanted. After an exceptionally long outage the backlog
takes several runs to clear, and is visibly behind until it does; that is
preferred to a single run long enough for the host to kill it partway. The cap
is configuration, not a fixed rule, so it can be raised temporarily to recover
from an exceptional outage.

**A race takes real, measurable time to work out.** A 100 km race with 16
riders takes roughly eight seconds. This is why simulating an entire season on
demand was rejected as a way of fast-forwarding, and why a developer jumping
their clock forward across several scheduled races is expected to take a
noticeable moment.

**A developer's controllable clock is a development- and test-only concept.**
It does not exist as a possibility in the live game — not disabled, not
gated behind a permission, simply not a code path production runs. Nothing a
player does, and no configuration a live deployment carries, can put the game
on anything but real time.

**Nothing is scheduled yet.** When this is built there is no calendar and no
season, so most checks find nothing due. That is the expected and correct
first state.

## Decisions taken

- **What the game's time is, in production** — real time, exactly, always. Not
  a value that tracks real time closely; the actual current time, every time
  it is asked. Revised from an earlier design where a stored value advanced
  itself to approximate real time.
- **How a developer fast-forwards for testing** — by running the game against
  a different clock they control (frozen, jumped to the next event, or moved
  forward by a chosen amount), entirely separate from production, rather than
  a speed setting that could ever apply to the live game.
- **Smallest unit of world time** — a date *and* time of day, so races start at
  their stated hour and other timed features can name a time.
- **What the player sees** — the current date and time, always visible. No
  countdown to the next event; that belongs to the race calendar (#7).
- **Missed runs** — the unworked backlog is cleared in order the next time the
  game checks, rather than skipped. The date itself is never stale, because it
  is always real time; only the backlog of unworked races can lag.
- **Catch-up cost** — capped per run, rather than queueing races separately or
  accepting an unbounded run.
- **Who may run the game against a non-real clock** — nobody player-facing, and
  never in production. Developer and test-only, from outside the game's UI.
- **Race status while being worked out** — shown as racing now, rather than
  hidden until finished or blocking anything else from happening.
- **Clock discipline** — game code reads the clock abstraction, never real
  time directly, stated as a project rule in `world/README.md` with no
  automated enforcement in this version. This is what makes the developer
  clock possible without touching the code that reads time.
- **How races are triggered** — scheduled work checked on a schedule, with no
  separate job-queue service. Carried over from `racing/README.md`, not
  re-decided here.
- **How often production checks for due work** — once an hour, which fixes the
  finest schedulable moment at a whole hour. Accepted as a limitation.
- **How large a backlog one run absorbs** — capped, on the assumption of an
  always-on host where outages are measured in hours. Held as configuration so
  it can be raised for an exceptional recovery.

## Open questions

**Where the game is hosted.** Not a question this feature answers, but this
feature constrains it. Whatever platform is chosen must support an
always-on application with a reliable hourly scheduled task, and must allow that
task to run long enough to work out a day's races — currently around eight
seconds per race. Platforms that sleep idle applications are ruled out by this
feature: a sleeping game does not check for due work, and races start late by
the length of the sleep. Record this against the deployment decision.

## Deferred

- **Several races worked out at the same time** — the natural next step once a
  game day routinely holds more races than one check should sit through. The
  frugal form is a queue held in the database the game already has, with workers
  claiming races; no broker service is needed. Waiting because there is currently
  no way for a day to hold more than one race, so there is nothing to run in
  parallel and no scheduling model to build the consumer against.
- **An in-game admin screen for controlling the developer clock** — waiting for
  a reason beyond convenience; the roadmap already judged a purpose-built admin
  tool premature.
- **Automated enforcement that game code reads the game clock** — waiting until
  there is enough timed behaviour for the rule to be worth policing. Today there
  is almost none.
- **Slimming the race log format** — not part of this feature, but it is what
  makes a long catch-up cheap, so it is worth doing before race volume grows.

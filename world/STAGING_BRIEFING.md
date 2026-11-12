# Briefing for beta managers on the staging world

This text is meant to go into the LLM beta managers' prompt as it is (#132).
It describes the **accelerated staging world** (#129, `world/README.md`, *The
accelerated clock (#129)*). Keep it in step with the code: when a number below
changes, change it here too.

---

You are managing a team on a **test world that runs 24 times faster than real
time**. Apart from the speed, it is the real game, and the rules are the same
as they will be at launch. The speed creates some effects that are expected
and are **not bugs**, so please don't report them:

**How time passes**

- **One game day passes every real hour.** A game week takes about 7 real
  hours, and a twelve-week season takes about 3.5 real days. When one season
  ends, the next opens straight away.
- **Game time moves on between every two of your requests.** If you read the
  same thing twice a few seconds apart, it can show slightly different times.
- **The world is checked every 5 real minutes**, which is every 2 game hours.
  A race, a payday or an auction result can therefore appear up to about 2 game
  hours after its scheduled time. Production checks once an hour, so the
  real game lags too, by up to one game hour.
- **Occasionally the world is frozen** while something is being fixed. While it
  is frozen, game time stands still. Afterwards it carries on from where it
  stopped.
- **After the server has been down,** several game weeks can be processed at
  once: paydays, races and possibly a season end. Results for races you didn't
  see happen are expected.

**What that means for your plans**

- **Races:** a one-day race every game Sunday at 14:00, so about every 7 real
  hours. A stage race's stages are one game day apart, so one real hour apart.
  Pick your squad well ahead of the start.
- **Wages, sponsorship and merchandise** are paid every game week, so about
  every 7 real hours. A season's finances play out over about 3.5 real days.
- **Auctions last 3 game days, about 3 real hours.** A bid placed in an
  auction's last game hour (about 2.5 real minutes) pushes the deadline back by
  a game hour. The world is only checked every 5 real minutes, though, so a
  deadline that has been pushed back can resolve before you see it move.
  Don't rely on having the full extension to respond.
- **Inactivity:** a manager who doesn't visit for **10 game weeks loses their
  team.** On this world that is about **70 real hours, a little under 3 real
  days.** Visit at least once a real day.
- **Youth intake, training weeks, salary reviews and retirements** all follow
  game time too, so you will see several of each in a real week.

**What stays on real time**

These limits are measured in real time, not game time:

- **Reporting problems:** at most 20 reports per 24 real hours. That is
  roughly one game month, so save reports for things that look genuinely
  wrong.
- **The API rate limit:** 60 requests per real minute. A `429` response tells
  you how long to wait.
- **Timestamps that record when the server did something**, such as when a
  report was received, are in real time.

**Worth reporting**

Anything that is wrong at any speed: money that doesn't add up, a rider in two
places, a rule the documentation describes that the game doesn't follow, an
error response to a valid request, or a screen or endpoint that contradicts
another. If you are not sure whether something is a speed artefact, check it
against the list above before you report it.

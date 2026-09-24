# Broom wagon (time-cut DNF)

**Status:** proposed
**Domain(s):** `race_engine/`, `racing/`, `riders/`, `frontend/`
**One-liner:** Once the winner finishes, a rider who is too far behind to have a chance is pulled from the race instead of crawling to a meaningless finish hours later.

## Why this exists

The race engine has a known failure mode: a rider who cracks and falls off
the back of the group has no way back to equilibrium, and keeps getting
slower forever. In a small field this is masked — there's almost always
someone nearby to share the load with — but in a full-size field on a long
course, an isolated rider can spiral for tens of extra minutes of simulated
racing after everyone who matters has already finished. The result is a
race that takes nearly twice as long to simulate as it should, for a finish
time nobody would recognise as a real result.

This gives every race a floor under how bad a bad day can get. A rider who
has a rough race still finishes near the back, at a plausible time. A rider
who genuinely falls apart is pulled, the way a real broom wagon would pull
them, rather than being left to simulate a result that was never going to
mean anything.

## Player experience

A manager sends a squad into a long, hard stage. One rider — maybe tired
from a heavy week, maybe just having a bad day — gets dropped early and
never gets back on terms. The race plays out as normal for everyone else.
When the winner crosses the line, the result screen shows where every other
rider finished, in the order they crossed — except for that one rider, who
sits at the bottom marked DNF, the same way a rider who abandons already
appears today.

Nothing about the moment the rider was dropped is called out in the race —
the cut is only ever evaluated after there's a winner to measure against.
The manager doesn't experience a special "pulled from the race" event; they
just see a squad member who didn't finish, and can look at the standings to
see the rest of the field did.

That rider comes out of the race as tired as everyone who did finish it —
missing a race takes just as much out of a rider's legs as running it does
— but the race teaches them nothing, because they didn't actually complete
it. For a manager, the lesson is squad selection: sending a fatigued or
poorly-suited rider into a long, hard race is a real risk, and this is what
that risk now looks like when it goes wrong.

This applies the same way, at the same threshold, to every race — a
sprint stage and a mountain stage are cut on the same percentage of the
winner's time. It never applies before there is a winner, so a solo rider
just having a slow day is never pulled while still the only one racing.

## In scope

1. Every race, once its winner finishes, applies one time limit to every
   rider still racing: a fixed percentage of the winner's finishing time,
   the same percentage for every race.
2. A rider still on the road when that limit passes does not finish the
   race. They are recorded exactly as a rider who abandons is recorded
   today — no finishing time, no position among the finishers.
3. Among riders who don't finish, whoever was further along the course
   when the limit passed is listed ahead of the others — furthest
   travelled first — rather than in whatever order they happen to appear
   today.
4. A rider cut this way scores no points, earns no prize money, and is
   otherwise invisible to the season standings, in every way a rider who
   already fails to finish today is invisible to them.
5. A rider cut this way is charged the same racing fatigue as if they had
   finished the race, and does not get that week's rest recovery — sending
   a rider into a race and having them pulled costs exactly as much as
   racing normally does.
6. A rider cut this way earns no training credit for the race, unlike a
   rider who finishes it — they didn't actually complete the course, so
   there is nothing to have learned from finishing it.
7. The result screen shows a cut rider exactly the way it shows today's
   non-finishers: no position, no time, marked DNF. There is no separate
   label or explanation distinguishing "pulled for time" from any other
   reason a rider doesn't finish.

## Out of scope

- **The autobus** (dropped riders forming a second, slower group and
  surviving together) — Later. This spec only stops the engine from
  reporting a nonsense result; it does nothing to give a struggling rider
  a chance to hang on and finish. The two are meant to ship together or
  with the autobus following, per the engine README's own note, but the
  autobus is a materially bigger change (it touches the pack-cohesion
  machinery every course's realism balance already depends on) and isn't
  needed to fix the performance problem this ticket exists for.
- **A mid-race sweep** (pulling a rider for falling too far behind at any
  point in the race, not just after the winner finishes) — No. This
  spec's cut only ever applies once there's a winner to measure the limit
  against, which is simpler to reason about and can never end a rider's
  race before the race itself has a result.
- **A course-dependent time limit** (looser on mountain stages, tighter on
  flat ones, as real cycling does) — No, for now. One percentage for every
  race is simpler and was the explicit call; if it turns out to cut riders
  somewhere it shouldn't, that's a reason to revisit, not a reason to build
  it up front.
- **Reinstating riders if the winner is so far clear that the whole field
  would be cut** — No. This is judged an acceptable edge case rather than
  a rule worth building for; a limit generous enough that a normal race
  never loses anyone makes it very unlikely to come up in practice.
- **Any special display, label, or explanation** (e.g. "outside time
  limit") for a rider cut this way, as distinct from any other DNF — No.
  It shows exactly as today's non-finishers do.
- **Multi-day stage races** (what happens to a squad's remaining stages
  when a rider is cut mid-race) — belongs to stage races (#9), which
  doesn't exist yet. This spec is written for the one-day race that exists
  today.
- **Anything about why a rider fell apart** (an injury, a mechanical, a
  narrative reason) — belongs to future features (injuries, mechanicals).
  This spec doesn't change or explain the cause, only what happens once a
  rider has fallen far enough behind.

## Rules and edge cases

- The limit is evaluated once, off the winner's actual finishing time —
  not off a fixed expected time for the course, and not off the leader's
  position while the race is still in progress. Nobody can be cut before
  someone has won.
- The percentage is the same for every race regardless of length, terrain,
  or field size. It is deliberately generous: on a normal race, where the
  whole field finishes within a small margin of the winner, this changes
  nothing for anyone. It only removes riders from the genuinely broken
  tail — a rider who would otherwise take dramatically, implausibly longer
  than the winner.
- A team whose entire squad is cut this way scores and earns nothing from
  the race, the same as a team whose entire squad abandons today.
- A rider cut this way is treated as having raced, for fatigue purposes,
  even though they don't appear as a finisher. This is a deliberate split
  from today's rule, where "didn't finish" and "didn't race" are the same
  thing: cracking under the workload of a race is not the same as skipping
  it, and should not leave a rider rested afterwards.
- This does not interact with squad selection, race entry, or anything a
  manager does during the week. It is purely a rule about how a race's
  result is decided once the race itself has been run.

## Decisions taken

- **What happens to a badly-cracked rider:** they're cut and marked DNF
  once the limit passes, rather than crawling to a capped or continued
  finish, and rather than being folded into a group that survives (the
  autobus). Settled in the question round.
- **Basis for the limit:** a percentage of the winner's actual finishing
  time, the same percentage for every race regardless of course. Settled
  in the question round.
- **When the limit applies:** only after the winner finishes, not as a
  rolling mid-race check. Settled by scope discussion — a mid-race sweep
  was cut.
- **Fatigue cost for a cut rider:** full racing fatigue, no rest-week
  recovery, same as a finisher. Settled in the question round, to avoid
  a cracked rider coming out of the race fresher than one who finished it.
- **Training credit for a cut rider:** none. Settled in the question
  round, as the flip side of the fatigue decision above — they didn't
  actually complete the course.
- **Display:** plain DNF, identical to today's non-finisher rendering. No
  new label. Settled in the question round.
- **DNF ordering:** riders who don't finish are ordered furthest-travelled
  first, rather than arbitrarily. Settled during scope discussion, as
  something the original idea implied but didn't say.
- **The autobus, and a mid-race/course-dependent limit:** deferred or cut.
  Settled during scope discussion (see Out of scope).

## Open questions

- **The exact percentage.** No number is fixed by this spec. It should be
  calibrated against `race_engine/audit.py` so that every one of the
  bundled realism configs — including a larger-roster, longer-course case
  — loses nobody under a clean race, and reliably catches the death-spiral
  tail. That calibration is implementation work for the plan, not a
  product decision.

## Deferred

- **The autobus** — the mechanism-level fix, giving a dropped rider a
  chance to recover in a second group instead of being cut. Waits because
  it's a bigger, riskier change to code every course result already
  depends on, and isn't required to solve the performance problem.
- **Course-dependent time limits** — waits on evidence that one fixed
  percentage actually cuts a race it shouldn't.
- **Stage-race interaction** — waits on stage races (#9) existing at all.

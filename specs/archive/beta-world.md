# The beta world

**Status:** implemented
**Domain(s):** `schedule/`, `racing/`, `world/`, `teams/`, `staff/`
**Issue:** #139
**One-liner:** a real season calendar with named races and courses, and one command that builds a clean, playable world for staging or production.

## Why this exists

The only race content in the game is two example seasons. They were written to
exercise features (one has a sprint marker, one a stage race), not to be played:
the races are named after what they test, the dates are fixed in 2027, and no
one has checked whether they reward one kind of rider over another. Building a
world means running five commands in an order with a known trap in it, and the
demo account appears along the way.

Staging (#129, #136) and launch (#133) need a world prepared before the first
manager logs in, and staging needs to rebuild it between beta runs. Without
this, the first thing every beta manager notices is that the calendar is a
test fixture, and the first thing the operator gets wrong is the seeding
order.

## Player experience

A manager logs in for the first time and finds sixteen teams to choose from,
all free to claim. The calendar shows a season of named races with recognisable
character: a flat coastal sprint, a cobble-free spring classic over short steep
hills, a long endurance day, a summit finish, and two stage races, a three-day
tour midweek and a full week-long grand tour with its own flat, hilly and
mountain stages. The race names are Spanish and modelled on real
Spanish races: Clásica de Jaén, Vuelta a Cataluña, Subida a Urkiola.

Over the season, the manager finds that no single kind of rider is enough.
Sprinters win the flat days, climbers the mountain days, puncheurs the short
steep finishes, and rouleurs the long, flat-to-rolling races where strength
over distance decides it. A squad built from one speciality wins its handful
of races and loses the rest.

When the season ends, the next one opens straight away with the same calendar:
the same races, in the same weeks, the way the real classics come back every
year. A manager who lost the summit finish last year knows it is coming in the
same week this year and can build towards it.

The manager never sees the demo account, a test team or a race called
"Opening Sprint". In staging, the operator can wipe the world and rebuild it
between beta runs. The beta managers' accounts survive the wipe, and they claim
a fresh team in the new world.

## In scope

1. **One world calendar**, used for every season: named one-day races, plus a
   three-day and a seven-day stage race. The two example season files are left
   as they are, for development.
2. **Race density stays the same as the examples:** one one-day race a week
   (except the week a stage race fills), plus the two stage races, about 21
   race days a season.
3. **Every winning speciality has races it wins.** In a simulated season with a
   freshly generated field, climbers, sprinters and puncheurs each win at
   least two race days, rouleurs at least one (see *Decisions taken*), and
   no speciality wins more than about 40% of them. The check can be re-run by the operator or a developer, and its result
   is written down next to the calendar.
4. **Courses use course markers** (sprints with weights, climbs with
   categories, finish-line climbs) so the points competition has something to
   score on every kind of day.
5. **Race and stage names are Spanish proper nouns** modelled on real Spanish
   races. They are not translated (#137).
6. **The calendar can be started on any Monday.** The same file serves staging
   and production, each anchored to its own start. Every later season begins
   exactly where the previous one ends.
7. **One command builds a world:** 16 teams, all claimable, a trainer pool of
   24, and four seasons of the calendar back to back, in the order that makes
   the first season's sponsor offers appear when it opens.
8. **A second command adds the next season** after the last one declared, so a
   running world never runs out of calendar.
9. **A world can be wiped and rebuilt** with the same command, keeping user
   accounts. Wiping refuses to run anywhere it hasn't been explicitly allowed,
   and it is not allowed in production.
10. **Building a world never creates the demo account.** The world command
    refuses to build on top of a world that already exists unless asked to
    wipe it.
11. **The staging world starts immediately.** When the world runs on the
    accelerated clock, building it moves the clock to the first season's
    opening and opens the season, so sponsor offers are there for the first
    manager. A production world is built ahead of its start date, and teams
    are claimable during that lead time.

## Out of scope

- **Several rotating calendars, or generated variants.** Decided: one fixed
  calendar. Rotation can come later if beta managers find a repeated season
  stale.
- **New course features**: cobbles (#3), altitude (#108), time trials (#89).
  The calendar uses only what the engine supports today.
- **Domestique wins.** Domestiques are support riders and aren't expected to
  win races, the same as in real cycling.
- **Keeping the world going indefinitely.** Calling the add-a-season command
  when the calendar runs low belongs to the deployment (#129, #136).
- **Changing prize money or any economic number.** The calendar keeps the
  density that the economy was measured against.
- **Wiping accounts.** A wipe keeps every user. Removing agent accounts is the
  harness's job (#132).
- **A world-launch admin screen.** These are operator commands, like
  `load_season`.

## Rules and edge cases

- The start date must be a Monday at midnight UTC, as every season's already
  must. Anything else is refused with a message, not rounded.
- Adding a season to a world with no seasons is refused. The world command
  comes first.
- A season that has already started can never be changed. That rule is
  `load_season`'s and is unchanged.
- The wipe removes the whole game world: teams, riders, trainers, seasons and
  races, results and race logs, the ledger and fanbase, the market, and youth
  squads. Accounts stay. A manager whose team disappears is left with no team,
  the same as a newly registered player.
- Courses should stay inside what the engine was tuned for: no course much
  longer than the longest example, and no gradients steeper than the steepest
  bundled engine course.
- Stage-race stages count as race days for the speciality check. The general
  classification winner is reported too, but it isn't part of the 40% rule.

## Decisions taken

- One calendar or several? **One**, repeated every season, like the real
  calendar.
- How many race days? **The same density as the examples**: weekly one-day
  races plus a ~7-day and a 3-day stage race.
- What does "every speciality can win" mean? **Climbers, sprinters, rouleurs
  and puncheurs each win at least two race days, none more than ~40%.**
  Domestiques don't need wins.
- Rouleurs can't meet the two-win rule (found while tuning). The engine has
  no time trial, echelon or breakaway, so they won about one flat day in
  eight. **Their minimum is one a season**, with three rouleur-shaped days
  in the calendar, and their full share waits for time trials (#89, #90).
  This was the recommended option. The alternatives were tuning the engine
  inside this ticket, or shipping no rouleur days at all.
- World size? **16 teams in both worlds, all claimable, and a trainer pool of
  24.**
- Start date? **Set by the operator. The production world gets a week of lead
  time, and staging starts immediately.**
- How many seasons up front? **Four**, plus a command that appends the next.
- What does a wipe remove? **The whole game world, but not accounts.** It
  refuses in production. No demo account, ever.
- Names: first drafted in the team names' tone (invented European places).
  **Changed on review to Spanish names modelled on real Spanish races**
  (Clásica de Jaén, Vuelta a Cataluña), at Mario's request. The courses
  are unchanged, so the balance result still stands.

## Open questions

None.

## Deferred

- Rotating calendars, if a repeated season turns out to feel stale in beta.
- A course with a time trial, once #89 and #90 exist, which is also when
  the rouleur minimum goes back up to two.

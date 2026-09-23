# Season

**Status:** implemented
**Domain(s):** `schedule/` (new), with obligations on `world/`, `racing/` and `frontend/`
**One-liner:** Racing happens inside numbered seasons of twelve weeks, declared in advance by an admin, separated by an off-season in which nothing is raced.

## Why this exists

The game clock (#6) gives the world a time, but time on its own is featureless —
a date with nothing to measure it against. A season is the unit that makes the
passage of time mean something: it is what a result belongs to, what a table is
won at the end of, and what the player is a certain number of weeks into. Without
it, "week 3" is not a sentence the game can say.

It is also the thing that makes an ending possible. A game where races simply
keep happening has no shape. A season ends, there is a pause, and then a new one
starts from the beginning — which is what later gives promotion, contract renewal
and a champion somewhere to happen.

## Player experience

A player logs in and the game tells them where they are in the season: `Season 1
· Week 3`, at the top of the page, alongside the date the clock already shows.
That number climbs, one per week, from Week 1 to Week 12. It is the answer to
"how far through are we?" and it is visible everywhere.

Races happen inside those weeks. A race the player looks at belongs to a season —
not just to a date — so a result read months later still says which season it was
won in.

When Week 12 ends, racing stops. The header changes to `Season 1 · Off-season`
and stays there. There are no races, and the player can see plainly that this is
a deliberate pause rather than a game that has quietly broken. Then the next
season's start arrives, the header becomes `Season 2 · Week 1`, and the week
count begins again from one.

Seasons do not appear by themselves. Before a season can start, an admin declares
it: which season number it is and when it begins. That declaration is made from
outside the game — a file loaded by a command, not a screen in the UI — and once
the season has started it is fixed. If nobody declares the next one, the world
does not invent it: the clock keeps running, the game sits in the off-season, and
it says so until somebody configures what comes next.

## In scope

1. The world is either inside a season or in the off-season, and which of the two
   is visible to the player wherever they are in the game.
2. A season has a number, starting at 1 and increasing by one for each subsequent
   season.
3. A season is twelve weeks long. Its end follows from its start; it is not
   separately chosen.
4. Weeks within a season are numbered 1 to 12, and each is a real period the game
   can place things into and refer to — not merely a number computed for display.
5. A season begins on a week boundary, so that every week of every season starts
   on the same day of the week.
6. While a season is running, the player sees its number and the current week.
7. Between the end of one season and the start of the next, the player sees the
   off-season, labelled with the season that has just finished.
8. A season is declared in advance, from outside the game, by an admin: its
   number and its start. The declaration is a file, loaded by a command — not a
   screen in the game.
9. A season that has started cannot be reconfigured. Its number, its start and
   its end are fixed from that moment.
10. A season starts because the world's clock reached its start moment, and it
    ends because the clock reached its end. This happens exactly once for each,
    and is not triggered by anybody looking at the game.
11. If no next season has been declared when the current one ends, the world
    stays in the off-season indefinitely. The clock continues; no races are
    scheduled; the game does not invent a season.
12. A race belongs to exactly one season, and a race cannot be scheduled outside
    a season's twelve weeks.

## Out of scope

- **Anything that resolves during the off-season.** The original issue names
  promotion/relegation, contracts, sponsorships and salary reviews as the things
  the break exists for. None of them exist yet (#10–#13, #20–#27). This feature
  builds the window; it puts nothing in it. **Later.**
- **"Everything else hangs off a Season."** Taken literally this reaches into
  results, points and finances. Points and finances do not exist. The only
  ownership committed here is that a race belongs to a season. The rest arrives
  with the features that need it. **Later.**
- **Which races a season contains.** The season declaration is the file races
  will eventually be listed in, but listing them, placing them on days and
  deciding who enters is the race calendar. **Belongs to #7.**
- **Season history and past champions.** A list of completed seasons and who won
  them. There is no champion until there are standings. **Later — belongs after
  #12.**
- **An admin season-configuration screen.** A purpose-built season builder in the
  UI. The roadmap already judged this premature when it excluded #8; a file and a
  command do the same job for one admin and one season. **No.**
- **A countdown to the season's end.** The week number already conveys how far
  through the season the player is. **No.**
- **Seasons of varying length, or seasons mapped to real-world months.** Every
  season is twelve weeks; seasons do not correspond to a real calendar year.
  **No.**

## Rules and edge cases

**Seasons sit on top of the clock's ordinary time, and invent no calendar of
their own.** The world already has a date and time (#6). A season is a numbered
period of that time with a start and an end. There are no game-world month names
and no fictional year: a race is `Season 1 · Week 3`, Sunday at 14:00, and the
underlying instant is an ordinary one. This avoids maintaining a second notion of
time a week after building the first.

**The off-season has no fixed length.** It is simply the gap between one season's
end and the next declared season's start. A week is the intended convention, not
a rule the game enforces. This is what makes "nobody has configured the next
season" the same condition as "a very long break" rather than a separate failure
state needing its own handling.

**An unconfigured next season is a visible condition, not an error.** The game
does not stall, crash, extend the current season, or manufacture an empty one. It
sits in the off-season and says so. This is deliberate: it turns a forgotten
configuration step into something legible on the page rather than something
discovered from a log.

**Seasons start on a week boundary.** A season anchored to an arbitrary moment
would give weeks that begin mid-week at an odd hour, and "the Sunday race in week
3" would become ambiguous. Fixing the boundary means every week of every season
begins on the same day.

**A race cannot be scheduled outside a season.** There is no racing in the
off-season, and no race in week 13. The calendar (#7) will enforce this when it
places races; this feature states the rule it must respect.

**Starting and ending happen exactly once.** A season opening or closing is
driven by the world reaching a moment, and inherits the clock's exactly-once
guarantee (#6). The world may be advanced twice, or an advance interrupted, and a
season must not open twice or be closed twice.

**Nothing is scheduled yet when this is built.** There is no race calendar, so
the first season will run for twelve weeks with no races in it. That is the
expected first state, and mirrors the same honest emptiness the clock shipped
with.

**This feature depends on the clock being built, not merely specified.** A season
needs a world time to start and end against. It is the first thing in the game to
be scheduled on the clock, which makes it the first real exercise of that
guarantee.

**The season is shown at the top of the page, not in the sidebar.** The sidebar's
game-date display is the clock's (#6) and stays as that feature planned it. The
season does not replace it and does not claim that slot.

## Decisions taken

- **Abstract or real-world dates** — abstract, sitting on top of the clock's
  ordinary datetimes. No fictional calendar, no mapping to real months.
- **Season length** — twelve racing weeks. Shortest end of the range in the
  backlog, so a full cycle is visible in about three real months.
- **Break length** — not fixed. The off-season is whatever gap the next declared
  season's start leaves.
- **Weeks** — a real numbered unit the calendar can place races into, not a
  display-only derivation.
- **How seasons come into being** — declared in advance by an admin, from a file
  loaded by a command. Not automatic, and not a built UI tool.
- **Reconfiguration** — locked once a season starts.
- **No next season configured** — the world sits in the off-season and says so,
  indefinitely. It does not auto-generate or extend.
- **What the player sees** — season number and week at the top of the page;
  `Season N · Off-season` during the break.
- **The sidebar** — untouched. The clock's date display stands; the season does
  not go there.
- **Rollover ceremony** — nothing happens at a rollover in this version beyond
  the number changing. The break exists as the window later features will hook
  into.
- **Does #6 block this spec** — no. The clock's contract (a world datetime,
  hourly advance, scheduled things fire exactly once) is settled in
  `specs/game-clock.md`, and is the entire surface this feature consumes. #6
  blocks building #5, not specifying it.

## Open questions

None.

## Deferred

- **What resolves during the off-season** — promotion/relegation, contracts,
  sponsorships, salary reviews. Waiting because none of those features exist;
  each will hook into the window as it lands.
- **Races declared in the season file** — the file gains a list of races when the
  race calendar (#7) defines what a race entry is. Waiting so that #5 and #7 do
  not become one feature.
- **Season history and past champions** — waiting for standings (#12); there is
  no champion to record until then.
- **An admin season-configuration screen** — waiting for a reason beyond
  convenience. A file and a command serve one admin adequately.

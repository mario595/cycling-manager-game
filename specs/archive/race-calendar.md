# Race calendar

**Status:** implemented
**Domain(s):** `schedule/` (new), with obligations on `racing/`, `world/` and `frontend/`
**One-liner:** A season declares, in advance, exactly which one-day races happen on which day of which week — and every team races every one of them.

## Why this exists

The season (#5) gives the world twelve numbered weeks, but an empty season is
just a countdown — nothing actually happens in it. The calendar is what fills
those weeks with something to watch: races, on named days, that the clock (#6)
brings to life one at a time as it advances. Without it, the clock and the
season are both built and neither has anything to do.

It is also the thing a player plans around. "What's racing this week? What's
next?" only has an answer once a season's races are laid out and visible from
day one.

## Player experience

A player opens the season calendar and sees the whole season at a glance:
twelve weeks, each showing whether a race falls on it and, if so, its name and
day. Nothing is hidden — a race in week 11 is visible in week 1, the same way
the whole season's shape is visible from the start.

Weeks with no race are visibly weeks with no race, not gaps that look like
missing data.

As the season plays out, each race's entry on the calendar reflects where it
is: not yet happened, happening today, or finished. A player checking in
after a race's day knows, at a glance, whether to expect a result yet. Every
team races every one of these — a player never wonders whether their team is
"in" this week's race, because there is no such question to ask.

Before there is a season at all, or during the off-season, there is nothing to
show, and the player sees that plainly rather than an empty grid that looks
broken.

## In scope

1. A season names, in advance, a list of races: which week and which day of
   the week each falls on, and the course each is run on.
2. At most one race happens on any given day.
3. A course is authored as part of that same declaration — a fresh course can
   be defined for any race, not only ones that already exist as engine
   examples.
4. Every team in the game is entered in every race the season declares. There
   is no per-team calendar and no opt-in.
5. The full season's calendar — all twelve weeks, races already past and
   races still to come — is visible to a player from the moment the season
   starts, not revealed week by week.
6. A player can tell, for each race on the calendar, whether it has not yet
   happened, is happening today, or is finished.
7. Once the season has started, its calendar is fixed: no race is added,
   moved, or removed.
8. A race cannot be placed outside its season's twelve weeks.

## Out of scope

- **Stage races, short stage races, and any mix between them.** The original
  issue asked for a mix of one-day races and multi-day stage races. Cut
  entirely: a stage race is not yet a thing the game has (#9). This calendar
  places one-day races only. **Belongs to #9**, which will also teach the
  calendar to place a multi-day block once it exists.
- **Anything that determines entry.** The issue's own open question — does a
  team's Division decide which races it enters — is moot: there is no notion
  of a team entering or not entering. Every team is in every race,
  unconditionally. **Revisit only if this stops being true** — nothing in the
  current design (including Divisions, #10) is expected to change it, since
  the game currently has one shared calendar for everyone.
- **What happens when a manager hasn't prepared a squad or tactic for a
  race.** A real question, and one the team asking for this spec flagged
  explicitly — but it is squad selection's problem (#37), not the
  calendar's. This feature only guarantees the race happens; it says nothing
  about who's actually ready to start it. **Belongs to #37 or a ticket
  alongside it.**
- **A course catalogue, reusable across races or seasons.** Courses are
  authored inline, once, as part of a season's declaration. There is no
  library to browse, no reuse tracking, and no course outliving the season
  that defined it. **Later, if a real need for reuse shows up.**
- **A dedicated per-race screen.** The calendar shows a race's name, day and
  status; what a player sees when they open one race — course detail,
  who's racing, the result — is a separate screen the design mockup already
  anticipates and nothing yet builds. Split out as its own ticket,
  [#47](https://github.com/mario595/cycling-manager/issues/47), so it isn't
  silently assumed here. **This feature's calendar rows can point at it once
  it exists; today they point nowhere.**
- **A "next race" widget or countdown on the dashboard.** The clock's spec
  (#6) already deferred this to the calendar and it is not asked for now.
  **Later.**
- **An admin screen for building a season's calendar.** A file, loaded by a
  command, is how the season itself is declared (#5) and this feature adds
  no separate tool. **No** — matches the roadmap's existing call on #8.

## Rules and edge cases

**A race is declared alongside its season, in the same file.** The season
spec already anticipated the season's declaration file gaining a list of
races once the calendar existed; this is that list. A course's segments are
written inline, in the shape the simulation already reads, so a brand-new
course can be invented for any race without touching the six examples that
ship with the engine today.

**One race per day, full stop.** No two races share a day. This sidesteps
every question about a team facing a clash, because there is no day on which
a clash could happen. If Divisions ever mean different groups of teams race
in parallel on the same day, that is a deliberate change to this rule, not an
oversight in it.

**Every team races every declared race.** There are no Divisions or Groups
yet (#10), and even once they exist, nothing in this design assumes a race
belongs to a subset of teams. A season's calendar is one shared list.

**The calendar is whole from week one.** A player planning around week 9's
race does not wait eight weeks to learn it exists. This mirrors the season's
own commitment that the whole twelve-week shape is knowable in advance —the
calendar is the concrete version of that.

**A race's visible status follows the clock, not a separate signal.** Not
yet happened, happening today, and finished are the same three states the
clock's spec already established for a race in general (#6) — the calendar
is where a player watches them play out across a whole season instead of one
race at a time.

**A calendar is locked the moment its season starts.** This is inherited
directly from the season's own rule that a started season cannot be
reconfigured (#5): the races within it are part of that same fixed
declaration, not something layered on separately that could still move.

**No season, no calendar.** During the off-season, or before any season has
been declared, there is nothing to show. This is the same honest emptiness
the season spec committed to for its own display, extended to the calendar
underneath it.

## Decisions taken

- **Stage races vs. one-day only** — one-day races only for this feature.
  Stage races wait for #9 to exist as a thing at all.
- **Entry** — every team races every declared race. No Division-based entry,
  no manager opt-in. The Admin configures one season-wide list; it applies to
  every team regardless of Group or Division.
- **Same-day races** — never. At most one per day.
- **How races come into being** — authored in the season's own declaration
  file, alongside the season's number and start. Locked once the season
  starts, exactly like the season itself.
- **Courses** — authored inline per race, in the engine's existing segment
  format. Not drawn from a reusable catalogue, and not limited to the six
  bundled example courses — a season can define brand-new ones.
- **What the player sees** — the whole season's calendar, all twelve weeks,
  visible from the start; each race shows its day, name, and status.
- **The unprepared-squad question** — explicitly out of scope, referred to
  squad selection (#37).
- **A dedicated race screen** — explicitly out of scope, tracked separately
  as #47 so it isn't silently assumed as part of this feature.

## Open questions

None.

## Deferred

- **Stage races and multi-day placement** — waiting on #9.
- **Division- or Group-scoped calendars** — waiting on a reason to depart
  from "every team races everything"; nothing currently requires it.
- **Course catalogue and reuse across seasons** — waiting on a real need;
  today's inline authoring is adequate for a handful of seasons.
- **A dedicated per-race screen** — tracked as #47.
- **A "next race" dashboard widget** — waiting on the same call the clock's
  spec already made: not needed for this to be playable.
- **An admin UI for building the calendar** — a file and a command serve one
  admin adequately, per the roadmap's existing judgment on #8.

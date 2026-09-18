# Race detail view

**Status:** proposed
**Domain(s):** `frontend/`, `api/`, `competitions/`
**One-liner:** A dedicated screen for a single race — course and squad before it runs, full results after — reached by clicking a race anywhere it's shown.

## Why this exists

Right now a race exists on screen only as a row in the calendar (a name, a
date, a status) and, once finished, as a single misleading table on a
separate `/results` page that conflates two different things: who crossed
the line, and who scored. There's no place to actually look at a race — to
see whether the course suits your team before you pick a squad, or to
understand a finished race's result the way it actually works (points go to
one rider per team, not to whoever finished highest).

This gives every race its own screen: what it looks like before it runs, and
what happened once it has.

## Player experience

A manager looking at the calendar sees a race coming up in two weeks and
clicks it. They land on that race's own page: its name, date and distance,
and — because they can now see the shape of the course, not just its
length — an elevation profile telling them at a glance whether it's a flat
sprinter's day or a climbers' race. Below that, if it's their race to enter,
the same squad picker they already know: pick four riders, star one as
leader, save. The numbers next to each rider's attribute bars are visible
here too, the same as on the roster screen, so the decision isn't guesswork.

If the race belongs to another team, or the manager just wants to look
without picking anyone, the course and details are still there — just no
squad widget.

After the race happens, the same URL shows something different. Two tables,
because two different things happened: one shows every rider who started,
in the order they finished, with the winner's time and everyone else's gap
behind them, DNFs marked plainly. The other shows which teams scored and how
many points each got — every team that had a rider in the race, including
the ones that scored zero, so nobody looking at their own team wonders if
the table forgot them.

Wherever a race is mentioned elsewhere in the app — the calendar, the
dashboard's next-race card, a finished result — clicking it goes here. The
old standalone results page is gone; this replaces it.

## In scope

1. A single screen, one per race, reachable at the race's own URL.
2. An **upcoming** race shows: name, date, distance, and an elevation
   profile derived from the course.
3. If the viewing manager's team is entered in that upcoming race, the
   screen also shows the existing squad-selection tool (pick riders, star a
   leader, save) — unchanged in behaviour from what exists today.
4. In the squad picker, each rider's attribute bar is shown with its numeric
   value next to it, matching how the roster screen already displays the
   same attributes. Today the race screen shows only the bar.
5. A **finished** race shows two separate tables:
   - Rider results, ordered by finishing position: the winner's total race
     time; every other finisher's gap behind the winner; non-finishers
     marked as such, not given a time.
   - Team points: one row per team that had at least one rider in the race,
     each with the points that race earned them — including a zero for a
     team that started but didn't score.
6. A race that did not run (failed) shows a plain, unambiguous message
   instead of a blank or broken-looking page.
7. Every place a race is currently shown as a link or a row — the calendar,
   the dashboard's next-race card — links to this screen. A finished race's
   calendar row links here too (it does not today).
8. The standalone results page and its sidebar entry are removed. There is
   no other route that shows a finished race's result.

## Out of scope

- **A "racing now" / in-progress state.** Races are simulated as a single
  step of the world's weekly tick — there is no window during which one is
  partway run, so there is nothing to show and nothing to poll for. If a
  race is ever seen in a transitional status, the screen shows a minimal
  "this race is being simulated" message rather than attempting a live
  view. No.
- **Temperature, race tier, and per-race points value as displayed facts.**
  The idea (from the ticket) came from a mockup that invented facts the
  game doesn't track this way — temperature isn't modelled, "tier" isn't a
  concept that exists, and a race's points aren't a fixed number (they
  depend on finishing position). No.
- **Wind as a displayed fact.** Wind band is real and modelled, but showing
  it here is a flavour addition with nothing to act on until team tactics
  (#38) exist. Later.
- **Per-rider course suitability in the squad picker** (a score for how well
  a rider's attributes fit this specific course). Belongs to #45, which
  covers course-aware assessment properly. Later.
- **Other teams' entrants on an upcoming race.** Only the viewing manager's
  own squad selection is shown. Showing the field lets a manager counter-pick
  against a rival's known squad, which is a hidden-information decision this
  ticket doesn't make. Later, if ever — needs its own call.
- **Embedding or linking to the race replay** (`race_player/`, the tick-by-
  tick visualizer). It's a separate app with a different stack, reading logs
  from local files rather than from where the game stores them. Folding it
  in is real, separate work, and doesn't buy the manager anything more than
  the two result tables already do. Later — after the log-slimming work
  `racing/README.md` already calls for, since logs are large.
- **Keeping `/results` in any form, including a redirect.** It's replaced
  outright by the finished-race view of this screen. No.

## Rules and edge cases

- **A race the viewing manager's team is not entered in** still shows a full
  screen: course and profile if upcoming, both result tables if finished.
  Only the squad picker is specific to the manager's own team, and it's
  simply absent when they have no squad to pick.
- **A finished race where the manager's team didn't score** still shows that
  team's row in the points table, with zero points — this is the entire
  reason the points table lists every entered team rather than only
  scorers.
- **A finishing-time tie** (more than one rider recording the same time —
  ordinary for a bunch sprint) shows both riders with the same gap; a `+0:00`
  gap is correct and expected, not a display bug to hide.
- **A non-finisher** appears in the rider table in a clearly-marked
  "did not finish" state, not given a fabricated time or gap, and not
  omitted from the table.
- **A race that failed to run** shows a message saying so, distinctly from
  both the upcoming and finished views — not a blank page, not a 404-shaped
  error, and not a table with no rows.
- **Time display**: the winner's total elapsed time is shown in full
  (hours/minutes/seconds, dropping the hour component under an hour); every
  other finisher shows their gap behind the winner as `+m:ss`, extending to
  `+h:mm:ss` past an hour.

## Decisions taken

- Split out of #7 (race calendar) as its own ticket, per the original issue.
- No "racing now" state — races simulate atomically within one tick; there
  is no in-progress window to design for.
- Course shown as a full elevation profile (not just a flat/hilly/mountain
  label) — a label hides how climbing is distributed, which is what a
  manager actually needs to judge a course.
- `race_player/` stays a separate app; not folded into this screen. This
  ticket is about results, not playback.
- Finished-race points table lists every team that had a rider in the race,
  including zero-scorers, not only teams that scored.
- Upcoming-race view shows only the viewing manager's own squad, never other
  teams' entrants.
- `/results` is deleted outright, not kept as a redirect — its content now
  lives at a finished race's own URL.
- Numeric attribute values are added next to the squad picker's bars, to
  match `Roster.tsx`'s existing display — this was already flagged as a gap
  in the original ticket, not a new decision.

## Open questions

- None. The one real design gap the ticket left open — how the points table
  should handle a team that started but didn't score — is resolved above:
  it must be answerable, which the results API does not currently support
  and the implementation plan needs to address (either by extending what
  `RaceResultsView` returns, or by another means the plan settles).

## Deferred

- Wind band as a displayed fact — waits for team tactics (#38) to make it
  actionable.
- Per-rider course suitability in the squad picker — belongs to #45.
- Showing other teams' entrants pre-race — a hidden-information decision
  that needs its own discussion, not a side effect of this ticket.
- Embedding the race replay (`race_player/`) — waits for log slimming
  (`racing/README.md`) and is a larger, separate integration.

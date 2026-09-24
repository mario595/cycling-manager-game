# Rider detail view

**Status:** proposed
**Domain(s):** `riders/`, `racing/`, `competitions/`, `frontend/`, `api/`
**One-liner:** A page for a single rider — attribute shape, career arc, and race history — reachable from everywhere a rider's name already appears.

## Why this exists

The Roster is a table of twelve rows and a side panel of bars. There is no
place a manager goes to actually study one rider — to watch them over a
season and form an opinion, or to size up an opponent's rider before a race.

That gap matters more than a missing screen usually would.
`specs/archive/rider-attributes.md` deliberately hides potential, peak age,
decline rate and the rest, on the condition that every hidden trait is
**inferable** — a manager who watches a rider for long enough can form a
justified opinion about it from what they can see. A rider page is where
that watching happens. Without one, the hidden-trait design has nowhere to
pay off: the game asks the player to read a rider's trajectory and gives
them nowhere to see it laid out.

It also gives the game's growing race history somewhere to lead. Race
results, the free-agent pool and (eventually) the transfer market all name
riders; today none of those names go anywhere.

## Player experience

A manager is looking at the Roster and wants to know more about their
strongest climber than the side panel shows. They click through to a full
page for that rider: a five-axis shape — climb, sprint, flat, resistance,
positioning — drawn as a radar, so the rider's profile reads as a shape at a
glance rather than five numbers to compare one at a time. Underneath, the
same five attributes plotted as lines over time — flat at first for a rider
who just joined the roster, with real movement appearing as seasons pass.
Below that, every race the rider has started: the race, the date, who they
were riding for at the time, where they finished, and how many points it
was worth. A short strip of career numbers — races, wins, podiums, top tens,
DNFs, total points — gives the season-to-date shape without counting rows.

The same page opens from a race result: a manager watching the league table
notices an opponent's rider keeps finishing in the top five and clicks their
name to see who they are and where they came from. It opens the identical
page — a rival's rider shows everything the manager's own riders show,
including how tired they currently are, because that information already
determines who a manager fields and hiding it only for other teams would be
inconsistent with what a free-agent listing already shows. Hidden traits
never appear, for anyone's rider.

If the rider the manager clicked through to is no longer in the game — an
unclaimed free agent that sat too long and was removed from the pool — the
page says so plainly instead of erroring or showing a blank screen. The
manager was following a link from real history; the page should explain why
that particular rider can no longer be found, not pretend the link was
wrong.

## In scope

1. A page dedicated to a single rider, reachable by a stable link from that
   rider's name or ID.
2. The five engine attributes (climb, sprint, flat, resistance, positioning)
   shown as a five-axis radar, using the same 0–10 display scale as
   everywhere else in the game — rings at each whole step, a plotted point
   only on whole numbers, the value printed at each point. The chart implies
   no finer resolution than the roster already shows.
3. The same five attributes plotted as lines over time, one line per
   attribute, using the recorded attribute-history snapshots. A rider with
   only a starting snapshot shows a flat line and the point at which
   recording began, not an empty chart.
4. Identity: name, age, speciality, height, weight, current team (or "Free
   agent" if unattached), weekly salary, and market value.
5. Freshness, shown the same way it is shown on the Roster and squad
   selection.
6. Race history: every race the rider has a recorded result for, newest
   first, showing the race name, its date, which team the rider was riding
   for, their finishing position (or DNF), finish time, and points scored.
7. Career totals derived from that race history: races started, wins,
   podiums, top-ten finishes, DNFs, and total points scored.
8. A rider with no race history yet shows that plainly rather than an empty
   table.
9. A rider who can no longer be found (removed from the game) shows a page
   saying so, rather than a generic error or a blank screen.
10. Every rider's page shows the same information regardless of who is
    viewing it or which team the rider belongs to. Hidden traits are never
    shown, to anyone, under any circumstance.
11. A rider's name becomes a link to this page everywhere it currently
    appears as plain text: the Roster's side panel (as a "full profile"
    link, alongside the panel it already shows), race result rows, and the
    free-agent list.

## Out of scope

- **Team history as its own section.** Which team a rider rode for at each
  point is already carried by each race-history row (item 6) once a rider
  changes teams. A separate "teams previously ridden for" list would
  duplicate that. **No** — the race history already answers it.
- **Form as a separate trend indicator.** A season is around twelve races;
  the race history list already shows recent results in order. A dedicated
  sparkline would restate the same twelve rows in a harder-to-read form.
  **No.**
- **A team-mate or rival comparison view.** The question this would answer —
  who should start this race — belongs to squad selection, not a rider's own
  page. **No**, for this feature; may resurface once course suitability
  (#45) exists.
- **Prize money on this page.** Prize money belongs to the team, not the
  rider, and already appears on each race's own screen. This page shows
  points, which are earned individually; not money, which is not. **No.**
- **Season-by-season summary.** Only one season has been played; a
  season-grouped view is indistinguishable from the flat race list until a
  second season exists. **Later.**
- **Terrain breakdown** (results split by course profile). Meaningful once a
  rider has raced enough varied courses to show a pattern — not yet, with a
  twelve-week season. **Later.**
- **Contract and salary context beyond the current weekly salary.** Needs
  contracts (#26) to exist first. **Later.**
- **Scout reports or any estimate of a hidden trait**, however framed. The
  scout (#40) is a distinct, paid way to learn about a rider; this page
  stays limited to what any manager can see for free, or it undercuts the
  scout's reason to exist. **No.**
- **Squad-selection rows becoming links to this page.** Every row there is
  already a selection control with its own click target; turning the same
  row into a navigation link would conflict with it. **No.**

## Rules and edge cases

- **Attribute history plots the same 0–10 display values shown everywhere
  else**, per rider-attribute-history's recording rule — never a finer
  number. A rider who has not changed on the display scale yet shows a flat
  line, which is the correct, honest picture, not a bug in the chart.
- **A rider generated directly onto a team** (never having passed through
  the free-agent pool) still has at least one snapshot from the moment they
  were created, so their line graph is never empty.
- **The radar and the line graph must agree with each other and with every
  other attribute display in the game** — same five attributes, same 0–10
  scale, same rounding rule (floor, not round). A rider must never look
  different on this page than they look on the Roster.
- **A rider with zero races** (never selected into a squad) shows the
  career-totals strip as all zeros and the race history as an explicit empty
  state, not a missing section.
- **Viewing another team's rider, or a free agent, shows exactly the same
  page** as viewing your own — including freshness. No field is redacted
  based on who owns the rider or who is looking. Hidden traits are the only
  thing ever withheld, and that withholding does not vary either.
- **A rider who no longer exists** (currently: an expired, long-unclaimed
  free agent — see *Conflict with current game*, below) shows a dedicated
  "this rider is no longer part of the game" page rather than a 404 or a
  crash. This is a graceful-degradation requirement on the page itself, not
  a fix to why the rider is gone.
- **Every link to this page (Roster panel, race results, free-agent list)
  points at the same page for the same rider** — there is one rider page,
  not a variant per screen it's reached from.

## Conflict with the current game

**A rider who has raced can currently be deleted outright, taking their race
results with them.** `world.services._expire_free_agents` (shipped on
`master` as part of #29) hard-deletes any free agent unattached for 8+
in-season weeks and priced in the pool's bottom quintile — with no check for
whether that rider ever raced. Its cascade removes their `RaceResult` rows
too, so a past race's own result table can lose a row after the fact, and
anything computed from those results (standings, prize history) can shift
retroactively.

This is a real conflict for a feature whose whole premise is that a rider's
race history is durable enough to build a page around, and whose entry
points include clicking through from a race result that may itself have
already lost that rider's row. It is not this spec's to fix — it changes
shipped expiry behaviour and needs its own product decision (kept, retired,
re-signable?). **[#104](https://github.com/mario595/cycling-manager/issues/104)**
tracks it: riders with no race history may still be deleted on expiry;
riders who have raced should not be.

Until #104 ships, this spec treats "the rider is gone" as a real, current
possibility and requires the page (item 9, above) to handle it rather than
assuming it cannot happen.

## Decisions taken

- The existing Roster side panel stays as-is and gains a link to this page,
  rather than being replaced by it — the panel serves quick lineup checks,
  this page serves close study.
- Any manager can open any rider's page, including rivals' and free agents',
  with identical content — this both serves the "watch a rival" use case and
  keeps the page one thing rather than two.
- Freshness is shown regardless of whose rider it is. A rival can infer
  something about your next squad from it; accepted, not an oversight — the
  free-agent list already exposes freshness-equivalent information about
  unattached riders, and hiding it selectively would be inconsistent.
- The attribute line graph ships in the MVP rather than waiting for more
  history to accumulate — the data already exists (#95 records a baseline
  snapshot for every rider at creation), and a page that starts thin and
  fills in over real seasons is exactly the intended shape of this feature.
- The radar chart uses whole-number rings and points, matching the existing
  0–10 display scale precisely — it must not imply resolution the roster
  doesn't have.
- "Teams previously ridden for" is not a separate section; the race-history
  list already carries it per row once a rider changes teams, so a second
  list would be redundant.
- The rider-deletion conflict is split out as its own ticket (#104) rather
  than folded into this one's scope, since it is a change to already-shipped
  expiry behaviour that needs its own spec.

## Open questions

None outstanding — the "rider is gone" case is answered by item 9 and the
*Conflict* section above; #104 will resolve the underlying cause separately.

## Deferred

- **Season-by-season summary** — waits for a second season to exist; until
  then it is indistinguishable from the flat race list.
- **Terrain breakdown** — waits for enough races per rider across varied
  courses to show a real pattern.
- **Contract and salary context** — waits for #26 (contracts).
- **Scout reports** — waits for #40 (the scout), and belongs there rather
  than here so the scout keeps a reason to exist.

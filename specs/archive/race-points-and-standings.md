# Race points and season standings

**Status:** implemented
**Domain(s):** `competitions` (new), `racing`
**One-liner:** Every finished race scores each team by its best finisher, and those points accumulate into a season-long league table.

## Why this exists

Today, races happen and results exist, but nothing remembers them. A team can
win every race of a season and finish it exactly as anonymous as a team that
never started. There is no reason to care about one race over another, and no
answer to the most basic question a management game needs to answer: *who is
winning?*

This closes that loop. It gives every race result a consequence that outlives
the race itself, and gives the player a table to check every week, climb, and
worry about falling down.

## Player experience

A race finishes. On the result screen, next to the finishing order, the player
sees the points their team just earned — a number tied directly to where
their best rider crossed the line. If nobody finishes in the scoring
positions, they see that plainly: zero, this week.

Anywhere the player can see the league table, it shows every team in their
Group, ranked by total points accumulated since the season began, updating
race by race. A team on top by a wide margin looks dominant; two teams level
on points sit ordered by their countback (see *Rules and edge cases*) rather
than in some unexplained order. Early in a season the table is noisy and
compresses; by week 12 it has separated out into something that looks like a
league.

There is exactly one table per Group, and — for now — exactly one Group.

## In scope

1. Every race that finishes awards points to each team that entered a squad.
2. A team's points for a race are determined by its **best-placed finisher
   only** — the other three riders in the squad do not add anything further.
3. The points table, from 1st to 10th place:

   | Position | Points |
   |---|---|
   | 1st | 20 |
   | 2nd | 15 |
   | 3rd | 12 |
   | 4th | 10 |
   | 5th | 8 |
   | 6th | 6 |
   | 7th | 4 |
   | 8th | 3 |
   | 9th | 2 |
   | 10th | 1 |

   11th place and below score nothing.
4. Points are awarded per race, not per season — a season's total is the sum
   of everything a team has scored so far.
5. Unmanaged teams score under the same table as managed teams; a race does
   not know or care who is behind a squad.
6. The race result screen shows the points each team earned from that race,
   at the same time and place the finishing order is shown.
7. A single season-long standings table exists per Group, listing every team
   with its total points, visible to players throughout the season.
8. The table is visible and correct at any point in the season, not only at
   its end — a player can check it in week 3 and see exactly what has
   accumulated so far.
9. The table resets to zero at the start of each new season.
10. Two teams level on total points are ordered by countback: the team with
    more 1st-place finishes ranks higher; if still level, more 2nd-place
    finishes, and so on down the scoring positions. A team that has never
    scored ranks below one that has, regardless of countback.

## Out of scope

- **Points per stage and for a final general classification** — the original
  ticket's second half. Stage races do not exist as a feature yet: a race
  today is one course, one day, one result. Scoring a multi-day race with a
  cumulative classification is a property of *that* feature, not a rule
  bolted onto today's one-day races. Belongs with whichever future ticket
  builds stage races.
- **Division affecting the points award.** Only one Division exists, and a
  points table only has meaning among teams that race each other. This is
  not deferred so much as not yet a real question — it becomes one only if a
  future feature needs to compare teams across Divisions, which nothing
  today does.
- **Race tiers or bigger races awarding more points.** Every race on the
  calendar uses the same table. No race is yet authored as more prestigious
  than another, and inventing that distinction now means balancing something
  nobody can evaluate.
- **All four riders scoring, or a second/back-up scorer.** Only the best
  finisher counts. Support riders remain support — their contribution is to
  the race's outcome (leading out, pacing), not to a separate points ledger.
- **A rider points ranking.** This feature produces a team table only.
- **Prize money.** A separate reward on the same finishing positions,
  belongs to its own ticket (#19).
- **Promotion, relegation, or anything that reads the table to move teams
  between tiers.** The table exists to be looked at this season; what
  happens to it between seasons is #13.
- **Multiple Groups, or placing a team into one.** One Group, one table.
  Building the pyramid is #10/#11 and is explicitly not part of this slice.

## Rules and edge cases

- **A race must reach `FINISHED` to award points.** A cancelled or
  not-yet-simulated race awards nothing to anyone. If the clock runs late and
  a race finishes out of calendar order, points are still awarded the moment
  it finishes — the table does not wait for the whole week to complete.
- **A team with nobody classified scores zero.** If every rider in a team's
  squad abandons or otherwise fails to finish, that team simply does not
  appear in the scoring for that race. This is not an error state; it is a
  bad day.
- **A team that fielded no squad at all still races** (an auto-picked squad
  is guaranteed — see `racing/README.md`) and scores normally off whatever
  position that squad achieves.
- **Ties on the road** (two riders credited with the same finishing
  position) are resolved by giving both teams the points for the position
  they're tied at, and skipping the position(s) that would otherwise follow —
  e.g. two riders tied for 3rd both score 3rd-place points, and the next
  finisher scores as if they were 5th, not 4th.
- **Points awarded to a race are fixed at the moment the race finishes.**
  If the points table is retuned later in development, races already scored
  keep what they were awarded at the time — nothing is retroactively
  recalculated. This mirrors the existing rule that a race log is an
  authoritative historical record, not something regenerated under new
  rules (`racing/README.md`).
- **The table is derived from stored per-race points, not recomputed from
  raw race results on every read.** Whether that means a running total or a
  sum-on-read of stored per-race scores is an implementation choice for the
  plan; the product requirement is only that the number shown is always
  correct for races finished so far.
- **A newly claimed team (see `specs/archive/claiming-a-team.md`) keeps its
  points.** Claiming an unmanaged team is documented to preserve "table
  position, points and history" — this feature is what gives that promise
  something real to preserve. No new behaviour is needed here beyond making
  sure points already belong to the team, not to whoever was managing it.

## Decisions taken

- Merged with #12 (season standings) — scoring a race and accumulating those
  scores into a table are one feature end to end; a points rule with no
  table to show it in has no player-visible effect.
- Best-finisher-only scoring, not all four riders or top two. Simplest to
  read and makes the squad's leader choice matter.
- Points run 1st-10th, steep at the front, tapering to 1 apart near the
  bottom (20 down to 1). Most of a 16-team field scores nothing on a given
  day — normal for cycling, and creates real separation between a win and a
  podium.
- Stage races and GC points cut entirely — the underlying feature doesn't
  exist yet. See *Out of scope*.
- Every race is worth the same; no tier system. Deferred, not rejected —
  revisit if the calendar ever needs shape.
- Team points only, no rider ranking.
- Points shown immediately on the race result screen, not only inferable
  from a later change in the table.
- Division does not affect the award — not yet a real question with one
  Division.
- Unmanaged teams score like any other team; the table describes what
  happened on the road, not who was watching.
- One table, all teams, whole season, reset at season start — matches the
  roadmap's instruction to take only the "one Group exists" slice of #10.
- Ties broken by countback (most wins, then most runners-up, etc.), not
  head-to-head record or arbitrary order.

## Open questions

None. Everything raised by #15 and #12 was resolved above or explicitly
deferred to a named future ticket.

## Deferred

- **Stage race and GC points** — waits on stage races existing as a feature
  at all.
- **Race tiers scaling points** — waits on the calendar needing that shape;
  no evidence yet that it does.
- **Division-scaled points** — waits on more than one Division existing
  (#11).
- **Rider points ranking** — waits on something reading from it; currently
  would be display with no mechanic attached.
- **Prize money on the same positions** — separate ticket, #19.

# Sprint points

**Status:** implemented
**Domain(s):** `racing`, `competitions`, `frontend`
**One-liner:** The first riders across a sprint marker score points that count toward their team's league total.

## Why this exists

A course can already declare sprint markers (#70) and a race already records
who crosses each one first — but nothing is at stake. The crossing is
visible on the results screen and nowhere else; a manager who builds a squad
around a fast finisher gets nothing for it beyond the finish line itself.
This ticket makes a sprint marker mean something: the riders who contest it
well earn points, and those points count toward their team's season.

It is deliberately the sprint half only. #17 does the identical thing for
mountain markers, and the two are never pooled — a sprinter and a climber
can each have a good season doing entirely different things.

## Player experience

A manager opens an upcoming race's course profile and sees, same as today,
where the sprint markers sit. Now each one also shows what it's worth — a
small weight label, "minor", "standard", or "major" — so a course with two
modest early sprints and nothing else reads differently from one with a
single big intermediate sprint that's nearly as valuable as the stage.
Picking a fast finisher for the squad is now a decision with a visible
payoff before the race runs, not just a hope for the finish line.

When the race runs, the same contesting behaviour from #70 plays out — fast
riders kick for the line at each marker, at a cost to their legs later in
the race. Nothing changes about how a marker is contested.

After the race, the results screen shows what it showed before — the first
few riders across each sprint marker, in order — but now with points next
to each name, most for first, declining down the order. Below that, the
manager sees their team's race-day total broken in two: points from the
finish and points from sprints. The team's best-placed rider at each sprint
is the one who scored; a lead-out rider who also crossed well doesn't add a
second helping.

Over a season, those sprint points accumulate into the same league table
everyone already watches — a team whose GC challenger crashed out in week 4
can still be climbing the table on sprint points alone, because their
sprinter has been winning intermediate sprints all year.

## In scope

1. Each sprint marker on a course carries a named weight — how much it's
   worth relative to other sprints — set by whoever authors the course.
2. The first 5 riders across a sprint marker score points, most to the
   first, declining down the order, scaled by the marker's weight.
3. A team's sprint points for a marker come from its single best-placed
   rider at that marker — the same rule the finish already uses. A second
   teammate crossing well earns nothing extra for the team.
4. Sprint points earned are visible after the race, per marker, alongside
   the crossing order already shown there.
5. Sprint points add to the same season league total every other point
   source feeds — visible on the league table, and on the race's own
   results as a breakdown of finish points vs. sprint points.
6. A sprint marker's weight is visible on the course profile before the
   race runs.
7. A sprint marker placed at the finish line scores sprint points exactly
   like any other sprint marker — nothing distinguishes it in this
   ticket, so a race can pay both a finish result and a finish-line sprint
   if the course author places one there. Whether that double-counts is
   the author's call, the same way placing two sprints back-to-back is.

## Out of scope

- **A season-long sprinters' classification or leaderboard.** Crossings
  and their points stay visible per race; accumulating them into a
  standing of their own, with a jersey and a leader shown mid-race, is
  #18.
- **Mountain points.** #17's twin ticket, tracked and scored completely
  separately — never pooled with sprint points into one tally or one
  classification. Both do add to the same season league total, the same way
  finish points already do; "never pooled" is about the two staying
  distinguishable, not about mountain points being worth nothing to a team's
  season.
- **Rebalancing the existing race-points table.** Sprint points are additive
  on top of what a race already pays for finishing position. A full pass
  over every points source (finish, sprint, eventually mountain and
  classifications) belongs after #17 exists and the whole picture is
  known, not inside this ticket.
- **Prize money for a sprint.** #19's territory. Sprint markers pay points
  only.
- **A manager choosing who contests a sprint, or opting a rider out.**
  Unchanged from #70 — still automatic, attribute-driven, and still
  deferred to team tactics (#38).
- **Sprint points shown or used anywhere in the race player's playback.**
  A presentation question of its own, same as #70 left it.
- **A numeric weight authored per marker.** Weight is chosen from a small
  named set (see *Rules and edge cases*), not an arbitrary number written
  into the season file.

## Rules and edge cases

- **Weight is a small named set, not a free number.** Something like
  *minor*, *standard*, *major* — the exact labels and how many are a
  naming detail for the plan, not a product decision. A marker's weight
  is optional in the season file; an unweighted sprint marker defaults to
  the middle tier, so every existing season file keeps working unchanged.
- **A sprint's points are well below what winning the race itself pays.**
  Even the heaviest sprint tier stays a fraction of first place at the
  finish — a sprint is a bonus a squad can chase, not an alternate way to
  top the league.
- **Only the top 5 riders across a marker score.** A rider who crosses 6th
  or worse at that marker gets nothing for it, no matter how strong their
  finish later in the race.
- **A rider who never reaches a marker scores nothing there.** Unchanged
  from #70 — a DNF or dropped rider simply isn't in a marker's crossing
  record.
- **Points are frozen at the moment a race is scored**, the same rule
  finish points and prize money already follow. If the sprint points table
  is retuned later, races already scored keep what they were awarded at
  the time.
- **A course with no sprint markers is unaffected.** Nothing about this
  feature is mandatory; a race without sprint markers scores exactly as it
  does today.
- **A mountain marker never scores here.** This ticket reads sprint
  markers only; a mountain marker sits untouched until #17.

## Decisions taken

- Sprint points feed into the same league point total every other race
  outcome already contributes to, rather than staying a separate,
  display-only tally. (Question: what sprint points feed into.)
- The team's sprint score at a marker comes from its single best-placed
  rider there, mirroring the existing finish-points rule, rather than
  summing every scoring rider on the team. (Question: does a lead-out
  train double-score.)
- A finish-line sprint marker is not a special case — it scores like any
  other sprint marker, and whether placing one there double-pays a race
  winner is a course-authoring decision, not something this ticket
  guards against. (Question: does the stage winner also take sprint
  points.)
- A sprint marker's weight is chosen from a small named set the course
  author picks per marker, rather than left uniform or opened up to an
  arbitrary number. An unweighted marker defaults to the middle tier.
  (Question: does every sprint count the same.)
- The top 5 riders across each marker score, declining down the order.
  (Question: how many places.)
- Rebalancing the existing finish-points table is explicitly deferred
  until #17 exists, so the whole points picture is known before it's
  retuned once rather than twice. (Question: does adding a new points
  source require retuning the old one.)
- Sprint points staying separate from mountain points, and mountain
  points arriving as their own ticket rather than alongside this one, is
  accepted as a temporary imbalance favouring sprinters — #17 is next in
  the roadmap and closes the gap. (Question: sprinters vs. climbers
  fairness.)

## Open questions

None — the scope above is settled pending the user's sign-off on this spec.

## Deferred

- **A sprinters' season classification with a visible leader mid-race** —
  #18, which also owns the end-of-stage-race bonus that makes a
  classification worth chasing.
- **A full retune of the race-points table across every points source** —
  wait until #17 (mountain points) exists so the whole picture is known.
- **Sprint prize money** — #19.
- **Sprint markers or points shown in the race player** — waits on the
  same presentation work #70 deferred, blocked on #94.
- **Manager-directed sprint tactics** (choosing who contests, sitting a
  rider up) — #38, team tactics, unsized and deferred.

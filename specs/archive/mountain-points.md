# Mountain points

**Status:** implemented
**Domain(s):** `racing`, `competitions`, `frontend`
**One-liner:** The first riders across a mountain marker score points that count toward their team's league total.

## Why this exists

A course can already declare mountain markers (#70) and a race already
records who crosses each one first — but nothing is at stake. #16 made a
sprint marker mean something for a fast finisher; this ticket does the
identical thing for a mountain marker and a climber. Without it, a manager
who builds a squad around a strong climber gets nothing for it beyond
however the summit affects the finishing time.

It is deliberately the mountain half only, the twin of #16. The two are
tracked and scored completely separately, so a sprinter and a climber can
each have a good season doing entirely different things.

## Player experience

A manager opens an upcoming race's course profile and sees, same as today,
where the mountain markers sit. Now each one also shows its category — HC,
1st, 2nd or 3rd, the names any cycling fan already knows — so a course
description reads at a glance: a day with two Cat 3 rises is a different
proposition from one with a single HC summit. Picking a strong climber for
the squad is now a decision with a visible payoff before the race runs.

When the race runs, the same contesting behaviour from #70 plays out —
strong climbers push the pace to be first over each summit, at a cost to
their legs later in the race. Nothing changes about how a marker is
contested.

After the race, the results screen shows what it showed before — the first
few riders across each mountain marker, in order — but now with points next
to each name, most for first, declining down the order. The manager's team
breakdown for the race now has three parts: finish points, sprint points,
and mountain points. A team whose GC challenger crashed out in week 4 can
still be climbing the league table on mountain points alone, because their
climber has been first over every summit all season.

## In scope

1. Each mountain marker on a course carries a named category — HC, 1st,
   2nd or 3rd — set by whoever authors the course.
2. The first 5 riders across a mountain marker score points, most to the
   first, declining down the order, scaled by the marker's category.
3. A team's mountain points for a marker come from its single best-placed
   rider at that marker — the same rule sprint points and finish points
   already use. A second teammate crossing well earns nothing extra for
   the team.
4. Mountain points earned are visible after the race, per marker, alongside
   the crossing order already shown there.
5. Mountain points add to the same season league total every other point
   source feeds — visible on the league table, and on the race's own
   results as a three-way breakdown of finish, sprint and mountain points.
6. A mountain marker's category is visible on the course profile before
   the race runs.
7. A mountain marker placed at a summit finish scores mountain points
   exactly like any other mountain marker — nothing distinguishes it in
   this ticket. A course author who wants a summit finish to matter gives
   it the HC category; that is an authoring choice, not a rule this
   ticket enforces.

## Out of scope

- **A season-long climbers' classification or leaderboard.** Crossings and
  their points stay visible per race; accumulating them into a standing of
  their own, with a jersey and a leader shown mid-race, is #18.
- **Sprint points.** #16's twin ticket, tracked and scored completely
  separately. Both count toward the same team season total (that's not new
  — #16 already does), but the two tallies are never merged into one
  number or one classification.
- **Rebalancing the finish-points or sprint-points tables.** This ticket
  only adds a third points source on top of what already exists. A full
  retune across finish, sprint and mountain points — now that the whole
  picture is known — is its own ticket, done once rather than piecemeal.
- **Prize money for a mountain marker.** #19's territory. Mountain markers
  pay points only.
- **A manager choosing who contests a marker, or opting a rider out.**
  Unchanged from #70 — still automatic, attribute-driven, and still
  deferred to team tactics (#38).
- **Mountain points shown or used anywhere in the race player's
  playback.** A presentation question of its own, same as #70 and #16 left
  it.
- **Rewarding a climber harder for a bigger climb beyond the points
  themselves** — e.g. making a rider contest an HC summit any differently
  than a Cat 3 rise. Contesting behaviour is #70's territory and unchanged.
- **A numeric weight authored per marker.** Category is chosen from a
  fixed named set, not an arbitrary number written into the season file.
- **A Cat 4 tier.** Real cycling has one; a climb small enough to need it
  isn't worth marking in this game.
- **Double points for a summit finish.** Considered and rejected — see
  *Decisions taken*.

## Rules and edge cases

- **Category is a fixed named set: HC, 1st, 2nd, 3rd.** The exact internal
  representation is a naming detail for the plan, not a product decision.
  A marker's category is optional in the season file; an uncategorised
  mountain marker defaults to **2nd**, so every existing mountain marker in
  today's season file keeps working unchanged and lands in the middle of
  the scale rather than at either extreme.
- **A mountain marker's points are well below what winning the race itself
  pays**, the same ceiling #16 set for sprint points: even the heaviest
  category's win stays a fraction of first place at the finish.
- **Only the top 5 riders across a marker score.** A rider who crosses 6th
  or worse at that marker gets nothing for it, no matter how strong their
  finish later in the race.
- **A rider who never reaches a marker scores nothing there.** Unchanged
  from #70 — a DNF or dropped rider simply isn't in a marker's crossing
  record.
- **Points are frozen at the moment a race is scored**, the same rule
  finish points and sprint points already follow. If the mountain points
  table is retuned later, races already scored keep what they were
  awarded at the time.
- **A course with no mountain markers is unaffected.** Nothing about this
  feature is mandatory; a race without mountain markers scores exactly as
  it does today.
- **A sprint marker never scores here.** This ticket reads mountain
  markers only; a sprint marker is #16's territory, untouched by this one.
- **A summit finish is not a special case.** It scores mountain points
  like any other mountain marker, and separately scores finish points like
  any other finish — the same non-special-case rule #16 set for a
  finish-line sprint.

## Decisions taken

- Category names are HC, 1st, 2nd and 3rd — the real, familiar cycling
  ladder — rather than reusing sprint's minor/standard/major vocabulary or
  inventing a new one. (Question: how the weight is named.)
- Cat 4 is dropped; the game only marks climbs worth marking. (Question:
  full real-world ladder or a trimmed one.)
- An uncategorised mountain marker defaults to **2nd**, the middle of the
  four-tier scale, so today's season file keeps working unchanged.
  (Question: what an unset category means.)
- The top 5 riders across every mountain marker score, regardless of
  category — the same depth #16 uses for sprints, rather than a smaller
  category scoring fewer places. Considered scaling the number of scoring
  places with category (HC deeper than Cat 3) and rejected it for this
  ticket: it adds a second axis of tuning before the first one has ever
  run in production, and the category itself already scales how much each
  place is worth. Revisit once real results show it's needed. (Question:
  how many riders score.)
- Mountain points count toward the same season league total that finish
  points and sprint points already feed, exactly as #16 established for
  sprint points — not held back until #18's classification exists.
  (Question: does a climber's season depend on #18 shipping first.)
- A summit finish gets no special treatment — no double points, no
  distinct rule. The course author signals a summit finish by giving that
  marker the HC category; if they want it to matter more, they place it
  that way rather than the game inferring it from the marker's distance
  matching the course length. Considered doubling points for a marker at
  the finish (cycling's own convention) and rejected it: sprint points
  drew no such special case for a finish-line sprint, and adding one here
  would make the two tickets inconsistent for no player-visible reason
  beyond "mountains are special." (Question: summit finish handling.)
- The team's mountain score at a marker comes from its single best-placed
  rider there, mirroring sprint points and finish points. (Question: does
  a team with two strong climbers double-score.)
- Rebalancing the finish-points or sprint-points tables is out of scope
  here; a full retune across all three sources is deferred until both
  #16 and this ticket exist and the whole picture is known. (Question:
  does adding mountain points require retuning what's already there.)

## Open questions

None — the scope above is settled pending the user's sign-off on this spec.

## Deferred

- **A climbers' season classification with a visible leader mid-race** —
  #18, which also owns the end-of-stage-race bonus that makes a
  classification worth chasing.
- **A full retune of finish, sprint and mountain points together** — now
  that all three exist, worth doing once as its own ticket rather than
  guessed at inside this one.
- **Mountain prize money** — #19.
- **Mountain markers or points shown in the race player** — waits on the
  same presentation work #70 and #16 deferred, blocked on #94.
- **Manager-directed climbing tactics** (choosing who contests, sitting a
  rider up) — #38, team tactics, unsized and deferred.
- **Scoring places that grow with category** (HC pays deeper than Cat 3) —
  revisit once mountain points have run in production and the current flat
  top-5 is shown to need it.

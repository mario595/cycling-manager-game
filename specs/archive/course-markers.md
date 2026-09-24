# Course markers

**Status:** implemented
**Domain(s):** `race_engine`, `racing`, `schedule`, `frontend`
**One-liner:** A course can declare named points — intermediate sprints and mountain summits — and a race records the order riders cross each one.

## Why this exists

Today a course is only ever judged by its finish line. Nothing distinguishes
a flat sprinters' stage from a mountain stage except how a rider's overall
finishing time comes out, and nothing rewards the specialists who make a
race interesting mid-route — the sprinter who fights for the intermediate
points, the climber who leads the group over a summit. Markers give a course
author a way to say *"something happens here"*, and give a race something to
record beyond who won.

This is deliberately the foundation, not the feature. It does not award
points or build a jersey — see `specs/backlog-brain-dump.md`, #16 and #17 —
it only makes marker crossings a real, recorded, visible thing a course can
have and a race can produce. Those two tickets, and eventually the
classifications in #18, are unbuildable without it.

## Player experience

A manager building a team looks at an upcoming race and opens its course
profile, the same elevation chart they already use to judge whether the day
suits a sprinter or a climber. Now two more things sit on that chart: an
intermediate sprint partway along, and — if the route climbs — a mountain
marker at the summit. Each is named, the way a real race names its primes
("Sprint at Verbier", "Col du Chat").

When the race runs, the engine doesn't just carry the pack to each marker
and move on. A course's fast finishers contest the sprint the way they
contest the finish, kicking for the line at that point in the road; a
course's strongest climbers push the pace to be first over the summit. It
costs them something — a rider who goes for every marker on a hard day has
spent effort they don't get back — so contesting is a real, if currently
automatic, choice the engine makes on the rider's behalf.

After the race, the manager opens the results screen and finds, alongside
the finishing order and the team points, a small line for each marker: who
was first, second, third across it. It's a modest thing today — nothing
depends on it yet — but it's there, and it's real: the same rider who's
strong in the attributes that matter shows up at the top of it.

## In scope

1. A course can declare markers as part of its authored definition: each has
   a kind (**sprint** or **mountain**), a distance from the start, and a
   name.
2. A race records, for every marker on its course, the order in which
   riders cross it.
3. Riders whose relevant specialism is strong contest a marker: a fast
   rider kicks for a sprint marker, a strong climber pushes for a mountain
   marker's summit. This costs the rider effort, the same way any other
   in-race effort does.
4. A marker's record is available after the race: a course preview, before
   the race runs, shows where markers are and what kind they are; a
   finished race's results show the first few riders across each marker,
   in order.
5. A marker placed exactly at the finish line produces a crossing order
   consistent with the finish result — it is not a separate, possibly
   contradicting, race.

## Out of scope

- **Awarding points for a crossing.** #16 (sprint) and #17 (mountain).
- **A marker's weight, or a climb's category (HC/1st/2nd/3rd/4th).** These
  only mean something once something consumes them — #16/#17 own that
  decision, including whether sprint markers need a weight at all.
- **Accumulating crossings into a classification, or a classification
  jersey/leader.** #18.
- **Showing markers on the race player's playback.** The race player
  already renders an elevation profile; markers belong there eventually,
  but that's presentation work of its own, blocked on #94 (watching a
  finished race at all).
- **A manager choosing who contests a marker, or ordering a rider to sit
  up and not contest one.** That's a team-tactics decision (#38, currently
  unsized and deferred) — this ticket's contesting behaviour is automatic
  and attribute-driven, standing in for that future control.
- **Breakaways taking intermediate crossings away from the bunch.** The
  engine doesn't form early breakaways at all; every intermediate sprint
  under this feature is a bunch sprint. Also #38's territory.
- **Deriving mountain markers from gradient.** Settled on the issue already:
  climbs are placed by the course author, not inferred from terrain — see
  *Rules and edge cases*.

## Rules and edge cases

- **Contesting is attribute-gated, not universal.** A marker is contested by
  riders strong enough in the relevant specialism to plausibly fight for it
  — not by the whole field. This keeps a marker from becoming a second,
  unintended finish line that every rider sprints for, which would spend
  energy across the entire bunch and distort how the rest of the race,
  including the real finish, plays out.
- **Contesting costs effort.** A rider who contests a marker is genuinely
  more tired afterward than one who didn't. A course with several markers
  close together, or a marker placed near a climb the same rider wants to
  attack later, is a real tension the manager can see coming from the
  course profile — nobody gets marker glory for free.
- **A marker at the finish line is not a special case in the data — it's a
  marker whose distance happens to equal the course length — but its
  recorded order must agree with the actual finish order.** Two separate
  mechanisms silently disagreeing (a marker crossing recorded in one order,
  `RaceResult` finishing in another) is worse than not recording it.
- **Placement is entirely the author's call.** A mountain marker can sit
  anywhere on the course, including flat ground — nothing checks it against
  the terrain underneath. If an author places a summit marker on a flat
  segment, that is a course-design mistake visible on the profile, not
  something the loader rejects or warns about.
- **No limit on how many markers a course carries**, beyond what an author
  would reasonably write into one race — this spec doesn't invent a cap.
- **A marker at distance 0 or beyond the course length is invalid** — it
  isn't a point on the course.
- **Two markers may share a distance** (an intermediate sprint at the base
  of a climb whose summit is also marked nearby is ordinary race design);
  nothing requires markers to be spaced apart.
- **A course with no markers is unchanged** — nothing about this feature is
  mandatory for a race to run, matching how today's season file already
  allows a bare course.
- **DNF riders don't cross markers they never reached.** A rider who
  abandons before a marker simply isn't in its record; this needs no new
  rule beyond what `RaceResult` already does for finishers vs. non-finishers.

## Decisions taken

- Markers are placed by the course author, never derived from gradient —
  settled on the issue itself, before this spec.
- Riders contest markers automatically, gated by specialism, rather than
  either the whole field sprinting for every marker or nobody making any
  effort. (Question: contesting.)
- The finished race screen shows the first few riders across each marker,
  so the feature is visibly real before any points system depends on it.
  (Question: visibility.)
- Weight is cut from this ticket entirely and left to #16/#17, which will
  decide what a crossing is worth and whether sprint markers need a weight
  at all. (Question: weight.)
- A mountain marker can be placed anywhere; nothing validates it against
  the terrain underneath. (Question: placement.)
- Manager control over who contests a marker (or opting a rider out) is
  explicitly deferred to team tactics (#38), not part of this ticket's
  scope — automatic, attribute-driven contesting is the stand-in until that
  exists.

## Open questions

None — the scope above is settled pending the user's sign-off on this spec.

## Deferred

- **Marker weight / climb categories** — to #16/#17, where a weight gains
  an actual meaning (points).
- **Classifications and jerseys built from crossings** — #18.
- **Markers on the race player's playback** — its own presentation work,
  waiting on #94.
- **Manager-directed marker tactics** (fight for this one, sit up for that
  one) — #38, team tactics, currently unsized. This ticket's automatic
  attribute-gated contesting is what stands in until a manager can give the
  order directly.
- **Breakaways contesting markers independently of the bunch** — also #38;
  the engine currently forms no early breakaways at all.

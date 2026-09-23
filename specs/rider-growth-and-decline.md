# Rider growth and decline

**Status:** implemented
**Domain(s):** `riders/`, `world/`
**One-liner:** Every rider's attributes move a little each week along their
own hidden age curve — climbing fast while young, flattening through their
prime, falling away past their peak — and their visible age advances each
season.

## Why this exists

`specs/rider-attributes.md` gave every rider a hidden potential, peak age
and decline rate, and a visible age — but nothing reads them. A rider
generated today has the same five numbers forever, no matter how many
seasons pass. That makes keeping or replacing a rider a decision with no
weight behind it: a 34-year-old and a 19-year-old are just two sets of
numbers, not two different futures.

This feature is what makes a rider's age mean something the player has to
think about. A promising 19-year-old is worth patience because they're
still climbing toward a ceiling only the game knows. A 33-year-old at the
top of the roster is a countdown, not a fixture. Nothing about this is a
decision the player makes directly — it's a fact about the asset they
already chose to keep or sign, the same way weather is a fact about a race.

## Player experience

Nothing announces itself. There's no notification, no report, no page for
this. A manager who checks a rider's roster entry after training on
Monday-morning-me sees the same screen as always — five attribute numbers
on the familiar 0-10 scale, and an age.

Most weeks, nothing looks different: the underlying numbers moved, but not
by enough to cross a line on the 0-10 display. Over a season, though, a
young rider a manager kept an eye on shows up one week with climb a point
higher than it was — no explanation offered, the same as every other hidden
mechanic in the game. An older rider's sprint quietly loses a point a few
weeks later. Nobody announces which is which; the manager builds a sense of
it by watching the same riders season over season, the same way training
affinity or injury proneness are only ever inferred, never shown.

At the season's turn, every rider on every roster — and every rider not on
one — is a year older. That's the one moment where the ground shifts
underneath the curve: a rider who was still climbing might now be past
their peak, or a rider coasting through their prime might tip into decline,
all invisibly, ready to show up in how next season's weekly numbers move.

A young rider bought or kept through their early twenties visibly
rewards the patience: growth is fastest right when a manager is deciding
whether a promising but unproven rider is worth a squad slot. A rider
brought on past their prime is a known, honest trade — what they offer now
against how much less of it there'll be to offer next season.

## In scope

1. Every rider's five attributes (climb, sprint, flat, resistance,
   positioning) move by a small amount every week, whether or not the
   rider raced or trained that week.
2. The direction and size of that movement follows an age curve shaped
   like an inverted parabola: fast upward movement while young and well
   below potential, a flat middle where a rider at or near their prime
   moves negligibly, and a fall once a rider is past their peak.
3. The curve is individual to each rider, driven entirely by their
   existing hidden `potential`, `peak_age` and `decline_rate` — no new
   hidden trait is introduced.
4. Growth respects each attribute's place in the rider's existing shape: a
   Climber's climb grows toward a higher ceiling than their sprint does.
   Attributes don't converge toward a single flat number as a rider
   approaches potential.
5. A rider's visible age advances by one at each season boundary, for
   every rider in the game — rostered, free agent, or otherwise — not on
   an individual per-rider schedule.
6. This applies to every rider that exists, whether they are on a team's
   roster or an unattached free agent.
7. A full season of growth for a rider well below their potential is
   worth roughly one to two points on the 0-10 display scale (one to two
   tenths of the stored 1-100 range). A rider deep in decline loses about
   the same over a season.
8. This feature runs entirely independently of weekly training (#36):
   both apply to the same rider in the same week, neither scales or gates
   the other. A young rider who is both training well and climbing the
   age curve improves faster than either effect alone; an ageing rider's
   training can offset part of a week's decline but doesn't reverse the
   curve.
9. Attributes can rise or fall from this feature. Unlike training (#36,
   additive-only), this is the one place in the game an attribute goes
   down on its own.

## Out of scope

- **Any visible summary, report, or notification of what moved.** The
  player discovers growth and decline by noticing a number is different
  than it was. **Later** — when #36 (weekly training) builds its
  Training-page summary of what moved that week, that surface should also
  carry age-driven movement, so the two mechanisms that both move
  attributes weekly get one shared "what changed" list rather than two.
  Not built here.
- **Training slowing decline, or freshness resisting it.** Decided:
  independent and additive (see In scope #8). Training (#36) and
  freshness (#59) are their own levers; this feature doesn't reach into
  either.
- **Anything that reveals `peak_age`, `potential`, or `decline_rate`
  directly**, including a trajectory hint like "improving" or "declining"
  on a rider's page. **No.** These stay inferable only from watching
  numbers move over seasons, same as every other hidden trait.
- **A floor that stops decline, or any retirement behaviour.** A rider can
  decline indefinitely toward the bottom of the range and stay on the
  roster, unusable, forever. **Belongs to #42** (retirement) — this
  feature deliberately does not solve the exit.
- **Per-rider birth weeks or mid-season ageing.** Age is a season counter
  advanced once for everyone at the boundary, not a calendar date. **No**
  — no new field, no mid-season ageing moment.
- **Pricing or valuing the curve** — salary renegotiation (#26), market
  value (#31). **Later**, and this feature is their prerequisite, not part
  of them.

## Rules and edge cases

- **Riders generated already past their peak exist today**, because
  `generate_rider` rolls age and peak age independently. The very first
  week this feature runs, a real slice of the world's existing roster
  starts declining immediately — not a bug, a consequence of a population
  that already contains veterans.
- **The flat middle is not a separate rule to tune.** It falls out of the
  same curve that produces fast early growth and later decline — a rider
  near their peak age, by construction, is close to whichever of headroom
  or shortfall the curve measures, so movement there is naturally small.
  Nothing separate needs to define "prime."
- **A rider already at or above their potential on some attribute doesn't
  fall just for being there before their peak age.** Growth toward
  potential and age-driven decline are two ends of the same curve, not two
  competing forces that can both apply to a young rider — a rider below
  peak age moves toward potential (or not at all, if they're already
  there); only a rider past peak age is on the falling half.
- **A rider's climb and sprint don't grow at the same rate even under the
  same curve shape**, because each attribute has its own room left before
  its own place in the potential shape (see In scope #4) — a Climber's
  climb has more headroom than their sprint, and grows faster in absolute
  terms as a result.
- **Free agents are not exempt.** A rider with no team ages and grows or
  declines exactly like a rostered one. There is no way to "pause" a
  rider's curve by leaving them unsigned.
- **This needs a weekly hook the game doesn't have yet.** `world/`'s tick
  currently fires on season transitions and due races; there is no
  "a week rolled over" moment for anything to attach to. Building that
  hook is this feature's job (or shared with #36, whichever lands first) —
  not a pre-existing mechanism being reused.

## Decisions taken

- Growth and decline run weekly, not only at the season boundary. *(Cadence)*
- The player has no lever over this feature at all — it is not
  influenced by training or freshness, and offers none of its own.
  *(Agency)*
- The player sees only the changed numbers, with no dedicated report or
  notification in this ticket. *(Visibility)*
- Decline has no floor here and no retirement behaviour; a rider can
  decline indefinitely until #42 exists. *(Floor)*
- Age advances once per season, for every rider at once, not on an
  individual birth-week schedule. *(Ageing)*
- The curve shape is an inverted parabola: fast growth while young and
  below potential, a flat prime, decline past peak age — driven entirely
  by the existing hidden `potential`, `peak_age`, `decline_rate` traits,
  no new hidden trait. *(Curve shape)*
- A season of growth for a young rider well below potential is worth
  roughly one to two points on the 0-10 scale; decline is comparable.
  *(Magnitude)*
- This feature is fully independent of and additive with #36 (weekly
  training) — neither gates or scales the other, and #58 does not need
  #36 to ship. *(Relationship to #36)*
- Growth respects each attribute's own headroom to potential, following
  the rider's existing speciality-driven shape, rather than pulling every
  attribute toward one flat ceiling. *(Shape preservation)*

## Open questions

None outstanding.

## Deferred

- **A visible "what moved" summary** — fold into #36's Training-page
  summary once that ships, covering both training and age-driven
  movement in one list, rather than building a second surface here.
- **Training or freshness interacting with the curve** — revisit only if
  #36 or #59, once live, turn up a reason independence doesn't hold up in
  play.
- **Retirement** — #42's job; this feature only creates the pressure for
  it to eventually solve.

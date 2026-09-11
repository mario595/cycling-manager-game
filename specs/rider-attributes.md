# Rider attributes

**Status:** proposed
**Domain(s):** `riders/`, with a defined boundary against `race_engine/`
**One-liner:** Every rider is described by a handful of visible racing ratings and a
set of hidden traits that decide how they grow, tire and break down — so two
riders who look identical on the roster page are not the same asset.

## Why this exists

Riders are currently five numbers between 1 and 100, and nothing else. That is
enough to simulate a race and not nearly enough to manage a team: every rider of
a given quality is interchangeable, nobody gets better or worse, and there is no
reason to prefer a 22-year-old to a 33-year-old beyond the number on the page. A
manager game is mostly the decisions taken *between* races, and right now there
is nothing to decide.

This gives riders a life. They arrive with a speciality they keep forever, they
improve toward a ceiling only they know about, they decline once they are past
it, they tire across a season and recover at their own rate, and some of them
are quietly more fragile than others. None of that changes how a race is
simulated — it changes what the player is choosing between when they pick who
rides.

## Player experience

Rob opens the roster. Every rider shows five ratings on a 0–10 scale — climbing,
sprinting, flat, resistance, positioning — and a speciality: Sprinter, Climber,
Rouleur, Puncheur, Domestique. Mira Kestrel is a Climber, 9 for climbing, 4 for
sprinting, and reading her line takes a second because the numbers are coarse
enough to take in at a glance rather than compare digit by digit.

Two of his riders show identical ratings. They are not identical. One is 22 and
one is 31, and Rob knows — because the game has told him this is how riders work,
not because it has shown him a number — that the young one is probably still
improving and the older one probably is not. How much either is true, he finds
out by keeping them.

Over a season he watches Luca Duarte, 22, climbing 7. Some weeks nothing
changes. Then one morning the roster says 8, and it registers as an event
because it is the first movement in months. Rob does not know whether Luca stops
at 8 or reaches 9 — he has a hunch based on how quickly that first jump came,
and he is weighing a contract on it. Meanwhile Ciro Battaglia, 34, drops from 7
to 6 and that is Rob's answer about whether to renew him.

Alongside the ratings each rider shows freshness. Race a rider three weekends
running and it falls; rest them and it comes back, faster for some riders than
others. It is the number Rob actually consults when picking a lineup, and it is
the reason his best climber sometimes stays home.

What Rob never sees: how good a rider can eventually become, when they will peak,
how fast they will decline, how injury-prone they are, how quickly they recover.
He infers all of it from watching riders over seasons — which is the point. A
scout's report and a hunch are supposed to be worth something.

## In scope

1. Every rider has five racing ratings — climbing, sprinting, flat, resistance,
   positioning — displayed to the player on a **0–10 integer scale**.
2. The game stores those ratings at a finer resolution than it displays. A
   rider can improve without the displayed rating moving, and then move a whole
   point at once.
3. Every rider has a **speciality** — Sprinter, Climber, Rouleur, Puncheur,
   Domestique — assigned when the rider is created and **never changing for the
   rest of their life**.
4. Every rider has a visible physical build (height and weight) that never
   changes and is consistent with their speciality: sprinters are heavier and
   bigger, climbers lighter and slighter.
5. Every rider has a visible age, which increases as seasons pass.
6. Riders below their peak age **improve** over time; riders past it **decline**.
   The player observes this happening on the roster.
7. Every rider has a **freshness** value, visible, which falls when they race and
   recovers when they rest.
8. Riders recover freshness at different rates, and the rate is not shown.
9. Each rider has a hidden **potential** — the ceiling their ratings grow toward.
10. Each rider has a hidden **peak age** and a hidden **decline rate**, so two
    riders of the same age are not on the same curve.
11. Each rider has a hidden **injury proneness**, describing how susceptible they
    are relative to other riders.
12. Each rider has a hidden **training affinity**: they improve faster in the
    ratings their speciality is built on than in the others.
13. Every hidden trait must be **inferable** — a player who watches a rider over
    enough time can form a justified opinion about it from observed behaviour.
14. None of the above changes how the race engine simulates a race. The engine
    reads the same five attributes it reads today.

## Out of scope

- **An overall rating (OVR).** Cut. It collapses five deliberately incomparable
  ratings onto one axis and lets the player skip judging a rider entirely, which
  is the judgement this feature exists to create.
- **Rider market value.** Not an attribute — an output of a market. Belongs to
  `transfers/`.
- **Morale.** No. It needs grievances to be about — squad selection disputes,
  contract rows, a results history — and none of those exist.
- **A second, medium-term "form" number** distinct from freshness. No. Planning a
  peak requires a race calendar to peak toward; without `schedule/` there is
  nothing to plan against, and two freshness numbers would be one thing shown
  twice.
- **Scouting accuracy and attribute fog** (ratings shown as ranges that sharpen).
  No. Imperfect information needs a transfer market to matter in.
- **The injury mechanic itself** — how injuries occur, how long they last, how
  they are treated. This spec defines the *attribute*; the system is its own
  feature.
- **Descending as a rating separate from sprinting.** Later — see Deferred.
- **Time-trialling, cobbles/bike handling, weather tolerance.** Wanted, but
  blocked on things the engine does not model. Tracked as
  [#2](https://github.com/mario595/cycling-manager/issues/2),
  [#3](https://github.com/mario595/cycling-manager/issues/3) and
  [#4](https://github.com/mario595/cycling-manager/issues/4).

## Rules and edge cases

**Display scale.** The player's world is 0–10 whole numbers; the game's is finer.
Two riders showing the same rating can differ, and the player has no way to tell
them apart from the roster page. This is deliberate — it is what makes watching a
rider over time worth more than reading their line — and it means the roster
cannot offer a meaningful sort on a single rating.

**Speciality never changes.** A 34-year-old Sprinter whose sprinting has declined
to 4 is still a Sprinter. The label says what the rider *is* — a consequence of
their build — not what they are currently good at. A rider whose ratings no
longer flatter their speciality is a rider in decline, and reading that from the
roster is the intended experience, not a bug to be fixed by re-labelling them.

**Improvement is not guaranteed or uniform.** A young rider with low potential
improves very little. A rider improves faster in the ratings their speciality
favours, so a Climber's growth mostly lands on climbing. Growth is gradual enough
that most weeks nothing visibly changes.

**Decline is not a cliff.** Past their peak, riders lose ground steadily. Some
riders decline slowly enough to stay useful into their mid-thirties; others fall
away quickly. The player learns which kind they bought by owning them.

**Freshness has floors and ceilings.** It cannot exceed full, and a rider who is
rested for long enough returns to full — resting is always eventually sufficient.
A rider raced continuously reaches a bad state and stays there rather than
falling forever.

**Every hidden trait must be inferable.** A hidden value the player can never
form a justified opinion about is not depth, it is an unfair dice roll. If a
proposed hidden attribute has no observable consequence a player could read over
a season, it should not exist.

**The engine boundary.** Attributes divide into two kinds, and the distinction
governs what is cheap and what is expensive:

- **In-race attributes** are read by the simulation. There are five, and adding a
  sixth invalidates the verified realism results for all six bundled courses and
  requires re-deriving that balance. Add sparingly and never casually.
- **Between-race attributes** — age, potential, peak, decline, injury proneness,
  recovery, training affinity — are invisible to the simulation entirely. They
  cost nothing in engine terms.

Everything this MVP adds is the second kind. That is why it can be substantial
without touching the engine.

**Existing riders.** Riders that already exist have five ratings and nothing
else. They need a speciality, build, age and hidden traits assigned in a way
consistent with the ratings they already have — a rider with 94 climbing and 38
sprinting must come out a Climber.

## Decisions taken

- **Do new engine inputs get added?** Not in this MVP. New in-race attributes are
  on the table in principle but each one costs a re-derivation of the audited
  course balance, so they are judged individually rather than added by default.
- **How much of a rider's quality is visible?** The five ratings are visible but
  coarsened to 0–10; the true finer value is never shown. Growth therefore
  arrives as an occasional visible jump.
- **Can two riders look identical but differ?** Yes, accepted deliberately.
- **Form and condition as two numbers?** No — one freshness number. The
  medium-term half has no race calendar to plan against yet.
- **Is speciality derived from the ratings or innate?** Innate: assigned at
  creation from the rider's physical build and kept for life, as in real cycling.
  It also biases training gains, which gives it a mechanical job rather than
  making it a label.
- **What does age do?** Growth toward a hidden potential before a hidden peak,
  decline after it. Both the peak and the rate vary per rider and are hidden.
- **How far do injuries go here?** The attribute is defined; the mechanic is a
  separate feature.
- **Is there an overall rating?** No. Cut.
- **Are the design mockups binding on scope?** No. They are a visual guide only;
  where this spec and the mockup disagree, the spec wins.

## Open questions

- **Where does the player learn how any of this works?** The feature depends on
  the player understanding that young riders improve and old ones decline, since
  the numbers driving it are hidden. Whether that arrives as onboarding text,
  scout reports or is simply left to be discovered is unresolved — resolved by
  whoever specs the rider detail screen.
- **Do AI-managed teams' riders follow the same rules?** Presumably yes, but the
  answer affects world balance over many seasons and belongs with `world/`.

## Deferred

- **Descending split from sprinting, with crash risk for poor handlers.**
  Sprinting currently doubles as descending speed, so a descending specialist
  cannot exist. Wanted — including the possibility that unskilled riders crash on
  descents — but it is an in-race attribute, so it needs an engine change and a
  full re-derivation of the six-course realism balance. Waiting for that to be
  worth doing on its own terms.

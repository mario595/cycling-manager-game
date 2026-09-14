# Rider attributes

**Status:** proposed
**Domain(s):** `riders/`, with a defined boundary against `race_engine/`
**One-liner:** Every rider is a person rather than five numbers — a speciality
they keep for life, a build, an age, and a set of hidden traits that will decide
how they grow and break down — so two riders who look identical on the roster
page are not the same asset.

## Why this exists

Riders are currently five numbers between 1 and 100, and nothing else. That is
enough to simulate a race and not nearly enough to manage a team: every rider of
a given quality is interchangeable, and there is no reason to prefer a
22-year-old to a 33-year-old beyond the number on the page. A manager game is
mostly the decisions taken *between* races, and right now there is nothing to
decide between.

This is the first half of fixing that: riders acquire the description they have
been missing. They arrive with a speciality that reflects their build and that
they keep forever, they have an age the player can weigh, and they carry hidden
traits that will govern their future. Nothing about a rider changes over time
yet — that is a separate feature, deliberately. What this delivers is a roster
worth reading, and the foundation two blocked features are waiting on: the
starting squad a new player is handed
([#46](https://github.com/mario595/cycling-manager/issues/46)) and youth intake
([#33](https://github.com/mario595/cycling-manager/issues/33)).

## Player experience

Rob opens the roster. Every rider shows five ratings — climbing, sprinting,
flat, resistance, positioning — on a 0–10 scale, and a speciality: Sprinter,
Climber, Rouleur, Puncheur, Domestique. Mira Kestrel is a Climber, 9 for
climbing, 4 for sprinting, and reading her line takes a second rather than a
comparison digit by digit. Beside her speciality sit her age, her height and her
weight; she is 59kg and 1.68m, which is what being a Climber looks like.

Two of his riders show identical ratings. They are not identical, and Rob has no
way to tell from the roster page how they differ — the game stores their quality
more precisely than it shows it. One is 22 and one is 31, and that difference is
the one Rob can actually act on: he knows, because this is how cycling works,
that the young one has time ahead of him and the older one does not. Today that
is a judgement about the future rather than something he watches happen.

Picking a squad, Rob now has something to think about beyond five numbers. His
Sprinter is the obvious pick for a flat finish; his Climber is not, whatever her
positioning rating says. The label does work the raw ratings do not, because it
tells him what the rider *is* rather than only what they can currently do.

What Rob never sees: how good any rider can eventually become, when they will
peak, how fast they will fall away, or how fragile they are. Those exist inside
every rider from the day they are created. They do nothing yet, and the game
does not pretend otherwise.

## In scope

1. Every rider has five racing ratings — climbing, sprinting, flat, resistance,
   positioning — displayed to the player on a **0–10 integer scale**, everywhere
   ratings appear, including the squad selection screen.
2. The game stores those ratings at a finer resolution than it displays, so two
   riders showing the same rating can genuinely differ.
3. Every rider has a **speciality** — Sprinter, Climber, Rouleur, Puncheur,
   Domestique — assigned when the rider is created and **never changing for the
   rest of their life**. It is shown on the roster and wherever a rider is
   listed for selection.
4. Every rider has a visible physical build — height and weight — that never
   changes and is consistent with their speciality: sprinters heavier and
   bigger, climbers lighter and slighter.
5. Every rider has a visible **age**.
6. Every rider has a hidden **potential**: the ceiling their ratings will
   eventually grow toward.
7. Every rider has a hidden **peak age** and a hidden **decline rate**, so that
   two riders of the same age will not be on the same curve.
8. Every rider has a hidden **injury proneness**, describing how susceptible
   they are relative to other riders.
9. Every rider has a hidden **training affinity**, biased by their speciality,
   describing which ratings they will improve fastest in.
10. Riders can be **generated** — a new rider is produced complete, with ratings,
    speciality, build, age and hidden traits that are mutually consistent: a
    Climber is light and climbs well, a 34-year-old is at or past their peak.
11. Generating a group of riders produces a **deliberate spread** — some clearly
    worth building around, some clearly not, most in between — rather than
    variations on one average rider.
12. The existing rider population is **replaced** by a generated one, along with
    the race results and saved squads that referred to it.
13. None of the above changes how the race engine simulates a race. The engine
    reads the same five attributes it reads today.

## Out of scope

- **Riders improving or declining over time.** Split out — the age curve,
  potential, peak age and decline rate become *live* in a separate ticket. This
  one gives them somewhere to live. See *Deferred*.
- **Freshness** — a visible value falling with racing and recovering with rest
  at a hidden per-rider rate. Split out: it is a mechanic rather than a stored
  number, requiring a rule at race time and a rule on the weekly tick. See
  *Deferred*.
- **Anything reading the hidden traits.** Injury proneness is stored here and
  read by injuries ([#41](https://github.com/mario595/cycling-manager/issues/41));
  training affinity is stored here and read by training
  ([#36](https://github.com/mario595/cycling-manager/issues/36)). Neither is
  this feature's job.
- **An overall rating (OVR).** Cut. It collapses five deliberately incomparable
  ratings onto one axis and lets the player skip judging a rider, which is the
  judgement this feature exists to create.
- **Rider market value.** Not an attribute — an output of a market. Belongs to
  `transfers/` ([#31](https://github.com/mario595/cycling-manager/issues/31)).
- **Morale.** No. It needs grievances to be about — selection disputes, contract
  rows, a results history — and none of those exist.
- **A second, medium-term "form" number** distinct from freshness. No. Planning
  a peak requires a calendar to peak toward, and two freshness numbers would be
  one thing shown twice.
- **Scouting accuracy and attribute fog** (ratings shown as ranges that sharpen).
  No. Imperfect information needs a transfer market to matter in.
- **Descending as a rating separate from sprinting.** Later — see *Deferred*.
- **Time-trialling, cobbles/bike handling, weather tolerance.** Wanted, but
  blocked on things the engine does not model. Tracked as
  [#2](https://github.com/mario595/cycling-manager/issues/2),
  [#3](https://github.com/mario595/cycling-manager/issues/3) and
  [#4](https://github.com/mario595/cycling-manager/issues/4).

## Rules and edge cases

**Display scale.** The player's world is 0–10 whole numbers; the game's is
finer. Two riders showing the same rating can differ, and the player has no way
to tell them apart from the roster page. This is deliberate — it is what will
make watching a rider over time worth more than reading their line, once riders
change over time — and it means no screen can offer a meaningful sort on a
single rating. **This replaces the 1–100 values currently shown on the squad
selection screen**, which were built before this decision was taken.

**Speciality never changes.** A 34-year-old Sprinter whose sprinting has
declined to 4 is still a Sprinter. The label says what the rider *is* — a
consequence of their build — not what they are currently good at. A rider whose
ratings no longer flatter their speciality is a rider in decline, and reading
that from the roster is the intended experience, not a bug to be fixed by
re-labelling them.

**Build follows speciality, and never changes.** Height and weight are generated
to be consistent with the speciality and then fixed for life. A rider does not
get taller, and does not change what kind of rider they are.

**Age is visible and static for now.** A rider has an age from creation. Ageing
as seasons pass belongs to the growth-and-decline feature, along with everything
that makes age consequential.

**The hidden traits are inert in this feature, and the spec does not pretend
otherwise.** Potential, peak age, decline rate, injury proneness and training
affinity are generated and stored, and nothing reads them. A player cannot infer
potential today, because there is nothing to observe. That is accepted: the
alternative is generating the whole population twice, once now and once when
growth lands, and a generator that produces a coherent rider is the expensive
part. The rule that **every hidden trait must be inferable** — that a hidden
value with no observable consequence is an unfair dice roll rather than depth —
holds from the moment each trait becomes live, and is a bar the growth, injury
and training features must each clear.

**Generation must produce a spread, not a population of clones.** A generated
group of twelve contains riders a manager would build around and riders a
manager would sell. This is the property
[#46](https://github.com/mario595/cycling-manager/issues/46) depends on: its
starting rosters must differ from one another in shape while being comparable in
total strength.

**Replacing the existing population is destructive, and that is the decision.**
Existing riders are not backfilled — they are replaced. Race results and saved
squads point at riders, so those go too. This is a pre-launch world with no real
players and nothing worth preserving; inventing a scheme to detach historical
results from deleted riders would be protecting data nobody is attached to. The
world is repopulated from generation, and racing starts again.

**The engine boundary.** Attributes divide into two kinds, and the distinction
governs what is cheap and what is expensive:

- **In-race attributes** are read by the simulation. There are five, and adding
  a sixth invalidates the verified realism results for all six bundled courses
  and requires re-deriving that balance. Add sparingly and never casually.
- **Between-race attributes** — age, speciality, build, potential, peak, decline,
  injury proneness, training affinity — are invisible to the simulation
  entirely. They cost nothing in engine terms.

Everything this feature adds is the second kind. That is why it can be
substantial without touching the engine.

## Decisions taken

- **Do new engine inputs get added?** No. New in-race attributes each cost a
  re-derivation of the audited course balance, so they are judged individually
  rather than added by default.
- **How much of a rider's quality is visible?** The five ratings are visible but
  coarsened to 0–10; the true finer value is never shown.
- **Does the 0–10 scale override the squad screen built by #37?** Yes. The
  squad screen currently shows raw 1–100 values and changes to 0–10.
- **Can two riders look identical but differ?** Yes, accepted deliberately.
- **Is speciality derived from the ratings or innate?** Innate: assigned at
  creation from the rider's physical build and kept for life, as in real
  cycling. It will also bias training gains, which gives it a mechanical job
  rather than making it a label.
- **Do riders age, improve or decline in this feature?** No. Split into its own
  ticket, so that this one unblocks #46 and #33 without waiting on a weekly-tick
  design and a balancing exercise.
- **Is freshness part of this?** No. Split into its own ticket — it is a
  mechanic, not an attribute.
- **Are the hidden traits stored even though nothing reads them?** Yes.
  Generating a coherent rider is the expensive part and doing it twice is worse
  than storing inert fields.
- **What happens to existing riders?** They are replaced by a generated
  population, along with the race results and squads that referred to them.
- **Form and condition as two numbers?** No — one freshness number, and not in
  this feature.
- **Is there an overall rating?** No. Cut.
- **Are the design mockups binding on scope?** No. They are a visual guide only;
  where this spec and the mockup disagree, the spec wins.

## Open questions

- **Where does the player learn how any of this works?** Once riders grow and
  decline, the feature depends on the player understanding that young riders
  improve and old ones do not, since the numbers driving it are hidden. Whether
  that arrives as onboarding text, scout reports, or is left to be discovered is
  unresolved — resolved by whoever specs the rider detail screen
  ([#47](https://github.com/mario595/cycling-manager/issues/47) is the nearest
  existing ticket). Not blocking, because nothing grows yet.
- **Do AI-managed teams' riders follow the same rules?** Presumably yes, but the
  answer affects world balance over many seasons and belongs with `world/` and
  [#45](https://github.com/mario595/cycling-manager/issues/45).

## Deferred

- **Rider growth and decline.** The age curve made live: riders below their peak
  improve toward their potential, riders past it decline at their own rate, and
  ages advance as seasons pass. Waiting because it needs a hook on the world
  tick that has not been designed and a balancing pass so the curve is neither
  invisible nor absurd — and because #46 and #33 need the attributes, not the
  movement.
- **Freshness.** Visible, falls with racing, recovers with rest at a hidden
  per-rider rate, with a floor and a ceiling so that rest is always eventually
  sufficient and continuous racing bottoms out rather than falling forever.
  Waiting because it is the one item here that is a mechanic spanning `racing/`
  and the weekly tick, and nothing currently blocked needs it.
- **Descending split from sprinting, with crash risk for poor handlers.**
  Sprinting currently doubles as descending speed, so a descending specialist
  cannot exist. Wanted, but it is an in-race attribute, so it needs an engine
  change and a full re-derivation of the six-course realism balance. Waiting for
  that to be worth doing on its own terms.

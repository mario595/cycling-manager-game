# Rider freshness

**Status:** proposed
**Domain(s):** `riders/`, `racing/`, `world/`, `api/`
**One-liner:** Every rider carries a visible freshness that falls when they
race and recovers when they rest, so fielding your strongest four every
single week quietly costs you results instead of being free.

## Why this exists

Today a squad pick is a pure quality comparison: whichever four riders have
the best attributes should always start, every week, forever. Nothing in the
game notices or cares that a rider raced last week too. That is not how
managing a team works, and it removes a decision a manager should be making
every week: who races, and who is rested for it.

Freshness gives racing a cost. A rider who races drops below their best;
a rider who rests climbs back toward it. A manager who always starts the
same four will, over a season, be fielding tired riders against a rival who
rotated — and will lose races for a reason visible on the squad screen, not
a reason hidden in the simulation.

## Player experience

Rob opens squad selection for Sunday's race. Mira Kestrel, his strongest
Climber, shows a freshness bar alongside her ratings — she raced last
Sunday too, and it's low. He can still pick her; nothing stops him. But the
bar makes the trade-off plain: start her tired and she'll likely underperform
what her ratings promise, or rest her this week and have her back near her
best for the race that actually matters.

He rests her. A week later, the bar has climbed — not all the way, but
enough that starting her again is a real option rather than a gamble. He
never sees the exact rate she recovers at; he learns it by watching her,
same as he'd learn a real rider's resilience over a season of racing them.

A teammate who never opens the squad screen keeps getting fielded
automatically. The auto-pick is not oblivious to freshness — it won't run
the same four into the ground the way a naive strength-only pick would —
but it's still no substitute for a manager actually planning a rotation.

By the end of a season, a manager who ignored freshness has a team of
riders quietly racing below what the roster page says they're capable of,
and a manager who rotated has a team performing closer to its true
strength. Nothing announces the difference in words; the results do.

## In scope

1. Every rider has a visible **freshness**, shown on the squad selection
   screen on the same 0–10 scale as the ratings.
2. Freshness falls when a rider races, by a fixed amount per race.
3. Freshness recovers during a week a rider does not race, at a hidden
   rate individual to that rider — some riders bounce back faster than
   others, and a manager can learn who by watching them over a season.
4. Freshness cannot rise above its starting maximum and cannot fall below
   a floor. A rider raced continuously reaches that floor and stays there
   rather than falling forever; a rider rested for long enough always
   returns to full.
5. The floor is low enough that a rider sitting on it is a real handicap —
   clearly, not marginally, worse than the same rider at full freshness.
6. A tired rider **performs below their ratings** in a race, in proportion
   to how tired they are. They are never blocked from being selected, and
   a tired rider can still win — they are simply working against a
   disadvantage the manager chose to accept.
7. A new rider — freshly generated, whether from a population reset or a
   newly claimed team — starts at full freshness.
8. The automatic squad picker (used for a team with no manager-chosen
   squad) takes freshness into account rather than picking on raw
   attribute strength alone.

## Out of scope

- **Freshness on the roster screen.** The squad screen is where the number
  changes a decision; the roster is a page you read. Later, if wanted —
  see *Deferred*.
- **Cost varying by race distance or difficulty.** Every race costs the
  same amount of freshness. The calendar has no long or short races to
  distinguish yet, and a varying cost is a tuning axis nobody could
  perceive.
- **Stage races costing more per day.** No stage race exists in the game
  yet ([#9](https://github.com/mario595/cycling-manager/issues/9)). This
  is the one question the parent ticket asked that has no answer today
  because there is nothing to answer it about — see *Deferred*.
- **Freshness loss from anything but racing.** No cost for training, no
  cost for travel, no cost for being on a team at all. Only starting a
  race drains it.
- **A visible recovery rate.** The rate a rider recovers at is not shown
  as a number anywhere. It is inferred by watching freshness change week
  to week, the same way `riders/README.md` treats every other hidden
  trait.
- **A second, medium-term "form" number.** Already rejected once, in the
  attributes spec this was split from: one freshness number, not two.
- **A hard selection floor that blocks a tired rider from racing.** A
  manager can always start whoever they choose. The cost is in the
  result, not in the picker.
- **Freshness affecting injury risk.** That link, if it exists at all,
  belongs to injuries ([#41](https://github.com/mario595/cycling-manager/issues/41))
  to decide, not to this feature.

## Rules and edge cases

**Recovery happens on the weekly tick, not continuously.** A rider's
freshness updates when a game week opens, for however many weeks were
missed if the world fell behind — the same batching the age curve already
uses for weekly growth. There is no freshness change mid-week.

**Racing and recovering in the same week.** A rider who races this week
loses freshness for the race; whether they also recover that same week is
an implementation question with no player-visible difference worth
specifying here, as long as a rider raced every week without a break
trends toward the floor over a season, and a rider rested even
occasionally recovers meaningfully.

**A rider who races most weeks should still be worth fielding sometimes,
but a rider raced every single week for a season should be a manager's
own mistake, not a viable long-term strategy.** This is the balance point
the numbers must hit: freshness needs to fall faster from a race than a
single week of rest returns, so that only a rotation across the squad —
not merely "resting occasionally" — keeps a rider consistently near full.

**The floor is a real handicap, not a rounding error.** A rider parked at
the floor must be a visibly worse pick than the same rider fresh — the
kind of difference a manager notices in the results, not one buried in
the noise of a single race's randomness.

**A tired rider's ratings do not change.** Climbing, sprinting, flat,
resistance and positioning stay exactly what they are — freshness is a
separate, temporary multiplier on performance in a given race, not a
change to the rider's underlying ability. The roster page is unaffected;
only what a tired rider actually does in a race is.

**Auto-pick's use of freshness is a light preference, not a
optimisation.** It exists so an unmanaged team doesn't mechanically run
its best four into the ground for a reason the player has no way to see.
It is not expected to out-plan a manager who rotates deliberately —
auto-pick losing to deliberate selection is existing, intended behaviour
(`racing/README.md`) and this feature does not change that intent.

## Decisions taken

- **Freshness produces a soft performance penalty, never a hard block on
  selection.** A manager can always start a tired rider; the cost shows
  up in how that rider performs, not in whether they can play at all.
  Chosen because the calendar allows at most one race per day and no
  stage races exist — a hard gate would rarely trigger and would feel
  like the game taking the decision away on the rare week it did.
- **One race costs more freshness than one week of rest returns.** This
  is what makes rotation across a squad necessary rather than optional —
  without it, a rider could race every week forever with no consequence,
  and the feature would be decoration.
- **The recovery rate is hidden per rider; the freshness value itself is
  visible, 0–10.** Keeps the decision the (now-implemented) rider
  attributes spec already took. The hidden rate stays fair under
  `riders/README.md`'s rule that a hidden trait must be inferable, because
  its effect — how fast the visible number climbs — is something the
  player watches happen.
- **The floor is low**, so that a rider raced continuously becomes a
  genuine liability rather than a mild inconvenience — the whole point of
  the feature is that neglecting rotation should visibly cost a manager
  results.
- **Auto-pick is updated to prefer fresher riders**, rather than left
  purely strength-based, so an unmanaged team doesn't visibly and
  permanently degrade for a reason invisible to the player. It remains
  deliberately weaker than a manager's own choice, consistent with its
  existing role.
- **Freshness is shown only on the squad selection screen**, not the
  roster, because that is the only screen where the number currently
  changes a decision.
- **Every race costs the same freshness regardless of course**, and stage
  races are explicitly out of scope, because neither varying difficulty
  nor stage races exist yet in a form this feature could react to.

## Open questions

None. The parent ticket's stage-race question is answered by *Out of
scope*: there are no stage races to cost differently yet.

## Deferred

- **Freshness on the roster screen.** Later, if a manager scanning the
  full roster (not just the squad screen) turns out to want it. One-line
  addition to an existing serializer once wanted.
- **Per-race cost varying by distance or difficulty.** Waiting on the
  calendar actually containing races distinct enough for it to matter.
- **Stage races costing more freshness per day.** Blocked on stage races
  existing at all ([#9](https://github.com/mario595/cycling-manager/issues/9)).
- **A "who's tired" summary.** Fold into weekly training's
  ([#36](https://github.com/mario595/cycling-manager/issues/36)) page
  once it exists, alongside the similar growth/decline summary already
  deferred there — one weekly report, not two.

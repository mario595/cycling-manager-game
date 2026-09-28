# Youth intake generation

**Status:** proposed
**Domain(s):** `riders`
**One-liner:** An open development squad periodically brings in young riders of wildly varying quality, who grow there and stay off the senior roster until a manager decides what to do with them.

## Why this exists

The development squad (#32) is a facility a manager pays for and nothing
more — no rider has ever arrived through it. This is the ticket that makes
the payoff real: the reason to open a squad, and to climb its ladder, is
that better odds of a genuinely promising young rider are worth paying for.

It is also the first time the game gives a manager a rider whose future is
unknown. Every rider today — starting roster, free agent, transfer target —
comes with ratings already legible on the 0-10 scale. A youth intake rider
arrives young and mostly weak, with a hidden ceiling nobody can read. Whether
that ceiling is worth the wait is exactly the judgement `specs/archive/rider-attributes.md`
built hidden `potential` for, and until now nothing has given a manager a
rider to make that judgement about.

## Player experience

A manager with an open development squad gets on with their season. Every
few weeks — the squad panel says when the next one is due — a batch of two
young riders arrives. The manager finds them on the squad's own screen, each
shown the same way a roster rider is: name, age, speciality, the five 0-10
ratings. They are visibly teenagers with visibly modest numbers. Most look
unremarkable. Once in a while one stands out — high for their age, or simply
higher than the rest of the batch — but the panel never says which, if any,
of them is actually good. That is the manager's own read, same as sizing up
any rider.

A higher squad level does not change how many arrive or promise a better
rider for certain. It shifts the odds — a squad run at Elite finds a
genuinely promising prospect more often than one run at Regional, across a
season, not in any one batch. The panel says as much, in the same plain
terms it already uses for cost: what a higher level buys is better odds, not
a guarantee.

These riders are not on the senior roster. They cost the manager nothing
individually — the squad's weekly cost is what's paying for them — and they
cannot be selected for a race, trained by the team's trainer, or listed on
the transfer market. What they do is grow, the same age curve every rider
follows, so a rider who arrived unremarkable can, over a season, start to
look like something. That growth, watched over time, is the only window
into the hidden ceiling — and it is also all this ticket promises: whether
and how a manager acts on what they see is #34.

If a manager closes their squad, or a team changes hands, every rider
sitting in it that moment is released as a free agent — the same market
every released or unsigned rider already passes through, prospects
included. A youth rider nobody wanted eventually expires by the same rule
that already clears out the bottom of that market.

## In scope

1. An open development squad receives a batch of new young riders on a
   fixed cadence through the season, as long as the squad stays open.
2. Every arriving rider is young, and their starting ratings vary widely —
   most are well below what it takes to race competitively, some are
   promising for their age.
3. A higher development squad level improves the odds, across a season, of
   a batch containing a promising rider. It does not change batch size, and
   it does not guarantee anything about any single batch.
4. A rider who has arrived through youth intake is visible to the manager
   on the development squad's own screen, showing the same ratings, age and
   speciality a roster rider shows elsewhere, plus when they arrived.
5. A rider in the development squad ages and grows exactly as any other
   rider does.
6. A rider in the development squad is excluded from: race squad selection,
   the team's trainer focus, the senior roster's 30-rider cap, and the
   transfer market (cannot be listed, bid on, or released through it).
7. A rider in the development squad draws no individual weekly wage; the
   squad's own weekly cost is what pays for the facility that holds them.
8. When a development squad closes — by the manager's choice or because the
   team is claimed by a new manager — every rider then sitting in it is
   released as a free agent.
9. The development squad panel states, in plain terms, how often riders
   arrive and that a higher level improves the odds of a promising one —
   never a number, never a guarantee.

## Out of scope

- **Promoting a squad rider to the senior roster, retaining them longer, or
  discarding them outright.** That is #34 in full. Under this ticket alone,
  a squad rider has no path onto the senior roster — the only way they
  leave the squad is the squad closing, which sends them to the free-agent
  market, not the roster.
- **A cap on how many riders a squad can hold.** #34's concern, once triage
  exists to keep the squad from just accumulating. Accepted as an open
  question here — see *Rules and edge cases*.
- **Any effect of squad tenure on a rider beyond ordinary growth.** A rider
  who has sat in the squad for three intakes grows no faster or slower for
  it.
- **Batch size varying by level, or by anything else.** Every open squad,
  at any level, gets the same number of riders per intake (see *Decisions
  taken*).
- **An arrival notification or dashboard alert.** There's no inbox or
  notification system in the game yet. A manager finds new arrivals by
  visiting the squad screen, same as they'd notice anything else in the
  game today.
- **Scouting or any report on a squad rider beyond what's already
  visible.** That is the scout (#40), which needs #34's triage to have
  something to sell information into.
- **Intake for a team with no open squad, or an unmanaged team.** A closed
  squad receives nothing, and unmanaged teams cannot open one (#32).

## Rules and edge cases

- **Cadence: one batch of two riders every four weeks the squad is open,**
  aligned to the season's week numbers, not to when the squad happened to
  open. A twelve-week season produces at most three batches (weeks 4, 8 and
  12), six riders in total, for a squad open the whole season.
- **A squad that opens after a season's last intake week gets nothing until
  the following season's first one.** A squad opened the week before an
  intake week still receives that batch in full — there is no partial
  batch, and no discount for having just paid the fee. This is the same
  shape as the weekly cost: paid for the week regardless of when in it the
  squad opened.
- **No intake happens outside a declared season's weeks.** Between seasons,
  nothing arrives, same as nothing else in the game moves.
- **A rider's starting quality is drawn from a wide spread, skewed toward
  the low end.** Most of every batch will not be worth developing; that's
  the intended shape of triage once #34 exists, and it's what makes a
  promising arrival feel like a find rather than the expected outcome.
- **A higher level shifts the odds of a promising rider upward; it never
  guarantees one, and a lower level never guarantees a bad batch.** A
  Regional squad can still produce a gem, rarely; an Elite squad can still
  produce a weak batch. What differs is the average over many batches, not
  any single one — the same shape the age curve's `potential` already
  applies to a single rider, one level up: probability, not promise.
- **A squad rider carries no salary and is excluded from the wage bill.**
  Nothing changes about how a roster rider's wage is computed; this is
  purely "this rider is not counted."
- **A squad rider cannot be selected into a race squad, trained by the
  team's trainer, listed on the transfer market, or counted toward the
  30-rider roster cap.** All five exclusions hold for as long as the rider
  remains in the development squad specifically — none of them are new
  rules for a roster rider.
- **Closing the squad, whether by the manager or because a new manager
  claims the team, releases every rider then in it as a free agent,
  immediately.** They enter the same market any other released or unsigned
  rider passes through, including its existing expiry rule for riders that
  go unsigned for a long time at the bottom of the market. A youth rider is
  not treated specially there — this ticket adds no new exception to that
  market's rules.
- **The development squad panel's wording about odds is qualitative,
  never numeric.** It says a higher level improves the odds of a promising
  arrival; it does not say by how much, and it never promises a specific
  outcome for the next batch.

## Decisions taken

- **Ship without #34.** A squad rider has no exit but the squad closing
  until #34 lands. Accepted for the same reason #32 shipped ahead of this
  ticket: the game has no live players yet, and #34 follows directly next
  on the roadmap.
- **Squad level affects odds of quality only, never batch size.** Keeps
  every open squad producing the same amount of triage work regardless of
  level, and puts the entire value of a higher level into the hidden-trait
  judgement the game is built around, rather than into volume.
- **Cadence is every 4 weeks, batch size 2** — three intakes and six riders
  across a twelve-week season. Frequent enough that a batch can be compared
  against the last one; infrequent enough that six riders a season doesn't
  overwhelm triage once #34 exists.
- **A closed squad's riders become free agents, not retirees and not
  automatic promotions.** Promotion is #34's decision to make, not a side
  effect of closing; the free-agent market already exists and already
  expires long-unsigned riders at the bottom, so nothing new has to be
  built to clean up a youth rider nobody wanted.
- **No dashboard alert.** There's no notification system yet; adding one is
  bigger than this ticket and belongs, if it ever gets built, to whatever
  ticket introduces alerts generally.

## Open questions

- **Is there ever a cap on squad size before #34 ships?** Left open here,
  deliberately: at six riders a season, the pileup before #34 lands is
  small, and a cap is easier to size once #34 defines what triage actually
  removes from the squad. If #34 slips a long way, this may need revisiting
  on its own.

## Deferred

- **A cap on squad size** — waits on #34 to define triage, which is what a
  cap would actually be protecting against.
- **An arrival notification** — waits on a notification/inbox system that
  does not exist yet.
- **Scout reports on squad riders** — #40, which needs #34's triage to have
  something to sell information into.

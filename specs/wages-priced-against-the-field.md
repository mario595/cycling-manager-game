# Wages priced against the field

**Status:** approved
**Domain(s):** `riders/` (salary), `transfers/` (market value), `economy/` (salary review), `world/` (season close), `api/`, `frontend/` (roster)
**One-liner:** A rider is paid for how good he is compared with the rest of
the world's riders, so wage bills stay level as the whole world gets stronger.

Issue: [#166](https://github.com/mario595/cycling-manager/issues/166), found
during #156.

## Why this exists

Riders train every week, and at every season close their salaries are
repriced from their absolute strength. Income doesn't grow with them: the
prize pot is a fixed table, and sponsorship moves only with fanbase. A
four-season measurement with AI teams only, on the world calendar, put the
average wage bill at $181k, $202k, $220k and $228k a season. The average net
went −$5k, +$4k, −$10k, −$14k, and by season 4 the median team was losing
about $70,000 a season.

Growing income to match was considered and rejected. It would shrink every
fixed price in the game (the starting balance, trainer and development squad
fees) and need all of them indexed too, so a late joiner's $500k would buy
less than an early joiner's. Pricing wages against the field keeps the amount
of money in the game level instead, and nothing else has to move.

## Player experience

Nothing changes in season 1. A new world pays what it pays today.

At each season close, salaries are repriced as before, but against the field
as it now stands. A rider who kept pace with the world earns what he earned.
A rider who outgrew it earns more. A rider who improved, but less than
everyone else did, can earn slightly less. The season-end salary review on
the roster screen says when the field as a whole got stronger (for example,
"The field got 6% stronger this season, and wages are set against it"), so a
pay cut for an improved rider isn't a mystery.

Market value follows the same rule. Signing fees, severance and auction
reserves are set by how good a rider is relative to the field, so they hold
their meaning against a level wage bill.

## In scope

1. Every weekly salary is set by the rider's strength relative to the field's
   level, on today's curve, with today's age adjustment.
2. The field's level is measured at each season close from every active
   rider on a team's roster. Free agents, development squad youth and retired
   riders don't count.
3. The field's level is frozen between closes. Every price set during a
   season (a new rider, a promotion, a signing fee, a valuation) uses the
   level from the last close.
4. The level is calibrated so that the field's average weekly salary equals
   what a freshly generated world pays on average. A world that has never
   closed a season prices exactly as today.
5. Market value, and with it signing fees, severance and auction reserves,
   uses the same relative strength.
6. The season-end salary review says how much stronger (or weaker) the field
   got that season.
7. Staging and production need no migration of rider data. Every salary
   reprices at the next season close.

## Out of scope

- **Growing income with the world** (rejected; see *Why this exists*).
- **Trainer prices.** A trainer's skill doesn't grow, so his fee and salary
  don't drift.
- **Prize tables and sponsorship.** These are unchanged.
- **Mid-season repricing.** A wage is still predictable inside a season.

## Rules and edge cases

- **Calibration is to the average, not to each rider.** The total a field
  pays per rider stays level. How it splits between strong and weak riders
  follows the existing curve.
- **An empty or tiny field** (no rostered riders) leaves the level unchanged.
- **The level can rise as well as fall.** If a world gets weaker, for example
  after a wave of retirements, salaries rise back towards today's prices.
- **The level is bounded**, so one odd season close can't produce absurd
  prices.

## Decisions taken

- *Option 1 (field-relative pricing) or option 2 (index income)?* Option 1.
  (Mario, 2026-11-25.)
- *Who is the field?* Active rostered riders only. (Default, Mario 2026-11-25.)
- *When is it measured?* At each season close, frozen in between. (Default.)
- *Calibration?* A new world prices as today, and the average wage stays at
  that level. (Default.)
- *Age adjustment?* Unchanged. (Default.)
- *Market value too?* Yes, in this ticket. (Default.)
- *What does the manager see?* One line in the salary review. (Default.)
- *Migration?* None; the next close reprices. (Default.)

## Open questions

None.

## Deferred

None.

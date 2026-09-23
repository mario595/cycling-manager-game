# Transfers

## What this app owns

`transfers.pricing.market_value_for(rider)` — a rider's market value, in
whole credits. That is all: **no models, no migrations, no stored field**.
Value is a pure function of a rider's visible attributes and age, recomputed
on every read, never persisted. This is deliberate, not an early-stage gap:
the spec ([#31](https://github.com/mario595/cycling-manager/issues/31))
requires value to move the instant a rider's attributes move, and a stored
column would be a cache that drifts from the arithmetic it summarizes.

`transfers/migrations/` exists as an empty package only so Django treats
the app as migration-capable once a later ticket gives it its first model.

This app is the future home of the transfer market itself — auctions
([#28](https://github.com/mario595/cycling-manager/issues/28)), free
agents ([#29](https://github.com/mario595/cycling-manager/issues/29)) and
AI trading ([#30](https://github.com/mario595/cycling-manager/issues/30)) —
but none of that is built yet. Today it holds one pricing function.

## Value vs salary

The game already prices riders once: `riders.pricing.weekly_salary_for`,
what a rider costs to keep, stored at generation and frozen for the
season. Market value is a **second** price — what a rider is worth — and
the two share one input but not their shape:

- **Shared:** `riders.pricing.strength(rider)`, the five engine attributes
  weighted by speciality. Both prices import it unchanged — one definition
  of "how good is this rider".
- **Not shared:** age. Salary's `age_multiplier` is a mild, symmetric ±15%
  penalty around a 24-32 prime band — a wage cares about current fitness
  for the job. Value's `career_horizon` is monotonically decreasing from
  age 23 onward, because a valuation prices in years of career remaining,
  not current form. A 22-year-old and a 30-year-old of identical ability
  have near-identical salaries but very different values — that gap is the
  point (see the spec's *Rules and edge cases*).

**Never express value as a multiple of salary** (`weekly_salary_for(rider)
× k`). That would inherit salary's wrong-shaped age curve and couple the
two prices together, so a future salary retune
([#26](https://github.com/mario595/cycling-manager/issues/26)) would
silently move every valuation. Keep two formulas over the same `strength()`,
not one wrapping the other.

Rounding also differs: salary rounds to the nearest 50 (right for a weekly
figure in the hundreds); value rounds to the nearest 1,000 (`_round_to_nearest_1000`,
local to this app — a capital sum in the hundreds of thousands rounded to 50
reads as false precision).

## Never a hidden trait

Like salary, market value reads only visible fields — the five engine
attributes and `age`. `potential`, `peak_age`, `decline_rate`,
`injury_proneness`, `training_affinity`, `recovery_rate` and `growth_debt`
are never read here. Pricing off a hidden trait would silently expose it
through a number the player can already see, which `riders/README.md`'s
*Visible vs hidden* treats as a defect everywhere it could happen. Two
riders identical on the roster page must be worth the same, even if one has
more room to grow. `transfers/tests/test_pricing.py::test_no_hidden_trait_is_read`
guards this directly.

## Calibration

`VALUE_AT_MIN_STRENGTH` and `VALUE_AT_MAX_STRENGTH` were picked by sampling
`riders.generation.generate_rider` over a large seeded population, the same
method `riders/pricing.py`'s own constants use — not by reasoning about the
theoretical 1-100 range, since a generated rider's attributes cluster well
under it in practice. The anchor: an average generated rider's market value
lands at roughly one twelve-week season of their own wages
(`transfers/tests/test_pricing.py::test_average_value_is_about_one_season_of_wages`).
A second calibration test pins that value's spread across a generated
population is wider than salary's, proving the age skew actually does
something rather than just rescaling the same curve
(`test_generated_roster_value_spans_wider_than_salary`).

**Retuning the formula means re-running these two tests until they pass
again, not eyeballing the constants.** If `riders.pricing.strength()` or
`riders.generation.generate_rider`'s quality spread ever changes, both
salary's and value's calibration tests should be re-checked together —
they are sampling the same population.

## What `transfers/` may import

Only `riders/` (`AGENTS.md`'s dependency direction: `transfers -> riders`).
Not `economy/`, not `teams/`, not `world/`, not `api/`. `api/` is the only
app that imports `transfers/`, the same one-way rule every other domain
follows.

## Future work / possible improvements

Market value was built to serve four consumers, none wired up yet:

- **Reserve price for auctions.** [#28](https://github.com/mario595/cycling-manager/issues/28)
  is the natural place for value — or a percentage of it — to become a
  floor an auction bid must clear, protecting a seller in a thin market
  from a strong rider selling for next to nothing.
- **AI bidding logic.** [#30](https://github.com/mario595/cycling-manager/issues/30)
  needs some number to decide what to bid and when to stop; this is it.
- **Forced sales under insolvency.** [#27](https://github.com/mario595/cycling-manager/issues/27)
  needs a price when there is no auction to discover one.
- **Season-boundary salary renegotiation.** [#26](https://github.com/mario595/cycling-manager/issues/26)
  needs a value to renegotiate a rider's salary against.

Nothing here reads `market_value_for` back yet — it is purely informational,
shown on the Roster screen (`api/README.md`, `frontend/README.md`).

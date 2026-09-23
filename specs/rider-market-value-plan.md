# Rider market value — Implementation Plan

**Spec:** `specs/rider-market-value.md` · **Issue:** #31 · **Status:** proposed
**Apps touched:** `transfers/` (new), `api/`, `frontend/`

## Context you need

The game already prices riders once. `riders/pricing.py` computes
`weekly_salary_for(rider)` — what a rider costs to keep, per week — from two
pure functions over **visible** fields only: `strength(rider)` (the five
engine attributes weighted by `riders.generation.SPECIALITY_PROFILES`) and
`age_multiplier(age)` (a mild ±15% taper outside a 24-32 prime band). That
result is **stored** on `Rider.weekly_salary` at generation and frozen for
the season.

This feature adds a **second** price — what a rider is *worth* — which is
computed fresh on every read, never stored. The two numbers share inputs
but not shape, and that difference is the whole feature (see Design
decision 2).

What exists today that this plan builds on:

- `riders/pricing.py` — `strength()`, `age_multiplier()`,
  `weekly_salary_for()`, `_round_to_nearest_50()`. Read it before starting;
  this plan's new module is deliberately its sibling in structure.
- `riders/models.py` — `Rider`, `ENGINE_ATTRIBUTES`, `Rider.Speciality`.
  Age is validated 18-40. The hidden traits (`potential`, `peak_age`,
  `decline_rate`, …) are listed there and **must not** be read by this work.
- `api/serializers.py:86` — `RiderSerializer`, the roster payload.
  `api/serializers.py:241-250` shows the exact pattern to copy: a
  `SerializerMethodField` calling a pricing function (`staff.pricing`).
- `api/views.py:306` — `RiderListView`, which returns a **bare list**
  (`Response(RiderSerializer(riders, many=True).data)`). The squad total
  needs an envelope; see Design decision 6.
- `economy/services.py:144` — `payroll_for(team)`, the wage-bill total the
  squad total mirrors. Note it aggregates in SQL because `weekly_salary` is
  a column; market value cannot (Design decision 7).
- `frontend/src/api.ts:225` — the `Rider` interface and `getRiders()`.
  `frontend/src/useRoster.ts` polls it every 60s.
  `frontend/src/screens/Roster.tsx` renders it; `formatMoney` from
  `frontend/src/format.ts` is the `$` formatter.

Repo rules this work is bound by (`AGENTS.md`):

- **Dependency direction.** `transfers/` is new and unlisted. This plan adds
  `transfers -> riders` and nothing else. `transfers/` must **not** import
  `economy/`, `teams/`, `world/` or `api/`. Only `api/` imports `transfers/`.
- **Apps are created on demand and get a `README.md` in the same change.**
- Tests are pytest: `.venv/bin/python -m pytest`. A worktree has no `.venv` —
  use `/home/mario/dev/cycling-manager/.venv/bin/python`.
- Money is displayed with a `$` prefix, thousands-separated, never a decimal.

## Goal

When this is done:

1. `transfers.pricing.market_value_for(rider)` returns a whole-credit
   valuation from a rider's visible attributes and age, with no database
   access and no hidden trait read.
2. Value weighs age far more heavily than salary does, and monotonically —
   a 22-year-old is worth more than a 30-year-old of identical ability.
3. The roster API ships `market_value` per rider plus a `squad_value` total.
4. The Roster screen shows each rider's value next to their salary, and the
   squad total in the header.
5. Nothing reads the value back. No model, no migration, no stored field.

## Design decisions (settled — implement these, do not substitute)

**D1 — A new `transfers/` app, even though it has no models.**
The spec places this in `transfers/`, and `AGENTS.md` already reserves that
folder for the market. A model-less app is unusual but correct here: it is
the home every later market ticket (#28, #29, #30) builds into, and putting
the function in `riders/` instead would mean moving it later, breaking every
import. The app gets `apps.py`, `__init__.py`, `pricing.py`, `README.md`,
`tests/`, and an empty `migrations/` package. **Do not** run `makemigrations`
for it — there are no models, so there is no initial migration, and an empty
one is noise. Add `"transfers"` to `LOCAL_APPS` in
`config/settings/base.py` anyway: the app must be installed for its tests to
be collected under the project's settings.

**D2 — Value reuses salary's `strength()` but gets its own age curve.**
This is the load-bearing decision. `riders.pricing.strength()` is imported
and reused unchanged — one definition of "how good is this rider",
speciality-weighted, shared by both prices. But `riders.pricing.age_multiplier`
is **not** reused: it is a symmetric ±15% penalty that treats 18 and 40 as
equally undesirable, which is right for a wage and wrong for a valuation. A
valuation needs a *monotonic career-horizon* curve — worth falls as age
rises, because value is about how many good years remain. `transfers/pricing.py`
defines its own `career_horizon(age)` for this.

**Do not** try to express value as `weekly_salary_for(rider) × some_factor`.
That would inherit salary's wrong-shaped age curve and couple the two
prices, so a future salary retune (#26) would silently move every valuation.
Two formulas over the same inputs, sharing only `strength()`.

**D3 — `career_horizon(age)` is monotonically decreasing, linear, clamped.**
1.0 at `_PEAK_VALUE_AGE` (23) and below, falling linearly to
`_HORIZON_AT_MAX_AGE` (0.15) at age 40. A 22-year-old and an 18-year-old
are worth the same multiplier — the spec does not ask for teenagers to be
worth *more* than riders entering their prime, and a curve that peaks
mid-range would reintroduce salary's symmetry. Below 23 it is flat; above,
it falls. Keep it linear: a polynomial here is unjustifiable precision on a
number nobody can verify.

**D4 — Value is a capital sum in the same convex shape as salary.**
`market_value_for` uses the same structure as `weekly_salary_for`: strength
scaled 0-1, raised to `_STRENGTH_EXPONENT` (2.0 — the same exponent, so the
star premium is felt the same way in both prices), interpolated between
`VALUE_AT_MIN_STRENGTH` and `VALUE_AT_MAX_STRENGTH`, then multiplied by
`career_horizon(age)`. Calibrate the two constants so an average generated
rider's value lands at roughly **one season of their own wages** (12 weeks —
`schedule/` declares twelve-week seasons). That is the anchor the spec's
"roughly a season's wages" promises, and it makes value legible: "this
rider is worth about a year of what I pay them."

**D5 — Rounding is to the nearest 1,000, not 50.**
`riders.pricing._round_to_nearest_50` is right for a weekly wage in the
hundreds. A capital sum in the hundreds of thousands rounded to 50 reads as
false precision (`$412,350`). Define a local `_round_to_nearest_1000`. Do
**not** import the private helper from `riders/pricing.py` — it is private,
and the two roundings are genuinely different decisions.

**D6 — The roster endpoint gains an envelope. This is a breaking API change.**
`RiderListView` returns a bare JSON array today. The squad total has nowhere
to live in an array, so the response becomes:

```json
{"riders": [...], "squad_value": 4820000}
```

The alternative — a second endpoint for the total — means two round trips
and two chances for the numbers to disagree. Changing the shape is correct
and cheap because there is exactly one consumer (`frontend/src/api.ts`'s
`getRiders`), which this plan updates in the same change (W5). **Update the
client and the screen in the same commit as the view** so the repo is never
left with a frontend reading `.map` on an object.

**D7 — `squad_value` is computed in Python, not SQL.**
`economy.services.payroll_for` uses `Sum("riders__weekly_salary")` because
salary is a stored column. Market value is not stored — it is a function of
five columns and age — so there is nothing to `Sum`. The view already has
the rider queryset in memory for serialization; sum over it:
`sum(market_value_for(r) for r in riders)`. A roster is ~12 riders, so this
is free. **Do not** add a stored `market_value` column to make an
aggregate possible — the spec's *Rules and edge cases* requires value to
move the moment attributes move, and a stored column is a cache that will
drift.

**D8 — No floor above zero for a declined rider.**
The spec is explicit: value may fall close to nothing. `market_value_for`
has no `max(..., MINIMUM)` guard, unlike `weekly_salary_for`, which floors
at `SALARY_AT_MIN_STRENGTH`. It still returns a non-negative int, because
`strength` is clamped at 0 and `career_horizon` at 0.15.

**D9 — Never read a hidden trait.** `potential`, `peak_age`, `decline_rate`,
`injury_proneness`, `training_affinity`, `recovery_rate`, `growth_debt` are
off limits. A test enforces this (W2). This mirrors the rule
`riders/README.md` already sets for salary and the spec restates as a hard
constraint.

## Data model

**No model changes. No migrations. No new fields.**

This is deliberate and is the single most likely thing for a reader to get
wrong. Market value is a pure function computed on read (D7). If you find
yourself writing `models.py` in `transfers/`, stop — you have misread the
plan.

`transfers/migrations/__init__.py` exists (an empty package) only so Django
treats the app as migration-capable when a later ticket adds its first
model. It contains no migration files.

## `transfers/pricing.py` (new)

```python
"""What a rider is worth on the market. A pure function of visible
attributes and age — never a hidden trait, never stored. Recomputed on
every read so a rider who improves is worth more immediately (#31)."""

from riders.pricing import strength

VALUE_AT_MIN_STRENGTH: int
VALUE_AT_MAX_STRENGTH: int
_STRENGTH_EXPONENT = 2.0      # same as riders.pricing, deliberately
_PEAK_VALUE_AGE = 23
_HORIZON_AT_MAX_AGE = 0.15
_MIN_AGE = 18                 # duplicated from riders/models.py validators,
_MAX_AGE = 40                 # same self-containment reasoning as riders/pricing.py

def _round_to_nearest_1000(value: float) -> int: ...

def career_horizon(age: int) -> float:
    """1.0 at or below _PEAK_VALUE_AGE, falling linearly to
    _HORIZON_AT_MAX_AGE at _MAX_AGE. Monotonic, unlike
    riders.pricing.age_multiplier — see the plan's D2/D3."""

def market_value_for(rider) -> int:
    """This rider's market value in whole credits. Pure: no database
    access, safe on an unsaved Rider."""
```

`career_horizon` must clamp: an age below `_PEAK_VALUE_AGE` returns 1.0
exactly, and the linear fall is clamped to `[_HORIZON_AT_MAX_AGE, 1.0]` so
an out-of-range age (the model validates 18-40, but the function is pure and
may be called on anything) cannot produce a negative or >1 multiplier.

## `api/serializers.py`

`RiderSerializer` gains one field, following the `staff` precedent at
line 241:

```python
market_value = serializers.SerializerMethodField()

def get_market_value(self, instance) -> int:
    return market_value_for(instance)
```

Import at module scope: `from transfers.pricing import market_value_for`.
`api/` may import anything (`AGENTS.md`).

A new `RosterSerializer` wraps the list and the total:

```python
class RosterSerializer(serializers.Serializer):
    riders = RiderSerializer(many=True)
    squad_value = serializers.IntegerField()
```

Note `weekly_salary` stays `serializers.IntegerField()` — it is a stored
column. Only `market_value` is computed. Do not convert one to match the
other.

## `api/views.py`

`RiderListView.get` becomes:

```python
riders = list(Rider.objects.filter(team=team))
return Response(RosterSerializer({
    "riders": riders,
    "squad_value": sum(market_value_for(r) for r in riders),
}).data)
```

`list(...)` is load-bearing: without it the queryset is evaluated twice —
once for the sum, once for serialization — which is two queries and, worse,
two chances to read different data.

The 403 branch for a manager-less user is unchanged.

## `frontend/src/api.ts`

`Rider` gains `market_value: number`. `getRiders` changes its return type
and unwraps the envelope:

```ts
export interface Roster {
  riders: Rider[]
  squad_value: number
}

export async function getRiders(): Promise<Roster>
```

## `frontend/src/useRoster.ts`

`RosterState` gains `squadValue: number | null`, set from the envelope.
The null-while-loading discipline the file already documents is kept —
do not default it to 0, which would render `$0` as though it were real.

## `frontend/src/screens/Roster.tsx`

Three changes:

1. The squad-value total in the screen header, formatted with
   `formatMoney`, labelled "Squad value".
2. `market_value` in the rider card's facts grid (near line 261, beside the
   existing `['Salary', ...]` entry), as `['Value', formatMoney(rider.market_value)]`.
   No `/wk` suffix — it is a capital sum, not a rate.
3. `'market_value'` added to `SortKey` and a `{ key: 'market_value', label: 'Value' }`
   entry in the sort options at line 38, so the roster can be sorted by it
   the same way it sorts by salary.

## Work items

### W1 — `transfers/`: scaffold the app [done]
Create `transfers/__init__.py`, `transfers/apps.py` (`TransfersConfig`),
`transfers/migrations/__init__.py`, `transfers/tests/__init__.py`, and
`transfers/README.md`. Add `"transfers"` to `LOCAL_APPS` in
`config/settings/base.py`, after `"teams"` (the app it is closest to in the
dependency graph). No models, no migration file.
**Test:** none of its own; `.venv/bin/python -m pytest` must still collect
and pass, proving the app is installed without breaking the suite.

### W2 — `transfers/pricing.py`: the valuation function [done]
Implement `career_horizon` and `market_value_for` per the module sketch
above, with the constants left at a first guess — W3 calibrates them.
**Test:** `transfers/tests/test_pricing.py`, mirroring
`riders/tests/test_pricing.py`'s structure with an in-memory `_rider(**attrs)`
helper (no database):
- `test_stronger_rider_is_worth_more`
- `test_value_reads_speciality_weighting` — the CLIMBER/SPRINTER mirror
  pair from the salary tests, proving `strength()` is actually used
- `test_younger_rider_is_worth_more_at_equal_ability` — **the load-bearing
  test for D2/D3.** A 22-year-old and a 30-year-old with identical
  attributes; the younger must be worth strictly more. This is the test
  that fails if someone reuses `riders.pricing.age_multiplier`, because
  that function returns 1.0 for both 24-32 and *penalises* 22.
- `test_value_falls_monotonically_with_age` — value at 23, 28, 33, 38 is
  strictly decreasing after the peak
- `test_declined_veteran_is_worth_very_little` — floor attributes at age 39
  produces a small but non-negative int (D8)
- `test_result_is_a_whole_credit`
- `test_no_hidden_trait_is_read` — **the D9 guard.** Build two riders with
  identical visible fields but different `potential`, `peak_age` and
  `decline_rate`; assert equal value.

### W3 — `transfers/pricing.py`: calibrate the constants [done]
Tune `VALUE_AT_MIN_STRENGTH` and `VALUE_AT_MAX_STRENGTH` by sampling
`riders.generation.generate_rider`, exactly as `riders/tests/test_pricing.py`
does — not by reasoning about the 1-100 range.
**Test:** two calibration tests in the same file, seeded `random.Random`,
3000 riders:
- `test_average_value_is_about_one_season_of_wages` — mean value within
  ~15% of `mean(weekly_salary) × 12`. This is the D4 anchor.
- `test_generated_roster_value_spans_wider_than_salary` — the p95/p5 ratio
  of value exceeds that of salary over the same population, proving the
  age skew actually widens the spread rather than just rescaling it.

### W4 — `api/`: serialize value and the squad total [done]
Add `market_value` to `RiderSerializer`, add `RosterSerializer`, rewrite
`RiderListView.get` per the sections above.
**Test:** `api/tests.py`:
- `test_roster_includes_market_value_per_rider`
- `test_roster_includes_squad_value_total` — asserts the total equals the
  sum of the per-rider values in the same response, not a recomputation
- `test_roster_still_requires_a_team` — the 403 branch is unchanged
- `test_roster_response_has_no_hidden_traits` — extend or assert alongside
  whatever existing test guards the payload keys

### W5 — `frontend/`: consume the envelope and render value
`api.ts`, `useRoster.ts` and `Roster.tsx` per the sections above, **in one
commit** (D6 — the API shape changed).
**Test:** `frontend/src/screens/Roster.test.tsx`:
- a rider's value renders, `$`-formatted
- the squad total renders in the header
- sorting by Value orders the roster correctly
Update whatever fixture the existing tests use to the new envelope shape.

### W6 — Documentation
`transfers/README.md` (new, written in W1 but completed here with the real
decisions), `riders/README.md`, `AGENTS.md`, `api/README.md`,
`frontend/README.md`. See *Documentation update*.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6.

- **W1 first** because everything else needs the app to exist and be
  installed; it lands alone so a failure there is unambiguous.
- **W2 before W3** because the tests must exist before the constants they
  pin are tuned — writing the calibration first means tuning against
  nothing.
- **W3 before W4** so the API ships numbers that are already right; a
  reviewer looking at the endpoint sees final values, not placeholders.
- **W4 before W5** because the frontend consumes the envelope the backend
  defines. Commit W4 and W5 separately but land them together — between
  them the repo has a backend the frontend does not match, so do not stop
  for the day at W4.
- **W6 last**, once what was actually built is known.

Each work item is one reviewable commit. The suite must be green at every
one.

## Documentation update (required, not optional)

- **`transfers/README.md` (new).** The app's first content. Sections: *What
  this app owns* (a valuation function, no models — and why that is
  deliberate); *Value vs salary* (D2 — shared `strength()`, separate age
  curves, and the warning against expressing one as a multiple of the
  other); *Never a hidden trait* (D9, pointing at `riders/README.md`'s
  *Visible vs hidden*); *Calibration* (D4, and that retuning means
  re-running the calibration tests, not eyeballing constants); *What
  `transfers/` may import* (`riders/` only); *Future work* — the consumers
  this number was built for: #28 reserve price, #30 AI bidding, #27 forced
  sales, #26 renegotiation.
- **`riders/README.md`.** In *Salary*, a short note that a second price now
  exists in `transfers/`, reusing `strength()` but not `age_multiplier`,
  and that a change to `strength()` moves both prices.
- **`AGENTS.md`.** Flip `transfers/` from *not yet* to **built**, `README.md`
  in the domain table with a one-line description. Add `transfers -> riders`
  to the dependency-direction block.
- **`api/README.md`.** Note the roster endpoint's envelope change and the
  `market_value` field.
- **`frontend/README.md`.** Note the roster screen shows value and squad
  total, if it enumerates screens' content.

## Verification

Unit tests first:

```bash
/home/mario/dev/cycling-manager/.venv/bin/python -m pytest
```

Then end to end, from the worktree:

```bash
/home/mario/dev/cycling-manager/.venv/bin/python scripts/dev_db.py
/home/mario/dev/cycling-manager/.venv/bin/python manage.py migrate
/home/mario/dev/cycling-manager/.venv/bin/python manage.py seed_user
/home/mario/dev/cycling-manager/.venv/bin/python manage.py seed_teams --claim-for test@mail.com
/home/mario/dev/cycling-manager/.venv/bin/python manage.py runserver
```

Log in as `test@mail.com` / `123456789`, open Roster, and check:

1. Every rider shows a value, `$`-formatted with thousands separators.
2. The squad total equals the sum of the visible per-rider values.
3. Sorting by Value works and differs from sorting by Salary — **if the two
   orderings are identical across a twelve-rider roster, the age skew is not
   doing anything**, which is the headline failure mode.

**The likeliest failure mode is D2 done wrong** — reusing
`riders.pricing.age_multiplier`, or deriving value as a multiple of salary.
Either produces a plausible-looking number that is wrong in exactly the way
the feature exists to avoid. The check that catches it is
`test_younger_rider_is_worth_more_at_equal_ability`: with salary's symmetric
curve, a 22-year-old and a 30-year-old of equal ability come out with the
22-year-old *cheaper*, so the assertion fails. A passing version of that
test could not have passed under the wrong implementation, which is what
makes it evidence rather than decoration.

For the calibration tests, the evidence is the *ratio*, not the absolute
number — a test asserting `value > 0` would pass under any implementation
and proves nothing.

## Risks

| Risk | Mitigation |
|---|---|
| Reader reuses `riders.pricing.age_multiplier` for value, flattening the age skew | D2/D3 state it explicitly; `test_younger_rider_is_worth_more_at_equal_ability` fails loudly if they do |
| Reader adds a stored `market_value` column to enable a SQL aggregate | D7 and *Data model* forbid it; value must move when attributes move, and a column caches staleness |
| Envelope change (D6) lands without the frontend, leaving `getRiders().map` broken | W4 and W5 land together; execution order says not to stop between them |
| Calibration drifts and value stops meaning "about a season of wages" | `test_average_value_is_about_one_season_of_wages` pins it; it fails rather than silently rebalancing |
| A hidden trait sneaks into the formula via a future edit | `test_no_hidden_trait_is_read` compares two riders differing only in hidden fields |
| `transfers/` accumulates imports beyond `riders/` as later tickets land | `transfers/README.md`'s *What `transfers/` may import* section states the rule now, before there is pressure on it |
| Double queryset evaluation in the view | `list(...)` before summing; called out in the `api/views.py` section |

## Open questions

None.

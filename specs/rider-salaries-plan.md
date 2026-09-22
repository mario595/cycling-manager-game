# Rider salaries paid weekly — Implementation Plan

**Spec:** `specs/rider-salaries.md` · **Issue:** [#25](https://github.com/mario595/cycling-manager/issues/25) · **Status:** proposed
**Apps touched:** `riders/`, `economy/`, `world/`, `api/`, `frontend/`

## Context you need

Today every rider costs the same flat `WEEKLY_WAGE_PER_RIDER = 1_200`
(`economy/models.py`). `economy.services.charge_weekly_wages(week)` counts each
team's riders with a single annotated query and writes one `LedgerEntry` of
`-(rider_count × 1_200)` per team per week. It is called from
`world.services.tick()` inside the per-week loop over `WeekTransition` rows.
That loop, its exactly-once guarantees and the `(team, week)` partial unique
constraint are all correct and **stay exactly as they are** — the only thing
this feature changes is what number gets summed.

Riders live in `riders/models.py`. Attributes are stored 1-100 and shown 0-10
through `riders.display.to_display_scale` (which floors). Riders carry visible
fields (the five engine attributes, `age`, `speciality`, `freshness`) and hidden
traits (`potential`, `peak_age`, `decline_rate`, `training_affinity`,
`recovery_rate`, `growth_debt`) that are **never serialized** — see
`riders/README.md`, *Visible vs hidden*. Salary must be derived from visible
fields only; the spec is explicit that no hidden trait feeds it.

`staff/pricing.py` is the closest precedent and worth reading before you start:
a small pure module that scales a price linearly between two named constants and
rounds to the nearest 50 so prices read as prices. This plan reuses its shape
(and its `_round_to_nearest_50` idea) but **not** its storage decision — see
Design decision 1.

Riders are created in two places, both of which must produce a salary:
`riders.generation.generate_rider()` (which `generate_roster` and, through it,
`teams.services.claim_team` and the `reset_riders` command all call).

Repo rules that bind this work: `riders -> core, teams` and
`economy -> core, teams, riders, schedule` (`AGENTS.md`). `economy/` **may**
import `riders/` — that edge already exists — so unlike the trainer-salary case
there is no need to inject a map from `world/`. Tests are pytest, run with the
main checkout's interpreter:
`/home/mario/dev/cycling-manager/.venv/bin/python -m pytest`.

## Goal

When this is done:

1. Every `Rider` has a stored `weekly_salary` in whole credits, set at
   generation and backfilled for every existing rider.
2. The salary is computed from visible attributes and age only, and spans
   roughly a 10x range between a weak rider and a strong one.
3. `charge_weekly_wages` debits each team the **sum of its riders' actual
   salaries** instead of a flat per-head rate, keeping every existing
   exactly-once and dating guarantee untouched.
4. The roster screen shows each rider's weekly salary; the Finances screen
   shows the team's total weekly wage bill.
5. A twelve-rider generated roster still costs roughly 14,400/week on average,
   so `STARTING_BALANCE` and the merchandise tuning stay valid.

## Design decisions (settled — implement these, do not substitute)

**1. Salary is a stored field on `Rider`, not derived on read.**
This is the opposite of `staff/pricing.py`, which derives a trainer's salary
from their speciality score every time and stores nothing. Do not copy that here.
The spec requires a salary to be **frozen for the season** while the rider's
attributes keep moving every single week through the age curve (#58) and
training (#36). A derived salary would silently change every week — exactly the
behaviour the spec's *Out of scope* rules out. Storage is what makes "frozen"
mean anything. **Load-bearing.**

**2. The pricing function is pure and lives in `riders/pricing.py` (new).**
`weekly_salary_for(rider) -> int` takes a rider-like object and returns whole
credits. It touches no database and imports nothing but the constants it needs,
so it is testable against a hand-built unsaved `Rider()`. Same shape as
`staff/pricing.py`. The *field* stores the result; the *function* is the single
place the formula lives, so backfill, generation and any later recomputation all
agree by construction.

**3. The price is driven by a speciality-weighted "strength", not a flat mean of
five attributes.** A Climber with 70 climb and 30 sprint is a better rider than
one with 50 across the board, and a flat mean prices them identically. Reuse
`generation.SPECIALITY_PROFILES` — already the source of truth for what each
speciality values — to weight the five attributes, then divide by the profile's
weight sum (~5.0) to get a 1-100 strength figure. This also means importing
`SPECIALITY_PROFILES` from `generation.py` into `pricing.py`; that is an
intra-app import and fine. Do **not** define a second weighting table.

**4. Age is a multiplier on strength, not an additive term.** A 32-year-old and a
22-year-old at the same strength are worth the same *now*, which is the spec's
decision; but a rider at the very edges of the age range is worth somewhat less
in practice — a 19-year-old is unproven, a 36-year-old is a short-term asset.
Apply a mild multiplier peaking across the prime years and tapering at both
ends, bounded so it never swings the price more than about ±15%. Keep it mild:
the spec's decision is that visible strength dominates, and a strong age term
would start to look like the hidden-potential pricing the spec rejected.
**Do not read `peak_age`** — it is a hidden trait. Use the literal `age` field
and fixed constants.

**5. The 10x spread comes from an explicit floor and an exponent, verified by a
test, not from hoping the arithmetic lands there.** Define
`SALARY_AT_MIN_STRENGTH` and `SALARY_AT_MAX_STRENGTH` as named constants whose
ratio *is* the intended spread, and interpolate between them non-linearly so the
curve is convex — a rider at strength 70 should cost much more than twice a
rider at 35, because the top of the range is where scarcity lives. A plain
linear interpolation between a floor and a ceiling gives a compressed middle and
is the natural wrong first attempt. Pin the resulting spread with an assertion in
`riders/tests/test_pricing.py`.

**6. Calibrate against generated riders, not against the theoretical range.**
The 1-100 attribute range is not where riders actually live:
`generation.QUALITY_SPREAD` tops out at quality 55 and `_MAX_STARTING_ATTRIBUTE`
caps a starting attribute at 74. A formula calibrated so that "strength 100 costs
10x strength 10" will, in practice, produce a roster clustered in a narrow band
near the bottom and the 10x spread will never be observed by a player.
**Calibrate the constants so that a generated roster's cheapest and most
expensive riders differ by roughly 10x**, and prove it with a seeded test over a
few hundred generated riders (W2). This is the single most likely thing to get
wrong. **Load-bearing.**

**7. Average cost is pinned by a test, not by judgement.** The spec requires an
average twelve-rider roster to still cost roughly 14,400/week. Write a seeded
test asserting the mean generated salary sits within a stated tolerance of
`WEEKLY_WAGE_PER_RIDER` (1,200). Tune the constants until it passes. Without
this test the feature silently rebalances the economy, which the spec forbids.

**8. `charge_weekly_wages` aggregates in the database, not in Python.** Replace
the `Count("riders")` annotation with `Sum("riders__weekly_salary")`. Keep the
`rider_count` annotation too — the field exists on `LedgerEntry`, the Finances
screen may use it, and dropping it would be an unrelated change. A team with no
riders yields `None` from `Sum`, not 0; coalesce it. That `None` is the specific
bug this decision exists to pre-empt — spec item 9 requires a zero-amount entry,
and an uncoalesced `None` raises instead.

**9. `WEEKLY_WAGE_PER_RIDER` stays, repurposed as the calibration target.** Do
not delete it. It is referenced by `STARTING_BALANCE`'s explanatory comment and
is the anchor the average-cost test asserts against. Update its docstring to say
it is no longer charged per rider but is the average a generated rider costs.

**10. No recomputation at the season boundary in this ticket.** `advance_ages()`
runs at a season close (`world/services.py`) and is the obvious hook for
re-pricing. Do not add one. The spec's *Out of scope* assigns what happens at a
season boundary to #26, and a silent automatic repricing would pre-empt that
ticket's decision about whether a manager can refuse a new salary.

**11. Salary is exact on screen, never mapped to the display scale.**
`to_display_scale` is for 1-100 attributes. A salary is money and renders through
the frontend's existing `formatMoney` with the `$` prefix (`AGENTS.md`,
*Displaying game money*). A rounded-for-display salary would not sum to the
charged bill and reads as a bug.

## Data model

### `riders.Rider.weekly_salary` (new field)

| Property | Value |
|---|---|
| Type | `PositiveIntegerField` |
| Null / blank | `null=False`, `blank=False` |
| Default | `1200` |
| Validators | `MinValueValidator(1)` |
| Index | none |
| Constraint | none |

`PositiveIntegerField`, not `PositiveSmallIntegerField`: small tops out at 32767
and a top-end salary under a future rebalance could plausibly exceed that.
Whole credits, never `Decimal` — the ledger is `BigIntegerField`
(`economy/README.md`).

The `default=1200` exists so the migration can add the column without a
`default` prompt and so a hand-built `Rider()` in a test is valid; it is **not**
the real value for any rider. Generation overwrites it and W3's data migration
backfills it. Help text must say so, and must say the value is set at creation
and frozen until #26.

### Migrations

- `riders/migrations/0007_rider_weekly_salary.py` — schema, adds the column.
- `riders/migrations/0008_backfill_rider_salaries.py` — data migration, W3.
  Separate file: a schema migration and a data migration in one file cannot be
  reasoned about or reverted independently.

No `economy/` migration. `LedgerEntry` is unchanged — the wage row keeps the
same `kind`, `week`, `rider_count` and `description`; only its `amount` is
computed differently.

## `riders/pricing.py` (new)

```python
"""What a rider costs per week. Derived from visible attributes and age
only — never from a hidden trait. Stored on the rider at creation (see
specs/rider-salaries-plan.md, Design decision 1), not recomputed on read."""

from .generation import SPECIALITY_PROFILES
from .models import ENGINE_ATTRIBUTES

SALARY_AT_MIN_STRENGTH: int
SALARY_AT_MAX_STRENGTH: int
_STRENGTH_EXPONENT: float
_PRIME_AGE_LOW: int
_PRIME_AGE_HIGH: int
_AGE_PENALTY_MAX: float


def strength(rider) -> float:
    """A rider's 1-100 overall level, weighting each attribute by what their
    speciality values. Uses SPECIALITY_PROFILES so there is exactly one
    weighting table in the app."""


def age_multiplier(age: int) -> float:
    """Mild multiplier, 1.0 across the prime years and tapering at both ends.
    Reads `age` only — never `peak_age`, which is hidden."""


def weekly_salary_for(rider) -> int:
    """This rider's weekly salary in whole credits. Pure: no database
    access, safe on an unsaved Rider."""
```

`weekly_salary_for` composes the three: interpolate
`SALARY_AT_MIN_STRENGTH → SALARY_AT_MAX_STRENGTH` across the strength range
raised to `_STRENGTH_EXPONENT`, multiply by `age_multiplier`, round to the
nearest 50 (copy `staff/pricing.py`'s `_round_to_nearest_50` — duplicating four
lines is correct here; `riders/` must not import `staff/`, which is not in its
dependency list), and clamp to at least `SALARY_AT_MIN_STRENGTH`.

## `riders/generation.py`

`generate_rider()` gains one line before the `return`: compute the salary and
pass it to the `Rider(...)` constructor. It must be computed from the rolled
attributes and age, so build the `Rider` first or compute strength from the
local `attributes` dict and `age` directly — either is fine, but the salary must
reflect *this* rider, not the defaults.

Import `weekly_salary_for` at module scope. `pricing.py` imports from
`generation.py` (`SPECIALITY_PROFILES`) and `generation.py` would then import
from `pricing.py` — **that is a circular import and it will fail.** Break it by
having `pricing.py` import `SPECIALITY_PROFILES` and `generation.py` import
`weekly_salary_for` *inside* `generate_rider`'s body, or — cleaner, and the
recommended fix — move `SPECIALITY_PROFILES` nowhere and instead have
`generation.py` do the function-body import. Do not move the profiles table;
`generation.py` is its home and `riders/README.md` says so.

## `economy/services.py`

```python
def charge_weekly_wages(week) -> int:
    totals = Team.objects.annotate(
        n=Count("riders"),
        payroll=Coalesce(Sum("riders__weekly_salary"), 0),
    ).values_list("pk", "n", "payroll")
    for team_id, rider_count, payroll in totals:
        with transaction.atomic():
            try:
                LedgerEntry.objects.create(
                    team_id=team_id,
                    kind=LedgerEntry.Kind.WAGES,
                    amount=-payroll,
                    occurred_at=week.starts_at,
                    week=week,
                    rider_count=rider_count,
                    description="Weekly wages",
                )
```

Everything else in the function — the per-create `transaction.atomic()`, the
`IntegrityError: continue`, the `written` counter, charging every team including
unmanaged and empty ones — is unchanged. `Coalesce(..., 0)` is what makes an
empty roster write `amount=0` instead of raising on `None`.

Add a `payroll_for(team) -> int` helper alongside it, returning the same sum for
one team, for the API's wage-bill tile. `Count` and `Sum` in one `annotate` over
the same join is safe here because `riders` is a single reverse FK — there is no
second multi-valued join to fan out against.

## `api/serializers.py` and `api/views.py`

- `RiderSerializer` gains `weekly_salary = serializers.IntegerField()`. It is a
  visible field: pass it straight through, do **not** route it through
  `_display_scale_attributes`.
- `SquadRiderSerializer` does **not** gain it (spec's *Out of scope*).
- `FinancesSerializer` gains `weekly_wage_bill = serializers.IntegerField()`,
  and `FinancesView.get` populates it from `payroll_for(team)` — and returns
  `0` in the no-team branch alongside the other zeros.

## `frontend/`

- `api.ts`: `Rider` gains `weekly_salary: number`; the `Finances` response type
  gains `weekly_wage_bill: number`.
- `screens/Roster.tsx`: show the salary per rider via `formatMoney`. Add
  `'weekly_salary'` to `SortKey` and `SORT_OPTIONS` labelled "Salary" — the
  existing numeric sort branch (`b[sort] - a[sort]`) already handles it, so this
  is two array entries and a type union member.
- `screens/Finances.tsx`: a `StatTile` for the weekly wage bill beside the
  existing balance and fanbase tiles, via `formatMoney`.

## Work items

### W1 — `riders/pricing.py` + `riders/tests/test_pricing.py`: the formula ✅
New module per the signatures above, with constants named and documented. No
model change yet, nothing calls it.
**Tests** (`riders/tests/test_pricing.py`): a stronger rider costs more than a
weaker one of the same speciality; two riders of different specialities whose
attributes match their profile equally well cost the same (mirrors
`staff/tests/test_pricing.py::test_salary_scales_with_speciality`); the return is
an `int`; a rider with floor attributes still costs at least
`SALARY_AT_MIN_STRENGTH`; `weekly_salary_for` touches no database (call it on an
unsaved `Rider()` with no `db` fixture).

### W2 — `riders/tests/test_pricing.py`: calibration ✅

Landed with W1 in the same commit and the same file — the plan lists them
separately, but the formula was calibrated (constants tuned against sampled
`generate_rider` output, per Design decision 6) before it was written, so
splitting the commit would have meant reverting and rewriting the same
constants. `SALARY_AT_MIN_STRENGTH = 100`, `SALARY_AT_MAX_STRENGTH = 10_000`,
`_STRENGTH_EXPONENT = 2.0` — over a 3000-rider seeded sample these land the
p95/p5 spread at ~10x and the mean within ~2% of `WEEKLY_WAGE_PER_RIDER`
(1,200), both asserted in `test_generated_roster_spans_roughly_tenfold` and
`test_generated_roster_average_matches_flat_wage`.
**Load-bearing — this is where the feature is actually tuned.** Two seeded tests
over a generated population (a few hundred riders via `generate_rider(rng=...)`):
the mean salary is within ±10% of `WEEKLY_WAGE_PER_RIDER`; the ratio of the 95th
percentile to the 5th percentile is roughly 10x (assert a band, e.g. 7x–13x, not
an exact figure). Tune W1's constants until both pass. Import
`WEEKLY_WAGE_PER_RIDER` from `economy.models` — `riders/` may not import
`economy/` in library code, but a **test** importing it is fine; if that sits
badly, hard-code 1200 with a comment naming the constant it tracks.

### W3 — `riders/models.py` + two migrations: the stored field ✅
Add `weekly_salary` per the Data model section. Generate the schema migration.
Then hand-write `0008_backfill_rider_salaries.py`: a `RunPython` that iterates
existing riders, computes `weekly_salary_for`, and `bulk_update`s in batches.
**The data migration must not import `riders.pricing` at module scope from
within the migration and call it on a historical model** — `apps.get_model`
returns a historical `Rider` without custom methods, but `weekly_salary_for` only
reads plain fields, so passing a historical instance to it works. Import it
inside the `RunPython` function. Give it a no-op reverse (`RunPython.noop`).
**Tests** (`riders/tests/test_models.py`): the field defaults to 1200 and
rejects 0. Migration behaviour is proven by W6's end-to-end check rather than a
migration test — this repo has no migration-test harness and adding one is out
of scope.

### W4 — `riders/generation.py`: price riders at creation ✅
Set `weekly_salary` in `generate_rider`, breaking the circular import as
described above.
**Tests** (`riders/tests/test_generation.py`): a generated rider's
`weekly_salary` equals `weekly_salary_for(rider)`; it is never the bare default
for a rider whose attributes are not default; a seeded `generate_roster(12)`
produces a spread of distinct salaries.

### W5 — `economy/services.py`: charge the real payroll
Rewrite `charge_weekly_wages` per the section above and add `payroll_for`.
**Tests** (`economy/tests/test_wages.py`): the existing tests reference
`WEEKLY_WAGE_PER_RIDER` and will fail — update them. A team of three riders with
known differing salaries is charged exactly their sum; a team with no riders is
charged an entry with `amount == 0` **and that entry exists** (this is the
`Coalesce` guard, and the existing zero-roster test should already cover the
existence half); the `(team, week)` constraint still makes a second call a no-op;
`rider_count` is still populated.
Also update `world/tests/test_tick.py`, which asserts
`entry.amount == -(len(riders) * WEEKLY_WAGE_PER_RIDER)`.

### W6 — `api/`: serialize salary and the wage bill
`RiderSerializer`, `FinancesSerializer`, `FinancesView` per the section above.
**Tests** (`api/tests.py`): the riders endpoint includes `weekly_salary` and it
matches the stored value; it does **not** include any hidden trait (extend the
existing hidden-trait assertion rather than writing a new one); the finances
endpoint returns `weekly_wage_bill` equal to the roster's salary sum, and `0`
for a user with no team.

### W7 — `frontend/`: show it
`api.ts` types, the Roster column and sort option, the Finances tile.
**Tests**: `frontend/src/screens/Roster.test.tsx` — a rider's salary renders
formatted with the `$` prefix, and sorting by Salary reorders the list.
`frontend/src/screens/Finances.test.tsx` — the wage bill tile renders.
Both files exist; extend them.

### W8 — documentation
Per the section below. Its own commit.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7 → W8.

W1 and W2 come first and together because the formula and its calibration are
the feature; everything after is plumbing, and plumbing built against an
un-calibrated formula gets rebuilt. Stop and commit after W2 — at that point the
pricing module is provably correct in isolation with nothing depending on it yet.

W3 before W4 because generation cannot set a field that does not exist. W3's
backfill leaves the repo green and every rider correctly priced even though
nothing reads the field yet.

W5 is the first item that changes player-visible behaviour, and it is the one
that can break the tick. It comes after the data is known-good so that a failure
there is unambiguously the aggregation, not the pricing.

W6 and W7 are additive and safe. W8 last, describing what was actually built.

Commit after each work item.

## Documentation update (required, not optional)

- **`riders/README.md`** — a new `## Salary` section: that every rider carries a
  stored `weekly_salary`, that it is derived from visible attributes and age
  only (and why no hidden trait may ever feed it), that it is frozen once set
  and #26 owns what changes at a season boundary, and that `pricing.py` is the
  single home of the formula. Add a line to *Visible vs hidden* listing
  `weekly_salary` among the visible fields. Update *Future work* to point
  repricing at #26.
- **`economy/README.md`** — update *Wages run off week transitions* to say the
  wage bill is now the sum of each team's riders' salaries, and that the
  `Coalesce` is what keeps an empty roster at a real zero row. Remove
  **Per-rider salaries** from *Future work* — it is done. Update
  `WEEKLY_WAGE_PER_RIDER`'s description to "the average a generated rider
  costs", not "the flat wage".
- **`api/README.md`** — note `weekly_salary` on the rider payload and
  `weekly_wage_bill` on finances.
- **`frontend/README.md`** — note the Roster salary column and sort, and the
  Finances wage-bill tile.
- **`AGENTS.md`** — the `economy/` row currently ends "…and rider salaries still
  to come." Remove that clause. The `riders/` row should mention salary.

## Verification

```bash
cd /home/mario/dev/cycling-manager/.claude/worktrees/rider-salaries
/home/mario/dev/cycling-manager/.venv/bin/python scripts/dev_db.py
/home/mario/dev/cycling-manager/.venv/bin/python manage.py migrate
/home/mario/dev/cycling-manager/.venv/bin/python -m pytest
cd frontend && npm test
```

Then a real world, which is what proves the backfill and the tick together:

```bash
/home/mario/dev/cycling-manager/.venv/bin/python manage.py seed_user
/home/mario/dev/cycling-manager/.venv/bin/python manage.py seed_teams --claim-for test@mail.com
/home/mario/dev/cycling-manager/.venv/bin/python manage.py seed_trainers
/home/mario/dev/cycling-manager/.venv/bin/python manage.py load_season seasons/season-1.example.json
GAME_CLOCK_CLASS=world.clocks.MockClock /home/mario/dev/cycling-manager/.venv/bin/python manage.py mock_clock set <season start>
GAME_CLOCK_CLASS=world.clocks.MockClock /home/mario/dev/cycling-manager/.venv/bin/python manage.py tick
```

**The likeliest failure mode is Design decision 6: a formula that is arithmetically
correct but produces a roster where every rider costs nearly the same**, because
generated attributes occupy a narrow band well below the 1-100 range the constants
were reasoned about. W2's percentile-ratio test is the check that catches it, and
it must be written to fail loudly — run it once with a deliberately linear
interpolation and confirm it *does* fail, otherwise it proves nothing.

The second check that matters: after `tick`, open the Finances screen and confirm
the wage entry's amount equals the sum of the salaries shown on the Roster screen.
If those two disagree the aggregation is wrong, and no unit test will tell you
because both sides would be computed from the same helper. Add the numbers by hand
once.

Third: confirm a team with zero riders still gets a wage row at `amount = 0`
rather than no row (query `LedgerEntry` for an unmanaged team with no roster).

## Risks

| Risk | Mitigation |
|---|---|
| Circular import between `generation.py` and `pricing.py` | Known and called out in the `generation.py` section — function-body import in `generate_rider`. It will fail immediately and loudly at import time, so it cannot ship silently. |
| Formula calibrated against 1-100 instead of the band riders actually occupy, collapsing the spread | W2's seeded percentile test over generated riders, not over the theoretical range. Design decision 6. |
| `Sum` returns `None` for an empty roster and `amount=-None` raises | `Coalesce(Sum(...), 0)`. Spec item 9 requires the zero row; W5's test asserts the row exists with `amount == 0`. |
| The feature silently rebalances the economy | W2's mean-salary test pinned to `WEEKLY_WAGE_PER_RIDER`. |
| Data migration misses riders, leaving some at the 1200 default | The default is a valid salary, so nothing crashes — it fails silently. Verification step: after migrating a seeded world, assert no rider's salary is exactly 1200 unless its computed value is (`Rider.objects.exclude(weekly_salary=F(...))` is not expressible; spot-check a handful on the Roster screen instead). |
| Someone later "helpfully" reprices at the season boundary | Design decision 10 says why not, and `riders/README.md` must record it (W8). |
| A hidden trait creeps into the formula during tuning | `pricing.py` reads only `ENGINE_ATTRIBUTES`, `speciality` and `age`. W6's test asserts no hidden trait is serialized; the formula's inputs are a code-review check. |

## Open questions

None.

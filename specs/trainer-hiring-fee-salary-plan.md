# Trainer hiring fee and recurring salary — Implementation Plan

**Spec:** `specs/trainer-hiring-fee-salary.md` · **Issue:** #69 · **Status:** proposed
**Apps touched:** `staff/`, `economy/`, `world/`, `api/`, `frontend/`

## Context you need

Trainers already exist and are free. `staff.Trainer` is a row in a shared pool
with five 1-100 skills (`climb`, `sprint`, `flat`, `resistance`,
`positioning`) and a nullable `OneToOneField` to `teams.Team` — `team = None`
means unemployed. `staff.services.hire_trainer` / `fire_trainer` move a trainer
in and out of a team's single slot; `hire_trainer` locks the row with
`select_for_update()` (no `skip_locked`) and re-checks `team_id is None`
**after** taking the lock. That re-check is the app's one genuinely concurrent
operation — read `staff/README.md`, *The pool is shared, and hiring is
contended*, before touching it.

`Trainer.speciality` is a **derived property**, not a column:
`max(ENGINE_ATTRIBUTES, key=...)`. Generation guarantees exactly one clear
maximum by drawing the speciality from 70-95 and the other four from 25-64 —
non-overlapping bands, so there is never a tie (`staff/generation.py`).
Skills never change after generation, which is what makes a price derived from
them stable for the trainer's whole life.

`economy/` is the append-only ledger: a team's balance is
`Sum(LedgerEntry.amount)`, never a stored column, and `amount` is a signed
integer (income positive, spending negative). Read `economy/README.md`, *The
ledger is append-only* — a cached balance column is forbidden. `LedgerEntry`
currently has four kinds: `starting_balance`, `wages`, `takeover`,
`merchandise`. Weekly money runs off week transitions:
`world.services.tick()` loops over `WeekTransition` rows **one week at a time**
and calls `charge_weekly_wages(week)`, `apply_weekly_fanbase(...)` and
`pay_merchandise(week)` inside that loop, each dating its row to
`week.starts_at` (never `now()`). Exactly-once comes from the `WeekTransition`
row; a `(team, week)` partial unique constraint per kind is the second line of
defence, with each write in its own `transaction.atomic()` and `IntegrityError`
caught and skipped — an `IntegrityError` poisons an enclosing transaction in
Django.

Player-facing money is prefixed `$` and thousands-separated, never decimal
(`AGENTS.md`, *Displaying game money*). Fanbase and other counts get no symbol.
`frontend/src/screens/Finances.tsx` has a local `formatMoney` helper this work
needs to reuse.

Repo rules this work is bound by: `staff -> core, teams, riders` plus a
string-only `schedule.Week` FK, and **`staff/` must never import `economy/`**;
`economy -> core, teams, riders, schedule`, and it must not import `staff/`.
Only `world/` and `api/` may know about everything. See `AGENTS.md`,
*Dependency direction* — Design decision 2 below is entirely about obeying this.

## Goal

When this is done:

- Every trainer has a hire fee and a weekly salary derived from their
  speciality score, visible in the API and on the Staff screen before hiring.
- Hiring debits the fee atomically with the hire, and is refused when the
  team's balance will not cover it.
- Each week the slot is filled, the team is charged the trainer's salary as its
  own `trainer_salary` ledger row, distinct from `wages`.
- A team with no trainer gets no salary row at all for that week.
- Firing stops future salary rows and refunds nothing.
- A salary charge can take a balance negative; nothing reacts to that yet.

## Design decisions (settled — implement these, do not substitute)

**1. Price is a pure function of the speciality score, living in `staff/`.**
Add `staff/pricing.py` with `hire_fee(trainer)` and `weekly_salary(trainer)`,
both reading `getattr(trainer, trainer.speciality)`. Pure functions over a
model instance, no new columns. **Do not add `fee` / `salary` fields to
`Trainer`.** Stored prices would be a second source of truth that can drift
from the skills they are derived from, would need a data migration to
backfill, and would let someone "rebalance" prices and silently change what
already-employed trainers cost — which spec item 11 forbids. Derivation is
free here precisely because skills are immutable after generation.

**2. `staff/` must not import `economy/`, so `world/` and `api/` compose them.**
This is the load-bearing architectural constraint. `AGENTS.md` gives
`staff -> core, teams, riders`; `economy/` is not on that list and `staff/`
has no entry-point exception like `teams/`'s. Therefore:

- `staff.services.hire_trainer` gains an **injected callback**, not an
  `economy` import (see Design decision 3);
- the weekly salary charge lives in **`economy/services.py`** as
  `charge_trainer_salaries(week, *, salary_by_team)`, taking the salaries as a
  plain dict — `economy/` may not import `staff/` either;
- `world.services.tick()` is the only place that knows both sides, building
  the dict from `staff/` and handing it to `economy/`.

This is exactly the inversion `apply_weekly_fanbase(week, *, points_by_team)`
already uses for `competitions/` — copy that shape. **Do not** add an
`economy` import to `staff/`, and **do not** reach for the lazy
function-body-import exception `teams/` has: that exception exists to break a
genuine import cycle in `claim_team`, and `AGENTS.md` calls it "an exception
that proves the rule". There is no cycle here, so the injection is the correct
tool.

**3. The fee is debited inside `hire_trainer`'s existing transaction, via an
injected `charge` callback.** Signature becomes
`hire_trainer(team, trainer_id, *, charge=None)`. The callback is invoked
**after** the lock is taken and all availability checks pass, but **before**
the transaction commits, so the hire and its debit are one atomic unit — a
trainer can never end up hired without being charged, or charged without being
hired. A callback raising `InsufficientFunds` propagates out and rolls the
hire back. `charge=None` means no charge (keeps every existing test and the
seed path working unchanged).

**Do not** debit the fee in the API view after calling `hire_trainer` — a
failure between the two leaves a free trainer, and the two writes would not
share a transaction.

**4. Affordability is checked against the fee only, inside the same
transaction.** The `charge` callback computes `balance_for(team)` and raises
`InsufficientFunds` when it is below the fee. Checking inside the transaction
(rather than in the view before calling) is what stops two concurrent hires
from both passing an affordability check the balance can only satisfy once.
The weekly salary is **never** checked for affordability, at hire time or at
charge time — spec items 10 and the existing wage behaviour both require the
balance to be allowed to go negative.

**5. The salary is a new `LedgerEntry.Kind`, not a field on the `wages` row.**
`kind = "trainer_salary"` with its own `(team, week)` partial unique
constraint, mirroring `one_wage_entry_per_team_per_week` and
`one_merchandise_entry_per_team_per_week`. Spec item 7 requires a
distinguishable line, and the existing `wages` constraint already forbids a
second `wages` row per team per week, so folding staff cost in is not even
possible without changing rider-wage semantics.

**6. Teams with no trainer get no row — the deliberate asymmetry with wages.**
`charge_weekly_wages` writes an `amount = 0` row for a team with no riders "so
the history has no silent gaps". `charge_trainer_salaries` iterates only the
teams present in `salary_by_team`, so an unstaffed team gets nothing. Spec
decision: an empty staff slot is the normal long-run state for most teams,
and a weekly zero row for every one of them is noise. Note this asymmetry in
`economy/README.md` so it does not read as an oversight.

**7. Fee and salary scale together off one band, with the fee set well above
several weeks' salary.** Constants in `staff/pricing.py`. The fee must stay
large enough that firing to dodge a lean week and re-hiring later never pays —
the spec's open question, resolved here: at roughly **12× the weekly salary**,
a fire-and-rehire cycle costs twelve weeks of salary to save a few, so the fee
*is* the cooldown `fire_trainer` deliberately lacks (`staff/README.md`: "No
cooldown, no penalty"). Do not add a cooldown or severance — spec says No.

**8. Correct `STARTING_BALANCE`'s comment, do not retune the balance.**
`economy/models.py` documents 500,000 as "roughly 34 weeks" of a twelve-rider
team's wages. Adding a top-end trainer shortens that materially. Fix the
comment to state both figures; leave the constant alone — the spec did not ask
for an economy retune, and `STARTING_FANBASE`'s own comment already warns
against retuning before prize money (#19) and sponsorship (#22) land.

## Data model

No new models. No new fields on `Trainer` (Design decision 1).

**`economy/models.py`** — one new `Kind` member and one new constraint:

- `LedgerEntry.Kind.TRAINER_SALARY = "trainer_salary", "Trainer salary"`.
  Fits the existing `max_length=20` (15 characters).
- New `UniqueConstraint(fields=["team", "week"],
  condition=Q(kind="trainer_salary"), name="one_trainer_salary_per_team_per_week")`.
- `rider_count` stays `0` on these rows (its help text already says it is
  meaningful only on wages). `week` is set, `description` is
  `"Trainer salary"`.
- Fee rows: `kind = TRAINER_SALARY` is **wrong** for the upfront fee — use a
  separate `Kind.TRAINER_FEE = "trainer_fee", "Trainer hire fee"`, with
  `week = None` (it is not a weekly charge) and **no** unique constraint (a
  team can legitimately pay several hire fees over a season).

**Migration:** `economy/migrations/0003_trainer_salary_and_fee.py` — an
`AlterField` on `kind` (choices changed) plus `AddConstraint`. Choices-only
changes still need the migration; `makemigrations` will generate it.

**`world/models.py`** — one counter, matching the existing three:
`trainer_salary_entries = PositiveIntegerField(default=0, help_text="Ledger
trainer salary entries written this tick (#69).")`. Migration
`world/migrations/0008_tickrun_trainer_salary_entries.py`.

## staff/pricing.py (new)

```python
"""What a trainer costs. Derived from the speciality score, never stored —
see specs/trainer-hiring-fee-salary-plan.md, Design decision 1."""

#: Weekly salary at the bottom of the speciality band (70) and at the top
#: (95). Interpolated linearly between; a trainer's score cannot fall
#: outside _SPECIALITY_BAND, but clamp anyway so a hand-made Trainer in a
#: test cannot produce a negative salary.
SALARY_AT_MIN_SPECIALITY = 1_500
SALARY_AT_MAX_SPECIALITY = 4_500

#: The hire fee is this multiple of the weekly salary. Load-bearing: it is
#: the only thing deterring fire-and-rehire, since firing is free and has no
#: cooldown (staff/README.md). Twelve weeks is a full season, so dodging a
#: few lean weeks never pays.
FEE_WEEKS_OF_SALARY = 12


def weekly_salary(trainer) -> int: ...
def hire_fee(trainer) -> int: ...
```

Both return whole credits (`int`, never `Decimal` — the ledger is
`BigIntegerField`). Interpolate with integer arithmetic and round to the
nearest 50 so the numbers read as prices rather than as hash output.

Import nothing from `economy/` or `django.db` here — this module is pure
arithmetic over a model instance, which is what makes it trivially testable.

## staff/services.py

```python
class InsufficientFunds(StaffError):
    """The team cannot cover this trainer's hire fee."""


def hire_trainer(team, trainer_id: int, *, charge=None) -> Trainer:
```

The only change inside the existing `with transaction.atomic():` block — the
lock, the post-lock `team_id is None` re-check and the `SlotOccupied` check
are all untouched, in that order — is that immediately before
`trainer.team = team`:

```python
        # Inside the same transaction as the hire, and AFTER every
        # availability check: the debit and the hire commit together or not
        # at all. `charge` is injected because staff/ may not import
        # economy/ (AGENTS.md); world/ and api/ supply it. Raising
        # InsufficientFunds here rolls the hire back.
        if charge is not None:
            charge(team, trainer)
```

`fire_trainer` is **unchanged** — no refund, no severance, and the salary stops
simply because the next tick will not find a trainer for that team.

## economy/services.py

```python
def charge_trainer_salaries(week, *, salary_by_team: dict[int, int]) -> int:
    """Debit each team in `salary_by_team` its trainer's weekly salary for
    `week`. Returns rows written.

    Takes the salaries as a plain dict: economy/ may not import staff/
    (AGENTS.md), so world/ computes them. Same inversion
    apply_weekly_fanbase uses for competitions/.

    Only teams in the dict get a row — a team with no trainer gets nothing,
    deliberately unlike charge_weekly_wages' amount=0 rows (plan D6).
    Never checks affordability: the balance is allowed to go negative,
    exactly as wages do.
    """
```

Body follows `charge_weekly_wages` exactly: one `transaction.atomic()` per
create, `IntegrityError` caught and `continue`d, `occurred_at=week.starts_at`,
`week=week`, `amount=-salary`, `description="Trainer salary"`.

Also add, for the API to use as the injected callback:

```python
def charge_trainer_fee(team, *, amount: int, at, description: str) -> LedgerEntry:
    """Write one `trainer_fee` debit. Raises nothing — affordability is the
    caller's check (it must happen inside the hire's transaction)."""
```

## api/views.py

`HireTrainerView.post` builds the callback and maps the new failure to a 409,
alongside the existing two:

```python
        def charge(team, trainer):
            fee = hire_fee(trainer)
            if balance_for(team) < fee:
                raise InsufficientFunds(
                    f"You need ${fee:,} to hire {trainer.name}."
                )
            charge_trainer_fee(
                team, amount=-fee, at=now(),
                description=f"Hired {trainer.name}",
            )

        try:
            hire_trainer(team, serializer.validated_data["trainer_id"], charge=charge)
        except (TrainerNotAvailable, SlotOccupied, InsufficientFunds) as exc:
            return Response({"detail": str(exc)}, status=409)
```

409 not 402/400: the request is well-formed and the world's state refuses it —
the same split `ClaimTeamView` and the existing two exceptions document.
`now()` is `world.services.now()`, never `timezone.now()` (`world/README.md`).

`StaffView.get` adds the team's balance to the payload so the screen can
disable unaffordable hires without a second request.

## api/serializers.py

`TrainerSerializer` gains two `SerializerMethodField`s, `hire_fee` and
`weekly_salary`, reading `staff.pricing`. `StaffSerializer` gains
`balance = serializers.IntegerField()`. Both prices are plain integers — the
`$` belongs to the frontend (`AGENTS.md`).

## frontend/

- **`src/format.ts` (new)** — move `formatMoney` out of `Finances.tsx` and
  import it in both places. One money formatter, not two divergent copies.
- **`src/api.ts`** — `Trainer` gains `hire_fee: number` and
  `weekly_salary: number`; `Staff` gains `balance: number`; the
  `LedgerEntry['kind']` union gains `'trainer_fee' | 'trainer_salary'`.
- **`src/screens/Staff.tsx`** — `TrainerCard` shows both prices; the Hire
  button is disabled when `trainer.hire_fee > staff.balance`, with the reason
  shown. The subtitle string **"Hire a trainer from the pool below — it is
  free."** is now a lie and must change.
- **`src/screens/Finances.tsx`** — label the two new kinds.

## Work items

### W1 — `staff/pricing.py`: the price functions — **done**

New module per Design decision 1 and 7. **Test:**
`staff/tests/test_pricing.py` — `test_salary_scales_with_speciality`
(a 95-speciality trainer costs more than a 70), `test_fee_is_twelve_weeks`,
`test_price_reads_speciality_not_first_attribute` (a sprint specialist and a
climb specialist with the same peak price identically — catches a
`getattr(trainer, "climb")` hardcode), `test_prices_are_whole_credits`.
Pure functions, no DB.

### W2 — `economy/`: the two new kinds, constraint and migration — **done**
`Kind.TRAINER_FEE`, `Kind.TRAINER_SALARY`, the salary's `(team, week)`
constraint, migration `0003`. Plus the `STARTING_BALANCE` comment fix (D8).
**Test:** `economy/tests/test_models.py` —
`test_one_trainer_salary_entry_per_team_per_week` (second insert raises
`IntegrityError`), `test_several_trainer_fees_per_team_allowed` (the fee has
no constraint — this is the one someone will "helpfully" add).

### W3 — `economy/services.py`: `charge_trainer_salaries` and `charge_trainer_fee` — **done**
**Load-bearing:** the injected `salary_by_team` dict, and no `staff/` import.
**Test:** `economy/tests/test_trainer_costs.py` —
`test_charges_only_teams_in_the_dict` (an unstaffed team gets **no** row, not
a zero row — D6), `test_dated_to_the_week_not_now`,
`test_second_call_writes_nothing` (idempotency via the constraint),
`test_balance_can_go_negative`.

### W4 — `staff/services.py`: the `charge` callback in `hire_trainer` — **done**
`InsufficientFunds`, the callback invoked inside the transaction after the
checks. **Load-bearing:** the callback must run *after* the post-lock
availability re-check and *before* commit. **Test:**
`staff/tests/test_services.py` — `test_hire_invokes_charge`,
`test_charge_raising_rolls_back_the_hire` (trainer still unemployed after an
`InsufficientFunds`, asserted by re-reading the row),
`test_hire_without_charge_still_works` (the seed path),
`test_charge_not_called_when_trainer_already_taken`.

### W5 — `world/services.py` + `TickRun`: charge salaries each week — **done**
Build `salary_by_team` from `Trainer.objects.filter(team__isnull=False)` and
call `charge_trainer_salaries` inside the existing per-week loop, next to
`charge_weekly_wages`. Add the counter and migration `0008`.
**Load-bearing:** inside the `for transition in weeks:` loop, never outside —
a catch-up tick must write one row per missed week, dated to each.
**Test:** `world/tests/test_tick.py` —
`test_tick_charges_trainer_salary`, `test_catch_up_charges_each_week_once`
(three missed weeks → three rows with three distinct `occurred_at`),
`test_no_salary_row_for_unstaffed_team`, `test_tick_twice_charges_once`.

### W6 — `api/`: prices, balance, and the insufficient-funds 409
Serializer fields, `StaffView`'s balance, the `charge` callback in
`HireTrainerView`. **Test:** `api/tests.py` —
`test_staff_payload_carries_prices_and_balance`,
`test_hire_debits_the_fee`, `test_hire_refused_when_balance_too_low` (409,
and the trainer is still in the pool), `test_fire_refunds_nothing`.

### W7 — `frontend/`: prices on the cards, disabled unaffordable hire
`src/format.ts`, the `api.ts` types, `Staff.tsx` (including the "it is free"
subtitle), `Finances.tsx` labels. **Test:**
`frontend/src/screens/Staff.test.tsx` — renders both prices, Hire disabled
with a reason when the fee exceeds the balance, enabled when it does not.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7.

W1 and W2 are independent leaves and can land in either order; both are pure
additions that leave the repo green. W3 needs W2's `Kind`. W4 needs nothing
from W3 — the callback is injected, which is the point — but doing W3 first
means W4's tests can use the real `charge_trainer_fee` instead of a stub.
W5 needs W3 and W4. W6 needs W4 (the exception) and W1 (the prices). W7 needs
W6's payload.

**Stop and commit after each item.** W5 is the one to review most carefully:
the salary charge must sit inside the per-week loop.

## Documentation update (required, not optional)

- **`staff/README.md`** — replace the *Future work* bullet "Fee and recurring
  salary — #69. Unblocked… Hiring today is free." with a new section, *What a
  trainer costs*: prices derived from the speciality and never stored (D1),
  the fee-as-cooldown reasoning (D7), and why `hire_trainer` takes an injected
  `charge` rather than importing `economy/` (D2, D3). Update *The pool is
  shared, and hiring is contended* to mention the debit sharing the
  transaction.
- **`economy/README.md`** — under *What this app owns*, add the two new kinds.
  New subsection on the per-week salary charge and the injected
  `salary_by_team` dict, and **explicitly** note the no-row-for-unstaffed-teams
  asymmetry with wages' `amount = 0` rows (D6) so it does not read as a bug.
- **`world/README.md`** — *How a tick works*: the salary charge in the
  per-week loop, and the new counter.
- **`api/README.md`** — the new payload fields and the insufficient-funds 409.
- **`frontend/README.md`** — the shared `format.ts`.
- **`AGENTS.md`** — the `staff/` row currently says "Trainers hireable from a
  shared pool into one fixed slot per team" with no mention of cost; add the
  fee and salary.
- **Delete** `specs/trainer-hiring-fee-salary.md` and this plan when the
  ticket closes, per `AGENTS.md`, *Closing a ticket*.

## Verification

```bash
.venv/bin/python manage.py migrate
.venv/bin/python -m pytest
cd frontend && npm test
```

End to end, with the mock clock:

```bash
.venv/bin/python manage.py seed_user
.venv/bin/python manage.py seed_teams --claim-for test@mail.com
.venv/bin/python manage.py seed_trainers
.venv/bin/python manage.py load_season seasons/season-1.example.json
GAME_CLOCK_CLASS=world.clocks.MockClock .venv/bin/python manage.py mock_clock set <season start>
```

Then: open Staff, confirm every pool card shows a fee and a weekly salary and
that the balance is on screen; hire one and confirm Finances gains a
`Trainer hire fee` row and the balance drops by exactly the fee; `mock_clock
tick` twice across a week boundary and confirm **one** `Trainer salary` row
appears, separate from `Weekly wages`; fire the trainer, tick again, confirm
no new salary row and no refund.

**Likeliest failure mode:** the salary charge placed outside the per-week loop,
so a catch-up tick across three weeks writes one row instead of three. The
check that catches it is `test_catch_up_charges_each_week_once` asserting
**three distinct `occurred_at` values**, not just a count of three — a count
alone passes if three rows are written against the same week, which the unique
constraint would actually prevent, making the test unable to fail for the right
reason.

**Second likeliest:** the fee debited outside `hire_trainer`'s transaction, so
a mid-flight failure leaves a free trainer.
`test_charge_raising_rolls_back_the_hire` catches it only if it re-reads the
`Trainer` row from the database rather than trusting the in-memory instance.

## Risks

| Risk | Mitigation |
|---|---|
| `staff/` grows an `economy/` import, breaking `AGENTS.md`'s graph | The injected `charge` callback (D2/D3). Reviewers: grep `staff/` for `economy` — it must return nothing. |
| Reader adds `fee`/`salary` columns to `Trainer` as "simpler" | D1 states why not. Prices are derived; there is no migration to backfill and no drift. |
| Salary folded into the existing `wages` row | D5. The `wages` unique constraint makes it impossible anyway without changing rider-wage semantics. |
| Salary charge outside the per-week loop | W5 marked load-bearing; `test_catch_up_charges_each_week_once` asserts distinct dates. |
| Affordability checked in the view, before the transaction | D4. Two concurrent hires would both pass. The check belongs in the callback. |
| Someone adds a `(team, week)` constraint to `trainer_fee` by symmetry | W2 has an explicit test that several fees per team are allowed. |
| Economy retuned while fixing the `STARTING_BALANCE` comment | D8: fix the comment, leave the constant. |

## Open questions

None. The spec's one open question — the fee-to-salary ratio — is resolved in
Design decision 7 (12× weekly salary) with the reasoning; overrule the constant
if you disagree, it is one line in `staff/pricing.py`.

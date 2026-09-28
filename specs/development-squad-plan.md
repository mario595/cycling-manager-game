# Development squad — Implementation Plan

**Spec:** `specs/development-squad.md` · **Issue:** #32 · **Status:** proposed
**Apps touched:** `riders/`, `economy/`, `teams/`, `world/`, `api/`, `frontend/`

## Context you need

A team can pay for exactly one kind of standing commitment today: a trainer.
`staff/` holds the trainer in a one-slot `OneToOneField` to `Team`; hiring
charges a one-off fee and the tick charges a weekly salary. **The development
squad is the same economic shape** (one-off fee plus a weekly cost), so this
plan copies that pattern deliberately. Read `staff/README.md`, *What a trainer
costs*, and `staff/services.py`'s `hire_trainer` before starting. The
`charge=` callback there is the model for how a fee gets written without
`riders/` importing `economy/`.

What exists and what you will touch:

- **`economy/`** owns the append-only ledger (`economy/README.md`, *The ledger
  is append-only*). A team's balance is `balance_for(team)`, the sum of its
  `LedgerEntry` rows. There is no balance column anywhere. Every kind of
  money movement is a `LedgerEntry.Kind`. Weekly charges are written once per
  `(team, week)`, with a partial unique constraint as a second line of
  defence; see `charge_trainer_salaries` and `charge_trainer_fee` in
  `economy/services.py`.
- **`world/services.py`'s `tick()`** loops over crossed week boundaries and
  calls each weekly charge inside `for transition in weeks:`. It builds the
  trainer's `salary_by_team` map **once, before the loop**, and hands it to
  `economy/`. `TickRun` (`world/models.py`) carries one counter per kind of
  row the tick writes.
- **`teams/services.py`'s `claim_team`** resets a team for a new manager:
  roster, balance, fanbase and sponsorship. `release_team` deliberately
  touches nothing but the manager link (`teams/README.md`).
- **`AGENTS.md`** says the development squad "lives in `riders/`". Youth
  riders (#33) will be `Rider` rows, so the facility sits beside them.
- **`api/views.py`**: `StaffView` / `HireTrainerView` / `FireTrainerView` are
  the exact template for the new views: `team_for()`, 403 without a team, 409
  for a well-formed request the world's state refuses.
- **`frontend/`**: one screen per nav item (`src/navigation.ts` is the single
  source of truth for the sidebar and the router). The data hooks follow
  `useStaff.ts`, and money goes through `formatMoney` (`frontend/README.md`,
  *Conventions*).

Repo rules this is bound by (`AGENTS.md`):
`riders -> core, teams`. `economy -> core, teams, riders, schedule`.
`teams -> core, accounts, riders` (plus the lazy `economy` exception).
`world` and `api` may import anything, and nothing imports them.
**`riders/` may not import `economy/` or `schedule/`.**

## Goal

1. A managed team can open a development squad at one of three levels, which
   debits that level's opening fee. It can upgrade (debiting the difference in
   opening fees), downgrade (free, no refund) or close (free, no refund).
   Opening or upgrading is refused if the balance does not cover the fee.
2. Every week boundary, every team with an open squad is debited its current
   level's weekly cost, exactly once per week.
3. Claiming a team closes its squad. Releasing a team does not.
4. A new **Development squad** screen shows every level's opening fee, weekly
   cost, full-season cost and what it would cost *this* team to move to it,
   plus the team's current level. The screen has no "coming soon" copy, per
   the spec's *Decisions taken*.
5. Fees and weekly costs appear on the Finances screen as their own labelled
   lines.

## Design decisions (settled — implement these, do not substitute)

1. **The model lives in `riders/`, as `riders.DevelopmentSquad`.** `AGENTS.md`
   already places the development squad there, and #33 will generate youth
   riders into it. Every reader is allowed to import it: `economy` → `riders`,
   `teams` → `riders`, `world`/`api` → everything. *Not* `teams/`: that app is
   the manager link and naming, and `teams/README.md` says staff and tactics
   do not live there. *Not* `economy/`: the facility is not money; only its
   charges are.

2. **One row per open squad; closing deletes the row.** `team` is a
   `OneToOneField`, so "one squad per team" is a database constraint, the same
   argument `staff/README.md`, *The one-slot rule*, makes. The spec says "a
   closed squad has no level" and reopening does not remember the old level,
   so a closed row would carry state nobody may read. The ledger is the
   history of what was paid. *Do not* add an `is_open` flag or a nullable
   `level`.

3. **Prices are a fixed table in code, `riders/development_squad.py`'s
   `LEVELS`, never stored on the row.** It is the same reasoning as
   `staff/pricing.py`: a stored price can drift from the table. Three levels:

   | Level | Name | Opening fee | Weekly cost | Season cost (×12) |
   |---|---|---|---|---|
   | 1 | Regional | $30,000 | $1,500 | $18,000 |
   | 2 | National | $75,000 | $3,500 | $42,000 |
   | 3 | Elite | $150,000 | $6,000 | $72,000 |

   These are calibrated against `STARTING_BALANCE` (500,000) and a ~14,400/week
   wage bill: Regional is roughly a mid-range trainer, and Elite's first season
   (fee plus 12 weeks) is ~44% of a starting balance, so an Elite squad is a
   real bet. **Both columns must rise strictly with level** (spec, *Rules and
   edge cases*); a test enforces it, because the upgrade-fee rule depends on
   it. The numbers are tunable. The ordering is not.

4. **Upgrade fee = `opening_fee(new) − opening_fee(old)`. Downgrade and close
   write no ledger row at all.** A zero-amount row is not written. Unlike wages,
   there is nothing to record.

5. **The fee is written through an injected `charge` callback**, exactly like
   `hire_trainer(team, trainer_id, *, charge=None)`. `riders/` cannot import
   `economy/`. The callback is `charge(amount: int, description: str) -> None`,
   where `amount` is the **positive** fee. It runs *inside* the service's
   transaction, *after* the state checks and *before* the row write, so a raise
   (insufficient funds) rolls everything back. `api/` supplies it: it checks
   `balance_for(team) >= amount`, raises `InsufficientFunds`, and otherwise
   calls `economy.services.charge_development_squad_fee`. With `charge=None`,
   the change is free, which is the path tests and any future seed use.

6. **Every squad operation locks the `Team` row** (`select_for_update()`,
   without `skip_locked`) before reading the squad. When the squad is closed
   there is no squad row to lock, so the team row is the only thing that
   serialises two concurrent "open" requests. Locking it for upgrade, downgrade
   and close too gives one lock order for all four operations. The
   `OneToOneField` unique index is the second line of defence: an
   `IntegrityError` on create is re-raised as `SquadAlreadyOpen`.

7. **The weekly cost is charged at each week boundary, at the level the squad
   holds when the tick processes that boundary.** That is how wages and
   trainer salaries work: the charge is dated the opening week's `starts_at`.
   So a squad opened mid-week pays its first weekly cost at the *next*
   boundary; the opening fee covers the remainder of the opening week. The
   spec's "including a week where it was also opened, upgraded, or downgraded"
   is honoured as "no week is charged twice and none is skipped while open",
   not as a pro-rata charge. *Do not* charge a weekly cost at the moment of
   opening. That would be a second, differently-dated weekly row for the same
   week, and the `(team, week)` constraint would reject the real one at the
   boundary.

8. **`world/` builds `cost_by_team` once, before the week loop**, from
   `DevelopmentSquad.objects.all()`. `economy/` receives a plain dict, the same
   shape as `salary_by_team`. `economy/` *may* import `riders/`, but taking a
   dict keeps `charge_development_squad_costs` trivially testable and identical
   in shape to its neighbour. No squad changes mid-tick, so one map is right
   for every missed week (same argument as the trainer map's comment).

9. **Squads are charged whether or not the team is managed.** A released team
   keeps its squad (spec, *In scope* 10), so it keeps paying. The balance is
   reset on the next claim anyway, and the claim closes the squad.

10. **Two new ledger kinds: `development_squad_fee` and `development_squad`.**
    The fee covers both opening and upgrading, told apart by `description`
    ("Opened development squad — Regional", "Upgraded development squad to
    Elite"), which is the same "one kind, description distinguishes" rule
    `TRANSFER_FEE` follows (`economy/README.md`, *Free-agent fees*). The weekly
    row's description is "Development squad — National". `LedgerEntry.kind` is
    `max_length=20` and `development_squad_fee` is 21 characters, so **widen
    `kind` to `max_length=32`** in the same migration. *Do not* shorten the name
    to `dev_squad_*`: the issue's naming note exists precisely because "dev"
    means software in this codebase.

11. **The API computes every price the screen shows**, including `change_fee`,
    what moving to each level would cost this team right now. The SPA never
    re-derives the upgrade rule. It is the same discipline as `StaffView`
    shipping `hire_fee` rather than a formula.

12. **Season cost uses `schedule.models.SEASON_WEEKS`, read in `api/`.**
    `riders/` may not import `schedule/`, so the ×12 is applied in the view,
    not in `LEVELS`.

13. **Unmanaged teams never open a squad.** There is no AI path, per the spec's
    *Out of scope* (#45). Nothing in `world/ai_market.py` changes.

14. **No seed change.** Every team starts with no squad, which is the spec's
    default. The demo account can open one from the screen.

## Data model

### `riders.DevelopmentSquad` (new) — `riders/models.py`

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `team` | `OneToOneField("teams.Team", on_delete=CASCADE, related_name="development_squad")` | no | — | One squad per team, enforced by the unique index. |
| `level` | `PositiveSmallIntegerField(choices=Level.choices)` | no | — | 1, 2 or 3. |
| `opened_at` | `DateTimeField` | no | — | Game time the squad was (last) opened. Informational; nothing reads it for pricing. |
| `created_at`, `updated_at` | from `TimeStampedModel` | | | |

- `class Level(models.IntegerChoices): REGIONAL = 1, "Regional"; NATIONAL = 2, "National"; ELITE = 3, "Elite"` is nested on the model.
- `Meta.constraints`: `CheckConstraint(condition=Q(level__gte=1) & Q(level__lte=3), name="development_squad_level_in_range")`. `condition=` is the keyword this repo's Django uses; see `Rider`'s `retired_rider_has_no_team`.
- Migration: **`riders/migrations/0013_developmentsquad.py`**, depending on `0012_rider_retired_at` and `teams`' `0003_team_managed_since_managerialspell`.

### `economy.LedgerEntry` — `economy/models.py`

- `Kind` gains `DEVELOPMENT_SQUAD_FEE = "development_squad_fee", "Development squad fee"` and `DEVELOPMENT_SQUAD = "development_squad", "Development squad"`.
- `kind` becomes `CharField(max_length=32, choices=Kind.choices)`.
- New constraint: `UniqueConstraint(fields=["team", "week"], condition=Q(kind="development_squad"), name="one_development_squad_cost_per_team_per_week")`.
- Update `week`'s `help_text` to include development squad entries.
- Migration: **`economy/migrations/0011_development_squad_kinds.py`** (AlterField plus AddConstraint), depending on `0010_alter_ledgerentry_kind`.

### `world.TickRun` — `world/models.py`

- `development_squad_entries = PositiveIntegerField(default=0, help_text="Ledger development squad weekly entries written this tick (#32).")`
- Migration: **`world/migrations/0017_tickrun_development_squad_entries.py`**.

Run `makemigrations` and check what it generates matches the names above.
Rename the file if Django picks another name; the content is what matters.

## `riders/development_squad.py` (new)

Pricing and the four operations. Kept out of `riders/services.py`, which is
already long and about the age curve and training.

```python
@dataclass(frozen=True)
class LevelTerms:
    level: int          # DevelopmentSquad.Level value
    name: str
    opening_fee: int
    weekly_cost: int

LEVELS: dict[int, LevelTerms]   # keyed 1..3, table in Design decision 3

class DevelopmentSquadError(Exception): ...
class SquadAlreadyOpen(DevelopmentSquadError): ...
class SquadNotOpen(DevelopmentSquadError): ...
class SameLevel(DevelopmentSquadError): ...
class UnknownLevel(DevelopmentSquadError): ...    # ValueError-like; API's ChoiceField catches it first
class InsufficientFunds(DevelopmentSquadError): ... # raised by api/'s charge callback, declared here so the service's callers can catch one family

def weekly_cost(level: int) -> int
def change_fee(current_level: int | None, target_level: int) -> int
    # None -> opening_fee(target); upgrade -> difference; downgrade -> 0.
    # target == current raises SameLevel.
def squad_for(team) -> DevelopmentSquad | None
def open_squad(team, level: int, *, at, charge=None) -> DevelopmentSquad
def change_level(team, level: int, *, charge=None) -> DevelopmentSquad
def close_squad(team) -> bool      # True if a squad was closed, False if none was open
```

`change_fee` is the **only** place the upgrade rule lives. `open_squad`,
`change_level` and the API's per-level `change_fee` all go through it.

The load-bearing function, in full:

```python
def open_squad(team, level, *, at, charge=None):
    terms = LEVELS.get(level)
    if terms is None:
        raise UnknownLevel(f"No development squad level {level!r}.")
    with transaction.atomic():
        Team.objects.select_for_update().get(pk=team.pk)        # D6: the only lockable thing
        if DevelopmentSquad.objects.filter(team=team).exists():
            raise SquadAlreadyOpen("Your development squad is already open.")
        if charge is not None:
            charge(change_fee(None, level), f"Opened development squad — {terms.name}")
        try:
            with transaction.atomic():                          # savepoint: keep the outer txn usable
                return DevelopmentSquad.objects.create(team=team, level=level, opened_at=at)
        except IntegrityError:
            raise SquadAlreadyOpen("Your development squad is already open.")
```

`IntegrityError` rolls back the savepoint; the exception then propagates out
of the outer `atomic()`, which rolls back the fee row too. Keep that order.

`change_level`: same lock. `SquadNotOpen` if there is no row, `SameLevel` if
`level == squad.level`. If `level > squad.level` and `charge` is set, call
`charge(change_fee(...), f"Upgraded development squad to {name}")`. Then
`squad.level = level; squad.save(update_fields=["level", "updated_at"])`. A
downgrade never calls `charge`.

`close_squad`: same lock, then `DevelopmentSquad.objects.filter(team=team).delete()`,
returning whether the count was > 0. It does not raise. The API turns `False`
into a 409, and `claim_team` ignores the return value.

## `economy/services.py`

```python
def charge_development_squad_costs(week, *, cost_by_team: dict[int, int]) -> int
def charge_development_squad_fee(team, *, amount: int, at, description: str) -> LedgerEntry
```

Copy the bodies of `charge_trainer_salaries` and `charge_trainer_fee`: one
`atomic()` per create with `IntegrityError` skipped, a negative `amount`, and
`occurred_at=week.starts_at` with `week=week` on the weekly one. The weekly
description is `f"Development squad — {level_name}"`, so the map carries the
name as well as the cost: **`cost_by_team: dict[int, tuple[int, str]]`**
(team pk → `(weekly_cost, level_name)`), documented in the docstring.
`economy/` never looks up `LEVELS` itself.

## `teams/services.py`

In `claim_team`, after the new roster is written and before the lazy
`economy` import:

```python
close_squad(team)
```

It is imported at module scope from `riders.development_squad`, since
`teams -> riders` is allowed and `teams/services.py` already imports
`riders.generation` and `riders.services` there. **`release_team` is not
touched** (Design decision 9).

## `world/services.py` and `world/models.py`

In `tick()`, next to `salary_by_team`:

```python
squad_cost_by_team = {
    squad.team_id: (weekly_cost(squad.level), LEVELS[squad.level].name)
    for squad in DevelopmentSquad.objects.all()
}
```

Inside `for transition in weeks:`, directly after `charge_trainer_salaries`:

```python
development_squad_entries += charge_development_squad_costs(
    week, cost_by_team=squad_cost_by_team,
)
```

Initialise the counter with the others, and pass it into the `TickRun`
creation beside `trainer_salary_entries`. Check how the `TickRun` is
constructed at the bottom of `tick()` and follow it exactly.

## `api/`

**`api/serializers.py`**

- `DevelopmentSquadLevelSerializer`: `level`, `name`, `opening_fee`,
  `weekly_cost`, `season_cost`, `change_fee` (int or null; null for the
  current level), `is_current` (bool).
- `DevelopmentSquadSerializer`: `level` (int or null), `levels`
  (many), `balance`.
- `DevelopmentSquadLevelChoiceSerializer`: `level =
  ChoiceField(choices=DevelopmentSquad.Level.choices)`. Invalid input → 400.

**`api/views.py`**

| View | Method + URL | Success | 409 when |
|---|---|---|---|
| `DevelopmentSquadView` | `GET /api/development-squad/` | 200 + payload | — |
| `OpenDevelopmentSquadView` | `POST /api/development-squad/open/` `{level}` | 204 | `SquadAlreadyOpen`, `InsufficientFunds` |
| `ChangeDevelopmentSquadLevelView` | `POST /api/development-squad/level/` `{level}` | 204 | `SquadNotOpen`, `SameLevel`, `InsufficientFunds` |
| `CloseDevelopmentSquadView` | `POST /api/development-squad/close/` | 204 | no squad open |

All four return 403 without a team, and are `IsAuthenticated` by the project
default. **Do not add `AllowAny`.** `POST` for close, not `DELETE`, is the
same reasoning `FireTrainerView` gives.

The callback both write views share is a module-level helper:

```python
def _squad_charge(team):
    def charge(amount, description):
        if balance_for(team) < amount:
            raise InsufficientFunds("You cannot afford this.")
        charge_development_squad_fee(team, amount=-amount, at=now(), description=description)
    return charge
```

Here `InsufficientFunds` is `riders.development_squad.InsufficientFunds`,
**not** `staff.services.InsufficientFunds`. They are separate classes, and
catching the wrong one turns a 409 into a 500.

The GET builds `levels` from `LEVELS` in level order. `season_cost` is
`weekly_cost * SEASON_WEEKS`, and `change_fee` is `None` for the current
level, otherwise `development_squad.change_fee(current, level)`.

**`api/urls.py`**: add the four paths.

## `frontend/`

- **`src/api.ts`**: types `DevelopmentSquad` / `DevelopmentSquadLevel`, plus
  `getDevelopmentSquad()`, `openDevelopmentSquad(level)`,
  `changeDevelopmentSquadLevel(level)` and `closeDevelopmentSquad()`, using the
  existing `writeJson` helper the trainer calls use. Add both new kinds to
  `LedgerEntry['kind']` and to its doc comment.
- **`src/useDevelopmentSquad.ts`** (new): a copy of `useStaff.ts`'s lifecycle,
  with a 60-second poll and `refresh()`.
- **`src/screens/DevelopmentSquad.tsx`** (new): a header with the current state
  ("Closed", or the level name), then one card per level showing the name,
  opening fee, weekly cost and "$X per season". Each card has one action,
  worded by state:
  - Closed: **Open** (showing the fee).
  - Higher than current: **Upgrade** (showing the difference).
  - Lower than current: **Downgrade** (free).
  - Current: a **Current** badge.

  A **Close squad** button appears when the squad is open. An action whose fee
  exceeds `balance` is disabled, which mirrors how `Staff.tsx` handles an
  unaffordable trainer. Check that screen and copy its treatment. On a 409,
  show the server's `detail`. **No copy about youth intake or "coming soon"**
  (spec, *Decisions taken*). Close and downgrade take no confirmation dialog
  unless `Staff.tsx`'s fire does. Match it.
- **`src/navigation.ts`**: add `{ path: '/development-squad', name: 'Development squad' }`
  to TEAM, after Staff.
- **`src/App.tsx`**: map `'/development-squad': DevelopmentSquad` in the
  path→screen record beside `'/staff': Staff`. Without it, the nav item opens
  the catch-all redirect.
- **`src/screens/Finances.tsx`**: add both kinds to `KIND_LABELS`. TypeScript
  fails the build if you forget, because the record is keyed on the union.

Styling follows `frontend/README.md`, *Conventions*: inline styles, colours
from `theme.ts`, money through `formatMoney`.

## Work items

### W1 — `riders/`: model, migration, pricing table ✅
Add `DevelopmentSquad` plus `0013_developmentsquad.py`, and
`riders/development_squad.py` with `LEVELS`, `weekly_cost` and `change_fee`
only (no operations yet).
**Tests** in `riders/tests/test_development_squad.py`:
- `test_levels_rise_strictly_in_both_columns`
- `test_change_fee_from_closed_is_opening_fee`
- `test_change_fee_upgrade_is_difference`
- `test_change_fee_downgrade_is_zero`
- `test_change_fee_same_level_raises`
- `test_one_squad_per_team` (a second create raises `IntegrityError`)
- `test_level_out_of_range_rejected_by_db`

### W2 — `riders/development_squad.py`: open, change level, close ✅
The four operations, with the locking and callback order from Design
decisions 5 and 6.
**Tests**, same file:
- `test_open_creates_squad_and_charges_opening_fee` (a fake `charge` records its calls)
- `test_open_when_open_raises_and_charges_nothing`
- `test_charge_raising_rolls_back_open` (callback raises; no row exists afterwards)
- `test_upgrade_charges_difference`
- `test_downgrade_charges_nothing`
- `test_change_level_when_closed_raises`
- `test_change_to_same_level_raises`
- `test_close_deletes_and_returns_true`
- `test_close_when_closed_returns_false`
- `test_reopen_after_close_charges_full_fee`

### W3 — `economy/`: kinds, constraint, charge functions ✅
The model change, `0011_development_squad_kinds.py`, and both service
functions.
**Tests** in `economy/tests/test_development_squad_costs.py`:
- `test_weekly_cost_debits_each_team_in_map`
- `test_weekly_cost_is_idempotent_per_week` (call twice, one row)
- `test_team_absent_from_map_gets_no_row`
- `test_fee_writes_negative_row_with_description`
- `test_kind_accepts_21_char_value` (a `full_clean()` on a
  `development_squad_fee` row passes, which proves the `max_length` bump)

### W4 — `world/`: charge squads in the tick ✅
`squad_cost_by_team`, the call inside the loop, `TickRun.development_squad_entries`
and its migration.
**Tests** in `world/tests/` (put them beside the existing trainer-salary tick
tests; grep `trainer_salary_entries`):
- `test_tick_charges_open_squad_each_crossed_week` (open at level 2, move the
  mock clock three weeks, tick → three rows at 3,500, dated to three weeks)
- `test_tick_charges_unmanaged_team_with_squad`
- `test_tick_twice_does_not_double_charge`
- `test_squad_opened_mid_week_first_charged_at_next_boundary`

### W5 — `teams/`: claim closes the squad ✅
**Tests** in `teams/tests/` beside the existing claim tests:
- `test_claim_closes_development_squad`
- `test_release_keeps_development_squad`

### W6 — `api/`: the four endpoints
**Tests** in `api/tests.py`, beside the staff tests, reusing their fixtures'
shape:
- `test_development_squad_requires_authentication`
- `test_development_squad_without_team_is_403`
- `test_development_squad_closed_payload` (level null; every `change_fee`
  equals its opening fee; `season_cost == weekly_cost * 12`)
- `test_development_squad_open_payload_marks_current_and_prices_changes`
- `test_open_debits_fee` (balance drops by exactly 30,000 at level 1, one
  `development_squad_fee` row)
- `test_open_refused_when_balance_too_low` (409, no row, no ledger entry)
- `test_open_invalid_level_is_400`
- `test_upgrade_debits_difference`
- `test_downgrade_debits_nothing`
- `test_close_then_close_again_is_409`

### W7 — `frontend/`: screen, hook, nav, Finances labels
**Tests** in `src/screens/DevelopmentSquad.test.tsx`, mocking
`useDevelopmentSquad` as `Staff.test.tsx` mocks `useStaff`:
- renders three levels with fee, weekly and per-season cost in `$` format
- closed state: each card offers **Open**, and no Close button appears
- open at National: Elite offers **Upgrade** at the difference, Regional offers
  **Downgrade**, National shows **Current**, and Close appears
- an action costing more than the balance is disabled

Add `'/development-squad'` to `BUILT_SCREENS` in `src/navigation.test.ts`.
Its "every nav item has a screen" test fails until you do, which is the
intended guard against the `App.tsx` mapping being forgotten.

### W8 — Documentation
See *Documentation update*. This is its own commit, along with archiving the
spec and plan per `AGENTS.md`, *Closing a ticket*.

## Execution order

1. **W1 → W2**: the domain first, with no money, so the rules are provable in
   isolation with a fake callback.
2. **W3**: the ledger can now record fees and weekly costs. It is independent
   of W2, but a pure addition.
3. **W4**: the tick. It needs W1 (the model) and W3 (the charge function).
   This is the step with the likeliest silent bug (Design decision 7), so it
   gets its own commit and its date-level assertions.
4. **W5**: a small change, but it touches `claim_team`, which every account
   depends on. Run the whole `teams/` suite.
5. **W6**: wires W2 and W3 together through the callback.
6. **W7**: the frontend, against a working API.
7. **W8**.

Commit after each W, and run the full suite (`.venv/bin/python -m pytest`)
before each commit. After W7, also run `npm --prefix frontend test` and
`npm --prefix frontend run build`.

## Documentation update (required, not optional)

- **`riders/README.md`**: add a **Development squad** section: the model, the
  one-row-per-open-squad rule and why closing deletes, `LEVELS` and the
  strictly-rising rule, the injected `charge` callback, the `Team` row lock,
  and that #33 will generate youth riders into it. Update *What this app
  owns*.
- **`economy/README.md`**: add a **Development squad costs** section covering
  the two kinds and the one-kind-for-open-and-upgrade rule, why `kind` was
  widened to 32, and that the weekly cost is charged at the boundary at the
  level held then (Design decision 7). Update *What this app owns*.
- **`world/README.md`**: add the charge to the tick's per-week list and
  `development_squad_entries` to the `TickRun` description.
- **`teams/README.md`**: in *Claiming a team*, add the new step "closes the
  development squad". In the `release_team` section, add squads to what it
  leaves untouched.
- **`api/README.md`**: the four endpoints.
- **`frontend/README.md`**: *What exists*, the new screen (the count becomes
  eleven), and the `AGENTS.md` frontend row to match.
- **`AGENTS.md`**: the `riders/` row gains "a team's development squad
  facility (level, opening fee, weekly cost)", and the `economy/` row adds
  development squad fee and weekly cost to its list of entries.
- **`specs/roadmap.md`**: mark #32 ✅.
- Spec and plan: `Status: implemented`, moved to `specs/archive/`.

## Verification

Beyond the suite:

```bash
cd .claude/worktrees/development-squad
/home/mario/dev/cycling-manager/.venv/bin/python scripts/dev_db.py
/home/mario/dev/cycling-manager/.venv/bin/python manage.py migrate
/home/mario/dev/cycling-manager/.venv/bin/python manage.py seed_user
/home/mario/dev/cycling-manager/.venv/bin/python manage.py seed_teams --claim-for test@mail.com
/home/mario/dev/cycling-manager/.venv/bin/python manage.py load_season seasons/season-1.example.json
GAME_CLOCK_CLASS=world.clocks.MockClock /home/mario/dev/cycling-manager/.venv/bin/python manage.py runserver <port from config/worktree.py>
```

1. Log in as the demo account and open **Development squad**. All three levels
   show with correct per-season figures, and the screen says nothing about
   intake.
2. Open at Regional. Finances shows one "Opened development squad — Regional"
   line at −$30,000, and the balance drops by exactly that.
3. Upgrade to Elite: one line at −$120,000. Downgrade to National: **no new
   line.**
4. Move the mock clock two weeks and `tick`. Finances shows two "Development
   squad — National" lines at −$3,500, **dated a week apart.** The likeliest
   failure is charging at open time as well, or dating by `now()`. That shows
   up here as three lines or two lines with the same date.
5. Close the squad, `tick` another week, and see no new squad line.
6. With a balance below $30,000 (tick forward, or use the Django shell to add a
   `LedgerEntry` debit to the test team), confirm **Open** is disabled and a
   forced `POST /api/development-squad/open/` returns 409 with no ledger row.

## Risks

| Risk | Mitigation |
|---|---|
| Charging a weekly cost at open time as well as at the boundary (a double charge, or an `IntegrityError` that silently drops the real one). | Design decision 7; `test_squad_opened_mid_week_first_charged_at_next_boundary`; verification step 4. |
| Catching `staff.services.InsufficientFunds` instead of the `riders` one in the API, so an unaffordable open 500s. | Called out in the `api/` section; `test_open_refused_when_balance_too_low` asserts 409. |
| The fee row survives a failed open, because the `IntegrityError` was caught inside the outer transaction and the view carried on. | The savepoint-then-re-raise code in `open_squad` is given in full; `test_charge_raising_rolls_back_open`. |
| `kind` `max_length` left at 20, so Postgres raises `value too long` on the first fee. | Migration 0011 widens it; `test_kind_accepts_21_char_value`. |
| Two different fee-charging actions (hiring a trainer and opening a squad) race past their balance checks, taking the balance below zero. | Accepted, and pre-existing for the trainer. The `Team` lock (D6) serialises squad operations against each other only. Insolvency (#27) owns what a negative balance means. |
| Upgrading from level 1 straight to 3 charged as two steps, or the SPA computing its own price. | `change_fee` is the single source (D3/D11), and the API ships `change_fee` per level. |
| Someone adds intake copy to the empty-looking screen. | The spec's *Decisions taken* and the `frontend/` section both say no. |

## Open questions

None.

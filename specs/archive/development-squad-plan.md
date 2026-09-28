# Development squad — Implementation Plan

**Spec:** `specs/archive/development-squad.md` · **Issue:** #32 · **Status:** implemented
**Apps touched:** `riders/`, `economy/`, `teams/`, `world/`, `api/`, `frontend/`
**Amended:** 2026-09-28, before merge — the squad became a ladder climbed one level at a time, with no downgrade and a per-rung fee. Design decisions 3, 4, 6, 7 and 11 are amended below, and W9–W12 in *Amendment* record the work. Everything W1–W8 built stands except where noted.

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

   | Level | Name | Fee to reach | Weekly cost | Season cost (×12) |
   |---|---|---|---|---|
   | 1 | Regional | $30,000 | $1,500 | $18,000 |
   | 2 | National | $75,000 | $3,500 | $42,000 |
   | 3 | Elite | $150,000 | $6,000 | $72,000 |

   These are calibrated against `STARTING_BALANCE` (500,000) and a ~14,400/week
   wage bill: Regional is roughly a mid-range trainer. **Both columns must rise
   strictly with level** (spec, *Rules and edge cases*), and the test that
   enforces it is now load-bearing for a different reason than it was: the
   upgrade rule is no longer a difference between fees, so there is no
   side-door to undercut. What the ordering guarantees now is that the ladder
   is a ladder — the top is the most expensive thing to reach *and* to run, so
   a player is never meant to stop short of it or to climb to save money. The
   numbers are tunable. The ordering is not.

   **Amended.** The column was "Opening fee" and each figure was only payable
   by opening at that level. It is now the fee to *reach* that level, paid in
   full on every rung, so reaching Elite costs 30,000 + 75,000 + 150,000 =
   255,000 — and Elite's first season is 65% of a starting balance, against
   44% when an upgrade was a difference.

4. **A level's fee is what reaching it costs, whatever route was taken.
   Closing writes no ledger row at all.** So opening (lowest level only) and
   upgrading (the rung directly above) both charge `LEVELS[target].opening_fee`,
   and the figure the screen quotes is the figure the ledger is debited —
   there is no separate "difference" arithmetic anywhere. Closing writes
   nothing: a zero-amount row is not written, and unlike wages there is
   nothing to record. **Amended** — the original charged the difference and
   made a free downgrade the counterpart; there is no downgrade now, and
   closing is the only way to spend less.

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
   serialises two concurrent "open" requests. Locking it for upgrade and close
   too gives one lock order for all three operations. The
   `OneToOneField` unique index is the second line of defence: an
   `IntegrityError` on create is re-raised as `SquadAlreadyOpen`.

7. **The weekly cost is charged at each week boundary, at the level the squad
   holds when the tick processes that boundary.** That is how wages and
   trainer salaries work: the charge is dated the opening week's `starts_at`.
   So a squad opened mid-week pays its first weekly cost at the *next*
   boundary; the opening fee covers the remainder of the opening week. The
   spec's "including a week where it was also opened or upgraded"
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

11. **The API computes every price and every rule the screen shows.** It ships
    each level's `fee`, what moving onto it would cost, and its `action` —
    `open`, `upgrade`, `current` or `locked` — plus `requires`, why a locked
    level is locked, as `riders.development_squad.level_status` states it. The
    SPA renders those and never re-derives the ladder from a level comparison
    or a null. It is the same discipline as `StaffView` shipping `hire_fee`
    rather than a formula, and it is the only thing that stops a padlock on a
    card and a 409 from the service disagreeing. **Amended** — this originally
    shipped `change_fee` and `is_current`, which forced the SPA to rebuild the
    rule from them, including a zero-fee "downgrade" that no longer exists.

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

Pricing and the three operations. Kept out of `riders/services.py`, which is
already long and about the age curve and training.

```python
@dataclass(frozen=True)
class LevelTerms:
    level: int          # DevelopmentSquad.Level value
    name: str
    opening_fee: int
    weekly_cost: int

LEVELS: dict[int, LevelTerms]   # keyed 1..3, table in Design decision 3
ENTRY_LEVEL: int = min(LEVELS)  # the one level a squad can be opened at

SquadAction = Literal["open", "upgrade", "current", "locked"]

@dataclass(frozen=True)
class LevelStatus:
    action: SquadAction
    note: str | None = None     # never null when locked

class DevelopmentSquadError(Exception): ...
class SquadAlreadyOpen(DevelopmentSquadError): ...
class SquadNotOpen(DevelopmentSquadError): ...
class SameLevel(DevelopmentSquadError): ...
class LevelLocked(DevelopmentSquadError): ...      # above the level held, or above the entry level while closed
class CannotDowngrade(DevelopmentSquadError): ...  # below the level held: there is no way down the ladder
class UnknownLevel(DevelopmentSquadError): ...    # ValueError-like; API's ChoiceField catches it first
class InsufficientFunds(DevelopmentSquadError): ... # raised by api/'s charge callback, declared here so the service's callers can catch one family

def weekly_cost(level: int) -> int
def level_fee(level: int) -> int          # what moving ONTO this level costs, in every state
def level_status(current_level: int | None, target_level: int) -> LevelStatus
def squad_for(team) -> DevelopmentSquad | None
def open_squad(team, level: int, *, at, charge=None) -> DevelopmentSquad
def change_level(team, level: int, *, charge=None) -> DevelopmentSquad
def close_squad(team) -> bool      # True if a squad was closed, False if none was open
```

`level_status` is the **only** place the ladder rule lives, and it returns the
`action` *and* the `note`, because a locked level has two different reasons and
the screen has to tell them apart: a rung not yet reached ("Upgrade to National
first") and one already climbed past ("Climbed past. Close the squad to start
over."). `open_squad` and `change_level` go through it as well, so the padlock
and the refusal cannot disagree.

**Amended** — this section originally had `change_fee(current_level,
target_level)`, which returned the difference on an upgrade, 0 on a downgrade
and the full fee on an opening, and `change_level` accepted any target. A
level's price is a property of the level, not of the move that reaches it, so
`change_fee` is gone in favour of `level_fee`; the ladder rule that replaces it
is `level_status`, not arithmetic. See W9.

The load-bearing function, in full:

```python
def open_squad(team, level, *, at, charge=None):
    terms = LEVELS.get(level)
    if terms is None:
        raise UnknownLevel(f"No development squad level {level!r}.")
    if level_status(None, level).action == "locked":      # anything but ENTRY_LEVEL
        raise LevelLocked(...)
    with transaction.atomic():
        Team.objects.select_for_update().get(pk=team.pk)        # D6: the only lockable thing
        if DevelopmentSquad.objects.filter(team=team).exists():
            raise SquadAlreadyOpen("Your development squad is already open.")
        if charge is not None:
            charge(level_fee(level), f"Opened development squad — {terms.name}")
        try:
            with transaction.atomic():                          # savepoint: keep the outer txn usable
                return DevelopmentSquad.objects.create(team=team, level=level, opened_at=at)
        except IntegrityError:
            raise SquadAlreadyOpen("Your development squad is already open.")
```

`IntegrityError` rolls back the savepoint; the exception then propagates out
of the outer `atomic()`, which rolls back the fee row too. Keep that order.

`change_level`: same lock, and the same lock *order* as the other two. Checked
in this order, and the order matters — the squad's existence before the ladder,
so a closed squad reports `SquadNotOpen` rather than a lock complaint:

1. `SquadNotOpen` if there is no row.
2. `level_status(squad.level, level).action` — `current` raises `SameLevel`;
   `locked` raises `CannotDowngrade` when `level < squad.level` and
   `LevelLocked` when it is a skipped rung. Comparing the levels here rather
   than trusting the status to distinguish them is deliberate: `LevelStatus`
   carries copy for the screen, and an exception type is a promise to a caller
   about *why*, so each branch raises the one that names the actual reason.
3. Otherwise call `charge(level_fee(level), f"Upgraded development squad to
   {name}")`, then `squad.level = level; squad.save(update_fields=["level",
   "updated_at"])`.

There is no branch that writes the row without charging: with no downgrade, an
accepted change is always an upgrade, and a charge that raises rolls the whole
thing back.

`close_squad`: same lock, then `DevelopmentSquad.objects.filter(team=team).delete()`,
returning whether the count was > 0. It does not raise. The API turns `False`
into a 409, and `claim_team` ignores the return value. Closing deletes rather
than flags, which is what makes the reopen a genuine start from the bottom
rather than a resume.

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

- `DevelopmentSquadLevelSerializer`: `level`, `name`, `weekly_cost`,
  `season_cost`, `fee` (what moving onto this level costs), `action`
  (`open`/`upgrade`/`current`/`locked`), `requires` (string or null; null for
  anything but `locked`).
- `DevelopmentSquadSerializer`: `level` (int or null), `levels`
  (many), `balance`.
- `DevelopmentSquadLevelChoiceSerializer`: `level =
  ChoiceField(choices=DevelopmentSquad.Level.choices)`. Invalid input → 400.

**`api/views.py`**

| View | Method + URL | Success | 409 when |
|---|---|---|---|
| `DevelopmentSquadView` | `GET /api/development-squad/` | 200 + payload | — |
| `OpenDevelopmentSquadView` | `POST /api/development-squad/open/` `{level}` | 204 | `SquadAlreadyOpen`, `LevelLocked`, `InsufficientFunds` |
| `ChangeDevelopmentSquadLevelView` | `POST /api/development-squad/level/` `{level}` | 204 | `SquadNotOpen`, `SameLevel`, `LevelLocked`, `CannotDowngrade`, `InsufficientFunds` |
| `CloseDevelopmentSquadView` | `POST /api/development-squad/close/` | 204 | no squad open |

All four return 403 without a team, and are `IsAuthenticated` by the project
default. **Do not add `AllowAny`.** `POST` for close, not `DELETE`, is the
same reasoning `FireTrainerView` gives.

Every 409 above is a domain exception, including the two new ladder ones. The
views translate; they do not decide. A `LevelLocked` on open means "that level
is not the way in", not "that level does not exist" — the latter is the
serializer's 400, and the two answers are different enough to be worth keeping
apart.

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
`weekly_cost * SEASON_WEEKS`. `fee` is `level_fee(level)` — the same for every
state, which is the point: the card quotes what the move would charge, and the
lock is carried by `action`, not by a nulled-out price. `action` and `requires`
come straight from `level_status(current_level, level)`, called once per level
and reused for both fields. **Amended** — the original built `change_fee` and
`is_current` here, which pushed the ladder rule into the SPA.

**`api/urls.py`**: add the four paths.

## `frontend/`

- **`src/api.ts`**: types `DevelopmentSquad` / `DevelopmentSquadLevel` /
  `DevelopmentSquadAction`, plus `getDevelopmentSquad()`,
  `openDevelopmentSquad(level)`, `changeDevelopmentSquadLevel(level)` and
  `closeDevelopmentSquad()`, using the existing `writeJson` helper the trainer
  calls use. Add both new kinds to `LedgerEntry['kind']` and to its doc
  comment.
- **`src/useDevelopmentSquad.ts`** (new): a copy of `useStaff.ts`'s lifecycle,
  with a 60-second poll and `refresh()`.
- **`src/screens/DevelopmentSquad.tsx`** (new): a header with the current state
  ("Closed", or the level name), then one card per level showing the name, the
  fee to reach it, weekly cost and "$X per season". **Amended** — the fee row
  is labelled by the rung it buys ("Open fee" on level 1, "Upgrade fee" above),
  not "Opening fee", because a level above the entry one is never opened, only
  upgraded into.

  Each card renders the server's `action` and has at most one action:
  - `open`: an **Open** button, disabled when the fee exceeds `balance`.
  - `upgrade`: an **Upgrade** button, same affordability check.
  - `current`: a **Current** badge and no button.
  - `locked`: no button at all — a padlock (inline SVG, as
    `AttributeRadar` does; there is no icon library) and the server's `requires`
    text.

  **There is no `actionFor` in the client.** The original built one, deriving
  the action from `is_current` and the sign of `change_fee`; with `action` on
  the wire it is dead weight and a second place for the rule to live. The same
  goes for the per-move footer row: the card's own fee row is the price, and
  printing it twice is noise.

  A **Close squad** button appears when the squad is open, next to copy that
  says what closing costs — nothing refunded, and reopening starts at Regional
  again — because with no downgrade it is the only way to spend less and the
  manager is choosing it under pressure. On a 409, show the server's `detail`.
  **No copy about youth intake or "coming soon"** (spec, *Decisions taken*).
  Close takes no confirmation dialog unless `Staff.tsx`'s fire does. Match it.
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
The three operations, with the locking and callback order from Design
decisions 5 and 6. **Amended by W9**: there were four operations' worth of
behaviour here, but a downgrade was one of them and it no longer exists, so
there are three.
**Tests**, same file (names as W9 left them):
- `test_open_creates_squad_and_charges_opening_fee` (a fake `charge` records its calls)
- `test_open_when_open_raises_and_charges_nothing`
- `test_charge_raising_rolls_back_open` (callback raises; no row exists afterwards)
- `test_upgrade_charges_the_target_level_s_own_fee` — *was* `..._difference`
- `test_change_level_when_closed_raises`
- `test_change_to_same_level_raises`
- `test_close_deletes_and_returns_true`
- `test_close_when_closed_returns_false`
- `test_reopen_after_close_charges_full_fee_from_the_bottom` — *was*
  `..._full_fee`, and opened at level 2; it now opens at level 1
- `test_downgrade_charges_nothing` and `test_change_fee_*` — **removed by W9**

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
- `test_squad_cost_follows_the_level_held_at_the_boundary` — **amended in W9**:
  it used to prove a mid-week *downgrade* dropped the rate to Regional, which
  the ladder no longer allows. It now does the one direction that exists —
  a mid-week upgrade to National, charged at National from the next boundary —
  and asserts both rows, so the "held at the boundary" claim is checked in both
  directions of time as well as level.

### W5 — `teams/`: claim closes the squad ✅
**Tests** in `teams/tests/` beside the existing claim tests. **Amended in W9**:
the two that go through `open_squad` opened at level 2, which is now
`LevelLocked`, so they open at level 1 — the assertion in
`test_release_keeps_development_squad` moved with them. Neither test was about
levels; one was about the *service* opening a squad at all.
- `test_claim_closes_development_squad`
- `test_release_keeps_development_squad`

### W6 — `api/`: the four endpoints ✅
**Tests** in `api/tests.py`, beside the staff tests, reusing their fixtures'
shape. **Amended by W10** — names as W10 left them:
- `test_development_squad_requires_authentication`
- `test_development_squad_without_team_is_403`
- `test_development_squad_closed_payload` (level null; only the entry level
  `open`, the rest `locked` with a note; `season_cost == weekly_cost * 12`)
- `test_every_level_is_priced_from_the_table`
- `test_open_payload_unlocks_only_the_next_level_up` (parametrised over all
  three current levels) — *replaces*
  `test_development_squad_open_payload_marks_current_and_prices_changes`
- `test_open_debits_fee` (balance drops by exactly 30,000 at level 1, one
  `development_squad_fee` row)
- `test_open_above_the_entry_level_is_409` — **new in W10**
- `test_open_refused_when_balance_too_low` (409, no row, no ledger entry)
- `test_open_invalid_level_is_400`
- `test_upgrade_debits_the_target_levels_own_fee` — *was* `..._difference`
- `test_upgrade_skipping_a_level_is_409` — **new in W10**
- `test_downgrade_is_409` — *was* `test_downgrade_debits_nothing`
- `test_open_payload_distinguishes_climbed_past_from_not_yet_reached` — **new
  in W10**; the two lock reasons are the thing a reader would otherwise assume
  are one
- `test_reopening_after_close_starts_from_the_bottom`,
  `test_reopening_above_the_entry_level_is_409` — **new in W10**
- `test_close_then_close_again_is_409`

### W7 — `frontend/`: screen, hook, nav, Finances labels ✅
**Tests** in `src/screens/DevelopmentSquad.test.tsx`, mocking
`useDevelopmentSquad` as `Staff.test.tsx` mocks `useStaff`. **Amended by W11**:
- renders three levels with fee, weekly and per-season cost in `$` format
- closed state: only the entry level offers **Open**, and no Close button
  appears — *was: each card offers Open*
- open at National: Elite offers **Upgrade**, National shows **Current**, and
  Close appears — *was: Regional also offers Downgrade*
- the fee row is labelled by the rung it buys — **new in W11**
- a locked card shows a padlock and the server's reason, and has no button —
  **new in W11**, one test per lock kind
- an action costing more than the balance is disabled, and a locked card is
  never reported as unaffordable — *extended in W11*, because a lock is not a
  price
- closing's copy says reopening starts at the bottom — **new in W11**; it is
  the only way left to spend less
- the no-riders-promise test over both subtitles, extended with the new
  closed-state subtitle

Add `'/development-squad'` to `BUILT_SCREENS` in `src/navigation.test.ts`.
Its "every nav item has a screen" test fails until you do, which is the
intended guard against the `App.tsx` mapping being forgotten.

### W8 — Documentation ✅
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

## Amendment — W9 to W12, 2026-09-28

W1–W8 were built, reviewed by hand against a running server, and then changed:
the squad became a ladder climbed one level at a time, with no downgrade and a
per-rung fee. The spec's *Amendment* records the product change and why; this
records the work. Everything W1–W8 built still stands — the model, the two
ledger kinds, the weekly charge, the tick, the claim-closes rule, the four
endpoints, the hook, the nav entry and the Finances labels are all untouched.
The changes are the pricing rule, the validation around it, the payload, and
the copy.

Four commits, one per app boundary, in the same order as W2 → W6 → W7.

### W9 — `riders/`: the ladder ✅
`LEVELS` and the model are unchanged. Everything about *which* moves are legal
and what they cost is new.

- `change_fee(current, target)` is **deleted**. It returned a different figure
  per move, and with a per-rung fee there is no per-move figure: a level's
  price is a property of the level. `level_fee(level)` replaces it.
- `level_status(current, target)` is **new**, returning a `LevelStatus` of an
  `action` (`open`/`upgrade`/`current`/`locked`) and a `note`. One function
  owns the rule, and it returns the note alongside the action because a locked
  level has two reasons that need different words — the entry-point getter
  `ENTRY_LEVEL = min(LEVELS)` is derived from the table so adding a level
  cannot leave it stale.
- `LevelLocked` and `CannotDowngrade` join the refusal family. `change_level`
  distinguishes them by comparing levels rather than asking `LevelStatus`,
  because `LevelStatus.note` is copy for the screen and an exception type is a
  promise to a caller about *why*.
- Docstrings, the module docstring and the `LEVELS` calibration comment are
  rewritten: the ordering test's justification changed, and leaving the old
  one would have claimed the code guards an exploit that can no longer happen.

**Tests**: `test_levels_rise_strictly_in_both_columns` keeps its assertion and
loses its reason. New: `test_climbing_to_the_top_costs_every_fee` (255,000 —
the total the spec quotes, pinned so a retune is deliberate), the four
`test_level_status_*` tests including one that no combination produces a
`"downgrade"` and one that a lock is never without a note, plus the refusals:
`test_open_above_the_entry_level_raises`,
`test_upgrade_skipping_a_level_raises`, `test_downgrade_raises` (parametrised
over all three descending pairs) and
`test_reopen_above_the_entry_level_raises`.

### W10 — `api/`: send the rule, don't send its parts ✅
`opening_fee` and `change_fee` collapse into `fee`; `is_current` and
`change_fee`'s null go away; `action` and `requires` arrive. The three
serializers change, and the two write views add the new exceptions to their 409
lists. `level_status` is called once per level and both fields read off the one
result.

**Tests**: the payload tests are rewritten rather than added to, and the
parametrised `test_open_payload_unlocks_only_the_next_level_up` over all three
current levels is what replaces the one open-payload test — it is the shape of
the rule, so it is worth pinning in full. `test_open_payload_distinguishes_
climbed_past_from_not_yet_reached` is the one worth arguing for: both locks
read as `locked`, and only the note tells them apart, so nothing else in the
suite would notice if the server started sending the wrong one.

The `_open_squad` test helper writes the row directly rather than calling
`open_squad`, because it exists to set up a state the ladder rule does not
allow reaching in one call, and using the service would mean every test of the
API at a higher level was really a test of the service.

### W11 — `frontend/`: one action, a padlock, the increment ✅
`DevelopmentSquadLevel` loses two fields and gains two; `actionFor` and
`ACTION_LABELS` are deleted. A `Padlock` component is added as inline SVG,
following `AttributeRadar` and `AttributeHistoryChart` — the project has no
icon library and one glyph does not justify one. The fee row is labelled "Open
fee" on level 1 and "Upgrade fee" above, the per-move footer row is deleted
(the card's own row is the price, and printing it twice was noise), and
closing's copy now states the cost of closing, since it is the only way left to
spend less and a manager picks it under pressure.

**Tests**: rewritten around a `payload(current, balance)` builder that mirrors
the server's rule, so a test cannot quietly encode a ladder the server does
not implement — that was the main risk in this W, since the old fixtures
hard-coded `change_fee: 0` for a downgrade. One test per lock kind, one for the
fee labels, one asserting a locked card offers nothing at all, and one for
closing's copy. The no-riders-promise test is extended to the new closed-state
subtitle, because that subtitle is new copy making the same promise.

### W12 — Documentation ✅
This spec and plan (the *Amended* notes above), plus `riders/README.md`,
`economy/README.md`, `api/README.md`, `frontend/README.md`,
`specs/roadmap.md` and `AGENTS.md` where they described a downgrade or a
difference-priced upgrade.

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
   show with correct per-season figures, only Regional offers **Open** and the
   other two are padlocked, and the screen says nothing about intake.
2. Open at Regional. Finances shows one "Opened development squad — Regional"
   line at −$30,000, and the balance drops by exactly that.
3. Upgrade to National: one line at −$75,000 — the level's own fee, not the
   $45,000 difference. Elite now offers **Upgrade**; Regional is padlocked as
   "Climbed past", and a forced `POST .../level/ {"level": 1}` is a 409 with no
   new line. **Amended** — the original step was "Upgrade to Elite: −$120,000,
   then downgrade for free".
4. Move the mock clock two weeks and `tick`. Finances shows two "Development
   squad — National" lines at −$3,500, **dated a week apart.** The likeliest
   failure is charging at open time as well, or dating by `now()`. That shows
   up here as three lines or two lines with the same date.
5. Close the squad, `tick` another week, and see no new squad line. Reopen it
   and confirm it offers **Open** at Regional again, not a resume at National.
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
| A level being reachable for a price the panel never quoted. | The quoted figure and the charged figure are the same call, `level_fee`; W10's payload test asserts `fee == LEVELS[n].opening_fee` in every state. |
| A padlock on a card and a 409 from the service disagreeing, because one is derived in the SPA and the other in the domain. | `level_status` is the single source and the API ships its `action` verbatim (D11); the SPA has no `actionFor`. |
| **New in the amendment:** a locked level showing a padlock and no reason, or the wrong reason — "not yet reached" and "already climbed past" need different words and only the server knows which. | `LevelStatus.note` is never null when locked, `test_every_locked_level_explains_itself` covers every state pair, and W10's `..._distinguishes_climbed_past_from_not_yet_reached` pins the two sentences. |
| **New in the amendment:** a downgrade creeping back as an unpriced move, which would be a cheaper rung to step down to and would undo the reason closing exists. | There is no "downgrade" action to derive it from, `change_level` raises `CannotDowngrade` on every descending pair, and the tick still charges the level held — so a downgraded squad would be a squad nobody can reach. |
| Someone adds intake copy to the empty-looking screen. | The spec's *Decisions taken* and the `frontend/` section both say no. |

## Open questions

None.

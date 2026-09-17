# Economy

## What this app owns

`LedgerEntry` — the append-only financial history every team's balance is
derived from. The balance itself is never stored: it is the sum of a team's
`LedgerEntry.amount` values, computed on demand. This app owns the one
recurring outgoing the game has so far — the weekly wage bill, charged once
per team per crossed week boundary — plus the entry that gives a team its
starting money and the `takeover` entry that resets a claimed team's balance.
Not prize money, sponsorship or spending (each a separate ticket, *Future
work* below).

The dependency direction is `economy -> core, teams, riders, schedule`.
Nothing may import `economy/` except `world/` and `api/` — with the single
exception that `teams/` imports one function **inside `claim_team`** to write
the takeover entry (and `teams/`'s `seed_teams` command imports
`ensure_opening_balance` inside `handle()`). See `teams/README.md`, *What
`teams/` may import*.

## The ledger is append-only

Nothing about a team's balance is ever corrected by editing or deleting a
past row. A mistake, or a deliberate reset, is recorded as a *new* row that
adjusts the balance — the way a real accounting ledger works. Concretely:

- `amount` is a **signed integer** (`BigIntegerField`): income is positive,
  spending negative, and the balance is a plain `Sum(amount)`. There is no
  `direction` field — a separate enum would require every read to branch, and
  would make a wrong-signed row silently possible. There is also no
  `balance_after` column: the running balance shown in a history is computed
  at serialization time (`api/views.py`), because a stored one would be
  wrong the moment a catch-up tick inserts rows out of order.
- The escaping hatch if the sum ever gets slow is a periodic
  opening-balance entry — still a row, never a mutable balance column. Today
  ~16 teams × ~12 weeks is a few hundred rows a season, comfortably small.

Why a cached balance column is forbidden: it can drift from the rows it
summarizes if a tick half-fails, and then the readout and the audit history
disagree with nobody noticing. The sum cannot.

## Wages run off week transitions

`world.services.tick()` calls `schedule.services.process_week_transitions()`,
which returns one `WeekTransition` row per week boundary the clock crossed
that had not been recorded, oldest first. `tick()` loops over those rows **one
week at a time** — the existing `# per week, NOT weeks=len(weeks)` loop — and
`economy.services.charge_weekly_wages(week)` is called inside that loop.

That is the load-bearing design: everything the spec asks for falls out of
machinery that already exists.

- **one entry per week, correctly dated** → the loop iterates actual `Week`
  rows, and `occurred_at` is the week's own `starts_at`, never `now()`;
- **catch-up across several weeks** → `process_week_transitions` returns all
  of them, so a three-week jump becomes three wage entries dated to three
  weeks, not one lump sum;
- **exactly-once** → the `WeekTransition` row (unique on `week`, written
  before the loop runs) is the real guarantee.

The `(team, week)` partial unique constraint on `LedgerEntry` — `unique =
(team, week)` where `kind = "wages"` — is a **second line of defence**, exactly
the way `staff.TrainingWeekReport`'s own `(team, week)` constraint backs up
`WeekTransition`. It is deliberately conditional: `week` is null on
`starting_balance` and `takeover` entries, several of which can exist for one
team. Each week's wage write runs in its own `transaction.atomic()` with the
`IntegrityError` caught and passed, one row at a time — an `IntegrityError`
poisons an enclosing transaction in Django, so a duplicate charge is *skipped
quietly* rather than aborting the rest of the week's payroll.

Wages are charged to **every** team — managed or not, empty roster or not. A
team with no riders gets a real entry at `amount = 0`, not a skipped one, so
the history has no silent gaps.

## What `economy/` may import

`core`, `teams`, `riders`, `schedule` — matching `AGENTS.md`'s dependency
graph. It must not import `world/`, `api/`, `racing/` or `competitions/`.
Like `staff/`, this app stands a bit apart from `teams/` (`teams` must not
import `economy` at module scope) precisely so the takeover write can happen
inside `claim_team` without creating a cycle.

## Future work

- **Any source of income** (prize money, sponsorship, merchandise) — #19,
  #21, #22/#23. After this ticket every balance only goes down; that is
  expected while the game has no live players yet.
- **Per-rider salaries** — #25 replaces the flat `WEEKLY_WAGE_PER_RIDER`
  with a salary derived from a rider's attributes or performance.
- **Trainer fees and recurring salaries** — #69 points a trainer's cost at
  this ledger.
- **Insolvency** — #27, what happens when a balance goes and stays deeply
  negative. This ticket only flags a negative balance, never acts on it.
- **Runway projection** — "N weeks of money left": not useful until there is
  income to make it interesting.
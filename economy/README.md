# Economy

## What this app owns

`LedgerEntry` — the append-only financial history every team's balance is
derived from. The balance itself is never stored: it is the sum of a team's
`LedgerEntry.amount` values, computed on demand. This app owns the game's
recurring money moves: the weekly wage bill (charged once per team per
crossed week boundary, the game's only recurring outgoing) and, since #21,
its first **income** — the weekly merchandise payout derived from a team's
fanbase. It also owns the entries that give a team its starting money and
the `takeover` row that resets a claimed team's balance.

`FanbaseEntry` — the append-only history every team's fanbase is derived
from, on the same discipline as the ledger (`#21`; see *Fanbase is derived
too* below). Merchandise income is the point of fanbase: a team's weekly
`LedgerEntry` is floor-divided out of its current fanbase.

Not prize money or sponsorship (each a separate ticket, *Future work*
below), and nothing players spend on yet.

The dependency direction is `economy -> core, teams, riders, schedule`.
Nothing may import `economy/` except `world/` and `api/` — with the single
exception that `teams/` imports functions **inside function bodies** (never
at module scope): the takeover and fanbase-reset writes inside `claim_team`,
and the starting-balance and starting-fanbase ensures inside `seed_teams`'
`handle()`. See `teams/README.md`, *What `teams/` may import*.

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

## Fanbase is derived too

A team's fanbase gets the same treatment as its balance: never a column on
`Team`, always the sum of a team's `FanbaseEntry` rows. Each fanbase change —
the opening grant, one `weekly` row per crossed week boundary, occasionally
a `takeover` reset — is its own append-only row, so "why did my fanbase drop
this week" answers itself from the history and a fast-forwarded tick cannot
silently lose moves.

`FanbaseEntry` is a **separate** model, not a `LedgerEntry` kind: fanbase is
not money, and reusing the ledger would corrupt `balance_for`, whose sum
would suddenly mix credits and fanbase points. The weekly rows carry their
own `(team, week)` partial unique constraint (the same exactly-once defence
wages use) and their own `points` field, recording what a week's racing was
worth so the screen can say *why* the number moved without re-querying
`competitions/`.

## Fanbase reads the completed week

Entering week N adjusts every team's fanbase off week N−1's racing, then pays
merchandise on the now-updated figure. `world.services.tick()` calls
`economy.services.apply_weekly_fanbase(week, points_by_team=...)` and
`economy.services.pay_merchandise(week)` inside its per-week transition loop,
in that order, with `occurred_at` the week's own `starts_at` — never
`now()`. There is no point reading the week being entered: the tick writes a
`WeekTransition` when a week *opens*, before that week's races are claimed
or simulated, so the opening week's `RacePoints` are always empty. Both
functions read `_completed_week(week)` for the same reason `_apply_training_week`
does — see `world/README.md`, *How a tick works*.

## Why `economy/` does not query `RacePoints`

`economy/` may not import `competitions/` (`AGENTS.md`'s dependency graph),
so `apply_weekly_fanbase` never touches a `RacePoints` row. Instead it takes
the week's points as an injected argument,
`points_by_team: dict[int, int]`, and `world/` — the app allowed to know
about everything — computes that dict from
`competitions.services.points_by_team(week)` right before the call. This is
the same inversion `competitions/README.md` documents for `racing/`.

## Fanbase is clamped at write time

A team's fanbase cannot fall below `MINIMUM_FANBASE`. The clamp applies to
the **result**, and the **stored delta gets whatever reaches the floor**:
`apply_weekly_fanbase` computes `raw = points × FANBASE_PER_POINT −
WEEKLY_FANBASE_DECAY`, then stores `max(now + raw, MINIMUM_FANBASE) − now`.
Clamping on read instead would make stored history and the displayed value
disagree — the rows would say "−500" while the fanbase stood still — and any
later arithmetic off those rows would compound the lie.

## What `economy/` may import

`core`, `teams`, `riders`, `schedule` — matching `AGENTS.md`'s dependency
graph. It must not import `world/`, `api/`, `racing/` or `competitions/`.
Like `staff/`, this app stands a bit apart from `teams/` (`teams` must not
import `economy` at module scope) precisely so the takeover write can happen
inside `claim_team` without creating a cycle.

## Future work

- **Prize money** (#19) and **sponsorship** (#22/#23) — the remaining income
  sources; #22/#23's sponsor offers read `fanbase_for`.
- **A player lever on fanbase** — #21 deliberately has none; nothing lets a
  manager spend or invest in fanbase yet.
- **Per-rider salaries** — #25 replaces the flat `WEEKLY_WAGE_PER_RIDER`
  with a salary derived from a rider's attributes or performance.
- **Trainer fees and recurring salaries** — #69 points a trainer's cost at
  this ledger.
- **Insolvency** — #27, what happens when a balance goes and stays deeply
  negative. This ticket only flags a negative balance, never acts on it.
- **A full-table read every tick** — `charge_weekly_wages` counts every
  team's riders on each wage run. Fine at dozens of teams; worth a
  `WHERE team.manager IS NOT NULL` or another efficiency when the pool
  grows. Not before — the sum is not yet a bottleneck.
- **Runway projection** — "N weeks of money left": not useful until there is
  income to make it interesting.
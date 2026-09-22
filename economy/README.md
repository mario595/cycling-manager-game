# Economy

## What this app owns

`LedgerEntry` — the append-only financial history every team's balance is
derived from. The balance itself is never stored: it is the sum of a team's
`LedgerEntry.amount` values, computed on demand. This app owns the game's
recurring money moves: the weekly wage bill and, since
[#69](https://github.com/mario595/cycling-manager/issues/69), the weekly
trainer salary — each charged once per team per crossed week boundary — and
the weekly **merchandise payout** derived from a team's fanbase, its first
income since #21. #69 also adds the one-off `trainer_fee` row written when a
team hires a trainer (see *Trainer salaries run off the same loop*). It also
owns the entries that give a team its starting money, the `takeover` row that
resets a claimed team's balance, and the `prize_money` rows a finished race
pays out (#19).

`FanbaseEntry` — the append-only history every team's fanbase is derived
from, on the same discipline as the ledger (`#21`; see *Fanbase is derived
too* below). Merchandise income is the point of fanbase: a team's weekly
`LedgerEntry` is floor-divided out of its current fanbase.

Not sponsorship (a separate ticket, *Future work* below), and nothing
players spend on yet.

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

Player-facing amounts are prefixed with `$` — see `AGENTS.md`, *Displaying
game money*. `Kind`, field and variable names in this app stay
`credit`-flavoured (`LedgerEntry`, `STARTING_BALANCE`,
`WEEKLY_WAGE_PER_RIDER`); only the display changed, not the model.

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

## Prize money reads the same way fanbase does

`pay_race_prizes(race_id, *, race_name, at, prizes_by_team)` credits a team its
winnings for one race. It takes the race as an **id** plus a plain
`prizes_by_team` dict — `{team_id: [(position, amount), ...]}` — computed by
`competitions.services.prizes_by_team`. It never reads a `Race` or a
`RaceResult` itself, and never receives a model instance tied to another app's
ORM. That is exactly the shape `world/` already hands `apply_weekly_fanbase`
for `points_by_team`, and for the same reason: `economy/` may not import
`racing/` or `competitions/` (see *What `economy/` may import*).

The `race` FK is therefore declared as the string `"racing.Race"`, not an
imported class, so `economy/models.py` imports nothing from `racing/`. It is
the same import-free pattern as `racing/models.py`'s `Race.week` and
`staff/models.py`'s `TrainingWeekReport.week` — a string FK is still a real
dependency edge, it just does not load the other app's module.

Exactly-once is the `(team, race, position)` partial unique constraint, **not**
an early return. A payout writes several rows per team (a team can place two
riders in the top ten), so "is there already a row for this team?" is the wrong
question: it would leave a team paid for its 3rd-placed rider but not its 8th
if the loop were interrupted. The constraint makes each *placement* unique, so
an interrupted payout completes on the next attempt and a re-run is a no-op.
Each placement is written in its own `transaction.atomic()` with the
`IntegrityError` caught and passed, the same idiom as `charge_weekly_wages`.

## Trainer salaries run off the same loop

`world.services.tick()` calls `economy.services.charge_trainer_salaries(week,
salary_by_team=...)` inside the same per-week transition loop as
`charge_weekly_wages`, immediately after it. A trainer's salary therefore gets
the same three guarantees wages do: one row per crossed week, dated to that
week's `starts_at` (never `now()`), a three-week catch-up producing three
separate rows, and exactly-once backed by the `WeekTransition` row. The
`(team, week)` partial unique constraint — this time where `kind =
"trainer_salary"` — is the second line of defence, and each insert runs in its
own `transaction.atomic()` with `IntegrityError` caught, the same per-row shape
wages use.

`salary_by_team` is **injected**, exactly as `apply_weekly_fanbase` takes
`points_by_team`: `economy/` may not import `staff/` (`AGENTS.md`), so
`world/` — allowed to know both — builds the `{team_pk: weekly_salary}` dict
from `staff.pricing.weekly_salary` and passes it in. A trainer's skill never
changes, so `world/` builds the dict once before the loop; the charge still
runs inside it, one dated row per missed week.

**There is deliberately no `amount = 0` row for a team with no trainer.** This
is the one asymmetry with wages, and it is not a bug: every team has a wage
bill (possibly zero) and is charged it every week, whereas "no trainer" means
no salary obligation at all. A team with no trainer simply has no
`trainer_salary` row, and the unique constraint above is unaffected. The hire
fee is the mirror image: `charge_trainer_fee(team, amount=..., at=...,
description=...)` writes a single negative row at the moment of hiring, with
`week` left null and **no** `(team, week)` constraint — a team may legitimately
pay several fees in a season, and a test asserts that.

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

The prize-money `race` FK does **not** change this: it is declared as the
string `"racing.Race"`, so nothing in `economy/` imports `racing/`. Likewise
`prizes_by_team` arrives as plain data, so no `competitions/` import is needed.

## Future work

- **Sponsorship** (#22/#23) — the remaining income source; sponsor offers
  read `fanbase_for`.
- **A player lever on fanbase** — #21 deliberately has none; nothing lets a
  manager spend or invest in fanbase yet.
- **Per-rider salaries** — #25 replaces the flat `WEEKLY_WAGE_PER_RIDER`
  with a salary derived from a rider's attributes or performance.
- **Insolvency** — #27, what happens when a balance goes and stays deeply
  negative. This ticket only flags a negative balance, never acts on it.
- **A full-table read every tick** — `charge_weekly_wages` counts every
  team's riders on each wage run. Fine at dozens of teams; worth a
  `WHERE team.manager IS NOT NULL` or another efficiency when the pool
  grows. Not before — the sum is not yet a bottleneck.
- **Runway projection** — "N weeks of money left": not useful until there is
  income to make it interesting.
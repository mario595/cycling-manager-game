# Economy

## What this app owns

`LedgerEntry` — the append-only financial history every team's balance is
derived from. The balance itself is never stored: it is the sum of a team's
`LedgerEntry.amount` values, computed on demand. This app owns the game's
recurring money moves: the weekly wage bill — since
[#25](https://github.com/mario595/cycling-manager/issues/25), the sum of
each rider's own `weekly_salary`, never a flat per-head rate — and, since
[#69](https://github.com/mario595/cycling-manager/issues/69), the weekly
trainer salary — each charged once per team per crossed week boundary — and
the weekly **merchandise payout** derived from a team's fanbase, its first
income since #21. #69 also adds the one-off `trainer_fee` row written when a
team hires a trainer (see *Trainer salaries run off the same loop*), and the
free-agent market (#29) adds the one-off `transfer_fee` row written on a
signing or a release, and rider auctions (#28) add that same kind's credit
side — a won auction pays the seller and debits the buyer, both
`transfer_fee` rows (see *Free-agent fees* below). It also
owns the entries that give a team its starting money, the `takeover` row that
resets a claimed team's balance, and the `prize_money` rows a finished race
pays out (#19). A development squad (#32) adds two more: the recurring
`development_squad` weekly cost and the one-off `development_squad_fee` for
opening or upgrading (see *Development squad costs* below).

`FanbaseEntry` — the append-only history every team's fanbase is derived
from, on the same discipline as the ledger (`#21`; see *Fanbase is derived
too* below). Merchandise income is the point of fanbase: a team's weekly
`LedgerEntry` is floor-divided out of its current fanbase.

`SolvencyCheck` — the weekly assessment of a managed team that is, or was,
insolvent (`#27`; see *Insolvency* below). A row exists only when it
matters, so the latest row of the current managerial spell is the whole
state.

`SponsorOffer` and `SponsorContract` — a team's sponsorship (`#22`; see
*Sponsorship* below). A team picks one of three fanbase-sized offers each
season, and its weekly payment then swings with race results inside a
promised range.

Nothing players spend on yet.

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

**The charge is a sum of each rider's own `weekly_salary`
([#25](https://github.com/mario595/cycling-manager/issues/25)), not a head
count times `WEEKLY_WAGE_PER_RIDER`.** That constant still exists — it is
now only the average a generated rider's salary is calibrated to land near,
never charged directly; see `riders/README.md`, *Salary*. Because the sum
reads `Team.riders` (a `team` FK), a development squad rider (#33) — whose
`team` is always null — is never in it: the squad's own weekly cost, charged
separately above, is what pays for them (`riders/README.md`, *Youth
intake*). `charge_weekly_wages`
annotates `Sum("riders__weekly_salary")` alongside the existing rider-count
annotation and wraps it in `Coalesce(..., 0)` — a team with no riders makes
`Sum` return `None`, and `amount=-None` would raise rather than write the
real zero row the paragraph above requires. `economy.services.payroll_for(team)`
exposes the same sum for one team, on demand, for the Finances screen's
wage-bill tile — it reads the roster as it stands *now*, not the last
`LedgerEntry` written, since a manager can buy or sell a rider between
paydays.

## Salary review

At every season close, `riders.services.reprice_all()` recomputes every
rider's `weekly_salary` from the pricing formula (after ageing — see
`world/README.md`, *How a tick works*), and `economy.services.
write_salary_reviews(season, changes)` writes one `SalaryReviewReport` per
**managed** team recording what that did to the payroll. It mirrors
`staff.TrainingWeekReport`: a season-change the player did not directly
trigger, surfaced as a report rather than left silent.

**Why the model lives here and not in `riders/`.** The report needs a
`Team` FK and a `Season` FK; `riders/` may not depend on `schedule/` at
all, and the report is a statement about a team's wage bill, which is this
app's subject. Keeping it in `staff/` next to `TrainingWeekReport` would be
wrong too — that model lives there because training focus is a staff
concept, not because it is a report.

**The shape.** One `SalaryReviewReport` row per `(team, season)`, enforced
by a `UniqueConstraint` — the same second line of defence the `(team,
week)` wage constraint gives the weekly charge, backing up the
`SeasonTransition` row that guarantees repricing runs once. Each `create()`
runs inside its own `transaction.atomic()` with the `IntegrityError`
caught and passed, one row at a time: an `IntegrityError` poisons an
enclosing transaction in Django, so catching it inside a shared one fails
the next statement with `TransactionManagementError`. Copy the
`process_transitions()` shape, never one `atomic()` around the whole loop.

**How far the field moved (#166).** Salaries are priced against the
field's level (`riders/README.md`, *Salary*), so a rider who improved less
than everyone else can see a pay cut. `write_salary_reviews` therefore
takes `field_change_percent`, how much stronger (positive) or weaker the
rostered field got that close, worked out in `world.services.
field_change_percent(before, after)` from the factor before and after
repricing, and stores it on every report of that season. The roster screen
shows it as one line ("The field got 6% stronger this season, and wages are
set against it."). It is null for reports written before #166 and is 0
when the level did not move, and neither shows a line.

**Free agents are repriced but generate no report.** `reprice_all()`
covers every rider; `write_salary_reviews` iterates managed teams only, so
an unrostered rider's salary move is silent. A managed team with no
qualifying changes still gets a report — `changes` is an empty list and
`payroll_before == payroll_after`, so the season leaves a trace.

Two deliberate imprecisions, both worth recording:

- **`changes` is filtered, not exhaustive.** `reprice_all()` always writes
  every rider's exact formula value, but only returns movements of at
  least `SALARY_REVIEW_THRESHOLD` (`riders/pricing.py`); the threshold
  filters the *report*, never the write, so a stored salary can never
  drift from the formula on behalf of a quiet rounding step.
- **`payroll_before` is derived, not captured**: `payroll_after` minus the
  net of the *listed* changes. That is exact only because sub-threshold
  changes are included in `payroll_after` but omitted from `changes` — a
  deliberate "what the bill was counting only the movements we are showing
  you", instead of a second per-team query for a number that differs by
  at most a rounding step per rider. `payroll_after` itself is
  `payroll_for(team)` read over the post-reprice roster, which is exact.

`latest_salary_review(team)` (newest season first, `None` if there isn't
one) feeds the Roster screen's salary-review panel; `api/` serializes it
onto the roster payload as `salary_review`.

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

### General classification prize money

`pay_gc_prizes(final_stage_id, *, stage_race_name, at, prizes_by_team)` is
`pay_race_prizes`'s twin for a stage race's general classification — both
now share a private `_pay_prizes` writer, parameterised on `kind`. It is
written under `LedgerEntry.Kind.GC_PRIZE_MONEY`, **not** `PRIZE_MONEY`, and
that separation is load-bearing rather than tidiness: a stage race's final
stage can owe a team both its own stage prize and a GC prize at the exact
same `(team, race, position)` (a rider who wins the last stage and leads
the GC, say). Sharing `PRIZE_MONEY`'s constraint would make the second
write collide with the first's `(team, race, position)` row and silently
no-op — exactly the "already paid" outcome the constraint is supposed to
mean, except nothing was actually paid twice. `race` on a `gc_prize_money`
row is the stage race's **final stage**, not a row of its own kind; `world.
services._settle_stage_race` calls this once, the moment the whole stage
race completes. See `racing/README.md`, *Stage races*, and `competitions/
README.md`, *Stage races*.

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

## Development squad costs

Two kinds, and **one kind covers both opening and upgrading**
(`development_squad_fee`), the mirror of the transfer market's single
`transfer_fee` (Design decision 10 in
`specs/archive/development-squad-plan.md`). Opening, upgrading and reopening
are the same shape of transaction — money out, no week attached, named by
`description` ("Opened development squad — Regional" vs "Upgraded development
squad to Elite") — so a second kind would be a distinction with nothing behind
it. It is also all the fee transactions there are: with no downgrade, a *close*
is the only remaining move, and it writes nothing at all.

Every one of those fees is the target level's own price, charged in full
(`riders/README.md`, *Development squad*), so climbing to Elite debits three
rows totalling 255,000 rather than one. The ledger is where the shape of that
climb is visible afterwards, which is the point of the fee-per-rung rule: three
rows in the finances history read as a ladder, where one would not.

The recurring weekly cost is a **separate** kind, `development_squad`, and the
split is not tidiness. That row needs the `(team, week)` partial unique
constraint that makes a re-tick harmless, and a one-off fee must not be swept
up by it — a team can upgrade on Monday and reopen on Tuesday, and both are
real rows the player paid for. Sharing `trainer_salary`'s constraint would
have silently dropped the second one.

`charge_development_squad_costs(week, cost_by_team=...)` runs inside the same
per-week transition loop as wages and trainer salaries, immediately after
them, and `charge_development_squad_fee(team, *, amount, at, description)`
writes a single negative row with `week` null, exactly the shape
`charge_trainer_fee` uses. `cost_by_team` is **injected**, and
`economy/` never looks up `riders.development_squad.LEVELS` for itself: it
maps team pk to `(weekly_cost, level_name)`, with the name because it goes
straight into the row's `description`, and `world/` — which may import both —
builds it. `economy/` may import `riders/` (`AGENTS.md`), but a dict keeps the
function trivially testable and identical in shape to its neighbour.

**The weekly cost is charged at the boundary, at the level the squad holds
when the tick processes that boundary** (Design decision 7) — dated to the
week's `starts_at`, never `now()`. Nothing is prorated and nothing is charged
at the moment of opening. A squad opened mid-week is therefore first charged
at the *next* boundary: the opening fee covers the remainder of the opening
week. This is not a special case invented for squads; it is how wages and
trainer salaries already behave, and a mid-week change to a level is charged
at the new rate from the following boundary. Note the consequence honestly:
if a tick has not run for several weeks, a squad opened during the gap is
charged for every week in it, including the one it was only part-way through.
The alternative — prorating — would mean a differently-dated row for the same
week, which the `(team, week)` constraint would then reject at the boundary.

**`kind` was widened from `max_length=20` to `32`.** `development_squad_fee`
is 21 characters, so the old limit was one short of a name actually in use.
The old value was never a real constraint — every earlier value fitted well
inside it — just a round number that had not yet met a name that did not.
Postgres enforces the column, not Django's `max_length`, so without the
`AlterField` in `0011_development_squad_kinds.py` the very first squad fee
would have failed at the database. A test asserts the widest name still
validates.

## Free-agent fees

`economy.services.charge_transfer_fee(team, *, amount, at, description)`
writes a single negative `transfer_fee` row at the moment of a free-agent
signing or a paid roster release — `week` null, no `(team, week)`
constraint, several per season allowed, exactly the shape
`charge_trainer_fee` above uses. It is not called from `world/` (nothing
automatic charges it) and not from `transfers/` (which may not import
`economy/`): `api/`'s free-agent views invoke it through the injected
`charge` callback the actions take (`transfers/README.md`, *Free agents*),
with `description` naming the rider and the direction — "Signed X" or
"Released X". A $0 release — a rider still within the claim cooldown — is
skipped at the call site (`api/` only writes when the fee is positive):
no money moved, no row.

There is deliberately **one** kind for both directions. A signing fee and a
release severance are the same shape of transaction — money out, no week
attached — so they share `TRANSFER_FEE` and are told apart by `description`
(Design decision 7). The Finances screen renders them under one **Transfer
fee** label.

**`economy.services.pay_transfer_income(team, *, amount, at, description)`**
is the credit-side mirror, added for rider auctions (#28): same
`TRANSFER_FEE` kind — a sale is still "money moved for a transfer reason,"
just told apart by `description` and sign — but a deliberately **separate**
function rather than a repurposing of `charge_transfer_fee`, whose
docstring is an explicit, tested "amount is negative, debits only"
contract. `amount` here is always positive. Unlike the free-agent fee
(charged from `api/`), this one is called from `world.services.
_resolve_expired_auctions`, alongside `charge_transfer_fee` for the
buyer's debit — both injected into `transfers.services.resolve_auction`
as callbacks, since `transfers/` may not import `economy/` — see
`world/README.md`, *How a tick works*, and `transfers/README.md`,
*Auctions*.

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
`points_by_team` sums finish points **and** both kinds of marker points
(#16, #17), so a sprint- or climb-heavy week moves both fanbase and
sponsorship, the same as a strong finish would — see `competitions/README.md`,
*Marker points*. One dict, one number per team: the two marker kinds are kept
apart everywhere a player can read them, but a fanbase and a sponsorship
payment do not care which way a team earned its points.

## Fanbase is clamped at write time

A team's fanbase cannot fall below `MINIMUM_FANBASE`. The clamp applies to
the **result**, and the **stored delta gets whatever reaches the floor**:
`apply_weekly_fanbase` computes `raw = points × FANBASE_PER_POINT −
WEEKLY_FANBASE_DECAY`, then stores `max(now + raw, MINIMUM_FANBASE) − now`.
Clamping on read instead would make stored history and the displayed value
disagree — the rows would say "−500" while the fanbase stood still — and any
later arithmetic off those rows would compound the lie.

## Sponsorship

A team picks at most one sponsor per season, from three offers generated at
season open (and again whenever the team is claimed). Signing turns an
offer into a permanent `SponsorContract`; the weekly payment then varies
with race results but always stays inside the range shown at signing. See
`specs/archive/sponsorship-contracts.md` and its plan for the product and technical
story in full — this section is the load-bearing rules a future change must
not break.

**Two models, not one with a flag.** `SponsorOffer` is disposable — a round
is regenerated wholesale (season open, or a claim), which means deleting a
team's unsigned offers. `SponsorContract` is permanent financial history.
Keeping them separate makes that delete structurally unable to touch signed
history: the query that clears a round can never accidentally clear a
contract, because contracts are not rows in that table.

**Unmanaged teams always sign the steady offer** (#45), from
`world/ai_management.py`'s `sign_ai_sponsors`: at season open, straight after
the round is generated, and at any later week boundary for an unmanaged team
with no contract that season (one released mid-season). It goes through
`sign_offer` like the API, so nothing here knows the AI exists. See
`world/README.md`, *The AI management (#45)*.

**A contract copies its terms; it never reads them through its offer.**
`weekly_base`, `floor_amount`, `ceiling_amount` and `sensitivity` are
columns on `SponsorContract` itself, copied at signing — `sign_offer`
(`economy/services.py`) writes them onto the contract before deleting the
rest of the round. `offer` survives only as a nullable, `SET_NULL`
provenance link. The offer that produced a contract is usually deleted
minutes later (the rest of its round, on signing; the whole thing, on a
later void) — a contract that read `weekly_base` through `self.offer` would
go blind, or worse, silently repriced, the moment that row is gone.

**The floor and ceiling are stored, not recomputed at payment time.** The
range shown at signing is a promise; recomputing it later from
`SPONSOR_CREDITS_PER_THOUSAND_FANS` or a profile's fractions would let a constant
tuning change silently reprice a contract someone already signed against a
different number.

**Payment is computed against the team's own season-to-date average**, not
the field's. `economy.services._season_average_points` reads the team's own
`FanbaseEntry.points` for every settled week this season (this app already
owns that number — no need to touch `competitions/`) and
`economy.sponsors.payment_for` scales the contract's `weekly_base` by how
this week's points compare to that average, clamped into
`[floor_amount, ceiling_amount]`. A team with no settled week yet this
season (week 1, or freshly claimed) has no average and is paid
`weekly_base` exactly — the same result a zero-sensitivity `STEADY`
contract always gets. Relative-to-field was rejected: it would make a
team's income a function of *other* teams' results, illegible on a
finances screen.

**Three fixed profiles, always all three in a round.**
`economy/sponsors.py`'s `PROFILES` — `steady` (flat, lower baseline),
`balanced`, `demanding` (higher baseline, wider swing) — are a constant
table, not rolled. A round is always one of each, so the three cards on the
Sponsors screen are never near-identical; rolling three independent
sensitivities could produce exactly that.

**A team with no contract gets no ledger row for that week — not a
zero-amount one.** Unlike wages (charged to every team, `rider_count=0`
included), an empty sponsorship slot is the normal long-run state for a
team that never signed, matching how `#69`'s trainer salary already treats
an unfilled slot.

**Claiming a team voids its contract; it does not delete it.**
`teams.services.claim_team` calls `economy.services.void_sponsorship`
(imported inside the function body — see *What `economy/` may import*),
which sets `voided_at` on any active contract and clears unsigned offers.
The contract row survives as history; it simply stops paying. A new round
is not generated here — `claim_team` has no `Season` to hand it, and
`teams/` may not import `schedule/`. `api.views.SponsorsView` generates the
fresh round lazily on the newly-claimed manager's first read.

**Idempotent per `(team, season)`.** `ensure_offer_round` no-ops if the
team already has offers for that season or an active contract — the
`UniqueConstraint` on `(team, season, profile)` backs this the same way
`(team, week)` backs wages. This is what lets both `world.services.tick()`
(on every `SeasonTransition.Kind.OPENED`) and the API's lazy path call it
freely without ever doubling a round.

**Weekly payment joins the tick after merchandise.**
`world.services.tick()` calls `economy.services.pay_sponsorship(week,
points_by_team=...)` right after `pay_merchandise(week)`, reusing the same
`points_by_team` dict already built for fanbase — `economy/` may not import
`competitions/` (`AGENTS.md`), so the caller supplies points, same
inversion `apply_weekly_fanbase` already uses. Running after fanbase
matters because `_season_average_points` reads settled `FanbaseEntry` rows;
by the time sponsorship pays, this week's own fanbase row already exists
but is excluded (`week__number__lt`), so only genuinely prior weeks count.

**Telling a manager they have no sponsor (#161).** `sponsor_gap(team,
season)` is `None` when the team has an active contract for that season,
otherwise the highest `floor_amount` among its waiting offers (the most a
week signing can guarantee) or `0` when there is no round yet. It reports
the floor, never `weekly_base`, for the same reason the Sponsors screen
never shows the base on its own. `economy/` does not decide which season is
"this one": `api.views.MeView` passes the current in-season `Season` and
turns the answer into `me.team.sponsor_missing` and
`me.team.guaranteed_weekly`, which the dashboard banner and the sidebar dot
read. There is deliberately no auto-sign for managed teams and no back-pay
of unsigned weeks; see `specs/archive/unsigned-sponsor-warning.md`.

## Insolvency

A managed team is **insolvent** when its balance is negative after a week's
payday (#27; `specs/archive/insolvency-ladder.md` for the product story).
This section is the load-bearing rules a future change must not break. The
code is `economy/solvency.py`.

**State is rows, not a flag.** `SolvencyCheck` — one row per `(team, week)`,
backed by a unique constraint — is written only when it matters: a managed
team whose balance is negative after payday, or whose open case needs its
closing recovery row. A solvent team with no open case gets nothing. "Is this
team insolvent?" is therefore *the latest check in its current spell has a
negative balance* (`open_check`). There is deliberately no `is_insolvent` on
`Team`: a cached flag drifts from the ledger it summarises, the way a cached
balance would, and `teams/` would have to learn about insolvency.

**A claim clears it for free.** Only checks with `occurred_at >=
team.managed_since` count, so a claimed team's older checks fall out of scope
with no write in `claim_team`. The assessment also skips a team claimed after
the boundary it is judging, so a catch-up tick never holds a new manager to a
week they did not run. A team with no `managed_since` counts every check.

**Strikes** are consecutive paydays with the target unmet, the opening payday
included:

| previous (this spell) | balance | row | strikes |
|---|---|---|---|
| none / non-negative | `>= 0` | none | — |
| none / non-negative | `< 0` | case opens | 1, or 0 with no shortfall |
| open | `< 0` | written | previous + 1, or 0 with no shortfall |
| open | `>= 0` | recovery row, case closes | 0 |

`INSOLVENCY_LOSS_STRIKES` (4) strikes loses the team. `world/` reads
`assess_solvency`'s `lost` list and releases the team; `economy/` never
imports `teams.services`. The previous check must be read **before** the new
row is created, or every case looks already open.

**The target.** `weekly_shortfall` is regular outgoings minus regular income,
floored at 0. Outgoings are the roster's payroll, the trainer's salary and the
squad's weekly cost; income is merchandise plus the signed sponsor's *base*
payment. Prize money is left out because it is irregular, and the
results-driven swing of a sponsor is left out because the base is the
promised figure. The trainer salary and squad cost arrive as plain numbers
from the caller — `economy/` may not read `staff/` or `riders/`'s price
tables, the same inversion `charge_trainer_salaries` uses. The target is
computed from the roster **as it stands**, not from the last wage row, so a
forced sale mid-week has already lowered it by payday.

**The embargo lives in `api/`.** `is_embargoed(team)` is `open_check(team)
is not None`. The views that add cost or spend cash — signing a free agent,
bidding, hiring a trainer, opening or upgrading a development squad, promoting
a squad rider or graduate onto the roster (#34) — return
409 with `EMBARGO_MESSAGE`, next to the existing affordability checks, because
`transfers/`, `staff/` and `riders/` may not import `economy/`. Signing a
sponsor, firing, closing, releasing, ordinary listing and discarding a squad
rider stay open: each cuts cost, adds income, or adds nothing. The embargo outlasts the escalation: it lifts only when a
payday ends with a balance of zero or more.

**Status for the screens.** `solvency_status` is the read model behind
`GET /api/economy/solvency/`: the live shortfall, `target` (the shortfall at
the last payday), `cut_so_far` (`target` minus the live shortfall, so it resets
every payday), `paydays_left` (null once the live shortfall is zero) and
`deadline` (the start of the week that payday falls in, or null when that week
is not declared yet). Nothing about the deadline is stored.

## Balance targets

What the money is *meant* to do, set by #125 (`specs/archive/economy-break-even.md`).
A change to any income or cost constant (sponsor rate, prize tables, salary
pricing, trainer prices, merchandise) should be checked against these by
re-running the measurement, not by reasoning about one flow in isolation.

1. **The average team breaks even, slightly ahead.** With a steady sponsor,
   the cheapest trainer it can get, no development squad and no transfers,
   a team that races about as well as the field ends a settled season roughly
   **$10,000–$20,000 up**.
2. **The top quarter makes a clear profit**, several times the average.
3. **The bottom quarter loses money slowly**, slowly enough that a starting
   balance lasts several seasons. Insolvency is the result of racing badly
   for a long time, not a property of the prices.

Optional spending (a development squad, transfer buying) is deliberately
*not* covered: it is paid for by racing above average or by spending the
starting balance.

**The levers #125 moved.** Sponsorship grew ×2.2 — `SPONSOR_CREDITS_PER_THOUSAND_FANS`
went from the old `fanbase // 2` (500 per thousand) to **1,100**, so a steady
offer at the starting fanbase pays $9,350 a week — and all three prize tables
(`competitions/scoring.py`) rose 10%. Wages, merchandise, trainer prices,
development squad prices and the starting balance were left alone. Most of the
new money is sponsorship, which every team gets, so the gap between strong and
weak teams widened only a little.

**Wages priced against the field (#166).** Before #166 salaries were priced
on absolute strength, so as riders trained the average wage bill grew
season on season ($181k, $202k, $220k, $228k on a four-season world-calendar
run, AI teams only) while income barely moved, and the average net slid to
−$14k by season 4. With pricing against the field the same run paid $167k,
$177k, $174k and $173k (field factor 0.93, 0.83, 0.76, 0.72 after each
close), and the average net was +$7k, +$33k, +$44k and +$51k, median +$29k
in season 4. The average now sits above target 1 from season 2 on and still
creeps up with sponsorship, which follows fanbase; that is an income-side
question and was left for a balance ticket.

**The measurement.** `.venv/bin/python scripts/measure_economy.py` drops and
recreates this checkout's dev database, seeds a world (16 unmanaged teams),
plays seasons 1 and 2 a day at a time on the mock clock and prints every
ledger kind per season plus the season-2 spread. It takes about 25 minutes.
Transfer fees are excluded from the net (AI market churn, not a structural
flow). Season 2 is the steady state, because season 1 carries the trainer's
one-off hire fee.

Season 2, average per team, before and after #125:

| Ledger kind | Before | After |
|---|---|---|
| Sponsorship | 48,909 | 108,778 |
| Prize money + GC prizes | 92,625 | 108,075 |
| Merchandise | 4,341 | 4,415 |
| Trainer salary | −34,538 | −37,725 |
| Wages | −179,888 | −172,725 |
| **Net** | **−68,550** | **+10,818** |
| Bottom quarter / median / top quarter | −135,528 / −92,188 / +47,262 | −89,820 / +11,816 / +151,394 |

**Runs are noisy.** Wages, trainer prices and fanbase differ between seeds,
so the average moves by about ±$8,000 from run to run. Three runs during #125,
at rates 1,250, 1,150 and 1,100, measured +$28,159, +$26,228 and +$10,818. Do not
tune to a single run near an edge of the band.

**#156: claimed teams, not prices.** On staging in season 3 the AI field
was on target (median about +$65,000), while every LLM tester team lost money:
they earned $2,000–$10,000 of prize money against an AI median of about $80,000.
A claim used to hand out a fresh, day-one roster, and by season 3 that ranked
about 14th of 16 by squad strength. Since #156 a claimant keeps the team's
riders and is given the free team nearest the middle of the field
(`teams/README.md`, *Claiming a team*). The measurement now claims one team
just before season 2 and prints its season next to the unmanaged field. Two
runs of the shipped code claimed the 8th and 9th of 16 by squad strength, and
their season-2 nets were −$61,116 and −$24,580 (ahead of 3 and 5 of 15
unmanaged teams).

One experiment, not shipped, gave the claimed team the AI's course-aware squad
pick instead of the course-blind default that a manager who does not choose
gets. That team (8th of 16) made −$4,734, ahead of 7 of 15. This suggests the
default pick costs a passive manager part of the gap.

**Wages outgrow income in a mature world.** A four-season AI-only run on the
world calendar (`seasons/world.json`) measured average wages of $181k, $202k,
$220k and $228k across seasons 1–4. Riders train and are repriced at every
close, while income barely moves (sponsorship +9%, a fixed prize pot). The
average net goes −$5k, +$4k, −$10k, −$14k, and by season 4 the median team
loses about $70,000 a season while the top quarter makes +$219,000. This was
found during #156 and is not fixed by it.

**Prize money is a shared pot.** Each race pays a fixed table split by
placing, so the average team's share falls as the field grows. The targets
hold for a field of about sixteen teams. The pyramid will need its own pass.

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

- **Sponsor renewal** (#23) — at season end, whether the incumbent sponsor
  re-offers, and at what price. Narrower than it once looked: in-season
  payment is already performance-sensitive (see *Sponsorship* above), so
  #23 only has to decide what happens *between* seasons.
- **A player lever on fanbase** — #21 deliberately has none; nothing lets a
  manager spend or invest in fanbase yet.
- **Insolvency for unmanaged teams.** #27 assesses managed teams only.
  Since #125 the average unmanaged team breaks even (see *Balance targets*),
  but the bottom quarter still loses money slowly. Revisit once staging has
  shown the economy holding over several seasons.
- **A full-table read every tick** — `charge_weekly_wages` counts every
  team's riders on each wage run. Fine at dozens of teams; worth a
  `WHERE team.manager IS NOT NULL` or another efficiency when the pool
  grows. Not before — the sum is not yet a bottleneck.
- **Runway projection** — "N weeks of money left": not useful until there is
  income to make it interesting.
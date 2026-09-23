# Team finances ledger — Implementation Plan

**Spec:** `specs/team-finances-ledger.md` · **Issue:** #20 · **Status:** implemented
**Apps touched:** `economy/` (new), `world/`, `teams/`, `api/`, `frontend/`

## Context you need

The game has no money at all today. `economy/` is listed in `AGENTS.md` as
*not yet* built — this ticket creates it. Read `AGENTS.md` first (the app
table and the dependency graph), then `world/README.md` (the tick) and
`teams/README.md` (claiming).

What exists today that this work plugs into:

- **`world/services.py::tick()`** is the only thing that makes time pass. It
  already calls `schedule.services.process_week_transitions(at)`, which
  returns a list of `WeekTransition` rows — **one per week boundary that had
  not been recorded yet**, oldest first. `tick()` then loops over them:
  `for transition in weeks: riders_trained += _apply_training_week(transition.week)`.
  That comment in the code — `# per week, NOT weeks=len(weeks)` — is the
  existing precedent for exactly the per-week behaviour the spec requires.
- **`schedule.models.WeekTransition`** has a `UniqueConstraint` on `week`.
  This is the exactly-once guarantee for anything hung off a week boundary,
  and it is written *before* wages would run.
- **`schedule.models.Week`** has `season`, `number` (1–12), `starts_at`,
  `ends_at`, all game time.
- **`teams.models.Team`** — `name`, `code`, `manager` (nullable
  `OneToOneField`), colours. No money field, deliberately.
- **`riders.models.Rider.team`** is a `ForeignKey` with
  `related_name="riders"`, so `team.riders` is the roster.
- **`teams.services.claim_team()`** runs one `transaction.atomic()`: locks an
  unmanaged team, renames it, releases its riders, generates a new roster.
- **`competitions.services.standings()`** aggregates `RacePoints` rows on
  every call rather than storing a running total, with the reasoning written
  down in `competitions/README.md` (*Standings are computed, not stored*).
  That precedent applies directly here.
- **`staff/`** is the most recent app built and is the closest model for
  this one: `models.py`, `services.py`, a `README.md`, serializers and views
  in `api/`, a hook and a screen in `frontend/`.

Repo rules this work is bound by: `AGENTS.md`'s dependency direction — the
new app sits at `economy -> core, teams, riders, schedule`, and **nothing
may import `economy/` except `world/` and `api/`**; Postgres everywhere;
tests are pytest via `.venv/bin/python -m pytest`; frontend styling is
inline `style={{}}` with colours from `src/theme.ts`, never hex literals.

## Goal

When this is done:

1. A new `economy/` app exists, with a `README.md` and its first migration.
2. Every team's balance is derived by summing an append-only
   `LedgerEntry` table — there is no balance column anywhere.
3. Every team starts at a fixed balance, via a ledger entry written when
   the team is created.
4. Each week boundary the tick crosses debits every team one combined
   `wages` entry, dated to that week — one entry per week, even when the
   clock catches up several weeks at once.
5. Claiming a team writes a `takeover` adjustment entry bringing its
   balance back to the standard starting amount, without deleting anything.
6. `GET /api/economy/finances/` returns the caller's balance and history,
   and a Finances screen renders it, flagging a negative balance.

## Design decisions (settled — implement these, do not substitute)

**D1. The balance is a SQL aggregate over `LedgerEntry.amount`, never a
stored column.**

`balance_for(team)` is `LedgerEntry.objects.filter(team=team).aggregate(
Sum("amount"))["amount__sum"] or 0`. The spec makes append-only a hard
requirement and `AGENTS.md` repeats it; a cached balance column is the
thing it is forbidding, because it can drift from the rows if a tick
half-fails.

*Do not* add `Team.balance`. *Do not* add a `balance_after` column to
`LedgerEntry` either — the running balance shown in the history is computed
in Python when serializing (D7), because a stored one is wrong the moment
any entry is inserted out of order during clock catch-up.

The size argument is the same one `competitions/README.md` already makes:
~16 teams × ~12 weeks is a few hundred rows a season. When that stops being
true, the fix is a periodic opening-balance entry, not a mutable column.

**D2. `amount` is a signed integer. Income is positive, expenditure is
negative. There is no `direction` field.**

One column, one sign convention, and the balance is a plain `Sum`. A
separate `direction` enum means every read has to branch, and makes a
wrong-signed row silently possible.

`amount` is `BigIntegerField` — **not** `PositiveIntegerField` (it must go
negative) and **not** `DecimalField`: the spec settles currency as abstract
whole-number credits with no decimals.

**D3. Wages run off `WeekTransition` rows, inside the tick's existing
per-week loop.**

This is the load-bearing decision of the ticket. `tick()` already does:

```python
weeks = process_week_transitions(at)
for transition in weeks:            # per week, NOT weeks=len(weeks)
    riders_trained += _apply_training_week(transition.week)
```

Add the wage run to that same loop. Everything the spec asks for falls out
of machinery that already exists and is already tested:

- one entry per week, correctly dated → the loop iterates actual `Week` rows;
- catch-up across several weeks → `process_week_transitions` returns them all;
- exactly-once → `WeekTransition`'s unique-on-`week` constraint, written
  before the loop runs.

*Do not* write a separate catch-up routine that compares "last wage run" to
`now()`. *Do not* hang wages off `SeasonTransition` (wrong cadence). *Do
not* add a `last_paid_at` field to `Team` — that is a second, weaker copy of
a guarantee `WeekTransition` already gives.

**D4. A second line of defence: `unique(team, week)` on wage entries, via a
partial constraint.**

`WeekTransition` is the real guarantee, exactly as `TrainingWeekReport`'s
docstring in `staff/models.py` explains for its own case. But a
`UniqueConstraint` on `(team, week)` with
`condition=Q(kind=Kind.WAGES)` makes double-charging impossible at the
database level too. It must be conditional: `week` is null on
`starting_balance` and `takeover` entries, and several of those can exist
for one team.

Wrap each week's wage write in its own `transaction.atomic()` with
`IntegrityError` caught and passed — the same per-row shape
`process_transitions` and `_write_training_reports` use, and for the same
stated reason: **an `IntegrityError` poisons an enclosing transaction in
Django.**

**D5. One wage entry per team per week, for the whole roster.**

The spec is explicit: twelve riders produce one "Weekly wages" entry, not
twelve. `amount` is `-(roster_count * WEEKLY_WAGE_PER_RIDER)`, and
`rider_count` is stored on the row so the history can say *why* the number
is what it is without re-deriving a roster that has since changed.

**D6. Unmanaged teams are charged too, with no special case.**

`Team.objects.all()`, not `.filter(manager__isnull=False)`. The spec says
the economy applies uniformly. Writing the filter now means #45's AI later
has to discover that fifteen of sixteen teams have no financial history.

A team with an empty roster gets `rider_count=0` and `amount=0` — a real
row, not a skipped one, so the history has no silent gaps.

**D7. The running balance in the history is computed at serialization time,
oldest-to-newest, then reversed for display.**

The API returns entries newest-first (spec rule 9) but each carries the
balance *after* it. Compute by walking the entries in chronological order
accumulating a running total, then reverse. Doing it newest-first by
subtracting is the natural first attempt and it is off-by-one at the
boundary.

**D8. `claim_team` writes a `takeover` entry; it never deletes rows.**

The amount is whatever brings the balance to `STARTING_BALANCE`:
`STARTING_BALANCE - balance_for(team)`. This is the append-only ledger's
own idiom for a correction, and it satisfies #46's recorded decision.

The write goes **inside** `claim_team`'s existing `transaction.atomic()`, so
a half-claimed team with a reset roster but an unreset balance is not
observable — the same invariant that block already protects.

**This means `teams/` imports `economy/`,** which inverts the dependency
graph (`economy -> teams`). Resolve it the way `AGENTS.md` and
`teams/management/commands/seed_teams.py` already resolve the same problem:
**import inside the function, not at module scope.** Add a note to
`teams/README.md`'s *What `teams/` may import*. The alternative — a signal
on `Team.save` — is worse: it hides a financial write behind an implicit
hook and fires on every unrelated save.

**D9. A team's starting balance is written by a `post_save` — no. It is
written explicitly by `ensure_opening_balance(team)`, called from
`claim_team` and from `seed_teams`.**

Explicit over implicit, for the same reason as D8. The function is
idempotent (`get_or_create` on `kind=STARTING_BALANCE`) so re-running
`seed_teams` cannot double-credit a team.

**D10. Constants live in `economy/models.py`, not in settings.**

`STARTING_BALANCE = 500_000` and `WEEKLY_WAGE_PER_RIDER = 1_200` are game
balance, not deployment configuration. A twelve-rider team burns 14,400 a
week, so the starting balance covers roughly 34 weeks — comfortably past a
twelve-week season, which is what the spec asks for in *Decisions taken*.
`WEEKLY_WAGE_PER_RIDER` is what #25 replaces with a per-rider salary.

## Data model

New app `economy/`, one model.

### `economy.models.LedgerEntry`

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `team` | `ForeignKey("teams.Team", on_delete=CASCADE, related_name="ledger_entries")` | no | — | Deleting a team deletes its financial history; it has no meaning without the team. |
| `kind` | `CharField(max_length=20, choices=Kind.choices)` | no | — | `TextChoices`, below. |
| `amount` | `BigIntegerField` | no | — | Signed credits. Negative is expenditure. Never `Positive*`, never `Decimal` — D2. |
| `occurred_at` | `DateTimeField` | no | — | **Game** time. For wages, the week's own `starts_at` — not the moment the tick noticed. Same rule as `SeasonTransition.occurred_at`. |
| `week` | `ForeignKey("schedule.Week", on_delete=SET_NULL, null=True, blank=True, related_name="ledger_entries")` | yes | `None` | Set on `wages` entries only. Null elsewhere. |
| `rider_count` | `PositiveSmallIntegerField` | no | `0` | How many riders this charge covered. Meaningful only on `wages`; `0` elsewhere. |
| `description` | `CharField(max_length=120)` | no (`blank=False`) | — | Player-facing label, e.g. `"Weekly wages"`. Written at creation; never recomputed. |

Inherits `core.models.TimeStampedModel`, giving `created_at`/`updated_at` as
**real** time — distinct from `occurred_at`, exactly as
`SeasonTransition` separates `occurred_at` from `recorded_at`.

```python
class Kind(models.TextChoices):
    STARTING_BALANCE = "starting_balance", "Starting balance"
    WAGES = "wages", "Weekly wages"
    TAKEOVER = "takeover", "Team taken over"
```

`Meta`:

```python
ordering = ["-occurred_at", "-pk"]
constraints = [
    models.UniqueConstraint(
        fields=["team", "week"],
        condition=models.Q(kind="wages"),
        name="one_wage_entry_per_team_per_week",
    ),
]
indexes = [
    models.Index(fields=["team", "-occurred_at"], name="ledger_team_recent_idx"),
]
```

The `-pk` tiebreak in `ordering` is load-bearing: a takeover entry and a
wage entry can share an `occurred_at` to the microsecond under `MockClock`,
and without it the history order is nondeterministic between reads.

The constraint's `condition` uses the literal `"wages"`, not
`Kind.WAGES` — a `TextChoices` member serializes into the migration as its
enum repr in some Django versions and produces a spurious no-op migration
on every subsequent `makemigrations`.

Migration: `economy/migrations/0001_initial.py`.

## `economy/services.py` (new)

```python
def balance_for(team) -> int
def entries_for(team) -> QuerySet[LedgerEntry]
def ensure_opening_balance(team) -> LedgerEntry
def reset_to_starting_balance(team) -> LedgerEntry | None
def charge_weekly_wages(week) -> int
```

`charge_weekly_wages` is the only one worth spelling out — it is where the
natural first attempt is wrong:

```python
def charge_weekly_wages(week) -> int:
    """Debit every team one combined wage entry for `week`. Returns how
    many entries were written.

    Called once per crossed week boundary from world.services.tick(),
    inside the loop over WeekTransition rows. Exactly-once comes from that
    WeekTransition row (unique on `week`, written before this runs); the
    (team, week) constraint below is a second line of defence.

    One atomic() per create, never one around the loop: an IntegrityError
    poisons the enclosing transaction in Django. Same shape as
    schedule.services.process_transitions and staff's
    _write_training_reports, for the same reason.
    """
    counts = dict(
        Team.objects.annotate(n=Count("riders")).values_list("pk", "n")
    )
    written = 0
    for team_id, rider_count in counts.items():
        with transaction.atomic():
            try:
                LedgerEntry.objects.create(
                    team_id=team_id,
                    kind=LedgerEntry.Kind.WAGES,
                    amount=-(rider_count * WEEKLY_WAGE_PER_RIDER),
                    occurred_at=week.starts_at,
                    week=week,
                    rider_count=rider_count,
                    description="Weekly wages",
                )
                written += 1
            except IntegrityError:
                continue          # already charged; correct outcome, not an error
    return written
```

`Count("riders")` on a single annotated query, not `team.riders.count()` per
team — the latter is N+1 across every team in the world, every week.

`reset_to_starting_balance` returns `None` when the delta is zero, so a team
claimed at exactly the starting balance does not get a meaningless 0-credit
row.

## `world/services.py`

One import and one line inside the existing week loop:

```python
from economy.services import charge_weekly_wages
...
weeks = process_week_transitions(at)
riders_trained = 0
wage_entries = 0
for transition in weeks:            # per week, NOT weeks=len(weeks)
    riders_trained += _apply_training_week(transition.week)
    wage_entries += charge_weekly_wages(transition.week)
```

Add `wage_entries` to the `TickRun.objects.create(...)` call (see below).

**Order within the loop is deliberate: training first, then wages.** Both
are independent, but keeping the existing call first means the diff does
not reorder tested behaviour.

## `world/models.py`

Add one field to `TickRun`, matching its existing counters:

```python
wage_entries = models.PositiveIntegerField(
    default=0,
    help_text="Ledger wage entries written this tick.",
)
```

Migration: `world/migrations/00XX_tickrun_wage_entries.py`.

## `teams/services.py`

Inside `claim_team`'s existing `transaction.atomic()`, after the roster is
generated:

```python
        team.riders.update(team=None)
        Rider.objects.bulk_create(generate_roster(roster_size, team=team))

        # Imported here, not at module scope: teams/ must not import
        # economy/ at import time (AGENTS.md's dependency direction). Same
        # rule and reason as seed_teams.py importing racing.models inside
        # handle().
        from economy.services import reset_to_starting_balance
        reset_to_starting_balance(team)
```

## `api/serializers.py`, `api/views.py`, `api/urls.py`

- `LedgerEntrySerializer` — `kind`, `description`, `amount`, `occurred_at`,
  `rider_count`, `balance_after`.
- `FinancesSerializer` — `balance`, `entries`.
- `FinancesView(APIView)` — `get`, resolving the team via the existing
  `team_for(request.user)`. Returns `{"balance": 0, "entries": []}` for a
  user with no team, matching how `StaffView` handles the same case.
- `path("economy/finances/", FinancesView.as_view(), name="finances")`.

`balance_after` is computed in the view per D7 — walk chronologically
accumulating, then reverse.

## `frontend/`

- `src/api.ts` — `LedgerEntry`, `Finances` interfaces and `getFinances()`.
- `src/useFinances.ts` — new hook, copied in shape from `useStaff.ts`:
  `{ finances, loading, error }`, 60s poll, renders nothing while loading.
- `src/screens/Finances.tsx` — balance headline (negative shown in
  `color.danger` or equivalent from `theme.ts`, with a warning line) and the
  history list, newest first.
- `src/navigation.ts` — add `{ path: '/finances', name: 'Finances' }` to the
  `TEAM` section, after Staff. `App.tsx` generates the route from
  `NAV_ITEMS`, so no routing change beyond registering the screen in
  `SCREENS`.

## Work items

### W1 — `economy/`: create the app
**[x] done**
`startapp economy`, add to `LOCAL_APPS` in `config/settings/base.py`,
write `economy/README.md`, add `economy/models.py` with `LedgerEntry`,
`Kind`, `STARTING_BALANCE`, `WEEKLY_WAGE_PER_RIDER`, and generate
`0001_initial`.
**Test:** `economy/tests/test_models.py::test_ledger_entry_roundtrips`, plus
`test_wage_entries_are_unique_per_team_per_week` asserting `IntegrityError`
on a duplicate, and `test_non_wage_entries_are_not_constrained` writing two
`takeover` rows for one team to prove the partial condition works.
*Load-bearing:* the constraint's `condition`, and that it does not bite
non-wage rows.

### W2 — `economy/services.py`: balance, opening balance, reset
**[x] done**
`balance_for`, `entries_for`, `ensure_opening_balance`,
`reset_to_starting_balance`.
**Test:** `economy/tests/test_services.py` — `test_balance_is_zero_with_no_entries`,
`test_balance_sums_signed_amounts`,
`test_ensure_opening_balance_is_idempotent`,
`test_reset_writes_the_difference` (balance already moved → new entry brings
it exactly to `STARTING_BALANCE`, and **the prior entries still exist**),
`test_reset_at_starting_balance_writes_nothing`.

### W3 — `economy/services.py`: `charge_weekly_wages`
**[x] done**
**Test:** `economy/tests/test_wages.py` —
`test_charges_every_team_once`, `test_amount_is_roster_times_wage`,
`test_unmanaged_teams_are_charged`,
`test_empty_roster_is_charged_zero_not_skipped`,
`test_second_call_for_same_week_writes_nothing` (idempotency at the
constraint), `test_occurred_at_is_the_weeks_start`.
*Load-bearing:* the second-call test, and that the first call's entries are
unchanged by it.

### W4 — `world/`: wire wages into the tick
**[x] done**
Import and call inside the existing week loop; add `TickRun.wage_entries`
and its migration.
**Test:** `world/tests/test_tick.py` —
`test_tick_charges_wages_for_the_week_it_crosses`,
`test_catch_up_charges_each_missed_week_separately` (move `MockClock`
forward three weeks, one tick, assert **three** entries with three distinct
`occurred_at` values matching the three weeks' `starts_at`),
`test_running_tick_twice_does_not_double_charge`.
*Load-bearing:* the catch-up test. This is the spec's rule 7 and the whole
reason for D3.

### W5 — `teams/`: reset balance on claim
**[x] done**
The function-scope import and call in `claim_team`.
**Test:** `teams/tests/test_services.py` —
`test_claim_resets_balance_to_starting_amount`,
`test_claim_preserves_prior_ledger_entries` (assert the pre-claim entries
are still queryable afterwards — this is the append-only guarantee, and the
test that catches someone "simplifying" it to a delete).

### W6 — `api/`: the finances endpoint
**[x] done**
Serializers, view, url.
**Test:** `api/tests.py` — `test_finances_requires_a_session`,
`test_finances_returns_balance_and_entries`,
`test_entries_are_newest_first_with_running_balance`
(assert the oldest entry's `balance_after` equals the starting balance, and
the newest equals `balance`), `test_finances_for_a_user_with_no_team`.
*Load-bearing:* the running-balance test — D7's off-by-one lives here.

### W7 — `frontend/`: the Finances screen
**[x] done**
`api.ts` additions, `useFinances.ts`, `screens/Finances.tsx`, the nav item,
the `SCREENS` registration.
**Test:** `frontend/src/screens/Finances.test.tsx` — renders nothing while
loading, renders balance and entries, and shows the warning when the
balance is negative.

### W8 — `teams/`: seed an opening balance
**[x] done**
Call `ensure_opening_balance` for each team in `seed_teams` (function-scope
import, same as W5).
**Test:** `teams/tests/test_seed_teams.py::test_seeded_teams_have_an_opening_balance`
and `::test_reseeding_does_not_double_credit`.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7, with W8 any time after W2.

W1 first because nothing else has anywhere to go. W2 before W3 because
`charge_weekly_wages`'s tests assert on `balance_for`. **W3 before W4 is the
important one:** it proves the wage logic against a `Week` row directly,
with no tick involved, so when W4's catch-up test fails you already know the
charging itself is correct and the bug is in the wiring.

W6 and W7 are read-only over everything above and cannot break it.

Commit at the end of each work item; each leaves the suite green.

## Documentation update (required, not optional)

**`economy/README.md` (new, in W1).** Sections: *What this app owns*;
*The ledger is append-only* (D1, D2, D8 — why there is no balance column and
why a correction is a new row); *Wages run off week transitions* (D3, D4,
naming `WeekTransition` as the real guarantee and the constraint as the
second line); *What `economy/` may import*; *Future work* listing #19, #25,
#27, #69 with the one-line reason each is not here.

**`AGENTS.md`.** Mark `economy/` **built**, `README.md` in the app table,
and add `economy -> core, teams, riders, schedule` to the dependency graph.
Add the Finances screen to the `frontend/` row.

**`teams/README.md`.** Under *What `teams/` may import*, record the
function-scope `economy/` import and why. In *Future work*, the
"Resetting a claimed team's money" bullet is now **done** — replace it with
a pointer to D8's behaviour.

**`world/README.md`.** In *How a tick works*, step 1 now also charges wages
per crossed week; add the sentence and the `TickRun.wage_entries` counter.

**`staff/README.md`.** Its *Future work* says trainer pricing waits on
"the ledger (`economy/`) exists" — it now does. Update the bullet to say
#69 is unblocked.

**`api/README.md`** and **`frontend/README.md`.** The new endpoint and the
new screen, in the existing lists.

## Verification

```bash
.venv/bin/python -m pytest
```

Then, end to end, in a worktree with a mock clock:

```bash
.venv/bin/python manage.py seed_user
.venv/bin/python manage.py seed_teams --claim-for test@mail.com
.venv/bin/python manage.py load_season seasons/season-1.example.json
GAME_CLOCK_CLASS=world.clocks.MockClock .venv/bin/python manage.py mock_clock set <season start>
GAME_CLOCK_CLASS=world.clocks.MockClock .venv/bin/python manage.py tick
```

Log in and open Finances: one starting-balance entry, one takeover entry,
and the balance at `STARTING_BALANCE`.

**The likeliest failure mode is the catch-up case** — wages charged once for
a multi-week jump, or charged with the wrong date. The specific check:

```bash
GAME_CLOCK_CLASS=world.clocks.MockClock .venv/bin/python manage.py mock_clock set <season start + 3 weeks>
GAME_CLOCK_CLASS=world.clocks.MockClock .venv/bin/python manage.py tick
```

The history must then show **three separate wage entries**, dated to three
different weeks — not one, not four. A single entry means the per-week loop
was collapsed; a wrong date means `occurred_at` was taken from `now()`
instead of `week.starts_at`.

Then run `tick` again immediately with the clock unmoved: the entry count
must not change. An assertion that only ever runs against a freshly migrated
database with one week elapsed cannot fail and proves nothing.

## Risks

| Risk | Mitigation |
|---|---|
| Wages collapsed into one charge for a multi-week catch-up — the single likeliest error | D3 puts the call inside the existing per-week loop that already carries the `# per week, NOT weeks=len(weeks)` comment; W4's `test_catch_up_charges_each_missed_week_separately` is the guard |
| A reviewer "simplifies" the claim reset into deleting the old rows | W5's `test_claim_preserves_prior_ledger_entries`; the reasoning is in `economy/README.md` and D8 |
| `IntegrityError` inside a loop-level transaction poisoning it, silently aborting the rest of the week's charges | One `atomic()` **per create**, never around the loop — stated in `charge_weekly_wages`'s docstring, and the shape already used twice elsewhere in the repo |
| The `(team, week)` constraint accidentally blocking a second `takeover` entry | The partial `condition=Q(kind="wages")`; W1's `test_non_wage_entries_are_not_constrained` |
| A cached balance column reintroduced later "for performance" | D1's reasoning in `economy/README.md`, with the opening-balance-entry escape hatch named so there is a sanctioned answer |
| `economy/` imported at module scope from `teams/`, inverting the graph | Function-scope import with the reason in a comment; a real cycle surfaces as an `ImportError` at Django startup, so the suite catches it immediately |
| N+1 roster count across every team, every week | `Team.objects.annotate(Count("riders"))` in one query — spelled out in the service body |

## Open questions

None.

# Fanbase and merchandise revenue — Implementation Plan

**Spec:** `specs/fanbase-and-merchandise-revenue.md` · **Issue:** [#21](https://github.com/mario595/cycling-manager/issues/21) · **Status:** proposed
**Apps touched:** `economy/`, `world/`, `api/`, `frontend/`

## Context you need

`economy/` already exists and shipped last week ([#20](https://github.com/mario595/cycling-manager/issues/20),
PR #76). Read `economy/README.md` before anything else — this plan extends
that app and is bound by the discipline it records. The short version:

- **`LedgerEntry`** (`economy/models.py`) is an append-only financial history.
  `amount` is a signed `BigIntegerField` — income positive, spending negative.
  There is deliberately **no balance column anywhere**; `balance_for(team)` is a
  `Sum("amount")`. There is no `balance_after` column either — `api/views.py`
  computes the running balance at serialization time.
- **`charge_weekly_wages(week)`** (`economy/services.py`) is the existing
  once-per-week write. It is called from `world.services.tick()` inside the
  `for transition in weeks:` loop — the loop commented `# per week, NOT
  weeks=len(weeks)`. Copy its shape exactly; this plan's new weekly write is
  its sibling.
- **Exactly-once** comes from the `WeekTransition` row (unique on `week`,
  written by `schedule.services.process_week_transitions` *before* the loop
  runs). The `(team, week)` partial unique constraint on `LedgerEntry` is a
  **second line of defence**, not the guarantee. Each write runs in its own
  `transaction.atomic()` with `IntegrityError` caught and passed, because an
  `IntegrityError` poisons an enclosing transaction in Django.

The results data this feature reads is **`competitions.RacePoints`**
(`competitions/models.py`): one row per team per race, but **only for teams
finishing in the top 10** — `score_race` filters `points_for(position) > 0`.
A team finishing 14th, a team whose squad all abandoned, and a team that
entered nobody all produce *no row*. This is why the spec chose passive
decay; see Design decision 2. `RacePoints` reaches a week through
`race__week`, so "this team's points in week N" is one query.

Repo rules this work is bound by (check `AGENTS.md`, do not trust this list):

- **Dependency direction.** `economy -> core, teams, riders, schedule`.
  `economy/` **must not import `competitions/`** — that edge does not exist in
  the graph. This is the single biggest constraint on this plan; Design
  decision 1 is how it is honoured.
- Nothing may import `world/` or `api/`.
- Tests are pytest: `.venv/bin/python -m pytest`.
- Postgres in dev and prod alike.

`specs/roadmap.md` puts this immediately after #20 and **before** #22/#23
(sponsorship), which price their offers off fanbase. Nothing this plan needs
is unbuilt.

## Goal

When this is done:

1. Every team has a fanbase derived from an append-only history of weekly
   changes — never a stored mutable number.
2. Once per crossed week boundary, each team's fanbase is adjusted: a fixed
   passive decay, offset by a gain computed from the race points it scored in
   the week that just completed.
3. Fanbase never falls below a floor.
4. Immediately after that adjustment, each team is paid a merchandise income
   derived from its now-current fanbase, written as its own `LedgerEntry`.
5. Claiming an unmanaged team resets its fanbase to the standard starting
   figure via a new entry, never by deleting rows.
6. The Finances screen shows the team's current fanbase and this week's change
   to it, alongside the balance.

## Design decisions (settled — implement these, do not substitute)

### D1. `world/` computes the points, `economy/` receives them. **Load-bearing.**

`economy/` may not import `competitions/`. The natural first attempt —
`economy.services.apply_weekly_fanbase()` querying `RacePoints` itself — is a
dependency-graph violation that will pass tests and be caught in review.

Instead, mirror how scoring already avoids the same problem (`racing/` must
never import `competitions/`, so `world.services.tick()` calls `score_race`
right after `simulate_race`):

- `competitions.services.points_by_team(week) -> dict[int, int]` — new. Maps
  team id to total race points scored in that week. `competitions` may import
  `schedule`, so this is legal.
- `economy.services.apply_weekly_fanbase(week, *, points_by_team) -> int` —
  new. Takes the mapping as a **plain dict argument**. It never learns where
  the numbers came from.
- `world/services.py` wires the two together inside the existing per-week loop.

Do **not** put the `RacePoints` query in `economy/`, and do **not** add a
`competitions -> economy` edge to make it convenient.

### D2. Fanbase reads the week that just *completed*, not the week being entered. **Load-bearing.**

This is the subtlest part of the feature and the one most likely to be got
wrong.

A `WeekTransition` is written when a week **opens**. In `tick()`, the
week-transition loop runs **before** `_claim()` and `_execute()` — so at the
moment week N's transition is processed, **week N's races have not been
simulated yet**. Querying `RacePoints` for week N there always returns
nothing, and every team would decay forever.

`world/services.py` already solves this for training: `_completed_week(week)`
returns the week before `week` in the same season, or `None` for week 1.
**Reuse that exact function.** Entering week N adjusts fanbase off week N−1's
points.

Consequence to accept, not fix: week 1 of a season has no preceding week, so
every team takes plain decay with no offset that week. Cross-season carry-over
is out of scope, matching the same decision already recorded in
`world/README.md`.

### D3. Fanbase is a sum of `FanbaseEntry` rows, never a column on `Team`.

The spec requires a recorded history of weekly changes. Apply the ledger's own
discipline and for the same reasons (`economy/README.md`, *The ledger is
append-only*): a cached number can drift from the rows that explain it if a
tick half-fails, and then the readout and the history disagree with nobody
noticing.

A separate model rather than reusing `LedgerEntry`: fanbase is not money, is
not summed into the balance, and must never appear on the Finances history as
a transaction. Sharing the table would make `balance_for`'s `Sum("amount")`
silently wrong.

### D4. The floor is applied at write time, by clamping the delta.

The floor must hold against the **sum**, not against a single row. Compute the
team's current fanbase, apply the raw delta, clamp the result to
`MINIMUM_FANBASE`, then store `clamped_result - current` as the row's `delta`.

Do **not** clamp by storing the raw delta and clamping on read — the sum is
the fanbase, so a read-time clamp makes stored history and displayed value
disagree, and a later recovery would have to climb back through phantom
negative rows before showing any movement.

### D5. Growth is linear in the week's points, decay is a flat constant.

```
raw_delta = (points_this_week * FANBASE_PER_POINT) - WEEKLY_FANBASE_DECAY
```

Both constants live in `economy/models.py` alongside `STARTING_BALANCE` and
`WEEKLY_WAGE_PER_RIDER` — game balance, not deployment configuration, exactly
as that file's existing comment argues. Not in settings.

Values (tunable, chosen to make the spec's "meaningful but not sufficient"
true — see D6 for the arithmetic):

```python
STARTING_FANBASE = 10_000
MINIMUM_FANBASE = 1_000
WEEKLY_FANBASE_DECAY = 150
FANBASE_PER_POINT = 40
```

Decay applies to **every** team every week including winners — a winning week
is a gain that outweighs the same decay, not decay skipped (spec, *Rules and
edge cases*). Implement it as one subtraction applied unconditionally; do not
branch on whether the team scored.

### D6. Merchandise pays a fixed rate per unit of fanbase, floored to a whole credit.

```
amount = fanbase // CREDITS_PER_FANBASE_DIVISOR
```

with `MERCHANDISE_CREDITS_PER_FANBASE = 1` per 25 fans, expressed as an
integer divisor to keep credits whole (the ledger is `BigIntegerField`, never
`Decimal` — `economy/README.md`).

```python
MERCHANDISE_FANBASE_PER_CREDIT = 25
```

Sanity check against the spec's "meaningful, not sufficient": a 12-rider team
costs `12 * 1_200 = 14_400` a week. At `STARTING_FANBASE = 10_000` merchandise
pays `400` — about 2.8% of the wage bill. A strong team scoring ~60 points a
week gains `60*40 - 150 = 2_250` fanbase a week, so after a twelve-week season
it sits near `37_000` and earns `~1_480` a week, ~10% of wages. Visible,
nowhere near solvency. Prize money (#19) and sponsorship (#22) are what close
the rest of the gap; do not retune these constants to make the economy balance
now.

### D7. Fanbase is written first, merchandise second, in that order, in the same loop pass.

Spec rule 6: merchandise is paid on the **now-updated** fanbase. Within one
week's processing, call `apply_weekly_fanbase(...)` then
`pay_merchandise(week)`. `pay_merchandise` recomputes each team's fanbase from
the rows — it does not accept a number from the previous call, so the two
functions stay independently testable and a re-run cannot pay on a stale
figure.

### D8. The merchandise entry is a new `LedgerEntry.Kind`, reusing the existing week-uniqueness pattern.

`LedgerEntry.Kind.MERCHANDISE = "merchandise"`. It needs its own partial
unique constraint on `(team, week)` — the existing
`one_wage_entry_per_team_per_week` is conditioned on `kind="wages"` and does
**not** cover the new kind. Add a second, separately named constraint; do not
widen the existing one to cover both kinds, which would make a team's wage and
merchandise entries for one week mutually exclusive.

`rider_count` stays `0` on merchandise entries (its help text already says it
is meaningful only on wages).

### D9. Claiming a team resets fanbase inside the existing `claim_team` transaction.

`teams/services.py`'s `claim_team` already imports
`economy.services.reset_to_starting_balance` **inside the function body** to
avoid a module-scope `teams -> economy` import. Add
`reset_fanbase(team, *, at)` to the same deferred import and call it in the
same transaction. Same idiom, same reason — do not move either import to
module scope.

Like `reset_to_starting_balance`, it returns `None` when the team already sits
at `STARTING_FANBASE`, so a freshly seeded team claimed immediately does not
get a meaningless zero-delta row.

### D10. `economy/` still may not import `world/`; callers pass `at`.

Every new write takes an explicit `at` (game time) from its caller, exactly as
`ensure_opening_balance` and `reset_to_starting_balance` already do. The
weekly functions take a `Week` and use `week.starts_at` — never `now()`, never
`timezone.now()`.

## Data model

### `economy/models.py` — new constants

```python
STARTING_FANBASE = 10_000
MINIMUM_FANBASE = 1_000
WEEKLY_FANBASE_DECAY = 150
FANBASE_PER_POINT = 40
MERCHANDISE_FANBASE_PER_CREDIT = 25
```

### `economy/models.py` — new model `FanbaseEntry(TimeStampedModel)`

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `team` | `FK("teams.Team", on_delete=CASCADE, related_name="fanbase_entries")` | no | — | Deleting a team deletes its fanbase history. |
| `kind` | `CharField(max_length=20, choices=Kind.choices)` | no | — | `starting`, `weekly`, `takeover`. |
| `delta` | `IntegerField()` | no | — | Signed. Already floor-clamped at write time (D4). `IntegerField`, not `BigInteger` — fanbase moves in hundreds. |
| `occurred_at` | `DateTimeField()` | no | — | Game time. For weekly rows, the week's own `starts_at`. |
| `week` | `FK("schedule.Week", on_delete=SET_NULL, null=True, blank=True, related_name="fanbase_entries")` | yes | `None` | Set on `weekly` rows only. Null elsewhere. |
| `points` | `PositiveSmallIntegerField(default=0)` | no | `0` | Race points that drove this row. Meaningful on `weekly` only. Stored so the screen can say *why* it moved without re-querying `competitions`. |
| `description` | `CharField(max_length=120)` | no | — | Player-facing label, written at creation, never recomputed. |

```python
class Kind(models.TextChoices):
    STARTING = "starting", "Starting fanbase"
    WEEKLY = "weekly", "Weekly change"
    TAKEOVER = "takeover", "Team taken over"
```

`Meta`:

```python
ordering = ["-occurred_at", "-pk"]
constraints = [
    models.UniqueConstraint(
        fields=["team", "week"],
        condition=models.Q(kind="weekly"),
        name="one_fanbase_entry_per_team_per_week",
    ),
]
indexes = [
    models.Index(fields=["team", "-occurred_at"], name="fanbase_team_recent_idx"),
]
```

### `economy/models.py` — `LedgerEntry.Kind`

Add `MERCHANDISE = "merchandise", "Merchandise revenue"`.

Add to `LedgerEntry.Meta.constraints`:

```python
models.UniqueConstraint(
    fields=["team", "week"],
    condition=models.Q(kind="merchandise"),
    name="one_merchandise_entry_per_team_per_week",
),
```

### `world/models.py` — `TickRun`

Add, matching the existing `wage_entries` field's shape:

```python
merchandise_entries = models.PositiveIntegerField(
    default=0, help_text="Ledger merchandise entries written this tick (#21).",
)
fanbase_entries = models.PositiveIntegerField(
    default=0, help_text="Fanbase change entries written this tick (#21).",
)
```

### Migrations

- `economy/migrations/0002_fanbaseentry_merchandise.py` — creates
  `FanbaseEntry`, adds the `merchandise` choice to `LedgerEntry.kind`, adds the
  merchandise unique constraint. One migration; these ship together.
- `world/migrations/0007_tickrun_merchandise_fanbase.py` — the two counters.

No data migration. Existing teams have no `FanbaseEntry` rows and therefore a
fanbase of 0 until backfilled — W2 covers this via `ensure_starting_fanbase`
being called from the same places `ensure_opening_balance` already is.

## `economy/services.py`

```python
def fanbase_for(team) -> int:
    """A team's fanbase: the sum of its FanbaseEntry deltas. Derived,
    never stored — same discipline as balance_for."""

def fanbase_entries_for(team) -> QuerySet[FanbaseEntry]:
    """A team's fanbase history, newest first (the model default)."""

def ensure_starting_fanbase(team, *, at) -> FanbaseEntry:
    """Give `team` its starting fanbase, once. Idempotent via
    get_or_create on kind=STARTING, like ensure_opening_balance."""

def reset_fanbase(team, *, at) -> FanbaseEntry | None:
    """Bring `team`'s fanbase back to STARTING_FANBASE with a `takeover`
    row. Returns None when it already is STARTING_FANBASE."""

def apply_weekly_fanbase(week, *, points_by_team: dict[int, int]) -> int:
    """Adjust every team's fanbase for `week`. Returns rows written."""

def pay_merchandise(week) -> int:
    """Credit every team merchandise income for `week`, computed off its
    current fanbase. Returns entries written."""
```

The two weekly functions, where the natural attempt is subtly wrong:

```python
def apply_weekly_fanbase(week, *, points_by_team) -> int:
    current = dict(
        FanbaseEntry.objects.values("team_id").annotate(total=Sum("delta"))
        .values_list("team_id", "total")
    )
    written = 0
    for team_id in Team.objects.values_list("pk", flat=True):
        points = points_by_team.get(team_id, 0)
        now_at = current.get(team_id) or 0
        raw = points * FANBASE_PER_POINT - WEEKLY_FANBASE_DECAY
        # Clamp the RESULT, store the delta that gets there (D4).
        delta = max(now_at + raw, MINIMUM_FANBASE) - now_at
        with transaction.atomic():
            try:
                FanbaseEntry.objects.create(
                    team_id=team_id,
                    kind=FanbaseEntry.Kind.WEEKLY,
                    delta=delta,
                    occurred_at=week.starts_at,
                    week=week,
                    points=points,
                    description="Weekly fanbase change",
                )
                written += 1
            except IntegrityError:
                continue          # already applied; correct outcome
    return written
```

Note `current` is built from one grouped query over all teams, not a
`fanbase_for` call per team inside the loop — at ~16 teams either works, but
the N+1 shape is the one that rots.

```python
def pay_merchandise(week) -> int:
    current = dict(
        FanbaseEntry.objects.values("team_id").annotate(total=Sum("delta"))
        .values_list("team_id", "total")
    )
    written = 0
    for team_id in Team.objects.values_list("pk", flat=True):
        fanbase = max(current.get(team_id) or 0, 0)
        amount = fanbase // MERCHANDISE_FANBASE_PER_CREDIT
        with transaction.atomic():
            try:
                LedgerEntry.objects.create(
                    team_id=team_id,
                    kind=LedgerEntry.Kind.MERCHANDISE,
                    amount=amount,
                    occurred_at=week.starts_at,
                    week=week,
                    description="Merchandise revenue",
                )
                written += 1
            except IntegrityError:
                continue
    return written
```

A team with zero fanbase gets a real `amount = 0` entry, not a skipped one —
same rule `charge_weekly_wages` already follows for an empty roster, so the
history has no silent gaps.

## `competitions/services.py`

```python
def points_by_team(week) -> dict[int, int]:
    """Total race points each team scored in `week`. Teams that scored
    nothing are absent from the mapping — callers treat a missing key as 0.

    Read by world.services.tick() and handed to economy's fanbase
    adjustment: economy/ may not import competitions/ (AGENTS.md), so the
    caller does the join. Same shape as score_race being called from
    world/ rather than from racing/.
    """
    rows = (
        RacePoints.objects.filter(race__week=week)
        .values("team_id").annotate(total=Sum("points"))
    )
    return {row["team_id"]: row["total"] for row in rows}
```

Needs `from django.db.models import Sum` at the top of the module.

## `world/services.py`

Inside `tick()`, in the existing per-week loop:

```python
    weeks = process_week_transitions(at)
    riders_trained = 0
    wage_entries = 0
    merchandise_entries = 0
    fanbase_entries = 0
    for transition in weeks:            # per week, NOT weeks=len(weeks)
        week = transition.week
        riders_trained += _apply_training_week(week)
        wage_entries += charge_weekly_wages(week)

        # Fanbase reads the week that just COMPLETED, not the one opening:
        # this loop runs before _claim()/_execute(), so `week`'s own races
        # have not been simulated yet (D2). Same reason _apply_training_week
        # uses _completed_week().
        raced_week = _completed_week(week)
        points = points_by_team(raced_week) if raced_week is not None else {}
        fanbase_entries += apply_weekly_fanbase(week, points_by_team=points)
        merchandise_entries += pay_merchandise(week)
```

New imports: `from competitions.services import points_by_team, score_race`
and `from economy.services import apply_weekly_fanbase, charge_weekly_wages,
pay_merchandise`.

Pass both new counters to the `TickRun.objects.create(...)` call.

## `teams/services.py`

In `claim_team`, extend the existing deferred import:

```python
        from economy.services import reset_fanbase, reset_to_starting_balance
        reset_to_starting_balance(team, at=at)
        reset_fanbase(team, at=at)
```

Inside the same `transaction.atomic()` block. Do not move the import to module
scope (D9).

## `teams/management/commands/seed_teams.py`

Extend the existing deferred import block so every seeded team gets a starting
fanbase alongside its opening balance:

```python
            from economy.services import ensure_opening_balance, ensure_starting_fanbase
            ...
            for team in Team.objects.all():
                ensure_opening_balance(team, at=at)
                ensure_starting_fanbase(team, at=at)
```

Both are `get_or_create`-backed, so re-running `seed_teams` stays safe.

## `api/serializers.py`

- `LedgerEntrySerializer` — no field change needed; `kind` is already a plain
  `CharField`, so `"merchandise"` passes through.
- `FinancesSerializer` — add two fields:

```python
    fanbase = serializers.IntegerField()
    fanbase_change = serializers.IntegerField()
```

`fanbase_change` is the most recent `weekly` entry's `delta`, or `0` when
there is none. Spec decision: the player sees the change, not two raw numbers
to diff.

## `api/views.py`

`FinancesView.get` — after the existing balance work:

```python
        latest = fanbase_entries_for(team).filter(
            kind=FanbaseEntry.Kind.WEEKLY,
        ).first()          # model ordering is -occurred_at, -pk
        return Response(FinancesSerializer({
            "balance": balance_for(team),
            "fanbase": fanbase_for(team),
            "fanbase_change": latest.delta if latest else 0,
            "entries": entries,
        }).data)
```

The no-team early return gains `"fanbase": 0, "fanbase_change": 0` so the
empty state still serializes.

## `frontend/src/api.ts`

- `LedgerEntry['kind']` union gains `'merchandise'`.
- `Finances` gains `fanbase: number` and `fanbase_change: number`.

## `frontend/src/screens/Finances.tsx`

- `KIND_LABELS` gains `merchandise: 'Merchandise revenue'`. **Load-bearing:**
  the record is typed `Record<LedgerEntry['kind'], string>`, so omitting it is
  a TypeScript error at build time — but only if the union in `api.ts` was
  updated first. Do both in the same commit.
- Add a second `StatTile` beside the balance showing fanbase, with the weekly
  change as its suffix (`+2,250 this week` / `−150 this week`), using the
  existing `color.positive` / `color.negative` and `formatCredits` for the
  thousands separator.

No new screen, no chart — both are out of scope.

## Work items

### W1 — `economy/models.py`, `economy/migrations/0002_*`: the fanbase model and the merchandise kind

**Done.** Add the five constants, `FanbaseEntry`, the `MERCHANDISE` choice and the
merchandise unique constraint. Generate the migration.

**Test:** `economy/tests/test_models.py` — `test_fanbase_entry_week_unique_per_team`
(a second `weekly` row for the same `(team, week)` raises `IntegrityError`),
`test_fanbase_starting_and_takeover_rows_allow_null_week` (several null-week
rows coexist), `test_merchandise_entry_unique_per_team_per_week`, and
`test_wage_and_merchandise_entries_coexist_for_one_week` — the last is the one
that catches D8 being implemented by widening the existing constraint.

### W2 — `economy/services.py`: `fanbase_for`, `fanbase_entries_for`, `ensure_starting_fanbase`, `reset_fanbase`

**Done.** The four non-weekly functions. No caller yet.

**Test:** `economy/tests/test_fanbase.py` (new) —
`test_fanbase_is_sum_of_deltas`, `test_ensure_starting_fanbase_is_idempotent`
(two calls, one row, fanbase still `STARTING_FANBASE`),
`test_reset_fanbase_returns_none_when_already_at_start`,
`test_reset_fanbase_writes_takeover_delta_without_deleting_history` (a team
grown to 30,000 resets to 10,000 via a −20,000 row, with the earlier rows
still present).

### W3 — `competitions/services.py`: `points_by_team`

**Done.**

**Test:** `competitions/tests/` — `test_points_by_team_sums_a_weeks_races`
(two races in one week, one team scoring in both), and
`test_points_by_team_omits_teams_that_scored_nothing`.

### W4 — `economy/services.py`: `apply_weekly_fanbase` **Load-bearing (D4)**

**Done.**

**Test:** `economy/tests/test_fanbase.py` —
`test_points_raise_fanbase_net_of_decay` (10 points → `10*40 - 150 = +250`),
`test_scoreless_team_only_decays` (`−150`),
`test_decay_applies_to_winners_too` (a scoring team's delta is strictly less
than `points * FANBASE_PER_POINT`),
`test_fanbase_never_falls_below_floor` — a team at `MINIMUM_FANBASE` with no
points gets `delta == 0`, and `fanbase_for` is still exactly
`MINIMUM_FANBASE`; and `test_second_call_for_same_week_writes_nothing`.

The floor test is the one that proves D4: if the implementation clamps on read
instead of at write, `fanbase_for` looks right while `delta` is `−150`. Assert
on **both** the stored `delta` and `fanbase_for`.

### W5 — `economy/services.py`: `pay_merchandise`

**Done.**

**Test:** `economy/tests/test_merchandise.py` (new) —
`test_merchandise_is_fanbase_over_divisor` (10,000 fanbase → 400 credits),
`test_merchandise_is_a_positive_ledger_entry` (`amount > 0`, and
`balance_for` rose by exactly that),
`test_zero_fanbase_team_gets_a_zero_entry_not_a_skip`,
`test_second_call_for_same_week_writes_nothing`.

### W6 — `world/services.py`, `world/models.py`, `world/migrations/0007_*`: wire it into the tick **Load-bearing (D2)**

**Done.** Add the two `TickRun` counters and the loop body from the section above.

**Test:** `world/tests/test_tick.py` —
`test_tick_pays_merchandise_after_updating_fanbase` (a team whose fanbase rose
this week is paid on the **new** figure, not the old one — assert the ledger
amount matches post-adjustment fanbase);
`test_fanbase_reads_the_completed_week_not_the_opening_one` — the critical
one: set up week 1 with a scored race, advance the clock into week 2, and
assert the week-2 fanbase row has `points > 0`. An implementation that queries
the opening week gets `points == 0` and a pure-decay delta;
`test_week_one_has_no_preceding_week_and_only_decays`;
`test_catch_up_across_three_weeks_writes_three_fanbase_and_three_merchandise_entries`,
each dated to its own week's `starts_at`;
`test_tick_run_counts_fanbase_and_merchandise_entries`.

### W7 — `teams/services.py`, `teams/management/commands/seed_teams.py`: reset on claim, seed on create **Done.**

**Test:** `teams/tests/test_services.py` —
`test_claiming_a_team_resets_its_fanbase` (an unmanaged team grown to 30,000
is claimed and sits at `STARTING_FANBASE`, with its prior rows still in the
history); `teams/tests/test_seed_teams.py` —
`test_seed_teams_gives_every_team_a_starting_fanbase` and
`test_reseeding_does_not_double_credit_fanbase`.

### W8 — `api/serializers.py`, `api/views.py`: expose fanbase **Done.**

**Test:** `api/tests.py` — `test_finances_includes_fanbase_and_weekly_change`,
`test_finances_fanbase_change_is_zero_before_any_weekly_entry`,
`test_finances_without_a_team_returns_zero_fanbase`,
`test_merchandise_entry_serializes_with_its_kind`.

### W9 — `frontend/src/api.ts`, `frontend/src/screens/Finances.tsx`: show it

**Test:** `frontend/src/screens/Finances.test.tsx` —
`renders the fanbase tile with its weekly change`,
`renders a negative weekly change in the negative colour`,
`renders a merchandise entry with its label and a positive amount`.

### W10 — documentation

See below. One commit, last, once the behaviour is settled.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7 → W8 → W9 → W10.

The reasoning:

- **W1 before everything**: the model and constraints are what every later
  item writes against, and the constraint tests are cheap and catch D8 early.
- **W2 before W4/W5**: `fanbase_for` is the assertion every weekly test makes;
  writing it first means W4's floor test can be trusted.
- **W3 standalone and early**: it touches a different app and has no
  dependency on the economy work, so it can be reviewed on its own merits.
- **W4 before W5**: merchandise is computed off fanbase, so the thing it reads
  must be correct first. Testing them in the other order means W5 passes
  against a fanbase that is always exactly `STARTING_FANBASE`.
- **W6 after both**: the tick wiring is where D2 can go wrong, and it is much
  easier to diagnose when the two functions it calls are independently proven.
- **W7 after W6**: claiming resets a number that only means something once the
  weekly machinery moves it.
- **W8/W9 last of the code**: the API and screen are a readout of settled
  behaviour. W9 must follow W8 or the frontend types describe a payload the
  server does not send.

Commit after each work item; the suite must be green at every one.

## Documentation update (required, not optional)

**`economy/README.md`** — the main one.

- *What this app owns*: add `FanbaseEntry`, and that this app now owns the
  game's first **income** (merchandise), not only outgoings. Correct the
  existing sentence that says every balance only goes down.
- New section, *Fanbase is derived too*: the same append-only argument the
  ledger section already makes, and why `FanbaseEntry` is a separate model
  rather than a `LedgerEntry` kind (D3 — sharing the table would corrupt
  `balance_for`).
- New section, *Fanbase reads the completed week*: D2 in full, including why
  the obvious reading of the opening week is always empty. This is the thing a
  future reader will otherwise re-break.
- New section, *Why `economy/` does not query `RacePoints`*: D1, and the
  `points_by_team` injection point.
- *Fanbase is clamped at write time*: D4 and what breaks if clamped on read.
- *Future work*: remove merchandise from the income list; leave prize money
  (#19) and sponsorship (#22/#23); add that #22/#23 read `fanbase_for`.

**`competitions/README.md`** — *What this app owns* gains `points_by_team`, and
a line that `world/` calls it to feed `economy/` because `economy` may not
import this app — the same inversion note the file already makes about
`racing/`.

**`world/README.md`** — *How a tick works*: the per-week loop now also adjusts
fanbase and pays merchandise, in that order, off `_completed_week()`. Note the
two new `TickRun` counters.

**`teams/README.md`** — *What `teams/` may import*: the deferred economy import
in `claim_team` now covers `reset_fanbase` as well.

**`frontend/README.md`** — the Finances screen now shows fanbase and its weekly
change.

**`AGENTS.md`** — the `economy/` row currently reads *not yet*; it was updated
by #20, so confirm and extend its description to mention fanbase and
merchandise. The dependency graph gains no new edge — say so explicitly in the
commit message, because a reader will expect `economy -> competitions` and it
is deliberately absent.

## Verification

```bash
.venv/bin/python manage.py migrate
.venv/bin/python -m pytest
```

Then a real world, which is what actually proves D2:

```bash
.venv/bin/python manage.py seed_user
.venv/bin/python manage.py seed_teams --claim-for test@mail.com
.venv/bin/python manage.py seed_trainers
.venv/bin/python manage.py load_season seasons/season-1.example.json
```

With `GAME_CLOCK_CLASS=world.clocks.MockClock`:

```bash
.venv/bin/python manage.py mock_clock set <season start>
.venv/bin/python manage.py tick      # week 1 opens: decay only, no prior week
.venv/bin/python manage.py mock_clock advance --weeks 1
.venv/bin/python manage.py tick      # week 2 opens: week 1's points land here
```

**The likeliest failure mode is D2** — fanbase reading the week being entered
rather than the one that completed. It is invisible in a single tick and looks
like a plausible game ("fanbase only ever decays"), so it will not announce
itself.

**The check that catches it:** after the *second* tick, the week-2
`FanbaseEntry` for a team that scored in week 1 must have `points > 0` and a
`delta` greater than `−WEEKLY_FANBASE_DECAY`. If every team in the game has
`delta == −150` and `points == 0` after several weeks of racing, D2 is wrong.

```bash
.venv/bin/python manage.py shell -c "
from economy.models import FanbaseEntry
for e in FanbaseEntry.objects.filter(kind='weekly').select_related('team','week')[:20]:
    print(e.week.number, e.team.code, e.points, e.delta)
"
```

A passing `test_fanbase_never_falls_below_floor` that asserts only on
`fanbase_for` proves nothing about D4 — it must also assert the stored `delta`.
Same trap: a merchandise test that asserts `amount > 0` without checking it
against the post-adjustment fanbase would pass against a stale figure.

Finally, open the Finances screen and confirm the fanbase tile, the weekly
change, and a green "Merchandise revenue" row in the history.

## Risks

| Risk | Mitigation |
|---|---|
| **Fanbase reads the opening week, so it only ever decays.** The single most likely defect; produces a plausible-looking game and passes any test that does not span two weeks. | D2; reuse `_completed_week()`; `test_fanbase_reads_the_completed_week_not_the_opening_one`; the shell check in *Verification*. |
| **`economy/` imports `competitions/`** to query `RacePoints` directly — the obvious implementation, and a dependency-graph violation. | D1; `points_by_team` injected as a plain dict; documented in both READMEs. Reviewer should grep `economy/` for `competitions`. |
| **The floor is clamped on read, not on write**, so stored history and displayed fanbase disagree and recovery lags behind phantom negative rows. | D4; the floor test asserts on the stored `delta` as well as on `fanbase_for`. |
| **The existing wage constraint gets widened** to cover merchandise, making a team's wage and merchandise entries for one week mutually exclusive. | D8; a separate named constraint; `test_wage_and_merchandise_entries_coexist_for_one_week`. |
| **Merchandise paid on pre-adjustment fanbase**, making the income lag an extra week. | D7; `pay_merchandise` recomputes from rows rather than accepting a passed number; `test_tick_pays_merchandise_after_updating_fanbase`. |
| **A `Team.fanbase` column added for convenience**, which drifts from its rows exactly as a cached balance would. | D3; documented in `economy/README.md` alongside the existing no-balance-column argument. |
| **Constants retuned to balance the economy now**, pre-empting #19 and #22. | D6 records the arithmetic and the intent; the spec's "meaningful, not sufficient" is binding. |
| **Frontend `KIND_LABELS` missing the new kind** — a runtime `undefined` label if the union is not updated in the same commit. | W9 does both files together; the `Record<>` type makes it a build error once `api.ts` is correct. |

## Open questions

None. The spec's `Open questions` is empty, and every constant this plan
introduces is a tunable recorded in `economy/models.py` with its reasoning,
not a blocking decision.

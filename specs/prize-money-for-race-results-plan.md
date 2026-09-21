# Prize money for race results — Implementation Plan

**Spec:** `specs/prize-money-for-race-results.md` · **Issue:** #19 · **Status:** proposed
**Apps touched:** `economy/`, `competitions/`, `world/`, `api/`, `frontend/`

## Context you need

The game already turns a finished race into points. `world.services._execute`
simulates a race and then calls `competitions.services.score_race(race)`
(`world/services.py:99-100`). `score_race` writes one `RacePoints` row per team
— **the team's single best classified finisher only** — and is idempotent by
early-returning existing rows. `competitions/scoring.py` holds
`POINTS_BY_POSITION` (20/15/12/10/8/6/4/3/2/1 for positions 1–10) and
`points_for(position)`.

Money already exists, and now has its first income: #21 (fanbase and
merchandise revenue) shipped since this ticket was scoped.
`economy.LedgerEntry` is an append-only table of signed integers; a team's
balance is `Sum(amount)`, never stored. Current kinds are `starting_balance`,
`wages`, `takeover`, `merchandise` (`economy/models.py`). Player-facing
amounts are `$`-prefixed per `AGENTS.md`, *Displaying game money* — this is a
display rule only, the model stays a plain signed integer.
`charge_weekly_wages(week)` and `pay_merchandise(week)` are both the shape to
copy: one `transaction.atomic()` **per row**, catching `IntegrityError` and
continuing, because an `IntegrityError` poisons an enclosing transaction in
Django.

**#21 also already solved this ticket's hardest problem, for a different
feature.** `economy/` may not import `competitions/`, but fanbase has to be
adjusted off a week's `RacePoints`. The shipped solution:
`competitions.services.points_by_team(week)` returns a plain
`{team_id: total}` dict, and `world/services.py` computes it and passes it
into `economy.services.apply_weekly_fanbase(week, points_by_team=...)` —
`economy/` never imports `competitions/`, and `world/` (which may know about
everything) is the one place that reads both. This plan uses the identical
shape for prize money instead of inventing a different one.

Three repo rules bind this work, all from `AGENTS.md`:

- **`economy/` may import `core`, `teams`, `riders`, `schedule` — and nothing
  else.** It must not import `racing/` or `competitions/`.
- **`racing/` must never import `competitions/`.** This is why scoring is
  called from `world/` and not from inside `simulate_race`.
- **`world/` and `api/` may know about everything**, and nothing may import
  them.

Read `economy/README.md` (*The ledger is append-only*, *Why `economy/` does
not query `RacePoints`*, *Fanbase reads the completed week*) and
`competitions/README.md` (*Why non-finishers are filtered*, *The points
table*) before starting. Both record decisions this plan follows rather than
re-derives.

## Goal

When this is done:

1. A finished race pays every team with a rider in the top 10, **once per
   placed rider**, as its own `LedgerEntry` naming the race.
2. Non-finishers and team-less riders are never paid; unmanaged teams are.
3. Paying a race twice is impossible, and the amounts are frozen at award time.
4. A manager sees the payout table on a race before it runs, the per-team
   money alongside the points after it runs, and a dated line per prize in
   their finances history.
5. A prize failure can never mark a successfully simulated race `FAILED`.

## Design decisions (settled — implement these, do not substitute)

**1. `competitions/` computes the payout; `economy/` writes the ledger. Never
the other way, and never combined.**
The payout is a function of a finishing position, exactly like points, and
`competitions/` is already allowed to import `racing`, `teams` and `schedule`
to read a `RaceResult`. `economy/` is not allowed to import `racing/` or
`competitions/` at all — the graph in `AGENTS.md` has not changed, and this
plan does not ask to change it. Put `PRIZE_BY_POSITION` and
`prize_for(position)` in `competitions/scoring.py` beside the points table.
Put a **read-only** function in `competitions/services.py`,
`prizes_by_team(race)`, that returns `{team_id: [(position, amount), ...]}` —
it touches no ledger and writes nothing. `world/` calls it and passes the
result into a new `economy.services.pay_race_prizes(race_id, ..., prizes_by_team=...)`.
*Do not* create a new app, and *do not* let `competitions/` write a
`LedgerEntry` or `economy/` read a `RaceResult`.

**2. This is the same inversion `economy/README.md` already documents for
fanbase — reuse it exactly, do not invent a second shape.**
`apply_weekly_fanbase(week, *, points_by_team: dict[int, int])` takes a plain
dict because `economy/` cannot query `RacePoints` itself; `world/` computes
that dict via `competitions.services.points_by_team(week)` and passes it in.
Prize money has the identical constraint (`economy/` cannot query
`RaceResult` either) and gets the identical fix: a plain-data argument
computed by `world/`, not a lazy in-function import. **Do not** reach for the
`teams -> economy` lazy-import exception (`teams/README.md`) — that pattern
exists for a one-off write inside `claim_team` and `seed_teams`, not for a
recurring cross-app read, and `AGENTS.md`'s graph does not list
`competitions -> economy` the way it explicitly carves out `teams -> economy`.
Introducing a second import exception where an established data-passing
pattern already solves the same problem would be needless divergence.

**3. `LedgerEntry.race` is a string FK.**
`race = models.ForeignKey("racing.Race", ...)` declared as a **string** imports
nothing from `racing/` at module scope — the same import-free pattern
`staff.TrainingWeekReport.week` uses for `schedule.Week`
(`staff/models.py:118`) and `racing.Race.week` uses. `economy/` never imports
`racing/` even though this field exists — the string is what makes that true.
**Load-bearing.**

**4. Exactly-once is a database constraint on `(team, race, position)`, not an
early return.**
`score_race` gets away with "return existing rows if any exist" because it
writes at most one row per team. Prize money writes *several* rows per team
(one per placed rider), so "are there any rows?" cannot distinguish a complete
payout from a half-finished one interrupted mid-loop. Use a partial unique
constraint on `(team, race, position)` where `kind = "prize_money"`, and the
per-row `atomic()` + `except IntegrityError: continue` loop `charge_weekly_wages`
and `pay_merchandise` both already use. A retry after a partial failure then
completes the payout instead of skipping it. **Load-bearing — this is the one
place the obvious approach is wrong.**

Two riders of the same team cannot share a position: `RaceResult` has a
`unique_position_per_race` constraint, so `(team, race, position)` is safe as a
key.

**5. Paying happens in `world/services._execute`, after `score_race`, inside
its own try/except.**
`_execute` currently wraps `simulate_race` + `score_race` in one `try` that
marks the race `FAILED` on any exception (`world/services.py:96-106`). A race
that simulated and scored correctly but failed to pay must **not** be recorded
as a failed race — the log is authoritative and the result is real. Wrap the
payout in its own `try`, append to `tick.error`, and leave `race.status`
alone. **Load-bearing.**

**6. The payout table mirrors the points table's shape, scaled by 1,000.**

```python
PRIZE_BY_POSITION: dict[int, int] = {
    1: 20_000, 2: 15_000, 3: 12_000, 4: 10_000, 5: 8_000,
    6: 6_000,  7: 4_000,  8: 3_000,  9: 2_000, 10: 1_000,
}
```

Rationale, against the spec's "meaningful, not sufficient": a 12-rider team
burns `12 × 1_200 = 14_400` a week. A win covers ~1.4 weeks of wages; a 5th
place covers ~0.55 of a week; a team with two riders in the top 10 (say 3rd and
8th) banks 15,000, about one week. Across a 12-race season a consistently
strong team earns on the order of 150–250k against a ~173k wage bill — helpful,
not self-sufficient, leaving room for fanbase (#21) and sponsors (#22/#23).
These are game-balance constants and belong in `competitions/scoring.py`
beside the points table, **not** in settings.

**7. Amounts are frozen by being written, not by being recalculated.**
The `LedgerEntry.amount` is the record. The ledger is append-only, so a later
change to `PRIZE_BY_POSITION` cannot reach a past row — the spec's "frozen at
award time" requirement is satisfied structurally, with no extra work. Do not
add a `prize_table_version` field or similar.

**8. The API reports prize money per team, summed, alongside points.**
`RaceResultsView` already emits a `points` list with a zero row for every
starting team that did not score. Add `prize` to those same entries (summing a
team's rows, since a team may have several) so the two tables cannot disagree
about which teams are listed. Do not add a second parallel list.

## Data model

### `economy/models.py` — new kind and two new fields on `LedgerEntry`

`LedgerEntry.Kind` gains:

```python
PRIZE_MONEY = "prize_money", "Prize money"
```

New fields:

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `race` | `ForeignKey("racing.Race", on_delete=models.SET_NULL)` | `null=True, blank=True` | — | Set on `prize_money` entries only; null elsewhere. `SET_NULL` matches `week`: deleting a race must not delete financial history. **Declared as a string** (decision 3). `related_name="ledger_entries"`. |
| `position` | `PositiveSmallIntegerField` | `null=True, blank=True` | — | The finishing position this prize was for, 1–10. Meaningful only on `prize_money`; null elsewhere. Needed for the uniqueness key and shown in the description. |

New constraint on `LedgerEntry.Meta`:

```python
models.UniqueConstraint(
    fields=["team", "race", "position"],
    condition=models.Q(kind="prize_money"),
    name="one_prize_entry_per_team_race_position",
),
```

Conditional for the same reason the wage constraint is: `race` is null on every
other kind, and several such rows exist per team.

New index:

```python
models.Index(fields=["race"], name="ledger_race_idx"),
```

Migration: `economy/migrations/0002_prize_money.py` (`economy/migrations/`
currently holds only `0001_initial.py`). Schema-only — no data migration; races
finished before this ships are not retroactively paid, and the spec does not
ask for that.

`competitions/` gains **no new model.** The `LedgerEntry` rows are the record;
a `RacePrize` table would duplicate them and be able to drift.

## `competitions/scoring.py`

Add beside the existing points table:

```python
#: Prize money by finishing position, 1-indexed. Positions beyond this pay
#: nothing. Frozen per race at award time by virtue of the append-only
#: ledger — see specs/prize-money-for-race-results.md.
PRIZE_BY_POSITION: dict[int, int] = {...}   # decision 6


def prize_for(position: int) -> int:
    """What a finishing position pays. Zero outside the table."""
    return PRIZE_BY_POSITION.get(position, 0)
```

## `competitions/services.py`

```python
def prizes_by_team(race) -> dict[int, list[tuple[int, int]]]:
    """Every placed rider's prize for one finished race, keyed by team.

    {team_id: [(position, amount), ...]} — a team with two riders in the
    top 10 gets two entries in its list, unlike points which credit only
    the best finisher. Read-only: writes nothing, touches no ledger.
    economy/ cannot compute this itself (it may not import racing/ or
    competitions/), so world/ calls this and passes the result into
    economy.services.pay_race_prizes — the same shape points_by_team/
    apply_weekly_fanbase already use for the identical constraint
    (economy/README.md, *Why `economy/` does not query `RacePoints`*).

    Raises ValueError if the race is not FINISHED.
    """
    if race.status != Race.Status.FINISHED:
        raise ValueError(f"{race} is not finished; nothing to pay")

    rows = (
        RaceResult.objects
        .filter(race=race, finish_time__isnull=False)     # non-finishers never pay
        .values_list("rider__team_id", "position")
        .order_by("position")
    )

    by_team: dict[int, list[tuple[int, int]]] = {}
    for team_id, position in rows:
        if team_id is None:                # team-less rider: spec item 5
            continue
        amount = prize_for(position)
        if amount <= 0:
            continue
        by_team.setdefault(team_id, []).append((position, amount))
    return by_team
```

`finish_time__isnull=False` is the whole of spec item 4 and mirrors
`score_race` exactly — `simulate_race` numbers every rider including those who
never finished, so an unfiltered query would pay teams for abandoning
(`competitions/README.md`, *Why non-finishers are filtered*).

## `economy/services.py`

```python
def pay_race_prizes(race_id: int, *, race_name: str, at,
                    prizes_by_team: dict[int, list[tuple[int, int]]]) -> int:
    """Credit every team its prize money for one race. Returns rows written.

    Takes the race as an id plus the amounts already computed by
    competitions.services.prizes_by_team — economy/ may not import
    racing/ or competitions/ (AGENTS.md), so it never reads a RaceResult
    itself. The identical shape apply_weekly_fanbase takes points_by_team.

    Idempotent through the (team, race, position) constraint, not an
    early return: a partial payout (interrupted mid-loop) must be
    completable on retry, unlike score_race's early return which only
    ever needs to check for the presence of one row per team.
    """
    written = 0
    description = f"Prize money — {race_name}"[:120]
    for team_id, placements in prizes_by_team.items():
        for position, amount in placements:
            with transaction.atomic():
                try:
                    LedgerEntry.objects.create(
                        team_id=team_id,
                        kind=LedgerEntry.Kind.PRIZE_MONEY,
                        amount=amount,
                        occurred_at=at,
                        race_id=race_id,
                        position=position,
                        description=description,
                    )
                    written += 1
                except IntegrityError:
                    continue      # already paid; correct outcome, not an error
    return written
```

One `atomic()` per row, exactly as `charge_weekly_wages` and `pay_merchandise`
both do and for the same documented reason: an `IntegrityError` poisons an
enclosing transaction, so a duplicate must be isolated rather than aborting
the rest of the payout.

`amount` is positive — income. The ledger has no `direction` field
(`economy/README.md`). `race_id` is a plain integer; `race_name` a plain
string — `economy/` never receives a `Race` object.

## `world/services.py`

In `_execute`, after the existing try block's `score_race(race)`:

```python
    for race_id in race_ids:
        race = Race.objects.get(pk=race_id)
        try:
            simulate_race(race, game_time=at)
            score_race(race)
            tick.races_finished += 1
        except Exception:
            race.status = Race.Status.FAILED
            race.save(update_fields=["status"])
            tick.error += f"race {race_id}:\n{traceback.format_exc()}\n"
            continue                      # nothing to pay for a failed race

        try:
            prizes = prizes_by_team(race)
            tick.prize_entries += pay_race_prizes(
                race.pk, race_name=race.name, at=race.finished_at,
                prizes_by_team=prizes,
            )
        except Exception:
            # The race ran and scored; a payout failure must not rewrite
            # that into a failed race. Record it and move on.
            tick.error += f"race {race_id} prizes:\n{traceback.format_exc()}\n"
```

The `continue` is new and necessary: without it a race that failed to simulate
would fall through into the payout block.

`race.finished_at` is **game** time, matching wages' and merchandise's use of
`week.starts_at` rather than `now()`. `simulate_race` sets it before this
runs.

Import `from competitions.services import prizes_by_team, score_race` and
`from economy.services import pay_race_prizes, ...` at module scope —
`world/` is allowed to import everything, and already imports both modules
this way.

### `world/models.py`

`TickRun` gains, beside `wage_entries`:

```python
    prize_entries = models.PositiveIntegerField(
        default=0,
        help_text="Ledger prize-money entries written this tick (#19).",
    )
```

Migration: `world/migrations/0007_tickrun_prize_entries.py` — `0006_tickrun_wage_entries.py`
is currently the latest.

## `api/serializers.py` and `api/views.py`

`RaceResultPointsEntrySerializer` gains `prize = serializers.IntegerField()`.

`RaceResultsView.get` — build a per-team prize total and attach it to both
branches of `points_payload`:

```python
        prizes = (
            LedgerEntry.objects
            .filter(race=race, kind=LedgerEntry.Kind.PRIZE_MONEY)
            .values("team_id")
            .annotate(total=Sum("amount"))
        )
        prize_by_team = {p["team_id"]: p["total"] for p in prizes}
```

then `"prize": prize_by_team.get(p.team_id, 0)` on the scored rows and
`"prize": prize_by_team.get(t.pk, 0)` on the zero rows. A team can hold a prize
without holding points only in theory (both read the same top-10 table), but
reading the dict for both branches costs nothing and cannot be wrong.

`RaceDetailSerializer` gains a payout table so an unraced race can show what it
pays:

```python
class RacePayoutEntrySerializer(serializers.Serializer):
    position = serializers.IntegerField()
    points = serializers.IntegerField()
    prize = serializers.IntegerField()
```

`RaceDetailView.get` adds `"payout": [{"position": p, "points": points_for(p),
"prize": prize_for(p)} for p in sorted(POINTS_BY_POSITION)]`. Served on **every**
race regardless of status — the spec asks for it before the race, and showing
it after costs nothing and keeps one shape.

`api/` may import `competitions/` freely.

## `frontend/src/`

`api.ts`:
- `RaceResultPointsEntry` gains `prize: number`.
- `LedgerEntry['kind']` union gains `'prize_money'`.
- `RaceDetail` gains `payout: RacePayoutEntry[]` with a new
  `RacePayoutEntry { position: number; points: number; prize: number }`.

`screens/Finances.tsx`: `KIND_LABELS` gains `prize_money: 'Prize money'`. The
row already prefers `entry.description`, so "Prize money — Paris-Roubaix"
renders with no further change.

`screens/Race.tsx`:
- `TeamPointsTable` renders the prize beside the points — retitle the card
  "Team points and prizes" and add a money column. Follow the existing row
  layout (`fontFamily: font.mono`) rather than inventing one.
- A new `PayoutTable` card listing position / points / prize, rendered in the
  `scheduled` branch of `raceBody` above the `SquadPanel`, and in the
  `finished` branch below the results. Both branches, one component.

Money formatting: `Finances.tsx:9` has `formatCredits(amount)`
(`amount.toLocaleString('en-US')`), currently module-private. Export it and
import it in `Race.tsx` rather than writing a second formatter.

## Work items

### W1 — `competitions/scoring.py`: the payout table — **done**
Add `PRIZE_BY_POSITION` and `prize_for()`. No callers yet.
**Test:** `competitions/tests/test_scoring.py` —
`test_prize_by_position`, `test_position_outside_table_pays_nothing`,
`test_prize_table_matches_points_table_positions` (asserts both tables cover
exactly positions 1–10, so they can never drift apart).

### W2 — `economy/`: the ledger can hold a prize
New `PRIZE_MONEY` kind, `race` and `position` fields, the conditional unique
constraint, the index, migration `0002_prize_money`, and
`pay_race_prizes(race_id, *, race_name, at, prizes_by_team)` — it takes
plain data only, the same shape `apply_weekly_fanbase` takes `points_by_team`.
**Load-bearing:** `race` must be declared as the **string** `"racing.Race"`.
**Test:** `economy/tests/test_models.py` —
`test_prize_entry_unique_per_team_race_position` (second identical write
raises `IntegrityError`; a *different* position for the same team and race
succeeds). `economy/tests/test_services.py` —
`test_pay_race_prizes_writes_one_entry_per_placement` (a two-position
`prizes_by_team` dict for one team writes two positive entries),
`test_pay_race_prizes_is_idempotent` (calling twice with the same dict writes
nothing the second time),
`test_pay_race_prizes_completes_a_partial_payout` (write one of the two rows
by hand first, then call it — assert the missing row appears and the existing
one is untouched). The last test proves decision 4; an early-return
implementation fails it.

### W3 — `competitions/services.py`: `prizes_by_team`, and `world/` wiring
The read-only payout computation, plus the second try block in `_execute`
(with its `continue`), `TickRun.prize_entries` and its migration. One work
item because neither half is independently useful — `world/` is the only
caller of both, mirroring `points_by_team` / `apply_weekly_fanbase`.
**Test:** `competitions/tests/test_prizes.py` (new file) —
`test_every_placed_rider_is_paid` (one team, riders 2nd and 5th →
`{team_id: [(2, prize_for(2)), (5, prize_for(5))]}`),
`test_non_finishers_are_never_paid`,
`test_rider_without_a_team_is_skipped`,
`test_positions_outside_the_table_pay_nothing`,
`test_unfinished_race_raises`.
`world/tests/test_tick.py` —
`test_tick_pays_prize_money_for_a_finished_race`,
`test_prize_failure_does_not_fail_the_race` (monkeypatch `prizes_by_team` to
raise; assert `race.status == FINISHED` and `tick.error` is non-empty). The
second test is the point of this work item.

### W5 — `api/`: serve prizes and the payout table
`prize` on the results points entries; `payout` on race detail.
**Test:** `api/tests.py` (a single module, not a package) —
`test_race_results_includes_prize_per_team`,
`test_race_results_prize_is_zero_for_unplaced_starters`,
`test_race_detail_includes_payout_table` (on a *scheduled* race).

### W6 — `frontend/`: show it
Types, `KIND_LABELS`, the prize column, the `PayoutTable` card in both
branches.
**Test:** `frontend/src/screens/Race.test.tsx` — the payout table renders for a
scheduled race and prizes render beside points for a finished one.
`Finances.test.tsx` — a `prize_money` entry renders with its description.

### W7 — documentation
See below. Its own commit.

## Execution order

W1 → W2 → W3 → W5 → W6 → W7 (there is no separate W4; the tick wiring moved
into W3 — see above).

W1 first because it is pure data with no dependencies and makes the numbers
reviewable on their own. W2 before W3 because `world/`'s wiring calls
`economy.services.pay_race_prizes`, which cannot be written against a column
that does not exist. W5 and W6 are read-only presentation and cannot break
the payout.

Commit after each work item; each leaves the suite green.

## Documentation update (required, not optional)

**`economy/README.md`** —
- *What this app owns*: prize money is now a second income source it holds
  rows for; update the "Not prize money or sponsorship" sentence, which this
  ticket falsifies for prize money (sponsorship is still not built).
- New section, *Prize money reads the same way fanbase does*: `pay_race_prizes`
  takes ids and a plain `prizes_by_team` dict, never a `Race` or `RaceResult`
  object — the same shape `apply_weekly_fanbase` takes `points_by_team`, and
  for the same reason. The `race` FK is a string FK and why. The
  `(team, race, position)` constraint is the exactly-once guarantee, not an
  early return, because a payout writes several rows per team.
- *What `economy/` may import*: unchanged — say explicitly that the new
  `race` FK does not change it, since it is declared as a string.

**`competitions/README.md`** —
- *What this app owns*: add the payout, and that it writes no model of its own.
- *The points table*: note the prize table sits beside it and covers the same
  positions.
- *Future work*: remove the "**Prize money** (#19)" bullet — it is now built.

**`world/README.md`** — *How a tick works*, step on races: after `score_race`,
the tick pays prizes in a separate try block, and why a payout failure does not
fail the race.

**`api/README.md`** and **`frontend/README.md`** — the new `payout` field on
race detail and `prize` on race results; the new ledger kind.

**`AGENTS.md`** — the dependency graph is unchanged: `economy/` still imports
only `core, teams, riders, schedule`, and `competitions/` still imports only
`racing, teams, schedule, core`. No new edge and no new exception — the
`world`-computes-and-passes-in shape (decision 2) is precisely what keeps it
that way. Update only the `economy/` and `competitions/` table row
descriptions to mention prize money.

## Verification

```bash
.venv/bin/python manage.py migrate
.venv/bin/python -m pytest
```

End to end, with the mock clock:

```bash
.venv/bin/python manage.py seed_user
.venv/bin/python manage.py seed_teams --claim-for test@mail.com
.venv/bin/python manage.py seed_trainers
.venv/bin/python manage.py load_season seasons/season-1.example.json
GAME_CLOCK_CLASS=world.clocks.MockClock .venv/bin/python manage.py mock_clock set <season start>
GAME_CLOCK_CLASS=world.clocks.MockClock .venv/bin/python manage.py tick
```

Then, on the running server: open a scheduled race and confirm the payout table
shows before it has run; tick past it; confirm the race page shows money beside
points, and the Finances screen shows one dated "Prize money — <race>" line per
placed rider.

**The likeliest failure mode is a silently partial payout** — a team paid for
its 3rd-placed rider but not its 8th, because the implementer reached for
`score_race`'s early-return idiom. The check that catches it:

```bash
.venv/bin/python -m pytest competitions/tests/test_prizes.py::test_partial_payout_completes_on_retry
```

A test that only asserts "calling twice doesn't double-pay" passes against the
broken implementation and proves nothing. The retry test is the one that
matters.

Second check, that the ledger and the race page agree:

```python
# manage.py shell
from economy.models import LedgerEntry
from django.db.models import Sum
LedgerEntry.objects.filter(kind="prize_money").aggregate(Sum("amount"))
```

must equal the sum of the prize column on that race's results page.

## Risks

| Risk | Mitigation |
|---|---|
| `economy/` imports `racing/` at module scope to type the `race` FK, creating an import cycle | The FK is declared as the string `"racing.Race"`. Called out in W2 as load-bearing and in `economy/README.md`. |
| Implementer reaches for the `teams -> economy` lazy-import exception instead of the plain-data pattern, creating an import `competitions/` should never need | Decision 2 names the established `points_by_team`/`apply_weekly_fanbase` precedent explicitly and says not to use the other one. `prizes_by_team` takes and returns no model instances tied to another app's ORM. |
| Early-return idempotence copied from `score_race`, leaving partial payouts permanently incomplete | Decision 4, plus `test_partial_payout_completes_on_retry`, which fails against that implementation. |
| A payout exception marks a successfully simulated race `FAILED`, destroying a real result | Decision 5: separate try block, plus `test_prize_failure_does_not_fail_the_race`. |
| The missing `continue` pays out for a race that just failed to simulate | Written explicitly into the `_execute` snippet above. |
| A long race name overflows `description`'s `max_length=120` | Truncate with `[:120]` at the call site. |
| Prize and points tables drift apart when one is retuned | `test_prize_table_matches_points_table_positions` asserts they cover the same positions. |

## Open questions

None. The spec's two open items are resolved here: the wiring goes through
`world/` (decision 5), and the amounts are set in decision 6 — both are
technical calls within the spec's stated bounds, and the constants are one line
to retune if playtesting disagrees.

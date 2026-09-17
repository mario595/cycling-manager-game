# Rider freshness — Implementation Plan

**Spec:** `specs/rider-freshness.md` · **Issue:** #59 · **Status:** proposed
**Apps touched:** `riders/`, `racing/`, `world/`, `api/`, `frontend/`

## Context you need

Freshness is the counterpart to weekly training (#36, just merged). Training is
what a manager *gains* each week; freshness is what racing *costs*. Both settle
on the same weekly tick, and both read the same "who raced last week" helper.

What exists today, and matters here:

- **`riders.models.Rider`** holds five engine attributes (stored 1–100) plus
  visible extras (speciality, build, age) and hidden traits (`potential`,
  `peak_age`, `decline_rate`, `injury_proneness`, `training_affinity`,
  `growth_debt`). Hidden traits are **never serialized** — see
  `riders/README.md`, *Visible vs hidden*. Freshness breaks that pattern in one
  direction only: the **value** is visible, its **recovery rate** is hidden.
- **`riders.display.to_display_scale(value)`** maps stored 1–100 onto 0–10 by
  flooring (`value // 10`). It is the only place that mapping happens.
- **`riders.services.apply_weekly_growth(weeks, extra_deltas)`** moves every
  rider along their age curve plus per-rider extras, settling both through one
  `growth_debt` ledger, and returns display-scale change records.
- **`world.services._apply_training_week(week)`** runs once per week transition
  (never batched — see `world/README.md`, *How a tick works*), builds
  `extra_deltas` from trainers and last week's racing, and calls
  `apply_weekly_growth(weeks=1, ...)`.
- **`racing.services.riders_who_raced(week)`** returns
  `{rider_id: [training_attribute, ...]}` for one week, filtered to actual
  finishers (`finish_time__isnull=False`).
- **`racing.services.simulate_race(race, *, game_time)`** builds the engine
  field from `RaceSquadRider` rows via `to_engine_rider`, runs the engine, then
  writes `RaceLog`, `RaceResult` rows and the FINISHED flip in **one
  transaction**.
- **`racing.adapters.to_engine_rider(rider, *, role)`** is the only place a
  database rider becomes an engine rider, and `racing/adapters.py` is the only
  module in the project allowed to import `race_engine` at all.
- **`racing.services.auto_pick_squad(team)`** picks four riders by total engine
  attributes descending, pk ascending, strongest leading.

Rules this work is bound by (`AGENTS.md`):

- Dependency direction: `riders -> core, teams`. **`riders/` may not import
  `racing/`, `schedule/` or `world/`.** `world/` and `api/` may import anything.
- **`race_engine/` never learns about Django, and never learns about
  freshness.** This is the load-bearing constraint of the whole feature — see
  Design decision 1.
- Postgres everywhere; tests are pytest via `.venv/bin/python -m pytest`.

## Goal

When this is done:

1. Every rider has a stored freshness (1–100) and a hidden recovery rate, shown
   to the player as 0–10 on the squad selection screen only.
2. Finishing a race costs a fixed amount of freshness, written in the same
   transaction as the race's results.
3. Each weekly tick restores freshness to riders, at a per-rider hidden rate,
   clamped to a ceiling of 100 and a floor of 20.
4. A tired rider's attributes are scaled down **on the way into the engine**,
   in the adapter, so the engine stays ignorant and the stored attributes are
   untouched.
5. Auto-pick prefers fresher riders, without becoming an optimiser.

## Design decisions (settled — implement these, do not substitute)

**1. The performance penalty is applied in `racing/adapters.py`, by scaling the
attributes handed to the engine. Load-bearing.**
The engine must not gain a fatigue concept, a freshness field, or any new
input. `to_engine_rider` already builds `RiderAttributes` from the database
rider; it gains a `freshness` argument and scales each of the five values by a
multiplier derived from it.
**Do not** add a field to `race_engine.models.RiderAttributes`. **Do not**
mutate `rider.climb` etc. before calling the adapter — the spec is explicit
that stored ratings never change (*A tired rider's ratings do not change*), and
a mutation path risks a stray `save()` persisting the penalty permanently.

**2. Freshness is stored 1–100 and displayed 0–10 through the existing
`to_display_scale`.** Same convention as every attribute and every trainer
skill. Do not invent a second mapping, and do not store it 0–10.

**3. The floor is 20 stored (display 2), the ceiling 100 (display 10).**
"Low floor" was decided in the spec. At the floor the attribute multiplier is
0.80 — a 20% cut, clearly visible in results and unmistakably a handicap,
without making the rider a non-participant. The multiplier is linear in
freshness between floor and ceiling:

```
PENALTY_AT_FLOOR = 0.80
multiplier = PENALTY_AT_FLOOR + (1 - PENALTY_AT_FLOOR) * (freshness - FLOOR) / (MAX - FLOOR)
```

so freshness 100 → 1.00, freshness 20 → 0.80, freshness 60 → 0.90. Clamp the
input to `[FLOOR, MAX]` before computing, so a value outside the range (only
reachable via admin or a fixture) cannot produce a multiplier above 1.0.

**4. Racing costs 25 freshness; a week of rest returns 8–20 depending on the
rider's hidden `recovery_rate`.**
The spec requires a race to cost more than a week of rest returns. At the
average recovery rate (~14/week), a rider racing every week nets −11/week and
reaches the floor from full in about seven weeks — within a twelve-week season,
as the spec requires. A rider racing every *other* week nets +3/week and holds
near full. The recovery rate maps `recovery_rate` 1–100 onto 8–20 linearly.

**5. Recovery is applied per week inside `_apply_training_week`, not in a
separate tick step.** That function already runs exactly once per week
transition and already knows the week. Adding a second per-week loop over the
rider table would double the full-table write for no benefit.
**Do not** batch recovery as `weeks * per_week` in a single call — the tick
deliberately iterates weeks one at a time (#36's Design decision 3), and
freshness must follow, because whether a rider raced differs per week.

**6. A rider who raced during the week being settled does not also recover that
week.** The spec leaves this open ("an implementation question with no
player-visible difference"). Skipping recovery for racers is the simpler rule
and makes the intended pressure sharper. It reuses `riders_who_raced` — already
called in `_apply_training_week` for the training half — so it costs no extra
query.

**7. Freshness consumption is written in `simulate_race`'s existing results
transaction, not on the tick.** If the cost were applied weekly, a tick killed
between simulating a race and the next week boundary would lose it entirely.
Writing it beside the `RaceResult` rows makes "raced" and "paid for it" atomic.
**Only finishers pay.** A rider whose `finish_time` is None did not complete
the race — the same rule `riders_who_raced` and `competitions/` already apply
(`racing/README.md`: `RaceResult.position` is assigned to everyone, only
`finish_time` says they actually raced).

**8. `riders/` owns the freshness arithmetic; `racing/` and `world/` call it.**
`recovery_amount(rider)`, `apply_race_cost(rider_ids)` and
`freshness_multiplier(freshness)` live in `riders/services.py`. This keeps the
dependency direction intact — `racing/` already imports `riders.models`, and
`riders/` imports neither `racing/` nor `world/`.

**9. Auto-pick sorts on a freshness-weighted score, not on freshness first.**
```
score = sum(attributes) * freshness_multiplier(rider.freshness)
```
This is deliberately the *same* multiplier the engine penalty uses, so
auto-pick optimises for the thing that actually determines race outcome. It
remains a light preference: a much stronger tired rider still outranks a weak
fresh one, which is correct. **Do not** add a freshness threshold or exclude
tired riders — the spec forbids a hard gate (*Out of scope*).

**10. Freshness is added to `SquadRiderSerializer` only, never
`RiderSerializer`.** The spec restricts it to the squad screen. The hidden
`recovery_rate` goes in neither, like every other hidden trait.

## Data model

Two new fields on `riders.models.Rider`, one migration.

| Field | Type | Null/blank | Default | Validators | Notes |
|---|---|---|---|---|---|
| `freshness` | `PositiveSmallIntegerField` | not null, not blank | `100` | `MinValueValidator(1)`, `MaxValueValidator(100)` | **Visible** (0–10 via `to_display_scale`). Default 100 satisfies spec item 7 — every newly generated rider starts full, with no change to `generate_rider`. |
| `recovery_rate` | `PositiveSmallIntegerField` | not null, not blank | `50` | `MinValueValidator(1)`, `MaxValueValidator(100)` | **Hidden — never serialize.** Rolled in `generate_rider`. |

No index on either: nothing filters or orders by them in the database (auto-pick
sorts in Python over a team's dozen riders, as it already does).

Migration: `riders/migrations/000X_rider_freshness.py` — auto-generated,
`makemigrations riders`. Both fields have defaults, so existing rows backfill to
full freshness and an average recovery rate with no data migration. That is the
right outcome: this is a pre-launch world, and starting everyone fresh is
exactly what the spec asks for a new rider.

Constants live in `riders/services.py` beside the existing weekly constants:

```python
FRESHNESS_MAX = 100
FRESHNESS_FLOOR = 20
RACE_FRESHNESS_COST = 25
RECOVERY_MIN = 8
RECOVERY_MAX = 20
PENALTY_AT_FLOOR = 0.80
```

## riders/models.py

Add the two fields above. Extend the class docstring's hidden-trait list to
name `recovery_rate`, and note that `freshness` is visible but its rate is not.

## riders/services.py

```python
def freshness_multiplier(freshness: int) -> float:
    """Attribute scaling for a rider at this freshness.

    1.0 at FRESHNESS_MAX, PENALTY_AT_FLOOR at FRESHNESS_FLOOR, linear
    between. Input is clamped, so a value outside the range (only
    reachable via admin) can never scale attributes *up*.
    """


def recovery_amount(rider: Rider) -> int:
    """Freshness this rider regains in a week of rest.

    Maps recovery_rate 1-100 onto RECOVERY_MIN..RECOVERY_MAX linearly.
    """


def apply_race_cost(rider_ids: list[int]) -> int:
    """Deduct RACE_FRESHNESS_COST from each rider, floored at
    FRESHNESS_FLOOR. One UPDATE via Greatest/F, not a per-row loop.
    Returns the number of rows updated.
    """


def apply_weekly_recovery(*, exclude_ids: set[int]) -> int:
    """Restore one week of freshness to every rider not in exclude_ids,
    capped at FRESHNESS_MAX. Returns rows updated.
    """
```

`apply_race_cost` must be one statement, not a read-modify-write, because it
runs inside `simulate_race`'s transaction:

```python
from django.db.models import F
from django.db.models.functions import Greatest

Rider.objects.filter(pk__in=rider_ids).update(
    freshness=Greatest(
        Value(FRESHNESS_FLOOR),
        F("freshness") - RACE_FRESHNESS_COST,
    )
)
```

`apply_weekly_recovery` cannot use one statement, because the amount differs
per rider (`recovery_rate`). Iterate and `bulk_update`, matching
`apply_weekly_growth`'s existing shape:

```python
def apply_weekly_recovery(*, exclude_ids: set[int]) -> int:
    to_update = []
    for rider in Rider.objects.exclude(pk__in=exclude_ids):
        restored = min(FRESHNESS_MAX, rider.freshness + recovery_amount(rider))
        if restored != rider.freshness:
            rider.freshness = restored
            to_update.append(rider)
    Rider.objects.bulk_update(to_update, ["freshness"])
    return len(to_update)
```

## riders/generation.py

In `generate_rider`, roll `recovery_rate=rng.randint(_MIN_ATTRIBUTE,
_MAX_ATTRIBUTE)` alongside `decline_rate` and `injury_proneness`. Leave
`freshness` to the model default (100) — do not pass it explicitly; the default
is what guarantees spec item 7 for every creation path, including
`teams.services.claim_team`.

## racing/adapters.py

`to_engine_rider` gains a required keyword argument:

```python
def to_engine_rider(rider: DBRider, *, role: str, freshness_scale: float = 1.0) -> EngineRider:
    attributes = RiderAttributes(**{
        name: _scaled(getattr(rider, name), freshness_scale)
        for name in ENGINE_ATTRIBUTES
    })
```

where `_scaled(value, scale)` rounds and clamps into the engine's valid 1–100
range: `max(1, min(100, round(value * scale)))`. The engine validates its own
attribute range, so an unclamped value would raise there.

`freshness_scale` defaults to 1.0 so existing callers and tests that do not
care about fatigue keep working unchanged. `simulate_race` passes a real value.

**The import of `riders.services` goes in `racing/services.py`, not here.**
`adapters.py` takes a plain float, which keeps it a pure translation module
with no game-rule knowledge.

## racing/services.py

In `simulate_race`, compute the scale per rider when building the field:

```python
from riders.services import apply_race_cost, freshness_multiplier

engine_riders = [
    to_engine_rider(
        m.rider,
        role="leader" if m.is_leader else "support",
        freshness_scale=freshness_multiplier(m.rider.freshness),
    )
    for m in members
]
```

Inside the existing `transaction.atomic()` block, after `bulk_create` of the
results, deduct the cost from finishers only:

```python
finisher_ids = [
    by_pk[s.rider.id].pk for s in finishers if s.finish_time is not None
]
apply_race_cost(finisher_ids)
```

In `auto_pick_squad`, change the sort key:

```python
ordered = sorted(
    riders,
    key=lambda r: (
        -sum(getattr(r, name) for name in ENGINE_ATTRIBUTES)
        * freshness_multiplier(r.freshness),
        r.pk,
    ),
)
```

Update the docstring: it currently says "by total engine attributes descending"
and must now say the total is weighted by freshness, still pk-tiebroken and so
still deterministic.

## world/services.py

In `_apply_training_week`, after the `apply_weekly_growth` call, add recovery.
The `raced` dict is already in scope from the training half:

```python
changes = apply_weekly_growth(weeks=1, extra_deltas=extra)
_write_training_reports(week, changes, focus_by_team)
apply_weekly_recovery(exclude_ids=set(raced))
return len(changes)
```

`set(raced)` is the set of rider ids who finished a race in the week being
settled — exactly the riders Design decision 6 excludes from recovery.

Update the function docstring to say it now settles freshness recovery as well,
and note that racers are excluded.

No change to `TickRun`: the spec asks for no weekly freshness report (the
"who's tired" summary is deferred).

## api/serializers.py

Add to `SquadRiderSerializer` only:

```python
freshness = serializers.SerializerMethodField()

def get_freshness(self, instance) -> int:
    return to_display_scale(instance["freshness"])
```

`SquadRiderSerializer` is fed plain dicts, not model instances —
`api/views.py`'s `_squad_payload` builds one dict per rider. Add
`"freshness": rider.freshness` to that dict alongside the spread of
`ENGINE_ATTRIBUTES`, and have the serializer map it through
`to_display_scale`. Update the serializer docstring to say freshness is
included and the recovery rate deliberately is not.

## frontend/

Show freshness on the squad selection screen beside the five ratings, using the
same 0–10 presentation the ratings already use. Follow whatever component the
screen already uses for a rating; do not introduce a new widget style. Read
`frontend/README.md` before touching the screen.

## Work items

### W1 — `riders/`: the fields, the constants and the arithmetic ✅ done
Add `freshness` and `recovery_rate` to `Rider` with the migration; add the six
constants, `freshness_multiplier`, `recovery_amount`, `apply_race_cost` and
`apply_weekly_recovery` to `riders/services.py`; roll `recovery_rate` in
`generate_rider`.
**Tests** (`riders/tests.py`): `test_freshness_multiplier_is_one_at_full`,
`test_freshness_multiplier_is_penalty_at_floor`,
`test_freshness_multiplier_clamps_out_of_range_input`,
`test_apply_race_cost_floors_at_minimum`,
`test_apply_weekly_recovery_caps_at_full`,
`test_apply_weekly_recovery_skips_excluded_riders`,
`test_generated_rider_starts_at_full_freshness`.
**Load-bearing:** the multiplier must clamp its input; an unclamped value
scales attributes *above* their stored values.

### W2 — `racing/adapters.py`: scale attributes into the engine ✅ done
Add `freshness_scale` to `to_engine_rider` with `_scaled` clamping into 1–100.
**Tests** (`racing/tests.py`): `test_to_engine_rider_scales_attributes_by_freshness`,
`test_to_engine_rider_defaults_to_no_scaling`,
`test_to_engine_rider_never_scales_below_engine_minimum` (a rider at attribute 1
with the floor multiplier must still produce 1, not 0).
**Load-bearing:** this is the only place the penalty exists. Verify
`race_engine/` is untouched by this commit.

### W3 — `racing/services.py`: consume freshness and weight auto-pick ✅ done
Pass `freshness_scale` in `simulate_race`; deduct from finishers inside the
existing transaction; weight `auto_pick_squad`'s sort.
**Tests** (`racing/tests.py`): `test_simulate_race_deducts_freshness_from_finishers`,
`test_simulate_race_does_not_deduct_from_non_finishers`,
`test_auto_pick_prefers_fresher_rider_of_equal_strength`,
`test_auto_pick_still_prefers_much_stronger_tired_rider`.
**Load-bearing:** the deduction goes *inside* `transaction.atomic()`, and only
finishers pay.

### W4 — `world/services.py`: weekly recovery on the tick ✅ done
Call `apply_weekly_recovery(exclude_ids=set(raced))` in `_apply_training_week`.
**Tests** (`world/tests/`): `test_tick_recovers_freshness_for_resting_riders`,
`test_tick_does_not_recover_a_rider_who_raced_that_week`,
`test_three_missed_weeks_recover_three_times` (proves the per-week loop is
honoured rather than collapsed).

### W5 — `api/`: freshness on the squad screen ✅ done
Add it to the view's dict and `SquadRiderSerializer`.
**Tests** (`api/tests.py`): `test_squad_riders_include_freshness_on_display_scale`,
`test_squad_riders_never_expose_recovery_rate`.

### W6 — `frontend/`: show it on the squad selection screen
**Verification:** the browser check in *Verification*, below — this item has no
unit test of its own beyond whatever the screen's existing tests cover.

### W7 — documentation
See *Documentation update*.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7, and each leaves the suite green.

W1 first because everything else calls into it. W2 before W3 because the
adapter change is independently testable without touching a race. W3 before W4
so that consumption exists before recovery — otherwise W4's tests have nothing
to recover *from* and would need to fabricate a lowered freshness by hand.
W5 and W6 last because the screen is the only part that cannot be proven by the
test suite alone.

Commit after each work item.

## Documentation update (required, not optional)

- **`riders/README.md`** — a new *Freshness* section: the two fields, the
  1–100/0–10 convention, the floor and ceiling, the cost-vs-recovery balance and
  why a race must cost more than a week returns. Extend *Visible vs hidden* to
  list `recovery_rate` as hidden and to note that `freshness` is the first
  visible field whose *rate of change* is hidden — the inferability rule is met
  because the player watches the visible number move.
- **`racing/README.md`** — note in the adapter section that
  `to_engine_rider` scales attributes by freshness and that this is the only
  place the penalty is applied; update the *Squads* section's description of
  `auto_pick_squad` (it is no longer purely "by total engine attributes").
- **`world/README.md`** — in *How a tick works*, step 1, say that freshness
  recovery settles alongside training, once per week, excluding riders who
  raced that week.
- **`api/README.md`** — freshness appears on the squad endpoint; the recovery
  rate never does.
- **`frontend/README.md`** — the squad screen now shows freshness.
- **`AGENTS.md`** — the `riders/` row says "Freshness (#59) still to come";
  remove that clause.
- **Delete `specs/rider-freshness.md` and `specs/rider-freshness-plan.md`**
  before opening the PR, per `AGENTS.md`, *Closing a ticket*.

## Verification

```bash
.venv/bin/python -m pytest
```

Then, by hand, against a seeded world with the mock clock:

```bash
GAME_CLOCK_CLASS=world.clocks.MockClock .venv/bin/python manage.py mock_clock set 2027-03-01T09:00
GAME_CLOCK_CLASS=world.clocks.MockClock .venv/bin/python manage.py tick
```

1. Open squad selection. Every rider shows freshness 10.
2. Advance to the first race and tick. The four riders who raced drop to 7
   (100 − 25 = 75 → display 7); everyone else stays 10.
3. Advance a full week and tick. The racers recover toward 10; a rider who
   raced again that week does not.
4. Repeat for seven or eight weeks always fielding the same four. They reach
   display 2 and stop falling — never lower.

**The likeliest failure mode is the penalty silently not applying** — the
plumbing all exists, the numbers all look right on screen, and races are decided
exactly as before because the scaled attributes never reached the engine. A
passing "freshness went down" test proves nothing about this.

**The check that catches it:** simulate the same race twice with the same seed,
once with the field at full freshness and once with one team's riders at the
floor, and assert the finishing order differs — and specifically that the tired
team finishes worse. Add this as
`test_tired_riders_finish_worse_than_fresh_ones_on_the_same_seed` in
`racing/tests.py`. A same-seed comparison is what makes it a real check: without
fixing the seed, engine randomness alone could produce either result.

## Risks

| Risk | Mitigation |
|---|---|
| The penalty is applied to stored attributes instead of in the adapter, permanently damaging riders. | Design decision 1 forbids it; W2's tests assert stored values are unchanged after conversion. Review any `save()` near the race path. |
| Scaled attributes fall below the engine's valid minimum of 1 and raise mid-race. | `_scaled` clamps to `[1, 100]`; W2 has an explicit test at attribute 1. |
| Recovery is collapsed into `weeks * per_week` for a late tick, contradicting #36's per-week rule. | W4's `test_three_missed_weeks_recover_three_times`. |
| Freshness is deducted outside the results transaction and lost when a tick dies mid-race. | Design decision 7; W3's test asserts deduction and results commit together. |
| `recovery_rate` leaks into a serializer. | W5's `test_squad_riders_never_expose_recovery_rate`; the rule is stated in `riders/README.md`. |
| Non-finishers are charged freshness, so an abandoning rider pays twice over. | W3's `test_simulate_race_does_not_deduct_from_non_finishers`. |
| The balance is wrong — riders bottom out too fast or never move. | Verification step 4 walks a full season by hand. Constants are in one place in `riders/services.py` for retuning. |

## Open questions

None.

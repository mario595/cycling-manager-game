# Stage races as an entity — Implementation Plan

**Spec:** `specs/stage-races.md` · **Issue:** #9 · **Status:** proposed
**Apps touched:** `racing/`, `competitions/`, `economy/`, `riders/`, `schedule/`, `world/`, `api/`, `frontend/`

## Context you need

Today every race is a one-day `racing.Race`: declared in a season JSON file
(`schedule/loaders.py`, `manage.py load_season`), claimed by the hourly tick
(`world/services.py` `_claim` → `_execute`), simulated by
`racing.services.simulate_race`, then scored (`competitions.services.score_race`)
and paid (`competitions.services.prizes_by_team` →
`economy.services.pay_race_prizes`). Read `racing/README.md`,
`competitions/README.md`, `schedule/README.md`, `world/README.md` and the
*Freshness* section of `riders/README.md` before starting.

Facts about the current code this plan leans on:

- **One race per calendar day per week** is enforced twice: the loader's
  `(week, day)` check and `Race`'s `UniqueConstraint(week, race_day)`.
  Stages are ordinary `Race` rows on consecutive days, so both still hold
  unchanged — and they are what makes the spec's rider-exclusivity rule true
  (Design decision 9).
- **Squads** (`RaceSquad` + `RaceSquadRider`) are one row per team per race.
  `_write_squad` insists on exactly `SQUAD_SIZE` (4). `simulate_race` already
  drops squad members who have left the team, and `_effective_leader_ids`
  already promotes the lowest-pk remaining member when the leader is gone.
- **`RaceResult.finish_time`** is whole seconds (the engine ticks at 1 s,
  `race_engine/models.py` sets `finish_time = current_time`); `None` means
  DNF (abandon or time cut). `position` is assigned to everyone — anything
  that ranks must filter `finish_time__isnull=False` first.
- **`RacePoints`** is unique on `(race, team)`. **`LedgerEntry`** prize rows
  are unique on `(team, race, position)` for `kind="prize_money"`.
- **Fatigue**: `riders.services.apply_race_cost(rider_ids)` deducts
  `RACE_FRESHNESS_COST` (25) from every starter, floored at 20.
- **Training** reads `racing.services.riders_who_raced(week)`: one training
  entry per race finished. Stages are races, so each finished stage trains —
  this was accepted in the spec's scoping round (a tour trains its four
  riders up to seven times; the fatigue is the price). **Do not change it.**
- **Weekly fanbase and sponsorship** read `competitions.services.points_by_team(week)`,
  a sum over `RacePoints`. GC points land there automatically — accepted in
  scoping: a tour week is the big week.

Repo rules that bite here: `schedule/` library code never imports `racing/`
(the loader gets injected callables); `economy/` never imports `racing/` or
`competitions/` (`world/` computes and passes amounts in); `racing/` never
imports `competitions/` or `world/`; `race_engine/` is untouched by this plan.

## Goal

1. A season file can declare a stage race: 2–7 stages on consecutive days
   inside one week, each stage a normal `Race`.
2. A team's squad and leader are chosen once, for stage 1, and carried to
   every later stage minus riders who did not finish an earlier stage.
3. Every finisher's stage time is normalised to their group's time; a
   general classification (GC) is computable after any stage.
4. Stages score and pay from reduced tables and cost reduced freshness; when
   the last stage finishes the GC is scored and paid from bigger tables.
5. The calendar, race page, squad panel and results screen show the stage
   race, the locked squad and the GC.

## Design decisions (settled — implement these, do not substitute)

**D1. A stage is a `Race` row; a `StageRace` groups them.** New model
`racing.StageRace(name, week)`; `Race` gains nullable `stage_race` FK and
`stage_number`. A one-day race has both null and is **not** modelled as a
one-stage stage race. *Rejected:* a separate `Stage` model — every existing
consumer (tick claim, simulation, squads, results, markers, replay, training,
freshness) works off `Race`, and a second model would mean duplicating all of
it. *Rejected:* one-day race = stage race of length one — it would touch every
existing race, migration included, for no player-visible gain (spec: a player
never sees "Stage 1 of 1").

**D2. `StageRace` stores nothing derivable.** No status, no stage count, no
finished_at, no GC rows. Status is derived from its stages
(`is_complete()`), the count is `stages.count()`, the GC is computed from
`RaceResult` (D6). Same principle as `schedule/`'s "derived, not stored".
The only frozen GC facts are the award rows (`RacePoints(kind=gc)`,
`LedgerEntry(kind=gc_prize_money)`), frozen at award time like every other
award.

**D3. Per-stage squads are carried, not shared.** Each stage keeps its own
`RaceSquad` rows, so `simulate_race`, the results API ("which team did this
rider ride for") and the replay all keep working unmodified. Stage 1's squad
is written the normal way (manager or `ensure_squads` auto-pick). For stage
N > 1, `ensure_squads` does **not** auto-pick: it copies each team's stage-1
squad minus every rider who is no longer in the race (D4), keeping
`is_leader` and `is_auto_picked`. A carried squad may have fewer than four
riders, or be absent entirely for a team with nobody left. **Load-bearing:**
the copy must bypass `_write_squad`'s exactly-four check — write it with a
dedicated `_carry_squad` helper. *Do not* relax `_write_squad` or add a
`force`/`allow_short` flag to it; that check protects every manager write.

**D4. "Still in the race" means: in the stage-1 squad, and finished every
earlier stage that FINISHED.** A rider with `finish_time is None` in any
earlier finished stage is out. A rider with *no* `RaceResult` in an earlier
finished stage (dropped because they left the team mid-tour) is out. Stages
with status `FAILED` are ignored — they have no results, so they cannot put
anyone out and do not count toward the GC. If the leader is out, the carried
squad has no `is_leader` row and `_effective_leader_ids` promotes the
lowest-pk remaining rider for that stage, exactly as it already does for a
departed leader. The stored stage-1 `is_leader` is never rewritten.

**D5. Same group, same time: `RaceResult.group_time`, stored.** For every
finisher, `simulate_race` writes `group_time` = the finish time of the first
rider of their group, where a new group starts whenever the gap to the
*previous* finisher exceeds `GROUP_GAP_SECONDS = 1.0`. Chained, not measured
from the group head: a strung-out bunch arriving over five consecutive seconds
is one group. `1.0` rather than `< 1` because finish times are whole ticks — a
strict `< 1` would only group riders crossing in the same tick, which is
exactly the fraction-of-a-second sprint gap the spec wants gone. Non-finishers
get `None`. Written for **every** race (one-day too) so `simulate_race` has no
stage branch here; only stage results *display* it. **Stored, not computed on
read,** so retuning `GROUP_GAP_SECONDS` never rewrites a GC already shown to
players. `finish_time` and `position` are never altered — stage points and
prizes still come from strict finishing order (spec, *Rules*).

**D6. GC is a pure read over stored results.** `racing.services.general_classification(stage_race, *, through_stage=None)`:
eligible riders are those with a non-null `finish_time` in **every**
`FINISHED` stage with `stage_number <= through_stage`; GC time is the sum of
their `group_time`s. Ordered by `(gc_time, sum of stage positions, rider_id)`
— the stage-position sum is the spec's "better individual stage placings"
tiebreak; `rider_id` only makes it deterministic. Each entry carries the team
the rider rode for, read from the **stage-1 squad**, not `Rider.team` — a
rider cannot change team and stay in the race (D4), and the squad is the
durable record (`racing/README.md`, *Squads*).

**D7. Reduced stage tables, bigger GC tables, all in `competitions/scoring.py`.**

| Position | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| One-day points (unchanged) | 20 | 15 | 12 | 10 | 8 | 6 | 4 | 3 | 2 | 1 |
| **Stage points** | 10 | 8 | 6 | 5 | 4 | 3 | 2 | 2 | 1 | 1 |
| **GC points** | 40 | 30 | 24 | 20 | 16 | 12 | 8 | 6 | 4 | 2 |
| One-day prize (unchanged) | 20,000 | 15,000 | 12,000 | 10,000 | 8,000 | 6,000 | 4,000 | 3,000 | 2,000 | 1,000 |
| **Stage prize** | 10,000 | 7,500 | 6,000 | 5,000 | 4,000 | 3,000 | 2,000 | 1,500 | 1,000 | 500 |
| **GC prize** | 40,000 | 30,000 | 24,000 | 20,000 | 16,000 | 12,000 | 8,000 | 6,000 | 4,000 | 2,000 |

Stage ≈ half a one-day race, GC = double. A 5-stage tour is worth at most
5×10 + 40 = 90 points over five race days: more than a classic in total (the
spec's "worth building a squad around"), less per day (the spec's "without a
7-stage tour paying out seven times a classic"). These are tuning constants —
change the numbers freely, never the shape. All six tables cover positions
1–10; extend the existing table-drift test to all of them.

GC scoring mirrors one-day scoring: **points** to each team's best GC rider,
**prize** to every placed GC rider. Stage scoring is exactly `score_race` /
`prizes_by_team` with the stage tables.

**D8. GC awards attach to the final stage.** `RacePoints` gains
`kind` (`race` | `gc`, default `race`); uniqueness becomes
`(race, team, kind)`. GC rows have `race` = the stage race's highest-numbered
stage, whatever its status. That keeps `standings()` (`race__week__season`)
and `points_by_team(week)` (`race__week`) correct with **no code change**.
Countback counts GC rows' positions alongside stage rows — accepted: a GC win
is a 1st place. Ledger: new `LedgerEntry.Kind.GC_PRIZE_MONEY =
"gc_prize_money"`, `race` = the final stage, its own partial unique
constraint `(team, race, position)`. **A separate kind is load-bearing:**
sharing `prize_money` would collide with the final stage's own prize for the
same `(team, race, position)` and one of the two payouts would be silently
dropped by the `IntegrityError` catch in `pay_race_prizes`.

**D9. Rider exclusivity is guaranteed by the calendar, not by a check.**
Stages occupy consecutive days of one week, and no two races share a day, so a
rider cannot race anything else while a tour is running. Selecting a tour
rider for a race *after* the tour (e.g. that Sunday) is allowed — that race
starts after the tour ends, which is what the spec's rule protects. Do **not**
add a squad-selection check; there is nothing it could catch.

**D10. Freshness: `STAGE_FRESHNESS_COST = 10` per stage** in
`riders/services.py`, next to `RACE_FRESHNESS_COST`. `apply_race_cost` takes a
`cost` keyword (default `RACE_FRESHNESS_COST`); `simulate_race` passes
`STAGE_FRESHNESS_COST` when `race.stage_race_id` is set. A 3-stage race costs
30 (> one race, 25); a 7-stage race costs 70 — a fresh rider ends a full tour
at 30, above the floor of 20, having ridden stage 4 at 60 (multiplier ~0.90).
Weekly recovery is unchanged: tour riders started races that week, so they
skip it, like any racer.

**D11. The GC is settled by `world/`, when the stage race completes.**
`StageRace.is_complete()` = every stage is `FINISHED` or `FAILED` and at least
one is `FINISHED`. `world.services._execute` calls `_settle_stage_race` after
each stage it processes — **on both the success and the failure path**, so a
failed final stage still settles the GC over the stages that ran. Settling is
`score_general_classification` + `pay_gc_prizes`, both idempotent. Neither
`racing/` nor `competitions/` triggers it: `racing/` may not import
`competitions/`, and settlement is orchestration.

**D12. Squad selection happens on stage 1 only.** `set_squad` raises
`SquadError` for `stage_number > 1`. The squad API reports `editable: false`
for later stages and returns the carried squad (computed read-only via D4
before the stage has run; the stored carried rows after). No per-stage leader
choice (spec, *Out of scope*).

**D13. Season file: a top-level `stage_races` list.** Each entry names the
tour, its week, its first day, a default time and 2–7 stage objects; stage *i*
runs on `start_day + i`. Stage `Race.name` is
`"<tour> — Stage <n>"`, or `"<tour> — Stage <n>: <stage name>"` when a stage
names itself. Every stage's `(week, day)` joins the **same** duplicate check
as one-day races, so a clash names both entries. *Rejected:* a `stage_race`
key on ordinary race entries — it makes consecutiveness, ordering and the
2–7 rule a cross-entry check and lets an admin scatter a tour through the
file.

## Data model

### `racing.StageRace` (new, `racing/models.py`)

| Field | Type | Notes |
|---|---|---|
| `name` | `CharField(max_length=120)` | not blank. 120 leaves room for `" — Stage 7: …"` inside `Race.name`'s 150. |
| `week` | `ForeignKey("schedule.Week", on_delete=PROTECT, related_name="stage_races")` | not null. String reference, like `Race.week`. |
| (inherited) `created_at`, `updated_at` | `TimeStampedModel` | |

Methods (no stored state):

```python
def final_stage(self) -> Race:          # highest stage_number
def is_complete(self) -> bool:          # D11
```

### `racing.Race` (changed)

| Field | Type | Notes |
|---|---|---|
| `stage_race` | `ForeignKey(StageRace, on_delete=PROTECT, null=True, blank=True, related_name="stages")` | null for one-day races. PROTECT: deleting a tour must never cascade to raced stages. |
| `stage_number` | `PositiveSmallIntegerField(null=True, blank=True)` | 1-based. Null iff `stage_race` is null. |

New constraints on `Race.Meta`:

```python
models.UniqueConstraint(fields=["stage_race", "stage_number"], name="one_race_per_stage_number"),
models.CheckConstraint(
    condition=Q(stage_race__isnull=True, stage_number__isnull=True)
            | Q(stage_race__isnull=False, stage_number__gte=1),
    name="stage_number_iff_stage_race",
),
```

(`condition=` is right for the installed Django 6.1; `check=` is the removed
pre-5.1 spelling.) `Race.clean()` additionally rejects a
stage whose `week_id` differs from `stage_race.week_id`.

### `racing.RaceResult` (changed)

| Field | Type | Notes |
|---|---|---|
| `group_time` | `FloatField(null=True, blank=True)` | D5. Null for non-finishers and for every result recorded before this migration. |

Migration: `racing/migrations/0008_stage_race.py` — schema only, no data
migration. Old results keep `group_time = NULL`; nothing reads it for
one-day races.

### `competitions.RacePoints` (changed)

| Field | Type | Notes |
|---|---|---|
| `kind` | `CharField(max_length=8, choices=Kind.choices, default=Kind.RACE)` | `Kind.RACE = "race"`, `Kind.GC = "gc"`. Existing rows become `race`. |

Replace `one_points_row_per_team_per_race` with
`UniqueConstraint(fields=["race", "team", "kind"], name="one_points_row_per_team_race_kind")`.
Migration: `competitions/migrations/0002_racepoints_kind.py`.

### `economy.LedgerEntry` (changed)

New choice `GC_PRIZE_MONEY = "gc_prize_money", "General classification prize"`
(14 chars, fits `max_length=32`). New constraint:

```python
models.UniqueConstraint(
    fields=["team", "race", "position"],
    condition=models.Q(kind="gc_prize_money"),
    name="one_gc_prize_entry_per_team_race_position",
),
```

Update the `race`/`position` help texts to say "prize_money and
gc_prize_money". Migration: `economy/migrations/0012_gc_prize_money.py`.

## `racing/services.py`

```python
GROUP_GAP_SECONDS = 1.0

def group_times(finish_times: list[float]) -> list[float]: ...
def carried_squad(race: Race, team: Team) -> tuple[list[int], int | None]: ...
def riders_still_in(stage_race: StageRace, before_stage: int) -> set[int]: ...
def general_classification(stage_race: StageRace, *, through_stage: int | None = None) -> list[GCEntry]: ...
def create_stage_race(*, name: str, week) -> StageRace: ...   # injected into the loader
```

`GCEntry` is a frozen dataclass: `rider_id: int`, `team_id: int | None`,
`gc_time: float`, `position_sum: int`, `stages: int`.

**`group_times`** — pure, input sorted ascending, real code because the
off-by-one is the likely bug:

```python
def group_times(finish_times: list[float]) -> list[float]:
    """Each finisher's group time: the time of the first rider of their group.
    A new group starts when the gap to the PREVIOUS finisher exceeds
    GROUP_GAP_SECONDS. Input must be sorted ascending (finishers only)."""
    out: list[float] = []
    for i, t in enumerate(finish_times):
        if i == 0 or t - finish_times[i - 1] > GROUP_GAP_SECONDS:
            head = t
        out.append(head)
    return out
```

**`simulate_race`** changes, all inside the existing results transaction:

1. Build `group_by_state` from the finishers in `ordered`
   (`[s for s in ordered if s.finish_time is not None]`, already ascending),
   and set `group_time=` on each `RaceResult(...)` in the `bulk_create`.
2. `apply_race_cost(ids, cost=STAGE_FRESHNESS_COST if race.stage_race_id else RACE_FRESHNESS_COST)`.

**`ensure_squads`** — first line branches:

```python
if race.stage_race_id and race.stage_number > 1:
    _carry_squads(race)
    return
```

**`riders_still_in(stage_race, before_stage)`** — D4, one query per input:

```python
stage1 = stage_race.stages.get(stage_number=1)
squad_riders = set(RaceSquadRider.objects.filter(squad__race=stage1).values_list("rider_id", flat=True))
earlier = list(stage_race.stages.filter(stage_number__lt=before_stage, status=Race.Status.FINISHED)
               .values_list("pk", flat=True))
if not earlier:
    return squad_riders
finished = (RaceResult.objects.filter(race_id__in=earlier, finish_time__isnull=False)
            .values("rider_id").annotate(n=Count("pk")).filter(n=len(earlier))
            .values_list("rider_id", flat=True))
return squad_riders & set(finished)
```

**`_carry_squads(race)`** — for each stage-1 `RaceSquad` (prefetch members):
keep members whose `rider_id` is in `riders_still_in(stage_race, race.stage_number)`;
if none remain, write nothing for that team; else in one `transaction.atomic()`
`update_or_create` the stage's `RaceSquad(race, team, is_auto_picked=<stage-1 flag>)`,
delete its members, `bulk_create` the kept members with their stage-1
`is_leader`. Idempotent: running it twice gives the same rows.

**`carried_squad(race, team)`** — the read-only version for the API: the same
filter applied to one team's stage-1 squad, returning `(rider_ids, leader_id
or None)`. `_carry_squads` and `carried_squad` must share the one
`riders_still_in` call — do not implement D4 twice.

**`set_squad`** — after the status check:

```python
if race.stage_number and race.stage_number > 1:
    raise SquadError(f"{race} is a later stage; the squad is chosen for stage 1")
```

**`general_classification`** — D6:

```python
stages = stage_race.stages.filter(status=Race.Status.FINISHED)
if through_stage is not None:
    stages = stages.filter(stage_number__lte=through_stage)
stage_ids = list(stages.values_list("pk", flat=True))
if not stage_ids:
    return []
rows = RaceResult.objects.filter(race_id__in=stage_ids).values_list(
    "rider_id", "finish_time", "group_time", "position")
# accumulate per rider; eligible iff len(stage_ids) finishes with non-null finish_time
team_by_rider = dict(RaceSquadRider.objects.filter(squad__race__stage_race=stage_race,
                     squad__race__stage_number=1).values_list("rider_id", "squad__team_id"))
return sorted(entries, key=lambda e: (e.gc_time, e.position_sum, e.rider_id))
```

`group_time` is non-null whenever `finish_time` is (D5), so sum it directly —
but assert it in a test rather than coalescing silently.

## `riders/services.py`

```python
STAGE_FRESHNESS_COST = 10

def apply_race_cost(rider_ids: list[int], *, cost: int = RACE_FRESHNESS_COST) -> int: ...
```

Nothing else changes. `racing/` imports the constant; `riders/` does not
learn about stage races.

## `competitions/scoring.py`

Add `STAGE_POINTS_BY_POSITION`, `GC_POINTS_BY_POSITION`,
`STAGE_PRIZE_BY_POSITION`, `GC_PRIZE_BY_POSITION` (D7 values) and
`stage_points_for`, `gc_points_for`, `stage_prize_for`, `gc_prize_for`, each
`TABLE.get(position, 0)`.

## `competitions/models.py`

`RacePoints.Kind` (`TextChoices`), the `kind` field and the constraint swap
(see *Data model*).

## `competitions/services.py`

- **`score_race(race)`**: pick the table by `race.stage_race_id`. The
  existing-rows early return must filter `kind=RacePoints.Kind.RACE`, or the
  final stage — which gains a GC row — would look "already scored" if
  anything ever scored the GC first. Create rows with `kind=RACE`.
- **`prizes_by_team(race)`**: same table switch.
- **`score_general_classification(stage_race) -> list[RacePoints]`** (new):
  raises `ValueError` unless `stage_race.is_complete()`. Early-returns
  existing `kind=GC` rows for the final stage. Otherwise walks
  `general_classification(stage_race)` in order, position = index + 1, first
  entry per `team_id` is that team's best, skips `team_id is None` and
  zero-point positions, `bulk_create(..., ignore_conflicts=True)` with
  `race=stage_race.final_stage()`, `kind=GC`.
- **`gc_prizes_by_team(stage_race) -> dict[int, list[tuple[int, int]]]`**
  (new): same shape as `prizes_by_team`, every placed GC rider, GC prize
  table.

`standings`, `points_by_team`, `_countback_key`: **unchanged** (D8).

## `economy/services.py`

Refactor `pay_race_prizes`' loop into a private
`_pay_prizes(kind, race_id, description, at, prizes_by_team) -> int` and add:

```python
def pay_gc_prizes(final_stage_id: int, *, stage_race_name: str, at,
                  prizes_by_team: dict[int, list[tuple[int, int]]]) -> int:
    """GC prize money, kind=gc_prize_money, race=final stage. Idempotent via
    its own (team, race, position) constraint — see the plan's D8."""
```

Description: `f"General classification — {stage_race_name}"[:120]`.
`pay_race_prizes`' public signature does not change.

## `world/services.py`

In `_execute`, restructure so the stage-race hook runs after both paths:

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
        tick.error += ...
    else:
        try:
            ... existing prize payout ...
        except Exception:
            tick.error += ...
    if race.stage_race_id:
        _settle_stage_race(race.stage_race, tick, at)
```

```python
def _settle_stage_race(stage_race, tick, at) -> None:
    """Score and pay the GC once every stage has run (D11). Idempotent; a
    failure is recorded on the tick, never raised."""
    if not stage_race.is_complete():
        return
    try:
        score_general_classification(stage_race)
        tick.prize_entries += pay_gc_prizes(
            stage_race.final_stage().pk, stage_race_name=stage_race.name, at=at,
            prizes_by_team=gc_prizes_by_team(stage_race),
        )
    except Exception:
        tick.error += f"stage race {stage_race.pk} GC:\n{traceback.format_exc()}\n"
```

`race.stage_race` must be re-read fresh inside the helper
(`is_complete()` queries), never cached across loop iterations — a catch-up
tick runs several stages of one tour in one `_execute` call, and only the
last one completes it.

**Ordering is load-bearing:** `_claim` orders by `starts_at`, and stages are
a day apart, so within one tick stage N always runs before stage N+1, and
`_carry_squads` for N+1 reads N's committed results. Do not parallelise
`_execute`.

## `schedule/loaders.py`

- `_KNOWN_KEYS` gains `"stage_races"`.
- New constants: `STAGE_RACE_MIN_STAGES = 2`, `STAGE_RACE_MAX_STAGES = 7`.
- New `StageRaceDeclaration(name: str, week: int, stages: list[RaceDeclaration])`;
  `SeasonDeclaration` gains `stage_races: list[StageRaceDeclaration] = field(default_factory=list)`.
- `_parse_stage_race(raw, path, warnings)`: known keys `{"name", "week",
  "start_day", "time", "stages"}`; stage known keys `{"name", "time", "course",
  "wind", "seed", "markers"}`. `name` non-empty, ≤ 120. `week` as for races.
  `start_day` in `DAY_INDEX`. `time` via `_parse_time`, overridable per stage.
  `stages` a list of 2–7. `DAY_INDEX[start_day] + len(stages) - 1 > 6` →
  `SeasonFileError(f"{path} runs past Sunday: {n} stages from {start_day}")`.
  Each stage is parsed into a `RaceDeclaration` — reuse `_parse_course`,
  `_parse_markers`, `_parse_wind`, `_parse_seed` — with `day` =
  the weekday name at `DAY_INDEX[start_day] + i` and the D13 name.
- `parse_season_file`: after the one-day loop, parse `stage_races`; feed every
  stage's `(week, day)` into the **same** `seen` dict so a clash with a
  one-day race or another tour's stage raises the existing "two races on
  week N day" error naming both.
- New `create_stage_races(season, declarations, *, create_race, create_stage_race) -> list[Any]`:
  per declaration, `sr = create_stage_race(name=d.name, week=weeks[d.week])`,
  then per stage `create_race(..., stage_race=sr, stage_number=n)` with the
  same `starts_at` arithmetic `create_races` uses (factor that arithmetic
  into a private `_starts_at(week, day, time)` shared by both). Returns the
  created stage races. `create_races`' signature is **unchanged**.

## `schedule/management/commands/load_season.py`

Inside `handle()` (never module scope), additionally import
`racing.models.StageRace` and `racing.services.create_stage_race`.

- `--replace`: delete order becomes races → stage races → season
  (`Race.stage_race` and `StageRace.week` are both `PROTECT`):
  ```python
  Race.objects.filter(week__season=existing).delete()
  StageRace.objects.filter(week__season=existing).delete()
  existing.delete()
  ```
- After `create_races`, call `create_stage_races(season, declaration.stage_races, ...)`
  inside the same `transaction.atomic()`.
- Output one line per stage race: `week 6 Tue–Sat — Alpine Tour (5 stages, 612.0 km)`.

## `seasons/season-1.example.json`

Add a `stage_races` list with two tours, so seeded worlds show the feature:

- **Alpine Tour**, week 6, `start_day: "monday"`, 5 stages (flat opener,
  rolling, mountain, mountain, flat), each with one sprint or mountain marker.
  Mon–Fri; the existing Sunday race stays.
- **Coastal Three Days**, week 10, `start_day: "wednesday"`, 3 stages.

Keep courses 90–180 km, like the existing races.

## `api/views.py` and `api/serializers.py`

- **Calendar** `_race_payload`: add `"stage_race": {"id", "name",
  "stage_number", "stage_count"}` or `None`. Prefetch with
  `prefetch_related("races__stage_race__stages")` — **not** a
  `stages.count()` per race, which is N+1 across the calendar.
- **Race detail**: add `"stage_race"`: `None` or `{"id", "name",
  "stage_number", "stage_count", "stages": [{"id", "stage_number",
  "starts_at", "status"}]}`. `"payout"` uses the stage tables for a stage;
  new `"gc_payout"` (`[]` for a one-day race) lists the GC tables.
- **Squad**: `_squad_payload` gains `"stage_race": {"name",
  "stage_number"}` or `None`; `editable` = `status == SCHEDULED and not
  later-stage`. `SquadView.get` for a later stage returns `carried_squad(race,
  team)` with `saved=True`. `leader_id` may be `None` there — the payload's
  `is_leader` is simply false for everyone. `put` needs no change:
  `set_squad` refuses (D12) and the view already turns `SquadError` into 400.
- **Results** (`RaceResultsView`):
  - `race.points` → filter `kind=RacePoints.Kind.RACE`. **Forgetting this**
    puts the GC award into the final stage's team-points table.
  - `_result_row` adds `"group_time"`.
  - `payload["race"]` adds the calendar-shaped `"stage_race"` block.
  - New `payload["gc"]`: `None` for a one-day race; else
    `{"after_stage": n, "final": bool, "standings": [{"position", "rider",
    "team", "gc_time", "gap"}], "points": [...]}` from
    `general_classification(stage_race, through_stage=race.stage_number)`.
    `final` = `stage_race.is_complete()` and no FINISHED stage has a higher
    number than this one. `points` is `[]` unless `final`; when final it lists
    the `RacePoints(kind=GC)` rows of the final stage with each team's summed
    `gc_prize_money` ledger amount — same shape as the existing `points`
    entries.
- New serializers for each block; keep field names exactly as above so the
  SPA types in W10 match.

## `frontend/`

- **`src/api.ts`**: `StageRaceRef` (`id, name, stage_number, stage_count`) on
  `CalendarRace` and on `RaceResults.race`; `RaceDetail.stage_race` (with
  `stages`) and `RaceDetail.gc_payout`; `Squad.stage_race`;
  `RaceResultEntry.group_time`; `RaceResults.gc` (`GCStandings | null`);
  `'gc_prize_money'` in `LedgerEntry['kind']`.
- **`screens/Calendar.tsx`** `WeekRow`: fold consecutive races sharing a
  `stage_race.id` into one `StageRaceRow` — a header ("Alpine Tour · 5
  stages · Mon–Fri") over the existing `RaceRow`s for each stage, labelled
  "Stage n". One-day races render exactly as today. `HeaderStats` still
  counts stages as races ridden.
- **`screens/Race.tsx`**: under the heading, a stage strip ("Stage 2 of 5 —
  Alpine Tour" with links to each stage via `racePath`). `PayoutTable` gets a
  second table from `gc_payout` titled "General classification". In
  `SquadPanel`, a one-line note: on stage 1 "This squad and leader ride every
  stage of <tour>."; on later stages "Chosen at stage 1 — riders who
  didn't finish an earlier stage are out."
- **`components/RaceResults.tsx`**: `RiderResultsTable` computes gaps from
  `group_time` when `results.race.stage_race` is set, from `finish_time`
  otherwise (a one-day race's display must not change). New
  `GeneralClassificationCard`: title "General classification after stage n"
  or "Final general classification", rows position / rider (linked) / team /
  GC time for the leader and `+gap` for the rest; when `final`, a team
  points-and-prize list under it in the `TeamPointsTable` style. Rendered
  from the race screen's results section when `results.gc` is non-null.
- **`screens/Finances.tsx`**: `KIND_LABELS.gc_prize_money =
  'General classification prize'` (the `Record` type forces this — the build
  fails without it).
- Money shown with `$` and thousands separators (`AGENTS.md`, *Displaying
  game money*); use `formatMoney` from `src/format.ts`.
- No mockup exists for stage races in `design/`; reuse `primitives.tsx` and
  the calendar's existing row styling rather than inventing a new look.

## Work items

### W1 — `racing/models.py`: `StageRace`, `Race.stage_race`/`stage_number`, `RaceResult.group_time` — done
Models, constraints, `clean()` week check, `final_stage()`, `is_complete()`,
migration `0008_stage_race`, admin registration beside `Race`'s.
Tests in `racing/tests.py`: `test_stage_number_requires_stage_race` (check
constraint raises `IntegrityError`), `test_stage_numbers_unique_within_stage_race`,
`test_stage_must_share_stage_race_week`, `test_is_complete_*` (all
scheduled → False; mixed finished/failed → True; all failed → False),
`test_final_stage_is_highest_number`.

### W2 — `riders/services.py` + `racing/services.py`: group times and stage fatigue — done
`STAGE_FRESHNESS_COST`, `apply_race_cost(cost=)`, `GROUP_GAP_SECONDS`,
`group_times`, both wired into `simulate_race`.
Tests: `riders/tests/test_services.py::test_apply_race_cost_custom_cost`;
`racing/tests.py::test_group_times_chains_consecutive_gaps` (e.g.
`[100,100,101,102,105,106]` → `[100,100,100,100,105,105]`),
`test_group_times_gap_just_over_threshold_splits`,
`test_simulate_race_writes_group_time_for_finishers_only`,
`test_simulate_stage_costs_stage_freshness` vs
`test_simulate_one_day_race_costs_race_freshness`.

### W3 — `racing/services.py`: carried squads and the stage-1 lock — done
`riders_still_in`, `_carry_squads`, `carried_squad`, the `ensure_squads`
branch, the `set_squad` refusal, `create_stage_race`.
Tests: `test_later_stage_carries_stage_one_squad_and_leader`,
`test_rider_dnf_in_stage_is_not_carried`,
`test_failed_stage_does_not_remove_anyone`,
`test_team_with_no_riders_left_gets_no_squad`,
`test_leader_out_promotes_lowest_pk_for_the_stage` (assert the stored
stage-1 `is_leader` is unchanged), `test_set_squad_refuses_later_stage`,
`test_later_stage_never_auto_picks` (team without a stage-1 squad gets none
at stage 2). **Load-bearing:** the short-squad path must not go through
`_write_squad`.

### W4 — `racing/services.py`: `general_classification` — done
Tests: `test_gc_sums_group_times`, `test_gc_excludes_rider_who_missed_a_stage`,
`test_gc_through_stage_ignores_later_stages`,
`test_gc_ignores_failed_stage`, `test_gc_tie_broken_by_stage_position_sum`,
`test_gc_team_is_stage_one_squad_team`,
`test_finisher_always_has_group_time` (the invariant D6 relies on).

### W5 — `competitions/`: tables, `RacePoints.kind`, stage and GC scoring — done
`scoring.py` tables, `RacePoints.Kind` + migration `0002_racepoints_kind`,
`score_race`/`prizes_by_team` table switch, `score_general_classification`,
`gc_prizes_by_team`.
Tests: `test_scoring.py::test_all_tables_cover_same_positions` (a sibling of
the existing `test_prize_table_matches_points_table_positions`, covering all
six tables), `test_services.py::test_stage_scored_from_stage_table`,
`test_prizes.py::test_stage_prizes_from_stage_table`,
`test_services.py::test_gc_scored_once_on_final_stage` (second call returns
the same rows), `test_gc_refuses_incomplete_stage_race`,
`test_gc_row_and_final_stage_row_coexist`,
`test_standings.py::test_standings_include_gc_points`.

### W6 — `economy/`: `GC_PRIZE_MONEY` and `pay_gc_prizes` — done
Kind, constraint, migration `0012_gc_prize_money`, `_pay_prizes` refactor,
`pay_gc_prizes`.
Tests in `economy/tests/test_services.py`: `test_pay_gc_prizes_idempotent`,
`test_gc_prize_and_stage_prize_same_team_race_position_both_recorded`
(**the D8 collision test** — must fail if `pay_gc_prizes` reuses
`prize_money`), and the existing `pay_race_prizes` tests unchanged and green.

### W7 — `world/services.py`: settle the GC — done
`_execute` restructure and `_settle_stage_race`.
Tests in `world/tests/test_tick.py`: `test_tick_runs_stage_race_and_settles_gc`
(mock clock across all stages: GC `RacePoints` and `gc_prize_money` rows
exist exactly once), `test_catch_up_tick_runs_all_stages_in_order` (one
tick, clock past the last stage: carried squads correct, GC settled),
`test_failed_final_stage_still_settles_gc`,
`test_gc_not_settled_until_last_stage`.

### W8 — `schedule/`: declaring stage races — done
Loader, `load_season` changes, the example season file.
Tests: `schedule/tests/test_loaders.py` —
`test_stage_race_parsed_onto_consecutive_days`,
`test_stage_race_names`, `test_stage_race_too_few_stages`,
`test_stage_race_too_many_stages`, `test_stage_race_runs_past_sunday`,
`test_stage_clashes_with_one_day_race` (error names both),
`test_stage_time_overrides_default`, `test_unknown_stage_key_warns`;
`schedule/tests/test_load_season.py` —
`test_load_season_creates_stage_races`,
`test_replace_deletes_stage_races`, and
`test_example_season_file_loads` (loads `seasons/season-1.example.json`).

### W9 — `api/`: calendar, race detail, squad, results — done
Tests in `api/tests.py`: `test_calendar_race_carries_stage_race`,
`test_calendar_query_count_does_not_grow_with_stages`
(`django_assert_max_num_queries`), `test_race_detail_stage_payout_and_gc_payout`,
`test_squad_later_stage_is_read_only_carried`,
`test_squad_put_later_stage_400`,
`test_results_stage_points_exclude_gc_rows`,
`test_results_gc_after_stage`, `test_results_final_gc_has_points_and_prizes`,
`test_results_one_day_race_gc_is_null`.

### W10 — `frontend/`: calendar, race page, results, finances — done
Tests: `screens/Calendar` — add `Calendar.test.tsx` with
`groups stages of a stage race under one header` and `renders one-day races
unchanged`; `screens/Race.test.tsx` — `shows stage strip and GC payout`,
`squad note on stage 1`, `later stage squad is read-only`;
a `RaceResults` test — `stage gaps use group_time`, `one-day gaps use
finish_time`, `renders final GC with points and prizes`;
`screens/Finances.test.tsx` — `labels gc prize money`. Run `npm test` and
`npm run build` (type errors in the `KIND_LABELS` record show up there).

### W11 — documentation — done
See *Documentation update*. Its own commit.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7 → W8 → W9 → W10 → W11, one commit each,
full `pytest` green before each commit.

- W1 first: every later item needs the fields.
- W2 before W3/W4: the GC sums `group_time`, and carried squads are only
  testable against results `simulate_race` actually wrote.
- W3 before W4: GC eligibility and carrying share D4's definition — getting
  the carry right first means W4's tests run on realistic stage sequences.
- W5 and W6 before W7: `world/` only wires them together.
- W8 after W7: a loadable stage race is only useful once the tick can finish
  it; it also gives W9/W10 real seed data.
- W9 before W10: the SPA types are copied from the API payloads.

Stop and show the user after W7 (the game can run a tour end to end, headless)
and after W10.

## Documentation update (required, not optional)

- **`racing/README.md`**: new section *Stage races* — `StageRace`, the
  stage fields, D2 (nothing stored), D3/D4 (carried squads, who is still in,
  why the carry bypasses `_write_squad`), D5 (`group_time`, why stored, why
  chained, the 1 s threshold), D6 (GC read, tiebreak, team from stage-1
  squad). Update *What lives here*'s table, *Squads* (the exactly-four rule's
  one exception), and *Simulating a race* (group time, stage fatigue cost).
- **`competitions/README.md`**: the stage and GC tables beside *The points
  table* and *The prize table sits beside it*; `RacePoints.kind` and why GC
  rows hang off the final stage (D8); countback counts GC positions.
  Remove "Stage races" from anything listing them as future.
- **`economy/README.md`**: `gc_prize_money` in the list of kinds and why it
  is its own kind (the D8 collision).
- **`riders/README.md`**, *Freshness*: `STAGE_FRESHNESS_COST` and the
  arithmetic in D10.
- **`schedule/README.md`**: *The `stage_races` list* under *Declaring a
  season* with a JSON example and key table; *One race per day* notes that
  stages go through the same check; *Replacing a season with races* gets the
  new delete order; *What `schedule/` may import* lists the two new
  in-`handle()` imports.
- **`world/README.md`**: *How a tick works* — `_settle_stage_race`, why it
  runs on the failure path too, why ordering within `_execute` matters.
- **`api/README.md`**: the new payload blocks (`stage_race`, `gc`,
  `gc_payout`, `group_time`) and the later-stage squad behaviour.
- **`frontend/README.md`**, *What exists*: stage races on the calendar,
  stage strip, GC card.
- **`AGENTS.md`**: the `racing/` and `competitions/` rows mention stage races
  and the GC; the *Seeding* section notes the example season now declares two
  stage races (weeks 6 and 10).
- **`specs/roadmap.md`**: #9 into *Part 1 — Done*.

Then set `Status: implemented` on the spec and this plan and move both to
`specs/archive/` (`AGENTS.md`, *Closing a ticket*).

## Verification

Unit tests prove each piece; this proves a tour actually plays. In the
worktree:

```bash
.venv/bin/python scripts/dev_db.py
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_user
.venv/bin/python manage.py seed_teams --claim-for test@mail.com
.venv/bin/python manage.py seed_trainers
.venv/bin/python manage.py load_season seasons/season-1.example.json
GAME_CLOCK_CLASS=world.clocks.MockClock .venv/bin/python manage.py mock_clock set 2027-04-05T00:00
GAME_CLOCK_CLASS=world.clocks.MockClock .venv/bin/python manage.py tick
```

Then, before stage 1: log in as `test@mail.com`, open the Alpine Tour's
stage 1, pick a squad with a deliberately weak leader, save. Advance one
stage at a time (`mock_clock advance --to-next` then `tick`, five times) and
after each:

1. **Carried squad** — in `manage.py shell`, stage N's squad for the demo
   team equals stage 1's minus any DNF, and the stage-1 `is_leader` row is
   unchanged. *This catches the likeliest bug: `ensure_squads` auto-picking a
   fresh four for a later stage.* A fresh auto-pick would show a different,
   stronger set of riders on stage 2.
2. **Freshness** — the demo team's four riders drop exactly 10 per stage (or
   stop at 20).
3. **Results screen** — stage gaps show bunch finishers on the same time
   (`+0:00`), and the GC card's leader changes as expected across stages.
4. **Squad panel** on stage 2+ is read-only with the carried riders.

After the final stage: `RacePoints.objects.filter(kind="gc")` has one row per
scoring team, attached to stage 5; the Finances screen shows a "General
classification prize" line; the standings include the GC points; re-running
`tick` writes no new GC rows or ledger entries (idempotency). Finally the
Sunday one-day race in week 6 runs and its results page looks exactly as
before — no GC card, gaps from `finish_time`.

## Risks

| Risk | Mitigation |
|---|---|
| `ensure_squads` auto-picks a fresh squad for stage 2+, silently undoing the lock. | D3's branch is the first line of `ensure_squads`; W3's `test_later_stage_never_auto_picks`; verification step 1. |
| Relaxing `_write_squad`'s four-rider check to make carrying work, opening manager writes to short squads. | D3 forbids it; `_carry_squads` is a separate writer. Existing `set_squad` size tests stay. |
| GC prize written as `prize_money` and silently dropped against the final stage's own prize. | D8's separate kind; W6's collision test. |
| Final stage's results table shows the GC award as stage points. | `kind=RACE` filter in `RaceResultsView`; W9 `test_results_stage_points_exclude_gc_rows`. |
| `score_race`'s early return sees a GC row and skips scoring a stage. | Early return filters `kind=RACE`; W5 `test_gc_row_and_final_stage_row_coexist`. |
| `group_times` off-by-one (`>=` vs `>`) splits every bunch that arrives over two ticks. | Real code in this plan; W2's threshold test pins `> 1.0`. |
| A failed final stage leaves the GC unsettled forever. | D11: settle on the failure path too; W7 test. |
| GC scoring raises mid-tick and nothing retries it. | Both halves idempotent; error recorded on `TickRun.error`. Rerunning `_settle_stage_race` from a shell is safe. A retry sweep is not worth building until it happens. |
| Tour weeks inflate fanbase and sponsorship swings (`points_by_team` includes GC). | Accepted in scoping. Tables are constants; retune if a playtest says so. |
| A rider sold or released mid-tour vanishes from later stages and the GC. | Consistent with existing squad behaviour (`simulate_race` drops departed riders). Not blocked — auctions resolve on wall-clock deadlines and blocking them mid-tour is out of this spec. |
| Calendar becomes N+1 on stage counts. | Prefetch; W9 query-count test. |
| Two concurrent ticks run stage N and N+1 out of order. | Stages are a day apart and ticks are hourly; `_claim` orders by `starts_at` and locks. No extra guard. |

## Open questions

None.

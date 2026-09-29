# Youth intake generation — Implementation Plan

**Spec:** `specs/archive/youth-intake.md` · **Issue:** #33 · **Status:** implemented
**Apps touched:** `riders/`, `transfers/`, `teams/`, `world/`, `api/`, `frontend/`

## Context you need

A team can open a **development squad** (#32, merged): `riders.DevelopmentSquad`
is a one-to-one row per team holding a `level` (1 Regional, 2 National,
3 Elite). Opening, upgrading and closing live in `riders/development_squad.py`.
Closing **deletes** the row. `teams.services.claim_team` calls `close_squad(team)`,
and `release_team` does not touch the squad. The tick charges each open squad's
weekly cost. **Nothing populates the squad yet.** That is this ticket. Read
`riders/README.md`, *Development squad* and *Generation*, before starting.

What you will lean on:

- **`Rider.team`** (`riders/models.py`) is a nullable FK. Today `NULL` means
  "free agent" (or retired). **Every roster-shaped query in the codebase filters
  on `team`**:
  - wages: `economy.services.charge_weekly_wages` sums `Team.riders`;
  - trainer focus: `world.services._apply_training_week` iterates `trainer.team.riders`;
  - the roster cap: `transfers.services.ROSTER_CAP` counts `Rider.objects.filter(team=team)`;
  - auctions and releases: `list_for_auction` and `release_rider` check `rider.team_id == team.pk`;
  - race squads: `racing.services.set_squad` filters `pk__in=ids, team=team`;
  - the roster GET: `api.views.RiderListView` filters `team=team`.
- **The free-agent pool** is `transfers.services.free_agents()`, which is
  `Rider.objects.active().filter(team__isnull=True)`. `world.services._expire_free_agents`
  reads it, and so does `api.views.FreeAgentsView`. `sign_free_agent` checks
  `rider.team_id is not None` under a row lock.
- **Generation** is `riders.generation.generate_rider(...)`, which returns an
  unsaved `Rider` with hidden traits rolled. `_roll_potential` derives potential
  from quality and age. The model's age validator is `MinValueValidator(18)`,
  and the same `_MIN_AGE = 18` is **copied** into `riders/pricing.py` and
  `transfers/pricing.py`.
- **The tick** (`world.services.tick`) loops `for transition in weeks:`. Each
  `WeekTransition` is written once ever when a week opens (`schedule/README.md`),
  which is the exactly-once guarantee for everything in that loop. `week.number`
  runs 1–12 within a season.
- **Growth** (`riders.services.apply_weekly_growth`) moves every
  `Rider.objects.active()` rider along their age curve toward `potential`, and
  `record_initial_snapshots` writes a rider's baseline attribute history. Both
  already cover any rider, team or not.

Repo rules this is bound by (`AGENTS.md`): `riders -> core, teams`.
`transfers -> riders`. `teams -> core, accounts, riders`. `world` and `api` may
import anything, and nothing imports them. **`riders/` may not import
`schedule/`, `economy/` or `world/`.** Game time comes from
`world.services.now()`, never `timezone.now()`.

## Goal

1. At the opening of weeks 4, 8 and 12 of every season, every open development
   squad gains two new riders aged 17–19. Their hidden potential is drawn from
   bands whose odds improve with squad level, and their current ability sits
   well below it.
2. A squad rider belongs to no senior roster. It draws no wage, gets no trainer
   focus, doesn't count toward the roster cap, can't race, can't be listed or
   released, and isn't a free agent. It ages and grows like any rider.
3. Closing a squad, by the manager or through `claim_team`, releases its riders
   into the free-agent pool with the pool's expiry clock started.
4. The Development squad screen lists the squad's riders (latest batch marked
   new), says how often riders arrive and that a higher level improves the odds,
   and says when the next intake is due. A squad rider's profile page says which
   team's squad they are in.

## Design decisions (settled — implement these, do not substitute)

1. **A squad rider has `team = NULL` and a new `development_squad` FK set.**
   *Load-bearing.* Every roster-shaped query already filters on `team` (see
   *Context*), so with `team` null a squad rider falls out of wages, training,
   the roster cap, auctions, releases, race squads and the roster screen **with
   no change to any of that code**. The only thing `team = NULL` pulls them into
   is the free-agent pool, which has exactly two entry points (`free_agents()`
   and `sign_free_agent`). *Do not* do the obvious thing: keep `team` set and
   add an `in_development_squad` flag. That inverts the surface. Seven-plus
   roster queries would each need an exclusion, and the first one forgotten
   pays a youth rider's wage or lets them race.

2. **The FK points at `DevelopmentSquad`, not at `Team`.** A rider pointing at
   a team whose squad is closed would be a state with no meaning. Pointing at the
   squad row makes "in a squad that exists" structural. `on_delete=SET_NULL` is
   a **backstop only**: `close_squad` releases riders explicitly *before*
   deleting (D6), because SET_NULL cannot stamp `unattached_since`. *Not*
   `PROTECT`, which turns a cascade from a test or admin team delete into an
   error. *Not* `CASCADE`, which deletes riders.

3. **Two database invariants, as `CheckConstraint`s on `Rider`**:
   - `rider_not_on_roster_and_in_squad`: `team IS NULL OR development_squad IS NULL`;
   - `retired_rider_not_in_squad`: `retired_at IS NULL OR development_squad IS NULL`.

   They are cheap, and they turn the likeliest future bug into an
   `IntegrityError`. That bug is #34's promotion setting `team` and forgetting to
   clear the squad.

4. **`intake_at` (`DateTimeField`, null) records when a rider arrived through
   intake, and is never cleared.** It is the arrival week the screen shows,
   resolved through `schedule.services.current_position` in `api/`, the same
   way `retired_payload` resolves `retired_at`. It also marks the latest batch
   (D10) and is the idempotency key for a batch (D7). *Not* a `ForeignKey` to
   `schedule.Week`. A datetime needs no new cross-app reference and resolves the
   same way, because `intake_at` is exactly a `week.starts_at`.

5. **Cadence and batch size are constants in `riders/youth_intake.py`**:
   `INTAKE_INTERVAL_WEEKS = 4` and `INTAKE_BATCH_SIZE = 2`. The rule is
   `is_intake_week(week_number)`, which is `week_number % INTAKE_INTERVAL_WEEKS == 0`,
   giving weeks 4, 8 and 12. `riders/` receives a plain int week number and a
   datetime from `world/`, and never a `Week`. That is the same boundary
   `record_week_snapshots(week_id=...)` keeps. `world/` decides *when*, and
   `riders/` decides *what*.

6. **`close_squad(team, *, at)` releases its riders, then deletes.**
   *Load-bearing.* Each rider gets `unattached_since = at` (via the existing
   `mark_team_change(..., team_now=None, at=at)`), then `development_squad = NULL`,
   then the squad row is deleted, all under the existing team lock. Skip the
   stamp and the rider enters the pool with a null `unattached_since`, which
   `_expire_free_agents` excludes forever ("never treated as unattached since
   the beginning of time"). An unwanted 17-year-old would then sit in the market
   permanently. `at` becomes a required keyword: `claim_team` passes its own
   `at`, and `CloseDevelopmentSquadView` passes `now()`.

7. **Intake runs once per crossed intake week in the tick, locks each team, and
   is idempotent per `(squad, intake_at)`.** The `WeekTransition` row is the
   real exactly-once guarantee. The `exists()` check on
   `(development_squad, intake_at)` is the second line of defence, the same role
   the `(team, week)` constraints play for wages. The team lock matters because
   a manager can close the squad *during* the tick. Without it, intake can
   insert riders pointing at a squad `close_squad` is deleting, and SET_NULL then
   leaves them in the pool with no stamp (D6's failure, by another route). The
   squad is re-read **by team** under the lock, not by the pk listed earlier, so
   a squad closed and reopened between the listing and the lock still gets its
   batch. The code is given in full under `riders/youth_intake.py`.

8. **Intake runs after the week's growth, training and charges, inside the week
   loop.** A rider arriving at week 4 first grows at week 5's boundary.
   Otherwise their baseline snapshot and a first growth tick would land at the
   same instant, and the attribute history would open with a jump that never
   happened. Wages would be unaffected either way (D1), but the order is fixed.

9. **Every open squad gets intake, managed or not.** A team released to the pool
   keeps its squad and keeps paying for it (#32, and `tick()`'s own comment on
   `squad_cost_by_team`), so it keeps receiving riders too. The next claim closes
   the squad and releases them into the market. The spec's *Out of scope* rules
   out unmanaged teams *opening* a squad (#45), and nothing here opens one.

10. **Youth generation rolls potential first, then current ability from it.**
    For a youth, "hopeless or promising" is a statement about **potential**, and
    the level has to bias exactly that. Generating from a quality and deriving
    potential with `_roll_potential` gives the level only an indirect handle on
    potential. The steps:
    - Pick a band from `POTENTIAL_BANDS` using the weights for the squad's
      level (table below), and draw `potential` uniformly within it.
    - Set `quality = round(potential * uniform(*YOUTH_QUALITY_FRACTION))` with
      `YOUTH_QUALITY_FRACTION = (0.25, 0.40)`, clamped to at least 1.
    - Draw age uniformly from `INTAKE_AGE_RANGE = (17, 19)`.
    - Call `generate_rider(quality=..., age=..., potential=..., rng=rng)`. The
      new `potential` argument is honoured as `max(potential, best_attribute)`,
      the existing young-rider rule that a rider cannot already exceed their own
      ceiling.

    | Band | Potential | Regional (1) | National (2) | Elite (3) |
    |---|---|---|---|---|
    | hopeless | 20–35 | 50 | 40 | 30 |
    | journeyman | 36–50 | 35 | 37 | 37 |
    | promising | 51–65 | 13 | 19 | 25 |
    | gem | 66–85 | 2 | 4 | 8 |

    Rows are weights, and each column sums to 100. Tests enforce three
    properties of the table:
    - the share of promising-or-better rises strictly with level;
    - the bottom two bands are a majority at every level ("most of every batch
      will not be worth developing");
    - every band has a non-zero weight at every level ("a Regional squad can
      still produce a gem").

    The numbers are tunable. Those three properties are not. For calibration: a
    typical starting-roster rider has quality 21–35 and potential around 40–50
    (`generation.QUALITY_SPREAD`). A "promising" youth ends above that, and a gem
    ends well above. At 17 even a gem starts at quality 16–34, "far below
    professional level" for all but the very top.

11. **The age floor drops from 18 to 17**, in the model validator and in
    **both** copied `_MIN_AGE` constants (`riders/pricing.py`,
    `transfers/pricing.py`). *Load-bearing for `riders/pricing.age_multiplier`.*
    With `_MIN_AGE = 18`, a 17-year-old's fraction is `(24-17)/(24-18) = 7/6`,
    so the penalty exceeds `_AGE_PENALTY_MAX`. One accepted side effect: the
    taper under 24 widens by a year, so riders aged 18–23 drift slightly in
    price at the next `reprice_all()` (season close). That is at most a few
    percent, within `SALARY_REVIEW_THRESHOLD`'s purpose.
    `transfers.pricing.career_horizon` is flat below 23, so its constant only
    changes for consistency.

12. **A squad rider's `weekly_salary` is still computed, and is never charged.**
    The field is `NOT NULL`, min 1. `generate_rider` prices every rider, and
    `reprice_all()` reprices every active rider. Neither needs to know about
    squads. Nothing charges it (D1). The screens hide it (D14). *Do not* set it
    to a sentinel.

13. **`free_agents()` and `sign_free_agent` are the only transfer changes.**
    `free_agents()` adds `development_squad__isnull=True`. `sign_free_agent`
    refuses a squad rider with `RiderNotAvailable`, checked under the rider lock
    beside the existing `team_id` check. `_expire_free_agents` reads
    `free_agents()`, so it is covered. `retire_riders` only receives ids from
    that pool.

14. **What the player sees.**
    - The squad endpoint gains `riders` (the squad's riders, strongest first) and
      `intake` (`{every_weeks, batch_size, next}`).
    - A squad rider's payload is identity, age, speciality and the five 0–10
      attributes, plus `arrived` (`{season, week}`) and `is_new`. There is **no**
      `weekly_salary`, `market_value`, `release_cost` or `final_season`. Salary
      would read as a cost the team pays, and value and release cost describe a
      market the rider isn't in.
    - The rider profile gains a `development_squad` key (the owning team's
      `{id, name, code}`, or null). The screen shows the rider as
      "<Team> · Development squad", and the salary tile reads "Paid by squad"
      instead of a number.
    - The squad screen's copy states the cadence from `intake` and that "a
      higher level improves the odds of a promising rider". It gives no
      percentage and makes no promise about a single batch (spec *In scope* 9).

15. **`is_new` means "arrived at the most recent intake week that has opened".**
    That week is the last `Week` with `starts_at <= now()` and
    `is_intake_week(number)`. A rider is new if `intake_at` equals that week's
    `starts_at`. After week 8's intake, week 4's riders stop being new, even
    though they're still in the squad. *Not* "arrived in the last N days",
    which is time-zone and tick-lateness sensitive.

16. **`retire_due_riders` also clears `development_squad`.** No squad rider can
    reach 33 in practice before #34 exists, but D3's constraint would otherwise
    turn that into a crashed season close. It is one extra key in the existing
    `update()`.

## Data model

### `riders.Rider` — `riders/models.py`

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `development_squad` | `ForeignKey("DevelopmentSquad", on_delete=SET_NULL, related_name="riders")` | null=True, blank=True | NULL | Set only while the rider is in a squad. `team` is NULL whenever this is set (D3). |
| `intake_at` | `DateTimeField` | null=True, blank=True | NULL | Game time the rider arrived through youth intake (a `week.starts_at`). Never cleared. NULL for every rider who didn't come through intake. |
| `age` | *(changed)* `MinValueValidator(17)` | — | — | Was 18. Validator-only, but Django still emits an `AlterField`. |

- `DevelopmentSquad` is declared *after* `Rider` in `models.py`, so reference
  it as the string `"DevelopmentSquad"`. It is the same app, so no import is
  involved.
- `team`'s `help_text` becomes: "Null means no senior team: a free agent, a
  retired rider, or a development squad rider (see development_squad)."
- `Meta.constraints` gains the two `CheckConstraint`s from D3, using `condition=`
  as the existing `retired_rider_has_no_team` does.
- Update the class docstring's paragraph on `team`/free agents to match.
- Migration: **`riders/migrations/0014_youth_intake.py`**, depending on
  `0013_developmentsquad`. It adds both fields, alters `age`, and adds both
  constraints. No data migration: every existing rider gets NULL for both
  fields, which is correct.

### `world.TickRun` — `world/models.py`

- `youth_intake_riders = PositiveIntegerField(default=0, help_text="Riders generated into development squads by youth intake this tick (#33).")`
- Migration: **`world/migrations/0019_tickrun_youth_intake_riders.py`**, depending on `0018_developmentsquadentries`.

Run `makemigrations riders world` and rename the files to the names above if
Django picks others.

## `riders/generation.py`

- `generate_rider(..., potential: int | None = None, ...)` is a new optional
  keyword. When given, it replaces `_roll_potential`:
  `potential = _clamp(max(potential, max(attributes.values())), _MIN_ATTRIBUTE, _MAX_ATTRIBUTE)`.
  When omitted, behaviour is unchanged. Every existing caller passes nothing.
- Nothing else changes. `_AGE_RANGE` stays `(18, 36)`: senior generation does
  not produce 17-year-olds.

## `riders/pricing.py` and `transfers/pricing.py`

- `_MIN_AGE = 17` in both, with each comment updated (it says "(18, 40)").
- `riders/tests/test_pricing.py`: the two tests that build `age=18` as "the edge"
  (lines ~66 and ~76) move to `age=17`.
- `transfers/tests/test_pricing.py`: `career_horizon(18) == career_horizon(23)`
  gains `career_horizon(17)`, and the `range(18, 41)` loop becomes `range(17, 41)`.

## `riders/youth_intake.py` (new)

```python
INTAKE_INTERVAL_WEEKS = 4
INTAKE_BATCH_SIZE = 2
INTAKE_AGE_RANGE = (17, 19)
YOUTH_QUALITY_FRACTION = (0.25, 0.40)

#: (low, high) potential per band, lowest band first. See D10.
POTENTIAL_BANDS: tuple[tuple[int, int], ...] = ((20, 35), (36, 50), (51, 65), (66, 85))
#: Band weights per DevelopmentSquad level, same order as POTENTIAL_BANDS.
BAND_WEIGHTS: dict[int, tuple[int, ...]] = {1: (50, 35, 13, 2), 2: (40, 37, 19, 4), 3: (30, 37, 25, 8)}

def is_intake_week(week_number: int) -> bool
def generate_youth_rider(level: int, *, rng: random.Random) -> Rider   # unsaved
def run_intake(*, at, rng: random.Random | None = None) -> int          # riders created
```

`BAND_WEIGHTS` is keyed by the same integers as `development_squad.LEVELS`. A
test asserts the two key sets are equal, so adding a fourth level cannot
silently skip intake.

The load-bearing function, in full:

```python
def run_intake(*, at, rng=None) -> int:
    """Give every open development squad one batch of youth riders, dated `at`
    (the intake week's starts_at). world/ decides which weeks; this decides who."""
    rng = rng or random.Random()
    created_total = 0
    for team_id in list(DevelopmentSquad.objects.values_list("team_id", flat=True)):
        with transaction.atomic():
            # D7: the same lock close_squad takes, so a close cannot delete the
            # squad between our read and our insert.
            team = Team.objects.select_for_update().get(pk=team_id)
            squad = squad_for(team)                 # re-read BY TEAM under the lock
            if squad is None:
                continue                            # closed since we listed it
            if Rider.objects.filter(development_squad=squad, intake_at=at).exists():
                continue                            # second line of defence
            batch = [generate_youth_rider(squad.level, rng=rng) for _ in range(INTAKE_BATCH_SIZE)]
            for rider in batch:
                rider.development_squad = squad
                rider.intake_at = at
            created = Rider.objects.bulk_create(batch)
            record_initial_snapshots(created)       # baseline for the attribute history
            created_total += len(created)
    return created_total
```

Imports: `squad_for` from `.development_squad`, `record_initial_snapshots` from
`.services`, and `generate_rider` from `.generation`. None of those import
`youth_intake`, so there is no cycle. Leave `team`, `joined_team_at` and
`unattached_since` NULL on a new squad rider. It has never been on a roster or
in the pool.

## `riders/development_squad.py`

`close_squad(team, *, at) -> bool`. Replace the body:

```python
with transaction.atomic():
    _lock_team(team)
    squad = squad_for(team)
    if squad is None:
        return False
    riders = list(Rider.objects.filter(development_squad=squad))
    # D6: stamp BEFORE clearing — this is what starts the pool's expiry clock.
    mark_team_change(riders, team_now=None, at=at)
    Rider.objects.filter(pk__in=[r.pk for r in riders]).update(development_squad=None)
    squad.delete()
return True
```

Add `from .services import mark_team_change` and `Rider` to the model import.
Update the module docstring and `close_squad`'s docstring: closing now releases
the squad's riders as free agents.

## `riders/services.py`

`retire_due_riders`: `.update(team=None, development_squad=None, retired_at=at)` (D16).

## `teams/services.py`

`claim_team`: `close_squad(team, at=at)`. Nothing else changes. The comment
above it gains one sentence: the squad's riders go to the free-agent pool.

## `transfers/services.py`

- `free_agents()`: `Rider.objects.active().filter(team__isnull=True, development_squad__isnull=True)`.
  Update the docstring ("…and development squad riders are never in it").
- `sign_free_agent`: after the `team_id` check, under the lock:
  `if rider.development_squad_id is not None: raise RiderNotAvailable("That rider is not available.")`.

## `world/services.py` and `world/models.py`

Import `is_intake_week` and `run_intake` from `riders.youth_intake`. Initialise
`youth_intake_riders = 0` with the other counters. Inside
`for transition in weeks:`, **directly after** `charge_development_squad_costs(...)`:

```python
if is_intake_week(week.number):
    youth_intake_riders += run_intake(at=week.starts_at)
```

Pass `youth_intake_riders=youth_intake_riders` into `TickRun.objects.create(...)`.
`at=week.starts_at`, not `now()`. The batch is dated to the week it belongs to,
even when the tick runs late, which is what `is_new` (D15) and the idempotency
check (D7) both compare against.

## `api/`

**`api/views.py`: `DevelopmentSquadView.get`** adds two keys:

- `riders`: `Rider.objects.filter(development_squad=squad)` when a squad is
  open, else `[]`, sorted in Python by `riders.pricing.strength` descending.
- `intake`: `{"every_weeks": INTAKE_INTERVAL_WEEKS, "batch_size": INTAKE_BATCH_SIZE, "next": _next_intake(at)}`.

Two module-level helpers:

```python
def _next_intake(at) -> dict | None     # {"season", "week"} of the first Week with starts_at > at
                                        # and is_intake_week(number); None if none is declared
def _latest_intake_at(at) -> datetime | None   # starts_at of the last Week with starts_at <= at
                                               # and is_intake_week(number)
```

Both iterate `Week.objects.select_related("season").order_by("starts_at")`,
filtered on `starts_at`. There are at most a few dozen weeks, so a Python-side
`is_intake_week` filter is fine. Keep the rule in one place and do not
reimplement `% 4` in SQL. Resolve each rider's `arrived` through
`current_position(rider.intake_at)`, the same shape as `retired_payload` in
`api/rider_profile.py`. Pass `latest_intake_at` in the serializer context for
`is_new`.

**`api/serializers.py`**:

- `DevelopmentSquadRiderSerializer` (new): `id`, `name`, `speciality`
  (`get_speciality_display`), `nationality`, `age`, the five attributes through
  the existing `_display_scale_attributes`, `arrived` (`{season, week}`), and
  `is_new` (bool). **No salary, value, release cost or final_season** (D14). Not
  a `RiderSerializer` subclass: that would inherit all four.
- `DevelopmentSquadIntakeSerializer` (new): `every_weeks`, `batch_size`,
  `next` (nullable `{season, week}`).
- `DevelopmentSquadSerializer` gains `riders` (many) and `intake`.

**`api/rider_profile.py`**: `rider_profile` adds
`"development_squad": _team_payload(rider.development_squad.team) if rider.development_squad_id else None`.
The view's queryset becomes `select_related("team", "development_squad__team")`.
`RiderProfileSerializer` gains `development_squad = SerializerMethodField()`,
the same shape as `get_team`.

**`api/views.py`: `CloseDevelopmentSquadView`** calls `close_squad(team, at=now())`.

## `frontend/`

- **`src/api.ts`**: add `DevelopmentSquadRider`
  (`id, name, speciality, nationality, age, climb, sprint, flat, resistance, positioning, arrived: {season: number | null, week: number | null}, is_new: boolean`),
  and `DevelopmentSquadIntake` (`every_weeks, batch_size, next: {season, week} | null`).
  `DevelopmentSquad` gains `riders` and `intake`. `RiderProfile` gains
  `development_squad: RaceResultTeam | null`.
- **`src/screens/DevelopmentSquad.tsx`**:
  - **Subtitle.** Replace both subtitles and the comment above them. Closed:
    "Closed. A squad starts at Regional, and each level above costs more to
    reach and to run." (unchanged). Open: "Running at {name}. {batch_size} young
    riders arrive every {every_weeks} weeks; a higher level improves the odds of
    a promising one."
  - **Intake card**, directly under the heading and only while open: "Next
    intake: Season {s}, Week {w}", or "No intake scheduled" when `next` is null.
  - **Riders card**, below the level cards and only while open. It has a header
    and one row per rider:
    - name, linking to `riderPath(id)`;
    - age and speciality;
    - the five 0–10 attributes, using the same short labels
      (`CLM SPR FLT RES POS`) and cell treatment as `Roster.tsx`;
    - "Arrived S{season} W{week}";
    - a small `NEW` badge when `is_new`, styled like the existing `CURRENT`
      badge.

    Empty state: "No riders yet — the first intake arrives Season {s}, Week {w}."
  - While closed, show no riders card and no intake card. A closed squad has
    no riders (D6).
- **`src/screens/DevelopmentSquad.test.tsx`**: **replace**
  `promises no riders while %s — only what is actually charged`. It pinned
  #32's rule that the screen may not mention riders, and that rule is now
  obsolete by design. The replacement,
  `describes intake without promising an outcome`, asserts:
  - the open subtitle names the cadence from the payload;
  - `document.body.textContent` does not match `/guarantee/i` or `/\d+\s*%/`;
  - the closed state still contains no `/soon/i`.

  Add these tests:
  - `lists squad riders with arrival and a NEW badge on the latest batch`
  - `shows the next intake week, and the empty state when no riders have arrived`
  - `shows no riders or intake card while closed`

  Every fixture now needs `riders` and `intake` keys. Update the shared payload
  builders at the top of the file.
- **`src/screens/RiderProfile.tsx`**:
  - `affiliation()` checks `profile.development_squad` first and returns
    `` `${profile.development_squad.name} · Development squad` ``.
  - The weekly salary `StatTile` shows `value="Paid by squad"` and no `/wk`
    suffix when `profile.development_squad` is set.
  - Add a test to `RiderProfile.test.tsx`:
    `shows a development squad rider's squad and no salary figure`.

Styling follows `frontend/README.md`, *Conventions*: inline styles and colours
from `theme.ts`. There is no money on the riders card.

## Work items

### W1 — `riders/`: model fields, constraints, age floor, migration; pricing floors — done
- **What changes:**
  - Add `development_squad`, `intake_at`, the `age` validator, both constraints
    and `0014_youth_intake.py`.
  - Set `_MIN_AGE = 17` in `riders/pricing.py` and `transfers/pricing.py`, and
    update their tests (see those sections).
- **Tests** in `riders/tests/test_models.py`:
  - `test_rider_cannot_be_on_roster_and_in_squad` (`IntegrityError`)
  - `test_retired_rider_cannot_be_in_squad` (`IntegrityError`)
  - `test_age_17_is_valid` (`full_clean()` passes)
  - `test_squad_delete_nulls_rider_link` (the SET_NULL backstop)
- **Test** in `riders/tests/test_pricing.py`: `test_age_multiplier_at_17_is_max_penalty`,
  which asserts it equals `1 - _AGE_PENALTY_MAX` exactly, not more.

### W2 — `riders/generation.py` + `riders/youth_intake.py`: youth generation — done
- **What changes:** the `potential=` argument on `generate_rider`. Add the new
  module's constants, `is_intake_week` and `generate_youth_rider`. `run_intake`
  is not in this item.
- **Tests** in `riders/tests/test_youth_intake.py` (**new**):
  - `test_intake_weeks_are_4_8_12`
  - `test_band_weights_cover_every_level`, whose keys equal `LEVELS`' keys
  - `test_promising_share_rises_strictly_with_level`, from the table itself,
    not from sampling
  - `test_bottom_two_bands_are_a_majority_at_every_level`
  - `test_every_band_possible_at_every_level`
  - `test_youth_age_is_17_to_19`
  - `test_youth_potential_at_least_best_attribute`
  - `test_youth_far_below_pro_level_on_average`: with seeded
    `random.Random(0)`, 500 youths per level have a mean `strength()` below the
    mean of 500 `generate_rider()` riders
  - `test_elite_mean_potential_above_regional`: seeded, 2,000 each
- **Test** in `riders/tests/test_generation.py`:
  `test_potential_override_respected_and_floored_at_best_attribute`.

### W3 — `riders/`: `run_intake`, `close_squad` releases riders, retirement clears squad; `teams/` and the close view pass `at` — done
- **What changes:**
  - `run_intake` as given.
  - `close_squad(team, *, at)`.
  - `retire_due_riders`.
  - Update both existing callers of `close_squad`: `teams/services.py` and
    `api/views.py`'s `CloseDevelopmentSquadView`. The signature change breaks
    them otherwise, so they land in the same commit.
- **Tests** in `riders/tests/test_youth_intake.py`:
  - `test_run_intake_adds_batch_to_every_open_squad`
  - `test_run_intake_riders_have_no_team_and_carry_intake_at`
  - `test_run_intake_skips_team_without_squad`
  - `test_run_intake_twice_same_at_is_idempotent`
  - `test_run_intake_writes_baseline_snapshots`
- **Tests** in `riders/tests/test_development_squad.py`:
  - `test_close_releases_squad_riders_to_pool_with_unattached_since`, which
    asserts `unattached_since == at`. **This is the test that catches D6.**
  - `test_close_with_no_riders_still_closes`

  Also update every existing `close_squad(team)` call in that file to pass `at=`.
- **Test** in `riders/tests/test_services.py`: `test_retire_due_riders_clears_development_squad`.
- **Test** in `teams/tests/test_services.py` beside the claim tests:
  `test_claim_releases_squad_riders_as_free_agents`.

### W4 — `transfers/services.py`: squad riders are not free agents — done
- **Tests** in `transfers/tests/test_services.py`:
  - `test_free_agents_excludes_squad_riders`
  - `test_sign_squad_rider_raises_not_available`
  - `test_released_squad_rider_is_signable`: after `close_squad`, sign succeeds.

### W5 — `world/`: intake in the tick, and the exclusions proved end to end — done
- **What changes:** the tick call, `TickRun.youth_intake_riders` and its
  migration.
- **Tests** in `world/tests/test_tick.py`, beside the development squad cost
  tests (grep `development_squad_entries`):
  - `test_tick_into_week_4_gives_open_squad_two_riders`, with the
    `TickRun.youth_intake_riders == 2` check
  - `test_tick_into_week_5_gives_nothing`
  - `test_catch_up_across_weeks_3_to_9_gives_two_batches_dated_to_their_weeks`
  - `test_tick_twice_does_not_duplicate_batch`
  - `test_released_team_with_squad_still_receives_intake` (D9)
  - `test_squad_riders_draw_no_wages`: the wage row for the team equals the
    roster's salaries only
  - `test_squad_riders_get_no_trainer_focus_but_still_grow`: a trainer with a
    focus is hired, and after a tick the squad rider's `growth_debt` or
    attributes moved by growth alone, with no training delta applied
  - `test_new_arrivals_first_grow_the_following_week` (D8)

### W6 — `api/`: squad riders and intake on the squad endpoint; profile shows the squad — done
- **Tests** in `api/tests.py`, beside `test_development_squad_closed_payload`:
  - `test_development_squad_payload_lists_riders_without_salary_or_value`,
    asserting those keys are **absent**
  - `test_development_squad_marks_only_latest_batch_new`
  - `test_development_squad_intake_next_week`, which is null after the season's
    last intake week
  - `test_development_squad_closed_has_no_riders`
  - `test_close_endpoint_releases_riders_to_free_agent_list`, the close POST
    followed by a GET of free agents
  - `test_rider_profile_shows_development_squad_team`
  - `test_squad_rider_cannot_be_listed_released_or_raced`: the list-for-auction
    and release endpoints return their existing not-on-roster error, and
    `racing.services.set_squad` with a squad rider raises `SquadError`. These
    already hold by D1, and the test pins it.

### W7 — `frontend/`: squad screen riders and intake, rider profile — done
- **Tests:** as listed in the `frontend/` section. Then run
  `npm --prefix frontend test` and `npm --prefix frontend run build`.

### W8 — Documentation — done
See *Documentation update*. Archive the spec and plan per `AGENTS.md`,
*Closing a ticket*.

## Execution order

1. **W1** is schema only. Every later item needs the fields, and the
   constraints are in force from the start, so any later code that breaks an
   invariant fails loudly.
2. **W2** proves the distribution in isolation, with no database side effects
   beyond reads.
3. **W3** is the domain operations, including the close/release path, which is
   the one where a missed stamp silently strands riders. It lands with its
   callers so the repo stays green.
4. **W4** closes the one hole D1 opens: the free-agent pool.
5. **W5** is the tick. It needs W2 and W3. The exclusion tests live here
   because this is where wages and training actually run.
6. **W6**, then **W7**, then **W8**.

Commit after each item. Run the full suite (`/home/mario/dev/cycling-manager/.venv/bin/python -m pytest`)
before each commit.

## Documentation update (required, not optional)

- **`riders/README.md`**:
  - Add a new **Youth intake** section covering:
    - the `team = NULL` + `development_squad` representation, and why (D1);
    - the two constraints;
    - `intake_at`;
    - cadence and batch constants;
    - potential-first generation and the band table with its three enforced
      properties;
    - the team lock and idempotency in `run_intake`;
    - that squad riders grow but draw no wage and get no trainer focus.
  - In *Development squad*, replace the paragraph starting "**#33 will generate
    youth riders into the squad. Nothing populates it yet**" with a pointer to
    *Youth intake*. The corollary that no screen may promise riders the code
    doesn't produce becomes: the screen describes the cadence and that level
    improves odds, never a percentage or a per-batch promise.
  - Add that closing releases riders with `unattached_since` stamped.
  - In *Generation*, document the `potential=` argument.
  - In *What this app owns*, add `youth_intake.py`.
  - In *Visible vs hidden*, add `intake_at` and `development_squad` to the
    visible list (both reach the player only as their consequence).
- **`transfers/README.md`**: in *Free agents*, add that development squad
  riders are never in the pool and cannot be signed, and that a closed squad's
  riders enter it stamped. Note the `_MIN_AGE` change in the pricing section.
- **`world/README.md`**: in *How a tick works*, add the intake step to the
  per-week list, after the development squad cost. Add `youth_intake_riders` to
  the `TickRun` description.
- **`teams/README.md`**: in *Claiming a team*, the "closes the development
  squad" step now also releases its riders to the free-agent pool.
- **`economy/README.md`**: one line in the wages section. Squad riders have no
  `team`, so they are not in the wage sum, and the squad's weekly cost is what
  pays for them.
- **`api/README.md`**: the squad endpoint's new `riders` and `intake` keys, and
  the rider profile's `development_squad` key.
- **`frontend/README.md`**: the Development squad screen now lists riders and
  the next intake. The rider profile shows squad membership.
- **`AGENTS.md`**:
  - `riders/` row: replace "It generates no youth riders yet (#33)" with youth
    intake: two riders every four weeks per open squad, potential odds by level,
    squad riders held with `team = NULL`, and released to free agents on close.
  - `transfers/` row: "development squad riders are not free agents".
  - `world/` row: add youth intake to the tick's list.
- **`specs/roadmap.md`**: mark #33 ✅. #34 is next.
- Spec and plan: `Status: implemented`, moved to `specs/archive/`.

## Verification

```bash
cd /home/mario/dev/cycling-manager/.claude/worktrees/youth-intake
/home/mario/dev/cycling-manager/.venv/bin/python scripts/dev_db.py
/home/mario/dev/cycling-manager/.venv/bin/python manage.py migrate
/home/mario/dev/cycling-manager/.venv/bin/python manage.py seed_user
/home/mario/dev/cycling-manager/.venv/bin/python manage.py seed_teams --claim-for test@mail.com
/home/mario/dev/cycling-manager/.venv/bin/python manage.py seed_trainers
/home/mario/dev/cycling-manager/.venv/bin/python manage.py load_season seasons/season-1.example.json
export GAME_CLOCK_CLASS=world.clocks.MockClock
/home/mario/dev/cycling-manager/.venv/bin/python manage.py mock_clock set 2027-03-01T01:00
/home/mario/dev/cycling-manager/.venv/bin/python manage.py tick
/home/mario/dev/cycling-manager/.venv/bin/python manage.py runserver 8392
```

1. Log in as the demo account, open **Development squad**, and open it at
   Regional. The subtitle states the cadence, and the intake card reads
   "Next intake: Season 1, Week 4". The riders card shows the empty state.
2. Run `mock_clock advance --by 21d` and then `tick`, which enters week 4.
   Reload the screen: two riders, both `NEW`, "Arrived S1 W4", aged 17–19.
   The tick's output shows `youth_intake_riders = 2`.
3. **The likeliest failure is a squad rider leaking into a roster-shaped
   query.** Check each of these:
   - the **Roster** screen does not list either rider;
   - **Finances** shows no wage change attributable to them. Compare the week-4
     wage line with week 3's.
   - the **Transfers** free-agent list does not show them;
   - opening one rider's profile shows "<Team> · Development squad" and
     "Paid by squad".
4. Run `mock_clock advance --by 28d` and then `tick`, which enters week 8. Four
   riders are listed, and only the week-8 pair is `NEW`.
5. **The second likeliest failure is close without the stamp.** Close the
   squad, then open **Transfers**: all four riders are free agents. In
   `manage.py shell`, confirm each has `unattached_since` set and
   `development_squad_id is None`. A null `unattached_since` here means they
   will never expire. That is the bug D6 exists to prevent.
6. Reopen at Regional and tick past week 12. One more batch arrives. Tick into
   the next season's week 1–3: nothing arrives.

## Risks

| Risk | Mitigation |
|---|---|
| Keeping `team` set on squad riders and adding a flag, leaving seven roster queries to each remember an exclusion. | D1 names the rejected alternative. W5 and W6 pin the exclusions (wages, training, roster, auction, release, race squad) against the real code paths. |
| `close_squad` deletes without stamping `unattached_since`, stranding released youths in the pool forever (SET_NULL does the unlinking silently, so nothing crashes). | D6 and the code given in full. `test_close_releases_squad_riders_to_pool_with_unattached_since`. Verification step 5. |
| A manager closes the squad mid-tick while intake inserts riders pointing at the row being deleted. | D7's team lock in `run_intake`, the same lock `close_squad` takes, with the squad re-read by team under it. |
| `_MIN_AGE` left at 18 in `riders/pricing.py`, so a 17-year-old gets a larger salary discount than the model allows. | D11. `test_age_multiplier_at_17_is_max_penalty`. |
| Intake dated `now()` instead of `week.starts_at`, so a late tick's batch is never `NEW` and the idempotency check misses it. | The `world/` section says so explicitly. `test_catch_up_across_weeks_3_to_9_gives_two_batches_dated_to_their_weeks`. |
| The squad-screen test from #32 that forbids the word "rider" gets "fixed" by weakening it rather than replaced with the new rule. | The `frontend/` section names the test, why it goes, and what replaces it. |
| Serializing a squad rider through `RiderSerializer` and shipping salary, value and release cost. | D14. A dedicated serializer. `test_development_squad_payload_lists_riders_without_salary_or_value` asserts the keys are absent. |
| Youth riders generated as good as pros, which defeats "far below professional level". | D10's `YOUTH_QUALITY_FRACTION`. `test_youth_far_below_pro_level_on_average`. |
| #34 later promotes by setting `team` and forgets `development_squad`. | D3's constraint makes it an `IntegrityError` rather than a rider in two places. |

## Open questions

None. The spec's one open question (a squad cap before #34) does not block
this plan: no cap is built, per the spec.

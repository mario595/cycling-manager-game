# Retire raced riders instead of deleting them — Implementation Plan

**Spec:** `specs/retire-raced-riders.md` · **Issue:** #104 · **Status:** proposed
**Apps touched:** `riders/`, `transfers/`, `world/`, `api/`, `frontend/`

## Context you need

**Free agents today.** A free agent is any `Rider` with `team=None`
(`transfers/README.md`, *Free agents*). The pool is
`transfers.services.free_agents()`. Once per in-season week boundary,
`world.services._expire_free_agents(week)` (`world/services.py`, called at
the end of the `for transition in weeks:` loop in `tick()`) selects every
free agent who has been unattached for `EXPIRY_WEEKS` (8) in-season weeks
**and** is priced at or below the pool's bottom `EXPIRY_VALUE_PERCENTILE`
(0.20), then runs `Rider.objects.filter(pk__in=doomed).delete()`.

**What that delete destroys.** `RaceResult.rider`, `RaceSquadRider.rider`,
`RiderAttributeSnapshot.rider` and `transfers.Auction.rider` are all
`on_delete=CASCADE`. A rider who raced, was released and went unsigned
loses every result row they ever earned, and that race's result table loses
a row after the fact. Standings (`competitions.RacePoints`) and prize money
(`economy.LedgerEntry`) are frozen per team when a race is scored, so they
do **not** move. The damage is the race's own result table and the rider
page (#96, `GET /api/riders/<id>/`, `api/rider_profile.py`), which 404s and
shows "This rider is no longer part of the game."
(`frontend/src/screens/RiderProfile.tsx`).

**Everything that touches every rider every week.** These all iterate
`Rider.objects.all()` (or `.exclude(...)`) today and must stop touching a
retired rider:

| Where | What it does |
|---|---|
| `riders.services.apply_weekly_growth` | age curve + training deltas → attributes, `growth_debt` |
| `riders.services.apply_weekly_recovery` | freshness recovery |
| `riders.services.advance_ages` | +1 age at season close |
| `riders.services.reprice_all` | `weekly_salary` at season close |
| `world.services._apply_training_week` | builds the race-effect deltas for riders without a trainer |

`charge_weekly_wages` sums riders **per team**, so a teamless retired rider
already costs nobody anything. `racing.services.set_squad` only accepts
riders with `team=team`. `list_for_auction` and `release_rider` both require
the rider to be on the caller's team. So the retired rider's teamlessness
already fences them out of wages, squads, auctions and releases. The
only other ways back in are the free-agent pool and `sign_free_agent`.

**Repo rules this work is bound by.**
- `transfers -> riders` only. `riders -> core, teams`. `world` and `api` may
  import anything. `racing.RaceResult` may be read by `world/` and `api/`,
  **not** by `riders/` or `transfers/` (`AGENTS.md`, *Dependency direction*).
- `world/` owns week counting and time. `riders/` never reads the clock:
  functions take `at` from their caller.
- Tests are pytest (`/home/mario/dev/cycling-manager/.venv/bin/python -m pytest`). CI has an 85% coverage floor.

## Goal

1. On expiry, a selected free agent with **at least one `RaceResult`** gets
   `retired_at` stamped and stays in the database with every related row
   intact. A selected free agent with **no** `RaceResult` is deleted exactly
   as today.
2. A retired rider is never in the free-agent pool, can never be signed,
   and is never counted in the expiry percentile again.
3. A retired rider's attributes, `growth_debt`, freshness, age and salary
   never change after retirement.
4. `GET /api/riders/<id>/` returns a retired rider normally, plus a
   `retired: {season, week}` object. The rider page shows "Retired" with
   that season and week in place of the team.
5. `TickRun` reports retired and deleted counts separately.

## Design decisions (settled — implement these, do not substitute)

1. **Retirement is a nullable timestamp, `Rider.retired_at`, not a status
   enum or a boolean.** Null means active. It is game time, taken from the
   caller the same way `unattached_since` is. A timestamp answers "when" for
   the rider page, and it is also what #42 (age-based retirement at season
   close) will stamp. A boolean can't give the date, and an enum with one
   non-default value just adds ceremony. **Do not** add a `Week` foreign key
   (`retired_in_week`). #42 will retire riders at a season *close*, which is
   not a week, and a DateTimeField keeps `riders/` free of a new `schedule/`
   edge. `api/` turns the timestamp into season and week (D7).

2. **A database check constraint enforces that a retired rider has no
   team:** `Q(retired_at__isnull=True) | Q(team__isnull=True)`, named
   `retired_rider_has_no_team`. The service checks (D5) give the friendly
   error. The constraint makes a missed code path fail loudly instead of
   silently putting a retired rider on a roster. **Load-bearing.**

3. **One definition of "active": `Rider.objects.active()`**, a
   `RiderQuerySet` method (`retired_at__isnull=True`), installed with
   `objects = RiderQuerySet.as_manager()`. Every call site in the
   *Context* table switches to it. Seven sites need the same filter, and
   forgetting one silently changes a retired rider, which is the defect this
   ticket exists to prevent.
   **Do not make the default manager hide retired riders.** It is the
   tempting shortcut, but `get_object_or_404(Rider, …)` on the profile would
   404 exactly the riders this ticket keeps. Admin would also lose them, and
   the reverse relations (`race.results.all()` → `rider`) would behave
   differently depending on which manager Django picks.

4. **"Has raced" means at least one `RaceResult` row, of any status.** A DNF
   has a row, so it counts. A squad membership with no result doesn't count
   (spec, *Rules and edge cases*). `world/` decides this because it is the
   only app on the expiry path allowed to read `racing/`. `riders/` gets a
   plain list of ids to retire.

5. **Race safety between expiry and a concurrent signing comes from the
   `WHERE` clause and the row lock, not from a new lock.**
   `riders.services.retire_riders` is a single
   `UPDATE … WHERE pk IN (…) AND team_id IS NULL AND retired_at IS NULL`.
   `sign_free_agent` already holds `select_for_update()` on the rider row
   and re-checks `team_id` after the lock. Add a `retired_at` re-check right
   beside it. Under Postgres READ COMMITTED:
   - if the signing commits first, the UPDATE blocks on the row lock,
     re-evaluates `team_id IS NULL` against the new row, gets false, and
     skips that rider;
   - if the retirement commits first, the signing's locked read sees
     `retired_at` set and raises `RiderNotAvailable`.
   The same `team__isnull=True` filter goes on the delete for never-raced
   riders. That narrows a race that already exists but doesn't close it
   (see *Risks*).

6. **The pool excludes retired riders in exactly one place,
   `transfers.services.free_agents()`, and expiry reads the pool through
   it.** `_expire_free_agents` currently builds its pool with its own
   `Rider.objects.filter(team__isnull=True)`. Replace that with
   `list(free_agents())`. Otherwise retired riders would stay in the pool
   the percentile is computed from. They are by definition bottom-quintile
   and unattached forever, so they would pin the cutoff low and slowly stop
   active riders from ever expiring. **Load-bearing.**

7. **`api/` derives `{season, week}` from `retired_at` with
   `schedule.services.current_position(rider.retired_at)`.** Expiry stamps
   `week.starts_at`, and `current_position` at a week's `starts_at` returns
   that same week (`starts_at__lte=at, ends_at__gt=at`). If the position
   isn't `in_season` (not reachable today; possible once #42 retires riders
   at a season close), return `{"season": position.season.number, "week":
   null}`, or `{"season": null, "week": null}` for `no_season`. Never 500.

8. **`TickRun.agents_expired` keeps its meaning of "free agents removed
   from the database this tick". A new `TickRun.agents_retired` counts
   retirements.** Two counters, not one total, so the tick log shows which
   branch fired. Only the help text of `agents_expired` changes. Both count
   riders (`len(ids)` / the UPDATE's rowcount), never
   `delete()`'s cascaded-row tuple (the existing
   `test_expiry_counts_riders_deleted_not_cascaded_rows` rule).

9. **A frozen rider's page still shows market value, salary and freshness**,
   computed exactly as for anyone else. They are frozen because their
   inputs are frozen, not because of special-casing. **Do not** hide tiles
   for retired riders. The spec settled on one page layout for everyone.
   The attribute-history chart draws flat from retirement to the current
   week, which is true: nothing moved.

10. **No data migration.** Existing riders get `retired_at = NULL` (active).
    Riders deleted before this ships stay gone (spec, *Out of scope*).

## Data model

### `riders.Rider` — one new field, one constraint, a queryset

| Field | Type | null/blank | Default | Index | Notes |
|---|---|---|---|---|---|
| `retired_at` | `DateTimeField` | `null=True, blank=True` | `None` | no | Game time the rider left the game for good. Null = active. Only ever set on a rider with `team=None` (D2). Never cleared. |

No index: the filter runs over a table of a few thousand rows, alongside
full-table loops that already exist.

```python
class RiderQuerySet(models.QuerySet):
    def active(self):
        """Riders still in the game — everyone except the retired. See
        riders/README.md, *Retirement*."""
        return self.filter(retired_at__isnull=True)


class Rider(TimeStampedModel):
    ...
    objects = RiderQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(retired_at__isnull=True) | models.Q(team__isnull=True),
                name="retired_rider_has_no_team",
            ),
        ]
```

The repo runs Django 6.1, so the keyword is `condition=`. `check=` was
removed in 6.0 and fails at import. Nothing in this repo uses
`CheckConstraint` yet, so there is no local precedent to copy.

Migration: **`riders/migrations/0012_rider_retired_at.py`** (new),
generated by `makemigrations riders`. It depends on
`0011_merge_20260924_1020`. Its operations are `AddField` and
`AddConstraint`. The constraint holds on existing data trivially (every
`retired_at` is null).

### `world.TickRun` — one new counter

| Field | Type | Default | Notes |
|---|---|---|---|
| `agents_retired` | `PositiveSmallIntegerField` | `0` | Free agents retired this tick: selected by expiry, with at least one race result. |

Update `agents_expired`'s `help_text` to: "Free agents deleted this tick:
selected by expiry (unattached EXPIRY_WEEKS+ in-season weeks, priced in the
pool's bottom EXPIRY_VALUE_PERCENTILE) and never raced (#29, #104)."

Migration: **`world/migrations/0015_tickrun_agents_retired.py`** (new). It
also carries the `AlterField` for the help text, because `makemigrations`
emits it.

## `riders/models.py`

`RiderQuerySet`, `Rider.objects`, `Rider.retired_at`, and the `Meta.constraints` entry,
exactly as in *Data model*. Extend the class docstring by one line:
`retired_at` is visible, and a retired rider is frozen (see
`riders/README.md`, *Retirement*).

## `riders/services.py`

```python
def retire_riders(rider_ids: Iterable[int], *, at) -> int:
    """Retire every still-active free agent in `rider_ids`, as of `at`
    (game time). Returns rows updated.

    One UPDATE whose WHERE re-checks team IS NULL and retired_at IS NULL —
    that re-check, not a lock, is what makes a concurrent sign_free_agent
    safe (plan D5). A rider signed or already retired in the meantime is
    silently skipped, never an error.
    """
    return Rider.objects.filter(
        pk__in=list(rider_ids), team__isnull=True, retired_at__isnull=True,
    ).update(retired_at=at)
```

Switch these four to `Rider.objects.active()`:

- `apply_weekly_growth`: `for rider in Rider.objects.active():`
- `advance_ages`: `Rider.objects.active().filter(age__lt=40).update(...)`
- `reprice_all`: `Rider.objects.active().only(...)`
- `apply_weekly_recovery`: `Rider.objects.active().exclude(pk__in=exclude_ids)`

Leave these alone: `apply_race_cost` (only racers, who are never retired),
`record_week_snapshots` (fed from `apply_weekly_growth`'s changes, which
now never include a retired rider), `mark_team_change` and
`record_initial_snapshots`.

## `transfers/services.py`

- `free_agents()` → `Rider.objects.active().filter(team__isnull=True).order_by("name")`.
  Update the docstring: "every active rider with no team — retired riders
  are never in the pool."
- `sign_free_agent`: directly after the existing `if rider.team_id is not
  None:` re-check, **still under the same lock**, add:

  ```python
  if rider.retired_at is not None:
      raise RiderNotAvailable("That rider has retired.")
  ```

  `api/`'s signing view already maps `RiderNotAvailable` to 409, so no view
  change is needed.

No change to `EXPIRY_WEEKS`, `EXPIRY_VALUE_PERCENTILE`, releasing or
auctions.

## `world/services.py`

### `_expire_free_agents(week) -> tuple[int, int]`

The return type changes from `int` to `(retired, deleted)`. The selection
logic stays the same, except that the pool is read through `free_agents()`
(D6). Only the last two lines, the outcome, change:

```python
    pool = list(free_agents())                      # D6 — was Rider.objects.filter(team__isnull=True)
    ...                                             # percentile + week cutoff: unchanged
    doomed = [...]                                  # unchanged

    raced = set(
        RaceResult.objects.filter(rider_id__in=doomed)
        .values_list("rider_id", flat=True).distinct()
    )
    retired = retire_riders(raced, at=boundary)
    never_raced = [pk for pk in doomed if pk not in raced]
    # team__isnull re-check narrows (does not close) the window against a
    # concurrent signing — see the plan's Risks. Count is len(), not
    # delete()'s cascaded-row total (D8).
    Rider.objects.filter(pk__in=never_raced, team__isnull=True).delete()
    return retired, len(never_raced)
```

`boundary` is `week.starts_at`, the value already computed above. Using
the week boundary rather than the tick's `at` follows the same
catch-up-dating rule every other write in the week loop follows
(`world/README.md`, *How a tick works*).

Rewrite the docstring's last paragraph. It currently justifies the
cascade with "an expired rider never raced for the releasing team", which
is the false assumption this ticket fixes. Replace it with the retire/delete
split and point to `specs/retire-raced-riders.md`.

Imports to add: `RaceResult` from `racing.models` (already imports
`Race`), `retire_riders` from `riders.services`, `free_agents` from
`transfers.services`.

### `_apply_training_week`

`for rider in Rider.objects.exclude(pk__in=extra):` →
`for rider in Rider.objects.active().exclude(pk__in=extra):`. This is not
strictly needed, since `apply_weekly_growth` now ignores retired riders'
deltas and a retired rider can't have raced last week. Change it anyway, so
the loop doesn't compute deltas for riders who are thrown away later.

### `tick()`

```python
    agents_retired = 0
    ...
        retired, expired = _expire_free_agents(week)
        agents_retired += retired
        agents_expired += expired
    ...
    run = TickRun.objects.create(..., agents_expired=agents_expired, agents_retired=agents_retired, ...)
```

## `world/models.py`

`TickRun.agents_retired` and the `agents_expired` help text, as in *Data
model*.

## `api/rider_profile.py`

```python
def retired_payload(rider: Rider) -> dict | None:
    """{season, week} the rider retired in, or None if active (plan D7)."""
```

- `None` when `rider.retired_at is None`.
- Otherwise `position = current_position(rider.retired_at)`:
  - `in_season` → `{"season": position.season.number, "week": position.week.number}`
  - `off_season` → `{"season": position.season.number, "week": None}`
  - `no_season` → `{"season": None, "week": None}`

`rider_profile()` adds `"retired": retired_payload(rider)`. Nothing else
changes. `race_history` already reads the team from `RaceSquadRider`, not
`rider.team`, so a retired rider's past races already show the right team.

## `api/serializers.py`

`RiderProfileSerializer` gets `retired = serializers.SerializerMethodField()`,
returning `RetiredSerializer(profile["retired"]).data` or `None`, with a new

```python
class RetiredSerializer(serializers.Serializer):
    season = serializers.IntegerField(allow_null=True)
    week = serializers.IntegerField(allow_null=True)
```

`retired` goes on the profile only, **not** on the base `RiderSerializer`.
Every other rider list (roster, free agents, squads) contains only active
riders, so there the field would always be null.

## `frontend/src/api.ts`

```ts
export interface RiderRetired { season: number | null; week: number | null }
export interface RiderProfile extends Rider {
  team: RaceResultTeam | null
  retired: RiderRetired | null
  ...
}
```

Update the `getRiderProfile` 404 comment: a 404 now means "deleted, never
raced". A retired rider returns 200.

## `frontend/src/screens/RiderProfile.tsx`

The subtitle's first segment becomes the team name if there is one, else
the retired label if `retired` is set, else "Free agent":

```ts
function affiliation(profile: RiderProfile): string {
  if (profile.team) return profile.team.name
  if (profile.retired) return retiredLabel(profile.retired)
  return 'Free agent'
}
// "Retired · Season 1, Week 11" / "Retired · Season 1" / "Retired"
```

The "no longer part of the game" branch for a 404 stays unchanged. It still
applies to a deleted never-raced rider. No other layout change (D9).

## Work items

### W1 — `riders/models.py`: `retired_at`, constraint, `active()`; migration `0012_rider_retired_at` — done

Tests, `riders/tests/test_models.py`:
- `test_active_excludes_retired_riders`: two riders, one with `retired_at`
  set. `Rider.objects.active()` returns only the other.
- `test_retired_rider_cannot_have_a_team`: create a teamed rider, set
  `retired_at`, and `save()` raises `IntegrityError` (wrap in
  `transaction.atomic()` inside the test).

### W2 — `riders/services.py`: `retire_riders`; freeze retired riders in the four weekly/seasonal loops — done

Tests, `riders/tests/test_services.py`:
- `test_retire_riders_stamps_only_teamless_active_riders`: a free agent, a
  teamed rider and an already-retired rider (with an older `retired_at`).
  Only the free agent is stamped, the return value is 1, and the
  already-retired rider's timestamp is unchanged.
- `test_retired_rider_does_not_grow_or_decline`: a young, below-potential
  retired rider, with `apply_weekly_growth(extra_deltas={pk: {"climb": 5.0}})`.
  Attributes and `growth_debt` are unchanged. The extra delta is what makes
  this test able to fail.
- `test_retired_rider_does_not_recover_freshness`: freshness 40,
  `apply_weekly_recovery(exclude_ids=set())` leaves it at 40.
- `test_retired_rider_does_not_age`: `advance_ages()` leaves age unchanged.
- `test_retired_rider_is_not_repriced`: set a `weekly_salary` that
  `weekly_salary_for` would change. `reprice_all()` leaves it, and the
  rider is absent from the returned changes.

### W3 — `transfers/services.py`: pool and signing exclude retired riders — done

Tests, `transfers/tests/test_services.py`:
- `test_free_agents_excludes_retired_riders`.
- `test_signing_a_retired_rider_raises_not_available`: nothing is charged
  (the injected `charge` is never called), and the rider is still teamless
  and retired.

### W4 — `world/`: split expiry into retire/delete; `TickRun.agents_retired`; migration `0015_tickrun_agents_retired` — done

Tests, `world/tests/test_expiry.py`:
- **Rewrite** `test_expiry_counts_riders_deleted_not_cascaded_rows`. It
  currently asserts that the raced rider and their `RaceResult` are
  **deleted**, which is the exact behaviour this ticket removes. New name:
  `test_expiry_retires_a_raced_rider_and_keeps_their_results`. Same setup:
  the raced rider still exists with `retired_at == week 11's starts_at`,
  the `RaceResult` still exists, `run.agents_retired == 1` and
  `run.agents_expired == 3`.
- `test_expiry_deletes_a_never_raced_rider`: the existing
  `test_tick_expires_low_value_long_unattached_riders` keeps passing
  unchanged (four never-raced weaklings deleted), and also asserts
  `run.agents_retired == 0`.
- `test_a_dnf_counts_as_having_raced`: the doomed rider's only result has
  `finish_time=None`, and they are retired, not deleted.
- `test_retired_riders_do_not_count_toward_the_expiry_percentile`
  (**load-bearing**, D6): pre-create several retired riders with very low
  attributes and old `unattached_since`, plus a five-agent active pool
  identical to `_five_agent_pool()`. The tick expires exactly the same four
  active weaklings it would with no retired riders present. With the
  retired riders in the pool, the cutoff would drop and fewer would expire,
  so this test fails if D6 is skipped.
- `test_a_retired_rider_is_untouched_by_later_ticks`: retire one rider,
  then move the clock across more week boundaries **and** a season close,
  and tick. Attributes, freshness, age, salary and `retired_at` are all
  unchanged.

`world/tests/test_models.py` (or wherever `TickRun` defaults are tested):
no new test is needed unless one already asserts the full field list.

### W5 — `api/`: `retired` on the rider profile — done

Tests, `api/tests.py`, next to the existing rider-profile tests:
- `test_rider_profile_of_a_retired_rider_returns_200_with_retired_week`:
  a season with weeks, a rider with a `RaceResult` and
  `retired_at = week 11's starts_at`. The response has
  `retired == {"season": 1, "week": 11}`, `team is None`, and a non-empty
  `races`.
- `test_rider_profile_of_an_active_rider_has_null_retired`.
- `test_retired_payload_outside_a_season_does_not_error`: `retired_at`
  after the season's `ends_at` gives `{"season": 1, "week": None}`.
- `test_free_agents_endpoint_omits_retired_riders`: `GET` the free-agent
  list, and the retired rider is not in `riders`.
- `test_signing_a_retired_rider_returns_409`.

### W6 — `frontend/`: show "Retired · Season S, Week W" — done

Tests, `frontend/src/screens/RiderProfile.test.tsx`:
- `shows "Retired · Season 1, Week 11" in place of the team for a retired rider`
- `shows "Free agent" for an unattached, active rider`: if no existing
  test covers this, add one. It guards that the branch order hasn't flipped.
- The existing 404 → "no longer part of the game" test stays as it is.

Run `npm test` and `npm run build` in `frontend/`.

### W7 — Docs, then archive the spec and plan

See *Documentation update*.

## Execution order

1. **W1 → W2.** The model and the freeze come first, because everything
   else depends on `retired_at` and `active()`. W2 is safe to land alone:
   nothing sets `retired_at` yet, so every rider is active and behaviour is
   identical. Commit after each.
2. **W3.** The pool and signing guard, still inert (no retired riders
   exist). Commit.
3. **W4.** The behaviour change. It lands last on the backend, when every
   consumer already treats a retired rider correctly, so there is no
   commit in which a retired rider exists but still grows, ages or sits in
   the pool. Commit.
4. **W5 → W6.** The API, then the page. Commit after each.
5. **W7.** Commit, push, open the PR.

The whole backend suite must pass after every commit. Run it, not only the
app you touched: `/home/mario/dev/cycling-manager/.venv/bin/python -m pytest`.

## Documentation update (required, not optional)

- **`riders/README.md`:** new section **`## Retirement`**, after *Team
  membership stamps*. Cover `retired_at` (game time, null = active, never
  cleared); the `retired_rider_has_no_team` constraint;
  `Rider.objects.active()` as the one definition of an active rider and
  the rule that any new every-rider loop uses it; the frozen guarantee and
  which four functions enforce it; and that #42 will stamp the same field.
  Replace the *Future work* bullet **Retirement** with a pointer to this
  section, noting that age-driven retirement (#42) is still to come.
  Also update the `advance_ages` wording that says a rider at the cap holds
  there "until retirement (#42) exists".
- **`transfers/README.md`, *Free agents*:** the pool is active teamless
  riders, not just teamless ones. Rewrite the **Expiry** bullet: a selected
  rider with race history is **retired** (kept, frozen, out of the pool for
  good), and a never-raced rider is deleted. Remove "This is a permanent
  deletion … never a re-release to the pool" and replace it with the
  split. Signing a retired rider raises `RiderNotAvailable`.
- **`world/README.md`, *How a tick works*:** the `_expire_free_agents`
  paragraph. It retires or deletes, the pool comes from `free_agents()`,
  the two `TickRun` counters, and retirement is dated `week.starts_at`.
- **`api/README.md`:** in the `GET /api/riders/<rider_id>/` entry, add the
  `retired` object and its three shapes, and note that a 404 now means only
  a deleted never-raced rider.
- **`frontend/README.md`:** the rider profile's affiliation line (team /
  Retired · Season, Week / Free agent).
- **`AGENTS.md` table:** the `riders/` row gains "retirement (a frozen,
  permanent exit from the game)". The `transfers/` row changes "weekly
  expiry of long-unattached, bottom-quintile riders" to say raced ones
  retire and never-raced ones are deleted.
- **Spec and plan:** set `Status: implemented` in both, then move both to
  `specs/archive/`.

## Verification

Beyond the unit tests, prove it once end to end on a real database:

```bash
cd .claude/worktrees/retire-raced-riders
PY=/home/mario/dev/cycling-manager/.venv/bin/python
$PY scripts/dev_db.py && $PY manage.py migrate
$PY manage.py seed_user && $PY manage.py seed_teams --claim-for test@mail.com
$PY manage.py seed_trainers && $PY manage.py load_season seasons/season-1.example.json
# GAME_CLOCK_CLASS=world.clocks.MockClock for the next commands
$PY manage.py mock_clock set <season start> && $PY manage.py tick
```

Then tick forward far enough for a few races to finish, and in
`manage.py shell` build the scenario the bug needs:

1. Pick a rider with at least one `RaceResult`. Note the race id and the
   number of rows in that race's result table.
2. Set `team=None`, set `unattached_since` to week 1's `starts_at`, and
   drop the rider's attributes to 1–5 so they sit in the pool's bottom
   quintile. Make sure the pool has at least five free agents; releasing a
   few from the demo team via the Roster screen is enough.
3. Move the clock past week 9's `starts_at` and `tick`.

**What proves it:**
- `TickRun` latest: `agents_retired >= 1`.
- The rider row exists with `retired_at` set, **and the race's result table
  still has the same row count as in step 1**. This is the check that
  catches the original bug. A passing unit test with a mocked
  `RaceResult` can't show that the cascade didn't fire on real FKs.
- Open `/riders/<id>` in the dev server (logged in as `test@mail.com`). The
  subtitle reads "Retired · Season 1, Week N" and the race history lists
  the race.
- Open the race's result page. The rider's row is there and links to the
  page above.
- The free-agent market screen doesn't list them.
- Tick another week, then check that the rider's attributes, freshness,
  age and salary are identical to their values right after retirement.

Likeliest failure: **the pool in `_expire_free_agents` still built from
`team__isnull=True`** (D6). Nothing breaks visibly for weeks. The expiry
cutoff just drifts. Only
`test_retired_riders_do_not_count_toward_the_expiry_percentile` catches it.
Confirm that test fails with D6 reverted before trusting it.

## Risks

| Risk | Mitigation |
|---|---|
| A new every-rider loop added later (or one missed here) moves a retired rider. | `Rider.objects.active()` as the single definition (D3), a `riders/README.md` rule that every loop over all riders uses it, and one freeze test per existing loop (W2) plus the multi-tick freeze test (W4). |
| The expiry pool still includes retired riders and the percentile drifts. | D6, and the load-bearing W4 test, confirmed to fail with the change reverted. |
| An engineer "tidies" things by making the default manager hide retired riders. | D3 says why not. The W5 retired-profile test would 404. |
| A concurrent signing races the retire UPDATE. | D5: the UPDATE's `team IS NULL` re-check plus `sign_free_agent`'s lock and re-check. The constraint (D2) catches anything that slips through. |
| A concurrent signing races the **delete** of a never-raced rider. Django's `QuerySet.delete()` collects pks with a SELECT and deletes by pk, so the `team__isnull` filter isn't re-evaluated at DELETE time. | Pre-existing (the same window exists on master), and narrowed but not closed here. Needs a signing to land inside a single tick's expiry step, on a bottom-quintile rider nobody wanted for 8 weeks. Accepted. Not worth a lock on every free agent row every week. |
| The expiry test that asserts cascade deletion is "fixed" by deleting the test. | W4 names it: **rewrite** it to assert retirement, keeping its setup. |
| Using `check=` from an older tutorial on `CheckConstraint`. | Django 6.1 accepts only `condition=` (*Data model*). It fails at import, so the mistake can't ship. |
| Deleting a never-raced rider still cascades their `Auction`/`Bid` rows (a rider can be listed and sold without ever racing). | Unchanged from today and outside the spec, which only protects race history. Ledger entries record the sale in their `description`, not through an FK, so no money history is lost. |

## Open questions

None.

# Post-season salary renegotiation — Implementation Plan

**Spec:** `specs/post-season-salary-renegotiation.md` · **Issue:** #26 · **Status:** proposed
**Apps touched:** `riders/`, `economy/`, `world/`, `api/`, `frontend/`

## Context you need

A rider's weekly wage lives on `riders.Rider.weekly_salary`, an integer of
whole credits. It is written once, by `riders.generation.generate_rider()`,
from `riders.pricing.weekly_salary_for(rider)` — and then never again.
`riders/README.md`'s *Salary* section states this freeze explicitly and
names #26 as the owner of what happens at a season boundary. That is the
seam this ticket fills.

`riders.pricing.weekly_salary_for(rider)` is already exactly the function
this feature needs: pure, no database access, safe on an unsaved rider,
reading only `strength(rider)` (the five engine attributes weighted by
speciality) and `age_multiplier(rider.age)`. It rounds to the nearest 50
via `_round_to_nearest_50`. **This plan does not change that function at
all** — it only calls it again, later.

The season boundary already does work. `world.services.tick()` calls
`schedule.services.process_transitions(at)`, filters the result for
`SeasonTransition.Kind.CLOSED`, and calls `riders.services.advance_ages()`
for each one. `advance_ages()` is a single bulk `UPDATE ... SET age = age + 1`
via `F()`, capped at 40, returning a row count. Repricing hangs off this
same `CLOSED` list, immediately after ageing (spec: *Ordering at the
boundary*).

`SeasonTransition` carries a `UniqueConstraint` on `(season, kind)`, which
is the game's exactly-once guarantee for anything that runs at a season
boundary — a tick that runs twice, or catches up three seasons late, sees
each transition exactly once. See `schedule/README.md`, *Exactly-once*.

The report model this feature needs is shaped almost exactly like
`staff.TrainingWeekReport` (`staff/models.py:103`) — a per-team,
per-boundary snapshot in a `JSONField`, written at the moment the change
happens because the stored value afterwards cannot tell you what it was
before. Read that model and `world.services._write_training_reports` before
starting; this plan mirrors both deliberately.

**Repo rules this work is bound by** (`AGENTS.md`):

- Dependency direction: `riders -> core, teams`. `riders/` may **not**
  import `schedule/`, `economy/` or `world/`.
- `economy -> core, teams, riders, schedule`. It already declares
  `ForeignKey("schedule.Season", ...)` as a string on `SponsorOffer` and
  `SponsorContract`.
- Only `world/` and `api/` may import everything; nothing imports them.
- Tests are pytest: `.venv/bin/python -m pytest`. A worktree has no
  `.venv` — use `/home/mario/dev/cycling-manager/.venv/bin/python`.

## Goal

When this is done:

1. At every season close, every `Rider` in the game — rostered or free
   agent — has `weekly_salary` recomputed from `weekly_salary_for()`
   against their post-ageing attributes and age.
2. Repricing runs strictly after `advance_ages()` for the same transition.
3. A `SalaryReviewReport` row exists per managed team per closed season,
   holding that team's per-rider old→new changes and the team's old and new
   total weekly wage bill.
4. Only riders whose wage moved by at least a threshold appear in a
   report's `changes`; the wage bill totals always reflect **all** riders.
5. The Roster screen shows the last season's salary review; a team with no
   report yet renders an empty state, not an error.
6. Repricing is idempotent per season: a tick running twice cannot double-
   apply or duplicate a report.

## Design decisions (settled — implement these, do not substitute)

**1. Repricing lives in `riders/services.py`, as a function that returns
what it changed.**

`reprice_all()` recomputes and saves, and returns one record per rider whose
salary moved. It must return the before/after, because — exactly as with
`TrainingWeekReport` — once the new value is stored, nothing can recover the
old one.

Do **not** mirror `advance_ages()`'s single bulk `UPDATE ... F()` here. That
works for ageing because the new value is a pure function of the old column
(`age + 1`); a salary is a function of six columns through a Python formula
with rounding, which no single SQL expression reproduces. Read the riders,
compute in Python, write back with `bulk_update`.

**2. The report model lives in `economy/`, not `riders/` or `staff/`.**

The report needs a `Team` FK and a `Season` FK. `riders/` may not depend on
`schedule/` at all, and adding one — even as a string FK — would widen a
dependency `AGENTS.md` deliberately keeps narrow. `economy/` already
imports `schedule/` and already declares `ForeignKey("schedule.Season")` as
a string on two models, and this report *is* a statement about a team's
wage bill, which is `economy/`'s subject.

Do **not** put it in `staff/` just because `TrainingWeekReport` lives there
— that model is in `staff/` because training focus is a staff concept, not
because it is a report.

**3. `riders.services.reprice_all()` knows nothing about seasons, teams or
reports.**

It takes no arguments, reprices every rider, and returns plain data. The
caller (`world.services.tick()`) is what knows a season just closed and
what turns the returned records into `SalaryReviewReport` rows. This is the
same inversion `apply_weekly_growth` / `_write_training_reports` already
uses, and it is what keeps `riders/` free of `schedule/` and `economy/`.

**4. The threshold filters the report, never the repricing.**

Every rider's stored `weekly_salary` is updated to the exact recomputed
value, always. The threshold decides only whether a change is *listed* in
the report. Do not skip the write for a sub-threshold change — that would
let small movements accumulate as permanent drift between the stored salary
and what the formula says, and two seasons of sub-threshold moves would
never be paid.

**5. `SALARY_REVIEW_THRESHOLD = 100`, in `riders/pricing.py`.**

`weekly_salary_for` already rounds to the nearest 50, so the smallest change
it can ever produce is 50 — a $1,400 → $1,403 move is not reachable. The
noise case is a rider landing one rounding step away purely from
`age_multiplier` shifting by a year. A threshold of 50 would suppress every
single-step move including genuine ones; 100 (two steps) filters age-only
drift while any real attribute movement clears it.

This is a tuning constant. It lives next to the formula whose granularity
justifies it, and W2's test pins the reasoning, not just the number.

**6. Idempotency comes from the `SeasonTransition` row, plus a
`(team, season)` unique constraint as a second line of defence.**

`process_transitions()` returns a `CLOSED` transition at most once ever, so
the repricing call cannot run twice for one season. The
`UniqueConstraint` on `SalaryReviewReport(team, season)` backs it the same
way `(team, week)` backs `TrainingWeekReport`, and report creation catches
`IntegrityError` per row inside its own `transaction.atomic()`.

**Load-bearing:** one `atomic()` per `create()`, never one around the whole
loop. An `IntegrityError` poisons the enclosing transaction in Django, so
catching it inside a shared transaction and continuing fails the next
statement with `TransactionManagementError`. This is the same trap
`schedule.services.process_transitions` and
`world.services._write_training_reports` both already navigate — copy their
shape exactly.

**7. The wage bill totals count every rider on the team, not only listed
ones.**

`payroll_before` / `payroll_after` are the sums over the team's whole
roster. If they only summed the listed changes they would contradict the
Finances screen the moment a sub-threshold rider existed.

**8. Free agents are repriced but generate no report.**

`reprice_all()` covers every rider. Report generation iterates managed
teams only (`Team.objects.filter(manager__isnull=False)`), so a rider with
`team = null` is repriced silently, exactly as the spec requires.

**9. The review is surfaced on the Roster screen, not a new screen.**

The roster is where a manager already sees each rider's weekly salary, so
old→new belongs beside it. A dedicated screen for a once-a-season list of a
handful of rows is not worth a route, and the spec explicitly defers the
richer per-rider history view to its own ticket.

## Data model

### `economy.SalaryReviewReport` (new)

`economy/models.py`. Inherits `core.models.TimeStampedModel`, as every other
model in that file does.

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `team` | `ForeignKey("teams.Team", on_delete=CASCADE, related_name="salary_reviews")` | not null | — | A deleted team's reviews go with it. |
| `season` | `ForeignKey("schedule.Season", on_delete=CASCADE, related_name="salary_reviews")` | not null | — | **String reference**, so `economy/models.py` needs no `schedule` import at module scope. The season that just *closed*. |
| `changes` | `JSONField` | not null | `list` | `[{"rider_id", "rider_name", "from", "to"}]`, whole credits. An empty list is normal and valid. |
| `payroll_before` | `PositiveIntegerField` | not null | — | Team's total weekly wage bill before repricing. |
| `payroll_after` | `PositiveIntegerField` | not null | — | After. |

Constraint: `UniqueConstraint(fields=["team", "season"], name="one_salary_review_per_team_per_season")`.

`__str__`: `f"{self.team}, {self.season}"`, matching `TrainingWeekReport`.

`CASCADE` on `season` rather than `PROTECT` (which `SponsorContract` uses):
a review is a convenience snapshot, not financial history — the ledger is
the financial record, and nothing computes money from these rows.

Migration: `economy/migrations/00XX_salaryreviewreport.py`, generated with
`makemigrations economy`. One new model, no data migration — existing
riders keep their current `weekly_salary` and get repriced at the next
season close.

## `riders/pricing.py`

Add one constant. No existing function changes.

```python
#: Smallest salary movement worth reporting to a manager (#26). The
#: formula rounds to the nearest 50, so 50 is the smallest change it can
#: produce at all; at 100 a rider must move two rounding steps, which
#: filters the drift `age_multiplier` alone produces at a birthday while
#: any real attribute movement still clears it. Filters the *report* only
#: — every rider's stored salary is always updated exactly (plan D4).
SALARY_REVIEW_THRESHOLD = 100
```

## `riders/services.py`

```python
def reprice_all() -> list[dict]:
    """Recompute every rider's weekly_salary from riders.pricing and save.

    Returns one record per rider whose salary moved by at least
    SALARY_REVIEW_THRESHOLD: {"rider_id", "rider_name", "team_id",
    "from", "to"} in whole credits. Every rider's salary is written
    regardless of the threshold; the threshold filters only what is
    returned (plan D4).

    Pure with respect to time, like advance_ages() and
    apply_weekly_growth(): this app knows nothing about seasons or the
    clock. world.services.tick() decides when to call it.
    """
```

Implementation shape — the part worth getting right:

```python
def reprice_all() -> list[dict]:
    changes = []
    updated = []
    for rider in Rider.objects.all().only(
        "id", "first_name", "last_name", "team_id", "speciality", "age",
        "weekly_salary", *ENGINE_ATTRIBUTES,
    ):
        new_salary = weekly_salary_for(rider)
        if new_salary == rider.weekly_salary:
            continue
        if abs(new_salary - rider.weekly_salary) >= SALARY_REVIEW_THRESHOLD:
            changes.append({
                "rider_id": rider.pk,
                "rider_name": rider.name,
                "team_id": rider.team_id,
                "from": rider.weekly_salary,
                "to": new_salary,
            })
        rider.weekly_salary = new_salary
        updated.append(rider)

    Rider.objects.bulk_update(updated, ["weekly_salary"], batch_size=500)
    return changes
```

`rider.name` is the right accessor — `riders/services.py:221` already feeds
`TrainingWeekReport.changes`' `rider_name` from exactly that. Use the same
spelling, not a second one.

`.only(...)` must include every field `weekly_salary_for` touches —
`speciality`, `age` and the five engine attributes — or each rider triggers
a deferred-field query. `team_id` is needed to group the report.

## `economy/services.py`

```python
def payroll_for(team) -> int:
```

Already exists (`economy/services.py:144`) — it sums the team's riders'
`weekly_salary`. Reuse it for `payroll_after`; do not write a second sum.

`payroll_before` cannot come from it (the salaries are already written by
then), so the caller derives it: `payroll_after` minus the net of that
team's changes. Put that arithmetic in the report writer, not here.

```python
def write_salary_reviews(season, changes: list[dict]) -> int:
    """One SalaryReviewReport per managed team for a closed season.

    `changes` is riders.services.reprice_all()'s return, already filtered
    by threshold. Each insert runs inside its own transaction.atomic()
    with IntegrityError caught — the same per-row shape
    process_transitions() uses, and for the same reason: an
    IntegrityError poisons an enclosing transaction (plan D6).

    A managed team with no qualifying changes still gets a report, with an
    empty `changes` list and payroll_before == payroll_after. Returns how
    many rows were written.
    """
```

Implementation shape:

```python
def write_salary_reviews(season, changes) -> int:
    by_team: dict[int, list[dict]] = {}
    for change in changes:
        if change["team_id"] is None:      # free agent: repriced, not reported
            continue
        by_team.setdefault(change["team_id"], []).append(change)

    written = 0
    for team in Team.objects.filter(manager__isnull=False):
        team_changes = by_team.get(team.pk, [])
        after = payroll_for(team)
        before = after - sum(c["to"] - c["from"] for c in team_changes)
        with transaction.atomic():
            try:
                SalaryReviewReport.objects.create(
                    team=team, season=season,
                    changes=[
                        {k: v for k, v in c.items() if k != "team_id"}
                        for c in team_changes
                    ],
                    payroll_before=before, payroll_after=after,
                )
                written += 1
            except IntegrityError:
                pass
    return written
```

`before` is derived by subtracting the net movement rather than being
captured up front, so it stays correct without a second full pass over the
roster. **This is exact only because sub-threshold changes are excluded
from `changes` but included in `payroll_after`.** That is a real,
deliberate imprecision: `payroll_before` is "what the bill was, counting
only the movements we are showing you". Accept it — the alternative is
capturing every team's payroll before repricing, which means a second
query per team for a number that differs by at most a rounding step per
rider. Say so in the docstring.

```python
def latest_salary_review(team) -> SalaryReviewReport | None:
    """This team's most recent salary review, newest season first, or None.

    Mirrors staff.services.latest_report(team) for TrainingWeekReport.
    """
```

## `world/services.py`

Extend the existing `CLOSED` loop. Today:

```python
closed = [t for t in transitions if t.kind == SeasonTransition.Kind.CLOSED]
riders_aged = 0
for _ in closed:
    riders_aged = advance_ages()
```

becomes:

```python
closed = [t for t in transitions if t.kind == SeasonTransition.Kind.CLOSED]
riders_aged = 0
riders_repriced = 0
salary_reviews = 0
for transition in closed:
    riders_aged = advance_ages()
    # Repricing AFTER ageing: next season's wage must reflect the rider a
    # manager will actually have, age included (spec, *Ordering at the
    # boundary*).
    changes = reprice_all()
    riders_repriced += len(changes)
    salary_reviews += write_salary_reviews(transition.season, changes)
```

**Load-bearing: `reprice_all()` goes inside this loop and after
`advance_ages()`, not before it and not outside it.** Before ageing, every
rider is priced a year young. Outside the loop, a tick catching up two
closed seasons writes a report for only one of them.

Add the two imports: `from riders.services import reprice_all` (alongside
the existing `advance_ages`) and `from economy.services import
write_salary_reviews` (alongside the existing economy imports).

### `world/models.py`

Add two counters to `TickRun`, matching the existing `riders_aged` /
`riders_trained` style:

| Field | Type | Default |
|---|---|---|
| `riders_repriced` | `PositiveIntegerField` | `0` |
| `salary_reviews` | `PositiveIntegerField` | `0` |

Pass both into the `TickRun.objects.create(...)` call. Migration:
`world/migrations/00XX_tickrun_riders_repriced_salary_reviews.py`.

## `api/serializers.py`

```python
class SalaryChangeSerializer(serializers.Serializer):
    """One rider's wage movement at a season close. Whole credits, never
    the display scale — this is money (riders/README.md, *Salary*)."""

    rider_id = serializers.IntegerField()
    rider_name = serializers.CharField()
    from_value = serializers.IntegerField(source="from")
    to_value = serializers.IntegerField(source="to")
```

`source="from"` is required — `from` is a Python keyword and cannot be a
field name. `TrainingChangeSerializer` (`api/serializers.py:292`) already
does exactly this; copy it.

Extend the existing `RosterSerializer` (`api/serializers.py:117`) with one
nullable key:

```python
    salary_review = serializers.SerializerMethodField()

    def get_salary_review(self, obj):
        report = obj["salary_review"]
        if report is None:
            return None
        return {
            "season_number": report.season.number,
            "payroll_before": report.payroll_before,
            "payroll_after": report.payroll_after,
            "changes": SalaryChangeSerializer(report.changes, many=True).data,
        }
```

Every key always present, null when there is no report — the same
whole-payload rule `TrainingSerializer` follows, so the SPA branches on one
response.

## `api/views.py`

`RiderListView` (`api/views.py:366`) gains one key in its response,
populated via `economy.services.latest_salary_review(team)`. No new route,
no new view — D9. Its `get()` body becomes:

```python
        riders = list(Rider.objects.filter(team=team))
        return Response(RosterSerializer({
            "riders": riders,
            "squad_value": sum(market_value_for(r) for r in riders),
            "salary_review": latest_salary_review(team),
        }).data)
```

The existing `riders` and `squad_value` keys are unchanged — this adds one
key alongside them. Import `latest_salary_review` from `economy.services`
next to the view's existing economy imports.

## `frontend/src/screens/Roster.tsx`

A panel above the roster table, rendered only when `salary_review` is
non-null and its `changes` array is non-empty:

- Heading naming the season that closed.
- The wage bill: `payroll_before` → `payroll_after`, both `$`-prefixed and
  thousands-separated via the existing `formatMoney` helper (`AGENTS.md`,
  *Displaying game money*).
- One row per change: rider name, `$from` → `$to`, and the delta.
- Sorted by absolute delta descending — the biggest movements first, since
  those are the decisions.

Add `salary_review` to the roster response type in `frontend/src/api.ts`
as a nullable field. **Update the loading-state mock in
`Roster.test.tsx`** — a missing key there has already broken this file once
(commit `3268ede`, "Fix loading-state mock in Roster.test.tsx for the
squadValue field").

## Work items

### W1 — `riders/`: the threshold constant and `reprice_all()` — DONE

Add `SALARY_REVIEW_THRESHOLD` to `riders/pricing.py` and `reprice_all()` to
`riders/services.py`. No callers yet.

Tests — `riders/tests/test_services.py`:
- `test_reprice_all_updates_every_rider_salary` — a rider whose attributes
  were raised directly gets the new formula value stored.
- `test_reprice_all_reports_only_changes_over_threshold` — a rider moved by
  50 is repriced but **not** returned; one moved by 200 is returned. This
  is the D4 guard: assert both the storage and the omission.
- `test_reprice_all_returns_before_and_after` — the record's `from` is the
  pre-call value.
- `test_reprice_all_includes_free_agents` — a rider with `team=None` is
  repriced and carries `team_id: None`.
- `test_reprice_all_is_stable_when_nothing_changed` — calling it twice in a
  row returns `[]` the second time.

### W2 — `economy/`: the `SalaryReviewReport` model — DONE

Model, `Meta.constraints`, `__str__`, and `makemigrations economy`.

Tests — `economy/tests/test_models.py`:
- `test_one_salary_review_per_team_per_season` — the second
  `create()` for the same `(team, season)` raises `IntegrityError`.

### W3 — `economy/services.py`: `write_salary_reviews` and `latest_salary_review` — DONE

Tests — `economy/tests/test_services.py`:
- `test_write_salary_reviews_writes_one_per_managed_team`
- `test_write_salary_reviews_skips_unmanaged_teams` — an unmanaged team
  gets no row.
- `test_write_salary_reviews_excludes_free_agent_changes` — a change with
  `team_id: None` lands in no report.
- `test_write_salary_reviews_records_payroll_before_and_after` — the two
  totals differ by the net of the listed changes.
- `test_write_salary_reviews_is_idempotent` — calling twice writes one row
  and does not raise. **Load-bearing:** this is the test that catches the
  `TransactionManagementError` trap in D6; if it passes only because the
  second call never reaches the `create()`, it proves nothing — assert the
  row count is 1 after two calls.
- `test_latest_salary_review_returns_newest_season`

### W4 — `world/`: wire repricing into the season-close loop — DONE

Extend the `CLOSED` loop, add the two `TickRun` counters and their
migration.

Tests — `world/tests/test_services.py`:
- `test_tick_reprices_riders_at_season_close` — after crossing a close,
  a rider whose attributes grew has a higher `weekly_salary`.
- `test_tick_reprices_after_ageing` — **load-bearing.** Construct a rider
  who will cross out of the prime age band at this boundary (age 32 → 33)
  and assert the stored salary matches `weekly_salary_for` evaluated at
  age 33, not 32. This is the one ordering bug that is invisible in every
  other test.
- `test_tick_writes_a_salary_review_per_managed_team`
- `test_tick_does_not_reprice_at_a_week_boundary` — a tick crossing only
  week transitions leaves salaries untouched, proving the mid-season
  freeze still holds.
- `test_tick_reprices_once_per_closed_season` — a tick catching up two
  closed seasons writes two reports and applies two repricings.

### W5 — `api/`: serialize the review onto the roster payload

`SalaryChangeSerializer`, the `salary_review` key on `RosterSerializer`,
and the `RiderListView` wiring.

Tests — `api/tests/test_views.py`:
- `test_roster_includes_salary_review_when_one_exists`
- `test_roster_salary_review_is_null_without_one` — the key is present and
  `null`, not absent.
- `test_roster_salary_review_serializes_from_and_to` — confirms the
  `source="from"` mapping produces `from_value` / `to_value`.

### W6 — `frontend/`: the review panel on Roster

The panel, the `api.ts` type, and the `Roster.test.tsx` mock update.

Tests — `frontend/src/screens/Roster.test.tsx`:
- renders the panel with the wage bill and one row per change
- renders nothing when `salary_review` is null
- renders nothing when `changes` is empty

### W7 — documentation

See *Documentation update*, below. Its own commit, landed last.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7.

W1 first because it is self-contained and pure — the formula call and the
threshold can be proven with no model, no migration and no tick. W2 before
W3 because the service needs the model to write to. W3 before W4 so the
tick wires together two pieces that are each already tested; debugging a
repricing bug through a tick is far worse than debugging it directly.

**W4 is where the feature becomes real**, and it is the commit to slow down
on — the ageing-order test is the one that matters. W5 and W6 are
presentation over a working backend and cannot break the simulation.

Each work item leaves the repo green and is one reviewable commit. CI runs
the full suite with an 85% backend coverage floor.

## Documentation update (required, not optional)

- **`riders/README.md`**, *Salary* — the "Set once, frozen for the season"
  paragraph currently ends by naming #26 as the open owner of the boundary.
  Rewrite it: the freeze still holds **within** a season, and
  `reprice_all()` recomputes at every season close, after ageing. Remove
  the forward reference to #26 now that it is answered. State D4 — the
  threshold filters the report, never the write.
- **`economy/README.md`** — a new *Salary review* section: the report model,
  why it lives in `economy/` rather than `riders/` (D2), the
  `(team, season)` constraint and the per-row `atomic()` shape (D6), the
  free-agent exclusion (D8), and the `payroll_before` derivation with its
  deliberate imprecision.
- **`world/README.md`**, *How a tick works* — add repricing to the
  season-close sequence, stating the ageing-then-repricing order and why.
- **`api/README.md`** — the `salary_review` key on the roster payload.
- **`frontend/README.md`** — update the `/roster` row in the screens table
  to mention the salary review panel.
- **`AGENTS.md`** — update the `riders/` and `economy/` one-line
  descriptions in the domain table: `riders/` no longer freezes salary
  forever, `economy/` now owns the salary review report.

Per `AGENTS.md`'s *Closing a ticket*: before opening the PR, delete
`specs/post-season-salary-renegotiation.md` and
`specs/post-season-salary-renegotiation-plan.md`.

## Verification

Unit tests first:

```bash
/home/mario/dev/cycling-manager/.venv/bin/python -m pytest riders economy world api
```

Then prove it end to end against a seeded world. From the worktree root:

```bash
/home/mario/dev/cycling-manager/.venv/bin/python scripts/dev_db.py
/home/mario/dev/cycling-manager/.venv/bin/python manage.py migrate
/home/mario/dev/cycling-manager/.venv/bin/python manage.py seed_user
/home/mario/dev/cycling-manager/.venv/bin/python manage.py seed_teams --claim-for test@mail.com
/home/mario/dev/cycling-manager/.venv/bin/python manage.py seed_trainers
/home/mario/dev/cycling-manager/.venv/bin/python manage.py load_season seasons/season-1.example.json
```

Then, with `GAME_CLOCK_CLASS=world.clocks.MockClock`, record a few riders'
`weekly_salary`, move the clock past the season's end, `tick`, and confirm:
the recorded riders' salaries changed, a `SalaryReviewReport` exists for the
claimed team, and the Roster screen renders the panel with `$`-prefixed,
thousands-separated amounts.

**The likeliest failure mode is the ageing/repricing order** (Risks, below),
and it is invisible in any test whose rider does not cross an age-band
edge — a rider aged 25 → 26 has `age_multiplier == 1.0` on both sides, so
ordering makes no difference and a wrong implementation passes. The check
that actually catches it is `test_tick_reprices_after_ageing`, with a rider
crossing 32 → 33. **A passing test built on a rider inside the prime band
proves nothing here.**

Second-likeliest: the report writer's transaction shape. Verify
`test_write_salary_reviews_is_idempotent` asserts a row count of 1 after
two calls and that no `TransactionManagementError` surfaces.

## Risks

| Risk | Mitigation |
|---|---|
| Repricing placed before `advance_ages()`, pricing every rider a year young. Invisible unless the test rider crosses the prime-age band. | `test_tick_reprices_after_ageing` with a rider crossing 32 → 33; the ordering comment in `tick()`. |
| `IntegrityError` caught inside a shared `transaction.atomic()`, producing `TransactionManagementError` on the next statement. | One `atomic()` per `create()` (D6), copied from `_write_training_reports`; idempotency test asserts a row count, not just absence of an exception. |
| Reaching for `bulk_update`-style `F()` arithmetic to mirror `advance_ages()`. A salary is not expressible as one SQL expression. | D1 states this explicitly and says what to do instead. |
| Sub-threshold changes skipped on write as well as on report, causing permanent drift between stored salary and formula. | D4; `test_reprice_all_reports_only_changes_over_threshold` asserts the storage *and* the omission separately. |
| `.only()` missing a field `weekly_salary_for` reads, turning one query into N deferred-field queries. | The field list is spelled out in the `riders/services.py` section; add `django_assert_num_queries` to the repricing test if the suite already uses it. |
| `Roster.test.tsx` loading-state mock not updated, breaking the frontend suite. | Called out in W6; this exact failure already happened once (commit `3268ede`). |
| `riders/` growing an import of `schedule/` or `economy/` to build the report. | D3 — `reprice_all()` returns plain data and the caller owns the season. |

## Open questions

None.

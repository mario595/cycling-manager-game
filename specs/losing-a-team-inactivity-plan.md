# Losing a team: inactivity — Implementation Plan

**Spec:** `specs/losing-a-team-inactivity.md` · **Issue:** #63 · **Status:** proposed
**Apps touched:** `accounts/`, `api/`, `teams/`, `world/`

## Context you need

`#62` built the mechanism this feature triggers, and it must be merged before
this work starts. It ships `teams.services.release_team(team, *, reason, at)`,
which clears `Team.manager`, clears `Team.managed_since`, and writes one
`teams.ManagerialSpell` row — atomically, and touching nothing else. It also
ships `ManagerialSpell.Reason.INACTIVITY`, declared but unreachable until this
ticket. Read `teams/README.md`, *Releasing a team* and *Managerial spells*,
before starting. **This ticket writes no new release logic** — it decides
*when* to call something that already exists.

`world.services.tick()` runs hourly from cron. Its middle section loops over
every `WeekTransition` that `schedule.services.process_week_transitions(at)`
just recorded — one iteration per game week that opened — and inside that loop
charges wages, applies training, and pays sponsorship. That loop is where this
check belongs; see Design decision 3.

`schedule.Season` is exactly twelve weeks (`SEASON_WEEKS`), and
`schedule.Week` rows carry `starts_at`/`ends_at` in **game** time.
`schedule.services.current_position(at)` derives whether the world is
`in_season`, `off_season` or `no_season` from `at` alone — there is no stored
"current season" pointer, deliberately (`schedule/README.md`, *Derived, not
stored*).

**Repo rules this work is bound by:**

- **`accounts/` imports nothing.** It is the root of `AGENTS.md`'s dependency
  graph, and `accounts/README.md` states it explicitly. This constrains the
  whole design — see Design decision 2.
- **The clock discipline rule** (`world/README.md`): game code reads
  `world.services.now()`, never `timezone.now()`, when deciding whether
  something scheduled is due. The one sanctioned exception is a field that
  records when something happened *on the host*, like `TickRun.finished_at`.
- `teams/` may not import `world/`; that is why `release_team` takes `at`.
- Tests are pytest. The worktree has no `.venv` — use
  `/home/mario/dev/cycling-manager/.venv/bin/python`.
- CI enforces an 85% backend coverage floor.

## Goal

When this is done:

1. Every manager's last login is recorded in **game time**, on the account.
2. `world.services.tick()`, at each week transition, releases the team of any
   manager who has been inactive for ten or more game-weeks of in-season play.
3. Weeks outside a running Season do not count toward those ten.
4. A manager who has never logged in cannot lose a team this way.
5. Released teams go through `release_team(..., reason=INACTIVITY)`, so the
   ex-manager sees `#62`'s existing lost-team message on their next login and
   the team is immediately re-claimable.
6. `TickRun` records how many teams a run released.

## Design decisions (settled — implement these, do not substitute)

### 1. Do not use `django.contrib.auth`'s `last_login`

`accounts.User` inherits `last_login` from `AbstractUser`, and Django's
`login()` updates it automatically. It is the obvious field to measure from
and it is **wrong for this feature**.

`last_login` is stamped with `timezone.now()` — **real** time. Everything this
feature compares against is **game** time: `Week.starts_at`, `Season.starts_at`,
the `at` threaded through `tick()`. Under `RealClock` the two coincide and the
bug is invisible. Under `MockClock` — dev and the entire test suite — they have
no relationship at all: `MockClock.now()` returns an arbitrary stored datetime,
so a developer who runs `mock_clock set 2027-03-01` and ticks would compute an
inactivity span of *years* for an account that logged in thirty seconds ago,
and release every managed team in the world.

**Add a separate game-time field** (`User.last_seen_at`, Data model below) and
measure from that. Leave `last_login` alone — Django owns it, other things may
come to rely on it, and it remains the honest record of real-world login time.

**Do not** try to "convert" real time to game time, and do not make the check
read `timezone.now()` for one side of the comparison. Both sides are game time
or the feature is broken.

### 2. The login stamp goes in `api/`, not `accounts/`

`accounts/` imports nothing, so `accounts.views.LoginView` cannot call
`world.services.now()` to stamp a game-time field. The field itself lives on
`accounts.User` (it is account state), but **the write happens in `api/`**,
the app already allowed to import both.

The repo uses no Django signals anywhere today. Do **not** introduce a
`user_logged_in` receiver for this: a signal in `accounts/` that reaches into
`world/` inverts the dependency graph just as surely as an import does, and it
would be the only signal in the codebase — invisible machinery a new reader has
no reason to look for.

**Instead: move the login endpoint's game-time concern into `api/`.**
`accounts.views.LoginView` keeps authenticating and keeps its response shape.
`api/` gains a thin `touch_last_seen(user, at)` helper called from the one place
that knows the game clock. See *`api/` — recording activity* for the exact
wiring and why `LoginView` is subclassed rather than edited in place.

**Load-bearing:** `accounts/views.py` must still import nothing outside
`accounts/`. If you find yourself adding `from world.services import now` to
that file, you have taken the wrong path.

### 3. The check runs in `tick()`'s existing week-transition loop

The spec leaves the cadence open. Run it once per `WeekTransition`, inside the
loop that already exists in `world.services.tick()`, alongside wages and
training.

**Why there and not its own scheduled pass:** a week transition is exactly the
event the rule is phrased in terms of ("ten game-weeks"), the loop already
iterates one entry per week including when a tick catches up late, and
`WeekTransition`'s unique constraint already gives exactly-once semantics for
free. A separate cron entry would be a second schedule to deploy, to monitor,
and to reason about against the first.

**Load-bearing:** the check runs **per transition**, never collapsed to "once
per tick". A tick catching up three weeks must evaluate three week boundaries,
the same reason `_apply_training_week` is called per week rather than with
`weeks=len(weeks)`.

### 4. Inactivity is counted in *in-season weeks elapsed*, by query, not a stored counter

Do not add a per-user "weeks inactive" counter incremented each tick. A counter
is a cache of something derivable, and it goes wrong in exactly the ways this
codebase already refuses to allow (`schedule/README.md`, *Derived, not stored*):
a double-run inflates it, a missed run under-counts it, and it needs a reset
path on every login.

**Derive it:** the number of `Week` rows whose `starts_at` falls in the
half-open interval `[user.last_seen_at, boundary)`.

```python
INACTIVITY_WEEKS = 10

def _weeks_inactive(last_seen_at, boundary) -> int:
    """In-season weeks that opened since `last_seen_at`, up to `boundary`.

    Counting Week rows rather than dividing a timedelta by seven days is
    what makes the spec's "off-season doesn't count" rule fall out for
    free: weeks only exist inside a season, so a gap between seasons
    contributes no rows. It is also robust to a season being declared with
    a gap before the next one.
    """
    return Week.objects.filter(
        starts_at__gte=last_seen_at, starts_at__lt=boundary,
    ).count()
```

`boundary` is the transition's own `week.starts_at`, **not** the tick's `at` —
same reasoning as `WeekTransition.occurred_at`: a tick running three weeks late
must evaluate each boundary as of the moment it actually happened, or a late
tick releases teams it should have released one week apart all at once with the
wrong counts.

The interval is half-open and `starts_at__gte` is deliberate: a manager who
logged in at the exact instant a week opened has seen that week.

### 5. `INACTIVITY_WEEKS` is a module constant in `world/`, not a setting or a `GameClock` field

Ten is a game-balance number that no operator should be changing per
environment, and a `GameClock` column would invite a migration plus an admin
surface for something the spec fixed at one value everywhere. A module-level
constant in `world/services.py` is greppable, testable by monkeypatch, and
honest about being a rule rather than configuration.

Contrast `GameClock.catch_up_max_races`, which *is* a field: that one exists to
be raised temporarily during an incident. This one does not.

### 6. A null `last_seen_at` exempts the account

`last_seen_at` is null for every user that exists today, and for any user who
registers but never logs in. The spec makes this exemption explicit (In scope
item 5).

**Do not backfill it to the migration date or to `last_login`.** Backfilling to
a real-time value reintroduces Design decision 1's bug under `MockClock`, and
backfilling to "now" at migration time bakes a real timestamp into a game-time
column. Null means "never seen", the filter skips it, and the first login fixes
it permanently.

**Load-bearing:** the queryset must exclude nulls explicitly
(`last_seen_at__isnull=False`). A `None` reaching `_weeks_inactive` raises;
a `None` in a `__lt` comparison in SQL silently matches nothing, which would
hide the bug rather than surface it.

### 7. Release failures must not break the tick

A release that raises must not abort the week loop and strand wages or
training. Wrap each release in `try`/`except`, record the traceback on
`TickRun.error`, and continue — the same shape `_execute` already uses for a
broken race.

## Data model

### `accounts.User` — one new field

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `last_seen_at` | `DateTimeField` | `null=True, blank=True` | none | **Game** time of the user's most recent login. Null means never logged in — exempt from the inactivity check (Design decision 6). Written only by `api.services.touch_last_seen`. |

Migration: `accounts/migrations/0003_user_last_seen_at.py` — `AddField`, no
data migration (Design decision 6). (`0002_email_login.py` is the current
head in this app.)

Docstring on the field must say *game time, not real time* and point at
`world/README.md`'s clock discipline rule. This is the field a future reader is
most likely to confuse with `last_login`; the help text is the only thing
standing between them and Design decision 1's bug.

### `world.TickRun` — one new counter

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `teams_released` | `PositiveSmallIntegerField` | not null | `0` | How many teams this run released for inactivity (#63). |

Migration: `world/migrations/0011_tickrun_teams_released.py`, depending on
`0010_merge_20260922_1145`. **Check this before writing it** — `world/` has
accumulated several merge migrations from parallel tickets (`0008_merge`,
`0009_merge` ×2, `0010_merge`), so the head may have moved again by the time
this is built. `manage.py makemigrations world` picks the right parent; do not
hand-write the dependency.

No new model. The release record is `teams.ManagerialSpell`, which `#62`
already writes.

## `accounts/models.py`

Add the field to `User` as specified. Nothing else in this app changes — no new
imports, no service, no view change. `accounts/README.md` gets one line (see
*Documentation update*).

## `api/` — recording activity

`api/services.py` (**new file** — `api/` has `views.py`, `serializers.py` and
`urls.py` today, no services module):

```python
def touch_last_seen(user, at) -> None:
    """Stamp the user's game-time last-seen. Called on login.

    `at` is passed in rather than read here so this stays a pure function
    of the caller's clock read, matching how teams/ takes `at` in
    claim_team and release_team.

    update_fields is deliberate: this runs on every login and must not
    write the rest of the row, which would race with anything else
    touching the user.
    """
    user.last_seen_at = at
    user.save(update_fields=["last_seen_at"])
```

`api/views.py` — a `LoginView` subclass, registered in `api/urls.py` ahead of
the `include("accounts.urls")` line:

```python
class LoginView(AccountsLoginView):
    """accounts' login, plus the game-time last-seen stamp.

    The stamp lives here and not in accounts/ because accounts/ imports
    nothing (AGENTS.md) and this needs world.services.now(). Subclassed
    rather than reimplemented so the authentication logic, the vague
    failure message and the response shape stay in one place.
    """

    def post(self, request):
        response = super().post(request)
        if response.status_code == 200 and request.user.is_authenticated:
            touch_last_seen(request.user, now())
        return response
```

**Route it before the include**, so `api/accounts/login/` resolves to this view
rather than `accounts.urls`'. Django's URL resolver takes the first match;
putting the `path()` above `include("accounts.urls")` in `api/urls.py`'s list is
what makes the override effective. Verify with the test named in W3 — a route
registered in the wrong order silently keeps the old behaviour and every other
test still passes.

**`request.user.is_authenticated` is checked after `super().post()`** because
`login()` inside it is what populates `request.user`. Reading it before would
give `AnonymousUser`.

## `world/services.py`

A module constant and one function, plus two lines in `tick()`.

```python
INACTIVITY_WEEKS = 10


def _weeks_inactive(last_seen_at, boundary) -> int:
    ...  # Design decision 4


def _release_inactive(week, tick: TickRun) -> int:
    """Release the team of every manager inactive for INACTIVITY_WEEKS
    in-season weeks as of this week boundary.

    Counted in game-time weeks that actually opened, so off-season gaps
    contribute nothing (spec, Rules and edge cases). A null last_seen_at
    is exempt: the account has never logged in.
    """
    boundary = week.starts_at
    released = 0
    managed = Team.objects.filter(
        manager__isnull=False, manager__last_seen_at__isnull=False,
    ).select_related("manager")

    for team in managed:
        if _weeks_inactive(team.manager.last_seen_at, boundary) < INACTIVITY_WEEKS:
            continue
        try:
            if release_team(
                team,
                reason=ManagerialSpell.Reason.INACTIVITY,
                at=boundary,
            ) is not None:
                released += 1
        except Exception:
            # One bad release must not strand this week's wages or
            # training — same shape as _execute's per-race guard.
            tick.error += f"release team {team.pk}:\n{traceback.format_exc()}\n"
    return released
```

`release_team` returns `None` for an already-unmanaged team (`#62`'s Design
decision 6), so the `is not None` guard keeps the counter honest if two ticks
race.

`at=boundary` — the release is dated to the week boundary that triggered it,
not to the tick's `at`, for the same reason the count is: a late tick must
record what happened when it happened.

In `tick()`, inside the existing `for transition in weeks:` loop, after the
economy calls:

```python
teams_released += _release_inactive(week, run_placeholder)
```

**`tick()` creates its `TickRun` row after the loop today.** `_release_inactive`
needs somewhere to record an error before that row exists. Accumulate into a
local `error` string and a local `teams_released` int, then pass both into the
existing `TickRun.objects.create(...)` call — do **not** move the `create()`
earlier in the function, which would change when every other counter is
persisted. Adjust `_release_inactive`'s signature to take and return the error
string, or collect errors into a list; either is fine, but do not reach for a
partially-built model instance.

Imports: `from teams.models import ManagerialSpell` and
`from teams.services import release_team` at module scope. `world/` may import
everything (`AGENTS.md`), and `world/services.py` already imports
`teams.models.Team`.

## Work items

### W1 — `accounts/models.py`: `User.last_seen_at` ✅
The field and its migration, exactly as *Data model* specifies. Nothing reads
or writes it yet.
**Test:** `accounts/tests.py::test_last_seen_at_defaults_to_null`.

### W2 — `api/services.py`: `touch_last_seen` ✅
New module, one function.
**Test:** `api/tests.py::test_touch_last_seen_writes_game_time` — set the mock
clock to a known instant, call it, assert the stored value is that instant and
**not** `timezone.now()`. The assertion that the two differ is the point;
under `RealClock` this test would pass while proving nothing.

### W3 — `api/`: login stamps `last_seen_at` ✅
The `LoginView` subclass and the URL ordering.
**Load-bearing:** the route must precede `include("accounts.urls")`.
**Tests:** `api/tests.py::test_login_stamps_last_seen_at` (post real
credentials through `api/accounts/login/`, assert the field moved to game
time), `::test_failed_login_does_not_stamp_last_seen_at`.

### W4 — `world/services.py`: `_weeks_inactive` ✅ (committed with W5 — see note there)
The counting function alone, tested directly against declared seasons. Easiest
piece to get subtly wrong and the cheapest to test in isolation.
**Tests:** `world/tests/test_inactivity.py` (new) —
`::test_counts_weeks_that_opened_in_the_interval`,
`::test_off_season_gap_contributes_no_weeks` (declare two seasons with a gap,
assert a span crossing it counts only in-season weeks),
`::test_week_opening_exactly_at_last_seen_is_not_counted`.

### W5 — `world/services.py`: `_release_inactive` and the `tick()` wiring ✅
(Note: implemented in the same commit as W4. `_release_inactive` calls
`_weeks_inactive` directly and both are exercised by the same test file
(`world/tests/test_inactivity.py`), so splitting them into two commits
would have meant committing dead code in the first. All of W4's and W5's
tests pass and were individually verified against a sabotaged
implementation before landing.)
The release pass, the `TickRun.teams_released` counter and its migration, the
error accumulation.
**Load-bearing:** per-transition, not per-tick; `at=boundary`, not the tick's
`at`.
**Tests:** `world/tests/test_inactivity.py::test_releases_a_manager_inactive_ten_weeks`,
`::test_leaves_a_manager_inactive_nine_weeks`,
`::test_never_logged_in_manager_is_exempt`,
`::test_unmanaged_teams_are_untouched`,
`::test_release_records_inactivity_reason`,
`::test_a_late_tick_evaluates_each_boundary_separately` (advance the clock
three weeks in one jump, assert the counts used are per-boundary),
`::test_a_failed_release_does_not_stop_the_week_loop` (monkeypatch
`release_team` to raise; assert wages for that week were still charged and the
traceback landed on `TickRun.error`).

### W6 — documentation
See *Documentation update*. Its own commit.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6.

- **W1 first** because everything else reads the field.
- **W2 and W3 before W4/W5** so there is a real way to produce an account with
  a game-time `last_seen_at`, which is what makes W5 testable against something
  other than a hand-written fixture.
- **W4 before W5** because the counting rule is the part most likely to be
  wrong, and proving it alone is far cheaper than proving it through a full
  tick.
- **W6 last**, when what was built is known.

Commit after every work item; each leaves the suite green.

## Documentation update (required, not optional)

- **`accounts/README.md`** — a new short section, *Last seen is game time*:
  the field, that it is **not** `last_login`, and why (Design decision 1).
  Note that the write happens in `api/` because this app imports nothing.
- **`world/README.md`** — under *How a tick works*, extend step 1 to say the
  week loop also releases inactive managers' teams, with the ten-week rule and
  the fact that only in-season weeks count. Add `teams_released` to whatever
  describes `TickRun`'s counters.
- **`teams/README.md`** — under *Releasing a team*, one line: `INACTIVITY` is
  now reachable, fired by `world/`'s tick; `ADMIN` remains the manual path.
- **`api/README.md`** — note that `api/` overrides `accounts`' login route to
  stamp `last_seen_at`, and why the override exists rather than the logic
  living in `accounts/`.
- **`AGENTS.md`** — the `world/` row mentions what the tick does; extend it to
  include releasing inactive managers' teams. No dependency-graph change.

## Verification

Backend:

```bash
/home/mario/dev/cycling-manager/.venv/bin/python -m pytest world api accounts teams -q
/home/mario/dev/cycling-manager/.venv/bin/python -m pytest -q
```

End to end, in this worktree (its own database and port — `python
config/worktree.py` prints them), under the mock clock:

```bash
export GAME_CLOCK_CLASS=world.clocks.MockClock
.venv/bin/python manage.py seed_user
.venv/bin/python manage.py seed_teams --claim-for test@mail.com
.venv/bin/python manage.py load_season seasons/season-1.example.json
.venv/bin/python manage.py mock_clock set 2027-03-01T00:00
.venv/bin/python manage.py tick
```

Log in once through the SPA as `test@mail.com` / `123456789` so
`last_seen_at` is stamped, then jump the clock past ten in-season weeks and
tick:

```bash
.venv/bin/python manage.py mock_clock advance --by 77d
.venv/bin/python manage.py tick
```

The team should now be unmanaged, and logging in again should land on `/claim`
with `#62`'s message naming the team and "Manager inactive".

**The likeliest failure mode is the real-time/game-time confusion in Design
decision 1**, and it is invisible under `RealClock` — which is what
`config/settings/base.py` and a default dev shell both use. A test suite that
passes proves little here on its own, because the suite forces `MockClock`
while a careless implementation reading `timezone.now()` would still look
correct in production for the first few weeks and then behave bizarrely the
first time anyone fast-forwards a dev world.

The check that actually catches it:

```bash
GAME_CLOCK_CLASS=world.clocks.MockClock .venv/bin/python manage.py shell -c "
from django.utils import timezone
from accounts.models import User
from world.services import now
u = User.objects.get(email='test@mail.com')
print('game now :', now())
print('real now :', timezone.now())
print('last_seen:', u.last_seen_at)
print('last_login:', u.last_login)
"
```

With the mock clock set to 2027, `last_seen_at` must sit near the **game**
time and `last_login` near the **real** time. If `last_seen_at` tracks real
time, W2/W3 are wrong regardless of what the suite says.

Second deliberate check: **the off-season rule.** Declare a second season
starting several weeks after the first ends, park a manager's `last_seen_at`
before the first season's close, and advance through the gap. No release may
fire on weeks that do not exist; the count must only move again once the second
season's weeks start opening.

## Risks

| Risk | Mitigation |
|---|---|
| Implementer uses `last_login`, the obvious field, and the feature silently misbehaves under `MockClock` — releasing every team on the first fast-forward. | Design decision 1 states it and says what not to do. W2's test asserts game time differs from real time; the shell check in *Verification* catches it outside the suite. |
| `from world.services import now` added to `accounts/views.py`, inverting the dependency graph. | Design decision 2 marks it load-bearing and names the tell. `accounts/README.md` already states the app imports nothing. |
| A `user_logged_in` signal is introduced instead of the view override, hiding the behaviour from anyone reading the URL conf. | Design decision 2 rejects it explicitly and says why: no signals exist in this repo today. |
| The `LoginView` override is routed *after* `include("accounts.urls")`, so it never runs — and every other test still passes. | Called out in *`api/` — recording activity*; W3's test posts through the real URL rather than calling the view directly. |
| The check is collapsed to once per tick, so a catch-up tick evaluates one boundary instead of three. | Design decision 3 marks per-transition load-bearing; `::test_a_late_tick_evaluates_each_boundary_separately` covers it. |
| A stored "weeks inactive" counter is added, drifting on double-runs and missed runs. | Design decision 4 rejects it and gives the derived query instead. |
| `last_seen_at` is backfilled during the migration, either to `last_login` or to "now", reintroducing real time into a game-time column. | Design decision 6 forbids it; `::test_never_logged_in_manager_is_exempt` asserts the null path. |
| A raising `release_team` aborts the week loop, stranding that week's wages and training. | Design decision 7; `::test_a_failed_release_does_not_stop_the_week_loop`. |

## Open questions

None. The spec's two open questions are answered here: the check runs in the
existing tick's week-transition loop (Design decision 3), and the
season-boundary counting is by `Week` rows in the interval (Design decision 4).

**One dependency, not a question:** `#62` must be merged before W5 can be
written, since `release_team` and `ManagerialSpell.Reason.INACTIVITY` come from
it. W1–W4 do not depend on it and can proceed in parallel with that ticket.

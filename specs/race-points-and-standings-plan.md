# Race points and season standings — Implementation Plan

**Spec:** `specs/race-points-and-standings.md` · **Issue:** #15 · **Status:** proposed
**Apps touched:** `competitions/` (**new**), `world/`, `api/`, `frontend/`

## Context you need

Today a race is simulated and its result is thrown into `RaceResult` rows — one
per rider, with a `position` and a `finish_time` — and nothing ever reads them
again. There is no league table, no points, and no API endpoint that returns a
race's result at all. This plan adds the scoring layer on top of results that
already exist.

**What exists and matters here:**

- `racing.models.RaceResult(race, rider, position, finish_time)` — written by
  `racing.services.simulate_race`. `position` is assigned by strict enumeration
  (`enumerate(finishers, start=1)`) over every rider in the field, sorted with
  non-finishers last. Two constraints: `unique_result_per_rider_per_race` and
  `unique_position_per_race`.
- **`finish_time` is null for a rider who did not finish** — and they *still*
  receive a position, because the enumeration does not skip them. This is the
  single most important fact in this plan. See D3.
- `racing.models.RaceSquad(race, team)` — one row per team per race. This is how
  you know which teams were in a race; `RaceResult` points at a *rider*, and the
  rider's team is reached via `Rider.team`.
- `world.services.tick()` claims due races and calls `simulate_race` for each
  inside `_execute()`. `world/` is one of only two apps permitted to import
  everything (`AGENTS.md`).
- `schedule.models.Season` / `Week`; `racing.Race.week` is the FK linking a race
  to its season. Null for an ad-hoc race outside any season.
- `api/` owns no models; it aggregates. `api/urls.py`, `api/views.py`,
  `api/serializers.py` are flat single files. `team_for(user)` in `api/views.py`
  is the house helper for "the caller's own team".
- `frontend/` is a React SPA. `/results` and `/league` are already nav items
  landing on `Placeholder`; pointing them at real components removes the
  placeholder automatically (`frontend/README.md`, *Conventions*).

**Repo rules this work is bound by:**

- **Dependency direction** (`AGENTS.md`): the new `competitions/` app may import
  `racing`, `teams`, `schedule`, `core`. **`racing/` must never import
  `competitions/`** — that would invert the graph. Nothing may import `world/`
  or `api/`.
- Apps are created on demand and get a `README.md` in the same change.
- Postgres in dev and prod. Tests are pytest, run with `.venv/bin/python -m pytest`.

## Goal

When this is done:

1. Every race that reaches `FINISHED` awards points to each team that entered
   it, by that team's best **classified** finisher, using a fixed 20-down-to-1
   table for positions 1–10.
2. Those awards are stored per team per race, at the moment the race finishes,
   and are never recalculated afterwards.
3. A season standings table is derivable for any season at any moment, ordered
   by total points with a countback tiebreak.
4. `GET /api/racing/races/<id>/results/` returns a finished race's order with
   each team's points.
5. `GET /api/competitions/standings/` returns the current season's table.
6. The SPA's `/results` and `/league` routes render both.

## Design decisions (settled — implement these, do not substitute)

**D1. `competitions/` is a new Django app and owns all scoring.**
Not a module inside `racing/`. `racing/` is the Django↔engine seam
(`racing/README.md`) and scoring is a game-rules concern with no engine
involvement. The app table in `AGENTS.md` already reserves `competitions/` for
"Divisions and Groups, standings, points" — this is that app's first foothold.

**D2. `world/`'s tick calls the scoring step, not `racing.services`.**
`simulate_race` must not learn about `competitions/` — `racing -> competitions`
is backwards. `world/services._execute()` calls `score_race(race)` immediately
after `simulate_race(...)` returns, inside the same `try`. `world/` is already
the orchestrator and already imports both.

*Do not* be tempted to use a Django signal on `RaceResult` post-save to decouple
this. A signal would fire once per rider row, run outside the caller's control,
and make the ordering between "results written" and "points awarded" implicit.
The explicit call in `_execute` is load-bearing and readable.

**D3. Scoring ignores results with a null `finish_time`. Load-bearing.**
`simulate_race` gives *every* rider a position, including riders who never
finished — they sort last but still get numbered. A team whose riders all
abandoned could therefore hold position 5 in a small field and score 8 points,
which directly contradicts the spec ("A team with nobody classified scores
zero").

So the scoring query filters `finish_time__isnull=False` before taking a team's
minimum position. This is the one detail most likely to be missed, and W3's test
`test_team_with_only_non_finishers_scores_nothing` exists specifically to catch
it.

**D4. The points table is a module constant, not a model.**
`POINTS_BY_POSITION` in `competitions/scoring.py`. The spec fixes awards at the
moment of the race and forbids recalculation; storing the awarded number per
team per race achieves that. Making the table itself a database row invites
someone editing it and expecting history to change, which is exactly the
behaviour the spec rules out.

**D5. Ties on the road are unreachable, and the plan does not code for them.**
The spec describes shared-position scoring, but `RaceResult` has
`unique_position_per_race` and `simulate_race` enumerates strictly — two riders
cannot share a position through any real code path. Score directly off
`position`. Record in `competitions/README.md` that the spec's tie rule is
dormant: it describes what to do *if* the engine is ever changed to credit equal
times, which today it cannot. Do not write a defensive branch no test can reach.

**D6. Standings are computed on read, not stored as a running total.**
A `TeamSeasonPoints` row with a mutable `total` would need updating in step with
every award and would drift if a tick half-failed. `RacePoints` rows are the
durable record; the table is an aggregate query over them. At twelve races a
season and ~16 teams this is trivially small — roughly 200 rows per season. The
spec explicitly leaves this choice to the plan.

**D7. Countback ordering is computed in Python, not SQL.**
Ordering by "most 1st places, then most 2nds, then …" down ten positions is a
ten-level sort. Expressing it in the ORM means ten conditional aggregates and an
unreadable `order_by`. The row count is tiny (one per team), so `standings()`
fetches the aggregates and sorts in Python with a tuple key. Clear beats clever
at this size.

**D8. `RacePoints` stores the position that earned the points.**
Not just the points value. The countback needs to know *which* positions a team
took, and re-deriving that from `RaceResult` at read time would mean re-applying
the null-`finish_time` filter in a second place — two copies of D3's rule is one
too many.

**D9. A team that entered but scored nothing gets no row.**
No zero-point rows. The standings query left-joins from `Team`, so a team with
no `RacePoints` rows correctly shows 0. Writing explicit zeros would double the
row count to say nothing.

## Data model

### `competitions/models.py` (new)

```python
class RacePoints(TimeStampedModel):
    race     = FK("racing.Race", on_delete=CASCADE, related_name="points")
    team     = FK("teams.Team",  on_delete=CASCADE, related_name="race_points")
    position = PositiveSmallIntegerField()   # the scoring position, 1-10
    points   = PositiveSmallIntegerField()   # what it was worth when awarded
```

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `race` | FK `racing.Race`, `CASCADE` | no | — | `related_name="points"` |
| `team` | FK `teams.Team`, `CASCADE` | no | — | `related_name="race_points"` |
| `position` | `PositiveSmallIntegerField` | no | — | The team's best classified finisher's position. Always 1–10; a team outside the points gets no row at all (D9). |
| `points` | `PositiveSmallIntegerField` | no | — | Frozen at award time (D4). |

- **Constraint:** `UniqueConstraint(fields=["race", "team"], name="one_points_row_per_team_per_race")`
  — this is what makes `score_race` safe to call twice. Load-bearing.
- **Index:** `models.Index(fields=["team", "race"], name="points_team_race_idx")`
  — the standings aggregate groups by team.
- **Meta.ordering:** `["race", "position"]`.
- `CASCADE` on both FKs, deliberately: unlike `Race.week` (which is `PROTECT`
  because deleting a week must not silently destroy race history), a points row
  is *derived* from a race. If the race goes, its derived scoring should go with
  it rather than dangle.
- Migration: `competitions/migrations/0001_initial.py`.

There is **no** `Group`, `Division` or `Standing` model. The spec's *Out of
scope* rules out multiple Groups, and one implicit Group means the standings
table is "every team". Adding an empty `Group` model now would be scaffolding
for #10/#11, not this ticket.

## `competitions/scoring.py` (new)

```python
#: Points by finishing position, 1-indexed. Positions beyond this score nothing.
#: Frozen per race at award time — see specs/race-points-and-standings.md.
POINTS_BY_POSITION: dict[int, int] = {
    1: 20, 2: 15, 3: 12, 4: 10, 5: 8, 6: 6, 7: 4, 8: 3, 9: 2, 10: 1,
}

def points_for(position: int) -> int:
    """What a finishing position is worth. Zero outside the table."""
```

## `competitions/services.py` (new)

```python
def score_race(race: Race) -> list[RacePoints]:
    """Award points for one finished race, by each team's best classified
    finisher. Idempotent: a race already scored returns its existing rows.

    Raises ValueError if the race is not FINISHED.
    """
```

The body, because the null-`finish_time` filter and the idempotency are both
easy to get subtly wrong:

```python
def score_race(race: Race) -> list[RacePoints]:
    if race.status != Race.Status.FINISHED:
        raise ValueError(f"{race} is not finished; nothing to score")

    existing = list(RacePoints.objects.filter(race=race))
    if existing:
        return existing

    # finish_time__isnull=False is the whole of D3: simulate_race numbers
    # every rider including those who never finished, so an unfiltered
    # min(position) would score a team for abandoning.
    best_by_team: dict[int, int] = {}
    rows = (
        RaceResult.objects
        .filter(race=race, finish_time__isnull=False)
        .values_list("rider__team_id", "position")
    )
    for team_id, position in rows:
        if team_id is None:
            continue
        if team_id not in best_by_team or position < best_by_team[team_id]:
            best_by_team[team_id] = position

    to_create = [
        RacePoints(race=race, team_id=team_id, position=position,
                   points=points_for(position))
        for team_id, position in best_by_team.items()
        if points_for(position) > 0
    ]
    return RacePoints.objects.bulk_create(
        to_create, ignore_conflicts=True,
    )
```

`ignore_conflicts=True` plus the unique constraint is the belt-and-braces for a
tick that is retried after a partial failure: the read-then-write above is not
atomic, and two concurrent calls would otherwise raise `IntegrityError`.

```python
def standings(season: Season) -> list[dict]:
    """The season's table: every team, total points, and countback.

    Ordered by total points descending, then by most 1st places, then most
    2nd places, and so on down the scoring positions. A team with no points
    sorts last. See D7 for why this sorts in Python.

    Each entry: {"team": Team, "points": int, "positions": {pos: count}}.
    """
```

The sort key, spelled out because getting the countback direction wrong is silent:

```python
def _countback_key(entry: dict) -> tuple:
    counts = entry["positions"]
    # Negated throughout: Python sorts ascending, and more is better for
    # every component here.
    return (-entry["points"],) + tuple(
        -counts.get(position, 0)
        for position in sorted(POINTS_BY_POSITION)
    )
```

Season scoping: a race belongs to a season through `race.week.season`, so the
aggregate filters `race__week__season=season`. A race with a null `week` is
outside every season and never appears in a table — correct, and it falls out of
the join for free.

## `world/services.py` (changed)

`_execute()` gains one call. The whole diff:

```python
from competitions.services import score_race   # new import
...
        try:
            simulate_race(race, game_time=at)
            score_race(race)                    # new
            tick.races_finished += 1
        except Exception:
            ...
```

Scoring inside the existing `try` is deliberate: a race that simulates but fails
to score is a broken race, and the existing handler already marks it `FAILED`
and records the traceback without stopping the other races in the tick.

**Note the ordering constraint:** `score_race` requires `race.status ==
FINISHED`, and `simulate_race` sets that before returning. Do not move the call
above `simulate_race`.

## `api/serializers.py`, `api/views.py`, `api/urls.py` (changed)

Two new endpoints, both `IsAuthenticated` (the project default — neither has the
"shop window" justification the clock/calendar endpoints have; see
`api/README.md`, *Authentication*).

**`GET /api/racing/races/<race_id>/results/`** — `RaceResultsView`,
`RaceResultsSerializer`. Returns the finishing order plus each team's points:

```json
{
  "race": {"id": 4, "name": "Opening Classic", "status": "finished"},
  "results": [
    {"position": 1, "rider": {"id": 9, "name": "..."},
     "team": {"id": 2, "name": "...", "code": "MOV"},
     "finish_time": 4512.0, "finished": true}
  ],
  "points": [
    {"team": {"id": 2, "name": "...", "code": "MOV"}, "position": 1, "points": 20}
  ]
}
```

- A race that is not `FINISHED` returns `404` rather than an empty result list —
  "no results yet" and "no such race" are the same thing to the SPA, and a
  200-with-nothing invites rendering an empty table as if the race were a draw.
- `finished` is `finish_time is not None`, surfaced explicitly so the SPA does
  not have to infer D3's distinction itself.
- Query with `select_related("rider__team")` — without it this is one query per
  rider.

**`GET /api/competitions/standings/`** — `StandingsView`, `StandingsSerializer`.
The current season's table, via `schedule.services.current_position(now())`:

```json
{
  "state": "in_season",
  "season": 1,
  "standings": [
    {"rank": 1, "team": {"id": 2, "name": "...", "code": "MOV"}, "points": 47}
  ]
}
```

- Reuses the **same `state` vocabulary** as the existing position and calendar
  endpoints (`in_season` / `off_season` / `no_season`) — `api/README.md`
  documents that vocabulary and a third spelling would be a needless dialect.
  `off_season` returns the season that just finished with its final table;
  `no_season` returns `standings: []`.
- `rank` is computed server-side from the sorted order, 1-indexed. Do not make
  the SPA infer it from array index — two teams level on points and countback
  are genuinely joint, and the server is where that is known.

`api/urls.py` gains, **above** the SPA catch-all (see `api/README.md`, *URL
ordering*):

```python
path("racing/races/<int:race_id>/results/", RaceResultsView.as_view(), name="race-results"),
path("competitions/standings/", StandingsView.as_view(), name="standings"),
```

## `frontend/` (changed)

- `src/api.ts` — `getRaceResults(raceId)`, `getStandings()`, plus the
  `RaceResults` and `Standings` types. Both are reads: plain `fetch`, no
  `writeJson`.
- `src/useStandings.ts` (**new**) — same shape as `useCalendar.ts`: poll every
  60s, `{ standings, loading, error }`. Copy that file's lifecycle exactly,
  including the `cancelled` flag.
- `src/screens/League.tsx` (**new**) — the standings table. Rank, team (code +
  name), points. Highlight the caller's own team row using `useAuth`'s
  `me.team.id`, the same way the roster screen identifies its own rows.
- `src/screens/Results.tsx` (**new**) — the most recent finished race's order
  with its points column. Uses `useCalendar` to find the latest race whose
  `status` is `finished`, then `getRaceResults` on it.
- `src/App.tsx` — point the `/league` and `/results` routes at the new screens.
  Their `Placeholder` entries disappear automatically
  (`frontend/README.md`, *Conventions*).

No new nav items: `/league` ("League table") and `/results` ("Results") are
already in `NAV_SECTIONS`.

## Work items

### W1 — `competitions/`: create the app ✅ done
`startapp competitions`, add to `LOCAL_APPS` in `config/settings/base.py`,
write `competitions/README.md`, add `competitions/models.py` with `RacePoints`
and its `0001_initial` migration.
**Test:** `competitions/tests/test_app.py::test_app_is_installed` and
`test_race_points_unique_per_team_per_race` (assert the constraint raises
`IntegrityError` on a duplicate `(race, team)`).
Mirror `world/tests/test_app.py` for the app check.

### W2 — `competitions/scoring.py`: the points table ✅ done
`POINTS_BY_POSITION` and `points_for`.
**Test:** `competitions/tests/test_scoring.py::test_points_by_position` (the
full table, asserted value by value — a typo in a constant is exactly what a
table test is for) and `test_position_outside_table_scores_zero` (11, 50).

### W3 — `competitions/services.py`: `score_race`
**Load-bearing: the `finish_time__isnull=False` filter (D3).**
**Tests:** `competitions/tests/test_services.py` —
- `test_best_finisher_scores_for_the_team`
- `test_only_the_best_finisher_counts` (a team with riders in 2nd and 4th
  scores 15, not 25)
- `test_team_with_only_non_finishers_scores_nothing` — **the D3 test.** Build a
  race where a team's only riders have `finish_time=None` at positions that
  would otherwise score, and assert no `RacePoints` row exists for them.
- `test_position_outside_the_points_writes_no_row` (D9)
- `test_scoring_twice_is_idempotent` (call `score_race` twice, assert the row
  count is unchanged)
- `test_unfinished_race_raises`

### W4 — `competitions/services.py`: `standings`
**Tests:** `competitions/tests/test_standings.py` —
- `test_totals_accumulate_across_races`
- `test_team_with_no_points_appears_on_zero` (D9 — the left join)
- `test_countback_breaks_a_tie_on_points` (two teams on equal points, one with a
  win and the other with two seconds; assert the winner ranks higher)
- `test_races_outside_a_season_are_excluded` (a race with `week=None`)
- `test_table_resets_between_seasons`

### W5 — `world/services.py`: call `score_race` from the tick
**Test:** `world/tests/test_services.py::test_tick_scores_finished_races` — run
a tick over a due race and assert `RacePoints` rows exist afterwards. Also
`test_a_race_that_fails_to_score_is_marked_failed` (monkeypatch `score_race` to
raise; assert `Race.status == FAILED` and the tick's other races still ran).

### W6 — `api/`: the race results endpoint
**Tests:** `api/tests.py` — `test_race_results_returns_order_and_points`,
`test_unfinished_race_results_404`, `test_race_results_requires_login`.

### W7 — `api/`: the standings endpoint
**Tests:** `api/tests.py` — `test_standings_returns_ranked_table`,
`test_standings_no_season_returns_empty`, `test_standings_requires_login`.

### W8 — `frontend/`: the League table screen
`api.ts` additions, `useStandings.ts`, `screens/League.tsx`, route in `App.tsx`.
**Verification:** manual — see below. No frontend test harness exists in this
repo yet; do not add one as part of this ticket.

### W9 — `frontend/`: the Results screen
`screens/Results.tsx`, route in `App.tsx`.
**Verification:** manual.

### W10 — Documentation
`competitions/README.md` (written in W1, completed here with the final
behaviour), plus updates to `AGENTS.md`, `racing/README.md`, `world/README.md`,
`api/README.md`, `frontend/README.md`. See *Documentation update*.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7 → W8 → W9 → W10.

The reasoning: **W1–W4 are pure backend with no callers**, so each one leaves
the suite green on its own and nothing in the running game changes. W5 is the
moment the feature becomes live — points start being awarded by the tick — and
it is deliberately *after* the scoring logic is fully tested, so if a tick
starts failing you already know the scoring itself is sound.

W6/W7 expose what W3/W4 compute; they cannot be written earlier because there is
nothing to serialize. W8/W9 consume W6/W7 for the same reason.

**Commit after every work item.** W3 and W4 are the two that carry real logic
and should each be reviewable alone.

## Documentation update

- **`competitions/README.md`** (new, W1) — sections: *What this app owns*;
  *What `competitions/` may import* (the dependency direction, and explicitly
  that `racing/` must never import back — D1/D2); *The points table* (the
  values, and that they are frozen per race — D4); *Why non-finishers are
  filtered* (D3, with the reason spelled out: `simulate_race` numbers every
  rider); *The tie rule is dormant* (D5); *Standings are computed, not stored*
  (D6/D7); *Future work* — Groups and Divisions (#10/#11), promotion and
  relegation (#13), prize money (#19).
- **`AGENTS.md`** — mark `competitions/` **built**, `README.md` in the domain
  table; add `competitions -> core, racing, teams, schedule` to the dependency
  block.
- **`racing/README.md`** — a line under *What lives here* noting that
  `RaceResult.position` is assigned to every rider including non-finishers, and
  that anything scoring off it must filter on `finish_time`. This is the trap
  D3 exists to avoid and it belongs where the next reader of `RaceResult` will
  look.
- **`world/README.md`** — the tick now scores a race after simulating it, and
  why that call lives here rather than in `racing/` (D2).
- **`api/README.md`** — the two new endpoints, in the existing *What exists*
  list, noting both are `IsAuthenticated` and that standings reuses the
  `state` vocabulary.
- **`frontend/README.md`** — `/league` and `/results` are no longer
  placeholders; update the route table at the top.

## Verification

```bash
.venv/bin/python -m pytest
.venv/bin/python manage.py migrate
```

End to end, against a dev database with a season loaded:

```bash
.venv/bin/python manage.py load_season seasons/season-1.example.json
.venv/bin/python manage.py mock_clock set "<a time just before race 1>"
.venv/bin/python manage.py tick
```

Then confirm, in `manage.py shell`:

```python
from competitions.models import RacePoints
from competitions.services import standings
from schedule.models import Season
list(RacePoints.objects.values_list("team__code", "position", "points"))
[(e["team"].code, e["points"]) for e in standings(Season.objects.get(number=1))]
```

**The likeliest failure mode is D3** — scoring a team for a rider who abandoned.
A passing `test_best_finisher_scores_for_the_team` proves nothing about it,
because in a race where everyone finishes the filter is a no-op.

**The check that actually catches it:** in the shell above, find a race with at
least one non-finisher and assert the awarded position matches the best rider
whose `finish_time` is not null:

```python
from racing.models import RaceResult
race = ...  # a finished race
dnf = RaceResult.objects.filter(race=race, finish_time__isnull=True)
print(dnf.values_list("rider__team__code", "position"))   # positions that must NOT score
print(RacePoints.objects.filter(race=race).values_list("team__code", "position"))
```

No position in the second list may appear in the first. If the engine's bundled
courses produce no non-finishers at all, force one: null a `finish_time` on a
finished race's result row by hand, delete that race's `RacePoints`, re-run
`score_race`, and confirm the team's award changed.

Frontend (W8/W9): run the dev server, log in as a manager whose team has scored,
and confirm `/league` shows the table with that team's row highlighted and
`/results` shows the last finished race with a points column.

## Risks

| Risk | Mitigation |
|---|---|
| **Scoring a team for a rider who did not finish** — `simulate_race` numbers every rider, so an unfiltered `min(position)` is wrong in a way that looks right in any race where everyone finishes. | D3's filter; `test_team_with_only_non_finishers_scores_nothing`; the shell check under *Verification*, which is the only step that exercises it against real engine output. |
| `racing/` importing `competitions/` to call scoring from `simulate_race` — the obvious-looking placement, and it inverts the dependency graph. | D2: the call lives in `world/services._execute`. Stated in both `competitions/README.md` and `world/README.md`. |
| A retried tick double-scoring a race. | The `one_points_row_per_team_per_race` constraint plus the early return in `score_race`; `test_scoring_twice_is_idempotent`. |
| Countback sorted the wrong way (ascending) — silent, and only visible when two teams are actually level. | `_countback_key` negates every component with the reason in a comment; `test_countback_breaks_a_tie_on_points` builds a genuine tie rather than trusting the happy path. |
| Standings including ad-hoc races with `week=None`, inflating totals. | The `race__week__season` join excludes them by construction; `test_races_outside_a_season_are_excluded`. |
| The new API routes added below the SPA catch-all, silently returning `index.html`. | `api/README.md`, *URL ordering*; the endpoint tests assert JSON, which HTML would fail. |

## Open questions

None.

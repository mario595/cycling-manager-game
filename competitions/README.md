# Competitions — scoring and standings

## What this app owns

Turning a finished race's results into points, and those points into a
season standings table. `RacePoints` is one model here: one row per team
per race, recording the position that scored and what it was worth.
`MarkerPoints` is the other: one row per team per sprint marker, recording
the crossing position that scored and what it was worth — see *Sprint
points* below.

It also owns the **prize table** — `scoring.PRIZE_BY_POSITION` and
`prizes_by_team` — but writes no model of its own for it. The money lands
in `economy/`'s ledger, because a team's balance is the sum of its
`LedgerEntry` rows and only `economy/` may write them. `competitions/`
computes *what is owed*; `economy.services.pay_race_prizes` records it.
The two are wired together by `world/` (`world/README.md`), the same way
scoring is.

`competitions.services.points_by_team(week)` — one dict of a week's combined
points, `{team_id: total}`, absent keys meaning zero — exists to feed
`economy/`'s weekly fanbase adjustment (`economy/README.md`, *Why `economy/`
does not query `RacePoints`*). It sums `RacePoints` and sprint `MarkerPoints`
together, so fanbase and sponsorship move with sprint points too — see
*Sprint points* below. `world/` calls it off the week that just
completed and hands the result to `economy.services.apply_weekly_fanbase`,
because `economy` may not import this app — the same inversion this file
documents for `racing/` below.

There is no `Group` or `Division` model yet — one implicit Group, one
table, per `specs/archive/race-points-and-standings.md`. See *Future work* below.

## What `competitions/` may import

`racing`, `teams`, `schedule`, `core` — see `AGENTS.md`'s dependency
graph. **`racing/` must never import `competitions/`** — that would
invert the graph. Scoring a race is therefore never called from
`racing.services.simulate_race`; it is called from `world/services.py`,
right after `simulate_race` returns (`world/README.md`). `world/` is
already one of the two apps allowed to know about everything.

## The points table

`competitions/scoring.py`'s `POINTS_BY_POSITION` runs 20 down to 1 for
1st through 10th place; 11th and below score nothing. Points are frozen
onto a `RacePoints` row the moment a race is scored and are never
recalculated — if the table is retuned later, races already scored keep
what they were awarded at the time (`specs/archive/race-points-and-standings.md`,
*Rules and edge cases*).

`STAGE_POINTS_BY_POSITION` and `GC_POINTS_BY_POSITION` sit alongside it —
roughly half and double the one-day table respectively — for a stage race's
own stages and its final general classification. See *Stage races*, below.

## The prize table sits beside it

`PRIZE_BY_POSITION` pays 1st through 10th, the **same positions** the
points table covers, so a test asserts the two tables never drift apart.
Unlike points, which go to a team's single best finisher, **every** placed
rider earns a prize: a team with riders 2nd and 5th is paid for both. The
payout is written to `economy/`'s ledger when a race finishes, so — like
`RacePoints` — the amount is frozen at payout time and a later retune does
not rewrite past results.

`STAGE_PRIZE_BY_POSITION` and `GC_PRIZE_BY_POSITION` are the stage race
counterparts, same shape, same positions — see *Stage races*, below.

## Sprint points

Each sprint marker (`racing.RaceMarker`, kind `sprint`) carries a `weight` —
`minor`, `standard` or `major`, set by the course author, defaulting to
`standard` so an unweighted marker in an existing season file keeps
working. `competitions/scoring.py`'s `SPRINT_POINTS_BY_WEIGHT` pays the top
`SPRINT_PLACES` (5) crossing positions per weight, declining down the
order; even the `major` tier's win stays at most half of `POINTS_BY_POSITION[1]`,
so a sprint is a bonus a squad can chase, never an alternate way to top
the league. `score_sprints(race)` writes one `MarkerPoints` row per
(marker, team) and is idempotent, the same shape as `score_race`.

**A team's row comes from its single best-placed rider among the top 5
crossings — cut to 5 first, then keep each team's best.** Walking the
crossing order until five distinct teams have scored would let a team
that took 1st and 2nd push a 6th-place rider into the scoring places,
which is exactly the double-scoring the best-rider rule exists to
prevent. `score_sprints` filters `MarkerCrossing.position__lte=SPRINT_PLACES`
**before** de-duplicating by team, never after.

**Mountain markers never score here.** Every aggregate — `score_sprints`,
`points_by_team`, `standings` — filters `marker__kind=RaceMarker.Kind.SPRINT`,
so a future mountain-points ticket (#17) writing its own `MarkerPoints`
rows on mountain markers cannot leak into a sprint total.

**Sprint points are frozen at award time**, same rule as `RacePoints` and
the prize table. `world/services.py` calls `score_sprints(race)` right
after `score_race(race)`, in its own `try`/`except` — a sprint-scoring
failure is recorded on the tick and never rewrites a finished race into
`FAILED`.

**A finish-line sprint marker is not a special case.** It scores like any
other sprint marker; whether placing one there double-pays a race winner
is a course-authoring decision this app does not guard against — see
`specs/archive/sprint-points.md`.

## Why non-finishers are filtered

`racing.services.simulate_race` assigns a `position` to every rider in a
race, including one whose `finish_time` is null because they never
finished — they simply sort last. `score_race` filters
`finish_time__isnull=False` before finding each team's best-placed
rider, so a team whose whole squad abandoned scores nothing rather than
being credited for wherever its DNF riders were numbered. This is the
single most important rule in this app; see `racing/README.md` for the
trap it exists to avoid.

## The tie rule is dormant

The product spec describes what happens when two riders share a
finishing position — both teams score the position's points, and the
next finisher scores as if that position didn't exist. This cannot
happen today: `RaceResult` has a `unique_position_per_race` constraint
and `simulate_race` assigns positions by strict enumeration, so two
riders can never hold the same position. `score_race` scores directly
off `RaceResult.position` and has no branch for a tie. If the engine is
ever changed to credit equal times, this rule needs writing for real.

## Standings are computed, not stored

There is no running-total model. `competitions.services.standings(season)`
aggregates `RacePoints` for that season on every call, then adds each
team's season sprint `MarkerPoints` total on top — `entry["points"]` is
the combined figure the league table shows, and `entry["sprint_points"]`
the sprint-only component. At twelve races a season and roughly sixteen
teams that is on the order of two hundred rows — cheap enough that a
stored total, and the risk of it drifting from the per-race rows if a
tick half-fails, buys nothing.

Countback ordering (most 1st places, then most 2nds, and so on) is
computed in Python over the small per-team aggregate rather than
expressed as a multi-level SQL `ORDER BY` — clearer at this size.
**Countback counts finish positions only.** A sprint win never enters
`entry["positions"]`, so two teams level on combined points but one
reached it purely through sprints rank below the one that reached it
through a finish — sprinting is a different skill from finishing, and
tie-breaking follows the finish.

## Stage races

A stage race's own stages score and pay exactly like a one-day race —
`score_race`/`prizes_by_team`, `finish_time__isnull=False`, everything
above — just from the reduced `STAGE_*` tables instead of the one-day ones,
switched on `race.stage_race_id`. See `racing/README.md`, *Stage races*,
for what a stage race is and how the general classification it feeds is
computed.

The GC itself is different: `RacePoints.kind` (`RACE` or `GC`) exists
**because** of it. A stage race's final stage carries both its own
`kind=RACE` points and, once the whole tour completes, a `kind=GC` row for
the same race — `score_race`'s idempotency check and `standings()`/
`points_by_team()` (which sum every `RacePoints` row regardless of `kind`,
so a GC win counts exactly like any other 1st place in countback) both need
that distinction to not conflate the two. `score_general_classification`
and `gc_prizes_by_team` are the GC's own `score_race`/`prizes_by_team`:
called once, from `world.services._settle_stage_race`, the moment the
stage race completes — never from `racing/` or from this app on its own,
same as one-day scoring.

## Future work / possible improvements

- **Groups and Divisions** (#10, #11) — today there is one implicit
  Group. Splitting the standings by Group is the next thing this app
  will need once more than one exists.
- **Promotion and relegation** (#13) — reading the table to move teams
  between tiers at season end.
- **Race tiers** — every race currently awards from the same table;
  scaling points by a race's prestige is deferred until the calendar
  needs that shape.
- **Mountain points** (#17) — the identical mechanism for mountain
  markers, tracked as its own `MarkerPoints` rows (filtered by kind) and
  never pooled with sprint points into one tally.
- **A full points retune** — sprint points were sized as a starting point
  (`specs/archive/sprint-points.md`, D6); a pass across every points
  source belongs after #17 exists and the whole picture is known.
- **A sprinters' classification** (#18) — accumulating a season's sprint
  crossings into a standing of their own, with a visible leader mid-race
  and an end-of-stage-race bonus.

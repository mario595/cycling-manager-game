# Competitions — scoring and standings

## What this app owns

Turning a finished race's results into points, and those points into a
season standings table. `RacePoints` is the one model here: one row per
team per race, recording the position that scored and what it was worth.

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
does not query `RacePoints`*). `world/` calls it off the week that just
completed and hands the result to `economy.services.apply_weekly_fanbase`,
because `economy` may not import this app — the same inversion this file
documents for `racing/` below.

There is no `Group` or `Division` model yet — one implicit Group, one
table, per `specs/race-points-and-standings.md`. See *Future work* below.

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
what they were awarded at the time (`specs/race-points-and-standings.md`,
*Rules and edge cases*).

## The prize table sits beside it

`PRIZE_BY_POSITION` pays 1st through 10th, the **same positions** the
points table covers, so a test asserts the two tables never drift apart.
Unlike points, which go to a team's single best finisher, **every** placed
rider earns a prize: a team with riders 2nd and 5th is paid for both. The
payout is written to `economy/`'s ledger when a race finishes, so — like
`RacePoints` — the amount is frozen at payout time and a later retune does
not rewrite past results.

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
aggregates `RacePoints` for that season on every call. At twelve races a
season and roughly sixteen teams that is on the order of two hundred rows
— cheap enough that a stored total, and the risk of it drifting from the
per-race rows if a tick half-fails, buys nothing.

Countback ordering (most 1st places, then most 2nds, and so on) is
computed in Python over the small per-team aggregate rather than
expressed as a multi-level SQL `ORDER BY` — clearer at this size.

## Future work / possible improvements

- **Groups and Divisions** (#10, #11) — today there is one implicit
  Group. Splitting the standings by Group is the next thing this app
  will need once more than one exists.
- **Promotion and relegation** (#13) — reading the table to move teams
  between tiers at season end.
- **Race tiers** — every race currently awards from the same table;
  scaling points by a race's prestige is deferred until the calendar
  needs that shape.

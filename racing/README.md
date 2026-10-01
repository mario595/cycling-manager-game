# Racing — the bridge between Django and the race engine

## Role of this document

`racing/` is not a game domain in the way `riders/` or `teams/` are. It is the
**seam** between the persistence layer (Django) and the simulation layer
(`race_engine/`). This file explains why that seam exists and the rules that
keep it intact.

## The core rule

> `racing/adapters.py` is the **only** module in the project that may import
> from `race_engine`.

The dependency runs one way and must keep running one way:

```
racing.adapters  ->  race_engine        yes
race_engine      ->  django, racing     never
```

### Why the engine stays free of Django

The engine is plain dataclasses with no ORM. That is deliberate, and it buys
three things worth protecting:

1. **Speed.** A race is ~2000 ticks x N riders. Every attribute read going
   through a Django model instance, with its descriptors and deferred-field
   machinery, is dead weight in the innermost loop of the whole game.
2. **Testability.** The engine's 49 tests run in under a second with no
   database. Making `Rider` a Django model would put a database behind every
   one of them.
3. **Freedom to change.** Engine internals can be restructured without a
   migration, because nothing in the engine is persisted.

The cost is one translation layer. That is a good trade, and `adapters.py` is
where the whole cost is paid.

### Two Rider classes, on purpose

`riders.models.Rider` (a database row) and `race_engine.models.Rider` (a
dataclass) are different classes describing overlapping things. This is not
duplication to be refactored away — it is the seam doing its job. The database
rider carries game-layer concerns the engine knows nothing about (contracts,
age, form, morale); the engine rider carries only what the simulation reads.

The shared attribute names are listed once, in `riders.models.ENGINE_ATTRIBUTES`,
so the adapter iterates that tuple rather than hard-coding the list twice.

**`to_engine_rider` scales attributes by freshness — the only place the
feasibility penalty is applied.** Each of the five engine attributes is
multiplied by `riders.services.freshness_multiplier(rider.freshness)`, linear
between `PENALTY_AT_FLOOR` (0.80) at `FRESHNESS_FLOOR` (20) and 1.0 at full,
then clamped into the engine's valid range. The downgrade therefore travels
into the simulation itself — a tired rider is genuinely weaker in the race —
rather than being shaved off results afterwards. This is deliberate and
single-location: `race_engine/` never hears the word "freshness" (see the
core rule above), `riders/` owns the arithmetic, and `racing/` applies it at
the only crossing point (the plan for #59 made this the load-bearing decision,
because every other placement either leaks the penalty into `race_engine/` or
requests an ad-hoc `to_engine_rider` override that bypasses it).

## Race logs

### What they are

A log is a brotli-compressed JSONL file: one header line holding everything
constant for the race, then a sampled tick-by-tick payload. The race player
consumes it whole; nothing else reads it. See `race_player/README.md` for the
consumer's expectations and the header/sample layout.

### Where they live

Logs are **never** stored in the database. They are megabytes per race and grow
with distance x rider count — the old uncompressed format ran an 18 km test race
to ~5.5 MB and `mountain_stage.jsonl` to 75.7 MB; the header + sampled, brotli-
compressed `.jsonl.br` format takes the same mountain stage to ~0.75 MB.

Instead:

- The file is written through **Django's storage API** (`FileField` /
  `default_storage`), never with a raw `open()`. The engine writes its stream to
  a temp file (it may not learn about Django); `simulate_race` hands the finished
  `.jsonl.br` bytes to storage and the `sample_count`/`tick_interval` pair comes
  back from the engine rather than by counting lines of a binary stream.
- `RaceLog` holds only the pointer plus metadata: `sample_count` (written
  samples, not race seconds), `tick_interval` (the race seconds between samples,
  mirrored from the header so admin can read a log without opening it) and
  `size_bytes` (the **compressed** size). `tick_interval` is the second clock
  anyway — stored once here so admin does not decompress a file just to learn it.
- Development writes to the local filesystem under `MEDIA_ROOT`.

Because nothing touches file paths directly, moving logs to object storage is a
change to `STORAGES` in settings and nothing else. When local disk starts to
hurt, **Cloudflare R2** is the frugal target: 10 GB free and, unusually, zero
egress fees — and egress is what actually costs money when players watch
replays.

One thing does change shape on R2: `GET /api/racing/races/<race_id>/log/`
(`api/README.md`) currently streams the bytes Django reads out of storage. With
a private bucket that becomes a **signed-URL redirect** — the same view, one
fewer hop through this application, and a URL that expires. The endpoint's
contract (authenticated, brotli when accepted, `404` when there is no log)
does not change, so nothing in `race_player/` or `frontend/` has to know.

### The slimmed, compressed format (#88)

Tracked as [#88](https://github.com/mario595/cycling-manager/issues/88). One
header line, then sampled positional arrays, brotli-compressed. The full spec is
in `race_engine/README.md`; the short version:

- **Header (line 1):** `v`, `tick_interval`, `course_length`, `segments`,
  `teams`, `riders` (identity only: id, name, team, role) and `wind_band` when
  wind is enabled. `v` lets a future format change be detected rather than
  mis-parsed.
- **Samples (every later line):** `[time, riders, wind?]`, one positional array
  per rider in header order — the array index *is* the rider identity. Values
  are rounded to screen precision; `finish_time` is deliberately **not** snapped
  to the sample grid, or a bunch sprint would manufacture ties that contradict
  `RaceResult.finish_time`.
- **Sampling:** the first tick, every `tick_interval` ticks, and any tick where
  a `finished` flag changes — a finish is never invisible, only its exact
  instant is quantised. Default interval is 2 s.
- **Compression:** written brotli (quality 5) by the engine through an
  incremental compressor; the stored file keeps the `.jsonl.br` extension.
  `GET /api/racing/races/<race_id>/log/` serves it: streamed from storage,
  `Content-Encoding: br` when — and only when — the caller accepts `br`, and
  decompressed otherwise (`api/README.md`). The player never sees a file name
  and never links to `/media/`.

### Rejected: regenerating logs from a seed

Storing only `(config, seed)` and re-running the engine on demand looks
attractive — near-zero storage — but it is **wrong for this project**, not
merely premature.

The engine is deterministic *for a given engine version*. It is under active
development. Any change to the formulas, the tactics or the tick order changes
the outcome for the same seed. A log regenerated after such a change would
disagree with the `RaceResult` rows recorded at the time — the standings would
say one thing and the replay another.

`Race.seed` is therefore stored for **reproducibility during debugging only**.
The stored log file is the single authoritative record of what happened in a
race. Do not add a "regenerate log" feature.

## Triggering simulations

Races are simulated when the game clock reaches their `starts_at`, not in a
request/response cycle — a race takes far too long to run inside an HTTP
request. There is no job queue (no Celery, no Redis) and none is needed:
`world/` owns the tick and calls `racing.services.simulate_race` for each
race it claims as due. See `world/README.md` for how the tick works.

`world/` may run against a real, live clock (production) or a developer's
mock clock (development and test); `racing/` never knows or cares which —
`simulate_race`'s `game_time` parameter is why.

The deployment assumption is now **hourly**, not daily: the world is nudged
once an hour so a race scheduled for a given hour starts near that hour. See
`world/README.md`, *Deployment requirement*.

## What lives here

| Model | Purpose |
|-------|---------|
| `Race` | A race to simulate: name, course JSON, wind settings, seed, plus scheduling (`starts_at`, `status`, `finished_at` — all **game** time, set and read by `world/`). `week` links it to the season it belongs to (`schedule.Week`); nullable — a race outside any season. `race_day` is derived, never authored — see *A race belongs to a week*, below. |
| `RaceLog` | Pointer to the log file plus its metadata. One per race. |
| `RaceResult` | One rider's finishing position. Small, queryable, stays in the DB. |
| `RaceSquad` | One team's entry into one race — see *Squads*, below. |
| `RaceSquadRider` | One rider's membership in a squad, and whether they lead it. |
| `RaceMarker` | One named point on a race's course — see *Markers and crossings*, below. |
| `MarkerCrossing` | One rider's recorded crossing of one marker. |
| `StageRace` | A named run of 2-7 consecutive-day races sharing one squad and a general classification — see *Stage races*, below. |

`Race.course` is stored in the same `{length, gradient}` shape the engine's
config parser already accepts, so an existing `race_engine/configs/*.json`
can seed a Race without a translation step.

**`RaceResult.position` is assigned to every rider, including one who never
finished.** `simulate_race` sorts non-finishers (`finish_time is None`) to
the back of the field but still numbers them — there is no "did not
finish" position, only a lower one. Non-finishers are ordered
furthest-travelled first among themselves (key
`(finish_time is None, finish_time or 0, -position)`, matching
`race_engine`'s own `get_results()`), not in whatever order they happen to
appear. They are now a real, sizeable population, not just an edge case:
the race engine's time cut (broom wagon) marks a rider DNF once they're too
far behind the winner to matter, on top of the abandons this already
covered — see `race_engine/README.md`, *Simulation tick* and *Known
limitation*. Anything that scores or ranks off `RaceResult` must filter on
`finish_time` first; see `competitions/README.md` for the rule this
protects (a team whose whole squad didn't finish must not be credited for
wherever those riders were numbered).

## Markers and crossings

Course markers are named points a race declares (`RaceMarker`), and the
riders who crossed each one (`MarkerCrossing`) — see
`specs/course-markers-plan.md`. Design decisions that shaped the schema:

- **D1 — `RaceMarker` is a row, not JSON on `Race`.** Crossings need
  something to point at, and a future issue adds a weight/category column to
  the marker — a migration on a model, not a reshaped JSON blob. `Race.course`
  stays a bare `{length, gradient}` segment list: four existing readers (the
  training attribute, the API, the frontend, the engine adapter) depend on
  that shape, and changing it to carry markers would break all of them.
- **D2 — `MarkerCrossing` is a row, not a log event.** The log is the race
  player's input and nothing else reads it; the marker-points and
  classification queries need database rows, the same reason `RaceResult` is a
  table and not a log line.
  The engine's log format does not change in this ticket — no header key, no
  version bump. Markers are deliberately **not** in the JSONL (see
  `race_engine/README.md`, *JSONL output format*).
- **D5 — a marker exactly at the finish line takes its order from the
  results.** In a same-second sprint, `RaceResult`'s order (integer
  `finish_time`, then the engine's rider order) is final; an interpolated
  crossing time could disagree with it. `simulate_race` therefore builds a
  finish-line marker's crossings from the same `ordered` list it writes
  `RaceResult` from — finishers only, `crossed_at = finish_time`.
- **D9 — one ordering of markers, threaded through.** Marker index `i` in the
  engine must mean the same `RaceMarker` here. `simulate_race` fetches
  `list(race.markers.order_by("distance", "pk"))` **once** and passes that
  same list to `to_engine_course` and to the crossing writer. `to_engine_course`
  takes it as a *required* second argument on purpose — a query of its own
  would be a second, potentially different ordering the day someone changes
  one of them.

`RaceMarker` validates exactly the way `Race` does: `kind` ∈ {sprint,
mountain}, non-empty `name` of at most 100 chars, `0 < distance <= course
length`, checked in `clean()` from `save()` (`racing/README.md` mirrors the
loader's checks), and `Meta.ordering` of `("distance", "pk")` — the same
order `simulate_race` relies on. Two markers may share a distance; names may
repeat. Crossings carry the marker, the rider, a `position` (1 for the first
rider across) and the interpolated `crossed_at` (race seconds — `finish_time`
for a finish-line marker, per D5).

**`RaceMarker.weight`** (`minor` / `standard` / `major`, default `standard`)
is the weight/category column D1 anticipated, added by #16 (`specs/archive/sprint-points.md`).
It scales what a sprint marker's crossings score — see `competitions/README.md`,
*Marker points* — and is **inert on a mountain marker**: the season loader
(`schedule/README.md`) rejects a `weight` key on one, so the two vocabularies
cannot be confused. The engine never sees it: weight does not change how a
marker is contested, only what a crossing is later worth.

**`RaceMarker.category`** (`hc` / `cat1` / `cat2` / `cat3`, default `cat2`)
is the mirror of that: it scales what a **mountain** marker's crossings score,
is **inert on a sprint marker**, and is rejected by the loader on one. A
separate field rather than more `weight` values, because a season file written
today with `weight` on a climb would have to be reinterpreted the day climbs
started scoring — and because `AddField(default="cat2")` gives every existing
mountain row the middle of the scale in one step, with no data migration
(`specs/archive/mountain-points.md`, D1). The engine never sees it either: a
category changes what a crossing is worth, not how the climb is ridden.

**Races with markers are born through `racing.services.create_race`, not
`Race.objects.create`.** `create_race` opens one transaction, creates the
`Race` then one `RaceMarker` per entry (`markers=[{"kind", "name",
"distance", "weight"?, "category"?}, ...]`), each `create()` so `save()` →
`clean()` runs.
`load_season` injects it in place of the plain `Race.objects.create` it wired
before (`schedule/README.md`, *What `schedule/` may import*) — `schedule/`
still imports nothing from `racing/`, it just receives a callable that
happens to be `create_race`. A race created without markers gets an empty
`markers` list and behaves exactly as before; the crossing writer records
nothing, and the engine's contest rule and crossing detection are both
guarded off when a course has no markers (D7 in the plan).

## The weekly-training readers

Weekly training ([#36](https://github.com/mario595/cycling-manager/issues/36))
needs one thing only this app can answer: what a race *rewarded*. That answer
lives in `services.py`, computed entirely from the stored `Race.course` JSON,
in two functions:

- **`course_training_attribute(course)`** — which single attribute a course
  trains. Pure and engine-free: a distance-weighted average gradient at or
  above `CLIMB_GRADIENT_THRESHOLD` (2.0%) trains `climb`; a course of
  `SPRINT_MAX_DISTANCE` (120 km) or less with no such climb trains `sprint`;
  `RESISTANCE_MIN_DISTANCE` (200 km) or more trains `resistance`; anything
  else merely flat trains `flat`. `positioning` is never awarded — no course
  shape distinctly rewards draft skill (the plan's Design decision 4).
- **`riders_who_raced(week)`** — `{rider_id: [attribute, ...]}` over every
  `RaceResult` with a `finish_time` in `week`'s races, one query rather than
  one per race. A rider who finished several of the week's races appears once
  per race and is trained for each. This is the *training* reader — a rider
  cut by the time limit didn't complete the course, so they earn nothing
  here.
- **`riders_who_started(week)`** — `set[int]` of every `RaceResult.rider_id`
  in `week`'s races, finisher or not. This is the *fatigue* reader `world/`
  excludes from weekly recovery: missing a race costs a rider's legs the
  same as racing it (`riders/README.md`, *Freshness*), so it deliberately
  does **not** filter on `finish_time` the way `riders_who_raced` does.

**Terrain is classified here, not read from the engine's `Terrain`**, for the
same reason everything else in this app is the seam: only `racing/adapters.py`
may import `race_engine`, and the stored course JSON is already the segment
list — reaching into the engine would drag a whole other import path in for a
computation the app's own `Race.course` row already carries. `riders/` must
not import `racing/`, so the two halves meet in `world/`, which imports both:
see `world/README.md`, *How a tick works*, for where these results are
consumed each week.

### A race belongs to a week

`Race.week` is a `ForeignKey("schedule.Week", ...)`, declared as a string so
`racing/models.py` needs no import of `schedule/` — the app-level dependency
(`racing -> schedule`, see `AGENTS.md`) is real, but the module stays
import-free of it.

A race whose `starts_at` falls outside its week's `[starts_at, ends_at)`
range is rejected: `Race.clean()` checks the containment, called from
`Race.save()`. This is enforced in Python, not a database constraint,
because the bound lives on a different table (`Week.starts_at`/`ends_at`)
and a `CheckConstraint` cannot reach across rows. `clean()` is a no-op when
`week` is null — every race before this feature landed, is.

`on_delete=PROTECT`, deliberately: deleting a week (and by extension a
started season) must never silently delete the races and results run in
it. (An unstarted season's `--replace` path deletes its races explicitly
before the season, precisely because `PROTECT` refuses to do it silently —
see `schedule/README.md`, *Replacing a season with races*.)

**Races are created by `schedule/`'s `load_season` command**, not by
anything in this app. `schedule/loaders.create_races()` places each
declared race into its week and calls an injected `create_race` callable —
`racing.models.Race.objects.create`, passed in by the command — rather than
`schedule/` importing this module directly. That indirection exists purely
to keep the dependency direction honest: `racing -> schedule` is the
documented, one-way edge (`AGENTS.md`), so `schedule/` importing `Race`
would create a cycle. See `schedule/README.md`, *What `schedule/` may
import*, for the full picture.

**One race per day, enforced at the database level.** `race_day` is a
`DateField`, set in `save()` from `starts_at`
(`self.race_day = self.starts_at.date() if self.starts_at else None`) —
never set by hand, never read anywhere. It exists solely so a
`UniqueConstraint` on `(week, race_day)` can express "at most one race per
calendar day within a week" — a rule a bare `race_day` constraint would get
wrong, since it would forbid two unrelated ad-hoc races (both with a null
`week`) from sharing a date; Postgres treats `NULL` as distinct in a unique
index, so `(week, race_day)` correctly allows that.

## Simulating a race

`racing/services.py` has the one entry point: `simulate_race(race, *,
game_time)`. It assumes the caller (`world/`) has already claimed the race by
flipping its status to `RUNNING`; it runs the engine, writes the log and
`RaceResult` rows, and flips the race to `FINISHED`.

`game_time` is a parameter, not read from the clock here — **`racing/` must
never import `world/`** (`AGENTS.md`'s dependency direction). The clock
passes its own current time in; `racing/` stores it as `Race.finished_at`
without knowing where it came from.

The engine writes its log with a raw `open()` and cannot be taught about
Django (see *Where they live*, above), so `simulate_race` runs it into a
`tempfile.TemporaryDirectory()` and hands the finished file to
`RaceLog.file` through Django's storage API afterwards — one extra copy per
race, paid to keep both rules (no raw file writes, no Django in the engine)
intact at once.

**The field is built from squads, not the whole rider table.** `simulate_race`
calls `ensure_squads(race)` first, then builds the engine's rider list from
`RaceSquadRider` rows for that race — see *Squads*, below. A rider not
selected by any team's squad simply does not appear in the log, the replay,
or the results.

**A squad member whose rider has since left that team is dropped before
racing, not raced anyway.** A rider can be sold at auction ([#28](https://github.com/mario595/cycling-manager/issues/28))
or released to the free agent pool ([#29](https://github.com/mario595/cycling-manager/issues/29))
while still sitting in a team's saved squad for a race that has not run
yet — both let a listed/released rider keep racing until the move
actually happens, so a manager leaving them in a squad is the normal
case, not a mistake. `simulate_race`'s squad query filters on
`rider__team_id == squad__team_id` (an `F()` comparison, not two separate
reads) for exactly this reason: `to_engine_rider` and, downstream,
`competitions.services.score_race` / `prizes_by_team` all key off the
rider's **current** `team_id`, never the squad's — so racing a
team-mismatched rider anyway would credit the result to whoever they
belong to *now*, not the team that actually fielded them. The team that
picked them simply races a rider short; nothing else about the race is
affected. `_effective_leader_ids` handles the one wrinkle this creates:
if the dropped rider was the squad's picked leader, the engine still
requires exactly one leader per team present
(`race_engine.models.validate_team_leaders`), so the lowest-pk remaining
squad member is promoted **for this race's engine call only** — the
squad's own stored `is_leader` is never rewritten, since this is a
simulation-time workaround for an engine constraint, not a correction to
what the manager actually picked.

**Finishers pay the freshness cost.** Inside the same transaction that records
`RaceResult` rows, every rider who finished has `RACE_FRESHNESS_COST` (25,
`riders/`) deducted from their stored `freshness`, floored at
`FRESHNESS_FLOOR` — the counterpart to the penalty above (see `riders/README.
md`, *Freshness*). Auto-picked and saved squads cost the same; resting is
what recovers the ground, once per week in `world/`. A stage costs
`STAGE_FRESHNESS_COST` (10) instead — see *Stage races*, below.

**Every race — one-day or a stage — also writes `RaceResult.group_time` for
each finisher.** See *Stage races*, below, for what it is and why it is
written unconditionally.

## Squads

Before a race, a manager picks which four of their team's riders start and
which one leads — see `specs/archive/squad-selection.md` (now folded in here) for the
player-facing feature. Two models record the choice:

- **`RaceSquad(race, team)`** — one row per team per race, plus
  `is_auto_picked` (see below).
- **`RaceSquadRider(squad, rider, is_leader)`** — one row per selected rider,
  four per squad.

`RaceSquad` is also the record of which teams started a race: the results
API (`api/`) reads it to list non-scoring teams, so a finished race's points
table is exhaustive rather than derived from which teams recorded a result
(see `api/README.md`). `RaceSquadRider` is, likewise, the durable record of
which team a rider raced for on a given day — `Rider.team` only ever holds
the *current* team, so both the race results endpoint and the rider profile
endpoint (#96) read squad membership rather than the rider's own `team`
field to label a past race correctly after a release or a signing.

**Membership is rows, not a JSON list on `RaceSquad`.** `simulate_race` joins
against every selected rider's attributes in one query to build the engine's
field, and a JSON array of ids would mean either N+1 lookups or a manual
`id__in` reassembly. Rows also give a `UniqueConstraint` — `unique_rider_per_
squad` — that stops the same rider being entered twice, which a JSON array
cannot express. The leader flag lives on the membership row (`is_leader`),
not as a `leader = FK(Rider)` on `RaceSquad`: a leader FK pointing at a rider
who is not in the squad would need validating separately, and `is_leader`
cannot represent that state at all.

**Exactly four riders and exactly one leader is a service rule, not a
database constraint.** Postgres cannot express "this parent has exactly four
children" without a trigger or a denormalised counter, and neither is worth
the machinery here. `racing.services.set_squad(race, team, rider_ids,
leader_id)` is the **only sanctioned writer** — it validates (right size, no
duplicates, every rider on the team, the leader among them), refuses a race
that has already started, then replaces the whole squad in one transaction.
The Django admin can save a squad that breaks this rule; that is accepted,
and it is why the *simulation* validates again independently (see below),
rather than trusting whatever is in the database.

**The one exception: a stage race's later stages.** `set_squad` refuses any
stage past the first outright — a stage race's squad is chosen once, for
stage 1 (see *Stage races*, below). From stage 2 on, `ensure_squads` writes
the squad by a **different** path, `_carry_squads`, which deliberately
bypasses `_write_squad`'s exactly-four check: a carried squad may hold fewer
than four riders, or none, once riders have been cut or abandoned in earlier
stages. Do not relax `_write_squad` itself to allow this — that check still
protects every manager write, one-day race or stage 1 alike.

**A team with no squad still starts.** `ensure_squads(race)`, called at the
top of `simulate_race`, writes an auto-picked squad (`is_auto_picked=True`)
for every team that does not already have one for this race — a manager who
never opened the screen still fields a squad, per the spec's item 8. The pick
itself, `auto_pick_squad`, is deliberately naive — by total engine attributes
descending, each rider's raw total weighted by their `freshness_multiplier`
(tired riders rank behind equally strong rested ones; [#59]), then by pk as a
tiebreak, with the strongest rider leading — and is meant
to lose to a manager who chooses deliberately (#45 covers a smarter fallback
later; #39 and #44 will share this same mechanism rather than duplicate it).
A team with fewer than four riders is skipped with a warning, not an
exception — that is a broken roster (enforcing the floor belongs to whichever
feature lets riders leave one), and it must not stop every other team racing.

**The engine validates too, independently.** `race_engine.models.
validate_team_leaders` (moved out of `config.py`, called from `run_race`)
rejects a field with zero or two-plus leaders on one team regardless of how
it got there — the Django path never went through `load_config`'s validation,
so without this a malformed squad could reach the simulation and produce a
race with undefined role-scaled tactics. See `race_engine/README.md`.

**The engine's per-race role comes only from `RaceSquadRider.is_leader`.**
A rider has no leadership of their own — `Rider` carries no `role` field —
so `to_engine_rider`'s `role` argument is required, not defaulted, and
`simulate_race` passes `"leader"` or `"support"` from the squad row for
every rider it converts. See `specs/leadership-is-per-race.md`.

## Stage races

A stage race (`StageRace`) is a named run of 2-7 ordinary races on
consecutive calendar days, entirely inside one `schedule.Week` — see
`specs/archive/stage-races.md` for the player-facing feature. Each stage is
just a `Race` row with `stage_race` and `stage_number` set; a one-day race
has both null, and is not internally modelled as a stage race of length one.

**`StageRace` stores nothing derivable from its stages.** No status, no
stage count, no GC. `is_complete()` (every stage `FINISHED` or `FAILED`,
with at least one actually `FINISHED`) and `final_stage()` (highest
`stage_number`) both read the `Race` rows in `stages` fresh — the same
"derived, not stored" principle `schedule/README.md` uses for the current
season/week. The only frozen stage-race facts are the GC award rows
themselves (`competitions.models.RacePoints(kind=gc)`, a
`gc_prize_money` ledger entry), frozen at award time like every other
scoring row in this app.

### The squad is chosen once, for stage 1

`set_squad` refuses outright for `stage_number > 1` — see *Squads*, above.
From stage 2 on, `ensure_squads` calls `_carry_squads` instead of
auto-picking: for each team's **stage-1** squad, it keeps only the members
`riders_still_in(stage_race, stage_number)` says are still in the race, and
writes that (possibly short, possibly empty) set as the stage's own
`RaceSquad`/`RaceSquadRider` rows, preserving `is_leader` and
`is_auto_picked` from stage 1. A team with nobody left simply gets no squad
row for that stage — it scores nothing, the same as a whole squad not
finishing today.

**"Still in the race" (`riders_still_in`)**: a rider from the stage-1 squad
who has a non-null `finish_time` in *every* earlier `FINISHED` stage. A
`FAILED` stage neither removes anyone nor counts as "earlier" — it produced
no results, so there is nothing to have missed. `racing.services.
carried_squad(race, team)` is the read-only twin of the same rule, used by
the squad API to show a later stage before it has actually run; both share
`riders_still_in` rather than re-deriving D4 twice.

If the stored leader is among those dropped, `_effective_leader_ids`
(above) promotes the lowest-pk remaining member **for that stage's engine
call only** — the stage-1 `is_leader` row is never rewritten, exactly the
way it already handles a leader sold or released mid-race.

### Same group, same time — `RaceResult.group_time`

Written for **every** finisher of **every** race, one-day included — the
same field, unconditionally, so `simulate_race` has no stage-shaped branch
here; only a stage race's general classification ever reads it.
`racing.services.group_times(finish_times)` chains consecutive finishers:
a new group starts whenever the gap to the *previous* finisher exceeds
`GROUP_GAP_SECONDS` (1.0), so a bunch strung out over several small gaps is
still one group. `1.0` rather than a strict `<1` because the engine ticks
at whole seconds — a stricter threshold would only ever group riders who
cross in literally the same tick, which is exactly the fraction-of-a-second
sprint gap the feature exists to remove. `finish_time` and `RaceResult.
position` are **never** touched by this — a stage's points and prize money
still come from strict finishing order, unchanged.

### The general classification is a read, not a table

`racing.services.general_classification(stage_race, *, through_stage=None)`
computes the GC fresh from stage results every time it is asked, never
stored. A rider is eligible iff they have a non-null `finish_time` in every
`FINISHED` stage up to `through_stage` (every `FINISHED` stage if
`through_stage` is `None`); their GC time is the sum of those stages'
`group_time` (every finisher has one, by construction above). Ordered by GC
time ascending, then by the sum of their stage positions ascending (the
spec's tiebreak — better individual stage placings — for the genuine edge
case of two riders finishing with an identical GC time), then by rider id
for determinism. Each entry's team comes from the **stage-1** squad, never
`Rider.team`: a rider cannot change team mid-tour (see *still in the race*,
above), and the squad is the durable per-race record `racing/README.md`
already treats it as (see *Squads*).

### Scoring and paying the GC

Stages score and pay from `competitions.scoring`'s reduced
`STAGE_POINTS_BY_POSITION`/`STAGE_PRIZE_BY_POSITION` tables — roughly half
the one-day tables — via the same `score_race`/`prizes_by_team` functions,
switched on `race.stage_race_id`. The GC itself is scored and paid **once**,
by `competitions.services.score_general_classification`/`gc_prizes_by_team`,
called from `world.services._settle_stage_race` the moment
`stage_race.is_complete()` — see `world/README.md`, *How a tick works*. GC
points land as a `RacePoints` row on the stage race's **final stage**, with
`kind=RacePoints.Kind.GC` rather than `RACE` — the same race can carry both
a stage's own points and the tour's GC points, so `kind` is what tells them
apart; `score_race`'s idempotency check and any reader building a stage's
own results must filter on `kind=RACE`, never assume every row on a race is
one. GC prize money lands as an `economy.LedgerEntry` with its own
`kind=gc_prize_money`, never `prize_money` — the final stage's own stage
prize and its GC prize can land on the exact same `(team, race, position)`,
and sharing a kind would let one payout collide with, and silently drop,
the other (`economy/README.md`).

### Declaring one

A season file's top-level `stage_races` list (`schedule/README.md`,
*Declaring a season*) is the only way one is created; `racing.services.
create_stage_race` and `racing.services.create_race` (with `stage_race`/
`stage_number` passed straight through) are the injected callables the
loader uses, the same indirection `create_races` already relies on to keep
`schedule/` free of any import from `racing/`.

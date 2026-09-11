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

## Race logs

### What they are

A log is a JSONL file, one entry per tick, each entry holding the full state of
every rider. The race player consumes it whole; nothing else reads it. See
`race_player/README.md` for the consumer's expectations.

### Where they live

Logs are **never** stored in the database. They are megabytes per race and grow
with distance x rider count — an 18 km test race with a small field already
produces ~5.5 MB. Free-tier Postgres is 0.5–1 GB total; a handful of races
would fill it.

Instead:

- The file is written through **Django's storage API** (`FileField` /
  `default_storage`), never with a raw `open()`.
- `RaceLog` holds only the pointer plus metadata (tick count, size).
- Development writes to the local filesystem under `MEDIA_ROOT`.

Because nothing touches file paths directly, moving logs to object storage is a
change to `STORAGES` in settings and nothing else. When local disk starts to
hurt, **Cloudflare R2** is the frugal target: 10 GB free and, unusually, zero
egress fees — and egress is what actually costs money when players watch
replays.

### Planned: slim and compress the log format — NOT YET DONE

The current format is knowingly wasteful. Deferred deliberately; do it before
storage becomes a real problem, not after.

The redundancy is large and easy to remove:

- `segments` and `teams` are written identically on **every** line. They are
  static for the whole race and belong in a header on line 1 only.
- Per-tick rider entries repeat `name`, `team` and `role`, none of which
  change. Only the id is needed after the header.
- Ticks are 1 second. The player almost certainly cannot show the difference
  between 1 s and 2 s sampling.

With those three changes plus gzip, the 5.5 MB sample should land in the low
hundreds of kilobytes. That single change makes every storage question easier,
so it comes first.

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
| `Race` | A race to simulate: name, course JSON, wind settings, seed, plus scheduling (`starts_at`, `status`, `finished_at` — all **game** time, set and read by `world/`). |
| `RaceLog` | Pointer to the log file plus its metadata. One per race. |
| `RaceResult` | One rider's finishing position. Small, queryable, stays in the DB. |

`Race.course` is stored in the same `{length, gradient}` shape the engine's
config parser already accepts, so an existing `race_engine/configs/*.json`
can seed a Race without a translation step.

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

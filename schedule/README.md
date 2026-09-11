# Schedule — seasons, weeks, and the transition record

## What this app owns

`Season`, `Week`, and `SeasonTransition` — the numbered periods racing
happens inside, and the exactly-once record of when one opens or closes.
Not races (that is `racing/`, which points at a `Week`), not the clock
(`world/`), and not the race calendar yet (#7 — which weeks and days races
fall on).

## Derived, not stored

There is no "current season" field anywhere in this app. `current_position(at)`
is a pure function of the time passed in: it queries `Season`/`Week` ranges
and returns where `at` falls. A missed tick can never make the game display
the wrong week, because nothing caches "where we are" — every read asks the
question fresh.

**Adding a cached pointer (`Season.is_current`, a `CurrentSeason` singleton,
a `WorldState.season_id`) would be a regression, not an optimisation.** The
production clock (`world.clocks.RealClock`) holds no state and never
advances; `tick()` only processes what has *become* due. A stored pointer
would be a cache of `current_position()` with no reliable event to
invalidate it on.

## The week boundary

A season's `starts_at` must be a Monday at 00:00:00 UTC. This is an
arbitrary but fixed choice — any single fixed weekday would satisfy the
spec's "every week starts on the same day" rule, and Monday reads as "week
1" to a European cycling audience. UTC because every other datetime in the
project is UTC. The race calendar (#7) will place a race's "day of the
week" against this same anchor.

## Exactly-once

`SeasonTransition` has a `UniqueConstraint` on `(season, kind)`. That
constraint — not a check-then-insert — is what makes recording a
transition safe under concurrent ticks: `process_transitions()` wraps each
row's `create()` in its own `transaction.atomic()` block and catches
`IntegrityError` when a concurrent call wins the race. One `atomic()` per
create, never one around the whole loop — an `IntegrityError` poisons the
enclosing transaction in Django, so catching it inside a shared transaction
and continuing would fail the next statement with
`TransactionManagementError`.

`occurred_at` is the season's own `starts_at`/`ends_at` — the boundary that
was crossed — never the `at` passed to `process_transitions()`. A tick that
runs three weeks late still records the moment the season actually opened
or closed, not how late the tick was. (`recorded_at`, separately, is
`auto_now_add` real time — the gap between the two is exactly how late.)

## The transition hook ships empty

Nothing happens at a season boundary today beyond the `SeasonTransition`
row being written. That row is the hook later features (promotion/
relegation, contract renewal, salary reviews — all out of scope here, see
`specs/season.md`) will attach to. Shipping it empty is deliberate, not an
oversight.

## Declaring a season

```bash
manage.py load_season seasons/season-1.example.json
manage.py load_season seasons/season-1.example.json --replace
```

The file is JSON: `number` (int, starting at 1) and `starts_at` (ISO 8601,
must resolve to a Monday 00:00:00 UTC). The command creates the `Season`
and its twelve `Week` rows in one transaction.

A season that has already started (`starts_at <= now()`) can never be
touched again — `load_season` refuses outright, with no `--replace`
escape. A season declared but not yet started is still a draft: reloading
its file requires `--replace` and replaces it (cascading its weeks).

Unknown top-level keys in the file are warned about and ignored, not
rejected — the file gains a `races` key when #7 lands, and this is the one
place a forward-compatibility allowance is worth it.

There is deliberately no admin UI, no API endpoint, and no interactive
prompt for declaring a season — see `specs/season.md`'s *Out of scope*.

## What `schedule/` may import

`core`, and nothing else it needs today. **`schedule/` must never import
`world/`** — that would invert the dependency direction in `AGENTS.md`
(`world/` may import everything; nothing may import `world/`).

The one documented exception: `load_season.py` reads `world.services.now()`
to check whether a season has already started, imported **inside**
`handle()`, not at module scope. That is deliberate — the rule protects
`schedule/`'s *library* code (`models.py`, `services.py`), and the command
is an entry point, the same way `world/`'s own management commands are.

## What may import `schedule/`

`racing/` (a `Race` points at the `Week` it belongs to, via a string FK —
see `racing/README.md`), `world/` (the tick calls `process_transitions()`),
and `api/` (the position endpoint calls `current_position()`).

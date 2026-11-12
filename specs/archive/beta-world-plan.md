# The beta world: Implementation Plan

**Spec:** `specs/archive/beta-world.md` · **Issue:** #139 · **Status:** implemented
**Apps touched:** `schedule/` (command option), `racing/` (calendar check), `world/` (seed_world, add_season, wipe), `config/settings/`, `seasons/` (new calendar file)

## Context you need

The game's race content is two example season files in `seasons/`, loaded by
`schedule`'s `load_season` command. The command reads the season's `number`
and `starts_at` from the file, creates the season, its twelve weeks and its
races in one transaction, and refuses an overlap or a season that has already
started (`schedule/README.md`, *Declaring a season*).

A world today is built by five commands in a set order (`AGENTS.md`, *Seeding
a world for testing*): `seed_user`, `seed_teams`, `seed_trainers`, then
`load_season` twice. `seed_teams` stamps each team's opening balance and
fanbase, and generates a sponsor offer round only if a season is already
current. Otherwise the tick that opens a season generates it
(`economy/README.md`, *Sponsorship*).

Unmanaged teams pick their squads with `racing.services.course_pick_squad`,
which ranks riders by the course's attribute (`course_training_attribute`)
plus general strength. A 64-rider race takes about 30 seconds to simulate.

Rules this work is bound by: `world/` is the only app (with `api/`) that may
import everything. `racing/adapters.py` is the only importer of
`race_engine`. `schedule/`'s library code may not import `racing/` or
`world/`.

## Goal

- One calendar file, `seasons/world.json`, that any season of a world is
  declared from, re-anchored by number and start date.
- A repeatable check that simulates the calendar against generated fields
  and says whether the four winning specialities each get their races.
- `seed_world` builds a clean world (16 claimable teams, 24 trainers, four
  chained seasons) and never creates a user. With `--reset`, it wipes the
  game world first and keeps accounts, and only where settings allow it.
- `add_season` appends the next season to a running world.

## Design decisions (settled: implement these, do not substitute)

1. **`load_season` gains `--number` and `--starts-at`, and they overwrite the
   parsed JSON *before* `parse_season_file` runs.** That way the overrides go
   through the same Monday-midnight validation as the file's own value. Do
   not validate them separately, because a second check would drift from
   the first.
2. **The calendar check is database-free.** It uses unsaved, generated
   `Rider` rows with synthetic pks, and runs the engine through
   `racing/adapters.py` with no log file. The alternative was a full season
   through the real tick in a rolled-back transaction, which would include
   fatigue and training. It was rejected because it takes about ten minutes
   a season, writes race logs to storage, and couples the check to every
   tick subsystem. The check answers "what does this course reward".
3. **Squads in the check are picked with the game's own ranking.**
   `course_pick_squad` is split into `course_pick_order(riders, course)` over
   a plain list, which the check reuses. Do not copy the scoring, or the
   check stops measuring what unmanaged teams actually field.
4. **A stage race's squad is picked once, for stage 1, in the check too**
   (`Day.pick_course`), which is the rule the game applies. That also makes
   the check's GC meaningful, because the same riders ride every stage.
5. **The check is a management command (`check_calendar`), not a test.** A
   season of 21 race days across three seeds takes roughly 25 minutes on 4
   cores, which is too slow for CI. Its result is recorded in
   `world/README.md` next to the calendar. Unit tests cover the check's
   logic, and the suite checks that the calendar *loads*.
6. **`seed_world` composes the existing seed commands** (`seed_teams`,
   `seed_trainers`, `load_season`) through `call_command`, and does not
   re-implement them. Each domain keeps owning its own seeding.
7. **The wipe is one `TRUNCATE … RESTART IDENTITY CASCADE` over the models of
   an explicit app list** (`WORLD_APPS`), preceded by `SET CONSTRAINTS ALL
   IMMEDIATE`. An ORM delete would have to follow the PROTECT foreign keys
   (race → week, stage → tour) in the right order, and that order goes stale
   with every new model. `accounts` and Django's own apps are not in the
   list. `world.GameClock` is kept. A new game app is **not** wiped until
   someone adds it to the list, which is the safe default. Race log files
   are deleted from storage first.
8. **The wipe is gated on a setting, `ALLOW_WORLD_RESET`**, which is False in
   `base.py`, True in `dev.py`, and must be set True by `staging.py` (#129).
   It is never inferred from `DEBUG` or the settings module's name: staging
   inherits prod and runs with `DEBUG = False`.
9. **`--set-clock` is MockClock-only.** It moves the clock to the start before
   anything is seeded, so opening ledger entries are stamped in game time,
   and ticks once afterwards so season 1 opens with its sponsor rounds.
   Without the flag, nothing touches the clock.
10. **Seeding runs in one transaction.** A broken calendar leaves no
    half-built world behind. The closing tick is outside it.
11. **`seed_world` refuses over an existing world** (any team, trainer or
    season) unless `--reset` is passed. It is not additive the way the
    per-domain seeds are, because a second set of 16 teams is never what
    an operator means.

## Data model

None. No migrations.

## `schedule/management/commands/load_season.py`

`--number INT`, `--starts-at ISO` (a bare date means 00:00 UTC). Both are
applied to `data` before `parse_season_file`.

## `racing/services.py`

`course_pick_order(riders: list[Rider], course: list[dict]) -> list[Rider]`.
`course_pick_squad` calls it.

## `racing/adapters.py`

`to_engine_course_from_json(course, markers) -> Course`.
`run_race_via_adapter`'s `log_path` becomes `str | None`; the engine already
skips logging on `None`.

## `racing/calendar_check.py`, `racing/management/commands/check_calendar.py`

`calendar_days(declaration) -> list[Day]`, `generate_field(seed)`,
`run_day(day, field_seed, race_seed) -> DayResult`,
`check_calendar(declaration, seeds, *, jobs)`, `judge(results) -> Verdict`,
`general_classification(results, tour, seed)`. Workers use the `fork`
context, so they inherit configured Django. The command exits non-zero when
`judge` fails, and `--only` narrows the run to one course while tuning.

## `world/world_setup.py`, `seed_world`, `add_season`

`build_world(*, starts_at, seasons, teams, trainers, calendar, set_clock, reset)`,
`add_season(*, calendar) -> int`, `wipe_world() -> dict[str, int]`,
`next_monday(after)`, `check_season_start(starts_at)`, `WorldError`.

## Work items

### W1: `load_season --number/--starts-at`
Tests: `schedule/tests/test_load_season.py`, the four `override` tests.

### W2: the calendar check
`course_pick_order`, `to_engine_course_from_json`, `calendar_check.py`, and
the command. Tests: `racing/test_calendar_check.py`.

### W3: `seed_world`, `add_season`, the wipe
Tests: `world/tests/test_world_setup.py`.

### W4: `seasons/world.json`
Write the calendar, run `check_calendar --seeds 1,2,3 --jobs 4`, and tune
until it passes (rouleurs need one win a season, the rest two; see the spec's *Decisions taken*). Record the result in `world/README.md`. Test:
`test_the_world_calendar_loads`.

### W5: docs
Update `AGENTS.md`, `world/README.md`, `schedule/README.md` and
`racing/README.md`.

## Documentation update

- `world/README.md`: a new *Building a world* section covering seed_world,
  add_season, the wipe and its setting, and the staging and production
  recipes. Plus *The world calendar*: what each race is for, and the latest
  check result.
- `schedule/README.md`, *Declaring a season*: the two overrides.
- `racing/README.md`: the calendar check, and why it is database-free.
- `AGENTS.md`, *Seeding a world for testing*: point beta and launch worlds
  at `seed_world`, and keep the dev recipe.

## Verification

- Run `seed_world --set-clock` on a mock-clock dev database. The dashboard
  should show 16 claimable teams, the calendar four seasons, and sponsor
  offers present.
- Run `check_calendar seasons/world.json --seeds 1,2,3 --jobs 4`. It should
  print `balanced`.
- The likeliest failure is the wipe missing a table that is later added
  with a FK to a wiped one. TRUNCATE CASCADE takes such a table with it,
  which is the right outcome for game data, and the reason the app list is
  explicit.

## Risks

| Risk | Mitigation |
|---|---|
| The check passes on fresh fields but a real season drifts (fatigue, training) | Stated in the README. Staging is the real check, and the agents report it. |
| Engine nondeterminism (`race_engine/README.md`, *Regression audit*) shifts single results | The rule is judged across three seeds, and the margin is recorded. |
| `--reset` run against production | `ALLOW_WORLD_RESET` is never set in `prod.py`, and the default is off. |

## Open questions

None.

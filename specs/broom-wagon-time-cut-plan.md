# Broom wagon (time-cut DNF) — Implementation Plan

**Spec:** `specs/broom-wagon-time-cut.md` · **Issue:** #102 · **Status:** proposed
**Apps touched:** `race_engine/`, `racing/`, `world/` (no model changes, no migrations; `frontend/`, `api/` and `race_player/` verified unchanged)

## Context you need

**The engine never gives up on a rider.** `race_engine.models.run_race` loops
`while not state.is_finished(): state.tick()`, and `is_finished()` is
`all(rs.finished for rs in rider_states)`. A rider who cracks alone has no
route back to equilibrium (`race_engine/README.md`, *Known limitation*), so
on a 64-rider, 200 km race the last rider can take ~1.9× the winner's time,
and every one of those extra ticks costs wall-clock time and log samples for
the whole race. In-game fields are already 64 riders (16 seeded teams ×
`racing.models.SQUAD_SIZE = 4`), and `seasons/season-1.example.json` has four
210–230 km races. That is the shape that breaks.

**Downstream, "did not finish" already exists but has never happened.**
`racing.models.RaceResult.finish_time` is nullable; `racing.services.simulate_race`
sorts `finish_time is None` to the back and still numbers those riders
(`racing/README.md`); `competitions/` filters `finish_time__isnull=False`
before points and prizes; the API returns `finished = finish_time is not None`
(`api/views.py`); and `frontend/src/screens/Race.tsx` already renders `—`
and `DNF`. All of it is dormant today, because the engine always runs every
rider to the line.

**"Raced" currently means "finished", in three places.**
- `simulate_race` charges `RACE_FRESHNESS_COST` only to finishers
  (`riders.services.apply_race_cost(finisher_ids)`).
- `racing.services.riders_who_raced(week)` returns finishers only. It feeds
  training credit.
- `world.services._apply_training_week` excludes `set(riders_who_raced(...))`
  from weekly recovery.

The spec splits the definition. A cut rider is charged fatigue and skips
recovery like a finisher, but gets no training.

**Rules this work is bound by.**
- `race_engine/` imports nothing from Django.
- Only `racing/adapters.py` imports the engine.
- `riders/` may not import `racing/` or `world/`, which is why the recovery
  exclusion is computed in `world/`.
- Engine changes are validated with `race_engine/audit.py`: save a baseline
  before the change and diff it after (`race_engine/README.md`,
  *Regression audit*).

## Goal

1. Once the first rider finishes, the engine fixes a time limit:
   `ceil(winner_time × (1 + TIME_CUT_MARGIN))`. The same margin applies to
   every race.
2. When race time reaches the limit, every rider not yet across the line is
   marked DNF and the race ends. Nobody is simulated past the limit.
3. Engine results and `RaceResult.position` list finishers by time, then
   DNF riders furthest-travelled first.
4. A DNF rider is charged the race's freshness cost and skips that week's
   recovery. They get no training credit, no points and no prize.
5. A race in which nobody is cut is bit-for-bit identical to today.

## Design decisions (settled — implement these, do not substitute)

1. **The cut lives in `RaceState.tick()`, not in `run_race`.** Two loops drive
   the engine: `run_race` and `audit._run_one`. Putting the rule in the tick
   means both loops, and any future loop, obey it. Do **not** add a check to
   the `while` loop in `run_race`, or the audit would silently keep measuring
   the old unbounded behaviour.

2. **A new `RiderState.dnf: bool = False`. Do not reuse `finished`.**
   `finished` means "crossed the line" everywhere: logger flag bit 4,
   `race_player`'s ✅, the audit's winner lookup, and eight skip checks inside
   `tick()`. Setting `finished=True` with `finish_time=None` would make a cut
   rider look like a finisher to every one of those.

3. **The limit is computed once, from the winner's actual finish time,**
   stored as `RaceState.time_limit: int | None = None`, with
   `math.ceil(winner_time * (1 + TIME_CUT_MARGIN))`. `ceil` makes it
   generous: a rider finishing on the limit's own tick is a finisher.
   Do not recompute it later from a changing reference.

4. **The cut happens at the end of phase 2 of the tick in which
   `current_time >= time_limit`, before `current_time += 1`.** Riders who
   cross the line during that tick get `finish_time == current_time` and are
   finishers. Everyone else still racing becomes DNF. The rule is therefore
   exactly "finisher iff `finish_time <= time_limit`". **This ordering is
   load-bearing.** Cutting before phase 2 would DNF a rider who reaches the
   line on the limit tick. Cutting after the increment is off by one.

5. **A race with any DNF rider is over. Do not add `or rs.dnf` to the skip
   checks in `tick()`.** `is_finished()` becomes
   `all(rs.finished or rs.dnf ...)`. The cut marks *every* remaining rider in
   one tick, so no caller ever ticks a race that has a DNF rider in it.
   Sprinkling `dnf` through eight code paths adds risk and protects against
   nothing.

6. **`TIME_CUT_MARGIN = 0.25` in `race_engine/formulas.py`, with the other
   constants.** A clean race spreads the field over 5–10% of the winner's
   time; the death spiral reaches ~90%. 25% sits well clear of both. It is
   one constant with no dependence on course, terrain or field size
   (spec: *Decisions taken*). The value is checked, not tuned, in
   Verification: no bundled config at any seed may lose a rider. If one
   does, raise the margin; never lower it below 2× the worst clean spread
   observed. Import it **inside** `tick()`, the way `tick()` imports every
   other constant, so tests can `monkeypatch.setattr("race_engine.formulas.TIME_CUT_MARGIN", ...)`.

7. **DNF riders are ordered furthest first, at both sorting sites.**
   `RaceState.get_results()` and the `finishers = sorted(...)` in
   `racing.services.simulate_race` both use the key
   `(finish_time is None, finish_time or 0, -position)`. `racing` keeps its
   own sort because it owns `RaceResult.position`. The new engine key also
   fixes the latent bug where the current `rs.finish_time or float("inf")`
   treats a finish at t=0 as never finishing.

8. **No database change.** `RaceResult.finish_time IS NULL` already means DNF.
   Do not add a `dnf` or `distance` field to `RaceResult`: furthest-first is
   recorded in `position` at write time, and nothing reads distance
   afterwards.

9. **Freshness charges every starter; recovery excludes every starter;
   training stays finishers-only.**
   - `simulate_race` calls `apply_race_cost` with every rider in the race's
     states.
   - A new reader, `racing.services.riders_who_started(week) -> set[int]`,
     returns every `RaceResult.rider_id` in the week's races.
   - `world` passes that set to `apply_weekly_recovery(exclude_ids=...)`.
   - `riders_who_raced` is **not** changed. It is the training reader, and
     the spec says a cut rider learns nothing.
   - Do not widen `riders_who_raced` and filter finishers back out in
     `world`: that couples training to a detail it should not see.

10. **The log gets flag bit `8` for DNF, and the cut tick is always sampled.**
    `RaceLogger.log` currently forces a sample only when the `finished`
    tuple changes. The cut tick changes no `finished` flag, so on an
    off-grid tick the final state, and so the DNF, would never be written.
    Track `(finished, dnf)` pairs for change detection instead.
    `FORMAT_VERSION` stays `1`: the bit is additive, old logs never carry
    it, and `race_player`'s parser tests bits individually, so it ignores
    an unknown one. Race logs are authoritative records, so the DNF must be
    in the record even though nothing renders it yet.

11. **`race_player/`, `api/` and `frontend/` do not change.** The API already
    returns `finished: false`, and the results screen already shows `—` /
    `DNF` (covered by `Race.test.tsx`). In the player, a DNF rider freezes
    where they were cut, with no result. Rendering that belongs to #94
    (watch a finished race), per the spec's *Out of scope*.

12. **The audit gains a large-field config, `race_engine/configs/grand_field.json`
    (new): the in-game shape.** It has 64 riders (the 16 in `_roster.json`
    replicated 4×, as teams `t1`–`t16`, one leader each) on Lombardia's
    course with every segment length doubled (200 km). It gets **no**
    `EXPECTED_ARCHETYPE` entry; it exists to cover the tail, not to assert a
    winner. `--tick-cap` stays, because it still guards a race in which
    nobody ever finishes, which the time limit cannot catch.

## Data model

No Django model or migration changes.

Engine dataclasses (`race_engine/models.py`):

| Class | Field | Type | Default | Meaning |
|---|---|---|---|---|
| `RiderState` | `dnf` | `bool` | `False` | Cut by the time limit. Mutually exclusive with `finished`. When `True`, `finish_time` is `None`. |
| `RaceState` | `time_limit` | `int \| None` | `None` | Race second at which the finish closes. `None` until the first rider finishes, then fixed. |

Constant (`race_engine/formulas.py`): `TIME_CUT_MARGIN = 0.25`, a fraction of
the winner's time.

## race_engine/formulas.py

Add `TIME_CUT_MARGIN = 0.25` with a one-line comment: the fraction of the
winner's time after which the finish closes (see `race_engine/README.md`).

## race_engine/models.py

- `RiderState.dnf: bool = False`, after `finish_time`.
- `RaceState.time_limit: int | None = None`, after `wind_rng`.
- Add `import math` at module scope (not imported today).
- `tick()`: add `TIME_CUT_MARGIN` to the in-function import. After the
  phase-2 loop and **before** `self.current_time += 1`:

```python
if self.time_limit is None:
    finish_times = [rs.finish_time for rs in self.rider_states if rs.finished]
    if finish_times:
        self.time_limit = math.ceil(min(finish_times) * (1 + TIME_CUT_MARGIN))
if self.time_limit is not None and self.current_time >= self.time_limit:
    for rs in self.rider_states:
        if not rs.finished:
            rs.dnf = True
```

  The limit is set and can be reached in the same tick when the winner's
  time is 0 or the margin is 0. The code above handles both. Keep it that
  way; do not turn the second `if` into an `elif`.
- `is_finished()` returns `all(rs.finished or rs.dnf for rs in self.rider_states)`.
- `get_results()` sorts with the key
  `(rs.finish_time is None, rs.finish_time or 0, -rs.position)`.
- `run_race` needs no change.

## race_engine/race_logger.py

- `_last_finished` becomes `_last_status: tuple[tuple[bool, bool], ...] | None`,
  built as `tuple((rs.finished, rs.dnf) for rs in state.rider_states)`.
  "Changed" compares that tuple.
- The flags expression gains `| (8 if rs.dnf else 0)`.
- Update the class docstring: a sample is also forced on any tick where a
  rider's DNF status changes.

## race_engine/audit.py

- `_run_one` needs no logic change. `dnf_riders = [... if not rs.finished]`
  already catches cut riders, and `_time_of` uses `state.current_time` for
  them, which is now the limit tick.
- `_summarize` adds `"total_dnf": sum(len(r.dnf_riders) for r in runs)`.
- `_print_report` prints `  time-cut DNFs: {n}` when `total_dnf > 0`.
- `RunResult` is unchanged, so old `--json` baselines still load through
  `RunResult(**r)`. **Do not add a field to `RunResult` without a default**,
  or `--baseline` against a pre-change file breaks.

## race_engine/configs/grand_field.json (new)

Generate it once with a throwaway script in the scratchpad, not committed:

- Riders: `_roster.json`'s 16 riders, 4 copies (k = 0..3). Id
  `f"{id}_{k}"`, so `gc1_0`, and `_archetype`'s prefix match still works.
  Team `f"t{int(team[1:]) + 4*k}"`, so `t1`–`t16`. Role unchanged, so each
  new team keeps exactly one leader. Names get a ` {k+1}` suffix.
- Course: `lombardia.json`'s segments with every `length` doubled (100 km →
  200 km).
- `teams`: 16 entries, each with a unique 3-uppercase-letter code and a
  non-empty name. `load_config` rejects duplicate codes.
- `name`: `"Grand field (64 riders, 200 km)"`.

## racing/services.py

- `simulate_race`: the `finishers` sort key becomes
  `(s.finish_time is None, s.finish_time or 0, -s.position)`, and the
  variable is renamed `ordered`. `apply_race_cost` receives
  `[by_pk[s.rider.id].pk for s in states]`, every starter. Rewrite the
  comment above it to say starters pay, including a rider cut by the time
  limit (spec, In scope 5).
- New function:

```python
def riders_who_started(week) -> set[int]:
    """Every rider with a RaceResult in `week`'s races, finisher or not."""
```

  One `values_list("rider_id", flat=True)` query over
  `RaceResult.objects.filter(race__week=week)`.
- `riders_who_raced`: code unchanged. Amend its docstring to say it is the
  *training* reader and that `riders_who_started` is the fatigue one.

## world/services.py

In `_apply_training_week`:

```python
started = riders_who_started(raced_week) if raced_week is not None else set()
...
apply_weekly_recovery(exclude_ids=started)
```

Import `riders_who_started` alongside `riders_who_raced`. Update the comment
above the call, and the docstring's "excluding riders who raced" line, to say
"started".

## Work items

### W1 — race_engine/formulas.py, race_engine/models.py: the time cut ✅ done
Add the constant, the two dataclass fields, the tick block, `is_finished`
and the `get_results` key, exactly as above. New test file
`race_engine/test_time_cut.py`. Use `RaceState.create_initial_state(...,
wind=False, seed=1)` and tick until `is_finished()`. Place riders by setting
`rider_states[i].position` before the first tick. Two riders with no team,
one 10 km flat segment.
- `test_time_limit_is_unset_until_someone_finishes`: after a few ticks with
  nobody across, `time_limit is None`.
- `test_time_limit_is_ceil_of_winner_time_times_margin`: once the first
  rider finishes at W, `time_limit == ceil(W * 1.25)`.
- `test_rider_outside_time_limit_is_dnf_and_race_ends_at_the_limit`: rider A
  starts at 6000 m and rider B at 0. B is `dnf`, not `finished`, with
  `finish_time is None`, and the race ends with
  `current_time == time_limit + 1`.
- `test_rider_inside_time_limit_finishes`: same setup with the margin
  monkeypatched to `10.0`. Both finish and no one is `dnf`.
- `test_rider_crossing_on_the_limit_tick_is_a_finisher`: pin the boundary.
  Monkeypatch the margin so the limit lands on the tick B crosses. Find that
  tick from a first, uncut run with the same seed, then compute the margin
  as `(B_time / A_time) - 1`. B finishes with `finish_time == time_limit`.
  **This test is the one that proves Design decision 4.**
- `test_results_list_dnfs_furthest_first`: three riders, two of them cut at
  different positions. `get_results()` returns the winner, then the rider
  further along, then the other.

### W2 — race_engine/race_logger.py: DNF flag and forced sample
Make the change as specified. Tests go in `race_engine/test_race_logger.py`,
following the style of `test_flags_pack_into_a_bitfield` and
`test_finish_off_the_sample_grid_is_still_written`:
- `test_dnf_sets_flag_bit_eight`
- `test_dnf_off_the_sample_grid_is_still_written`: a state whose DNF flips
  on an off-grid tick still produces a sample for that tick.

### W3 — race_engine/audit.py, race_engine/configs/grand_field.json: large-field coverage
Add the summary field and print line, and generate the config. Test in
`race_engine/test_config.py`:
`test_grand_field_config_loads_sixty_four_riders_in_sixteen_teams`. It
asserts `load_config` succeeds (which also validates one leader per team
and unique codes), that there are 64 riders and 16 distinct team ids, and
that the course is 200 km.

### W4 — racing/services.py: starters pay, DNFs ordered, starters reader
Make the three changes as specified, with tests in `racing/tests.py`:
- Replace `test_simulate_race_does_not_deduct_from_non_finishers` with
  `test_simulate_race_deducts_freshness_from_non_finishers`. Same
  fake-adapter seam, and the `SimpleNamespace` states gain `position`. The
  non-finisher ends at `100 - 25`. Rewrite the comment: the engine now
  produces non-finishers, and the seam just makes one deterministic.
- `test_simulate_race_orders_non_finishers_furthest_first`: fake states
  with two `finish_time=None` riders at positions 3000 and 8000. The
  8000 m rider gets the lower `RaceResult.position`.
- `test_riders_who_started_includes_non_finishers`: `RaceResult` rows with
  and without `finish_time` in a week. Both rider ids are returned, and a
  race in another week is excluded.
- Extend `test_riders_who_raced_groups_by_rider`, or add a sibling test, so
  that a `finish_time=None` row in the same week is **absent** from
  `riders_who_raced`. This guards training staying finishers-only.

### W5 — world/services.py: recovery excludes starters
Make the change as specified. Test in `world/tests/test_services.py`:
`test_tick_does_not_recover_a_rider_who_did_not_finish`. Build it on
`test_tick_does_not_recover_a_rider_who_raced_that_week`, but instead of
running the race, create the week-one `Race` as `FINISHED` with a
`RaceResult(finish_time=None)` for the rider. Tick into week two and assert
the rider's freshness is unchanged, while a resting rider recovers.

### W6 — Documentation
See *Documentation update*. Commit it on its own.

## Execution order

0. **Before touching code**, from the worktree root:

   ```bash
   .venv/bin/python -m race_engine.audit --jobs 4 --json /tmp/claude-1000/before.json
   ```

   This covers the six bundled configs (`grand_field` does not exist yet).
   Use your scratchpad for the file. `audit_baseline.json` is not tracked.
1. **W1.** Run the full suite, then the audit with
   `--baseline <before.json>`. Every one of the six configs must show a
   **zero** delta and no DNFs (Goal 5). If any moves, a clean race was cut:
   stop, raise the margin, and record the observed spread in the commit
   message. Commit.
2. **W2**, commit. It depends on W1's `dnf` field.
3. **W3**, commit. Then run the audit on `grand_field` alone (see
   Verification) and record the numbers in the W6 README update.
4. **W4**, commit. It is independent of W2 and W3, but must come after W1
   because the new tests assume the engine can produce DNFs.
5. **W5**, commit. It uses W4's `riders_who_started`.
6. **W6**, commit, push.

Each item leaves the suite green. W1 is the only one that can move race
results, which is why its audit check comes before anything is layered on
it.

## Documentation update (required, not optional)

- **`race_engine/README.md`**
  - *Known limitation*: replace the "no longer observed" paragraph. The
    mechanism is still there, but it is now bounded by the time cut.
    Include the numbers: winner vs last finisher at 32 riders / 200 km,
    before and after.
  - *Data model*: add `RiderState.dnf` and `RaceState.time_limit`.
  - *Simulation tick*: add a step after phase 2 covering the time limit
    and the cut, including the "finisher iff `finish_time <= time_limit`"
    rule.
  - *Output format*: flags bit `8` = DNF, and the forced sample on a DNF
    change.
  - *Regression audit*: `grand_field` and why it carries no expected
    archetype, plus the new DNF line. Warn that it is the slow config, and
    that `--configs` can exclude it.
  - *Realism status*: the `grand_field` row.
  - *Future work*: delete *Broom wagon*, which is now built. Keep *Autobus*,
    noting the time cut now exists and the autobus is the mechanism-level
    follow-up.
  - `get_results`: document the new ordering.
- **`racing/README.md`**: in the `RaceResult.position` paragraph, say that
  non-finishers are now real (cut by the time limit) and are numbered
  furthest-travelled first. Add a line on `riders_who_started` vs
  `riders_who_raced` next to the weekly-training readers.
- **`riders/README.md`**, *Freshness*: the cost is charged to every rider who
  **started**, finisher or cut, and recovery excludes every starter.
- **`world/README.md`**: line ~123, recovery excludes riders who *started* a
  race that week, via `riders_who_started`.
- **`race_player/README.md`**: the flags list gains `8` DNF, currently
  ignored by the player; rendering is left to #94.
- **Specs**: set `Status: implemented` on the spec and this plan and move
  both to `specs/archive/`, per `AGENTS.md`.

## Verification

1. **Unit suite:** `.venv/bin/python -m pytest`, which must be green, and
   `cd frontend && npm test -- Race`, unchanged and green, because the DNF
   rendering is already covered.
2. **No clean race is cut, the likeliest failure.** Run
   `.venv/bin/python -m race_engine.audit --jobs 4 --baseline <before.json>`.
   The six configs must show zero delta and no `time-cut DNFs` line. This
   is the evidence for Goal 5, and it could fail: a margin that is too
   tight shows up here as DNFs and a shifted `avg 1st-last gap`.
3. **The spiral is bounded.** Run
   `.venv/bin/python -m race_engine.audit --configs grand_field --jobs 5`.
   For every seed, `last_over_winner_ratio <= 1.25` (in `--json` output),
   and no tick-cap warning. Then reproduce the issue's spike: a 32-rider
   version (roster ×2) of the same 200 km course, built as a scratch config
   and passed by path, seed as in the issue. Before the change the last
   rider arrived at ~1.87× the winner; after it, the race must end by
   1.25×, with the stragglers DNF. Record ticks before and after. That is
   the performance claim.
4. **End to end in-game.** Seed a world as `AGENTS.md` describes, set the
   mock clock through week 3 (*Long Haul*, 210 km, 64 riders), and `tick`.
   On `/races/<id>` any DNF rider shows `—` / `DNF` and sits below every
   finisher. In the shell, a DNF rider's `freshness` dropped by 25, and
   after the next week's tick it did not recover. The race may produce no
   DNF, which is the expected outcome; in that case steps 1–3 are the
   evidence, and this step only proves nothing regressed.

## Risks

| Risk | Mitigation |
|---|---|
| The cut is applied before phase 2 or after the increment (off by one), DNFing a rider who crossed on the limit tick. | Design decision 4, with real code; `test_rider_crossing_on_the_limit_tick_is_a_finisher` pins it. |
| The implementer adds `or rs.dnf` throughout `tick()` "to be safe". | Design decision 5. The race ends on the cut tick, and the audit zero-delta check catches any behaviour change. |
| The margin is too tight for real in-game fields, which include riders at 0.80 freshness, so ordinary back-markers get cut. | The 25% margin is ~2.5× the clean spread. The `grand_field` audit plus the in-game Long Haul check are the evidence. Raise the margin, never lower it, if a clean run loses anyone. |
| The cut tick is not sampled, so the log ends without the DNF. | Design decision 10; `test_dnf_off_the_sample_grid_is_still_written`. |
| Training accidentally widens to starters. | `riders_who_raced` is untouched, and W4's absence test guards it. |
| `grand_field` makes the default audit slow (roughly 64² pack work × 2× ticks). | Documented, with `--configs` to exclude it. `--jobs` parallelises it. It never runs in pytest. |
| A runaway solo winner cuts most of the field. | Accepted by the spec (*Out of scope*: no reinstatement). The 25% margin makes it effectively unreachable. Do not add a reinstatement rule. |

## Open questions

None.

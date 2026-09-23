# Slim and compress the race log format — Implementation Plan

**Spec:** `specs/slim-race-log-format.md` · **Issue:** [#88](https://github.com/mario595/cycling-manager/issues/88) · **Status:** proposed
**Apps touched:** `race_engine/`, `racing/`, `race_player/`

## Context you need

A race log is a JSONL file written by `race_engine/race_logger.py`. Today every
line is a complete snapshot of the race at one second: the course segments, the
team map, and for every rider their id, name, team, role and full state. Nothing
is compressed. A mountain stage is 75.7 MB across 18,961 lines for 16 riders.

Two things write and read it:

- **`race_engine/race_logger.py`** — `RaceLogger.log(state)`, called by
  `run_race` once before the first tick and once after every tick
  (`race_engine/models.py:868-883`). The engine writes with a raw `open()` and
  **may never import Django** (`AGENTS.md`; `racing/README.md`, *The core rule*).
- **`race_player/src/utils/parseRaceLog.ts`** — splits on newlines, `JSON.parse`s
  each line into a `RaceSnapshot`, and reads `segments`/`course_length`/`teams`
  from `snapshots[0]`. It is the only parser; `App.tsx` is the only caller.

`racing/services.py:280-305` bridges them: the engine writes into a
`TemporaryDirectory`, then `simulate_race` hands the finished file to Django
storage as a `ContentFile` and records `RaceLog.tick_count` / `size_bytes`.
Logs never bypass the storage API — that is what keeps a move to object storage
a settings change.

**Nothing serves logs over HTTP yet.** There is no log endpoint in `api/`
(checked: `api/views.py`, `api/urls.py`, `api/README.md`). The only consumer is
the standalone player reading `race_player/public/*.jsonl` via Vite's dev server
or `race_player/scripts/serve_viewer.py`. That is why this plan changes no
Django view: the serving decision in the spec is about how the file is stored
and labelled, so that whoever adds that endpoint later has nothing to invent.

**Things this work is bound by:**

- `race_engine/` imports nothing from Django. The logger is engine code.
- Race logs are authoritative records, never regenerated from a seed
  (`racing/README.md`, *Rejected: regenerating logs from a seed*).
- Tests are pytest (`.venv/bin/python -m pytest`) plus vitest in
  `race_player/` (`npm run test`).
- There are six sample logs in `race_player/public/`. They are gitignored
  generated files, not source.

## Goal

When this is done:

1. A simulated mountain stage's stored log is under 2 MB, from 75.7 MB.
2. The log is one header line followed by sampled tick lines, each rider's
   changing state a positional array.
3. Ticks are recorded every 2 seconds; every rider's `finish_time` is still the
   exact float the simulation computed.
4. The file is stored brotli-compressed.
5. `race_player` parses only the new format. The old format has no reader.
6. The player's race-time readout, seek and playback still report real race
   seconds, read from the header rather than assumed.

## Design decisions (settled — implement these, do not substitute)

**1. One header line, then tick lines. Still JSONL.**
Line 1 is a header object; every later line is one sampled tick. Do **not**
switch to a single JSON document or a columnar layout — a columnar file measured
0.38 MB smaller but stops being line-readable and forces the player to transpose
the whole race before it can draw one tick. JSONL keeps the writer streaming and
the reader incremental.

**2. Per-tick rider state is a positional array, not an object.**
`[pos, speed, energy, stamina, flags, finish_time]`. Riders appear in the same
order as `header.riders`, every tick, with no exceptions — **this is
load-bearing**: the array index *is* the rider identity. The logger must iterate
`state.rider_states` in a stable order and the header must be built from that
same list.

Measured: header hoist alone took 75.7 MB → 39.6 MB raw / 2.80 MB gzipped.
Adding positional arrays and rounding took it to 11.3 MB raw / 1.53 MB. The
arrays are the larger half of the win, which is why they are not optional.

**3. `pulling`, `surging` and `finished` pack into one integer.**
Bit 0 `pulling`, bit 1 `surging`, bit 2 `finished`. Three JSON booleans cost
~20 bytes a rider a tick; one small int costs 1–2. Do not use three separate
`0`/`1` fields — same idea, three times the separators.

**4. Rounding: `pos` 1dp, `speed` 2dp, `energy`/`stamina` 1dp.**
0.1 m on a 116 km course is far below one screen pixel; energy bars render to
whole percent. `finish_time` is **not** rounded — see decision 6.

**5. The logger samples; `run_race` does not.**
`RaceLogger.__init__` takes `sample_interval: int = 2`. `log(state)` is still
called every tick by `run_race` (`race_engine/models.py:879-883`, unchanged) and
the logger decides whether to write. It always writes the first tick and always
writes a tick in which any rider's `finished` flag changed since the last
written tick — so a finish is never invisible, only its exact instant is
quantised. Do **not** move sampling into `run_race`'s loop: that puts a
presentation concern in the simulation and makes it easy to drop the final tick.

**6. `finish_time` stays the exact float the engine computed.**
Never snapped to the sample grid. The spec forbids it: snapping would
manufacture ties in a bunch sprint that did not happen and contradict
`RaceResult.finish_time`, which `competitions/` scores from. **Load-bearing.**

**7. The header states `tick_interval`. The player never assumes it.**
`maxTicks` is a count of samples; race seconds are `sampleIndex *
tick_interval`. `PlaybackControls.formatDuration` currently takes ticks and
treats them as seconds (`race_player/src/components/PlaybackControls.tsx:20-24`)
— it must take seconds, with the caller converting. The playback loop's interval
becomes `(1000 * tick_interval) / speed` so x1 stays real time
(`RaceViz.tsx:27-38`).

**8. Wind stays per-tick; only `band` moves to the header.**
`advance_wind` mutates `speed` and `angle` every tick
(`race_engine/models.py:262-266`), and `WindCompass` is documented to breathe
with the live value (`race_player/README.md`, §5). `band` is constant for the
race. Per-tick wind becomes a two-element array `[speed, angle]`, omitted
entirely when wind is disabled — matching today's "absent means absent".

**9. Brotli, written by the logger, stored compressed.**
`race_engine/race_logger.py` writes through `brotli`. Quality 5: 1.38 MB, and
encode time indistinguishable from gzip's (measured 0.3 s vs 0.4 s on the
9.7 MB slimmed payload). Quality 11 reaches 1.04 MB but costs 23 s per race —
the spec defers it. Add `brotli>=1.1` to `requirements.txt`.

The file keeps a `.jsonl.br` extension. **Do not** also gzip it, and do not
decompress server-side.

**10. Optional rider fields become required.**
`team` and `role` are `Rider?` fields in `race_player/src/types/race.ts` purely
because pre-team logs existed. With one format they are always present:
make them required, and delete the fallbacks in `teamColors.ts` — `teamColor()`'s
`if (!team)` branch and `isLeader()`'s `role !== 'support'` default. Keep
`NEUTRAL_TEAM_COLOR` for a rider genuinely on no team (the engine still allows
`team_id=None`; `adapters.to_engine_rider` passes `None` for a teamless rider).

**11. `RaceLog.tick_count` is renamed `sample_count`.**
It no longer counts race seconds and must not be read as though it does
(`racing/admin.py:14`, `racing/tests.py:139`). `size_bytes` keeps its name and
now records compressed bytes — add a new `tick_interval` field so the pair is
interpretable. No backwards compatibility: the game is not deployed.

## Data model

One migration, `racing/migrations/0006_racelog_sampling.py`:

| Model | Field | Type | Null | Default | Notes |
|---|---|---|---|---|---|
| `RaceLog` | `tick_count` → `sample_count` | `PositiveIntegerField` | no | `0` | `RenameField`. Count of written samples, not race seconds. |
| `RaceLog` | `tick_interval` | `PositiveSmallIntegerField` | no | `2` | Race seconds between samples. Mirrors the header so admin can read a log without opening it. |
| `RaceLog` | `size_bytes` | `PositiveBigIntegerField` | no | `0` | Unchanged name; now compressed size. Update `help_text`. |

No other model changes. `RaceResult.finish_time` is untouched — decision 6.

## The log format

**Line 1 — header:**

```json
{"v":1,"tick_interval":2,"course_length":116000.0,
 "segments":[{"length":30000.0,"gradient":1.0}],
 "teams":{"t1":{"code":"ALP","name":"Alpine Racing","colour":"#1d56c9","secondary":"#ffffff"}},
 "riders":[{"id":"gc1","name":"GC Climber 1","team":"t1","role":"leader"}],
 "wind_band":"moderate"}
```

`v` is a format version so a future change (e.g. [#70](https://github.com/mario595/cycling-manager/issues/70)'s course markers) can be
detected rather than mis-parsed. `wind_band` is omitted when wind is disabled.
`teams` is `{}` when no teams are configured, as today.

**Every later line — one sample:**

```json
[1246.0,[[8420.5,11.62,87.4,91.2,1,null],[8418.2,11.60,86.9,90.8,0,null]],[17.3,214.6]]
```

`[time, riders, wind?]`. `time` is race seconds (not the sample index — keep it
explicit so a reader never has to multiply). Each rider is
`[pos, speed, energy, stamina, flags, finish_time]` in header order. The wind
element is absent when wind is disabled.

## race_engine/race_logger.py

Rewritten. `RaceLogger` gains a header, sampling and compression:

```python
FORMAT_VERSION = 1
DEFAULT_SAMPLE_INTERVAL = 2
BROTLI_QUALITY = 5

class RaceLogger:
    def __init__(
        self,
        path: str,
        team_codes: dict[str, dict[str, str]] | None = None,
        sample_interval: int = DEFAULT_SAMPLE_INTERVAL,
    ) -> None: ...

    def log(self, state: RaceState) -> None:
        """Write a sample if this tick is due, the first tick, or a tick in
        which any rider's finished flag changed. Otherwise do nothing."""

    def close(self) -> None: ...

    @property
    def sample_count(self) -> int: ...
```

The header is written lazily on the first `log()` call, because the rider list
and wind band are only knowable from a `RaceState`.

The finish-flag check is the subtle part — get it wrong and a rider appears to
finish up to two seconds late *and* the pack view loses them:

```python
    def log(self, state: RaceState) -> None:
        if self._header_written is False:
            self._write_header(state)

        finished = tuple(rs.finished for rs in state.rider_states)
        due = self._ticks_seen % self._sample_interval == 0
        changed = finished != self._last_finished
        self._ticks_seen += 1

        if not (due or changed or self._last_finished is None):
            return

        self._last_finished = finished
        self._write_sample(state)
```

Compression is a `brotli.Compressor` fed incrementally so a 9.7 MB payload is
never held twice in memory:

```python
        self._raw = open(path, "wb")
        self._compressor = brotli.Compressor(quality=BROTLI_QUALITY)

    def _emit(self, line: str) -> None:
        chunk = self._compressor.process(line.encode())
        if chunk:
            self._raw.write(chunk)

    def close(self) -> None:
        self._raw.write(self._compressor.finish())
        self._raw.close()
```

Drop the `self._file.flush()` that exists today — it flushed every line and is
meaningless against a compressor.

## racing/services.py

In `simulate_race` (lines 280-305), three changes:

- The temp file becomes `race-{race.pk}.jsonl.br`, and the saved `ContentFile`
  takes the same name so `FileField` stores the right extension.
- `tick_count = sum(1 for _ in log_path.open())` **must go** — the file is now
  binary and line-counting it is both wrong and wasteful. Read the count from
  the logger instead. `run_race_via_adapter` currently returns only
  `list[RiderState]`; extend it to return `(states, sample_count)` so the count
  crosses the seam without `racing/` importing the engine.
- `RaceLog.objects.update_or_create` writes `sample_count`, `tick_interval` and
  the compressed `size_bytes`.

## racing/adapters.py

`run_race_via_adapter` returns `tuple[list[RiderState], int]`. `run_race` must
hand back the logger's `sample_count`; give `race_engine.models.run_race` an
optional out-parameter or return the logger — simplest is for `run_race` to
return `(states, logger.sample_count if logger else 0)` and for the adapter to
pass it straight through. Update the docstring: the adapter is still the only
importer of the engine.

## race_player/src/types/race.ts

`RaceSnapshot` is replaced. Add `RaceHeader` and `RaceSample`; `Rider` becomes
the decoded shape the components already consume — **decode into today's object
shape in the parser**, so no component changes except the two tick-to-seconds
call sites. That keeps this change small and reviewable.

```ts
export interface RaceHeader {
  v: number
  tick_interval: number
  course_length: number
  segments: Segment[]
  teams: Record<string, { code: string; name: string }>
  riders: { id: string; name: string; team: string | null; role: 'leader' | 'support' }[]
  wind_band?: WindBand
}

export interface Rider {
  id: string
  name: string
  team: string | null      // was `team?: string`
  role: 'leader' | 'support'  // was optional
  pos: number
  speed: number
  energy: number
  stamina: number
  pulling: boolean
  surging: boolean
  finished: boolean
  finish_time: number | null
}

export interface ParsedRace {
  snapshots: RaceSnapshot[]
  profile: ProfilePoint[]
  courseLength: number
  maxTicks: number          // sample count - 1
  tickInterval: number      // NEW: race seconds per sample
  teamCodes: Record<string, string>
  teamNames: Record<string, string>
}
```

## race_player/src/utils/parseRaceLog.ts

Parses line 1 as the header, then decodes each sample back into a
`RaceSnapshot` with full rider objects, merging the header's identity fields
with the sample's state. Throws on a missing or wrong-version header rather than
guessing — a file that is not this format must fail loudly.

```ts
const FLAG_PULLING = 1, FLAG_SURGING = 2, FLAG_FINISHED = 4
```

Reject `header.v !== 1` with a clear error naming the version found.

## race_player/src/components/PlaybackControls.tsx

`formatDuration` takes **seconds**, not ticks. The two call sites (line 84)
become `formatDuration(tick * tickInterval)` and
`formatDuration(maxTicks * tickInterval)`. The raw `tick {tick} / {maxTicks}`
readout on line 85 stays as-is — it is a debug affordance and samples are the
honest unit there. Add `tickInterval: number` to `PlaybackControlsProps`.

## race_player/src/components/RaceViz.tsx

The playback interval becomes `(1000 * tickInterval) / speed` (line 36), so x1
playback remains real time. Pass `tickInterval` down to `PlaybackControls`.

## race_player/src/utils/teamColors.ts

Delete the pre-format fallbacks per decision 10. `isLeader(rider)` becomes
`rider.role === 'leader'`. `teamColor(team: string | null)` keeps its
`NEUTRAL_TEAM_COLOR` branch for a genuinely teamless rider.

## Work items

### W1 — `race_engine/race_logger.py`: header, sampling, positional samples ✅
Rewrite `RaceLogger` per decisions 1-5, 7, 8. **Not yet compressed** — write
plain text, so this item is verifiable by reading the file. `sample_interval`
defaults to 2; `sample_count` property added.
**Load-bearing:** rider order in samples must match `header.riders` exactly.
**Tests** (`race_engine/test_race_logger.py`, rewritten): header carries
segments/teams/riders/tick_interval once; a 10-tick race at interval 2 writes 6
lines not 11; sample rider arrays are in header order; flags pack and unpack;
`finish_time` is unrounded; a tick where a rider finishes is always written even
off the sample grid; `wind_band` in header and `[speed, angle]` per tick;
wind keys absent entirely when disabled.

### W2 — `race_engine/race_logger.py`: brotli compression ✅
(This commit is red on its own: the moment the logger writes brotli,
`simulate_race` line-counts the binary temp file and fails. W3, the commit
immediately after, restores green — the user chose to keep the W2/W3 boundary
rather than merge them.)
Add the incremental compressor and the `.br` filename convention. Add
`brotli>=1.1` to `requirements.txt`.
**Tests:** the written file is brotli-decodable and round-trips to the exact
lines W1's tests assert; `close()` is required for a complete stream (a file
read before `close()` must not be assumed complete).

### W3 — `racing/`: adapter returns the sample count, services records it ✅
`run_race` returns `(states, sample_count)`; `run_race_via_adapter` passes it
through; `simulate_race` stops line-counting the file, names it `.jsonl.br`,
and writes the new metadata.
**Tests** (`racing/tests.py`): `simulate_race` stores a log whose
`sample_count` matches the decompressed line count minus the header, whose
`tick_interval` is 2, and whose `size_bytes` equals the stored file's size;
the stored filename ends `.jsonl.br`. Replace the existing
`assert log.tick_count > 0` (line 139).

*(Implemented note: the `sample_count`/`tick_interval` columns do not exist
until W4's migration, so this commit keeps writing `tick_count` (the value is
the sample count) and asserts `tick_interval` from the decompressed header;
W4 renames the column, adds `tick_interval`, and flips these assertions to
`log.sample_count`/`log.tick_interval` — same boundary choice as W2/W3, so
every commit stays green.)*

### W4 — `racing/`: migration and admin ✅
`0006_racelog_sampling.py` — rename `tick_count` → `sample_count`, add
`tick_interval`, update `size_bytes` help text. Update `racing/admin.py:14`'s
`list_display`. Update `RaceLog`'s docstring, which currently says slimming is
"planned work".
**Tests:** `.venv/bin/python manage.py makemigrations --check --dry-run` is
clean after the migration is written.

*(Implemented note: `makemigrations --noinput` guessed remove+add for the
rename; the migration was hand-edited to a data-preserving `RenameField`. The
rename means the seam must carry the interval for admin and tests to record
it, so `run_race`/`run_race_via_adapter` grew to `(states, sample_count,
sample_interval)` here and `simulate_race` stores `sample_count` and
`tick_interval`; the W3 assertions flipped to `log.sample_count` /
`log.tick_interval`.)*

### W5 — `race_player/`: types and parser ✅
New `RaceHeader`/`RaceSample` types; `parseRaceLog` decodes the header and
samples into the existing `RaceSnapshot` shape; `tickInterval` on `ParsedRace`;
version check throws.
**Tests** (`race_player/src/utils/parseRaceLog.test.ts`, new): a two-line
fixture decodes to full rider objects with names and teams from the header;
flags decode to the right booleans; `tickInterval` is surfaced; a wrong `v`
throws; a file with no header throws.

### W6 — `race_player/`: tick-to-seconds in the UI
`formatDuration` takes seconds; `RaceViz`'s interval scales by `tickInterval`;
`tickInterval` threaded through props; `teamColors.ts` fallbacks deleted per
decision 10.
**Tests:** existing vitest suite stays green; add a case asserting
`formatDuration` renders `0h 2m 4s` for 124 seconds, and that a race with
`tickInterval: 2` and 62 samples reports a total of 2m 2s not 1m 1s.

### W7 — regenerate the sample logs
Regenerate all six `race_player/public/*.jsonl` as `.jsonl.br` via
`python -m race_engine race_engine/configs/<name>.json`. Delete the old ones.
Four globs must move to `.jsonl.br` or the file explorer silently lists
nothing: `race_player/vite.config.ts:18` (`endsWith('.jsonl')`), and
`scripts/serve_viewer.py` lines 39 (`DIST.glob`), 66-67 (the single-file copy
target) and 74 (`PUBLIC.glob`).
**Verification:** the player loads and plays each regenerated log.
**Load-bearing:** serving `.br` needs `Content-Encoding: br` in both the Vite
dev middleware and `RaceHandler`, or the browser hands the player compressed
bytes and `JSON.parse` fails on line 1.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7.

W1 before W2 because a plain-text new format can be read and diffed by hand;
adding compression on top of a format you have already eyeballed turns a
two-variable debugging problem into a one-variable one. W3 and W4 follow so the
Django side is consistent before anything in the player moves. W5 before W6
because the parser must produce `tickInterval` before the UI can consume it.
W7 last: it is the end-to-end proof, and it needs both sides done.

Commit after each work item. The repo is green at every one — W1-W4 leave the
player unable to read new logs, which is expected and is why W7 regenerates the
samples rather than leaving stale ones that appear to work.

## Documentation update (required, not optional)

**`racing/README.md`** — replace *Planned: slim and compress the log format —
NOT YET DONE* (lines 91-118) with what was built: the header/sample layout, the
2 s sampling and why `finish_time` is exempt, brotli and the `.jsonl.br`
convention, and the `sample_count`/`tick_interval` metadata. Keep *Rejected:
regenerating logs from a seed* untouched. Note in *Where they live* that the
stored file is compressed and that a future HTTP endpoint must serve it with
`Content-Encoding: br`.

**`race_player/README.md`** — rewrite *Data Source & Format* for the new
layout. Remove the "optional, logs predating this" caveats on `team`, `role` and
`teams` (§*Key Data Fields*), which decision 10 makes false. State that `wind`
is still per-tick and `band` is now in the header. Update §5's note about logs
predating wind.

**`AGENTS.md`** — the *Generated files* section says the log format is
"knowingly verbose and slimming it is planned work" and points at #88. Replace
with a one-line statement of the format and its size, still pointing at
`racing/README.md`.

## Verification

```bash
.venv/bin/python -m pytest                         # backend, 85% floor
cd race_player && npm run test && npm run lint     # player
.venv/bin/python -m race_engine race_engine/configs/mountain_stage.json
ls -la race_player/public/mountain_stage.jsonl.br  # expect < 2 MB
```

Then load the regenerated log in the player (`npm run dev`) and check, in this
order — each catches a different one of the risks below:

1. **It plays at all.** If the header is being served without
   `Content-Encoding: br`, `JSON.parse` throws on line 1. This is the most
   likely failure and the cheapest to spot.
2. **The clock reads right.** A race the engine reports as ~4 h must show ~4 h
   total, not ~2 h. A halved total means `tickInterval` is not reaching
   `formatDuration` — the exact failure decision 7 exists to prevent.
3. **Riders have names and team colours.** Blank names or all-neutral markers
   mean the header's rider list is not being merged into samples, or the order
   drifted (decision 2).
4. **The finish is right.** Compare the player's Result column against the
   engine's own stdout finishing order. Identical times and gaps prove decision
   6 held; a bunch sprint collapsing to a pile of identical times means
   `finish_time` got rounded or snapped.
5. **x1 is real time.** Ten seconds of wall clock should advance the race clock
   ten seconds, not twenty.

A passing unit test on a hand-written two-line fixture proves the decoder, not
the format — only a regenerated real log played end to end proves W1-W7 agree.

## Risks

| Risk | Mitigation |
|---|---|
| The `.br` file is served without `Content-Encoding: br`, so the player gets compressed bytes. **Most likely failure.** | W7 explicitly updates both `vite.config.ts` and `serve_viewer.py`. Verification step 1 catches it immediately. |
| Rider array order drifts from `header.riders`, silently swapping riders' identities mid-race. | Decision 2 marks order load-bearing; W1's test asserts it. Both header and samples must iterate `state.rider_states` — never re-sort. |
| `finish_time` gets rounded along with the other floats, corrupting gaps and ties. | Decision 6; W1 tests it explicitly. It is the one float excluded from decision 4's rounding. |
| Tick index is used as seconds somewhere not listed, halving a duration. | Verification step 2. The known sites are `PlaybackControls.formatDuration` and `RaceViz`'s interval — grep `tick` in `race_player/src` before finishing W6. |
| A rider's finish falls on a skipped sample and the pack view loses them. | The logger always writes a tick where a `finished` flag changed (decision 5), so the transition is never skipped. |
| `simulate_race` still line-counts the now-binary file. | W3 removes it explicitly; `racing/tests.py` asserts `sample_count` against a decompressed count. |
| Brotli's incremental `Compressor` is left unflushed, truncating the file. | `close()` writes `finish()`. W2 tests that a stream is only complete after `close()`. `RaceLogger` is already a context manager — `simulate_race` must keep using `with` or call `close()`. |

## Open questions

None.

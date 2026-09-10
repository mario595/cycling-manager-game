# Team Code Column + Finish-Time Display — Implementation Plan

**Status:** approved, ready to implement.

## Context

Two small, independent additions to the rider list on top of the already-shipped
team-colour work (`TEAM_VISUALIZATION_PLAN.md`):

1. Show each team's UCI-style 3-letter code in its own column, before the name.
2. Add a new "Result" column: blank while a rider is still racing, and once
   they finish, shows their finish time (winner) or time gap to the winner
   (everyone else). **Km and Speed are untouched** — they keep showing live
   data for every row, always; this is a pure addition, not a replacement.

## Part 1 — Team code column

### Data contract

The engine now writes a top-level `teams` map on every tick line, sibling to
`course_length`/`segments` — **not** per-rider:

```json
{ "time": 0, "course_length": 130000, "segments": [...], "riders": [...],
  "teams": { "t1": { "code": "ALP" }, "t2": { "code": "SPR" } } }
```

Confirmed against `race_engine/race_logger.py` and regenerated fixtures — all
six bundled configs already emit codes (`ALP`/`SPR`/`CLA`/`MIX`).

- Written even when no teams are configured (`"teams": {}`), so it is safe to
  treat as always-present in the type, unlike `team/role` on `Rider`.
- Logs predating this change won't have the field at all (not merely empty) —
  treat as **optional** in TypeScript and default to `{}`, showing a blank
  code cell rather than crashing. Same "stale logs must still play" rule as
  the team/role fields.

### Changes

- **`src/types/race.ts`** — add `teams?: Record<string, { code: string }>` to
  `RaceSnapshot`. Add a `teamCodes?: Record<string, string>` to `ParsedRace`
  (flattened `team_id -> code`, built once in `parseRaceLog`, not re-derived
  per render).
- **`src/utils/parseRaceLog.ts`** — read `snapshots[0].teams` (codes are
  static for the race, so first tick is enough) into `ParsedRace.teamCodes`,
  defaulting to `{}` when absent.
- **`src/utils/teamColors.ts`** — add `teamCode(teamCodes, team?): string`.
  Returns the 3-letter code when known, otherwise `'—'` (no team, or team id
  not present in the map — keeps the column visually aligned instead of
  collapsing).
- **`src/components/RiderList.tsx`** — new column **before** Rider, header
  `""` (or `Team`, narrow), showing the code in the row's team colour (bold,
  small, e.g. `text-xs font-semibold`, matching how the colour bar already
  marks the row — this makes the code redundant with the colour bar by
  design, which is fine: the bar is a glance cue, the code is the readable
  label for anyone colour-blind or unfamiliar with the palette).
  - `RaceViz` → `RiderList` needs `teamCodes` threaded down as a prop.

## Part 2 — Result column (finish time / gap)

### The rule (confirmed)

A new column, **per-row**, independent of what any other rider is doing:

- **Still racing** (`rider.finished === false`): column is blank. Km and
  Speed for this row are untouched — they show live data exactly as today,
  for the entire race, regardless of whether other riders have finished.
- **Winner** (first rider to finish, i.e. lowest `finish_time` across the
  field): `hh:mm:ss`, from `finish_time` (a tick count = seconds).
- **Every other finished rider:** gap to the winner, formatted `+mm:ss`-style
  matching the existing gap formatter's convention seen in the pack list
  (`+3m 14s`, `+2s` — reuse `formatGapTime` already in `RiderList.tsx`, do not
  invent a second time-formatting function).
- **Riders who finish in the same group as the rider immediately ahead get
  `+0`.** "Same group" is determined by reusing the existing pack-cohesion
  distance (`PACK_COHESION_DISTANCE = 60m` in `computePacks.ts`): at rider
  X's finish tick, if X's `pos` is within 60m of the *previous finisher's*
  `pos` at that same tick, X gets the same displayed gap as the rider ahead
  (chained — a group's 3rd/4th/... riders also inherit +0, not just the 2nd).
  This mirrors real bunch-sprint timing and reuses a constant that already
  exists rather than inventing a new threshold.

Km/Speed and the new Result column are fully independent: nothing about one
rider finishing changes what any other row displays in Km/Speed. The table
never changes shape or headers based on race progress — the Result cell is
just blank until that row's own rider crosses the line.

### Why this needs the full snapshot history, not just the current tick

Computing "gap to winner" for a rider who finished 40 minutes ago requires
knowing the winner's finish time, and computing "same group" requires the
finishing rider's pos at the *previous finisher's* tick — both are lookups
into `snapshots`, not the current snapshot alone.

### Changes

- **`src/utils/raceResults.ts` (new)** — pure function operating on
  `ParsedRace`:

  ```ts
  export interface RiderResult {
    riderId: string
    finishTime: number | null   // seconds (tick count), null if still racing
    gapSeconds: number | null   // null for the winner and for unfinished riders
  }

  export function computeRaceResults(raceData: ParsedRace): Map<string, RiderResult>
  ```

  Algorithm:
  1. Scan `snapshots` once to find each rider's finish tick (first snapshot
     where `finished === true`) — mirrors how `finish_time` already works,
     but we need the **snapshot** at that tick to read positions, so index by
     tick number, not just take `finish_time` at face value (they should
     agree; use `finish_time` as the tick to look up, it's already exactly
     that).
  2. Sort finishers by `finish_time`.
  3. Walk in order. For the winner, `gapSeconds = 0` conceptually but we
     special-case it in rendering (show finish time, not a gap). For each
     subsequent finisher, look up their `pos` in the snapshot at the
     *previous finisher's* `finish_time` tick; if within
     `PACK_COHESION_DISTANCE` of the previous finisher's finish `pos`
     (course length), inherit the previous finisher's `gapSeconds`;
     otherwise `gapSeconds = finish_time - winnerFinishTime`.
  4. Riders never finishing (`finish_time` stays `null` through the last
     snapshot) get `finishTime: null, gapSeconds: null` — their Result cell
     stays blank; their Km/Speed cells are unaffected by any of this (they
     never consult `results` in the first place).
  - Computed once via `useMemo` in `RaceViz` (keyed on `raceData`, not on
    `tick` — results don't change as playback proceeds), not recomputed per
    tick or per row.
- **`src/utils/formatTime.ts`** — promote the existing `formatGapTime` out of
  `RiderList.tsx` into a shared util (it's about to be used in two places:
  the pack-gap divider and the new finish-time column), and add
  `formatFinishTime(seconds): string` → `hh:mm:ss` (reuse the
  hours/minutes/seconds split already in `PlaybackControls.tsx`'s
  `formatDuration` as the pattern, but zero-padded to `hh:mm:ss` since this
  is a results table, not a live counter).
- **`src/components/RiderList.tsx`**:
  - Accept a `results: Map<string, RiderResult>` prop. No other new prop —
    every row looks itself up by `rider.id`.
  - New column, header **"Result"**, placed after Speed (rightmost, before
    the Stamina/Energy bars — those stay last since they're about current
    physical state, not race outcome). Cell content per row:
    - Still racing → blank (`—` or empty, matching the visual weight of
      other blank/NA cells elsewhere in the app, e.g. em-dash).
    - Winner → `formatFinishTime(result.finishTime)` → `hh:mm:ss`.
    - Other finished → `formatGapTime(result.gapSeconds)` with a leading
      `+`, or literally `+0` when `gapSeconds === 0` (same-group case).
  - Km/Speed columns and their cell logic are **not touched** — no
    conditional, no header change, no dependency on `results` at all.
  - `RiderRow` reads its own `RiderResult` from the `results` map by
    `rider.id`.

- **`src/components/RaceViz.tsx`** — compute `results = useMemo(() =>
  computeRaceResults(raceData), [raceData])`, pass to `RiderList`. Also pass
  `raceData.teamCodes` down (Part 1).

## Work items

1. **Team codes** — types, `parseRaceLog`, `teamColors.ts` (`teamCode`),
   `RiderList` column, `RaceViz` wiring. Regenerate `.jsonl` fixtures first
   (same command as before) so codes are present to test against.
2. **Results computation** — `raceResults.ts`, shared `formatTime.ts`
   (extract `formatGapTime`, add `formatFinishTime`).
3. **RiderList Result column** — new column, winner/gap/blank cell logic,
   wire `results` prop from `RaceViz`. No changes to Km/Speed.

## Verification

1. Load any bundled config, confirm the new code column shows `ALP`/`SPR`/
   `CLA`/`MIX` in the row's team colour, before the name, for all ticks
   (including tick 0, before anyone moves).
2. Scrub to a tick **before** anyone finishes — Km/Speed unchanged from
   today, Result column blank for every row.
3. Scrub to the exact tick the leader finishes — leader's Result cell shows
   `hh:mm:ss` immediately; every other row's Km/Speed is unaffected (still
   live), their Result cell stays blank until each rider individually
   finishes.
4. Scrub to end of race — confirm bunch-sprint finishers (per the earlier
   pack-blob verification, `sprinters_classic` has a group finish) show `+0`
   for riders who crossed together, and a real `+mm:ss` for clear gaps. Every
   row still shows its final Km/Speed alongside the Result column — nothing
   is replaced. Cross-check a couple of gap values against `finish_time`
   deltas by hand.
5. Load a log stripped of the `teams` field (simulate a stale log) — code
   column shows `—` instead of crashing; results columns unaffected (separate
   optional field).
6. Confirm `formatGapTime`/`formatFinishTime` produce sane output at
   boundaries: 0s, <1min, exactly on the hour.

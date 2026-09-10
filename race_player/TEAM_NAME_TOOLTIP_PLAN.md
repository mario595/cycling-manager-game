# Team Name Tooltip — Implementation Plan

**Status:** approved, ready to implement.

## Context

The rider list already shows a 3-letter UCI-style team code (`ALP`, `SPR`,
...) per row, sourced from a `race.teams` config block that currently only
carries `code`. The ask: hovering the code shows the full team name in a
tooltip. No team-name data exists anywhere today — engine config, models, or
logs — so this is an engine change (add the field, thread it through) plus a
small frontend change (read it, show it on hover).

This spans two independently-versioned pieces of code: `race_engine`
(Python) and `race_player` (TypeScript), connected only by the `.jsonl` file
contract — same shape as the code work before it.

## Part 1 — Engine: add `name` alongside `code`

### Config format change

`race.teams` entries currently require only `code`:

```json
"teams": {
  "t1": { "code": "ALP" }
}
```

Add a required sibling `name`:

```json
"teams": {
  "t1": { "code": "ALP", "name": "Alpine Racing" }
}
```

**`name` is required, not optional**, matching how `code` is already
required once a team block exists — an entry with a code but no name is a
config error, not a silently-blank tooltip. No length/format constraint
beyond non-empty (unlike `code`'s exactly-3-uppercase-letters rule — team
names are free text, e.g. "Team Alpine Racing" or "Mixed Nationale").

### Changes

- **`race_engine/config.py`** (`_parse_teams`):
  - Change return type from `dict[str, str]` (id → code) to
    `dict[str, dict[str, str]]` (id → `{"code": ..., "name": ...}`) — carry
    both fields as a unit through the whole pipeline instead of two parallel
    maps that could drift out of sync.
  - Require `name` via the same `_require()` helper already used for `code`;
    validate it's a non-empty string (reuse the pattern of `code`'s
    `_TEAM_CODE_RE` check, but just `if not name.strip(): raise ConfigError`
    — no format constraint beyond non-empty).
  - Uniqueness check stays on `code` only (that's the identity UCI codes
    guarantee); team names are display text and are not required to be
    unique.
- **`race_engine/models.py`** (`run_race`): the `team_codes` **parameter**
  keeps its name (renaming a public function parameter across the engine for
  a display-metadata tweak is unnecessary churn) but its type annotation
  changes to `dict[str, dict[str, str]] | None`. It's threaded straight into
  `RaceLogger` unchanged, same as today.
- **`race_engine/race_logger.py`** (`RaceLogger.log`): the `teams` block
  already writes `{team_id: {"code": code} for ...}` — change to write the
  whole per-team dict as-is: `{team_id: team_data for team_id, team_data in
  self._team_codes.items()}`, since `team_data` is now already `{"code":
  ..., "name": ...}`. Simplifies the comprehension rather than complicating
  it.
- **`race_engine/configs/*.json`** (all six bundled configs): add a `name`
  to every existing team entry. Suggested names (cosmetic, pick anything
  sensible — these are fictional teams for an MVP):
  - `ALP` → "Alpine Racing"
  - `SPR` → "Sprint Collective"
  - `CLA` → "Classics Crew"
  - `MIX` → "Mixed Nationale"
- **`race_engine/test_race_logger.py`**: update
  `test_logger_writes_team_codes` to pass `{"t1": {"code": "ALP", "name":
  "Alpine Racing"}, ...}` and assert the full dict comes back unchanged
  (the logger no longer needs to know the shape of the team data at all,
  which is arguably a simplification worth calling out in the test
  docstring). `test_logger_writes_empty_teams_when_absent` is unaffected.
- **New test in `race_engine/test_config.py`** (or wherever config parsing
  is already tested — check before assuming a new file) covering: a team
  with `code` but no `name` raises `ConfigError`; a team with both parses
  correctly into the `{"code", "name"}` shape.

## Part 2 — Frontend: read `name`, show it on hover

### Data contract

```json
{ "teams": { "t1": { "code": "ALP", "name": "Alpine Racing" } } }
```

Same optionality rules as `code` today: the whole `teams` field is optional
on `RaceSnapshot` (stale logs lack it entirely), but once present, `name` is
assumed present alongside `code` (the engine now enforces this at config
parse time — a log without `name` shouldn't exist going forward, but a
**stale log predating this change** will still be missing it entirely, same
as the current `teams` optionality already handles). No new "optional within
optional" case to design around — treat `name` as present whenever `teams`
is present; if a log manages to have `teams` without `name` (only possible
by hand-editing a log file), fall back to the code itself as the tooltip
text rather than crashing.

### Changes

- **`src/types/race.ts`**: `RaceSnapshot.teams` becomes `Record<string,
  { code: string; name: string }>`.
- **`src/utils/parseRaceLog.ts`**: currently flattens `teams` into
  `ParsedRace.teamCodes: Record<string, string>` (id → code). Add a parallel
  `ParsedRace.teamNames: Record<string, string>` (id → name) built the same
  way, from the same loop over `snapshots[0].teams`.
- **`src/utils/teamColors.ts`**: add `teamName(teamNames, team?): string`,
  mirroring `teamCode()`'s shape exactly (same signature pattern, same `—`
  fallback for no team / missing entry).
- **`src/components/RiderList.tsx`**:
  - Accept `teamNames: Record<string, string>` prop, threaded the same way
    `teamCodes` already is (`RaceViz` → `RiderList` → `RiderRow`).
  - On the team-code `<td>`, add a native `title` attribute:
    `title={teamName(teamNames, rider.team)}`. A native title tooltip is the
    simplest correct choice here — it's a single short line of plain text,
    exactly what `title` is for, with zero new UI dependency or hover-state
    plumbing. Do not build a custom tooltip component for this.
- **`src/components/RaceViz.tsx`**: pass `raceData.teamNames` down to
  `RiderList` alongside the existing `raceData.teamCodes`.

## Work items

1. **Engine:** `config.py` (`_parse_teams` shape + validation),
   `race_logger.py` (pass-through simplification), `models.py` (type
   annotation only), all six configs (add `name`), test updates.
2. **Frontend:** types, `parseRaceLog.ts` (`teamNames`), `teamColors.ts`
   (`teamName()`), `RiderList.tsx` (`title` attribute), `RaceViz.tsx`
   (wiring). Regenerate `.jsonl` fixtures after the engine change so `name`
   is present to test against.

## Verification

1. `python -m pytest race_engine/` — new/updated tests pass; a team config
   entry with `code` but no `name` raises `ConfigError`.
2. Regenerate all six `.jsonl` fixtures; spot-check one file's first line has
   `"teams": {"t1": {"code": "ALP", "name": "Alpine Racing"}, ...}`.
3. In the browser, hover a team-code cell in the rider list — native tooltip
   shows the full team name after the OS/browser's normal hover delay.
4. Load a log with `teams` present but stale in shape (simulate: strip
   `name` from one entry only) — tooltip falls back to showing the code
   itself for that team, no crash, no blank tooltip.
5. Load a fully stale log (no `teams` field at all, from before any of this
   work) — team-code cell still shows `—` with no tooltip (nothing to show),
   confirming the earlier optional-field fallback chain still holds.

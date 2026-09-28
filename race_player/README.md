# Race Player / Visualizer

A standalone React-based web application for visualizing race simulations produced by `race_engine`.

## Running it

```bash
npm install
npm run dev
```

Other scripts: `npm run build`, `npm run test` (vitest), `npm run lint` (oxlint).

The player reads brotli-compressed `.jsonl.br` logs from `public/`. Generate
one from the repository root with `python -m race_engine
race_engine/configs/<name>.json`, which writes straight into
`race_player/public/`.

## Project Goals

- **Primary:** Provide a sophisticated, interactive visualization of race logs (`.jsonl.br` files).
- **Design:** Mimic professional cycling visualizers like Strava or VeloViewer (elevation profile + rider markers).
- **Integration:** Must be modular and portable enough to integrate into the future Django-based game web app.

## Tech Stack

| Layer | Technology | Notes |
|-------|------------|-------|
| **Build Tool** | Vite | Fast HMR, excellent React support. Dev server also serves the `/api/races` listing endpoint. |
| **UI Library** | React 19+ | Functional components and hooks. |
| **Language** | TypeScript | Strict typing for race data and props. |
| **Styling** | Tailwind CSS | Utility-first CSS for rapid UI development. |
| **UI Components** | Ant Design (antd) | UI kit (Segmented, Button, Space). |

## Data Source & Format

### Input
- **File:** `.jsonl.br` files in `public/` (produced by `race_engine`).
  Brotli-compressed, so a log has no usable bytes until the browser decodes
  it — the dev endpoint and the static server both serve it with
  `Content-Encoding: br` (see *Running the visualizer*, below).
- **Structure:** Line 1 is a header object holding everything constant for the
  race; every later line is one **sampled** snapshot. Sampling is every
  `tick_interval` race-seconds (the player multiplies tick indices by it to get
  real time), and a tick where someone's `finished` flag changes is always
  captured, so no finish is missed — only its exact instant is quantised. The
  parser hard-rejects anything without a header or with an unsupported `v`.

### The header (line 1)
`{ "v": 1, "tick_interval": 2, "course_length": ..., "segments": [...],
"teams": {...}, "riders": [...], "wind_band"? }`. `v` is the format version and
must be understood or the parse fails loudly. The player uses `maxTicks =
snapshots.length - 1` and `tickInterval` together to drive the clock; both the
time display and the playback rate derive from `tickInterval`.

### Key Data Fields
- **Segments:** Array of `{ length, gradient }` objects, in the header. Used to
  derive the elevation profile.
- **Teams:** In the header — `{ "t1": { "code": "ALP", "name": "Alpine
  Racing" }, ... }`, a `team_id -> {code, name}` map. `code` is the UCI-style
  3-letter TV abbreviation; `name` is the full team name (engine-enforced
  non-empty whenever a team block exists — see `race_engine/config.py`'s
  `_parse_teams`). Always present, even when empty (`"teams": {}`).
  `parseRaceLog` reads it into `ParsedRace.teamCodes`/`teamNames`, defaulting
  to `{}`. See `teamCode()`/`teamName()` in `utils/teamColors.ts`.
- **Riders:** The header lists identity only — `id`, `name`, `team`, `role` —
  in race order. Every sample references a rider **by array index**, so the
  order never changes and a rider is never re-listed. Per-sample values:
  - `pos` (meters from start)
  - `speed` (m/s)
  - `energy`, `stamina` (0-100)
  - flags bitmask — `1` pulling, `2` surging, `4` finished, `8` DNF (cut by
    the race engine's time limit, the broom wagon — see
    `race_engine/README.md`, *Simulation tick*). Bit `8` decodes to
    `Rider.dnf` and is honoured, not ignored: a host splits a snapshot's
    riders into **racing** (`!dnf`) and **out** (`dnf`), and only the racing
    ones go into `computePacks`. A cut rider therefore leaves the profile and
    the pack list instead of freezing on it — under a broom wagon a large
    share of the field can go at once, and a trail of stationary markers
    would bury the live race. Both hosts then list them separately: the game
    under "Out of the race" with `DNF` in the result column (see
    `frontend/README.md`), the standalone simply omits them, which is
    acceptable for a dev tool. `dnf` is mutually exclusive with `finished`.
    `pulling` is set
    only for the rider setting the pace at the front of a pack; there is no
    separate "drafting" flag (shelter degree in a pack is continuous, not a
    meaningful boolean — every non-pulling pack member is assumed to be
    benefiting to some degree; see `race_engine/README.md`'s "Drafting & pack
    cohesion")
  - `finish_time`
  Identity fields are on the header rider, never on the sample: `team` (string
  team id, e.g. `t1`-`t4`, or `null` for a rider with no team, falling back to
  a neutral colour — `teamColor()` in `utils/teamColors.ts`) and `role`
  (`"leader"` | `"support"`, exactly one leader per team; `isLeader()` in
  `utils/teamColors.ts`).
- **Wind:** One `[speed, angle]` pair per **sample** (wind changes tick by
  tick) when wind is on; `speed` is km/h, `angle` is degrees `[0, 360)`,
  **relative to the rider, not a compass bearing** — `0` = headwind, `90` =
  crosswind from the rider's right, `180` = tailwind, `270` = crosswind from
  the left. The `band` (`"calm" | "light" | "moderate" | "strong"`) lives in
  the **header** as `wind_band` — it is constant for the race and the parser
  merges it with each sample's pair into the `Wind` object the compass renders.
  Both are absent when wind is disabled. See `race_engine/WIND_PLAN.md` for
  the simulation side and the `Wind`/`WindBand` types in `types/race.ts`.

### Elevation Derivation
Since absolute altitude is not stored in the engine logs, it must be derived from the segment data (`utils/profile.ts`):
1. Initialize `elevation = 0`.
2. For each segment in the course:
   - Calculate `elevation_change = segment.length * (segment.gradient / 100)`.
   - Add to cumulative `elevation`.
   - Store as part of the profile coordinate data.

This `computeProfile()` is shared: the frontend's race-detail screen
(`CourseProfile.tsx`) imports it across packages, so the calendar and this
visualizer always agree on how a course looks.

## Core Features

### 1. Elevation Profile Visualization
- **Type:** Custom SVG area chart — `CourseChart.tsx`, the shared chart that
  the frontend's race-detail screen imports directly (no rider markers there).
- **Coloring:** Gradient-colored area based on the slope (green for flat, blue for descents, yellow→red for climbs).
- **Gradient Labels:** Shows `%` labels below each segment (only for segments wide enough to avoid overlap).
- **`ElevationProfile.tsx` is the chart plus the riders.** It composes
  `CourseChart` with an overlay of markers/blobs/tooltips, drawn on top via
  the chart's overlay render-prop so they share the exact scale the course
  was drawn with.
- **Rendering unit is the pack, not the rider.** The profile consumes
  `Pack[]` from `computePacks` (the same packs `RiderList` renders), not a
  flat rider list — a bunch of 40+ riders at one x-coordinate is otherwise
  unreadable. **Adaptive rule:** packs of 1-2 riders render as individual
  `RiderMarker`s; packs of 3+ collapse into a single `PackMarker` blob at the
  pack's `frontPos`. The size boundary is damped with hysteresis (become a
  blob at 3, split back to individuals at 1) to avoid flicker for a pack
  hovering at the threshold — see `BLOB_SPLIT_SIZE`/`BLOB_MERGE_SIZE` in
  `ElevationProfile.tsx`.
- **Rider Markers (`RiderMarker.tsx`):** Team-coloured circle (`teamColor()`).
  Leaders are larger (radius 7 vs 5, or 9 vs 7 when active) and carry a white
  inner dot — never an emoji at this scale. Team identity is colour; leader
  identity is shape, kept orthogonal per design.
- **Pack Blobs (`PackMarker.tsx`):** A single glyph per bunched pack:
  - **Size** scales sub-linearly (∝ √riders) so a 40-rider bunch doesn't
    dwarf a small break, clamped to a min/max radius.
  - **Composition** is a segmented donut ring, one arc per team coloured and
    sized by that team's share of the pack (segments sorted by team id for
    tick-to-tick stability).
  - **Leaders present** get a small coloured pip around the ring, capped at a
    few pips with the ring carrying the rest.
  - **Rider count** is centred in the donut hole once the blob is large
    enough to fit it legibly.
- **Z-order:** Larger packs paint first so smaller packs/individuals paint on
  top — a lone attacker off the front must never render behind the bunch it
  escaped.
- **Interactivity:** Clicking a rider marker or pack blob selects it (packs
  select their front rider, reusing the existing selection path). Hovering
  shows a stats tooltip (individual rider) or a composition tooltip (pack:
  size, per-team counts, leaders named) — both tooltip boxes size themselves
  to their actual content.
- **Team colours:** 12-colour palette in `utils/teamColors.ts`, validated for
  perceptual separation and contrast — do not substitute hues without
  re-validating (see `race_player/TEAM_VISUALIZATION_PLAN.md`). Riders/packs
  with no team use a neutral slate, not part of the 12.

### 2. Playback Controls
- **Start/Pause:** Toggle button to start/stop the simulation.
- **Keyboard:** `←` steps back, `→` steps forward, `Space` toggles play/pause.
  Handled by `utils/usePlayback.ts`, and only for events aimed at the page:
  a `keydown` whose target is an `INPUT`, `TEXTAREA`, `SELECT` or `BUTTON`, or
  is content-editable, is left alone, so `Space` on the game's focused
  Play button presses that button once and nothing else.
- **Speed Selector:** Options for x1, x2, x5, x10, x25, x50 playback speeds.
- **Seek Slider:** Native `<input type="range">` (not antd `Slider`, see known issue below) spanning `0..maxTicks`; scrubs to any tick regardless of play state.
- **Elapsed/Total Display:** Race seconds (tick index × `tickInterval`) formatted as `Hh Mm Ss / Hh Mm Ss` (always the full `Hh Mm Ss` shape — even `0h 2m 4s` — since the digits are fixed-width tabular, not units that get dropped). A ~4 h race reads as ~4 h, not ~2 h — the display runs on the header's `tickInterval`, not on sample count. The raw `tick x / y` counters stay beside it for debugging.
- **Logic:** `utils/usePlayback.ts` — a hook holding tick, play state and
  speed, with an `interval` advancing one tick per `tickInterval / speed`. It
  takes the default speed from its host (`{ initialSpeed }`): ×1 here, ×10 in
  the game, where a five-hour stage at ×1 is five hours. The speed list itself
  is `PLAYBACK_SPEEDS` in the same module, so both hosts offer the same six
  speeds. Toggling play at the last tick restarts from 0; `seek` and `step`
  clamp to `[0, maxTicks]`. `RaceViz` consumes it, and so does the game's
  replay screen — the standalone's behaviour is unchanged.

### 3. Rider Leaderboard (Packs)
- **Pack Grouping:** Riders are grouped into packs mirroring the race engine's cohesion algorithm: BFS connected components over riders within `PACK_COHESION_DISTANCE (60m)` on draft-allowed terrain (gradient ≤ 5%). A single rider is its own pack. Finished riders are included (frozen at their finish `pos`), so they naturally separate into their own pack as the field behind them keeps moving.
- **Ranking tie-break:** Rows (and pack membership) sort by `pos` descending,
  but once several riders finish they all share the same `pos`
  (`course_length`) — ties are broken by `finish_time` ascending
  (`comparePosition()` in `computePacks.ts`) so the actual first-across-the-
  line rider ranks #1, not whoever happens first in the source array.
- **Gap Dividers:** Time gap displayed between adjacent packs, formatted as
  `+Xm Ys (Zm)` — minutes/seconds with the raw meter gap in parentheses. The
  numbers come from `utils/packGaps.ts`, which measures from the **rear** of
  the pack ahead to the **front** of the pack behind (a leading pack has no
  gap, hence the leading `null`) and divides by the trailing pack's speed.
  Shared with the game's replay screen, which formats the same two numbers
  differently — a separator row rather than a table row.
- **Result column:** `utils/raceResults.ts`'s `resultLabel()` — `—` while a
  rider is still racing, `hh:mm:ss` for the winner, `+0` for a rider in the
  winner's group, `+Xm Ys` otherwise. The results are precomputed over the
  whole race, so the gate is the rider's own live `finished` flag rather than
  the presence of a result.
- **Columns:** Rank, Team, Name, Km, Speed, Result, Energy/Stamina bars.
- **Finished Riders:** Stay in the list (not removed) with a ✅ prefix on their name; speed cell shows `✓` instead of km/h.
- **Leader Highlight:** Visual distinction for the current race leader (highest `pos`).
- **Team Colour Bar:** 3px left border on each row in the rider's team colour
  (`teamColor()`), cheap enough to survive rows re-sorting into packs every
  tick.
- **Team Code Column:** The rider's 3-letter UCI code (`teamCode()`) whenever
  their `team` is set, coloured to match the row's team colour bar; shows `—`
  for the teamless.
  Hovering the cell shows the full team name (`teamName()`) via a native
  `title` attribute — no custom tooltip component, since it's one line of
  plain text.
- **Team Leader Crown:** 👑 prefix on the rider name (via `isLeader()`),
  alongside the ✅ finished prefix.
- **Result Column:** Per-row, independent of every other row — blank
  (`—`) while that rider is still racing (`rider.finished === false` in the
  *currently displayed* tick; note the precomputed results map holds a
  finish time regardless of tick, so the cell must gate on the live
  `finished` flag, not just presence in the map). Once a rider finishes:
  the winner (earliest `finish_time` across the whole race) shows their
  finish time as `hh:mm:ss`; every other finished rider shows their time gap
  to the winner as `+mm:ss` (`formatGapTime`/`formatFinishTime` in
  `utils/formatTime.ts`). Km/Speed are never replaced — they keep showing
  live data for every row for the whole race; Result is a pure addition.
  - **Group finishes:** riders who cross in the same bunch as the finisher
    immediately ahead of them get `+0`, chained down the group (3rd/4th+
    riders in a bunch sprint inherit it too, not just the 2nd). "Same group"
    reuses the existing `PACK_COHESION_DISTANCE` (60m) rather than a new
    threshold: at rider X's finish tick, is X within 60m of the previous
    finisher's position at that same tick? See `computeRaceResults()` in
    `utils/raceResults.ts`. A tight bunch sprint can legitimately collapse
    the *entire* field to `+0` this way if each successive gap stays under
    60m — that mirrors real UCI bunch timing, not a bug.
  - Computed once per loaded race (`useMemo` keyed on `raceData`, not on
    `tick`) since results never change as playback proceeds.
- **Legend:** Footer legends `pulling`/`surging`/👑, plus one swatch per team
  actually present in the loaded race (not all 12 when fewer are racing);
  wraps onto multiple lines at the 12-team ceiling rather than truncating.

### 4. File Explorer (Sidebar)
- **Location:** `FileExplorer.tsx` — standalone dev tool, decoupled from player logic.
- **Endpoint:** `GET /api/races` returns `{ files: [{ name, mtime }, ...] }` listing all `.jsonl.br` in `public/`, `mtime` as an ISO timestamp; the sidebar shows each file's last-modified date/time below its name.
  - Dev: Vite plugin in `vite.config.ts` (middleware, not built into the app).
  - Prod: custom `RaceHandler` in `serve_viewer.py` + copies all `.jsonl.br` into `dist/`. Both paths also set `Content-Encoding: br` when serving a `.br` file — load-bearing, or the browser hands the player compressed bytes and `JSON.parse` throws on line 1.
- **Refresh button:** Re-fetches the file list without page reload.
- **Selection:** Clicking a file loads and parses it via `App.tsx`; the `RaceViz` component receives parsed data as a prop — zero coupling to the file system.

### 5. Wind Compass (`WindCompass.tsx`)
- **What it answers, at a glance:** which way the wind is hitting the riders,
  and how hard. Lives in the `PlaybackControls` row, right-aligned next to
  the elapsed/tick readout — a small (~110px) persistent instrument, not a
  feature panel; it must never compete with the elevation profile.
- **The bike never rotates; the arrow does.** This is a direct translation
  of the engine's model: wind is relative to the rider, there is no course
  heading, so there is nothing for the bike to rotate against. The arrow
  rotates around the fixed bike to show where the wind is coming from.
  Rotation is smoothed via a CSS transition driven by a continuously
  unwrapped angle (`unwrapAngle()` in `utils/wind.ts`, tracked in a ref) so
  a 359°→1° wrap takes the short way rather than spinning through 180°.
- **Compass rose labelled in rider terms** — `HEAD` / `TAIL` / `L` / `R`,
  never N/S/E/W. There is no geography in this model; writing compass
  directions would imply one that doesn't exist.
- **Intensity is redundantly encoded**: colour ramp (`windColor()`) and arrow
  length/thickness (`arrowLength()`) both derive from the *live* `speed`
  (not the band), so the arrow visibly breathes as wind drifts tick to tick;
  the `band` name is used only for the text label underneath. Two channels
  keep it readable for colour-blind viewers.
- **Optional, absent means absent:** returns `null` when `wind` is
  `undefined` (races run with wind disabled) — no placeholder, no "no wind
  data" box, layout collapses cleanly. (Wind is only absent for disabled
  races now: the format reads `wind_band` from the header and a per-sample
  pair, so there are no stale predating-wind files to defend against.)
- **Memoised** (`memo(WindCompass)`, matching `RiderMarker`/`PackMarker`) —
  it re-renders every tick.
- **Inline styles, not Tailwind** — the one deliberate exception to the
  Tailwind rule below, because the game's replay screen renders this same
  component and the SPA has no Tailwind build: a class name would be a silent
  no-op there. Anything the SPA imports must be styled this way. Colours are
  the slate literals the classes resolved to (`#334155`, `#94a3b8`).
- Explicitly **not built**: animated particle streaks, a per-segment wind
  overlay on the elevation profile (wind is a property of time, not course
  position, in this model — painting it on the distance axis would imply a
  spatial relationship that doesn't exist), or a wind timeline under the
  seek bar. See `race_player/WIND_VISUALIZATION_PLAN.md` decision 5.

## Architecture

### File Structure
```
race-player/
├── public/
│   └── *.jsonl.br               # Brotli-compressed race data files (any number)
├── src/
│   ├── components/
│   │   ├── RaceViz.tsx         # Main container: pack computation, selection, layout (playback is usePlayback's)
│   │   ├── CourseChart.tsx     # SHARED elevation chart: segments, % labels, km markers, axes
│   │   ├── ElevationProfile.tsx# CourseChart + rider markers/blobs/tooltips via the overlay prop
│   │   ├── RiderMarker.tsx     # Custom SVG circle marker (memoized), team colour + leader shape
│   │   ├── PackMarker.tsx      # Segmented-ring pack blob (memoized): size, team composition, leader pips
│   │   ├── PlaybackControls.tsx# Play/Pause, speed selector, elapsed/race-time readout, wind compass
│   │   ├── RiderList.tsx       # Pack-grouped table with gap dividers, team colour bar, crown
│   │   ├── WindCompass.tsx     # Fixed-bike/rotating-arrow wind readout (memoized)
│   │   └── FileExplorer.tsx    # Dev sidebar: lists .jsonl.br, refresh, standalone
│   ├── types/
│   │   └── race.ts             # TypeScript interfaces (Rider, Pack, ProfilePoint, Wind, etc.)
│   ├── utils/
│   │   ├── parseRaceLog.ts     # Parses JSONL, computes profile via utils/profile.ts
│   │   ├── profile.ts          # SHARED elevation derivation (computeProfile) — imported by the frontend
│   │   ├── interpolateRider.ts # Maps rider.pos to (x,y) on profile
│   │   ├── computePacks.ts     # BFS pack cohesion mirroring race_engine logic
│   │   ├── gradientColors.ts   # Maps gradient % to color pairs
│   │   ├── teamColors.ts       # 12-colour team palette, teamColor()/teamCode()/isLeader() helpers
│   │   ├── raceResults.ts      # Winner finish time + gap-to-winner per rider, group-finish detection, resultLabel()
│   │   ├── packGaps.ts         # Gap from each pack to the one ahead (null for the leader) — SHARED
│   │   ├── formatTime.ts       # formatGapTime (+3m 14s) / formatFinishTime (hh:mm:ss) / formatDuration
│   │   ├── usePlayback.ts      # SHARED tick/play/speed hook, PLAYBACK_SPEEDS, keyboard with an
│   │   │                       #   interactive-target guard — imported by the frontend
│   │   ├── wind.ts             # windColor()/windLabel()/arrowLength()/unwrapAngle() (wind.test.ts)
│   │   └── useProfileScale.ts  # Linear SVG scale with fixed margins (profileScale + hook)
│   ├── App.tsx                 # Sidebar + dynamic file fetch (the only glue point)
│   └── main.tsx
├── scripts/
│   └── serve_viewer.py         # CLI tool: serves player + all .jsonl.br in public/ + /api/races
├── package.json
├── vite.config.ts              # Plugins: React, Tailwind, race-file-listing dev endpoint
└── tsconfig.json
```

### Component Hierarchy
```
App.tsx
├── FileExplorer (standalone, no knowledge of player)
└── main
    └── RaceViz
        ├── PlaybackControls
        ├── ElevationProfile
        │   └── CourseChart         # the chart, shared with the frontend SPA
        │       └── overlay → RiderMarker (memoized SVG marker, packs of 1-2)
        │                 → PackMarker (memoized SVG blob, packs of 3+)
        │                 → tooltips
        └── RiderList
            └── Pack groups + gap dividers
```

### Data Flow
```
App.tsx
 ├─ fetch(`/api/races`)              → FileExplorer renders sidebar list
 ├─ fetch(`/${selectedFile}`)        → parseRaceLog() → ParsedRace
 ├─ <FileExplorer onSelect={setSelectedFile} />
 └─ <RaceViz raceData={parsedRace} />
      ├─ computePacks(riders, profile)  → Pack[] → RiderList AND ElevationProfile
      │                                   (single computation, shared — not recomputed per view)
      ├─ ElevationProfile (custom SVG, consumes Pack[])
      └─ PlaybackControls (keyboard + buttons)
```

## Integration Strategy

### Current (Standalone)
- Serve via `vite dev` (HMR + `/api/races` middleware) or `serve_viewer.py` (static build + `/api/races` handler).
- Fetch any `.jsonl.br` from `public/` via the file explorer sidebar.

### The game's replay screen (built)

The game does not embed this app. It imports the **logic and the SVG
directly from this package's source**, through a relative path out of
`frontend/src/`, and the SPA builds and serves it — no iframe, no web
component, no second copy of the code to keep in step. The two hosts share
the drawing and the maths and nothing else: every piece of chrome is the
host's own, because the standalone's chrome is antd and Tailwind and the
game's is neither.

**Exactly what the SPA imports** (each a direct relative import, none through
an index or a package boundary):

| Module | Used for |
|---|---|
| `utils/profile.ts` (`computeProfile`) | the course profile on the calendar and race screens |
| `components/CourseChart.tsx` | the elevation chart itself |
| `components/ElevationProfile.tsx` | chart + rider markers + pack blobs + tooltips |
| `components/RiderMarker.tsx`, `components/PackMarker.tsx` | the markers, incl. the own-team ring |
| `components/WindCompass.tsx` | the wind read-out in the game's playback bar |
| `utils/parseRaceLog.ts` | parsing a log fetched over HTTP |
| `utils/computePacks.ts` | pack grouping at the displayed tick |
| `utils/raceResults.ts` (`computeRaceResults`, `resultLabel`) | the result column |
| `utils/packGaps.ts` | the gap between packs |
| `utils/formatTime.ts` (`formatDuration`) | the elapsed clock |
| `utils/usePlayback.ts` (`usePlayback`, `PLAYBACK_SPEEDS`) | playback state and the six speeds |

Not imported, and not to be: `App.tsx`, `FileExplorer.tsx`, `RaceViz.tsx`,
`RiderList.tsx` and `PlaybackControls.tsx` — each is chrome for the standalone
alone, and the game has its own (`frontend/src/components/replay/`).

**The rule this creates: a module the SPA imports must stay free of antd and
of Tailwind.** The SPA has neither, and an import chain that pulled antd in
would ship the whole library to every manager. `WindCompass` is therefore
inline-styled, and any new shared module follows it. The frontend dedupes
`react`/`react-dom` in its `vite.config.ts` so shared components resolve to
the SPA's React copy rather than this package's, and CI installs this
package's `node_modules` before the SPA's build so its types resolve.

**Tests live where the code does.** This package's own vitest suite (node
environment) covers the parsing, pack, gap and result maths. Anything needing
a DOM — `usePlayback`, the markers' highlight rendering — is tested from
`frontend/src/`, which has jsdom, importing across the boundary exactly as the
app does. CI runs both suites.

## Development Guidelines

1. **Modularity:** Keep components decoupled. Data flows down from `App.tsx`.
2. **Performance:** Use `React.memo` for expensive renders (e.g. `RiderMarker`).
3. **Type Safety:** Define all data structures in `types/race.ts` and use them throughout.
4. **Styling:** Tailwind for layout; antd for complex UI elements. The
   exception is anything the SPA imports (see *Integration Strategy*), which
   must be inline-styled and antd-free.
5. **KNOWN ISSUE:** Antd v6 `Slider` has a bug: its `Portal` component has a `useEffect` with no dependency array that causes "Maximum update depth exceeded" when dragging. Do **not** re-add the Slider until antd is patched/upgraded. The playback seek control uses a plain native `<input type="range">` instead — see `PlaybackControls.tsx`.
